"""End-to-end test of server/sil/sil_server.py with a client that behaves like DQMJ3P's SIL code.

Starts the server on a temporary data dir, then: register -> getnonce -> login -> private upload ->
private download (Data="Download_Code") -> public download/getproperties -> present code.
usage: python -I test_sil.py
"""
import hashlib
import hmac
import importlib.util
import json
import os
import socket
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "..", "sil", "sil_server.py")
GP_FILES = os.path.join(HERE, "..", "..", "re", "tools", "gp_files.py")
KEY = b"3Ef7Db65775e4cCF"
PRESENT_KEY_B = bytes.fromhex("21dc24dd6a48fde68c934832a87b1762b522031cadf4f53f9e21ea8eed3ccc2d")


def tlv(fields):
    # The game adds parameters at the list head, so the wire order is reversed; the server must not care.
    out = b""
    for name, data in reversed(list(fields.items())):
        out += bytes([len(name)]) + name.encode() + struct.pack("<I", len(data)) + data
    return out


def untlv(body):
    fields, i = {}, 0
    while i < len(body):
        n = body[i]
        name = body[i + 1:i + 1 + n].decode()
        i += 1 + n
        (size,) = struct.unpack_from("<I", body, i)
        fields[name] = body[i + 4:i + 4 + size]
        i += 4 + size
    return fields


class GameClient:
    def __init__(self, base):
        self.base, self.friend_code, self.token = base, None, None

    def call(self, endpoint, fields=None, wire=None):
        """wire: bytes actually sent instead of the TLV body (the digest still covers the TLV body)."""
        body = tlv(fields or {})
        headers = {"Content-Type": "application/octet-stream", "X-Sil-Version": "1",
                   "X-Sil-Client": "3DS", "X-Sil-Title-Code": "00200605"}
        if self.friend_code:
            headers["X-Sil-Friend-Code"] = self.friend_code
        if self.token:
            headers["X-Sil-Digest"] = hashlib.md5(body + self.token + KEY).hexdigest()
        req = urllib.request.Request(self.base + endpoint, data=body if wire is None else wire, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            assert resp.status == 200
            raw = resp.read()
            if self.token:  # the game rejects responses with a wrong digest (-304)
                assert resp.headers["X-Sil-Digest"] == hashlib.md5(raw + self.token + KEY).hexdigest(), "bad response digest"
        out = untlv(raw)
        assert "Result" in out, out
        return out


def player_token():
    return hashlib.md5(os.urandom(16)).hexdigest()[:16].encode().ljust(256, b"\0")


def logged_in_client(base):
    c = GameClient(base)
    service_token = player_token()
    r = c.call("nuser/register", {"Authentication-Token": service_token})
    assert r["Result"] == b"OK" and len(r["Friend-Code"]) == 12, r
    c.friend_code = r["Friend-Code"].decode()
    r = c.call("nuser/getnonce")
    assert r["Result"] == b"OK" and len(r["Nonce"]) == 16, r
    r = c.call("nuser/login", {"Authentication-Token": service_token,
                               "Digest": hashlib.md5(r["Nonce"] + KEY).digest()})
    assert r["Result"] == b"OK" and len(r["Token"]) == 16, r
    c.token = r["Token"]
    return c


def result_pack(pop=0, strength=0, evaluation=0, win=0, wins=0, level=50, stat=None):
    """GradeResultPack: points, `wins` rounds won out of 3, a team of 4 Geodraco Baugaia (species
    71, max stats 1900/320/970/730/600/610) of `level`, every stat 10 * level (or `stat`)."""
    pack = bytearray(0x540)
    pack[0] = 3
    struct.pack_into("<4H2xI", pack, 2, pop, strength, evaluation, win, pop + strength + evaluation + win)
    for i in range(wins):
        pack[0x14 + i * 0x78 + 0x40] = 1
    for i in range(4):
        m = 0x17c + i * 0xf0
        struct.pack_into("<h8h", pack, m + 0x1c, 0x47, *[stat or 10 * level] * 8)
        pack[m + 0x2e] = level
        pack[m + 0x3c] = 100  # level cap 100
    return bytes(pack)


def player_files(name, location, level):
    """00_UserData + GradeResultPack of a player whose team is 4 monsters of the given level."""
    user_data = bytearray(0xc4)
    struct.pack_into("<I", user_data, 4, location)
    user_data[0xc:0xc + 2 * len(name)] = name.encode("utf-16-le")
    user_data[0xb9] = 1
    return bytes(user_data), result_pack(win=1000, wins=3, level=level)


def check_older_results():
    """Results stored before the team check (or under another TEAM_CHECK_VERSION) are checked at start."""
    spec = importlib.util.spec_from_file_location("sil_server_test", SERVER)
    sil = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sil)
    caps = sil.load_species_caps()
    level_121 = bytearray(result_pack())
    level_121[0x17c + 0x40:0x17c + 0x42] = struct.pack("<H", 0x400)  # two stars: cap 120
    level_121[0x17c + 0x2e] = 120
    assert sil.gp_result_problems(bytes(level_121), caps) is None
    level_121[0x17c + 0x2e] = 121
    assert sil.gp_result_problems(bytes(level_121), caps) == "slot 0 species 71: level 121 (cap 120)"
    bonus = bytearray(result_pack())  # base stats fine, the bonus at +0x84 inflated (ATK 500+4000)
    bonus[0x17c + 0x88:0x17c + 0x8a] = struct.pack("<h", 4000)
    assert sil.gp_result_problems(bytes(bonus), caps) == "slot 0 species 71: ATK 500+4000 (limit 1455)"
    bonus[0x17c + 0x88:0x17c + 0x8a] = struct.pack("<h", 900)  # 500+900 is within the limit
    assert sil.gp_result_problems(bytes(bonus), caps) is None
    bonus[0x17c + 0x88:0x17c + 0x8a] = struct.pack("<h", 4000)
    path = os.path.join(tempfile.mkdtemp(prefix="sil-check-"), "sil.sqlite3")
    store = sil.Store(path)
    store.db.execute("DROP TABLE gp_results")  # the table as before the check
    store.db.execute("CREATE TABLE gp_results (id INTEGER PRIMARY KEY, friend_code TEXT, mode TEXT, score INTEGER, "
                     "data BLOB, uploaded INTEGER, day TEXT)")
    for data in (result_pack(stat=8000), result_pack(), bytes(level_121), bytes(bonus)):
        store.db.execute("INSERT INTO gp_results (friend_code, mode, score, data, day) VALUES ('1', 'grade', 0, ?, '2026-01-01')", (data,))
    store.db.commit()
    store.db.close()
    store = sil.Store(path)  # reopen: adds the columns
    check = lambda data: sil.gp_result_problems(data, caps)
    assert [rid for rid, _ in store.check_gp_results(check)] == [1, 3, 4]
    v = sil.TEAM_CHECK_VERSION
    assert store.q("SELECT id, rejected IS NOT NULL, checked FROM gp_results ORDER BY id") == [(1, 1, v), (2, 0, v), (3, 1, v), (4, 1, v)]
    assert store.check_gp_results(check) == []  # already decided


def load_server():
    spec = importlib.util.spec_from_file_location("sil_server_cpu", SERVER)
    sil = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sil)
    return sil


def check_cpu_teams():
    """cpu_teams.json: every team loads, passes the team check, fits in 4 slots and matches the catalog."""
    sil = load_server()
    caps = sil.load_species_caps()
    teams = sil.load_cpu_teams(caps)
    with open(sil.CPU_TEAMS_FILE, encoding="utf-8") as f:
        assert len(teams) == len(json.load(f)["teams"]) > 0, "a CPU team was left out"
    with open(os.path.join(HERE, "..", "dashboard", "data", "monsters.json"), encoding="utf-8") as f:
        catalog = {m["id"]: m for m in json.load(f)["species"]}
    bodies = {70: 1, 71: 1, 72: 2, 73: 3, 74: 4}  # Small, Normal, Mega, Giga, Ultra Body
    for team in teams:
        assert team["name"].startswith("CPU ") and sil.team_problems(team["record"], caps) == []
        assert sum(m["slots"] for m in team["monsters"]) <= 4, team["name"]
        for i, m in enumerate(team["monsters"]):
            kind = catalog[m["species"]]
            size = [bodies[t] for t, _ in m["traits"] if t in bodies]
            assert (m["family"], m["rank"]) == (kind["family"], kind["rank"]) and not kind["story_copy"], m
            assert m["slots"] == (size[0] if size else max(1, kind["size"])), m
            body = [t for t, _ in m["traits"] if t in bodies]
            assert m["small"] == (body[:1] == [70] or (not body and kind["size"] == 0)), m
            rec = team["record"][i * 0xf0:(i + 1) * 0xf0]
            assert struct.unpack_from("<h", rec, 0x1c)[0] == m["species"] and rec[0x2e] == m["level"]
            assert sil.monster_level_cap(rec) == (120 if m["level"] > 100 else 100)
            assert list(struct.unpack_from("<9H", rec, 0x44))[:len(m["traits"])] == [t for t, _ in m["traits"]]
        main, sub = team["record"][0x3c0], team["record"][0x3c1]  # main and sub: two different monsters
        single = len(team["monsters"]) == 1
        assert main < len(team["monsters"]) and (sub == 0xff if single else sub != main), team["name"]
        block = sil.cpu_team_block(team)
        assert len(block) == 0x49c and block[:5] == team["id"].encode() and block[0xd8:0xd8 + 0x3c4] == team["record"]
        assert block[0x20:0x44].decode("utf-16-le").rstrip("\0") == team["name"]
    names = lambda rules: {t["name"] for t in teams if sil.cpu_team_allowed(t, rules)}
    assert names([(1, 1), (9, 0), (9, 0)]) == {"CPU Metallo", "CPU Slime"}  # Slime family
    assert names([(0, 0)]) == {"CPU Roulette", "CPU Demoni", "CPU Piccoli", "CPU Skip"}  # size S only, not N
    assert names([(5, 4)]) == set() and len(names([])) == len(teams)  # strength limit: no CPU team


def check_cpu_opponents():
    """With CPU teams on, a registered player gets them as opponents even when nobody else played,
    and in Challengers GP only the teams that meet the rules (contest 2: Slime family only)."""
    data_dir = tempfile.mkdtemp(prefix="sil-cpu-")
    port = free_port()
    log = open(os.path.join(data_dir, "server.log"), "w+b")
    proc = subprocess.Popen([sys.executable, "-I", SERVER, "--port", str(port), "--data", data_dir,
                             "--gp-start", "2026-01-05", "--gp-today", "2026-01-14"],
                            stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", port), 0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        c = logged_in_client(f"http://127.0.0.1:{port}/00300701/")
        fc = c.friend_code.encode()
        user_data, _ = player_files("Solo", 76, 50)
        assert c.call("file/upload", {"File-Name": b"00_UserData.bin", "Friend-Code": fc, "Data": user_data})["Result"] == b"OK"
        owners = {}
        for name, mode in ((b"09_Grade_PrivateDlBattle.bin", "grade"), (b"18_Limit_PrivateDlBattle.bin", "limit")):
            r = c.call("file/upload", {"File-Name": name, "Friend-Code": fc, "Data": b"Download_Code"})
            pack = r["Add-Data"]
            assert r["Result"] == b"OK" and len(pack) == 0x297c, r["Result"]
            teams = [pack[i * 0x49c:(i + 1) * 0x49c] for i in range(9)]
            owners[mode] = {t[0x20:0x44].decode("utf-16-le").split("\0")[0] for t in teams if t[:3] == b"CPU"}
            # rounds with no team keep Def_DLBattle (no public files here: all zero)
            full = mode == "grade"  # 9 CPU teams for 3 rounds; only 2 meet the Slime rule
            assert all(t[:3] == b"CPU" or (not full and t == bytes(0x49c)) for t in teams), mode
        assert len(owners["grade"]) >= 3, owners
        assert owners["limit"] == {"CPU Metallo", "CPU Slime"}, owners  # the only Slime family teams
    finally:
        proc.terminate()
        proc.wait(timeout=5)
        log.seek(0)
        text = log.read().decode(errors="replace")
        with open(os.path.join(HERE, "..", "sil", "cpu_teams.json"), encoding="utf-8") as f:
            count = len(json.load(f)["teams"])
        assert f"Grand Prix CPU teams: {count}" in text, text[-1500:]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    data_dir = tempfile.mkdtemp(prefix="sil-test-")
    # seed the Grand Prix files like a real deployment would
    public = os.path.join(data_dir, "public")
    subprocess.run([sys.executable, "-I", GP_FILES, "--private-template", public], check=True, capture_output=True)
    os.rename(os.path.join(public, "private_template"), os.path.join(data_dir, "private_templates"))
    port = free_port()
    # a file, not a pipe: nobody reads a pipe until the end, and a full one blocks the server
    log = open(os.path.join(data_dir, "server.log"), "w+b")
    # Grand Prix calendar: contest 1 = Jan 5-11, contest 2 = Jan 12-18, today = its 3rd day
    proc = subprocess.Popen([sys.executable, "-I", SERVER, "--port", str(port), "--data", data_dir,
                             "--gp-start", "2026-01-05", "--gp-today", "2026-01-14",
                             "--gp-prize-champion", "47", "--gp-prize-top10", "66", "--no-cpu-teams"],
                            stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", port), 0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        c = GameClient(f"http://127.0.0.1:{port}/00300701/")
        service_token = player_token()

        r = c.call("nuser/register", {"Authentication-Token": service_token})
        assert r["Result"] == b"OK" and len(r["Friend-Code"]) == 12, r
        c.friend_code = r["Friend-Code"].decode()

        r = c.call("nuser/getnonce")
        assert r["Result"] == b"OK" and len(r["Nonce"]) == 16, r
        r = c.call("nuser/login", {"Authentication-Token": service_token,
                                   "Digest": hashlib.md5(r["Nonce"] + KEY).digest()})
        assert r["Result"] == b"OK" and len(r["Token"]) == 16, r
        c.token = r["Token"]

        # a save that registered on another server logs in with its old friend code
        old = GameClient(c.base)
        old.friend_code = "456093702889"
        r = old.call("nuser/getnonce")
        assert r["Result"] == b"OK" and len(r["Nonce"]) == 16, r
        r = old.call("nuser/login", {"Authentication-Token": service_token,
                                     "Digest": hashlib.md5(r["Nonce"] + KEY).digest()})
        assert r["Result"] == b"OK" and len(r["Token"]) == 16, r
        bad = GameClient(c.base)
        bad.friend_code = "short"
        assert bad.call("nuser/getnonce")["Result"] == b"USER_NOT_EXIST"

        # that login bound the friend code: another player can't use it
        nonce = old.call("nuser/getnonce")["Nonce"]
        r = old.call("nuser/login", {"Authentication-Token": player_token(),
                                     "Digest": hashlib.md5(nonce + KEY).digest()})
        assert r["Result"] == b"INVALID_TOKEN", r
        # malformed tokens, as the old patches send them, are refused
        for token in (bytes(256), os.urandom(256)):
            r = GameClient(c.base).call("nuser/register", {"Authentication-Token": token})
            assert r["Result"] == b"INVALID_DATA", r
        nonce = old.call("nuser/getnonce")["Nonce"]
        r = old.call("nuser/login", {"Authentication-Token": bytes(256),
                                     "Digest": hashlib.md5(nonce + KEY).digest()})
        assert r["Result"] == b"INVALID_DATA", r
        # a game that lost its friend code gets the same one back
        r = GameClient(c.base).call("nuser/register", {"Authentication-Token": service_token})
        assert r["Result"] == b"OK" and r["Friend-Code"].decode() in (c.friend_code, old.friend_code), r

        save = os.urandom(0x37af0)
        fc = c.friend_code.encode()
        r = c.call("file/upload", {"File-Name": b"PrivateDLFixedSaveData.bin", "Friend-Code": fc, "Data": save})
        assert r["Result"] == b"OK", r
        r = c.call("file/upload", {"File-Name": b"PrivateDLFixedSaveData.bin", "Friend-Code": fc, "Data": b"Download_Code"})
        assert r["Result"] == b"OK" and r["Add-Data"] == save and struct.unpack("<I", r["Add-Data-Size"])[0] == len(save)
        r = c.call("file/upload", {"File-Name": b"missing.bin", "Friend-Code": fc, "Data": b"Download_Code"})
        assert r["Result"] == b"FILE_NOT_EXIST", r
        # Azahar sends the chunks sorted by content: here the Data payload lands after a whole record
        fields = {"File-Name": b"PrivateDLFixedSaveData.bin", "Friend-Code": fc, "Data": b"Download_Code"}
        wire = (b"\x04Data" + struct.pack("<I", 13) + tlv({"File-Name": fields["File-Name"]})
                + tlv({"Friend-Code": fc}) + b"Download_Code")
        r = c.call("file/upload", fields, wire=wire)
        assert r["Result"] == b"OK" and r["Add-Data"] == save, r["Result"]

        r = c.call("file/download", {"File-Name": b"001_Server_Status.bin"})
        assert r["Result"] == b"OK" and r["Data"][0] == 0, r  # seeded: Grand Prix open

        # Grand Prix: no user pack before registering, template (registered byte 0xb9 = 1) after
        r = c.call("file/upload", {"File-Name": b"23_UserPackData.bin", "Friend-Code": fc, "Data": b"Download_Code"})
        assert r["Result"] == b"FILE_NOT_EXIST", r
        r = c.call("file/upload", {"File-Name": b"00_UserData.bin", "Friend-Code": fc, "Data": bytes(0xc4)})
        assert r["Result"] == b"OK", r
        r = c.call("file/upload", {"File-Name": b"23_UserPackData.bin", "Friend-Code": fc, "Data": b"Download_Code"})
        assert r["Result"] == b"OK" and len(r["Add-Data"]) == 0x2698 and r["Add-Data"][0xb9] == 1, r["Result"]
        empty_result = bytearray(0x540)
        struct.pack_into("<I", empty_result, 0xC, 4321)
        r = c.call("file/upload", {"File-Name": b"GradeResultPack.bin", "Friend-Code": fc, "Data": bytes(empty_result)})
        assert r["Result"] == b"OK", r
        r = c.call("file/download", {"File-Name": b"147_Grade_Def_DLBattle.bin"})
        assert len(r["Data"]) == 0x297c, len(r["Data"])
        default_opponents = r["Data"]

        # Grand Prix opponents: no other player yet -> the all-zero template (client uses Def_DLBattle)
        r = c.call("file/upload", {"File-Name": b"09_Grade_PrivateDlBattle.bin", "Friend-Code": fc, "Data": b"Download_Code"})
        assert r["Result"] == b"OK" and r["Add-Data"] == bytes(0x297c), r["Result"]
        rival = logged_in_client(c.base)
        user_data, result = player_files("Rival", 76, 50)
        for name, data in ((b"00_UserData.bin", user_data), (b"GradeResultPack.bin", result)):
            r = rival.call("file/upload", {"File-Name": name, "Friend-Code": rival.friend_code.encode(), "Data": data})
            assert r["Result"] == b"OK", r
        r = c.call("file/upload", {"File-Name": b"09_Grade_PrivateDlBattle.bin", "Friend-Code": fc, "Data": b"Download_Code"})
        pack = r["Add-Data"]
        assert r["Result"] == b"OK" and len(pack) == 0x297c, r["Result"]
        for entry in range(3):  # round 1 = the rival (only team), rounds 2-3 = Def_DLBattle teams
            team = pack[entry * 0xdd4:entry * 0xdd4 + 0x49c]
            assert team[:12] == rival.friend_code.encode() and struct.unpack_from("<H", team, 0x14)[0] == 76
            assert team[0x20:0x2a] == "Rival".encode("utf-16-le") and team[0xd8:0xd8 + 0x3c4] == result[0x17c:]
            assert pack[entry * 0xdd4 + 0x49c:(entry + 1) * 0xdd4] == default_opponents[entry * 0xdd4 + 0x49c:(entry + 1) * 0xdd4]
        r = c.call("file/upload", {"File-Name": b"18_Limit_PrivateDlBattle.bin", "Friend-Code": fc, "Data": b"Download_Code"})
        assert r["Add-Data"] == bytes(0x297c), r["Result"]  # nobody played Limit yet

        # a modified team (every stat 8000) is stored and answered OK, but nobody gets it as an opponent
        cheater = logged_in_client(c.base)
        user_data, _ = player_files("Cheater", 12, 50)
        for name, data in ((b"00_UserData.bin", user_data), (b"GradeResultPack.bin", result_pack(win=5000, wins=3, stat=8000))):
            r = cheater.call("file/upload", {"File-Name": name, "Friend-Code": cheater.friend_code.encode(), "Data": data})
            assert r["Result"] == b"OK", r
        r = c.call("file/upload", {"File-Name": b"09_Grade_PrivateDlBattle.bin", "Friend-Code": fc, "Data": b"Download_Code"})
        assert r["Add-Data"] == pack, "a rejected team was offered as an opponent"
        rejected = sqlite3.connect(os.path.join(data_dir, "sil.sqlite3")).execute(
            "SELECT rejected FROM gp_results WHERE friend_code = ?", (cheater.friend_code,)).fetchone()[0]
        assert rejected.startswith("slot 0 species 71: HP 8000 (limit 4750)"), rejected

        # Grand Prix rankings, from results of earlier days (today's uploads above do not count yet)
        r = c.call("file/download", {"File-Name": b"003_Held_Record.bin"})
        assert struct.unpack("<IHBBIII", r["Data"]) == (2, 2026, 1, 14, 1, 2, 0), r["Data"].hex()
        r = c.call("file/download", {"File-Name": b"018_LimitSetting.bin"})  # contest 2: 2nd rule set
        assert len(r["Data"]) == 0x848 and struct.unpack_from("<6I", r["Data"]) == (1, 1, 9, 0, 9, 0)
        assert r["Data"][0x538:].decode("utf-16-le").startswith("Theme: the Slime tournament!\nTema: il torneo degli Slime!")
        r = c.call("file/download", {"File-Name": b"033_Limit_DLNewsMsg.bin"})
        assert len(r["Data"]) == 0x600 and r["Data"].decode("utf-16-le").startswith("Slime family monsters only.\nSolo mostri della famiglia Slime.")
        db = sqlite3.connect(os.path.join(data_dir, "sil.sqlite3"))
        for owner, day, pack in ((rival.friend_code, "2026-01-08", result_pack(win=900, wins=3)),  # contest 1
                                 (c.friend_code, "2026-01-09", result_pack(win=300, wins=1)),
                                 (c.friend_code, "2026-01-12", result_pack(pop=100, evaluation=200, win=450, wins=3)),
                                 (rival.friend_code, "2026-01-12", result_pack(win=600, wins=2)),
                                 (c.friend_code, "2026-01-13", result_pack(win=150, wins=1))):
            db.execute("INSERT INTO gp_results (friend_code, mode, score, data, day) VALUES (?, 'grade', 0, ?, ?)", (owner, pack, day))
        # rejected results count nowhere (the cheater would be first with 5000 points)
        db.execute("INSERT INTO gp_results (friend_code, mode, score, data, day, rejected) VALUES (?, 'grade', 0, ?, ?, ?)",
                   (cheater.friend_code, result_pack(win=5000, wins=3, stat=8000), "2026-01-12", "test"))
        db.commit()
        r = c.call("file/download", {"File-Name": b"089_Grade_Ranking_Pack.bin"})
        pack = r["Data"]
        assert len(pack) == 0x19998, len(pack)
        entry = lambda block, i: struct.unpack_from("<H2xHBBII", pack, block * 0x808 + i * 0x44 + 0x20)
        # contest 2 so far: c 900 points (4 wins / 6 rounds, rank 1, yesterday 1st with 750), rival 600 (2nd both days)
        assert entry(0, 0) == (900, 0, 4, 2, 1, 1) and entry(0, 1) == (600, 76, 2, 1, 2, 2), (entry(0, 0), entry(0, 1))
        assert pack[0x44 + 0x30:0x44 + 0x30 + 10] == "Rival".encode("utf-16-le")
        assert pack[0x10:0x1c] == c.friend_code.encode() and struct.unpack_from("<I", pack, 0)[0] == 1
        assert entry(1, 0) == (900, 76, 3, 0, 0, 1) and entry(1, 1) == (300, 0, 1, 2, 0, 2)  # contest 1 final
        assert entry(2, 0)[0] == 900 and entry(2, 1)[0] == 0  # location 0 (c): only c
        r = c.call("file/download", {"File-Name": b"141_Grade_ChampionRecord.bin"})
        assert len(r["Data"]) == 0x1454 and struct.unpack_from("<I", r["Data"], 0)[0] == 1  # entry 0 starts at 0
        assert struct.unpack_from("<IIBB", r["Data"], 8) == (76, 900, 3, 0) and r["Data"][0x14:0x1e] == "Rival".encode("utf-16-le")
        r = c.call("file/upload", {"File-Name": b"23_UserPackData.bin", "Friend-Code": fc, "Data": b"Download_Code"})
        user_pack = r["Add-Data"]
        assert len(user_pack) == 0x2698 and user_pack[0xb9] == 1
        assert struct.unpack_from("<HH", user_pack, 0xfc) == (1, 66)  # 2nd in contest 1: top-ten item
        grade = 0x110
        assert struct.unpack_from("<III4x7I", user_pack, grade) == (1, 2, 1, 2, 600, 100, 0, 200, 6, 4)
        assert struct.unpack_from("<H2xHBBII", user_pack, grade + 0x88 + 0x20) == (900, 0, 4, 2, 0, 1)  # your ranking
        assert struct.unpack_from("<III4xI", user_pack, grade + 0x1098) == (2, 2, 2, 1)  # contest 1: 2nd of 2
        assert struct.unpack_from("<H2x4H", user_pack, grade + 0x1098 + 0x44) == (3, 0, 0, 3, 0)  # top ten: 3 silver
        assert user_pack[0x110 + 0x12c4:] == bytes(0x12c4)  # no Limit results
        with open(os.path.join(data_dir, "public", "030_GP_WallPapers.arc"), "wb") as f:
            f.write(b"x" * 1234)
        r = c.call("file/getproperties", {"File-Name": b"030_GP_WallPapers.arc"})
        assert struct.unpack("<I", r["File-Size"])[0] == 1234 and len(r["Content-Code"]) == 16, r

        db = sqlite3.connect(os.path.join(data_dir, "sil.sqlite3"))
        assert db.execute("SELECT mode, score, day, rejected, checked FROM gp_results ORDER BY id LIMIT 2").fetchall() == [
            ("grade", 4321, "2026-01-14", None, 2), ("grade", 1000, "2026-01-14", None, 2)]
        # portal capture: each uploaded result has its snapshot (name/location at upload, calendar, contest)
        snaps = db.execute("SELECT g.friend_code, s.calendar, s.contest, s.day, s.name, s.location, s.decoder "
                           "FROM gp_snapshots s JOIN gp_results g ON g.id = s.result_id ORDER BY s.result_id").fetchall()
        assert snaps == [(c.friend_code, 1, 2, "2026-01-14", bytes(0x24), 0, 1),
                         (rival.friend_code, 1, 2, "2026-01-14", "Rival".encode("utf-16-le").ljust(0x24, b"\0"), 76, 1),
                         # a rejected result is kept too, with its snapshot
                         (cheater.friend_code, 1, 2, "2026-01-14", "Cheater".encode("utf-16-le").ljust(0x24, b"\0"), 12, 1)], snaps
        assert db.execute("SELECT start, days, offset_source FROM gp_calendars").fetchall() == [("2026-01-05", 7, "local")]
        assert len(db.execute("SELECT value FROM meta WHERE key = 'generation'").fetchone()[0]) == 16
        db.execute("INSERT INTO present_codes (code, package_id) VALUES ('DQMJ3PTEST', 7)")
        db.commit()
        code = "DQMJ3PTEST".encode("utf-16-le").ljust(0x2a, b"\0")
        r = c.call("file/upload", {"File-Name": b"present_code.bin", "Friend-Code": fc, "Data": code})
        assert struct.unpack("<II", r["Add-Data"]) == (7, 0), r
        r = c.call("file/upload", {"File-Name": b"present_code.bin", "Friend-Code": fc, "Data": code})
        assert struct.unpack("<II", r["Add-Data"]) == (7, 1), r  # already used
        r = c.call("file/upload", {"File-Name": b"present_code.bin", "Friend-Code": fc, "Data": "NOPE".encode("utf-16-le")})
        assert struct.unpack("<II", r["Add-Data"])[1] == 2, r  # wrong
        # Original codes (present_codes.json): full-width A code of DQMJ3, then the Latin alias
        for typed, package in (("ＡＥＨＥＳ９Ｖ２ＮＣ", 335), ("goldslimedisc", 201)):
            r = c.call("file/upload", {"File-Name": b"present_code.bin", "Friend-Code": fc,
                                       "Data": typed.encode("utf-16-le").ljust(0x2a, b"\0")})
            assert struct.unpack("<II", r["Add-Data"]) == (package, 0), r
            r = c.call("file/download", {"File-Name": b"PresentCodePackageS%d.bin" % package})
            pack = r["Data"]
            assert pack[:4] == b"BPCP" and struct.unpack_from("<I", pack, 8)[0] == package
            assert hmac.new(PRESENT_KEY_B, pack[:-32], hashlib.sha256).digest() == pack[-32:]
        assert struct.unpack_from("<II", pack, 0xc) == (0, 1)  # disc package, key index 1

        # a body bigger than any upload of the game (save backup: 228 080 bytes) is refused unread
        req = urllib.request.Request(f"http://127.0.0.1:{port}/00300701/file/upload", data=bytes(0x80001), method="POST")
        try:
            urllib.request.urlopen(req, timeout=10)
            raise AssertionError("oversized body accepted")
        except urllib.error.HTTPError as e:
            assert e.code == 413, e.code
        c.call("file/download", {"File-Name": b"001_Server_Status.bin"})  # the server still answers

        c.token = os.urandom(16)  # a client with a wrong session must be refused
        try:
            c.call("file/download", {"File-Name": b"001_Server_Status.bin"})
            raise AssertionError("wrong digest accepted")
        except AssertionError as e:
            assert "bad response digest" in str(e), e
        check_older_results()
        check_cpu_teams()
        check_cpu_opponents()
        print("SIL TEST OK")
    finally:
        proc.terminate()
        proc.wait(timeout=5)
        log.seek(0)
        print(log.read().decode(errors="replace")[-1500:])


main()
