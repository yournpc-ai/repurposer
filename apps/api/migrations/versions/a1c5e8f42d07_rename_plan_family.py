"""rename plan family: plan_nodes → run_nodes, content_plan → content_brief

NAMING 判例 N-09/N-10：plan 词汇整体退休。
- plan_nodes 表 → run_nodes（含索引名）
- outputs.plan_node_id → run_node_id
- plan_nodes.kind 'director_plan' → 'director_brief'
- outputs.type 'content_plan' → 'content_brief'

Revision ID: a1c5e8f42d07
Revises: b3d7f1a94e52
Create Date: 2026-07-25
"""

from typing import Sequence, Union

from alembic import op

revision: str = "a1c5e8f42d07"
down_revision: Union[str, Sequence[str], None] = "b3d7f1a94e52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("plan_nodes", "run_nodes")
    op.execute("ALTER INDEX ix_plan_nodes_run_status RENAME TO ix_run_nodes_run_status")
    op.execute("ALTER INDEX ix_plan_nodes_kind_status RENAME TO ix_run_nodes_kind_status")
    op.alter_column("outputs", "plan_node_id", new_column_name="run_node_id")
    op.execute("UPDATE run_nodes SET kind = 'director_brief' WHERE kind = 'director_plan'")
    op.execute("UPDATE outputs SET type = 'content_brief' WHERE type = 'content_plan'")


def downgrade() -> None:
    op.execute("UPDATE outputs SET type = 'content_plan' WHERE type = 'content_brief'")
    op.execute("UPDATE run_nodes SET kind = 'director_plan' WHERE kind = 'director_brief'")
    op.alter_column("outputs", "run_node_id", new_column_name="plan_node_id")
    op.execute("ALTER INDEX ix_run_nodes_run_status RENAME TO ix_plan_nodes_run_status")
    op.execute("ALTER INDEX ix_run_nodes_kind_status RENAME TO ix_plan_nodes_kind_status")
    op.rename_table("run_nodes", "plan_nodes")
