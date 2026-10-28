"""Pure tests for the video-spec compiler (editing → family="video" spec).

Locks the quantization handoff (ticks → frames at the ONE seat), the
three-time-domain separation on the wire (source window in source frames,
clip window in output frames, keyframes clip-local), the static-source law
(image clips carry NO source window), and the provenance pin.
"""

from __future__ import annotations

import json
import pytest

from app.editing.video_spec import CompileError, compile_video_spec
from app.editing.schemas import (
    Clip,
    GeneratorObject,
    LayoutBox,
    ProgramOutput,
    ShapeObject,
    TimeRange,
    Track,
    VideoObject,
)
from test_editing_edits_pure import SNAPSHOT_FACTS, valid_content

COMP_ID = "33333333-3333-3333-3333-333333333333"
VER_ID = "44444444-4444-4444-4444-444444444444"


def compile_sample():
    content = valid_content()
    content.timeline.tracks.append(
        Track(
            track_id="trk_shape", kind="visual", role="effect", order=2,
            clips=[Clip(
                clip_id="clp_shape", range=TimeRange(start=0, end=360000), scene_id=None,
                source=None,
                object=ShapeObject(
                    kind="shape", object_id="obj_shape", shape="rect",
                    layout=LayoutBox(x=40, y=50, width=320, height=180),
                    fill="#3366FF", corner_radius=24,
                ),
                animations=[],
            )],
        )
    )
    generator = GeneratorObject(
        kind="generator", object_id="obj_generator", runtime="drawing-v1",
        code="function render(ctx) { return []; }",
        output=ProgramOutput(
            width=640, height=360, fps=15, duration_frames=60, background="#000000"
        ),
        layout=LayoutBox(x=0, y=0, width=1920, height=1080),
    )
    content.timeline.tracks.append(
        Track(
            track_id="trk_generator", kind="visual", role="main", order=3,
            clips=[Clip(
                clip_id="clp_generator", range=TimeRange(start=0, end=360000), scene_id=None,
                source=None, object=generator, animations=[],
            )],
        )
    )
    return compile_video_spec(
        content,
        SNAPSHOT_FACTS,
        composition_id=COMP_ID,
        version_id=VER_ID,
        content_digest="c" * 64,
        generator_media={
            "obj_generator": {
                "program_digest": generator.program_digest(),
                "media": {"storage_key": "generated/program.mp4", "digest": "d" * 64},
            }
        },
    )


def test_spec_shape_and_quantization():
    spec = compile_sample()
    assert spec["family"] == "video" and spec["format"] == 1
    assert spec["fps"] == {"num": 30, "den": 1}
    assert spec["width"] == 1920 and spec["height"] == 1080
    assert spec["duration_frames"] == 120  # 4s @ 30fps
    assert spec["provenance"] == {
        "composition_id": COMP_ID,
        "composition_version_id": VER_ID,
        "content_digest": "c" * 64,
    }

    tracks = {t["track_id"]: t for t in spec["tracks"]}
    clips = {c["clip_id"]: c for t in spec["tracks"] for c in t["clips"]}

    # Output windows quantized at the single seat (0.3s fade-in = 9 frames).
    assert clips["clp_bg"]["start_frame"] == 0 and clips["clp_bg"]["end_frame"] == 120
    assert clips["clp_title"]["start_frame"] == 30 and clips["clp_title"]["end_frame"] == 120
    fade = clips["clp_title"]["animations"][0]
    assert fade["keyframes"][0]["at"] == 0 and fade["keyframes"][1]["at"] == 9

    # Static source: image clip has a source URL but NO source window.
    assert clips["clp_bg"]["source"] == {"url": "snapshots/img.png", "digest": "a" * 64}

    # Audio: 1× source window in SOURCE frames at output fps.
    bed = tracks["trk_music"]["clips"][0]
    assert bed["source"] == {
        "url": "snapshots/audio.wav",
        "digest": "b" * 64,
        "start_frame": 0,
        "end_frame": 120,
    }
    assert bed["object"] == {"kind": "audio", "object_id": "obj_bed", "gain_db": -20.0}

    # Text clip: an explicit null source, never an absent key.
    assert clips["clp_title"]["source"] is None
    assert clips["clp_shape"]["object"]["shape"] == "rect"
    assert clips["clp_shape"]["object"]["fill"] == "#3366FF"
    assert clips["clp_shape"]["source"] is None
    assert clips["clp_generator"]["object"]["kind"] == "video"
    assert clips["clp_generator"]["object"]["muted"] is True
    assert clips["clp_generator"]["source"] == {
        "url": "generated/program.mp4", "digest": "d" * 64,
        "start_frame": 0, "end_frame": 120,
    }
    assert "drawing-v1" not in json.dumps(clips["clp_generator"])
    assert "function render" not in json.dumps(clips["clp_generator"])


def test_provenance_is_identity_not_renderer_state():
    spec = compile_sample()
    # No renderer concepts may leak into the contract surface.
    import json

    blob = json.dumps(spec).lower()
    for banned in ("remotion", "react", "component", "jsx"):
        assert banned not in blob


def test_video_source_window_preserves_one_x_output_frames_and_audio_controls():
    content = valid_content()
    clip = next(c for t in content.timeline.tracks for c in t.clips if c.clip_id == "clp_bg")
    snapshot_id = clip.source.snapshot_id
    clip.object = VideoObject(
        kind="video", object_id="obj_bg", layout=clip.object.layout,
        fit="contain", gain_db=-6.0, muted=True,
    )
    clip.source.source_range = TimeRange(start=45000, end=405000)  # 0.5–4.5s
    facts = {**SNAPSHOT_FACTS, snapshot_id: {
        **SNAPSHOT_FACTS[snapshot_id], "kind": "video", "duration_ticks": 540000,
        "storage_key": "snapshots/video.mp4",
    }}
    spec = compile_video_spec(
        content, facts, composition_id=COMP_ID, version_id=VER_ID, content_digest="c" * 64
    )
    compiled = next(c for t in spec["tracks"] for c in t["clips"] if c["clip_id"] == "clp_bg")
    assert compiled["source"]["start_frame"] == 15
    assert compiled["source"]["end_frame"] == 135  # exact 120-frame output window
    assert compiled["object"]["fit"] == "contain"
    assert compiled["object"]["gain_db"] == -6.0
    assert compiled["object"]["muted"] is True


def test_missing_snapshot_facts_fail_compile():
    content = valid_content()
    with pytest.raises(CompileError, match="not resolved"):
        compile_video_spec(
            content, {}, composition_id=COMP_ID, version_id=VER_ID, content_digest="c" * 64
        )


def test_generator_requires_media_for_the_exact_program():
    content = valid_content()
    clip = next(c for t in content.timeline.tracks for c in t.clips if c.clip_id == "clp_bg")
    clip.object = GeneratorObject(
        kind="generator", object_id="obj_bg", runtime="drawing-v1",
        code="function render(ctx) { return []; }",
        output=ProgramOutput(
            width=640, height=360, fps=15, duration_frames=60, background="#000000"
        ),
        layout=clip.object.layout,
    )
    clip.source = None
    with pytest.raises(CompileError, match="exact program"):
        compile_video_spec(
            content, SNAPSHOT_FACTS, composition_id=COMP_ID, version_id=VER_ID,
            content_digest="c" * 64,
        )


def test_spec_round_trips_the_ts_schema():
    """The compiled spec must satisfy the wire contract the renderer
    validates against (packages/video-spec zod schema)."""
    import json
    import subprocess
    from pathlib import Path

    spec = compile_sample()
    repo = Path(__file__).resolve().parents[3]
    probe = (
        "import { readFileSync } from 'node:fs';"
        "import { videoSpecSchema } from '@repurposer/video-spec';"
        "const spec = JSON.parse(readFileSync(0, 'utf8'));"
        "const r = videoSpecSchema.safeParse(spec);"
        "if (!r.success) { console.error(JSON.stringify(r.error.issues)); process.exit(1); }"
    )
    proc = subprocess.run(
        ["node", "--import", "tsx", "--input-type=module", "-e", probe],
        input=json.dumps(spec),
        capture_output=True,
        text=True,
        cwd=repo / "apps" / "render",
    )
    assert proc.returncode == 0, proc.stderr
