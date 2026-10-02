"""messages suggestion block + suggestion_ref (ADR-099 §4 建议谱系)

Revision ID: p7c2d4e6f8a1
Revises: o2b8f4a6c1e9
Create Date: 2026-10-03

The interaction block for the non-blocking suggestion form (answer +
suggestions): an assistant row's offered options persist ON the row
(lifecycle = the message's, no separate table, never a mention) with
their code-stamped provenance — [{id, label, description, recommended,
source_turn, source_state}]; source_state is the directed stale check's
snapshot (the grounded asset ids at stamp time — zero version counters).
A user row that IS a suggestion pick carries its structured ref
{source_turn, suggestion_id}; the visible content stays the picked label.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'p7c2d4e6f8a1'
down_revision: Union[str, Sequence[str], None] = 'o2b8f4a6c1e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'messages',
        sa.Column(
            'suggestions',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default='[]',
        ),
    )
    op.add_column(
        'messages',
        sa.Column(
            'suggestion_ref',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('messages', 'suggestion_ref')
    op.drop_column('messages', 'suggestions')
