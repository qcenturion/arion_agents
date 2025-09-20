# Repository Guidelines

## Project Structure & Module Organization
- Core runtime lives in `src/arion_agents/`: FastAPI surface (`api.py`), orchestration loop (`engine/loop.py`), prompt builders (`prompts/`), and tool providers (`tools/`). Keep new logic inside this tree so `PYTHONPATH=src` remains the only packaging requirement.
- Helper assets: `tools/` (seed scripts, `serve_and_run.sh`), `snapshots/` (checked-in example graphs), and `docs/` (design notes). New utilities should document themselves in `docs/` if they change workflows.
- Logs are produced under `logs/` at runtime but ignored from version control; treat the directory as ephemeral.

## Build, Run, and Development Commands
- Activate the bundled venv: `source .venv/bin/activate`, then `make install` to sync dependencies.
- `make lint` / `make format` invoke Ruff on `src/`; run them before sending a PR.
- Local API (Postgres): export `DATABASE_URL` and use `make run-api`; for quick experiments without Postgres, `make run-api-sqlite` will create `dev.db` automatically. See `docs/rag_quickstart.md` for the RAG service setup order.
- Fast feedback loop: `make dev` enables Uvicorn reloads and verbose logging.
- End-to-end sanity check: `bash tools/serve_and_run.sh snapshots/locations_demo.json "When is sunset in Paris?"` boots the API, sends `/run` with an inline snapshot, and tails logs.

## Coding Style & Naming Conventions
- Run Ruff’s formatter (`ruff format src`) and keep 4-space indents with sorted imports.
- Leverage type hints and Pydantic models throughout; new orchestration helpers belong in `src/arion_agents/engine/`.
- Modules stay `snake_case`, classes `PascalCase`, functions and variables `snake_case`. Co-locate configuration with its usage and prefer explicit dependency injection when wiring services.

## Commit & Pull Request Guidelines
- Follow conventional commits (`feat:`, `fix:`, optional scopes) with imperative subjects; wrap long body text at ~72 characters.
- PRs should link issues, explain behavior changes, list manual checks (e.g., `make lint`, `bash tools/serve_and_run.sh ...`), and attach relevant logs or snapshots.
- Ship schema or snapshot updates alongside code and update `docs/` when workflows change.

## Secrets & Configuration
- Store secrets in `.secrets/` (e.g., `.secrets/gemini_api_key`) and load them via environment variables.
- Core env vars: `DATABASE_URL` (runtime store), `GEMINI_API_KEY`/`GEMINI_MODEL` (LLM access), optional `SQL_ECHO` for verbose DB logging.
- Remove stray SQLite files after schema churn; regenerate with `make run-api-sqlite` if needed.

## Local Testing
- Run the smoke script: `bash tools/serve_and_run.sh snapshots/locations_demo.json "When is sunset in Paris?"`
- Summaries: `./tools/show_last_run.py` prints prompts, tool calls, execution log, final result.
- Logs: `logs/server.log` (rotating file) and `/tmp/arion_uvicorn.log` (detailed Uvicorn output).
