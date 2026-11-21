"""Retain the original paid execution when alignment ownership changes."""

import sqlalchemy as sa
from alembic import op

revision = "j6c01_narration_identity"
down_revision = "j6b01_export_jobs"
branch_labels = depends_on = None


def upgrade():
    op.add_column("video_narrations", sa.Column("synthesis_execution_id", sa.String(128)))


def downgrade():
    op.drop_column("video_narrations", "synthesis_execution_id")
