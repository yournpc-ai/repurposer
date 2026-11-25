"""Editing splits and authoring — unit contracts."""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.agents.candidate_correction import (
    CandidateCorrectionArgs,
    CandidateRecord,
    CandidateScope,
    apply_correction,
)
from app.editing.revisions import RevisionTargetAmbiguityError, expand_revision_op, fixed_visual_ops
from app.editing.schemas import CompositionContent
from app.skills.package_session import SkillPackageSession
from test.support.revision_fixtures import (
    VIDEO_DIGEST,
    VIDEO_ID,
    revision_args,
    revision_content,
    snapshot_facts,
)

pytestmark = pytest.mark.unit


def test_native_create_and_high_level_revision_wires_stay_closed():
    from app.chat.editor_create import CreateVideoArgs

    assert CreateVideoArgs.model_json_schema()["additionalProperties"] is False

    from app.chat.editor import InsertVisualArgs

    raw = {
        "source_id": str(VIDEO_ID), "start_seconds": 4, "end_seconds": 8,
        "position": "lower-right", "width_ratio": 0.28,
    }
    with pytest.raises(ValidationError) as raised:
        InsertVisualArgs.model_validate(raw)
    import json

    errors = json.loads(raised.value.json(include_input=False, include_url=False))
    record = CandidateRecord.create(
        tool_name="insert_visual",
        arguments=raw,
        errors=errors,
        schema=InsertVisualArgs.model_json_schema(),
        scope=CandidateScope(owner_id=str(uuid4()), conversation_id=str(uuid4())),
        base_keys=frozenset({f"snapshot:{VIDEO_ID}:{VIDEO_DIGEST}"}),
        call_id="call_overlay",
    )
    diagnostic = record.diagnostic()
    assert "candidate" not in diagnostic
    assert diagnostic["candidate_id"] == record.candidate_id
    assert diagnostic["candidate_digest"] == record.candidate_digest
    assert diagnostic["errors"][0]["original_value"] == "lower-right"
    assert record.arguments["position"] == "lower-right"
    request = CandidateCorrectionArgs.model_validate(
        {
            "candidate_id": record.candidate_id,
            "candidate_digest": record.candidate_digest,
            "mode": "patch",
            "corrections": [{"error_id": "error_1", "value": "bottom_right"}],
        }
    ).root
    merged = apply_correction(record, request)
    corrected = InsertVisualArgs.model_validate(merged.arguments)
    assert corrected.position == "bottom_right"
    assert corrected.source_id == VIDEO_ID
    assert record.base_keys == frozenset({f"snapshot:{VIDEO_ID}:{VIDEO_DIGEST}"})


def test_ambiguous_target_returns_candidates_without_ops():
    owner = uuid4()
    content = revision_content()
    track, clip = next(
        (track, clip)
        for track in content.timeline.tracks
        for clip in track.clips
        if clip.clip_id == "clp_open_name"
    )
    duplicate_track = deepcopy(track)
    duplicate_track.track_id = "trk_duplicate"
    duplicate_track.order = 99
    content.timeline.tracks.append(duplicate_track)
    args = revision_args(
        SimpleNamespace(composition_id=uuid4(), id=uuid4(), content_digest="d" * 64),
        {"op": "set_text", "clip_id": clip.clip_id, "text": "Changed"},
    )
    with pytest.raises(RevisionTargetAmbiguityError) as raised:
        expand_revision_op(args.ops[0], content, facts=snapshot_facts(owner))
    assert len(raised.value.candidates) == 2

    omitted = revision_args(
        SimpleNamespace(composition_id=uuid4(), id=uuid4(), content_digest="d" * 64),
        {"op": "set_text", "text": "Changed"},
    )
    with pytest.raises(RevisionTargetAmbiguityError) as missing:
        expand_revision_op(omitted.ops[0], content, facts=snapshot_facts(owner))
    assert missing.value.candidates
    assert all("text" in candidate for candidate in missing.value.candidates)


@pytest.mark.asyncio
async def test_settled_skill_text_receipts_restore_only_same_owner_version_and_digest(tmp_path):
    from app.models.schemas import BuiltInSkillReference
    from app.skills.package_reader import SkillPackageReader

    skill = BuiltInSkillReference(kind="builtin", skill_id="promo-video", version="1.0.0")
    owner = uuid4()
    source_package = SkillPackageSession(SkillPackageReader(root=tmp_path))
    paths = [
        "references/sequences/product-evidence.md",
        "references/shots/opening/brand-emergence.md",
        "references/shots/camera/evidence-push.md",
        "references/shots/outro/next-step-lockup.md",
    ]
    for path in paths:
        file = tmp_path / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(f"# {path}")
    reads = []
    for path in paths:
        source = await source_package.reader.read_text(path)
        reads.append({
            "path": path,
            "digest": source.digest,
            "kind": "reference",
            "offset": 0,
            "truncated": False,
        })
    package = SkillPackageSession(SkillPackageReader(root=tmp_path))
    receipt = {
        "package_identity": package.receipt_identity(skill),
        "skill_reference": skill.model_dump(mode="json"),
        "owner_id": str(owner),
        "reads": reads,
        "preview_checks": [{"shot_id": "evidence-push", "available": True}],
        "media_files": 1,
    }
    assert await package.restore_text_reads(receipt, skill=skill, owner_id=owner) == 4
    assert {(item["path"], item["digest"]) for item in package.reads} == {
        (item["path"], item["digest"]) for item in reads
    }
    assert package.provenance["preview_checks"] == []
    assert package.media_files == 0 and not package._media_cache

    changed_version = skill.model_copy(update={"version": "2.0.0"})
    other = SkillPackageSession(SkillPackageReader(root=tmp_path))
    assert await other.restore_text_reads(receipt, skill=changed_version, owner_id=owner) == 0
    foreign = SkillPackageSession(SkillPackageReader(root=tmp_path))
    assert await foreign.restore_text_reads(receipt, skill=skill, owner_id=uuid4()) == 0

    changed_reads = deepcopy(reads)
    changed_reads[2]["digest"] = "f" * 64
    stale = SkillPackageSession(SkillPackageReader(root=tmp_path))
    assert await stale.restore_text_reads(
        {**receipt, "reads": changed_reads}, skill=skill, owner_id=owner
    ) == 3
    assert changed_reads[2]["digest"] not in {item["digest"] for item in stale.reads}


def test_video_overlay_checks_the_source_window_and_aspect_before_adding_any_ops():
    content = revision_content()
    fact = snapshot_facts(uuid4())[VIDEO_ID]
    args = dict(source_id=VIDEO_ID, identity=uuid4().hex, scene_id="proof", start=360000,
                end=540000, position="bottom_right", width_ratio=0.28, margin_px=48)
    with pytest.raises(ValueError, match="real duration"):
        fixed_visual_ops(content, {**fact, "duration_ticks": 90000}, **args)
    with pytest.raises(ValueError, match="aspect"):
        fixed_visual_ops(content, fact, **{**args, "width_ratio": 0.95})
    assert content == revision_content()


@pytest.mark.asyncio
async def test_generic_scene_video_window_preserves_each_timebase_and_fails_closed():
    from app.tools.video.design import (
        CandidateDesignError,
        CompositionSceneAuthoring,
        _expand_scene_authoring,
    )

    owner = uuid4()
    facts = snapshot_facts(owner)
    content = CompositionContent(
        settings={"timebase": 45000, "width": 1920, "height": 1080},
        scenes=[{
            "scene_id": "proof",
            "range": {"start": 0, "end": 180000},
            "intent": "Show the source",
            "speech_clip_ids": [],
        }],
        timeline={"tracks": [{
            "track_id": "trk_main",
            "kind": "visual",
            "role": "main",
            "order": 0,
            "clips": [],
        }], "transitions": []},
    ).model_dump(mode="json")
    scene = CompositionSceneAuthoring.model_validate({
        "scene_id": "proof",
        "snapshot_id": str(VIDEO_ID),
        "source_start_seconds": 1,
        "source_end_seconds": 5,
    })
    expanded = await _expand_scene_authoring(deepcopy(content), scene, facts)
    clip = expanded["timeline"]["tracks"][0]["clips"][0]
    assert clip["range"] == {"start": 0, "end": 180000}
    assert clip["source"]["source_range"] == {"start": 90000, "end": 450000}
    assert clip["object"]["kind"] == "video"

    original = deepcopy(content)
    with pytest.raises(CandidateDesignError) as raised:
        await _expand_scene_authoring(
            deepcopy(content),
            CompositionSceneAuthoring.model_validate({
                "scene_id": "proof",
                "snapshot_id": str(VIDEO_ID),
                "source_start_seconds": 8,
                "source_end_seconds": 12,
            }),
            facts,
        )
    assert raised.value.issues[0]["type"] == "source_too_short"
    assert content == original
    with pytest.raises(ValidationError):
        CompositionSceneAuthoring.model_validate({
            "scene_id": "proof",
            "snapshot_id": str(VIDEO_ID),
            "source_start_seconds": 5,
            "source_end_seconds": 1,
        })


def test_add_audio_effect_expands_to_a_trimmed_audio_clip():
    from app.editing.edits import apply_ops
    from app.editing.validators import validate_content

    audio_id = uuid4()
    content = revision_content()
    version = SimpleNamespace(composition_id=uuid4(), id=uuid4(), content_digest="d" * 64)
    args = revision_args(version, {
        "op": "add_audio_effect",
        "source_id": str(audio_id),
        "scene_id": "proof",
        "start_seconds": 4.5,
        "duration_seconds": 0.2,
        "gain_db": -6,
    })
    facts = {
        **snapshot_facts(version.composition_id),
        audio_id: {
            "kind": "audio", "digest": "e" * 64, "storage_key": "sources/click.mp3",
            "duration_ticks": 90000, "meta": {},
        },
    }
    updated = apply_ops(
        content,
        expand_revision_op(args.ops[0], content, facts=facts),
        {audio_id: "e" * 64},
    )
    validate_content(updated, facts)
    track = next(track for track in updated.timeline.tracks if track.track_id == "trk_audio_effect")
    assert track.kind == "audio" and track.role == "effect"
    assert len(track.clips) == 1
    clip = track.clips[0]
    assert clip.object.kind == "audio" and clip.object.gain_db == -6
    assert clip.scene_id == "proof"
    assert clip.range.start == 405000 and clip.range.end == 423000
    assert clip.source.snapshot_id == audio_id
    assert clip.source.source_range.start == 0
    assert clip.source.source_range.end == 18000


def test_set_narration_changes_only_pending_speech_text():
    from app.editing.edits import apply_ops
    from app.editing.schemas import Clip, SpeechObject, Track
    from app.editing.validators import validate_content

    content = revision_content()
    scene = next(scene for scene in content.scenes if scene.scene_id == "proof")
    content.timeline.tracks.append(Track(
        track_id="trk_dialogue",
        kind="audio",
        role="dialogue",
        order=0,
        clips=[Clip(
            clip_id="clp_speech_proof",
            scene_id="proof",
            range=scene.range,
            source=None,
            object=SpeechObject(
                kind="speech",
                object_id="obj_speech_proof",
                text="A much longer narration that needs to be shortened",
                voice_id="presenter_male",
                language="en",
            ),
            animations=[],
        )],
    ))
    scene.speech_clip_ids.append("clp_speech_proof")
    args = revision_args(
        SimpleNamespace(composition_id=uuid4(), id=uuid4(), content_digest="d" * 64),
        {"op": "set_narration", "clip_id": "clp_speech_proof", "text": "Shorter narration"},
    )
    updated = apply_ops(
        content,
        expand_revision_op(args.ops[0], content, facts=snapshot_facts(uuid4())),
        {},
    )
    validate_content(updated, snapshot_facts(uuid4()))
    speech = next(
        clip for track in updated.timeline.tracks for clip in track.clips if clip.clip_id == "clp_speech_proof"
    )
    assert speech.object.text == "Shorter narration"
    assert speech.object.voice_id == "presenter_male" and speech.object.language == "en"
    assert speech.range == scene.range and speech.scene_id == "proof"


def test_editor_does_not_silently_rebind_an_old_or_inaccessible_output():
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.intent import intent_router
    from app.chat.prompts import assemble_video_round

    base = {"composition_id": str(uuid4()), "composition_version_id": str(uuid4()), "content_digest": "a"*64}
    work = {"kind": "composition", "base_ref": base, "composition_id": base["composition_id"],
            "version_id": base["composition_version_id"]}
    for hint in [{"unavailable": True}, {"composition_id": str(uuid4())},
                 {"composition_id": base["composition_id"], "version_id": str(uuid4())}]:
        assembly = assemble_video_round({"snapshot": ContextSnapshot("saved", resources=(("work", work),)),
                                         "tools": intent_router.tools, "mode": "plan", "target_hint": hint})
        assert assembly.caller_state["video_target"] is None
