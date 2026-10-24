"""run_review — the closing audit's deterministic core (iter-3 S5, ADR-088
§8 R21 / N-58).

分词注记 (N-58): ``verify`` lives INSIDE the execution graph (the per-node
quality gate); ``run_review`` lives at the chat edge's trigger turn (the
closing review's fact substrate). This module is a PURE function seat — zero
LLM, zero DB: the caller (``app/chat/trigger_turn.py``) owns the IO and hands
in plain data (the run's Confirmed Scope Snapshot, the landed outputs), and
gets back the 兑现事实清单 (delivery-fact list):

- promised vs landed output families (type / language presence, clip counts);
- per-landed-clip facts: duration vs the cut range, caption-track existence,
  dub existence, the verify flag (``outputs.quality`` — passed /
  needs_human / never-verified), the render outcome (``outputs.render_status``
  — a render-FAILED row never counts toward the delivery tallies and fires
  the ``render_failed:<type>`` gap), and the delivery pair (COMPLETED +
  ``files.video`` present — a payload-complete but file-missing clip never
  counts toward the tallies either, ADR-096 §4). Films additionally carry
  the narration pace adjustment when one fired (ADR-136 — bounded, zero-sum
  scene-second rebalancing, always disclosed, never hidden).

Spend is NEVER a closing-beat fact (2026-09-24 用户拍板 — Claude/Codex
parity: a finished task does not report what it cost; the wallet owns the
ledger, the speech owns the work). No charge lines, no over-quote gaps.

The review's prose law (one outcome branch, facts only, zero subjective
quality words) lives in ``delivery_system.j2``; this module only guarantees
the facts the prose may narrate are REAL. No autonomous repair anywhere
(P2 挂账 — the audit advises, never acts).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# The compiled tool → product-family mapping (the promise side). Transform
# tasks (translate_clip / dub_clip) promise TRACKS on the clips, never new
# outputs — they map to None here and surface in the track facts instead.
_WRITER_TOOL_TO_TYPE = {
    "write_post": "post",
    "write_article": "article",
    "write_quotes": "quotes",
    "write_carousel": "carousel",
    "launch_film": "film",
}

# Render-contracted row types (a render_status lifecycle + files.video prove
# delivery, ADR-096 §4): the clip family and the film family share the one
# render chain (ADR-119) — "delivered" means the same thing for both.
_RENDER_CONTRACTED = frozenset({"clip", "film"})


@dataclass(frozen=True)
class LandedFact:
    """One landed output's user-checkable facts (never a quality opinion)."""

    output_type: str
    language: str | None = None
    duration_s: int | None = None  # clips: the planned clip length
    cut_range_s: tuple[float, float] | None = None  # clips: the source span
    has_captions: bool | None = None  # clips only (None = not a clip)
    has_translation: bool | None = None  # clips only: the translated caption half
    dubbed: bool | None = None  # clips only: the cloned-voice dub track
    quality: str | None = None  # passed | needs_human | None (never verified)
    render: str | None = None  # pending | rendering | completed | failed | None (no render contract)
    has_file: bool | None = None  # clips only: files.video present (None = not a clip)
    narration_flex_s: float | None = None  # films: scene seconds rebalanced to fit the spoken lines (zero-sum, ADR-136)
    # films: the landed bed's presence, read off the baked render_spec (the
    # executed record's own entry). Three states, never two: True = a valid
    # spec carries the music block; False = a valid spec (scenes anchor
    # readable) carries none; None = the record is missing or too thin to
    # judge (unknown — never read as off/none) or not a film.
    music_bed: bool | None = None
    # films: the deterministic confirmed-version-vs-landed-spec comparison
    # (ADR-139 sibling law — d08af2af: the closing beat once claimed a drift
    # that the landed spec disproved; the facts block now carries the check).
    # Tuple of machine-key lines; None = not a film. The comparison reads the
    # CONFIRMED version stamped on the run's own context (never the current
    # live draft) and the landed row's baked render_spec — data, never pixels.
    film_check: tuple[str, ...] | None = None


@dataclass(frozen=True)
class RunReview:
    """The delivery-fact list (结构化事实, zero prose): the promise derived
    from the confirmed scope, the landed facts, and the deterministic gaps.
    ``has_snapshot=False`` marks the legacy/no-scope run — the promise side
    then stays empty by DESIGN (never reconstructed)."""

    has_snapshot: bool
    promised_types: tuple[str, ...] = ()  # e.g. ("clip", "clip", "post:fr")
    promised_clip_count: int = 0
    promised_caption_languages: tuple[str, ...] = ()
    promised_dub: bool = False
    landed: tuple[LandedFact, ...] = ()
    gaps: tuple[str, ...] = ()
    needs_human: tuple[str, ...] = ()  # landed output types flagged by verify


# ---- film: confirmed version vs landed spec (d08af2af lesson) ------------------
#
# The run's own context stamps the CONFIRMED version at Start
# (``prepared_storyboard`` + ``film_storyboard_params`` + version + content
# digest); the landed row's baked ``render_spec`` carries the executed scenes
# + the provenance digest. Comparing them is deterministic and needs no LLM.
# Scope discipline: only fields this run promised AND the spec carries
# semantically comparably — never a generic diff platform; the comparison is
# DATA-level (it never claims pixel verification of the rendered video).

# Per-scene content slots the spec carries verbatim from the board. focuses
# are EXCLUDED by construction (the board names element ids, the spec bakes
# resolved geometry — never comparable); narration text likewise (the spec
# carries the audio ref, not the line). A UI scene's page/shot selectors are
# excluded for the same reason: baking resolves them to url/image, so their
# absence from the spec is not drift. Their identity rides the storyboard
# digest instead of a shape-mismatched field comparison.
_SCENE_CONTENT_KEYS = (
    "type", "dark", "motion", "enter", "enter_start", "enter_interval",
    "enter_duration", "enter_hold_until", "motion_start", "motion_end",
    "exit_duration", "motion_scale", "align", "size", "accent_style",
    "enter_style",
    "lines", "word", "sub", "lead",
    "label", "roll", "title", "cards", "name", "tagline", "frame",
)
_SNAP_TOLERANCE_FRAMES = 6  # beat snap moves a boundary by at most ±0.2s @30fps
_MAX_DRIFT_LINES = 4


# Per-element keys the board↔spec comparison excludes (ADR-140): identity
# handles (element_id/id), the asset→key resolution (asset/src — that leg is
# the provenance digest's: the spec's src derives from the media universe
# this pure seat never reloads), and lines' derived shadow (copy_text).
# Every other key compares verbatim, null ≡ absent on both sides (the
# spec's null-stays-out convention).
_ELEMENT_COMPARE_EXCLUDED = frozenset(
    {"element_id", "id", "asset", "src", "copy_text"}
)


def film_delivery_check(
    confirmed: dict[str, Any] | None,
    spec: dict[str, Any],
    payload: dict[str, Any],
) -> tuple[str, ...]:
    """The film's confirmed-vs-landed adjudication (pure). Four honest
    states: MATCH (every leg ran and matched) / MATCH-ON-CHECKED-SCOPE (no
    proven drift, but some leg could not run — the unchecked items are
    NAMED, never rounded up to full consistency) / DRIFT (fields named) /
    not-comparable (missing information is NEVER a match).
    ``confirmed`` = the run context's stamp (board/params/version/digest);
    ``spec``/``payload`` = the landed row's.

    Timing leg asymmetry (honest scope): only an UNDERSHOOT beyond the beat
    snap tolerance is proven drift — beat snap moves ±6 frames and the
    structural floor only ever ADDS frames. But growth is NOT verified
    consistency either: an over-tolerance growth with no narration-flex
    record is an unexplained adjustment — it lands in the UNCHECKED scope
    (named per scene), never silently passes. A narration flex (ADR-136,
    separately disclosed) stands the whole leg down — timing then reads as
    unchecked, never as verified."""
    board = (confirmed or {}).get("board")
    scenes = board.get("scenes") if isinstance(board, dict) else None
    if not isinstance(scenes, list) or not scenes:
        return ("not-comparable:no-confirmed-storyboard",)
    spec_scenes = spec.get("scenes") if isinstance(spec, dict) else None
    if not isinstance(spec_scenes, list) or not spec_scenes:
        return ("not-comparable:no-landed-spec",)

    version = (confirmed or {}).get("version")
    head = f"confirmed=v{version}" if version is not None else "confirmed=?"
    drift: list[str] = []
    unchecked: list[str] = []

    landed_digest = (spec.get("provenance") or {}).get("storyboard_digest")
    confirmed_digest = (confirmed or {}).get("digest")
    if isinstance(landed_digest, str) and isinstance(confirmed_digest, str):
        digest_state = (
            "digest:match" if landed_digest == confirmed_digest else "digest:MISMATCH"
        )
        if landed_digest != confirmed_digest:
            drift.append("content digest differs from the confirmed version")
    else:
        digest_state = "digest:unavailable"
        unchecked.append("digest")

    if len(spec_scenes) != len(scenes):
        drift.append(f"scene count confirmed={len(scenes)} landed={len(spec_scenes)}")
    fps_raw = spec.get("fps")
    fps: float = float(fps_raw) if isinstance(fps_raw, (int, float)) else 30.0
    flex_fired = isinstance(payload.get("narration_flex"), dict)
    if flex_fired:
        unchecked.append("timing(narration-flex disclosed, leg stood down)")
    timing_field_gaps = 0
    timing_unverified: list[str] = []
    for i, (b, landed) in enumerate(zip(scenes, spec_scenes)):
        if not isinstance(b, dict) or not isinstance(landed, dict):
            timing_field_gaps += 1
            continue
        sid = b.get("scene_id") or f"s{i + 1}"
        for key in _SCENE_CONTENT_KEYS:
            bv, lv = b.get(key), landed.get(key)
            if bv is None and lv is None:
                continue
            if bv != lv:
                drift.append(f"{sid}.{key}")
        # Composite elements (ADR-140): the confirmed board's elements vs
        # the landed spec's, normalized — identity keys excluded (the
        # asset→key resolution is the provenance digest's leg, never
        # re-derived here).
        if b.get("type") == "composite" or landed.get("type") == "composite":
            b_els = b.get("elements")
            l_els = landed.get("elements")
            if not isinstance(b_els, list) or not isinstance(l_els, list):
                unchecked.append(f"{sid}.elements")
            elif len(b_els) != len(l_els):
                drift.append(f"{sid}.elements(count)")
            else:
                for ei, (be, le) in enumerate(zip(b_els, l_els)):
                    if not isinstance(be, dict) or not isinstance(le, dict):
                        unchecked.append(f"{sid}.elements[{ei}]")
                        continue
                    eid = be.get("element_id") or f"e{ei + 1}"
                    for key in set(be) | set(le):
                        if key in _ELEMENT_COMPARE_EXCLUDED:
                            continue
                        bv, lv = be.get(key), le.get(key)
                        if bv is None and lv is None:
                            continue
                        if bv != lv:
                            drift.append(f"{sid}.{eid}.{key}")
                if digest_state != "digest:match":
                    unchecked.append(
                        f"{sid}.elements(asset→key identity — no matching "
                        "digest to carry it)"
                    )
        if flex_fired:
            continue
        sec, frames = b.get("seconds"), landed.get("frames")
        if not (isinstance(sec, (int, float)) and isinstance(frames, (int, float))):
            timing_field_gaps += 1
            continue
        expected = round(sec * fps)
        if frames < expected - _SNAP_TOLERANCE_FRAMES:
            drift.append(f"{sid}.frames")
        elif frames > expected + _SNAP_TOLERANCE_FRAMES:
            # Growth beyond the snap window is a legal allocator adjustment
            # (structural floors) but UNEXPLAINED here (no flex record) —
            # unverified, never verified-consistent.
            timing_unverified.append(
                f"{sid} frames {frames} vs ~{expected} (growth beyond snap "
                "tolerance, no flex record — unverified)"
            )
    if timing_field_gaps:
        unchecked.append(f"timing({timing_field_gaps} scene(s) missing seconds/frames)")
    if timing_unverified:
        unchecked.append("timing(unverified growth)")

    params = (confirmed or {}).get("params") or {}
    aspect = params.get("aspect")
    if isinstance(aspect, str) and spec.get("aspect") != aspect:
        drift.append(f"aspect confirmed={aspect} landed={spec.get('aspect')}")
    mood = params.get("music_mood")
    if mood == "off" and spec.get("music"):
        drift.append("music landed but confirmed off")
    elif isinstance(mood, str) and mood != "off" and not spec.get("music"):
        drift.append("music confirmed but none landed")
    voiceover = params.get("voiceover")
    has_audio = any(isinstance(s, dict) and s.get("audio") for s in spec_scenes)
    if voiceover is False and has_audio:
        drift.append("audio landed but voiceover confirmed off")
    elif voiceover is True and not has_audio:
        board_has_narration = any(
            isinstance(s, dict) and str(s.get("narration") or "").strip()
            for s in scenes
        )
        if board_has_narration:
            drift.append("voiceover confirmed on but no narration audio landed")

    if drift:
        state = "DRIFT"
    elif unchecked:
        state = "MATCH-ON-CHECKED-SCOPE"
    else:
        state = "MATCH"
    lines = [f"{head} {digest_state} {state}"]
    lines.extend(f"drift:{d}" for d in drift[:_MAX_DRIFT_LINES])
    if len(drift) > _MAX_DRIFT_LINES:
        lines.append(f"drift:+{len(drift) - _MAX_DRIFT_LINES} more")
    if unchecked:
        lines.append("unchecked: " + "; ".join(unchecked))
    lines.extend(f"timing-note:{n}" for n in timing_unverified[:_MAX_DRIFT_LINES])
    return tuple(lines)


def landed_fact(output: Any, film_confirmed: dict[str, Any] | None = None) -> LandedFact:
    """Extract one landed output's facts from its row (reads only — pure).
    Clip track facts read the BAKED render_spec (the sole render contract,
    ADR-016): the caption/translation tracks' presence and the dub block.

    ``film_confirmed`` (film rows only) = the run context's stamped confirmed
    version (``prepared_storyboard`` + params + version + content digest —
    the version THIS run consumed, never the current live draft). Absent or
    unreadable → the check reports not-comparable; missing information never
    reads as a match."""
    spec = getattr(output, "render_spec", None) or {}
    # 配乐三态 (与读取工具 executes.py 同律): 只有可读的有效 spec(带
    # scenes 结构锚) 才能判断音乐配置 — 缺失(None)/空记录({})/半写记录
    # (无 scenes) 一律 unknown, 永不转成 none/off; 有效 spec 明确无 music
    # 块才报无配乐。配置了音乐 = spec 里写了床, 不等于试听确认有声。
    spec_substantive = isinstance(spec, dict) and isinstance(spec.get("scenes"), list)
    payload = getattr(output, "payload", None) or {}
    source_ref = getattr(output, "source_ref", None) or {}
    files = getattr(output, "files", None) or {}
    quality = getattr(output, "quality", None) or {}
    render_status = getattr(output, "render_status", None)
    is_clip = getattr(output, "type", None) == "clip"
    is_render_contracted = getattr(output, "type", None) in _RENDER_CONTRACTED
    cut_range = None
    if is_clip:
        start = source_ref.get("start_seconds")
        end = source_ref.get("end_seconds")
        if isinstance(start, (int, float)) and isinstance(end, (int, float)):
            cut_range = (float(start), float(end))
    flex = payload.get("narration_flex")
    return LandedFact(
        output_type=str(getattr(output, "type", "") or "unknown"),
        language=getattr(output, "language", None),
        duration_s=(
            int(payload["duration"])
            if is_render_contracted and isinstance(payload.get("duration"), (int, float))
            else None
        ),
        cut_range_s=cut_range,
        has_captions=(
            bool(spec.get("caption_enabled", True) and spec.get("caption_track"))
            if is_clip
            else None
        ),
        has_translation=bool(spec.get("translation_track")) if is_clip else None,
        dubbed=bool(spec.get("dub")) if is_clip else None,
        quality=(quality.get("status") if isinstance(quality, dict) else None),
        # Enum → its value, without importing the models layer (pure seat).
        render=getattr(render_status, "value", render_status),
        has_file=bool(files.get("video")) if is_render_contracted else None,
        # 窗口弹性披露 (ADR-136): the flex's borrowed seconds ride the
        # output payload — the closing review narrates the adjustment,
        # never hides it.
        narration_flex_s=(
            float(flex["borrowed_s"])
            if isinstance(flex, dict)
            and isinstance(flex.get("borrowed_s"), (int, float))
            else None
        ),
        music_bed=(
            (bool(spec.get("music")) if spec_substantive else None)
            if getattr(output, "type", None) == "film"
            else None
        ),
        film_check=(
            film_delivery_check(film_confirmed, spec, payload)
            if getattr(output, "type", None) == "film"
            else None
        ),
    )


def _promised_from_scope(compiled_scope: list[dict[str, Any]]) -> dict[str, Any]:
    """The promise half, derived from the snapshot's compiled scope (the
    exact task chain the user confirmed): writer families (+ language),
    the clip count (cut_segments spans), caption language versions
    (translate_clip), the dub promise (dub_clip), the film (+ its pinned
    spoken language — launch_film, 2026-10-15 语言钉参: an unpinned film
    promises no language, the storyboard declares it)."""
    types: list[str] = []
    clip_count = 0
    caption_languages: list[str] = []
    dub = False
    for task in compiled_scope:
        tool = str(task.get("tool") or "")
        params = task.get("params") or {}
        if tool in _WRITER_TOOL_TO_TYPE:
            language = params.get("language")
            types.append(
                f"{_WRITER_TOOL_TO_TYPE[tool]}:{language}" if language else _WRITER_TOOL_TO_TYPE[tool]
            )
        elif tool == "cut_segments":
            segments = params.get("segments")
            clip_count += len(segments) if isinstance(segments, list) else 1
            types.extend(["clip"] * (len(segments) if isinstance(segments, list) else 1))
        elif tool == "select_clips":  # legacy scope rows (read-tolerated)
            count = params.get("count")
            n = int(count) if isinstance(count, (int, float)) else 1
            clip_count += n
            types.extend(["clip"] * n)
        elif tool == "translate_clip":
            language = params.get("target_language")
            if language:
                caption_languages.append(str(language))
        elif tool == "dub_clip":
            dub = True
    return {
        "types": types,
        "clip_count": clip_count,
        "caption_languages": caption_languages,
        "dub": dub,
    }


def _is_delivered(fact: LandedFact) -> bool:
    """Whether the row is a user-deliverable product, not just a DB record.

    Render-contracted outputs need BOTH a completed render and the video
    file. Every other output family delivers through its ordinary payload.
    """
    return fact.render != "failed" and (
        fact.output_type not in _RENDER_CONTRACTED
        or (fact.render == "completed" and bool(fact.has_file))
    )


def output_is_delivered(output: Any) -> bool:
    """Shared by finalization and delivery review: a row is not a delivery."""
    return _is_delivered(landed_fact(output))


def compute_run_review(
    *,
    confirmed_scope: dict[str, Any] | None,
    landed: list[LandedFact],
) -> RunReview:
    """The audit's pure adjudication: promise vs landed, gaps named as
    stable snake_case keys (the prompt layer narrates them; the suggestion
    pills ground on them). Conservative by design — a gap is only what the
    data proves missing, never an inference."""
    snapshot = confirmed_scope if isinstance(confirmed_scope, dict) else None
    compiled = (snapshot or {}).get("compiled_scope") or []
    promised = (
        _promised_from_scope([t for t in compiled if isinstance(t, dict)])
        if compiled
        else {"types": [], "clip_count": 0, "caption_languages": [], "dub": False}
    )

    # A render-FAILED or not-ready row stays in the raw landed tuple so its
    # availability gap remains provable, but it is not a delivered product
    # and never enters the delivered tallies or "landed" prompt lines. Only
    # render_status COMPLETED + the video file present proves delivery for
    # the render-contracted clip/film family. Other output families deliver
    # through their ordinary payload.
    delivered = [f for f in landed if _is_delivered(f)]
    landed_clips = [f for f in delivered if f.output_type == "clip"]
    landed_writers = [f for f in delivered if f.output_type != "clip"]

    gaps: list[str] = []
    # The render failure itself is a proven fact independent of any promise —
    # it fires even for legacy no-snapshot runs.
    for failed_type in sorted({f.output_type for f in landed if f.render == "failed"}):
        gaps.append(f"render_failed:{failed_type}")
    for not_ready_type in sorted(
        {
            f.output_type
            for f in landed
            if f.output_type in _RENDER_CONTRACTED
            and f.render != "failed"
            and not _is_delivered(f)
        }
    ):
        gaps.append(f"output_not_ready:{not_ready_type}")
    if snapshot is not None and compiled:
        # Family presence: a promised writer family with zero landed rows.
        for entry in promised["types"]:
            if entry == "clip":
                continue
            ptype, _, plang = entry.partition(":")
            hit = any(
                f.output_type == ptype and (not plang or f.language == plang)
                for f in landed_writers
            )
            if not hit:
                gaps.append(f"missing_output:{entry}")
        # Clip count shortfall (a partially-failed fan-out reads here).
        if len(landed_clips) < promised["clip_count"]:
            gaps.append(f"clip_shortfall:{len(landed_clips)}/{promised['clip_count']}")
        # Track promises against the landed clips' baked specs.
        for language in promised["caption_languages"]:
            if not any(f.has_translation for f in landed_clips):
                gaps.append(f"missing_caption_version:{language}")
        if promised["dub"] and not any(f.dubbed for f in landed_clips):
            gaps.append("missing_dub")
    # Consistency review belongs to a DELIVERED film only. A failed or
    # not-ready render has no delivered piece to compare; its only user-facing
    # fact is the missing delivery, not an audit of a video the user never got.
    for f in delivered:
        if f.film_check and f.film_check[0].endswith(" DRIFT"):
            gaps.append("film_drift:film")

    needs_human = sorted(
        {f.output_type for f in delivered if f.quality == "needs_human"}
    )

    return RunReview(
        has_snapshot=snapshot is not None,
        promised_types=tuple(promised["types"]),
        promised_clip_count=promised["clip_count"],
        promised_caption_languages=tuple(promised["caption_languages"]),
        promised_dub=promised["dub"],
        landed=tuple(landed),
        gaps=tuple(gaps),
        needs_human=tuple(needs_human),
    )


# ---- the bounded prompt-feed rendering (context lines, never user copy) --------

_MAX_LANDED_LINES = 12
_MAX_PROMISED_LINES = 8
_MAX_GAP_LINES = 6


_AVAILABILITY_GAP_PREFIXES = (
    "render_failed:",
    "output_not_ready:",
    "missing_output:",
    "clip_shortfall:",
    "missing_caption_version:",
    "missing_dub",
)


def delivery_state(review: RunReview) -> str:
    """The ONE outcome the delivery turn must narrate.

    Availability alone selects the branch; quality flags and a delivered
    film's consistency notes do not turn a delivery into a partial one.
    ``unknown`` is the empty legacy shape, whose old plain-receipt fallback
    remains honest.
    """
    delivered = [f for f in review.landed if _is_delivered(f)]
    if not delivered:
        if review.landed or review.promised_types or review.gaps:
            return "failed"
        return "unknown"
    if any(
        gap.startswith(_AVAILABILITY_GAP_PREFIXES) for gap in review.gaps
    ):
        return "partial"
    return "delivered"


def review_fact_lines(review: RunReview) -> list[str]:
    """Render the fact list as the BOUNDED context block for the delivery
    turn (machine-structured English keys, the Graph-section precedent —
    the LLM narrates, never invents). Caps are structural: a mega-run's
    audit never floods the context."""
    state = delivery_state(review)
    delivered = [f for f in review.landed if _is_delivered(f)]
    if (
        state == "unknown"
        and not review.landed
        and not review.promised_types
        and not review.gaps
    ):
        return []
    lines: list[str] = [f"delivery={state}"]
    if review.has_snapshot and review.promised_types:
        promised = list(review.promised_types[: _MAX_PROMISED_LINES])
        extra = len(review.promised_types) - len(promised)
        line = "promised: " + ", ".join(promised) + (f" (+{extra} more)" if extra > 0 else "")
        if review.promised_caption_languages:
            line += "; caption versions: " + ", ".join(review.promised_caption_languages)
        if review.promised_dub:
            line += "; dub promised"
        lines.append(line)
    for f in delivered[: _MAX_LANDED_LINES]:
        parts = [f"landed {f.output_type}"]
        if f.language:
            parts.append(f"lang={f.language}")
        if f.duration_s is not None:
            parts.append(f"duration={f.duration_s}s")
        if f.cut_range_s is not None:
            parts.append(f"cut={f.cut_range_s[0]:.1f}–{f.cut_range_s[1]:.1f}s")
        if f.has_captions is not None:
            parts.append("captions=yes" if f.has_captions else "captions=NO")
        if f.has_translation:
            parts.append("translated=yes")
        if f.dubbed:
            parts.append("dubbed=yes")
        if f.narration_flex_s:
            # 窗口弹性披露 (ADR-136): scene timings rebalanced to fit the
            # spoken lines — a fact the narrator relays plainly, never a
            # defect, never silently skipped (展示=执行's bounded,
            # disclosed tolerance).
            parts.append(f"pace=adjusted(+{f.narration_flex_s:g}s narration room)")
        if f.output_type == "film":
            # The film bed's three states (the spec's own entry): bed = a
            # valid spec carries it, none = a valid spec carries none,
            # unknown = the record is missing/too thin — the closing beat
            # never has to guess, and never reads a gap as "no music".
            parts.append(
                "music=bed"
                if f.music_bed
                else ("music=none" if f.music_bed is False else "music=unknown")
            )
        if f.quality:
            # The token is echoed by the narrator — keep it human words even
            # in the machine block (a raw `needs_human` leaked into the closing
            # prose as inline code in the 2026-09-24 live acceptance).
            parts.append(
                "verify=flagged-for-human-review"
                if f.quality == "needs_human"
                else f"verify={f.quality}"
            )
        if f.film_check:
            # Confirmed-vs-landed (data-level, never pixels): the headline
            # rides the landed line ("confirmed=v3 digest:match MATCH" /
            # …DRIFT / not-comparable:…), the named drift fields follow as
            # detail lines.
            parts.append(f.film_check[0])
        lines.append("- " + " ".join(parts))
        if f.film_check:
            for detail in f.film_check[1:]:
                lines.append("  " + detail)
    if len(delivered) > _MAX_LANDED_LINES:
        lines.append(f"- … ({len(delivered) - _MAX_LANDED_LINES} more landed outputs)")
    for gap in review.gaps[: _MAX_GAP_LINES]:
        lines.append(f"GAP {gap}")
    if review.needs_human:
        lines.append("verify flagged for human review: " + ", ".join(review.needs_human))
    return lines


__all__ = [
    "LandedFact",
    "RunReview",
    "compute_run_review",
    "delivery_state",
    "landed_fact",
    "review_fact_lines",
]
