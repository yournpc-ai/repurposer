"""outputs.render_barrier — the compile-static writer barrier for renders (ADR-096 §1)

Revision ID: o2b8f4a6c1e9
Revises: n4d7e0a3b6c9
Create Date: 2026-10-01

The render-ownership law: the compiler statically names every output's
writers of its render_spec (seq-ordered, last = the render owner); the
render claim gate fires only when every listed writer step is done, so a
render always reads the full final spec. The barrier lives on the output
row as the writer-step id list because the render claim reads the output
row — rule 2 (要查的字段升级为列). NULL = unbarriered (run-less re-pends:
undo/redo, manual render, pre-migration rows).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'o2b8f4a6c1e9'
down_revision: Union[str, Sequence[str], None] = 'n4d7e0a3b6c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'outputs',
        sa.Column('render_barrier', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('outputs', 'render_barrier')
