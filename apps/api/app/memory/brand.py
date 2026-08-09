"""Resolve a persona's brand skin block into a typed ClipBrand block.

The persona's skin lives in the free-form camelCase ``brand`` block on
``Persona`` (ADR-038 — brand_templates retired; the word stays, the module
does not). At generation time we map the subset the renderer supports into
``ClipBrand`` and bake it into the clip-spec, so the render service / preview
never touch the DB.
"""

from typing import Any, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import ClipBrand, ClipMusic, IntroOutroCard
from app.models.tables import Music, Persona
from app.pipeline.music import get_music, get_music_by_mood
from app.tools.storage import public_url

# The system default skin — a persona whose brand block is NULL bakes with
# these values (partial blocks merge over them). Craft/format defaults
# (aspect / fillMode / captionEnabled / music toggle) live here too: they are
# the task-book defaults the clips pipeline reads when no recipe overrides
# them — they are never written into a persona row.
DEFAULT_BRAND_CONFIG: dict[str, Any] = {
    "aspect": "9:16",
    "fillMode": "fill",
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
    "musicEnabled": False,
    "musicMood": "calm",
    "musicId": None,
    "musicGainDb": -18.0,
    "removeFiller": False,
    "keywordHighlighter": True,
    "captionEnabled": True,
}


async def resolve_brand_block(
    db: AsyncSession,
    persona: Persona | None,
) -> tuple[dict[str, Any], str | None]:
    """Merge the persona's skin over the system default skin + its music id.

    Returns the merged camelCase block (the clips pipeline reads aspect /
    caption / title / intro-outro keys off it) and the resolved default music
    piece id for the GenerationContext.
    """
    cfg = dict(DEFAULT_BRAND_CONFIG)
    if persona is not None and isinstance(persona.brand, dict):
        cfg.update(persona.brand)
    piece = await resolve_music_ref(db, cfg.get("musicId") or cfg.get("musicMood"))
    return cfg, (str(piece.id) if piece is not None else None)


def brand_from_block(config: dict[str, Any] | None) -> ClipBrand:
    """Map a brand skin block dict to a ClipBrand (empties -> None)."""
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

    return ClipBrand(
        caption_color=_clean("captionColor"),
        caption_size=caption_size,
        caption_font=_clean("captionFont"),
        intro=_intro_outro_card(cfg, "intro"),
        outro=_intro_outro_card(cfg, "outro"),
        fill_mode=fill_mode,
        caption_enabled=bool(cfg.get("captionEnabled", True)),
    )


def _intro_outro_card(cfg: dict[str, Any], prefix: str) -> IntroOutroCard | None:
    """Build an intro/outro card from ``{prefix}Enabled/Kind/Text/MediaUrl/DurationSeconds``."""
    if not cfg.get(f"{prefix}Enabled"):
        return None
    duration_raw = cfg.get(f"{prefix}DurationSeconds")
    duration = float(duration_raw) if isinstance(duration_raw, (int, float)) else None
    raw_kind = cfg.get(f"{prefix}Kind") or "image"
    if raw_kind == "text":
        text = cfg.get(f"{prefix}Text")
        text = text.strip() if isinstance(text, str) else ""
        return (
            IntroOutroCard(kind="text", text=text, duration_seconds=duration)
            if text
            else None
        )
    kind: Literal["image", "video"] = "video" if raw_kind == "video" else "image"
    media_url = cfg.get(f"{prefix}MediaUrl")
    media_url = media_url.strip() if isinstance(media_url, str) else ""
    return (
        IntroOutroCard(kind=kind, media_url=media_url, duration_seconds=duration)
        if media_url
        else None
    )


async def music_from_block(
    db: AsyncSession,
    config: dict[str, Any] | None,
) -> ClipMusic:
    """Resolve a brand skin block's default music into a ClipMusic block (DB-backed).

    Reads ``musicId`` (a Music row UUID string) first, falling back to the
    legacy ``musicMood`` key (calm/uplifting/corporate/none). ``musicEnabled``
    toggles playback; ``musicGainDb`` sets the gain. A missing/unknown piece
    yields a disabled, track-less block.
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
        # Bake the storage-resolved public URL (object key → public object URL)
        # so the renderer fetches the audio directly from object storage.
        url=public_url(piece.file_path),
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
    """ClipMusic from a clip's own mood suggestion (fallback when no skin block).

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
        music_id=str(piece.id), url=public_url(piece.file_path), enabled=True
    )


async def music_from_plan(
    db: AsyncSession,
    plan: Any,
    brand_block: dict[str, Any] | None,
) -> ClipMusic:
    """Per-clip music: the Clip Agent's pick wins, else the brand default.

    Selection (see docs/MUSIC_ARCHITECTURE.md §8.3):
    0. If a brand block is set and its ``musicEnabled`` toggle is off, music
       is disabled outright — the skin-level toggle is a master switch the
       per-clip agent's pick cannot override.
    1. ``plan.music_id`` (UUID or mood key) when ``plan.music_enabled`` — the
       agent's per-clip choice, with ``plan.music_gain_db`` applied.
    2. Otherwise the brand block default (``music_from_block``), which
       honors ``musicEnabled``/``musicId``/``musicGainDb`` (and legacy musicMood).
    3. If neither resolves, a disabled, track-less block is returned.
    """
    if brand_block is not None and not brand_block.get("musicEnabled"):
        return ClipMusic(gain_db=_gain_db(brand_block.get("musicGainDb")))

    if getattr(plan, "music_enabled", True) and getattr(plan, "music_id", None):
        piece = await resolve_music_ref(db, plan.music_id)
        if piece is not None:
            return ClipMusic(
                music_id=str(piece.id),
                url=public_url(piece.file_path),
                enabled=True,
                gain_db=float(getattr(plan, "music_gain_db", -18.0) or -18.0),
            )
    return await music_from_block(db, brand_block)
