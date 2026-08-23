"""Stills beat planning (产物质量线期 2, 简报 §2.3) — the editor's code half.

The stills editor agent writes the beat plan's CREATIVE half (image order /
motion / emphasis / markers); this module owns the deterministic half:

- ``build_backing_list`` — the backing visuals in the exact order
  ``resolve_render_source`` feeds them (slide pages first, then images),
  joined with their visual anchors (deterministic faces/subject box from
  asset.meta, semantic labels from the understanding) so the editor can
  match the hook image to the opening phrase.
- ``resolve_beat_plan`` — markers snap onto the word axis (同理解层铁律:
  LLM 永不写时间戳); beat[0] starts at the span start and the last beat
  ends at the span end BY CONSTRUCTION (zero-gap chain — cuts always land
  on word boundaries); unresolved interior markers degrade to an even
  share of the remaining span (logged, never fabricated precision).
- ``coherence_violations`` — the独立跨拍连贯性检查 (简报 §2.3: 节奏曲线/
  强调多样性是机械质检的盲区，这条链专管): one-image-once, motion
  alternation, dwell bands, emphasis scarcity/dedup, breathing coverage.
  Violations ride the agent funnel's ``repair_feedback`` for ONE bounded
  re-roll (ADR-047 节点内有界环), never a silent accept.
- ``plan_still_beats`` — the orchestration: single pass inside the可靠域
  (≤15 beats / ≤45s), two-stage (大纲段 → 逐拍段 with explicit handoff
  state) beyond it.
"""

from __future__ import annotations

import re
from typing import Any

import structlog

from app.models.schemas import (
    AssetType,
    BeatOutline,
    BeatPlan,
    MaterialUnderstanding,
    Segment,
    StillBeat,
)
from app.pipeline.beat_map import _Axis, _locate
from app.pipeline.clip_spec import locate_span
from app.providers.storage import stream_url
from app.tools.clips.transcript import build_anchored_transcript

logger = structlog.get_logger()

# 单发可靠域 (简报 §2.3 上限纪律): beyond either bound the editor works
# two-stage (outline → per-section beats with handoff state).
_SINGLE_PASS_MAX_BEATS = 15
_SINGLE_PASS_MAX_SECONDS = 45.0
# Craft bands from the §2.1 图文视频 prior table (先验 — 解剖校准前不作闸;
# these drive coherence WARNINGS, never hard rejects).
_DWELL_MIN_S = 1.3
_DWELL_MAX_S = 6.0
_BREATHING_WINDOW_S = 18.0
_BEAT_TARGET_S = 3.5  # planning heuristic for the beat-count guidance


def build_backing_list(
    assets: list, understanding: MaterialUnderstanding | None
) -> list[dict[str, Any]]:
    """The backing visuals in render order (slide pages first, then images —
    the same order ``resolve_render_source`` builds ``still_images``).

    Each entry: ref ("image N"), url (storage seam), asset_id (None for
    slide pages), the understanding's semantic label + argument links, and
    the deterministic visual anchors (faces / subject box) when the asset
    carries them.
    """
    semantic_by_asset: dict[str, Any] = {}
    if understanding is not None:
        for v in understanding.visual_anchors:
            if v.asset_id:
                semantic_by_asset[v.asset_id] = v

    backing: list[dict[str, Any]] = []
    ordered = [a for a in assets if a.type == AssetType.SLIDES] + [
        a for a in assets if a.type == AssetType.IMAGE
    ]
    for a in ordered:
        if a.type == AssetType.SLIDES:
            for idx, page in enumerate(a.slide_pages or [], start=1):
                url = stream_url(page)
                if url:
                    backing.append(
                        {
                            "ref": f"image {len(backing) + 1}",
                            "url": url,
                            "asset_id": None,
                            "label": f"Slide {idx} of the deck",
                            "argument_ids": [],
                            "has_face": None,
                            "subject_box": None,
                        }
                    )
        elif a.type == AssetType.IMAGE and a.file_url:
            url = stream_url(a.file_url)
            if not url:
                continue
            anchors = (a.meta or {}).get("visual_anchors") or {}
            semantic = semantic_by_asset.get(str(a.id))
            backing.append(
                {
                    "ref": f"image {len(backing) + 1}",
                    "url": url,
                    "asset_id": str(a.id),
                    "label": (semantic.label if semantic else "") or "photo",
                    "argument_ids": list(semantic.argument_ids) if semantic else [],
                    "has_face": bool(anchors.get("faces")) if anchors else None,
                    "subject_box": anchors.get("subject_box"),
                }
            )
    return backing


def _word_index_at_time(axis: _Axis, t: float) -> int:
    """The first word whose start is at/after ``t`` (last word when beyond)."""
    for i, w in enumerate(axis.words):
        if float(w.get("start") or 0) >= t:
            return i
    return len(axis.words) - 1


def _word_end_before(axis: _Axis, t: float) -> float:
    """The end of the last word starting before ``t`` (the cut lands in the
    pause); ``t`` itself when there is no earlier word."""
    idx = _word_index_at_time(axis, t)
    if idx <= 0:
        return t
    return float(axis.words[idx - 1].get("end") or t)


def _resolve_beats(
    beats: list[StillBeat],
    axis: _Axis,
    backing: list[dict[str, Any]],
    span_start: float,
    span_end: float,
) -> None:
    """Snap beat markers onto the word axis and chain the ends in place.

    Construction guarantees: beats[0].start = span_start, beats[-1].end =
    span_end; interior boundaries snap from markers. An unresolved marker
    degrades to an even share of its enclosing resolved span, snapped to the
    nearest word start (logged, never fabricated mid-word). Spans are then
    assigned by TILING (pass C): each beat ends exactly at the next beat's
    start — the shots play back-to-back on the render timeline.
    """
    by_ref = {b["ref"]: b for b in backing}
    for b in beats:
        entry = by_ref.get(b.image_ref.strip())
        if entry is None:  # tolerate "Image 2" casing / loose spacing
            m = re.fullmatch(r"image\s+(\d+)", b.image_ref.strip().lower())
            if m and 0 < int(m.group(1)) <= len(backing):
                entry = backing[int(m.group(1)) - 1]
        if entry is not None:
            b.asset_id = entry["asset_id"] or ""
            b.image_url = entry["url"]
    if not beats:
        return

    # Pass A: boundary times — first/last by construction, interior by marker.
    n = len(beats)
    bounds: list[float | None] = [span_start]
    for b in beats[1:]:
        hit = _locate([axis], b.marker, b.approx_start)
        bounds.append(axis.word_start_s(hit[1]) if hit else None)
    bounds.append(span_end)

    # Pass B: even-share fill for unresolved interior markers, then a
    # monotone clamp (out-of-order markers can never invert a dwell).
    unresolved = [i for i in range(1, n) if bounds[i] is None]
    if unresolved:
        logger.warning("beat_plan_marker_fallback", count=len(unresolved))
        i = 0
        while i < len(unresolved):
            run = [unresolved[i]]
            while i + 1 < len(unresolved) and unresolved[i + 1] == run[-1] + 1:
                i += 1
                run.append(unresolved[i])
            i += 1
            left = float(bounds[run[0] - 1])  # always resolved (construction or earlier fill)
            right = float(bounds[run[-1] + 1])  # next resolved boundary or span_end
            step = max(0.0, right - left) / (len(run) + 1)
            for k, idx in enumerate(run):
                target = left + step * (k + 1)
                wi = _word_index_at_time(axis, target)
                snapped = axis.word_start_s(wi)
                bounds[idx] = max(float(bounds[idx - 1]), min(snapped, right))
    for i in range(1, len(bounds)):
        if float(bounds[i]) < float(bounds[i - 1]):
            bounds[i] = float(bounds[i - 1])

    # Pass C: assign spans by TILING — a beat holds through the trailing
    # pause and ends exactly at the next beat's first word (the cut lands
    # on the new sentence, never mid-word; shots tile the output timeline
    # contiguously, so boundaries and dwells share the one word clock).
    for i, b in enumerate(beats):
        b.start = float(bounds[i])
        b.end = float(bounds[i + 1])


def coherence_violations(plan: BeatPlan, backing: list[dict[str, Any]]) -> list[str]:
    """The独立跨拍连贯性检查 — mechanical, prior-band warnings (never gates).

    Returns human-readable violation lines (they ride repair_feedback
    verbatim, so they must tell the editor exactly what to fix).
    """
    violations: list[str] = []
    beats = [b for b in plan.beats if b.start is not None and b.end is not None]
    if not beats:
        return ["no resolved beats — every beat needs a marker from the cue lines"]

    seen: dict[str, int] = {}
    for i, b in enumerate(plan.beats):
        ref = b.image_ref.strip().lower()
        seen[ref] = seen.get(ref, 0) + 1
        if seen[ref] > 1:
            violations.append(f"beat {i + 1}: {b.image_ref} is used more than once — one visual at most once")
        if b.image_ref and not b.image_url:
            violations.append(f"beat {i + 1}: unknown visual ref {b.image_ref!r} — use the listed refs exactly")

    dwells = [float(b.end) - float(b.start) for b in beats]
    for i, d in enumerate(dwells):
        if d < _DWELL_MIN_S:
            violations.append(f"beat {i + 1}: dwell {d:.1f}s strobes (<{_DWELL_MIN_S}s) — widen its span")
        elif d > _DWELL_MAX_S:
            violations.append(f"beat {i + 1}: dwell {d:.1f}s bores (>{_DWELL_MAX_S}s) — split it or accept material scarcity")

    moving = [(i, b.motion) for i, b in enumerate(beats) if b.motion != "none"]
    for (i, m), (j, n) in zip(moving, moving[1:]):
        opposite = {("zoom_in", "zoom_out"), ("zoom_out", "zoom_in"), ("pan_left", "pan_right"), ("pan_right", "pan_left")}
        if (m, n) not in opposite and m == n:
            violations.append(f"beats {i + 1}-{j + 1}: same motion {m} twice in a row — alternate direction")

    emphasized = [i for i, b in enumerate(beats) if b.emphasis != "none"]
    if len(emphasized) > max(1, len(beats) // 3):
        violations.append("emphasis is scarce — keep it to about a third of the beats")
    for i, j in zip(emphasized, emphasized[1:]):
        if beats[i].emphasis == beats[j].emphasis:
            violations.append(f"beats {i + 1}-{j + 1}: same emphasis device twice — vary hold/punch_in/caption_pop")

    reset_times = [float(b.start) for b in beats if b.reset]
    t0, t1 = float(beats[0].start), float(beats[-1].end)
    cursor = t0
    for rt in sorted(reset_times):
        if rt - cursor > _BREATHING_WINDOW_S:
            violations.append(f"no breathing reset between {cursor:.0f}s and {rt:.0f}s — mark a `reset` beat every 12–18s")
        cursor = rt
    if t1 - cursor > _BREATHING_WINDOW_S and t1 - t0 > _BREATHING_WINDOW_S:
        violations.append(f"no breathing reset after {cursor:.0f}s — mark a `reset` beat every 12–18s")

    return violations


def _span_emphasis_hints(
    understanding: MaterialUnderstanding | None,
    render_source,
    start: float,
    end: float,
) -> list[dict[str, Any]]:
    """The evidence rows overlapping the clip span: the understanding's
    semantic beat-map rows (emphasis words / climax / quotables) PLUS the
    render source's acoustic peaks (prosody meta, when the source is a real
    recording) — the two channels side by side, never merged (铁律)."""
    hints: list[dict[str, Any]] = []
    if understanding is not None:
        for e in understanding.emphasis_words:
            if e.start is not None and start <= e.start <= end:
                hints.append({"kind": "emphasis_word", "word": e.word, "at": e.start, "weight": e.weight})
        for c in understanding.climax_spans:
            if c.start is not None and c.end is not None and c.end > start and c.start < end:
                hints.append({"kind": "climax", "text": c.text[:80], "start": c.start, "end": c.end})
        for q in understanding.quotable_lines:
            if q.start is not None and q.end is not None and q.end > start and q.start < end:
                hints.append({"kind": "quotable", "text": q.text[:80], "start": q.start, "end": q.end})
    prosody = (render_source.meta or {}).get("prosody") or {}
    for p in prosody.get("emphasis_peaks") or []:
        t = p.get("t")
        if t is not None and start <= float(t) <= end:
            hints.append(
                {
                    "kind": "acoustic_peak",
                    "word": p.get("word"),
                    "at": t,
                    "channel": p.get("kind"),  # f0 / energy / f0+energy
                    "f0_z": p.get("f0_z"),
                    "energy_z": p.get("energy_z"),
                }
            )
    return hints


async def plan_still_beats(
    render_source,
    segment: Segment,
    understanding: MaterialUnderstanding | None,
    assets: list,
) -> BeatPlan | None:
    """One stills clip's beat plan, or None when beats can't be planned
    (no word axis / no backing visuals — the caller falls back to the
    legacy even split).

    Single pass inside the可靠域 (≤15 beats / ≤45s); two-stage beyond:
    outline (arc + resource assignment) → per-section beats carrying the
    explicit handoff state (used visuals / last motion / emphasis history /
    span anchors) — 防漏点全在拍间 (简报 §2.3).
    """
    from app.tools.stills.agents import stills_editor, stills_editor_outline  # deferred: agents import chain

    words = (render_source.meta or {}).get("words") or []
    if not words:
        return None
    backing = build_backing_list(assets, understanding)
    if not backing:
        return None

    span_start, span_end = locate_span(words, segment)
    span_words = [
        w for w in words if span_start <= float(w.get("start", 0)) and float(w.get("end", 0)) <= span_end + 0.05
    ]
    if not span_words:
        return None
    duration = span_end - span_start
    target_beats = min(len(backing), max(2, round(duration / _BEAT_TARGET_S)))
    axis = _Axis("render", [w for w in span_words if str(w.get("word") or "").strip()])
    if not axis.words:
        return None

    ctx: dict[str, Any] = {
        "span_transcript": build_anchored_transcript(span_words),
        "images": [
            {k: v for k, v in b.items() if k != "url"} for b in backing
        ],
        "emphasis_hints": _span_emphasis_hints(understanding, render_source, span_start, span_end),
        "span_seconds": round(duration, 1),
        "target_beats": target_beats,
    }

    if target_beats <= _SINGLE_PASS_MAX_BEATS and duration <= _SINGLE_PASS_MAX_SECONDS:
        plan = await stills_editor.call(**ctx)
        resolve_beat_plan(plan, axis, backing, span_start, span_end)
        violations = coherence_violations(plan, backing)
        if violations:
            # ONE bounded adjudicated re-roll (repair_feedback 先例 — the
            # violations ride the same structured echo; never a blind retry).
            logger.info("beat_plan_coherence_repair", violations=len(violations))
            plan = await stills_editor.call(**ctx, repair_feedback="\n".join(violations))
            resolve_beat_plan(plan, axis, backing, span_start, span_end)
            remaining = coherence_violations(plan, backing)
            if remaining:
                logger.warning("beat_plan_coherence_residual", violations=remaining)
        return plan

    # Two-stage: outline → per-section beats with explicit handoff state.
    outline = await stills_editor_outline.call(**ctx)
    _resolve_sections(outline, axis, span_start, span_end)
    used_refs: list[str] = []
    last_motion = "none"
    last_emphasis = "none"
    all_beats: list[StillBeat] = []
    for section in outline.sections:
        if section.start is None or section.end is None or not section.image_refs:
            continue
        sec_words = [
            w for w in span_words
            if section.start <= float(w.get("start", 0)) and float(w.get("end", 0)) <= section.end + 0.05
        ]
        if not sec_words:
            continue
        handoff = {
            "role": section.role,
            "note": section.note,
            "used_image_refs": list(used_refs),
            "assigned_image_refs": section.image_refs,
            "last_motion": last_motion,
            "last_emphasis": last_emphasis,
            "span_start": round(section.start, 2),
            "span_end": round(section.end, 2),
        }
        part = await stills_editor.call(
            **{**ctx,
               "span_transcript": build_anchored_transcript(sec_words),
               "target_beats": min(len(section.image_refs), max(1, round((section.end - section.start) / _BEAT_TARGET_S))),
               "handoff": handoff},
        )
        resolve_beat_plan(part, axis, backing, section.start, section.end)
        for b in part.beats:
            used_refs.append(b.image_ref.strip().lower())
        if part.beats:
            last_motion = part.beats[-1].motion
            last_emphasis = part.beats[-1].emphasis
        all_beats.extend(part.beats)
    # Re-tile across section boundaries: each section's last beat holds
    # through the inter-section pause, ending at the next section's first
    # beat (the render timeline is contiguous — gaps are not renderable).
    for i in range(len(all_beats) - 1):
        if all_beats[i].end is not None and all_beats[i + 1].start is not None:
            all_beats[i].end = all_beats[i + 1].start
    plan = BeatPlan(arc=outline.arc, beats=all_beats)
    violations = coherence_violations(plan, backing)
    if violations:
        logger.warning("beat_plan_coherence_residual", violations=violations)
    return plan


def _resolve_sections(outline: BeatOutline, axis: _Axis, span_start: float, span_end: float) -> None:
    """Snap section markers onto the axis; chain ends across sections. A
    section whose marker won't resolve keeps start=None (the caller skips
    it — its assigned visuals simply go unused, never fabricated spans)."""
    sections = outline.sections
    if not sections:
        return
    sections[0].start = span_start
    for s in sections[1:]:
        hit = _locate([axis], s.marker, s.approx_start)
        if hit is not None:
            _, w0, _ = hit
            s.start = axis.word_start_s(w0)
    for i, s in enumerate(sections):
        if s.start is None:
            continue
        if i + 1 < len(sections):
            nxt = next(
                (sections[j].start for j in range(i + 1, len(sections)) if sections[j].start is not None),
                None,
            )
            s.end = _word_end_before(axis, nxt) if nxt is not None else span_end
        else:
            s.end = span_end


def resolve_beat_plan(
    plan: BeatPlan,
    axis: _Axis,
    backing: list[dict[str, Any]],
    span_start: float,
    span_end: float,
) -> BeatPlan:
    """Public wrapper (the caller's seam): refs → asset/url, markers → times."""
    _resolve_beats(plan.beats, axis, backing, span_start, span_end)
    return plan
