"""Add CANCELLED to workflow and render statuses.

Revision ID: b8d5e3f1a720
Revises: a7f4c2e8b619
Create Date: 2026-10-31

Additive-only enum migration; no existing rows are rewritten.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "b8d5e3f1a720"
down_revision: Union[str, Sequence[str], None] = "a7f4c2e8b619"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE workflowstatus ADD VALUE IF NOT EXISTS 'CANCELLED'")
        op.execute("ALTER TYPE renderstatus ADD VALUE IF NOT EXISTS 'CANCELLED'")


def downgrade() -> None:
    # PostgreSQL enum values are not removed in place; downgrade leaves the
    # additive value dormant rather than rewriting or recreating user tables.
    pass
