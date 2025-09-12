from __future__ import annotations

from typing import List, Optional

from sqlalchemy import Column, ForeignKey, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


# Association: Agent equipped tools
agent_tools = Table(
    "agent_tools",
    Base.metadata,
    Column("agent_id", ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
    Column("tool_id", ForeignKey("tools.id", ondelete="CASCADE"), primary_key=True),
    UniqueConstraint("agent_id", "tool_id", name="uq_agent_tool"),
)


# Association: Allowed routes (agent -> agent)
agent_routes = Table(
    "agent_routes",
    Base.metadata,
    Column("from_agent_id", ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
    Column("to_agent_id", ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
    UniqueConstraint("from_agent_id", "to_agent_id", name="uq_agent_route"),
)


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    equipped_tools: Mapped[List[Tool]] = relationship(
        "Tool", secondary=agent_tools, back_populates="agents", cascade="all"
    )

    allowed_routes: Mapped[List[Agent]] = relationship(
        "Agent",
        secondary=agent_routes,
        primaryjoin="Agent.id==agent_routes.c.from_agent_id",
        secondaryjoin="Agent.id==agent_routes.c.to_agent_id",
        backref="routed_from",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"Agent(id={self.id!r}, name={self.name!r})"


class Tool(Base):
    __tablename__ = "tools"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    agents: Mapped[List[Agent]] = relationship(
        "Agent", secondary=agent_tools, back_populates="equipped_tools"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"Tool(id={self.id!r}, name={self.name!r})"

