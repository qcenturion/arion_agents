# Feature: Interfaces (API and CLI)

## Summary
Command-line interface now; optional HTTP API later.

## User Stories
- As a developer, I can run the agent via CLI.
- As a platform owner, I can host an HTTP API.

## Functional Requirements
- CLI entry (`python -m arion_agents`)
- Config management via env/args
- (Later) HTTP API with minimal routes

## Non-Functional Requirements
- Clear UX and error messages
- Secure defaults for API

## Milestones
- M1: CLI entry and help
- M2: Config handling
- M3: Basic API skeleton
