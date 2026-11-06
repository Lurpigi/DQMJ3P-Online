"""Public read-only API (/api/v1). Every response is built from explicit field lists: no source row
is serialized as-is, and friend codes, PIDs, save data, tokens and addresses never leave the
database (players are opaque ids, see decode.public_id)."""
import base64
import csv
import datetime
import hashlib
import io
import json
import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException

from . import db, queries
from .decode import GCUP_FPS, LANGUAGES, UTC

log = logging.getLogger("dashboard.api")
PREFIX = "/api/v1"
MODES = ("grade", "limit", "gcup")
STATUSES = ("upcoming", "open", "finalizing", "final")
MAX_EXPORT = 5000


def catalog_version(path):
    """Version of data/monsters.json (tools/import-monsters). The site reads the catalog itself as a
    static file; the API only reports which one it was built with. Missing file: None, the API runs."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("version")
    except (OSError, ValueError) as e:
        log.warning("monster catalog not loaded: %s", e)
        return None


class NotFound(HTTPException):
    def __init__(self):
        super().__init__(404, "not_found")


class BadRequest(HTTPException):
    def __init__(self, detail="invalid_parameter"):
        super().__init__(400, detail)


# --- formatting -----------------------------------------------------------------------------
def iso(t):
    return t.astimezone(UTC).isoformat().replace("+00:00", "Z") if t else None


def race_time(frames):
    if frames is None:
        return None
    return f"{frames // (60 * GCUP_FPS)}'{frames // GCUP_FPS % 60:02d}\"{frames % GCUP_FPS * 100 // GCUP_FPS:02d}"


def status_of(c, now):
    if c["final_revision"] is not None:
        return "final"
    if now < c["starts_at"]:
        return "upcoming"
    if now < c["ends_at"]:
        return "open"
    return "finalizing"


def official_today(c, now):
    return (now + datetime.timedelta(minutes=c["utc_offset_minutes"])).date()


def first_day(c):
    return (c["starts_at"] + datetime.timedelta(minutes=c["utc_offset_minutes"])).date()


def last_day(c):
    return (c["ends_at"] + datetime.timedelta(minutes=c["utc_offset_minutes"])).date() - datetime.timedelta(days=1)


def champ_out(c, now, extra=None):
    out = {
        "id": c["id"], "mode": c["mode"], "edition": c["source_edition"], "calendar_version": c["calendar_version"],
        "starts_at": iso(c["starts_at"]), "ends_at": iso(c["ends_at"]), "utc_offset_minutes": c["utc_offset_minutes"],
        "status": status_of(c, now), "revision": c["final_revision"], "finalized_at": iso(c["finalized_at"]),
        "rules": c["rules"], "rewards": c["rewards"], "cup": c["cup"],
        "definition_provenance": c["definition_provenance"], "coverage": c["coverage"] or {},
    }
    if c["mode"] != "gcup":
        out["days"] = {"first": first_day(c).isoformat(), "last": last_day(c).isoformat()}
    if extra:
        out.update(extra)
    return out


def player_ref(pid, name):
    return {"id": pid, "name": name or ""} if pid else None


def enc_cursor(data):
    return base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).decode().rstrip("=")


def dec_cursor(text):
    if not text:
        return None
    try:
        return json.loads(base64.urlsafe_b64decode(text + "=" * (-len(text) % 4)))
    except ValueError:
        raise BadRequest("invalid_cursor")


def csv_cell(value):
    """Spreadsheet-safe text: a leading = + - @ tab or CR would start a formula."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


class RateLimiter:
    def __init__(self, per_minute):
        self.per_minute, self.hits, self.lock, self.window = per_minute, {}, threading.Lock(), 0

    def allow(self, key):
        window = int(time.time() // 60)
        with self.lock:
            if window != self.window:
                self.hits, self.window = {}, window
            self.hits[key] = self.hits.get(key, 0) + 1
            return self.hits[key] <= self.per_minute


# --- application ----------------------------------------------------------------------------
def create_app(settings, start_importer=True, now=None):
    """now: fixed clock for tests."""
    state = {}
    clock = now or (lambda: datetime.datetime.now(UTC))

    @asynccontextmanager
    async def lifespan(app):
        state["pool"] = db.pool(settings.api_db_url, settings.statement_timeout_ms, name="api")
        state["catalog_version"] = catalog_version(settings.catalog)
        stop = threading.Event()
        thread = None
        if start_importer and settings.import_enabled:
            from .importer import Importer
            importer = Importer(settings)
            thread = threading.Thread(target=importer.run_forever, args=(stop,), daemon=True, name="importer")
            thread.start()
        yield
        stop.set()
        if thread:
            thread.join(timeout=10)
        state["pool"].close()

    app = FastAPI(title="DQMJ3P Online statistics", lifespan=lifespan, docs_url=f"{PREFIX}/docs",
                  openapi_url=f"{PREFIX}/openapi.json", redoc_url=None)
    if settings.allowed_origins:
        app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_methods=["GET"],
                           allow_headers=["If-None-Match"], expose_headers=["ETag"], max_age=3600)
    limiter = RateLimiter(settings.rate_limit)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        client = request.client.host if request.client else "-"
        if settings.trust_proxy:
            client = request.headers.get("x-forwarded-for", client).split(",")[0].strip()
        if not limiter.allow(client):
            return JSONResponse({"error": "rate_limited"}, status_code=429, headers={"Retry-After": "60"})
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(HTTPException)
    async def http_error(_request, exc):
        return JSONResponse({"error": exc.detail if isinstance(exc.detail, str) else "error"}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, exc):
        fields = [".".join(str(p) for p in e.get("loc", ())[1:]) for e in exc.errors()]
        return JSONResponse({"error": "invalid_parameter", "fields": fields}, status_code=400)

    def conn():
        return state["pool"].connection()

    def reply(request, data, max_age=15):
        body = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str).encode()
        etag = '"' + hashlib.sha256(body).hexdigest()[:20] + '"'
        headers = {"ETag": etag, "Cache-Control": f"public, max-age={max_age}"}
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        return Response(body, media_type="application/json", headers=headers)

    def get_champ(c, cid):
        row = c.execute("SELECT * FROM dashboard.championships WHERE id = %s", (cid,)).fetchone()
        if not row:
            raise NotFound()
        return row

    def entrants(c, champ, now):
        if champ["final_revision"] is not None:
            return c.execute("SELECT count(*) AS n FROM dashboard.standings WHERE championship_id = %s AND revision = %s",
                             (champ["id"], champ["final_revision"])).fetchone()["n"]
        if champ["mode"] == "gcup":
            return c.execute("SELECT count(DISTINCT player_id) AS n FROM dashboard.gcup_best WHERE championship_id = %s",
                             (champ["id"],)).fetchone()["n"]
        return c.execute("SELECT count(DISTINCT player_id) AS n FROM dashboard.entries WHERE championship_id = %s "
                         "AND validation = 'unverified'", (champ["id"],)).fetchone()["n"]

    def views(champ, now):
        status = status_of(champ, now)
        if status == "final":
            return ["final"]
        if champ["mode"] == "gcup":
            return ["live"]
        return ["published", "provisional"] if status == "open" else ["provisional"]

    def standings(c, champ, view, now, max_entry=None, revision=None):
        """(rows, meta) for a view: final (a revision), live (G-Cup), published / provisional (GP)."""
        meta = {"view": view}
        if view == "final":
            rev = revision or champ["final_revision"]
            rows = c.execute("SELECT * FROM dashboard.standings WHERE championship_id = %s AND revision = %s ORDER BY position",
                             (champ["id"], rev)).fetchall()
            if not rows and revision and revision != champ["final_revision"]:
                exists = c.execute("SELECT 1 FROM dashboard.revisions WHERE championship_id = %s AND revision = %s",
                                   (champ["id"], rev)).fetchone()
                if not exists:
                    raise NotFound()
            meta["revision"] = rev
            return rows, meta
        if view == "live":
            rows = queries.gcup_live(c, champ["id"])
            return rows, meta
        if max_entry is None:
            max_entry = c.execute("SELECT max(id) AS m FROM dashboard.entries WHERE championship_id = %s",
                                  (champ["id"],)).fetchone()["m"] or 0
        meta["as_of_entry"] = str(max_entry)
        cutoff = None
        if view == "published":
            cutoff = min(official_today(champ, now), last_day(champ) + datetime.timedelta(days=1))
            meta["cutoff_day"] = cutoff.isoformat()
            meta["first_day"] = cutoff <= first_day(champ)
        rows = queries.gp_standings(c, champ["id"], cutoff, max_entry)
        if view == "published" and cutoff and cutoff - datetime.timedelta(days=1) > first_day(champ):
            before = queries.gp_standings(c, champ["id"], cutoff - datetime.timedelta(days=1), max_entry)
            previous = {r["player_id"]: r["rank"] for r in before}
            for r in rows:
                r["previous_rank"] = previous.get(r["player_id"])
        return rows, meta

    def teams_for(c, champ_id, player_ids):
        """Latest recorded team of each player in an edition: {player_id: [species, ...]}."""
        if not player_ids:
            return {}
        rows = c.execute(
            """SELECT DISTINCT ON (e.player_id) e.player_id, e.id FROM dashboard.entries e
               WHERE e.championship_id = %s AND e.player_id = ANY(%s) AND e.kind = 'gp'
                 AND EXISTS (SELECT 1 FROM dashboard.team_members t WHERE t.entry_id = e.id)
               ORDER BY e.player_id, e.received_at DESC, e.id DESC""", (champ_id, list(player_ids))).fetchall()
        return team_species(c, {r["id"]: r["player_id"] for r in rows})

    def team_species(c, entry_to_key):
        out = {}
        if not entry_to_key:
            return out
        for t in c.execute("SELECT entry_id, slot, species, level FROM dashboard.team_members WHERE entry_id = ANY(%s) "
                           "ORDER BY entry_id, slot", (list(entry_to_key),)):
            out.setdefault(entry_to_key[t["entry_id"]], []).append({"species": t["species"], "level": t["level"]})
        return out

    def standing_out(r, mode, team=None):
        out = {"position": r["position"], "rank": r["rank"], "player": player_ref(r["player_id"], r.get("name")),
               "location": r.get("location")}
        if mode == "gcup":
            out.update({"frames": r.get("frames"), "time": race_time(r.get("frames"))})
        else:
            out.update({"points": {"total": r.get("points"), "win": r.get("points_win"), "popularity": r.get("points_pop"),
                                   "strength": r.get("points_strength"), "evaluation": r.get("points_eval")},
                        "rounds": r.get("rounds"), "rounds_won": r.get("rounds_won"), "entries": r.get("entries")})
            if "previous_rank" in r:
                out["previous_rank"] = r["previous_rank"]
        if team is not None:
            out["team"] = team
        return out

    def entry_out(e, champ=None, team=None, rounds=None):
        out = {"id": str(e["id"]), "kind": e["kind"], "championship": e["championship_id"],
               "player": player_ref(e["player_id"], e["observed_name"]), "name_provenance": e["name_provenance"],
               "received_at": iso(e["received_at"]), "validation": e["validation"], "signature": e["signature"]}
        if e["kind"] == "gp":
            out.update({"contest_day": e["contest_day"].isoformat() if e["contest_day"] else None,
                        "location": e["observed_location"],
                        "points": {"total": e["points"], "win": e["points_win"], "popularity": e["points_pop"],
                                   "strength": e["points_strength"], "evaluation": e["points_eval"]},
                        "rounds": e["rounds"], "rounds_won": e["rounds_won"]})
        else:
            out.update({"frames": e["frames"], "time": race_time(e["frames"]), "improved": e["improved"]})
        if champ is not None:
            out["championship_mode"] = champ
        if team is not None:
            out["team"] = team
        if rounds is not None:
            out["round_results"] = rounds
        return out

    def page(rows, limit, key):
        more = len(rows) > limit
        rows = rows[:limit]
        return rows, (enc_cursor(key(rows[-1])) if more and rows else None)

    # --- endpoints --------------------------------------------------------------------------
    @app.get(f"{PREFIX}/health")
    def health():
        with conn() as c:
            c.execute("SELECT 1")
        return {"ok": True}

    def current_editions(c, now):
        out = {}
        for mode in MODES:
            row = c.execute("SELECT * FROM dashboard.championships WHERE mode = %s AND starts_at <= %s "
                            "ORDER BY starts_at DESC LIMIT 1", (mode, now)).fetchone()
            out[mode] = row
        return out

    def freshness(c, now):
        out = []
        for r in c.execute("SELECT * FROM dashboard.freshness ORDER BY source"):
            lag = (now - r["source_as_of"]).total_seconds() if r["source_as_of"] else None
            out.append({"source": r["source"], "as_of": iso(r["source_as_of"]), "lag_seconds": round(lag) if lag is not None else None,
                        "failing": bool(r["failing"])})
        return out

    @app.get(f"{PREFIX}/meta")
    def meta(request: Request):
        now = clock()
        with conn() as c:
            current = current_editions(c, now)
            gp = next((r for m, r in current.items() if m != "gcup" and r), None)
            data = {"server_id": settings.server_id, "locales": list(LANGUAGES), "modes": list(MODES),
                    "current": {m: champ_out(r, now) if r else None for m, r in current.items()},
                    "time_zones": {"gp_utc_offset_minutes": gp["utc_offset_minutes"] if gp else None,
                                   "gcup_utc_offset_minutes": 0},
                    "catalog_version": state["catalog_version"], "freshness": freshness(c, now), "now": iso(now)}
        return reply(request, data, 30)

    @app.get(f"{PREFIX}/overview")
    def overview(request: Request):
        now = clock()
        with conn() as c:
            panels = []
            for mode, champ in current_editions(c, now).items():
                panel = {"mode": mode, "current": None, "leaders": [], "view": None, "previous": None}
                if champ:
                    view = views(champ, now)[0]
                    rows, meta_ = standings(c, champ, view, now)
                    teams = teams_for(c, champ["id"], [r["player_id"] for r in rows[:5]]) if mode != "gcup" else {}
                    panel.update({"current": champ_out(champ, now, {"entrants": entrants(c, champ, now)}), "view": meta_,
                                  "leaders": [standing_out(r, mode, teams.get(r["player_id"])) for r in rows[:5]]})
                    prev = c.execute("SELECT * FROM dashboard.championships WHERE mode = %s AND starts_at < %s "
                                     "AND final_revision IS NOT NULL ORDER BY starts_at DESC LIMIT 1",
                                     (mode, champ["starts_at"])).fetchone()
                    if prev:
                        podium, _ = standings(c, prev, "final", now)
                        panel["previous"] = {"championship": champ_out(prev, now, {"entrants": len(podium)}),
                                             "podium": [standing_out(r, mode) for r in podium if r["rank"] <= 3][:5]}
                panels.append(panel)
            recent = c.execute("SELECT * FROM dashboard.entries WHERE validation = 'unverified' "
                               "ORDER BY received_at DESC, id DESC LIMIT 10").fetchall()
            modes = {r["id"]: r["mode"] for r in c.execute(
                "SELECT id, mode FROM dashboard.championships WHERE id = ANY(%s)", ([e["championship_id"] for e in recent],))}
            recent_teams = team_species(c, {e["id"]: e["id"] for e in recent})
            data = {"panels": panels, "recent": [entry_out(e, modes.get(e["championship_id"]), recent_teams.get(e["id"], []))
                                                 for e in recent],
                    "freshness": freshness(c, now), "now": iso(now)}
        return reply(request, data, 15)

    @app.get(f"{PREFIX}/championships")
    def championships(request: Request, mode: str | None = Query(None, pattern="^(grade|limit|gcup)$"),
                      status: str | None = Query(None, pattern="^(upcoming|open|finalizing|final)$"),
                      year: int | None = Query(None, ge=2000, le=2100), q: str | None = Query(None, max_length=40),
                      cursor: str | None = None, limit: int = Query(25, ge=1, le=100)):
        now = clock()
        where, args = ["TRUE"], {"now": now, "limit": limit + 1}
        if mode:
            where.append("c.mode = %(mode)s")
            args["mode"] = mode
        if year:
            where.append("extract(year FROM c.starts_at) = %(year)s")
            args["year"] = year
        status_sql = {"final": "c.final_revision IS NOT NULL",
                      "upcoming": "c.final_revision IS NULL AND c.starts_at > %(now)s",
                      "open": "c.final_revision IS NULL AND c.starts_at <= %(now)s AND c.ends_at > %(now)s",
                      "finalizing": "c.final_revision IS NULL AND c.ends_at <= %(now)s"}
        if status:
            where.append(status_sql[status])
        if q:
            q = q.strip()
            digits = "".join(ch for ch in q if ch.isdigit())
            where.append("(c.id ILIKE %(q)s OR (c.cup ->> 'name') ILIKE %(q)s OR c.source_edition::text = %(digits)s)")
            args.update({"q": f"%{q}%", "digits": digits or "-"})
        after = dec_cursor(cursor)
        if after:
            where.append("(c.starts_at, c.id) < (%(after_start)s, %(after_id)s)")
            args.update({"after_start": after["s"], "after_id": after["i"]})
        with conn() as c:
            rows = c.execute(f"SELECT c.* FROM dashboard.championships c WHERE {' AND '.join(where)} "
                             "ORDER BY c.starts_at DESC, c.id DESC LIMIT %(limit)s", args).fetchall()
            rows, nxt = page(rows, limit, lambda r: {"s": iso(r["starts_at"]), "i": r["id"]})
            winners = {w["championship_id"]: w for w in c.execute(
                "SELECT s.championship_id, s.player_id, s.name FROM dashboard.standings s JOIN dashboard.championships c "
                "ON c.id = s.championship_id AND s.revision = c.final_revision WHERE s.position = 1 AND c.id = ANY(%s)",
                ([r["id"] for r in rows],))}
            items = [champ_out(r, now, {"entrants": entrants(c, r, now),
                                        "winner": player_ref(winners[r["id"]]["player_id"], winners[r["id"]]["name"])
                                        if r["id"] in winners else None}) for r in rows]
        return reply(request, {"items": items, "next_cursor": nxt}, 30)

    @app.get(f"{PREFIX}/championships/{{cid}}")
    def championship(request: Request, cid: str):
        now = clock()
        with conn() as c:
            champ = get_champ(c, cid)
            revisions = c.execute("SELECT revision, created_at, reason FROM dashboard.revisions WHERE championship_id = %s "
                                  "ORDER BY revision", (cid,)).fetchall()
            near = {}
            for key, op, order in (("previous", "<", "DESC"), ("next", ">", "ASC")):
                r = c.execute(f"SELECT id FROM dashboard.championships WHERE mode = %s AND starts_at {op} %s "
                              f"ORDER BY starts_at {order} LIMIT 1", (champ["mode"], champ["starts_at"])).fetchone()
                near[key] = r["id"] if r else None
            counts = c.execute("SELECT count(*) AS entries, count(DISTINCT contest_day) AS days FROM dashboard.entries "
                               "WHERE championship_id = %s AND validation <> 'source_lost'", (cid,)).fetchone()
            data = champ_out(champ, now, {
                "entrants": entrants(c, champ, now), "entries": counts["entries"], "views": views(champ, now),
                "revisions": [{"revision": r["revision"], "created_at": iso(r["created_at"]), "reason": r["reason"]}
                              for r in revisions], **near})
        return reply(request, data, 300 if champ["final_revision"] else 15)

    @app.get(f"{PREFIX}/championships/{{cid}}/standings")
    def championship_standings(request: Request, cid: str,
                               view: str | None = Query(None, pattern="^(final|live|published|provisional)$"),
                               revision: int | None = Query(None, ge=1), q: str | None = Query(None, max_length=40),
                               cursor: str | None = None, limit: int = Query(25, ge=1, le=100),
                               format: str | None = Query(None, pattern="^(csv|json)$")):
        now = clock()
        after = dec_cursor(cursor)
        with conn() as c:
            champ = get_champ(c, cid)
            allowed = views(champ, now)
            view = (after or {}).get("v") or view or allowed[0]
            if view not in allowed:
                raise BadRequest("view_not_available")
            rows, meta_ = standings(c, champ, view, now, int(after["a"]) if after and after.get("a") else None,
                                    revision or (after or {}).get("r"))
            total = len(rows)
            if q:
                key = q.casefold().strip()
                rows = [r for r in rows if key in (r.get("name") or "").casefold()]
            if format:
                return export(champ, rows[:MAX_EXPORT], meta_, format, now)
            start = (after or {}).get("p", 0)
            rows = [r for r in rows if r["position"] > start]
            rows, more = rows[:limit], len(rows) > limit
            teams = teams_for(c, cid, [r["player_id"] for r in rows]) if champ["mode"] != "gcup" else {}
            nxt = enc_cursor({"v": view, "a": meta_.get("as_of_entry"), "r": meta_.get("revision"),
                              "p": rows[-1]["position"]}) if more and rows else None
            data = {"championship": champ_out(champ, now), "views": allowed, **meta_, "total": total,
                    "rows": [standing_out(r, champ["mode"], teams.get(r["player_id"])) for r in rows], "next_cursor": nxt}
        return reply(request, data, 300 if view == "final" else 15)

    def export(champ, rows, meta_, fmt, now):
        mode = champ["mode"]
        out_rows = [standing_out(r, mode) for r in rows]
        head = {"championship": champ["id"], "mode": mode, "view": meta_["view"], "revision": meta_.get("revision"),
                "cutoff_day": meta_.get("cutoff_day"), "as_of_entry": meta_.get("as_of_entry"), "exported_at": iso(now)}
        name = f"{champ['id']}-{meta_['view']}" + (f"-r{meta_['revision']}" if meta_.get("revision") else "")
        disposition = {"Content-Disposition": f'attachment; filename="{name}.{fmt}"', "Cache-Control": "public, max-age=60"}
        if fmt == "json":
            return Response(json.dumps({**head, "rows": out_rows}, ensure_ascii=False), media_type="application/json",
                            headers=disposition)
        buf = io.StringIO()
        w = csv.writer(buf)
        cols = ["championship", "view", "revision", "cutoff_day", "position", "rank", "player_id", "player_name", "location"]
        cols += ["frames", "time"] if mode == "gcup" else ["points", "win", "popularity", "strength", "evaluation",
                                                           "rounds", "rounds_won", "entries"]
        w.writerow(cols)
        for r in out_rows:
            base = [head["championship"], head["view"], head["revision"], head["cutoff_day"], r["position"], r["rank"],
                    r["player"]["id"], r["player"]["name"], r["location"]]
            if mode == "gcup":
                base += [r["frames"], r["time"]]
            else:
                p = r["points"]
                base += [p["total"], p["win"], p["popularity"], p["strength"], p["evaluation"], r["rounds"],
                         r["rounds_won"], r["entries"]]
            w.writerow([csv_cell(v) for v in base])
        return Response(buf.getvalue(), media_type="text/csv; charset=utf-8", headers=disposition)

    def entries_query(c, where, args, limit, cursor):
        after = dec_cursor(cursor)
        if after:
            where.append("(e.received_at, e.id) < (%(after_t)s, %(after_id)s)")
            args.update({"after_t": after["t"], "after_id": int(after["i"])})
        args["limit"] = limit + 1
        rows = c.execute(f"SELECT e.*, c.mode FROM dashboard.entries e JOIN dashboard.championships c ON c.id = e.championship_id "
                         f"WHERE {' AND '.join(where)} ORDER BY e.received_at DESC, e.id DESC LIMIT %(limit)s", args).fetchall()
        rows, nxt = page(rows, limit, lambda r: {"t": iso(r["received_at"]), "i": str(r["id"])})
        teams = team_species(c, {r["id"]: r["id"] for r in rows})
        rounds = {}
        for r in c.execute("SELECT entry_id, idx, won FROM dashboard.rounds WHERE entry_id = ANY(%s) ORDER BY entry_id, idx",
                           ([r["id"] for r in rows],)):
            rounds.setdefault(r["entry_id"], []).append({"idx": r["idx"], "won": r["won"]})
        items = [entry_out(r, r["mode"], teams.get(r["id"], []), rounds.get(r["id"])) for r in rows]
        return items, nxt

    @app.get(f"{PREFIX}/championships/{{cid}}/results")
    def championship_results(request: Request, cid: str, player: str | None = Query(None, max_length=20),
                             species: int | None = Query(None, ge=1, le=2000),
                             day: datetime.date | None = None, cursor: str | None = None,
                             limit: int = Query(25, ge=1, le=100)):
        with conn() as c:
            get_champ(c, cid)
            where, args = ["e.championship_id = %(cid)s", "e.validation <> 'source_lost'"], {"cid": cid}
            if player:
                where.append("e.player_id = %(player)s")
                args["player"] = player
            if species:
                where.append("EXISTS (SELECT 1 FROM dashboard.team_members t WHERE t.entry_id = e.id AND t.species = %(species)s)")
                args["species"] = species
            if day:
                where.append("e.contest_day = %(day)s")
                args["day"] = day
            items, nxt = entries_query(c, where, args, limit, cursor)
        return reply(request, {"items": items, "next_cursor": nxt}, 30)

    def usage(c, where_sql, args, top=20):
        """Monster usage: share of player teams (latest team of each player in each edition) that
        contain a species. Repeated uploads of one player do not inflate it."""
        rows = c.execute(f"""
            WITH teams AS (
                SELECT DISTINCT ON (e.championship_id, e.player_id) e.id
                FROM dashboard.entries e
                WHERE e.kind = 'gp' AND e.validation = 'unverified' AND {where_sql}
                  AND EXISTS (SELECT 1 FROM dashboard.team_members t WHERE t.entry_id = e.id)
                ORDER BY e.championship_id, e.player_id, e.received_at DESC, e.id DESC)
            SELECT t.species, count(DISTINCT t.entry_id)::int AS teams, (SELECT count(*) FROM teams)::int AS total
            FROM dashboard.team_members t JOIN teams ON teams.id = t.entry_id
            GROUP BY t.species ORDER BY teams DESC, t.species LIMIT %(top)s""", {**args, "top": top}).fetchall()
        total = rows[0]["total"] if rows else c.execute(f"""
            SELECT count(*)::int AS n FROM (SELECT DISTINCT e.championship_id, e.player_id FROM dashboard.entries e
            WHERE e.kind = 'gp' AND e.validation = 'unverified' AND {where_sql}
              AND EXISTS (SELECT 1 FROM dashboard.team_members t WHERE t.entry_id = e.id)) x""", args).fetchone()["n"]
        return {"unit": "player_team_per_edition", "teams": total,
                "species": [{"species": r["species"], "teams": r["teams"]} for r in rows]}

    @app.get(f"{PREFIX}/championships/{{cid}}/stats")
    def championship_stats(request: Request, cid: str):
        now = clock()
        with conn() as c:
            champ = get_champ(c, cid)
            per_day = c.execute(
                "SELECT contest_day, count(*)::int AS entries, count(DISTINCT player_id)::int AS players FROM dashboard.entries "
                "WHERE championship_id = %s AND validation = 'unverified' AND contest_day IS NOT NULL "
                "GROUP BY contest_day ORDER BY contest_day", (cid,)).fetchall()
            totals = c.execute(
                "SELECT count(*)::int AS entries, COALESCE(sum(rounds), 0)::int AS rounds, COALESCE(sum(rounds_won), 0)::int AS rounds_won, "
                "count(*) FILTER (WHERE signature = 'valid')::int AS signed, min(frames) AS best_frames "
                "FROM dashboard.entries WHERE championship_id = %s AND validation = 'unverified'", (cid,)).fetchone()
            data = {"championship": cid, "entrants": entrants(c, champ, now), **totals,
                    "best_time": race_time(totals["best_frames"]),
                    "per_day": [{"day": r["contest_day"].isoformat(), "entries": r["entries"], "players": r["players"]}
                                for r in per_day]}
            if champ["mode"] != "gcup":
                data["usage"] = usage(c, "e.championship_id = %(cid)s", {"cid": cid})
        return reply(request, data, 300 if champ["final_revision"] else 30)

    @app.get(f"{PREFIX}/players")
    def players(request: Request, q: str | None = Query(None, max_length=40),
                namespace: str | None = Query(None, pattern="^(sil|nex)$"),
                mode: str | None = Query(None, pattern="^(grade|limit|gcup)$"),
                cursor: str | None = None, limit: int = Query(25, ge=1, le=100)):
        where, args = ["TRUE"], {"limit": limit + 1}
        if q:
            key = q.casefold().strip()
            where.append("(p.name_search LIKE %(q)s OR p.id = %(exact)s OR EXISTS (SELECT 1 FROM dashboard.player_aliases a "
                         "WHERE a.player_id = p.id AND a.name_search LIKE %(q)s))")
            args.update({"q": "%" + key.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%", "exact": q.strip()})
        if namespace:
            where.append("p.namespace = %(ns)s")
            args["ns"] = namespace
        if mode:
            where.append("(EXISTS (SELECT 1 FROM dashboard.entries e JOIN dashboard.championships c ON c.id = e.championship_id "
                         "WHERE e.player_id = p.id AND c.mode = %(mode)s) OR EXISTS (SELECT 1 FROM dashboard.standings s "
                         "JOIN dashboard.championships c ON c.id = s.championship_id WHERE s.player_id = p.id AND c.mode = %(mode)s))")
            args["mode"] = mode
        after = dec_cursor(cursor)
        if after:
            where.append("(p.last_seen, p.id) < (%(after_t)s, %(after_id)s)")
            args.update({"after_t": after["t"], "after_id": after["i"]})
        with conn() as c:
            rows = c.execute(
                f"""SELECT p.*, (SELECT count(DISTINCT championship_id) FROM dashboard.standings s WHERE s.player_id = p.id)::int AS finals,
                    (SELECT array_agg(a.name ORDER BY a.last_seen DESC) FROM dashboard.player_aliases a WHERE a.player_id = p.id) AS aliases
                    FROM dashboard.players p WHERE p.last_seen IS NOT NULL AND {' AND '.join(where)}
                    ORDER BY p.last_seen DESC, p.id DESC LIMIT %(limit)s""", args).fetchall()
            rows, nxt = page(rows, limit, lambda r: {"t": iso(r["last_seen"]), "i": r["id"]})
            items = [{"id": r["id"], "name": r["display_name"], "source": r["namespace"],
                      "aliases": [a for a in dict.fromkeys(r["aliases"] or []) if a != r["display_name"]][:5],
                      "first_seen": iso(r["first_seen"]), "last_seen": iso(r["last_seen"]), "final_standings": r["finals"]}
                     for r in rows]
        return reply(request, {"items": items, "next_cursor": nxt}, 30)

    def get_player(c, pid):
        row = c.execute("SELECT * FROM dashboard.players WHERE id = %s", (pid,)).fetchone()
        if not row:
            raise NotFound()
        return row

    def placements(c, pid, mode=None):
        args = {"pid": pid, "mode": mode}
        return c.execute(
            """SELECT s.*, c.mode, c.source_edition, c.starts_at, c.ends_at, c.cup,
                  (SELECT count(*) FROM dashboard.standings x WHERE x.championship_id = s.championship_id AND x.revision = s.revision)::int AS entrants
               FROM dashboard.standings s JOIN dashboard.championships c ON c.id = s.championship_id AND s.revision = c.final_revision
               WHERE s.player_id = %(pid)s AND (%(mode)s::text IS NULL OR c.mode = %(mode)s)
               ORDER BY c.starts_at DESC""", args).fetchall()

    def current_positions(c, pid, now):
        """The player's place in the editions still running (published view for GP when it exists)."""
        out = []
        rows = c.execute(
            """SELECT DISTINCT c.* FROM dashboard.championships c WHERE c.final_revision IS NULL AND c.starts_at <= %(now)s
               AND (EXISTS (SELECT 1 FROM dashboard.entries e WHERE e.championship_id = c.id AND e.player_id = %(pid)s)
                 OR EXISTS (SELECT 1 FROM dashboard.gcup_best b WHERE b.championship_id = c.id AND b.player_id = %(pid)s))""",
            {"now": now, "pid": pid}).fetchall()
        for champ in rows:
            view = views(champ, now)[0]
            ranked, meta_ = standings(c, champ, view, now)
            mine = next((r for r in ranked if r["player_id"] == pid), None)
            if view == "published" and mine is None:
                view = "provisional"
                ranked, meta_ = standings(c, champ, view, now)
                mine = next((r for r in ranked if r["player_id"] == pid), None)
            out.append({"championship": champ_out(champ, now), "view": view, "entrants": len(ranked),
                        "standing": standing_out(mine, champ["mode"]) if mine else None})
        return out

    @app.get(f"{PREFIX}/players/{{pid}}")
    def player(request: Request, pid: str):
        now = clock()
        with conn() as c:
            p = get_player(c, pid)
            aliases = c.execute("SELECT name, provenance, first_seen, last_seen FROM dashboard.player_aliases WHERE player_id = %s "
                                "ORDER BY last_seen DESC LIMIT 20", (pid,)).fetchall()
            places = placements(c, pid)
            summary = {}
            for mode in MODES:
                mine = [r for r in places if r["mode"] == mode]
                stats = c.execute("SELECT count(*)::int AS entries, count(DISTINCT e.championship_id)::int AS editions, "
                                  "COALESCE(sum(rounds_won), 0)::int AS rounds_won, COALESCE(sum(rounds), 0)::int AS rounds, "
                                  "min(frames) AS best_frames FROM dashboard.entries e JOIN dashboard.championships c "
                                  "ON c.id = e.championship_id WHERE e.player_id = %s AND c.mode = %s AND e.validation = 'unverified'",
                                  (pid, mode)).fetchone()
                summary[mode] = {"finals": len(mine), "titles": sum(1 for r in mine if r["rank"] == 1),
                                 "podiums": sum(1 for r in mine if r["rank"] <= 3),
                                 "best_rank": min((r["rank"] for r in mine), default=None),
                                 "entries": stats["entries"], "editions_entered": stats["editions"],
                                 "rounds": stats["rounds"], "rounds_won": stats["rounds_won"],
                                 "best_frames": stats["best_frames"], "best_time": race_time(stats["best_frames"])}
            data = {"id": p["id"], "name": p["display_name"], "source": p["namespace"],
                    "first_seen": iso(p["first_seen"]), "last_seen": iso(p["last_seen"]),
                    "aliases": [{"name": a["name"], "provenance": a["provenance"], "first_seen": iso(a["first_seen"]),
                                 "last_seen": iso(a["last_seen"])} for a in aliases],
                    "summary": summary, "current": current_positions(c, pid, now)}
        return reply(request, data, 30)

    @app.get(f"{PREFIX}/players/{{pid}}/championships")
    def player_championships(request: Request, pid: str, mode: str | None = Query(None, pattern="^(grade|limit|gcup)$")):
        now = clock()
        with conn() as c:
            get_player(c, pid)
            items = [{"championship": {"id": r["championship_id"], "mode": r["mode"], "edition": r["source_edition"],
                                       "starts_at": iso(r["starts_at"]), "ends_at": iso(r["ends_at"]),
                                       "cup": r["cup"]},
                      "revision": r["revision"], "entrants": r["entrants"], "standing": standing_out(r, r["mode"])}
                     for r in placements(c, pid, mode)]
            data = {"items": items, "current": [x for x in current_positions(c, pid, now)
                                                if not mode or x["championship"]["mode"] == mode]}
        return reply(request, data, 60)

    @app.get(f"{PREFIX}/players/{{pid}}/results")
    def player_results(request: Request, pid: str, mode: str | None = Query(None, pattern="^(grade|limit|gcup)$"),
                       championship: str | None = Query(None, max_length=40), cursor: str | None = None,
                       limit: int = Query(25, ge=1, le=100)):
        with conn() as c:
            get_player(c, pid)
            where, args = ["e.player_id = %(pid)s", "e.validation <> 'source_lost'"], {"pid": pid}
            if mode:
                where.append("c.mode = %(mode)s")
                args["mode"] = mode
            if championship:
                where.append("e.championship_id = %(cid)s")
                args["cid"] = championship
            items, nxt = entries_query(c, where, args, limit, cursor)
        return reply(request, {"items": items, "next_cursor": nxt}, 30)

    @app.get(f"{PREFIX}/players/{{pid}}/teams")
    def player_teams(request: Request, pid: str, mode: str | None = Query(None, pattern="^(grade|limit)$"),
                     limit: int = Query(50, ge=1, le=100)):
        with conn() as c:
            get_player(c, pid)
            rows = c.execute(
                """SELECT DISTINCT ON (c.starts_at, e.championship_id) e.id, e.championship_id, e.received_at, c.mode,
                          c.source_edition, c.starts_at
                   FROM dashboard.entries e JOIN dashboard.championships c ON c.id = e.championship_id
                   WHERE e.player_id = %s AND e.kind = 'gp' AND e.validation = 'unverified' AND (%s::text IS NULL OR c.mode = %s)
                     AND EXISTS (SELECT 1 FROM dashboard.team_members t WHERE t.entry_id = e.id)
                   ORDER BY c.starts_at DESC, e.championship_id, e.received_at DESC, e.id DESC LIMIT %s""",
                (pid, mode, mode, limit)).fetchall()
            teams = team_species(c, {r["id"]: r["id"] for r in rows})
            items = [{"championship": {"id": r["championship_id"], "mode": r["mode"], "edition": r["source_edition"],
                                       "starts_at": iso(r["starts_at"])},
                      "entry": str(r["id"]), "recorded_at": iso(r["received_at"]), "team": teams.get(r["id"], [])}
                     for r in rows]
        return reply(request, {"items": items}, 60)

    @app.get(f"{PREFIX}/results/{{eid}}")
    def result(request: Request, eid: str):
        now = clock()
        if not eid.isdigit():
            raise NotFound()
        with conn() as c:
            e = c.execute("SELECT * FROM dashboard.entries WHERE id = %s", (int(eid),)).fetchone()
            if not e:
                raise NotFound()
            champ = get_champ(c, e["championship_id"])
            team = [{"slot": t["slot"], "species": t["species"], "level": t["level"],
                     "stats": {k: t[k] for k in ("hp", "mp", "atk", "def", "agi", "wis")}}
                    for t in c.execute("SELECT * FROM dashboard.team_members WHERE entry_id = %s ORDER BY slot", (e["id"],))]
            rounds = [{"idx": r["idx"], "opponent": {"name": r["opponent_name"],
                                                    "player": player_ref(r["opponent_player_id"], r["opponent_display"])},
                       "won": r["won"], "points": {"win": r["points_win"], "popularity": r["points_pop"],
                                                   "strength": r["points_strength"], "evaluation": r["points_eval"]}}
                      for r in c.execute("SELECT r.*, p.display_name AS opponent_display FROM dashboard.rounds r "
                                         "LEFT JOIN dashboard.players p ON p.id = r.opponent_player_id WHERE r.entry_id = %s "
                                         "ORDER BY r.idx", (e["id"],))]
            data = entry_out(e, champ["mode"], team, rounds)
            data["championship_detail"] = champ_out(champ, now)
        return reply(request, data, 300)

    @app.get(f"{PREFIX}/battles")
    def battles(request: Request, championship: str | None = Query(None, max_length=40),
                player: str | None = Query(None, max_length=20), mode: str | None = Query(None, pattern="^(grade|limit)$"),
                species: int | None = Query(None, ge=1, le=2000), since: datetime.date | None = Query(None, alias="from"),
                until: datetime.date | None = Query(None, alias="to"), cursor: str | None = None,
                limit: int = Query(25, ge=1, le=100)):
        where, args = ["e.kind = 'gp'", "e.validation = 'unverified'"], {"limit": limit + 1}
        if championship:
            where.append("e.championship_id = %(cid)s")
            args["cid"] = championship
        if player:
            where.append("(e.player_id = %(player)s OR r.opponent_player_id = %(player)s)")
            args["player"] = player
        if mode:
            where.append("c.mode = %(mode)s")
            args["mode"] = mode
        if species:
            where.append("EXISTS (SELECT 1 FROM dashboard.team_members t WHERE t.entry_id = e.id AND t.species = %(species)s)")
            args["species"] = species
        if since:
            where.append("e.received_at >= %(since)s")
            args["since"] = datetime.datetime.combine(since, datetime.time(), UTC)
        if until:
            if since and until < since:
                raise BadRequest("invalid_range")
            where.append("e.received_at < %(until)s")
            args["until"] = datetime.datetime.combine(until + datetime.timedelta(days=1), datetime.time(), UTC)
        after = dec_cursor(cursor)
        if after:
            where.append("(e.received_at, e.id, r.idx) < (%(t)s, %(i)s, %(x)s)")
            args.update({"t": after["t"], "i": int(after["i"]), "x": after["x"]})
        with conn() as c:
            rows = c.execute(
                f"""SELECT r.*, e.player_id, e.observed_name, e.received_at, e.championship_id, c.mode,
                          o.display_name AS opponent_display
                    FROM dashboard.rounds r JOIN dashboard.entries e ON e.id = r.entry_id
                    JOIN dashboard.championships c ON c.id = e.championship_id
                    LEFT JOIN dashboard.players o ON o.id = r.opponent_player_id
                    WHERE {' AND '.join(where)} ORDER BY e.received_at DESC, e.id DESC, r.idx DESC LIMIT %(limit)s""",
                args).fetchall()
            rows, nxt = page(rows, limit, lambda r: {"t": iso(r["received_at"]), "i": str(r["entry_id"]), "x": r["idx"]})
            teams = team_species(c, {r["entry_id"]: r["entry_id"] for r in rows})
            items = [{"entry": str(r["entry_id"]), "round": r["idx"] + 1, "championship": r["championship_id"], "mode": r["mode"],
                      "received_at": iso(r["received_at"]), "player": player_ref(r["player_id"], r["observed_name"]),
                      "team": teams.get(r["entry_id"], []),
                      "opponent": {"name": r["opponent_name"], "player": player_ref(r["opponent_player_id"], r["opponent_display"])},
                      "won": r["won"], "points": {"win": r["points_win"], "popularity": r["points_pop"],
                                                  "strength": r["points_strength"], "evaluation": r["points_eval"]}}
                     for r in rows]
        coverage = {"grand_prix_rounds": "recorded", "direct_battles": "unavailable"}
        return reply(request, {"items": items, "next_cursor": nxt, "coverage": coverage}, 30)

    @app.get(f"{PREFIX}/monsters/{{species}}/stats")
    def monster_stats(request: Request, species: int):
        with conn() as c:
            by_mode = {}
            for mode in ("grade", "limit"):
                u = usage(c, "EXISTS (SELECT 1 FROM dashboard.championships c WHERE c.id = e.championship_id AND c.mode = %(mode)s)",
                          {"mode": mode}, top=2000)
                mine = next((s["teams"] for s in u["species"] if s["species"] == species), 0)
                by_mode[mode] = {"teams": u["teams"], "with_species": mine}
            recent = c.execute(
                """SELECT e.id, e.player_id, e.observed_name, e.received_at, e.championship_id, e.points, c.mode
                   FROM dashboard.entries e JOIN dashboard.championships c ON c.id = e.championship_id
                   WHERE e.validation = 'unverified' AND EXISTS (SELECT 1 FROM dashboard.team_members t WHERE t.entry_id = e.id AND t.species = %s)
                   ORDER BY e.received_at DESC, e.id DESC LIMIT 10""", (species,)).fetchall()
            teams = team_species(c, {r["id"]: r["id"] for r in recent})
            data = {"species": species, "unit": "player_team_per_edition", "by_mode": by_mode,
                    "recent": [{"entry": str(r["id"]), "championship": r["championship_id"], "mode": r["mode"],
                                "player": player_ref(r["player_id"], r["observed_name"]), "received_at": iso(r["received_at"]),
                                "points": r["points"], "team": teams.get(r["id"], [])} for r in recent]}
        return reply(request, data, 120)

    @app.get(f"{PREFIX}/records")
    def records(request: Request, mode: str | None = Query(None, pattern="^(grade|limit|gcup)$")):
        with conn() as c:
            final = """FROM dashboard.standings s JOIN dashboard.championships c
                       ON c.id = s.championship_id AND s.revision = c.final_revision
                       WHERE (%(mode)s::text IS NULL OR c.mode = %(mode)s)"""
            args = {"mode": mode}
            champions = c.execute(f"""SELECT s.championship_id, s.player_id, s.name, s.points, s.frames, c.mode, c.source_edition,
                    c.starts_at, c.cup {final} AND s.rank = 1 ORDER BY c.starts_at DESC, s.position LIMIT 100""", args).fetchall()
            podiums = c.execute(f"""SELECT s.player_id, (array_agg(s.name ORDER BY c.starts_at DESC))[1] AS name,
                    count(*) FILTER (WHERE s.rank = 1)::int AS titles, count(*) FILTER (WHERE s.rank <= 3)::int AS podiums,
                    count(*)::int AS finals {final} GROUP BY s.player_id HAVING count(*) FILTER (WHERE s.rank <= 3) > 0
                    ORDER BY titles DESC, podiums DESC, finals DESC, s.player_id LIMIT 20""", args).fetchall()
            participation = c.execute(f"""SELECT s.player_id, (array_agg(s.name ORDER BY c.starts_at DESC))[1] AS name,
                    count(*)::int AS finals {final} GROUP BY s.player_id ORDER BY finals DESC, s.player_id LIMIT 20""", args).fetchall()
            courses = c.execute("""SELECT DISTINCT ON (c.cup -> 'course', c.cup -> 'event') c.cup -> 'course' AS course,
                    c.cup -> 'event' AS event, s.frames, s.player_id, s.name, s.championship_id, c.source_edition
                    FROM dashboard.standings s JOIN dashboard.championships c ON c.id = s.championship_id
                      AND s.revision = c.final_revision
                    WHERE c.mode = 'gcup' AND s.frames IS NOT NULL
                    ORDER BY c.cup -> 'course', c.cup -> 'event', s.frames, c.starts_at""").fetchall()
            data = {
                "champions": [{"championship": r["championship_id"], "mode": r["mode"], "edition": r["source_edition"],
                               "starts_at": iso(r["starts_at"]), "cup": r["cup"], "player": player_ref(r["player_id"], r["name"]),
                               "points": r["points"], "frames": r["frames"], "time": race_time(r["frames"])} for r in champions],
                "podium_leaders": [{"player": player_ref(r["player_id"], r["name"]), "titles": r["titles"],
                                    "podiums": r["podiums"], "finals": r["finals"]} for r in podiums],
                "participation": [{"player": player_ref(r["player_id"], r["name"]), "finals": r["finals"]} for r in participation],
                "gcup_best_times": [{"course": r["course"], "event": r["event"], "frames": r["frames"], "time": race_time(r["frames"]),
                                     "player": player_ref(r["player_id"], r["name"]), "championship": r["championship_id"],
                                     "edition": r["source_edition"]} for r in courses],
                "basis": "final_standings"}
        return reply(request, data, 300)

    @app.get(f"{PREFIX}/status")
    def status(request: Request):
        now = clock()
        with conn() as c:
            fresh = freshness(c, now)
            finalizing = [r["id"] for r in c.execute(
                "SELECT id FROM dashboard.championships WHERE final_revision IS NULL AND ends_at <= %s ORDER BY ends_at", (now,))]
            current = current_editions(c, now)
            signed = c.execute("SELECT count(*) FILTER (WHERE signature = 'valid')::int AS valid, "
                               "count(*) FILTER (WHERE signature = 'invalid')::int AS invalid FROM dashboard.entries WHERE kind = 'gp'").fetchone()
        degraded = any(f["failing"] or f["lag_seconds"] is None or f["lag_seconds"] > 600 for f in fresh) or not fresh
        data = {"status": "degraded" if degraded else "ok", "now": iso(now), "sources": fresh, "finalizing": finalizing,
                "current": {m: {"id": r["id"], "status": status_of(r, now), "ends_at": iso(r["ends_at"])} if r else None
                            for m, r in current.items()},
                "catalog_version": state["catalog_version"], "gp_signature_checks": signed}
        return reply(request, data, 15)

    return app
