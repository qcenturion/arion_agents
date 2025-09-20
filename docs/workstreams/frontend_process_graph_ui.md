# Workstream: Traversable Process Graph UI

## Purpose & Scope
Design and build the browser application for MVP that acts as the control plane for networks, agents, and tools. The first release must:

- Provide CRUD management against the Postgres-backed `/config` APIs for networks, agents, tools, routes, and snapshots.
- Visualise the currently selected network (graph of agents and routes) with drill-down cards describing each component (prompt, equipped tools, routes, tool definitions).
- Offer an inline runner where an operator selects a network, enters a text prompt, triggers `/run`, and inspects the execution timeline (one bubble per log entry with success/error status, expandable to reveal full prompt/response and tool payloads).
- Support post-run auditing with deterministic layouts and evidence provenance.

Future enhancements (real-time streaming, diff mode) remain on the roadmap but are not required for the initial MVP unless noted.

## Architectural Decisions
| Concern | Decision | Notes |
| --- | --- | --- |
| Framework/runtime | Next.js (App Router) + React + TypeScript | Enables hybrid static/SSR, easy deployment alongside FastAPI, strong DX. |
| Styling/system | Tailwind CSS + Radix UI primitives | Rapid composition, baked-in accessibility, theme tokens for future design system integration. |
| State management | Zustand (client UI state) + TanStack Query (server data + caching) | Keeps local UI concerns isolated and uses battle-tested fetching primitives. |
| Graph rendering | Sigma.js atop Graphology | WebGL rendering with a shared in-memory graph model for selections and playback. |
| Layout | ELK (elkjs) computed server-side, persisted per node | Prevents runtime jitter; front end just reads stored `x`/`y`. |
| Drag & drop | `@dnd-kit/core` | Needed for evidence drawers, pinned panels, future graph editing. |
| Animations | Framer Motion | Drive transitions (timelines, panels, toast notifications) without custom tweening. |
| Event transport | Deferred (initial MVP uses completed run payload). SSE reserved for future live streaming. |
| Accessibility & theming | Radix theming + Tailwind tokens and colour-blind-safe palette | Ensures compliance from day one and avoids rework when design tokens arrive. |

## Data Contracts & Back-End Alignment
The UI assumes the following shapes (mirroring the API work for GraphRAG and run playback):

```ts
// Core graph structures
interface GraphNode {
  id: string;           // Nebula VID (stable)
  label: string;
  type: 'task' | 'decision' | 'subprocess';
  x: number;
  y: number;
  pinned: boolean;
  kpi?: Array<{ name: string; value: number; unit?: string; trend?: 'up' | 'down' | 'flat' }>;
}

interface GraphEdge {
  key: string;          // `${from}->${to}:${type}`
  from: string;
  to: string;
  type: 'NEXT' | 'PERFORMED_BY' | 'REQUIRES' | 'PRODUCES' | 'VIOLATES';
  cond?: string;
  probability?: number;
  avg_ms?: number;
  support?: number;
  evidenceIds?: string[]; // matches Qdrant `{doc_id}:{chunk_id}`
}

// Run playback envelopes
interface RunEnvelope {
  traceId: string;                // W3C traceparent compatible
  seq: number;                    // monotonically increasing
  t: number;                      // epoch ms
  step: 
    | { kind: 'visit_node'; nodeId: string }
    | { kind: 'traverse_edge'; edgeKey: string }
    | { kind: 'attach_evidence'; evidenceIds: string[]; context?: Record<string, unknown> }
    | { kind: 'vector_lookup'; query: string; hits: Array<{ evidenceId: string; score: number }> }
    | { kind: 'cypher'; statement: string; duration_ms: number };
}
```

SSE endpoint contract:
- URL shape: `/runs/{traceId}/stream`
- Event: `run.step`
- Data: JSON stringified `RunEnvelope`
- Reconnect: SSE default; UI resubscribes starting from the last committed `seq`.

REST alignment:
- `GET /graphs/{versionId}` returns `{ nodes: GraphNode[], edges: GraphEdge[] }`.
- `GET /runs/{traceId}` returns `{ traceId, graphVersionId, steps: RunEnvelope[] }` for replay.
- `GET /evidence/{evidenceId}` resolves a Qdrant payload (text, metadata, highlight ranges).

## Application Structure
```
app/
  layout.tsx
  page.tsx                     # default landing: run picker
  runs/
    [traceId]/page.tsx         # playback surface
    [traceId]/diff/[other]/page.tsx
  graphs/
    [graphVersionId]/page.tsx  # static graph inspection
lib/
  api/                         # TanStack Query fetchers
  graph/                       # Graphology helpers
  latency/                     # run timing utilities
components/
  GraphCanvas/                 # Sigma wrapper + overlays
  RunControls/                 # play, pause, seek, keyboard, aria-live
  TraceTimeline/               # vertical timeline with step descriptors
  EvidencePanel/               # tabbed evidence viewer (text, metadata, related runs)
  DiffLegend/
  TraceHeader/                 # trace meta, copy button
  LayoutShell/                 # theming, nav, toasts
stores/
  usePlaybackStore.ts          # Zustand: play state, current seq, speed
  useSelectionStore.ts         # selected node/edge/evidence
```

## Key Feature Flows
### 1. Live Run Playback
1. User selects/launches a run → receives `traceId` + `graphVersionId`.
2. UI fetches graph via TanStack Query and hydrates Graphology store with nodes/edges (positions included).
3. Subscribe to `/runs/{traceId}/stream` SSE endpoint.
4. On `run.step` event: enqueue into immutable `RunLog` (array sorted by `seq`).
5. Zustand `usePlaybackStore` orchestrates play/pause/seek and exposes derived state (current node/edge, upcoming evidence).
6. `GraphCanvas` animates halo/pulse based on the current step; `TraceTimeline` updates with aria-live for screen readers.
7. Evidence steps fetch data on demand (`GET /evidence/{id}`) and populate `EvidencePanel` with skeleton loading.

### 2. Run Diffing
1. User navigates to `/runs/{traceId}/diff/{other}`.
2. UI loads both `RunEnvelope[]` payloads and overlays them in separate playback stores.
3. Graph nodes reuse identical positions (same `graphVersionId`).
4. Divergent edges display badges (colour-coded) in timeline and canvas; `DiffLegend` clarifies semantics.

### 3. Auditing via Trace ID
1. Footer `TraceHeader` exposes trace ID with copy-to-clipboard.
2. On reload with `?trace=...`, the page replays the same run and restores viewport from persisted settings (localStorage: camera target, zoom, pinned panels).

## Accessibility & Performance
- `RunControls` uses semantic buttons with keyboard shortcuts (`Space` toggle, `←/→` seek).
- `TraceTimeline` offers aria-live polite announcements for new steps during live mode; no repeated announcements during scrubbing.
- Colour palette derived from Tailwind config with colour-blind-safe primary/secondary scales; edges use patterns/line styles in addition to colour for distinction.
- `GraphCanvas` batches updates inside `requestAnimationFrame` to avoid re-render storms; Graphology mutations run in worker-friendly chunks if needed.
- SSE reconnection logic resumes from last `seq`; duplicates are ignored by a guard in playback store.

## Testing & Monitoring
- Unit: component tests via Testing Library for `RunControls`, `TraceTimeline`, `EvidencePanel` interactions.
- Integration: Playwright e2e covering playback start/seek, evidence fetch, diff view.
- Smoke scripts: `npm run dev` + mocked SSE stream verifying ≤100 ms UI response (instrumented via `performance.now`).
- Observability: capture `traceId`, `seq`, `step.kind` in browser console telemetry (later shipping to real observability pipeline).

## Implementation Milestones
1. **Foundations**
   - Scaffold Next.js + Tailwind + Radix.
   - Implement theming tokens and layout shell.
  - Integrate TanStack Query + Zustand baseline.
2. **CRUD Panels**
   - Build network/agent/tool CRUD views over `/config/*` endpoints.
   - Support snapshot publish flow (compile + publish buttons with status toasts).
3. **Graph Canvas & Inspector**
   - Load snapshot graph (agents + routes) and render with Sigma.
   - Provide inspector drawer showing agent prompts, equipped tools, and tool definitions.
4. **Run Console (Post-Run Playback)**
   - Implement runner panel with network selector, text box, `Run` button calling `/run`.
   - After completion, render timeline bubbles from returned `execution_log` and `latency` data; colour by status, expand per step for full prompt/response/tool payload.
   - Optional stretch: add SSE subscriber for real-time updates if backend endpoint ready.
5. **Evidence & Logs**
   - Hook evidence IDs to REST lookups (if available) otherwise show raw payload preview.
6. **QA & Accessibility**
   - Accessibility pass (axe-core, keyboard trap checks).
   - Smoke/e2e tests covering CRUD flows and run execution timeline.

## Dependencies & Open Questions
- Back-end must expose the REST/SSE endpoints and honour deterministic node coordinates; see GraphRAG workstream for layout responsibilities.
- Authentication model still TBD (session vs token). Plan for pluggable auth guard around fetchers.
- Need design tokens or reference palette from design team; placeholder theme defined in `tailwind.config.ts`.
- Export format for runs? (JSON download vs PDF) — scope for later unless MVP requires it.

## Alignment With Existing Docs
- Supersedes prior `frontend_ui.md` workstream; merge run playback requirements with latency instrumentation from `docs/issues/2024-09-orchestrator-latency-metrics.md`.
- Coordinates with GraphRAG pipeline (see companion doc) for node/edge/evidence provenance and layout persistence.
