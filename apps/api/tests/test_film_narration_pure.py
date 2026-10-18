"""Pure tests for the film narration window flex (app/tools/film/narration.py,
ADR-136) — the bounded zero-sum rescue between an exhausted speed ladder and
the honest failure.

No DB, no LLM, no provider IO (suite discipline): what's gated HERE is the
flex's pure core contract —

- zero-sum: Σ frames (the film's total runtime, the pre-metered seconds)
  NEVER moves;
- doubly bounded: a silent donor never loses more than 30% of its frames
  across ALL steals and never dips under its structural floor; a narrated
  receiver never gains more than 40% on top of its own frames;
- narrated scenes NEVER donate (their own audio fits their window);
- deterministic: donors give in descending spare capacity, ties by scene
  order;
- an uncoverable shortfall returns None — the caller fails honestly with
  the real attempts AND the tried flex named (the pre-flex law).

Test durations are built with a half-frame float margin so ``ceil()`` never
wobbles on binary representation edges — the contract under test is the
steal logic, not float luck.
"""

from app.tools.film.narration import (
    _FLEX_DONOR_MAX_FRAC,
    _FLEX_STRETCH_MAX_FRAC,
    _WINDOW_ALLOW,
    _flex_frames_for_overruns,
)

_FPS = 30


def _duration_for(window_frames: int, need_frames: int) -> float:
    """The decoded seconds that asks for exactly ``need_frames`` on top of
    the scene's window — half a frame under the integer boundary so the
    implementation's ceil lands on it regardless of float wobble."""
    return (window_frames + need_frames - 0.5) / _FPS + _WINDOW_ALLOW


def test_the_incident_shape_steals_from_the_roomiest_silent_scene() -> None:
    # The 7048c4b4 shape: a ≈4.4s narrated scene whose line outruns the
    # whole speed ladder — 7 frames short. Silent scenes: a 2s cold open,
    # a divider near its roll floor, a 3s walk (the roomiest).
    frames = [60, 131, 64, 90, 75]
    floors = [30, 30, 51, 30, 75]
    verdict = _flex_frames_for_overruns(
        frames=frames,
        floors=floors,
        silent={0, 2, 3, 4},
        overruns={1: _duration_for(131, 7)},
        fps=_FPS,
    )
    assert verdict is not None
    adjusted, moves = verdict
    assert adjusted[1] == 131 + 7
    assert adjusted[3] == 90 - 7  # the roomiest donor gives it all
    assert adjusted[0] == 60 and adjusted[2] == 64 and adjusted[4] == 75
    assert sum(adjusted) == sum(frames)  # zero-sum — total runtime unmoved
    assert moves == [
        {
            "scene": 1,
            "gained_s": round(7 / _FPS, 2),
            "donors": [{"scene": 3, "gave_s": round(7 / _FPS, 2)}],
        }
    ]


def test_receiver_stretch_cap_binds() -> None:
    # The scene may never gain more than 40% over its own frames — beyond
    # that the fix is a redesign, never a rescue.
    frames = [90, 131, 90]
    max_gain = int(frames[1] * _FLEX_STRETCH_MAX_FRAC)
    assert _flex_frames_for_overruns(
        frames=frames, floors=[30, 30, 30], silent={0, 2},
        overruns={1: _duration_for(131, max_gain)}, fps=_FPS,
    ) is not None
    assert (
        _flex_frames_for_overruns(
            frames=frames, floors=[30, 30, 30], silent={0, 2},
            overruns={1: _duration_for(131, max_gain + 1)}, fps=_FPS,
        )
        is None
    )


def test_donor_cap_and_floor_bind_together() -> None:
    # One tiny silent scene: min(floor slack, 30% cap) can't cover a real
    # shortfall → None (the honest failure).
    frames = [35, 131]
    assert (
        _flex_frames_for_overruns(
            frames=frames, floors=[30, 30], silent={0},
            overruns={1: _duration_for(131, 22)}, fps=_FPS,
        )
        is None
    )


def test_narrated_scenes_never_donate() -> None:
    # A narrated scene's audio fits its own window — shrinking it would
    # break that fit. Only the silent scene gives; when it can't cover,
    # None.
    frames = [90, 131, 60]
    assert (
        _flex_frames_for_overruns(
            frames=frames, floors=[30, 30, 30], silent={2},
            overruns={1: _duration_for(131, 19)}, fps=_FPS,
        )
        is None
    )


def test_donor_cap_spans_multiple_steals() -> None:
    # Two scenes overrun; the single silent donor's 30% cap is a LIFETIME
    # budget across both steals — the second steal gets only the remainder
    # and the verdict is None when it falls short.
    frames = [120, 131, 131]
    donor_budget = int(frames[0] * _FLEX_DONOR_MAX_FRAC)
    assert 19 <= donor_budget < 2 * 19  # one steal fits, two don't
    assert (
        _flex_frames_for_overruns(
            frames=frames, floors=[30, 30, 30], silent={0},
            overruns={1: _duration_for(131, 19), 2: _duration_for(131, 19)},
            fps=_FPS,
        )
        is None
    )
    # …while a single overrun over the same donor resolves.
    verdict = _flex_frames_for_overruns(
        frames=frames, floors=[30, 30, 30], silent={0},
        overruns={1: _duration_for(131, 19)}, fps=_FPS,
    )
    assert verdict is not None
    adjusted, _ = verdict
    assert adjusted[0] == frames[0] - 19
    assert adjusted[1] == frames[1] + 19
    assert adjusted[2] == frames[2]


def test_donor_order_is_deterministic() -> None:
    # Equal spare capacity → the lower scene index gives first.
    frames = [90, 131, 90]
    verdict = _flex_frames_for_overruns(
        frames=frames, floors=[30, 30, 30], silent={0, 2},
        overruns={1: _duration_for(131, 19)}, fps=_FPS,
    )
    assert verdict is not None
    _, moves = verdict
    assert [d["scene"] for d in moves[0]["donors"]] == [0]


def test_no_overrun_is_a_passthrough() -> None:
    frames = [60, 131, 90]
    adjusted, moves = _flex_frames_for_overruns(
        frames=frames, floors=[30, 30, 30], silent={0, 2},
        overruns={}, fps=_FPS,
    )
    assert adjusted == frames
    assert moves == []
