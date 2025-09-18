#!/usr/bin/env python3
"""Simple runner: send one message to a network and print final + execution_log.

Usage examples:
  - python tools/run_message.py --network locations_demo \
      --message "What are the sunrise and sunset times in Singapore?" \
      --system '{"username":"demo"}' --debug

  - API_URL=http://localhost:8000 python tools/run_message.py \
      --network locations_demo --message "Hello" --debug

Environment:
  - API_URL (default: http://localhost:8000)
"""

import argparse
import json
import os
import sys
from typing import Any, Dict

import requests


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one message against a network and print results"
    )
    parser.add_argument(
        "--network", required=True, help="Network name (e.g., locations_demo)"
    )
    parser.add_argument("--message", required=True, help="User message text")
    parser.add_argument(
        "--agent-key", default=None, help="Optional agent key to start with"
    )
    parser.add_argument(
        "--version", type=int, default=None, help="Optional version number"
    )
    parser.add_argument(
        "--system",
        default=None,
        help='JSON for system params (e.g., \'{"username":"demo"}\')',
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug output in API response"
    )
    parser.add_argument(
        "--api-url",
        default=os.getenv("API_URL", "http://localhost:8000"),
        help="Base API URL",
    )
    args = parser.parse_args()

    system_params: Dict[str, Any] = {}
    if args.system:
        try:
            system_params = json.loads(args.system)
        except Exception as e:
            print(f"Invalid --system JSON: {e}", file=sys.stderr)
            sys.exit(2)

    payload: Dict[str, Any] = {
        "network": args.network,
        "user_message": args.message,
        "system_params": system_params,
        "debug": bool(args.debug),
    }
    if args.agent_key:
        payload["agent_key"] = args.agent_key
    if args.version is not None:
        payload["version"] = args.version

    url = f"{args.api_url.rstrip('/')}/run"
    r = requests.post(url, json=payload)
    try:
        data = r.json()
    except Exception:
        print(f"HTTP {r.status_code}: {r.text}", file=sys.stderr)
        r.raise_for_status()
        return

    if r.status_code != 200:
        print(json.dumps(data, indent=2))
        sys.exit(1)

    # Print concise result: final + execution_log
    out = {
        "final": data.get("final"),
        "execution_log": data.get("execution_log"),
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
