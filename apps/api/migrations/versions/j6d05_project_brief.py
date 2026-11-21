"""Remove the task-plan projection from project briefing and presentation facts."""

from alembic import op

revision = "j6d05_project_brief"
down_revision = "j6d04_retire_workflow"
branch_labels = depends_on = None


def upgrade():
    op.execute("""
        UPDATE projects
        SET pending_brief = (pending_brief::jsonb -
            ARRAY['intent','derived','plans','plan_task_map','reasons','needs_clarification'])::json
        WHERE json_typeof(pending_brief) = 'object' AND pending_brief::jsonb ?|
            ARRAY['intent','derived','plans','plan_task_map','reasons','needs_clarification']
    """)


def downgrade():
    raise RuntimeError("Retired task plans are not reconstructible.")
