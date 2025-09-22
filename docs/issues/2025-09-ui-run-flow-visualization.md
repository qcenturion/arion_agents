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
