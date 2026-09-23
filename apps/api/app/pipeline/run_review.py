"""run_review — the closing audit's deterministic core (iter-3 S5, ADR-088
§8 R21 / N-58).

分词注记 (N-58): ``verify`` lives INSIDE the execution graph (the per-node
quality gate); ``run_review`` lives at the chat edge's trigger turn (the
closing review's fact substrate). This module is a PURE function seat — zero
LLM, zero DB: the caller (``app/chat/trigger_turn.py``) owns the IO and hands
in plain data (the run's Confirmed Scope Snapshot, the landed outputs, the
captured credits), and gets back the 兑现事实清单 (delivery-fact list):

- promised vs landed output families (type / language presence, clip counts);
- per-landed-clip facts: duration vs the cut range, caption-track existence,
  dub existence, the verify flag (``outputs.quality`` — passed /
  needs_human / never-verified), the render outcome (``outputs.render_status``
  — a render-FAILED row never counts toward the delivery tallies and fires
  the ``render_failed:<type>`` gap);
- the charge fact: captured credits vs the confirm-time quote range.

The review's prose law (facts first, ZERO subjective quality words, gaps
become suggestions) lives in the prompt (``trigger_system.j2``); this module
only guarantees the facts the prose may narrate are REAL. No autonomous
repair anywhere (P2 挂账 — the audit advises, never acts).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# The compiled tool → product-family mapping (the promise side). Transform
# tasks (translate_clip / dub_clip) promise TRACKS on the clips, never new
# outputs — they map to None here and surface in the track facts instead.
_WRITER_TOOL_TO_TYPE = {
    "write_post": "post",
    "write_article": "article",
    "write_quotes": "quotes",
    "write_carousel": "carousel",
}


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


@dataclass(frozen=True)
class ChargeFact:
    """实扣 vs 报价 (BILLING §7's closing mirror): the confirm-time quote
    range and the credits actually captured. ``captured=None`` = no capture
    rows found (legacy run) — the review says nothing about the charge."""

    quoted_low: int | None = None
    quoted_high: int | None = None
    captured: int | None = None


@dataclass(frozen=True)
class RunReview:
    """The delivery-fact list (结构化事实, zero prose): the promise derived
    from the confirmed scope, the landed facts, the deterministic gaps, and
    the charge. ``has_snapshot=False`` marks the legacy/no-scope run — the
    promise side then stays empty by DESIGN (never reconstructed)."""

    has_snapshot: bool
    promised_types: tuple[str, ...] = ()  # e.g. ("clip", "clip", "post:fr")
    promised_clip_count: int = 0
    promised_caption_languages: tuple[str, ...] = ()
    promised_dub: bool = False
    landed: tuple[LandedFact, ...] = ()
    gaps: tuple[str, ...] = ()
    needs_human: tuple[str, ...] = ()  # landed output types flagged by verify
    charge: ChargeFact = field(default_factory=ChargeFact)


def landed_fact(output: Any) -> LandedFact:
    """Extract one landed output's facts from its row (reads only — pure).
    Clip track facts read the BAKED render_spec (the sole render contract,
    ADR-016): the caption/translation tracks' presence and the dub block."""
    spec = getattr(output, "render_spec", None) or {}
    payload = getattr(output, "payload", None) or {}
    source_ref = getattr(output, "source_ref", None) or {}
    quality = getattr(output, "quality", None) or {}
    render_status = getattr(output, "render_status", None)
    is_clip = getattr(output, "type", None) == "clip"
    cut_range = None
    if is_clip:
        start = source_ref.get("start_seconds")
        end = source_ref.get("end_seconds")
        if isinstance(start, (int, float)) and isinstance(end, (int, float)):
            cut_range = (float(start), float(end))
    return LandedFact(
        output_type=str(getattr(output, "type", "") or "unknown"),
        language=getattr(output, "language", None),
        duration_s=(
            int(payload["duration"])
            if is_clip and isinstance(payload.get("duration"), (int, float))
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
    )


def _promised_from_scope(compiled_scope: list[dict[str, Any]]) -> dict[str, Any]:
    """The promise half, derived from the snapshot's compiled scope (the
    exact task chain the user confirmed): writer families (+ language),
    the clip count (cut_segments spans), caption language versions
    (translate_clip), the dub promise (dub_clip)."""
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


def compute_run_review(
    *,
    confirmed_scope: dict[str, Any] | None,
    landed: list[LandedFact],
    captured_credits: int | None,
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

    # A render-FAILED row is not delivered — it carries no playable file. It
    # stays visible in the landed tuple (its line carries render=FAILED) but
    # never counts toward the delivery tallies (live-acceptance red 2026-09-24:
    # "3 clips landed" narrated over a fan-out whose third render had failed).
    delivered = [f for f in landed if f.render != "failed"]
    landed_clips = [f for f in delivered if f.output_type == "clip"]
    landed_writers = [f for f in delivered if f.output_type != "clip"]

    gaps: list[str] = []
    # The render failure itself is a proven fact independent of any promise —
    # it fires even for legacy no-snapshot runs.
    for failed_type in sorted({f.output_type for f in landed if f.render == "failed"}):
        gaps.append(f"render_failed:{failed_type}")
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

    needs_human = sorted(
        {f.output_type for f in landed if f.quality == "needs_human"}
    )

    quote = (snapshot or {}).get("quote") or {}
    total = quote.get("total") if isinstance(quote, dict) else None
    quoted_low = quoted_high = None
    if isinstance(total, list) and len(total) == 2:
        quoted_low, quoted_high = int(total[0]), int(total[1])
    charge = ChargeFact(
        quoted_low=quoted_low, quoted_high=quoted_high, captured=captured_credits
    )
    # An over-quote capture is a fact the review must surface (BILLING §5's
    # honesty extends to the closing beat).
    if (
        captured_credits is not None
        and quoted_high is not None
        and captured_credits > quoted_high
    ):
        gaps.append(f"charge_over_quote:{captured_credits}>{quoted_high}")

    return RunReview(
        has_snapshot=snapshot is not None,
        promised_types=tuple(promised["types"]),
        promised_clip_count=promised["clip_count"],
        promised_caption_languages=tuple(promised["caption_languages"]),
        promised_dub=promised["dub"],
        landed=tuple(landed),
        gaps=tuple(gaps),
        needs_human=tuple(needs_human),
        charge=charge,
    )


# ---- the bounded prompt-feed rendering (context lines, never user copy) --------

_MAX_LANDED_LINES = 12
_MAX_PROMISED_LINES = 8
_MAX_GAP_LINES = 6


def review_fact_lines(review: RunReview) -> list[str]:
    """Render the fact list as the BOUNDED context block for the trigger
    turn (machine-structured English keys, the Graph-section precedent —
    the LLM narrates, never invents). Caps are structural: a mega-run's
    audit never floods the context."""
    lines: list[str] = []
    if review.has_snapshot and review.promised_types:
        promised = list(review.promised_types[: _MAX_PROMISED_LINES])
        extra = len(review.promised_types) - len(promised)
        line = "promised: " + ", ".join(promised) + (f" (+{extra} more)" if extra > 0 else "")
        if review.promised_caption_languages:
            line += "; caption versions: " + ", ".join(review.promised_caption_languages)
        if review.promised_dub:
            line += "; dub promised"
        lines.append(line)
    for f in review.landed[: _MAX_LANDED_LINES]:
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
        if f.quality:
            # The token is echoed by the narrator — keep it human words even
            # in the machine block (a raw `needs_human` leaked into the closing
            # prose as inline code in the 2026-09-24 live acceptance).
            parts.append(
                "verify=flagged-for-human-review"
                if f.quality == "needs_human"
                else f"verify={f.quality}"
            )
        if f.render == "failed":
            parts.append("render=FAILED")
        lines.append("- " + " ".join(parts))
    if len(review.landed) > _MAX_LANDED_LINES:
        lines.append(f"- … ({len(review.landed) - _MAX_LANDED_LINES} more landed outputs)")
    for gap in review.gaps[: _MAX_GAP_LINES]:
        lines.append(f"GAP {gap}")
    if review.needs_human:
        lines.append("verify flagged for human review: " + ", ".join(review.needs_human))
    charge = review.charge
    if charge.captured is not None:
        if charge.quoted_low is not None and charge.quoted_high is not None:
            lines.append(
                f"charge: captured {charge.captured} credits "
                f"(quoted {charge.quoted_low}–{charge.quoted_high})"
            )
        else:
            lines.append(f"charge: captured {charge.captured} credits (no quote on record)")
    return lines


__all__ = [
    "ChargeFact",
    "LandedFact",
    "RunReview",
    "compute_run_review",
    "landed_fact",
    "review_fact_lines",
]
