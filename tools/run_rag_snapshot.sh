#!/usr/bin/env bash
set -euo pipefail

# Quick smoke test using an inline snapshot and running RAG service.
# Usage: tools/run_rag_snapshot.sh "What should I do in London?"

MSG=${1:-"What should I do in London?"}
SNAPSHOT=${SNAPSHOT:-snapshots/locations_rag_demo.json}
SERVICE_URL=${SERVICE_URL:-http://localhost:7100}
COLLECTION=${COLLECTION:-city_activities}
CORPUS=${CORPUS:-tools/rag_service/city_activities.md}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ ! -f "$REPO_ROOT/$SNAPSHOT" ]; then
  echo "Snapshot not found at $SNAPSHOT" >&2
  exit 1
fi

if ! curl -sf "$SERVICE_URL/health" >/dev/null; then
  echo "RAG service not reachable at $SERVICE_URL" >&2
  exit 2
fi

source "$REPO_ROOT/.venv/bin/activate"
python "$REPO_ROOT/tools/rag_index.py" "$REPO_ROOT/$CORPUS" \
  --service-url "$SERVICE_URL" \
  --collection "$COLLECTION"

echo "Running serve_and_run with inline snapshot..."
bash "$REPO_ROOT/tools/serve_and_run.sh" "$SNAPSHOT" "$MSG"
