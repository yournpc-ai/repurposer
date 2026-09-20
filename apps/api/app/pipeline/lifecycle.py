"""Lifecycle Projection (ADR-087 §2) — the server-named, read-only
lifecycle stamp. One truth, many readers: Transport carries the stamp on
the results/graph responses; Presentation reacts to it and never derives
lifecycle from artifact existence.

Direction (ADR-087 §6, Phase 1 brief §Preflight P9): the projection reads
only already-defined Domain facts with a declared owner — it invents no
reasoning of its own and is never a second heuristic center:

- Agent Interface facts (the docked plan row) arrive as *parameters* —
  the transport caller fetches them through chat's public read protocol
  (``find_conversation`` / ``latest_pending_question`` / ``is_pending_plan``),
  so this module never imports chat (pipeline→chat stays Phase 5's debt,
  not ours).
- Pipeline facts (asset states / active run / chain re-adjudication) are
  gathered here through the same functions the write gates already use
  (``validate_task_list`` / ``_check_transform_targets`` / the birthplace
  ``Requirement`` predicates / ``has_active_run``).

Two halves:

- ``compute_lifecycle(facts)`` — the PURE core. Plain data in, stamp out;
  the whole T1~T15 test matrix runs against it with no DB.
- ``project_lifecycle(db, project, ...)`` — the gatherer. Resolves the
  pipeline-owned facts, then delegates to the pure core.

Rulings baked in (Phase 1 brief §Preflight P7, 2026-09-19):

- U1: blockers are first-class reasons — ``material_failed`` never
  collapses into a generic not-ready.
- U2: MATERIAL_READY(P) is plan-scoped by *definition* (the inputs the
  docked chain declares via its nodes' ``requires``). The asset *set* is
  resolved project-scope in v1 — a legacy compatibility resolver (the
  worker claim gate shares that scope), not the concept definition.
- U4: CONFIRMATION_READY = PLAN_READY ∧ ConfirmationScopeReady
  ∧ ChargeSemanticsReady ∧ NoActiveConflictingRun — four independent
  conjuncts on the stamp, one composition point. Payload-existence is
  never the authority; the stamp reads field-level facts.
- U5: unknown source language on a transform chain = a required content
  fact missing (``language_unknown``), not an adjudication failure;
  adjudication failure (``chain_adjudication_failed``) is reserved for a
  KNOWN language breaking the same-language rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Asset
from app.pipeline.graph import (
    MEDIA,
    NODE_KINDS,
    PERSONA_PHOTO,
    TRANSCRIPT,
    VOICEPRINT,
)
from app.pipeline.morph import _check_transform_targets, _faced_source_languages
from app.pipeline.orchestrator import has_active_run
from app.tools import ToolRejected, validate_task_list

if TYPE_CHECKING:
    from app.models.tables import Message, Project

# The birthplace's own Requirement declarations by key (pipeline.graph) —
# the projection reads the node's own knowledge, never a parallel table.
_REQUIREMENT_BY_KEY = {
    r.key: r for r in (MEDIA, TRANSCRIPT, PERSONA_PHOTO, VOICEPRINT)
}

# Blocker vocabulary (the stamp's reason channel — U1). Order in the
# `blockers` list follows the predicate evaluation order below.
BLOCKER_MATERIAL_PENDING = "material_pending"
BLOCKER_MATERIAL_FAILED = "material_failed"
BLOCKER_CONTENT_MISSING = "content_missing"
BLOCKER_LANGUAGE_UNKNOWN = "language_unknown"
BLOCKER_CHAIN_ADJUDICATION_FAILED = "chain_adjudication_failed"
BLOCKER_PENDING_PREREQUISITE = "pending_prerequisite"
BLOCKER_ACTIVE_RUN = "active_run"

# Lifecycle states (ADR-087 §2 — PREPARING is the default).
STATE_PREPARING = "preparing"
STATE_PLAN_READY = "plan_ready"
STATE_CONFIRMATION_READY = "confirmation_ready"
STATE_RUNNING = "running"


@dataclass(frozen=True)
class LifecycleFacts:
    """The projection's input facts — plain data, each with a declared
    owner (Phase 1 brief §Preflight P9). The gatherer resolves them; the
    pure core never touches a session."""

    # Agent Interface facts (docked plan row, caller-fetched)
    has_pending_plan: bool = False
    prerequisite_pending: bool = False
    plan_tasks: tuple[dict[str, Any], ...] = ()
    plan_prose: str = ""
    estimate_total: tuple[int, int] | None = None
    # Pipeline facts (asset states / requirements / adjudication / run)
    assets_pending: bool = False
    assets_failed: bool = False
    missing_inputs: tuple[str, ...] = ()
    language_unknown: bool = False
    adjudication_error: str | None = None
    active_run: bool = False
    # Registry-resolved chain requirement keys (media / transcript / …),
    # pre-computed by the gatherer from the same NODE_KINDS declarations
    # the birthplace ∀-check reads.
    required_inputs: tuple[str, ...] = ()


@dataclass(frozen=True)
class LifecycleStamp:
    """The projection's output contract (Phase 1 brief §Preflight P4).

    The four CONFIRMATION_READY conjuncts are independent fields; the
    single composition point is ``confirmation_ready`` (门禁三: never one
    boolean). ``state`` is the presentation rollup — the booleans are the
    truth, ``state`` merely names the furthest stage reached."""

    state: str
    material_ready: bool
    plan_ready: bool
    confirmation_scope_ready: bool
    charge_semantics_ready: bool
    no_active_conflicting_run: bool
    confirmation_ready: bool
    blockers: tuple[str, ...] = ()
    charge_known: tuple[int, int] | None = None
    charge_deferred: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "material_ready": self.material_ready,
            "plan_ready": self.plan_ready,
            "confirmation_scope_ready": self.confirmation_scope_ready,
            "charge_semantics_ready": self.charge_semantics_ready,
            "no_active_conflicting_run": self.no_active_conflicting_run,
            "confirmation_ready": self.confirmation_ready,
            "blockers": list(self.blockers),
            "charge": {
                "known": list(self.charge_known) if self.charge_known else None,
                "deferred": self.charge_deferred,
            },
        }


def compute_lifecycle(facts: LifecycleFacts) -> LifecycleStamp:
    """The pure predicate family (ADR-087 §2 five states + U4 four
    conjuncts). No DB, no LLM, no clock — the whole test matrix runs here.

    Evaluation order == blocker emission order (deterministic stamps)."""
    blockers: list[str] = []

    # --- MATERIAL_READY(P): plan-scoped required inputs (U2) -----------
    # Status facts only gate when the chain actually consumes assets —
    # a chain with no media/transcript requirement doesn't wait on upload
    # processing it will never read.
    chain_consumes_assets = bool(
        {"media", "transcript"} & set(facts.required_inputs)
    )
    if facts.has_pending_plan and chain_consumes_assets:
        if facts.assets_pending:
            blockers.append(BLOCKER_MATERIAL_PENDING)
        if facts.assets_failed:
            blockers.append(BLOCKER_MATERIAL_FAILED)
    if facts.has_pending_plan and facts.missing_inputs:
        blockers.append(BLOCKER_CONTENT_MISSING)
    if facts.has_pending_plan and facts.language_unknown:
        # U5: a required content fact (the faced source language) is
        # missing — NOT an adjudication failure.
        blockers.append(BLOCKER_LANGUAGE_UNKNOWN)

    material_ready = facts.has_pending_plan and not (
        (chain_consumes_assets and (facts.assets_pending or facts.assets_failed))
        or facts.missing_inputs
        or facts.language_unknown
    )

    # --- PLAN_READY -----------------------------------------------------
    adjudication_ok = facts.adjudication_error is None
    if facts.has_pending_plan and not adjudication_ok:
        blockers.append(BLOCKER_CHAIN_ADJUDICATION_FAILED)
    if facts.prerequisite_pending:
        blockers.append(BLOCKER_PENDING_PREREQUISITE)

    plan_ready = (
        facts.has_pending_plan
        and bool(facts.plan_tasks)  # 无链不成计划——空链 task_book 永不 ready
        and material_ready
        and adjudication_ok
        and not facts.prerequisite_pending
    )

    # --- ConfirmationScopeReady (P8 field inventory) --------------------
    # The confirmation card's scope facts: a non-empty, structurally legal
    # chain + the plan prose. Everything else on the dock payload is
    # either another conjunct (estimate → charge) or already covered
    # (reasons/brief/role pins → pending_prerequisite).
    confirmation_scope_ready = (
        facts.has_pending_plan
        and bool(facts.plan_tasks)
        and adjudication_ok
        and bool(facts.plan_prose.strip())
    )

    # --- ChargeSemanticsReady (ADR-087 §2.1) ----------------------------
    # The disclosure surface is renderable whenever a plan is docked: a
    # known estimate shows the numbers, a NULL estimate shows the honest
    # Deferred facet ("估价随运行" + hold timing). Never block Confirm on
    # estimate completeness (ADR-063 stays valid).
    charge_semantics_ready = facts.has_pending_plan
    charge_deferred = facts.estimate_total is None

    # --- NoActiveConflictingRun -----------------------------------------
    no_active_conflicting_run = not facts.active_run
    if facts.active_run:
        blockers.append(BLOCKER_ACTIVE_RUN)

    # --- The ONE composition point (U4) ----------------------------------
    confirmation_ready = (
        plan_ready
        and confirmation_scope_ready
        and charge_semantics_ready
        and no_active_conflicting_run
    )

    # State rollup: the furthest stage reached. RUNNING wins over the
    # plan stages (T10: a docked ready plan during an active run reads
    # plan_ready=true / state=running / confirmation_ready=false).
    if facts.active_run:
        state = STATE_RUNNING
    elif confirmation_ready:
        state = STATE_CONFIRMATION_READY
    elif plan_ready:
        state = STATE_PLAN_READY
    else:
        state = STATE_PREPARING

    return LifecycleStamp(
        state=state,
        material_ready=material_ready,
        plan_ready=plan_ready,
        confirmation_scope_ready=confirmation_scope_ready,
        charge_semantics_ready=charge_semantics_ready,
        no_active_conflicting_run=no_active_conflicting_run,
        confirmation_ready=confirmation_ready,
        blockers=tuple(blockers),
        charge_known=facts.estimate_total,
        charge_deferred=charge_deferred,
    )


# ---- The Start gate (ADR-087 §4 D3, Phase 4 B6) -----------------------------------


@dataclass(frozen=True)
class StartGateVerdict:
    """One pre-birth block at the ONLY confirmation seat (``answer_question``
    kind="start" — the dock pill and the G-1 prose confirm share it,
    plan_turn._start_run funnels into the same function). Machine-readable
    by construction (D3: never a disguised business error — "the frontend
    button is disabled" is the first line, never the only one).
    ``http_status`` separates the structural guards (409 — the request is
    stale / there is nothing to confirm) from the readiness block (422 —
    the four-conjunction projection says not yet)."""

    http_status: int
    code: str
    blockers: tuple[str, ...] = ()


def evaluate_start_gate(
    *,
    already_answered: bool = False,
    superseded: bool = False,
    has_pending_plan: bool,
    effective_tasks_nonempty: bool,
    stamp: LifecycleStamp,
) -> StartGateVerdict | None:
    """Every check that must hold before the Start seat reaches paid
    ``create_run``, in evaluation order (the precedence the blockers
    report). ``None`` = the start may proceed.

    - ``superseded`` (the dock moved on — the answered task_book is no
      longer the current confirmation scope) beats the generic
      ``already_answered`` (a double start) — D3's "current plan /
      task_book 与确认范围一致" and "explicit confirmation missing".
    - no resolvable pending plan → 409 ``start.no_pending_plan``: charge
      semantics are by definition unavailable there (§3's deliberate
      equivalence: charge ≡ has_pending_plan) and there is nothing to
      confirm — one code covers D3's charge-unavailable and
      confirmation-missing rows.
    - an empty effective chain is not a confirmable scope (422
      ``start.empty_plan``).
    - the stamp's four conjuncts → 422 ``start.blocked`` carrying the
      projection's own blocker ids (material / adjudication / prerequisite
      / active conflicting run).
    """
    if superseded:
        return StartGateVerdict(409, "start.scope_mismatch")
    if already_answered:
        return StartGateVerdict(409, "start.already_answered")
    if not has_pending_plan:
        return StartGateVerdict(409, "start.no_pending_plan")
    if not effective_tasks_nonempty:
        return StartGateVerdict(422, "start.empty_plan")
    if not stamp.confirmation_ready:
        return StartGateVerdict(422, "start.blocked", stamp.blockers)
    return None


async def project_lifecycle(
    db: AsyncSession,
    project: "Project",
    *,
    pending_question: "Message | None",
    pending_plan: bool,
    ui_language: str = "en",
) -> LifecycleStamp:
    """Gather the pipeline-owned facts and compute the stamp.

    ``pending_question`` / ``pending_plan`` are the Agent Interface facts,
    fetched by the transport caller through chat's public read protocol
    (this module never imports chat — Phase 5 keeps the reverse-import
    list flat). Read-only: no writes, no flushes.

    The morph helpers are module-internal reads (pipeline package) — the
    same-language adjudication's public-seat promotion is Phase 5's move;
    using the existing private seats here adds no new cross-module debt.
    """
    # --- Agent Interface facts, field-level (U4: never payload-existence)
    plan_tasks: tuple[dict[str, Any], ...] = ()
    plan_prose = ""
    estimate_total: tuple[int, int] | None = None
    prerequisite_pending = False
    if pending_question is not None:
        payload = pending_question.question or {}
        if pending_plan:
            intent = pending_question.intent or {}
            raw_tasks = intent.get("tasks") or []
            plan_tasks = tuple(t for t in raw_tasks if isinstance(t, dict))
            plan_prose = str(
                (intent.get("answer") or "") or (pending_question.content or "")
            )
            estimate = payload.get("estimate_credits") or {}
            total = estimate.get("total")
            if isinstance(total, list) and len(total) == 2:
                estimate_total = (int(total[0]), int(total[1]))
        else:
            # A pending non-task_book question IS the hanging prerequisite
            # (slot ask / caption-mode / asset-role — single-pending
            # invariant makes it the latest unanswered row).
            prerequisite_pending = True

    # --- Chain structure + requirement keys (same registry the
    # birthplace ∀-check reads — orchestrator._check_birthplace_requires).
    required_inputs: tuple[str, ...] = ()
    adjudication_error: str | None = None
    if pending_plan and plan_tasks:
        try:
            entries = validate_task_list(
                [_TaskShim(t) for t in plan_tasks]
            )
            keys: dict[str, None] = {}
            for entry in entries:
                node = NODE_KINDS.get(entry.name)
                for req in node.requires if node else ():
                    keys.setdefault(req.key)
            required_inputs = tuple(sorted(keys))
        except (ToolRejected, ValueError) as e:
            adjudication_error = str(e)

    # --- Asset status facts (legacy project-scope resolver — U2 compat;
    # the worker claim gate shares this scope, jobs.py:176).
    assets = list(
        (
            await db.execute(
                select(Asset).where(
                    Asset.project_id == project.id,
                    Asset.file_url.isnot(None),
                )
            )
        )
        .scalars()
        .all()
    )
    assets_pending = any(
        _asset_status(a) in ("pending", "processing") for a in assets
    )
    assets_failed = any(_asset_status(a) == "failed" for a in assets)

    # --- Required-input existence (the birthplace Requirement predicates
    # themselves — the node's own knowledge, not a parallel table).
    missing: list[str] = []
    if pending_plan and not adjudication_error:
        for key in required_inputs:
            req = _REQUIREMENT_BY_KEY.get(key)
            if req is not None and await req.missing(db, project):
                missing.append(key)

    # --- Transform language facts (U5 split): unknown faced language is
    # a missing content fact; a KNOWN language hitting the same-language
    # rule is the adjudication failure.
    language_unknown = False
    if pending_plan and not adjudication_error and plan_tasks:
        transform_tasks = [
            t
            for t in plan_tasks
            if t.get("tool") in ("translate_clip", "dub_clip")
            and (t.get("params") or {}).get("target_language")
        ]
        if transform_tasks:
            chain_has_select_clips = any(
                t.get("tool") == "select_clips" for t in plan_tasks
            )
            scopes = {
                str((t.get("params") or {}).get("target_output_id") or "") or None
                for t in transform_tasks
            }
            faced_sets = {
                scope: await _faced_source_languages(
                    db, project, scope, chain_has_select_clips=chain_has_select_clips
                )
                for scope in scopes
            }
            if any(not faced for faced in faced_sets.values()):
                language_unknown = True
            else:
                try:
                    await _check_transform_targets(
                        db,
                        project,
                        [_TaskShim(t) for t in plan_tasks],
                        zh=ui_language.startswith("zh"),
                    )
                except (ToolRejected, ValueError) as e:
                    adjudication_error = str(e)

    active = await has_active_run(db, project.id)

    return compute_lifecycle(
        LifecycleFacts(
            has_pending_plan=pending_plan,
            prerequisite_pending=prerequisite_pending,
            plan_tasks=plan_tasks,
            plan_prose=plan_prose,
            estimate_total=estimate_total,
            assets_pending=assets_pending,
            assets_failed=assets_failed,
            missing_inputs=tuple(missing),
            language_unknown=language_unknown,
            adjudication_error=adjudication_error,
            active_run=active,
            required_inputs=required_inputs,
        )
    )


class _TaskShim:
    """validate_task_list/_check_transform_targets read ``.tool`` /
    ``.params`` attributes; the docked intent stamp stores plain dicts.
    Attribute view only — no validation logic here."""

    __slots__ = ("tool", "params")

    def __init__(self, raw: dict[str, Any]) -> None:
        self.tool = raw.get("tool")
        self.params = raw.get("params") or {}


def _asset_status(asset: Asset) -> str:
    """processing_status normalized to its lowercase value (the column is
    Enum(AssetStatus) — rows materialize as enum members or plain strings
    depending on the read path)."""
    status = asset.processing_status
    return str(getattr(status, "value", status)).lower()
