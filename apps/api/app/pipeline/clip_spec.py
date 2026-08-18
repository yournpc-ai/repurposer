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
    AssetType,
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
from app.tools.storage import stream_url

# Seconds each backing image holds in a no-audio "stills" slideshow.
SECS_PER_IMAGE = 4.0

# Mirrors ClipSpec.caption_style_preset's Literal values.
_CAPTION_STYLE_PRESETS = {
    "clean-bottom",
    "karaoke-highlight",
    "fade-in",
    "pop-in",
    "slide-up",
    "stacking",
}


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
    aspect = aspect if aspect in ("9:16", "1:1", "16:9", "original") else "9:16"
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
        # Only an AUDIO source's file is a playable speech track — a transcript
        # asset's file is the text document and must never become audio_url.
        audio_url = stream_url(source.file_url) if source.type == AssetType.AUDIO else None
        if words:
            # Word-timed: captions (+ speech track when a recording exists)
            # sliced to the located span. Words without audio = the estimated
            # timeline from align_stills — a captioned slideshow, silent
            # speech track (RECIPES §2's third time source).
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
            url, duration = audio_url or "", (
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


def remove_range(spec: ClipSpec, start: float, end: float) -> ClipSpec:
    """Python mirror of the TS ``removeRange`` (packages/clip/src/types.ts) —
    same name across the stack (NAMING §1).

    Non-destructive cut of a source time range [start, end]: the overlapped
    part of each kept segment becomes a ``hidden`` segment (recoverable), and
    caption cues fully inside the range are dropped. Compromise (same as TS):
    cues are word/line-level, so a cue that straddles the boundary is kept.

    Segment ids (ADR-044): the FIRST kept piece of a split segment inherits
    the parent's id (anchors ride the surviving kept content); hidden pieces
    and later kept pieces mint fresh ids. Hetero splices (asset_id/url) carry
    their donor identity onto every piece.
    """
    if end <= start:
        return spec
    segments: list[ClipSegment] = []
    for s in spec.segments:
        if s.hidden:
            segments.append(s)
            continue
        a = max(start, s.start)
        b = min(end, s.end)
        if a >= b:
            segments.append(s)
            continue
        donor = {"asset_id": s.asset_id, "url": s.url, "provenance": s.provenance}
        # The transition lives on the ENTRY edge: only the piece that still
        # starts at s.start inherits it; cut-born pieces hard-cut in.
        pieces: list[ClipSegment] = []
        if s.start < a:
            pieces.append(
                ClipSegment(start=s.start, end=a, hidden=False, transition=s.transition, **donor)
            )
        pieces.append(ClipSegment(start=a, end=b, hidden=True, **donor))
        if b < s.end:
            pieces.append(ClipSegment(start=b, end=s.end, hidden=False, **donor))
        # First kept piece keeps the parent id; the rest ride minted ids.
        first_kept = next((p for p in pieces if not p.hidden), None)
        if first_kept is not None:
            first_kept.id = s.id
        segments.extend(pieces)
    eps = 1e-6
    caption_track = [
        c for c in spec.caption_track if not (c.start >= start - eps and c.end <= end + eps)
    ]
    return spec.model_copy(update={"segments": segments, "caption_track": caption_track})


def set_trim(spec: ClipSpec, start: float, end: float) -> ClipSpec:
    """Python mirror of the TS ``setTrim`` (packages/clip/src/types.ts) —
    same name across the stack (NAMING §1).

    Set the outer in/out by moving the first/last kept segment boundaries.
    """
    if end <= start:
        return spec
    kept_idx = [i for i, s in enumerate(spec.segments) if not s.hidden]
    if not kept_idx:
        return spec
    segments = list(spec.segments)
    segments[kept_idx[0]] = segments[kept_idx[0]].model_copy(update={"start": start})
    segments[kept_idx[-1]] = segments[kept_idx[-1]].model_copy(update={"end": end})
    return spec.model_copy(update={"segments": segments})


# ---------------------------------------------------------------------------
# Lane projection mirrors (存法 C, ADR-044) — Python twins of the TS lane
# projection (packages/clip/src/types.ts; snake_case per NAMING §1). Dict-based:
# the seams carry render_spec JSONB, not models. The output clock computed here
# is a compile artifact — never persisted.
# ---------------------------------------------------------------------------

# Mirror TS INTRO_SECONDS / OUTRO_SECONDS (brand card default durations).
INTRO_SECONDS = 2.0
OUTRO_SECONDS = 2.0


def intro_seconds(spec: dict) -> float:
    """Intro card duration (0 when no brand intro card). TS: introSeconds."""
    brand = spec.get("brand")
    card = brand.get("intro") if isinstance(brand, dict) else None
    if not isinstance(card, dict):
        return 0.0
    return float(card.get("duration_seconds") or INTRO_SECONDS)


def outro_seconds(spec: dict) -> float:
    """Outro card duration (0 when no brand outro card). TS: outroSeconds."""
    brand = spec.get("brand")
    card = brand.get("outro") if isinstance(brand, dict) else None
    if not isinstance(card, dict):
        return 0.0
    return float(card.get("duration_seconds") or OUTRO_SECONDS)


def video_duration_seconds(spec: dict) -> float:
    """Kept video duration (cards excluded). TS: videoDurationSeconds."""
    return sum(
        max(0.0, float(s.get("end", 0)) - float(s.get("start", 0)))
        for s in spec.get("segments") or []
        if isinstance(s, dict) and not s.get("hidden")
    )


def total_output_seconds(spec: dict) -> float:
    """Seconds of rendered output — pricing's duration mirror (TS twin
    ``totalDurationSeconds``). Kept video + brand card seconds.

    Known boundary (ADR-044): the registry does NOT auto-adopt duration —
    a future duration-bearing track extends the arithmetic right here,
    alongside its renderer piece.
    """
    total = video_duration_seconds(spec) + intro_seconds(spec) + outro_seconds(spec)
    return total if total > 0 else 1 / 30.0  # >= a frame (COMPOSITION_FPS=30)


def video_timeline(spec: dict) -> list[dict]:
    """Kept segments on the video-local output clock. TS: videoTimeline.

    Each entry: ``{"segment": <the spec dict>, "out_start": float, "dur": float}``.
    """
    entries: list[dict] = []
    acc = 0.0
    for s in spec.get("segments") or []:
        if not isinstance(s, dict) or s.get("hidden"):
            continue
        dur = max(0.0, float(s.get("end", 0)) - float(s.get("start", 0)))
        entries.append({"segment": s, "out_start": acc, "dur": dur})
        acc += dur
    return entries


def source_time_at_output_time(spec: dict, output_seconds: float) -> float | None:
    """Output → source remap. TS: sourceTimeAtOutputTime.

    Which SOURCE second shows at this FULL-CLOCK output second (intro card
    included). None outside the video portion. Transition veils are visual
    overlays — they never shift the mapping (single-sided, no time eat).
    """
    local = output_seconds - intro_seconds(spec)
    if local < 0 or local >= video_duration_seconds(spec):
        return None
    for entry in video_timeline(spec):
        if entry["out_start"] <= local < entry["out_start"] + entry["dur"]:
            seg = entry["segment"]
            return float(seg["start"]) + (local - entry["out_start"])
    return None


def output_time_at_source_time(spec: dict, source_seconds: float) -> float | None:
    """Source → output remap. TS: outputTimeAtSourceTime.

    The FULL-CLOCK output second at which this source second appears. None
    when the source second is cut (hidden) or uncovered.
    """
    for entry in video_timeline(spec):
        seg = entry["segment"]
        if float(seg["start"]) <= source_seconds < float(seg["end"]):
            return intro_seconds(spec) + entry["out_start"] + (source_seconds - float(seg["start"]))
    return None


def project_layer_windows(spec: dict) -> dict:
    """Layer lane projection. TS: projectLayers.

    Resolve every layer's anchor to a full-clock output window clamped to the
    video portion. Unresolvable anchors (segment deleted/hidden) land in
    ``unresolved`` — the stored anchor is never rewritten (non-destructive).
    """
    intro = intro_seconds(spec)
    video_dur = video_duration_seconds(spec)
    timeline = video_timeline(spec)
    resolved: list[dict] = []
    unresolved: list[dict] = []
    for layer in spec.get("layers") or []:
        anchor = layer.get("anchor") or {}
        offset = float(anchor.get("offset_seconds") or 0.0)
        anchor_out: float | None = None
        kind = anchor.get("kind")
        if kind == "segment":
            entry = next(
                (t for t in timeline if t["segment"].get("id") == anchor.get("segment_id")),
                None,
            )
            if entry is not None:
                anchor_out = intro + entry["out_start"] + min(max(0.0, offset), entry["dur"])
        elif kind == "edge":
            anchor_out = intro + video_dur - offset if anchor.get("edge") == "tail" else intro + offset
        elif kind == "ratio":
            anchor_out = intro + float(anchor.get("ratio") or 0.0) * video_dur
        if anchor_out is None:
            unresolved.append(layer)
            continue
        start = min(max(anchor_out, intro), intro + video_dur)
        end = min(start + float(layer.get("duration_seconds") or 0.0), intro + video_dur)
        resolved.append({"layer": layer, "window": {"start": start, "end": end}})
    return {"resolved": resolved, "unresolved": unresolved}
