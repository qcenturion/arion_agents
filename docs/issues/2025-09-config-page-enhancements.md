# Config Page & Network Detail View Overhaul

**Status:** In progress
**Date:** 2025-09-25
**Owner:** Gemini
**Last Updated:** 2025-09-27 (Codex planning pass)

## 1. Updated Scope
- Provide first-class UI flows to create networks, agents, and tools without relying on seed scripts.
- Add clone/duplicate actions for networks, network-scoped agents, and global tools.
- Allow renaming of networks plus display names for agents and tools from the same surface.
- Stage the deeper network detail view/graph work behind the CRUD improvements so we can ship incremental value.

## 2. Current State
- `frontend/components/Config/ConfigWorkbench.tsx` renders the tabbed configuration surface backed by React Query.
- Network rows expose publish + RESPOND controls but lack create, rename, or copy affordances.
- Agents and tools tabs show editable cards yet have no entry points for creating or duplicating resources.
- `frontend/lib/api/config.ts` only exposes read/patch helpers; create + association endpoints are not wrapped for frontend use.
- We still rely on scripts like `tools/seed_dialogflow_demo.py` for initial provisioning.

## 3. Implementation Plan

### 3.1 Shared API + State Layer
- Extend `frontend/lib/api/config.ts` with helpers: `createNetwork`, `createAgent`, `createTool`, `addNetworkTools`, `setAgentTools`, `setAgentRoutes`, and orchestrators for duplication flows.
- Define small payload helpers for clone forms (target name/key, optional overrides) so UI validation and API calls share logic.
- Centralize toast/error handling inside `ConfigWorkbench` state so every mutation can surface success/failure consistently.
- Reuse the existing JSON helpers (`prettyJson`, `parseJsonObject*`) across new forms to avoid duplicating validation code.

### 3.2 Networks Tab (`ConfigWorkbench`)
- Add a collapsible "Create network" card above the list with fields for `name`, optional `description`, RESPOND payload schema JSON, and general `additional_data`; submit via `createNetwork` and refresh `"networks"`.
- Extend edit mode in `NetworkRow` to include a `name` input, enforce case-insensitive uniqueness client-side, and call `updateNetwork` with the new name plus existing payload.
- Reuse the existing toast/error region within the card so create/rename feedback stays visible without extra components.
- Introduce a "Clone" action per row that opens a minimal form (new name + optional suffix toggle) and invokes the duplication helper to copy metadata, attach tools, recreate agents, and reapply routes.
- After cloning invalidate `"networks"`, `"agents"`, and `"tools"` queries to keep all tabs in sync with the new records.

- Prepend a "Create agent" card with inputs: target network (select), agent `key`, optional display name/description, flags for `allow_respond`/`is_default`, and prompt template; submit via `createAgent`.
- Refresh agent and network queries after creation and surface any API validation errors inline.
- Add a "Clone" button on each `AgentCard` that prompts for a new key/display name, then recreates the agent, reapplies equipped tools via `setAgentTools`, and mirrors outbound routes via `setAgentRoutes`.
- Default cloned agents to `is_default = false` while letting users opt in to transferring default status to prevent accidental constraint violations (the publish constraint remains enforced server-side).
- Clarify copy in edit mode that display name is the user-facing rename handle while keys remain immutable today.

### 3.4 Tools Tab (`ToolCard`, `ToolsPanel`)
- Add a creation card collecting tool `key`, display name, optional description/provider/secret, and JSON editors for `params_schema` + `additional_data`; validate that `additional_data.agent_params_json_schema` is an object before POSTing.
- Invalidate the tools query and reset the form after successful creation while keeping validation errors inline when they occur.
- Provide a "Clone" action on `ToolCard` that hydrates the create card with existing values, requires a new key, and submits a duplicate via `createTool`.
- Update edit-mode labels to emphasize that display name changes serve as the rename affordance; keys stay fixed until backend support exists (rename == display name update for this iteration).
- Add a quick "Copy key" utility button on the tool card header to streamline attaching the tool to networks.

### 3.5 Clone Execution Flow
- Wrap duplication logic in helpers (`duplicateNetwork`, `duplicateAgent`, `duplicateTool`) within `frontend/lib/api/config.ts` returning the created summary objects.
- Network duplication steps: fetch `GET /config/networks/{id}/graph`, POST the new network (copy name/description/additional_data plus RESPOND schema), add network tools by key, recreate agents with identical keys/settings, call `setAgentTools` for each, reapply adjacency via `setAgentRoutes` once all agents exist, and copy the latest published network version metadata so the duplicate starts with the current compiled snapshot lineage (leave status `draft`).
- Agent duplication steps: POST a new agent with copied metadata, reattach equipped tools, then mirror outbound routes using the same key list; surface a warning if the original agent was default and the clone opted into default.
- Tool duplication: reuse the creation payload, force unique key suffixing (`_copy`, `_copy_2`, …) when the requested key collides, and return the new tool summary for display.
- All orchestrators should report which step failed so the UI can present actionable errors (e.g., tool attach vs route update).

## 4. API Contracts
- `POST /config/networks` creates a network (fields: `name`, optional `description`, `additional_data`); `PATCH /config/networks/{id}` renames with server-side uniqueness enforcement.
- `POST /config/networks/{id}/agents` creates an agent; `PUT /config/networks/{id}/agents/{agent_id}/tools` and `/routes` endpoints manage equipped tools and adjacency.
- `POST /config/tools` provisions a global tool; `PATCH /config/tools/{tool_id}` updates display metadata and schemas while keys remain immutable.
- `POST /config/networks/{id}/tools` attaches global tools by key; `PATCH /config/networks/{id}/tools/{key}` keeps per-network schema overrides aligned.
- `GET /config/networks/{id}/graph` supplies the data needed to seed duplication flows (agents, tools, adjacency, network metadata).

## 5. Validation & UX Notes
- Enforce required fields (`name`, `key`) and basic formatting before firing mutations to reduce 4xx responses.
- Apply shared JSON parsing helpers so malformed schemas surface immediately with descriptive messages.
- Disable action buttons while mutations run to avoid duplicate submissions, especially for multi-step clones.
- Show success toasts that mention the resource key/name and offer quick navigation (e.g., scroll to the new network row).
- Keep forms open on failure and display `extractApiErrorMessage` output so users see backend validation messages.

## 6. Testing Plan
- Unit-test the new API helpers with mocked `apiFetch` to confirm payload shapes for create and clone operations.
- (Optional) Add a Playwright smoke covering the happy path for creating a tool, network, and agent via the UI.
- Manually verify network clone preserves tool equipage and agent routes using the DialogFlow demo network as a fixture.
- Run `make lint` and `npm run lint` inside `frontend` before submitting the feature branch.
- Capture before/after screenshots for the issue to document the new create/clone affordances.

## 7. Open Questions
- Is it acceptable to defer the dedicated network detail page/graph visualization until after CRUD surfaces ship? (currently agreed: yes, defer)
