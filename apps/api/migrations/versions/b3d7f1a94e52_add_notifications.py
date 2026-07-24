"""add notifications table (platform-layer event stream)

Revision ID: b3d7f1a94e52
Revises: f4b8e2c91d05
Create Date: 2026-07-24

The bell dropdown is the presentation layer for thin events (publish
succeeded/failed, channel expired; feature announcements later) — they
surface as notifications instead of growing dedicated pages. ``type`` is a
plain string so new sources don't need migrations. Table ownership is
registered in docs/MODULE_ARCHITECTURE.md §4 (platform layer, not
Distribution-private).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b3d7f1a94e52'
down_revision: Union[str, Sequence[str], None] = 'f4b8e2c91d05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notifications',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('type', sa.String(length=64), nullable=False),
        sa.Column('payload', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )
    op.create_index('ix_notifications_user_id', 'notifications', ['user_id'])
    op.create_index('ix_notifications_user_created', 'notifications', ['user_id', 'created_at'])
    op.create_index(
        'ix_notifications_user_unread',
        'notifications',
        ['user_id'],
        postgresql_where=sa.text('read_at IS NULL'),
    )


def downgrade() -> None:
    op.drop_index('ix_notifications_user_unread', table_name='notifications')
    op.drop_index('ix_notifications_user_created', table_name='notifications')
    op.drop_index('ix_notifications_user_id', table_name='notifications')
    op.drop_table('notifications')
