"""messages.seq — transcript 数组序 (ADR-108)

Revision ID: r8f1a3c5d7e9
Revises: q3d9e5f7a2b4
Create Date: 2026-10-07

持久化顺序即渲染顺序：messages.seq = per-conversation 单调序号（数组位置），
渲染序 = seq 序，时间戳只用于显示。

分配器计数器住独立表 message_seq_counters（FK → conversations，CASCADE），
永不与回合事务共享行锁——回合事务从 prepare 起就持有 conversations 行锁
（ui_language 盖章 + 首次 flush），若计数器住 conversations 行，分配器的
独立短事务 UPDATE 同 row 即自死锁（prepare → checkpoint 路径必中）。

Backfill: 存量行按 (created_at, id) 编 row_number；计数器回填为各会话最大值。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'r8f1a3c5d7e9'
down_revision: Union[str, Sequence[str], None] = 'q3d9e5f7a2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'messages',
        sa.Column('seq', sa.BigInteger(), nullable=True),
    )
    op.execute(
        """
        WITH numbered AS (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY conversation_id
                       ORDER BY created_at, id
                   ) AS rn
            FROM messages
        )
        UPDATE messages m SET seq = n.rn FROM numbered n WHERE m.id = n.id
        """
    )
    op.create_table(
        'message_seq_counters',
        sa.Column(
            'conversation_id',
            sa.UUID(),
            sa.ForeignKey('conversations.id', ondelete='CASCADE'),
            primary_key=True,
        ),
        sa.Column('last_seq', sa.BigInteger(), nullable=False, server_default='0'),
    )
    op.execute(
        """
        INSERT INTO message_seq_counters (conversation_id, last_seq)
        SELECT c.id, COALESCE(
            (SELECT MAX(m.seq) FROM messages m WHERE m.conversation_id = c.id), 0
        )
        FROM conversations c
        """
    )
    op.create_index(
        'ix_messages_conversation_seq', 'messages', ['conversation_id', 'seq']
    )


def downgrade() -> None:
    op.drop_index('ix_messages_conversation_seq', table_name='messages')
    op.drop_table('message_seq_counters')
    op.drop_column('messages', 'seq')
