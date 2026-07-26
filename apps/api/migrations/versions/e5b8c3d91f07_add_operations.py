"""add operations table (Operation Model, ADR-032)

产物级编辑操作日志：三前端（editor/chat/mcp）共用，快照式 undo（spec_after），
append-only + undone_at 可空时间戳。判例 N-16：restore_range 独立 op 否决，
恢复语义全归快照层。

Revision ID: e5b8c3d91f07
Revises: c4a9e2f17b03
Create Date: 2026-07-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "e5b8c3d91f07"
down_revision: Union[str, Sequence[str], None] = "c4a9e2f17b03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "operations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "output_id",
            UUID(as_uuid=True),
            sa.ForeignKey("outputs.id"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("op", sa.String(50), nullable=False),
        sa.Column("params", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("spec_after", JSONB, nullable=False),
        sa.Column("spec_hash", sa.String(64), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "message_id",
            UUID(as_uuid=True),
            sa.ForeignKey("messages.id"),
            nullable=True,
        ),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("output_id", "seq", name="uq_operations_output_seq"),
    )
    op.create_index("ix_operations_output_id", "operations", ["output_id"])
    op.create_index("ix_operations_project_id", "operations", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_operations_project_id", table_name="operations")
    op.drop_index("ix_operations_output_id", table_name="operations")
    op.drop_table("operations")
