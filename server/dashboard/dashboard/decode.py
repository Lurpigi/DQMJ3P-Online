"""Pure decoding of game records and competition calendars. Grand Prix scoring and calendar rules
come from server/sil/sil_server.py itself (loaded as a module, without starting its server), so the
portal cannot drift from what the game is served."""
import base64
import datetime
import hashlib
import hmac
import importlib.util
import struct
import sys
import unicodedata

UTC = datetime.timezone.utc
GP_MODES = ("grade", "limit")
LANGUAGES = ("en", "it", "es", "fr", "ja")

# ResultPack (re/notes/grandprix_formats.md 3.10)
RESULT_SIZE = 0x540
ROUND_SUMMARY, ROUND_SUMMARY_SIZE, ROUNDS = 0x14, 0x78, 3
RESULT_TEAM, MONSTER, TEAM_SLOTS = 0x17C, 0xF0, 4
# HMAC-SHA256 key of the round summaries (FUN_002f5fa0, re/tools/gp_files.py). The check follows the
# reverse engineering and has not been confirmed on real uploads: it is reported, never enforced.
RESULT_HMAC_KEY = struct.pack("<8I", 0x56C4A85F, 0x120A04C0, 0x838D9CB1, 0xF3C72986,
                              0xCA886FEB, 0xCA175817, 0x3316FDF5, 0x029ED65B)

# G-Cup (server/nex/nex/gcup_week.go, server/nex/sql/gcup_official_communities.sql)
GCUP_EPOCH = datetime.datetime(2015, 1, 5, tzinfo=UTC)
GCUP_CUPS = 12
GCUP_FPS = 30
GCUP_PRIZE_BANDS = [(r, r) for r in range(1, 11)] + [(11, 100)] + [(a, a + 99) for a in range(101, 1000, 100)] + [(1001, 10000)]


def load_sil(path):
    """server/sil/sil_server.py as a module (its server only starts from main())."""
    spec = importlib.util.spec_from_file_location("sil_server_portal", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("sil_server_portal", module)
    spec.loader.exec_module(module)
    return module


# --- text -----------------------------------------------------------------------------------
def clean_name(text, limit=24):
    """Player-provided names as plain text: NFC, no control/format characters, trimmed."""
    text = unicodedata.normalize("NFC", text)
    text = "".join(" " if unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") else c for c in text)
    return " ".join(text.split())[:limit]


def utf16_name(data, limit=18):
    units = []
    for i in range(0, len(data) - 1, 2):
        (u,) = struct.unpack_from("<H", data, i)
        if u == 0:
            break
        units.append(u)
    return clean_name(struct.pack(f"<{len(units)}H", *units).decode("utf-16-le", "replace"), limit)


def search_key(name):
    return unicodedata.normalize("NFKC", name).casefold().strip()


def public_id(salt, server_id, namespace, source_id):
    """Opaque, stable public id: rebuilding the portal keeps every permanent link."""
    digest = hmac.new(salt.encode(), f"{server_id}|{namespace}|{source_id}".encode(), hashlib.sha256).digest()
    return "p" + base64.b32encode(digest).decode().lower()[:12]


# --- Grand Prix -----------------------------------------------------------------------------
def gp_result(sil, data):
    """Decoded GP entry: points (as the SIL standings count them), three round summaries, team.
    None for a payload too short for the standings (the SIL server skips those too)."""
    if len(data) < RESULT_TEAM:
        return None
    totals = sil.gp_result_totals(data)
    rounds, signatures = [], []
    for i in range(ROUNDS):
        s = data[ROUND_SUMMARY + i * ROUND_SUMMARY_SIZE:ROUND_SUMMARY + (i + 1) * ROUND_SUMMARY_SIZE]
        header = s[0x24:0x40]
        opponent_code = header[:12].decode("ascii", "replace") if header[:12].isdigit() else None
        win, = struct.unpack_from("<I", s, 0x44)
        pop, strength, evaluation = struct.unpack_from("<3H", s, 0x48)
        rounds.append({"idx": i, "opponent_name": utf16_name(s[:0x24]), "opponent_code": opponent_code,
                       "won": True if s[0x40] == 1 else None,
                       "points_win": win, "points_pop": pop, "points_strength": strength, "points_eval": evaluation})
        signatures.append(hmac.compare_digest(hmac.new(RESULT_HMAC_KEY, s[:0x58], hashlib.sha256).digest(), s[0x58:0x78]))
    team = []
    record = data[RESULT_TEAM:RESULT_TEAM + TEAM_SLOTS * MONSTER]
    for slot in range(TEAM_SLOTS):
        m = record[slot * MONSTER:(slot + 1) * MONSTER]
        if len(m) < MONSTER:
            break
        (species,) = struct.unpack_from("<h", m, 0x1C)
        if species <= 0:
            continue
        hp, mp, _hp, _mp, atk, dfn, agi, wis = struct.unpack_from("<8h", m, 0x1E)
        team.append({"slot": slot, "species": species, "level": m[0x3C],
                     "hp": hp, "mp": mp, "atk": atk, "def": dfn, "agi": agi, "wis": wis})
    return {"totals": totals, "rounds": rounds, "team": team,
            "signature": "valid" if all(signatures) else "invalid",
            "complete": len(data) >= RESULT_SIZE}


class GpCalendarVersion:
    """One row of SIL gp_calendars: contest N of `mode` runs [starts_at, ends_at) in UTC."""

    def __init__(self, sil, row):
        self.id = row["id"]
        self.version = f"cal{row['id']}"
        self.offset_hours = row["utc_offset"] if row["utc_offset"] is not None else 0.0
        self.tz = datetime.timezone(datetime.timedelta(hours=self.offset_hours))
        self.start = datetime.date.fromisoformat(row["start"])
        self.calendar = sil.GpCalendar(self.start, row["days"], self.offset_hours)
        self.days = row["days"]
        self.first_used = datetime.datetime.fromtimestamp(row["first_used"], UTC)
        self.config = row["config"] or {}

    def day_of(self, moment):
        return moment.astimezone(self.tz).date()

    def contest(self, day):
        return self.calendar.contest(day)[0]

    def bounds(self, n):
        first = self.calendar.first_day(n)
        start = datetime.datetime.combine(first, datetime.time(), self.tz).astimezone(UTC)
        return start, start + datetime.timedelta(days=self.days)

    def edition_id(self, mode, n):
        return f"gp-{mode}-{self.version}-n{n}"


def gp_rules(sil, mode, n, config):
    if mode == "grade":
        return {"kind": "open"}
    if not config.get("limit_rotation", True):
        return {"kind": "static"}  # served from a file the portal cannot read
    rules, text, theme = sil.LIMIT_RULE_SETS[(n - 1) % len(sil.LIMIT_RULE_SETS)]
    split = lambda t: dict(zip(sil.LANGUAGES, t.split("\n")))
    return {"kind": "limit", "rules": [{"type": t, "value": v} for t, v in rules],
            "text": split(text), "theme": split(theme)}


def gp_rewards(config):
    coins = lambda c: dict(zip(("bronze", "silver", "gold", "platinum"), c)) if c else None
    return {"champion": {"item": config.get("prize_champion") or None, "coins": coins(config.get("coins_champion"))},
            "top10": {"item": config.get("prize_top10") or None, "coins": coins(config.get("coins_top10"))}}


# --- G-Cup ----------------------------------------------------------------------------------
def gcup_week(moment):
    return int((moment - GCUP_EPOCH).total_seconds() // (7 * 86400))


def gcup_bounds(week):
    start = GCUP_EPOCH + datetime.timedelta(weeks=week)
    return start, start + datetime.timedelta(weeks=1)


def gcup_definition(buffer):
    """The 0x1b0-byte application buffer of an official G-Cup community (cup rules and prizes)."""
    if not buffer or len(buffer) < 0xEC:
        return {}
    allowed = []
    for i in range(50):
        (s,) = struct.unpack_from("<H", buffer, 0x0A + i * 2)
        if s == 0:
            break
        allowed.append(s)
    prizes = []
    for i, (low, high) in enumerate(GCUP_PRIZE_BANDS):
        platinum, gold, silver, bronze = buffer[0x96 + i * 4:0x9A + i * 4]
        if platinum or gold or silver or bronze:
            prizes.append({"from": low, "to": high, "coins": {"platinum": platinum, "gold": gold,
                                                              "silver": silver, "bronze": bronze}})
    return {"name": utf16_name(buffer[0x6E:0x90], 16),
            "cpu": [s for s in struct.unpack_from("<3H", buffer, 0x04) if s],
            "allowed_species": allowed, "strength": buffer[0x90],
            "course": {"map": buffer[0x92], "variant": buffer[0x93]},
            "event": buffer[0x94], "prizes": prizes}


def gcup_team_name(data):
    return utf16_name(data or b"", 10)
