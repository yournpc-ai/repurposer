"""ConversationContext-backed working Composition drafts.

The records carry raw content and explicitly supplied design metadata. Model
observations expose only draft identity, digest and validation facts.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.agents.candidate_correction import CandidateRecord, CorrectionError, exception_errors
from app.editing.edits import ClipEntityWrite, EditError, EntityWrites, apply_entity_writes_raw


@dataclass(frozen=True)
class WorkingDraftRejected:
    """The current working draft failed local or final content validation."""

    reason: str
    errors: list[dict]
    arguments: dict[str, Any]


@dataclass(frozen=True)
class WorkingDraftUpdated:
    """A save=false call merged into the working draft without saving a version."""

    arguments: dict[str, Any]


@dataclass(frozen=True)
class WorkingDraftReviewed:
    """A draft read that retains only the evidence actually obtained."""

    arguments: dict[str, Any]
    observation: Any


def tool_progress_digest(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    base_keys=(),
) -> str:
    """Content-only retry identity for retained tool calls."""
    encoded = json.dumps(
        {
            "target_tool": tool_name,
            "arguments": arguments,
            "base_keys": sorted(base_keys),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def candidate_progress_digest(record: CandidateRecord) -> str:
    """Random candidate ids never fake progress."""
    return tool_progress_digest(
        record.tool_name, record.arguments, base_keys=record.base_keys
    )


def _errors(record: CandidateRecord) -> list[dict]:
    """Keep validator facts and natural Composition paths, not repair programs."""
    return [
        {
            "loc": list(error.get("loc") or error.get("original_loc") or error.get("field_path") or error.get("operation_path") or []),
            "type": error.get("type", "content_validation"),
            "msg": error.get("msg", error.get("message", "invalid Composition")),
            **({"entity": deepcopy(error["entity"])} if error.get("entity") else {}),
            **({"relation": error["relation"]} if error.get("relation") else {}),
            **{
                key: deepcopy(error[key])
                for key in (
                    "reference_text", "line_id", "candidate_text_objects", "expected", "actual",
                )
                if key in error
            },
        }
        for error in record.errors
    ]


def _draft_facts(record: CandidateRecord) -> dict[str, Any]:
    return {
        "draft_id": record.candidate_id,
        "draft_digest": record.candidate_digest,
        "draft_ref": {
            "draft_id": record.candidate_id,
            "draft_digest": record.candidate_digest,
        },
    }


def working_draft_observation(record: CandidateRecord) -> dict[str, Any]:
    review = working_draft_review_facts(record.arguments)
    if not review["review_started"]:
        review = {
            key: value for key, value in review.items()
            if key not in {"editable_targets", "evidence"}
        }
    return {
        "ok": True,
        "saved": False,
        **_draft_facts(record),
        "review": review,
        "errors": [],
    }


def working_draft_diagnostic(
    record: CandidateRecord,
    *,
    kind: str = "content_validation",
) -> dict[str, Any]:
    return {
        "ok": False,
        "saved": False,
        "kind": kind,
        **_draft_facts(record),
        "errors": _errors(record),
    }


def verify_working_draft(record: CandidateRecord, reference: Any) -> None:
    if isinstance(reference, dict):
        draft_id = reference.get("draft_id")
        draft_digest = reference.get("draft_digest")
    else:
        draft_id = getattr(reference, "draft_id", None)
        draft_digest = getattr(reference, "draft_digest", None)
    if not isinstance(draft_id, str) or not isinstance(draft_digest, str):
        raise CorrectionError("invalid_draft", "draft_ref needs string draft_id and draft_digest")
    if record.candidate_id != draft_id:
        raise CorrectionError("unknown_draft", "draft_id does not name a current retained Composition draft")
    if not hmac.compare_digest(record.candidate_digest, draft_digest):
        raise CorrectionError("stale_draft", "draft_digest is stale; read the latest working-draft result")


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return deepcopy(value)


def apply_working_draft_writes(
    content: dict[str, Any],
    writes: EntityWrites,
    *,
    settings: Any = None,
    sources: Any = None,
) -> dict[str, Any]:
    """Merge complete settings/sources and complete entities into raw content."""
    candidate = deepcopy(content)
    if settings is not None:
        candidate["settings"] = _json_value(settings)
    if sources is not None:
        candidate["sources"] = _json_value(sources)
    return apply_entity_writes_raw(candidate, writes)


def _draft_entity_writes(args: Any, content: dict[str, Any]) -> EntityWrites:
    scene_id = getattr(args, "scene_id", None)
    if scene_id is None:
        return args.entity_writes()
    if not any(scene.get("scene_id") == scene_id for scene in content.get("scenes") or []):
        raise EditError(f"scene {scene_id} does not exist in the current draft")
    writes = EntityWrites()
    existing_tracks = {
        track.get("track_id"): track
        for track in (content.get("timeline") or {}).get("tracks") or []
    }
    for track in args.tracks:
        if any(clip.scene_id is not None and clip.scene_id != scene_id for clip in track.clips):
            raise EditError("every Clip in a single-scene write must belong to its scene_id")
        clips = [clip.model_copy(update={"scene_id": scene_id}) for clip in track.clips]
        existing = existing_tracks.get(track.track_id)
        if existing is None:
            writes.tracks.append(track.model_copy(update={"clips": clips}))
            continue
        if any(existing.get(key) != getattr(track, key) for key in ("kind", "role", "order")):
            raise EditError(f"track {track.track_id} must reuse its current kind, role and order")
        writes.clips.extend(
            ClipEntityWrite(track_id=track.track_id, clip=clip) for clip in clips
        )
    return writes


def working_draft_arguments(
    args: Any,
    content: dict[str, Any],
    *,
    base: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Retain content plus only explicitly supplied, non-write design metadata."""
    previous_arguments = base or getattr(args, "_working_draft", None) or {}
    previous = previous_arguments.get("design", {})
    excluded = {
        *EntityWrites.model_fields, "settings", "sources", "save", "draft_ref", "scene_id",
        "scene", "scene_plan", "source_ids", "focus_clip_id", "focus_element_id", "skill_resource",
    }
    current = args.model_dump(
        mode="json",
        exclude_unset=True,
        exclude=excluded,
    )
    design = {**deepcopy(previous), **current}
    if getattr(args, "scene_plan", None) is not None or getattr(args, "scene", None) is not None:
        design["authoring"] = "high_level_scene"
    explicit_constraints = getattr(args, "_explicit_constraints", None)
    if explicit_constraints is not None:
        design["user_constraints"] = deepcopy(explicit_constraints)
    review = review_state_after_edit(previous_arguments, content)
    arguments = {
        "content": deepcopy(content),
        "design": design,
    }
    if review is not None:
        arguments["review"] = review
    return arguments


def merge_working_draft(record: CandidateRecord, args: Any) -> dict[str, Any]:
    """Apply this call's complete values to the authenticated current draft."""
    content = record.arguments.get("content")
    if record.tool_name != "design_video" or not isinstance(content, dict):
        raise CorrectionError("invalid_draft", "the retained record is not a Composition working draft")
    if getattr(args, "scene", None) is not None:
        return working_draft_arguments(args, deepcopy(content), base=record.arguments)
    try:
        merged = apply_working_draft_writes(
            content,
            _draft_entity_writes(args, content),
            settings=getattr(args, "settings", None),
            sources=getattr(args, "sources", None),
        )
    except ValueError as exc:
        raise CorrectionError("invalid_draft_write", str(exc)) from exc
    return working_draft_arguments(args, merged, base=record.arguments)


def _timebase(content: dict[str, Any]) -> int:
    from app.editing.timing import DEFAULT_TIMEBASE

    return int((content.get("settings") or {}).get("timebase") or DEFAULT_TIMEBASE)


def _clips(content: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        clip
        for track in (content.get("timeline") or {}).get("tracks") or []
        for clip in track.get("clips") or []
    ]


def _seconds(content: dict[str, Any], ticks: int) -> float:
    return ticks / _timebase(content)


def _range(content: dict[str, Any], value: dict[str, Any]) -> dict[str, float]:
    return {
        "start": _seconds(content, int(value["start"])),
        "end": _seconds(content, int(value["end"])),
    }


def _union(ranges: list[dict[str, float]]) -> list[dict[str, float]]:
    result: list[dict[str, float]] = []
    for item in sorted(ranges, key=lambda row: (row["start"], row["end"])):
        if item["end"] <= item["start"]:
            continue
        if result and item["start"] <= result[-1]["end"] + 1e-9:
            result[-1]["end"] = max(result[-1]["end"], item["end"])
        else:
            result.append(dict(item))
    return result


def _subtract(
    ranges: list[dict[str, float]], removed: list[dict[str, float]]
) -> list[dict[str, float]]:
    remaining = _union(ranges)
    for cut in _union(removed):
        next_remaining = []
        for item in remaining:
            if cut["end"] <= item["start"] or item["end"] <= cut["start"]:
                next_remaining.append(item)
                continue
            if item["start"] < cut["start"]:
                next_remaining.append({"start": item["start"], "end": cut["start"]})
            if cut["end"] < item["end"]:
                next_remaining.append({"start": cut["end"], "end": item["end"]})
        remaining = next_remaining
    return remaining


def _intersects(left: dict[str, float], right: dict[str, float]) -> bool:
    return left["start"] < right["end"] and right["start"] < left["end"]


def _timeline_range(content: dict[str, Any]) -> dict[str, float] | None:
    entities = [*(content.get("scenes") or []), *_clips(content)]
    ranges = [item.get("range") for item in entities if item.get("range")]
    if not ranges:
        return None
    return {
        "start": _seconds(content, min(int(item["start"]) for item in ranges)),
        "end": _seconds(content, max(int(item["end"]) for item in ranges)),
    }


def _affected_ranges(
    before: dict[str, Any], after: dict[str, Any]
) -> tuple[list[dict[str, float]], set[str], bool]:
    timeline = _timeline_range(after) or _timeline_range(before)
    if timeline is None:
        return [], set(), False
    if before.get("settings") != after.get("settings") or before.get("sources") != after.get("sources"):
        return [timeline], set(), True

    affected: list[dict[str, float]] = []
    changed_clip_ids: set[str] = set()
    old_clips = {item.get("clip_id"): item for item in _clips(before)}
    new_clips = {item.get("clip_id"): item for item in _clips(after)}
    for clip_id in old_clips.keys() | new_clips.keys():
        old, new = old_clips.get(clip_id), new_clips.get(clip_id)
        if old == new:
            continue
        changed_clip_ids.add(str(clip_id))
        affected.extend(_range(after if new else before, item["range"]) for item in (old, new) if item)

    old_scenes = {item.get("scene_id"): item for item in before.get("scenes") or []}
    new_scenes = {item.get("scene_id"): item for item in after.get("scenes") or []}
    for scene_id in old_scenes.keys() | new_scenes.keys():
        old, new = old_scenes.get(scene_id), new_scenes.get(scene_id)
        if old == new or (old or {}).get("range") == (new or {}).get("range"):
            continue
        changed_clip_ids.update(
            str(item.get("clip_id")) for item in (*old_clips.values(), *new_clips.values())
            if item.get("scene_id") == scene_id
        )
        affected.extend(_range(after if new else before, item["range"]) for item in (old, new) if item)

    old_tracks = {
        item.get("track_id"): item
        for item in (before.get("timeline") or {}).get("tracks") or []
    }
    new_tracks = {
        item.get("track_id"): item
        for item in (after.get("timeline") or {}).get("tracks") or []
    }
    for track_id in old_tracks.keys() | new_tracks.keys():
        old, new = old_tracks.get(track_id), new_tracks.get(track_id)
        old_meta = {**(old or {}), "clips": []}
        new_meta = {**(new or {}), "clips": []}
        if old_meta == new_meta:
            continue
        for content, track in ((before, old), (after, new)):
            for clip in (track or {}).get("clips") or []:
                changed_clip_ids.add(str(clip.get("clip_id")))
                affected.append(_range(content, clip["range"]))

    old_transitions = {
        item.get("transition_id"): item
        for item in (before.get("timeline") or {}).get("transitions") or []
    }
    new_transitions = {
        item.get("transition_id"): item
        for item in (after.get("timeline") or {}).get("transitions") or []
    }
    for transition_id in old_transitions.keys() | new_transitions.keys():
        old, new = old_transitions.get(transition_id), new_transitions.get(transition_id)
        if old == new:
            continue
        for transition, content in ((old, before), (new, after)):
            if not transition:
                continue
            clips = {item.get("clip_id"): item for item in _clips(content)}
            changed_clip_ids.update(str(transition.get(key)) for key in ("from_clip_id", "to_clip_id"))
            origin = clips.get(transition.get("from_clip_id"))
            if origin is None:
                affected.append(timeline)
                continue
            cut = int(origin["range"]["end"])
            duration = int(transition.get("duration") or 0)
            affected.append({
                "start": _seconds(content, max(cut - duration // 2, int(origin["range"]["start"]))),
                "end": _seconds(content, cut + duration - duration // 2),
            })
    return _union(affected), changed_clip_ids, False


def review_state_after_edit(
    previous_arguments: dict[str, Any], new_content: dict[str, Any]
) -> dict[str, Any] | None:
    state = deepcopy(previous_arguments.get("review") or {})
    if not state:
        return None
    before = previous_arguments.get("content") or {}
    affected, changed_clip_ids, global_change = _affected_ranges(before, new_content)
    if not affected:
        state["started"] = True
        return state
    invalidated = list(state.get("invalidated") or [])
    for review in state.get("reviews") or []:
        evidence_scope = (review.get("evidence") or {}).get("scope") or {}
        scope = evidence_scope.get("source_range_seconds")
        if not scope:
            continue
        applies = (
            global_change
            or bool(changed_clip_ids & set(evidence_scope.get("clip_ids") or []))
            or any(_intersects(item, scope) for item in affected)
        )
        if not applies:
            continue
        removed = [item for item in affected if _intersects(item, scope)]
        segments = review["valid_segments"] if "valid_segments" in review else [scope]
        still_valid = _subtract(segments, removed)
        actually_removed = _subtract(segments, still_valid)
        review["valid_segments"] = still_valid
        for item in actually_removed:
            invalidated.append({
                "evidence_id": review.get("evidence_id"),
                "range_seconds": item,
                "changed_clip_ids": sorted(changed_clip_ids),
            })
    state["reviews"] = (state.get("reviews") or [])[-16:]
    state["invalidated"] = invalidated[-32:]
    state["started"] = True
    return state


def record_working_draft_review(
    arguments: dict[str, Any], evidence: dict[str, Any]
) -> dict[str, Any]:
    state = deepcopy(arguments.get("review") or {})
    scope = evidence["scope"]
    reviews = list(state.get("reviews") or [])
    identity = {
        "content_digest": evidence.get("content_digest"),
        "media_digest": evidence["observation"]["media_digest"],
        "scope": scope,
    }
    if evidence["observation"].get("confirmation_retry"):
        prior = next((item for item in reversed(reviews)
                      if item.get("valid_segments") and (item.get("judgment") or {}).get("verdict") == "uncertain"), None)
        if (
            prior is None or prior["evidence"]["scope"].get("review_target") != scope.get("review_target")
            or prior["evidence"]["observation"].get("confirmation_retry")
        ):
            raise ValueError("no matching unconfirmed preview to retry")
        prior["valid_segments"] = []
        identity["retry_of"] = prior["evidence_id"]
    evidence_id = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]
    review = {
        "evidence_id": evidence_id,
        "evidence": {**deepcopy(evidence), "evidence_id": evidence_id},
        "valid_segments": [deepcopy(scope["source_range_seconds"])],
        "judgment": None,
    }
    return {
        "content": deepcopy(arguments["content"]),
        "design": deepcopy(arguments.get("design") or {}),
        "review": {
            **state,
            "schema_version": 1,
            "started": True,
            "reviews": [*reviews, review][-16:],
            "invalidated": list(state.get("invalidated") or [])[-32:],
        },
    }


def record_working_draft_judgment(
    arguments: dict[str, Any], judgment: Any
) -> dict[str, Any]:
    value = judgment.model_dump(mode="json") if isinstance(judgment, BaseModel) else deepcopy(judgment)
    reviews = deepcopy((arguments.get("review") or {}).get("reviews") or [])
    review = next((item for item in reviews if item.get("evidence_id") == value["evidence_id"]), None)
    if review is None:
        raise ValueError("evidence_id does not belong to the current working draft")
    from app.models.schemas import canonical_json_hash

    content_digest = canonical_json_hash(arguments.get("content") or {})
    if review["evidence"].get("content_digest") != content_digest:
        raise ValueError("evidence_id belongs to an earlier draft content digest")
    if review.get("judgment") is not None:
        raise ValueError("this evidence already has a model judgment")
    if review["evidence"]["observation"].get("representative_frame") and not (value.get("observed") or "").strip():
        raise ValueError("record what is visible in the target Scene before giving a verdict")
    if value["verdict"] == "uncertain" and not review["evidence"]["scope"].get("review_target"):
        raise ValueError("obtain a current Scene preview before recording uncertainty")
    if value["verdict"] == "issue":
        value["issue_id"] = "issue_" + value["evidence_id"]
    review["judgment"] = value
    return {
        "content": deepcopy(arguments["content"]),
        "design": deepcopy(arguments.get("design") or {}),
        "review": {**deepcopy(arguments.get("review") or {}), "reviews": reviews},
    }


def working_draft_review_facts(
    arguments: dict[str, Any], *, pending_question: dict[str, Any] | None = None
) -> dict[str, Any]:
    from app.models.schemas import canonical_json_hash

    content = arguments.get("content") or {}
    state = arguments.get("review") or {}
    reviews = state.get("reviews") or []
    unconfirmed = next((review for review in reversed(reviews)
                        if review.get("valid_segments") and (review.get("judgment") or {}).get("verdict") == "uncertain"), None)
    confirmation_blocked = bool(unconfirmed and unconfirmed["evidence"]["observation"].get("confirmation_retry"))
    timeline = state.get("scope") or _timeline_range(content)
    valid = _union([
        segment
        for review in reviews
        if (review.get("judgment") or {}).get("verdict") != "uncertain"
        for segment in review.get("valid_segments") or []
    ])
    missing = _subtract([timeline], valid) if timeline else []
    invalidated = _subtract(
        _union([item["range_seconds"] for item in state.get("invalidated") or []]), valid
    )
    unjudged = [
        review["evidence_id"] for review in reviews
        if review.get("valid_segments") and review.get("judgment") is None
    ]
    resolved = {
        issue_id
        for review in reviews
        if (review.get("judgment") or {}).get("verdict") == "pass"
        for issue_id in (review.get("judgment") or {}).get("resolves_issue_ids") or []
    }
    open_issues = [
        review["judgment"] for review in reviews
        if (review.get("judgment") or {}).get("verdict") == "issue"
        and review["judgment"].get("issue_id") not in resolved
    ]
    scenes = sorted(content.get("scenes") or [], key=lambda item: item.get("range", {}).get("start", 0))
    clips = _clips(content)
    scoped_scene_id = state.get("scene_id")
    current_index = next((
        index for index, scene in enumerate(scenes)
        if (
            scene.get("scene_id") == scoped_scene_id if scoped_scene_id else
            any(_intersects(_range(content, scene["range"]), gap) for gap in missing)
        ) and missing
    ), None)
    current = scenes[current_index] if current_index is not None else None
    next_target = None
    if unconfirmed is not None:
        if not confirmation_blocked and not unjudged:
            next_target = {**unconfirmed["evidence"]["scope"]["review_target"], "confirmation_retry": True}
    elif current is not None and not unjudged:
        current_range = _range(content, current["range"])
        recheck = bool(invalidated)
        if state.get("scope"):
            start = min(gap["start"] for gap in missing)
            recheck = True
        elif recheck:
            start = min(
                gap["start"] for gap in missing
                if _intersects(current_range, gap)
            )
        else:
            start = current_range["start"]
        if not recheck and current_index:
            previous_range = _range(content, scenes[current_index - 1]["range"])
            start = max(previous_range["start"], current_range["start"] - 1.5)
        next_target = {
            "scene_id": current["scene_id"],
            "include_previous_scene": current_index > 0 and (
                not state.get("scope") or start < current_range["start"]
            ),
            "start_seconds": start,
            "end_seconds": current_range["end"],
            "recheck": recheck,
        }
    current_scene_id = current.get("scene_id") if current else None
    editable_scene_id = current_scene_id or scoped_scene_id or (scenes[-1].get("scene_id") if scenes else None)
    track_by_clip = {
        clip.get("clip_id"): track.get("track_id")
        for track in (content.get("timeline") or {}).get("tracks") or []
        for clip in track.get("clips") or []
    }
    editable = [{
        "track_id": track_by_clip.get(clip.get("clip_id")),
        **deepcopy(clip),
        "range_seconds": _range(content, clip["range"]),
    } for clip in clips if clip.get("scene_id") == editable_scene_id]
    return {
        "schema_version": 1,
        "review_started": bool(state.get("started")),
        "content_digest": canonical_json_hash(content),
        "scenes": [{
            "scene_id": scene.get("scene_id"),
            "ordinal": index + 1,
            "range_seconds": _range(content, scene["range"]),
            "intent": scene.get("intent"),
            "visual_description": scene.get("visual_description"),
            "clip_ids": [clip.get("clip_id") for clip in clips if clip.get("scene_id") == scene.get("scene_id")],
        } for index, scene in enumerate(scenes)],
        "reviewed_ranges_seconds": valid,
        "invalidated_ranges_seconds": invalidated,
        "unreviewed_ranges_seconds": missing,
        "current_scene_id": current_scene_id,
        "current_scene_ordinal": current_index + 1 if current_index is not None else None,
        "next_review_target": next_target,
        "editable_targets": editable,
        "evidence": [{
            "evidence_id": review["evidence_id"],
            "content_digest": review["evidence"].get("content_digest"),
            "media_digest": (review["evidence"].get("observation") or {}).get("media_digest"),
            "representative_frame": (review["evidence"].get("observation") or {}).get("representative_frame"),
            "scope": (review["evidence"].get("scope") or {}).get("source_range_seconds"),
            "valid_segments": review.get("valid_segments") or [],
            "judgment": review.get("judgment"),
        } for review in reviews],
        "awaiting_judgment": bool(unjudged),
        "unjudged_evidence_ids": unjudged,
        "confirmation_blocked": confirmation_blocked,
        "unconfirmed_evidence_id": unconfirmed["evidence_id"] if unconfirmed else None,
        "open_issues": open_issues,
        "save_ready": bool(
            state.get("started") and timeline and not missing and not unjudged and not open_issues and not unconfirmed
        ),
        "pending_question": pending_question,
    }


def assert_working_draft_review_ready(arguments: dict[str, Any]) -> None:
    facts = working_draft_review_facts(arguments)
    if not facts["review_started"] or facts["save_ready"]:
        return
    raise ValueError(
        "sequential review is incomplete; obtain current continuous evidence, record judgments "
        "and resolve open issues before saving: "
        + json.dumps({
            "unreviewed": facts["unreviewed_ranges_seconds"],
            "unjudged_evidence_ids": facts["unjudged_evidence_ids"],
            "open_issues": facts["open_issues"],
            "unconfirmed_evidence_id": facts["unconfirmed_evidence_id"],
        }, ensure_ascii=False)
    )


__all__ = [
    "WorkingDraftRejected",
    "WorkingDraftReviewed",
    "WorkingDraftUpdated",
    "apply_working_draft_writes",
    "assert_working_draft_review_ready",
    "candidate_progress_digest",
    "working_draft_review_facts",
    "exception_errors",
    "merge_working_draft",
    "record_working_draft_review",
    "record_working_draft_judgment",
    "review_state_after_edit",
    "tool_progress_digest",
    "verify_working_draft",
    "working_draft_arguments",
    "working_draft_diagnostic",
    "working_draft_observation",
]
