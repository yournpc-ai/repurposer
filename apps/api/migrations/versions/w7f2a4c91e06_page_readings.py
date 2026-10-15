"""page_readings — 页面读本表 (world-seat 存储层)

Revision ID: w7f2a4c91e06
Revises: v6d2f9b4c8e15
Create Date: 2026-10-16

One stored reading per (project, url) — the canonical page text the whole
project reuses (chat read tool's write-through fetch + the web_page
capture chain write here; ``app/tools/world.py`` is the read seat).
Snapshot semantics: text is a capture as of fetched_at; re-fetch is an
explicit act, never an implicit TTL. Cascades with the project.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'w7f2a4c91e06'
down_revision: Union[str, Sequence[str], None] = 'v6d2f9b4c8e15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'page_readings',
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('url', sa.String(length=512), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('project_id', 'url'),
    )


def downgrade() -> None:
    op.drop_table('page_readings')
