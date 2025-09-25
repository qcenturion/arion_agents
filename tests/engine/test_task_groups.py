from collections import deque
from typing import Any, Callable, Dict, List

from arion_agents.agent_decision import (
    AgentDecision,
    RespondDetails,
    TaskGroupDetails,
    TaskRespondDetails,
)
from arion_agents.engine.loop import run_loop
from arion_agents.llm import GeminiDecideResult
from arion_agents.orchestrator import (
    DelegationDetails,
    RunConfig,
    TaskGroupDelegate,
    TaskGroupUseTool,
    TaskRetryPolicy,
    ToolRuntimeSpec,
)
from arion_agents.tools.base import BaseTool, ToolConfig, ToolRunInput, ToolRunOutput
from arion_agents.tools.registry import PROVIDERS


def _make_decide_fn(decisions: List[AgentDecision]) -> Callable[[str, str | None], GeminiDecideResult]:
    queue = deque(decisions)

    def decide(_: str, __: str | None) -> GeminiDecideResult:
        if not queue:
            raise AssertionError("No more decisions available for decide_fn")
        decision = queue.popleft()
        return GeminiDecideResult(
            text="",
            parsed=decision,
            usage=None,
            usage_raw=None,
            response_payload=None,
        )

    decide.remaining = queue  # type: ignore[attr-defined]
    return decide


def _tool_spec(key: str, provider: str) -> ToolRuntimeSpec:
    return ToolRuntimeSpec(key=key, provider_type=provider, params_schema={}, metadata={})


def test_task_group_success_with_delegation() -> None:
    primary_cfg = RunConfig(
        current_agent="primary",
        equipped_tools=["echo"],
        tools_map={"echo": _tool_spec("echo", "builtin:echo")},
        allowed_routes=[],
        allow_respond=True,
        allow_task_group=True,
        allow_task_respond=False,
        system_params={},
        prompt=None,
    )
    child_cfg = RunConfig(
        current_agent="child",
        equipped_tools=[],
        tools_map={},
        allowed_routes=[],
        allow_respond=False,
        allow_task_group=False,
        allow_task_respond=True,
        system_params={},
        prompt=None,
    )

    decisions = [
        AgentDecision(
            action="TASK_GROUP",
            action_reasoning="plan tasks",
            action_details=TaskGroupDetails(
                group_id="group-1",
                tasks=[
                    TaskGroupUseTool(
                        task_type="use_tool",
                        task_id="echo-task",
                        tool_name="echo",
                        tool_params={"message": "hello"},
                    ),
                    TaskGroupDelegate(
                        task_type="delegate_agent",
                        task_id="delegate-task",
                        delegation_details=[
                            DelegationDetails(
                                agent_key="child",
                                assignment="Summarize the document section",
                                context_overrides={},
                                max_steps=3,
                            )
                        ],
                    ),
                ],
            ),
        ),
        AgentDecision(
            action="TASK_RESPOND",
            action_reasoning="finished",
            action_details=TaskRespondDetails(payload={"message": "delegated done"}),
        ),
        AgentDecision(
            action="RESPOND",
            action_reasoning="complete",
            action_details=RespondDetails(payload={"message": "all done"}),
        ),
    ]

    decide_fn = _make_decide_fn(decisions)

    def _get_cfg(agent_key: str) -> RunConfig:
        if agent_key == "primary":
            return primary_cfg
        if agent_key == "child":
            return child_cfg
        raise AssertionError(f"Unexpected agent {agent_key}")

    result = run_loop(
        _get_cfg,
        default_agent_key="primary",
        user_message="Process the document",
        max_steps=5,
        decide_fn=decide_fn,
        model=None,
        debug=False,
    )

    assert not decide_fn.remaining  # type: ignore[attr-defined]
    final = result["final"]
    assert final["status"] == "ok"
    assert final["response"]["message"] == "all done"

    task_groups = [e for e in result["execution_log"] if e.get("type") == "task_group"]
    assert len(task_groups) == 1
    task_group_entry = task_groups[0]
    assert task_group_entry["status"] == "ok"
    assert task_group_entry["group_id"] == "group-1"
    assert task_group_entry["tasks"][0]["status"] == "ok"
    assert task_group_entry["tasks"][1]["status"] == "ok"
    delegation_result = task_group_entry["tasks"][1].get("result")
    assert isinstance(delegation_result, list)
    assert delegation_result[0]["message"] == "delegated done"

    # Ensure tool log entry is associated with the task group
    tool_logs: Dict[str, Dict[str, Any]] = result["tool_log"]
    assert len(tool_logs) == 1
    first_tool = next(iter(tool_logs.values()))
    assert first_tool["group_id"] == "group-1"
    assert first_tool["tool_key"] == "echo"


class _FailingTool(BaseTool):
    def __init__(self, config: ToolConfig, secret_value: str | None = None) -> None:
        super().__init__(config, secret_value)

    def run(self, payload: ToolRunInput) -> ToolRunOutput:
        return ToolRunOutput(ok=False, error="intentional failure")


def test_task_group_failure_aborts_run() -> None:
    PROVIDERS["test:fail"] = _FailingTool
    try:
        primary_cfg = RunConfig(
            current_agent="primary",
            equipped_tools=["fail"],
            tools_map={"fail": _tool_spec("fail", "test:fail")},
            allowed_routes=[],
            allow_respond=True,
            allow_task_group=True,
            allow_task_respond=False,
            system_params={},
            prompt=None,
        )

        decisions = [
            AgentDecision(
                action="TASK_GROUP",
                action_reasoning="try failing tool",
                action_details=TaskGroupDetails(
                    group_id="fail-group",
                    tasks=[
                        TaskGroupUseTool(
                            task_type="use_tool",
                            task_id="fail-task",
                            tool_name="fail",
                            tool_params={},
                            retry_policy=TaskRetryPolicy(attempts=2),
                        )
                    ],
                ),
            )
        ]

        decide_fn = _make_decide_fn(decisions)

        result = run_loop(
            lambda _: primary_cfg,
            default_agent_key="primary",
            user_message="Trigger failure",
            max_steps=3,
            decide_fn=decide_fn,
            model=None,
            debug=False,
        )

        assert not decide_fn.remaining  # type: ignore[attr-defined]
        final = result["final"]
        assert final["status"] == "error"
        assert final["action_type"] == "TASK_GROUP"
        assert "intentional failure" in (final.get("error") or "")

        task_groups = [e for e in result["execution_log"] if e.get("type") == "task_group"]
        assert len(task_groups) == 1
        task_entry = task_groups[0]
        assert task_entry["status"] == "error"
        attempts = task_entry["tasks"][0]["attempts"]
        assert len(attempts) == 2
        assert all(attempt["status"] == "error" for attempt in attempts)

        tool_logs: Dict[str, Dict[str, Any]] = result["tool_log"]
        assert len(tool_logs) == 2
        for entry in tool_logs.values():
            assert entry["group_id"] == "fail-group"
            assert entry["tool_key"] == "fail"
    finally:
        PROVIDERS.pop("test:fail", None)
