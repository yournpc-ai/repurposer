"""add wallets / credit_transactions / configs (credits system, ADR-055)

Revision ID: c9d4e7f2a815
Revises: 7d1bce699fd9
Create Date: 2026-09-05

Credits-system day-1 groundwork (docs/BILLING.md §2, W7 credits batch):

- ``wallets`` — one row per user, its own aggregate root (deliberately no
  column on ``users``); lazy-opened at first login. ``balance`` is the
  materialized cache of the ledger — negative balances are allowed by design
  (BILLING §5: a NULL-estimate step may settle past zero; clamping would hide
  the bleed point), so no CHECK constraint. ``version`` is the optimistic
  lock for concurrent holds.
- ``credit_transactions`` — the append-only ledger and sole source of truth
  for every balance change. ``amount`` is signed (hold/capture negative);
  ``balance_after`` chains each row to the balance it produced, so drift is a
  one-query audit; ``idempotency_key`` UNIQUE makes worker restarts / step
  retries / (W11) payment webhook replays dedupe structurally, never via
  check-then-write code. ``kind`` stays a plain string so W11's ``purchase``
  needs no migration.
- ``configs`` — public operating parameters (dotted key namespaces). The code
  registry (app/platform/configs.py CONFIG_REGISTRY) is the sole source of
  truth for keys / defaults / types; the table only carries override values.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c9d4e7f2a815'
down_revision: Union[str, Sequence[str], None] = '7d1bce699fd9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'wallets',
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('balance', sa.BigInteger(), nullable=False, server_default=sa.text('0')),
        sa.Column('version', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('user_id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )

    op.create_table(
        'credit_transactions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('amount', sa.BigInteger(), nullable=False),
        sa.Column('balance_after', sa.BigInteger(), nullable=False),
        sa.Column('ref', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('idempotency_key', sa.String(length=128), nullable=False),
        sa.Column('note', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.UniqueConstraint('idempotency_key', name='uq_credit_transactions_idempotency_key'),
    )
    op.create_index('ix_credit_transactions_user_id', 'credit_transactions', ['user_id'])

    op.create_table(
        'configs',
        sa.Column('key', sa.String(length=128), nullable=False),
        sa.Column('value', postgresql.JSONB(), nullable=False),
        sa.Column('description', sa.String(length=512), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('key'),
    )


def downgrade() -> None:
    op.drop_table('configs')
    op.drop_index('ix_credit_transactions_user_id', table_name='credit_transactions')
    op.drop_table('credit_transactions')
    op.drop_table('wallets')
