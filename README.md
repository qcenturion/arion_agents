# arion_agents

A Python project scaffold for building LLM-powered agents. This repo uses a modern `src/` layout, `pytest` for testing, and a lightweight documentation structure to guide architecture and feature planning.

## Quickstart

- Python: verified locally (see below)
- Install deps: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- Run unit tests (SQLite): `pytest`
- Run API: `make run-api`

## Local Postgres (recommended)

Use Docker for local DB to mirror production behavior.

- Start DB: `make db-up`
- Run migrations: `make db-migrate` (uses `DB_URL` Make var, default: `postgresql+psycopg://postgres:postgres@localhost:5432/arion_agents`)
- Tail logs: `make db-logs`
- Stop DB: `make db-down`
- Integration test (requires DB up): `make test-int`

Set `DATABASE_URL` in your environment to point to Postgres for the API.

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

- Confirm/adjust the feature roadmap files under `docs/features/`.
- Add a GitHub remote and push the initial commit.
- Decide on any LLM-specific evaluation tooling to complement `pytest` (see docs).


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
