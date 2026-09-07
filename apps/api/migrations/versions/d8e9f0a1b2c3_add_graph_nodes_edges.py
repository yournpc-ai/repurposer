"""add graph_nodes / graph_edges (graph-as-product, ADR-057)

Revision ID: d8e9f0a1b2c3
Revises: c9d4e7f2a815
Create Date: 2026-09-07

Graph-kernel rebuild batch K1 (docs/tasks/graph-as-product.md): the graph
graduates from a per-run compile-and-discard artifact to a PERSISTENT,
mutable product object. Two tables, owner = Pipeline (MODULE_ARCH §4):

- ``graph_nodes`` — one row per canvas node. ``kind`` = the five node types
  (asset | document | generator | processor | agent); ``state`` = the
  orthogonal lifecycle dimension (draft | queued | running | done | failed
  | skipped | stale); ``spec`` = the node's program (prompt / params /
  estimate fold / output_id back-reference / internal step keys — steps
  stay step-grained INSIDE the node: composition, never projection);
  ``layout`` = the settled canvas frame ({x, y, w, h}, assigned once at
  birth — append-only, existing nodes never move).
- ``graph_edges`` — one row per typed context/data-flow edge
  (video | audio | text | ctx). Edges are typed flows, not execution-order
  decoration; node deletion cascades its edges structurally.

The execution kernel (workflow_steps / NodeBase / queue / billing) is
untouched — zero behavior change, no consumers yet (K1 lands the seam).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd8e9f0a1b2c3'
down_revision: Union[str, Sequence[str], None] = 'c9d4e7f2a815'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'graph_nodes',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('state', sa.String(length=20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column('spec', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('layout', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_graph_nodes_project_id', 'graph_nodes', ['project_id'])

    op.create_table(
        'graph_edges',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('from_node', sa.UUID(), nullable=False),
        sa.Column('from_port', sa.String(length=40), nullable=False, server_default=sa.text("'out'")),
        sa.Column('to_node', sa.UUID(), nullable=False),
        sa.Column('to_port', sa.String(length=40), nullable=False, server_default=sa.text("'in'")),
        sa.Column('edge_type', sa.String(length=10), nullable=False, server_default=sa.text("'text'")),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['from_node'], ['graph_nodes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['to_node'], ['graph_nodes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_graph_edges_project_id', 'graph_edges', ['project_id'])
    op.create_index('ix_graph_edges_from', 'graph_edges', ['from_node'])
    op.create_index('ix_graph_edges_to', 'graph_edges', ['to_node'])


def downgrade() -> None:
    op.drop_index('ix_graph_edges_to', table_name='graph_edges')
    op.drop_index('ix_graph_edges_from', table_name='graph_edges')
    op.drop_index('ix_graph_edges_project_id', table_name='graph_edges')
    op.drop_table('graph_edges')
    op.drop_index('ix_graph_nodes_project_id', table_name='graph_nodes')
    op.drop_table('graph_nodes')
