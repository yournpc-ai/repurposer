"""merge conversation_usage + canvas_available

Revision ID: 51434b00283c
Revises: t4c6e8a0b2d4, u5c1e8a3f6b9d
Create Date: 2026-10-14 19:47:32.568192

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '51434b00283c'
down_revision: Union[str, Sequence[str], None] = ('t4c6e8a0b2d4', 'u5c1e8a3f6b9d')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
