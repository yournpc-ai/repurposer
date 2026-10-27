"""messages.blocks — structured presentation blocks (ADR-145 phase B)

Revision ID: z5d8f1b3a7c2
Revises: y4c7e0b2d6a1
Create Date: 2026-10-27

One JSONB column on messages: server-stamped component references (the
video storyboard card's composition/version identity) that a chat component
resolves to its read DTO. Pure addition, default [], no backfill.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'z5d8f1b3a7c2'
down_revision: Union[str, Sequence[str], None] = 'y4c7e0b2d6a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'messages',
        sa.Column(
            'blocks',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default='[]',
        ),
    )


def downgrade() -> None:
    op.drop_column('messages', 'blocks')
