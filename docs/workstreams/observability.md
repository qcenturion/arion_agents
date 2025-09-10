# Workstream: Observability (OTel, Jaeger, Prometheus, Grafana)

## Goals
- End-to-end traces, metrics, logs using OpenTelemetry
- Local stack via Docker Compose
- Dashboards for API health and orchestration latency

## Decisions
- Use OpenTelemetry Collector to route OTLP data
- Export traces to Jaeger, metrics to Prometheus
- Visualize in Grafana (dashboards for API + Orchestrator)

## Milestones & Tasks
- M1: Local tracing
  - [ ] Add OTel SDK + FastAPI/requests instrumentation (#issue)
  - [ ] OTLP exporter to local Collector (#issue)
  - [ ] Jaeger UI shows traces with events (#issue)
- M2: Metrics + dashboards
  - [ ] Prometheus scrape via Collector (#issue)
  - [ ] Grafana with OTel + Prometheus data sources (#issue)
  - [ ] Dashboards for latency, errors, token usage (#issue)
- M3: Logs + sampling
  - [ ] Structured logging with trace correlation (#issue)
  - [ ] Tail-based sampling in Collector (optional) (#issue)

## Configuration
- `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317`
- Service name envs and resource attributes
