"""Music-library lookup shared with ordinary Composition audio preparation."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Music
from app.pipeline.music import get_music, get_music_by_mood

PERSONA_CRAFT_KEYS = ("aspect", "fillMode", "captionEnabled")

_LIBRARY_MOODS = {
    "mixkit-tech-house", "mixkit-cat-walk", "mixkit-g-eazy-nba-type",
    "mixkit-house-vibez", "mixkit-tonight-hiphop",
}
_MOOD_SYNONYMS = {
    "tech house": "mixkit-tech-house", "tech-house": "mixkit-tech-house",
    "electronic": "mixkit-tech-house", "energetic": "mixkit-tech-house",
    "corporate": "mixkit-tech-house", "professional": "mixkit-tech-house",
    "business": "mixkit-tech-house", "cat walk": "mixkit-cat-walk",
    "g eazy nba type": "mixkit-g-eazy-nba-type", "house": "mixkit-house-vibez",
    "house vibez": "mixkit-house-vibez", "hip hop": "mixkit-tonight-hiphop",
    "hip-hop": "mixkit-tonight-hiphop", "tonight": "mixkit-tonight-hiphop",
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
