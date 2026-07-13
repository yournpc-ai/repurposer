"""Resolve a BrandTemplate's free-form config into a typed ClipBrand block.

The brand-template UI stores its settings as a camelCase ``config`` dict on
``BrandTemplate`` (see apps/web/src/routes/brand-template.tsx ``Template``). At
generation time we map the subset the renderer supports into ``ClipBrand`` and
bake it into the clip-spec, so the render service / preview never touch the DB.
"""

from typing import Any, Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import DEFAULT_USER_EMAIL, DEFAULT_USER_ID
from app.models.database import AsyncSessionLocal
from app.models.schemas import ClipBrand, ClipMusic
from app.models.tables import BrandTemplate, Music, User
from app.services.music import get_music, get_music_by_mood
from app.services.storage import music_stream_url

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
    "musicId": None,
    "musicGainDb": -18.0,
    "removeFiller": False,
    "keywordHighlighter": True,
}


async def seed_default_brand_template() -> None:
    """Insert a default brand template for the default user if none exist."""
    async with AsyncSessionLocal() as db:
        # Ensure the seeded default user exists.
        result = await db.execute(select(User).where(User.email == DEFAULT_USER_EMAIL))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                id=DEFAULT_USER_ID,
                email=DEFAULT_USER_EMAIL,
                name="Default User",
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

        count = (
            await db.execute(
                select(func.count())
                .select_from(BrandTemplate)
                .where(BrandTemplate.user_id == user.id)
            )
        ).scalar_one()
        if count and count > 0:
            return
        db.add(
            BrandTemplate(
                name="Default",
                user_id=user.id,
                config=DEFAULT_BRAND_CONFIG,
            )
        )
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


async def music_from_template(
    db: AsyncSession,
    config: dict[str, Any] | None,
) -> ClipMusic:
    """Resolve a BrandTemplate's default music into a ClipMusic block (DB-backed).

    Reads ``musicId`` (a Music row UUID string) first, falling back to the
    legacy ``musicMood`` key (calm/uplifting/corporate/none) for templates saved
    before the rename. ``musicEnabled`` toggles playback; ``musicGainDb`` sets
    the gain. A missing/unknown piece yields a disabled, track-less block.
    """
    cfg = config or {}
    gain = _gain_db(cfg.get("musicGainDb"))
    enabled = bool(cfg.get("musicEnabled"))
    piece = await resolve_music_ref(db, cfg.get("musicId")) or await resolve_music_ref(
        db, cfg.get("musicMood")
    )
    if piece is None:
        return ClipMusic(enabled=enabled, gain_db=gain)
    return ClipMusic(
        music_id=str(piece.id),
        url=music_stream_url(piece.id),
        enabled=enabled,
        gain_db=gain,
    )


# Built-in mood library keys (the 3 default-catalog moods). The DB ``music``
# table is the source of truth for which pieces exist; this set is the
# free-text normalization layer (the Clip Agent may emit a synonym).
_LIBRARY_MOODS = {"calm", "uplifting", "corporate"}

# Normalize a free-text mood (e.g. the script agent's suggestion, which may be
# localized) to a library key. Unknown -> None (no music rather than a 404 URL).
_MOOD_SYNONYMS = {
    "calm": "calm",
    "warm": "calm",
    "gentle": "calm",
    "soft": "calm",
    "peaceful": "calm",
    "uplifting": "uplifting",
    "epic": "uplifting",
    "energetic": "uplifting",
    "upbeat": "uplifting",
    "inspiring": "uplifting",
    "motivational": "uplifting",
    "light": "uplifting",
    "corporate": "corporate",
    "professional": "corporate",
    "business": "corporate",
    "neutral": "corporate",
}


def normalize_mood(mood: str | None) -> str | None:
    """Map an arbitrary mood string to a library key, or None if unrecognized."""
    if not isinstance(mood, str):
        return None
    key = mood.strip().lower()
    if key in _LIBRARY_MOODS:
        return key
    return _MOOD_SYNONYMS.get(key) or _MOOD_SYNONYMS.get(mood.strip())


def _gain_db(raw: Any) -> float:
    """Coerce a config gain value to a float, defaulting to -18 dB."""
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    return -18.0


async def resolve_music_ref(db: AsyncSession, ref: Any) -> Music | None:
    """Resolve a music reference (UUID string or mood key) to a Music row.

    Tries ``ref`` as a UUID first (the new contract), then as a mood key (legacy
    / agent-friendly). ``None``/empty/unknown -> None.
    """
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
    if key is None:
        return None
    return await get_music_by_mood(db, key)


async def music_from_mood(db: AsyncSession, mood: str | None) -> ClipMusic:
    """ClipMusic from a clip's own mood suggestion (fallback when no template).

    Resolves the mood to a Music row and enables playback; unknown moods (or no
    matching row) yield a disabled, track-less block.
    """
    key = normalize_mood(mood)
    if key is None:
        return ClipMusic()
    piece = await get_music_by_mood(db, key)
    if piece is None:
        return ClipMusic()
    return ClipMusic(
        music_id=str(piece.id), url=music_stream_url(piece.id), enabled=True
    )


async def music_from_plan(
    db: AsyncSession,
    plan: Any,
    brand_config: dict[str, Any] | None,
) -> ClipMusic:
    """Per-clip music: the Clip Agent's pick wins, else the brand default.

    Selection (see docs/MUSIC_ARCHITECTURE.md §8.3):
    1. ``plan.music_id`` (UUID or mood key) when ``plan.music_enabled`` — the
       agent's per-clip choice, with ``plan.music_gain_db`` applied.
    2. Otherwise the brand template default (``music_from_template``), which
       honors ``musicEnabled``/``musicId``/``musicGainDb`` (and legacy musicMood).
    3. If neither resolves, a disabled, track-less block is returned.
    """
    if getattr(plan, "music_enabled", True) and getattr(plan, "music_id", None):
        piece = await resolve_music_ref(db, plan.music_id)
        if piece is not None:
            return ClipMusic(
                music_id=str(piece.id),
                url=music_stream_url(piece.id),
                enabled=True,
                gain_db=float(getattr(plan, "music_gain_db", -18.0) or -18.0),
            )
    return await music_from_template(db, brand_config)
