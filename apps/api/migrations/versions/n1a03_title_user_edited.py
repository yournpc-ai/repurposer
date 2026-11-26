"""Add title_user_edited flag to projects and conversations.

Revision ID: n1a03_title_user_edited
Revises: n1a02_sample_waveform_peaks
Create Date: 2026-11-27

Records whether a user manually renamed a project or conversation so
automatic progressive title derivation/summarization never overwrites
explicit user edits.
"""

from alembic import op
import sqlalchemy as sa

revision = "n1a03_title_user_edited"
down_revision = "n1a02_sample_waveform_peaks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "title_user_edited",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "title_user_edited",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("conversations", "title_user_edited")
    op.drop_column("projects", "title_user_edited")
