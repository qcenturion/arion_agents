"""Tokenizer helpers for embedding models."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, List, Sequence

try:
    from transformers import AutoTokenizer, PreTrainedTokenizerBase
except ImportError as exc:  # pragma: no cover - dependency guard
    raise ImportError(
        "transformers package is required for tokenization. Install sentence-transformers extra."
    ) from exc


DEFAULT_EMBED_MODEL = os.getenv("RAG_EMBED_MODEL", "BAAI/bge-large-en")


@lru_cache(maxsize=8)
def _load_tokenizer(model_name: str) -> PreTrainedTokenizerBase:
    return AutoTokenizer.from_pretrained(model_name)


@dataclass(frozen=True)
class TokenSlice:
    """Representation of a token span."""

    start_idx: int
    end_idx: int
    tokens: List[int]


class EmbeddingTokenizer:
    """Utility wrapper that exposes token-level helpers for embedding models."""

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or DEFAULT_EMBED_MODEL
        self._tokenizer = _load_tokenizer(self.model_name)

    @property
    def tokenizer(self) -> PreTrainedTokenizerBase:
        return self._tokenizer

    @property
    def max_length(self) -> int:
        value = getattr(self._tokenizer, "model_max_length", None)
        if value and value != int(1e30):  # some tokenizers report large sentinel value
            return int(value)
        return 8192

    def encode(self, text: str) -> List[int]:
        return self._tokenizer.encode(text, add_special_tokens=False)

    def decode(self, tokens: Sequence[int]) -> str:
        return self._tokenizer.decode(tokens, skip_special_tokens=True)

    def count_tokens(self, text: str) -> int:
        return len(self.encode(text))

    def slice_tokens(
        self,
        text: str,
        chunk_size: int = 200,
        overlap: int = 20,
    ) -> List[TokenSlice]:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if overlap < 0:
            raise ValueError("overlap must be non-negative")
        if overlap >= chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")

        tokens = self.encode(text)
        total = len(tokens)
        if total == 0:
            return []

        slices: List[TokenSlice] = []
        step = chunk_size - overlap
        start = 0
        index = 0
        while start < total:
            end = min(total, start + chunk_size)
            span_tokens = tokens[start:end]
            slices.append(TokenSlice(start_idx=start, end_idx=end, tokens=span_tokens))
            index += 1
            if end == total:
                break
            start += step
        return slices

    def trim_tokens_to_limit(self, token_lists: Iterable[Sequence[int]], limit: int) -> List[int]:
        if limit <= 0:
            return []
        merged: List[int] = []
        for token_seq in token_lists:
            remaining = limit - len(merged)
            if remaining <= 0:
                break
            if len(token_seq) <= remaining:
                merged.extend(token_seq)
            else:
                merged.extend(list(token_seq)[:remaining])
                break
        return merged


def get_embedding_tokenizer(model_name: str | None = None) -> EmbeddingTokenizer:
    return EmbeddingTokenizer(model_name=model_name)
