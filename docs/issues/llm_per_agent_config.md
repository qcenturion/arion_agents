Title: LLM configuration per agent/network with Gemini + multi-provider support

Labels: workstream:agents_llm, type:feature

Context
- We now have a working Gemini integration with disabled thinking and a test endpoint.
- Next, allow selecting model/provider per network and per agent, with sane defaults.

Scope
- Add DB config to store LLM provider + model at network and agent levels, with override rules (agent > network > global default).
- Extend compiled snapshot to include resolved LLM settings per agent.
- Wire orchestrator to use the resolved agent-specific LLM config when requesting structured outputs.
- Support Gemini first; leave hooks for OpenAI/Anthropic/Mistral/Groq.

Acceptance Criteria
- API: Endpoints to set/get LLM config for network and agent.
- Snapshot: published artifact contains LLM settings per agent.
- Runtime: Pydantic AI agent selection uses the settings to instantiate the correct model + disabled thinking by default.
- Docs: README + START_HERE updated with examples.
- Tests: unit tests for config resolution and a smoke test using the draft-instruction endpoint.

Out of Scope
- Cost tracking and rate limiting (follow-up issue).

Notes
- Default thinking: disabled via `thinking_budget=0`; allow opt-in at agent level.
- Key management: continue using `.secrets/` for local dev; don’t store keys in DB.

