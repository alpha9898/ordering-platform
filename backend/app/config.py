"""Runtime configuration, read from environment variables only."""

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

# libpq rejects unknown URI parameters (e.g. Supabase's "supa=..." hint)
_LIBPQ_PARAMS = {"sslmode", "sslrootcert", "connect_timeout", "application_name", "options", "target_session_attrs"}
_LOCAL_DB = "postgresql://postgres@localhost:54329/ordering"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[1] / ".env", extra="ignore")

    # postgresql://user:pass@host:port/db. If unset, POSTGRES_URL (set by the
    # Supabase <-> Vercel integration, transaction pooler) is used.
    database_url: str = ""
    # "null" disables SQLAlchemy pooling (serverless + external pooler).
    # Defaults to "null" automatically on Vercel.
    db_pool: str = ""

    # Optional. When unset, the signing key generated inside the database
    # (platform_secrets.jwt_secret) is used, so no one has to handle it.
    jwt_secret: str | None = None
    session_days: int = 14
    environment: str = "development"  # development | production | test

    # Public demo abuse limits
    chat_msgs_per_min: int = 40
    chat_starts_per_hour_ip: int = 30
    orders_per_hour_ip: int = 12
    login_failures_per_window: int = 20
    login_window_seconds: int = 300

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def pool_mode(self) -> str:
        return self.db_pool or ("null" if os.environ.get("VERCEL") else "queue")

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url or os.environ.get("POSTGRES_URL") or _LOCAL_DB
        parts = urlsplit(url)
        query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if k in _LIBPQ_PARAMS])
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
