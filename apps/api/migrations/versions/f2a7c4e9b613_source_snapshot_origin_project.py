"""Retain the birth Chat on prepared asset-less source snapshots.

Revision ID: f2a7c4e9b613
Revises: e1f4a8c2d6b9
Create Date: 2026-11-06

This is provenance for later project-context reads, not an ownership grant.
Existing snapshot identities, digests and composition bindings stay unchanged.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f2a7c4e9b613"
down_revision: str | Sequence[str] | None = "e1f4a8c2d6b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "source_snapshots",
        sa.Column("origin_project_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_source_snapshots_origin_project_id_projects",
        "source_snapshots",
        "projects",
        ["origin_project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_source_snapshots_origin_project_id",
        "source_snapshots",
        ["origin_project_id"],
    )
    op.execute(
        """
        UPDATE source_snapshots AS snapshot
        SET origin_project_id = asset.project_id
        FROM assets AS asset
        WHERE snapshot.asset_id = asset.id
          AND snapshot.origin_project_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE source_snapshots AS derivative
        SET origin_project_id = source.origin_project_id
        FROM source_snapshots AS source
        WHERE source.id = (derivative.meta->>'web_snapshot_id')::uuid
          AND derivative.origin_project_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_source_snapshots_origin_project_id", table_name="source_snapshots")
    op.drop_constraint(
        "fk_source_snapshots_origin_project_id_projects",
        "source_snapshots",
        type_="foreignkey",
    )
    op.drop_column("source_snapshots", "origin_project_id")
