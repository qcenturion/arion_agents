PY?=python3
VENV?=.venv
PIP?=$(VENV)/bin/pip
PYTHON?=$(VENV)/bin/python
PYTEST?=$(VENV)/bin/pytest
RUFF?=$(VENV)/bin/ruff

.PHONY: venv install test lint format run-api clean

venv:
	$(PY) -m venv $(VENV)

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

test:
	$(PYTEST) -q

lint:
	$(RUFF) check src tests

format:
	$(RUFF) format src tests

run-api:
	PYTHONPATH=src $(PYTHON) -m arion_agents api

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache

# --- Local Postgres (Docker) ---
.PHONY: db-up db-down db-logs db-migrate test-int

DB_URL?=postgresql+psycopg://postgres:postgres@localhost:5432/arion_agents

db-up:
	docker compose up -d db

db-down:
	docker compose down

db-logs:
	docker compose logs -f db

db-migrate:
	DATABASE_URL=$(DB_URL) alembic -c alembic.ini upgrade head

test-int:
	DATABASE_URL=$(DB_URL) pytest -q tests_int
