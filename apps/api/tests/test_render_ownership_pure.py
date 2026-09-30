"""Pure tests for the render-ownership transition laws (ADR-096 batch A).

No DB / no LLM / no HTTP: the decision kernels are pure folds — the SQL
seats filter structural eligibility (run / kind / seq / fork / scope) and
hand plain data to these:

- ``later_active_morph_exists`` — the D2-status defer law: a later morph
  owns the render only while its step can still write
  (pending/running/waiting). A terminal morph (done/failed/skipped) never
  suppresses a render it will never own (the black-card incident's root:
  the seq-ordered defer looked at a "future" that had already happened).

SQL-layer behavior (row-lock ordering, the actual claim/claim CAS) belongs
to the e2e reruns, never to this suite (repo convention).
"""

from app.pipeline.morph import (
    _ACTIVE_MORPH_STATUSES,
    later_active_morph_exists,
)


# ---- the defer law's truth table (D2-status) ---------------------------------


class TestLaterActiveMorphExists:
    def test_pending_counts(self) -> None:
        assert later_active_morph_exists(["pending"]) is True

    def test_running_counts(self) -> None:
        assert later_active_morph_exists(["running"]) is True

    def test_waiting_counts(self) -> None:
        """A parked interrupt (direction / verify escalation) revives via
        resume_waiting_interrupt — it is a future writer, not a corpse."""
        assert later_active_morph_exists(["waiting"]) is True

    def test_done_never_suppresses(self) -> None:
        """The incident's exact shape: the later-seq morph finished FIRST —
        deferring to it strands the render with no owner."""
        assert later_active_morph_exists(["done"]) is False

    def test_failed_never_suppresses(self) -> None:
        assert later_active_morph_exists(["failed"]) is False

    def test_skipped_never_suppresses(self) -> None:
        assert later_active_morph_exists(["skipped"]) is False

    def test_empty_is_false(self) -> None:
        assert later_active_morph_exists([]) is False

    def test_any_active_among_terminal_wins(self) -> None:
        assert later_active_morph_exists(["done", "failed", "running"]) is True
        assert later_active_morph_exists(["done", "waiting"]) is True

    def test_status_vocabulary_pinned(self) -> None:
        """The workflow_steps status vocabulary is pending / running /
        waiting / done / failed / skipped — the active set is exactly the
        non-terminal half."""
        assert set(_ACTIVE_MORPH_STATUSES) == {"pending", "running", "waiting"}
        assert not (
            set(_ACTIVE_MORPH_STATUSES) & {"done", "failed", "skipped"}
        )
