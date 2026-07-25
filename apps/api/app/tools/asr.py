"""Speech-to-text via faster-whisper (CTranslate2 — self-hosted, EU/GDPR).

Produces a full transcript plus **word-level timestamps**, which are the basis
for the editor's live caption overlay and caption editing (the equivalent of
Descript's "forced alignment"). No PyTorch and no system ffmpeg required:
faster-whisper runs on CTranslate2 and decodes media via PyAV (bundled ffmpeg).

The model is loaded lazily and cached per worker process — the first call
downloads the weights (~150 MB for ``base``).
"""

from pathlib import Path
from typing import Any

import structlog

from app.config import settings

logger = structlog.get_logger()

_model: Any = None


def _get_model() -> Any:
    """Lazily load and cache the faster-whisper model for this process."""
    global _model
    if _model is None:
        from faster_whisper import WhisperModel  # lazy: heavy import

        logger.info("asr_model_loading", model=settings.asr_model)
        _model = WhisperModel(
            settings.asr_model,
            device=settings.asr_device,
            compute_type=settings.asr_compute_type,
        )
    return _model


def transcribe(file_path: Path) -> dict[str, Any]:
    """Transcribe an audio/video file to text + word-level timestamps.

    Returns ``{transcript, words, language, duration}`` where ``words`` is a list
    of ``{start, end, word}`` (seconds). Decoding is handled by faster-whisper
    (PyAV), so video files work without a separate audio-extraction step.
    """
    model = _get_model()
    segments, info = model.transcribe(str(file_path), word_timestamps=True)

    texts: list[str] = []
    words: list[dict[str, Any]] = []
    for seg in segments:  # generator — consuming it runs the transcription
        texts.append(seg.text)
        for w in seg.words or []:
            words.append(
                {"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word}
            )

    return {
        "transcript": "".join(texts).strip(),
        "words": words,
        "language": info.language,
        "duration": info.duration,
    }
