# arion_agents

arion_agents is a FastAPI-based runtime for executing pre-compiled LLM agent networks. Networks, tools, and prompts are authored through the config API, compiled into immutable snapshots, and executed with minimal latency at `/run`.

## Quickstart

1. **Install deps**
   ```bash
   cd arion_agents
   source .venv/bin/activate  # bundled venv
   make install
   ```
2. **Bring up Postgres (recommended)**
   ```bash
   make db-up           # docker-compose postgres:16
   make db-init         # initialize config schema
   export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/arion_agents
   ```
3. **Seed an example network**
   ```bash
   API_URL=http://127.0.0.1:8000 make seed-location
   ```
   This creates global tools (GeoNames + sunrise API), agents, routes, and publishes a compiled snapshot.
4. **Run the API**
   ```bash
   make run-api
   ```
5. **Smoke test**
   ```bash
   bash tools/serve_and_run.sh snapshots/locations_demo.json "When is sunset in Paris?"
   ```
   The script starts the API, posts `/run` with an inline snapshot, prints the JSON response, and tails the server log.

SQLite is still available via `make run-api-sqlite`, but the production target is Postgres so the runtime layout matches Cloud SQL or AlloyDB deployments.

## Snapshot-First Runtime

- `/config/...` endpoints create and update networks, tools, and agents. `POST /config/networks/{id}/versions/compile_and_publish` materializes a snapshot into `cfg_compiled_snapshots`.
- `/run` accepts either a `network` name (fetched from Postgres) or an inline `snapshot` payload. Inline snapshots are ideal for load tests and local experiments.
- `/invoke` executes a single structured instruction against a compiled graph—useful for testing tool constraints without calling the LLM.

## Unified HTTP Tool Provider

Every outbound HTTP tool is powered by the `http:request` provider. Tool metadata defines:

```json
{
  "http": {
    "base_url": "https://api.sunrise-sunset.org",
    "path": "/json",
    "method": "GET",
    "query": {
      "lat": {"source": "agent"},
      "lng": {"source": "agent"}
    },
    "response": {"unwrap": "results"}
  },
  "agent_params_json_schema": { ... }
}
```

The provider enforces parameter sourcing (agent, system, const, secret), shapes responses, and keeps all HTTP tools consistent. Additional transport types can be introduced later via new providers if needed.

## Local Utilities

- `make dev` – reloadable API with verbose logging.
- `make lint` / `make format` – Ruff check/format on `src/`.
- `make snapshot-sun` – generate a minimal example snapshot (`tools/sun_snapshot.json`).
- `make seed-sun` – seed the database from that snapshot.
- `make run-message NET=... MSG="..."` – call `/run` with optional system params.

## Logging & Diagnostics

- Application logs rotate under `logs/server.log` (created on demand).
- Each `/run` request writes a JSON artifact to `logs/runs/` with request/response metadata.
- `serve_and_run.sh` surfaces both the API response and the latest log tail so you can compare to expected traces quickly.

## Deployment Notes

- Package the API via the provided `Dockerfile`; it installs dependencies, initializes the schema, and runs `python -m arion_agents api`.
- Configure `DATABASE_URL`, `GEMINI_API_KEY`, optional `GEMINI_MODEL`, and logging verbosity (`LOG_LEVEL`, `UVICORN_LOG_LEVEL`).
- Plan for GKE or Cloud Run by running Postgres (Cloud SQL/AlloyDB) separately from the API deployment. Only compiled snapshots are read at runtime; authoring remains in the control plane.

## Front-End Alignment

The control-plane UI should surface:
- Network, tool, and agent CRUD via the `/config` routes.
- Prompt previews and debug traces returned by `/run` (pretty print `debug` payload and tool logs).
- Snapshot publish history so operators can roll forward/back quickly.

With these pieces in place, the UI drives configuration while `/run` remains a low-latency executor backed by validated, pre-compiled graphs.
