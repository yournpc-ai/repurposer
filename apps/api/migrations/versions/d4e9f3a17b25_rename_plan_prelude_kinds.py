"""rename plan-prelude step kinds (director_* → understand/plan)

Revision ID: d4e9f3a17b25
Revises: c3a9e71f52d0
Create Date: 2026-09-03

ADR-052 判词 3 / NAMING N-44（plan 一词归一主；「导演」概念退役——它是动词
不是角色）：the two plan-prelude node kinds drop the director prefix.
Data migration only; no schema change (String kind 列，b8e4f2a91c63 先例).

    director_understand → understand
    director_plan       → plan
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd4e9f3a17b25'
down_revision: Union[str, Sequence[str], None] = 'c3a9e71f52d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RENAMES = {
    "director_understand": "understand",
    "director_plan": "plan",
}


def _rename(mapping: dict[str, str]) -> None:
    cases = "\n".join(
        f"            WHEN '{old}' THEN '{new}'" for old, new in mapping.items()
    )
    kinds = ", ".join(f"'{old}'" for old in mapping)
    op.execute(
        f"""
        UPDATE workflow_steps
        SET kind = CASE kind
{cases}
            ELSE kind
        END
        WHERE kind IN ({kinds})
        """
    )


def upgrade() -> None:
    _rename(_RENAMES)


def downgrade() -> None:
    _rename({v: k for k, v in _RENAMES.items()})
