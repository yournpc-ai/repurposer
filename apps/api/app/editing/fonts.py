"""Pinned text resources and layout identities for CompositionVersion.

The version carries the font-set digest, so changing a font file changes the
content identity instead of silently changing a later render. Object storage
keys are content-addressed; the renderer independently verifies every fetched
font against the per-file digest in video-spec.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


FONT_ID = "noto-sans-sc"
FONT_FAMILY = "Noto Sans SC"
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

_REGULAR = {
    "family": FONT_FAMILY,
    "weight": 400,
    "filename": "NotoSansSC-Regular.otf",
    "format": "opentype",
    "digest": "faa6c9df652116dde789d351359f3d7e5d2285a2b2a1f04a2d7244df706d5ea9",
}
_BOLD = {
    "family": FONT_FAMILY,
    "weight": 700,
    "filename": "NotoSansSC-Bold.otf",
    "format": "opentype",
    "digest": "c6cb5a93abaa9edc8ee7463b7ebb7f42d618d40e6ed2f7a5371c97b0b64767c0",
}
# Unmodified NotoSansCJKsc-Black.otf from notofonts/noto-cjk (SIL OFL 1.1).
# FontFace registers the bytes under the same explicit CSS family alias as the
# other SC faces; only the storage filename is shortened.
_BLACK = {
    "family": FONT_FAMILY,
    "weight": 900,
    "filename": "NotoSansSC-Black.otf",
    "format": "opentype",
    "digest": "2267c4a0312d267dff8c0d1609948f7d949a3da8be3e126f5e2690cb9cc883b4",
}
_EMOJI = {
    "family": "Noto Emoji",
    "weight": 400,
    "filename": "NotoEmoji-Regular.ttf",
    "format": "truetype",
    "digest": "988621dc5c9a75eb6144f28faae30317a8e3421b68b28740747b3d739e2326b8",
    "unicode_range": _EMOJI_UNICODE_RANGE,
}

LEGACY_FONT_SET_DIGEST = "11c92f6b5efd1a6b91ed87e04d82ddbf961fd40a6d5d6be2e36d33b2e0d272b3"
_LEGACY_FONT_FILES = (_REGULAR, _BOLD, _EMOJI)
FONT_FILES = (_REGULAR, _BOLD, _BLACK, _EMOJI)


DISPLAY_FONTS = {
    "editorial-serif": {"filename": "DejaVuSerif.ttf", "family": "DejaVu Serif", "weight": 400, "format": "truetype",
                        "digest": "107244956e9962b9e96faccdc551825e0ae0898ae13737133e1b921a2fd35ffa"},
    "terminal-mono": {"filename": "DejaVuSansMono.ttf", "family": "DejaVu Sans Mono", "weight": 400, "format": "truetype",
                      "digest": "602ec86b8948cfcd956482fe64f94c36c867770149ef2f791d4613f443bcecb3"},
}


def _font_set_digest(files: tuple[dict[str, Any], ...], font_id: str = FONT_ID) -> str:
    identity = json.dumps(
        {"font_id": font_id, "files": files},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(identity).hexdigest()


FONT_SET_DIGEST = _font_set_digest(FONT_FILES)
DISPLAY_DIGESTS = {key: _font_set_digest((face, *FONT_FILES), key) for key, face in DISPLAY_FONTS.items()}
_FONT_SETS = {
    LEGACY_FONT_SET_DIGEST: _LEGACY_FONT_FILES,
    FONT_SET_DIGEST: FONT_FILES,
}


def font_storage_key(filename: str, digest: str) -> str:
    suffix = Path(filename).suffix.lower()
    return f"fonts/{FONT_ID}/{digest}{suffix}"


def font_resources(font_id: str, set_digest: str, weights: set[int]) -> list[dict[str, Any]]:
    """Resolve the immutable files needed by the requested CSS weights.

    Chromium's established matching law is explicit: 400/500 use Regular,
    600/700/800 use Bold, and 900 uses the pinned Black face. Historical
    font-set digests retain their original files and cannot silently acquire
    a face that did not exist when their versions were saved.
    """
    if font_id in DISPLAY_FONTS and set_digest == DISPLAY_DIGESTS[font_id]:
        files = (DISPLAY_FONTS[font_id], *FONT_FILES)
    elif font_id == FONT_ID and set_digest in _FONT_SETS:
        files = _FONT_SETS[set_digest]
    else:
        raise ValueError(f"unsupported font resource {font_id}:{set_digest}")
    if not weights <= {400, 500, 600, 700, 800, 900}:
        raise ValueError(f"unsupported font weights: {sorted(weights)}")
    wanted = {
        400 if weight in (400, 500) else 700 if weight in (600, 700, 800) else 900
        for weight in weights
    }
    available = {int(item["weight"]) for item in files if item["family"] == FONT_FAMILY}
    if not wanted <= available:
        raise ValueError(
            f"font set {set_digest} lacks requested weights: {sorted(wanted - available)}"
        )
    resources: list[dict[str, Any]] = []
    for item in files:
        weight = int(item["weight"])
        if item["family"] == FONT_FAMILY and weight not in wanted:
            continue
        filename = str(item["filename"])
        digest = str(item["digest"])
        resource: dict[str, Any] = {
            "font_id": font_id,
            "font_set_digest": set_digest,
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
