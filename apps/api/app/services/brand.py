"""Resolve a BrandTemplate's free-form config into a typed ClipBrand block.

The brand-template UI stores its settings as a camelCase ``config`` dict on
``BrandTemplate`` (see apps/web/src/routes/brand-template.tsx ``Template``). At
generation time we map the subset the renderer supports into ``ClipBrand`` and
bake it into the clip-spec, so the render service / preview never touch the DB.
"""

from typing import Any, Literal

from app.models.schemas import ClipBrand


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
        fill_mode=fill_mode,
    )
