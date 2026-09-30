"""Database engine / session wiring.

Defaults to a local SQLite file so the prototype runs with zero infrastructure.
Set DATABASE_URL to a PostgreSQL DSN to use the production path.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings

settings = get_settings()

_connect_args: dict = {}
_engine_kwargs: dict = {"echo": settings.sql_echo, "future": True, "pool_pre_ping": True}

if settings.is_sqlite:
    # check_same_thread=False is required because FastAPI serves requests from a
    # thread pool; each request still gets its own Session.
    _connect_args["check_same_thread"] = False

engine: Engine = create_engine(settings.database_url, connect_args=_connect_args, **_engine_kwargs)


@event.listens_for(engine, "connect")
def _configure_sqlite(dbapi_connection, _record):  # noqa: ANN001
    """SQLite ignores foreign keys unless told otherwise - we rely on them."""
    if not settings.is_sqlite:
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for scripts, seeding and background tasks."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
