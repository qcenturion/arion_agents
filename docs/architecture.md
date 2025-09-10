# Architecture Overview

This document outlines the system architecture at a high level. It will evolve as features are added.

## System Context
- External services: LLM providers, vector DB / memory store, GitHub, observability.
- Interfaces: CLI, (future) HTTP API, and tool integrations.
 - Data: configuration DB only in POC; production-ready DB is pluggable.

## Core Components
- Agent Core: policy loop, tool routing, error handling.
- LLM Integration: providers, retry/backoff, prompt templates.
- Memory & State: short-term context, long-term storage, traces.
- Tools & Integrations: external APIs, file I/O, search.
- Interfaces: CLI now; API/SDK later.

## Database Decoupling
- Principle: the application must not depend on a specific SQL vendor. Use an abstraction (SQLAlchemy ORM + repository/service layer) with a single env `DATABASE_URL`.
- Local Dev: default to SQLite for ease of setup.
- Production: recommend managed Postgres (e.g., GCP Cloud SQL or AlloyDB). MySQL or others are possible via drivers.
- Migrations: managed by Alembic; no raw DDL in code.
- Access Pattern: read-mostly for configuration (agents, tools). Runtime session data remains out of DB for POC; may be introduced later via a separate persistence strategy.

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
