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

logger = logging.getLogger(__name__)
router = APIRouter()


def get_db_dep() -> Session:
    # SQLModel Session is directly usable as a context manager
    with get_session() as s:
        yield s


def _lc(s: str) -> str:
    return s.strip().lower()


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


@router.get("/tools", response_model=List[ToolOut])
def list_tools(db: Session = Depends(get_db_dep)):
    tools = db.exec(select(Tool)).all()
    return [_to_tool_out(t) for t in tools]


@router.post("/tools", response_model=ToolOut, status_code=status.HTTP_201_CREATED)
def create_tool(payload: ToolCreate, db: Session = Depends(get_db_dep)):
    # Check for existing key
    if db.exec(select(Tool).where(func.lower(Tool.key) == _lc(payload.key))).first():
        raise HTTPException(status_code=409, detail="tool key exists")
    # Map API DTO to ORM model (meta <- metadata)
    t = Tool(
        key=payload.key,
        display_name=payload.display_name,
        description=payload.description,
        provider_type=payload.provider_type,
        params_schema=payload.params_schema or {},
        secret_ref=payload.secret_ref,
        additional_data=payload.additional_data or {},
    )
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


@router.get("/networks/{network_id}/tools", response_model=List[ToolOut])
def list_network_tools(network_id: int, db: Session = Depends(get_db_dep)):
    if not db.get(Network, network_id):
        raise HTTPException(status_code=404, detail="network not found")
    tools = db.exec(select(Tool).join(NetworkTool).where(NetworkTool.network_id == network_id)).all()
    return [_to_tool_out(t) for t in tools]


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
    agent = Agent(
        network_id=network_id,
        key=payload.key,
        display_name=payload.display_name,
        description=payload.description,
        allow_respond=payload.allow_respond,
        is_default=payload.is_default,
        additional_data=payload.additional_data or {},
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return _resolve_agent_out(agent)


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
    # This function remains complex as it's business logic, not simple CRUD.
    # It will need to be updated to work with the new SQLModel relationships.
    # For now, we will focus on the CRUD endpoints.
    # A full implementation would require careful translation of the relationship logic.
    raise NotImplementedError("Snapshot compilation needs to be refactored for SQLModel relationships.")

@router.post("/networks/{network_id}/versions/compile_and_publish")
def compile_and_publish(network_id: int, payload: PublishRequest, db: Session = Depends(get_db_dep)):
    # This endpoint is temporarily disabled until the snapshot logic is refactored.
    raise HTTPException(status_code=501, detail="Snapshot compilation is being refactored for SQLModel.")

@router.get("/networks/{network_id}/snapshot_current")
def get_current_snapshot(network_id: int, db: Session = Depends(get_db_dep)):
    # This endpoint is temporarily disabled.
    raise HTTPException(status_code=501, detail="Snapshot retrieval is being refactored for SQLModel.")
