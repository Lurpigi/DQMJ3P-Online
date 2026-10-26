"""Send a Python snippet to ghidra_server.py and print the result.

usage: gq.py "decomp(0x1234)"     or     gq.py - < snippet.py
"""
import sys, urllib.request

code = sys.stdin.read() if sys.argv[1] == '-' else ' '.join(sys.argv[1:])
port = 18489
req = urllib.request.Request(f'http://127.0.0.1:{port}/', data=code.encode(), method='POST')
sys.stdout.buffer.write(urllib.request.urlopen(req, timeout=600).read())
