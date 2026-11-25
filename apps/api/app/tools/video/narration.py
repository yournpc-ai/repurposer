"""Original narration synthesis, measured timing and character quotes."""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
from typing import Any
from uuid import UUID

from app.editing.schemas import (
    Clip,
    CompositionContent,
    SpeechObject,
)
from app.tools.video.params import NARRATION_FIT_MARGIN, NarrationPolicy

DEFAULT_VIDEO_VOICE_ID = "presenter_male"
NARRATION_ALIGNMENT = "minimax-t2a-v2-sentence-v1"


def resolve_video_voice(persona_voice: dict | None) -> str:
    """Persona voice binding → a concrete voice id; Auto uses the house voice."""
    block = persona_voice if isinstance(persona_voice, dict) else {}
    if block.get("kind") == "cloned" and isinstance(block.get("voice_id"), str):
        return block["voice_id"]
    if block.get("kind") == "stock" and isinstance(block.get("stock_id"), str):
        return block["stock_id"]
    return DEFAULT_VIDEO_VOICE_ID


def narration_synth_config() -> dict[str, Any]:
    """Complete original-synthesis identity; changes invalidate old originals."""
    from app.providers import voice

    return {
        "provider": "minimax",
        "model": voice.tts_model(),
        "sample_rate": 32000,
        "bitrate": 128000,
        "format": "mp3",
        "channels": 1,
        "volume": 1,
        "pitch": 0,
        "speed_base": 1.0,
        "subtitle_type": "sentence",
        "alignment": NARRATION_ALIGNMENT,
    }


def narration_content_hash(
    *, text: str, voice_id: str, language: str, config: dict
) -> tuple[str, str]:
    normalized = " ".join(text.split())
    config_hash = hashlib.sha256(
        json.dumps(config, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    payload = json.dumps(
        {
            "text": normalized,
            "voice_id": voice_id,
            "language": language,
            "config": config_hash,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest(), config_hash


def narration_original_request_key(*, text: str, voice_id: str, language: str) -> str:
    """The shared quote/execution identity for one original-only request."""
    content_hash, _ = narration_content_hash(
        text=text,
        voice_id=voice_id,
        language=language,
        config=narration_synth_config(),
    )
    return content_hash


async def narration_original_quote_characters(
    *, text: str, voice_id: str, language: str, user_id: UUID
) -> int:
    """One missing speed-1.0 synthesis; a fixed original needs no new charge."""
    from app.tools.video.narration_store import peek_original

    speech = SpeechObject(
        kind="speech",
        object_id="obj_prepare_narration",
        text=text,
        voice_id=voice_id,
        language=language,
    )
    if await peek_original(user_id, speech) is not None:
        return 0
    return narration_billable_upper_bound(" ".join(text.split()))


def narration_alignment_digest(text: str, cues: list[dict]) -> str:
    payload = {"alignment": NARRATION_ALIGNMENT, "text": text, "cues": cues}
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def decode_duration_s(data: bytes) -> float:
    """MP3 bytes → seconds by decoding and counting samples, not container metadata."""
    import av

    with av.open(io.BytesIO(data)) as container:
        stream = next(s for s in container.streams if s.type == "audio")
        rate = stream.codec_context.sample_rate
        samples = sum(frame.samples for frame in container.decode(stream))
    if not rate or samples <= 0:
        raise ValueError("decoded narration has no audio samples")
    return samples / float(rate)


class NarrationError(ValueError):
    """A safe, bounded narration preparation failure."""


class NarrationBudgetError(NarrationError):
    user_key = "narration_budget_exceeded"


def _speech_clips(content: CompositionContent) -> list[Clip]:
    return sorted(
        (
            clip
            for track in content.timeline.tracks
            for clip in track.clips
            if isinstance(clip.object, SpeechObject) and clip.object.alignment is None
        ),
        key=lambda clip: (clip.range.start, clip.clip_id),
    )


async def _cues(subtitle_file: str | None, normalized_text: str, duration_s: float) -> list[dict]:
    from app.providers.voice import fetch_subtitle_cues

    if not subtitle_file:
        raise NarrationError("T2A returned fixed audio without its subtitle file")
    cues = await asyncio.to_thread(fetch_subtitle_cues, subtitle_file, source_text=normalized_text)
    if cues[-1]["time_end"] > duration_s * 1000 + 150:
        raise NarrationError("T2A sentence timings exceed the decoded narration duration")
    return cues


def narration_billable_upper_bound(text: str) -> int:
    """Conservative MiniMax units: CJK/non-ASCII may count twice per codepoint."""
    return sum(2 if ord(character) > 127 else 1 for character in text)


def _check_budget(policy: NarrationPolicy, spent: int, normalized_text: str) -> None:
    required = narration_billable_upper_bound(normalized_text)
    if spent + required > policy.max_tts_characters:
        raise NarrationBudgetError(
            f"the next narration synthesis needs at most {required} billable characters, but only "
            f"{max(0, policy.max_tts_characters - spent)} remain in this Run's pinned TTS budget"
        )


async def narration_quote_characters(content: CompositionContent, *, user_id: UUID) -> int:
    """Maximum additional TTS characters this version may still require."""
    from app.tools.video.narration_store import peek_original

    total = 0
    for clip in _speech_clips(content):
        speech = clip.object
        assert isinstance(speech, SpeechObject)
        normalized = " ".join(speech.text.split())
        upper_bound = narration_billable_upper_bound(normalized)
        original = await peek_original(user_id, speech)
        if original is None:
            total += upper_bound * 2
            continue
        window = clip.range.duration / content.settings.timebase
        if original["duration_s"] <= window:
            continue
        required = original["duration_s"] / max(window, 1 / 30) * NARRATION_FIT_MARGIN
        if required <= 1.35:
            # A new request needs the same conservative bound as _check_budget;
            # the original's actual charge cannot authorize its next synthesis.
            total += upper_bound
    return total


async def prepare_original_narration(
    speech: SpeechObject,
    *,
    user_id: UUID,
    execution_id: str,
    policy: NarrationPolicy,
    spent: int = 0,
    before_submit=None,
) -> tuple[dict[str, Any], bool]:
    """Resolve the speed-1.0 recording and its sentence timings under one authorization."""
    from app.metering import record_media_usage
    from app.providers.voice import synthesize_detailed
    from app.tools.video.narration_store import (
        NarrationOutcomeUnknown,
        cancel_unsubmitted,
        complete_alignment,
        complete_audio,
        mark_outcome_unknown,
        resolve_original,
    )

    generated = False
    resolution = await resolve_original(user_id, speech, execution_id=execution_id, reserve_only=before_submit is not None)
    if resolution["state"] == "done":
        original = {**resolution["original"], "cache_hit": True, "run_usage": 0}
    else:
        normalized = resolution["normalized_text"]
        run_usage = 0
        if resolution["state"] == "needs_audio":
            try:
                _check_budget(policy, spent, normalized)
            except Exception:
                await cancel_unsubmitted(user_id, speech, execution_id=execution_id)
                raise
            if before_submit is not None:
                await before_submit()
            try:
                from app.editing.catalog import VERIFIED_VOICE_IDS
                from app.models.database import AsyncSessionLocal
                from app.pipeline.voices import synthesize_with_voice_resilience

                if speech.voice_id in VERIFIED_VOICE_IDS:
                    result = await asyncio.to_thread(
                        synthesize_detailed, normalized, speech.voice_id, speech.language, 1.0
                    )
                else:
                    async with AsyncSessionLocal() as voice_db:
                        result, _ = await synthesize_with_voice_resilience(
                            voice_db,
                            text=normalized,
                            voice_ref=speech.voice_id,
                            language=speech.language,
                            speed=1.0,
                            owner_id=user_id,
                        )
                generated = True
            except Exception as exc:
                await mark_outcome_unknown(
                    user_id, speech, execution_id=execution_id, error=str(exc)
                )
                raise NarrationOutcomeUnknown(
                    f"Original narration outcome is unconfirmed: {exc}"
                ) from exc
            duration = decode_duration_s(result.audio)
            audio = await complete_audio(
                user_id,
                speech,
                execution_id=execution_id,
                audio=result.audio,
                duration_s=duration,
                subtitle_file=result.subtitle_file,
                usage_characters=result.usage_characters,
                trace_id=result.trace_id,
            )
            run_usage = result.usage_characters
            await record_media_usage({"tts_chars": float(run_usage)})
            resolution = {"state": "needs_alignment", "audio": audio, "normalized_text": normalized}
        else:
            # Confirmed audio from an earlier attempt resumes without re-metering.
            if resolution["audio"].get("synthesis_execution_id") == execution_id:
                run_usage = int(resolution["audio"].get("usage_characters") or 0)
        audio = resolution["audio"]
        cues = await _cues(audio.get("subtitle_file"), normalized, float(audio["duration_s"]))
        original = await complete_alignment(
            user_id, speech, execution_id=execution_id, cues=cues
        )
        original = {**original, "cache_hit": not generated and not run_usage, "run_usage": run_usage}
    return original, generated
