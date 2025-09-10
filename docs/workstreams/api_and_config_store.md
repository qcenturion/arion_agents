# Workstream: API & Config Store

## Goals
- FastAPI service to host orchestration endpoints
- SQLite-backed config DB (agents, tools) only
- Alembic migrations for schema evolution

## Decisions
- DB: SQLite for config (no runtime/session data)
- API shape: `/invoke`, `/config/*`, `/health`

## Milestones & Tasks
- M1: Skeleton API
  - [ ] FastAPI app, `/health` endpoint
  - [ ] `/invoke` that triggers orchestrator with request payload
  - [ ] Pydantic models for request/response
- M2: Config management
  - [ ] Tables for agents, tools, associations
  - [ ] CRUD endpoints (auth TBD)
  - [ ] Loader used by orchestrator
- M3: Migrations & packaging
  - [ ] Alembic setup
  - [ ] Dockerfile and Compose integration

## Acceptance Criteria
- Local run returns a trace ID and response
- Config changes reflect in agent capabilities on next run
