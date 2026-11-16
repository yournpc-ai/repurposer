"""Current video Director contracts and whole-answer validation."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from app.editing.schemas import REMOTION_RESOURCE_LIMIT, RemotionResource
from app.editing.timing import SOURCE_TIMEBASE

class MgShapeAnswer(BaseModel):
    """One native decorative primitive in normalized canvas coordinates."""

    model_config = ConfigDict(extra="forbid")

    shape: Literal["rect", "ellipse"] = Field(validation_alias=AliasChoices("shape", "type"))
    x: float = Field(ge=-0.25, le=1.0)
    y: float = Field(ge=-0.25, le=1.0)
    width: float = Field(gt=0, le=1.5)
    height: float = Field(gt=0, le=1.5)
    fill: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    opacity: float = Field(default=1.0, gt=0, le=1)
    corner_radius: float = Field(default=0.0, ge=0, le=200)
    motion: Literal["fade", "rise", "scale", "rotate"] = "fade"


class MgTextBeat(BaseModel):
    """An independently timed native text block, in source reading order."""

    model_config = ConfigDict(extra="forbid")

    lines: list[str] = Field(min_length=1, max_length=3)
    start_seconds: float = Field(default=0, ge=0)
    end_seconds: float = Field(gt=0)
    x: float = Field(default=0.08, ge=0, le=1)
    y: float = Field(default=0.3, ge=0, le=1)
    width: float = Field(default=0.84, gt=0, le=1)
    height: float = Field(default=0.4, gt=0, le=1)
    font_size: int = Field(default=72, ge=24, le=200)
    weight: Literal[400, 500, 600, 700, 800, 900] = 700
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    align: Literal["left", "center", "right"] = "left"
    enter: Literal["fade", "rise", "lines", "words", "graphemes"] = "rise"
    drift: Literal["none", "push_in", "pull_out"] = "none"


class NativeTextSceneAnswer(BaseModel):
    """Shared fields implemented by both native text scene compilers."""

    model_config = ConfigDict(extra="forbid")

    intent: str = Field(default="", max_length=120)
    visual_description: str | None = Field(default=None, description="A short sentence describing the actual saved picture and motion.")
    duration_seconds: float = Field(gt=0, le=30)
    lines: list[str] = Field(default=[], max_length=3)
    narration: str | None = Field(
        default=None,
        max_length=9000,
        description="Exact spoken copy for this scene; null only when narration is off.",
    )
    size: Literal["medium", "large", "hero"] = "large"
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    enter: Literal["fade", "rise", "lines", "words", "graphemes"] = "rise"
    drift: Literal["none", "push_in", "pull_out"] = "none"
    align: Literal["left", "center", "right"] = "center"
    shapes: list[MgShapeAnswer] = Field(default=[], max_length=4)


class MgSceneAnswer(NativeTextSceneAnswer):
    """Motion graphics additionally compiles independently timed text beats."""

    text_beats: list[MgTextBeat] = Field(default=[], max_length=12)


class MgDirection(BaseModel):
    """The MG director's answer — text scenes over a solid field."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None)
    language: str | None = None
    background: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    scenes: list[MgSceneAnswer] = Field(min_length=1, max_length=6)


class ComponentFileAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    content: str = Field(min_length=1, max_length=24000)


class ComponentProjectAnswer(BaseModel):
    """The complete authored project, without scene/native-content metadata."""

    model_config = ConfigDict(extra="forbid")

    entry: str = "src/index.tsx"
    composition_id: str = "GeneratedVisual"
    files: list[ComponentFileAnswer] = Field(min_length=2, max_length=24)
    props: dict[str, Any] = Field(default={}, max_length=32)
    props_schema: dict[str, Any]
    resources: list[RemotionResource] = Field(default=[], max_length=REMOTION_RESOURCE_LIMIT)


class AlignedGeneratorAnswer(BaseModel):
    """Agent-authored visual source; the server owns its output window."""

    model_config = ConfigDict(extra="forbid")

    producer: Literal["draw-2d", "remotion-project"] = "draw-2d"
    parameters: dict[str, str | float | bool] = Field(default={}, max_length=24)
    code: str | None = Field(default=None, min_length=1, max_length=24000)
    project: ComponentProjectAnswer | None = None

    @model_validator(mode="after")
    def _complete_source(self) -> AlignedGeneratorAnswer:
        if self.producer == "draw-2d":
            if self.code is None or self.project is not None:
                raise ValueError("draw-2d needs code and no project")
        elif self.project is None or self.code is not None or self.parameters:
            raise ValueError("remotion-project needs a complete project and no draw-2d fields")
        return self


class AlignedNarrationSceneAnswer(BaseModel):
    """Native visual direction for real sentence ids; timing stays server-owned."""

    model_config = ConfigDict(extra="forbid")

    sentence_ids: list[str] = Field(min_length=1, max_length=100)
    intent: str = Field(default="", max_length=120)
    visual_description: str | None = Field(default=None, max_length=240)
    lines: list[str] = Field(min_length=1, max_length=3)
    size: Literal["medium", "large", "hero"] = "large"
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    enter: Literal["fade", "rise", "lines", "words", "graphemes"] = "rise"
    drift: Literal["none", "push_in", "pull_out"] = "none"
    align: Literal["left", "center", "right"] = "center"
    shapes: list[MgShapeAnswer] = Field(default=[], max_length=4)
    generator: AlignedGeneratorAnswer | None = None


class AlignedNarrationDirection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=24)
    language: str | None = None
    background: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    scenes: list[AlignedNarrationSceneAnswer] = Field(min_length=1, max_length=6)


class ProgramDirection(BaseModel):
    """The controlled visual-program consumer (draw-2d)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=24)
    language: str | None = None
    title: str | None = Field(default=None, max_length=100)
    intent: str = Field(min_length=1, max_length=120)
    visual_description: str | None = Field(default=None, max_length=240)
    duration_seconds: float = Field(gt=0, le=30)
    background: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    parameters: dict[str, str | float | bool] = Field(default={}, max_length=24)
    code: str = Field(min_length=1, max_length=24000)


class ComponentDirection(ComponentProjectAnswer):
    """One authored Remotion scene plus independent native title."""

    name: str | None = Field(default=None, max_length=24)
    language: str | None = None
    title: str | None = Field(default=None, max_length=100)
    intent: str = Field(min_length=1, max_length=120)
    visual_description: str | None = Field(default=None, max_length=240)
    duration_seconds: float = Field(gt=0, le=30)
    background: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class ComponentSceneDirection(ComponentDirection):
    """One code-driven scene in a complete animated work."""

    narration: str | None = Field(default=None, max_length=9000)


class ComponentVideoDirection(BaseModel):
    """A coherent sequence of code-driven scenes on the ordinary timeline."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=24)
    language: str | None = None
    scenes: list[ComponentSceneDirection] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def _bounded_work(self) -> ComponentVideoDirection:
        if sum(scene.duration_seconds for scene in self.scenes) > 118:
            raise ValueError("a code-driven work stays within the 118-second design budget")
        return self


class GeneratedImageDirection(BaseModel):
    """The first model-image consumer: one background request plus native copy."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=24)
    language: str | None = None
    title: str | None = Field(default=None, max_length=100)
    intent: str = Field(min_length=1, max_length=120)
    visual_description: str | None = Field(default=None, max_length=240)
    duration_seconds: float = Field(gt=0, le=6)
    prompt: str = Field(min_length=1, max_length=2000)


class MixedCaptionAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=120)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)


class MixedDirection(BaseModel):
    """A real recording with native title/captions and synchronized sound."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=24)
    language: str | None = None
    source_snapshot_id: UUID
    source_start_seconds: float = Field(ge=0)
    source_end_seconds: float = Field(gt=0)
    title: str = Field(min_length=1, max_length=100)
    intent: str = Field(min_length=1, description="The scene's purpose, in plain language.")
    visual_description: str | None = Field(default=None, description="A short sentence describing the actual saved picture and motion.")
    captions: list[MixedCaptionAnswer] = Field(default=[], max_length=16)
    include_original_audio: bool = True


# ---------------------------------------------------------------------------
# Resolution: director answer + bound manifests → DesignSlots, or the honest
# violation list that rides back as the repair round's feedback.
# ---------------------------------------------------------------------------


class DirectionRejected(ValueError):
    """The director's answer failed grounding; ``violations`` are the
    repair feedback's content (model-facing, one per line)."""

    def __init__(self, violations: list[str]) -> None:
        super().__init__("; ".join(violations))
        self.violations = violations


def validate_mg_direction(direction: MgDirection, *, source_text: str | None = None,
                          scene_count: int | None = None, target_seconds: float | None = None,
                          narration_text: str | None = None) -> None:
    """The MG answer's whole-answer bounds (total duration cap); scene-level
    shapes are the schema's own job."""
    total = sum(scene.duration_seconds for scene in direction.scenes)
    if scene_count is not None and len(direction.scenes) != scene_count:
        raise DirectionRejected([f"the user requested exactly {scene_count} scenes"])
    if target_seconds is not None and abs(total - target_seconds) > 1 / 30:
        raise DirectionRejected([f"the user requested {target_seconds:g}s, not {total:g}s"])
    if source_text is not None:
        actual = "".join(
            "".join("".join(line for beat in scene.text_beats for line in beat.lines).split())
            if scene.text_beats else "".join("".join(scene.lines).split())
            for scene in direction.scenes
        )
        expected = "".join(source_text.split())
        if actual != expected:
            shared = min(len(expected), len(actual))
            index = next(
                (i for i in range(shared) if expected[i] != actual[i]), shared
            )
            expected_char = expected[index] if index < len(expected) else "<end>"
            actual_char = actual[index] if index < len(actual) else "<end>"
            raise DirectionRejected([
                "on-screen copy must preserve every source character in order; "
                f"first difference at non-space character {index + 1}: "
                f"expected {expected_char!r}, got {actual_char!r} "
                f"(expected {len(expected)} characters, got {len(actual)})"
            ])
    if narration_text is not None:
        actual_narration = "".join(
            "".join((scene.narration or "").split()) for scene in direction.scenes
        )
        if actual_narration != "".join(narration_text.split()):
            raise DirectionRejected(["narration must preserve every supplied character in order"])
    elif any(scene.narration is not None for scene in direction.scenes):
        raise DirectionRejected(["narration is off for this design"])
    if total > 118:
        raise DirectionRejected(
            [f"the scenes total {total:.1f}s — over the 118s cap; shorten or drop a scene"]
        )
    for i, scene in enumerate(direction.scenes, start=1):
        if bool(scene.lines) == bool(scene.text_beats):
            raise DirectionRejected([f"scene {i}: use either lines or text_beats, not both or neither"])
        previous_start = -1.0
        for beat in scene.text_beats:
            if not (previous_start <= beat.start_seconds < beat.end_seconds <= scene.duration_seconds):
                raise DirectionRejected([f"scene {i}: text beats need ordered starts and positive windows within the scene"])
            previous_start = beat.start_seconds
            if beat.x + beat.width > 1.001 or beat.y + beat.height > 1.001:
                raise DirectionRejected([f"scene {i}: text beat layout must fit the canvas"])
            if beat.end_seconds - beat.start_seconds < max(1.2, sum(len(line.strip()) for line in beat.lines) / 8):
                raise DirectionRejected([f"scene {i}: text beat needs more reading time"])
        for line in (line for beat in scene.text_beats for line in beat.lines) if scene.text_beats else scene.lines:
            if len(line.strip()) > 40:
                raise DirectionRejected(
                    [f"scene {i} line is {len(line)} chars (cap 40 — split it into another scene)"]
                )


def validate_aligned_narration_direction(
    direction: AlignedNarrationDirection,
    *,
    sentences: list[tuple[str, str]],
    scene_count: int | None = None,
    require_generator: bool = False,
    component_enabled: bool = False,
) -> None:
    expected_ids = [sentence_id for sentence_id, _ in sentences]
    actual_ids = [sentence_id for scene in direction.scenes for sentence_id in scene.sentence_ids]
    if actual_ids != expected_ids:
        raise DirectionRejected(
            ["sentence_ids must cover every real sentence exactly once, in script order"]
        )
    generators = [scene.generator for scene in direction.scenes if scene.generator is not None]
    if require_generator and len(generators) != 1:
        raise DirectionRejected(["knowledge-explainer needs exactly one explanatory Generator main visual"])
    if len(generators) > 1:
        raise DirectionRejected(["source-aligned narration supports one Generator main visual"])
    if not component_enabled and any(item.producer == "remotion-project" for item in generators):
        raise DirectionRejected(["remotion-project is unavailable in this deployment; use draw-2d"])
    if any(item.producer == "remotion-project" and item.project and item.project.resources for item in generators):
        raise DirectionRejected(["source-aligned component visuals use declared graphics, not external resources"])
    if scene_count is not None and len(direction.scenes) != scene_count:
        raise DirectionRejected([f"the user requested exactly {scene_count} scenes"])
    text_by_id = dict(sentences)
    for index, scene in enumerate(direction.scenes, start=1):
        selected_text = "\n".join(text_by_id[sentence_id] for sentence_id in scene.sentence_ids)
        for line in scene.lines:
            if not line.strip() or len(line.strip()) > 40:
                raise DirectionRejected([f"scene {index} lines must contain 1–40 characters"])
            if line.strip() not in selected_text:
                raise DirectionRejected(
                    [f"scene {index} on-screen lines must be exact fragments of its selected sentences"]
                )


def validate_program_direction(
    direction: ProgramDirection | ComponentDirection,
    *,
    source_text: str | None = None,
    target_seconds: float | None = None,
) -> None:
    if source_text is not None and (direction.title or "").strip() != source_text.strip():
        raise DirectionRejected(
            ["the native title must preserve the supplied on-screen copy exactly"]
        )
    if target_seconds is not None and abs(direction.duration_seconds - target_seconds) > 1 / 30:
        raise DirectionRejected(
            [f"the user requested {target_seconds:g}s, not {direction.duration_seconds:g}s"]
        )


def validate_component_video_direction(
    direction: ComponentVideoDirection,
    *,
    source_text: str | None = None,
    narration_text: str | None = None,
    target_seconds: float | None = None,
    scene_count: int | None = None,
) -> None:
    """Ground the complete code-driven work without flattening its scenes."""
    if scene_count is not None and len(direction.scenes) != scene_count:
        raise DirectionRejected([f"the user requested exactly {scene_count} scenes"])
    duration = sum(scene.duration_seconds for scene in direction.scenes)
    if target_seconds is not None and abs(duration - target_seconds) > 1 / 30:
        raise DirectionRejected(
            [f"the user requested {target_seconds:g}s in total, not {duration:g}s"]
        )
    if source_text is not None:
        actual = "\n".join(
            scene.title.strip() for scene in direction.scenes if scene.title and scene.title.strip()
        )
        if actual != source_text.strip():
            raise DirectionRejected([
                "native scene titles must preserve the supplied on-screen copy exactly, in order"
            ])
    actual_narration = "".join(
        "".join((scene.narration or "").split()) for scene in direction.scenes
    )
    if narration_text is not None:
        if actual_narration != "".join(narration_text.split()):
            raise DirectionRejected([
                "scene narration must preserve every supplied character in order"
            ])
    elif actual_narration:
        raise DirectionRejected(["narration is off for this design"])


def recapturable_web_elements(meta: dict[str, Any]) -> frozenset[str]:
    """DOM relocation capability, distinct from frozen-image visibility."""
    if meta.get("capture_plan"):
        return frozenset()
    selectors: dict[str, set[str]] = {}
    for view in meta.get("views") or []:
        for element in view.get("elements") or []:
            selector = element.get("selector")
            if isinstance(selector, str) and selector and element.get("id"):
                selectors.setdefault(str(element["id"]), set()).add(selector)
    return frozenset(key for key, values in selectors.items() if len(values) == 1)


def validate_generated_image_direction(
    direction: GeneratedImageDirection,
    *,
    source_text: str | None = None,
    target_seconds: float | None = None,
) -> None:
    if source_text is not None and (direction.title or "").strip() != source_text.strip():
        raise DirectionRejected(
            ["the native title must preserve the supplied on-screen copy exactly"]
        )
    if target_seconds is not None and abs(direction.duration_seconds - target_seconds) > 1 / 15:
        raise DirectionRejected(
            [f"the user requested {target_seconds:g}s, not {direction.duration_seconds:g}s"]
        )


def resolve_mixed_direction(
    direction: MixedDirection,
    *,
    snapshot_facts: dict[UUID, dict],
    target_seconds: float | None = None,
) -> MixedDirection:
    """Resolve a mixed design against the frozen source's real media facts."""
    violations: list[str] = []
    facts = snapshot_facts.get(direction.source_snapshot_id)
    if facts is None or facts.get("kind") != "video":
        violations.append("source_snapshot_id must name one of the supplied video snapshots")
        duration = 0.0
    else:
        duration = float(facts.get("duration_ticks") or 0) / SOURCE_TIMEBASE
        if duration <= 0:
            violations.append("the selected video snapshot has no probed duration")
    output_seconds = direction.source_end_seconds - direction.source_start_seconds
    if output_seconds <= 0:
        violations.append("source_end_seconds must be after source_start_seconds")
    if direction.source_end_seconds > duration + 1 / SOURCE_TIMEBASE:
        violations.append(f"the source window ends past the recording's real {duration:.3f}s duration")
    if output_seconds > 118:
        violations.append("the selected source window exceeds the 118s production limit")
    if target_seconds is not None and abs(output_seconds - target_seconds) > 1 / 30:
        violations.append(f"the user requested {target_seconds:g}s, not {output_seconds:g}s")
    if not direction.title.strip():
        violations.append("title must not be blank")
    captions = sorted(direction.captions, key=lambda item: (item.start_seconds, item.end_seconds))
    previous_end = 0.0
    for index, caption in enumerate(captions, start=1):
        if not caption.text.strip():
            violations.append(f"caption {index} is blank")
        if caption.end_seconds <= caption.start_seconds:
            violations.append(f"caption {index} has a reversed window")
        if caption.start_seconds < previous_end:
            violations.append(f"caption {index} overlaps the previous caption")
        if caption.end_seconds > output_seconds + 1 / SOURCE_TIMEBASE:
            violations.append(f"caption {index} ends past the selected source window")
        previous_end = caption.end_seconds
    if violations:
        raise DirectionRejected(violations)
    has_audio = bool(((facts or {}).get("meta") or {}).get("media", {}).get("has_audio"))
    return direction.model_copy(
        update={
            "title": direction.title.strip(),
            "captions": captions,
            "include_original_audio": direction.include_original_audio and has_audio,
        }
    )
