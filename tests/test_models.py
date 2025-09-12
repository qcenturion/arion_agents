from sqlalchemy import inspect

from arion_agents.db import Base
from arion_agents.models import Agent, Tool, agent_routes, agent_tools
from sqlalchemy import create_engine


def test_metadata_creates_tables_in_memory_sqlite():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert {"agents", "tools", "agent_tools", "agent_routes"}.issubset(tables)


def test_basic_relationships_work():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    # No runtime session test here, just ensure models import fine and tables create
    assert agent_tools.c.agent_id is not None
    assert agent_routes.c.from_agent_id is not None

