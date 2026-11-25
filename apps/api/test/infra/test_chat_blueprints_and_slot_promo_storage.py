"""Chat blueprints and slot promo — infra contracts."""
from __future__ import annotations

import hashlib
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.chat.editor import InsertAudioArgs, InsertMotionBlockArgs, edit_clip
from app.dependencies import get_current_user_required, get_db
from app.editing.store import apply_composition_edits, content_of
from app.editing.styles import CompositionStyle
from app.editing.timing import SOURCE_TIMEBASE, seconds_to_ticks
from app.main import app
from app.models.tables import (
    CompositionVersion,
    Conversation,
    Message,
    Project,
    SkillVersion,
    SourceSnapshot,
    User,
)
from app.skills.blueprint import (
    BLUEPRINT_CAPABILITY,
    BLUEPRINT_PATH,
    BlueprintAct,
    BlueprintActSlotInput,
    BlueprintAudioProfile,
    BlueprintOverlay,
    BlueprintSfxCue,
    BlueprintTransition,
    InstantiateSkillBlueprintArgs,
    SkillBlueprintV1,
    instantiate_skill_blueprint,
    load_blueprint_from_skill_version,
    music_clips_for_window,
    save_composition_as_skill,
)
from app.skills.external import SkillCapabilityReport, SkillDraft, SkillPolicy, SkillSource
from app.skills.resolution import list_available_skills
from app.skills.slot_preview import ALLOWED_FONT_FILENAMES, count_blueprint_slots
from app.skills.store import import_external_skill
from app.tools.video.preparation import canonical_resource
from test.support.blueprint_fixtures import _dig, _sample_master_composition
from test.support.db_helpers import _create, _project, _snapshots, _user

pytestmark = pytest.mark.infra


@pytest.mark.asyncio
async def test_stopped_turn_fences_save_and_instantiate_without_side_effects(database):
    from sqlalchemy import select as sa_select

    from app.chat.service import TurnStopped
    from app.models.tables import Composition, UserSkill

    content, origins, ids = _sample_master_composition()
    async with database() as db:
        owner = User(email=f"{uuid4()}@example.test", name="owner")
        db.add(owner)
        await db.flush()
        p_master = Project(id=uuid4(), user_id=owner.id, title="Master")
        p_remake = Project(id=uuid4(), user_id=owner.id, title="Stopped Remake")
        db.add_all([p_master, p_remake])
        await db.flush()
        for key, sid in ids.items():
            kind = "image" if key == "img" else "audio"
            meta = {"origin": {"kind": "sound_recipe", **origins[sid]}} if sid in origins else {}
            db.add(SourceSnapshot(
                id=sid,
                owner_id=owner.id,
                origin_project_id=p_master.id,
                kind=kind,
                digest=_dig(key),
                storage_key=f"test/{key}.bin",
                duration_ticks=seconds_to_ticks(24.0, SOURCE_TIMEBASE) if kind == "audio" else None,
                meta=meta,
            ))
        await db.flush()
        comp, ver, _ = await apply_composition_edits(
            db,
            owner_id=owner.id,
            origin_project_id=p_master.id,
            name="Master Promo",
            content=content.model_dump(mode="json"),
        )
        conv_master = Conversation(id=uuid4(), user_id=owner.id, project_id=p_master.id, title="Master Chat")
        stopped_save_opening = Message(
            id=uuid4(),
            conversation_id=conv_master.id,
            role="user",
            content="Save skill",
            turn_state="stopped",
            intent={},
        )
        conv_remake = Conversation(id=uuid4(), user_id=owner.id, project_id=p_remake.id, title="Remake Chat")
        stopped_inst_opening = Message(
            id=uuid4(),
            conversation_id=conv_remake.id,
            role="user",
            content="Instantiate skill",
            turn_state="stopped",
            intent={},
        )
        new_img = SourceSnapshot(
            id=uuid4(),
            owner_id=owner.id,
            origin_project_id=p_remake.id,
            kind="image",
            digest=_dig("stopped_img"),
            storage_key="remake/stopped.png",
            meta={"content_type": "image/png"},
        )
        db.add_all([conv_master, stopped_save_opening, conv_remake, stopped_inst_opening, new_img])
        await db.commit()

        # 1. Stopped turn blocks save_composition_as_skill before writing UserSkill
        with pytest.raises(TurnStopped):
            await save_composition_as_skill(
                db,
                owner_id=owner.id,
                project_id=p_master.id,
                composition_id=comp.id,
                version_id=ver.id,
                name="stopped-skill",
                description="Should not persist on a stopped turn.",
                opening_id=stopped_save_opening.id,
                conversation_id=conv_master.id,
            )
        assert await db.scalar(sa_select(UserSkill.id).where(UserSkill.owner_id == owner.id)) is None

        # Save legitimately (without stopped opening) so we have a valid skill_version_id for instantiate check
        saved_skill = await save_composition_as_skill(
            db,
            owner_id=owner.id,
            project_id=p_master.id,
            composition_id=comp.id,
            version_id=ver.id,
            name="valid-blueprint",
            description="Valid blueprint for stopped instantiate check.",
        )

    sfx_calls: list[str] = []

    async def should_not_run_sfx(*, owner_id, project_id, recipe_id, params=None, seed=None):
        sfx_calls.append(recipe_id)
        raise AssertionError("synthesize_project_sfx must not be called on a stopped turn")

    turn = SimpleNamespace(
        project=p_remake,
        turn_id=stopped_inst_opening.id,
        conversation_id=conv_remake.id,
    )
    inst_args = InstantiateSkillBlueprintArgs(
        skill_version_id=UUID(saved_skill["skill_version_id"]),
        name="Should Not Create",
        acts=[
            BlueprintActSlotInput(act_id="act_1", props={"headline": "A"}, duration_seconds=4.0),
            BlueprintActSlotInput(act_id="act_2", props={"url_bar": "a.test"}, resources=[new_img.id], duration_seconds=5.0),
            BlueprintActSlotInput(act_id="act_3", props={"items": [{"value": "1", "label": "X"}, {"value": "2", "label": "Y"}]}, duration_seconds=5.0),
            BlueprintActSlotInput(act_id="act_4", props={"brand_name": "B", "tagline": "T"}, duration_seconds=4.0),
        ],
    )

    with (
        patch("app.models.database.AsyncSessionLocal", database),
        patch("app.tools.video.sfx_synthesis.synthesize_project_sfx", side_effect=should_not_run_sfx),
    ):
        with pytest.raises(TurnStopped):
            await instantiate_skill_blueprint(turn=turn, args=inst_args, call_id="call_stopped_1")

    assert sfx_calls == []
    async with database() as db:
        assert await db.scalar(sa_select(Composition.id).where(Composition.origin_project_id == p_remake.id)) is None


def _make_all_13_blocks_blueprint() -> SkillBlueprintV1:
    acts = [
        BlueprintAct(
            act_id="act_1",
            block_id="statement_hook",
            role="opener",
            target_duration_s=4.0,
            min_duration_s=2.5,
            required_slots=["headline"],
            optional_slots=["subheadline"],
            transition_after=BlueprintTransition(kind="wipe_reveal", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_2",
            block_id="kinetic_title",
            role="title",
            target_duration_s=3.0,
            min_duration_s=2.0,
            required_slots=["headline"],
            optional_slots=["subheadline"],
        ),
        BlueprintAct(
            act_id="act_3",
            block_id="product_showcase",
            role="showcase",
            target_duration_s=6.0,
            min_duration_s=3.5,
            style_defaults={"camera_preset": "tilt_left", "chrome_mode": "browser"},
            required_slots=["image_resource"],
            optional_slots=["url_bar", "callout_steps"],
            callout_windows_s=[(1.0, 2.8), (3.1, 5.2)],
            cursor_click_at_s=2.0,
            overlays=[
                BlueprintOverlay(
                    overlay_id="act_3_overlay_1",
                    rel_start_s=0.6,
                    rel_end_s=3.4,
                    style_defaults={"surface_style": "pill_caption", "position": "bottom_left"},
                )
            ],
            transition_after=BlueprintTransition(kind="crossfade", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_4",
            block_id="device_mockup",
            role="showcase",
            target_duration_s=5.0,
            min_duration_s=3.0,
            style_defaults={"layout": "dual", "reveal_at_s": 1.2},
            required_slots=["image_resource", "mobile_image_resource"],
            transition_after=BlueprintTransition(kind="whip_pan", duration_s=0.4),
        ),
        BlueprintAct(
            act_id="act_5",
            block_id="chat_demo",
            role="demo",
            target_duration_s=6.0,
            min_duration_s=3.5,
            required_slots=["messages", "preview_resource"],
            optional_slots=["work_steps", "result_card"],
            item_reveals_s=[0.4, 1.4, 2.6, 3.6],
            secondary_reveals_s=[1.8, 2.2],
            transition_after=BlueprintTransition(kind="zoom_through", duration_s=0.4),
        ),
        BlueprintAct(
            act_id="act_6",
            block_id="metric_grid",
            role="metrics",
            target_duration_s=5.0,
            min_duration_s=3.0,
            required_slots=["items"],
            metric_reveals_s=[0.5, 1.1, 1.7],
            transition_after=BlueprintTransition(kind="iris_focus", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_7",
            block_id="bento_features",
            role="features",
            target_duration_s=5.0,
            min_duration_s=3.0,
            style_defaults={"highlight_index": 1},
            required_slots=["cards"],
            item_reveals_s=[0.4, 1.0, 1.6, 2.2],
            transition_after=BlueprintTransition(kind="crossfade", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_8",
            block_id="flow_diagram",
            role="workflow",
            target_duration_s=5.0,
            min_duration_s=3.0,
            required_slots=["nodes"],
            item_reveals_s=[0.4, 1.1, 1.8, 2.5],
            transition_after=BlueprintTransition(kind="wipe_reveal", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_9",
            block_id="step_timeline",
            role="roadmap",
            target_duration_s=5.0,
            min_duration_s=3.0,
            style_defaults={"active_step": 2},
            required_slots=["steps"],
            item_reveals_s=[0.5, 1.3, 2.1],
            transition_after=BlueprintTransition(kind="crossfade", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_10",
            block_id="split_compare",
            role="compare",
            target_duration_s=5.0,
            min_duration_s=3.0,
            style_defaults={"dim_left": True},
            required_slots=["left_heading", "left_items", "right_heading", "right_items"],
            item_reveals_s=[0.4, 1.0, 1.6],
            secondary_reveals_s=[0.8, 1.4, 2.0],
            transition_after=BlueprintTransition(kind="crossfade", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_11",
            block_id="data_chart",
            role="data",
            target_duration_s=5.0,
            min_duration_s=3.0,
            style_defaults={"chart_type": "bar", "highlight_index": 3},
            required_slots=["title", "points"],
            item_reveals_s=[0.5, 1.0, 1.5, 2.0],
            transition_after=BlueprintTransition(kind="crossfade", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_12",
            block_id="quote_proof",
            role="proof",
            target_duration_s=4.5,
            min_duration_s=3.0,
            style_defaults={"highlight_at_s": 1.2},
            required_slots=["quote", "author"],
            transition_after=BlueprintTransition(kind="crossfade", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_13",
            block_id="closing_cta",
            role="closing",
            target_duration_s=4.5,
            min_duration_s=3.0,
            required_slots=["brand_name", "tagline"],
        ),
    ]
    sfx_cues = [
        BlueprintSfxCue(cue_id="sfx_1", recipe_id="sub_swell", act_index=0, anchor="act_start", offset_s=0.0, gain_db=-12.0),
        BlueprintSfxCue(cue_id="sfx_2", recipe_id="callout_ping", act_index=2, anchor="act_start", offset_s=1.0, gain_db=-11.0),
        BlueprintSfxCue(cue_id="sfx_3", recipe_id="swoosh_cut", act_index=5, anchor="cut_after", offset_s=-0.15, gain_db=-12.0),
        BlueprintSfxCue(cue_id="sfx_4", recipe_id="stinger", act_index=12, anchor="act_start", offset_s=0.2, gain_db=-11.0),
    ]
    return SkillBlueprintV1(
        canvas={"width": 1920, "height": 1080, "fps_num": 30, "fps_den": 1, "background": "#0A0F16"},
        style=CompositionStyle(preset_id="vox_editorial"),
        acts=acts,
        audio_profile=BlueprintAudioProfile(has_bgm=False),
        sfx_cues=sfx_cues,
    )


def _make_6_act_blueprint() -> SkillBlueprintV1:
    full = _make_all_13_blocks_blueprint()
    picked_ids = {
        "product_showcase",
        "metric_grid",
        "bento_features",
        "data_chart",
        "quote_proof",
        "closing_cta",
    }
    acts = [a for a in full.acts if a.block_id in picked_ids]
    return SkillBlueprintV1(
        canvas=full.canvas,
        style=CompositionStyle(preset_id="vox_editorial"),
        acts=acts,
        audio_profile=BlueprintAudioProfile(),
        sfx_cues=[
            BlueprintSfxCue(cue_id="sfx_open", recipe_id="title_bloom", act_index=0, anchor="act_start", offset_s=0.0),
            BlueprintSfxCue(cue_id="sfx_cut", recipe_id="velvet_pass", act_index=1, anchor="cut_after", offset_s=-0.1),
            BlueprintSfxCue(cue_id="sfx_close", recipe_id="stinger", act_index=5, anchor="act_start", offset_s=0.2),
        ],
    )


def _skill_draft_for_blueprint(name: str, bp: SkillBlueprintV1) -> SkillDraft:
    bp_json = bp.model_dump_json(indent=2)
    bp_digest = hashlib.sha256(bp_json.encode("utf-8")).hexdigest()
    skill_md = f"---\nname: {name}\ndescription: Test blueprint\n---\nUse this template.\n"
    return SkillDraft(
        name=name,
        description="Test slot blueprint template",
        instructions=skill_md,
        references=[
            SkillSource(
                path=BLUEPRINT_PATH,
                role="reference",
                digest=bp_digest,
                text=bp_json,
            )
        ],
        media=[],
        declared_inputs=[],
        capability_report=SkillCapabilityReport(
            supported=[BLUEPRINT_CAPABILITY, "native_motion_graphics"]
        ),
        policy=SkillPolicy(),
        source_uri=f"composition://test-{name}@v1",
        source_revision="v1",
        source_hash=bp_digest,
    )


@pytest.mark.asyncio
async def test_skills_api_endpoints_owner_isolation_and_fonts(database, installed_promo, monkeypatch):
    owner = User(id=uuid4(), email="owner@example.com")
    other = User(id=uuid4(), email="other@example.com")
    bp = _make_6_act_blueprint()

    async with database() as db:
        db.add_all([owner, other])
        await db.flush()
        bp_ver, _ = await import_external_skill(
            db, owner_id=owner.id, draft=_skill_draft_for_blueprint("oxvalue-template", bp)
        )
        non_bp_draft = SkillDraft(
            name="plain-method",
            description="Plain instructions without blueprint",
            instructions="---\nname: plain-method\ndescription: Plain\n---\nInstructions.\n",
            references=[],
            media=[],
            declared_inputs=[],
            capability_report=SkillCapabilityReport(supported=["progressive_skill_package"]),
            policy=SkillPolicy(),
            source_uri="local://plain",
            source_revision="1",
            source_hash="c" * 64,
        )
        plain_ver, _ = await import_external_skill(db, owner_id=owner.id, draft=non_bp_draft)
        await db.commit()

        # The picker exposes the production methods and the external template summary.
        available = await list_available_skills(db, owner_id=owner.id)
        builtin_ids = {o.reference.skill_id for o in available if o.reference.kind == "builtin"}
        assert builtin_ids == {
            "kinetic-launch",
            "promo-video",
            "talking-head-video",
            "text-animation",
            "knowledge-explainer",
        }
        ext_bp = next(
            o for o in available
            if o.reference.kind == "external" and o.reference.skill_version_id == bp_ver.id
        )
        assert ext_bp.blueprint_summary is not None
        assert ext_bp.blueprint_summary.act_count == 6

    active_user = {"user": owner}

    async def override_db():
        async with database() as session:
            yield session

    async def override_user():
        return active_user["user"]

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user_required] = override_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            # 1. Font route: strict allowlist + immutable cache header
            for fname in ALLOWED_FONT_FILENAMES:
                r = await client.get(f"/api/v1/skills/fonts/{fname}")
                assert r.status_code == 200
                assert "immutable" in r.headers.get("cache-control", "")
                assert len(r.content) > 1000
            bad_font = await client.get("/api/v1/skills/fonts/OFL.txt")
            assert bad_font.status_code == 404
            traversal = await client.get("/api/v1/skills/fonts/..%2F..%2Fmain.py")
            assert traversal.status_code == 404

            # 2. Owner gets valid slot-preview JSON
            r = await client.get(
                f"/api/v1/skills/{bp_ver.id}/slot-preview",
                params={"style_preset": "institutional_dark", "locale": "en"},
            )
            assert r.status_code == 200
            payload = r.json()
            assert payload["style_preset"] == "institutional_dark"
            assert payload["locale"] == "en"
            assert payload["name"] == "oxvalue-template"
            assert len(payload["slots"]) == count_blueprint_slots(bp)
            assert payload["video_spec"]["fonts"][0]["url"].startswith("/api/v1/skills/fonts/")
            main_track = next(
                t for t in payload["video_spec"]["tracks"] if t["track_id"] == "trk_slot_main"
            )
            ps_clip = next(
                c for c in main_track["clips"] if c["object"]["block_id"] == "product_showcase"
            )
            assert ps_clip["object"]["resources"][0]["url"].startswith("data:image/png;base64,")

            # 3. Non-blueprint skill returns 400
            r_non_bp = await client.get(f"/api/v1/skills/{plain_ver.id}/slot-preview")
            assert r_non_bp.status_code == 400

            # 4. Missing UUID returns 404
            r_missing = await client.get(f"/api/v1/skills/{uuid4()}/slot-preview")
            assert r_missing.status_code == 404

            # 5. Foreign owner gets 404 (strict isolation)
            active_user["user"] = other
            r_foreign = await client.get(f"/api/v1/skills/{bp_ver.id}/slot-preview")
            assert r_foreign.status_code == 404

            # 6. Export endpoint: returns structured 503 when render service is unreachable
            active_user["user"] = owner

            class _FailingClient:
                def __init__(self, *args, **kwargs):
                    pass

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    return False

                async def post(self, *args, **kwargs):
                    raise httpx.ConnectError("render offline")

            monkeypatch.setattr("app.skills.routes.httpx.AsyncClient", _FailingClient)
            r_503 = await client.post(
                f"/api/v1/skills/{bp_ver.id}/slot-preview/export",
                json={"style_preset": "vox_editorial", "locale": "zh", "include_sfx": False},
            )
            assert r_503.status_code == 503
            assert "detail" in r_503.json()
    finally:
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def editor(database):
    owner = await _user(database)
    pid = await _project(database, owner)
    await _snapshots(database, owner)
    comp, ver, _ = await _create(database, owner, pid)
    async with database() as db:
        chat = Conversation(user_id=owner, project_id=pid)
        db.add(chat)
        await db.flush()
        opening = Message(conversation_id=chat.id, role="user", content="Edit", turn_state="in_flight")
        db.add(opening)
        await db.flush()

        async def insert(tool, args):
            result = await edit_clip(
                db, name=tool, project=await db.get(Project, pid), opening_id=opening.id,
                conversation_id=chat.id, call_id="insert", args=args,
                base={"composition_id": str(comp.id), "composition_version_id": str(ver.id),
                      "content_digest": ver.content_digest},
            )
            return content_of(await db.get(CompositionVersion, UUID(result["version_id"])))

        yield db, owner, pid, insert


@pytest.mark.asyncio
async def test_web_target_resolves_only_in_selected_view(editor):
    db, owner, pid, insert = editor
    view = {"view_id": "workflow", "width": 1600, "height": 900, "storage_key": "workflow.png",
            "digest": "b" * 64, "elements": [{"id": "row", "x": 0.53, "y": 0.7, "w": 0.24, "h": 0.03}]}
    home = {**view, "view_id": "home", "elements": [{"id": "hero"}]}
    web = SourceSnapshot(owner_id=owner, origin_project_id=pid, kind="web", storage_key="web.json", digest="a" * 64,
                         meta={"views": [home, view]})
    db.add(web)
    await db.flush()
    targets = canonical_resource(web)["views"]
    assert "box" not in targets[0]["targets"][0]
    box = targets[1]["targets"][0]["box"]
    assert box == [0.41, 0.685, 0.24, 0.03]
    args = InsertMotionBlockArgs(block_id="product_showcase", resources=[web.id], view_id="home",
                                 props={"callout": {"element_id": "row", "label": "Workflow"}},
                                 start_seconds=0, end_seconds=2)
    with pytest.raises(ValueError, match="row.*home"):
        await insert("insert_motion_block", args)
    content = await insert("insert_motion_block", args.model_copy(update={"view_id": "workflow"}))
    clip = next(t.clips[0] for t in content.timeline.tracks if t.track_id == "trk_mg_main")
    assert clip.object.props["callout"] == {"x": 0.41, "y": 0.685, "width": 0.24, "height": 0.03, "label": "Workflow"}


@pytest.mark.asyncio
async def test_insert_short_music_covers_requested_window_and_fades_at_ends(editor):
    db, owner, pid, insert = editor
    audio = SourceSnapshot(owner_id=owner, origin_project_id=pid, kind="audio", storage_key="music.mp3",
                           digest="b" * 64, duration_ticks=90000, meta={"origin": {"kind": "library_music"}})
    db.add(audio)
    await db.flush()
    content = await insert("insert_audio", InsertAudioArgs(source_id=audio.id, start_seconds=1,
                           duration_seconds=2.001, gain_db=-25, fade_in_seconds=0.2, fade_out_seconds=0.3))
    clips = next(t.clips for t in content.timeline.tracks if t.track_id == "trk_editor_music")
    assert [(c.range.start, c.range.end) for c in clips] == [(90000, 180000), (180000, 267000), (267000, 270090)]
    assert [(c.source.source_range.start, c.source.source_range.end) for c in clips] == [(0, 90000), (0, 87000), (0, 3090)]
    assert [c.object.gain_db for c in clips] == [-25] * 3
    assert not clips[1].animations
    for clip, endpoints in [(clips[0], (0, 1)), (clips[-1], (1, 0))]:
        animation, = clip.animations
        assert animation.property == "audio.gain"
        assert (animation.keyframes[0].value, animation.keyframes[-1].value) == endpoints


@pytest.mark.asyncio
async def test_saved_skill_keeps_fades_from_first_and_last_music_clips(editor):
    db, owner, pid, insert = editor
    content = await insert("insert_motion_block", InsertMotionBlockArgs(
        block_id="statement_hook", props={"headline": "Opening"}, start_seconds=0, end_seconds=4,
    ))
    track = next(t for t in content.timeline.tracks if t.role == "music")
    original, = track.clips
    track.clips = music_clips_for_window(
        settings=content.settings, start=0, end=original.range.end, source_ticks=90000,
        source_id=original.source.snapshot_id, digest=original.source.snapshot_digest,
        id_stem="loop", gain_db=-25, fade_in_seconds=0.2, fade_out_seconds=0.3,
    )[::-1]  # Storage order need not match playback order.
    comp, ver, _ = await apply_composition_edits(db, owner_id=owner, origin_project_id=pid, content=content)
    saved = await save_composition_as_skill(db, owner_id=owner, project_id=pid, composition_id=comp.id,
                                            version_id=ver.id, name="loop", description="Opening with looped music.")
    skill = await db.get(SkillVersion, UUID(saved["skill_version_id"]))
    profile = load_blueprint_from_skill_version(skill).audio_profile
    assert (profile.bgm_fade_in_s, profile.bgm_fade_out_s) == (0.2, 0.3)
