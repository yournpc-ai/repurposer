"""narration_alignments — final-audio/script alignment and semantic readiness

Revision ID: c7e2a5f9b413
Revises: d7f3b20c9a41
Create Date: 2026-11-03

The fifth worker claim source stores deterministic word timing separately
from Agent-authored semantics. String statuses keep the state machine
explicit without a PostgreSQL ENUM.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c7e2a5f9b413"
down_revision: Union[str, Sequence[str], None] = "d7f3b20c9a41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "narration_alignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("audio_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_digest", sa.String(length=64), nullable=False),
        sa.Column("audio_digest", sa.String(length=64), nullable=False),
        sa.Column("algorithm", sa.String(length=64), nullable=False),
        sa.Column("normalization_version", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("source_timebase", sa.Integer(), nullable=False),
        sa.Column("timing_digest", sa.String(length=64), nullable=True),
        sa.Column("content_digest", sa.String(length=64), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("claim_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["audio_snapshot_id"], ["source_snapshots.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id",
            "audio_snapshot_id",
            "text_digest",
            "algorithm",
            "normalization_version",
            "provider",
            "model",
            name="uq_narration_alignments_source_script_algorithm",
        ),
    )
    op.create_index(
        "ix_narration_alignments_owner_id", "narration_alignments", ["owner_id"]
    )
    op.create_index(
        "ix_narration_alignments_audio_snapshot_id",
        "narration_alignments",
        ["audio_snapshot_id"],
    )
    op.create_index("ix_narration_alignments_status", "narration_alignments", ["status"])


def downgrade() -> None:
    op.drop_index("ix_narration_alignments_status", table_name="narration_alignments")
    op.drop_index(
        "ix_narration_alignments_audio_snapshot_id", table_name="narration_alignments"
    )
    op.drop_index("ix_narration_alignments_owner_id", table_name="narration_alignments")
    op.drop_table("narration_alignments")
