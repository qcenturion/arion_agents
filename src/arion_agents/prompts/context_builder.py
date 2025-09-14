from __future__ import annotations

from typing import Any, Dict, List


def build_constraints(cfg) -> str:
    lines: List[str] = []
    lines.append(
        "You MUST respond as JSON with fields: action (USE_TOOL|ROUTE_TO_AGENT|RESPOND), action_reasoning (string), action_details (object)."
    )
    if getattr(cfg, "equipped_tools", None):
        lines.append("Allowed tools and agent-provided params:")
        for k in cfg.equipped_tools:
            ts = cfg.tools_map.get(k)
            if not ts:
                continue
            params_schema = getattr(ts, "params_schema", None) or (isinstance(ts, dict) and ts.get("params_schema")) or {}
            ps = [name for name, spec in (params_schema or {}).items() if (spec or {}).get("source", "agent") == "agent"]
            lines.append(f"- {k}: params={ps}")
    if getattr(cfg, "allowed_routes", None):
        lines.append("Allowed routes (agent keys):")
        for r in cfg.allowed_routes:
            lines.append(f"- {r}")
    lines.append("When using USE_TOOL, action_details must include tool_name and tool_params.")
    lines.append("When routing, action_details must include target_agent_name.")
    lines.append("When responding, put your payload in action_details.payload.")
    return "\n".join(lines)


def build_context(user_message: str, exec_log: List[Dict[str, Any]], full_tool_outputs: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    parts.append(f"User message:\n{user_message}")
    if full_tool_outputs:
        parts.append("Tool outputs (most recent first):")
        for item in reversed(full_tool_outputs):
            tool_key = item.get("tool_key") or item.get("result", {}).get("tool")
            result = item.get("result")
            parts.append(f"- {tool_key}: {result}")
    if exec_log:
        parts.append("Execution log summary:")
        for e in exec_log[-10:]:  # last 10
            if e.get("type") == "agent":
                parts.append(f"  step {e['step']}: agent {e['agent_key']} → {e['decision']['action']}")
            elif e.get("type") == "tool":
                parts.append(f"  step {e['step']}: tool {e['tool_key']} status={e['status']}")
    return "\n".join(parts)


def build_prompt(base_prompt: str | None, context: str, constraints: str) -> str:
    parts: List[str] = []
    if base_prompt:
        parts.append(base_prompt)
    parts.append(context)
    parts.append(constraints)
    return "\n\n".join(parts)

