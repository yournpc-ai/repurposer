"""messages.turn_id — explicit opening-user-turn association

Revision ID: a7f4c2e8b619
Revises: f7a2c4d9e1b6
Create Date: 2026-10-30

Nullable self-reference for newly written user-turn facts. No backfill: old
rows and independent trigger/material facts keep NULL rather than acquiring
an inferred relationship from transcript adjacency.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a7f4c2e8b619"
down_revision: Union[str, Sequence[str], None] = "f7a2c4d9e1b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("turn_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_messages_turn_id_messages",
        "messages",
        "messages",
        ["turn_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_messages_turn_id_messages", "messages", type_="foreignkey")
    op.drop_column("messages", "turn_id")
