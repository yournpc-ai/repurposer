"""Shared high-level authoring and legacy-provenance revision contracts."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.agents.candidate_correction import (
    CandidateCorrectionArgs,
    CandidateRecord,
    CandidateScope,
    apply_correction,
)
from app.editing.revisions import RevisionTargetAmbiguityError, expand_revision_op
from app.editing.schemas import CompositionContent
from app.editing.service import revise_video
from app.editing.store import StaleBase, apply_composition_edits, content_of
from app.models.schemas import ReviseVideoOpsArgs
from app.models.tables import Composition, CompositionVersion, Project, SourceSnapshot, User
from app.skills.package_session import SkillPackageSession
from app.skills.resolution import get_builtin_skill_option

WEB_ID = UUID("11111111-1111-1111-1111-111111111111")
VIDEO_ID = UUID("33333333-3333-3333-3333-333333333333")
WEB_DIGEST = "a" * 64
VIDEO_DIGEST = "c" * 64


def snapshot_facts(owner_id):
    return {
        WEB_ID: {
            "digest": WEB_DIGEST,
            "kind": "web",
            "owner_id": owner_id,
            "storage_key": "sources/web.json",
            "duration_ticks": None,
            "meta": {
                "views": [
                    {
                        "view_id": "hero",
                        "storage_key": "sources/hero.png",
                        "digest": "b" * 64,
                        "width": 1440,
                        "height": 900,
                        "elements": [
                            {
                                "id": "title",
                                "kind": "heading",
                                "x": 0.5,
                                "y": 0.3,
                                "w": 0.6,
                                "h": 0.15,
                            }
                        ],
                    }
                ]
            },
        },
        VIDEO_ID: {
            "digest": VIDEO_DIGEST,
            "kind": "video",
            "owner_id": owner_id,
            "storage_key": "sources/person.mp4",
            "duration_ticks": 900000,
            "meta": {"media": {"width": 1080, "height": 1920}},
        },
    }


def revision_content():
    def text_clip(scene_id, start, end):
        return {
            "clip_id": f"clp_{scene_id}_name",
            "scene_id": scene_id,
            "range": {"start": start, "end": end},
            "source": None,
            "animations": [],
            "object": {
                "kind": "text",
                "object_id": f"obj_{scene_id}_name",
                "text": "Evidence-led value",
                "layout": {"x": 153.6, "y": 432.0, "width": 1612.8, "height": 166.4},
                "style": {
                    "font_size": 104,
                    "color": "#F8FAFC",
                    "weight": 700,
                    "align": "center",
                    "line_height": 1.2,
                },
            },
        }

    scenes = [
        ("open", 0, 360000),
        ("proof", 360000, 720000),
        ("close", 720000, 990000),
    ]
    return CompositionContent.model_validate({
        "settings": {"width": 1920, "height": 1080, "background": "#0B1020"},
        "sources": [],
        "scenes": [
            {
                "scene_id": scene_id,
                "range": {"start": start, "end": end},
                "intent": f"Scene {scene_id}",
                "speech_clip_ids": [],
            }
            for scene_id, start, end in scenes
        ],
        "timeline": {
            "tracks": [
                {
                    "track_id": "trk_main",
                    "kind": "visual",
                    "role": "main",
                    "order": 0,
                    "clips": [],
                },
                {
                    "track_id": "trk_title",
                    "kind": "visual",
                    "role": "title",
                    "order": 1,
                    "clips": [text_clip(scene_id, start, end) for scene_id, start, end in scenes],
                },
            ],
            "transitions": [],
        },
    })


def revision_args(version, action):
    return ReviseVideoOpsArgs.model_validate(
        {
            "base_ref": {
                "composition_id": str(version.composition_id),
                "composition_version_id": str(version.id),
                "content_digest": version.content_digest,
            },
            "ops": [action],
        }
    )


def test_native_create_and_high_level_revision_wires_stay_closed():
    from app.chat.editor_create import CreateVideoArgs

    assert CreateVideoArgs.model_json_schema()["additionalProperties"] is False

    raw = {
        "base_ref": {
            "composition_id": str(uuid4()),
            "composition_version_id": str(uuid4()),
            "content_digest": "d" * 64,
        },
        "ops": [{
            "op": "add_media_overlay",
            "source_id": str(VIDEO_ID),
            "scene_id": "proof",
            "start_seconds": 4.0,
            "end_seconds": 8.0,
            "position": "lower-right",
            "width_ratio": 0.28,
            "margin_px": 48,
            "motion": "fade_in",
        }],
    }
    with pytest.raises(ValidationError) as raised:
        ReviseVideoOpsArgs.model_validate(raw)
    import json

    errors = json.loads(raised.value.json(include_input=False, include_url=False))
    record = CandidateRecord.create(
        tool_name="revise_video",
        arguments=raw,
        errors=errors,
        schema=ReviseVideoOpsArgs.model_json_schema(),
        scope=CandidateScope(owner_id=str(uuid4()), conversation_id=str(uuid4())),
        base_keys=frozenset({f"snapshot:{VIDEO_ID}:{VIDEO_DIGEST}"}),
        call_id="call_overlay",
    )
    diagnostic = record.diagnostic()
    assert "candidate" not in diagnostic
    assert diagnostic["candidate_id"] == record.candidate_id
    assert diagnostic["candidate_digest"] == record.candidate_digest
    assert diagnostic["errors"][0]["original_value"] == "lower-right"
    assert record.arguments["ops"][0]["position"] == "lower-right"
    request = CandidateCorrectionArgs.model_validate(
        {
            "candidate_id": record.candidate_id,
            "candidate_digest": record.candidate_digest,
            "mode": "patch",
            "corrections": [{"error_id": "error_1", "value": "bottom_right"}],
        }
    ).root
    merged = apply_correction(record, request)
    corrected = ReviseVideoOpsArgs.model_validate(merged.arguments)
    assert corrected.ops[0].position == "bottom_right"
    assert corrected.ops[0].source_id == VIDEO_ID
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


async def _user(factory):
    async with factory() as db:
        row = User(email=f"{uuid4()}@example.test", name="promo")
        db.add(row)
        await db.commit()
        return row.id


async def _project(factory, owner_id):
    async with factory() as db:
        row = Project(user_id=owner_id, title="promo")
        db.add(row)
        await db.commit()
        return row.id


@pytest.mark.asyncio
async def test_skill_binding_survives_an_unsaved_clarification_turn(database, monkeypatch, installed_promo):
    from app.chat.service import prepare_chat_turn
    from app.models.schemas import ChatRequest
    from app.models.tables import Conversation, Message

    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    owner = await _user(database)
    project = await _project(database, owner)
    skill = get_builtin_skill_option("promo-video").reference
    async with database() as db:
        conversation = Conversation(
            user_id=owner,
            project_id=project,
            context={"schema_version": 1, "items": [{
                "id": "draft-item",
                "tool": "design_video",
                "target_tool": "design_video",
                "text": '{"draft_id":"draft-1"}',
                "candidate": {"active": True},
            }]},
        )
        db.add(conversation)
        await db.flush()
        db.add_all([
            Message(
                conversation_id=conversation.id,
                role="user",
                content="first",
                turn_state="settled",
                seq=1,
                intent={"skill": skill.model_dump(mode="json")},
            ),
            Message(
                conversation_id=conversation.id,
                role="user",
                content="clarify",
                turn_state="settled",
                seq=2,
                intent={
                    "skill": skill.model_dump(mode="json"),
                    "skill_binding": "inherited",
                },
            ),
        ])
        await db.commit()
        prepared = await prepare_chat_turn(
            db, owner, ChatRequest(project_id=project, message="save the draft"),
        )
        assert prepared.skill == skill
        assert prepared.user_message.intent["skill_binding"] == "inherited"


async def _sources(factory, owner_id):
    facts = snapshot_facts(owner_id)
    async with factory() as db:
        for snapshot_id, fact in facts.items():
            db.add(
                SourceSnapshot(
                    id=snapshot_id,
                    owner_id=owner_id,
                    kind=fact["kind"],
                    storage_key=fact["storage_key"],
                    digest=fact["digest"],
                    duration_ticks=fact["duration_ticks"],
                    meta=fact["meta"],
                )
            )
        await db.commit()


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


@pytest.mark.asyncio
async def test_overlay_saves_change_set_and_stale_base_never_overwrites(database, installed_promo):
    owner = await _user(database)
    project = await _project(database, owner)
    await _sources(database, owner)
    provenance = {
        "skill": "promo-video",
        "skill_reference": get_builtin_skill_option("promo-video").reference.model_dump(
            mode="json"
        ),
        "skill_version": get_builtin_skill_option("promo-video").reference.version,
        "arc_id": "product-evidence",
        "language": "en",
        "copy_evidence": [],
        "builder_version": "promo-native-v1",
    }
    async with database() as db:
        composition, base, _ = await apply_composition_edits(
            db,
            owner_id=owner,
            origin_project_id=project,
            content=revision_content(),
            skill_provenance=provenance,
            name="OxValue promo",
        )
    scene = next(scene for scene in base.scenes if scene["scene_id"] == "proof")
    start = scene["range"]["start"] / 90000 + 0.5
    async with database() as db:
        read = await revise_video(
            db,
            owner_id=owner,
            args=revision_args(
                base,
                {
                    "op": "add_media_overlay",
                    "source_id": str(VIDEO_ID),
                    "scene_id": "proof",
                    "start_seconds": start,
                    "end_seconds": start + 2,
                    "position": "bottom_right",
                    "width_ratio": 0.28,
                    "margin_px": 48,
                    "motion": "fade_in",
                },
            ),
            request_id="promo-overlay-v2",
        )
    added = read["change_set"]["clips"]["added"]
    assert len(added) == 1
    overlay_id = added[0]["clip_id"]
    assert not read["change_set"]["clips"]["updated"]
    assert not read["change_set"]["clips"]["removed"]
    storyboard_clip = next(
        clip
        for scene in read["storyboard"]["scenes"]
        for clip in scene["clips"]
        if clip["clip_id"] == overlay_id
    )
    assert storyboard_clip["object_kind"] == "video"
    async with database() as db:
        version = await db.get(CompositionVersion, read["composition_version_id"])
        assert version.skill_provenance["arc_id"] == "product-evidence"
        assert version.skill_provenance["builder_version"] == "promo-native-v1"
        assert "last_revision" not in version.skill_provenance
        content = content_of(version)
        track = next(
            track
            for track in content.timeline.tracks
            if any(clip.clip_id == overlay_id for clip in track.clips)
        )
        overlay = track.clips[0]
        assert track.kind == "visual" and track.role == "effect"
        assert round(overlay.object.layout.x + overlay.object.layout.width + 48) == 1920
        assert overlay.source.snapshot_id == VIDEO_ID
        assert overlay.source.source_range.duration == 180000
        assert len(overlay.animations) == 1
        with pytest.raises(StaleBase):
            await revise_video(
                db,
                owner_id=owner,
                args=revision_args(
                    base,
                    {
                        "op": "set_text",
                        "clip_id": "clp_open_name",
                        "text": "Must not overwrite",
                    },
                ),
                request_id="promo-stale-base",
            )
        assert await db.scalar(select(func.count()).select_from(CompositionVersion)) == 2
        current = await db.get(Composition, composition.id, populate_existing=True)
        assert current.current_version_id == UUID(read["composition_version_id"])


def test_overlay_resolves_saved_scene_ranges_and_keeps_ambiguity_write_free():
    owner = uuid4()
    content = revision_content()
    scene = next(item for item in content.scenes if item.scene_id == "proof")
    version = SimpleNamespace(composition_id=uuid4(), id=uuid4(), content_digest="d" * 64)

    whole = revision_args(version, {
        "op": "add_media_overlay",
        "source_id": str(VIDEO_ID),
        "scene_id": "proof",
        "scope": "whole_scene",
        "position": "bottom_right",
        "width_ratio": 0.28,
        "margin_px": 48,
        "motion": "none",
    })
    from app.editing.edits import AddClip

    ops = expand_revision_op(whole.ops[0], content, facts=snapshot_facts(owner))
    overlay = next(op.clip for op in ops if isinstance(op, AddClip))
    assert overlay.range == scene.range
    assert overlay.source.source_range.duration == scene.range.duration

    start = scene.range.start / 90000 + 0.25
    timed = revision_args(version, {
        "op": "add_media_overlay",
        "source_id": str(VIDEO_ID),
        "scene_id": "proof",
        "start_seconds": start,
        "duration_seconds": 2,
        "position": "bottom_right",
        "width_ratio": 0.28,
        "margin_px": 48,
        "motion": "none",
    })
    ops = expand_revision_op(timed.ops[0], content, facts=snapshot_facts(owner))
    overlay = next(op.clip for op in ops if isinstance(op, AddClip))
    assert overlay.range.start == scene.range.start + 22500
    assert overlay.range.end == overlay.range.start + 180000

    for action in (
        {
            "op": "add_media_overlay",
            "source_id": str(VIDEO_ID),
            "scope": "whole_scene",
            "position": "bottom_right",
            "width_ratio": 0.28,
            "margin_px": 48,
            "motion": "none",
        },
        {
            "op": "add_media_overlay",
            "source_id": str(VIDEO_ID),
            "scene_id": "proof",
            "position": "bottom_right",
            "width_ratio": 0.28,
            "margin_px": 48,
            "motion": "none",
        },
    ):
        with pytest.raises(RevisionTargetAmbiguityError) as raised:
            expand_revision_op(revision_args(version, action).ops[0], content, facts=snapshot_facts(owner))
        assert len(raised.value.candidates) == len(content.scenes)

    with pytest.raises(RevisionTargetAmbiguityError):
        expand_revision_op(
            whole.ops[0],
            content,
            facts=snapshot_facts(owner),
            request_context={"user_text": "把本人视频放到右下角，不制作。"},
        )
    wrong_scene = revision_args(version, {
        "op": "add_media_overlay",
        "source_id": str(VIDEO_ID),
        "scene_id": "open",
        "scope": "whole_scene",
        "position": "bottom_right",
        "width_ratio": 0.28,
        "margin_px": 48,
        "motion": "none",
    })
    with pytest.raises(RevisionTargetAmbiguityError):
        expand_revision_op(
            wrong_scene.ops[0],
            content,
            facts=snapshot_facts(owner),
            request_context={"user_text": "整个第二镜，不需要我再给秒数。"},
        )
    confirmed = expand_revision_op(
        whole.ops[0],
        content,
        facts=snapshot_facts(owner),
        request_context={"user_text": "整个第二镜，不需要我再给秒数。"},
    )
    assert next(op.clip for op in confirmed if isinstance(op, AddClip)).range == scene.range
    inferred = revision_args(version, {
        "op": "add_media_overlay", "source_id": str(VIDEO_ID),
        "position": "bottom_right", "width_ratio": 0.28, "margin_px": 48, "motion": "none",
    })
    bound = expand_revision_op(
        inferred.ops[0], content, facts=snapshot_facts(owner),
        request_context={"user_text": "整个第二镜，不需要我再给秒数。"},
    )
    assert next(op.clip for op in bound if isinstance(op, AddClip)).range == scene.range
    with pytest.raises(ValidationError):
        revision_args(version, {
            "op": "add_media_overlay", "source_id": str(VIDEO_ID), "scene_id": "proof",
            "scope": "whole_scene", "start_seconds": 4, "position": "bottom_right",
            "width_ratio": 0.28, "margin_px": 48, "motion": "none",
        })


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


@pytest.mark.asyncio
async def test_add_audio_effect_loads_new_source_and_saves_version(database, installed_promo):
    owner = await _user(database)
    project = await _project(database, owner)
    await _sources(database, owner)
    audio_id = uuid4()
    async with database() as db:
        db.add(SourceSnapshot(
            id=audio_id,
            owner_id=owner,
            kind="audio",
            storage_key="sources/click.mp3",
            digest="e" * 64,
            duration_ticks=90000,
            meta={},
        ))
        composition, base, _ = await apply_composition_edits(
            db,
            owner_id=owner,
            origin_project_id=project,
            content=revision_content(),
            name="Audio effect base",
        )
        await db.commit()
    async with database() as db:
        read = await revise_video(
            db,
            owner_id=owner,
            args=revision_args(base, {
                "op": "add_audio_effect",
                "source_id": str(audio_id),
                "scene_id": "proof",
                "start_seconds": 4.5,
                "duration_seconds": 0.2,
            }),
            request_id="audio-effect-v2",
        )
    assert read["version"] == 2
    async with database() as db:
        version = await db.get(CompositionVersion, read["composition_version_id"])
        updated = content_of(version)
    track = next(track for track in updated.timeline.tracks if track.track_id == "trk_audio_effect")
    assert track.kind == "audio" and track.role == "effect"
    assert len(track.clips) == 1
    assert track.clips[0].source.snapshot_id == audio_id


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


@pytest.mark.asyncio
async def test_direct_op_batch_saves_one_version_for_one_user_intent(database, installed_promo):
    owner = await _user(database)
    project = await _project(database, owner)
    async with database() as db:
        composition, base, _ = await apply_composition_edits(
            db,
            owner_id=owner,
            origin_project_id=project,
            content=revision_content(),
            name="Direct Op batch",
        )
    args = ReviseVideoOpsArgs.model_validate({
        "base_ref": {
            "composition_id": str(composition.id),
            "composition_version_id": str(base.id),
            "content_digest": base.content_digest,
        },
        "ops": [
            {"op": "set_text", "clip_id": "clp_open_name", "text": "Direct opening"},
            {"op": "set_text", "clip_id": "clp_proof_name", "text": "Direct proof"},
        ],
    })
    async with database() as db:
        read = await revise_video(db, owner_id=owner, args=args, request_id="direct-op-batch")
        assert read["version"] == 2
        assert len(read["change_set"]["clips"]["updated"]) == 2
        assert await db.scalar(select(func.count()).select_from(CompositionVersion)) == 2
        current = await db.get(Composition, composition.id)
        assert current.current_version_id == UUID(read["composition_version_id"])
        content = content_of(await db.get(CompositionVersion, current.current_version_id))
        texts = {
            clip.object.text
            for track in content.timeline.tracks
            for clip in track.clips
            if clip.clip_id in {"clp_open_name", "clp_proof_name"}
        }
        assert texts == {"Direct opening", "Direct proof"}


def test_editor_does_not_silently_rebind_an_old_or_inaccessible_output():
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.prompts import assemble_video_round
    from app.chat.intent import intent_router

    base = {"composition_id": str(uuid4()), "composition_version_id": str(uuid4()), "content_digest": "a"*64}
    work = {"kind": "composition", "base_ref": base, "composition_id": base["composition_id"],
            "version_id": base["composition_version_id"]}
    for hint in [{"unavailable": True}, {"composition_id": str(uuid4())},
                 {"composition_id": base["composition_id"], "version_id": str(uuid4())}]:
        assembly = assemble_video_round({"snapshot": ContextSnapshot("saved", resources=(("work", work),)),
                                         "tools": intent_router.tools, "mode": "plan", "target_hint": hint})
        assert assembly.caller_state["video_target"] is None
