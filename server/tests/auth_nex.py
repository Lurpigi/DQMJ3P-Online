"""Player password test for the DQMJ3P NEX server running without DEV mode.

A fake client logs in like the patched game, with LoginEx and the player password as the token:
the first login of a PID stores the password, later logins must match and a client that only
knows the PID gets nowhere. Plain Login must be refused.

usage: python auth_nex.py [host] [auth_port]
Prints the test PID, so it can be removed from accounts.passwords on a shared server.
"""
import hashlib
import os
import random
import sys

import anyio
from nintendo.nex import authentication, backend, common, settings

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 45000


def make_settings():
    s = settings.load("3ds")
    s.configure("5812c478", 31001)
    s["nex.struct_header"] = 1
    return s


def info(token):
    auth = authentication.AuthenticationInfo()
    auth.token = token
    auth.ngs_version = 3
    auth.server_version = 0
    return auth


def player_password():
    return hashlib.md5(os.urandom(16)).hexdigest()[:16]


async def login(pid, password, token):
    """Logs in and registers on the secure server, returns the error text or None."""
    try:
        async with backend.connect(make_settings(), HOST, PORT) as be:
            async with be.login(str(pid), password, auth_info=info(token) if token is not None else None):
                return None
    except Exception as e:
        return repr(e)


async def main():
    pid = random.randint(1000000, 1400000000)
    password = player_password()
    print("test pid", pid)

    error = await login(pid, password, password)
    assert error is None, f"first login: {error}"
    print("[auth] first login registered the password")

    error = await login(pid, password, password)
    assert error is None, f"second login: {error}"
    print("[auth] second login accepted")

    error = await login(pid, player_password(), player_password())
    assert error is not None, "login with another password accepted"
    print("[auth] other password refused:", error)

    attacker = player_password()
    error = await login(pid, attacker, password)
    assert error is not None, "stolen PID accepted without the password"
    print("[auth] right token with wrong key refused:", error)

    for token in ("", "t", "ABCDEF0123456789", "0123456789abcde"):
        error = await login(pid + 1, password, token)
        assert error is not None, f"token {token!r} accepted"
    print("[auth] malformed tokens refused")

    error = await login(pid, password, None)
    assert error is not None, "plain Login accepted"
    print("[auth] plain Login refused:", error)

    print("AUTH TEST OK")


anyio.run(main)
