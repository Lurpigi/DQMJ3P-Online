"""python -m dashboard COMMAND

  serve [--host H] [--port P]   public API, with the importer in the same process (one worker)
  migrate [--wait T1,T2]        apply migrations and grants (DASHBOARD_ADMIN_DB_URL, run as the DB owner;
                                DASHBOARD_IMPORTER_PASSWORD / DASHBOARD_API_PASSWORD create the two roles)
  import-once                   one import cycle (sources -> dashboard tables), then exit
  revise CHAMPIONSHIP REASON    recompute a final GP edition; a new revision only if the standings change
  rename-alias PLAYER OLD NEW   correct a public name (audited in the log; result snapshots keep theirs)
  hide-player PLAYER            data removal request: blank the player's public names everywhere

Maintenance happens over SSH with these commands: the portal has no admin pages and no login.
"""
import argparse
import logging
import os
import sys

from . import db
from .config import Settings


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(prog="python -m dashboard", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8090)
    mig = sub.add_parser("migrate")
    mig.add_argument("--wait", default="", help="comma-separated tables to wait for (created by the NEX server)")
    mig.add_argument("--timeout", type=int, default=180)
    sub.add_parser("import-once")
    revise = sub.add_parser("revise")
    revise.add_argument("championship")
    revise.add_argument("reason")
    rename = sub.add_parser("rename-alias")
    rename.add_argument("player")
    rename.add_argument("old")
    rename.add_argument("new")
    hide = sub.add_parser("hide-player")
    hide.add_argument("player")
    args = ap.parse_args(argv)

    if args.command == "migrate":
        admin = os.environ.get("DASHBOARD_ADMIN_DB_URL") or os.environ.get("DASHBOARD_DB_URL")
        if not admin:
            raise SystemExit("DASHBOARD_ADMIN_DB_URL is not set")
        if args.wait:
            db.wait_for_tables(admin, [t for t in args.wait.split(",") if t], args.timeout)
        db.migrate(admin, os.environ.get("DASHBOARD_IMPORTER_PASSWORD"), os.environ.get("DASHBOARD_API_PASSWORD"))
        return

    settings = Settings.from_env()
    settings.check()
    if args.command == "serve":
        import uvicorn

        from .api import create_app
        uvicorn.run(create_app(settings), host=args.host, port=args.port, workers=1, proxy_headers=settings.trust_proxy,
                    forwarded_allow_ips="*" if settings.trust_proxy else None, timeout_keep_alive=5,
                    limit_concurrency=64, log_level="info", access_log=False)
        return

    from .importer import Importer
    with db.connect(settings.db_url, autocommit=True) as conn:
        if args.command == "import-once":
            Importer(settings).run_once(conn)
        elif args.command == "revise":
            with conn.transaction():
                rev = Importer(settings).revise(conn, args.championship, args.reason)
            print(f"revision {rev}" if rev else "standings unchanged: no new revision")
        elif args.command == "rename-alias":
            with conn.transaction():
                n = conn.execute("UPDATE dashboard.player_aliases SET name = %s WHERE player_id = %s AND name = %s",
                                 (args.new, args.player, args.old)).rowcount
                conn.execute("UPDATE dashboard.players SET display_name = %s WHERE id = %s AND display_name = %s",
                             (args.new, args.player, args.old))
            logging.getLogger("dashboard.audit").info("rename-alias %s %r -> %r (%d aliases)", args.player, args.old, args.new, n)
        elif args.command == "hide-player":
            with conn.transaction():
                conn.execute("UPDATE dashboard.players SET display_name = '', name_search = '', hidden = true WHERE id = %s",
                             (args.player,))
                conn.execute("DELETE FROM dashboard.player_aliases WHERE player_id = %s", (args.player,))
                conn.execute("UPDATE dashboard.entries SET observed_name = '' WHERE player_id = %s", (args.player,))
                conn.execute("UPDATE dashboard.standings SET name = '' WHERE player_id = %s", (args.player,))
                conn.execute("UPDATE dashboard.gcup_best SET team_name = '' WHERE player_id = %s", (args.player,))
                conn.execute("UPDATE dashboard.rounds SET opponent_name = '' WHERE opponent_player_id = %s", (args.player,))
            logging.getLogger("dashboard.audit").info("hide-player %s", args.player)


if __name__ == "__main__":
    sys.exit(main())
