"""Pure tests for the archive invariant's wipe law (ADR-091, N-59 — S1).

No DB, no LLM, no HTTP. The matrix locks the three pure helpers that carry
the archive invariant's mechanical core (app.pipeline.outputs):

- ``partition_by_run`` — the delivery-status partition law: a doomed row
  produced by a step of the CURRENT run is mid-production (physical delete,
  no history rights); anything else (an earlier run's delivered row, or a
  legacy NULL-step row) earns the archive.
- ``pair_work_inheritance`` — positional work_id inheritance: the i-th
  newborn continues the i-th archived row's work (oldest first); extra
  newborns start fresh works (None = the column default fires).
- ``next_work_id`` — the per-birth pop: returns a kwargs dict so a birth
  can ``**next_work_id(...)``; an empty chain yields ``{}`` — never an
  explicit ``work_id=None`` (NULL violates NOT NULL).
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.pipeline.outputs import (
    VersionSwitchRejected,
    next_work_id,
    pair_work_inheritance,
    partition_by_run,
    plan_version_switch,
)


def _triple(step_id):
    return (uuid4(), uuid4(), step_id)


class TestPartitionByRun:
    def test_current_run_step_is_physical(self):
        step = uuid4()
        physical, archive = partition_by_run([_triple(step)], {step})
        assert len(physical) == 1 and archive == []

    def test_other_run_step_is_archived(self):
        row = _triple(uuid4())
        physical, archive = partition_by_run([row], {uuid4()})
        assert physical == [] and archive == [row[0]]

    def test_legacy_null_step_is_archived(self):
        row = _triple(None)
        physical, archive = partition_by_run([row], {uuid4()})
        assert physical == [] and archive == [row[0]]

    def test_mixed_set_splits_and_preserves_order(self):
        s1, s2 = uuid4(), uuid4()
        r_phys1, r_arch1, r_phys2, r_arch2 = (
            _triple(s1), _triple(s2), _triple(s1), _triple(None),
        )
        physical, archive = partition_by_run(
            [r_phys1, r_arch1, r_phys2, r_arch2], {s1}
        )
        assert physical == [r_phys1[0], r_phys2[0]]
        assert archive == [r_arch1[0], r_arch2[0]]

    def test_empty_input(self):
        assert partition_by_run([], {uuid4()}) == ([], [])


class TestPairWorkInheritance:
    def test_positional_continuation_oldest_first(self):
        w1, w2 = uuid4(), uuid4()
        archived = [(uuid4(), w1), (uuid4(), w2)]
        assert pair_work_inheritance(archived, 2) == [w1, w2]

    def test_extra_newborns_start_fresh(self):
        w1 = uuid4()
        archived = [(uuid4(), w1)]
        assert pair_work_inheritance(archived, 3) == [w1, None, None]

    def test_fewer_newborns_than_archived(self):
        w1, w2 = uuid4(), uuid4()
        archived = [(uuid4(), w1), (uuid4(), w2)]
        assert pair_work_inheritance(archived, 1) == [w1]

    def test_no_archived_all_fresh(self):
        assert pair_work_inheritance([], 2) == [None, None]

    def test_zero_newborns(self):
        assert pair_work_inheritance([(uuid4(), uuid4())], 0) == []


class TestNextWorkId:
    def test_pops_oldest_first(self):
        w1, w2 = uuid4(), uuid4()
        chain = {"clip": [w1, w2]}
        assert next_work_id(chain, "clip") == {"work_id": w1}
        assert next_work_id(chain, "clip") == {"work_id": w2}
        assert next_work_id(chain, "clip") == {}

    def test_empty_chain_yields_empty_kwargs_never_none(self):
        assert next_work_id({}, "clip") == {}
        assert next_work_id({"clip": []}, "clip") == {}

    def test_chains_are_per_type(self):
        w_clip, w_frame = uuid4(), uuid4()
        chain = {"clip": [w_clip], "quote_frame": [w_frame]}
        assert next_work_id(chain, "quote_frame") == {"work_id": w_frame}
        assert next_work_id(chain, "clip") == {"work_id": w_clip}
        assert next_work_id(chain, "clip") == {}


def _row(work_id, archived: bool):
    from datetime import UTC, datetime

    return SimpleNamespace(
        id=uuid4(),
        work_id=work_id,
        archived_at=datetime.now(UTC) if archived else None,
    )


class TestPlanVersionSwitch:
    """换态 law (ADR-091 §2): target must be archived; same-work active
    siblings demote; at most one active per work after the swap."""

    def test_active_target_rejected(self):
        w = uuid4()
        with pytest.raises(VersionSwitchRejected):
            plan_version_switch(_row(w, archived=False), [])

    def test_archived_target_demotes_same_work_active(self):
        w = uuid4()
        target = _row(w, archived=True)
        active = _row(w, archived=False)
        demoted = plan_version_switch(target, [active])
        assert [r.id for r in demoted] == [active.id]

    def test_other_work_siblings_untouched(self):
        w, other = uuid4(), uuid4()
        target = _row(w, archived=True)
        mine = _row(w, archived=False)
        foreign_active = _row(other, archived=False)
        demoted = plan_version_switch(target, [mine, foreign_active])
        assert [r.id for r in demoted] == [mine.id]

    def test_already_archived_siblings_not_redemoted(self):
        w = uuid4()
        target = _row(w, archived=True)
        old = _row(w, archived=True)
        assert plan_version_switch(target, [old]) == []

    def test_target_excluded_even_if_listed(self):
        w = uuid4()
        target = _row(w, archived=True)
        assert plan_version_switch(target, [target]) == []
