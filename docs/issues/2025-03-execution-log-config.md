# Execution Log Overrides Per Network

## Summary
- Allow network owners to specify exactly which request/response slices from each tool invocation are surfaced in the execution log, including per-field truncation policy.
- Ship the config as part of the compiled network graph so the orchestrator reads it every loop iteration; prompts and downstream agents then see the curated log in real time.
- Expose the configuration in the frontend Config workbench so operators can edit it without touching raw JSON artifacts.

## Current Behavior
- `ExecutionLog.append_tool_step` (`src/arion_agents/logs/execution_log.py`) stores stringified previews of the entire request/response with a hard-coded truncation helper.
- The orchestrator passes full tool payloads into `ToolExecutionLog` and the prompt context, but there is no way to suppress noisy fields or increase truncation length for high-value data.
- Network metadata only covers RESPOND payload guidance; nothing in `additional_data` describes execution log preferences, so every network inherits the same default summaries.

## Requirements
- Per-network execution log policy that can:
  - Target individual tools by key (network-scoped names) with optional fallbacks.
  - Choose which request fields and response fields to emit, using JSON path selectors understood by Pydantic models for the tool output.
  - Set truncation length per field (including an option for "no truncation").
- Defaults must preserve today’s behavior when no override exists.
- Configurable through the frontend UI (no manual file edits) and stored in network `additional_data` so it version-controls with snapshots.

## Proposed Data Model
Store the policy under `network.additional_data.execution_log`. Example:

```json
{
  "execution_log": {
    "defaults": {
      "request_max_chars": 120,
      "response_max_chars": 200
    },
    "tools": {
      "sun": {
        "request": [
          {"path": "params.lat", "label": "lat", "max_chars": 0},
          {"path": "params.lng", "label": "lng", "max_chars": 0}
        ],
        "response": [
          {"path": "result.sunrise", "label": "sunrise", "max_chars": 0},
          {"path": "result.sunset", "label": "sunset", "max_chars": 0}
        ]
      },
      "geonames": {
        "response": [
          {"path": "result.geonames[0].name", "label": "top_match", "max_chars": 80}
        ]
      }
    }
  }
}
```

- `path` uses dot / bracket traversal resolved against typed Pydantic models exposed by the tool provider (fallback to runtime JSON if a model is absent).
- `label` becomes the key stored in the execution log entry; omit to reuse the path string.
- `max_chars = 0` means no truncation. Omitted `max_chars` falls back to tool-level override or `defaults`.

## Implementation Steps
1. **Backend schema & snapshot compilation**
   - Define `ExecutionLogFieldConfig`, `ExecutionLogToolConfig`, and `ExecutionLogPolicy` Pydantic models in a new module under `src/arion_agents/logs/` for reuse by API + runtime.
   - Extend `_compile_snapshot` in `src/arion_agents/api_config.py` to copy `execution_log` from `network.additional_data` into the compiled graph (validating with the new models and emitting schema errors via FastAPI when invalid).
   - Update `_build_run_config_from_graph` (`src/arion_agents/api.py`) and the `RunConfig` model (`src/arion_agents/orchestrator.py`) to carry the parsed policy (or `None`). Ensure the policy is serialized in `/prompts/resolve` responses for debugging if needed.

2. **Runtime logging pipeline**
   - Add a helper in `ExecutionLog` (or a sibling utility) that, given the policy and a `ToolRunOutput`, selects fields, resolves Pydantic models where available, and applies truncation before calling `append_tool_step`.
   - Modify `_log_tool_execution` in `src/arion_agents/engine/loop.py` to invoke the helper with the current tool key, request payload, and response body. Replace the existing `request_preview` / `response_preview` strings with the curated map produced by the policy, while preserving backward-compatible keys when no override exists.
   - Ensure the curated snippets are also what `build_context` sees via `full_tool_outputs` so downstream prompts stay consistent with the execution log view.

3. **Frontend editing & validation**
   - Extend the Config workbench (`frontend/components/Config/ConfigWorkbench.tsx`) to surface an "Execution Log Policy" editor alongside the existing RESPOND configuration. Provide a lightweight form that lets users select a tool, add request/response field rows, and set truncation limits (fall back to a JSON textarea only if the structured editor fails to parse).
   - Update `@/lib/api/types` and related fetch/update helpers to include the new `execution_log` blob in `NetworkSummary.additional_data` and preserve it when saving.
   - Add inline validation/error messaging mirroring backend constraints (path must be non-empty, `max_chars` >= 0, etc.).

4. **Testing & artifacts**
   - Unit-test the policy parser + field extraction using representative tool outputs (e.g., sun, geonames) in `tests/test_execution_log_policy.py`.
   - Extend orchestration loop tests (or add new ones) to assert that different policies yield the expected execution log entries and prompt context updates.
   - Capture an updated run snapshot under `logs/runs/` during manual QA showing customized execution log output for a network with overrides.

## Open Questions
- Do we need schema hints from each tool provider to help users author valid paths, or is free-form path entry sufficient for now?
- Should we support redact/omit semantics (e.g., explicitly removing sensitive fields) in addition to positive selection?
- How should we expose the policy in run history exports—embed the curated view only, or surface both raw + curated for diagnostics?
