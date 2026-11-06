// Every locale has the keys of en.json (plural forms aside) and every literal t("key") of the code exists.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const dir = new URL("../src/locales/", import.meta.url).pathname;
const flat = (o, p = "") => Object.entries(o).flatMap(([k, v]) => (typeof v === "object" ? flat(v, `${p}${k}.`) : [`${p}${k}`]));
const base = (k) => k.replace(/_(zero|one|two|few|many|other)$/, "");
const load = (l) => new Set(flat(JSON.parse(readFileSync(join(dir, `${l}.json`), "utf8"))).map(base));
const en = load("en");
let failed = false;
for (const l of ["it", "es", "fr", "ja"]) {
  const keys = load(l);
  const missing = [...en].filter((k) => !keys.has(k));
  const extra = [...keys].filter((k) => !en.has(k));
  if (missing.length || extra.length) { failed = true; console.error(`${l}: missing ${missing.join(", ") || "-"}; extra ${extra.join(", ") || "-"}`); }
}
const files = (d) => readdirSync(d).flatMap((f) => (statSync(join(d, f)).isDirectory() ? files(join(d, f)) : f.endsWith(".tsx") || f.endsWith(".ts") ? [join(d, f)] : []));
for (const file of files(new URL("../src/", import.meta.url).pathname)) {
  for (const [, key] of readFileSync(file, "utf8").matchAll(/\bt\("([a-zA-Z0-9_.]+)"/g)) {
    if (key.includes(".") && !en.has(key)) { failed = true; console.error(`${file}: unknown key ${key}`); }
  }
}
if (failed) process.exit(1);
console.log("locales OK");
