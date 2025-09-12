# Workstream: Frontend UI (SPA)

## Goals
- Control plane for agents/tools/routes (CRUD)
- Visualize topology (graph) and recent runs
- Trigger a run with user-provided input (chat/input box)
- Real-time execution log: agent transitions, tool calls, and results
- Integrate with Jaeger/Grafana views

## Decisions
- Framework: React or Svelte (TBD)
- Timeframe: optional for POC; rely on FastAPI docs and Jaeger UI initially

## Milestones & Tasks
- M1: Design + stubs
  - [ ] UX wireframes for config + flow viewer
  - [ ] Static SPA shell served by API
- M2: Config editor
  - [ ] CRUD for agents/tools via API
  - [ ] Validation and previews
- M3: Visualization & runs
  - [ ] Network graph of agent routes and tool usage
  - [ ] Start run from UI with input payload
  - [ ] Live log view via SSE/WebSocket from `/runs/{run_id}/events`
  - [ ] Deep links to Jaeger traces
