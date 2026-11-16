// Personal patches for Azahar without Pretendo, built in the browser. The same records as
// re/tools/make_url_patch.py apply_identity(): the secret stays on the player's computer, the server
// only gets the player password derived from it (POST /azahar/accounts, server/dashboard).
// web/scripts/check-azahar.ts checks this file against the Python tools.

export const PLAYER_SALT = "DQMJ3P-Online-v1";
export const ISSUED_PID_MIN = 0xf0000000;
export const ISSUED_PID_MAX = 0xfffffffe;
const PLAYER_CAVE = 0x6b9a60;
const SECRET_CALL = PLAYER_CAVE + 0x0c; // bl GetMyPassword in the player-password routine
const IDENTITY_CAVE = 0x6b9b70;
const PID_SITE = 0x42d48c; // GetMyFriendKey wrapper
const GET_MY_PASSWORD = 0x42c674;
const SECRET_LENGTH = 16;
const SECRET_ALPHABET = "abcdefghijkmnpqrstuvwxyz23456789"; // 32 symbols: 80 bits
const ARM_NOP = 0xe320f000;

// Base patches of the release (web/public/patches): the Azahar "enhanced" variants
export const VARIANTS = { jp: "patches/azahar-jp.ips", it: "patches/azahar-it.ips" } as const;
export type Variant = keyof typeof VARIANTS;

export interface IpsRecord { off: number; data: Uint8Array }
export interface Identity { pid: number; secret: string }

export function readIps(bytes: Uint8Array): IpsRecord[] {
  const ascii = (i: number, n: number) => String.fromCharCode(...bytes.subarray(i, i + n));
  if (ascii(0, 5) !== "PATCH") throw new Error("not_ips");
  const records: IpsRecord[] = [];
  let i = 5;
  while (ascii(i, 3) !== "EOF") {
    if (i + 5 > bytes.length) throw new Error("not_ips");
    const off = (bytes[i] << 16) | (bytes[i + 1] << 8) | bytes[i + 2];
    const size = (bytes[i + 3] << 8) | bytes[i + 4];
    i += 5;
    if (size === 0) { // RLE
      const count = (bytes[i] << 8) | bytes[i + 1];
      records.push({ off, data: new Uint8Array(count).fill(bytes[i + 2]) });
      i += 3;
    } else {
      if (i + size > bytes.length) throw new Error("not_ips");
      records.push({ off, data: bytes.slice(i, i + size) });
      i += size;
    }
  }
  return records;
}

export function writeIps(records: IpsRecord[]): Uint8Array {
  const parts: number[] = [..."PATCH"].map((c) => c.charCodeAt(0));
  for (const { off, data } of records) {
    for (let start = 0; start < data.length; start += 0xffff) {
      const chunk = data.subarray(start, start + 0xffff);
      const o = off + start;
      if (o === 0x454f46) throw new Error("eof_offset");
      parts.push((o >> 16) & 0xff, (o >> 8) & 0xff, o & 0xff, chunk.length >> 8, chunk.length & 0xff);
      for (const b of chunk) parts.push(b);
    }
  }
  parts.push(0x45, 0x4f, 0x46);
  return new Uint8Array(parts);
}

function words(...ws: number[]): Uint8Array<ArrayBuffer> {
  const out = new Uint8Array(ws.length * 4);
  const view = new DataView(out.buffer);
  ws.forEach((w, i) => view.setUint32(i * 4, w >>> 0, true));
  return out;
}

function branchLink(src: number, dst: number): number {
  return ((0xe << 28) | (0xb << 24) | (((dst - src - 8) >> 2) & 0xffffff)) >>> 0;
}

function concat(...arrays: Uint8Array[]): Uint8Array {
  const out = new Uint8Array(arrays.reduce((n, a) => n + a.length, 0));
  let at = 0;
  for (const a of arrays) { out.set(a, at); at += a.length; }
  return out;
}

const equal = (a: Uint8Array, b: Uint8Array) => a.length === b.length && a.every((x, i) => x === b[i]);

/** Friend code checksum (high word of the local friend code): top 7 bits of SHA-1(PID, little endian). */
export async function friendCodeHigh(pid: number): Promise<number> {
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-1", words(pid)));
  return digest[0] >> 1;
}

export async function friendCode(pid: number): Promise<string> {
  const code = (BigInt(await friendCodeHigh(pid)) << 32n) | BigInt(pid);
  return code.toString().padStart(12, "0").replace(/(\d{4})(\d{4})(\d{4})/, "$1-$2-$3");
}

/** Records of a release Azahar patch turned into a personal one (make_url_patch.py apply_identity). */
export async function applyIdentity(base: IpsRecord[], id: Identity): Promise<IpsRecord[]> {
  const secret = new TextEncoder().encode(id.secret);
  if (secret.length !== SECRET_LENGTH || id.pid < ISSUED_PID_MIN || id.pid > ISSUED_PID_MAX) throw new Error("bad_identity");
  const records = base.map((r) => ({ off: r.off, data: r.data.slice() }));
  const host = records.find((r) => SECRET_CALL - r.off >= 0 && SECRET_CALL - r.off <= r.data.length - 4);
  const at = host ? SECRET_CALL - host.off : -1;
  if (!host || !equal(host.data.subarray(at, at + 4), words(branchLink(SECRET_CALL, GET_MY_PASSWORD)))) throw new Error("not_release_patch");
  host.data.set(words(branchLink(SECRET_CALL, IDENTITY_CAVE)), at);
  const secretRoutine = concat(words(
    0xe28f100c, // adr r1,secret
    0xe891100e, // ldm r1,{r1-r3,r12}
    0xe880100e, // stm r0,{r1-r3,r12}
    0xe3a00000, // mov r0,#0
    0xe12fff1e, // bx lr
  ), secret);
  const pidRoutine = words(
    0xe59f0010, // ldr r0,high
    0xe585000c, // str r0,[r5,#0xc]
    0xe59f100c, // ldr r1,pid
    0xe3a02000, // mov r2,#0
    0xe1a03001, // mov r3,r1
    0xe12fff1e, // bx lr
    await friendCodeHigh(id.pid), id.pid,
  );
  const site = words(branchLink(PID_SITE, IDENTITY_CAVE + secretRoutine.length), ARM_NOP, ARM_NOP, ARM_NOP);
  const ours = [{ off: PID_SITE, data: site }, { off: IDENTITY_CAVE, data: concat(secretRoutine, pidRoutine) }];
  for (const r of records) {
    for (const o of ours) {
      if (r.off < o.off + o.data.length && o.off < r.off + r.data.length) throw new Error("not_release_patch");
    }
  }
  return [...records, ...ours];
}

/** PID and secret of a personal patch, or null for any other patch. */
export function readIdentity(records: IpsRecord[]): Identity | null {
  const cave = records.find((r) => r.off === IDENTITY_CAVE && r.data.length === 0x44);
  if (!cave || !equal(cave.data.subarray(0, 0x14), words(0xe28f100c, 0xe891100e, 0xe880100e, 0xe3a00000, 0xe12fff1e))) return null;
  const secret = new TextDecoder().decode(cave.data.subarray(0x14, 0x24));
  const pid = new DataView(cave.data.buffer, cave.data.byteOffset).getUint32(0x40, true);
  return pid >= ISSUED_PID_MIN && pid <= ISSUED_PID_MAX && /^[\x21-\x7e]{16}$/.test(secret) ? { pid, secret } : null;
}

export function newSecret(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(SECRET_LENGTH));
  return [...bytes].map((b) => SECRET_ALPHABET[b & 31]).join("");
}

/** What the patched game sends as its NEX and SIL token: MD5(salt + secret), first 8 bytes in hex. */
export function playerPassword(secret: string): string {
  return md5(new TextEncoder().encode(PLAYER_SALT + secret)).slice(0, 16);
}

// RFC 1321 (Web Crypto has no MD5)
const S = [7, 12, 17, 22, 5, 9, 14, 20, 4, 11, 16, 23, 6, 10, 15, 21];
const K = Array.from({ length: 64 }, (_, i) => Math.floor(Math.abs(Math.sin(i + 1)) * 2 ** 32) >>> 0);

export function md5(message: Uint8Array): string {
  const length = message.length;
  const padded = new Uint8Array(((length + 8) >> 6) * 64 + 64);
  padded.set(message);
  padded[length] = 0x80;
  const view = new DataView(padded.buffer);
  view.setUint32(padded.length - 8, (length * 8) >>> 0, true);
  view.setUint32(padded.length - 4, Math.floor(length / 0x20000000), true);
  let a0 = 0x67452301, b0 = 0xefcdab89, c0 = 0x98badcfe, d0 = 0x10325476;
  for (let block = 0; block < padded.length; block += 64) {
    let a = a0, b = b0, c = c0, d = d0;
    for (let i = 0; i < 64; i++) {
      let f: number, g: number;
      if (i < 16) { f = (b & c) | (~b & d); g = i; }
      else if (i < 32) { f = (d & b) | (~d & c); g = (5 * i + 1) % 16; }
      else if (i < 48) { f = b ^ c ^ d; g = (3 * i + 5) % 16; }
      else { f = c ^ (b | ~d); g = (7 * i) % 16; }
      const sum = (a + f + K[i] + view.getUint32(block + g * 4, true)) >>> 0;
      const s = S[(i >> 4) * 4 + (i % 4)];
      a = d; d = c; c = b;
      b = (b + ((sum << s) | (sum >>> (32 - s)))) >>> 0;
    }
    a0 = (a0 + a) >>> 0; b0 = (b0 + b) >>> 0; c0 = (c0 + c) >>> 0; d0 = (d0 + d) >>> 0;
  }
  const out = words(a0, b0, c0, d0);
  return [...out].map((x) => x.toString(16).padStart(2, "0")).join("");
}
