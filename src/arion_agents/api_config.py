from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_session
from .config_models import (
    Agent,
    Network,
    NetworkTool,
    Tool,
    NetworkVersion,
    CompiledSnapshot,
)


router = APIRouter()


def get_db_dep() -> Session:
    with get_session() as s:
        yield s


def _lc(s: str) -> str:
    return s.strip().lower()


class GlobalToolCreate(BaseModel):
    key: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    provider_type: Optional[str] = None
    params_schema: dict = {}
    secret_ref: Optional[str] = None
    metadata: dict = {}

    @field_validator("key")
    @classmethod
    def validate_key(cls, v: str) -> str:
        v2 = _lc(v)
        if not v2:
            raise ValueError("key cannot be empty")
        return v2


class GlobalToolOut(BaseModel):
    id: int
    key: str
    display_name: Optional[str]
    description: Optional[str]
    provider_type: Optional[str]
    params_schema: dict
    secret_ref: Optional[str]
    metadata: dict


class NetworkCreate(BaseModel):
    name: str
    description: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v2 = _lc(v)
        if not v2:
            raise ValueError("name cannot be empty")
        return v2


class NetworkOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    status: str
    current_version_id: Optional[int]


class AgentCreate(BaseModel):
    key: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    allow_respond: bool = True
    metadata: dict = {}

    @field_validator("key")
    @classmethod
    def validate_key(cls, v: str) -> str:
        v2 = _lc(v)
        if not v2:
            raise ValueError("key cannot be empty")
        return v2


class AgentOut(BaseModel):
    id: int
    key: str
    display_name: Optional[str]
    description: Optional[str]
    allow_respond: bool
    equipped_tools: List[str]
    allowed_routes: List[str]


class SetTools(BaseModel):
    tool_keys: List[str]

    @field_validator("tool_keys")
    @classmethod
    def clean(cls, v: List[str]) -> List[str]:
        out = []
        seen = set()
        for k in v:
            k2 = _lc(k)
            if k2 and k2 not in seen:
                out.append(k2)
                seen.add(k2)
        return out


class SetRoutes(BaseModel):
    agent_keys: List[str]

    @field_validator("agent_keys")
    @classmethod
    def clean(cls, v: List[str]) -> List[str]:
        out = []
        seen = set()
        for k in v:
            k2 = _lc(k)
            if k2 and k2 not in seen:
                out.append(k2)
                seen.add(k2)
        return out


class PublishRequest(BaseModel):
    notes: Optional[str] = None
    created_by: Optional[str] = None
    published_by: Optional[str] = None


@router.get("/tools", response_model=List[GlobalToolOut])
def list_tools(db: Session = Depends(get_db_dep)):
    return list(db.scalars(select(Tool)).all())


@router.post("/tools", response_model=GlobalToolOut, status_code=status.HTTP_201_CREATED)
def create_tool(payload: GlobalToolCreate, db: Session = Depends(get_db_dep)):
    if db.scalar(select(Tool).where(func.lower(Tool.key) == payload.key)):
        raise HTTPException(status_code=409, detail="tool key exists")
    t = Tool(
        key=payload.key,
        display_name=payload.display_name,
        description=payload.description,
        provider_type=payload.provider_type,
        params_schema=payload.params_schema or {},
        secret_ref=payload.secret_ref,
        meta=payload.metadata or {},
    )
    db.add(t)
    db.flush()
    return t


@router.post("/networks", response_model=NetworkOut, status_code=status.HTTP_201_CREATED)
def create_network(payload: NetworkCreate, db: Session = Depends(get_db_dep)):
    if db.scalar(select(Network).where(func.lower(Network.name) == payload.name)):
        raise HTTPException(status_code=409, detail="network name exists")
    n = Network(name=payload.name, description=payload.description, status="draft")
    db.add(n)
    db.flush()
    return NetworkOut(id=n.id, name=n.name, description=n.description, status=n.status, current_version_id=n.current_version_id)


@router.get("/networks", response_model=List[NetworkOut])
def list_networks(db: Session = Depends(get_db_dep)):
    nets = list(db.scalars(select(Network)).all())
    return [NetworkOut(id=n.id, name=n.name, description=n.description, status=n.status, current_version_id=n.current_version_id) for n in nets]


@router.post("/networks/{network_id}/tools", response_model=List[str])
def add_tools_to_network(network_id: int, payload: SetTools, db: Session = Depends(get_db_dep)):
    net = db.get(Network, network_id)
    if not net:
        raise HTTPException(status_code=404, detail="network not found")
    if not payload.tool_keys:
        return []
    globals_ = list(db.scalars(select(Tool).where(func.lower(Tool.key).in_(payload.tool_keys))).all())
    found = {g.key.lower(): g for g in globals_}
    missing = sorted(set(payload.tool_keys) - set(found.keys()))
    if missing:
        raise HTTPException(status_code=400, detail=f"unknown tool keys: {', '.join(missing)}")
    created_keys: List[str] = []
    for k in payload.tool_keys:
        g = found[k]
        existing = db.scalar(
            select(NetworkTool).where(
                (NetworkTool.network_id == network_id) & (func.lower(NetworkTool.key) == k)
            )
        )
        if existing:
            created_keys.append(existing.key)
            continue
        nt = NetworkTool(
            network_id=network_id,
            source_tool_id=g.id,
            key=g.key,
            display_name=g.display_name,
            description=g.description,
            provider_type=g.provider_type,
            params_schema=g.params_schema,
            secret_ref=g.secret_ref,
            meta=g.meta,
        )
        db.add(nt)
        created_keys.append(g.key)
    db.flush()
    return created_keys


@router.get("/networks/{network_id}/tools", response_model=List[GlobalToolOut])
def list_network_tools(network_id: int, db: Session = Depends(get_db_dep)):
    net = db.get(Network, network_id)
    if not net:
        raise HTTPException(status_code=404, detail="network not found")
    items = list(db.scalars(select(NetworkTool).where(NetworkTool.network_id == network_id)).all())
    return [
        GlobalToolOut(
            id=nt.id,
            key=nt.key,
            display_name=nt.display_name,
            description=nt.description,
            provider_type=nt.provider_type,
            params_schema=nt.params_schema,
            secret_ref=nt.secret_ref,
            metadata=nt.meta,
        )
        for nt in items
    ]


def _agent_out(a: Agent) -> AgentOut:
    return AgentOut(
        id=a.id,
        key=a.key,
        display_name=a.display_name,
        description=a.description,
        allow_respond=a.allow_respond,
        equipped_tools=[t.key for t in a.equipped_tools],
        allowed_routes=[r.key for r in a.allowed_routes],
    )


@router.post("/networks/{network_id}/agents", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
def create_agent(network_id: int, payload: AgentCreate, db: Session = Depends(get_db_dep)):
    if not db.get(Network, network_id):
        raise HTTPException(status_code=404, detail="network not found")
    if db.scalar(
        select(Agent).where((Agent.network_id == network_id) & (func.lower(Agent.key) == payload.key))
    ):
        raise HTTPException(status_code=409, detail="agent key exists")
    a = Agent(
        network_id=network_id,
        key=payload.key,
        display_name=payload.display_name,
        description=payload.description,
        allow_respond=payload.allow_respond,
        meta=payload.metadata or {},
    )
    db.add(a)
    db.flush()
    db.refresh(a)
    return _agent_out(a)


@router.get("/networks/{network_id}/agents", response_model=List[AgentOut])
def list_agents(network_id: int, db: Session = Depends(get_db_dep)):
    if not db.get(Network, network_id):
        raise HTTPException(status_code=404, detail="network not found")
    agents = list(db.scalars(select(Agent).where(Agent.network_id == network_id)).all())
    return [_agent_out(a) for a in agents]


@router.get("/networks/{network_id}/agents/{agent_id}", response_model=AgentOut)
def get_agent(network_id: int, agent_id: int, db: Session = Depends(get_db_dep)):
    a = db.get(Agent, agent_id)
    if not a or a.network_id != network_id:
        raise HTTPException(status_code=404, detail="agent not found")
    return _agent_out(a)


@router.put("/networks/{network_id}/agents/{agent_id}/tools", response_model=AgentOut)
def set_agent_tools(network_id: int, agent_id: int, payload: SetTools, db: Session = Depends(get_db_dep)):
    a = db.get(Agent, agent_id)
    if not a or a.network_id != network_id:
        raise HTTPException(status_code=404, detail="agent not found")
    if payload.tool_keys:
        nts = list(
            db.scalars(
                select(NetworkTool).where(
                    (NetworkTool.network_id == network_id) & (func.lower(NetworkTool.key).in_(payload.tool_keys))
                )
            ).all()
        )
        found = {t.key.lower() for t in nts}
        missing = sorted(set(payload.tool_keys) - found)
        if missing:
            raise HTTPException(status_code=400, detail=f"unknown network tool keys: {', '.join(missing)}")
        a.equipped_tools = nts
    else:
        a.equipped_tools = []
    db.add(a)
    db.flush()
    db.refresh(a)
    return _agent_out(a)


@router.put("/networks/{network_id}/agents/{agent_id}/routes", response_model=AgentOut)
def set_agent_routes(network_id: int, agent_id: int, payload: SetRoutes, db: Session = Depends(get_db_dep)):
    a = db.get(Agent, agent_id)
    if not a or a.network_id != network_id:
        raise HTTPException(status_code=404, detail="agent not found")
    if payload.agent_keys:
        targets = list(
            db.scalars(
                select(Agent).where(
                    (Agent.network_id == network_id) & (func.lower(Agent.key).in_(payload.agent_keys))
                )
            ).all()
        )
        found = {ag.key.lower() for ag in targets}
        missing = sorted(set(payload.agent_keys) - found)
        if missing:
            raise HTTPException(status_code=400, detail=f"unknown agents: {', '.join(missing)}")
        if any(ag.id == agent_id for ag in targets):
            raise HTTPException(status_code=400, detail="agent cannot route to itself")
        a.allowed_routes = targets
    else:
        a.allowed_routes = []
    db.add(a)
    db.flush()
    db.refresh(a)
    return _agent_out(a)


def _compile_snapshot(db: Session, network_id: int, version_id: int) -> dict:
    agents = list(db.scalars(select(Agent).where(Agent.network_id == network_id)).all())
    tools = list(db.scalars(select(NetworkTool).where(NetworkTool.network_id == network_id)).all())

    out_agents = []
    for a in agents:
        out_agents.append(
            {
                "key": a.key,
                "allow_respond": a.allow_respond,
                "equipped_tools": [t.key for t in a.equipped_tools],
                "allowed_routes": [r.key for r in a.allowed_routes],
                "metadata": a.meta or {},
            }
        )

    out_tools = []
    for t in tools:
        out_tools.append(
            {
                "key": t.key,
                "description": t.description,
                "provider_type": t.provider_type,
                "params_schema": t.params_schema,
                "secret_ref": t.secret_ref,
                "metadata": t.meta or {},
            }
        )

    compiled = {
        "agents": out_agents,
        "tools": out_tools,
        "adjacency": [
            {"from": a.key, "to": r.key} for a in agents for r in a.allowed_routes
        ],
        "policy": {},
    }
    return compiled


@router.post("/networks/{network_id}/versions/compile_and_publish")
def compile_and_publish(network_id: int, payload: PublishRequest, db: Session = Depends(get_db_dep)):
    net = db.get(Network, network_id)
    if not net:
        raise HTTPException(status_code=404, detail="network not found")
    max_v = db.scalar(select(func.max(NetworkVersion.version)).where(NetworkVersion.network_id == network_id)) or 0
    vnum = max_v + 1
    ver = NetworkVersion(
        network_id=network_id,
        version=vnum,
        created_by=payload.created_by,
        published_by=payload.published_by,
        notes=payload.notes,
    )
    db.add(ver)
    db.flush()

    compiled = _compile_snapshot(db, network_id, ver.id)
    snap = CompiledSnapshot(network_version_id=ver.id, compiled_graph=compiled)
    db.add(snap)
    db.flush()

    net.current_version_id = ver.id
    db.add(net)
    db.flush()
    return {"version": vnum, "version_id": ver.id, "snapshot_id": snap.id}
