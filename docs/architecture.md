# Architecture Overview

## System Context
- External services: Gemini LLM, HTTP tools, future RAG backend (Qdrant), observability sinks.
- Interfaces: REST control plane (`/config`), runtime execution (`/run`/`/invoke`), Upcoming frontend UI, tooling scripts.
- Data: configuration in Postgres, compiled snapshots (`cfg_compiled_snapshots`), runtime logs in `logs/`.

## Deployment Targets
- Local Dev: FastAPI + Uvicorn with Postgres via docker-compose.
- Production: containerized ASGI app on GCP (Cloud Run or GKE). Postgres (Cloud SQL/AlloyDB) runs separately; runtime only reads compiled snapshots.
- Configuration via env vars (`DATABASE_URL`, `GEMINI_API_KEY`, logging levels). Tracing is optional; file logs are default.

## Runtime Flow
1. Author networks/tools/agents via `/config/*`.
2. Compile snapshots to `cfg_compiled_snapshots`.
3. `/run` loads the snapshot (DB or inline payload), executes the loop, logs detailed artifacts.
4. `/invoke` executes a single validated instruction.

## Control-Plane UI
- CRUD for networks, tools, agents, routes.
- Snapshot history (publish, diff, rollback).
- Run viewer built on `logs/runs/` structure (prompts, raw LLM output, tool log, execution log, final response).
- Tool catalog surfacing provider metadata (e.g., `http:request`, upcoming RAG retriever).

## Tools Layer
- `http:request` provider handles all HTTP integrations via structured metadata (query, headers, body, response shaping).
- Additional providers: hybrid RAG (service-backed retrieval) and any bespoke tools.
- Secrets resolved via `src/arion_agents/secrets.py` (env or `.secrets/` files).

## Logging & Observability
- `logs/server.log` (rotating file) captures prompts, tool requests, LLM responses.
- `logs/runs/*.json` store structured artifacts for each `/run` call.
- `tools/show_last_run.py` provides quick inspection; frontend run viewer will reuse the same schema.

## Hybrid RAG Integration
- Retrieval runs in a dedicated container that handles chunking, embeddings, indexing, and reranking; the runtime calls it via `rag:hybrid` over HTTP.
- Data prep pipeline (document upload, metadata defaults) is tracked in `docs/workstreams/RAG_hybrid_search.md`.
- Runtime integration exposes the retriever as a provider under `rag:hybrid` and forwards queries to the service with agent-validated parameters.

## Open Questions
- Frontend framework choice and hosting (likely React + Vite?).
- Real-time streaming (SSE/WebSocket) for live run inspection beyond static logs.
- Long-term observability (metrics/traces) if we reintroduce OTel.
