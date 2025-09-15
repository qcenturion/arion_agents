import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.types import JSON as SAJSON
try:
    from sqlalchemy.dialects.postgresql import JSONB as PGJSONB  # type: ignore
except Exception:  # pragma: no cover
    PGJSONB = None  # type: ignore


# Default to local Postgres for dev; override via DATABASE_URL
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/arion_agents",
)


def _engine_kwargs(url: str) -> dict:
    # No special kwargs for Postgres
    return {}


engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True, **_engine_kwargs(DATABASE_URL))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True, class_=Session)

Base = declarative_base()

# Expose a JSON type alias that is Postgres JSONB when available, otherwise generic JSON
backend = engine.url.get_backend_name()
if backend.startswith("postgres") and PGJSONB is not None:
    JSONType = PGJSONB  # type: ignore
else:  # sqlite / others
    JSONType = SAJSON  # type: ignore


@contextmanager
def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create all tables for configured models if missing (dev/MVP bootstrap)."""
    # Import models to register metadata, then create
    from . import config_models  # noqa: F401

    Base.metadata.create_all(bind=engine)
