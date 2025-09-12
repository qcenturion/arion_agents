from typing import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from arion_agents.api import app
from arion_agents import api_config
from arion_agents.db import Base


def override_db() -> Generator:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[api_config.get_db_dep] = override_db


def test_tool_and_agent_crud_and_assignments():
    client = TestClient(app)

    # Create tools
    r = client.post("/config/tools", json={"name": "TemplateRetrievalTool"})
    assert r.status_code == 201, r.text
    tool_id = r.json()["id"]

    # Create agents
    r = client.post("/config/agents", json={"name": "TriageAgent"})
    assert r.status_code == 201
    agent_id = r.json()["id"]

    r = client.post("/config/agents", json={"name": "HumanRemarksAgent"})
    assert r.status_code == 201
    human_id = r.json()["id"]

    # Assign tools to triage
    r = client.put(f"/config/agents/{agent_id}/tools", json={"tools": ["TemplateRetrievalTool"]})
    assert r.status_code == 200, r.text
    assert r.json()["equipped_tools"] == ["TemplateRetrievalTool"]

    # Assign route triage -> human
    r = client.put(f"/config/agents/{agent_id}/routes", json={"agents": ["HumanRemarksAgent"]})
    assert r.status_code == 200, r.text
    assert r.json()["allowed_routes"] == ["HumanRemarksAgent"]

    # Get triage
    r = client.get(f"/config/agents/{agent_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["equipped_tools"] == ["TemplateRetrievalTool"]
    assert data["allowed_routes"] == ["HumanRemarksAgent"]

