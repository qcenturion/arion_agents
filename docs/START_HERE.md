# Start Here

1. **Understand the Runtime**
   - Read `README.md` for setup, snapshot workflow, and logging utilities.
   - Inspect `src/arion_agents/api.py` for entrypoints (`/run`, `/invoke`, `/config/*`).

2. **Bring Up the Stack**
   - `make db-up && make db-init`
   - `make run-api`
   - Smoke test: `bash tools/serve_and_run.sh snapshots/locations_demo.json "When is sunset in Paris?"`
   - Inspect logs with `tools/show_last_run.py`.

3. **Plan the Front-End**
   - `docs/architecture.md` outlines the control-plane UI expectations.
   - Design tasks are tracked under `docs/workstreams/frontend.md` (create if needed) – focuses on network/tool CRUD, run viewer, and snapshot history.

4. **Explore Hybrid RAG**
   - Review `docs/rag_quickstart.md` for step-by-step flows (inline snapshot and full Postgres-based testing).
   - Use `tools/rag_index.py` and `tools/rag_search.py` against the local RAG service container.

5. **Key Tools**
   - `tools/serve_and_run.sh`: boot server + inline snapshot run + log tail.
   - `tools/show_last_run.py`: display the most recent run artifacts.
   - `tools/seed_location_demo.py` & `tools/seed_sun_demo.py`: seed example networks.

6. **Contribute**
   - Follow `AGENTS.md` for contributor guidelines.
   - Keep documentation synced with runtime/UX changes.

7. **Open Questions**
   - Front-end component boundaries and framework choice.
   - RAG tool surfacing in the UI once implemented.
   - Observability beyond log streaming (metrics/traces) if needed later.
