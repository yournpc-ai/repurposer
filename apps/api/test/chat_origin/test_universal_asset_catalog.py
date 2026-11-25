"""Exercise discovery and permanent recording placement through the public chat stream."""

import json
import wave
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from sqlalchemy import select

from app.catalog.sfx_ingest import Recording, ingest_recording
from app.catalog.sync import sync_builtin_catalog
from app.chat.intent import intent_router
from app.config import settings
from app.editing.store import content_of, snapshot_facts
from app.editing.video_spec import compile_video_spec
from app.models.tables import CompositionVersion, User
from app.providers.llm.base import ToolCall, ToolGeneration
from scripts.eval_chat_e2e import parse_sse_frames
from test.support.db_helpers import (
    ScriptedToolClient,
    _project,
    _user,
    bind_test_database,
    full_api_client,
)

pytestmark = [pytest.mark.chat_origin, pytest.mark.asyncio]


def call(tool, **args):
    return ToolGeneration(
        content="Done" if tool == "answer" else "",
        tool_calls=[ToolCall(id=str(uuid4()), name=tool, arguments=args)],
    )


async def post(client, project, message):
    response = await client.post(
        "/api/v1/chat",
        json={"project_id": str(project), "message": message},
        headers={"Accept": "text/event-stream"},
    )
    assert response.status_code == 200
    frames = parse_sse_frames(response.text)
    assert frames and not any(kind == "error" for kind, _ in frames)


async def test_catalog_discovery_and_sample_placement(database, monkeypatch, tmp_path):
    bind_test_database(monkeypatch, database)
    monkeypatch.setattr(
        settings, "s3_endpoint_url", (tmp_path / "objects").as_uri().replace("file:", "local:")
    )
    owner_id = await _user(database)
    project = await _project(database, owner_id)
    # A short calibrated tone burst has a known duration and a late energy peak.
    pcm = np.zeros(48000, dtype="<i2")
    pcm[28800:33600] = (
        15000 * np.sin(2 * np.pi * 1000 * np.arange(4800) / 48000) * np.hanning(4800)
    ).astype("<i2")
    with wave.open(str(tmp_path / "click.wav"), "wb") as audio:
        audio.setparams((1, 2, 48000, 0, "NONE", ""))
        audio.writeframes(pcm.tobytes())
    recording = Recording(
        file="click.wav",
        slug="measured_click",
        name="Measured click",
        category="tactile_ui",
        moods=["crisp"],
        energy="medium",
        summary="Short tone burst",
        use_for=["Tap"],
        avoid=["Ambience"],
        license="CC0",
    )
    async with database.begin() as db:
        owner = await db.get(User, owner_id)
        await sync_builtin_catalog(db)
        row = await ingest_recording(db, recording, tmp_path)
        assert row.duration_ms == 1000 and 635 < row.peak_offset_ms < 665
        assert -40 < row.lufs < -10
        assert (await ingest_recording(db, recording, tmp_path)).id == row.id
        pack = Path(__file__).resolve().parents[2] / "assets/sfx"
        switch = Recording.model_validate(json.loads((pack / "manifest.json").read_bytes())[0])
        real_sample = await ingest_recording(db, switch, pack)
        digest = "43bfa8dde4a8553802b826518aff7246f510037e563009166b93584be626dba2"
        assert real_sample.content_sha256 == digest
        assert (real_sample.duration_ms, real_sample.peak_offset_ms) == (385, 17)
        assert real_sample.lufs == pytest.approx(-20.849, abs=0.01)
    llm = ScriptedToolClient(
        [
            call("search_blocks", category="code_terminal"),
            call("get_blocks", ids=["code_terminal", "logo_wall"]),
            call("search_text_presets", query="neon"),
            call("get_text_presets", ids=["neon_pulse", "chrome_cinema"]),
            call("search_sfx_library", query="foley_switch"),
            call("get_sfx", ids=["foley_switch", "dsp_select_tick"]),
            call(
                "create_video",
                name="Console",
                motion_blocks=[
                    {
                        "block_id": "code_terminal",
                        "duration_seconds": 3,
                        "props": {"lines": ["$ studio build", "+ Ready"]},
                    }
                ],
            ),
            call("answer"),
            call("insert_audio", sfx_slug="foley_switch", start_seconds=0.5, gain_db=-10),
            call("answer"),
        ],
        streaming=True,
    )
    monkeypatch.setattr(intent_router, "client", llm)
    monkeypatch.setattr("app.providers.llm.get_llm_client", lambda: llm)
    async with full_api_client(database, owner) as client:
        await post(client, project, "查常驻动效、字效、音效目录，制作一个三秒终端演示，无旁白。")
        await post(client, project, "将刚才的 foley_switch 音效在 0.5 秒加入时间线。")
    payloads = []
    for iteration in llm.calls:
        messages = iteration["messages"]
        if messages[-1].get("role") == "tool":
            body = messages[-1]["content"]
            if isinstance(body, str) and body.startswith("{"):
                value = json.loads(body)
                if "items" in value:
                    payloads.append(value["items"])
    assert [len(rows) for rows in payloads[:6]] == [1, 2, 1, 2, 1, 2]
    for rows in payloads[:6:2]:
        assert not (
            {"props_schema", "example_props", "preview_spec", "params_schema"} & rows[0].keys()
        )
    assert payloads[1][1]["id"] == "logo_wall" and payloads[1][1]["props_schema"]
    assert payloads[3][0]["example_props"]["color"] == "#B9FFF8"
    assert payloads[5][0]["storage_ready"] and payloads[5][1]["params_schema"]
    async with database() as db:
        version = (
            await db.scalars(select(CompositionVersion).order_by(CompositionVersion.version.desc()))
        ).first()
        content = content_of(version)
        facts = await snapshot_facts(db, {s.snapshot_id for s in content.sources})
        spec = compile_video_spec(
            content,
            facts,
            composition_id=version.composition_id,
            version_id=version.id,
            content_digest=version.content_digest,
        )
        audio = next(t for t in spec["tracks"] if t["role"] == "effect")["clips"][0]
        assert audio["source"]["digest"] == digest and audio["source"]["url"].endswith(
            "sfx/foley_switch.wav"
        )
        assert audio["start_frame"] == 15 and audio["end_frame"] == 27
        assert "Short tone burst" not in json.dumps(spec)
