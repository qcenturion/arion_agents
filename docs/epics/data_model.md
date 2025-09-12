# Data Model and Runtime Snapshot

## Overview
Relational edit-time model in Postgres with a compiled, read-optimized JSONB snapshot per published version. Designed for infrequent topology edits and high-confidence runtime behavior.

## Entities (Edit-Time, Relational)
- Network
  - id (PK), name (unique), description, status (draft/published/archived), current_version_id (FK)
- Agent
  - id (PK), network_id (FK), key (slug, unique per network), display_name, description, allow_respond (bool), metadata (JSONB)
  - Unique: (network_id, lower(key))
- Tool
  - id (PK), key (global unique), display_name, description, provider_type, params_schema (JSONB), secret_ref, metadata (JSONB)
  - Unique: lower(key)
- AgentTool
  - agent_id (FK), tool_id (FK)
  - Unique: (agent_id, tool_id)
- AgentRoute
  - from_agent_id (FK), to_agent_id (FK)
  - Unique: (from_agent_id, to_agent_id)
  - Check: from_agent_id != to_agent_id
- NetworkVersion
  - id (PK), network_id (FK), version (int), created_by, created_at, published_by, published_at, notes
  - Unique: (network_id, version)
- CompiledSnapshot
  - id (PK), network_version_id (FK, unique), checksum, compiled_graph (JSONB), created_at

## Compiled Snapshot (Runtime, JSONB)
- agents: [{ key, allow_respond, equipped_tools: [tool_key], allowed_routes: [agent_key], metadata }]
- tools: [{ key, description, params: [{ name, source: agent|system|default, required, default_value, schema }] }]
- adjacency: [{ from: agent_key, to: agent_key }]
- policy: runtime limits, retry/backoff, max steps
- validation: precomputed maps (e.g., allowed tools per agent) for fast checks

## Runtime Invocation
- /invoke loads compiled snapshot for the requested network/version (or current_version).
- Orchestrator enforces:
  - RESPOND allowed only if agent.allow_respond.
  - USE_TOOL only if tool in equipped_tools; agent params validated; system params injected; defaults applied.
  - ROUTE_TO_AGENT only if target in allowed_routes.
- Emits domain events (for UI) and OTel spans.

## Why Postgres + JSONB
- Strong constraints and transactional edits for quality.
- JSONB snapshot removes N-join hot paths and yields versioned, portable runtime artifacts.
- Easy local-prod parity and CI/CD with migrations.

## Alternatives Considered
- Graph DB (Neo4j): powerful queries but heavier ops; overkill for CRUD + adjacency validation.
- NoSQL document store: flexible, but weak relational integrity for edit-time operations; better as a secondary for run logs if needed.

## Open Questions
- Tenancy/env: Do we scope networks by tenant and/or environment?
- Tool overrides: Are tools global-only or can networks alias/override param schemas?
- Cycles: Allowed in routes? Enforce a max steps policy at runtime?
- Run persistence: Store runs/steps in DB or rely on OTel only?
- Scale: Approx agents/tools/routes per network and QPS?
