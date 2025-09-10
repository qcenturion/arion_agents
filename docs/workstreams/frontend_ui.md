# Workstream: Frontend UI (SPA)

## Goals
- Web UI to manage config and visualize agent flows
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
- M3: Visualization
  - [ ] Network graph of agent routes and tool usage
  - [ ] Deep links to Jaeger traces
