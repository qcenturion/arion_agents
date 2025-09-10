# Workstream: Tools & Integrations

## Goals
- Deterministic tool interfaces with validation
- Permissions enforced via config (equipped_tools)
- Support for system-provided parameters (secure injection)

## Decisions
- Tool interface: sync for POC, async later if needed
- Registry: discoverable via entrypoints or explicit registration

## Milestones & Tasks
- M1: Registry + sample tools
  - [ ] Tool base class + type hints (#issue)
  - [ ] Example: TemplateRetrievalTool (#issue)
  - [ ] Example: TransactionValidationTool (mock impl) (#issue)
- M2: Permissions & policy
  - [ ] Enforce allowed tools per agent (#issue)
  - [ ] Parameter policies (agent_provided vs system_provided) (#issue)
- M3: Production readiness
  - [ ] Timeouts, retries, circuit breakers as needed (#issue)
  - [ ] Tracing + input/output redaction options (#issue)

## Acceptance Criteria
- Tools cannot be invoked if not permitted
- System-provided params never come from LLM output
- Traces include tool spans with statuses
