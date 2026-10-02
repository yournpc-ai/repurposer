"""Pure tests for the caption-mode funnel (ADR-099 §8 default absorption) —
``app.chat.service._derive_chat_caption_mode``.

No DB, no LLM, no HTTP (suite discipline): the funnel's only world read is
the asset list behind ``project_source_language`` — stubbed at its import
seat; everything else is in-memory values. What is gated HERE:

- a chain without a caption-bearing task derives nothing (registry-native
  DerivativeWriterNode check, no parallel tool list);
- priority order: the user's own words (literal bilingual keyword) > the
  previous dock's value > the source_only default;
- the default is stamped ONLY when the choice is real (a distinct second
  language exists) — with no distinct alt language nothing is stamped,
  because there is no choice to show and the run narrows bilingual →
  source_only on its own at dispatch.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.pipeline.derivative_dispatch as dispatch
from app.chat.service import _derive_chat_caption_mode
from app.models.schemas import TaskItem

_QUOTES = TaskItem(tool="write_quotes", params={"language": "de"})
_POST = TaskItem(tool="write_post", params={"language": "en"})


def _project(language: str = "en", caption_mode: str | None = None):
    return SimpleNamespace(
        id=uuid4(),
        language=language,
        pending_brief=(
            {"intent": {"caption_mode": caption_mode}} if caption_mode else None
        ),
    )


@pytest.fixture
def no_assets(monkeypatch):
    """The world read behind the funnel: no assets → the source language
    falls back to the project's own language."""

    async def _list_assets(db, project_id):
        return []

    monkeypatch.setattr(dispatch, "list_assets", _list_assets)


class TestChainGuard:
    @pytest.mark.asyncio
    async def test_no_caption_task_derives_nothing(self):
        mode = await _derive_chat_caption_mode(None, _project(), [_POST], "双语")
        assert mode is None

    @pytest.mark.asyncio
    async def test_stashed_value_ignored_without_caption_task(self):
        mode = await _derive_chat_caption_mode(
            None, _project(caption_mode="bilingual"), [_POST], "make a post"
        )
        assert mode is None


class TestUserWordsWin:
    @pytest.mark.asyncio
    async def test_bilingual_keyword(self):
        mode = await _derive_chat_caption_mode(
            None, _project(), [_QUOTES], "make it bilingual"
        )
        assert mode == "bilingual"

    @pytest.mark.asyncio
    async def test_chinese_bilingual_keyword(self):
        mode = await _derive_chat_caption_mode(
            None, _project(), [_QUOTES], "金句卡要双语字幕"
        )
        assert mode == "bilingual"

    @pytest.mark.asyncio
    async def test_keyword_beats_stash(self):
        mode = await _derive_chat_caption_mode(
            None,
            _project(caption_mode="source_only"),
            [_QUOTES],
            "actually, bilingual please",
        )
        assert mode == "bilingual"


class TestStashInherits:
    @pytest.mark.asyncio
    async def test_stash_wins_over_default(self, no_assets):
        # de task vs en project → the choice would be real, but the docked
        # value still beats the default.
        mode = await _derive_chat_caption_mode(
            None, _project(caption_mode="target_only"), [_QUOTES], "改成 5 张"
        )
        assert mode == "target_only"


class TestDefaultAbsorption:
    @pytest.mark.asyncio
    async def test_distinct_alt_stamps_source_only(self, no_assets):
        # de task language vs en source/project → a real choice exists, the
        # funnel stamps the visible default.
        mode = await _derive_chat_caption_mode(
            None, _project(language="en"), [_QUOTES], "make quote cards"
        )
        assert mode == "source_only"

    @pytest.mark.asyncio
    async def test_no_distinct_alt_stamps_nothing(self, no_assets):
        # en task vs en source/project → bilingual would print one language
        # twice: no choice to show, nothing stamped.
        mode = await _derive_chat_caption_mode(
            None,
            _project(language="en"),
            [TaskItem(tool="write_quotes", params={"language": "en"})],
            "make quote cards",
        )
        assert mode is None
