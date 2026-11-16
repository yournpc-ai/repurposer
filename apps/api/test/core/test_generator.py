"""Knowledge-explainer drawing contract journey; no DB, LLM, HTTP or paid provider."""
from __future__ import annotations

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
from app.editing.templates import instantiate_aligned_narration
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
