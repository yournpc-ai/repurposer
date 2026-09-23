"""users.settings JSONB — confirm_strategy 的用户级座位 (ADR-092 §1, E5)

Revision ID: j9f3a6b24c38
Revises: i8e2f5a13b27
Create Date: 2026-09-24

计费偏好集成 S4：confirm_strategy ∈ {always, large, never} 落用户级设置
（persona brand/voice JSONB 的 user 级先例）。NULL = 全默认（读容忍 —
默认 large，前端 localStorage 降级为首访回退）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'j9f3a6b24c38'
down_revision: Union[str, Sequence[str], None] = 'i8e2f5a13b27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('users', 'settings')
