"""Tests for the sliding-window assembly predicate (ADR-117 D4 — B4).

Pure coverage only (no DB, no LLM, no HTTP — ``bounded_history`` /
``estimate_message_tokens`` are the units under test; the config funnel
seat ``recent_history_within_budget`` is a one-line get_config wrapper and
is covered by the live paths). The locked matrix (验收: 窗口边界 /
世界状态幸存):

- under budget → the whole history rides unchanged
- over budget → the newest suffix that fits survives, dropped from the
  front only (the window is ALWAYS a suffix — the only prefix-cache-lawful
  shape)
- the newest row ALWAYS survives, even when it alone busts the budget
- payload mass counts: question/answer JSON rides the estimate
- 世界状态幸存: the predicate's only input is the message list — world
  state (project summary / graph / pending line) never enters this fold
  by construction; what the window returns is exactly a suffix of what it
  was given, never a mutation
"""

from app.chat.context import bounded_history, estimate_message_tokens
from app.models.tables import Message


def _msg(content: str, **kwargs) -> Message:
    return Message(role="user", content=content, **kwargs)


def test_under_budget_keeps_everything() -> None:
    history = [_msg("short") for _ in range(10)]
    assert bounded_history(history, 120000) == history


def test_over_budget_keeps_the_newest_suffix_that_fits() -> None:
    # 44 tokens per row (160 chars / 4 + 4 overhead); budget 100 → the
    # newest two rows (88) fit, the third (132) busts.
    history = [_msg("x" * 160) for _ in range(5)]
    kept = bounded_history(history, 100)
    assert kept == history[-2:]


def test_exact_boundary_fits_and_one_less_folds() -> None:
    history = [_msg("x" * 160) for _ in range(3)]  # 44 tokens each
    assert bounded_history(history, 88) == history[-2:]
    assert bounded_history(history, 87) == history[-1:]


def test_the_newest_row_always_survives() -> None:
    history = [_msg("tiny"), _msg("x" * 40000)]  # newest alone busts 100
    assert bounded_history(history, 100) == history[-1:]


def test_empty_history_stays_empty() -> None:
    assert bounded_history([], 100) == []


def test_non_positive_budget_degenerates_to_the_newest_row() -> None:
    history = [_msg("a"), _msg("b")]
    assert bounded_history(history, 0) == history[-1:]


def test_payload_mass_rides_the_estimate() -> None:
    plain = _msg("x" * 160)
    with_question = _msg(
        "x" * 160, question={"question": "q" * 400, "options": []}
    )
    assert estimate_message_tokens(with_question) > estimate_message_tokens(plain)


def test_the_window_is_always_a_suffix_never_a_mutation() -> None:
    # 世界状态幸存's message-side tooth: folding only ever drops from the
    # front — the returned rows are the SAME row objects in the SAME order
    # (world state is never in this list to begin with; nothing here is
    # rewritten, truncated, or summarized).
    history = [_msg("x" * 160) for _ in range(6)]
    kept = bounded_history(history, 100)
    assert kept == history[-2:]
    assert all(kept_row is source for kept_row, source in zip(kept, history[-2:]))
