#!/usr/bin/env python3
"""Upload documents to an external RAG service for indexing."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Iterable, List
from urllib.parse import urljoin

import requests


def _collect_files(root: Path, patterns: Iterable[str]) -> List[Path]:
    if root.is_file():
        return [root]
    matches: List[Path] = []
    seen = set()
    for pattern in patterns:
        for path in sorted(root.rglob(pattern.strip())):
            if path.is_file() and path not in seen:
                matches.append(path)
                seen.add(path)
    return matches


def _load_documents(paths: List[Path], base_dir: Path, collection: str | None) -> List[dict]:
    documents: List[dict] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:
            print(f"Failed to read {path}: {exc}", file=sys.stderr)
            continue
        rel = path.relative_to(base_dir)
        doc = {
            "id": rel.as_posix(),
            "text": text,
            "metadata": {
                "filename": path.name,
                "relative_path": rel.as_posix(),
            },
        }
        if collection:
            doc["collection"] = collection
        documents.append(doc)
    return documents


def main() -> None:
    parser = argparse.ArgumentParser(description="Send documents to the RAG service index API")
    parser.add_argument("input", help="File or directory containing documents")
    parser.add_argument("--service-url", required=True, help="Base URL for the RAG service")
    parser.add_argument("--index-path", default="/index", help="Relative path for the index endpoint")
    parser.add_argument(
        "--patterns",
        default="*.txt,*.md",
        help="Comma-separated glob patterns when input is a directory",
    )
    parser.add_argument("--collection", default=None, help="Optional collection identifier")
    parser.add_argument(
        "--api-key", default=None, help="API key or token forwarded to the service"
    )
    parser.add_argument(
        "--api-key-header",
        default="Authorization",
        help="Header name used for the API key",
    )
    parser.add_argument(
        "--extra-payload",
        default=None,
        help="Additional JSON object merged into the index request",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="Request timeout")
    args = parser.parse_args()

    root = Path(args.input).expanduser().resolve()
    if not root.exists():
        print(f"Input path not found: {root}", file=sys.stderr)
        sys.exit(2)

    patterns = [p.strip() for p in args.patterns.split(",") if p.strip()]
    files = _collect_files(root, patterns)
    if not files:
        print("No documents matched the given patterns", file=sys.stderr)
        sys.exit(1)

    documents = _load_documents(files, root if root.is_dir() else root.parent, args.collection)
    payload = {"documents": documents}
    if args.extra_payload:
        try:
            payload.update(json.loads(args.extra_payload))
        except json.JSONDecodeError as exc:
            print(f"Invalid JSON for --extra-payload: {exc}", file=sys.stderr)
            sys.exit(3)

    url = urljoin(args.service_url.rstrip("/") + "/", args.index_path.lstrip("/"))
    headers = {"Content-Type": "application/json"}
    if args.api_key:
        headers[args.api_key_header] = args.api_key

    resp = requests.post(url, json=payload, headers=headers, timeout=args.timeout)
    if resp.status_code >= 400:
        print(f"Index request failed ({resp.status_code}): {resp.text}", file=sys.stderr)
        sys.exit(4)

    print(f"Indexed {len(documents)} document(s) via {url}")


if __name__ == "__main__":
    main()
