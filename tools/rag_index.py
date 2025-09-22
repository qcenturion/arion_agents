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


import uuid

# Create a consistent namespace for generating deterministic UUIDs from file paths
_DOC_ID_NAMESPACE = uuid.UUID("a6b7a8b3-9e8d-4e6a-8f0c-9e9d8e7f6a5b")


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Index documents into the RAG service.")
    parser.add_argument("corpus_path", type=Path, help="Path to a file or directory of files to index.")
    parser.add_argument("--service-url", type=str, default=os.getenv("RAG_SERVICE_URL", "http://localhost:7100"), help="URL of the RAG service.")
    parser.add_argument("--collection", type=str, default=None, help="Assign documents to this collection.")
    parser.add_argument("--timeout", type=int, default=60, help="Request timeout in seconds.")
    return parser.parse_args()


def main() -> None:
    """Main entrypoint."""
    args = _parse_args()
    if not args.corpus_path.exists():
        print(f"Corpus path not found: {args.corpus_path}")
        sys.exit(1)

    if args.corpus_path.is_dir():
        files = list(args.corpus_path.rglob("*.md"))
        if not files:
            print(f"No markdown files found in {args.corpus_path}")
            sys.exit(1)
    else:
        files = [args.corpus_path]

    documents = []
    for file in files:
        doc_id = str(file.relative_to(args.corpus_path.parent))
        # Generate a deterministic UUIDv5 from the file-based ID
        point_id = str(uuid.uuid5(_DOC_ID_NAMESPACE, doc_id))
        doc = {
            "id": point_id,
            "text": file.read_text(),
            "metadata": {"filename": file.name, "relative_path": doc_id},
        }
        if args.collection:
            doc["collection"] = args.collection
        documents.append(doc)

    url = urljoin(args.service_url, "/index")
    payload = {"documents": documents}
    headers = {"Content-Type": "application/json"}

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=args.timeout)
        resp.raise_for_status()
        result = resp.json()
        print(f"Indexed {result.get('indexed', 0)} document(s) via {url}")
    except requests.RequestException as e:
        print(f"Index request failed ({e.response.status_code if e.response else 'N/A'}): {e}")
        sys.exit(4)




if __name__ == "__main__":
    main()
