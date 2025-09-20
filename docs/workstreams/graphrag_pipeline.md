# Workstream: GraphRAG Extraction & Serving

## Purpose & Scope
Deliver the GraphRAG foundations that power the control-plane UI. MVP scope focuses on:

- Ingesting source material (~500 pages) and extracting Activities, Transitions, Roles, Artifacts, Policies using the existing Gemini LLM integration (no local vLLM dependency).
- Persisting process graphs with stable identities, stored coordinates, and evidence provenance (NebulaGraph + Qdrant).
- Exposing REST/SSE payloads consumed by the front-end for graph visualisation and run playback.

Community detection, nightly jobs, and large-scale hardening are out of scope for the first release and can be revisited after MVP.

## Target Architecture
```
┌─────────┐   embeddings   ┌──────────┐
│ Source  │ ─────────────▶ │ TEI (bge)│
│ Docs    │                └────┬─────┘
└───┬─────┘                     │
    │ chunk + metadata          │ vectors (dense + sparse)
    ▼                           ▼
┌──────────┐   upsert       ┌─────────┐
│ Ingestor │ ─────────────▶ │ Qdrant  │
└────┬─────┘                └────┬────┘
     │ extractor calls            │ evidence lookup
     ▼                           ▼
┌──────────┐ structured JSON  ┌────────────┐
│ Gemini   │◀───────────────▶ │ Extractors │
│ API      │                  └────┬───────┘
└──────────┘                       │ canonicalized entities/edges
                                   ▼
                               ┌───────────────┐
                               │ Graph Loader  │
                               └────┬──────┬───┘
                                    │      │
                                    │      │ layout request
                                    ▼      ▼
                               ┌─────────┐  ┌────────┐
                               │ Nebula  │◀─│ ELK svc │
                               └────┬────┘  └────────┘
                                    │ graph queries
                                    ▼
                               ┌────────────┐
                               │ FastAPI    │
                               │ (REST/SSE) │
                               └────┬───────┘
                                    ▼
                               Front-End UI
```

## Components & Responsibilities
### Storage Layer
- **NebulaGraph** (single node initially)
  - Tags: `Activity`, `Role`, `Artifact`, `Policy`, `Community` with properties noted below.
  - Edges: `NEXT`, `PERFORMED_BY`, `REQUIRES`, `PRODUCES`, `VIOLATES`, `IN_COMMUNITY`.
  - Each node stores `x`, `y`, `pinned` (bool) for layout and `kpi` array when available.
  - VID used verbatim as `GraphNode.id` for the UI.

- **Qdrant** (hybrid collection)
  - Named collection `process_evidence`.
  - Vectors: dense + sparse (BAAI bge-m3 via TEI).
  - Payload schema:
    ```json
    {
      "doc_id": "whitepaper_001",
      "chunk_id": "00042",
      "text": "...",
      "entities": ["authenticator", "case management"],
      "relations": ["authenticator->Open Case"],
      "activity": "Open Case",
      "community_id": "comm-2",
      "kpi": [{"name": "avg_wait_ms", "value": 5400}]
    }
    ```
  - Evidence IDs formatted as `{doc_id}:{chunk_id}`; referenced in Nebula edges/nodes.

### Compute Layer
- **Gemini API** (existing integration)
  - Invoked via `arion_agents.llm` helpers.
  - Prompts enforce JSON schema output to reduce post-processing for Activities, Transitions, Roles, Artifacts, Policies.

- **Text-Embeddings-Inference** (TEI) with `bge-m3`
  - Provides both dense and sparse vectors for chunk payloads feeding Qdrant.

- **Celery Workers + Redis Broker**
  - Job orchestration for ingestion → extraction → canonicalization → graph load → layout.
  - Supports retries with idempotency keys (doc_id chunk, VID pairs).

- **ELK Layout Service**
  - Minimal Node.js service running elkjs.
  - Accepts JSON graph (nodes/edges) and returns coordinates.
  - Persists x/y back into Nebula via Graph Loader.

### API Layer (FastAPI)
- REST endpoints:
  - `GET /graphs/{versionId}`
  - `GET /runs/{traceId}`
  - `GET /evidence/{evidenceId}`
- `POST /ingest/run` (kick off pipeline for new corpus)
- `POST /runs/{traceId}/replay` (optional helper)
- SSE endpoint: `/runs/{traceId}/stream` emitting `run.step` events (see contract below).
- Propagates `traceparent` header; attaches `traceId` to logs.

## Data Model Details
### Nebula Tags
| Tag | Properties |
| --- | --- |
| `Activity` | `name`, `type` (`task`|`decision`|`subprocess`), `sla_ms`, `description`, `x`, `y`, `pinned`, `kpi` (array of `{name,value,unit?,trend?}`), `created_at`, `updated_at` |
| `Role` | `name`, `description?` |
| `Artifact` | `name`, `kind`, `description?` |
| `Policy` | `name`, `text`, `category?` |
| `Community` | *Omitted for MVP* |

### Nebula Edges
| Edge Type | Properties |
| --- | --- |
| `NEXT` | `cond`, `probability`, `avg_ms`, `support`, `evidence_ids` (string list) |
| `PERFORMED_BY` | none |
| `REQUIRES` | `input` |
| `PRODUCES` | `output` |
| `VIOLATES` | `reason`, `severity?`, `evidence_ids` |
| `IN_COMMUNITY` | *Omitted for MVP* |

### RunEnvelope Contract
```json
{
  "traceId": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
  "seq": 12,
  "t": 1758349924741,
  "step": {
    "kind": "traverse_edge",
    "edgeKey": "vid12->vid17:NEXT",
    "metrics": { "duration_ms": 1400 }
  }
}
```
- `seq` strictly increases; replay endpoints return sorted arrays.
- Additional `step` variants include `visit_node`, `attach_evidence`, `vector_lookup`, `cypher`.

## Pipeline Stages
1. **Ingestor**
   - Splits source docs using semantic chunker (e.g., `nltk` or `langchain` recursive splitter) targeting 400–600 token chunks.
   - Generates chunk metadata (source, page range, titles).
   - Calls TEI for embeddings; upserts into Qdrant with payload scaffolding (no entities yet).

2. **Extractor**
   - For each chunk (batched), call vLLM using JSON-schema prompts.
   - Collect candidate nodes and edges with provisional IDs (`temp-{uuid}`) and evidence references.

3. **Canonicalizer**
   - Deduplicate names via deterministic rules + embedding similarity (threshold e.g., cosine ≥ 0.92).
   - Map to stable IDs: either existing Nebula VIDs (via lookups) or allocate new ones.
   - Produce canonical edge records with `fromVID`, `toVID`, `edgeType`, `evidenceIds`.

4. **Graph Loader**
   - Upsert nodes/edges into Nebula via parameterised queries.
   - Attach `evidence_ids` lists using JSON arrays.
   - Trigger layout service for affected subgraphs if nodes new/updated.

5. **Layout Pass**
   - Build subgraph JSON and POST to ELK service.
   - Receive coordinates; update `x`, `y`, `pinned` (respect manual pins).

6. **Run Generation**
   - When runtime executes a request, it streams traversal steps using stored graph/evidence metadata.
   - Each tool lookup references Qdrant evidence, enabling UI to render `EvidencePanel` quickly.

## Operational Concerns
- **Container Orchestration**: Docker Compose stack containing FastAPI, Celery workers, Redis, NebulaGraph, Qdrant, vLLM, TEI, ELK service.
- **Observability**: unify logging format (`traceId`, `job_id`, `doc_id`) for ingestion jobs; metrics for throughput, error rates, queue depth.
- **Performance**: Stage extraction in batches (~50 chunks) to maximise GPU utilisation; reuse embeddings for canonicalization.
- **Resilience**: Celery tasks idempotent via unique keys; SSE stream consumers can request replay from `seq` checkpoint.

## Interfaces for Front-End & Runtime
- `GraphNode`/`GraphEdge` shapes identical to the front-end workstream doc.
- Evidence resolution via `GET /evidence/{id}` returning:
  ```json
  {
    "evidenceId": "doc42:0007",
    "text": "...chunk text...",
    "highlights": [{"start": 104, "end": 152}],
    "metadata": {"doc_id": "doc42", "chunk_id": "0007", "source": "SOP.pdf", "page_start": 12, "page_end": 13}
  }
  ```
- Run playback SSE contract identical to the front-end doc to ensure parity.

## Implementation Milestones
1. **Environment Bring-Up**
   - Compose stack with NebulaGraph, Qdrant, Redis, Celery, FastAPI skeleton, TEI service, ELK layout helper.
   - Health checks & traceparent propagation baseline using existing Gemini credentials.
2. **Ingestion MVP**
   - Ingest raw documents → Qdrant.
   - Run extractor + canonicalizer (Gemini-powered) storing sample nodes/edges in Nebula.
3. **Layout & Snapshot Publication**
   - Integrate ELK service and persist coordinates.
   - Expose `GET /graphs/{versionId}` returning stable layout.
4. **Run Playback & Evidence**
   - Wire runtime to emit `RunEnvelope` events (post-run for MVP).
   - Implement evidence resolver endpoint.
5. **QA Loop**
   - Validate CRUD-driven graph edits propagate to Nebula/Qdrant.
   - Ensure `/run` timelines align with `execution_log` semantics used in the front-end.

## Dependencies & Open Questions
- GPU availability for vLLM (minimum 24 GB recommended). Explore quantised models if constrained.
- Document ingestion format contract (PDF vs HTML vs Markdown) — choose canonical format (probably Markdown extracted via conversion pipeline).
- Moderation/safety filtering for extracted text? Potentially out of scope for MVP but note for follow-up.
- Auth between services (e.g., service tokens) to be defined once broader security posture is set.

## Alignment With Existing Docs
- Reflects goals outlined in `docs/issues/2024-09-persistent-rag-storage.md` (persistence) and extends with process graph requirements.
- Provides interfaces required by the front-end workstream; coordinates with `src/arion_agents` runtime for streaming events and layout persistence.
