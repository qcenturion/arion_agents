# Epic: Control Plane (Frontend + API)

## Summary
Deliver a UI and API endpoints that allow operators to create/update agents, tools, and routes; visualize the topology; trigger runs with inputs; and view real-time execution logs. Acts as the control plane for the agent framework.

## Scope
- CRUD for agents, tools, route permissions
- Topology viewer (graph)
- Run invocation from UI with input payload
- Real-time log stream of steps (agent transitions, tool calls, outputs)
- Deep links to OpenTelemetry traces in Jaeger/Grafana

## Interfaces
- API endpoints under `/config/*` for CRUD
- `/invoke` to start runs; returns `{run_id, trace_id}`
- `/runs/{run_id}/events` via SSE/WebSocket for live updates

## Milestones
- CP1: CRUD + list views
- CP2: Run trigger + live log
- CP3: Topology graph + trace deep links

## Dependencies
- Orchestrator event publishing
- API config store and models
- Observability stack
