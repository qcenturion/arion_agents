PY?=python3
VENV?=.venv
PIP?=$(VENV)/bin/pip
PYTHON?=$(VENV)/bin/python
RUFF?=$(VENV)/bin/ruff

.PHONY: venv install lint format run-api run-api-sqlite dev clean db-up db-down db-logs db-init seed-location seed-sun snapshot-sun run-message compose-build compose-up compose-down compose-logs

venv:
	$(PY) -m venv $(VENV)

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

lint:
	$(RUFF) check src

format:
	$(RUFF) format src

run-api:
	PYTHONPATH=src $(PYTHON) -m arion_agents api

run-api-sqlite:
	DATABASE_URL=${DATABASE_URL:-sqlite+pysqlite:///./dev.db} PYTHONPATH=src $(PYTHON) -c "from arion_agents.db import init_db; init_db(); print('SQLite DB initialized at dev.db')"
	DATABASE_URL=${DATABASE_URL:-sqlite+pysqlite:///./dev.db} PYTHONPATH=src $(PYTHON) -m arion_agents api

dev:
	UVICORN_RELOAD=1 LOG_LEVEL=DEBUG UVICORN_LOG_LEVEL=debug UVICORN_ACCESS_LOG=true \
	PYTHONPATH=src $(PYTHON) -m arion_agents api

clean:
	rm -rf $(VENV) .ruff_cache

# --- Local Postgres (Docker) ---
DB_URL?=postgresql+psycopg://postgres:postgres@localhost:5432/arion_agents

db-up:
	docker-compose up -d db

db-down:
	docker-compose down

db-logs:
	docker-compose logs -f db

db-init:
	DATABASE_URL=$(DB_URL) PYTHONPATH=src $(PYTHON) -c "from arion_agents.db import init_db; init_db(); print('DB initialized')"

seed-sun:
	API_URL?=http://localhost:8000
	API_URL=$(API_URL) $(PYTHON) tools/seed_sun_demo.py

seed-location:
	API_URL?=http://localhost:8000
	API_URL=$(API_URL) $(PYTHON) tools/seed_location_demo.py

snapshot-sun:
	$(PYTHON) tools/make_sun_snapshot.py tools/sun_snapshot.json

# Run one message via local API and print final + execution_log
# Usage: make run-message NET=locations_demo MSG="..." SYS='{"username":"demo"}' DEBUG=1 API_URL=http://localhost:8000
run-message:
	API_URL?=http://localhost:8000
	@if [ -z "$(NET)" ]; then echo "NET is required (e.g., NET=locations_demo)"; exit 2; fi
	@if [ -z "$(MSG)" ]; then echo "MSG is required (e.g., MSG=\"Hello\")"; exit 2; fi
	@if [ -n "$(SYS)" ]; then SYS_ARG=--system '$(SYS)'; else SYS_ARG=; fi; \
	API_URL=$(API_URL) PYTHONPATH=src $(PYTHON) tools/run_message.py --network '$(NET)' --message '$(MSG)' $$SYS_ARG $(if $(DEBUG),--debug,)

compose-build:
	docker-compose build

compose-up:
	docker-compose up -d

compose-down:
	docker-compose down

compose-logs:
	docker-compose logs -f api db
rag-demo:
	@echo "Indexing sample corpus in the RAG service..."
	PYTHONPATH=src .venv/bin/python tools/rag_index.py tools/rag_service/city_activities.md --service-url http://localhost:7100 --collection city_activities
	@echo "Setting up locations_demo with city_rag tool..."
	PYTHONPATH=src .venv/bin/python tools/setup_rag_network.py
	@echo "Smoke testing via serve_and_run..."
	bash tools/serve_and_run.sh locations_demo "What should I do in London?" --network locations_demo
	@echo "Done."
