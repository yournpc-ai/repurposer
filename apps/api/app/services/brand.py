"""Resolve a BrandTemplate's free-form config into a typed ClipBrand block.

The brand-template UI stores its settings as a camelCase ``config`` dict on
``BrandTemplate`` (see apps/web/src/routes/brand-template.tsx ``Template``). At
generation time we map the subset the renderer supports into ``ClipBrand`` and
bake it into the clip-spec, so the render service / preview never touch the DB.
"""

from typing import Any, Literal

from sqlalchemy import func, select

from app.models.database import AsyncSessionLocal
from app.models.schemas import ClipBrand, ClipMusic
from app.models.tables import BrandTemplate
from app.services.storage import music_url

# Seeded when the DB has no brand templates so generation/preview always have a
# usable default. Mirrors the brand-template UI's PRESET_1.
DEFAULT_BRAND_CONFIG: dict[str, Any] = {
    "aspect": "9:16",
    "fillMode": "fill",
    "captionFont": "lilita",
    "captionSize": 44,
    "captionColor": "#facc15",
    "logoUrl": "",
    "cta": "Read the full talk →",
    "captionPosition": {"x": 0.5, "y": 0.84},
    "titlePosition": {"x": 0.5, "y": 0.12},
    "ctaPosition": {"x": 0.5, "y": 0.92},
    "introEnabled": False,
    "introText": "",
    "outroEnabled": False,
    "outroText": "",
    "musicEnabled": False,
    "musicMood": "calm",
    "removeFiller": False,
    "keywordHighlighter": True,
}


async def seed_default_brand_template() -> None:
    """Insert a default brand template if none exist (idempotent)."""
    async with AsyncSessionLocal() as db:
        count = (
            await db.execute(select(func.count()).select_from(BrandTemplate))
        ).scalar_one()
        if count and count > 0:
            return
        db.add(BrandTemplate(name="Default", config=DEFAULT_BRAND_CONFIG))
        await db.commit()


def brand_from_template(config: dict[str, Any] | None) -> ClipBrand:
    """Map a BrandTemplate.config dict to a ClipBrand (empties -> None)."""
    cfg = config or {}

    def _clean(key: str) -> str | None:
        val = cfg.get(key)
        if isinstance(val, str):
            val = val.strip()
        return val or None

    size = cfg.get("captionSize")
    caption_size = int(size) if isinstance(size, (int, float)) else None

    fill = cfg.get("fillMode")
    fill_mode: Literal["fill", "fit"] = "fit" if fill == "fit" else "fill"

    intro = _clean("introText") if cfg.get("introEnabled") else None
    outro = _clean("outroText") if cfg.get("outroEnabled") else None

    return ClipBrand(
        logo_url=_clean("logoUrl"),
        cta=_clean("cta"),
        cta_position=cfg.get("ctaPosition"),
        caption_color=_clean("captionColor"),
        caption_size=caption_size,
        caption_font=_clean("captionFont"),
        intro_text=intro,
        outro_text=outro,
        fill_mode=fill_mode,
    )


def music_from_template(config: dict[str, Any] | None) -> ClipMusic:
    """Map a BrandTemplate.config's music settings to a ClipMusic block.

    ``musicMood`` (calm/uplifting/corporate/none) resolves to a built-in track
    URL via the storage seam; ``musicEnabled`` toggles playback. ``none`` or a
    missing mood yields a disabled, track-less block (renderer plays no audio).
    """
    cfg = config or {}
    mood = cfg.get("musicMood")
    if not isinstance(mood, str) or mood in ("", "none"):
        return ClipMusic()
    return ClipMusic(
        track_id=mood,
        url=music_url(mood),
        enabled=bool(cfg.get("musicEnabled")),
    )


# Built-in mood library keys (data/music/<mood>.<ext>). Kept in sync with the
# brand-template UI's MOODS and data/music/README.md.
_LIBRARY_MOODS = {"calm", "uplifting", "corporate"}

# Normalize a free-text mood (e.g. the script agent's suggestion, which may be
# localized) to a library key. Unknown -> None (no music rather than a 404 URL).
_MOOD_SYNONYMS = {
    "calm": "calm", "warm": "calm", "gentle": "calm", "soft": "calm", "peaceful": "calm",
    "uplifting": "uplifting", "epic": "uplifting", "energetic": "uplifting",
    "upbeat": "uplifting", "inspiring": "uplifting", "motivational": "uplifting", "light": "uplifting",
    "corporate": "corporate", "professional": "corporate", "business": "corporate", "neutral": "corporate",
}


def normalize_mood(mood: str | None) -> str | None:
    """Map an arbitrary mood string to a library key, or None if unrecognized."""
    if not isinstance(mood, str):
        return None
    key = mood.strip().lower()
    if key in _LIBRARY_MOODS:
        return key
    return _MOOD_SYNONYMS.get(key) or _MOOD_SYNONYMS.get(mood.strip())


def music_from_mood(mood: str | None) -> ClipMusic:
    """ClipMusic from a clip's own mood suggestion (fallback when no brand template).

    Normalizes to a library key and enables playback; unknown moods yield a
    disabled, track-less block. Playback still requires a track file present
    (see data/music/README.md) — otherwise the endpoint 404s and it's silent.
    """
    key = normalize_mood(mood)
    if key is None:
        return ClipMusic()
    return ClipMusic(track_id=key, url=music_url(key), enabled=True)
