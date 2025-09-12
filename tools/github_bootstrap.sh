#!/usr/bin/env bash
set -euo pipefail

# Bootstrap GitHub labels, project, and initial issues for arion_agents.
# Requirements: GitHub CLI (gh) authenticated, repo set as default or pass --repo.

OWNER=""
REPO=""
PROJECT_TITLE="arion_agents Roadmap"

usage() {
  cat <<EOF
Usage: $0 --owner <github_owner> [--repo <owner/name>] [--no-project] [--dry-run]

Examples:
  $0 --owner qcenturion
  $0 --owner qcenturion --repo qcenturion/arion_agents
EOF
}

NO_PROJECT=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --owner) OWNER="$2"; shift 2 ;;
    --repo) REPO="$2"; shift 2 ;;
    --no-project) NO_PROJECT=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1"; usage; exit 1 ;;
  esac
done

if [[ -z "$OWNER" ]]; then
  echo "--owner is required" >&2; exit 1
fi

if [[ -z "$REPO" ]]; then
  # Try to infer default repo
  if gh repo view --json nameWithOwner >/dev/null 2>&1; then
    REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
  else
    REPO="${OWNER}/arion_agents"
  fi
fi

echo "Using repo: $REPO"

run() {
  echo "+ $*"
  if [[ "$DRY_RUN" == "false" ]]; then
    eval "$*"
  fi
}

echo "Creating labels..."
run "gh label create 'workstream:orchestrator' --color '#0E8A16' --description 'Orchestrator tasks' || true"
run "gh label create 'workstream:agents_llm' --color '#5319E7' --description 'Agents & LLM tasks' || true"
run "gh label create 'workstream:tools' --color '#1D76DB' --description 'Tools & integrations' || true"
run "gh label create 'workstream:api_config' --color '#0052CC' --description 'API & Config Store' || true"
run "gh label create 'workstream:observability' --color '#FBCA04' --description 'OTel/Jaeger/Prometheus/Grafana' || true"
run "gh label create 'workstream:frontend_ui' --color '#B60205' --description 'Control plane UI' || true"
run "gh label create 'workstream:devops_github' --color '#5319E7' --description 'CI/CD, repo hygiene' || true"
run "gh label create 'workstream:security' --color '#D93F0B' --description 'Security & compliance' || true"
run "gh label create 'type:task' --color '#C5DEF5' --description 'Concrete task' || true"
run "gh label create 'type:feature' --color '#84B6EB' --description 'Feature work' || true"
run "gh label create 'type:bug' --color '#EE0701' --description 'Bug' || true"
run "gh label create 'epic' --color '#0E8A16' --description 'Epic/large scope' || true"

PROJECT_NUMBER=""
if [[ "$NO_PROJECT" == "false" ]]; then
  echo "Ensuring project exists..."
  # Check if project exists
  EXIST=$(gh project list --owner "$OWNER" --limit 50 --format json --jq ".[] | select(.title == \"$PROJECT_TITLE\") | .number" || true)
  if [[ -z "$EXIST" ]]; then
    run "gh project create --owner '$OWNER' --title '$PROJECT_TITLE' --format"
    PROJECT_NUMBER=$(gh project list --owner "$OWNER" --limit 50 --format json --jq ".[] | select(.title == \"$PROJECT_TITLE\") | .number")
  else
    PROJECT_NUMBER="$EXIST"
  fi
  echo "Project number: $PROJECT_NUMBER"
fi

echo "Creating seed issues..."
issue() {
  local title="$1" body="$2" labels="$3"
  run "gh issue create --repo '$REPO' -t '$title' -b '$body' -l '$labels'"
}

issue "API/Config: init Alembic and SQLAlchemy models" \
      "Define agents/tools/routes models and baseline migration. Acceptance: models created, alembic revision generated, tests for model creation." \
      "workstream:api_config,type:task"
issue "API/Config: CRUD endpoints for /config/*" \
      "Implement CRUD for agents, tools, and route associations with validation. Acceptance: endpoints tested via pytest." \
      "workstream:api_config,type:feature"
issue "Orchestrator: enforce equipped_tools and allowed_routes" \
      "Validate requested actions against agent config; block and log disallowed operations." \
      "workstream:orchestrator,type:task"
issue "Orchestrator: system-provided parameter injection" \
      "Inject secure params (e.g., customer_id) from state; prevent LLM-provided overrides." \
      "workstream:orchestrator,type:task"
issue "Orchestrator: run_id and EventPublisher interface" \
      "Define run_id and publish per-step events; add in-memory publisher." \
      "workstream:orchestrator,type:feature"
issue "API: SSE endpoint /runs/{run_id}/events" \
      "Serve real-time execution events for UI via Server-Sent Events (SSE)." \
      "workstream:api_config,type:feature"
issue "Observability: docker-compose for OTel Collector + Jaeger + Prometheus + Grafana" \
      "Local stack to receive and visualize traces/metrics." \
      "workstream:observability,type:feature"
issue "Frontend: scaffold SPA shell and config views" \
      "Create initial SPA with routing and placeholder pages for agents/tools/routes." \
      "workstream:frontend_ui,type:feature"
issue "Frontend: run trigger and live log view" \
      "Add input form to trigger /invoke and subscribe to /runs/{run_id}/events." \
      "workstream:frontend_ui,type:feature"
issue "DevOps: add pre-commit hooks (ruff/black optional)" \
      "Pre-commit setup and CI verification." \
      "workstream:devops_github,type:task"
issue "Security: secrets handling and redaction utilities" \
      "Document .env usage, add helpers to redact sensitive data in logs/traces." \
      "workstream:security,type:task"
issue "Deployment: Dockerfile and Cloud Run deployment" \
      "Containerize API, push to Artifact Registry, and deploy to Cloud Run from CI." \
      "workstream:devops_github,type:feature,epic"

echo "Done. Optionally add issues to project $PROJECT_TITLE in the UI or via: gh project item-add --owner '$OWNER' --project '$PROJECT_NUMBER' --url <issue_url>"

