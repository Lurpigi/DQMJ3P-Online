// src/azahar.ts builds the same personal patch as re/tools/make_url_patch.py apply_identity():
// the expected hashes come from the Python tool (same PID and secret). Run by `npm run check`.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { applyIdentity, friendCode, md5, newSecret, playerPassword, readIdentity, readIps, writeIps } from "../src/azahar.ts";

const id = { pid: 0xf1234567, secret: "abcdefghijkmnpqr" };
const expected: Record<string, string> = {
  jp: "dcdc4a29ea44726b4378c9810386ff697ef84a5d89d10731e66efc8e817d4ece",
  it: "ff14ef8c8c1e2e1db4c7681cbb609280bade22229152c7a1d15c69ea1030e3e1",
};
const fail = (msg: string) => { console.error(msg); process.exit(1); };

if (md5(new Uint8Array()) !== "d41d8cd98f00b204e9800998ecf8427e") fail("md5('')");
if (md5(new TextEncoder().encode("a".repeat(100))) !== "36a92cc94a9e0fa21f625f8bfb007adf") fail("md5(a*100)");
if (playerPassword(id.secret) !== "016247f122a2e50d") fail("player password");
if ((await friendCode(id.pid)) !== "4249-5241-5591") fail("friend code");
if (!/^[a-km-np-z2-9]{16}$/.test(newSecret())) fail("secret alphabet");

for (const [variant, hash] of Object.entries(expected)) {
  const base = readIps(new Uint8Array(readFileSync(new URL(`../public/patches/azahar-${variant}.ips`, import.meta.url))));
  if (readIdentity(base) !== null) fail(`${variant}: base patch has an identity`);
  const personal = writeIps(await applyIdentity(base, id));
  if (createHash("sha256").update(personal).digest("hex") !== hash) fail(`${variant}: differs from make_url_patch.py`);
  const back = readIdentity(readIps(personal));
  if (back?.pid !== id.pid || back.secret !== id.secret) fail(`${variant}: identity not read back`);
  const again = writeIps(await applyIdentity(base, back));
  if (Buffer.compare(Buffer.from(again), Buffer.from(personal)) !== 0) fail(`${variant}: rebuild differs`);
  try { await applyIdentity(readIps(personal), id); fail(`${variant}: identity applied twice`); } catch (e) {
    if ((e as Error).message !== "not_release_patch") throw e;
  }
}
console.log("azahar patches OK");
