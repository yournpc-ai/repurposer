"""add workflow step estimate

Revision ID: 07d997444570
Revises: b8e4f2a91c63
Create Date: 2026-08-10 19:02:01.328338

Quotation foundation (ADR-039 P4, N-34): the plan side of the
plan-plus-ledger step row. ``estimate`` holds the node's compile-time
self-quotation ({prompt_tokens: [low, high], completion_tokens: [low,
high], units: {…}} — agent token ranges / mechanical exact units /
free zeros); ``cost`` stays the metering ledger (ADR-025). NULL = never
estimated (pre-migration rows, runtime fan-out steps, quantities
unknowable at compile). The ONLY table change of the estimate
foundation — autogenerate's unrelated drift detections
(operations.created_at, the publications index) are deliberately NOT
carried here.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '07d997444570'
down_revision: Union[str, Sequence[str], None] = 'b8e4f2a91c63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'workflow_steps',
        sa.Column('estimate', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('workflow_steps', 'estimate')
