"""Director contracts and slot resolution (VIDEO_PROJECT §8.3).

The director LLM answers ONLY the creative slots: which chapters, the exact
citations, the creative-channel copy, camera-target choices and the per-scene
visual descriptions. Structure, timing, layout and camera numbers are code's
(the template's). This module is pure: the Agent declaration and the model
call live in ``app/tools/video/agents.py`` (gate 6a), the assembly data they
render and the answer's resolution into ``DesignSlots`` live here.

Null tolerance: every prose field the model may skip is nullable and reads
as an honest default — a schema rejection is a rejected iteration, never a
streamed half-answer (打字机牙①).
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.editing.grounding import (
    CiteLine,
    ManifestLine,
    detect_plate_cards,
    fit_to_cap,
    manifest_lines,
    resolve_citation,
    resolve_focus,
    strip_edge_connectors,
)
from app.editing.templates import DesignSlots, ViewFact
from app.editing.timing import SOURCE_TIMEBASE

# On-screen copy caps (one law for the factual slots — the launch-film
# craft's reading-time bounds).
TEXT_CAPS: dict[str, tuple[int, str]] = {
    "hero.word": (20, "head"),
    "hero.sub": (90, "head"),
    "reveal.word": (30, "head"),
    "reveal.sub": (90, "head"),
    "end.name": (30, "head"),
    "end.tagline": (90, "head"),
}
_COLD_OPEN_CAP = 24  # ≤3 words (CJK ≈8 glyphs) — enforced as a char bound
_CHAPTER_TITLE_CAP = 20

# The reveal's code-voiced lead-in when the director leaves the slot null
# (the launch languages; anything else falls back to en).
_REVEAL_LEAD = {
    "en": "One more thing.",
    "zh": "还有一件事。",
    "fr": "Encore une chose.",
    "de": "Eine Sache noch.",
    "es": "Una cosa más.",
    "it": "Ancora una cosa.",
}


def reveal_lead_default(language: str | None) -> str:
    return _REVEAL_LEAD.get(
        (language or "en").split("-")[0].split("_")[0].lower(), _REVEAL_LEAD["en"]
    )


class ChapterAnswer(BaseModel):
    """One chapter's creative answer: the cited pillar it tells, its short
    display title, and the walk's camera-target override."""

    model_config = ConfigDict(extra="forbid")

    pillar: CiteLine
    chapter_title: str = Field(min_length=1, max_length=_CHAPTER_TITLE_CAP)
    camera_focus: str | None = Field(
        default=None,
        description="Element id from the walk's assigned view inventory; null = the system's default target.",
    )


class LaunchFilmDirection(BaseModel):
    """The launch-film director's answer (the website-promo design)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, description="The film's display name (≤24 chars); null = the system labels it from the material.")
    language: str | None = Field(default=None, description="The film's language code, declared verbatim.")
    cold_open: list[str] = Field(min_length=1, max_length=3)
    hero_word: CiteLine
    hero_sub: CiteLine
    chapters: list[ChapterAnswer] = Field(min_length=3, max_length=5)
    reveal_lead: str | None = Field(default=None, description="The creative lead-in; null = the code phrase.")
    reveal_word: CiteLine
    reveal_sub: CiteLine
    end_name: CiteLine
    end_tagline: CiteLine
    subtitles: dict[str, str | None] | None = Field(
        default=None,
        description="Visible caption copy keyed by scene key (home / chapter_N_walk / chapter_N_plate / proof); omit keys for scenes that play without a text layer.",
    )
    visual_descriptions: dict[str, str | None] | None = Field(
        default=None,
        description="Per scene key: one plain sentence on what the viewer SEES (elements, motion, camera) — only real elements of the designed scene.",
    )

    @field_validator("subtitles", mode="before")
    @classmethod
    def _fold_subtitle_values(cls, data: Any) -> Any:
        """Read tolerance: a caption spelled as ``{"text": ..., "citation":
        ...}`` or a list of such fragments folds to its plain copy (the
        citation echo is dropped — captions are authored copy, and any
        factual claim inside them is grounded by the scene's own cited
        slots)."""
        if not isinstance(data, dict):
            return data

        def fold_one(value: Any) -> Any:
            if isinstance(value, str) or value is None:
                return value
            if isinstance(value, dict) and isinstance(value.get("text"), str):
                return value["text"]
            if isinstance(value, list):
                parts = [fold_one(item) for item in value]
                if parts and all(isinstance(part, str) for part in parts):
                    text = " ".join(part.strip() for part in parts if part.strip())
                    if text:
                        return text
            return value

        return {key: fold_one(value) for key, value in data.items()}


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


class MgSceneAnswer(BaseModel):
    """One motion-graphics scene (the no-skill free design)."""

    model_config = ConfigDict(extra="forbid")

    intent: str = Field(default="", max_length=120)
    visual_description: str | None = Field(default=None, max_length=240)
    duration_seconds: float = Field(gt=0, le=30)
    lines: list[str] = Field(min_length=1, max_length=3)
    narration: str | None = Field(
        default=None,
        max_length=9000,
        description="Exact spoken copy for this scene; null only when narration is off.",
    )
    size: Literal["medium", "large", "hero"] = "large"
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    enter: Literal["fade", "rise", "lines", "words", "graphemes"] = "rise"
    align: Literal["left", "center", "right"] = "center"
    shapes: list[MgShapeAnswer] = Field(default=[], max_length=4)


class MgDirection(BaseModel):
    """The MG director's answer — text scenes over a solid field."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None)
    language: str | None = None
    background: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    scenes: list[MgSceneAnswer] = Field(min_length=1, max_length=6)


class ProgramDirection(BaseModel):
    """The first controlled visual-program consumer (drawing-v1)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=24)
    language: str | None = None
    title: str | None = Field(default=None, max_length=100)
    intent: str = Field(min_length=1, max_length=120)
    visual_description: str | None = Field(default=None, max_length=240)
    duration_seconds: float = Field(gt=0, le=6)
    background: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    parameters: dict[str, str | float | bool] = Field(default={}, max_length=24)
    code: str = Field(min_length=1, max_length=24000)


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
    intent: str = Field(min_length=1, max_length=120)
    visual_description: str | None = Field(default=None, max_length=240)
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


def _cite(
    lines: list[ManifestLine], ref: CiteLine, slot: str, violations: list[str]
) -> str:
    try:
        text = resolve_citation(lines, ref)
    except ValueError as exc:
        violations.append(f"{slot}: {exc}")
        return ""
    cap, fit = TEXT_CAPS[slot]
    fitted = strip_edge_connectors(fit_to_cap(text, cap, fit))
    if not fitted:
        violations.append(f"{slot}: line L{ref.line} leaves nothing inside the {cap}-char cap")
    return fitted


def _planned_scene_keys(n_chapters: int, plate_chapter: int | None) -> set[str]:
    keys = {"cold_open", "hero", "home", "reveal", "proof", "end"}
    for i in range(1, n_chapters + 1):
        keys.add(f"chapter_{i}_divider")
        keys.add(f"chapter_{i}_walk")
        if plate_chapter == i:
            keys.add(f"chapter_{i}_plate")
    return keys


def resolve_launch_direction(
    direction: LaunchFilmDirection,
    *,
    snapshot_metas: list[dict],
    views: list[ViewFact],
    template_min_views: int,
) -> DesignSlots:
    """Resolve the answer against the bound world. Every citation and every
    camera target is checked; the first bad batch raises DirectionRejected
    with the full violation list (the repair round's feedback)."""
    violations: list[str] = []
    lines = manifest_lines(snapshot_metas)
    if len(views) < template_min_views:
        violations.append(
            f"only {len(views)} usable page views are captured; the arc needs "
            f"at least {template_min_views} — capture more of the page first"
        )
    if not lines:
        violations.append("the captured pages expose no citable text lines")

    hero_word = _cite(lines, direction.hero_word, "hero.word", violations)
    hero_sub = _cite(lines, direction.hero_sub, "hero.sub", violations)
    reveal_word = _cite(lines, direction.reveal_word, "reveal.word", violations)
    reveal_sub = _cite(lines, direction.reveal_sub, "reveal.sub", violations)
    end_name = _cite(lines, direction.end_name, "end.name", violations)
    end_tagline = _cite(lines, direction.end_tagline, "end.tagline", violations)

    cold_open: list[str] = []
    for i, line in enumerate(direction.cold_open):
        cleaned = line.strip()
        if not cleaned:
            violations.append(f"cold_open line {i + 1} is empty")
        elif len(cleaned) > _COLD_OPEN_CAP:
            violations.append(
                f"cold_open line {i + 1} is {len(cleaned)} chars (cap {_COLD_OPEN_CAP} — ≤3 words)"
            )
        else:
            cold_open.append(cleaned)

    n_chapters = len(direction.chapters)
    for i, chapter in enumerate(direction.chapters, start=1):
        try:
            resolve_citation(lines, chapter.pillar)
        except ValueError as exc:
            violations.append(f"chapter {i} pillar: {exc}")

    plate_cards = detect_plate_cards(lines)
    plate_page = (
        max(
            (pages := [card["page"] for card in plate_cards]),
            key=pages.count,
        )
        if plate_cards
        else None
    )
    plate_chapter = None
    if plate_page is not None:
        plate_chapter = next(
            (i for i in range(1, n_chapters + 1) if i < len(views) and views[i].page == plate_page),
            1,
        )
    scene_keys = _planned_scene_keys(n_chapters, plate_chapter)

    # Camera targets: chapter walks + the proof walk, resolved against each
    # assigned view's element inventory.
    focuses: dict[str, dict[str, float] | None] = {}
    for i, chapter in enumerate(direction.chapters, start=1):
        key = f"chapter_{i}_walk"
        if i < len(views):
            try:
                focuses[key] = resolve_focus(views[i].elements, chapter.camera_focus)
            except ValueError as exc:
                violations.append(f"{key}: {exc}")
    if views:
        proof_view = views[-1] if n_chapters + 1 >= len(views) else views[n_chapters + 1]
        focuses["proof"] = resolve_focus(proof_view.elements, None)

    captions: dict[str, str] = {}
    for key, text in (direction.subtitles or {}).items():
        if key not in scene_keys:
            violations.append(f"subtitle for unknown scene {key!r} — no such scene exists")
            continue
        if text and text.strip():
            captions[key] = text.strip()

    visual_descriptions: dict[str, str] = {}
    for key, text in (direction.visual_descriptions or {}).items():
        if key not in scene_keys:
            violations.append(
                f"visual_description for unknown scene {key!r} — describe the designed scenes"
            )
            continue
        if text and text.strip():
            visual_descriptions[key] = text.strip()

    if violations:
        raise DirectionRejected(violations)
    return DesignSlots(
        name=(direction.name or "").strip()[:24] or None,
        language=direction.language,
        cold_open=cold_open,
        hero_word=hero_word,
        hero_sub=hero_sub,
        chapter_titles=[c.chapter_title.strip() for c in direction.chapters],
        reveal_lead=(direction.reveal_lead or "").strip() or reveal_lead_default(direction.language),
        reveal_word=reveal_word,
        reveal_sub=reveal_sub,
        end_name=end_name,
        end_tagline=end_tagline,
        captions=captions,
        visual_descriptions=visual_descriptions,
        camera_focuses=focuses,
        plate_cards=plate_cards,
        plate_page=plate_page,
    )


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
            "".join("".join(scene.lines).split()) for scene in direction.scenes
        )
        if actual != "".join(source_text.split()):
            raise DirectionRejected(["on-screen copy must preserve every source character in order"])
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
        for line in scene.lines:
            if len(line.strip()) > 40:
                raise DirectionRejected(
                    [f"scene {i} line is {len(line)} chars (cap 40 — split it into another scene)"]
                )


def validate_program_direction(
    direction: ProgramDirection,
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
