"""Speech-to-text via faster-whisper (CTranslate2 — self-hosted, EU/GDPR).

Produces a full transcript plus **word-level timestamps**, which are the basis
for the editor's live caption overlay and caption editing (the equivalent of
Descript's "forced alignment"). No PyTorch and no system ffmpeg required:
faster-whisper runs on CTranslate2 and decodes media via PyAV (bundled ffmpeg).

The model is loaded lazily and cached per worker process — the first call
downloads the weights (~150 MB for ``base``).

zh 字符集规范化 (2026-09-28): Whisper's Chinese output script is a lottery —
its zh training data skews Traditional, and small models (our default
``base``) have the weakest discrimination, so Mandarin speech often lands
as Traditional characters. We pin nothing at decode time (the product is
multi-language), so the script is normalized AFTER the fact: when the
detected language is ``zh``, the transcript and every word pass through
OpenCC ``t2s`` (Traditional→Simplified, phrase-level) — deterministic,
never another statistical bias. Cantonese (``yue``) is NOT touched: its
natural script is Traditional.
"""

from pathlib import Path
from typing import Any

import structlog

from app.config import settings

logger = structlog.get_logger()

_model: Any = None
_zh_t2s: Any = None


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


def _get_zh_t2s() -> Any:
    """Lazily load and cache the OpenCC Traditional→Simplified converter
    (``t2s`` = phrase-level, not a bare char map — 頭髮→头发)."""
    global _zh_t2s
    if _zh_t2s is None:
        import opencc  # lazy: heavy dictionary load

        _zh_t2s = opencc.OpenCC("t2s")
    return _zh_t2s


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

    transcript = "".join(texts).strip()
    if info.language == "zh":
        # The zh script lottery (module docstring): Whisper picked the
        # script by chance; the product's Chinese register is Simplified —
        # normalize deterministically. The joined transcript converts in
        # one pass (full phrase context); words convert per word (timestamps
        # untouched — words stay the caption evidence truth, C4 不变量).
        t2s = _get_zh_t2s()
        normalized = t2s.convert(transcript)
        if normalized != transcript:
            logger.info(
                "asr_zh_script_normalized",
                chars=len(transcript),
                changed=sum(1 for a, b in zip(transcript, normalized) if a != b),
            )
        transcript = normalized
        for w in words:
            w["word"] = t2s.convert(w["word"])

    return {
        "transcript": transcript,
        "words": words,
        "language": info.language,
        "duration": info.duration,
    }
