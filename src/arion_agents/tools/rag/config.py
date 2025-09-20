"""Configuration models for the RAG service-backed tool."""
from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import urljoin

from pydantic import BaseModel, ConfigDict, Field


class RAGServiceConfig(BaseModel):
    """Connection details for the external RAG service container."""

    model_config = ConfigDict(extra="ignore")

    base_url: str = Field(..., description="Base URL for the RAG service")
    search_path: str = Field(
        default="/search",
        description="Relative path for the search endpoint",
    )
    index_path: Optional[str] = Field(
        default="/index",
        description="Relative path for the indexing endpoint (optional)",
    )
    timeout: float = Field(default=30.0, gt=0, description="Request timeout in seconds")
    headers: Dict[str, str] = Field(
        default_factory=dict,
        description="Static headers to include with every request",
    )
    default_payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Base payload merged into each search request",
    )
    api_key_header: Optional[str] = Field(
        default=None,
        description="Header name to use for the secret value when provided",
    )

    def resolve_url(self, path: Optional[str]) -> str:
        target = path or ""
        return urljoin(self.base_url.rstrip("/") + "/", target.lstrip("/"))


class HybridToolMetadata(BaseModel):
    """Top-level metadata bundle consumed by the hybrid RAG tool."""

    model_config = ConfigDict(extra="ignore")

    service: RAGServiceConfig = Field(..., description="External RAG service configuration")
    agent_params_json_schema: Dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema forwarded to the agent for validation",
    )

    @classmethod
    def from_tool_metadata(cls, metadata: dict) -> "HybridToolMetadata":
        data = metadata or {}
        # Allow nested structure under `rag` for backwards compatibility.
        if "rag" in data and isinstance(data["rag"], dict):
            rag_block = data["rag"].copy()
            rag_block.setdefault(
                "agent_params_json_schema",
                data.get("agent_params_json_schema", {}),
            )
            data = rag_block
        if "service" not in data:
            raise ValueError("rag metadata must include a 'service' block")
        return cls.model_validate(data)

    def agent_schema(self) -> Dict[str, Any]:
        return dict(self.agent_params_json_schema or {})
