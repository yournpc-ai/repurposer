"""clip render_spec + drop dead columns

Revision ID: 99efa033eb5c
Revises: 8565f7764dc8
Create Date: 2026-06-27 02:02:38.710092

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '99efa033eb5c'
down_revision: str | Sequence[str] | None = '8565f7764dc8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

render_status = postgresql.ENUM(
    'PENDING', 'RENDERING', 'COMPLETED', 'FAILED', name='renderstatus'
)


def upgrade() -> None:
    """Upgrade schema."""
    # Drop dead ADR-008 image-carousel scaffolding (never written/read).
    op.drop_column('assets', 'keyframes')
    op.drop_column('clips', 'subtitles')

    # Vertical-clip render contract + job state. render_status nullable
    # (NULL = render not requested), so no backfill needed.
    render_status.create(op.get_bind(), checkfirst=True)
    op.add_column('clips', sa.Column('render_spec', sa.JSON(), nullable=True))
    op.add_column(
        'clips',
        sa.Column(
            'render_status',
            sa.Enum(
                'PENDING', 'RENDERING', 'COMPLETED', 'FAILED',
                name='renderstatus', create_type=False,
            ),
            nullable=True,
        ),
    )
    op.add_column('clips', sa.Column('render_error', sa.Text(), nullable=True))
    op.add_column('clips', sa.Column('srt_url', sa.String(length=512), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('clips', 'srt_url')
    op.drop_column('clips', 'render_error')
    op.drop_column('clips', 'render_status')
    op.drop_column('clips', 'render_spec')
    render_status.drop(op.get_bind(), checkfirst=True)

    op.add_column(
        'clips',
        sa.Column('subtitles', postgresql.JSON(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        'assets',
        sa.Column('keyframes', postgresql.JSON(astext_type=sa.Text()), nullable=True),
    )
