"""Database engine and session handling."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from .config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    s = get_settings()
    kwargs: dict = {
        "future": True,
        # prepare_threshold=None keeps psycopg compatible with pgbouncer/Supabase pooler
        "connect_args": {"prepare_threshold": None},
    }
    if s.pool_mode == "null":
        kwargs["poolclass"] = NullPool
    else:
        kwargs.update(pool_size=5, max_overflow=5, pool_pre_ping=True)
    return create_engine(s.sqlalchemy_url, **kwargs)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Request-scoped session. Endpoints commit explicitly; anything
    left uncommitted is rolled back when the request ends."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()
