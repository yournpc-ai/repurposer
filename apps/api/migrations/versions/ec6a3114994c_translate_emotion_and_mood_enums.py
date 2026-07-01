"""translate_emotion_and_mood_enums

Revision ID: ec6a3114994c
Revises: 90154b458822
Create Date: 2026-07-01 15:39:36.929295

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'ec6a3114994c'
down_revision: Union[str, Sequence[str], None] = '90154b458822'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Mapping from legacy Chinese enum values to English values.
EMOTIONAL_TONE_MAP = {
    '理性': 'rational',
    '激情': 'passionate',
    '温和': 'gentle',
    '犀利': 'sharp',
    '幽默': 'humorous',
}

MUSIC_MOOD_MAP = {
    '沉稳': 'calm',
    '温暖': 'calm',
    '平静': 'calm',
    '激昂': 'uplifting',
    '轻快': 'uplifting',
    '史诗': 'uplifting',
    '激励': 'uplifting',
    '商务': 'corporate',
}


def _case_sql(column_expr: str, mapping: dict[str, str]) -> str:
    """Build a CASE expression that maps known values and leaves others unchanged."""
    whens = "\n".join(f"            WHEN '{k}' THEN '{v}'" for k, v in mapping.items())
    return f"""CASE {column_expr}
{whens}
            ELSE {column_expr}
        END"""


def upgrade() -> None:
    """Translate Chinese emotional_tone and music_mood values to English."""
    # speakers.persona.emotional_tone
    op.execute(f"""
        UPDATE speakers
        SET persona = jsonb_set(
            persona::jsonb,
            '{{emotional_tone}}',
            to_jsonb({_case_sql("persona->>'emotional_tone'", EMOTIONAL_TONE_MAP)})
        )::json
        WHERE persona::jsonb ? 'emotional_tone';
    """)

    # clips.music_mood column
    op.execute(f"""
        UPDATE clips
        SET music_mood = {_case_sql('music_mood', MUSIC_MOOD_MAP)};
    """)

    # clips.script.music_mood
    op.execute(f"""
        UPDATE clips
        SET script = jsonb_set(
            script::jsonb,
            '{{music_mood}}',
            to_jsonb({_case_sql("script->>'music_mood'", MUSIC_MOOD_MAP)})
        )::json
        WHERE script::jsonb ? 'music_mood';
    """)


def downgrade() -> None:
    """Reverse the enum translation (best-effort; collapsed values map to canonical Chinese)."""
    reverse_emotion = {v: k for k, v in EMOTIONAL_TONE_MAP.items()}
    reverse_mood = {v: k for k, v in MUSIC_MOOD_MAP.items()}

    op.execute(f"""
        UPDATE speakers
        SET persona = jsonb_set(
            persona::jsonb,
            '{{emotional_tone}}',
            to_jsonb({_case_sql("persona->>'emotional_tone'", reverse_emotion)})
        )::json
        WHERE persona::jsonb ? 'emotional_tone';
    """)

    op.execute(f"""
        UPDATE clips
        SET music_mood = {_case_sql('music_mood', reverse_mood)};
    """)

    op.execute(f"""
        UPDATE clips
        SET script = jsonb_set(
            script::jsonb,
            '{{music_mood}}',
            to_jsonb({_case_sql("script->>'music_mood'", reverse_mood)})
        )::json
        WHERE script::jsonb ? 'music_mood';
    """)
