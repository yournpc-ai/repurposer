"""Layer 1A Chat-Origin: save_composition_as_skill, instantiate_skill_blueprint, slot-preview API, and multi-act template remakes."""

from __future__ import annotations
import pytest

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

    # Zero private snapshot UUIDs, master composition_id, or master copy/metrics leak into SKILL.md or blueprint.json
    bp_text = draft.references[0].text
    combined = draft.instructions + "\n" + bp_text
    assert draft.source_uri == f"composition://{comp_id}@v40"
    assert str(comp_id) not in combined
    assert "source_composition_uri" not in bp_text
    for sid in ids.values():
        assert str(sid) not in combined
    for secret in ("SECRET_MASTER_HEADLINE", "SECRET_BADGE", "SECRET_METRICS", "SECRET_BRAND", "SECRET_PILL_TEXT"):
        assert secret not in combined

    # Backward-compatible deserialization when legacy blueprint.json carries source_composition_uri
    from app.skills.blueprint import SkillBlueprintV1

    legacy = json.loads(bp_text)
    legacy["source_composition_uri"] = f"composition://{comp_id}@v40"
    parsed_legacy = SkillBlueprintV1.model_validate(legacy)
    assert parsed_legacy.source_composition_uri == f"composition://{comp_id}@v40"


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
            duration_ticks=seconds_to_ticks(8.0, SOURCE_TIMEBASE),
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
        music = next(t["clips"] for t in spec["tracks"] if t["track_id"] == "trk_editor_music")
        assert [(c["start_frame"], c["end_frame"]) for c in music] == [
            (0, 240), (240, 480), (480, spec["duration_frames"]),
        ]
        assert [len(c["animations"]) for c in music] == [1, 0, 1]


    # Replay short-circuit: same (turn_id, call_id, args) returns saved version WITHOUT calling SFX or apply
    events.clear()
    with (
        patch("app.models.database.AsyncSessionLocal", database),
        patch("app.tools.video.sfx_synthesis.synthesize_project_sfx", side_effect=fake_synthesize_sfx),
        patch("app.skills.blueprint.apply_composition_edits", side_effect=spy_apply),
    ):
        replayed = await instantiate_skill_blueprint(turn=turn, args=inst_args, call_id="call_bp_1")
    assert events == []
    assert replayed["version_id"] == res["version_id"]
    assert replayed["composition_id"] == res["composition_id"]
    assert replayed["sfx_clips_count"] == 2


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


# --- HTTP /api/v1/skills, /slot-preview & font allowlist ---

import hashlib


import io


import json


import subprocess


from pathlib import Path


from types import SimpleNamespace


from uuid import UUID, uuid4


import httpx


import pytest


from httpx import ASGITransport, AsyncClient


from PIL import Image


from app.chat.activity_receipts import skill_saved_receipt


from app.dependencies import get_current_user_required, get_db


from app.editing.catalog import MOTION_BLOCK_CATALOG


from app.editing.styles import CompositionStyle, STYLE_PRESETS


from app.editing.timing import SOURCE_TIMEBASE, seconds_to_ticks


from app.main import app


from app.models.tables import User


from app.skills import SKILL_REGISTRY


from app.skills.blueprint import (
    BLUEPRINT_CAPABILITY,
    BLUEPRINT_PATH,
    BlueprintAct,
    BlueprintAudioProfile,
    BlueprintOverlay,
    BlueprintSfxCue,
    BlueprintTransition,
    SkillBlueprintV1,
)


from app.skills.external import (
    SkillCapabilityReport,
    SkillDraft,
    SkillPolicy,
    SkillSource,
)


from app.skills.resolution import (
    _external_option,
    get_builtin_skill_option,
    list_available_skills,
)


from app.skills.slot_preview import (
    ALLOWED_FONT_FILENAMES,
    build_slot_preview_video_spec,
    compile_blueprint_slot_preview,
    count_blueprint_slots,
    format_slot_checklist,
)


from app.skills.store import import_external_skill


REPO_ROOT = Path(__file__).resolve().parents[4]


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

        # Verify list_available_skills returns all 4 builtins + blueprint_summary on external
        available = await list_available_skills(db, owner_id=owner.id)
        builtin_ids = {o.reference.skill_id for o in available if o.reference.kind == "builtin"}
        assert builtin_ids == {
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


# --- 60-second 24-act template remake ---

from types import SimpleNamespace


from uuid import UUID


import pytest


from pydantic import ValidationError


from app.chat.editor import SetTransitionArgs


from app.editing.schemas import CompositionContent, ProductShowcaseProps


from app.editing.store import apply_composition_edits, content_of, get_video_version, snapshot_facts


from app.editing.video_spec import compile_video_spec


from app.models.tables import Conversation, Message, Project, SkillVersion, SourceSnapshot


from app.skills.blueprint import (
    InstantiateSkillBlueprintArgs, SkillBlueprintV1, instantiate_skill_blueprint, save_composition_as_skill,
)


from test.support.db_helpers import _project, _user


@pytest.mark.asyncio
async def test_sixty_second_template_rebinds_targets_and_retains_cadence(database, monkeypatch):
    owner = await _user(database)
    master_id = await _project(database, owner, title="Master")
    remake_id = await _project(database, owner, title="Remake")
    kinds = ["crossfade", "whip_pan", "wipe_reveal", "zoom_through", "iris_focus"]
    async with database() as db:
        master_image = SourceSnapshot(owner_id=owner, origin_project_id=master_id, kind="image",
                                      digest="a" * 64, storage_key="master-private.png")
        target = SourceSnapshot(owner_id=owner, origin_project_id=remake_id, kind="web",
                                digest="b" * 64, storage_key="new-web.json", meta={"views": [{
                                    "view_id": "register", "width": 1600, "height": 900,
                                    "digest": "c" * 64, "storage_key": "new-register.png",
                                    "elements": [
                                        dict(id="row", x=.3, y=.48, w=.2, h=.08),
                                        dict(id="action", x=.72, y=.64, w=.12, h=.04),
                                    ],
                                }]})
        project = await db.get(Project, remake_id)
        chat = Conversation(user_id=owner, project_id=remake_id)
        db.add_all([master_image, target, chat])
        await db.flush()
        opening = Message(conversation_id=chat.id, role="user", content="Remake", turn_state="in_flight")
        db.add(opening)
        await db.flush()
        turn = SimpleNamespace(project=project, conversation_id=chat.id, turn_id=opening.id)

        # 24 acts × 2.5s also exercises the actual input and persisted Skill package size limits.
        clips, slots, transitions = [], [], []
        private_box = dict(x=.123456, y=.234567, width=.19, height=.12)
        cuts = [i * 225000 + (i % 2) * 900 for i in range(25)]
        for i in range(24):
            block, props, replacement = "statement_hook", {"headline": "PRIVATE_COPY"}, {"headline": "New hook"}
            resources = []
            slot = {}
            if i == 0:
                props.update(highlight_phrase="COPY", highlight_at_s=.73, backdrop_style="editorial_paper")
            if i == 1:
                block = "product_showcase"
                props = dict(camera_preset="tilt_left", scroll_from_y=.1, scroll_to_y=.8,
                             backdrop_style="architectural_grid", url_bar="PRIVATE_HOST",
                             cursor=dict(x=.345678, y=.456789, start_x=.187654, click_at_s=1.7),
                             callout_steps=[dict(**private_box, start_s=a, end_s=b, label="PRIVATE_LABEL")
                                            for a, b in [(0.1, 1.1), (1.25, 2.4)]])
                resources = [dict(path="media/private.png", snapshot_id=master_image.id,
                                  snapshot_digest=master_image.digest, content_type="image/png")]
                replacement = dict(cursor={"element_id": "action"}, callout_steps=[
                    dict(element_id="row", label="Review"), dict(element_id="action", label="Open")])
                slot = dict(resources=[target.id], view_id="register")
            if i == 2:
                block = "metric_grid"
                props = dict(items=[dict(value="PRIVATE", label="A", reveal_at_s=.2),
                                    dict(value="PRIVATE", label="B", reveal_at_s=1.6)])
                replacement = dict(items=[dict(value="1", label="First"), dict(value="2", label="Second")])
            slots.append(dict(props=replacement, **slot))
            clips.append(dict(clip_id=f"clp_{i}", range=dict(start=cuts[i], end=cuts[i+1]),
                              object=dict(kind="motion_block", block_id=block, object_id=f"obj_{i}",
                                          props=props, resources=resources, fit="cover",
                                          layout=dict(x=0, y=0, width=1920, height=1080))))
            if 0 < i <= len(kinds):
                transitions.append(dict(transition_id=f"tr_{i}", kind=kinds[i-1], duration=39900,
                                        from_clip_id=f"clp_{i-1}", to_clip_id=f"clp_{i}"))
        master = CompositionContent.model_validate(dict(settings=dict(width=1920, height=1080),
            sources=[dict(snapshot_id=master_image.id, snapshot_digest=master_image.digest)], scenes=[],
            timeline=dict(tracks=[dict(track_id="main", kind="visual", role="main", order=0, clips=clips)],
                          transitions=transitions)))
        comp, version, _ = await apply_composition_edits(db, owner_id=owner, origin_project_id=master_id, content=master)
        saved = await save_composition_as_skill(db, owner_id=owner, project_id=master_id,
            composition_id=comp.id, version_id=version.id, name="research-template", description="Reusable brief.")
        skill = await db.get(SkillVersion, UUID(saved["skill_version_id"]))
        raw = skill.references[0]["text"]
        for secret in ("PRIVATE", str(master_image.id), master_image.storage_key, ".123456", ".234567",
                       ".345678", ".456789", ".187654"):
            assert secret not in raw
        bp = SkillBlueprintV1.model_validate_json(raw)
        assert {"cursor", "callout_steps"} <= set(bp.acts[1].optional_slots)
        # An old v1 act has no cue metadata or transition kind.
        legacy = {"canvas": bp.canvas, "acts": [{"act_id": "act_1", "block_id": "statement_hook",
                  "role": "opener", "target_duration_s": 3, "min_duration_s": 2,
                  "transition_after": {"duration_s": .4}}]}
        assert SkillBlueprintV1.model_validate(legacy).acts[0].transition_after.kind == "crossfade"

    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    result = await instantiate_skill_blueprint(turn=turn, call_id="remake", args=InstantiateSkillBlueprintArgs(
        skill_version_id=skill.id, name="New research brief", acts=slots))
    async with database() as db:
        _, version = await get_video_version(db, owner_id=owner, version_id=UUID(result["version_id"]))
        content = content_of(version)
        facts = await snapshot_facts(db, {s.snapshot_id for s in content.sources})
        spec = compile_video_spec(content, facts, composition_id=version.composition_id,
                                  version_id=version.id, content_digest=version.content_digest)
    assert spec["duration_frames"] == 1800
    assert [(t["kind"], t["end_frame"] - t["start_frame"]) for t in spec["transitions"]] == [(k, 13) for k in kinds]
    hook, show, grid = [c["object"] for c in spec["tracks"][0]["clips"][:3]]
    assert hook["props"]["highlight_at_s"] == .73 and hook["props"]["backdrop_style"] == "editorial_paper"
    assert show["resources"][0]["digest"] == "c" * 64
    p = show["props"]
    assert (p["camera_preset"], p["backdrop_style"], p["scroll_from_y"], p["scroll_to_y"]) == (
        "tilt_left", "architectural_grid", .1, .8)
    assert (p["cursor"]["x"], p["cursor"]["y"], p["cursor"]["click_at_s"]) == pytest.approx((.72, .64, 1.7))
    assert [(s["x"], s["y"], s["start_s"], s["end_s"], s["label"]) for s in p["callout_steps"]] == [
        (.2, .44, .1, 1.1, "Review"), (.66, .62, 1.25, 2.4, "Open")]
    assert [item["reveal_at_s"] for item in grid["props"]["items"]] == [.2, 1.6]


# --- 8-act narrative blueprint remake ---

from types import SimpleNamespace


from uuid import UUID


import pytest


from pydantic import ValidationError


from app.editing.catalog import MOTION_BLOCK_CATALOG


from app.editing.schemas import CompositionContent, MOTION_BLOCK_PROP_MODELS, MotionBlockObject


from app.editing.store import apply_composition_edits, content_of, get_video_version, snapshot_facts


from app.editing.video_spec import compile_video_spec


from app.models.tables import Conversation, Message, Project, SkillVersion, SourceSnapshot


from app.skills.blueprint import (
    InstantiateSkillBlueprintArgs, SkillBlueprintV1, instantiate_skill_blueprint, save_composition_as_skill,
)


from test.support.db_helpers import _project, _user


def materials(label, metric):
    return {
        "chat_demo": dict(title=label, messages=[dict(role=r, text=label) for r in ("user", "assistant")],
                          work_steps=[dict(label=label)], result_card=dict(title=label, subtitle=label, badge=label)),
        "device_mockup": dict(eyebrow=label, headline=label, caption=label),
        "flow_diagram": dict(title=label, nodes=[dict(title=label, detail=label, step_label=label, badge=label) for _ in range(3)]),
        "split_compare": dict(left_heading=label, right_heading=label, left_items=[dict(text=label) for _ in range(2)],
                              right_items=[dict(text=label) for _ in range(3)]),
        "step_timeline": dict(steps=[dict(number=label, title=label, detail=label) for _ in range(3)]),
        "bento_features": dict(cards=[dict(tag=label, title=label, detail=label) for _ in range(4)]),
        "data_chart": dict(title=label, subtitle=label, unit=label, points=[
            dict(label=label, value=metric+i, display_value=label) for i in range(4)]),
        "quote_proof": dict(quote=label, author=label, role_or_source=label, verification_badge=label, highlight_phrase=label),
    }


STYLES = {
    "chat_demo": {}, "device_mockup": {"layout": "dual", "reveal_at_s": 1.5},
    "flow_diagram": {}, "split_compare": {"dim_left": False},
    "step_timeline": {"active_step": 2}, "bento_features": {"highlight_index": 3},
    "data_chart": {"chart_type": "bar", "highlight_index": 3}, "quote_proof": {"highlight_at_s": 1.4},
}


BOX = dict(x=0, y=0, width=1920, height=1080)


@pytest.mark.asyncio
async def test_eight_act_skill_remakes_in_another_project(database, monkeypatch):
    owner = await _user(database)
    source = await _project(database, owner, title="Master")
    target = await _project(database, owner, title="Remake")
    master_props = materials("PRIVATE_COPY", 79312)
    master_props["chat_demo"]["messages"][0]["text"] = "https://master.example/private"
    replacements = materials("New material", -5)
    expected = materials("New material", -5)
    async with database() as db:
        images = [SourceSnapshot(owner_id=owner, origin_project_id=project, kind="image",
                                 digest=str(i+1)*64, storage_key=f"{prefix}-{i}.png")
                  for i, (project, prefix) in enumerate([(source, "secret"), (source, "secret"),
                                                          (target, "desktop"), (target, "phone")])]
        chat = Conversation(user_id=owner, project_id=target)
        db.add_all([chat, *images])
        await db.flush()
        opening = Message(conversation_id=chat.id, role="user", content="Use template", turn_state="in_flight")
        db.add(opening)
        await db.flush()
        turn = SimpleNamespace(project=await db.get(Project, target), conversation_id=chat.id, turn_id=opening.id)
        clips, slots = [], []
        for i, (block, props) in enumerate(master_props.items()):
            style = dict(theme="light", backdrop_style="editorial_paper", accent_color="#334477", **STYLES[block])
            expected[block].update(style)
            for group, items in props.items():
                if isinstance(items, list):
                    key = "at_s" if block == "chat_demo" else "reveal_at_s"
                    for j, item in enumerate(items):
                        beat = (j+1)*0.51 + (0.23 if group in ("right_items", "work_steps") else 0)
                        item[key] = beat
                        expected[block][group][j][key] = beat
            slot = dict(props=replacements[block])
            if block == "chat_demo":
                slot["props"]["messages"][1]["at_s"] = 2.25
                expected[block]["messages"][1]["at_s"] = 2.25
            media = []
            if block == "device_mockup":
                media = [dict(path=f"media/secret-{j}.png", snapshot_id=im.id, snapshot_digest=im.digest,
                              content_type="image/png") for j, im in enumerate(images[:2])]
                slot["resources"] = [im.id for im in images[2:]]
            slots.append(slot)
            clips.append(dict(clip_id=f"c{i}", range=dict(start=i*360000, end=(i+1)*360000),
                              object=dict(object_id=f"o{i}", kind="motion_block", block_id=block,
                                          layout=BOX, fit="cover", props={**props, **style}, resources=media)))
        content = CompositionContent.model_validate(dict(settings=dict(width=1920, height=1080), scenes=[],
            sources=[dict(snapshot_id=im.id, snapshot_digest=im.digest) for im in images[:2]],
            timeline=dict(tracks=[dict(track_id="main", order=0, kind="visual", role="main", clips=clips)])))
        comp, version, _ = await apply_composition_edits(db, owner_id=owner, origin_project_id=source, content=content)
        saved = await save_composition_as_skill(db, owner_id=owner, project_id=source, composition_id=comp.id,
            version_id=version.id, name="editorial", description="Reusable timed narrative.")
        skill = await db.get(SkillVersion, UUID(saved["skill_version_id"]))
        raw = skill.references[0]["text"]
        for private in ("PRIVATE_COPY", "master.example", "79312", "secret-", *(str(im.id) for im in images[:2]),
                        *(im.digest for im in images[:2])):
            assert private not in raw and private not in skill.instructions
        blueprint = SkillBlueprintV1.model_validate_json(raw)
        device = next(a for a in blueprint.acts if a.block_id == "device_mockup")
        assert "image_resource" in device.required_slots and "mobile_image_resource" in device.optional_slots
        assert set(MOTION_BLOCK_PROP_MODELS) == set(MOTION_BLOCK_CATALOG)
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    result = await instantiate_skill_blueprint(turn=turn, call_id="remake", args=InstantiateSkillBlueprintArgs(
        skill_version_id=skill.id, name="Replacement", acts=slots))
    async with database() as db:
        _, version = await get_video_version(db, owner_id=owner, version_id=UUID(result["version_id"]))
        content = content_of(version)
        facts = await snapshot_facts(db, {row.snapshot_id for row in content.sources})
        spec = compile_video_spec(content, facts, composition_id=version.composition_id, version_id=version.id,
                                  content_digest=version.content_digest)
    objects = [clip["object"] for clip in spec["tracks"][0]["clips"]]
    assert [o["block_id"] for o in objects] == list(expected)
    for obj in objects:
        block = obj["block_id"]
        assert obj["props"] == MOTION_BLOCK_PROP_MODELS[block].model_validate(expected[block]).model_dump(mode="json")
    assert [(r["url"], r["digest"]) for r in objects[1]["resources"]] == [(im.storage_key, im.digest) for im in images[2:]]


# --- Web target view isolation & looped music fades ---

from uuid import UUID, uuid4


import pytest


import pytest_asyncio


from app.chat.editor import InsertAudioArgs, InsertMotionBlockArgs, edit_clip


from app.editing.edits import apply_ops


from app.editing.revisions import motion_block_ops


from app.editing.store import apply_composition_edits, content_of


from app.editing.video_spec import compile_video_spec


from app.models.tables import CompositionVersion, Conversation, Message, Project, SkillVersion, SourceSnapshot


from app.skills.blueprint import load_blueprint_from_skill_version, music_clips_for_window, save_composition_as_skill


from app.tools.video.preparation import canonical_resource


from test.support.composition_fixtures import base_content as _base_content


from test.support.db_helpers import _create, _project, _snapshots, _user


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

