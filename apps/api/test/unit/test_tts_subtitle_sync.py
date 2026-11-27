"""Layer 0 pure unit tests for broadcast timed phrase chunking and verbatim TTS-subtitle lockstep."""

from __future__ import annotations

import pytest

from app.editing.caption_timing import (
    TimedPhrase,
    chunk_timed_words,
    align_translations_to_phrases,
    build_motion_block_caption_phrases,
    format_caption_punctuation,
    split_cue_into_timed_phrases,
)


def _assert_contiguous_bounds(phrases: list[TimedPhrase], start_ms: float, end_ms: float) -> None:
    assert phrases, "Expected at least one timed phrase"
    assert phrases[0].time_begin_ms == pytest.approx(start_ms)
    assert phrases[-1].time_end_ms == pytest.approx(end_ms)
    for idx, phrase in enumerate(phrases):
        assert phrase.text.strip() == phrase.text and phrase.text
        assert phrase.time_end_ms > phrase.time_begin_ms
        if idx > 0:
            assert phrase.time_begin_ms == pytest.approx(phrases[idx - 1].time_end_ms)


def test_split_en_cue_prefers_clause_punctuation_and_preserves_verbatim():
    text = "Every valuation model breaks down, when private IP data stays locked in silos."
    phrases = split_cue_into_timed_phrases(text, 100.0, 5200.0, language="en")

    assert len(phrases) == 2
    assert phrases[0].text == "Every valuation model breaks down,"
    assert phrases[1].text == "when private IP data stays locked in silos."
    assert " ".join(p.text for p in phrases) == text
    _assert_contiguous_bounds(phrases, 100.0, 5200.0)


def test_split_en_long_unpunctuated_cue_respects_word_and_char_limits():
    text = (
        "Institutional investors demand auditable methodology across every single "
        "patent portfolio worldwide without manual spreadsheet reconciliation."
    )
    phrases = split_cue_into_timed_phrases(text, 0.0, 7400.0, language="en")

    assert len(phrases) >= 3
    assert " ".join(p.text for p in phrases) == text
    for p in phrases:
        assert len(p.text) <= 46
        assert len(p.text.split()) <= 8
        assert len(p.text.split()) >= 2  # zero 1-word orphans
    _assert_contiguous_bounds(phrases, 0.0, 7400.0)


def test_split_en_preserves_domains_decimals_and_short_cues():
    short = "Cut flagship product videos in seconds."
    phrases_short = split_cue_into_timed_phrases(short, 0.0, 2600.0, language="en")
    assert len(phrases_short) == 1
    assert phrases_short[0].text == short

    domain_text = "OxValue.AI prices 4.2 million patents in 3.0 seconds, with full boardroom audit trails."
    phrases_dom = split_cue_into_timed_phrases(domain_text, 0.0, 6000.0, language="en")
    assert len(phrases_dom) >= 2
    assert any("OxValue.AI" in p.text for p in phrases_dom)
    assert any("4.2" in p.text for p in phrases_dom)
    assert any("3.0" in p.text for p in phrases_dom)
    assert " ".join(p.text for p in phrases_dom) == domain_text
    _assert_contiguous_bounds(phrases_dom, 0.0, 6000.0)


def test_split_zh_cue_prefers_chinese_punctuation_and_avoids_orphans():
    text = "过去剪一支产品宣传片，你要在时间线上反复对齐音频和画面。"
    phrases = split_cue_into_timed_phrases(text, 200.0, 5600.0, language="zh")

    assert len(phrases) == 2
    assert phrases[0].text == "过去剪一支产品宣传片，"
    assert phrases[1].text == "你要在时间线上反复对齐音频和画面。"
    assert "".join(p.text for p in phrases) == text
    _assert_contiguous_bounds(phrases, 200.0, 5600.0)


def test_split_zh_unpunctuated_and_mixed_brand_tokens_never_break_mid_word():
    text = "Rookie Cut 把视频剪辑变成一句自然对话直接生成带配音与配乐的商业宣传片"
    phrases = split_cue_into_timed_phrases(text, 0.0, 6200.0, language="zh")

    assert len(phrases) >= 2
    assert "Rookie Cut" in phrases[0].text
    # Ensure no Latin token was split mid-word and no 1-2 char Chinese orphan exists
    for p in phrases:
        assert len(p.text) >= 4
    reconstructed = "".join(p.text for p in phrases).replace(" ", "")
    assert reconstructed == text.replace(" ", "")
    _assert_contiguous_bounds(phrases, 0.0, 6200.0)


def test_split_zh_absorbs_tiny_leading_clause_instead_of_flashing_orphan():
    text = "是的，这套引擎能够在毫秒级完成音画精准同步与多轨自动压低处理。"
    phrases = split_cue_into_timed_phrases(text, 0.0, 5800.0, language="zh")

    assert len(phrases) >= 2
    assert all(len(p.text) >= 4 for p in phrases), f"Found tiny orphan phrase: {phrases}"
    assert "".join(p.text for p in phrases) == text
    _assert_contiguous_bounds(phrases, 0.0, 5800.0)


def test_build_caption_phrases_ignores_same_language_paraphrase():
    narration = "Every valuation model breaks down, when private IP data stays locked in silos."
    cues = [
        {"text": narration, "time_begin": 0.0, "time_end": 5400.0},
    ]
    phrases, is_bilingual = build_motion_block_caption_phrases(
        narration,
        cues=cues,
        duration_ms=5400.0,
        language="en",
        caption_text="Private IP Valuations Need Data",  # same-language paraphrase -> MUST BE IGNORED!
    )

    assert is_bilingual is False
    assert len(phrases) == 2
    assert " ".join(p.text for p in phrases) == narration
    assert all("Need Data" not in p.text for p in phrases)
    _assert_contiguous_bounds(phrases, 0.0, 5400.0)


def test_build_caption_phrases_bilingual_1_to_1_caption_translations_lockstep():
    narration = "过去剪一支产品宣传片，你要在时间线上反复对齐音频和画面。"
    cues = [
        {"text": narration, "time_begin": 0.0, "time_end": 5400.0},
    ]
    translations = [
        "Editing a product film used to take hours,",
        "aligning audio and frames on a timeline.",
    ]
    phrases, is_bilingual = build_motion_block_caption_phrases(
        narration,
        cues=cues,
        duration_ms=5400.0,
        language="zh",
        caption_translations=translations,
    )

    assert is_bilingual is True
    assert len(phrases) == 2
    assert phrases[0].text == "过去剪一支产品宣传片，\nEditing a product film used to take hours,"
    assert phrases[1].text == "你要在时间线上反复对齐音频和画面。\naligning audio and frames on a timeline."
    primary_concat = "".join(p.text.split("\n", 1)[0] for p in phrases)
    assert primary_concat == narration
    _assert_contiguous_bounds(phrases, 0.0, 5400.0)


def test_build_caption_phrases_bilingual_caption_text_never_replaces_line1_verbatim():
    narration = "过去剪一支产品宣传片，你要在时间线上反复对齐音频和画面。"
    cues = [
        {"text": narration, "time_begin": 0.0, "time_end": 5200.0},
    ]
    # Caller passed paraphrased Chinese on Line 1 + English on Line 2 in legacy caption_text
    phrases, is_bilingual = build_motion_block_caption_phrases(
        narration,
        cues=cues,
        duration_ms=5200.0,
        language="zh",
        caption_text="剪片告别繁琐时间线\nSay goodbye to tedious timelines, cut films by chat.",
    )

    assert is_bilingual is True
    assert len(phrases) == 2
    # Line 1 MUST come 100% verbatim from MiniMax cues, NOT the paraphrased Chinese!
    assert "".join(p.text.split("\n", 1)[0] for p in phrases) == narration
    assert all("告别繁琐" not in p.text for p in phrases)
    assert phrases[0].text.split("\n", 1)[1] == "Say goodbye to tedious timelines,"
    assert phrases[1].text.split("\n", 1)[1] == "cut films by chat."


def test_build_caption_phrases_foreign_single_line_caption_text_becomes_line2():
    narration = "一句对话，从零生成带配音与配乐的商业宣传片。"
    cues = [{"text": narration, "time_begin": 0.0, "time_end": 4600.0}]
    phrases, is_bilingual = build_motion_block_caption_phrases(
        narration,
        cues=cues,
        duration_ms=4600.0,
        language="zh",
        caption_text="One prompt, generating a voiced commercial from scratch.",
    )

    assert is_bilingual is True
    assert len(phrases) == 2
    assert "".join(p.text.split("\n", 1)[0] for p in phrases) == narration
    assert all("\n" in p.text for p in phrases)


def test_align_translations_handles_count_mismatch_gracefully():
    primaries = [
        TimedPhrase("过去剪一支产品宣传片，", 0.0, 1800.0),
        TimedPhrase("你要在时间线上反复对齐，", 1800.0, 3600.0),
        TimedPhrase("还要自己配音加字幕。", 3600.0, 5400.0),
    ]
    # 1 single translation string split into 3 segments
    aligned_from_one = align_translations_to_phrases(
        ["Editing a film meant timeline grinding, manual audio alignment, and hand-typed captions."],
        primaries,
    )
    assert len(aligned_from_one) == 3
    assert all(seg.strip() for seg in aligned_from_one)
    assert " ".join(aligned_from_one) == (
        "Editing a film meant timeline grinding, manual audio alignment, and hand-typed captions."
    )

    # 4 translations merged down to 3
    aligned_from_four = align_translations_to_phrases(
        ["Editing a film", "meant timeline grinding,", "manual alignment,", "and hand-typed captions."],
        primaries,
    )
    assert len(aligned_from_four) == 3
    assert all(seg.strip() for seg in aligned_from_four)


@pytest.mark.parametrize(("language", "tokens"), [
    ("en", "Each measured word stays exactly where the speaker said it, even after the caption breaks.".split()),
    ("zh", ["现在", "我们", "一起", "来看看，", "真实", "词轴", "怎样", "让每个", "字幕", "短句", "精确", "贴合", "原声。"]),
])
def test_measured_phrases_keep_word_boundaries_and_silent_gaps(language, tokens):
    words = [{"text": token, "start_s": i * 0.375, "end_s": i * 0.375 + 0.125} for i, token in enumerate(tokens)]
    phrases = chunk_timed_words(words, language)
    assert len(phrases) > 1
    cursor = 0
    for phrase in phrases:
        count = len(phrase.word_timings)
        group = words[cursor:cursor + count]
        cursor += count
        start = group[0]["start_s"]
        assert phrase.time_begin_ms == start * 1000
        assert phrase.time_end_ms == group[-1]["end_s"] * 1000
        assert phrase.word_timings == tuple((w["start_s"] - start, w["end_s"] - start) for w in group)
        assert phrase.text == (" " if language == "en" else "").join(w["text"] for w in group)
        if language == "en":
            assert 2 <= count <= 8 and len(phrase.text) <= 46
        else:
            assert 4 <= len(phrase.text) <= 19
    assert cursor == len(words)


@pytest.mark.parametrize("with_words", [True, False])
def test_upload_captions_use_safe_layout_and_selected_source_clock(with_words):
    from app.editing.revisions import text_safe_layout
    from app.editing.schemas import TimeRange
    from app.editing.source_captions import source_caption_ops
    from app.editing.source_selection import source_sentences
    from test.support.composition_fixtures import AUDIO_DIGEST, AUDIO_SNAPSHOT, valid_content

    tokens = "Studio editors follow the exact spoken words, while the captions stay inside their safe area.".split()
    words = [{"word": " " + token, "start": 1 + i / 5, "end": 1.1 + i / 5} for i, token in enumerate(tokens)]
    sentences = source_sentences(words, duration_ticks=450000)
    if not with_words:
        sentences = tuple(s.model_copy(update={"words": []}) for s in sentences)
    content = valid_content()
    ops = source_caption_ops(
        content, scene_id="scn_open", snapshot_id=AUDIO_SNAPSHOT, snapshot_digest=AUDIO_DIGEST,
        source_range=TimeRange(start=90000, end=450000), sentences=sentences,
    )
    clips = [op.clip for op in ops if op.op == "add_clip"]
    assert len(clips) > 1
    assert " ".join(c.object.text for c in clips) == " ".join(tokens)
    for clip in clips:
        assert 2 <= len(clip.object.text.split()) <= 8 and len(clip.object.text) <= 46
        assert clip.object.layout == text_safe_layout(1920, 1080, "bottom", role="caption")
        assert clip.range.start == clip.object.caption.source_range.start - 90000
        assert clip.range.end == clip.object.caption.source_range.end - 90000
        if with_words:
            assert clip.object.caption.source_range.start in {round(w["start"] * 90000) for w in words}
            assert clip.object.caption.source_range.end in {round(w["end"] * 90000) for w in words}


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["speech", "asr"])
async def test_insert_captions_slice_the_bound_word_axis_and_keep_local_offsets(source):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from uuid import uuid4

    from app.chat.editor import _resolve_aligned_caption_cues
    from app.editing.schemas import AudioObject, Clip, CompositionContent, SpeechObject, TimeRange
    from app.tools.video.narration_alignment import align_narration

    tokens = "one two three four five six seven eight nine ten eleven twelve".split()
    words = [{"word": " " + token, "start": i + 0.125, "end": i + 0.625} for i, token in enumerate(tokens)]
    script = " ".join(tokens)
    source_id, alignment_id = uuid4(), uuid4()
    db = AsyncMock()
    if source == "speech":
        obj = SpeechObject(kind="speech", object_id="obj_speech", text=script, provider=None, model=None, alignment={
            "alignment_id": alignment_id, "content_digest": "b" * 64,
            "audio_snapshot_id": source_id, "audio_digest": "a" * 64,
        })
        payload = align_narration(text=script, asr={"words": words}, duration_ticks=1080000)
        db.scalar.return_value = SimpleNamespace(
            id=alignment_id, algorithm="faster-whisper-script-v1", content_digest="b" * 64,
            payload=payload.model_dump(mode="json"),
        )
    else:
        obj = AudioObject(kind="audio", object_id="obj_audio")
        db.scalars.return_value = []
        db.scalar.return_value = SimpleNamespace(meta={"words": words}, duration_ticks=1080000)
    clip = Clip(clip_id="clp_vo", range=TimeRange(start=2000, end=13000), source={
        "snapshot_id": source_id, "snapshot_digest": "a" * 64, "source_range": {"start": 90000, "end": 1080000},
    }, object=obj)
    content = CompositionContent(settings={"width": 1280, "height": 720, "timebase": 1000})
    cues = await _resolve_aligned_caption_cues(db, SimpleNamespace(user_id=uuid4()), content, clip)
    assert len(cues) >= 2
    assert " ".join(c["text"] for c in cues) == " ".join(tokens[1:])
    for cue in cues:
        caption = cue["caption"]
        if source == "speech":
            assert script[caption.text_start:caption.text_end] == cue["text"]
            assert caption.narration_alignment_id == alignment_id
        else:
            assert caption.alignment == "faster-whisper-source-v1"
            assert cue["output_start"] == 2000 + (caption.source_range.start - 90000) // 90
        timings = cue["word_timings"]
        assert timings[0]["start_s"] == 0
        assert [cue["text"][w["text_start"]:w["text_end"]] for w in timings] == cue["text"].split()
        assert [w["start_s"] for w in timings] == list(range(len(timings)))
        assert [w["end_s"] for w in timings] == [i + 0.5 for i in range(len(timings))]


def test_format_caption_punctuation_zh_and_en_broadcast_rules():
    # Chinese: omit 。，、；： (internal -> single space, trailing stripped), keep ？！《》“”……——·
    assert (
        format_caption_punctuation("过去剪一支产品宣传片，你要在时间线上反复对齐音频和画面。")
        == "过去剪一支产品宣传片 你要在时间线上反复对齐音频和画面"
    )
    assert format_caption_punctuation("透明、高效、可验证。") == "透明 高效 可验证"
    assert (
        format_caption_punctuation("真的能做到吗？《估值报告》说：可以！")
        == "真的能做到吗？《估值报告》说 可以！"
    )
    assert (
        format_caption_punctuation("迈克尔·波特——“核心竞争力”……")
        == "迈克尔·波特——“核心竞争力”……"
    )
    assert format_caption_punctuation("每天 10:30 准时更新。") == "每天 10:30 准时更新"

    # English: strip trailing . , ; : while keeping ? ! ... decimals, domains, abbreviations
    assert format_caption_punctuation("confidence and reviews.") == "confidence and reviews"
    assert format_caption_punctuation("built to withstand scrutiny.") == "built to withstand scrutiny"
    assert format_caption_punctuation("£18.7m on OxValue.AI.") == "£18.7m on OxValue.AI"
    assert format_caption_punctuation("Wait... is it live?") == "Wait... is it live?"
    assert format_caption_punctuation("Built for U.S.") == "Built for U.S."
    assert format_caption_punctuation("Ready now!") == "Ready now!"

    # Bilingual multi-line: formats each line by its own language convention
    assert (
        format_caption_punctuation("confidence and reviews.\n信心、背书与复核。")
        == "confidence and reviews\n信心 背书与复核"
    )
