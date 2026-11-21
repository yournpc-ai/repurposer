"""Remove the retired execution tables and their mirrors."""

from alembic import op

revision = "j6d04_retire_workflow"
down_revision = "j6d03_asset_claims"
branch_labels = depends_on = None


def upgrade():
    op.drop_index("uq_messages_trigger_review", table_name="messages")
    op.drop_column("messages", "workflow_run_id")
    for name in ("workflow_step_id", "render_error", "render_claim_token", "render_attempt", "render_barrier"):
        op.drop_column("outputs", name)
    op.drop_table("workflow_steps")
    op.drop_table("workflow_runs")
    op.execute("DROP TYPE workflowstatus")


def downgrade():
    raise RuntimeError("Retired execution history cannot be restored from the current schema.")
