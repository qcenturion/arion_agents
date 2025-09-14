from __future__ import annotations

from typing import Any, Dict, Literal

from pydantic import BaseModel, ValidationError

from .orchestrator import (
    Instruction,
    UseToolAction,
    RouteToAgentAction,
    RespondAction,
    RunConfig,
)


class AgentDecision(BaseModel):
    action: Literal["USE_TOOL", "ROUTE_TO_AGENT", "RESPOND"]
    action_reasoning: str
    action_details: Dict[str, Any]


def decision_to_instruction(decision: AgentDecision, cfg: RunConfig) -> Instruction:
    a = decision.action
    details = decision.action_details or {}
    if a == "USE_TOOL":
        tool = details.get("tool_name") or details.get("tool")
        params = details.get("tool_params") or details.get("params") or {}
        if not isinstance(params, dict):
            raise ValidationError(["tool_params must be an object"], AgentDecision)
        return Instruction(reasoning=decision.action_reasoning, action=UseToolAction(type="USE_TOOL", tool_name=str(tool or ""), tool_params=params))
    if a == "ROUTE_TO_AGENT":
        target = details.get("target_agent_name") or details.get("agent")
        ctx = details.get("context") or {}
        if not isinstance(ctx, dict):
            ctx = {}
        return Instruction(reasoning=decision.action_reasoning, action=RouteToAgentAction(type="ROUTE_TO_AGENT", target_agent_name=str(target or ""), context=ctx))
    # RESPOND default
    payload = details.get("payload") if "payload" in details else details or {}
    return Instruction(reasoning=decision.action_reasoning, action=RespondAction(type="RESPOND", payload=payload))

