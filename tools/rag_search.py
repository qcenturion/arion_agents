#!/usr/bin/env python3
"""Query the external RAG service and print results."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests


def _load_query(args: argparse.Namespace) -> str:
    if args.query:
        return args.query
    if args.query_file:
        path = Path(args.query_file).expanduser().resolve()
        if not path.is_file():
            raise SystemExit(f"Query file not found: {path}")
        return path.read_text(encoding="utf-8")
    raise SystemExit("Provide --query or --query-file")


def main() -> None:
    parser = argparse.ArgumentParser(description="Call the RAG service search API")
    parser.add_argument("--service-url", required=True, help="Base URL for the RAG service")
    parser.add_argument("--search-path", default="/search", help="Relative path for the search endpoint")
    parser.add_argument("--query", default=None, help="Inline query text")
    parser.add_argument("--query-file", default=None, help="File containing the query text")
    parser.add_argument("--top-k", type=int, default=None, help="Optional top_k override")
    parser.add_argument("--collection", default=None, help="Optional collection identifier")
    parser.add_argument(
        "--filter",
        default=None,
        help="JSON filter forwarded to the service",
    )
    parser.add_argument(
        "--extra-payload",
        default=None,
        help="Additional JSON merged into the request body",
    )
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--api-key-header", default="Authorization")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    query = _load_query(args)
    payload = {"query": query}
    if args.top_k is not None:
        payload["top_k"] = max(1, args.top_k)
    if args.collection:
        payload["collection"] = args.collection
    if args.filter:
        try:
            payload["filter"] = json.loads(args.filter)
        except json.JSONDecodeError as exc:
            print(f"Invalid filter JSON: {exc}", file=sys.stderr)
            sys.exit(2)
    if args.extra_payload:
        try:
            payload.update(json.loads(args.extra_payload))
        except json.JSONDecodeError as exc:
            print(f"Invalid JSON for --extra-payload: {exc}", file=sys.stderr)
            sys.exit(3)

    url = urljoin(args.service_url.rstrip("/") + "/", args.search_path.lstrip("/"))
    headers = {"Content-Type": "application/json"}
    if args.api_key:
        headers[args.api_key_header] = args.api_key

    resp = requests.post(url, json=payload, headers=headers, timeout=args.timeout)
    if resp.status_code >= 400:
        print(f"Search request failed ({resp.status_code}): {resp.text}", file=sys.stderr)
        sys.exit(4)

    try:
        data = resp.json()
    except json.JSONDecodeError:
        print(resp.text)
        sys.exit(0)

    print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
