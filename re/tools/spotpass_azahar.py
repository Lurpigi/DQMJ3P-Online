"""Put DQMJ3P SpotPass data (gift discs, Wi-Fi shop stock) where Azahar's BOSS service reads it.

Azahar never downloads SpotPass tasks: nn::boss NsData are files in the title's BOSS extdata,
  <sdmc>/Nintendo 3DS/<id0>/<id1>/extdata/00000000/00001ACB/boss/<any name>
each one a 0x34-byte big-endian header (Azahar BossHeader, online_service.h) + the payload. The game
picks the newest unread NsData whose datatype matches (GetNsDataIdList: filter 0x10000|mask, high
half equal, low half sharing a bit): gift discs mask 0x10 (FUN_00370a70), Wi-Fi shop 0x20
(FUN_002c9a54, payload must be 0x1288 bytes). Payloads are BSDT (re/tools/bsdt.py). The game also
waits for the task state "done", which Azahar never reports: build the code.ips with
make_url_patch.py --azahar.

usage (python -I, Azahar closed or at least out of the gift/shop menus):
  spotpass_azahar.py [--sdmc DIR] [--present FILE] [--shop FILE | --default-shop] [--remove]
    --present FILE   BossPresentDisc as BSDT .bin or bsdt.py JSON (e.g. RomFS data/Debug/BossPresentDisc.bin)
    --shop FILE      Wi-Fi shop stock as JSON: {"days": [[{"kind","id","bronze","silver","gold",
                     "platinum","u32"}, ...] x7]} (up to 42 slots a day; kind 1 item, 2 monster)
    --default-shop   built-in stock (items only, see DEFAULT_SHOP)
    --remove         delete the files this tool wrote
"""
import argparse
import json
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bsdt  # noqa: E402

PROGRAM_ID = 0x00040000001ACB00
EXTDATA_LOW = 0x00001ACB  # exheader ExtSaveDataId
DATATYPE = {"present": 0x00010010, "shop": 0x00010020}
FILE_NAME = {"present": "PresentDisc.bin", "shop": "WiFiShopTbl.bin"}
SHOP_DAYS, SHOP_SLOTS = 7, 42
SHOP_PAYLOAD = 0x1288

# Item ids = ItemMessage.mes keys I%04d. Prices: the shop shows the first non-zero of
# bronze/silver/gold/platinum (FUN_00446efc).
ALWAYS = [  # (item, bronze, silver, gold, platinum)
    (2, 2, 0, 0, 0),     # Medicina potente
    (7, 3, 0, 0, 0),     # Acqua magica
    (34, 3, 0, 0, 0),    # Panacea
    (47, 5, 0, 0, 0),    # Bocconi Bestiali
    (60, 0, 3, 0, 0),    # Mini Medaglia
    (68, 0, 2, 0, 0),    # Piccola Sfera di Luce
    (66, 0, 0, 1, 0),    # Sfera di Luce
    (42, 0, 2, 0, 0),    # Semi di Abilita'
]
ROTATING = [  # one tuple per weekday index 0..6: extra stock that day
    [(36, 0, 2, 0, 0), (54, 0, 0, 1, 0), (5, 0, 2, 0, 0), (200, 0, 0, 2, 0)],    # Vita, accessori
    [(37, 0, 2, 0, 0), (55, 0, 0, 1, 0), (9, 0, 2, 0, 0), (204, 0, 0, 2, 0)],    # Magia
    [(38, 0, 2, 0, 0), (56, 0, 0, 1, 0), (10, 0, 3, 0, 0), (208, 0, 0, 2, 0)],   # Forza
    [(39, 0, 2, 0, 0), (57, 0, 0, 1, 0), (11, 0, 0, 1, 0), (212, 0, 0, 2, 0)],   # Agilita'
    [(40, 0, 2, 0, 0), (58, 0, 0, 1, 0), (62, 0, 0, 1, 0), (225, 0, 0, 3, 0)],  # Resilienza
    [(41, 0, 2, 0, 0), (59, 0, 0, 1, 0), (43, 0, 3, 0, 0), (256, 0, 0, 0, 1)],   # Saggezza
    [(43, 0, 2, 0, 0), (70, 0, 0, 0, 1), (153, 0, 0, 1, 0), (116, 0, 0, 2, 0)],  # Grande Sfera di Luce
]


def default_shop():
    return {"days": [[{"kind": 1, "id": item, "bronze": b, "silver": s, "gold": g, "platinum": p}
                      for item, b, s, g, p in ALWAYS + ROTATING[day]] for day in range(SHOP_DAYS)]}


def shop_bsdt(stock):
    days = stock["days"]
    if len(days) != SHOP_DAYS:
        sys.exit("the shop needs 7 days")
    fields = {"days": []}
    for day in days:
        if len(day) > SHOP_SLOTS:
            sys.exit(f"at most {SHOP_SLOTS} slots a day")
        slots = [{"kind": e["kind"], "id": e["id"], "f2": e.get("bronze", 0), "f3": e.get("silver", 0),
                  "f4": e.get("gold", 0), "f5": e.get("platinum", 0), "u32": e.get("u32", 0)} for e in day]
        slots += [{"kind": 0, "id": 0, "f2": 0, "f3": 0, "f4": 0, "f5": 0, "u32": 0}] * (SHOP_SLOTS - len(slots))
        fields["days"].append(slots)
    data = bsdt.encode({"type": 6, "flags": 0, "fields": fields})
    assert len(data) == SHOP_PAYLOAD, len(data)
    return data


def load_bsdt(path, expected_type):
    raw = open(path, "rb").read()
    data = bsdt.encode(json.loads(raw)) if raw[:1] == b"{" else raw
    decoded = bsdt.decode(data)
    if decoded["type"] != expected_type or not decoded["hmac_ok"]:
        sys.exit(f"{path}: not a valid BSDT of type {expected_type}")
    return data


def boss_file(datatype, payload, ns_data_id):
    """Azahar BossHeader (0x34, big-endian): header_length 0x18 at 0, download date at 0x10,
    program id at 0x18, datatype 0x24, payload size 0x28, NsData id 0x2c, version 0x30."""
    header = bytearray(0x34)
    header[0] = 0x18
    struct.pack_into(">I", header, 0x10, int(time.time()) & 0xFFFFFFFF)
    struct.pack_into(">Q", header, 0x18, PROGRAM_ID)
    struct.pack_into(">IIII", header, 0x24, datatype, len(payload), ns_data_id, 1)
    return bytes(header) + payload


def extdata_dir(sdmc):
    root = os.path.join(sdmc, "Nintendo 3DS")
    hexid = lambda name: len(name) == 32 and all(c in "0123456789abcdefABCDEF" for c in name)  # noqa: E731
    ids = [os.path.join(root, a, b) for a in os.listdir(root) if hexid(a) and os.path.isdir(os.path.join(root, a))
           for b in os.listdir(os.path.join(root, a)) if hexid(b) and os.path.isdir(os.path.join(root, a, b))]
    if len(ids) != 1:
        sys.exit(f"expected one <id0>/<id1> folder under {root}, found {len(ids)}")
    return os.path.join(ids[0], "extdata", "00000000", f"{EXTDATA_LOW:08X}")


def ensure_extdata(path):
    """The game never formats its extdata on Azahar; Open() only needs boss/ to exist."""
    for sub in ("boss", "user"):
        os.makedirs(os.path.join(path, sub), exist_ok=True)
    meta = os.path.join(path, "metadata")
    if not os.path.exists(meta):
        open(meta, "wb").write(bytes.fromhex("ffffffff000000000300000000000000"))  # as Azahar formats it
    icon = os.path.join(path, "icon")
    if not os.path.exists(icon):
        open(icon, "wb").write(bytes(4))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sdmc", default=os.path.join(os.environ.get("APPDATA", ""), "Azahar", "sdmc"))
    ap.add_argument("--present", help="BossPresentDisc BSDT (.bin) or bsdt.py JSON")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--shop", help="shop stock JSON")
    group.add_argument("--default-shop", action="store_true", help="built-in shop stock")
    ap.add_argument("--remove", action="store_true", help="delete the files written by this tool")
    args = ap.parse_args()

    path = extdata_dir(args.sdmc)
    if args.remove:
        for name in FILE_NAME.values():
            target = os.path.join(path, "boss", name)
            if os.path.exists(target):
                os.remove(target)
                print("removed", target)
        return
    payloads = {}
    if args.present:
        payloads["present"] = load_bsdt(args.present, 5)
    if args.shop:
        payloads["shop"] = shop_bsdt(json.load(open(args.shop, encoding="utf-8")))
    elif args.default_shop:
        payloads["shop"] = shop_bsdt(default_shop())
    if not payloads:
        ap.error("nothing to write: pass --present and/or --shop/--default-shop")

    ensure_extdata(path)
    # A new id each time: the game only takes NsData newer than the last one it used.
    ns_data_id = int(time.time()) & 0x7FFFFFFF
    for i, (kind, payload) in enumerate(payloads.items()):
        target = os.path.join(path, "boss", FILE_NAME[kind])
        open(target, "wb").write(boss_file(DATATYPE[kind], payload, ns_data_id + i))
        print(f"wrote {target} ({len(payload)} B payload, NsData id {ns_data_id + i})")


if __name__ == "__main__":
    main()
