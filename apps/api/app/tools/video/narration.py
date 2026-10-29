"""Fixed-window narration preparation for CompositionVersion production.

The immutable version owns reviewed text and voice. This module owns actual
TTS calls, measured-duration fit decisions and execution-local media facts.
Only speed-1.0 originals are shared through ``narration_store``; a faster
adaptation is a separate, explicitly bounded provider call fixed to one Run.
"""
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
    speech_text_digest,
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


def narration_alignment_digest(text: str, cues: list[dict]) -> str:
    payload = {"alignment": NARRATION_ALIGNMENT, "text": text, "cues": cues}
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def adaptation_speed(
    *, duration_s: float, window_s: float, speed_max: float, fit_margin: float = NARRATION_FIT_MARGIN
) -> float | None:
    """Return None when the original fits; otherwise its bounded second-pass speed."""
    if duration_s <= window_s:
        return None
    # Leave room for measured provider duration variation, without trimming audio.
    needed = duration_s / max(window_s, 1 / 30) * fit_margin
    return min(needed, speed_max)


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


class NarrationFitError(NarrationError):
    user_key = "narration_window_conflict"


class NarrationBudgetError(NarrationError):
    user_key = "narration_budget_exceeded"


def _speech_clips(content: CompositionContent) -> list[Clip]:
    return sorted(
        (
            clip
            for track in content.timeline.tracks
            for clip in track.clips
            if isinstance(clip.object, SpeechObject)
        ),
        key=lambda clip: (clip.range.start, clip.clip_id),
    )


def _request(clip: Clip, policy: NarrationPolicy) -> dict[str, Any]:
    speech = clip.object
    assert isinstance(speech, SpeechObject)
    return {
        "speech_object_id": speech.object_id,
        "text_digest": speech_text_digest(speech.text),
        "provider": speech.provider,
        "model": speech.model,
        "voice_id": speech.voice_id,
        "language": speech.language,
        "gain_db": speech.gain_db,
        "window_ticks": clip.range.duration,
        "min_speed": policy.min_speed,
        "max_speed": policy.max_speed,
        "max_attempts": policy.max_attempts,
        "fit_margin": policy.fit_margin,
    }


def _manifest_key(execution_id: str, clip_id: str) -> str:
    return f"video-narrations/executions/{UUID(execution_id)}/{clip_id}.json"


async def _save_manifest(key: str, value: dict[str, Any]) -> None:
    from app.providers import storage

    await storage.save(
        key,
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        content_type="application/json",
    )


async def _read_manifest(
    key: str, *, clip: Clip, execution_id: str, policy: NarrationPolicy
) -> dict[str, Any] | None:
    from app.providers import storage
    from app.tools.video.narration_store import NarrationOutcomeUnknown

    if not await storage.exists(key):
        return None
    value = json.loads(await storage.read(key))
    if not isinstance(value, dict) or value.get("execution_id") != execution_id:
        raise NarrationError("narration execution manifest identity mismatch")
    if value.get("request") != _request(clip, policy):
        raise NarrationError("narration execution manifest does not match the reviewed SpeechClip")
    state = value.get("state")
    if state == "submitted":
        raise NarrationOutcomeUnknown(
            f"clip {clip.clip_id}: an adapted narration request has no confirmed result; "
            "automatic recovery will not submit it again"
        )
    if state == "conflict":
        raise NarrationFitError(str(value.get("error") or "narration does not fit its fixed window"))
    if state == "done":
        media = value.get("media") or {}
        data = await storage.read(media["storage_key"])
        if hashlib.sha256(data).hexdigest() != media.get("digest"):
            raise NarrationError("prepared narration bytes do not match their manifest digest")
        if narration_alignment_digest(value["normalized_text"], value["cues"]) != value.get(
            "alignment_digest"
        ):
            raise NarrationError("prepared narration alignment does not match its digest")
    return value


def _fit_conflict(clip: Clip, content: CompositionContent, duration: float, policy: NarrationPolicy) -> NarrationFitError:
    window = clip.range.duration / content.settings.timebase
    required = duration / max(window, 1 / 30) * policy.fit_margin
    return NarrationFitError(
        f"clip {clip.clip_id} in scene {clip.scene_id}: measured narration is {duration:.3f}s "
        f"for its fixed {window:.3f}s window; fitting needs {required:.3f}× speed "
        f"(allowed {policy.min_speed:.2f}–{policy.max_speed:.2f}×, at most "
        f"{policy.max_attempts} paid attempts). The reviewed text and cut are unchanged; "
        "shorten this scene's narration or revise its window before producing again."
    )


async def _cues(subtitle_file: str | None, normalized_text: str, duration_s: float) -> list[dict]:
    from app.providers.voice import fetch_subtitle_cues

    if not subtitle_file:
        raise NarrationError("T2A returned fixed audio without its subtitle file")
    cues = await asyncio.to_thread(fetch_subtitle_cues, subtitle_file, source_text=normalized_text)
    if cues[-1]["time_end"] > duration_s * 1000 + 150:
        raise NarrationError("T2A sentence timings exceed the decoded narration duration")
    return cues


def _usage(manifest: dict[str, Any]) -> int:
    return int((manifest.get("usage") or {}).get("tts_chars") or 0)


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


async def prepare_speech_media(
    content: CompositionContent,
    *,
    user_id: UUID,
    execution_id: str | None,
    policy: NarrationPolicy,
) -> dict[str, dict[str, Any]]:
    """Prepare every SpeechClip inside its fixed window, with no blind paid replay."""
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
    from app.tools.video.preparation import store_source_bytes

    clips = _speech_clips(content)
    if not clips:
        return {}
    if execution_id is None:
        raise NarrationError("narrated video requires an authorized Run execution identity")
    prepared: dict[str, dict[str, Any]] = {}
    spent = 0
    for clip in clips:
        speech = clip.object
        assert isinstance(speech, SpeechObject)
        key = _manifest_key(execution_id, clip.clip_id)
        manifest = await _read_manifest(key, clip=clip, execution_id=execution_id, policy=policy)
        if manifest is not None and manifest.get("state") == "done":
            prepared[speech.object_id] = manifest
            spent += _usage(manifest)
            continue

        if manifest is not None and manifest.get("state") == "aligning":
            # Adapted audio and usage are fixed; only its subtitle download resumes.
            cues = await _cues(
                (manifest.get("adapted") or {}).get("subtitle_file"),
                manifest["normalized_text"],
                float(manifest["duration_s"]),
            )
            manifest = {
                **manifest,
                "state": "done",
                "cues": cues,
                "alignment_digest": narration_alignment_digest(manifest["normalized_text"], cues),
            }
            await _save_manifest(key, manifest)
            prepared[speech.object_id] = manifest
            spent += _usage(manifest)
            continue

        if manifest is None:
            resolution = await resolve_original(user_id, speech, execution_id=execution_id)
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
                    try:
                        result = await asyncio.to_thread(
                            synthesize_detailed, normalized, speech.voice_id, speech.language, 1.0
                        )
                    except Exception as exc:
                        await mark_outcome_unknown(
                            user_id, speech, execution_id=execution_id, error=str(exc)
                        )
                        raise NarrationOutcomeUnknown(
                            f"clip {clip.clip_id}: original narration outcome is unconfirmed: {exc}"
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
                    run_usage = int(resolution["audio"].get("usage_characters") or 0)
                audio = resolution["audio"]
                cues = await _cues(audio.get("subtitle_file"), normalized, float(audio["duration_s"]))
                original = await complete_alignment(
                    user_id, speech, execution_id=execution_id, cues=cues
                )
                original = {**original, "cache_hit": False, "run_usage": run_usage}
            manifest = {
                "schema_version": 1,
                "state": "original_ready",
                "execution_id": execution_id,
                "request": _request(clip, policy),
                "original": original,
                "usage": {"tts_chars": int(original.get("run_usage") or 0)},
            }
            await _save_manifest(key, manifest)

        original = manifest["original"]
        spent += _usage(manifest)
        window = clip.range.duration / content.settings.timebase
        speed = adaptation_speed(
            duration_s=float(original["duration_s"]),
            window_s=window,
            speed_max=policy.max_speed,
            fit_margin=policy.fit_margin,
        )
        base = {
            "schema_version": 1,
            "execution_id": execution_id,
            "request": _request(clip, policy),
            "original": original,
            "normalized_text": original["normalized_text"],
            "alignment": original["alignment"],
            "usage": manifest.get("usage") or {"tts_chars": 0},
        }
        if speed is None:
            manifest = {
                **base,
                "state": "done",
                "media": original["media"],
                "duration_s": original["duration_s"],
                "cues": original["cues"],
                "alignment_digest": original["alignment_digest"],
                "speed": 1.0,
                "cache_hit": bool(original.get("cache_hit")),
                "attempts": [{
                    "speed": 1.0,
                    "duration_s": original["duration_s"],
                    "tts_chars": int(original.get("run_usage") or 0),
                    "trace_id": original.get("trace_id"),
                }],
            }
            await _save_manifest(key, manifest)
            prepared[speech.object_id] = manifest
            continue

        required = float(original["duration_s"]) / max(window, 1 / 30) * policy.fit_margin
        if policy.max_attempts < 2 or required > policy.max_speed:
            error = _fit_conflict(clip, content, float(original["duration_s"]), policy)
            await _save_manifest(key, {**base, "state": "conflict", "error": str(error)})
            raise error

        normalized = original["normalized_text"]
        _check_budget(policy, spent, normalized)
        submitted = {
            **base,
            "state": "submitted",
            "speed": speed,
            "cache_hit": False,
        }
        await _save_manifest(key, submitted)
        try:
            result = await asyncio.to_thread(
                synthesize_detailed, normalized, speech.voice_id, speech.language, speed
            )
        except Exception as exc:
            raise NarrationOutcomeUnknown(
                f"clip {clip.clip_id}: adapted narration outcome is unconfirmed: {exc}"
            ) from exc
        duration = decode_duration_s(result.audio)
        media_key, media_digest = await store_source_bytes(result.audio, ".mp3", "audio/mpeg")
        await record_media_usage({"tts_chars": float(result.usage_characters)})
        usage = {"tts_chars": _usage(manifest) + result.usage_characters}
        adapted = {
            "media": {"storage_key": media_key, "digest": media_digest, "mime_type": "audio/mpeg"},
            "duration_s": duration,
            "subtitle_file": result.subtitle_file,
            "trace_id": result.trace_id,
            "usage_characters": result.usage_characters,
        }
        if duration > window:
            error = _fit_conflict(clip, content, duration, policy)
            await _save_manifest(key, {
                **base, "state": "conflict", "error": str(error), "speed": speed,
                "adapted": adapted, "usage": usage, "cache_hit": False,
            })
            raise error
        manifest = {
            **base,
            "state": "aligning",
            "media": adapted["media"],
            "duration_s": duration,
            "speed": speed,
            "cache_hit": False,
            "adapted": adapted,
            "usage": usage,
            "attempts": [
                {
                    "speed": 1.0,
                    "duration_s": original["duration_s"],
                    "tts_chars": int(original.get("run_usage") or 0),
                    "trace_id": original.get("trace_id"),
                },
                {
                    "speed": speed,
                    "duration_s": duration,
                    "tts_chars": result.usage_characters,
                    "trace_id": result.trace_id,
                },
            ],
        }
        await _save_manifest(key, manifest)
        cues = await _cues(result.subtitle_file, normalized, duration)
        manifest = {
            **manifest,
            "state": "done",
            "cues": cues,
            "alignment_digest": narration_alignment_digest(normalized, cues),
        }
        await _save_manifest(key, manifest)
        prepared[speech.object_id] = manifest
        spent += result.usage_characters
    return prepared
