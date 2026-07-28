"""add asset title

Revision ID: b6c2a4d18f05
Revises: e5b8c3d91f07
Create Date: 2026-07-28

User-facing display name for ``assets`` (defaults to the original upload
filename). The storage key in ``file_url`` embeds a random suffix and is not
presentable; ``title`` gives speaker materials (and later project assets) a
renameable label without touching storage.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6c2a4d18f05'
down_revision: Union[str, Sequence[str], None] = 'e5b8c3d91f07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('assets', sa.Column('title', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('assets', 'title')
