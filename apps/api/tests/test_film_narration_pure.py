"""Pure integration tests for ``synthesize_film_narration``'s store seat
(ADR-138 R4-A; no DB, no LLM, no HTTP — provider, metering, storage and the
store seats are all stubbed in the module namespace).

What is locked here (the synthesis path's behavioral laws; the store's own
concurrency laws are DB-proven by ``scratch/film_narration_store_check.py``):

1. **命中且适配 = 零合成零计费** — a hash hit whose 1.0 original fits the
   window never calls the provider, never bills, and the spec rides the
   store's object key.
2. **命中不适配 = 运行期适配（重新合成，计量）** — the ladder resumes from
   the KNOWN 1.0 duration with a REAL provider call at the computed speed
   (pass 2; the tests pin the call AND the metered characters — never a
   free local transform of the original's bytes), the adapted product lands
   at the per-output staging key, and the store is never written.
3. **未命中 = 先发布原件再判适配** — the miss path's pass 1 is published as
   the speed-1.0 original BEFORE the fit verdict; a fit rides the committed
   store key (no per-output copy), an unfit line still adapts into its own
   staging file.
4. **straddle 成对律** — a finalize that loses ownership returns the
   WINNER's (key, duration) pair; the two never decouple.
5. **失败不留毒** — a provider failure on the miss path deletes our own
   placeholder; a published original survives a later honest fit failure.
6. **store 等待超时 = voice_unavailable** — a budget exhaustion reads as a
   transient voice condition, never the design-failure key.

The file's second layer (§6) gates the window flex's PURE core
(``_flex_frames_for_overruns``, ADR-136) — the bounded zero-sum rescue
between an exhausted speed ladder and the honest failure:

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

Flex test durations are built with a half-frame float margin so
``ceil()`` never wobbles on binary representation edges — the contract
under test is the steal logic, not float luck.
"""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.schemas import FilmSceneWords, FilmStoryboard
from app.providers.voice import VoiceError
from app.tools.film import narration
from app.tools.film.narration import (
    _FLEX_DONOR_MAX_FRAC,
    _FLEX_STRETCH_MAX_FRAC,
    _WINDOW_ALLOW,
    _flex_frames_for_overruns,
)
from app.tools.film.narration_store import NarrationReuse

_VOICE = "presenter_male"
_LANG = "en"


def _words(seconds: float, narration_text: str | None = None) -> FilmSceneWords:
    return FilmSceneWords(
        type="words", seconds=seconds, dark=True, lines=["line"], narration=narration_text
    )


def _project() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), user_id=uuid4())


class _World:
    """The stubbed seats around ``synthesize_film_narration``: provider
    (scripted durations by requested speed), metering, storage, and the
    store trio. The synthesize stub encodes the scripted duration into the
    bytes; the decode stub reads it back — decode-and-count stays real code
    path shaped without a codec."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *, reuse: NarrationReuse | BaseException,
                 durations: dict[float, float], finalize_result: tuple[str, float] | None = None,
                 synthesize_error: Exception | None = None):
        self.calls: dict[str, list] = {
            "synthesize": [], "bills": [], "finalize": [], "fail": [],
        }
        self.saved: dict[str, bytes] = {}

        async def _resolve(project_id, *, text, voice_id, language, config=None):
            if isinstance(reuse, BaseException):
                raise reuse
            return reuse

        def _synthesize(text, voice_id, language="en", speed=1.0):
            if synthesize_error is not None:
                raise synthesize_error
            key = round(speed, 4)
            self.calls["synthesize"].append((text, voice_id, language, key))
            return f"D{durations[key]}".encode()

        def _decode(data: bytes) -> float:
            return float(data.decode()[1:])

        async def _meter(usage: dict) -> None:
            self.calls["bills"].append(usage["tts_chars"])

        async def _get_output_path(project_id, user_id, filename):
            return f"out/{filename}"

        async def _save(key, data, content_type=None):
            self.saved[key] = data
            return key

        async def _finalize(project_id, *, text, voice_id, language, owner_token,
                            staging_key, duration_s, config=None):
            self.calls["finalize"].append(
                {"owner_token": owner_token, "staging_key": staging_key,
                 "duration_s": duration_s}
            )
            return finalize_result or (staging_key, duration_s)

        async def _fail(project_id, *, text, voice_id, language, owner_token, config=None):
            self.calls["fail"].append(owner_token)

        monkeypatch.setattr(narration, "resolve_narration", _resolve)
        monkeypatch.setattr(narration, "finalize_narration", _finalize)
        monkeypatch.setattr(narration, "fail_narration", _fail)
        monkeypatch.setattr(narration, "synthesize", _synthesize)
        monkeypatch.setattr(narration, "_decode_duration_s", _decode)
        monkeypatch.setattr(narration, "record_media_usage", _meter)
        monkeypatch.setattr(narration, "get_output_path", _get_output_path)
        monkeypatch.setattr(narration, "save", _save)


def _run(sb: FilmStoryboard, frames: list[int], floors: list[int]):
    return asyncio.run(
        narration.synthesize_film_narration(
            output_id=uuid4(),
            project=_project(),
            storyboard=sb,
            frames=frames,
            floors=floors,
            voice_id=_VOICE,
            language=_LANG,
        )
    )


# --- 1. 命中且适配 ---------------------------------------------------------


def test_hit_fit_reuses_with_zero_synthesis_and_zero_billing(monkeypatch):
    _World(
        monkeypatch,
        reuse=NarrationReuse("store/original.mp3", 3.0, None),
        durations={},
    )
    audio_map, frames, moves = _run(FilmStoryboard(scenes=[_words(4.0, "Hello world")]), [120], [60])
    assert audio_map == {0: ("store/original.mp3", 3.0)}
    assert frames == [120] and moves == []


def test_hit_fit_never_touches_provider_or_meter(monkeypatch):
    world = _World(
        monkeypatch,
        reuse=NarrationReuse("store/original.mp3", 4.4, None),  # window 4.0 + 0.4 allowance — exactly at the edge
        durations={},
    )
    _run(FilmStoryboard(scenes=[_words(4.0, "Hello world")]), [120], [60])
    assert world.calls["synthesize"] == []
    assert world.calls["bills"] == []
    assert world.calls["finalize"] == [] and world.calls["fail"] == []
    assert world.saved == {}


# --- 2. 命中不适配 → 运行期适配 --------------------------------------------


def test_hit_unfit_adapts_from_known_duration_into_run_staging(monkeypatch):
    world = _World(
        monkeypatch,
        reuse=NarrationReuse("store/original.mp3", 5.0, None),  # 5.0 > 4.0 + 0.4
        durations={1.25: 4.1},  # adaptation_speed(5.0, 4.0, 1.35) = 1.25
    )
    out_id_scene = FilmStoryboard(scenes=[_words(4.0, "Hello world")])
    audio_map, frames, moves = _run(out_id_scene, [120], [60])
    # ONE adaptation pass at the computed speed, billed once…
    assert [c[3] for c in world.calls["synthesize"]] == [1.25]
    assert world.calls["bills"] == [float(len("Hello world"))]
    # …landing at the per-output staging key, never the store's…
    (key, seconds), = audio_map.values()
    assert key.endswith("_narr_0.mp3") and seconds == 4.1
    # …and the store is never written on a hit.
    assert world.calls["finalize"] == [] and world.calls["fail"] == []
    assert frames == [120] and moves == []


# --- 3. 未命中 → 先发布原件 -------------------------------------------------


def test_miss_fit_publishes_original_and_rides_the_store_key(monkeypatch):
    world = _World(
        monkeypatch,
        reuse=NarrationReuse(None, None, "tok1"),
        durations={1.0: 3.0},
    )
    audio_map, _, _ = _run(FilmStoryboard(scenes=[_words(4.0, "Hello world")]), [120], [60])
    # Pass 1 at 1.0 published the original under the owner token…
    assert [c[3] for c in world.calls["synthesize"]] == [1.0]
    (pub,) = world.calls["finalize"]
    assert pub["owner_token"] == "tok1" and pub["duration_s"] == 3.0
    assert "narr_" in pub["staging_key"]
    # …and the fit rides the COMMITTED store key — no per-output copy.
    assert audio_map == {0: (pub["staging_key"], 3.0)}
    assert list(world.saved) == [pub["staging_key"]]
    assert world.calls["fail"] == []


def test_miss_unfit_publishes_original_then_adapts_into_run_staging(monkeypatch):
    world = _World(
        monkeypatch,
        reuse=NarrationReuse(None, None, "tok2"),
        durations={1.0: 5.0, 1.25: 4.1},
    )
    audio_map, frames, moves = _run(
        FilmStoryboard(scenes=[_words(4.0, "Hello world")]), [120], [60]
    )
    # Original published (5.0s), THEN the adaptation pass billed separately.
    assert [c[3] for c in world.calls["synthesize"]] == [1.0, 1.25]
    assert len(world.calls["finalize"]) == 1
    assert world.calls["bills"] == [float(len("Hello world"))] * 2
    (key, seconds), = audio_map.values()
    assert key.endswith("_narr_0.mp3") and seconds == 4.1
    # The original's store object AND the run's adaptation both exist.
    assert any("narr_" in k for k in world.saved) and any(k.endswith("_narr_0.mp3") for k in world.saved)
    assert world.calls["fail"] == []
    assert frames == [120] and moves == []


# --- 4. straddle 成对律 -----------------------------------------------------


def test_straddled_finalize_pairs_the_winners_key_and_duration(monkeypatch):
    world = _World(
        monkeypatch,
        reuse=NarrationReuse(None, None, "tok-stale"),
        durations={1.0: 5.0},  # OUR decode does not fit…
        finalize_result=("store/winner.mp3", 3.0),  # …but the WINNER's does
    )
    audio_map, _, _ = _run(FilmStoryboard(scenes=[_words(4.0, "Hello world")]), [120], [60])
    # The pair travels together — never our 5.0s decode over the winner's audio.
    assert audio_map == {0: ("store/winner.mp3", 3.0)}
    assert world.calls["fail"] == []  # the row belongs to the takeover owner


# --- 5. 失败语义 ------------------------------------------------------------


def test_flex_rescue_keeps_published_original_and_discloses(monkeypatch):
    # Terminal overrun at the cap, covered by the silent scene's frames.
    world = _World(
        monkeypatch,
        reuse=NarrationReuse(None, None, "tok3"),
        durations={1.0: 5.0, 1.25: 4.9, 1.35: 4.6},  # 4.6 > 4.4 even at the cap
    )
    sb = FilmStoryboard(scenes=[_words(4.0, "Hello world"), _words(6.0)])  # silent donor
    audio_map, frames, moves = _run(sb, [120, 180], [60, 90])
    # Zero-sum flex: the narrated scene gained, the donor gave, Σ invariant.
    assert sum(frames) == 300 and frames[0] > 120 > 0 and frames[1] < 180
    assert len(moves) == 1
    (key, seconds), = audio_map.values()
    assert key.endswith("_narr_0.mp3") and seconds == 4.6
    # The published original survives the rescued run — and no fail fired.
    assert len(world.calls["finalize"]) == 1
    assert world.calls["fail"] == []


def test_uncoverable_overrun_fails_honestly_and_keeps_the_original(monkeypatch):
    world = _World(
        monkeypatch,
        reuse=NarrationReuse(None, None, "tok4"),
        durations={1.0: 5.0, 1.25: 4.9, 1.35: 4.6},
    )
    with pytest.raises(VoiceError) as exc_info:
        _run(FilmStoryboard(scenes=[_words(4.0, "Hello world")]), [120], [60])  # no silent donor
    assert exc_info.value.user_key == "film_narration_fit"
    # The done row (published original) survives the failed run (store law 5).
    assert len(world.calls["finalize"]) == 1
    assert world.calls["fail"] == []


def test_provider_failure_on_miss_deletes_own_placeholder(monkeypatch):
    world = _World(
        monkeypatch,
        reuse=NarrationReuse(None, None, "tok5"),
        durations={},
        synthesize_error=VoiceError("provider boom"),
    )
    with pytest.raises(VoiceError):
        _run(FilmStoryboard(scenes=[_words(4.0, "Hello world")]), [120], [60])
    assert world.calls["fail"] == ["tok5"]
    assert world.calls["finalize"] == []


def test_store_wait_timeout_reads_as_voice_unavailable(monkeypatch):
    _World(
        monkeypatch,
        reuse=TimeoutError("budget exhausted"),
        durations={},
    )
    with pytest.raises(VoiceError) as exc_info:
        _run(FilmStoryboard(scenes=[_words(4.0, "Hello world")]), [120], [60])
    assert exc_info.value.user_key == "voice_unavailable"


# --- 6. 窗口弹性纯核（ADR-136）------------------------------------------------
# The bounded zero-sum rescue's pure core — no DB, no provider IO.

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
