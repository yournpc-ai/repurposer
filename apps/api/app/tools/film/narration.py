"""Film narration synthesis — the intro film's voiceover seat (ADR-120 E2).

One T2A call per narrated scene, fitted to the scene's allocated window
(pass 1 at speed 1.0; an overrun re-synthesizes at the provider's
voice-level speed, ≤1.35× — the dub chain's fit law, one narration per
scene so no cue alignment is needed). Each scene's audio is its own
storage object (``<output_id>_narr_<i>.mp3``); the renderer plays it inside
the scene's Sequence, so scene boundaries trim honestly.

Voice resolution (all by code, never the LLM): the persona's voice block
(cloned voice_id / stock id) → the default narrator. The persona block is
the ONLY voice source — a film has no source footage to clone from.

Zero LLM here (N-29 mechanics): text in (the validated storyboard's
narration lines), audio keys out.
"""

import asyncio
import io
from typing import TYPE_CHECKING

import structlog
from starlette.concurrency import run_in_threadpool

from app.metering import record_media_usage
from app.providers.storage import get_output_path, save
from app.providers.voice import synthesize

if TYPE_CHECKING:
    from uuid import UUID

    from app.models.schemas import FilmStoryboard
    from app.models.tables import Project

logger = structlog.get_logger()

_RATE = 32000  # MiniMax T2A output sample rate (the dub chain's mirror)
_SPEED_MAX = 1.35  # fastest re-synthesis (beyond = unnatural speech)
_TTS_CONCURRENCY = 4
# The default narrator when the persona carries no voice binding (a MiniMax
# system voice id — the STOCK_VOICES registry is a deferred batch; until
# then the film family speaks with one house voice).
DEFAULT_FILM_VOICE_ID = "presenter_male"
# A narration may eat this much past its scene's window before the speed
# pass fires (the renderer trims at the scene boundary — a small overhang
# reads as a natural sentence tail).
_WINDOW_ALLOW = 0.4


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
    voice_id: str,
    language: str,
) -> dict[int, str]:
    """Synthesize every narrated scene → {scene_index: object key}.

    Scenes without narration simply absent from the map (the renderer
    reads ``audio`` null as silent). Provider failures propagate as
    VoiceError — voiceover was promised in the review, a silent film
    would be a quiet gap, so the step fails honestly.
    """
    from app.tools.film.storyboard import FILM_FPS  # one law, one seat

    async def _one(index: int, text: str, window_s: float, sem: asyncio.Semaphore) -> tuple[int, str]:
        async with sem:
            audio = await run_in_threadpool(synthesize, text, voice_id, language)
        await record_media_usage({"tts_chars": float(len(text))})
        duration = await run_in_threadpool(_decode_duration_s, audio)
        if duration > window_s + _WINDOW_ALLOW:
            speed = min(duration / max(window_s, 0.2), _SPEED_MAX)
            async with sem:
                audio = await run_in_threadpool(synthesize, text, voice_id, language, speed)
            # Every synthesis call bills its characters (the dub chain's
            # metering law — a re-fit is a second call).
            await record_media_usage({"tts_chars": float(len(text))})
            duration = await run_in_threadpool(_decode_duration_s, audio)
        key = str(
            await get_output_path(
                project.id, project.user_id, f"{output_id}_narr_{index}.mp3"
            )
        )
        await save(key, audio, content_type="audio/mpeg")
        logger.info(
            "film_narration_scene",
            output_id=str(output_id),
            scene=index,
            chars=len(text),
            seconds=round(duration, 2),
            window_s=round(window_s, 2),
        )
        return index, key

    sem = asyncio.Semaphore(_TTS_CONCURRENCY)
    jobs = []
    for i, scene in enumerate(storyboard.scenes):
        narration = getattr(scene, "narration", None)
        if not narration or not narration.strip():
            continue
        jobs.append(_one(i, narration.strip(), frames[i] / FILM_FPS, sem))
    results = await asyncio.gather(*jobs) if jobs else []
    return dict(results)
