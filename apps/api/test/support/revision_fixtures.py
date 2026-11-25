"""Editing splits and authoring fixtures."""
from __future__ import annotations

from uuid import UUID

from app.editing.schemas import CompositionContent
from app.models.schemas import ReviseVideoOpsArgs

WEB_ID = UUID("11111111-1111-1111-1111-111111111111")


VIDEO_ID = UUID("33333333-3333-3333-3333-333333333333")


WEB_DIGEST = "a" * 64


VIDEO_DIGEST = "c" * 64


def snapshot_facts(owner_id):
    return {
        WEB_ID: {
            "digest": WEB_DIGEST,
            "kind": "web",
            "owner_id": owner_id,
            "storage_key": "sources/web.json",
            "duration_ticks": None,
            "meta": {
                "views": [
                    {
                        "view_id": "hero",
                        "storage_key": "sources/hero.png",
                        "digest": "b" * 64,
                        "width": 1440,
                        "height": 900,
                        "elements": [
                            {
                                "id": "title",
                                "kind": "heading",
                                "x": 0.5,
                                "y": 0.3,
                                "w": 0.6,
                                "h": 0.15,
                            }
                        ],
                    }
                ]
            },
        },
        VIDEO_ID: {
            "digest": VIDEO_DIGEST,
            "kind": "video",
            "owner_id": owner_id,
            "storage_key": "sources/person.mp4",
            "duration_ticks": 900000,
            "meta": {"media": {"width": 1080, "height": 1920}},
        },
    }


def revision_content():
    def text_clip(scene_id, start, end):
        return {
            "clip_id": f"clp_{scene_id}_name",
            "scene_id": scene_id,
            "range": {"start": start, "end": end},
            "source": None,
            "animations": [],
            "object": {
                "kind": "text",
                "object_id": f"obj_{scene_id}_name",
                "text": "Evidence-led value",
                "layout": {"x": 153.6, "y": 432.0, "width": 1612.8, "height": 166.4},
                "style": {
                    "font_size": 104,
                    "color": "#F8FAFC",
                    "weight": 700,
                    "align": "center",
                    "line_height": 1.2,
                },
            },
        }

    scenes = [
        ("open", 0, 360000),
        ("proof", 360000, 720000),
        ("close", 720000, 990000),
    ]
    return CompositionContent.model_validate({
        "settings": {"width": 1920, "height": 1080, "background": "#0B1020"},
        "sources": [],
        "scenes": [
            {
                "scene_id": scene_id,
                "range": {"start": start, "end": end},
                "intent": f"Scene {scene_id}",
                "speech_clip_ids": [],
            }
            for scene_id, start, end in scenes
        ],
        "timeline": {
            "tracks": [
                {
                    "track_id": "trk_main",
                    "kind": "visual",
                    "role": "main",
                    "order": 0,
                    "clips": [],
                },
                {
                    "track_id": "trk_title",
                    "kind": "visual",
                    "role": "title",
                    "order": 1,
                    "clips": [text_clip(scene_id, start, end) for scene_id, start, end in scenes],
                },
            ],
            "transitions": [],
        },
    })


def revision_args(version, action):
    return ReviseVideoOpsArgs.model_validate(
        {
            "base_ref": {
                "composition_id": str(version.composition_id),
                "composition_version_id": str(version.id),
                "content_digest": version.content_digest,
            },
            "ops": [action],
        }
    )
