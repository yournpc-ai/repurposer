"""Pure tests for the video-spec compiler (editing → family="video" spec).

Locks the quantization handoff (ticks → frames at the ONE seat), the
three-time-domain separation on the wire (source window in source frames,
clip window in output frames, keyframes clip-local), the static-source law
(image clips carry NO source window), and the provenance pin.
"""

from __future__ import annotations

import pytest

from app.editing.video_spec import CompileError, compile_video_spec
from test_editing_edits_pure import SNAPSHOT_FACTS, valid_content

COMP_ID = "33333333-3333-3333-3333-333333333333"
VER_ID = "44444444-4444-4444-4444-444444444444"


def compile_sample():
    content = valid_content()
    return compile_video_spec(
        content,
        SNAPSHOT_FACTS,
        composition_id=COMP_ID,
        version_id=VER_ID,
        content_digest="c" * 64,
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


def test_provenance_is_identity_not_renderer_state():
    spec = compile_sample()
    # No renderer concepts may leak into the contract surface.
    import json

    blob = json.dumps(spec).lower()
    for banned in ("remotion", "react", "component", "jsx"):
        assert banned not in blob


def test_missing_snapshot_facts_fail_compile():
    content = valid_content()
    with pytest.raises(CompileError, match="not resolved"):
        compile_video_spec(
            content, {}, composition_id=COMP_ID, version_id=VER_ID, content_digest="c" * 64
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
