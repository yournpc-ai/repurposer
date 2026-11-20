"""Save an editable first version from ordered shots through the Composition store."""
from typing import Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.agents.tool_progress import current_call_id
from app.editing.schemas import CompositionContent, VersionSettings
from app.editing.store import RequestMismatch, apply_composition_edits, snapshot_facts
from app.models.schemas import canonical_json_hash
from app.models.tables import Composition, CompositionVersion, Message, Project, SourceSnapshot
from app.tools.video.design import (
    CompositionSceneAuthoring, CompositionScenePlan, _expand_scene_authoring, _scene_plan_write,
)


class FirstShot(CompositionSceneAuthoring):
    scene_id: str = Field(default="", exclude=True, description="Assigned by the editor; omit.")
    duration_seconds: float | None = Field(default=None, gt=0, allow_inf_nan=False,
                                           description="Exact duration of a still or title.")
    text_color: str = Field(default="#FFFFFF", pattern=r"^#[0-9A-Fa-f]{6}$")
    title_motion: Literal["static", "entrance"] = "static"
    source_motion: Literal["hold", "push"] = "hold"


class CreateVideoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    shots: list[FirstShot] = Field(min_length=1, max_length=64)
    aspect: Literal["16:9", "9:16", "1:1"] = "16:9"
    background: str = Field(default="#000000", pattern=r"^#[0-9A-Fa-f]{6}$")
    fps: int = Field(default=30, ge=1, le=120)


async def create_video(db, turn, args: CreateVideoArgs):
    from app.chat.service import _lock_turn_for_transcript_write
    from app.editing.service import video_version_read

    opening = await _lock_turn_for_transcript_write(db, turn.turn_id)
    if opening.role != "user" or opening.conversation_id != turn.conversation_id:
        raise ValueError("The opening message is unavailable.")
    owner, project = turn.project.user_id, turn.project.id
    identity = str(uuid5(turn.turn_id, current_call_id()))
    fingerprint = canonical_json_hash({"tool": "create_video", "args": args.model_dump(mode="json")})
    markers = (opening.intent or {}).get("editor_commits", [])
    marker = next((item for item in markers if item["request"] == identity), None)
    if marker:
        if marker["fingerprint"] != fingerprint:
            raise RequestMismatch("This call already saved different content.")
        saved = await db.scalar(select(CompositionVersion).join(Composition, Composition.id == CompositionVersion.composition_id)
                                .where(CompositionVersion.request_id == identity, Composition.owner_id == owner,
                                       Composition.origin_project_id == project))
        if saved is None:
            raise ValueError("The saved version is unavailable.")
    else:
        if opening.turn_state != "in_flight":
            raise ValueError("This turn has ended.")
        await db.execute(select(Project.id).where(Project.id == project, Project.user_id == owner)
                         .with_for_update(key_share=True))
        if await db.scalar(select(Composition.id).where(Composition.origin_project_id == project).limit(1)):
            raise ValueError("This project already has a saved work. Inspect it before editing.")
        if await db.scalar(select(Message.id).where(Message.turn_id == opening.id,
                                                    Message.intent["editor_media"].astext == identity)):
            raise RequestMismatch("This call already belongs to a media request.")

        ids = {sid for shot in args.shots for sid in (shot.snapshot_id, shot.narration_snapshot_id) if sid}
        accessible = set(await db.scalars(select(SourceSnapshot.id).where(SourceSnapshot.id.in_(ids),
                              SourceSnapshot.owner_id == owner, SourceSnapshot.origin_project_id == project)))
        if accessible != ids:
            raise ValueError("Choose fixed sources available in this project.")
        facts = await snapshot_facts(db, ids)
        width, height = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}[args.aspect]
        settings = VersionSettings(width=width, height=height, fps={"num": args.fps}, background=args.background)
        content = CompositionContent(settings=settings).model_dump(mode="json")
        shots = [shot.model_copy(update={"scene_id": f"scene_{i + 1}"}) for i, shot in enumerate(args.shots)]
        content = _scene_plan_write(content, [CompositionScenePlan(scene_id=shot.scene_id,
                                    intent=shot.headline or args.name) for shot in shots])
        for shot in shots:
            content = await _expand_scene_authoring(content, shot, facts, owner)
        activity = await db.scalar(select(Message.id).where(Message.turn_id == opening.id,
                                   Message.intent["frame"]["call_id"].astext == current_call_id(),
                                   Message.intent["frame"]["status"].astext == "active").limit(1))
        opening.intent = {**(opening.intent or {}), "editor_commits": [*markers, {
            "request": identity, "tool": "create_video", "fingerprint": fingerprint,
            "activity_row": str(activity) if activity else None,
        }]}
        _, saved, _ = await apply_composition_edits(db, owner_id=owner, origin_project_id=project,
                                                    name=args.name, content=content, request_id=identity)
    read = await video_version_read(db, owner_id=owner, version_id=saved.id)
    turn._video_presentation_pending = read
    from app.chat.editor import _remember_labels

    _remember_labels(turn, [], saved.id, saved.content_digest, saved.version)
    return {"composition_id": str(saved.composition_id), "version_id": str(saved.id), "version": saved.version,
            "content_digest": saved.content_digest, "saved": True, "shots": [
                {"seconds": (clip["range"]["end"] - clip["range"]["start"]) / saved.settings["timebase"],
                 "text": clip["object"]["text"], "color": clip["object"]["style"]["color"],
                 "animated": bool(clip["animations"])} for track in saved.timeline["tracks"] for clip in track["clips"]
                if clip["object"]["kind"] == "text"
            ]}
