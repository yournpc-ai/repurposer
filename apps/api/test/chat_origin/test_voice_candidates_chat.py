"""Layer 1A Chat-Origin integration tests for voice/music candidates and verbatim TTS-subtitle sync."""

from __future__ import annotations

import io
import json
import math
import struct
import wave
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

pytestmark = pytest.mark.chat_origin
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.chat.intent import intent_router
from app.config import settings
from app.dependencies import get_current_user, get_current_user_required, get_db
from app.editing.store import content_of
from app.main import app
from app.models import database as database_module
from app.models.tables import Composition, CompositionVersion, Conversation, Message, Project, User, Voice
from app.pipeline.music import GeneratedMusic, create_music_from_generation
from app.pipeline.voices import voice_reference_key
from app.providers import storage
from app.providers import voice as voice_provider
from app.providers.llm.base import ToolCall, ToolGeneration
from app.providers.voice import T2AResult
from app.tools.video.voice_candidates import VoiceCandidateError, select_voice_candidate


def _wav_bytes(duration_s: float = 1.6, sample_rate: int = 16000, freq: float = 330.0) -> bytes:
    n_samples = int(duration_s * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n_samples):
            val = int(32767 * 0.2 * math.sin(2.0 * math.pi * freq * i / sample_rate))
            frames.extend(struct.pack("<h", val))
        wf.writeframes(bytes(frames))
    return buf.getvalue()


def _parse_sse_events(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    event_name = None
    data_lines: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.strip("\r")
        if line.startswith("event:"):
            event_name = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:") :].strip())
        elif line == "":
            if event_name and data_lines:
                try:
                    payload = json.loads("\n".join(data_lines))
                except json.JSONDecodeError:
                    payload = {"raw": "\n".join(data_lines)}
                events.append((event_name, payload))
            event_name = None
            data_lines = []
    if event_name and data_lines:
        try:
            payload = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            payload = {"raw": "\n".join(data_lines)}
        events.append((event_name, payload))
    return events


async def _make_user_and_project(database, name: str = "tester") -> tuple[User, Project]:
    async with database() as db:
        user = User(email=f"{name}-{uuid4().hex[:8]}@example.test", name=name)
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title=f"{name} project")
        db.add(project)
        await db.commit()
        await db.refresh(user)
        await db.refresh(project)
        return user, project


def _api_client(database, user: User) -> AsyncClient:
    async def _override_db():
        async with database() as session:
            yield session

    async def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_current_user_required] = _override_user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class _ScriptedClient:
    model = "test-voice-candidates-model-v1"
    capabilities = SimpleNamespace(supports_native_tools=True, supports_streaming=False)

    def __init__(self, handler):
        self._handler = handler
        self.calls: list[dict] = []

    async def generate_with_tools(self, **kwargs):
        self.calls.append(kwargs)
        return await self._handler(len(self.calls), kwargs)

    async def generate_stream_with_tools(self, **kwargs):
        gen = await self.generate_with_tools(**kwargs)
        on_delta = kwargs.get("on_delta")
        if on_delta is not None and gen.content:
            on_delta(gen.content)
        return gen


@pytest.mark.asyncio
async def test_chat_origin_voice_and_music_candidates_sse_selection_and_isolation(
    database, tmp_path, monkeypatch
):
    """Full ASGI SSE /api/v1/chat flow: show_voice_candidates + enriched show_music_candidates -> select_voice -> owner isolation."""
    monkeypatch.setattr(database_module, "AsyncSessionLocal", database)
    monkeypatch.setattr("app.tools.project_context.AsyncSessionLocal", database)
    monkeypatch.setattr("app.chat.conversation_context.AsyncSessionLocal", database)
    monkeypatch.setattr("app.chat.editor.AsyncSessionLocal", database)
    monkeypatch.setattr("app.chat.editor_media.AsyncSessionLocal", database)
    monkeypatch.setattr("app.tools.video.design.AsyncSessionLocal", database)
    monkeypatch.setattr("app.tools.video.music_preparation.AsyncSessionLocal", database)
    monkeypatch.setattr("app.tools.world.AsyncSessionLocal", database)
    monkeypatch.setattr(settings, "s3_endpoint_url", f"local://{tmp_path}")

    user_a, project_a = await _make_user_and_project(database, "owner-a")
    user_b, project_b = await _make_user_and_project(database, "owner-b")

    voice_wav = _wav_bytes(duration_s=3.0, freq=300.0)
    bgm_wav = _wav_bytes(duration_s=4.0, freq=220.0)

    # Seed: 1 private voice owned by user_a, 1 curated platform voice, 1 private voice owned by user_b, and 1 enriched BGM
    async with database() as db:
        v_private_a_id = uuid4()
        key_a = voice_reference_key(v_private_a_id)
        await storage.save(key_a, voice_wav, content_type="audio/wav")
        v_private_a = Voice(
            id=v_private_a_id,
            owner_id=user_a.id,
            scope="user",
            status="ready",
            source_kind="minimax_design",
            name="OxValue Institutional Baritone",
            description="Calm British institutional narrator.",
            languages=["en"],
            gender="male",
            age_band="35-45",
            tone_tags=["authoritative", "institutional"],
            compatible_styles=["institutional_dark"],
            provider="minimax",
            provider_voice_id="vd_oxvalue_baritone",
            reference_audio_key=key_a,
            preview_audio_key=key_a,
            use_count=3,
            meta={"duration_seconds": 3},
        )

        v_platform_id = uuid4()
        key_p = voice_reference_key(v_platform_id)
        await storage.save(key_p, voice_wav, content_type="audio/wav")
        v_platform = Voice(
            id=v_platform_id,
            owner_id=None,
            scope="platform",
            status="curated",
            source_kind="minimax_stock",
            name="Curated Studio Narrator",
            description="Platform curated studio voice.",
            languages=["en"],
            gender="female",
            age_band="28-38",
            tone_tags=["warm", "documentary"],
            compatible_styles=["institutional_dark", "swiss_paper"],
            provider="minimax",
            provider_voice_id="English_Graceful_Lady",
            reference_audio_key=key_p,
            preview_audio_key=key_p,
            use_count=5,
            meta={"duration_seconds": 3},
        )

        v_private_b_id = uuid4()
        key_b = voice_reference_key(v_private_b_id)
        await storage.save(key_b, voice_wav, content_type="audio/wav")
        v_private_b = Voice(
            id=v_private_b_id,
            owner_id=user_b.id,
            scope="user",
            status="ready",
            source_kind="minimax_clone",
            name="Secret User B Clone",
            description="Private cloned voice of user B.",
            languages=["en"],
            gender="male",
            age_band="30-40",
            tone_tags=["authoritative"],
            compatible_styles=["institutional_dark"],
            provider="minimax",
            provider_voice_id="clone_user_b_secret",
            reference_audio_key=key_b,
            preview_audio_key=key_b,
            use_count=0,
        )

        db.add_all([v_private_a, v_platform, v_private_b])
        await db.flush()

        bgm_row = await create_music_from_generation(
            db,
            prompt="Minimal institutional pulse underscore, 108 BPM",
            generated=GeneratedMusic(
                audio_bytes=bgm_wav,
                ext="wav",
                duration_seconds=4,
                size_bytes=len(bgm_wav),
                model="studio-synth-v2",
                generation_id="synth-inst-108",
                extra_meta={"bpm": 108, "style": "institutional"},
            ),
            mood="institutional-pulse",
            title="OxValue Institutional Pulse",
            user_id=user_a.id,
            is_public=True,
            tags=["institutional", "pulse"],
            compatible_styles=["institutional_dark"],
            scope="user",
            status="ready",
        )
        bgm_row.use_count = 2
        await db.commit()

    # Turn 1: show_voice_candidates + show_music_candidates via SSE /api/v1/chat/stream
    async def _turn1_handler(step: int, kwargs: dict):
        if step == 1:
            return ToolGeneration(
                content="",
                tool_calls=[
                    ToolCall(
                        id="tc_vc",
                        name="show_voice_candidates",
                        arguments={"language": "en", "style_preset": "institutional_dark"},
                    ),
                ],
            )
        if step == 2:
            return ToolGeneration(
                content="",
                tool_calls=[
                    ToolCall(
                        id="tc_mc",
                        name="show_music_candidates",
                        arguments={"style_preset": "institutional_dark"},
                    ),
                ],
            )
        return ToolGeneration(
            content="Here are playable permanent voices and BGM tracks you can audition right in chat.",
            tool_calls=[],
        )

    monkeypatch.setattr(intent_router, "client", _ScriptedClient(_turn1_handler))

    conversation_id: str | None = None
    voice_set_id: str | None = None
    try:
        async with _api_client(database, user_a) as client_a:
            resp = await client_a.post(
                "/api/v1/chat",
                headers={"Accept": "text/event-stream"},
                json={
                    "project_id": str(project_a.id),
                    "message": "Show me institutional dark voice and music candidates to audition.",
                },
            )
            assert resp.status_code == 200, resp.text
            sse_events = _parse_sse_events(resp.text)

            for ev_name, payload in sse_events:
                if ev_name == "conversation" and payload.get("conversation_id"):
                    conversation_id = payload["conversation_id"]
                elif payload.get("conversation_id") and conversation_id is None:
                    conversation_id = payload["conversation_id"]

            candidate_events = [p for name, p in sse_events if name == "assistant.candidates"]
            voice_sets = [p for p in candidate_events if p.get("kind") == "voice_set"]
            music_sets = [p for p in candidate_events if p.get("kind") == "music_set"]

            assert len(voice_sets) == 1
            vset = voice_sets[0]
            voice_set_id = vset["candidate_set_id"]
            assert vset["asset_id"] is None
            v_ids = {m["voice_id"] for m in vset["members"]}
            assert str(v_private_a_id) in v_ids
            assert str(v_platform_id) in v_ids
            # Owner isolation: user_b's private cloned voice MUST NOT appear!
            assert str(v_private_b_id) not in v_ids

            member_a = next(m for m in vset["members"] if m["voice_id"] == str(v_private_a_id))
            assert member_a["provider"] == "voice_library"
            assert member_a["provider_id"] == str(v_private_a_id)
            assert member_a["provider_voice_id"] == "vd_oxvalue_baritone"
            assert member_a["title"] == "OxValue Institutional Baritone"
            assert member_a["source_kind"] == "minimax_design"
            assert member_a["scope"] == "user"
            assert member_a["languages"] == ["en"]
            assert member_a["gender"] == "male"
            assert member_a["age_band"] == "35-45"
            assert member_a["tone_tags"] == ["authoritative", "institutional"]
            assert member_a["compatible_styles"] == ["institutional_dark"]
            assert member_a["use_count"] == 3
            assert member_a["preview_url"] == f"/api/v1/voices/{v_private_a_id}/audio"
            assert member_a["start"] == 0 and member_a["end"] == 3

            # Enriched music_set assertions
            assert len(music_sets) == 1
            mset = music_sets[0]
            assert len(mset["members"]) == 1
            mm = mset["members"][0]
            assert mm["bpm"] == 108
            assert mm["lufs"] is not None
            assert mm["compatible_styles"] == ["institutional_dark"]
            assert mm["tags"] == ["institutional", "pulse"]
            assert mm["mood"] == "institutional-pulse"
            assert mm["scope"] == "user"
            assert mm["status"] == "ready"
            assert mm["instrumental"] is True
            assert mm["use_count"] == 2

            # Activity frames emitted for voiceSearch
            activity_keys = [
                p.get("key") for name, p in sse_events if name == "assistant.activity"
            ]
            assert "chat.activity.voiceSearch" in activity_keys
            assert "chat.activity.voiceSearchDone" in activity_keys

            # Verify candidates_log persisted in DB
            async with database() as db:
                logs = list(
                    (
                        await db.scalars(
                            select(Message).where(Message.intent["type"].astext == "candidates_log")
                        )
                    ).all()
                )
                assert len(logs) >= 1
                all_logged = [e for row in logs for e in ((row.intent or {}).get("events") or [])]
                assert any(e.get("kind") == "voice_set" and e.get("candidate_set_id") == voice_set_id for e in all_logged)

            # Determine member_index of v_private_a in vset
            idx_a = next(i for i, m in enumerate(vset["members"]) if m["voice_id"] == str(v_private_a_id))

            # Turn 2: select_voice resolves persisted voice_set member cleanly!
            selected_obs_box: list[dict] = []

            async def _turn2_handler(step: int, kwargs: dict):
                if step == 1:
                    return ToolGeneration(
                        content="",
                        tool_calls=[
                            ToolCall(
                                id="tc_sv_pick",
                                name="select_voice",
                                arguments={
                                    "candidate_set_id": voice_set_id,
                                    "member_index": idx_a,
                                },
                            )
                        ],
                    )
                for msg in reversed(kwargs.get("messages") or []):
                    txt = str(msg.get("content") or "")
                    if "vd_oxvalue_baritone" in txt:
                        json_part = txt.split("\n", 1)[-1]
                        selected_obs_box.append(json.loads(json_part))
                        break
                return ToolGeneration(
                    content="Locked OxValue Institutional Baritone for your video.",
                    tool_calls=[],
                )

            monkeypatch.setattr(intent_router, "client", _ScriptedClient(_turn2_handler))

            resp2 = await client_a.post(
                "/api/v1/chat",
                headers={"Accept": "text/event-stream"},
                json={
                    "project_id": str(project_a.id),
                    "conversation_id": conversation_id,
                    "message": "Use the first voice.",
                },
            )
            assert resp2.status_code == 200, resp2.text
            sse_events_2 = _parse_sse_events(resp2.text)

            assert selected_obs_box, "Expected select_voice observation payload"
            assert selected_obs_box[0]["voice_id"] == str(v_private_a_id)
            assert selected_obs_box[0]["provider_voice_id"] == "vd_oxvalue_baritone"
            assert any(
                name == "assistant.candidates"
                and p.get("kind") == "selection"
                and p.get("candidate_set_id") == voice_set_id
                and p.get("selected") == [idx_a]
                for name, p in sse_events_2
            )
            activity_keys_2 = [
                p.get("key") for name, p in sse_events_2 if name == "assistant.activity"
            ]
            assert "chat.activity.voiceSelection" in activity_keys_2
            assert "chat.activity.voiceSelectionDone" in activity_keys_2

            # Direct owner-isolation verification on select_voice_candidate:
            # user_b MUST NOT be able to select user_a's private voice even with the voice_set event!
            async with database() as db:
                with pytest.raises(VoiceCandidateError, match="no longer accessible"):
                    await select_voice_candidate(
                        db,
                        owner_id=user_b.id,
                        events=[vset],
                        candidate_set_id=UUID(voice_set_id),
                        member_index=idx_a,
                    )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_chat_origin_create_video_verbatim_lockstep_and_bilingual_translations(
    database, tmp_path, monkeypatch
):
    """End-to-end create_video splits multi-clause cues into verbatim timed phrases, aligns caption_translations, and ignores same-language paraphrases."""
    monkeypatch.setattr(database_module, "AsyncSessionLocal", database)
    monkeypatch.setattr("app.tools.project_context.AsyncSessionLocal", database)
    monkeypatch.setattr("app.chat.conversation_context.AsyncSessionLocal", database)
    monkeypatch.setattr("app.chat.editor.AsyncSessionLocal", database)
    monkeypatch.setattr("app.chat.editor_media.AsyncSessionLocal", database)
    monkeypatch.setattr("app.tools.video.design.AsyncSessionLocal", database)
    monkeypatch.setattr("app.tools.video.music_preparation.AsyncSessionLocal", database)
    monkeypatch.setattr("app.tools.world.AsyncSessionLocal", database)
    monkeypatch.setattr(settings, "s3_endpoint_url", f"local://{tmp_path}")
    monkeypatch.setattr(settings, "minimax_api_key", "test-minimax-key")

    user, project = await _make_user_and_project(database, "sync-test")
    tts_wav_1 = _wav_bytes(duration_s=5.4, freq=330.0)
    tts_wav_2 = _wav_bytes(duration_s=5.0, freq=360.0)

    call_idx = 0

    def _fake_t2a(text: str, voice_id: str, language: str = "en", speed: float = 1.0) -> T2AResult:
        nonlocal call_idx
        call_idx += 1
        return T2AResult(
            audio=tts_wav_1 if call_idx == 1 else tts_wav_2,
            subtitle_file=f"https://cues.example.test/sync-{call_idx}.json",
            usage_characters=len(text),
            trace_id=f"trace-sync-{call_idx}",
        )

    def _fake_cues(subtitle_file: str, *, source_text: str) -> list[dict]:
        dur_ms = 5400.0 if subtitle_file.endswith("1.json") else 5000.0
        return [
            {
                "text": source_text,
                "text_begin": 0,
                "text_end": len(source_text),
                "time_begin": 0.0,
                "time_end": dur_ms,
            }
        ]

    monkeypatch.setattr(voice_provider, "synthesize_detailed", _fake_t2a)
    monkeypatch.setattr(voice_provider, "fetch_subtitle_cues", _fake_cues)

    en_narration = "Every valuation model breaks down, when private IP data stays locked in silos."
    zh_narration = "过去剪一支产品宣传片，你要在时间线上反复对齐音频和画面。"

    async def _handler(step: int, kwargs: dict):
        if step == 1:
            return ToolGeneration(
                content="",
                tool_calls=[
                    ToolCall(
                        id="tc_cv_sync",
                        name="create_video",
                        arguments={
                            "name": "Lockstep Sync Proof",
                            "style_preset": "institutional_dark",
                            "motion_blocks": [
                                {
                                    "block_id": "statement_hook",
                                    "duration_seconds": 6.0,
                                    "props": {"headline": "Audited Valuation"},
                                    "narration": en_narration,
                                    # Same-language paraphrase MUST be ignored in favor of verbatim MiniMax cues!
                                    "caption_text": "Private IP Models Need Better Data",
                                },
                                {
                                    "block_id": "closing_cta",
                                    "duration_seconds": 5.8,
                                    "props": {"brand_name": "Rookie Cut", "tagline": "Direct by chat"},
                                    "narration": zh_narration,
                                    "caption_translations": [
                                        "Editing a product film used to take hours,",
                                        "aligning audio and visuals on a timeline.",
                                    ],
                                },
                            ],
                        },
                    )
                ],
            )
        return ToolGeneration(content="Created lockstep synced composition.", tool_calls=[])

    monkeypatch.setattr(intent_router, "client", _ScriptedClient(_handler))

    try:
        async with _api_client(database, user) as client:
            resp = await client.post(
                "/api/v1/chat",
                json={
                    "project_id": str(project.id),
                    "message": "Create a 2-act narrated promo with synced subtitles.",
                },
            )
            assert resp.status_code == 201, resp.text
    finally:
        app.dependency_overrides.clear()

    async with database() as db:
        comp = await db.scalar(select(Composition).where(Composition.origin_project_id == project.id))
        assert comp is not None
        version = await db.get(CompositionVersion, comp.current_version_id)
        assert version is not None
        content = content_of(version)
        tb = content.settings.timebase

        dialogue_clips = [
            c for t in content.timeline.tracks if t.kind == "audio" and t.role == "dialogue" for c in t.clips
        ]
        caption_clips = [
            c for t in content.timeline.tracks if t.kind == "visual" and t.role == "caption" for c in t.clips
        ]
        assert len(dialogue_clips) == 2

        # Act 1 (EN): split into 2 verbatim phrases; same-language paraphrase ignored!
        s1_caps = [c for c in caption_clips if c.scene_id == "scene_1"]
        assert len(s1_caps) == 2
        assert " ".join(c.object.text for c in s1_caps) == en_narration
        assert all("Better Data" not in c.object.text for c in s1_caps)
        for c in s1_caps:
            assert c.range.start >= dialogue_clips[0].range.start - round(0.05 * tb)
            assert c.range.end <= dialogue_clips[0].range.end + round(0.05 * tb)

        # Act 2 (ZH + caption_translations): split into 2 bilingual lockstep phrases!
        s2_caps = [c for c in caption_clips if c.scene_id == "scene_2"]
        assert len(s2_caps) == 2
        assert "".join(c.object.text.split("\n", 1)[0] for c in s2_caps) == zh_narration
        assert s2_caps[0].object.text.split("\n", 1)[1] == "Editing a product film used to take hours,"
        assert s2_caps[1].object.text.split("\n", 1)[1] == "aligning audio and visuals on a timeline."
        for c in s2_caps:
            assert c.range.start >= dialogue_clips[1].range.start - round(0.05 * tb)
            assert c.range.end <= dialogue_clips[1].range.end + round(0.05 * tb)
            assert c.object.style.background_mode == "pill"
            assert c.object.style.secondary_line_scale == 0.74
