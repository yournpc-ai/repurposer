"""Pinned text resources and layout identities for CompositionVersion.

The version carries the font-set digest, so changing a font file changes the
content identity instead of silently changing a later render. Object storage
keys are content-addressed; the renderer independently verifies every fetched
font against the per-file digest in video-spec.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


FONT_ID = "noto-sans-sc"
FONT_FAMILY = "Noto Sans SC"
FONT_SET_DIGEST = "11c92f6b5efd1a6b91ed87e04d82ddbf961fd40a6d5d6be2e36d33b2e0d272b3"
SEGMENTATION_VERSION = "scalar-grapheme-v1"
LAYOUT_VERSION = "explicit-line-inline-v1"

# The emoji face joins every text family stack as fallback coverage for emoji
# codepoints. Its build also contains Latin glyphs (with a broken space
# advance), so it must be fenced by unicode-range: without the fence Chromium
# matches it first (its family sorts ahead of "Noto Sans SC") and whole Latin
# lines render word-spread in the emoji face.
_EMOJI_UNICODE_RANGE = (
    "U+2190-21FF, U+2300-23FF, U+25A0-25FF, U+2600-27BF, "
    "U+2B00-2BFF, U+1F000-1FAFF, U+FE0F"
)

FONT_FILES = (
    {
        "family": FONT_FAMILY,
        "weight": 400,
        "filename": "NotoSansSC-Regular.otf",
        "format": "opentype",
        "digest": "faa6c9df652116dde789d351359f3d7e5d2285a2b2a1f04a2d7244df706d5ea9",
    },
    {
        "family": FONT_FAMILY,
        "weight": 700,
        "filename": "NotoSansSC-Bold.otf",
        "format": "opentype",
        "digest": "c6cb5a93abaa9edc8ee7463b7ebb7f42d618d40e6ed2f7a5371c97b0b64767c0",
    },
    {
        "family": "Noto Emoji",
        "weight": 400,
        "filename": "NotoEmoji-Regular.ttf",
        "format": "truetype",
        "digest": "988621dc5c9a75eb6144f28faae30317a8e3421b68b28740747b3d739e2326b8",
        "unicode_range": _EMOJI_UNICODE_RANGE,
    },
)


def font_storage_key(filename: str, digest: str) -> str:
    suffix = Path(filename).suffix.lower()
    return f"fonts/{FONT_ID}/{digest}{suffix}"


def font_resources(font_id: str, set_digest: str, weights: set[int]) -> list[dict[str, Any]]:
    """Resolve the immutable files needed by the requested CSS weights.

    With the two pinned faces, Chromium's established matching law is made
    explicit: 400/500 use Regular; 600/700/800 use Bold. No system fallback or
    renderer-local font discovery participates in the compiled spec.
    """
    if font_id != FONT_ID or set_digest != FONT_SET_DIGEST:
        raise ValueError(f"unsupported font resource {font_id}:{set_digest}")
    wanted = {400 if weight in (400, 500) else 700 for weight in weights}
    if not wanted <= {400, 700}:
        raise ValueError(f"unsupported font weights: {sorted(weights)}")
    resources: list[dict[str, Any]] = []
    for item in FONT_FILES:
        weight = int(item["weight"])
        if item["family"] == FONT_FAMILY and weight not in wanted:
            continue
        filename = str(item["filename"])
        digest = str(item["digest"])
        resource: dict[str, Any] = {
            "font_id": FONT_ID,
            "font_set_digest": FONT_SET_DIGEST,
            "family": item["family"],
            "weight": weight,
            "format": item["format"],
            "url": font_storage_key(filename, digest),
            "digest": digest,
        }
        if "unicode_range" in item:
            resource["unicode_range"] = item["unicode_range"]
        resources.append(resource)
    return resources
