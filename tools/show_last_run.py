#!/usr/bin/env python3
"""Display the latest /run artifact with prompts, LLM output, tool calls, and final response."""

import json
from pathlib import Path
from typing import Any, Dict

RUNS_DIR = Path(__file__).resolve().parent.parent / "logs" / "runs"


def _load_latest() -> Dict[str, Any]:
    files = sorted(RUNS_DIR.glob("run_*.json"))
    if not files:
        raise SystemExit("No run artifacts found in logs/runs")
    latest = files[-1]
    with latest.open("r", encoding="utf-8") as f:
        data = json.load(f)
    data["_file"] = str(latest)
    return data


def _print_header(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> None:
    payload = _load_latest()
    print(f"File: {payload['_file']}")
    final = payload.get("response", {}).get("final") or payload.get("final")
    exec_log = payload.get("response", {}).get("execution_log") or payload.get(
        "execution_log"
    )
    debug = payload.get("response", {}).get("debug") or payload.get("debug")
    tool_log = payload.get("response", {}).get("tool_log") or payload.get("tool_log")
    latency = payload.get("response", {}).get("latency") or payload.get("latency")
    llm_totals = payload.get("response", {}).get("llm_usage_totals") or payload.get(
        "llm_usage_totals"
    )
    run_duration_ms = payload.get("response", {}).get("run_duration_ms") or payload.get(
        "run_duration_ms"
    )

    _print_header("Final Response")
    print(json.dumps(final, indent=2))

    if latency:
        steps = latency.get("steps") or []
        total_ms = latency.get("total_run_ms")
        _print_header("Latency Summary")
        for item in steps:
            step_idx = item.get("step")
            step_num = step_idx + 1 if isinstance(step_idx, int) else step_idx
            agent = item.get("agent_key") or "<unknown>"
            action = item.get("action_type") or "?"
            duration_ms = item.get("duration_ms")
            llm_ms = item.get("llm_duration_ms")
            tool_ms = item.get("tool_duration_ms")
            tool_total_ms = item.get("tool_total_duration_ms")
            tool_key = item.get("tool_key")
            tool_status = item.get("tool_status")
            parts = []
            if isinstance(duration_ms, (int, float)):
                parts.append(f"total={duration_ms / 1000.0:.3f}s")
            if isinstance(llm_ms, (int, float)):
                parts.append(f"llm={llm_ms / 1000.0:.3f}s")
            if tool_key:
                if isinstance(tool_ms, (int, float)):
                    parts.append(f"tool={tool_ms / 1000.0:.3f}s")
                elif isinstance(tool_total_ms, (int, float)):
                    parts.append(f"tool≈{tool_total_ms / 1000.0:.3f}s")
                if tool_status:
                    parts.append(f"tool_status={tool_status}")
            if item.get("routed_to_agent"):
                parts.append(f"routed_to={item['routed_to_agent']}")
            if item.get("result_status") and not tool_status:
                parts.append(f"status={item['result_status']}")
            detail = ", ".join(parts) if parts else "no timing data"
            print(f"Step {step_num} ({agent} → {action}): {detail}")
        if isinstance(total_ms, (int, float)):
            print(f"Total Run Time: {total_ms / 1000.0:.3f}s")

    if isinstance(llm_totals, dict):
        _print_header("LLM Token Totals")
        prompt = llm_totals.get("prompt_tokens")
        response = llm_totals.get("response_tokens")
        total = llm_totals.get("total_tokens")
        parts = []
        if isinstance(prompt, int):
            parts.append(f"prompt={prompt}")
        if isinstance(response, int):
            parts.append(f"response={response}")
        if isinstance(total, int):
            parts.append(f"total={total}")
        print(", ".join(parts) if parts else json.dumps(llm_totals, indent=2))

    if isinstance(run_duration_ms, int):
        _print_header("Run Duration")
        seconds = run_duration_ms / 1000.0
        print(f"{run_duration_ms} ms ({seconds:.3f}s)")

    _print_header("Execution Log")
    print(json.dumps(exec_log, indent=2))

    _print_header("LLM Prompts & Raw Responses")
    for entry in debug or []:
        print(f"\nAgent: {entry.get('agent')}")
        print("Prompt:\n" + entry.get("prompt", ""))
        print("Raw:\n" + entry.get("raw", ""))

    _print_header("Tool Calls")
    if isinstance(tool_log, dict):
        for key, info in tool_log.items():
            print(f"\nExecution ID: {key}")
            print(json.dumps(info, indent=2))
    else:
        print(json.dumps(tool_log, indent=2))


if __name__ == "__main__":
    main()
