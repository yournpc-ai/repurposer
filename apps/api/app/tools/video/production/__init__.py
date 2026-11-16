"""Saved-version facts and authorization at the shared Run birthplace.

This is orchestration, not another content writer or confirmation machine.
"""
from math import gcd
from uuid import UUID

from sqlalchemy import select

from app.config import settings
from app.editing.service import video_version_read
from app.editing.store import content_of, get_video_version
from app.models.schemas import PendingPlan, WorkflowStatus
from app.models.tables import Composition, Conversation, Message, WorkflowRun
from app.tools.video.params import PrepareNarrationParams, ProduceVideoParams


def assert_saved_producers_available(clips: list[dict]) -> None:

    if not settings.component_bake_enabled and any(
        clip.get("object_kind") == "generator" and clip.get("producer") == "remotion-project"
        for clip in clips
    ):
        raise ValueError(
            "This saved video requires remotion-project, which is unavailable in this deployment; "
            "revise it to use native or fixed-media scenes before production"
        )


async def reviewed_output_ref(db, project, output_id):
    """An owned delivered production is a review anchor across Chats."""
    from app.models.tables import Output, Project, WorkflowStep
    from app.pipeline.run_review import output_is_delivered
    output = await db.scalar(select(Output).join(Project, Output.project_id == Project.id)
        .where(Output.id == output_id, Project.user_id == project.user_id))
    if output is None or not output_is_delivered(output) or not output.workflow_step_id:
        return None
    step = await db.get(WorkflowStep, output.workflow_step_id)
    run = await db.get(WorkflowRun, step.run_id) if step else None
    ref = (run.context or {}).get("version_ref") if run else None
    return ref if ref == (output.render_spec or {}).get("provenance") else None


def _render_capture_units(payload: dict) -> dict[str, float]:
    """The mirror bills render time only; ProduceVideo captures actual TTS."""
    return {"video_seconds": float((payload or {}).get("duration_seconds") or 0)}


async def capture_video_render(db, output_id):
    """Capture only after upload/probe, in the fenced Output success transaction.

    The mirror's existing step key deduplicates retries. Assembly itself is
    free; failed renders leave the held reservation for normal release.
    """
    from sqlalchemy import update
    from app.models.schemas import RenderStatus
    from app.models.tables import Output, Project, WorkflowStep, now_utc
    from app.platform.billing import capture_step, estimate_usd_range
    output = await db.get(Output, output_id)
    if output is None or output.type != "video" or output.render_status != RenderStatus.COMPLETED:
        return
    mirror = await db.scalar(select(WorkflowStep).where(
        WorkflowStep.kind == "render",
        WorkflowStep.spec["output_id"].as_string() == str(output_id),
    ).order_by(WorkflowStep.seq.desc()).with_for_update().limit(1))
    if mirror is None:
        return  # Internal run-less preview has no production charge.
    if output.archived_at is None:
        await db.execute(update(Output).where(
            Output.work_id == output.work_id, Output.id != output.id,
            Output.archived_at.is_(None), Output.render_status == RenderStatus.COMPLETED,
        ).values(archived_at=now_utc()))
    project = await db.get(Project, output.project_id)
    units = _render_capture_units(output.payload or {})
    usd = estimate_usd_range({"prompt_tokens": [0, 0], "completion_tokens": [0, 0], "units": units})[1]
    mirror.cost = {"prompt_tokens": 0, "completion_tokens": 0,
                   "units": units, "fixed_cost": usd}
    await capture_step(db, user_id=project.user_id, node=mirror)


async def video_quote_facts(db, project, tasks):
    seconds = {}
    images = {}
    tts_characters = {}
    narration_tts_characters = {}
    from app.editing.schemas import GeneratorObject
    from app.tools.video.generated_images import has_fixed_generated_image
    from app.tools.video.narration import (
        narration_original_quote_characters,
        narration_original_request_key,
        narration_quote_characters,
    )

    for task in tasks or []:
        if task.tool == "prepare_narration":
            params = PrepareNarrationParams.model_validate(task.params)
            key = narration_original_request_key(
                text=params.text, voice_id=params.voice_id, language=params.language
            )
            narration_tts_characters[key] = await narration_original_quote_characters(
                text=params.text,
                voice_id=params.voice_id,
                language=params.language,
                user_id=project.user_id,
            )
            continue
        if task.tool != "produce_video":
            continue
        production = ProduceVideoParams.model_validate(task.params)
        ref = production.version_ref
        composition, version = await get_video_version(
            db, owner_id=project.user_id, version_id=ref.composition_version_id
        )
        if composition.id != ref.composition_id or version.content_digest != ref.content_digest:
            raise ValueError("Video version identity mismatch")
        content = content_of(version)
        seconds[str(version.id)] = max(
            (c.range.end for t in content.timeline.tracks for c in t.clips), default=0
        ) / content.settings.timebase
        missing = 0
        for track in content.timeline.tracks:
            for clip in track.clips:
                if not isinstance(clip.object, GeneratorObject) or clip.object.producer != "image-generation":
                    continue
                if production.regenerate_media or not await has_fixed_generated_image(
                    clip, composition_id=str(composition.id)
                ):
                    missing += 1
        if production.regenerate_media and missing == 0:
            raise ValueError("This saved video has no model-generated image to regenerate")
        images[str(version.id)] = missing
        tts_characters[str(version.id)] = await narration_quote_characters(
            content, user_id=project.user_id
        )
    return {
        "video_seconds": seconds,
        "video_images": images,
        "video_tts_characters": tts_characters,
        "narration_tts_characters": narration_tts_characters,
    }


def is_short_video_affirmation(text: str) -> bool:
    import re

    return bool(re.fullmatch(r"(?:ok(?:ay)?|yes)[.!。！]?", text.strip(), re.I))


async def latest_video_approval(db, project):
    """Use the persisted Chat user turn, never an id relayed by the model."""
    return await db.scalar(
        select(Message.id).join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.project_id == project.id, Message.role == "user")
        .order_by(Message.created_at.desc(), Message.seq.desc()).limit(1)
    )


async def pin_narration_preparation(project, tasks):
    """Pin the one original-only request after the ordinary plan/Start gate."""
    narration_tasks = [t for t in tasks or [] if t.tool == "prepare_narration"]
    if not narration_tasks:
        return {}
    from app.tools.video.narration import narration_original_quote_characters
    from app.tools.video.params import narration_original_policy

    if len(narration_tasks) != 1 or len(tasks or []) != 1:
        raise ValueError("Prepare narration runs as one narration-only task")
    params = PrepareNarrationParams.model_validate(narration_tasks[0].params)
    characters = await narration_original_quote_characters(
        text=params.text,
        voice_id=params.voice_id,
        language=params.language,
        user_id=project.user_id,
    )
    return {
        "narration_preparation": {
            "request": params.model_dump(mode="json"),
            "narration_policy": narration_original_policy(characters).model_dump(mode="json"),
        }
    }


async def pin_video_production(db, project, tasks, approved_by):
    video_tasks = [t for t in tasks or [] if t.tool == "produce_video"]
    if not video_tasks:
        return {}
    if len(video_tasks) != 1:
        raise ValueError("Produce one saved video per run")
    production = ProduceVideoParams.model_validate(video_tasks[0].params)
    ref = production.version_ref
    composition = await db.scalar(select(Composition).where(
        Composition.id == ref.composition_id,
        Composition.owner_id == project.user_id,
    ).with_for_update())
    if composition is None:
        raise ValueError("Video composition not found")
    read = await video_version_read(db, owner_id=project.user_id,
                                    version_id=ref.composition_version_id)
    if read["base_ref"] != ref.model_dump(mode="json"):
        raise ValueError("Video version identity mismatch")
    storyboard = read["storyboard"]
    clips = [
        clip
        for scene in storyboard["scenes"]
        for clip in scene["clips"]
    ] + list(storyboard["unassigned_clips"])
    assert_saved_producers_available(clips)
    if production.regenerate_media and not any(
        clip.get("object_kind") == "generator" and clip.get("producer") == "image-generation"
        for clip in clips
    ):
        raise ValueError("This saved video has no model-generated image to regenerate")
    pending = PendingPlan.model_validate(project.pending_brief or {})
    receipt = pending.video_presentation or {}
    for key in ("composition_id", "composition_version_id", "content_digest", "presentation_digest"):
        if receipt.get(key) != read[key]:
            raise ValueError("Present this exact saved video version before production")
    if not receipt.get("presentation_complete"):
        raise ValueError("The creative overview has not finished presenting")
    presented = await db.get(Message, UUID(receipt["presented_message_id"]))
    approval = await db.get(Message, approved_by) if approved_by else None
    revision_approval = False
    prior_id = receipt.get("prior_presented_message_id")
    if (approval is not None and prior_id and read["version"] > 1
            and receipt.get("authorized_revision_message_id") == str(approval.id)):
        prior = await db.get(Message, UUID(prior_id))
        revision_approval = bool(prior and prior.conversation_id == approval.conversation_id
            and prior.seq < approval.seq and any(
                b.get("kind") == "video_storyboard" and b.get("composition_id") == read["composition_id"]
                for b in prior.blocks or []))
    if (approval is not None and read["version"] > 1 and receipt.get("prior_reviewed_output_id")
            and receipt.get("authorized_revision_message_id") == str(approval.id)):
        prior_ref = await reviewed_output_ref(db, project, UUID(receipt["prior_reviewed_output_id"]))
        revision_approval = bool(prior_ref and prior_ref["composition_id"] == read["composition_id"])
    if (presented is None or approval is None or approval.role != "user"
            or approval.conversation_id != presented.conversation_id
            or (approval.seq <= presented.seq and not revision_approval)):
        raise ValueError("The first storyboard needs a later user approval before production")
    conversation = await db.get(Conversation, approval.conversation_id)
    if conversation is None or conversation.project_id != project.id:
        raise ValueError("The approval belongs to another Chat")
    if is_short_video_affirmation(approval.content or ""):
        confirmation = (approval.intent or {}).get("video_confirmation") or {}
        if (not receipt.get("production_invited")
                or confirmation.get("action") not in {"produce", "start"}
                or confirmation.get("base_ref") != read["base_ref"]
                or confirmation.get("presented_message_id") != str(presented.id)
                or composition.current_version_id != ref.composition_version_id):
            raise ValueError("This confirmation needs a current storyboard with a production invitation")
        used = await db.scalar(select(WorkflowRun.id).where(
            WorkflowRun.project_id == project.id,
            WorkflowRun.context["video_presentation"]["presented_message_id"].as_string()
            == str(presented.id),
        ).limit(1))
        if used is not None:
            raise ValueError("Production was already requested for this storyboard")
    block = next((b for b in presented.blocks or []
                  if b.get("kind") == "video_storyboard"
                  and b.get("composition_version_id") == read["composition_version_id"]), None)
    if not block or block.get("presentation_digest") != read["presentation_digest"]:
        raise ValueError("The storyboard presentation receipt is invalid")
    # The Composition lock serializes cross-Chat starts for the same work.
    active = await db.scalar(select(WorkflowRun.id).where(
        WorkflowRun.status.in_([WorkflowStatus.PENDING, WorkflowStatus.RUNNING]),
        WorkflowRun.context["version_ref"]["composition_id"].as_string() == str(composition.id),
    ).limit(1))
    if active:
        raise ValueError("This video already has a production in progress")
    from app.tools.video.narration import narration_quote_characters
    from app.tools.video.params import narration_policy

    _, pinned_version = await get_video_version(
        db, owner_id=project.user_id, version_id=ref.composition_version_id
    )
    policy = narration_policy(
        await narration_quote_characters(
            content_of(pinned_version), user_id=project.user_id
        )
    )
    version_settings = content_of(pinned_version).settings
    divisor = gcd(version_settings.width, version_settings.height)
    aspect = (
        f"{version_settings.width // divisor}:{version_settings.height // divisor}"
    )
    return {"version_ref": ref.model_dump(mode="json"),
            "regenerate_media": production.regenerate_media,
            "narration_policy": policy.model_dump(mode="json"),
            "aspect": aspect,
            "video_authorized_by": str(approval.id),
            "video_presentation": receipt}
