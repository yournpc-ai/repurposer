"""Compile only fixed media for a native export. No production side effects."""

import hashlib

from botocore.exceptions import ClientError
from sqlalchemy import select

from app.editing.schemas import GeneratorObject, SpeechObject
from app.editing.store import content_of, snapshot_facts
from app.editing.video_spec import compile_video_spec
from app.models.schemas import PlanEstimate
from app.models.tables import Output, SourceSnapshot
from app.platform.billing import credits_for_cost, estimate_usd_range
from app.providers import storage
from app.tools.video import components, generated_images, programs
from app.tools.video.narration_store import (
    NarrationStoreError,
    peek_original,
    pending_original_status,
)


async def fixed_export_spec(db, project, composition, version):
    if (
        composition.owner_id != project.user_id
        or composition.origin_project_id != project.id
        or version.composition_id != composition.id
    ):
        raise ValueError("This video is outside the current project.")
    content = content_of(version)
    sources = {source.snapshot_id for source in content.sources}
    facts = await snapshot_facts(db, sources)
    if facts.keys() != sources or any(f["owner_id"] != project.user_id for f in facts.values()):
        raise ValueError("An owned fixed source is unavailable.")
    generators, speech, missing = {}, {}, []
    for track in content.timeline.tracks:
        for clip in track.clips:
            obj = clip.object
            if isinstance(obj, GeneratorObject):
                if obj.producer == "image-generation":
                    try:
                        media = await generated_images.find_fixed_generated_image(
                            clip, composition_id=str(composition.id)
                        )
                    except (generated_images.GeneratedImageError, ClientError) as exc:
                        reason = (
                            "provider_outcome_unknown"
                            if isinstance(exc, generated_images.GeneratedImageOutcomeUnknown)
                            else "fixed_image_unreadable"
                        )
                        missing.append(
                            {
                                "clip_id": clip.clip_id,
                                "kind": obj.producer,
                                "reason": reason,
                                "allow_regeneration": False,
                            }
                        )
                        continue
                else:
                    store = programs if obj.producer == "draw-2d" else components
                    media = await store._cached_manifest(obj, verify_media=True)
                if media:
                    generators[obj.object_id] = media
                else:
                    missing.append(
                        {
                            "clip_id": clip.clip_id,
                            "kind": obj.producer,
                            "prompt": obj.prompt,
                            **(
                                {"binding_tool": "bind_clip_source"}
                                if obj.producer == "image-generation"
                                else {}
                            ),
                            "tool": "generate_image"
                            if obj.producer == "image-generation"
                            else "preview_range",
                        }
                    )
            if isinstance(obj, SpeechObject) and obj.alignment is None:
                # A previously exported version can have a fixed, adapted original.
                outputs = await db.scalars(
                    select(Output)
                    .where(
                        Output.project_id == project.id,
                        Output.composition_version_id == version.id,
                        Output.payload["speech_media"].has_key(obj.object_id),
                    )
                    .order_by(Output.created_at.desc())
                )
                manifest = next((o.payload["speech_media"][obj.object_id] for o in outputs), None)
                if manifest:
                    media = manifest.get("media") or {}
                    try:
                        matches = (
                            hashlib.sha256(await storage.read(media["storage_key"])).hexdigest()
                            == media["digest"]
                        )
                    except ClientError:
                        matches = False
                    if matches:
                        speech[obj.object_id] = manifest
                        continue
                try:
                    original = await peek_original(project.user_id, obj)
                except (ClientError, NarrationStoreError):
                    missing.append(
                        {
                            "clip_id": clip.clip_id,
                            "kind": "speech",
                            "reason": "fixed_original_unreadable",
                            "allow_regeneration": False,
                        }
                    )
                    continue
                if not original and (
                    pending := await pending_original_status(project.user_id, obj)
                ):
                    missing.append(
                        {
                            "clip_id": clip.clip_id,
                            "kind": "speech",
                            "reason": pending,
                            "allow_regeneration": False,
                        }
                    )
                    continue
                snapshot = None
                if original:
                    snapshot = await db.scalar(
                        select(SourceSnapshot.id)
                        .where(
                            SourceSnapshot.owner_id == project.user_id,
                            SourceSnapshot.origin_project_id == project.id,
                            SourceSnapshot.digest == original["media"]["digest"],
                            SourceSnapshot.storage_key == original["media"]["storage_key"],
                        )
                        .order_by(SourceSnapshot.id)
                        .limit(1)
                    )
                missing.append(
                    {
                        "clip_id": clip.clip_id,
                        "kind": "speech",
                        "tool": "bind_clip_source" if snapshot else "generate_voice",
                        "binding_tool": "bind_clip_source",
                        "alignment_tool": "annotate_narration",
                        "cache_available": bool(original),
                        "source_id": str(snapshot) if snapshot else None,
                        "text": obj.text,
                        "language": obj.language,
                        "voice_id": obj.voice_id,
                    }
                )
    if missing:
        return None, missing
    spec = compile_video_spec(
        content,
        facts,
        composition_id=composition.id,
        version_id=version.id,
        content_digest=version.content_digest,
        generator_media=generators,
        speech_media=speech,
    )
    return spec, []


async def export_quote(db, spec):
    seconds = spec["duration_frames"] * spec["fps"]["den"] / spec["fps"]["num"]
    usd = estimate_usd_range(
        {"prompt_tokens": [0, 0], "completion_tokens": [0, 0], "units": {"video_seconds": seconds}}
    )[1]
    credits = await credits_for_cost(db, usd)
    return PlanEstimate(total=[credits, credits], per_task=[[credits, credits]])


async def bind_clip_source_ops(db, project, content, clip, source_id):
    from app.editing.edits import BindSource, UpdateClip
    from app.editing.schemas import ClipSource, ImageObject, NarrationAlignmentRef, TimeRange
    from app.editing.timing import source_ticks_to_output_ticks
    from app.models.tables import NarrationAlignment

    snapshot = await db.get(SourceSnapshot, source_id)
    if (
        clip is None
        or snapshot is None
        or snapshot.owner_id != project.user_id
        or snapshot.origin_project_id != project.id
    ):
        raise ValueError("Select a pending clip and fixed source in this project.")
    obj = clip.object
    source = ClipSource(snapshot_id=snapshot.id, snapshot_digest=snapshot.digest)
    window = clip.range
    if (
        isinstance(obj, GeneratorObject)
        and obj.producer == "image-generation"
        and snapshot.kind == "image"
    ):
        replacement = ImageObject(
            kind="image",
            object_id=obj.object_id,
            layout=obj.layout,
            transform=obj.transform,
            fit=obj.fit,
            opacity=obj.opacity,
        )
    elif isinstance(obj, SpeechObject) and obj.alignment is None and snapshot.kind == "audio":
        original = await peek_original(project.user_id, obj)
        if (
            not original
            or snapshot.digest != original["media"]["digest"]
            or not snapshot.duration_ticks
        ):
            raise ValueError("The fixed recording must match the reviewed voice and exact script.")
        align = await db.scalar(
            select(NarrationAlignment)
            .where(
                NarrationAlignment.owner_id == project.user_id,
                NarrationAlignment.audio_snapshot_id == snapshot.id,
                NarrationAlignment.audio_digest == snapshot.digest,
                NarrationAlignment.status == "READY",
                NarrationAlignment.text == obj.text,
            )
            .order_by(NarrationAlignment.created_at.desc())
            .limit(1)
        )
        if not align:
            raise ValueError(
                "The fixed recording needs its reviewed script alignment before binding."
            )
        end = window.start + source_ticks_to_output_ticks(
            snapshot.duration_ticks, content.settings.timebase
        )
        if end > window.end:
            raise ValueError(
                "The recording exceeds the saved clip window. Review the timing before binding."
            )
        window = TimeRange(start=window.start, end=end)
        source.source_range = TimeRange(start=0, end=snapshot.duration_ticks)
        replacement = SpeechObject(
            kind="speech",
            object_id=obj.object_id,
            text=obj.text,
            gain_db=obj.gain_db,
            provider=None,
            model=None,
            alignment=NarrationAlignmentRef(
                alignment_id=align.id,
                content_digest=align.content_digest,
                audio_snapshot_id=snapshot.id,
                audio_digest=snapshot.digest,
            ),
        )
    else:
        raise ValueError("This clip does not accept that fixed media type.")
    ops = (
        []
        if any(s.snapshot_id == source_id for s in content.sources)
        else [BindSource(op="bind_source", snapshot_id=source_id)]
    )
    return [
        *ops,
        UpdateClip(
            op="update_clip", clip_id=clip.clip_id, source=source, object=replacement, range=window
        ),
    ]
