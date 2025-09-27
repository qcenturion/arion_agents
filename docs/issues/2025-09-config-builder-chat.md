# Config Builder Chat Experience

**Status:** Draft
**Date:** 2025-09-27
**Owner:** Codex

## 1. Goal

Prototype a conversational assistant that can walk a user through creating and managing networks, agents, and tools directly from the front-end. The agent must:

- Gather the exact inputs required by each backend endpoint.
- Validate user-provided values before issuing mutations.
- Explain optional vs. required fields and the consequences of defaults.
- Sequence operations so that dependent resources (e.g., agents that need tools) are only created once prerequisites exist.
- Surface backend validation errors in plain language and offer retry paths.

This document enumerates the workflows, required data, and validation steps the chat assistant must follow.

## 2. Global Context & Constraints

1. **APIs live under `/config/*`.** All requests are JSON POST/PATCH/PUT and expect/return snake_case.
2. **Authentication/headers.** Reuse the existing `apiFetch` client; the assistant just calls named helpers (e.g., `createNetwork`).
3. **Uniqueness rules.**
   - Network names must be globally unique (case-insensitive).
   - Tool keys are globally unique.
   - Agent keys must be unique within their parent network.
4. **RESPOND requirements.** Every network must have at least one agent with `allow_respond=true`. Publishing requires a RESPOND-capable default agent.
5. **Tool schema requirement.** `additional_data.agent_params_json_schema` **must** be a JSON object. The API rejects non-objects.
6. **Default values.** When fields are optional and omitted, the backend typically inserts `null`, `{}`, or `draft`. The assistant should state what happens if the user leaves the field empty.

## 3. Conversational Flow Outline

1. **Intent detection.** Identify whether the user wants to create, edit, clone, or publish a resource.
2. **Resource existence check.** For create flows, fetch and list existing resources to guard against duplicates.
3. **Data collection.** Ask for required fields first; confirm optional inputs only if relevant.
4. **Validation.**
   - Inline: enforce non-empty name/key, valid JSON via `parseJsonObject` helpers, and uniqueness against cached queries.
   - Backend: relay precise error messages from API responses and propose fixes.
5. **Execution.** Call the appropriate helper (see Section 4) and await success response.
6. **Post-action guidance.** Summarize what changed, suggest next steps (e.g., attach tools, set routes, publish).

## 4. Detailed Workflows

### 4.1 Tool Creation (`POST /config/tools`)

**Required fields**

| Field | Type | Notes |
| --- | --- | --- |
| `key` | string | Unique across all tools. Assistant must verify case-insensitive uniqueness via cached tools list. |
| `additional_data.agent_params_json_schema` | object | Required; provide a template if user has none. Validate JSON and enforce object type. |

**Optional fields**

- `display_name`, `description`, `provider_type`, `secret_ref` (strings). Empty -> send `null`.
- `params_schema` (object). If omitted, send `{}`.
- `additional_data` can carry other keys (e.g., description); ensure final payload remains an object.

**Steps**

1. Fetch existing tools to check for duplicate keys (`GET /config/tools` → `fetchTools()` helper).
2. Collect key and confirm uniqueness.
3. Gather display name/description/provider/secret if desired.
4. Prompt for agent-facing params schema; if user unsure, offer default stub.
5. Collect additional metadata. Merge user-provided JSON with required `agent_params_json_schema` block.
6. Call `createTool(payload)`.
7. On success, surface tool ID/key and suggest attaching it to a network.

### 4.2 Network Creation (`POST /config/networks`)

**Required fields**

| Field | Type | Notes |
| --- | --- | --- |
| `name` | string | Unique globally; trim whitespace and lowercase when checking duplicates. |

**Optional fields**

- `description` (string).
- `additional_data` (object) — commonly includes RESPOND guidance:
  - `respond_payload_schema` (object): strongly encouraged; validates final payload shape.
  - `respond_payload_guidance` / `respond_payload_example` (strings/objects) to guide agents.
  - `force_respond` (bool) and `force_respond_agent` (string) can remain unset during creation.

**Steps**

1. Fetch networks to validate uniqueness (`GET /config/networks` → `fetchNetworks()`).
2. Request name and optional description.
3. Ask whether the user wants to define RESPOND schema now:
   - If yes, collect JSON schema. Validate with `parseJsonObject`.
   - If no, note that it can be edited later in the network card.
4. Gather any additional metadata (execution log policies, etc.).
5. Call `createNetwork` with `status: "draft"`.
6. Surface the new network ID and recommend next actions (create agents, attach tools, configure routes, publish).

### 4.3 Agent Creation (`POST /config/networks/{id}/agents`)

**Required fields**

| Field | Type | Notes |
| --- | --- | --- |
| `network_id` | number | Must reference an existing network. |
| `key` | string | Unique within network. |
| `allow_respond` | boolean | Default `true`; inform user about RESPOND publishing requirement. |

**Optional fields**

- `display_name`, `description` (strings).
- `is_default` (boolean). Only one agent per network should have this flag.
- `prompt_template` (string). Stored inside `additional_data` when provided.
- `additional_data` (object). Rarely used beyond prompt template.

**Steps**

1. Confirm target network:
   - If only one network exists, offer to use it automatically.
   - Otherwise show choices by name/ID.
2. Fetch network agents to check key uniqueness and identify existing RESPOND agents (`GET /config/networks/{id}/agents` → part of `fetchNetworkGraph` or `fetchAgents()` filtered by `network_id`).
3. Collect agent key, display name, description, RESPOND toggle, default toggle, prompt template.
4. Warn if user makes the clone RESPOND-default combination invalid (e.g., default but no RESPOND).
5. Call `createAgent(networkId, payload)`.
6. Suggest equipping tools and setting routes (Sections 4.4 & 4.5).

### 4.4 Attach Tools to Network (`POST /config/networks/{id}/tools`)

**Required fields**

- `tool_keys` (array of strings). Each key must exist globally and not already be attached.

**Steps**

1. Fetch global tools (`GET /config/tools` → `fetchTools()`) if the user needs to browse options.
2. Confirm which keys to attach; coerce to lowercase and deduplicate.
3. Call `addToolsToNetwork(networkId, toolKeys)`.
4. If overrides (per-network params/additional data) are needed, follow up with `updateNetworkTool`.

### 4.5 Equip Tools to Agent (`PUT /config/networks/{id}/agents/{agent_id}/tools`)

**Required fields**

- `tool_keys` array referencing network-attached tool keys.

**Steps**

1. Fetch network graph to list available network tools.
2. Validate the selected keys exist for that network.
3. Call `setAgentTools`.

### 4.6 Configure Agent Routes (`PUT /config/networks/{id}/agents/{agent_id}/routes`)

**Required fields**

- `agent_keys` array listing downstream agent keys in the same network.

**Steps**

1. Provide a summary of existing agents (`GET /config/networks/{id}/agents`).
2. Collect downstream keys; guard against self-routing (backend rejects) and unknown keys.
3. Call `setAgentRoutes`.

### 4.7 Clone Operations

#### Clone Network (`duplicateNetwork` helper)

1. Ask for a new unique name (suggest `<Original> Copy`). Optional new description.
2. The helper performs:
   - GET source graph.
   - POST new network with merged `additional_data`.
   - POST attach tools and patch overrides.
   - Recreate agents, equip tools, reapply routes.
   - Recompile/publish automatically if the source had a published version.
3. Inform user the new network starts as `draft` unless publish succeeded.

#### Clone Agent (`duplicateAgent` helper)

1. Collect new unique key and optional display name/description/prompt.
2. Allow user to opt into RESPOND/default flags (default: RESPOND mirrors source, default=false).
3. Helper recreates agent, copies tools and routes.

#### Clone Tool (`duplicateTool` helper)

1. Collect new unique key.
2. Optionally override display name/description/provider/secret/schema.
3. Helper reuses existing params/additional data.

### 4.8 Publish Network (`POST /config/networks/{id}/versions/compile_and_publish`)

**Required fields**

- None strictly required, but the backend enforces:
  - At least one RESPOND-capable agent.
  - Exactly one default agent.
  - Valid RESPOND schema if provided earlier.

**Optional fields**

- `notes`, `created_by`, `published_by` (strings).

**Steps**

1. Confirm user intent to publish.
2. Optionally collect notes/created_by/published_by for audit log.
3. Call `compileAndPublishNetwork`.
4. Surface success/version number or relay constraint violation messages with remediation steps (e.g., designate default agent, enable RESPOND).

## 5. Conversation Snippets

- **Network creation**
  1. "Do you want to create a new network?" → yes.
  2. Ask for name → validate uniqueness.
  3. Ask for description (optional).
  4. "Do you want to define the RESPOND payload schema now?" → if yes, accept JSON and validate.
  5. Confirm summary and execute creation.

- **Agent creation**
  1. Determine target network.
  2. Request agent key → check duplicates.
  3. Ask for display name/description.
  4. Toggle RESPOND/default flags; explain constraints.
  5. Prompt template (multi-line input allowed).
  6. Confirm recap and call create API.

- **Tool creation**
  1. Request key → check duplicates.
  2. Ask for display name/description/provider/secret.
  3. Params schema → provide stub if uncertain.
  4. Additional data → ensure `agent_params_json_schema` is present and valid.
  5. Confirm recap and call create API.

## 6. Error Handling Patterns

- **Duplicate name/key:** Inform user which existing resource conflicts and prompt for a new value.
- **JSON parse failure:** Echo parser error message and provide guidance (e.g., "Ensure quotes are double-quoted").
- **Validation errors from backend:** Use `extractApiErrorMessage` to display friendly messages, then guide user on next steps.
- **Network publish failure:** Suggest enabling RESPOND, setting default agent, or reviewing execution log policies.

## 7. Data to Cache Between Turns

- Lists of networks, agents per network, tools, and network tools to minimize repeated fetches.
- Partial form state while collecting multi-step inputs (e.g., tool schema segments).
- Pending operations so the assistant can remind the user about unfinished setups (e.g., "You created the network but haven’t added any agents yet").

## 8. Next Steps

1. Implement a mock chat UI flow that logs decisions instead of performing live mutations.
2. Encode the above steps into prompt templates for the Gemini model (system instructions + few-shot examples).
3. Iterate with users to refine language, especially around RESPOND schema guidance and error recovery.
