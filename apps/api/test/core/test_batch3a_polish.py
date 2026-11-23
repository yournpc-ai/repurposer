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
from test.core.test_batch2_multiscene import _base_content
from test.core.test_compositions import _create, _project, _snapshots, _user


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


@pytest.mark.parametrize("detail", [None, "Published valuation methods"])
def test_three_column_metrics_compile_with_optional_supporting_copy(detail):
    content = _base_content(4)
    items = [{"value": str(i), "label": label} for i, label in enumerate(("Evidence", "Models", "Reports"), 1)]
    if detail:
        items[1]["detail"] = detail
    ops = motion_block_ops(content, block_id="metric_grid", props={"columns": 3, "items": items},
                           clip_id="clp_metrics", object_id="obj_metrics", scene_id="scn_1",
                           start=0, end=360000, resources=[])
    spec = compile_video_spec(apply_ops(content, ops, {}), {}, composition_id=uuid4(),
                              version_id=uuid4(), content_digest="d" * 64)
    clip, = spec["tracks"][0]["clips"]
    props = clip["object"]["props"]
    assert (clip["object"]["block_id"], props["columns"], clip["end_frame"]) == ("metric_grid", 3, 120)
    assert [(i["label"], i["value"], i.get("detail")) for i in props["items"]] == [
        ("Evidence", "1", None), ("Models", "2", detail), ("Reports", "3", None),
    ]
