"""rename projects.pending_intent → pending_brief (PendingIntent → PendingBrief)

Revision ID: 7d1bce699fd9
Revises: d4e9f3a17b25
Create Date: 2026-09-03

ADR-052 判词 3 / NAMING N-45（brief 账本）：the docked unconfirmed task book
is a *brief*, not an intent — the intent router's verdict is the intent, the
persisted working copy is the brief. Column rename only; 存量行随列走零丢失
(JSON 列，无约束/索引引用).
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '7d1bce699fd9'
down_revision: Union[str, Sequence[str], None] = 'd4e9f3a17b25'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("projects", "pending_intent", new_column_name="pending_brief")


def downgrade() -> None:
    op.alter_column("projects", "pending_brief", new_column_name="pending_intent")
