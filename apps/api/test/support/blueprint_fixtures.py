"""Chat blueprints and slot promo fixtures."""
from __future__ import annotations

import hashlib
from uuid import UUID, uuid4

from app.editing.revisions import build_audio_gain_animation
from app.editing.schemas import (
    Animation,
    AudioObject,
    Clip,
    ClipSource,
    CompositionContent,
    LayoutBox,
    MotionBlockObject,
    RemotionResource,
    Scene,
    SourceBinding,
    Timeline,
    TimeRange,
    Track,
    Transition,
    VersionSettings,
)
from app.editing.timing import SOURCE_TIMEBASE, seconds_to_ticks


def _dig(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _sample_master_composition() -> tuple[CompositionContent, dict[UUID, dict], dict[str, UUID]]:
    """Build a 4-act master composition with overlay, crossfade, BGM fades, and 2 SFX cues."""
    settings_obj = VersionSettings(width=1920, height=1080, fps={"num": 30, "den": 1}, background="#070B11")
    tb = settings_obj.timebase
    ids = {
        "img": uuid4(),
        "vo1": uuid4(),
        "vo2": uuid4(),
        "bgm": uuid4(),
        "sfx_cut": uuid4(),
        "sfx_end": uuid4(),
    }
    t0 = 0
    t1 = seconds_to_ticks(5.0, tb)
    t2 = seconds_to_ticks(12.0, tb)
    t3 = seconds_to_ticks(19.0, tb)
    t4 = seconds_to_ticks(24.0, tb)

    bgm_anim = Animation.model_validate(
        build_audio_gain_animation(
            object_id="obj_bgm",
            clip_start_ticks=0,
            clip_end_ticks=t4,
            timebase=tb,
            fps_num=30,
            fps_den=1,
            fade_in_seconds=1.2,
            fade_out_seconds=2.0,
        )
    )

    content = CompositionContent(
        settings=settings_obj,
        sources=[SourceBinding(snapshot_id=sid, snapshot_digest=_dig(k)) for k, sid in ids.items()],
        scenes=[
            Scene(scene_id="scene_1", range=TimeRange(start=t0, end=t1)),
            Scene(scene_id="scene_2", range=TimeRange(start=t1, end=t2)),
            Scene(scene_id="scene_3", range=TimeRange(start=t2, end=t3)),
            Scene(scene_id="scene_4", range=TimeRange(start=t3, end=t4)),
        ],
        timeline=Timeline(
            tracks=[
                Track(
                    track_id="trk_main",
                    kind="visual",
                    role="main",
                    order=0,
                    clips=[
                        Clip(
                            clip_id="clp_1",
                            range=TimeRange(start=t0, end=t1),
                            scene_id="scene_1",
                            object=MotionBlockObject(
                                kind="motion_block",
                                object_id="obj_1",
                                block_id="statement_hook",
                                block_version=1,
                                props={
                                    "eyebrow": "SECRET_MASTER_EYEBROW",
                                    "headline": "SECRET_MASTER_HEADLINE",
                                    "highlight_phrase": "SECRET",
                                    "theme": "dark",
                                    "accent_color": "#0F766E",
                                    "show_backdrop": True,
                                },
                                layout=LayoutBox(x=0, y=0, width=1920, height=1080),
                                fit="cover",
                            ),
                        ),
                        Clip(
                            clip_id="clp_2",
                            range=TimeRange(start=t1, end=t2),
                            scene_id="scene_2",
                            object=MotionBlockObject(
                                kind="motion_block",
                                object_id="obj_2",
                                block_id="product_showcase",
                                block_version=1,
                                props={
                                    "url_bar": "secret-master.example",
                                    "badge": "SECRET_BADGE",
                                    "theme": "light",
                                    "chrome_mode": "browser",
                                    "camera_motion": "drift_focus",
                                    "show_backdrop": True,
                                },
                                resources=[
                                    RemotionResource(
                                        path="media/master.png",
                                        snapshot_id=ids["img"],
                                        snapshot_digest=_dig("img"),
                                        content_type="image/png",
                                    )
                                ],
                                layout=LayoutBox(x=0, y=0, width=1920, height=1080),
                                fit="cover",
                            ),
                        ),
                        Clip(
                            clip_id="clp_3",
                            range=TimeRange(start=t2, end=t3),
                            scene_id="scene_3",
                            object=MotionBlockObject(
                                kind="motion_block",
                                object_id="obj_3",
                                block_id="metric_grid",
                                block_version=1,
                                props={
                                    "eyebrow": "SECRET_METRICS",
                                    "title": "SECRET_TITLE",
                                    "items": [
                                        {"value": "99%", "label": "Secret Metric A"},
                                        {"value": "10x", "label": "Secret Metric B"},
                                    ],
                                    "columns": 2,
                                    "theme": "light",
                                    "show_backdrop": True,
                                },
                                layout=LayoutBox(x=0, y=0, width=1920, height=1080),
                                fit="cover",
                            ),
                        ),
                        Clip(
                            clip_id="clp_4",
                            range=TimeRange(start=t3, end=t4),
                            scene_id="scene_4",
                            object=MotionBlockObject(
                                kind="motion_block",
                                object_id="obj_4",
                                block_id="closing_cta",
                                block_version=1,
                                props={
                                    "brand_name": "SECRET_BRAND",
                                    "tagline": "SECRET_TAGLINE",
                                    "cta_label": "SECRET_CTA",
                                    "url_text": "secret.example",
                                    "theme": "dark",
                                    "logo_surface": "light_pill",
                                    "show_backdrop": True,
                                },
                                layout=LayoutBox(x=0, y=0, width=1920, height=1080),
                                fit="cover",
                            ),
                        ),
                    ],
                ),
                Track(
                    track_id="trk_title",
                    kind="visual",
                    role="title",
                    order=1,
                    clips=[
                        Clip(
                            clip_id="clp_ov_2",
                            range=TimeRange(
                                start=seconds_to_ticks(5.6, tb),
                                end=seconds_to_ticks(11.4, tb),
                            ),
                            scene_id="scene_2",
                            object=MotionBlockObject(
                                kind="motion_block",
                                object_id="obj_ov_2",
                                block_id="kinetic_title",
                                block_version=1,
                                props={
                                    "headline": "SECRET_PILL_TEXT",
                                    "surface_style": "pill_caption",
                                    "position": "bottom_left",
                                    "accent_color": "#0F766E",
                                },
                                layout=LayoutBox(x=0, y=0, width=1920, height=1080),
                                fit="cover",
                            ),
                        ),
                    ],
                ),
                Track(
                    track_id="trk_vo",
                    kind="audio",
                    role="dialogue",
                    order=0,
                    clips=[
                        Clip(
                            clip_id="clp_vo_1",
                            range=TimeRange(start=seconds_to_ticks(0.2, tb), end=seconds_to_ticks(4.5, tb)),
                            source=ClipSource(
                                snapshot_id=ids["vo1"],
                                snapshot_digest=_dig("vo1"),
                                source_range=TimeRange(start=0, end=seconds_to_ticks(4.3, SOURCE_TIMEBASE)),
                            ),
                            object=AudioObject(kind="audio", object_id="obj_vo_1", gain_db=0.0),
                        ),
                    ],
                ),
                Track(
                    track_id="trk_bgm",
                    kind="audio",
                    role="music",
                    order=1,
                    clips=[
                        Clip(
                            clip_id="clp_bgm",
                            range=TimeRange(start=0, end=t4),
                            source=ClipSource(
                                snapshot_id=ids["bgm"],
                                snapshot_digest=_dig("bgm"),
                                source_range=TimeRange(start=0, end=seconds_to_ticks(24.0, SOURCE_TIMEBASE)),
                            ),
                            object=AudioObject(kind="audio", object_id="obj_bgm", gain_db=-25.0),
                            animations=[bgm_anim],
                        ),
                    ],
                ),
                Track(
                    track_id="trk_sfx",
                    kind="audio",
                    role="effect",
                    order=2,
                    clips=[
                        Clip(
                            clip_id="clp_sfx_1",
                            range=TimeRange(
                                start=seconds_to_ticks(4.85, tb),
                                end=seconds_to_ticks(5.2, tb),
                            ),
                            source=ClipSource(
                                snapshot_id=ids["sfx_cut"],
                                snapshot_digest=_dig("sfx_cut"),
                                source_range=TimeRange(start=0, end=seconds_to_ticks(0.35, SOURCE_TIMEBASE)),
                            ),
                            object=AudioObject(kind="audio", object_id="obj_sfx_1", gain_db=-13.0),
                        ),
                        Clip(
                            clip_id="clp_sfx_2",
                            range=TimeRange(
                                start=seconds_to_ticks(19.1, tb),
                                end=seconds_to_ticks(20.1, tb),
                            ),
                            source=ClipSource(
                                snapshot_id=ids["sfx_end"],
                                snapshot_digest=_dig("sfx_end"),
                                source_range=TimeRange(start=0, end=seconds_to_ticks(1.0, SOURCE_TIMEBASE)),
                            ),
                            object=AudioObject(kind="audio", object_id="obj_sfx_2", gain_db=-11.5),
                        ),
                    ],
                ),
            ],
            transitions=[
                Transition(
                    transition_id="trn_1_2",
                    from_clip_id="clp_1",
                    to_clip_id="clp_2",
                    kind="crossfade",
                    duration=seconds_to_ticks(0.4, tb),
                    alignment="center",
                ),
            ],
        ),
    )
    origins = {
        ids["sfx_cut"]: {"recipe_id": "swoosh_cut", "params": {"length": 0.35}, "seed": 111},
        ids["sfx_end"]: {"recipe_id": "stinger", "params": {"pitch": 62}, "seed": 222},
    }
    return content, origins, ids
