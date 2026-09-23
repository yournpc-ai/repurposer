"""outputs.work_id + outputs.archived_at — work/version 两身份与归档不变量 (ADR-091, N-59)

Revision ID: i8e2f5a13b27
Revises: b2e8f1a94c07
Create Date: 2026-09-24

精确编辑迭代 S1：产物身份从「物理行」升格为「work（用户语义锚）× version
（生产历史）」两身份。work_id 出生 = 自身 id（legacy 行全部回填为单体
work——它们的 ADR-091 前历史已随物理删除蒸发，单体是唯一诚实的身份）；
archived_at 可空时间戳律（NULL = active），wipe 点从此写归档不写删除。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'i8e2f5a13b27'
down_revision: Union[str, Sequence[str], None] = 'b2e8f1a94c07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'outputs',
        sa.Column('work_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    # Singleton works for every legacy row (read-tolerance: each row anchors
    # its own work — there is no older history to chain to).
    op.execute('UPDATE outputs SET work_id = id')
    op.alter_column('outputs', 'work_id', nullable=False)
    op.create_index('ix_outputs_work_id', 'outputs', ['work_id'])
    op.add_column(
        'outputs',
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('outputs', 'archived_at')
    op.drop_index('ix_outputs_work_id', table_name='outputs')
    op.drop_column('outputs', 'work_id')
