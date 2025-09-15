#!/usr/bin/env python3
"""
End-to-end local run without Docker or Postgres.

Uses SQLite + FastAPI TestClient + stubbed LLM decisions to drive the loop.
Optionally, set USE_LLM=1 to call the real LLM.
"""
import json
import os
from typing import Optional, Tuple

from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./e2e.db")
os.environ.setdefault("PYTHONPATH", "src")


def main() -> None:
    from arion_agents.db import init_db
    from arion_agents.api import app
    from arion_agents.engine.loop import run_loop
    from arion_agents.orchestrator import RunConfig
    from arion_agents.agent_decision import AgentDecision

    # Initialize SQLite schema
    init_db()

    c = TestClient(app)

    def post(path: str, payload: dict):
        r = c.post(path, json=payload)
        if r.status_code >= 300:
            raise RuntimeError(f"POST {path} {r.status_code}: {r.text}")
        return r.json() if r.content else {}

    def put(path: str, payload: dict):
        r = c.put(path, json=payload)
        if r.status_code >= 300:
            raise RuntimeError(f"PUT {path} {r.status_code}: {r.text}")
        return r.json() if r.content else {}

    # Seed minimal sun tool/network/agents
    try:
        post(
            "/config/tools",
            {
                "key": "sun",
                "display_name": "Sunrise/Sunset",
                "description": "Get sunrise and sunset times for a given latitude and longitude.",
                "provider_type": "http:sunapi",
                "params_schema": {
                    "lat": {"source": "agent", "required": True},
                    "lng": {"source": "agent", "required": True},
                },
                "metadata": {
                    "agent_params_json_schema": {
                        "type": "object",
                        "properties": {
                            "lat": {"type": ["string", "number"]},
                            "lng": {"type": ["string", "number"]},
                        },
                        "required": ["lat", "lng"],
                        "additionalProperties": False,
                    }
                },
            },
        )
    except Exception:
        pass

    net = post("/config/networks", {"name": "e2e"})
    net_id = net.get("id") or next(n["id"] for n in c.get("/config/networks").json() if n["name"] == "e2e")
    post(f"/config/networks/{net_id}/tools", {"tool_keys": ["sun"]})

    triage_tmpl = (
        "You are {agent_key}. Tools:\n{tools}\nRoutes:\n{routes}\n"
        "When asked about the sun, USE the 'sun' tool first, then RESPOND."
    )
    writer_tmpl = (
        "You are {agent_key}. Tools:\n{tools}\nRoutes:\n{routes}\n"
        "RESPOND with the message including sunrise and sunset times."
    )
    triage = post(
        f"/config/networks/{net_id}/agents",
        {"key": "triage", "allow_respond": True, "is_default": True, "prompt_template": triage_tmpl},
    )
    writer = post(f"/config/networks/{net_id}/agents", {"key": "writer", "allow_respond": True, "prompt_template": writer_tmpl})
    put(f"/config/networks/{net_id}/agents/{triage['id']}/tools", {"tool_keys": ["sun"]})
    put(f"/config/networks/{net_id}/agents/{triage['id']}/routes", {"agent_keys": ["writer"]})
    post(f"/config/networks/{net_id}/versions/compile_and_publish", {})

    use_llm = os.getenv("USE_LLM", "0").lower() in {"1", "true", "yes"}
    if use_llm:
        # Call the real /run endpoint with debug=true
        out = post(
            "/run",
            {"network": "e2e", "user_message": "When does the sun rise and set for lat 36.7201600 and lng -4.4203400?", "debug": True},
        )
        print(json.dumps(out, indent=2))
        return

    # Offline stubbed LLM decisions path using run_loop directly (no network)

    def get_cfg(agent_key: str) -> RunConfig:
        # Use the API helper to build RunConfig so tools_map/prompts are identical to runtime
        from arion_agents.api import _build_run_config as mk

        return mk("e2e", agent_key, None, True, {})

    calls = {"n": 0}

    def decide_fn(prompt: str, model: Optional[str]) -> Tuple[str, AgentDecision]:
        if calls["n"] == 0:
            calls["n"] += 1
            text = json.dumps(
                {
                    "action": "USE_TOOL",
                    "action_reasoning": "Fetch sunrise/sunset first",
                    "action_details": {"tool_name": "sun", "tool_params": {"lat": 36.7201600, "lng": -4.4203400}},
                }
            )
            return text, AgentDecision.model_validate_json(text)
        else:
            text = json.dumps(
                {
                    "action": "RESPOND",
                    "action_reasoning": "done",
                    "action_details": {"payload": {"message": "ok"}},
                }
            )
            return text, AgentDecision.model_validate_json(text)

    out = run_loop(get_cfg, "triage", "When does the sun rise and set for lat 36.7201600 and lng -4.4203400?", max_steps=5, model=None, decide_fn=decide_fn, debug=True)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()

