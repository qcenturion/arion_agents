# Workstream: Hybrid RAG Service Integration

Status: In Progress
Owner: TBD

## Goal
Expose retrieval-augmented generation through a dedicated service container. The service owns chunking, embeddings, indexing, and search; the runtime simply sends HTTP requests via the `rag:hybrid` provider.

## Phase 1 – Container Capabilities
- [x] Service exposes REST endpoints:
  - `POST /index` accepts batches of documents `{id,text,metadata?,collection?}`.
  - `POST /search` accepts `{query, top_k?, filter?, collection?}` and returns `{matches, context, meta}`.
- [ ] Optional authentication (API key header) handled by the service.
- [ ] Health check endpoint for observability.
- [ ] Expand ops checklist alongside `docs/rag_quickstart.md`.

## Phase 2 – Runtime Integration
- [x] Update `rag:hybrid` tool to proxy queries to the service over HTTP.
- [x] Support per-tool defaults (e.g., collection) via `metadata.rag.service.default_payload`.
- [x] Rework CLI utilities to call the service for indexing/search (`tools/rag_index.py`, `tools/rag_search.py`).
- [ ] Support per-network overrides by patching network tool metadata.

## Phase 3 – Developer Experience
- [x] Document metadata format in `README.md` and `docs/architecture.md`.
- [ ] Provide sample docker-compose file for the service (future work).
- [ ] Add smoke tests that mock the service for CI.

## Deliverables
- Updated runtime module under `src/arion_agents/tools/rag/` that performs HTTP delegation.
- CLI scripts that upload documents and run searches against the service.
- Documentation describing the metadata contract and local workflows.

## Open Questions
- Should indexing support streaming uploads or signed URLs for large corpora?
- What authentication mechanism (API keys vs OAuth) should the service use in production?
- How will we monitor service latency/errors alongside agent executions?
- Do we need per-collection rate limiting or quotas enforced by the service?
