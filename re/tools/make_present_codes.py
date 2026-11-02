"""Build server/sil/present_codes.json: the original DQMJ3 / DQMJ3P present codes and their gifts.

Sources (re/notes/present_codes.md):
  - the game's code table data/PresentCode/PresentCodeROMCode.bin (AES-128-CTR, Shift-JIS) and the
    packages data/PresentCode/Package/PresentCodePackageR%03d.bin, from the RomFS and the update RomFS;
  - the code list of game8.jp/dqmj3pro/122320 for the base game codes that DQMJ3P left out of the
    table (A/B/C codes) or replaced with its own (R026-R036, R050-R064, R080-R083).

Each gift also gets a Latin-letter alias: the keyboard of the fan translations has no kana or digits.

usage (python -I, needs pycryptodome): make_present_codes.py ROMFS UPDATE_ROMFS [-o OUT]
"""
import argparse
import json
import os
import re
import struct
import sys

from Crypto.Cipher import AES
from Crypto.Util import Counter

ROMCODE_KEY = bytes.fromhex("90bc1182e5aaf96d55752cf7be4bfcd9")
ROMCODE_IV = bytes.fromhex("d0733b8cdbdbc0e3a9c6950ef8025561")
PACKAGE_BASE = 200  # server package number = 200 + table id, 300 + game8 number for replaced codes

# Base game codes from game8 (number, code, item, count). 001-025 are still in the DQMJ3P table.
BASE_CODES = [
    (26, "A5OD9GVZCG", 110, 1), (27, "AIHQ877TI9", 111, 1), (28, "AFEFBGNF9B", 112, 1),
    (29, "A1DE9P93TR", 113, 1), (30, "AKZDN58BXE", 114, 1), (31, "AVI3OFS03A", 131, 1),
    (32, "AC18KC0UJA", 132, 1), (33, "AS9JJZ34C4", 133, 1), (34, "AM8ASATB0T", 134, 1),
    (35, "AEHES9V2NC", 151, 1), (36, "AL58BPW1CX", 152, 1),
    (37, "A6TVP4JB7L", None, None), (38, "AV1GDUARXV", None, None), (39, "AUKMYQY4HW", None, None),
    (40, "AKRH853GV4", None, None), (41, "A2EYYOD4HF", None, None), (42, "AN1ZSOMATM", None, None),
    (43, "ARC3FJ7J58", None, None), (44, "A5ULVBV5UC", None, None), (45, "AZP2W202ZC", None, None),
    (46, "A4AVDVI89Y", None, None), (47, "ARHB4ZMVIB", None, None), (48, "A6ETWNXDL7", None, None),
    (49, "AAJAJJG95T", None, None),
    (50, "APR4I5W2HK", 66, 5), (51, "ADAE04QYPL", 36, 3), (52, "A92I1XY8J3", 36, 3),
    (53, "AOOPFWGT61", 37, 3), (54, "A29CV7ATUH", 37, 3), (55, "ACWHU6GVTN", 38, 3),
    (56, "A5C8EJRSEK", 38, 3), (57, "AT5U8KF1WZ", 39, 3), (58, "AJ21PY9F9D", 39, 3),
    (59, "ARMFXSTXQC", 40, 3), (60, "ARBRZTVNVX", 40, 3), (61, "AAM439CHR5", 41, 3),
    (62, "A687D3RC1C", 41, 3), (63, "ACDUQN5PE9", 42, 3), (64, "AO0QVAODYJ", 42, 3),
    (65, "ASBG027Q52", None, None), (66, "AGOKV0NZCL", None, None), (67, "AEB23X9YC4", None, None),
    (68, "A2X153K9SG", None, None), (69, "A3JZONNQS9", None, None), (70, "A8PV6YFGTR", None, None),
    (71, "AI6Z641616", None, None), (72, "AE7OWJA8R9", None, None), (73, "AKTU23CDDC", None, None),
    (74, "A6CSJKTN3W", None, None), (75, "AUMIVQ22XW", None, None),
    (76, "Bンドぼぢモニい", None, None), (77, "Bドっッケゥワッ", None, None), (78, "Bぜオヨニならハ", None, None),
    (79, "Bせやきれゆリト", None, None), (80, "Bぴぶたえでまヅ", 68, 3), (81, "Bゃウヤきてろプ", 68, 3),
    (82, "Bピグづッじはレ", 42, 1), (83, "Bォゥポむニブぞ", 43, 1), (84, "Bきてヨはもゆざ", None, None),
    (85, "Bドパふてぽもぽ", None, None), (86, "Bヒモらぱゆドゼ", None, None), (87, "Bダぶぎねラけブ", None, None),
    (88, "Bほきポザれヅヌ", None, None), (89, "Bラぶポネフモに", None, None), (90, "Bイスこコツばつ", None, None),
    (91, "Cでゆあぞづ", None, None), (92, "Cヅオナダヅ", None, None), (93, "C鳥炎木士長", None, None),
    (94, "CRPBPU", None, None), (95, "Chkkri", None, None), (96, "C5/2↑～", None, None),
    (97, "Cツりヲデキ", None, None), (98, "C曹闘ホぉ少", None, None), (99, "Cりこせぬわ", None, None),
    (100, "Cじだめてつ", None, None),
]
# * Items None: the DQMJ3P package with the same number still holds the base game gift

DISC_NAMES = {1: ("スライムゴールドのMAP", "GOLDSLIMEDISC"), 2: ("メタルスライムのMAP", "METALSLIMEDISC"),
              36: ("プチットⅧ", "CHIBIEIGHTSDISC")}
COUNT_WORDS = {1: "ONE", 3: "THREE", 5: "FIVE", 10: "TEN", 20: "TWENTY", 99: "NINETYNINE", 100: "HUNDRED"}
ALIAS_MAX = 21


def rom_codes(path):
    data = open(path, "rb").read()
    counter = Counter.new(128, initial_value=int.from_bytes(ROMCODE_IV, "big"))
    text = AES.new(ROMCODE_KEY, AES.MODE_CTR, counter=counter).decrypt(data).decode("cp932")
    return {int(i): c for i, c in re.findall(r'id\s*=\s*(\d+)\s*code\s*=\s*"([^"]*)"', text)
            if not c.startswith("熙")}


def item_names(translation):
    names = {}
    for lang, paths in (("ja", ["jp"]), ("it", ["it", "update/it"]), ("en", ["eng", "update/eng"])):
        table = {}
        for p in paths:
            f = os.path.join(translation, p, "Message", "ItemMessage.json")
            if os.path.exists(f):
                table.update(json.load(open(f, encoding="utf-8")))
        names[lang] = table
    return names


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("romfs")
    ap.add_argument("update_romfs")
    ap.add_argument("--translation", help="DQMJ3P-IT-FanTranslation/json, for item names")
    ap.add_argument("-o", "--out", default=os.path.join(os.path.dirname(__file__), "..", "..", "server", "sil",
                                                        "present_codes.json"))
    args = ap.parse_args()

    codes = rom_codes(os.path.join(args.romfs, "data/PresentCode/PresentCodeROMCode.bin"))
    codes.update(rom_codes(os.path.join(args.update_romfs, "data/PresentCode/PresentCodeROMCode.bin")))
    names = item_names(args.translation) if args.translation else {}

    def package(number):
        for root in (args.update_romfs, args.romfs):
            f = os.path.join(root, "data/PresentCode/Package/PresentCodePackageR%03d.bin" % number)
            if os.path.exists(f):
                return open(f, "rb").read()
        raise FileNotFoundError(number)

    gifts = []

    def add(number, source, code, data=None, item=None, count=None):
        gift = {"package": number, "source": source, "codes": [code]}
        if data is not None and struct.unpack_from("<I", data, 0xC)[0] == 0:
            gift["disc"] = data[0x20:-32].hex()
            gift["names"] = {"ja": DISC_NAMES[number % 100][0]}
            gift["alias"] = DISC_NAMES[number % 100][1]
        else:
            if data is not None:
                item, count = struct.unpack_from("<hh", data, 0x20)
            gift["item"], gift["count"] = item, count
            key = "I%04d" % item
            gift["names"] = {lang: table.get(key, "").strip() for lang, table in names.items()}
        gifts.append(gift)

    for number, code in sorted(codes.items()):
        source = "DQMJ3P" if 26 <= number <= 36 or 50 <= number <= 64 or 80 <= number <= 83 else "DQMJ3"
        add(PACKAGE_BASE + number, source, code, data=package(number))
    for number, code, item, count in BASE_CODES:
        if item is None:
            add(PACKAGE_BASE + number, "DQMJ3", code, data=package(number))
        else:
            add(PACKAGE_BASE + 100 + number, "DQMJ3", code, item=item, count=count)

    # * One alias per gift: English item name in letters, plus the count when the item comes in several
    counts = {}
    for gift in gifts:
        if "item" in gift:
            counts.setdefault(gift["item"], set()).add(gift["count"])
    aliases = {}
    for gift in gifts:
        if "item" in gift:
            base = re.sub(r"[^A-Z]", "", gift["names"].get("en", "").upper()) or "ITEM%d" % gift["item"]
            suffix = COUNT_WORDS[gift["count"]] if len(counts[gift["item"]]) > 1 else ""
            gift["alias"] = base[:ALIAS_MAX - len(suffix)] + suffix
        owner = aliases.setdefault(gift["alias"], gift)
        if owner is not gift:
            assert (owner.get("item"), owner.get("count"), owner.get("disc")) == \
                   (gift.get("item"), gift.get("count"), gift.get("disc")), gift["alias"]
            gift["package"] = owner["package"]

    out = {"comment": "Generated by re/tools/make_present_codes.py, see re/notes/present_codes.md",
           "gifts": gifts}
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(len(gifts), "codes,", len(aliases), "aliases ->", args.out)


if __name__ == "__main__":
    sys.exit(main())
