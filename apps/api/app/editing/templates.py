"""VideoTemplate loading and instantiation (VIDEO_PROJECT §7).

A template is DECLARATIVE data (``app/skills/<name>/video-template.json``):
the fixed scene arc, tracks, per-scene clip blueprints, timing bands, slot
names and bounded variation (chapter repeat 3–5, the optional plate). All
logic lives here — the JSON carries no assistant copy and no executable
behavior.

Instantiation turns the director's RESOLVED slots (exact on-screen text,
per-scene visual descriptions, camera target choices) plus the bound
snapshots' view facts into one op batch for the content write door. IDs are
minted deterministically from scene keys; TextPart-targeted animations get
their part ids from the same derivation the validator/compiler use.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from app.editing.animation import derive_text_parts
from app.editing.alignment import NarrationPayload
from app.editing.edits import Op, apply_ops
from app.editing.grounding import camera_keyframes
from app.editing.presets import expand_preset
from app.editing.schemas import (
    GENERATOR_FPS,
    CompositionContent,
    NarrationAlignmentRef,
    speech_text_digest,
)
from app.editing.timing import seconds_to_ticks, source_ticks_to_output_ticks

_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

# Easing the presets use (the LLM never writes bezier numbers).
_EASE_OUT = (0.16, 1.0, 0.3, 1.0)
_OP_BATCH = TypeAdapter(list[Op])

# Code-voiced chrome phrases (the divider kicker), by film language.
_CHAPTER_KICKER = {
    "en": "Chapter",
    "zh": "章节",
    "fr": "Chapitre",
    "de": "Kapitel",
    "es": "Capítulo",
    "it": "Capitolo",
}


def chapter_kicker(language: str | None, ordinal: int) -> str:
    word = _CHAPTER_KICKER.get(
        (language or "en").split("-")[0].split("_")[0].lower(), _CHAPTER_KICKER["en"]
    )
    return f"{word} {ordinal}"


class TemplateError(ValueError):
    """The template JSON or a slot/world fact failed instantiation."""


class _SecondsBand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base: float = Field(gt=0)
    min: float = Field(gt=0)
    max: float = Field(gt=0)


class _Layout(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class _Style(BaseModel):
    model_config = ConfigDict(extra="forbid")

    font_size: int = Field(gt=0, le=400)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    weight: Literal[400, 500, 600, 700, 800] = 600
    align: Literal["left", "center", "right"] = "left"
    line_height: float = Field(default=1.2, gt=0)
    background: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class ClipBlueprint(BaseModel):
    """One clip of a scene blueprint. ``slot`` names the text content slot;
    ``view`` names the walk's view role; ``camera``-style motion is the
    ``camera`` preset; ``card_layout`` marks the plate's per-card fan-out."""

    model_config = ConfigDict(extra="forbid")

    track: str
    slot: str | None = None
    view: Literal["home", "chapter", "proof"] | None = None
    window: tuple[float, float] | None = None  # fractions of the scene range
    layout: _Layout | None = None
    style: _Style | None = None
    fit: Literal["cover", "contain"] = "cover"
    card_layout: dict[str, float] | None = None
    big_style: _Style | None = None
    label_style: _Style | None = None
    preset: Literal["line_rise", "fade_in", "fade_in_out", "settle_scale", "camera"] | None = None
    preset_params: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _shape(self) -> "ClipBlueprint":
        if self.slot == "plate.cards":
            if self.card_layout is None or self.big_style is None or self.label_style is None:
                raise TemplateError("plate.cards blueprint needs card_layout + big/label styles")
        elif self.slot is not None and (self.layout is None or self.style is None):
            raise TemplateError(f"text blueprint {self.slot!r} needs layout + style")
        if self.view is not None and self.layout is None:
            raise TemplateError("a web blueprint needs its layout box")
        if self.window is not None and not (0 <= self.window[0] < self.window[1] <= 1):
            raise TemplateError("window must be [start_frac, end_frac] within [0, 1]")
        return self


class SceneBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["scene"] = "scene"
    key: str = Field(min_length=1, max_length=64)
    intent: str = ""
    seconds: _SecondsBand
    # The plate exists only when code detected numbers evidence on this
    # chapter's page (the ONE bounded conditional — not a template language).
    when: Literal["plate_here"] | None = None
    # A walk is dropped (chapter keeps its divider only) when the views run
    # out — the view-poor world's honest degradation, never invented imagery.
    when_view_available: bool = False
    caption: bool = False
    clips: list[ClipBlueprint] = Field(min_length=1)


class RepeatBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["repeat"] = "repeat"
    repeat: Literal["chapters"]
    scenes: list[SceneBlueprint] = Field(min_length=1)


class VideoTemplate(BaseModel):
    """The declarative skeleton (``video-template.json``)."""

    model_config = ConfigDict(extra="forbid")

    template_id: str = Field(min_length=1, max_length=64)
    template_version: int = Field(ge=1)
    settings: dict[str, Any]
    duration: dict[str, float]
    chapters: dict[str, int]
    min_views: int = Field(default=1, ge=1)
    tracks: list[dict[str, Any]] = Field(min_length=1)
    arc: list[SceneBlueprint | RepeatBlock] = Field(min_length=1)
    # The optional music bed's declarative params (gain + fades); the audio
    # track itself is one of ``tracks`` (kind "audio") and lands only when
    # the design resolves a bed.
    music: dict[str, Any] | None = None


_TEMPLATES: dict[str, VideoTemplate] = {}


def load_template(name: str) -> VideoTemplate:
    """Load + validate a skill's template eagerly (bad template = loud
    startup-class failure on first use, never mid-draft ambiguity)."""
    cached = _TEMPLATES.get(name)
    if cached is not None:
        return cached
    path = _SKILLS_DIR / name / "video-template.json"
    if not path.is_file():
        raise TemplateError(f"skill {name!r} carries no video-template.json")
    try:
        template = VideoTemplate.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except Exception as exc:
        raise TemplateError(f"template {name!r} is invalid: {exc}") from exc
    if template.template_id != name:
        raise TemplateError(f"template_id {template.template_id!r} must equal its skill {name!r}")
    _TEMPLATES[name] = template
    return template


@dataclass(frozen=True)
class ViewFact:
    """One usable view of a bound web snapshot (the walk's raw material)."""

    snapshot_id: UUID
    snapshot_digest: str
    view_id: str
    width: int
    height: int
    elements: list[dict[str, Any]]
    heading: str
    page: int  # which bound snapshot (bind order)
    state_id: str | None = None
    artifact_role: str | None = None
    paired_view_id: str | None = None
    target_id: str | None = None
    target_element_id: str | None = None
    route: str | None = None
    actions: list[dict[str, Any]] = field(default_factory=list)
    source_y: int = 0
    css_width: int | None = None
    css_height: int | None = None
    device_scale_factor: float = 1.0
    region_text: str | None = None
    region_text_truncated: bool | None = None
    region_visually_truncated: bool | None = None
    source_url: str | None = None


@dataclass(frozen=True)
class MediaFact:
    """One frozen real image or video used by a product-promo evidence scene."""

    snapshot_id: UUID
    snapshot_digest: str
    kind: Literal["image", "video"]
    duration_ticks: int | None
    width: int
    height: int
    title: str = ""


@dataclass(frozen=True)
class DesignSlots:
    """The director's resolved answer, ready for instantiation. Every text
    slot is EXACT copy (citations already resolved and cap-fitted)."""

    name: str | None
    language: str | None
    cold_open: list[str]
    hero_word: str
    hero_sub: str
    chapter_titles: list[str]
    reveal_lead: str
    reveal_word: str
    reveal_sub: str
    end_name: str
    end_tagline: str
    captions: dict[str, str]  # scene key → exact subtitle copy
    visual_descriptions: dict[str, str]  # scene key → LLM summary (may be absent)
    camera_focuses: dict[str, dict[str, float] | None]  # scene key → resolved focus
    plate_cards: list[dict[str, Any]]  # code-detected; [] = no plate
    plate_page: int | None


@dataclass(frozen=True)
class MusicBed:
    """The resolved music bed: one pinned audio snapshot the film tiles
    across its whole length (a global clip, ``scene_id=None``)."""

    snapshot_id: UUID
    snapshot_digest: str
    duration_ticks: int  # source-time ticks; SOURCE_TIMEBASE == content timebase


@dataclass(frozen=True)
class FixedSoundCue:
    """One existing fixed SFX source, compensated to a native visual action."""

    snapshot_id: UUID
    snapshot_digest: str
    duration_ticks: int
    source_peak_ticks: int
    output_offset_ticks: int
    scene_index: int
    action_offset_ticks: int
    gain_db: float = -6.0


@dataclass(frozen=True)
class _PlannedScene:
    key: str  # instance key (chapter scenes carry their ordinal suffix)
    blueprint: SceneBlueprint
    chapter: int | None  # 1-based for chapter scenes
    view: ViewFact | None


def _ease(kind: str) -> dict[str, Any]:
    if kind == "linear":
        return {"kind": "linear", "params": None}
    if kind == "hold":
        return {"kind": "hold", "params": None}
    return {"kind": "cubic_bezier", "params": list(_EASE_OUT)}


def _kf(at: int, value: Any, easing: str = "linear") -> dict[str, Any]:
    return {"at": at, "value": value, "easing": _ease(easing)}


def _preset_animations(
    bp: ClipBlueprint,
    *,
    object_id: str,
    text: str | None,
    clip_ticks: int,
    timebase: int,
    animation_prefix: str,
) -> list[dict[str, Any]]:
    """Expand one blueprint's named preset into concrete animations. TextPart
    targets are derived from the clip's OWN text (content-addressed ids)."""
    if bp.preset is None:
        return []
    p = bp.preset_params
    anims: list[dict[str, Any]] = []
    if bp.preset == "fade_in":
        delay = seconds_to_ticks(p.get("delay_s", 0.0), timebase)
        dur = max(seconds_to_ticks(p.get("dur_s", 0.5), timebase), 1)
        anims.append(
            {
                "animation_id": f"{animation_prefix}_opacity",
                "target_object_id": object_id,
                "text_part": None,
                "property": "opacity",
                "keyframes": [_kf(delay, 0.0), _kf(min(delay + dur, clip_ticks), 1.0)],
            }
        )
    elif bp.preset == "fade_in_out":
        in_s = max(seconds_to_ticks(p.get("in_s", 0.4), timebase), 1)
        out_s = max(seconds_to_ticks(p.get("out_s", 0.4), timebase), 1)
        anims.append(
            {
                "animation_id": f"{animation_prefix}_opacity",
                "target_object_id": object_id,
                "text_part": None,
                "property": "opacity",
                "keyframes": [
                    _kf(0, 0.0),
                    _kf(in_s, 1.0),
                    _kf(max(clip_ticks - out_s, in_s), 1.0, "hold"),
                    _kf(clip_ticks, 0.0),
                ],
            }
        )
    elif bp.preset == "settle_scale":
        dur = max(seconds_to_ticks(p.get("dur_s", 0.8), timebase), 1)
        anims.append(
            {
                "animation_id": f"{animation_prefix}_scale",
                "target_object_id": object_id,
                "text_part": None,
                "property": "transform.scale",
                "keyframes": [_kf(0, float(p.get("from", 1.1))), _kf(min(dur, clip_ticks), 1.0, "ease")],
            }
        )
        anims.append(
            {
                "animation_id": f"{animation_prefix}_opacity",
                "target_object_id": object_id,
                "text_part": None,
                "property": "opacity",
                "keyframes": [_kf(0, 0.0), _kf(min(dur // 2, clip_ticks) or 1, 1.0)],
            }
        )
    elif bp.preset == "line_rise":
        assert text is not None
        parts = derive_text_parts(text, "line")
        stagger = seconds_to_ticks(p.get("stagger_s", 0.45), timebase)
        dur = max(seconds_to_ticks(p.get("dur_s", 0.9), timebase), 1)
        dy = float(p.get("dy", 48))
        part_ids = [part.part_id for part in parts]
        target = {"kind": "line", "part_ids": part_ids, "stagger": stagger}
        anims.append(
            {
                "animation_id": f"{animation_prefix}_line_opacity",
                "target_object_id": object_id,
                "text_part": target,
                "property": "opacity",
                "keyframes": [_kf(0, 0.0), _kf(min(dur // 2, clip_ticks) or 1, 1.0)],
            }
        )
        anims.append(
            {
                "animation_id": f"{animation_prefix}_line_position",
                "target_object_id": object_id,
                "text_part": target,
                "property": "transform.position",
                "keyframes": [_kf(0, [0.0, dy]), _kf(min(dur, clip_ticks), [0.0, 0.0], "ease")],
            }
        )
    elif bp.preset == "camera":
        raise TemplateError("the camera preset expands through the view-aware seat")
    return anims


def _camera_animations(
    bp: ClipBlueprint,
    *,
    object_id: str,
    view: ViewFact,
    focus: dict[str, float] | None,
    clip_ticks: int,
    canvas: tuple[int, int],
    animation_prefix: str,
) -> list[dict[str, Any]]:
    """The walk's camera: computed from the resolved focus element (or the
    honest center push-in fallback), never from model-authored numbers."""
    p = bp.preset_params
    start_scale = float(p.get("start_scale", 1.08))
    zoom, position_kfs = camera_keyframes(
        focus,
        view_width=view.width,
        view_height=view.height,
        canvas_width=canvas[0],
        canvas_height=canvas[1],
        clip_ticks=clip_ticks,
        arrival_frac=float(p.get("arrival_frac", 0.45)),
        start_scale=start_scale,
    )
    arrival_at = position_kfs[1][0]
    return [
        {
            "animation_id": f"{animation_prefix}_scale",
            "target_object_id": object_id,
            "text_part": None,
            "property": "transform.scale",
            "keyframes": [
                _kf(0, start_scale),
                _kf(arrival_at, zoom, "ease"),
                _kf(clip_ticks, round(min(zoom * 1.01, 2.05), 3)),
            ],
        },
        {
            "animation_id": f"{animation_prefix}_position",
            "target_object_id": object_id,
            "text_part": None,
            "property": "transform.position",
            "keyframes": [
                _kf(at, [float(v[0]), float(v[1])], "ease" if i == 1 else "linear")
                for i, (at, v) in enumerate(position_kfs)
            ],
        },
    ]


def _plan_scenes(
    template: VideoTemplate, slots: DesignSlots, views: list[ViewFact]
) -> list[_PlannedScene]:
    """The fixed arc → the concrete scene list: chapter repeat expansion,
    view assignment (home first, one walk per chapter while views last, the
    proof walk on the last unused view), the plate after the chapter whose
    page proved the numbers."""
    planned: list[_PlannedScene] = []
    used_views: set[int] = set()

    def assign_view(role: str, chapter: int | None) -> ViewFact | None:
        if role == "home":
            used_views.add(0)
            return views[0]
        if role == "chapter" and chapter is not None:
            if chapter < len(views):
                used_views.add(chapter)
                return views[chapter]
            return None
        if role == "proof":
            for idx in range(len(views) - 1, -1, -1):
                if idx not in used_views:
                    used_views.add(idx)
                    return views[idx]
            return views[-1]
        return None

    n_chapters = len(slots.chapter_titles)
    plate_chapter: int | None = None
    if slots.plate_cards and slots.plate_page is not None:
        # The plate hangs off the chapter whose walk shows the numbers' page.
        plate_chapter = next(
            (
                i
                for i in range(1, n_chapters + 1)
                if i < len(views) and views[i].page == slots.plate_page
            ),
            1,
        )

    for entry in template.arc:
        if isinstance(entry, RepeatBlock):
            for chapter in range(1, n_chapters + 1):
                for bp in entry.scenes:
                    if bp.when == "plate_here" and chapter != plate_chapter:
                        continue
                    view = assign_view(bp.clips[0].view, chapter) if bp.clips[0].view else None
                    if bp.when_view_available and view is None:
                        continue
                    planned.append(
                        _PlannedScene(
                            key=f"chapter_{chapter}_{bp.key}",
                            blueprint=bp,
                            chapter=chapter,
                            view=view,
                        )
                    )
        else:
            bp = entry
            view = assign_view(bp.clips[0].view, None) if bp.clips[0].view else None
            planned.append(_PlannedScene(key=bp.key, blueprint=bp, chapter=None, view=view))
    return planned


def _assign_seconds(planned: list[_PlannedScene], template: VideoTemplate) -> list[float]:
    """Base weights scaled to the target total, clamped into each scene's
    band (the craft law's 70–118s)."""
    bases = [p.blueprint.seconds.base for p in planned]
    total_base = sum(bases)
    target = float(template.duration["target_seconds"])
    factor = target / total_base if total_base else 1.0
    out: list[float] = []
    for p, base in zip(planned, bases):
        band = p.blueprint.seconds
        out.append(min(max(base * factor, band.min), band.max))
    return out


def _slot_text(bp: ClipBlueprint, slots: DesignSlots, planned: _PlannedScene) -> str:
    """Resolve a clip blueprint's text slot to its exact copy."""
    chapter = planned.chapter
    if bp.slot == "cold_open":
        return "\n".join(slots.cold_open)
    if bp.slot == "hero.word":
        return slots.hero_word
    if bp.slot == "hero.sub":
        return slots.hero_sub
    if bp.slot == "divider.kicker":
        assert chapter is not None
        return chapter_kicker(slots.language, chapter)
    if bp.slot == "divider.title":
        assert chapter is not None
        return slots.chapter_titles[chapter - 1]
    if bp.slot == "reveal.lead":
        return slots.reveal_lead
    if bp.slot == "reveal.word":
        return slots.reveal_word
    if bp.slot == "reveal.sub":
        return slots.reveal_sub
    if bp.slot == "end.name":
        return slots.end_name
    if bp.slot == "end.tagline":
        return slots.end_tagline
    raise TemplateError(f"unknown text slot {bp.slot!r}")


def _text_object(
    bp: ClipBlueprint, *, object_id: str, text: str, style: _Style | None = None
) -> dict[str, Any]:
    s = style or bp.style
    assert s is not None and bp.layout is not None
    layout = bp.layout if isinstance(bp.layout, _Layout) else _Layout.model_validate(bp.layout)
    style_dump = {
        "font_size": s.font_size,
        "color": s.color,
        "background": s.background,
        "weight": s.weight,
        "align": s.align,
        "line_height": s.line_height,
    }
    return {
        "kind": "text",
        "object_id": object_id,
        "text": text,
        "layout": layout.model_dump(mode="json"),
        "style": style_dump,
        "transform": {"x": 0.0, "y": 0.0, "scale": 1.0, "rotation": 0.0, "origin": "center"},
        "opacity": 1.0,
    }


def _music_bed_ops_for_track(
    track: dict[str, Any],
    cfg: dict[str, Any],
    bed: MusicBed,
    *,
    total_ticks: int,
    timebase: int,
) -> list[dict[str, Any]]:
    """Tile one pinned bed on a caller-owned audio track (global clips)."""
    if bed.duration_ticks <= 0 or total_ticks <= 0:
        return []
    gain_db = float(cfg.get("gain_db", -20.0))
    fade_in = seconds_to_ticks(float(cfg.get("fade_in_s", 1.0)), timebase)
    fade_out = seconds_to_ticks(float(cfg.get("fade_out_s", 2.0)), timebase)

    ops: list[dict[str, Any]] = [
        {"op": "add_track", "track": {**track, "clips": []}},
        {"op": "bind_source", "snapshot_id": str(bed.snapshot_id)},
    ]
    pos = 0
    index = 0
    while pos < total_ticks:
        length = min(bed.duration_ticks, total_ticks - pos)
        first = pos == 0
        last = pos + length >= total_ticks
        keyframes: list[dict[str, Any]] = []
        if first:
            keyframes.append(_kf(0, 0.0))
            keyframes.append(_kf(min(fade_in, length), 1.0, "ease"))
        else:
            keyframes.append(_kf(0, 1.0))
        if last:
            # The fade-out ramp holds until ``length - fade_out`` when that
            # still leaves the previous keyframe behind it; a shorter tail
            # clip simply ramps down from wherever the envelope already is.
            hold = length - fade_out
            if hold > keyframes[-1]["at"]:
                keyframes.append(_kf(hold, 1.0))
            if length > keyframes[-1]["at"]:
                keyframes.append(_kf(length, 0.0))
        object_id = f"obj_music_{index}"
        ops.append(
            {
                "op": "add_clip",
                "track_id": track["track_id"],
                "clip": {
                    "clip_id": f"clp_music_{index}",
                    "range": {"start": pos, "end": pos + length},
                    "scene_id": None,
                    "source": {
                        "snapshot_id": str(bed.snapshot_id),
                        "snapshot_digest": bed.snapshot_digest,
                        "source_range": {"start": 0, "end": length},
                    },
                    "object": {
                        "kind": "audio",
                        "object_id": object_id,
                        "gain_db": gain_db,
                    },
                    "animations": [
                        {
                            "animation_id": f"anm_music_{index}_gain",
                            "target_object_id": object_id,
                            "text_part": None,
                            "property": "audio.gain",
                            "keyframes": keyframes,
                        }
                    ],
                },
            }
        )
        pos += length
        index += 1
    return ops


def _music_bed_ops(
    template: VideoTemplate,
    bed: MusicBed,
    *,
    total_ticks: int,
    timebase: int,
) -> list[dict[str, Any]]:
    track = next((t for t in template.tracks if t.get("kind") == "audio"), None)
    if track is None:
        return []
    return _music_bed_ops_for_track(
        track, template.music or {}, bed, total_ticks=total_ticks, timebase=timebase
    )


def instantiate_music_bed(
    bed: MusicBed, *, total_ticks: int, timebase: int
) -> list[dict[str, Any]]:
    """The template-independent music bed for free/mixed compositions."""
    track = {"track_id": "trk_music", "kind": "audio", "role": "music", "order": 0, "clips": []}
    return _music_bed_ops_for_track(
        track,
        {"gain_db": -20.0, "fade_in_s": 1.0, "fade_out_s": 2.0},
        bed,
        total_ticks=total_ticks,
        timebase=timebase,
    )


def instantiate_fixed_sound_cue(
    cue: FixedSoundCue,
    *,
    scene_id: str,
    scene_start: int,
    clip_suffix: str = "keyword",
) -> list[dict[str, Any]]:
    """Place the measured source peak on a scene-local visual action."""
    start = scene_start + cue.action_offset_ticks - cue.source_peak_ticks - cue.output_offset_ticks
    if start < scene_start:
        raise TemplateError("fixed SFX peak compensation precedes its scene")
    return [
        {"op": "bind_source", "snapshot_id": str(cue.snapshot_id)},
        {
            "op": "add_track",
            "track": {
                "track_id": "trk_sfx", "kind": "audio", "role": "effect", "order": 1, "clips": [],
            },
        },
        {
            "op": "add_clip",
            "track_id": "trk_sfx",
            "clip": {
                "clip_id": f"clp_sfx_{clip_suffix}",
                "range": {"start": start, "end": start + cue.duration_ticks},
                "scene_id": scene_id,
                "source": {
                    "snapshot_id": str(cue.snapshot_id),
                    "snapshot_digest": cue.snapshot_digest,
                    "source_range": {"start": 0, "end": cue.duration_ticks},
                },
                "object": {"kind": "audio", "object_id": f"obj_sfx_{clip_suffix}", "gain_db": cue.gain_db},
                "animations": [],
            },
        },
    ]


def _insert_product_media_ops(
    ops: list[dict[str, Any]],
    media: list[MediaFact],
    slots: DesignSlots,
    *,
    canvas: tuple[int, int],
    timebase: int,
    frame_ticks: int,
) -> int:
    """Add real image/video evidence scenes before the closing card.

    These are ordinary native Clips on the existing timeline. The video keeps
    an exact 1× source window; its old demo-film audio is muted so the new
    work's music and SFX remain the only soundtrack.
    """
    image = next((item for item in media if item.kind == "image"), None)
    video = next((item for item in media if item.kind == "video"), None)
    if image is None and video is None:
        return 0
    end_scene = next(
        (op for op in ops if op["op"] == "add_scene" and op["scene"]["scene_id"] == "scn_end"),
        None,
    )
    if end_scene is None:
        raise TemplateError("product media scenes need the launch film's end scene")
    insert_at = int(end_scene["scene"]["range"]["start"])
    image_ticks = 6 * timebase
    video_ticks = 8 * timebase
    if video is not None:
        if video.duration_ticks is None or video.duration_ticks <= frame_ticks:
            raise TemplateError("the product video has no usable probed duration")
        assert video.duration_ticks is not None
        video_ticks = min(video_ticks, (video.duration_ticks // frame_ticks) * frame_ticks)
        if video_ticks <= 0:
            raise TemplateError("the product video is shorter than one output frame")
    added = (image_ticks if image is not None else 0) + (video_ticks if video is not None else 0)
    for op in ops:
        if op["op"] == "add_scene" and op["scene"]["scene_id"] == "scn_end":
            op["scene"]["range"]["start"] += added
            op["scene"]["range"]["end"] += added
        elif op["op"] == "add_clip" and op["clip"].get("scene_id") == "scn_end":
            op["clip"]["range"]["start"] += added
            op["clip"]["range"]["end"] += added
    end_clip_ops = [
        op for op in ops if op["op"] == "add_clip" and op["clip"].get("scene_id") == "scn_end"
    ]
    ops.remove(end_scene)
    for op in end_clip_ops:
        ops.remove(op)
    ops.append({"op": "add_track", "track": {
        "track_id": "trk_product_media", "kind": "visual", "role": "main", "order": 50, "clips": [],
    }})
    cursor = insert_at

    def add_scene(key: str, duration: int, intent: str, visual: str) -> tuple[str, int, int]:
        nonlocal cursor
        scene_id = f"scn_product_{key}"
        start, end = cursor, cursor + duration
        ops.append({"op": "add_scene", "scene": {
            "scene_id": scene_id, "range": {"start": start, "end": end},
            "intent": intent, "visual_description": visual, "speech_clip_ids": [],
        }})
        cursor = end
        return scene_id, start, end

    def add_text(scene_id: str, start: int, end: int, key: str, text: str,
                 layout: dict[str, float], font_size: int, color: str) -> None:
        bp = ClipBlueprint(
            track="trk_title", slot="caption", layout=layout,
            style=_Style(font_size=font_size, color=color, weight=700, align="center"),
        )
        object_id = f"obj_product_{key}"
        ops.append({"op": "add_clip", "track_id": "trk_title", "clip": {
            "clip_id": f"clp_product_{key}", "range": {"start": start, "end": end},
            "scene_id": scene_id, "source": None,
            "object": _text_object(bp, object_id=object_id, text=text),
            "animations": [{
                "animation_id": f"anm_product_{key}_opacity", "target_object_id": object_id,
                "text_part": None, "property": "opacity",
                "keyframes": [_kf(0, 0.0), _kf(min(timebase // 2, end - start), 1.0, "ease")],
            }],
        }})

    if image is not None:
        scene_id, start, end = add_scene(
            "image", image_ticks, "Establish the product's real brand artwork",
            f"The bound real brand image {image.title} is held with a slow native entrance.",
        )
        ops.append({"op": "bind_source", "snapshot_id": str(image.snapshot_id)})
        object_id = "obj_product_image"
        ops.append({"op": "add_clip", "track_id": "trk_product_media", "clip": {
            "clip_id": "clp_product_image", "range": {"start": start, "end": end},
            "scene_id": scene_id,
            "source": {"snapshot_id": str(image.snapshot_id), "snapshot_digest": image.snapshot_digest, "source_range": None},
            "object": {
                "kind": "image", "object_id": object_id,
                "layout": {"x": 300.0, "y": 180.0, "width": 1320.0, "height": 693.0}, "fit": "contain",
                "transform": {"x": 0.0, "y": 0.0, "scale": 1.0, "rotation": 0.0, "origin": "center"}, "opacity": 1.0,
            },
            "animations": [
                {"animation_id": "anm_product_image_opacity", "target_object_id": object_id, "text_part": None,
                 "property": "opacity", "keyframes": [_kf(0, 0.0), _kf(timebase // 2, 1.0, "ease")]},
                {"animation_id": "anm_product_image_scale", "target_object_id": object_id, "text_part": None,
                 "property": "transform.scale", "keyframes": [_kf(0, 0.98), _kf(timebase * 4 // 5, 1.0, "ease")]},
            ],
        }})
        add_text(scene_id, start, end, "image_title", slots.end_name,
                 {"x": 260.0, "y": 60.0, "width": 1400.0, "height": 90.0}, 56, "#F8FAFC")

    if video is not None:
        scene_id, start, end = add_scene(
            "video", video_ticks, "Show the disclosed product film excerpt in motion",
            f"The existing real video {video.title} plays an exact middle source window with its old audio muted.",
        )
        source_start = min(
            (video.duration_ticks // 4 // frame_ticks) * frame_ticks,
            video.duration_ticks - video_ticks,
        )
        ops.append({"op": "bind_source", "snapshot_id": str(video.snapshot_id)})
        object_id = "obj_product_video"
        ops.append({"op": "add_clip", "track_id": "trk_product_media", "clip": {
            "clip_id": "clp_product_video", "range": {"start": start, "end": end},
            "scene_id": scene_id,
            "source": {
                "snapshot_id": str(video.snapshot_id), "snapshot_digest": video.snapshot_digest,
                "source_range": {"start": source_start, "end": source_start + video_ticks},
            },
            "object": {
                "kind": "video", "object_id": object_id,
                "layout": {"x": 320.0, "y": 180.0, "width": 1280.0, "height": 720.0}, "fit": "contain",
                "transform": {"x": 0.0, "y": 0.0, "scale": 1.0, "rotation": 0.0, "origin": "center"},
                "opacity": 1.0, "gain_db": 0.0, "muted": True,
            },
            "animations": [
                {"animation_id": "anm_product_video_opacity", "target_object_id": object_id, "text_part": None,
                 "property": "opacity", "keyframes": [_kf(0, 0.0), _kf(timebase * 2 // 5, 1.0, "ease")]},
                {"animation_id": "anm_product_video_scale", "target_object_id": object_id, "text_part": None,
                 "property": "transform.scale", "keyframes": [_kf(0, 0.98), _kf(timebase * 3 // 5, 1.0, "ease")]},
            ],
        }})
        add_text(scene_id, start, end, "video_title", slots.reveal_lead,
                 {"x": 260.0, "y": 60.0, "width": 1400.0, "height": 90.0}, 56, "#F8FAFC")

    ops.append(end_scene)
    ops.extend(end_clip_ops)
    return added


def instantiate_template(
    template: VideoTemplate,
    slots: DesignSlots,
    views: list[ViewFact],
    *,
    music_bed: MusicBed | None = None,
    capture_views: list[ViewFact] | None = None,
    media: list[MediaFact] | None = None,
    fixed_sfx: FixedSoundCue | None = None,
) -> list[dict[str, Any]]:
    """Expand the template + resolved slots into the create-path op batch
    (plain op dicts — the caller validates them into the Op union before
    the write door sees them)."""
    if len(views) < template.min_views:
        raise TemplateError(
            f"the arc needs at least {template.min_views} usable page views, "
            f"got {len(views)} — capture more of the page first"
        )
    canvas = (int(template.settings["width"]), int(template.settings["height"]))
    timebase = 90000  # DEFAULT_TIMEBASE — the content timebase new versions carry
    fps = template.settings.get("fps") or {"num": 30, "den": 1}

    planned = _plan_scenes(template, slots, views)
    seconds = _assign_seconds(planned, template)
    # Quantize each scene to whole frames (the render grid), min 1 frame.
    frame_ticks = seconds_to_ticks(1 / (fps["num"] / fps["den"]), timebase)
    durations = [
        max(round(seconds_to_ticks(s, timebase) / frame_ticks), 1) * frame_ticks
        for s in seconds
    ]

    ops: list[dict[str, Any]] = [
        {
            "op": "set_settings",
            "settings": {
                "width": canvas[0],
                "height": canvas[1],
                "fps": {"num": fps["num"], "den": fps["den"]},
                "timebase": timebase,
                "sample_rate": 48000,
                "channels": 2,
                "background": template.settings["background"],
            },
        }
    ]
    bound: set[UUID] = set()
    # Concurrent title elements occupy distinct tracks. Keep those lanes
    # adjacent in the declared stacking order, below later base tracks.
    # Audio (the music bed) lands after the scene walk, only when the
    # design resolved a bed — a silent film carries no empty audio track.
    lane_groups: dict[str, list[dict[str, Any]]] = {}
    for track in template.tracks:
        if track["kind"] == "audio":
            continue
        lane = {**track, "clips": []}
        ops.append({"op": "add_track", "track": lane})
        lane_groups[track["track_id"]] = [lane]
    occupied: dict[str, list[tuple[int, int]]] = {}
    cursor = 0
    for planned_scene, duration in zip(planned, durations):
        bp = planned_scene.blueprint
        scene_range = {"start": cursor, "end": cursor + duration}
        scene_id = f"scn_{planned_scene.key}"
        ops.append(
            {
                "op": "add_scene",
                "scene": {
                    "scene_id": scene_id,
                    "range": scene_range,
                    "intent": bp.intent,
                    "visual_description": slots.visual_descriptions.get(planned_scene.key),
                    "speech_clip_ids": [],
                },
            }
        )
        clip_index = 0

        def emit_clip(object_dict: dict[str, Any], animations: list[dict[str, Any]], *,
                       source: dict[str, Any] | None, window: tuple[float, float] | None,
                       track: str, suffix: str) -> None:
            nonlocal clip_index
            start = scene_range["start"]
            end = scene_range["end"]
            if window is not None:
                start = scene_range["start"] + int(duration * window[0])
                end = scene_range["start"] + int(duration * window[1])
                if end <= start:
                    end = start + frame_ticks
            lanes = lane_groups[track]
            lane = next((t for t in lanes if all(
                old_end <= start or old_start >= end
                for old_start, old_end in occupied.get(t["track_id"], [])
            )), None)
            if lane is None:
                lane = {**lanes[0], "track_id": f"{track}_layer{len(lanes)}", "clips": []}
                lanes.append(lane)
                ops.append({"op": "add_track", "track": lane})
            occupied.setdefault(lane["track_id"], []).append((start, end))
            ops.append(
                {
                    "op": "add_clip",
                    "track_id": lane["track_id"],
                    "clip": {
                        "clip_id": f"clp_{planned_scene.key}_{suffix}",
                        "range": {"start": start, "end": end},
                        "scene_id": scene_id,
                        "source": source,
                        "object": object_dict,
                        "animations": animations,
                    },
                }
            )
            clip_index += 1

        for clip_bp in bp.clips:
            if clip_bp.view is not None:
                view = planned_scene.view
                if view is None:
                    raise TemplateError(f"scene {planned_scene.key} has no assigned view")
                if view.snapshot_id not in bound:
                    ops.append({"op": "bind_source", "snapshot_id": str(view.snapshot_id)})
                    bound.add(view.snapshot_id)
                object_id = f"obj_{planned_scene.key}_web"
                object_dict = {
                    "kind": "web",
                    "object_id": object_id,
                    "view_id": view.view_id,
                    "layout": clip_bp.layout.model_dump(mode="json") if clip_bp.layout else None,
                    "fit": clip_bp.fit,
                    "transform": {"x": 0.0, "y": 0.0, "scale": 1.0, "rotation": 0.0, "origin": "center"},
                    "opacity": 1.0,
                }
                animations: list[dict[str, Any]] = []
                if clip_bp.preset == "camera":
                    animations = _camera_animations(
                        clip_bp,
                        object_id=object_id,
                        view=view,
                        focus=slots.camera_focuses.get(planned_scene.key),
                        clip_ticks=duration,
                        canvas=canvas,
                        animation_prefix=f"anm_{planned_scene.key}",
                    )
                emit_clip(
                    object_dict,
                    animations,
                    source={
                        "snapshot_id": str(view.snapshot_id),
                        "snapshot_digest": view.snapshot_digest,
                        "source_range": None,
                    },
                    window=clip_bp.window,
                    track=clip_bp.track,
                    suffix="web",
                )
                continue
            if clip_bp.slot == "plate.cards":
                layout = clip_bp.card_layout or {}
                cards = slots.plate_cards
                n = len(cards)
                for i, card in enumerate(cards):
                    x = canvas[0] / 2 + (i - (n - 1) / 2) * layout.get("step", 520) - layout.get("width", 460) / 2
                    delay = float(clip_bp.preset_params.get("delay_step_s", 0.25)) * i
                    for part, style in (("big", clip_bp.big_style), ("label", clip_bp.label_style)):
                        assert style is not None
                        card_bp = clip_bp.model_copy(
                            update={
                                "layout": {
                                    "x": x,
                                    "y": layout.get("big_y" if part == "big" else "label_y", 400),
                                    "width": layout.get("width", 460),
                                    "height": layout.get(
                                        "big_height" if part == "big" else "label_height", 120
                                    ),
                                },
                                "style": style,
                                "preset_params": {**clip_bp.preset_params, "delay_s": delay},
                            }
                        )
                        object_id = f"obj_{planned_scene.key}_card{i}_{part}"
                        emit_clip(
                            _text_object(card_bp, object_id=object_id, text=card[part]),
                            _preset_animations(
                                card_bp,
                                object_id=object_id,
                                text=card[part],
                                clip_ticks=duration,
                                timebase=timebase,
                                animation_prefix=f"anm_{planned_scene.key}_card{i}_{part}",
                            ),
                            source=None,
                            window=None,
                            track=clip_bp.track,
                            suffix=f"card{i}_{part}",
                        )
                continue
            text = _slot_text(clip_bp, slots, planned_scene)
            object_id = f"obj_{planned_scene.key}_{clip_index}"
            emit_clip(
                _text_object(clip_bp, object_id=object_id, text=text),
                _preset_animations(
                    clip_bp,
                    object_id=object_id,
                    text=text,
                    clip_ticks=(
                        int(duration * clip_bp.window[1]) - int(duration * clip_bp.window[0])
                        if clip_bp.window else duration
                    ),
                    timebase=timebase,
                    animation_prefix=f"anm_{planned_scene.key}_{clip_index}",
                ),
                source=None,
                window=clip_bp.window,
                track=clip_bp.track,
                suffix=f"text{clip_index}",
            )

        # The scene's optional subtitle caption (exact copy, one clip over
        # the scene's window minus small insets).
        caption = slots.captions.get(planned_scene.key)
        if bp.caption and caption:
            inset = min(seconds_to_ticks(0.3, timebase), duration // 6)
            caption_bp = ClipBlueprint(
                track="trk_caption",
                slot="caption",
                layout=_Layout(x=260, y=920, width=1400, height=110),
                style=_Style(
                    font_size=34, color="#FFFFFF", weight=600, align="center",
                    line_height=1.3, background="#000000",
                ),
                preset="fade_in_out",
                preset_params={"in_s": 0.3, "out_s": 0.3},
            )
            object_id = f"obj_{planned_scene.key}_caption"
            start = scene_range["start"] + inset
            end = scene_range["end"] - inset
            ops.append(
                {
                    "op": "add_clip",
                    "track_id": caption_bp.track,
                    "clip": {
                        "clip_id": f"clp_{planned_scene.key}_caption",
                        "range": {"start": start, "end": max(end, start + frame_ticks)},
                        "scene_id": scene_id,
                        "source": None,
                        "object": _text_object(caption_bp, object_id=object_id, text=caption),
                        "animations": _preset_animations(
                            caption_bp,
                            object_id=object_id,
                            text=caption,
                            clip_ticks=max(end - start, frame_ticks),
                            timebase=timebase,
                            animation_prefix=f"anm_{planned_scene.key}_caption",
                        ),
                    },
                }
            )
        cursor += duration
    if media:
        cursor += _insert_product_media_ops(
            ops, media, slots, canvas=canvas, timebase=timebase, frame_ticks=frame_ticks,
        )
    if fixed_sfx is not None:
        video_scene = next(
            (op["scene"] for op in ops
             if op["op"] == "add_scene" and op["scene"]["scene_id"] == "scn_product_video"),
            None,
        )
        if video_scene is None:
            raise TemplateError("the product fixed SFX needs its real video entrance scene")
        ops.extend(instantiate_fixed_sound_cue(
            fixed_sfx,
            scene_id="scn_product_video",
            scene_start=int(video_scene["range"]["start"]),
            clip_suffix="product_video",
        ))
    if capture_views:
        from app.editing.web_shots import insert_capture_shot_ops

        cursor += insert_capture_shot_ops(
            ops, capture_views, canvas=canvas, timebase=timebase,
            fps_num=int(fps["num"]), fps_den=int(fps["den"]),
        )
    if music_bed is not None:
        bed_ops = _music_bed_ops(template, music_bed, total_ticks=cursor, timebase=timebase)
        if any(op["op"] == "bind_source" for op in bed_ops):
            bound.add(music_bed.snapshot_id)
        ops.extend(bed_ops)
    order_by_kind: dict[str, int] = {}
    for base_track in sorted(template.tracks, key=lambda t: t["order"]):
        for lane in lane_groups.get(base_track["track_id"], []):
            kind = lane["kind"]
            lane["order"] = order_by_kind.get(kind, 0)
            order_by_kind[kind] = lane["order"] + 1
    known_tracks = {lane["track_id"] for lanes in lane_groups.values() for lane in lanes}
    for op in ops:
        if op["op"] == "add_track" and op["track"]["track_id"] not in known_tracks:
            lane = op["track"]
            kind = lane["kind"]
            lane["order"] = order_by_kind.get(kind, 0)
            order_by_kind[kind] = lane["order"] + 1
            known_tracks.add(lane["track_id"])
    return ops


# ---------------------------------------------------------------------------
# The no-skill motion-graphics design (B1): the director's scene answers
# expand into text clips over a solid field — the SAME content model, the
# SAME write door; no template involved.
# ---------------------------------------------------------------------------

_MG_FONT_SIZES = {"medium": 64, "large": 96, "hero": 140}


def _mg_animations(
    enter: str,
    *,
    object_id: str,
    text: str,
    clip_ticks: int,
    timebase: int,
    prefix: str,
) -> list[dict[str, Any]]:
    """The MG entrance vocabulary (bounded presets, code-expanded — TextPart
    targets derive from the clip's own text)."""
    def t(seconds: float) -> int:
        return seconds_to_ticks(seconds, timebase)

    if enter == "fade":
        return [
            {
                "animation_id": f"{prefix}_opacity",
                "target_object_id": object_id,
                "text_part": None,
                "property": "opacity",
                "keyframes": [_kf(0, 0.0), _kf(min(t(0.6), clip_ticks), 1.0)],
            }
        ]
    if enter == "rise":
        return [
            {
                "animation_id": f"{prefix}_opacity",
                "target_object_id": object_id,
                "text_part": None,
                "property": "opacity",
                "keyframes": [_kf(0, 0.0), _kf(min(t(0.5), clip_ticks), 1.0)],
            },
            {
                "animation_id": f"{prefix}_position",
                "target_object_id": object_id,
                "text_part": None,
                "property": "transform.position",
                "keyframes": [_kf(0, [0.0, 64.0]), _kf(min(t(0.9), clip_ticks), [0.0, 0.0], "ease")],
            },
        ]
    if enter in ("lines", "words", "graphemes"):
        kind: Literal["line", "word", "grapheme"]
        if enter == "lines":
            kind, stagger_s, dur_s = "line", 0.45, 0.8
        elif enter == "words":
            kind, stagger_s, dur_s = "word", 0.14, 0.3
        else:
            kind, stagger_s, dur_s = "grapheme", 0.06, 0.24
        parts = derive_text_parts(text, kind)
        target = {
            "kind": kind,
            "part_ids": [part.part_id for part in parts],
            "stagger": t(stagger_s),
        }
        return [
            {
                "animation_id": f"{prefix}_{kind}_opacity",
                "target_object_id": object_id,
                "text_part": target,
                "property": "opacity",
                "keyframes": [_kf(0, 0.0), _kf(min(t(dur_s), clip_ticks), 1.0)],
            }
        ]
    raise TemplateError(f"unknown MG entrance {enter!r}")


def _mg_shape_animations(
    motion: str, *, object_id: str, clip_ticks: int, timebase: int, prefix: str
) -> list[dict[str, Any]]:
    at = min(seconds_to_ticks(0.8, timebase), clip_ticks)

    def animation(property_name: str, values: list[Any]) -> dict[str, Any]:
        return {
            "animation_id": f"{prefix}_{property_name.replace('.', '_')}",
            "target_object_id": object_id,
            "text_part": None,
            "property": property_name,
            "keyframes": [
                _kf(0, values[0]),
                _kf(at, values[1], "ease"),
            ],
        }

    if motion == "fade":
        return [animation("opacity", [0.0, 1.0])]
    if motion == "rise":
        return [animation("transform.position", [[0.0, 80.0], [0.0, 0.0]])]
    if motion == "scale":
        return [animation("transform.scale", [0.2, 1.0])]
    if motion == "rotate":
        return [animation("transform.rotation", [0.0, 90.0])]
    raise TemplateError(f"unknown shape motion {motion!r}")


def instantiate_mg(
    direction: Any,
    *,
    aspect: str = "16:9",
    background: str | None = None,
    narration_voice: dict[str, Any] | None = None,
    music_bed: MusicBed | None = None,
    preset_id: str | None = None,
) -> list[dict[str, Any]]:
    """The MG director's validated answer → the create-path op batch.
    ``direction`` is editing/director.py's MgDirection (imported as Any to
    keep this module's import graph one-directional)."""
    canvas = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}[aspect]
    timebase = 90000
    fps_num, fps_den = 30, 1
    background = background or direction.background or "#0B1020"
    frame_ticks = seconds_to_ticks(fps_den / fps_num, timebase)
    if narration_voice is None and any(scene.narration is not None for scene in direction.scenes):
        raise TemplateError("narrated scenes need a resolved voice")
    if narration_voice is not None and any(not scene.narration for scene in direction.scenes):
        raise TemplateError("every scene needs exact narration while narration is enabled")

    ops: list[dict[str, Any]] = [
        {
            "op": "set_settings",
            "settings": {
                "width": canvas[0],
                "height": canvas[1],
                "fps": {"num": fps_num, "den": fps_den},
                "timebase": timebase,
                "sample_rate": 48000,
                "channels": 2,
                "background": background,
            },
        },
        {
            "op": "add_track",
            "track": {
                "track_id": "trk_title",
                "kind": "visual",
                "role": "title",
                "order": 0,
                "clips": [],
            },
        },
    ]
    if narration_voice is not None:
        ops.extend([
            {
                "op": "add_track",
                "track": {
                    "track_id": "trk_dialogue",
                    "kind": "audio",
                    "role": "dialogue",
                    "order": 1 if music_bed is not None else 0,
                    "clips": [],
                },
            },
            {
                "op": "add_track",
                "track": {
                    "track_id": "trk_caption",
                    "kind": "visual",
                    "role": "caption",
                    "order": 0,
                    "clips": [],
                },
            },
        ])
    shape_lanes = max((len(scene.shapes) for scene in direction.scenes), default=0)
    if shape_lanes:
        ops[1]["track"]["order"] = shape_lanes
        for lane in range(1, shape_lanes + 1):
            ops.insert(
                lane,
                {
                    "op": "add_track",
                    "track": {
                        "track_id": "trk_shape" if lane == 1 else f"trk_shape_{lane}",
                        "kind": "visual",
                        "role": "effect",
                        "order": lane - 1,
                        "clips": [],
                    },
                },
            )
    if narration_voice is not None:
        caption_track = next(op["track"] for op in ops if op["op"] == "add_track" and op["track"]["track_id"] == "trk_caption")
        caption_track["order"] = shape_lanes + 1
    text_lanes = max((len(scene.text_beats) for scene in direction.scenes), default=0)
    for lane in range(1, text_lanes):
        ops.append({"op": "add_track", "track": {
            "track_id": f"trk_text_{lane}", "kind": "visual", "role": "title",
            "order": shape_lanes + lane, "clips": [],
        }})
    if narration_voice is not None:
        caption_track["order"] = shape_lanes + max(text_lanes, 1)
    text_clip_ids: list[str] = []
    cursor = 0
    for index, scene in enumerate(direction.scenes, start=1):
        duration = max(
            round(seconds_to_ticks(scene.duration_seconds, timebase) / frame_ticks), 1
        ) * frame_ticks
        scene_id = f"scn_mg_{index}"
        ops.append(
            {
                "op": "add_scene",
                "scene": {
                    "scene_id": scene_id,
                    "range": {"start": cursor, "end": cursor + duration},
                    "intent": scene.intent,
                    "visual_description": scene.visual_description,
                    "speech_clip_ids": [f"clp_mg_{index}_speech"] if narration_voice is not None else [],
                },
            }
        )
        for beat_index, beat in enumerate(scene.text_beats or [scene]):
            suffix = f"_beat_{beat_index + 1}" if scene.text_beats else ""
            beat_start = cursor + round(seconds_to_ticks(beat.start_seconds, timebase) / frame_ticks) * frame_ticks if scene.text_beats else cursor
            beat_end = cursor + round(seconds_to_ticks(beat.end_seconds, timebase) / frame_ticks) * frame_ticks if scene.text_beats else cursor + duration
            beat_duration = beat_end - beat_start
            if beat_duration <= 0:
                raise TemplateError("text beat needs at least one output frame")
            text = "\n".join(line.strip() for line in beat.lines if line.strip())
            font_size = beat.font_size if scene.text_beats else _MG_FONT_SIZES[scene.size]
            block_height = max(len(beat.lines), 1) * font_size * 1.15
            layout = {
                "x": 120.0,
                "y": max(120.0, (canvas[1] - block_height) / 2),
                "width": float(canvas[0] - 240),
                "height": block_height * 1.25,
            }
            if scene.text_beats:
                layout = {"x": beat.x * canvas[0], "y": beat.y * canvas[1],
                          "width": beat.width * canvas[0], "height": beat.height * canvas[1]}
            object_id = f"obj_mg_{index}" + suffix
            clip_id = f"clp_mg_{index}" + suffix
            text_clip_ids.append(clip_id)
            ops.append(
                {
                    "op": "add_clip",
                    "track_id": "trk_title" if beat_index == 0 else f"trk_text_{beat_index}",
                    "clip": {
                        "clip_id": clip_id,
                        "range": {"start": beat_start, "end": beat_start + beat_duration},
                        "scene_id": scene_id,
                        "source": None,
                        "object": {
                            "kind": "text",
                            "object_id": object_id,
                            "text": text,
                            "layout": layout,
                            "style": {
                                "font_size": font_size,
                                "color": beat.color or "#F8FAFC",
                                "background": None,
                                "weight": beat.weight if scene.text_beats else 700,
                                "align": beat.align,
                                "line_height": 1.15,
                            },
                            "transform": {
                                "x": 0.0,
                                "y": 0.0,
                                "scale": 1.0,
                                "rotation": 0.0,
                                "origin": "center",
                            },
                            "opacity": 1.0,
                        },
                        "animations": ([] if preset_id is not None else _mg_animations(
                            beat.enter,
                            object_id=object_id,
                            text=text,
                            clip_ticks=beat_duration,
                            timebase=timebase,
                            prefix=f"anm_mg_{index}{suffix}",
                        )) + ([{
                            "animation_id": f"anm_mg_{index}{suffix}_drift",
                            "target_object_id": object_id,
                            "text_part": None,
                            "property": "transform.scale",
                            "keyframes": [
                                _kf(0, 1.0 if beat.drift == "push_in" else 1.035),
                                _kf(beat_duration, 1.035 if beat.drift == "push_in" else 1.0),
                            ],
                        }] if beat.drift != "none" else []),
                    },
                }
            )
        if narration_voice is not None:
            speech_text = scene.narration or ""
            speech_object_id = f"obj_mg_{index}_speech"
            ops.extend([
                {
                    "op": "add_clip",
                    "track_id": "trk_dialogue",
                    "clip": {
                        "clip_id": f"clp_mg_{index}_speech",
                        "range": {"start": cursor, "end": cursor + duration},
                        "scene_id": scene_id,
                        "source": None,
                        "object": {
                            "kind": "speech",
                            "object_id": speech_object_id,
                            "text": speech_text,
                            **narration_voice,
                            "gain_db": 0.0,
                        },
                        "animations": [],
                    },
                },
                {
                    "op": "add_clip",
                    "track_id": "trk_caption",
                    "clip": {
                        "clip_id": f"clp_mg_{index}_caption",
                        "range": {"start": cursor, "end": cursor + duration},
                        "scene_id": scene_id,
                        "source": None,
                        "object": {
                            "kind": "text",
                            "object_id": f"obj_mg_{index}_caption",
                            "text": speech_text,
                            "layout": {
                                "x": 160.0,
                                "y": float(canvas[1] - 170),
                                "width": float(canvas[0] - 320),
                                "height": 120.0,
                            },
                            "style": {
                                "font_size": max(24, round(canvas[0] * 34 / 1920)),
                                "color": "#FFFFFF",
                                "background": "#000000",
                                "weight": 600,
                                "align": "center",
                                "line_height": 1.3,
                            },
                            "transform": {
                                "x": 0.0, "y": 0.0, "scale": 1.0,
                                "rotation": 0.0, "origin": "center",
                            },
                            "opacity": 1.0,
                            "caption": {
                                "speech_object_id": speech_object_id,
                                "source_text_digest": speech_text_digest(speech_text),
                                "alignment": "minimax-t2a-v2-sentence-v1",
                                "state": "derived",
                            },
                        },
                        "animations": [],
                    },
                },
            ])
        for shape_index, shape in enumerate(scene.shapes, start=1):
            shape_object_id = f"obj_mg_{index}_shape_{shape_index}"
            ops.append(
                {
                    "op": "add_clip",
                    "track_id": "trk_shape" if shape_index == 1 else f"trk_shape_{shape_index}",
                    "clip": {
                        "clip_id": f"clp_mg_{index}_shape_{shape_index}",
                        "range": {"start": cursor, "end": cursor + duration},
                        "scene_id": scene_id,
                        "source": None,
                        "object": {
                            "kind": "shape",
                            "object_id": shape_object_id,
                            "shape": shape.shape,
                            "layout": {
                                "x": shape.x * canvas[0],
                                "y": shape.y * canvas[1],
                                "width": shape.width * canvas[0],
                                "height": shape.height * canvas[1],
                            },
                            "fill": shape.fill,
                            "stroke": None,
                            "stroke_width": 0.0,
                            "corner_radius": shape.corner_radius if shape.shape == "rect" else 0.0,
                            "path": None,
                            "transform": {
                                "x": 0.0, "y": 0.0, "scale": 1.0,
                                "rotation": 0.0, "origin": "center",
                            },
                            "opacity": shape.opacity,
                        },
                        "animations": _mg_shape_animations(
                            shape.motion,
                            object_id=shape_object_id,
                            clip_ticks=duration,
                            timebase=timebase,
                            prefix=f"anm_mg_{index}_shape_{shape_index}",
                        ),
                    },
                }
            )
        cursor += duration
    if music_bed is not None:
        ops.extend(instantiate_music_bed(music_bed, total_ticks=cursor, timebase=timebase))
    if preset_id is not None:
        from app.editing.edits import EditTarget
        from app.editing.presets import expand_preset_at_target

        bound = (
            {music_bed.snapshot_id: music_bed.snapshot_digest}
            if music_bed is not None else {}
        )
        candidate = apply_ops(
            CompositionContent(settings=ops[0]["settings"]),
            _OP_BATCH.validate_python(ops),
            bound,
        )
        for clip_id in text_clip_ids:
            preset_ops = expand_preset_at_target(
                preset_id,
                candidate,
                EditTarget(kind="clip", id=clip_id),
            )
            ops.extend(op.model_dump(mode="json", exclude_unset=True) for op in preset_ops)
            candidate = apply_ops(candidate, preset_ops, bound)
    return ops


def instantiate_aligned_narration(
    direction: Any,
    *,
    payload: NarrationPayload,
    alignment: NarrationAlignmentRef,
    snapshot: Any,
    aspect: str = "16:9",
    background: str | None = None,
    music_bed: MusicBed | None = None,
) -> list[dict[str, Any]]:
    """READY sentence facts → native titles, fixed source audio and word anchors."""
    canvas = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}[aspect]
    timebase = 90000
    background = background or direction.background or "#0B1020"
    sentence_by_id = {sentence.sentence_id: sentence for sentence in payload.sentences}
    groups = [
        [sentence_by_id[sentence_id] for sentence_id in scene.sentence_ids]
        for scene in direction.scenes
    ]
    total_ticks = source_ticks_to_output_ticks(payload.duration_ticks, timebase)
    ops: list[dict[str, Any]] = [
        {
            "op": "set_settings",
            "settings": {
                "width": canvas[0], "height": canvas[1],
                "fps": {"num": 30, "den": 1}, "timebase": timebase,
                "sample_rate": 48000, "channels": 2, "background": background,
            },
        },
        {"op": "bind_source", "snapshot_id": str(snapshot.id)},
        {
            "op": "add_track",
            "track": {"track_id": "trk_title", "kind": "visual", "role": "title", "order": 0, "clips": []},
        },
        {
            "op": "add_track",
            "track": {"track_id": "trk_dialogue", "kind": "audio", "role": "dialogue", "order": 1 if music_bed is not None else 0, "clips": []},
        },
        {
            "op": "add_track",
            "track": {"track_id": "trk_caption", "kind": "visual", "role": "caption", "order": 1, "clips": []},
        },
    ]
    shape_lanes = max((len(scene.shapes) for scene in direction.scenes), default=0)
    if shape_lanes:
        ops[2]["track"]["order"] = shape_lanes
        ops[4]["track"]["order"] = shape_lanes + 1
        for lane in range(1, shape_lanes + 1):
            ops.insert(
                2 + lane,
                {
                    "op": "add_track",
                    "track": {
                        "track_id": "trk_shape" if lane == 1 else f"trk_shape_{lane}",
                        "kind": "visual", "role": "effect", "order": lane - 1, "clips": [],
                    },
                },
            )

    if any(scene.generator is not None for scene in direction.scenes):
        for op in ops:
            if op["op"] == "add_track" and op["track"]["kind"] == "visual":
                op["track"]["order"] += 1
        ops.insert(2, {
            "op": "add_track",
            "track": {
                "track_id": "trk_aligned_generator", "kind": "visual", "role": "main",
                "order": 0, "clips": [],
            },
        })

    for index, (scene, sentences) in enumerate(zip(direction.scenes, groups, strict=True), start=1):
        scene_id = f"scn_aligned_{index}"
        scene_start = 0 if index == 1 else source_ticks_to_output_ticks(sentences[0].start_tick, timebase)
        scene_end = (
            source_ticks_to_output_ticks(groups[index][0].start_tick, timebase)
            if index < len(groups)
            else total_ticks
        )
        if scene_end <= scene_start:
            raise TemplateError(f"aligned scene {scene_id} has no positive output window")
        speech_clip_ids = [f"clp_aligned_{sentence.sentence_id}_speech" for sentence in sentences]
        ops.append({
            "op": "add_scene",
            "scene": {
                "scene_id": scene_id,
                "range": {"start": scene_start, "end": scene_end},
                "intent": scene.intent,
                "visual_description": scene.visual_description,
                "speech_clip_ids": speech_clip_ids,
            },
        })
        text = "\n".join(line.strip() for line in scene.lines if line.strip())
        font_size = _MG_FONT_SIZES[scene.size]
        block_height = max(len(scene.lines), 1) * font_size * 1.15
        object_id = f"obj_aligned_{index}"
        ops.append({
            "op": "add_clip",
            "track_id": "trk_title",
            "clip": {
                "clip_id": f"clp_aligned_{index}",
                "range": {"start": scene_start, "end": scene_end},
                "scene_id": scene_id,
                "source": None,
                "object": {
                    "kind": "text", "object_id": object_id, "text": text,
                    "layout": {
                        "x": 120.0,
                        "y": max(120.0, (canvas[1] - block_height) / 2),
                        "width": float(canvas[0] - 240), "height": block_height * 1.25,
                    },
                    "style": {
                        "font_size": font_size, "color": scene.color or "#F8FAFC",
                        "background": None, "weight": 700, "align": scene.align, "line_height": 1.15,
                    },
                    "transform": {"x": 0.0, "y": 0.0, "scale": 1.0, "rotation": 0.0, "origin": "center"},
                    "opacity": 1.0,
                },
                "animations": _mg_animations(
                    scene.enter, object_id=object_id, text=text,
                    clip_ticks=scene_end - scene_start, timebase=timebase,
                    prefix=f"anm_aligned_{index}",
                ) + ([{
                    "animation_id": f"anm_aligned_{index}_drift",
                    "target_object_id": object_id, "text_part": None,
                    "property": "transform.scale",
                    "keyframes": [
                        _kf(0, 1.0 if scene.drift == "push_in" else 1.035),
                        _kf(scene_end - scene_start, 1.035 if scene.drift == "push_in" else 1.0),
                    ],
                }] if scene.drift != "none" else []),
            },
        })

        if scene.generator is not None:
            generator_object_id = f"obj_aligned_{index}_generator"
            duration_frames = (scene_end - scene_start) * GENERATOR_FPS // timebase
            if duration_frames < 1:
                raise TemplateError(f"aligned scene {scene_id} is too short for its Generator")
            generator_end = scene_start + duration_frames * (timebase // GENERATOR_FPS)
            generator = scene.generator
            source_fields: dict[str, Any]
            if generator.producer == "remotion-project":
                assert generator.project is not None
                source_fields = {
                    "producer": "remotion-project",
                    "project": generator.project.model_dump(mode="json"),
                    "parameters": {},
                }
            else:
                assert generator.code is not None
                source_fields = {
                    "producer": "draw-2d",
                    "code": generator.code,
                    "parameters": generator.parameters,
                }
            ops.append({
                "op": "add_clip",
                "track_id": "trk_aligned_generator",
                "clip": {
                    "clip_id": f"clp_aligned_{index}_generator",
                    "range": {"start": scene_start, "end": generator_end},
                    "scene_id": scene_id,
                    "source": None,
                    "object": {
                        "kind": "generator", "object_id": generator_object_id,
                        **source_fields,
                        "output": {
                            "width": canvas[0], "height": canvas[1],
                            "fps": GENERATOR_FPS,
                            "duration_frames": duration_frames,
                            "background": background,
                        },
                        "layout": {
                            "x": 0.0, "y": 0.0,
                            "width": float(canvas[0]), "height": float(canvas[1]),
                        },
                        "fit": "cover",
                        "transform": {
                            "x": 0.0, "y": 0.0, "scale": 1.0,
                            "rotation": 0.0, "origin": "center",
                        },
                        "opacity": 1.0,
                    },
                    "animations": [],
                },
            })

        for sentence in sentences:
            start = source_ticks_to_output_ticks(sentence.start_tick, timebase)
            end = source_ticks_to_output_ticks(sentence.end_tick, timebase)
            speech_object_id = f"obj_aligned_{sentence.sentence_id}_speech"
            source = {
                "snapshot_id": str(snapshot.id), "snapshot_digest": snapshot.digest,
                "source_range": {"start": sentence.start_tick, "end": sentence.end_tick},
            }
            ops.append({
                "op": "add_clip", "track_id": "trk_dialogue",
                "clip": {
                    "clip_id": f"clp_aligned_{sentence.sentence_id}_speech",
                    "range": {"start": start, "end": end}, "scene_id": scene_id,
                    "source": source,
                    "object": {
                        "kind": "speech", "object_id": speech_object_id, "text": sentence.text,
                        "provider": None, "model": None, "voice_id": None,
                        "language": direction.language or "und", "gain_db": 0.0,
                        "alignment": alignment.model_dump(mode="json"),
                    },
                    "animations": [],
                },
            })

        for shape_index, shape in enumerate(scene.shapes, start=1):
            shape_object_id = f"obj_aligned_{index}_shape_{shape_index}"
            ops.append({
                "op": "add_clip",
                "track_id": "trk_shape" if shape_index == 1 else f"trk_shape_{shape_index}",
                "clip": {
                    "clip_id": f"clp_aligned_{index}_shape_{shape_index}",
                    "range": {"start": scene_start, "end": scene_end}, "scene_id": scene_id,
                    "source": None,
                    "object": {
                        "kind": "shape", "object_id": shape_object_id,
                        "shape": shape.shape,
                        "layout": {
                            "x": shape.x * canvas[0], "y": shape.y * canvas[1],
                            "width": shape.width * canvas[0], "height": shape.height * canvas[1],
                        },
                        "fill": shape.fill, "stroke": None, "stroke_width": 0.0,
                        "corner_radius": shape.corner_radius if shape.shape == "rect" else 0.0,
                        "path": None,
                        "transform": {"x": 0.0, "y": 0.0, "scale": 1.0, "rotation": 0.0, "origin": "center"},
                        "opacity": shape.opacity,
                    },
                    "animations": _mg_shape_animations(
                        shape.motion, object_id=shape_object_id,
                        clip_ticks=scene_end - scene_start, timebase=timebase,
                        prefix=f"anm_aligned_{index}_shape_{shape_index}",
                    ),
                },
            })
    bound = {snapshot.id: snapshot.digest}
    candidate = apply_ops(
        CompositionContent(settings={"width": canvas[0], "height": canvas[1]}),
        _OP_BATCH.validate_python(ops),
        bound,
    )
    caption_ops = expand_preset("caption-phrases", candidate, {
        "payload": payload,
        "alignment": alignment,
        "cue": "sentence",
    })
    ops.extend(op.model_dump(mode="json", exclude_unset=True) for op in caption_ops)
    candidate = apply_ops(candidate, caption_ops, bound)
    for sentence in payload.sentences:
        semantics = sentence.semantics
        for word_id in (semantics.emphasis_word_ids if semantics is not None else []):
            impact_ops = expand_preset("text-impact", candidate, {
                "narration": {
                    "payload": payload,
                    "alignment": alignment,
                    "word_id": word_id,
                },
            })
            ops.extend(op.model_dump(mode="json", exclude_unset=True) for op in impact_ops)
            candidate = apply_ops(candidate, impact_ops, bound)
    if music_bed is not None:
        ops.extend(instantiate_music_bed(music_bed, total_ticks=total_ticks, timebase=timebase))
    return ops


def _instantiate_generator(
    direction: Any,
    *,
    aspect: str,
    background: str,
    output: dict[str, Any],
    source_fields: dict[str, Any],
    scene_id: str,
    title_clip_id: str,
    title_object_id: str,
    animation_prefix: str,
    narration: str | None = None,
    narration_voice: dict[str, Any] | None = None,
    start_ticks: int = 0,
    include_structure: bool = True,
    generator_clip_id: str = "clp_generator",
    generator_object_id: str = "obj_generator",
) -> list[dict[str, Any]]:
    """One fixed-media Generator background plus independent native content."""
    if (narration is None) != (narration_voice is None):
        raise TemplateError("native narration needs exact text and a resolved voice")
    width, height = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}[aspect]
    timebase = 90000
    fps = int(output.get("fps", GENERATOR_FPS))
    duration_frames = int(output.get(
        "duration_frames", max(1, round(direction.duration_seconds * fps))
    ))
    if timebase % fps:
        raise TemplateError("Generator fps must divide the Composition timebase exactly")
    duration = duration_frames * timebase // fps
    end_ticks = start_ticks + duration
    scene_op: dict[str, Any] = {
        "op": "add_scene",
        "scene": {
            "scene_id": scene_id,
            "range": {"start": start_ticks, "end": end_ticks},
            "intent": direction.intent,
            "visual_description": direction.visual_description,
            "speech_clip_ids": [],
        },
    }
    generator_track_op: dict[str, Any] = {
        "op": "add_track",
        "track": {"track_id": "trk_generator", "kind": "visual", "role": "main", "order": 0, "clips": []},
    }
    generator_clip_op: dict[str, Any] = {
        "op": "add_clip",
        "track_id": "trk_generator",
        "clip": {
            "clip_id": generator_clip_id,
            "range": {"start": start_ticks, "end": end_ticks},
            "scene_id": scene_id,
            "source": None,
            "object": {
                "kind": "generator",
                "object_id": generator_object_id,
                **source_fields,
                "output": output,
                "layout": {"x": 0.0, "y": 0.0, "width": float(width), "height": float(height)},
                "fit": "cover",
                "transform": {"x": 0.0, "y": 0.0, "scale": 1.0, "rotation": 0.0, "origin": "center"},
                "opacity": 1.0,
            },
            "animations": [],
        },
    }
    ops: list[dict[str, Any]] = []
    if include_structure:
        ops.append({
            "op": "set_settings",
            "settings": {
                "width": width, "height": height, "fps": {"num": 30, "den": 1},
                "timebase": timebase, "sample_rate": 48000, "channels": 2,
                "background": background,
            },
        })
        ops.append(generator_track_op)
    ops.extend([scene_op, generator_clip_op])
    title = (direction.title or "").strip()
    if title:
        ops.extend([
            {
                "op": "add_track",
                "track": {"track_id": "trk_title", "kind": "visual", "role": "title", "order": 1, "clips": []},
            },
            {
                "op": "add_clip",
                "track_id": "trk_title",
                "clip": {
                    "clip_id": title_clip_id,
                    "range": {"start": start_ticks, "end": end_ticks},
                    "scene_id": scene_id,
                    "source": None,
                    "object": {
                        "kind": "text",
                        "object_id": title_object_id,
                        "text": title,
                        "layout": {
                            "x": width * 0.08, "y": height * 0.76,
                            "width": width * 0.84, "height": height * 0.16,
                        },
                        "style": {
                            "font_size": 64 if width >= height else 56,
                            "color": "#F8FAFC", "background": "#111827", "weight": 700,
                            "align": "center", "line_height": 1.15,
                        },
                        "transform": {"x": 0.0, "y": 0.0, "scale": 1.0, "rotation": 0.0, "origin": "center"},
                        "opacity": 1.0,
                    },
                    "animations": _mg_animations(
                        "fade", object_id=title_object_id, text=title,
                        clip_ticks=duration, timebase=timebase, prefix=animation_prefix,
                    ),
                },
            },
        ])
    if narration is not None and narration_voice is not None:
        # Narration drives the component's design, but its spoken copy and
        # captions remain native editable objects, never baked component audio.
        speech_clip_id = f"{scene_id.replace('scn_', 'clp_', 1)}_speech"
        caption_clip_id = f"{scene_id.replace('scn_', 'clp_', 1)}_caption"
        speech_object_id = f"{speech_clip_id.replace('clp_', 'obj_', 1)}"
        scene_op["scene"]["speech_clip_ids"] = [speech_clip_id]
        ops.extend([
            {
                "op": "add_track",
                "track": {"track_id": "trk_dialogue", "kind": "audio", "role": "dialogue", "order": 0, "clips": []},
            },
            {
                "op": "add_track",
                "track": {"track_id": "trk_caption", "kind": "visual", "role": "caption", "order": 2, "clips": []},
            },
            {
                "op": "add_clip",
                "track_id": "trk_dialogue",
                "clip": {
                    "clip_id": speech_clip_id,
                    "range": {"start": start_ticks, "end": end_ticks},
                    "scene_id": scene_id,
                    "source": None,
                    "object": {
                        "kind": "speech",
                        "object_id": speech_object_id,
                        "text": narration,
                        **narration_voice,
                        "gain_db": 0.0,
                    },
                    "animations": [],
                },
            },
            {
                "op": "add_clip",
                "track_id": "trk_caption",
                "clip": {
                    "clip_id": caption_clip_id,
                    "range": {"start": start_ticks, "end": end_ticks},
                    "scene_id": scene_id,
                    "source": None,
                    "object": {
                        "kind": "text",
                        "object_id": f"{caption_clip_id.replace('clp_', 'obj_', 1)}",
                        "text": narration,
                        "layout": {
                            "x": 160.0,
                            "y": float(height - 170),
                            "width": float(width - 320),
                            "height": 120.0,
                        },
                        "style": {
                            "font_size": max(24, round(width * 34 / 1920)),
                            "color": "#FFFFFF",
                            "background": "#000000",
                            "weight": 600,
                            "align": "center",
                            "line_height": 1.3,
                        },
                        "transform": {
                            "x": 0.0, "y": 0.0, "scale": 1.0,
                            "rotation": 0.0, "origin": "center",
                        },
                        "opacity": 1.0,
                        "caption": {
                            "speech_object_id": speech_object_id,
                            "source_text_digest": speech_text_digest(narration),
                            "alignment": "minimax-t2a-v2-sentence-v1",
                            "state": "derived",
                        },
                    },
                    "animations": [],
                },
            },
        ])
    if not include_structure:
        ops = [op for op in ops if op["op"] not in {"set_settings", "add_track"}]
    return ops


def instantiate_program(
    direction: Any, *, aspect: str = "16:9", background: str | None = None
) -> list[dict[str, Any]]:
    """One Agent-authored draw-2d background plus optional native title."""
    width, height = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}[aspect]
    duration_frames = max(1, round(direction.duration_seconds * GENERATOR_FPS))
    output = {
        "width": width,
        "height": height,
        "fps": GENERATOR_FPS,
        "duration_frames": duration_frames,
        "background": background or direction.background,
    }
    return _instantiate_generator(
        direction,
        aspect=aspect,
        background=output["background"],
        output=output,
        source_fields={
            "producer": "draw-2d",
            "code": direction.code,
            "parameters": direction.parameters,
        },
        scene_id="scn_program",
        title_clip_id="clp_program_title",
        title_object_id="obj_program_title",
        animation_prefix="anm_program_title",
    )


def instantiate_component(
    direction: Any,
    *,
    aspect: str = "16:9",
    background: str | None = None,
    narration: str | None = None,
    narration_voice: dict[str, Any] | None = None,
    start_ticks: int = 0,
    include_structure: bool = True,
    scene_index: int | None = None,
) -> list[dict[str, Any]]:
    """One controlled TSX scene plus independent native title/narration."""
    width, height = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}[aspect]
    duration_frames = max(1, round(direction.duration_seconds * GENERATOR_FPS))
    output = {
        "width": width,
        "height": height,
        "fps": GENERATOR_FPS,
        "duration_frames": duration_frames,
        "background": background or direction.background,
    }
    ops = _instantiate_generator(
        direction,
        aspect=aspect,
        background=output["background"],
        output=output,
        source_fields={
            "producer": "remotion-project",
            "project": {
                "schema_version": 1,
                "entry": direction.entry,
                "composition_id": direction.composition_id,
                "files": [item.model_dump(mode="json") for item in direction.files],
                "props": direction.props,
                "props_schema": direction.props_schema,
                "resources": [item.model_dump(mode="json") for item in direction.resources],
            },
            "parameters": {},
        },
        scene_id="scn_component" if scene_index is None else f"scn_component_{scene_index}",
        title_clip_id="clp_component_title" if scene_index is None else f"clp_component_{scene_index}_title",
        title_object_id="obj_component_title" if scene_index is None else f"obj_component_{scene_index}_title",
        animation_prefix="anm_component_title" if scene_index is None else f"anm_component_{scene_index}_title",
        narration=narration,
        narration_voice=narration_voice,
        start_ticks=start_ticks,
        include_structure=include_structure,
        generator_clip_id="clp_generator" if scene_index is None else f"clp_component_{scene_index}_generator",
        generator_object_id="obj_generator" if scene_index is None else f"obj_component_{scene_index}_generator",
    )
    bindings: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for resource in direction.resources:
        if resource.snapshot_id in seen:
            continue
        seen.add(resource.snapshot_id)
        bindings.append({"op": "bind_source", "snapshot_id": str(resource.snapshot_id)})
    return [*bindings, *ops]


def instantiate_component_video(
    direction: Any,
    *,
    aspect: str = "16:9",
    background: str | None = None,
    narration_voice: dict[str, Any] | None = None,
    music_bed: MusicBed | None = None,
) -> list[dict[str, Any]]:
    """A coherent multi-scene code animation on the ordinary Composition timeline."""
    width, height = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}[aspect]
    canvas_background = background or direction.scenes[0].background
    ops: list[dict[str, Any]] = [
        {
            "op": "set_settings",
            "settings": {
                "width": width, "height": height, "fps": {"num": 30, "den": 1},
                "timebase": 90000, "sample_rate": 48000, "channels": 2,
                "background": canvas_background,
            },
        },
        {"op": "add_track", "track": {
            "track_id": "trk_generator", "kind": "visual", "role": "main", "order": 0, "clips": [],
        }},
        {"op": "add_track", "track": {
            "track_id": "trk_title", "kind": "visual", "role": "title", "order": 1, "clips": [],
        }},
        {"op": "add_track", "track": {
            "track_id": "trk_caption", "kind": "visual", "role": "caption", "order": 2, "clips": [],
        }},
        {"op": "add_track", "track": {
            "track_id": "trk_dialogue", "kind": "audio", "role": "dialogue", "order": 0, "clips": [],
        }},
    ]
    cursor = 0
    bound: set[Any] = set()
    for index, scene in enumerate(direction.scenes, start=1):
        scene_narration = scene.narration if scene.narration else None
        scene_ops = instantiate_component(
            scene,
            aspect=aspect,
            background=background,
            narration=scene_narration,
            narration_voice=narration_voice if scene_narration is not None else None,
            start_ticks=cursor,
            include_structure=False,
            scene_index=index,
        )
        for op in scene_ops:
            if op["op"] == "bind_source":
                snapshot_id = op["snapshot_id"]
                if snapshot_id in bound:
                    continue
                bound.add(snapshot_id)
            ops.append(op)
        generator = next(
            op for op in scene_ops
            if op["op"] == "add_clip" and op["clip"]["clip_id"] == f"clp_component_{index}_generator"
        )
        cursor = generator["clip"]["range"]["end"]
    if music_bed is not None:
        ops.extend(instantiate_music_bed(music_bed, total_ticks=cursor, timebase=90000))
    return ops


def instantiate_generated_image(
    direction: Any, *, aspect: str = "16:9", background: str | None = None
) -> list[dict[str, Any]]:
    """One MiniMax image-01 request plus an independent native title."""
    return _instantiate_generator(
        direction,
        aspect=aspect,
        background=background or "#000000",
        output={"aspect_ratio": "16:9"},
        source_fields={
            "producer": "image-generation",
            "prompt": direction.prompt,
            "provider": "minimax",
            "model": "image-01",
            "parameters": {},
        },
        scene_id="scn_generated_image",
        title_clip_id="clp_generated_image_title",
        title_object_id="obj_generated_image_title",
        animation_prefix="anm_generated_image_title",
    )


def instantiate_mixed(
    direction: Any,
    *,
    snapshot_digest: str,
    aspect: str = "16:9",
    background: str | None = None,
    music_bed: MusicBed | None = None,
) -> list[dict[str, Any]]:
    """A real source window as dynamic background + central picture + sound.

    Native title/caption clips stay independently editable. The two pictures
    share source bytes but only the central object may emit original audio.
    """
    width, height = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}[aspect]
    timebase = 90000
    source_start = seconds_to_ticks(direction.source_start_seconds, timebase)
    source_end = seconds_to_ticks(direction.source_end_seconds, timebase)
    duration = source_end - source_start
    source = {
        "snapshot_id": str(direction.source_snapshot_id),
        "snapshot_digest": snapshot_digest,
        "source_range": {"start": source_start, "end": source_end},
    }
    output_range = {"start": 0, "end": duration}
    scene_id = "scn_mixed"
    ops: list[dict[str, Any]] = [
        {
            "op": "set_settings",
            "settings": {
                "width": width,
                "height": height,
                "fps": {"num": 30, "den": 1},
                "timebase": timebase,
                "sample_rate": 48000,
                "channels": 2,
                "background": background or "#000000",
            },
        },
        {"op": "bind_source", "snapshot_id": str(direction.source_snapshot_id)},
        {
            "op": "add_scene",
            "scene": {
                "scene_id": scene_id,
                "range": output_range,
                "intent": direction.intent,
                "visual_description": direction.visual_description,
                "speech_clip_ids": [],
            },
        },
    ]
    for track_id, role, order in (
        ("trk_background", "main", 0),
        ("trk_video", "main", 1),
        ("trk_title", "title", 2),
        ("trk_caption", "caption", 3),
    ):
        ops.append({
            "op": "add_track",
            "track": {"track_id": track_id, "kind": "visual", "role": role, "order": order, "clips": []},
        })

    def video_object(object_id: str, layout: dict[str, float], fit: str, muted: bool) -> dict[str, Any]:
        return {
            "kind": "video",
            "object_id": object_id,
            "layout": layout,
            "fit": fit,
            "transform": {"x": 0.0, "y": 0.0, "scale": 1.0, "rotation": 0.0, "origin": "center"},
            "opacity": 1.0,
            "gain_db": 0.0,
            "muted": muted,
        }

    ops.extend([
        {
            "op": "add_clip",
            "track_id": "trk_background",
            "clip": {
                "clip_id": "clp_background",
                "range": output_range,
                "scene_id": scene_id,
                "source": source,
                "object": video_object(
                    "obj_background",
                    {"x": 0.0, "y": 0.0, "width": float(width), "height": float(height)},
                    "cover",
                    True,
                ),
                "animations": [],
            },
        },
        {
            "op": "add_clip",
            "track_id": "trk_video",
            "clip": {
                "clip_id": "clp_video",
                "range": output_range,
                "scene_id": scene_id,
                "source": source,
                "object": video_object(
                    "obj_video",
                    {
                        "x": width * 0.14,
                        "y": height * 0.18,
                        "width": width * 0.72,
                        "height": height * 0.62,
                    },
                    "contain",
                    not direction.include_original_audio,
                ),
                "animations": [],
            },
        },
    ])
    title_id = "obj_title"
    ops.append({
        "op": "add_clip",
        "track_id": "trk_title",
        "clip": {
            "clip_id": "clp_title",
            "range": output_range,
            "scene_id": scene_id,
            "source": None,
            "object": {
                "kind": "text",
                "object_id": title_id,
                "text": direction.title,
                "layout": {"x": width * 0.08, "y": height * 0.045, "width": width * 0.84, "height": height * 0.11},
                "style": {
                    "font_size": max(30, round(width * 0.04)),
                    "color": "#F8FAFC",
                    "background": None,
                    "weight": 700,
                    "align": "center",
                    "line_height": 1.15,
                },
                "transform": {"x": 0.0, "y": 0.0, "scale": 1.0, "rotation": 0.0, "origin": "center"},
                "opacity": 1.0,
            },
            "animations": [],
        },
    })
    for index, caption in enumerate(direction.captions, start=1):
        start = seconds_to_ticks(caption.start_seconds, timebase)
        end = seconds_to_ticks(caption.end_seconds, timebase)
        ops.append({
            "op": "add_clip",
            "track_id": "trk_caption",
            "clip": {
                "clip_id": f"clp_caption_{index}",
                "range": {"start": start, "end": end},
                "scene_id": scene_id,
                "source": None,
                "object": {
                    "kind": "text",
                    "object_id": f"obj_caption_{index}",
                    "text": caption.text.strip(),
                    "layout": {"x": width * 0.12, "y": height * 0.86, "width": width * 0.76, "height": height * 0.09},
                    "style": {
                        "font_size": max(24, round(width * 34 / 1920)),
                        "color": "#FFFFFF",
                        "background": "#000000",
                        "weight": 600,
                        "align": "center",
                        "line_height": 1.3,
                    },
                    "transform": {"x": 0.0, "y": 0.0, "scale": 1.0, "rotation": 0.0, "origin": "center"},
                    "opacity": 1.0,
                },
                "animations": [],
            },
        })
    if music_bed is not None:
        ops.extend(instantiate_music_bed(music_bed, total_ticks=duration, timebase=timebase))
    return ops
