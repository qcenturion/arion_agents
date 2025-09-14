from arion_agents.agent_decision import AgentDecision, decision_to_instruction
from arion_agents.orchestrator import RunConfig, execute_instruction


def cfg_with_echo():
    return RunConfig(
        current_agent="solo",
        equipped_tools=["echo"],
        tools_map={
            "echo": {
                "key": "echo",
                "provider_type": "builtin:echo",
                "params_schema": {
                    "message": {"source": "agent", "required": True},
                    "customer_id": {"source": "system", "required": False},
                },
                "metadata": {},
            }
        },
        allowed_routes=[],
        allow_respond=True,
        system_params={"customer_id": "abc"},
        prompt=None,
    )


def test_translate_use_tool_and_execute():
    decision = AgentDecision(
        action="USE_TOOL",
        action_reasoning="echo",
        action_details={"tool_name": "echo", "tool_params": {"message": "hi"}},
    )
    cfg = cfg_with_echo()
    instr = decision_to_instruction(decision, cfg)
    out = execute_instruction(instr, cfg)
    assert out.status in {"ok", "not_implemented"}


def test_translate_respond():
    decision = AgentDecision(action="RESPOND", action_reasoning="done", action_details={"payload": {"ok": True}})
    cfg = cfg_with_echo()
    instr = decision_to_instruction(decision, cfg)
    out = execute_instruction(instr, cfg)
    assert out.status == "ok"
    assert out.response == {"ok": True}


def test_translate_route():
    decision = AgentDecision(action="ROUTE_TO_AGENT", action_reasoning="next", action_details={"target_agent_name": "writer"})
    cfg = cfg_with_echo()
    instr = decision_to_instruction(decision, cfg)
    assert instr.action.type == "ROUTE_TO_AGENT"
