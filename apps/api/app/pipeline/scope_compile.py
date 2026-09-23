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

**R20 修订路由器 (iter-3, N-58)**: the Confirmed Scope Snapshot is not an
audit ornament — it is the revision router's substrate. ``compile_scope``
returns ``CompiledScope{tasks, plan_task_map}``: the map pins each plan to
its half-open task range in the compiled chain, and ``route_revision``
resolves a user pointing ("plan 2" / a plan_id / an @output pin) to the
plan's live canvas node set — plan → task slice → fill_key → nodes. The
fill-key projection MIRRORS the stamp-time law (``graph_fill``'s
``_fill_key_for_step`` + the compile's per-type ordinals + the autofork
pass): one law, two mirrors, cross-checked by the pure tests (the
``_document_frame`` ↔ ``layout.ts`` precedent). Legacy runs (no snapshot /
no map) and unresolvable targets degrade honestly — the caller's echo
points at the @output channel, never a silent guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.models.schemas import TaskItem
from app.pipeline.exploration_store import (
    STATE_DRAFT,
    STATE_READY,
    CandidateSetSpec,
    ContentPlanSpec,
    PlanOutput,
    SelectSpec,
)
from app.pipeline.graph import NODE_KINDS
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


@dataclass(frozen=True)
class CompiledScope:
    """The compile's full product (iter-3 E1, N-58): the executable chain
    plus the plan→task mapping (``plan_task_map``: plan_id → the plan's
    half-open task range ``[start, end)`` into ``tasks``). The map is born
    WITH the compile — never re-derived positionally afterwards (that
    derivation would drift the moment the vocabulary shifts)."""

    tasks: list[TaskItem]
    plan_task_map: dict[str, list[int]] = field(default_factory=dict)


def compile_scope(
    plans: list[Any],
    selects: list[Any],
    candidate_sets: list[Any],
    *,
    source_language: str | None,
    default_language: str = "en",
) -> CompiledScope:
    """Compile Content Plans into the Execution Scope (CompiledScope).

    Pure: rows in (read-only), tasks + the plan→task map out — no DB, no
    writes, no LLM. Raises ScopeCompileRejected on the first offense (the
    whole package dies together — a partial scope is never presented).
    """
    if not plans:
        raise ScopeCompileRejected("no content plans to compile")
    select_by_id = {str(n.id): n for n in selects}
    cset_by_id = {str(n.id): n for n in candidate_sets}

    tasks: list[TaskItem] = []
    plan_task_map: dict[str, list[int]] = {}
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

        plan_start = len(tasks)
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
        # Every compiled plan produced ≥1 task (outputs are non-empty by the
        # door's completeness check) — the range is never degenerate.
        plan_task_map[str(plan_row.id)] = [plan_start, len(tasks)]

    # The registry's own adjudication re-enters here (B3 上移): an illegal
    # chain (params / count bounds / task cap) is a compile rejection, so an
    # uncompilable plan never reaches the dock.
    try:
        validate_task_list(tasks)
    except ToolRejected as e:
        raise ScopeCompileRejected(str(e)) from e
    return CompiledScope(tasks=tasks, plan_task_map=plan_task_map)


def compile_plans(
    plans: list[Any],
    selects: list[Any],
    candidate_sets: list[Any],
    *,
    source_language: str | None,
    default_language: str = "en",
) -> list[TaskItem]:
    """The iter-2 calling shape, kept as a thin wrapper (E1: existing
    callers diff zero) — the mapping rides ``compile_scope``."""
    return compile_scope(
        plans,
        selects,
        candidate_sets,
        source_language=source_language,
        default_language=default_language,
    ).tasks


__all__ = [
    "CompiledScope",
    "CraftRevisionOps",
    "RevisionRoute",
    "ScopeCompileRejected",
    "assemble_craft_revision",
    "compile_plans",
    "compile_scope",
    "compose_revised_program",
    "decision_package_plans",
    "build_confirmed_scope",
    "route_revision",
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
    plan_task_map: dict[str, list[int]] | None = None,
) -> dict[str, Any]:
    """The Confirmed Scope Snapshot (ADR-089 §4 R20, iter-2 ④ — 销 P0-①):
    the immutable record of WHAT the user confirmed at the paid boundary,
    stamped onto ``run.context.confirmed_scope`` after the birthplace
    succeeds — the reading layer as docked (``plans``, empty on
    router-drafted docks — 读容忍), the compiled scope (the exact TaskItem
    chain the run was born with — hand edits included, since Start ships
    the confirmed intent verbatim), the quote shown at confirm time, and
    the confirmation channel (``confirmed_via``: "dock_pill" | "chat_reply",
    N-57). Pure: the caller owns the clock and the row write.

    Iter-3 E2: ``plan_task_map`` (plan_id → half-open task range, N-58)
    rides as an ADDITIVE key when the dock carried one — it is the revision
    router's mapping substrate. Snapshots without it (legacy runs /
    router-drafted docks) are read-tolerated: the router degrades honestly
    to the @output channel."""
    snapshot: dict[str, Any] = {
        "confirmation_id": confirmation_id,
        "confirmed_at": confirmed_at,
        "confirmed_via": confirmed_via,
        "plans": plans,
        "compiled_scope": [t.model_dump(mode="json") for t in tasks],
        "quote": quote,
    }
    if plan_task_map:
        snapshot["plan_task_map"] = plan_task_map
    return snapshot


# ---- R20 revision router (iter-3, N-58) ------------------------------------------

# The transform variants' fill-key form (graph_fill._fill_key_for_step reads
# these FIRST, before the slot form — the same order here).
_VARIANT_TOOLS = ("translate_clip", "dub_clip")


@dataclass(frozen=True)
class RevisionRoute:
    """The revision router's result (R20, N-58): the resolved live canvas
    node set, or an honest degrade whose reason the caller's loop echo
    carries (never a silent guess — the @output channel is the fallback
    seat). ``unmatched_keys`` = slice keys with no live node (a partial
    route is still usable — the caller executes the matched part and SAYS
    what it could not cover)."""

    status: Literal["ok", "degrade"]
    node_ids: tuple[str, ...] = ()
    plan_id: str | None = None
    unmatched_keys: tuple[str, ...] = ()
    reason: str | None = None


def _scope_fill_keys(tasks: list[TaskItem]) -> list[str]:
    """The stamp-time fill-key law projected onto a TaskItem chain.

    One law, two mirrors (cross-checked against ``compile_graph`` +
    ``graph_fill._fill_key_for_step`` by the pure tests): producers take
    ``kind#output_type#ordinal`` (the compile's per-type ordinal walk over
    the WHOLE chain — slice keys are cut AFTER the full walk), the
    translate/dub variants take ``kind#language#bilingual#fork`` with the
    compile's autofork pass replicated (≥2 variants in the chain flip every
    fork), deterministic processors / unknowns read as the bare kind.
    """
    autofork = sum(1 for t in tasks if t.tool in _VARIANT_TOOLS) >= 2
    ordinals: dict[str, int] = {}
    keys: list[str] = []
    for t in tasks:
        params = t.params or {}
        if t.tool in _VARIANT_TOOLS:
            keys.append(
                f"{t.tool}#{params.get('target_language') or ''}"
                f"#{bool(params.get('bilingual'))}"
                f"#{bool(params.get('fork')) or autofork}"
            )
            continue
        node_cls = NODE_KINDS.get(t.tool)
        if node_cls is None or (
            not node_cls.needs_plan_prelude and not node_cls.produces_outputs
        ):
            keys.append(t.tool)  # the bare-kind law (deterministic processors)
            continue
        output_type = node_cls.output_type or ""
        ordinal = ordinals.get(output_type, 0)
        ordinals[output_type] = ordinal + 1
        keys.append(f"{t.tool}#{output_type}#{ordinal}")
    return keys


def _degrade(reason: str) -> RevisionRoute:
    return RevisionRoute(status="degrade", reason=reason)


def _resolve_plan_ref(plans: list[dict[str, Any]], plan_ref: str) -> str | None:
    """序位词 / plan_id 双通道: a plan_id string matches verbatim; an ordinal
    ("2", "plan 2", "#2") indexes the reading layer's order (1-based — the
    dock's numbering). UUID-looking refs never fall through to ordinals."""
    ref = plan_ref.strip()
    for p in plans:
        if str(p.get("plan_id")) == ref:
            return ref
    digits = ref.lower().removeprefix("plan").strip().lstrip("#").strip()
    if digits.isdigit():
        ordinal = int(digits)
        if 1 <= ordinal <= len(plans):
            return str(plans[ordinal - 1].get("plan_id"))
    return None


def route_revision(
    snapshot: dict[str, Any] | None,
    nodes: list[Any],
    *,
    plan_ref: str | None = None,
    output_id: str | None = None,
) -> RevisionRoute:
    """R20 修订路由器 (ADR-089 §4, iter-3 S1): a user pointing → the target
    node set. Pure — the snapshot dict and the project's live graph nodes
    in, the route out; no DB, no writes.

    指认三通道 (E4): ``plan_ref`` (序位词 "2" or plan_id) resolves through
    the snapshot's ``plan_task_map`` → task slice → fill-keys → live nodes;
    ``output_id`` (@output pin) resolves straight to the producing node
    (``spec.output_ids``) — snapshot membership is best-effort context, the
    pin never needs the map. Legacy (no snapshot / no map), ambiguity, and
    vanished nodes all degrade honestly — the @output channel is the
    named fallback, never a guess."""
    if not (plan_ref or "").strip() and not (output_id or "").strip():
        return _degrade(
            "no target — name a plan (\"2\" or its id) or pin an output with @"
        )

    if output_id:
        node = next(
            (
                n
                for n in nodes
                if output_id
                in [str(o) for o in (n.spec or {}).get("output_ids") or []]
            ),
            None,
        )
        if node is None:
            return _degrade(
                f"output {output_id} is not on this project's canvas"
            )
        plan_id = _plan_owning_node(snapshot, nodes, node)
        return RevisionRoute(status="ok", node_ids=(str(node.id),), plan_id=plan_id)

    assert plan_ref is not None  # narrowed by the empty-target guard above
    if not snapshot:
        return _degrade(
            "this run predates the confirmed-scope snapshot — pin the output "
            "with @ instead"
        )
    plans = snapshot.get("plans") or []
    plan_task_map = snapshot.get("plan_task_map")
    compiled = snapshot.get("compiled_scope") or []
    if not plans or not plan_task_map:
        return _degrade(
            "the confirmed scope predates the plan→task map — pin the output "
            "with @ instead"
        )
    plan_id = _resolve_plan_ref(plans, plan_ref)
    if plan_id is None:
        return _degrade(
            f"\"{plan_ref}\" matches none of the {len(plans)} confirmed "
            f"plans (name 1..{len(plans)} or a plan_id)"
        )
    span = plan_task_map.get(plan_id)
    if (
        not isinstance(span, list)
        or len(span) != 2
        or span[1] <= span[0]
        or span[1] > len(compiled)
    ):
        return _degrade(
            "the plan's slice is outside the confirmed scope — pin the "
            "output with @ instead"
        )
    tasks = [TaskItem.model_validate(t) for t in compiled]
    keys = _scope_fill_keys(tasks)[span[0] : span[1]]
    by_key: dict[str, Any] = {}
    for n in nodes:
        fill_key = (n.spec or {}).get("fill_key")
        if fill_key:
            by_key[fill_key] = n
    matched: list[str] = []
    unmatched: list[str] = []
    for key in keys:
        node = by_key.get(key)
        if node is None:
            unmatched.append(key)
        elif str(node.id) not in matched:
            matched.append(str(node.id))
    if not matched:
        return _degrade(
            "the plan's compiled nodes are gone from the canvas — pin the "
            "output with @ instead"
        )
    return RevisionRoute(
        status="ok",
        node_ids=tuple(matched),
        plan_id=plan_id,
        unmatched_keys=tuple(unmatched),
    )


def _plan_owning_node(
    snapshot: dict[str, Any] | None, nodes: list[Any], node: Any
) -> str | None:
    """Best-effort context for an @output pin: which confirmed plan's slice
    contains the node's fill-key. None when the snapshot/map is absent or
    the node belongs to another scope — the pin itself already resolved."""
    if not snapshot:
        return None
    plan_task_map = snapshot.get("plan_task_map")
    compiled = snapshot.get("compiled_scope") or []
    if not plan_task_map or not compiled:
        return None
    fill_key = (node.spec or {}).get("fill_key")
    if not fill_key:
        return None
    try:
        keys = _scope_fill_keys([TaskItem.model_validate(t) for t in compiled])
    except ValueError:
        return None
    for plan_id, span in plan_task_map.items():
        if (
            isinstance(span, list)
            and len(span) == 2
            and 0 <= span[0] < span[1] <= len(keys)
            and fill_key in keys[span[0] : span[1]]
        ):
            return str(plan_id)
    return None


# ---- R19 消费侧 (iter-3 S3): craft revision ops assembly ----------------------

# prompt 消费族 (N-58 revise_output 的门控词表): nodes whose spec.prompt is
# a real PROGRAM the runtime's instruction channel steers (the four writers
# + the legacy LLM selector). Deterministic stations (cut_segments /
# translate_clip / dub_clip / materialize …) carry params, not programs —
# editing their display line would change nothing at runtime, so they are
# the honest-degrade family, never silently "revised".
_PROMPT_CONSUMING_TOOLS = frozenset(
    {
        "write_post",
        "write_article",
        "write_quotes",
        "write_carousel",
        "select_clips",
    }
)


@dataclass(frozen=True)
class CraftRevisionOps:
    """The assembled craft-revision ops (R19 continuation candidate):
    ``ops`` = one edit_prompt per prompt-consuming node + the closing bare
    run (the run op targets the edited nodes ∪ downstream — the wiring
    door's own closure); ``uncovered`` = the deterministic nodes' display
    labels the revision could NOT touch (the caller's disclosure line names
    them — a partial cover executes and SAYS what it skipped)."""

    ops: tuple[dict[str, Any], ...]
    uncovered: tuple[str, ...] = ()


def compose_revised_program(current: str, instruction: str) -> str:
    """The ONE prompt-composition seat for revise_output (R12: no LLM
    composition of wiring internals — the program is user-language and the
    revision clause is the user's own ask, restated): the current program
    absorbs the instruction verbatim as a trailing clause, so the node's
    program surface honestly shows what changed."""
    current = (current or "").strip()
    instruction = instruction.strip()
    if not current:
        return instruction
    if not instruction:
        return current
    return f"{current}\n\n{instruction}"


def assemble_craft_revision(
    nodes: list[Any], instruction: str
) -> CraftRevisionOps | None:
    """prompt 消费族门控 + ops 组装 (E4, pure): the routed node set →
    edit_prompt + run ops. None = NOTHING here consumes a program (the
    all-deterministic honest degrade — the caller's echo says what CAN
    change); a partial cover returns the editable ops plus the uncovered
    labels for the disclosure line."""
    editable: list[dict[str, Any]] = []
    uncovered: list[str] = []
    for n in nodes:
        spec = getattr(n, "spec", None) or {}
        if spec.get("tool") in _PROMPT_CONSUMING_TOOLS:
            editable.append(
                {
                    "op": "edit_prompt",
                    "node": str(n.id),
                    "prompt": compose_revised_program(
                        str(spec.get("prompt") or ""), instruction
                    ),
                }
            )
        else:
            uncovered.append(str(spec.get("summary") or getattr(n, "type", "?")))
    if not editable:
        return None
    return CraftRevisionOps(
        ops=(*editable, {"op": "run"}), uncovered=tuple(uncovered)
    )
