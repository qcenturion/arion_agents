from __future__ import annotations

from typing import Any, Dict, List
import json


def build_constraints(
    cfg, tool_defs: str | None = None, route_defs: str | None = None
) -> str:
    # Determine action flags up front
    has_tools = bool(getattr(cfg, "equipped_tools", []) or [])
    has_routes = bool(getattr(cfg, "allowed_routes", []) or [])
    can_respond = bool(getattr(cfg, "allow_respond", True))
    can_task_group = bool(getattr(cfg, "allow_task_group", False))
    can_task_respond = bool(getattr(cfg, "allow_task_respond", False))

    allowed_actions: List[str] = []
    if has_tools:
        allowed_actions.append("USE_TOOL")
    if has_routes:
        allowed_actions.append("ROUTE_TO_AGENT")
    if can_respond:
        allowed_actions.append("RESPOND")
    if can_task_group:
        allowed_actions.append("TASK_GROUP")
    if can_task_respond:
        allowed_actions.append("TASK_RESPOND")

    lines: List[str] = []
    if allowed_actions:
        lines.append(
            "You MUST reply with EXACTLY ONE of the following allowed actions and match the corresponding JSON schema."
        )
        lines.append(f"Allowed actions: {', '.join(allowed_actions)}")

    # Action sections in consistent order
    if has_tools:
        lines.append(
            "\n=== USE_TOOL action ===\nYou MUST follow this schema:"
        )
        lines.append("```json")
        lines.append(
            json.dumps(
                {
                    "action": "USE_TOOL",
                    "action_reasoning": "<why you chose this tool>",
                    "action_details": {
                        "tool_name": "<exact tool name>",
                        "tool_params": {"<param>": "<value>"},
                    },
                }
            )
        )
        lines.append("```")
        lines.append("tool_params MUST conform to the tool schemas listed below.")
        tool_names: List[str] = []
        for k in cfg.equipped_tools:
            ts = cfg.tools_map.get(k)
            if not ts:
                continue
            params_schema = (
                getattr(ts, "params_schema", None)
                or (isinstance(ts, dict) and ts.get("params_schema"))
                or {}
            )
            tool_names.append(k)
        try:
            first = tool_names[0] if tool_names else "<tool>"
            tool_entry = cfg.tools_map.get(first)
            if isinstance(tool_entry, dict):
                params_schema = tool_entry.get("params_schema") or {}
            else:
                params_schema = getattr(tool_entry, "params_schema", {}) or {}
            agent_fields = [
                name
                for name, spec in (params_schema or {}).items()
                if (spec or {}).get("source", "agent") == "agent"
            ]
            example_params = {name: f"<{name}>" for name in agent_fields}
            if not example_params:
                example_params = {"param": "<value>"}
            lines.append("Example:")
            lines.append("```json")
            lines.append(
                json.dumps(
                    {
                        "action": "USE_TOOL",
                        "action_reasoning": "why this tool",
                        "action_details": {
                            "tool_name": first,
                            "tool_params": example_params,
                        },
                    }
                )
            )
            lines.append("```")
        except Exception:
            pass

        if tool_defs:
            lines.append(tool_defs)

    if has_routes:
        lines.append(
            "\n=== ROUTE_TO_AGENT action ===\nYou MUST follow this schema:"
        )
        lines.append("```json")
        sample_route = cfg.allowed_routes[0] if cfg.allowed_routes else "<agent>"
        lines.append(
            json.dumps(
                {
                    "action": "ROUTE_TO_AGENT",
                    "action_reasoning": "<why you are handing off>",
                    "action_details": {
                        "target_agent_name": sample_route,
                        "context": {"handoff_summary": "<details to pass>"},
                    },
                }
            )
        )
        lines.append("```")
        if route_defs:
            lines.append(route_defs)
        lines.append(
            "Use action_details.context to pass any structured handoff data the next agent needs (conversation transcripts, findings, constraints). The orchestrator injects this object into their prompt context verbatim."
        )
        if not can_respond:
            lines.append(
                "You are not allowed to RESPOND directly; hand off with ROUTE_TO_AGENT when you have sufficient evidence."
            )
        lines.append("Always return JSON matching one of the allowed envelopes; never emit free-form text.")

    if can_respond:
        lines.append(
            "\n=== RESPOND action ===\nYou MUST follow this schema:"
        )
        lines.append("```json")
        lines.append(
            json.dumps(
                {
                    "action": "RESPOND",
                    "action_reasoning": "<why final>",
                    "action_details": {"payload": {"message": "<final text>"}},
                }
            )
        )
        lines.append("```")
        additional_guidance = getattr(cfg, "respond_payload_guidance", None)
        if additional_guidance:
            lines.append(f"RESPOND guidance: {additional_guidance}")
        payload_schema = getattr(cfg, "respond_payload_schema", None)
        if payload_schema:
            try:
                lines.append("RESPOND payload schema (follow exactly):")
                lines.append("```json")
                lines.append(json.dumps(payload_schema))
                lines.append("```")
            except Exception:
                lines.append("RESPOND payload schema provided but could not be serialized for display.")
        payload_example = getattr(cfg, "respond_payload_example", None)
        if payload_example:
            try:
                lines.append("Example RESPOND payload structure:")
                lines.append("```json")
                lines.append(json.dumps(payload_example))
                lines.append("```")
            except Exception:
                lines.append("RESPOND payload example provided but could not be serialized for display.")

    if can_task_group:
        lines.append(
            "\n=== TASK_GROUP action ===\nWhen using TASK_GROUP, action_details.tasks must be a list of task objects with unique task_id values when possible."
        )
        lines.append(
            "Each task requires task_type (use_tool|delegate_agent) and retry_policy.attempts (defaults to 2)."
        )
        lines.append(
            "use_tool tasks mirror the USE_TOOL schema; delegate_agent tasks require delegation_details with agent_key and assignment text."
        )
        try:
            example_tool = cfg.equipped_tools[0] if cfg.equipped_tools else "tool_key"
            task_group_example = {
                "action": "TASK_GROUP",
                "action_reasoning": "plan parallel tasks",
                "action_details": {
                    "group_id": "group-1",
                    "tasks": [
                        {
                            "task_type": "use_tool",
                            "task_id": "geocode",
                            "tool_name": example_tool,
                            "tool_params": {"example": "value"},
                            "retry_policy": {"attempts": 2},
                        },
                        {
                            "task_type": "delegate_agent",
                            "task_id": "summarize",
                            "retry_policy": {"attempts": 2},
                            "delegation_details": [
                                {
                                    "agent_key": "delegate_agent_1",
                                    "assignment": "Summarize assigned section",
                                    "context_overrides": {},
                                    "max_steps": 3,
                                }
                            ],
                        },
                    ],
                },
            }
            lines.append("Example:")
            lines.append("```json")
            lines.append(json.dumps(task_group_example))
            lines.append("```")
        except Exception:
            pass
    if can_task_respond:
        lines.append(
            "\n=== TASK_RESPOND action ===\nUse TASK_RESPOND to finish delegated work; place the delegated result in action_details.payload."
        )
        lines.append("Example:")
        lines.append("```json")
        lines.append(
            json.dumps(
                {
                    "action": "TASK_RESPOND",
                    "action_reasoning": "deliver delegated result",
                    "action_details": {"payload": {"summary": "<delegated output>"}},
                }
            )
        )
        lines.append("```")

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
        desc = (
            getattr(ts, "description", None)
            or (isinstance(ts, dict) and ts.get("description"))
            or ""
        )
        metadata = (
            getattr(ts, "metadata", None)
            or (isinstance(ts, dict) and ts.get("metadata"))
            or {}
        )
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
    lines.append("Available Routes and Schema (use EXACT agent names):")
    route_descriptions = getattr(cfg, "route_descriptions", {}) or {}
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
        "route_descriptions": [
            {"agent": r, "description": route_descriptions.get(r, "")} for r in routes
        ],
    }
    lines.append("```json")
    lines.append(json.dumps(block))
    lines.append("```")
    # Add a minimal example
    if any(route_descriptions.get(r) for r in routes):
        lines.append("Route guides:")
        for r in routes:
            desc = route_descriptions.get(r)
            if desc:
                lines.append(f"- {r}: {desc}")
    lines.append(
        "Example for ROUTE_TO_AGENT (follow exactly; use exact agent name and populate context as needed):"
    )
    sample_route = routes[0]
    route_example = {
        "action": "ROUTE_TO_AGENT",
        "action_reasoning": f"Routing to {sample_route} because it best fits the user request.",
        "action_details": {
            "target_agent_name": sample_route,
            "context": {"handoff_summary": "<details to pass>"},
        },
    }
    lines.append("```json")
    lines.append(json.dumps(route_example))
    lines.append("```")
    return "\n".join(lines)


def build_context(
    user_message: str,
    exec_log: List[Dict[str, Any]],
    full_tool_outputs: List[Dict[str, Any]],
    handoff_context: Dict[str, Any] | None = None,
) -> str:
    parts: List[str] = []
    parts.append(f"User message:\n{user_message}")
    if handoff_context:
        parts.append("Context handed off from previous agent:")
        try:
            parts.append(json.dumps(handoff_context))
        except Exception:
            parts.append(str(handoff_context))
    if full_tool_outputs:
        parts.append("Tool outputs (most recent first):")
        for item in reversed(full_tool_outputs):
            tool_key = item.get("tool_key") or "<unknown>"
            result = item.get("result") or {}
            if tool_key == "dialogflow_cx_tester":
                summary = result.get("summary") or {}
                if isinstance(summary, dict):
                    if set(summary.keys()) == {"message"}:
                        formatted = summary.get("message")
                    else:
                        formatted = {
                            "message": summary.get("message"),
                            "intent": summary.get("intent"),
                            "intent_confidence": summary.get("intent_confidence"),
                        }
                else:
                    formatted = summary
                parts.append(f"- {tool_key}: {formatted}")
            else:
                parts.append(f"- {tool_key}: {result}")
    if exec_log:
        parts.append("Execution log summary:")
        for e in exec_log[-10:]:  # last 10
            if e.get("type") == "agent":
                parts.append(
                    f"  step {e['step']}: agent {e['agent_key']} → {e['decision']['action']}"
                )
            elif e.get("type") == "tool":
                parts.append(
                    f"  step {e['step']}: tool {e['tool_key']} status={e['status']}"
                )
            elif e.get("type") == "task_group":
                group_id = e.get("group_id")
                group_status = e.get("status")
                parts.append(
                    f"  step {e['step']}: task_group {group_id} status={group_status}"
                )
                for child in e.get("tasks", [])[:3]:  # summarize first few tasks
                    parts.append(
                        f"    - task {child.get('task_id')}: {child.get('task_type')} status={child.get('status')}"
                    )
    return "\n".join(parts)


def build_prompt(
    cfg,
    base_prompt: str | None,
    context: str,
    constraints: str,
) -> str:
    parts: List[str] = []
    if base_prompt:
        parts.append(base_prompt)
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
        lines.append(
            f"ROUTE_TO_AGENT target_agent_name must be EXACTLY one of: {' | '.join(routes)}"
        )
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
