"""Layer 1A Chat-Origin: permanent voice/music library + FirstMotionBlock narration + synced tight captions + ducked BGM."""

from __future__ import annotations

import io
import json
import math
import wave
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import numpy as np
import pytest
from sqlalchemy import select

from app.agents.tool_progress import bind_progress
from app.chat.editor_create import CreateVideoArgs, create_video
from app.chat.intent import intent_router
from app.chat.service import _create_message
from app.config import settings
from app.dependencies import get_current_user, get_current_user_required, get_db
from app.editing.store import content_of
from app.main import app
from app.models import database as database_module
from app.models.tables import (
    Composition,
    CompositionVersion,
    Conversation,
    Music,
    Project,
    User,
    Voice,
)
from app.pipeline.music import (
    GeneratedMusic,
    create_music_from_generation,
    search_music_library,
)
from app.providers import storage
from app.providers import voice as voice_provider
from app.providers.llm.base import ToolCall, ToolGeneration
from app.providers.voice import T2AResult, VoiceDesignResult
from test.support.db_helpers import _project, _user


def _wav_bytes(*, duration_s: float = 2.0, freq: float = 330.0, amplitude: float = 0.2, rate: int = 24000) -> bytes:
    n = int(rate * duration_s)
    t = np.arange(n, dtype=np.float64) / rate
    pcm = np.clip(amplitude * np.sin(2.0 * math.pi * freq * t), -1.0, 1.0)
    samples = (pcm * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(samples.tobytes())
    return buf.getvalue()


class _ScriptedClient:
    model = "test-audio-lib-model-v1"
    capabilities = SimpleNamespace(supports_native_tools=True, supports_streaming=False)

    def __init__(self, generations: list[ToolGeneration]):
        self._generations = list(generations)
        self.calls: list[dict] = []

    async def generate_with_tools(self, **kwargs):
        self.calls.append(kwargs)
        assert self._generations, "Unexpected extra LLM iteration"
        return self._generations.pop(0)


def _api_client(database, user: User):
    async def _override_db():
        async with database() as session:
            yield session

    async def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user_required] = _override_user
    app.dependency_overrides[get_current_user] = _override_user
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )


@pytest.mark.asyncio
async def test_rest_voices_and_upgraded_music_library_with_duplicate_moods_and_isolation(
    database, tmp_path, monkeypatch
):
    monkeypatch.setattr(database_module, "AsyncSessionLocal", database)
    monkeypatch.setattr(settings, "s3_endpoint_url", f"local://{tmp_path}")
    monkeypatch.setattr(settings, "minimax_api_key", "test-key")

    owner_a_id = await _user(database)
    owner_b_id = await _user(database)

    wav_a = _wav_bytes(duration_s=2.0, freq=260.0)
    wav_b = _wav_bytes(duration_s=2.0, freq=440.0)

    # 1. Upgraded music table accepts multiple tracks sharing the exact same mood!
    async with database() as db:
        m1 = await create_music_from_generation(
            db,
            prompt="Warm editorial piano pulse",
            generated=GeneratedMusic(
                audio_bytes=wav_a, ext="wav", duration_seconds=2, size_bytes=len(wav_a), model="music-2.6-free", generation_id="g1"
            ),
            mood="editorial-warm",
            title="Editorial Piano Pulse",
            user_id=owner_a_id,
            is_public=True,
            tags=["piano", "warm"],
            compatible_styles=["vox_editorial", "swiss_paper"],
            scope="user",
            status="ready",
        )
        m2 = await create_music_from_generation(
            db,
            prompt="Warm acoustic marimba bed",
            generated=GeneratedMusic(
                audio_bytes=wav_b, ext="wav", duration_seconds=2, size_bytes=len(wav_b), model="music-2.6-free", generation_id="g2"
            ),
            mood="editorial-warm",
            title="Acoustic Marimba Bed",
            user_id=owner_a_id,
            is_public=False,
            tags=["marimba", "warm"],
            compatible_styles=["vox_editorial"],
            scope="user",
            status="ready",
        )
        assert m1.mood == "editorial-warm"
        assert m2.mood == "editorial-warm"
        assert m1.lufs is not None and m2.lufs is not None

        # Multi-facet search sees both for owner_a, only public m1 for owner_b
        hits_a = await search_music_library(
            db, owner_id=owner_a_id, style_preset="vox_editorial", mood="editorial-warm"
        )
        hits_b = await search_music_library(
            db, owner_id=owner_b_id, style_preset="vox_editorial", mood="editorial-warm"
        )
        assert {m.id for m in hits_a} == {m1.id, m2.id}
        assert {m.id for m in hits_b} == {m1.id}

    # 2. REST endpoints: /api/v1/voices/design, /api/v1/voices, /api/v1/voices/{id}/audio, /api/v1/music
    designed_audio = _wav_bytes(duration_s=1.0, freq=300.0)
    monkeypatch.setattr(
        voice_provider,
        "design_voice",
        lambda prompt, preview_text, **kw: VoiceDesignResult(
            voice_id="vd_rest_founder_01",
            trial_audio=designed_audio,
            trace_id="tr-rest-1",
        ),
    )

    async with database() as db:
        user_a = await db.get(User, owner_a_id)
        user_b = await db.get(User, owner_b_id)

    try:
        async with _api_client(database, user_a) as client_a:
            resp = await client_a.post(
                "/api/v1/voices/design",
                json={
                    "name": "Founder Warm EN",
                    "prompt": "Warm confident founder voice",
                    "preview_text": "Welcome to Rookie Cut.",
                    "languages": ["en"],
                    "tone_tags": ["warm", "founder"],
                    "compatible_styles": ["vox_editorial"],
                },
            )
            assert resp.status_code == 201, resp.text
            voice_data = resp.json()
            assert voice_data["provider_voice_id"] == "vd_rest_founder_01"
            assert voice_data["scope"] == "user"
            assert voice_data["preview_url"] == f"/api/v1/voices/{voice_data['id']}/audio"

            list_resp = await client_a.get("/api/v1/voices", params={"language": "en", "style_preset": "vox_editorial"})
            assert list_resp.status_code == 200
            assert any(item["id"] == voice_data["id"] for item in list_resp.json())

            audio_resp = await client_a.get(f"/api/v1/voices/{voice_data['id']}/audio")
            assert audio_resp.status_code == 200
            assert audio_resp.content == designed_audio

            music_resp = await client_a.get("/api/v1/music")
            assert music_resp.status_code == 200
            music_items = music_resp.json()
            m1_json = next(item for item in music_items if item["id"] == str(m1.id))
            assert m1_json["scope"] == "user"
            assert m1_json["status"] == "ready"
            assert m1_json["tags"] == ["piano", "warm"]
            assert m1_json["compatible_styles"] == ["vox_editorial", "swiss_paper"]
            assert m1_json["instrumental"] is True
            assert m1_json["lufs"] is not None
            assert m1_json["use_count"] == 0

        # Privacy check: user_b MUST NOT see or stream user_a's private voice!
        async with _api_client(database, user_b) as client_b:
            list_b = await client_b.get("/api/v1/voices")
            assert list_b.status_code == 200
            assert all(item["id"] != voice_data["id"] for item in list_b.json())

            audio_b = await client_b.get(f"/api/v1/voices/{voice_data['id']}/audio")
            assert audio_b.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_chat_origin_permanent_audio_flywheel_and_tts_motion_blocks(
    database, tmp_path, monkeypatch
):
    """End-to-end ASGI POST /api/v1/chat: search_voices -> design_voice -> search_music -> create_video(narration + music_id)."""
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

    owner_id = await _user(database)
    project_id = await _project(database, owner_id)

    bgm_wav = _wav_bytes(duration_s=4.0, freq=220.0, amplitude=0.18)
    tts_wav_1 = _wav_bytes(duration_s=2.6, freq=340.0, amplitude=0.25)
    tts_wav_2 = _wav_bytes(duration_s=2.2, freq=380.0, amplitude=0.25)
    design_preview = _wav_bytes(duration_s=1.0, freq=310.0)

    # Seed one permanent BGM track in the music library
    async with database() as db:
        bgm_track = await create_music_from_generation(
            db,
            prompt="Clean warm editorial instrumental bed",
            generated=GeneratedMusic(
                audio_bytes=bgm_wav,
                ext="wav",
                duration_seconds=4,
                size_bytes=len(bgm_wav),
                model="music-2.6-free",
                generation_id="bgm-chat-1",
            ),
            mood="editorial-warm",
            title="Editorial Warm Bed",
            user_id=owner_id,
            is_public=True,
            tags=["editorial", "warm", "piano"],
            compatible_styles=["vox_editorial"],
            scope="user",
            status="ready",
        )
        bgm_id = bgm_track.id
        user = await db.get(User, owner_id)

    # Mock MiniMax voice_design + T2A synthesis + sentence cues (zero live network!)
    monkeypatch.setattr(
        voice_provider,
        "design_voice",
        lambda prompt, preview_text, **kw: VoiceDesignResult(
            voice_id="vd_chat_editorial_01",
            trial_audio=design_preview,
            trace_id="trace-design-chat",
        ),
    )

    tts_calls: list[tuple[str, str]] = []

    def _fake_t2a(text: str, voice_id: str, language: str = "en", speed: float = 1.0) -> T2AResult:
        tts_calls.append((text, voice_id))
        audio = tts_wav_1 if len(tts_calls) == 1 else tts_wav_2
        return T2AResult(
            audio=audio,
            subtitle_file=f"https://cues.example.test/{len(tts_calls)}.json",
            usage_characters=len(text),
            trace_id=f"trace-t2a-{len(tts_calls)}",
        )

    def _fake_cues(subtitle_file: str, *, source_text: str) -> list[dict]:
        dur_ms = 2600.0 if subtitle_file.endswith("1.json") else 2200.0
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

    # Scripted agent calls:
    # Turn iter 1: search_voices + search_music (reuse-first!)
    # Turn iter 2: design_voice (creates permanent voiceprint)
    # Turn iter 3: create_video(motion_blocks with narration + bilingual caption_text, voice_id=designed, music_id=bgm_id)
    # Turn iter 4: answer
    designed_voice_id_box: list[str] = []

    class _DynamicScriptedClient(_ScriptedClient):
        async def generate_with_tools(self, **kwargs):
            self.calls.append(kwargs)
            step = len(self.calls)
            if step == 1:
                return ToolGeneration(
                    content="",
                    tool_calls=[
                        ToolCall(id="tc_sv", name="search_voices", arguments={"language": "en", "style_preset": "vox_editorial"}),
                        ToolCall(id="tc_sm", name="search_music", arguments={"style_preset": "vox_editorial", "mood": "editorial-warm"}),
                    ],
                )
            if step == 2:
                return ToolGeneration(
                    content="",
                    tool_calls=[
                        ToolCall(
                            id="tc_dv",
                            name="design_voice",
                            arguments={
                                "name": "Vox Editorial Narrator",
                                "prompt": "Warm documentary narrator, clear articulation",
                                "preview_text": "Cut videos at the speed of thought.",
                                "languages": ["en"],
                                "tone_tags": ["warm", "documentary"],
                                "compatible_styles": ["vox_editorial"],
                            },
                        )
                    ],
                )
            if step == 3:
                # Extract the designed voice_id from the prior tool observation!
                for msg in reversed(kwargs.get("messages") or []):
                    content = str(msg.get("content") or "")
                    if "vd_chat_editorial_01" in content:
                        parsed = json.loads(content)
                        designed_voice_id_box.append(parsed["voice_id"])
                        break
                assert designed_voice_id_box, "Expected design_voice tool observation with voice_id"
                return ToolGeneration(
                    content="",
                    tool_calls=[
                        ToolCall(
                            id="tc_cv",
                            name="create_video",
                            arguments={
                                "name": "Rookie Cut Commercial Draft",
                                "style_preset": "vox_editorial",
                                "voice_id": designed_voice_id_box[0],
                                "narration_language": "en",
                                "music_id": str(bgm_id),
                                "caption_preset": "bilingual_cinema",
                                "motion_blocks": [
                                    {
                                        "block_id": "statement_hook",
                                        "duration_seconds": 10.0,  # deliberately long -> should tighten to [2.6+0.45, 2.6+1.5] = 4.1s!
                                        "props": {"headline": "Cut by Chat", "subheadline": "Zero timeline grind"},
                                        "narration": "Cut flagship product videos in seconds by chatting.",
                                        "caption_text": "Cut flagship product videos in seconds.\n用对话几秒剪出旗舰产品宣传片。",
                                        "transition_after": "whip_pan",
                                        "transition_duration_seconds": 0.4,
                                    },
                                    {
                                        "block_id": "closing_cta",
                                        "duration_seconds": 2.0,  # shorter than 2.2s TTS -> should expand to 2.2+0.45 = 2.65s!
                                        "props": {"brand_name": "Rookie Cut", "tagline": "Direct by chat"},
                                        "narration": "Try Rookie Cut today.",
                                    },
                                ],
                            },
                        )
                    ],
                )
            return ToolGeneration(
                content="Created your voiced Vox Editorial commercial draft with tight-pill captions and ducked BGM.",
                tool_calls=[],
            )

    scripted = _DynamicScriptedClient([])
    monkeypatch.setattr(intent_router, "client", scripted)

    try:
        async with _api_client(database, user) as client:
            resp = await client.post(
                "/api/v1/chat",
                json={
                    "project_id": str(project_id),
                    "message": "Make a Vox Editorial promo video with voiceover, bilingual captions, and warm BGM.",
                },
            )
            assert resp.status_code == 201, resp.text
    finally:
        app.dependency_overrides.clear()

    # Verify DB state: permanent voice saved + use_count incremented, music use_count incremented, composition tracks verified
    async with database() as db:
        voice_row = await db.get(Voice, UUID(designed_voice_id_box[0]))
        assert voice_row is not None
        assert voice_row.provider_voice_id == "vd_chat_editorial_01"
        assert voice_row.use_count == 1
        assert voice_row.reference_audio_key is not None
        assert await storage.exists(voice_row.reference_audio_key)

        refreshed_bgm = await db.get(Music, bgm_id)
        assert refreshed_bgm is not None
        assert refreshed_bgm.use_count == 1

        comp = await db.scalar(select(Composition).where(Composition.origin_project_id == project_id))
        assert comp is not None
        version = await db.get(CompositionVersion, comp.current_version_id)
        assert version is not None
        content = content_of(version)
        tb = content.settings.timebase

        # Motion block pacing adapted to measured TTS duration (no 4+s dead air, no clipped speech!)
        mg_clips = [c for t in content.timeline.tracks for c in t.clips if c.object.kind == "motion_block"]
        assert len(mg_clips) == 2
        act1_s = mg_clips[0].range.duration / tb
        act2_s = mg_clips[1].range.duration / tb
        assert 3.0 <= act1_s <= 4.2  # tightened from 10.0s to measured 2.6s + 1.5s = 4.1s!
        assert 2.6 <= act2_s <= 3.0  # expanded from 2.0s to measured 2.2s + 0.45s = 2.65s!

        # Dialogue track has 2 bound voiceover audio clips synthesized with the designed voice
        dialogue_tracks = [t for t in content.timeline.tracks if t.kind == "audio" and t.role == "dialogue"]
        assert len(dialogue_tracks) == 1
        assert len(dialogue_tracks[0].clips) == 2
        assert all(voice_id == "vd_chat_editorial_01" for _, voice_id in tts_calls)

        # Both acts carry editable captions with the chosen bilingual style.
        caption_tracks = [t for t in content.timeline.tracks if t.kind == "visual" and t.role == "caption"]
        assert len(caption_tracks) == 1
        assert len(caption_tracks[0].clips) == 3
        for cap in caption_tracks[0].clips:
            assert cap.object.style.background_mode == "pill"
            assert cap.object.style.background == "#111318"
            assert cap.object.style.background_padding == (20.0, 10.0)
            assert cap.object.style.background_radius == 10.0
            assert cap.object.style.secondary_line_scale == 0.74
        from app.chat.editor import EditTextArgs, SetCompositionStyleArgs, edit_clip
        from app.editing.schemas import SourceCaptionDerivation, speech_text_digest
        from app.editing.timing import source_ticks_to_output_ticks

        caps = caption_tracks[0].clips
        assert [len(c.object.text.splitlines()) for c in caps] == [2, 2, 1]
        assert " ".join(c.object.text.splitlines()[0] for c in caps[:2]) == "Cut flagship product videos in seconds by chatting."
        for cap in caps:
            derivation = cap.object.caption
            assert isinstance(derivation, SourceCaptionDerivation) and derivation.state == "derived"
            assert derivation.alignment == "minimax-t2a-v2-sentence-v1"
            assert derivation.source_text_digest == speech_text_digest(cap.object.text.splitlines()[0])
            source = next(c for c in dialogue_tracks[0].clips if c.scene_id == cap.scene_id)
            assert (derivation.snapshot_id, derivation.snapshot_digest) == (source.source.snapshot_id, source.source.snapshot_digest)
            for edge in ("start", "end"):
                assert getattr(cap.range, edge) == source.range.start + source_ticks_to_output_ticks(
                    getattr(derivation.source_range, edge) - source.source.source_range.start, tb
                )

        chat = await db.scalar(select(Conversation).where(Conversation.project_id == project_id))
        opening = await _create_message(db, chat.id, "user", "Restyle the captions and edit the opening line")
        opening.turn_state = "in_flight"
        await db.commit()
        project = await db.get(Project, project_id)

        async def edit(name, call_id, args):
            nonlocal version
            result = await edit_clip(
                db, name=name, project=project, opening_id=opening.id, conversation_id=chat.id,
                call_id=call_id, args=args, base={
                    "composition_id": str(comp.id), "composition_version_id": str(version.id),
                    "content_digest": version.content_digest,
                },
            )
            version = await db.get(CompositionVersion, UUID(result["version_id"]))
            return result

        style = await edit("set_composition_style", "restyle", SetCompositionStyleArgs(preset_id="swiss_paper"))
        assert style["style_summary"]["captions_updated"] == len(caps)
        batch = await edit("edit_text", "preset", EditTextArgs(scope="all_derived_captions", preset_id="bilingual_cinema"))
        assert set(batch["text_summary"]["updated_clip_ids"]) == {c.clip_id for c in caps}
        await edit("edit_text", "review", EditTextArgs(scope="clip", clip_id=caps[0].clip_id, text="Reviewed wording"))
        final = await edit("edit_text", "resize", EditTextArgs(scope="all_derived_captions", font_size=47))
        assert set(final["text_summary"]["updated_clip_ids"]) == {c.clip_id for c in caps[1:]}
        reviewed = next(c for t in content_of(version).timeline.tracks for c in t.clips if c.clip_id == caps[0].clip_id)
        assert reviewed.object.text == "Reviewed wording" and reviewed.object.caption.state == "independent"

        # Music track has full-length BGM clips automatically ducked to -22 dB with fades!
        music_tracks = [t for t in content.timeline.tracks if t.kind == "audio" and t.role == "music"]
        assert len(music_tracks) == 1
        assert len(music_tracks[0].clips) >= 1
        assert music_tracks[0].clips[0].object.gain_db == pytest.approx(-22.0)
        assert any(a.property == "audio.gain" for c in music_tracks[0].clips for a in c.animations)


@pytest.mark.asyncio
async def test_create_video_motion_block_pending_speech_and_voice_forbidden_guard(
    database, monkeypatch
):
    """When MiniMax is unconfigured, FirstMotionBlock.narration builds pending SpeechObject + derived tight captions; forbidden voiceover raises ValueError."""
    monkeypatch.setattr(database_module, "AsyncSessionLocal", database)
    monkeypatch.setattr(settings, "minimax_api_key", "")

    owner_id = await _user(database)
    project_id = await _project(database, owner_id)

    async with database() as db:
        project = await db.get(Project, project_id)
        conv = Conversation(user_id=owner_id, project_id=project_id, title="Pending speech test")
        db.add(conv)
        await db.commit()
        opening = await _create_message(db, conv.id, "user", "Create a narrated 2-act motion promo")
        opening.turn_state = "in_flight"
        await db.commit()

        turn = SimpleNamespace(
            project=project,
            conversation_id=conv.id,
            turn_id=opening.id,
            text=opening.content,
        )
        args = CreateVideoArgs(
            name="Offline Narrated Promo",
            style_preset="institutional_dark",
            caption_preset="bilingual_cinema",
            motion_blocks=[
                {
                    "block_id": "statement_hook",
                    "duration_seconds": 5.0,
                    "props": {"headline": "Fast Cuts"},
                    "narration": "过去剪一支产品宣传片，你要在时间线上反复对齐音频和画面。",
                    "caption_translations": ["Editing a product film took hours, aligning audio with each frame."],
                },
                {
                    "block_id": "closing_cta",
                    "duration_seconds": 4.0,
                    "props": {"brand_name": "Rookie Cut", "tagline": "Direct by chat"},
                    "narration": "Start creating now.",
                },
            ],
        )
        with bind_progress("create-pending-vo-1", None):
            result = await create_video(db, turn, args)

        assert result["saved"] is True
        assert len(result["narration_clips"]) == 2
        assert all(c["kind"] == "speech" for c in result["narration_clips"])

        version = await db.get(CompositionVersion, UUID(result["version_id"]))
        content = content_of(version)
        speech_clips = [c for t in content.timeline.tracks for c in t.clips if c.object.kind == "speech"]
        assert len(speech_clips) == 2
        caption_clips = [
            c for t in content.timeline.tracks if t.role == "caption" for c in t.clips
        ]
        assert len(caption_clips) == 2
        assert all(c.object.caption is not None and c.object.caption.state == "derived" for c in caption_clips)
        assert all(c.object.style.background_mode == "pill" for c in caption_clips)
        from app.editing.video_spec import _compile_derived_caption

        cap = caption_clips[0]
        primary, secondary = cap.object.text.split("\n")
        prepared = {
            "request": {"speech_object_id": cap.object.caption.speech_object_id,
                        "text_digest": cap.object.caption.source_text_digest},
            "normalized_text": primary,
            "cues": [{"text": primary, "text_begin": 0, "text_end": len(primary), "time_begin": 100, "time_end": 4000}],
        }
        compiled = _compile_derived_caption(cap, content, {cap.object.caption.speech_object_id: prepared})
        assert len(compiled) == 2
        lines = [c["object"]["text"].split("\n") for c in compiled]
        assert "".join(line[0] for line in lines) == primary
        assert " ".join(line[1] for line in lines) == secondary
        assert compiled[0]["start_frame"] == 3
        assert compiled[0]["end_frame"] == compiled[1]["start_frame"]
        assert compiled[1]["end_frame"] == 120

    # Voice-forbidden guardrail check on a fresh project
    project_id_2 = await _project(database, owner_id)
    async with database() as db:
        project_2 = await db.get(Project, project_id_2)
        conv_2 = Conversation(user_id=owner_id, project_id=project_id_2, title="No voiceover test")
        db.add(conv_2)
        await db.commit()
        opening_2 = await _create_message(db, conv_2.id, "user", "做一个产品宣传片，不要配音")
        opening_2.turn_state = "in_flight"
        await db.commit()
        turn_2 = SimpleNamespace(
            project=project_2,
            conversation_id=conv_2.id,
            turn_id=opening_2.id,
            text=opening_2.content,
        )
        with bind_progress("create-no-vo-1", None):
            with pytest.raises(ValueError, match="disallowed narration generation"):
                await create_video(db, turn_2, args)


@pytest.mark.asyncio
@pytest.mark.parametrize("needs_review", [False, True])
async def test_align_recording_word_axis_drives_narration_and_insert_text(database, tmp_path, monkeypatch, needs_review):
    from app.chat.editor import InsertTextArgs, edit_clip
    from app.chat.video_turn_seats import align_recording_seat
    from app.editing.edits import apply_ops
    from app.editing.narration_audio import narration_audio_ops
    from app.editing.revisions import text_safe_layout
    from app.editing.schemas import CompositionContent, Scene, TimeRange
    from app.editing.store import apply_composition_edits
    from app.models.schemas import AlignRecordingArgs
    from app.models.tables import Asset, AssetType, NarrationAlignment
    from app.tools.video import alignment_store

    monkeypatch.setattr(database_module, "AsyncSessionLocal", database)
    monkeypatch.setattr(settings, "s3_endpoint_url", f"local://{tmp_path}")
    script = "Keep every word on its measured beat, and give each phrase its own readable line."
    axis = [{"word": w, "start": i / 5, "end": i / 5 + 0.1} for i, w in enumerate(script.split())]
    sentences = [script]
    if needs_review:
        sentences.append("Unknown syllables.")
        script = " ".join(sentences)
    monkeypatch.setattr("app.providers.asr.transcribe", lambda path: {"words": axis})
    wait = alignment_store.wait_for_alignment

    async def run_worker(**request):
        async with database() as session:
            claim = await alignment_store.claim_pending_alignment(session)
        assert claim and claim[0] == request["alignment_id"]
        await alignment_store.process_narration_alignment(*claim)
        return await wait(**request)

    monkeypatch.setattr(alignment_store, "wait_for_alignment", run_worker)
    owner = await _user(database)
    project_id = await _project(database, owner)
    await storage.save("audio/recording.wav", _wav_bytes(duration_s=4), content_type="audio/wav")
    async with database() as db:
        project = await db.get(Project, project_id)
        asset = Asset(user_id=owner, project_id=project_id, type=AssetType.AUDIO, file_url="audio/recording.wav")
        chat = Conversation(user_id=owner, project_id=project_id)
        db.add_all([asset, chat])
        await db.commit()
        read = await align_recording_seat(
            project=project, args=AlignRecordingArgs(audio_asset_id=asset.id, text=script),
            mentions=[SimpleNamespace(type="asset", id=asset.id)],
        )
        facts = json.loads(read.text)
        assert facts["status"] == ("ALIGNED" if needs_review else "READY")
        assert facts["actual_duration_seconds"] == 4
        assert [cue["text"] for cue in facts["cues"]] == sentences
        row = await db.get(NarrationAlignment, UUID(facts["alignment_id"]))
        assert row.payload["sentences"][0]["semantics"] is None
        assert row.payload["sentences"][-1]["status"] == ("review_required" if needs_review else "aligned")
        await alignment_store.ready_alignment(db, owner_id=owner, alignment_id=row.id)
        content = CompositionContent(settings={"width": 1280, "height": 720}, scenes=[
            Scene(scene_id="intro", range=TimeRange(start=0, end=360000))
        ])
        ops = narration_audio_ops(
            content, scene_id="intro", snapshot_id=row.audio_snapshot_id, snapshot_digest=row.audio_digest, alignment=row,
        )
        content = apply_ops(content, ops, {row.audio_snapshot_id: row.audio_digest})
        captions = next(t.clips for t in content.timeline.tracks if t.role == "caption")
        assert len(captions) > 1
        assert " ".join(c.object.text for c in captions) == script
        for c in captions:
            assert c.object.layout == text_safe_layout(1280, 720, "bottom", role="caption")
            assert c.object.caption.narration_alignment_id == row.id
            assert c.range == c.object.caption.source_range
        comp, version, _ = await apply_composition_edits(db, owner_id=owner, origin_project_id=project_id, content=content)
        opening = await _create_message(db, chat.id, "user", "Caption the recording")
        opening.turn_state = "in_flight"
        await db.commit()
        result = await edit_clip(
            db, name="insert_text", project=project, opening_id=opening.id, conversation_id=chat.id,
            call_id="measured_captions", base={"composition_id": str(comp.id), "composition_version_id": str(version.id),
                                             "content_digest": version.content_digest},
            args=InsertTextArgs(from_audio_clip_id="clp_dialogue_intro", preset_id="karaoke_focus"),
        )
        assert result["text_summary"]["karaoke_clips"] == len(captions)
        updated = content_of(await db.get(CompositionVersion, UUID(result["version_id"])))
        inserted = [c for t in updated.timeline.tracks for c in t.clips if c.clip_id in result["text_summary"]["clip_ids"]]
        assert [(c.range, c.object.text) for c in inserted] == [(c.range, c.object.text) for c in captions]


@pytest.mark.asyncio
async def test_uploaded_audio_freezes_asr_words_for_caption_insertion(database, tmp_path, monkeypatch):
    from app.chat.editor import _resolve_aligned_caption_cues
    from app.editing.schemas import AudioObject, Clip, CompositionContent, TimeRange
    from app.models.tables import Asset, AssetType
    from app.tools.video.preparation import snapshot_audio_asset

    monkeypatch.setattr(settings, "s3_endpoint_url", f"local://{tmp_path}")
    owner = await _user(database)
    project_id = await _project(database, owner)
    script = "One measured phrase ends here, then the next one follows the silence."
    axis = [{"word": " " + w, "start": i * 0.25, "end": i * 0.25 + 0.125} for i, w in enumerate(script.split())]
    await storage.save("audio/upload.wav", _wav_bytes(duration_s=4), content_type="audio/wav")
    async with database() as db:
        asset = Asset(user_id=owner, project_id=project_id, type=AssetType.AUDIO, file_url="audio/upload.wav")
        db.add(asset)
        await db.flush()
        original = await snapshot_audio_asset(db, asset, owner_id=owner)
        asset.meta = {"words": axis}
        measured = await snapshot_audio_asset(db, asset, owner_id=owner)
        assert measured.id != original.id and measured.digest == original.digest
        assert "words" not in original.meta and measured.meta["words"] == axis
        assert (await snapshot_audio_asset(db, asset, owner_id=owner)).id == measured.id
        content = CompositionContent(settings={"width": 1280, "height": 720})
        window = TimeRange(start=0, end=measured.duration_ticks)
        clip = Clip(clip_id="recording", range=window, object=AudioObject(kind="audio", object_id="vo"),
                    source={"snapshot_id": measured.id, "snapshot_digest": measured.digest, "source_range": window})
        cues = await _resolve_aligned_caption_cues(db, await db.get(Project, project_id), content, clip)
        assert len(cues) >= 2 and " ".join(c["text"] for c in cues) == script
        for cue in cues:
            assert cue["caption"].alignment == "faster-whisper-source-v1"
            assert cue["caption"].snapshot_id == measured.id
            assert cue["word_timings"][-1]["end_s"] == (cue["output_end"] - cue["output_start"]) / 90000
