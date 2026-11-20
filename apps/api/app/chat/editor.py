"""Direct operations on the saved work selected in this Chat round."""

import json
from fractions import Fraction
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.agents.tool_loop import ChatTool, ToolObservation, ToolPresentation
from app.agents.tool_progress import current_call_id
from app.editing.edits import SplitClip
from app.editing.store import apply_composition_edits, content_of, get_video_version
from app.editing.timing import SOURCE_TIMEBASE
from app.models.database import AsyncSessionLocal
from app.models.schemas import VideoRangeScrubTarget
from app.models.tables import CompositionVersion


class InspectTimelineArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offset: int = Field(default=0, ge=0, description="First clip index, starting at zero.")


class SplitClipArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clip_id: str = Field(min_length=1, max_length=128)
    time: float = Field(
        gt=0, allow_inf_nan=False, description="Seconds from the start of this clip."
    )


EDITOR_TOOLS = (
    ChatTool(
        "inspect_timeline",
        "Read the selected version's clips in timeline order, including source windows.",
        InspectTimelineArgs,
        terminal=False,
        presentation=ToolPresentation(
            kind="read",
            active_key="chat.activity.inspectClips",
            done_key="chat.activity.inspectClipsDone",
        ),
    ),
    ChatTool(
        "split_clip",
        "Split a clip and its linked media at a clip-local time. Save one version.",
        SplitClipArgs,
        terminal=False,
        presentation=ToolPresentation(
            kind="read",
            active_key="chat.activity.splitClip",
            done_key="chat.activity.splitClipDone",
        ),
    ),
    ChatTool(
        "preview_range",
        "Play the complete local window across all active tracks and cuts. Both times are seconds from the start of the composition.",
        VideoRangeScrubTarget,
        terminal=False,
        presentation=ToolPresentation(
            kind="read",
            active_key="chat.activity.previewRange",
            done_key="chat.activity.previewRangeDone",
        ),
    ),
)
EDITOR_NAMES = frozenset(tool.name for tool in EDITOR_TOOLS)


async def split_clip(
    db, *, project, opening_id, conversation_id, call_id, base, args, inspected_version=None
):
    from app.chat.service import TurnStopped, _lock_turn_for_transcript_write

    opening = await _lock_turn_for_transcript_write(db, opening_id)
    if opening.conversation_id != conversation_id or opening.role != "user":
        raise ValueError("The editing request is unavailable.")
    identity = uuid5(opening_id, call_id)
    # A replay can arrive after the round reader has already observed our new
    # head. Reconstruct the original request against its immutable base and
    # let the store compare its digest before returning the committed row.
    previous = await db.scalar(
        select(CompositionVersion).where(
            CompositionVersion.request_id == str(identity),
            CompositionVersion.composition_id == UUID(base["composition_id"]),
        )
    )
    if previous is None:
        if opening.turn_state != "in_flight":
            raise TurnStopped(str(opening_id))
        if inspected_version and inspected_version != base["composition_version_id"]:
            raise ValueError(
                "The timeline changed since inspection. Inspect the current clips again."
            )
    composition, version = await get_video_version(
        db,
        owner_id=project.user_id,
        version_id=previous.base_version_id if previous else UUID(base["composition_version_id"]),
    )
    if (
        str(composition.id) != base["composition_id"]
        or composition.origin_project_id != project.id
        or (not previous and version.content_digest != base["content_digest"])
    ):
        raise ValueError("The selected work or version changed.")
    content = content_of(version)
    clips = {c.clip_id: c for track in content.timeline.tracks for c in track.clips}
    target = clips.get(args.clip_id)
    if target is None:
        raise ValueError("The selected clip does not exist in this version.")
    offset = Fraction(str(args.time)) * content.settings.timebase
    if offset.denominator != 1:
        raise ValueError("The cut must fall on an exact composition tick.")
    cut = target.range.start + int(offset)
    if not target.range.start < cut < target.range.end:
        raise ValueError("The cut must be strictly inside the selected clip.")
    right = f"clp_{identity.hex}"
    _, saved, replayed = await apply_composition_edits(
        db,
        owner_id=project.user_id,
        composition_id=composition.id,
        base_version_id=version.id,
        base_digest=version.content_digest,
        request_id=str(identity),
        skill_provenance=version.skill_provenance,
        ops=[
            SplitClip(
                op="split_clip",
                clip_id=args.clip_id,
                at=cut,
                new_clip_id=right,
                new_object_id=f"obj_{identity.hex}",
            )
        ],
    )
    return {
        "composition_id": str(composition.id),
        "base_version_id": str(version.id),
        "version_id": str(saved.id),
        "version": saved.version,
        "content_digest": saved.content_digest,
        "left_clip_id": target.clip_id,
        "right_clip_id": right,
        "replayed": replayed,
        "cut_seconds": cut / content.settings.timebase,
        "added_clips": [
            c["clip_id"]
            for t in saved.timeline["tracks"]
            for c in t["clips"]
            if c["clip_id"] not in clips
        ],
    }


async def execute_editor(turn, name, args):
    base = getattr(turn, "_video_base_ref", None)
    if not base or turn.project is None:
        return ToolObservation(
            "Select one accessible, current saved work before editing.", ok=False
        )
    async with AsyncSessionLocal() as db:
        try:
            if name == "split_clip":
                if not turn.turn_id or not current_call_id():
                    raise ValueError("A persisted turn and native call identity are required.")
                result = await split_clip(
                    db,
                    project=turn.project,
                    opening_id=turn.turn_id,
                    conversation_id=turn.conversation_id,
                    call_id=current_call_id(),
                    base=base,
                    args=args,
                    inspected_version=getattr(turn, "_inspected_version", None),
                )
                turn._inspected_version = result["version_id"]
                if getattr(turn, "_editor_output_pin", None):
                    turn._editor_output_pin["version_id"] = result["version_id"]
                turn._video_presentation_pending = None
                return ToolObservation(json.dumps(result))
            composition, version = await get_video_version(
                db,
                owner_id=turn.project.user_id,
                version_id=UUID(base["composition_version_id"]),
            )
            if (
                composition.origin_project_id != turn.project.id
                or str(composition.id) != base["composition_id"]
            ):
                raise ValueError("This version is outside the selected project.")
            if name == "inspect_timeline":
                turn._inspected_version = str(version.id)
                content = content_of(version)
                clips = sorted(
                    ((track, c) for track in content.timeline.tracks for c in track.clips),
                    key=lambda pair: (pair[1].range.start, pair[0].order, pair[1].clip_id),
                )
                return ToolObservation(
                    json.dumps(
                        {
                            "version_id": str(version.id),
                            "count": len(clips),
                            "offset": args.offset,
                            "timebase": content.settings.timebase,
                            "source_timebase": SOURCE_TIMEBASE,
                            "clips": [
                                {
                                    "clip_id": c.clip_id,
                                    "track_id": track.track_id,
                                    "scene_id": c.scene_id,
                                    "kind": c.object.kind,
                                    "linked_group_id": c.linked_group_id,
                                    "layout": c.object.layout.model_dump()
                                    if getattr(c.object, "layout", None)
                                    else None,
                                    "start_seconds": c.range.start / content.settings.timebase,
                                    "end_seconds": c.range.end / content.settings.timebase,
                                    "source": c.source.model_dump(mode="json")
                                    if c.source
                                    else None,
                                }
                                for track, c in clips[args.offset : args.offset + 24]
                            ],
                        }
                    ),
                    fold_after_delivery=True,
                )
            if name != "preview_range":
                raise ValueError("Unknown editor operation.")
            from app.editing.service import video_version_read
            from app.tools.video.preview import prepare_saved_video_scrub, saved_preview_media

            read = await video_version_read(
                db, owner_id=turn.project.user_id, version_id=version.id
            )
            read = await prepare_saved_video_scrub(
                db, read, owner_id=turn.project.user_id, target=args
            )
            preview = read["video_preview"]
            if preview["status"] != "ready":
                raise ValueError(preview.get("reason") or preview["status"])
            media, evidence = await saved_preview_media(preview, version.id)
            turn._video_presentation_pending = read
            return ToolObservation(json.dumps(evidence), images=media)
        except ValueError as exc:
            return ToolObservation(str(exc), ok=False)
