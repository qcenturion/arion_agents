#!/usr/bin/env python3
"""Upload a batch experiment CSV/JSONL and enqueue runs via the /run-batch API."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Dict

import requests


def _parse_system_params(raw_params: list[str]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for param in raw_params:
        key, sep, raw_value = param.partition("=")
        if not sep:
            raise argparse.ArgumentTypeError(f"Invalid system param '{param}'. Use key=value format.")
        key = key.strip()
        if not key:
            raise argparse.ArgumentTypeError(f"Invalid system param '{param}'. Key cannot be blank.")
        value = raw_value.strip()
        if not value:
            result[key] = ""
            continue
        try:
            result[key] = json.loads(value)
        except json.JSONDecodeError:
            result[key] = value
    return result


def _print_errors(errors: list[dict[str, Any]]) -> None:
    if not errors:
        return
    print("Validation errors:", file=sys.stderr)
    for entry in errors:
        row = entry.get("row")
        message = entry.get("error")
        print(f"  - Row {row}: {message}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Queue a DialogFlow batch experiment")
    parser.add_argument("file", help="Path to CSV or JSONL experiment definition")
    parser.add_argument("--network", required=True, help="Network name to run")
    parser.add_argument("--agent-key", help="Agent key to start (defaults to network default agent)")
    parser.add_argument("--version", type=int, help="Published network version to use")
    parser.add_argument("--model", help="Override model for the run")
    parser.add_argument("--experiment-id", help="Identifier for this experiment (defaults to random UUID)")
    parser.add_argument("--experiment-desc", help="Optional experiment description")
    parser.add_argument("--max-steps", type=int, help="Override orchestrator max steps")
    parser.add_argument(
        "--system-param",
        action="append",
        default=[],
        help="Shared system param in key=value form (value parsed as JSON when possible)",
    )
    parser.add_argument("--api-root", default="http://localhost:8000", help="Base URL for the arion_agents API")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode for the run")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompts when warnings are present")

    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.is_file():
        print(f"File not found: {file_path}", file=sys.stderr)
        return 1

    try:
        shared_params = _parse_system_params(args.system_param)
    except argparse.ArgumentTypeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    experiment_id = args.experiment_id or uuid.uuid4().hex
    api_root = args.api_root.rstrip("/")

    try:
        with file_path.open("rb") as fh:
            resp = requests.post(
                f"{api_root}/run-batch/upload",
                files={"file": (file_path.name, fh)},
                timeout=60,
            )
    except requests.RequestException as exc:
        print(f"Upload failed: {exc}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        print(f"Upload failed (HTTP {resp.status_code}): {resp.text}", file=sys.stderr)
        return 1

    upload_payload = resp.json()
    errors = upload_payload.get("errors") or []
    _print_errors(errors)
    if errors:
        return 1

    warnings = upload_payload.get("warnings") or []
    if warnings and not args.yes:
        print("Warnings detected:", file=sys.stderr)
        for entry in warnings:
            row = entry.get("row")
            message = entry.get("message")
            print(f"  - Row {row}: {message}", file=sys.stderr)
        answer = input("Proceed with launch? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Aborted.")
            return 0

    items = upload_payload.get("items")
    if not isinstance(items, list) or not items:
        print("No experiment items detected after validation.", file=sys.stderr)
        return 1

    preview = upload_payload.get("preview") or []
    print(f"Validated {len(items)} item(s)." )
    if preview:
        shown = preview[: min(3, len(preview))]
        print("Preview (first rows):")
        print(json.dumps(shown, indent=2))

    payload: Dict[str, Any] = {
        "experiment_id": experiment_id,
        "experiment_desc": args.experiment_desc,
        "network": args.network,
        "agent_key": args.agent_key,
        "version": args.version,
        "model": args.model,
        "debug": bool(args.debug),
        "shared_system_params": shared_params,
        "items": items,
    }
    if args.max_steps is not None:
        if args.max_steps <= 0:
            print("--max-steps must be a positive integer", file=sys.stderr)
            return 1
        payload["max_steps"] = args.max_steps

    try:
        response = requests.post(
            f"{api_root}/run-batch",
            json=payload,
            timeout=60,
        )
    except requests.RequestException as exc:
        print(f"Launch failed: {exc}", file=sys.stderr)
        return 1

    if response.status_code != 200:
        print(f"Launch failed (HTTP {response.status_code}): {response.text}", file=sys.stderr)
        return 1

    launch = response.json()
    total_runs = launch.get("total_runs")
    print(
        f"Experiment {launch.get('experiment_id')} queued successfully ({total_runs} run{'s' if total_runs != 1 else ''})."
    )
    if launch.get("experiment_desc"):
        print(f"Description: {launch['experiment_desc']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
