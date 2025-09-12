from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_session
from .models import Agent, Tool


router = APIRouter()


def get_db_dep() -> Session:
    with get_session() as s:
        yield s


# Schemas
class ToolCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ToolUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class ToolOut(BaseModel):
    id: int
    name: str
    description: Optional[str]

    class Config:
        from_attributes = True


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class AgentOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    equipped_tools: List[str]
    allowed_routes: List[str]

    class Config:
        from_attributes = True


# Tools endpoints
@router.get("/tools", response_model=List[ToolOut])
def list_tools(db: Session = Depends(get_db_dep)):
    return list(db.scalars(select(Tool)).all())


@router.post("/tools", response_model=ToolOut, status_code=status.HTTP_201_CREATED)
def create_tool(payload: ToolCreate, db: Session = Depends(get_db_dep)):
    if db.scalar(select(Tool).where(Tool.name == payload.name)):
        raise HTTPException(status_code=400, detail="Tool name already exists")
    t = Tool(name=payload.name, description=payload.description)
    db.add(t)
    db.flush()
    return t


@router.get("/tools/{tool_id}", response_model=ToolOut)
def get_tool(tool_id: int, db: Session = Depends(get_db_dep)):
    t = db.get(Tool, tool_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tool not found")
    return t


@router.patch("/tools/{tool_id}", response_model=ToolOut)
def update_tool(tool_id: int, payload: ToolUpdate, db: Session = Depends(get_db_dep)):
    t = db.get(Tool, tool_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tool not found")
    if payload.name is not None:
        if payload.name != t.name and db.scalar(select(Tool).where(Tool.name == payload.name)):
            raise HTTPException(status_code=400, detail="Tool name already exists")
        t.name = payload.name
    if payload.description is not None:
        t.description = payload.description
    db.add(t)
    return t


@router.delete("/tools/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tool(tool_id: int, db: Session = Depends(get_db_dep)):
    t = db.get(Tool, tool_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tool not found")
    db.delete(t)
    return None


# Agents endpoints
def _agent_out(a: Agent) -> AgentOut:
    return AgentOut(
        id=a.id,
        name=a.name,
        description=a.description,
        equipped_tools=[t.name for t in a.equipped_tools],
        allowed_routes=[r.name for r in a.allowed_routes],
    )


@router.get("/agents", response_model=List[AgentOut])
def list_agents(db: Session = Depends(get_db_dep)):
    agents = list(db.scalars(select(Agent)).all())
    return [_agent_out(a) for a in agents]


@router.post("/agents", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
def create_agent(payload: AgentCreate, db: Session = Depends(get_db_dep)):
    if db.scalar(select(Agent).where(Agent.name == payload.name)):
        raise HTTPException(status_code=400, detail="Agent name already exists")
    a = Agent(name=payload.name, description=payload.description)
    db.add(a)
    db.flush()
    db.refresh(a)
    return _agent_out(a)


@router.get("/agents/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: int, db: Session = Depends(get_db_dep)):
    a = db.get(Agent, agent_id)
    if not a:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _agent_out(a)


@router.patch("/agents/{agent_id}", response_model=AgentOut)
def update_agent(agent_id: int, payload: AgentUpdate, db: Session = Depends(get_db_dep)):
    a = db.get(Agent, agent_id)
    if not a:
        raise HTTPException(status_code=404, detail="Agent not found")
    if payload.name is not None:
        if payload.name != a.name and db.scalar(select(Agent).where(Agent.name == payload.name)):
            raise HTTPException(status_code=400, detail="Agent name already exists")
        a.name = payload.name
    if payload.description is not None:
        a.description = payload.description
    db.add(a)
    db.flush()
    db.refresh(a)
    return _agent_out(a)


class ToolNames(BaseModel):
    tools: List[str]


@router.put("/agents/{agent_id}/tools", response_model=AgentOut)
def set_agent_tools(agent_id: int, payload: ToolNames, db: Session = Depends(get_db_dep)):
    a = db.get(Agent, agent_id)
    if not a:
        raise HTTPException(status_code=404, detail="Agent not found")
    if payload.tools:
        tools = list(db.scalars(select(Tool).where(Tool.name.in_(payload.tools))).all())
        found = {t.name for t in tools}
        missing = sorted(set(payload.tools) - found)
        if missing:
            raise HTTPException(status_code=400, detail=f"Unknown tools: {', '.join(missing)}")
        a.equipped_tools = tools
    else:
        a.equipped_tools = []
    db.add(a)
    db.flush()
    db.refresh(a)
    return _agent_out(a)


class RouteNames(BaseModel):
    agents: List[str]


@router.put("/agents/{agent_id}/routes", response_model=AgentOut)
def set_agent_routes(agent_id: int, payload: RouteNames, db: Session = Depends(get_db_dep)):
    a = db.get(Agent, agent_id)
    if not a:
        raise HTTPException(status_code=404, detail="Agent not found")
    if payload.agents:
        targets = list(db.scalars(select(Agent).where(Agent.name.in_(payload.agents))).all())
        found = {ag.name for ag in targets}
        missing = sorted(set(payload.agents) - found)
        if missing:
            raise HTTPException(status_code=400, detail=f"Unknown agents: {', '.join(missing)}")
        a.allowed_routes = targets
    else:
        a.allowed_routes = []
    db.add(a)
    db.flush()
    db.refresh(a)
    return _agent_out(a)

