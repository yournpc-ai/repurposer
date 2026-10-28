"""CompositionVersion content schemas (VIDEO_PROJECT §2–§6).

The four JSONB columns of a ``composition_versions`` row (settings / sources
/ scenes / timeline) serialize from ``CompositionContent`` — this module is
the single shape law for what a version may carry. Current scope: Text /
Shape / Image / Web / Video / Audio / Speech objects over visual + audio
tracks; Transitions are a declared empty list (a non-empty one is an honest
"unsupported", not silent data loss). Pending Speech carries its reviewed
script and voice, never fabricated source media.

Three time domains stay name-separated (§6.1):
- Output time:  ``Scene.range`` / ``Clip.range`` — ticks at ``settings.timebase``.
- Source time:  ``ClipSource.source_range`` — ticks at ``timing.SOURCE_TIMEBASE``.
- Clip-local:   ``Keyframe.at`` — ticks at ``settings.timebase``, zero at the
  clip's own start; it travels when the clip moves.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.editing.fonts import FONT_ID, FONT_SET_DIGEST, LAYOUT_VERSION, SEGMENTATION_VERSION
from app.editing.timing import DEFAULT_TIMEBASE

SCHEMA_VERSION = 1

_ID = Field(min_length=1, max_length=64)
_HEX_COLOR = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class Fps(BaseModel):
    """Rational frame rate: 30/1 today; 30000/1001 stays expressible."""

    model_config = ConfigDict(extra="forbid")

    num: int = Field(default=30, gt=0)
    den: int = Field(default=1, gt=0)


class VersionSettings(BaseModel):
    """Production settings snapshot of one version (§2.1 ``settings``)."""

    model_config = ConfigDict(extra="forbid")

    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: Fps = Fps()
    timebase: int = Field(default=DEFAULT_TIMEBASE, gt=0)
    sample_rate: int = Field(default=48000, gt=0)
    channels: int = Field(default=2, gt=0)
    background: str = Field(default="#000000", pattern=r"^#[0-9a-fA-F]{6}$")


class TimeRange(BaseModel):
    """Half-open ``[start, end)`` in integer ticks (which clock = the field
    the range sits in — see the module docstring's three domains)."""

    model_config = ConfigDict(extra="forbid")

    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def _half_open(self) -> TimeRange:
        if self.end <= self.start:
            raise ValueError("range end must be after start ([start, end))")
        return self

    @property
    def duration(self) -> int:
        return self.end - self.start


class SourceBinding(BaseModel):
    """One immutable SourceSnapshot this version binds (§2.1 ``sources``).

    The digest is pinned INTO the version at bind time (resolved from the
    snapshot row by the write door) — a later refresh of the asset produces
    a new snapshot row and never rewrites this binding.
    """

    model_config = ConfigDict(extra="forbid")

    snapshot_id: UUID
    snapshot_digest: str = Field(min_length=64, max_length=64)


class ClipSource(BaseModel):
    """A clip's media source: one bound snapshot + an optional source window.

    ``source_range`` exists only for time-based media (audio/video). Static
    sources (image, static webpage views) never carry one — their display
    length is the clip's own output range (§4.2: no fabricated source windows).
    """

    model_config = ConfigDict(extra="forbid")

    snapshot_id: UUID
    snapshot_digest: str = Field(min_length=64, max_length=64)
    source_range: TimeRange | None = None


class LayoutBox(BaseModel):
    """The static box in canvas pixels (§4.3: layout owns the box)."""

    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class Transform(BaseModel):
    """Relative to the layout box (§4.3: never a second absolute truth)."""

    model_config = ConfigDict(extra="forbid")

    x: float = 0.0
    y: float = 0.0
    scale: float = Field(default=1.0, gt=0)
    rotation: float = 0.0  # degrees
    origin: Literal["center", "top_left"] = "center"


class FontRef(BaseModel):
    """Immutable font-set identity; the compiler resolves concrete files."""

    model_config = ConfigDict(extra="forbid")

    font_id: str = FONT_ID
    digest: str = FONT_SET_DIGEST


class TextStyle(BaseModel):
    """Closed text style set (no free CSS — §11.1 spec law)."""

    model_config = ConfigDict(extra="forbid")

    font_size: int = Field(gt=0, le=400)
    color: str = _HEX_COLOR
    background: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    weight: Literal[400, 500, 600, 700, 800] = 600
    align: Literal["left", "center", "right"] = "left"
    line_height: float = Field(default=1.2, gt=0)
    font: FontRef = FontRef()


class CaptionDerivation(BaseModel):
    """A caption's editable link to the reviewed SpeechObject text.

    Actual cue times are execution facts, not version mutations. ``derived``
    captions follow Speech edits; ``independent`` preserves a user's manual
    text until an explicit sync operation re-links it.
    """

    model_config = ConfigDict(extra="forbid")

    speech_object_id: str = _ID
    source_text_digest: str = Field(min_length=64, max_length=64)
    alignment: Literal["minimax-t2a-v2-sentence-v1"]
    state: Literal["derived", "independent"] = "derived"


def speech_text_digest(text: str) -> str:
    """Exact reviewed-text identity (whitespace is content, not normalized away)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class TextObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["text"]
    object_id: str = _ID
    text: str = Field(min_length=1)
    layout: LayoutBox
    style: TextStyle
    transform: Transform = Transform()
    opacity: float = Field(default=1.0, ge=0, le=1)
    segmentation_version: str = SEGMENTATION_VERSION
    layout_version: str = LAYOUT_VERSION
    caption: CaptionDerivation | None = None


class ImageObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["image"]
    object_id: str = _ID
    layout: LayoutBox
    fit: Literal["cover", "contain"] = "cover"
    transform: Transform = Transform()
    opacity: float = Field(default=1.0, ge=0, le=1)


class WebObject(BaseModel):
    """One static view of an immutable webpage snapshot.

    Camera motion uses the same transform animations as other visual objects;
    the view itself has no fabricated source-time window.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["web"]
    object_id: str = _ID
    view_id: str = _ID
    layout: LayoutBox
    fit: Literal["cover", "contain"] = "cover"
    transform: Transform = Transform()
    opacity: float = Field(default=1.0, ge=0, le=1)


class VideoObject(BaseModel):
    """One real video window and its synchronized original audio.

    The picture and source audio share this Clip's source/output windows;
    muting never creates or removes a second audio clip.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["video"]
    object_id: str = _ID
    layout: LayoutBox
    fit: Literal["cover", "contain"] = "contain"
    transform: Transform = Transform()
    opacity: float = Field(default=1.0, ge=0, le=1)
    gain_db: float = Field(default=0.0, ge=-60, le=12)
    muted: bool = False


class ShapeObject(BaseModel):
    """One native vector primitive; path data is geometry, never renderer code."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["shape"]
    object_id: str = _ID
    shape: Literal["rect", "ellipse", "path"]
    layout: LayoutBox
    fill: str | None = Field(default="#FFFFFF", pattern=r"^#[0-9a-fA-F]{6}$")
    stroke: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    stroke_width: float = Field(default=0.0, ge=0, le=200)
    corner_radius: float = Field(default=0.0, ge=0, le=1000)
    path: str | None = Field(default=None, max_length=4096)
    transform: Transform = Transform()
    opacity: float = Field(default=1.0, ge=0, le=1)

    @model_validator(mode="after")
    def _geometry_matches_shape(self) -> ShapeObject:
        if self.shape == "path":
            if not self.path or not re.fullmatch(
                r"[MmLlHhVvCcQqZz0-9eE+\-.,\s]+", self.path
            ):
                raise ValueError("path shapes need numeric M/L/H/V/C/Q/Z path data")
        elif self.path is not None:
            raise ValueError("only path shapes carry path data")
        if self.shape != "rect" and self.corner_radius:
            raise ValueError("corner_radius belongs to rect shapes")
        return self


class ProgramOutput(BaseModel):
    """Fixed raster constraints for one short controlled visual program."""

    model_config = ConfigDict(extra="forbid")

    width: int = Field(ge=16, le=1920)
    height: int = Field(ge=16, le=1920)
    fps: int = Field(default=15, gt=0, le=60)
    duration_frames: int = Field(gt=0, le=180)
    background: str = _HEX_COLOR

    @model_validator(mode="after")
    def _even_raster(self) -> ProgramOutput:
        if self.width % 2 or self.height % 2:
            raise ValueError("program output dimensions must be even for H.264")
        return self


class GeneratedImageOutput(BaseModel):
    """The single image-generation output constraint consumed by B-V."""

    model_config = ConfigDict(extra="forbid")

    aspect_ratio: Literal["16:9"] = "16:9"


class GeneratorObject(BaseModel):
    """A reviewable program or model request; production resolves fixed media."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["generator"]
    object_id: str = _ID
    runtime: Literal["drawing-v1", "image-v1"] = "drawing-v1"
    code: str | None = Field(default=None, min_length=1, max_length=24000)
    prompt: str | None = Field(default=None, min_length=1, max_length=2000)
    provider: Literal["minimax"] | None = None
    model: Literal["image-01"] | None = None
    parameters: dict[str, str | float | bool] = Field(default={}, max_length=24)
    output: ProgramOutput | GeneratedImageOutput
    layout: LayoutBox
    fit: Literal["cover", "contain"] = "cover"
    transform: Transform = Transform()
    opacity: float = Field(default=1.0, ge=0, le=1)

    @model_validator(mode="after")
    def _bounded_parameters(self) -> GeneratorObject:
        for key, value in self.parameters.items():
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,39}", key):
                raise ValueError("program parameter keys use letters, digits and underscores")
            if isinstance(value, str) and len(value) > 128:
                raise ValueError("program string parameters stay within 128 characters")
        if self.runtime == "drawing-v1":
            if self.code is None or not isinstance(self.output, ProgramOutput):
                raise ValueError("drawing-v1 needs code and program output constraints")
            if self.prompt is not None or self.provider is not None or self.model is not None:
                raise ValueError("drawing-v1 does not take model-generation fields")
        else:
            if (
                self.prompt is None
                or self.provider != "minimax"
                or self.model != "image-01"
                or not isinstance(self.output, GeneratedImageOutput)
            ):
                raise ValueError("image-v1 needs a MiniMax image-01 prompt and image output")
            if self.code is not None or self.parameters:
                raise ValueError("image-v1 exposes only its prompt and declared image output")
        return self

    def program_digest(self) -> str:
        if self.runtime == "drawing-v1":
            # Preserve the drawing-v1 identity byte-for-byte across the image extension.
            payload = {
                "runtime": self.runtime,
                "code": self.code,
                "parameters": self.parameters,
                "output": self.output.model_dump(mode="json"),
            }
        else:
            payload = {
                "runtime": self.runtime,
                "prompt": self.prompt,
                "provider": self.provider,
                "model": self.model,
                "parameters": self.parameters,
                "output": self.output.model_dump(mode="json"),
            }
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class AudioObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["audio"]
    object_id: str = _ID
    gain_db: float = Field(default=0.0, ge=-60, le=12)


class SpeechObject(BaseModel):
    """Reviewed narration; production resolves it into ordinary audio."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["speech"]
    object_id: str = _ID
    text: str = Field(min_length=1, max_length=9000)
    provider: Literal["minimax"] = "minimax"
    model: Literal["speech-2.6-hd"] = "speech-2.6-hd"
    voice_id: str = Field(min_length=1, max_length=255)
    language: str = Field(min_length=2, max_length=16)
    gain_db: float = Field(default=0.0, ge=-60, le=12)

    @model_validator(mode="after")
    def _nonblank_script(self) -> SpeechObject:
        if not self.text.strip():
            raise ValueError("speech text must not be blank")
        return self


Object = Annotated[
    TextObject | ShapeObject | ImageObject | WebObject | VideoObject
    | GeneratorObject | AudioObject | SpeechObject,
    Field(discriminator="kind"),
]


class Easing(BaseModel):
    """Segment easing (§5.1): an easing belongs to the segment FROM this
    keyframe TO the next; ``hold`` keeps the value until the next keyframe,
    then jumps."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["linear", "hold", "cubic_bezier"] = "linear"
    # Cubic-bezier control points (x1, y1, x2, y2); required iff kind asks.
    params: tuple[float, float, float, float] | None = None

    @model_validator(mode="after")
    def _params_when_bezier(self) -> Easing:
        if self.kind == "cubic_bezier" and self.params is None:
            raise ValueError("cubic_bezier easing requires params (x1, y1, x2, y2)")
        if self.kind != "cubic_bezier" and self.params is not None:
            raise ValueError(f"{self.kind} easing takes no params")
        if self.params is not None and not (0 <= self.params[0] <= 1 and 0 <= self.params[2] <= 1):
            raise ValueError("cubic_bezier x control points must stay in [0, 1]")
        return self


class Keyframe(BaseModel):
    """``at`` is CLIP-LOCAL ticks (settings.timebase, 0 = clip start)."""

    model_config = ConfigDict(extra="forbid")

    at: int = Field(ge=0)
    # Scalar for opacity/scale/rotation/gain; [x, y] for transform.position.
    value: float | tuple[float, float]
    easing: Easing = Easing()


AnimatableProperty = Literal[
    "opacity",
    "transform.position",
    "transform.scale",
    "transform.rotation",
    "audio.gain",
]


class TextPartTarget(BaseModel):
    """Explicit derived-part targets plus clip-local stagger ticks.

    IDs are content/range addressed, never array indexes. A text edit that
    invalidates one is rejected instead of re-pointing the animation silently.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["line", "word", "grapheme"]
    part_ids: list[str] = Field(min_length=1)
    stagger: int = Field(default=0, ge=0)


class Animation(BaseModel):
    """One property track on one object or its derived TextParts."""

    model_config = ConfigDict(extra="forbid")

    animation_id: str = _ID
    target_object_id: str = _ID
    text_part: TextPartTarget | None = None
    property: AnimatableProperty
    keyframes: list[Keyframe] = Field(min_length=1)


class Clip(BaseModel):
    """The unified edit item on a track (§4.2) — time + source + object."""

    model_config = ConfigDict(extra="forbid")

    clip_id: str = _ID
    range: TimeRange  # OUTPUT time (ticks at settings.timebase)
    scene_id: str | None = None
    source: ClipSource | None = None
    object: Object
    animations: list[Animation] = []


TrackKind = Literal["visual", "audio"]
TrackRole = Literal["main", "title", "caption", "dialogue", "music", "effect"]


class Track(BaseModel):
    """A track spans the whole timeline (§4.1); visual ``order`` decides the
    stacking (lower order paints first / sits at the bottom)."""

    model_config = ConfigDict(extra="forbid")

    track_id: str = _ID
    kind: TrackKind
    role: TrackRole
    order: int = Field(ge=0)
    clips: list[Clip] = []


class Scene(BaseModel):
    """Narrative range over output time (§3.1); never a track container."""

    model_config = ConfigDict(extra="forbid")

    scene_id: str = _ID
    range: TimeRange  # OUTPUT time
    intent: str = ""
    visual_description: str | None = None
    speech_clip_ids: list[str] = []


class Timeline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tracks: list[Track] = []
    # First slice: declared, always empty — a non-empty list is an honest
    # "transitions unsupported yet" rejection, never silent data loss.
    transitions: list[dict] = []


class CompositionContent(BaseModel):
    """The full content of one CompositionVersion — the candidate the write
    door validates as a whole before it may land."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    settings: VersionSettings
    sources: list[SourceBinding] = []
    scenes: list[Scene] = []
    timeline: Timeline = Timeline()
