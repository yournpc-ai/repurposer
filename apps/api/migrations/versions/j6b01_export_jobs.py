"""Durable ownership of a native export. Existing versions, outputs and ledger rows stay in place."""

from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
import sqlalchemy as sa

revision = "j6b01_export_jobs"
down_revision = "h8e5a2c4d7f1"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "export_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "receipt_id", sa.Uuid(), sa.ForeignKey("messages.id"), unique=True, nullable=False
        ),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "version_id", sa.Uuid(), sa.ForeignKey("composition_versions.id"), nullable=False
        ),
        sa.Column("render_spec", JSONB(), nullable=False),
        sa.Column("authorized_credits", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("claim_token", sa.Uuid()),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_export_jobs_queue", "export_jobs", ["status", "created_at"])


def downgrade():
    op.drop_table("export_jobs")
