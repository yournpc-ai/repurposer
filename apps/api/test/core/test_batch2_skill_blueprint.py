"""Core contract tests for Batch 2 Checkpoint 2B (Skill + Slot Blueprint loop).

Covers:
1. Privacy-stripped deterministic blueprint extraction (no snapshot UUIDs or source copy).
2. Persistence into existing UserSkill / SkillVersion tables (0 new tables) + picker listing.
3. Instantiation: SFX synthesis strictly outside apply_composition_edits write lock,
   adaptive act duration from measured narration + breathing, re-anchored SFX, and
   full compile_video_spec validity.
"""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.editing.revisions import build_audio_gain_animation
from app.editing.schemas import (
    Animation,
    AudioObject,
    Clip,
    ClipSource,
    CompositionContent,
    LayoutBox,
    MotionBlockObject,
    RemotionResource,
    Scene,
    SourceBinding,
    TimeRange,
    Timeline,
    Track,
    Transition,
    VersionSettings,
)
from app.editing.store import apply_composition_edits, content_of
from app.editing.timing import SOURCE_TIMEBASE, seconds_to_ticks
from app.editing.video_spec import compile_video_spec
from app.models.database import Base
from app.models.tables import Conversation, Message, Project, SourceSnapshot, User
from app.skills.blueprint import (
    BLUEPRINT_PATH,
    BlueprintActSlotInput,
    InstantiateSkillBlueprintArgs,
    extract_skill_draft_from_composition,
    instantiate_skill_blueprint,
    save_composition_as_skill,
)
from app.skills.loading import load_skill_creative_context
from app.skills.resolution import list_available_skills
from app.skills.store import SkillNotFoundError, get_skill_version

def _dig(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


@pytest_asyncio.fixture
async def database():
    name = f"rep_bp_test_{uuid4().hex[:12]}"
    server = settings.database_url.rsplit("/", 1)[0]
    admin = create_async_engine(f"{server}/postgres", isolation_level="AUTOCOMMIT")
    async with admin.connect() as connection:
        await connection.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_async_engine(f"{server}/{name}")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin.connect() as connection:
            await connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        await admin.dispose()


def _sample_master_composition() -> tuple[CompositionContent, dict[UUID, dict], dict[str, UUID]]:
    """Build a 4-act master composition with overlay, crossfade, BGM fades, and 2 SFX cues."""
    settings_obj = VersionSettings(width=1920, height=1080, fps={"num": 30, "den": 1}, background="#070B11")
    tb = settings_obj.timebase
    ids = {
        "img": uuid4(),
        "vo1": uuid4(),
        "vo2": uuid4(),
        "bgm": uuid4(),
        "sfx_cut": uuid4(),
        "sfx_end": uuid4(),
    }
    t0 = 0
    t1 = seconds_to_ticks(5.0, tb)
    t2 = seconds_to_ticks(12.0, tb)
    t3 = seconds_to_ticks(19.0, tb)
    t4 = seconds_to_ticks(24.0, tb)

    bgm_anim = Animation.model_validate(
        build_audio_gain_animation(
            object_id="obj_bgm",
            clip_start_ticks=0,
            clip_end_ticks=t4,
            timebase=tb,
            fps_num=30,
            fps_den=1,
            fade_in_seconds=1.2,
            fade_out_seconds=2.0,
        )
    )

    content = CompositionContent(
        settings=settings_obj,
        sources=[SourceBinding(snapshot_id=sid, snapshot_digest=_dig(k)) for k, sid in ids.items()],
        scenes=[
            Scene(scene_id="scene_1", range=TimeRange(start=t0, end=t1)),
            Scene(scene_id="scene_2", range=TimeRange(start=t1, end=t2)),
            Scene(scene_id="scene_3", range=TimeRange(start=t2, end=t3)),
            Scene(scene_id="scene_4", range=TimeRange(start=t3, end=t4)),
        ],
        timeline=Timeline(
            tracks=[
                Track(
                    track_id="trk_main",
                    kind="visual",
                    role="main",
                    order=0,
                    clips=[
                        Clip(
                            clip_id="clp_1",
                            range=TimeRange(start=t0, end=t1),
                            scene_id="scene_1",
                            object=MotionBlockObject(
                                kind="motion_block",
                                object_id="obj_1",
                                block_id="statement_hook",
                                block_version=1,
                                props={
                                    "eyebrow": "SECRET_MASTER_EYEBROW",
                                    "headline": "SECRET_MASTER_HEADLINE",
                                    "highlight_phrase": "SECRET",
                                    "theme": "dark",
                                    "accent_color": "#0F766E",
                                    "show_backdrop": True,
                                },
                                layout=LayoutBox(x=0, y=0, width=1920, height=1080),
                                fit="cover",
                            ),
                        ),
                        Clip(
                            clip_id="clp_2",
                            range=TimeRange(start=t1, end=t2),
                            scene_id="scene_2",
                            object=MotionBlockObject(
                                kind="motion_block",
                                object_id="obj_2",
                                block_id="product_showcase",
                                block_version=1,
                                props={
                                    "url_bar": "secret-master.example",
                                    "badge": "SECRET_BADGE",
                                    "theme": "light",
                                    "chrome_mode": "browser",
                                    "camera_motion": "drift_focus",
                                    "show_backdrop": True,
                                },
                                resources=[
                                    RemotionResource(
                                        path="media/master.png",
                                        snapshot_id=ids["img"],
                                        snapshot_digest=_dig("img"),
                                        content_type="image/png",
                                    )
                                ],
                                layout=LayoutBox(x=0, y=0, width=1920, height=1080),
                                fit="cover",
                            ),
                        ),
                        Clip(
                            clip_id="clp_3",
                            range=TimeRange(start=t2, end=t3),
                            scene_id="scene_3",
                            object=MotionBlockObject(
                                kind="motion_block",
                                object_id="obj_3",
                                block_id="metric_grid",
                                block_version=1,
                                props={
                                    "eyebrow": "SECRET_METRICS",
                                    "title": "SECRET_TITLE",
                                    "items": [
                                        {"value": "99%", "label": "Secret Metric A"},
                                        {"value": "10x", "label": "Secret Metric B"},
                                    ],
                                    "columns": 2,
                                    "theme": "light",
                                    "show_backdrop": True,
                                },
                                layout=LayoutBox(x=0, y=0, width=1920, height=1080),
                                fit="cover",
                            ),
                        ),
                        Clip(
                            clip_id="clp_4",
                            range=TimeRange(start=t3, end=t4),
                            scene_id="scene_4",
                            object=MotionBlockObject(
                                kind="motion_block",
                                object_id="obj_4",
                                block_id="closing_cta",
                                block_version=1,
                                props={
                                    "brand_name": "SECRET_BRAND",
                                    "tagline": "SECRET_TAGLINE",
                                    "cta_label": "SECRET_CTA",
                                    "url_text": "secret.example",
                                    "theme": "dark",
                                    "logo_surface": "light_pill",
                                    "show_backdrop": True,
                                },
                                layout=LayoutBox(x=0, y=0, width=1920, height=1080),
                                fit="cover",
                            ),
                        ),
                    ],
                ),
                Track(
                    track_id="trk_title",
                    kind="visual",
                    role="title",
                    order=1,
                    clips=[
                        Clip(
                            clip_id="clp_ov_2",
                            range=TimeRange(
                                start=seconds_to_ticks(5.6, tb),
                                end=seconds_to_ticks(11.4, tb),
                            ),
                            scene_id="scene_2",
                            object=MotionBlockObject(
                                kind="motion_block",
                                object_id="obj_ov_2",
                                block_id="kinetic_title",
                                block_version=1,
                                props={
                                    "headline": "SECRET_PILL_TEXT",
                                    "surface_style": "pill_caption",
                                    "position": "bottom_left",
                                    "accent_color": "#0F766E",
                                },
                                layout=LayoutBox(x=0, y=0, width=1920, height=1080),
                                fit="cover",
                            ),
                        ),
                    ],
                ),
                Track(
                    track_id="trk_vo",
                    kind="audio",
                    role="dialogue",
                    order=0,
                    clips=[
                        Clip(
                            clip_id="clp_vo_1",
                            range=TimeRange(start=seconds_to_ticks(0.2, tb), end=seconds_to_ticks(4.5, tb)),
                            source=ClipSource(
                                snapshot_id=ids["vo1"],
                                snapshot_digest=_dig("vo1"),
                                source_range=TimeRange(start=0, end=seconds_to_ticks(4.3, SOURCE_TIMEBASE)),
                            ),
                            object=AudioObject(kind="audio", object_id="obj_vo_1", gain_db=0.0),
                        ),
                    ],
                ),
                Track(
                    track_id="trk_bgm",
                    kind="audio",
                    role="music",
                    order=1,
                    clips=[
                        Clip(
                            clip_id="clp_bgm",
                            range=TimeRange(start=0, end=t4),
                            source=ClipSource(
                                snapshot_id=ids["bgm"],
                                snapshot_digest=_dig("bgm"),
                                source_range=TimeRange(start=0, end=seconds_to_ticks(24.0, SOURCE_TIMEBASE)),
                            ),
                            object=AudioObject(kind="audio", object_id="obj_bgm", gain_db=-25.0),
                            animations=[bgm_anim],
                        ),
                    ],
                ),
                Track(
                    track_id="trk_sfx",
                    kind="audio",
                    role="effect",
                    order=2,
                    clips=[
                        Clip(
                            clip_id="clp_sfx_1",
                            range=TimeRange(
                                start=seconds_to_ticks(4.85, tb),
                                end=seconds_to_ticks(5.2, tb),
                            ),
                            source=ClipSource(
                                snapshot_id=ids["sfx_cut"],
                                snapshot_digest=_dig("sfx_cut"),
                                source_range=TimeRange(start=0, end=seconds_to_ticks(0.35, SOURCE_TIMEBASE)),
                            ),
                            object=AudioObject(kind="audio", object_id="obj_sfx_1", gain_db=-13.0),
                        ),
                        Clip(
                            clip_id="clp_sfx_2",
                            range=TimeRange(
                                start=seconds_to_ticks(19.1, tb),
                                end=seconds_to_ticks(20.1, tb),
                            ),
                            source=ClipSource(
                                snapshot_id=ids["sfx_end"],
                                snapshot_digest=_dig("sfx_end"),
                                source_range=TimeRange(start=0, end=seconds_to_ticks(1.0, SOURCE_TIMEBASE)),
                            ),
                            object=AudioObject(kind="audio", object_id="obj_sfx_2", gain_db=-11.5),
                        ),
                    ],
                ),
            ],
            transitions=[
                Transition(
                    transition_id="trn_1_2",
                    from_clip_id="clp_1",
                    to_clip_id="clp_2",
                    kind="crossfade",
                    duration=seconds_to_ticks(0.4, tb),
                    alignment="center",
                ),
            ],
        ),
    )
    origins = {
        ids["sfx_cut"]: {"recipe_id": "swoosh_cut", "params": {"length": 0.35}, "seed": 111},
        ids["sfx_end"]: {"recipe_id": "stinger", "params": {"pitch": 62}, "seed": 222},
    }
    return content, origins, ids


def test_extract_skill_draft_strips_private_snapshots_and_copy():
    content, origins, ids = _sample_master_composition()
    comp_id = uuid4()
    draft, bp = extract_skill_draft_from_composition(
        composition_id=comp_id,
        version_number=40,
        content=content,
        snapshot_origins=origins,
        name="OxValue Promo Blueprint!",
        description="4-act commercial studio promo structure.",
    )
    assert draft.name == "oxvalue-promo-blueprint"
    assert len(bp.acts) == 4
    assert [a.block_id for a in bp.acts] == [
        "statement_hook",
        "product_showcase",
        "metric_grid",
        "closing_cta",
    ]
    assert bp.acts[0].transition_after is not None
    assert bp.acts[0].transition_after.duration_s == pytest.approx(0.4, abs=0.01)
    assert len(bp.acts[1].overlays) == 1
    assert bp.acts[1].overlays[0].style_defaults["surface_style"] == "pill_caption"
    assert bp.audio_profile.has_bgm is True
    assert bp.audio_profile.bgm_fade_in_s == pytest.approx(1.2, abs=0.05)
    assert bp.audio_profile.bgm_fade_out_s == pytest.approx(2.0, abs=0.05)
    assert len(bp.sfx_cues) == 2
    assert bp.sfx_cues[0].recipe_id == "swoosh_cut"
    assert bp.sfx_cues[0].act_index == 0 and bp.sfx_cues[0].anchor == "cut_after"
    assert bp.sfx_cues[0].offset_s == pytest.approx(-0.15, abs=0.01)
    assert bp.sfx_cues[1].recipe_id == "stinger"
    assert (bp.sfx_cues[1].act_index, bp.sfx_cues[1].anchor) in {(2, "cut_after"), (3, "act_start")}
    assert bp.sfx_cues[1].offset_s == pytest.approx(0.1, abs=0.01)

    # Zero private snapshot UUIDs or master copy/metrics leak into SKILL.md or blueprint.json
    bp_text = draft.references[0].text
    combined = draft.instructions + "\n" + bp_text
    for sid in ids.values():
        assert str(sid) not in combined
    for secret in ("SECRET_MASTER_HEADLINE", "SECRET_BADGE", "SECRET_METRICS", "SECRET_BRAND", "SECRET_PILL_TEXT"):
        assert secret not in combined


@pytest.mark.asyncio
async def test_save_composition_as_skill_persists_and_lists_in_picker(database):
    content, origins, ids = _sample_master_composition()
    async with database() as db:
        owner = User(email=f"{uuid4()}@example.test", name="owner")
        other = User(email=f"{uuid4()}@example.test", name="other")
        db.add_all([owner, other])
        await db.flush()
        proj = Project(id=uuid4(), user_id=owner.id, title="Master Project")
        db.add(proj)
        await db.flush()
        # Persist referenced SourceSnapshots (including sound_recipe origins)
        for key, sid in ids.items():
            kind = "image" if key == "img" else "audio"
            meta = {"origin": {"kind": "sound_recipe", **origins[sid]}} if sid in origins else {}
            db.add(SourceSnapshot(
                id=sid,
                owner_id=owner.id,
                origin_project_id=proj.id,
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
            origin_project_id=proj.id,
            name="Master Promo",
            content=content.model_dump(mode="json"),
        )
        await db.commit()

        saved1 = await save_composition_as_skill(
            db,
            owner_id=owner.id,
            project_id=proj.id,
            composition_id=comp.id,
            version_id=ver.id,
            name="oxvalue-promo-blueprint",
            description="Reusable 4-act studio promo.",
        )
        assert saved1["saved"] is True and saved1["reused"] is False
        assert saved1["acts_count"] == 4 and saved1["sfx_cues_count"] == 2

        # Idempotent replay returns identical SkillVersion
        saved2 = await save_composition_as_skill(
            db,
            owner_id=owner.id,
            project_id=proj.id,
            composition_id=comp.id,
            version_id=ver.id,
            name="oxvalue-promo-blueprint",
            description="Reusable 4-act studio promo.",
        )
        assert saved2["reused"] is True
        assert saved2["skill_version_id"] == saved1["skill_version_id"]

        # Visible immediately in / SkillPicker for owner, invisible to other user
        owner_skills = await list_available_skills(db, owner_id=owner.id)
        found = [s for s in owner_skills if s.name == "oxvalue-promo-blueprint"]
        assert len(found) == 1
        assert "slot_blueprint_v1" in found[0].capabilities
        other_skills = await list_available_skills(db, owner_id=other.id)
        assert not [s for s in other_skills if s.name == "oxvalue-promo-blueprint"]
        with pytest.raises(SkillNotFoundError):
            await get_skill_version(db, owner_id=other.id, skill_version_id=UUID(saved1["skill_version_id"]))

        # Progressive Skill package reader reads both SKILL.md and references/blueprint.json cleanly
        from app.skills.package_session import ReadSkillReferenceArgs

        ctx = await load_skill_creative_context(
            db, owner_id=owner.id, skill_version_id=UUID(saved1["skill_version_id"])
        )
        obs = await ctx.package.observe("read_skill_reference", ReadSkillReferenceArgs(path=BLUEPRINT_PATH))
        assert obs.ok
        envelope = json.loads(obs.text)
        parsed = json.loads(envelope["text"]) if "text" in envelope else envelope
        assert parsed["schema_version"] == 1 and len(parsed["acts"]) == 4


@pytest.mark.asyncio
async def test_instantiate_skill_blueprint_sfx_outside_write_lock_and_adaptive_timing(database):
    content, origins, ids = _sample_master_composition()
    async with database() as db:
        owner = User(email=f"{uuid4()}@example.test", name="owner")
        db.add(owner)
        await db.flush()
        p_master = Project(id=uuid4(), user_id=owner.id, title="Master")
        p_remake = Project(id=uuid4(), user_id=owner.id, title="Chinese Remake")
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
        await db.commit()
        saved_skill = await save_composition_as_skill(
            db,
            owner_id=owner.id,
            project_id=p_master.id,
            composition_id=comp.id,
            version_id=ver.id,
            name="oxvalue-promo-blueprint",
            description="Reusable 4-act studio promo.",
        )

        # Fresh remake assets: longer Chinese Act 1 narration (7.0s -> act should widen from 5.0s to ~7.5s!)
        new_img = SourceSnapshot(
            id=uuid4(),
            owner_id=owner.id,
            origin_project_id=p_remake.id,
            kind="image",
            digest=_dig("new_img"),
            storage_key="remake/platform.png",
            meta={"content_type": "image/png"},
        )
        new_vo1 = SourceSnapshot(
            id=uuid4(),
            owner_id=owner.id,
            origin_project_id=p_remake.id,
            kind="audio",
            digest=_dig("new_vo1"),
            storage_key="remake/vo1.mp3",
            duration_ticks=seconds_to_ticks(7.0, SOURCE_TIMEBASE),
        )
        new_vo2 = SourceSnapshot(
            id=uuid4(),
            owner_id=owner.id,
            origin_project_id=p_remake.id,
            kind="audio",
            digest=_dig("new_vo2"),
            storage_key="remake/vo2.mp3",
            duration_ticks=seconds_to_ticks(5.2, SOURCE_TIMEBASE),
        )
        new_bgm = SourceSnapshot(
            id=uuid4(),
            owner_id=owner.id,
            origin_project_id=p_remake.id,
            kind="audio",
            digest=_dig("new_bgm"),
            storage_key="remake/bgm.mp3",
            duration_ticks=seconds_to_ticks(45.0, SOURCE_TIMEBASE),
        )
        conv = Conversation(id=uuid4(), user_id=owner.id, project_id=p_remake.id, title="Remake")
        opening = Message(
            id=uuid4(),
            conversation_id=conv.id,
            role="user",
            content="用蓝图复刻中文版",
            turn_state="in_flight",
            intent={},
        )
        db.add_all([new_img, new_vo1, new_vo2, new_bgm, conv, opening])
        await db.commit()

    events: list[str] = []

    async def fake_synthesize_sfx(*, owner_id, project_id, recipe_id, params=None, seed=None):
        events.append(f"sfx:{recipe_id}")
        sid = uuid4()
        dig = _dig(f"sfx_{recipe_id}_{sid}")
        async with database() as sfx_db:
            snap = SourceSnapshot(
                id=sid,
                owner_id=owner_id,
                origin_project_id=project_id,
                kind="audio",
                digest=dig[:64],
                storage_key=f"remake/sfx_{recipe_id}.wav",
                duration_ticks=seconds_to_ticks(0.4, SOURCE_TIMEBASE),
                meta={"origin": {"kind": "sound_recipe", "recipe_id": recipe_id, "params": params or {}, "seed": seed}},
            )
            sfx_db.add(snap)
            await sfx_db.commit()
        return {
            "snapshot": {"snapshot_id": str(sid), "digest": snap.digest},
            "audio_snapshot_id": str(sid),
            "audio_digest": snap.digest,
            "duration_seconds": 0.4,
            "acoustics": {"duration_ms": 400, "peak_offset_ms": 120, "peak_dbfs": -2.0},
        }

    orig_apply = apply_composition_edits

    async def spy_apply(*args, **kwargs):
        events.append("apply_composition_edits")
        return await orig_apply(*args, **kwargs)

    turn = SimpleNamespace(
        project=p_remake,
        turn_id=opening.id,
        conversation_id=conv.id,
    )
    inst_args = InstantiateSkillBlueprintArgs(
        skill_version_id=UUID(saved_skill["skill_version_id"]),
        name="OxValue 中文技术转移宣传片",
        bgm_snapshot_id=new_bgm.id,
        acts=[
            BlueprintActSlotInput(
                act_id="act_1",
                props={"eyebrow": "牛津技术转移", "headline": "让早期硬科技估值有据可依", "highlight_phrase": "有据可依"},
                narration_snapshot_id=new_vo1.id,
            ),
            BlueprintActSlotInput(
                act_id="act_2",
                props={"url_bar": "agent.oxvalue.ai/platform", "badge": "核心平台"},
                resources=[new_img.id],
                narration_snapshot_id=new_vo2.id,
                overlay_props={"headline": "全链路技术估值与治理看板"},
            ),
            BlueprintActSlotInput(
                act_id="act_3",
                props={
                    "eyebrow": "核心指标",
                    "title": "以可验证数据支撑每一次定价",
                    "items": [
                        {"value": "4", "label": "全流程估值环节"},
                        {"value": "100%", "label": "完整审计溯源"},
                    ],
                },
                duration_seconds=5.5,
            ),
            BlueprintActSlotInput(
                act_id="act_4",
                props={
                    "brand_name": "OxValue.AI",
                    "tagline": "面向大学技术转移与治理团队的智能估值平台",
                    "cta_label": "预约中文演示",
                    "url_text": "agent.oxvalue.ai",
                },
                duration_seconds=4.5,
            ),
        ],
    )

    with (
        patch("app.models.database.AsyncSessionLocal", database),
        patch("app.tools.video.sfx_synthesis.synthesize_project_sfx", side_effect=fake_synthesize_sfx),
        patch("app.skills.blueprint.apply_composition_edits", side_effect=spy_apply),
    ):
        res = await instantiate_skill_blueprint(turn=turn, args=inst_args, call_id="call_bp_1")

    # Guardrail #2: every SFX synthesis strictly precedes apply_composition_edits!
    assert events == ["sfx:swoosh_cut", "sfx:stinger", "apply_composition_edits"]

    # Adaptive timing: Act 1 widened from 5.0s baseline to 7.0 + 0.5 = 7.5s; Act 2 = 5.2 + 0.5 = 5.7s
    assert res["acts"][0]["start_seconds"] == pytest.approx(0.0, abs=0.05)
    assert res["acts"][0]["end_seconds"] == pytest.approx(7.5, abs=0.05)
    assert res["acts"][1]["start_seconds"] == pytest.approx(7.5, abs=0.05)
    assert res["acts"][1]["end_seconds"] == pytest.approx(13.2, abs=0.05)
    assert res["transitions_count"] == 1
    assert res["sfx_clips_count"] == 2

    # Inspect persisted CompositionVersion: re-anchored SFX, zero master copy, valid compile_video_spec
    async with database() as db:
        from app.editing.store import get_video_version

        _, saved_ver = await get_video_version(db, owner_id=owner.id, version_id=UUID(res["version_id"]))
        remake_content = content_of(saved_ver)
        tb = remake_content.settings.timebase
        dumped = json.dumps(remake_content.model_dump(mode="json"), ensure_ascii=False)
        assert "SECRET_MASTER_HEADLINE" not in dumped
        assert "让早期硬科技估值有据可依" in dumped
        assert "全链路技术估值与治理看板" in dumped

        # Verify swoosh_cut shifted from 4.85s (master) to 7.5 - 0.15 = 7.35s (adapted cut_after act 1!)
        sfx_clips = [
            c
            for t in remake_content.timeline.tracks
            if t.kind == "audio" and t.role == "effect"
            for c in t.clips
        ]
        assert len(sfx_clips) == 2
        assert sfx_clips[0].range.start / tb == pytest.approx(7.35, abs=0.05)
        # Verify stinger shifted to Act 4 start (7.5 + 5.7 + 5.5 = 18.7) + 0.1 = 18.8s
        assert sfx_clips[1].range.start / tb == pytest.approx(18.8, abs=0.05)

        # Compiles cleanly to VideoSpec!
        sources_map = {}
        for binding in remake_content.sources:
            sources_map[binding.snapshot_id] = {
                "kind": "image" if binding.snapshot_id == new_img.id else "audio",
                "url": f"https://example.invalid/{binding.snapshot_id}",
                "storage_key": f"k/{binding.snapshot_id}",
                "digest": binding.snapshot_digest,
            }
        spec = compile_video_spec(
            remake_content,
            sources_map,
            composition_id=saved_ver.composition_id,
            version_id=saved_ver.id,
            content_digest=saved_ver.content_digest,
        )
        assert len(spec["tracks"]) >= 4
