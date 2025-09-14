# Orchestrator Loop & Execution Log — TODO

## Goals
- Deterministic loop: LLM decision → validate/execute → repeat until RESPOND.
- Exactly one default agent per network; at least one RESPOND-capable agent; graph safety checks.
- Rich, near real-time observability and reproducibility via structured logs and spans.

## Data Model
- Agent: add `is_default: bool = False` (unique true per network).
- Snapshot: include `default_agent_key` at root.
- Agent: keep `allow_respond` and `prompt_template` (compiled to `prompt`).

## Compile-Time Validation (on publish)
- Exactly one `is_default=True` agent per network.
- ≥1 agent with `allow_respond=True`.
- Routes must reference existing agents within the network.
- Reachability: from `default_agent_key`, there exists a path to an agent with `allow_respond=True`.

## Runtime: run_loop(cfg, max_steps=10)
- State
  - `current_agent: str` (start: default agent unless overridden).
  - `steps: int` with guard `max_steps`.
  - `execution_log: List[dict]` ordered entries (see below).
  - `tool_execution_log: Dict[str, dict]` full payloads keyed by `execution_id` (unique per tool call).
  - `control_epoch: int` tracks segments of continuous control by a single agent.
- Per step
  1) Build prompt = compiled base prompt for `current_agent` + Context + Constraints.
     - Context includes:
       - User message (first step) and any subsequent agent messages (future).
       - Full tool outputs from the “continuous control loop” (see below) injected for tools equipped by the current agent.
       - Execution log summary (truncated) as a reference (read-only context).
     - Constraints include allowed tools + agent-provided param names; allowed routes; required JSON fields: action, action_reasoning, action_details.
  2) Call LLM in JSON mode (google-genai) for `AgentDecision` (thinking disabled).
  3) Translate to `Instruction` and execute via `execute_instruction()`.
  4) Append to `execution_log` with truncated displays; for tool calls, also write full response to `tool_execution_log` under the `execution_id`.
  5) Routing: if ROUTE_TO_AGENT, set `current_agent = target` and increment `control_epoch` if target != previous agent.
  6) Tool: remain with same `current_agent` (no epoch change).
  7) RESPOND: stop and return transcript (execution_log), tool_execution_log index keys, and final.
- Guardrails: stop on `max_steps`, or max tool errors; return error with transcript.

## Execution Log (ordered, in-memory)
- Entry shapes (JSON-safe dicts):
  - Agent step:
    - `type: 'agent'`
    - `step: int`
    - `epoch: int` (control epoch id)
    - `agent_key: str`
    - `input_preview: str` (user message or context summary, truncated ~80 chars)
    - `decision: { action, action_reasoning (trunc ~120), action_details (trunc ~120) }`
  - Tool step:
    - `type: 'tool'`
    - `step: int`
    - `epoch: int`
    - `agent_key: str` (caller)
    - `tool_key: str`
    - `execution_id: str` (monotonic or uuid)
    - `request_preview: str` (trunc ~50)
    - `response_preview: str` (trunc ~100)
    - `status: 'ok'|'error'`
    - `duration_ms: int`

## Tool Execution Log (full payloads)
- Map `execution_id -> { agent_key, tool_key, merged_params, result, status, duration_ms, timestamp }`.
- Full objects are not placed in `execution_log`; only previews live there.

## Continuous Control Loop Context Injection
- When invoking `current_agent`, include full tool outputs for tool steps that belong to the current continuous control loop segment:
  - Identify the most recent `epoch` for `current_agent`.
  - Collect all tool entries with the same `epoch` occurring after the last agent step of a different agent.
  - For each such tool entry, fetch full result from `tool_execution_log[execution_id]` and bind into the prompt context.
- Do not include tool outputs from earlier epochs (i.e., from other agents’ control) to avoid irrelevant context leakage.

## Prompt Binding Rules
- Base prompt in snapshot remains static (precompiled `{tools}`, `{routes}`, `{agent_key}` replacements).
- Runtime Context section (appended or injected via `{tool_history}` if present):
  - Recent tool outputs for this epoch (full, structured, labeled by tool_key/execution_id).
  - Execution log summary (ordered, truncated, neutral tone, for reference).
- Constraints section: unchanged from current implementation.

## API
- `/run` → call `run_loop()` with `{ network, agent_key?, user_message, version?, system_params?, max_steps? }`.
- Add `debug=true` to include raw prompts and raw LLM JSON text per step.

## Observability (OTel)
- Root span per `/run`, child spans per step; nested spans for tool calls.
- Attach prompt (redacted), decisions, and tool previews as span events.
- In serverless, call `force_flush()` on tracer provider before returning.

## Acceptance Criteria
- Can run multi-step flows from default agent to RESPOND with max_steps guard.
- Execution log shows ordered steps with previews; tool_execution_log stores full payloads keyed by execution_id.
- Context injection includes only full tool outputs from the current agent’s latest continuous control segment.
- Snapshot publish fails if default agent isn’t unique, no RESPOND-capable agent, or no path to RESPOND.

## Out of Scope (for now)
- Cross-agent control return after tool (future option).
- MCP tooling; durable execution; UI.

## Files & Changes

Existing files to edit
- `src/arion_agents/config_models.py`
  - Add `Agent.is_default: bool = False`
  - Optional: DB-level checks/indices if desired (primary enforcement at API level)
- `src/arion_agents/api_config.py`
  - Compile-time validations during `compile_and_publish`:
    - Exactly one default agent per network
    - ≥1 RESPOND-capable agent
    - Routes reference existing agents
    - Reachability from default to a RESPOND-capable agent
  - Snapshot additions: set `default_agent_key` at root
- `src/arion_agents/orchestrator.py`
  - Keep `Instruction`, `RunConfig`, `execute_instruction()` as-is
  - Add thin `run_loop(cfg, user_message, max_steps=10, debug=False)` that delegates to helpers
  - Define lightweight `ToolEvent` model only if needed locally (prefer external logs module)
- `src/arion_agents/api.py`
  - Update `/run` to call `run_loop()` and return `{ instruction(s), result, execution_log, tool_refs }`
  - Add `debug=true` to include raw prompt and raw LLM JSON per step
  - `_build_run_config`: if `agent_key` not supplied, use snapshot `default_agent_key`
- `src/arion_agents/llm.py`
  - Reuse `gemini_decide()` for the loop; no extra framework on hot path

New files to add
- `src/arion_agents/logs/execution_log.py`
  - `ExecutionLog` with `append_agent_step()`, `append_tool_step()`, `to_list()`, `current_epoch_for(agent)`
  - `ToolExecutionLog` with `put(execution_id, full_payload)`, `get(execution_id)`,
    `collect_full_for(agent, epoch, since_last_agent_switch)`
- `src/arion_agents/prompts/context_builder.py`
  - `build_constraints(cfg)`
  - `build_context(cfg, user_message, exec_log, tool_log, current_agent)`
  - `build_prompt(base_prompt, context, constraints)`
- `src/arion_agents/graph/validate.py`
  - Pure functions used by `api_config.py` to validate snapshots: uniqueness, existence, reachability
- `src/arion_agents/otel/tracing.py` (optional)
  - `enter_step_span()`, `enter_tool_span()`, `force_flush()` wrappers

Tests
- `tests/test_run_loop_basic.py`
  - Echo tool: agent → USE_TOOL → agent → RESPOND within max_steps
  - Execution log content and tool full-output injection rules validated
- `tests/test_snapshot_validation.py`
  - Fails on multiple defaults, no RESPOND agent, missing route target, unreachable RESPOND
