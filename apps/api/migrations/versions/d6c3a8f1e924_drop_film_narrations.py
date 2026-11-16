"""Drop the retired Film narration store.

Revision ID: d6c3a8f1e924
Revises: b4e9d2c7a810
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d6c3a8f1e924"
down_revision: Union[str, Sequence[str], None] = "b4e9d2c7a810"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("film_narrations")


def downgrade() -> None:
    op.create_table(
        "film_narrations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("voice_id", sa.String(length=255), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("config_hash", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=True),
        sa.Column("duration_s", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("owner_token", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "content_hash", name="uq_film_narrations_project_hash"
        ),
    )
