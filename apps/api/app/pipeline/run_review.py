"""Build deterministic delivery facts from the confirmed video version and landed Outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_RENDER_CONTRACTED = frozenset({"video"})


@dataclass(frozen=True)
class LandedFact:
    """One landed output's user-checkable facts (never a quality opinion)."""

    output_type: str
    video_version_matches: bool | None = None
    language: str | None = None
    duration_s: int | None = None
    quality: str | None = None
    render: str | None = None
    has_file: bool | None = None
    music_bed: bool | None = None


@dataclass(frozen=True)
class RunReview:
    """The delivery-fact list (结构化事实, zero prose): the promise derived
    from the confirmed scope, the landed facts, and the deterministic gaps.
    ``has_snapshot=False`` marks the legacy/no-scope run — the promise side
    then stays empty by DESIGN (never reconstructed)."""

    has_snapshot: bool
    promised_types: tuple[str, ...] = ()
    landed: tuple[LandedFact, ...] = ()
    gaps: tuple[str, ...] = ()
    needs_human: tuple[str, ...] = ()  # landed output types flagged by verify


def landed_fact(output: Any, *, video_confirmed: dict[str, Any] | None = None) -> LandedFact:
    """Read landed facts and compare video provenance with the confirmed version."""
    spec = getattr(output, "render_spec", None) or {}
    output_type = getattr(output, "type", None)
    video_spec_substantive = (
        isinstance(spec, dict)
        and spec.get("family") == "video"
        and isinstance(spec.get("tracks"), list)
    )
    video_music_bed = None
    if video_spec_substantive:
        video_music_bed = any(
            isinstance(track, dict)
            and track.get("kind") == "audio"
            and track.get("role") == "music"
            and bool(track.get("clips"))
            for track in spec["tracks"]
        )
    payload = getattr(output, "payload", None) or {}
    files = getattr(output, "files", None) or {}
    quality = getattr(output, "quality", None) or {}
    render_status = getattr(output, "render_status", None)
    is_render_contracted = getattr(output, "type", None) in _RENDER_CONTRACTED
    video_matches = None
    if getattr(output, "type", None) == "video":
        pinned = {
            "composition_id": str(getattr(output, "composition_id", "") or ""),
            "composition_version_id": str(getattr(output, "composition_version_id", "") or ""),
            "content_digest": payload.get("composition_digest"),
        }
        video_matches = bool(
            all(pinned.values()) and spec.get("family") == "video"
            and spec.get("provenance") == pinned
            and (video_confirmed is None or video_confirmed == pinned)
        )
    return LandedFact(
        output_type=str(getattr(output, "type", "") or "unknown"),
        video_version_matches=video_matches,
        language=(payload.get("content_language") if getattr(output, "type", None) == "video"
                  else getattr(output, "language", None)),
        duration_s=(
            int(payload["duration"])
            if is_render_contracted and isinstance(payload.get("duration"), (int, float))
            else None
        ),
        quality=(quality.get("status") if isinstance(quality, dict) else None),
        # Enum → its value, without importing the models layer (pure seat).
        render=getattr(render_status, "value", render_status),
        has_file=bool(files.get("video")) if is_render_contracted else None,
        music_bed=video_music_bed if output_type == "video" else None,
    )


def _is_delivered(fact: LandedFact) -> bool:
    """Whether the row is a user-deliverable product, not just a DB record.

    Render-contracted outputs need BOTH a completed render and the video
    file. Every other output family delivers through its ordinary payload.
    """
    return fact.video_version_matches is not False and fact.render != "failed" and (
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
    promised = ("video",) if any(
        isinstance(task, dict) and task.get("tool") == "produce_video"
        for task in compiled
    ) else ()
    delivered = [f for f in landed if _is_delivered(f)]

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
    if promised and not any(f.output_type == "video" for f in delivered):
        gaps.append("missing_output:video")
    needs_human = sorted(
        {f.output_type for f in delivered if f.quality == "needs_human"}
    )

    return RunReview(
        has_snapshot=snapshot is not None,
        promised_types=promised,
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
        lines.append(line)
    for f in delivered[: _MAX_LANDED_LINES]:
        parts = [f"landed {f.output_type}"]
        if f.language:
            parts.append(f"lang={f.language}")
        if f.duration_s is not None:
            parts.append(f"duration={f.duration_s}s")
        if f.output_type == "video":
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
        lines.append("- " + " ".join(parts))
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
