from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ToolRunInput(BaseModel):
    params: Dict[str, Any]
    system: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ToolRunOutput(BaseModel):
    ok: bool = True
    result: Any = None
    error: Optional[str] = None


class ToolConfig(BaseModel):
    key: str
    provider_type: str
    params_schema: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    secret_ref: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BaseTool:
    def __init__(self, config: ToolConfig, secret_value: Optional[str] = None) -> None:
        self.config = config
        self.secret_value = secret_value

    def run(self, payload: ToolRunInput) -> ToolRunOutput:  # pragma: no cover - interface
        raise NotImplementedError
