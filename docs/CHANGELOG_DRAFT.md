# Changelog Draft (to include in next commit)

## Summary
- Add orchestrator loop engine with structured execution log and tool execution log.
- Add agent prompt templating and resolved prompt visibility for debugging.
- Add worldtimeapi tool provider and end-to-end demo seeding.
- Add Dockerfile and docker-compose stack for Postgres + API.

## Breaking/Model Changes
- `cfg_agents`: new column `is_default` (bool, default false) used to select default agent at runtime.
- Compiled snapshot now includes `default_agent_key` and agent `is_default` flags.

## Features
- Orchestrator loop
  - New engine `run_loop()` driving multi-step flows until RESPOND with max_steps guard.
  - ExecutionLog (ordered) and ToolExecutionLog (full payloads by execution_id).
  - Context injection: full tool outputs from the current agent’s continuous control segment are injected into prompts.
- Agent prompts
  - `prompt_template` stored in `Agent.meta`; compiled at publish to static `prompt` with `{tools}`, `{routes}`, `{agent_key}`.
- LLM decisions
  - Use Google JSON mode (disabled thinking) to produce `AgentDecision` → translate to `Instruction`.
  - `/run` supports `debug=true` to return resolved prompts and raw model JSON per step.
- Tools
  - Class-based provider registry; added provider `http:worldtimeapi` to fetch UTC and compute TAI.
  - Orchestrator returns tool `{tool, params, result, duration_ms}` for richer logging.
- API
  - `/run`: one-call agent loop with debug.
  - `/prompts/resolve`: returns fully resolved prompt for preview.
  - `/config/networks/{id}/snapshot_current`: returns compiled snapshot JSON.
  - Static snapshot mode: set `SNAPSHOT_FILE=<path>` to bypass DB and run end-to-end from a file (real loop, LLM, tools).
- Docker
  - Dockerfile for API; docker-compose with Postgres; Make targets `compose-*`.
  - Mounts `.secrets/` into container; key is read from `/app/.secrets/gemini_api_key`.
- Seeds
  - `make seed-time`: builds network `time_demo`, equips triage with `time` tool, routes triage→writer, publishes, runs demo.

## Internal/Refactor
- Split concerns into new modules:
  - `engine/loop.py`: loop engine
  - `logs/execution_log.py`: execution logs
  - `prompts/context_builder.py`: constraints/context/prompt builders
- Kept orchestrator single-step executor minimal (`execute_instruction`).
 - Debug: when `debug=true`, `/run` now includes `tool_log` (full tool results keyed by execution_id) in addition to `execution_log`.
 - SQLite compatibility for local e2e without Postgres (JSONType alias).

## Tests
- `test_run_loop_basic.py`: verifies loop with stub decisions and echo semantics.
- `test_decision_translation.py`: AgentDecision → Instruction translation and execution.
- `test_snapshot_validation.py`: placeholder (validations covered at API level).
- All tests passing locally (`14 passed, 2 skipped`).

## Docs
- `DOCKER.md`: how to build/run with Docker.
- Updated README and START_HERE for venv and LLM setup; `/llm/complete`, `/llm/draft-instruction`, `/run`.
- `TODO_orchestrator_loop.md`: plan/status; files & changes; completed vs pending.
 - Added local e2e instructions (file-based snapshot and in-process TestClient flow).

## Deploy/Run Notes
- Local dev: `make db-up && make db-init && make run-api` or Docker `make compose-up`.
- Secrets: put Gemini key in `arion_agents/.secrets/gemini_api_key` (git-ignored); compose mounts it into the container.
- Tracing: set `OTEL_ENABLED=true` and `OTEL_EXPORTER_OTLP_ENDPOINT` to enable OTLP export.

## Next (Post-merge)
- Add OTel span helpers with safe redaction.
- Add PATCH endpoint for network-local tool overrides.
- Formalize `graph/validate.py` helpers and unit tests.
- Per-agent/provider LLM config in snapshot; selection in `/run`.
