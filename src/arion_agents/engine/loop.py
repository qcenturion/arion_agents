from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from arion_agents.agent_decision import AgentDecision, decision_to_instruction
from arion_agents.logs.execution_log import ExecutionLog, ToolExecutionLog
from arion_agents.prompts.context_builder import build_constraints, build_context, build_prompt, build_tool_definitions
from arion_agents.orchestrator import RunConfig, execute_instruction
from arion_agents.llm import gemini_decide


DecideFn = Callable[[str, Optional[str]], tuple[str, Optional[AgentDecision]]]


def run_loop(
    get_cfg: Callable[[str], RunConfig],
    default_agent_key: str,
    user_message: str,
    *,
    max_steps: int = 10,
    model: Optional[str] = None,
    decide_fn: Optional[DecideFn] = None,
    debug: bool = False,
) -> Dict[str, Any]:
    decide = decide_fn or (lambda prompt, m: gemini_decide(prompt, m))

    current_agent = default_agent_key
    exec_log = ExecutionLog()
    tool_log = ToolExecutionLog()
    step = 0
    debug_steps = []

    while step < max_steps:
        cfg = get_cfg(current_agent)
        exec_log.start_agent_epoch(current_agent)

        # Gather full tool outputs for this agent's current epoch
        epoch = exec_log.current_epoch_for(current_agent)
        full_tool_outputs = [
            {**payload, "execution_id": ex_id}
            for ex_id, payload in tool_log.collect_full_for(exec_log.to_list(), current_agent, epoch)
        ]

        constraints = build_constraints(cfg)
        tool_defs = build_tool_definitions(cfg)
        context = build_context(user_message if step == 0 else "(continued)", exec_log.to_list(), full_tool_outputs)
        prompt = build_prompt(cfg.prompt, context, constraints, tool_defs)

        text, parsed = decide(prompt, model)
        decision = parsed or AgentDecision.model_validate_json(text)
        exec_log.append_agent_step(
            step=step,
            agent_key=current_agent,
            user_input_preview=user_message if step == 0 else "(continued)",
            decision_preview=decision.model_dump(),
        )
        if debug:
            debug_steps.append({"agent": current_agent, "prompt": prompt, "raw": text})

        instr = decision_to_instruction(decision, cfg)
        res = execute_instruction(instr, cfg)
        print(f"--- STEP {step} RESULT ---")
        print(res)
        print("--- END RESULT ---")

        if instr.action.type == "RESPOND":
            out = {
                "final": res.model_dump(),
                "execution_log": exec_log.to_list(),
                "tool_log_keys": list(tool_log.store.keys()),
                "debug": debug_steps if debug else None,
            }
            if debug:
                out["tool_log"] = tool_log.store
            return out
        elif instr.action.type == "USE_TOOL":
            # res.response structure includes tool, params, result, duration_ms
            r = res.response or {}
            execution_id = tool_log.put(
                agent_key=current_agent,
                tool_key=r.get("tool"),
                merged_params=r.get("params") or {},
                full_result=r.get("result"),
                duration_ms=int(r.get("duration_ms") or 0),
            )
            exec_log.append_tool_step(
                step=step + 1,
                agent_key=current_agent,
                tool_key=r.get("tool"),
                execution_id=execution_id,
                request_preview=str(r.get("params")),
                response_preview=str(r.get("result")),
                status=res.status,
                duration_ms=int(r.get("duration_ms") or 0),
            )
            # Stay with same agent
        elif instr.action.type == "ROUTE_TO_AGENT":
            # Switch agent; epoch will increment on next start_agent_epoch call
            current_agent = instr.action.target_agent_name
        else:
            # Unknown -> bail
            out = {
                "final": res.model_dump(),
                "execution_log": exec_log.to_list(),
                "tool_log_keys": list(tool_log.store.keys()),
                "debug": debug_steps if debug else None,
            }
            if debug:
                out["tool_log"] = tool_log.store
            return out

        step += 1

    # Guardrail exceeded
    out = {
        "final": {"status": "error", "error": "max_steps_exceeded"},
        "execution_log": exec_log.to_list(),
        "tool_log_keys": list(tool_log.store.keys()),
        "debug": debug_steps if debug else None,
    }
    if debug:
        out["tool_log"] = tool_log.store
    return out
