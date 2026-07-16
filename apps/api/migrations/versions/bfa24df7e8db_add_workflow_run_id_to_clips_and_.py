"""add_workflow_run_id_to_clips_and_derivatives

Revision ID: bfa24df7e8db
Revises: b1e9a632a806
Create Date: 2026-07-16 20:48:36.643891

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bfa24df7e8db'
down_revision: Union[str, Sequence[str], None] = 'b1e9a632a806'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add workflow_run_id to clips and derivatives."""
    op.add_column(
        "clips",
        sa.Column(
            "workflow_run_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("workflow_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "derivatives",
        sa.Column(
            "workflow_run_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("workflow_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_clips_workflow_run_id", "clips", ["workflow_run_id"])
    op.create_index("ix_derivatives_workflow_run_id", "derivatives", ["workflow_run_id"])


def downgrade() -> None:
    """Remove workflow_run_id from clips and derivatives."""
    op.drop_index("ix_derivatives_workflow_run_id", table_name="derivatives")
    op.drop_index("ix_clips_workflow_run_id", table_name="clips")
    op.drop_column("derivatives", "workflow_run_id")
    op.drop_column("clips", "workflow_run_id")
