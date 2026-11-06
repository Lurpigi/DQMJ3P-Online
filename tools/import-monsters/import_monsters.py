"""Builds the portal's monster catalog and portraits from local, reviewed sources.

Sources (all local files, nothing is fetched from the network):
  --sheet       the HTML export (zip or extracted folder) of the "DQM J3 Professional Master's guide"
                spreadsheet: Mostri.html + resources/cellImage_*.jpg (one icon per monster row)
  --kindparam   romfs:/data/Parameter/KindParam.tp: per species id (MK%04d) the Japanese name
                (Shift-JIS, +0x00), rank (+0x22, 1..8 = F..SS), family (+0x23), max stats (+0x24,
                6 x u16: HP MP ATK DEF AGI WIS) and size (+0x30, 0/1 small, 2 medium, 3 giga, 4 mega)
  --translation a DQMJ3P-IT-FanTranslation checkout: update/{it,eng}/Message/MonsterKindMessage.mes
                (the v1.3 update texts, newer than it/ and eng/), it|eng/Message/LocationMessage.mes
  --french      a French MonsterKindMessage.mes (optional)
  --japanese-locations  an untranslated LocationMessage.mes (optional, Japanese location names)

The spreadsheet has no species ids and its row order is not the id order, so every row is matched
to species ids by evidence, best first:
  name+stats   Italian name (update/it) and the six max stats of KindParam both equal
  stats        only the stats match (rows renamed in the sheet, e.g. "corrotto" = "Δ" forms); all
               candidates must share one Italian name and the sheet rank must agree
  name         the name matches species that share one set of stats, different from the sheet
               (sheet typos, placeholder stats in KindParam)
  stats-near   one species of the same rank within 100 stat points (renamed and retouched rows)
The game keeps several ids with the same name and stats (story copies of a monster); a row links
to all of them. Rows without evidence stay unmatched and are listed in the report.

Images are decoded and re-encoded with Pillow (size limits, no metadata), normalised to 96 px
wide tiles: large monsters are 2-4 tiles stacked vertically, as in the game's party list.

usage: python -I tools/import-monsters/import_monsters.py --sheet GUIDE.zip --kindparam KindParam.tp
         --translation ../DQMJ3P-IT-FanTranslation [--french fr/Message/MonsterKindMessage.mes]
         [--japanese-locations fr/Message/LocationMessage.mes]
         [--catalog server/dashboard/data/monsters.json] [--images web/public/monsters]
"""
import argparse
import collections
import datetime
import hashlib
import html.parser
import io
import json
import os
import re
import struct
import sys
import unicodedata
import zipfile

TILE = 96
MAX_IMAGE_BYTES = 1 << 20
MAX_IMAGE_SIDE = 2048
RANKS = {"F": 1, "E": 2, "D": 3, "C": 4, "B": 5, "A": 6, "S": 7, "SS": 8}
KIND_ENTRY = 0x78
# Names KindParam uses for unused or not yet named slots
PLACEHOLDER_JA = re.compile(r"^(追加モンスター|魔王リベンジ|ダミー|予備|dummy|-|\?+$)", re.IGNORECASE)
# Story copies of a monster: "（ボス）" prefix, or internal "魔王リベンジN" (rematch) labels
BOSS_JA = re.compile(r"^\s*[（(]ボス[）)]|^魔王リベンジ")


# --- game message files (.mes) --------------------------------------------------------------
def parse_mes(data):
    """{key: text}: u32 group count, groups (u32 count, u32 offset), then per key u32 text offset +
    ASCII key padded to 4 bytes; texts are NUL-terminated UTF-16LE."""
    (groups,) = struct.unpack_from("<I", data, 0)
    counts = [struct.unpack_from("<II", data, 4 + i * 8)[0] for i in range(groups)]
    offset, out = 4 + groups * 8, {}
    for _ in range(sum(counts)):
        (value,) = struct.unpack_from("<I", data, offset)
        end = data.index(b"\0", offset + 4)
        key = data[offset + 4:end].decode("ascii")
        offset = (end + 1 + 3) & ~3
        stop = value
        while data[stop:stop + 2] != b"\0\0":
            stop += 2
        out[key] = data[value:stop].decode("utf-16-le")
    return out


def read_mes(*paths):
    for path in paths:
        if path and os.path.isfile(path):
            return parse_mes(open(path, "rb").read()), path
    return {}, None


def parse_kindparam(data):
    if data[:4] != b"KINP":
        raise SystemExit("KindParam.tp: bad magic")
    kinds = {}
    for species in range((len(data) - 4) // KIND_ENTRY):
        e = data[4 + species * KIND_ENTRY:4 + (species + 1) * KIND_ENTRY]
        kinds[species] = {
            "ja": e[:0x20].split(b"\0")[0].decode("cp932", "replace"),
            "rank": e[0x22], "family": e[0x23],
            "stats": struct.unpack_from("<6H", e, 0x24), "size": e[0x30]}
    return kinds


# --- spreadsheet export ---------------------------------------------------------------------
class SheetParser(html.parser.HTMLParser):
    """Rows of the Google Sheets HTML export: per cell its text and first image source."""

    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell = [], None, None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self.row = []
        elif tag == "td" and self.row is not None:
            self.cell = {"text": "", "img": None}
        elif tag == "img" and self.cell is not None and self.cell["img"] is None:
            self.cell["img"] = attrs.get("src")
        elif tag == "br" and self.cell is not None:
            self.cell["text"] += "\n"

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None:
            self.row.append(self.cell)
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell["text"] += data


class Sheet:
    """Reads the export from a zip or a folder without extracting anything else."""

    def __init__(self, path):
        self.zip = zipfile.ZipFile(path) if zipfile.is_zipfile(path) else None
        self.dir = None if self.zip else path

    def read(self, name, limit=None):
        name = name.replace("\\", "/")
        if ".." in name.split("/") or name.startswith("/"):
            raise ValueError(f"unsafe path in sheet: {name}")
        if self.zip:
            info = self.zip.getinfo(name)
            if limit and info.file_size > limit:
                raise ValueError(f"{name}: {info.file_size} bytes")
            return self.zip.read(info)
        path = os.path.join(self.dir, name)
        if limit and os.path.getsize(path) > limit:
            raise ValueError(f"{name}: {os.path.getsize(path)} bytes")
        return open(path, "rb").read()


def sheet_rows(sheet):
    parser = SheetParser()
    parser.feed(sheet.read("Mostri.html").decode("utf-8"))
    out = []
    for number, row in enumerate(parser.rows, 1):
        if len(row) < 12 or not row[0]["img"]:
            continue
        text = [c["text"].strip() for c in row]
        try:
            stats = tuple(int(x) for x in text[6:12])
        except ValueError:
            stats = None
        out.append({"row": number, "image": row[0]["img"], "name": text[2], "rank": text[3].strip(),
                    "family": text[5], "stats": stats})
    return out


def norm(text):
    text = unicodedata.normalize("NFKC", text).replace("’", "'")
    return re.sub(r"\s+", " ", text).strip().casefold()


# --- matching -------------------------------------------------------------------------------
def stat_distance(a, b):
    return sum(abs(x - y) for x, y in zip(a, b))


def match_rows(rows, kinds, italian):
    by_name = collections.defaultdict(list)
    for key, name in italian.items():
        if key.startswith("MK") and name not in ("", "-"):
            by_name[norm(name)].append(int(key[2:]))
    by_stats = collections.defaultdict(list)
    for species, kind in kinds.items():
        if species and any(kind["stats"]):
            by_stats[kind["stats"]].append(species)

    def same_rank(species, rank):  # rank 0 = not set in KindParam (some story copies)
        return rank is None or kinds[species]["rank"] in (0, rank)

    def one_identity(candidates):
        """Candidates that are one monster: a single Italian name once story copies are set aside."""
        regular = [s for s in candidates if not BOSS_JA.match(kinds[s]["ja"])] or candidates
        names = {norm(italian.get("MK%04d" % s, "")) for s in regular}
        if len(names) != 1:
            return None
        name = names.pop()
        return [s for s in candidates if norm(italian.get("MK%04d" % s, "")) == name or s not in regular]

    links, unmatched = [], []
    for row in rows:
        rank = RANKS.get(row["rank"])
        named = sorted(s for s in by_name.get(norm(row["name"]), []) if s in kinds)
        both = [s for s in named if kinds[s]["stats"] == row["stats"]]
        if both:
            links.append((row, both, "name+stats"))
            continue
        stats = [s for s in by_stats.get(row["stats"], []) if same_rank(s, rank)] if row["stats"] else []
        identity = one_identity(sorted(stats)) if stats else None
        if identity:
            links.append((row, identity, "stats"))
            continue
        if named and len({kinds[s]["stats"] for s in named}) == 1:
            links.append((row, named, "name"))
            continue
        near = [s for s, kind in kinds.items() if s and row["stats"] and kind["rank"] == rank
                and stat_distance(kind["stats"], row["stats"]) <= 100]
        if len(near) == 1:
            links.append((row, near, "stats-near"))
            continue
        unmatched.append((row, named, sorted(stats)))
    return links, unmatched


# --- images ---------------------------------------------------------------------------------
def portrait(data):
    """Decoded, size-checked and re-encoded image: (webp bytes, tiles)."""
    from PIL import Image  # only needed when images are written

    image = Image.open(io.BytesIO(data))
    if image.format not in ("JPEG", "PNG", "WEBP", "GIF"):
        raise ValueError(f"unexpected image format {image.format}")
    if max(image.size) > MAX_IMAGE_SIDE:
        raise ValueError(f"image too large {image.size}")
    image.load()
    image = image.convert("RGB")
    tiles = max(1, min(4, round(image.height / image.width)))
    lanczos = getattr(Image, "Resampling", Image).LANCZOS  # Pillow < 9.1 has Image.LANCZOS only
    image = image.resize((TILE, TILE * tiles), lanczos)
    out = io.BytesIO()
    image.save(out, "WEBP", quality=88, method=6)
    return out.getvalue(), tiles


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--kindparam", required=True)
    ap.add_argument("--translation", required=True)
    ap.add_argument("--french")
    ap.add_argument("--japanese-locations")
    ap.add_argument("--french-items", help="French ItemMessage.mes (optional, reward names)")
    root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    ap.add_argument("--catalog", default=os.path.join(root, "server", "dashboard", "data", "monsters.json"))
    ap.add_argument("--images", default=os.path.join(root, "web", "public", "monsters"))
    ap.add_argument("--report", default=os.path.join(root, "tools", "import-monsters", "report.md"))
    ap.add_argument("--no-images", action="store_true", help="only write the catalog")
    args = ap.parse_args()

    kinds = parse_kindparam(open(args.kindparam, "rb").read())
    t = args.translation
    message = os.path.join("Message", "MonsterKindMessage.mes")
    italian, it_path = read_mes(os.path.join(t, "update", "it", message), os.path.join(t, "it", message))
    english, en_path = read_mes(os.path.join(t, "update", "eng", message), os.path.join(t, "eng", message))
    french, fr_path = read_mes(args.french)
    if not italian or not english:
        raise SystemExit("MonsterKindMessage.mes not found in the translation checkout")
    places = os.path.join("Message", "LocationMessage.mes")
    loc_en, _ = read_mes(os.path.join(t, "eng", places), os.path.join(t, "it", places))
    loc_ja, _ = read_mes(args.japanese_locations)
    items_msg = os.path.join("Message", "ItemMessage.mes")
    item_names = {"it": read_mes(os.path.join(t, "update", "it", items_msg), os.path.join(t, "it", items_msg))[0],
                  "en": read_mes(os.path.join(t, "update", "eng", items_msg), os.path.join(t, "eng", items_msg))[0],
                  "fr": read_mes(args.french_items)[0]}

    sheet = Sheet(args.sheet)
    rows = sheet_rows(sheet)
    links, unmatched = match_rows(rows, kinds, italian)

    art, species_art, conflicts, failures = {}, {}, [], []
    if not args.no_images:
        os.makedirs(args.images, exist_ok=True)
    for row, ids, how in links:
        key = "s%04d" % ids[0]
        if any(s in species_art for s in ids):
            conflicts.append((row, ids, [species_art.get(s) for s in ids]))
            ids = [s for s in ids if s not in species_art]
            if not ids:
                continue
        try:
            data = sheet.read(row["image"], MAX_IMAGE_BYTES)
            webp, tiles = portrait(data) if not args.no_images else (None, None)
        except Exception as e:  # noqa: BLE001 - reported, the species keeps the placeholder
            failures.append((row, str(e)))
            continue
        entry = {"file": key + ".webp", "tiles": tiles, "sheet_row": row["row"], "sheet_name": row["name"],
                 "match": how, "source_sha256": hashlib.sha256(data).hexdigest()}
        if webp:
            open(os.path.join(args.images, entry["file"]), "wb").write(webp)
            entry["sha256"] = hashlib.sha256(webp).hexdigest()
        art[key] = entry
        for s in ids:
            species_art[s] = key

    # Copies with the same Italian name and stats as a linked species share its portrait
    by_identity = {(norm(italian.get("MK%04d" % s, "")), kinds[s]["stats"]): key for s, key in species_art.items()}
    for s, kind in kinds.items():
        if s and s not in species_art:
            key = by_identity.get((norm(italian.get("MK%04d" % s, "")), kind["stats"]))
            if key and italian.get("MK%04d" % s, "-") not in ("", "-"):
                species_art[s] = key

    species = []
    for s, kind in sorted(kinds.items()):
        mk = "MK%04d" % s
        ja = BOSS_JA.sub("", kind["ja"]).strip()
        names = {"en": english.get(mk, ""), "it": italian.get(mk, ""), "fr": french.get(mk, ""),
                 "ja": "" if PLACEHOLDER_JA.match(kind["ja"]) else ja}
        names = {k: v for k, v in names.items() if v and v != "-"}
        if s == 0 or not (names.get("en") or names.get("it")):
            continue
        species.append({"id": s, "names": names, "rank": kind["rank"] or None, "family": kind["family"] or None,
                        "size": kind["size"], "stats": list(kind["stats"]), "art": species_art.get(s),
                        "story_copy": bool(BOSS_JA.match(kind["ja"]))})

    locations = {}
    for key, name in loc_en.items():
        m = re.fullmatch(r"loc_actual_(\d{3})", key)
        if m and name.strip():
            n = int(m.group(1))
            locations[n] = {"en": name.strip(), "short": loc_en.get("loc_%03d" % n, "").strip()}
            ja = loc_ja.get(key, "").strip()
            if ja:
                locations[n]["ja"] = ja

    items = {}
    for lang, names in item_names.items():
        for key, name in names.items():
            m = re.fullmatch(r"I(\d{4})", key)
            if m and name.strip() and name.strip() != "-":
                items.setdefault(str(int(m.group(1))), {})[lang] = name.strip()
    body = {"species": species, "art": art, "locations": {str(k): v for k, v in sorted(locations.items())},
            "items": dict(sorted(items.items(), key=lambda kv: int(kv[0])))}
    version = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
    catalog = {
        "version": version,
        "generated": datetime.date.today().isoformat(),
        "sources": {
            "artwork": "DQM J3 Professional Master's guide IT V1.0 by StrangeServer & Yggdrasil (spreadsheet export)",
            "names": {"it": os.path.relpath(it_path, t), "en": os.path.relpath(en_path, t),
                      "fr": "French fan translation" if fr_path else None, "ja": "KindParam.tp"},
            "parameters": "KindParam.tp (rank, family, size, max stats)",
        },
        "families": {"1": "slime", "2": "dragon", "3": "beast", "4": "nature", "5": "demon",
                     "6": "undead", "7": "material", "8": "corrupted", "9": "unknown"},
        **body,
    }
    os.makedirs(os.path.dirname(args.catalog), exist_ok=True)
    with open(args.catalog, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")

    how = collections.Counter(h for _, _, h in links)
    lines = [
        "# Monster catalog import report", "",
        f"Catalog version `{version}`, generated {catalog['generated']}.", "",
        f"- Sheet rows with an image: {len(rows)}",
        f"- Matched: {len(links)} ({', '.join(f'{k} {v}' for k, v in how.most_common())})",
        f"- Unmatched rows: {len(unmatched)}; image failures: {len(failures)}; conflicts: {len(conflicts)}",
        f"- Species in the catalog: {len(species)}, with a portrait: {sum(1 for s in species if s['art'])}",
        f"- Locations: {len(locations)}; items: {len(items)}", "",
        "## Matches by stats only", "",
        "| Sheet row | Sheet name | Species | Game name (it) |", "|---|---|---|---|"]
    lines += [f"| {r['row']} | {r['name']} | {', '.join(map(str, ids))} | {italian.get('MK%04d' % ids[0], '')} |"
              for r, ids, h in links if h == "stats"]
    lines += ["", "## Matches by name only or by near stats", "",
              "| Sheet row | Name | Species | Sheet stats | KindParam stats |", "|---|---|---|---|---|"]
    lines += [f"| {r['row']} | {r['name']} | {ids[0]} | {r['stats']} | {kinds[ids[0]]['stats']} |"
              for r, ids, h in links if h in ("name", "stats-near")]
    lines += ["", "## Unmatched rows", "", "| Sheet row | Name | Name candidates | Stats candidates |", "|---|---|---|---|"]
    lines += [f"| {r['row']} | {r['name']} | {named or '-'} | {stats or '-'} |" for r, named, stats in unmatched]
    if conflicts or failures:
        lines += ["", "## Problems", ""]
        lines += [f"- row {r['row']} {r['name']}: species {ids} already linked to {prev}" for r, ids, prev in conflicts]
        lines += [f"- row {r['row']} {r['name']}: {err}" for r, err in failures]
    with open(args.report, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"catalog {args.catalog} ({len(species)} species, {len(art)} portraits, version {version}); "
          f"report {args.report}; unmatched {len(unmatched)}", file=sys.stderr)


if __name__ == "__main__":
    main()
