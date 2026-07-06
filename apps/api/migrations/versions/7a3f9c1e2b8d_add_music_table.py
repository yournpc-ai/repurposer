"""add music table

Revision ID: 7a3f9c1e2b8d
Revises: 0b19cd023b4a
Create Date: 2026-07-06 22:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a3f9c1e2b8d'
down_revision: Union[str, Sequence[str], None] = '0b19cd023b4a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the ``music`` table.

    Schema-only: the 3 default pieces are generated + committed under
    ``assets/music/`` and seeded into this table at app startup by
    ``services/music.seed_default_music`` (see docs/MUSIC_ARCHITECTURE.md).
    """
    op.create_table(
        'music',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('mood', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('ext', sa.String(length=8), nullable=False),
        sa.Column('file_path', sa.String(length=512), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.Column('prompt', sa.Text(), nullable=True),
        sa.Column('model', sa.String(length=100), nullable=True),
        sa.Column('generation_id', sa.String(length=255), nullable=True),
        sa.Column('license', sa.String(length=100), nullable=True),
        sa.Column('source_url', sa.String(length=512), nullable=True),
        sa.Column('attribution', sa.Text(), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('generated_by_user_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('mood'),
    )
    op.create_foreign_key(
        'fk_music_generated_by_user_id_users',
        'music',
        'users',
        ['generated_by_user_id'],
        ['id'],
    )


def downgrade() -> None:
    """Drop the ``music`` table (audio files on disk are left untouched)."""
    op.drop_constraint(
        'fk_music_generated_by_user_id_users',
        'music',
        type_='foreignkey',
    )
    op.drop_table('music')