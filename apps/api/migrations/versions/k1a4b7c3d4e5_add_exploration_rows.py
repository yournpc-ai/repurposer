"""add exploration_rows (exploration family re-home, Workspace 合同 v4.2 C1)

Revision ID: k1a4b7c3d4e5
Revises: j9f3a6b24c38
Create Date: 2026-09-26

Workspace 空间模型合同 v4.2 (2026-09-26 封板) C1 图节点资格: Candidate /
Selection / Preview NEVER enter the Graph — the exploration family
(Candidate Set / Select / Content Plan, ADR-088) is re-homed out of
``graph_nodes`` into its own table. Production of graph-resident
exploration nodes stops at the door (``exploration_store`` writes here
now); the family's chat-surface data chain (tool observations / dock
payloads, all message-borne) is unchanged.

- ``exploration_rows`` mirrors the row facts the door and the compiler
  read: id / project_id / journey_id / state / spec + stamps. No ``type``
  column (the family IS the table) and no ``layout`` (no canvas seat —
  C1/C6). ``spec.exploration_kind`` keeps distinguishing candidate_set /
  select / content_plan, exactly as the legacy graph rows did.
- Legacy ``graph_nodes`` rows with ``type="exploration"`` are NOT
  migrated: the /graph read face filters them out (their canvas cards are
  deleted by the same contract), and the graph_store reverse guard keeps
  rejecting them from wiring ops. Project cascade still removes both
  tables' rows.

The execution kernel and the execution write door are untouched —
I-EXPLORE-01 holds by construction now (exploration artifacts cannot be
wiring targets: they are not graph rows at all).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'k1a4b7c3d4e5'
down_revision: Union[str, Sequence[str], None] = 'j9f3a6b24c38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'exploration_rows',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('journey_id', sa.UUID(), nullable=True),
        sa.Column('state', sa.String(length=20), nullable=False),
        sa.Column('spec', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['journey_id'], ['journeys.id'], ondelete='SET NULL'),
    )
    op.create_index('ix_exploration_rows_project_id', 'exploration_rows', ['project_id'])
    op.create_index('ix_exploration_rows_journey_id', 'exploration_rows', ['journey_id'])


def downgrade() -> None:
    op.drop_index('ix_exploration_rows_journey_id', table_name='exploration_rows')
    op.drop_index('ix_exploration_rows_project_id', table_name='exploration_rows')
    op.drop_table('exploration_rows')
