"""claim fencing tokens (ADR-079, R1 B2 执行围栏)

Revision ID: f3a8c1d52e97
Revises: c5a1f7b3d9e2
Create Date: 2026-09-16

Execution writes must be fenced by execution identity (North Star §8.3).
Two nullable UUID columns:

- ``workflow_steps.claim_token`` — minted by ``claim_ready_node`` at claim,
  NULLed on every authority-losing path (reap / retry re-pend / QualityBounce
  reset / runtime-fanout re-pend / Suspend park / resume / cascade-skip).
  ``execute_step``'s terminal tails write
  ``WHERE id=:id AND claim_token=:mine`` and check rowcount — a zombie
  executor (reaped, then re-claimed by a live worker) matches 0 rows, rolls
  back, and never captures / syncs / cascades.
- ``outputs.render_claim_token`` — same fence for the render chain:
  minted by ``claim_pending_render``, NULLed at every re-pend (the 10 morph /
  verify / undo-redo / manual re-pend seats + the startup reap). The three
  render terminal writes switch their predicate from
  ``render_status==RENDERING`` (a state, not an identity — the morph-window
  race proof, POST_T5_DELTA_AUDIT §3.3) to the token.

Deployment note (contract T8): rows already in flight when this lands carry
token=NULL — the new entry defenses (``execute_step`` / ``render_output``)
refuse them with a log line; the deploy restarts the worker, killing the
in-flight asyncio executions that owned them.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f3a8c1d52e97'
down_revision: Union[str, Sequence[str], None] = 'c5a1f7b3d9e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'workflow_steps',
        sa.Column('claim_token', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        'outputs',
        sa.Column('render_claim_token', postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('outputs', 'render_claim_token')
    op.drop_column('workflow_steps', 'claim_token')
