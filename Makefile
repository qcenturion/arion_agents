PY?=python3
VENV?=.venv
PIP?=$(VENV)/bin/pip
PYTHON?=$(VENV)/bin/python
PYTEST?=$(VENV)/bin/pytest
RUFF?=$(VENV)/bin/ruff

.PHONY: venv install test lint format run-api clean db-up db-down db-logs db-init seed-demo seed-time compose-build compose-up compose-down compose-logs e2e-local e2e-local-llm

venv:
	$(PY) -m venv $(VENV)

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

test:
	DATABASE_URL=${DATABASE_URL:-postgresql+psycopg://postgres:postgres@localhost:5432/arion_agents} PYTHONPATH=src $(PYTEST) -q

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
	docker-compose up -d db

db-down:
	docker-compose down

db-logs:
	docker-compose logs -f db

db-init:
	DATABASE_URL=$(DB_URL) PYTHONPATH=src $(PYTHON) -c "from arion_agents.db import init_db; init_db(); print('DB initialized')"



seed-demo:
	API_URL?=http://localhost:8000
	API_URL=$(API_URL) $(PYTHON) tools/seed_demo.py

seed-time:
	API_URL?=http://localhost:8000
	API_URL=$(API_URL) $(PYTHON) tools/seed_time_demo.py

e2e-local:
	DATABASE_URL=sqlite:///./e2e.db PYTHONPATH=src $(PYTHON) tools/e2e_local.py

e2e-local-llm:
	USE_LLM=1 DATABASE_URL=sqlite:///./e2e.db PYTHONPATH=src $(PYTHON) tools/e2e_local.py

snapshot-sun:
	$(PYTHON) tools/make_sun_snapshot.py tools/sun_snapshot.json

e2e-snapshot:
	SNAPSHOT_FILE=tools/sun_snapshot.json PYTHONPATH=src $(PYTHON) - << 'PY'
	from fastapi.testclient import TestClient
	import json
	from arion_agents.api import app

	c = TestClient(app)
	out = c.post('/run', json={
	  'network':'unused',
	  'user_message':'When does the sun rise and set for lat 36.7201600 and lng -4.4203400?',
	  'debug': True
	}).json()
	print(json.dumps(out, indent=2))
	PY

compose-build:
	docker-compose build

compose-up:
	docker-compose up -d

compose-down:
	docker-compose down

compose-logs:
	docker-compose logs -f api db
