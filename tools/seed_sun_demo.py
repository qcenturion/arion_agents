#!/usr/bin/env python3
import json
import os
import sys
import time
import requests

# This script seeds the database using the new SQLModel-based API.

API = os.getenv("API_URL", "http://localhost:8000")
SNAPSHOT_FILE = os.path.join(os.path.dirname(__file__), "sun_snapshot.json")
NETWORK_NAME = "sun_demo_from_snapshot"


def post(path: str, json_data):
    return requests.post(f"{API}{path}", json=json_data)


def put(path: str, json_data):
    return requests.put(f"{API}{path}", json=json_data)


def get(path: str):
    return requests.get(f"{API}{path}")


def delete(path: str):
    return requests.delete(f"{API}{path}")


def ensure_ok(r, expected=(200, 201, 204)):
    if not isinstance(expected, (list, tuple)):
        expected = (expected,)
    if r.status_code not in expected:
        print(f"Error {r.status_code} for {r.request.method} {r.request.url}: {r.text}", file=sys.stderr)
        r.raise_for_status()
    return r.json() if r.content else {}


def main():
    # Wait for API to be available
    for _ in range(10):
        try:
            if get("/health").status_code == 200:
                break
        except requests.ConnectionError:
            pass
        time.sleep(2)
    else:
        raise SystemExit("API did not become available in time.")

    print(f"Using API: {API}")
    print(f"Loading snapshot from: {SNAPSHOT_FILE}")

    with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
        snapshot = json.load(f)

    # 1. Clean up previous network if it exists
    print(f"Checking for and cleaning up existing network '{NETWORK_NAME}'...")
    try:
        nets = ensure_ok(get("/config/networks"))
        for n in nets:
            if n["name"] == NETWORK_NAME:
                print(f"Deleting network {n['id']}...")
                ensure_ok(delete(f"/config/networks/{n['id']}"), 204)
    except Exception as e:
        print(f"Cleanup failed, assuming first run: {e}")

    # 2. Create all tools from the snapshot
    print("Creating tools from snapshot...")
    for tool_data in snapshot.get("tools", []):
        tool_data["additional_data"] = tool_data.pop("metadata", {})
        r = post("/config/tools", json_data=tool_data)
        if r.status_code not in (201, 409):
            ensure_ok(r, 201)

    # 3. Create the network
    print(f"Creating network '{NETWORK_NAME}'...")
    net = ensure_ok(post("/config/networks", json_data={"name": NETWORK_NAME}), 201)
    net_id = net["id"]
    print(f"Network id: {net_id}")

    # 4. Add all tools from the snapshot to the network
    tool_keys = [t["key"] for t in snapshot.get("tools", [])]
    if tool_keys:
        print(f"Adding tools to network: {tool_keys}")
        ensure_ok(post(f"/config/networks/{net_id}/tools", json_data={"tool_keys": tool_keys}))

    # 5. Create all agents from the snapshot
    print("Creating agents from snapshot...")
    agent_ids = {}
    agents_from_snapshot = snapshot.get("agents", [])
    for agent_data in agents_from_snapshot:
        # The API now expects the Agent SQLModel directly.
        # We need to prepare the payload accordingly.
        agent_payload = {
            "key": agent_data["key"],
            "allow_respond": agent_data["allow_respond"],
            "is_default": agent_data["key"] == snapshot.get("default_agent_key"),
            "additional_data": {"prompt_template": agent_data.get("prompt", "")}
        }
        agent = ensure_ok(post(f"/config/networks/{net_id}/agents", json_data=agent_payload), 201)
        agent_ids[agent["key"]] = agent["id"]

    # 6. Equip agents with tools and set routes
    print("Configuring agent tools and routes...")
    for agent_data in agents_from_snapshot:
        agent_key = agent_data["key"]
        agent_id = agent_ids[agent_key]
        
        equipped_tools = agent_data.get("equipped_tools", [])
        if equipped_tools:
            print(f"Equipping agent '{agent_key}' with tools: {equipped_tools}")
            ensure_ok(put(f"/config/networks/{net_id}/agents/{agent_id}/tools", json_data={"tool_keys": equipped_tools}))

        allowed_routes = agent_data.get("allowed_routes", [])
        if allowed_routes:
            print(f"Setting routes for agent '{agent_key}': {allowed_routes}")
            ensure_ok(put(f"/config/networks/{net_id}/agents/{agent_id}/routes", json_data={"agent_keys": allowed_routes}))

    print("Seed complete. Skipping publish step as it is under refactoring.")


if __name__ == "__main__":
    main()
