# Local Development and Testing

This guide explains how to run the API and database locally for development and tests.

Prerequisites
- Python 3.12+
- Docker (for local Postgres)
- Make (optional but recommended)

Setup (one-time)
- Create venv and install deps:
  - `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
  - Or: `make install`

Local Postgres (recommended)
- Start DB: `make db-up`
- Set `DATABASE_URL` for the API/migrations (example):
  - `export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/arion_agents`
- Run migrations: `make db-migrate`
- Tail logs: `make db-logs`
- Stop DB: `make db-down`

Run the API
- Ensure env is set (Postgres or SQLite fallback):
  - Postgres: `export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/arion_agents`
  - SQLite (quick start): omit `DATABASE_URL` to use `sqlite:///config.db`
- Start server: `make run-api`
- Health check: `curl http://localhost:8000/health`

Config endpoints (examples)
- Create tool: `curl -X POST :8000/config/tools -H 'content-type: application/json' -d '{"name":"TemplateRetrievalTool"}'`
- Create agents:
  - `curl -X POST :8000/config/agents -H 'content-type: application/json' -d '{"name":"TriageAgent"}'`
  - `curl -X POST :8000/config/agents -H 'content-type: application/json' -d '{"name":"HumanRemarksAgent"}'`
- Assign tools: `curl -X PUT :8000/config/agents/1/tools -H 'content-type: application/json' -d '{"tools":["TemplateRetrievalTool"]}'`
- Assign route: `curl -X PUT :8000/config/agents/1/routes -H 'content-type: application/json' -d '{"agents":["HumanRemarksAgent"]}'`

Invoke endpoint (example)
- `curl -X POST :8000/invoke -H 'content-type: application/json' -d '{
    "agent_name":"TriageAgent",
    "allow_respond":false,
    "system_params":{"customer_id":"abc123"},
    "instruction":{
      "reasoning":"Done",
      "action":{"type":"RESPOND","payload":{"message":"ok"}}
    }
  }'`

Testing
- Unit tests (SQLite): `pytest`
- Integration tests (Postgres):
  - Start DB: `make db-up`
  - `export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/arion_agents`
  - `make test-int`

Troubleshooting
- API can’t bind port in some sandboxes; run locally on your machine.
- If imports fail for OpenTelemetry, set `OTEL_ENABLED=false` (tracing optional for local dev).
- If migrations fail, verify `DATABASE_URL` and that `make db-up` started the container.
