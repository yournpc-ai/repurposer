"""asset processing status

Revision ID: e8347ed87fcf
Revises: af72bd2ce608
Create Date: 2026-06-26 20:09:50.465723

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e8347ed87fcf'
down_revision: str | Sequence[str] | None = 'af72bd2ce608'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Enum stores member NAMES (uppercase), consistent with the other StrEnum
# columns in the initial migration.
asset_status = postgresql.ENUM(
    'PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', name='assetstatus'
)


def upgrade() -> None:
    """Upgrade schema."""
    asset_status.create(op.get_bind(), checkfirst=True)
    # Backfill existing rows to COMPLETED via a temporary server_default — they
    # were already processed under the old synchronous upload model — then
    # switch the go-forward default to PENDING for new uploads.
    op.add_column(
        'assets',
        sa.Column(
            'processing_status',
            sa.Enum(
                'PENDING', 'PROCESSING', 'COMPLETED', 'FAILED',
                name='assetstatus', create_type=False,
            ),
            nullable=False,
            server_default='COMPLETED',
        ),
    )
    op.alter_column('assets', 'processing_status', server_default='PENDING')
    op.add_column('assets', sa.Column('processing_error', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('assets', 'processing_error')
    op.drop_column('assets', 'processing_status')
    asset_status.drop(op.get_bind(), checkfirst=True)
