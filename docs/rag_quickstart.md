# RAG Quickstart

This guide walks through two workflows for exercising the `rag:hybrid` provider.

- **Quick Inline Snapshot Loop** – index a small corpus in the dev RAG service, then
  run `tools/serve_and_run.sh` against a frozen snapshot (no Postgres required).
- **Full Network Flow** – bring up Postgres, register the tool via the config API,
  publish the network, and run the smoke test through the real `/run` endpoint.

Keep a separate terminal open for each long-running process (API, RAG service).

## Prerequisites

1. `make install` with the bundled virtualenv activated (`source .venv/bin/activate`).
2. The dev RAG service container (runs FastAPI app at `tools/rag_service/service.py`).
3. Optional: Docker Compose Postgres (`make db-up`) if you follow the full flow.

## Start the RAG Service

The dev service now persists vectors via an embedded Qdrant store. Mount the storage
directory somewhere durable so restarts keep the index.

```bash
# from repo root
source .venv/bin/activate
mkdir -p data/qdrant
RAG_QDRANT_PATH="$(pwd)/data/qdrant" \
RAG_COLLECTIONS=city_activities \
uvicorn tools.rag_service.service:app --host 0.0.0.0 --port 7100
```

> The service loads the `BAAI/bge-large-en` model by default. Set `RAG_EMBED_MODEL`
> if you need something else, and ensure the storage path lives on a mounted volume
> when running inside Docker.

## Index the Sample Corpus

The service persists documents to the Qdrant store. Re-index only when the corpus
changes or you explicitly reset the storage directory.

```bash
source .venv/bin/activate
python tools/rag_index.py tools/rag_service/city_activities.md \
  --service-url http://localhost:7100 \
  --collection city_activities

# sanity check
python tools/rag_search.py --service-url http://localhost:7100 \
  --collection city_activities \
  --query "Things to do in London"
```

## Workflow A: Quick Inline Snapshot

1. Export a compiled snapshot once (after running the full flow) or check one in at
   `snapshots/locations_rag_demo.json`.
2. Update `tools/serve_and_run.sh` command to point at the snapshot.

```bash
bash tools/serve_and_run.sh snapshots/locations_rag_demo.json \
  "What should I do in London?"
```

This path bypasses Postgres entirely; you only need the snapshot JSON and the RAG service.
Convenience wrapper:

```bash
tools/run_rag_snapshot.sh "What should I do in London?"
```

## Workflow B: Full Network + Config API

1. Ensure Postgres is running:
   ```bash
   make db-up
   make db-init
   export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/arion_agents
   ```
2. Start the API (foreground):
   ```bash
   make run-api
   ```
3. Register the RAG tool, attach it to the `locations_demo` network, equip the agent, and publish:
   ```bash
   # list networks -> capture ID (e.g., 4)
   curl http://localhost:8000/config/networks

   # create tool
   curl -X POST http://localhost:8000/config/tools \
     -H "Content-Type: application/json" \
     -d '{
       "key": "city_rag",
       "display_name": "City Activities RAG",
       "description": "Retrieve interesting activities for major cities.",
       "provider_type": "rag:hybrid",
       "params_schema": {
         "query": {"source": "agent", "required": true},
         "top_k": {"source": "agent"},
         "filter": {"source": "agent"}
       },
       "additional_data": {
         "agent_params_json_schema": {
           "type": "object",
           "properties": {
             "query": {"type": "string", "minLength": 1},
             "top_k": {"type": "integer", "minimum": 1},
             "filter": {"type": "object"}
           },
           "required": ["query"],
           "additionalProperties": false
         },
         "rag": {
           "service": {
             "base_url": "http://localhost:7100",
             "search_path": "/search",
             "timeout": 20,
             "default_payload": {"collection": "city_activities"}
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
     }'

   # attach to network 4
   curl -X POST http://localhost:8000/config/networks/4/tools \
     -H "Content-Type: application/json" \
     -d '{"tool_keys": ["city_rag"]}'

   # equip the location_details agent
   curl http://localhost:8000/config/networks/4/agents
   curl -X PUT http://localhost:8000/config/networks/4/agents/<agent_id>/tools \
     -H "Content-Type: application/json" \
     -d '{"tool_keys": ["sun", "geonames", "city_rag"]}'

   # publish
   curl -X POST http://localhost:8000/config/networks/4/versions/compile_and_publish \
     -H "Content-Type: application/json" -d '{}'
   ```
4. Smoke test via the live `/run` flow:
```bash
bash tools/serve_and_run.sh locations_demo "What should I do in London?" --network locations_demo
```

To automate steps 3–4 (after the API is running and the RAG service is seeded), run:

```bash
make rag-demo
```

`make rag-demo` indexes the sample corpus, ensures the RAG tool is configured on
`locations_demo`, publishes the network, and executes the smoke test.

## Reset / Cleanup

- Stop the API (CTRL+C) and Postgres (`make db-down`) when done.
- Stop the RAG service process when done.
- Re-run `tools/rag_index.py` only when the corpus changes or you wipe `data/qdrant`.

See `docs/workstreams/RAG_hybrid_search.md` for longer-term design notes and future work.
