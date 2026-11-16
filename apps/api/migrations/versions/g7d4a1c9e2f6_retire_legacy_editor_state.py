"""Retire the ClipSpec editor and multi-output exploration stores.

Revision ID: g7d4a1c9e2f6
Revises: d6c3a8f1e924
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g7d4a1c9e2f6"
down_revision: Union[str, Sequence[str], None] = "d6c3a8f1e924"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("operations", if_exists=True)
    op.drop_column("graph_nodes", "journey_id", if_exists=True)
    op.drop_column("graph_nodes", "island_id", if_exists=True)
    op.drop_column("graph_nodes", "island_seq", if_exists=True)
    op.drop_table("graph_islands", if_exists=True)
    op.drop_table("exploration_rows", if_exists=True)
    op.drop_table("journeys", if_exists=True)


def downgrade() -> None:
    op.create_table(
        "journeys",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("project_id", sa.UUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("goal_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "exploration_rows",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("project_id", sa.UUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("journey_id", sa.UUID(), sa.ForeignKey("journeys.id", ondelete="CASCADE"), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "graph_islands",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("project_id", sa.UUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("parent_ids", sa.JSON(), nullable=False),
        sa.Column("origin_x", sa.Integer(), nullable=False),
        sa.Column("origin_y", sa.Integer(), nullable=False),
        sa.Column("row_h", sa.Integer(), nullable=False),
        sa.Column("cols", sa.Integer(), nullable=False),
        sa.Column("cap", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.add_column("graph_nodes", sa.Column("island_seq", sa.Integer()))
    op.add_column("graph_nodes", sa.Column("island_id", sa.UUID(), sa.ForeignKey("graph_islands.id", ondelete="SET NULL")))
    op.add_column("graph_nodes", sa.Column("journey_id", sa.UUID(), sa.ForeignKey("journeys.id", ondelete="SET NULL")))
    op.create_table(
        "operations",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("output_id", sa.UUID(), sa.ForeignKey("outputs.id"), nullable=False),
        sa.Column("project_id", sa.UUID(), sa.ForeignKey("projects.id", deferrable=True, initially="DEFERRED"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("op", sa.String(length=50), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("spec_after", sa.JSON(), nullable=False),
        sa.Column("spec_hash", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id")),
        sa.Column("message_id", sa.UUID(), sa.ForeignKey("messages.id")),
        sa.Column("undone_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("output_id", "seq", name="uq_operations_output_seq"),
    )
