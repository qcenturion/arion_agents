#!/usr/bin/env python3
"""Automate the RAG demo network setup against a running API server.

- Registers the RAG tool if missing
- Attaches it to the locations_demo network
- Equips the location_details agent
- Publishes the network
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

API_URL = os.getenv("API_URL", "http://localhost:8000")
SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://localhost:7100")
COLLECTION = os.getenv("RAG_COLLECTION", "city_activities")
NETWORK_NAME = os.getenv("RAG_NETWORK", "locations_demo")
TOOL_KEY = os.getenv("RAG_TOOL_KEY", "city_rag")

SESSION = requests.Session()


@dataclass
class ToolSpec:
    payload: Dict[str, Any]


TOOL_SPEC = ToolSpec(
    payload={
        "key": TOOL_KEY,
        "display_name": "City Activities RAG",
        "description": "Retrieve interesting activities for major cities.",
        "provider_type": "rag:hybrid",
        "params_schema": {
            "query": {"source": "agent", "required": True},
            "top_k": {"source": "agent"},
            "filter": {"source": "agent"},
        },
        "additional_data": {
            "agent_params_json_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "top_k": {"type": "integer", "minimum": 1},
                    "filter": {"type": "object"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            "rag": {
                "service": {
                    "base_url": SERVICE_URL,
                    "search_path": "/search",
                    "timeout": 20,
                    "default_payload": {"collection": COLLECTION},
                },
                "agent_params_json_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "minLength": 1},
                        "top_k": {"type": "integer", "minimum": 1},
                        "filter": {"type": "object"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        },
    }
)


def _request(method: str, path: str, **kwargs) -> requests.Response:
    url = f"{API_URL.rstrip('/')}/{path.lstrip('/')}"
    resp = SESSION.request(method, url, **kwargs)
    if resp.status_code >= 400:
        raise RuntimeError(f"{method} {url} failed: {resp.status_code} {resp.text}")
    return resp


def ensure_tool(spec: ToolSpec) -> None:
    resp = _request("GET", "/config/tools")
    tools = resp.json()
    if any(t.get("key") == spec.payload["key"] for t in tools):
        return
    _request(
        "POST",
        "/config/tools",
        headers={"Content-Type": "application/json"},
        data=json.dumps(spec.payload),
    )


def find_network_id(name: str) -> Optional[int]:
    resp = _request("GET", "/config/networks")
    for net in resp.json():
        if net.get("name") == name:
            return net.get("id")
    return None


def attach_tool(network_id: int, key: str) -> None:
    _request(
        "POST",
        f"/config/networks/{network_id}/tools",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"tool_keys": [key]}),
    )


def equip_agent(network_id: int, tool_keys: list[str]) -> None:
    agents = _request("GET", f"/config/networks/{network_id}/agents").json()
    # pick location_details or the first agent that allows respond
    target = None
    for agent in agents:
        if agent.get("key") == "location_details":
            target = agent
            break
    if not target and agents:
        target = agents[0]
    if not target:
        raise RuntimeError("No agents found in network")
    agent_id = target["id"]
    _request(
        "PUT",
        f"/config/networks/{network_id}/agents/{agent_id}/tools",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"tool_keys": tool_keys}),
    )


def publish_network(network_id: int) -> None:
    _request(
        "POST",
        f"/config/networks/{network_id}/versions/compile_and_publish",
        headers={"Content-Type": "application/json"},
        data="{}",
    )


def main() -> None:
    ensure_tool(TOOL_SPEC)
    net_id = find_network_id(NETWORK_NAME)
    if net_id is None:
        raise RuntimeError(f"Network '{NETWORK_NAME}' not found")
    attach_tool(net_id, TOOL_KEY)
    equip_agent(net_id, [
        "sun",
        "geonames",
        TOOL_KEY,
    ])
    publish_network(net_id)
    print(json.dumps({"network_id": net_id, "tool": TOOL_KEY}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - dev helper
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
