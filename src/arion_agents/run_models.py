from datetime import datetime
from enum import Enum
from typing import Iterable, Optional

import sqlalchemy as sa
from sqlalchemy import select
from sqlmodel import Column, Field, Session, SQLModel

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


class ExperimentQueueStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ExperimentQueueRecord(SQLModel, table=True):
    __tablename__ = "experiment_queue"

    id: Optional[int] = Field(default=None, primary_key=True)
    experiment_id: str = Field(
        sa_column=sa.Column(sa.String(120), nullable=False, index=True)
    )
    item_index: int = Field(
        sa_column=sa.Column(sa.Integer, nullable=False, index=True)
    )
    iteration: int = Field(
        sa_column=sa.Column(sa.Integer, nullable=False)
    )
    status: ExperimentQueueStatus = Field(
        default=ExperimentQueueStatus.PENDING,
        sa_column=sa.Column(
            sa.Enum(
                ExperimentQueueStatus,
                name="experiment_queue_status",
                values_callable=lambda enum_cls: [member.value for member in enum_cls],
                validate_strings=True,
            ),
            nullable=False,
            server_default=ExperimentQueueStatus.PENDING.value,
        ),
    )
    enqueued_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column_kwargs={"server_default": sa.func.now()},
    )
    started_at: datetime | None = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True),
    )
    completed_at: datetime | None = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True),
    )
    error: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.Text, nullable=True),
    )
    payload: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONType, nullable=False, default=dict),
    )
    result: dict | None = Field(
        default=None,
        sa_column=Column(JSONType, nullable=True),
    )


def enqueue_queue_items(session: Session, records: Iterable[ExperimentQueueRecord]) -> None:
    for record in records:
        session.add(record)


def lease_next_queue_item(session: Session) -> ExperimentQueueRecord | None:
    stmt = (
        select(ExperimentQueueRecord)
        .where(
            ExperimentQueueRecord.status
            == ExperimentQueueStatus.PENDING.value
        )
        .order_by(ExperimentQueueRecord.enqueued_at)
        .limit(1)
    )
    record = session.exec(stmt).scalars().first()
    if record is None:
        return None

    record.status = ExperimentQueueStatus.IN_PROGRESS
    record.started_at = datetime.utcnow()
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def mark_queue_item_completed(
    session: Session,
    record_id: int,
    *,
    succeeded: bool,
    error: str | None = None,
    result: dict | None = None,
) -> None:
    record = session.get(ExperimentQueueRecord, record_id)
    if record is None:
        return

    record.completed_at = datetime.utcnow()
    if succeeded:
        record.status = ExperimentQueueStatus.COMPLETED
        record.error = None
    else:
        record.status = ExperimentQueueStatus.FAILED
        record.error = error
    record.result = result
    session.add(record)
