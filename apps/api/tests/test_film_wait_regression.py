"""Regression: long citations, live-but-endless generation, and failed docks."""
import asyncio
from types import SimpleNamespace

import pytest

from app.providers.llm.base import LLMError
from app.tools.film import storyboard as module
from test_film_storyboard_pure import _film_page, _direction, _assemble_with


def test_divider_fits_shared_full_citation_without_regeneration():
    pages = [_film_page(h2=["Every night out becomes a new way to connect."])]
    resolved, violations = _assemble_with(pages)
    assert not violations
    assert resolved is not None
    rolls = [s.roll for s in resolved.scenes if s.type == "divider"]
    assert rolls and all(len(text) <= 30 for roll in rolls for text in roll)
    assert any("Every night out becomes" in text for roll in rolls for text in roll)
    assert not [v for v in module.validate_storyboard(resolved, pages) if ".roll" in v.detail]


@pytest.mark.asyncio
async def test_live_but_endless_generation_is_cancelled(monkeypatch):
    cancelled = False
    async def endless(**kwargs):
        nonlocal cancelled
        try:
            while True:
                await asyncio.sleep(0.001)
        finally:
            cancelled = True
    monkeypatch.setattr(module, "_DIRECTION_BUDGET_S", 0.02)
    monkeypatch.setattr(module.film_director, "call", endless)
    monkeypatch.setattr(module, "fixed_direction", lambda *a, **kw: None)
    with pytest.raises(LLMError) as error:
        await module.orchestrate_storyboard(pages=[_film_page()], instruction="intro", focus=None, page_images=[])
    assert error.value.user_key == "film_storyboard_timeout"
    assert cancelled


@pytest.mark.asyncio
async def test_rejection_reports_progress_within_same_budget(monkeypatch):
    calls, reports = [], []
    async def candidate(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return _direction(cold_open=["x" * 500])
        await asyncio.sleep(10)
    async def rejected(attempt, violations, feedback):
        reports.append((attempt, feedback))
    monkeypatch.setattr(module, "_DIRECTION_BUDGET_S", 0.03)
    monkeypatch.setattr(module.film_director, "call", candidate)
    monkeypatch.setattr(module, "fixed_direction", lambda *a, **kw: None)
    with pytest.raises(LLMError):
        await module.orchestrate_storyboard(pages=[_film_page()], instruction="intro", focus=None, page_images=[], on_reject=rejected)
    assert len(calls) == 2 and len(reports) == 1
    assert calls[1]["repair_feedback"] == reports[0][1]


async def no_music(*args):
    return None, None, None


@pytest.mark.asyncio
async def test_failed_draft_cannot_dock_without_storyboard(monkeypatch):
    async def no_board(*args, **kwargs):
        return None
    monkeypatch.setattr(module, "_dock_music_context", no_music)
    monkeypatch.setattr(module, "draft_film_storyboard", no_board)
    with pytest.raises(LLMError) as error:
        await module.prepare_dock_storyboard(None, SimpleNamespace(id="project"), tasks=[{"tool":"launch_film"}], instruction="intro")
    assert error.value.user_key == "film_storyboard_ungrounded"


@pytest.mark.asyncio
async def test_missing_views_keep_their_user_key(monkeypatch):
    async def settled(_project_id):
        return None
    async def pages(_db, _project):
        return [_film_page()]
    async def images(_pages):
        return []
    async def insufficient_views(**_kwargs):
        raise module.FilmStoryboardRejected(
            ["INSUFFICIENT_VIEWS"],
            "only 0 captured page views (need 4)",
            user_key="film_views_missing",
        )
    monkeypatch.setattr(module, "_await_captures_settled", settled)
    monkeypatch.setattr(module, "load_storyboard_pages", pages)
    monkeypatch.setattr(module, "page_media_inputs", images)
    monkeypatch.setattr(module, "orchestrate_storyboard", insufficient_views)
    with pytest.raises(module.FilmStoryboardRejected) as error:
        await module.draft_film_storyboard(
            None, SimpleNamespace(id="project"), instruction="intro"
        )
    assert error.value.user_key == "film_views_missing"


@pytest.mark.asyncio
async def test_dock_budget_covers_capture_and_forwards_progress(monkeypatch):
    phases = []
    async def phase(value):
        phases.append(value)
    async def wait_for_capture(*args, on_progress=None, **kwargs):
        await on_progress("capturing")
        await asyncio.sleep(10)
    monkeypatch.setattr(module, "_dock_music_context", no_music)
    monkeypatch.setattr(module, "draft_film_storyboard", wait_for_capture)
    monkeypatch.setattr(module, "_DOCK_DRAFT_BUDGET_S", 0.01)
    with pytest.raises(LLMError) as error:
        await module.prepare_dock_storyboard(None, SimpleNamespace(id="project"), tasks=[{"tool":"launch_film"}], instruction="intro", on_progress=phase)
    assert error.value.user_key == "film_storyboard_timeout"
    assert phases == ["capturing"]


@pytest.mark.asyncio
async def test_stream_done_does_not_wait_for_connection_close_and_honors_timeout(monkeypatch):
    from contextlib import asynccontextmanager
    import httpx
    from pydantic import BaseModel
    from app.providers.llm import minimax

    class Result(BaseModel):
        ok: bool
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"choices":[{"delta":{"content":"{\\"ok\\":true}"}}]}\n\n'
            yield b'data: [DONE]\n\n'
            await asyncio.sleep(10)  # provider leaves the HTTP connection open
    async def handle(request):
        assert request.extensions["timeout"]["read"] == 7
        return httpx.Response(200, stream=Stream())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        @asynccontextmanager
        async def pool():
            yield client
        monkeypatch.setattr(minimax, "_pooled_client", pool)
        async with asyncio.timeout(0.5):
            result = await minimax.MiniMaxClient(api_key="test",base_url="https://test.invalid").generate_stream(
                messages=[], response_model=Result, timeout_s=7)
    assert result.ok
