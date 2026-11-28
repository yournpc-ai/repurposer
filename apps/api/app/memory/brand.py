"""Music-library lookup shared with ordinary Composition audio preparation."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Music
from app.pipeline.music import CURATED_MUSIC_CATALOG, get_music, get_music_by_mood

PERSONA_CRAFT_KEYS = ("aspect", "fillMode", "captionEnabled")

_LIBRARY_MOODS = {entry["mood"] for entry in CURATED_MUSIC_CATALOG}
_MOOD_SYNONYMS = {
    "city-pop": "vlog-nagoya-citypop",
    "city pop": "vlog-nagoya-citypop",
    "travel": "vlog-nagoya-citypop",
    "vlog": "vlog-nagoya-citypop",
    "lofi": "vlog-cafe-acoustic",
    "lo-fi": "vlog-cafe-acoustic",
    "acoustic": "vlog-cafe-acoustic",
    "cafe": "vlog-cafe-acoustic",
    "ambient": "vlog-night-rail",
    "night": "vlog-night-rail",
    "cinematic": "vlog-golden-cinema",
    "funk": "craft-swiss-funk",
    "swiss": "craft-swiss-funk",
    "electronic": "craft-tech-arpeggio",
    "tech house": "craft-tech-arpeggio",
    "tech-house": "craft-tech-arpeggio",
    "showreel": "hook-showreel-15s",
    "dark": "craft-dark-impact",
    "energetic": "promo-keynote-percussion",
    "corporate": "promo-keynote-percussion",
    "professional": "promo-keynote-percussion",
    "business": "promo-keynote-percussion",
    "saas": "promo-keynote-percussion",
    "manifesto": "promo-keynote-percussion",
    "editorial": "explainer-vox-pluck",
    "calm": "explainer-minimal-rhodes",
}


def normalize_mood(mood: str | None) -> str | None:
    if not isinstance(mood, str):
        return None
    key = mood.strip().lower()
    if key in _LIBRARY_MOODS:
        return key
    return _MOOD_SYNONYMS.get(key) or _MOOD_SYNONYMS.get(mood.strip())


async def resolve_music_ref(db: AsyncSession, ref: Any) -> Music | None:
    """Resolve a library UUID or one of the catalog's existing mood names."""
    if not isinstance(ref, str) or not ref.strip():
        return None
    ref = ref.strip()
    if ref.lower() == "none":
        return None
    try:
        return await get_music(db, UUID(ref))
    except ValueError:
        pass
    key = normalize_mood(ref)
    return await get_music_by_mood(db, key) if key is not None else None
