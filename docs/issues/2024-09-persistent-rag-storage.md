# Issue: Persistent Storage for RAG Service

**Date:** 2024-09-19

## Problem
The dev RAG service (`tools/rag_service/service.py`) originally held indexed documents in
memory. Any restart wiped the store, forcing us to re-run `tools/rag_index.py` before
smoke tests. This slowed the loop and hid bugs that only appear with cold caches.

## Goals
- Introduce durable storage (Qdrant with disk-backed volume or equivalent).
- Update the service to write/read from persistence by default.
- Keep tooling (`run_rag_snapshot.sh`, `make rag-demo`) working without manual re-index
  when the service restarts.
- Document how to reset or refresh the index on demand.

## Proposed Steps
1. Provision a Qdrant container with a persistent volume (or managed instance).
2. Refactor the service to use Qdrant instead of the in-memory `_STORE`.
3. Update `tools/rag_index.py` / `tools/rag_search.py` to target the persistent store.
4. Add a reset/reindex switch so we can refresh the corpus when content changes.
5. Update `docs/rag_quickstart.md` + README to describe the persistent setup.

## Notes
- Evaluate whether the runtime should call Qdrant directly (bypassing the service) once
  persistence is in place.
- Ensure smoke tests still exist for a fallback in-memory mode (useful for CI or offline runs).
- The updated service runs Qdrant in embedded mode inside `service.py`, pointing it at a
  configurable storage path (default `./data/qdrant`). Bind that directory as a volume when
  starting the existing FastAPI container so data survives restarts.
- If we later adopt a standalone Qdrant container, reuse the same storage directory and rely
  on its write-ahead log for durability. Snapshots become optional unless we want manual
  checkpoints.
