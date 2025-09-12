from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class UseToolAction(BaseModel):
    type: Literal["USE_TOOL"]
    tool_name: str
    tool_params: Dict[str, Any] = Field(default_factory=dict)


class RouteToAgentAction(BaseModel):
    type: Literal["ROUTE_TO_AGENT"]
    target_agent_name: str
    context: Dict[str, Any] = Field(default_factory=dict)


class RespondAction(BaseModel):
    type: Literal["RESPOND"]
    payload: Any


Action = Union[UseToolAction, RouteToAgentAction, RespondAction]


class Instruction(BaseModel):
    reasoning: str
    action: Action


class OrchestratorResult(BaseModel):
    status: Literal["ok", "not_implemented", "retry", "error"]
    response: Optional[Any] = None
    next_agent: Optional[str] = None
    error: Optional[str] = None


class ToolParamSpec(BaseModel):
    name: str
    source: Literal["agent", "system"] = "agent"
    required: bool = False
    default: Optional[Any] = None


class ToolSpec(BaseModel):
    name: str
    description: Optional[str] = None
    params: List[ToolParamSpec] = Field(default_factory=list)


# Minimal registry for validation only (no actual execution yet)
TOOL_REGISTRY: Dict[str, ToolSpec] = {
    "TemplateRetrievalTool": ToolSpec(
        name="TemplateRetrievalTool",
        description="Fetch pre-written response template by intent",
        params=[
            ToolParamSpec(name="intent", source="agent", required=True),
            ToolParamSpec(name="customer_id", source="system", required=True),
        ],
    ),
}


class RunConfig(BaseModel):
    current_agent: str
    equipped_tools: List[str]
    allowed_routes: List[str]
    allow_respond: bool = True
    system_params: Dict[str, Any] = Field(default_factory=dict)


def execute_instruction(instr: Instruction, cfg: Optional[RunConfig] = None) -> OrchestratorResult:
    # RESPOND
    if isinstance(instr.action, RespondAction):
        if cfg and not cfg.allow_respond:
            return OrchestratorResult(
                status="retry",
                error="RESPOND not permitted for current agent",
            )
        return OrchestratorResult(status="ok", response=instr.action.payload)

    # USE_TOOL
    if isinstance(instr.action, UseToolAction):
        if cfg and instr.action.tool_name not in set(cfg.equipped_tools):
            return OrchestratorResult(
                status="retry",
                error=f"Tool '{instr.action.tool_name}' not permitted for agent {cfg.current_agent}",
            )
        spec = TOOL_REGISTRY.get(instr.action.tool_name)
        if not spec:
            return OrchestratorResult(status="retry", error=f"Unknown tool '{instr.action.tool_name}'")

        # Validate parameters against spec
        params = instr.action.tool_params or {}
        # Agent must not set system-provided params
        system_param_names = {p.name for p in spec.params if p.source == "system"}
        forbidden = system_param_names.intersection(params.keys())
        if forbidden:
            return OrchestratorResult(
                status="retry",
                error=f"System params must not be provided by agent: {sorted(forbidden)}",
            )
        # Ensure required params
        missing_agent = [p.name for p in spec.params if p.source == "agent" and p.required and p.name not in params]
        if missing_agent:
            return OrchestratorResult(status="retry", error=f"Missing required params: {missing_agent}")

        # Merge system params from cfg
        merged = dict(params)
        if cfg:
            for p in spec.params:
                if p.source == "system":
                    if p.required and p.name not in cfg.system_params:
                        return OrchestratorResult(status="error", error=f"Missing system param: {p.name}")
                    if p.name in cfg.system_params:
                        merged[p.name] = cfg.system_params[p.name]
        # Defaults
        for p in spec.params:
            if p.default is not None and p.name not in merged:
                merged[p.name] = p.default

        # Placeholder execution
        return OrchestratorResult(status="not_implemented")

    # ROUTE_TO_AGENT
    if isinstance(instr.action, RouteToAgentAction):
        if cfg and instr.action.target_agent_name not in set(cfg.allowed_routes):
            return OrchestratorResult(
                status="retry",
                error=f"Route to '{instr.action.target_agent_name}' not permitted",
            )
        return OrchestratorResult(status="not_implemented", next_agent=instr.action.target_agent_name)

    return OrchestratorResult(status="not_implemented")
