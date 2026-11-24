"""Shared immutable-source and Composition fixtures for API tests."""

from __future__ import annotations

from uuid import UUID, uuid4

from pydantic import TypeAdapter

from app.editing.edits import Op, apply_ops
from app.editing.schemas import CompositionContent, Scene, TimeRange, Timeline, Track, VersionSettings
from app.editing.timing import SOURCE_TIMEBASE
from app.editing.validators import validate_content

ADAPT = TypeAdapter(Op)

IMG_SNAPSHOT = UUID("11111111-1111-1111-1111-111111111111")
IMG_DIGEST = "a" * 64
AUDIO_SNAPSHOT = UUID("22222222-2222-2222-2222-222222222222")
AUDIO_DIGEST = "b" * 64
FOUR_S_TICKS = 4 * SOURCE_TIMEBASE

SNAPSHOT_FACTS = {
    IMG_SNAPSHOT: {
        "digest": IMG_DIGEST,
        "kind": "image",
        "duration_ticks": None,
        "owner_id": uuid4(),
        "storage_key": "snapshots/img.png",
    },
    AUDIO_SNAPSHOT: {
        "digest": AUDIO_DIGEST,
        "kind": "audio",
        "duration_ticks": FOUR_S_TICKS,
        "owner_id": uuid4(),
        "storage_key": "snapshots/audio.wav",
    },
}


def set_intent(intent: str) -> Op:
    return ADAPT.validate_python(
        {"op": "update_scene", "scene_id": "scn_open", "intent": intent}
    )


def creation_ops() -> list[Op]:
    ops = [
        {"op": "set_settings", "settings": {"width": 1920, "height": 1080}},
        {"op": "bind_source", "snapshot_id": str(IMG_SNAPSHOT)},
        {"op": "bind_source", "snapshot_id": str(AUDIO_SNAPSHOT)},
        {
            "op": "add_scene",
            "scene": {
                "scene_id": "scn_open",
                "range": {"start": 0, "end": FOUR_S_TICKS},
                "intent": "opening",
            },
        },
        {
            "op": "add_track",
            "track": {"track_id": "trk_main", "kind": "visual", "role": "main", "order": 0},
        },
        {
            "op": "add_track",
            "track": {"track_id": "trk_title", "kind": "visual", "role": "title", "order": 1},
        },
        {
            "op": "add_track",
            "track": {"track_id": "trk_music", "kind": "audio", "role": "music", "order": 0},
        },
        {
            "op": "add_clip",
            "track_id": "trk_main",
            "clip": {
                "clip_id": "clp_bg",
                "range": {"start": 0, "end": FOUR_S_TICKS},
                "scene_id": "scn_open",
                "source": {"snapshot_id": str(IMG_SNAPSHOT), "snapshot_digest": IMG_DIGEST},
                "object": {
                    "kind": "image",
                    "object_id": "obj_bg",
                    "layout": {"x": 0, "y": 0, "width": 1920, "height": 1080},
                },
            },
        },
        {
            "op": "add_clip",
            "track_id": "trk_title",
            "clip": {
                "clip_id": "clp_title",
                "range": {"start": SOURCE_TIMEBASE, "end": FOUR_S_TICKS},
                "scene_id": "scn_open",
                "object": {
                    "kind": "text",
                    "object_id": "obj_title",
                    "text": "Hello",
                    "layout": {"x": 160, "y": 480, "width": 1600, "height": 120},
                    "style": {"font_size": 96, "color": "#FFFFFF"},
                },
                "animations": [
                    {
                        "animation_id": "anm_fade",
                        "target_object_id": "obj_title",
                        "property": "opacity",
                        "keyframes": [
                            {"at": 0, "value": 0},
                            {"at": 27000, "value": 1},
                        ],
                    }
                ],
            },
        },
        {
            "op": "add_clip",
            "track_id": "trk_music",
            "clip": {
                "clip_id": "clp_bed",
                "range": {"start": 0, "end": FOUR_S_TICKS},
                "source": {
                    "snapshot_id": str(AUDIO_SNAPSHOT),
                    "snapshot_digest": AUDIO_DIGEST,
                    "source_range": {"start": 0, "end": FOUR_S_TICKS},
                },
                "object": {"kind": "audio", "object_id": "obj_bed", "gain_db": -20},
            },
        },
    ]
    return [ADAPT.validate_python(op) for op in ops]


def valid_content() -> CompositionContent:
    content = apply_ops(
        CompositionContent(settings={"width": 1920, "height": 1080}),
        creation_ops(),
        {snapshot_id: facts["digest"] for snapshot_id, facts in SNAPSHOT_FACTS.items()},
    )
    validate_content(content, SNAPSHOT_FACTS)
    return content


def base_content(total_seconds: int = 36, *, with_caption: bool = False) -> CompositionContent:
    tb = SOURCE_TIMEBASE
    tracks = []
    if with_caption:
        tracks = [
            Track(track_id="trk_main", kind="visual", role="main", order=0, clips=[]),
            Track(track_id="trk_caption", kind="visual", role="caption", order=1, clips=[]),
        ]
    return CompositionContent(
        settings=VersionSettings(width=1920, height=1080, timebase=tb),
        sources=[],
        scenes=[Scene(scene_id="scn_1", range=TimeRange(start=0, end=total_seconds * tb))],
        timeline=Timeline(tracks=tracks, transitions=[]),
    )
