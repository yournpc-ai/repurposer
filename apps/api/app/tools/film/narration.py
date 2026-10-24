"""Film narration synthesis — the intro film's voiceover seat (ADR-130).

One T2A call per narrated scene, fitted to the scene's allocated window
over a bounded ladder (pass 1 at speed 1.0; an overrun re-synthesizes
faster, scaled by the measured shortfall, ≤1.35× — the dub chain's fit
law, one narration per scene, at most ``_FIT_PASSES`` passes). A line
that STILL does not fit gets ONE bounded rescue before failing: the
window flex (ADR-136) — the scene steals frames from the film's SILENT
scenes (zero-sum: the total runtime never moves; bounded on both sides:
a donor never loses more than ``_FLEX_DONOR_MAX_FRAC`` and never dips
under its structural floor, a receiver never gains more than
``_FLEX_STRETCH_MAX_FRAC``). The flex activates ONLY on the
otherwise-fatal path — a line the ladder fits never touches it, so green
renders stay byte-identical — and every steal is disclosed on the
output's payload for the closing review's facts (展示=执行's bounded
tolerance, disclosed, never silent). A line the flex cannot cover fails
the step honestly (VoiceError with the ``film_narration_fit`` key — a
design problem, never an outage line), naming the real attempts AND the
tried flex. The approved storyboard is never silently rewritten, and its
audio is never quietly trimmed past meaning; beyond the bounded flex the
fix is a shorter line through the design beat, not a render-time fudge.
One scene's failure cancels its siblings — a dead step bills no further
synthesis passes. Each scene's audio is its own storage object; the
renderer plays it inside the scene's Sequence, so scene boundaries trim
honestly. The synthesis also returns the decoded seconds so the film-spec's
subtitle cues time against the real spoken span (never a second duration
guess).

Reuse (ADR-138 §10.1 — the five concurrency laws' full text lives in
``narration_store.py``): every line first resolves against the project's
narration store — identity = normalized text | RESOLVED voice | language |
synthesis config, never a display name, never an unresolved Auto. The store
holds ONLY the speed-1.0 ORIGINAL; adaptation is a runtime RE-SYNTHESIS.
A hash hit answers the "pass 1" duration with ZERO synthesis: fits → the
original's object key rides straight into the spec (reuse bills nothing);
does not fit → re-synthesize faster from the KNOWN 1.0 duration — a real,
metered vendor call — into the run's own staging file
(``<output_id>_narr_<i>.mp3`` — never stored; a lost staging file is
recovered only by re-synthesizing, never by transforming the original's
bytes — no zero-TTS or deterministic-recovery claim). A miss makes this run
the owner: its pass 1 IS the original, published to the store BEFORE the
fit verdict (another window reuses it even when this scene adapts; a failed
later pass never poisons the published original).

Voice resolution (all by code, never the LLM): the persona's voice block
(cloned voice_id / stock id) → the default narrator. The persona block is
the ONLY voice source — a film has no source footage to clone from.

Zero LLM here (N-29 mechanics): text in (the validated storyboard's
narration lines), audio keys out.
"""

import asyncio
import io
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog
from starlette.concurrency import run_in_threadpool

from app.metering import record_media_usage
from app.providers.storage import get_output_path, save
from app.providers.voice import VoiceError, synthesize
from app.tools.film.narration_store import (
    adaptation_speed,
    fail_narration,
    finalize_narration,
    narration_content_hash,
    narration_synth_config,
    resolve_narration,
)

if TYPE_CHECKING:
    from uuid import UUID

    from app.models.schemas import FilmStoryboard
    from app.models.tables import Project

logger = structlog.get_logger()

_RATE = 32000  # MiniMax T2A output sample rate (the dub chain's mirror)
_SPEED_MAX = 1.35  # fastest re-synthesis (beyond = unnatural speech)
_FIT_PASSES = 3  # total synthesis passes per scene, bounded — never a retry loop
_TTS_CONCURRENCY = 4
# The default narrator when the persona carries no voice binding (a MiniMax
# system voice id — the STOCK_VOICES registry is a deferred batch; until
# then the film family speaks with one house voice).
DEFAULT_FILM_VOICE_ID = "presenter_male"
# A narration may eat this much past its scene's window before the speed
# pass fires (the renderer trims at the scene boundary — a small overhang
# reads as a natural sentence tail).
_WINDOW_ALLOW = 0.4
# Window flex bounds (ADR-136): the steal is zero-sum (Σ frames — the
# film's total runtime — never moves) and doubly bounded — a silent donor
# never loses more than this fraction of its frames across ALL steals and
# never dips under its structural floor; a narrated receiver never gains
# more than this fraction on top of its own frames. Beyond the bounds the
# step fails honestly — the flex is a rescue, never a rewrite.
_FLEX_DONOR_MAX_FRAC = 0.30
_FLEX_STRETCH_MAX_FRAC = 0.40


@dataclass
class _SceneOverrun:
    """A scene whose line outruns its window past the WHOLE ladder. The
    audio rides in memory (billed, decoded, never yet saved) until the
    flex verdict: covered → saved against the stretched window; uncovered
    → dropped unsaved and the step fails honestly (the pre-flex law)."""

    audio: bytes
    duration: float
    attempts: list[tuple[float, float]]


async def _save_narration(project: "Project", output_id: "UUID", index: int, audio: bytes) -> str:
    """One scene's audio → its own storage object (the renderer reads it
    inside the scene's Sequence)."""
    key = str(
        await get_output_path(
            project.id, project.user_id, f"{output_id}_narr_{index}.mp3"
        )
    )
    await save(key, audio, content_type="audio/mpeg")
    return key


async def _publish_original(
    project: "Project",
    *,
    text: str,
    voice_id: str,
    language: str,
    owner_token: str,
    audio: bytes,
    duration: float,
) -> tuple[str, float]:
    """The miss path's store publish: the pass-1 (speed 1.0) audio lands at
    a token-suffixed staging object under the project output prefix (the
    project cascade reaps it with the project, mirroring the row's own
    CASCADE), then the owner-conditional finalize adopts it (store laws
    3–4: a lost finalize deletes ONLY our own staging and reads the
    winner's committed result). Returns the AUTHORITATIVE
    ``(storage_key, duration_s)`` pair — on an ownership straddle the pair
    is the winner's, never our decode coupled to someone else's audio."""
    content_hash, _ = narration_content_hash(
        text=text,
        voice_id=voice_id,
        language=language,
        config=narration_synth_config(),
    )
    staging_key = str(
        await get_output_path(
            project.id,
            project.user_id,
            f"narr_{content_hash[:16]}-{owner_token[:12]}.mp3",
        )
    )
    await save(staging_key, audio, content_type="audio/mpeg")
    try:
        return await finalize_narration(
            project.id,
            text=text,
            voice_id=voice_id,
            language=language,
            owner_token=owner_token,
            staging_key=staging_key,
            duration_s=duration,
        )
    except TimeoutError as e:
        # The straddle tail: ownership lost AND no committed result stands
        # (the takeover is still synthesizing) — a transient store
        # condition, not a design problem; the next attempt re-resolves.
        raise VoiceError(f"narration reuse store publish lost: {e}") from e


def _flex_frames_for_overruns(
    *,
    frames: list[int],
    floors: list[int],
    silent: set[int],
    overruns: dict[int, float],
    fps: int,
) -> tuple[list[int], list[dict[str, Any]]] | None:
    """The window flex's pure core (ADR-136): overrun scenes steal frames
    from the film's SILENT scenes so the decoded line fits its stretched
    window (the already-synthesized audio is kept — the frames move, the
    audio never re-bills). Zero-sum by construction (Σ frames invariant),
    bounded on both sides, deterministic (donors give in descending spare
    capacity, ties by scene order; a donor's 30% loss cap spans ALL the
    steals it feeds). Returns ``(adjusted_frames, disclosure_moves)``, or
    None when the bounded steal cannot cover a shortfall — the caller
    then fails honestly, exactly the pre-flex law."""
    adjusted = list(frames)
    stolen: dict[int, int] = {}
    moves: list[dict[str, Any]] = []
    for i in sorted(overruns):
        need = math.ceil((overruns[i] - _WINDOW_ALLOW) * fps) - adjusted[i]
        if need <= 0:
            continue  # defensive: an overrun by definition needs ≥1 frame
        if need > int(frames[i] * _FLEX_STRETCH_MAX_FRAC):
            return None  # the stretch cap binds — a redesign, not a rescue
        donors = sorted(
            (
                (
                    j,
                    min(
                        adjusted[j] - floors[j],
                        int(frames[j] * _FLEX_DONOR_MAX_FRAC) - stolen.get(j, 0),
                    ),
                )
                for j in silent
                if j != i
            ),
            key=lambda pair: (-pair[1], pair[0]),
        )
        gained = 0
        gifts: list[tuple[int, int]] = []
        for j, capacity in donors:
            if gained >= need:
                break
            take = min(capacity, need - gained)
            if take <= 0:
                continue
            adjusted[j] -= take
            stolen[j] = stolen.get(j, 0) + take
            gained += take
            gifts.append((j, take))
        if gained < need:
            return None
        adjusted[i] += gained
        moves.append(
            {
                "scene": i,
                "gained_s": round(gained / fps, 2),
                "donors": [
                    {"scene": j, "gave_s": round(take / fps, 2)} for j, take in gifts
                ],
            }
        )
    assert sum(adjusted) == sum(frames)  # zero-sum by construction
    return adjusted, moves


def resolve_film_voice(persona_voice: dict | None) -> str:
    """The persona's voice block → a synthesizable voice_id. ``kind=cloned``
    carries the cached MiniMax clone id; ``kind=stock``'s stock_id IS a
    system voice id; anything else (None / auto) → the house narrator."""
    block = persona_voice if isinstance(persona_voice, dict) else {}
    if block.get("kind") == "cloned" and isinstance(block.get("voice_id"), str):
        return block["voice_id"]
    if block.get("kind") == "stock" and isinstance(block.get("stock_id"), str):
        return block["stock_id"]
    return DEFAULT_FILM_VOICE_ID


def _decode_duration_s(data: bytes) -> float:
    """MP3 bytes → seconds (decode-and-count; container durations lie)."""
    import av

    total = 0
    with av.open(io.BytesIO(data)) as inp:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=_RATE)
        for frame in inp.decode(audio=0):
            for r in resampler.resample(frame):
                total += r.samples
        for r in resampler.resample(None):
            total += r.samples
    if total == 0:
        raise ValueError("narration decoded to zero samples")
    return total / _RATE


async def synthesize_film_narration(
    *,
    output_id: "UUID",
    project: "Project",
    storyboard: "FilmStoryboard",
    frames: list[int],
    floors: list[int],
    voice_id: str,
    language: str,
) -> tuple[dict[int, tuple[str, float]], list[int], list[dict[str, Any]]]:
    """Synthesize every narrated scene → ``(audio_map, frames, flex_moves)``.

    ``audio_map``: {scene_index: (object key, seconds)} — scenes without
    narration simply absent (the renderer reads ``audio`` null as silent).
    The decoded duration rides along so the spec builder lays the subtitle
    cues over the REAL spoken span instead of re-guessing the timing.
    ``frames``: the scene allocation the spec MUST build from — identical
    to the caller's unless the window flex (ADR-136) rescued an overrun
    (zero-sum: Σ never moves). ``flex_moves``: the disclosure records
    (empty when no flex fired) — the caller bakes them onto the output
    payload for the closing review's facts. Provider failures propagate
    as VoiceError — voiceover was promised in the review, a silent film
    would be a quiet gap, so the step fails honestly.
    """
    from app.tools.film.storyboard import FILM_FPS  # one law, one seat

    async def _one(index: int, text: str, window_s: float, sem: asyncio.Semaphore) -> tuple[int, tuple[str, float] | None, _SceneOverrun | None]:
        """One scene's narration, fitted over a BOUNDED ladder of passes:
        pass 1 at speed 1.0; each overrun re-synthesizes faster, scaled by
        THIS pass's measured shortfall (the provider's speed response is not
        guaranteed linear — correct against what we actually decoded), never
        past ``_SPEED_MAX``. Every pass logs its requested speed, decoded
        seconds and the scene window. A terminal overrun is NOT raised here
        — it returns the overrun (audio in memory, billed, decoded, unsaved)
        for the flex verdict (ADR-136); the pre-flex law's honest failure
        fires only after the flex falls short, naming the real attempts.

        The reuse store sits in front of the ladder (ADR-138 §10.1): a hash
        HIT answers pass 1 for free (the stored original's real duration —
        fit = zero-synthesis reuse; unfit = the ladder resumes at pass 2
        from the known 1.0 fact, and the adapted product is this run's own
        staging file, never the store's). A MISS makes this run the owner —
        its pass 1 is published as the original BEFORE the fit verdict, so
        a wider window elsewhere reuses it even when this scene adapts."""
        # 复用座位: identity = normalized text | resolved voice | language |
        # synth config; the store's bounded wait / takeover laws ride along
        # (a budget exhaustion is a transient store condition, never a
        # design problem — it reads as voice_unavailable, not the fit key).
        try:
            reuse = await resolve_narration(
                project.id, text=text, voice_id=voice_id, language=language
            )
        except TimeoutError as e:
            raise VoiceError(f"narration reuse store wait exhausted: {e}") from e

        attempts: list[tuple[float, float]] = []
        speed = 1.0
        audio = b""
        duration = 0.0
        start_pass = 1
        owner_token = reuse.owner_token
        if reuse.reusable:
            stored = reuse.duration_s
            if stored is None or stored <= 0:
                # done ⇒ (key, duration) is ONE atomic write — a violation
                # is a bug: fail loud, never guess a timing.
                raise VoiceError(
                    "narration store row corrupt: done without duration "
                    f"(key={reuse.storage_key})"
                )
            duration = stored
            attempts.append((1.0, duration))
            if duration <= window_s + _WINDOW_ALLOW:
                # 命中且适配: zero synthesis, zero billing — the original's
                # object key rides straight into the spec.
                logger.info(
                    "film_narration_reuse",
                    output_id=str(output_id),
                    scene=index,
                    seconds=round(duration, 2),
                    window_s=round(window_s, 2),
                )
                return index, (reuse.storage_key, duration), None
            # 命中不适配: adapt — the ladder resumes from the KNOWN 1.0
            # duration with a REAL, metered re-synthesis at the computed
            # speed; the adapted product lands at the per-output staging
            # key (never stored; recovered only by re-synthesizing, never
            # by transforming the original's bytes).
            speed = (
                adaptation_speed(
                    duration_s=duration, window_s=window_s, speed_max=_SPEED_MAX
                )
                or _SPEED_MAX
            )
            start_pass = 2
            logger.info(
                "film_narration_adapt",
                output_id=str(output_id),
                scene=index,
                seconds=round(duration, 2),
                window_s=round(window_s, 2),
                requested_speed=round(speed, 3),
            )

        try:
            for pass_no in range(start_pass, _FIT_PASSES + 1):
                async with sem:
                    audio = await run_in_threadpool(synthesize, text, voice_id, language, speed)
                # Every synthesis call bills its characters (the dub chain's
                # metering law — a re-fit is a second call). A FITTING store
                # hit never reaches this loop (zero synthesis, zero billing);
                # an unfit hit's adaptation passes bill like any synthesis.
                await record_media_usage({"tts_chars": float(len(text))})
                duration = await run_in_threadpool(_decode_duration_s, audio)
                attempts.append((speed, duration))
                logger.info(
                    "film_narration_pass",
                    output_id=str(output_id),
                    scene=index,
                    pass_no=pass_no,
                    requested_speed=round(speed, 3),
                    seconds=round(duration, 2),
                    window_s=round(window_s, 2),
                )
                if owner_token is not None:
                    # The miss path's first synthesis IS the speed-1.0
                    # original — publish it BEFORE the fit verdict. The
                    # token stays armed until the publish RETURNS: a
                    # pre-finalize failure (staging save hiccup) still owns
                    # the placeholder and the BaseException cleanup reaps
                    # it; a straddle raise finds the row already owned by
                    # the takeover, where the double-conditioned fail is a
                    # safe no-op.
                    committed_key, committed_duration = await _publish_original(
                        project,
                        text=text,
                        voice_id=voice_id,
                        language=language,
                        owner_token=owner_token,
                        audio=audio,
                        duration=duration,
                    )
                    owner_token = None
                    # On an ownership straddle the committed pair is the
                    # winner's — key AND duration travel together.
                    duration = committed_duration
                    if duration <= window_s + _WINDOW_ALLOW:
                        logger.info(
                            "film_narration_scene",
                            output_id=str(output_id),
                            scene=index,
                            chars=len(text),
                            seconds=round(duration, 2),
                            window_s=round(window_s, 2),
                            store="original",
                        )
                        return index, (committed_key, duration), None
                    # The original stands in the store; THIS scene still
                    # needs its adaptation — keep climbing from the 1.0 fact.
                    speed = min(speed * duration / max(window_s, 0.2), _SPEED_MAX)
                    continue
                if duration <= window_s + _WINDOW_ALLOW:
                    break
                if pass_no == _FIT_PASSES or speed >= _SPEED_MAX:
                    return index, None, _SceneOverrun(
                        audio=audio, duration=duration, attempts=attempts
                    )
                speed = min(speed * duration / max(window_s, 0.2), _SPEED_MAX)
        except BaseException:
            if owner_token is not None:
                # 失败不留毒 (store law 5): the double-conditioned delete
                # reaps ONLY our own still-synthesizing placeholder.
                try:
                    await fail_narration(
                        project.id,
                        text=text,
                        voice_id=voice_id,
                        language=language,
                        owner_token=owner_token,
                    )
                except Exception as cleanup_err:  # noqa: BLE001 — cleanup never masks the real failure
                    logger.warning(
                        "film_narration_fail_cleanup_failed", error=str(cleanup_err)
                    )
            raise
        key = await _save_narration(project, output_id, index, audio)
        logger.info(
            "film_narration_scene",
            output_id=str(output_id),
            scene=index,
            chars=len(text),
            seconds=round(duration, 2),
            window_s=round(window_s, 2),
        )
        return index, (key, duration), None

    sem = asyncio.Semaphore(_TTS_CONCURRENCY)
    tasks: list[asyncio.Task] = []
    for i, scene in enumerate(storyboard.scenes):
        narration = getattr(scene, "narration", None)
        if not narration or not narration.strip():
            continue
        tasks.append(
            asyncio.create_task(_one(i, narration.strip(), frames[i] / FILM_FPS, sem))
        )
    if not tasks:
        return {}, list(frames), []
    try:
        results = await asyncio.gather(*tasks)
    except BaseException:
        # 收束律: one scene's failure cancels the siblings — a cancelled
        # awaiting task stops at its next await instead of billing further
        # synthesis passes for a step that is already dead. (A cancelled
        # threadpool call may still complete provider-side unrecorded —
        # prompt wind-down outranks that metering edge here.)
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise

    fitted: dict[int, tuple[str, float]] = {}
    overruns: dict[int, _SceneOverrun] = {}
    for index, fit, overrun in results:
        if fit is not None:
            fitted[index] = fit
        if overrun is not None:
            overruns[index] = overrun

    adjusted = list(frames)
    flex_moves: list[dict[str, Any]] = []
    if overruns:
        # 窗口弹性 (ADR-136): the ladder exhausted — one bounded rescue
        # before the honest failure. The steal is zero-sum (total runtime
        # never moves — the pre-metered film seconds stay exact), silent
        # scenes only, floors and both caps bind, every move disclosed.
        silent = {
            i
            for i, scene in enumerate(storyboard.scenes)
            if not (getattr(scene, "narration", None) or "").strip()
        }
        verdict = _flex_frames_for_overruns(
            frames=frames,
            floors=floors,
            silent=silent,
            overruns={i: ov.duration for i, ov in overruns.items()},
            fps=FILM_FPS,
        )
        if verdict is None:
            # 适配法 (Batch 2 + ADR-136): the line no longer reads inside
            # its scene even at the fastest natural speed, and the bounded
            # flex cannot cover the difference. The approved storyboard is
            # NEVER silently rewritten or its audio quietly trimmed past
            # meaning — the step fails honestly, naming the REAL attempts
            # AND the tried flex, and asks for a shorter line through the
            # design beat. A design problem, not an outage — its own
            # user_key, never "voice unavailable".
            detail = "; ".join(
                f"scene {i}: "
                + ", ".join(f"{s:.2f}x→{d:.1f}s" for s, d in ov.attempts)
                for i, ov in sorted(overruns.items())
            )
            raise VoiceError(
                f"narration overruns its scene window after the bounded "
                f"speed ladder AND the silent scenes could not spare the "
                f"difference ({detail}; fastest natural speed is "
                f"{_SPEED_MAX}x, flex bounded at "
                f"+{_FLEX_STRETCH_MAX_FRAC:.0%} stretch / "
                f"-{_FLEX_DONOR_MAX_FRAC:.0%} per silent scene) — redesign "
                f"the storyboard with a shorter narration line for this "
                f"scene.",
                user_key="film_narration_fit",
            )
        adjusted, flex_moves = verdict
        # The flex covered every overrun — the kept audio (never re-billed)
        # saves now, against the stretched windows.
        for i, ov in sorted(overruns.items()):
            key = await _save_narration(project, output_id, i, ov.audio)
            logger.info(
                "film_narration_scene",
                output_id=str(output_id),
                scene=i,
                seconds=round(ov.duration, 2),
                window_s=round(adjusted[i] / FILM_FPS, 2),
                flex=True,
            )
            fitted[i] = (key, ov.duration)
    return fitted, adjusted, flex_moves
