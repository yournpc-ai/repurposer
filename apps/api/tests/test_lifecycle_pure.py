"""Tests for the Lifecycle Projection pure core (ADR-087 §2 — Phase 1).

Pure-function coverage only (suite discipline: no DB, no LLM, no HTTP).
The matrix is the Phase 1 brief's §Preflight P6 (T1~T15), locked against
``compute_lifecycle(LifecycleFacts)`` — the gatherer (project_lifecycle)
only resolves these facts from their owners and is covered by scenarios.

The three hard gates made executable:

- 门禁一 (coverage): every real path state — PENDING / PROCESSING /
  FAILED / COMPLETED / empty transcript / unknown language / pending
  prerequisite / old task_book / re-dock / revision / active run — has a
  row here with an explicit stamp answer.
- 门禁三 (independence): PLAN_READY and CONFIRMATION_READY are never the
  same boolean — the flagship negative cases T10 (active run) and T10b
  (scope not ready) pin `plan_ready=True ∧ confirmation_ready=False`,
  and T15 pins the single composition point.
- U5 split: unknown source language is a missing content fact
  (``language_unknown`` → material not ready), never an adjudication
  failure; ``chain_adjudication_failed`` is reserved for a KNOWN language
  breaking the rule.
"""

from app.pipeline.lifecycle import (
    BLOCKER_ACTIVE_RUN,
    BLOCKER_CHAIN_ADJUDICATION_FAILED,
    BLOCKER_CONTENT_MISSING,
    BLOCKER_LANGUAGE_UNKNOWN,
    BLOCKER_MATERIAL_FAILED,
    BLOCKER_MATERIAL_PENDING,
    BLOCKER_PENDING_PREREQUISITE,
    STATE_CONFIRMATION_READY,
    STATE_PREPARING,
    STATE_RUNNING,
    LifecycleFacts,
    compute_lifecycle,
)

_TASK = {"tool": "write_post", "params": {"language": "en"}}
_MEDIA_CHAIN_INPUTS = ("media", "transcript")


def _ready_facts(**overrides) -> LifecycleFacts:
    """The all-green docked plan — every test starts here and breaks one
    fact, so each row isolates exactly one predicate's tooth."""
    base = {
        "has_pending_plan": True,
        "plan_tasks": (_TASK,),
        "plan_prose": "Plan: one post from the transcript.",
        "estimate_total": (10, 20),
        "required_inputs": _MEDIA_CHAIN_INPUTS,
    }
    base.update(overrides)
    return LifecycleFacts(**base)


# T1 — no docked plan: PREPARING, nothing ready, no blockers.
def test_t1_no_pending_plan_is_preparing() -> None:
    stamp = compute_lifecycle(LifecycleFacts())
    assert stamp.state == STATE_PREPARING
    assert not stamp.plan_ready
    assert not stamp.confirmation_ready
    assert not stamp.material_ready
    assert stamp.blockers == ()


# T2 — docked plan + asset PENDING: material_pending, PREPARING.
def test_t2_asset_pending() -> None:
    stamp = compute_lifecycle(_ready_facts(assets_pending=True))
    assert stamp.state == STATE_PREPARING
    assert not stamp.material_ready
    assert not stamp.plan_ready
    assert stamp.blockers == (BLOCKER_MATERIAL_PENDING,)


# T3 — PROCESSING reads identically to PENDING (the gatherer folds both
# into assets_pending; this row pins the fold's downstream sameness).
def test_t3_asset_processing_same_as_pending() -> None:
    stamp = compute_lifecycle(_ready_facts(assets_pending=True))
    assert BLOCKER_MATERIAL_PENDING in stamp.blockers
    assert not stamp.plan_ready


# T4 — asset FAILED: its OWN blocker reason (U1 — never a generic
# not-ready), plan not ready.
def test_t4_asset_failed_has_own_reason() -> None:
    stamp = compute_lifecycle(_ready_facts(assets_failed=True))
    assert BLOCKER_MATERIAL_FAILED in stamp.blockers
    assert BLOCKER_MATERIAL_PENDING not in stamp.blockers
    assert not stamp.material_ready
    assert stamp.state == STATE_PREPARING


# T5 — assets COMPLETED but the chain's required input facts are absent
# (e.g. empty transcript): content_missing.
def test_t5_content_missing() -> None:
    stamp = compute_lifecycle(_ready_facts(missing_inputs=("transcript",)))
    assert stamp.blockers == (BLOCKER_CONTENT_MISSING,)
    assert not stamp.material_ready
    assert not stamp.plan_ready


# T6 — transform chain + unknown source language: language_unknown, a
# CONTENT-fact absence (U5) — material not ready, NOT adjudication.
def test_t6_unknown_language_is_content_fact_missing() -> None:
    stamp = compute_lifecycle(_ready_facts(language_unknown=True))
    assert stamp.blockers == (BLOCKER_LANGUAGE_UNKNOWN,)
    assert not stamp.material_ready
    assert not stamp.plan_ready
    assert BLOCKER_CHAIN_ADJUDICATION_FAILED not in stamp.blockers


# T6b — KNOWN language breaking the same-language rule: adjudication
# failure (the only reading of chain_adjudication_failed, U5).
def test_t6b_known_language_rule_failure_is_adjudication() -> None:
    stamp = compute_lifecycle(
        _ready_facts(adjudication_error="Source is already English")
    )
    assert stamp.blockers == (BLOCKER_CHAIN_ADJUDICATION_FAILED,)
    assert stamp.material_ready  # material facts are fine — the CHAIN fails
    assert not stamp.plan_ready


# T7 — prerequisite question hanging: plan not ready, its own blocker.
def test_t7_pending_prerequisite() -> None:
    stamp = compute_lifecycle(_ready_facts(prerequisite_pending=True))
    assert stamp.blockers == (BLOCKER_PENDING_PREREQUISITE,)
    assert not stamp.plan_ready


# T8 — chain re-adjudication failure (known language, registry/legal
# structure broken): chain_adjudication_failed.
def test_t8_chain_readjudication_failure() -> None:
    stamp = compute_lifecycle(
        _ready_facts(adjudication_error="Unknown tool 'x'")
    )
    assert BLOCKER_CHAIN_ADJUDICATION_FAILED in stamp.blockers
    assert not stamp.plan_ready
    assert not stamp.confirmation_ready


# T9 — all ready + estimate NULL: Deferred disclosure presentable →
# charge_semantics_ready stays true, confirmation_ready true (ADR-063:
# estimate completeness never gates).
def test_t9_null_estimate_still_confirmation_ready() -> None:
    stamp = compute_lifecycle(_ready_facts(estimate_total=None))
    assert stamp.plan_ready
    assert stamp.charge_semantics_ready
    assert stamp.charge_deferred
    assert stamp.charge_known is None
    assert stamp.confirmation_ready
    assert stamp.state == STATE_CONFIRMATION_READY


# T9b — known estimate rides the stamp as data (never adjudicated).
def test_t9b_known_estimate() -> None:
    stamp = compute_lifecycle(_ready_facts())
    assert stamp.charge_known == (10, 20)
    assert not stamp.charge_deferred
    assert stamp.confirmation_ready


# T10 — FLAGSHIP NEGATIVE (门禁三): fully ready plan + active run →
# plan_ready=True ∧ confirmation_ready=False, state=running, and the UI
# is legal (canvas + pill visible, Confirm disabled).
def test_t10_flagship_negative_active_run() -> None:
    stamp = compute_lifecycle(_ready_facts(active_run=True))
    assert stamp.plan_ready
    assert not stamp.no_active_conflicting_run
    assert not stamp.confirmation_ready
    assert stamp.state == STATE_RUNNING
    assert BLOCKER_ACTIVE_RUN in stamp.blockers


# T10b — R10 (2026-09-21 翻案 P8): the plan prose is narrative decoration,
# never a scope fact — an empty-echo dock (the LLM's legal silent
# present_plan / the caption replay's TaskListProposal stash) is
# confirmation-ready like any other. (Pre-R10 this seat was the flagship
# PLAN_READY ∧ ¬ScopeReady conjunct-independence witness; with the prose
# conjunct retired, scope_ready = has_pending_plan ∧ chain ∧ adjudication
# is implied by plan_ready's own conjuncts — the independence witness is
# gone BY DESIGN, this pin locks the R10 truth.)
def test_t10b_empty_prose_dock_is_confirmation_ready() -> None:
    stamp = compute_lifecycle(_ready_facts(plan_prose=""))
    assert stamp.plan_ready
    assert stamp.confirmation_scope_ready
    assert stamp.confirmation_ready
    assert stamp.state == STATE_CONFIRMATION_READY


# T11 — active run + no new plan: RUNNING, plan facts all false.
def test_t11_active_run_no_plan() -> None:
    stamp = compute_lifecycle(LifecycleFacts(active_run=True))
    assert stamp.state == STATE_RUNNING
    assert not stamp.plan_ready
    assert not stamp.confirmation_ready


# T12 — answered/superseded task_book rows never participate: the
# gatherer only passes has_pending_plan=True for an UNANSWERED row, so an
# old row reads exactly like T1.
def test_t12_answered_task_book_equals_no_plan() -> None:
    assert compute_lifecycle(LifecycleFacts()) == compute_lifecycle(
        LifecycleFacts(plan_tasks=(), plan_prose="")
    )


# T13 — re-dock: the stamp is a pure function of the CURRENT facts, so a
# re-docked (rewritten) row simply recomputes — pin determinism.
def test_t13_redock_is_deterministic_recompute() -> None:
    facts = _ready_facts()
    assert compute_lifecycle(facts) == compute_lifecycle(facts)


# T14 — hand-edited panel chain: the projection adjudicates the STORED
# dock chain (the birthplace 422 keeps guarding edits); nothing in the
# core distinguishes them — pin that the stamp reads plan_tasks as given.
def test_t14_stamp_reads_stored_chain_verbatim() -> None:
    edited = {"tool": "write_post", "params": {"language": "de"}}
    stamp = compute_lifecycle(_ready_facts(plan_tasks=(edited,)))
    assert stamp.confirmation_scope_ready  # chain non-empty + prose
    assert stamp.plan_ready


# T15 — single composition point: plan_ready=False forces
# confirmation_ready=False no matter how the other three conjuncts stand.
def test_t15_composition_point_uniqueness() -> None:
    stamp = compute_lifecycle(
        _ready_facts(assets_pending=True)  # plan_ready False via material
    )
    assert not stamp.plan_ready
    assert stamp.confirmation_scope_ready  # other conjuncts can be true…
    assert stamp.charge_semantics_ready
    assert stamp.no_active_conflicting_run
    assert not stamp.confirmation_ready  # …composition still says no


# Chain with NO asset requirements never waits on upload processing —
# status facts gate only chains that consume assets (plan-scoped, U2).
def test_chain_without_asset_inputs_ignores_asset_status() -> None:
    stamp = compute_lifecycle(
        _ready_facts(required_inputs=(), assets_pending=True, assets_failed=True)
    )
    assert stamp.material_ready
    assert stamp.plan_ready
    assert stamp.blockers == ()


# A task_book row with an EMPTY chain is never plan-ready (无链不成计划 —
# material/adjudication conditions can't save it; ConfirmationScopeReady
# independently false).
def test_empty_chain_never_plan_ready() -> None:
    stamp = compute_lifecycle(_ready_facts(plan_tasks=()))
    assert not stamp.plan_ready
    assert not stamp.confirmation_scope_ready
    assert not stamp.confirmation_ready


# ---- Phase 2.5 Batch B-1: the remaining conjunct pins -----------------------


# ChargeSemanticsReady IS exactly "a plan is docked" (ADR-063 final reading):
# the disclosure surface is renderable whenever a plan exists — a NULL
# estimate shows the honest Deferred facet, so estimate completeness NEVER
# blocks Confirm. The conjunct's only False is the no-plan row, where
# plan_ready is already False (T1); there is NO reachable "plan_ready ∧
# charge-incomplete" state by design — T9 pins the NULL-estimate green case,
# this pin locks the equivalence itself.
def test_charge_semantics_ready_is_exactly_the_docked_plan() -> None:
    no_plan = compute_lifecycle(LifecycleFacts())
    assert no_plan.charge_semantics_ready is False
    assert no_plan.confirmation_scope_ready is False
    assert no_plan.confirmation_ready is False
    docked = compute_lifecycle(_ready_facts(estimate_total=None))
    assert docked.charge_semantics_ready is True
    assert docked.confirmation_ready is True  # ADR-063: deferred ≠ blocked
    assert docked.charge_deferred is True


# Multi-blocker determinism: when several predicates fail at once the
# blockers tuple is the predicate evaluation order — stable, deduped,
# semantic (never DB row order / dict order / stream order). Pinned as an
# EXACT tuple so reordering or duplication goes red.
def test_multi_blocker_order_is_the_predicate_evaluation_order() -> None:
    facts = _ready_facts(
        assets_pending=True,
        language_unknown=True,
        prerequisite_pending=True,
        active_run=True,
    )
    expected = (
        BLOCKER_MATERIAL_PENDING,   # material facts first
        BLOCKER_LANGUAGE_UNKNOWN,   # …then the content fact…
        BLOCKER_PENDING_PREREQUISITE,  # …then the dangling prerequisite…
        BLOCKER_ACTIVE_RUN,         # …then the authority conflict last
    )
    stamp = compute_lifecycle(facts)
    assert stamp.blockers == expected
    # Determinism: the same facts re-computed byte-identically.
    assert compute_lifecycle(facts).blockers == expected
    # And the failing predicates still leave plan_ready false /
    # confirmation_ready false (the blockers are explanatory, never
    # decorative).
    assert not stamp.plan_ready
    assert not stamp.confirmation_ready


# ---- D3 Start gate six-case matrix (ADR-087 §4, Phase 4 B6) ----------------

from app.pipeline.lifecycle import evaluate_start_gate  # noqa: E402

_READY_STAMP = compute_lifecycle(_ready_facts())


def test_d3_case1_confirmation_ready_is_allowed() -> None:
    # ① confirmation_ready=true → allowed (None = proceed to create_run).
    verdict = evaluate_start_gate(
        has_pending_plan=True, effective_tasks_nonempty=True, stamp=_READY_STAMP
    )
    assert verdict is None


def test_d3_case2_confirmation_not_ready_is_blocked_machine_readable() -> None:
    # ② confirmation_ready=false → 422 start.blocked carrying the
    # projection's own blocker ids (here: material pending).
    stamp = compute_lifecycle(_ready_facts(assets_pending=True))
    verdict = evaluate_start_gate(
        has_pending_plan=True, effective_tasks_nonempty=True, stamp=stamp
    )
    assert verdict is not None
    assert verdict.http_status == 422
    assert verdict.code == "start.blocked"
    assert "material_pending" in verdict.blockers


def test_d3_case3_charge_semantics_unavailable_is_blocked() -> None:
    # ③ charge semantics unavailable → blocked. §3's deliberate
    # equivalence (charge ≡ has_pending_plan) folds this into the
    # no-pending-plan structural guard — one code covers it.
    verdict = evaluate_start_gate(
        has_pending_plan=False, effective_tasks_nonempty=True, stamp=_READY_STAMP
    )
    assert verdict is not None
    assert verdict.http_status == 409
    assert verdict.code == "start.no_pending_plan"


def test_d3_case4_scope_mismatch_is_blocked() -> None:
    # ④ scope mismatch (the answered task_book was superseded — the dock
    # moved on) → 409 start.scope_mismatch, and it beats the generic
    # already-answered code.
    verdict = evaluate_start_gate(
        already_answered=True,
        superseded=True,
        has_pending_plan=True,
        effective_tasks_nonempty=True,
        stamp=_READY_STAMP,
    )
    assert verdict is not None
    assert verdict.http_status == 409
    assert verdict.code == "start.scope_mismatch"


def test_d3_case5_active_conflicting_run_is_blocked() -> None:
    # ⑤ active conflicting run → 422 start.blocked with active_run.
    stamp = compute_lifecycle(_ready_facts(active_run=True))
    verdict = evaluate_start_gate(
        has_pending_plan=True, effective_tasks_nonempty=True, stamp=stamp
    )
    assert verdict is not None
    assert verdict.http_status == 422
    assert verdict.code == "start.blocked"
    assert verdict.blockers == ("active_run",)


def test_d3_case6_explicit_confirmation_missing_is_blocked() -> None:
    # ⑥ explicit confirmation missing (a double start) → 409
    # start.already_answered; no pending plan reads as the same
    # missing-confirmation guard (start.no_pending_plan, case ③'s code).
    verdict = evaluate_start_gate(
        already_answered=True,
        has_pending_plan=True,
        effective_tasks_nonempty=True,
        stamp=_READY_STAMP,
    )
    assert verdict is not None
    assert verdict.http_status == 409
    assert verdict.code == "start.already_answered"


def test_d3_empty_chain_is_not_a_confirmable_scope() -> None:
    verdict = evaluate_start_gate(
        has_pending_plan=True, effective_tasks_nonempty=False, stamp=_READY_STAMP
    )
    assert verdict is not None
    assert verdict.http_status == 422
    assert verdict.code == "start.empty_plan"


def test_d3_gate_precedence_structural_before_projection() -> None:
    # The structural guards precede the projection verdict: a missing
    # plan reports no_pending_plan even when the stamp would also block.
    not_ready = compute_lifecycle(_ready_facts(assets_pending=True))
    verdict = evaluate_start_gate(
        has_pending_plan=False, effective_tasks_nonempty=True, stamp=not_ready
    )
    assert verdict is not None
    assert verdict.code == "start.no_pending_plan"
