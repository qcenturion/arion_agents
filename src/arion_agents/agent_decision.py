from __future__ import annotations

from typing import Any, Dict, Literal, Union, List, Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator

from .orchestrator import (
    Instruction,
    UseToolAction,
    RouteToAgentAction,
    RespondAction,
    TaskGroupAction,
    TaskGroupTask,
    TaskRespondAction,
    RunConfig,
)


def _strip_additional_properties(schema: dict) -> None:
    # Recursively remove any 'additionalProperties' keys from the JSON Schema
    if isinstance(schema, dict):
        schema.pop("additionalProperties", None)
        for v in list(schema.values()):
            _strip_additional_properties(v) if isinstance(v, dict) else (
                [_strip_additional_properties(i) for i in v] if isinstance(v, list) else None
            )



class UseToolDetails(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra=lambda s, _: _strip_additional_properties(s),
    )
    tool_name: str
    tool_params: Dict[str, Any] = Field(default_factory=dict)


class RouteToAgentDetails(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra=lambda s, _: _strip_additional_properties(s),
    )
    target_agent_name: str
    context: Dict[str, Any] = Field(default_factory=dict)


class RespondDetails(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra=lambda s, _: _strip_additional_properties(s),
    )
    payload: Union[Dict[str, Any], str] = Field(default_factory=dict)


class TaskGroupDetails(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra=lambda s, _: _strip_additional_properties(s),
    )
    group_id: Optional[str] = None
    tasks: List[TaskGroupTask] = Field(default_factory=list)

    @field_validator("tasks")
    @classmethod
    def _validate_tasks(cls, value: List[TaskGroupTask]) -> List[TaskGroupTask]:
        if not value:
            raise ValueError("tasks must contain at least one entry")
        return value


class TaskRespondDetails(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra=lambda s, _: _strip_additional_properties(s),
    )
    payload: Union[Dict[str, Any], str] = Field(default_factory=dict)


class AgentDecision(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra=lambda s, _: _strip_additional_properties(s),
    )
    action: Literal["USE_TOOL", "ROUTE_TO_AGENT", "RESPOND", "TASK_GROUP", "TASK_RESPOND"]
    action_reasoning: str
    action_details: Union[
        UseToolDetails,
        RouteToAgentDetails,
        RespondDetails,
        TaskGroupDetails,
        TaskRespondDetails,
    ]


def decision_to_instruction(decision: AgentDecision, cfg: RunConfig) -> Instruction:
    a = decision.action
    details = decision.action_details
    if a == "USE_TOOL":
        if not isinstance(details, UseToolDetails):
            # Coerce from raw dict if the LLM returned a plain object
            details = UseToolDetails.model_validate(details if isinstance(details, dict) else {})
        return Instruction(
            reasoning=decision.action_reasoning,
            action=UseToolAction(type="USE_TOOL", tool_name=details.tool_name, tool_params=details.tool_params),
        )
    if a == "ROUTE_TO_AGENT":
        if not isinstance(details, RouteToAgentDetails):
            # Coerce from raw dict
            details = RouteToAgentDetails.model_validate(details if isinstance(details, dict) else {})
        return Instruction(
            reasoning=decision.action_reasoning,
            action=RouteToAgentAction(
                type="ROUTE_TO_AGENT", target_agent_name=details.target_agent_name, context=details.context
            ),
        )
    if a == "TASK_GROUP":
        if not isinstance(details, TaskGroupDetails):
            details = TaskGroupDetails.model_validate(details if isinstance(details, dict) else {})
        return Instruction(
            reasoning=decision.action_reasoning,
            action=TaskGroupAction(
                type="TASK_GROUP",
                group_id=details.group_id,
                tasks=details.tasks,
            ),
        )
    if a == "TASK_RESPOND":
        if not isinstance(details, TaskRespondDetails):
            details = TaskRespondDetails.model_validate(details if isinstance(details, dict) else {})
        payload = details.payload
        if isinstance(payload, str):
            payload = {"message": payload}
        return Instruction(
            reasoning=decision.action_reasoning,
            action=TaskRespondAction(type="TASK_RESPOND", payload=payload),
        )
    # RESPOND default
    if not isinstance(details, RespondDetails):
        # Coerce from raw dict
        coerced = RespondDetails.model_validate(details if isinstance(details, dict) else {})
        details = coerced

    final_payload = details.payload
    if isinstance(final_payload, str):
        final_payload = {"message": final_payload}

    return Instruction(
        reasoning=decision.action_reasoning,
        action=RespondAction(type="RESPOND", payload=final_payload),
    )
