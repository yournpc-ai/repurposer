"""Separate Skill source identity from full immutable version identity.

Revision ID: d7f3b20c9a41
Revises: c6e2a91f4b30
Create Date: 2026-11-01

Existing versions stay immutable and receive no backfill; the store compares
all draft fields when replaying one of those pre-digest rows.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7f3b20c9a41"
down_revision: str | Sequence[str] | None = "c6e2a91f4b30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_skill_versions_source_hash", "skill_versions", type_="unique")
    op.add_column(
        "skill_versions",
        sa.Column("version_digest", sa.String(length=64), nullable=True),
    )
    op.create_unique_constraint(
        "uq_skill_versions_version_digest",
        "skill_versions",
        ["skill_id", "version_digest"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_skill_versions_version_digest", "skill_versions", type_="unique")
    op.drop_column("skill_versions", "version_digest")
    op.create_unique_constraint(
        "uq_skill_versions_source_hash",
        "skill_versions",
        ["skill_id", "source_hash"],
    )
