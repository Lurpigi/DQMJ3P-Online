"""Settings from the environment (server/.env, docker-compose.yml)."""
import os
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))


def _list(value):
    return [v.strip().rstrip("/") for v in value.split(",") if v.strip()]


@dataclass
class Settings:
    # importer: dashboard writes + narrow source reads; api: SELECT on public dashboard tables only
    db_url: str = ""
    api_db_url: str = ""
    sil_db: str = "/sil-data/sil.sqlite3"
    sil_code: str = "/sil/sil_server.py"
    server_id: str = "dev"
    id_salt: str = ""
    allowed_origins: list = field(default_factory=list)
    import_enabled: bool = True
    import_interval: float = 15.0
    batch_size: int = 500
    catalog: str = os.path.join(HERE, "..", "data", "monsters.json")
    trust_proxy: bool = False   # take the client address from X-Forwarded-For (only behind Caddy)
    rate_limit: int = 300       # requests per minute and client address
    statement_timeout_ms: int = 3000

    @classmethod
    def from_env(cls, env=os.environ):
        db_url = env.get("DASHBOARD_DB_URL", "")
        return cls(
            db_url=db_url,
            api_db_url=env.get("DASHBOARD_API_DB_URL") or db_url,
            sil_db=env.get("DASHBOARD_SIL_DB", cls.sil_db),
            sil_code=env.get("DASHBOARD_SIL_CODE", cls.sil_code),
            server_id=env.get("DASHBOARD_SERVER_ID", "dev"),
            id_salt=env.get("DASHBOARD_ID_SALT", ""),
            allowed_origins=_list(env.get("DASHBOARD_ALLOWED_ORIGINS", "")),
            import_enabled=env.get("DASHBOARD_IMPORT", "1") != "0",
            import_interval=float(env.get("DASHBOARD_IMPORT_INTERVAL", "15")),
            batch_size=int(env.get("DASHBOARD_BATCH_SIZE", "500")),
            catalog=env.get("DASHBOARD_CATALOG", cls.catalog),
            trust_proxy=env.get("DASHBOARD_TRUST_PROXY", "0") == "1",
            rate_limit=int(env.get("DASHBOARD_RATE_LIMIT", "300")),
        )

    def check(self):
        if not self.db_url:
            raise SystemExit("DASHBOARD_DB_URL is not set")
        if self.server_id != "dev" and len(self.id_salt) < 16:
            raise SystemExit("DASHBOARD_ID_SALT must be set (16+ characters) outside development: "
                             "public player ids are derived from it and must stay stable")
