# Seed Issues (copy-paste commands)

Prereqs:
- Install GitHub CLI and login: `brew install gh && gh auth login`
- Set default repo: `gh repo set-default qcenturion/arion_agents`

Labels:
```
gh label create 'workstream:orchestrator' --color '#0E8A16' --description 'Orchestrator tasks'
gh label create 'workstream:agents_llm' --color '#5319E7' --description 'Agents & LLM tasks'
gh label create 'workstream:tools' --color '#1D76DB' --description 'Tools & integrations'
gh label create 'workstream:api_config' --color '#0052CC' --description 'API & Config Store'
gh label create 'workstream:observability' --color '#FBCA04' --description 'OTel/Jaeger/Prometheus/Grafana'
gh label create 'workstream:frontend_ui' --color '#B60205' --description 'Control plane UI'
gh label create 'workstream:devops_github' --color '#5319E7' --description 'CI/CD, repo hygiene'
gh label create 'workstream:security' --color '#D93F0B' --description 'Security & compliance'
gh label create 'type:task' --color '#C5DEF5' --description 'Concrete task'
gh label create 'type:feature' --color '#84B6EB' --description 'Feature work'
gh label create 'type:bug' --color '#EE0701' --description 'Bug'
gh label create 'epic' --color '#0E8A16' --description 'Epic/large scope'
```

Project Board (optional):
```
gh project create --owner qcenturion --title "arion_agents Roadmap"
```

Seed Issues:
```
gh issue create -t "API/Config: init Alembic and SQLAlchemy models" -b "Define agents/tools/routes models and baseline migration. Acceptance: models created, alembic revision generated, tests for model creation." -l "workstream:api_config,type:task"
gh issue create -t "API/Config: CRUD endpoints for /config/*" -b "Implement CRUD for agents, tools, and route associations with validation. Acceptance: endpoints tested via pytest." -l "workstream:api_config,type:feature"
gh issue create -t "Orchestrator: enforce equipped_tools and allowed_routes" -b "Validate requested actions against agent config; block and log disallowed operations." -l "workstream:orchestrator,type:task"
gh issue create -t "Orchestrator: system-provided parameter injection" -b "Inject secure params (e.g., customer_id) from state; prevent LLM-provided overrides." -l "workstream:orchestrator,type:task"
gh issue create -t "Orchestrator: run_id and EventPublisher interface" -b "Define run_id and publish per-step events; add in-memory publisher." -l "workstream:orchestrator,type:feature"
gh issue create -t "API: SSE endpoint /runs/{run_id}/events" -b "Serve real-time execution events for UI via Server-Sent Events (SSE)." -l "workstream:api_config,type:feature"
gh issue create -t "Observability: docker-compose for OTel Collector + Jaeger + Prometheus + Grafana" -b "Local stack to receive and visualize traces/metrics." -l "workstream:observability,type:feature"
gh issue create -t "Frontend: scaffold SPA shell and config views" -b "Create initial SPA with routing and placeholder pages for agents/tools/routes." -l "workstream:frontend_ui,type:feature"
gh issue create -t "Frontend: run trigger and live log view" -b "Add input form to trigger /invoke and subscribe to /runs/{run_id}/events." -l "workstream:frontend_ui,type:feature"
gh issue create -t "DevOps: add pre-commit hooks (ruff/black optional)" -b "Pre-commit setup and CI verification." -l "workstream:devops_github,type:task"
gh issue create -t "Security: secrets handling and redaction utilities" -b "Document .env usage, add helpers to redact sensitive data in logs/traces." -l "workstream:security,type:task"
gh issue create -t "Deployment: Dockerfile and Cloud Run deployment" -b "Containerize API, push to Artifact Registry, and deploy to Cloud Run from CI." -l "workstream:devops_github,type:feature,epic"
```

