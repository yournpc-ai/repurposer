"""Infer a default for Chat speech from the user's own conversational text."""

import re
from collections.abc import Sequence
from functools import cache

from langdetect.detector_factory import PROFILES_DIRECTORY, DetectorFactory
from langdetect.lang_detect_exception import LangDetectException

from app.models.tables import Message

# A source quotation, URL path, or filename can be longer than the request around it.
_REFERENCES = re.compile(
    r"```[\s\S]*?(?:```|\Z)|`[^`\n]*`|^\s*>[^\n]*"
    r'|"[^"\n]+"|“[^”]+”|「[^」]+」|『[^』]+』|(?<!\w)\x27[^\x27\n]+\x27(?!\w)'
    r"|\[[^\]\n]*\]\((?:https?://|www\.)[^)\n]+\)"
    r"|(?:https?://|www\.)[^\s<>，。；：！？、）】]+"
    r"|\b[\da-f]{8}(?:-[\da-f]{4}){3}-[\da-f]{12}\b"
    r"|\b[\w-]+(?:\.[\w-]+)+\b",
    re.MULTILINE | re.IGNORECASE,
)
_WORDS = re.compile(r"[^\W\d_]+")
_UNSPACED = re.compile(r"[\u0e00-\u0e7f\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")


@cache
def _detector_factory() -> DetectorFactory:
    factory = DetectorFactory()
    factory.set_seed(0)
    factory.load_profile(PROFILES_DIRECTORY)
    return factory


def _language_of(text: str) -> str | None:
    words = _WORDS.findall(_REFERENCES.sub(" ", text[:4096]))
    sample = " ".join(words)
    if len(_UNSPACED.findall(sample)) < 4 and (
        len(words) < 3 or sum(map(len, words)) < 12
    ):
        return None

    detector = _detector_factory().create()
    detector.append(sample)
    try:
        results = detector.get_probabilities()
    except LangDetectException:
        return None
    # The model has separate simplified/traditional profiles for the same language.
    scores: dict[str, float] = {}
    for result in results:
        lang = result.lang.partition("-")[0]
        scores[lang] = scores.get(lang, 0.0) + result.prob
    return next((lang for lang, score in scores.items() if score >= 0.90), None)


def conversation_speech_language(rows: Sequence[Message]) -> str | None:
    """Return the most recent confident ISO 639-1 hint from durable human turns."""
    for row in reversed(rows):
        if row.role != "user" or getattr(row, "suggestion_ref", None):
            continue
        intent = getattr(row, "intent", None) or {}
        if intent.get("answered_question_id") or intent.get("video_confirmation"):
            continue
        language = _language_of(row.content or "")
        if language:
            return language
    return None
