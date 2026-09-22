"""add journeys / graph_nodes.journey_id (exploration artifacts, ADR-088)

Revision ID: b2e8f1a94c07
Revises: h7d1e4a93b26
Create Date: 2026-09-22

Agent Working Loop 迭代一（docs/tasks/agent-working-loop-iter-1.md）:
exploration artifacts (Candidate Set / Select / Content Plan) take up
residence in the persistent graph (ADR-088 §4, prototype fourth value
``exploration``, NAMING N-55), and every exploration artifact carries a
``journey_id`` — the attribution property of one User Goal's working loop
(R24: an attribution, NEVER a graph edge).

- ``journeys`` — one row per User Goal's working loop: the honest source
  of ``journey_id`` (goal text + stamps; owner = Pipeline, same as the
  graph kernel, MODULE_ARCH §4). No status column in iter-1: the journey
  row is an attribution anchor, not a state machine — artifact states live
  on the artifacts themselves (ADR-088 §3).
- ``graph_nodes.journey_id`` — nullable FK -> journeys.id, indexed (the
  read law's history-by-journey queries). NULL on every execution-family
  node; only exploration artifacts carry it. ``ondelete=SET NULL``: there
  is no journey-deletion path anywhere in the product; if one ever
  appears, the artifact survives as a project object with its attribution
  honestly gone (project cascade still removes both).

The execution kernel (workflow_steps / NodeBase / queue / billing) and the
execution write door (apply_wiring_ops) are untouched — exploration
artifacts never participate in execution topology (I-EXPLORE-01).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2e8f1a94c07'
down_revision: Union[str, Sequence[str], None] = 'h7d1e4a93b26'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'journeys',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('goal_text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_journeys_project_id', 'journeys', ['project_id'])

    op.add_column(
        'graph_nodes',
        sa.Column('journey_id', sa.UUID(), nullable=True),
    )
    op.create_index('ix_graph_nodes_journey_id', 'graph_nodes', ['journey_id'])
    op.create_foreign_key(
        'fk_graph_nodes_journey_id',
        'graph_nodes',
        'journeys',
        ['journey_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_graph_nodes_journey_id', 'graph_nodes', type_='foreignkey')
    op.drop_index('ix_graph_nodes_journey_id', table_name='graph_nodes')
    op.drop_column('graph_nodes', 'journey_id')
    op.drop_index('ix_journeys_project_id', table_name='journeys')
    op.drop_table('journeys')
