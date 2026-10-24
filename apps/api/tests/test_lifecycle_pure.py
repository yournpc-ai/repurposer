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


# ---- ADR-129: the Start gate's film conjuncts ----

from app.pipeline.lifecycle import ConfirmationNeed, FilmGateFacts  # noqa: E402


def test_film_gate_no_active_draft_is_409() -> None:
    # A film chain with no active storyboard draft has nothing versioned to
    # confirm → 409 start.no_storyboard.
    verdict = evaluate_start_gate(
        has_pending_plan=True,
        effective_tasks_nonempty=True,
        stamp=_READY_STAMP,
        film=FilmGateFacts(film_chain=True, has_active_draft=False),
    )
    assert verdict is not None
    assert verdict.http_status == 409
    assert verdict.code == "start.no_storyboard"


def test_film_gate_stale_draft_is_409() -> None:
    # A dock presenting a superseded draft → 409 start.stale_storyboard
    # (the dock moved on — the scope_mismatch family).
    verdict = evaluate_start_gate(
        has_pending_plan=True,
        effective_tasks_nonempty=True,
        stamp=_READY_STAMP,
        film=FilmGateFacts(film_chain=True, has_active_draft=True, draft_match=False),
    )
    assert verdict is not None
    assert verdict.http_status == 409
    assert verdict.code == "start.stale_storyboard"


def test_film_gate_inflight_draft_is_409() -> None:
    # A redesign's in-flight marker voids the docked confirmation for the
    # duration → 409 start.stale_storyboard even when the docked token still
    # matches the stored draft (并发护栏: the old Start fails closed while
    # the marker stands).
    verdict = evaluate_start_gate(
        has_pending_plan=True,
        effective_tasks_nonempty=True,
        stamp=_READY_STAMP,
        film=FilmGateFacts(
            film_chain=True,
            has_active_draft=True,
            draft_match=True,
            draft_inflight=True,
        ),
    )
    assert verdict is not None
    assert verdict.http_status == 409
    assert verdict.code == "start.stale_storyboard"


def test_film_gate_review_hold_is_422() -> None:
    # An active review hold (「只看分镜，先别制作」) → 422
    # start.review_hold — the readiness family.
    verdict = evaluate_start_gate(
        has_pending_plan=True,
        effective_tasks_nonempty=True,
        stamp=_READY_STAMP,
        film=FilmGateFacts(film_chain=True, has_active_draft=True, review_hold=True),
    )
    assert verdict is not None
    assert verdict.http_status == 422
    assert verdict.code == "start.review_hold"


def test_first_draft_unpresented_blocks_same_turn_auto_start() -> None:
    # Auto + production intent + a cleared review hold still cannot spend
    # before the first board's presentation row exists.
    verdict = evaluate_start_gate(
        has_pending_plan=True,
        effective_tasks_nonempty=True,
        stamp=_READY_STAMP,
        confirmation=ConfirmationNeed(requires_confirmation=False),
        docked_this_turn=True,
        film=FilmGateFacts(
            film_chain=True,
            has_active_draft=True,
            first_draft_unpresented=True,
        ),
    )
    assert verdict is not None
    assert verdict.http_status == 422
    assert verdict.code == "start.review_hold"


def test_first_draft_unpresented_also_blocks_an_early_explicit_start() -> None:
    verdict = evaluate_start_gate(
        has_pending_plan=True,
        effective_tasks_nonempty=True,
        stamp=_READY_STAMP,
        film=FilmGateFacts(
            film_chain=True,
            has_active_draft=True,
            first_draft_unpresented=True,
        ),
    )
    assert verdict is not None
    assert verdict.code == "start.review_hold"


def test_presented_first_draft_allows_the_later_explicit_start() -> None:
    # The dock's review stamp does not become a second auto-start permit:
    # after presentation, the user's explicit Start is the release beat.
    verdict = evaluate_start_gate(
        has_pending_plan=True,
        effective_tasks_nonempty=True,
        stamp=_READY_STAMP,
        confirmation=ConfirmationNeed(
            requires_confirmation=True,
            reason="first_draft_review",
        ),
        docked_this_turn=False,
        film=FilmGateFacts(
            film_chain=True,
            has_active_draft=True,
            first_draft_unpresented=False,
        ),
    )
    assert verdict is None


def test_presented_first_draft_allows_auto_on_the_approval_redock() -> None:
    # A post-presentation "就按这版做" may re-dock with production intent:
    # the ordinary auto machine starts it without a second approval beat.
    verdict = evaluate_start_gate(
        has_pending_plan=True,
        effective_tasks_nonempty=True,
        stamp=_READY_STAMP,
        confirmation=ConfirmationNeed(requires_confirmation=False),
        docked_this_turn=True,
        film=FilmGateFacts(
            film_chain=True,
            has_active_draft=True,
            first_draft_unpresented=False,
        ),
    )
    assert verdict is None


def test_film_gate_matching_active_draft_is_allowed() -> None:
    verdict = evaluate_start_gate(
        has_pending_plan=True,
        effective_tasks_nonempty=True,
        stamp=_READY_STAMP,
        film=FilmGateFacts(film_chain=True, has_active_draft=True, draft_match=True),
    )
    assert verdict is None


def test_film_gate_conjuncts_stay_dark_off_film_chains() -> None:
    # film_chain=False disables every film conjunct — a non-film start
    # never trips them, whatever the other flags say.
    verdict = evaluate_start_gate(
        has_pending_plan=True,
        effective_tasks_nonempty=True,
        stamp=_READY_STAMP,
        film=FilmGateFacts(
            film_chain=False,
            has_active_draft=False,
            draft_match=False,
            review_hold=True,
            first_draft_unpresented=True,
        ),
    )
    assert verdict is None


def test_film_gate_precedence_stale_before_empty_plan() -> None:
    # The 409 staleness family precedes the 422 readiness family: a dock
    # presenting a superseded draft reports the stale code even when the
    # chain is also empty.
    verdict = evaluate_start_gate(
        has_pending_plan=True,
        effective_tasks_nonempty=False,
        stamp=_READY_STAMP,
        film=FilmGateFacts(film_chain=True, has_active_draft=True, draft_match=False),
    )
    assert verdict is not None
    assert verdict.code == "start.stale_storyboard"


def test_film_gate_precedence_hold_before_projection_block() -> None:
    # The review hold precedes the stamp's projection blockers: the user
    # scoped review only — that is the answer even when material is also
    # unready.
    not_ready = compute_lifecycle(_ready_facts(assets_pending=True))
    verdict = evaluate_start_gate(
        has_pending_plan=True,
        effective_tasks_nonempty=True,
        stamp=not_ready,
        film=FilmGateFacts(film_chain=True, has_active_draft=True, review_hold=True),
    )
    assert verdict is not None
    assert verdict.code == "start.review_hold"


# ---- ADR-117 授权前移: confirmation_need + the gate's authorization conjunct ----

from app.pipeline.lifecycle import confirmation_need, first_draft_confirmation  # noqa: E402

GUARDRAIL = 5000


def test_confirmation_need_auto_auto_under_guardrail_is_free() -> None:
    # The default regime: both prefs auto, a quotable plan under the
    # guardrail, production intent present — no beat owed.
    need = confirmation_need(
        execution="auto", credits="auto",
        quote_high=800, unquotable=False, always_confirm_above=GUARDRAIL,
    )
    assert need.requires_confirmation is False
    assert need.reason == ""
    assert need.quote_high == 800
    assert need.unquotable is False


def test_first_draft_confirmation_adds_review_even_in_full_auto() -> None:
    need = first_draft_confirmation(
        ConfirmationNeed(requires_confirmation=False, quote_high=55),
        unpresented=True,
    )
    assert need.requires_confirmation is True
    assert need.reason == "first_draft_review"
    assert need.quote_high == 55


def test_first_draft_confirmation_preserves_stronger_reasons() -> None:
    priced = ConfirmationNeed(
        requires_confirmation=True,
        reason="above_guardrail",
        quote_high=9000,
    )
    assert first_draft_confirmation(priced, unpresented=True) is priced
    ordinary = ConfirmationNeed(requires_confirmation=False)
    assert first_draft_confirmation(ordinary, unpresented=False) is ordinary


def test_confirmation_need_execution_ask_alone_holds() -> None:
    # 执行确认=ask alone holds the beat — even a free plan (the execution
    # pref is about TOOL invocation, not money; quote never shields it).
    need = confirmation_need(
        execution="ask", credits="auto",
        quote_high=0, unquotable=False, always_confirm_above=GUARDRAIL,
    )
    assert need.requires_confirmation is True
    assert need.reason == "execution_pref"


def test_confirmation_need_credits_ask_only_fires_on_a_nonzero_quote() -> None:
    # 费用确认=ask + quote_high=0 (a free plan) → NO beat (D1: asking about
    # spending when nothing can be spent is noise); a nonzero quote holds.
    free = confirmation_need(
        execution="auto", credits="ask",
        quote_high=0, unquotable=False, always_confirm_above=GUARDRAIL,
    )
    assert free.requires_confirmation is False
    priced = confirmation_need(
        execution="auto", credits="ask",
        quote_high=120, unquotable=False, always_confirm_above=GUARDRAIL,
    )
    assert priced.requires_confirmation is True
    assert priced.reason == "credits_pref"
    assert priced.quote_high == 120


def test_confirmation_need_guardrail_beats_prefs_in_any_mode() -> None:
    # D6: fold high over the guardrail always asks once — both prefs auto
    # included. Reason precedence names the guardrail over the prefs.
    need = confirmation_need(
        execution="auto", credits="auto",
        quote_high=5001, unquotable=False, always_confirm_above=GUARDRAIL,
    )
    assert need.requires_confirmation is True
    assert need.reason == "above_guardrail"
    # The boundary itself is inclusive-exclusive: exactly at the line is free.
    at_line = confirmation_need(
        execution="auto", credits="auto",
        quote_high=5000, unquotable=False, always_confirm_above=GUARDRAIL,
    )
    assert at_line.requires_confirmation is False


def test_confirmation_need_unquotable_always_asks_and_wins() -> None:
    # NULL 族恒问: an unquotable plan asks once in every mode, and the
    # reason names unquotable ahead of the guardrail (the pill's label
    # follows it — 「估价随运行确定」, never a fabricated number).
    need = confirmation_need(
        execution="auto", credits="auto",
        quote_high=9000, unquotable=True, always_confirm_above=GUARDRAIL,
    )
    assert need.requires_confirmation is True
    assert need.reason == "unquotable"
    assert need.unquotable is True
    # A deferred quote (None) rides the same clause.
    deferred = confirmation_need(
        execution="auto", credits="auto",
        quote_high=None, unquotable=True, always_confirm_above=GUARDRAIL,
    )
    assert deferred.requires_confirmation is True
    assert deferred.reason == "unquotable"


def test_confirmation_need_reason_precedence_money_before_execution() -> None:
    # credits=ask on a priced plan beats a bare execution=ask in the
    # reason order (the pill's priced label keys on it).
    need = confirmation_need(
        execution="ask", credits="ask",
        quote_high=120, unquotable=False, always_confirm_above=GUARDRAIL,
    )
    assert need.reason == "credits_pref"


def test_gate_authorization_conjunct_fires_only_in_the_docks_own_turn() -> None:
    # The auto regime's presentation-time start attempt: a dock that owes
    # a beat AND docked this turn → 422 start.needs_confirm carrying the
    # reason + quote. The SAME need on a later-turn start (the user's beat
    # IS the confirmation) never trips the conjunct.
    need = confirmation_need(
        execution="auto", credits="auto",
        quote_high=9000, unquotable=False, always_confirm_above=GUARDRAIL,
    )
    blocked = evaluate_start_gate(
        has_pending_plan=True,
        effective_tasks_nonempty=True,
        stamp=_READY_STAMP,
        confirmation=need,
        docked_this_turn=True,
    )
    assert blocked is not None
    assert blocked.http_status == 422
    assert blocked.code == "start.needs_confirm"
    assert blocked.reason == "above_guardrail"
    assert blocked.quote_high == 9000
    # Later-turn start (verbal yes / pill click) — the beat itself:
    later = evaluate_start_gate(
        has_pending_plan=True,
        effective_tasks_nonempty=True,
        stamp=_READY_STAMP,
        confirmation=need,
        docked_this_turn=False,
    )
    assert later is None
    # No beat owed — the presentation-time start proceeds (the auto path).
    free = confirmation_need(
        execution="auto", credits="auto",
        quote_high=800, unquotable=False, always_confirm_above=GUARDRAIL,
    )
    assert (
        evaluate_start_gate(
            has_pending_plan=True,
            effective_tasks_nonempty=True,
            stamp=_READY_STAMP,
            confirmation=free,
            docked_this_turn=True,
        )
        is None
    )


def test_gate_authorization_conjunct_yields_to_structural_truth() -> None:
    # Precedence: the structural guards + the projection verdict report
    # before the authorization conjunct (a start that cannot run is not
    # a confirmation question).
    need = confirmation_need(
        execution="auto", credits="auto",
        quote_high=9000, unquotable=False, always_confirm_above=GUARDRAIL,
    )
    stamp = compute_lifecycle(_ready_facts(assets_pending=True))
    verdict = evaluate_start_gate(
        has_pending_plan=True,
        effective_tasks_nonempty=True,
        stamp=stamp,
        confirmation=need,
        docked_this_turn=True,
    )
    assert verdict is not None
    assert verdict.code == "start.blocked"


def test_confirmation_need_unmet_condition_holds_the_auto_regime() -> None:
    """带条件制作授权 (7276ef13 ③ — 「修完开工吧」): a dock that rides a
    turn where the user's requested change was REFUSED (correction cap /
    a superseded correction draft) owes one explicit beat even under full
    auto — the conditional authorization named a fix that never landed, so
    starting the UNFIXED version is never the auto regime's call."""
    need = confirmation_need(
        execution="auto", credits="auto",
        quote_high=120, unquotable=False, always_confirm_above=GUARDRAIL,
        production_intent=True, unmet_condition=True,
    )
    assert need.requires_confirmation
    assert need.reason == "unmet_condition"
    assert need.quote_high == 120
    # The default keeps the pre-existing law byte-for-byte (auto/auto under
    # the guardrail with intent present starts free).
    assert not confirmation_need(
        execution="auto", credits="auto",
        quote_high=120, unquotable=False, always_confirm_above=GUARDRAIL,
        production_intent=True,
    ).requires_confirmation


def test_confirmation_need_unmet_condition_precedence() -> None:
    """Reason order: money first, then the unmet condition, then the bare
    awaiting-production hold (the pill's label follows the money reasons;
    an unmet fix outranks a missing production word)."""
    money = confirmation_need(
        execution="ask", credits="ask",
        quote_high=120, unquotable=False, always_confirm_above=GUARDRAIL,
        production_intent=True, unmet_condition=True,
    )
    assert money.reason == "credits_pref"
    guardrail = confirmation_need(
        execution="auto", credits="auto",
        quote_high=9000, unquotable=False, always_confirm_above=GUARDRAIL,
        production_intent=True, unmet_condition=True,
    )
    assert guardrail.reason == "above_guardrail"
    unquotable = confirmation_need(
        execution="auto", credits="auto",
        quote_high=None, unquotable=True, always_confirm_above=GUARDRAIL,
        production_intent=True, unmet_condition=True,
    )
    assert unquotable.reason == "unquotable"
    intent = confirmation_need(
        execution="auto", credits="auto",
        quote_high=120, unquotable=False, always_confirm_above=GUARDRAIL,
        production_intent=None, unmet_condition=True,
    )
    assert intent.reason == "unmet_condition"
    # …and the same-turn start attempt trips the authorization conjunct.
    need = confirmation_need(
        execution="auto", credits="auto",
        quote_high=120, unquotable=False, always_confirm_above=GUARDRAIL,
        production_intent=True, unmet_condition=True,
    )
    blocked = evaluate_start_gate(
        has_pending_plan=True,
        effective_tasks_nonempty=True,
        stamp=_READY_STAMP,
        confirmation=need,
        docked_this_turn=True,
    )
    assert blocked is not None and blocked.code == "start.needs_confirm"
    assert blocked.reason == "unmet_condition"
    # A LATER-turn explicit start (the user's own beat — a conscious
    # acceptance of the standing version) never trips it.
    assert (
        evaluate_start_gate(
            has_pending_plan=True,
            effective_tasks_nonempty=True,
            stamp=_READY_STAMP,
            confirmation=need,
            docked_this_turn=False,
        )
        is None
    )


# ---- the dock echo's estimate tail (ADR-111 §2) ------------------------------

from app.chat.service import _estimate_tail  # noqa: E402
from app.models.schemas import PlanEstimate  # noqa: E402


def _est() -> PlanEstimate:
    return PlanEstimate(total=[100, 200], per_task=[])


class TestEstimateTail:
    """The disclosure tails key on the dock's stamped confirmation reason
    (BILLING §2.1): guardrail / default / unquotable shapes."""

    def test_reasoned_and_default_tails(self) -> None:
        assert "Estimated" in _estimate_tail("go", _est(), reason="above_guardrail")
        assert "估价" in _estimate_tail("好", _est())
        assert "估价随运行确定" in _estimate_tail("好", None, reason="unquotable")


# ---- ADR-139: auto 只免批准拍，不创造制作意图 ----


def test_production_intent_absent_holds_in_the_full_auto_regime() -> None:
    # A dock born from a message WITHOUT a production request waits in ANY
    # regime — the settings only waive approval beats, they never turn a
    # discussion into an authorization.
    need = confirmation_need(
        execution="auto", credits="auto",
        quote_high=800, unquotable=False, always_confirm_above=GUARDRAIL,
        production_intent=False,
    )
    assert need.requires_confirmation is True
    assert need.reason == "awaiting_production"
    # Unasserted (None) reads as absent — the safe side.
    need_none = confirmation_need(
        execution="auto", credits="auto",
        quote_high=800, unquotable=False, always_confirm_above=GUARDRAIL,
        production_intent=None,
    )
    assert need_none.requires_confirmation is True
    assert need_none.reason == "awaiting_production"


def test_production_intent_present_keeps_the_auto_fast_path() -> None:
    need = confirmation_need(
        execution="auto", credits="auto",
        quote_high=800, unquotable=False, always_confirm_above=GUARDRAIL,
        production_intent=True,
    )
    assert need.requires_confirmation is False
    assert need.reason == ""


def test_production_intent_money_reasons_win_the_label() -> None:
    # A hold that exists for BOTH a money reason and missing intent names
    # the money reason (the pill's priced label follows it).
    need = confirmation_need(
        execution="auto", credits="ask",
        quote_high=120, unquotable=False, always_confirm_above=GUARDRAIL,
        production_intent=False,
    )
    assert need.reason == "credits_pref"
    need2 = confirmation_need(
        execution="auto", credits="auto",
        quote_high=9000, unquotable=False, always_confirm_above=GUARDRAIL,
        production_intent=None,
    )
    assert need2.reason == "above_guardrail"


def test_production_intent_default_true_preserves_non_dock_callers() -> None:
    # The parameter default keeps the pure law's non-dock readers at their
    # pre-ADR-139 behavior; the dock seats always pass the real assertion.
    need = confirmation_need(
        execution="auto", credits="auto",
        quote_high=800, unquotable=False, always_confirm_above=GUARDRAIL,
    )
    assert need.requires_confirmation is False


# ---- 7276ef13 定点收尾②: copy_drift — unproven drift holds the auto start ----


def test_confirmation_need_copy_drift_holds_the_auto_regime() -> None:
    """原文继承守卫 (7276ef13 定点收尾② — 「布局请求中模型误加一句」): a
    dock that rides a turn whose published copy DRIFTED from the
    user-verifiable original owes one explicit beat even under full auto —
    the honest drift note informs, but never green-lights by itself."""
    need = confirmation_need(
        execution="auto", credits="auto",
        quote_high=120, unquotable=False, always_confirm_above=GUARDRAIL,
        production_intent=True, copy_drift=True,
    )
    assert need.requires_confirmation
    assert need.reason == "copy_drift"
    assert need.quote_high == 120
    # The default keeps the pre-existing law byte-for-byte.
    assert not confirmation_need(
        execution="auto", credits="auto",
        quote_high=120, unquotable=False, always_confirm_above=GUARDRAIL,
        production_intent=True,
    ).requires_confirmation


def test_confirmation_need_copy_drift_precedence() -> None:
    """Reason order: money first, then an unmet condition, then the drift
    hold, then the bare awaiting-production hold."""
    money = confirmation_need(
        execution="auto", credits="ask",
        quote_high=120, unquotable=False, always_confirm_above=GUARDRAIL,
        production_intent=True, copy_drift=True,
    )
    assert money.reason == "credits_pref"
    unmet = confirmation_need(
        execution="auto", credits="auto",
        quote_high=120, unquotable=False, always_confirm_above=GUARDRAIL,
        production_intent=True, unmet_condition=True, copy_drift=True,
    )
    assert unmet.reason == "unmet_condition"
    intent = confirmation_need(
        execution="auto", credits="auto",
        quote_high=120, unquotable=False, always_confirm_above=GUARDRAIL,
        production_intent=None, copy_drift=True,
    )
    assert intent.reason == "copy_drift"
    # …and the same-turn start attempt trips the authorization conjunct;
    # a LATER-turn explicit start (a conscious acceptance of the drifted
    # copy) never trips it.
    need = confirmation_need(
        execution="auto", credits="auto",
        quote_high=120, unquotable=False, always_confirm_above=GUARDRAIL,
        production_intent=True, copy_drift=True,
    )
    blocked = evaluate_start_gate(
        has_pending_plan=True,
        effective_tasks_nonempty=True,
        stamp=_READY_STAMP,
        confirmation=need,
        docked_this_turn=True,
    )
    assert blocked is not None and blocked.code == "start.needs_confirm"
    assert blocked.reason == "copy_drift"
    assert (
        evaluate_start_gate(
            has_pending_plan=True,
            effective_tasks_nonempty=True,
            stamp=_READY_STAMP,
            confirmation=need,
            docked_this_turn=False,
        )
        is None
    )


def test_estimate_tail_copy_drift_names_the_two_honest_outs() -> None:
    """The drift tail states the choice honestly: confirm starts THIS
    (drifted) version, or say the word and the original is restored."""
    tail_en = _estimate_tail("go", _est(), reason="copy_drift")
    assert "differs from the text you gave" in tail_en
    assert "restore your original" in tail_en
    tail_zh = _estimate_tail("好", _est(), reason="copy_drift")
    assert "有出入" in tail_zh and "恢复原文" in tail_zh
    # The estimate-absent half keeps the same choice statement.
    tail_zh_none = _estimate_tail("好", None, reason="copy_drift")
    assert "有出入" in tail_zh_none and "恢复原文" in tail_zh_none
    assert "Estimate" not in tail_zh_none
