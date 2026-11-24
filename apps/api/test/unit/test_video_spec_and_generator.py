"""Layer 0 pure contracts: video-spec compiler, Zod parity, and draw-2d/Remotion generator budgets."""

from __future__ import annotations
import pytest

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


from test.support.composition_fixtures import SNAPSHOT_FACTS, valid_content


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
        kind="generator", object_id="obj_generator", producer="draw-2d",
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


def test_video_spec_enforces_the_current_production_frame_cap():
    content = valid_content()
    content.timeline.tracks[0].clips[0].range = TimeRange(start=0, end=10803000)
    with pytest.raises(CompileError, match="3600 frames"):
        compile_video_spec(
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
    assert clips["clp_shape"]["object"]["shape"] == "rect"
    assert clips["clp_shape"]["object"]["fill"] == "#3366FF"
    assert clips["clp_shape"]["source"] is None
    assert clips["clp_generator"]["object"]["kind"] == "video"
    assert clips["clp_generator"]["object"]["muted"] is True
    assert clips["clp_generator"]["source"] == {
        "url": "generated/program.mp4", "digest": "d" * 64,
        "start_frame": 0, "end_frame": 120,
    }
    assert "draw-2d" not in json.dumps(clips["clp_generator"])
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
        kind="generator", object_id="obj_bg", producer="draw-2d",
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


@pytest.mark.parity
def test_spec_round_trips_the_ts_schema():
    """The compiled spec must satisfy the wire contract the renderer
    validates against (packages/video-spec zod schema)."""
    import json
    import subprocess
    from pathlib import Path

    spec = compile_sample()
    repo = Path(__file__).resolve().parents[4]
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


# --- Generator & aligned narration contracts ---

import hashlib


import json


from types import SimpleNamespace


from uuid import UUID, uuid4


import pytest


from pydantic import TypeAdapter


from app.editing.alignment import NarrationPayload


from app.editing.director import (
    AlignedNarrationDirection,
    validate_aligned_narration_direction,
)


from app.editing.edits import Op, apply_ops


from app.editing.schemas import (
    REMOTION_RESOURCE_LIMIT,
    CompositionContent,
    GeneratorObject,
    NarrationAlignmentRef,
    RemotionProjectSource,
    RemotionResource,
)


from app.editing.aligned_narration import instantiate_aligned_narration


from app.editing.validators import validate_content


from app.editing.video_spec import compile_video_spec


from app.tools.video import programs


SCRIPT = "清晰的表达，让专业知识被更多人理解。"


VALID_CODE = """function render(ctx) {
  const progress = ctx.frame / Math.max(1, ctx.durationFrames - 1);
  const unit = ctx.width / 24;
  const gather = unit * (1 - progress) * 3;
  return [
    { kind: 'rect', x: ctx.width * 0.12 + gather, y: ctx.height * 0.28,
      width: unit * 5, height: ctx.height * 0.12, fill: '#334155', opacity: 0.9 },
    { kind: 'ellipse', x: ctx.width * 0.52, y: ctx.height * 0.25 + gather,
      width: unit * 2, height: unit * 2, fill: '#38BDF8', stroke: '#F8FAFC', stroke_width: 2 },
    { kind: 'polygon', points: [[ctx.width * 0.68, ctx.height * 0.3],
      [ctx.width * 0.76, ctx.height * 0.3 + gather], [ctx.width * 0.72, ctx.height * 0.46]],
      fill: '#F59E0B', stroke: '#F8FAFC', stroke_width: 2 },
    { kind: 'line', points: [[ctx.width * 0.2, ctx.height * 0.65],
      [ctx.width * (0.45 + progress * 0.25), ctx.height * 0.65]],
      stroke: '#F8FAFC', stroke_width: 4 }
  ];
}"""


INVALID_CODE = """function render(ctx) {
  return [{ kind: 'rect', x: ctx.frame, y: 20, width: 100, height: 80,
    fill: '#38BDF8', stroke: '#FFFFFF', corner_radius: 12 }];
}"""


def _aligned_content(code: str):
    words = []
    tick = 0
    for index, char in enumerate(SCRIPT):
        if char in "，。":
            continue
        words.append({
            "word_id": f"w{len(words) + 1:06d}", "text": char,
            "text_start": index, "text_end": index + 1,
            "start_tick": tick, "end_tick": tick + 10000, "timing": "anchored",
        })
        tick += 10000
    payload = NarrationPayload.model_validate({
        "source_timebase": 90000,
        "duration_ticks": tick,
        "sentences": [{
            "sentence_id": "s0001", "text": SCRIPT, "text_start": 0,
            "text_end": len(SCRIPT), "start_tick": 0, "end_tick": tick,
            "match": 1.0, "status": "aligned", "words": words,
            "semantics": {
                "role": "summary", "weight": "main", "entities": ["清晰的表达"],
                "needs": ["native_text", "generator"],
                "emphasis_word_ids": ["w000001", "w000002"],
            },
        }],
    })
    direction = AlignedNarrationDirection.model_validate({
        "name": "清晰表达", "language": "zh", "background": "#0B1020",
        "scenes": [{
            "sentence_ids": ["s0001"], "intent": "把复杂知识整理成清晰结构",
            "visual_description": "分散图形汇聚成有序关系，文字与字幕保持原生",
            "lines": [SCRIPT], "size": "large", "align": "center",
            "generator": {"code": code, "parameters": {"density": 4}},
        }],
    })
    validate_aligned_narration_direction(
        direction, sentences=[("s0001", SCRIPT)], require_generator=True,
    )
    snapshot = SimpleNamespace(id=uuid4(), digest="a" * 64)
    alignment = NarrationAlignmentRef(
        alignment_id=uuid4(), content_digest="b" * 64,
        audio_snapshot_id=snapshot.id, audio_digest=snapshot.digest,
    )
    ops = TypeAdapter(list[Op]).validate_python(instantiate_aligned_narration(
        direction, payload=payload, alignment=alignment, snapshot=snapshot,
    ))
    content = apply_ops(
        CompositionContent(settings={"width": 1920, "height": 1080}),
        ops,
        {snapshot.id: snapshot.digest},
    )
    facts = {snapshot.id: {
        "digest": snapshot.digest, "kind": "audio", "duration_ticks": tick,
        "owner_id": uuid4(), "storage_key": "snapshots/narration.mp3",
    }}
    validate_content(content, facts)
    generator = next(
        clip for track in content.timeline.tracks for clip in track.clips
        if isinstance(clip.object, GeneratorObject)
    )
    return content, generator, facts


@pytest.mark.asyncio
async def test_valid_aligned_fixture_executes_and_compiles_to_fixed_media(monkeypatch):
    objects: dict[str, bytes] = {}

    async def exists(key: str) -> bool:
        return key in objects

    async def read(key: str) -> bytes:
        return objects[key]

    async def save(key: str, data: bytes, content_type: str | None = None) -> None:
        objects[key] = data

    async def store(data: bytes, suffix: str, mime_type: str):
        digest = hashlib.sha256(data).hexdigest()
        key = f"test-generator/{digest}{suffix}"
        objects[key] = data
        return key, digest

    monkeypatch.setattr(programs.storage, "exists", exists)
    monkeypatch.setattr(programs.storage, "read", read)
    monkeypatch.setattr(programs.storage, "save", save)
    monkeypatch.setattr(programs, "store_source_bytes", store)

    content, clip, facts = _aligned_content(VALID_CODE)
    assert isinstance(clip.object, GeneratorObject)
    manifest = await programs.ensure_generator_clip(clip)
    assert manifest["program_digest"] == clip.object.program_digest()
    assert manifest["diagnostics"]["unique_frames"] > 1
    assert hashlib.sha256(objects[manifest["media"]["storage_key"]]).hexdigest() == manifest["media"]["digest"]
    spec = compile_video_spec(
        content, facts,
        composition_id=UUID("33333333-3333-3333-3333-333333333333"),
        version_id=UUID("44444444-4444-4444-4444-444444444444"),
        content_digest="c" * 64,
        generator_media={clip.object.object_id: manifest},
    )
    compiled = next(c for t in spec["tracks"] for c in t["clips"] if c["clip_id"] == clip.clip_id)
    assert compiled["object"]["kind"] == "video"
    assert compiled["source"]["url"] == manifest["media"]["storage_key"]
    assert compiled["source"]["digest"] == manifest["media"]["digest"]
    serialized = json.dumps(spec, ensure_ascii=False)
    for forbidden in ("draw-2d", "NarrationAlignment", "React", "Remotion"):
        assert forbidden not in serialized


@pytest.mark.asyncio
async def test_rect_stroke_and_corner_fixture_is_rejected_before_media_or_version(monkeypatch):
    objects: dict[str, bytes] = {}

    async def exists(key: str) -> bool:
        return key in objects

    async def save(*args, **kwargs):
        raise AssertionError("invalid commands must not save fixed media or a manifest")

    monkeypatch.setattr(programs.storage, "exists", exists)
    monkeypatch.setattr(programs.storage, "save", save)
    _, clip, _ = _aligned_content(INVALID_CODE)
    with pytest.raises(programs.ProgramError) as caught:
        await programs.ensure_generator_clip(clip)
    diagnostic = str(caught.value)
    assert "invalid drawing commands" in diagnostic
    assert "stroke" in diagnostic and "corner_radius" in diagnostic
    assert "extra_forbidden" in diagnostic
    assert objects == {}


def _fixed_resource(index: int) -> RemotionResource:
    return RemotionResource(
        path=f'assets/card-{index}.png', snapshot_id=uuid4(),
        snapshot_digest=hashlib.sha256(f'card-{index}'.encode()).hexdigest(),
        content_type='image/png',
    )


def test_generator_resource_collection_budget_accepts_deck_scale_and_rejects_overflow():
    from app.editing.director import ComponentProjectAnswer

    resources = [_fixed_resource(index) for index in range(REMOTION_RESOURCE_LIMIT)]
    payload = {
        'entry': 'src/index.tsx', 'composition_id': 'Deck',
        'files': [
            {'path': 'src/index.tsx', 'content': 'export default function Deck() { return null }'},
            {'path': 'src/shared.ts', 'content': 'export const answer = 42'},
        ],
        'props': {},
        'props_schema': {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False},
    }
    assert len(RemotionProjectSource(**payload, resources=resources).resources) == 64
    assert len(ComponentProjectAnswer(**payload, resources=resources).resources) == 64
    with pytest.raises(ValueError):
        RemotionProjectSource(**payload, resources=[*resources, _fixed_resource(64)])
    with pytest.raises(ValueError):
        ComponentProjectAnswer(**payload, resources=[*resources, _fixed_resource(64)])


def test_generator_project_accepts_json_data_but_keeps_a_typescript_entry():
    entry = {'path': 'src/index.tsx', 'content': 'export const entry = true'}
    layout = {'path': 'src/layout.json', 'content': '{"camera":{"x":320}}\n'}
    payload = dict(composition_id='Layout', props_schema={}, files=[entry, layout])
    project = RemotionProjectSource(entry=entry['path'], **payload)
    assert project.files[1].digest == hashlib.sha256(layout['content'].encode()).hexdigest()
    with pytest.raises(ValueError, match=r'\.ts or \.tsx'):
        RemotionProjectSource(entry=layout['path'], **payload)
    with pytest.raises(ValueError, match='valid JSON'):
        RemotionProjectSource(
            entry=entry['path'],
            **{**payload, 'files': [entry, {**layout, 'content': '{"camera":}'}]},
        )


@pytest.mark.asyncio
async def test_generator_collection_keeps_single_and_total_resource_byte_budgets(monkeypatch):
    from app.tools.video import components

    data = bytes(11 * 1024 * 1024)
    digest = hashlib.sha256(data).hexdigest()
    resources = [
        _fixed_resource(index).model_copy(update={'snapshot_digest': digest})
        for index in range(3)
    ]
    snapshots = {}

    for resource in resources:
        snapshots[resource.snapshot_id] = {
            'kind': 'image', 'digest': resource.snapshot_digest,
            'storage_key': resource.path,
        }

    async def read(_key):
        return data

    monkeypatch.setattr(components.storage, 'read', read)
    obj = SimpleNamespace(project=SimpleNamespace(resources=resources))
    with pytest.raises(components.ComponentError, match='byte budget'):
        await components._fixed_resources(obj, snapshots)

