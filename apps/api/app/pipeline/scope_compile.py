"""scope_compile — the Content Plan → Execution Scope compiler (ADR-089 §1~§3, iter-2).

**编译移出 LLM (R12)**: the agent's vocabulary stays product-semantic
(candidates / selects / plans); turning plans into an executable task chain
is a DETERMINISTIC pure function, never an LLM duty. The compile consumes
the exploration world's already-validated facts:

- the Select's evidence pointer is dereferenced at COMPILE TIME (R7 — the
  exploration rows are read-only inputs; the door validated the range
  verbatim at birth, the compiler never re-judges);
- output families map to registry tools (``clip`` → ``cut_segments`` —
  NEVER ``select_clips``, the execution world has no second discoverer;
  the four writers for the text families);
- language versions / caption forms / dubbing continue as the existing
  transform capabilities (``translate_clip`` / ``dub_clip``), same law as
  the hand-drafted chains;
- the compiled chain re-enters the registry's own adjudication
  (``validate_task_list``) — "only registry-legal chains reach the dock"
  (B3) moves up to "only compilable plans are ever presented".

**座位 (R14 编译器半边)**: the compiler is a translator between two legal
world states, NOT a third write door — zero write privileges here; its
product lands through the existing paths (the dock payload / ``create_run``
consumes the same ``TaskItem[]``).

**域拒绝**: a plan that cannot compile (open self-check issues, an
unresolvable select pointer, a semantic contradiction, a registry
rejection) raises ``ScopeCompileRejected`` — the loop-echo family's third
sibling (WiringRejected / ExplorationRejected): the rejection IS the repair
signal, never a 500, and an uncompilable plan never reaches the dock.

Quote (ADR-089 §7): the quotation is the EXISTING fold mechanism applied to
the compiled chain at the dock seat (``_safe_task_estimate``) — the inputs
stand on plan facts (exact ranges → render units), never on LLM guesses.
"""

from __future__ import annotations

from typing import Any

from app.models.schemas import TaskItem
from app.pipeline.exploration_store import (
    STATE_DRAFT,
    STATE_READY,
    CandidateSetSpec,
    ContentPlanSpec,
    PlanOutput,
    SelectSpec,
)
from app.tools import ToolRejected, validate_task_list

# The artifact states a compile accepts (ADR-088 §3): ready at birth, or
# revised by the revision verb (iter-2 ⑦ — a revised plan re-compiles and
# re-docks). draft = the self-check found gaps (reject with the issues);
# compiled/superseded = lifecycle leftovers, never re-compiled by a new
# decision package.
_COMPILABLE_STATES = frozenset({STATE_READY, "revised"})

# Product-semantic output kind → registry tool (R12: the compiler owns this
# mapping; the agent never names tools). ``clip`` deliberately absent — its
# seat is cut_segments with per-language transform continuations.
_WRITER_TOOLS = {
    "post": "write_post",
    "article": "write_article",
    "quotes": "write_quotes",
    "carousel": "write_carousel",
}


class ScopeCompileRejected(ValueError):
    """The compiler's domain rejection (WiringRejected / ExplorationRejected
    同族, N-57): the whole compile dies together; the loop echo carries the
    reason back so the agent repairs the PLAN and re-proposes."""


def _differs(language: str, source_language: str | None) -> bool:
    """The same-language judgment (morph.py's guardrail law): unknown source
    stays silent (treated as different — the user's named language version is
    honored; the runtime same-language guard remains the backstop)."""
    return language.strip().lower() != (source_language or "").strip().lower()


def _compile_clip_output(
    output: PlanOutput,
    span_payload: dict[str, Any],
    *,
    source_language: str | None,
) -> list[TaskItem]:
    """clip → cut_segments (the range rides verbatim) + transform
    continuations for a named language version (dub re-voices, translate
    re-captions — transform semantics, never birth params, N-56)."""
    cut_params: dict[str, Any] = {
        "segments": [{"start": span_payload["start"], "end": span_payload["end"]}],
        "asset_id": span_payload.get("asset_id"),
    }
    if output.aspect:
        cut_params["aspect"] = output.aspect
    tasks = [
        TaskItem(
            tool="cut_segments",
            params={k: v for k, v in cut_params.items() if v is not None},
        )
    ]
    language = output.language
    if not language or not _differs(language, source_language):
        return tasks
    if output.dub:
        tasks.append(
            TaskItem(tool="dub_clip", params={"target_language": language})
        )
        return tasks
    if output.caption_mode == "source_only":
        raise ScopeCompileRejected(
            "clip output: source_only captions conflict with a target "
            f"language ({language}) — drop the language version or pick "
            "bilingual / target_only captions"
        )
    tasks.append(
        TaskItem(
            tool="translate_clip",
            params={
                "target_language": language,
                "bilingual": output.caption_mode == "bilingual",
            },
        )
    )
    return tasks


def _compile_writer_output(
    output: PlanOutput,
    span_payload: dict[str, Any],
    *,
    default_language: str,
) -> TaskItem:
    """post / article / quotes / carousel → the writer with the span-narrowed
    source (iter-2 ②) and the plan's per-output brief riding the existing
    ``focus`` field (semantic identity)."""
    params: dict[str, Any] = {
        "language": output.language or default_language,
        "source_span": span_payload,
    }
    if output.brief and output.brief.strip():
        params["focus"] = output.brief.strip()
    return TaskItem(tool=_WRITER_TOOLS[output.kind], params=params)


def compile_plans(
    plans: list[Any],
    selects: list[Any],
    candidate_sets: list[Any],
    *,
    source_language: str | None,
    default_language: str = "en",
) -> list[TaskItem]:
    """Compile Content Plans into the Execution Scope (a TaskItem list).

    Pure: rows in (read-only), tasks out — no DB, no writes, no LLM. Raises
    ScopeCompileRejected on the first offense (the whole package dies
    together — a partial scope is never presented).
    """
    if not plans:
        raise ScopeCompileRejected("no content plans to compile")
    select_by_id = {str(n.id): n for n in selects}
    cset_by_id = {str(n.id): n for n in candidate_sets}

    tasks: list[TaskItem] = []
    for plan_row in plans:
        # The door stamps draft issues INTO the spec payload (additive, its
        # own schema forbids the key) — pop before strict validation (读容忍
        # on the door's own stamp, never a silent drop: a draft rejects WITH
        # its issues below).
        raw = dict(plan_row.spec or {})
        open_issues = raw.pop("issues", None)
        spec = ContentPlanSpec.model_validate(raw)
        state = getattr(plan_row, "state", STATE_DRAFT)
        if state == STATE_DRAFT:
            raise ScopeCompileRejected(
                f"plan {plan_row.id} still has open gaps: "
                + ("; ".join(open_issues) if open_issues else "incomplete outputs")
                + " — fix the plan and re-propose it"
            )
        if state not in _COMPILABLE_STATES:
            raise ScopeCompileRejected(
                f"plan {plan_row.id} is {state} — only ready or revised "
                "plans compile"
            )

        select_row = select_by_id.get(spec.select_id)
        if select_row is None:
            raise ScopeCompileRejected(
                f"plan {plan_row.id}: its select {spec.select_id} is not in "
                "this journey's selects"
            )
        sspec = SelectSpec.model_validate(select_row.spec)
        cset_row = cset_by_id.get(sspec.candidate_set_id)
        if cset_row is None:
            raise ScopeCompileRejected(
                f"plan {plan_row.id}: the candidate set "
                f"{sspec.candidate_set_id} is not in this journey"
            )
        cspec = CandidateSetSpec.model_validate(cset_row.spec)
        if not (0 <= sspec.member_index < len(cspec.members)):
            raise ScopeCompileRejected(
                f"plan {plan_row.id}: member {sspec.member_index} is outside "
                f"the candidate set's {len(cspec.members)} members"
            )
        member = cspec.members[sspec.member_index]
        # The R7 pointer dereference — the door validated this range verbatim
        # at the candidate set's birth; the compiler never re-judges it.
        span_payload = {
            "start": member.start,
            "end": member.end,
            "asset_id": cspec.asset_id,
        }

        for output in spec.outputs:
            if output.kind == "clip":
                tasks.extend(
                    _compile_clip_output(
                        output, span_payload, source_language=source_language
                    )
                )
            elif output.kind in _WRITER_TOOLS:
                tasks.append(
                    _compile_writer_output(
                        output, span_payload, default_language=default_language
                    )
                )
            else:  # unreachable — the door's Literal gates the vocabulary
                raise ScopeCompileRejected(
                    f"plan {plan_row.id}: output kind {output.kind!r} has no "
                    "compile mapping"
                )

    # The registry's own adjudication re-enters here (B3 上移): an illegal
    # chain (params / count bounds / task cap) is a compile rejection, so an
    # uncompilable plan never reaches the dock.
    try:
        validate_task_list(tasks)
    except ToolRejected as e:
        raise ScopeCompileRejected(str(e)) from e
    return tasks


__all__ = [
    "ScopeCompileRejected",
    "compile_plans",
    "decision_package_plans",
    "build_confirmed_scope",
]


def decision_package_plans(plans: list[Any]) -> list[dict[str, Any]]:
    """The decision package's READING layer (ADR-089 §4 R16, iter-2 ③):
    Content Plan rows → the dock payload's user-safe plan summaries
    (``plans`` key, N-57) — plan_id / title / outputs / state, the LLM-named
    product semantics (展示文案二源律). The compiled TaskItem[] (the EVIDENCE
    layer) and the quote (费用语义) ride their own seats on the same dock.
    The door's additive ``issues`` stamp is popped before strict validation
    (the compile seat's same read tolerance)."""
    package: list[dict[str, Any]] = []
    for row in plans:
        raw = dict(row.spec or {})
        open_issues = raw.pop("issues", None)
        spec = ContentPlanSpec.model_validate(raw)
        entry: dict[str, Any] = {
            "plan_id": str(row.id),
            "title": spec.title,
            "state": getattr(row, "state", STATE_READY),
            "outputs": [
                o.model_dump(mode="json", exclude_none=True) for o in spec.outputs
            ],
        }
        if open_issues:
            entry["issues"] = open_issues
        package.append(entry)
    return package


def build_confirmed_scope(
    *,
    confirmation_id: str,
    confirmed_at: str,
    confirmed_via: str,
    plans: list[dict[str, Any]],
    tasks: list[TaskItem],
    quote: dict[str, Any] | None,
) -> dict[str, Any]:
    """The Confirmed Scope Snapshot (ADR-089 §4 R20, iter-2 ④ — 销 P0-①):
    the immutable record of WHAT the user confirmed at the paid boundary,
    stamped onto ``run.context.confirmed_scope`` after the birthplace
    succeeds — the reading layer as docked (``plans``, empty on
    router-drafted docks — 读容忍), the compiled scope (the exact TaskItem
    chain the run was born with — hand edits included, since Start ships
    the confirmed intent verbatim), the quote shown at confirm time, and
    the confirmation channel (``confirmed_via``: "dock_pill" | "chat_reply",
    N-57). Pure: the caller owns the clock and the row write."""
    return {
        "confirmation_id": confirmation_id,
        "confirmed_at": confirmed_at,
        "confirmed_via": confirmed_via,
        "plans": plans,
        "compiled_scope": [t.model_dump(mode="json") for t in tasks],
        "quote": quote,
    }
