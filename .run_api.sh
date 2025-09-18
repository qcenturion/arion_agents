#!/usr/bin/env bash
set -euo pipefail
mkdir -p logs
export PYTHONPATH=src
export LOG_LEVEL=DEBUG
export OTEL_ENABLED=false
# ARION_RUN_LOG_JSON_PATH inherited from parent if set
.venv/bin/python -m uvicorn arion_agents.api:app --host 127.0.0.1 --port 8000 --log-level debug >> logs/server.log 2>&1 &
PID=$!
echo $PID > logs/server.pid
