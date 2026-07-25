"""MiniMax voice cloning + T2A speech synthesis (sync, for the dub endpoint).

Clone the speaker's voice from an audio sample, then synthesize translated text
in that voice. Sync httpx (the dub endpoint awaits it off the request like
translate-captions). GDPR is set aside for the MVP per the product decision; a
future EU-local MiniMax deployment handles residency.
"""

import binascii
import os
import tempfile
import uuid
from pathlib import Path

import httpx
import structlog

from app.clients.minimax import MiniMaxError
from app.config import settings

logger = structlog.get_logger()

_TTS_MODEL = "speech-2.6-hd"

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
            file_id = up.json().get("file", {}).get("file_id")
            if not file_id:
                raise MiniMaxError(f"file upload returned no file_id: {up.text[:300]}")
            cl = client.post(
                f"{base}/voice_clone",
                headers={**_headers(), "Content-Type": "application/json"},
                json={"file_id": file_id, "voice_id": voice_id},
            )
            cl.raise_for_status()
        return voice_id
    except MiniMaxError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.error("voice_clone_failed", error=str(e))
        raise MiniMaxError(f"Voice clone failed: {e}") from e


def synthesize(text: str, voice_id: str, language: str = "en") -> bytes:
    """Synthesize ``text`` in the cloned ``voice_id`` -> MP3 bytes."""
    if not settings.minimax_api_key:
        raise MiniMaxError("MINIMAX_API_KEY not configured")
    payload = {
        "model": _TTS_MODEL,
        "text": text[:9000],
        "stream": False,
        "language_boost": _LANG_BOOST.get(language, "auto"),
        "output_format": "hex",
        "voice_setting": {"voice_id": voice_id, "speed": 1, "vol": 1, "pitch": 0},
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        },
    }
    try:
        with httpx.Client(timeout=180) as client:
            resp = client.post(
                f"{settings.minimax_base_url}/t2a_v2",
                headers={**_headers(), "Content-Type": "application/json"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        audio_hex = (data.get("data") or {}).get("audio")
        if not audio_hex:
            raise MiniMaxError(f"T2A returned no audio: {data.get('base_resp')}")
        return binascii.unhexlify(audio_hex)
    except MiniMaxError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.error("t2a_failed", error=str(e))
        raise MiniMaxError(f"T2A synthesis failed: {e}") from e


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
