"""Public editing, template privacy and multi-resource compilation contracts."""
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
from test.core.test_compositions import _project, _user


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


@pytest.mark.parametrize(("block", "invalid"), [
    ("chat_demo", dict(messages=[dict(role="system", text="x")]*2)),
    ("chat_demo", dict(work_steps=[])), ("device_mockup", dict(layout="tablet")),
    ("flow_diagram", dict(nodes=[dict(title="x", url="private")] * 3)),
    ("split_compare", dict(left_items=[])), ("step_timeline", dict(active_step=0)),
    ("step_timeline", dict(active_step=4)), ("bento_features", dict(highlight_index=4)),
    ("data_chart", dict(highlight_index=-1)), ("data_chart", dict(highlight_index=4)),
    ("data_chart", dict(points=[dict(label="x", value=float("inf"))]*3)),
    ("quote_proof", dict(author="  ")), ("quote_proof", dict(highlight_at_s=-1)),
])
def test_narrative_props_are_closed(block, invalid):
    valid = {**materials("Source", 2)[block], **STYLES[block]}
    model = MOTION_BLOCK_PROP_MODELS[block]
    assert model.model_validate(valid).show_backdrop
    for patch in [invalid, {"unregistered": "field"}]:
        with pytest.raises(ValidationError):
            model.model_validate({**valid, **patch})


def test_device_accepts_one_or_two_ordered_images():
    obj = dict(kind="motion_block", object_id="device", block_id="device_mockup", props={}, layout=BOX)
    images = [dict(path=f"media/{i}.png", snapshot_id=UUID(int=i+1),
                   snapshot_digest="e"*64, content_type="image/png") for i in range(3)]
    for count in (1, 2):
        assert len(MotionBlockObject(**obj, resources=images[:count]).resources) == count
    for invalid in ([], images, [{**images[0], "content_type": "video/mp4"}]):
        with pytest.raises(ValidationError):
            MotionBlockObject(**obj, resources=invalid)


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
