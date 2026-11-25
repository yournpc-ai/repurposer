"""Chat turn settlement and imports — unit contracts."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_no_progress_without_saved_version_does_not_claim_saved_history():
    from app.chat.service import _design_no_progress_text

    english = _design_no_progress_text("Make a promo", version_saved=False)
    chinese = _design_no_progress_text("制作宣传片", version_saved=False)
    assert "Previously saved" not in english
    assert "did not save a new storyboard" in english
    assert "此前保存" not in chinese
    assert "没有保存新的分镜" in chinese
    exported = _design_no_progress_text("导出", version_saved=False, exported=True)
    assert "MP4 已导出" in exported and "未完成交付" in exported


CANDIDATE_SET_ID = UUID("11111111-1111-1111-1111-111111111111")


async def test_search_sfx_seat_uses_classified_user_intent(monkeypatch):
    from types import SimpleNamespace

    from app.chat.sfx_intent import SfxIntentDecision, sfx_intent_agent
    from app.chat.video_turn_seats import search_sfx_seat
    from app.models.schemas import SearchSfxArgs

    decision = SfxIntentDecision(action="add", evidence="使用真实 CC0 音效")

    async def classify(**kwargs):
        assert kwargs["user_text"] == "使用真实 CC0 音效"
        return decision

    calls = []

    async def provider(query):
        calls.append(query)
        return {"candidate_set_id": str(CANDIDATE_SET_ID), "topic": query, "members": []}

    emitted = []

    async def on_candidates(payload):
        emitted.append(payload)

    monkeypatch.setattr(sfx_intent_agent, "call", classify)
    monkeypatch.setattr("app.tools.video.sfx.search_sfx_candidates", provider)
    project = SimpleNamespace(user_id=uuid4())
    result = await search_sfx_seat(
        project=project,
        args=SearchSfxArgs(query="soft click"),
        user_text="使用真实 CC0 音效",
        on_candidates=on_candidates,
    )
    assert result.ok and calls == ["soft click"] and len(emitted) == 1
    assert '"action": "add"' in result.text
    assert "使用真实 CC0 音效" in result.text

    decision.action = "deny"
    rejected = await search_sfx_seat(
        project=project,
        args=SearchSfxArgs(query="another click"),
        user_text="使用真实 CC0 音效",
        on_candidates=on_candidates,
    )
    assert not rejected.ok and calls == ["soft click"] and len(emitted) == 1
    assert '"action": "deny"' in rejected.text


async def test_freesound_download_bypasses_ambient_proxy(monkeypatch):
    from app.providers import freesound

    captured = {}

    class Response:
        status_code = 200
        headers = {"content-type": "application/json"}

        async def aiter_bytes(self):
            yield b"{}"

    class Stream:
        async def __aenter__(self):
            return Response()

        async def __aexit__(self, *args):
            return None

    class Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def stream(self, *args, **kwargs):
            return Stream()

    monkeypatch.setattr(freesound.httpx, "AsyncClient", Client)
    data, content_type = await freesound._download(
        "https://freesound.org/apiv2/search/text/", max_bytes=16,
    )
    assert data == b"{}" and content_type == "application/json"
    assert captured["trust_env"] is False
