"""Persist reusable tool exchanges on their conversation.

Revision ID: b4e9d2c7a810
Revises: a3f8c2d91e47
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b4e9d2c7a810"
down_revision = "a3f8c2d91e47"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("conversations", sa.Column("context", postgresql.JSONB(), nullable=False,
                                            server_default=sa.text("'{\"schema_version\": 1, \"items\": []}'::jsonb")))


def downgrade():
    op.drop_column("conversations", "context")
