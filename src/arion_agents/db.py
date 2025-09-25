import os
from contextlib import contextmanager
from typing import Iterator

from sqlmodel import create_engine, Session
from sqlalchemy.types import JSON as SAJSON

try:
    from sqlalchemy.dialects.postgresql import JSONB as PGJSONB
except ImportError:
    PGJSONB = None

# Default to SQLite for lightweight local dev; override via env for Postgres
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/arion_agents",
)

SQL_ECHO = os.getenv("SQL_ECHO", "false").lower() in {"1", "true", "yes", "debug"}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=SQL_ECHO)

# Expose a JSON type alias that is Postgres JSONB when available, otherwise generic JSON
backend_name = engine.url.get_backend_name()
if backend_name.startswith("postgres") and PGJSONB is not None:
    JSONType = PGJSONB
else:  # sqlite / others
    JSONType = SAJSON

# Enable foreign key enforcement for SQLite (required for ondelete cascades)
if backend_name.startswith("sqlite"):
    try:
        from sqlalchemy import event  # type: ignore

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_con, con_record):  # pragma: no cover
            cur = dbapi_con.cursor()
            try:
                cur.execute("PRAGMA foreign_keys=ON")
            finally:
                cur.close()
    except Exception:
        # Non-fatal if event hook fails; tests may still pass without cascades
        pass


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def init_db() -> None:
    """Create all tables for configured models if missing (dev/MVP bootstrap)."""
    from sqlmodel import SQLModel
    from . import config_models  # noqa: F401
    from . import run_models  # noqa: F401

    SQLModel.metadata.create_all(engine)
