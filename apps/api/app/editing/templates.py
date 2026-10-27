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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.editing.animation import derive_text_parts
from app.editing.grounding import camera_keyframes
from app.editing.timing import seconds_to_ticks

_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

# Easing the presets use (the LLM never writes bezier numbers).
_EASE_OUT = (0.16, 1.0, 0.3, 1.0)

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


def _music_bed_ops(
    template: VideoTemplate,
    bed: MusicBed,
    *,
    total_ticks: int,
    timebase: int,
) -> list[dict[str, Any]]:
    """The bed's op batch: the template's audio track + whole-film global
    clips tiling the pinned music bytes (a loop longer than the source is
    re-stated as sequential 1× clips — the validator's own law), with the
    template's gain and fade shape."""
    track = next(
        (t for t in template.tracks if t.get("kind") == "audio"), None
    )
    if track is None or bed.duration_ticks <= 0 or total_ticks <= 0:
        return []
    cfg = template.music or {}
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


def instantiate_template(
    template: VideoTemplate,
    slots: DesignSlots,
    views: list[ViewFact],
    *,
    music_bed: MusicBed | None = None,
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
                    font_size=36, color="#F8FAFC", weight=600, align="center",
                    line_height=1.25, background="#111827",
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


def instantiate_mg(direction: Any, *, aspect: str = "16:9", background: str | None = None) -> list[dict[str, Any]]:
    """The MG director's validated answer → the create-path op batch.
    ``direction`` is editing/director.py's MgDirection (imported as Any to
    keep this module's import graph one-directional)."""
    canvas = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}[aspect]
    timebase = 90000
    fps_num, fps_den = 30, 1
    background = background or direction.background or "#0B1020"
    frame_ticks = seconds_to_ticks(fps_den / fps_num, timebase)

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
                    "speech_clip_ids": [],
                },
            }
        )
        text = "\n".join(line.strip() for line in scene.lines if line.strip())
        font_size = _MG_FONT_SIZES[scene.size]
        block_height = max(len(scene.lines), 1) * font_size * 1.15
        layout = {
            "x": 120.0,
            "y": max(120.0, (canvas[1] - block_height) / 2),
            "width": float(canvas[0] - 240),
            "height": block_height * 1.25,
        }
        object_id = f"obj_mg_{index}"
        ops.append(
            {
                "op": "add_clip",
                "track_id": "trk_title",
                "clip": {
                    "clip_id": f"clp_mg_{index}",
                    "range": {"start": cursor, "end": cursor + duration},
                    "scene_id": scene_id,
                    "source": None,
                    "object": {
                        "kind": "text",
                        "object_id": object_id,
                        "text": text,
                        "layout": layout,
                        "style": {
                            "font_size": font_size,
                            "color": scene.color or "#F8FAFC",
                            "background": None,
                            "weight": 700,
                            "align": scene.align,
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
                    "animations": _mg_animations(
                        scene.enter,
                        object_id=object_id,
                        text=text,
                        clip_ticks=duration,
                        timebase=timebase,
                        prefix=f"anm_mg_{index}",
                    ),
                },
            }
        )
        cursor += duration
    return ops
