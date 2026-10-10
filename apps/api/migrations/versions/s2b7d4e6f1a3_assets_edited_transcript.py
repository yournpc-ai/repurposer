"""assets.edited_transcript + transcript 节点退役清库 (ADR-113)

Revision ID: s2b7d4e6f1a3
Revises: r8f1a3c5d7e9
Create Date: 2026-10-09

ADR-113 §1 (transcript = 视频的内容层，不是节点): the transcript folds into
the asset row — ONE storage seat. The card's edit overlay moves off the
graph spec (``spec.edited_text``, Workspace 合同 v4.2 C4 双层) onto the
asset itself as ``assets.edited_transcript``; the C4 invariants are
unchanged (the overlay never reverse-computes a timecode — the source
layer and ``meta.words`` stay untouched).

Same-migration housekeeping (task_book 先例, l2b5c8e1f4a7):

1. Backfill: each legacy transcript node's ``spec.edited_text`` (the
   current overlay — the top of ``text_edits``) lands on its asset row,
   joined by ``spec.asset_id``.
2. Hard-delete: every ``document`` node with ``spec.role = 'transcript'``
   plus every edge touching one. The /graph read face filters these rows
   from the same batch (projects.py, task_book 先例同构), so the canvas is
   unchanged; the card's content (text/cues) is a read-time derivation of
   the asset row (``display_cues`` one law), so nothing user-owned is lost.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 's2b7d4e6f1a3'
down_revision: Union[str, Sequence[str], None] = 'r8f1a3c5d7e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'assets',
        sa.Column('edited_transcript', sa.Text(), nullable=True),
    )
    # Overlay 搬家: edited_text IS the current overlay (the top of
    # text_edits) — one UPDATE per asset, no version replay needed.
    op.execute(
        sa.text(
            """
            UPDATE assets a
            SET edited_transcript = n.spec->>'edited_text'
            FROM graph_nodes n
            WHERE n.type = 'document'
              AND n.spec->>'role' = 'transcript'
              AND n.spec ? 'edited_text'
              AND (n.spec->>'asset_id')::uuid = a.id
            """
        )
    )
    # Edges first (the door's own order — children before parents).
    op.execute(
        sa.text(
            """
            DELETE FROM graph_edges
            WHERE from_node IN (
                SELECT id FROM graph_nodes
                WHERE type = 'document' AND spec->>'role' = 'transcript'
            )
            OR to_node IN (
                SELECT id FROM graph_nodes
                WHERE type = 'document' AND spec->>'role' = 'transcript'
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM graph_nodes
            WHERE type = 'document' AND spec->>'role' = 'transcript'
            """
        )
    )


def downgrade() -> None:
    # Hard-deleted transcript nodes are not restorable (their content face
    # is derived from the asset row, never stored); the overlay column is
    # droppable.
    op.drop_column('assets', 'edited_transcript')
