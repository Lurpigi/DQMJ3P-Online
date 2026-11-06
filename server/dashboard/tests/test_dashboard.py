"""Portal tests on real databases: a SQLite file written by the real SIL Store (sil_server.py) and a
PostgreSQL database (DASHBOARD_TEST_DB, emptied by the tests), e.g.
    DASHBOARD_TEST_DB=postgresql://dqmj3p:dqmj3p@127.0.0.1:54329/dashboard_test python -m pytest -q tests
Synthetic data only."""
import datetime
import json
import os
import re
import struct
import types

import psycopg
import pytest
from fastapi.testclient import TestClient

from dashboard import db, decode
from dashboard.api import create_app
from dashboard.config import Settings
from dashboard.importer import Importer

HERE = os.path.dirname(os.path.abspath(__file__))
SIL_CODE = os.path.join(HERE, "..", "..", "sil", "sil_server.py")
DSN = os.environ.get("DASHBOARD_TEST_DB")
UTC = datetime.timezone.utc
pytestmark = pytest.mark.skipif(not DSN, reason="DASHBOARD_TEST_DB not set")
sil = decode.load_sil(SIL_CODE)

START = datetime.date(2026, 1, 5)      # contest 1: Jan 5-11, contest 2: Jan 12-18 (UTC+1)
DURING = datetime.datetime(2026, 1, 14, 12, tzinfo=UTC)
AFTER = datetime.datetime(2026, 1, 19, 12, tzinfo=UTC)
CODES = {"A": "111111111111", "B": "222222222222", "C": "333333333333", "X": "444444444444"}


def result_pack(points, wins, species=(1, 25, 0, 0), opponent=None):
    pack = bytearray(0x540)
    pack[0] = 3
    struct.pack_into("<4H2xI", pack, 2, 0, 0, 0, points, points)
    for i in range(3):
        s = 0x14 + i * 0x78
        pack[s:s + 10] = "Rival".encode("utf-16-le")
        if opponent:
            pack[s + 0x24:s + 0x30] = opponent.encode()
        pack[s + 0x40] = 1 if i < wins else 0
        struct.pack_into("<I", pack, s + 0x44, points // 3)
    for slot, sp in enumerate(species):
        m = 0x17C + slot * 0xF0
        struct.pack_into("<h8h", pack, m + 0x1C, sp, *[100] * 8)
        pack[m + 0x3C] = 40
    return bytes(pack)


def user_data(name, location=76):
    b = bytearray(0xC4)
    struct.pack_into("<I", b, 4, location)
    b[0xC:0xC + 2 * len(name)] = name.encode("utf-16-le")
    return bytes(b)


@pytest.fixture
def env(tmp_path):
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute("DROP SCHEMA IF EXISTS dashboard, ranking, history, matchmaking CASCADE")
        c.execute(open(os.path.join(HERE, "nex_schema.sql")).read())
        buf = bytearray(0x1B0)
        buf[0x6E:0x6E + 12] = "Cup 6".encode("utf-16-le")
        buf[0x92], buf[0x93] = 2, 1
        buf[0x96:0x9A] = bytes([0, 3, 0, 0])
        for idx in range(12):
            c.execute("INSERT INTO matchmaking.persistent_gatherings VALUES (%s, 2, %s, %s, 'secret')",
                      (idx + 1, [0, idx, 0, 0, 0, 0], bytes(buf)))
    db.migrate(DSN, log=lambda *_: None)
    store = sil.Store(str(tmp_path / "sil.sqlite3"))
    calendar = sil.GpCalendar(START, 7, 1)
    cal_id = store.use_calendar(calendar, {"prize_champion": 70, "prize_top10": 66, "coins_champion": (0, 0, 3, 0),
                                           "coins_top10": None, "limit_rotation": True})
    settings = Settings(db_url=DSN, api_db_url=DSN, sil_db=str(tmp_path / "sil.sqlite3"), sil_code=SIL_CODE,
                        server_id="test", id_salt="test-salt-0123456789", allowed_origins=["https://example.github.io"])
    ns = types.SimpleNamespace(store=store, calendar=calendar, cal_id=cal_id, settings=settings,
                               importer=Importer(settings, sil))

    def register(who, name, location=76):
        store.q("INSERT INTO private_files (friend_code, name, data) VALUES (?, '00_UserData.bin', ?) "
                "ON CONFLICT(friend_code, name) DO UPDATE SET data = excluded.data", CODES[who], user_data(name, location))

    def upload(who, day, points, wins=1, mode="grade", **kw):
        d = datetime.date.fromisoformat(day)
        return store.add_gp_result(CODES[who], mode, result_pack(points, wins, **kw), d.isoformat(), cal_id,
                                   calendar.contest(d)[0])

    def run(now):
        with psycopg.connect(DSN, autocommit=True, row_factory=psycopg.rows.dict_row) as c:
            ns.importer.run_once(c, now)

    def client(now):
        return TestClient(create_app(settings, start_importer=False, now=lambda: now))

    def pid(who, namespace="sil"):
        return decode.public_id(settings.id_salt, settings.server_id, namespace, CODES.get(who, who))

    def sql(query, *args):
        with psycopg.connect(DSN, autocommit=True, row_factory=psycopg.rows.dict_row) as c:
            return c.execute(query, args).fetchall()

    ns.register, ns.upload, ns.run, ns.client, ns.pid, ns.sql = register, upload, run, client, pid, sql
    return ns


def seed_contest2(env):
    env.register("A", "Alice")
    env.register("B", "Bob", 0)
    env.register("C", "Chiara")
    env.upload("A", "2026-01-12", 300, 1)
    env.upload("B", "2026-01-12", 500, 2, opponent=CODES["A"])
    env.upload("A", "2026-01-13", 200, 3)        # A: 500 = B: 500 (tie)
    env.upload("C", "2026-01-13", 100, 0)
    env.upload("C", "2026-01-14", 900, 3)        # today: provisional only


def sil_standings(env, first, end):
    return env.store and sil.Handler._standings(types.SimpleNamespace(store=env.store), "grade", first, end)


def test_gp_standings_match_the_game(env):
    seed_contest2(env)
    env.run(DURING)
    with env.client(DURING) as c:
        cid = f"gp-grade-cal{env.cal_id}-n2"
        published = c.get(f"/api/v1/championships/{cid}/standings").json()
        assert published["view"] == "published" and published["cutoff_day"] == "2026-01-14"
        game = sil_standings(env, datetime.date(2026, 1, 12), datetime.date(2026, 1, 14))
        ours = {r["player"]["id"]: (r["rank"], r["points"]["total"], r["rounds_won"]) for r in published["rows"]}
        assert ours == {env.pid(next(k for k, v in CODES.items() if v == p["friend_code"])): (p["rank"], p["total"], p["wins"])
                        for p in game}
        assert [r["rank"] for r in published["rows"]] == [1, 1, 3]  # tie shares the rank, positions stay 1..3
        provisional = c.get(f"/api/v1/championships/{cid}/standings", params={"view": "provisional"}).json()
        assert provisional["rows"][0]["player"]["name"] == "Chiara" and provisional["rows"][0]["points"]["total"] == 1000
        assert published["rows"][0]["team"][0]["species"] == 1
        # every contest of both modes exists, with or without players
        ids = {r["id"] for r in env.sql("SELECT id FROM dashboard.championships WHERE mode <> 'gcup'")}
        assert ids == {f"gp-{m}-cal{env.cal_id}-n{n}" for m in ("grade", "limit") for n in (1, 2)}
        limit = c.get(f"/api/v1/championships/gp-limit-cal{env.cal_id}-n2").json()
        assert limit["rules"]["rules"] == [{"type": 1, "value": 1}] and limit["rules"]["text"]["it"].startswith("Solo mostri")
        assert limit["entrants"] == 0 and limit["status"] == "open"


def test_import_is_idempotent(env):
    seed_contest2(env)
    env.run(DURING)
    count = env.sql("SELECT count(*) AS n FROM dashboard.entries")[0]["n"]
    env.run(DURING)
    env.sql("UPDATE dashboard.import_checkpoints SET cursor = 0, fingerprint = NULL WHERE source = 'sil-gp' RETURNING 1")
    env.run(DURING)
    assert env.sql("SELECT count(*) AS n FROM dashboard.entries")[0]["n"] == count == 5
    assert env.sql("SELECT count(*) AS n FROM dashboard.rounds")[0]["n"] == 15


def test_finalization_keeps_history(env):
    seed_contest2(env)
    env.run(DURING)
    env.register("A", "Alicia")                  # rename after the contest
    env.upload("A", "2026-01-19", 50, 0, species=(36, 0, 0, 0))
    env.run(AFTER)
    cid = f"gp-grade-cal{env.cal_id}-n2"
    champ = env.sql("SELECT final_revision FROM dashboard.championships WHERE id = %s", cid)[0]
    assert champ["final_revision"] == 1
    final = env.sql("SELECT name, rank, points FROM dashboard.standings WHERE championship_id = %s ORDER BY position", cid)
    assert final[0] == {"name": "Chiara", "rank": 1, "points": 1000}
    assert {r["name"] for r in final} == {"Chiara", "Alice", "Bob"}  # observed names, not the new one
    game = sil_standings(env, datetime.date(2026, 1, 12), datetime.date(2026, 1, 19))
    assert [p["total"] for p in game] == [r["points"] for r in final]
    with env.client(AFTER) as c:
        player = c.get(f"/api/v1/players/{env.pid('A')}").json()
        assert player["name"] == "Alicia" and {a["name"] for a in player["aliases"]} >= {"Alice", "Alicia"}
        teams = c.get(f"/api/v1/players/{env.pid('A')}/teams").json()["items"]
        assert [t["team"][0]["species"] for t in teams] == [36, 1]  # each edition keeps its own team
        assert c.get(f"/api/v1/championships/{cid}").json()["status"] == "final"
        assert c.get(f"/api/v1/championships/{cid}/standings").json()["view"] == "final"


def test_legacy_rows_are_reconstructed(env):
    env.register("X", "Old")
    env.store.q("INSERT INTO gp_results (friend_code, mode, score, data, day) VALUES (?, 'grade', 10, ?, '2026-01-07')",
                CODES["X"], result_pack(10, 1))
    env.store.q("INSERT INTO gp_results (friend_code, mode, score, data, day) VALUES (?, 'grade', 10, ?, '2026-01-07')",
                CODES["X"], b"short")
    env.run(DURING)
    rows = env.sql("SELECT championship_id, name_provenance, observed_name, validation FROM dashboard.entries ORDER BY id")
    assert [(r["name_provenance"], r["observed_name"], r["validation"]) for r in rows] == [
        ("reconstructed", "Old", "unverified"), ("reconstructed", "Old", "malformed")]
    assert rows[0]["championship_id"] == f"gp-grade-cal{env.cal_id}-n1"
    assert env.sql("SELECT coverage FROM dashboard.championships WHERE id = %s", rows[0]["championship_id"])[0]["coverage"] == {
        "names": "reconstructed"}


def test_restored_source_is_reconciled(env):
    seed_contest2(env)
    env.run(AFTER)
    last = env.store.q("SELECT max(id) FROM gp_results")[0][0]
    env.store.q("DELETE FROM gp_snapshots WHERE result_id = ?", last)
    env.store.q("DELETE FROM gp_results WHERE id = ?", last)   # a restore lost the last upload...
    env.upload("B", "2026-01-14", 5, 0)                       # ...and its id is reused by another one
    assert env.store.q("SELECT max(id) FROM gp_results")[0][0] == last
    env.run(AFTER)
    lost = env.sql("SELECT validation, observed_name FROM dashboard.entries WHERE validation = 'source_lost'")
    assert lost == [{"validation": "source_lost", "observed_name": "Chiara"}]
    cid = f"gp-grade-cal{env.cal_id}-n2"
    revs = env.sql("SELECT revision, reason FROM dashboard.revisions WHERE championship_id = %s ORDER BY revision", cid)
    assert [r["reason"] for r in revs] == ["closing", "source_reconciled"]
    rev1 = env.sql("SELECT points FROM dashboard.standings WHERE championship_id = %s AND revision = 1 ORDER BY position", cid)
    assert rev1[0]["points"] == 1000  # revision 1 is never rewritten


def test_gcup_history(env):
    week = decode.gcup_week(DURING)
    start = decode.gcup_bounds(week - 1)[0]
    cat = (week - 1) % 12 + 1
    team = lambda n: n.encode("utf-16-le")
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute("INSERT INTO history.gcup_editions (week, cup_index, category, starts_at, ends_at, definition, closed_at, entrants) "
                  "VALUES (%s, %s, %s, %s, %s, %s, now(), 2)", (week - 1, (week - 1) % 12, cat, start, start + datetime.timedelta(weeks=1),
                                                                 bytes(0x1B0)))
        c.execute("INSERT INTO history.gcup_editions (week, cup_index, category, starts_at, ends_at, definition) VALUES (%s, %s, %s, %s, %s, %s)",
                  (week, week % 12, week % 12 + 1, start + datetime.timedelta(weeks=1), start + datetime.timedelta(weeks=2), bytes(0x1B0)))
        c.execute("INSERT INTO ranking.gcup_weeks (week) VALUES (%s), (%s)", (week - 1, week))
        for pos, (pid_, score, name) in enumerate([(201, 3733, "Fast"), (202, 4000, "Slow")], 1):
            c.execute("INSERT INTO history.gcup_finals VALUES (%s, %s, %s, %s, 0, %s, %s, %s, %s)",
                      (week - 1, pos, pos, pid_, score, (start + datetime.timedelta(days=1)).replace(tzinfo=None), name, team(name)))
        t = start + datetime.timedelta(days=1)
        c.execute("INSERT INTO history.gcup_common_data (pid, unique_id, data, received, week) VALUES (201, 0, %s, %s, %s)",
                  (team("Fast"), t, week - 1))
        for score, best in ((3900, True), (4100, False), (3733, True)):
            c.execute("INSERT INTO history.gcup_submissions (pid, category, unique_id, score, order_by, update_mode, groups, param, "
                      "received, week, changed_best) VALUES (201, %s, 0, %s, 0, 0, '', 0, %s, %s, %s)", (cat, score, t, week - 1, best))
        now_naive = DURING.replace(tzinfo=None)
        c.execute("INSERT INTO ranking.scores VALUES (203, %s, 0, 5000, 0, '', 0, %s)", (week % 12 + 1, now_naive))
        c.execute("INSERT INTO ranking.common_data VALUES (203, 0, %s)", (team("Live"),))
    env.run(DURING)
    with env.client(DURING) as c:
        final = c.get(f"/api/v1/championships/gcup-w{week - 1}/standings").json()
        assert final["view"] == "final" and [(r["player"]["name"], r["time"]) for r in final["rows"]] == [
            ("Fast", "2'04\"43"), ("Slow", "2'13\"33")]
        live = c.get(f"/api/v1/championships/gcup-w{week}/standings").json()
        assert live["view"] == "live" and live["rows"][0]["player"]["name"] == "Live"
        attempts = c.get(f"/api/v1/players/{env.pid('201', 'nex')}/results").json()["items"]
        assert [(a["frames"], a["improved"]) for a in attempts] == [(3900, True), (4100, False), (3733, True)][::-1] or \
            sorted(a["frames"] for a in attempts) == [3733, 3900, 4100]
        records = c.get("/api/v1/records").json()
        assert records["gcup_best_times"][0]["time"] == "2'04\"43"
        overview = c.get("/api/v1/overview").json()
        assert {p["mode"] for p in overview["panels"]} == {"grade", "limit", "gcup"}


def test_public_contract(env):
    env.register("A", "=HYPERLINK(\"x\")")
    env.register("B", "Bob")
    env.upload("A", "2026-01-12", 300, 1)
    env.upload("B", "2026-01-13", 200, 1, opponent=CODES["A"])
    env.run(DURING)
    cid = f"gp-grade-cal{env.cal_id}-n2"
    with env.client(DURING) as c:
        bodies = []
        for path in ["/api/v1/meta", "/api/v1/overview", "/api/v1/championships", f"/api/v1/championships/{cid}",
                     f"/api/v1/championships/{cid}/standings", f"/api/v1/championships/{cid}/results",
                     f"/api/v1/championships/{cid}/stats", "/api/v1/players?q=bo", f"/api/v1/players/{env.pid('B')}",
                     f"/api/v1/players/{env.pid('B')}/championships", f"/api/v1/players/{env.pid('B')}/results",
                     "/api/v1/battles", "/api/v1/monsters/1/stats",
                     "/api/v1/records", "/api/v1/status"]:
            r = c.get(path)
            assert r.status_code == 200, (path, r.text)
            bodies.append(r.text)
        battles = json.loads(bodies[11])
        assert any(b["opponent"]["player"] and b["opponent"]["player"]["id"] == env.pid("A") for b in battles["items"])
        everything = "\n".join(bodies)
        for code in CODES.values():
            assert code not in everything  # friend codes never leave the database
        assert "secret" not in everything
        csv_text = c.get(f"/api/v1/championships/{cid}/standings", params={"view": "provisional", "format": "csv"}).text
        assert "'=HYPERLINK" in csv_text and "\n=HYPERLINK" not in csv_text.replace(",", "\n")
        assert c.get("/api/v1/championships/nope").status_code == 404
        assert c.get("/api/v1/championships", params={"limit": 1000}).status_code == 400
        assert c.get(f"/api/v1/championships/{cid}/standings", params={"view": "final"}).status_code == 400
        first = c.get("/api/v1/championships", params={"limit": 2}).json()
        second = c.get("/api/v1/championships", params={"limit": 2, "cursor": first["next_cursor"]}).json()
        assert not {x["id"] for x in first["items"]} & {x["id"] for x in second["items"]}
        etag = c.get("/api/v1/records").headers["etag"]
        assert c.get("/api/v1/records", headers={"If-None-Match": etag}).status_code == 304
        cors = c.get("/api/v1/meta", headers={"Origin": "https://example.github.io"})
        assert cors.headers["access-control-allow-origin"] == "https://example.github.io"
        assert "access-control-allow-origin" not in c.get("/api/v1/meta", headers={"Origin": "https://evil.example"}).headers
        assert re.fullmatch(r"p[a-z2-7]{12}", env.pid("A"))


def test_roles(env):
    db.migrate(DSN, "importer-pass", "api-pass", log=lambda *_: None)
    api = re.sub(r"//[^@]+@", "//dashboard_api:api-pass@", DSN)
    with psycopg.connect(api, autocommit=True) as c:
        c.execute("SELECT count(*) FROM dashboard.championships")
        c.execute("SELECT * FROM dashboard.freshness")
        for table in ("dashboard.player_sources", "dashboard.import_checkpoints", "ranking.scores"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(f"SELECT 1 FROM {table}")
    importer = re.sub(r"//[^@]+@", "//dashboard_importer:importer-pass@", DSN)
    with psycopg.connect(importer, autocommit=True) as c:
        c.execute("SELECT application_buffer FROM matchmaking.persistent_gatherings")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT password FROM matchmaking.persistent_gatherings")
