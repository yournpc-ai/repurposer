"""execution attempt counters (R1 B4a poison-pill termination)

Revision ID: a4b7c2d91e05
Revises: f3a8c1d52e97
Create Date: 2026-09-16

Crash-loop termination (North Star §8 家族: 超限 retry 必有终态). Two
NOT-NULL-DEFAULT-0 integer columns count CLAIMS of queue rows:

- ``assets.attempt`` — mirrors the ``workflow_steps.attempt`` precedent
  (bare name; Asset has no competing attempt semantics). Incremented by
  ``claim_pending_asset``; the crash-recovery reap keeps counting (that IS
  the poison pill); the manual reprocess seat resets to 0 (new budget).
- ``outputs.render_attempt`` — the render_* column family (render_status /
  render_error / render_claim_token) gets its own counter; a bare ``attempt``
  here would collide semantically with the verify verdict's
  ``quality.attempt`` key. Incremented by ``claim_pending_render``; reset at
  every INTENT-driven re-pend (morph / verify title-card / undo-redo /
  manual render / the tool re-render seats — new intent = new budget),
  never at the crash reap.

The cap (config ``asset_max_attempts`` / ``render_max_attempts``, default 3)
is enforced at claim/reap: ``attempt > cap`` flips the row to its FAILED
terminal with a localized honest line instead of re-entering the loop.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4b7c2d91e05'
down_revision: Union[str, Sequence[str], None] = 'f3a8c1d52e97'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'assets',
        sa.Column('attempt', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'outputs',
        sa.Column('render_attempt', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('outputs', 'render_attempt')
    op.drop_column('assets', 'attempt')
