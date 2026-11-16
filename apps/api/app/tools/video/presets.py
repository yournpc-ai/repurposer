"""Registered native-Preset candidates and persisted-member resolution.

The existing assistant.candidates envelope is the only transport. Preset ids
are the sole model input; preview media, titles, durations and digests come
from the validated registry manifest and real object-storage URL seam.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.editing.presets import PRESET_REGISTRY
from app.models.schemas import VideoPresetChoice
from app.models.tables import Project
from app.providers import storage


class VideoPresetError(ValueError):
    """A requested candidate is not a complete registered native Preset."""


class PresetPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    storage_key: str = Field(min_length=1)
    sha256: str = Field(min_length=64, max_length=64)
    duration_seconds: float = Field(gt=0, allow_inf_nan=False)
    frame_count: int = Field(gt=0)
    fps: float = Field(gt=0, allow_inf_nan=False)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    aspect: str = Field(min_length=3)
    size_bytes: int = Field(gt=0)
    lineage: dict[str, Any]


def _preview_manifest() -> dict[str, PresetPreview]:
    path = Path(__file__).resolve().parents[2] / "editing/preset_previews.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("version") != 1 or not isinstance(raw.get("items"), dict):
        raise VideoPresetError("the native Preset preview manifest is malformed")
    items = {
        preset_id: PresetPreview.model_validate(value)
        for preset_id, value in raw["items"].items()
    }
    if set(items) != set(PRESET_REGISTRY):
        raise VideoPresetError("every registered Preset needs exactly one real preview")
    return items


_PREVIEWS = _preview_manifest()


def preset_member(preset_id: str) -> dict[str, Any]:
    """Complete server-derived candidate facts; no scratch path leaves here."""
    if preset_id not in PRESET_REGISTRY:
        raise VideoPresetError(f"unknown native Preset {preset_id!r}")
    preview = _PREVIEWS.get(preset_id)
    if preview is None:
        raise VideoPresetError(f"Preset {preset_id!r} has no verified dynamic preview")
    url = storage.public_url(preview.storage_key)
    if not url:
        raise VideoPresetError(f"Preset {preset_id!r} has no public preview URL")
    return {
        "start": 0,
        "end": preview.duration_seconds,
        "excerpt": preset_id,
        "speaker": None,
        "provider": "native",
        "preset_id": preset_id,
        "title": preset_id,
        "preview_url": url,
        "preview_digest": preview.sha256,
        "duration_seconds": preview.duration_seconds,
        "aspect": preview.aspect,
        "width": preview.width,
        "height": preview.height,
    }


def show_video_preset_candidates(preset_ids: list[str]) -> dict[str, Any]:
    if not 2 <= len(preset_ids) <= 4 or len(set(preset_ids)) != len(preset_ids):
        raise VideoPresetError("show 2–4 distinct registered native Presets")
    return {
        "kind": "video_preset_set",
        "candidate_set_id": str(uuid4()),
        "topic": "native-video-presets",
        "asset_id": None,
        "members": [preset_member(preset_id) for preset_id in preset_ids],
    }


def resolve_video_preset_member(
    events: list[dict[str, Any]],
    *,
    choice: VideoPresetChoice,
) -> dict[str, Any]:
    """Resolve a complete persisted member and match today's immutable preview."""
    for event in events:
        if (
            event.get("kind") != "video_preset_set"
            or event.get("candidate_set_id") != str(choice.candidate_set_id)
        ):
            continue
        members = event.get("members")
        if not isinstance(members, list) or not 0 <= choice.member_index < len(members):
            raise VideoPresetError("the Preset candidate member does not exist")
        member = members[choice.member_index]
        if not isinstance(member, dict) or not isinstance(member.get("preset_id"), str):
            raise VideoPresetError("the Preset candidate member is malformed")
        expected = preset_member(member["preset_id"])
        if any(member.get(key) != value for key, value in expected.items()):
            raise VideoPresetError("the persisted Preset member no longer matches its registry preview")
        return dict(member)
    raise VideoPresetError(
        "no persisted Preset candidate set matches this id; choose a shown candidate first"
    )


async def resolve_video_preset_choice(
    db,
    *,
    project: Project,
    choice: VideoPresetChoice,
) -> str:
    from app.tools.video.sfx import persisted_candidate_events

    events = await persisted_candidate_events(
        db, project=project, candidate_set_id=choice.candidate_set_id
    )
    return str(resolve_video_preset_member(events, choice=choice)["preset_id"])


def video_preset_candidate_context_lines(
    candidate_logs: list[dict[str, Any]],
) -> list[str]:
    """Expose only ids, ordinals and registry names to a later selection turn."""
    sets: dict[str, dict[str, Any]] = {}
    for log in candidate_logs:
        events = log.get("events") if isinstance(log, dict) else None
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, dict):
                continue
            set_id = event.get("candidate_set_id")
            if not isinstance(set_id, str) or not set_id:
                continue
            if event.get("kind") == "video_preset_set":
                members = event.get("members")
                if not isinstance(members, list) or not 2 <= len(members) <= 4:
                    continue
                try:
                    resolved = [
                        preset_member(str(member.get("preset_id")))
                        for member in members
                        if isinstance(member, dict)
                    ]
                except (VideoPresetError, AttributeError):
                    continue
                if len(resolved) != len(members):
                    continue
                sets[set_id] = {
                    "candidate_set_id": set_id,
                    "members": [
                        {
                            "member_index": index,
                            "ordinal": index + 1,
                            "preset_id": member["preset_id"],
                            "duration_seconds": member["duration_seconds"],
                        }
                        for index, member in enumerate(resolved)
                    ],
                    "selected": [],
                }
            elif event.get("kind") == "selection" and set_id in sets:
                selected = event.get("selected")
                if isinstance(selected, list):
                    sets[set_id]["selected"] = [
                        index for index in selected
                        if isinstance(index, int) and not isinstance(index, bool)
                    ]
    if not sets:
        return []
    return [
        "Persisted native Preset candidate sets (internal references for selection/application):",
        *(json.dumps(item, ensure_ascii=False) for item in sets.values()),
    ]
