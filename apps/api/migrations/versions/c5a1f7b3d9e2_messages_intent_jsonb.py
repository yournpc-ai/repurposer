"""messages.intent: JSON → JSONB

Revision ID: c5a1f7b3d9e2
Revises: b4d6f8a0c2e4
Create Date: 2026-09-16

R1 B1 (remix 收口批) 实证修复: the trigger turn's dedup guard
(``trigger_turn._already_spoke``) reads ``Message.intent["trigger"].astext``
— a JSONB-only comparator in this SQLAlchemy/asyncpg stack (generic
``JSON`` subscript yields a plain BinaryExpression, ``.astext`` raises
``AttributeError``). ``messages.intent`` was the schema's one generic-JSON
outlier among JSON columns (every other — spec / payload / source_ref /
render_spec — is JSONB), so EVERY whitelist trigger turn died at its dedup
check with ``trigger_turn_failed`` and no review row ever persisted; the
trigger feature (ADR-077 判词③, T3) was structurally silent. PG casts
json → jsonb row-by-row (key order is not preserved — JSON semantics are).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c5a1f7b3d9e2'
down_revision: Union[str, Sequence[str], None] = 'b4d6f8a0c2e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'messages',
        'intent',
        existing_type=postgresql.JSON(astext_type=sa.Text()),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        postgresql_using='intent::jsonb',
    )


def downgrade() -> None:
    op.alter_column(
        'messages',
        'intent',
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=postgresql.JSON(astext_type=sa.Text()),
        postgresql_using='intent::json',
    )
