# Frontend Graph Visualization Enhancements

**Status:** Proposed
**Date:** 2025-09-25
**Author:** Gemini

## 1. Overview

This document outlines a set of targeted UI/UX enhancements for the main "Execution Flow Graph" visualization to improve clarity and readability.

## 2. Requested Changes

### 2.1. Widen Graph Nodes
- **Description:** The rectangular nodes representing steps in the graph should be made twice as wide to better accommodate their content.
- **Constraint:** No other aspects of the graph's shape, layout, or assets should be altered.

### 2.2. Simplify Node Content
- **Description:** The text content within each node needs to be revised for clarity.
- **Change 1 (Remove Redundancy):** Remove the "Action: TOOL" text. This is redundant as the following node in the graph is already visually identifiable as a tool.
- **Change 2 (Add Agent Name):** The "Agent: " label is currently followed by a blank space. This should be populated with the name of the agent that executed the step.

### 2.3. Relocate Network Name
- **Description:** The network name currently appears at the bottom of every node in the graph. This is redundant as the network is a property of the entire run.
- **Change:** The network name should be removed from individual nodes and displayed once in the top-left area of the graph canvas, directly below the "EXECUTION FLOW GRAPH" title.

## 3. Implementation Plan & File Pointers

### 3.1. Widening Nodes

- **File to Modify:** `frontend/components/GraphCanvas/GraphViewer.tsx`
- **Plan:** The graph is rendered using the `sigma.js` library. We will need to investigate the `sigma.js` settings to find the appropriate property to control node width. It is likely that we cannot simply set a "width" property directly. Instead, we may need to use a custom node renderer or adjust the layout engine's (ELKjs) configuration to allocate more horizontal space for each node's label, effectively widening the node.

### 3.2. Simplifying Node Content (Agent Name & Action Text)

- **File to Modify:** The backend Python file where the `step_events` log is generated. The most likely candidate is **`src/arion_agents/engine/loop.py`**, which contains the `run_loop` function that produces the final output.
- **Plan:**
    1.  Locate the code within the `run_loop` (or a function it calls) that constructs the `label` for each step event dictionary.
    2.  Modify the string formatting logic to remove the "Action: TOOL" phrase.
    3.  Modify the logic to correctly retrieve and append the current agent's key (name) after the "Agent: " label.

### 3.3. Relocating the Network Name

This is a two-part change involving both the backend and frontend.

- **Part 1 (Backend):**
    - **File:** `src/arion_agents/api.py` (specifically the `get_run` endpoint).
    - **Plan:** The `_run_record_to_snapshot` function, which prepares the payload for the frontend, should be modified. It needs to extract the network name from the `RunRecord` and include it in the top-level `metadata` object of the response.
- **Part 2 (Frontend):**
    - **File:** `frontend/app/runs/[traceId]/page.tsx` (the page that displays the graph).
    - **Plan:**
        1.  Modify this page component to access the new `networkName` field from the `metadata` of the fetched run data.
        2.  Render this network name in a `<div>` or `<h2>` element positioned in the top-left corner of the area containing the `GraphViewer`.
        3.  The logic that currently renders the network name inside the node (identified in step 3.2) must be removed from the backend.
