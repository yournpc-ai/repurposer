"""Shared application service for the video content chain (B2).

design / revise / read share ONE seat — the chat plan path and the propose
path both land here; neither carries its own compose/patch copy. Everything
content-side passes the single write door (``apply_composition_edits``):
this module applies bounded and complete-entity revisions, computes the system change set,
and shapes the canonical read.

The design orchestration's IO half (capture, snapshot freezing, the director
LLM call) lives in ``app/tools/video/design.py`` — gate 6a keeps this module
on models+editing imports only; what arrives here is already prepared.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.editing.edits import EditError, replace_text_ops
from app.editing.revisions import (
    AddMediaOverlayAction as RevisionAddMediaOverlayAction,
    expand_revision_action,
)
from app.editing.schemas import Clip, CompositionContent
from app.editing.storyboard import storyboard_payload
from app.editing.store import (
    PermissionDenied,
    apply_composition_edits,
    content_of,
    get_video_version,
    snapshot_facts,
)
from app.models.schemas import (
    ReviseVideoActionArgs,
    ReviseVideoArgs,
    ReviseVideoTextArgs,
    canonical_json_hash,
)
from app.models.tables import Composition, CompositionVersion


class VideoServiceError(ValueError):
    """A revision/design rejection whose text is model-facing feedback."""


def presentation_digest_of(payload: dict[str, Any]) -> str:
    """The presented content's identity (§2.3): the canonical storyboard
    payload's hash — the receipt proves THIS table was presented for THIS
    version."""
    return canonical_json_hash(payload)


def version_read_dict(
    composition: Composition, version: CompositionVersion, payload: dict[str, Any]
) -> dict[str, Any]:
    """The version read/presentation facts (one shape for the tool
    observation, the receipt and the DTO route)."""
    return {
        "composition_id": str(composition.id),
        "composition_name": composition.name,
        "composition_version_id": str(version.id),
        "version": version.version,
        "content_digest": version.content_digest,
        "base_ref": {
            "composition_id": str(composition.id),
            "composition_version_id": str(version.id),
            "content_digest": version.content_digest,
        },
        "presentation_digest": presentation_digest_of(payload),
        "storyboard": payload,
    }


async def video_version_read(
    db: AsyncSession,
    *,
    owner_id: UUID,
    version_id: UUID | None = None,
    composition_id: UUID | None = None,
    output_id: UUID | None = None,
) -> dict[str, Any]:
    """The explicit version read face (§2.2) with its canonical storyboard."""
    if output_id is not None:
        from app.models.tables import Output, Project
        output = await db.get(Output, output_id)
        project = await db.get(Project, output.project_id) if output else None
        if (project is None or project.user_id != owner_id
                or output.composition_version_id is None):
            raise VideoServiceError("This output has no accessible editable video version")
        version_id = output.composition_version_id
    composition, version = await get_video_version(
        db, owner_id=owner_id, version_id=version_id, composition_id=composition_id
    )
    content = content_of(version)
    facts = await snapshot_facts(db, {b.snapshot_id for b in content.sources})
    payload = storyboard_payload(
        content,
        composition_id=composition.id,
        version_id=version.id,
        version=version.version,
        content_digest=version.content_digest,
        source_facts=facts,
    )
    read = version_read_dict(composition, version, payload)
    read["is_current"] = composition.current_version_id == version.id
    read["current_version_id"] = str(composition.current_version_id)
    return read


# ---------------------------------------------------------------------------
# Revision: complete entities → the single write door
# ---------------------------------------------------------------------------

async def revise_video(
    db: AsyncSession,
    *,
    owner_id: UUID,
    args: ReviseVideoArgs | ReviseVideoActionArgs | ReviseVideoTextArgs,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Apply complete entities or one bounded action to an exact base."""
    if args.base_ref is None:
        raise VideoServiceError("revise_video needs a resolved current work before execution")
    composition, base_version = await get_video_version(
        db,
        owner_id=owner_id,
        version_id=args.base_ref.composition_version_id,
    )
    if composition.id != args.base_ref.composition_id:
        raise VideoServiceError(
            "base_ref's composition_id does not match the version's work — "
            "re-read the version with get_video_version and echo its base_ref"
        )
    base_content = content_of(base_version)
    provenance = deepcopy(base_version.skill_provenance or {})
    write: dict[str, Any]
    if isinstance(args, ReviseVideoTextArgs):
        clip = next(
            (clip for track in base_content.timeline.tracks for clip in track.clips
             if clip.clip_id == args.clip_id),
            None,
        )
        if clip is None:
            raise VideoServiceError(f"clip {args.clip_id!r} does not exist in the base version")
        ops = replace_text_ops(clip, args.text)
        if not ops:
            raise VideoServiceError("the text already matches the requested value")
        write = {"ops": ops}
    elif isinstance(args, ReviseVideoActionArgs):
        source_ids = {binding.snapshot_id for binding in base_content.sources}
        if isinstance(args.action, RevisionAddMediaOverlayAction):
            source_ids.add(args.action.source_id)
        source_facts = await snapshot_facts(db, source_ids)
        if any(fact.get("owner_id") != owner_id for fact in source_facts.values()):
            raise PermissionDenied("a referenced source snapshot belongs to another user")
        ops = expand_revision_action(
            args.action,
            base_content,
            facts=source_facts,
            request_context=args._request_context,
        )
        if not ops:
            raise VideoServiceError("the action does not change the saved version")
        write = {"ops": ops}
    else:
        from app.editing.edits import apply_entity_writes

        write = {"content": apply_entity_writes(base_content, args.entity_writes())}
    _, version, replayed = await apply_composition_edits(
        db,
        owner_id=owner_id,
        composition_id=composition.id,
        base_version_id=base_version.id,
        base_digest=args.base_ref.content_digest,
        request_id=request_id,
        skill_provenance=provenance,
        **write,
    )
    new_content = content_of(version)
    facts = await snapshot_facts(db, {b.snapshot_id for b in new_content.sources})
    payload = storyboard_payload(
        new_content,
        composition_id=composition.id,
        version_id=version.id,
        version=version.version,
        content_digest=version.content_digest,
        source_facts=facts,
    )
    read = version_read_dict(composition, version, payload)
    read["change_set"] = compute_change_set(base_content, new_content)
    read["previous_version_ref"] = args.base_ref.model_dump(mode="json")
    read["replayed"] = replayed
    return read


# ---------------------------------------------------------------------------
# Change set (system-computed, never model-reported — §2.2)
# ---------------------------------------------------------------------------

def compute_change_set(
    base: CompositionContent, new: CompositionContent
) -> dict[str, Any]:
    """The honest delta between two saved versions: scene adds/removals/
    moves, clip adds/removals/updates with the changed fields named."""
    base_scenes = {s.scene_id: s for s in base.scenes}
    new_scenes = {s.scene_id: s for s in new.scenes}
    base_clips = {
        c.clip_id: c for t in base.timeline.tracks for c in t.clips
    }
    new_clips = {c.clip_id: c for t in new.timeline.tracks for c in t.clips}

    def clip_changes(before: Clip, after: Clip) -> list[str]:
        changes: list[str] = []
        if before.range != after.range:
            changes.append("range")
        if before.object.model_dump(mode="json") != after.object.model_dump(mode="json"):
            changes.append("object")
        if [a.model_dump(mode="json") for a in before.animations] != [
            a.model_dump(mode="json") for a in after.animations
        ]:
            changes.append("animations")
        if before.scene_id != after.scene_id:
            changes.append("scene_id")
        if before.source != after.source:
            changes.append("source")
        if before.linked_group_id != after.linked_group_id:
            changes.append("linked_group_id")
        return changes

    def field_changes(before: Any, after: Any, path: str = "") -> list[dict[str, Any]]:
        """Only scalar/list values that actually changed, never the unchanged surroundings."""
        if isinstance(before, dict) and isinstance(after, dict):
            return [
                change
                for key in sorted(before.keys() | after.keys())
                for change in field_changes(
                    before.get(key), after.get(key), f"{path}.{key}" if path else key
                )
            ]
        if before == after:
            return []
        return [{"path": path, "before": before, "after": after}]

    def clip_field_changes(before: Clip, after: Clip) -> list[dict[str, Any]]:
        return field_changes(
            before.model_dump(mode="json", exclude={"track_id"}),
            after.model_dump(mode="json", exclude={"track_id"}),
        )

    return {
        **({"transitions": {"before": [t.model_dump(mode="json") for t in base.timeline.transitions],
                            "after": [t.model_dump(mode="json") for t in new.timeline.transitions]}}
           if base.timeline.transitions != new.timeline.transitions else {}),
        "settings": {
            key: {"before": before, "after": new.settings.model_dump(mode="json")[key]}
            for key, before in base.settings.model_dump(mode="json").items()
            if before != new.settings.model_dump(mode="json")[key]
        },
        "scenes": {
            "added": [sid for sid in new_scenes if sid not in base_scenes],
            "removed": [sid for sid in base_scenes if sid not in new_scenes],
            "moved": [
                {
                    "scene_id": sid,
                    "from_seconds": base_scenes[sid].range.start / base.settings.timebase,
                    "to_seconds": new_scenes[sid].range.start / new.settings.timebase,
                }
                for sid in new_scenes.keys() & base_scenes.keys()
                if new_scenes[sid].range != base_scenes[sid].range
            ],
        },
        "clips": {
            "added": [
                {"clip_id": cid, "kind": new_clips[cid].object.kind}
                for cid in new_clips
                if cid not in base_clips
            ],
            "removed": [cid for cid in base_clips if cid not in new_clips],
            "updated": [
                {
                    "clip_id": cid,
                    "changes": clip_changes(base_clips[cid], new_clips[cid]),
                    "fields": clip_field_changes(base_clips[cid], new_clips[cid]),
                }
                for cid in new_clips.keys() & base_clips.keys()
                if clip_changes(base_clips[cid], new_clips[cid])
            ],
        },
    }


# ---------------------------------------------------------------------------
# The model-facing fact sheet: the canonical payload rendered as compact
# text (the loop's observation; the USER's visible presentation is the
# model's grounded Markdown overview — it never re-transcribes this DTO)
# ---------------------------------------------------------------------------


def storyboard_presentation_rows(read: dict) -> list[dict]:
    """Chronological user-presentation rows derived from the saved version."""
    payload = read["storyboard"]
    presentation_rows: list[dict] = []
    for scene in payload["scenes"]:
        text_clips = sorted(
            (clip for clip in scene["clips"]
             if clip["object_kind"] == "text" and clip["track_role"] == "title"
             and not clip.get("caption")),
            key=lambda clip: clip["range_seconds"]["start"],
        )
        groups: dict[tuple[float, float], list[dict]] = {}
        for clip in text_clips:
            window = clip["range_seconds"]
            groups.setdefault((window["start"], window["end"]), []).append(clip)
        has_beats = len(groups) > 1
        windows = list(groups.items()) if has_beats else [(
            (scene["range_seconds"]["start"], scene["range_seconds"]["end"]), text_clips
        )]
        for beat, ((start, end), clips) in enumerate(windows, start=1):
            presentation_rows.append({
                "shot": f"{scene['number']}.{beat}" if has_beats else str(scene["number"]),
                "scene_number": scene["number"],
                "start_seconds": start,
                "end_seconds": end,
                "duration_seconds": round(end - start, 6),
                "text": "\n".join(clip.get("text") or "" for clip in clips),
                "subject_clip_ids": [clip["clip_id"] for clip in clips],
                "scene_intent": scene.get("intent"),
                "scene_visual_description": scene.get("visual_description"),
            })
    return presentation_rows


def format_storyboard_text(read: dict[str, Any]) -> str:
    """Compact, complete, deterministic: every scene's window, intent,
    picture summary, chronological presentation rows, exact copy and revision ids."""
    payload = read["storyboard"]
    import json

    lines: list[str] = [
        f"Composition {read['composition_id']} “{read['composition_name'] or 'untitled'}” — "
        f"version {read['version']} (id {read['composition_version_id']}).",
        "base_ref for any revision: "
        + json.dumps(read["base_ref"], ensure_ascii=False, sort_keys=True),
        f"Canvas {payload['settings']['width']}x{payload['settings']['height']} "
        f"@ {payload['settings']['fps']:g}fps, {payload['duration_seconds']:.1f}s total.",
    ]
    # A row plan derived from the saved version, not a second editable storyboard.
    # Independently timed text beats stay visible even inside one narrative Scene.
    presentation_rows = storyboard_presentation_rows(read)
    lines.append("Presentation rows (saved output times; scene subnumbers denote reading beats, "
                 "not additional Scenes): " + json.dumps(presentation_rows, ensure_ascii=False))
    if read.get("is_current") is False:
        lines.append(
            "This output pins an OLDER version. Current version_id="
            + read["current_version_id"]
            + "; read current and clarify which version to continue; never overwrite silently."
        )
    for scene in payload["scenes"]:
        rng = scene["range_seconds"]
        lines.append(
            f"\n#{scene['number']} {scene['scene_id']} [{rng['start']:.2f}s–{rng['end']:.2f}s]"
            + (f" — {scene['intent']}" if scene.get("intent") else "")
        )
        if scene.get("visual_description"):
            lines.append(f"  picture: {scene['visual_description']}")
        for clip in scene["clips"]:
            output_range = clip["range_seconds"]
            desc = (f"  clip {clip['clip_id']} ({clip['object_kind']}, {clip['track_role']}) "
                    f"output={output_range['start']:.3f}s–{output_range['end']:.3f}s")
            if clip.get("text") is not None:
                style = clip.get("style") or {}
                desc += f" text={clip['text']!r} (size {style.get('font_size')}, {style.get('color')}, weight {style.get('weight')}, align {style.get('align')})"
            if clip.get("view_id") is not None:
                view = clip.get("view") or {}
                desc += f" view={clip['view_id']} {view.get('heading') or ''}".rstrip()
            if clip.get("source_range_seconds") is not None:
                source_range = clip["source_range_seconds"]
                desc += f" source={source_range['start']:.2f}s–{source_range['end']:.2f}s"
            if clip.get("layout") is not None:
                box = clip["layout"]
                desc += (
                    f" layout=({box['x']:g},{box['y']:g},{box['width']:g},{box['height']:g})"
                )
            if clip.get("transform") is not None:
                desc += " transform=" + json.dumps(clip["transform"], sort_keys=True)
            if clip.get("opacity") is not None:
                desc += f" opacity={clip['opacity']}"
            if clip["object_kind"] == "video":
                desc += f" fit={clip.get('fit')} gain={clip.get('gain_db')}dB muted={clip.get('muted')}"
            if clip["object_kind"] == "speech":
                desc += (
                    f" voice={clip.get('voice_id')} language={clip.get('language')} "
                    f"provider={clip.get('provider')} model={clip.get('model')} gain={clip.get('gain_db')}dB"
                )
            if clip.get("caption") is not None:
                desc += f" caption_state={clip['caption'].get('state')}"
            if clip["object_kind"] == "shape":
                desc += (
                    f" shape={clip.get('shape')} fill={clip.get('fill')} "
                    f"stroke={clip.get('stroke')} opacity={clip.get('opacity')}"
                )
                if clip.get("path"):
                    desc += f" path={clip['path']!r}"
            if clip["object_kind"] == "generator":
                desc += (
                    f" producer={clip.get('producer')} digest={clip.get('program_digest')} "
                    f"output={json.dumps(clip.get('output'), sort_keys=True)} "
                    f"parameters={json.dumps(clip.get('parameters'), ensure_ascii=False, sort_keys=True)}"
                )
                lines.append(desc)
                if clip.get("producer") == "image-generation":
                    lines.append(
                        f"    IMAGE REQUEST provider={clip.get('provider')} model={clip.get('model')} "
                        "(revise its complete owning Clip; internal pixels are not native objects):"
                    )
                    lines.append(str(clip.get("prompt") or ""))
                else:
                    lines.append("    PROGRAM SOURCE (revise inside the complete owning Clip):")
                    if clip.get("project"):
                        lines.append(json.dumps(clip["project"], ensure_ascii=False, sort_keys=True))
                    else:
                        lines.append(str(clip.get("code") or ""))
                desc = None
            if desc is not None:
                lines.append(desc)
            for anim in clip["animations"]:
                kfs = ", ".join(
                    f"{kf['at_seconds']:.2f}s→{kf['value']}" for kf in anim["keyframes"]
                )
                part = f" per {anim['text_part']}" if anim.get("text_part") else ""
                lines.append(
                    f"    anim {anim['animation_id']} {anim['property']}{part}: {kfs}"
                )
    for clip in payload["unassigned_clips"]:
        lines.append(
            f"\nglobal clip {clip['clip_id']} ({clip['object_kind']}, {clip['track_role']})"
        )
    for transition in payload.get("transitions", []):
        lines.append("transition " + json.dumps(transition, sort_keys=True))
    duration = float(payload["duration_seconds"])
    fps = float(payload["settings"]["fps"])
    final_frame_at = max(0.0, duration - 1.0 / fps)
    all_clips = [
        clip for scene in payload["scenes"] for clip in scene["clips"]
    ] + payload["unassigned_clips"]
    final_clips = [
        clip
        for clip in all_clips
        if clip["range_seconds"]["start"] <= final_frame_at < clip["range_seconds"]["end"]
    ]
    final_facts = ", ".join(
        f"{clip['clip_id']} ({clip['object_kind']})" for clip in final_clips
    ) or "none"
    lines.append(
        f"\nFinal-frame facts at {final_frame_at:.3f}s: active clips = {final_facts}. "
        "Clips whose ranges ended earlier are absent from the final frame."
    )
    for source in payload["sources"]:
        if (source.get("beat_grid") or {}).get("available") or (source.get("beat_grid") or {}).get("bpm"):
            lines.append(f"frozen music snapshot {source['snapshot_id']} BeatGrid={source['beat_grid']}")
    speech_clips = [
        clip
        for scene in payload["scenes"]
        for clip in scene["clips"]
        if clip["object_kind"] == "speech"
    ]
    if speech_clips:
        lines.append(
            "\nNarration: reviewed SpeechObjects above; actual audio and sentence-aligned "
            "captions are prepared only by authorized production inside each fixed clip window."
        )
    else:
        lines.append("\nNarration: off.")
    music_clips = [clip for clip in all_clips if clip.get("track_role") == "music"]
    lines.append(
        f"\nMusic: {len(music_clips)} saved Clip(s) in this version."
        if music_clips else "\nMusic: none in this saved version."
    )
    return "\n".join(lines)


def format_revision_text(read: dict[str, Any]) -> str:
    """The saved field-level delta plus the reference needed by the next tool.

    The saved version owns the complete current work. Returning the changed
    clips' whole style/layout/source readout here invites a technical handoff
    and repeats unchanged layers; the system-computed delta is the only fact
    the answering iteration needs. A later parameter question can explicitly
    read the full version again.
    """
    import json

    return json.dumps({
        "version": read["version"],
        "duration_seconds": read["storyboard"]["duration_seconds"],
        "base_ref": read["base_ref"],
        "change_set": read.get("change_set") or {},
    }, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------------------
# The presentation receipt (§2.3 — the generic confirmation state's video
# slice) and its carry across PendingPlan rewrites
# ---------------------------------------------------------------------------


def video_carry_state(stored: Any) -> dict[str, Any]:
    """The video presentation receipt preserved verbatim across a PendingPlan
    rewrite (the film_carry_state sibling): a dock/ask/degrade write never
    drops which version was presented where."""
    return {
        "video_presentation": (
            getattr(stored, "video_presentation", None) if stored is not None else None
        )
    }


def video_presentation_receipt(
    read: dict[str, Any], *, review_hold: bool | None = None
) -> dict[str, Any]:
    """The receipt stamped when a version's canonical storyboard is handed
    to the loop; ``presented_message_id`` fills in when the presenting row
    actually persists (the finish beat's stamp)."""
    return {
        "composition_id": read["composition_id"],
        "composition_version_id": read["composition_version_id"],
        "version": read["version"],
        "content_digest": read["content_digest"],
        "presentation_digest": read["presentation_digest"],
        "presented_message_id": None,
        "review_hold": review_hold,
    }


def storyboard_block(read: dict[str, Any]) -> dict[str, Any]:
    """The version reference stamped on the presenting Markdown reply (§10)."""
    return {
        "kind": "video_storyboard",
        "composition_id": read["composition_id"],
        "composition_version_id": read["composition_version_id"],
        "version": read["version"],
        "content_digest": read["content_digest"],
        "presentation_digest": read["presentation_digest"],
        **({"scrub": read["scrub"]} if read.get("scrub") is not None else {}),
    }


__all__ = [
    "EditError",
    "VideoServiceError",
    "apply_composition_edits",
    "compute_change_set",
    "presentation_digest_of",
    "storyboard_block",
    "storyboard_presentation_rows",
    "video_carry_state",
    "video_presentation_receipt",
    "video_version_read",
    "version_read_dict",
]
