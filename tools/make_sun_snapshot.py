#!/usr/bin/env python3
import json
import sys


def main() -> None:
    # Minimal compiled snapshot with sun tool and two agents
    triage_prompt = (
        "You are {agent_key}. Tools:\n{tools}\nRoutes:\n{routes}\n"
        "When asked about the sun, USE the 'sun' tool first, then RESPOND."
    )
    writer_prompt = (
        "You are {agent_key}. Tools:\n{tools}\nRoutes:\n{routes}\n"
        "RESPOND with the message including sunrise and sunset times."
    )
    graph = {
        "agents": [
            {
                "key": "triage",
                "display_name": None,
                "description": None,
                "allow_respond": True,
                "is_default": True,
                "equipped_tools": ["sun"],
                "allowed_routes": ["writer"],
                "metadata": {},
                "prompt": triage_prompt.replace("{agent_key}", "triage")
                .replace(
                    "{tools}",
                    "- sun: Get sunrise and sunset times for a given latitude and longitude.",
                )
                .replace("{routes}", "- writer: "),
            },
            {
                "key": "writer",
                "display_name": None,
                "description": None,
                "allow_respond": True,
                "is_default": False,
                "equipped_tools": [],
                "allowed_routes": [],
                "metadata": {},
                "prompt": writer_prompt.replace("{agent_key}", "writer")
                .replace("{tools}", "(none)")
                .replace("{routes}", "(none)"),
            },
        ],
        "tools": [
            {
                "key": "sun",
                "description": "Get sunrise and sunset times for a given latitude and longitude.",
                "provider_type": "http:request",
                "params_schema": {
                    "lat": {"source": "agent", "required": True},
                    "lng": {"source": "agent", "required": True},
                },
                "secret_ref": None,
                "metadata": {
                    "http": {
                        "base_url": "https://api.sunrise-sunset.org",
                        "path": "/json",
                        "method": "GET",
                        "query": {
                            "lat": {"source": "agent"},
                            "lng": {"source": "agent"},
                        },
                        "response": {"unwrap": "results"},
                    },
                    "agent_params_json_schema": {
                        "type": "object",
                        "properties": {
                            "lat": {"type": ["string", "number"]},
                            "lng": {"type": ["string", "number"]},
                        },
                        "required": ["lat", "lng"],
                        "additionalProperties": False,
                    },
                },
            }
        ],
        "default_agent_key": "triage",
        "adjacency": [{"from": "triage", "to": "writer"}],
        "policy": {},
    }
    path = sys.argv[1] if len(sys.argv) > 1 else "sun_snapshot.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2)
    print(f"Wrote snapshot to {path}")


if __name__ == "__main__":
    main()
