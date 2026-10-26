"""Wrap a decompressed 3DS code.bin + exheader into an ARM ELF for Ghidra.

usage: codebin_to_elf.py code.bin exheader.bin out.elf
"""
import struct, sys

code = open(sys.argv[1], 'rb').read()
exh = open(sys.argv[2], 'rb').read()
(ta, tpages, tsize, _, ra, rpages, rsize, _, da, dpages, dsize, bss) = struct.unpack('<12I', exh[0x10:0x40])

segs = [  # name, vaddr, file offset in code.bin, size, flags (R=4 W=2 X=1)
    ('.text', ta, 0, tsize, 5),
    ('.rodata', ra, ra - ta, rsize, 4),
    ('.data', da, da - ta, dsize, 6),
]
EHDR, PHDR, SHDR = 52, 32, 40
phoff = EHDR
data_off = (phoff + PHDR * len(segs) + 0xFFF) & ~0xFFF
body = bytearray()
phdrs, shdrs = b'', []
shstr = b'\0'
def name_off(n):
    global shstr
    o = len(shstr); shstr += n.encode() + b'\0'; return o
for name, va, off, size, fl in segs:
    foff = data_off + len(body)
    body += code[off:off + size]
    body += b'\0' * (-len(body) % 0x1000)
    memsz = size + (bss if name == '.data' else 0)
    phdrs += struct.pack('<8I', 1, foff, va, va, size, memsz, fl, 0x1000)
    shflags = 2 | (4 if fl & 1 else 0) | (1 if fl & 2 else 0)  # ALLOC|EXEC|WRITE
    shdrs.append((name_off(name), 1, shflags, va, foff, size, 0, 0, 4, 0))
if bss:
    bva = da + dsize
    shdrs.append((name_off('.bss'), 8, 3, bva, data_off + len(body), bss, 0, 0, 4, 0))
shstr_idx = len(shdrs) + 1
shdrs.append((name_off('.shstrtab'), 3, 0, 0, data_off + len(body), len(shstr), 0, 0, 1, 0))
body += shstr
body += b'\0' * (-len(body) % 4)
shoff = data_off + len(body)
ident = b'\x7fELF' + bytes([1, 1, 1, 0]) + b'\0' * 8
ehdr = ident + struct.pack('<HHIIIIIHHHHHH', 2, 40, 1, ta, phoff, shoff, 0x05000000,
                           EHDR, PHDR, len(segs), SHDR, len(shdrs) + 1, shstr_idx)
out = bytearray(ehdr + phdrs)
out += b'\0' * (data_off - len(out))
out += body
out += b'\0' * SHDR
for s in shdrs:
    out += struct.pack('<10I', *s)
open(sys.argv[3], 'wb').write(out)
print(f'text {ta:#x}+{tsize:#x} ro {ra:#x}+{rsize:#x} data {da:#x}+{dsize:#x} bss {bss:#x} -> {sys.argv[3]}')
