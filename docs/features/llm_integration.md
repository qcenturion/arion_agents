# Feature: LLM Integration

## Summary
Provider-agnostic LLM clients with retries, timeouts, and templating.
Initial provider: Google Gemini via `google-genai` with optional fallback to `google-generativeai`.

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
- M1: Gemini client with disabled-thinking config, test endpoint, retries
- M2: Prompt templates + guardrails
- M3: Multi-provider switching (per-network/per-agent model selection)

## Notes
- Default model: `gemini-2.5-flash` (override with `GEMINI_MODEL` per env).
- API key resolution order: `GEMINI_API_KEY` env var, then `.secrets/gemini_api_key`.
- Thinking is disabled by default using `ThinkingConfig(thinking_budget=0)`.
