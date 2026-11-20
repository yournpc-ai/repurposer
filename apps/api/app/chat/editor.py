"""Direct operations on the saved work selected in this Chat round."""

import json
import re
from fractions import Fraction
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select

from app.agents.tool_loop import ChatTool, ToolObservation, ToolPresentation
from app.agents.tool_progress import current_call_id
from app.editing.edits import SplitClip, TemporalEdit, UpdateClip
from app.editing.schemas import EditTarget
from app.editing.store import (
    RequestMismatch,
    apply_composition_edits,
    content_of,
    get_video_version,
)
from app.editing.timing import SOURCE_TIMEBASE
from app.models.database import AsyncSessionLocal
from app.models.schemas import VideoRangeScrubTarget, canonical_json_hash
from app.models.tables import CompositionVersion, Message


class InspectTimelineArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offset: int = Field(default=0, ge=0, description="First clip index, starting at zero.")


class ClipArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clip_id: str = Field(min_length=1, max_length=64)


class SplitClipArgs(ClipArgs):
    time: float = Field(
        gt=0, allow_inf_nan=False, description="Seconds from the start of this clip."
    )


class TrimClipArgs(ClipArgs):
    start: float | None = Field(
        None,
        ge=0,
        allow_inf_nan=False,
        description="First clip-local second to keep. Defaults to zero.",
    )
    end: float | None = Field(
        None,
        gt=0,
        allow_inf_nan=False,
        description="Exclusive clip-local end to keep. Defaults to the clip duration.",
    )

    @model_validator(mode="after")
    def check_window(self):
        if self.start is None and self.end is None:
            raise ValueError("Specify a boundary to trim.")
        if self.end is not None and self.end <= (self.start or 0):
            raise ValueError("The retained window must have a positive duration.")
        return self


class MoveClipArgs(ClipArgs):
    time: float = Field(
        ge=0, allow_inf_nan=False, description="New absolute start in composition seconds."
    )


class ObjectArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(
        min_length=1, max_length=64, description="Visual object_id returned by inspection."
    )


class TranslateArgs(ObjectArgs):
    x: float = Field(
        allow_inf_nan=False,
        description="Horizontal offset from the layout box, in canvas pixels; positive is right.",
    )
    y: float = Field(
        allow_inf_nan=False,
        description="Vertical offset from the layout box, in canvas pixels; positive is down.",
    )


class ScaleArgs(ObjectArgs):
    value: float = Field(
        gt=0,
        allow_inf_nan=False,
        description="Absolute scale relative to layout size, 1 = original. Preserve origin and position.",
    )


def _editor_tool(name, description, args, key):
    return ChatTool(
        name,
        description,
        args,
        terminal=False,
        presentation=ToolPresentation(
            kind="read",
            active_key="chat.activity." + key,
            done_key="chat.activity." + key + "Done",
        ),
    )


EDITOR_TOOLS = (
    _editor_tool(
        "inspect_timeline",
        "Read clips in timeline order, their tracks, scene numbers, source windows and spatial object IDs.",
        InspectTimelineArgs,
        "inspectClips",
    ),
    _editor_tool(
        "inspect_clip",
        "Inspect one clip, its layout, transform, animation properties and same-track neighbors on the current version.",
        ClipArgs,
        "inspectClip",
    ),
    _editor_tool(
        "split_clip",
        "Split a clip and its linked media at a clip-local second. Save one version.",
        SplitClipArgs,
        "splitClip",
    ),
    _editor_tool(
        "trim_clip",
        "Keep a subrange measured from this clip's start. Crop linked fixed sources at 1x, leave gaps, keep other clips in place. Reject broken transitions or loss of a linked member.",
        TrimClipArgs,
        "trimClip",
    ),
    _editor_tool(
        "move_clip",
        "Set a clip's start on the timeline, moving its linked clips equally. Preserve duration and source window, leave gaps. Reject same-track collisions, broken transitions and scene escape.",
        MoveClipArgs,
        "moveClip",
    ),
    _editor_tool(
        "translate",
        "Set one visual object's static offset relative to its layout box. Preserve other objects and time. Reject an animated position.",
        TranslateArgs,
        "translate",
    ),
    _editor_tool(
        "scale",
        "Set one visual object's static scale around its existing origin. Preserve other objects, including subtitles. Reject animated scale.",
        ScaleArgs,
        "scale",
    ),
    _editor_tool(
        "preview_range",
        "Play the current composition across all tracks and cuts. Specify start and end seconds from the beginning (up to 12 seconds).",
        VideoRangeScrubTarget,
        "previewRange",
    ),
)
EDITOR_NAMES = frozenset(tool.name for tool in EDITOR_TOOLS)
WRITE_TOOLS = {
    t.name: t
    for t in EDITOR_TOOLS
    if t.params_model in (SplitClipArgs, TrimClipArgs, MoveClipArgs, TranslateArgs, ScaleArgs)
}


def _ticks(seconds, timebase):
    ticks = Fraction(str(seconds)) * timebase
    if ticks.denominator != 1:
        raise ValueError("The time must fall on an exact composition tick.")
    return int(ticks)


def _clip_facts(track, clip, content):
    rate = content.settings.timebase
    obj = clip.object
    transform = getattr(obj, "transform", None)
    scene_number = next(
        (i for i, scene in enumerate(content.scenes, 1) if scene.scene_id == clip.scene_id), None
    )
    return {
        "clip_id": clip.clip_id,
        "object_id": obj.object_id,
        "kind": obj.kind,
        "track_id": track.track_id,
        "track_role": track.role,
        "scene_id": clip.scene_id,
        "scene_number": scene_number,
        "linked_group_id": clip.linked_group_id,
        "start_seconds": clip.range.start / rate,
        "end_seconds": clip.range.end / rate,
        "source": clip.source.model_dump(mode="json") if clip.source else None,
        "layout": obj.layout.model_dump() if getattr(obj, "layout", None) else None,
        "transform": transform.model_dump() if transform else None,
        "animated_properties": sorted({a.property for a in clip.animations if a.text_part is None}),
        **({"text": obj.text[:160]} if obj.kind == "text" else {}),
    }


async def edit_clip(
    db, *, name, project, opening_id, conversation_id, call_id, base, args, inspected_version=None
):
    from app.chat.service import TurnStopped, _lock_turn_for_transcript_write

    opening = await _lock_turn_for_transcript_write(db, opening_id)
    if opening.conversation_id != conversation_id or opening.role != "user":
        raise ValueError("The editing request is unavailable.")
    if name not in WRITE_TOOLS or not isinstance(args, WRITE_TOOLS[name].params_model):
        raise ValueError("Arguments do not match this editor operation.")
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
    entries = [(track, clip) for track in content.timeline.tracks for clip in track.clips]
    clips = {clip.clip_id: clip for _, clip in entries}
    commits = (opening.intent or {}).get("editor_commits", [])
    prior = next((c for c in commits if c["request"] == str(identity)), None)
    fingerprint = canonical_json_hash({"tool": name, "args": args.model_dump(mode="json")})
    if prior and prior["fingerprint"] != fingerprint:
        raise RequestMismatch("This native call already committed different parameters.")
    rate = content.settings.timebase
    extra = {}
    if isinstance(args, ObjectArgs):
        target = next((clip for _, clip in entries if clip.object.object_id == args.id), None)
        if target is None or not getattr(target.object, "transform", None):
            raise ValueError("Select a visual object with an editable transform.")
        prop = "transform.scale" if name == "scale" else "transform.position"
        if any(a.property == prop and a.text_part is None for a in target.animations):
            raise ValueError(
                "Keyframes control this property. Its static transform cannot make this edit."
            )
        updates = {"scale": args.value} if name == "scale" else {"x": args.x, "y": args.y}
        transform = target.object.transform.model_copy(update=updates)
        if transform == target.object.transform:
            raise ValueError("The object already has this transform.")
        op = UpdateClip(
            op="update_clip",
            clip_id=target.clip_id,
            object=target.object.model_copy(update={"transform": transform}),
        )
    else:
        target = clips.get(args.clip_id)
        if target is None:
            raise ValueError("The selected clip does not exist in this version.")
        if name == "split_clip":
            cut = target.range.start + _ticks(args.time, rate)
            if not target.range.start < cut < target.range.end:
                raise ValueError("The cut must be strictly inside the selected clip.")
            # A short stable native id is also a useful handle in a later round.
            # Historical requests must reproduce their original store digest.
            right = target.clip_id[:56] + "_right"
            if right in clips or (previous and not prior):
                right = f"clp_{identity.hex}"
            op = SplitClip(
                op="split_clip",
                clip_id=target.clip_id,
                at=cut,
                new_clip_id=right,
                new_object_id=f"obj_{identity.hex}",
            )
            extra = {
                "left_clip_id": target.clip_id,
                "right_clip_id": right,
                "cut_seconds": cut / rate,
            }
        elif name == "trim_clip":
            start = target.range.start + _ticks(args.start or 0, rate)
            end = (
                target.range.start + _ticks(args.end, rate)
                if args.end is not None
                else target.range.end
            )
            if (start, end) == (target.range.start, target.range.end):
                raise ValueError("The requested window already covers this clip.")
            op = TemporalEdit(
                op="temporal_edit",
                action="trim",
                target=EditTarget(kind="clip", id=target.clip_id),
                start=start,
                end=end,
                source_policy="crop_1x",
            )
        else:
            start = _ticks(args.time, rate)
            if start == target.range.start:
                raise ValueError("The clip is already at that start time.")
            op = TemporalEdit(
                op="temporal_edit",
                action="move",
                target=EditTarget(kind="clip", id=target.clip_id),
                start=start,
            )
    if previous is None:
        # The pointer and the immutable version live in the same store transaction.
        # Neither becomes visible unless the version passes validation and CAS.
        presentation = WRITE_TOOLS[name].presentation
        active = await db.scalar(
            select(Message.id)
            .where(
                Message.turn_id == opening_id,
                Message.intent["frame"]["status"].astext == "active",
                Message.intent["frame"]["key"].astext == presentation.active_key,
            )
            .order_by(Message.seq.desc())
            .limit(1)
        )
        marker = {
            "request": str(identity),
            "tool": name,
            "fingerprint": fingerprint,
            "activity_row": str(active) if active else None,
        }
        opening.intent = {**(opening.intent or {}), "editor_commits": [*commits, marker]}
    _, saved, replayed = await apply_composition_edits(
        db,
        owner_id=project.user_id,
        composition_id=composition.id,
        base_version_id=version.id,
        base_digest=version.content_digest,
        request_id=str(identity),
        skill_provenance=version.skill_provenance,
        ops=[op],
    )
    saved_content = content_of(saved)
    changed = [
        _clip_facts(t, c, saved_content)
        for t in saved_content.timeline.tracks
        for c in t.clips
        if c != clips.get(c.clip_id)
    ]

    return {
        "composition_id": str(composition.id),
        "base_version_id": str(version.id),
        "version_id": str(saved.id),
        "version": saved.version,
        "content_digest": saved.content_digest,
        **extra,
        "target_before_seconds": [target.range.start / rate, target.range.end / rate],
        "replayed": replayed,
        "changed_clips": changed,
        "added_clips": [c["clip_id"] for c in changed if c["clip_id"] not in clips],
    }


def project_editor_reply(text, labels, user_text):
    if not text or not labels:
        return text
    zh = any("\u4e00" <= c <= "\u9fff" for c in user_text)
    pattern = (
        r"(?<![\w-])`?("
        + "|".join(re.escape(key) for key in sorted(labels, key=len, reverse=True))
        + r")`?(?![\w-])"
    )
    return re.sub(pattern, lambda m: labels[m[1]][0 if zh else 1], text, flags=re.ASCII)


def _remember_labels(turn, facts, version_id, digest, number):
    labels = turn.__dict__.setdefault("_editor_labels", {})
    for identity in (str(version_id), digest):
        for token in (identity, identity[:8], identity[:12]):
            labels[token] = (f"第 {number} 版", f"version {number}")
    for item in facts:
        window = f"{item['start_seconds']:g}–{item['end_seconds']:g}"
        labels[item["clip_id"]] = (window + " 秒的片段", "the " + window + " s clip")
        labels[item["object_id"]] = (window + " 秒的对象", "the object at " + window + " s")


async def execute_editor(turn, name, args):
    base = getattr(turn, "_video_base_ref", None)
    if not base or turn.project is None:
        return ToolObservation(
            "Select one accessible, current saved work before editing.", ok=False
        )
    async with AsyncSessionLocal() as db:
        try:
            if name in WRITE_TOOLS:
                if not turn.turn_id or not current_call_id():
                    raise ValueError("A persisted turn and native call identity are required.")
                from app.chat.editor_recovery import editor_lock_key

                await turn.db.execute(
                    select(func.pg_advisory_xact_lock(editor_lock_key(turn.turn_id)))
                )
                result = await edit_clip(
                    db,
                    name=name,
                    project=turn.project,
                    opening_id=turn.turn_id,
                    conversation_id=turn.conversation_id,
                    call_id=current_call_id(),
                    base=base,
                    args=args,
                    inspected_version=getattr(turn, "_inspected_version", None),
                )
                _remember_labels(
                    turn,
                    result["changed_clips"],
                    result["version_id"],
                    result["content_digest"],
                    result["version"],
                )
                recent = getattr(turn, "_editor_recent", {})
                focused = (
                    dict(recent.get("clips", {}))
                    if recent.get("version_id") == result["base_version_id"]
                    else {}
                )
                for clip in result["changed_clips"]:
                    focused[clip["clip_id"]] = {
                        k: clip[k]
                        for k in ("clip_id", "object_id", "kind", "start_seconds", "end_seconds")
                    }
                applied = (
                    list(recent.get("applied", []))
                    if recent.get("composition_id") == result["composition_id"]
                    else []
                )
                if not any(item["version"] == result["version"] for item in applied):
                    receipt = {
                        "version": result["version"],
                        "tool": name,
                        "arguments": args.model_dump(exclude_none=True),
                    }
                    if name in {"split_clip", "trim_clip", "move_clip"}:
                        receipt["target_before_seconds"] = result["target_before_seconds"]
                        receipt["target_after_seconds"] = {
                            c["clip_id"]: [c["start_seconds"], c["end_seconds"]]
                            for c in result["changed_clips"]
                        }
                    if name == "split_clip":
                        receipt["right_clip_id"] = result["right_clip_id"]
                    before = getattr(turn, "_editor_last_preview", None)
                    if before and before["version_id"] == result["base_version_id"]:
                        receipt["previewed_before_edit"] = before["window_seconds"]
                    applied.append(receipt)
                turn._editor_recent = {
                    "composition_id": result["composition_id"],
                    "version_id": result["version_id"],
                    "clips": dict(list(focused.items())[-24:]),
                    "applied": applied,
                }
                turn._inspected_version = result["version_id"]
                if getattr(turn, "_editor_output_pin", None):
                    turn._editor_output_pin["version_id"] = result["version_id"]
                turn._video_presentation_pending = None
                return ToolObservation(
                    json.dumps(result),
                    valid_for_key=f"composition:{result['version_id']}:{result['content_digest']}",
                )
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
            version_key = f"composition:{version.id}:{version.content_digest}"
            if name in {"inspect_timeline", "inspect_clip"}:
                turn._inspected_version = str(version.id)
                content = content_of(version)
                clips = sorted(
                    ((track, c) for track in content.timeline.tracks for c in track.clips),
                    key=lambda pair: (pair[1].range.start, pair[0].order, pair[1].clip_id),
                )
                if name == "inspect_clip":
                    target = next((item for item in clips if item[1].clip_id == args.clip_id), None)
                    if target is None:
                        raise ValueError("The selected clip does not exist in this version.")
                    neighbors = [item for item in clips if item[0].track_id == target[0].track_id]
                    index = neighbors.index(target)
                    page = neighbors[max(0, index - 1) : index + 2]
                    scope = {"target_clip_id": args.clip_id}
                else:
                    page = clips[args.offset : args.offset + 24]
                    next_offset = args.offset + len(page)
                    scope = {
                        "offset": args.offset,
                        "next_offset": next_offset if next_offset < len(clips) else None,
                    }
                facts = [_clip_facts(track, clip, content) for track, clip in page]
                _remember_labels(turn, facts, version.id, version.content_digest, version.version)
                return ToolObservation(
                    json.dumps(
                        {
                            "version_id": str(version.id),
                            "count": len(clips),
                            **scope,
                            "canvas_px": [content.settings.width, content.settings.height],
                            "timebase": content.settings.timebase,
                            "source_timebase": SOURCE_TIMEBASE,
                            "clips": facts,
                        }
                    ),
                    valid_for_key=version_key,
                )
            if name != "preview_range":
                raise ValueError("Unknown editor operation.")
            from app.editing.service import storyboard_block, video_version_read
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
            turn._editor_last_preview = {
                "version_id": str(version.id),
                "window_seconds": preview["scope"]["source_range_seconds"],
                "model_media": evidence["model_media"],
            }
            block = storyboard_block(read)
            blocks = turn.__dict__.setdefault("_editor_preview_blocks", [])
            if block not in blocks:
                blocks.append(block)
            turn._video_presentation_pending = read
            evidence["coverage"] = (
                "Exact requested window of this version, across all tracks. Reuse for this window until the work changes."
            )
            return ToolObservation(json.dumps(evidence), images=media, valid_for_key=version_key)
        except ValueError as exc:
            return ToolObservation(str(exc), ok=False, fold_after_delivery=True)
