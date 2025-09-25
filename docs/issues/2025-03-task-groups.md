# Task Group Concurrency for Agent Orchestration

This issue doc tracks design work for enabling agents to dispatch multiple tasks in parallel (or as a batch) while preserving the existing run loop semantics.

## Problem Statement
- The current `run_loop` (see `src/arion_agents/engine/loop.py`) processes exactly one action per step (`USE_TOOL`, `ROUTE_TO_AGENT`, or `RESPOND`).
- Planner agents cannot fan out work to multiple tools or delegate to several agents at once, which limits scalability for workflows like document ingestion where summarization, chunking, and dictionary lookups could run concurrently.
- We need a minimal enhancement that introduces task grouping without rewriting the entire orchestrator.

## Goals
- Allow an agent to emit multiple sub-tasks that execute concurrently (or as a batch) and resume once all sub-tasks finish.
- Maintain compatibility with existing execution logging, LLM prompts, and tool schemas.
- Treat agent delegation as a first-class task, ideally reusing tool semantics so the core loop stays simple.
- Provide guardrails for concurrency (bounded parallelism, error handling, shared budgeting).

## Proposed Approach
1. **Action Schema Extension**
   - Introduce a new decision action type `TASK_GROUP` alongside `USE_TOOL`, `ROUTE_TO_AGENT`, and `RESPOND`. Agents advertise support the same way they do today: snapshots flag available actions via their graph edges (no ad‑hoc metadata flags).
   - `action_details` carries a list of `tasks`. Each child task has a `task_type` (`use_tool` or `delegate_agent`), plus a `task_id`, `retry_policy`, and an explicit payload. `use_tool` mirrors the existing schema (`tool_name`, `tool_params`). `delegate_agent` wraps one or more `delegation_details` objects, each specifying `agent_key`, `assignment` (prompt text for the assignee), optional `context_overrides`, and bounds such as `max_steps` / `max_tokens`.
   - Delegated agents need a way to hand control back to the parent without terminating the top-level run. Introduce a companion action type `TASK_RESPOND`. Only agents that can be delegated to receive this action in their configuration; `RESPOND` continues to represent the terminal edge for the full run.

2. **Agent-as-Tool Adapter (`agent:delegate`)**
   - Implement an internal provider that executes delegated work by invoking `run_loop` (or a dedicated helper) for the target agent while disabling standard `RESPOND` and enabling `TASK_RESPOND`.
   - The adapter must inject the delegation assignment into the delegated agent’s context, enforce `max_steps`, and surface a structured result payload to the parent agent. This keeps orchestration consistent: planners still emit a single `TASK_GROUP` decision yet receive a multi-task summary.

3. **Task Group Execution Phases**
   - Extend the engine to detect `TASK_GROUP`. For each child task:
     - `use_tool` → call the existing tool execution path.
     - `delegate_agent` → invoke the adapter described above and capture the sub-run output.
   - **Phase 1 (Batch semantics, sequential execution):** process child tasks one after another while recording a nested execution log entry per group (`group_id` + ordered child outcomes). Tool and agent steps inside a group maintain their existing schema but include the parent `group_id` so they can be reconstructed hierarchically.
   - **Phase 2 (True parallelism):** upgrade execution to run child tasks concurrently (e.g., `asyncio.gather` or a worker pool). Requires coordinating limits, propagating cancellations, and merging results deterministically.
   - After either phase completes, aggregate results and resume the planner with outputs appended to the execution log. Failed children trigger one retry; if the retry also fails, abort the entire run and surface the final error to the planner.

4. **Logging & Telemetry**
   - Emit a parent `task_group` entry per decision containing ordered child outcomes; each nested tool/agent step keeps the existing schema plus a `group_id`/`parent_execution_id` for traceability.
   - Preserve compatibility with `ExecutionLog` consumers by continuing to record flattened tool steps while also exposing the hierarchy for richer UIs.
   - Ensure conversation context builders include these grouped outputs so downstream agents see previous sub-task results.

5. **Constraints & Safeguards**
   - Configurable max tasks per group (e.g., 3–5) to avoid runaway fan-out.
   - Token budget coordination: before launching child tasks, estimate remaining budget; abort or warn if likely to exceed.
   - Error policy: retry a failed child once; if the retry also fails, abort the entire run and return the aggregated failure to the planner.

6. **Prompt & Schema Updates**
   - Update planner prompt templates to explain the new `TASK_GROUP` option and provide example JSON.
   - Produce JSON Schema for `TASK_GROUP` that Pydantic can validate, ensuring LLM outputs remain well-formed.

## Implementation Plan (Draft)
1. Update `AgentDecision` models to include `TaskGroupDetails` and adjust `decision_to_instruction`.
2. Extend `RunConfig`/`execute_instruction` to recognize the new action and manage task execution.
3. Create `agent:delegate` provider, wiring it into `tools/registry.py`.
4. Add unit tests covering sequential task groups, nested delegation, and failure handling.
5. Optional: Add async execution path once the sequential version is stable.

## Open Questions
- Do we need nested task groups (a child task spawning another group)? If yes, how to prevent deep recursion?
- How do we reconcile aggregated tool responses with current context builders (flatten vs. hierarchical)?
- Should we expose partial progress to the user or only surface a single planner response once all tasks complete?
- How do we handle long-running delegated agents—do we need cancellation/timeouts surfaced to the planner?

## References
- LangGraph “Send/Gather” pattern for inspiration on fan-out/fan-in orchestration.
- CrewAI / Autogen discussions on treating agents as tools.
- Existing `tools/seed_location_demo.py` for how networks/agents/tools are registered via API; similar flows will create any new delegate tools.

Use this doc to refine the concurrency strategy before implementation. Add diagrams, pseudocode, or API changes as decisions solidify.
