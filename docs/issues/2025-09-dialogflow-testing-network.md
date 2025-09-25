# New Network: Automated DialogFlow CX Bot Testing

**Status:** To Do
**Workstream:** Tools, Agents & LLM
**Epic:** [Link to Epic if applicable]

## Summary
This issue tracks the work to design and build a new agent network dedicated to the automated, iterative testing of a DialogFlow CX chatbot. The system will manage conversations with the bot, evaluate its responses against predefined criteria, and log the results in a structured format. This is particularly aimed at testing the bot's RAG capabilities and ensuring consistent quality.

---

## 1. New Tool: DialogFlow CX Integration

A new tool is required to communicate with the DialogFlow CX API.

### Requirements
- **Authentication:** The tool must authenticate using Google Cloud SDK and a provided JSON service account key.
- **Interaction:** It needs a `run` method that can send a message to a specified DialogFlow session and return the bot's response.
- **Configuration:** The specific DialogFlow bot endpoint/session details should be configurable at the system level, not hardcoded in the tool.

### Files to Investigate
- **`src/arion_agents/tools/base.py`**: The `BaseTool` class will be the foundation for the new `DialogFlowCXTool`.
- **`src/arion_agents/secrets.py`**: This will be the place to manage the loading and handling of the DialogFlow JSON credentials file securely.
- **`src/arion_agents/system_params.py`**: The mechanism for injecting system-level parameters (like the bot endpoint) into the tool at runtime.
- **`src/arion_agents/tools/registry.py`**: The new tool provider will need to be registered here.
- **`src/arion_agents/tools/dialogflow.py`**: New tool implementation. TODO: add authenticated customer profile payload once UI sends username/auth context.
- **`config/system_params_defaults.json`**: Defaults now pre-populated with `dialogflow_project_id=satacs-be-prd`, `dialogflow_location=global`, `dialogflow_environment=draft`, language `en`.
- Tool automatically seeds each session with the hidden warm-up utterance `"ewc"`, sets `$session.params.sataCustomerVerified="true"`, and applies `sataUsername` (default `CSTESTINR`, overrideable via system params or tool params).
- Tool now returns a compact summary (only the visible bot message by default) to keep LLM token usage low; set `dialogflow_summary_mode="detailed"` for richer diagnostics when needed.
- **`tools/seed_dialogflow_demo.py`** seeds a fresh network (`dialogflow_multiple_accounts_demo`) with the new tool and a tester agent, then publishes it. Optional smoke test calls `/run` with the configured agent ID.

---

## 2. New Agent Network: "Bot Tester"

A new network with at least two specialized agents needs to be designed.

### Agent Roles
1.  **`DialogFlowTesterAgent`**:
    *   **Objective:** Initiate and carry on a conversation with the DialogFlow bot via the new tool.
    *   **Instructions:** Will be given a persona and a fictional issue to resolve.
    *   **Stopping Conditions:** Its prompt will include instructions to stop and route to the evaluation agent if specific conditions are met (e.g., the bot triggers a human handoff, a response is repeated 3 times, or a seemingly correct answer is provided).
2.  **`ConversationEvaluatorAgent`**:
    *   **Objective:** Receive the conversation history from the tester agent and evaluate the bot's final answer.
    *   **Instructions:** Will be given specific scoring criteria (e.g., "Was the answer correct? Was it concise? Did it fully resolve the user's issue?").
    *   **Action:** After its analysis, it will use the `RESPOND` action to output the final, structured evaluation.

### Files to Investigate
- **API Endpoints (`/config/*`)**: The new network, agents, and their tool configurations will be created using the existing configuration API. No code changes are expected here, but the API will be the primary interface for setup.
- **`src/arion_agents/prompts/context_builder.py`**: We will rely on this to ensure the prompts for the new agents are constructed correctly based on their unique goals, tools, and routing capabilities.

---

## 3. Data Persistence & Structured Logging

The results of each test run must be stored for later analysis.

### Requirements
- The full conversation history (user message -> bot response) must be accessible.
- The final evaluation from the `ConversationEvaluatorAgent` must be stored.
- **NOTE:** Run records now carry `experiment_id`, `experiment_*` metadata, and include the full `tool_log`; add stored procedure later to project conversations for analytics (TODO).

### Files to Investigate
- **`src/arion_agents/db.py`**: We need to examine the schema for the `run_history` table. Does it store the full `tool_log` (which contains the structured request/response from tool calls)? If not, this schema may need to be updated.
- **`src/arion_agents/engine/loop.py`**: This is where the `RunResult` is assembled and saved. We need to confirm that the complete `tool_log` is being passed to the database layer for persistence. The data is likely already available here; we just need to ensure it's being saved.

---

## 4. Batch Processing: "Experiment Runner" Module

A mechanism is needed to run tests in batches (e.g., 20 questions, 5 times each).

### Requirements
- A new entry point, separate from the single-message `/run` API, is needed.
- It should be able to read a list of inputs from a file (e.g., CSV or JSONL).
- For each input, it should trigger a new run of the target network using the agent’s existing prompt; file data only augments the run.
- It should manage the queue and execution of these batch runs.
- **Implemented:** `/run-batch` API accepts structured experiment payloads (CSV parsing still TODO upstream UI).

### CSV → Experiment payload mapping
- **Required column:** `iterations` (positive integer). All other columns are optional augmentations that flow into the `ExperimentItem` payload.
- Suggested optional headers:
  - `issue_description` → becomes part of the run’s user prompt context (prepended/embedded ahead of `user_message`).
  - `true_solution_description` → mapped to `correct_answer` for downstream evaluation.
  - `stopping_conditions` → appended to the agent instructions for that run; these are soft per-session hints, not hard orchestrator limits.
  - `user_message` → seed message to kick off the run (defaults to the base operator prompt if omitted).
  - `system_params.*` → any header prefixed with `system_params.` feeds into per-item system overrides (e.g., `system_params.username`).
  - Additional columns land under `metadata` for analytics.

### Control knobs & safety rails
- The orchestrator already enforces a hard loop ceiling via the `max_steps` argument (default 10). Expose this as an experiment-level knob so batches can opt into a lower or higher cap.
- Soft stopping conditions (e.g., “bot hands off to a human”) remain part of the agent prompt; they should be templated with placeholders that the CSV row can fill.
- Hard failures (tool errors, LLM exceptions) bubble up as normal and cause the iteration to terminate.

### UX & async execution
- Upload CSV/JSONL, preview inferred mappings, allow overrides, and produce the structured experiment payload. Surface inline helper text summarising required vs. optional columns (at minimum: `iterations` required; `issue_description`, `true_solution_description`, `stopping_conditions`, `user_message`, `system_params.*` optional).
- Kick off batch runs asynchronously: enqueue work and return a handle so the UI can poll progress, stream per-item results, and download consolidated transcripts.
- Minimal async design: persist an `experiment_queue` row per item, let the API return immediately, and run a lightweight background worker (FastAPI `BackgroundTasks` initially, extracted to a dedicated process as volume grows) that dequeues sequential runs and records status/progress timestamps.
- Provide a CLI helper (e.g., `tools/run_experiment.py`) that mirrors the UI contract for automation and smoke testing.

### Experiment history & reporting
- Maintain an `experiments` overview panel showing experiment metadata (ID, description, created/started/completed timestamps, total runs, success vs. failure counts, last status update).
- Each experiment row links to detailed run history (per-item iterations, trace IDs, final status) leveraging existing `/runs` data. Initial scope can reuse the current run log viewer filtered by `experiment_id`.

### Implementation plan (minimal first cut)
1. **Schema & queue plumbing**
   - Create `experiment_queue` table (columns: id, experiment_id, item_index, iteration, status enum, enqueued_at, started_at, completed_at, error, payload JSON).
   - Extend `/run-batch` to insert queue rows instead of executing inline; return `{ experiment_id, total_items, queued: true }`.
   - Add helper in `run_models.py` for queue access plus DAL functions (enqueue, lease next pending, mark status).
2. **Async worker**
   - Introduce background consumer in API process using FastAPI `BackgroundTasks` (triggered when `/run-batch` receives work) that drains the queue sequentially.
   - Provide abstraction so we can later move the consumer into a dedicated worker service without API changes.
   - Respect experiment-level `max_steps` override when calling `run_loop`.
3. **CSV ingestion helper**
   - `/run-batch/upload` endpoint accepts multipart CSV/JSONL, infers columns per schema above, echoes preview + inferred payload; UI can confirm and call the main `/run-batch`.
   - Add `tools/run_experiment.py` CLI with identical contract for automation.
4. **UI work**
   - New “Experiments” tab with two panels:
     - Upload wizard: file select, helper text, mapping overrides, shared params editor, submit button.
     - Experiment history list: fetch `/experiments` summary, show ID, description, created/start/end times, total runs, success/failure counts; link to filtered Run Console view.
   - Add experiment progress view (poll `/experiments/{id}` for queued/in-progress/completed counts).
5. **Observability**
   - Emit structured logs and metrics for queue depth, per-item duration, failure reasons.
   - Optional: webhook or email hooks later for completion notifications.

### Files to Investigate
- **This will likely be a new file:** A good approach would be to create a new script, for example, **`tools/run_experiment.py`**. This script would contain the logic for parsing the input file and repeatedly calling the core `run_loop` function (from `src/arion_agents/engine/loop.py`) or making requests to the `/run` API endpoint. This approach isolates the batching logic from the core agent runtime.
