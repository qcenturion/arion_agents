# Start Here: Context For Next Session

This file orients a future coding session to what exists, where to look, and what’s next.

What this project is
- Python backend for an LLM‑powered agent orchestrator (FastAPI), moving toward Cloud Run.
- Clean separation: Orchestrator (deterministic), Agents (LLM), Tools (deterministic), Config Store (SQLAlchemy), Observability (OTel).

Key docs to skim first
- Project overview: `README.md`
- Architecture: `docs/architecture.md`
- Data model proposal: `docs/epics/data_model.md`
- Workstreams index: `docs/workstreams/README.md`
- Tracking guide (labels, board, issues): `docs/workstreams/TRACKING.md`
- Epics: `docs/epics/control_plane.md`, `docs/epics/deployment_gcp.md`
- ADRs: `docs/adr/0001-db-decoupling.md`

Code entry points
- API app: `src/arion_agents/api.py` (endpoints: `/health`, `/invoke`, `/config/*`)
- Config endpoints: `src/arion_agents/api_config.py`
- Orchestrator core models: `src/arion_agents/orchestrator.py`
- DB/ORM scaffolding: `src/arion_agents/db.py`, `src/arion_agents/models.py`
- Alembic config/migrations: `alembic.ini`, `alembic/` folder

What we recently did
- Scaffolded CRUD for agents/tools/routes under `/config/*` with SQLAlchemy.
- Added orchestrator guardrails (RunConfig, permission checks, system vs agent params).
- Documented the production‑ready data model (relational + JSONB compiled snapshot).
- Set up local Postgres via Docker Compose and Make targets.
- Seeded GitHub labels/issues via a Bootstrap workflow; CI runs tests + lint.

What’s intentionally paused
- Further feature work until data model decisions are finalized (networks, versioning, compiled snapshot).

What to do next (suggested order)
1) Re‑read `docs/epics/data_model.md` and confirm answers to Open Questions (tenant/env, tool overrides, cycles policy, run persistence, scale).
2) Implement Network + Version tables and scope Agent/Routes/Equipped by network.
3) Add “Publish” that validates the graph and writes a JSONB compiled snapshot.
4) Update `/invoke` to load a compiled snapshot (by network/version) instead of live joining.
5) Add SSE `/runs/{run_id}/events` with an in‑memory publisher for live logs (UI uses it later).
6) Dockerfile + Compose for Observability stack (Collector + Jaeger + Prometheus + Grafana).

Where to find tasks
- GitHub Issues (labels: `workstream:*`, `type:*`) and the “arion_agents Roadmap” Project board.
- Many tasks are listed in `docs/workstreams/*.md` with `(#issue)` markers.

Quick repo health checks
- Last commits: `git log --oneline -n 10`
- CI/Actions: check GitHub Actions tab
- Tests locally: `make install && pytest` (unit / SQLite)
- Local DB up/migrate: see `docs/LOCAL_DEV.md`

If you only have 5 minutes
- Read `docs/epics/data_model.md` Open Questions and ask the user to confirm choices.
- If confirmed, start a PR with Network/Version migrations and updated models.
