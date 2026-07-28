"""add project pending_intent

Revision ID: d7e3b1a95c42
Revises: b6c2a4d18f05
Create Date: 2026-07-28

Unconfirmed task book + original prompt from ``POST /projects/{id}/intent``
(``PendingIntent`` shape: prompt / intent / needs_clarification / reasons /
brand_template_id). Written on every intent call (chat refinements update it),
cleared by ``/generate``. Its presence on a draft project is what "awaiting
confirmation" means — the plan-confirm chat can be resumed exactly, from any
device.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd7e3b1a95c42'
down_revision: Union[str, Sequence[str], None] = 'b6c2a4d18f05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'projects',
        sa.Column('pending_intent', postgresql.JSON(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('projects', 'pending_intent')
