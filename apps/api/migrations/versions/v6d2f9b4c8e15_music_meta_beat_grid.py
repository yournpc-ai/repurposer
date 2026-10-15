"""music.meta — beat grid seat (ADR-121 B3)

Revision ID: v6d2f9b4c8e15
Revises: 51434b00283c
Create Date: 2026-10-15

The film bed's beat grid ({"bpm": float, "beats": [seconds...]}) lives on
the music row — computed ONCE at birth (``create_music_from_generation``,
bytes in hand) or at seed/reconcile time (``seed_default_music`` backfills
catalog rows), read at spec build to snap scene boundaries to the track's
real beats. Runtime never analyzes audio (no aubio/librosa in the deps —
the prohibition is the ADR's). NULL = never analyzed → the spec builder
skips the snap honestly.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'v6d2f9b4c8e15'
down_revision: Union[str, Sequence[str], None] = '51434b00283c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'music',
        sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('music', 'meta')
