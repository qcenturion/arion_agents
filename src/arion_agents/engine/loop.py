from __future__ import annotations

from typing import Any, Callable, Dict, Optional
import logging
import time
import uuid

from arion_agents.agent_decision import AgentDecision, decision_to_instruction
from arion_agents.logs.execution_log import ExecutionLog, ToolExecutionLog
from arion_agents.prompts.context_builder import (
    build_constraints,
    build_context,
    build_prompt,
    build_tool_definitions,
    build_route_definitions,
)
from arion_agents.orchestrator import (
    DelegationDetails,
    Instruction,
    RunConfig,
    TaskGroupAction,
    TaskGroupDelegate,
    TaskGroupUseTool,
    UseToolAction,
    OrchestratorResult,
    execute_instruction,
)
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
    pending_route_context: Dict[str, Dict[str, Any]] = {}

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

    def _append_step_event(entry_type: str, payload: Dict[str, Any], timestamp_ms: int) -> None:
        nonlocal next_seq
        step_events.append(
            {
                "seq": next_seq,
                "t": timestamp_ms,
                "step": {
                    "kind": "log_entry",
                    "entryType": entry_type,
                    "payload": payload,
                },
            }
        )
        next_seq += 1

    def _log_tool_execution(
        *,
        agent_key: str,
        agent_display_name: Optional[str] = None,
        step_idx: int,
        tool_action,
        result,
        action_started_at_ms: int,
        action_duration_ms: int,
        group_id: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        attempt_index: Optional[int] = None,
    ) -> Dict[str, Any]:
        r = result.response or {}
        attempted_tool = getattr(tool_action, "tool_name", None)
        tool_key = r.get("tool") or attempted_tool
        params_for_log = r.get("params") or (
            getattr(tool_action, "tool_params", {}) if result.status != "ok" else {}
        )
        full_result = r.get("result")
        if result.status != "ok" and full_result is None:
            full_result = {"error": result.error}
        duration_ms = int(r.get("duration_ms") or 0)
        tool_started_at_ms = action_started_at_ms
        total_for_completion = max(duration_ms, action_duration_ms, 0)
        tool_completed_at_ms = (
            tool_started_at_ms + total_for_completion
            if total_for_completion
            else tool_started_at_ms
        )
        execution_id = tool_log.put(
            agent_key=agent_key,
            tool_key=tool_key or "",
            merged_params=params_for_log or {},
            full_result=full_result,
            duration_ms=duration_ms,
            started_at_ms=tool_started_at_ms,
            completed_at_ms=tool_completed_at_ms,
            total_duration_ms=action_duration_ms,
            group_id=group_id,
            parent_task_id=parent_task_id,
            attempt=attempt_index,
        )
        exec_log.append_tool_step(
            step=step_idx,
            agent_key=agent_key,
            tool_key=tool_key or "",
            execution_id=execution_id,
            request_preview=str(params_for_log or {}),
            response_preview=str(full_result),
            status=result.status,
            duration_ms=duration_ms,
            agent_display_name=agent_display_name,
            request_payload=params_for_log or {},
            response_payload=full_result,
            started_at_ms=tool_started_at_ms,
            completed_at_ms=tool_completed_at_ms,
            total_duration_ms=action_duration_ms,
            group_id=group_id,
            parent_task_id=parent_task_id,
            attempt=attempt_index,
        )
        tool_entry = exec_log.entries[-1]
        _append_step_event("tool", tool_entry, tool_started_at_ms)
        return {
            "execution_id": execution_id,
            "tool_key": tool_key,
            "duration_ms": duration_ms,
            "total_duration_ms": action_duration_ms,
            "result": full_result,
            "params": params_for_log,
            "status": result.status,
            "completed_at_ms": tool_completed_at_ms,
        }

    def _run_delegation_attempt(
        detail: DelegationDetails,
        *,
        delegating_agent_key: str,
        group_id: str,
        parent_task_id: str,
        attempt_index: int,
    ) -> Dict[str, Any]:
        delegated_agent = detail.agent_key
        assignment_message = detail.assignment
        context_overrides = detail.context_overrides or {}
        max_steps = max(detail.max_steps or 1, 1)

        def _delegated_get_cfg(agent_key: str) -> RunConfig:
            base_cfg = get_cfg(agent_key)
            base_system = dict(base_cfg.system_params or {})
            delegation_ctx = dict(context_overrides)
            delegation_ctx.update(
                assignment=assignment_message,
                parent_agent=delegating_agent_key,
                group_id=group_id,
                task_id=parent_task_id,
            )
            base_system["delegation"] = delegation_ctx
            return base_cfg.model_copy(
                update={
                    "allow_respond": False,
                    "allow_task_respond": True,
                    "system_params": base_system,
                }
            )

        attempt_started_at_ms = int(time.time() * 1000)
        sub_run: Optional[Dict[str, Any]] = None
        error_message: Optional[str] = None
        status = "ok"
        try:
            sub_run = run_loop(
                _delegated_get_cfg,
                delegated_agent,
                assignment_message,
                max_steps=max_steps,
                model=model,
                decide_fn=decide,
                debug=debug,
            )
            final_payload = (sub_run or {}).get("final") or {}
            final_status = final_payload.get("status")
            final_action_type = (
                final_payload.get("action_type")
                or (final_payload.get("response") or {}).get("action_type")
            )
            if final_status != "ok" or final_action_type != "TASK_RESPOND":
                status = "error"
                error_message = final_payload.get("error") or "Delegated agent did not complete successfully"
        except Exception as exc:  # pragma: no cover - defensive
            status = "error"
            error_message = str(exc)

        attempt_completed_at_ms = int(time.time() * 1000)
        duration_ms = attempt_completed_at_ms - attempt_started_at_ms
        attempt_entry: Dict[str, Any] = {
            "attempt": attempt_index,
            "status": status,
            "agent_key": delegated_agent,
            "assignment": assignment_message,
            "started_at_ms": attempt_started_at_ms,
            "completed_at_ms": attempt_completed_at_ms,
            "duration_ms": duration_ms,
        }
        if status != "ok" and error_message:
            attempt_entry["error"] = error_message
        if sub_run is not None:
            attempt_entry["run"] = {
                "final": sub_run.get("final"),
                "execution_log": sub_run.get("execution_log"),
                "tool_log": sub_run.get("tool_log"),
                "step_events": sub_run.get("step_events"),
                "run_duration_ms": sub_run.get("run_duration_ms"),
                "trace_id": sub_run.get("trace_id"),
            }

        result_payload = None
        if sub_run and status == "ok":
            final_payload = sub_run.get("final") or {}
            result_payload = final_payload.get("response") or final_payload.get("payload")

        return {
            "status": status,
            "attempt_entry": attempt_entry,
            "result_payload": result_payload,
            "error": error_message,
        }

    def _handle_task_group(
        action: TaskGroupAction,
        cfg: RunConfig,
        *,
        agent_key: str,
        step_idx: int,
    ) -> Dict[str, Any]:
        group_id = action.group_id or uuid.uuid4().hex
        if cfg and not cfg.allow_task_group:
            return {
                "status": "error",
                "error": f"TASK_GROUP not permitted for agent {agent_key}",
                "group_id": group_id,
                "tasks_log": [],
                "response": None,
            }

        tasks_log: list[Dict[str, Any]] = []
        response_tasks: list[Dict[str, Any]] = []
        for idx, task in enumerate(action.tasks):
            task_identifier = task.task_id or f"{idx}"
            attempts_allowed = max(getattr(task.retry_policy, "attempts", 1) or 1, 1)
            attempt_entries: list[Dict[str, Any]] = []
            task_success = False
            last_error: Optional[str] = None
            result_payload: Optional[Any] = None

            for attempt_idx in range(1, attempts_allowed + 1):
                attempt_started_at_ms = int(time.time() * 1000)
                attempt_perf_start = time.perf_counter()

                if isinstance(task, TaskGroupUseTool):
                    child_instr = Instruction(
                        reasoning=f"TASK_GROUP child {task_identifier}",
                        action=UseToolAction(
                            type="USE_TOOL",
                            tool_name=task.tool_name,
                            tool_params=task.tool_params,
                        ),
                    )
                    child_result = execute_instruction(child_instr, cfg)
                    action_duration_ms = int(
                        (time.perf_counter() - attempt_perf_start) * 1000
                    )
                    log_info = _log_tool_execution(
                        agent_key=agent_key,
                        agent_display_name=cfg.display_name,
                        step_idx=step_idx + 1,
                        tool_action=child_instr.action,
                        result=child_result,
                        action_started_at_ms=attempt_started_at_ms,
                        action_duration_ms=action_duration_ms,
                        group_id=group_id,
                        parent_task_id=task_identifier,
                        attempt_index=attempt_idx,
                    )
                    attempt_entry: Dict[str, Any] = {
                        "attempt": attempt_idx,
                        "status": child_result.status,
                        "tool": task.tool_name,
                        "execution_id": log_info["execution_id"],
                        "duration_ms": action_duration_ms,
                    }
                    if child_result.status != "ok":
                        last_error = child_result.error or "tool execution failed"
                        attempt_entry["error"] = last_error
                    else:
                        result_payload = log_info["result"]
                        attempt_entry["result"] = log_info["result"]
                        task_success = True
                        last_error = None
                    attempt_entries.append(attempt_entry)

                elif isinstance(task, TaskGroupDelegate):
                    delegation_attempts: list[Dict[str, Any]] = []
                    delegation_results: list[Any] = []
                    delegation_error: Optional[str] = None
                    for detail in task.delegation_details:
                        delegation_outcome = _run_delegation_attempt(
                            detail,
                            delegating_agent_key=agent_key,
                            group_id=group_id,
                            parent_task_id=task_identifier,
                            attempt_index=attempt_idx,
                        )
                        delegation_attempts.append(delegation_outcome["attempt_entry"])
                        if delegation_outcome["status"] != "ok":
                            delegation_error = (
                                delegation_outcome["error"]
                                or "delegated agent failed"
                            )
                            break
                        delegation_results.append(delegation_outcome["result_payload"])

                    attempt_entry = {
                        "attempt": attempt_idx,
                        "status": "ok" if delegation_error is None else "error",
                        "delegations": delegation_attempts,
                    }
                    if delegation_error is not None:
                        last_error = delegation_error
                        attempt_entry["error"] = delegation_error
                    else:
                        result_payload = delegation_results
                        task_success = True
                        last_error = None
                    attempt_entries.append(attempt_entry)
                else:
                    last_error = f"Unsupported task type: {getattr(task, 'task_type', '<unknown>')}"
                    attempt_entries.append(
                        {
                            "attempt": attempt_idx,
                            "status": "error",
                            "error": last_error,
                        }
                    )

                if task_success:
                    break

            task_log_entry = {
                "task_id": task_identifier,
                "task_type": getattr(task, "task_type", "<unknown>"),
                "status": "ok" if task_success else "error",
                "attempts": attempt_entries,
            }
            if result_payload is not None:
                task_log_entry["result"] = result_payload
            if not task_success and last_error is not None:
                task_log_entry["error"] = last_error
            tasks_log.append(task_log_entry)

            response_tasks.append(
                {
                    "task_id": task_identifier,
                    "status": "ok" if task_success else "error",
                    "result": result_payload,
                    "error": None if task_success else last_error,
                }
            )

            if not task_success:
                return {
                    "status": "error",
                    "error": last_error,
                    "group_id": group_id,
                    "tasks_log": tasks_log,
                    "response": {
                        "group_id": group_id,
                        "tasks": response_tasks,
                    },
                }

        return {
            "status": "ok",
            "error": None,
            "group_id": group_id,
            "tasks_log": tasks_log,
            "response": {
                "group_id": group_id,
                "tasks": response_tasks,
            },
        }

    while step < max_steps:
        cfg = get_cfg(current_agent)
        exec_log.start_agent_epoch(current_agent)

        handoff_context = pending_route_context.pop(current_agent, None)

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

        tool_defs = build_tool_definitions(cfg)
        route_defs = build_route_definitions(cfg)
        constraints = build_constraints(cfg, tool_defs, route_defs)
        # Always include the original user message for every agent/step so
        # routed agents see the full request context instead of a placeholder.
        context = build_context(
            user_message,
            exec_log.to_list(),
            full_tool_outputs,
            handoff_context,
        )
        prompt = build_prompt(cfg, cfg.prompt, context, constraints)

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
        task_group_outcome: Optional[Dict[str, Any]] = None
        if isinstance(instr.action, TaskGroupAction):
            handler_outcome = _handle_task_group(
                instr.action,
                cfg,
                agent_key=current_agent,
                step_idx=step,
            )
            res = OrchestratorResult(
                status=handler_outcome["status"],
                response=handler_outcome["response"],
                error=handler_outcome.get("error"),
            )
            task_group_outcome = handler_outcome
            perf_after_action = time.perf_counter()
        else:
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
            agent_display_name=cfg.display_name,
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
        _append_step_event("agent", agent_entry, step_started_at_ms)

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
        elif instr.action.type == "TASK_RESPOND":
            run_duration_ms = int((time.perf_counter() - run_perf_start) * 1000)
            step_summary["run_duration_ms"] = run_duration_ms
            agent_entry["run_duration_ms"] = run_duration_ms
            final_payload = res.model_dump()
            final_payload["action_type"] = "TASK_RESPOND"
            out = {
                "final": final_payload,
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
            log_info = _log_tool_execution(
                agent_key=current_agent,
                agent_display_name=cfg.display_name,
                step_idx=step + 1,
                tool_action=instr.action,
                result=res,
                action_started_at_ms=action_started_at_ms,
                action_duration_ms=action_duration_ms,
            )
            step_summary.update(
                {
                    "tool_key": log_info.get("tool_key"),
                    "tool_status": res.status,
                    "tool_duration_ms": log_info.get("duration_ms"),
                    "tool_total_duration_ms": action_duration_ms,
                }
            )
            # Stay with same agent
        elif instr.action.type == "ROUTE_TO_AGENT":
            # Switch agent; epoch will increment on next start_agent_epoch call
            target_agent = instr.action.target_agent_name
            current_agent = target_agent
            step_summary["routed_to_agent"] = target_agent
            route_context = dict(getattr(instr.action, "context", {}) or {})
            pending_route_context[target_agent] = route_context
            if route_context:
                step_summary["route_context_keys"] = sorted(route_context.keys())
                agent_entry["route_context"] = route_context
        elif instr.action.type == "TASK_GROUP":
            if task_group_outcome is not None:
                group_id = task_group_outcome.get("group_id")
                group_status = task_group_outcome.get("status")
                tasks_log = task_group_outcome.get("tasks_log", [])
                group_completed_at_ms = action_started_at_ms + action_duration_ms
                exec_log.append_task_group_step(
                    step=step + 1,
                    agent_key=current_agent,
                    group_id=group_id or "",
                    status=group_status or res.status,
                    reasoning=instr.reasoning,
                    tasks=tasks_log,
                    started_at_ms=action_started_at_ms,
                    duration_ms=action_duration_ms,
                    completed_at_ms=group_completed_at_ms,
                )
                group_entry = exec_log.entries[-1]
                _append_step_event("task_group", group_entry, action_started_at_ms)
                step_summary.update(
                    {
                        "task_group_id": group_id,
                        "task_group_status": group_status,
                        "task_group_duration_ms": action_duration_ms,
                    }
                )
            if res.status != "ok":
                out = {
                    "final": res.model_dump(),
                    "execution_log": exec_log.to_list(),
                    "tool_log_keys": list(tool_log.store.keys()),
                    "debug": debug_steps if debug else None,
                    "step_events": step_events,
                }
                out["latency"] = _latency_payload()
                out["tool_log"] = tool_log.store
                out.setdefault("final", {}).setdefault("action_type", "TASK_GROUP")
                if aggregate_usage:
                    out["llm_usage_totals"] = aggregate_usage
                out["run_duration_ms"] = int((time.perf_counter() - run_perf_start) * 1000)
                return out
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
