"""MiniMax voice cloning + T2A speech synthesis (sync, for the dub endpoint).

Clone the persona's voice from an audio sample, then synthesize translated text
in that voice. Sync httpx (the dub endpoint awaits it off the request like
translate-captions). GDPR is set aside for the MVP per the product decision; a
future EU-local MiniMax deployment handles residency.
"""

import binascii
import math
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()

_TTS_MODEL = "speech-2.6-hd"


def tts_model() -> str:
    """The synthesis model fact (the narration store's config-hash input —
    a model move is a config change: old originals stop matching, never
    silently reused under a new voice engine)."""
    return _TTS_MODEL


class VoiceError(Exception):
    """Voice provider failure (clone / T2A) — tools/ never imports the LLM
    client (N-29), so the voice wrapper speaks its own error; callers up the
    stack (dub procedure) map it onto their error contract."""

    # Every voice failure reads as the same user line (pipeline/errors.py)
    # unless the raise site names a more honest one (e.g. the film narration
    # fit failure is a design problem — a line too long for its scene —
    # never an outage, so it carries its own key).
    user_key = "voice_unavailable"

    def __init__(self, message: str, *, user_key: str | None = None) -> None:
        super().__init__(message)
        if user_key is not None:
            self.user_key = user_key

# Map our ISO codes to MiniMax `language_boost` names.
_LANG_BOOST = {
    "en": "English",
    "zh": "Chinese",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "it": "Italian",
}


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.minimax_api_key}"}


def clone_voice(audio_path: Path) -> str | None:
    """Upload an audio sample and clone it; return a usable voice_id (or None)."""
    if not settings.minimax_api_key:
        return None
    base = settings.minimax_base_url
    # voice_id: >=8 chars, starts with a letter, alphanumeric.
    voice_id = "vc" + uuid.uuid4().hex[:14]
    try:
        with httpx.Client(timeout=180) as client:
            with audio_path.open("rb") as fh:
                up = client.post(
                    f"{base}/files/upload",
                    headers=_headers(),
                    data={"purpose": "voice_clone"},
                    files={"file": (audio_path.name, fh)},
                )
            up.raise_for_status()
            # MiniMax returns HTTP 200 with an error base_resp on business
            # failure — check it before touching the payload (landmine: a
            # failed upload answers {"file": null, "base_resp": {...}}).
            up_data = up.json()
            base_resp = up_data.get("base_resp") or {}
            if base_resp.get("status_code") != 0:
                raise VoiceError(
                    f"MiniMax file upload failed: {base_resp.get('status_msg')}"
                    f" (code {base_resp.get('status_code')})"
                )
            file_id = (up_data.get("file") or {}).get("file_id")
            if not file_id:
                raise VoiceError(f"file upload returned no file_id: {up.text[:300]}")
            cl = client.post(
                f"{base}/voice_clone",
                headers={**_headers(), "Content-Type": "application/json"},
                json={"file_id": file_id, "voice_id": voice_id},
            )
            cl.raise_for_status()
            cl_resp = cl.json().get("base_resp") or {}
            if cl_resp.get("status_code") != 0:
                raise VoiceError(
                    f"MiniMax voice clone failed: {cl_resp.get('status_msg')}"
                    f" (code {cl_resp.get('status_code')})"
                )
        return voice_id
    except VoiceError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.error("voice_clone_failed", error=str(e))
        raise VoiceError(f"Voice clone failed: {e}") from e


@dataclass(frozen=True)
class T2AResult:
    audio: bytes
    subtitle_file: str | None
    usage_characters: int
    trace_id: str | None


def _synthesize_t2a(
    text: str,
    voice_id: str,
    language: str,
    speed: float,
    *,
    subtitles: bool,
) -> T2AResult:
    if not settings.minimax_api_key:
        raise VoiceError("MINIMAX_API_KEY not configured")
    if not 0.5 <= speed <= 2.0:
        raise VoiceError(f"T2A speed {speed} is outside the provider's 0.5–2.0 range")
    payload = {
        "model": _TTS_MODEL,
        "text": text,
        "stream": False,
        "language_boost": _LANG_BOOST.get(language, "auto"),
        "output_format": "hex",
        "voice_setting": {"voice_id": voice_id, "speed": speed, "vol": 1, "pitch": 0},
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        },
        "subtitle_enable": subtitles,
    }
    if subtitles:
        payload["subtitle_type"] = "sentence"
    try:
        with httpx.Client(timeout=180) as client:
            resp = client.post(
                f"{settings.minimax_base_url}/t2a_v2",
                headers={**_headers(), "Content-Type": "application/json"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        base_resp = data.get("base_resp") or {}
        if base_resp.get("status_code") != 0:
            raise VoiceError(
                f"MiniMax T2A failed: {base_resp.get('status_msg')} "
                f"(code {base_resp.get('status_code')})"
            )
        audio_hex = (data.get("data") or {}).get("audio")
        if not audio_hex:
            raise VoiceError(f"T2A returned no audio: {base_resp}")
        usage = (data.get("extra_info") or {}).get("usage_characters")
        if not isinstance(usage, int) or isinstance(usage, bool) or usage < 0:
            raise VoiceError("T2A returned no valid usage_characters")
        return T2AResult(
            audio=binascii.unhexlify(audio_hex),
            subtitle_file=(data.get("data") or {}).get("subtitle_file"),
            usage_characters=usage,
            trace_id=data.get("trace_id"),
        )
    except VoiceError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.error("t2a_failed", error=str(e))
        raise VoiceError(f"T2A synthesis failed: {e}") from e


def synthesize(text: str, voice_id: str, language: str = "en", speed: float = 1.0) -> bytes:
    """Existing audio-only caller; one non-idempotent POST and no hidden retry."""
    return _synthesize_t2a(text[:9000], voice_id, language, speed, subtitles=False).audio


def synthesize_detailed(
    text: str, voice_id: str, language: str = "en", speed: float = 1.0
) -> T2AResult:
    """One narrated synthesis with sentence-timing metadata, never truncated."""
    if not text or len(text) > 9000:
        raise VoiceError("T2A narration takes 1–9000 characters without truncation")
    return _synthesize_t2a(text, voice_id, language, speed, subtitles=True)


def _parse_subtitle_cues(payload: object, *, source_text: str) -> list[dict]:
    entries = payload
    if isinstance(payload, dict):
        entries = payload.get("subtitles") or payload.get("results")
        if entries is None:
            data = payload.get("data")
            entries = data if isinstance(data, list) else (data or {}).get("subtitles")
    if not isinstance(entries, list) or not entries:
        raise VoiceError("T2A subtitle file has no sentence entries")
    cues: list[dict] = []
    expected_begin = 0
    previous_time_end = 0.0
    for entry in entries:
        if not isinstance(entry, dict):
            raise VoiceError("T2A subtitle entry is not an object")
        begin, end = entry.get("text_begin"), entry.get("text_end")
        start, finish = entry.get("time_begin"), entry.get("time_end")
        if any(isinstance(v, bool) or not isinstance(v, int) for v in (begin, end)):
            raise VoiceError("T2A subtitle text offsets must be integers")
        if any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
            for v in (start, finish)
        ):
            raise VoiceError("T2A subtitle times must be finite millisecond numbers")
        if begin != expected_begin or end <= begin or end > len(source_text):
            raise VoiceError("T2A subtitles do not cover the exact narration text contiguously")
        original = source_text[begin:end]
        if "".join(str(entry.get("text") or "").split()) != "".join(original.split()):
            raise VoiceError("T2A subtitle text differs from the reviewed narration")
        if start < 0 or start < previous_time_end or finish <= start:
            raise VoiceError("T2A subtitle times are not ordered and non-overlapping")
        cues.append({
            "text": original,
            "text_begin": begin,
            "text_end": end,
            "time_begin": float(start),
            "time_end": float(finish),
        })
        expected_begin = end
        previous_time_end = float(finish)
    if expected_begin != len(source_text):
        raise VoiceError("T2A subtitles omit part of the reviewed narration")
    return cues


def fetch_subtitle_cues(subtitle_file: str, *, source_text: str) -> list[dict]:
    """Download and validate MiniMax sentence timing against the exact script."""
    if not subtitle_file.startswith("https://"):
        raise VoiceError("T2A subtitle file is not an HTTPS resource")
    try:
        with httpx.Client(timeout=60) as client:
            response = client.get(subtitle_file)
            response.raise_for_status()
            payload = response.json()
    except VoiceError:
        raise
    except Exception as e:  # noqa: BLE001
        raise VoiceError(f"T2A subtitle download failed: {e}") from e
    return _parse_subtitle_cues(payload, source_text=source_text)


def extract_audio(video_path: Path) -> Path | None:
    """Best-effort: extract a video's audio to a temp 16k mono wav via PyAV.

    Returns None on any failure (caller falls back to an audio voice sample).
    """
    try:
        import av  # faster-whisper dep; no system ffmpeg needed
    except ImportError:
        return None
    try:
        fd, tmp_name = tempfile.mkstemp(suffix=".wav")
        os.close(fd)  # close the handle so the file is deletable later
        out = Path(tmp_name)
        with av.open(str(video_path)) as inp:
            astream = next((s for s in inp.streams if s.type == "audio"), None)
            if astream is None:
                return None
            resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
            with av.open(str(out), "w") as outp:
                ostream = outp.add_stream("pcm_s16le", rate=16000, layout="mono")
                for frame in inp.decode(astream):
                    resampled = resampler.resample(frame)
                    frames = (
                        resampled
                        if isinstance(resampled, list)
                        else [resampled]
                        if resampled is not None
                        else []
                    )
                    for rf in frames:
                        for packet in ostream.encode(rf):
                            outp.mux(packet)
                for packet in ostream.encode(None):
                    outp.mux(packet)
        return out
    except Exception as e:  # noqa: BLE001
        logger.error("extract_audio_failed", path=str(video_path), error=str(e))
        return None
