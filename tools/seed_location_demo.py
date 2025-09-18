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
        print(
            f"Error {r.status_code} for {r.request.method} {r.request.url}: {r.text}",
            file=sys.stderr,
        )
        r.raise_for_status()
    return r.json() if r.content else {}


def main():
    print(f"Using API: {API}")

    # Create or ensure global tools: sun and geonames
    print("Ensuring global tool 'sun'...")
    r = post(
        "/config/tools",
        json={
            "key": "sun",
            "display_name": "Sunrise/Sunset",
            "description": "Get sunrise and sunset times for a given latitude and longitude.",
            "provider_type": "http:request",
            "params_schema": {
                "lat": {"source": "agent", "required": True},
                "lng": {"source": "agent", "required": True},
            },
            "additional_data": {
                "http": {
                    "base_url": "https://api.sunrise-sunset.org",
                    "path": "/json",
                    "method": "GET",
                    "query": {"lat": {"source": "agent"}, "lng": {"source": "agent"}},
                    "response": {"unwrap": "results"},
                },
                "agent_params_json_schema": {
                    "type": "object",
                    "properties": {
                        "lat": {"type": ["number", "string"]},
                        "lng": {"type": ["number", "string"]},
                    },
                    "required": ["lat", "lng"],
                    "additionalProperties": False,
                },
            },
        },
    )
    if r.status_code not in (201, 409):
        ensure_ok(r, 201)

    print("Creating global tool 'geonames'...")
    r = post(
        "/config/tools",
        json={
            "key": "geonames",
            "display_name": "GeoNames Search API",
            "description": "Geocode a place name to latitude/longitude via GeoNames.",
            "provider_type": "http:request",
            "params_schema": {
                "q": {"source": "agent", "required": True},
                "username": {"source": "system", "required": True},
                "maxRows": {"source": "agent", "required": False},
                "featureClass": {"source": "agent", "required": False},
            },
            "additional_data": {
                "http": {
                    "base_url": "http://api.geonames.org",
                    "path": "/searchJSON",
                    "method": "GET",
                    "query": {
                        "q": {"source": "agent"},
                        "username": {"source": "system"},
                        "maxRows": {"source": "agent", "default": 10},
                        "featureClass": {"source": "agent"},
                    },
                    "response": {"keys": ["totalResultsCount", "geonames"]},
                },
                "agent_params_json_schema": {
                    "type": "object",
                    "properties": {
                        "q": {"type": "string", "minLength": 1},
                        "maxRows": {"type": "integer", "minimum": 1, "default": 10},
                        "featureClass": {"type": "string"},
                    },
                    "required": ["q"],
                    "additionalProperties": False,
                },
            },
        },
    )
    if r.status_code not in (201, 409):
        ensure_ok(r, 201)

    # Create a network
    print("Creating network 'locations_demo'...")
    r = post(
        "/config/networks",
        json={
            "name": "locations_demo",
            "description": "Routing triage -> location agent with multiple tools",
        },
    )
    if r.status_code == 409:
        # Lookup id
        net_id = next(
            (
                n["id"]
                for n in ensure_ok(get("/config/networks"))
                if n["name"] == "locations_demo"
            ),
            None,
        )
        if not net_id:
            raise SystemExit("Could not resolve existing network 'locations_demo'")
    else:
        net_id = ensure_ok(r, 201)["id"]
    print("Network id:", net_id)

    # Add tools to this network
    ensure_ok(
        post(
            f"/config/networks/{net_id}/tools", json={"tool_keys": ["sun", "geonames"]}
        )
    )

    # Create agents
    triage_prompt = (
        "You are part of an AI assistant network. Your goal is to find the correct specialist agent to route the user's request to.\n"
        "Read the user request, compare against agent goals, and ROUTE_TO_AGENT with the most suitable target."
    )
    location_prompt = (
        "You are a location details agent. Goal: provide users with requested details using the available tools.\n"
        "Follow the ReAct pattern: Think -> Act (USE_TOOL) -> Observe -> (repeat as needed) -> Respond.\n"
        "Some queries may require multiple tool calls (e.g., geocoding then a sun query).\n"
        "After each tool call, the conversation will be routed back to you with the tool response; decide next steps."
    )

    tri_resp = post(
        f"/config/networks/{net_id}/agents",
        json={
            "key": "triage",
            "display_name": "Triage",
            "allow_respond": False,
            "is_default": True,
            "prompt_template": triage_prompt,
        },
    )
    if tri_resp.status_code == 201:
        triage = tri_resp.json()
    elif tri_resp.status_code == 409:
        # Fetch existing
        triage = next(
            (
                a
                for a in ensure_ok(get(f"/config/networks/{net_id}/agents"))
                if a["key"] == "triage"
            ),
            None,
        )
        if not triage:
            triage = ensure_ok(
                post(
                    f"/config/networks/{net_id}/agents",
                    json={"key": "triage", "allow_respond": False},
                ),
                201,
            )
    else:
        ensure_ok(tri_resp, 201)

    loc_resp = post(
        f"/config/networks/{net_id}/agents",
        json={
            "key": "location_details",
            "display_name": "Location Details Agent",
            "allow_respond": True,
            "prompt_template": location_prompt,
        },
    )
    if loc_resp.status_code == 201:
        location = loc_resp.json()
    elif loc_resp.status_code == 409:
        location = next(
            (
                a
                for a in ensure_ok(get(f"/config/networks/{net_id}/agents"))
                if a["key"] == "location_details"
            ),
            None,
        )
        if not location:
            location = ensure_ok(
                post(
                    f"/config/networks/{net_id}/agents",
                    json={"key": "location_details", "allow_respond": True},
                ),
                201,
            )
    else:
        ensure_ok(loc_resp, 201)

    # Equip tools to location_details
    ensure_ok(
        put(
            f"/config/networks/{net_id}/agents/{location['id']}/tools",
            json={"tool_keys": ["sun", "geonames"]},
        )
    )
    # Triage routes to location_details
    ensure_ok(
        put(
            f"/config/networks/{net_id}/agents/{triage['id']}/routes",
            json={"agent_keys": ["location_details"]},
        )
    )

    # Publish
    pub = ensure_ok(
        post(f"/config/networks/{net_id}/versions/compile_and_publish", json={})
    )
    print("Published version:", pub.get("version"))

    # Show graph for verification
    graph = ensure_ok(get(f"/config/networks/{net_id}/graph"))
    print("Agents:")
    for a in graph.get("agents", []):
        print(
            "-",
            a["key"],
            "tools=",
            a.get("equipped_tools"),
            "routes=",
            a.get("allowed_routes"),
        )
        if a.get("prompt_template"):
            print("  prompt:", a.get("prompt_template")[:120].replace("\n", " "), "...")


if __name__ == "__main__":
    main()
