from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel, Field, model_validator


class ExecutionLogFieldConfig(BaseModel):
    """Defines how to surface a single field in the execution log."""

    path: str = Field(..., min_length=1)
    label: Optional[str] = None
    max_chars: Optional[int] = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}


class ExecutionLogToolConfig(BaseModel):
    """Per-tool overrides for execution log extraction."""

    request: list[ExecutionLogFieldConfig] = Field(default_factory=list)
    response: list[ExecutionLogFieldConfig] = Field(default_factory=list)
    request_max_chars: Optional[int] = Field(default=None, ge=0)
    response_max_chars: Optional[int] = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}


class ExecutionLogDefaults(BaseModel):
    """Network-wide fallback truncation configuration."""

    request_max_chars: Optional[int] = Field(default=120, ge=0)
    response_max_chars: Optional[int] = Field(default=200, ge=0)

    model_config = {"extra": "forbid"}


class ExecutionLogPolicy(BaseModel):
    """Top-level execution log policy for a network."""

    defaults: ExecutionLogDefaults = Field(default_factory=ExecutionLogDefaults)
    tools: Dict[str, ExecutionLogToolConfig] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _check_tool_keys(self) -> "ExecutionLogPolicy":
        for key in self.tools.keys():
            if not key or not str(key).strip():
                raise ValueError("execution log tool key must be non-empty")
        return self

    def tool_policy(self, tool_key: str) -> Optional[ExecutionLogToolConfig]:
        """Return the policy block for a given tool, if configured."""

        if not tool_key:
            return None
        return self.tools.get(tool_key)

    def default_request_max_chars(self) -> Optional[int]:
        return self.defaults.request_max_chars

    def default_response_max_chars(self) -> Optional[int]:
        return self.defaults.response_max_chars


DEFAULT_REQUEST_PREVIEW_LIMIT = 50
DEFAULT_RESPONSE_PREVIEW_LIMIT = 100

_MISSING = object()


def _to_plain(value):
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump(mode="python")
        except TypeError:
            return value.model_dump()
    return value


def _apply_limit(text: str, limit: Optional[int]) -> str:
    if limit is None or limit == 0:
        return text
    if limit < 0:
        return text
    if len(text) <= limit:
        return text
    cutoff = max(0, limit - 1)
    return text[:cutoff] + "…"


def _stringify(value: object) -> str:
    import json

    value = _to_plain(value)
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list, tuple)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except TypeError:
            pass
    return str(value)


def _parse_path(path: str) -> list[object]:
    tokens: list[object] = []
    current: list[str] = []
    i = 0
    while i < len(path):
        ch = path[i]
        if ch == ".":
            if current:
                tokens.append("".join(current))
                current = []
            i += 1
            continue
        if ch == "[":
            if current:
                tokens.append("".join(current))
                current = []
            i += 1
            end = path.find("]", i)
            if end == -1:
                raise ValueError(f"Invalid path segment (missing ]): {path!r}")
            segment = path[i:end].strip()
            if (segment.startswith('"') and segment.endswith('"')) or (
                segment.startswith("'") and segment.endswith("'")
            ):
                tokens.append(segment[1:-1])
            else:
                try:
                    tokens.append(int(segment))
                except ValueError:
                    tokens.append(segment)
            i = end + 1
            continue
        current.append(ch)
        i += 1
    if current:
        tokens.append("".join(current))
    return tokens


def _resolve_path(payload: object, path: str):
    tokens = _parse_path(path)
    value = _traverse_tokens(payload, tokens)
    if value is _MISSING and tokens and isinstance(tokens[0], str):
        # Gracefully handle paths that prefix with synthetic roots like "result." or "response."
        trimmed = tokens[1:]
        if trimmed:
            value = _traverse_tokens(payload, trimmed)
    return value


def _traverse_tokens(payload: object, tokens: list[object]):
    current = payload
    for token in tokens:
        current = _step(current, token)
        if current is _MISSING:
            return _MISSING
    return current


def _step(current: object, token: object):
    current = _to_plain(current)
    if isinstance(token, int):
        if isinstance(current, (list, tuple)) and -len(current) <= token < len(current):
            return current[token]
        return _MISSING
    if isinstance(current, dict):
        return current.get(token, _MISSING)
    if hasattr(current, token):
        return getattr(current, token)
    return _MISSING


def _effective_limit(
    *,
    policy: Optional[ExecutionLogPolicy],
    tool_cfg: Optional[ExecutionLogToolConfig],
    side: str,
    fallback: int,
) -> int:
    if tool_cfg is not None:
        if side == "request" and tool_cfg.request_max_chars is not None:
            return tool_cfg.request_max_chars
        if side == "response" and tool_cfg.response_max_chars is not None:
            return tool_cfg.response_max_chars
    if policy is not None:
        if side == "request" and policy.defaults.request_max_chars is not None:
            return policy.defaults.request_max_chars
        if side == "response" and policy.defaults.response_max_chars is not None:
            return policy.defaults.response_max_chars
    return fallback


def _collect_pairs(
    *, payload: object, fields: list[ExecutionLogFieldConfig], default_limit: int
) -> tuple[list[tuple[str, str]], Optional[dict[str, str]]]:
    pairs: list[tuple[str, str]] = []
    excerpt: dict[str, str] = {}
    for cfg in fields:
        value = _resolve_path(payload, cfg.path)
        if value is _MISSING:
            continue
        text = _stringify(value)
        limit = cfg.max_chars if cfg.max_chars is not None else default_limit
        truncated = _apply_limit(text, limit)
        label = cfg.label or cfg.path
        pairs.append((label, truncated))
        excerpt[label] = truncated
    if not pairs:
        return [], None
    return pairs, excerpt


def build_execution_log_previews(
    *,
    policy: Optional[ExecutionLogPolicy],
    tool_key: str,
    request_payload: object,
    response_payload: object,
    fallback_request_limit: int = DEFAULT_REQUEST_PREVIEW_LIMIT,
    fallback_response_limit: int = DEFAULT_RESPONSE_PREVIEW_LIMIT,
) -> tuple[str, Optional[dict[str, str]], str, Optional[dict[str, str]]]:
    tool_cfg = policy.tool_policy(tool_key) if policy else None

    request_limit = _effective_limit(
        policy=policy,
        tool_cfg=tool_cfg,
        side="request",
        fallback=fallback_request_limit,
    )
    response_limit = _effective_limit(
        policy=policy,
        tool_cfg=tool_cfg,
        side="response",
        fallback=fallback_response_limit,
    )

    request_fields = tool_cfg.request if tool_cfg else []
    response_fields = tool_cfg.response if tool_cfg else []

    if request_fields:
        request_pairs, request_excerpt = _collect_pairs(
            payload=request_payload, fields=request_fields, default_limit=request_limit
        )
    else:
        request_pairs, request_excerpt = [], None
    if response_fields:
        response_pairs, response_excerpt = _collect_pairs(
            payload=response_payload,
            fields=response_fields,
            default_limit=response_limit,
        )
    else:
        response_pairs, response_excerpt = [], None

    if request_pairs:
        request_preview = "; ".join(
            f"{label}={value}" for label, value in request_pairs
        )
    else:
        request_preview = _apply_limit(_stringify(request_payload), request_limit)
    if response_pairs:
        response_preview = "; ".join(
            f"{label}={value}" for label, value in response_pairs
        )
    else:
        response_preview = _apply_limit(_stringify(response_payload), response_limit)

    return request_preview, request_excerpt, response_preview, response_excerpt
