#!/usr/bin/env python3
"""gp_files.py - generate default SIL "Ranking Battle / Grand Prix" public files
for Dragon Quest Monsters Joker 3 Professional (code.bin v1.3).

Usage:  python -I gp_files.py OUTDIR [options]
        python -I gp_files.py --selftest [ROMFS_DATA_DIR]

Formats are documented in re/notes/grandprix_formats.md.  Every layout choice that
is NOT proven by the client code is marked GUESS in the comments below.

Stdlib only (struct, hmac, hashlib, datetime, argparse).
"""
import argparse
import datetime
import hashlib
import hmac
import os
import struct
import sys

# --------------------------------------------------------------------------
# Public file sizes (fixed client buffers, see sil_RankingDownloadTables 0x41fe68)
# --------------------------------------------------------------------------
PUBLIC_FILES = {
    "001_Server_Status.bin": 0x8,
    "003_Held_Record.bin": 0x14,
    "600_CorrectPointTable.bin": 0x28,
    "008_PopularTbl.bin": 0x58,
    "009_WinPointTable.bin": 0x54,
    "029W_EvaluationPoint.bin": 0x3E,
    "018_LimitSetting.bin": 0x848,
    "144_Grade_Popular.bin": 0x7FE,
    "032_Grade_DLNewsMsg.bin": 0x600,
    "033_Limit_DLNewsMsg.bin": 0x600,
    "089_Grade_Ranking_Pack.bin": 0x19998,
    "139_Limit_Ranking_Pack.bin": 0x19998,
    "141_Grade_ChampionRecord.bin": 0x1454,
    "142_Limit_ChampionRecord.bin": 0x1454,
    "147_Grade_Def_DLBattle.bin": 0x297C,
    "148_Limit_Def_DLBattle.bin": 0x297C,
    "171_Grade_Other_Countries.bin": 0xDD4,
}
# private (per Friend-Code) downloads, tipo 0 "Download_Code"; all optional on the server
PRIVATE_FILES = {
    "23_UserPackData.bin": 0x2698,
    "PrivateSCRegister.bin": 4,
    "09_Grade_PrivateDlBattle.bin": 0x297C,
    "18_Limit_PrivateDlBattle.bin": 0x297C,
    "28W_Grade_Other_Countries.bin": 0x938,
}

TEAM_BLOCK = 0x49C      # one opponent "team" (header 0xd8 + 4 monsters*0xf0 + 4)
ENTRY_SIZE = 0xDD4      # 3 team blocks
MONSTER_SIZE = 0xF0
RANK_ENTRY = 0x44       # ranking pack entry
RANK_BLOCK = 0x808      # 30 entries * 0x44 + 0x10
N_BLOCKS = 51           # 2 global + 49 location blocks (client iterates loc 0..46)

# HMAC key used by the client for the 0x78 team summary inside ResultPack (0x2f5fa0)
RESULT_HMAC_KEY = struct.pack("<8I", 0x56C4A85F, 0x120A04C0, 0x838D9CB1, 0xF3C72986,
                              0xCA886FEB, 0xCA175817, 0x3316FDF5, 0x029ED65B)
# HMAC-SHA256 key (index 1) used to sign PresentCodePackage*.bin (verified on all 115 RomFS packages)
PRESENT_KEY_B = bytes.fromhex(
    "21dc24dd6a48fde68c934832a87b1762b522031cadf4f53f9e21ea8eed3ccc2d")


def u16s(s, nbytes):
    """UTF-16LE string padded/truncated to nbytes (NUL padded)."""
    b = s.encode("utf-16le")[:nbytes - 2]
    return b + b"\0" * (nbytes - len(b))


# --------------------------------------------------------------------------
# Small tables
# --------------------------------------------------------------------------
def make_status(state=0, tickets=7):
    """001_Server_Status.bin (8).  byte0: 0 open, 1/2 reception closed, 3 anomaly, 4 not open [CERTO].
    byte4: number of participation tickets per week [PROBABILE: read as *(R+8) in FUN_00572a60]."""
    b = bytearray(8)
    b[0] = state
    b[4] = tickets
    return bytes(b)


def make_held(date, contest_no, weekday_idx=None, final_flag=0):
    """003_Held_Record.bin (0x14).
    +0 u32 index into CorrectPointTable (0..6)            [CERTO as index, meaning GUESS = weekday]
    +4 u16 year, +6 u8 month, +7 u8 day (contest date)    [CERTO: compared with save+0x3d0]
    +8 u32 flag (0 = normal; selects ranking block A/B)   [PROBABILE]
    +0xc u32 contest number N (>=1)                       [CERTO: compared with save rec +0x3c8]
    +0x10 u32 unknown (0)"""
    if weekday_idx is None:
        weekday_idx = date.weekday()          # GUESS
    return struct.pack("<IHBBIII", weekday_idx, date.year, date.month, date.day,
                       final_flag, contest_no, 0)


def make_correct_point():
    """600_CorrectPointTable.bin (0x28): float[7] (index = Held+0) then float[3] (index = chosen
    opponent 0..2).  Values = multipliers applied to the battle points [CERTO structure, values GUESS]."""
    return struct.pack("<10f", 1, 1, 1, 1, 1, 1, 1, 1.0, 1.5, 2.0)


def make_win_point():
    """009_WinPointTable.bin (0x54) = u32[21]: 10 (threshold, points) pairs ascending (strength
    difference opponent-player), then u32 base win points at +0x50 [CERTO structure, values GUESS]."""
    pairs = [(50, 10), (100, 20), (200, 30), (400, 40), (800, 50),
             (1600, 60), (3200, 70), (6400, 80), (12800, 90), (25600, 100)]
    flat = [v for p in pairs for v in p] + [100]
    return struct.pack("<21I", *flat)


def make_evaluation():
    """029W_EvaluationPoint.bin (0x3e) = u16[31]: [0..10] points by battle length/turn index,
    [11..20] bonus by remaining-HP ratio bucket, [21..30] bonus by second ratio bucket
    [PROBABILE structure (FUN_002f6298), values GUESS]."""
    a = [200, 180, 160, 140, 120, 100, 80, 60, 40, 20, 0]
    b = [0, 10, 20, 30, 40, 50, 60, 70, 80, 100]
    c = [0, 5, 10, 15, 20, 25, 30, 35, 40, 50]
    return struct.pack("<31H", *(a + b + c))


def make_popular_tbl():
    """008_PopularTbl.bin (0x58): 2 modes * 11 (u16 avg_popularity_threshold, u16 points); the scan
    stops at the first pair with points==0 [CERTO (FUN_002f6980)], values GUESS."""
    one = b""
    for i in range(11):
        one += struct.pack("<HH", 1000 * (i + 1), max(0, 110 - 10 * i))
    return one + one


def make_popular(value=5000):
    """144_Grade_Popular.bin (0x7fe) = u16[1023] popularity by species id, shown if <= 10000
    [CERTO: FUN_0065e598].  Constant default (GUESS)."""
    return struct.pack("<1023H", *([value] * 1023))


LIMIT_RULE_NONE = 9


def make_limit_setting(rules=(), text="Limit rules: no restrictions.", theme="Theme: free-for-all!"):
    """018_LimitSetting.bin (0x848): +0 3 rules (u32 type, u32 value), checked on every monster of
    the team by FUN_002f7e9c [CERTO]. Types:
      0 size (FUN_006bfe90: species size, or 0..4 from traits 0x46..0x4a; value 0 also accepts 1)
      1 species-table byte +0x23 (FUN_00661088; family [PROBABILE])
      4 rank class (FUN_006bfdec: species rank 1..8, raised by level: 25-49 -> 4, 50-99 -> 6, 100 -> 8)
      5 team grade cap: grade (FUN_002473c0: 1..8 for strength <4000, <8000, <12000, <18000,
        <32000, <46000, <74000, more) of the summed team strength (FUN_00247444) must be <= value
      9 no rule; any other type rejects every team
    +0x18 UTF-16LE rule text (0x520 B) [PROBABILE], +0x538 UTF-16LE theme announcement (0x310 B)
    [PROBABILE: FUN_006cd6c4 = R+0x9608]."""
    rules = list(rules)[:3]
    rules += [(LIMIT_RULE_NONE, 0)] * (3 - len(rules))
    b = bytearray(0x848)
    for i, (kind, value) in enumerate(rules):
        struct.pack_into("<II", b, i * 8, kind, value)
    b[0x18:0x18 + 0x520] = u16s(text, 0x520)
    b[0x538:0x538 + 0x310] = u16s(theme, 0x310)
    return bytes(b)


def make_news(text):
    """0x0xx_*_DLNewsMsg.bin (0x600): UTF-16LE text [INCERTO: consumer not located]."""
    return u16s(text, 0x600)


# --------------------------------------------------------------------------
# Monsters / opponent teams
# --------------------------------------------------------------------------
def make_monster(species=1, level=10, hp=100, mp=30, atk=50, dfn=50, agi=50, wis=50):
    """0xf0 save-format monster record.  Only the fields proven by the client are set:
    +0x1c s16 species [CERTO], +0x1e HP, +0x20 MP, +0x22/+0x24 current HP/MP, +0x26 ATK,
    +0x28 DEF, +0x2a AGI, +0x2c WIS (s16) [PROBABILE], +0x3c u8 level [PROBABILE].
    Everything else (skills at +0x44.., traits, name at +0x72?, ...) is zero: GUESS that the
    battle engine tolerates it.  Prefer real records (see server logic in the notes)."""
    b = bytearray(MONSTER_SIZE)
    struct.pack_into("<h", b, 0x1C, species)
    struct.pack_into("<6h", b, 0x1E, hp, mp, hp, mp, atk, dfn)
    struct.pack_into("<hh", b, 0x2A, agi, wis)
    b[0x3C] = level
    return bytes(b)


def make_team_record(monsters):
    """0x3c4 = 4 * 0xf0 monsters + 4 trailer bytes (same as save ranking record [0:0x3c4])."""
    ms = list(monsters)[:4]
    ms += [bytes(MONSTER_SIZE)] * (4 - len(ms))
    return b"".join(ms) + bytes(4)


def make_team_block(name, monsters, mii=None):
    """0x49c opponent team block (re/notes/grandprix_formats.md 3.8).
    +0x00 owner id (0 here; Def_DLBattle is never checked)  +0x14 u16 location loc_NNN (0 = Japan,
    Hokkaido)  +0x18 u32 counter  +0x20 name UTF-16LE 0x24 B  +0x44 u8 beginner mark
    +0x45 u8 has-Mii flag  +0x46 u32  +0x4a 5 profile bytes  +0x50 Mii 0x88 B (only if +0x45 != 0)
    +0xd8 team record 0x3c4 [CERTO]. The server builds real ones in sil_server.make_team_block."""
    b = bytearray(TEAM_BLOCK)
    b[0x20:0x44] = u16s(name, 0x24)
    if mii:
        b[0x45] = 1
        b[0x50:0x50 + len(mii[:0x88])] = mii[:0x88]
    b[0xD8:0xD8 + 0x3C4] = make_team_record(monsters)
    return bytes(b)


def make_default_entry(label, base_level):
    """One 'opponent' = 3 team blocks."""
    teams = []
    for t in range(3):
        mons = [make_monster(1, base_level + t, 60 + 10 * base_level, 20 + 2 * base_level,
                             30 + 5 * base_level, 30 + 5 * base_level,
                             30 + 5 * base_level, 30 + 5 * base_level) for _ in range(4)]
        teams.append(make_team_block("%s%d" % (label, t + 1), mons))
    return b"".join(teams)


def make_def_dlbattle(levels=(16, 12, 8)):
    """147/148_*_Def_DLBattle.bin (0x297c) = 3 entries in menu order: hard / similar / easy
    (FUN_005b8d24 rows, CERTO from the in-game menu)."""
    return b"".join(make_default_entry("CPU", lv) for lv in levels)


# --------------------------------------------------------------------------
# Ranking pack / champion
# --------------------------------------------------------------------------
def make_rank_entry(rank, score, name, pref=0):
    """0x44 ranking entry.  CERTO: +0x20 u16 score; +0x24 u16, +0x26 u8, +0x27 u8, +0x28 u32,
    +0x2c u32, +0x30 name UTF-16LE (0x14 B).  Semantics of 0x24..0x2c (rank? points?) GUESS."""
    e = bytearray(RANK_ENTRY)
    struct.pack_into("<H", e, 0x20, score)
    struct.pack_into("<I", e, 0x28, score)
    struct.pack_into("<I", e, 0x2C, rank)
    e[0x30:0x44] = u16s(name, 0x14)
    return bytes(e)


def make_rank_block(entries):
    b = bytearray(RANK_BLOCK)
    for i, e in enumerate(entries[:30]):
        b[i * RANK_ENTRY:(i + 1) * RANK_ENTRY] = e
    return bytes(b)


def make_ranking_pack(demo=False):
    """089/139_*_Ranking_Pack.bin (0x19998) = 51 blocks of 0x808: [0] overall, [1] previous-day /
    secondary list, [2..50] per location (loc_000..046 used by the client) [CERTO sizes, PROBABILE roles]."""
    blocks = [bytes(RANK_BLOCK)] * N_BLOCKS
    if demo:
        ents = [make_rank_entry(i + 1, 1000 - 20 * i, "Player%02d" % (i + 1)) for i in range(30)]
        blocks[0] = blocks[1] = make_rank_block(ents)
    return b"".join(blocks)


def make_champion(count=0):
    """141/142_*_ChampionRecord.bin (0x1454): u32 count, then entries of 0x34 [INCERTO]."""
    b = bytearray(0x1454)
    struct.pack_into("<I", b, 0, count)
    return bytes(b)


# --------------------------------------------------------------------------
# Present code package (PresentCodePackageS%02u.bin / R%03d.bin)
# --------------------------------------------------------------------------
def make_present_package(pkg_id, item_id=0x2E, count=1, key_index=1):
    """type 2 (item) package, 0x48 bytes, signed HMAC-SHA256(KEY_B, data[:-32]) [CERTO,
    reproduces RomFS R003 byte-for-byte; see --selftest]."""
    body = struct.pack("<4sIIIIIII", b"BPCP", 0x1000, pkg_id, 2, key_index, 0, 0, 0)
    body += struct.pack("<hhI", item_id, count, 0)
    return body + hmac.new(PRESENT_KEY_B, body, hashlib.sha256).digest()


# --------------------------------------------------------------------------
def build_all(outdir, date, contest, state, tickets, demo, limit=None, only=None):
    """limit: make_limit_setting keyword arguments; only: names of the files to write (default all)."""
    os.makedirs(outdir, exist_ok=True)
    files = {
        "001_Server_Status.bin": make_status(state, tickets),
        "003_Held_Record.bin": make_held(date, contest),
        "600_CorrectPointTable.bin": make_correct_point(),
        "008_PopularTbl.bin": make_popular_tbl(),
        "009_WinPointTable.bin": make_win_point(),
        "029W_EvaluationPoint.bin": make_evaluation(),
        "018_LimitSetting.bin": make_limit_setting(**(limit or {})),
        "144_Grade_Popular.bin": make_popular(),
        "032_Grade_DLNewsMsg.bin": make_news("Grade Ranking Battle is open! Good luck!"),
        "033_Limit_DLNewsMsg.bin": make_news("Limit Ranking Battle is open! Good luck!"),
        "089_Grade_Ranking_Pack.bin": make_ranking_pack(demo),
        "139_Limit_Ranking_Pack.bin": make_ranking_pack(demo),
        "141_Grade_ChampionRecord.bin": make_champion(),
        "142_Limit_ChampionRecord.bin": make_champion(),
        "147_Grade_Def_DLBattle.bin": make_def_dlbattle(),
        "148_Limit_Def_DLBattle.bin": make_def_dlbattle((18, 14, 10)),
        "171_Grade_Other_Countries.bin": bytes(0xDD4),
        "PresentCodePackageS01.bin": None,
    }
    if only:
        unknown = set(only) - set(files)
        if unknown:
            raise ValueError("unknown file(s): %s" % ", ".join(sorted(unknown)))
        files = {k: v for k, v in files.items() if k in only}
    present = "PresentCodePackageS01.bin" in files
    files.pop("PresentCodePackageS01.bin", None)
    for name, data in files.items():
        assert len(data) == PUBLIC_FILES[name], (name, len(data), PUBLIC_FILES[name])
        with open(os.path.join(outdir, name), "wb") as f:
            f.write(data)
    if not present:
        return list(files)
    # present-code package S01 (item 0x2e x1), package ids are chosen by the server's
    # present_code.bin answer
    with open(os.path.join(outdir, "PresentCodePackageS01.bin"), "wb") as f:
        f.write(make_present_package(1))
    return list(files) + ["PresentCodePackageS01.bin"]


def build_private_template(outdir):
    """Templates for per-user private files (server should serve them for Download_Code requests)."""
    pdir = os.path.join(outdir, "private_template")
    os.makedirs(pdir, exist_ok=True)
    upd = bytearray(0x2698)
    upd[0xB9] = 1                      # UserPackData+0xb9 != 0 : 'registered on server'
    out = {
        "23_UserPackData.bin": bytes(upd),
        "PrivateSCRegister.bin": bytes(4),
        "09_Grade_PrivateDlBattle.bin": bytes(0x297C),   # all-zero => client falls back to Def_DLBattle
        "18_Limit_PrivateDlBattle.bin": bytes(0x297C),
        "28W_Grade_Other_Countries.bin": bytes(0x938),
    }
    for k, v in out.items():
        assert len(v) == PRIVATE_FILES[k]
        with open(os.path.join(pdir, k), "wb") as f:
            f.write(v)


def selftest(romfs):
    ok = True
    pkg = make_present_package(3, 0x2E, 1)
    if romfs:
        p = os.path.join(romfs, "PresentCode", "Package", "PresentCodePackageR003.bin")
        if os.path.exists(p):
            ref = open(p, "rb").read()
            ok = ref == pkg
            print("R003 reproduced byte-for-byte:", ok)
    assert len(make_def_dlbattle()) == 0x297C
    assert len(make_ranking_pack(True)) == 0x19998
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("outdir", nargs="?")
    ap.add_argument("--date", help="contest date YYYY-MM-DD (default: today JST)")
    ap.add_argument("--contest", type=int, default=1, help="contest number N (>=1)")
    ap.add_argument("--state", type=int, default=0, help="server status byte (0=open)")
    ap.add_argument("--tickets", type=int, default=7)
    ap.add_argument("--demo-ranking", action="store_true")
    ap.add_argument("--limit-rule", action="append", default=[], metavar="TYPE:VALUE",
                    help="Challengers GP rule (up to 3; types in make_limit_setting), e.g. 5:6")
    ap.add_argument("--limit-text", help="Challengers GP rule description shown in game")
    ap.add_argument("--limit-theme", help="Challengers GP theme announcement")
    ap.add_argument("--only", action="append", metavar="FILE", help="write only these files")
    ap.add_argument("--private-template", action="store_true")
    ap.add_argument("--selftest", nargs="?", const="", metavar="ROMFS_DATA_DIR")
    a = ap.parse_args(argv)
    if a.selftest is not None:
        return 0 if selftest(a.selftest or None) else 1
    if not a.outdir:
        ap.error("outdir required")
    if a.date:
        d = datetime.date.fromisoformat(a.date)
    else:
        d = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)).date()
    if len(a.limit_rule) > 3:
        ap.error("at most 3 --limit-rule")
    limit = {"rules": [tuple(int(x, 0) for x in r.split(":")) for r in a.limit_rule]}
    if a.limit_text is not None:
        limit["text"] = a.limit_text
    if a.limit_theme is not None:
        limit["theme"] = a.limit_theme
    names = build_all(a.outdir, d, a.contest, a.state, a.tickets, a.demo_ranking, limit, a.only)
    if a.private_template:
        build_private_template(a.outdir)
    for n in names:
        print("%-34s %7d" % (n, os.path.getsize(os.path.join(a.outdir, n))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
