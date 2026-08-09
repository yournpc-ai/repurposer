"""persona identity: new blocks + brand absorption

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-08-10

Persona identity module, cut 2 (ADR-038 / NAMING N-28, brief
docs/tasks/persona-identity.md §2/§6): the persona absorbs the brand skin —
``brand_templates`` retires and its config splits three ways.

- ``personas`` gains: ``brand`` JSONB (skin block; NULL = system default
  skin), ``learned_from`` JSONB (provenance, written by later cuts),
  ``calibrated_at`` / ``auto_created_at`` (nullable timestamps — the system
  bootstrap marker replaces any is_default boolean).
- The old ``voice`` text column (writing-style description) is appended to
  ``guidelines``, then dropped and re-added as ``voice`` JSONB — the voice
  block (``{"kind":"cloned"|"stock", ...}``); ``voice`` returns to its single
  audio meaning.
- ``brand_templates`` data split: skin keys (caption/title/intro/outro/
  keyword highlighter/logo) move to ``persona.brand``; craft/format keys
  (aspect/fillMode/removeFiller/captionEnabled/music defaults) do NOT
  migrate — recipe/task-book defaults absorb them. A template whose skin
  equals the system default skin writes nothing (NULL already falls back to
  the same look), which is how the seeded "Default" template is retired.
  A user with several personas gets the skin on every persona — the single
  per-user template used to serve them all.
- ``projects.brand_template_id`` needs no DDL: it never existed as a column
  (the brand choice only rode ``pending_intent`` / ``run.context`` JSON —
  read-tolerated, never migrated, per the brief).
"""
import json
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Skin keys = the persona.brand block's vocabulary (brief §2). Craft/format
# keys are deliberately absent — their home is the recipe registry / task
# book. ``captionEnabled`` is a craft toggle, so caption keys are enumerated
# exactly (a "caption" prefix would swallow it).
_SKIN_EXACT = {
    "captionFont",
    "captionSize",
    "captionColor",
    "captionPosition",
    "captionStylePreset",
    "titleEnabled",
    "titlePosition",
    "titleSize",
    "keywordHighlighter",
    "logo",
}
_SKIN_PREFIXES = ("intro", "outro")

# The system default skin (mirrors app.memory.brand.DEFAULT_BRAND_CONFIG at
# introduction time — inlined so the migration stays self-contained). A
# template whose skin subset matches these values migrates to NULL instead.
_DEFAULT_SKIN = {
    "captionFont": "lilita",
    "captionSize": 44,
    "captionColor": "#facc15",
    "captionPosition": {"x": 0.5, "y": 0.84},
    "captionStylePreset": "clean-bottom",
    "titleEnabled": True,
    "titlePosition": {"x": 0.5, "y": 0.12},
    "introEnabled": False,
    "introKind": "image",
    "introText": "",
    "introMediaUrl": None,
    "introDurationSeconds": 2.0,
    "outroEnabled": False,
    "outroKind": "image",
    "outroText": "",
    "outroMediaUrl": None,
    "outroDurationSeconds": 2.0,
    "keywordHighlighter": True,
}


def _skin_of(config: dict[str, Any]) -> dict[str, Any]:
    return {
        k: v
        for k, v in (config or {}).items()
        if k in _SKIN_EXACT or k.startswith(_SKIN_PREFIXES)
    }


def upgrade() -> None:
    # 1. New persona blocks (existing rows backfill NULL).
    op.add_column('personas', sa.Column('brand', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('personas', sa.Column('learned_from', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('personas', sa.Column('calibrated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('personas', sa.Column('auto_created_at', sa.DateTime(timezone=True), nullable=True))

    # 2. Old voice text folds into guidelines, then the column is recreated
    # as the JSONB voice block.
    op.execute(
        """
        UPDATE personas
        SET guidelines = CASE
            WHEN guidelines IS NULL OR btrim(guidelines) = '' THEN voice
            ELSE guidelines || E'\\n\\n' || voice
        END
        WHERE voice IS NOT NULL AND btrim(voice) <> ''
        """
    )
    op.drop_column('personas', 'voice')
    op.add_column('personas', sa.Column('voice', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    # 3. Skin keys of each user's latest brand template -> that user's
    # personas' brand block (NULL-brand rows only).
    conn = op.get_bind()
    templates = conn.execute(
        sa.text(
            """
            SELECT DISTINCT ON (user_id) user_id, config
            FROM brand_templates
            ORDER BY user_id, created_at DESC
            """
        )
    ).all()
    for user_id, config in templates:
        skin = _skin_of(config)
        if skin == _skin_of(_DEFAULT_SKIN):
            continue
        conn.execute(
            sa.text(
                "UPDATE personas SET brand = CAST(:skin AS JSONB) "
                "WHERE user_id = :uid AND brand IS NULL"
            ).bindparams(skin=json.dumps(skin), uid=user_id)
        )
    op.drop_table('brand_templates')


def downgrade() -> None:
    op.create_table(
        'brand_templates',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('config', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    # The JSONB voice block drops back to the plain text column; cloned/stock
    # block contents do not survive the downgrade.
    op.drop_column('personas', 'voice')
    op.add_column('personas', sa.Column('voice', sa.String(length=255), nullable=True))
    op.drop_column('personas', 'auto_created_at')
    op.drop_column('personas', 'calibrated_at')
    op.drop_column('personas', 'learned_from')
    op.drop_column('personas', 'brand')
