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
	$(PYTHON) -m arion_agents api

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache
