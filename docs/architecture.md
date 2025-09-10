# Architecture Overview

This document outlines the system architecture at a high level. It will evolve as features are added.

## System Context
- External services: LLM providers, vector DB / memory store, GitHub, observability.
- Interfaces: CLI, (future) HTTP API, and tool integrations.

## Core Components
- Agent Core: policy loop, tool routing, error handling.
- LLM Integration: providers, retry/backoff, prompt templates.
- Memory & State: short-term context, long-term storage, traces.
- Tools & Integrations: external APIs, file I/O, search.
- Interfaces: CLI now; API/SDK later.

## Cross-Cutting Concerns
- Config & Secrets management
- Logging/Tracing/Telemetry
- Evaluation & Testing strategy
- Security & Compliance considerations

## Open Questions / Decisions
- Which providers and SDKs to prioritize?
- Standard memory interface and backing store?
- Tracing/eval stack choices (e.g., TruLens, DeepEval, promptfoo)?
