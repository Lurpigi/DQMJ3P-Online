"""Synthetic data for trying the portal locally (never real players). Writes a SIL SQLite file with
the real SIL Store and NEX-like tables into an EMPTY test database, then runs one import.

usage: DASHBOARD_TEST_DB=postgresql://... python tests/demo_data.py OUT_DIR
then:  DASHBOARD_DB_URL=$DASHBOARD_TEST_DB DASHBOARD_SIL_DB=OUT_DIR/sil.sqlite3 DASHBOARD_SIL_CODE=../sil/sil_server.py \
       DASHBOARD_IMPORT=0 python -m dashboard serve
"""
import datetime
import os
import random
import struct
import sys

import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from dashboard import db, decode  # noqa: E402
from dashboard.config import Settings  # noqa: E402
from dashboard.importer import Importer  # noqa: E402

SIL_CODE = os.path.join(HERE, "..", "..", "sil", "sil_server.py")
NAMES = ["Lurpigi", "JEJ", "Ayaka", "Marco", "Sofía", "Élodie", "Kenta", "Giulia", "Tobi", "ミナ", "Pietro", "Lucía",
         "Hiroshi", "Chloé", "Sam", "Davide", "さくら", "Noah", "Federica", "Yuki", "Alessandro Magno", "Bea"]
SPECIES = [1, 25, 36, 37, 91, 107, 152, 190, 253, 333, 372, 452, 568, 622, 651, 730, 805, 834, 843]


def result_pack(rng, team, opponents):
    pack = bytearray(0x540)
    pack[0] = 3
    total = [0, 0, 0, 0]
    wins = 0
    for i in range(3):
        s = 0x14 + i * 0x78
        name, code = opponents[i]
        pack[s:s + 0x24] = name.encode("utf-16-le")[:0x22].ljust(0x24, b"\0")
        if code:
            pack[s + 0x24:s + 0x30] = code.encode()
        won = rng.random() < 0.6
        wins += won
        pack[s + 0x40] = 1 if won else 0
        win, pop, strength, ev = (rng.randint(80, 160) if won else 0), rng.randint(5, 40), rng.randint(0, 30), rng.randint(10, 60)
        struct.pack_into("<I3H", pack, s + 0x44, win, pop, strength, ev)
        for k, v in enumerate((pop, strength, ev, win)):
            total[k] += v
    struct.pack_into("<4H2xI", pack, 2, *total, sum(total))
    for slot, sp in enumerate(team):
        m = 0x17C + slot * 0xF0
        struct.pack_into("<h8h", pack, m + 0x1C, sp, *[rng.randint(300, 999) for _ in range(8)])
        pack[m + 0x3C] = rng.randint(30, 100)
    return bytes(pack)


def main(out):
    dsn = os.environ["DASHBOARD_TEST_DB"]
    rng = random.Random(7)
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "sil.sqlite3")
    if os.path.exists(path):
        os.remove(path)
    sil = decode.load_sil(SIL_CODE)
    store = sil.Store(path)
    cal = sil.GpCalendar(datetime.date(2026, 10, 26), 7, 1)
    cal_id = store.use_calendar(cal, {"prize_champion": 70, "prize_top10": 66, "coins_champion": [0, 0, 3, 0],
                                      "coins_top10": [0, 3, 0, 0], "limit_rotation": True})
    codes = {n: f"{100000000000 + i * 7919:012d}" for i, n in enumerate(NAMES)}
    teams = {n: rng.sample(SPECIES, rng.choice((3, 4))) for n in NAMES}
    today = datetime.date.today()
    for n, code in codes.items():
        ud = bytearray(0xC4)
        struct.pack_into("<I", ud, 4, rng.choice((76, 76, 47, 13, 80, 0)))
        ud[0xC:0xC + 2 * len(n[:10])] = n[:10].encode("utf-16-le")
        store.q("INSERT INTO private_files (friend_code, name, data) VALUES (?, '00_UserData.bin', ?)", code, bytes(ud))
    day = cal.start
    while day <= today:
        for n in rng.sample(NAMES, rng.randint(4, 12)):
            mode = "grade" if rng.random() < 0.65 else "limit"
            if rng.random() < 0.15:
                teams[n][rng.randrange(len(teams[n]))] = rng.choice(SPECIES)
            opps = [(o, codes[o]) if rng.random() < 0.7 else ("Server team", None) for o in rng.sample(NAMES, 3)]
            for _ in range(rng.randint(1, 2)):
                rid = store.add_gp_result(codes[n], mode, result_pack(rng, teams[n], opps), day.isoformat(), cal_id,
                                          cal.contest(day)[0])
                moment = datetime.datetime.combine(day, datetime.time(rng.randint(0, 22)), datetime.timezone(datetime.timedelta(hours=1)))
                store.q("UPDATE gp_results SET uploaded = ? WHERE id = ?", int(min(moment.timestamp(), datetime.datetime.now().timestamp())), rid)
        day += datetime.timedelta(days=1)

    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute("DROP SCHEMA IF EXISTS dashboard, ranking, history, matchmaking CASCADE")
        c.execute(open(os.path.join(HERE, "nex_schema.sql")).read())
        week = decode.gcup_week(datetime.datetime.now(decode.UTC))
        for idx in range(12):
            buf = bytearray(0x1B0)
            buf[0x6E:0x6E + 2 * len(f"G-Cup {idx + 1}")] = f"G-Cup {idx + 1}".encode("utf-16-le")
            buf[0x92], buf[0x93], buf[0x94] = idx % 4, idx % 2, idx % 3
            for band, coins in ((0, (0, 3, 0, 0)), (1, (0, 2, 0, 0)), (2, (0, 1, 0, 0)), (10, (0, 0, 2, 0))):
                buf[0x96 + band * 4:0x9A + band * 4] = bytes(coins)
            c.execute("INSERT INTO matchmaking.persistent_gatherings VALUES (%s, 2, %s, %s, 'secret')",
                      (100 + idx, [0, idx, 0, 0, 0, 0], bytes(buf)))
        racers = {200 + i: n for i, n in enumerate(rng.sample(NAMES, 10))}
        for w in range(week - 3, week + 1):
            start, end = decode.gcup_bounds(w)
            c.execute("INSERT INTO history.gcup_editions (week, cup_index, category, starts_at, ends_at, definition, closed_at, entrants) "
                      "SELECT %s, %s, %s, %s, %s, application_buffer, %s, NULL FROM matchmaking.persistent_gatherings WHERE id = %s",
                      (w, w % 12, 100 + w % 12, start, end, end if w < week else None, 100 + w % 12))
            best = {}
            for pid, name in racers.items():
                if rng.random() < 0.3:
                    continue
                c.execute("INSERT INTO history.gcup_common_data (pid, unique_id, data, received, week) VALUES (%s, 0, %s, %s, %s)",
                          (pid, name[:10].encode("utf-16-le"), start, w))
                for k in range(rng.randint(1, 4)):
                    t = start + datetime.timedelta(hours=rng.randint(1, 160))
                    if t > datetime.datetime.now(decode.UTC):
                        continue
                    score = rng.randint(3500, 5200)
                    improved = score < best.get(pid, (10 ** 9,))[0]
                    if improved:
                        best[pid] = (score, t)
                    c.execute("INSERT INTO history.gcup_submissions (pid, category, unique_id, score, order_by, update_mode, groups, "
                              "param, received, week, changed_best) VALUES (%s, %s, 0, %s, 0, 0, '', 0, %s, %s, %s)",
                              (pid, 100 + w % 12, score, t, w, improved))
            ranked = sorted(best.items(), key=lambda kv: kv[1])
            if w < week:
                c.execute("INSERT INTO ranking.gcup_weeks (week) VALUES (%s) ON CONFLICT DO NOTHING", (w + 1,))
                for pos, (pid, (score, t)) in enumerate(ranked, 1):
                    c.execute("INSERT INTO history.gcup_finals VALUES (%s, %s, %s, %s, 0, %s, %s, %s, %s)",
                              (w, pos, pos, pid, score, t.replace(tzinfo=None), racers[pid][:10], racers[pid][:10].encode("utf-16-le")))
                c.execute("UPDATE history.gcup_editions SET entrants = %s WHERE week = %s", (len(ranked), w))
            else:
                for pid, (score, t) in ranked:
                    c.execute("INSERT INTO ranking.scores VALUES (%s, %s, 0, %s, 0, '', 0, %s)", (pid, 100 + w % 12, score, t.replace(tzinfo=None)))
                    c.execute("INSERT INTO ranking.common_data VALUES (%s, 0, %s) ON CONFLICT DO NOTHING", (pid, racers[pid][:10].encode("utf-16-le")))
    db.migrate(dsn, log=print)
    settings = Settings(db_url=dsn, sil_db=path, sil_code=SIL_CODE, server_id="demo", id_salt="demo-salt-0123456789")
    with psycopg.connect(dsn, autocommit=True, row_factory=psycopg.rows.dict_row) as c:
        Importer(settings, sil).run_once(c)
    print(f"demo data in {path} and {dsn}")


if __name__ == "__main__":
    main(sys.argv[1])
