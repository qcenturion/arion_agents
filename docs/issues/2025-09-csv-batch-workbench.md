# CSV Batch Workbench

**Status:** Draft
**Date:** 2025-09-27
**Owner:** Codex

## 1. Overview

Introduce a CSV-oriented batch runner that mirrors the Experiments “queue” experience but focuses on structured data ingestion and response capture. Users can upload a CSV, map columns to runtime inputs, define the desired JSON output schema (“Add column” UI), and execute each row sequentially through `/run`. Results appear in a queue table with per-run drill-down and can be exported on demand.

Key requirements:

1. Minimal setup—single-agent networks acceptable, no snapshot cloning required.
2. Familiar UX—reuse Experiments’ upload preview, queue visualization, and run drill-down patterns.
3. Schema awareness—operators define the response payload shape via UI controls; generated schema becomes part of the network’s RESPOND metadata for the run session.
4. Export control—like Experiments, expose an “Export CSV” action once the queue completes (not automatic).

## 2. Reuse From Experiments

| Area | Reuse | Adjustments |
| --- | --- | --- |
| File upload | Existing CSV/JSONL parser + preview component | Rename prompts/labels to “Columns”/“Input mapping”. No expected-answer concepts. |
| Queue backend | Same queue model (`experiment_queue_items`) | Clone schema into a new table (e.g., `csv_batch_items`) if naming gets confusing; share worker logic. |
| Queue UI | Left rail progress, status filters, detail panel | Swap column headers to focus on row index, CSV key columns, response summary. |
| Run drill-down | Shared run viewer (`TraceTimeline`, `StepDetailsPanel`) | Identify the parent queue item ID so exports can reconcile row → result. |
| Export action | Existing download button + API | Generate a CSV/JSON export on demand, including original columns + response payload fields. |

## 3. New UX Flow

1. **Upload step**
   - Dropzone accepts CSV only for MVP (JSONL later).
   - Parse with existing backend helper; preview top N rows.
   - Let users rename the dataset (display only).

2. **Column mapping**
   - For each CSV column, allow toggling between:
     - `Ignore`
     - `Include in prompt` (concatenate into the agent prompt template)
     - `Send as system param` (key name defaults to column header; editable)
   - Provide a live example prompt showing how selected columns appear.

3. **Prompt definition**
   - Single textarea where users define the agent instruction (supports templating tokens like `{{ system_params.customer_email.body }}`).
   - Preview includes one sample row to validate substitution.

4. **Response schema builder**
   - “Add field” button → prompts for `field name` + `description` + type (string, number, boolean; default string for MVP).
   - Maintains an ordered list; fields can be edited or removed.
   - Description fed into RESPOND guidance; names aggregated into JSON Schema.
   - Optional “Mark required” toggle per field.

5. **Run configuration summary**
   - Selected network name + agent key (if multiple agents; default agent otherwise).
   - Row count, estimated run time (based on sequential execution).
   - Buttons: `Start batch`, `Reset form`.

6. **Queue execution**
   - Once launched, reuse Experiments’ queue worker:
     - Each row wrapped as `{ system_params: { row_data }, user_message: rendered_prompt }`.
     - Submit to `/run` with `debug=false` by default; optional toggle to capture debug traces.
   - UI shows row index, status (queued, running, succeeded, failed), timestamp.
   - Clicking an item opens the familiar run detail view (Trace timeline + final payload).

7. **Export**
   - After queue completion, “Export CSV” button performs server-side merge:
     - Original CSV columns.
     - One column per response field (extracted from `final.response_payload[field]`).
     - Optional metadata (trace ID, status, elapsed time).

## 4. Backend Changes

1. **Data model**
   - New tables (or reuse with a type flag):
     - `csv_batches` (id, name, network_id, agent_key, schema_json, prompt_template, created_by, created_at).
     - `csv_batch_rows` (id, batch_id, row_index, row_payload JSON, status ENUM, run_trace_id, result_payload JSON, error_message, timestamps).
   - If we reuse experiments tables, add a `kind` column and filter accordingly.

2. **API endpoints**
   - `POST /csv_batches` – create batch config + upload metadata.
   - `POST /csv_batches/{id}/rows` – bulk insert row payloads (called right after upload).
   - `POST /csv_batches/{id}/run` – enqueue items (similar to `/experiments/{id}/run`).
   - `GET /csv_batches/{id}` / `GET /csv_batches/{id}/rows` – progress polling.
   - `GET /csv_batches/{id}/export` – produce CSV on demand.

3. **Worker**
   - Reuse experiment queue worker logic; inject different prompt/response handling:
     - Build `user_message` by rendering the CSV row into the template (same templating helper as experiments).
     - Set `system_params` to the selected columns (key → raw cell value).
     - Call `/run` with network + optional agent key.
     - Capture `final.response_payload` and store in row record.

4. **Network schema injection**
   - Before running a batch, update the target network’s `additional_data.respond_payload_schema` (and guidance/example) based on UI inputs.
   - Optionally warn if the existing schema differs; allow users to skip the update if they have a pre-defined schema.

## 5. Front-End Implementation Plan

1. **Route**
   - Create `frontend/app/csv-batch/page.tsx` (parallel to experiments page).
   - Shared layout components (`QueueSidebar`, `QueueDetailPane`) can be imported with renamed props.

2. **Upload + Mapping wizard**
   - Stepper with sections: Upload → Map Inputs → Define Prompt → Response Schema → Review → Run.
   - Store state in a dedicated Zustand slice (mirroring experiments store) for undo/reset behavior.

3. **Queue view**
   - Reuse `QueueTable` and detail components; pass new column definitions (Row #, Status, Started, Completed, Summary fields).
   - Summary row for each item should display key response fields (maybe first two schema fields).

4. **Run detail**
   - Existing run viewer with ability to tap into `final.response_payload` and show as structured list.
   - Add a panel for “Original row data” so analysts can compare input ↔ output.

5. **Export button**
   - Mirror experiments export component; call new endpoint.
   - Provide CSV + JSONL options for completeness (JSONL later if needed).

6. **Empty states & errors**
   - Guidance cards explaining required steps (upload, prompt, schema) before enabling “Start batch”.
   - Row-level errors surfaced inline with retry option (similar to experiments retry queue item).

## 6. Open Questions

1. Should we allow multi-agent networks, or always force the default agent for simplicity?
2. Do we need per-row overrides (e.g., different prompt chunk) beyond the mapped columns?
3. How do we handle huge CSVs? For MVP, rely on existing upload limits; pagination can come later.
4. Should schema updates modify the persisted network, or stay ephemeral to the batch session?

## 7. Next Steps

1. Confirm whether to fork experiments tables or extend them with a `kind` discriminator.
2. Implement backend endpoints and queue worker reuse.
3. Build the React wizard + queue view.
4. Dogfood with a sample email classification CSV; verify schema enforcement and export format.
5. Iterate on UX copy based on user feedback.

