"""add message focus output

Revision ID: 3a1c5e9b72d8
Revises: 07d997444570
Create Date: 2026-08-13 21:30:00.000000

Focus persistence (ADR-041 D8 修订 — 灰行入流): the canvas product a chat
turn was pointed at, denormalized ``{id, label}`` like ``mentions``. The
rebuilt history renders the gray focus prefix row on the user message
after a refresh — the flow stays honest across sessions. NULL = a turn
with no pointed-at product (the overwhelming default).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3a1c5e9b72d8'
down_revision: Union[str, Sequence[str], None] = '07d997444570'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'messages',
        sa.Column('focus_output', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('messages', 'focus_output')
