"""video_narrations — cross-Chat original speech and alignment reuse

Revision ID: a6e9c2d4f801
Revises: z5d8f1b3a7c2
Create Date: 2026-10-28

User-scoped speed-1.0 originals, occupancy and outcome-unknown facts for the
CompositionVersion narration producer. No Film rows are moved or rewritten.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a6e9c2d4f801"
down_revision: Union[str, Sequence[str], None] = "z5d8f1b3a7c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "video_narrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("voice_id", sa.String(length=255), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("config_hash", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=True),
        sa.Column("audio_digest", sa.String(length=64), nullable=True),
        sa.Column("duration_s", sa.Float(), nullable=True),
        sa.Column("subtitle_file", sa.Text(), nullable=True),
        sa.Column("subtitles", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("alignment_digest", sa.String(length=64), nullable=True),
        sa.Column("usage_characters", sa.Integer(), nullable=True),
        sa.Column("trace_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("owner_token", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "content_hash", name="uq_video_narrations_user_hash"),
    )


def downgrade() -> None:
    op.drop_table("video_narrations")
