# Workstream: API & Config Store

## Goals
- FastAPI service to host orchestration endpoints
- Database-agnostic config store (agents, tools) via SQLAlchemy
- Alembic migrations for schema evolution

## Decisions
- DB: abstract via SQLAlchemy; `DATABASE_URL` drives backend
  - Local: SQLite (e.g., `sqlite:///config.db`)
  - Prod: Managed Postgres on GCP (Cloud SQL/AlloyDB) recommended
- API shape: `/invoke`, `/config/*`, `/health`

## Milestones & Tasks
- M1: Skeleton API
  - [ ] FastAPI app, `/health` endpoint
  - [ ] `/invoke` that triggers orchestrator with request payload
  - [ ] Pydantic models for request/response
- M2: Config management
  - [ ] SQLAlchemy models for agents, tools, associations
  - [ ] Alembic init and baseline migration
  - [ ] CRUD endpoints (auth TBD)
  - [ ] Loader used by orchestrator
- M3: Migrations & packaging
  - [ ] Migration workflow documented
  - [ ] Dockerfile and Compose integration

## Acceptance Criteria
- Local run returns a trace ID and response
- Config changes reflect in agent capabilities on next run
 - Swapping `DATABASE_URL` from SQLite to Postgres requires no code changes

## Configuration
- `DATABASE_URL` (prod-capable) – example: `postgresql+psycopg://user:pass@host:5432/db` (GCP Cloud SQL)
- For local dev, fallback to `sqlite:///config.db` is acceptable
