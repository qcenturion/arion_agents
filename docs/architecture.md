# Architecture Overview

This document outlines the system architecture at a high level. It will evolve as features are added.

## System Context
- External services: LLM providers, vector DB / memory store, GitHub, observability.
- Interfaces: CLI, (future) HTTP API, and tool integrations.
- Data: configuration DB only in POC; production-ready DB is pluggable.

## Deployment Targets
- Local Dev: run FastAPI with Uvicorn and Docker Compose for Postgres.
- Production: containerized ASGI app on GCP Cloud Run (preferred); Cloud Functions 2nd gen is possible via container entry.
- 12-factor config via env vars (`DATABASE_URL`, LLM provider keys, logging levels).

## Invocation Model
- Each invocation is a stateless request that executes the Orchestrator loop until a RESPOND action or policy stop.
- For long-running or asynchronous patterns, consider Pub/Sub + callbacks, but MVP is synchronous HTTP.
- Real-time visibility: an events stream (SSE/WebSocket) publishes step-by-step execution updates for the UI.

## Core Components
- Agent Core: policy loop, tool routing, error handling.
- LLM Integration: providers, retry/backoff, prompt templates.
- Memory & State: short-term context, long-term storage, traces.
- Tools & Integrations: external APIs, file I/O, search.
- Interfaces: CLI now; API/SDK later.
 - Control Plane (Frontend): CRUD for agents/tools/routes; visualize topology and runs; trigger invocations.

## Database Decoupling
- Principle: the application must not depend on a specific SQL vendor. Use an abstraction (SQLAlchemy ORM + repository/service layer) with a single env `DATABASE_URL`.
- Local Dev: default to SQLite for ease of setup.
- Production: recommend managed Postgres (e.g., GCP Cloud SQL or AlloyDB). MySQL or others are possible via drivers.
- Migrations: managed by Alembic; no raw DDL in code.
- Access Pattern: read-mostly for configuration (agents, tools). Runtime session data remains out of DB for POC; may be introduced later via a separate persistence strategy.

## Runtime Observability
- Default logging targets rotating files; forward to Cloud Logging or another aggregator in production.
- Future: add tracing/metrics when the runtime stabilizes so the same instrumentation can feed UI replay.
- Execution events (domain-level) should stream over SSE/WebSockets for the frontend with a generated `run_id`.

## Cross-Cutting Concerns
- Config & Secrets management
- Logging/Tracing/Telemetry
- Evaluation & Testing strategy
- Security & Compliance considerations
 - Portability across database backends (SQLA + Alembic)

## Open Questions / Decisions
- Which providers and SDKs to prioritize?
- Standard memory interface and backing store?
- Tracing/eval stack choices (e.g., TruLens, DeepEval, promptfoo)?
 - Postgres vs. MySQL in production? (default to Postgres)
 - Whether to persist runtime session state later and where
