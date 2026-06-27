"""Build a clip-spec (render contract) from an analyzer Segment + ASR words.

The analyzer picks segments by *text* (``source_text`` + ``start_marker`` /
``end_marker``), not by time. To render a real vertical clip we must locate that
text in the source video's ASR word-level timestamps (``Asset.meta["words"]``)
to get precise start/end seconds and the per-word ``caption_track``.

This is the seam between the old ADR-008 text-script model and the new
render-contract model (see docs/VIDEO_EDITOR.md §8): ``Clip.script`` stays as the
AI's creative suggestion; ``Clip.render_spec`` is what actually gets rendered.
"""

import re
from typing import Any, cast

from app.models.schemas import (
    CaptionCue,
    ClipBrand,
    ClipSegment,
    ClipSource,
    ClipSpec,
    ClipTitle,
    Segment,
)
from app.models.tables import Asset
from app.services.storage import stream_url


def _norm(text: str) -> list[str]:
    """Lowercased alphanumeric word tokens, for marker matching."""
    return [t for t in (re.sub(r"[^\w]", "", w).lower() for w in text.split()) if t]


def _locate(haystack: list[str], needle: list[str], *, want: str) -> int | None:
    """Locate a marker in the word stream.

    ``want='start'``: match a leading prefix of ``needle`` (first occurrence),
    return the match's first index. ``want='end'``: match a trailing suffix
    (last occurrence), return the match's last index. Progressively shorter
    probes tolerate light LLM rewording of the marker.
    """
    length = len(haystack)
    for size in range(min(len(needle), 6), 0, -1):
        if want == "start":
            probe = needle[:size]
            for i in range(0, length - size + 1):
                if haystack[i : i + size] == probe:
                    return i
        else:
            probe = needle[-size:]
            for i in range(length - size, -1, -1):
                if haystack[i : i + size] == probe:
                    return i + size - 1
    return None


def locate_span(words: list[dict[str, Any]], segment: Segment) -> tuple[float, float]:
    """Locate a segment's [start, end] seconds within ASR word timestamps.

    Falls back progressively: start/end markers -> source_text ends -> the whole
    transcript. Never raises; returns a best-effort span.
    """
    if not words:
        return (0.0, float(segment.duration_seconds))

    flat = [(_norm(w.get("word", "")) or [""])[0] for w in words]

    start_tokens = _norm(segment.start_marker) or _norm(segment.source_text)
    end_tokens = _norm(segment.end_marker) or _norm(segment.source_text)

    i = _locate(flat, start_tokens, want="start")
    j = _locate(flat, end_tokens, want="end")

    start_idx = i if i is not None else 0
    end_idx = j if j is not None else len(words) - 1
    if end_idx < start_idx:
        end_idx = len(words) - 1

    return (float(words[start_idx]["start"]), float(words[end_idx]["end"]))


def build_clip_spec(
    source: Asset,
    segment: Segment,
    target_language: str,
    *,
    brand: ClipBrand | None = None,
    brand_ref: Any = None,
) -> ClipSpec | None:
    """Build a render-ready clip-spec, or None if the source can't be rendered."""
    url = stream_url(source.file_url)
    if url is None:
        return None

    words: list[dict[str, Any]] = cast("dict[str, Any]", source.meta or {}).get(
        "words", []
    )
    start, end = locate_span(words, segment)

    caption_track = [
        CaptionCue(
            start=float(w["start"]),
            end=float(w["end"]),
            text=str(w["word"]).strip(),
            lang=target_language,
        )
        for w in words
        if start <= float(w["start"]) and float(w["end"]) <= end + 0.05
    ]

    return ClipSpec(
        source=ClipSource(
            asset_id=source.id,
            url=url,
            duration=float(source.duration_seconds) if source.duration_seconds else None,
        ),
        segments=[ClipSegment(start=start, end=end)],
        caption_track=caption_track,
        title=ClipTitle(text=segment.hook or "", enabled=bool(segment.hook)),
        target_language=target_language,
        brand=brand,
        brand_ref=brand_ref,
    )
