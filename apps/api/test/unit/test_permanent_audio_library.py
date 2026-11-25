"""Layer 0 pure unit contracts for permanent audio library: voice design, auto-reclone resilience, LUFS, and privacy."""

from __future__ import annotations

import io
import math
import struct
import wave
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import numpy as np
import pytest

from app.config import settings
from app.pipeline import voices as voices_svc
from app.pipeline.music import measure_audio_lufs
from app.providers import storage
from app.providers import voice as voice_provider
from app.providers.voice import (
    T2AResult,
    VoiceDesignResult,
    VoiceError,
    design_voice,
    is_voice_expired_error,
)


def _sine_wav_bytes(*, amplitude: float = 0.25, duration_s: float = 1.0, rate: int = 48000) -> bytes:
    n_samples = int(rate * duration_s)
    t = np.arange(n_samples, dtype=np.float64) / rate
    pcm = np.clip(amplitude * np.sin(2.0 * math.pi * 440.0 * t), -1.0, 1.0)
    int16 = (pcm * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(int16.tobytes())
    return buf.getvalue()


def test_design_voice_parses_hex_audio_and_errors(monkeypatch):
    monkeypatch.setattr(settings, "minimax_api_key", "test-key")
    monkeypatch.setattr(settings, "minimax_base_url", "https://api.example.test/v1")

    sample_bytes = b"ID3-fake-mp3-voiceprint-audio"
    captured: dict = {}

    class _FakeResp:
        def __init__(self, payload: dict):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class _FakeClient:
        def __init__(self, payload: dict):
            self._payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _FakeResp(self._payload)

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda timeout=180: _FakeClient(
            {
                "voice_id": "vd_warm_founder_01",
                "trial_audio": sample_bytes.hex(),
                "trace_id": "trace-vd-123",
                "base_resp": {"status_code": 0, "status_msg": "success"},
            }
        ),
    )

    result = design_voice(
        "Warm composed British founder voice, late 30s, crisp articulation",
        "Welcome to Rookie Cut.",
    )
    assert isinstance(result, VoiceDesignResult)
    assert result.voice_id == "vd_warm_founder_01"
    assert result.trial_audio == sample_bytes
    assert result.trace_id == "trace-vd-123"
    assert captured["url"] == "https://api.example.test/v1/voice_design"
    assert captured["json"]["audio_setting"]["format"] == "mp3"

    # Non-zero status_code raises VoiceError
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda timeout=180: _FakeClient(
            {"base_resp": {"status_code": 2013, "status_msg": "invalid prompt"}}
        ),
    )
    with pytest.raises(VoiceError, match="MiniMax voice design failed"):
        design_voice("bad prompt", "Hello")


def test_is_voice_expired_error_detection():
    assert is_voice_expired_error(VoiceError("MiniMax T2A failed: voice_id not found (code 2054)"))
    assert is_voice_expired_error(VoiceError("MiniMax T2A failed: timbre expired (code 2055)"))
    assert is_voice_expired_error(VoiceError("MiniMax T2A failed: 音色不存在 (code 1042)"))
    assert not is_voice_expired_error(VoiceError("MiniMax T2A failed: rate limit exceeded (code 1002)"))
    assert not is_voice_expired_error(RuntimeError("voice not found"))


@pytest.mark.asyncio
async def test_synthesize_with_voice_resilience_auto_reclones_expired_voice(monkeypatch):
    ref_audio = b"ID3-permanent-reference-audio-bytes"
    voice_row = SimpleNamespace(
        id=uuid4(),
        provider_voice_id="vd_expired_01",
        reference_audio_key="voices/test/reference.mp3",
        meta={},
    )

    async def _fake_read(key: str) -> bytes:
        assert key == "voices/test/reference.mp3"
        return ref_audio

    monkeypatch.setattr(storage, "read", _fake_read)

    seen_clone_bytes: list[bytes] = []

    def _fake_clone(path: Path) -> str:
        seen_clone_bytes.append(path.read_bytes())
        return "vc_recloned_99"

    monkeypatch.setattr(voice_provider, "clone_voice", _fake_clone)

    t2a_calls: list[str] = []

    def _fake_t2a(text: str, voice_id: str, language: str = "en", speed: float = 1.0) -> T2AResult:
        t2a_calls.append(voice_id)
        if voice_id == "vd_expired_01":
            raise VoiceError("MiniMax T2A failed: voice_id not found (code 2054)")
        return T2AResult(
            audio=b"fresh-tts-mp3",
            subtitle_file="https://sub.example.test/cues.json",
            usage_characters=len(text),
            trace_id="trace-ok",
        )

    monkeypatch.setattr(voice_provider, "synthesize_detailed", _fake_t2a)

    res, active_voice_id = await voices_svc.synthesize_with_voice_resilience(
        None,
        text="Ship flagship promos in seconds.",
        voice_ref="vd_expired_01",
        language="en",
        speed=1.0,
        voice_row=voice_row,
    )

    assert t2a_calls == ["vd_expired_01", "vc_recloned_99"]
    assert seen_clone_bytes == [ref_audio]
    assert active_voice_id == "vc_recloned_99"
    assert voice_row.provider_voice_id == "vc_recloned_99"
    assert voice_row.meta["recloned_from"] == "vd_expired_01"
    assert res.audio == b"fresh-tts-mp3"


def test_measure_audio_lufs_ranks_loudness_and_handles_silence():
    loud = _sine_wav_bytes(amplitude=0.5, duration_s=1.0)
    quiet = _sine_wav_bytes(amplitude=0.05, duration_s=1.0)
    silent = _sine_wav_bytes(amplitude=0.0, duration_s=1.0)

    lufs_loud = measure_audio_lufs(loud)
    lufs_quiet = measure_audio_lufs(quiet)
    lufs_silent = measure_audio_lufs(silent)

    assert lufs_loud is not None and lufs_quiet is not None
    assert -15.0 < lufs_loud < -3.0
    assert lufs_loud - lufs_quiet == pytest.approx(20.0, abs=1.0)
    assert lufs_silent is None


def test_voice_privacy_invariant_blocks_platform_clones():
    with pytest.raises(ValueError, match="scope='user'"):
        voices_svc._enforce_voice_privacy(
            source_kind="minimax_clone",
            scope="platform",
            owner_id=uuid4(),
        )
    with pytest.raises(ValueError, match="owner_id"):
        voices_svc._enforce_voice_privacy(
            source_kind="minimax_clone",
            scope="user",
            owner_id=None,
        )
    # Valid user-scoped clone passes
    voices_svc._enforce_voice_privacy(
        source_kind="minimax_clone",
        scope="user",
        owner_id=uuid4(),
    )


def test_voice_design_unsupported_detector_and_stock_voice_matcher():
    assert voice_provider.is_voice_design_unsupported_error(
        VoiceError("MiniMax voice design failed: your current token plan not support model, preview_text (code 2061)")
    )
    assert not voice_provider.is_voice_design_unsupported_error(
        VoiceError("network timeout")
    )
    assert (
        voices_svc._select_curated_stock_voice(
            languages=["en"],
            gender="male",
            prompt="Calm British male baritone for institutional finance",
            tone_tags=["authoritative"],
            compatible_styles=["institutional_dark"],
        )
        == "English_Deep-VoicedGentleman"
    )
    assert (
        voices_svc._select_curated_stock_voice(
            languages=["en"],
            gender="female",
            prompt="Warm BBC scientific documentary narrator",
            tone_tags=["documentary"],
            compatible_styles=["swiss_paper"],
        )
        == "English_Graceful_Lady"
    )
    assert (
        voices_svc._select_curated_stock_voice(
            languages=["zh", "en"],
            gender="male",
            prompt="Modern energetic Chinese tech product launch commercial",
            tone_tags=["energetic"],
            compatible_styles=["vox_editorial"],
        )
        == "male-qn-jingying-jingpin"
    )


@pytest.mark.asyncio
async def test_design_and_save_voice_falls_back_cleanly_on_code_2061(monkeypatch):
    def _fail_design(*_args, **_kwargs):
        raise VoiceError(
            "MiniMax voice design failed: your current token plan not support model, preview_text (code 2061)"
        )

    def _fake_preview(text: str, voice_id: str, language: str = "en") -> T2AResult:
        return T2AResult(
            audio=b"real-speech-26-hd-mp3",
            subtitle_file=None,
            usage_characters=len(text),
            trace_id="trace-stock-preview",
        )

    saved_objects: dict[str, bytes] = {}

    async def _fake_save(key: str, data: bytes, **_kwargs) -> None:
        saved_objects[key] = data

    class _FakeDB:
        def __init__(self) -> None:
            self.added = []

        def add(self, obj) -> None:
            self.added.append(obj)

        async def commit(self) -> None:
            return None

        async def refresh(self, _obj) -> None:
            return None

    monkeypatch.setattr(voice_provider, "design_voice", _fail_design)
    monkeypatch.setattr(voice_provider, "synthesize_preview_mp3", _fake_preview)
    monkeypatch.setattr(voices_svc.storage, "save", _fake_save)

    db = _FakeDB()
    row = await voices_svc.design_and_save_voice(
        db,
        owner_id=uuid4(),
        name="OxValue Baritone",
        prompt="British institutional male baritone narrator",
        preview_text="Valuations boards can defend.",
        languages=["en"],
        tone_tags=["authoritative", "british"],
        compatible_styles=["institutional_dark"],
        gender="male",
    )
    assert row.source_kind == "minimax_stock"
    assert row.provider_voice_id == "English_Deep-VoicedGentleman"
    assert row.meta["fallback_from"] == "minimax_design"
    assert "2061" in row.meta["fallback_reason"]
    assert saved_objects[row.reference_audio_key] == b"real-speech-26-hd-mp3"


@pytest.mark.asyncio
async def test_generate_music_falls_back_to_studio_synth_on_code_2153(monkeypatch):
    from app.pipeline import music as music_svc
    from app.providers.llm.base import LLMError

    assert music_svc.is_minimax_music_unavailable_error(
        LLMError("MiniMax music generation failed: This Music API is no longer available to new users.")
    )

    async def _fail_minimax(*_args, **_kwargs):
        raise LLMError("MiniMax music generation failed: This Music API is no longer available to new users.")

    monkeypatch.setattr(music_svc.minimax_client, "generate_music", _fail_minimax)

    generated = await music_svc.generate_music(
        "Minimal institutional electronic ambient pulse",
        compatible_styles=["institutional_dark"],
        duration_seconds=16,
    )
    assert generated.model == "studio-synth-v2"
    assert generated.ext == "mp3"
    assert generated.size_bytes > 50_000
    assert generated.duration_seconds == 16
    assert generated.extra_meta is not None
    assert generated.extra_meta["fallback_from"] == "minimax_music"
    assert generated.extra_meta["bpm"] == 108
    lufs = measure_audio_lufs(generated.audio_bytes)
    assert lufs is not None and -20.0 <= lufs <= -11.0
