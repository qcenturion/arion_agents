from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CompiledTool(BaseModel):
    key: str
    provider_type: str
    params_schema: Dict[str, Any] = Field(default_factory=dict)
    secret_ref: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    description: Optional[str] = None


class CompiledAgent(BaseModel):
    key: str
    allow_respond: bool = True
    equipped_tools: List[str] = Field(default_factory=list)
    allowed_routes: List[str] = Field(default_factory=list)
    prompt: Optional[str] = None


class CompiledGraph(BaseModel):
    version_id: Optional[int] = None
    default_agent_key: Optional[str] = None
    agents: List[CompiledAgent] = Field(default_factory=list)
    tools: List[CompiledTool] = Field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return self.model_dump()
