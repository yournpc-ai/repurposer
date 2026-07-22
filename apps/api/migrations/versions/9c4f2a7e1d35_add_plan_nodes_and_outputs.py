"""add_plan_nodes_and_outputs

Revision ID: 9c4f2a7e1d35
Revises: bfa24df7e8db
Create Date: 2026-07-22

RunPlan Phase 1 (ADR-028/030): create the plan_nodes execution-plan table and
the unified outputs product table. Additive only — clips/derivatives,
projects.content_plan, and workflow_runs.current_step are dropped by the
follow-up migration once every consumer has moved (docs/tasks/
runplan-phase1-implementation.md §3, R1 tree-green discipline).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '9c4f2a7e1d35'
down_revision: Union[str, Sequence[str], None] = 'bfa24df7e8db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create plan_nodes + outputs with their indexes."""
    op.create_table(
        "plan_nodes",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "inputs",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "spec",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "output_refs",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("cost", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_plan_nodes_run_status", "plan_nodes", ["run_id", "status"])
    op.create_index("ix_plan_nodes_kind_status", "plan_nodes", ["kind", "status"])

    op.create_table(
        "outputs",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column(
            "plan_node_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("plan_nodes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("language", sa.String(10), nullable=True, server_default="zh"),
        sa.Column("status", sa.String(50), nullable=True, server_default="generated"),
        sa.Column("provenance", sa.String(20), nullable=False, server_default="real"),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "files",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("source_ref", postgresql.JSONB(), nullable=True),
        sa.Column("render_spec", postgresql.JSONB(), nullable=True),
        sa.Column(
            "render_status",
            postgresql.ENUM(
                "PENDING",
                "RENDERING",
                "COMPLETED",
                "FAILED",
                name="renderstatus",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("render_error", sa.Text(), nullable=True),
        sa.Column("score", postgresql.JSONB(), nullable=True),
        sa.Column(
            "publishing",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_outputs_project_type", "outputs", ["project_id", "type"])
    op.create_index("ix_outputs_plan_node_id", "outputs", ["plan_node_id"])
    op.create_index(
        "ix_outputs_render_status",
        "outputs",
        ["render_status"],
        postgresql_where=sa.text("render_status IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop outputs + plan_nodes."""
    op.drop_index("ix_outputs_render_status", table_name="outputs")
    op.drop_index("ix_outputs_plan_node_id", table_name="outputs")
    op.drop_index("ix_outputs_project_type", table_name="outputs")
    op.drop_table("outputs")
    op.drop_index("ix_plan_nodes_kind_status", table_name="plan_nodes")
    op.drop_index("ix_plan_nodes_run_status", table_name="plan_nodes")
    op.drop_table("plan_nodes")
