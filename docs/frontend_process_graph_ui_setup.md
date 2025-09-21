# Frontend Control Plane Setup

The Next.js application that implements the process graph UI lives in `frontend/`. It provides the operator console, graph playback, and CRUD panels defined in `docs/workstreams/frontend_process_graph_ui.md`.

## Prerequisites
- Node.js 18+
- Yarn, pnpm, or npm (the project ships with npm scripts)
- Running FastAPI backend (locally via `make run-api` or `make run-api-sqlite`)

## Installation
```bash
cd frontend
npm install
```

Install commands respect `.npmrc` if present. You can also substitute `yarn install` or `pnpm install`.

## Environment Variables
The UI expects an API endpoint that mirrors the `/config`, `/graphs`, `/runs`, and `/evidence` routes:
- `NEXT_PUBLIC_API_BASE_URL` — defaults to `http://localhost:8000` when unset. Override this to point at a remote control plane.
- `API_BASE_URL` — optional server-side override (useful for Next.js edge/server functions).
- Backend CORS: set `CORS_ALLOW_ORIGINS` on the FastAPI service (comma-separated origins, default `http://localhost:3000`) so the browser can call the API directly.

Set them in a `.env.local` file:
```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## Development Workflow
```bash
npm run dev
```

This starts Next.js on port 3000 with fast refresh. Pair it with `make dev` (FastAPI hot reload) to exercise the live run playback.

Useful npm scripts:
- `npm run dev` — development server
- `npm run build` — production bundle
- `npm run start` — run the production build locally
- `npm run lint` — Next.js ESLint checks
- `npm run typecheck` — TypeScript project validation

## Feature Overview
- **Run Console** (`/`) — trigger `/run` requests, inspect execution logs, and preview evidence payloads inline.
- **Run Playback** (`/runs/[traceId]`) — timeline playback with SSE support, sigma.js graph overlay, and evidence inspector.
- **Run Diff** (`/runs/[traceId]/diff/[other]`) — side-by-side comparison of envelope sequences with mismatch highlighting.
- **Graph Explorer** (`/graphs`) — list available snapshots and drill down into graph layouts.
- **Config Workbench** (`/config`) — read-only CRUD views for networks, agents, tools, and snapshots.

## Testing & QA
Frontend tests will live under `frontend/`:
- Component tests (React Testing Library) for run controls, timeline, and evidence viewer.
- Playwright end-to-end coverage for run playback and config CRUD flows.

Add test scripts once dependencies are installed:
```bash
npm run test
```
(placeholder — wiring detailed test commands is tracked separately.)

## Integration Notes
- SSE subscriptions are encapsulated in `subscribeToRunSteps` and resume from the last known sequence number.
- Graph layouts honour persisted `x`/`y` coordinates from the backend; the UI does not recompute ELK layouts client-side.
- Evidence fetches are deferred and cached via TanStack Query, ensuring deterministic replay for audits.
