"""Pure-function tests for the captions seam (ADR-072 批 A1 — 两站拆分的接缝).

Scope discipline (same as the other *_pure suites): no database, no network
— the shared ``translator`` agent is monkeypatched with a stub whose ``call``
returns a fixed CaptionTranslation. Covers the seam's three surfaces:

- ``build_translation_cues`` (the document station's artifact): unit rows
  carry the source span + joined source text + the translated line, verbatim
  and in order; empty tracks translate to nothing.
- ``spread_translation_cues`` (assemble, single track): word-level
  redistribution is proportional to word length, the last word pins the
  unit's end (no float drift), no-space translations (CJK) degrade to one
  cue per row, empty rows produce nothing.
- ``unit_translation_cues`` (assemble, bilingual): one cue per row, never
  word-split, carries the lang tag, empty translations drop out.
- Wrapper parity: the two public translators are EXACTLY seam + view (zero
  behavior change — the runners keep calling them until 批 A2).
- 批 A2 reuse hook: ``translation_source_hash`` is deterministic, keyed on
  source cue times+words / title / language / style hint, and NEVER on the
  translated text (a user edit must not bust the cache);
  ``find_reusable_translation`` hits per clip on hash match, misses on
  drift, and tolerates malformed artifacts.
"""

from types import SimpleNamespace

import pytest

from app.tools.captions import procedure
from app.tools.captions.procedure import (
    UNIT_WORDS,
    build_translation_cues,
    find_reusable_translation,
    spread_translation_cues,
    translate_caption_track,
    translate_caption_units,
    translation_source_hash,
    unit_translation_cues,
)


def _word_track(words: list[str], start: float = 0.0, step: float = 0.5) -> list[dict]:
    """A word-level caption track: one cue per word, uniform ``step`` spans."""
    return [
        {"start": start + i * step, "end": start + (i + 1) * step, "text": w}
        for i, w in enumerate(words)
    ]


def _stub_translator(monkeypatch: pytest.MonkeyPatch, lines: list[str]) -> list[dict]:
    """Swap the shared translator agent for a stub returning ``lines``;
    returns a list that captures the call kwargs."""
    calls: list[dict] = []

    async def _call(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(lines=list(lines))

    monkeypatch.setattr(procedure, "translator", SimpleNamespace(call=_call))
    return calls


@pytest.mark.asyncio
async def test_build_rows_carry_unit_span_and_source(monkeypatch: pytest.MonkeyPatch):
    words = [f"w{i}" for i in range(UNIT_WORDS * 2)]
    _stub_translator(monkeypatch, ["translated one", "translated two"])

    rows = await build_translation_cues(_word_track(words), "fr")

    assert [r["text"] for r in rows] == ["translated one", "translated two"]
    # Row 1 spans the first UNIT_WORDS words; row 2 the rest.
    assert rows[0]["start"] == 0.0
    assert rows[0]["end"] == UNIT_WORDS * 0.5
    assert rows[1]["start"] == UNIT_WORDS * 0.5
    assert rows[1]["end"] == UNIT_WORDS * 2 * 0.5
    assert rows[0]["source"] == " ".join(words[:UNIT_WORDS])
    assert rows[1]["source"] == " ".join(words[UNIT_WORDS:])


@pytest.mark.asyncio
async def test_build_strips_and_keeps_empty_translation_row(monkeypatch: pytest.MonkeyPatch):
    # A unit the model answers with whitespace survives as an empty-text row
    # (the gap is visible/editable on the document station; the views decide
    # what drops out).
    _stub_translator(monkeypatch, ["  ", "fine"])
    rows = await build_translation_cues(_word_track(["a"] * (UNIT_WORDS + 1)), "fr")
    assert [r["text"] for r in rows] == ["", "fine"]


@pytest.mark.asyncio
async def test_build_empty_track(monkeypatch: pytest.MonkeyPatch):
    calls = _stub_translator(monkeypatch, [])
    assert await build_translation_cues([], "fr") == []
    assert calls == []  # an empty track never buys a translator call


@pytest.mark.asyncio
async def test_build_passes_style_hint_and_language(monkeypatch: pytest.MonkeyPatch):
    calls = _stub_translator(monkeypatch, ["x"])
    await build_translation_cues(_word_track(["a"]), "de", style_hint="terse")
    assert calls[0]["target_language"] == "de"
    assert calls[0]["style_hint"] == "terse"


def test_spread_proportional_and_pins_last_word():
    rows = [{"start": 0.0, "end": 3.0, "source": "a bbb", "text": "aa b"}]
    cues = spread_translation_cues(rows, "fr")
    assert [c["text"] for c in cues] == ["aa", "b"]
    # "aa" takes 2/3 of the span (char-length proportional)…
    assert cues[0]["start"] == 0.0
    assert cues[0]["end"] == pytest.approx(2.0)
    # …and the last word pins the unit end exactly (no float drift).
    assert cues[1]["end"] == 3.0
    assert all(c["lang"] == "fr" for c in cues)


def test_spread_no_space_language_one_cue_per_row():
    rows = [{"start": 1.0, "end": 2.5, "source": "hello", "text": "你好世界"}]
    cues = spread_translation_cues(rows, "zh")
    assert cues == [{"start": 1.0, "end": 2.5, "text": "你好世界", "lang": "zh"}]


def test_spread_empty_rows_produce_nothing():
    rows = [{"start": 0.0, "end": 1.0, "source": "a", "text": ""}]
    assert spread_translation_cues(rows, "fr") == []


def test_unit_view_never_splits_and_drops_empty():
    rows = [
        {"start": 0.0, "end": 1.0, "source": "a b", "text": "un deux trois"},
        {"start": 1.0, "end": 2.0, "source": "c", "text": ""},
    ]
    cues = unit_translation_cues(rows, "fr")
    assert cues == [{"start": 0.0, "end": 1.0, "text": "un deux trois", "lang": "fr"}]


@pytest.mark.asyncio
async def test_wrappers_are_seam_plus_view(monkeypatch: pytest.MonkeyPatch):
    # Parity: translate_caption_track == spread(build(…)),
    # translate_caption_units == unit view of the same rows.
    _stub_translator(monkeypatch, ["bonjour le monde", ""])
    track = _word_track(["hello", "there", "world"] + ["x"] * UNIT_WORDS)

    single = await translate_caption_track(track, "fr")
    assert [c["text"] for c in single] == ["bonjour", "le", "monde"]
    assert all(c["lang"] == "fr" for c in single)

    _stub_translator(monkeypatch, ["bonjour le monde", ""])
    bilingual = await translate_caption_units(track, "fr")
    # Unit 1 = the first UNIT_WORDS words (span 0 → 10×0.5); unit 2's empty
    # translation drops out.
    assert bilingual == [
        {"start": 0.0, "end": UNIT_WORDS * 0.5, "text": "bonjour le monde", "lang": "fr"}
    ]


# ── 批 A2: the reuse hook ────────────────────────────────────────────────


def test_source_hash_deterministic_and_source_sensitive():
    track = _word_track(["hello", "world"])
    base = translation_source_hash(track, "Title", "fr", None)
    assert translation_source_hash(track, "Title", "fr", None) == base
    # A source word change busts it (reprocess / different material)…
    assert translation_source_hash(_word_track(["hello", "there"]), "Title", "fr", None) != base
    # …a timing shift busts it (the artifact's spans would be stale)…
    assert translation_source_hash(_word_track(["hello", "world"], step=0.6), "Title", "fr", None) != base
    # …the title, the language and the persona register each bust it.
    assert translation_source_hash(track, "Other", "fr", None) != base
    assert translation_source_hash(track, "Title", "de", None) != base
    assert translation_source_hash(track, "Title", "fr", "terse") != base


def test_find_reusable_hit_miss_and_tolerance():
    track = _word_track(["a", "b"])
    sh = translation_source_hash(track, "", "fr", None)
    artifact = {
        "clips": {
            "o1": {"source_hash": sh, "rows": [{"start": 0.0, "end": 1.0, "source": "a b", "text": "édité"}]},
            # A second clip drifts independently (per-clip reuse).
            "o2": {"source_hash": "stale", "rows": []},
        }
    }
    hit = find_reusable_translation(artifact, "o1", sh)
    assert hit is not None and hit["rows"][0]["text"] == "édité"
    assert find_reusable_translation(artifact, "o1", "other-hash") is None
    assert find_reusable_translation(artifact, "o2", sh) is None
    assert find_reusable_translation(artifact, "missing", sh) is None
    # Malformed / absent artifacts tolerate to a miss, never a crash.
    assert find_reusable_translation(None, "o1", sh) is None
    assert find_reusable_translation({"clips": "bogus"}, "o1", sh) is None
    assert find_reusable_translation({"clips": {"o1": {"source_hash": sh}}}, "o1", sh) is None
