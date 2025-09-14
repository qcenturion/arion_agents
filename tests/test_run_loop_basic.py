from arion_agents.engine.loop import run_loop
from arion_agents.orchestrator import RunConfig
from arion_agents.agent_decision import AgentDecision


def test_run_loop_with_echo_tool():
    # Fake get_cfg returns fixed config for the agent
    def get_cfg(agent_key: str) -> RunConfig:
        return RunConfig(
            current_agent=agent_key,
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
            prompt="You are triage. Tools:\n- echo: echoes\nRoutes:\n(none)\nPick one action.",
        )

    # Decide function yields USE_TOOL then RESPOND
    calls = {"n": 0}

    def decide_fn(prompt: str, model):
        if calls["n"] == 0:
            calls["n"] += 1
            return (
                "",
                AgentDecision(
                    action="USE_TOOL",
                    action_reasoning="need echo",
                    action_details={"tool_name": "echo", "tool_params": {"message": "hi"}},
                ),
            )
        else:
            return (
                "",
                AgentDecision(
                    action="RESPOND",
                    action_reasoning="done",
                    action_details={"payload": {"ok": True}},
                ),
            )

    out = run_loop(get_cfg, "triage", "say hi", max_steps=5, model=None, decide_fn=decide_fn, debug=False)
    assert out["final"]["status"] == "ok"
    assert any(e["type"] == "tool" for e in out["execution_log"])
    assert len(out["tool_log_keys"]) == 1

