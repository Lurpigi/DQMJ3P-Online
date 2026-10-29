"""Minimal GDB remote-protocol client for Azahar's GDB stub (Emulation > Configure > Debug).

Sets software breakpoints, lets the game run and, at each hit, prints the registers, a scan of
the stack for return addresses into code.bin, and optional memory dumps; then continues.

usage (python -I): gdbtrace.py ADDR[,ADDR...] [--hits N] [--mem EXPR:LEN ...] [--port 24689]
  EXPR is a register (r0..r15) or hex address, optionally +hex offset, optionally prefixed with *
  to read the pointer stored there: e.g. --mem r0:0x40 --mem *r4+0xa0:0x20 (= *(r4+0xa0))
Breakpoints go into the memory of the process that is running when the client connects (the CPU
halts on connect): connect while the game, not a system applet such as the error display, runs.
"""
import argparse
import re
import socket
import struct

CODE_START, CODE_END = 0x100000, 0x7c0000


class Stub:
    def __init__(self, port):
        self.s = socket.create_connection(("127.0.0.1", port))
        self.buf = b""

    def _byte(self):
        while not self.buf:
            chunk = self.s.recv(65536)
            if not chunk:
                raise EOFError("stub closed the connection")
            self.buf += chunk
        b, self.buf = self.buf[:1], self.buf[1:]
        return b

    def send(self, data, wait=True):
        body = data.encode()
        self.s.sendall(b"$" + body + b"#%02x" % (sum(body) & 0xff))
        return self.recv() if wait else None

    def recv(self):
        while True:
            b = self._byte()
            if b == b"$":
                break
        data = b""
        while (b := self._byte()) != b"#":
            data += b
        self._byte(), self._byte()
        self.s.sendall(b"+")
        return data.decode(errors="replace")

    def regs(self):
        raw = bytes.fromhex(self.send("g"))
        return list(struct.unpack_from("<16I", raw))

    def mem(self, addr, size):
        reply = self.send(f"m{addr:x},{size:x}")
        return bytes.fromhex(reply) if re.fullmatch(r"[0-9a-fA-F]*", reply) else b""


def resolve(stub, regs, expr):
    deref = expr.startswith("*")
    expr = expr.lstrip("*")
    base, _, off = expr.partition("+")
    value = (regs[int(base[1:])] if base.startswith("r") else int(base, 16)) + (int(off, 16) if off else 0)
    if deref:
        value = struct.unpack("<I", stub.mem(value, 4))[0]
    return value


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("addrs", help="code breakpoints, comma separated (may be empty: \"\")")
    ap.add_argument("--watch", action="append", default=[], metavar="ADDR[:LEN]",
                    help="write watchpoint (GDB Z2)")
    ap.add_argument("--hits", type=int, default=1)
    ap.add_argument("--mem", action="append", default=[])
    ap.add_argument("--port", type=int, default=24689)
    args = ap.parse_args()
    addrs = [int(a, 16) for a in args.addrs.split(",") if a]
    watches = [(int(a, 16), int(n or "1", 16)) for a, _, n in (w.partition(":") for w in args.watch)]

    stub = Stub(args.port)  # Azahar halts the CPU when a client connects
    print("status:", stub.send("?"), flush=True)
    for a in addrs:
        print(f"Z0 {a:#x}:", stub.send(f"Z0,{a:x},4"), flush=True)
    for a, n in watches:
        print(f"Z2 {a:#x}:", stub.send(f"Z2,{a:x},{n:x}"), flush=True)
    for hit in range(args.hits):
        stop = stub.send("c")
        regs = stub.regs()
        print(f"\n== hit {hit + 1}: {stop} pc={regs[15]:#x} lr={regs[14]:#x} sp={regs[13]:#x}")
        print(" ".join(f"r{i}={v:08x}" for i, v in enumerate(regs[:13])))
        stack = stub.mem(regs[13], 0x400)
        chain = [f"sp+{i * 4:#x}:{w:#x}" for i, (w,) in enumerate(struct.iter_unpack("<I", stack))
                 if CODE_START <= w < CODE_END and w & 3 == 0]
        print("stack code ptrs:", " ".join(chain[:40]))
        for spec in args.mem:
            expr, _, size = spec.rpartition(":")
            addr = resolve(stub, regs, expr)
            print(f"mem {expr} ({addr:#x}):", stub.mem(addr, int(size, 16)).hex(), flush=True)
        if regs[15] in addrs:  # step over the breakpoint, else "c" stops on it again
            stub.send(f"z0,{regs[15]:x},4")
            stub.send("s")
            stub.send(f"Z0,{regs[15]:x},4")
    for a in addrs:
        stub.send(f"z0,{a:x},4")
    for a, n in watches:
        stub.send(f"z2,{a:x},{n:x}")
    stub.send("D", wait=False)
    print("detached", flush=True)


if __name__ == "__main__":
    main()
