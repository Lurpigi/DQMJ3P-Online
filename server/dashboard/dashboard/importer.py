"""Imports the game databases into the dashboard schema, in bounded batches.

Sources are read, never written: SIL's SQLite file through a read-only connection (one short
transaction per batch), NEX's PostgreSQL tables through the importer role. Each batch commits its
rows together with the checkpoint, and every insert is idempotent (unique source key), so a crash
or a retry can neither lose nor duplicate a result.

Checkpoints keep the source generation (SIL meta 'generation') and a fingerprint of the row at the
cursor. A different generation is a new database: its rows are imported as new ones. A fingerprint
that no longer matches means the same database was restored or rewound: entries whose source row
vanished or changed are marked source_lost (kept, but out of the standings), the cursor restarts,
and final standings that change get a new revision.
"""
import datetime
import hashlib
import json
import logging
import os
import sqlite3
import threading
import time

from psycopg.types.json import Jsonb

from . import db, queries
from .decode import (UTC, GP_MODES, GpCalendarVersion, gcup_bounds, gcup_definition, gcup_team_name, gcup_week,
                     gp_result, gp_rewards, gp_rules, load_sil, public_id, search_key, utf16_name)

log = logging.getLogger("dashboard.importer")
LOCK_KEY = 0x44514D4A  # pg advisory lock: one active importer
MAX_BATCHES = 20       # per cycle and source, so one cycle stays short
GCUP_RESCAN = datetime.timedelta(minutes=5)  # bigserial ids are not commit-ordered


def _hash(*parts):
    h = hashlib.sha256()
    for p in parts:
        h.update(p if isinstance(p, (bytes, bytearray)) else str(p).encode())
        h.update(b"\0")
    return h.hexdigest()[:24]


class Importer:
    def __init__(self, settings, sil=None):
        self.s = settings
        self.sil = sil or load_sil(settings.sil_code)
        self.salt = settings.id_salt or "dev-salt"

    # --- shared helpers -----------------------------------------------------------------
    def checkpoint(self, conn, source):
        row = conn.execute("SELECT * FROM dashboard.import_checkpoints WHERE source = %s", (source,)).fetchone()
        if row is None:
            conn.execute("INSERT INTO dashboard.import_checkpoints (source) VALUES (%s) ON CONFLICT DO NOTHING", (source,))
            row = conn.execute("SELECT * FROM dashboard.import_checkpoints WHERE source = %s", (source,)).fetchone()
        return row

    def fail(self, conn, source, error):
        self.checkpoint(conn, source)
        conn.execute("UPDATE dashboard.import_checkpoints SET last_error = %s, last_error_at = now() WHERE source = %s",
                     (str(error)[:500], source))

    def player(self, conn, namespace, source_id, name, seen, provenance):
        pid = public_id(self.salt, self.s.server_id, namespace, source_id)
        if self.hidden(conn, pid):
            name = ""
        conn.execute(
            """INSERT INTO dashboard.players (id, namespace, display_name, name_search, first_seen, last_seen)
               VALUES (%(id)s, %(ns)s, %(name)s, %(search)s, %(seen)s, %(seen)s)
               ON CONFLICT (id) DO UPDATE SET
                 display_name = CASE WHEN %(name)s <> '' AND (players.last_seen IS NULL OR %(seen)s >= players.last_seen
                                     OR players.display_name = '') THEN %(name)s ELSE players.display_name END,
                 name_search = CASE WHEN %(name)s <> '' AND (players.last_seen IS NULL OR %(seen)s >= players.last_seen
                                     OR players.display_name = '') THEN %(search)s ELSE players.name_search END,
                 first_seen = LEAST(players.first_seen, %(seen)s), last_seen = GREATEST(players.last_seen, %(seen)s)""",
            {"id": pid, "ns": namespace, "name": name, "search": search_key(name), "seen": seen})
        conn.execute("INSERT INTO dashboard.player_sources (namespace, source_id, player_id) VALUES (%s, %s, %s) "
                     "ON CONFLICT DO NOTHING", (namespace, str(source_id), pid))
        if name and seen:
            conn.execute(
                """INSERT INTO dashboard.player_aliases (player_id, name, name_search, provenance, first_seen, last_seen)
                   VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (player_id, name, provenance) DO UPDATE SET
                   first_seen = LEAST(player_aliases.first_seen, excluded.first_seen),
                   last_seen = GREATEST(player_aliases.last_seen, excluded.last_seen)""",
                (pid, name, search_key(name), "observed" if provenance == "observed" else "reconstructed", seen, seen))
        return pid

    def hidden(self, conn, pid):
        row = conn.execute("SELECT hidden FROM dashboard.players WHERE id = %s", (pid,)).fetchone()
        return bool(row and row["hidden"])

    def edition(self, conn, cid, mode, number, version, bounds, offset_minutes, rules, rewards, cup=None,
                provenance=None, now=None):
        now = now or datetime.datetime.now(UTC)
        provenance = provenance or ("observed" if now < bounds[1] else "reconstructed")
        conn.execute(
            """INSERT INTO dashboard.championships (id, server_id, mode, source_edition, calendar_version, starts_at,
                 ends_at, utc_offset_minutes, rules, rewards, cup, definition_provenance)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING""",
            (cid, self.s.server_id, mode, number, version, bounds[0], bounds[1], offset_minutes, Jsonb(rules),
             Jsonb(rewards), Jsonb(cup) if cup is not None else None, provenance))

    def mark_coverage(self, conn, cid, feature, level):
        conn.execute("UPDATE dashboard.championships SET coverage = coverage || %s WHERE id = %s AND "
                     "(coverage ->> %s) IS DISTINCT FROM %s", (Jsonb({feature: level}), cid, feature, level))

    def insert_entry(self, conn, values, rounds=(), team=()):
        row = conn.execute(
            """INSERT INTO dashboard.entries (source_generation, source_ns, source_key, source_hash, championship_id,
                 player_id, kind, received_at, contest_day, points, points_win, points_pop, points_strength, points_eval,
                 rounds, rounds_won, frames, improved, observed_name, observed_location, name_provenance, validation,
                 signature, decoder_version)
               VALUES (%(generation)s, %(ns)s, %(key)s, %(hash)s, %(championship)s, %(player)s, %(kind)s, %(received)s,
                 %(day)s, %(points)s, %(points_win)s, %(points_pop)s, %(points_strength)s, %(points_eval)s, %(rounds)s,
                 %(rounds_won)s, %(frames)s, %(improved)s, %(name)s, %(location)s, %(provenance)s, %(validation)s,
                 %(signature)s, %(decoder)s)
               ON CONFLICT (source_generation, source_ns, source_key) DO NOTHING RETURNING id""",
            {"points": None, "points_win": None, "points_pop": None, "points_strength": None, "points_eval": None,
             "rounds": None, "rounds_won": None, "frames": None, "improved": None, "day": None, "location": None,
             "signature": None, "decoder": None, **values}).fetchone()
        if row is None:
            return None
        if self.hidden(conn, values["player"]):
            conn.execute("UPDATE dashboard.entries SET observed_name = '' WHERE id = %s", (row["id"],))
        for r in rounds:
            if r.get("opponent_player_id") and self.hidden(conn, r["opponent_player_id"]):
                r = {**r, "opponent_name": ""}
            conn.execute("INSERT INTO dashboard.rounds (entry_id, idx, opponent_name, opponent_player_id, won, points_win, "
                         "points_pop, points_strength, points_eval) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                         (row["id"], r["idx"], r["opponent_name"], r.get("opponent_player_id"), r["won"], r["points_win"],
                          r["points_pop"], r["points_strength"], r["points_eval"]))
        for m in team:
            conn.execute("INSERT INTO dashboard.team_members (entry_id, slot, species, level, hp, mp, atk, def, agi, wis) "
                         "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                         (row["id"], m["slot"], m["species"], m["level"], m["hp"], m["mp"], m["atk"], m["def"],
                          m["agi"], m["wis"]))
        return row["id"]

    def reconcile(self, conn, ns, generation, source_hashes):
        """Marks entries whose source row vanished or changed (restored source) as source_lost and
        frees their keys. Returns the championships affected."""
        rows = conn.execute("SELECT id, source_key, source_hash, championship_id FROM dashboard.entries "
                            "WHERE source_ns = %s AND source_generation = %s AND validation <> 'source_lost'",
                            (ns, generation)).fetchall()
        current = source_hashes([r["source_key"] for r in rows])
        affected = set()
        for r in rows:
            if current.get(r["source_key"]) != r["source_hash"]:
                conn.execute("UPDATE dashboard.entries SET validation = 'source_lost', source_key = source_key || '#lost-' || id "
                             "WHERE id = %s", (r["id"],))
                affected.add(r["championship_id"])
        log.warning("%s: source rewound, %d entries no longer in the source", ns, sum(1 for r in rows if current.get(r["source_key"]) != r["source_hash"]))
        return affected

    def revise(self, conn, championship, reason):
        """New revision of a final edition when its recomputed standings differ."""
        champ = conn.execute("SELECT * FROM dashboard.championships WHERE id = %s", (championship,)).fetchone()
        if not champ or champ["final_revision"] is None or champ["mode"] == "gcup":
            return None
        rows = queries.gp_standings(conn, championship)
        old = conn.execute("SELECT * FROM dashboard.standings WHERE championship_id = %s AND revision = %s ORDER BY position",
                           (championship, champ["final_revision"])).fetchall()
        if queries.same_standings(rows, old):
            return None
        return queries.write_revision(conn, championship, rows, reason, {"previous": champ["final_revision"]})

    # --- Grand Prix (SIL) -----------------------------------------------------------------
    def _sil_open(self):
        if not os.path.isfile(self.s.sil_db):
            raise FileNotFoundError("SIL database not found")
        src = sqlite3.connect(f"file:{self.s.sil_db}?mode=ro", uri=True, timeout=10, isolation_level=None)
        src.row_factory = sqlite3.Row
        return src

    def gp_calendars(self, src):
        tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if "gp_calendars" not in tables:
            return [], None
        cals = []
        for r in src.execute("SELECT id, start, days, utc_offset, config, first_used FROM gp_calendars ORDER BY id"):
            row = dict(r)
            row["config"] = json.loads(row["config"]) if row["config"] else {}
            cals.append(GpCalendarVersion(self.sil, row))
        generation = src.execute("SELECT value FROM meta WHERE key = 'generation'").fetchone()
        return cals, generation[0] if generation else None

    def ensure_gp_editions(self, conn, cals, now):
        for i, cal in enumerate(cals):
            until = cals[i + 1].first_used if i + 1 < len(cals) else now
            first = 1 if i == 0 else cal.contest(cal.day_of(cal.first_used))
            last = cal.contest(cal.day_of(min(until, now)))
            for n in range(first, last + 1):
                for mode in GP_MODES:
                    self.edition(conn, cal.edition_id(mode, n), mode, n, cal.version, cal.bounds(n),
                                 round(cal.offset_hours * 60), gp_rules(self.sil, mode, n, cal.config),
                                 gp_rewards(cal.config), now=now)

    def sync_gp(self, conn, now=None):
        now = now or datetime.datetime.now(UTC)
        ns, source = "sil-gp", "sil-gp"
        for _ in range(MAX_BATCHES):
            src = self._sil_open()
            try:
                src.execute("BEGIN")  # one read snapshot for the batch
                cals, generation = self.gp_calendars(src)
                if not cals:
                    raise RuntimeError("SIL has no gp_calendars yet (server not upgraded or never started)")
                with conn.transaction():
                    cp = self.checkpoint(conn, source)
                    cursor = cp["cursor"] if cp["generation"] == generation else 0
                    if cursor and cp["fingerprint"] != self._sil_fingerprint(src, cursor):
                        affected = self.reconcile(conn, ns, generation, lambda keys: self._sil_hashes(src, keys))
                        for cid in affected:
                            self.revise(conn, cid, "source_reconciled")
                        cursor = 0
                    rows = src.execute(
                        """SELECT g.id, g.friend_code, g.mode, g.data, g.uploaded, g.day, s.calendar, s.contest,
                                  s.name AS snap_name, s.location AS snap_location, s.decoder, s.result_id AS snap,
                                  u.data AS user_data
                           FROM gp_results g LEFT JOIN gp_snapshots s ON s.result_id = g.id
                           LEFT JOIN private_files u ON u.friend_code = g.friend_code AND u.name = '00_UserData.bin'
                           WHERE g.id > ? ORDER BY g.id LIMIT ?""", (cursor, self.s.batch_size)).fetchall()
                    codes = {r for row in rows for r in self._opponent_codes(row)}
                    known = {c for c in codes if src.execute("SELECT 1 FROM gp_results WHERE friend_code = ? LIMIT 1", (c,)).fetchone()}
                    self.ensure_gp_editions(conn, cals, now)
                    by_id = {c.id: c for c in cals}
                    for row in rows:
                        self._import_gp_row(conn, row, generation, ns, by_id, cals[0], known, now)
                    done = len(rows) < self.s.batch_size
                    last = rows[-1]["id"] if rows else cursor
                    conn.execute(
                        """UPDATE dashboard.import_checkpoints SET generation = %s, cursor = %s, fingerprint = %s,
                           source_as_of = CASE WHEN %s THEN %s ELSE source_as_of END, last_success = now(),
                           rows_total = rows_total + %s WHERE source = %s""",
                        (generation, last, self._sil_fingerprint(src, last) if last else None, done, now, len(rows), source))
            finally:
                src.execute("COMMIT") if src.in_transaction else None
                src.close()
            if done:
                return

    @staticmethod
    def _row_hash(friend_code, mode, day, data):
        return _hash(friend_code, mode, day, data)

    def _sil_fingerprint(self, src, rid):
        row = src.execute("SELECT friend_code, mode, day, data FROM gp_results WHERE id = ?", (rid,)).fetchone()
        return self._row_hash(*row) if row else None

    def _sil_hashes(self, src, keys):
        out = {}
        for key in keys:
            row = src.execute("SELECT friend_code, mode, day, data FROM gp_results WHERE id = ?", (int(key),)).fetchone()
            if row:
                out[key] = self._row_hash(*row)
        return out

    @staticmethod
    def _opponent_codes(row):
        data = row["data"] or b""
        for i in range(3):
            header = data[0x14 + i * 0x78 + 0x24:0x14 + i * 0x78 + 0x30]
            if len(header) == 12 and header.isdigit():
                yield header.decode()

    def _import_gp_row(self, conn, row, generation, ns, cals_by_id, first_cal, known_codes, now):
        received = datetime.datetime.fromtimestamp(row["uploaded"], UTC)
        day = datetime.date.fromisoformat(row["day"]) if row["day"] else first_cal.day_of(received)
        if row["snap"] is not None and row["calendar"] in cals_by_id:
            cal, n = cals_by_id[row["calendar"]], row["contest"]
            name, location, provenance = utf16_name(row["snap_name"] or b""), row["snap_location"], "observed"
            if row["snap_name"] is None:
                provenance = "unknown"
        else:  # stored before snapshots existed: calendar 1, name from the current registration
            cal, n = first_cal, first_cal.contest(day)
            user = row["user_data"] or b""
            name = utf16_name(user[0xC:0x30]) if len(user) >= 0x30 else ""
            location = int.from_bytes(user[4:6], "little") if len(user) >= 6 else None
            provenance = "reconstructed" if name else "unknown"
        cid = cal.edition_id(row["mode"], n)
        if row["mode"] not in GP_MODES:
            return
        self.edition(conn, cid, row["mode"], n, cal.version, cal.bounds(n), round(cal.offset_hours * 60),
                     gp_rules(self.sil, row["mode"], n, cal.config), gp_rewards(cal.config), now=now)
        if provenance != "observed":
            self.mark_coverage(conn, cid, "names", "reconstructed")
        player = self.player(conn, "sil", row["friend_code"], name, received, provenance)
        decoded = gp_result(self.sil, row["data"] or b"")
        values = {"generation": generation, "ns": ns, "key": str(row["id"]),
                  "hash": self._row_hash(row["friend_code"], row["mode"], row["day"], row["data"]),
                  "championship": cid, "player": player, "kind": "gp", "received": received, "day": day,
                  "name": name, "location": location, "provenance": provenance, "decoder": row["decoder"]}
        if decoded is None:
            self.insert_entry(conn, {**values, "validation": "malformed"})
            return
        t = decoded["totals"]
        rounds = []
        for r in decoded["rounds"]:
            code = r.pop("opponent_code")
            if code in known_codes:
                r["opponent_player_id"] = self.player(conn, "sil", code, "", None, "unknown")
            rounds.append(r)
        self.insert_entry(conn, {**values, "points": t["total"], "points_win": t["win"], "points_pop": t["pop"],
                                 "points_strength": t["strength"], "points_eval": t["eval"], "rounds": t["battles"],
                                 "rounds_won": t["wins"], "validation": "unverified", "signature": decoded["signature"]},
                          rounds, decoded["team"])

    # --- G-Cup (NEX) ----------------------------------------------------------------------
    def _exists(self, conn, name):
        return conn.execute("SELECT to_regclass(%s) AS t", (name,)).fetchone()["t"] is not None

    def sync_gcup(self, conn, now=None):
        now = now or datetime.datetime.now(UTC)
        if not self._exists(conn, "ranking.scores") or not self._exists(conn, "matchmaking.persistent_gatherings"):
            raise RuntimeError("NEX tables not found")
        history = self._exists(conn, "history.gcup_editions")
        with conn.transaction():
            cups = {r["idx"]: r for r in conn.execute(
                "SELECT id, attribs[2] AS idx, application_buffer FROM matchmaking.persistent_gatherings "
                "WHERE community_type = 2 AND attribs[1] = 0")}
            recorded = {r["week"]: r for r in conn.execute("SELECT * FROM history.gcup_editions")} if history else {}
            processed = {r["week"] for r in conn.execute("SELECT week FROM ranking.gcup_weeks")} \
                if self._exists(conn, "ranking.gcup_weeks") else set()
            current = gcup_week(now)
            known = list(recorded) + [w - 1 for w in processed]
            first = min(known + [current])
            for week in range(first, current + 1):
                rec = recorded.get(week)
                cup = cups.get(week % 12)
                category = rec["category"] if rec else (cup["id"] if cup else None)
                if category is None:
                    continue
                definition = gcup_definition(bytes(rec["definition"]) if rec else bytes(cup["application_buffer"] or b""))
                info = {"number": week % 12 + 1, "category": str(category), **{k: v for k, v in definition.items() if k != "prizes"}}
                rules = {"kind": "gcup", "allowed_species": definition.get("allowed_species", [])}
                self.edition(conn, f"gcup-w{week}", "gcup", week, "gcup", gcup_bounds(week), 0, rules,
                             {"prizes": definition.get("prizes", [])}, info, "observed" if rec else "reconstructed", now)
                if rec is None:
                    self.mark_coverage(conn, f"gcup-w{week}", "attempts", "unavailable")
        if history:
            self._gcup_submissions(conn, now)
        self._gcup_live(conn, now, processed)
        self._gcup_finals(conn, processed, history)

    def _gcup_submissions(self, conn, now):
        source = ns = "nex-gcup"
        for _ in range(MAX_BATCHES):
            with conn.transaction():
                cp = self.checkpoint(conn, source)
                cursor = cp["cursor"] or 0
                if cursor and cp["fingerprint"] != self._nex_fingerprint(conn, cursor):
                    self.reconcile(conn, ns, "nex", lambda keys: self._nex_hashes(conn, keys))
                    cursor = 0
                select = """SELECT s.*, s.unique_id::text AS uid,
                      (SELECT c.data FROM history.gcup_common_data c WHERE c.pid = s.pid AND c.unique_id = s.unique_id
                         AND c.received <= s.received ORDER BY c.id DESC LIMIT 1) AS observed_data,
                      (SELECT r.data FROM ranking.common_data r WHERE r.pid = s.pid AND r.unique_id = s.unique_id) AS current_data
                    FROM history.gcup_submissions s"""
                rows = conn.execute(select + " WHERE s.id > %s ORDER BY s.id LIMIT %s", (cursor, self.s.batch_size)).fetchall()
                since = (cp["source_as_of"] or now) - GCUP_RESCAN
                late = conn.execute(select + " WHERE s.id <= %s AND s.received >= %s ORDER BY s.id LIMIT %s",
                                    (cursor, since, self.s.batch_size)).fetchall() if cursor else []
                editions = {r["id"]: r for r in conn.execute(
                    "SELECT id, cup ->> 'category' AS category FROM dashboard.championships WHERE mode = 'gcup'")}
                for row in late + rows:
                    cid = f"gcup-w{row['week']}"
                    if cid not in editions:
                        continue
                    if row["observed_data"] is not None:
                        name, provenance = gcup_team_name(bytes(row["observed_data"])), "observed"
                    elif row["current_data"] is not None:
                        name, provenance = gcup_team_name(bytes(row["current_data"])), "reconstructed"
                    else:
                        name, provenance = "", "unknown"
                    player = self.player(conn, "nex", row["pid"], name, row["received"], provenance)
                    other = editions[cid]["category"] != str(row["category"])
                    self.insert_entry(conn, {
                        "generation": "nex", "ns": ns, "key": str(row["id"]), "hash": self._nex_row_hash(row),
                        "championship": cid, "player": player, "kind": "gcup", "received": row["received"],
                        "frames": row["score"], "improved": row["changed_best"], "name": name,
                        "provenance": provenance, "validation": "other_cup" if other else "unverified"})
                done = len(rows) < self.s.batch_size
                last = rows[-1]["id"] if rows else cursor
                conn.execute(
                    """UPDATE dashboard.import_checkpoints SET generation = 'nex', cursor = %s, fingerprint = %s,
                       source_as_of = CASE WHEN %s THEN %s ELSE source_as_of END, last_success = now(),
                       rows_total = rows_total + %s WHERE source = %s""",
                    (last, self._nex_fingerprint(conn, last) if last else None, done, now, len(rows), source))
            if done:
                return

    @staticmethod
    def _nex_row_hash(row):
        return _hash(row["pid"], row["category"], row["uid"] if "uid" in row else row["unique_id"], row["score"],
                     row["received"].isoformat())

    def _nex_fingerprint(self, conn, sid):
        row = conn.execute("SELECT pid, category, unique_id::text AS uid, score, received FROM history.gcup_submissions "
                           "WHERE id = %s", (sid,)).fetchone()
        return self._nex_row_hash(row) if row else None

    def _nex_hashes(self, conn, keys):
        rows = conn.execute("SELECT id, pid, category, unique_id::text AS uid, score, received FROM history.gcup_submissions "
                            "WHERE id = ANY(%s)", ([int(k) for k in keys],)).fetchall()
        return {str(r["id"]): self._nex_row_hash(r) for r in rows}

    def _gcup_live(self, conn, now, processed):
        """Leaderboard of the editions whose week the NEX server has not closed yet."""
        current = gcup_week(now)
        with conn.transaction():
            for week in (current - 1, current):
                cid = f"gcup-w{week}"
                champ = conn.execute("SELECT cup ->> 'category' AS category, starts_at, ends_at, final_revision "
                                     "FROM dashboard.championships WHERE id = %s", (cid,)).fetchone()
                if not champ or champ["final_revision"] is not None or (week + 1) in processed:
                    continue
                naive = lambda t: t.astimezone(UTC).replace(tzinfo=None)  # ranking.scores.update_time is UTC
                rows = conn.execute(
                    """SELECT s.pid, s.unique_id::text AS uid, s.score, s.update_time, c.data FROM ranking.scores s
                       LEFT JOIN ranking.common_data c ON c.pid = s.pid AND c.unique_id = s.unique_id
                       WHERE s.category = %s AND s.update_time >= %s AND s.update_time < %s""",
                    (int(champ["category"]), naive(champ["starts_at"]), naive(champ["ends_at"]))).fetchall()
                conn.execute("DELETE FROM dashboard.gcup_best WHERE championship_id = %s", (cid,))
                for r in rows:
                    name = gcup_team_name(bytes(r["data"])) if r["data"] is not None else ""
                    updated = r["update_time"].replace(tzinfo=UTC)
                    player = self.player(conn, "nex", r["pid"], name, updated, "reconstructed")
                    conn.execute("INSERT INTO dashboard.gcup_best (championship_id, player_id, unique_id, frames, updated_at, "
                                 "team_name) VALUES (%s, %s, %s, %s, %s, %s)", (cid, player, r["uid"], r["score"], updated, name))

    def _gcup_finals(self, conn, processed, history):
        pending = conn.execute("SELECT id, source_edition FROM dashboard.championships WHERE mode = 'gcup' "
                               "AND final_revision IS NULL").fetchall()
        for champ in pending:
            week = champ["source_edition"]
            if week + 1 not in processed:
                continue  # NEX has not closed the week yet
            with conn.transaction():
                rows, source = [], "ranking.gcup_results"
                closed = history and conn.execute("SELECT 1 FROM history.gcup_editions WHERE week = %s AND closed_at IS NOT NULL",
                                                  (week,)).fetchone()
                if closed:
                    source = "history.gcup_finals"
                    finals = conn.execute("SELECT position, rank, pid, score, name, update_time FROM history.gcup_finals "
                                          "WHERE week = %s ORDER BY position", (week,)).fetchall()
                else:
                    finals = conn.execute("SELECT rank AS position, rank, pid, score, name, NULL::timestamp AS update_time "
                                          "FROM ranking.gcup_results WHERE week = %s ORDER BY rank", (week,)).fetchall()
                    self.mark_coverage(conn, champ["id"], "finals", "reconstructed")
                for f in finals:
                    seen = f["update_time"].replace(tzinfo=UTC) if f["update_time"] else None
                    player = self.player(conn, "nex", f["pid"], f["name"] if f["name"] != "?" else "", seen,
                                         "observed" if closed else "reconstructed")
                    rows.append({"position": f["position"], "rank": f["rank"], "player_id": player,
                                 "name": f["name"] if f["name"] != "?" else "", "frames": f["score"]})
                conn.execute("DELETE FROM dashboard.gcup_best WHERE championship_id = %s", (champ["id"],))
                queries.write_revision(conn, champ["id"], rows, "closing", {"source": source}, mode="gcup")

    # --- finalization -----------------------------------------------------------------------
    def finalize_gp(self, conn, now=None):
        now = now or datetime.datetime.now(UTC)
        cp = conn.execute("SELECT source_as_of FROM dashboard.import_checkpoints WHERE source = 'sil-gp'").fetchone()
        if not cp or not cp["source_as_of"]:
            return
        pending = conn.execute("SELECT id FROM dashboard.championships WHERE mode IN ('grade', 'limit') AND final_revision IS NULL "
                               "AND ends_at <= %s ORDER BY ends_at", (cp["source_as_of"],)).fetchall()
        for champ in pending:
            with conn.transaction():
                rows = queries.gp_standings(conn, champ["id"])
                queries.write_revision(conn, champ["id"], rows, "closing", {"source_as_of": cp["source_as_of"].isoformat()})

    # --- loop -----------------------------------------------------------------------------
    def run_once(self, conn, now=None):
        for name, step in (("sil-gp", self.sync_gp), ("nex-gcup", self.sync_gcup)):
            try:
                step(conn, now)
            except Exception as e:  # noqa: BLE001 - one failing source must not stop the other
                log.warning("%s import failed: %s", name, e)
                conn.rollback() if not conn.autocommit else None
                self.fail(conn, name, e)
        self.finalize_gp(conn, now)

    def run_forever(self, stop: threading.Event):
        while not stop.is_set():
            try:
                with db.connect(self.s.db_url, autocommit=True) as conn:
                    if not conn.execute("SELECT pg_try_advisory_lock(%s) AS ok", (LOCK_KEY,)).fetchone()["ok"]:
                        log.info("another importer holds the lock")
                        stop.wait(self.s.import_interval * 4)
                        continue
                    while not stop.is_set():
                        started = time.monotonic()
                        self.run_once(conn)
                        stop.wait(max(1.0, self.s.import_interval - (time.monotonic() - started)))
            except Exception as e:  # noqa: BLE001 - database restarts: retry
                log.warning("importer: %s", e)
                stop.wait(self.s.import_interval)
