import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

TEST_DB_PATH = Path(__file__).parent / "config_test.sqlite"
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

from arion_agents.api import app  # noqa: E402
from arion_agents.config_models import Agent, CompiledSnapshot, Network, NetworkVersion  # noqa: E402
from arion_agents.db import engine, init_db  # noqa: E402


init_db()


@pytest.fixture(autouse=True)
def reset_db() -> None:
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _create_network(session: Session, name: str = "network-1") -> int:
    network = Network(name=name, description="demo")
    session.add(network)
    session.commit()
    session.refresh(network)
    return network.id


def _create_agent(
    session: Session,
    network_id: int,
    key: str,
    *,
    allow_respond: bool = True,
    is_default: bool = False,
) -> int:
    agent = Agent(
        network_id=network_id,
        key=key,
        display_name=key.title(),
        description="",
        allow_respond=allow_respond,
        is_default=is_default,
        additional_data={},
    )
    session.add(agent)
    session.commit()
    session.refresh(agent)
    return agent.id


def test_list_agents_returns_agents(client: TestClient) -> None:
    with Session(engine) as session:
        network_id = _create_network(session)
        agent_id = _create_agent(session, network_id, "triage")

    response = client.get("/config/agents")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    item = payload[0]
    assert item["id"] == agent_id
    assert item["network_id"] == network_id
    assert item["key"] == "triage"
    assert item["display_name"] == "Triage"
    assert item["description"] == ""
    assert item["allow_respond"] is True
    assert item["is_default"] is False
    assert item["prompt_template"] is None
    assert item["equipped_tools"] == []
    assert item["allowed_routes"] == []


def test_list_snapshots_returns_snapshot(client: TestClient) -> None:
    with Session(engine) as session:
        network_id = _create_network(session)
        version = NetworkVersion(network_id=network_id, version=1)
        session.add(version)
        session.commit()
        session.refresh(version)
        snapshot = CompiledSnapshot(
            network_version_id=version.id,
            compiled_graph={"agents": []},
        )
        session.add(snapshot)
        session.commit()
        session.refresh(snapshot)

    response = client.get("/config/snapshots")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    item = payload[0]
    assert item["snapshot_id"] == str(snapshot.id)
    assert item["graph_version_id"] == str(snapshot.network_version_id)
    assert item["network_id"] == str(network_id)
    assert item["created_at"] is not None

    legacy = client.get("/snapshots")
    assert legacy.status_code == 200
    assert legacy.json() == payload


def test_patch_agent_rejects_removing_last_respond(client: TestClient) -> None:
    with Session(engine) as session:
        network_id = _create_network(session)
        agent_id = _create_agent(session, network_id, "triage")

    response = client.patch(
        f"/config/networks/{network_id}/agents/{agent_id}",
        json={"allow_respond": False},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "network_constraint_violation"

    with Session(engine) as session:
        refreshed = session.get(Agent, agent_id)
        assert refreshed is not None
        assert refreshed.allow_respond is True


def test_patch_agent_allows_when_another_can_respond(client: TestClient) -> None:
    with Session(engine) as session:
        network_id = _create_network(session)
        agent_id = _create_agent(session, network_id, "triage")
        _create_agent(session, network_id, "writer", allow_respond=True)

    response = client.patch(
        f"/config/networks/{network_id}/agents/{agent_id}",
        json={"allow_respond": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["allow_respond"] is False
    assert body["prompt_template"] is None

    with Session(engine) as session:
        updated = session.get(Agent, agent_id)
        assert updated is not None
        assert updated.allow_respond is False


def test_default_agent_can_skip_respond(client: TestClient) -> None:
    with Session(engine) as session:
        network_id = _create_network(session)
        default_agent_id = _create_agent(
            session, network_id, "triage", allow_respond=False, is_default=True
        )
        _create_agent(session, network_id, "writer", allow_respond=True)

    response = client.patch(
        f"/config/networks/{network_id}/agents/{default_agent_id}",
        json={"description": "triage agent"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["description"] == "triage agent"
    assert payload["allow_respond"] is False

    with Session(engine) as session:
        refreshed = session.get(Agent, default_agent_id)
        assert refreshed is not None
        assert refreshed.allow_respond is False


def test_list_agents_uses_compiled_prompt_and_default_fallback(client: TestClient) -> None:
    with Session(engine) as session:
        network_id = _create_network(session)
        triage_id = _create_agent(
            session, network_id, "triage", allow_respond=False, is_default=False
        )
        _create_agent(session, network_id, "writer", allow_respond=True, is_default=False)

        triage = session.get(Agent, triage_id)
        assert triage is not None
        triage.description = "Routes requests to specialists."
        session.add(triage)
        session.commit()

        version = NetworkVersion(network_id=network_id, version=1)
        session.add(version)
        session.commit()
        session.refresh(version)

        snapshot = CompiledSnapshot(
            network_version_id=version.id,
            compiled_graph={
                "default_agent_key": "triage",
                "agents": [
                    {
                        "key": "triage",
                        "prompt": "Triage prompt instructions",
                        "description": "Routes requests to specialists.",
                    },
                    {"key": "writer", "prompt": "Writer prompt"},
                ],
                "tools": [],
            },
        )
        session.add(snapshot)
        session.commit()
        session.refresh(snapshot)

        network = session.get(Network, network_id)
        assert network is not None
        network.current_version_id = version.id
        session.add(network)
        session.commit()

    response = client.get("/config/agents")
    assert response.status_code == 200
    payload = response.json()
    triage = next(item for item in payload if item["id"] == triage_id)
    assert (
        triage["prompt_template"]
        == "Routes requests to specialists.\n\nTriage prompt instructions"
    )
    assert triage["is_default"] is True



def test_patch_agent_updates_prompt_template(client: TestClient) -> None:
    with Session(engine) as session:
        network_id = _create_network(session)
        agent_id = _create_agent(session, network_id, "writer", allow_respond=True)

    new_prompt = "You are a writer."
    response = client.patch(
        f"/config/networks/{network_id}/agents/{agent_id}",
        json={"prompt_template": new_prompt},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["prompt_template"] == new_prompt

    with Session(engine) as session:
        agent = session.get(Agent, agent_id)
        assert agent is not None
        assert (agent.additional_data or {}).get("prompt_template") == new_prompt
