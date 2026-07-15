"""Build a clip-spec (render contract) from an analyzer Segment + ASR words.

The analyzer picks segments by *text* (``source_text`` + ``start_marker`` /
``end_marker``), not by time. To render a real vertical clip we must locate that
text in the source video's ASR word-level timestamps (``Asset.meta["words"]``)
to get precise start/end seconds and the per-word ``caption_track``.

``Clip.render_spec`` is the sole renderer contract; the analyzer's creative
output lives directly on ``Clip`` fields (hook, title_options, music_mood,
duration) and in ``Clip.source_segment``.
"""

import re
from typing import Any, cast

from app.models.schemas import (
    CaptionCue,
    ClipBrand,
    ClipMusic,
    ClipSegment,
    ClipSource,
    ClipSpec,
    ClipTitle,
    Segment,
)
from app.models.tables import Asset
from app.services.storage import stream_url

# Seconds each backing image holds in a no-audio "stills" slideshow.
SECS_PER_IMAGE = 4.0

# Mirrors ClipSpec.caption_style_preset's Literal values.
_CAPTION_STYLE_PRESETS = {"clean-bottom", "karaoke-highlight", "fade-in", "pop-in", "slide-up"}


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

    Prefer exact ``start_seconds`` / ``end_seconds`` when the agent provided them.
    Otherwise fall back to text matching via start/end markers -> source_text
    ends -> the whole transcript. Never raises; returns a best-effort span.
    """
    if not words:
        return (0.0, float(segment.duration_seconds))

    # If the agent produced numeric timestamps, use them directly but snap to the
    # nearest word boundaries so cues stay in sync with the audio.
    if segment.start_seconds is not None and segment.end_seconds is not None:
        start_sec = max(0.0, float(segment.start_seconds))
        end_sec = max(start_sec, float(segment.end_seconds))
        start_idx = next(
            (i for i, w in enumerate(words) if float(w.get("start", 0)) >= start_sec),
            0,
        )
        end_idx = next(
            (
                i
                for i in range(len(words) - 1, -1, -1)
                if float(words[i].get("end", 0)) <= end_sec
            ),
            len(words) - 1,
        )
        if end_idx < start_idx:
            end_idx = len(words) - 1
        return (float(words[start_idx]["start"]), float(words[end_idx]["end"]))

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
    kind: str = "video",
    aspect: str = "9:16",
    caption_position: Any = None,
    caption_enabled: bool = True,
    caption_style_preset: str = "clean-bottom",
    title_size: int | None = None,
    title_position: Any = None,
    title_enabled: bool = True,
    image_urls: list[str] | None = None,
    brand: ClipBrand | None = None,
    music: ClipMusic | None = None,
    brand_ref: Any = None,
) -> ClipSpec | None:
    """Build a render-ready clip-spec, or None if the source can't be rendered.

    ``kind="video"``: ``source`` is an on-camera VIDEO asset (with ASR words).
    ``kind="stills"``: an audiogram — ``image_urls`` back the visual and
    ``source`` is either a speech AUDIO asset (ASR words -> captions + audio
    track) or, when there's no recording, the primary IMAGE asset (no audio, a
    fixed-length slideshow sized by the image count).

    ``caption_position`` / ``title_position`` are normalized ``{x, y}`` points
    (or None for the renderer default); pydantic coerces the dicts into ``Point``.
    """
    images = image_urls or []
    aspect = aspect if aspect in ("9:16", "1:1") else "9:16"
    caption_style_preset = (
        caption_style_preset if caption_style_preset in _CAPTION_STYLE_PRESETS else "clean-bottom"
    )
    title = ClipTitle(
        text=segment.hook or "",
        enabled=bool(segment.hook) and title_enabled,
        size=title_size,
        position=title_position,
    )

    if kind == "stills":
        words: list[dict[str, Any]] = cast("dict[str, Any]", source.meta or {}).get(
            "words", []
        )
        audio_url = stream_url(source.file_url)
        if words and audio_url:
            # Audio-backed: captions + speech track sliced to the located span.
            start, end = locate_span(words, segment)
            caption_track = (
                [
                    CaptionCue(
                        start=float(w["start"]),
                        end=float(w["end"]),
                        text=str(w["word"]).strip(),
                        lang=target_language,
                    )
                    for w in words
                    if start <= float(w["start"]) and float(w["end"]) <= end + 0.05
                ]
                if caption_enabled
                else []
            )
            url, duration = audio_url, (
                float(source.duration_seconds) if source.duration_seconds else None
            )
        else:
            # No recording: a fixed-length slideshow (no per-word captions).
            start, end = 0.0, float(max(1, len(images)) * SECS_PER_IMAGE)
            caption_track = []
            url, duration = "", end
        return ClipSpec(
            source=ClipSource(
                asset_id=source.id,
                kind="stills",
                url=url,
                image_urls=images,
                duration=duration,
            ),
            aspect=aspect,
            segments=[ClipSegment(start=start, end=end)],
            caption_track=caption_track,
            caption_position=caption_position,
            caption_enabled=caption_enabled,
            caption_style_preset=caption_style_preset,
            title=title,
            target_language=target_language,
            brand=brand,
            music=music or ClipMusic(),
            brand_ref=brand_ref,
        )

    url = stream_url(source.file_url)
    if url is None:
        return None

    words = cast("dict[str, Any]", source.meta or {}).get("words", [])
    start, end = locate_span(words, segment)

    caption_track = (
        [
            CaptionCue(
                start=float(w["start"]),
                end=float(w["end"]),
                text=str(w["word"]).strip(),
                lang=target_language,
            )
            for w in words
            if start <= float(w["start"]) and float(w["end"]) <= end + 0.05
        ]
        if caption_enabled
        else []
    )

    return ClipSpec(
        source=ClipSource(
            asset_id=source.id,
            url=url,
            duration=float(source.duration_seconds) if source.duration_seconds else None,
        ),
        aspect=aspect,
        segments=[ClipSegment(start=start, end=end)],
        caption_track=caption_track,
        caption_position=caption_position,
        caption_enabled=caption_enabled,
        caption_style_preset=caption_style_preset,
        title=title,
        target_language=target_language,
        brand=brand,
        music=music or ClipMusic(),
        brand_ref=brand_ref,
    )
