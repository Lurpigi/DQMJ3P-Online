#!/usr/bin/env python3
"""Issue a DQMJ3P online account for Azahar without Pretendo (HLE friends module).

Azahar's HLE friends module gives every player PID 0 and no friends password, so the server
refuses them. An issued account is a personal code.ips: the release Azahar patch plus a fixed PID
from the reserved range and a random 16-character secret (make_url_patch.py --identity). The NEX
server accepts PIDs of that range only when accounts.passwords has their row, so the SQL this tool
writes must be run on the server before the first login. SIL needs nothing: its identity is the
player password.

The registry keeps PID and secret, so a lost patch can be written again. It holds the secrets:
keep it private and out of git. The SQL file holds the player password: delete it once applied.

usage (python -I):
  azahar_identity.py --base release/.../azahar-enhanced/code.ips -o code.ips --sql account.sql [--note NAME]
  azahar_identity.py --base ... -o code.ips --pid PID      # the same account again, no SQL
  psql: docker compose exec -T postgres psql -U dqmj3p dqmj3p < account.sql
"""
import argparse
import csv
import secrets
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_url_patch as patch  # noqa: E402

SECRET_ALPHABET = "abcdefghijkmnpqrstuvwxyz23456789"  # 32 symbols: 16 characters = 80 bits
FIELDS = ["pid", "secret", "created", "note"]


def load_registry(path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def append_registry(path, row):
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, FIELDS, delimiter="\t")
        if new:
            writer.writeheader()
        writer.writerow(row)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True, type=Path,
                    help="release Azahar code.ips (built with --nex-player-password, no --pid-offset)")
    ap.add_argument("-o", "--out", required=True, type=Path, help="personal code.ips to write")
    ap.add_argument("--registry", type=Path, default=Path("azahar_accounts.tsv"),
                    help="private TSV with the issued PIDs and secrets (default: %(default)s)")
    ap.add_argument("--sql", type=Path, help="where to write the SQL that registers a new account")
    ap.add_argument("--pid", type=int, help="write the patch of an account already in the registry")
    ap.add_argument("--note", default="", help="who the account is for (kept in the registry)")
    args = ap.parse_args()

    registry = load_registry(args.registry)
    if args.pid is not None:
        rows = [r for r in registry if int(r["pid"]) == args.pid]
        if not rows:
            sys.exit(f"PID {args.pid} is not in {args.registry}")
        pid, secret = args.pid, rows[0]["secret"]
    else:
        if not args.sql:
            ap.error("a new account needs --sql")
        taken = {int(r["pid"]) for r in registry}
        while True:
            pid = patch.IDENTITY_PID_MIN + secrets.randbelow(patch.IDENTITY_PID_MAX - patch.IDENTITY_PID_MIN + 1)
            if pid not in taken:
                break
        secret = "".join(secrets.choice(SECRET_ALPHABET) for _ in range(patch.IDENTITY_SECRET_LENGTH))

    records = patch.read_ips(args.base.read_bytes())
    patch.apply_identity(records, pid, secret.encode())
    data = patch.write_ips(records)

    if args.pid is None:
        # no ON CONFLICT: a PID that is already taken must fail, not take over the account
        password = patch.player_password(secret.encode())
        args.sql.write_text(f"INSERT INTO accounts.passwords (pid, password) VALUES ({pid}, '{password}');\n",
                            encoding="ascii")
        append_registry(args.registry, {"pid": pid, "secret": secret,
                                        "created": time.strftime("%Y-%m-%d"), "note": args.note})
    args.out.write_bytes(data)
    print(f"PID {pid}, friend code {patch.friend_code(pid):012d}: wrote {args.out}"
          + (f" and {args.sql}" if args.pid is None else ""))


if __name__ == "__main__":
    main()
