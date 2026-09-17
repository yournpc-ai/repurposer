"""conversations.ui_language — the interface-language owner (ADR-080, 2026-09-17)

Revision ID: h7d1e4a93b26
Revises: g5c9e3a72f14
Create Date: 2026-09-17

单一叙事者律的持久化半：会话的界面语言有唯一 owner。请求链的
Accept-Language 在每个用户 chat 回合（prepare_chat_turn）盖章到
conversations.ui_language；一切 assistant 写者（plan / chat / trigger /
未来的 worker 生言语）继承它，不做 per-writer 推导——2026-09-16 事故里
plan 说英文、trigger 被中文素材拖拽说中文的分叉在结构上不再可能。

Nullable, no backfill: legacy rows read as "owner 未盖章" — the trigger's
resolution chain falls through to the run pin / history inference (the
pre-ADR-080 behavior), which is exactly right for conversations that have
not seen a request since.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'h7d1e4a93b26'
down_revision: Union[str, Sequence[str], None] = 'g5c9e3a72f14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'conversations',
        sa.Column('ui_language', sa.String(length=10), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('conversations', 'ui_language')
