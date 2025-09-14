PY?=python3
VENV?=.venv
PIP?=$(VENV)/bin/pip
PYTHON?=$(VENV)/bin/python
PYTEST?=$(VENV)/bin/pytest
RUFF?=$(VENV)/bin/ruff

.PHONY: venv install test lint format run-api clean db-up db-down db-logs db-init seed-demo

venv:
	$(PY) -m venv $(VENV)

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

test:
	PYTHONPATH=src DATABASE_URL?=postgresql+psycopg://postgres:postgres@localhost:5432/arion_agents $(PYTEST) -q

lint:
	$(RUFF) check src tests

format:
	$(RUFF) format src tests

run-api:
	PYTHONPATH=src $(PYTHON) -m arion_agents api

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache

# --- Local Postgres (Docker) ---
DB_URL?=postgresql+psycopg://postgres:postgres@localhost:5432/arion_agents

db-up:
	docker compose up -d db

db-down:
	docker compose down

db-logs:
	docker compose logs -f db

db-init:
	DATABASE_URL=$(DB_URL) PYTHONPATH=src $(PYTHON) -c "from arion_agents.db import init_db; init_db(); print('DB initialized')"

seed-demo:
	API_URL?=http://localhost:8000
	API_URL=$(API_URL) $(PYTHON) tools/seed_demo.py

seed-time:
	API_URL?=http://localhost:8000
	API_URL=$(API_URL) $(PYTHON) tools/seed_time_demo.py
