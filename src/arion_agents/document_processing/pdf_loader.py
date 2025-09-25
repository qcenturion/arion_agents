"""PDF extraction helpers."""
from __future__ import annotations

import base64
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from pypdf import PdfReader


@dataclass
class PDFPage:
    index: int
    text: str


@dataclass
class PDFSection:
    id: str
    title: str
    level: int
    text: str
    page_start: int
    page_end: int
    heading_path: Sequence[str] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class PDFDocument:
    source: str
    pages: List[PDFPage]
    sections: List[PDFSection]
    metadata: Dict[str, str] = field(default_factory=dict)


def _load_pdf_reader(source: bytes | str | Path | io.BytesIO) -> PdfReader:
    if isinstance(source, (bytes, bytearray)):
        return PdfReader(io.BytesIO(source))
    if isinstance(source, io.BytesIO):
        source.seek(0)
        return PdfReader(source)
    path = Path(source)
    with path.open("rb") as fh:
        return PdfReader(fh)


def _slugify(text: str, *, default: str = "section") -> str:
    collapsed = re.sub(r"\s+", " ", text).strip().lower()
    if not collapsed:
        return default
    slug = re.sub(r"[^a-z0-9]+", "-", collapsed).strip("-")
    return slug or default


def _is_heading(line: str) -> Optional[str]:
    stripped = line.strip()
    if not stripped:
        return None
    if len(stripped) > 140:
        return None
    words = stripped.split()
    if len(words) <= 2 and stripped.isupper():
        return stripped.title()
    if re.match(r"^(chapter|section|part)\b", stripped, flags=re.IGNORECASE):
        return stripped
    numeric = re.match(r"^(\d+(?:\.\d+)*)\s+(.+)$", stripped)
    if numeric:
        return stripped
    if stripped.endswith(":") and len(words) <= 10:
        return stripped[:-1].strip()
    return None


def _infer_level(title: str) -> int:
    numeric = re.match(r"^(\d+(?:\.\d+)*)\b", title)
    if numeric:
        return len(numeric.group(1).split("."))
    lowered = title.lower()
    if lowered.startswith("chapter") or lowered.startswith("part"):
        return 1
    if lowered.startswith("section"):
        return 2
    return 3


def _iter_page_lines(pages: Sequence[PDFPage]) -> Iterable[tuple[int, str]]:
    for page in pages:
        for line in page.text.splitlines():
            yield page.index, line


def _consolidate_sections(pages: Sequence[PDFPage]) -> List[PDFSection]:
    sections: List[PDFSection] = []
    current_lines: List[str] = []
    current_title = "Document"
    current_level = 1
    current_page_start = pages[0].index if pages else 0
    heading_stack: List[str] = []
    counter = 0

    def flush(end_page: int) -> None:
        nonlocal counter, current_lines, current_title, current_level, heading_stack
        if not current_lines:
            return
        counter += 1
        section_id = f"section-{counter:04d}-{_slugify(current_title)}"
        text = "\n".join(current_lines).strip()
        sections.append(
            PDFSection(
                id=section_id,
                title=current_title,
                level=current_level,
                text=text,
                page_start=current_page_start,
                page_end=end_page,
                heading_path=tuple(heading_stack),
                metadata={
                    "section_index": str(counter - 1),
                    "title": current_title,
                    "level": str(current_level),
                },
            )
        )
        current_lines = []

    last_page_index = current_page_start

    for page_index, line in _iter_page_lines(pages):
        heading = _is_heading(line)
        if heading:
            flush(end_page=last_page_index)
            current_title = heading.strip()
            current_level = _infer_level(current_title)
            current_page_start = page_index
            heading_stack = list(heading_stack[: max(0, current_level - 1)])
            heading_stack.append(current_title)
            current_lines = []
            last_page_index = page_index
            continue
        current_lines.append(line)
        last_page_index = page_index

    flush(end_page=last_page_index)
    return sections


def load_pdf_document(
    source: bytes | str | Path | io.BytesIO,
    *,
    metadata: Optional[Dict[str, str]] = None,
) -> PDFDocument:
    reader = _load_pdf_reader(source)
    pages = [
        PDFPage(index=i + 1, text=(page.extract_text() or ""))
        for i, page in enumerate(reader.pages)
    ]
    doc_meta: Dict[str, str] = metadata.copy() if metadata else {}
    pdf_meta = getattr(reader, "metadata", None)
    if pdf_meta:
        title_value = pdf_meta.get("/Title")
        if title_value:
            doc_meta.setdefault("title", title_value)
    sections = _consolidate_sections(pages)
    return PDFDocument(
        source=str(source) if not isinstance(source, (bytes, bytearray, io.BytesIO)) else "<bytes>",
        pages=pages,
        sections=sections or [
            PDFSection(
                id="section-0000-document",
                title="Document",
                level=1,
                text="\n".join(page.text for page in pages),
                page_start=pages[0].index if pages else 0,
                page_end=pages[-1].index if pages else 0,
                heading_path=(),
                metadata={"section_index": "0", "level": "1"},
            )
        ],
        metadata=doc_meta,
    )


def decode_pdf_base64(data: str) -> bytes:
    try:
        return base64.b64decode(data)
    except Exception as exc:  # pragma: no cover - safety net
        raise ValueError("Invalid base64-encoded PDF payload") from exc
