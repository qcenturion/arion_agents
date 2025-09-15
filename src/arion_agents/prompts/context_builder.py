from __future__ import annotations

from typing import Any, Dict, List


def build_constraints(cfg) -> str:
    lines: List[str] = []
    lines.append(
        "You MUST respond as JSON with fields: action (USE_TOOL|ROUTE_TO_AGENT|RESPOND), action_reasoning (string), action_details (object)."
    )
    tool_names: List[str] = []
    if getattr(cfg, "equipped_tools", None):
        lines.append("Allowed tools and agent-provided params:")
        for k in cfg.equipped_tools:
            ts = cfg.tools_map.get(k)
            if not ts:
                continue
            params_schema = getattr(ts, "params_schema", None) or (isinstance(ts, dict) and ts.get("params_schema")) or {}
            ps = [name for name, spec in (params_schema or {}).items() if (spec or {}).get("source", "agent") == "agent"]
            lines.append(f"- {k}: params={ps}")
            tool_names.append(k)
        if tool_names:
            lines.append(f"tool_name must be one of: {tool_names}")
    if getattr(cfg, "allowed_routes", None):
        lines.append("Allowed routes (agent keys):")
        for r in cfg.allowed_routes:
            lines.append(f"- {r}")
    lines.append("When using USE_TOOL, action_details must include tool_name and tool_params.")
    lines.append("When routing, action_details must include target_agent_name.")
    lines.append("When responding, put your payload in action_details.payload.")
    # Add a concrete example for USE_TOOL based on the first tool
    try:
        if tool_names:
            first = tool_names[0]
            ts = cfg.tools_map.get(first)
            params_schema = getattr(ts, "params_schema", None) or (isinstance(ts, dict) and ts.get("params_schema")) or {}
            agent_fields = [name for name, spec in (params_schema or {}).items() if (spec or {}).get("source", "agent") == "agent"]
            example_params = {k: f"<{k}>" for k in agent_fields} or {"example": "value"}
            import json
            lines.append("Example for USE_TOOL (follow exactly):")
            example = {
                "action": "USE_TOOL",
                "action_reasoning": "why this tool",
                "action_details": {"tool_name": first, "tool_params": example_params},
            }
            lines.append("```json")
            lines.append(json.dumps(example))
            lines.append("```")
    except Exception:
        pass
    return "\n".join(lines)


def build_tool_definitions(cfg) -> str:
    lines: List[str] = []
    lines.append("Tool Definitions (read carefully):")
    for k in getattr(cfg, "equipped_tools", []) or []:
        ts = cfg.tools_map.get(k)
        if not ts:
            continue
        # ts may be dict or object
        desc = getattr(ts, "description", None) or (isinstance(ts, dict) and ts.get("description")) or ""
        provider_type = getattr(ts, "provider_type", None) or (isinstance(ts, dict) and ts.get("provider_type")) or ""
        metadata = getattr(ts, "metadata", None) or (isinstance(ts, dict) and ts.get("metadata")) or {}
        lines.append(f"- {k}: {desc}")
        lines.append(f"  provider: {provider_type}")
        # If a JSON schema is provided for agent params, render it for the model to follow exactly
        agent_params_json_schema = None
        if isinstance(metadata, dict):
            agent_params_json_schema = metadata.get("agent_params_json_schema")
        if agent_params_json_schema:
            lines.append("  agent_params_json_schema (use this EXACTLY in action_details.tool_params):")
            import json
            lines.append("  ```json")
            lines.append("  " + json.dumps(agent_params_json_schema))
            lines.append("  ```")
    return "\n".join(lines)


def build_context(user_message: str, exec_log: List[Dict[str, Any]], full_tool_outputs: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    parts.append(f"User message:\n{user_message}")
    if full_tool_outputs:
        parts.append("Tool outputs (most recent first):")
        for item in reversed(full_tool_outputs):
            result = item.get("result")
            if result is not None:
                tool_key = item.get("tool_key") or result.get("tool")
                parts.append(f"- {tool_key}: {result}")
            else:
                tool_key = item.get("tool_key")
                parts.append(f"- {tool_key}: (no result)")
    if exec_log:
        parts.append("Execution log summary:")
        for e in exec_log[-10:]:  # last 10
            if e.get("type") == "agent":
                parts.append(f"  step {e['step']}: agent {e['agent_key']} → {e['decision']['action']}")
            elif e.get("type") == "tool":
                parts.append(f"  step {e['step']}: tool {e['tool_key']} status={e['status']}")
    return "\n".join(parts)


def build_prompt(base_prompt: str | None, context: str, constraints: str, tool_defs: str | None = None) -> str:
    parts: List[str] = []
    if base_prompt:
        parts.append(base_prompt)
    if tool_defs:
        parts.append(tool_defs)
    parts.append(constraints)
    parts.append(context)
    return "\n\n".join(parts)
