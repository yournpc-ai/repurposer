"""Pure component-v1 domain tests: no DB, LLM, HTTP or real renderer."""
from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.editing.schemas import (
    COMPONENT_DEPENDENCIES,
    GeneratorObject,
    ProgramOutput,
)
from app.editing.edits import apply_ops
from app.editing.director import ComponentDirection
from app.editing.service import translate_revision
from app.editing.templates import instantiate_component
from app.editing.validators import ContentValidationError, validate_content
from app.editing.video_spec import compile_video_spec
from app.models.schemas import DesignVideoArgs, ReviseVideoArgs
from app.tools.video import components
from app.tools.video import design as video_design
from test_editing_edits_pure import SNAPSHOT_FACTS, valid_content

VALID_CODE = """export default function Visual({ parameters }: { parameters: { label: string } }) {
  const frame = useCurrentFrame();
  return <AbsoluteFill style={{ opacity: frame / 60 }}>{parameters.label}</AbsoluteFill>;
}"""


def _content(*, code: str = VALID_CODE, parameters=None):
    content = valid_content()
    clip = next(c for t in content.timeline.tracks for c in t.clips if c.clip_id == "clp_bg")
    clip.object = GeneratorObject(
        kind="generator",
        object_id="obj_component",
        runtime="component-v1",
        code=code,
        parameters=parameters or {"label": "A real line"},
        output=ProgramOutput(
            width=640, height=360, fps=15, duration_frames=60, background="#101010"
        ),
        layout=clip.object.layout,
    )
    clip.source = None
    return content, clip


def test_component_digest_covers_source_parameters_output_and_dependency_lock():
    _, clip = _content()
    obj = clip.object
    payload = {
        "runtime": "component-v1",
        "code": obj.code,
        "parameters": obj.parameters,
        "output": obj.output.model_dump(mode="json"),
        "dependencies": COMPONENT_DEPENDENCIES,
    }
    expected = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert obj.program_digest() == expected
    assert obj.model_copy(update={"code": obj.code + "\n// change"}).program_digest() != expected
    assert obj.model_copy(update={"parameters": {"label": "Changed"}}).program_digest() != expected
    changed_output = obj.output.model_copy(update={"duration_frames": 61})
    assert obj.model_copy(update={"output": changed_output}).program_digest() != expected


def test_component_validates_quantization_and_compiles_to_plain_muted_video():
    content, clip = _content()
    validate_content(content, SNAPSHOT_FACTS)
    spec = compile_video_spec(
        content,
        SNAPSHOT_FACTS,
        composition_id=UUID("33333333-3333-3333-3333-333333333333"),
        version_id=UUID("44444444-4444-4444-4444-444444444444"),
        content_digest="c" * 64,
        generator_media={
            "obj_component": {
                "program_digest": clip.object.program_digest(),
                "media": {"storage_key": "generated/component.mp4", "digest": "d" * 64},
            }
        },
    )
    compiled = next(c for t in spec["tracks"] for c in t["clips"] if c["clip_id"] == "clp_bg")
    assert compiled["object"]["kind"] == "video"
    assert compiled["object"]["muted"] is True
    assert compiled["source"] == {
        "url": "generated/component.mp4",
        "digest": "d" * 64,
        "start_frame": 0,
        "end_frame": 120,
    }
    blob = json.dumps(spec).lower()
    for forbidden in ("component-v1", "tsx", "remotion", "react", "export default"):
        assert forbidden not in blob


def test_component_python_validation_keeps_structure_without_scanning_jsx_words():
    content, _ = _content(code="""export default function Visual() {
      // document and window are ordinary narration words here.
      return <AbsoluteFill><span>Our process · document · window · fetch</span></AbsoluteFill>;
    }""")
    validate_content(content, SNAPSHOT_FACTS)

    missing_export, _ = _content(code="const Visual = () => <div />;")
    with pytest.raises(ContentValidationError, match="default component export"):
        validate_content(missing_export, SNAPSHOT_FACTS)


def test_component_parameters_cannot_smuggle_external_resources():
    content, _ = _content(parameters={"asset": "https://example.test/a.png"})
    with pytest.raises(ContentValidationError, match="not a fixed resource"):
        validate_content(content, SNAPSHOT_FACTS)


def test_update_generator_changes_only_the_target_source_identity():
    base, original = _content()
    args = ReviseVideoArgs.model_validate({
        "base_ref": {
            "composition_id": "55555555-5555-5555-5555-555555555555",
            "composition_version_id": "66666666-6666-6666-6666-666666666666",
            "content_digest": "c" * 64,
        },
        "edits": [{
            "op": "update_generator",
            "clip_id": "clp_bg",
            "parameters": {"label": "Revised real line"},
        }],
    })
    updated = apply_ops(base, translate_revision(base, args), {})
    validate_content(updated, SNAPSHOT_FACTS)
    revised = next(c for t in updated.timeline.tracks for c in t.clips if c.clip_id == "clp_bg")
    assert revised.object.parameters == {"label": "Revised real line"}
    assert revised.object.program_digest() != original.object.program_digest()
    assert original.object.parameters == {"label": "A real line"}
    base_others = {
        c.clip_id: c for t in base.timeline.tracks for c in t.clips if c.clip_id != "clp_bg"
    }
    updated_others = {
        c.clip_id: c for t in updated.timeline.tracks for c in t.clips if c.clip_id != "clp_bg"
    }
    assert updated_others == base_others


def test_component_design_mode_keeps_first_consumer_free_of_external_material():
    args = DesignVideoArgs.model_validate({
        "mode": "component",
        "text": "Exact native title",
        "specific_instruction": "A line of narration drives a restrained kinetic diagram",
    })
    assert args.mode == "component"
    with pytest.raises(ValueError, match="takes no media materials"):
        DesignVideoArgs.model_validate({
            "mode": "component",
            "specific_instruction": "A diagram",
            "material_urls": ["https://example.test"],
        })


@pytest.mark.asyncio
async def test_exact_component_media_is_reused_and_revision_bakes_a_new_digest(monkeypatch):
    monkeypatch.setattr(components.settings, "component_bake_enabled", True)
    objects: dict[str, bytes] = {}

    async def exists(key: str) -> bool:
        return key in objects

    async def read(key: str) -> bytes:
        return objects[key]

    async def save(key: str, data: bytes, content_type: str | None = None) -> None:
        objects[key] = data

    calls = []

    async def fake_bake(obj):
        calls.append(obj.program_digest())
        return (
            b"\x00\x00\x00\x18ftypisom" + obj.program_digest().encode(),
            b"\x89PNG\r\n\x1a\n" + obj.program_digest().encode(),
            {"frames": obj.output.duration_frames, "preview_frame": 30},
        )

    monkeypatch.setattr(components.storage, "exists", exists)
    monkeypatch.setattr(components.storage, "read", read)
    monkeypatch.setattr(components.storage, "save", save)
    monkeypatch.setattr(components, "_bake", fake_bake)

    _, clip = _content()
    reused = []
    first = await components.ensure_component_clip(clip, on_reuse=reused.append)
    second = await components.ensure_component_clip(clip, on_reuse=reused.append)
    assert first == second
    assert calls == [clip.object.program_digest()]
    assert reused == [False, True]

    revised_clip = clip.model_copy(
        update={"object": clip.object.model_copy(update={"parameters": {"label": "New"}})}
    )
    revised = await components.ensure_component_clip(revised_clip)
    assert revised["program_digest"] != first["program_digest"]
    assert revised["media"]["digest"] != first["media"]["digest"]
    assert calls == [clip.object.program_digest(), revised_clip.object.program_digest()]


@pytest.mark.asyncio
async def test_component_bake_is_fail_closed_before_cache_or_public_design(monkeypatch):
    monkeypatch.setattr(components.settings, "component_bake_enabled", False)

    async def cache_must_not_be_read(*args, **kwargs):
        raise AssertionError("disabled component execution touched the cache")

    monkeypatch.setattr(components.storage, "exists", cache_must_not_be_read)
    _, clip = _content()
    with pytest.raises(components.ComponentError, match="no.*isolated component runner"):
        await components.ensure_component_clip(clip)

    async def director_must_not_run(**kwargs):
        raise AssertionError("disabled component execution paid for a Director call")

    monkeypatch.setattr(video_design.component_director, "call", director_must_not_run)
    args = DesignVideoArgs.model_validate({
        "mode": "component",
        "specific_instruction": "A restrained animated diagram",
    })
    with pytest.raises(components.ComponentError, match="no.*isolated component runner"):
        await video_design._design_locked(
            None,
            owner_id=UUID("11111111-1111-1111-1111-111111111111"),
            project_id=UUID("22222222-2222-2222-2222-222222222222"),
            args=args,
            request_id=None,
        )


@pytest.mark.asyncio
async def test_component_narration_reaches_director_and_stays_native(monkeypatch):
    monkeypatch.setattr(components.settings, "component_bake_enabled", True)
    args = DesignVideoArgs.model_validate({
        "mode": "component",
        "specific_instruction": "A restrained diagram driven by the supplied talk",
        "narration": "Our process makes the document clear.",
    })
    director_calls = []
    instantiate_calls = []
    direction = ComponentDirection(
        name=None,
        language="en",
        title=None,
        intent="A clear process diagram",
        visual_description="Three labeled stages connect in sequence",
        duration_seconds=4,
        background="#101010",
        parameters={"label": "Process"},
        code=VALID_CODE,
    )

    async def fake_director(**kwargs):
        director_calls.append(kwargs)
        return direction

    async def fake_voice(*args, **kwargs):
        return {"provider": "minimax", "model": "speech", "voice_id": "voice-1"}

    def fake_instantiate(received, **kwargs):
        instantiate_calls.append((received, kwargs))
        return []

    composition = SimpleNamespace(id=UUID("55555555-5555-5555-5555-555555555555"))
    version = SimpleNamespace(
        id=UUID("66666666-6666-6666-6666-666666666666"),
        version=1,
        content_digest="c" * 64,
    )

    async def fake_apply(*args, **kwargs):
        return composition, version, False

    async def no_facts(*args, **kwargs):
        return {}

    monkeypatch.setattr(video_design.component_director, "call", fake_director)
    monkeypatch.setattr(video_design, "_resolve_narration_voice", fake_voice)
    monkeypatch.setattr(video_design, "instantiate_component", fake_instantiate)
    monkeypatch.setattr(video_design, "apply_composition_edits", fake_apply)
    monkeypatch.setattr(video_design, "content_of", lambda value: valid_content())
    monkeypatch.setattr(video_design, "snapshot_facts", no_facts)
    monkeypatch.setattr(video_design, "storyboard_payload", lambda *args, **kwargs: {"scenes": []})
    monkeypatch.setattr(video_design, "version_read_dict", lambda *args: {"version": 1})

    await video_design._design_locked(
        None,
        owner_id=UUID("11111111-1111-1111-1111-111111111111"),
        project_id=UUID("22222222-2222-2222-2222-222222222222"),
        args=args,
        request_id=None,
    )
    assert director_calls[0]["narration"] == args.narration
    assert instantiate_calls[0][1]["narration"] == args.narration
    assert instantiate_calls[0][1]["narration_voice"]["language"] == "en"

    native_ops = instantiate_component(
        direction,
        narration=args.narration,
        narration_voice={
            "provider": "minimax", "model": "speech", "voice_id": "voice-1", "language": "en",
        },
    )
    objects = [op["clip"]["object"] for op in native_ops if op["op"] == "add_clip"]
    speech = next(obj for obj in objects if obj["kind"] == "speech")
    caption = next(obj for obj in objects if obj["kind"] == "text" and obj.get("caption"))
    assert speech["text"] == args.narration
    assert caption["text"] == args.narration
    assert caption["caption"]["speech_object_id"] == speech["object_id"]


@pytest.mark.asyncio
async def test_static_bake_failure_never_writes_a_success_manifest(monkeypatch):
    monkeypatch.setattr(components.settings, "component_bake_enabled", True)

    async def no_cached_media(key):
        return False

    async def static_failure(obj):
        raise components.ComponentError("identical pixels at every sampled frame")

    async def save_must_not_run(*args, **kwargs):
        raise AssertionError("static component output was cached as successful media")

    monkeypatch.setattr(components.storage, "exists", no_cached_media)
    monkeypatch.setattr(components, "_bake", static_failure)
    monkeypatch.setattr(components.storage, "save", save_must_not_run)
    _, clip = _content()
    with pytest.raises(components.ComponentError, match="identical pixels"):
        await components.ensure_component_clip(clip)
