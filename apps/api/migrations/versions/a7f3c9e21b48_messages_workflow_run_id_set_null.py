"""messages_workflow_run_id_set_null

Revision ID: a7f3c9e21b48
Revises: 3e8a1f5b9c02
Create Date: 2026-07-23

messages.workflow_run_id carried no ondelete rule, so deleting a workflow run
(e.g. ``seed_demo.py --force`` wiping demo runs) violated the FK as soon as any
chat message referenced that run. A message's run link is informational — the
chat log should survive run cleanup — so the FK becomes ``ondelete=SET NULL``,
matching the convention the retired clips/derivatives tables used.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a7f3c9e21b48'
down_revision: Union[str, Sequence[str], None] = '3e8a1f5b9c02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("messages_workflow_run_id_fkey", "messages", type_="foreignkey")
    op.create_foreign_key(
        "messages_workflow_run_id_fkey",
        "messages",
        "workflow_runs",
        ["workflow_run_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("messages_workflow_run_id_fkey", "messages", type_="foreignkey")
    op.create_foreign_key(
        "messages_workflow_run_id_fkey",
        "messages",
        "workflow_runs",
        ["workflow_run_id"],
        ["id"],
    )
