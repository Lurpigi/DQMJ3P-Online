"""Build a Luma3DS / Azahar code.ips that redirects DQMJ3P's Square Enix servers.

Luma (and Azahar) load ONE code.ips per title, so this tool can merge the records of an
existing patch (e.g. the Italian fan translation) with the URL replacements.

usage (python -I):
  make_url_patch.py --code code.bin --sil-url http://example.org/00300701/ \
      [--infra-url http://example.org/infra/] [--spotpass-url http://example.org:8380/p01/nsa/H7btVjYWs7p5dGj6] \
      [--skip-nasc] [--skip-frd] [--azahar] [--azahar-hle-boss] [--merge other/code.ips] -o code.ips

Install: SD:/luma/titles/00040000001ACB00/code.ips  (3DS, "Enable game patching" on)
         <Azahar user dir>/load/mods/00040000001ACB00/exefs/code.ips
"""
import argparse
import struct
import sys

# String slots in code.bin v1.3 (file offsets = VA - 0x100000), verified in Ghidra.
SIL_URL = (0x76C83C, b"https://dqm32ds.sil2.square-enix.com/00300701/")
INFRA_URL = (0x7BF6D4, b"http://wi-fi.infralib.square-enix.com/")
# SpotPass (BOSS) base URL; tasks are "%s/%s" with "<TASK>/<file>" (re/notes/spotpass_boss.md).
SPOTPASS_URL = (0x76A0C4, b"https://npdl.cdn.nintendowifi.net/p01/nsa/H7btVjYWs7p5dGj6")

# --skip-nasc: SilAuthJob_Update (0x66cacc) logs in to NEX (NASC LOGIN) and asks NASC for a
# service token (SVCLOC) before talking to SIL; Pretendo answers both with error 110 while the
# game is not registered there. Skip them so the job goes straight to SIL register/login with an
# all-zero token (our SIL server does not verify it). Test builds only.
# The friends-server login that comes first (frd Login, job 0x66ed9c) works on Pretendo with Nimbus.
ARM_NOP = bytes.fromhex("00f020e3")
# --skip-frd: also pretend the frd login succeeded. Without a real login the next frd calls fail
# (Azahar 2026-10-26: error 006-0000 right after AC connect), so this is only a debugging aid.
SKIP_FRD = [  # (file offset, original, replacement)
    # frd job state 0: bne 0x66ee54 -> b 0x66eee4 (success path: flags |= 4, then state 2)
    (0x56EDE0, bytes.fromhex("1b00001a"), bytes.fromhex("3f0000ea")),
]
# --azahar: work around two Azahar http:C bugs hit by sil_HttpWorker (0x603a10).
# 1. A POST without post data is never sent (BeginRequest leaves it pending until
#    NotifyFinishSendPostData, which refuses contexts without data), so SIL requests with an empty
#    body (nuser/getnonce) time out after 60 s. The worker only enables lazy/chunked post data when
#    the body is non-empty: force it on. The SDK's SendPostDataRaw rejects a NULL/0-length buffer,
#    so the dummy entry used for an empty list ({next, data, alt, size} at 0x7d5f8c, only read
#    there) is made to send one 0x00 byte; the server treats b"\0" as empty. The request digest
#    only covers the real entries, so it is unchanged.
# 2. GetResponseData (all headers) reports min(real size, buffer size) instead of the real size, so
#    the worker's size probe with a 1-byte buffer allocates 1 byte, X-Sil-Digest is never found
#    and every file/* response is rejected (-304, "Download non riuscito"). Replace the probe's
#    error check with a fixed 4 KiB header buffer size; the second call still checks its result.
AZAHAR_FIXES = [
    (0x503E88, bytes.fromhex("0090a003"), ARM_NOP),  # moveq r9,#0
    (0x503E8C, bytes.fromhex("0e00000a"), ARM_NOP),  # beq (skip SetLazyPostDataSetting)
    (0x6D5F8C, bytes(16), bytes.fromhex("00000000" "8c5f7d00" "00000000" "01000000")),
    (0x504290, bytes.fromhex("020110e3"), bytes.fromhex("010aa0e3")),  # tst r0,#0x80000000 -> mov r0,#0x1000
    (0x504294, bytes.fromhex("2000001a"), bytes.fromhex("140084e5")),  # bne error -> str r0,[r4,#0x14]
]
# --azahar-hle-boss: only for Azahar with the HLE BOSS service (no "required online LLE modules"),
# which never downloads tasks and always reports task state 0 while the game waits for 6 ("done")
# before reading NsData (gift discs FUN_00370e94, coin shop FUN_002c9a54). The NsData then come
# from files in the BOSS extdata (re/tools/spotpass_azahar.py). With the real boss module (LLE) use
# --spotpass-url instead.
AZAHAR_HLE_BOSS = [
    (0x58212C, bytes.fromhex("000051e30900a003"), bytes.fromhex("0600a0e31eff2fe1")),  # boss_vfn_68212c: mov r0,#6; bx lr
]
SKIP_NASC = [
    (0x56CB48, bytes.fromhex("7afcff0b"), ARM_NOP),  # case 0: bleq 0x66bd38 (queue NEX login)
    (0x56CB90, bytes.fromhex("ba00000a"), ARM_NOP),  # case 1: beq (wait for NEX logged-in flag 0x10)
    (0x56CBC4, bytes.fromhex("0d00000a"), ARM_NOP),  # case 1: beq (token empty -> silAuthRequestAuthToken)
    # The Wi-Fi plaza connection (also from the rankings desk) logs in to NEX through other paths
    # (Azahar: 002-0110). NexLoginJob_Start (0x66c4ec) -> "mov r0,#0; bx lr": report success without
    # NASC. NEX features (battles, communities) stay unusable, SIL does not need them.
    (0x56C4EC, bytes.fromhex("f0402de90040a0e1"), bytes.fromhex("0000a0e31eff2fe1")),
    # Ranking Battle connect screen (FUN_003ca8cc): after connecting it requires a live NEX session
    # (FUN_00445fb8 -> NgsFacade state 0x10001), else closes the menu silently. Skip that check.
    (0x2CA944, bytes.fromhex("1900000a"), ARM_NOP),  # beq 0x3ca9b0
    # The plaza's generic connect screen (0x5e, update function 0x3879ac, state in +0x68): states 2/3
    # bring up the AC connection, state 7 (8) then runs a network login task (+0x80 / +0x84) that
    # fails without NEX and is reported through FUN_005f3b74 (006-0000). The AC connection is what
    # the BOSS module needs for gift discs and the coin shop stock, so take the success path
    # (state 10) whatever the task result is.
    (0x288044, bytes.fromhex("800094e5"), bytes.fromhex("2b0000ea")),  # state 7: b 0x3880f8
    (0x2880AC, bytes.fromhex("840094e5"), bytes.fromhex("110000ea")),  # state 8: b 0x3880f8
    # After screen 0x5e the gift disc menu (FUN_00439e58) and the coin shop (FUN_002ca3b8) only go
    # on to the download if FUN_00445fb8 (NEX connected) says so: force it at those two calls.
    (0x339EC4, bytes.fromhex("3b3000eb"), bytes.fromhex("0100a0e3")),  # gift: bl -> mov r0,#1
    (0x1CA434, bytes.fromhex("dfee05eb"), bytes.fromhex("0100a0e3")),  # coin shop: bl -> mov r0,#1
]


def read_ips(data):
    if data[:5] != b"PATCH":
        raise ValueError("not an IPS file")
    records, i = [], 5
    while data[i:i + 3] != b"EOF":
        off = int.from_bytes(data[i:i + 3], "big")
        size = int.from_bytes(data[i + 3:i + 5], "big")
        i += 5
        if size == 0:  # RLE record
            count = int.from_bytes(data[i:i + 2], "big")
            records.append((off, bytes([data[i + 2]]) * count))
            i += 3
        else:
            records.append((off, data[i:i + size]))
            i += size
    return records


def write_ips(records):
    out = bytearray(b"PATCH")
    for off, payload in records:
        if off == 0x454F46:  # "EOF" as an offset would end the patch early
            raise ValueError("record at offset 0x454F46 is not representable")
        for start in range(0, len(payload), 0xFFFF):
            chunk = payload[start:start + 0xFFFF]
            out += (off + start).to_bytes(3, "big") + len(chunk).to_bytes(2, "big") + chunk
    return bytes(out + b"EOF")


def slot_record(code, slot, new_url):
    off, original = slot
    if code[off:off + len(original)] != original:
        sys.exit(f"code.bin does not contain {original!r} at {off:#x}: wrong version (needs v1.3)")
    # The slot is the original string plus its NUL; padding up to the next string is unknown,
    # so never write past the original terminator.
    new = new_url.encode()
    if len(new) > len(original):
        sys.exit(f"{new_url!r} is {len(new)} bytes, max {len(original)} for this slot")
    return off, new + b"\0" * (len(original) + 1 - len(new))


def code_record(code, site):
    off, original, new = site
    if code[off:off + len(original)] != original:
        sys.exit(f"code.bin does not contain {original.hex()} at {off:#x}: wrong version (needs v1.3)")
    return off, new


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--code", required=True, help="decompressed code.bin v1.3")
    ap.add_argument("--sil-url", required=True, help="replacement for the Square Enix SIL base URL (keep the trailing /)")
    ap.add_argument("--infra-url", help="replacement for wi-fi.infralib.square-enix.com")
    ap.add_argument("--spotpass-url",
                    help="replacement SpotPass base, e.g. http://host:8380/p01/nsa/H7btVjYWs7p5dGj6 (server/spotpass)")
    ap.add_argument("--azahar-hle-boss", action="store_true",
                    help="Azahar with the HLE BOSS service: report SpotPass tasks as done (data from spotpass_azahar.py)")
    ap.add_argument("--skip-nasc", action="store_true",
                    help="skip NEX login + NASC service token before SIL (test builds, game not on Pretendo)")
    ap.add_argument("--skip-frd", action="store_true", help="also fake the friends-server login (debugging only)")
    ap.add_argument("--azahar", action="store_true",
                    help="work around Azahar http:C bugs (empty POST, header size probe)")
    ap.add_argument("--merge", action="append", default=[], help="existing code.ips to include")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()

    code = open(args.code, "rb").read()
    ours = [slot_record(code, SIL_URL, args.sil_url)]
    if args.infra_url:
        ours.append(slot_record(code, INFRA_URL, args.infra_url))
    if args.spotpass_url:
        ours.append(slot_record(code, SPOTPASS_URL, args.spotpass_url))
    if args.azahar_hle_boss:
        ours += [code_record(code, site) for site in AZAHAR_HLE_BOSS]
    if args.skip_nasc:
        ours += [code_record(code, site) for site in SKIP_NASC]
    if args.skip_frd:
        ours += [code_record(code, site) for site in SKIP_FRD]
    if args.azahar:
        ours += [code_record(code, site) for site in AZAHAR_FIXES]

    # records this tool wrote into a previously merged patch are replaced, not kept
    own_offsets = {SIL_URL[0], INFRA_URL[0], SPOTPASS_URL[0]} | {
        off for off, _, _ in SKIP_NASC + SKIP_FRD + AZAHAR_FIXES + AZAHAR_HLE_BOSS}
    merged = []
    for path in args.merge:
        for off, payload in read_ips(open(path, "rb").read()):
            if off in own_offsets:
                continue
            for o, p in ours:
                if off < o + len(p) and o < off + len(payload):
                    sys.exit(f"{path}: record at {off:#x} overlaps our patch at {o:#x}")
            merged.append((off, payload))

    open(args.out, "wb").write(write_ips(merged + ours))
    print(f"wrote {args.out}: {len(merged)} merged records + {len(ours)} records of ours")


if __name__ == "__main__":
    main()
