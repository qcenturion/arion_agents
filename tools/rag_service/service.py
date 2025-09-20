"""Minimal RAG service for local development.

The service keeps documents in memory per collection, performs a simple
keyword-based ranking, and exposes /index and /search endpoints compatible
with the runtime's rag:hybrid tool.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("rag_service")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="RAG Dev Service")


class DocumentIn(BaseModel):
    id: str
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    collection: Optional[str] = None


class IndexRequest(BaseModel):
    documents: List[DocumentIn]


class SearchRequest(BaseModel):
    query: str
    collection: Optional[str] = None
    top_k: int = 5
    filter: Optional[Dict[str, Any]] = None


class MatchOut(BaseModel):
    id: str
    score: float
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    matches: List[MatchOut]
    context: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


_STORE: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
_DEFAULT_COLLECTION = "default"


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/index")
async def index_docs(payload: IndexRequest) -> Dict[str, Any]:
    if not payload.documents:
        raise HTTPException(status_code=400, detail="documents list is empty")

    indexed = 0
    for doc in payload.documents:
        collection = doc.collection or _DEFAULT_COLLECTION
        _STORE[collection][doc.id] = {
            "text": doc.text,
            "metadata": doc.metadata,
        }
        indexed += 1
    logger.info("Indexed %s documents across %s collections", indexed, len(_STORE))
    return {"indexed": indexed, "collections": list(_STORE.keys())}


def _score_document(query: str, text: str) -> float:
    if not text:
        return 0.0
    query_tokens = query.lower().split()
    text_lower = text.lower()
    score = 0
    for token in query_tokens:
        if token in text_lower:
            score += text_lower.count(token)
    return float(score)


@app.post("/search", response_model=SearchResponse)
async def search_docs(payload: SearchRequest) -> SearchResponse:
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")

    collection = payload.collection or _DEFAULT_COLLECTION
    docs = _STORE.get(collection, {})
    if not docs:
        logger.warning("Search requested on empty collection '%s'", collection)
    matches: List[MatchOut] = []

    for doc_id, doc in docs.items():
        score = _score_document(payload.query, doc.get("text", ""))
        if score <= 0:
            continue
        matches.append(
            MatchOut(id=doc_id, score=score, text=doc.get("text", ""), metadata=doc.get("metadata", {}))
        )

    matches.sort(key=lambda m: m.score, reverse=True)
    top_k = max(1, payload.top_k or 5)
    matches = matches[:top_k]

    context_parts = [m.text for m in matches if m.text]
    context = "\n\n".join(context_parts) if context_parts else None

    meta = {
        "collection": collection,
        "returned": len(matches),
        "available_collections": list(_STORE.keys()),
    }

    return SearchResponse(query=payload.query, matches=matches, context=context, meta=meta)
