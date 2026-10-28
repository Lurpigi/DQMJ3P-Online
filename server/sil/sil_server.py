"""Replacement for Square Enix's SIL server used by DQMJ3P (dqm32ds.sil2.square-enix.com).

Protocol (see re/notes/sil_protocol.md):
  POST <base>/<endpoint>, body and response = TLV records [u8 name_len][name][u32le len][data]
  every response carries a `Result` record ("OK" or an error name)
  after nuser/login, requests and responses carry
      X-Sil-Digest: hex(MD5(body || Token || Key))
  Key = "3Ef7Db65775e4cCF", title code 00200605, URL app path 00300701

The game reaches this server only after its URL string is patched (re/tools/make_url_patch.py),
e.g. http://<host>:<port>/00300701/

usage (python -I): sil_server.py [--host 0.0.0.0] [--port 8381] [--data DIR]
  DIR/sil.sqlite3       users, sessions, private files, present codes
  DIR/public/<name>     files served by file/download and file/getproperties
  DIR/private_templates/<name>  default private files for Grand Prix-registered users

Seed the Grand Prix (Ranking Battle) files with re/tools/gp_files.py:
  python -I re/tools/gp_files.py --private-template DIR/public && move DIR/public/private_template DIR/private_templates
The server itself generates the contest calendar (003_Held_Record), the rankings (089/139),
the champion records (141/142), the users' 23_UserPackData and their opponents (09/18) from the
uploaded results; see --gp-* options.
"""
import argparse
import datetime
import hashlib
import itertools
import os
import secrets
import sqlite3
import struct
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KEY = b"3Ef7Db65775e4cCF"
TITLE_CODE = "00200605"
APP_PATH = "00300701"
DOWNLOAD_CODE = b"Download_Code"

# Fallback public files, so features that need them do not hard-fail on an empty server.
DEFAULT_PUBLIC = {
    # byte 0: 0 open, 1/2 reception closed, 3 anomaly, 4 not open. Ranking Battle data is not
    # recreated yet, so keep it "not open".
    "001_Server_Status.bin": bytes([4]) + bytes(7),
    "025_SendOfficialDummy.bin": bytes(0x54),
}


# --- TLV -----------------------------------------------------------------------------------
def tlv_decode(body):
    fields, i = {}, 0
    while i < len(body):
        n = body[i]
        name = body[i + 1:i + 1 + n].decode("ascii", "replace")
        i += 1 + n
        (size,) = struct.unpack_from("<I", body, i)
        i += 4
        fields[name] = body[i:i + size]
        i += size
    return fields


def tlv_encode(fields):
    out = bytearray()
    for name, data in fields.items():
        if isinstance(data, str):
            data = data.encode("ascii")
        out += bytes([len(name)]) + name.encode("ascii") + struct.pack("<I", len(data)) + data
    return bytes(out)


def digest_hex(body, token):
    return hashlib.md5(body + token + KEY).hexdigest()


REQUEST_FIELDS = ("Authentication-Token", "Digest", "File-Name", "Friend-Code", "Data")


def azahar_unsort(body, token, sent):
    """Azahar's http:C keeps chunked post data in a std::map keyed by content, so the chunks of a
    request (whole TLV records, or a record header and its payload sent apart, e.g. file/upload
    Data) arrive sorted by their bytes. Rebuild the fields from the known record headers and try
    their orders against the client's digest. Returns the original body, or None."""
    heads = []
    for name in REQUEST_FIELDS:
        head = bytes([len(name)]) + name.encode()
        start = body.find(head)
        while start != -1:
            if start + len(head) + 4 <= len(body):
                (size,) = struct.unpack_from("<I", body, start + len(head))
                heads.append((start, name, len(head) + 4, size))
            start = body.find(head, start + 1)
    heads.sort()
    if not heads or len(heads) > 6:
        return None
    # at most one payload is sent apart from its header: try each record (or none) as detached
    for detached in [None] + heads:
        covered = bytearray(len(body))
        fields = []
        for head in heads:
            start, name, head_len, size = head
            end = start + (head_len if head is detached else head_len + size)
            if end > len(body) or any(covered[start:end]):
                break
            covered[start:end] = b"\1" * (end - start)
            if head is not detached:
                fields.append((name, body[start + head_len:end]))
        else:
            rest = [i for i, c in enumerate(covered) if not c]
            if detached is None:
                if rest:
                    continue
            elif len(rest) != detached[3] or (rest and rest != list(range(rest[0], rest[0] + len(rest)))):
                continue
            else:
                fields.append((detached[1], body[rest[0]:rest[-1] + 1] if rest else b""))
            for order in itertools.permutations(fields):
                candidate = tlv_encode(dict(order))
                if digest_hex(candidate, token) == sent:
                    return candidate
    return None


# --- storage -------------------------------------------------------------------------------
class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS users (friend_code TEXT PRIMARY KEY, created INTEGER DEFAULT (strftime('%s','now')));
            CREATE TABLE IF NOT EXISTS sessions (friend_code TEXT PRIMARY KEY, nonce BLOB, token BLOB);
            CREATE TABLE IF NOT EXISTS private_files (friend_code TEXT, name TEXT, data BLOB, updated INTEGER DEFAULT (strftime('%s','now')), PRIMARY KEY (friend_code, name));
            -- Grand Prix results (GradeResultPack.bin / LimitResultPack.bin, 0x540 B, score = u32 at +0xc);
            -- day: contest day (GpCalendar, YYYY-MM-DD) the result counts for
            CREATE TABLE IF NOT EXISTS gp_results (id INTEGER PRIMARY KEY, friend_code TEXT, mode TEXT, score INTEGER, data BLOB, uploaded INTEGER DEFAULT (strftime('%s','now')), day TEXT);
            CREATE TABLE IF NOT EXISTS downloads (name TEXT PRIMARY KEY, count INTEGER);
            -- code: the code as typed (UTF-16LE decoded, NULs stripped); status: 0 ok, 1 already used, 2 wrong
            CREATE TABLE IF NOT EXISTS present_codes (code TEXT PRIMARY KEY, package_id INTEGER, single_use INTEGER DEFAULT 1);
            CREATE TABLE IF NOT EXISTS present_code_uses (code TEXT, friend_code TEXT, PRIMARY KEY (code, friend_code));
        """)
        if "day" not in [c[1] for c in self.db.execute("PRAGMA table_info(gp_results)")]:
            self.db.execute("ALTER TABLE gp_results ADD COLUMN day TEXT")

    def date_gp_results(self, calendar):
        """Results stored before gp_results.day existed count for the day they were uploaded."""
        for rid, uploaded in self.q("SELECT id, uploaded FROM gp_results WHERE day IS NULL"):
            self.q("UPDATE gp_results SET day = ? WHERE id = ?", calendar.day_of(uploaded).isoformat(), rid)

    def q(self, sql, *args):
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur.fetchall()


# --- request handling ----------------------------------------------------------------------
class SilError(Exception):
    def __init__(self, result, **extra):
        super().__init__(result)
        self.result, self.extra = result, extra


GP_RESULT_FILES = {"GradeResultPack.bin": "grade", "LimitResultPack.bin": "limit"}
GP_REGISTRATION_FILE = "00_UserData.bin"
GP_PRIVATE_OPPONENT_FILES = {"09_Grade_PrivateDlBattle.bin": "grade", "18_Limit_PrivateDlBattle.bin": "limit"}
GP_DEF_OPPONENT_FILES = {"grade": "147_Grade_Def_DLBattle.bin", "limit": "148_Limit_Def_DLBattle.bin"}


# --- Grand Prix opponents (re/notes/grandprix_formats.md 3.8) ------------------------------
# *_DLBattle = 3 entries (menu rows: 0 hard, 1 similar, 2 easy) of 3 team blocks (one per round).
TEAM_BLOCK = 0x49C
TEAM_RECORD = 0x3C4    # the mode's registered team in the save: 4 monsters of 0xf0 + 4 bytes
MONSTER = 0xF0
RESULT_TEAM = 0x17C    # team record inside Grade/LimitResultPack
ENTRIES, ROUNDS = 3, 3


def team_strength(record):
    """Rough team strength, to sort opponents. The game's own measure (FUN_00247444) also weighs
    species, skills and traits; stats and level are enough to tell weaker from stronger teams."""
    total = 0
    for i in range(4):
        m = record[i * MONSTER:(i + 1) * MONSTER]
        if len(m) < MONSTER or struct.unpack_from("<h", m, 0x1C)[0] <= 0:  # no species
            continue
        hp, mp, _hp, _mp, atk, dfn, agi, wis = struct.unpack_from("<8h", m, 0x1E)
        total += hp + mp + atk + dfn + agi + wis + 10 * m[0x3C]
    return total


def make_team_block(friend_code, user_data, record):
    """0x49c team block from a player's 00_UserData and the team record of their last ResultPack.
    Head: +0x00 owner id (the client uses a PrivateDlBattle only if entry 1 starts with non-zero
    bytes, FUN_006cd8f4), +0x14 u16 location (loc_NNN, flag), +0x18 u32 counter shown next to
    the round (0), +0x20 name, +0x44 beginner mark, +0x45 has Mii, +0x4a 5 profile bytes,
    +0x50 Mii; team record at +0xd8 (FUN_005a5bf8, FUN_002f7a6c, FUN_002f7618)."""
    b = bytearray(TEAM_BLOCK)
    b[0:12] = friend_code.encode("ascii")[:12].ljust(12, b"\0")
    if len(user_data) >= 0xC4:
        b[0x14:0x16] = user_data[0x4:0x6]
        b[0x20:0x44] = user_data[0xC:0x30]
        b[0x44] = user_data[0xB8]
        b[0x45] = user_data[0xBA]
        b[0x4A:0x4F] = user_data[0xBB:0xC0]
        b[0x50:0xD8] = user_data[0x30:0xB8]
    b[0xD8:0xD8 + TEAM_RECORD] = record[:TEAM_RECORD].ljust(TEAM_RECORD, b"\0")
    return bytes(b)


def pick_opponents(pool, own_strength):
    """pool: [(strength, team_block)]. Returns the 3 entries (hard, similar, easy) as lists of up to
    3 team blocks, each sorted from the weakest round to the strongest."""
    ranked = sorted(pool, key=lambda t: t[0])
    stronger = [t for t in ranked if t[0] >= own_strength] or ranked
    weaker = [t for t in ranked if t[0] <= own_strength] or ranked
    entries = (stronger[-ROUNDS:],
               sorted(ranked, key=lambda t: abs(t[0] - own_strength))[:ROUNDS],
               weaker[:ROUNDS])
    return [[block for _, block in sorted(entry, key=lambda t: t[0])] for entry in entries]


# --- Grand Prix contests and rankings (re/notes/grandprix_formats.md 2, 3.2, 3.6, 3.7, 3.9) -----
GP_MODES = ("grade", "limit")
GP_HELD_FILE = "003_Held_Record.bin"
GP_RANKING_FILES = {"089_Grade_Ranking_Pack.bin": "grade", "139_Limit_Ranking_Pack.bin": "limit"}
GP_CHAMPION_FILES = {"141_Grade_ChampionRecord.bin": "grade", "142_Limit_ChampionRecord.bin": "limit"}
GP_USER_PACK_FILE = "23_UserPackData.bin"
RANK_ENTRY, RANK_BLOCK, RANK_BLOCKS, RANK_BLOCK_ENTRIES = 0x44, 0x808, 51, 30
USER_PACK, USER_PACK_HEAD, USER_PACK_MODE = 0x2698, 0x110, 0x12C4
USER_PACK_NEIGHBOURS = 0x88    # mode block: 10 ranking entries around the user ("your ranking")
USER_PACK_PREVIOUS = 0x1098    # mode block: result in the previous contest (same layout as +0)
CHAMPION_ENTRY, CHAMPION_MAX = 0x34, 100
GP_LIMIT_FILE = "018_LimitSetting.bin"
GP_LIMIT_NEWS_FILE = "033_Limit_DLNewsMsg.bin"  # UTF-16LE, 0x600 B

# Challengers GP rules (018_LimitSetting, re/notes/grandprix_formats.md 3.4), one set per contest,
# in rotation. A rule (type, value) must hold for every monster of the team (FUN_002f7e9c):
#   0 size: species table +0x30 (0/1 small, 2 medium, 3 giga, 4 mega; value 0 also accepts 1)
#   1 family: species table +0x23 (1 Slime, 2 Dragon, 3 Beast, 4 Nature, 5 Demon, 6 Undead, 7 Material)
#   4 rank: species rank 1..8 (F..SS), raised by level (25-49 -> C, 50-99 -> A, 100 -> SS)
#   5 team grade cap: whole-team strength grade (<4000 -> 1, ..., >=74000 -> 8) must be <= value
LIMIT_RULE_SETS = [
    ([], "Nessuna regola: porta la tua squadra migliore!", "Tema: tutti contro tutti!"),
    ([(1, 1)], "Regola: solo mostri della famiglia Slime.", "Tema: il torneo degli Slime!"),
    ([(5, 4)], "Regola: grado della squadra al massimo 4\n(forza totale sotto 18000).", "Tema: squadre leggere!"),
    ([(0, 0)], "Regola: solo mostri di taglia piccola.", "Tema: piccoli ma forti!"),
    ([(1, 2)], "Regola: solo mostri della famiglia Drago.", "Tema: il torneo dei Draghi!"),
    ([(5, 6)], "Regola: grado della squadra al massimo 6\n(forza totale sotto 46000).", "Tema: squadre equilibrate!"),
    ([(1, 5)], "Regola: solo mostri della famiglia Demone.", "Tema: il torneo dei Demoni!"),
    ([(4, 8)], "Regola: solo mostri di rango SS\n(o qualsiasi mostro al livello 100).", "Tema: campioni al massimo livello!"),
]


def utf16_field(text, size):
    return text.encode("utf-16-le")[:size - 2].ljust(size, b"\0")


def limit_setting(contest):
    """018_LimitSetting (0x848) for contest N: 3 rules (u32 type, u32 value; 9 = none), rule text
    (UTF-16LE, 0x520 B) and theme announcement (UTF-16LE, 0x310 B)."""
    rules, text, theme = LIMIT_RULE_SETS[(contest - 1) % len(LIMIT_RULE_SETS)]
    rules = (list(rules) + [(9, 0)] * 3)[:3]
    return (b"".join(struct.pack("<II", *r) for r in rules)
            + utf16_field(text, 0x520) + utf16_field(theme, 0x310))


class GpCalendar:
    """Contest N runs for `days` days from start + (N-1)*days. Results count for the day they are
    uploaded; rankings are published once a day from the contest's previous days, so the first
    day of a contest has none (Held+8 = 0: the client then only shows the previous contest)."""

    def __init__(self, start, days=7, utc_offset=None, today=None):
        self.start, self.days, self.utc_offset, self.fixed_today = start, days, utc_offset, today

    def day_of(self, unix_time):
        if self.utc_offset is None:
            return datetime.datetime.fromtimestamp(unix_time).date()
        return (datetime.datetime.fromtimestamp(unix_time, datetime.timezone.utc)
                + datetime.timedelta(hours=self.utc_offset)).date()

    def today(self):
        return self.fixed_today or self.day_of(time.time())

    def contest(self, day):
        """(contest number N >= 1, day index in the contest)"""
        n, idx = divmod(max(0, (day - self.start).days), self.days)
        return n + 1, idx

    def first_day(self, n):
        return self.start + datetime.timedelta(days=(n - 1) * self.days)

    def held_record(self):
        """003_Held_Record (0x14): +0 u32 day index (CorrectPointTable multiplier), +4 u16 year,
        +6 u8 month, +7 u8 day, +8 u32 'today's rankings exist' (FUN_006cd8a0), +0xc u32 N."""
        day = self.today()
        n, idx = self.contest(day)
        return struct.pack("<IHBBIII", min(idx, 6), day.year, day.month, day.day, int(idx > 0), n, 0)


def gp_result_totals(data):
    """Points (ResultPack +2 popularity, +4 strength, +6 evaluation, +8 win, +0xc total) and the
    rounds won (round summary +0x40 = 1) of one Grand Prix entry (3 rounds)."""
    pop, strength, evaluation, win = struct.unpack_from("<4H", data, 2)
    (total,) = struct.unpack_from("<I", data, 0xC)
    wins = sum(data[0x14 + i * 0x78 + 0x40] == 1 for i in range(3))
    return {"total": total, "win": win, "pop": pop, "strength": strength, "eval": evaluation,
            "battles": 3, "wins": wins}


def rank_players(players):
    """Sort by total points; position = 1..n, rank = 1 + players with more points (ties share)."""
    ordered = sorted(players, key=lambda p: (-p["total"], p["friend_code"]))
    out = []
    for pos, p in enumerate(ordered, 1):
        rank = out[-1]["rank"] if out and out[-1]["total"] == p["total"] else pos
        out.append(dict(p, position=pos, rank=rank))
    return out


def rank_entry(p, previous_rank=0):
    """0x44 ranking entry: +0 u32 rank (non-zero: FUN_006cd8a0 checks a block's first word),
    +8 u32 position (FUN_002f6b80 highlights the user's row with it), +0x10 owner friend code,
    +0x20 u16 points, +0x24 u16 location, +0x26 u8 wins, +0x27 u8 losses, +0x28 u32 previous rank
    (0 = no arrow), +0x2c u32 rank, +0x30 name (10 UTF-16 chars) (FUN_002f5624, FUN_005d4638)."""
    e = bytearray(RANK_ENTRY)
    struct.pack_into("<I", e, 0, p["rank"])
    struct.pack_into("<I", e, 8, p["position"])
    e[0x10:0x1C] = p["friend_code"].encode("ascii")[:12].ljust(12, b"\0")
    struct.pack_into("<H2xHBBII", e, 0x20, min(p["total"], 0xFFFF), p["location"], min(p["wins"], 255),
                     min(p["battles"] - p["wins"], 255), previous_rank, p["rank"])
    e[0x30:0x42] = p["name"][:0x12]
    return bytes(e)


def rank_block(players, previous=None):
    """0x808 block: 30 entries + 0x10 unknown bytes; previous: {friend_code: rank} for the arrows."""
    b = bytearray(RANK_BLOCK)
    for i, p in enumerate(players[:RANK_BLOCK_ENTRIES]):
        b[i * RANK_ENTRY:(i + 1) * RANK_ENTRY] = rank_entry(p, (previous or {}).get(p["friend_code"], 0))
    return bytes(b)


def write_user_result(b, at, p, players, contest):
    """23_UserPackData mode block (or its previous-contest copy at +0x1098): +0 u32 rank, +4 u32
    players, +8 u32 position, +0x10 u32 contest, +0x14 win, +0x18 popularity, +0x1c strength,
    +0x20 evaluation points, +0x24 battles, +0x28 wins (FUN_005b4a2c, FUN_005a4548, FUN_005cb584).
    Previous-contest copy only: +0x44 u16 3 = certificate + Network Coins at the end-of-contest
    announcement (FUN_005cb39c, FUN_005cb0ac), +0x48 u16 platinum, +0x4a gold, +0x4c silver,
    +0x4e bronze coins (FUN_002f84d0 -> FUN_0065baa0, MenuMessageNetworkCoinGet01..04)."""
    struct.pack_into("<III", b, at, p["rank"], players, p["position"])
    struct.pack_into("<I6I", b, at + 0x10, contest, p["win"], p["pop"], p["strength"], p["eval"],
                     p["battles"], p["wins"])


def champion_entry(p):
    """0x34 ChampionRecord entry (entry i at file + i*0x34, FUN_00602424): +0 unused (entry 0: the
    count), +8 u32 location, +0xc u32 points, +0x10 u8 wins, +0x11 u8 losses, +0x14 name
    (FUN_005d46a0)."""
    e = bytearray(CHAMPION_ENTRY)
    struct.pack_into("<IIBB", e, 8, p["location"], p["total"], min(p["wins"], 255), min(p["battles"] - p["wins"], 255))
    e[0x14:0x32] = p["name"][:0x1E]
    return bytes(e)


class Handler(BaseHTTPRequestHandler):
    store: Store = None
    public_dir: str = None
    private_templates_dir: str = None
    self_opponents = False  # also offer players their own team (testing with a single player)
    calendar: GpCalendar = None
    prize_champion = prize_top10 = 0  # item ids of the end-of-contest Special Present (0 = none)
    coins_champion = coins_top10 = None  # (bronze, silver, gold, platinum) Network Coins, None = none
    limit_rotation = True  # Challengers GP rules from LIMIT_RULE_SETS (False: public 018_LimitSetting.bin)
    timeout = 15  # seconds; a stuck read must not outlive the client's 60 s request timeout

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[sil] {self.client_address[0]} {fmt % args}\n")

    def do_POST(self):
        path = self.path.split("?", 1)[0].strip("/")
        prefix = APP_PATH + "/"
        if not path.startswith(prefix):
            self.send_error(404)
            return
        endpoint = path[len(prefix):]
        body = self._read_body()
        if body == b"\0":  # empty body sent as one dummy byte (make_url_patch.py --azahar)
            body = b""
        friend_code = self.headers.get("X-Sil-Friend-Code", "")
        token = self._session_token(friend_code)

        # v1.3 on Azahar sends the app path (00300701) here, not the silInit title code
        if self.headers.get("X-Sil-Title-Code") not in (TITLE_CODE, APP_PATH):
            self.log_message("unexpected title code %r", self.headers.get("X-Sil-Title-Code"))
        if token and endpoint.startswith("file/"):
            sent = self.headers.get("X-Sil-Digest", "")
            if sent != digest_hex(body, token):
                original = azahar_unsort(body, token, sent)
                if original is None:
                    dump = os.path.join(os.path.dirname(self.public_dir), f"digest_{endpoint.replace('/', '_')}.bin")
                    open(dump, "wb").write(body)
                    self.log_message("request digest mismatch for %s (%s), body saved to %s; token %s; headers: %s",
                                     friend_code, endpoint, dump, token.hex(), dict(self.headers))
                    self._reply({"Result": "INVALID_DATA"}, token)
                    return
                body = original

        try:
            fields = tlv_decode(body)
        except (struct.error, IndexError):
            dump = os.path.join(os.path.dirname(self.public_dir), f"bad_{endpoint.replace('/', '_')}.bin")
            open(dump, "wb").write(body)
            self.log_message("cannot decode %s body (%d bytes), saved to %s; headers: %s",
                             endpoint, len(body), dump, dict(self.headers))
            self._reply({"Result": "INVALID_DATA"}, None)
            return

        handler = ROUTES.get(endpoint)
        try:
            if handler is None:
                raise SilError("INTERNAL_ERROR")
            response = handler(self, fields, friend_code)
            response = {"Result": "OK", **response}
        except SilError as e:
            response = {"Result": e.result, **e.extra}
        file_name = fields.get("File-Name", b"").decode("ascii", "replace")
        self.log_message("%s %s%s -> %s %s", endpoint, friend_code or "-", f" [{file_name}]" if file_name else "",
                         response["Result"], {k: len(v) for k, v in response.items() if k != "Result"})
        # register/getnonce/login answer without a digest; the session token is (re)created by login
        self._reply(response, self._session_token(friend_code) if endpoint.startswith("file/") else None)

    def _read_body(self):
        # Azahar's http:C sends "Transfer-Encoding: chunked" together with Content-Length;
        # chunked wins (RFC 9112 6.3), otherwise the chunk-size line ends up in the TLV data.
        # With an empty body it sends Content-Length: 0 and no chunks at all (not even "0\r\n").
        length = int(self.headers.get("Content-Length", 0))
        if "chunked" not in self.headers.get("Transfer-Encoding", "").lower() or length == 0:
            return self.rfile.read(length)
        body = bytearray()
        while True:
            size = int(self.rfile.readline().split(b";", 1)[0].strip() or b"0", 16)
            if size == 0:
                while self.rfile.readline() not in (b"\r\n", b"\n", b""):  # trailers
                    pass
                return bytes(body)
            body += self.rfile.read(size)
            self.rfile.readline()  # CRLF after each chunk

    def _session_token(self, friend_code):
        rows = self.store.q("SELECT token FROM sessions WHERE friend_code = ?", friend_code)
        return rows[0][0] if rows and rows[0][0] else None

    def _reply(self, fields, token):
        body = tlv_encode(fields)
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        if token:
            self.send_header("X-Sil-Digest", digest_hex(body, token))
        self.end_headers()
        self.wfile.write(body)

    # nuser/*
    def register(self, fields, _friend_code):
        if len(fields.get("Authentication-Token", b"")) == 0:
            raise SilError("INVALID_DATA")
        # TODO: validate the Nintendo/Pretendo service token (account server) and map it to a PID,
        # so a friend code can be bound to one console. For now every register creates a new user.
        while True:
            friend_code = "".join(secrets.choice("0123456789") for _ in range(12))
            if not self.store.q("SELECT 1 FROM users WHERE friend_code = ?", friend_code):
                break
        self.store.q("INSERT INTO users (friend_code) VALUES (?)", friend_code)
        return {"Friend-Code": friend_code}

    def getnonce(self, _fields, friend_code):
        self._require_user(friend_code)
        nonce = secrets.token_bytes(16)
        self.store.q("INSERT INTO sessions (friend_code, nonce, token) VALUES (?, ?, NULL) "
                     "ON CONFLICT(friend_code) DO UPDATE SET nonce = excluded.nonce, token = NULL", friend_code, nonce)
        return {"Nonce": nonce}

    def login(self, fields, friend_code):
        self._require_user(friend_code)
        rows = self.store.q("SELECT nonce FROM sessions WHERE friend_code = ?", friend_code)
        if not rows or not rows[0][0]:
            raise SilError("INVALID_DATA")
        if fields.get("Digest") != hashlib.md5(rows[0][0] + KEY).digest():
            raise SilError("INVALID_DATA")
        token = secrets.token_bytes(16)
        self.store.q("UPDATE sessions SET nonce = NULL, token = ? WHERE friend_code = ?", token, friend_code)
        return {"Token": token}

    def _require_user(self, friend_code):
        if not friend_code or not self.store.q("SELECT 1 FROM users WHERE friend_code = ?", friend_code):
            raise SilError("USER_NOT_EXIST")

    def _require_session(self, friend_code):
        if not self._session_token(friend_code):
            raise SilError("INVALID_TOKEN")

    # file/*
    def upload(self, fields, friend_code):
        self._require_session(friend_code)
        name = fields.get("File-Name", b"").decode("ascii", "replace")
        # Private files always belong to the logged-in friend code (header), whatever the body says
        owner = friend_code
        if fields.get("Friend-Code", owner.encode()) != owner.encode():
            self.log_message("body Friend-Code differs from session %s", owner)
        data = fields.get("Data", b"")
        if not name:
            raise SilError("INVALID_DATA")

        if data == DOWNLOAD_CODE:  # "private download": return the stored file
            rows = self.store.q("SELECT data FROM private_files WHERE friend_code = ? AND name = ?", owner, name)
            data = rows[0][0] if rows else None
            if name in GP_PRIVATE_OPPONENT_FILES:
                data = self._opponent_pack(owner, GP_PRIVATE_OPPONENT_FILES[name]) or data
            elif name == GP_USER_PACK_FILE and self._registered(owner):
                data = self._user_pack(owner)
            if data is None:
                data = self._private_template(owner, name)
            if data is None:
                raise SilError("FILE_NOT_EXIST")
            return {"Add-Data-Size": struct.pack("<I", len(data)), "Add-Data": data}

        if name == "present_code.bin":  # exchange: code in, (package id, status) out
            package_id, status = self._redeem(data, owner)
            return {"Add-Data-Size": struct.pack("<I", 8), "Add-Data": struct.pack("<II", package_id, status)}

        if name in GP_RESULT_FILES and len(data) >= 0x10:
            (score,) = struct.unpack_from("<I", data, 0xC)
            self.store.q("INSERT INTO gp_results (friend_code, mode, score, data, day) VALUES (?, ?, ?, ?, ?)",
                         owner, GP_RESULT_FILES[name], score, data, self.calendar.today().isoformat())

        self.store.q("INSERT INTO private_files (friend_code, name, data) VALUES (?, ?, ?) "
                     "ON CONFLICT(friend_code, name) DO UPDATE SET data = excluded.data, updated = strftime('%s','now')",
                     owner, name, data)
        return {}

    def _private_template(self, friend_code, name):
        """Default private file (e.g. 23_UserPackData with the 'registered' byte set), only for
        users that registered to the Grand Prix; new users must get FILE_NOT_EXIST (= no data)."""
        path = os.path.join(self.private_templates_dir, os.path.basename(name))
        if not os.path.isfile(path) or not self._registered(friend_code):
            return None
        return open(path, "rb").read()

    def _registered(self, friend_code):
        return bool(self.store.q("SELECT 1 FROM private_files WHERE friend_code = ? AND name = ?",
                                 friend_code, GP_REGISTRATION_FILE))

    def _standings(self, mode, first, end):
        """Ranked players of the results counted for days [first, end): points summed over all
        their entries (one ticket = one entry of 3 rounds), name and location from 00_UserData."""
        players = {}
        for owner, data, user_data in self.store.q(
                "SELECT g.friend_code, g.data, u.data FROM gp_results g "
                "LEFT JOIN private_files u ON u.friend_code = g.friend_code AND u.name = ? "
                "WHERE g.mode = ? AND g.day >= ? AND g.day < ? ORDER BY g.id",
                GP_REGISTRATION_FILE, mode, first.isoformat(), end.isoformat()):
            if len(data) < RESULT_TEAM:
                continue
            user_data = user_data or bytes(0xC4)
            p = players.setdefault(owner, {
                "friend_code": owner, "name": user_data[0xC:0x30],
                "location": struct.unpack_from("<H", user_data, 4)[0],
                "total": 0, "win": 0, "pop": 0, "strength": 0, "eval": 0, "battles": 0, "wins": 0})
            for k, v in gp_result_totals(data).items():
                p[k] += v
        return rank_players(players.values())

    def _ranking_pack(self, mode):
        """089/139_*_Ranking_Pack: block 0 = this contest up to yesterday (with yesterday's ranks
        for the arrows), block 1 = final standings of the previous contest (its top ten is
        announced when a contest ends), blocks 2+loc = block 0 restricted to location loc_NNN."""
        day = self.calendar.today()
        n, idx = self.calendar.contest(day)
        first = self.calendar.first_day(n)
        blocks = [bytes(RANK_BLOCK)] * RANK_BLOCKS
        if idx > 0:
            now = self._standings(mode, first, day)
            before = self._standings(mode, first, day - datetime.timedelta(days=1)) if idx > 1 else []
            blocks[0] = rank_block(now, {p["friend_code"]: p["rank"] for p in before})
            for loc in range(RANK_BLOCKS - 2):
                local = rank_players(p for p in now if p["location"] == loc)
                if local:
                    local_before = rank_players(p for p in before if p["location"] == loc)
                    blocks[2 + loc] = rank_block(local, {p["friend_code"]: p["rank"] for p in local_before})
        if n >= 2:
            blocks[1] = rank_block(self._standings(mode, self.calendar.first_day(n - 1), first))
        return b"".join(blocks)

    def _champion_record(self, mode):
        """141/142_*_ChampionRecord: the winners of the finished contests, newest first (the client
        numbers them count, count-1, ...; contests nobody played are skipped), u32 count at +0."""
        n, _ = self.calendar.contest(self.calendar.today())
        entries = []
        for k in range(n - 1, 0, -1):
            final = self._standings(mode, self.calendar.first_day(k), self.calendar.first_day(k + 1))
            if final:
                entries.append(champion_entry(final[0]))
            if len(entries) == CHAMPION_MAX:
                break
        # the entries start at offset 0: the count overlays the (unused) first word of entry 0
        record = bytearray(b"".join(entries).ljust(CHAMPION_MAX * CHAMPION_ENTRY + 4, b"\0"))
        struct.pack_into("<I", record, 0, len(entries))
        return bytes(record)

    def _user_pack(self, friend_code):
        """23_UserPackData (0x2698): +0xb9 = 1 registered (else the client deletes its local GP
        data, FUN_003cacc4); per mode (+0x110 + mode*0x12c4) the user's result in this contest up
        to yesterday, the 10 ranking entries around them and their result in the previous contest."""
        b = bytearray(USER_PACK)
        b[0xB9] = 1
        day = self.calendar.today()
        n, idx = self.calendar.contest(day)
        first = self.calendar.first_day(n)
        # Special Present (+0xfc u16 type: 1 item id at +0xfe, 2 monster, 3 prize screen; FUN_003cb4b0,
        # FUN_003cae8c). The client gives it once per contest: its "received" flag is cleared when
        # Held N grows (FUN_003caaa8). Prize for the best rank in the previous contest (any mode).
        if n >= 2:
            ranks = [p["rank"] for mode in GP_MODES
                     for p in self._standings(mode, self.calendar.first_day(n - 1), first)
                     if p["friend_code"] == friend_code]
            item = (self.prize_champion if 1 in ranks else
                    self.prize_top10 if ranks and min(ranks) <= 10 else 0)
            if item:
                struct.pack_into("<HH", b, 0xFC, 1, item)
        for m, mode in enumerate(GP_MODES):
            base = USER_PACK_HEAD + m * USER_PACK_MODE
            now = self._standings(mode, first, day) if idx > 0 else []
            me = next((p for p in now if p["friend_code"] == friend_code), None)
            if me:
                write_user_result(b, base, me, len(now), n)
                start = max(0, min(me["position"] - 5, len(now) - 10))
                for i, p in enumerate(now[start:start + 10]):
                    at = base + USER_PACK_NEIGHBOURS + i * RANK_ENTRY
                    b[at:at + RANK_ENTRY] = rank_entry(p)
            if n >= 2:
                final = self._standings(mode, self.calendar.first_day(n - 1), first)
                me = next((p for p in final if p["friend_code"] == friend_code), None)
                if me:
                    write_user_result(b, base + USER_PACK_PREVIOUS, me, len(final), n - 1)
                    coins = self.coins_champion if me["rank"] == 1 else self.coins_top10 if me["rank"] <= 10 else None
                    if coins:  # end-of-contest certificate + Network Coins (bronze, silver, gold, platinum)
                        struct.pack_into("<H", b, base + USER_PACK_PREVIOUS + 0x44, 3)
                        struct.pack_into("<4H", b, base + USER_PACK_PREVIOUS + 0x48, *reversed(coins))
        return bytes(b)

    def _opponent_pack(self, friend_code, mode):
        """*_PrivateDlBattle built from the teams other players used in their last Grand Prix
        battle of this mode; rounds with no player team keep the public Def_DLBattle team.
        None (=> stored file or template, i.e. the client falls back to Def_DLBattle) when the
        user is not registered or there is no team to offer. Challengers GP teams only count from
        the current contest: earlier ones were built for other rules."""
        if not self._registered(friend_code):
            return None
        since = "0000-00-00"
        if mode == "limit":
            since = self.calendar.first_day(self.calendar.contest(self.calendar.today())[0]).isoformat()
        rows = self.store.q(
            "SELECT g.friend_code, g.data, u.data FROM gp_results g "
            "JOIN (SELECT friend_code, MAX(id) AS id FROM gp_results WHERE mode = ? AND day >= ? GROUP BY friend_code) last ON g.id = last.id "
            "LEFT JOIN private_files u ON u.friend_code = g.friend_code AND u.name = ?", mode, since, GP_REGISTRATION_FILE)
        own, pool = None, []
        for owner, result, user_data in rows:
            record = result[RESULT_TEAM:RESULT_TEAM + TEAM_RECORD]
            if team_strength(record) == 0:
                continue
            if owner == friend_code:
                own = team_strength(record)
                if not self.self_opponents:
                    continue
            pool.append((team_strength(record), make_team_block(owner, user_data or b"", record)))
        if not pool:
            return None
        if own is None:  # first battle: no team on record yet, aim at the middle of the pool
            own = sorted(s for s, _ in pool)[len(pool) // 2]
        path = os.path.join(self.public_dir, GP_DEF_OPPONENT_FILES[mode])
        default = open(path, "rb").read() if os.path.isfile(path) else b""
        default = default.ljust(ENTRIES * ROUNDS * TEAM_BLOCK, b"\0")
        out = bytearray()
        for e, teams in enumerate(pick_opponents(pool, own)):
            for r in range(ROUNDS):
                at = (e * ROUNDS + r) * TEAM_BLOCK
                out += teams[r] if r < len(teams) else default[at:at + TEAM_BLOCK]
        if not any(out[ROUNDS * TEAM_BLOCK:ROUNDS * TEAM_BLOCK + 0x10]):  # see make_team_block
            return None
        return bytes(out)

    def _redeem(self, data, friend_code):
        code = data.decode("utf-16-le", "replace").split("\0", 1)[0].strip().upper()
        rows = self.store.q("SELECT package_id, single_use FROM present_codes WHERE code = ?", code)
        if not rows:
            return 0, 2  # wrong code
        package_id, single_use = rows[0]
        if single_use and self.store.q("SELECT 1 FROM present_code_uses WHERE code = ? AND friend_code = ?", code, friend_code):
            return package_id, 1  # already used
        self.store.q("INSERT OR IGNORE INTO present_code_uses (code, friend_code) VALUES (?, ?)", code, friend_code)
        return package_id, 0

    def _public(self, fields):
        name = os.path.basename(fields.get("File-Name", b"").decode("ascii", "replace"))
        if name == GP_HELD_FILE:
            return name, self.calendar.held_record()
        if name == GP_LIMIT_FILE and self.limit_rotation:
            return name, limit_setting(self.calendar.contest(self.calendar.today())[0])
        if name == GP_LIMIT_NEWS_FILE and self.limit_rotation:  # Notizie -> ULTIME INFORMAZIONI
            _, text, theme = LIMIT_RULE_SETS[(self.calendar.contest(self.calendar.today())[0] - 1) % len(LIMIT_RULE_SETS)]
            return name, utf16_field(theme + "\n" + text, 0x600)
        if name in GP_RANKING_FILES:
            return name, self._ranking_pack(GP_RANKING_FILES[name])
        if name in GP_CHAMPION_FILES:
            return name, self._champion_record(GP_CHAMPION_FILES[name])
        path = os.path.join(self.public_dir, name)
        if name and os.path.isfile(path):
            return name, open(path, "rb").read()
        if name in DEFAULT_PUBLIC:
            return name, DEFAULT_PUBLIC[name]
        raise SilError("FILE_NOT_EXIST")

    def download(self, fields, friend_code):
        self._require_session(friend_code)
        name, data = self._public(fields)
        self.store.q("INSERT INTO downloads (name, count) VALUES (?, 1) "
                     "ON CONFLICT(name) DO UPDATE SET count = count + 1", name)
        return {"Data": data}

    def getproperties(self, fields, friend_code):
        self._require_session(friend_code)
        name, data = self._public(fields)
        rows = self.store.q("SELECT count FROM downloads WHERE name = ?", name)
        return {"File-Size": struct.pack("<I", len(data)),
                "Download-Count": struct.pack("<I", rows[0][0] if rows else 0),
                "Content-Code": hashlib.md5(data).digest()}


ROUTES = {
    "nuser/register": Handler.register,
    "nuser/getnonce": Handler.getnonce,
    "nuser/login": Handler.login,
    "file/upload": Handler.upload,
    "file/download": Handler.download,
    "file/getproperties": Handler.getproperties,
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8381)
    ap.add_argument("--data", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
    ap.add_argument("--self-opponents", action="store_true",
                    help="Grand Prix: also offer players their own last team as an opponent (single-player tests)")
    day = datetime.date.fromisoformat
    ap.add_argument("--gp-start", type=day, default=datetime.date(2026, 10, 26),
                    help="Grand Prix: first day of contest 1 (YYYY-MM-DD, default %(default)s)")
    ap.add_argument("--gp-days", type=int, default=7, help="Grand Prix: days per contest (1-7, default 7)")
    ap.add_argument("--gp-utc-offset", type=float,
                    help="Grand Prix: day boundary as hours from UTC (default: this computer's time zone; Japan = 9)")
    ap.add_argument("--gp-today", type=day, help="Grand Prix: pretend today is this date (testing)")
    # item ids = ItemMessage.mes keys I%04d (e.g. 60 Mini Medaglia, 66 Sfera di Luce, 70 Grande Sfera di Luce)
    ap.add_argument("--gp-prize-champion", type=int, default=70, metavar="ITEM",
                    help="Grand Prix: item id given to last contest's champions (default %(default)s, 0 = none)")
    ap.add_argument("--gp-prize-top10", type=int, default=66, metavar="ITEM",
                    help="Grand Prix: item id given to last contest's top ten (default %(default)s, 0 = none)")
    def coins(text):
        values = tuple(int(x) for x in text.split(","))
        if len(values) != 4 or not all(0 <= v <= 0xFFFF for v in values):
            raise argparse.ArgumentTypeError("expected BRONZE,SILVER,GOLD,PLATINUM")
        return values if any(values) else None
    ap.add_argument("--gp-coins-champion", type=coins, default=(0, 0, 3, 0), metavar="B,S,G,P",
                    help="Grand Prix: Network Coins for last contest's champions (default 0,0,3,0; 0,0,0,0 = none)")
    ap.add_argument("--gp-coins-top10", type=coins, default=(0, 3, 0, 0), metavar="B,S,G,P",
                    help="Grand Prix: Network Coins for last contest's top ten (default 0,3,0,0)")
    ap.add_argument("--gp-limit-static", action="store_true",
                    help="Grand Prix: serve DIR/public/018_LimitSetting.bin instead of the rule rotation")
    args = ap.parse_args()
    if not 1 <= args.gp_days <= 7:  # Held+0 indexes a 7-entry table
        ap.error("--gp-days must be 1..7")

    for sub in ("public", "private_templates"):
        os.makedirs(os.path.join(args.data, sub), exist_ok=True)
    Handler.store = Store(os.path.join(args.data, "sil.sqlite3"))
    Handler.public_dir = os.path.join(args.data, "public")
    Handler.private_templates_dir = os.path.join(args.data, "private_templates")
    Handler.self_opponents = args.self_opponents
    Handler.calendar = GpCalendar(args.gp_start, args.gp_days, args.gp_utc_offset, args.gp_today)
    Handler.store.date_gp_results(Handler.calendar)
    Handler.prize_champion, Handler.prize_top10 = args.gp_prize_champion, args.gp_prize_top10
    Handler.coins_champion, Handler.coins_top10 = args.gp_coins_champion, args.gp_coins_top10
    Handler.limit_rotation = not args.gp_limit_static
    n, idx = Handler.calendar.contest(Handler.calendar.today())
    print(f"SIL server on http://{args.host}:{args.port}/{APP_PATH}/ (data: {args.data}); "
          f"Grand Prix contest {n}, day {idx + 1}/{args.gp_days} ({Handler.calendar.today()})", flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
