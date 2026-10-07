"""Pure tests for the speaker_map form gate's aggregate law (形态是统计
不是绝对值) and the face_scan digest derivation.

No DB, no LLM, no cv2 — the seams under test take plain per-sample face
count lists. The law: the people count is the majority of face-bearing
samples (a third person in a few frames never upgrades the form), and the
digest derives the two span families downstream editing reuses.
"""

from app.pipeline.speaker_map import (
    SCAN_STRIDE_S,
    _face_scan_digest,
    _majority_people,
    _runs,
)


# ---- _majority_people --------------------------------------------------------


def test_majority_unanimous_two():
    assert _majority_people([2] * 170) == (2, 1.0, 170)


def test_majority_holds_against_occasional_extra_person():
    # An interview with audience cutaways: a few 3-person frames NEVER
    # upgrade the form to multi (the 2026-10-06 misjudgment's fix).
    counts = [2] * 160 + [3] * 8 + [0] * 4
    people, share, faced = _majority_people(counts)
    assert people == 2
    assert faced == 168  # zero-face frames don't dilute
    assert abs(share - 160 / 168) < 1e-9


def test_no_strict_majority_reads_unknown_never_a_coin_flip():
    # 1:3, 2:3, 3:3 among faced samples — no >50% winner.
    people, share, faced = _majority_people([1, 1, 1, 2, 2, 2, 3, 3, 3])
    assert people == 0
    assert faced == 9
    assert abs(share - 1 / 3) < 1e-9


def test_exactly_half_is_not_a_majority():
    people, _share, _faced = _majority_people([1, 1, 2, 2])
    assert people == 0


def test_three_plus_collapses_to_one_bucket():
    # 4-person frames and 5-person frames are the same "multi" bucket.
    assert _majority_people([4, 5, 3, 4]) == (3, 1.0, 4)


def test_all_faceless_is_unknown():
    assert _majority_people([0, 0, 0]) == (0, 0.0, 0)


def test_empty_scan_is_unknown():
    assert _majority_people([]) == (0, 0.0, 0)


# ---- _runs -------------------------------------------------------------------


def test_runs_basic_and_min_length():
    # stride 2s: indices 2-3 qualify (2 samples = 4s), index 6 alone is a blip.
    counts = [2, 2, 0, 0, 2, 2, 0, 2]
    assert _runs(counts, lambda c: c == 0) == [[4.0, 8.0]]


def test_runs_trailing_run_at_eof():
    counts = [1, 1, 0, 0]
    assert _runs(counts, lambda c: c == 0) == [[4.0, 8.0]]


def test_runs_none_qualify():
    assert _runs([2, 2, 2], lambda c: c == 0) == []


# ---- _face_scan_digest --------------------------------------------------------


def test_digest_interview_with_audience_cutaways():
    counts = [2] * 10 + [3, 3] + [2] * 8 + [0, 0] + [2] * 5
    people, share, _faced = _majority_people(counts)
    d = _face_scan_digest(counts, people, share)
    assert d["version"] == 1
    assert d["stride_s"] == SCAN_STRIDE_S
    assert d["counts"] == counts
    assert d["majority"] == 2
    # extra people at samples 10-11 → 20s~24s; face-free at 20-21 → 40s~44s.
    assert d["extra_people_spans"] == [[20.0, 24.0]]
    assert d["face_free_spans"] == [[40.0, 44.0]]


def test_digest_no_majority_has_no_extra_people_spans():
    counts = [1, 1, 2, 2]
    people, share, _faced = _majority_people(counts)
    assert people == 0
    d = _face_scan_digest(counts, people, share)
    assert d["extra_people_spans"] == []
    assert d["face_free_spans"] == []


def test_digest_all_faceless_everything_is_free():
    counts = [0, 0, 0, 0]
    d = _face_scan_digest(counts, 0, 0.0)
    assert d["face_free_spans"] == [[0.0, 8.0]]
    assert d["extra_people_spans"] == []
