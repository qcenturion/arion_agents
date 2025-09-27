from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, ConfigDict, field_validator

from arion_agents.logs.execution_log_policy import ExecutionLogPolicy


class UseToolAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["USE_TOOL"]
    tool_name: str
    tool_params: Dict[str, Any] = Field(default_factory=dict)


class RouteToAgentAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["ROUTE_TO_AGENT"]
    target_agent_name: str
    context: Dict[str, Any] = Field(default_factory=dict)


class RespondAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["RESPOND"]
    payload: Any


class TaskRetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempts: int = Field(default=2, ge=1)


class DelegationDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_key: str
    assignment: str
    context_overrides: Dict[str, Any] = Field(default_factory=dict)
    max_steps: int = Field(default=5, ge=1)
    max_tokens: Optional[int] = None


class TaskGroupTaskBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: Optional[str] = None
    retry_policy: TaskRetryPolicy = Field(default_factory=TaskRetryPolicy)


class TaskGroupUseTool(TaskGroupTaskBase):
    task_type: Literal["use_tool"]
    tool_name: str
    tool_params: Dict[str, Any] = Field(default_factory=dict)


class TaskGroupDelegate(TaskGroupTaskBase):
    task_type: Literal["delegate_agent"]
    delegation_details: List[DelegationDetails] = Field(default_factory=list)

    @field_validator("delegation_details")
    @classmethod
    def _validate_details(
        cls, value: List[DelegationDetails]
    ) -> List[DelegationDetails]:
        if not value:
            raise ValueError("delegation_details must contain at least one assignment")
        return value


TaskGroupTask = Union[TaskGroupUseTool, TaskGroupDelegate]


class TaskGroupAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["TASK_GROUP"]
    group_id: Optional[str] = None
    tasks: List[TaskGroupTask] = Field(default_factory=list)

    @field_validator("tasks")
    @classmethod
    def _validate_tasks(cls, value: List[TaskGroupTask]) -> List[TaskGroupTask]:
        if not value:
            raise ValueError("Task group must contain at least one task")
        return value


class TaskRespondAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["TASK_RESPOND"]
    payload: Any


Action = Union[
    UseToolAction,
    RouteToAgentAction,
    RespondAction,
    TaskGroupAction,
    TaskRespondAction,
]


class Instruction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reasoning: str
    action: Action


class OrchestratorResult(BaseModel):
    status: Literal["ok", "not_implemented", "retry", "error"]
    response: Optional[Any] = None
    next_agent: Optional[str] = None
    error: Optional[str] = None


class ToolRuntimeSpec(BaseModel):
    key: str
    provider_type: str
    params_schema: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    secret_ref: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RunConfig(BaseModel):
    current_agent: str
    equipped_tools: List[str]
    tools_map: Dict[str, ToolRuntimeSpec] = Field(default_factory=dict)
    allowed_routes: List[str]
    route_descriptions: Dict[str, str] = Field(default_factory=dict)
    allow_respond: bool = True
    allow_task_group: bool = False
    allow_task_respond: bool = False
    system_params: Dict[str, Any] = Field(default_factory=dict)
    prompt: Optional[str] = None
    respond_payload_schema: Optional[Dict[str, Any]] = None
    respond_payload_guidance: Optional[str] = None
    respond_payload_example: Optional[Dict[str, Any]] = None
    display_name: Optional[str] = None
    execution_log_policy: Optional[ExecutionLogPolicy] = None


def execute_instruction(
    instr: Instruction, cfg: Optional[RunConfig] = None
) -> OrchestratorResult:
    # RESPOND
    if isinstance(instr.action, RespondAction):
        if cfg and not cfg.allow_respond:
            return OrchestratorResult(
                status="retry",
                error="RESPOND not permitted for current agent",
            )
        return OrchestratorResult(status="ok", response=instr.action.payload)

    # TASK_RESPOND
    if isinstance(instr.action, TaskRespondAction):
        if cfg and not cfg.allow_task_respond:
            return OrchestratorResult(
                status="retry",
                error="TASK_RESPOND not permitted for current agent",
            )
        return OrchestratorResult(status="ok", response=instr.action.payload)

    # USE_TOOL
    if isinstance(instr.action, UseToolAction):
        if cfg and instr.action.tool_name not in set(cfg.equipped_tools):
            return OrchestratorResult(
                status="retry",
                error=f"Tool '{instr.action.tool_name}' not permitted for agent {cfg.current_agent}",
            )
        # Lookup tool runtime spec
        tspec: Optional[ToolRuntimeSpec] = None
        if cfg:
            tspec = cfg.tools_map.get(instr.action.tool_name)
        if not tspec:
            return OrchestratorResult(
                status="retry",
                error=f"Tool '{instr.action.tool_name}' is not configured",
            )

        # Validate parameters against runtime params_schema
        # params_schema format: { name: { source: 'agent'|'system', required: bool, default?: any } }
        schema = tspec.params_schema or {}
        params = dict(instr.action.tool_params or {})

        # Agent must not supply system-provided params
        system_names = {
            k for k, v in schema.items() if (v or {}).get("source") == "system"
        }
        forbidden = sorted(system_names.intersection(params.keys()))
        if forbidden:
            return OrchestratorResult(
                status="retry",
                error=f"System params must not be provided by agent: {forbidden}",
            )

        # Ensure required agent params
        missing_agent = sorted(
            [
                k
                for k, v in schema.items()
                if (v or {}).get("source", "agent") == "agent"
                and (v or {}).get("required")
                and k not in params
            ]
        )
        if missing_agent:
            return OrchestratorResult(
                status="retry", error=f"Missing required params: {missing_agent}"
            )

        # Merge system params and defaults
        merged: Dict[str, Any] = dict(params)
        if cfg:
            for k, v in schema.items():
                src = (v or {}).get("source", "agent")
                if src == "system":
                    if (v or {}).get("required") and k not in cfg.system_params:
                        return OrchestratorResult(
                            status="error", error=f"Missing system param: {k}"
                        )
                    if k in cfg.system_params:
                        merged[k] = cfg.system_params[k]
                # defaults
                if (v or {}).get("default") is not None and k not in merged:
                    merged[k] = v.get("default")

        # Optional JSON Schema validation for agent-visible params
        try:
            # If tool metadata includes a JSON Schema for agent params, validate here
            from jsonschema import validate as _js_validate  # type: ignore
            from jsonschema import ValidationError as _JSValidationError  # type: ignore

            meta_schema = getattr(tspec, "metadata", None) or {}
            agent_params_schema = None
            if isinstance(meta_schema, dict):
                agent_params_schema = meta_schema.get("agent_params_json_schema")
            if agent_params_schema:
                try:
                    _js_validate(instance=params, schema=agent_params_schema)
                except _JSValidationError as ve:  # pragma: no cover
                    return OrchestratorResult(
                        status="retry",
                        error=f"tool_params do not match schema: {ve.message}",
                    )
        except Exception:
            # jsonschema not available or unexpected error; proceed with built-in validation
            pass

        # Execute via registry
        try:
            from arion_agents.tools.base import ToolConfig as _ToolConfig, ToolRunInput
            from arion_agents.tools.registry import instantiate_tool
            from arion_agents.secrets import resolve_secret

            tool_cfg = _ToolConfig(
                key=tspec.key,
                provider_type=tspec.provider_type,
                params_schema=tspec.params_schema,
                secret_ref=tspec.secret_ref,
                metadata=tspec.metadata,
            )
            secret_value = resolve_secret(tspec.secret_ref)
            tool = instantiate_tool(tool_cfg, secret_value)
            import time

            t0 = time.perf_counter()
            out = tool.run(
                ToolRunInput(
                    params=merged, system=cfg.system_params, metadata=tspec.metadata
                )
            )
            dur_ms = int((time.perf_counter() - t0) * 1000)
            if out.ok:
                return OrchestratorResult(
                    status="ok",
                    response={
                        "tool": tspec.key,
                        "params": merged,
                        "result": out.result,
                        "duration_ms": dur_ms,
                    },
                )
            return OrchestratorResult(status="error", error=out.error or "tool error")
        except Exception as e:
            return OrchestratorResult(
                status="error", error=f"tool execution failed: {e}"
            )

    # ROUTE_TO_AGENT
    if isinstance(instr.action, RouteToAgentAction):
        if cfg and instr.action.target_agent_name not in set(cfg.allowed_routes):
            return OrchestratorResult(
                status="retry",
                error=f"Route to '{instr.action.target_agent_name}' not permitted",
            )
        return OrchestratorResult(
            status="not_implemented", next_agent=instr.action.target_agent_name
        )

    return OrchestratorResult(status="not_implemented")
