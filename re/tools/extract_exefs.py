import struct, sys
def blz(data):
    w = struct.unpack("<I", data[-8:-4])[0]; enc_len, off_info = w, w
    hdr_len = off_info >> 24; enc_len &= 0xFFFFFF
    inc = struct.unpack('<I', data[-4:])[0]
    out = bytearray(data) + bytearray(inc)
    src = len(data) - hdr_len; dst = len(out); stop = len(data) - enc_len
    while src > stop:
        src -= 1; flags = out[src]
        for _ in range(8):
            if src <= stop: break
            if flags & 0x80:
                src -= 2; v = out[src] | out[src+1] << 8
                n = (v >> 12) + 3; d = (v & 0xFFF) + 3
                for _ in range(n):
                    dst -= 1; out[dst] = out[dst + d]
            else:
                src -= 1; dst -= 1; out[dst] = out[src]
            flags = (flags << 1) & 0xFF
    return bytes(out)
fn, outdir = sys.argv[1], sys.argv[2]
f = open(fn, 'rb')
hs,typ,ver,cs,ts,ms,cont = struct.unpack('<IHHIIIQ', f.read(0x20)[:28])
al = lambda x: (x+63) & ~63
base = al(hs)+al(cs)+al(ts)+al(ms)
f.seek(base); n = f.read(0x400)
exh = n[0x200:0x400]
compressed = exh[0xD] & 1
print('title', exh[:8], 'compressed', compressed)
eo, es = struct.unpack('<II', n[0x1A0:0x1A8])
f.seek(base + eo*0x200); ex = f.read(es*0x200)
for i in range(10):
    name, o, s = struct.unpack('<8sII', ex[i*16:i*16+16])
    name = name.rstrip(b'\0').decode()
    if not name: continue
    d = ex[0x200+o:0x200+o+s]
    if name == '.code' and compressed: d = blz(d)
    open(f'{outdir}/{name.strip(".")}.bin', 'wb').write(d); print(name, len(d))
open(f'{outdir}/exheader.bin','wb').write(exh)
