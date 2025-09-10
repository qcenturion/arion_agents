# Workstreams Overview

This folder tracks the major workstreams needed to deliver the arion_agents framework from POC to production-readiness. Each workstream doc contains:
- Goals and scope
- Decisions and open questions
- Milestones and task list (with acceptance criteria)
- Configuration and dependencies

Workstreams:
- orchestrator.md — deterministic executor, instruction validation, state
- agents_llm.md — agent design, schema-constrained outputs, providers
- tools.md — tool registry, permissions, system-provided params
- api_and_config_store.md — FastAPI service, config DB, migrations
- observability.md — OpenTelemetry, collector, Jaeger, Prometheus, Grafana
- frontend_ui.md — SPA for config + trace visualization
- devops_github.md — repo setup, CI, Docker, GitHub integration
- security.md — secret management, least privilege, auditing

Tracking approach:
- For now: task lists in these docs for clarity.
- Option: mirror as GitHub Issues with labels per workstream and a GitHub Project board once the repo is on GitHub.
