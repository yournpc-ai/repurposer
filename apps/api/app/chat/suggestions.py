"""建议谱系纯核 (ADR-099 §3/§4): the non-blocking suggestion form's pure
functions — record stamping, the directed stale verdict, and the
LLM-facing provenance note. NO database, NO LLM here (suite discipline):
the world reads live in ``app.chat.service.resolve_suggestion_note``,
which feeds these cores its findings.

- ``build_suggestion_records``: an accepted terminal call's options become
  the row's persisted interaction block — the option PLUS its provenance
  (id = the 1-based dock grammar, source_turn = the carrying row's own id,
  source_state = the stale-check snapshot). Code stamps provenance; the
  model only ever names direction + reason + evidence.
- ``suggestion_stale_reasons``: the stale verdict (ADR-099 §4 — 定向校验,
  零计数器): stale ⟺ ① the grounded assets are gone/failed ② new material
  understanding landed after source_turn ③ a plan docked or a run started
  after source_turn. Returns the NAMED reasons (never a bare bool — the
  note must say what moved).
- ``compose_suggestion_note``: the pick's provenance line for the next
  turn's context — a pick is a control event, not fresh input; a stale
  pick is re-grounding advice, never silent adoption and never silent
  dismissal.
"""

from app.models.schemas import SuggestionItem


def build_suggestion_records(
    items: list[SuggestionItem],
    source_turn: str,
    asset_ids: list[str],
) -> list[dict]:
    """The persisted interaction block for one assistant row: one record
    per option, provenance code-stamped (the model's payload carries only
    label/description/recommended). ``source_turn`` = the carrying row's
    own id — the suggestion_ref's lookup anchor; ``source_state.asset_ids``
    = the world snapshot the directed stale check re-reads at pick time.
    """
    return [
        {
            "id": str(index + 1),
            "label": item.label,
            "description": item.description,
            "recommended": item.recommended,
            "source_turn": source_turn,
            "source_state": {"asset_ids": asset_ids},
        }
        for index, item in enumerate(items)
    ]


def suggestion_stale_reasons(
    *,
    assets_missing: bool,
    assets_failed: bool,
    new_understanding: bool,
    plan_or_run_since: bool,
) -> list[str]:
    """The directed stale verdict's NAMED reasons (ADR-099 §4 — the three
    predicates are the whole stale definition; there is no fourth). Order
    is stable: material first, then understanding, then the offer's
    context. Empty = fresh."""
    reasons: list[str] = []
    if assets_missing:
        reasons.append("the material it drew on was deleted")
    if assets_failed:
        reasons.append("the material it drew on failed processing")
    if new_understanding:
        reasons.append("new material understanding landed since")
    if plan_or_run_since:
        reasons.append("a plan was docked or a run started since")
    return reasons


def compose_suggestion_note(label: str, stale_reasons: list[str]) -> str:
    """The pick's provenance note (model-facing, parenthesized — the
    stand-in line convention): the fresh pick names the control event (an
    accepted offer ≠ a brand-new request); the stale pick names WHAT moved
    and orders re-grounding — adoption is the user's, silence is banned
    (provenance 永不静默压过用户原话, and a stale candidate is never
    silently adopted)."""
    if not stale_reasons:
        return (
            f'(The user picked "{label}" from your earlier suggestion card '
            "— they are accepting that offered direction, not making a new "
            "request from scratch. Carry it forward accordingly.)"
        )
    reasons = "; ".join(stale_reasons)
    return (
        f'(The user picked "{label}" from an EARLIER suggestion card, but '
        f"the project has moved since that suggestion: {reasons}. Re-check "
        "it against the current state before acting — if it no longer "
        "fits, say so plainly and offer what fits now; never adopt it "
        "silently.)"
    )
