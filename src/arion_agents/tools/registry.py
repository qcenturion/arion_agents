from __future__ import annotations

from typing import Any, Dict, Optional, Type

from pydantic import BaseModel, Field, ConfigDict, field_validator

from .base import BaseTool, ToolConfig, ToolRunInput, ToolRunOutput


class EchoTool(BaseTool):
    """Built-in helper that simply echoes inputs (provider_type: builtin:echo)."""

    def run(self, payload: ToolRunInput) -> ToolRunOutput:
        return ToolRunOutput(
            ok=True,
            result={
                "echo": payload.params,
                "system": payload.system,
                "metadata": payload.metadata,
            },
        )


class HTTPParamSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = "agent"
    name: Optional[str] = None
    default: Any = None
    value: Any = None
    prefix: Optional[str] = None

    @field_validator("source")
    @classmethod
    def _normalize_source(cls, value: str) -> str:
        v = (value or "agent").strip().lower()
        if v not in {"agent", "system", "const", "secret"}:
            raise ValueError(f"Unsupported source '{value}'")
        return v


class HTTPResponseSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unwrap: Optional[str] = None
    keys: Optional[list[str]] = None


class HTTPToolSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: str = "GET"
    base_url: Optional[str] = None
    path: Optional[str] = None
    url: Optional[str] = None
    timeout: float = 15.0
    query: Dict[str, HTTPParamSpec] = Field(default_factory=dict)
    headers: Dict[str, HTTPParamSpec] = Field(default_factory=dict)
    body: Optional[Dict[str, Any]] = None
    response: HTTPResponseSpec = Field(default_factory=HTTPResponseSpec)

    @field_validator("method")
    @classmethod
    def _normalize_method(cls, value: str) -> str:
        return (value or "GET").strip().upper()

    def resolved_url(self) -> str:
        if self.url:
            return self.url
        base = (self.base_url or "").rstrip("/")
        path = (self.path or "").lstrip("/")
        if base and path:
            return f"{base}/{path}"
        if path and not base:
            return path
        if base and not path:
            return base
        raise ValueError("HTTP tool requires either url or base_url/path")


class HttpRequestTool(BaseTool):
    """Generic HTTP executor driven by HTTPToolSpec metadata.

    Each tool instance is configured via ToolConfig.metadata. The metadata may be
    specified directly as the HTTP schema or nested under the `http` key. This
    keeps older snapshots compatible while encouraging structured configs.
    """

    def run(self, payload: ToolRunInput) -> ToolRunOutput:
        import requests

        raw_meta = self.config.metadata or {}
        if "http" in raw_meta and isinstance(raw_meta["http"], dict):
            spec_source = raw_meta["http"]
        else:
            spec_source = {
                k: v
                for k, v in raw_meta.items()
                if k not in {"agent_params_json_schema", "description"}
            } or raw_meta
        try:
            spec = HTTPToolSpec.model_validate(spec_source)
        except Exception as exc:  # pragma: no cover - defensive validation message
            return ToolRunOutput(ok=False, error=f"invalid http spec: {exc}")

        try:
            url = spec.resolved_url()
        except ValueError as exc:
            return ToolRunOutput(ok=False, error=str(exc))

        query_params = self._build_params(spec.query, payload)
        headers = self._build_params(spec.headers, payload)

        try:
            if spec.method == "GET":
                resp = requests.get(
                    url, params=query_params, headers=headers, timeout=spec.timeout
                )
            elif spec.method == "POST":
                resp = requests.post(
                    url,
                    params=query_params,
                    headers=headers,
                    json=self._build_body(spec.body or {}, payload),
                    timeout=spec.timeout,
                )
            elif spec.method == "DELETE":
                resp = requests.delete(
                    url, params=query_params, headers=headers, timeout=spec.timeout
                )
            elif spec.method == "PUT":
                resp = requests.put(
                    url,
                    params=query_params,
                    headers=headers,
                    json=self._build_body(spec.body or {}, payload),
                    timeout=spec.timeout,
                )
            else:
                return ToolRunOutput(
                    ok=False, error=f"unsupported http method: {spec.method}"
                )
            resp.raise_for_status()
            data = self._shape_response(resp, spec)
            return ToolRunOutput(ok=True, result=data)
        except Exception as exc:
            return ToolRunOutput(ok=False, error=str(exc))

    def _build_params(
        self, spec: Dict[str, HTTPParamSpec], payload: ToolRunInput
    ) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for key, param in spec.items():
            value = self._resolve_param_value(key, param, payload)
            if value is not None:
                out[param.name or key] = value
        return out

    def _resolve_param_value(
        self, key: str, param: HTTPParamSpec, payload: ToolRunInput
    ) -> Any:
        source = param.source
        if source == "agent":
            if key in payload.params:
                return payload.params[key]
            return param.default
        if source == "system":
            lookup = param.name or key
            if lookup in payload.system:
                prefix = param.prefix or ""
                return f"{prefix}{payload.system[lookup]}"
            return param.default
        if source == "const":
            return param.value if param.value is not None else param.default
        if source == "secret":
            if self.secret_value is not None:
                prefix = param.prefix or ""
                return f"{prefix}{self.secret_value}"
            return param.default
        return None

    def _build_body(
        self, body_spec: Dict[str, Any], payload: ToolRunInput
    ) -> Dict[str, Any]:
        # Allow body spec to mirror the query/header pattern for dynamic values.
        if not body_spec:
            return {}
        resolved: Dict[str, Any] = {}
        for key, value in body_spec.items():
            if isinstance(value, dict) and "source" in value:
                param = HTTPParamSpec.model_validate(value)
                resolved[key] = self._resolve_param_value(key, param, payload)
            else:
                resolved[key] = value
        return resolved

    def _shape_response(self, response, spec: HTTPToolSpec) -> Any:
        data = response.json()
        shape = spec.response
        if shape.unwrap and isinstance(data, dict):
            data = data.get(shape.unwrap)
        if shape.keys and isinstance(data, dict):
            data = {k: data.get(k) for k in shape.keys}
        return data


PROVIDERS: Dict[str, Type[BaseTool]] = {
    "builtin:echo": EchoTool,
    "http:request": HttpRequestTool,
}


def instantiate_tool(cfg: ToolConfig, secret_value: Optional[str]) -> BaseTool:
    cls = PROVIDERS.get(cfg.provider_type)
    if not cls:
        raise ValueError(f"No provider for type '{cfg.provider_type}'")
    return cls(cfg, secret_value)
