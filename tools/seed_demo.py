#!/usr/bin/env python3
import os
import sys
from typing import Any, Dict

import requests


API = os.getenv("API_URL", "http://localhost:8000")


def post(path: str, json: Dict[str, Any]) -> requests.Response:
    r = requests.post(f"{API}{path}", json=json)
    return r


def put(path: str, json: Dict[str, Any]) -> requests.Response:
    r = requests.put(f"{API}{path}", json=json)
    return r


def get(path: str) -> requests.Response:
    r = requests.get(f"{API}{path}")
    return r


def ensure_ok(r: requests.Response, expected: int = 200) -> Dict[str, Any]:
    if r.status_code != expected:
        print(f"Error {r.status_code} for {r.request.method} {r.request.url}: {r.text}", file=sys.stderr)
        r.raise_for_status()
    return r.json() if r.content else {}


def main() -> None:
    print(f"Using API: {API}")

    # Create a global tool (templater)
    print("Creating global tool 'templater'...")
    r = post(
        "/config/tools",
        json={
            "key": "templater",
            "display_name": "Template Retrieval",
            "description": "Fetches response templates by intent",
            "params_schema": {
                "intent": {"source": "agent", "required": False},
                "customer_id": {"source": "system", "required": True},
            },
        },
    )
    if r.status_code not in (201, 409):
        ensure_ok(r, 201)

    # Create a network
    print("Creating network 'support'...")
    r = post("/config/networks", json={"name": "support"})
    if r.status_code == 409:
        # Fetch networks and find id
        data = ensure_ok(get("/config/networks"))
        net_id = next((n["id"] for n in data if n["name"] == "support"), None)
        if not net_id:
            raise SystemExit("Could not resolve existing network 'support'")
    else:
        net_id = ensure_ok(r, 201)["id"]
    print(f"Network id: {net_id}")

    # Add tool to network
    print("Adding 'templater' tool to network...")
    ensure_ok(post(f"/config/networks/{net_id}/tools", json={"tool_keys": ["templater"]}))

    # Create agents triage and writer
    print("Creating agents 'triage' and 'writer'...")
    triage = ensure_ok(post(f"/config/networks/{net_id}/agents", json={"key": "triage", "allow_respond": True}), 201)
    writer = ensure_ok(post(f"/config/networks/{net_id}/agents", json={"key": "writer", "allow_respond": True}), 201)
    triage_id = triage["id"]
    writer_id = writer["id"]

    # Assign tools to triage
    print("Assigning 'templater' to 'triage'...")
    ensure_ok(put(f"/config/networks/{net_id}/agents/{triage_id}/tools", json={"tool_keys": ["templater"]}))

    # Route triage -> writer
    print("Adding route triage -> writer...")
    ensure_ok(put(f"/config/networks/{net_id}/agents/{triage_id}/routes", json={"agent_keys": ["writer"]}))

    # Compile and publish
    print("Compiling and publishing snapshot...")
    pub = ensure_ok(post(f"/config/networks/{net_id}/versions/compile_and_publish", json={}))
    version = pub["version"]

    # Sanity: invoke RESPOND on triage
    print("Invoking triage RESPOND...")
    inv = ensure_ok(
        post(
            "/invoke",
            json={
                "network": "support",
                "agent_key": "triage",
                "version": version,
                "instruction": {"reasoning": "done", "action": {"type": "RESPOND", "payload": {"ok": True}}},
            },
        )
    )
    print("Invoke result:", inv)
    print("Seed complete.")


if __name__ == "__main__":
    main()

