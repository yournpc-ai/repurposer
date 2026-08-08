"""Re-translate a clip's caption track while keeping it WORD-LEVEL.

The renderer and editor both treat ``caption_track`` as word-level cues (grouped
into 7-word display lines; karaoke highlights the active word). Machine
translation, however, only makes sense on whole lines/sentences. So we:

1. group the word cues into translation units (~``UNIT_WORDS`` words each),
2. translate each unit's joined text via the LLM (line-by-line, order preserved),
3. split each translated unit back into words and spread the unit's
   ``[start, end]`` source-time span across them proportionally to word length.

Granularity stays word-level end-to-end, so nothing downstream changes. Target
languages are space-delimited European languages (FR/DE/ES/IT/EN); a no-space
result (e.g. CJK) degrades gracefully to a single cue for the whole unit.
"""

from typing import Any

from app.skills.caption_translate import caption_translate_agent

UNIT_WORDS = 10  # words per translation unit (display re-chunks by 7 anyway)


def _group_units(cues: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Chunk word cues into fixed-size translation units, preserving order."""
    return [cues[i : i + UNIT_WORDS] for i in range(0, len(cues), UNIT_WORDS)]


def _redistribute(
    translated: str, start: float, end: float, lang: str
) -> list[dict[str, Any]]:
    """Spread ``[start, end]`` across the words of ``translated`` by char length."""
    words = translated.split()
    span = max(0.0, end - start)
    if len(words) <= 1 or span == 0:
        # Single token / no-space language / zero span: one cue for the unit.
        text = translated.strip()
        return [{"start": start, "end": end, "text": text, "lang": lang}] if text else []

    total_chars = sum(len(w) for w in words) or len(words)
    cues: list[dict[str, Any]] = []
    cursor = start
    for i, word in enumerate(words):
        if i == len(words) - 1:
            w_end = end  # pin the last word to the unit end (no float drift)
        else:
            w_end = cursor + span * (len(word) / total_chars)
        cues.append({"start": cursor, "end": w_end, "text": word, "lang": lang})
        cursor = w_end
    return cues


async def translate_text(
    text: str,
    target_language: str,
    style_hint: str | None = None,
) -> str:
    """Translate one free-standing string (e.g. the clip title card) — the
    same line-by-line agent, reused with a single line (2026-08-09: a dubbed
    clip with an untranslated title card reads broken; found via the dub
    contrast pack showing the EN title on all four videos)."""
    text = text.strip()
    if not text:
        return ""
    translated = await caption_translate_agent.translate(
        [text], target_language, style_hint=style_hint
    )
    return translated[0].strip() if translated else ""


async def translate_caption_track(
    cues: list[dict[str, Any]],
    target_language: str,
    style_hint: str | None = None,
) -> list[dict[str, Any]]:
    """Translate a word-level caption track into ``target_language``.

    Returns a new word-level track (same shape as the input cues). Raises
    ``MiniMaxError`` if the LLM call fails. ``style_hint`` = persona register
    injection (dub 生产级, 2026-08-07).
    """
    if not cues:
        return []

    units = _group_units(cues)
    unit_texts = [" ".join(str(c["text"]).strip() for c in unit) for unit in units]

    translated = await caption_translate_agent.translate(
        unit_texts, target_language, style_hint=style_hint
    )

    out: list[dict[str, Any]] = []
    for unit, text in zip(units, translated, strict=False):
        start = float(unit[0]["start"])
        end = float(unit[-1]["end"])
        out.extend(_redistribute(text, start, end, target_language))
    return out
