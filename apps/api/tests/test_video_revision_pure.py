"""Pure tests for the Video Project phase-B content services.

No DB, no LLM, no HTTP: the revision translation (LLM ops → write-door
ops), the launch-film template + MG instantiation (slots → op batch that
the write door's own apply/validate accepts), grounding helpers, the
system-computed change set, and the presentation receipt/block shapes.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from pydantic import TypeAdapter

from app.editing.director import MgDirection, ProgramDirection
from app.editing.edits import Op, apply_ops
from app.editing.grounding import (
    CiteLine,
    ManifestLine,
    detect_plate_cards,
    fit_to_cap,
    resolve_citation,
)
from app.editing.schemas import CompositionContent, TimeRange, VideoObject, WebObject
from app.editing.service import (
    VideoServiceError,
    compute_change_set,
    storyboard_block,
    translate_revision,
    video_carry_state,
    video_presentation_receipt,
)
from app.editing.templates import (
    DesignSlots,
    ViewFact,
    instantiate_mg,
    instantiate_program,
    instantiate_template,
    load_template,
)
from app.editing.validators import validate_content
from app.models.schemas import ReviseVideoArgs
from test_editing_edits_pure import SNAPSHOT_FACTS, valid_content

ADAPT = TypeAdapter(Op)

COMP_ID = UUID("55555555-5555-5555-5555-555555555555")
VER_ID = UUID("66666666-6666-6666-6666-666666666666")


def _args(*edits: dict, visual_descriptions=None) -> ReviseVideoArgs:
    return ReviseVideoArgs.model_validate(
        {
            "base_ref": {
                "composition_id": str(COMP_ID),
                "composition_version_id": str(VER_ID),
                "content_digest": "c" * 64,
            },
            "edits": list(edits),
            "visual_descriptions": visual_descriptions,
        }
    )


# ---- revision translation -------------------------------------------------


def test_update_text_deep_copies_and_clears_background():
    base = valid_content()
    ops = translate_revision(
        base,
        _args(
            {
                "op": "update_text",
                "clip_id": "clp_title",
                "text": "Bonjour",
                "background": None,  # explicit null clears (absent keeps)
            }
        ),
    )
    updated = apply_ops(base, ops, {})
    title = next(
        c for t in updated.timeline.tracks for c in t.clips if c.clip_id == "clp_title"
    )
    assert title.object.text == "Bonjour"
    assert title.object.style.background is None
    # The base is immutable: untouched by the translation's copy.
    original = next(
        c for t in base.timeline.tracks for c in t.clips if c.clip_id == "clp_title"
    )
    assert original.object.text == "Hello"


def test_update_text_rejects_non_text_clip():
    with pytest.raises(VideoServiceError):
        translate_revision(
            valid_content(), _args({"op": "update_text", "clip_id": "clp_bg", "text": "x"})
        )


def test_add_text_rides_existing_role_track_and_validates():
    base = valid_content()
    ops = translate_revision(
        base,
        _args(
            {
                "op": "add_text",
                "scene_id": "scn_open",
                "text": "A late note",
                "track": "title",
                "at_seconds": 2.0,
                "duration_seconds": 1.5,
            }
        ),
    )
    updated = apply_ops(base, ops, {})
    validate_content(updated, SNAPSHOT_FACTS)
    added = [
        c
        for t in updated.timeline.tracks
        for c in t.clips
        if c.clip_id.startswith("clp_rev_")
    ]
    assert len(added) == 1 and added[0].scene_id == "scn_open"
    # The title track carries it (the base has no caption track).
    title_track = next(t for t in updated.timeline.tracks if any(c.clip_id == added[0].clip_id for c in t.clips))
    assert title_track.role == "title"


def test_add_text_creates_a_missing_caption_track():
    base = valid_content()
    args = _args({"op": "add_text", "scene_id": "scn_open", "text": "x", "track": "caption"})
    ops = translate_revision(base, args, request_id="same-call")
    assert ops == translate_revision(base, args, request_id="same-call")
    updated = apply_ops(base, ops, {})
    validate_content(updated, SNAPSHOT_FACTS)
    assert any(t.role == "caption" and t.clips for t in updated.timeline.tracks)


def test_add_text_stays_inside_the_scene_window():
    with pytest.raises(VideoServiceError):
        translate_revision(
            valid_content(),
            _args(
                {
                    "op": "add_text",
                    "scene_id": "scn_open",
                    "text": "x",
                    "at_seconds": 3.0,
                    "duration_seconds": 2.0,  # past the 4s scene end
                }
            ),
        )


def test_remove_clip_is_text_only():
    ops = translate_revision(
        valid_content(), _args({"op": "remove_clip", "clip_id": "clp_title"})
    )
    updated = apply_ops(valid_content(), ops, {})
    assert all(
        c.clip_id != "clp_title" for t in updated.timeline.tracks for c in t.clips
    )
    with pytest.raises(VideoServiceError):
        translate_revision(
            valid_content(), _args({"op": "remove_clip", "clip_id": "clp_bg"})
        )


def test_focus_web_recomputes_camera_from_frozen_element_without_model_numbers():
    base = valid_content()
    clip = next(c for t in base.timeline.tracks for c in t.clips if c.clip_id == "clp_bg")
    clip.object = WebObject(
        kind="web", object_id="obj_bg", view_id="view-1", layout=clip.object.layout,
    )
    snapshot_id = clip.source.snapshot_id
    facts = {**SNAPSHOT_FACTS, snapshot_id: {
        **SNAPSHOT_FACTS[snapshot_id],
        "kind": "web",
        "meta": {"views": [{
            "view_id": "view-1", "width": 2880, "height": 1800,
            "storage_key": "snapshots/view-1.png", "digest": "d" * 64,
            "elements": [{
                "id": "s1e8", "kind": "heading",
                "x": 0.3423, "y": 0.2564, "w": 0.4374, "h": 0.1045,
            }],
        }]},
    }}
    args = _args({"op": "focus_web", "clip_id": "clp_bg", "element_id": "s1e8"})
    updated = apply_ops(base, translate_revision(base, args, snapshots=facts), {})
    validate_content(updated, facts)
    revised = next(c for t in updated.timeline.tracks for c in t.clips if c.clip_id == "clp_bg")
    assert revised.source == clip.source
    assert revised.object == clip.object
    scale = next(a for a in revised.animations if a.property == "transform.scale")
    position = next(a for a in revised.animations if a.property == "transform.position")
    assert scale.keyframes[1].value == 1.257
    assert position.keyframes[1].value == (246.7, 138.7)

    # Repeating the semantic focus replaces the camera in place, preserving
    # animation identities rather than appending a second camera.
    repeated = apply_ops(updated, translate_revision(updated, args, snapshots=facts), {})
    repeated_clip = next(c for t in repeated.timeline.tracks for c in t.clips if c.clip_id == "clp_bg")
    assert [a.animation_id for a in repeated_clip.animations] == [
        a.animation_id for a in revised.animations
    ]


def test_update_video_changes_only_that_layer_and_keeps_output_duration():
    base = valid_content()
    clip = next(c for t in base.timeline.tracks for c in t.clips if c.clip_id == "clp_bg")
    clip.object = VideoObject(
        kind="video", object_id="obj_bg", layout=clip.object.layout, fit="contain"
    )
    clip.source.source_range = TimeRange(start=0, end=360000)
    snapshot_id = clip.source.snapshot_id
    facts = {**SNAPSHOT_FACTS, snapshot_id: {
        **SNAPSHOT_FACTS[snapshot_id], "kind": "video", "duration_ticks": 540000,
    }}
    music_before = next(c for t in base.timeline.tracks for c in t.clips if c.clip_id == "clp_bed")
    ops = translate_revision(base, _args({
        "op": "update_video", "clip_id": "clp_bg", "scale": 0.8,
        "muted": True, "source_start_seconds": 0.5, "source_end_seconds": 4.5,
    }))
    updated = apply_ops(base, ops, {})
    validate_content(updated, facts)
    changed = next(c for t in updated.timeline.tracks for c in t.clips if c.clip_id == "clp_bg")
    music_after = next(c for t in updated.timeline.tracks for c in t.clips if c.clip_id == "clp_bed")
    assert changed.object.transform.scale == 0.8 and changed.object.muted is True
    assert changed.source.source_range == TimeRange(start=45000, end=405000)
    assert changed.range == clip.range
    assert music_after == music_before
    assert compute_change_set(base, updated)["clips"]["updated"] == [
        {"clip_id": "clp_bg", "changes": ["object", "source"]}
    ]


def test_update_animation_replaces_keyframes_clip_local():
    base = valid_content()
    ops = translate_revision(
        base,
        _args(
            {
                "op": "update_animation",
                "animation_id": "anm_fade",
                "keyframes": [
                    {"at_seconds": 0.0, "value": 0.0, "easing": "hold"},
                    {"at_seconds": 1.0, "value": 1.0, "easing": "ease_out"},
                ],
            }
        ),
    )
    updated = apply_ops(base, ops, {})
    title = next(
        c for t in updated.timeline.tracks for c in t.clips if c.clip_id == "clp_title"
    )
    (anim,) = title.animations
    assert [kf.at for kf in anim.keyframes] == [0, 90000]
    assert anim.keyframes[1].easing.kind == "cubic_bezier"  # ease_out maps


def test_move_and_remove_scene_map_seconds_to_ticks():
    base = valid_content()
    moved = translate_revision(
        base, _args({"op": "move_scene", "scene_id": "scn_open", "start_seconds": 2.0})
    )
    result = apply_ops(base, moved, {})
    assert result.scenes[0].range.start == 180000
    removed = translate_revision(
        base, _args({"op": "remove_scene", "scene_id": "scn_open"})
    )
    assert removed[0].op == "remove_scene"


def test_unknown_handles_reject_with_model_readable_reasons():
    with pytest.raises(VideoServiceError, match="clp_nope"):
        translate_revision(
            valid_content(), _args({"op": "update_text", "clip_id": "clp_nope", "text": "x"})
        )
    with pytest.raises(VideoServiceError, match="anm_nope"):
        translate_revision(
            valid_content(),
            _args(
                {
                    "op": "update_animation",
                    "animation_id": "anm_nope",
                    "keyframes": [{"at_seconds": 0.0, "value": 1.0}],
                }
            ),
        )


def test_visual_descriptions_land_after_content_ops():
    ops = translate_revision(
        valid_content(),
        _args(
            {"op": "update_text", "clip_id": "clp_title", "text": "Salut"},
            visual_descriptions=[{"scene_id": "scn_open", "text": "a quiet opening"}],
        ),
    )
    assert ops[-1].op == "update_scene"
    updated = apply_ops(valid_content(), ops, {})
    assert updated.scenes[0].visual_description == "a quiet opening"


# ---- the system-computed change set ----------------------------------------


def test_change_set_names_the_delta():
    base = valid_content()
    ops = translate_revision(
        base,
        _args(
            {"op": "update_text", "clip_id": "clp_title", "text": "Bonjour"},
            {"op": "add_text", "scene_id": "scn_open", "text": "note", "track": "title"},
        ),
    )
    updated = apply_ops(base, ops, {})
    change = compute_change_set(base, updated)
    assert change["scenes"]["added"] == [] and change["scenes"]["removed"] == []
    assert change["clips"]["removed"] == []
    updated_clips = {c["clip_id"]: c["changes"] for c in change["clips"]["updated"]}
    assert updated_clips == {"clp_title": ["object"]}
    assert [c["kind"] for c in change["clips"]["added"]] == ["text"]


# ---- template instantiation (launch-film) ----------------------------------

WEB_SNAPSHOT = UUID("77777777-7777-7777-7777-777777777777")
WEB_DIGEST = "d" * 64


def _web_views(count: int = 5) -> list[ViewFact]:
    return [
        ViewFact(
            snapshot_id=WEB_SNAPSHOT,
            snapshot_digest=WEB_DIGEST,
            view_id=f"v{i}",
            width=1920,
            height=1080,
            elements=[
                {"id": f"el{i}", "kind": "heading", "x": 100, "y": 100, "width": 800, "height": 120}
            ],
            heading=f"Section {i}",
            page=0,
        )
        for i in range(count)
    ]


def _slots(chapters: int = 3) -> DesignSlots:
    return DesignSlots(
        name="Demo Film",
        language="en",
        cold_open=["A quiet question."],
        hero_word="Clarity",
        hero_sub="Everything in one place.",
        chapter_titles=[f"Chapter {i}" for i in range(1, chapters + 1)],
        reveal_lead="So",
        reveal_word="One home.",
        reveal_sub="For the work that matters.",
        end_name="Demo",
        end_tagline="Start today.",
        captions={},
        visual_descriptions={},
        camera_focuses={},
        plate_cards=[],
        plate_page=None,
    )


def test_launch_film_template_instantiates_into_valid_content():
    template = load_template("launch-film")
    ops = [ADAPT.validate_python(o) for o in instantiate_template(template, _slots(), _web_views())]
    content = apply_ops(CompositionContent(settings={"width": 1920, "height": 1080}), ops, {WEB_SNAPSHOT: WEB_DIGEST})
    validate_content(
        content,
        {
            WEB_SNAPSHOT: {
                "digest": WEB_DIGEST,
                "kind": "web",
                "duration_ticks": None,
                "owner_id": uuid4(),
                "storage_key": "snapshots/web.json",
                "meta": {
                    "views": [
                        {
                            "view_id": f"v{i}",
                            "storage_key": f"snapshots/web/v{i}.png",
                            "digest": f"{i:064x}",
                        }
                        for i in range(5)
                    ]
                },
            }
        },
    )
    # The fixed arc: cold open / hero / home / per-chapter divider+walk /
    # reveal / proof / end (no plate — no number-led lines detected).
    scene_ids = [s.scene_id for s in content.scenes]
    assert scene_ids[0] == "scn_cold_open" and scene_ids[-1] == "scn_end"
    assert "scn_home" in scene_ids and "scn_reveal" in scene_ids and "scn_proof" in scene_ids
    walks = [s for s in scene_ids if s.startswith("scn_chapter_") and s.endswith("_walk")]
    assert len(walks) == 3
    # Scenes tile the timeline without gaps or overlaps.
    cursor = 0
    for scene in content.scenes:
        assert scene.range.start == cursor
        cursor = scene.range.end
    assert cursor > 0


# ---- MG instantiation ------------------------------------------------------


def test_mg_direction_instantiates_into_valid_content():
    direction = MgDirection.model_validate(
        {
            "name": "Launch Notes",
            "scenes": [
                {
                    "intent": "hook",
                    "duration_seconds": 4.0,
                    "lines": ["Ship the work.", "Skip the busywork."],
                    "size": "large",
                    "enter": "lines",
                    "shapes": [
                        {
                            "shape": "rect",
                            "x": 0.08,
                            "y": 0.12,
                            "width": 0.3,
                            "height": 0.18,
                            "fill": "#3366FF",
                            "opacity": 0.8,
                            "corner_radius": 24,
                            "motion": "scale",
                        },
                        {
                            "type": "ellipse",
                            "x": 0.62,
                            "y": 0.58,
                            "width": 0.22,
                            "height": 0.16,
                            "fill": "#22CCFF",
                            "motion": "rise",
                        }
                    ],
                },
                {
                    "intent": "close",
                    "duration_seconds": 3.0,
                    "lines": ["Start today."],
                    "size": "hero",
                    "enter": "words",
                },
            ],
        }
    )
    ops = [ADAPT.validate_python(o) for o in instantiate_mg(direction)]
    content = apply_ops(CompositionContent(settings={"width": 1920, "height": 1080}), ops, {})
    validate_content(content, {})
    assert [s.scene_id for s in content.scenes] == ["scn_mg_1", "scn_mg_2"]
    first_texts = [
        c.object.text
        for t in content.timeline.tracks
        for c in t.clips
        if c.scene_id == "scn_mg_1" and c.object.kind == "text"
    ]
    assert first_texts == ["Ship the work.\nSkip the busywork."]
    shapes = [c for t in content.timeline.tracks for c in t.clips if c.object.kind == "shape"]
    assert len(shapes) == 2
    shape = shapes[0]
    assert shape.object.shape == "rect"
    assert shape.object.layout.width == 576
    assert shape.animations[0].property == "transform.scale"
    shape_tracks = [t.track_id for t in content.timeline.tracks if any(c.object.kind == "shape" for c in t.clips)]
    assert shape_tracks == ["trk_shape", "trk_shape_2"]


def test_native_shape_and_animation_revision_preserve_other_layers():
    direction = MgDirection.model_validate(
        {
            "scenes": [
                {
                    "duration_seconds": 2.0,
                    "lines": ["Keep this title"],
                    "shapes": [
                        {
                            "shape": "rect", "x": 0.1, "y": 0.1, "width": 0.3, "height": 0.2,
                            "fill": "#3366FF", "corner_radius": 12, "motion": "scale",
                        }
                    ],
                }
            ]
        }
    )
    ops = [ADAPT.validate_python(o) for o in instantiate_mg(direction)]
    base = apply_ops(CompositionContent(settings={"width": 1920, "height": 1080}), ops, {})
    revision = translate_revision(
        base,
        _args(
            {
                "op": "update_shape", "clip_id": "clp_mg_1_shape_1",
                "fill": "#FF3300", "corner_radius": 32,
            },
            {
                "op": "update_animation", "animation_id": "anm_mg_1_shape_1_transform_scale",
                "keyframes": [
                    {"at_seconds": 0, "value": 0.5},
                    {"at_seconds": 1.0, "value": 1.2, "easing": "ease_out"},
                ],
            },
        ),
    )
    updated = apply_ops(base, revision, {})
    validate_content(updated, {})
    shape = next(c for t in updated.timeline.tracks for c in t.clips if c.object.kind == "shape")
    title = next(c for t in updated.timeline.tracks for c in t.clips if c.object.kind == "text")
    assert shape.object.fill == "#FF3300" and shape.object.corner_radius == 32
    assert shape.animations[0].keyframes[-1].value == 1.2
    assert title.object.text == "Keep this title"
    assert title.animations == next(
        c for t in base.timeline.tracks for c in t.clips if c.object.kind == "text"
    ).animations


def test_generator_source_revision_changes_digest_and_preserves_native_title():
    direction = ProgramDirection.model_validate(
        {
            "title": "Independent title",
            "intent": "moving field",
            "duration_seconds": 2.0,
            "background": "#101828",
            "parameters": {"color": "#3366FF"},
            "code": "function render(ctx) { return [{kind:'rect',x:ctx.frame,y:0,width:20,height:20,fill:ctx.parameters.color}]; }",
        }
    )
    ops = [ADAPT.validate_python(o) for o in instantiate_program(direction)]
    base = apply_ops(CompositionContent(settings={"width": 1920, "height": 1080}), ops, {})
    validate_content(base, {})
    before = next(c for t in base.timeline.tracks for c in t.clips if c.object.kind == "generator")
    revision = translate_revision(
        base,
        _args({
            "op": "update_generator", "clip_id": "clp_generator",
            "code": "function render(ctx) { return [{kind:'ellipse',x:ctx.frame * 2,y:10,width:30,height:30,fill:ctx.parameters.color}]; }",
            "parameters": {"color": "#FF3300"},
        }),
    )
    updated = apply_ops(base, revision, {})
    validate_content(updated, {})
    generator = next(c for t in updated.timeline.tracks for c in t.clips if c.object.kind == "generator")
    title = next(c for t in updated.timeline.tracks for c in t.clips if c.object.kind == "text")
    assert generator.object.program_digest() != before.object.program_digest()
    assert generator.object.parameters == {"color": "#FF3300"}
    assert "ellipse" in generator.object.code
    assert title.object.text == "Independent title"
    assert title.animations == next(
        c for t in base.timeline.tracks for c in t.clips if c.object.kind == "text"
    ).animations


# ---- grounding helpers ------------------------------------------------------


def test_citation_folds_natural_forms():
    assert CiteLine.model_validate_natural("L2").line == 2
    assert CiteLine.model_validate_natural(3).line == 3
    assert CiteLine.model_validate_natural({"id": "L1"}).line == 1


def test_resolve_citation_returns_the_exact_line():
    lines = [
        ManifestLine(index=1, kind="title", text="One", page=0),
        ManifestLine(index=2, kind="paragraph", text="Two", page=0),
    ]
    assert resolve_citation(lines, CiteLine(line=2)) == "Two"
    with pytest.raises(ValueError, match="L9"):
        resolve_citation(lines, CiteLine(line=9))


def test_fit_to_cap_prefers_sentence_boundaries():
    text = "First thought. Second thought is longer and runs past the cap."
    fitted = fit_to_cap(text, 30, "head")
    assert fitted == "First thought."
    assert len(fitted) <= 30


def test_plate_cards_need_two_number_led_lines():
    lines = [
        ManifestLine(index=1, kind="paragraph", text="12,000 members", page=0),
        ManifestLine(index=2, kind="paragraph", text="98% retention", page=0),
    ]
    cards = detect_plate_cards(lines)
    assert len(cards) == 2
    assert cards[0]["big"].startswith("12,000")
    assert detect_plate_cards(lines[:1]) == []


# ---- the presentation receipt / block / carry -------------------------------


def _read_stub() -> dict:
    return {
        "composition_id": str(COMP_ID),
        "composition_name": "Demo",
        "composition_version_id": str(VER_ID),
        "version": 2,
        "content_digest": "c" * 64,
        "presentation_digest": "e" * 64,
        "storyboard": {"scenes": []},
    }


def test_presentation_receipt_and_block_shapes():
    receipt = video_presentation_receipt(_read_stub(), review_hold=True)
    assert receipt["presented_message_id"] is None
    assert receipt["review_hold"] is True
    receipt["presented_message_id"] = "msg-1"
    block = storyboard_block(_read_stub())
    assert block == {
        "kind": "video_storyboard",
        "composition_id": str(COMP_ID),
        "composition_version_id": str(VER_ID),
        "version": 2,
        "content_digest": "c" * 64,
        "presentation_digest": "e" * 64,
    }


def test_carry_state_preserves_the_receipt_verbatim():
    receipt = {"version": 2, "presented_message_id": "msg-1"}

    class _Stored:
        video_presentation = receipt

    assert video_carry_state(_Stored()) == {"video_presentation": receipt}
    assert video_carry_state(None) == {"video_presentation": None}


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["plan", "chat"])
async def test_video_stamp_does_not_require_legacy_film_pending(path):
    from types import SimpleNamespace
    from app.chat.plan_turn import PlanTurn
    from app.chat.propose_turn import ChatTurn

    cls = PlanTurn if path == "plan" else ChatTurn
    runner = cls.__new__(cls)
    runner.project = SimpleNamespace(pending_brief={})
    runner._presentation_pending = None
    runner._video_presentation_pending = _read_stub()
    message = SimpleNamespace(id=uuid4(), blocks=[])
    await runner._stamp_presentation(message)
    assert message.blocks == [{**storyboard_block(_read_stub()), "presented_message_id": str(message.id)}]
    receipt = runner.project.pending_brief["video_presentation"]
    assert receipt["presented_message_id"] == str(message.id)
    assert receipt["review_hold"] is True


@pytest.mark.asyncio
async def test_video_request_keys_are_scoped_to_user_turns():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.chat.video_turn_seats import video_request_id

    first, second = uuid4(), uuid4()
    db = SimpleNamespace(scalar=AsyncMock(side_effect=[first, first, second]))
    chat_id = uuid4()
    key = await video_request_id(db, chat_id, 1)
    assert key == await video_request_id(db, chat_id, 1)
    assert key != await video_request_id(db, chat_id, 1)


@pytest.mark.parametrize("value", [{"line": True}, {"line": 1.0}, {"line": 1.5}, False, 0, -1])
def test_citation_rejects_non_integer_addresses(value):
    with pytest.raises(ValueError):
        CiteLine.model_validate(value)


@pytest.mark.parametrize("value", [[], ["  "], [{"unknown": "caption"}]])
def test_subtitle_fragments_do_not_silently_disappear(value):
    from app.editing.director import LaunchFilmDirection
    # Exercise the normalization seat; malformed values must survive it so
    # the actual dict[str, str | None] field rejects them, never become null.
    from pydantic import ValidationError
    folded = LaunchFilmDirection._fold_subtitle_values({"home": value})
    with pytest.raises(ValidationError):
        TypeAdapter(dict[str, str | None]).validate_python(folded)


def test_focus_treats_capture_coordinates_as_center_and_clips_visible_part():
    from app.editing.grounding import resolve_focus

    centered = resolve_focus([
        {"id": "heading", "kind": "heading", "x": 0.5, "y": 0.5, "w": 0.4, "h": 0.2},
    ], "heading")
    assert centered == pytest.approx({"cx": 0.5, "cy": 0.5, "w": 0.4, "h": 0.2})

    clipped = resolve_focus([
        {"id": "edge", "kind": "heading", "x": 0.95, "y": 0.5, "w": 0.2, "h": 0.4},
    ], "edge")
    assert clipped == pytest.approx({"cx": 0.925, "cy": 0.5, "w": 0.15, "h": 0.4})


@pytest.mark.parametrize("view", [(1280, 2000), (2400, 900), (1920, 1080)])
def test_camera_covers_the_rendered_box_for_the_whole_walk(view):
    from app.editing.grounding import camera_keyframes
    for start_scale in (1.0, 1.08):
        zoom, positions = camera_keyframes(
            {"cx": 0.99, "cy": 0.99, "w": 0.3, "h": 0.1},
            view_width=view[0], view_height=view[1],
            canvas_width=1920, canvas_height=1080, clip_ticks=3000,
            arrival_frac=0.45, start_scale=start_scale,
        )
        scales = [start_scale, zoom, round(min(zoom * 1.01, 2.05), 3)]
        # Scale and position use the same interpolation on each interval.
        # The coverage inequalities are affine, including between endpoints.
        for segment in range(2):
            for i in range(21):
                t = i / 20
                scale = scales[segment] * (1-t) + scales[segment+1] * t
                x = positions[segment][1][0] * (1-t) + positions[segment+1][1][0] * t
                y = positions[segment][1][1] * (1-t) + positions[segment+1][1][1] * t
                assert abs(x) <= (scale - 1) * 1920 / 2 + 1e-6
                assert abs(y) <= (scale - 1) * 1080 / 2 + 1e-6
