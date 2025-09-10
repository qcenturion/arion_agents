# Workstream: Agents & LLM

## Goals
- Agents output a single, schema-conforming Instruction
- Provider-agnostic LLM integration with retries/timeouts
- Dynamic prompt assembly from config (tools/routes)
- Safe templating and response validation (e.g., Instructor)

## Decisions
- Initial provider: TBD (OpenAI/Azure/Anthropic)
- JSON schema enforcement: Instructor or pydantic-based structured output
- Prompt format: system + context + capabilities + state summary + request

## Milestones & Tasks
- M1: Single provider + schema
  - [ ] Choose provider and models
  - [ ] Implement prompt template for POC agents
  - [ ] Enforce structured output (raise on invalid)
  - [ ] Retries/backoff, timeouts
- M2: Multi-provider abstraction
  - [ ] Provider client interface
  - [ ] OpenAI + one alternative adapter
  - [ ] Telemetry on tokens/cost/latency
- M3: Context/memory hooks
  - [ ] State summarization function for long contexts
  - [ ] RAG integration (see configuration)

## Acceptance Criteria
- Invalid LLM outputs are rejected and retried
- Capabilities in prompt reflect current config
- Telemetry surfaces latency/cost per step

## Configuration
- `LLM_PROVIDER` and API keys via `.env`
- Model names per provider (e.g., `OPENAI_MODEL`)
- RAG store choice and connection (optional for POC)
