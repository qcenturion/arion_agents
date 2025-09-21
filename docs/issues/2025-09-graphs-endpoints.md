# Issue: Implement Graph Snapshot Endpoints for Frontend

## Context
The Next.js dashboards expect REST endpoints to list published snapshots and fetch individual graph payloads (`GET /snapshots`, `GET /graphs/{graphVersionId}`), plus SSE hooks for live graph focus. The FastAPI surface currently only exposes `/config/*` routes, so the Graphs tab renders 404 errors and cannot hydrate Sigma canvases.

## Scope
- Persist and expose graph metadata separate from `/config`, honoring published `NetworkVersion` and `CompiledSnapshot` records.
- Provide lightweight DTOs aligned with `frontend/lib/api/types.ts` (`SnapshotSummary`, `GraphPayload`).
- Enforce authorization + pagination patterns consistent with other public API routes once defined.

## Tasks
1. Add a FastAPI router (e.g., `api_graphs.py`) wiring:
   - `GET /snapshots` → list recent published snapshots (id, graph_version_id, network_id, created_at).
   - `GET /graphs/{graph_version_id}` → return compiled graph JSON.
2. Reuse existing SQLModel session helpers; add queries that filter by `Network.status = 'published'` and match the requested version.
3. Ensure responses are cacheable (`Cache-Control`) and compatible with React Query defaults.
4. Extend backend tests / smoke script to validate the new endpoints.
5. Once routes land, remove the Graphs TODO warnings from the frontend and confirm the tab loads without 404.

## Out of Scope
- Real-time graph diffing or SSE stream per run (tracked separately).
- Authz/Auditing layers beyond read-only access.
