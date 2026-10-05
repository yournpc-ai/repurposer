"""assets.processing_requested_at — 休眠素材 (ADR-102 §1)

Revision ID: q3d9e5f7a2b4
Revises: p7c2d4e6f8a1
Create Date: 2026-10-05

NULL = dormant: uploaded but nobody has asked for the content. The
worker's claim loop requires non-NULL, so a dormant asset is never
processed — discarded/browsed/ignored materials cost zero. The ONLY two
request seats stamp it: get_understanding's read attempt (chat) and the
run birthplace (production prerequisite).

Backfill: rows already PENDING/PROCESSING were uploaded under the old
world's upload-time-processing semantics — their processing WAS
requested, so they inherit the stamp (created_at) and keep flowing.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'q3d9e5f7a2b4'
down_revision: Union[str, Sequence[str], None] = 'p7c2d4e6f8a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'assets',
        sa.Column(
            'processing_requested_at',
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.execute(
        "UPDATE assets SET processing_requested_at = created_at "
        "WHERE processing_status IN ('PENDING', 'PROCESSING')"
    )


def downgrade() -> None:
    op.drop_column('assets', 'processing_requested_at')
