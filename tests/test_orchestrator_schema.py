import pytest

from arion_agents.orchestrator import (
    Instruction,
    RespondAction,
    RouteToAgentAction,
    UseToolAction,
    RunConfig,
    execute_instruction,
)


def test_instruction_respond_executes():
    instr = Instruction(
        reasoning="Done",
        action=RespondAction(type="RESPOND", payload={"message": "ok"}),
    )
    result = execute_instruction(instr)
    assert result.status == "ok"
    assert result.response == {"message": "ok"}


def test_instruction_use_tool_not_implemented():
    instr = Instruction(
        reasoning="Need to fetch",
        action=UseToolAction(type="USE_TOOL", tool_name="TemplateRetrievalTool", tool_params={}),
    )
    cfg = RunConfig(current_agent="A", equipped_tools=["TemplateRetrievalTool"], allowed_routes=[], allow_respond=True, system_params={"customer_id": "123"})
    result = execute_instruction(instr, cfg)
    assert result.status == "not_implemented"


def test_instruction_route_not_implemented():
    instr = Instruction(
        reasoning="Hand over",
        action=RouteToAgentAction(type="ROUTE_TO_AGENT", target_agent_name="HumanRemarksAgent", context={}),
    )
    cfg = RunConfig(current_agent="A", equipped_tools=[], allowed_routes=["HumanRemarksAgent"], allow_respond=True, system_params={})
    result = execute_instruction(instr, cfg)
    assert result.status == "not_implemented"


def test_invalid_action_rejected():
    with pytest.raises(Exception):
        Instruction.model_validate(
            {
                "reasoning": "???",
                "action": {"type": "UNKNOWN", "foo": 1},
            }
        )
