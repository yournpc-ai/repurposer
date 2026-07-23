"""add channel_accounts and publications (Distribution P1)

Revision ID: f4b8e2c91d05
Revises: a7f3c9e21b48
Create Date: 2026-07-23

Distribution module tables (docs/DISTRIBUTION.md §3, 2026-07-23 trimmed P1
scope): ``channel_accounts`` = OAuth token lifecycle (sensitive credential
values Fernet-encrypted, ADR-031); ``publications`` = publish order with state
machine + idempotency, single FK to ``outputs`` (ADR-030).

``publication_events`` (institutional audit trail) is deliberately deferred to
P2 — P1 forensics rely on ``last_error`` + ``attempt_count`` + worker logs.
The claim index covers both claim predicates: ``SCHEDULED`` (time to publish)
and ``PUBLISHING`` (time to poll the platform again) — SQLAlchemy ``Enum``
stores member NAMES in Postgres.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f4b8e2c91d05'
down_revision: Union[str, Sequence[str], None] = 'a7f3c9e21b48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'channel_accounts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('platform', sa.Enum('LINKEDIN', 'TIKTOK', name='channelplatform'), nullable=False),
        sa.Column('platform_user_id', sa.String(length=255), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('avatar_url', sa.String(length=1024), nullable=True),
        sa.Column('scopes', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('credentials_enc', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'status',
            sa.Enum('ACTIVE', 'EXPIRED', 'REVOKED', name='channelaccountstatus'),
            nullable=False,
            server_default='ACTIVE',
        ),
        sa.Column('last_refreshed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.UniqueConstraint('user_id', 'platform', 'platform_user_id', name='uq_channel_account_per_user'),
    )
    op.create_index('ix_channel_accounts_user_id', 'channel_accounts', ['user_id'])

    op.create_table(
        'publications',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('output_id', sa.UUID(), nullable=False),
        sa.Column('channel_account_id', sa.UUID(), nullable=True),
        sa.Column('payload', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('ai_disclosure', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column(
            'state',
            sa.Enum(
                'DRAFT',
                'PENDING_REVIEW',
                'APPROVED',
                'SCHEDULED',
                'PUBLISHING',
                'PUBLISHED',
                'FAILED',
                'CANCELLED',
                name='publicationstate',
            ),
            nullable=False,
            server_default='SCHEDULED',
        ),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('platform_job_id', sa.String(length=512), nullable=True),
        sa.Column('platform_post_id', sa.String(length=512), nullable=True),
        sa.Column('platform_post_url', sa.String(length=1024), nullable=True),
        sa.Column('idempotency_key', sa.String(length=128), nullable=False),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('metrics', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.ForeignKeyConstraint(['output_id'], ['outputs.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['channel_account_id'], ['channel_accounts.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('idempotency_key', name='uq_publications_idempotency_key'),
    )
    op.create_index('ix_publications_user_id', 'publications', ['user_id'])
    op.create_index('ix_publications_user_state', 'publications', ['user_id', 'state'])
    op.create_index(
        'ix_publications_claim',
        'publications',
        ['state', 'due_at'],
        postgresql_where=sa.text("state IN ('SCHEDULED', 'PUBLISHING')"),
    )
    op.create_index('ix_publications_channel_account_id', 'publications', ['channel_account_id'])


def downgrade() -> None:
    op.drop_index('ix_publications_channel_account_id', table_name='publications')
    op.drop_index('ix_publications_claim', table_name='publications')
    op.drop_index('ix_publications_user_state', table_name='publications')
    op.drop_index('ix_publications_user_id', table_name='publications')
    op.drop_table('publications')
    op.drop_index('ix_channel_accounts_user_id', table_name='channel_accounts')
    op.drop_table('channel_accounts')
    sa.Enum(name='publicationstate').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='channelaccountstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='channelplatform').drop(op.get_bind(), checkfirst=True)
