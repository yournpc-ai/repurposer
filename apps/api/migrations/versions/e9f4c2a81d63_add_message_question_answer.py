"""add message question answer

Revision ID: e9f4c2a81d63
Revises: d7e3b1a95c42
Create Date: 2026-07-29

Ask primitive (docs/tasks/intent-ask-primitive.md, phase 1): one message row,
two states. ``question`` is the typed payload ({kind: task_book|choice|confirm,
options, allow_freeform, cost_hint}); ``answer`` NULL = pending. Pending
questions live in the QuestionDock above the input; answered ones archive in
the flow as QA pairs. ``content`` keeps the question's human text so it enters
the LLM context history naturally.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e9f4c2a81d63'
down_revision: Union[str, Sequence[str], None] = 'd7e3b1a95c42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'messages',
        sa.Column('question', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        'messages',
        sa.Column('answer', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('messages', 'answer')
    op.drop_column('messages', 'question')
