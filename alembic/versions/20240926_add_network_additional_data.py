"""Add additional_data column to cfg_networks for network-level metadata."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from arion_agents.db import JSONType

# revision identifiers, used by Alembic.
revision = "20240926_network_meta"
down_revision = "20240925_add_experiment_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cfg_networks",
        sa.Column("additional_data", JSONType, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cfg_networks", "additional_data")
