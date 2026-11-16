"""Pure tests for the render-ownership laws (ADR-096 batches A + D).

No DB / no LLM / no HTTP: the decision kernels are pure folds — the SQL
seats filter structural eligibility (run / kind / seq / fork / scope) and
hand plain data to these:

- ``writer_steps_for_output`` — the batch-D compile-static writer fold: one
  output's writer steps (birth step + every non-fork in-place morph whose
  scope covers the row), seq-ordered, the last entry the render owner. The
  fold errs WIDE: over-inclusion (a morph that skips the row) lifts its
  barrier slot on completion anyway; under-inclusion is the only real error
  (an early render reading a partial spec — the black-card incident).
- ``prune_writer_barrier`` — the failure-repair fold: closed (failed /
  cascade-skipped) writers drop out of a barrier so the survivors' spec
  honestly renders.
- ``render_delivery`` — the verify node's refusal of false completion:
  file present + render COMPLETED, with in-flight and honestly-failed
  states abstaining (无确定性依据不判决).
- ``needs_render_reconcile`` — the finalize reconcile's orphan predicate:
  repair mechanism only, idempotent by construction.

SQL-layer behavior (row-lock ordering, the actual claim/claim CAS, the
barrier predicate inside ``claim_pending_render``) belongs to the e2e
reruns, never to this suite (repo convention).
"""

from app.pipeline.quality import failed_checks, render_delivery
from app.pipeline.render_ownership import (
    CLIPS_PRODUCER_KINDS,
    CLOSED_STEP_STATUSES,
    INPLACE_MORPH_KINDS,
    StepView,
    needs_render_reconcile,
    prune_writer_barrier,
    writer_steps_for_output,
)


def _sv(
    id: str,
    kind: str,
    seq: int,
    inputs: tuple[str, ...] = (),
    *,
    fork: bool = False,
    target: str | None = None,
) -> StepView:
    return StepView(
        id=id, kind=kind, seq=seq, inputs=inputs, fork=fork, target_output_id=target
    )


# ---- the compile-static writer fold (batch D) ---------------------------------


class TestWriterStepsForOutput:
    def test_run_born_base_chain(self) -> None:
        """producer + two parallel non-fork morphs wired off it: all three
        are writers, seq-ordered, the last morph the owner."""
        steps = [
            _sv("p", "select_clips", 1),
            _sv("t", "translate_clip", 2, ("p",)),
            _sv("r", "reframe_clip", 3, ("p",)),
        ]
        assert writer_steps_for_output(steps, birth_step_id="p", output_id="o1") == [
            "p",
            "t",
            "r",
        ]

    def test_owner_is_last_by_seq_not_listing_order(self) -> None:
        """The fold reads seq, never the iteration order of the step list."""
        steps = [
            _sv("r", "reframe_clip", 3, ("p",)),
            _sv("t", "translate_clip", 2, ("p",)),
            _sv("p", "select_clips", 1),
        ]
        assert writer_steps_for_output(steps, birth_step_id="p", output_id="o1") == [
            "p",
            "t",
            "r",
        ]

    def test_fork_morph_never_writes_the_base_row(self) -> None:
        """A fork derives its OWN rows — the base row's barrier is the
        producer alone; the derived row's barrier is the fork step alone."""
        steps = [
            _sv("p", "select_clips", 1),
            _sv("t", "translate_clip", 2, ("p",), fork=True),
        ]
        assert writer_steps_for_output(steps, birth_step_id="p", output_id="o1") == ["p"]
        assert writer_steps_for_output(steps, birth_step_id="t", output_id="o2") == ["t"]

    def test_mutator_chain_all_writers(self) -> None:
        """remove_filler mutates the shared spec — a variant chained behind
        it holds BOTH the producer and the mutator in inputs; all three
        write the row."""
        steps = [
            _sv("p", "select_clips", 1),
            _sv("f", "remove_filler", 2, ("p",)),
            _sv("t", "translate_clip", 3, ("p", "f")),
        ]
        assert writer_steps_for_output(steps, birth_step_id="p", output_id="o1") == [
            "p",
            "f",
            "t",
        ]

    def test_target_scoped_morph_excluded_from_run_born_rows(self) -> None:
        """The scope was pinned at compile time — a run-born row was unborn
        then, so a target-scoped morph can never name it."""
        steps = [
            _sv("p", "select_clips", 1),
            _sv("t", "translate_clip", 2, ("p",), target="o-other"),
        ]
        assert writer_steps_for_output(steps, birth_step_id="p", output_id="o1") == ["p"]

    def test_two_producers_each_row_owns_its_chain(self) -> None:
        """A morph wired off producer p2 never writes p1's rows — the
        multi-output fork law: each owner waits only for its own writers."""
        steps = [
            _sv("p1", "select_clips", 1),
            _sv("p2", "materialize_source", 2),
            _sv("t", "translate_clip", 3, ("p2",)),
        ]
        assert writer_steps_for_output(steps, birth_step_id="p1", output_id="o1") == ["p1"]
        assert writer_steps_for_output(steps, birth_step_id="p2", output_id="o2") == [
            "p2",
            "t",
        ]

    def test_existing_profile_morphs_cover_preexisting_rows(self) -> None:
        """No clips producer in the run's morph inputs → the morph targets
        the project's pre-existing clips, so it covers every such row
        (birth step absent from this run)."""
        steps = [
            _sv("pp", "preprocess", 1),
            _sv("t", "translate_clip", 2, ("pp",)),
            _sv("d", "dub_clip", 3, ("pp",)),
        ]
        assert writer_steps_for_output(steps, birth_step_id=None, output_id="o-old") == [
            "t",
            "d",
        ]
        # A birth step id pointing outside this run (earlier run's row) is
        # the same case.
        assert writer_steps_for_output(steps, birth_step_id="ghost", output_id="o-old") == [
            "t",
            "d",
        ]

    def test_producer_wired_morph_never_covers_preexisting_rows(self) -> None:
        """The run births its own clips and morphs them; a pre-existing row
        of the project is NOT in scope — empty barrier (the row is not this
        run's to render)."""
        steps = [
            _sv("p", "select_clips", 1),
            _sv("t", "translate_clip", 2, ("p",)),
        ]
        assert writer_steps_for_output(steps, birth_step_id=None, output_id="o-old") == []

    def test_target_scoped_morph_covers_exactly_its_named_row(self) -> None:
        steps = [
            _sv("p", "select_clips", 1),
            _sv("t", "translate_clip", 2, ("p",), target="o-old"),
        ]
        assert writer_steps_for_output(steps, birth_step_id=None, output_id="o-old") == ["t"]
        assert writer_steps_for_output(steps, birth_step_id=None, output_id="o-other") == []

    def test_fork_scoped_out_of_preexisting_coverage(self) -> None:
        """Fork morphs derive new rows even on the existing profile — the
        pre-existing base row keeps no writer but its own (empty) set."""
        steps = [
            _sv("t", "translate_clip", 1, (), fork=True),
            _sv("r", "reframe_clip", 2, ()),
        ]
        assert writer_steps_for_output(steps, birth_step_id=None, output_id="o-old") == ["r"]

    def test_non_morph_steps_never_writers(self) -> None:
        """verify / render / preprocess rows sit in a run's step list too —
        the fold only ever names the birth step + in-place morphs."""
        steps = [
            _sv("p", "select_clips", 1),
            _sv("t", "translate_clip", 2, ("p",)),
            _sv("v", "verify", 3, ("p", "t")),
            _sv("m", "render", 4, ("p", "t")),
        ]
        assert writer_steps_for_output(steps, birth_step_id="p", output_id="o1") == [
            "p",
            "t",
        ]

    def test_kind_vocabularies_pinned(self) -> None:
        """The fold's three vocabularies are load-bearing — a new in-place
        morph kind must register here AND in the fold (this test is the
        drift alarm)."""
        assert set(INPLACE_MORPH_KINDS) == {
            "translate_clip",
            "dub_clip",
            "remove_filler",
            "add_music",
            "reframe_clip",
        }
        assert set(CLIPS_PRODUCER_KINDS) == {
            "select_clips",
            "materialize_source",
            "cut_segments",
        }
        assert set(CLOSED_STEP_STATUSES) == {"failed", "skipped"}


# ---- the failure-repair fold ---------------------------------------------------


class TestPruneWriterBarrier:
    def test_closed_writers_drop_order_preserved(self) -> None:
        assert prune_writer_barrier(["p", "t", "r"], {"t"}) == ["p", "r"]

    def test_all_closed_empties(self) -> None:
        """An emptied barrier lifts immediately — every writer the chain
        could still hear from is settled."""
        assert prune_writer_barrier(["p", "t"], {"p", "t"}) == []

    def test_nothing_closed_is_identity(self) -> None:
        assert prune_writer_barrier(["p", "t"], {"x"}) == ["p", "t"]
        assert prune_writer_barrier(["p", "t"], set()) == ["p", "t"]

    def test_empty_barrier_stays_empty(self) -> None:
        assert prune_writer_barrier([], {"p"}) == []


# ---- verify's false-completion refusal (render_delivery) ----------------------


class TestRenderDelivery:
    def test_no_render_contract_skips(self) -> None:
        c = render_delivery(None, False, has_render_spec=False)
        assert c.ok is None

    def test_completed_with_file_passes(self) -> None:
        c = render_delivery("completed", True, has_render_spec=True)
        assert c.ok is True

    def test_null_status_fails_and_gates(self) -> None:
        """The ownership hole: every writer settled and nobody pended the
        render — bounce-worthy (fidelity class, never craft escalation)."""
        c = render_delivery(None, False, has_render_spec=True)
        assert c.ok is False
        assert c.cls == "fidelity"
        assert failed_checks([c]) == [c]

    def test_completed_without_file_fails_and_gates(self) -> None:
        """Terminal contradiction: the COMPLETED write carries files
        atomically, so a missing video key means corruption."""
        c = render_delivery("completed", False, has_render_spec=True)
        assert c.ok is False
        assert c.cls == "fidelity"
        assert failed_checks([c]) == [c]

    def test_in_flight_abstains(self) -> None:
        """Pending/rendering are owned by the render chain — verify races
        renders by design (D2), so an in-flight render is never a verdict."""
        for status in ("pending", "rendering"):
            c = render_delivery(status, False, has_render_spec=True)
            assert c.ok is None, status
            assert failed_checks([c]) == []

    def test_failed_abstains(self) -> None:
        """An honest failure the render mirror + the closing review's
        render_failed gap already surface — double-gating it would bounce
        the generation executor for a render-service fault."""
        c = render_delivery("failed", False, has_render_spec=True)
        assert c.ok is None
        assert failed_checks([c]) == []


# ---- the finalize reconcile's orphan predicate --------------------------------


class TestNeedsRenderReconcile:
    def test_orphan_shape_matches(self) -> None:
        """spec present + never requested + live + no pending render step."""
        assert (
            needs_render_reconcile(
                has_render_spec=True,
                render_status=None,
                archived=False,
                has_pending_render_step=False,
            )
            is True
        )

    def test_each_flag_individually_excludes(self) -> None:
        base = {
            "has_render_spec": True,
            "render_status": None,
            "archived": False,
            "has_pending_render_step": False,
        }
        assert needs_render_reconcile(**{**base, "has_render_spec": False}) is False
        assert needs_render_reconcile(**{**base, "archived": True}) is False
        assert (
            needs_render_reconcile(**{**base, "has_pending_render_step": True})
            is False
        )

    def test_any_requested_status_excludes(self) -> None:
        """Idempotency: once reconciled the row is PENDING and the predicate
        never matches again — repeat finalizes are no-ops by construction."""
        for status in ("pending", "rendering", "completed", "failed"):
            assert (
                needs_render_reconcile(
                    has_render_spec=True,
                    render_status=status,
                    archived=False,
                    has_pending_render_step=False,
                )
                is False
            ), status

    def test_archived_never_repended(self) -> None:
        """The claim gate never picks archived rows — re-pending one would
        pend a render no worker ever claims (run held open forever)."""
        assert (
            needs_render_reconcile(
                has_render_spec=True,
                render_status=None,
                archived=True,
                has_pending_render_step=False,
            )
            is False
        )
