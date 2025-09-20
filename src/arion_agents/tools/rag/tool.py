"""RAG tool that delegates search to an external service container."""
from __future__ import annotations

from typing import Any, Dict, Optional

import requests

from arion_agents.tools.base import BaseTool, ToolRunInput, ToolRunOutput

from .config import HybridToolMetadata


class HybridRAGTool(BaseTool):
    """Proxy queries to an external RAG service over HTTP."""

    def __init__(self, config, secret_value: Optional[str] = None) -> None:
        super().__init__(config, secret_value)
        self._metadata: Optional[HybridToolMetadata] = None

    @property
    def metadata(self) -> HybridToolMetadata:
        if self._metadata is None:
            raw_meta = self.config.metadata or {}
            self._metadata = HybridToolMetadata.from_tool_metadata(raw_meta)
        return self._metadata

    def _build_headers(self) -> Dict[str, str]:
        headers = dict(self.metadata.service.headers)
        if self.metadata.service.api_key_header and self.secret_value:
            headers[self.metadata.service.api_key_header] = self.secret_value
        return headers

    def run(self, payload: ToolRunInput) -> ToolRunOutput:
        params = payload.params or {}
        query = params.get("query")
        if not query or not isinstance(query, str):
            return ToolRunOutput(ok=False, error="query parameter is required")

        top_k = params.get("top_k")
        if top_k is not None:
            try:
                top_k = max(1, int(top_k))
            except Exception:
                return ToolRunOutput(ok=False, error="top_k must be an integer")
        filter_dict = params.get("filter")
        if filter_dict is not None and not isinstance(filter_dict, dict):
            return ToolRunOutput(
                ok=False, error="filter must be an object compatible with the service"
            )

        service = self.metadata.service
        url = service.resolve_url(service.search_path)
        body: Dict[str, Any] = dict(service.default_payload)
        body.update({"query": query})
        if top_k is not None:
            body["top_k"] = top_k
        if filter_dict is not None:
            body["filter"] = filter_dict
        if payload.system:
            body.setdefault("system_params", payload.system)

        try:
            response = requests.post(
                url,
                json=body,
                headers=self._build_headers(),
                timeout=service.timeout,
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                return ToolRunOutput(
                    ok=False,
                    error="RAG service returned a non-object response",
                )
            return ToolRunOutput(ok=True, result=data)
        except requests.RequestException as exc:
            return ToolRunOutput(ok=False, error=f"rag service error: {exc}")
        except Exception as exc:  # pragma: no cover - safety net
            return ToolRunOutput(
                ok=False, error=f"unexpected rag service error: {exc}"
            )
