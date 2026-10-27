"""compositions / composition_versions / source_snapshots + Output lineage (ADR-145)

Revision ID: y4c7e0b2d6a1
Revises: x9e3b6d28f501
Create Date: 2026-10-27

Phase A batch 1 of the Video Project rebuild (docs/VIDEO_PROJECT.md §12).
Pure addition: three new tables (no existing row is touched) plus two
nullable lineage columns on outputs. compositions.current_version_id is a
circular FK with composition_versions — created as a plain column first,
the FK added by ALTER after both tables exist. No legacy Film data is
migrated (none will be).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'y4c7e0b2d6a1'
down_revision: Union[str, Sequence[str], None] = 'x9e3b6d28f501'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'source_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('asset_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('storage_key', sa.String(length=512), nullable=False),
        sa.Column('digest', sa.String(length=64), nullable=False),
        sa.Column('duration_ticks', sa.BigInteger(), nullable=True),
        sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('captured_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_source_snapshots_owner_id', 'source_snapshots', ['owner_id'])

    op.create_table(
        'compositions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('origin_project_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('current_version_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['origin_project_id'], ['projects.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_compositions_owner_id', 'compositions', ['owner_id'])

    op.create_table(
        'composition_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('composition_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('base_version_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('schema_version', sa.Integer(), nullable=False),
        sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('sources', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('scenes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('timeline', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('skill_provenance', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('content_digest', sa.String(length=64), nullable=False),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.Column('request_digest', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['composition_id'], ['compositions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('composition_id', 'version', name='uq_composition_versions_version'),
    )
    op.create_index('ix_composition_versions_composition_id', 'composition_versions', ['composition_id'])
    op.create_index(
        'uq_composition_versions_request_id',
        'composition_versions',
        ['request_id'],
        unique=True,
        postgresql_where=sa.text('request_id IS NOT NULL'),
    )
    # Circular FK closed post-hoc: head pointer → version row.
    op.create_foreign_key(
        'fk_compositions_current_version',
        'compositions',
        'composition_versions',
        ['current_version_id'],
        ['id'],
    )

    op.add_column('outputs', sa.Column('composition_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('outputs', sa.Column('composition_version_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_outputs_composition', 'outputs', 'compositions', ['composition_id'], ['id']
    )
    op.create_foreign_key(
        'fk_outputs_composition_version', 'outputs', 'composition_versions',
        ['composition_version_id'], ['id'],
    )
    op.create_index('ix_outputs_composition_id', 'outputs', ['composition_id'])


def downgrade() -> None:
    op.drop_index('ix_outputs_composition_id', table_name='outputs')
    op.drop_constraint('fk_outputs_composition_version', 'outputs', type_='foreignkey')
    op.drop_constraint('fk_outputs_composition', 'outputs', type_='foreignkey')
    op.drop_column('outputs', 'composition_version_id')
    op.drop_column('outputs', 'composition_id')
    op.drop_constraint('fk_compositions_current_version', 'compositions', type_='foreignkey')
    op.drop_index('uq_composition_versions_request_id', table_name='composition_versions')
    op.drop_index('ix_composition_versions_composition_id', table_name='composition_versions')
    op.drop_table('composition_versions')
    op.drop_index('ix_compositions_owner_id', table_name='compositions')
    op.drop_table('compositions')
    op.drop_index('ix_source_snapshots_owner_id', table_name='source_snapshots')
    op.drop_table('source_snapshots')
