# Issue: Add Graphical Run Flow Visualization

## Context
The Runs tab now offers a structured timeline view that lists every agent and tool step in sequence. Operators have asked for a faster way to grok a run at a glance. We want to complement the existing list with a graphical layout that uses icons and directional arrows to show the progression across agents, routes, and tool executions.

Key open items before committing to implementation:
- Confirm whether the frontend already depends on a graph/diagram library (e.g., in `GraphCanvas` components) that could be reused.
- Identify a small icon set (robot for agents, wrench for tools, etc.) that matches the Arion visual language and licensing.
- Align with design on layout conventions (horizontal vs vertical flow, handling long runs, mobile fallback).

## Requested Enhancements
1. **Visualization Research**
   - Audit the existing frontend codebase for diagram/graph utilities we can repurpose.
   - If nothing suitable exists, evaluate lightweight libraries that support step-based flows (consider bundle size and interactivity needs).

2. **Graphical Run Flow Toggle**
   - Introduce a toggle within the Runs tab that lets operators switch between the current list view and a new graphical view.
   - Ensure the toggle state is obvious and persists per session if possible.

3. **Iconography & Styling**
   - Source or design icons for agent steps (robot) and tool steps (wrench or similar) with clear success/error status treatments.
   - Define arrow/link styling to indicate direction and branching between steps.

4. **Data Parity**
   - The graphical view must consume the same step data the timeline already uses so both views stay in sync.
   - Handle the same status states (success, failure, unknown) visually.

## Deliverables / Next Steps
- Document findings on available libraries/components and propose one (or a custom approach) in a follow-up RFC.
- Produce a low-fidelity mock (screenshot or Figma link) illustrating the step icons, arrows, and status treatments.
- Outline the integration plan for the toggle, including any additional API or store changes.
- Track open questions (e.g., handling runs with >50 steps, zooming/filter options) for later scoping.

_No implementation work should start until this research issue is resolved._

---

## Research Notes — 2025-09-09

### Existing Surfaces & Data
- Timeline list (`frontend/components/TraceTimeline/TraceTimelinePanel.tsx`) renders from `RunEnvelope[]` stored in `usePlaybackStore`, already enriched with agent/tool summaries and status labels.
- The Run page (`frontend/app/runs/[traceId]/page.tsx`) currently pairs the timeline with a static network `GraphViewer` sidebar that uses Sigma.js + graphology for graph rendering, backed by `frontend/lib/graph` helpers.
- Stores used for selection (`useSelectionStore`) and playback state already expose the cursor, step metadata, and evidence ids we would need for hover/click sync in a graphical mode.

### Graph/Diagram Library Audit
- **Keep / extend Sigma.js (existing)**: already bundled (`~90 kB gzip` via sigma + graphology). Supports custom node/edge reducers for color, size, and hover, and we control layout inputs. Limitation: sprite-based icons require either custom node renderer or small background images, but avoids any new dependency and preserves consistent graph controls.
- **elkjs (already in package.json)**: hierarchical layout engine (MIT). Currently unused, but can give us vertical/left-to-right DAG layouts for a run flow once we transform `RunEnvelope` sequences into nodes/edges. Would run client-side during graph build and feed coordinates into Sigma.
- **React Flow**: purpose-built for flow diagrams with built-in node components and minimap. Pros: quick to get arrows, zoom, and custom JSX nodes; cons: adds ~160 kB gzip (core + style), introduces another state model, and duplicates functionality we already ship with Sigma.
- **Dagre / Dagre-D3**: small (~30 kB) layout helper, but still needs a rendering surface (Canvas/SVG) and custom plumbing—we would effectively be rebuilding sigma-like behavior.

**Recommendation:** reuse the Sigma + graphology stack we already ship, layered with elkjs for layout. This keeps the bundle stable, lets us reuse selection/highlight logic, and only requires incremental work to map run steps into a DAG.

### Data Parity Considerations
- `RunEnvelope.step.kind` covers both agent log entries and system events (tool invocations, evidence attachments, graph traversals). We can represent each envelope as a graph node, grouping sequential actions into swimlanes for the actor to keep in sync with timeline semantics.
- Status coloring can be sourced from the existing `summarizeAgentPayload` / `summarizeToolPayload` helpers so both views share success/failure heuristics and duration annotations.
- For long runs, we can paginate virtually by collapsing node groups past a configurable threshold (e.g., show first 25 nodes, group the rest) while keeping the underlying data identical to the timeline list.

### Iconography Options
- **lucide-react (MIT)**: matches current Tailwind-driven line icon aesthetic, includes `Robot`, `Wrench`, `ArrowRight`, etc. Adds ~35 kB gzip imported per-icon tree-shaken. Would require adding the dependency.
- **Radix Icons (MIT)**: already stylistically close to other UI primitives; has `PersonIcon`, `MixerHorizontalIcon`, etc. Slightly more geometric, fewer metaphors (no robot). Could be added as dependency or copied individually.
- **Inline SVG sprites**: keep dependency-free by curating two bespoke 24×24 SVGs that we drop under `frontend/components/icons/`. Requires upfront design time but gives us total control over weight/thickness.

Given the existing reliance on Radix for primitives, adding `@radix-ui/react-icons` keeps licensing simple, but lucide offers the exact metaphors requested (robot/wrench). Need product/design input on preferred style.

### Status Styling
- Success/failure colors can reuse Tailwind tokens already defined in `globals.css` (`--color-success`, `--color-danger`). Unknown/queued state can mirror the current timeline neutral (`foreground/25`).
- Edge arrows can adopt `--color-primary` for active paths and `--color-muted` for inactive branches to maintain contrast in dark theme.

## Low-Fidelity Mock (ASCII wireframe)

```
┌──────────────────────────────────────────────────────────────┐
│ Run Flow (Graph View)                                        │
│                                                              │
│ Robot🤖 Agent Atlas   ──▶  Wrench🔧 Tool: WebSearch ──▶  Robot🤖 Agent Atlas
│    (Route, success)             (Duration 1.2s, success)        (Respond, success)
│           │
│           └─▶ Robot🤖 Agent Bifrost ──▶ Wrench🔧 Tool: CRM Sync (failure)
│                            │
│                            └─▶ Evidence Attachment (neutral)                     
│                                                              │
│ Legend:  success = emerald, failure = danger, unknown = slate │
└──────────────────────────────────────────────────────────────┘
```

*(Emoji placeholders indicate planned icons; final will use consistent 24×24 SVGs.)*

## Integration Plan (proposed)
- Add a view toggle (`Graph` / `Timeline`) to `RunPlayback`, persisted via `zustand` with `persist` middleware (localStorage key `arion.runView`) so each operator keeps their preference per session.
- Build a `RunFlowGraph` client component that:
  - Transforms `RunEnvelope[]` into a directed graph model grouped by actor/tool, with elkjs generating a top-to-bottom layout.
  - Pipes the resulting nodes/edges into Sigma leveraging existing `buildGraphModel` patterns (or a specialized variant to avoid mutating network graph code).
  - Mirrors selection and hover behavior with the timeline by wiring into `usePlaybackStore` / `useSelectionStore`.
- Extend the playback store (or companion selector) to surface derived metadata (step duration, status) once so both views consume identical data.
- Introduce icon components (either via new dependency or inline SVGs) and status badge styles shared between list and graph views for consistency.
- Gate the existing sidebar `GraphViewer` behind the timeline mode (or collapse it when in graph mode) to avoid double-graph overload on smaller screens.

## Open Questions
- (none currently)

### Resolved Decisions (2025-09-09)
- Icon source: proceed with `lucide-react` for robot/wrench metaphors; keep Radix in reserve for supplemental glyphs if needed.
- Node granularity: render every `RunEnvelope` as its own node (1:1) to maintain parity with the timeline sequence.
- Loops: no special visualization; reuse default edge styling.
- Retries: represent as curved edges returning to the source node, annotated with a red counter badge to highlight failure-driven retries.
- Interaction: Sigma remains our layout engine, but user-facing zoom/pan is disabled; the static progress rail now surfaces run status at a glance.

### Implementation Notes (2025-09-09)
- Added a run view toggle in the Run Console header (persisted via zustand) so operators can swap views without leaving the main page; the run detail screen reuses the same preference.
- Built `RunFlowGraph` atop Sigma + graphology with elkjs-powered vertical layouts; each run envelope maps to a node with status-aware styling.
- Node glyphs are lightweight inline SVGs following the lucide silhouette (robot, wrench, pulse) to avoid adding a new package under restricted networking.
- Retry detection currently groups repeated agent/tool signatures; red arrows with badges flag the number of attempts that occurred before a completion.
- Default cards render in sequence order (step 0 at top) with condensed summaries whether in vertical or horizontal layout.
- Added a static `FlowProgress` rail that mirrors step status outside the Sigma canvas so zooming no longer hides the run summary.
- Draw main step connectors via an SVG overlay (`FlowEdges`) which keeps edges visible even though Sigma node sprites are hidden to remove the mini-map view.
