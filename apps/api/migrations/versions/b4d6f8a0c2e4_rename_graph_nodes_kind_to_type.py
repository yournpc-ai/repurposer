"""rename graph_nodes.kind to type

Revision ID: b4d6f8a0c2e4
Revises: e7a9c1d35b28
Create Date: 2026-09-14

词表 v3 (ADR-076, 画布三族批 C5b): the graph node's family word renames
``kind`` → ``type`` — the double meaning (``step.kind`` = the tool name,
N-35, untouched vs the graph node's family word) dissolves. ``type``
carries the medium five values (text/table/image/video/audio) plus the
two server-internal birth words (asset/document). Pure column rename —
values were stamped into place by C2b (new births) and are read-mapped by
C4's _read_face (legacy rows), so there is NO value migration. PG RENAME
COLUMN carries rows, the NOT NULL constraint, and the default with it.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b4d6f8a0c2e4'
down_revision: Union[str, Sequence[str], None] = 'e7a9c1d35b28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('graph_nodes', 'kind', new_column_name='type')


def downgrade() -> None:
    op.alter_column('graph_nodes', 'type', new_column_name='kind')
