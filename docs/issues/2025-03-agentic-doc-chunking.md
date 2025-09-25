# Agentic Document Chunking Network

This issue doc tracks design work for the PDF ingestion network that performs adaptive chunking, metadata enrichment, and RAG ingestion. We will iteratively refine the plan here before cutting tickets or writing code.

## Goals
- Plan an agent network that can inspect PDFs, generate hierarchical summaries, produce ~200-token chunks with contextual padding, and index them into Qdrant.
- Support dynamic dictionaries that clarify overloaded acronyms or domain entities (e.g., `MY` = Malaysia) without forcing full document scans for every run.
- Handle embedded hyperlinks that may reference other documents; ensure the network flags missing resources or fetches linked docs when available.

## Proposed Agent Topology
1. **Planner (`doc_ingest_planner`)**
   - Default entry agent, non-responding.
   - Consumes PDF metadata pointers; decides whether to request summaries, dictionary updates, or hyperlink checks.
   - Routes to structure scanner, summary orchestrator, chunk builder, dictionary steward, and RAG ingestor.
2. **Structure Scanner (`structure_scanner`)**
   - Uses `pdf_outline` tool to fetch page/section stats and heading hierarchy.
   - Returns normalized structure back to planner.
3. **Summary Orchestrator (`summary_orchestrator`)**
   - Generates document/chapter/section summaries via LLM tools.
   - May request raw section text through a `section_reader` helper.
4. **Chunk Builder (`chunk_builder`)**
   - Calls `chunk_generate` tool (wrapping `chunk_pdf_document`) with planner-provided config.
   - Validates chunk counts and token budgets.
5. **Dictionary Steward (`dictionary_steward`)**
   - Manages contextual dictionary entries.
   - Can query existing dictionary store, add new entries, or ask user/SME for clarification when necessary.
6. **Hyperlink Auditor (`hyperlink_auditor`)** *(optional, depending on volume)*
   - Detects outgoing links, verifies whether referenced docs exist in the staged collection, raises flags otherwise.
7. **RAG Ingestor (`rag_ingestor`)**
   - Final agent; assembles payloads for `/chunk-and-index` and confirms ingestion or errors.

All agents except planner respond only when their sub-task is done, routing control back to planner or onward per plan.

## Tooling Requirements
- `pdf_outline`: wraps `document_processing.load_pdf_document` to provide section stats without full chunking.
- `section_reader`: returns text for a specific `section_id` (with optional token truncation) so summarizers can work incrementally.
- `chunk_generate`: produces chunk payloads with configurable window/overlap/context settings (no indexing).
- `dictionary_store`: CRUD interface (likely Postgres table exposed via internal tool) that stores `{term, expansion, metadata, provenance}`.
- `hyperlink_resolver`: checks whether an extracted link target exists locally; returns match status and suggested actions.
- `rag_chunk_index`: POST to `/chunk-and-index` for final ingestion (reuse hybrid RAG provider with `index_path`).

## Dictionary Strategy
- Maintain a dedicated `document_dictionary` table keyed by normalized term.
- Each entry stores expansion, optional disambiguation text, tags (region, business unit), source document IDs, and timestamps.
- Expose tool operations:
  - `dictionary_lookup(term: str) -> entries`
  - `dictionary_upsert(term: str, expansion: str, context: str)`
  - `dictionary_suggest(missing_terms: list[str])` for batch prompts.
- Planner logic:
  1. During structure scan or summary generation, agents flag ambiguous tokens (e.g., uppercase 2–3 letter tokens matching dictionary heuristics).
  2. Dictionary steward queries existing entries. If gap persists, it can:
     - Ask summarizer/LLM to infer likely expansion.
     - Escalate to user via response/action log (depending on integration).
  3. Final chunks include resolved dictionary metadata for downstream retrieval prompts.
- Prompt injection: planner assembles a dictionary context block (e.g., top N relevant entries based on document metadata) and injects into summarizer/chunker prompts.

## Hyperlink Handling
- `pdf_outline` extracts href targets and anchors when available.
- Hyperlink auditor checks each target name/ID against staged document inventory (the “local folder” you mentioned). Possible actions:
  - If file is present, add cross-reference metadata so chunks carry relationship info.
  - If missing, log/flag for ingestion backlog.
- Planner decides whether to follow links immediately or stash for later ingestion to avoid deep recursive fetches.

## Open Questions / Decisions Needed
- **Dictionary seeding:** Do we pre-populate from historical docs, or rely purely on runtime discovery? Hybrid approach may need offline seeding script.
- **Storage & APIs:** Will dictionary updates happen through the FastAPI config endpoints or a new service route? (Leaning toward a dedicated `/dictionary` resource alongside the ingestion API.)
- **Hyperlink scope:** Should agents auto-fetch linked PDFs when available, or only annotate and wait for manual ingestion? Risk of runaway recursion if not bounded.
- **Performance:** Large PDFs may make repeated `section_reader` calls expensive. Consider caching parsed sections per ingestion session.
- **User-in-the-loop:** For ambiguous terms, do we pause ingestion and request clarification, or proceed with best guess + flag? Need UX decision.

## Next Steps
1. Define storage schema for dictionary entries and hyperlink manifests.
2. Draft tool provider implementations (internal wrappers + metadata for registry).
3. Write planner prompt skeleton capturing decision tree (document length, metadata availability, dictionary completeness).
4. Produce API/SQL scripts for network creation (mirroring `tools/seed_location_demo.py`).
5. Review document folder structure to confirm hyperlink resolution strategy (naming conventions, IDs).

Use this doc as the canonical place to capture revisions before coding. Add questions, decisions, or pseudocode snippets as the design stabilizes.

## Image Handling with Gemini
- Extend PDF parsing to capture embedded images (use PyMuPDF alongside existing text extraction). Store references with page numbers, bounding boxes, and nearby text captions if available.
- Introduce an `image_annotator` tool that wraps Gemini’s multimodal API. Params: `document_id`, `image_bytes` (system-supplied), `page_index`, optional `neighbor_text`. Returns structured annotations: concise caption, step-by-step description, notable entities.
- Add an **Image Describer** agent the planner can route to when sections contain images. It batches annotation requests, writes results into shared metadata for use by chunk builder.
- Chunk builder embeds image summaries into contextual padding (e.g., `Image Summary: ...`) and includes image metadata (page reference, original filename) in `metadata_pairs` so RAG clients can link back to source docs.
- Since images stay in the source PDF, chunk metadata should include `source_page` and a stable `document_path` so end users can open the original for full visuals.

## Implemented Files / Endpoints (session summary)
- `docs/chunking_pipeline.md` – high-level overview of pipeline objectives and flow.
- `src/arion_agents/document_processing/` modules (`__init__`, `tokenization.py`, `pdf_loader.py`, `chunker.py`, `pipeline.py`) – text chunking utilities.
- `tools/rag_service/service.py` – added `/chunk-and-index` endpoint to invoke the pipeline and index chunks.
- `docs/issues/2025-03-agentic-doc-chunking.md` – design issue doc (this file).
- Updated `requirements.txt` to include `pypdf` for PDF parsing.

## Concurrency & Task Group Planning
### Current State
- `run_loop` (see `src/arion_agents/engine/loop.py`) executes a single agent at a time in a strict request→LLM decision→action cycle.
- Each step ends with either staying on the same agent (after `USE_TOOL`), switching agents (`ROUTE_TO_AGENT`), or returning a final `RESPOND`.
- The decision schema (`AgentDecision`) only supports one action per step, preventing an agent from scheduling parallel sub-tasks.

### Enhancement Goals
1. Allow a planner agent to dispatch multiple sub-requests without waiting for each sequentially.
2. Keep the orchestration loop predictable (avoid uncontrolled recursion) and maintain existing execution logs.
3. Preserve “tool-call semantics” so that, from the planner’s perspective, sub-agent work resembles awaiting tool results.

### Proposed Minimal Upgrade
- Introduce a new `TASK_GROUP` action type where `action_details` contains a list of child tasks. Each task can be either:
  - `use_tool`: standard tool invocation (already supported).
  - `delegate_agent`: spawn a bounded sub-run to another agent (treated as a tool internally).
- Update `decision_to_instruction` and `execute_instruction` to handle `TASK_GROUP` by creating asynchronous jobs (likely via `asyncio`, but a thread pool suffices initially) and waiting for all to complete before resuming the planner step.
- Child tasks would reuse existing logging by writing synthetic tool entries with a `group_id`, so the conversation history reflects every sub-task outcome.
- Limit concurrency per task group (e.g., max 3 parallel tasks) to avoid resource starvation.

### Agent-as-Tool Bridge
- Add an internal tool provider (`agent:delegate`) that accepts `{target_agent, context, max_steps}` and internally calls `run_loop` with a fresh execution log slice.
- From the orchestrator’s perspective, this looks like a tool call (keeping loop semantics intact). The planner can include multiple `delegate_agent` tasks inside a `TASK_GROUP`, allowing parallel agent execution without changing routing rules.
- Need to propagate shared context selectively: pass the original user message + planner-provided sub-context into the delegated run; merge execution summaries back on completion.

### Incremental Rollout
1. Extend the decision schema and orchestrator to recognize `TASK_GROUP` (can still execute sequentially at first to unblock functionality).
2. Implement `agent:delegate` provider so agents can call other agents as if they were tools.
3. Add true parallelism (async gather) once stability is confirmed.
4. Revisit planner prompts to generate `TASK_GROUP` JSON (inspired by LangGraph “Send / Gather” pattern).

### Research References
- LangGraph’s `state.graph` & `Send`/`Gather` operations show how to fan out tasks and wait for them—useful inspiration for grouping constructs.
- Guidance from `openai/semantic-router` and `crewAI` on task delegation also illustrate agent-as-tool patterns.

Document open questions:
- How to replay child run logs in parent context (flatten vs. nested view)?
- Budget accounting across parallel tasks (shared token limits?).
- Retry/backoff strategy if one child task fails—does the planner resume others or abort the whole group?
