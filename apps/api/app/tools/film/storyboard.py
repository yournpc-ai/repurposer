"""launch_film node + film direction agent + skeleton assembler + grounding
validator (MG D2; 骨架收归代码 ADR-127, 2026-10-16 用户拍板).

One file, four layers:

1. THE SKELETON + ASSEMBLER (pure) — the film's STRUCTURE is code-owned,
   aligned with the launch-film skill's fixed template (cold open → hero →
   home walk → per chapter: divider → walk, a plate when the page carries
   numbers → reveal → proof walk → end; 70-118s total, 3-5 chapters). The
   LLM's ONE call (``FilmDirection``) answers only the slots: chapter picks
   and factual on-screen strings as CITATIONS (``CopyRef`` — the model
   never writes those), plus the creative channel as free text (cold-open
   hooks, the reveal lead, per-scene narration — hooks, never claims).
   ``assemble_storyboard`` splices direction into skeleton, resolving
   citations (verbatim line, word-boundary head/tail fit, accent wrap);
   the only citation errors are an unknown line id or a missed accent
   (INVALID_COPY_REF). The RESOLVED
   FilmStoryboard (real strings) stays the persisted and rendered shape —
   block, film-spec and renderer never see a reference.
   ``fixed_direction`` is the no-LLM terminal: code fills every slot from
   the manifest's own semantics over the SAME skeleton — the WORKER node's
   last rung only (the design journey fails honestly instead, see
   ``orchestrate_storyboard``'s ``allow_fixed_fallback``).

2. THE VALIDATOR (pure) — the deterministic gate between the resolved
   storyboard and the render contract: cited strings re-checked against
   the manifest (TEXT_NOT_GROUNDED — passes by construction on the
   assembly path; the seat that keeps a hand-built or stale confirmed
   storyboard honest; the creative slots are exempt — ``_CREATIVE_SLOTS``),
   camera focus bounds (INVALID_FOCUS), the closed scene vocabulary
   (UNSUPPORTED_SCENE), duration intents and content bounds
   (DURATION_INVALID / CONSTRAINT_VIOLATION). Bounded rewrite: the
   orchestrator offers the model at most MAX_REWRITES repair rounds (3
   candidates total) inside the 30-minute generation ceiling — never a
   blind retry (each rewrite rides the violation echo).

3. THE ALLOCATOR (pure) — deterministic frame assignment. Scene seconds
   are code-owned (``_assign_seconds``); code owns integer frames (fixed
   30 fps, structural minimums — the divider roll cadence, the end-card
   floor — the total is Σ scene frames), then snaps internal boundaries to
   the resolved bed's beat grid when one exists. The renderer only sums;
   narration cues are code-projected from the real synthesized durations.

4. THE NODE — loads the project's READY web_page assets (the birthplace
   ∀-check gates presence, the claim gate gates processing; a mid-run
   capture failure surfaces here as an honest error), drives the bounded
   loop, births the film output (``render_spec.family == "film"``) and
   pends its render through the ONE seat (``pend_outputs_for_render``). No
   second orchestration chain (ADR-028/029).

Grounding normalization: lowercase + every non-word char stripped (markdown
emphasis ``*``, punctuation, whitespace) — a screen string hits the manifest
when its normalized form is a substring of a normalized manifest item
(verbatim quote OR trim). Code-baked chrome is exempt by construction:
divider ordinals + kickers, ui/end display URLs, the ui screenshot, the
end logo.
"""

from __future__ import annotations

import asyncio
import inspect
import difflib
import hashlib
import json
import math
import re
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import bindparam, select, text as _text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import Agent, AssembleResult
from app.metering import record_media_usage
from app.models.schemas import (
    AssetStatus,
    AssetType,
    FilmFocus,
    FilmPlateCard,
    FilmScene,
    FilmSceneDivider,
    FilmSceneEnd,
    FilmSceneHero,
    FilmScenePlate,
    FilmSceneReveal,
    FilmSceneUi,
    FilmSceneWords,
    FilmStoryboard,
    FilmStoryboardTheme,
    MediaInput,
    PendingPlan,
    RenderStatus,
    ShotRef,
    WebPageResearch,
)
from app.models.tables import (
    Asset,
    Music,
    Output,
    Project,
    WorkflowRun,
    WorkflowStep,
)
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
# Capture settle wait ceiling (draft seat) — 30min floor (2026-10-17 用户拍板):
# a homepage capture's sub-page discovery chains run minutes end to end, and
# the wait is a phase of its OWN budget — never a squeeze on generation.
_CAPTURE_SETTLE_WAIT_S = 1800.0
_CAPTURE_SETTLE_POLL_S = 2.0
SCENE_COUNT_LIMITS = (8, 20)
# The film is a 70-118s keynote, never a 30s teaser (this range is THE law —
# the skill, the prompt and the review markdown all mirror it). 118 stays
# safely under the render frame cap.
TOTAL_SECONDS_RANGE = (70.0, 118.0)
# Render-side frame cap (server.ts FILM_MAX_FRAMES default) — the validator's
# total window stays comfortably under it; this is the post-allocation guard.
FILM_MAX_FRAMES = 3600

# Per-scene seconds intent bounds (code assigns within these — the skeleton's
# seconds are code-owned, ADR-127). Divider = the 4-beat chapter card (2s
# floor), reveal = the emotional peak (lead → beat pause → word needs 8s+).
SCENE_SECONDS: dict[str, tuple[float, float]] = {
    "words": (2.0, 4.0),
    "hero": (3.0, 6.0),
    "ui": (4.0, 12.0),
    "divider": (2.0, 6.0),
    "plate": (4.0, 8.0),
    "reveal": (8.0, 14.0),
    "end": (3.0, 6.0),
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
    ("words", "lines"): 36,
    ("hero", "word"): 20,
    ("hero", "sub"): 90,
    ("divider", "label"): 48,
    ("divider", "roll"): 30,
    ("plate", "title"): 48,
    ("plate", "big"): 12,
    ("plate", "label"): 30,
    ("reveal", "lead"): 72,
    ("reveal", "word"): 30,
    ("reveal", "sub"): 90,
    ("end", "name"): 30,
    ("end", "tagline"): 90,
}
# Per-scene item count caps.
_LIST_CAPS = {"words.lines": 4, "divider.roll": 5, "ui.focuses": 3, "plate.cards": 4}

# Camera bounds: x/y are normalized frame positions; zoom is a magnification
# (1 = the full frame). The spec's [0,1]³ law covers x/y; zoom lives in [1,4].
_ZOOM_RANGE = (1.0, 4.0)

MAX_REWRITES = 2  # at most three candidates, within ONE generation budget
# 30-minute ceiling (2026-10-18 用户拍板): the user explicitly accepts a
# long design beat — this is the ALLOWED ceiling for the whole candidate
# ladder, never a fixed wait (a clean first candidate returns in seconds).
# 180s once killed slow-but-alive generations mid-flight and dropped the
# journey to the fixed board (the Decline/Accept incident) — a real design
# now gets its time; an exhaustion fails honestly, never masquerades.
_DIRECTION_BUDGET_S = 1800.0
# The dock draft's total backstop = the phases' OWN budgets summed (capture
# wait + one generation budget + media/assembly slack). Each phase carries
# its own bound inside (the wait's deadline, the direction loop's timeout);
# this wrapper is the catch-all, never a squeeze — the retired shared 240s
# let a long capture wait eat the model's generation budget whole (the
# 2026-10-17 f5743045 incident: 151s waiting left 89s for a 180s budget).
_DOCK_DRAFT_BUDGET_S = _CAPTURE_SETTLE_WAIT_S + _DIRECTION_BUDGET_S + 60.0

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
# 行 ID 化 (2026-10-16): a citation that names no manifest line or an
# accent that misses its resolved text. The draft path's ONLY
# grounding-adjacent failure family — the old free-text whack-a-mole is
# impossible by construction.
INVALID_COPY_REF = "INVALID_COPY_REF"
# Quality gates (Batch 2): a repeated web shot (same captured image, same
# presentation), an empty chapter (a divider no walk follows), a padding
# scene (a static shot or a near-verbatim adjacent repeat) — each failure
# names its scenes so the rewrite knows exactly what to fix.
REPEATED_VIEW = "REPEATED_VIEW"
EMPTY_CHAPTER = "EMPTY_CHAPTER"
PADDING_SCENE = "PADDING_SCENE"
# 配音承诺失守 (2026-10-18): voiceover was promised but the board carries
# no narration at all (design-time: the rewrite repairs it) — or narration
# was keyed by names no scene owns (the silent key-drop that zeroed the
# 4ad7963e board's voice).
NARRATION_MISSING = "NARRATION_MISSING"
NARRATION_KEY_UNKNOWN = "NARRATION_KEY_UNKNOWN"


class FilmStoryboardRejected(Exception):
    """The bounded rewrite exhausted without a clean storyboard — the node
    settles FAILED with the structured codes on ``spec.failure``."""

    user_key = "film_storyboard_ungrounded"

    def __init__(
        self, codes: list[str], detail: str, *, user_key: str | None = None
    ) -> None:
        super().__init__(f"storyboard rejected ({', '.join(codes)}): {detail[:300]}")
        self.codes = codes
        self.detail = detail
        # The preflight's view-poor rejection speaks a different remedy than
        # the grounding exhaustion (the page's VISUALS never captured — the
        # fix is a re-capture or user-supplied shots, never clearer copy).
        if user_key is not None:
            self.user_key = user_key


class FilmCaptureTimeout(Exception):
    """The capture wait outlasted its ceiling with pages still in flight —
    the draft refuses a half-captured world (2026-10-17 用户拍板: a wait
    timeout is an honest failure, never a silent draft over incomplete
    material). Propagates through ``draft_film_storyboard`` (its except
    clause names only the drafting failure family) to the turn's failure
    envelope with this ``user_key``'s localized line."""

    user_key = "film_capture_timeout"


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
# The citation layer (行 ID 化, 2026-10-16 用户拍板; ADR-127 收窄到事实槽):
# the LLM never WRITES a factual on-screen string — it CITES a numbered
# manifest line. Code resolves the citation into the final string (verbatim,
# word-boundary fit, accent wrap), so the grounding failure family
# (TEXT_NOT_GROUNDED whack-a-mole) is impossible by construction on the
# assembly path. The creative channel (cold-open hooks, reveal lead,
# narration) is free text by design — hooks, never claims. The resolved
# FilmStoryboard (real strings) stays the persisted/rendered shape — block,
# spec, markdown and renderer are untouched.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ManifestLine:
    """One quotable line of the captured manifest. ``id`` is 1-based and
    globally unique across the presented pages (the model cites one number,
    never a page+line pair); ``kind`` preserves the line's semantics (a
    button label reads differently from a paragraph)."""

    id: int
    page: int
    kind: str  # title / description / h1 / h2 / h3 / button / link / paragraph
    text: str


def build_line_manifest(pages: list[StoryboardPage]) -> list[ManifestLine]:
    """The citation universe, in presentation order. The kind sequence
    mirrors the legacy grounding corpus (title → description → h1 → h2 → h3
    → buttons → links → paragraphs) so the resolved strings trace exactly
    the lines the old substring validator accepted."""
    lines: list[ManifestLine] = []
    next_id = 1
    for page_idx, p in enumerate(pages):
        r = p.research
        groups: list[tuple[str, list[str]]] = [
            ("title", [r.title] if r.title else []),
            ("description", [r.description] if r.description else []),
            ("h1", list(r.h1)),
            ("h2", list(r.h2)),
            ("h3", list(r.h3)),
            ("button", list(r.buttons)),
            ("link", list(r.links)),
            ("paragraph", list(r.paragraphs)),
        ]
        for kind, items in groups:
            for item in items:
                if _norm(item):
                    lines.append(ManifestLine(next_id, page_idx, kind, item.strip()))
                    next_id += 1
    return lines


class CopyRef(BaseModel):
    """One on-screen string, CITED never written. ``line`` names a manifest
    line id; ``fit`` governs over-cap lines ("full" = the line must fit its
    slot as-is, "head"/"tail" = code trims the leading/trailing segment at
    a word boundary — the model never counts characters); ``accent`` names
    a substring of the RESOLVED text to wrap in emphasis marks (null = no
    accent)."""

    model_config = ConfigDict(extra="forbid")

    line: int
    fit: Literal["full", "head", "tail"] = "full"
    accent: str | None = None


class FilmDirection(BaseModel):
    """The director's answer — the ONLY thing the LLM produces (ADR-127,
    2026-10-16 用户拍板): the scene STRUCTURE (order/types/durations/camera)
    is code-owned, aligned with the launch-film skill's fixed template; the
    model answers only the slots. Factual slots stay citations (``CopyRef``
    — product name, taglines, chapter headings); the creative
    channel is free text (cold-open hooks, the reveal lead, per-scene
    narration) — hooks, never claims (GPT 任务书法: 创作交给 LLM，正确性
    与执行交给代码). Never persisted: ``assemble_storyboard`` splices it
    into the code-built skeleton and resolves citations into the persisted
    FilmStoryboard shape."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    # Declared spoken language — the plan's pin rides the prompt and the
    # model declares it verbatim; null-read tolerance (打字机牙①).
    language: str | None = None
    theme: FilmStoryboardTheme | None = None
    # The chapters: 3-5 heading lines the site itself leads with, cited.
    pillars: list[CopyRef] = Field(min_length=3, max_length=5)
    hero_word: CopyRef
    hero_sub: CopyRef
    # Creative channel: 1-3 cold-open hook lines (≤3 words each, CJK ≤8
    # chars) — the film's own framing, never a product fact.
    cold_open: list[str] = Field(min_length=1, max_length=3)
    reveal_lead: str | None = None  # creative; null = the code phrase
    reveal_word: CopyRef
    reveal_sub: CopyRef
    end_name: CopyRef
    end_tagline: CopyRef
    # Spoken lines keyed by the skeleton's scene keys (a missing key reads
    # as a silent scene — 读容忍).
    narrations: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# The skeleton (code-owned scene structure, ADR-127): scene order, per-scene
# durations, view/camera assignment, plate inclusion — all deterministic,
# aligned with the launch-film skill's "structure that works": quiet cold
# open → hero → home walk → per pillar: divider → walk (a plate after the
# first chapter when the page carries numbers) → reveal → proof walk → end.
# ---------------------------------------------------------------------------

_MAX_CHAPTERS = 5  # mirrors FilmDirection.pillars' max (one law)

# Seconds base weights per type — scaled to _TARGET_TOTAL and clamped into
# SCENE_SECONDS by ``_assign_seconds``.
_BASE_SECONDS: dict[str, float] = {
    "words": 3.0,
    "hero": 5.0,
    "ui": 8.0,
    "divider": 2.5,
    "plate": 6.0,
    "reveal": 12.0,
    "end": 5.0,
}
_TARGET_TOTAL = 88.0  # the craft law's target band center (75-95s)

# The film needs the product's REAL pages on screen (the skill stops and
# asks for screenshots when a site blocks capture): fewer usable views than
# this = the arc cannot stand — the orchestrator fails honestly BEFORE
# burning an LLM call. The floor is home walk + one walk per chapter at the
# 3-chapter minimum: a chapter whose divider has no walk is an EMPTY_CHAPTER
# violation, so a 3-view world can no longer ship a film at all.
_MIN_VIEWS = 4

# Code-voiced chrome phrases (creative slots the code fills): the divider
# kicker and the reveal's lead-in, in the film's language (European product
# — the map covers the launch languages; anything else falls back to en).
_CHAPTER_KICKER = {
    "en": "Chapter", "zh": "章节", "fr": "Chapitre",
    "de": "Kapitel", "es": "Capítulo", "it": "Capitolo",
}
_REVEAL_LEAD = {
    "en": "One more thing.", "zh": "还有一件事。", "fr": "Encore une chose.",
    "de": "Eine Sache noch.", "es": "Una cosa más.", "it": "Ancora una cosa.",
}


def _phrase(table: dict[str, str], language: str | None) -> str:
    return table.get((language or "en").split("-")[0].split("_")[0].lower(), table["en"])


@dataclass(frozen=True)
class _Skeleton:
    """The code-owned half of the film: the usable page views (page, shot)
    in preference order, each view's code-picked camera focus, and the
    plate verdict (number-ish manifest lines the cards are split from, plus
    the page they live on — the plate hangs off THAT page's chapter)."""

    views: tuple[tuple[int, int], ...]
    focuses: dict[tuple[int, int], FilmFocus]
    plate_lines: tuple[int, ...]  # manifest ids, number-ish lines (empty = no plate)
    plate_page: int | None  # the page the plate lines came from


_FOCUS_KINDS = ("heading", "button", "image", "video")  # camera preference order


def build_skeleton(pages: list[StoryboardPage], lines: list[ManifestLine]) -> _Skeleton:
    """Derive the deterministic half from the captured world. Views = every
    captured (page, shot) with imagery, fold first per page (pages without
    any screenshot contribute nothing — a ui scene there is illegal by
    validator law). Each view's camera names its best uncovered element
    (headings/buttons/imagery first, largest area wins); a view with no
    element inventory falls back to the honest raw center push-in."""
    views: list[tuple[int, int]] = []
    focuses: dict[tuple[int, int], FilmFocus] = {}
    for page_idx, page in enumerate(pages):
        if page.shots:
            # A capture that stored the same image twice (same object key)
            # contributes the view ONCE — two walks of identical pixels are
            # a repeated web shot, whatever the shot index says.
            seen_keys: set[str] = set()
            for shot_idx, shot in enumerate(page.shots):
                if shot.key in seen_keys:
                    continue
                seen_keys.add(shot.key)
                key = (page_idx, shot_idx)
                views.append(key)
                focuses[key] = _pick_focus(shot.elements)
        elif page.screenshot_key is not None:
            key = (page_idx, 0)
            views.append(key)
            focuses[key] = _pick_focus([])
    numberish = tuple(
        l.id for l in lines if _NUMBERISH.match(l.text) and len(l.text) <= 40
    )
    by_id = {l.id: l for l in lines}
    return _Skeleton(
        views=tuple(views),
        focuses=focuses,
        # A plate needs ≥2 cards — a single number-ish line is no plate.
        plate_lines=numberish[:3] if len(numberish) >= 2 else (),
        # The plate hangs off the chapter whose page the numbers came from
        # (the reference arc plates the chapter that PROVED the numbers,
        # never blindly chapter 1). Majority page wins; ties keep the first
        # (max over the list itself stays deterministic — a set wouldn't).
        plate_page=(
            max(
                (pages_of := [by_id[l].page for l in numberish[:3]]),
                key=pages_of.count,
            )
            if len(numberish) >= 2
            else None
        ),
    )


# A plate card carries a number — the line's first token leads with one
# (the code split: big = that token, label = the rest; "40 apps a month"
# → "40" / "apps a month").
_NUMBERISH = re.compile(r"^\s*\S*\d")


def _split_card(text: str) -> tuple[str, str] | None:
    """big/label split for a number-led line: the leading token is the big
    (a unit stuck to it rides along — "40%", "256B"), the remainder is the
    label. None = no clean split (the card degrades to a phrase card)."""
    parts = text.strip().split(None, 1)
    if len(parts) != 2 or not any(ch.isdigit() for ch in parts[0]):
        return None
    big, label = parts[0].strip(), parts[1].strip(" —-·")
    if not big or not label:
        return None
    return big[: TEXT_CAPS[("plate", "big")]], _fit_to_cap(
        label, TEXT_CAPS[("plate", "label")], "head"
    )


def _pick_focus(elements: list) -> FilmFocus:
    """One camera beat for a view: the best uncovered element by kind
    preference then area (its ``at`` is re-derived at assembly once the
    scene's window exists — the skill counts arrivals in beats). No
    inventory = the raw center push-in (the two legal focus forms,
    ADR-121 B2)."""
    candidates = [e for e in elements if not e.covered]
    for kind in _FOCUS_KINDS:
        pool = [e for e in candidates if e.kind == kind]
        if pool:
            best = max(pool, key=lambda e: e.w * e.h)
            return FilmFocus(at=2.0, element=best.id)
    if candidates:
        best = max(candidates, key=lambda e: e.w * e.h)
        return FilmFocus(at=2.0, element=best.id)
    return FilmFocus(at=2.0, x=0.5, y=0.45, zoom=1.6)


def _fit_to_cap(text: str, cap: int, fit: str) -> str:
    """Apply a ref's fit to its slot cap. "full" returns the line as-is
    (an over-cap line then surfaces as a CONSTRAINT_VIOLATION downstream —
    the echo tells the model to fit or cite a shorter line). "head"/"tail"
    trim at a word boundary when one exists inside the window (CJK and
    single-word lines hard-cut at the cap)."""
    text = text.strip()
    if len(text) <= cap or fit == "full":
        return text
    if fit == "head":
        cut = text[:cap]
        sp = cut.rfind(" ")
        return (cut[:sp] if sp > 0 else cut).strip()
    cut = text[-cap:]
    sp = cut.find(" ")
    return (cut[sp + 1:] if 0 < sp < len(cut) - 1 else cut).strip()


def _apply_accent(text: str, accent: str) -> str | None:
    """Wrap the accent substring's first occurrence (case-insensitive) in
    emphasis marks. None = the accent is absent from the resolved text —
    a citation error the echo names precisely."""
    if not accent.strip():
        return None
    idx = text.lower().find(accent.strip().lower())
    if idx < 0:
        return None
    return f"{text[:idx]}*{text[idx:idx + len(accent.strip())]}*{text[idx + len(accent.strip()):]}"


@dataclass(frozen=True)
class _PlannedScene:
    """One scene of the code-built plan: its skeleton key (the narration
    dictionary's lookup), type, and — for ui scenes — the assigned view."""

    key: str
    type: str
    chapter: int | None = None  # 1-based, divider/ui chapter scenes
    view: tuple[int, int] | None = None


def _plate_chapter(n_chapters: int, skeleton: _Skeleton) -> int:
    """The plate hangs off the chapter whose page the numbers came from
    (chapter i's walk takes views[i]; views[0] is the home walk). Fallback
    1 = the numbers' page never got a chapter walk."""
    return next(
        (
            i
            for i in range(1, n_chapters + 1)
            if i < len(skeleton.views) and skeleton.views[i][0] == skeleton.plate_page
        ),
        1,
    )


def _scene_plan(n_chapters: int, skeleton: _Skeleton) -> list[_PlannedScene]:
    """The fixed arc, trimmed to the chapter count and the AVAILABLE views:
    home walk first, one walk per chapter while views last (a view-poor
    world degrades to divider-only chapters, never to invented imagery),
    the plate after the chapter whose page the plate's numbers came from,
    the proof walk last. Preflight (the orchestrator's ``_MIN_VIEWS`` gate)
    guarantees ≥3 views, so the plan always carries ≥3 ui scenes and the
    seconds assignment can reach the duration floor."""
    plan = [_PlannedScene("open", "words"), _PlannedScene("hero", "hero")]
    remaining = list(skeleton.views)

    def take_view() -> tuple[int, int] | None:
        return remaining.pop(0) if remaining else None

    if (v := take_view()) is not None:
        plan.append(_PlannedScene("home", "ui", view=v))
    plate_chapter = _plate_chapter(n_chapters, skeleton)
    for i in range(1, n_chapters + 1):
        plan.append(_PlannedScene(f"ch{i}_divider", "divider", chapter=i))
        if (v := take_view()) is not None:
            plan.append(_PlannedScene(f"ch{i}_ui", "ui", chapter=i, view=v))
        if skeleton.plate_lines and i == plate_chapter:
            plan.append(_PlannedScene("plate", "plate"))
    plan.append(_PlannedScene("reveal", "reveal"))
    if (v := take_view()) is not None:
        plan.append(_PlannedScene("prove", "ui", view=v))
    plan.append(_PlannedScene("end", "end"))
    return plan


def _assign_seconds(types: list[str]) -> list[float]:
    """Code-owned durations: base weights scaled toward _TARGET_TOTAL,
    clamped into SCENE_SECONDS, snapped to the half-second grid. When
    clamps bite (a view-poor world), the deficit top-up pushes ui scenes
    toward their ceiling first (they carry the walk), then dividers —
    preflight guarantees the ceiling can reach the floor."""
    base = [_BASE_SECONDS[t] for t in types]
    scale = _TARGET_TOTAL / sum(base)
    secs = [
        min(max(b * scale, SCENE_SECONDS[t][0]), SCENE_SECONDS[t][1])
        for b, t in zip(base, types)
    ]

    def _snap(v: float) -> float:
        return round(v * 2) / 2

    order = sorted(
        range(len(types)), key=lambda i: (types[i] != "ui", types[i] != "divider")
    )
    for target in (_TARGET_TOTAL, TOTAL_SECONDS_RANGE[0]):
        # Top up toward the target while any scene has headroom.
        for i in order:
            if sum(secs) >= target:
                break
            head = SCENE_SECONDS[types[i]][1] - secs[i]
            if head > 0:
                secs[i] += min(head, target - sum(secs))
    secs = [_snap(s) for s in secs]
    # Symmetric trim guard (a maximal structure must stay under the cap):
    # shave ui scenes toward their floor first.
    for i in order:
        if sum(secs) <= TOTAL_SECONDS_RANGE[1]:
            break
        lo = SCENE_SECONDS[types[i]][0]
        if secs[i] > lo:
            secs[i] = max(lo, secs[i] - (sum(secs) - TOTAL_SECONDS_RANGE[1]))
    return [_snap(s) for s in secs]


def assemble_storyboard(
    skeleton: _Skeleton,
    direction: FilmDirection,
    lines: list[ManifestLine],
    *,
    pinned_language: str | None = None,
) -> tuple[FilmStoryboard | None, list[FilmViolation]]:
    """Direction (the model's slot answers) + skeleton (code's structure) →
    the resolved storyboard. Citation errors resolve with the same precise
    echo as before (unknown line id, missed accent, a ui caption citing
    another page's line); the creative slots are length/emptiness checked
    here, then the whole board faces ``validate_storyboard`` like always.
    The grounding check there passes by construction for cited slots and
    exempts the creative ones (_CREATIVE_SLOTS)."""
    by_id = {l.id: l for l in lines}
    violations: list[FilmViolation] = []

    def resolve(
        ref: CopyRef, cap: int, where: str
    ) -> str:
        line = by_id.get(ref.line)
        if line is None:
            violations.append(
                FilmViolation(
                    INVALID_COPY_REF,
                    f"{where}: line L{ref.line} names no manifest line",
                )
            )
            return ""
        text = _fit_to_cap(line.text, cap, "head" if where.endswith(".roll") and ref.fit == "full" else ref.fit)
        if ref.accent is not None:
            accented = _apply_accent(text, ref.accent)
            if accented is None:
                violations.append(
                    FilmViolation(
                        INVALID_COPY_REF,
                        f"{where}: accent «{ref.accent[:30]}» is not in the resolved «{text[:40]}»",
                    )
                )
            else:
                text = accented
        return text

    def creative(text: str, cap: int, where: str) -> str:
        """A free-text slot's only law: non-blank, within its cap (hooks,
        never claims — the prompt's law, not machine-checkable)."""
        t = text.strip()
        if not _norm(t):
            violations.append(FilmViolation(CONSTRAINT_VIOLATION, f"{where}: blank"))
        elif len(t) > cap:
            violations.append(
                FilmViolation(
                    CONSTRAINT_VIOLATION,
                    f"{where}: {len(t)} chars over the {cap} cap ({t[:40]}…)",
                )
            )
        return t

    language = direction.language or pinned_language
    pillars = direction.pillars[:_MAX_CHAPTERS]
    plan = _scene_plan(len(pillars), skeleton)
    seconds = _assign_seconds([s.type for s in plan])
    plan_keys = {s.key for s in plan}
    narr: dict[str, str | None] = {}
    for k, v in (direction.narrations or {}).items():
        if not isinstance(v, str):
            continue
        if k not in plan_keys:
            # The silent key-drop (4ad7963e): a narration keyed by a name no
            # scene owns used to vanish without a word — the whole board
            # could come back voiceless with nobody told. Name the offender
            # and the valid keys; the bounded rewrite re-keys the line.
            violations.append(
                FilmViolation(
                    NARRATION_KEY_UNKNOWN,
                    f"narrations.{k!r}: no scene owns this key — valid scene "
                    f"keys: {', '.join(s.key for s in plan)}",
                )
            )
            continue
        narr[k] = v.strip() or None

    resolved_scenes: list[FilmScene] = []
    ui_count = 0
    for scene, secs in zip(plan, seconds):
        where = f"{scene.key}({scene.type})"
        narration = narr.get(scene.key)
        if scene.type == "words":
            resolved_scenes.append(FilmSceneWords(
                type="words", seconds=secs, dark=True, narration=narration,
                lines=[
                    creative(t, TEXT_CAPS[("words", "lines")], f"{where}.lines")
                    for t in direction.cold_open
                ],
            ))
        elif scene.type == "hero":
            resolved_scenes.append(FilmSceneHero(
                type="hero", seconds=secs, narration=narration,
                word=resolve(direction.hero_word, TEXT_CAPS[("hero", "word")], f"{where}.word"),
                sub=resolve(direction.hero_sub, TEXT_CAPS[("hero", "sub")], f"{where}.sub"),
            ))
        elif scene.type == "ui":
            assert scene.view is not None  # the plan only builds ui with a view
            page_idx, shot_idx = scene.view
            # The camera arrival scales with the scene's window (the skill
            # counts arrivals in BEATS, never a fixed 2s): a quarter of the
            # scene, snapped to the half-second grid, 1s..2s.
            arrival = min(2.0, max(1.0, round(secs * 0.25 * 2) / 2))
            resolved_scenes.append(FilmSceneUi(
                type="ui", seconds=secs, narration=narration,
                page=page_idx, shot=shot_idx,
                # The walk alternates browser-card and full-bleed (code's
                # rhythm — the skill's "this is a real page" vs the
                # immersive push).
                frame=(ui_count % 2 == 0),
                focuses=[skeleton.focuses[scene.view].model_copy(update={"at": arrival})],
            ))
            ui_count += 1
        elif scene.type == "divider":
            assert scene.chapter is not None
            own = pillars[scene.chapter - 1]
            # The roll: two decoys (the NEXT chapters' lines, cyclically —
            # plausible alternatives by construction, the skill's law) then
            # the real word last. The cyclic shift keeps every chapter's
            # roll distinct (a shared set in a different landing order is a
            # different screen — the validator's divider signature keys on
            # the roll IN ORDER). Decoys that trim-collide with the real
            # word drop.
            n = len(pillars)
            decoys = [pillars[scene.chapter % n], pillars[(scene.chapter + 1) % n]]
            roll_cap = TEXT_CAPS[("divider", "roll")]
            real = resolve(own, roll_cap, f"{where}.roll")
            roll: list[str] = []
            for decoy in decoys:
                text = resolve(decoy, roll_cap, f"{where}.roll")
                if _norm(text) != _norm(real):
                    roll.append(text)
            roll.append(real)
            resolved_scenes.append(FilmSceneDivider(
                type="divider", seconds=secs, narration=narration,
                label=_phrase(_CHAPTER_KICKER, language),
                roll=roll or [real],
            ))
        elif scene.type == "plate":
            title_line = next(
                (l for l in lines if l.kind in ("h1", "title")), lines[0]
            )
            cards: list[FilmPlateCard] = []
            for lid in skeleton.plate_lines:
                line = by_id.get(lid)
                if line is None:
                    continue
                split = _split_card(line.text)
                if split is not None:
                    cards.append(FilmPlateCard(big=split[0], label=split[1]))
                else:
                    cards.append(
                        FilmPlateCard(
                            big=None,
                            label=_fit_to_cap(line.text, TEXT_CAPS[("plate", "label")], "head"),
                        )
                    )
            if len(cards) < 2:
                # The preflight plate verdict promised 2+ number-ish lines;
                # a split failure downgrades honestly to NO plate rather
                # than a thin one — skip this scene.
                continue
            resolved_scenes.append(FilmScenePlate(
                type="plate", seconds=secs, narration=narration, backdrop="mist",
                title=_fit_to_cap(title_line.text, TEXT_CAPS[("plate", "title")], "head"),
                cards=cards[:4],
            ))
        elif scene.type == "reveal":
            lead = (direction.reveal_lead or "").strip() or _phrase(_REVEAL_LEAD, language)
            resolved_scenes.append(FilmSceneReveal(
                type="reveal", seconds=secs, narration=narration,
                lead=creative(lead, TEXT_CAPS[("reveal", "lead")], f"{where}.lead"),
                word=resolve(direction.reveal_word, TEXT_CAPS[("reveal", "word")], f"{where}.word"),
                sub=resolve(direction.reveal_sub, TEXT_CAPS[("reveal", "sub")], f"{where}.sub"),
                # Split reveal (the reference arc's emotional peak): the
                # lead holds the FIRST HALF alone, a one-beat black pause,
                # then the word lands (the spec builder snaps the word's
                # onset onto the music grid).
                lead_seconds=round(secs) / 2,
            ))
        elif scene.type == "end":
            resolved_scenes.append(FilmSceneEnd(
                type="end", seconds=secs, narration=narration,
                name=resolve(direction.end_name, TEXT_CAPS[("end", "name")], f"{where}.name"),
                tagline=resolve(direction.end_tagline, TEXT_CAPS[("end", "tagline")], f"{where}.tagline"),
            ))
    if violations:
        return None, violations
    return (
        FilmStoryboard(
            name=direction.name,
            theme=direction.theme,
            language=language,
            scenes=resolved_scenes,
        ),
        [],
    )


def fixed_direction(
    lines: list[ManifestLine], *, language: str | None = None
) -> FilmDirection | None:
    """The no-LLM direction (固定分镜兜底, 2026-10-16 用户拍板): every slot
    filled by code from the manifest's own semantics — pillars = the first
    h2s (padding through h3 → h1 → buttons on a thin page), hero/end from
    the title + description, the cold open quoting the title's own head.
    None = the manifest is too thin for three chapters (an honest failure,
    never an invented one). The same citation discipline applies — code
    cites line ids exactly like the model would."""
    by_kind: dict[str, list[ManifestLine]] = {}
    for l in lines:
        by_kind.setdefault(l.kind, []).append(l)

    def first(*kinds: str) -> ManifestLine | None:
        for k in kinds:
            if by_kind.get(k):
                return by_kind[k][0]
        return None

    pillar_lines: list[ManifestLine] = []
    for kind in ("h2", "h3", "h1", "button"):
        for l in by_kind.get(kind, []):
            if len(pillar_lines) < _MAX_CHAPTERS and l not in pillar_lines:
                pillar_lines.append(l)
        if len(pillar_lines) >= 3:
            break
    if len(pillar_lines) < 3:
        return None
    title = first("title") or lines[0]
    sub_line = first("description", "h1", "paragraph") or title
    reveal_line = first("h2", "h1") or title
    cold = _fit_to_cap(title.text, TEXT_CAPS[("words", "lines")], "head")
    if not _norm(cold):
        return None
    # 配音兜底 (填全槽的另一半 — voiceover 承诺不随 LLM 耗尽而沉默): speech
    # rides the site's own words read verbatim — the hero card speaks the
    # tagline, each chapter walk speaks its pillar heading, the end card
    # signs off with the title. Narration is the grounding-exempt creative
    # slot, so cited text passes trivially; 60 speech units (CJK-aware) fit
    # even the shortest scene window (validator cap = seconds×20, hero/end
    # floor 3s). A line that trims blank simply drops its key — the scene
    # plays silent.
    def spoken(line: ManifestLine) -> str:
        # 60 speech units (≈3s at the 20/s Latin rate, ≈15 CJK glyphs) fits
        # even the shortest scene window (hero/end floor 3s → cap 60).
        return _fit_units_head(" ".join(line.text.split()), 60)

    narrations = {"hero": spoken(sub_line), "end": spoken(title)}
    for i, pillar in enumerate(pillar_lines[:3], start=1):
        narrations[f"ch{i}_ui"] = spoken(pillar)
    return FilmDirection(
        name=None,
        language=language,
        theme=None,
        pillars=[CopyRef(line=l.id, fit="head") for l in pillar_lines[:3]],
        hero_word=CopyRef(line=title.id, fit="head"),
        hero_sub=CopyRef(line=sub_line.id, fit="head"),
        cold_open=[cold],
        reveal_lead=None,
        reveal_word=CopyRef(line=reveal_line.id, fit="head"),
        reveal_sub=CopyRef(line=sub_line.id, fit="head"),
        end_name=CopyRef(line=title.id, fit="head"),
        end_tagline=CopyRef(line=sub_line.id, fit="head"),
        narrations=narrations,
    )


# ---------------------------------------------------------------------------
# Grounding helpers (pure)
# ---------------------------------------------------------------------------


def _norm(s: str) -> str:
    """Grounding normalization: lowercase, word chars only (``*`` emphasis,
    punctuation, whitespace all vanish) — a trim of a quote still hits."""
    return re.sub(r"[^\w]+", "", s.lower())


# CJK-aware speech measure (Batch 2 旁白/字幕策略): the 20 chars/s narration
# law is Latin-calibrated; a CJK glyph carries a syllable of its own and
# speaks at roughly a quarter of that rate (≈5 chars/s), so it counts 4
# units. The validator's narration cap, the caption cue weights and the
# cue-length cap all read this ONE measure.
_CJK_CHAR = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
# CJK speech weight: one glyph ≈ one spoken syllable ≈ 4 latin chars.
_CJK_UNIT_WEIGHT = 4


def _speech_units(text: str) -> int:
    """Speakable length: CJK glyphs weigh _CJK_UNIT_WEIGHT, everything else 1
    (pure Latin text measures exactly its char count — backward compatible
    with the pre-CJK-aware cap)."""
    return sum(_CJK_UNIT_WEIGHT if _CJK_CHAR.match(ch) else 1 for ch in text)


def _fit_units_head(text: str, cap_units: int) -> str:
    """Largest head segment within the speech-unit budget — a Latin line
    trims at a word boundary, a CJK line hard-cuts (no spaces to trim at)."""
    text = text.strip()
    if _speech_units(text) <= cap_units:
        return text
    used = 0
    cut = 0
    for ch in text:
        u = _CJK_UNIT_WEIGHT if _CJK_CHAR.match(ch) else 1
        if used + u > cap_units:
            break
        used += u
        cut += 1
    head = text[:cut]
    sp = head.rfind(" ")
    return (head[:sp] if sp > 0 else head).strip()


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
    lines (similarity order) turn the blind re-roll into a pick. The cutoff
    sits HIGH (0.5) by law: lower bars let long manifest lines match
    unrelated gibberish (~0.27) and the menu becomes noise — no near
    neighbor means NO candidate list at all."""
    near = difflib.get_close_matches(
        norm_text, [n for n, _ in pairs], n=3, cutoff=0.5
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
        return []  # legacy captions survive on old rows but no longer render
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


# The creative channel (ADR-127): these slots are the film's OWN framing —
# hooks and lead-ins, never product claims — so the grounding check exempts
# them (caps, non-blank and the duplicate guards still apply). Every other
# on-screen slot is a citation and grounds by construction.
_CREATIVE_SLOTS = {("words", "lines"), ("reveal", "lead"), ("divider", "label")}


def validate_storyboard(
    storyboard: FilmStoryboard,
    pages: list[StoryboardPage],
    *,
    narration_required: bool = False,
) -> list[FilmViolation]:
    """Every violation found, in scene order. Empty list = the storyboard may
    proceed to frame allocation. The union corpus grounds every scene.

    ``narration_required`` (2026-10-18 最后一公里 — the 4ad7963e silent-film
    incident): the plan PROMISED voiceover. Individual scenes may stay
    silent by craft (a divider beat, the fast cold open), but an ALL-silent
    board fails the promise — caught here at design time (the bounded
    rewrite repairs it) and again at the run's defensive re-validation,
    never delivered as a successful silent film."""
    violations: list[FilmViolation] = []
    if narration_required and not any(
        getattr(s, "narration", None) for s in storyboard.scenes
    ):
        violations.append(
            FilmViolation(
                NARRATION_MISSING,
                "voiceover is promised but EVERY scene is silent — narrate "
                "the speech-carrying scenes (hero / chapter walks / reveal / "
                "end); only the cold open and divider beats may stay silent. "
                "Key each line by the skeleton's scene keys.",
            )
        )
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
    # REPEATED_VIEW state: (image key, presentation) → first scene index.
    # The frame flag stays in the key — the same view once browser-carded
    # and once full-bleed is the walk's deliberate rhythm, not a repeat.
    seen_views: dict[tuple[str, bool], int] = {}
    usable_views = sum(
        len(p.shots) if p.shots else (1 if p.screenshot_key else 0) for p in pages
    )
    chapter_ordinal = 0
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
            cap = TEXT_CAPS.get((scene.type, slot))
            if cap is not None and len(text.replace("*", "")) > cap:
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
            elif (scene.type, slot) not in _CREATIVE_SLOTS and not grounded(text, corpus):
                violations.append(
                    FilmViolation(
                        TEXT_NOT_GROUNDED,
                        f"{where}.{slot}: «{text[:60]}» traces to no manifest line — quote or trim the page's own copy"
                        + _nearest_hint(_norm(text), pairs),
                    )
                )

        # 配音词 sanity bound (never grounded — speech rephrases the page's
        # facts by design). The cap is the DESIGN-TIME fit law, calibrated
        # to the REAL synthesized rate (≈13 latin units/s at 1.0×, measured
        # against decoded TTS audio — CJK glyphs weigh _CJK_UNIT_WEIGHT
        # each): a passing line reads inside its scene at NATURAL speed, so
        # the synthesis ladder (≤1.35×) stays headroom for voice variance,
        # never the plan. The floor fits even the shortest scene through
        # the ladder (38 units ≈ 2.9s natural → inside a 2s+allowance
        # window at cap speed). Over cap = 打回: the bounded rewrite
        # shortens the line or drops the scene's narration (a new version
        # over the current draft), never a stretched window.
        narration = getattr(scene, "narration", None)
        if narration is not None:
            if not _norm(narration):
                violations.append(
                    FilmViolation(CONSTRAINT_VIOLATION, f"{where}.narration: blank")
                )
            else:
                narr_cap = max(38, int(scene.seconds * 13))
                units = _speech_units(narration)
                if units > narr_cap:
                    violations.append(
                        FilmViolation(
                            CONSTRAINT_VIOLATION,
                            f"{where}.narration: {units} speech units over the "
                            f"{narr_cap} cap for a {scene.seconds:g}s scene "
                            "(≈13 latin chars/s, CJK glyph = 4) — shorten the "
                            "line or leave this scene silent",
                        )
                    )

        # Within-scene duplicate copy.
        normed = [_norm(text) for _, text in strings]
        if len(set(normed)) != len(normed):
            violations.append(
                FilmViolation(CONSTRAINT_VIOLATION, f"{where}: duplicate copy within one screen")
            )
        # A whole screen repeated elsewhere (same type, same strings). ui
        # scenes key on their view AND presentation — two walks of
        # DIFFERENT views, or the same view once browser-carded and once
        # full-bleed, are not a repeat.
        signature: tuple = (
            ("ui", scene.page, scene.shot, scene.frame, tuple(sorted(normed)))
            if scene.type == "ui"
            # The roll's ORDER is the screen (it lands on the last word) —
            # chapters sharing a kicker with cyclically-shifted rolls are
            # not repeats.
            else ("divider", normed[0], tuple(normed[1:]))
            if scene.type == "divider"
            else (scene.type, tuple(sorted(normed)))
        )
        if signature in seen_screens:
            violations.append(
                FilmViolation(CONSTRAINT_VIOLATION, f"{where}: repeats another scene's screen verbatim")
            )
        seen_screens.add(signature)

        # EMPTY_CHAPTER: a chapter card no page walk follows (scanning until
        # the next structural scene — a plate between card and walk stays
        # legal). The walk is the chapter's substance — a divider straight
        # into another card is padding dressed as structure. The
        # attributable fix is fewer pillars (the model owns the chapter
        # count; the views are the world's).
        if scene.type == "divider":
            chapter_ordinal += 1
            has_walk = False
            for later in scenes[idx + 1:]:
                if later.type in ("divider", "reveal", "end"):
                    break
                if later.type == "ui":
                    has_walk = True
                    break
            if not has_walk:
                violations.append(
                    FilmViolation(
                        EMPTY_CHAPTER,
                        f"{where}: chapter {chapter_ordinal} has no page walk "
                        f"(the world offers {usable_views} usable views → at most "
                        f"{max(usable_views - 1, 0)} walked chapters) — cite fewer "
                        "pillars, never a chapter card without its walk",
                    )
                )

        # PADDING_SCENE (b): adjacent same-type text scenes saying nearly the
        # same thing twice (a padding beat, not an echo — the deliberate
        # cross-type callback stays legal). ui/divider adjacency is already
        # judged by the view/roll signatures above, never here.
        if (
            idx > 0
            and scenes[idx - 1].type == scene.type
            and scene.type not in ("ui", "divider")
        ):
            prev_norm = "".join(_norm(t) for _, t in _screen_strings(scenes[idx - 1]))
            cur_norm = "".join(_norm(t) for _, t in strings)
            if (
                prev_norm
                and cur_norm
                and difflib.SequenceMatcher(None, prev_norm, cur_norm).ratio() >= 0.8
            ):
                violations.append(
                    FilmViolation(
                        PADDING_SCENE,
                        f"{where}: near-verbatim repeat of scene[{idx - 1}] — "
                        "two adjacent beats saying the same thing is padding",
                    )
                )

        # List-size caps.
        if scene.type == "words" and len(scene.lines) > _LIST_CAPS["words.lines"]:
            violations.append(FilmViolation(CONSTRAINT_VIOLATION, f"{where}: {len(scene.lines)} lines over {_LIST_CAPS['words.lines']}"))
        if scene.type == "divider" and len(scene.roll) > _LIST_CAPS["divider.roll"]:
            violations.append(FilmViolation(CONSTRAINT_VIOLATION, f"{where}: roll of {len(scene.roll)} over {_LIST_CAPS['divider.roll']}"))
        if scene.type == "reveal" and not (0.8 <= scene.lead_seconds <= scene.seconds - 2.0):
            violations.append(
                FilmViolation(
                    DURATION_INVALID,
                    f"{where}: lead hold {scene.lead_seconds}s outside 0.8..{scene.seconds - 2.0:g}s (the word phase needs 2s)",
                )
            )
        if scene.type == "ui":
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
            # PADDING_SCENE (a): a static screenshot with zero camera beats
            # is a padding shot, not a walk (defense-in-depth — the schema's
            # min_length=1 already bars this on the parsed path).
            if not scene.focuses:
                violations.append(
                    FilmViolation(
                        PADDING_SCENE,
                        f"{where}: no camera beat — a static screenshot padding the runtime",
                    )
                )
            # REPEATED_VIEW: the same captured image with the same
            # presentation twice. Keyed on the IMAGE, not the shot index —
            # a capture that stored identical pixels under two shot keys
            # still repeats on screen.
            if 0 <= scene.page < len(pages):
                view_page = pages[scene.page]
                image_key = (
                    view_page.shots[scene.shot].key
                    if view_page.shots and scene.shot < len(view_page.shots)
                    else view_page.screenshot_key
                )
                if image_key is not None:
                    view_sig = (image_key, scene.frame)
                    first_at = seen_views.get(view_sig)
                    if first_at is not None:
                        violations.append(
                            FilmViolation(
                                REPEATED_VIEW,
                                f"{where}: repeats scene[{first_at}]'s web shot "
                                f"({image_key}, {'browser frame' if scene.frame else 'full-bleed'})",
                            )
                        )
                    else:
                        seen_views[view_sig] = idx
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


def _track_beats(track: Music | None) -> list[float] | None:
    """The bed's seed-time beat grid (Music.meta.beats) — the dock markdown
    and the run's snap read this ONE extraction so both show/render the same
    timing. None = the track carries no grid (degrade-honest)."""
    raw = (track.meta or {}).get("beats") if track is not None else None
    if not isinstance(raw, list):
        return None
    beats = [
        float(b) for b in raw
        if isinstance(b, (int, float)) and not isinstance(b, bool)
    ]
    return beats or None


def _track_bpm(track: Music | None) -> float | None:
    raw = (track.meta or {}).get("bpm") if track is not None else None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool) and raw > 0:
        return float(raw)
    return None


def _beat_interval(beats: list[float] | None, bpm: float | None) -> float | None:
    """Seconds per beat for display: the declared BPM wins; a beat grid
    without BPM falls back to the grid's median gap."""
    if bpm is not None:
        return 60.0 / bpm
    if beats is None or len(beats) < 2:
        return None
    gaps = [b - a for a, b in zip(beats, beats[1:]) if b > a]
    if not gaps:
        return None
    gaps.sort()
    return gaps[len(gaps) // 2]


async def _track_beats_backfilled(db: AsyncSession, track: Music | None) -> list[float] | None:
    """The bed's beat grid, backfilled on first need (ADR-130 §1 — 先走现
    有分析补齐): a track whose meta carries no grid gets ONE analysis from
    its stored bytes (the boot-time seed reconcile's own path), persisted
    back onto the row so every later seat reads it. Still None = the rhythm
    honestly cannot be obtained — the caller fails loudly, never a
    fabricated beat."""
    beats = _track_beats(track)
    if beats is not None or track is None:
        return beats
    try:
        from app.providers.storage import read  # deferred: storage edge
        from app.tools.music.beats import analyze_beat_grid  # deferred: cycle

        grid = analyze_beat_grid(await read(track.file_path))
    except Exception as e:  # noqa: BLE001 — storage/analysis best-effort
        logger.warning("film_beat_backfill_failed", track_id=str(track.id), error=str(e))
        return None
    if grid is None:
        return None
    track.meta = {**(track.meta or {}), **grid}
    await db.flush()
    logger.info("film_beat_backfilled", track_id=str(track.id))
    return _track_beats(track)


async def _resolve_track_backfilled(
    db: AsyncSession, project: Project, music_mood: str | None
) -> Music | None:
    """resolve_film_music + the beat-grid backfill in one seat: the design
    beat's snapshot, the dock's markdown timing and the node's snap all read
    the SAME grid (展示=执行 down to the beat)."""
    track = await resolve_film_music(db, project, music_mood)
    if track is not None:
        await _track_beats_backfilled(db, track)
    return track


# Caption cue splitting (two stages, terminators kept on the cue they close):
# sentence enders — CJK 。！？ and Latin !? always count; the Latin full stop
# counts only when it ends a sentence (followed by whitespace or the end of
# the string), so decimals and version strings survive intact. Clause marks
# then sub-split each sentence.
_SENTENCE_END = re.compile(r"[。！？!?]|\.(?=\s|$)")
_CLAUSE_END = re.compile(r"[；;，,、]")


def _split_keep(text: str, pattern: re.Pattern) -> list[str]:
    """Split on the pattern's matches, KEEPING each terminator on the piece
    it closes (the cue reads with its punctuation)."""
    pieces: list[str] = []
    start = 0
    for m in pattern.finditer(text):
        pieces.append(text[start : m.end()])
        start = m.end()
    if start < len(text):
        pieces.append(text[start:])
    return [p for p in (p.strip() for p in pieces) if p]


def narration_caption_cues(
    text: str, *, window_s: float, spoken_s: float | None
) -> list[dict[str, Any]]:
    """Project one scene's narration into deterministic caption cues.

    The split follows sentence/clause punctuation, CJK and Latin alike:
    sentence enders first (。！？!? — plus the Latin full stop ONLY when it
    ends a sentence, i.e. followed by whitespace or the string's end, so
    "2.4" and "v1.2" never split), then clause marks (；;，,、) within each
    sentence. Cue durations are speech-unit-weighted across the REAL decoded
    narration span (capped at the scene window — the renderer trims audio
    there), never a second timing source; a CJK glyph weighs
    ``_CJK_UNIT_WEIGHT`` Latin chars so mixed-language cues time honestly.
    One short line = one cue. The render contract stores ``at`` + ``end`` +
    ``text``; the last cue closes at the spoken span, never lingers through
    a silent scene tail.
    """
    pieces = [
        clause
        for sentence in _split_keep(text.strip(), _SENTENCE_END)
        for clause in _split_keep(sentence, _CLAUSE_END)
    ]
    if not pieces:
        return []
    chunks: list[str] = []
    for piece in pieces:
        # Keep a cue readable on one line (≈42 speech units — a CJK glyph is
        # double-width on screen AND slower to read); hard-split only
        # overlong clauses, at a word/clause boundary when one exists.
        while _speech_units(piece) > 42:
            used = 0
            cut_at = 0
            for ch in piece:
                u = _CJK_UNIT_WEIGHT if _CJK_CHAR.match(ch) else 1
                if used + u > 42:
                    break
                used += u
                cut_at += 1
            cut = piece[:cut_at]
            split = max(cut.rfind(" "), cut.rfind("，"), cut.rfind(","))
            head = (cut[:split] if split >= 18 else cut).strip()
            if head:
                chunks.append(head)
            piece = piece[len(head):].strip()
        if piece:
            chunks.append(piece)
    if not chunks:
        return []
    timeline = min(
        max(spoken_s or window_s, 0.4),
        max(window_s, 0.4),
    )
    weights = [max(2, _speech_units(re.sub(r"[^\w]+", "", c))) for c in chunks]
    total = sum(weights)
    cues: list[dict[str, Any]] = []
    starts = [
        round(timeline * sum(weights[:i]) / total, 2)
        for i in range(len(chunks))
    ]
    for i, (chunk, start) in enumerate(zip(chunks, starts, strict=True)):
        end = starts[i + 1] if i + 1 < len(starts) else timeline
        cues.append({"at": start, "end": round(end, 2), "text": chunk})
    return cues


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


def _camera_walk(
    focuses: list[FilmFocus], page: StoryboardPage, shot_idx: int, seconds: float
) -> list[dict[str, Any]]:
    """Expand the storyboard's camera ARRIVALS into the skill's walk: start
    wide, hold, glide to each target, then settle with a small push. The
    storyboard stays compact (one code-picked arrival per view today); the
    render contract carries the full camera path so the renderer never
    invents easing anchors."""
    arrivals = [_resolve_focus(f, page, shot_idx) for f in focuses]
    if not arrivals:
        arrivals = [{"at": 2.0, "x": 0.5, "y": 0.45, "zoom": 1.6}]
    walk: list[dict[str, Any]] = [
        {"at": 0.0, "x": 0.5, "y": 0.5, "zoom": 1.0}
    ]

    def push(at: float, point: dict[str, Any]) -> None:
        at = round(max(0.0, min(at, seconds)), 3)
        if at <= walk[-1]["at"] + 0.05:
            return
        walk.append(
            {
                "at": at,
                "x": round(float(point["x"]), 3),
                "y": round(float(point["y"]), 3),
                "zoom": round(float(point["zoom"]), 3),
            }
        )

    previous = walk[0]
    previous_at = 0.0
    for target in arrivals:
        arrival = float(target["at"])
        if arrival <= 0.05 and len(walk) == 1:
            # A hand-built/legacy storyboard may name an immediate target —
            # then the walk honestly STARTS there instead of dropping it.
            walk[0] = {
                "at": 0.0,
                "x": round(float(target["x"]), 3),
                "y": round(float(target["y"]), 3),
                "zoom": round(float(target["zoom"]), 3),
            }
            previous = walk[0]
            continue
        # The approach holds the previous frame before the glide (the skill's
        # 2.5-beat lead, shortened honestly on short scenes). A hold that
        # would land AT/AFTER the arrival is no hold at all — skip it so the
        # arrival itself never gets absorbed by the dedup guard.
        hold = max(previous_at + 0.2, arrival - 1.25)
        if hold < arrival - 0.05:
            push(hold, previous)
        push(arrival, target)
        previous = walk[-1]
        previous_at = previous["at"]
    # The tail never freezes: settle on the last target with a tiny push.
    # The push only ever goes IN (cap = the zoom law's max) — never pull
    # back below the arrival the glide just reached.
    push(
        seconds,
        {**previous, "zoom": min(_ZOOM_RANGE[1], float(previous["zoom"]) + 0.05)},
    )
    return walk


def build_film_spec(
    storyboard: FilmStoryboard,
    pages: list[StoryboardPage],
    *,
    narration: dict[int, tuple[str, float]] | None = None,
    music: dict[str, Any] | None = None,
    aspect: str = "16:9",
    frames: list[int] | None = None,
    storyboard_digest: str | None = None,
    execution_digest: str | None = None,
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
    ``storyboard_digest`` / ``execution_digest`` = the design beat's stamps
    (ADR-129): the spec carries them as ``provenance`` so 呈现稿 digest =
    run context digest = render spec digest verifies byte-for-byte; None on
    snapshot-less births (the keys stay out)."""
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
    beat_s = _beat_interval(
        (music or {}).get("beats"), (music or {}).get("bpm")
    )
    divider_ordinal = 0
    cursor = 0  # absolute frames — the reveal's word onset snaps to the grid
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
                    # B2: element-named arrivals resolve here; the `element`
                    # key never leaks into the render contract. The compact
                    # arrivals expand into the full wide → hold → glide →
                    # settle camera walk (the renderer never invents anchors).
                    "focuses": _camera_walk(
                        list(scene.focuses), page, scene.shot, n / FILM_FPS
                    ),
                    # Legacy ui captions never serialize — the narration
                    # caption track (below) owns the ``captions`` key.
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
            # lead → beat pause → word (the reference arc): the lead holds
            # its lead_seconds, then the word lands ON the music grid —
            # the next beat at/after the lead's end, plus one real beat of
            # black pause. No grid = the silent-cut fallback (a music-less
            # film has no beat to land on — the half-second hold is a plain
            # pause, never passed off as a beat). The word phase always
            # keeps ≥1s.
            word_f = round(scene.lead_seconds * FILM_FPS) + FILM_FPS // 2
            if beat_s:
                lead_end_abs = cursor / FILM_FPS + scene.lead_seconds
                beats_list = (music or {}).get("beats")
                nxt = (
                    min((b for b in beats_list if b >= lead_end_abs - 1e-9), default=None)
                    if isinstance(beats_list, list)
                    else None
                )
                word_abs = (
                    nxt + beat_s
                    if nxt is not None
                    else math.ceil(lead_end_abs / beat_s - 1e-9) * beat_s + beat_s
                )
                word_f = round((word_abs - cursor / FILM_FPS) * FILM_FPS)
            word_f = max(FILM_FPS, min(word_f, n - FILM_FPS))
            scenes.append(
                {
                    "type": "reveal",
                    "frames": n,
                    "lead": scene.lead,
                    "lead_frames": word_f,
                    "word": scene.word,
                    "sub": scene.sub,
                }
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
        # 配音轨 (ADR-130): the scene's narration object key, baked by
        # code from the synthesis map — absent = the scene plays silent. The
        # decoded spoken seconds also drive the deterministic caption cues,
        # so the words on screen ride the same timing truth as the audio.
        narration_entry = narration.get(idx)
        if narration_entry is not None:
            audio_key, spoken_seconds = narration_entry
            scenes[-1]["audio"] = audio_key
            spoken_text = getattr(scene, "narration", None)
            if spoken_text:
                cues = narration_caption_cues(
                    spoken_text,
                    window_s=n / FILM_FPS,
                    spoken_s=spoken_seconds,
                )
                if cues:
                    scenes[-1]["captions"] = cues
        cursor += n
    spec = {
        "family": "film",
        "name": storyboard.name,  # null-read tolerant (two-source law)
        "theme": theme,
        "aspect": aspect,
        "fps": FILM_FPS,
        "scenes": scenes,
    }
    if music is not None:
        spec["music"] = music
    if storyboard_digest or execution_digest:
        # ADR-129 provenance: the design beat's digests ride the spec so
        # 呈现稿 = run context = render spec verifies byte-for-byte.
        spec["provenance"] = {
            k: v
            for k, v in {
                "storyboard_digest": storyboard_digest,
                "execution_digest": execution_digest,
            }.items()
            if v
        }
    return spec


def storyboard_presentation(
    storyboard: FilmStoryboard,
    pages: list[StoryboardPage],
    *,
    aspect: str = "16:9",
    music: str | None = None,
    beats: list[float] | None = None,
    bpm: float | None = None,
    captions: bool = False,
) -> str:
    """The design beat's FACT SHEET for the presenting model (2026-10-18
    裁决 — 工具产生真实分镜, LLM 负责唯一表达): every user-visible fact
    of the SAVED board, projected off the SAME execution timeline the run
    consumes (``allocate_frames`` → ``snap_frames_to_beats`` over the
    resolved bed grid — the presenting model never re-derives times from
    raw seconds). This rides the ToolObservation; the chat model's ONE
    presentation message renders it (short intro / readable scene table /
    next step). The program no longer publishes its own markdown row —
    one storyboard, one voice.

    Completeness law (对内必须足够准确, 对外可以简洁): the name and the
    ACTUAL narration language, aspect/fps, the execution timeline's total
    seconds + frames, the bed label + BPM, per-scene order / type / arc
    role / start–end / duration / frames, what the viewer sees, the camera
    walk (focus elements resolved to their captured text — never a raw DOM
    id), the VERBATIM narration per scene (a silent scene says so — the
    model never guesses), and the compact source list (host+path+title —
    traceable without line-id spam)."""
    frames = allocate_frames(storyboard)
    if beats:
        frames = snap_frames_to_beats(storyboard, frames, beats)
    total_frames = sum(frames)
    total = round(total_frames / FILM_FPS, 1)

    head_bits = [
        f"name: {storyboard.name}" if storyboard.name else "name: (untitled)",
        f"narration language: {storyboard.language}",
        f"aspect {aspect}",
        f"{FILM_FPS}fps",
        f"total {total:g}s · {total_frames} frames",
    ]
    if music:
        head_bits.append(f"music: {music}")
    if captions and any(s.narration for s in storyboard.scenes):
        head_bits.append("captions: narration")

    def page_label(p: int) -> str:
        if not 0 <= p < len(pages):
            return f"page {p}"
        page = pages[p]
        path = urlparse(page.research.url).path.strip("/")
        base = f"{page.host}/{path}" if path else page.host
        title = (page.research.title or "").strip()
        return f"{base} \"{title}\"" if title else base

    # Arc roles, derived from the scene order alone (deterministic).
    roles: list[str] = []
    chapter = 0
    revealed = False
    for s in storyboard.scenes:
        if s.type == "divider":
            chapter += 1
            roles.append(f"chapter {chapter} card")
        elif s.type == "ui":
            if revealed:
                roles.append("proof walk")
            elif chapter:
                roles.append(f"chapter {chapter} walk")
            else:
                roles.append("home walk")
        elif s.type == "words":
            roles.append("cold open")
        elif s.type == "hero":
            roles.append("brand hero")
        elif s.type == "plate":
            roles.append("numbers plate")
        elif s.type == "reveal":
            roles.append("reveal")
            revealed = True
        else:
            roles.append("closing card")

    def scene_lines(idx: int, s: FilmScene) -> list[str]:
        start = round(sum(frames[: idx - 1]) / FILM_FPS, 1)
        end = round(sum(frames[:idx]) / FILM_FPS, 1)
        span = round(frames[idx - 1] / FILM_FPS, 1)
        out = [
            f"scene {idx} · {s.type} · {roles[idx - 1]} · "
            f"{start:g}–{end:g}s · {span:g}s · {frames[idx - 1]} frames"
        ]
        if s.type == "words":
            out.append(
                f"  shows: {' / '.join(s.lines)}{' (dark)' if s.dark else ''}"
            )
        elif s.type == "hero":
            out.append(f'  shows: "{s.word}" — {s.sub}')
        elif s.type == "ui":
            heading = None
            if 0 <= s.page < len(pages):
                pg = pages[s.page]
                if pg.shots and s.shot < len(pg.shots):
                    heading = pg.shots[s.shot].heading or None
            label = page_label(s.page)
            out.append(
                f'  shows: the "{heading}" section — {label} shot {s.shot}'
                if heading
                else f"  shows: {label} shot {s.shot}"
            )
            out[-1] += " · browser frame" if s.frame else " · full-bleed"
            moves: list[str] = []
            for f in s.focuses:
                target = None
                if f.element is not None and 0 <= s.page < len(pages):
                    pg = pages[s.page]
                    elts = (
                        pg.shots[s.shot].elements
                        if pg.shots and s.shot < len(pg.shots)
                        else []
                    )
                    el = next((e for e in elts if e.id == f.element), None)
                    if el is not None:
                        target = f'"{el.text}" ({el.kind})' if el.text else el.kind
                moves.append(
                    f"push to {target} at {f.at:g}s"
                    if target
                    else f"center push at {f.at:g}s"
                )
            if moves:
                out.append("  camera: wide → " + " → ".join(moves) + " → settle")
        elif s.type == "divider":
            out.append(f"  shows: {s.label} — {' · '.join(s.roll)}")
        elif s.type == "plate":
            cards = " · ".join(
                f"{c.big} — {c.label}" if c.big else c.label for c in s.cards
            )
            out.append(
                f"  shows: {s.title} — {cards}" if cards else f"  shows: {s.title}"
            )
        elif s.type == "reveal":
            out.append(f"  shows: lead {s.lead_seconds:g}s: {s.lead}")
            out.append(f'  then: "{s.word}" — {s.sub}')
        elif s.type == "end":
            out.append(f"  shows: {s.name} — {s.tagline}")
        out.append(
            f'  narration: "{s.narration}"'
            if s.narration
            else "  narration: (silent — no narration by design)"
        )
        return out

    sources = " · ".join(dict.fromkeys(page_label(p) for p in range(len(pages))))
    lines = [
        " · ".join(head_bits),
        f"sources: {sources}",
        "",
    ]
    for i, s in enumerate(storyboard.scenes, 1):
        lines.extend(scene_lines(i, s))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The storyboard agent
# ---------------------------------------------------------------------------


def current_direction_dict(storyboard: FilmStoryboard) -> dict[str, Any]:
    """The board under review as the director's revision base (ADR-129 修
    订基于当前稿): the resolved creative slots keyed like the direction's
    own output — real strings, never citations. The model re-cites whatever
    it keeps from the manifest (its citation universe) and rewrites only
    what the feedback names."""
    cold_open: list[str] = []
    hero: dict[str, str] = {}
    reveal: dict[str, str] = {}
    end: dict[str, str] = {}
    pillars: list[str] = []
    narrations: list[dict[str, Any]] = []
    for i, s in enumerate(storyboard.scenes, 1):
        if s.type == "words" and not cold_open:
            cold_open = list(s.lines)
        elif s.type == "hero":
            hero = {"hero_word": s.word, "hero_sub": s.sub}
        elif s.type == "divider":
            pillars.append(s.label)
        elif s.type == "reveal":
            reveal = {"reveal_lead": s.lead, "reveal_word": s.word, "reveal_sub": s.sub}
        elif s.type == "end":
            end = {"end_name": s.name, "end_tagline": s.tagline}
        if s.narration:
            narrations.append({"scene": i, "type": s.type, "text": s.narration})
    return {
        "name": storyboard.name,
        "language": storyboard.language,
        "pillars": pillars,
        **hero,
        "cold_open": cold_open,
        **reveal,
        **end,
        "narrations": narrations,
    }


def _assemble(
    pages: list[dict[str, Any]],
    skeleton: dict[str, Any],
    instruction: str | None,
    focus: str | None,
    language: str | None,
    current: dict[str, Any] | None,
    page_images: list[MediaInput],
    voiceover: bool = True,
) -> AssembleResult:
    """Purity by signature: the model sees the manifests (its grounding
    universe), the code-built skeleton (its answer sheet — ADR-127), the
    run's instruction, the slot's focus steer, the plan's pinned film
    language (None = declare it from the page), the board under review when
    the call is a feedback revision (None = a first design), the page
    screenshots, and the plan's VOICEOVER promise (2026-10-18 — the silent
    v2 incident: the director never knew the film ships with voice, so a
    'visual-first' steer read as all-silent) — nothing else."""
    return (
        {
            "pages": pages,
            "skeleton": skeleton,
            "instruction": instruction,
            "focus": focus,
            "language": language,
            "current": current,
            "voiceover": voiceover,
        },
        page_images,
    )


film_director = Agent[FilmDirection](
    name="film_director",
    prompt="film_director.j2",
    schema=FilmDirection,
    system=(
        "You are a film director. The film's structure is fixed — scene "
        "order, durations and camera are decided for you; you answer only "
        "the creative slots: pick the chapters, cite every factual on-screen "
        "string from the page's own copy by line number (you never write "
        "those), and write the creative channel in your own words — the "
        "cold-open hooks, the reveal's lead-in and the narration. Hooks, "
        "never claims: the creative channel never states a product fact the "
        "page does not state."
    ),
    assemble=_assemble,
    temperature=0.5,
    packs=["launch-film"],
    # The screenshots ground the pillar/caption picks; a multimodal failure
    # degrades to text-only (manifests still carry the copy).
    media_text_fallback=True,
    # Streaming transport (2026-10-16, 6c2103ee 取证): the non-stream form
    # was an all-or-nothing black box — a provider-slow day read as a hang,
    # and every 300s read timeout burned the whole腹稿 on a blind retry
    # (worst ≈ 15 min of "Drafting the storyboard…"). Reasoning chunks keep
    # the channel alive; the orchestrator bounds total generation time.
    stream=True,
    timeout_s=300,
)


def page_prompt_dict(
    page: StoryboardPage, index: int, lines: list[ManifestLine]
) -> dict[str, Any]:
    """One page's prompt block. ``lines`` = the page's slice of the global
    citation manifest (行 ID 化 — the j2 prints them numbered; the model
    cites ids, never strings). ``shots`` = the captured views the ui scene
    may pick from (0 = the fold; ADR-121 B1)."""
    r = page.research
    return {
        "index": index,
        "url": r.url,
        "host": page.host,
        "title": r.title,
        "has_screenshot": bool(page.shots) or page.screenshot_key is not None,
        "lines": [
            {"id": l.id, "kind": l.kind, "text": l.text}
            for l in lines
            if l.page == index
        ],
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
# Shared seats (ADR-130 — the run node and the plan-stage draft ride the
# SAME load/orchestration loop; no second orchestration chain, ADR-028)
# ---------------------------------------------------------------------------


def skeleton_prompt_dict(
    skeleton: _Skeleton, pages: list[StoryboardPage]
) -> dict[str, Any]:
    """The skeleton's prompt block (ADR-127): the maximal 5-chapter arc the
    j2 prints as the answer sheet — scene keys (the narration dictionary's
    lookup), types, and each ui scene's assigned view + code-picked camera
    target. Durations are deliberately NOT printed (code-owned and trimmed
    at assembly; a printed number would read as a writable slot)."""
    plan = _scene_plan(_MAX_CHAPTERS, skeleton)
    scenes = []
    for s in plan:
        entry: dict[str, Any] = {"key": s.key, "type": s.type}
        if s.chapter is not None:
            entry["chapter"] = s.chapter
        if s.view is not None:
            page_idx, shot_idx = s.view
            focus = skeleton.focuses[s.view]
            entry["page"] = page_idx
            entry["shot"] = shot_idx
            entry["host"] = pages[page_idx].host
            entry["camera"] = (
                {"element": focus.element}
                if focus.element is not None
                else {"x": focus.x, "y": focus.y, "zoom": focus.zoom}
            )
        scenes.append(entry)
    return {
        "max_chapters": _MAX_CHAPTERS,
        "min_chapters": 3,
        "has_plate": bool(skeleton.plate_lines),
        "plate_chapter": _plate_chapter(_MAX_CHAPTERS, skeleton),
        "scenes": scenes,
    }


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
                # The dock seat may have re-read a just-committed PENDING
                # capture before the wait; populate_existing makes this
                # post-wait read see the worker's COMPLETED write instead of
                # the session's identity-map copy.
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    pages: list[StoryboardPage] = []
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
    current: FilmStoryboard | None = None,
    on_reject=None,
    allow_fixed_fallback: bool = True,
    voiceover: bool = True,
) -> FilmStoryboard:
    """THE bounded direction loop (打回有界, ADR-127): the skeleton is
    code-owned; up to 1 + MAX_REWRITES direction candidates, each re-called
    with the violation echo (never a blind re-roll), each spliced into the
    skeleton by ``assemble_storyboard`` and then facing the validator.
    Returns the first assembly that passes.

    Terminal ladder (honest at every rung): candidate exhaustion or an
    LLM failure (schema terminal / transport) falls to ``fixed_direction``
    — the no-LLM code-filled direction over the SAME skeleton — and only
    ITS failure raises ``FilmStoryboardRejected`` (the caller stamps its
    own terminal). ``allow_fixed_fallback=False`` closes that rung: the
    DESIGN journey (the dock seats — a user is watching and will judge the
    board) fails honestly with the original rejection instead of shipping a
    fixed board that masquerades as a designed one (the 2026-10-17
    Decline/Accept incident — 180s budget exhausted mid-generation, the
    fallback's button-copy roll was then presented as the film). The worker
    node keeps the fallback (no user in the loop mid-run — the 2026-10-16
    拍板 stands there). A view-poor world (< ``_MIN_VIEWS`` usable page
    views) never reaches the model at all: the arc cannot stand without
    the product's real pages, so the rejection fires BEFORE an LLM call is
    burned (the skill's own law — a blocked site means stop and ask for
    screenshots). ``on_reject(attempt, violations, feedback)`` is the
    caller's logging hook."""
    lines = build_line_manifest(pages)
    skeleton = build_skeleton(pages, lines)
    if len(skeleton.views) < _MIN_VIEWS:
        logger.info(
            "film_direction_preflight_failed",
            views=len(skeleton.views),
            need=_MIN_VIEWS,
        )
        raise FilmStoryboardRejected(
            ["INSUFFICIENT_VIEWS"],
            f"only {len(skeleton.views)} captured page views (need {_MIN_VIEWS}) — "
            "the film shows the product's real pages; re-send the link to re-capture.",
            user_key="film_views_missing",
        )
    prompt_pages = [page_prompt_dict(p, i, lines) for i, p in enumerate(pages)]
    prompt_skeleton = skeleton_prompt_dict(skeleton, pages)
    # 修订基于当前稿 (ADR-129): a feedback redraft shows the director the
    # board under review — its slots are the revision base (keep whatever
    # the feedback does not name), never a from-scratch re-roll.
    prompt_current = current_direction_dict(current) if current is not None else None
    violations: list[FilmViolation] = []
    feedback: str | None = None
    try:
        async with asyncio.timeout(_DIRECTION_BUDGET_S):
            for attempt in range(1 + MAX_REWRITES):
                direction = await film_director.call(
                    pages=prompt_pages,
                    skeleton=prompt_skeleton,
                    instruction=instruction,
                    focus=focus,
                    language=language,
                    current=prompt_current,
                    page_images=page_images,
                    repair_feedback=feedback,
                    voiceover=voiceover,
                )
                resolved, violations = assemble_storyboard(
                    skeleton, direction, lines, pinned_language=language
                )
                if resolved is not None:
                    violations = validate_storyboard(
                        resolved, pages, narration_required=voiceover
                    )
                    if not violations:
                        return resolved
                feedback = format_violations(violations)
                if on_reject is not None:
                    notification = on_reject(attempt, violations, feedback)
                    if inspect.isawaitable(notification):
                        await notification
        rejection: Exception = FilmStoryboardRejected(
            sorted({v.code for v in violations}), feedback or ""
        )
    except TimeoutError:
        logger.warning("film_direction_budget_exhausted", budget_s=_DIRECTION_BUDGET_S)
        rejection = LLMError("Storyboard generation exceeded its total budget", user_key="film_storyboard_timeout")
    except (LLMSchemaError, LLMError) as exc:
        rejection = exc
    # 固定分镜兜底 (2026-10-16 用户拍板; 2026-10-18 收窄到无人值守道):
    # the LLM path exhausted itself — the SAME skeleton still stands, so
    # code fills every slot from the manifest's own semantics and the film
    # ships. Only a world too thin for three chapters (or a fixed assembly
    # that somehow fails its own validator) falls through to the honest
    # rejection. The design journey closes this rung entirely
    # (``allow_fixed_fallback=False``): a watched board is designed or it
    # fails honestly — never a fixed board masquerading as a designed one.
    if allow_fixed_fallback:
        logger.info("film_direction_fixed_fallback", reason=str(rejection)[:200])
        fixed = fixed_direction(lines, language=language)
        if fixed is not None:
            resolved, fviolations = assemble_storyboard(
                skeleton, fixed, lines, pinned_language=language
            )
            if resolved is not None:
                fviolations = validate_storyboard(
                    resolved, pages, narration_required=voiceover
                )
                if not fviolations:
                    logger.info(
                        "film_fixed_storyboard_used",
                        scenes=len(resolved.scenes),
                        seconds=sum(s.seconds for s in resolved.scenes),
                    )
                    return resolved
            logger.warning(
                "film_fixed_storyboard_rejected",
                detail=format_violations(fviolations)[:400],
            )
    raise rejection


async def _await_captures_settled(project_id: UUID) -> None:
    """Wait for the project's in-flight web_page captures to reach a terminal
    state (bounded by ``_CAPTURE_SETTLE_WAIT_S``). The waited set IS the
    design's grounding universe — every web_page asset of the project the
    draft will read (``load_storyboard_pages`` loads them all), discovered
    sub-pages included (they birth mid-wait as the parent's capture
    settles). Polls on FRESH sessions (the get_understanding read-wait's
    law — the turn's own session never survives a sleep). A FAILED capture
    is terminal (the wait ends; a too-thin world meets the preflight's
    honest rejection), but a wait that outlasts its ceiling with pages
    still in flight raises ``FilmCaptureTimeout`` — never a silent draft
    over a half-captured world (2026-10-17 用户拍板)."""
    import asyncio
    import time

    from app.models.database import AsyncSessionLocal  # deferred: worker seat

    deadline = time.monotonic() + _CAPTURE_SETTLE_WAIT_S
    await asyncio.sleep(_CAPTURE_SETTLE_POLL_S)  # the absorb lands first
    while True:
        async with AsyncSessionLocal() as poll:
            pending = list(
                (
                    await poll.execute(
                        select(Asset.title, Asset.processing_status).where(
                            Asset.project_id == project_id,
                            Asset.type == AssetType.WEB_PAGE,
                            Asset.processing_status.in_(
                                (AssetStatus.PENDING, AssetStatus.PROCESSING)
                            ),
                        )
                    )
                ).all()
            )
        if not pending:
            return
        if time.monotonic() >= deadline:
            names = sorted(str(title) for title, _status in pending)
            logger.warning(
                "film_capture_wait_timeout",
                project_id=str(project_id),
                pending=names,
                budget_s=_CAPTURE_SETTLE_WAIT_S,
            )
            raise FilmCaptureTimeout(
                f"capture still in flight after {_CAPTURE_SETTLE_WAIT_S:.0f}s "
                f"— waiting on: {', '.join(names)}"
            )
        await asyncio.sleep(_CAPTURE_SETTLE_POLL_S)


async def draft_film_storyboard(
    db: AsyncSession,
    project: Project,
    *,
    instruction: str | None,
    focus: str | None = None,
    language: str | None = None,
    current: FilmStoryboard | None = None,
    on_progress=None,
    voiceover: bool = True,
) -> tuple[FilmStoryboard, list[StoryboardPage]] | None:
    """The plan-stage storyboard draft: the SAME loop the node runs, against
    the project's READY pages. Returns ``(storyboard, pages)`` — the caller
    needs the pages for the markdown's source line. None honestly when the
    draft can't stand (no readable page / schema terminal / grounding
    exhaustion); the dock fails honestly without starting production.
    In-flight captures are awaited first (bounded) — the dock may not be
    raced by the absorb's async capture; a wait that outlasts its ceiling
    raises ``FilmCaptureTimeout`` (propagates — never a silent draft over a
    half-captured world). The ONE caller is the dock seats'
    ``prepare_dock_storyboard``. ``current`` = the board under review when
    this is a feedback redraft — the director revises IT (修订基于当前稿),
    never a from-scratch re-roll. The phase labels (capturing /
    storyboarding / storyboard_revision) belong to THIS span: they are
    cleared on every exit (``on_progress(None)`` — the explicit clear
    frame), so a label never outlives its work."""
    if on_progress is not None:
        await on_progress("capturing")
    try:
        await _await_captures_settled(project.id)
        pages = await load_storyboard_pages(db, project)
        if not pages:
            return None
        if on_progress is not None:
            await on_progress("storyboarding")
        page_images = await page_media_inputs(pages)

        async def rejected(attempt, violations, feedback):
            logger.info("film_plan_draft_rejected", project_id=str(project.id),
                        attempt=attempt, codes=sorted({v.code for v in violations}),
                        detail=(feedback or "")[:600])
            if on_progress is not None:
                await on_progress("storyboard_revision")
        try:
            storyboard = await orchestrate_storyboard(
                pages=pages,
                instruction=instruction,
                focus=focus,
                page_images=page_images,
                language=language,
                current=current,
                on_reject=rejected,
                # 设计旅程诚实终局 (2026-10-18 用户拍板): a user is watching
                # this board and will judge it — an exhausted ladder raises the
                # original rejection (timeout keeps its own key) instead of
                # shipping the fixed board as if it were a designed one. The
                # retry is a real redesign, never a dressed-up fallback.
                allow_fixed_fallback=False,
                voiceover=voiceover,
            )
        except (FilmStoryboardRejected, LLMSchemaError, LLMError) as exc:
            # Preflight and budget failures keep their OWN honest keys all the
            # way to the user — converting them to None would relabel a known
            # cause (missing captures / provider slowness) as an ungrounded
            # copy problem.
            if getattr(exc, "user_key", None) in {
                "film_storyboard_timeout",
                "film_views_missing",
            }:
                raise
            # The dock caller converts absence into an honest failed turn.
            logger.info(
                "film_plan_draft_failed",
                project_id=str(project.id),
                reason=str(exc)[:200],
            )
            return None
        return storyboard, pages
    finally:
        if on_progress is not None:
            await on_progress(None)


# ---------------------------------------------------------------------------
# The dock seat (a film chain docks with its storyboard already drafted —
# the resolved board's code-rendered markdown rides the dock echo, and the
# dump stores on the PendingPlan as the Start handoff; the run consumes
# exactly the storyboard the user last saw. 展示=执行: one resolved object,
# markdown and render_spec are both its projections)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DockStoryboard:
    """The prepared storyboard: the LLM-facing PRESENTATION FACT SHEET
    (``storyboard_presentation`` — the design beat's ToolObservation body;
    the chat model renders it as the ONE presentation message, 2026-10-18
    裁决) + the RESOLVED storyboard dump (the PendingPlan's
    ``film_storyboard`` handoff) + the reuse fingerprint. ``reused`` marks
    the fingerprint-hit path — the SAME board the user already saw, its
    facts re-projected from the store. ``execution`` is the design-time
    execution snapshot (ADR-129 — pages / resolved music grid / timing +
    digest), computed ONLY on a fresh draft; the reuse path carries None
    and the caller keeps the stored version's snapshot."""

    presentation: str
    storyboard: dict
    fingerprint: str
    reused: bool = False
    execution: dict | None = None


def _launch_film_params(tasks: list) -> dict | None:
    """The chain's launch_film params (None = no film task — the dock
    storyboard machinery stays out). Reads TaskItem objects and plain dicts
    alike."""
    for t in tasks:
        tool = t.get("tool") if isinstance(t, dict) else getattr(t, "tool", None)
        if tool == "launch_film":
            params = t.get("params") if isinstance(t, dict) else getattr(t, "params", None)
            return dict(params) if isinstance(params, dict) else {}
    return None


def canonical_film_params(params: dict) -> dict:
    """The launch_film design params in their ONE canonical form (the
    fingerprint's own pinning: nulls drop out, aspect pins "16:9",
    voiceover pins narrated). The dock seats rewrite the proposed task's
    params from the presented version's params through this, so the
    confirmed chain carries exactly what the presented board was designed
    with — a param the model spelled only once never reads as drift."""
    canonical = {
        k: v
        for k, v in params.items()
        if v is not None and k in {"focus", "language", "music_mood", "aspect"}
    }
    canonical["aspect"] = canonical.get("aspect") or "16:9"
    canonical["voiceover"] = params.get("voiceover") is not False
    return canonical


def storyboard_fingerprint(tasks: list, instruction: str | None) -> str | None:
    """The dock storyboard's reuse key: the launch_film params + the plan's
    BIRTH narrative, deterministically hashed. A revision that moves either
    redrafts; any other re-dock reuses the storyboard the user already saw
    (the user revises against a stable object). Storyboard feedback NEVER
    enters this hash — it rides ``prepare_dock_storyboard``'s
    ``fresh_instruction`` as a one-time redraft trigger, so the board a
    feedback redraft produced stays reusable on the next feedback-free
    re-dock. None = the chain holds no film.

    Canonical form (设计拍 → dock 拍同键, 2026-10-17): the design beat's
    synthetic task and the approval dock's real task must hash equal when
    they MEAN the same film — null params drop out, the voiceover default
    (null = narrated) pins to its explicit twin, a null aspect pins to the
    "16:9" default. Without this, a param the model spelled only once would
    read as a moved fingerprint and force a blind redraft."""
    params = _launch_film_params(tasks)
    if params is None:
        return None
    payload = json.dumps(
        {"params": canonical_film_params(params), "instruction": instruction or ""},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def storyboard_content_digest(storyboard: FilmStoryboard | dict) -> str:
    """sha256 over the resolved board's canonical dump — the presented
    draft's identity (ADR-129: 呈现稿 digest = run context digest = render
    spec digest, one truth stamped at the design beat). The input is
    NORMALIZED through the model first: a raw dict validates and re-dumps
    with every default materialized, so a sparse hand-built board and its
    validated twin digest identically — the design stamp, the dock/start
    checks and the worker check all read the same canonical bytes. A
    malformed board raises the validation error, never a digest of
    garbage."""
    model = (
        storyboard
        if isinstance(storyboard, FilmStoryboard)
        else FilmStoryboard.model_validate(storyboard)
    )
    payload = json.dumps(
        model.model_dump(mode="json"), sort_keys=True, ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_film_execution_snapshot(
    *,
    pages: list[StoryboardPage],
    track: Music | None,
) -> dict:
    """The film's execution inputs frozen at design time (ADR-129/ADR-130
    §1): the pages the board was grounded on (asset id / url / screenshot
    key), the resolved music grid (track id / mood / bpm / beats — the SAME
    grid the markdown's snapped timing shows), the timing constant, and
    ``digest`` over that canonical form. LaunchFilm consumes the snapshot
    verbatim; drift against it fails honestly, never a silent
    re-orchestration."""
    snapshot = {
        "pages": [
            {
                "asset_id": p.asset_id,
                "url": p.research.url,
                "screenshot_key": p.screenshot_key,
            }
            for p in pages
        ],
        "music": (
            {
                "track_id": str(track.id),
                "mood": track.mood,
                "bpm": _track_bpm(track),
                "beats": _track_beats(track),
            }
            if track is not None
            else None
        ),
        "timing": {"fps": FILM_FPS},
    }
    return {**snapshot, "digest": film_execution_snapshot_digest(snapshot)}


def film_execution_snapshot_digest(snapshot: dict) -> str:
    """The execution snapshot's canonical digest, recomputed by every read
    seat that must prove the frozen inputs still agree (the stamped
    ``digest`` key itself never participates)."""
    raw = {k: v for k, v in snapshot.items() if k != "digest"}
    payload = json.dumps(raw, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def film_design_state(
    stored: Any,
    *,
    film: DockStoryboard,
    design_params: dict,
    review_hold: bool | None,
    authorized_by: str | None,
) -> dict:
    """The PendingPlan's versioned film state after a design beat (ADR-129,
    both chat paths' design seats ride here). ``stored`` = the current
    PendingPlan (or None); ``film`` = the prepared DockStoryboard.

    - a FRESH draft (new board — first design, or a feedback redraft):
      version +1, a new draft token (旧 Start 失效), the canonical design
      params, the content digest, the design-time execution snapshot, and
      this turn's authorizing user message;
    - a REUSE re-presentation (fingerprint hit, no fresh feedback): the
      stored version / token / params / snapshot survive — the SAME board
      is shown again, nothing is invalidated (a token the begin beat
      cleared re-mints: the old confirmation was already voided).

    ``review_hold``: True sets the「只看分镜」hold, False releases it. None:
    a FRESH draft holds for review by default — a storyboard is a creation,
    so production never starts from a board the user has not seen; the one
    release seat is the user's explicit production request (the approval
    dock clears it). A REUSE re-presentation keeps the stored hold (that
    board was already seen). The content digest re-stamps on both paths
    (same input → same digest).
    Returns PendingPlan field kwargs only — the caller merges its own
    preserved fields and the presentation message id lands separately."""
    from uuid import uuid4

    stored_version = getattr(stored, "film_storyboard_version", None) if stored is not None else None
    fresh = not film.reused
    version = (stored_version or 0) + 1 if fresh else (stored_version or 1)
    if fresh:
        token = uuid4().hex
        params_snapshot = canonical_film_params(design_params)
        execution = film.execution
        authorized = authorized_by
        # 首稿默认 hold ON: production never starts from a board the user
        # has not seen — the approval dock is the one release seat.
        hold = review_hold if review_hold is not None else True
    else:
        # The begin beat cleared the stored token (旧确认作废), so a reuse
        # re-presentation RE-MINTS when it finds none — the same board, a
        # fresh confirmation identity. A token that survived (legacy path
        # without a begin) keeps its continuity.
        token = (
            stored.film_draft_token if stored is not None else None
        ) or uuid4().hex
        params_snapshot = (
            stored.film_storyboard_params
            if stored is not None and stored.film_storyboard_params
            else canonical_film_params(design_params)
        )
        execution = stored.film_storyboard_execution if stored is not None else None
        authorized = (
            stored.film_design_authorized_by or authorized_by
            if stored is not None
            else authorized_by
        )
        hold = review_hold if review_hold is not None else (
            stored.film_review_hold if stored is not None else False
        )
    return {
        "film_storyboard": film.storyboard,
        "film_storyboard_fingerprint": film.fingerprint,
        "film_storyboard_version": version,
        "film_storyboard_params": params_snapshot,
        "film_storyboard_content_digest": storyboard_content_digest(film.storyboard),
        "film_storyboard_execution": execution,
        "film_design_authorized_by": authorized,
        # The presentation message's provenance: a fresh draft clears it
        # (the publish beat stamps the new message's id), a reuse keeps the
        # stored presentation's id.
        "film_presented_message_id": (
            None if fresh else (stored.film_presented_message_id if stored is not None else None)
        ),
        "film_review_hold": hold,
        "film_draft_token": token,
        # The publish beat consumes the in-flight marker (并发护栏 step 2):
        # the new versioned state lands marker-free.
        "film_draft_inflight": None,
    }


def presentation_stamp_update(
    pending_brief: Any, *, version: int, message_id: str
) -> dict | None:
    """The presented-message association (2026-10-18 裁决 — 最终 LLM 分镜
    消息成功持久化后, 才关联 presented_message_id): the turn stamps the
    row that carried the presentation ONLY through here. Returns the
    updated pending_brief dump, or None when there is nothing honest to
    stamp:

    - no stored board (a non-film plan / a cleared pending) — the design
      beat's state is gone, stamping would invent provenance;
    - the stored version MOVED since this presentation's design beat (a
      newer draft landed — associating the old presentation with the new
      version would mislabel what the user saw).

    The stamp itself is ``film_presented_message_id`` — the ONE message the
    user actually read this version in (re-stamps on a re-presentation:
    the latest presentation of the SAME version is the live provenance)."""
    if not isinstance(pending_brief, dict):
        return None
    try:
        stored = PendingPlan.model_validate(pending_brief)
    except (ValueError, TypeError):
        return None
    if stored.film_storyboard is None or stored.film_storyboard_version != version:
        return None
    return stored.model_copy(
        update={"film_presented_message_id": message_id}
    ).model_dump(mode="json")


def rewrite_film_task_params(tasks: list, version_params: dict | None) -> None:
    """The dock's canonical rewrite (ADR-129 — dock 全座位只读当前版本并重
    写 launch_film 参数): the launch_film task's params BECOME the presented
    version's params verbatim — the confirmed chain carries exactly what the
    presented board was designed with. REPLACE, never merge: a key the model
    spelled beyond the version (e.g. a music_mood echoed from the board's
    narration text) would survive a merge into the fingerprint's canonical
    set and read as drift, rejecting every honest approval dock. In-place;
    dicts and TaskItems alike; no-op without a version."""
    if not version_params:
        return
    for t in tasks:
        tool = t.get("tool") if isinstance(t, dict) else getattr(t, "tool", None)
        if tool != "launch_film":
            continue
        if isinstance(t, dict):
            t["params"] = dict(version_params)
        else:
            t.params = dict(version_params)


def film_carry_state(stored: Any) -> dict:
    """The versioned film fields preserved verbatim across a non-dock
    PendingPlan rewrite (an interjection ask / a degrade write). The review
    hold survives here — only the proposal dock's explicit production seat
    clears it (``film_dock_state`` below)."""
    if stored is None or not getattr(stored, "film_storyboard", None):
        return {
            "film_storyboard": None,
            "film_storyboard_fingerprint": None,
            "film_storyboard_version": None,
            "film_storyboard_params": None,
            "film_storyboard_content_digest": None,
            "film_storyboard_execution": None,
            "film_design_authorized_by": None,
            "film_presented_message_id": None,
            "film_review_hold": False,
            "film_draft_token": None,
            "film_draft_inflight": getattr(stored, "film_draft_inflight", None),
        }
    return {
        "film_storyboard": stored.film_storyboard,
        "film_storyboard_fingerprint": stored.film_storyboard_fingerprint,
        "film_storyboard_version": stored.film_storyboard_version,
        "film_storyboard_params": stored.film_storyboard_params,
        "film_storyboard_content_digest": stored.film_storyboard_content_digest,
        "film_storyboard_execution": stored.film_storyboard_execution,
        "film_design_authorized_by": stored.film_design_authorized_by,
        "film_presented_message_id": stored.film_presented_message_id,
        "film_review_hold": bool(stored.film_review_hold),
        "film_draft_token": stored.film_draft_token,
        "film_draft_inflight": getattr(stored, "film_draft_inflight", None),
    }


def film_dock_state(stored: Any) -> dict:
    """The dock seat's film-state carry-over (ADR-129 — dock 只读当前版本):
    the stored version's fields ride onto the re-written PendingPlan
    VERBATIM (a dock never redrafts, never re-versions); the review hold
    CLEARS — a film proposal docking IS the user's explicit production
    request, the hold's one release seat. A stored plan without a presented
    board (non-film chains included) writes the empty state."""
    state = film_carry_state(stored)
    if state["film_storyboard"] is not None:
        state["film_review_hold"] = False
    return state


@dataclass(frozen=True)
class FilmDockResolution:
    """One dock seat's resolved film state. ``film_chain=False`` means the
    chain carries no launch_film task and ``state`` is the empty film state;
    a film chain carries the CURRENT presented version's state verbatim."""

    film_chain: bool
    state: dict


# Dock-stale steering (2026-10-18 最后一公里裁决): the rejection must NAME
# its failed leg (logged for forensics) and steer to the leg's OWN repair —
# never a blanket "call design_storyboard" (that text taught the model to
# REDESIGN on a dock hiccup: the 4ad7963e incident — the approval turn
# re-drafted the board under a restated direction and silently swapped the
# narrated v1 for an all-silent v2). A dock rejection is not a redesign
# license: approval of the presented board consumes it.
_FILM_DOCK_WAIT = (
    "a storyboard design is in flight right now — wait for its "
    "presentation, then dock the proposal with the presented version's "
    "params. Never dock over an in-flight design, and never redesign to "
    "escape the wait."
)
_FILM_DOCK_NO_VERSION = (
    "no usable storyboard version is on record for this film chain "
    "({legs}). Re-present the CURRENT board WITHOUT redesigning it: call "
    "design_storyboard ONCE with the film's params (focus / language / "
    "voiceover / music_mood / aspect) and NO specific_instruction — a bare "
    "re-call re-presents or repairs the current board; it never creates a "
    "new version on its own. Redesign only on the user's change words."
)
_FILM_DOCK_STATE_BROKEN = (
    "the presented storyboard's saved state is incomplete ({legs}) — this "
    "is a state fault, never a reason to redesign. Repair it WITHOUT "
    "changing the board: call design_storyboard ONCE with the SAME params "
    "and NO specific_instruction (no feedback words — a bare re-call "
    "re-presents/repairs the current version). Redesign only on the "
    "user's change words."
)
_FILM_DOCK_PLAN_MOVED = (
    "this plan moved away from the presented storyboard's version ({legs}) "
    "— the board belongs to the plan's earlier wording. Either dock with "
    "the presented version's params verbatim (they are restored onto your "
    "tasks automatically — retry present_plan once), or, when the user "
    "genuinely asked for something new, call design_storyboard with their "
    "change as specific_instruction. Approval of the presented board is "
    "never a redesign."
)


def resolve_film_dock_state(
    stored: Any,
    tasks: list,
    instruction: str | None,
) -> FilmDockResolution | str:
    """Resolve a dock's film state in ONE order (ADR-129): read the current
    persisted version → restore its canonical launch_film params onto the
    proposed task → THEN validate fingerprint / version / content digest /
    execution digest / draft token. The saved version wins over fresh
    wording (a focus paraphrase is not a redesign); ``specific_instruction``
    never enters this seat, so a dock can never trigger a redraft. A STRING
    return is the loop's steering rejection — leg-specific (each failed leg
    is LOGGED for forensics and the text steers to that leg's own repair;
    a blanket redesign steer is what turned the 4ad7963e approval turn into
    a silent v2 swap). ``film_chain=False`` clears any stale film fields
    from a non-film dock."""
    if _launch_film_params(tasks) is None:
        return FilmDockResolution(False, film_dock_state(None))

    def stale(legs: list[str], template: str) -> str:
        logger.info("film_dock_stale", legs=legs)
        return template.format(legs=", ".join(legs))

    board_raw = getattr(stored, "film_storyboard", None) if stored is not None else None
    version_params = (
        getattr(stored, "film_storyboard_params", None) if stored is not None else None
    )
    if not isinstance(board_raw, dict) or not isinstance(version_params, dict):
        if film_draft_inflight_live(
            getattr(stored, "film_draft_inflight", None) if stored is not None else None
        ):
            return stale(["design_in_flight"], _FILM_DOCK_WAIT)
        legs = []
        if not isinstance(board_raw, dict):
            legs.append("no_board")
        if not isinstance(version_params, dict):
            legs.append("no_version_params")
        return stale(legs, _FILM_DOCK_NO_VERSION)
    rewrite_film_task_params(tasks, version_params)
    fingerprint = storyboard_fingerprint(tasks, instruction)
    try:
        board = FilmStoryboard.model_validate(board_raw)
    except (TypeError, ValueError):
        return stale(["board_unreadable"], _FILM_DOCK_STATE_BROKEN)
    version = getattr(stored, "film_storyboard_version", None)
    content_digest = getattr(stored, "film_storyboard_content_digest", None)
    execution = getattr(stored, "film_storyboard_execution", None)
    execution_ok = (
        isinstance(execution, dict)
        and isinstance(execution.get("digest"), str)
        and film_execution_snapshot_digest(execution) == execution["digest"]
    )
    if not (
        fingerprint
        and fingerprint == getattr(stored, "film_storyboard_fingerprint", None)
    ):
        return stale(["fingerprint_mismatch"], _FILM_DOCK_PLAN_MOVED)
    legs = []
    if not (isinstance(version, int) and version >= 1):
        legs.append("version_missing")
    if content_digest != storyboard_content_digest(board):
        legs.append("content_digest_mismatch")
    if not execution_ok:
        legs.append("execution_digest_mismatch")
    if not getattr(stored, "film_draft_token", None):
        legs.append("draft_token_missing")
    if legs:
        return stale(legs, _FILM_DOCK_STATE_BROKEN)
    return FilmDockResolution(True, film_dock_state(stored))


def film_start_draft_match(
    stored: Any,
    tasks: list,
    instruction: str | None,
    docked_token: str | None,
    docked_version: int | None = None,
) -> bool:
    """The Start seat's film integrity predicate. Unlike the dock resolver
    this NEVER rewrites the submitted chain: panel-edited launch_film params
    must fail closed for an explicit re-dock, not silently align to the old
    board. Token equality alone is insufficient — canonical params, version,
    content digest and execution digest all compare on every versioned row.
    Pre-version rows keep the fingerprint fallback (读容忍)."""
    board_raw = getattr(stored, "film_storyboard", None) if stored is not None else None
    task_params = _launch_film_params(tasks)
    if not isinstance(board_raw, dict) or task_params is None:
        return False
    version_params = getattr(stored, "film_storyboard_params", None)
    if not isinstance(version_params, dict):
        return False
    if canonical_film_params(task_params) != canonical_film_params(version_params):
        return False

    stored_token = getattr(stored, "film_draft_token", None)
    if docked_token and stored_token:
        token_match = docked_token == stored_token
    else:
        fingerprint = storyboard_fingerprint(tasks, instruction)
        token_match = (
            fingerprint is not None
            and fingerprint == getattr(stored, "film_storyboard_fingerprint", None)
        )
    if not token_match:
        return False

    versioned = any(
        getattr(stored, key, None) is not None
        for key in (
            "film_draft_token",
            "film_storyboard_version",
            "film_storyboard_content_digest",
            "film_storyboard_execution",
        )
    )
    if not versioned:
        return True
    version = getattr(stored, "film_storyboard_version", None)
    if not isinstance(version, int) or version < 1:
        return False
    if docked_version is not None and docked_version != version:
        return False
    try:
        board = FilmStoryboard.model_validate(board_raw)
    except (TypeError, ValueError):
        return False
    if getattr(stored, "film_storyboard_content_digest", None) != storyboard_content_digest(board):
        return False
    execution = getattr(stored, "film_storyboard_execution", None)
    return (
        isinstance(execution, dict)
        and isinstance(execution.get("digest"), str)
        and film_execution_snapshot_digest(execution) == execution["digest"]
    )


def _film_revision_base_from_state(
    *,
    board: Any,
    fingerprint: Any,
    version: Any,
    params: Any,
    content_digest: Any,
    execution: Any,
) -> Any | None:
    """One revision-base candidate's validation (pure): the board must parse
    and — when a content digest rides along — re-prove against it. Returns a
    PendingPlan-shaped namespace (``film_design_state`` reads it through the
    same getattr surface), or None when the candidate is unusable (the next
    seat is tried)."""
    from types import SimpleNamespace

    if not isinstance(board, dict):
        return None
    try:
        validated = FilmStoryboard.model_validate(board)
    except (TypeError, ValueError):
        return None
    if isinstance(content_digest, str) and (
        storyboard_content_digest(validated) != content_digest
    ):
        return None
    return SimpleNamespace(
        film_storyboard=board,
        film_storyboard_fingerprint=fingerprint if isinstance(fingerprint, str) else None,
        film_storyboard_version=version if isinstance(version, int) else None,
        film_storyboard_params=params if isinstance(params, dict) else None,
        film_storyboard_content_digest=content_digest if isinstance(content_digest, str) else None,
        film_storyboard_execution=execution if isinstance(execution, dict) else None,
        # The recovered base carries no live draft token / marker /
        # authorization / presentation message — those belong to the beat
        # that re-presents it (a reuse keeps None, a fresh draft re-mints).
        film_draft_token=None,
        film_draft_inflight=None,
        film_design_authorized_by=None,
        film_presented_message_id=None,
        film_review_hold=False,
    )


async def resolve_film_revision_base(
    db: AsyncSession,
    project: Project,
    *,
    output_id: UUID | None = None,
) -> Any | None:
    """The design beat's deterministic revision base (ADR-129 修订基准解析座):
    when the live PendingPlan no longer carries a film design (a successful
    Start clears ``pending_brief``), a later ``design_storyboard`` recovers
    the CURRENT board from provenance instead of drafting from nothing:

    - ``output_id`` given (an explicit @output pin — 钉恒胜): ONLY that
      output's run context is eligible. An unrecoverable pinned target
      yields None (a fresh draft) — never a silent swap to the pending
      draft or another film's board.
    - no pin: 1. the live pending film state (``project.pending_brief``);
      2. the project's latest film run's stamped context.

    The recovered row is a READ-ONLY provenance snapshot shaped like the
    PendingPlan's film fields (``film_design_state`` reads it through the
    same getattr surface) — the source run/context is never mutated, an
    executing run is never rewritten. A candidate whose board fails to
    parse, or whose stamped content digest no longer matches the board,
    is skipped (the next seat is tried; none → None → a fresh first
    draft). Returns None when no provenance exists.
    """
    if output_id is not None:
        mentioned_ctx = (
            await db.execute(
                select(WorkflowRun.context)
                .select_from(Output)
                .join(WorkflowStep, Output.workflow_step_id == WorkflowStep.id)
                .join(WorkflowRun, WorkflowStep.run_id == WorkflowRun.id)
                .where(Output.id == output_id, Output.project_id == project.id)
            )
        ).scalar_one_or_none()
        if not isinstance(mentioned_ctx, dict):
            return None
        base = _film_revision_base_from_state(
            board=mentioned_ctx.get("prepared_storyboard"),
            fingerprint=mentioned_ctx.get("film_storyboard_fingerprint"),
            version=mentioned_ctx.get("film_storyboard_version"),
            params=mentioned_ctx.get("film_storyboard_params"),
            content_digest=mentioned_ctx.get("film_storyboard_content_digest"),
            execution=mentioned_ctx.get("film_execution"),
        )
        if base is not None:
            logger.info(
                "film_revision_base_recovered",
                project_id=str(project.id),
                output_id=str(output_id),
                version=base.film_storyboard_version,
            )
        return base

    pending = project.pending_brief if isinstance(project.pending_brief, dict) else None
    if pending and pending.get("film_storyboard"):
        return _film_revision_base_from_state(
            board=pending.get("film_storyboard"),
            fingerprint=pending.get("film_storyboard_fingerprint"),
            version=pending.get("film_storyboard_version"),
            params=pending.get("film_storyboard_params"),
            content_digest=pending.get("film_storyboard_content_digest"),
            execution=pending.get("film_storyboard_execution"),
        )

    # Latest film run fallback: the portable read (no JSON operator — the
    # recent-run scan filters in Python) so the seat holds on every backend.
    recent = (
        (
            await db.execute(
                select(WorkflowRun.context)
                .where(WorkflowRun.project_id == project.id)
                .order_by(WorkflowRun.created_at.desc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    for ctx in recent:
        if not isinstance(ctx, dict) or not isinstance(ctx.get("prepared_storyboard"), dict):
            continue
        base = _film_revision_base_from_state(
            board=ctx.get("prepared_storyboard"),
            fingerprint=ctx.get("film_storyboard_fingerprint"),
            version=ctx.get("film_storyboard_version"),
            params=ctx.get("film_storyboard_params"),
            content_digest=ctx.get("film_storyboard_content_digest"),
            execution=ctx.get("film_execution"),
        )
        if base is not None:
            logger.info(
                "film_revision_base_recovered",
                project_id=str(project.id),
                version=base.film_storyboard_version,
            )
            return base
    return None


def film_draft_inflight_live(marker: Any, *, now: float | None = None) -> bool:
    """The in-flight marker's liveness predicate (并发护栏, pure): a dict
    carrying a ``draft_id`` whose age is under the design budget. A marker
    with an unreadable clock reads as LIVE (fail closed); a marker older
    than the budget is stale — a crashed turn's residue never blocks
    forever."""
    if not isinstance(marker, dict) or not marker.get("draft_id"):
        return False
    started = marker.get("started_at")
    if not isinstance(started, (int, float)):
        return True
    return ((now if now is not None else time.time()) - started) < _DOCK_DRAFT_BUDGET_S


async def begin_film_draft(
    db: AsyncSession,
    project: Project,
    *,
    base_version: int | None,
    user_message_id: str | None,
) -> str | None:
    """The design beat's BEGIN (并发护栏 step 1): write the in-flight marker
    + supersede the old film confirmation (``film_draft_token`` clears) in
    the marker's OWN committed mini-transaction, so the Start gate (a
    separate request's transaction) sees it DURING the long draft. Returns
    the draft id; ``None`` = the begin is REFUSED.

    No fallback channel, by law: the marker is either committed through the
    side session or the beat does not start. A NOWAIT failure means the
    project row is locked — by a concurrent design's begin, by a Start's
    answer transaction, or by THIS turn's own earlier write (the flush
    below surfaces any pending write first, so an own-write reads as the
    lock it holds). Every one of those resolves to the same honest refusal
    — never a stale in-memory overwrite, never an uncommitted marker the
    Start gate cannot see. The publish beat's conditional check reads the
    COMMITTED marker, which is therefore always this begin's own row.

    Lock discipline: the side session locks ONLY the project row (nowait —
    it never waits behind another holder, so a second designer is refused,
    not queued); the caller's message writes stay in the turn transaction,
    so the Message → Project order is never inverted here. On success the
    turn session RE-READS the row (a plain refresh — no lock, no write) so
    its later reads see the committed marker + cleared token; the turn
    transaction never holds the project lock across the draft.
    """
    from uuid import uuid4

    from sqlalchemy.exc import OperationalError

    from app.models.database import AsyncSessionLocal  # deferred: worker seat

    # Surface this turn's pending writes BEFORE the side begin: a turn that
    # already wrote the project row holds its lock for the rest of the
    # transaction, and the NOWAIT below then refuses honestly instead of
    # the side commit being clobbered by the turn's later flush.
    await db.flush()

    draft_id = uuid4().hex
    marker = {
        "draft_id": draft_id,
        "base_version": base_version,
        "started_at": time.time(),
        "user_message_id": user_message_id,
    }

    def _apply(pend: dict) -> dict:
        return {
            **pend,
            "film_draft_inflight": marker,
            "film_draft_token": None,  # 旧确认作废
        }

    try:
        async with AsyncSessionLocal() as session:
            row = await session.get(
                Project, project.id, with_for_update={"nowait": True}
            )
            if row is None:
                return None
            pend = dict(row.pending_brief) if isinstance(row.pending_brief, dict) else {}
            if film_draft_inflight_live(pend.get("film_draft_inflight")):
                logger.info(
                    "film_draft_begin_refused",
                    project_id=str(project.id),
                    holder=(pend.get("film_draft_inflight") or {}).get("draft_id"),
                )
                return None
            row.pending_brief = _apply(pend)
            await session.commit()
    except OperationalError:
        # The row is locked — a concurrent design / a Start / this turn's
        # own earlier write. Refuse; NEVER fall back to an uncommitted
        # turn-transaction marker (the Start gate couldn't see it and the
        # publish check couldn't prove it).
        logger.info("film_draft_begin_contended", project_id=str(project.id))
        return None
    # Sync the turn session's object with the committed truth (plain
    # re-read — the turn holds no lock and carries no pending write here).
    await db.refresh(project)
    return draft_id


async def read_committed_film_marker(project_id: UUID) -> dict | None:
    """The publish beat's conditional read: the COMMITTED pending_brief's
    in-flight marker (a plain lock-free side-session SELECT — the publish
    check never takes the project row lock)."""
    from app.models.database import AsyncSessionLocal  # deferred: worker seat

    async with AsyncSessionLocal() as session:
        pend = (
            await session.execute(
                select(Project.pending_brief).where(Project.id == project_id)
            )
        ).scalar_one_or_none()
    if not isinstance(pend, dict):
        return None
    marker = pend.get("film_draft_inflight")
    return marker if isinstance(marker, dict) else None


async def clear_film_draft_marker(
    db: AsyncSession, project: Project, *, draft_id: str
) -> None:
    """Failure/timeout/cancel clears ONLY its own marker (并发护栏 step 3):
    a newer design's marker is never touched. The committed row is cleared
    through the marker's own side channel FIRST — on this path the turn
    holds no project lock (begin never writes through the turn), so the
    NOWAIT succeeds and a turn rollback cannot resurrect the marker. The
    turn session's object then re-reads the cleared row so a continuing
    turn (the loop catching the failure) sees the same truth."""
    from sqlalchemy.exc import OperationalError

    from app.models.database import AsyncSessionLocal  # deferred: worker seat

    try:
        async with AsyncSessionLocal() as session:
            row = await session.get(
                Project, project.id, with_for_update={"nowait": True}
            )
            if row is not None:
                committed = (
                    dict(row.pending_brief) if isinstance(row.pending_brief, dict) else {}
                )
                marker = committed.get("film_draft_inflight")
                if isinstance(marker, dict) and marker.get("draft_id") == draft_id:
                    committed.pop("film_draft_inflight", None)
                    row.pending_brief = committed
                    await session.commit()
    except OperationalError:
        # Someone else holds the row (a concurrent Start committing, a newer
        # design's begin): their transaction owns the pending plan's fate —
        # a Start's success clears pending_brief wholesale, a newer design
        # replaced the marker. Either way our marker is gone or stale; the
        # budget covers the rest.
        pass
    if not db.is_modified(project):
        with suppress(Exception):  # best-effort in-memory sync only
            await db.refresh(project)


async def sweep_orphan_film_draft_markers() -> int:
    """API boot sweep (重启孤儿收束): the design beat lives ONLY in this API
    process's chat turns — never in the worker, never in another service —
    so at boot NO committed in-flight marker can belong to a live design:
    every one is a crashed/reloaded turn's residue. Sweeping at boot is what
    keeps a mid-draft restart from refusing redesigns and blocking Start for
    the whole staleness budget. Ownership is structural (the seat's single
    home process), not per-row — if the API ever runs multi-replica, this
    seat needs a process-identity half. Boot must never fail on the sweep
    (the b5f1f3f lesson), and the column is generic JSON, so the jsonb cast
    rides the statement itself. Returns the swept count."""
    from sqlalchemy import text

    from app.models.database import AsyncSessionLocal  # deferred: worker seat

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text(
                    """
                    UPDATE projects
                    SET pending_brief = (pending_brief::jsonb - 'film_draft_inflight')
                    WHERE pending_brief IS NOT NULL
                      AND pending_brief::jsonb ? 'film_draft_inflight'
                    """
                )
            )
            await session.commit()
            return result.rowcount or 0
    except Exception as e:  # noqa: BLE001 — a sweep failure never blocks boot
        logger.warning("film_draft_marker_sweep_failed", error=str(e))
        return 0


async def resolve_film_music(
    db: AsyncSession, project: Project, music_mood: str | None
) -> Music | None:
    """The film bed's resolution chain (ONE law, shared by the dock's
    markdown projection and the node's spec build): the plan's named mood →
    the persona skin default → "calm". None = nothing resolved — the caller
    decides whether that is a hard failure (an explicitly named mood at run
    time) or an honest omission (the dock's music line simply stays out)."""
    from app.memory.brand import resolve_music_ref  # deferred: memory edge

    persona = await resolve_persona(db, project)  # None-safe
    brand_ref: Any = None
    if not music_mood and persona is not None:
        block = persona.brand or {}
        brand_ref = block.get("musicId") or block.get("musicMood")
    for ref in (music_mood, brand_ref, "calm"):
        if not ref:
            continue
        track = await resolve_music_ref(db, ref)
        if track is not None:
            return track
    return None


async def _dock_music_context(
    db: AsyncSession, project: Project, music_mood: str | None
) -> tuple[str | None, list[float] | None, float | None]:
    """The dock's music facts: (display label, beat grid, BPM). The label is
    best-effort — a resolution failure omits the line, never blocks the
    dock; the grid/BPM let the markdown show the SAME snapped timing the run
    will render (展示=执行 down to frames)."""
    try:
        track = await _resolve_track_backfilled(db, project, music_mood)
    except Exception as e:  # noqa: BLE001 — auxiliary display fact
        logger.info("dock_music_label_failed", project_id=str(project.id), error=str(e))
        return None, None, None
    if track is None:
        return None, None, None
    label = f"{track.mood} — {track.title}"
    bpm = _track_bpm(track)
    if bpm is not None:
        label += f" · {bpm:g} BPM"
    return label, _track_beats(track), bpm


async def prepare_dock_storyboard(
    db: AsyncSession,
    project: Project,
    *,
    tasks: list,
    instruction: str | None,
    fresh_instruction: str | None = None,
    cached_storyboard: dict | None = None,
    cached_fingerprint: str | None = None,
    on_progress=None,
) -> DockStoryboard | None:
    """The dock seats' ONE storyboard seat (the plan path's dock seats and
    the chat path's ``_dock_plan_as_question`` all ride here, before
    ``sync_plan_question`` and before the auto-start beat): draft the film
    storyboard NOW and return its presentation fact sheet + dump +
    fingerprint. No film task → None (a no-op).

    Reuse law — the user revises against a STABLE storyboard: ``instruction``
    is the fingerprint basis (the plan's frozen BIRTH narrative); a re-dock
    whose fingerprint matches re-projects the SAME stored board's facts,
    never a redraft. ``fresh_instruction`` is THIS dock's new storyboard
    feedback — its presence forces a redraft guided by it (falling back to
    the birth narrative when absent), and the stored fingerprint stays keyed
    on the birth narrative so the NEXT feedback-free re-dock reuses the
    feedback-incorporated board. A draft that cannot stand raises a user-facing failure before docking
    or auto-start; None means this is not a film proposal."""
    fingerprint = storyboard_fingerprint(tasks, instruction)
    if fingerprint is None:
        return None
    params = _launch_film_params(tasks) or {}
    aspect = params.get("aspect") or "16:9"
    voiceover = params.get("voiceover") is not False
    music_label, music_beats, music_bpm = await _dock_music_context(
        db, project, params.get("music_mood")
    )
    if (
        not (fresh_instruction or "").strip()
        and cached_fingerprint == fingerprint
        and isinstance(cached_storyboard, dict)
    ):
        try:
            cached = FilmStoryboard.model_validate(cached_storyboard)
        except (ValueError, TypeError):
            cached = None
        if cached is not None:
            # The reuse path re-projects the facts off the SAME stored
            # board — the music/display facts read fresh (they never alter
            # the board itself). execution=None: the caller keeps the
            # stored version's design-time snapshot.
            pages = await load_storyboard_pages(db, project)
            return DockStoryboard(
                presentation=storyboard_presentation(
                    cached,
                    pages,
                    aspect=aspect,
                    music=music_label,
                    beats=music_beats,
                    bpm=music_bpm,
                    captions=voiceover,
                ),
                storyboard=cached.model_dump(mode="json"),
                fingerprint=fingerprint,
                reused=True,
            )
    # 修订基于当前稿 (ADR-129): a feedback redraft revises the CURRENT
    # board — the director sees it as the revision base and keeps every
    # slot the feedback does not name (never a from-scratch re-roll).
    current: FilmStoryboard | None = None
    if (fresh_instruction or "").strip() and isinstance(cached_storyboard, dict):
        try:
            current = FilmStoryboard.model_validate(cached_storyboard)
        except (ValueError, TypeError):
            current = None
    try:
        async with asyncio.timeout(_DOCK_DRAFT_BUDGET_S):
            drafted = await draft_film_storyboard(
                db,
                project,
                instruction=(fresh_instruction or "").strip() or instruction,
                focus=params.get("focus"),
                language=params.get("language"),
                current=current,
                on_progress=on_progress,
                voiceover=voiceover,
            )
    except TimeoutError as exc:
        logger.warning("film_dock_budget_exhausted", project_id=str(project.id),
                       budget_s=_DOCK_DRAFT_BUDGET_S)
        raise LLMError("Storyboard preparation timed out", user_key="film_storyboard_timeout") from exc
    if drafted is None:
        # Never auto-start a film whose storyboard could not be presented.
        raise LLMError("No usable storyboard", user_key="film_storyboard_ungrounded")
    storyboard, pages = drafted
    presentation = storyboard_presentation(
        storyboard,
        pages,
        aspect=aspect,
        music=music_label,
        beats=music_beats,
        bpm=music_bpm,
        captions=voiceover,
    )
    # The design-time execution snapshot (ADR-129/ADR-130 §1): pages +
    # the resolved music grid + timing, digested — the run consumes THIS
    # and drift fails honestly. Best-effort music resolve (the fact sheet's
    # own best-effort law); None = the silent-cut snapshot.
    try:
        snap_track = await _resolve_track_backfilled(db, project, params.get("music_mood"))
    except Exception as e:  # noqa: BLE001 — auxiliary snapshot fact
        logger.info("film_snapshot_music_failed", project_id=str(project.id), error=str(e))
        snap_track = None
    return DockStoryboard(
        presentation=presentation,
        storyboard=storyboard.model_dump(mode="json"),
        fingerprint=fingerprint,
        execution=build_film_execution_snapshot(pages=pages, track=snap_track),
    )


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
    agents = (film_director,)

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
        # 配音承诺 (2026-10-18 — the silent v2 incident): read ONCE up front
        # — the prepared board's defensive re-validation, the orchestration
        # fallback and the synthesis gate all answer to it. A voiceover
        # promise with a voiceless board fails honestly; it never renders
        # as a successful silent film.
        voiceover = (slot.voiceover if slot else None) is not False

        pages = await load_storyboard_pages(db, project)
        if not pages:
            # The birthplace gates presence+readiness; a capture that FAILED
            # mid-wait lands here — the honest refusal (never an ungrounded
            # film).
            raise ValueError(
                "The page never became readable (the capture failed) — send the link again to re-capture it."
            )

        storyboard: FilmStoryboard | None = None
        # prepared_storyboard (ADR-129 严格消费): the confirmed run renders
        # the storyboard version the user SAW — stamped onto run.context at
        # Start with its content digest + execution snapshot. The node
        # re-validates it against the CURRENT pages (world drift: a page
        # re-captured since the design beat) — drift FAILS the step honestly
        # with a redesign request, never a silent re-orchestration. A run
        # born WITHOUT the handoff (a typed /generate birth, a pre-version
        # legacy run) orchestrates fresh by design.
        prepared_raw = ctx.get("prepared_storyboard")
        stamped_content_digest = ctx.get("film_storyboard_content_digest") or None
        proven_content_digest: str | None = None
        versioned_birth = prepared_raw is not None or stamped_content_digest is not None
        if prepared_raw is not None:
            # 篡改门禁 (ADR-129 fail-closed): the confirmed run's handoff is
            # the board the user SAW plus its content digest — both halves of
            # the pair must be present and consistent. A board that fails to
            # parse, a board without its digest (or a digest without a
            # board), or a board whose recomputed digest no longer matches
            # the stamp is corruption/tampering: the step fails honestly,
            # never silently re-orchestrating a fresh draft.
            prepared: FilmStoryboard | None = None
            if isinstance(prepared_raw, dict):
                try:
                    prepared = FilmStoryboard.model_validate(prepared_raw)
                except (ValueError, TypeError):
                    prepared = None
            if prepared is None or stamped_content_digest is None:
                raise ValueError(
                    "The confirmed storyboard handoff is malformed (the board "
                    "or its digest is missing or unreadable) — ask the "
                    "assistant to redesign the storyboard and confirm the new "
                    "version; the run never silently re-drafts."
                )
            proven_content_digest = storyboard_content_digest(prepared)
            if proven_content_digest != stamped_content_digest:
                logger.info(
                    "prepared_storyboard_digest_mismatch",
                    node_id=str(node.id),
                    stamped=stamped_content_digest,
                    recomputed=proven_content_digest,
                )
                raise ValueError(
                    "The confirmed storyboard's content changed since the "
                    "design beat — ask the assistant to redesign the "
                    "storyboard and confirm the new version; the run never "
                    "silently re-drafts."
                )
            stale = validate_storyboard(prepared, pages, narration_required=voiceover)
            if not stale:
                storyboard = prepared
                logger.info(
                    "prepared_storyboard_used",
                    node_id=str(node.id),
                    scenes=len(prepared.scenes),
                )
            else:
                logger.info(
                    "prepared_storyboard_stale",
                    node_id=str(node.id),
                    codes=sorted({v.code for v in stale}),
                )
                raise ValueError(
                    "The presented storyboard no longer holds up against the "
                    "captured pages or the plan's promises (they changed "
                    "since the design beat, or the board went voiceless "
                    "against a voiceover promise) — ask the assistant to "
                    "redesign the storyboard and confirm the new version; "
                    "the run never silently re-drafts."
                )
        elif stamped_content_digest is not None:
            # The half-pair without a board — fail closed (同上门禁).
            raise ValueError(
                "The confirmed storyboard handoff is malformed (a digest "
                "without its board) — ask the assistant to redesign the "
                "storyboard and confirm the new version; the run never "
                "silently re-drafts."
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
                    voiceover=voiceover,
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

        # Slot levers (ADR-130): voiceover / music mood / aspect /
        # language ride the compiled slot; absent = plan defaults (on /
        # persona-or-calm / 16:9 / storyboard-declared). ``voiceover``
        # itself is already read up front (the board gates answer to it).
        aspect = (slot.aspect if slot else None) or "16:9"
        music_mood = (slot.music_mood if slot else None) or None

        # 配乐 (ADR-130 §1 一份已解网格): the confirmed run consumes the
        # DESIGN-TIME snapshot's track (the markdown showed its snapped
        # timing — 展示=执行); a snapshot-less birth (typed /generate,
        # legacy) resolves through the mood → persona skin default → "calm"
        # chain as before. An EXPLICITLY named mood that resolves to nothing
        # fails the step (CHAT_ARCH §10: clear error, never a silent bed).
        from app.pipeline.music import music_file_path

        execution_snapshot = ctx.get("film_execution")
        # 快照自证 (ADR-129 fail-closed): the stamped snapshot's ``digest``
        # must recompute from its OWN frozen inputs before any of it (the
        # snapped music below) is consumed — a tampered or truncated
        # snapshot fails the step, never silently steers the render. A
        # versioned birth without a valid snapshot is the same half-pair
        # corruption as above.
        proven_execution_digest: str | None = None
        if isinstance(execution_snapshot, dict) and execution_snapshot.get("digest"):
            recomputed_execution = film_execution_snapshot_digest(execution_snapshot)
            if recomputed_execution != execution_snapshot["digest"]:
                logger.info(
                    "film_execution_snapshot_tampered",
                    node_id=str(node.id),
                    stamped=execution_snapshot["digest"],
                    recomputed=recomputed_execution,
                )
                raise ValueError(
                    "The film's execution snapshot no longer matches its own "
                    "frozen inputs — ask the assistant to redesign the "
                    "storyboard and confirm the new version; the run never "
                    "silently re-orchestrates."
                )
            proven_execution_digest = recomputed_execution
        elif versioned_birth:
            raise ValueError(
                "The confirmed film run is missing its execution snapshot — "
                "ask the assistant to redesign the storyboard and confirm "
                "the new version; the run never silently re-orchestrates."
            )
        snap_music = (
            execution_snapshot.get("music")
            if isinstance(execution_snapshot, dict)
            else None
        )
        track: Music | None = None
        if isinstance(snap_music, dict) and snap_music.get("track_id"):
            with suppress(ValueError):
                track = await db.get(Music, UUID(str(snap_music["track_id"])))
        if track is None and not (isinstance(snap_music, dict) and snap_music.get("track_id")):
            track = await resolve_film_music(db, project, music_mood)
        if track is None and music_mood:
            raise ValueError(f"No music track found for mood '{music_mood}'")

        # 节拍锁剪 (ADR-121 B3 + ADR-130 §1): the bed's beat grid snaps the
        # internal scene boundaries (structural floors respected, tolerance
        # ±0.2s — see snap_frames_to_beats). A track whose meta carries no
        # grid gets the ONE analysis backfill first (先补齐); a rhythm that
        # still cannot be obtained FAILS the step honestly — the reveal's
        # black beat is a real beat interval, never a fabricated 0.5s.
        beats = await _track_beats_backfilled(db, track)
        if track is not None and beats is None:
            raise ValueError(
                f"The music bed '{track.title}' carries no analyzable rhythm — "
                "pick another mood (or redesign without the bed); the film "
                "never fakes a beat."
            )
        if beats:
            frames = snap_frames_to_beats(storyboard, frames, beats)

        # 执行快照漂移校验 (ADR-129): the confirmed run's world must still
        # be the world the design beat froze — pages and music digest-equal
        # to the stamped snapshot. Drift fails honestly with a redesign
        # request, never a silent re-orchestration.
        if isinstance(execution_snapshot, dict) and execution_snapshot.get("digest"):
            current_digest = build_film_execution_snapshot(
                pages=pages, track=track
            )["digest"]
            if current_digest != execution_snapshot["digest"]:
                logger.info(
                    "film_execution_snapshot_drift",
                    node_id=str(node.id),
                    stamped=execution_snapshot["digest"],
                    current=current_digest,
                )
                raise ValueError(
                    "The film's execution inputs drifted since the design beat "
                    "(a page re-captured or the bed changed) — ask the assistant "
                    "to redesign the storyboard and confirm the new version; "
                    "the run never silently re-orchestrates."
                )

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
            bpm = _track_bpm(track)
            if bpm is not None:
                music_spec["bpm"] = bpm
            if beats:
                music_spec["beats"] = beats

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

        # 配音 (ADR-130): one T2A call per narrated scene, fitted to the
        # scene's SNAPPED window; the synthesis map bakes into the spec as
        # per-scene ``audio`` keys. Voice = persona voice block → house
        # narrator (the film has no source footage to clone from).
        # Voiceover off = the silent cut (music bed only) — the reviewed
        # narration words still stand in the storyboard, just unsynthesized.
        # 配音承诺最后一道防线 (2026-10-18 — the 4ad7963e silent delivery):
        # a voiceover-promised board with ZERO narrated scenes never slips
        # past as a successful silent film — the step fails honestly (the
        # board's validation gates above should have caught it first; this
        # is the fail-closed seat against every other birth path). The
        # worker NEVER writes narration the user never saw.
        narration_keys: dict[int, tuple[str, float]] = {}
        narrated = [
            sc for sc in storyboard.scenes if getattr(sc, "narration", None)
        ]
        if voiceover and not narrated:
            raise ValueError(
                "The plan promises voiceover but the storyboard carries no "
                "narration at all — ask the assistant to redesign the "
                "storyboard with spoken narration and confirm the new "
                "version; a promised-voice film never ships silent."
            )
        if voiceover and narrated:
            from app.tools.film.narration import (
                resolve_film_voice,
                synthesize_film_narration,
            )

            persona = await resolve_persona(db, project)  # None-safe
            voice_block = (persona.voice or None) if persona is not None else None
            # 窗口弹性 (ADR-136): a line that outruns its scene past the
            # whole speed ladder gets ONE bounded rescue — frames stolen
            # from silent scenes, zero-sum (the pre-metered film seconds
            # stay exact), disclosed on the output payload. ``frames`` is
            # reassigned to the adjusted allocation the spec MUST build
            # from; untouched when no flex fires (green renders stay
            # byte-identical).
            narration_keys, frames, flex_moves = await synthesize_film_narration(
                output_id=output.id,
                project=project,
                storyboard=storyboard,
                frames=frames,
                floors=[_scene_floor(sc) for sc in storyboard.scenes],
                voice_id=resolve_film_voice(voice_block),
                language=output.language,
            )
            if flex_moves:
                output.payload = {
                    **output.payload,
                    "narration_flex": {
                        "borrowed_s": round(
                            sum(m["gained_s"] for m in flex_moves), 2
                        ),
                        "moves": flex_moves,
                    },
                }

        output.render_spec = build_film_spec(
            storyboard,
            pages,
            narration=narration_keys,
            music=music_spec,
            aspect=aspect,
            frames=frames,
            # 血缘只写已证 digest (ADR-129 fail-closed): the render spec /
            # output payload carry the digests THIS node recomputed and
            # proved against the stamps — never the stamped values copied
            # blind. A tampered stamp fails above and writes no provenance.
            storyboard_digest=proven_content_digest,
            execution_digest=proven_execution_digest,
        )
        # 交付物血缘 (Batch 2): the design beat's digests ride the OUTPUT
        # payload as well — the delivered artifact's storyboard/execution
        # identity is queryable without unpicking the render spec. 读容忍:
        # snapshot-less births simply carry no provenance key.
        if output.render_spec.get("provenance"):
            output.payload = {
                **output.payload,
                "provenance": output.render_spec["provenance"],
            }
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
