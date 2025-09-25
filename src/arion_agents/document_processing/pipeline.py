"""High-level pipeline for PDF chunking."""
from __future__ import annotations

import re
from typing import Callable, Dict, Optional

from .chunker import ChunkedDocument, ChunkingConfig, DocumentChunker
from .pdf_loader import PDFDocument, PDFSection, decode_pdf_base64, load_pdf_document
from .tokenization import EmbeddingTokenizer, get_embedding_tokenizer

SummaryFn = Callable[[PDFDocument], Optional[str]]
SectionSummaryFn = Callable[[PDFSection], Optional[str]]


def _extractive_summary(text: str, *, max_sentences: int = 3, max_chars: int = 1000) -> Optional[str]:
    cleaned = text.strip()
    if not cleaned:
        return None
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    summary_parts: list[str] = []
    total_chars = 0
    for sentence in sentences:
        snippet = sentence.strip()
        if not snippet:
            continue
        summary_parts.append(snippet)
        total_chars += len(snippet)
        if len(summary_parts) >= max_sentences or total_chars >= max_chars:
            break
    return " ".join(summary_parts).strip() or None


def _default_document_summarizer(document: PDFDocument) -> Optional[str]:
    combined = "\n\n".join(section.text for section in document.sections)
    return _extractive_summary(combined, max_sentences=5, max_chars=1500)


def _default_section_summarizer(section: PDFSection) -> Optional[str]:
    return _extractive_summary(section.text, max_sentences=3, max_chars=700)


def chunk_pdf_document(
    pdf_bytes: bytes,
    *,
    document_id: str,
    metadata: Optional[Dict[str, str]] = None,
    chunk_config: Optional[ChunkingConfig] = None,
    tokenizer: Optional[EmbeddingTokenizer] = None,
    summarise_document: Optional[SummaryFn] = None,
    summarise_section: Optional[SectionSummaryFn] = None,
    enable_fallback_summaries: bool = True,
) -> ChunkedDocument:
    document = load_pdf_document(pdf_bytes, metadata=metadata)

    summarise_document = summarise_document or (
        _default_document_summarizer if enable_fallback_summaries else None
    )
    summarise_section = summarise_section or (
        _default_section_summarizer if enable_fallback_summaries else None
    )

    document_summary: Optional[str] = None
    if summarise_document:
        document_summary = summarise_document(document)

    section_summaries: Dict[str, str] = {}
    if summarise_section:
        for section in document.sections:
            summary = summarise_section(section)
            if summary:
                section_summaries[section.id] = summary

    tokenizer = tokenizer or get_embedding_tokenizer()
    chunker = DocumentChunker(tokenizer, config=chunk_config)
    return chunker.chunk_document(
        document,
        document_id=document_id,
        document_summary=document_summary,
        section_summaries=section_summaries,
        base_metadata=metadata,
    )


def chunk_pdf_base64(
    payload: str,
    *,
    document_id: str,
    **kwargs,
) -> ChunkedDocument:
    pdf_bytes = decode_pdf_base64(payload)
    return chunk_pdf_document(pdf_bytes, document_id=document_id, **kwargs)
