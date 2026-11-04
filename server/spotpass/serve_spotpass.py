"""Minimal SpotPass (BOSS npdl) server for DQMJ3P.

The game registers its tasks with direct URLs (no tasksheet on 3DS):
    <base>/p01/nsa/H7btVjYWs7p5dGj6/<TASK>/<file>
and the console's boss module decrypts the downloaded container with its own key, so the
original archived .boss files can be served unchanged.

Content layout: <content_dir>/<TASK>/<file>.boss (+ optional filelist.txt for Last-Modified),
e.g. the extracted archive in re/data/spotpass_archive/canonical.

usage (python -I): serve_spotpass.py <content_dir> [port] [host]
"""
import email.utils
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BOSS_APP_ID = "H7btVjYWs7p5dGj6"
TASKS = {"BREAK01", "BREAK02", "BREAK03", "FGONLYT"}
# /p01/nsa/<app>/<task>/[<country>/][<lang>/]<file>  (optional segments as accepted by Pretendo BOSS)
PATH_RE = re.compile(r"^/p01/nsa/([A-Za-z0-9]{16})/([A-Z0-9]+)/(?:[A-Za-z_]{2,5}/){0,2}([A-Za-z0-9_.]+)$")

content_dir = sys.argv[1]
port = int(sys.argv[2]) if len(sys.argv) > 2 else 8380
host = sys.argv[3] if len(sys.argv) > 3 else "127.0.0.1"
MAX_CONNECTIONS = 64


def updated_time(task, name):
    """Upload time from the archived filelist.txt (name<TAB>...<TAB>size<TAB>unix_time)."""
    try:
        with open(os.path.join(content_dir, task, "filelist.txt"), encoding="utf-8") as f:
            for line in f:
                fields = line.rstrip("\r\n").split("\t")
                if fields[0] == name and fields[-1].isdigit():
                    return int(fields[-1])
    except OSError:
        pass
    return None


class Handler(BaseHTTPRequestHandler):
    timeout = 15  # seconds: a client that stops sending must not hold its thread

    def _resolve(self):
        m = PATH_RE.match(self.path.split("?", 1)[0])
        if not m or m.group(1) != BOSS_APP_ID or m.group(2) not in TASKS:
            return None
        task, name = m.group(2), m.group(3)
        path = os.path.join(content_dir, task, name + ".boss")
        return (task, name, path) if os.path.isfile(path) else None

    def _send(self, body):
        found = self._resolve()
        if found is None:
            self.send_error(404)
            return
        task, name, path = found
        data = open(path, "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        ts = updated_time(task, name)
        if ts:
            self.send_header("Last-Modified", email.utils.formatdate(ts, usegmt=True))
        self.end_headers()
        if body:
            self.wfile.write(data)

    def do_GET(self):
        self._send(True)

    def do_HEAD(self):
        self._send(False)

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[spotpass] {self.client_address[0]} {fmt % args}\n")


class BoundedHTTPServer(ThreadingHTTPServer):
    """Closes connections beyond max_connections at once, so slow clients cannot pile up threads."""

    def __init__(self, address, handler, max_connections):
        super().__init__(address, handler)
        self.slots = threading.BoundedSemaphore(max_connections)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


if __name__ == "__main__":
    print(f"serving {content_dir} on http://{host}:{port}/p01/nsa/{BOSS_APP_ID}/<TASK>/<file>", flush=True)
    BoundedHTTPServer((host, port), Handler, MAX_CONNECTIONS).serve_forever()
