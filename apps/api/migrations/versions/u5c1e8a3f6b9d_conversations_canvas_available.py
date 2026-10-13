"""conversations.canvas_available — 环境能力位 owner (ADR-118 §6)

Revision ID: u5c1e8a3f6b9d
Revises: t1a3c5e7b9d2
Create Date: 2026-10-14

The client's raw can-host-canvas read, stamped from the chat request every
user turn (last-wins, ui_language 同律座) — the ONE environment fact the
worker-born delivery turn inherits for canvas_visible
(app/chat/canvas_visibility.py). NULL = never reported → the context's
Environment line is omitted and the handoff-sentence gate stays closed
(未知恒闭, 永不编造). No backfill: existing rows honestly read unknown.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'u5c1e8a3f6b9d'
down_revision: Union[str, Sequence[str], None] = 't1a3c5e7b9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'conversations',
        sa.Column('canvas_available', sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('conversations', 'canvas_available')
