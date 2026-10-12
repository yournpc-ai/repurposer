"""conversation_usage 会话层计量台账 (ADR-117 D3)

Revision ID: t4c6e8a0b2d4
Revises: s2b7d4e6f1a3
Create Date: 2026-10-12

会话层 LLM token 计量但不收费：每回合一行的 COGS 台账（tool loop 多轮
迭代聚合为一行），与回合 assistant 消息同一 commit 落库。永不上用户账
单、永不上 UI——用途 = COGS 可见性 + W11 fair-use 配额数据基础 +
context 预算校准数据源。owner = 平台层（MODULE_ARCH §4 登记）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 't4c6e8a0b2d4'
down_revision: Union[str, Sequence[str], None] = 's2b7d4e6f1a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'conversation_usage',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'user_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id'),
            nullable=False,
        ),
        sa.Column(
            'project_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('projects.id'),
            nullable=True,
        ),
        sa.Column('prompt_tokens', sa.BigInteger(), nullable=False),
        sa.Column('completion_tokens', sa.BigInteger(), nullable=False),
        sa.Column('cached_tokens', sa.BigInteger(), nullable=True),
        sa.Column('cost_usd', sa.Float(), nullable=False),
        sa.Column('model', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        'ix_conversation_usage_user_created',
        'conversation_usage',
        ['user_id', 'created_at'],
    )
    op.create_index(
        'ix_conversation_usage_project_created',
        'conversation_usage',
        ['project_id', 'created_at'],
    )


def downgrade() -> None:
    op.drop_index(
        'ix_conversation_usage_project_created', table_name='conversation_usage'
    )
    op.drop_index(
        'ix_conversation_usage_user_created', table_name='conversation_usage'
    )
    op.drop_table('conversation_usage')
