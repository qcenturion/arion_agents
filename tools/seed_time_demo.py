#!/usr/bin/env python3
import os
import sys
import requests

API = os.getenv("API_URL", "http://localhost:8000")


def post(path: str, json):
    return requests.post(f"{API}{path}", json=json)


def put(path: str, json):
    return requests.put(f"{API}{path}", json=json)


def get(path: str):
    return requests.get(f"{API}{path}")


def ensure_ok(r, expected=200):
    if r.status_code != expected:
        print(f"Error {r.status_code} for {r.request.method} {r.request.url}: {r.text}", file=sys.stderr)
        r.raise_for_status()
    return r.json() if r.content else {}


def main():
    print(f"Using API: {API}")
    # Create global tool
    print("Creating global time tool 'time'...")
    r = post(
        "/config/tools",
        json={
            "key": "time",
            "display_name": "WorldTime",
            "description": "Fetch UTC and compute TAI",
            "provider_type": "http:worldtimeapi",
            "params_schema": {
                "timezone": {"source": "agent", "required": False, "default": "Etc/UTC"}
            },
        },
    )
    if r.status_code not in (201, 409):
        ensure_ok(r, 201)

    # Create network
    print("Creating network 'time_demo'...")
    r = post("/config/networks", json={"name": "time_demo"})
    if r.status_code == 409:
        net_id = next((n["id"] for n in ensure_ok(get("/config/networks")) if n["name"] == "time_demo"), None)
    else:
        net_id = ensure_ok(r, 201)["id"]
    print("Network id:", net_id)

    # Add tool to network
    ensure_ok(post(f"/config/networks/{net_id}/tools", json={"tool_keys": ["time"]}))

    # Create agents
    triage_prompt = (
        "You are {agent_key}. Tools:\n{tools}\nRoutes:\n{routes}\n"
        "When asked for the current time, USE the 'time' tool first, then RESPOND."
    )
    writer_prompt = (
        "You are {agent_key}. Tools:\n{tools}\nRoutes:\n{routes}\n"
        "RESPOND with the message including UTC and TAI times."
    )
    triage = ensure_ok(post(f"/config/networks/{net_id}/agents", json={"key": "triage", "allow_respond": True, "is_default": True, "prompt_template": triage_prompt}), 201)
    writer = ensure_ok(post(f"/config/networks/{net_id}/agents", json={"key": "writer", "allow_respond": True, "prompt_template": writer_prompt}), 201)

    # Equip triage with time tool
    ensure_ok(put(f"/config/networks/{net_id}/agents/{triage['id']}/tools", json={"tool_keys": ["time"]}))
    # Route triage -> writer
    ensure_ok(put(f"/config/networks/{net_id}/agents/{triage['id']}/routes", json={"agent_keys": ["writer"]}))

    # Publish
    pub = ensure_ok(post(f"/config/networks/{net_id}/versions/compile_and_publish", json={}))
    print("Published version:", pub["version"]) 

    # Run with debug
    out = ensure_ok(
        post(
            "/run",
            json={
                "network": "time_demo",
                "user_message": "What time is it now?",
                "debug": True,
            },
        )
    )
    print("Final:", out.get("final"))
    print("Execution log entries:", len(out.get("execution_log", [])))
    dbg = out.get("debug") or []
    if dbg:
        print("--- First step resolved prompt ---\n", dbg[0].get("prompt", "")[:800])
        print("--- First step raw ---\n", dbg[0].get("raw", "")[:800])


if __name__ == "__main__":
    main()

