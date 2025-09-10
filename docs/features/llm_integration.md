# Feature: LLM Integration

## Summary
Provider-agnostic LLM clients with retries, timeouts, and templating.

## User Stories
- As a developer, I can switch providers via config.
- As a user, responses are reliable and fast.

## Functional Requirements
- Provider interfaces and adapters (OpenAI, Azure, etc.)
- Prompt templating, variables, and guards
- Rate limit handling and exponential backoff

## Non-Functional Requirements
- Testability with offline stubs/mocks
- Observability of cost/latency/quality

## Milestones
- M1: Single provider with retries
- M2: Prompt templates + guardrails
- M3: Multi-provider switching
