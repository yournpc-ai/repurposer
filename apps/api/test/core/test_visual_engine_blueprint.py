"""Contract at the public save / re-bind / compile boundary, including full-size templates."""
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
from test.core.test_compositions import _project, _user


def test_capture_targets_and_step_windows_are_unambiguous():
    view = {"view_id": "new", "elements": [{"id": "missing-box"}]}
    for target in ({"element_id": "old"}, {"element_id": "missing-box"}, {"element_id": "old", "x": 0.5}):
        for props in ({"cursor": target}, {"callout_steps": [target]}):
            with pytest.raises(ValueError):
                ProductShowcaseProps.resolve_props(props, [view], "new")
    step = dict(x=0, y=0, width=0.2, height=0.1, label="Region", start_s=0.2, end_s=0.7)
    for steps in ([step] * 5, [step, step], [{**step, "end_s": 0.1}]):
        with pytest.raises(ValidationError):
            ProductShowcaseProps(callout_steps=steps)
    assert SetTransitionArgs(from_clip_id="left", to_clip_id="right").kind == "crossfade"
    with pytest.raises(ValidationError):
        SetTransitionArgs(from_clip_id="left", to_clip_id="right", kind="unknown")


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
