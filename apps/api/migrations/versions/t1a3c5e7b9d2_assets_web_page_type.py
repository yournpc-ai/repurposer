"""assettype enum: add WEB_PAGE (网页采集资产化, MG film 批 D1)

Revision ID: t1a3c5e7b9d2
Revises: s2b7d4e6f1a3
Create Date: 2026-10-13

A user-named URL becomes a first-class asset (copy manifest + screenshot);
the row's ``type`` needs the new enum value. SQLAlchemy's ``Enum(AssetType)``
stores member NAMES, so the DB literal is ``WEB_PAGE``.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 't1a3c5e7b9d2'
down_revision: Union[str, Sequence[str], None] = 's2b7d4e6f1a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL ≥ 12: ADD VALUE inside a transaction is legal as long as
    # the new value is not used in the same transaction (it isn't — row
    # writes come from the app after deploy).
    op.execute("ALTER TYPE assettype ADD VALUE IF NOT EXISTS 'WEB_PAGE'")


def downgrade() -> None:
    # PostgreSQL cannot drop a single enum value (the derivativetype
    # rebuild in 1569e085b02b was a rename dance, not a value drop). A
    # downgrade that left the value in place is harmless: no rows
    # reference it after the app stops writing them. No-op by design.
    pass
