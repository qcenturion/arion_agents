from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Column, Field, SQLModel

from .db import JSONType


class RunRecord(SQLModel, table=True):
    __tablename__ = "run_history"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(
        sa_column=sa.Column(sa.String(64), unique=True, nullable=False, index=True)
    )
    network_id: Optional[int] = Field(
        default=None,
        sa_column=sa.Column(
            sa.Integer,
            sa.ForeignKey("cfg_networks.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    network_version_id: Optional[int] = Field(
        default=None,
        sa_column=sa.Column(
            sa.Integer,
            sa.ForeignKey("cfg_network_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    graph_version_key: Optional[str] = Field(
        default=None,
        sa_column=sa.Column(sa.String(120), nullable=True),
    )
    user_message: Optional[str] = Field(
        default=None,
        sa_column=sa.Column(sa.Text, nullable=True),
    )
    status: str = Field(
        default="unknown",
        sa_column=sa.Column(sa.String(32), nullable=False, server_default="unknown"),
    )
    request_payload: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONType, nullable=False, default=dict),
    )
    response_payload: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONType, nullable=False, default=dict),
    )
    experiment_id: Optional[str] = Field(
        default=None,
        sa_column=sa.Column(sa.String(120), index=True, nullable=True),
    )
    experiment_desc: Optional[str] = Field(
        default=None,
        sa_column=sa.Column(sa.Text, nullable=True),
    )
    experiment_item_index: Optional[int] = Field(
        default=None,
        sa_column=sa.Column(sa.Integer, nullable=True),
    )
    experiment_iteration: Optional[int] = Field(
        default=None,
        sa_column=sa.Column(sa.Integer, nullable=True),
    )
    experiment_item_payload: Optional[dict] = Field(
        default=None,
        sa_column=Column(JSONType, nullable=True),
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column_kwargs={"server_default": sa.func.now()},
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column_kwargs={
            "server_default": sa.func.now(),
            "onupdate": sa.func.now(),
        },
    )


class ExperimentRecord(SQLModel, table=True):
    __tablename__ = "experiment_history"

    id: Optional[int] = Field(default=None, primary_key=True)
    experiment_id: str = Field(
        sa_column=sa.Column(sa.String(120), unique=True, nullable=False, index=True)
    )
    description: Optional[str] = Field(
        default=None,
        sa_column=sa.Column(sa.Text, nullable=True),
    )
    payload: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONType, nullable=False, default=dict),
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column_kwargs={"server_default": sa.func.now()},
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column_kwargs={
            "server_default": sa.func.now(),
            "onupdate": sa.func.now(),
        },
    )
