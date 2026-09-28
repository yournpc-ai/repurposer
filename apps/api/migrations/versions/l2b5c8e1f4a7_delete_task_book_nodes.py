"""hard-delete legacy task_book graph rows (de-stamp cleanup, Workspace 合同 v4.2 C1-b)

Revision ID: l2b5c8e1f4a7
Revises: k1a4b7c3d4e5
Create Date: 2026-09-26

Workspace 空间模型合同 v4.2 (2026-09-26 封板) C1-b 伴侣文档资格上限: the
task-book document was an implementation-needs seat, never an eligible
Graph member (确认拍唯一座位 = dock pill, ADR-070; Plan 永不成节点).
Production stopped at the stamp (graph_fill de-stamp, same batch); this
migration hard-deletes the legacy stock — every ``document`` node with
``spec.role = 'task_book'`` plus every edge touching one.

Safety basis: the /graph read face has filtered these rows (and their
edges) since B1-lite, so the canvas is unchanged; runtime reads are
pointer-tolerant (``sync_graph_node_for_step`` no-ops when a step's
``graph_node_id`` dangles, and de-stamped fills never write that pointer
for prelude steps anymore). No user-owned content lives on these rows —
the plan's prose face is the question row (messages), never the node.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'l2b5c8e1f4a7'
down_revision: Union[str, Sequence[str], None] = 'k1a4b7c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Edges first (the door's own order — children before parents).
    op.execute(
        sa.text(
            """
            DELETE FROM graph_edges
            WHERE from_node IN (
                SELECT id FROM graph_nodes
                WHERE type = 'document' AND spec->>'role' = 'task_book'
            )
            OR to_node IN (
                SELECT id FROM graph_nodes
                WHERE type = 'document' AND spec->>'role' = 'task_book'
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM graph_nodes
            WHERE type = 'document' AND spec->>'role' = 'task_book'
            """
        )
    )


def downgrade() -> None:
    # Hard-deleted rows are not restorable (their prose face lives on the
    # messages table, never on the node) — the de-stamp makes them
    # unreproducible by construction.
    pass

