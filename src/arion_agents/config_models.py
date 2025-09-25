from datetime import datetime
from typing import Optional, List

import sqlalchemy as sa
from sqlmodel import Field, Relationship, SQLModel, Column, text

from .db import JSONType


class Tool(SQLModel, table=True):
    __tablename__ = "cfg_tools"

    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(sa_column=sa.Column(sa.String(120), nullable=False))
    display_name: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))
    provider_type: Optional[str] = Field(default=None, max_length=100)
    params_schema: dict = Field(default_factory=dict, sa_column=Column(JSONType, nullable=False, default=dict))
    secret_ref: Optional[str] = Field(default=None, max_length=200)
    additional_data: dict = Field(default_factory=dict, sa_column=Column("additional_data", JSONType, nullable=False, default=dict))

    __table_args__ = (sa.Index("ux_cfg_tools_key_lower", text("lower(key)"), unique=True),)


class Network(SQLModel, table=True):
    __tablename__ = "cfg_networks"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=120, unique=True)
    description: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))
    status: str = Field(default="draft", max_length=32)
    current_version_id: Optional[int] = Field(default=None)
    additional_data: dict = Field(
        default_factory=dict,
        sa_column=Column("additional_data", JSONType, nullable=True, default=dict),
    )

    agents: List["Agent"] = Relationship(back_populates="network", sa_relationship_kwargs={"passive_deletes": True})
    versions: List["NetworkVersion"] = Relationship(back_populates="network", sa_relationship_kwargs={"passive_deletes": True})
    network_tools: List["NetworkTool"] = Relationship(back_populates="network", sa_relationship_kwargs={"passive_deletes": True})

    __table_args__ = (sa.CheckConstraint("status in ('draft','published','archived')", name="ck_cfg_networks_status"),)


class AgentToolLink(SQLModel, table=True):
    __tablename__ = "cfg_agent_tools"
    agent_id: Optional[int] = Field(
        default=None,
        sa_column=sa.Column(
            sa.Integer,
            sa.ForeignKey("cfg_agents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    network_tool_id: Optional[int] = Field(
        default=None,
        sa_column=sa.Column(
            sa.Integer,
            sa.ForeignKey("cfg_network_tools.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


class AgentRouteLink(SQLModel, table=True):
    __tablename__ = "cfg_agent_routes"
    from_agent_id: Optional[int] = Field(
        default=None,
        sa_column=sa.Column(
            sa.Integer,
            sa.ForeignKey("cfg_agents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    to_agent_id: Optional[int] = Field(
        default=None,
        sa_column=sa.Column(
            sa.Integer,
            sa.ForeignKey("cfg_agents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    __table_args__ = (sa.CheckConstraint("from_agent_id <> to_agent_id", name="ck_cfg_agent_routes_not_self"),)


class Agent(SQLModel, table=True):
    __tablename__ = "cfg_agents"

    id: Optional[int] = Field(default=None, primary_key=True)
    network_id: int = Field(
        sa_column=sa.Column(
            sa.Integer,
            sa.ForeignKey("cfg_networks.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    key: str = Field(max_length=120)
    display_name: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))
    allow_respond: bool = True
    is_default: bool = False
    additional_data: dict = Field(default_factory=dict, sa_column=Column("additional_data", JSONType, nullable=False, default=dict))

    network: "Network" = Relationship(back_populates="agents")
    equipped_tools: List["NetworkTool"] = Relationship(link_model=AgentToolLink)
    allowed_routes: list["Agent"] = Relationship(
        link_model=AgentRouteLink,
        sa_relationship_kwargs=dict(
            primaryjoin="Agent.id==AgentRouteLink.from_agent_id",
            secondaryjoin="Agent.id==AgentRouteLink.to_agent_id",
        ),
    )

    __table_args__ = (sa.Index("ux_cfg_agents_network_key_lower", "network_id", text("lower(key)"), unique=True),)


class NetworkTool(SQLModel, table=True):
    __tablename__ = "cfg_network_tools"

    id: Optional[int] = Field(default=None, primary_key=True)
    network_id: int = Field(
        sa_column=sa.Column(
            sa.Integer,
            sa.ForeignKey("cfg_networks.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    source_tool_id: int = Field(
        sa_column=sa.Column(
            sa.Integer,
            sa.ForeignKey("cfg_tools.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )

    key: str = Field(max_length=120)
    display_name: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))
    provider_type: Optional[str] = Field(default=None, max_length=100)
    params_schema: dict = Field(default_factory=dict, sa_column=Column(JSONType, nullable=False, default=dict))
    secret_ref: Optional[str] = Field(default=None, max_length=200)
    additional_data: dict = Field(default_factory=dict, sa_column=Column("additional_data", JSONType, nullable=False, default=dict))

    network: "Network" = Relationship(back_populates="network_tools")
    source_tool: Tool = Relationship()

    __table_args__ = (
        sa.Index("ux_cfg_network_tools_network_key_lower", "network_id", text("lower(key)"), unique=True),
    )


    # moved above NetworkTool to ensure relationship string resolution


class NetworkVersion(SQLModel, table=True):
    __tablename__ = "cfg_network_versions"

    id: Optional[int] = Field(default=None, primary_key=True)
    network_id: int = Field(
        sa_column=sa.Column(
            sa.Integer,
            sa.ForeignKey("cfg_networks.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    version: int
    created_by: Optional[str] = Field(default=None, max_length=120)
    created_at: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"server_default": sa.func.now()})
    published_by: Optional[str] = Field(default=None, max_length=120)
    published_at: Optional[datetime] = Field(default=None)
    notes: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))

    network: Network = Relationship(back_populates="versions")

    __table_args__ = (sa.UniqueConstraint("network_id", "version", name="uq_cfg_network_version"),)


class CompiledSnapshot(SQLModel, table=True):
    __tablename__ = "cfg_compiled_snapshots"

    id: Optional[int] = Field(default=None, primary_key=True)
    network_version_id: int = Field(
        sa_column=sa.Column(
            sa.Integer,
            sa.ForeignKey("cfg_network_versions.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        )
    )
    checksum: Optional[str] = Field(default=None, max_length=128)
    compiled_graph: dict = Field(default_factory=dict, sa_column=Column(JSONType, nullable=False, default=dict))
    created_at: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"server_default": sa.func.now()})
