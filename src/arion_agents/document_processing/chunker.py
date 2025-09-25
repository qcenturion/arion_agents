"""Token-aware chunking pipeline."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

from .pdf_loader import PDFDocument, PDFSection
from .tokenization import EmbeddingTokenizer


@dataclass
class ChunkingConfig:
    primary_window_tokens: int = 200
    context_window_tokens: int = 100
    chunk_overlap_tokens: int = 40
    max_total_tokens: Optional[int] = None
    include_document_summary: bool = True
    include_section_summary: bool = True
    include_heading_path: bool = True
    include_metadata: bool = True

    def __post_init__(self) -> None:
        if self.primary_window_tokens <= 0:
            raise ValueError("primary_window_tokens must be positive")
        if self.context_window_tokens < 0:
            raise ValueError("context_window_tokens must be non-negative")
        if self.chunk_overlap_tokens < 0:
            raise ValueError("chunk_overlap_tokens must be non-negative")
        if (
            self.max_total_tokens is not None
            and self.max_total_tokens < self.primary_window_tokens + self.context_window_tokens
        ):
            raise ValueError(
                "max_total_tokens must be >= primary + context windows when provided"
            )


@dataclass
class ChunkPayload:
    id: str
    text: str
    metadata: Dict[str, object]


@dataclass
class ChunkedDocument:
    document_id: str
    chunks: List[ChunkPayload]
    document_summary: Optional[str]
    section_summaries: Dict[str, str]
    stats: Dict[str, object] = field(default_factory=dict)


def _slugify_identifier(value: str) -> str:
    collapsed = re.sub(r"\s+", " ", value).strip().lower()
    if not collapsed:
        return "item"
    slug = re.sub(r"[^a-z0-9]+", "-", collapsed)
    slug = slug.strip("-")
    return slug or "item"


class DocumentChunker:
    def __init__(self, tokenizer: EmbeddingTokenizer, config: Optional[ChunkingConfig] = None) -> None:
        self.tokenizer = tokenizer
        self.config = config or ChunkingConfig()

    def chunk_document(
        self,
        document: PDFDocument,
        *,
        document_id: str,
        document_summary: Optional[str] = None,
        section_summaries: Optional[Dict[str, str]] = None,
        base_metadata: Optional[Dict[str, object]] = None,
    ) -> ChunkedDocument:
        section_summaries = section_summaries or {}
        base_metadata = base_metadata or {}

        chunks: List[ChunkPayload] = []
        total_primary_tokens = 0
        total_context_tokens = 0

        for section in document.sections:
            section_summary = section_summaries.get(section.id)
            section_chunks = self._chunk_section(
                section,
                document_id=document_id,
                document_summary=document_summary,
                section_summary=section_summary,
                base_metadata=base_metadata,
            )
            for payload in section_chunks:
                meta = payload.metadata
                total_primary_tokens += int(meta.get("primary_token_count", 0))
                total_context_tokens += int(meta.get("context_token_count", 0))
            chunks.extend(section_chunks)

        stats = {
            "sections": len(document.sections),
            "chunks": len(chunks),
            "primary_tokens": total_primary_tokens,
            "context_tokens": total_context_tokens,
            "total_tokens": total_primary_tokens + total_context_tokens,
        }

        return ChunkedDocument(
            document_id=document_id,
            chunks=chunks,
            document_summary=document_summary,
            section_summaries=section_summaries,
            stats=stats,
        )

    def _chunk_section(
        self,
        section: PDFSection,
        *,
        document_id: str,
        document_summary: Optional[str],
        section_summary: Optional[str],
        base_metadata: Dict[str, object],
    ) -> List[ChunkPayload]:
        raw_text = section.text.strip()
        if not raw_text:
            return []

        slices = self.tokenizer.slice_tokens(
            raw_text,
            chunk_size=self.config.primary_window_tokens,
            overlap=self.config.chunk_overlap_tokens,
        )
        payloads: List[ChunkPayload] = []

        heading_path = " > ".join(
            [title for title in section.heading_path if title] + [section.title]
        )
        metadata_pairs = self._metadata_pairs(base_metadata, section)

        for idx, token_slice in enumerate(slices):
            primary_tokens = list(token_slice.tokens)
            primary_text = self.tokenizer.decode(primary_tokens).strip()
            if not primary_text:
                continue

            context_segments = self._build_context_segments(
                document_summary=document_summary,
                section_summary=section_summary,
                heading_path=heading_path,
                metadata_pairs=metadata_pairs,
            )
            context_tokens, context_texts = self._merge_context(context_segments)

            total_tokens = len(context_tokens) + len(primary_tokens)
            max_total = self.config.max_total_tokens or self.tokenizer.max_length
            if total_tokens > max_total:
                overflow = total_tokens - max_total
                if overflow >= len(primary_tokens):
                    # Fallback: trim both context and primary evenly
                    primary_tokens = primary_tokens[: max(0, len(primary_tokens) - overflow)]
                else:
                    # Trim context first
                    context_tokens = context_tokens[: max(0, len(context_tokens) - overflow)]
                    context_texts = [self.tokenizer.decode(context_tokens).strip()]
                primary_text = self.tokenizer.decode(primary_tokens).strip()

            text_parts = [part for part in context_texts if part]
            if primary_text:
                text_parts.append(primary_text)
            merged_text = "\n\n".join(text_parts)

            chunk_id = self._build_chunk_id(document_id, section.id, idx)
            payload = ChunkPayload(
                id=chunk_id,
                text=merged_text,
                metadata={
                    "document_id": document_id,
                    "section_id": section.id,
                    "chunk_index": idx,
                    "section_title": section.title,
                    "section_level": section.level,
                    "page_start": section.page_start,
                    "page_end": section.page_end,
                    "heading_path": section.heading_path,
                    "primary_token_count": len(primary_tokens),
                    "context_token_count": len(context_tokens),
                    "total_token_count": len(primary_tokens) + len(context_tokens),
                    "document_summary_present": bool(document_summary),
                    "section_summary_present": bool(section_summary),
                    "metadata_pairs": metadata_pairs,
                },
            )
            payloads.append(payload)
        return payloads

    def _metadata_pairs(
        self,
        base_metadata: Dict[str, object],
        section: PDFSection,
    ) -> List[str]:
        pairs: List[str] = []
        if self.config.include_metadata and base_metadata:
            for key, value in base_metadata.items():
                pairs.append(f"{key}: {value}")
        section_meta = section.metadata or {}
        for key, value in section_meta.items():
            pairs.append(f"section.{key}: {value}")
        return pairs

    def _build_context_segments(
        self,
        *,
        document_summary: Optional[str],
        section_summary: Optional[str],
        heading_path: str,
        metadata_pairs: Sequence[str],
    ) -> List[str]:
        segments: List[str] = []
        if self.config.include_heading_path and heading_path:
            segments.append(f"Heading: {heading_path}")
        if self.config.include_document_summary and document_summary:
            segments.append(f"Document Summary: {document_summary.strip()}")
        if self.config.include_section_summary and section_summary:
            segments.append(f"Section Summary: {section_summary.strip()}")
        if self.config.include_metadata and metadata_pairs:
            segments.append("Metadata: " + "; ".join(metadata_pairs))
        return segments

    def _merge_context(
        self,
        segments: Iterable[str],
    ) -> tuple[List[int], List[str]]:
        if not self.config.context_window_tokens:
            return [], []
        remaining = self.config.context_window_tokens
        all_tokens: List[int] = []
        texts: List[str] = []
        for segment in segments:
            if remaining <= 0:
                break
            encoded = self.tokenizer.encode(segment)
            if not encoded:
                continue
            if len(encoded) > remaining:
                encoded = encoded[:remaining]
            all_tokens.extend(encoded)
            texts.append(self.tokenizer.decode(encoded).strip())
            remaining -= len(encoded)
        return all_tokens, [text for text in texts if text]

    def _build_chunk_id(self, document_id: str, section_id: str, chunk_index: int) -> str:
        base = _slugify_identifier(document_id)
        section_slug = _slugify_identifier(section_id)
        return f"{base}-{section_slug}-chunk-{chunk_index:03d}"
