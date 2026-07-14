"""add project content_plan

Revision ID: eb812df93567
Revises: d46403707861
Create Date: 2026-07-14 20:04:43.741342

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eb812df93567'
down_revision: Union[str, Sequence[str], None] = 'd46403707861'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('projects', sa.Column('content_plan', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('projects', 'content_plan')
