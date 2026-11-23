"""Core contract tests for Batch 2 Checkpoint 2A: multi-scene Motion Blocks,
opaque MotionBlock crossfades, audio gain fades/ducking, and swoosh_cut SFX.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.editing.catalog import build_sound_spec, sound_spec_digest
from app.editing.revisions import build_audio_gain_animation, motion_block_ops
from app.editing.schemas import (
    Animation,
    AudioObject,
    Clip,
    ClipSource,
    CompositionContent,
    Scene,
    SourceBinding,
    TimeRange,
    Timeline,
    Track,
    Transition,
    VersionSettings,
)
from app.editing.validators import validate_content
from app.editing.video_spec import compile_video_spec


def _base_content(total_seconds: int = 36) -> CompositionContent:
    tb = 90000
    return CompositionContent(
        settings=VersionSettings(width=1920, height=1080, timebase=tb),
        sources=[],
        scenes=[Scene(scene_id="scn_1", range=TimeRange(start=0, end=total_seconds * tb))],
        timeline=Timeline(tracks=[], transitions=[]),
    )


def test_new_motion_blocks_and_opaque_crossfade_compile():
    from app.editing.edits import apply_ops

    tb = 90000
    img_id = uuid4()
    img_digest = "a" * 64
    logo_id = uuid4()
    logo_digest = "b" * 64
    snapshots = {
        img_id: {"kind": "image", "digest": img_digest, "storage_key": "uploads/ui.png", "meta": {}},
        logo_id: {"kind": "image", "digest": logo_digest, "storage_key": "uploads/logo.png", "meta": {}},
    }
    digests = {sid: info["digest"] for sid, info in snapshots.items()}

    content = _base_content(24)
    ops = []
    # Act 1: statement_hook (0-5s, no resources -> clip.source is None)
    ops.extend(motion_block_ops(
        content,
        block_id="statement_hook",
        props={
            "eyebrow": "OXVALUE.AI",
            "headline": "Institutional Valuation\nIn Minutes",
            "highlight_phrase": "In Minutes",
            "subheadline": "Evidence-grounded AI for venture and tech transfer.",
            "theme": "dark",
            "layout_variant": "centered",
        },
        resources=[],
        clip_id="clp_hook",
        object_id="obj_hook",
        scene_id="scn_1",
        start=0,
        end=5 * tb,
    ))
    content = apply_ops(content, ops, digests)

    # Act 2: product_showcase with callout + frameless (5-12s)
    content = apply_ops(content, motion_block_ops(
        content,
        block_id="product_showcase",
        props={
            "theme": "light",
            "chrome_mode": "frameless",
            "callout": {"x": 0.15, "y": 0.2, "width": 0.5, "height": 0.35, "label": "Valuation Engine"},
        },
        resources=[{
            "path": "media/img_0.png",
            "snapshot_id": str(img_id),
            "snapshot_digest": img_digest,
            "content_type": "image/png",
        }],
        clip_id="clp_ui",
        object_id="obj_ui",
        scene_id="scn_1",
        start=5 * tb,
        end=12 * tb,
    ), digests)

    # Act 3: metric_grid (12-18s)
    content = apply_ops(content, motion_block_ops(
        content,
        block_id="metric_grid",
        props={
            "eyebrow": "PROVEN SCALE",
            "title": "Built for institutional rigor",
            "items": [
                {"value": "10×", "label": "Faster Reports", "detail": "Automated diligence pipeline"},
                {"value": "98.4%", "label": "Source Traceability", "badge": "Audited"},
                {"value": "6", "label": "Valuation Models", "detail": "DCF, comparables & IP scoring"},
            ],
            "columns": 3,
            "count_up": True,
        },
        resources=[],
        clip_id="clp_metrics",
        object_id="obj_metrics",
        scene_id="scn_1",
        start=12 * tb,
        end=18 * tb,
    ), digests)

    # Act 4: closing_cta with protected light_pill logo (18-24s)
    content = apply_ops(content, motion_block_ops(
        content,
        block_id="closing_cta",
        props={
            "brand_name": "OxValue.AI",
            "tagline": "Trusted valuation intelligence for deep tech.",
            "cta_label": "Explore the platform",
            "url_text": "agent.oxvalue.ai",
            "logo_surface": "light_pill",
            "theme": "dark",
        },
        resources=[{
            "path": "media/logo_0.png",
            "snapshot_id": str(logo_id),
            "snapshot_digest": logo_digest,
            "content_type": "image/png",
        }],
        clip_id="clp_cta",
        object_id="obj_cta",
        scene_id="scn_1",
        start=18 * tb,
        end=24 * tb,
    ), digests)

    # Overlay pill_caption on Act 2 (lives on trk_mg_title, does not block main track crossfades)
    content = apply_ops(content, motion_block_ops(
        content,
        block_id="kinetic_title",
        props={
            "eyebrow": "LIVE INTERFACE",
            "headline": "Real-time Evidence Graph",
            "surface_style": "pill_caption",
            "position": "bottom_left",
        },
        resources=[],
        clip_id="clp_pill",
        object_id="obj_pill",
        scene_id="scn_1",
        start=5 * tb,
        end=12 * tb,
    ), digests)

    # Add centered crossfades across all 4 adjacent opaque main acts
    content = content.model_copy(update={
        "timeline": content.timeline.model_copy(update={
            "transitions": [
                Transition(transition_id="trn_1", from_clip_id="clp_hook", to_clip_id="clp_ui", kind="crossfade", duration=int(0.4 * tb)),
                Transition(transition_id="trn_2", from_clip_id="clp_ui", to_clip_id="clp_metrics", kind="crossfade", duration=int(0.4 * tb)),
                Transition(transition_id="trn_3", from_clip_id="clp_metrics", to_clip_id="clp_cta", kind="crossfade", duration=int(0.4 * tb)),
            ]
        })
    })

    validate_content(content, snapshots)
    spec = compile_video_spec(
        content,
        snapshots,
        composition_id=uuid4(),
        version_id=uuid4(),
        content_digest="d" * 64,
    )
    assert len(spec["transitions"]) == 3
    by_id = {c["clip_id"]: c for t in spec["tracks"] for c in t["clips"]}
    assert by_id["clp_hook"]["source"] is None
    assert by_id["clp_hook"]["end_frame"] == 150 + 6
    assert by_id["clp_ui"]["start_frame"] == 150 - 6
    assert by_id["clp_cta"]["object"]["props"]["logo_surface"] == "light_pill"
    assert by_id["clp_pill"]["object"]["props"]["surface_style"] == "pill_caption"


def test_transparent_motion_block_rejects_crossfade():
    from app.editing.edits import apply_ops

    tb = 90000
    content = _base_content(10)
    content = apply_ops(content, motion_block_ops(
        content,
        block_id="statement_hook",
        props={"headline": "Transparent opener", "show_backdrop": False},
        resources=[],
        clip_id="clp_a",
        object_id="obj_a",
        scene_id="scn_1",
        start=0,
        end=5 * tb,
    ), {})
    content = apply_ops(content, motion_block_ops(
        content,
        block_id="closing_cta",
        props={"brand_name": "OxValue", "tagline": "End", "show_backdrop": True},
        resources=[],
        clip_id="clp_b",
        object_id="obj_b",
        scene_id="scn_1",
        start=5 * tb,
        end=10 * tb,
    ), {})
    content = content.model_copy(update={
        "timeline": content.timeline.model_copy(update={
            "transitions": [
                Transition(transition_id="trn_bad", from_clip_id="clp_a", to_clip_id="clp_b", kind="crossfade", duration=int(0.4 * tb)),
            ]
        })
    })
    with pytest.raises(ValueError, match="show_backdrop=True"):
        compile_video_spec(
            content, {}, composition_id=uuid4(), version_id=uuid4(), content_digest="e" * 64
        )


def test_audio_gain_envelope_fades_and_ducking_compile_without_collapsed_frames():
    tb = 90000
    bgm_id = uuid4()
    bgm_digest = "f" * 64
    snapshots = {
        bgm_id: {
            "kind": "audio",
            "digest": bgm_digest,
            "storage_key": "music/bgm.mp3",
            "duration_ticks": 40 * tb,
            "meta": {},
        }
    }
    anim_dict = build_audio_gain_animation(
        object_id="obj_bgm",
        clip_start_ticks=0,
        clip_end_ticks=36 * tb,
        timebase=tb,
        fps_num=30,
        fps_den=1,
        fade_in_seconds=1.2,
        fade_out_seconds=2.0,
        duck_windows=[
            {"start_seconds": 1.0, "end_seconds": 8.0, "duck_db": -6.0, "ramp_seconds": 0.3},
            {"start_seconds": 10.0, "end_seconds": 18.0, "duck_db": -8.0, "ramp_seconds": 0.3},
        ],
    )
    assert anim_dict is not None
    anim = Animation.model_validate(anim_dict)
    assert anim.keyframes[0].at == 0 and anim.keyframes[0].value == 0.0
    assert anim.keyframes[-1].at == 36 * tb and anim.keyframes[-1].value == 0.0
    assert all(0.0 <= float(kf.value) <= 1.0 for kf in anim.keyframes)

    content = CompositionContent(
        settings=VersionSettings(width=1920, height=1080, timebase=tb),
        sources=[SourceBinding(snapshot_id=bgm_id, snapshot_digest=bgm_digest)],
        scenes=[Scene(scene_id="scn_1", range=TimeRange(start=0, end=36 * tb))],
        timeline=Timeline(tracks=[
            Track(
                track_id="trk_editor_music",
                kind="audio",
                role="music",
                order=0,
                clips=[
                    Clip(
                        clip_id="clp_bgm",
                        range=TimeRange(start=0, end=36 * tb),
                        scene_id=None,
                        source=ClipSource(
                            snapshot_id=bgm_id,
                            snapshot_digest=bgm_digest,
                            source_range=TimeRange(start=0, end=36 * tb),
                        ),
                        object=AudioObject(kind="audio", object_id="obj_bgm", gain_db=-24.0),
                        animations=[anim],
                    )
                ],
            )
        ]),
    )
    validate_content(content, snapshots)
    spec = compile_video_spec(
        content, snapshots, composition_id=uuid4(), version_id=uuid4(), content_digest="1" * 64
    )
    compiled_anim = spec["tracks"][0]["clips"][0]["animations"][0]
    assert compiled_anim["property"] == "audio.gain"
    frames = [kf["at"] for kf in compiled_anim["keyframes"]]
    assert frames == sorted(set(frames))


def test_swoosh_cut_catalog_and_digest_isolation():
    spec_a = build_sound_spec("swoosh_cut", {"length": 340, "pitch": 560}, seed=99)
    spec_b = build_sound_spec("swoosh_cut", {"length": 340, "pitch": 560}, seed=99)
    spec_c = build_sound_spec("swoosh_cut", {"length": 340, "pitch": 420}, seed=99)
    assert sound_spec_digest(spec_a) == sound_spec_digest(spec_b)
    assert sound_spec_digest(spec_a) != sound_spec_digest(spec_c)
