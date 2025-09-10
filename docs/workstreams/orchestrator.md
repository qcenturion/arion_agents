# Workstream: Orchestrator

## Goals
- Deterministic executor with no reasoning capability
- Validate and execute JSON Instruction objects
- Enforce permissions (tools, routes) from config
- Maintain session state and history
- Emit rich OpenTelemetry traces/spans with events

## Decisions
- Instruction schema: as defined in README (reasoning + action with USE_TOOL | ROUTE_TO_AGENT | RESPOND)
- State format: JSON-serializable structure persisted in-memory for POC, pluggable later

## Milestones & Tasks
- M1: Minimal loop
  - [ ] Define Instruction pydantic model with strict validation
  - [ ] Orchestrator loop (parse -> validate -> execute -> trace)
  - [ ] In-memory session state with history
  - [ ] Basic span events for instruction and results
- M2: Permissions & config
  - [ ] Enforce equipped_tools and allowed_routes
  - [ ] Config loader (SQLite-backed, see api_and_config_store)
  - [ ] System-provided parameter injection (e.g., customer_id)
- M3: Robustness & observability
  - [ ] Error handling, retries for tool calls
  - [ ] Structured logs and trace attributes
  - [ ] Trace IDs surfaced in responses

## Acceptance Criteria
- RESPOND action terminates loop, returns payload
- Invalid tool/route is blocked and logged, not executed
- Traces include instruction JSON and tool results as span events

## Dependencies
- agents_llm (Instruction generation)
- tools (tool registry and execution)
- observability (OTel setup)
