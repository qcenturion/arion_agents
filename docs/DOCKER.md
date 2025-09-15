# Dockerized Dev & Runtime

## Overview
This project includes a Dockerfile for the API and a docker-compose stack with Postgres. Use it for consistent local dev and easier deployment to container platforms.

## Prereqs
- Docker Desktop (or compatible)
- Put your Gemini key in a local file (git-ignored): `arion_agents/.secrets/gemini_api_key`

## Build & Run
- Build images:
  - `make compose-build`
- Start stack (db + api):
  - `make compose-up`
- Logs:
  - `make compose-logs`
- Stop:
  - `make compose-down`

The API listens on `http://localhost:8000`.
Your local `.secrets/` directory is mounted read-only into the container at `/app/.secrets`, and the app reads `/app/.secrets/gemini_api_key` automatically.

## First-Time DB Init
The API’s container command runs a bootstrap step:
- `python -c 'from arion_agents.db import init_db; init_db()'` to create tables
Then it starts the server: `python -m arion_agents api`.

## Seeding Demos (from host)
- Basic seed:
  - `make seed-demo` (uses host `localhost:8000`)
- WorldTime demo (real HTTP tool):
  - `make seed-time`

## Env Vars
- `DATABASE_URL` is wired in compose to use the `db` service.
- `GEMINI_API_KEY` and `GEMINI_MODEL` are passed through if set.
- `OTEL_ENABLED` defaults to false; set true and provide `OTEL_EXPORTER_OTLP_ENDPOINT` to export traces.

## Verify
- Health: `curl -sS http://localhost:8000/health`
- Run demo: `curl -sS -X POST :8000/run -H 'content-type: application/json' -d '{"network":"time_demo","user_message":"What time is it?","debug":true}'`

## Notes
- The Dockerfile uses `python:3.12-slim` and sets `PYTHONPATH=/app/src`.
- For dev live-reload, prefer running on host (`make run-api`) or add a bind mount + `UVICORN_RELOAD=true` in a dev override compose file.
- For production, build and push the same image; configure secrets via your orchestrator (e.g., Cloud Run secrets) and set `OTEL_ENABLED=true`.
