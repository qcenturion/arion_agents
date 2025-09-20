# Workstream: Frontend UI (SPA)

## Goals
- Control plane for agents/tools/routes (CRUD backed by `/config/*`).
- Visualize agent topology (graph) and published snapshots.
- Launch test runs with user-provided input and inspect results.
- Replay execution logs (prompts, LLM responses, tool calls) using the `logs/runs/` schema.
- Surface hybrid RAG tooling once implemented (config + monitoring).

## Decisions
- Framework: React (preferred) or Svelte (TBD).
- Hosting: served from the API container for local dev; static assets for production.
- Data sources: REST (`/config`, `/run`), log files/streaming endpoint (future SSE), optional metrics later.

## Milestones & Tasks
- **M1: UX & Shell**
  - [ ] Wireframes for config panels, run viewer, snapshot history.
  - [ ] SPA shell with routing, auth stubs (if needed).
  - [ ] Build JSON viewer components for `logs/runs` artifacts.
- **M2: Config Editor**
  - [ ] CRUD for agents/tools/networks/routes via REST calls.
  - [ ] Snapshot compile/publish triggers + status badges.
  - [ ] Tool metadata forms (http provider, hybrid rag provider).
- **M3: Run Insights**
  - [ ] Trigger `/run` inline snapshot runs from UI (wrap `serve_and_run` semantics).
  - [ ] Render execution timeline (agent steps + tool calls).
  - [ ] Display prompts/raw LLM output + final response.
  - [ ] Optional SSE/WebSocket to stream live runs once backend supports it.
- **M4: RAG Integration**
  - [ ] Configure hybrid retriever parameters (service URL, collections, auth headers).
  - [ ] Link to `docs/rag_quickstart.md` for ops handbook.
  - [ ] Embed indexing progress + search diagnostics.

## Dependencies
- API endpoints (`/config`, `/run`, `/invoke`).
- File-based logs (`logs/runs/`, `logs/server.log`) until streaming API is available.
- Future SSE endpoint for real-time updates.
- RAG retriever API once implemented (for configuration + monitoring).

## Open Questions
- Authentication/authorization requirements.
- Upload pipeline for documents once RAG tool is ready.
- How to expose diff/compare for snapshot versions.
