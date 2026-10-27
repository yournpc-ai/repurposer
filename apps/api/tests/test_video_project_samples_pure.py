"""Reusable website/MG fixtures through the pure half of the real write door."""

from __future__ import annotations

import copy
import hashlib
from uuid import UUID, uuid5

import pytest

from app.editing.edits import apply_ops
from app.editing.schemas import CompositionContent
from app.editing.timing import SOURCE_TIMEBASE
from app.editing.validators import ContentValidationError, validate_content
from app.editing.video_spec import compile_video_spec
from app.models.tables import SourceSnapshot
from scripts.video_project_samples import (
    FIXTURE_ROOT,
    SAMPLE_FILES,
    assert_local_text_edit,
    load_sample_fixture,
    resolve_ops,
)

COMPOSITION_ID = UUID("33333333-3333-3333-3333-333333333333")
BASE_VERSION_ID = UUID("44444444-4444-4444-4444-444444444444")
EDITED_VERSION_ID = UUID("55555555-5555-5555-5555-555555555555")


def _fixture_snapshot(ref: str, material) -> SourceSnapshot:
    return SourceSnapshot(
        id=uuid5(UUID(int=0), f"video-project-fixture:{ref}"),
        digest=hashlib.sha256(ref.encode()).hexdigest(),
        kind=material.kind,
    )


def _build_sample(sample_id: str):
    fixture = load_sample_fixture(FIXTURE_ROOT / SAMPLE_FILES[sample_id])
    snapshots = {ref: _fixture_snapshot(ref, m) for ref, m in fixture.sources.items()}
    facts = {}
    for ref, snapshot in snapshots.items():
        material = fixture.sources[ref]
        fact = {
            "digest": snapshot.digest,
            "kind": snapshot.kind,
            "duration_ticks": 16 * SOURCE_TIMEBASE if snapshot.kind == "audio" else None,
            "storage_key": f"fixture/{ref}",
            "meta": {},
        }
        if snapshot.kind == "web":
            fact["meta"] = {
                "views": [
                    {
                        "view_id": view.view_id,
                        "storage_key": f"fixture/{view.view_id}.png",
                        "digest": hashlib.sha256(view.view_id.encode()).hexdigest(),
                    }
                    for view in material.views
                ]
            }
        facts[snapshot.id] = fact
    create_ops = resolve_ops(fixture.create_ops, snapshots)
    content = apply_ops(
        CompositionContent(settings={"width": 1920, "height": 1080}),
        create_ops,
        {snapshot.id: snapshot.digest for snapshot in snapshots.values()},
    )
    validate_content(content, facts)
    edited = apply_ops(content, resolve_ops(fixture.edit_ops, snapshots), {})
    validate_content(edited, facts)
    proof = assert_local_text_edit(content, edited, fixture.edit_target)
    base_spec = compile_video_spec(
        content,
        facts,
        composition_id=COMPOSITION_ID,
        version_id=BASE_VERSION_ID,
        content_digest="a" * 64,
    )
    edited_spec = compile_video_spec(
        edited,
        facts,
        composition_id=COMPOSITION_ID,
        version_id=EDITED_VERSION_ID,
        content_digest="b" * 64,
    )
    return fixture, content, edited, proof, base_spec, edited_spec


def _clips(spec: dict) -> dict[str, dict]:
    return {clip["clip_id"]: clip for track in spec["tracks"] for clip in track["clips"]}


def test_website_fixture_compiles_real_web_views_captions_and_music():
    fixture, _, _, proof, base, edited = _build_sample("website")
    assert base["duration_frames"] == 360
    clips = _clips(base)
    assert clips["clp_web_hero"]["source"]["url"] == "fixture/hero.png"
    assert clips["clp_web_decide"]["source"]["url"] == "fixture/decide.png"
    assert clips["clp_web_proof"]["source"]["url"] == "fixture/proof.png"
    assert clips["clp_music"]["source"]["start_frame"] == 0
    assert clips["clp_music"]["source"]["end_frame"] == 360
    caption_track = next(track for track in base["tracks"] if track["role"] == "caption")
    assert len(caption_track["clips"]) == 6
    assert all(clip["object"]["kind"] == "text" for clip in caption_track["clips"])
    assert proof["clip_id"] == fixture.edit_target
    assert _clips(edited)[fixture.edit_target]["object"]["text"] == proof["after"]
    for clip_id, clip in clips.items():
        if clip_id != fixture.edit_target:
            assert _clips(edited)[clip_id] == clip


def test_mg_fixture_expands_line_grapheme_and_parent_scale_animations():
    fixture, _, _, proof, base, edited = _build_sample("mg")
    assert base["duration_frames"] == 270
    clips = _clips(base)
    line_animations = [
        animation
        for animation in clips["clp_mg_lines"]["animations"]
        if animation["animation_id"].startswith("anm_mg_line_opacity:")
    ]
    assert len(line_animations) == 2
    assert [animation["keyframes"][0]["at"] for animation in line_animations] == [0, 14]
    assert [animation["keyframes"][1]["at"] for animation in line_animations] == [18, 32]

    glyph_animations = [
        animation
        for animation in clips["clp_mg_graphemes"]["animations"]
        if animation["animation_id"].startswith("anm_mg_glyph_opacity:")
    ]
    assert len(glyph_animations) == 7
    assert [animation["keyframes"][0]["at"] for animation in glyph_animations] == [
        0,
        4,
        7,
        11,
        14,
        18,
        22,
    ]
    assert any(
        part["text"] == "👋🏽" and part["text_range"] == {"start": 3, "end": 5}
        for part in clips["clp_mg_graphemes"]["object"]["parts"]
    )
    scale = next(
        animation
        for animation in clips["clp_mg_graphemes"]["animations"]
        if animation["animation_id"] == "anm_mg_parent_scale"
    )
    assert [keyframe["at"] for keyframe in scale["keyframes"]] == [0, 27, 45, 72]
    assert scale["keyframes"][0]["easing"] == {
        "kind": "cubic_bezier",
        "params": [0.16, 1, 0.3, 1],
    }
    assert proof["after"] == "Ideas\nstay editable"
    assert _clips(edited)["clp_mg_lines"] == clips["clp_mg_lines"]
    assert _clips(edited)["clp_mg_graphemes"] == clips["clp_mg_graphemes"]


def test_unknown_web_view_is_an_explicit_rejection():
    fixture = load_sample_fixture(FIXTURE_ROOT / SAMPLE_FILES["website"])
    snapshots = {ref: _fixture_snapshot(ref, m) for ref, m in fixture.sources.items()}
    facts = {
        snapshot.id: {
            "digest": snapshot.digest,
            "kind": snapshot.kind,
            "duration_ticks": 16 * SOURCE_TIMEBASE if snapshot.kind == "audio" else None,
            "storage_key": f"fixture/{ref}",
            "meta": {
                "views": [
                    {
                        "view_id": view.view_id,
                        "storage_key": f"fixture/{view.view_id}.png",
                        "digest": hashlib.sha256(view.view_id.encode()).hexdigest(),
                    }
                    for view in fixture.sources[ref].views
                ]
            }
            if snapshot.kind == "web"
            else {},
        }
        for ref, snapshot in snapshots.items()
    }
    content = apply_ops(
        CompositionContent(settings={"width": 1920, "height": 1080}),
        resolve_ops(fixture.create_ops, snapshots),
        {snapshot.id: snapshot.digest for snapshot in snapshots.values()},
    )
    candidate = copy.deepcopy(content)
    candidate.timeline.tracks[0].clips[0].object.view_id = "not-captured"
    with pytest.raises(ContentValidationError, match="absent from the bound snapshot"):
        validate_content(candidate, facts)
