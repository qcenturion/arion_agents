"""initial schema

Revision ID: 0001_initial
Revises: 
Create Date: 2025-09-12 00:00:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.create_table(
        "tools",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.create_table(
        "agent_tools",
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("tool_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tool_id"], ["tools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("agent_id", "tool_id"),
        sa.UniqueConstraint("agent_id", "tool_id", name="uq_agent_tool"),
    )
    op.create_table(
        "agent_routes",
        sa.Column("from_agent_id", sa.Integer(), nullable=False),
        sa.Column("to_agent_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["from_agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("from_agent_id", "to_agent_id"),
        sa.UniqueConstraint("from_agent_id", "to_agent_id", name="uq_agent_route"),
    )


def downgrade() -> None:
    op.drop_table("agent_routes")
    op.drop_table("agent_tools")
    op.drop_table("tools")
    op.drop_table("agents")

