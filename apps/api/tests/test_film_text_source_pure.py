"""Pure tests for the TEXT-source film path (ADR-138 §7.6 — 文字视频).

No database, no LLM, no HTTP. These lock the text source's deterministic
contract: the code-owned manifest split (verbatim character preservation),
the display wrap, readability-owned durations (target rescale never below
the floor, overflow named concretely), the verbatim/authored assembly
discipline (cite vs write), the per-source validator bands, and the
canonical params' text pinning (web fingerprints byte-unchanged).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.schemas import FilmStoryboard
from app.tools.film.storyboard import (
    CONSTRAINT_VIOLATION,
    DURATION_INVALID,
    INVALID_COPY_REF,
    TEXT_TOTAL_SECONDS_RANGE,
    UNSUPPORTED_SCENE,
    CopyRef,
    FilmTextDirection,
    FilmTextSegment,
    FilmTextSource,
    _wrap_display_lines,
    assemble_text_storyboard,
    build_text_manifest,
    canonical_film_params,
    fixed_text_storyboard,
    storyboard_fingerprint,
    storyboard_presentation,
    validate_storyboard,
)

COPY = (
    "Repurposer turns one talk into a week of posts.\n"
    "You record once; the assistant does the rest.\n"
    "Your audience hears from you every week."
)


def _src(**kw) -> FilmTextSource:
    return FilmTextSource(text=COPY, verbatim=True, **kw)


# ---------------------------------------------------------------------------
# build_text_manifest / _wrap_display_lines — the verbatim mechanics
# ---------------------------------------------------------------------------


def test_text_manifest_splits_paragraphs_and_preserves_every_character():
    lines = build_text_manifest(COPY)
    # Clause-granularity citations (7276ef13 修复批): paragraph 2's «;» is a
    # clause boundary — each boundary lands its own citable line.
    assert [l.text for l in lines] == [
        "Repurposer turns one talk into a week of posts.",
        "You record once;",
        "the assistant does the rest.",
        "Your audience hears from you every week.",
    ]
    assert [l.kind for l in lines] == ["paragraph"] * 4
    # Verbatim law: the copy re-reads from the lines (split-point newlines
    # are layout, not content).
    assert " ".join(l.text for l in lines) == " ".join(COPY.split())


def test_text_manifest_sentence_splits_an_over_cap_paragraph_without_loss():
    long_para = (
        "第一句话足够长所以需要被拆分，它包含了很多很多的字符来超过上限。"
        "第二句话同样很长，同样需要被拆分处理，包含更多更多的字符内容！"
        "第三句继续，确保多句拆分正确。"
    ) * 2
    lines = build_text_manifest(long_para)
    assert len(lines) > 1
    joined = "".join(l.text for l in lines)
    assert joined == "".join(long_para.split())


def test_wrap_display_lines_never_loses_a_character():
    text = "关键词 逐字保留 never drops a single word 即使换行也完整"
    wrapped = _wrap_display_lines(text)
    assert len(wrapped) >= 2
    assert "".join("".join(wrapped).split()) == "".join(text.split())


# ---------------------------------------------------------------------------
# Clause-granularity citations (7276ef13 修复批 — the comma-split deadlock)
# ---------------------------------------------------------------------------

# The 7276ef13 incident's confirmed copy, verbatim.
INCIDENT_COPY = (
    "如果觉得身边的一切都太不如意，那就去见喜欢的人，做喜欢的事，买喜欢的东西，"
    "做一个积极向上的人，读温柔的句子，见阳光的人，眼里全是温柔和笑意"
)
# Its eight comma clauses, in order (the split keeps each clause's comma).
INCIDENT_CLAUSES = [
    "如果觉得身边的一切都太不如意，",
    "那就去见喜欢的人，",
    "做喜欢的事，",
    "买喜欢的东西，",
    "做一个积极向上的人，",
    "读温柔的句子，",
    "见阳光的人，",
    "眼里全是温柔和笑意",
]


def test_manifest_splits_clauses_into_individually_citable_lines():
    """The citation unit is the natural sentence/clause boundary — NEVER a
    greedy multi-clause pack (7276ef13: packing the copy into two 3-4-clause
    lines made「按逗号拆成更多幕」mechanically inexpressible — verbatim's
    fit=full citation could not split a packed line across screens)."""
    lines = build_text_manifest(INCIDENT_COPY)
    assert [l.text for l in lines] == INCIDENT_CLAUSES
    # The full copy re-reads from the lines, in order, character-exact.
    assert "".join(l.text for l in lines) == "".join(INCIDENT_COPY.split())
    # A short text under the old pack cap still splits at its clause
    # boundary — comma-splitting is expressible at any length.
    short = build_text_manifest("天黑了，回家吧。")
    assert [l.text for l in short] == ["天黑了，", "回家吧。"]


def test_manifest_sentences_split_without_greedy_merging():
    """Sentence boundaries are citation lines of their own — two short
    sentences in one paragraph are two citable units, never merged into
    one unsplittable pack."""
    lines = build_text_manifest("天黑了。回家吧。")
    assert [l.text for l in lines] == ["天黑了。", "回家吧。"]


def test_verbatim_comma_split_into_eight_screens_assembles_clean():
    """The incident's acceptance shape: the SAME confirmed copy, one comma
    clause per screen — eight scenes, the full text in its own order, the
    real validator clean. No rewriting, no newline cheating."""
    lines = build_text_manifest(INCIDENT_COPY)
    assert len(lines) == 8
    direction = FilmTextDirection(
        segments=[
            FilmTextSegment(refs=[CopyRef(line=l.id)], enter="words")
            for l in lines
        ]
    )
    board, violations = assemble_text_storyboard(
        direction, lines, source=FilmTextSource(text=INCIDENT_COPY, verbatim=True)
    )
    assert violations == []
    assert board is not None and len(board.scenes) == 8
    on_screen = [dl for s in board.scenes for dl in s.lines]
    assert "".join("".join(on_screen).split()) == "".join(INCIDENT_COPY.split())
    assert validate_storyboard(board, [], text_lines=lines) == []
    # The named-count pin agrees with the same segmentation.
    board2, violations2 = assemble_text_storyboard(
        direction, lines,
        source=FilmTextSource(text=INCIDENT_COPY, verbatim=True, scene_count=8),
    )
    assert violations2 == []
    assert board2 is not None and len(board2.scenes) == 8


def test_verbatim_clauses_may_compose_into_fewer_screens():
    """A citation unit is NOT a screen (细分引用 ≠ 强制一句一幕): the same
    copy legally composes into two screens of four clauses each."""
    lines = build_text_manifest(INCIDENT_COPY)
    direction = FilmTextDirection(
        segments=[
            FilmTextSegment(refs=[CopyRef(line=l.id) for l in lines[:4]]),
            FilmTextSegment(refs=[CopyRef(line=l.id) for l in lines[4:]], motion="pull"),
        ]
    )
    board, violations = assemble_text_storyboard(
        direction, lines, source=FilmTextSource(text=INCIDENT_COPY, verbatim=True)
    )
    assert violations == []
    assert board is not None and len(board.scenes) == 2
    on_screen = [dl for s in board.scenes for dl in s.lines]
    assert "".join("".join(on_screen).split()) == "".join(INCIDENT_COPY.split())


def test_verbatim_refs_must_follow_the_texts_own_order():
    """逐字律的顺序半边 (7276ef13 修复批): coverage's exactly-once check alone
    never noticed a REORDER — finer citation units make accidental reorder
    reachable, so the text's own order is enforced deterministically."""
    lines = build_text_manifest(INCIDENT_COPY)
    direction = FilmTextDirection(
        segments=[
            FilmTextSegment(refs=[CopyRef(line=2)]),
            FilmTextSegment(refs=[CopyRef(line=1)]),
            *[FilmTextSegment(refs=[CopyRef(line=l.id)]) for l in lines[2:]],
        ]
    )
    board, violations = assemble_text_storyboard(
        direction, lines, source=FilmTextSource(text=INCIDENT_COPY, verbatim=True)
    )
    assert board is None
    assert any("order" in v.detail and "L1" in v.detail for v in violations)


def test_text_source_drift_note_names_the_drifted_clause():
    """抄录漂移注记 (7276ef13 v3 取证 — 「买喜欢的东西」被重抄成「买喜欢的
    事」): a verbatim redraft that RE-PASTES the copy is trusted verbatim,
    so a drifted re-transcription would otherwise sail through coverage
    against the NEW wrong text. The note names the drifted clause pair
    honestly (never a silent «原文一字未改», never a hard reject — a
    deliberate copy edit stays legal)."""
    from app.tools.film.storyboard import text_source_drift_note

    drifted = INCIDENT_COPY.replace("买喜欢的东西", "买喜欢的事")
    note = text_source_drift_note(drifted, INCIDENT_COPY)
    assert note is not None
    assert "买喜欢的东西" in note and "买喜欢的事" in note
    # Identical re-paste / no restate / no base — no note.
    assert text_source_drift_note(INCIDENT_COPY, INCIDENT_COPY) is None
    assert text_source_drift_note(None, INCIDENT_COPY) is None
    assert text_source_drift_note(drifted, None) is None
    # A length change with no shared-clause drift still says so honestly.
    extended = INCIDENT_COPY + "，眼里有光"
    note = text_source_drift_note(extended, INCIDENT_COPY)
    assert note is not None


def test_text_drift_user_proven_is_a_whitespace_insensitive_substring():
    """漂移的用户可证性 (7276ef13 定点收尾②): the drifted copy is PROVEN
    when the user pasted it themselves this turn — a whitespace-insensitive
    substring of their message. An unproven drift (a layout-only request
    whose model re-transcription added a sentence) is NOT, and never
    green-lights an auto start on the note alone."""
    from app.tools.film.storyboard import text_drift_user_proven

    pasted = INCIDENT_COPY.replace("买喜欢的东西", "买让自己安心的东西")
    # The user pasted the copy with framing words and extra whitespace.
    assert text_drift_user_proven(pasted, f"文案换成：\n  {pasted}\n就按这个来")
    # A layout-only request never proves the model's added sentence.
    assert not text_drift_user_proven(pasted, "只调整排版布局，文案别动")
    # Empty halves never prove anything.
    assert not text_drift_user_proven("", pasted)
    assert not text_drift_user_proven(pasted, "")


# ---------------------------------------------------------------------------
# assemble_text_storyboard — the verbatim / authored discipline
# ---------------------------------------------------------------------------


def test_assemble_text_verbatim_resolves_citations_verbatim():
    lines = build_text_manifest(COPY)
    direction = FilmTextDirection(
        segments=[
            FilmTextSegment(refs=[CopyRef(line=l.id) for l in lines[:3]]),
            FilmTextSegment(refs=[CopyRef(line=lines[3].id)], motion="push", enter="words"),
        ]
    )
    # scene_count unset; two segments.
    board, violations = assemble_text_storyboard(direction, lines, source=_src())
    assert violations == []
    assert board is not None
    assert len(board.scenes) == 2
    on_screen = [dl for s in board.scenes for dl in s.lines]
    assert "".join("".join(on_screen).split()) == "".join(COPY.split())
    # The vocabulary pins ride the scene.
    assert board.scenes[1].motion == "push"
    assert board.scenes[1].enter == "words"
    # Code-owned rhythm: dark alternates by default.
    assert board.scenes[0].dark is False
    assert board.scenes[1].dark is True


def test_assemble_text_verbatim_rejects_rewriting_and_trimming():
    lines = build_text_manifest(COPY)
    # Writing text in verbatim mode = the zero-rewrite law's rejection.
    direction = FilmTextDirection(segments=[FilmTextSegment(text=["my rewrite"])])
    board, violations = assemble_text_storyboard(direction, lines, source=_src())
    assert board is None
    assert any(v.code == CONSTRAINT_VIOLATION for v in violations)
    # fit != full = a trim — rejected, never silently applied.
    direction = FilmTextDirection(
        segments=[FilmTextSegment(refs=[CopyRef(line=1, fit="head")])]
    )
    board, violations = assemble_text_storyboard(direction, lines, source=_src())
    assert board is None
    assert any(v.code == INVALID_COPY_REF for v in violations)


def test_assemble_text_authored_mode_writes_and_rejects_refs():
    direction = FilmTextDirection(
        segments=[
            FilmTextSegment(text=["A short authored line.", "Two beats on screen."]),
            FilmTextSegment(text=["And a closing thought."]),
        ]
    )
    board, violations = assemble_text_storyboard(
        direction,
        [],
        source=FilmTextSource(text="", verbatim=False),
    )
    assert violations == []
    assert board is not None
    assert board.scenes[0].lines == ["A short authored line.", "Two beats on screen."]
    # refs cite a corpus the authored film does not have.
    direction = FilmTextDirection(segments=[FilmTextSegment(refs=[CopyRef(line=1)])])
    board, violations = assemble_text_storyboard(
        direction, [], source=FilmTextSource(text="", verbatim=False)
    )
    assert board is None
    assert any(v.code == CONSTRAINT_VIOLATION for v in violations)


def test_assemble_text_scene_count_pin_is_deterministic():
    lines = build_text_manifest(COPY)
    direction = FilmTextDirection(
        segments=[FilmTextSegment(refs=[CopyRef(line=lines[0].id)]), FilmTextSegment(refs=[CopyRef(line=l.id) for l in lines[1:]])]
    )
    board, violations = assemble_text_storyboard(
        direction, lines, source=_src(scene_count=6)
    )
    assert board is None
    assert any("6" in v.detail for v in violations)
    # …and the matching count lands.
    board, violations = assemble_text_storyboard(
        direction, lines, source=_src(scene_count=2)
    )
    assert violations == []
    assert board is not None and len(board.scenes) == 2


def test_assemble_text_overfull_segment_names_the_split():
    lines = build_text_manifest(COPY)
    direction = FilmTextDirection(
        segments=[FilmTextSegment(refs=[CopyRef(line=l.id) for l in lines])]
    )
    board, violations = assemble_text_storyboard(direction, lines, source=_src())
    assert board is None
    assert any("split this segment" in v.detail for v in violations)


# ---------------------------------------------------------------------------
# Durations — readability floors, target rescale, named overflow
# ---------------------------------------------------------------------------


def test_text_seconds_readability_floor_and_target_rescale():
    lines = build_text_manifest(COPY)
    # One segment per line: floors sit well under the 8s ceiling, so the
    # target rescale has real headroom.
    direction = FilmTextDirection(
        segments=[FilmTextSegment(refs=[CopyRef(line=l.id)]) for l in lines]
    )
    board, _ = assemble_text_storyboard(direction, lines, source=_src())
    assert board is not None
    total = sum(s.seconds for s in board.scenes)
    assert TEXT_TOTAL_SECONDS_RANGE[0] <= total <= TEXT_TOTAL_SECONDS_RANGE[1]
    # A named 20s target lands within the band and never below the floors.
    board, violations = assemble_text_storyboard(
        direction, lines, source=_src(target_seconds=20.0)
    )
    assert violations == []
    assert board is not None
    assert abs(sum(s.seconds for s in board.scenes) - 20.0) < 2.0
    # A named target FASTER than the reading estimate is the user's explicit
    # choice (2026-10-22 拍板 — 估计 = 建议非边界): the floors scale DOWN to
    # the named total, every line still cited, never a rejection.
    board, violations = assemble_text_storyboard(
        direction, lines, source=_src(target_seconds=5.0)
    )
    assert violations == []
    assert board is not None
    assert abs(sum(s.seconds for s in board.scenes) - 5.0) < 1.0
    # The ONE refusal is REAL: a target so small a scene quantizes to zero
    # on the half-second render grid.
    board, violations = assemble_text_storyboard(
        direction, lines, source=_src(target_seconds=0.5)
    )
    assert board is None
    assert any(
        v.code == CONSTRAINT_VIOLATION and "grid" in v.detail for v in violations
    )


def test_same_copy_default_paces_longer_explicit_faster_is_legal():
    """The headline law (2026-10-22 拍板): the SAME copy — no target = the
    reading estimate recommends a LONGER readable film; a named faster
    total = the user's explicit choice, legally produced (every line still
    cited, the validator clean). The estimated pace is A feasible plan,
    never the only legal one — and the presentation names the faster pace
    honestly (never silent, never a rejection)."""
    from app.tools.film.storyboard import _text_source_note

    lines = build_text_manifest(COPY)
    direction = FilmTextDirection(
        segments=[FilmTextSegment(refs=[CopyRef(line=l.id)]) for l in lines]
    )
    # Default: the estimate recommends the floors' total.
    default_board, _ = assemble_text_storyboard(direction, lines, source=_src())
    assert default_board is not None
    default_total = sum(s.seconds for s in default_board.scenes)
    # Explicit faster: half the default — legal, valid, every line shown.
    fast_src = _src(target_seconds=default_total / 2)
    fast_board, violations = assemble_text_storyboard(
        direction, lines, source=fast_src
    )
    assert violations == []
    assert fast_board is not None
    fast_total = sum(s.seconds for s in fast_board.scenes)
    assert fast_total < default_total
    assert validate_storyboard(fast_board, [], text_lines=lines) == []
    # The presentation's pace note names the faster-than-estimate choice…
    note = _text_source_note(fast_src)
    assert note is not None and "faster" in note
    # …and stays silent when the named total is not faster than reading.
    calm = _text_source_note(_src(target_seconds=60.0))
    assert calm is not None and "pace" not in calm


# ---------------------------------------------------------------------------
# validate_storyboard — the per-source bands
# ---------------------------------------------------------------------------


def _text_board(**scene_kw) -> FilmStoryboard:
    base = {"type": "words", "seconds": 3.0, "dark": False}
    return FilmStoryboard.model_validate(
        {
            "scenes": [
                {**base, "lines": ["Short line."], **scene_kw},
                {**base, "dark": True, "lines": ["Second beat here."]},
            ]
        }
    )


def test_validate_text_mode_relaxed_bands_and_illegal_page_scenes():
    lines = build_text_manifest("Short line.\nSecond beat here.")
    board = _text_board()
    # 2 scenes × 3s = 6s total: illegal for the WEB source, legal for text.
    assert validate_storyboard(board, [], text_lines=lines) == []
    web_violations = validate_storyboard(board, [])
    assert any(
        v.code in (CONSTRAINT_VIOLATION, DURATION_INVALID) for v in web_violations
    )
    # A ui scene on a text source = the honest refusal (no page exists).
    with_ui = FilmStoryboard.model_validate(
        {
            "scenes": [
                {"type": "words", "seconds": 3.0, "dark": False, "lines": ["Short line."]},
                {"type": "ui", "seconds": 6.0, "page": 0,
                 "focuses": [{"at": 0.0, "x": 0.5, "y": 0.5, "zoom": 1.0}]},
            ]
        }
    )
    violations = validate_storyboard(with_ui, [], text_lines=lines)
    assert any(v.code == UNSUPPORTED_SCENE for v in violations)


def test_validate_text_mode_fast_pace_is_a_choice_never_a_violation():
    """The reading-time estimate NEVER gates (2026-10-22 拍板): a scene
    faster than its estimated reading time is the user's explicit faster
    pace (named target / patch) — legal. The REAL duration check that
    remains is a positive window (a zero scene renders nothing)."""
    dense = "这段话故意写得非常长，超出三秒钟能够自然阅读的密度上限，用来验证更快的节奏是用户的合法选择而不是违例。"
    lines = build_text_manifest(dense)
    board = FilmStoryboard.model_validate(
        {
            "scenes": [
                {"type": "words", "seconds": 1.0, "dark": i % 2 == 1,
                 "lines": [l.text]}
                for i, l in enumerate(lines)
            ]
        }
    )
    # 1s per dense line is far below the reading estimate — legal now (the
    # presentation's pace note carries the readability impact).
    assert validate_storyboard(board, [], text_lines=lines) == []
    # A zero-length scene is illegal DATA — it renders nothing.
    zeroed = FilmStoryboard.model_validate(
        {
            "scenes": [
                {"type": "words", "seconds": 0.0, "dark": i % 2 == 1,
                 "lines": [l.text]}
                for i, l in enumerate(lines)
            ]
        }
    )
    violations = validate_storyboard(zeroed, [], text_lines=lines)
    assert any(
        v.code == DURATION_INVALID and "scene[0]" in v.detail for v in violations
    )


# ---------------------------------------------------------------------------
# canonical params / fingerprint — text pins, web bytes unchanged
# ---------------------------------------------------------------------------


def test_canonical_params_pin_the_text_source_and_leave_web_untouched():
    web = canonical_film_params({"focus": "x", "voiceover": None})
    assert web == {"focus": "x", "aspect": "16:9", "voiceover": True}
    text = canonical_film_params(
        {"text": COPY, "verbatim": None, "target_seconds": 20.0, "voiceover": False}
    )
    assert text["text"] == COPY
    assert text["verbatim"] is True  # null reads as the user's own copy
    assert text["target_seconds"] == 20.0
    assert text["voiceover"] is False
    assert "scene_count" not in text
    # The fingerprint distinguishes copy — two films over different words
    # never share a version key.
    t1 = [{"tool": "launch_film", "params": {"text": COPY}}]
    t2 = [{"tool": "launch_film", "params": {"text": COPY + "!"}}]
    assert storyboard_fingerprint(t1, None) != storyboard_fingerprint(t2, None)


# ---------------------------------------------------------------------------
# fixed fallback + presentation
# ---------------------------------------------------------------------------


def test_fixed_text_storyboard_segments_greedily_in_order():
    lines = build_text_manifest(COPY)
    board = fixed_text_storyboard(lines, source=_src())
    assert board is not None
    on_screen = [dl for s in board.scenes for dl in s.lines]
    assert "".join("".join(on_screen).split()) == "".join(COPY.split())
    assert fixed_text_storyboard([], source=_src()) is None


def test_text_presentation_names_the_real_source_and_vocabulary():
    lines = build_text_manifest(COPY)
    direction = FilmTextDirection(
        name="Launch week",
        segments=[
            FilmTextSegment(refs=[CopyRef(line=l.id) for l in lines[:2]]),
            FilmTextSegment(refs=[CopyRef(line=l.id) for l in lines[2:]], motion="push", enter="words"),
        ],
    )
    board, _ = assemble_text_storyboard(direction, lines, source=_src())
    assert board is not None
    md = storyboard_presentation(
        board, [], source_note="source: the user's text (verbatim)"
    )
    assert "source: the user's text (verbatim)" in md
    assert "text plane" in md
    assert "push" in md and "word-by-word" in md
    # Echo law: no invented URL anywhere on a text film's fact sheet.
    assert "http" not in md


def test_text_direction_schema_is_closed():
    with pytest.raises(ValidationError):
        FilmTextDirection.model_validate(
            {"segments": [{"text": ["x"], "bogus": 1}]}
        )


def test_copy_ref_reads_the_models_natural_citation_shapes():
    """顺形 read tolerance (the citation wire contract): the model's natural
    spellings — a bare "L3"/"3"/3, or an {"id": ...} object — fold into the
    canonical {"line": int}; genuinely malformed input still rejects
    honestly (no silent coercion)."""
    assert CopyRef.model_validate("L3").line == 3
    assert CopyRef.model_validate("l2").line == 2
    assert CopyRef.model_validate("4").line == 4
    assert CopyRef.model_validate(7).line == 7
    assert CopyRef.model_validate({"id": "L5"}).line == 5
    assert CopyRef.model_validate({"id": 6}).line == 6
    # The canonical shape passes through untouched, fit/accent intact.
    ref = CopyRef.model_validate({"line": 1, "fit": "head", "accent": "x"})
    assert (ref.line, ref.fit, ref.accent) == (1, "head", "x")
    # Honest terminals: an unparseable id or an unknown key still rejects.
    with pytest.raises(ValidationError):
        CopyRef.model_validate({"id": "scene"})
    with pytest.raises(ValidationError):
        CopyRef.model_validate({"line": 1, "weight": 2})
    with pytest.raises(ValidationError):
        CopyRef.model_validate(True)


# ---------------------------------------------------------------------------
# The honest terminals speak the TEXT context (never the web page's)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_text_empty_preflight_keeps_its_own_key_through_the_draft():
    """空文案 preflight: the zero-copy rejection rides its own user key all
    the way out of the draft seat (never relabeled as an ungrounded page)."""
    from types import SimpleNamespace
    from uuid import uuid4

    from app.tools.film.storyboard import (
        FilmStoryboardRejected,
        draft_film_storyboard,
    )

    with pytest.raises(FilmStoryboardRejected) as exc_info:
        await draft_film_storyboard(
            None,
            SimpleNamespace(id=uuid4()),
            instruction="做一支文字片",
            text_source=FilmTextSource(text="  ", verbatim=True),
        )
    assert exc_info.value.user_key == "film_text_empty"


@pytest.mark.asyncio
async def test_text_ladder_exhaustion_speaks_the_text_context(monkeypatch):
    """梯级耗尽: every candidate rejected by the real validator → the
    rejection's user key names the TEXT context (duration/count/copy
    remedies), never the web source's 'clearer page'."""
    from app.tools.film.storyboard import (
        FilmStoryboardRejected,
        _orchestrate_text_storyboard,
        film_text_director,
    )

    async def _bad_direction(**kwargs):
        # Every candidate cites a line the copy does not carry.
        return FilmTextDirection(
            name=None,
            segments=[FilmTextSegment(refs=[CopyRef(line=999)])],
        )

    monkeypatch.setattr(film_text_director, "call", _bad_direction)
    with pytest.raises(FilmStoryboardRejected) as exc_info:
        await _orchestrate_text_storyboard(
            text_source=_src(),
            instruction=None,
            focus=None,
            language=None,
            current=None,
            on_reject=None,
            allow_fixed_fallback=False,
            voiceover=False,
        )
    assert exc_info.value.user_key == "film_text_ungrounded"
    assert "INVALID_COPY_REF" in exc_info.value.codes


# ---------------------------------------------------------------------------
# copy_text — the per-scene PRE-WRAP anchor (折行不入语料律): display lines
# are the layout result; the corpus anchor is set at assembly, accent-free
# ---------------------------------------------------------------------------


def test_assemble_anchors_each_scenes_unwrapped_copy_text():
    copy = "你把专业讲清楚，助手负责把内容送到更多人面前，让价值持续被看见。"
    lines = build_text_manifest(copy)
    direction = FilmTextDirection(
        segments=[FilmTextSegment(refs=[CopyRef(line=l.id) for l in lines])]
    )
    board, violations = assemble_text_storyboard(
        direction, lines, source=FilmTextSource(text=copy, verbatim=True)
    )
    assert violations == []
    scene = board.scenes[0]
    assert len(scene.lines) >= 2  # wrapped for display…
    # …but the anchor holds the UNwrapped corpus: the cited clause lines
    # joined (clause-granularity citations — the anchor re-reads the copy).
    assert scene.copy_text == "\n".join(l.text for l in lines)
    assert "".join(scene.copy_text.split()) == "".join(copy.split())


def test_assemble_copy_text_is_accent_free_and_multi_ref_joined():
    lines = build_text_manifest(COPY)
    direction = FilmTextDirection(
        segments=[
            FilmTextSegment(refs=[CopyRef(line=lines[0].id, accent="one talk"), CopyRef(line=lines[1].id)]),
            FilmTextSegment(refs=[CopyRef(line=l.id) for l in lines[2:]]),
        ]
    )
    board, violations = assemble_text_storyboard(direction, lines, source=_src())
    assert violations == []
    scene = board.scenes[0]
    assert any("*one talk*" in dl for dl in scene.lines)  # the chip is presentation
    assert scene.copy_text == (
        "Repurposer turns one talk into a week of posts.\n"
        "You record once;"
    )


def test_fixed_text_storyboard_anchors_manifest_lines_verbatim():
    lines = build_text_manifest(COPY)
    board = fixed_text_storyboard(lines, source=_src())
    assert board is not None
    joined = "\n".join(s.copy_text or "" for s in board.scenes)
    assert joined == "\n".join(l.text for l in lines)


def test_copy_text_null_reads_absent_in_the_digest():
    """Legacy boards carry no anchor: the materialized null is excluded from
    the digest, so a pre-anchor board keeps its byte-identical identity."""
    from app.tools.film.storyboard import scene_content_digest, storyboard_content_digest

    raw = {"scenes": [{"type": "words", "seconds": 4.0, "dark": False,
                       "lines": ["hello world"]}]}
    legacy = FilmStoryboard.model_validate(raw)
    assert legacy.scenes[0].copy_text is None
    assert storyboard_content_digest(legacy) == storyboard_content_digest(raw)
    assert scene_content_digest(legacy.scenes[0]) == scene_content_digest(raw["scenes"][0])


# ---------------------------------------------------------------------------
# 2026-10-22 文字片需求理解批 (the cf00526d deadlock's fixes):
# natural semantic boundaries + word-atomic splits; the 8s per-scene
# ceiling demoted to a craft default (a long citation line legally earns
# its window); verbatim full-coverage checked deterministically; material
# feasibility decided BEFORE any model call; no-progress stops the ladder.
# ---------------------------------------------------------------------------


def _no_severed_latin_boundary(lines) -> list[tuple[int, str, str]]:
    """Adjacent manifest lines whose boundary falls INSIDE a latin word
    (alnum on both sides = a severed word — the incident's «Superhe|ro»)."""
    import re as _re

    def _alnum(c: str) -> bool:
        return bool(_re.match(r"[A-Za-z0-9]", c))

    return [
        (l.id, l.text[-8:], lines[i + 1].text[:8])
        for i, l in enumerate(lines[:-1])
        if _alnum(l.text[-1]) and _alnum(lines[i + 1].text[0])
    ]


def test_text_manifest_clause_boundaries_and_word_atomicity():
    """A long CJK sentence packs at CLAUSE boundaries; a latin word embedded
    in CJK copy (no surrounding spaces) is never severed — the cut backs
    off to the word's start; the full copy re-reads whitespace-insensitively."""
    copy = (
        "代表寰宇、宇宙、全球人类社会，格局面向全世界；象征跨地域的组织AI网络，"
        "承载中美融合、全球协作，以技术联结东西方文明，走向人类命运共同体的宏大愿景。"
        "每一颗星辰就是一名被超级智能赋能的个体员工，每一个普通人都可以成为Superhero；"
        "万千独立个体星辰相互连接、协同组网，汇聚形成组织级智能。"
    )
    lines = build_text_manifest(copy)
    assert len(lines) > 2  # clause-level segmentation, not one hard-chopped run
    assert _no_severed_latin_boundary(lines) == []
    # Every latin word of the source survives whole inside exactly one line.
    import re as _re

    for word in _re.findall(r"[A-Za-z0-9]+", copy):
        hits = [l for l in lines if word in l.text]
        assert hits, f"{word} lost"
    assert "".join("".join(l.text for l in lines).split()) == "".join(copy.split())
    # Clause boundaries: lines end at a clause/sentence delimiter or a word
    # edge — never mid-clause when a clause boundary was available.
    assert any(l.text.endswith("；") or l.text.endswith("，") for l in lines)


def test_text_manifest_severs_only_an_over_cap_word_itself():
    """The one honest sever: a single latin word longer than the cap cannot
    be kept whole — the hard cut names the layout's own limit (the display
    wrap's over-cap token rule)."""
    copy = "前缀" + "x" * 90 + "后缀继续"
    lines = build_text_manifest(copy)
    assert len(lines) >= 2
    assert "".join("".join(l.text for l in lines).split()) == "".join(copy.split())
    # …but a word that FITS the cap is never severed, even with no spaces.
    copy2 = "每一个普通人都可以成为Superhero；万千个体相互连接组网汇聚。"
    lines2 = build_text_manifest(copy2)
    assert _no_severed_latin_boundary(lines2) == []
    assert any("Superhero" in l.text for l in lines2)


def test_text_seconds_long_line_earns_its_window_past_the_default():
    """The 8s craft default is NOT a ceiling: a citation line whose reading
    estimate crosses it stands as a legal scene (the incident's L3/L7/L9/L12
    — 8.5/8.5/9/9s — were unsplittable units the ceiling made illegal)."""
    dense = "这句话没有任何标点符号只是不断地向前延伸下去" * 3  # one long clause → a 9s line
    lines = build_text_manifest(dense)
    assert len(lines) >= 1
    direction = FilmTextDirection(
        segments=[FilmTextSegment(refs=[CopyRef(line=l.id)]) for l in lines]
    )
    board, violations = assemble_text_storyboard(
        direction, lines, source=FilmTextSource(text=dense, verbatim=True)
    )
    assert violations == []
    assert board is not None
    assert max(s.seconds for s in board.scenes) > 8.0
    # …and the validator agrees: no per-scene ceiling fires anymore.
    assert validate_storyboard(board, [], text_lines=lines) == []


def test_text_read_floor_never_rounds_below_the_estimate():
    """The floor snaps UP to the half-second grid (a floor that rounds down
    lets the validator's own mirror reject the allocator's output)."""
    from app.tools.film.storyboard import _text_read_floor

    assert _text_read_floor(103) == 9.0  # 8.58s estimate → 9.0
    assert _text_read_floor(87) == 7.5  # 7.25 → 7.5
    assert _text_read_floor(78) == 6.5  # exactly 6.5 stays 6.5
    assert _text_read_floor(2) == 2.0  # the absolute floor


def test_assemble_text_verbatim_requires_full_coverage():
    """逐字律's deterministic half: in verbatim mode every manifest line is
    cited EXACTLY ONCE — a dropped line is silent deletion, a repeated one
    is invention; both name the offending lines."""
    lines = build_text_manifest(COPY)
    # L3 silently dropped.
    direction = FilmTextDirection(
        segments=[
            FilmTextSegment(refs=[CopyRef(line=1)]),
            FilmTextSegment(refs=[CopyRef(line=2)]),
        ]
    )
    board, violations = assemble_text_storyboard(direction, lines, source=_src())
    assert board is None
    assert any("L3" in v.detail for v in violations)
    # L2 cited twice.
    direction = FilmTextDirection(
        segments=[
            FilmTextSegment(refs=[CopyRef(line=1), CopyRef(line=2)]),
            FilmTextSegment(refs=[CopyRef(line=2), CopyRef(line=3)]),
        ]
    )
    board, violations = assemble_text_storyboard(direction, lines, source=_src())
    assert board is None
    assert any("twice" in v.detail and "L2" in v.detail for v in violations)


# ---------------------------------------------------------------------------
# _text_feasibility — the pre-model material check
# ---------------------------------------------------------------------------


def test_text_feasibility_beyond_reach_names_the_ceiling():
    """A copy whose MINIMUM footprint (densest legal packing) already passes
    the single-film ceiling fails BEFORE any model call — never after three
    burned candidates, never dressed up as the user's parameter mistake."""
    from app.tools.film.storyboard import _text_feasibility

    long_copy = "这一段话足够长需要逐字保留展示，" * 120  # ≫118s at reading pace
    lines = build_text_manifest(long_copy)
    rejection = _text_feasibility(lines, source=FilmTextSource(text=long_copy, verbatim=True))
    assert rejection is not None
    assert rejection.user_key == "film_text_beyond_reach"
    # The feasible twin passes.
    ok = _text_feasibility(build_text_manifest(COPY), source=_src())
    assert ok is None


def test_text_feasibility_named_target_overflow_is_honest():
    """A named duration is the user's LAW — faster than the reading estimate
    is legal (the explicit faster pace); the REAL named-target conflicts are
    the render frame cap and a scene count below the densest composite
    packing (6 text elements × 4 display lines = 24 on one screen)."""
    from app.tools.film.storyboard import _text_feasibility

    copy = "这一段话足够长需要逐字保留展示，" * 12  # ≈ 30s+ of reading
    lines = build_text_manifest(copy)
    # A named 5s for ~30s of copy: faster than the estimate = the user's
    # explicit choice — the preflight stands aside.
    assert (
        _text_feasibility(
            lines, source=FilmTextSource(text=copy, verbatim=True, target_seconds=5.0)
        )
        is None
    )
    # A named duration over the 120s render frame cap = the REAL refusal.
    rejection = _text_feasibility(
        lines, source=FilmTextSource(text=copy, verbatim=True, target_seconds=150.0)
    )
    assert rejection is not None
    assert rejection.user_key == "film_text_target_overflow"
    # A named scene count below the densest COMPOSITE packing = the REAL
    # refusal (25 display lines > 24 on one screen — the screen-capacity
    # bound, never the 4-line words-plane convenience).
    dense_copy = "\n".join(f"第{i}行文案需要完整展示出来" for i in range(25))
    dense_lines = build_text_manifest(dense_copy)
    rejection = _text_feasibility(
        dense_lines,
        source=FilmTextSource(text=dense_copy, verbatim=True, scene_count=1),
    )
    assert rejection is not None
    assert rejection.user_key == "film_text_target_overflow"
    # The feasible count passes.
    ok = _text_feasibility(
        dense_lines,
        source=FilmTextSource(
            text=dense_copy, verbatim=True, scene_count=len(dense_lines)
        ),
    )
    assert ok is None


def test_text_feasibility_named_target_unlocks_beyond_reach_copy():
    """The headline law's long-copy twin (2026-10-22 拍板): a copy whose
    DEFAULT reading pace passes the 120s frame cap is refused ONLY while no
    duration is named — the same copy with the user's explicit faster total
    (≤ cap) is legally produced (the estimate is A feasible plan, never the
    only legal one; the beyond-reach echo's "OR name a duration" escape must
    be REAL, not a lie). A named total OVER the cap still meets the real
    TARGET_OVERFLOW refusal — the guard never smuggles an over-cap named
    duration past the frame cap."""
    from app.tools.film.storyboard import _text_feasibility

    long_copy = "这一段话足够长需要逐字保留展示，" * 120  # ≫118s at reading pace
    lines = build_text_manifest(long_copy)
    # No named pace: the default rhythm cannot stand inside the cap — refuse.
    rejection = _text_feasibility(lines, source=FilmTextSource(text=long_copy, verbatim=True))
    assert rejection is not None and rejection.user_key == "film_text_beyond_reach"
    # The SAME copy, the user's explicit faster choice (90s ≤ cap): the
    # preflight stands aside…
    fast = FilmTextSource(text=long_copy, verbatim=True, target_seconds=90.0)
    assert _text_feasibility(lines, source=fast) is None
    # …and the named pace yields a LEGAL board end to end — scenes rescaled
    # to the named total, every scene positive, the validator's only hard
    # total law (the frame cap) clean.
    board = fixed_text_storyboard(lines, source=fast)
    assert board is not None
    assert all(s.seconds > 0 for s in board.scenes)
    assert abs(sum(s.seconds for s in board.scenes) - 90.0) <= 0.5 * len(board.scenes)
    assert not [
        v for v in validate_storyboard(board, [], text_lines=lines)
        if v.code == DURATION_INVALID
    ]
    # Edge: default pace over the cap AND the named total over the cap — the
    # real refusal still fires (the bypass never smuggles an over-cap total).
    rejection = _text_feasibility(
        lines, source=FilmTextSource(text=long_copy, verbatim=True, target_seconds=150.0)
    )
    assert rejection is not None
    assert rejection.user_key == "film_text_target_overflow"


@pytest.mark.asyncio
async def test_text_preflight_never_calls_the_model(monkeypatch):
    """The feasibility preflight fires BEFORE the director: an unsatisfiable
    copy costs zero LLM calls (the model is never asked for the impossible)."""
    from app.tools.film.storyboard import (
        FilmStoryboardRejected,
        _orchestrate_text_storyboard,
        film_text_director,
    )

    async def _explode(**kwargs):  # pragma: no cover - must never run
        raise AssertionError("the director was called for an impossible copy")

    monkeypatch.setattr(film_text_director, "call", _explode)
    long_copy = "这一段话足够长需要逐字保留展示，" * 120
    with pytest.raises(FilmStoryboardRejected) as exc_info:
        await _orchestrate_text_storyboard(
            text_source=FilmTextSource(text=long_copy, verbatim=True),
            instruction=None,
            focus=None,
            language=None,
            current=None,
            on_reject=None,
            allow_fixed_fallback=False,
            voiceover=False,
        )
    assert exc_info.value.user_key == "film_text_beyond_reach"


@pytest.mark.asyncio
async def test_text_ladder_stops_on_no_progress(monkeypatch):
    """An identical violation set twice in a row stops the ladder EARLY —
    no third full regeneration re-burning the budget for the same answer."""
    from app.tools.film.storyboard import (
        FilmStoryboardRejected,
        _orchestrate_text_storyboard,
        film_text_director,
    )

    calls = 0

    async def _bad_direction(**kwargs):
        nonlocal calls
        calls += 1
        return FilmTextDirection(
            name=None,
            segments=[FilmTextSegment(refs=[CopyRef(line=999)])],
        )

    monkeypatch.setattr(film_text_director, "call", _bad_direction)
    with pytest.raises(FilmStoryboardRejected) as exc_info:
        await _orchestrate_text_storyboard(
            text_source=_src(),
            instruction=None,
            focus=None,
            language=None,
            current=None,
            on_reject=None,
            allow_fixed_fallback=False,
            voiceover=False,
        )
    assert exc_info.value.user_key == "film_text_ungrounded"
    assert calls == 2  # first candidate + the repeat that proves no progress


@pytest.mark.asyncio
@pytest.mark.parametrize("max_retries", [0, 2, 10])
async def test_text_ladder_progress_keeps_iterating(monkeypatch, max_retries):
    """Different violations = real progress: the ladder keeps its full
    budget of candidates."""
    from app.tools.film.storyboard import (
        FilmStoryboardRejected,
        _orchestrate_text_storyboard,
        film_text_director,
    )

    calls = 0
    monkeypatch.setattr("app.tools.film.storyboard.MAX_REWRITES", max_retries)

    async def _shifting_direction(**kwargs):
        nonlocal calls
        calls += 1
        return FilmTextDirection(
            name=None,
            segments=[FilmTextSegment(refs=[CopyRef(line=999 + calls)])],
        )

    monkeypatch.setattr(film_text_director, "call", _shifting_direction)
    with pytest.raises(FilmStoryboardRejected):
        await _orchestrate_text_storyboard(
            text_source=_src(),
            instruction=None,
            focus=None,
            language=None,
            current=None,
            on_reject=None,
            allow_fixed_fallback=False,
            voiceover=False,
        )
    assert calls == 1 + max_retries  # each candidate has a distinct failure


# ---------------------------------------------------------------------------
# 重新归类 (2026-10-22 用户拍板): craft defaults vs real technical bounds
# ---------------------------------------------------------------------------


def test_text_total_upper_is_the_frame_cap_and_the_lower_is_craft():
    """The text total's REAL upper is the render frame cap
    (FILM_MAX_FRAMES / FILM_FPS = 3600/30 = 120.0s — the old 118 misread
    it); the 5s lower is a craft suggestion (the allocator's top-up seat),
    never a rejection."""
    from app.tools.film.storyboard import FILM_FPS, FILM_MAX_FRAMES

    assert TEXT_TOTAL_SECONDS_RANGE[1] == FILM_MAX_FRAMES / FILM_FPS == 120.0
    # Two readable 2s scenes = 4s total < the 5s craft lower — the board
    # stands (the lower band is a suggestion, not a gate).
    lines = build_text_manifest("好。\n行。")
    board = FilmStoryboard.model_validate(
        {
            "scenes": [
                {"type": "words", "seconds": 2.0, "dark": False, "lines": ["好。"]},
                {"type": "words", "seconds": 2.0, "dark": True, "lines": ["行。"]},
            ]
        }
    )
    assert validate_storyboard(board, [], text_lines=lines) == []
    # 121s of readable scenes crosses the REAL cap — rejected and named as
    # the frame cap (never as a craft-band miss).
    lines = build_text_manifest("x" * 40)
    big = FilmStoryboard.model_validate(
        {
            "scenes": [
                {"type": "words", "seconds": 11.0, "dark": i % 2 == 0,
                 "lines": ["x" * 40]}
                for i in range(11)
            ]
        }
    )
    violations = validate_storyboard(big, [], text_lines=lines)
    assert any(
        v.code == DURATION_INVALID and "frame cap" in v.detail for v in violations
    )


def test_text_scene_count_band_is_craft_not_a_rejection():
    """The 2..30 count band is a craft DEFAULT (prompt guidance + the
    preflight's satisfiable range), never an unconditional validator
    rejection: a one-scene film stands when the scene is readable. The WEB
    source's count law is untouched."""
    lines = build_text_manifest("一句话成片。")
    board = FilmStoryboard.model_validate(
        {
            "scenes": [
                {"type": "words", "seconds": 2.5, "dark": False,
                 "lines": ["一句话成片。"]}
            ]
        }
    )
    assert validate_storyboard(board, [], text_lines=lines) == []
    web = validate_storyboard(board, [])
    assert any(
        v.code == CONSTRAINT_VIOLATION and "scene count" in v.detail for v in web
    )


def test_text_feasibility_count_band_is_craft_not_a_gate():
    """A copy needing 31 planes at its densest packing is NOT beyond reach
    when its reading floors fit the frame cap — the 30-plane craft band
    never gates; only the floors_sum (real) does."""
    from app.tools.film.storyboard import _text_feasibility

    # 121 one-row lines of 10 latin chars: densest packing = 4 rows/plane
    # → 31 planes; floors ≈ 30 × 3.5s + 2s = 107s ≤ 120s — a legal (if
    # busy) film the old 30-plane band rejected pre-model.
    copy = "\n".join(f"line{i:03d}abc" for i in range(121))
    lines = build_text_manifest(copy)
    assert len(lines) == 121
    assert (
        _text_feasibility(lines, source=FilmTextSource(text=copy, verbatim=True))
        is None
    )


def test_text_feasibility_named_count_range_is_the_real_satisfiable_span():
    """The named-count range is the REAL satisfiable span — the densest
    packing (display caps) to the line count (every segment cites at least
    one line); the craft band's 2..30 never enters."""
    from app.tools.film.storyboard import _text_feasibility

    one = "只有一句话。"
    lines = build_text_manifest(one)
    assert len(lines) == 1
    # A named single scene stands (the craft lower 2 is guidance only).
    assert (
        _text_feasibility(
            lines, source=FilmTextSource(text=one, verbatim=True, scene_count=1)
        )
        is None
    )
    # Two scenes from one line = a scene with nothing to cite — honestly
    # refused, pre-model.
    rejection = _text_feasibility(
        lines, source=FilmTextSource(text=one, verbatim=True, scene_count=2)
    )
    assert rejection is not None
    assert rejection.user_key == "film_text_target_overflow"


# ---------------------------------------------------------------------------
# film_verbatim_birth_pin — 贴文 ≠ 逐字 (2026-10-22 用户拍板)
# ---------------------------------------------------------------------------


def test_film_verbatim_birth_pin_inherits_the_decided_version():
    """An unset verbatim inherits the BASE version's pinned mode (执行提案
    继承已确定版本, never a re-guess from the pasted text); explicit values
    pin; only a genuinely new text film reads null as preserve (the safe
    legacy-compatible read); no text source = the key drops out."""
    from app.tools.film.storyboard import film_verbatim_birth_pin

    # Explicit pins, both ways.
    assert film_verbatim_birth_pin(False, None, base_present=False, text_present=True) is False
    assert film_verbatim_birth_pin(True, None, base_present=False, text_present=True) is True
    # A redraft inherits the decided version's mode — False stays False
    # (the old null→True re-guess would have flipped it).
    base_adapted = {"text": COPY, "verbatim": False, "voiceover": False}
    assert film_verbatim_birth_pin(None, base_adapted, base_present=True, text_present=True) is False
    base_verbatim = {"text": COPY, "verbatim": True, "voiceover": False}
    assert film_verbatim_birth_pin(None, base_verbatim, base_present=True, text_present=True) is True
    # A legacy base whose params predate the explicit pin reads as preserve
    # (the historical lens), as does a base with no params record at all.
    legacy = {"text": COPY, "voiceover": False}
    assert film_verbatim_birth_pin(None, legacy, base_present=True, text_present=True) is True
    assert film_verbatim_birth_pin(None, None, base_present=True, text_present=True) is True
    # A genuinely new text film with no declared mode: preserve (never
    # silently rewrite the user's words).
    assert film_verbatim_birth_pin(None, None, base_present=False, text_present=True) is True
    # No text source = the key drops out of the canonical form.
    assert film_verbatim_birth_pin(None, None, base_present=False, text_present=False) is None
    assert film_verbatim_birth_pin(True, None, base_present=False, text_present=False) is None


# ---------------------------------------------------------------------------
# B1 — the text film never emits the web "capturing" phase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_phases_text_never_emits_capturing(monkeypatch):
    """B1: a text film reads no page — its draft's first phase is
    "storyboarding" and no capture wait runs; "capturing" belongs to the
    WEB branch alone (emitted byte-for-byte as before)."""
    from types import SimpleNamespace

    import app.tools.film.storyboard as sb

    async def _board(**kwargs):
        return FilmStoryboard.model_validate(
            {
                "scenes": [
                    {"type": "words", "seconds": 3.0, "dark": False,
                     "lines": ["Short line."]}
                ]
            }
        )

    monkeypatch.setattr(sb, "orchestrate_storyboard", _board)
    project = SimpleNamespace(id="p1")

    # Text branch: no "capturing", no capture wait.
    async def _no_captures(project_id):  # pragma: no cover - must never run
        raise AssertionError("a text film never waits on captures")

    monkeypatch.setattr(sb, "_await_captures_settled", _no_captures)
    phases: list[str | None] = []

    async def _phase(label):
        phases.append(label)

    result = await sb.draft_film_storyboard(
        None, project, instruction=None, on_progress=_phase, text_source=_src()
    )
    assert result is not None
    assert phases == ["storyboarding", None]

    # Web branch: "capturing" leads, byte-for-byte.
    async def _settled(project_id):
        return None

    async def _pages(db, project):
        return [SimpleNamespace()]

    async def _media(pages):
        return []

    monkeypatch.setattr(sb, "_await_captures_settled", _settled)
    monkeypatch.setattr(sb, "load_storyboard_pages", _pages)
    monkeypatch.setattr(sb, "page_media_inputs", _media)
    phases.clear()
    result = await sb.draft_film_storyboard(
        None, project, instruction=None, on_progress=_phase
    )
    assert result is not None
    assert phases == ["capturing", "storyboarding", None]


# ---------------------------------------------------------------------------
# Composite birth (ADR-140 出生面, 下批 A2) — the text source's media
# composition through the REAL design chain: the director's draft
# vocabulary (no element_id — code owns identity), assembly (id minting,
# frame-law derived seconds, verbatim coverage across mixed segments,
# copy anchors), the target-duration law with material-bound scenes, the
# revision-base projection, the deployment gate, and the orchestration
# seat's media wiring (loader → validator at birth).
# ---------------------------------------------------------------------------

_COMPOSITE_DIRECTION = {
    "name": "demo",
    "segments": [
        {"refs": [{"line": 1}]},
        {
            "elements": [
                {
                    "kind": "video",
                    "asset": "a1",
                    "source_start": 0.0,
                    "source_end": 8.0,
                    "rect": {"x": 0.5, "y": 0.0, "w": 0.5, "h": 1.0},
                },
                {
                    "kind": "text",
                    "refs": [{"line": 2}, {"line": 3}, {"line": 4}],
                    "at": 0.5,
                    "until": 7.5,
                    "rect": {"x": 0.05, "y": 0.2, "w": 0.4, "h": 0.6},
                },
            ],
        },
    ],
}


def _media(**over) -> "object":
    from app.tools.film.storyboard import StoryboardMedia, StoryboardMediaAsset

    entry = dict(
        id="a1", key="k/a1.mp4", kind="video", title="demo",
        duration_seconds=8.0, width=None, height=None,
    )
    entry.update(over)
    return StoryboardMedia(assets={"a1": StoryboardMediaAsset(**entry)})


def test_composite_segment_parses_and_words_stays_compact():
    """The direction union: a words segment keeps its compact shape; a
    composite segment carries elements; the draft vocabulary never accepts
    element_id (code owns identity — the wire never teaches the handle)."""
    direction = FilmTextDirection.model_validate(_COMPOSITE_DIRECTION)
    from app.tools.film.storyboard import FilmCompositeSegment, FilmTextSegment

    assert isinstance(direction.segments[0], FilmTextSegment)
    assert isinstance(direction.segments[1], FilmCompositeSegment)
    with pytest.raises(ValidationError):
        FilmTextDirection.model_validate(
            {
                "segments": [
                    {
                        "elements": [
                            {
                                "kind": "video", "asset": "a1",
                                "source_start": 0.0, "source_end": 8.0,
                                "element_id": "e9",
                            }
                        ]
                    }
                ]
            }
        )


def test_assemble_composite_happy_path_mints_ids_and_derives_seconds():
    lines = build_text_manifest(COPY)
    direction = FilmTextDirection.model_validate(_COMPOSITE_DIRECTION)
    board, violations = assemble_text_storyboard(
        direction, lines, source=_src(), composite_ok=True
    )
    assert violations == []
    words, composite = board.scenes
    assert words.type == "words" and composite.type == "composite"
    # Element ids minted at birth (e1..eN — the positional law
    # ensure_scene_ids would derive later; digest-neutral either way).
    assert [e.element_id for e in composite.elements] == ["e1", "e2"]
    # Scene seconds derive from the element windows on the frame grid:
    # video span 8s → 240f; text until 7.5 → 225f; scene = 240f = 8.0s.
    assert composite.seconds == 8.0
    # The text element's copy anchors pre-wrap (逐字律, per element).
    text_el = composite.elements[1]
    assert text_el.copy_text == (
        "You record once;\n"
        "the assistant does the rest.\n"
        "Your audience hears from you every week."
    )
    # Dark alternates across mixed scenes by position.
    assert words.dark is False and composite.dark is True
    # The board faces the FULL validator with its media universe.
    assert (
        validate_storyboard(board, [], text_lines=lines, media=_media()) == []
    )


def test_assemble_composite_derived_seconds_frame_law():
    """The frame law (端点先量化 — the SAME accounting the validator
    applies): explicit play windows, sub-grid spans snapping UP to the
    half-second grid, and the 1s structural floor."""
    lines = build_text_manifest(COPY)

    def _composite_seconds(**video_over):
        video = {
            "kind": "video", "asset": "a1",
            "source_start": 0.0, "source_end": 8.0,
        }
        video.update(video_over)
        direction = FilmTextDirection.model_validate(
            {
                "segments": [
                    {"refs": [{"line": 1}, {"line": 2}]},
                    {"elements": [video]},
                    {"refs": [{"line": 3}, {"line": 4}]},
                ]
            }
        )
        board, violations = assemble_text_storyboard(
            direction, lines, source=_src(), composite_ok=True
        )
        assert violations == []
        scene = board.scenes[1]
        # The assembled board never rejects ITSELF on the grid.
        assert (
            validate_storyboard(board, [], text_lines=lines, media=_media(
                duration_seconds=30.0
            ))
            == []
        )
        return scene.seconds

    # Full source span (default play window): 8s → 240f → 8.0s.
    assert _composite_seconds() == 8.0
    # Explicit play window: 5s → 150f → 5.0s.
    assert _composite_seconds(duration=5.0) == 5.0
    # Sub-grid span snaps UP to the half-second grid: 8.02s → 241f →
    # 255f = 8.5s (never quantize-the-delta below the quantized end).
    assert _composite_seconds(source_end=8.02) == 8.5
    # The 1s structural floor holds a tiny window.
    assert _composite_seconds(source_end=0.5) == 1.0


def test_assemble_composite_unbounded_scene_is_a_repairable_violation():
    lines = build_text_manifest(COPY)
    direction = FilmTextDirection.model_validate(
        {
            "segments": [
                {"refs": [{"line": 1}]},
                {
                    "elements": [
                        {"kind": "image", "asset": "a2"},
                        {"kind": "text", "refs": [{"line": 2}, {"line": 3}]},
                    ]
                },
            ]
        }
    )
    board, violations = assemble_text_storyboard(
        direction, lines, source=_src(), composite_ok=True
    )
    assert board is None
    assert any(
        v.code == CONSTRAINT_VIOLATION and "none of these elements bounds it" in v.detail
        for v in violations
    )


def test_assemble_composite_cross_field_breach_is_a_violation_not_a_crash():
    """until ≤ at and a play window past the source span are draft defects
    the bounded rewrite repairs — FilmViolations, never a ladder-crashing
    ValidationError."""
    lines = build_text_manifest(COPY)
    direction = FilmTextDirection.model_validate(
        {
            "segments": [
                {"refs": [{"line": 1}]},
                {
                    "elements": [
                        {
                            "kind": "video", "asset": "a1",
                            "source_start": 0.0, "source_end": 8.0,
                            "duration": 9.0,
                        },
                        {
                            "kind": "text", "refs": [{"line": 2}, {"line": 3}],
                            "at": 5.0, "until": 3.0,
                        },
                    ]
                },
            ]
        }
    )
    board, violations = assemble_text_storyboard(
        direction, lines, source=_src(), composite_ok=True
    )
    assert board is None
    details = " | ".join(v.detail for v in violations)
    assert "segment[2].element1" in details  # play > span
    assert "segment[2].element2" in details  # until ≤ at


def test_assemble_composite_gate_off_is_a_repairable_violation():
    """执行端门控: gate OFF, a composite segment never assembles — the
    refusal names the deployment, the words arc stays available."""
    lines = build_text_manifest(COPY)
    direction = FilmTextDirection.model_validate(_COMPOSITE_DIRECTION)
    board, violations = assemble_text_storyboard(
        direction, lines, source=_src(), composite_ok=False
    )
    assert board is None
    assert any("not available in this deployment" in v.detail for v in violations)


def test_assemble_composite_verbatim_coverage_counts_text_elements():
    """逐字律 across mixed segments: a manifest line only cited inside a
    composite text element counts; a dropped line or a duplicated one
    (words + element both citing it) is the same coverage violation."""
    lines = build_text_manifest(COPY)
    # All four lines inside the composite's text element — full coverage.
    direction = FilmTextDirection.model_validate(
        {
            "segments": [
                {
                    "elements": [
                        {"kind": "video", "asset": "a1",
                         "source_start": 0.0, "source_end": 8.0},
                        {"kind": "text",
                         "refs": [{"line": 1}, {"line": 2}, {"line": 3},
                                  {"line": 4}],
                         "until": 7.5},
                    ]
                }
            ]
        }
    )
    board, violations = assemble_text_storyboard(
        direction, lines, source=_src(), composite_ok=True
    )
    # L1+L2+L3+L4 wrap to 2+1+1+2 = 6 display lines — over the element's
    # 4-line cap; split across TWO text elements instead.
    assert board is None
    assert any("display" in v.detail for v in violations)

    direction = FilmTextDirection.model_validate(
        {
            "segments": [
                {
                    "elements": [
                        {"kind": "video", "asset": "a1",
                         "source_start": 0.0, "source_end": 8.0},
                        {"kind": "text", "refs": [{"line": 1}, {"line": 2}],
                         "until": 7.5},
                        {"kind": "text", "refs": [{"line": 3}, {"line": 4}],
                         "at": 0.5, "until": 7.0, "tone": "dark"},
                    ]
                }
            ]
        }
    )
    board, violations = assemble_text_storyboard(
        direction, lines, source=_src(), composite_ok=True
    )
    assert violations == []
    scene = board.scenes[0]
    assert len(scene.elements) == 3
    # A duplicated citation (the words plane AND an element citing L1) is
    # the coverage law's invention half.
    direction = FilmTextDirection.model_validate(
        {
            "segments": [
                {"refs": [{"line": 1}]},
                {
                    "elements": [
                        {"kind": "video", "asset": "a1",
                         "source_start": 0.0, "source_end": 8.0},
                        {"kind": "text",
                         "refs": [{"line": 1}, {"line": 2}, {"line": 3},
                                  {"line": 4}],
                         "until": 7.5},
                    ]
                },
            ]
        }
    )
    board, violations = assemble_text_storyboard(
        direction, lines, source=_src(), composite_ok=True
    )
    assert board is None
    assert any("cited twice: L1" in v.detail for v in violations)


def test_assemble_composite_target_law_with_material_bound_scenes():
    """The named total paces the words planes into the REMAINING room
    (target − composite); no room = an honest refusal; an all-composite
    board with a named total must match it at the FRAME level — a match
    passes, a mismatch refuses with the concrete delta (the material owns
    the length — never silently stretched, looped or padded)."""
    lines = build_text_manifest(COPY)
    direction = FilmTextDirection.model_validate(_COMPOSITE_DIRECTION)
    board, violations = assemble_text_storyboard(
        direction, lines, source=_src(target_seconds=20.0), composite_ok=True
    )
    assert violations == []
    words, composite = board.scenes
    assert composite.seconds == 8.0  # material-bound, never rescaled
    assert words.seconds == 12.0  # the remaining room, to the grid

    # No room: the composite already fills the named total.
    board, violations = assemble_text_storyboard(
        direction, lines, source=_src(target_seconds=8.0), composite_ok=True
    )
    assert board is None
    assert any("already filled by the media" in v.detail for v in violations)

    # All-composite + a named total: a frame-level match is the law — the
    # mismatch refuses with the concrete delta and the levers named.
    direction = FilmTextDirection.model_validate(
        {
            "segments": [
                {
                    "elements": [
                        {"kind": "video", "asset": "a1",
                         "source_start": 0.0, "source_end": 8.0},
                        {"kind": "text",
                         "refs": [{"line": 1}, {"line": 2}, {"line": 3},
                                  {"line": 4}],
                         "until": 7.5},
                    ]
                },
                {
                    "elements": [
                        {"kind": "image", "asset": "a2", "until": 4.0},
                    ]
                },
            ]
        }
    )
    # (refs over-cap inside one element — but the target refusal fires on
    # the seconds law; drop to two text elements to isolate it.)
    direction = FilmTextDirection.model_validate(
        {
            "segments": [
                {
                    "elements": [
                        {"kind": "video", "asset": "a1",
                         "source_start": 0.0, "source_end": 8.0},
                        {"kind": "text", "refs": [{"line": 1}, {"line": 2}],
                         "until": 7.5},
                        {"kind": "text", "refs": [{"line": 3}, {"line": 4}],
                         "until": 7.0},
                    ]
                },
            ]
        }
    )
    board, violations = assemble_text_storyboard(
        direction, lines, source=_src(target_seconds=30.0), composite_ok=True
    )
    assert board is None
    # The mismatch reports the CONCRETE delta (30s named vs the 8s
    # material-derived total → 660 frames short on the render grid) —
    # never a blanket "cannot be paced out", never a words-filler demand.
    (v,) = [v for v in violations if "30" in v.detail]
    assert "8s" in v.detail and "660" in v.detail and "short" in v.detail
    assert "text planes" not in v.detail


def test_current_direction_projection_covers_composite_scenes():
    """修订基于当前稿 completeness: a composite scene projects its element
    facts (asset ids / windows / placements / copy) — code-owned seats
    (element_id, copy_text) never ride the base."""
    from app.tools.film.storyboard import current_text_direction_dict

    lines = build_text_manifest(COPY)
    direction = FilmTextDirection.model_validate(_COMPOSITE_DIRECTION)
    board, _ = assemble_text_storyboard(
        direction, lines, source=_src(), composite_ok=True
    )
    projection = current_text_direction_dict(board)
    assert projection["segments"][0]["type"] == "words"
    composite = projection["segments"][1]
    assert composite["type"] == "composite"
    video, text_el = composite["elements"]
    assert video["asset"] == "a1" and video["source_end"] == 8.0
    assert "element_id" not in video and "copy_text" not in text_el
    assert text_el["lines"] == board.scenes[1].elements[1].lines


@pytest.mark.asyncio
async def test_orchestrate_composite_birth_validates_against_media(monkeypatch):
    """The orchestration seat wires birth-time media truth: the director's
    call carries the candidate listing + the gate, and the candidate board
    faces the validator WITH its media universe (the loader sees the
    resolved board)."""
    from app.tools.film.storyboard import (
        _orchestrate_text_storyboard,
        film_text_director,
    )

    seen: dict = {}

    async def _direction(**kwargs):
        seen["call"] = kwargs
        return FilmTextDirection.model_validate(_COMPOSITE_DIRECTION)

    monkeypatch.setattr(film_text_director, "call", _direction)
    loaded = []

    async def _loader(board):
        loaded.append(board)
        return _media()

    candidates = [{"id": "a1", "kind": "video", "title": "demo",
                   "duration_seconds": 8.0, "width": None, "height": None,
                   "usable": True, "processing": "completed"}]
    board = await _orchestrate_text_storyboard(
        text_source=_src(),
        instruction=None,
        focus=None,
        language=None,
        current=None,
        on_reject=None,
        allow_fixed_fallback=False,
        voiceover=False,
        media_candidates=candidates,
        media_loader=_loader,
        composite_ok=True,
    )
    assert any(s.type == "composite" for s in board.scenes)
    assert seen["call"]["media"] == candidates
    assert seen["call"]["composite_ok"] is True
    assert loaded == [board]  # the loader validated THE resolved board


@pytest.mark.asyncio
async def test_orchestrate_composite_gate_off_rejects_every_candidate(monkeypatch):
    """Gate OFF at the orchestration seat: a composite direction never
    stands — the ladder exhausts into the honest rejection."""
    from app.tools.film.storyboard import (
        FilmStoryboardRejected,
        _orchestrate_text_storyboard,
        film_text_director,
    )

    async def _direction(**kwargs):
        return FilmTextDirection.model_validate(_COMPOSITE_DIRECTION)

    monkeypatch.setattr(film_text_director, "call", _direction)
    with pytest.raises(FilmStoryboardRejected) as exc_info:
        await _orchestrate_text_storyboard(
            text_source=_src(),
            instruction=None,
            focus=None,
            language=None,
            current=None,
            on_reject=None,
            allow_fixed_fallback=False,
            voiceover=False,
        )
    assert exc_info.value.user_key == "film_text_ungrounded"
    assert CONSTRAINT_VIOLATION in exc_info.value.codes


@pytest.mark.asyncio
async def test_draft_pure_seat_keeps_the_vocabulary_closed(monkeypatch):
    """The pure draft seat (db=None — the tests' own deferral law) reads
    the gate OFF: a composite direction can never leak through it."""
    from types import SimpleNamespace
    from uuid import uuid4

    from app.tools.film.storyboard import (
        FilmStoryboardRejected,
        draft_film_storyboard,
        film_text_director,
    )

    async def _direction(**kwargs):
        return FilmTextDirection.model_validate(_COMPOSITE_DIRECTION)

    monkeypatch.setattr(film_text_director, "call", _direction)
    with pytest.raises(FilmStoryboardRejected):
        await draft_film_storyboard(
            None,
            SimpleNamespace(id=uuid4()),
            instruction="做一支组合片",
            text_source=_src(),
        )


# ---------------------------------------------------------------------------
# 复审①② (下批 A 复审): all-composite + named target 的帧级符合律, and the
# preflight's provable-only bounds (composite 密排 / 无文字媒体幕 / 一幕多
# 文字元素).
# ---------------------------------------------------------------------------


def test_all_composite_target_frame_match_passes():
    """复审① repro: one composite scene (text element at=0/until=8) with the
    user naming target_seconds=8 — a FRAME-level match MUST pass (never a
    blanket 'cannot be paced out')."""
    lines = build_text_manifest(COPY)
    direction = FilmTextDirection.model_validate(
        {
            "segments": [
                {
                    "elements": [
                        {"kind": "text", "refs": [{"line": 1}, {"line": 2}],
                         "at": 0.0, "until": 8.0},
                        {"kind": "text", "refs": [{"line": 3}, {"line": 4}],
                         "at": 1.0, "until": 7.0},
                    ]
                }
            ]
        }
    )
    board, violations = assemble_text_storyboard(
        direction, lines, source=_src(target_seconds=8.0), composite_ok=True
    )
    assert violations == []
    assert board.scenes[0].seconds == 8.0


def test_all_composite_target_mismatch_reports_the_concrete_delta():
    """复审①: a mismatched named total rejects with the CONCRETE delta
    (frames and direction) — and never demands words filler planes, never
    silently touches the user's source windows or animation."""
    lines = build_text_manifest(COPY)
    direction = FilmTextDirection.model_validate(
        {
            "segments": [
                {
                    "elements": [
                        {"kind": "video", "asset": "a1",
                         "source_start": 0.0, "source_end": 8.0},
                        {"kind": "text",
                         "refs": [{"line": 1}, {"line": 2}], "until": 7.5},
                        {"kind": "text", "refs": [{"line": 3}, {"line": 4}],
                         "until": 7.0},
                    ]
                }
            ]
        }
    )
    board, violations = assemble_text_storyboard(
        direction, lines, source=_src(target_seconds=10.0), composite_ok=True
    )
    assert board is None
    (v,) = [v for v in violations if "10" in v.detail]
    assert "8s" in v.detail  # the material-derived total
    assert "60" in v.detail  # the delta in frames (2s × 30fps)
    assert "short" in v.detail  # the direction of the gap
    assert "text planes" not in v.detail  # no words-filler demand


def test_preflight_named_count_is_not_words_packed_anymore():
    """复审② repro: one line of copy, authored mode, scene_count=2 — the
    preflight must stand aside (a media-only composite scene carries no
    copy; the candidate assembly and the real validator judge the rest)."""
    from app.tools.film.storyboard import _text_feasibility

    copy = "一句简短的文案。"
    lines = build_text_manifest(copy)
    assert (
        _text_feasibility(
            lines, source=FilmTextSource(text=copy, verbatim=False, scene_count=2)
        )
        is None
    )
    # 多媒体幕 verbatim（有可用素材）: media-only scenes pad the count.
    many = FilmTextSource(text=COPY, verbatim=True, scene_count=5)
    assert (
        _text_feasibility(
            build_text_manifest(COPY), source=many, media_available=True
        )
        is None
    )


def test_preflight_count_below_composite_densest_is_the_real_refusal():
    """复审② 保留实际技术边界 (+ 定点复审 verbatim-only): the densest
    COMPOSITE packing (6 text elements × 4 display lines = 24 per scene)
    bounds the minimum scene count IN VERBATIM MODE — the exactly-once
    coverage law turns the input's display packing into a real screen
    floor, so a named count below it is provably impossible and still
    fails BEFORE any model call. (Authored mode has no input-derived
    floor at all — see the 定点复审 tests below.)"""
    from app.tools.film.storyboard import _text_feasibility

    # 25 manifest lines = 25 display lines > 24 → at least 2 scenes.
    copy = "\n".join(f"第{i}行文案需要完整展示出来" for i in range(25))
    lines = build_text_manifest(copy)
    display_total = sum(len(_wrap_display_lines(l.text)) for l in lines)
    assert display_total > 24
    rejection = _text_feasibility(
        lines, source=FilmTextSource(text=copy, verbatim=True, scene_count=1)
    )
    assert rejection is not None
    assert rejection.user_key == "film_text_target_overflow"
    # The feasible count passes.
    assert (
        _text_feasibility(
            lines, source=FilmTextSource(text=copy, verbatim=True, scene_count=2)
        )
        is None
    )


def test_preflight_verbatim_count_over_line_count_needs_media():
    """复审② 逐字完整覆盖保留: verbatim + no usable media → every scene
    needs a cited line (exactly-once coverage), so a count over the line
    count is provably impossible; with usable media, media-only scenes
    make it legal."""
    from app.tools.film.storyboard import _text_feasibility

    lines = build_text_manifest(COPY)  # 4 clause lines
    rejection = _text_feasibility(
        lines,
        source=FilmTextSource(text=COPY, verbatim=True, scene_count=5),
        media_available=False,
    )
    assert rejection is not None
    assert rejection.user_key == "film_text_target_overflow"
    # 单幕多文字元素组合 (legal): one scene, several text elements — the
    # preflight never bounds ABOVE the densest minimum.
    assert (
        _text_feasibility(
            lines,
            source=FilmTextSource(text=COPY, verbatim=True, scene_count=1),
            media_available=False,
        )
        is None
    )


# ---------------------------------------------------------------------------
# 定点复审 (下批 A 定点收尾): 改编模式的输入 = 参考材料，不是必须全文上屏
# 的文案——输入长度 ≠ 输出篇幅。
# ---------------------------------------------------------------------------


def test_preflight_authored_reference_is_not_a_display_floor():
    """定点复审 复现: verbatim=False 的输入是参考材料（提供创作信息，不
    要求全文展示）——30 行产品介绍 + target 10s + scene_count=1（有/无
    素材）预检必须放行；输入的行数与排版容量不构成合法幕数的下界，
    最终候选由真实校验判。"""
    from app.tools.film.storyboard import _text_feasibility

    copy = "\n".join(f"产品特性第{i}条需要详细介绍清楚" for i in range(30))
    lines = build_text_manifest(copy)
    assert len(lines) > 24  # over one screen's densest packing
    for media in (True, False):
        assert (
            _text_feasibility(
                lines,
                source=FilmTextSource(
                    text=copy, verbatim=False, target_seconds=10.0, scene_count=1
                ),
                media_available=media,
            )
            is None
        )


def test_preflight_authored_long_reference_is_not_estimate_gated():
    """定点复审: 长参考材料 + 允许改编 + 未指定时长——阅读估计是对原文的，
    不是对产出的（模型可以提炼成一句标题）；同一文案逐字模式仍按真实
    拒绝（全文必须上屏）；改编模式的显式超帧帽时长仍按真实拒绝。"""
    from app.tools.film.storyboard import _text_feasibility

    long_copy = "这一段话足够长需要完整阅读才能理解，" * 120  # ≫120s reading
    lines = build_text_manifest(long_copy)
    # Verbatim: the full copy MUST show — the default-pace ceiling is real.
    rejection = _text_feasibility(
        lines, source=FilmTextSource(text=long_copy, verbatim=True)
    )
    assert rejection is not None
    assert rejection.user_key == "film_text_beyond_reach"
    # Authored: the reference condenses — no estimate-based refusal.
    assert (
        _text_feasibility(
            lines, source=FilmTextSource(text=long_copy, verbatim=False)
        )
        is None
    )
    # The REAL technical bound never relaxes: an explicit total over the
    # render frame cap still refuses in authored mode.
    rejection = _text_feasibility(
        lines,
        source=FilmTextSource(
            text=long_copy, verbatim=False, target_seconds=150.0
        ),
    )
    assert rejection is not None
    assert rejection.user_key == "film_text_target_overflow"


def test_authored_candidate_over_screen_capacity_still_rejects():
    """定点复审 不放宽最终候选: 改编模式写出的超屏文案（一段 wrap 超过
    4 显示行屏容）仍在装配面对真实屏容拒——预检放行 ≠ 校验放宽。"""
    long_line = "这一段改编文案写得实在太长了根本放不下，" * 6
    direction = FilmTextDirection(segments=[FilmTextSegment(text=[long_line])])
    board, violations = assemble_text_storyboard(
        direction, [], source=FilmTextSource(text=long_line, verbatim=False)
    )
    assert board is None
    assert any("split this segment" in v.detail for v in violations)


@pytest.mark.asyncio
async def test_orchestrate_passes_the_listing_truncation_count_through(monkeypatch):
    """复审③: the director call carries the printed listing AND the count
    of older assets it did not print (截断 ≠ 不存在 — the model never
    reads the cap as the universe)."""
    from app.tools.film.storyboard import (
        _orchestrate_text_storyboard,
        film_text_director,
    )

    seen: dict = {}

    async def _direction(**kwargs):
        seen.update(kwargs)
        return FilmTextDirection.model_validate(_COMPOSITE_DIRECTION)

    monkeypatch.setattr(film_text_director, "call", _direction)

    async def _loader(board):
        return _media()

    candidates = [
        {"id": "a1", "kind": "video", "title": "demo",
         "duration_seconds": 8.0, "width": None, "height": None,
         "usable": True, "processing": "completed"}
    ]
    board = await _orchestrate_text_storyboard(
        text_source=_src(),
        instruction=None,
        focus=None,
        language=None,
        current=None,
        on_reject=None,
        allow_fixed_fallback=False,
        voiceover=False,
        media_candidates=candidates,
        media_more=17,
        media_loader=_loader,
        composite_ok=True,
    )
    assert any(s.type == "composite" for s in board.scenes)
    assert seen["media"] == candidates
    assert seen["media_more"] == 17


@pytest.mark.asyncio
async def test_citation_beyond_the_printed_listing_still_validates(monkeypatch):
    """复审③ 截断 ≠ 不存在 (校验层): a board citing a project asset NOT in
    the printed listing (paged out / pinned elsewhere) still faces the real
    media universe — the loader resolves by id, never by list membership."""
    from app.tools.film.storyboard import (
        _orchestrate_text_storyboard,
        film_text_director,
    )

    async def _direction(**kwargs):
        return FilmTextDirection.model_validate(_COMPOSITE_DIRECTION)

    monkeypatch.setattr(film_text_director, "call", _direction)

    async def _loader(board):
        return _media()  # "a1" resolves even with an EMPTY prompt listing

    board = await _orchestrate_text_storyboard(
        text_source=_src(),
        instruction=None,
        focus=None,
        language=None,
        current=None,
        on_reject=None,
        allow_fixed_fallback=False,
        voiceover=False,
        media_candidates=[],
        media_loader=_loader,
        composite_ok=True,
    )
    assert any(s.type == "composite" for s in board.scenes)


def test_film_text_drift_next_tracks_the_last_accepted_baseline():
    """未接受文字漂移的持续性 (7276ef13 复审② — A→B→继承 B 洞): the state
    tracks the LAST PROVABLY-ACCEPTED baseline; release is exhaustively
    restore / user-pasted / (the dock confirm — no seat here); omitting
    text, re-stating the drifted copy, or an unrelated change CARRIES the
    hold."""
    from app.tools.film.storyboard import (
        _text_drift_digest,
        film_text_drift_next,
        film_text_drift_held,
    )

    a = INCIDENT_COPY
    b = a + "，模型加的一句"
    # ① First unproven drift sets the state against the accepted baseline A.
    drift = film_text_drift_next(None, a, b, user_text="只调整排版")
    assert drift == {"baseline_sha256": _text_drift_digest(a)}
    assert film_text_drift_held({"film_text_drift": drift}) is True
    # ② Inheriting B (layout-only follow-up, text omitted → new==B) CARRIES
    # the hold against A — never washes.
    carried = film_text_drift_next(drift, b, b, user_text="再调一下布局")
    assert carried == drift
    # ③ Re-stating B (the model re-pastes the drifted copy) also carries.
    assert film_text_drift_next(drift, b, b, user_text="继续") == drift
    # ④ Restore: the new pinned copy == the baseline → released.
    assert film_text_drift_next(drift, b, a, user_text="恢复原文") is None
    # ⑤ User-pasted: the standing copy appears in the user's own message →
    # released (explicit acceptance by sourcing).
    assert film_text_drift_next(drift, b, b, user_text=f"就用这版：{b}") is None
    # ⑥ No baseline lineage (first text version / non-text chain) → no hold.
    assert film_text_drift_next(None, None, a, user_text="") is None
    assert film_text_drift_next(None, a, a, user_text="") is None
    # ⑦ The held predicate accepts dicts / PendingPlan / None alike.
    assert film_text_drift_held(None) is False
    assert film_text_drift_held({}) is False
    assert film_text_drift_held({"film_text_drift": None}) is False
