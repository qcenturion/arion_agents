from arion_agents.orchestrator import (
    Instruction,
    UseToolAction,
    RespondAction,
    RouteToAgentAction,
    RunConfig,
    execute_instruction,
)


def test_use_tool_forbids_system_params_from_agent():
    instr = Instruction(
        reasoning="call tool",
        action=UseToolAction(type="USE_TOOL", tool_name="TemplateRetrievalTool", tool_params={"customer_id": "hack"}),
    )
    cfg = RunConfig(current_agent="A", equipped_tools=["TemplateRetrievalTool"], allowed_routes=[], allow_respond=True, system_params={"customer_id": "123"})
    res = execute_instruction(instr, cfg)
    assert res.status == "retry"
    assert "System params" in (res.error or "")


def test_respond_not_allowed_returns_retry():
    instr = Instruction(reasoning="done", action=RespondAction(type="RESPOND", payload={"x": 1}))
    cfg = RunConfig(current_agent="A", equipped_tools=[], allowed_routes=[], allow_respond=False, system_params={})
    res = execute_instruction(instr, cfg)
    assert res.status == "retry"


def test_route_not_permitted_returns_retry():
    instr = Instruction(reasoning="route", action=RouteToAgentAction(type="ROUTE_TO_AGENT", target_agent_name="B", context={}))
    cfg = RunConfig(current_agent="A", equipped_tools=[], allowed_routes=["C"], allow_respond=True, system_params={})
    res = execute_instruction(instr, cfg)
    assert res.status == "retry"

