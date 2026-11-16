"""Add content-addressed gallery media identities to SkillVersions.

Revision ID: e1f4a8c2d6b9
Revises: c7e2a5f9b413
Create Date: 2026-11-04

Existing immutable rows stay NULL and read as an empty media collection. Media
bytes remain in object storage; this migration adds no backfill or media table.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e1f4a8c2d6b9"
down_revision: str | Sequence[str] | None = "c7e2a5f9b413"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "skill_versions",
        sa.Column("media", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("skill_versions", "media")
