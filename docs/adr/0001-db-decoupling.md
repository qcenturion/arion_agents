# ADR 0001: Database Decoupling Strategy

## Status
Proposed

## Context
The framework must support local developer ergonomics and production deployment on managed databases (e.g., GCP Cloud SQL/Postgres). Early coupling to a specific DB increases migration risk and slows delivery.

## Decision
- Use SQLAlchemy as the ORM/DB toolkit and Alembic for migrations.
- Expose a single `DATABASE_URL` env var to select the backend at runtime.
- Default to SQLite locally; prefer Postgres in production on GCP.
- Keep runtime session/state data out of the DB for the POC; DB stores configuration only (agents, tools, associations). Revisit session persistence as a separate design.
- Encapsulate DB access behind a repository/service layer to avoid leaking ORM details into orchestration logic.

## Consequences
- Easier local setup (no DB provisioning) with a clear path to managed SQL.
- Migrations can run in CI/CD pipelines and locally.
- Slight increase in initial complexity due to the repository pattern, but improved portability and testability.

## Alternatives Considered
- Raw SQL with vendor-specific DDL: fast initially, brittle later.
- No ORM (databases library + SQL): acceptable, but we still need migrations and abstractions.
