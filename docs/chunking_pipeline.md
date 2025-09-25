# Chunking Pipeline Overview

This document captures the first iteration of the document chunking pipeline that pairs with the Qdrant-backed RAG service.

## Objectives

- Normalize access to the BGE embedding tokenizer so new orchestration helpers can make token-aware decisions without duplicating setup code.
- Support PDF extraction with lightweight heuristics that identify document structure (front matter, headings, sub-sections) and thaw the raw text into a section tree.
- Provide a configurable chunker that slices primary content into ~200-token payloads and prepends up to ~100 tokens of contextual breadcrumbs derived from metadata, section headings, and agent-supplied summaries.
- Expose an ingestion endpoint in the RAG service so the agentic pipeline can submit a PDF, generate summaries as needed, and write enriched chunks directly into Qdrant.

## High-Level Flow

1. **Parse PDF** – Read PDF bytes using `pypdf` and emit a `DocumentLayout` object with pages, line blocks, and detected headings.
2. **Summaries & Metadata** – Agents (or pluggable summarizers) can request:
   - Document-wide overview
   - Section-level synopsis
   - Optional chapter/page highlights
3. **Token-Aware Chunking** – The `DocumentChunker` consumes section text + optional summaries:
   - Breaks section text into ~200-token primary slices (respecting boundary sentences when possible).
   - Conditionally layers contextual strings (document summary, section summary, headings, metadata key-value pairs, neighbor section titles) until a 100-token side window is reached.
4. **Ingestion** – Each chunk is converted into an index payload with:
   - `id`: deterministic slug combining document, section, and chunk index.
   - `text`: context + primary content.
   - `metadata`: provenance (document id, section id, title hierarchy, page span, summary references, token counts).
5. **RAG Service Endpoint** – `/chunk-and-index` accepts `{ document_id, pdf_base64, metadata, collection? }`, runs the pipeline, and inserts resulting chunks into the requested collection.

## Key Components

- `arion_agents.document_processing.tokenization`
  - Lazy-loads Hugging Face tokenizer for the configured embedding model.
  - Exposes helpers for encoding, decoding, and counting tokens.

- `arion_agents.document_processing.pdf_loader`
  - Wraps `pypdf.PdfReader`.
  - Provides `extract_sections` that groups text beneath detected headings. Heuristics treat all-caps lines, numbered headings, or short title-like lines as section boundaries.

- `arion_agents.document_processing.chunker`
  - `DocumentChunker` orchestrates splitting and context weaving.
  - Uses `TokenizedText` dataclass to keep token ids and decoded text in sync.
  - Accepts `ChunkingConfig` for tunables (primary window, context cap, overlap, summary usage flags).

- `arion_agents.document_processing.pipeline`
  - Convenience function `chunk_pdf_document` that ties everything together.
  - Accepts optional callbacks for document and section summarization so the orchestrator can plug in LLM-backed agents.

- `tools.rag_service.service`
  - Adds `/chunk-and-index` endpoint.
  - Utilizes the pipeline and streams new chunks into Qdrant.
  - Returns both chunk statistics and summary metadata to the caller for follow-on workflows.

## Follow-Up Ideas

- Detect table structures and include them as separate metadata payloads.
- Persist intermediate summaries into a cache directory for re-use across ingestion runs.
- Support alternative chunk strategies (sentence-based, layout-preserving) through strategy classes injected into `DocumentChunker`.
