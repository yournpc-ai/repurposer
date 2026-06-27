"""Resolve a BrandTemplate's free-form config into a typed ClipBrand block.

The brand-template UI stores its settings as a camelCase ``config`` dict on
``BrandTemplate`` (see apps/web/src/routes/brand-template.tsx ``Template``). At
generation time we map the subset the renderer supports into ``ClipBrand`` and
bake it into the clip-spec, so the render service / preview never touch the DB.
"""

from typing import Any, Literal

from app.models.schemas import ClipBrand, ClipMusic
from app.services.storage import music_url


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

    return ClipBrand(
        logo_url=_clean("logoUrl"),
        cta=_clean("cta"),
        caption_color=_clean("captionColor"),
        caption_size=caption_size,
        caption_font=_clean("captionFont"),
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
