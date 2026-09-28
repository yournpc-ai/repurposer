"""trigger once-only unique indexes (the 16-warm pile-up / double-dock race)

Revision ID: n4d7e0a3b6c9
Revises: m3c6d9f2a5b8
Create Date: 2026-09-28

Project 600d4a13 forensics (2026-09-28): three SELECT-then-insert guards
raced concurrent writers — 16 warmed material_understanding rows landed
for ONE asset digest (the API's lazy conversation-open seat fired a full
warm on every poll during the materialization window), and two
trigger_review rows docked 24s apart (the second superseded the first, so
the user's option click hit a dead question → 409). The SELECT guards
stay as cheap fast paths; these partial unique indexes are the hard
backstops that make the race loser's write structurally impossible — the
write doors treat the IntegrityError as a late-arriving dedup hit:

- outputs: one WARMED material_understanding per (project, asset_hash) —
  the worker's completion seat and the API's lazy seat can no longer both
  materialize the same digest.
- messages: one trigger_review per (conversation, trigger, ref) — the
  cross-process double-dock closes at the write door (the loser's commit
  fails into the turn's fire-and-forget silence).
- messages: one material_beat per (conversation, beat, ref) — same defect
  class, same index shape (NULL ref collapses to '' to match the SELECT
  guard's semantics exactly).

Data cleanup first (dev databases already carry the litter): warmed
understandings keep the EARLIEST row per digest (content-addressed
duplicates — any survivor is equivalent); beats keep the earliest (the
original speech); trigger_review keeps the LATEST (the live docked
question — the superseded earlier row is dead litter).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'n4d7e0a3b6c9'
down_revision: Union[str, Sequence[str], None] = 'm3c6d9f2a5b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Warmed understandings: keep the earliest per (project, digest).
    # Row-value comparison breaks exact created_at ties deterministically.
    op.execute(
        """
        DELETE FROM outputs a
        USING outputs b
        WHERE a.type = 'material_understanding'
          AND b.type = 'material_understanding'
          AND (a.source_ref->>'warmed')::boolean IS TRUE
          AND (b.source_ref->>'warmed')::boolean IS TRUE
          AND a.project_id = b.project_id
          AND a.source_ref->>'asset_hash' = b.source_ref->>'asset_hash'
          AND (a.created_at, a.id) > (b.created_at, b.id)
        """
    )
    # Trigger reviews: keep the LATEST (the live docked question).
    op.execute(
        """
        DELETE FROM messages a
        USING messages b
        WHERE a.intent->>'type' = 'trigger_review'
          AND b.intent->>'type' = 'trigger_review'
          AND a.conversation_id = b.conversation_id
          AND a.intent->>'trigger' = b.intent->>'trigger'
          AND a.intent->>'ref' = b.intent->>'ref'
          AND (a.created_at, a.id) < (b.created_at, b.id)
        """
    )
    # Material beats: keep the earliest (the original speech).
    op.execute(
        """
        DELETE FROM messages a
        USING messages b
        WHERE a.intent->>'type' = 'material_beat'
          AND b.intent->>'type' = 'material_beat'
          AND a.conversation_id = b.conversation_id
          AND a.intent->>'beat' = b.intent->>'beat'
          AND COALESCE(a.intent->>'ref', '') = COALESCE(b.intent->>'ref', '')
          AND (a.created_at, a.id) > (b.created_at, b.id)
        """
    )
    op.create_index(
        'uq_outputs_warmed_understanding',
        'outputs',
        ['project_id', sa.text("(source_ref->>'asset_hash')")],
        unique=True,
        postgresql_where=sa.text(
            "type = 'material_understanding' "
            "AND (source_ref->>'warmed')::boolean IS TRUE"
        ),
    )
    op.create_index(
        'uq_messages_trigger_review',
        'messages',
        [
            'conversation_id',
            sa.text("(intent->>'trigger')"),
            sa.text("(intent->>'ref')"),
        ],
        unique=True,
        postgresql_where=sa.text("intent->>'type' = 'trigger_review'"),
    )
    op.create_index(
        'uq_messages_material_beat',
        'messages',
        [
            'conversation_id',
            sa.text("(intent->>'beat')"),
            sa.text("COALESCE(intent->>'ref', '')"),
        ],
        unique=True,
        postgresql_where=sa.text("intent->>'type' = 'material_beat'"),
    )


def downgrade() -> None:
    op.drop_index('uq_messages_material_beat', table_name='messages')
    op.drop_index('uq_messages_trigger_review', table_name='messages')
    op.drop_index('uq_outputs_warmed_understanding', table_name='outputs')
