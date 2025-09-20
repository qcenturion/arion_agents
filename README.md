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

## Local Testing

1. Run the smoke script with an inline snapshot (requires `.secrets/gemini_api_key` or `GEMINI_API_KEY`):
   ```bash
   bash tools/serve_and_run.sh snapshots/locations_demo.json "When is sunset in Paris?"
   ```
2. Inspect the structured artifact:
   ```bash
   ./tools/show_last_run.py
   ```
   This prints prompts, raw LLM output, tool calls, execution log, and the final response.
3. View logs:
   - Focused file log: `logs/server.log` (rotating; appended each run).
   - Detailed Uvicorn log: `/tmp/arion_uvicorn.log` (per run instance).
   ```bash
   tail -n 80 logs/server.log
   tail -n 120 /tmp/arion_uvicorn.log
   ```

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

## Observability & Debugging

- Application logs rotate under `logs/server.log`; each server start re-attaches the file handler.
- Every `/run` request writes a structured artifact to `logs/runs/` with prompts, tool outputs, execution log, and final response.
- `bash tools/serve_and_run.sh ...` surfaces the JSON reply plus the latest `logs/server.log` tail.
- `tools/show_last_run.py` pretty-prints the most recent run artifact, including prompts, raw LLM output, tool calls, execution log, and the final payload.

## Front-End Roadmap

A dedicated control-plane UI will drive configuration and observability:

- CRUD workflow for networks, agents, tools, and routes backed by the `/config` API.
- Snapshot publish history with diffing and rollback affordances.
- Rich run viewer that surfaces the data captured in `logs/runs/` (prompts, tool traces, execution log, final response) and allows drilling into tool metadata.
- Inline testing harness that wraps `serve_and_run.sh` functionality for operators.

Progress on the UI will be tracked in the `docs/workstreams` directory; contributions should align with the layout described in `docs/architecture.md`.

## Hybrid RAG Tooling

`rag:hybrid` now delegates to an external RAG service container. The runtime only sends a query (and optional filters) over HTTP; the container handles chunking, embeddings, indexing, and reranking. Tool metadata points at the service:

```json
{
  "provider_type": "rag:hybrid",
  "params_schema": {
    "query": {"source": "agent", "required": true},
    "top_k": {"source": "agent", "required": false},
    "filter": {"source": "agent", "required": false}
  },
  "metadata": {
    "rag": {
      "service": {
        "base_url": "http://localhost:7000",
        "search_path": "/search",
        "timeout": 20,
        "api_key_header": "Authorization",
        "default_payload": {
          "collection": "city_activities"
        }
      },
      "agent_params_json_schema": {
        "type": "object",
        "properties": {
          "query": {"type": "string", "minLength": 1},
          "top_k": {"type": "integer", "minimum": 1},
          "filter": {"type": "object"}
        },
        "required": ["query"],
        "additionalProperties": false
      }
    }
  }
}
```

Use `tools/rag_index.py` to upload documents to the container for indexing:

```bash
python tools/rag_index.py docs/my_corpus --service-url http://localhost:7000 \
    --collection city_activities
```

Validate retrieval end-to-end with `tools/rag_search.py`:

```bash
python tools/rag_search.py --service-url http://localhost:7000 \
    --query "What is hybrid search?"
```

Both scripts honour `--collection`, `--top-k`, and arbitrary extra payload JSON so the same defaults can be mirrored inside tool metadata. See `docs/rag_quickstart.md` for full workflows.

## Local Utilities

- `make dev` – reloadable API with verbose logging.
- `make lint` / `make format` – Ruff check/format on `src/`.
- `make snapshot-sun` – generate a minimal example snapshot (`tools/sun_snapshot.json`).
- `make seed-sun` – seed the database from that snapshot.
- `make run-message NET=... MSG="..."` – call `/run` with optional system params.
- `tools/run_rag_snapshot.sh` – quick inline RAG smoke test (service + snapshot).
- `make rag-demo` – index sample corpus, wire the RAG tool, and run the smoke test against Postgres.
- `tools/show_last_run.py` – inspect the latest `/run` artifact without combing through logs.

## Deployment Notes

- Package the API via the provided `Dockerfile`; it installs dependencies, initializes the schema, and runs `python -m arion_agents api`.
- Configure `DATABASE_URL`, `GEMINI_API_KEY`, optional `GEMINI_MODEL`, and logging verbosity (`LOG_LEVEL`, `UVICORN_LOG_LEVEL`).
- Plan for GKE or Cloud Run by running Postgres (Cloud SQL/AlloyDB) separately from the API deployment. Only compiled snapshots are read at runtime; authoring remains in the control plane.

## Front-End Alignment

The control-plane UI should surface:
- Network, tool, and agent CRUD via the `/config` routes.
- Prompt previews and debug traces returned by `/run` (pretty print the `debug` payload and tool logs).
- Snapshot publish history so operators can roll forward/back quickly.
- RAG configuration and monitoring once the hybrid retriever tool lands.

With these pieces in place, the UI drives configuration while `/run` remains a low-latency executor backed by validated, pre-compiled graphs.
