"""CompositionVersion content schemas (VIDEO_PROJECT §2–§6).

The four JSONB columns of a ``composition_versions`` row (settings / sources
/ scenes / timeline) serialize from ``CompositionContent`` — this module is
the single shape law for what a version may carry. Current scope: Text /
Image / Web / Audio objects over visual + audio tracks; Transitions are a
declared empty list (a non-empty one is an honest "unsupported", not silent
data loss). Video / Speech objects remain explicitly unsupported.

Three time domains stay name-separated (§6.1):
- Output time:  ``Scene.range`` / ``Clip.range`` — ticks at ``settings.timebase``.
- Source time:  ``ClipSource.source_range`` — ticks at ``timing.SOURCE_TIMEBASE``.
- Clip-local:   ``Keyframe.at`` — ticks at ``settings.timebase``, zero at the
  clip's own start; it travels when the clip moves.
"""

from __future__ import annotations

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


class AudioObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["audio"]
    object_id: str = _ID
    gain_db: float = Field(default=0.0, ge=-60, le=12)


Object = Annotated[TextObject | ImageObject | WebObject | AudioObject, Field(discriminator="kind")]


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
