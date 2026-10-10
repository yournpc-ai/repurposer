"""Track-stack read-face projection (ADR-113 §4) — pure module.

The deliverable card's inspection face: below the full video, a VIDEO lane
(the kept segments as blocks) and a TEXT lane (the caption sentences as
blocks), both on the OUTPUT timeline. READ-ONLY inspection + seek — never
an orchestration surface (L3: no drag, no add/remove track, no transition
handles; the lanes are how the user READS the product, not edits it).

Derived at read time from the output's ``render_spec`` (the clip-spec stays
the sole render contract — ADR-016; this projection never leaks back into
it). Input shape is the row's JSONB dict (both stamping seats — /graph and
/results — decorate ORM rows whose render_spec is a plain dict).

Lane laws:

- ``video_lane``: the non-hidden segments in order, concatenated — the
  output clock is cumulative (``out`` times) while ``src`` times keep the
  SOURCE range (the cross-highlight's data: hovering a block lights the
  asset card's matching source interval — ADR-113 §6). Both ranges also
  carry preformatted labels (``src_label`` / ``out_label``).
- ``text_lane``: ``caption_track`` words (SOURCE time) are assigned to the
  kept segment their center falls in, grouped by the ONE cue law
  (``group_cues``) WITHIN each segment — a cut is a hard sentence break —
  then shifted to the output axis. Labels are preformatted ``m:ss–m:ss``
  (the client never formats time).
- ``ruler``: the NLE axis's scale — ticks at a nice-step density with
  labels preformatted (``None`` label = a minor tick; ADR-114 — the one
  time-formatting seat covers the scale too, the client draws geometry
  only). ``t=0`` and ``t=total`` always carry labels.
- ``modifiers``: presence only (``music`` = music.enabled, ``dub`` = dub
  non-null) — the modifier lanes' content face is a later batch.

Zero kept segments (or a non-clip render_spec) → None: the card renders no
track stack at all.
"""

from typing import Any, TypedDict

from app.tools.clips.transcript import fmt_cue_time, group_cues


class VideoLaneBlock(TypedDict):
    """One kept segment: its OUTPUT span + its SOURCE span + the source
    asset's id (the cross-highlight's address — ADR-113 §6; ``None`` when
    the spec carries no asset identity). ``src_label`` / ``out_label`` are
    the preformatted ``m:ss–m:ss`` ranges (the client never formats time)."""

    out_start: float
    out_end: float
    src_start: float
    src_end: float
    asset_id: str | None
    src_label: str
    out_label: str


class TextLaneBlock(TypedDict):
    """One caption sentence on the output timeline (label preformatted)."""

    out_start: float
    out_end: float
    text: str
    label: str


class RulerTick(TypedDict):
    """One scale tick on the output axis (ADR-114): ``label`` preformatted
    ``m:ss`` on the major steps, ``None`` on the minor ones."""

    t: float
    label: str | None


class TrackStack(TypedDict):
    video_lane: list[VideoLaneBlock]
    text_lane: list[TextLaneBlock]
    ruler: list[RulerTick]
    modifiers: dict[str, bool]


def _respaced(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Caption-track tokens → the ASR raw-token spacing convention.

    ``caption_track`` words are STRIPPED at birth (clip_spec), so the raw
    token's script spacing is gone: bare CJK tokens concatenate cleanly,
    but Latin tokens need their space back. Reconstruct the convention
    (a Latin-alnum-led token leads with a space) so the ONE grouping law's
    raw-join reads both scripts honestly — never a second grouping/join
    law. Token shape: ``{"word", "start", "end"}`` as ``group_cues`` reads.
    """
    out: list[dict[str, Any]] = []
    for w in words:
        if not isinstance(w, dict):
            continue
        text = str(w.get("text") or "").strip()
        if not text:
            continue
        token = " " + text if text[:1].isascii() and text[:1].isalnum() else text
        out.append(
            {
                "word": token,
                "start": float(w.get("start") or 0.0),
                "end": float(w.get("end") or 0.0),
            }
        )
    return out


def _ruler_ticks(total: float) -> list[RulerTick]:
    """The NLE axis's scale on the output timeline (ADR-114).

    Major step = the first nice value keeping ≤10 labeled ticks (a 45s
    clip reads 0:00–0:45 by fives; a 7min clip by minutes); minor = major/5
    (dropped when sub-second). ``t=0`` and ``t=total`` always labeled —
    the axis's ends never go unnamed. Labels preformatted (one seat).
    """
    if total <= 0:
        return []
    big = 600.0
    for step in (1.0, 2.0, 5.0, 10.0, 15.0, 30.0, 60.0, 120.0, 300.0, 600.0):
        big = step
        if total / step <= 10:
            break
    small = big / 5 if big / 5 >= 1 else big
    ticks: list[RulerTick] = []
    k = 0
    while True:
        t = k * small
        if t > total + 1e-6:
            break
        labeled = abs(t / big - round(t / big)) < 1e-6
        ticks.append(
            RulerTick(t=round(t, 3), label=fmt_cue_time(t) if labeled else None)
        )
        k += 1
    if ticks and abs(ticks[-1]["t"] - total) > 0.05:
        ticks.append(RulerTick(t=round(total, 3), label=fmt_cue_time(total)))
    elif ticks:
        # The end lands on a tick — it always carries its label.
        ticks[-1]["label"] = fmt_cue_time(total)
    return ticks


def build_track_stack(render_spec: Any) -> TrackStack | None:
    """Project one output's render_spec to its track stack (pure)."""
    if not isinstance(render_spec, dict):
        return None
    raw_segments = render_spec.get("segments")
    if not isinstance(raw_segments, list):
        return None
    kept: list[tuple[float, float, str | None]] = []
    # The homogeneous default: a segment without its own asset_id draws from
    # the spec's source (clip_spec ClipSegment.asset_id law); a hetero splice
    # (切 op) names its donor.
    source_asset_id = render_spec.get("asset_id")
    source_asset_id = str(source_asset_id) if source_asset_id else None
    for s in raw_segments:
        if not isinstance(s, dict) or s.get("hidden"):
            continue
        src_start = float(s.get("start") or 0.0)
        src_end = float(s.get("end") or 0.0)
        if src_end > src_start:
            seg_asset = s.get("asset_id") or source_asset_id
            kept.append((src_start, src_end, str(seg_asset) if seg_asset else None))
    if not kept:
        return None

    # The video lane: kept segments concatenated — out times cumulative.
    video_lane: list[VideoLaneBlock] = []
    windows: list[tuple[float, float, float, float]] = []  # src_start, src_end, out_start, out_end
    out_cursor = 0.0
    for src_start, src_end, seg_asset_id in kept:
        out_start = out_cursor
        out_end = out_cursor + (src_end - src_start)
        video_lane.append(
            VideoLaneBlock(
                out_start=round(out_start, 3),
                out_end=round(out_end, 3),
                src_start=src_start,
                src_end=src_end,
                asset_id=seg_asset_id,
                src_label=f"{fmt_cue_time(src_start)}–{fmt_cue_time(src_end)}",
                out_label=f"{fmt_cue_time(out_start)}–{fmt_cue_time(out_end)}",
            )
        )
        windows.append((src_start, src_end, out_start, out_end))
        out_cursor = out_end

    # The text lane: caption words → the segment their CENTER falls in →
    # the ONE cue law per segment (a cut is a hard sentence break) → shift
    # to the output axis (clamped at the segment bounds — a cue straddling
    # a cut reads within its kept span).
    text_lane: list[TextLaneBlock] = []
    words = _respaced(render_spec.get("caption_track") or [])
    by_segment: list[list[dict[str, Any]]] = [[] for _ in kept]
    for w in words:
        mid = (w["start"] + w["end"]) / 2
        for i, (src_start, src_end, _o_start, _o_end) in enumerate(windows):
            if src_start <= mid <= src_end:
                by_segment[i].append(w)
                break
    for i, segment_words in enumerate(by_segment):
        if not segment_words:
            continue
        src_start, src_end, out_start, _out_end = windows[i]
        cues, _truncated = group_cues(segment_words, raw_words=True)
        for cue in cues:
            if not cue["text"]:
                continue
            o_start = max(cue["start"], src_start) - src_start + out_start
            o_end = min(cue["end"], src_end) - src_start + out_start
            if o_end <= o_start:
                continue
            text_lane.append(
                TextLaneBlock(
                    out_start=round(o_start, 3),
                    out_end=round(o_end, 3),
                    text=cue["text"],
                    label=f"{fmt_cue_time(o_start)}–{fmt_cue_time(o_end)}",
                )
            )

    music = render_spec.get("music")
    modifiers = {
        "music": bool(isinstance(music, dict) and music.get("enabled")),
        "dub": bool(render_spec.get("dub")),
    }
    return TrackStack(
        video_lane=video_lane,
        text_lane=text_lane,
        ruler=_ruler_ticks(out_cursor),
        modifiers=modifiers,
    )
