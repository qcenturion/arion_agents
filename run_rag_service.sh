#!/bin/bash
set -e

# This script provides a reliable way to start the RAG service with all necessary environment variables.

echo "--- Starting Arion Agents RAG Service ---"

# Get the absolute path to the project root directory (the parent of this script's directory)
PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
echo "Project Root: $PROJECT_ROOT"

# Define paths for the virtual environment and data directories
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
MODEL_CACHE_PATH="$PROJECT_ROOT/.model_cache"
QDRANT_DATA_PATH="$PROJECT_ROOT/.qdrant_data"

# Check if the virtual environment exists
if [ ! -f "$VENV_PYTHON" ]; then
    echo "ERROR: Python virtual environment not found at $VENV_PYTHON"
    echo "Please run 'make install' to create it before running this script."
    exit 1
fi

# Set the environment variables required by the service
export HF_HOME="$MODEL_CACHE_PATH"
export RAG_QDRANT_PATH="$QDRANT_DATA_PATH"
export PYTHONPATH="$PROJECT_ROOT/src"

echo "Environment:"
echo "  - HF_HOME (model cache): $HF_HOME"
echo "  - RAG_QDRANT_PATH (vector db): $RAG_QDRANT_PATH"
echo "  - PYTHONPATH: $PYTHONPATH"
echo "-------------------------------------------"

# Execute the service using uvicorn, pointing it to the app object
"$VENV_PYTHON" -m uvicorn tools.rag_service.service:app --host 0.0.0.0 --port 7100
