from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ValidationError
from sqlmodel import SQLModel, Session, select, func

from .db import get_session
from .config_models import (
    Agent,
    Network,
    NetworkTool,
    Tool,
    NetworkVersion,
    CompiledSnapshot,
)
from .system_params import available_system_param_keys
from .config_validation import (
    NetworkConstraintError,
    validate_network_constraints,
)

from .logs.execution_log_policy import ExecutionLogPolicy

logger = logging.getLogger(__name__)
router = APIRouter()


_GEMINI_MODEL_CATALOG = [
    {
        "key": "gemini-2.5-pro",
        "label": "Gemini 2.5 Pro",
        "inputs": "Audio, images, videos, text, and PDF",
        "output": "Text",
        "optimized_for": "Enhanced reasoning, multimodal understanding, advanced coding",
    },
    {
        "key": "gemini-2.5-flash",
        "label": "Gemini 2.5 Flash",
        "inputs": "Audio, images, videos, and text",
        "output": "Text",
        "optimized_for": "Adaptive thinking with cost efficiency",
    },
    {
        "key": "gemini-2.5-flash-lite",
        "label": "Gemini 2.5 Flash-Lite",
        "inputs": "Audio, images, videos, and text",
        "output": "Text",
        "optimized_for": "Ultra low latency and lightweight cost-sensitive tasks",
    },
]


@router.get("/llm/models")
def list_llm_models() -> list[dict]:
    default_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    items: list[dict] = []
    for item in _GEMINI_MODEL_CATALOG:
        enriched = dict(item)
        enriched["is_default"] = enriched.get("key") == default_model
        items.append(enriched)
    return items


def get_db_dep() -> Session:
    # SQLModel Session is directly usable as a context manager
    with get_session() as s:
        yield s


def _lc(s: str) -> str:
    return s.strip().lower()


@router.get("/system_params/defaults")
def get_system_param_defaults() -> dict:
    return available_system_param_keys()


# Define Pydantic models for API input/output where they differ from the DB model.
# For simple cases, we can use the SQLModel directly.


class AgentCreate(SQLModel):
    key: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    allow_respond: bool = True
    is_default: bool = False
    additional_data: dict = Field(default_factory=dict)
    prompt_template: Optional[str] = None


class AgentOut(SQLModel):
    """API output model for an Agent, including computed fields."""

    id: int
    network_id: int
    key: str
    display_name: Optional[str]
    description: Optional[str]
    allow_respond: bool
    is_default: bool = False
    prompt_template: Optional[str] = None
    equipped_tools: List[str] = Field(default_factory=list)
    allowed_routes: List[str] = Field(default_factory=list)


class SetTools(SQLModel):
    tool_keys: List[str]


class SetRoutes(SQLModel):
    agent_keys: List[str]


class PublishRequest(SQLModel):
    notes: Optional[str] = None
    created_by: Optional[str] = None
    published_by: Optional[str] = None


class ToolCreate(BaseModel):
    key: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    provider_type: Optional[str] = None
    params_schema: dict = Field(default_factory=dict)
    secret_ref: Optional[str] = None
    additional_data: dict = Field(default_factory=dict)


class ToolOut(BaseModel):
    id: int
    key: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    provider_type: Optional[str] = None
    params_schema: dict = Field(default_factory=dict)
    secret_ref: Optional[str] = None
    additional_data: dict = Field(default_factory=dict)


def _to_tool_out(t: Tool) -> ToolOut:
    return ToolOut(
        id=t.id,  # type: ignore[arg-type]
        key=t.key,
        display_name=t.display_name,
        description=t.description,
        provider_type=t.provider_type,
        params_schema=t.params_schema or {},
        secret_ref=t.secret_ref,
        additional_data=t.additional_data or {},
    )


class ToolUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    provider_type: Optional[str] = None
    params_schema: Optional[dict] = None
    secret_ref: Optional[str] = None
    additional_data: Optional[dict] = None


class ToolTestRequest(BaseModel):
    params: dict = Field(default_factory=dict)
    system_params: dict = Field(default_factory=dict)
    additional_data_override: Optional[dict] = None


class ToolTestResponse(BaseModel):
    ok: bool
    status: int
    result: Optional[dict] = None
    error: Optional[str] = None


class SnapshotOut(BaseModel):
    snapshot_id: str
    graph_version_id: str
    network_id: str
    created_at: Optional[str] = None


def _validate_network_or_raise(db: Session, network_id: int) -> None:
    try:
        db.flush()
        validate_network_constraints(db, network_id)
    except NetworkConstraintError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "network_constraint_violation",
                "message": exc.message,
            },
        )


def _combine_description_prompt(
    description: Optional[str], prompt: Optional[str]
) -> Optional[str]:
    parts: List[str] = []
    if isinstance(description, str) and description.strip():
        parts.append(description.strip())
    if isinstance(prompt, str) and prompt.strip():
        parts.append(prompt.strip())
    if not parts:
        return None
    return "\n\n".join(parts)


def _load_compiled_agent_metadata(
    db: Session, network_ids: List[int]
) -> Tuple[Dict[int, Dict[str, Optional[str]]], Dict[int, Optional[str]]]:
    """Return compiled prompt map and default agent key for the given networks."""

    if not network_ids:
        return {}, {}

    prompts_map: Dict[int, Dict[str, Optional[str]]] = {}
    default_map: Dict[int, Optional[str]] = {}

    nets = db.exec(select(Network).where(Network.id.in_(list(network_ids)))).all()
    version_ids = {
        net.id: net.current_version_id for net in nets if net.current_version_id
    }
    if not version_ids:
        for net in nets:
            prompts_map[net.id] = {}
            default_map[net.id] = None
        return prompts_map, default_map

    snapshot_version_ids = list(version_ids.values())
    snapshots = db.exec(
        select(CompiledSnapshot).where(
            CompiledSnapshot.network_version_id.in_(snapshot_version_ids)
        )
    ).all()
    snapshot_by_version = {snap.network_version_id: snap for snap in snapshots}

    for net in nets:
        prompts: Dict[str, Optional[str]] = {}
        default_key: Optional[str] = None
        ver_id = version_ids.get(net.id)
        if ver_id:
            snap = snapshot_by_version.get(ver_id)
            if snap and isinstance(snap.compiled_graph, dict):
                graph = snap.compiled_graph
                agents_data = graph.get("agents", [])
                if isinstance(agents_data, list):
                    for entry in agents_data:
                        if not isinstance(entry, dict):
                            continue
                        key = entry.get("key")
                        if not isinstance(key, str):
                            continue
                        prompts[key] = _combine_description_prompt(
                            entry.get("description"), entry.get("prompt")
                        )
                default = graph.get("default_agent_key")
                if isinstance(default, str):
                    default_key = default
        prompts_map[net.id] = prompts
        default_map[net.id] = default_key

    return prompts_map, default_map


def _resolve_agent_out(
    agent: Agent,
    *,
    prompt_fallback: Optional[str] = None,
    default_fallback: bool = False,
) -> AgentOut:
    prompt_template = None
    addl = agent.additional_data or {}
    if isinstance(addl, dict):
        prompt_template = addl.get("prompt_template")
    if not prompt_template and prompt_fallback:
        prompt_template = prompt_fallback

    is_default = agent.is_default or default_fallback

    return AgentOut(
        id=agent.id,
        network_id=agent.network_id,
        key=agent.key,
        display_name=agent.display_name,
        description=agent.description,
        allow_respond=agent.allow_respond,
        is_default=is_default,
        prompt_template=prompt_template,
        equipped_tools=[t.key for t in agent.equipped_tools],
        allowed_routes=[r.key for r in agent.allowed_routes],
    )


@router.get("/tools", response_model=List[ToolOut])
def list_tools(db: Session = Depends(get_db_dep)):
    tools = db.exec(select(Tool)).all()
    return [_to_tool_out(t) for t in tools]


@router.get("/agents", response_model=List[AgentOut])
def list_all_agents(db: Session = Depends(get_db_dep)):
    agents = db.exec(
        select(Agent).order_by(Agent.network_id, func.lower(Agent.key))
    ).all()
    network_ids = {agent.network_id for agent in agents}
    prompts_map, default_map = _load_compiled_agent_metadata(db, list(network_ids))
    results: List[AgentOut] = []
    for agent in agents:
        prompt_fallback = prompts_map.get(agent.network_id, {}).get(agent.key)
        default_fallback = default_map.get(agent.network_id) == agent.key
        results.append(
            _resolve_agent_out(
                agent,
                prompt_fallback=prompt_fallback,
                default_fallback=default_fallback,
            )
        )
    return results


@router.get("/snapshots", response_model=List[SnapshotOut])
def list_snapshots(db: Session = Depends(get_db_dep)):
    rows = db.exec(
        select(CompiledSnapshot, NetworkVersion.network_id)
        .join(
            NetworkVersion,
            NetworkVersion.id == CompiledSnapshot.network_version_id,
        )
        .order_by(CompiledSnapshot.created_at.desc())
    ).all()
    items: List[SnapshotOut] = []
    for snapshot, network_id in rows:
        created_at = snapshot.created_at.isoformat() if snapshot.created_at else None
        items.append(
            SnapshotOut(
                snapshot_id=str(snapshot.id),
                graph_version_id=str(snapshot.network_version_id),
                network_id=str(network_id),
                created_at=created_at,
            )
        )
    return items


@router.post("/tools", response_model=ToolOut, status_code=status.HTTP_201_CREATED)
def create_tool(payload: ToolCreate, db: Session = Depends(get_db_dep)):
    # Check for existing key
    if db.exec(select(Tool).where(func.lower(Tool.key) == _lc(payload.key))).first():
        raise HTTPException(status_code=409, detail="tool key exists")
    # Require agent_params_json_schema in additional_data
    addl = payload.additional_data or {}
    schema = None
    if isinstance(addl, dict):
        schema = addl.get("agent_params_json_schema")
    if not isinstance(schema, dict):
        raise HTTPException(
            status_code=400,
            detail="additional_data.agent_params_json_schema is required and must be an object (agent-facing JSON Schema)",
        )
    # Map API DTO to ORM model (meta <- metadata)
    t = Tool(
        key=payload.key,
        display_name=payload.display_name,
        description=payload.description,
        provider_type=payload.provider_type,
        params_schema=payload.params_schema or {},
        secret_ref=payload.secret_ref,
        additional_data=addl,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return _to_tool_out(t)


@router.patch("/tools/{tool_id}", response_model=ToolOut)
def patch_tool(tool_id: int, payload: ToolUpdate, db: Session = Depends(get_db_dep)):
    t = db.get(Tool, tool_id)
    if not t:
        raise HTTPException(status_code=404, detail="tool not found")
    if payload.display_name is not None:
        t.display_name = payload.display_name
    if payload.description is not None:
        t.description = payload.description
    if payload.provider_type is not None:
        t.provider_type = payload.provider_type
    if payload.params_schema is not None:
        t.params_schema = payload.params_schema
    if payload.secret_ref is not None:
        t.secret_ref = payload.secret_ref
    if payload.additional_data is not None:
        addl = payload.additional_data or {}
        schema = (
            addl.get("agent_params_json_schema") if isinstance(addl, dict) else None
        )
        if not isinstance(schema, dict):
            raise HTTPException(
                status_code=400,
                detail="additional_data.agent_params_json_schema is required and must be an object (agent-facing JSON Schema)",
            )
        t.additional_data = addl
    db.add(t)
    db.commit()
    db.refresh(t)
    return _to_tool_out(t)


@router.delete("/tools/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tool(tool_id: int, db: Session = Depends(get_db_dep)):
    tool = db.get(Tool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="tool not found")
    # Check if this tool is in use by any networks
    usage_count = db.exec(
        select(func.count(NetworkTool.id)).where(NetworkTool.source_tool_id == tool_id)
    ).one()
    if usage_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete tool '{tool.key}' because it is in use by {usage_count} network(s).",
        )
    db.delete(tool)
    db.commit()


@router.post("/tools/{tool_id}/test_connection", response_model=ToolTestResponse)
def test_tool_connection(
    tool_id: int, payload: ToolTestRequest, db: Session = Depends(get_db_dep)
):
    t = db.get(Tool, tool_id)
    if not t:
        raise HTTPException(status_code=404, detail="tool not found")
    try:
        from arion_agents.tools.base import ToolConfig as _ToolConfig, ToolRunInput
        from arion_agents.tools.registry import instantiate_tool
        from arion_agents.secrets import resolve_secret

        meta = dict(t.additional_data or {})
        if payload.additional_data_override:
            meta.update(payload.additional_data_override)
        cfg = _ToolConfig(
            key=t.key,
            provider_type=t.provider_type or "",
            params_schema=t.params_schema or {},
            secret_ref=t.secret_ref,
            metadata=meta,
        )
        tool = instantiate_tool(cfg, resolve_secret(t.secret_ref))
        out = tool.run(
            ToolRunInput(
                params=payload.params or {},
                system=payload.system_params or {},
                metadata=meta,
            )
        )
        if out.ok:
            return ToolTestResponse(ok=True, status=200, result=out.result)
        return ToolTestResponse(ok=False, status=502, error=out.error)
    except Exception as e:
        return ToolTestResponse(ok=False, status=500, error=str(e))


@router.post("/networks", response_model=Network, status_code=status.HTTP_201_CREATED)
def create_network(payload: Network, db: Session = Depends(get_db_dep)):
    if db.exec(
        select(Network).where(func.lower(Network.name) == _lc(payload.name))
    ).first():
        raise HTTPException(status_code=409, detail="network name exists")
    payload.status = "draft"
    db.add(payload)
    db.commit()
    db.refresh(payload)
    return payload


@router.get("/networks", response_model=List[Network])
def list_networks(db: Session = Depends(get_db_dep)):
    return db.exec(select(Network)).all()


@router.get("/networks/{network_id}/graph")
def get_network_graph(network_id: int, db: Session = Depends(get_db_dep)):
    net = db.get(Network, network_id)
    if not net:
        raise HTTPException(status_code=404, detail="network not found")
    agents = db.exec(select(Agent).where(Agent.network_id == network_id)).all()
    nts = db.exec(select(NetworkTool).where(NetworkTool.network_id == network_id)).all()

    agent_nodes = []
    adjacency = []
    for a in agents:
        agent_nodes.append(
            {
                "id": a.id,
                "key": a.key,
                "display_name": a.display_name,
                "allow_respond": a.allow_respond,
                "is_default": a.is_default,
                "equipped_tools": [t.key for t in a.equipped_tools],
                "allowed_routes": [r.key for r in a.allowed_routes],
                "prompt_template": (a.additional_data or {}).get("prompt_template")
                if isinstance(a.additional_data, dict)
                else None,
            }
        )
        for r in a.allowed_routes:
            adjacency.append({"from": a.key, "to": r.key})

    tools = [
        {
            "id": nt.id,
            "key": nt.key,
            "display_name": nt.display_name,
            "provider_type": nt.provider_type,
            "params_schema": nt.params_schema or {},
            "secret_ref": nt.secret_ref,
            "additional_data": nt.additional_data or {},
            "description": nt.description,
            "source_tool_id": nt.source_tool_id,
        }
        for nt in nts
    ]

    return {
        "network": {
            "id": net.id,
            "name": net.name,
            "status": net.status,
            "description": net.description,
            "additional_data": net.additional_data or {},
        },
        "agents": agent_nodes,
        "tools": tools,
        "adjacency": adjacency,
        "current_version_id": net.current_version_id,
    }


class NetworkUpdate(SQLModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None  # draft|published|archived
    additional_data: Optional[dict] = None


@router.patch("/networks/{network_id}", response_model=Network)
def patch_network(
    network_id: int, payload: NetworkUpdate, db: Session = Depends(get_db_dep)
):
    net = db.get(Network, network_id)
    if not net:
        raise HTTPException(status_code=404, detail="network not found")
    if payload.name is not None:
        # uniqueness check (case-insensitive)
        exists = db.exec(
            select(Network).where(
                Network.id != network_id, func.lower(Network.name) == _lc(payload.name)
            )
        ).first()
        if exists:
            raise HTTPException(status_code=409, detail="network name exists")
        net.name = payload.name
    if payload.description is not None:
        net.description = payload.description
    if payload.status is not None:
        s = payload.status.strip().lower()
        if s not in {"draft", "published", "archived"}:
            raise HTTPException(status_code=400, detail="invalid status")
        net.status = s
    if payload.additional_data is not None:
        net.additional_data = payload.additional_data or {}
    db.add(net)
    db.commit()
    db.refresh(net)
    return net


@router.delete("/networks/{network_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_network(network_id: int, db: Session = Depends(get_db_dep)):
    net = db.get(Network, network_id)
    if not net:
        raise HTTPException(status_code=404, detail="network not found")
    # The ondelete="CASCADE" in the schema handles cleanup of children.
    # A 500 error will be returned by the DB if a RESTRICT constraint fails.
    db.delete(net)
    db.commit()


@router.post("/networks/{network_id}/tools", response_model=List[str])
def add_tools_to_network(
    network_id: int, payload: SetTools, db: Session = Depends(get_db_dep)
):
    net = db.get(Network, network_id)
    if not net:
        raise HTTPException(status_code=404, detail="network not found")
    if not payload.tool_keys:
        return []

    keys = [_lc(k) for k in payload.tool_keys]
    globals_ = db.exec(select(Tool).where(func.lower(Tool.key).in_(keys))).all()
    found = {g.key.lower(): g for g in globals_}
    missing = sorted(set(keys) - set(found.keys()))
    if missing:
        raise HTTPException(
            status_code=400, detail=f"unknown tool keys: {', '.join(missing)}"
        )

    created_keys: List[str] = []
    for k in keys:
        g = found[k]
        # Enforce that the global tool includes agent_params_json_schema
        addl = g.additional_data or {}
        schema = (
            addl.get("agent_params_json_schema") if isinstance(addl, dict) else None
        )
        if not isinstance(schema, dict):
            raise HTTPException(
                status_code=400,
                detail=f"tool '{g.key}' is missing additional_data.agent_params_json_schema; define it before adding to a network",
            )
        exists = db.exec(
            select(NetworkTool).where(
                NetworkTool.network_id == network_id,
                func.lower(NetworkTool.key) == k,
            )
        ).first()
        if exists:
            logger.debug(
                "NetworkTool exists; skipping: network_id=%s key=%s", network_id, k
            )
            continue
        nt = NetworkTool(
            network_id=network_id,
            source_tool_id=g.id,  # type: ignore[arg-type]
            key=g.key,
            display_name=g.display_name,
            description=g.description,
            provider_type=g.provider_type,
            params_schema=g.params_schema or {},
            secret_ref=g.secret_ref,
            additional_data=g.additional_data or {},
        )
        logger.debug(
            "Creating NetworkTool from Tool: network_id=%s source_tool_id=%s key=%s",
            network_id,
            g.id,
            g.key,
        )
        db.add(nt)
        created_keys.append(g.key)
    db.commit()
    return created_keys


class NetworkToolOut(BaseModel):
    id: int
    key: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    provider_type: Optional[str] = None
    params_schema: dict = Field(default_factory=dict)
    secret_ref: Optional[str] = None
    additional_data: dict = Field(default_factory=dict)
    source_tool_id: int


def _to_network_tool_out(nt: NetworkTool) -> NetworkToolOut:
    return NetworkToolOut(
        id=nt.id,  # type: ignore[arg-type]
        key=nt.key,
        display_name=nt.display_name,
        description=nt.description,
        provider_type=nt.provider_type,
        params_schema=nt.params_schema or {},
        secret_ref=nt.secret_ref,
        additional_data=nt.additional_data or {},
        source_tool_id=nt.source_tool_id,
    )


@router.get("/networks/{network_id}/tools", response_model=List[NetworkToolOut])
def list_network_tools(network_id: int, db: Session = Depends(get_db_dep)):
    if not db.get(Network, network_id):
        raise HTTPException(status_code=404, detail="network not found")
    nts = db.exec(select(NetworkTool).where(NetworkTool.network_id == network_id)).all()
    return [_to_network_tool_out(nt) for nt in nts]


class NetworkToolPatch(BaseModel):
    params_schema: Optional[dict] = None
    additional_data: Optional[dict] = None


@router.patch("/networks/{network_id}/tools/{key}", response_model=NetworkToolOut)
def patch_network_tool(
    network_id: int,
    key: str,
    payload: NetworkToolPatch,
    db: Session = Depends(get_db_dep),
):
    nt = db.exec(
        select(NetworkTool).where(
            NetworkTool.network_id == network_id,
            func.lower(NetworkTool.key) == _lc(key),
        )
    ).first()
    if not nt:
        raise HTTPException(status_code=404, detail="network tool not found")
    if payload.params_schema is not None:
        nt.params_schema = payload.params_schema
    if payload.additional_data is not None:
        nt.additional_data = payload.additional_data
    db.add(nt)
    db.commit()
    db.refresh(nt)
    return _to_network_tool_out(nt)


@router.delete(
    "/networks/{network_id}/tools/{key}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_network_tool(network_id: int, key: str, db: Session = Depends(get_db_dep)):
    nt = db.exec(
        select(NetworkTool).where(
            NetworkTool.network_id == network_id,
            func.lower(NetworkTool.key) == _lc(key),
        )
    ).first()
    if not nt:
        raise HTTPException(status_code=404, detail="network tool not found")
    db.delete(nt)
    db.commit()


@router.post(
    "/networks/{network_id}/agents",
    response_model=AgentOut,
    status_code=status.HTTP_201_CREATED,
)
def create_agent(
    network_id: int, payload: AgentCreate, db: Session = Depends(get_db_dep)
):
    if not db.get(Network, network_id):
        raise HTTPException(status_code=404, detail="network not found")
    if db.exec(
        select(Agent).where(
            Agent.network_id == network_id, func.lower(Agent.key) == _lc(payload.key)
        )
    ).first():
        raise HTTPException(status_code=409, detail="agent key exists")

    # Construct explicitly to satisfy required FK at validation time
    addl = payload.additional_data or {}
    if payload.prompt_template:
        addl = dict(addl)
        addl["prompt_template"] = payload.prompt_template
    agent = Agent(
        network_id=network_id,
        key=payload.key,
        display_name=payload.display_name,
        description=payload.description,
        allow_respond=payload.allow_respond,
        is_default=payload.is_default,
        additional_data=addl,
    )
    db.add(agent)
    _validate_network_or_raise(db, network_id)
    db.commit()
    db.refresh(agent)
    prompts_map, default_map = _load_compiled_agent_metadata(db, [network_id])
    return _resolve_agent_out(
        agent,
        prompt_fallback=prompts_map.get(network_id, {}).get(agent.key),
        default_fallback=default_map.get(network_id) == agent.key,
    )


class AgentUpdate(SQLModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    allow_respond: Optional[bool] = None
    is_default: Optional[bool] = None
    additional_data: Optional[dict] = None
    prompt_template: Optional[str] = None


@router.patch("/networks/{network_id}/agents/{agent_id}", response_model=AgentOut)
def patch_agent(
    network_id: int,
    agent_id: int,
    payload: AgentUpdate,
    db: Session = Depends(get_db_dep),
):
    a = db.get(Agent, agent_id)
    if not a or a.network_id != network_id:
        raise HTTPException(status_code=404, detail="agent not found")
    if payload.display_name is not None:
        a.display_name = payload.display_name
    if payload.description is not None:
        a.description = payload.description
    if payload.allow_respond is not None:
        a.allow_respond = bool(payload.allow_respond)
    if payload.is_default is not None:
        a.is_default = bool(payload.is_default)
    if payload.additional_data is not None:
        a.additional_data = payload.additional_data
    if payload.prompt_template is not None:
        addl = dict(a.additional_data or {})
        if payload.prompt_template == "":
            addl.pop("prompt_template", None)
        else:
            addl["prompt_template"] = payload.prompt_template
        a.additional_data = addl
    db.add(a)
    _validate_network_or_raise(db, network_id)
    db.commit()
    db.refresh(a)
    prompts_map, default_map = _load_compiled_agent_metadata(db, [network_id])
    return _resolve_agent_out(
        a,
        prompt_fallback=prompts_map.get(network_id, {}).get(a.key),
        default_fallback=default_map.get(network_id) == a.key,
    )


@router.get("/networks/{network_id}/agents", response_model=List[AgentOut])
def list_agents(network_id: int, db: Session = Depends(get_db_dep)):
    if not db.get(Network, network_id):
        raise HTTPException(status_code=404, detail="network not found")
    agents = db.exec(select(Agent).where(Agent.network_id == network_id)).all()
    prompts_map, default_map = _load_compiled_agent_metadata(db, [network_id])
    return [
        _resolve_agent_out(
            a,
            prompt_fallback=prompts_map.get(network_id, {}).get(a.key),
            default_fallback=default_map.get(network_id) == a.key,
        )
        for a in agents
    ]


@router.get("/networks/{network_id}/agents/{agent_id}", response_model=AgentOut)
def get_agent(network_id: int, agent_id: int, db: Session = Depends(get_db_dep)):
    a = db.get(Agent, agent_id)
    if not a or a.network_id != network_id:
        raise HTTPException(status_code=404, detail="agent not found")
    prompts_map, default_map = _load_compiled_agent_metadata(db, [network_id])
    return _resolve_agent_out(
        a,
        prompt_fallback=prompts_map.get(network_id, {}).get(a.key),
        default_fallback=default_map.get(network_id) == a.key,
    )


@router.delete(
    "/networks/{network_id}/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_agent(network_id: int, agent_id: int, db: Session = Depends(get_db_dep)):
    a = db.get(Agent, agent_id)
    if not a or a.network_id != network_id:
        raise HTTPException(status_code=404, detail="agent not found")
    db.delete(a)
    _validate_network_or_raise(db, network_id)
    db.commit()


@router.put("/networks/{network_id}/agents/{agent_id}/tools", response_model=AgentOut)
def set_agent_tools(
    network_id: int, agent_id: int, payload: SetTools, db: Session = Depends(get_db_dep)
):
    a = db.get(Agent, agent_id)
    if not a or a.network_id != network_id:
        raise HTTPException(status_code=404, detail="agent not found")

    keys = [_lc(k) for k in payload.tool_keys]
    if keys:
        nts = db.exec(
            select(NetworkTool).where(
                NetworkTool.network_id == network_id,
                func.lower(NetworkTool.key).in_(keys),
            )
        ).all()
        found = {t.key.lower() for t in nts}
        missing = sorted(set(keys) - found)
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"unknown network tool keys: {', '.join(missing)}",
            )
        a.equipped_tools = nts
    else:
        a.equipped_tools = []
    db.add(a)
    db.commit()
    db.refresh(a)
    prompts_map, default_map = _load_compiled_agent_metadata(db, [network_id])
    return _resolve_agent_out(
        a,
        prompt_fallback=prompts_map.get(network_id, {}).get(a.key),
        default_fallback=default_map.get(network_id) == a.key,
    )


@router.put("/networks/{network_id}/agents/{agent_id}/routes", response_model=AgentOut)
def set_agent_routes(
    network_id: int,
    agent_id: int,
    payload: SetRoutes,
    db: Session = Depends(get_db_dep),
):
    a = db.get(Agent, agent_id)
    if not a or a.network_id != network_id:
        raise HTTPException(status_code=404, detail="agent not found")

    keys = [_lc(k) for k in payload.agent_keys]
    if keys:
        targets = db.exec(
            select(Agent).where(
                Agent.network_id == network_id, func.lower(Agent.key).in_(keys)
            )
        ).all()
        found = {ag.key.lower() for ag in targets}
        missing = sorted(set(keys) - found)
        if missing:
            raise HTTPException(
                status_code=400, detail=f"unknown agents: {', '.join(missing)}"
            )
        if any(ag.id == agent_id for ag in targets):
            raise HTTPException(status_code=400, detail="agent cannot route to itself")
        a.allowed_routes = targets
    else:
        a.allowed_routes = []
    db.add(a)
    db.commit()
    db.refresh(a)
    prompts_map, default_map = _load_compiled_agent_metadata(db, [network_id])
    return _resolve_agent_out(
        a,
        prompt_fallback=prompts_map.get(network_id, {}).get(a.key),
        default_fallback=default_map.get(network_id) == a.key,
    )


def _compile_snapshot(db: Session, network_id: int, version_id: int) -> dict:
    # Build a minimal compiled graph for runtime usage
    net = db.get(Network, network_id)
    if not net:
        raise HTTPException(status_code=404, detail="network not found")

    # Load agents for the network
    agents = db.exec(select(Agent).where(Agent.network_id == network_id)).all()
    # network-local tools
    nts = db.exec(select(NetworkTool).where(NetworkTool.network_id == network_id)).all()

    def agent_entry(a: Agent) -> dict:
        equipped = [t.key for t in a.equipped_tools]
        routes = [r.key for r in a.allowed_routes]
        prompt = None
        if isinstance(a.additional_data, dict):
            prompt = a.additional_data.get("prompt_template")
        return {
            "key": a.key,
            "allow_respond": bool(a.allow_respond),
            "equipped_tools": equipped,
            "allowed_routes": routes,
            "description": a.description,
            "prompt": prompt,
        }

    tools_entries = []
    for nt in nts:
        tools_entries.append(
            {
                "key": nt.key,
                "provider_type": nt.provider_type,
                "params_schema": nt.params_schema or {},
                "secret_ref": nt.secret_ref,
                "metadata": nt.additional_data or {},
                "description": nt.description,
            }
        )

    default_agent_key = None
    # Choose the first agent marked is_default if any
    for a in agents:
        if a.is_default:
            default_agent_key = a.key
            break

    respond_config: dict = {}
    execution_log_policy_dump = None
    net_meta = net.additional_data if isinstance(net.additional_data, dict) else {}
    if isinstance(net_meta, dict):
        payload_schema = net_meta.get("respond_payload_schema")
        payload_guidance = net_meta.get("respond_payload_guidance")
        payload_example = net_meta.get("respond_payload_example")
        if payload_schema or payload_guidance or payload_example:
            respond_config = {}
            if payload_schema:
                respond_config["payload_schema"] = payload_schema
            if payload_guidance:
                respond_config["payload_guidance"] = payload_guidance
            if payload_example:
                respond_config["payload_example"] = payload_example
        execution_log_raw = net_meta.get("execution_log")
        if execution_log_raw:
            try:
                execution_log_policy_dump = ExecutionLogPolicy.model_validate(
                    execution_log_raw
                ).model_dump()
            except (ValueError, ValidationError) as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"invalid execution_log config: {exc}",
                ) from exc

    compiled = {
        "version_id": version_id,
        "default_agent_key": default_agent_key,
        "agents": [agent_entry(a) for a in agents],
        "tools": tools_entries,
    }
    if respond_config:
        compiled["respond"] = respond_config
    if execution_log_policy_dump:
        compiled["execution_log"] = execution_log_policy_dump
    return compiled


class PublishResponse(BaseModel):
    id: int
    network_id: int
    version: int
    published_at: Optional[str] = None


@router.post(
    "/networks/{network_id}/versions/compile_and_publish",
    response_model=PublishResponse,
)
def compile_and_publish(
    network_id: int, payload: PublishRequest, db: Session = Depends(get_db_dep)
):
    net = db.get(Network, network_id)
    if not net:
        raise HTTPException(status_code=404, detail="network not found")
    # Determine next version num
    current_max = db.exec(
        select(func.max(NetworkVersion.version)).where(
            NetworkVersion.network_id == network_id
        )
    ).one()
    next_ver = (current_max or 0) + 1
    ver = NetworkVersion(
        network_id=network_id,
        version=next_ver,
        created_by=payload.created_by,
        published_by=payload.published_by,
        notes=payload.notes,
    )
    db.add(ver)
    db.commit()
    db.refresh(ver)

    graph = _compile_snapshot(db, network_id, ver.id)  # type: ignore[arg-type]
    snap = CompiledSnapshot(network_version_id=ver.id, compiled_graph=graph)
    db.add(snap)
    # Update network pointer
    net.current_version_id = ver.id
    db.add(net)
    db.commit()
    return PublishResponse(
        id=ver.id, network_id=network_id, version=ver.version, published_at=None
    )


@router.get("/networks/{network_id}/snapshot_current")
def get_current_snapshot(network_id: int, db: Session = Depends(get_db_dep)):
    net = db.get(Network, network_id)
    if not net:
        raise HTTPException(status_code=404, detail="network not found")
    if not net.current_version_id:
        raise HTTPException(status_code=404, detail="no current version")
    snap = db.exec(
        select(CompiledSnapshot).where(
            CompiledSnapshot.network_version_id == net.current_version_id
        )
    ).first()
    if not snap:
        raise HTTPException(status_code=404, detail="snapshot not found")
    return snap.compiled_graph or {}
