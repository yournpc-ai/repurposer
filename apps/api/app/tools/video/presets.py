"""Registered native-Preset candidates and persisted-member resolution.

The existing assistant.candidates envelope is the only transport. Preset ids
are the sole model input; preview media, titles, durations and digests come
from the validated registry manifest and real object-storage URL seam.
"""
from __future__ import annotations

import base64
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field

from app.editing.presets import PRESET_REGISTRY
from app.editing.styles import CompositionStyle, resolve_style_tokens
from app.models.schemas import VideoPresetChoice, canonical_json_hash
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


MOTION_PREVIEW_CATALOG = {
    "kinetic_beat:impact_cut": {"headline": "Make it move", "highlight_phrase": "move", "scale_emphasis": "oversized"},
    "kinetic_beat:typewriter_swap": {"words": ["Imagine", "Design", "Launch"]},
    "kinetic_beat:slot_flip": {"prefix": "Make it", "words": ["clear", "bold", "move"]},
    "kinetic_beat:inline_badge_split": {"left_text": "Made", "right_text": "visible", "badge_icon": "sparkle"},
    "kinetic_beat:marquee_wall": {"items": [
        {"text": "Create", "icon": "bolt"}, {"text": "Design", "icon": "layers"}, {"text": "Play", "icon": "play"},
    ]},
    "ui_montage:rapid_cut": {"cut_interval_s": 0.35},
    "ui_montage:fan_slide": {},
    "ui_montage:cascade_3d": {},
}


@lru_cache(maxsize=1)
def _preview_font():
    from app.skills.slot_preview import FONTS_DIR

    data = (FONTS_DIR / "MotionPreviewLatin.otf").read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    return {"family": "Motion Preview Latin", "weight": 900, "format": "opentype",
            "font_id": "motion-preview-latin", "font_set_digest": digest, "digest": digest,
            "url": "data:font/otf;base64," + base64.b64encode(data).decode("ascii")}


def build_motion_preview_spec(preview_id: str, *, composition_style: CompositionStyle | None = None) -> dict[str, Any]:
    from app.editing.schemas import CompositionContent, MotionBlockObject, Clip, Track, VersionSettings
    from app.editing.video_spec import compile_video_spec
    from app.skills.slot_preview import render_slot_placeholder_png

    if preview_id not in MOTION_PREVIEW_CATALOG:
        raise VideoPresetError("Unknown motion preview")
    block, mode = preview_id.split(":")
    style = composition_style or CompositionStyle(preset_id="institutional_dark", accent_color="#A1A1AA", backdrop_style="clean")
    tokens = resolve_style_tokens(style)
    settings = VersionSettings(width=1280, height=720, fps={"num": 30}, background=tokens["canvas_bg"], style=composition_style)
    props = dict(MOTION_PREVIEW_CATALOG[preview_id])
    if composition_style is None:
        props.update(theme="dark", accent_color="#A1A1AA", backdrop_style="clean")
    resources, snapshots = [], {}
    if block == "ui_montage":
        props["layout_mode"] = mode
        for i, title in enumerate(("Workspace", "Library", "Timeline"), 1):
            data = render_slot_placeholder_png(f"[{i:02}]", title, "Interface study",
                                               width=480, height=300, tokens=tokens)
            digest = hashlib.sha256(data).hexdigest()
            sid = uuid5(NAMESPACE_URL, digest)
            snapshots[sid] = {"storage_key": "data:image/png;base64," + base64.b64encode(data).decode("ascii"),
                              "digest": digest}
            resources.append({"path": f"media/screen_{i}.png", "content_type": "image/png",
                              "snapshot_id": sid, "snapshot_digest": digest})
    else:
        props["mode"] = mode
    obj = MotionBlockObject(kind="motion_block", object_id="preview", block_id=block,
                            layout={"x": 0, "y": 0, "width": 1280, "height": 720},
                            fit="cover", props=props, resources=resources)
    clip = Clip(clip_id="motion", object=obj, range={"start": 0, "end": round(2.8 * settings.timebase)})
    content = CompositionContent(settings=settings, sources=[
        {"snapshot_id": sid, "snapshot_digest": snap["digest"]} for sid, snap in snapshots.items()
    ], timeline={"tracks": [Track(track_id="main", kind="visual", role="main", order=0, clips=[clip])]})
    digest = canonical_json_hash(content.model_dump(mode="json"))
    spec = compile_video_spec(content, snapshots, composition_id=uuid5(NAMESPACE_URL, preview_id),
                              version_id=uuid5(NAMESPACE_URL, digest), content_digest=digest)
    spec["fonts"] = [dict(_preview_font())]
    return spec


def preset_member(preset_id: str, *, composition_style: CompositionStyle | None = None) -> dict[str, Any]:
    """Complete server-derived candidate facts; no scratch path leaves here."""
    if preset_id in MOTION_PREVIEW_CATALOG:
        spec = build_motion_preview_spec(preset_id, composition_style=composition_style)
        block, mode = preset_id.split(":")
        return {
            "start": 0, "end": 2.8, "excerpt": preset_id, "speaker": None, "provider": "native",
            "preset_id": preset_id, "title": mode.replace("_", " ").title(), "category": block,
            "preview_spec": spec, "preview_digest": canonical_json_hash(spec),
            "duration_seconds": 2.8, "aspect": "16:9", "width": spec["width"], "height": spec["height"],
            "composition_style": composition_style.model_dump(mode="json") if composition_style else None,
        }
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


def show_video_preset_candidates(preset_ids: list[str], *, composition_style: CompositionStyle | None = None) -> dict[str, Any]:
    if not 2 <= len(preset_ids) <= 4 or len(set(preset_ids)) != len(preset_ids):
        raise VideoPresetError("show 2–4 distinct registered native Presets")
    return {
        "kind": "video_preset_set",
        "candidate_set_id": str(uuid4()),
        "topic": "native-video-presets",
        "asset_id": None,
        "members": [preset_member(preset_id, composition_style=composition_style) for preset_id in preset_ids],
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
        style = member.get("composition_style")
        expected = preset_member(member["preset_id"], composition_style=CompositionStyle.model_validate(style) if style else None)
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
                        member if member.get("preset_id") in MOTION_PREVIEW_CATALOG else preset_member(str(member.get("preset_id")))
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
