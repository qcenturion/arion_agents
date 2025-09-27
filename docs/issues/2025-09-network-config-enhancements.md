# Network Configuration Enhancements: Edit Name and Copy Network

**Date**: 2025-09-26

## Overview

This document outlines proposed enhancements to the network configuration interface to improve user workflow. The two primary features are the ability to edit a network's name and the ability to create a complete copy of an existing network.

## 1. Edit Network Name

Currently, the network name is a static field in the configuration UI. This feature will allow users to modify the name of a network after it has been created.

### Backend Changes (`api.py`)

- The `PATCH /api/config/networks/{network_id}` endpoint will be updated to accept a `name` field in its payload.
- The endpoint must include validation to ensure the new name is unique and does not conflict with existing network names.

### Frontend Changes (`frontend/components/Config/ConfigWorkbench.tsx`)

- In the `NetworkRow` component, when in "Edit" mode, the network name will be rendered as an editable text input field.
- The `handleSave` function will be updated to include the network name in the update payload.

## 2. Copy Network

To accelerate the creation of new networks that are similar to existing ones, a "Copy Network" feature will be implemented.

### Backend Changes (`api.py`)

- A new endpoint, `POST /api/config/networks/{network_id}/copy`, will be created.
- This endpoint will perform a "deep copy" of the specified network:
    - A new `Network` record is created. The name will be based on the original, with a `_copy` suffix appended (e.g., "MyNetwork" becomes "MyNetwork_copy"). If that name exists, it should append a number (e.g., "MyNetwork_copy_2").
    - All `Agent` records associated with the original network will be duplicated and associated with the new network.
    - All `NetworkTool` records will be duplicated for the new network.
    - Agent-tool links (`AgentToolLink`) and agent-to-agent routes (`AgentRouteLink`) will be recreated for the new agents.
    - The new network will be in a `draft` state.

### Frontend Changes (`frontend/components/Config/ConfigWorkbench.tsx`)

- A "Copy Network" button will be added to the `NetworkRow` component, likely next to the "Publish Network" button.
- An `onClick` handler will call the new copy endpoint.
- On success, the `networks` query will be invalidated to refresh the list, displaying the newly created network.
