import os
import time
from sqlalchemy import create_engine, text


def test_connect_and_version():
    url = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/arion_agents")
    engine = create_engine(url, future=True)
    # Allow a short wait in case container just started
    for _ in range(10):
        try:
            with engine.connect() as conn:
                version = conn.execute(text("select version()"))
                assert version.scalar() is not None
                return
        except Exception:
            time.sleep(1)
    raise AssertionError("Could not connect to Postgres. Is docker compose db up?")

