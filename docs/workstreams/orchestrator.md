# Workstream: Orchestrator

## Goals
- Deterministic executor with no reasoning capability
- Validate and execute JSON Instruction objects
- Enforce permissions (tools, routes) from config
- Maintain session state and history
- Emit rich OpenTelemetry traces/spans with events
 - Emit domain-level execution events for UI streaming (run_id-scoped)

## Decisions
- Instruction schema: as defined in README (reasoning + action with USE_TOOL | ROUTE_TO_AGENT | RESPOND)
- State format: JSON-serializable structure persisted in-memory for POC, pluggable later

## Milestones & Tasks
- M1: Minimal loop
  - [ ] Define Instruction pydantic model with strict validation (#issue)
  - [ ] Orchestrator loop (parse -> validate -> execute -> trace) (#issue)
  - [ ] In-memory session state with history (#issue)
  - [ ] Basic span events for instruction and results (#issue)
- M2: Permissions & config
  - [ ] Enforce equipped_tools and allowed_routes (#issue)
  - [ ] Config loader (SQLAlchemy, see api_and_config_store) (#issue)
  - [ ] System-provided parameter injection (e.g., customer_id) (#issue)
- M3: Robustness & observability
  - [ ] Error handling, retries for tool calls (#issue)
  - [ ] Structured logs and trace attributes (#issue)
  - [ ] Trace IDs surfaced in responses (#issue)
- M4: Event streaming
  - [ ] Define `run_id` and EventPublisher interface (#issue)
  - [ ] Publish per-step events (agent chosen, tool invoked, result/error) (#issue)
  - [ ] Pluggable transports (in-memory, Pub/Sub later) (#issue)

## Acceptance Criteria
- RESPOND action terminates loop, returns payload
- Invalid tool/route is blocked and logged, not executed
- Traces include instruction JSON and tool results as span events

## Dependencies
- agents_llm (Instruction generation)
- tools (tool registry and execution)
- observability (OTel setup)
