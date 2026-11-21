"""Fence irreversible social posts and retain unresolved publication receipts."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "j6d02_publication_dispatch"
down_revision = "j6d01_retire_canvas"
branch_labels = depends_on = None


def upgrade():
    op.execute("ALTER TYPE publicationstate ADD VALUE IF NOT EXISTS 'UNKNOWN'")
    op.add_column("publications", sa.Column("claim_token", sa.Uuid()))
    op.add_column("publications", sa.Column("dispatch_started_at", sa.DateTime(timezone=True)))
    op.add_column("publications", sa.Column("reconciliation", JSONB))
    # An interrupted pre-upgrade attempt has no durable send boundary.
    op.execute("UPDATE publications SET dispatch_started_at = CURRENT_TIMESTAMP "
               "WHERE (state = 'PUBLISHING' OR (state = 'SCHEDULED' AND attempt_count > 0)) "
               "AND (platform_job_id IS NULL OR payload->'channel'->>'platform' IS DISTINCT FROM 'tiktok')")


def downgrade():
    raise NotImplementedError("Unresolved external publication identities must be retained.")
