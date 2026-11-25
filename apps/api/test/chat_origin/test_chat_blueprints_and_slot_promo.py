"""Chat blueprints and slot promo — chat origin contracts."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest

from app.editing.catalog import MOTION_BLOCK_CATALOG
from app.editing.schemas import (
    MOTION_BLOCK_PROP_MODELS,
    CompositionContent,
)
from app.editing.store import apply_composition_edits, content_of, get_video_version, snapshot_facts
from app.editing.timing import SOURCE_TIMEBASE, seconds_to_ticks
from app.editing.video_spec import compile_video_spec
from app.models.tables import Conversation, Project, SkillVersion, SourceSnapshot, User
from app.skills.blueprint import (
    BLUEPRINT_PATH,
    BlueprintActSlotInput,
    InstantiateSkillBlueprintArgs,
    SkillBlueprintV1,
    instantiate_skill_blueprint,
)
from app.skills.loading import load_skill_creative_context
from app.skills.resolution import list_available_skills
from app.skills.store import SkillNotFoundError, get_skill_version
from test.support.blueprint_fixtures import _dig, _sample_master_composition
from test.support.chat_http import tool_result
from test.support.db_helpers import _project, _user

pytestmark = pytest.mark.chat_origin


async def save_template(database, monkeypatch, owner, project, name, description):
    result, _ = await tool_result(
        database, monkeypatch, owner, project, "Save the current film as a template.",
        "save_composition_as_skill", {"name": name, "description": description},
        operation="app.skills.blueprint.save_composition_as_skill",
    )
    return result


async def remake(database, monkeypatch, owner, project, args, call_id="remake"):
    return await tool_result(
        database, monkeypatch, owner, project, "Remake the film with this template.",
        "instantiate_skill_blueprint", args.model_dump(mode="json"), call_id=call_id,
        skill={"kind": "external", "skill_version_id": str(args.skill_version_id)},
        operation="app.skills.blueprint.instantiate_skill_blueprint",
    )


@pytest.mark.asyncio
async def test_save_composition_as_skill_persists_and_lists_in_picker(database, monkeypatch):
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

        saved1 = await save_template(database, monkeypatch, owner.id, proj.id,
                                    "oxvalue-promo-blueprint", "Reusable 4-act studio promo.")
        assert saved1["saved"] is True and saved1["reused"] is False
        assert saved1["acts_count"] == 4 and saved1["sfx_cues_count"] == 2

        # Idempotent replay returns identical SkillVersion
        saved2 = await save_template(database, monkeypatch, owner.id, proj.id,
                                    "oxvalue-promo-blueprint", "Reusable 4-act studio promo.")
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
async def test_instantiate_skill_blueprint_sfx_outside_write_lock_and_adaptive_timing(database, monkeypatch):
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
        saved_skill = await save_template(database, monkeypatch, owner.id, p_master.id,
                                    "oxvalue-promo-blueprint", "Reusable 4-act studio promo.")

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
        db.add_all([new_img, new_vo1, new_vo2, new_bgm])
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
        res, frames = await remake(database, monkeypatch, owner.id, p_remake.id, inst_args, "call_bp_1")

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
        # Replay the same native request identity after transport settlement.
        turn = SimpleNamespace(project=p_remake, turn_id=UUID(frames[-1][1]["user_message"]["id"]),
                               conversation_id=UUID(frames[-1][1]["conversation_id"]))
        replayed = await instantiate_skill_blueprint(turn=turn, args=inst_args, call_id="call_bp_1")
    assert events == []
    assert replayed["version_id"] == res["version_id"]
    assert replayed["composition_id"] == res["composition_id"]
    assert replayed["sfx_clips_count"] == 2


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
        saved = await save_template(database, monkeypatch, owner, master_id,
                                    "research-template", "Reusable brief.")
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
    result, _ = await remake(database, monkeypatch, owner, remake_id, InstantiateSkillBlueprintArgs(
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
        saved = await save_template(database, monkeypatch, owner, source,
                                    "editorial", "Reusable timed narrative.")
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
    result, _ = await remake(database, monkeypatch, owner, target, InstantiateSkillBlueprintArgs(
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
