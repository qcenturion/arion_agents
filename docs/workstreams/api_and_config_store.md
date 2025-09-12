# Workstream: API & Config Store

## Goals
- FastAPI service to host orchestration endpoints
- Database-agnostic config store (agents, tools) via SQLAlchemy
- Alembic migrations for schema evolution
 - Cloud-ready: containerized for Cloud Run; 12-factor config

## Decisions
- DB: abstract via SQLAlchemy; `DATABASE_URL` drives backend
  - Local: SQLite (e.g., `sqlite:///config.db`)
  - Prod: Managed Postgres on GCP (Cloud SQL/AlloyDB) recommended
- API shape:
  - `/invoke` — synchronous run execution
  - `/runs/{run_id}/events` — SSE/WebSocket for real-time execution events
  - `/config/*` — CRUD for agents, tools, routes
  - `/health`

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
- M4: Realtime events
  - [ ] EventPublisher interface (+ in-memory impl)
  - [ ] `/runs/{run_id}/events` SSE endpoint
  - [ ] Cloud Run/WebSocket compatibility validated

## Acceptance Criteria
- Local run returns a trace ID and response
- Config changes reflect in agent capabilities on next run
- Swapping `DATABASE_URL` from SQLite to Postgres requires no code changes
 - UI can subscribe to a run’s events and display step updates

## Configuration
- `DATABASE_URL` (prod-capable) – example: `postgresql+psycopg://user:pass@host:5432/db` (GCP Cloud SQL)
- For local dev, fallback to `sqlite:///config.db` is acceptable
