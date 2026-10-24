"""film_narrations — narration reuse store (ADR-138 R4-A)

Revision ID: x9e3b6d28f501
Revises: w7f2a4c91e06
Create Date: 2026-10-21

One row per (project_id, content_hash): the ORIGINAL speed-1.0 synthesis of
one narration line, reusable across the project's versions/runs. The unique
pair alone does not prevent duplicate TTS calls — every write is
ownership-conditioned (owner_token + status + lease), see the model's
docstring and 总设计 §10.1. Pure addition — no existing row is touched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'x9e3b6d28f501'
down_revision: Union[str, Sequence[str], None] = 'w7f2a4c91e06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'film_narrations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('voice_id', sa.String(length=255), nullable=False),
        sa.Column('language', sa.String(length=16), nullable=False),
        sa.Column('config_hash', sa.String(length=64), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('storage_key', sa.String(length=512), nullable=True),
        sa.Column('duration_s', sa.Float(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('owner_token', sa.String(length=64), nullable=True),
        sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['project_id'], ['projects.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'project_id', 'content_hash', name='uq_film_narrations_project_hash'
        ),
    )


def downgrade() -> None:
    op.drop_table('film_narrations')
