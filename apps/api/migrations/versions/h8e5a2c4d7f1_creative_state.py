"""composition_versions.creative_state — optional immutable authoring state

Revision ID: h8e5a2c4d7f1
Revises: g7d4a1c9e2f6
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "h8e5a2c4d7f1"
down_revision: str | Sequence[str] | None = "g7d4a1c9e2f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "composition_versions",
        sa.Column("creative_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("composition_versions", "creative_state")
