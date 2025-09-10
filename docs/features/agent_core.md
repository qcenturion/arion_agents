# Feature: Agent Core

## Summary
Core control loop, planning, tool selection, error handling, and retries.

## User Stories
- As a developer, I can define agent goals and constraints.
- As a user, I get robust behavior with graceful recovery.

## Functional Requirements
- Deterministic control loop with configurable policies
- Tool selection strategy (rules/heuristics/LLM)
- Structured error handling and retry policies

## Non-Functional Requirements
- Observability: logs + traces
- Extensibility: easy to add new tools/policies

## Milestones
- M1: Minimal loop with a single tool
- M2: Policy abstractions + retries
- M3: Observability hooks
