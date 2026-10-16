"""launch_film node + film storyboard agent + grounding validator (MG D2).

One file, three layers:

1. THE VALIDATOR (pure) — the deterministic gate between the LLM's storyboard
   and the render contract. Every on-screen string must trace to the captured
   page's research manifest (TEXT_NOT_GROUNDED); camera focus bounds
   (INVALID_FOCUS); the scene vocabulary is closed (UNSUPPORTED_SCENE);
   duration intents and content bounds (DURATION_INVALID /
   CONSTRAINT_VIOLATION). Bounded rewrite: the node offers the model at most
   MAX_REWRITES repair rounds (3 candidates total); exhaustion settles the
   node FAILED with the structured codes on ``spec.failure`` — never a blind
   retry (each rewrite rides the violation echo).

2. THE ALLOCATOR (pure) — deterministic frame assignment. The LLM writes a
   bounded seconds INTENT per scene; code owns integer frames (fixed 30 fps,
   structural minimums — the divider roll cadence, the end-card floor — the
   total is Σ scene frames). The renderer only sums.

3. THE NODE — loads the project's READY web_page assets (the birthplace
   ∀-check gates presence, the claim gate gates processing; a mid-run
   capture failure surfaces here as an honest error), drives the bounded
   loop, births the film output (``render_spec.family == "film"``) and pends
   its render through the ONE seat (``pend_outputs_for_render``). No second
   orchestration chain (ADR-028/029).

Grounding normalization: lowercase + every non-word char stripped (markdown
emphasis ``*``, punctuation, whitespace) — a screen string hits the manifest
when its normalized form is a substring of a normalized manifest item
(verbatim quote OR trim). Code-baked chrome is exempt by construction:
divider ordinals, ui/end display URLs, the ui screenshot, the end logo.
"""

from __future__ import annotations

import difflib
import re
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

import structlog
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import bindparam, func, select, text as _text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import Agent, AssembleResult
from app.metering import record_media_usage
from app.models.schemas import (
    AssetStatus,
    AssetType,
    FilmStoryboard,
    MediaInput,
    RenderStatus,
    ShotRef,
    WebPageResearch,
)
from app.models.tables import Asset, Output, Project, WorkflowRun, WorkflowStep
from app.pipeline.graph import WEB_PAGE, NodeBase, estimate_agent
from app.pipeline.outputs import delete_outputs_fk_safe
from app.platform.project_context import resolve_persona
from app.pipeline.render_ownership import pend_outputs_for_render
from app.pipeline.step_context import media_input_for_image
from app.pipeline.step_display import (
    fill_summary,
    node_slot,
    set_spec_field,
    slot_tag,
    ui_lang_of,
)
from app.providers.llm.base import LLMError, LLMSchemaError

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Constants (the contract numbers — the j2 states them as binding bounds, the
# validator enforces them; craft guidance lives in the launch-film pack)
# ---------------------------------------------------------------------------

FILM_FPS = 30  # fixed (render Root.tsx FILM_FPS — one law, mirrored here)
_CAPTURE_SETTLE_WAIT_S = 150.0  # capture settle wait ceiling (draft seat)
_CAPTURE_SETTLE_POLL_S = 2.0
SCENE_COUNT_LIMITS = (4, 16)
TOTAL_SECONDS_RANGE = (30.0, 115.0)
# Render-side frame cap (server.ts FILM_MAX_FRAMES default) — the validator's
# total window stays comfortably under it; this is the post-allocation guard.
FILM_MAX_FRAMES = 3600

# Per-scene seconds intent bounds (the LLM's legal range per type).
SCENE_SECONDS: dict[str, tuple[float, float]] = {
    "words": (1.5, 4.0),
    "hero": (2.0, 5.0),
    "ui": (3.0, 10.0),
    "divider": (2.0, 5.0),
    "plate": (3.0, 7.0),
    "reveal": (2.0, 5.0),
    "end": (2.5, 6.0),
}

# Structural frame minimums (the allocator clamps UP to these — code's seat):
_MIN_SCENE_FRAMES = 30  # 1s — the 7+7 fade veil plus one readable beat
_END_MIN_FRAMES = 75  # 2.5s — the closing card's floor
# The divider roll's cadence: one word per 13 frames (perWord in
# apps/render/src/film/components.tsx — the renderer owns the behavior, this
# mirror exists so the roll always fits its scene).
_DIVIDER_ROLL_STEP_FRAMES = 13
_DIVIDER_ROLL_TAIL_FRAMES = 25  # the last word must land and read

# On-screen copy caps (chars) per (scene type, slot).
TEXT_CAPS: dict[tuple[str, str], int] = {
    ("words", "lines"): 30,
    ("hero", "word"): 16,
    ("hero", "sub"): 90,
    ("divider", "label"): 40,
    ("divider", "roll"): 24,
    ("plate", "title"): 40,
    ("plate", "big"): 8,
    ("plate", "label"): 24,
    ("reveal", "lead"): 60,
    ("reveal", "word"): 24,
    ("reveal", "sub"): 90,
    ("end", "name"): 24,
    ("end", "tagline"): 90,
    ("ui", "captions"): 60,
}
# Per-scene item count caps.
_LIST_CAPS = {"words.lines": 4, "divider.roll": 5, "ui.captions": 3, "ui.focuses": 3, "plate.cards": 4}

# Camera bounds: x/y are normalized frame positions; zoom is a magnification
# (1 = the full frame). The spec's [0,1]³ law covers x/y; zoom lives in [1,4].
_ZOOM_RANGE = (1.0, 4.0)

MAX_REWRITES = 2  # bounded rejection: 3 candidates total, then FAILED

# 简式计价 (D3): the estimate's film_seconds quote. The storyboard's true
# length is unborn at compile time (the LLM writes it mid-run, bounded by
# TOTAL_SECONDS_RANGE), so the quote anchors on the TYPICAL film (the craft
# law's target band is 75-95s). A longer film settles by capture-past-hold,
# a shorter one by release — the ledger's NULL/under-quote semantics already
# carry both directions (BILLING §5); the sticker stays honest instead of
# quoting the validator ceiling over every real charge. The ACTUAL charge is
# the allocated seconds (record_media_usage at birth) — estimate ≡ meter
# reads the same price line.
ESTIMATE_FILM_SECONDS = 85.0

_DEFAULT_THEME = {"canvas": "#F7F6F2", "ink": "#141414"}
_HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

# Error codes (spec.failure.codes + the rewrite echo — the D4 failure
# ledger reads these).
UNSUPPORTED_SCENE = "UNSUPPORTED_SCENE"
TEXT_NOT_GROUNDED = "TEXT_NOT_GROUNDED"
INVALID_FOCUS = "INVALID_FOCUS"
DURATION_INVALID = "DURATION_INVALID"
CONSTRAINT_VIOLATION = "CONSTRAINT_VIOLATION"


class FilmStoryboardRejected(Exception):
    """The bounded rewrite exhausted without a clean storyboard — the node
    settles FAILED with the structured codes on ``spec.failure``."""

    user_key = "film_storyboard_ungrounded"

    def __init__(self, codes: list[str], detail: str) -> None:
        super().__init__(f"storyboard rejected ({', '.join(codes)}): {detail[:300]}")
        self.codes = codes
        self.detail = detail


class LaunchFilmParams(BaseModel):
    """launch_film slot params — the proposal carries a steer, never content."""

    focus: str | None = Field(
        default=None,
        description="Optional emphasis steer for the storyboard (e.g. the "
        "feature or audience the film should lead with). Null = the director "
        "reads the page and picks.",
    )
    voiceover: bool | None = Field(
        default=None,
        description="Spoken narration over the film (配音讲解). Null/true = "
        "narrated; false = silent cut (music bed only). The storyboard "
        "drafts per-scene narration either way so the review table shows "
        "the words; false skips synthesis at render time.",
    )
    music_mood: str | None = Field(
        default=None,
        description="Background-music mood for the bed (e.g. 'calm', "
        "'upbeat', 'cinematic'). Null = the persona's skin default, "
        "falling back to a calm bed.",
    )
    aspect: Literal["16:9", "1:1", "9:16"] | None = Field(
        default=None,
        description="Canvas aspect: '16:9' (default, landscape), '1:1' "
        "(square), or '9:16' (portrait). Null = 16:9.",
    )
    language: str | None = Field(
        default=None,
        description="The film's SPOKEN language (the narration voiceover), "
        "e.g. 'en', 'zh', 'de'. Pin it when the user names one, or when a "
        "named audience implies one ('英国年轻人' → 'en'); an already-captured "
        "page's own language is the next signal. The conversation's own "
        "language is NEVER a source — the film speaks to its audience, not "
        "to the chat. Null = the storyboard declares it from the page.",
    )


@dataclass(frozen=True)
class FilmViolation:
    code: str
    detail: str  # scene index + field + the offending value — echoed verbatim


@dataclass(frozen=True)
class StoryboardPage:
    """One captured page as the storyboard's grounding universe (and the ui
    scene's imagery source). ``screenshot_key`` None = the capture's
    screenshot half degraded — ui scenes pointing here are illegal.
    ``shots`` = the fold + section captures (ADR-121 B1; empty on pre-B1
    rows — the fold-only law then: ui scenes read screenshot_key and their
    ``shot`` must stay 0)."""

    asset_id: str
    research: WebPageResearch
    screenshot_key: str | None
    host: str  # display host baked into the ui/end url fields (code's seat)
    shots: tuple[ShotRef, ...] = ()


# ---------------------------------------------------------------------------
# Grounding helpers (pure)
# ---------------------------------------------------------------------------


def _norm(s: str) -> str:
    """Grounding normalization: lowercase, word chars only (``*`` emphasis,
    punctuation, whitespace all vanish) — a trim of a quote still hits."""
    return re.sub(r"[^\w]+", "", s.lower())


def _corpus_pairs(research: WebPageResearch) -> list[tuple[str, str]]:
    """(normalized, original) grounding pairs — the norm drives matching,
    the original rides the repair echo's nearest-candidate hints."""
    raw = [
        research.title,
        research.description,
        *research.h1,
        *research.h2,
        *research.h3,
        *research.buttons,
        *research.links,
        *research.paragraphs,
    ]
    return [(n, item) for item in raw if (n := _norm(item))]


def _nearest_hint(norm_text: str, pairs: list[tuple[str, str]]) -> str:
    """The repair echo's menu (2026-10-16 zymix 取证 — 打地鼠形态): a
    rejected line told the model WHAT failed but never WHAT was available,
    so each rewrite re-invented on another scene. Up to 3 nearest manifest
    lines (similarity order) turn the blind re-roll into a pick."""
    near = difflib.get_close_matches(
        norm_text, [n for n, _ in pairs], n=3, cutoff=0.25
    )
    if not near:
        return ""
    first: dict[str, str] = {}
    for n, orig in pairs:
        first.setdefault(n, orig.strip())
    return "; closest manifest lines: " + " / ".join(
        f"«{first[n][:80]}»" for n in near
    )


def _screen_strings(scene: Any) -> list[tuple[str, str]]:
    """(slot, text) pairs a scene puts on screen — the grounding surface.
    Code-baked chrome (divider index, ui/end urls, imagery) never appears
    here."""
    t = scene.type
    if t == "words":
        return [("lines", line) for line in scene.lines]
    if t == "hero":
        return [("word", scene.word), ("sub", scene.sub)]
    if t == "ui":
        return [("captions", c.text) for c in scene.captions]
    if t == "divider":
        return [("label", scene.label), *[("roll", w) for w in scene.roll]]
    if t == "plate":
        return [
            ("title", scene.title),
            *[("big", c.big) for c in scene.cards if c.big],
            *[("label", c.label) for c in scene.cards],
        ]
    if t == "reveal":
        return [("lead", scene.lead), ("word", scene.word), ("sub", scene.sub)]
    if t == "end":
        return [("name", scene.name), ("tagline", scene.tagline)]
    return []


# ---------------------------------------------------------------------------
# The validator (pure)
# ---------------------------------------------------------------------------


def validate_storyboard(
    storyboard: FilmStoryboard, pages: list[StoryboardPage]
) -> list[FilmViolation]:
    """Every violation found, in scene order. Empty list = the storyboard may
    proceed to frame allocation. The union corpus grounds every scene except
    ui captions, which ground against the page they show."""
    violations: list[FilmViolation] = []
    union_pairs = [pair for p in pages for pair in _corpus_pairs(p.research)]

    def grounded(text: str, corpus: list[str]) -> bool:
        norm = _norm(text)
        return bool(norm) and any(norm in item for item in corpus)

    scenes = storyboard.scenes
    if not (SCENE_COUNT_LIMITS[0] <= len(scenes) <= SCENE_COUNT_LIMITS[1]):
        violations.append(
            FilmViolation(
                CONSTRAINT_VIOLATION,
                f"scene count {len(scenes)} outside {SCENE_COUNT_LIMITS[0]}..{SCENE_COUNT_LIMITS[1]}",
            )
        )
    # The plate is the numbers beat — rare by law (two would already be a
    # pattern; three is a spreadsheet).
    plates = sum(1 for s in scenes if s.type == "plate")
    if plates > 2:
        violations.append(
            FilmViolation(CONSTRAINT_VIOLATION, f"{plates} plate scenes — at most 2 per film")
        )

    total_seconds = 0.0
    seen_screens: set[tuple[str, tuple[str, ...]]] = set()
    for idx, scene in enumerate(scenes):
        where = f"scene[{idx}]({scene.type})"
        if scene.type not in SCENE_SECONDS:
            # The pydantic union already enforces the closed vocabulary — this
            # is the defense-in-depth seat (a hand-built spec bypassing it).
            violations.append(FilmViolation(UNSUPPORTED_SCENE, f"{where}: unknown type"))
            continue

        lo, hi = SCENE_SECONDS[scene.type]
        if not (lo <= scene.seconds <= hi):
            violations.append(
                FilmViolation(
                    DURATION_INVALID,
                    f"{where}: {scene.seconds}s outside {lo}..{hi}s for {scene.type}",
                )
            )
        total_seconds += scene.seconds

        strings = _screen_strings(scene)
        pairs = (
            _corpus_pairs(pages[scene.page].research)
            if scene.type == "ui" and 0 <= scene.page < len(pages)
            else union_pairs
        )
        corpus = [norm for norm, _ in pairs]
        for slot, text in strings:
            cap = TEXT_CAPS.get((scene.type, "captions" if scene.type == "ui" else slot))
            if cap is not None and len(text) > cap:
                violations.append(
                    FilmViolation(
                        CONSTRAINT_VIOLATION,
                        f"{where}.{slot}: {len(text)} chars over the {cap} cap ({text[:40]}…)",
                    )
                )
            if not _norm(text):
                violations.append(
                    FilmViolation(CONSTRAINT_VIOLATION, f"{where}.{slot}: empty copy")
                )
            elif not grounded(text, corpus):
                violations.append(
                    FilmViolation(
                        TEXT_NOT_GROUNDED,
                        f"{where}.{slot}: «{text[:60]}» traces to no manifest line — quote or trim the page's own copy"
                        + _nearest_hint(_norm(text), pairs),
                    )
                )

        # 配音词 sanity bound (never grounded — speech rephrases the page's
        # facts by design; the T2A fit handles fine timing at synthesis).
        narration = getattr(scene, "narration", None)
        if narration is not None:
            if not _norm(narration):
                violations.append(
                    FilmViolation(CONSTRAINT_VIOLATION, f"{where}.narration: blank")
                )
            else:
                narr_cap = max(60, int(scene.seconds * 20))
                if len(narration) > narr_cap:
                    violations.append(
                        FilmViolation(
                            CONSTRAINT_VIOLATION,
                            f"{where}.narration: {len(narration)} chars over the {narr_cap} cap",
                        )
                    )

        # Within-scene duplicate copy.
        normed = [_norm(text) for _, text in strings]
        if len(set(normed)) != len(normed):
            violations.append(
                FilmViolation(CONSTRAINT_VIOLATION, f"{where}: duplicate copy within one screen")
            )
        # A whole screen repeated elsewhere (same type, same strings).
        signature = (scene.type, tuple(sorted(normed)))
        if signature in seen_screens:
            violations.append(
                FilmViolation(CONSTRAINT_VIOLATION, f"{where}: repeats another scene's screen verbatim")
            )
        seen_screens.add(signature)

        # List-size caps.
        if scene.type == "words" and len(scene.lines) > _LIST_CAPS["words.lines"]:
            violations.append(FilmViolation(CONSTRAINT_VIOLATION, f"{where}: {len(scene.lines)} lines over {_LIST_CAPS['words.lines']}"))
        if scene.type == "divider" and len(scene.roll) > _LIST_CAPS["divider.roll"]:
            violations.append(FilmViolation(CONSTRAINT_VIOLATION, f"{where}: roll of {len(scene.roll)} over {_LIST_CAPS['divider.roll']}"))
        if scene.type == "ui":
            if len(scene.captions) > _LIST_CAPS["ui.captions"]:
                violations.append(FilmViolation(CONSTRAINT_VIOLATION, f"{where}: {len(scene.captions)} captions over {_LIST_CAPS['ui.captions']}"))
            if len(scene.focuses) > _LIST_CAPS["ui.focuses"]:
                violations.append(FilmViolation(CONSTRAINT_VIOLATION, f"{where}: {len(scene.focuses)} focuses over {_LIST_CAPS['ui.focuses']}"))
            if not (0 <= scene.page < len(pages)):
                violations.append(
                    FilmViolation(CONSTRAINT_VIOLATION, f"{where}: page {scene.page} names no presented page")
                )
            elif not pages[scene.page].shots and pages[scene.page].screenshot_key is None:
                violations.append(
                    FilmViolation(
                        CONSTRAINT_VIOLATION,
                        f"{where}: page {scene.page} has no screenshot — a ui scene needs the page image",
                    )
                )
            elif pages[scene.page].shots and not (
                0 <= scene.shot < len(pages[scene.page].shots)
            ):
                violations.append(
                    FilmViolation(
                        CONSTRAINT_VIOLATION,
                        f"{where}: shot {scene.shot} outside the page's {len(pages[scene.page].shots)} captured shots",
                    )
                )
            elif not pages[scene.page].shots and scene.shot != 0:
                # Fold-only capture (pre-B1 rows): shot 0 is the only legal view.
                violations.append(
                    FilmViolation(
                        CONSTRAINT_VIOLATION,
                        f"{where}: shot {scene.shot} but the page has only the fold capture",
                    )
                )
            prev_at = -1.0
            for f in scene.focuses:
                # Two legal forms (ADR-121 B2): element-named (resolves at
                # spec build) or the raw x/y/zoom triple. Never mixed, never
                # neither.
                if f.element is not None:
                    if f.x is not None or f.y is not None or f.zoom is not None:
                        violations.append(
                            FilmViolation(INVALID_FOCUS, f"{where}: focus mixes element {f.element} with raw coordinates — one form only")
                        )
                    elif 0 <= scene.page < len(pages) and pages[scene.page].shots:
                        shot_elements = pages[scene.page].shots[scene.shot].elements if scene.shot < len(pages[scene.page].shots) else []
                        target = next((e for e in shot_elements if e.id == f.element), None)
                        if target is None:
                            violations.append(
                                FilmViolation(INVALID_FOCUS, f"{where}: element {f.element} names nothing in shot {scene.shot}'s inventory")
                            )
                        elif target.covered:
                            violations.append(
                                FilmViolation(INVALID_FOCUS, f"{where}: element {f.element} was covered at capture — pick another target")
                            )
                    else:
                        violations.append(
                            FilmViolation(INVALID_FOCUS, f"{where}: element focus but the page lists no element inventory")
                        )
                else:
                    if f.x is None or f.y is None or f.zoom is None:
                        violations.append(
                            FilmViolation(INVALID_FOCUS, f"{where}: a raw focus needs the full x/y/zoom triple")
                        )
                        continue
                    if not (0.0 <= f.x <= 1.0 and 0.0 <= f.y <= 1.0):
                        violations.append(
                            FilmViolation(INVALID_FOCUS, f"{where}: focus ({f.x}, {f.y}) outside [0,1]")
                        )
                    if not (_ZOOM_RANGE[0] <= f.zoom <= _ZOOM_RANGE[1]):
                        violations.append(
                            FilmViolation(INVALID_FOCUS, f"{where}: zoom {f.zoom} outside {_ZOOM_RANGE[0]}..{_ZOOM_RANGE[1]}")
                        )
                if not (0.0 <= f.at < scene.seconds):
                    violations.append(
                        FilmViolation(INVALID_FOCUS, f"{where}: focus at {f.at}s outside the scene's {scene.seconds}s")
                    )
                if f.at <= prev_at:
                    violations.append(
                        FilmViolation(INVALID_FOCUS, f"{where}: focus beats must ascend (at {f.at} after {prev_at})")
                    )
                prev_at = f.at
            prev_at = -1.0
            for c in scene.captions:
                if not (0.0 <= c.at < scene.seconds):
                    violations.append(
                        FilmViolation(INVALID_FOCUS, f"{where}: caption at {c.at}s outside the scene's {scene.seconds}s")
                    )
                if c.at < prev_at + 0.5:
                    violations.append(
                        FilmViolation(INVALID_FOCUS, f"{where}: captions need 0.5s of air each (at {c.at} after {prev_at})")
                    )
                prev_at = c.at

    if not (TOTAL_SECONDS_RANGE[0] <= total_seconds <= TOTAL_SECONDS_RANGE[1]):
        violations.append(
            FilmViolation(
                DURATION_INVALID,
                f"total {total_seconds:.1f}s outside {TOTAL_SECONDS_RANGE[0]}..{TOTAL_SECONDS_RANGE[1]}s",
            )
        )

    if storyboard.theme is not None:
        for field, value in (("canvas", storyboard.theme.canvas), ("ink", storyboard.theme.ink)):
            if not _HEX_COLOR.match(value):
                violations.append(
                    FilmViolation(CONSTRAINT_VIOLATION, f"theme.{field}: «{value}» is not a hex color")
                )

    return violations


def format_violations(violations: list[FilmViolation]) -> str:
    """The rewrite echo: codes + offenders, compact (this rides the next
    candidate call verbatim — the model fixes what it can read)."""
    lines = [f"- {v.code}: {v.detail}" for v in violations[:12]]
    extra = len(violations) - len(lines)
    if extra > 0:
        lines.append(f"- … and {extra} more")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The allocator + spec builder (pure)
# ---------------------------------------------------------------------------


def _scene_floor(scene: Any) -> int:
    """One scene's structural frame minimum — the divider roll must fit its
    cadence, the end card holds its floor (allocate_frames' clamp, factored
    out so the beat snap respects the same floors)."""
    n = _MIN_SCENE_FRAMES
    if scene.type == "divider":
        n = max(
            n,
            (len(scene.roll) - 1) * _DIVIDER_ROLL_STEP_FRAMES + _DIVIDER_ROLL_TAIL_FRAMES,
        )
    if scene.type == "end":
        n = max(n, _END_MIN_FRAMES)
    return n


def allocate_frames(storyboard: FilmStoryboard) -> list[int]:
    """Seconds intent → integer frames (fixed fps; structural minimums clamp
    UP — the divider roll must fit its cadence, the end card holds its floor).
    Total = Σ scene frames; the renderer only sums."""
    return [
        max(round(scene.seconds * FILM_FPS), _scene_floor(scene))
        for scene in storyboard.scenes
    ]


# Beat snap (ADR-121 B3): scene boundaries move to the bed's nearest beat,
# never farther than this — beyond it the cut stays where the storyboard put
# it (the grid serves the cut, never the other way around).
_BEAT_SNAP_TOLERANCE_S = 0.2


def snap_frames_to_beats(
    storyboard: FilmStoryboard, frames: list[int], beats: list[float]
) -> list[int]:
    """Snap internal scene boundaries to the music bed's beat grid. A snap
    never pushes a scene under its structural floor and never moves a
    boundary past the tolerance; the first scene still starts at 0, the
    total floats within ±tolerance per boundary. No grid → the frames pass
    through untouched (degrade-honest)."""
    if not beats:
        return frames
    tol = round(_BEAT_SNAP_TOLERANCE_S * FILM_FPS)
    beat_frames = [round(b * FILM_FPS) for b in beats]
    floors = [_scene_floor(s) for s in storyboard.scenes]
    out = list(frames)
    boundary = 0
    for i in range(len(out) - 1):
        boundary += out[i]
        nearest = min(beat_frames, key=lambda b: abs(b - boundary))
        delta = nearest - boundary
        if (
            0 < abs(delta) <= tol
            and out[i] + delta >= floors[i]
            and out[i + 1] - delta >= floors[i + 1]
        ):
            out[i] += delta
            out[i + 1] -= delta
            boundary = nearest
    return out


def _resolve_focus(f: Any, page: StoryboardPage, shot_idx: int) -> dict[str, Any]:
    """One focus beat → the spec's {at, x, y, zoom} (ADR-121 B2). An
    element-named beat resolves deterministically: the element's box center,
    zoom framing the box at ~half the canvas (clamped to the zoom law —
    a small button never gets a 4x push). Raw triples pass through. The
    validator bounded both forms; an unresolvable id here means a hand-built
    storyboard bypassed it — degrade to the shot's center, never crash the
    render seat."""
    if f.element is None:
        return {"at": f.at, "x": f.x, "y": f.y, "zoom": f.zoom}
    el = next(
        (e for e in page.shots[shot_idx].elements if e.id == f.element), None
    ) if page.shots and shot_idx < len(page.shots) else None
    if el is None:
        return {"at": f.at, "x": 0.5, "y": 0.5, "zoom": 1.0}
    zoom = min(2.6, max(1.2, 0.5 / max(el.w, el.h, 0.02)))
    return {"at": f.at, "x": el.x, "y": el.y, "zoom": round(zoom, 3)}


def build_film_spec(
    storyboard: FilmStoryboard,
    pages: list[StoryboardPage],
    *,
    narration: dict[int, str] | None = None,
    music: dict[str, Any] | None = None,
    aspect: str = "16:9",
    frames: list[int] | None = None,
) -> dict[str, Any]:
    """The validated storyboard → the persisted film-spec (render contract).

    The ui scene's ``image`` stores the screenshot's RELATIVE object key —
    absolutized at render time by the render chain (the clip path's storage
    seam law; narration ``audio`` keys and the ``music`` bed URL ride the
    same seam). Display URLs / divider ordinals / the end logo are baked
    here, never model-written. ``aspect`` declares the canvas (16:9 / 1:1 /
    9:16) — the renderer's dimensions read it, never a second source.
    ``frames`` = the caller's already-snapped allocation (ADR-121 B3: the
    run snaps to the beat grid before narration so the T2A windows ARE the
    snapped windows); None = allocate here (draft/preview seats).
    """
    narration = narration or {}
    allocated = frames if frames is not None else allocate_frames(storyboard)
    if sum(allocated) > FILM_MAX_FRAMES:
        raise FilmStoryboardRejected(
            [DURATION_INVALID],
            f"allocated {sum(allocated)} frames over the {FILM_MAX_FRAMES} render cap",
        )
    theme = dict(_DEFAULT_THEME)
    if storyboard.theme is not None:
        theme = {"canvas": storyboard.theme.canvas, "ink": storyboard.theme.ink}
    divider_ordinal = 0
    scenes: list[dict[str, Any]] = []
    for idx, (scene, n) in enumerate(zip(storyboard.scenes, allocated, strict=True)):
        if scene.type == "words":
            scenes.append({"type": "words", "frames": n, "dark": scene.dark, "lines": scene.lines})
        elif scene.type == "hero":
            scenes.append({"type": "hero", "frames": n, "word": scene.word, "sub": scene.sub})
        elif scene.type == "ui":
            page = pages[scene.page]
            # ADR-121 B1: the shot picks WHICH captured view of the page
            # (validator bounded it); fold-only pages read screenshot_key.
            image_key = (
                page.shots[scene.shot].key if page.shots else page.screenshot_key
            )
            scenes.append(
                {
                    "type": "ui",
                    "frames": n,
                    "image": image_key,
                    "url": page.host,
                    "frame": scene.frame,
                    # B2: element-named beats resolve here; the `element` key
                    # never leaks into the render contract.
                    "focuses": [
                        _resolve_focus(f, page, scene.shot) for f in scene.focuses
                    ],
                    "captions": [c.model_dump(mode="json") for c in scene.captions],
                }
            )
        elif scene.type == "divider":
            divider_ordinal += 1
            scenes.append(
                {
                    "type": "divider",
                    "frames": n,
                    "index": f"{divider_ordinal:02d}",
                    "label": scene.label,
                    "roll": scene.roll,
                }
            )
        elif scene.type == "plate":
            scenes.append(
                {
                    "type": "plate",
                    "frames": n,
                    "title": scene.title,
                    "cards": [c.model_dump(mode="json") for c in scene.cards],
                    "backdrop": scene.backdrop,
                }
            )
        elif scene.type == "reveal":
            scenes.append(
                {"type": "reveal", "frames": n, "lead": scene.lead, "word": scene.word, "sub": scene.sub}
            )
        elif scene.type == "end":
            scenes.append(
                {
                    "type": "end",
                    "frames": n,
                    "name": scene.name,
                    "tagline": scene.tagline,
                    "url": pages[0].host,
                    "logo_url": None,
                }
            )
        # 配音轨 (ADR-120 E2): the scene's narration object key, baked by
        # code from the synthesis map — absent = the scene plays silent.
        audio_key = narration.get(idx)
        if audio_key is not None:
            scenes[-1]["audio"] = audio_key
    spec = {
        "family": "film",
        "name": storyboard.name,  # null-read tolerant (two-source law)
        "theme": theme,
        "aspect": aspect,
        "scenes": scenes,
    }
    if music is not None:
        spec["music"] = music
    return spec


# ---------------------------------------------------------------------------
# The storyboard agent
# ---------------------------------------------------------------------------


def _assemble(
    pages: list[dict[str, Any]],
    instruction: str | None,
    focus: str | None,
    language: str | None,
    page_images: list[MediaInput],
) -> AssembleResult:
    """Purity by signature: the model sees the manifests (its grounding
    universe), the run's instruction, the slot's focus steer, the plan's
    pinned film language (None = declare it from the page), and the page
    screenshots (its camera target) — nothing else."""
    return (
        {
            "pages": pages,
            "instruction": instruction,
            "focus": focus,
            "language": language,
        },
        page_images,
    )


film_storyboarder = Agent[FilmStoryboard](
    name="film_storyboarder",
    prompt="film_storyboard.j2",
    schema=FilmStoryboard,
    system=(
        "You are a film director cutting a polished intro film from a captured "
        "web page. Every word on screen is quoted or trimmed from the page's "
        "own copy — you never invent claims. You write a storyboard; the "
        "system allocates frames and renders it."
    ),
    assemble=_assemble,
    temperature=0.5,
    packs=["launch-film"],
    # The screenshots ground the camera plan; a multimodal failure degrades
    # to text-only (manifests still carry the copy) — the validator's focus
    # checks keep a blind camera honest.
    media_text_fallback=True,
    # 20k-token prompt + full-film generation: 2026-10-15 取证 — a healthy
    # run took 142s, two degraded-night runs died on the pool's 120s read
    # timeout. Declared override rides the request call, pool untouched.
    timeout_s=300,
)


def page_prompt_dict(page: StoryboardPage, index: int) -> dict[str, Any]:
    """One page's prompt block (the manifest IS the grounding universe —
    the j2 prints it verbatim). ``shots`` = the captured views the ui scene
    may pick from (0 = the fold; ADR-121 B1)."""
    r = page.research
    return {
        "index": index,
        "url": r.url,
        "host": page.host,
        "title": r.title,
        "description": r.description,
        "h1": r.h1,
        "h2": r.h2,
        "h3": r.h3,
        "buttons": r.buttons,
        "links": r.links,
        "paragraphs": r.paragraphs,
        "has_screenshot": bool(page.shots) or page.screenshot_key is not None,
        "shots": [
            {
                "index": i,
                "heading": s.heading or "(top)",
                # B2: the camera-target inventory — focuses name these ids.
                "elements": [
                    {
                        "id": e.id,
                        "kind": e.kind,
                        "text": e.text,
                        "x": e.x,
                        "y": e.y,
                        "w": e.w,
                        "h": e.h,
                        "covered": e.covered,
                    }
                    for e in s.elements
                ],
            }
            for i, s in enumerate(page.shots)
        ],
    }


# ---------------------------------------------------------------------------
# Shared seats (ADR-120 §2 — the run node and the plan-stage draft ride the
# SAME load/orchestration loop; no second orchestration chain, ADR-028)
# ---------------------------------------------------------------------------


async def load_storyboard_pages(db: AsyncSession, project: Project) -> list[StoryboardPage]:
    """The project's READY web_page assets → grounding pages (capture
    order). A COMPLETED capture always carries its manifest; the
    screenshot may be honestly absent."""
    assets = list(
        (
            await db.execute(
                select(Asset)
                .where(
                    Asset.project_id == project.id,
                    Asset.type == AssetType.WEB_PAGE,
                    Asset.processing_status == AssetStatus.COMPLETED,
                )
                .order_by(Asset.created_at)
            )
        )
        .scalars()
        .all()
    )
    pages: list[StoryboardPage] = []
    from urllib.parse import urlparse

    for a in assets:
        meta = a.meta if isinstance(a.meta, dict) else {}
        raw = meta.get("research")
        if not isinstance(raw, dict):
            continue
        research = WebPageResearch.model_validate(raw)
        host = urlparse(research.url).netloc or (a.title or "")
        # ADR-121 B1: fold + section shots (pre-B1 rows carry none — the
        # fold-only law: ui scenes read screenshot_key, shot stays 0).
        shots: list[ShotRef] = []
        for s in meta.get("shots") or []:
            if isinstance(s, dict) and isinstance(s.get("key"), str):
                with suppress(ValidationError):
                    shots.append(ShotRef.model_validate(s))
        pages.append(
            StoryboardPage(
                asset_id=str(a.id),
                research=research,
                screenshot_key=meta.get("screenshot_key"),
                host=host,
                shots=tuple(shots),
            )
        )
    return pages


async def page_media_inputs(pages: list[StoryboardPage]) -> list[MediaInput]:
    """The page screenshots → multimodal inputs (the ui scene's camera
    targets); a missing screenshot degrades honestly (manifests still carry
    the copy)."""
    items: list[MediaInput] = []
    for i, page in enumerate(pages):
        if page.screenshot_key is None:
            continue
        item = await media_input_for_image(
            page.screenshot_key,
            caption=f"Screenshot of page {i} ({page.host}) — the ui scene's camera target.",
        )
        if item is not None:
            items.append(item)
    return items


async def orchestrate_storyboard(
    *,
    pages: list[StoryboardPage],
    instruction: str | None,
    focus: str | None,
    page_images: list[MediaInput],
    language: str | None = None,
    on_reject=None,
) -> FilmStoryboard:
    """THE bounded storyboard loop (打回有界): up to 1 + MAX_REWRITES
    candidates, each re-called with the violation echo (never a blind
    re-roll). Returns the first candidate passing the grounding validator.

    Raises ``FilmStoryboardRejected`` on exhaustion (the caller stamps its
    own terminal); ``LLMSchemaError`` propagates (the two-strike schema
    terminal). ``on_reject(attempt, violations, feedback)`` is the node's
    logging hook."""
    prompt_pages = [page_prompt_dict(p, i) for i, p in enumerate(pages)]
    violations: list[FilmViolation] = []
    feedback: str | None = None
    for attempt in range(1 + MAX_REWRITES):
        candidate = await film_storyboarder.call(
            pages=prompt_pages,
            instruction=instruction,
            focus=focus,
            language=language,
            page_images=page_images,
            repair_feedback=feedback,
        )
        violations = validate_storyboard(candidate, pages)
        if not violations:
            return candidate
        feedback = format_violations(violations)
        if on_reject is not None:
            on_reject(attempt, violations, feedback)
    raise FilmStoryboardRejected(
        sorted({v.code for v in violations}), feedback or ""
    )


async def _await_captures_settled(project_id: UUID) -> None:
    """Wait for the project's in-flight web_page captures to reach a terminal
    state (bounded). The URL turn docks while the capture is still running
    (S11 取证: capture landed ~33s after the dock — drafting against zero
    pages would skip the review hold and let the auto gate start the run
    unreviewed). Polls on FRESH sessions (the get_understanding read-wait's
    law — the turn's own session never survives a sleep); a timeout or a
    FAILED world just lets the draft degrade honestly."""
    import asyncio
    import time

    from app.models.database import AsyncSessionLocal  # deferred: worker seat

    deadline = time.monotonic() + _CAPTURE_SETTLE_WAIT_S
    await asyncio.sleep(_CAPTURE_SETTLE_POLL_S)  # the absorb lands first
    while time.monotonic() < deadline:
        async with AsyncSessionLocal() as poll:
            pending = (
                await poll.execute(
                    select(func.count(Asset.id)).where(
                        Asset.project_id == project_id,
                        Asset.type == AssetType.WEB_PAGE,
                        Asset.processing_status.in_(
                            (AssetStatus.PENDING, AssetStatus.PROCESSING)
                        ),
                    )
                )
            ).scalar_one()
        if not pending:
            return
        await asyncio.sleep(_CAPTURE_SETTLE_POLL_S)


async def draft_film_storyboard(
    db: AsyncSession,
    project: Project,
    *,
    instruction: str | None,
    focus: str | None = None,
    language: str | None = None,
) -> tuple[FilmStoryboard, list[StoryboardPage]] | None:
    """The plan-stage storyboard draft (ADR-120 §2): the SAME loop the node
    runs, against the project's READY pages. Returns ``(storyboard, pages)``
    — the caller needs the pages for the block's source line. None honestly
    when the draft can't stand (no readable page / schema terminal /
    grounding exhaustion). The ONE caller is the deferred seat
    (chat/storyboard_dock.py — 统一迟延 2026-10-16: the draft never runs
    inside a chat turn); the seat owns the bounded retry and the terminal
    failure row, and the review hold stands regardless of the outcome.
    In-flight captures are awaited first (bounded) — the review hold may
    not be raced by the absorb's async capture."""
    await _await_captures_settled(project.id)
    pages = await load_storyboard_pages(db, project)
    if not pages:
        return None
    page_images = await page_media_inputs(pages)
    try:
        storyboard = await orchestrate_storyboard(
            pages=pages,
            instruction=instruction,
            focus=focus,
            page_images=page_images,
            language=language,
            on_reject=lambda attempt, violations, feedback: logger.info(
                "film_plan_draft_rejected",
                project_id=str(project.id),
                attempt=attempt,
                codes=sorted({v.code for v in violations}),
            ),
        )
    except (FilmStoryboardRejected, LLMSchemaError, LLMError) as exc:
        # LLMError included (S11 取证 2026-10-15): a provider transport
        # failure mid-draft must degrade to no-block, NEVER kill the
        # plan turn's dock (the review simply happens at the node's
        # birth-time orchestration instead).
        logger.info(
            "film_plan_draft_skipped",
            project_id=str(project.id),
            reason=str(exc)[:200],
        )
        return None
    return storyboard, pages


# ---------------------------------------------------------------------------
# The node
# ---------------------------------------------------------------------------


class LaunchFilm(NodeBase):
    kind = "launch_film"
    node_type = "video"  # 词表 v3 (ADR-076) — 装配站 (官网介绍短片)
    prototype = "generator"  # 散文程序: the instruction/focus IS the program
    task_name = "Generate intro film"
    task_name_zh = "生成官网介绍短片"
    output_type = "film"
    slot_label = "Film"
    slot_label_zh = "介绍短片"
    # The film family needs NO source media — its input is the captured page
    # (the birthplace ∀-check's film fork: WEB_PAGE presence + readiness,
    # never MEDIA).
    requires = (WEB_PAGE,)
    needs_plan_prelude = False
    produces_outputs = True
    retries = 0  # the bounded rewrite absorbs model variance; transports ride tenacity
    agents = (film_storyboarder,)

    def estimate(self, ctx: dict) -> dict | None:
        """Orchestration tokens (worst case = one storyboard pass per
        candidate, 1 + MAX_REWRITES) + the film-seconds flat item (D3 简式
        计价: ESTIMATE_FILM_SECONDS typical × the ``film.usd_per_second``
        config rate — the capture settles the storyboard's true allocated
        seconds through the same price line, hold/release absorb the
        difference)."""
        single = estimate_agent([1500, 8000], [400, 2000])
        n = 1 + MAX_REWRITES
        return {
            "prompt_tokens": [single["prompt_tokens"][0] * n, single["prompt_tokens"][1] * n],
            "completion_tokens": [single["completion_tokens"][0] * n, single["completion_tokens"][1] * n],
            "units": {
                "film_seconds": ESTIMATE_FILM_SECONDS,
                # E2 配音: speech ≈ 14 chars/s over the estimate window
                # (voiceover is the plan default; a voiceover-off plan
                # simply captures less — hold/release absorbs).
                "tts_chars": ESTIMATE_FILM_SECONDS * 14.0,
            },
        }

    async def run(
        self, db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
    ) -> list[UUID]:
        ctx = run.context or {}
        slot = node_slot(node, ctx, "film")
        focus = (slot.focus if slot else None) or None
        instruction = ctx.get("instruction") or None
        ui_language = ui_lang_of(run, project)
        # 影片语言 (2026-10-15 语言钉参): the plan's pin rides the slot; the
        # storyboard's own declaration is the unpinned fallback (the page's
        # voice, drafted from the manifest). ctx.target_language /
        # project.language stay the LEGACY tail (pre-pin rows) — the chat's
        # language never leads a film.
        pinned_language = (slot.language if slot else None) or None

        pages = await load_storyboard_pages(db, project)
        if not pages:
            # The birthplace gates presence+readiness; a capture that FAILED
            # mid-wait lands here — the honest refusal (never an ungrounded
            # film).
            raise ValueError(
                "The page never became readable (the capture failed) — send the link again to re-capture it."
            )

        storyboard: FilmStoryboard | None = None
        # confirmed_storyboard (ADR-120 §4): the plan-stage draft the user
        # reviewed and verbally OK'd rides run.context — the node defensively
        # re-validates it against the CURRENT pages (world drift: a page
        # re-captured since the review), then renders it verbatim, skipping
        # the orchestration. A stale confirmation falls back to a fresh
        # orchestration — never a film from a void storyboard.
        confirmed_raw = ctx.get("confirmed_storyboard")
        if isinstance(confirmed_raw, dict):
            try:
                confirmed = FilmStoryboard.model_validate(confirmed_raw)
            except (ValueError, TypeError):
                confirmed = None
            if confirmed is not None:
                stale = validate_storyboard(confirmed, pages)
                if not stale:
                    storyboard = confirmed
                    logger.info(
                        "confirmed_storyboard_used",
                        node_id=str(node.id),
                        scenes=len(confirmed.scenes),
                    )
                else:
                    logger.info(
                        "confirmed_storyboard_stale",
                        node_id=str(node.id),
                        codes=sorted({v.code for v in stale}),
                    )

        if storyboard is None:
            page_images = await page_media_inputs(pages)

            def _log_reject(attempt, violations, feedback):
                logger.info(
                    "film_storyboard_rejected",
                    node_id=str(node.id),
                    attempt=attempt,
                    codes=sorted({v.code for v in violations}),
                    count=len(violations),
                    detail=(feedback or "")[:400],
                )

            try:
                storyboard = await orchestrate_storyboard(
                    pages=pages,
                    instruction=instruction,
                    focus=focus,
                    page_images=page_images,
                    language=pinned_language,
                    on_reject=_log_reject,
                )
            except LLMSchemaError:
                # The funnel's own repair round already fired — a raise here
                # is the two-strike schema terminal. Stamp the failure stage
                # for the D4 ledger, then let the node fail.
                await set_spec_field(node.id, "failure", {"stage": "schema"})
                raise
            except FilmStoryboardRejected as exc:
                await set_spec_field(
                    node.id,
                    "failure",
                    {"stage": "grounding", "codes": exc.codes, "detail": exc.detail[:500]},
                )
                raise

        await set_spec_field(node.id, "storyboard", storyboard.model_dump(mode="json"))

        # 同 spec 重试幂等: a re-run of this step wipes its own earlier film
        # rows (mid-production, never delivered — physical delete) and cancels
        # their pending render mirrors before the fresh birth.
        prior = list(
            (
                await db.execute(
                    select(Output.id).where(
                        Output.workflow_step_id == node.id,
                        Output.type == "film",
                    )
                )
            )
            .scalars()
            .all()
        )
        if prior:
            await db.execute(
                _text(
                    "UPDATE workflow_steps SET status = 'skipped', updated_at = now() "
                    "WHERE kind = 'render' AND status = 'pending' "
                    "AND spec->>'output_id' IN :oids"
                ).bindparams(bindparam("oids", expanding=True)),
                {"oids": [str(oid) for oid in prior]},
            )
            await delete_outputs_fk_safe(db, prior)

        frames = allocate_frames(storyboard)

        # Slot levers (ADR-120 E2/E3): voiceover / music mood / aspect /
        # language ride the compiled slot; absent = plan defaults (on /
        # persona-or-calm / 16:9 / storyboard-declared).
        aspect = (slot.aspect if slot else None) or "16:9"
        voiceover = (slot.voiceover if slot else None) is not False
        music_mood = (slot.music_mood if slot else None) or None

        # 配乐 (ADR-120 E2): mood → persona skin default → "calm" (the
        # AddMusic resolution order, one law). Resolved BEFORE narration so
        # the beat snap below settles the windows the T2A fits into. An
        # EXPLICITLY named mood that resolves to nothing fails the step
        # (CHAT_ARCH §10: clear error, never a silent bed); the default
        # chain always lands on the seeded library.
        from app.memory.brand import resolve_music_ref
        from app.pipeline.music import music_file_path

        persona = await resolve_persona(db, project)  # None-safe
        brand_ref: Any = None
        if not music_mood and persona is not None:
            block = persona.brand or {}
            brand_ref = block.get("musicId") or block.get("musicMood")
        track = None
        for ref in (music_mood, brand_ref, "calm"):
            if not ref:
                continue
            track = await resolve_music_ref(db, ref)
            if track is not None:
                break
        if track is None and music_mood:
            raise ValueError(f"No music track found for mood '{music_mood}'")

        # 节拍锁剪 (ADR-121 B3): the bed's seed-time beat grid snaps the
        # internal scene boundaries (structural floors respected, tolerance
        # ±0.2s — see snap_frames_to_beats). Everything downstream — the
        # metering line, the narration windows, the spec frames — reads the
        # SNAPPED allocation: one timing truth, zero re-synthesis.
        beats_raw = (track.meta or {}).get("beats") if track is not None else None
        beats = (
            [float(b) for b in beats_raw if isinstance(b, (int, float)) and not isinstance(b, bool)]
            if isinstance(beats_raw, list)
            else None
        )
        if beats:
            frames = snap_frames_to_beats(storyboard, frames, beats)

        total_seconds = sum(frames) / FILM_FPS
        # 逐次尝试计价的实扣侧 (D3): the storyboard passed the gate — meter
        # the ACTUAL rendered seconds (what we truly render, post-snap) so
        # the step's capture charges them (estimate ≡ meter, one price
        # line). A rejected storyboard never reaches here, so a
        # grounding-exhausted FAILED step carries zero film seconds —
        # 失败不扣费 by position.
        await record_media_usage({"film_seconds": total_seconds})

        music_spec: dict[str, Any] | None = None
        if track is not None:
            music_spec = {"url": music_file_path(track.id), "gain_db": -20.0}

        output = Output(
            project_id=project.id,
            workflow_step_id=node.id,
            type="film",
            language=str(
                pinned_language
                or storyboard.language
                or ctx.get("target_language")
                or project.language
                or "en"
            ),
            # AI-orchestrated render (ADR-026/ADR-119): the on-screen copy is
            # quoted from the page, the film itself is machine-composed.
            provenance="generated",
            payload={
                "name": storyboard.name or "",
                "duration": round(total_seconds),
                "scene_count": len(storyboard.scenes),
                "aspect": aspect,
            },
            source_ref={"pages": [p.asset_id for p in pages]},
            render_status=RenderStatus.PENDING,
        )
        db.add(output)
        await db.flush()

        # 配音 (ADR-120 E2): one T2A call per narrated scene, fitted to the
        # scene's SNAPPED window; the synthesis map bakes into the spec as
        # per-scene ``audio`` keys. Voice = persona voice block → house
        # narrator (the film has no source footage to clone from).
        # Voiceover off = the silent cut (music bed only) — the reviewed
        # narration words still stand in the storyboard, just unsynthesized.
        narration_keys: dict[int, str] = {}
        if voiceover and any(
            getattr(sc, "narration", None) for sc in storyboard.scenes
        ):
            from app.tools.film.narration import (
                resolve_film_voice,
                synthesize_film_narration,
            )

            voice_block = (persona.voice or None) if persona is not None else None
            narration_keys = await synthesize_film_narration(
                output_id=output.id,
                project=project,
                storyboard=storyboard,
                frames=frames,
                voice_id=resolve_film_voice(voice_block),
                language=output.language,
            )

        output.render_spec = build_film_spec(
            storyboard,
            pages,
            narration=narration_keys,
            music=music_spec,
            aspect=aspect,
            frames=frames,
        )
        await db.flush()

        # Render fan-out through the ONE pend seat (ADR-096 §1): barrier = the
        # birth step, mirror born here, claimed via outputs.render_status.
        await pend_outputs_for_render(db, run, [output])

        await fill_summary(
            node.id,
            self.kind,
            tag=slot_tag(slot),
            ui_language=ui_language,
            n=1,
            total_seconds=int(total_seconds),
        )
        return [output.id]
