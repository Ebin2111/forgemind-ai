"""Database engine, session management and declarative base."""
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from pathlib import Path

from fastapi import Depends
from sqlalchemy import MetaData, create_engine, event, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .core.config import settings

logger = logging.getLogger(__name__)

# Deterministic constraint names keep future Alembic migrations clean.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

_is_sqlite = settings.database_url.startswith("sqlite")


def _ensure_sqlite_dir(url: str) -> None:
    """Create the folder that will hold the SQLite file (a fresh checkout or volume has none)."""
    database = make_url(url).database
    if database and database != ":memory:" and not database.startswith("file:"):
        Path(database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def _build_engine() -> Engine:
    if _is_sqlite:
        _ensure_sqlite_dir(settings.database_url)
        return create_engine(
            settings.database_url,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )
    return create_engine(settings.database_url, pool_pre_ping=True, pool_size=5, max_overflow=10)


engine = _build_engine()

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")  # enforce FK constraints
        cursor.execute("PRAGMA journal_mode=WAL")  # readers don't block the writer
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, rolled back on error."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for scripts and startup tasks: commit on success, rollback on error."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Create tables if they don't exist. Swap for Alembic migrations as the schema grows."""
    from .models import db_models  # noqa: F401  (registers models on Base.metadata)

    Base.metadata.create_all(bind=engine)


def db_status() -> tuple[bool, str | None]:
    """Probe the database. Returns (ok, detail); detail is the error type when it is down.

    Only the exception type is reported and logged (no traceback, no URL), so a probe
    that runs every few seconds neither floods the logs nor leaks connection details.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:
        logger.warning("Database health check failed: %s", type(exc).__name__)
        return False, type(exc).__name__


def check_db() -> bool:
    return db_status()[0]