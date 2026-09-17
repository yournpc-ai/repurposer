"""messages.turn_state — the minimal turn identity (交互完整性批 A, 2026-09-17)

Revision ID: g5c9e3a72f14
Revises: a4b7c2d91e05
Create Date: 2026-09-17

The 2026-09-16 incident: a chat turn died mid-flight (abort / 502 / restart —
never determined) and the commit-once discipline rolled the WHOLE turn back,
including the user's own message — the world kept zero proof the request was
ever received, while a racing trigger review spoke blind into the empty
conversation. The fix's persistence half: the user row commits UPFRONT in
prepare_chat_turn with turn_state='in_flight', so input durability never
binds to turn success again; the turn's final commit stamps 'settled'; the
failure/cancel paths stamp 'failed' best-effort. The trigger admission gate
(交互完整性批 B) reads in_flight rows to never overtake a live user turn.

Nullable, no backfill: legacy rows read as non-turn rows (NULL), which is
exactly the gate's "not in flight" semantics. A crashed turn's stranded
in_flight row ages out via the stale bound in trigger_turn — no data
migration needed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'g5c9e3a72f14'
down_revision: Union[str, Sequence[str], None] = 'a4b7c2d91e05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'messages',
        sa.Column('turn_state', sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('messages', 'turn_state')
