# Issue: Contextual Embedding Pipeline for Knowledge Base

**Date:** 2024-10-08

## Problem
- Our RAG tooling relies on manual chunking and metadata curation, producing uneven
  context windows and missing global summaries.
- We need a repeatable pipeline that ingests documentation, learns how each asset fits
  into the wider knowledge graph, and emits high-quality embeddings ready for search.

## Goals
- Automate document splitting with heuristics tuned for our corpus (Markdown, notebooks,
  transcripts, etc.).
- Use LLM-generated contextual summaries that link each chunk back to the parent doc and
  the broader domain narrative.
- Recommend metadata tags (topics, services, lifecycle state) to standardize filtering.
- Publish finished chunks directly into the vector store through a dedicated ingestion
  tool so runtime agents can query immediately.

## Proposed Steps
1. Audit existing corpora and define canonical formats + required metadata fields.
2. Design the splitter API (likely Python module in `src/arion_agents/engine/`) with
   pluggable strategies and evaluation harness.
3. Prototype an LLM prompt that produces per-chunk summaries and doc-level overviews;
   capture evaluation metrics (recall, hallucination rate).
4. Implement a metadata tagging component (rule-based + LLM fallback) and persist the
   recommendations alongside embeddings.
5. Add a writer tool that batches the resulting chunks into Qdrant (respecting the
   persistent storage design) and exposes reset/refresh controls.
6. Document the pipeline in `docs/rag_quickstart.md` (or a new guide) and wire it into
   `tools/serve_and_run.sh` for regression coverage.

## Open Questions
- Which LLM should power the summarization (Gemini vs. local) and how do we handle cost?
- Do we need human-in-the-loop review for tag vocabularies before pushing to production?
- Should chunk evaluations feed into scoring logic in the hybrid service or stay offline?
