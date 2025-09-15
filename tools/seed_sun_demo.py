#!/usr/bin/env python3
import os
import sys
import time
import requests

API = os.getenv("API_URL", "http://localhost:8000")


def post(path: str, json):
    return requests.post(f"{API}{path}", json=json)


def put(path: str, json):
    return requests.put(f"{API}{path}", json=json)


def get(path: str):
    return requests.get(f"{API}{path}")


def delete(path: str):
    return requests.delete(f"{API}{path}")



def ensure_ok(r, expected=200):
    if r.status_code != expected:
        print(f"Error {r.status_code} for {r.request.method} {r.request.url}: {r.text}", file=sys.stderr)
        r.raise_for_status()
    return r.json() if r.content else {}


def main():
    time.sleep(10)
    print(f"Using API: {API}")

    # Clean up previous runs
    print("Cleaning up previous runs...")
    try:
        nets = ensure_ok(get("/config/networks"))
        for n in nets:
            if n["name"] == "sun_demo":
                print(f"Deleting agents from network {n['id']}...")
                agents = ensure_ok(get(f"/config/networks/{n['id']}/agents"))
                for a in agents:
                    ensure_ok(delete(f"/config/networks/{n['id']}/agents/{a['id']}"), 204)
                print(f"Deleting network {n['id']}...")
                ensure_ok(delete(f"/config/networks/{n['id']}"), 204)
    except Exception as e:
        print(f"Cleanup failed, assuming first run: {e}")

    # Create global tool
    print("Creating global time tool 'time'...")
    r = post(
        "/config/tools",
        json={
            "key": "sun",
            "display_name": "Sunrise/Sunset",
            "description": "Get sunrise and sunset times for a given latitude and longitude.",
            "provider_type": "http:sunapi",
            "params_schema": {
                "lat": {"source": "agent", "required": False, "default": "36.7201600"},
                "lng": {"source": "agent", "required": False, "default": "-4.4203400"},
            },
            "metadata": {
                "agent_params_json_schema": {
                    "type": "object",
                    "properties": {
                        "lat": {
                            "type": "string",
                            "description": "Latitude. Defaults to Malaga, Spain if not provided.",
                            "default": "36.7201600",
                        },
                        "lng": {
                            "type": "string",
                            "description": "Longitude. Defaults to Malaga, Spain if not provided.",
                            "default": "-4.4203400",
                        },
                    },
                }
            },
        },
    )
    if r.status_code not in (201, 409):
        ensure_ok(r, 201)

    # Create network
    print("Creating network 'sun_demo'...")
    r = post("/config/networks", json={"name": "sun_demo"})
    if r.status_code == 409:
        net_id = next((n["id"] for n in ensure_ok(get("/config/networks")) if n["name"] == "sun_demo"), None)
    else:
        net_id = ensure_ok(r, 201)["id"]
    print("Network id:", net_id)

    # Add tool to network
    ensure_ok(post(f"/config/networks/{net_id}/tools", json={"tool_keys": ["sun"]}))

    # Create agents
    triage_prompt = (
        "You are {agent_key}. Tools:\n{tools}\nRoutes:\n{routes}\n"
        "When asked about the sun, you MUST USE the 'sun' tool. Do not ask for more information."
    )
    writer_prompt = (
        "You are {agent_key}. Tools:\n{tools}\nRoutes:\n{routes}\n"
        "RESPOND with the message including sunrise and sunset times."
    )
    triage = ensure_ok(post(f"/config/networks/{net_id}/agents", json={"key": "triage", "allow_respond": True, "is_default": True, "prompt_template": triage_prompt}), 201)
    writer = ensure_ok(post(f"/config/networks/{net_id}/agents", json={"key": "writer", "allow_respond": True, "prompt_template": writer_prompt}), 201)

    # Equip triage with sun tool
    ensure_ok(put(f"/config/networks/{net_id}/agents/{triage['id']}/tools", json={"tool_keys": ["sun"]}))
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
                "network": "sun_demo",
                "user_message": "When does the sun rise and set?",
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
