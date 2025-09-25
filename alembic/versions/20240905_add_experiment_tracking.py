from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from arion_agents.db import JSONType


revision = "20240905_add_experiment_tracking"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "run_history",
        sa.Column("experiment_id", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "run_history",
        sa.Column("experiment_desc", sa.Text(), nullable=True),
    )
    op.add_column(
        "run_history",
        sa.Column("experiment_item_index", sa.Integer(), nullable=True),
    )
    op.add_column(
        "run_history",
        sa.Column("experiment_iteration", sa.Integer(), nullable=True),
    )
    op.add_column(
        "run_history",
        sa.Column("experiment_item_payload", JSONType, nullable=True),
    )
    op.create_index(
        "ix_run_history_experiment_id",
        "run_history",
        ["experiment_id"],
        unique=False,
    )

    op.create_table(
        "experiment_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("experiment_id", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("payload", JSONType, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            server_onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint("experiment_id", name="uq_experiment_history_experiment_id"),
    )
    op.create_index(
        "ix_experiment_history_experiment_id",
        "experiment_history",
        ["experiment_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_experiment_history_experiment_id", table_name="experiment_history")
    op.drop_table("experiment_history")

    op.drop_index("ix_run_history_experiment_id", table_name="run_history")
    op.drop_column("run_history", "experiment_item_payload")
    op.drop_column("run_history", "experiment_iteration")
    op.drop_column("run_history", "experiment_item_index")
    op.drop_column("run_history", "experiment_desc")
    op.drop_column("run_history", "experiment_id")
