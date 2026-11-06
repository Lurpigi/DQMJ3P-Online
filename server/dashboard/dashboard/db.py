"""PostgreSQL access: connection pools, migrations and database roles."""
import glob
import os
import time

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

MIGRATIONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "migrations")
IMPORTER_ROLE, API_ROLE = "dashboard_importer", "dashboard_api"

# Source tables the importer may read (column lists where the table holds anything private)
SOURCE_GRANTS = [
    ("ranking", "scores", None),
    ("ranking", "common_data", None),
    ("ranking", "gcup_results", None),
    ("ranking", "gcup_weeks", None),
    ("history", "gcup_submissions", None),
    ("history", "gcup_common_data", None),
    ("history", "gcup_editions", None),
    ("history", "gcup_finals", None),
    ("matchmaking", "persistent_gatherings", ("id", "community_type", "attribs", "application_buffer")),
]
# Tables the public API must not read
PRIVATE_TABLES = ("player_sources", "import_checkpoints")


def pool(url, timeout_ms, size=4, name="dashboard"):
    return ConnectionPool(url, min_size=1, max_size=size, open=True, name=name, timeout=5,
                          kwargs={"row_factory": dict_row, "autocommit": True,
                                  "options": f"-c statement_timeout={int(timeout_ms)}"})


def connect(url, **kwargs):
    return psycopg.connect(url, row_factory=dict_row, **kwargs)


def wait_for_tables(url, tables, timeout, log=print):
    """Waits until the NEX server created its tables (it does so at startup)."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            with connect(url, autocommit=True, connect_timeout=5) as conn:
                missing = [t for t in tables if not conn.execute("SELECT to_regclass(%s) AS t", (t,)).fetchone()["t"]]
            if not missing:
                return
        except psycopg.OperationalError as e:
            missing = [str(e).strip()]
        if time.monotonic() > deadline:
            raise SystemExit(f"still missing after {timeout} s: {', '.join(missing)}")
        log(f"waiting for {', '.join(missing)}")
        time.sleep(3)


def migrate(admin_url, importer_password=None, api_password=None, log=print):
    """Applies migrations/*.sql in order, then (re)creates the two roles and their grants. Run with
    the database owner (dashboard-migrate service); the long-running service uses the roles."""
    with connect(admin_url, autocommit=True) as conn:
        conn.execute("CREATE SCHEMA IF NOT EXISTS dashboard")
        conn.execute("CREATE TABLE IF NOT EXISTS dashboard.schema_migrations "
                     "(name text PRIMARY KEY, applied timestamptz NOT NULL DEFAULT now())")
        done = {r["name"] for r in conn.execute("SELECT name FROM dashboard.schema_migrations")}
        for path in sorted(glob.glob(os.path.join(MIGRATIONS, "*.sql"))):
            name = os.path.basename(path)
            if name in done:
                continue
            with conn.transaction():
                conn.execute(open(path, encoding="utf-8").read())
                conn.execute("INSERT INTO dashboard.schema_migrations (name) VALUES (%s)", (name,))
            log(f"applied {name}")
        if importer_password and api_password:
            grant_roles(conn, importer_password, api_password)
            log("roles updated")


def _ensure_role(conn, role, password):
    exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
    verb = "ALTER" if exists else "CREATE"
    conn.execute(sql.SQL(verb + " ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(role), sql.Literal(password)))


def grant_roles(conn, importer_password, api_password):
    _ensure_role(conn, IMPORTER_ROLE, importer_password)
    _ensure_role(conn, API_ROLE, api_password)
    imp, api = sql.Identifier(IMPORTER_ROLE), sql.Identifier(API_ROLE)
    conn.execute(sql.SQL("GRANT USAGE ON SCHEMA dashboard TO {}, {}").format(imp, api))
    conn.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA dashboard TO {}").format(imp))
    conn.execute(sql.SQL("GRANT USAGE ON ALL SEQUENCES IN SCHEMA dashboard TO {}").format(imp))
    tables = [r["tablename"] for r in conn.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'dashboard' AND tablename <> 'schema_migrations'")]
    for table in tables:
        target = sql.Identifier("dashboard", table)
        if table in PRIVATE_TABLES:
            conn.execute(sql.SQL("REVOKE ALL ON {} FROM {}").format(target, api))
        else:
            conn.execute(sql.SQL("GRANT SELECT ON {} TO {}").format(target, api))
    conn.execute(sql.SQL("GRANT SELECT ON dashboard.freshness TO {}").format(api))
    for schema, table, columns in SOURCE_GRANTS:
        if not conn.execute("SELECT to_regclass(%s)", (f"{schema}.{table}",)).fetchone()["to_regclass"]:
            continue  # created later by the NEX server; the next migrate run grants it
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(schema), imp))
        target = sql.Identifier(schema, table)
        if columns:
            conn.execute(sql.SQL("GRANT SELECT ({}) ON {} TO {}").format(
                sql.SQL(", ").join(map(sql.Identifier, columns)), target, imp))
        else:
            conn.execute(sql.SQL("GRANT SELECT ON {} TO {}").format(target, imp))
