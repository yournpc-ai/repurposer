"""Discover, tune and align a synthesized effect through the Studio chat stream."""

import asyncio
import json
import os
from pathlib import Path
import socket

import httpx
import pytest
from sqlalchemy import select

from app.catalog.sync import sync_builtin_catalog
from app.chat.intent import intent_router
from app.config import settings
from app.editing.store import content_of
from app.models.tables import CompositionVersion, SourceSnapshot, User
from scripts.eval_chat_e2e import parse_sse_frames
from test.support.chat_http import tool
from test.support.db_helpers import ScriptedToolClient, _project, _user, bind_test_database, full_api_client

pytestmark = [pytest.mark.chat_origin, pytest.mark.asyncio]


@pytest.fixture
async def sound_renderer(monkeypatch):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    process = await asyncio.create_subprocess_exec(
        "node", "--import", "tsx", "src/server.ts",
        cwd=Path(__file__).resolve().parents[3] / "render",
        env={**os.environ, "RENDER_PORT": str(port)},
    )
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            async with asyncio.timeout(30):
                while process.returncode is None:
                    try:
                        (await client.get(base + "/health")).raise_for_status()
                        break
                    except httpx.ConnectError:
                        await asyncio.sleep(0.1)
                else:
                    pytest.fail("Render exited before accepting requests")
        monkeypatch.setattr(settings, "render_url", base + "/render")
        yield
    finally:
        if process.returncode is None:
            process.terminate()
        await process.wait()


async def test_peak_placement_through_chat(database, monkeypatch, tmp_path, sound_renderer):
    bind_test_database(monkeypatch, database)
    monkeypatch.setattr(settings, "s3_endpoint_url", f"local://{tmp_path}")
    owner = await _user(database)
    project = await _project(database, owner)
    async with database.begin() as db:
        user = await db.get(User, owner)
        await sync_builtin_catalog(db)
    llm = ScriptedToolClient([
        tool("create_video", {"name": "Shutter cut", "motion_blocks": [
            {"block_id": "code_terminal", "duration_seconds": 3, "props": {"lines": ["$ build"]}}]}),
        tool("answer", {}, "Draft ready."),
        tool("search_sfx_library", {"domain": "video", "category": "transitions"}),
        tool("get_sfx", {"ids": ["dsp_trans_vinyl_pull"]}),
        tool("generate_sfx", {"sfx_id": "dsp_trans_vinyl_pull", "target_duration_ms": 704,
                              "tune": {"tone_pct": -17, "pitch_st": 2.5}, "align_peak_at_seconds": 1.375}),
        tool("answer", {}, "Placed the effect."),
    ], streaming=True)
    monkeypatch.setattr(intent_router, "client", llm)
    monkeypatch.setattr("app.providers.llm.get_llm_client", lambda: llm)
    async with full_api_client(database, user) as client:
        for message in ["Create a three-second terminal film without narration.",
                        "Find a vinyl transition and align its peak to the cut at 1.375 seconds."]:
            response = await client.post("/api/v1/chat", json={"project_id": str(project), "message": message},
                                         headers={"Accept": "text/event-stream"})
            assert response.status_code == 200
            frames = parse_sse_frames(response.text)
            assert frames and all(event != "error" for event, _ in frames)
    outlines = []
    for iteration in llm.calls:
        last = iteration["messages"][-1]
        if last.get("role") == "tool" and last["content"].startswith("{"):
            payload = json.loads(last["content"])
            if "items" in payload:
                outlines.append(payload["items"])
    search, details = outlines
    assert len(search) == 4 and all(row["domain"] == "video" and row["category"] == "transitions" for row in search)
    assert len(details[0]["tune_schema"]) == 7
    async with database() as db:
        version = (await db.scalars(select(CompositionVersion).order_by(CompositionVersion.version.desc()))).first()
        content = content_of(version)
        effect = next(t for t in content.timeline.tracks if t.role == "effect").clips[0]
        snapshot = await db.get(SourceSnapshot, effect.source.snapshot_id)
        origin = snapshot.meta["origin"]
        metrics = origin["acoustics"]
        assert origin["tune"]["tone_pct"] == -17 and origin["tune"]["pitch_st"] == 2.5
        assert metrics["duration_ms"] == 704 and 150 < metrics["peak_offset_ms"] < 550
        rate = content.settings.timebase
        assert effect.range.start == round((1375 - metrics["peak_offset_ms"]) * rate / 1000)
        assert effect.range.end - effect.range.start == round(704 * rate / 1000)
