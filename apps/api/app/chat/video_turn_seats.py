"""The video family's turn seats (ADR-145 phase B) — ONE implementation;
the plan path's and the chat path's runners both delegate here (the
codebase's two-path mirror stays thin instead of copying 100+ lines).

Layering: chat may import editing (the pure content services) and
tools/video (the LLM/capture orchestration). The write door commits on a
DEDICATED session — the turn's own long transaction never rides it; the
turn only carries the presentation receipt (pending_brief's
video_presentation slice) and the storyboard block on the presenting row.
"""

from typing import Any
from uuid import UUID

from app.agents.tool_loop import ToolObservation
from app.models.schemas import DesignVideoArgs, PendingPlan, ReviseVideoArgs
from app.models.tables import Message, Project


async def video_context_lines(db, project, mentions=()):
    """Identity-level material digest; full content is still read on demand."""
    import json
    from app.config import settings
    if not settings.video_project_enabled:
        return []
    from sqlalchemy import select
    from app.models.tables import Asset, Composition, CompositionVersion, Output
    rows = (await db.execute(select(Composition, CompositionVersion)
        .join(CompositionVersion, Composition.current_version_id == CompositionVersion.id)
        .where(Composition.owner_id == project.user_id, Composition.origin_project_id == project.id)
        .order_by(Composition.created_at.desc()).limit(16))).all()
    lines = ["Saved video works (ids are internal references, never user-facing prose):"] if rows else []
    for composition, version in rows:
        lines.append(json.dumps({"name": composition.name, "composition_id": str(composition.id),
            "composition_version_id": str(version.id), "content_digest": version.content_digest,
            "version": version.version}, ensure_ascii=False))
    receipt = (project.pending_brief or {}).get("video_presentation")
    if receipt:
        lines.append("Video currently under review: " + json.dumps(receipt, ensure_ascii=False))
    for mention in mentions or []:
        if mention.type == "asset":
            try:
                asset_id = UUID(str(mention.id))
            except ValueError:
                continue  # A staged local file has no server asset id yet.
            asset = await db.scalar(select(Asset).where(Asset.id == asset_id, Asset.user_id == project.user_id))
            if asset is not None:
                lines.append("Mentioned source material: " + json.dumps({"asset_id": str(asset.id),
                    "type": asset.type.value, "name": asset.title,
                    "processing_status": asset.processing_status.value}, ensure_ascii=False))
            continue
        if mention.type != "output":
            continue
        row = await db.scalar(select(Output).join(Project, Output.project_id == Project.id).where(
            Output.id == UUID(str(mention.id)), Project.user_id == project.user_id))
        if row is not None and row.composition_version_id:
            lines.append("Mentioned video output: " + json.dumps({"output_id": str(row.id),
                "composition_id": str(row.composition_id),
                "composition_version_id": str(row.composition_version_id),
                "content_digest": (row.payload or {}).get("composition_digest")}, ensure_ascii=False))
    return lines


async def read_video_for_presentation(db, project, params):
    """Read stays pure; the runner schedules its block on the accepted row."""
    from app.editing.service import video_version_read, format_storyboard_text
    from app.editing.store import CompositionNotFound, PermissionDenied
    try:
        read = await video_version_read(db, owner_id=project.user_id,
            version_id=params.version_id, composition_id=params.composition_id,
            output_id=params.output_id)
    except (CompositionNotFound, PermissionDenied, ValueError):
        return None, "No accessible video version at this reference."
    from app.tools.video.programs import enrich_generator_previews, generator_preview_images
    read = await enrich_generator_previews(read)
    return read, ToolObservation(
        format_storyboard_text(read), images=tuple(await generator_preview_images(read))
    )


async def video_proposal_guard(db, project, tasks, *, pending_read=None, production_intent=None, mentions=()):
    if not any(t.tool == "produce_video" for t in tasks):
        return None
    # Native tool loops occasionally serialize a nested object as JSON text.
    # Normalize that one bounded shape BEFORE any guard reads it; malformed
    # values become repair feedback, never a 500 or an implicit redesign.
    import json
    for task in tasks:
        if task.tool != "produce_video":
            continue
        params = dict(task.params or {})
        ref = params.get("version_ref")
        if isinstance(ref, str):
            try:
                ref = json.loads(ref)
            except (TypeError, ValueError):
                return "Video production held: version_ref must be the saved base_ref object, not opaque text. Re-read the version and relay its base_ref."
            if not isinstance(ref, dict):
                return "Video production held: version_ref must be the saved base_ref object. Re-read the version and relay its base_ref."
            task.params = {**params, "version_ref": ref}
    from app.tools.video.production import pin_video_production, latest_video_approval
    from app.editing.store import CompositionNotFound, PermissionDenied
    # A later revision may carry this turn's explicit "change and make".
    # It still waits for the canonical card to finish before auto Start.
    prior = (project.pending_brief or {}).get("video_presentation") or {}
    if pending_read is None and len(tasks) == 1:
        ref = (tasks[0].params or {}).get("version_ref") or {}
        if prior.get("composition_version_id") != ref.get("composition_version_id"):
            from sqlalchemy import select
            from app.models.tables import Conversation
            shown = await db.scalar(select(Message).join(Conversation, Message.conversation_id == Conversation.id)
                .where(Conversation.project_id == project.id, Message.blocks.contains([
                    {"kind": "video_storyboard", "composition_version_id": ref.get("composition_version_id"), "presentation_complete": True}
                ])).order_by(Message.seq.desc()).limit(1))
            if shown is not None:
                block = next(b for b in shown.blocks if b.get("composition_version_id") == ref.get("composition_version_id"))
                prior = {**block, "presented_message_id": str(shown.id)}
                stored = PendingPlan.model_validate(project.pending_brief or {})
                project.pending_brief = stored.model_copy(update={"video_presentation": prior}).model_dump(mode="json")
            else:
                from app.models.tables import WorkflowRun
                previous = await db.scalar(select(WorkflowRun).where(
                    WorkflowRun.project_id == project.id,
                    WorkflowRun.context["version_ref"]["composition_version_id"].as_string() == ref.get("composition_version_id"),
                ).order_by(WorkflowRun.created_at.desc()).limit(1))
                proven = (previous.context or {}).get("video_presentation") if previous else None
                if proven and proven.get("presentation_complete"):
                    prior = proven
                    stored = PendingPlan.model_validate(project.pending_brief or {})
                    project.pending_brief = stored.model_copy(update={"video_presentation": prior}).model_dump(mode="json")
    if (pending_read and pending_read["version"] > 1 and production_intent is True
            and prior.get("presentation_complete")
            and prior.get("composition_id") == pending_read["composition_id"]
            and all(t.tool == "produce_video" and (t.params or {}).get("version_ref") == pending_read["base_ref"] for t in tasks)):
        pending_read["authorized_revision_message_id"] = str(await latest_video_approval(db, project))
        pending_read["prior_presented_message_id"] = prior.get("presented_message_id")
        return None
    if (pending_read and production_intent is True and pending_read["version"] > 1
            and len(tasks) == 1 and tasks[0].params.get("version_ref") == pending_read["base_ref"]):
        from app.tools.video.production import reviewed_output_ref
        pins = [m for m in mentions if m.type == "output"]
        if len(pins) == 1:
            ref = await reviewed_output_ref(db, project, UUID(str(pins[0].id)))
            if ref and ref == pending_read.get("previous_version_ref"):
                pending_read["authorized_revision_message_id"] = str(await latest_video_approval(db, project))
                pending_read["prior_reviewed_output_id"] = str(pins[0].id)
                return None
    try:
        await pin_video_production(db, project, tasks, await latest_video_approval(db, project))
    except (ValueError, CompositionNotFound, PermissionDenied) as exc:
        return (
            f"Video production held: {exc}. Do not promise work has started. "
            "Use get_video_version(present=true) to recover a missing presentation, "
            "then wait for the user's approval; never redesign to repair a receipt."
        )
    return None


async def video_mention_guard(db, project, mentions, composition_id):
    """A unique @output fixes the work, even if the model relays another id."""
    pins = [m for m in mentions or [] if m.type == "output"]
    if len(pins) != 1:
        return None
    from app.editing.service import video_version_read, VideoServiceError
    try:
        read = await video_version_read(db, owner_id=project.user_id, output_id=UUID(str(pins[0].id)))
    except VideoServiceError:
        return "The mentioned output has no accessible video version; do not edit another work instead."
    if read["composition_id"] != str(composition_id):
        return "The user named a different work. Read get_video_version(output_id=" + str(pins[0].id) + ") and use that work's exact version reference."
    return None


async def video_request_id(db, conversation_id: UUID, counter: int) -> str:
    """Key a call by its persisted user turn, never the whole conversation.

    Re-entering the same turn/call keeps its key; subsequent user messages
    in the same Chat get a different namespace. The existing Chat execution
    mutex serializes turns in one conversation.
    """
    from sqlalchemy import select

    message_id = await db.scalar(
        select(Message.id)
        .where(Message.conversation_id == conversation_id, Message.role == "user")
        .order_by(Message.seq.desc())
        .limit(1)
    )
    if message_id is None:
        raise ValueError("video edits require a persisted user message")
    return f"video:{message_id}:{counter}"


async def design_video_seat(
    *,
    project: Project,
    args: DesignVideoArgs,
    request_id: str,
) -> tuple[dict[str, Any] | None, str | ToolObservation]:
    """design_video (非终态): capture/snapshot (fresh web path only — a
    redraft reuses the base version's bound snapshots), direct, instantiate
    and save through the write door; hand the saved version's FULL
    canonical facts back to the loop. Success → (read, observation);
    rejection → (None, model-facing feedback)."""
    from app.config import settings  # deferred: config leaf

    if not settings.video_project_enabled:
        return None, (
            "design_video is not available in this deployment — no "
            "version was designed or saved. Answer the user directly "
            "about what this deployment CAN do instead."
        )
    from app.editing.edits import EditError  # deferred: write door
    from app.editing.service import format_storyboard_text  # deferred: editing seam
    from app.editing.store import (  # deferred: write door
        CompositionNotFound,
        PermissionDenied,
    )
    from app.tools.video.design import DesignError, design_video  # deferred: tool seam
    from app.tools.video.programs import enrich_generator_previews, generator_preview_images

    try:
        read = await design_video(
            owner_id=project.user_id,
            project_id=project.id,
            args=args,
            request_id=request_id,
        )
    except (CompositionNotFound, PermissionDenied):
        return None, (
            "that video work does not exist in this project — never "
            "retry with the same reference; if the user named an older "
            "work, say honestly it is gone"
        )
    except (DesignError, EditError, ValueError) as exc:
        return None, f"design_video rejected: {exc}"
    redraft = read.get("change_set") is not None
    read = await enrich_generator_previews(read)
    preview_images = tuple(await generator_preview_images(read))
    preview_note = (
        "\nExact drawing-v1 preview media is stored; the attached image is its real middle frame. "
        "The user card carries the playable MP4 for this same program digest. Do not claim aesthetic approval."
        if read.get("generator_previews") else ""
    )
    return read, ToolObservation(
        f"Video version {read['version']} designed and saved "
        f"(composition {read['composition_id']}; "
        f"{'redraft — the earlier versions stay in history' if redraft else 'first version'}; "
        "no plan docked, no run started, nothing has been produced). "
        "Your next message introduces its saved storyboard card briefly. "
        "The system attaches the COMPLETE canonical card automatically; "
        "do not duplicate its scenes or internal ids in prose. Then "
        "wait for the user's word: a saved storyboard is not a produced "
        "video, and this chain never starts production on its own.\n"
        "SAVED VERSION (execution truth):\n"
        + format_storyboard_text(read)
        + "\nFeedback re-enters through design_video's "
        "specific_instruction (open direction) or revise_video's edits "
        "(targeted ops with base_ref echoed verbatim). What this chain "
        "cannot express yet — arbitrary speed changes and transitions — "
        "is said honestly, never faked."
        + preview_note,
        images=preview_images,
    )


async def revise_video_seat(
    *,
    project: Project,
    args: ReviseVideoArgs,
    request_id: str,
) -> tuple[dict[str, Any] | None, str | ToolObservation]:
    """revise_video (非终态): explicit base_ref → translated ops → the
    write door (own session) → the new version's canonical read + the
    system-computed change set. The revision alone never starts
    production."""
    from app.config import settings  # deferred: config leaf

    if not settings.video_project_enabled:
        return None, (
            "revise_video is not available in this deployment — no "
            "change was made and the current version stands untouched."
        )
    from app.editing.edits import EditError  # deferred: write door
    from app.editing.service import (  # deferred: editing seam
        format_storyboard_text,
        revise_video,
    )
    from app.editing.store import (  # deferred: write door
        CompositionNotFound,
        PermissionDenied,
    )
    from app.models.database import AsyncSessionLocal  # deferred: db seam
    from app.tools.video.programs import (
        enrich_generator_previews,
        generator_preview_images,
        prepare_generator_media,
    )

    try:
        async with AsyncSessionLocal() as video_db:
            read = await revise_video(
                video_db,
                owner_id=project.user_id,
                args=args,
                request_id=request_id,
                prepare_candidate=prepare_generator_media,
            )
    except (CompositionNotFound, PermissionDenied):
        return None, (
            "base_ref names a version this project cannot see — re-read "
            "the current version with get_video_version and echo its "
            "base_ref verbatim"
        )
    except (EditError, ValueError) as exc:
        return None, f"revise_video rejected: {exc}"
    import json

    read = await enrich_generator_previews(read)
    preview_images = tuple(await generator_preview_images(read))
    preview_note = (
        "\nThe revised exact program preview is attached; its MP4 and representative frame share the new digest. "
        "Internal code/parameter changes require this reproduction; external layout alone reuses the fixed media."
        if read.get("generator_previews") else ""
    )
    return read, ToolObservation(
        f"Video version {read['version']} saved as a revision "
        "(no run started, nothing has been produced). The SYSTEM computed "
        "this change set — summarize the changed user-visible facts, never re-derive the delta "
        "yourself:\n"
        + json.dumps(read.get("change_set") or {}, ensure_ascii=False, indent=1)
        + "\nThe system attaches the complete saved storyboard card; introduce it briefly without repeating its scenes. Canonical "
        "facts (internal ids stay internal):\n"
        + format_storyboard_text(read)
        + preview_note,
        images=preview_images,
    )


def stamp_video_presentation(
    project: Project, message: Message | None, read: dict[str, Any] | None
) -> PendingPlan | None:
    """The presentation association (ADR-145 phase B; the film stamp's
    sibling): fires from a runner's finish when a video design/revision
    beat this turn is owed its presentation and a TERMINAL speech row
    actually persisted. Two writes ride the turn's one transaction: the
    receipt on ``pending_brief.video_presentation`` (with the presenting
    row's id filled in) and the storyboard block on that row. Returns the
    updated PendingPlan, or None when nothing was owed / no row persisted
    (a degrade row never stamps — an unseen version stays honestly
    unpresented).

    review_hold is TRUE for every presentation in this phase: no
    production path exists yet, so a presented version ALWAYS waits for
    the user's word — the lower half's production wiring re-reads this
    receipt when it lands.
    """
    if read is None or message is None:
        return None
    from app.editing.service import (  # deferred: editing seam
        storyboard_block,
        video_presentation_receipt,
    )

    receipt = video_presentation_receipt(read, review_hold=True)
    for key in ("authorized_revision_message_id", "prior_presented_message_id", "prior_reviewed_output_id"):
        if read.get(key):
            receipt[key] = read[key]
    receipt["presented_message_id"] = str(message.id)
    stored = PendingPlan.model_validate(project.pending_brief or {})
    updated = stored.model_copy(update={"video_presentation": receipt})
    project.pending_brief = updated.model_dump(mode="json")
    message.blocks = [{**storyboard_block(read), "presented_message_id": str(message.id)}]
    return updated
