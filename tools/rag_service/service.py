"""Persistent RAG service backed by embedded Qdrant and BGE embeddings."""
from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from sentence_transformers import SentenceTransformer

# Configure logging before other imports create loggers.
import logging


logger = logging.getLogger("rag_service")
logging.basicConfig(level=logging.INFO)


DEFAULT_COLLECTION = os.getenv("RAG_DEFAULT_COLLECTION", "city_activities")
CONFIGURED_COLLECTIONS: Sequence[str] = tuple(
    filter(
        None,
        (name.strip() for name in os.getenv("RAG_COLLECTIONS", DEFAULT_COLLECTION).split(",")),
    )
)

if not CONFIGURED_COLLECTIONS:
    raise RuntimeError("RAG_COLLECTIONS resolved to an empty list; configure at least one collection")

EMBED_MODEL_NAME = os.getenv("RAG_EMBED_MODEL", "BAAI/bge-large-en")
EMBED_BATCH_SIZE = int(os.getenv("RAG_EMBED_BATCH", "16"))
EMBED_NORMALIZE = os.getenv("RAG_EMBED_NORMALIZE", "true").lower() not in {"0", "false", "no"}

_storage_path = Path(os.getenv("RAG_QDRANT_PATH", "./data/qdrant")).resolve()
_storage_path.mkdir(parents=True, exist_ok=True)


logger.info("Starting RAG service with storage at %s", _storage_path)


_client: Optional[QdrantClient] = None
_embedder: Optional[SentenceTransformer] = None
_vector_size: Optional[int] = None
_ready_collections: set[str] = set()


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


from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context."""
    logger.info("Executing application startup logic.")
    # Ensure dependencies are ready before serving traffic.
    get_embedder()
    for collection in CONFIGURED_COLLECTIONS:
        ensure_collection(collection)
    logger.info("Startup complete.")
    yield
    # No shutdown logic needed.


app = FastAPI(title="RAG Dev Service", lifespan=lifespan)


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        logger.info("Initialising embedded Qdrant client at %s", _storage_path)
        logger.info("--> Calling QdrantClient constructor...")
        _client = QdrantClient(path=str(_storage_path), prefer_grpc=False)
        logger.info("--> QdrantClient constructor returned.")
    return _client


def get_embedder() -> SentenceTransformer:
    global _embedder, _vector_size
    if _embedder is None:
        logger.info("Loading embedding model %s", EMBED_MODEL_NAME)
        logger.info("--> Calling SentenceTransformer constructor...")
        _embedder = SentenceTransformer(EMBED_MODEL_NAME)
        logger.info("--> SentenceTransformer constructor returned.")
        _vector_size = int(_embedder.get_sentence_embedding_dimension())
        logger.info("Embedding dimension: %s", _vector_size)
    return _embedder


def _vector_dim() -> int:
    if _vector_size is None:
        get_embedder()
    assert _vector_size is not None
    return _vector_size


def ensure_collection(name: str) -> None:
    if name in _ready_collections:
        return

    client = get_client()
    dim = _vector_dim()

    try:
        existing = client.get_collection(name)
    except Exception:  # collection missing
        logger.info("Creating Qdrant collection %s", name)
        client.create_collection(
            collection_name=name,
            vectors_config=qmodels.VectorParams(size=dim, distance=qmodels.Distance.COSINE),
        )
        _ready_collections.add(name)
        return

    current = existing.config.params
    if not current or not current.vectors:
        raise RuntimeError(f"Collection {name} exists but lacks vector configuration")

    size = getattr(current.vectors, "size", None)
    if size != dim:
        raise RuntimeError(
            f"Collection {name} vector size {size} != embedding dim {dim}; recreate collection"
        )

    metric = getattr(current.vectors, "distance", None)
    if metric and metric != qmodels.Distance.COSINE:
        logger.warning(
            "Collection %s uses distance %s, expected cosine; continuing", name, metric
        )
    _ready_collections.add(name)


def _encode_texts(texts: Sequence[str]) -> np.ndarray:
    embedder = get_embedder()
    vectors = embedder.encode(
        list(texts),
        batch_size=EMBED_BATCH_SIZE,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=EMBED_NORMALIZE,
    )
    return vectors


def _transform_filter(raw_filter: Optional[Dict[str, Any]]) -> Optional[qmodels.Filter]:
    if not raw_filter:
        return None
    conditions: List[qmodels.FieldCondition] = []
    for key, value in raw_filter.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            conditions.append(
                qmodels.FieldCondition(key=key, match=qmodels.MatchValue(value=value))
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported filter value for key '{key}': {type(value).__name__}",
            )
    if not conditions:
        return None
    return qmodels.Filter(must=conditions)


def _validate_collection(name: str) -> str:
    if name not in CONFIGURED_COLLECTIONS:
        configured = ", ".join(CONFIGURED_COLLECTIONS)
        raise HTTPException(
            status_code=400,
            detail=f"Collection '{name}' is not configured. Allowed collections: {configured}",
        )
    ensure_collection(name)
    return name




@app.get("/health")
async def health() -> Dict[str, Any]:
    try:
        client = get_client()
        stats = {
            name: client.count(collection_name=name).count for name in CONFIGURED_COLLECTIONS
        }
        return {
            "status": "ok",
            "collections": stats,
            "vector_dim": _vector_dim(),
            "model": EMBED_MODEL_NAME,
        }
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Health check failed: %s", exc)
        return {"status": "error", "detail": str(exc)}


@app.post("/index")
async def index_docs(payload: IndexRequest) -> Dict[str, Any]:
    if not payload.documents:
        raise HTTPException(status_code=400, detail="documents list is empty")

    grouped: Dict[str, List[DocumentIn]] = defaultdict(list)
    for doc in payload.documents:
        collection = _validate_collection(doc.collection or DEFAULT_COLLECTION)
        grouped[collection].append(doc)

    client = get_client()
    total = 0

    for collection, docs in grouped.items():
        vectors = _encode_texts([doc.text for doc in docs])
        points = []
        for doc, vector in zip(docs, vectors):
            payload_dict = {
                "text": doc.text,
                "metadata": doc.metadata,
            }
            points.append(
                qmodels.PointStruct(
                    id=doc.id,
                    vector=vector.astype(float).tolist(),
                    payload=payload_dict,
                )
            )
        client.upsert(collection_name=collection, points=points)
        total += len(points)
        logger.info("Indexed %s documents into %s", len(points), collection)

    return {"indexed": total, "collections": list(grouped.keys())}


@app.post("/search", response_model=SearchResponse)
async def search_docs(payload: SearchRequest) -> SearchResponse:
    if not payload.query or not payload.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")

    collection = _validate_collection(payload.collection or DEFAULT_COLLECTION)
    top_k = max(1, payload.top_k or 5)
    vector = _encode_texts([payload.query])[0]
    filter_ = _transform_filter(payload.filter)

    client = get_client()
    results = client.search(
        collection_name=collection,
        query_vector=vector.astype(float).tolist(),
        limit=top_k,
        with_payload=True,
        query_filter=filter_,
    )

    matches: List[MatchOut] = []
    for point in results:
        payload_dict = point.payload or {}
        matches.append(
            MatchOut(
                id=str(point.id),
                score=float(point.score or 0.0),
                text=payload_dict.get("text", ""),
                metadata=payload_dict.get("metadata") or {},
            )
        )

    context_parts = [match.text for match in matches if match.text]
    context = "\n\n".join(context_parts) if context_parts else None

    meta = {
        "collection": collection,
        "returned": len(matches),
        "available_collections": list(CONFIGURED_COLLECTIONS),
        "vector_dim": _vector_dim(),
        "model": EMBED_MODEL_NAME,
    }

    return SearchResponse(query=payload.query, matches=matches, context=context, meta=meta)
