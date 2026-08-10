"""rename workflow step kinds to skill names

Revision ID: b8e4f2a91c63
Revises: a7b8c9d0e1f2
Create Date: 2026-08-11

ADR-039 P2 / NAMING N-35 (kind 同名): a skill's node kind IS the skill name —
one name per thing, killing the SkillEntry.node_kind mapping field. Data
migration only; no schema change. Internal crew kinds (preprocess /
persona_bootstrap / director_understand / director_plan / checkpoint /
render) and already-clean kinds (translate_clip / remove_filler / add_music /
align_stills) are untouched.

    dub            → dub_clip
    clips_pipeline → select_clips
    post_gen       → write_post
    quotes_gen     → write_quotes
    carousel_gen   → write_carousel
    article_gen    → write_article
    script         → revise_script
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b8e4f2a91c63'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RENAMES = {
    "dub": "dub_clip",
    "clips_pipeline": "select_clips",
    "post_gen": "write_post",
    "quotes_gen": "write_quotes",
    "carousel_gen": "write_carousel",
    "article_gen": "write_article",
    "script": "revise_script",
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
        END,
        updated_at = now()
        WHERE kind IN ({kinds})
        """
    )


def upgrade() -> None:
    _rename(_RENAMES)


def downgrade() -> None:
    _rename({new: old for old, new in _RENAMES.items()})
