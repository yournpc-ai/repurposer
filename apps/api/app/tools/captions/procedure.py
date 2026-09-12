"""Captions tool's private procedures: re-translate a clip's caption track
while keeping it WORD-LEVEL (relocated from tools/caption_translate.py — the
module imports the translator agent, so it was never a tool, N-29).

The renderer and editor both treat ``caption_track`` as word-level cues (grouped
into 7-word display lines; karaoke highlights the active word). Machine
translation, however, only makes sense on whole lines/sentences. So we:

1. group the word cues into translation units (~``UNIT_WORDS`` words each),
2. translate each unit's joined text via the shared ``translator`` agent
   (line-by-line, order preserved),
3. split each translated unit back into words and spread the unit's
   ``[start, end]`` source-time span across them proportionally to word length.

Granularity stays word-level end-to-end, so nothing downstream changes. Target
languages are space-delimited European languages (FR/DE/ES/IT/EN); a no-space
result (e.g. CJK) degrades gracefully to a single cue for the whole unit.

两站拆分 (ADR-072 批 A): ``build_translation_cues`` is the SEAM — the unit-level
cue rows ({start, end, source, text}) are the DOCUMENT station's persistent,
user-editable artifact; the ASSEMBLE station never calls the translator, it
consumes the rows through the two deterministic views: ``spread_…`` (single
track — word-level redistribution) and ``unit_…`` (bilingual — the whole row
over its span). The two public translators below are thin wrappers over
seam + view (zero behavior change); the runners switch to the seam directly
when the artifact lands (批 A2)."""

from typing import Any

from app.agents.registry import translator

UNIT_WORDS = 10  # words per translation unit (display re-chunks by 7 anyway)

# The artifact's spec key on its owning graph node (批 A2; the document
# station's node in 批 A3 — the runner reads doc-first, node-second).
TRANSLATION_ARTIFACT_KEY = "translation"


def translation_source_hash(
    track: list[dict[str, Any]],
    title_text: str,
    target_language: str,
    style_hint: str | None,
) -> str:
    """Content address for one clip's translation input (批 A2 复用钩):
    the source cue times + words, the title source, the target language and
    the persona style hint. The TRANSLATED text is never hashed (editing the
    translation must NOT bust the cache — 改字后重渲染不再买翻译); a source
    change (reprocess shifts words or timing) does."""
    import hashlib
    import json

    payload = {
        "lang": target_language,
        "style": style_hint or "",
        "title": title_text,
        "cues": [
            [float(c.get("start") or 0), float(c.get("end") or 0), str(c.get("text") or "")]
            for c in track
        ],
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def find_reusable_translation(
    artifact: dict[str, Any] | None, output_id: str, source_hash: str
) -> dict[str, Any] | None:
    """The reuse lookup: the clip's cached entry iff its source hash matches
    (user-edited rows are a HIT — the edit IS the artifact's content)."""
    if not isinstance(artifact, dict):
        return None
    clips = artifact.get("clips")
    if not isinstance(clips, dict):
        return None
    entry = clips.get(output_id)
    if not isinstance(entry, dict) or entry.get("source_hash") != source_hash:
        return None
    if not isinstance(entry.get("rows"), list):
        return None
    return entry


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
    translated = await translator.call(
        lines=[text], target_language=target_language, style_hint=style_hint
    )
    return translated.lines[0].strip() if translated.lines else ""


async def build_translation_cues(
    cues: list[dict[str, Any]],
    target_language: str,
    style_hint: str | None = None,
) -> list[dict[str, Any]]:
    """The translation artifact (ADR-072 两站拆分的文档站产物): one row per
    translation unit — ``{start, end, source, text}`` — the unit's source-time
    span, its joined source text, and the translated line (stripped; may be
    empty when the model returns nothing for a unit — the row survives so the
    gap is visible and editable).

    This is the ONLY translator call site for caption translation; everything
    downstream (single-track spread / bilingual unit cues) derives from these
    rows deterministically. Raises ``MiniMaxError`` if the LLM call fails.
    """
    if not cues:
        return []

    units = _group_units(cues)
    unit_texts = [" ".join(str(c["text"]).strip() for c in unit) for unit in units]

    translated = await translator.call(
        lines=unit_texts, target_language=target_language, style_hint=style_hint
    )

    rows: list[dict[str, Any]] = []
    for unit, text in zip(units, translated.lines, strict=False):
        rows.append(
            {
                "start": float(unit[0]["start"]),
                "end": float(unit[-1]["end"]),
                "source": " ".join(str(c["text"]).strip() for c in unit),
                "text": text.strip(),
            }
        )
    return rows


def spread_translation_cues(
    rows: list[dict[str, Any]], target_language: str
) -> list[dict[str, Any]]:
    """The assemble station's SINGLE-track view: each row's translated text
    redistributed word-level across its span (the renderer's karaoke needs
    word granularity)."""
    out: list[dict[str, Any]] = []
    for row in rows:
        out.extend(
            _redistribute(
                str(row["text"]), float(row["start"]), float(row["end"]), target_language
            )
        )
    return out


def unit_translation_cues(
    rows: list[dict[str, Any]], target_language: str
) -> list[dict[str, Any]]:
    """The assemble station's BILINGUAL view (ClipSpec.translation_track):
    one cue per row, the whole translated line over its span — never
    word-split (a bilingual line is read whole; karaoke stays on the
    original words only). Empty translations drop out."""
    return [
        {
            "start": float(row["start"]),
            "end": float(row["end"]),
            "text": str(row["text"]),
            "lang": target_language,
        }
        for row in rows
        if str(row["text"]).strip()
    ]


async def translate_caption_track(
    cues: list[dict[str, Any]],
    target_language: str,
    style_hint: str | None = None,
) -> list[dict[str, Any]]:
    """Translate a word-level caption track into ``target_language``.

    Returns a new word-level track (same shape as the input cues). Raises
    ``MiniMaxError`` if the LLM call fails. ``style_hint`` = persona register
    injection (dub 生产级, 2026-08-07). Thin wrapper over the seam
    (``build_translation_cues``) + the single-track view.
    """
    return spread_translation_cues(
        await build_translation_cues(cues, target_language, style_hint), target_language
    )


async def translate_caption_units(
    cues: list[dict[str, Any]],
    target_language: str,
    style_hint: str | None = None,
) -> list[dict[str, Any]]:
    """Translate into UNIT-level cues — one cue per ~UNIT_WORDS words, the
    whole translated unit as ``text`` over the unit's [start, end] span.

    This is the 双语对照轨 (ClipSpec.translation_track, 2026-08-14): the
    renderer pairs it with the word-level original track by time overlap and
    shows it as the primary line, so it must NOT be word-split (a bilingual
    line is read whole; karaoke stays on the original words only). Thin
    wrapper over the seam + the bilingual view.
    """
    return unit_translation_cues(
        await build_translation_cues(cues, target_language, style_hint), target_language
    )
