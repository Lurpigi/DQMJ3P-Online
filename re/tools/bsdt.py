#!/usr/bin/env python3
"""BSDT codec for DQMJ3P (Dragon Quest Monsters Joker 3 Professional) SpotPass payloads.

Format (derived from code.bin v1.3, validator FUN_002273f0):
  +0  "BSDT"
  +4  u8  type  (1 StealthBox item, 2 StealthBox monster, 3 SkyMapMonster,
                 4 PassingMonster, 5 PresentDisc, 6 WiFiShopTbl)
  +5  u8  flags/version (game rejects (flags & 0x7f) > 3)
  +6  u16 total size (including the trailing 32 byte signature)
  +8  body (types 1-4: XOR-obfuscated with a fixed per-type key; 5-6: plaintext)
  end 32 bytes: HMAC-SHA256(key[type], data[0:size-32])

Usage (run with python -I):
  bsdt.py decode IN.bin [OUT.json]    # prints/writes JSON (plaintext body + parsed fields)
  bsdt.py encode IN.json OUT.bin
  bsdt.py selftest FILE...            # decode+encode, compare bytes
JSON: {"type","flags","body_hex","fields"}. On encode, "fields" (if present and
the type is 1-4) is packed and overrides body_hex; types 5/6 use "fields" too when
present (records as hex), else body_hex.
"""
import hmac, hashlib, json, struct, sys

HMAC_KEYS = {
    1: '99f1a3070d3caea0fd370eec3803cc466fad326c9991e4fcea43b6a6344b7ec7',
    2: 'bea6b4758221fda18e2b2486d9362340cc5d579cf9a1f6ead020a79f1bbf9c66',
    3: '03452b675584c1c17df5c1a5db413f7adf0d5e4c79ea5cbca7186d759a65c498',
    4: '1f2fa36aca25ed6021d4360efd1c12a411955877b70c02530c8bff3f6041e245',
    5: 'e36b52b7a963f0aa5d25d706f155ffab28ee6d0b816d1970b8b33bc53991a1bd',
    6: 'bb7da13ffb8ca713d23430664b7ccf8ee4d7e6f285310edc45d9889b12346d6f',
}
XOR_KEYS = {
    1: 'e2cd17ca',
    2: '8c29fe0526d345b4fa4eada2e1b6489cc56bb404e075b6aad861e7ea291e0bb0b8b5db2ccb24',
    3: '72599e842c1c7791',
    4: '889d2874c8827a32a3c69485e2e40adf42bec9ec6aabadae84211ee912d04bef9f23228f8d282851bb02d6e22db45f2f7d46e9a1b7e33d98ec8ae14ac71d78a3b5c938f145d0bfad580a0449a6a926daa48e7f42',
}
BODY_LEN = {1: 4, 2: 38, 3: 8, 4: 84}  # fixed body sizes (types 1-4)
NAMES = {1: 'StealthBoxItem', 2: 'StealthBoxMons', 3: 'SkyMapMonster',
         4: 'PassingMonster', 5: 'PresentDisc', 6: 'WiFiShopTbl'}


def _xor(body, t):
    k = bytes.fromhex(XOR_KEYS[t])
    return bytes(a ^ b for a, b in zip(body, k))


def _sig(t, data):
    return hmac.new(bytes.fromhex(HMAC_KEYS[t]), data, hashlib.sha256).digest()


def _u16s(b):
    return list(struct.unpack('<%dH' % (len(b) // 2), b))


# ---------------- field parsers / packers ----------------
def parse_body(t, body):
    if t == 1:
        item, pad, cnt = struct.unpack('<HBB', body)
        return {'item_id': item, 'pad': pad, 'count': cnt}
    if t == 2:
        seed, species, level, pad = struct.unpack_from('<IHBB', body, 0)
        skills = _u16s(body[8:20])
        return {'seed': seed, 'species_id': species, 'level_or_plus': level, 'pad7': pad,
                'skill_ids': skills, 'tail_hex': body[20:].hex()}
    if t == 3:
        a, b, seed = struct.unpack('<HHI', body)
        return {'monster_id_a': a, 'monster_id_b': b, 'seed': seed}
    if t == 4:
        seed = struct.unpack_from('<I', body, 0)[0]
        return {'seed': seed,
                'name': body[4:0x20].decode('utf-16le').rstrip('\0'),
                'name_raw_hex': body[4:0x20].hex(),
                'reward_u32': struct.unpack_from('<I', body, 0x20)[0],
                'skill_ids': _u16s(body[0x24:0x2c]),
                'species_id': struct.unpack_from('<H', body, 0x2c)[0],
                'rank_byte_2e': body[0x2e],
                'byte_2f': body[0x2f],
                'message': body[0x30:0x54].decode('utf-16le').rstrip('\0'),
                'message_raw_hex': body[0x30:0x54].hex()}
    if t == 5:
        na, nb = body[0], body[1]
        p = 4
        a = []
        for _ in range(na):
            hdr = body[p:p + 8]
            n = hdr[3]
            items = [body[p + 8 + 16 * i:p + 24 + 16 * i].hex() for i in range(n)]
            a.append({'hdr_hex': hdr.hex(), 'tag_u16': struct.unpack_from('<H', hdr, 0)[0],
                      'kind': hdr[2], 'year_off_2000': hdr[4], 'month': hdr[5],
                      'day': hdr[6], 'items16_hex': items})
            p += 8 + 16 * n
        b = []
        for _ in range(nb):
            b.append(body[p:p + 0x48].hex())
            p += 0x48
        return {'hdr4_hex': body[:4].hex(), 'records_a': a, 'records_b72_hex': b,
                'trailer_hex': body[p:].hex()}
    if t == 6:
        days = []
        for d in range(7):
            ents = []
            for i in range(42):
                e = body[(d * 42 + i) * 16:(d * 42 + i) * 16 + 16]
                k, ident, f2, f3, f4, f5, e32 = struct.unpack('<6HI', e)
                ents.append({'kind': k, 'id': ident, 'f2': f2, 'f3': f3, 'f4': f4, 'f5': f5,
                             'u32': e32})
            days.append(ents)
        return {'days': days}
    raise ValueError('bad type')


def pack_body(t, f):
    if t == 1:
        return struct.pack('<HBB', f['item_id'], f.get('pad', 0), f['count'])
    if t == 2:
        sk = list(f.get('skill_ids', [])) + [0] * 6
        return (struct.pack('<IHBB', f['seed'], f['species_id'], f['level_or_plus'], f.get('pad7', 0))
                + struct.pack('<6H', *sk[:6]) + bytes.fromhex(f.get('tail_hex', '00' * 18)))
    if t == 3:
        return struct.pack('<HHI', f['monster_id_a'], f['monster_id_b'], f['seed'])
    if t == 4:
        name = f['name_raw_hex'] if 'name' not in f else None
        nm = (f['name'].encode('utf-16le').ljust(0x1c, b'\0') if name is None else bytes.fromhex(name))
        msg = f['message'].encode('utf-16le').ljust(0x24, b'\0')
        sk = list(f.get('skill_ids', [])) + [0] * 4
        out = (struct.pack('<I', f['seed']) + nm[:0x1c] + struct.pack('<I', f['reward_u32']) + struct.pack('<4H', *sk[:4])
               + struct.pack('<HBB', f['species_id'], f['rank_byte_2e'], f.get('byte_2f', 0)) + msg[:0x24])
        assert len(out) == 84, len(out)
        return out
    if t == 5:
        a, b = f['records_a'], f['records_b72_hex']
        out = bytearray(bytes.fromhex(f['hdr4_hex']))
        out[0], out[1] = len(a), len(b)
        for r in a:
            items = r['items16_hex']
            hdr = bytearray(bytes.fromhex(r['hdr_hex']))
            hdr[3] = len(items)
            out += hdr
            for it in items:
                out += bytes.fromhex(it)
        for r in b:
            out += bytes.fromhex(r)
        out += bytes.fromhex(f.get('trailer_hex', ''))
        return bytes(out)
    if t == 6:
        out = bytearray()
        for d in f['days']:
            assert len(d) == 42
            for e in d:
                out += struct.pack('<6HI', e['kind'], e['id'], e['f2'], e['f3'], e['f4'], e['f5'], e['u32'])
        return bytes(out)
    raise ValueError('bad type')


# ---------------- decode / encode ----------------
def decode(data):
    if data[:4] != b'BSDT':
        raise ValueError('bad magic')
    t, flags, size = data[4], data[5], struct.unpack_from('<H', data, 6)[0]
    if t not in HMAC_KEYS:
        raise ValueError('bad type %d' % t)
    if size != len(data):
        raise ValueError('size field %d != file length %d' % (size, len(data)))
    sig_ok = hmac.compare_digest(_sig(t, data[:size - 32]), data[size - 32:size])
    body = data[8:size - 32]
    if t in XOR_KEYS:
        if len(body) != BODY_LEN[t]:
            raise ValueError('unexpected body length %d' % len(body))
        body = _xor(body, t)
    return {'type': t, 'type_name': NAMES[t], 'flags': flags, 'size': size, 'hmac_ok': sig_ok,
            'body_hex': body.hex(), 'fields': parse_body(t, body)}


def encode(j):
    t = j['type']
    if 'fields' in j and j['fields'] is not None:
        body = pack_body(t, j['fields'])
    else:
        body = bytes.fromhex(j['body_hex'])
    if t in XOR_KEYS:
        if len(body) != BODY_LEN[t]:
            raise ValueError('body length %d != %d' % (len(body), BODY_LEN[t]))
        body = _xor(body, t)
    size = 8 + len(body) + 32
    out = b'BSDT' + struct.pack('<BBH', t, j.get('flags', 0), size) + body
    return out + _sig(t, out)


def main(argv):
    if len(argv) >= 3 and argv[1] == 'decode':
        j = decode(open(argv[2], 'rb').read())
        s = json.dumps(j, indent=1, ensure_ascii=False)
        if len(argv) > 3:
            open(argv[3], 'w', encoding='utf-8').write(s)
        else:
            sys.stdout.buffer.write(s.encode('utf-8') + b'\n')
    elif len(argv) == 4 and argv[1] == 'encode':
        j = json.load(open(argv[2], encoding='utf-8'))
        open(argv[3], 'wb').write(encode(j))
    elif len(argv) >= 3 and argv[1] == 'selftest':
        rc = 0
        for p in argv[2:]:
            d = open(p, 'rb').read()
            j = decode(d)
            j2 = json.loads(json.dumps(j))  # via JSON text
            e1 = encode(j2)
            j2.pop('fields')
            e2 = encode(j2)  # from body_hex only
            ok = e1 == d and e2 == d
            rc |= (not ok)
            print('%-28s type=%d hmac_ok=%s roundtrip=%s' % (p.replace('\\', '/').split('/')[-1], j['type'], j['hmac_ok'], ok))
        return rc
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
