"""Fixed video-shotcraft shots → native Composition edits.

These source-pinned Strict adapters are contract-validation fixtures, not a
per-card product import mechanism. Each proves the exact shot card and
implementation digests, then instantiates the declared core with native
Objects/Animations. Editorial furniture, brand marks and external scripts are
outside this scope. The returned ops still have to pass through
``apply_composition_edits``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.editing.animation import derive_text_parts
from app.editing.edits import AddClip, AddScene, AddTrack, Op, SetSettings
from app.editing.schemas import (
    AnimatableProperty,
    Animation,
    Clip,
    Easing,
    Keyframe,
    Scene,
    ShapeObject,
    TextObject,
    TextPartTarget,
    TimeRange,
    Track,
)
from app.skills.external import SkillDraft

VIDEO_SHOTCRAFT_REVISION = "1266a3ec4831289c4d893d42dd5102723658039a"
_SHOT_PATH = "references/shots/typography/blur-slide.md"
_SHOT_DIGEST = "feb73479174b0ff073a6d774c6ed3bd250591439fbd750e1167c2f39b27a05d4"
_IMPLEMENTATION_PATH = "demos/typography/blur-slide/BlurSlide.tsx"
_IMPLEMENTATION_DIGEST = "4e7227b050b4f9fdd0c8762f308aaf2a152f8c476fa3e11efe84b3a23cc43a91"
_DEMOTE_SHOT_PATH = "references/shots/typography/title-demote-to-label.md"
_DEMOTE_SHOT_DIGEST = "4e01c04c76d9f6a3f1b18e9c75ac1502cb1aefe1ac08ef47426b8628ea9fa08f"
_DEMOTE_IMPLEMENTATION_PATH = "demos/typography/title-demote-to-label/TitleDemoteToLabel.tsx"
_DEMOTE_IMPLEMENTATION_DIGEST = "5448cdf76c9eb57ebc4de46ae0f2e9bd399275e9600181afb26fe5dfbf0eeff5"
_TIMEBASE = 90000
_FRAME_TICKS = _TIMEBASE // 30
_DURATION_FRAMES = 120
_DEMOTE_DURATION_FRAMES = 112
_EASE_OUT = Easing(kind="cubic_bezier", params=(0.22, 1.0, 0.36, 1.0))
_DEMOTE_EASE = Easing(kind="cubic_bezier", params=(0.6, 0.0, 0.18, 1.0))


class SkillAdaptationError(ValueError):
    """The pinned evidence or Strict input cannot instantiate this shot."""


class BlurSlidePalette(BaseModel):
    """The shot's three editable colors; timing and typography stay Strict."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    background: str = Field(default="#F7F6F2", pattern=r"^#[0-9a-fA-F]{6}$")
    title: str = Field(default="#17202A", pattern=r"^#[0-9a-fA-F]{6}$")
    subtitle: str = Field(default="#3E4650", pattern=r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True)
class NativeShotInstantiation:
    ops: list[Op]
    skill_provenance: dict[str, Any]


def _ticks(frames: float) -> int:
    return round(frames * _FRAME_TICKS)


def _prove_source(draft: SkillDraft, path: str, digest: str) -> None:
    source = next((item for item in draft.references if item.path == path), None)
    if source is None or source.digest != digest:
        raise SkillAdaptationError(f"blur-slide source evidence does not match: {path}")


def _words(text: str, expected: int, label: str) -> tuple[str, list[str]]:
    words = text.strip().split()
    if len(words) != expected:
        raise SkillAdaptationError(f"{label} needs exactly {expected} words in Strict mode")
    normalized = " ".join(words)
    if len(derive_text_parts(normalized, "word")) != expected:
        raise SkillAdaptationError(
            f"{label} needs words without attached punctuation in Strict mode"
        )
    return normalized, words


def _channels(
    *,
    object_id: str,
    prefix: str,
    part_ids: list[str],
    start: float,
    duration: float,
    stagger: float,
    distance_y: float,
    blur: float,
) -> list[Animation]:
    target = TextPartTarget(kind="word", part_ids=part_ids, stagger=_ticks(stagger))
    start_at, end_at = _ticks(start), _ticks(start + duration)

    def keys(
        initial: float | tuple[float, float], final: float | tuple[float, float]
    ) -> list[Keyframe]:
        return [
            Keyframe(at=start_at, value=initial, easing=_EASE_OUT),
            Keyframe(at=end_at, value=final),
        ]

    return [
        Animation(
            animation_id=f"{prefix}_opacity",
            target_object_id=object_id,
            text_part=target,
            property="opacity",
            keyframes=keys(0.0, 1.0),
        ),
        Animation(
            animation_id=f"{prefix}_position",
            target_object_id=object_id,
            text_part=target,
            property="transform.position",
            keyframes=keys((0.0, distance_y), (0.0, 0.0)),
        ),
        Animation(
            animation_id=f"{prefix}_blur",
            target_object_id=object_id,
            text_part=target,
            property="filter.blur",
            keyframes=keys(blur, 0.0),
        ),
    ]


def _text_clip(
    *,
    clip_id: str,
    object_id: str,
    text: str,
    y: float,
    font_size: int,
    color: str,
    letter_spacing: float,
    animations: list[Animation],
) -> Clip:
    return Clip(
        clip_id=clip_id,
        range=TimeRange(start=0, end=_ticks(_DURATION_FRAMES)),
        scene_id="scn_blur_slide",
        object=TextObject(
            object_id=object_id,
            kind="text",
            text=text,
            layout={
                "x": 162 if font_size > 100 else 168,
                "y": y,
                "width": 1500,
                "height": 180 if font_size > 100 else 70,
            },
            style={
                "font_size": font_size,
                "color": color,
                "weight": 400,
                "line_height": 1.0 if font_size > 100 else 1.2,
                "letter_spacing": letter_spacing,
            },
        ),
        animations=animations,
    )


def instantiate_blur_slide(
    draft: SkillDraft,
    *,
    title_lines: tuple[str, str],
    subtitle: str,
    palette: BlurSlidePalette | None = None,
) -> NativeShotInstantiation:
    """Instantiate the Strict 3+2-word title and 9-word subtitle core."""
    palette = palette or BlurSlidePalette()
    if draft.name != "video-shotcraft" or draft.source_revision != VIDEO_SHOTCRAFT_REVISION:
        raise SkillAdaptationError("blur-slide requires the pinned video-shotcraft revision")
    _prove_source(draft, _SHOT_PATH, _SHOT_DIGEST)
    _prove_source(draft, _IMPLEMENTATION_PATH, _IMPLEMENTATION_DIGEST)
    title_a, _ = _words(title_lines[0], 3, "the first title line")
    title_b, _ = _words(title_lines[1], 2, "the second title line")
    subtitle_text, _ = _words(subtitle, 9, "the subtitle")

    title_a_parts = derive_text_parts(title_a, "word")
    title_b_parts = derive_text_parts(title_b, "word")
    subtitle_parts = derive_text_parts(subtitle_text, "word")
    title_a_ids = [part.part_id for part in title_a_parts]
    title_b_ids = [part.part_id for part in title_b_parts]
    subtitle_ids = [part.part_id for part in subtitle_parts]

    title_a_animations = _channels(
        object_id="obj_blur_title_a",
        prefix="anm_blur_title_a",
        part_ids=title_a_ids,
        start=10,
        duration=22,
        stagger=4,
        distance_y=64,
        blur=18,
    )
    title_b_animations = _channels(
        object_id="obj_blur_title_b",
        prefix="anm_blur_title_b_first",
        part_ids=title_b_ids[:1],
        start=26,
        duration=22,
        stagger=0,
        distance_y=64,
        blur=18,
    ) + _channels(
        object_id="obj_blur_title_b",
        prefix="anm_blur_title_b_accent",
        part_ids=title_b_ids[1:],
        start=30,
        duration=30,
        stagger=0,
        distance_y=64,
        blur=18,
    )
    title_b_animations.append(Animation(
        animation_id="anm_blur_title_b_accent_tracking",
        target_object_id="obj_blur_title_b",
        text_part=TextPartTarget(kind="word", part_ids=title_b_ids[1:], stagger=0),
        property="text.letter_spacing",
        keyframes=[
            Keyframe(at=_ticks(30), value=0.03, easing=_EASE_OUT),
            Keyframe(at=_ticks(60), value=-0.025),
        ],
    ))
    subtitle_animations = _channels(
        object_id="obj_blur_subtitle",
        prefix="anm_blur_subtitle",
        part_ids=subtitle_ids,
        start=34,
        duration=20,
        stagger=2.4,
        distance_y=26,
        blur=9,
    )

    clips = [
        _text_clip(
            clip_id="clp_blur_title_a",
            object_id="obj_blur_title_a",
            text=title_a,
            y=384,
            font_size=170,
            color=palette.title,
            letter_spacing=-0.035,
            animations=title_a_animations,
        ),
        _text_clip(
            clip_id="clp_blur_title_b",
            object_id="obj_blur_title_b",
            text=title_b,
            y=556,
            font_size=170,
            color=palette.title,
            letter_spacing=-0.035,
            animations=title_b_animations,
        ),
        _text_clip(
            clip_id="clp_blur_subtitle",
            object_id="obj_blur_subtitle",
            text=subtitle_text,
            y=800,
            font_size=46,
            color=palette.subtitle,
            letter_spacing=-0.012,
            animations=subtitle_animations,
        ),
    ]
    ops: list[Op] = [
        SetSettings(
            op="set_settings",
            settings={
                "width": 1920,
                "height": 1080,
                "timebase": _TIMEBASE,
                "background": palette.background,
            },
        ),
        AddScene(
            op="add_scene",
            scene=Scene(
                scene_id="scn_blur_slide",
                range=TimeRange(start=0, end=_ticks(_DURATION_FRAMES)),
                intent="Word-by-word blur-slide title reveal",
            ),
        ),
        *[
            AddTrack(
                op="add_track",
                track=Track(
                    track_id=f"trk_blur_layer_{index}",
                    kind="visual",
                    role="title",
                    order=index,
                ),
            )
            for index in range(len(clips))
        ],
        *[
            AddClip(op="add_clip", track_id=f"trk_blur_layer_{index}", clip=clip)
            for index, clip in enumerate(clips)
        ],
    ]
    return NativeShotInstantiation(
        ops=ops,
        skill_provenance={
            "skill": "video-shotcraft",
            "source_revision": VIDEO_SHOTCRAFT_REVISION,
            "source_hash": draft.source_hash,
            "shot": "blur-slide",
            "adapter": "native-text-v1",
            "scope": "word-reveal-core",
            "excluded": [
                "editorial_furniture",
                "brand_marks",
                "background_folio",
                "group_push",
                "accent_paint",
                "punctuation_joined_words",
                "external_scripts",
            ],
        },
    )


def _whole_animation(
    *,
    animation_id: str,
    object_id: str,
    property_name: AnimatableProperty,
    start: float,
    duration: float,
    initial: float | tuple[float, float],
    final: float | tuple[float, float],
    easing: Easing = _EASE_OUT,
) -> Animation:
    return Animation(
        animation_id=animation_id,
        target_object_id=object_id,
        property=property_name,
        keyframes=[
            Keyframe(at=_ticks(start), value=initial, easing=easing),
            Keyframe(at=_ticks(start + duration), value=final),
        ],
    )


def instantiate_title_demote(
    draft: SkillDraft,
    *,
    title: str,
    content_lines: tuple[str, ...],
    palette: BlurSlidePalette | None = None,
) -> NativeShotInstantiation:
    """Adapt the A-variant's continuous title demotion and overlapping content."""
    if draft.name != "video-shotcraft" or draft.source_revision != VIDEO_SHOTCRAFT_REVISION:
        raise SkillAdaptationError("title-demote requires the pinned video-shotcraft revision")
    _prove_source(draft, _DEMOTE_SHOT_PATH, _DEMOTE_SHOT_DIGEST)
    _prove_source(draft, _DEMOTE_IMPLEMENTATION_PATH, _DEMOTE_IMPLEMENTATION_DIGEST)
    title_text, _ = _words(title, 1, "the section title")
    if len(title_text) > 12:
        raise SkillAdaptationError("the section title needs at most 12 characters in Strict mode")
    if len(content_lines) != 3:
        raise SkillAdaptationError("the section needs exactly three content lines in Strict mode")
    lines = tuple(line.strip() for line in content_lines)
    if any(not line or len(line) > 64 or "\n" in line for line in lines):
        raise SkillAdaptationError("each section content line needs 1–64 single-line characters")
    palette = palette or BlurSlidePalette()

    title_id = "obj_demote_title"
    title_parts = derive_text_parts(title_text, "grapheme")
    entrance_target = TextPartTarget(
        kind="grapheme",
        part_ids=[part.part_id for part in title_parts],
        stagger=_ticks(1.6),
    )
    title_animations = [
        Animation(
            animation_id="anm_demote_title_entrance_opacity",
            target_object_id=title_id,
            text_part=entrance_target,
            property="opacity",
            keyframes=[
                Keyframe(at=0, value=0.0, easing=_EASE_OUT),
                Keyframe(at=_ticks(16), value=1.0),
            ],
        ),
        Animation(
            animation_id="anm_demote_title_entrance_position",
            target_object_id=title_id,
            text_part=entrance_target,
            property="transform.position",
            keyframes=[
                Keyframe(at=0, value=(0.0, 36.0), easing=_EASE_OUT),
                Keyframe(at=_ticks(16), value=(0.0, 0.0)),
            ],
        ),
        _whole_animation(
            animation_id="anm_demote_title_scale",
            object_id=title_id,
            property_name="transform.scale",
            start=36,
            duration=26,
            initial=1.0,
            final=0.22,
            easing=_DEMOTE_EASE,
        ),
        _whole_animation(
            animation_id="anm_demote_title_position",
            object_id=title_id,
            property_name="transform.position",
            start=36,
            duration=26,
            initial=(0.0, 0.0),
            final=(-660.0, -344.0),
            easing=_DEMOTE_EASE,
        ),
    ]
    clips = [
        Clip(
            clip_id="clp_demote_title",
            range=TimeRange(start=0, end=_ticks(_DEMOTE_DURATION_FRAMES)),
            scene_id="scn_title_demote",
            object=TextObject(
                object_id=title_id,
                kind="text",
                text=title_text,
                layout={"x": 560, "y": 430, "width": 800, "height": 220},
                style={
                    "font_size": 220,
                    "color": palette.title,
                    "weight": 700,
                    "align": "center",
                    "line_height": 1.0,
                    "letter_spacing": -0.055,
                },
            ),
            animations=title_animations,
        )
    ]
    for index, line in enumerate(lines):
        object_id = f"obj_demote_content_{index}"
        clips.append(Clip(
            clip_id=f"clp_demote_content_{index}",
            range=TimeRange(start=0, end=_ticks(_DEMOTE_DURATION_FRAMES)),
            scene_id="scn_title_demote",
            object=TextObject(
                object_id=object_id,
                kind="text",
                text=line,
                layout={"x": 120, "y": 320 + index * 120, "width": 1500, "height": 70},
                style={
                    "font_size": 48,
                    "color": palette.subtitle,
                    "weight": 400,
                    "line_height": 1.2,
                },
            ),
            animations=[
                _whole_animation(
                    animation_id=f"anm_demote_content_{index}_opacity",
                    object_id=object_id,
                    property_name="opacity",
                    start=48 + index * 6,
                    duration=20,
                    initial=0.0,
                    final=1.0,
                ),
                _whole_animation(
                    animation_id=f"anm_demote_content_{index}_position",
                    object_id=object_id,
                    property_name="transform.position",
                    start=48 + index * 6,
                    duration=20,
                    initial=(0.0, 30.0),
                    final=(0.0, 0.0),
                ),
            ],
        ))
    clips.append(Clip(
        clip_id="clp_demote_divider",
        range=TimeRange(start=0, end=_ticks(_DEMOTE_DURATION_FRAMES)),
        scene_id="scn_title_demote",
        object=ShapeObject(
            object_id="obj_demote_divider",
            kind="shape",
            shape="rect",
            layout={"x": 120, "y": 274, "width": 1560, "height": 2},
            fill=palette.subtitle,
        ),
        animations=[_whole_animation(
            animation_id="anm_demote_divider_opacity",
            object_id="obj_demote_divider",
            property_name="opacity",
            start=56,
            duration=12,
            initial=0.0,
            final=0.65,
        )],
    ))
    return NativeShotInstantiation(
        ops=[
            AddScene(
                op="add_scene",
                scene=Scene(
                    scene_id="scn_title_demote",
                    range=TimeRange(start=0, end=_ticks(_DEMOTE_DURATION_FRAMES)),
                    intent="A title becomes a persistent section label while content enters",
                ),
            ),
            *[
                AddTrack(
                    op="add_track",
                    track=Track(
                        track_id=f"trk_demote_layer_{index}",
                        kind="visual",
                        role="title" if index == 0 else "main",
                        order=index,
                    ),
                )
                for index in range(len(clips))
            ],
            *[
                AddClip(op="add_clip", track_id=f"trk_demote_layer_{index}", clip=clip)
                for index, clip in enumerate(clips)
            ],
        ],
        skill_provenance={
            "skill": "video-shotcraft",
            "source_revision": VIDEO_SHOTCRAFT_REVISION,
            "source_hash": draft.source_hash,
            "shot": "title-demote-to-label",
            "variant": "A",
            "adapter": "native-text-v1",
            "scope": "demote-core",
            "excluded": [
                "left_origin_correction",
                "directional_motion_blur",
                "masked_line_reveal",
                "selection_highlight",
                "editorial_furniture",
                "workbench_cards",
                "external_scripts",
            ],
        },
    )


def _offset_shot_ops(ops: list[Op], *, start: int, track_order: int) -> list[Op]:
    """Place a shot on the shared timeline without changing clip-local motion."""
    shifted: list[Op] = []
    for op in ops:
        if isinstance(op, AddScene):
            shifted.append(op.model_copy(update={"scene": op.scene.model_copy(update={
                "range": TimeRange(
                    start=op.scene.range.start + start,
                    end=op.scene.range.end + start,
                )
            })}))
        elif isinstance(op, AddTrack):
            shifted.append(op.model_copy(update={"track": op.track.model_copy(update={
                "order": op.track.order + track_order,
            })}))
        elif isinstance(op, AddClip):
            shifted.append(op.model_copy(update={"clip": op.clip.model_copy(update={
                "range": TimeRange(
                    start=op.clip.range.start + start,
                    end=op.clip.range.end + start,
                )
            })}))
        else:
            raise SkillAdaptationError("a composed shot may only add scenes, tracks and clips")
    return shifted


def instantiate_blur_demote_sequence(
    draft: SkillDraft,
    *,
    title_lines: tuple[str, str],
    subtitle: str,
    section_title: str,
    section_lines: tuple[str, str, str],
    palette: BlurSlidePalette | None = None,
) -> NativeShotInstantiation:
    """Two source-pinned native shots on one ordinary Composition timeline."""
    opening = instantiate_blur_slide(
        draft,
        title_lines=title_lines,
        subtitle=subtitle,
        palette=palette,
    )
    section = instantiate_title_demote(
        draft,
        title=section_title,
        content_lines=section_lines,
        palette=palette,
    )
    return NativeShotInstantiation(
        ops=[
            *opening.ops,
            *_offset_shot_ops(
                section.ops,
                start=_ticks(_DURATION_FRAMES),
                track_order=3,
            ),
        ],
        skill_provenance={
            "skill": "video-shotcraft",
            "source_revision": VIDEO_SHOTCRAFT_REVISION,
            "source_hash": draft.source_hash,
            "shot": "blur-demote-sequence",
            "adapter": "native-text-v1",
            "scope": "two-source-pinned-shots",
            "shots": [opening.skill_provenance, section.skill_provenance],
        },
    )
