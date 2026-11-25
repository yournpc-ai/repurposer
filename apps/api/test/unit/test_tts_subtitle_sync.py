"""Layer 0 pure unit tests for broadcast timed phrase chunking and verbatim TTS-subtitle lockstep."""

from __future__ import annotations

import pytest

from app.editing.caption_timing import (
    TimedPhrase,
    align_translations_to_phrases,
    build_motion_block_caption_phrases,
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
        assert len(p.text) <= 50
        assert len(p.text.split()) <= 8
        assert len(p.text.split()) >= 2  # zero 1-word orphans
    _assert_contiguous_bounds(phrases, 0.0, 7400.0)


def test_split_en_preserves_domains_decimals_and_short_cues():
    short = "Cut flagship product videos in seconds by chatting."
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
