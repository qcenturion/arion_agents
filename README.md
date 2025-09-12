# arion_agents

A Python project scaffold for building LLM-powered agents. This repo uses a modern `src/` layout, `pytest` for testing, and a lightweight documentation structure to guide architecture and feature planning.

## Quickstart

- Python: verified locally (see below)
- Activate existing venv: `cd arion_agents && source .venv/bin/activate`
- Install/Update deps: `pip install -r requirements.txt`
- Run unit tests (SQLite): `pytest`
- Run API: `make run-api`

## Local Venv (Project-Scoped)

This repo includes a ready-to-use virtualenv at `arion_agents/.venv` to keep tools and versions consistent.

- Activate: `source .venv/bin/activate`
- Python: 3.12.8 (from the venv)
- Install/Update deps: `pip install -r requirements.txt`
- Run tests from repo root of `arion_agents/`: `pytest -q`
- Start API from `arion_agents/`: `PYTHONPATH=src python -m arion_agents api` or `make run-api`

Verify the baked-in venv
- Check Python version: `./.venv/bin/python -V` (expected: `Python 3.12.8`)
- Check pip: `./.venv/bin/pip -V`
- Confirm path: `./.venv/bin/python -c 'import sys; print(sys.executable)'`

Notes
- Tests and the API expect the package path `src/` to be on `PYTHONPATH`. The `Makefile` handles this for API runs; for ad‑hoc runs use `PYTHONPATH=src`.
- If you see import errors while running from the monorepo root, `cd arion_agents` first so relative paths match the expected layout.

Tip: Avoid creating a new venv. Use the bundled venv above for consistent local runs unless you intentionally need to recreate it.

## Open Next

- Start here for context and next steps: `docs/START_HERE.md`
- Local development guide (DB, migrations, API): `docs/LOCAL_DEV.md`

## Local Postgres (required for API & tests)

Use Docker for local DB.

- Start DB: `make db-up`
- Initialize schema (no Alembic yet): `make db-init` (uses `DB_URL`, default: `postgresql+psycopg://postgres:postgres@localhost:5432/arion_agents`)
- Tail logs: `make db-logs`
- Stop DB: `make db-down`

Set `DATABASE_URL` if you want a non-default URL.

Created tables after migrations
- Runtime (placeholder): `agents`, `tools`, `agent_tools`, `agent_routes`
- Config (edit-time): `cfg_networks`, `cfg_agents`, `cfg_tools`, `cfg_agent_tools`, `cfg_agent_routes`, `cfg_network_versions`, `cfg_compiled_snapshots`

Override the DB URL
- Example: `make db-migrate DB_URL=postgresql+psycopg://user:pass@localhost:5432/yourdb`

## Layout

```
arion_agents/
├── src/
│   └── arion_agents/
│       ├── __init__.py
│       └── __main__.py
├── tests/
│   └── test_sanity.py
├── docs/
│   ├── overview.md            # Paste your project overview here
│   ├── architecture.md        # High-level architecture outline
│   └── features/
│       ├── agent_core.md
│       ├── llm_integration.md
│       ├── memory_and_state.md
│       ├── tools_and_integrations.md
│       └── interfaces_api_cli.md
├── requirements.txt
└── .gitignore
```

## Python version

This machine reports Python 3.12.8. If you need to support a different version, we can adjust the configuration and CI later.

## Next steps

- Create a network, add global tools, add those tools to a network, create agents, assign tools/routes, then compile+publish a snapshot via the config API. Finally use `/invoke` with `network` + `agent_key`.

Config API (high‑level)
- Global tools: `POST /config/tools` (key, params_schema), `GET /config/tools`
- Networks: `POST/GET /config/networks`
- Network tools: `POST/GET /config/networks/{network_id}/tools`
- Agents: `POST/GET /config/networks/{network_id}/agents`
- Assignments: `PUT /config/networks/{network_id}/agents/{agent_id}/tools|routes`
- Publish: `POST /config/networks/{network_id}/versions/compile_and_publish`

Invoke API
- `POST /invoke` with `{ network, agent_key, version?, instruction, system_params?, allow_respond? }`

## LLM (Gemini) Setup (Optional)
- Local secret file (preferred): put your key in `arion_agents/.secrets/gemini_api_key` (this path is git-ignored)
- Or set env var: `export GEMINI_API_KEY=$(cat .secrets/gemini_api_key)`
- Optional model: `export GEMINI_MODEL=gemini-1.5-flash`
- Test completion (API running):
  - `curl -sS -X POST :8000/llm/complete -H 'content-type: application/json' -d '{"prompt":"Say hello"}'`
  - Expected: JSON with a `text` field containing the model reply

Structured output (Pydantic AI)
- Draft an Instruction object from free text:
  - `curl -sS -X POST :8000/llm/draft-instruction -H 'content-type: application/json' -d '{"prompt":"Return a RESPOND instruction with payload {\"hello\":\"world\"} and reasoning \"done\""}'`
  - Returns: `{ "model": "...", "instruction": { ... } }`


## Project Overview
1. Project Vision & Goals
The primary objective is to create a robust, secure, and deeply observable framework for orchestrating specialized AI agents. This framework will manage complex, multi-step workflows by executing instructions from intelligent agents, leveraging industry-standard tools to provide unparalleled visibility into the reasoning and performance of every step. The framework is designed to be a general-purpose foundation for various agentic solutions.

2. Core Architectural Principles
Modularity & Separation of Concerns: The system's logic is strictly separated into a central Orchestrator (executor), reasoning Agents (decision-makers), and action-oriented Tools.

Security First: The Orchestrator enforces strict, configuration-based permissions and securely injects sensitive data (e.g., customer_id) into tool calls, preventing agents from accessing or manipulating unauthorized information.

Dynamic Configuration: Agent capabilities (equipped tools, allowed routes) are defined in an external configuration, not in code. This configuration is used at runtime to dynamically construct prompts, ensuring agents are always aware of their precise, current capabilities.

Structured & Validated Instruction: All communication from an agent to the Orchestrator must be in a structured, validated JSON format. This ensures reliable, predictable execution and eliminates ambiguity.

Standardized Observability: The system is fully instrumented using the OpenTelemetry standard to generate detailed traces, metrics, and logs. This ensures interoperability with best-of-breed backend systems for professional-grade monitoring and debugging.

3. System Architecture
The system is a multi-component application designed for local development (via Docker Compose) with a clear path to cloud migration.

Backend API (Python/FastAPI): A web server that hosts the agent framework, is instrumented with the OpenTelemetry SDK, and exposes endpoints for invocation and configuration management.

Configuration Data Store (SQLite): A database solely for storing Agent and Tool configurations. It does not store any runtime session or log data.

Observability Backend Stack: A best-of-breed stack for collecting and visualizing telemetry.

Jaeger: For distributed trace collection and visualization.

Prometheus: For metrics collection.

Grafana: For unified dashboarding of traces and metrics.

Frontend UI (JavaScript): A single-page application providing a management and visualization layer for the framework, including a network visualizer, configuration editor, and an integration point for viewing session traces in Jaeger/Grafana.

4. Core Framework Components
This section defines the abstract, general-purpose components that form the foundation of the framework.

4.1. The Orchestrator
The Orchestrator is a deterministic process executor. It has no reasoning capabilities. Its sole function is to receive instructions from an Agent and execute them according to a fixed set of rules.

Responsibilities:

State Management: Manages the complete state for a given session, including the initial request and a history of all executed instructions and tool results.

Instruction Parsing: Reads the structured JSON instruction from the active agent.

Validation: Performs security and permission checks. It verifies that an agent's requested tool or route is listed in its pre-defined configuration.

Execution: Carries out the validated instruction by either calling a tool or invoking the next agent.

Observability: Creates and manages OpenTelemetry traces and spans for every step of the workflow, attaching rich context (like agent reasoning) as attributes and events.

4.2. Agents (General Definition)
An Agent is the sole decision-making component in the framework. It is a specialized, intelligent module that uses an LLM to analyze the current state and determine the single next action to take.

Properties (Defined in Configuration):

name: A unique identifier.

description: A clear explanation of the agent's purpose, used to inform other agents.

equipped_tools: A list of tool names the agent is permitted to use.

allowed_routes: A list of other agent names the agent is permitted to route to.

Functionality:

Analyzes the current state provided by the Orchestrator.

Employs an internal, task-scoped reasoning loop to determine the best course of action. This may involve multiple thoughts and logical steps to arrive at a single instruction.

Outputs a single, structured JSON Instruction object for the Orchestrator to execute.

4.3. Tools (General Definition)
A Tool is a deterministic, non-LLM component that provides an interface to an external capability (e.g., an API call, a database query).

Properties (Defined in Configuration):

name: A unique identifier.

description: A clear explanation of what the tool does and its parameters.

parameters: A structured definition of the tool's inputs, with each parameter flagged as either:

agent_provided: The value is supplied by the agent's reasoning.

system_provided: The value is securely injected by the Orchestrator from the system state.

5. Communication Protocol: The Instruction Object
All agents must communicate with the Orchestrator using the following structured JSON format. A library like Instructor will be used to ensure the LLM's output conforms to this schema.

Root Object:

reasoning: (string, mandatory) A step-by-step explanation from the agent justifying why it is choosing the specified action. This is critical for observability.

action: (object, mandatory) The specific instruction, which must be one of the following types:

USE_TOOL: Contains tool_name and tool_params.

ROUTE_TO_AGENT: Contains target_agent_name and context.

RESPOND: Contains the final payload.

6. Workflow & Logic Flow: The Orchestrator Loop
The Orchestrator operates a deterministic loop that continues until a RESPOND instruction is executed.

Trace Start: An invocation request starts a new root OpenTelemetry trace.

Span Start: Before invoking an Agent, the Orchestrator starts a new span.

Instruction Generation: The Agent analyzes the state and returns a structured Instruction object.

Add Span Events: The Orchestrator attaches the Agent's full Instruction object, including reasoning, as an event to the active span.

Instruction Processing: The Orchestrator parses, validates, and executes the action. Any results (e.g., from a tool call) are also added as events to the span.

Span End & Continuation: The Orchestrator ends the current span and continues the loop by starting the next one (either for the same agent or a new one, based on the executed instruction).

7. Proof-of-Concept (POC) Implementation
This section describes the specific implementation of the framework for the sports betting company's contact center.

7.1. POC Agents

TriageAgent

Purpose: The starting agent. Analyzes the initial email, classifies intent, extracts key entities, and uses transaction tools to gather necessary data before routing.

Equipped Tools: TransactionValidationTool, TransactionSearchTool

Allowed Routes: HumanRemarksAgent

HumanRemarksAgent

Purpose: The finishing agent. Takes the fully assembled context (intent, transaction details) and drafts a personalized, empathetic message to be combined with a formal response template.

Equipped Tools: TemplateRetrievalTool

Allowed Routes: None

7.2. POC Tools

TransactionValidationTool

Description: "Validates if a given transaction ID is valid for the customer."

Parameters: transaction_id (agent_provided), customer_id (system_provided).

TransactionSearchTool

Description: "Searches for a customer's recent transactions based on criteria like amount and date."

Parameters: amount (optional, agent_provided), date_range (optional, agent_provided), customer_id (system_provided).

TemplateRetrievalTool

Description: "Fetches a pre-written response template based on the inquiry's intent."
