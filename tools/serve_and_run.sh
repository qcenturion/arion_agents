#!/usr/bin/env bash
set -euo pipefail

# One-shot helper: boot the API, invoke /run once, print logs, and exit.
#
# Usage:
#   bash arion_agents/tools/serve_and_run.sh <snapshot_path_or_name> "<user_message>" [options]
#
# Options:
#   --network NAME    Use a published network instead of inline snapshot (requires Postgres)
#   --use-db          Same as --network but keeps legacy flag for clarity
#   --username NAME   GeoNames username (default: carlemueller89)
#   --host HOST       API host (default: 127.0.0.1)
#   --port PORT       API port (default: 8000)
#   --keep            Do not stop the server after the request
#
# Examples:
#   bash arion_agents/tools/serve_and_run.sh locations_demo "When is sunset in Paris?"
#   bash arion_agents/tools/serve_and_run.sh snapshots/locations_demo.json "When is sunset?" --keep
#   bash arion_agents/tools/serve_and_run.sh locations_demo "Ping network" --network locations_demo

if [ ${#} -lt 2 ]; then
  echo "Usage: $0 <snapshot_path_or_name> \"<user_message>\" [options]" 1>&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SNAP_ARG="$1"; shift
USER_MESSAGE="$1"; shift

NETWORK="locations_demo"
GEO_USER="carlemueller89"
HOST="127.0.0.1"
PORT="8000"
KEEP=0
USE_DB=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --network)
      NETWORK="$2"; USE_DB=1; shift 2;;
    --use-db)
      USE_DB=1; shift;;
    --username)
      GEO_USER="$2"; shift 2;;
    --host)
      HOST="$2"; shift 2;;
    --port)
      PORT="$2"; shift 2;;
    --keep)
      KEEP=1; shift;;
    *)
      echo "Unknown option: $1" 1>&2; exit 2;;
  esac
done

SNAP_PATH=""
if [ "$USE_DB" -eq 0 ]; then
  SNAP_PATH="$SNAP_ARG"
  if [ ! -f "$SNAP_PATH" ]; then
    if [ -f "$REPO_ROOT/snapshots/${SNAP_PATH}.json" ]; then
      SNAP_PATH="$REPO_ROOT/snapshots/${SNAP_PATH}.json"
    fi
  fi
  if [ ! -f "$SNAP_PATH" ]; then
    echo "Snapshot not found: $SNAP_ARG (resolved: $SNAP_PATH)" 1>&2
    exit 3
  fi
  echo "Using snapshot: $SNAP_PATH"
else
  if [ "$NETWORK" = "locations_demo" ] || [ -z "$NETWORK" ]; then
    NETWORK="$SNAP_ARG"
  fi
  echo "Using published network: $NETWORK"
fi

# Check interpreter
PYBIN="$REPO_ROOT/.venv/bin/python"
if [ ! -x "$PYBIN" ]; then
  PYBIN="$(command -v python3 || command -v python)"
fi
if [ -z "$PYBIN" ]; then
  echo "No python interpreter found" 1>&2
  exit 4
fi

echo "Python: $PYBIN"
echo "Host: $HOST  Port: $PORT"

# Kill any existing instance of this app
pkill -f 'uvicorn arion_agents.api:app' 2>/dev/null || true
sleep 0.5

export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export LOG_LEVEL=${LOG_LEVEL:-DEBUG}
export UVICORN_LOG_LEVEL=${UVICORN_LOG_LEVEL:-debug}

if [ -z "${GEMINI_API_KEY:-}" ]; then
  echo "WARNING: GEMINI_API_KEY not set. /run will fail when the model is called." 1>&2
fi

LOGFILE="/tmp/arion_uvicorn.log"
PIDFILE="/tmp/arion_uvicorn.pid"

echo "Starting server..."
nohup "$PYBIN" -m uvicorn arion_agents.api:app --host "$HOST" --port "$PORT" --log-level debug >"$LOGFILE" 2>&1 & echo $! >"$PIDFILE"
sleep 0.5

PID="$(cat "$PIDFILE" 2>/dev/null || true)"
if [ -z "$PID" ] || ! ps -p "$PID" >/dev/null 2>&1; then
  echo "Server failed to start. Log:" 1>&2
  sed -n '1,200p' "$LOGFILE" 1>&2 || true
  exit 5
fi

echo -n "Waiting for health"
for _ in $(seq 1 60); do
  if curl -fsS "http://$HOST:$PORT/health" >/dev/null; then
    echo " - OK"; break
  fi
  echo -n "."; sleep 0.25
done
if ! curl -fsS "http://$HOST:$PORT/health" >/dev/null; then
  echo "\nHealth check failed. Log head:" 1>&2
  sed -n '1,120p' "$LOGFILE" 1>&2 || true
  exit 6
fi

# Build payload
if [ "$USE_DB" -eq 1 ]; then
  REQ_PAYLOAD=$(jq -n --arg net "$NETWORK" --arg msg "$USER_MESSAGE" --arg user "$GEO_USER" '{network:$net, user_message:$msg, system_params:{username:$user}, debug:true}')
else
  REQ_PAYLOAD=$(jq -n --arg msg "$USER_MESSAGE" --arg user "$GEO_USER" --slurpfile snap "$SNAP_PATH" '{snapshot:$snap[0], user_message:$msg, system_params:{username:$user}, debug:true}')
fi

echo "Running /run with message: $USER_MESSAGE"
curl -sS -X POST "http://$HOST:$PORT/run" -H 'content-type: application/json' -d "$REQ_PAYLOAD" | jq -C '.' || true

if [ -f "$REPO_ROOT/logs/server.log" ]; then
  echo "--- server.log tail ---"
  tail -n 120 "$REPO_ROOT/logs/server.log" || true
fi

if [ "$KEEP" -eq 0 ]; then
  echo "Stopping server (pid $PID)"
  kill "$PID" 2>/dev/null || true
  sleep 0.5
  if ps -p "$PID" >/dev/null 2>&1; then
    kill -9 "$PID" 2>/dev/null || true
  fi
fi

echo "Done. Logs at $LOGFILE"
