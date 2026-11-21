"""Fence independent asset processing across worker restarts."""

from alembic import op
import sqlalchemy as sa

revision = "j6d03_asset_claims"
down_revision = "j6d02_publication_dispatch"
branch_labels = depends_on = None


def upgrade():
    op.add_column("assets", sa.Column("claim_token", sa.Uuid()))
    op.add_column("assets", sa.Column("lease_until", sa.DateTime(timezone=True)))
    op.execute("UPDATE assets SET lease_until = CURRENT_TIMESTAMP WHERE processing_status = 'PROCESSING'")


def downgrade():
    op.drop_column("assets", "lease_until")
    op.drop_column("assets", "claim_token")
