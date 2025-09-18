# Start Here: Session Boot + Next Actions

This file orients next sessions: how to start, what changed, and what to tackle next.

GitHub Repo
- URL: git@github.com:qcenturion/arion_agents.git
- Default branch: `main`
- Pull latest: `git pull origin main`

What this project is
- Python backend for an LLM‑powered agent orchestrator (FastAPI).
- Clean separation: Orchestrator (deterministic), Agents (LLM), Tools (deterministic), Config Store (Postgres), Observability (OTel‑ready).

Key docs to skim first
- Project overview: `README.md`
- Architecture: `docs/architecture.md`
- Data model: `docs/epics/data_model.md`
- Workstreams index: `docs/workstreams/README.md`
- Tracking: `docs/workstreams/TRACKING.md`

Code entry points
- API app: `src/arion_agents/api.py` (endpoints: `/health`, `/invoke`, `/config/*`)
- Config endpoints: `src/arion_agents/api_config.py`
- Orchestrator: `src/arion_agents/orchestrator.py`
- DB/ORM: `src/arion_agents/db.py`, `src/arion_agents/config_models.py`
- Docker Compose (Postgres): `docker-compose.yml`

What changed in the latest refactor
- Switched to Postgres‑only with a clean schema (no Alembic yet) and `create_all()` bootstrap.
- Added config schema `cfg_*`: networks, agents, global tools, network‑local tools (copied from globals), agent_tools, agent_routes, network_versions, compiled_snapshots.
- Rewrote config API under `/config` to be network‑scoped and to replicate global tools into a network.
- Implemented compile‑and‑publish endpoint to generate JSON snapshot and set `current_version`.
- `/invoke` now loads compiled snapshots by network/version and enforces permissions from that artifact.
- Removed legacy SQLite code, Alembic scaffolding, and temporary caches/hacks.

Run locally (fresh session)
- Open terminal in `arion_agents/` and activate venv: `source .venv/bin/activate`
- Start DB: `make db-up`
- Initialize schema: `make db-init`
- Smoke test: `bash tools/serve_and_run.sh snapshots/locations_demo.json "When is sunset in Paris?"`
- Start API: `make run-api`

Quick config API flow
- Create a global tool: `POST /config/tools`
- Create a network: `POST /config/networks`
- Add tool(s) to network (local copies): `POST /config/networks/{network_id}/tools`
- Create agents under network: `POST /config/networks/{network_id}/agents`
- Assign tools/routes: `PUT /config/networks/{id}/agents/{agent_id}/tools|routes`
- Publish snapshot: `POST /config/networks/{network_id}/versions/compile_and_publish`
- Invoke using snapshot: `POST /invoke` with `{ network, agent_key, instruction, version? }`

LLM quick check (Gemini)
- Local secret file: `echo "<key>" > .secrets/gemini_api_key` (git-ignored)
- Or set env: `export GEMINI_API_KEY=$(cat .secrets/gemini_api_key)` and optional `export GEMINI_MODEL=gemini-2.5-flash`
- Test endpoint (API running):
  - `curl -sS -X POST :8000/llm/complete -H 'content-type: application/json' -d '{"prompt":"Say hello"}'`
  - Returns: `{ "model": "...", "text": "..." }`

Seed and curl examples
- Seed everything via script (API must be running):
  - `make seed-demo`
  - Overrides: `make seed-demo API_URL=http://127.0.0.1:8000`
- Or use curl (assumes API at localhost:8000):
  - Create global tool
    `curl -sS -X POST localhost:8000/config/tools -H 'content-type: application/json' -d '{"key":"templater","display_name":"Template Retrieval","params_schema":{"intent":{"source":"agent","required":false},"customer_id":{"source":"system","required":true}}}'`
  - Create network
    `curl -sS -X POST localhost:8000/config/networks -H 'content-type: application/json' -d '{"name":"support"}'`
  - Add tool to network (replace NET_ID)
    `curl -sS -X POST localhost:8000/config/networks/NET_ID/tools -H 'content-type: application/json' -d '{"tool_keys":["templater"]}'`
  - Create agents
    `curl -sS -X POST localhost:8000/config/networks/NET_ID/agents -H 'content-type: application/json' -d '{"key":"triage","allow_respond":true}'`
    `curl -sS -X POST localhost:8000/config/networks/NET_ID/agents -H 'content-type: application/json' -d '{"key":"writer","allow_respond":true}'`
  - Assign tools/routes (replace TRIAGE_ID)
    `curl -sS -X PUT localhost:8000/config/networks/NET_ID/agents/TRIAGE_ID/tools -H 'content-type: application/json' -d '{"tool_keys":["templater"]}'`
    `curl -sS -X PUT localhost:8000/config/networks/NET_ID/agents/TRIAGE_ID/routes -H 'content-type: application/json' -d '{"agent_keys":["writer"]}'`
  - Publish snapshot
    `curl -sS -X POST localhost:8000/config/networks/NET_ID/versions/compile_and_publish -H 'content-type: application/json' -d '{}'`
  - Invoke (replace VERSION if needed)
    `curl -sS -X POST localhost:8000/invoke -H 'content-type: application/json' -d '{"network":"support","agent_key":"triage","instruction":{"reasoning":"done","action":{"type":"RESPOND","payload":{"ok":true}}}}'`

Next steps (high‑value)
- Network tool overrides: add PATCH endpoint to edit network‑local `params_schema` and metadata after replication.
- Snapshot validation: validate graph (dangling routes, tool param schemas, required system params).
- Orchestrator tooling: extend tool schema (agent/system/default) and integrate enforcement using compiled `params_schema`.
- Basic UI seed: a minimal page to visualize network agents, tools, and routes (optional now).
- Observability: add OTel Collector docker‑compose, quiet exporter errors when collector is offline.

5‑minute startup checklist
- `git pull origin main`
- `cd arion_agents && source .venv/bin/activate`
- `make db-up && make db-init`
- `make run-api` and hit `/health`
