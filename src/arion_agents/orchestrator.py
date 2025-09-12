from __future__ import annotations

from typing import Any, Dict, Literal, Optional, Union

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
    status: Literal["ok", "not_implemented"]
    response: Optional[Any] = None
    next_agent: Optional[str] = None


def execute_instruction(instr: Instruction) -> OrchestratorResult:
    # Minimal executor for POC: RESPOND ends; others are placeholders
    if isinstance(instr.action, RespondAction):
        return OrchestratorResult(status="ok", response=instr.action.payload)
    if isinstance(instr.action, UseToolAction):
        # TODO: integrate tool registry and permissions
        return OrchestratorResult(status="not_implemented")
    if isinstance(instr.action, RouteToAgentAction):
        # TODO: enforce allowed_routes and route control
        return OrchestratorResult(status="not_implemented", next_agent=instr.action.target_agent_name)
    return OrchestratorResult(status="not_implemented")

