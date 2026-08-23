"""add outputs quality verdict

Revision ID: b7c2d4e6f801
Revises: 3a1c5e9b72d8
Create Date: 2026-08-23

产物质量线期 3 (docs/tasks/output-quality-line.md §2.4): the verify node's
verdict lands on the product row — ``outputs.quality`` JSONB nullable
({status: passed|needs_human, checks: [{id, ok, detail, cls}], attempt,
checked_at}). NULL = never verified (legacy rows / verify-less graphs).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b7c2d4e6f801'
down_revision: Union[str, Sequence[str], None] = '3a1c5e9b72d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'outputs',
        sa.Column('quality', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('outputs', 'quality')
