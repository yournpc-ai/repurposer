"""Native media generation requests and execution leases."""

from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
import sqlalchemy as sa

revision = "j6c02_media_jobs"
down_revision = "j6c01_narration_identity"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "media_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "receipt_id", sa.Uuid(), sa.ForeignKey("messages.id"), unique=True, nullable=False
        ),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("request", JSONB(), nullable=False),
        sa.Column("authorized_credits", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("claim_token", sa.Uuid()),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_media_jobs_queue", "media_jobs", ["kind", "status", "created_at"])


def downgrade():
    op.drop_table("media_jobs")
