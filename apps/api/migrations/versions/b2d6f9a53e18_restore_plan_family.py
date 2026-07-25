"""restore plan family: run_nodes → plan_nodes, content_brief → content_plan

NAMING 判例 N-11（翻案 N-09/N-10）：plan 词汇恢复——
plan 必须带限定词（RunPlan/ContentPlan），裸用才违规。
- run_nodes 表 → plan_nodes（含索引名）
- outputs.run_node_id → plan_node_id
- plan_nodes.kind 'director_brief' → 'director_plan'
- outputs.type 'content_brief' → 'content_plan'

Revision ID: b2d6f9a53e18
Revises: a1c5e8f42d07
Create Date: 2026-07-25
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b2d6f9a53e18"
down_revision: Union[str, Sequence[str], None] = "a1c5e8f42d07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("run_nodes", "plan_nodes")
    op.execute("ALTER INDEX ix_run_nodes_run_status RENAME TO ix_plan_nodes_run_status")
    op.execute("ALTER INDEX ix_run_nodes_kind_status RENAME TO ix_plan_nodes_kind_status")
    op.alter_column("outputs", "run_node_id", new_column_name="plan_node_id")
    op.execute("UPDATE plan_nodes SET kind = 'director_plan' WHERE kind = 'director_brief'")
    op.execute("UPDATE outputs SET type = 'content_plan' WHERE type = 'content_brief'")


def downgrade() -> None:
    op.execute("UPDATE outputs SET type = 'content_brief' WHERE type = 'content_plan'")
    op.execute("UPDATE plan_nodes SET kind = 'director_brief' WHERE kind = 'director_plan'")
    op.alter_column("outputs", "plan_node_id", new_column_name="run_node_id")
    op.execute("ALTER INDEX ix_plan_nodes_run_status RENAME TO ix_run_nodes_run_status")
    op.execute("ALTER INDEX ix_plan_nodes_kind_status RENAME TO ix_run_nodes_kind_status")
    op.rename_table("plan_nodes", "run_nodes")
