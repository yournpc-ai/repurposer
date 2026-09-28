"""layout islands — graph_islands + graph_nodes.island_id/island_seq (v4.2 C6)

Revision ID: m3c6d9f2a5b8
Revises: l2b5c8e1f4a7
Create Date: 2026-09-26

Workspace 空间模型合同 v4.2 (2026-09-26 封板) C6 — Group Layout Island:
each sibling group gets an exclusive layout region whose width is reserved
by the group's DESIGN capacity (the growth corridor), frozen at the group's
birth — the island's right edge never crosses its frozen edge, so overlap
is structurally impossible. This migration creates the island registry
(``graph_islands``) and the node's membership columns (``island_id`` /
``island_seq``).

No backfill: pre-C6 rows stay island-less (NULL membership) and keep the
plain depth-column stacking law — islands bind new births only.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'm3c6d9f2a5b8'
down_revision: Union[str, Sequence[str], None] = 'l2b5c8e1f4a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'graph_islands',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('depth', sa.Integer(), nullable=False),
        sa.Column('parent_ids', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('origin_x', sa.Integer(), nullable=False),
        sa.Column('origin_y', sa.Integer(), nullable=False),
        sa.Column('row_h', sa.Integer(), nullable=False),
        sa.Column('cols', sa.Integer(), nullable=False),
        sa.Column('cap', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_graph_islands_project_id', 'graph_islands', ['project_id'])
    op.add_column('graph_nodes', sa.Column('island_id', sa.UUID(), nullable=True))
    op.add_column('graph_nodes', sa.Column('island_seq', sa.Integer(), nullable=True))
    op.create_index('ix_graph_nodes_island_id', 'graph_nodes', ['island_id'])
    op.create_foreign_key(
        'fk_graph_nodes_island_id',
        'graph_nodes',
        'graph_islands',
        ['island_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_graph_nodes_island_id', 'graph_nodes', type_='foreignkey')
    op.drop_index('ix_graph_nodes_island_id', table_name='graph_nodes')
    op.drop_column('graph_nodes', 'island_seq')
    op.drop_column('graph_nodes', 'island_id')
    op.drop_index('ix_graph_islands_project_id', table_name='graph_islands')
    op.drop_table('graph_islands')
