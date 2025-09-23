from __future__ import annotations

from typing import Any, Callable, Dict, Optional
import logging
import time

from arion_agents.agent_decision import AgentDecision, decision_to_instruction
from arion_agents.logs.execution_log import ExecutionLog, ToolExecutionLog
from arion_agents.prompts.context_builder import (
    build_constraints,
    build_context,
    build_prompt,
    build_tool_definitions,
    build_route_definitions,
)
from arion_agents.orchestrator import RunConfig, execute_instruction
from arion_agents.llm import GeminiDecideResult, gemini_decide


DecideFn = Callable[[str, Optional[str]], GeminiDecideResult]


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
    logger = logging.getLogger("arion_agents.engine.loop")
    decide = decide_fn or gemini_decide

    run_perf_start = time.perf_counter()
    run_started_at_ms = int(time.time() * 1000)

    current_agent = default_agent_key
    exec_log = ExecutionLog()
    tool_log = ToolExecutionLog()
    step = 0
    debug_steps = []
    step_summaries: list[Dict[str, Any]] = []
    step_events: list[Dict[str, Any]] = []
    next_seq = 0

    def _latency_payload() -> Dict[str, Any]:
        run_duration_ms = int((time.perf_counter() - run_perf_start) * 1000)
        completed_at_ms = run_started_at_ms + run_duration_ms
        return {
            "steps": step_summaries,
            "total_run_ms": run_duration_ms,
            "started_at_ms": run_started_at_ms,
            "completed_at_ms": completed_at_ms,
        }

    total_prompt_tokens = 0
    total_response_tokens = 0
    total_tokens = 0
    aggregate_usage: Optional[Dict[str, int]] = None

    def _safe_int(value: Any) -> int:
        try:
            if value is None:
                return 0
            return int(value)
        except (TypeError, ValueError):
            return 0

    while step < max_steps:
        cfg = get_cfg(current_agent)
        exec_log.start_agent_epoch(current_agent)

        # Gather full tool outputs for this agent's current epoch
        epoch = exec_log.current_epoch_for(current_agent)
        full_tool_outputs = [
            {**payload, "execution_id": ex_id}
            for ex_id, payload in tool_log.collect_full_for(
                exec_log.to_list(), current_agent, epoch
            )
        ]

        step_agent_key = current_agent
        step_started_at_ms = int(time.time() * 1000)
        step_perf_start = time.perf_counter()

        constraints = build_constraints(cfg)
        tool_defs = build_tool_definitions(cfg)
        route_defs = build_route_definitions(cfg)
        # Always include the original user message for every agent/step so
        # routed agents see the full request context instead of a placeholder.
        context = build_context(user_message, exec_log.to_list(), full_tool_outputs)
        prompt = build_prompt(
            cfg, cfg.prompt, context, constraints, tool_defs, route_defs
        )

        # Log prompt when debugging
        if debug:
            try:
                logger.debug(
                    "STEP %s agent=%s LLM request prompt:\n%s",
                    step,
                    current_agent,
                    prompt,
                )
            except Exception:
                pass

        llm_started_at_ms = int(time.time() * 1000)
        llm_perf_start = time.perf_counter()
        llm_result = decide(prompt, model)
        text = llm_result.text
        parsed = llm_result.parsed
        llm_usage = llm_result.usage
        llm_usage_raw = llm_result.usage_raw
        llm_response_payload = llm_result.response_payload
        cumulative_usage: Optional[Dict[str, int]] = aggregate_usage
        if llm_usage:
            step_prompt_tokens = _safe_int(llm_usage.get("prompt_tokens"))
            step_response_tokens = _safe_int(llm_usage.get("response_tokens"))
            step_total_tokens_raw = llm_usage.get("total_tokens")
            step_total_tokens = _safe_int(step_total_tokens_raw)
            if step_total_tokens == 0:
                step_total_tokens = step_prompt_tokens + step_response_tokens
            total_prompt_tokens += step_prompt_tokens
            total_response_tokens += step_response_tokens
            total_tokens += step_total_tokens
            aggregate_usage = {
                "prompt_tokens": total_prompt_tokens,
                "response_tokens": total_response_tokens,
                "total_tokens": total_tokens,
            }
            cumulative_usage = aggregate_usage
        llm_duration_ms = int((time.perf_counter() - llm_perf_start) * 1000)
        llm_completed_at_ms = llm_started_at_ms + llm_duration_ms
        decision = parsed or AgentDecision.model_validate_json(text)
        decision_dump = decision.model_dump()
        if debug:
            try:
                logger.debug(
                    "STEP %s agent=%s LLM raw response:\n%s", step, current_agent, text
                )
            except Exception:
                pass
            debug_steps.append({"agent": current_agent, "prompt": prompt, "raw": text})

        instr = decision_to_instruction(decision, cfg)
        if debug:
            try:
                logger.debug(
                    "STEP %s agent=%s decision -> action=%s",
                    step,
                    current_agent,
                    getattr(instr.action, "type", "<unknown>"),
                )
            except Exception:
                pass
        action_started_at_ms = int(time.time() * 1000)
        action_perf_start = time.perf_counter()
        res = execute_instruction(instr, cfg)
        perf_after_action = time.perf_counter()
        action_duration_ms = int((perf_after_action - action_perf_start) * 1000)
        step_duration_ms = int((perf_after_action - step_perf_start) * 1000)
        step_completed_at_ms = step_started_at_ms + step_duration_ms
        print(f"--- STEP {step} RESULT ---")
        print(res)
        print("--- END RESULT ---")

        exec_log.append_agent_step(
            step=step,
            agent_key=step_agent_key,
            # Mirror the context behavior: always show the original message
            user_input_preview=user_message,
            decision_preview=decision_dump,
            prompt=prompt,
            raw_response=text,
            decision_full=decision_dump,
            step_started_at_ms=step_started_at_ms,
            step_duration_ms=step_duration_ms,
            step_completed_at_ms=step_completed_at_ms,
            llm_started_at_ms=llm_started_at_ms,
            llm_duration_ms=llm_duration_ms,
            llm_completed_at_ms=llm_completed_at_ms,
            llm_usage=llm_usage,
            llm_usage_raw=llm_usage_raw,
            llm_response_payload=llm_response_payload,
            llm_usage_cumulative=cumulative_usage,
        )
        step_summary: Dict[str, Any] = {
            "step": step,
            "agent_key": step_agent_key,
            "action_type": getattr(instr.action, "type", "<unknown>"),
            "duration_ms": step_duration_ms,
            "started_at_ms": step_started_at_ms,
            "completed_at_ms": step_completed_at_ms,
            "llm_duration_ms": llm_duration_ms,
            "llm_started_at_ms": llm_started_at_ms,
            "llm_completed_at_ms": llm_completed_at_ms,
        }
        if llm_usage:
            step_summary["llm_prompt_tokens"] = llm_usage.get("prompt_tokens")
            step_summary["llm_response_tokens"] = llm_usage.get("response_tokens")
            step_summary["llm_total_tokens"] = llm_usage.get("total_tokens")
        if cumulative_usage:
            step_summary["llm_prompt_tokens_total"] = cumulative_usage.get(
                "prompt_tokens"
            )
            step_summary["llm_response_tokens_total"] = cumulative_usage.get(
                "response_tokens"
            )
            step_summary["llm_total_tokens_total"] = cumulative_usage.get(
                "total_tokens"
            )
        step_summary["result_status"] = res.status
        step_summaries.append(step_summary)

        agent_entry = exec_log.entries[-1]
        step_events.append(
            {
                "seq": next_seq,
                "t": step_started_at_ms,
                "step": {
                    "kind": "log_entry",
                    "entryType": "agent",
                    "payload": agent_entry,
                },
            }
        )
        next_seq += 1

        if instr.action.type == "RESPOND":
            run_duration_ms = int((time.perf_counter() - run_perf_start) * 1000)
            step_summary["run_duration_ms"] = run_duration_ms
            agent_entry["run_duration_ms"] = run_duration_ms
            out = {
                "final": res.model_dump(),
                "execution_log": exec_log.to_list(),
                "tool_log_keys": list(tool_log.store.keys()),
                "debug": debug_steps if debug else None,
                "step_events": step_events,
            }
            out["latency"] = _latency_payload()
            out["tool_log"] = tool_log.store
            if aggregate_usage:
                out["llm_usage_totals"] = aggregate_usage
            out["run_duration_ms"] = run_duration_ms
            return out
        elif instr.action.type == "USE_TOOL":
            # res.response structure includes tool, params, result, duration_ms
            r = res.response or {}
            attempted_tool = getattr(getattr(instr, "action", None), "tool_name", None)
            tool_key = r.get("tool") or attempted_tool
            params_for_log = r.get("params") or (
                getattr(getattr(instr, "action", None), "tool_params", {})
                if res.status != "ok"
                else {}
            )
            full_result = r.get("result")
            if res.status != "ok" and full_result is None:
                # Preserve the error so downstream prompts can see what failed
                full_result = {"error": res.error}
            duration_ms = int(r.get("duration_ms") or 0)
            tool_started_at_ms = action_started_at_ms
            total_for_completion = max(duration_ms, action_duration_ms, 0)
            tool_completed_at_ms = (
                tool_started_at_ms + total_for_completion
                if total_for_completion
                else tool_started_at_ms
            )
            execution_id = tool_log.put(
                agent_key=current_agent,
                tool_key=tool_key,
                merged_params=params_for_log or {},
                full_result=full_result,
                duration_ms=duration_ms,
                started_at_ms=tool_started_at_ms,
                completed_at_ms=tool_completed_at_ms,
                total_duration_ms=action_duration_ms,
            )
            exec_log.append_tool_step(
                step=step + 1,
                agent_key=current_agent,
                tool_key=tool_key or "",
                execution_id=execution_id,
                request_preview=str(params_for_log or {}),
                response_preview=str(full_result),
                status=res.status,
                duration_ms=duration_ms,
                request_payload=params_for_log or {},
                response_payload=full_result,
                started_at_ms=tool_started_at_ms,
                completed_at_ms=tool_completed_at_ms,
                total_duration_ms=action_duration_ms,
            )
            step_summary.update(
                {
                    "tool_key": tool_key,
                    "tool_status": res.status,
                    "tool_duration_ms": duration_ms,
                    "tool_total_duration_ms": action_duration_ms,
                }
            )
            tool_entry = exec_log.entries[-1]
            step_events.append(
                {
                    "seq": next_seq,
                    "t": tool_started_at_ms,
                    "step": {
                        "kind": "log_entry",
                        "entryType": "tool",
                        "payload": tool_entry,
                    },
                }
            )
            next_seq += 1
            # Stay with same agent
        elif instr.action.type == "ROUTE_TO_AGENT":
            # Switch agent; epoch will increment on next start_agent_epoch call
            target_agent = instr.action.target_agent_name
            current_agent = target_agent
            step_summary["routed_to_agent"] = target_agent
        else:
            # Unknown -> bail
            out = {
                "final": res.model_dump(),
                "execution_log": exec_log.to_list(),
                "tool_log_keys": list(tool_log.store.keys()),
                "debug": debug_steps if debug else None,
                "step_events": step_events,
            }
            out["latency"] = _latency_payload()
            out["tool_log"] = tool_log.store
            return out

        step += 1

    # Guardrail exceeded
    out = {
        "final": {"status": "error", "error": "max_steps_exceeded"},
        "execution_log": exec_log.to_list(),
        "tool_log_keys": list(tool_log.store.keys()),
        "debug": debug_steps if debug else None,
        "step_events": step_events,
    }
    run_duration_ms = int((time.perf_counter() - run_perf_start) * 1000)
    out["latency"] = _latency_payload()
    out["tool_log"] = tool_log.store
    out["run_duration_ms"] = run_duration_ms
    return out
