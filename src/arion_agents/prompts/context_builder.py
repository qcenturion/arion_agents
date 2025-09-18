from __future__ import annotations

from typing import Any, Dict, List
import json


def build_constraints(cfg) -> str:
    lines: List[str] = []
    # Action envelope statement tailored to what the agent can actually do
    actions: List[str] = []
    has_tools = bool(getattr(cfg, "equipped_tools", []) or [])
    has_routes = bool(getattr(cfg, "allowed_routes", []) or [])
    can_respond = bool(getattr(cfg, "allow_respond", True))
    if has_tools:
        actions.append("USE_TOOL")
    if has_routes:
        actions.append("ROUTE_TO_AGENT")
    if can_respond:
        actions.append("RESPOND")
    if actions:
        lines.append(
            f"You MUST respond as JSON with fields: action ({'|'.join(actions)}), action_reasoning (string), action_details (object)."
        )

    # Only describe tools if any are equipped
    tool_names: List[str] = []
    if has_tools:
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

    # Only describe routes if any exist
    if has_routes:
        lines.append("Allowed routes (exact agent keys):")
        for r in cfg.allowed_routes:
            lines.append(f"- {r}")

    # Tailor guidance per action availability
    if has_tools:
        lines.append("When using USE_TOOL, action_details must include tool_name and tool_params.")
    if has_routes:
        lines.append("When routing, action_details must include target_agent_name (use the exact agent key).")
    if can_respond:
        lines.append("When responding, put your payload in action_details.payload.")
        # Provide a minimal RESPOND example so agents know the exact envelope
        try:
            lines.append("Example for RESPOND (follow exactly):")
            respond_example = {
                "action": "RESPOND",
                "action_reasoning": "why final",
                "action_details": {"payload": {"message": "<final text>"}},
            }
            lines.append("```json")
            import json as _json
            lines.append(_json.dumps(respond_example))
            lines.append("```")
        except Exception:
            pass

    # Only show a USE_TOOL example when tools are present
    try:
        if has_tools and tool_names:
            first = tool_names[0]
            ts = cfg.tools_map.get(first)
            params_schema = getattr(ts, "params_schema", None) or (isinstance(ts, dict) and ts.get("params_schema")) or {}
            agent_fields = [name for name, spec in (params_schema or {}).items() if (spec or {}).get("source", "agent") == "agent"]
            example_params = {k: f"<{k}>" for k in agent_fields} or {"example": "value"}
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
    """Return a concise tools section with only what the agent needs.

    For each equipped tool, include:
      - tool key
      - one-line description
      - exact agent-facing JSON schema for tool_params

    Provider/endpoint/system details are intentionally omitted to avoid confusion.
    """
    equipped = list(getattr(cfg, "equipped_tools", []) or [])
    if not equipped:
        return ""
    lines: List[str] = []
    lines.append("Available Tools and Schemas (use EXACTLY these for tool_params):")
    for k in equipped:
        ts = cfg.tools_map.get(k)
        if not ts:
            continue
        desc = getattr(ts, "description", None) or (isinstance(ts, dict) and ts.get("description")) or ""
        metadata = getattr(ts, "metadata", None) or (isinstance(ts, dict) and ts.get("metadata")) or {}
        agent_schema = None
        if isinstance(metadata, dict):
            agent_schema = metadata.get("agent_params_json_schema")

        # Compose a compact JSON object for this tool
        tool_obj = {
            "tool": k,
            "description": desc or "",
            "tool_params_schema": agent_schema or {},
        }
        lines.append("```json")
        lines.append(json.dumps(tool_obj))
        lines.append("```")
    return "\n".join(lines)


def build_route_definitions(cfg) -> str:
    """Return a concise routes section mirroring the tool schema style.

    Includes the list of allowed route keys and a strict JSON schema for
    ROUTE_TO_AGENT action_details.
    """
    routes = list(getattr(cfg, "allowed_routes", []) or [])
    if not routes:
        return ""
    lines: List[str] = []
    lines.append("Available Routes and Schema (use EXACT agent keys):")
    route_schema = {
        "type": "object",
        "properties": {
            "target_agent_name": {"type": "string", "enum": routes},
            "context": {"type": "object"},
        },
        "required": ["target_agent_name"],
        "additionalProperties": False,
    }
    block = {
        "allowed_routes": routes,
        "route_params_schema": route_schema,
    }
    lines.append("```json")
    lines.append(json.dumps(block))
    lines.append("```")
    # Add a minimal example
    lines.append("Example for ROUTE_TO_AGENT (follow exactly; use exact key):")
    route_example = {
        "action": "ROUTE_TO_AGENT",
        "action_reasoning": "why route",
        "action_details": {"target_agent_name": routes[0]},
    }
    lines.append("```json")
    lines.append(json.dumps(route_example))
    lines.append("```")
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


def build_prompt(cfg, base_prompt: str | None, context: str, constraints: str, tool_defs: str | None = None, route_defs: str | None = None) -> str:
    parts: List[str] = []
    if base_prompt:
        parts.append(base_prompt)
    if tool_defs:
        parts.append(tool_defs)
    if route_defs:
        parts.append(route_defs)
    # Optionally include action schemas (strict) to guide the model (may duplicate info)
    # Keeping this for future unification; tools/routes sections already provide schemas.
    # parts.append(build_action_schemas(cfg))
    parts.append(constraints)
    parts.append(context)
    return "\n\n".join(parts)


def build_action_schemas(cfg) -> str:
    """Return strict JSON Schemas for actions and explicit enums for tools/routes.

    - USE_TOOL: tool_name is enum of equipped tools; tool_params must conform to the per-tool schema shown above.
    - ROUTE_TO_AGENT: target_agent_name is enum of allowed route keys (case-sensitive). Include strong language about EXACTLY one of.
    - RESPOND: payload is object|string.
    """
    tools = list(getattr(cfg, "equipped_tools", []) or [])
    routes = list(getattr(cfg, "allowed_routes", []) or [])

    # USE_TOOL envelope (tool_name enum only; per-tool params schema is specified in tool section)
    use_tool_schema = {
        "type": "object",
        "properties": {
            "tool_name": {"type": "string", "enum": tools},
            "tool_params": {"type": "object"},
        },
        "required": ["tool_name", "tool_params"],
        "additionalProperties": False,
    }

    # ROUTE_TO_AGENT schema with enum of allowed routes
    route_schema = {
        "type": "object",
        "properties": {
            "target_agent_name": {"type": "string", "enum": routes},
            "context": {"type": "object"},
        },
        "required": ["target_agent_name"],
        "additionalProperties": False,
    }

    # RESPOND schema
    respond_schema = {
        "type": "object",
        "properties": {
            "payload": {"type": ["object", "string"]},
        },
        "required": ["payload"],
        "additionalProperties": False,
    }

    lines: List[str] = []
    lines.append("Action Schemas (STRICT — follow EXACTLY):")
    if routes:
        lines.append(f"ROUTE_TO_AGENT target_agent_name must be EXACTLY one of: {' | '.join(routes)}")
    lines.append("USE_TOOL envelope:")
    lines.append("```json")
    lines.append(json.dumps(use_tool_schema))
    lines.append("```")
    lines.append("ROUTE_TO_AGENT envelope:")
    lines.append("```json")
    lines.append(json.dumps(route_schema))
    lines.append("```")
    lines.append("RESPOND envelope:")
    lines.append("```json")
    lines.append(json.dumps(respond_schema))
    lines.append("```")
    return "\n".join(lines)
