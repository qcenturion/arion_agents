"""Add experiment queue table for asynchronous batch runs."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from arion_agents.db import JSONType

# revision identifiers, used by Alembic.
revision = "20240925_add_experiment_queue"
down_revision = "20240905_add_experiment_tracking"
branch_labels = None
depends_on = None

STATUS_VALUES = ("pending", "in_progress", "completed", "failed")
status_enum = postgresql.ENUM(
    *STATUS_VALUES,
    name="experiment_queue_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    enum_type = postgresql.ENUM(*STATUS_VALUES, name="experiment_queue_status")
    enum_type.drop(bind, checkfirst=True)
    enum_type.create(bind, checkfirst=True)

    op.create_table(
        "experiment_queue",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("experiment_id", sa.String(length=120), nullable=False),
        sa.Column("item_index", sa.Integer(), nullable=False),
        sa.Column("iteration", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            status_enum,
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "enqueued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("payload", JSONType, nullable=False),
        sa.Column("result", JSONType, nullable=True),
    )

    op.create_index(
        "ix_experiment_queue_experiment_id",
        "experiment_queue",
        ["experiment_id"],
    )
    op.create_index(
        "ix_experiment_queue_item_index",
        "experiment_queue",
        ["item_index"],
    )


def downgrade() -> None:
    op.drop_index("ix_experiment_queue_item_index", table_name="experiment_queue")
    op.drop_index("ix_experiment_queue_experiment_id", table_name="experiment_queue")
    op.drop_table("experiment_queue")
    bind = op.get_bind()
    enum_type = postgresql.ENUM(*STATUS_VALUES, name="experiment_queue_status")
    enum_type.drop(bind, checkfirst=True)
