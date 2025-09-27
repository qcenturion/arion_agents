from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional, Tuple


def _truncate(s: Any, n: int) -> str:
    t = str(s)
    return t if len(t) <= n else t[: n - 1] + "…"


class ExecutionLog:
    def __init__(self) -> None:
        self.entries: List[Dict[str, Any]] = []
        self.epoch_by_agent: Dict[str, int] = {}
        self.current_epoch: int = 0
        self.last_agent: Optional[str] = None

    def start_agent_epoch(self, agent_key: str) -> None:
        if self.last_agent is None:
            self.current_epoch = 0
        elif self.last_agent != agent_key:
            self.current_epoch += 1
        self.epoch_by_agent[agent_key] = self.current_epoch
        self.last_agent = agent_key

    def append_agent_step(
        self,
        step: int,
        agent_key: str,
        user_input_preview: str,
        decision_preview: Dict[str, Any],
        *,
        agent_display_name: Optional[str] = None,
        prompt: Optional[str] = None,
        raw_response: Optional[str] = None,
        decision_full: Optional[Dict[str, Any]] = None,
        step_started_at_ms: Optional[int] = None,
        step_duration_ms: Optional[int] = None,
        step_completed_at_ms: Optional[int] = None,
        llm_started_at_ms: Optional[int] = None,
        llm_duration_ms: Optional[int] = None,
        llm_completed_at_ms: Optional[int] = None,
        llm_usage: Optional[Dict[str, int]] = None,
        llm_usage_raw: Optional[Dict[str, Any]] = None,
        llm_response_payload: Optional[Any] = None,
        llm_usage_cumulative: Optional[Dict[str, int]] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "type": "agent",
            "step": step,
            "epoch": self.current_epoch,
            "agent_key": agent_key,
            "input_preview": _truncate(user_input_preview, 80),
            "decision": {
                "action": decision_preview.get("action"),
                "action_reasoning": _truncate(
                    decision_preview.get("action_reasoning", ""), 120
                ),
                "action_details": _truncate(
                    decision_preview.get("action_details", {}), 120
                ),
            },
        }
        if agent_display_name is not None:
            payload["agent_display_name"] = agent_display_name
        if prompt is not None:
            payload["prompt"] = prompt
        if raw_response is not None:
            payload["raw_response"] = raw_response
        if llm_response_payload is not None:
            payload["llm_response_payload"] = llm_response_payload
        if decision_full is not None:
            payload["decision_full"] = decision_full
        if llm_usage is not None:
            payload["llm_usage"] = llm_usage
        if llm_usage_raw is not None:
            payload["llm_usage_raw"] = llm_usage_raw
        if llm_usage_cumulative is not None:
            payload["llm_usage_cumulative"] = llm_usage_cumulative
        timing: Dict[str, Any] = {}
        if step_started_at_ms is not None:
            timing["step_started_at_ms"] = step_started_at_ms
        if step_duration_ms is not None:
            payload["duration_ms"] = step_duration_ms
            timing["step_duration_ms"] = step_duration_ms
        if step_completed_at_ms is not None:
            timing["step_completed_at_ms"] = step_completed_at_ms
        if llm_started_at_ms is not None:
            timing["llm_started_at_ms"] = llm_started_at_ms
        if llm_duration_ms is not None:
            payload["llm_duration_ms"] = llm_duration_ms
            timing["llm_duration_ms"] = llm_duration_ms
        if llm_completed_at_ms is not None:
            timing["llm_completed_at_ms"] = llm_completed_at_ms
        if timing:
            payload["timing"] = timing
        self.entries.append(payload)

    def append_tool_step(
        self,
        step: int,
        agent_key: str,
        tool_key: str,
        execution_id: str,
        request_preview: str,
        response_preview: str,
        status: str,
        duration_ms: int,
        *,
        agent_display_name: Optional[str] = None,
        request_payload: Optional[Dict[str, Any]] = None,
        response_payload: Optional[Any] = None,
        started_at_ms: Optional[int] = None,
        completed_at_ms: Optional[int] = None,
        total_duration_ms: Optional[int] = None,
        group_id: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        attempt: Optional[int] = None,
        request_excerpt: Optional[Dict[str, Any]] = None,
        response_excerpt: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "type": "tool",
            "step": step,
            "epoch": self.current_epoch,
            "agent_key": agent_key,
            "tool_key": tool_key,
            "execution_id": execution_id,
            "request_preview": request_preview,
            "response_preview": response_preview,
            "status": status,
            "duration_ms": duration_ms,
        }
        if agent_display_name is not None:
            payload["agent_display_name"] = agent_display_name
        if request_payload is not None:
            payload["request_payload"] = request_payload
        if response_payload is not None:
            payload["response_payload"] = response_payload
        if request_excerpt is not None:
            payload["request_excerpt"] = request_excerpt
        if response_excerpt is not None:
            payload["response_excerpt"] = response_excerpt
        if group_id is not None:
            payload["group_id"] = group_id
        if parent_task_id is not None:
            payload["parent_task_id"] = parent_task_id
        if attempt is not None:
            payload["attempt"] = attempt
        timing: Dict[str, Any] = {}
        if started_at_ms is not None:
            timing["started_at_ms"] = started_at_ms
        if completed_at_ms is not None:
            timing["completed_at_ms"] = completed_at_ms
        if duration_ms is not None:
            timing["duration_ms"] = duration_ms
        if total_duration_ms is not None:
            timing["total_duration_ms"] = total_duration_ms
            payload["total_duration_ms"] = total_duration_ms
        if timing:
            payload["timing"] = timing
        self.entries.append(payload)

    def append_task_group_step(
        self,
        *,
        step: int,
        agent_key: str,
        group_id: str,
        status: str,
        reasoning: str,
        tasks: List[Dict[str, Any]],
        started_at_ms: int,
        duration_ms: int,
        completed_at_ms: int,
    ) -> None:
        payload: Dict[str, Any] = {
            "type": "task_group",
            "step": step,
            "epoch": self.current_epoch,
            "agent_key": agent_key,
            "group_id": group_id,
            "status": status,
            "reasoning": reasoning,
            "tasks": tasks,
            "duration_ms": duration_ms,
            "timing": {
                "started_at_ms": started_at_ms,
                "completed_at_ms": completed_at_ms,
                "duration_ms": duration_ms,
            },
        }
        self.entries.append(payload)

    def append_system_message(self, message: str) -> None:
        payload: Dict[str, Any] = {
            "type": "system",
            "message": message,
            "timestamp_ms": int(time.time() * 1000),
        }
        self.entries.append(payload)

    def current_epoch_for(self, agent_key: str) -> int:
        return self.epoch_by_agent.get(agent_key, self.current_epoch)

    def to_list(self) -> List[Dict[str, Any]]:
        return list(self.entries)


class ToolExecutionLog:
    def __init__(self) -> None:
        self.store: Dict[str, Dict[str, Any]] = {}

    def put(
        self,
        agent_key: str,
        tool_key: str,
        merged_params: Dict[str, Any],
        full_result: Any,
        duration_ms: int,
        *,
        started_at_ms: Optional[int] = None,
        completed_at_ms: Optional[int] = None,
        total_duration_ms: Optional[int] = None,
        group_id: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        attempt: Optional[int] = None,
        request_excerpt: Optional[Dict[str, Any]] = None,
        response_excerpt: Optional[Dict[str, Any]] = None,
        request_preview_text: Optional[str] = None,
        response_preview_text: Optional[str] = None,
    ) -> str:
        exec_id = uuid.uuid4().hex
        timestamp_ms = (
            completed_at_ms if completed_at_ms is not None else int(time.time() * 1000)
        )
        self.store[exec_id] = {
            "agent_key": agent_key,
            "tool_key": tool_key,
            "params": merged_params,
            "result": full_result,
            "duration_ms": duration_ms,
            "ts": timestamp_ms,
            "started_at_ms": started_at_ms,
            "completed_at_ms": completed_at_ms,
            "total_duration_ms": total_duration_ms,
            "group_id": group_id,
            "parent_task_id": parent_task_id,
            "attempt": attempt,
            "request_excerpt": request_excerpt,
            "response_excerpt": response_excerpt,
            "request_preview_text": request_preview_text,
            "response_preview_text": response_preview_text,
        }
        return exec_id

    def get(self, exec_id: str) -> Optional[Dict[str, Any]]:
        return self.store.get(exec_id)

    def collect_full_for(
        self, entries: List[Dict[str, Any]], agent_key: str, epoch: int
    ) -> List[Tuple[str, Dict[str, Any]]]:
        out: List[Tuple[str, Dict[str, Any]]] = []
        for e in entries:
            if (
                e.get("type") == "tool"
                and e.get("agent_key") == agent_key
                and e.get("epoch") == epoch
            ):
                ex_id = e.get("execution_id")
                if ex_id and ex_id in self.store:
                    out.append((ex_id, self.store[ex_id]))
        return out
