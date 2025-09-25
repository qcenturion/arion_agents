# Config Page & Network Detail View Overhaul

**Status:** Proposed
**Date:** 2025-09-25
**Author:** Gemini

## 1. Overview

This document outlines a major feature enhancement for the Configuration section of the application. The goal is to improve workflow efficiency by adding "copy" functionality for networks and agents, and to create a more intuitive and powerful interface for managing the components of a network.

## 2. Feature Breakdown

### Feature 2.1: Copy Network & Agent

- **User Story:** As a developer, I want to duplicate an existing network or agent so I can create a new version or test a variation without starting from scratch.
- **Requirements:**
    1.  Add a "Copy" button next to each network in the list on the main Config page.
    2.  Add a "Copy" button next to the "Publish Network" button on the (new) network detail view.
    3.  Add a "Copy" button next to each agent listed within the (new) network detail view.
    4.  The copy operation must be a deep copy, duplicating all child objects (agents, tools, routes, etc.) and linking them to the new parent.

### Feature 2.2: Unified Network Detail View

- **User Story:** As a developer, I want a single page where I can see and manage all the components of a specific network.
- **Requirements:**
    1.  Clicking a network on the Config page should navigate to a new, dedicated network detail page.
    2.  This page must display a list of all agents and tools belonging to the network.
    3.  The agents and tools listed must be editable in place, using the same forms/modals available on the main "Agents" and "Tools" tabs.

### Feature 2.3: Visual Graph in Network View

- **User Story:** As a developer, I want to see a visual representation of my network's structure on its detail page so I can quickly understand its flow.
- **Requirements:**
    1.  The network detail page must include a visual graph.
    2.  The graph should render agents as nodes.
    3.  It should render the `allowed_routes` between agents as directed edges (arrows).
    4.  It should visually indicate which tools are equipped by each agent (e.g., by listing them in the node or with icons).

## 3. Implementation Plan

### Phase 1: Backend API (Copy Functionality)

- **File to Modify:** `src/arion_agents/api_config.py`
- **Plan:**
    1.  **Create `POST /networks/{network_id}/copy` Endpoint:**
        - This endpoint will fetch the target `Network` and all its related objects (Agents, NetworkTools, routes, etc.).
        - It will create new database records for each of these, ensuring all foreign keys are correctly updated to point to the new parent network.
        - The new network will have a name like "Copy of [Original Name]".
    2.  **Create `POST /networks/{network_id}/agents/{agent_id}/copy` Endpoint:**
        - This endpoint will perform a similar deep copy operation for a single `Agent` within its parent network.
        - The new agent will have a key like "[original_key]_copy".

### Phase 2: Frontend UI (New Network Detail Page)

- **Plan:**
    1.  **Create New Page:** Create a new file at `frontend/app/config/networks/[networkId]/page.tsx`. This will be a client component that fetches data for a specific network.
    2.  **Unified Dashboard Layout:**
        - The page will fetch and display the network's details at the top.
        - It will have two main sections: "Agents" and "Tools".
        - Each section will list the items belonging to the network and provide "Edit" and "Copy" buttons for each. The edit functionality can reuse existing components.
    3.  **Visual Graph Component:**
        - Create a new component, e.g., `NetworkVisualizer.tsx`.
        - This component will fetch data from the existing `GET /networks/{network_id}/graph` endpoint.
        - It will use a library like `sigma.js` (already in use) or a simpler SVG-based renderer to draw the nodes (agents) and edges (routes). Tool equipage will be displayed as text within each node.

### Phase 3: Frontend UI (Adding Copy Buttons)

- **Plan:**
    1.  **Main Config Page:**
        - **File:** `frontend/components/Config/ConfigWorkbench.tsx`
        - **Action:** In the `NetworkRow` component, add a new "Copy" button. This button will trigger a `useMutation` hook that calls the new `POST /networks/{network_id}/copy` endpoint. On success, it will invalidate the `networks` query to refresh the list.
    2.  **Network Detail Page:**
        - **File:** `frontend/app/config/networks/[networkId]/page.tsx`
        - **Action:** Add the top-level "Copy Network" button near the "Publish" button. Add "Copy" buttons to each agent in the list, wired up to their respective API endpoints.
