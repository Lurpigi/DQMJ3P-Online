"""Persistent local Ghidra query server (keeps the JVM and program loaded).

Run with the ghidra venv:
    ghidra-venv/Scripts/python ghidra_server.py <project_dir> <project_name> <program_path> [port]
Then send Python snippets with gq.py. Snippets run with `program`, `flat`
(FlatProgramAPI) and the helpers below in scope; whatever they print is returned.
Listens on 127.0.0.1 only.
"""
import contextlib, io, os, sys, threading, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pyghidra

pyghidra.start(install_dir=os.environ.get('GHIDRA_INSTALL_DIR'))

from ghidra.app.decompiler import DecompInterface, DecompileOptions  # noqa: E402
from ghidra.program.flatapi import FlatProgramAPI  # noqa: E402
from ghidra.program.model.symbol import SourceType  # noqa: E402
from ghidra.util.task import TaskMonitor  # noqa: E402

proj_dir, proj_name, prog_path = sys.argv[1:4]
port = int(sys.argv[4]) if len(sys.argv) > 4 else 18489
project = pyghidra.open_project(proj_dir, proj_name)
program, consumer = pyghidra.consume_program(project, prog_path)
flat = FlatProgramAPI(program)
listing = program.getListing()
fm = program.getFunctionManager()
refman = program.getReferenceManager()
mem = program.getMemory()
_decomp = DecompInterface()
_decomp.setOptions(DecompileOptions())
_decomp.openProgram(program)
_lock = threading.Lock()


def A(x):
    """Address from int, hex string or symbol name."""
    if not isinstance(x, (int, str)):
        return x
    if isinstance(x, int):
        return flat.toAddr(x)
    try:
        return flat.toAddr(int(x, 16))
    except ValueError:
        syms = list(program.getSymbolTable().getSymbols(x))
        return syms[0].getAddress() if syms else None


def fn(x):
    a = A(x)
    return fm.getFunctionContaining(a) or fm.getFunctionAt(a)


def decomp(x, timeout=60):
    f = fn(x)
    if f is None:
        return print(f'no function at {x}')
    res = _decomp.decompileFunction(f, timeout, TaskMonitor.DUMMY)
    print(res.getDecompiledFunction().getC() if res.decompileCompleted() else res.getErrorMessage())


def xrefs(x, limit=50):
    for i, r in enumerate(refman.getReferencesTo(A(x))):
        if i >= limit:
            break
        f = fm.getFunctionContaining(r.getFromAddress())
        print(r.getFromAddress(), r.getReferenceType(), f.getName() + '@' + str(f.getEntryPoint()) if f else '-')


def strings(sub, limit=50):
    n = 0
    for d in listing.getDefinedData(True):
        if n >= limit:
            break
        v = d.getValue()
        if isinstance(v, str) and sub in v:
            print(d.getAddress(), repr(v[:120]))
            n += 1


def find_bytes(hexstr, limit=20):
    pat = bytes.fromhex(hexstr)
    import jpype
    arr = jpype.JArray(jpype.JByte)([b - 256 if b > 127 else b for b in pat])
    a = mem.getMinAddress()
    for _ in range(limit):
        a = mem.findBytes(a, arr, None, True, TaskMonitor.DUMMY)
        if a is None:
            break
        print(a)
        a = a.add(1)


def rename(x, name):
    f = fn(x)
    tx = program.startTransaction('rename')
    try:
        if f is not None and f.getEntryPoint() == A(x):
            f.setName(name, SourceType.USER_DEFINED)
        else:
            flat.createLabel(A(x), name, True)
    finally:
        program.endTransaction(tx, True)


def comment(x, text):
    tx = program.startTransaction('comment')
    try:
        flat.setPlateComment(A(x), text)
    finally:
        program.endTransaction(tx, True)


def save(msg='update'):
    program.save(msg, TaskMonitor.DUMMY)
    print('saved')


SCOPE = dict(globals())


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        code = self.rfile.read(int(self.headers['Content-Length'])).decode()
        out = io.StringIO()
        with _lock, contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                exec(compile(code, '<gq>', 'exec'), SCOPE)
            except Exception:
                traceback.print_exc()
        body = out.getvalue().encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


print(f'ready on 127.0.0.1:{port}', flush=True)
ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()
