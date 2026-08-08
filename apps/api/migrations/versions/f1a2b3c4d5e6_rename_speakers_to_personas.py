"""rename speakers to personas

Revision ID: f1a2b3c4d5e6
Revises: e9f4c2a81d63
Create Date: 2026-08-09

Persona identity module, cut 1 (ADR-037 / NAMING N-27, brief
docs/tasks/persona-identity.md §3): the identity module is renamed
Speaker → Persona across the stack. Pure mechanical rename — no column
added, no behavior change (new columns / brand absorption are cut 2).

- ``speakers`` → ``personas`` (table rename; rows, PK and indexes carry over)
- ``projects.speaker_id`` → ``persona_id`` and ``assets.speaker_id`` →
  ``persona_id``: PG RENAME COLUMN carries the FK constraints with it, and
  the asset check constraints (``ck_asset_owner_set`` /
  ``ck_asset_owner_single``) keep their names while their re-rendered SQL
  text follows the new column name automatically.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'e9f4c2a81d63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table('speakers', 'personas')
    op.alter_column('projects', 'speaker_id', new_column_name='persona_id')
    op.alter_column('assets', 'speaker_id', new_column_name='persona_id')


def downgrade() -> None:
    op.alter_column('assets', 'persona_id', new_column_name='speaker_id')
    op.alter_column('projects', 'persona_id', new_column_name='speaker_id')
    op.rename_table('personas', 'speakers')
