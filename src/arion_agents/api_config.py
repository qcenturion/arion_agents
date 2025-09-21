from __future__ import annotations

from typing import List, Optional
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
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

logger = logging.getLogger(__name__)
router = APIRouter()


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
    key: str
    display_name: Optional[str]
    description: Optional[str]
    allow_respond: bool
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


@router.get("/tools", response_model=List[ToolOut])
def list_tools(db: Session = Depends(get_db_dep)):
    tools = db.exec(select(Tool)).all()
    return [_to_tool_out(t) for t in tools]


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
        schema = addl.get("agent_params_json_schema") if isinstance(addl, dict) else None
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
    usage_count = db.exec(select(func.count(NetworkTool.id)).where(NetworkTool.source_tool_id == tool_id)).one()
    if usage_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete tool '{tool.key}' because it is in use by {usage_count} network(s).",
        )
    db.delete(tool)
    db.commit()


@router.post("/tools/{tool_id}/test_connection", response_model=ToolTestResponse)
def test_tool_connection(tool_id: int, payload: ToolTestRequest, db: Session = Depends(get_db_dep)):
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
        out = tool.run(ToolRunInput(params=payload.params or {}, system=payload.system_params or {}, metadata=meta))
        if out.ok:
            return ToolTestResponse(ok=True, status=200, result=out.result)
        return ToolTestResponse(ok=False, status=502, error=out.error)
    except Exception as e:
        return ToolTestResponse(ok=False, status=500, error=str(e))


@router.post("/networks", response_model=Network, status_code=status.HTTP_201_CREATED)
def create_network(payload: Network, db: Session = Depends(get_db_dep)):
    if db.exec(select(Network).where(func.lower(Network.name) == _lc(payload.name))).first():
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
                "prompt_template": (a.additional_data or {}).get("prompt_template") if isinstance(a.additional_data, dict) else None,
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
        "network": {"id": net.id, "name": net.name, "status": net.status, "description": net.description},
        "agents": agent_nodes,
        "tools": tools,
        "adjacency": adjacency,
        "current_version_id": net.current_version_id,
    }


class NetworkUpdate(SQLModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None  # draft|published|archived


@router.patch("/networks/{network_id}", response_model=Network)
def patch_network(network_id: int, payload: NetworkUpdate, db: Session = Depends(get_db_dep)):
    net = db.get(Network, network_id)
    if not net:
        raise HTTPException(status_code=404, detail="network not found")
    if payload.name is not None:
        # uniqueness check (case-insensitive)
        exists = db.exec(select(Network).where(Network.id != network_id, func.lower(Network.name) == _lc(payload.name))).first()
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
def add_tools_to_network(network_id: int, payload: SetTools, db: Session = Depends(get_db_dep)):
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
        raise HTTPException(status_code=400, detail=f"unknown tool keys: {', '.join(missing)}")

    created_keys: List[str] = []
    for k in keys:
        g = found[k]
        # Enforce that the global tool includes agent_params_json_schema
        addl = g.additional_data or {}
        schema = addl.get("agent_params_json_schema") if isinstance(addl, dict) else None
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
            logger.debug("NetworkTool exists; skipping: network_id=%s key=%s", network_id, k)
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
def patch_network_tool(network_id: int, key: str, payload: NetworkToolPatch, db: Session = Depends(get_db_dep)):
    nt = db.exec(
        select(NetworkTool).where(NetworkTool.network_id == network_id, func.lower(NetworkTool.key) == _lc(key))
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


@router.delete("/networks/{network_id}/tools/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_network_tool(network_id: int, key: str, db: Session = Depends(get_db_dep)):
    nt = db.exec(
        select(NetworkTool).where(NetworkTool.network_id == network_id, func.lower(NetworkTool.key) == _lc(key))
    ).first()
    if not nt:
        raise HTTPException(status_code=404, detail="network tool not found")
    db.delete(nt)
    db.commit()


def _resolve_agent_out(agent: Agent) -> AgentOut:
    return AgentOut(
        id=agent.id,
        key=agent.key,
        display_name=agent.display_name,
        description=agent.description,
        allow_respond=agent.allow_respond,
        equipped_tools=[t.key for t in agent.equipped_tools],
        allowed_routes=[r.key for r in agent.allowed_routes],
    )


@router.post("/networks/{network_id}/agents", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
def create_agent(network_id: int, payload: AgentCreate, db: Session = Depends(get_db_dep)):
    if not db.get(Network, network_id):
        raise HTTPException(status_code=404, detail="network not found")
    if db.exec(select(Agent).where(Agent.network_id == network_id, func.lower(Agent.key) == _lc(payload.key))).first():
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
    db.commit()
    db.refresh(agent)
    return _resolve_agent_out(agent)


class AgentUpdate(SQLModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    allow_respond: Optional[bool] = None
    is_default: Optional[bool] = None
    additional_data: Optional[dict] = None


@router.patch("/networks/{network_id}/agents/{agent_id}", response_model=AgentOut)
def patch_agent(network_id: int, agent_id: int, payload: AgentUpdate, db: Session = Depends(get_db_dep)):
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
    db.add(a)
    db.commit()
    db.refresh(a)
    return _resolve_agent_out(a)

@router.get("/networks/{network_id}/agents", response_model=List[AgentOut])
def list_agents(network_id: int, db: Session = Depends(get_db_dep)):
    if not db.get(Network, network_id):
        raise HTTPException(status_code=404, detail="network not found")
    agents = db.exec(select(Agent).where(Agent.network_id == network_id)).all()
    return [_resolve_agent_out(a) for a in agents]


@router.get("/networks/{network_id}/agents/{agent_id}", response_model=AgentOut)
def get_agent(network_id: int, agent_id: int, db: Session = Depends(get_db_dep)):
    a = db.get(Agent, agent_id)
    if not a or a.network_id != network_id:
        raise HTTPException(status_code=404, detail="agent not found")
    return _resolve_agent_out(a)


@router.delete("/networks/{network_id}/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(network_id: int, agent_id: int, db: Session = Depends(get_db_dep)):
    a = db.get(Agent, agent_id)
    if not a or a.network_id != network_id:
        raise HTTPException(status_code=404, detail="agent not found")
    db.delete(a)
    db.commit()


@router.put("/networks/{network_id}/agents/{agent_id}/tools", response_model=AgentOut)
def set_agent_tools(network_id: int, agent_id: int, payload: SetTools, db: Session = Depends(get_db_dep)):
    a = db.get(Agent, agent_id)
    if not a or a.network_id != network_id:
        raise HTTPException(status_code=404, detail="agent not found")
    
    keys = [_lc(k) for k in payload.tool_keys]
    if keys:
        nts = db.exec(select(NetworkTool).where(NetworkTool.network_id == network_id, func.lower(NetworkTool.key).in_(keys))).all()
        found = {t.key.lower() for t in nts}
        missing = sorted(set(keys) - found)
        if missing:
            raise HTTPException(status_code=400, detail=f"unknown network tool keys: {', '.join(missing)}")
        a.equipped_tools = nts
    else:
        a.equipped_tools = []
    db.add(a)
    db.commit()
    db.refresh(a)
    return _resolve_agent_out(a)


@router.put("/networks/{network_id}/agents/{agent_id}/routes", response_model=AgentOut)
def set_agent_routes(network_id: int, agent_id: int, payload: SetRoutes, db: Session = Depends(get_db_dep)):
    a = db.get(Agent, agent_id)
    if not a or a.network_id != network_id:
        raise HTTPException(status_code=404, detail="agent not found")

    keys = [_lc(k) for k in payload.agent_keys]
    if keys:
        targets = db.exec(select(Agent).where(Agent.network_id == network_id, func.lower(Agent.key).in_(keys))).all()
        found = {ag.key.lower() for ag in targets}
        missing = sorted(set(keys) - found)
        if missing:
            raise HTTPException(status_code=400, detail=f"unknown agents: {', '.join(missing)}")
        if any(ag.id == agent_id for ag in targets):
            raise HTTPException(status_code=400, detail="agent cannot route to itself")
        a.allowed_routes = targets
    else:
        a.allowed_routes = []
    db.add(a)
    db.commit()
    db.refresh(a)
    return _resolve_agent_out(a)


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

    compiled = {
        "version_id": version_id,
        "default_agent_key": default_agent_key,
        "agents": [agent_entry(a) for a in agents],
        "tools": tools_entries,
    }
    return compiled

class PublishResponse(BaseModel):
    id: int
    network_id: int
    version: int
    published_at: Optional[str] = None


@router.post("/networks/{network_id}/versions/compile_and_publish", response_model=PublishResponse)
def compile_and_publish(network_id: int, payload: PublishRequest, db: Session = Depends(get_db_dep)):
    net = db.get(Network, network_id)
    if not net:
        raise HTTPException(status_code=404, detail="network not found")
    # Determine next version num
    current_max = db.exec(select(func.max(NetworkVersion.version)).where(NetworkVersion.network_id == network_id)).one()
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
    return PublishResponse(id=ver.id, network_id=network_id, version=ver.version, published_at=None)

@router.get("/networks/{network_id}/snapshot_current")
def get_current_snapshot(network_id: int, db: Session = Depends(get_db_dep)):
    net = db.get(Network, network_id)
    if not net:
        raise HTTPException(status_code=404, detail="network not found")
    if not net.current_version_id:
        raise HTTPException(status_code=404, detail="no current version")
    snap = db.exec(select(CompiledSnapshot).where(CompiledSnapshot.network_version_id == net.current_version_id)).first()
    if not snap:
        raise HTTPException(status_code=404, detail="snapshot not found")
    return snap.compiled_graph or {}
