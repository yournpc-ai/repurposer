"""drop_clips_derivatives_and_retired_columns

Revision ID: 3e8a1f5b9c02
Revises: 9c4f2a7e1d35
Create Date: 2026-07-22

RunPlan Phase 1 destructive sweep (ADR-028/030): clips and derivatives are
replaced by the unified outputs table; projects.content_plan is replaced by
internal outputs[type=content_plan] rows; workflow_runs.current_step is
replaced by plan_nodes queries. No data is preserved (demo seed rebuilds).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '3e8a1f5b9c02'
down_revision: Union[str, Sequence[str], None] = '9c4f2a7e1d35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop clips/derivatives and the retired columns."""
    op.drop_table("derivatives")
    op.drop_table("clips")
    op.execute("DROP TYPE IF EXISTS derivativetype")
    op.drop_column("projects", "content_plan")
    op.drop_column("workflow_runs", "current_step")


def downgrade() -> None:
    """Recreate the retired structures (empty — data was never migrated)."""
    op.add_column(
        "workflow_runs",
        sa.Column("current_step", sa.String(100), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("content_plan", sa.JSON(), nullable=True),
    )
    op.execute(
        "CREATE TYPE derivativetype AS ENUM "
        "('POST', 'QUOTES', 'CAROUSEL', 'ARTICLE')"
    )
    op.create_table(
        "clips",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", sa.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("workflow_run_id", sa.UUID(as_uuid=True), sa.ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("hook", sa.String(500), nullable=False),
        sa.Column("title_options", sa.JSON(), nullable=True),
        sa.Column("music_mood", sa.String(50), nullable=True),
        sa.Column("status", sa.String(50), nullable=True),
        sa.Column("video_url", sa.String(512), nullable=True),
        sa.Column("duration", sa.Integer(), nullable=True),
        sa.Column("language", sa.String(10), nullable=True),
        sa.Column("source_segment", sa.JSON(), nullable=True),
        sa.Column("render_spec", sa.JSON(), nullable=True),
        sa.Column(
            "render_status",
            postgresql.ENUM("PENDING", "RENDERING", "COMPLETED", "FAILED", name="renderstatus", create_type=False),
            nullable=True,
        ),
        sa.Column("render_error", sa.Text(), nullable=True),
        sa.Column("srt_url", sa.String(512), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("hashtags", sa.JSON(), nullable=True),
        sa.Column("cover_image_url", sa.String(512), nullable=True),
        sa.Column("topic", sa.String(255), nullable=True),
        sa.Column("start_time", sa.Float(), nullable=True),
        sa.Column("end_time", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "derivatives",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", sa.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("workflow_run_id", sa.UUID(as_uuid=True), sa.ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("type", postgresql.ENUM("POST", "QUOTES", "CAROUSEL", "ARTICLE", name="derivativetype", create_type=False), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("language", sa.String(10), nullable=True),
        sa.Column("image_url", sa.String(512), nullable=True),
        sa.Column("status", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
