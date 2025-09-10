# Workstream: Security & Compliance

## Goals
- Principle of least privilege across tools and routes
- Secret management and secure parameter injection
- Auditing and redaction in traces/logs

## Decisions
- Secret loading from env for POC; vault later (e.g., AWS/GCP/Azure)
- Redaction policy for PII in spans/events

## Milestones & Tasks
- M1: Basics
  - [ ] `.env` handling and secret loading
  - [ ] System-provided params injected by orchestrator only
  - [ ] Unit tests verifying blocks on unauthorized tools/routes
- M2: Hardening
  - [ ] Input validation and schema limits
  - [ ] Output redaction utilities
  - [ ] Threat model for tool misuse
