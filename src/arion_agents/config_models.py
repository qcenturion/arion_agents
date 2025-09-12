from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Network(Base):
    __tablename__ = "cfg_networks"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(120), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False, default="draft")
    current_version_id: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)

    agents: Mapped[List[Agent]] = relationship("Agent", back_populates="network")
    versions: Mapped[List[NetworkVersion]] = relationship("NetworkVersion", back_populates="network")
    network_tools: Mapped[List[NetworkTool]] = relationship("NetworkTool", back_populates="network")

    __table_args__ = (
        CheckConstraint("status in ('draft','published','archived')", name="ck_cfg_networks_status"),
    )


class Tool(Base):
    __tablename__ = "cfg_tools"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(sa.String(200), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    provider_type: Mapped[Optional[str]] = mapped_column(sa.String(100), nullable=True)
    params_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    secret_ref: Mapped[Optional[str]] = mapped_column(sa.String(200), nullable=True)
    metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    __table_args__ = (
        sa.Index("ux_cfg_tools_key_lower", text("lower(key)"), unique=True),
    )


class NetworkTool(Base):
    __tablename__ = "cfg_network_tools"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    network_id: Mapped[int] = mapped_column(ForeignKey("cfg_networks.id", ondelete="CASCADE"), nullable=False)
    source_tool_id: Mapped[int] = mapped_column(ForeignKey("cfg_tools.id", ondelete="RESTRICT"), nullable=False)

    key: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(sa.String(200), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    provider_type: Mapped[Optional[str]] = mapped_column(sa.String(100), nullable=True)
    params_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    secret_ref: Mapped[Optional[str]] = mapped_column(sa.String(200), nullable=True)
    metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    network: Mapped[Network] = relationship("Network", back_populates="network_tools")
    source_tool: Mapped[Tool] = relationship("Tool")

    __table_args__ = (
        sa.Index(
            "ux_cfg_network_tools_network_key_lower",
            "network_id",
            text("lower(key)"),
            unique=True,
        ),
    )


class Agent(Base):
    __tablename__ = "cfg_agents"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    network_id: Mapped[int] = mapped_column(ForeignKey("cfg_networks.id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(sa.String(200), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    allow_respond: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    network: Mapped[Network] = relationship("Network", back_populates="agents")
    equipped_tools: Mapped[List[NetworkTool]] = relationship(
        "NetworkTool", secondary="cfg_agent_tools", backref="agents"
    )
    allowed_routes: Mapped[List[Agent]] = relationship(
        "Agent",
        secondary="cfg_agent_routes",
        primaryjoin="Agent.id==cfg_agent_routes.c.from_agent_id",
        secondaryjoin="Agent.id==cfg_agent_routes.c.to_agent_id",
        backref="routed_from",
    )

    __table_args__ = (
        sa.Index(
            "ux_cfg_agents_network_key_lower",
            "network_id",
            text("lower(key)"),
            unique=True,
        ),
    )


cfg_agent_tools = sa.Table(
    "cfg_agent_tools",
    Base.metadata,
    sa.Column("agent_id", sa.Integer, sa.ForeignKey("cfg_agents.id", ondelete="CASCADE"), primary_key=True),
    sa.Column("network_tool_id", sa.Integer, sa.ForeignKey("cfg_network_tools.id", ondelete="CASCADE"), primary_key=True),
    UniqueConstraint("agent_id", "network_tool_id", name="uq_cfg_agent_tool"),
)


cfg_agent_routes = sa.Table(
    "cfg_agent_routes",
    Base.metadata,
    sa.Column("from_agent_id", sa.Integer, sa.ForeignKey("cfg_agents.id", ondelete="CASCADE"), primary_key=True),
    sa.Column("to_agent_id", sa.Integer, sa.ForeignKey("cfg_agents.id", ondelete="CASCADE"), primary_key=True),
    UniqueConstraint("from_agent_id", "to_agent_id", name="uq_cfg_agent_route"),
    CheckConstraint("from_agent_id <> to_agent_id", name="ck_cfg_agent_routes_not_self"),
)


class NetworkVersion(Base):
    __tablename__ = "cfg_network_versions"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    network_id: Mapped[int] = mapped_column(ForeignKey("cfg_networks.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(sa.String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    published_by: Mapped[Optional[str]] = mapped_column(sa.String(120), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)

    network: Mapped[Network] = relationship("Network", back_populates="versions")

    __table_args__ = (
        UniqueConstraint("network_id", "version", name="uq_cfg_network_version"),
        sa.Index("ix_cfg_network_versions_network_id", "network_id"),
    )


class CompiledSnapshot(Base):
    __tablename__ = "cfg_compiled_snapshots"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    network_version_id: Mapped[int] = mapped_column(
        ForeignKey("cfg_network_versions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    checksum: Mapped[Optional[str]] = mapped_column(sa.String(128), nullable=True)
    compiled_graph: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
