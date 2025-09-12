import os
import pytest
from fastapi.testclient import TestClient

from arion_agents.api import app
from arion_agents.db import init_db


@pytest.fixture(scope="session", autouse=True)
def ensure_postgres():
    url = os.getenv("DATABASE_URL")
    if not url or "postgresql" not in url:
        pytest.skip("DATABASE_URL must point to Postgres for integration tests")
    # Initialize schema once
    init_db()


def test_config_workflow_and_publish_and_invoke():
    client = TestClient(app)

    # Create global tool
    r = client.post(
        "/config/tools",
        json={
            "key": "templater",
            "display_name": "Template Retrieval",
            "params_schema": {"intent": {"source": "agent", "required": False}, "customer_id": {"source": "system", "required": True}},
        },
    )
    assert r.status_code == 201, r.text

    # Create network
    r = client.post("/config/networks", json={"name": "support"})
    assert r.status_code == 201, r.text
    net_id = r.json()["id"]

    # Add tool to network
    r = client.post(f"/config/networks/{net_id}/tools", json={"tool_keys": ["templater"]})
    assert r.status_code == 200, r.text

    # Create agents
    r = client.post(f"/config/networks/{net_id}/agents", json={"key": "triage", "allow_respond": True})
    assert r.status_code == 201, r.text
    triage_id = r.json()["id"]

    r = client.post(f"/config/networks/{net_id}/agents", json={"key": "writer", "allow_respond": True})
    assert r.status_code == 201, r.text
    writer_id = r.json()["id"]

    # Assign tools to triage
    r = client.put(
        f"/config/networks/{net_id}/agents/{triage_id}/tools",
        json={"tool_keys": ["templater"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["equipped_tools"] == ["templater"]

    # Assign route triage -> writer
    r = client.put(
        f"/config/networks/{net_id}/agents/{triage_id}/routes",
        json={"agent_keys": ["writer"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["allowed_routes"] == ["writer"]

    # Compile and publish snapshot
    r = client.post(f"/config/networks/{net_id}/versions/compile_and_publish", json={})
    assert r.status_code == 200, r.text

    # Invoke using snapshot: RESPOND action should be allowed
    r = client.post(
        "/invoke",
        json={
            "network": "support",
            "agent_key": "triage",
            "instruction": {"reasoning": "done", "action": {"type": "RESPOND", "payload": {"ok": True}}},
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()["result"]
    assert data["status"] == "ok"

