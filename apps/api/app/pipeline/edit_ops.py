"""edit_output's op assembly (ADR-090 §1/§4, E2 — S3).

The controlled vocabulary's mechanical core: ``kind`` enum × params pairing
law + the translation from product semantics (quoted words / seconds off
the end / a preset name / a title text) into ONE operations-registry op.
The LLM never writes op names, timestamps, or parameter internals — this
module is where its product-level ask becomes the registry's vocabulary.

Pure: the clip's render_spec dict + the resolver's span in, the op dict or
an EditRefusal out. Every refusal carries an answerable form (域拒绝回环 —
never guess, never hardcode a default).
"""

from dataclasses import dataclass
from typing import Any

from app.pipeline.clip_spec import _CAPTION_STYLE_PRESETS
from app.pipeline.edit_span import ResolvedSpan, SpanRefusal

# MVP 四件 (ADR-090 §1) — the only kinds the LLM may name; everything else
# is a domain refusal. Each kind consumes EXACTLY its param key (多给/缺给
# = 域拒绝, E2).
KIND_PARAMS: dict[str, str] = {
    "remove_range": "quote",
    "set_trim": "seconds",
    "set_caption_style": "style",
    "set_title": "title",
}

# A trimmed clip keeps at least this much kept content (a zero-length cut is
# a delete, not a trim — and never a silent one).
_MIN_KEPT_SECONDS = 0.5


@dataclass(frozen=True)
class EditRefusal:
    """A domain refusal with its answerable form (the loop rides this text
    back; the agent asks or re-routes — the user never sees a guess)."""

    feedback: str


def param_mismatch(kind: str, params: dict[str, Any]) -> str | None:
    """The kind × params pairing law (E2): exactly the kind's own key with a
    usable value; a missing key, an empty value, or any extra key is a
    refusal reason (None = paired cleanly)."""
    if kind not in KIND_PARAMS:
        return (
            f"unknown edit kind {kind!r} — the precise-edit vocabulary is "
            f"{', '.join(KIND_PARAMS)}; an open-ended change goes to "
            "revise_output, a deliverables change to revise_plan."
        )
    want = KIND_PARAMS[kind]
    given = {k for k, v in params.items() if v is not None and str(v).strip() != ""}
    extra = given - {want}
    if extra:
        return (
            f"{kind} takes only params.{want} — drop {', '.join(sorted(extra))} "
            "(one kind consumes exactly one param)."
        )
    if want not in given:
        return (
            f"{kind} needs params.{want} — relay the user's "
            + {
                "quote": "quoted words verbatim",
                "seconds": "seconds to take off the end",
                "style": "preset name (list_caption_styles has the enum)",
                "title": "title text verbatim",
            }[want]
            + "."
        )
    return None


def kept_range(spec: dict[str, Any]) -> tuple[float, float] | None:
    """The clip's current outer kept span (source seconds) — set_trim's base."""
    kept = [s for s in (spec.get("segments") or []) if not s.get("hidden")]
    if not kept:
        return None
    return float(kept[0].get("start") or 0.0), float(kept[-1].get("end") or 0.0)


def span_feedback(refusal: SpanRefusal) -> str:
    """The resolver refusal's answerable form (E3 域拒绝回环)."""
    if refusal.reason == "ambiguous":
        return (
            f"the quoted words appear {refusal.occurrences} times in the "
            "clip — ask the user WHICH occurrence (\"the second time\"), or "
            "for a longer quote that lands once. Never guess."
        )
    return (
        "the quoted words were not found in the clip's captions — ask the "
        "user to paste the exact line as it appears (or pin the moment "
        "with the selection quote). Never guess."
    )


def assemble_edit_op(
    kind: str,
    params: dict[str, Any],
    *,
    spec: dict[str, Any],
    span: ResolvedSpan | SpanRefusal | None = None,
) -> dict | EditRefusal:
    """Product semantics → ONE registry op. ``span`` is the resolver's
    verdict for remove_range (its quote already adjudicated — a SpanRefusal
    here passes straight through as the refusal)."""
    mismatch = param_mismatch(kind, params)
    if mismatch:
        return EditRefusal(mismatch)

    if kind == "remove_range":
        if isinstance(span, SpanRefusal):
            return EditRefusal(span_feedback(span))
        if span is None:
            return EditRefusal(
                "remove_range needs its range — resolve params.quote first."
            )
        return {"op": "remove_range", "params": {"start": span.start, "end": span.end}}

    if kind == "set_trim":
        current = kept_range(spec)
        if current is None:
            return EditRefusal("the clip has no kept content to trim.")
        seconds = float(params["seconds"])
        if seconds <= 0:
            return EditRefusal(
                "set_trim takes a POSITIVE seconds — how much to take off "
                "the end; lengthening a clip is not one of the precise edits."
            )
        start, end = current
        new_end = end - seconds
        if new_end - start < _MIN_KEPT_SECONDS:
            return EditRefusal(
                f"taking {seconds:g}s off a {end - start:.1f}s clip leaves "
                "nothing — say a smaller cut, or delete the moment with "
                "remove_range instead."
            )
        duration = ((spec.get("source") or {}).get("duration"))
        if duration is not None and new_end > float(duration):
            new_end = float(duration)
        return {"op": "set_trim", "params": {"start": start, "end": new_end}}

    if kind == "set_caption_style":
        style = str(params["style"]).strip()
        if style not in _CAPTION_STYLE_PRESETS:
            return EditRefusal(
                f"{style!r} is not a caption preset — the enum is "
                f"{', '.join(sorted(_CAPTION_STYLE_PRESETS))} (free-form "
                "layout stays out: L3). Offer the closest preset, never "
                "invent one."
            )
        return {"op": "set_caption_style", "params": {"preset": style}}

    # set_title
    return {
        "op": "set_title",
        "params": {"text": str(params["title"]).strip(), "enabled": True},
    }
