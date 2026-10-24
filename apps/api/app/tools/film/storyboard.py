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
import unicodedata
from contextlib import suppress
from dataclasses import dataclass
from typing import Annotated, Any, Literal
from urllib.parse import urlparse
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator
from sqlalchemy import bindparam, select, text as _text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import Agent, AssembleResult
from app.metering import record_media_usage
from app.models.schemas import (
    AssetStatus,
    AssetType,
    FilmElementImage,
    FilmElementRect,
    FilmElementText,
    FilmElementVideo,
    FilmFocus,
    FilmPlateCard,
    FilmScene,
    FilmSceneComposite,
    FilmSceneDivider,
    FilmSceneElement,
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
    "composite": (1.0, 120.0),  # real bounds only: the readable-window floor
    # and the render frame cap (FILM_MAX_FRAMES / FILM_FPS) — a composition
    # scene's length is the material's, never a craft band
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
    # Composite text elements reuse the words plane's reading cap (ADR-140).
    ("composite", "lines"): 36,
}
# Per-scene item count caps.
_LIST_CAPS = {
    "words.lines": 4,
    "divider.roll": 5,
    "ui.focuses": 3,
    "plate.cards": 4,
    "composite.elements": 6,
    "composite.text-lines": 4,
}

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

# The accent is the emphasis TEXT color (accent_style="color" spans and
# tone="accent" elements) — distinct from the legacy inverted chip, which
# needs no third color.
_DEFAULT_THEME = {"canvas": "#F7F6F2", "ink": "#141414", "accent": "#FF6A1B"}
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
        description="Spoken narration over the film (配音讲解). A NEW film "
        "defaults OFF: true ONLY when the user explicitly asked for spoken "
        "narration — never on your own initiative; null/false = silent cut "
        "(no synthesis, no TTS cost; the music bed is an independent "
        "choice — 'no voiceover' never implies 'no music'). The storyboard "
        "may still draft per-scene narration so the review table shows the "
        "words and a later 'add voiceover' re-opens synthesis of those "
        "lines.",
    )
    music_mood: str | None = Field(
        default=None,
        description="Background-music mood for the bed (e.g. 'calm', "
        "'upbeat', 'cinematic') — or 'off' to ship the film with NO music "
        "bed (a real off state: later versions keep it until a mood is "
        "named again). Null = the persona's skin default, "
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
    # Text source (ADR-138 §7.6): the copy itself. Present = a text film (no
    # webpage anywhere in the chain — the words are the material). Absent =
    # a web film; the keys drop out of the canonical form entirely.
    text: str | None = Field(
        default=None,
        description="The copy for a TEXT film (text planes on solid color — "
        "no webpage). Its ROLE comes from the user's stated direction, "
        "never from the mere fact they pasted text: 'keep my wording' / "
        "逐字 = their copy preserved (verbatim true); 'adapt / polish / "
        "提炼' or copy you drafted and they accepted = your authored version "
        "(verbatim false). Repeat the presented version's params "
        "byte-for-byte when docking the proposal — an omitted verbatim "
        "inherits the decided version's mode, it is never re-guessed. "
        "Null = a web film (the URL rides material_urls).",
    )
    verbatim: bool | None = Field(
        default=None,
        description="Only meaningful with text: true = preserve the copy "
        "word for word (never rewritten, reordered or trimmed); false = you "
        "authored/adapted it from the user's brief. The mode is the "
        "direction-stage decision — pasting text alone NEVER implies true. "
        "Null inherits the decided version's mode; only a first version "
        "with no decided mode reads null as true (the legacy lens for "
        "already-stored versions — preserve is the safe read).",
    )
    target_seconds: float | None = Field(
        default=None,
        description="Only with text: the user's named total duration (e.g. "
        "20 for '做一个20秒视频'). Null = the system paces the copy at its "
        "natural reading time. A named duration is honored even when FASTER "
        "than the natural reading pace — the user's explicit choice (the "
        "presentation notes the readability impact); only a duration over "
        "the 120s render frame cap rejects.",
    )
    scene_count: int | None = Field(
        default=None,
        description="Only with text: the user's named scene count (e.g. 6 "
        "for '改成6幕'). The segmentation lands on exactly this count. "
        "Null = the director picks.",
    )
    group_chars: list[int] | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="Only with text: the user's named ON-SCREEN GROUP size "
        "as [min, max] characters per screen ('一次只展示3-5个字' → [3, 5]) "
        "— each screen shows ONE group of the copy, the previous group "
        "leaving as the next enters; the words themselves stay byte-exact "
        "(a citation line splits into pieces, never rewrites). Count: a "
        "CJK character or latin letter is 1; punctuation and spaces count "
        "0 (punctuation rides its group, never a screen of its own). "
        "Null = the director paces the screens itself.",
    )

    @model_validator(mode="after")
    def _group_chars_ordered(self) -> "LaunchFilmParams":
        if self.group_chars is not None:
            lo, hi = self.group_chars
            if not (1 <= lo <= hi):
                raise ValueError(
                    "group_chars is [min, max] with 1 <= min <= max"
                )
        return self


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


@dataclass(frozen=True)
class StoryboardMediaAsset:
    """One media asset a composite scene's element cites (ADR-140).
    ``duration_seconds`` None = UNKNOWN (a dormant video nobody ran ASR on
    yet) — the two-gate law: a known duration is checked at design time; an
    unknown one is probed at the run/patch seats and the truth checked
    there, never guessed."""

    id: str
    key: str | None  # storage key (assets.file_url); None = no bytes
    kind: str  # "video" | "image" (assets.type's value)
    title: str | None
    duration_seconds: float | None
    width: int | None
    height: int | None


@dataclass(frozen=True)
class StoryboardMedia:
    """The composite scenes' media universe, keyed by asset id. A cited id
    ABSENT here is the validator's unresolved-asset violation — the map
    never invents an entry."""

    assets: dict[str, StoryboardMediaAsset]


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
    accent). ``span`` cites a PIECE of the line — [start, end) character
    offsets into the line as printed (every printed character counts 1,
    CJK glyph or latin letter alike; the end is exclusive). Null = the
    whole line. Code snaps a boundary that would sever a latin word or a
    combining mark (``_snap_span``), never the model; a verbatim line's
    cited pieces must tile it in order — nothing dropped, repeated or
    added (the coverage law in ``assemble_text_storyboard``)."""

    model_config = ConfigDict(extra="forbid")

    line: int
    fit: Literal["full", "head", "tail"] = "full"
    accent: str | None = None
    span: list[int] | None = Field(default=None, min_length=2, max_length=2)

    @model_validator(mode="before")
    @classmethod
    def _natural_citation(cls, data: Any) -> Any:
        """顺形 read tolerance: the model's NATURAL citation spellings fold
        into the canonical ``{"line": int}`` — a bare ``"L3"``/``3``, or an
        ``{"id": "L3"}`` object. Anything else passes through untouched so
        pydantic's own rejection stays the honest terminal (no silent
        coercion of genuinely malformed input)."""
        if isinstance(data, bool):
            return data
        if isinstance(data, int):
            return {"line": data}
        if isinstance(data, str):
            m = re.fullmatch(r"[Ll]?(\d+)", data.strip())
            return {"line": int(m.group(1))} if m else data
        if isinstance(data, dict) and "line" not in data and "id" in data:
            ident = data["id"]
            if isinstance(ident, int) and not isinstance(ident, bool):
                return {**{k: v for k, v in data.items() if k != "id"}, "line": ident}
            if isinstance(ident, str):
                m = re.fullmatch(r"[Ll]?(\d+)", ident.strip())
                if m:
                    return {
                        **{k: v for k, v in data.items() if k != "id"},
                        "line": int(m.group(1)),
                    }
        return data


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
        base_text = line.text
        if ref.span is not None:
            # A cited piece (the span law lives on CopyRef): code slices,
            # snapped word/cluster-safe — the model never counts to a
            # severed boundary.
            s, e = _snap_span(base_text, ref.span[0], ref.span[1])
            base_text = base_text[s:e].strip()
        text = _fit_to_cap(base_text, cap, "head" if where.endswith(".roll") and ref.fit == "full" else ref.fit)
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
            cold_lines = [
                creative(t, TEXT_CAPS[("words", "lines")], f"{where}.lines")
                for t in direction.cold_open
            ]
            resolved_scenes.append(FilmSceneWords(
                type="words", seconds=secs, dark=True, narration=narration,
                scene_id=scene.key,
                lines=cold_lines,
                copy_text="\n".join(t.replace("*", "") for t in cold_lines),
            ))
        elif scene.type == "hero":
            resolved_scenes.append(FilmSceneHero(
                type="hero", seconds=secs, narration=narration,
                scene_id=scene.key,
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
                scene_id=scene.key,
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
                scene_id=scene.key,
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
                scene_id=scene.key,
                title=_fit_to_cap(title_line.text, TEXT_CAPS[("plate", "title")], "head"),
                cards=cards[:4],
            ))
        elif scene.type == "reveal":
            lead = (direction.reveal_lead or "").strip() or _phrase(_REVEAL_LEAD, language)
            resolved_scenes.append(FilmSceneReveal(
                type="reveal", seconds=secs, narration=narration,
                scene_id=scene.key,
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
                scene_id=scene.key,
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
# Text source (ADR-138 §7.6 — 文字视频): the grounding universe is the copy
# itself — the user's own text (verbatim mode: cited line by line, NEVER
# rewritten) or the agent's authored draft (authored mode: the draft IS the
# corpus). No webpage, no screenshots, no capture wait; the arc is text
# planes (words scenes) only. Versions / edits / music / voiceover /
# execution / render / billing all ride the EXISTING film chain.
# ---------------------------------------------------------------------------

# Per-source bands: the text film's count/duration law splits into two
# layers (重新归类, 2026-10-22 用户拍板):
#
# REAL TECHNICAL bounds (unconditional, code-justified):
#   * total upper = FILM_MAX_FRAMES / FILM_FPS = 3600 / 30 = 120.0s — the
#     renderer's frame cap (the post-allocation guard at FILM_MAX_FRAMES
#     rejects an over-cap board; this mirrors it upstream). The old 118.0
#     misread the cap: 3600 frames at 30fps is exactly 120s.
#   * the per-scene reading floor — a plane never runs shorter than its
#     reading-time estimate (a scene faster than its words is unwatchable,
#     a user-facing truth, not taste);
#   * the display caps (a cited line must fit one screen).
#
# CRAFT DEFAULTS (建议与冲突发现 — never unconditional rejections):
#   * scene count 2..30 — arc-sanity guidance: the prompt leads with it and
#     the preflight computes a named count's satisfiable range from the
#     densest packing, but a board outside the band stands when the real
#     bounds hold;
#   * total lower 5s — the no-target top-up's rhythm suggestion only (a
#     shorter film stands when every scene is readable).
TEXT_SCENE_COUNT_LIMITS = (2, 30)
TEXT_TOTAL_SECONDS_RANGE = (5.0, FILM_MAX_FRAMES / FILM_FPS)
# Per-scene CRAFT DEFAULTS (配方默认层, not hard law): they anchor the
# allocator's no-target top-up and the prompt's rhythm guidance. A text
# plane's duration has NO estimate-derived gate (2026-10-22 拍板): the
# reading-time estimate is the DEFAULT pace — a named faster total or an
# explicit seconds patch legally scales below it; the hard law is only a
# positive window (zero/negative = illegal data) plus the frame-capped
# total. A long citation line legally earns a window past the 8s default
# (the cf00526d incident's deadlock: an unsplittable citation unit whose
# reading time crossed the ceiling).
TEXT_SCENE_SECONDS: dict[str, tuple[float, float]] = {
    "words": (2.0, 8.0),
    "hero": (2.5, 6.0),
    "divider": (2.0, 6.0),
    "plate": (4.0, 8.0),
    "reveal": (8.0, 14.0),
    # Composite carries no craft band in a text film either (ADR-140): its
    # length is the material's play window — only the real bounds hold.
    "composite": SCENE_SECONDS["composite"],
}
# Page-coupled types can never stand on a text source — named honestly.
# A composite scene is text-legal: its media is an uploaded asset, not a
# captured page.
TEXT_ILLEGAL_SCENES = frozenset({"ui", "end"})

# On-screen reading pace ESTIMATE for the big-type text plane: ~12 latin
# chars/s; a CJK glyph weighs 3 (≈4 chars/s). An estimate that RECOMMENDS
# the default pace (the allocator's no-target rhythm + the presentation's
# faster-pace note), never a precise physics truth and never a technical
# bound (2026-10-22 拍板: the user's named faster total or explicit patch
# legally scales below it).
_TEXT_READ_UNITS_PER_SEC = 12.0
_TEXT_READ_CJK_WEIGHT = 3
# Display-wrap measure: latin char = 1, CJK glyph = 2 (the 168px type wraps
# at ~36 latin chars); a manifest line never exceeds 4 display lines so a
# cited line ALWAYS fits one screen (the model segments, never splits copy).
_TEXT_DISPLAY_CAP = 36
_TEXT_MANIFEST_UNIT_CAP = 4 * _TEXT_DISPLAY_CAP // 2  # 72 units ≈ 2 lines
# Latin word runs are atomic on the split plane — a cut backs off to the
# run's start rather than severing a word (unless the word alone overruns
# the cap).
_LATIN_RUN = re.compile(r"[A-Za-z0-9]+")


def _is_latin_char(ch: str) -> bool:
    return bool(_LATIN_RUN.fullmatch(ch))


def _group_units(text: str) -> int:
    """The user's 字 count for one on-screen group (the named grouping's ONE
    measure — the prompt law, the assembly check and the fallback packing
    all read this): every letter/digit/glyph counts 1 (a CJK character is
    one 字, a latin letter is one); whitespace and punctuation count 0 —
    punctuation RIDES its group, never a screen of its own."""
    return sum(1 for ch in text if ch.isalnum())


def _snap_span(text: str, start: int, end: int) -> tuple[int, int]:
    """Clamp a cited span into range, then snap its boundaries SAFE (the
    span law's mechanical half — the model names approximate boundaries,
    code never severs a grapheme or a word): a boundary landing between a
    base char and its combining mark pulls the cluster together; a
    boundary inside a latin word backs off to the word's start / extends
    to its end. Half-open [start, end) over the line as printed; the
    caller judges emptiness (an empty or whitespace-only resolution is a
    violation, never a silent drop)."""
    n = len(text)
    start = max(0, min(start, n))
    end = max(0, min(end, n))
    while 0 < start < n and unicodedata.combining(text[start]):
        start -= 1
    while 0 < end < n and unicodedata.combining(text[end]):
        end += 1
    if 0 < start < n and _is_latin_char(text[start - 1]) and _is_latin_char(text[start]):
        while start > 0 and _is_latin_char(text[start - 1]):
            start -= 1
    if 0 < end < n and _is_latin_char(text[end - 1]) and _is_latin_char(text[end]):
        while end < n and _is_latin_char(text[end]):
            end += 1
    return start, end


def _atomic_unit_count(text: str) -> int:
    """A line's finest legal citation granularity (the named scene-count
    preflight's provable ceiling): one latin word is one unit (a span never
    severs it); every other non-space character (a CJK glyph, a punctuation
    mark) is one."""
    runs = sum(1 for _ in _LATIN_RUN.finditer(text))
    others = sum(
        1 for ch in text if not ch.isspace() and not _is_latin_char(ch)
    )
    return runs + others


def _group_chars_param(value: Any) -> tuple[int, int] | None:
    """The named on-screen grouping as it rides the params dicts / slots
    (JSON): [min, max] 字 per screen, else None. A malformed value reads as
    absent (the pydantic seats already rejected bad shapes upstream)."""
    if (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and all(isinstance(v, int) and not isinstance(v, bool) for v in value)
        and 1 <= value[0] <= value[1]
    ):
        return (value[0], value[1])
    return None


@dataclass(frozen=True)
class FilmTextSource:
    """The text film's input: the copy, its role (verbatim = the user's own
    words, the zero-rewrite law; False = the agent authored it from a brief),
    and the user's named shape requests (duration / scene count / on-screen
    group size — ``group_chars`` = [min, max] 字 per screen, one group at a
    time; ``_group_units`` is the one measure)."""

    text: str
    verbatim: bool
    target_seconds: float | None = None
    scene_count: int | None = None
    group_chars: tuple[int, int] | None = None


def film_text_source_from_params(params: dict) -> FilmTextSource | None:
    """Project the pinned launch params into the text-film source object.

    The compose and patch presentation seats share this projection so a
    revision's fact sheet keeps the same source, pacing and grouping facts
    as the original design; no model re-read is needed.
    """
    if not params.get("text"):
        return None
    return FilmTextSource(
        text=str(params["text"]),
        verbatim=params.get("verbatim") is not False,
        target_seconds=(
            float(params["target_seconds"])
            if isinstance(params.get("target_seconds"), (int, float))
            and not isinstance(params.get("target_seconds"), bool)
            else None
        ),
        scene_count=(
            int(params["scene_count"])
            if isinstance(params.get("scene_count"), int)
            and not isinstance(params.get("scene_count"), bool)
            else None
        ),
        group_chars=_group_chars_param(params.get("group_chars")),
    )


def _text_source_note(source: FilmTextSource | None) -> str | None:
    """The fact sheet's source line for a text film — the REAL source (echo
    anti-fabrication: a text film never invents a URL). None = web source
    (the caller's page list carries the line). When the user's NAMED total
    is faster than the estimated natural reading time, the line also says
    so (2026-10-22 拍板: the faster pace is the user's explicit choice —
    presented, never silent, never rejected)."""
    if source is None:
        return None
    note = (
        "source: the user's text (verbatim)"
        if source.verbatim
        else "source: copy drafted by the assistant for the user's brief"
    )
    if source.target_seconds is not None:
        # The raw pace estimate (no floor snapping — this is advisory copy,
        # not an allocation): how long the copy takes to READ on screen.
        estimate = (
            sum(
                _read_units(l.text)
                for l in build_text_manifest(source.text)
            )
            / _TEXT_READ_UNITS_PER_SEC
        )
        if source.target_seconds < estimate:
            note += (
                f" · pace: the named {source.target_seconds:g}s is faster "
                f"than the ~{estimate:.0f}s natural reading time — the text "
                "moves quickly"
            )
    if source.group_chars is not None:
        lo, hi = source.group_chars
        note += (
            f" · grouping: {lo}–{hi} characters per screen, one group at a "
            "time (the previous group leaves as the next enters)"
        )
    return note


def _display_units(text: str) -> int:
    return sum(2 if _CJK_CHAR.match(ch) else 1 for ch in text)


def _read_units(text: str) -> int:
    return sum(_TEXT_READ_CJK_WEIGHT if _CJK_CHAR.match(ch) else 1 for ch in text)


def build_text_manifest(text: str) -> list[ManifestLine]:
    """Code-owned split of the source copy into citable lines (行 ID 化 — the
    same citation law as the web manifest): paragraphs first, then sentence
    ends, then clause boundaries (，、；：,;) — EACH boundary lands its own
    line, NEVER a greedy multi-clause pack; the word-atomic unit cap splits
    only an over-cap single clause, as the last resort. A citation unit is a
    citation unit, never a screen: the director COMPOSES consecutive lines
    onto one screen by citing several in one segment, and splits them one
    per screen when the user asks (7276ef13 — a packed multi-clause line is
    unsplittable under verbatim's fit=full citation law, so「按逗号拆成更多
    幕」was mechanically inexpressible while the director believed it could
    comply). Segmentation NEVER alters a character — the lines re-read the
    copy minus split-point whitespace (visual line-wrap is layout, not
    content — the 逐字律's allowed half)."""
    chunks: list[str] = []

    def hard_split(piece: str) -> None:
        """Over-cap residue: cut at the last space inside the cap, else back
        off to the start of a straddled latin word, else at the cap itself
        (a mid-word cut only when the word alone overruns the cap — the
        display wrap's over-cap token rule; a severed word is the
        cf00526d incident's «Superhe|ro»)."""
        piece = piece.strip()
        while piece:
            if _display_units(piece) <= _TEXT_MANIFEST_UNIT_CAP:
                chunks.append(piece)
                return
            used = 0
            cut = 0
            for i, ch in enumerate(piece):
                used += 2 if _CJK_CHAR.match(ch) else 1
                if used > _TEXT_MANIFEST_UNIT_CAP:
                    break
                cut = i + 1
            head = piece[:cut]
            sp = head.rfind(" ")
            if sp > 0:
                head = head[:sp]
            else:
                # No space to fall back to (CJK-dense copy): a latin run
                # straddling the cut backs off to its start — a word is
                # atomic unless it alone overruns the cap.
                last: re.Match[str] | None = None
                for last in _LATIN_RUN.finditer(head):
                    pass
                if last is not None and last.end() == len(head) and last.start() > 0:
                    head = head[: last.start()]
            chunks.append(head.strip())
            piece = piece[len(head):].strip()

    for para in re.split(r"\n+", text):
        para = " ".join(para.split())
        if not para:
            continue
        # Sentence split keeps the delimiter with its sentence; each clause
        # (split AFTER ，、；：,; — the delimiter stays with its clause) is
        # its OWN citation line — no greedy packing (the docstring's law).
        for sent in re.split(r"(?<=[。！？!?…])|(?<=[.])\s+", para):
            for clause in re.split(r"(?<=[，、；：,;])", sent):
                clause = clause.strip()
                if not clause:
                    continue
                if _display_units(clause) <= _TEXT_MANIFEST_UNIT_CAP:
                    chunks.append(clause)
                else:
                    hard_split(clause)
    return [ManifestLine(i + 1, 0, "paragraph", c) for i, c in enumerate(chunks)]


def _wrap_display_lines(text: str, cap: int = _TEXT_DISPLAY_CAP) -> list[str]:
    """Visual wrap of one segment's resolved text into display lines within
    the unit cap — latin at word boundaries, CJK anywhere. NEVER drops,
    duplicates or reorders a character (the 逐字律's mechanical half). The
    cap scales with the size tier (``film_text_line_cap``): a larger font
    wraps earlier, never clips."""
    words = text.split(" ")
    lines: list[str] = []
    cur = ""
    for w in words:
        # A single over-cap token (CJK run / long word) hard-wraps.
        while _display_units(w) > cap:
            if cur:
                lines.append(cur)
                cur = ""
            used = 0
            cut = 0
            for i, ch in enumerate(w):
                used += 2 if _CJK_CHAR.match(ch) else 1
                if used > cap:
                    break
                cut = i + 1
            lines.append(w[:cut])
            w = w[cut:]
        trial = f"{cur} {w}" if cur else w
        if _display_units(trial) <= cap:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return [l for l in lines if l]


class FilmTextSegment(BaseModel):
    """One text plane (one words scene). Verbatim mode: ``refs`` cite the
    manifest's lines in appearance order (fit must be "full" — the zero-
    rewrite law). Authored mode: ``text`` carries the model's own lines.
    Exactly one of the two is set; assembly rejects the mixed/empty shape."""

    model_config = ConfigDict(extra="forbid")

    refs: list[CopyRef] | None = None
    text: list[str] | None = None
    dark: bool | None = None  # null = code alternates for rhythm
    motion: Literal["static", "push", "pull"] | None = None
    enter: Literal["lines", "words"] | None = None
    # Batch B precise timing (scene-relative seconds; code quantizes to the
    # film fps). Null = the pre-parameterization default; explicit zero stays
    # zero. ``enter_*`` requires ``enter="words"`` at validation; the motion
    # window requires a push/pull move.
    enter_start: float | None = Field(default=None, ge=0.0)
    enter_interval: float | None = Field(default=None, ge=0.0)
    enter_duration: float | None = Field(default=None, ge=0.0)
    enter_hold_until: float | None = Field(default=None, ge=0.0)
    motion_start: float | None = Field(default=None, ge=0.0)
    motion_end: float | None = Field(default=None, ge=0.0)
    # The style/exit knobs (FilmSceneWords' field law): exit_duration fades
    # the words out over the window's final seconds (the background never
    # fades with them); motion_scale is the push/pull end scale (null =
    # 1.06); align centers the lines; size picks the font tier;
    # accent_style chooses inverted chip vs accent-color text for *marked*
    # spans; enter_style picks the entrance EFFECT (rise = legacy
    # fade+rise+blur; fade = opacity only) — orthogonal to enter's
    # organization (lines vs words = WHO arrives together).
    exit_duration: float | None = Field(default=None, gt=0.0)
    motion_scale: float | None = Field(default=None, gt=1.0, le=1.25)
    align: Literal["left", "center"] | None = None
    size: Literal["small", "medium", "large"] | None = None
    accent_style: Literal["chip", "color"] | None = None
    enter_style: Literal["rise", "fade", "slide"] | None = None
    narration: str | None = None


# ── Composite direction vocabulary (the text source's media-composition
# birth) ─────────────────────────────────────────────────────────────────
# The director's DRAFT element models: the SAME field law as the board's
# FilmElement* models MINUS ``element_id`` — code owns element identity
# (minted at assembly), so the wire never teaches a handle the model must
# not address. Cross-field rules (window ordering, play ≤ source span) are
# enforced when assembly constructs the real element models — a breach
# surfaces as a repairable FilmViolation, never a ladder-crashing
# ValidationError.


class FilmDraftElementVideo(BaseModel):
    """A video draft element: one SOURCE range of one cited asset playing
    inside one output window (the FilmElementVideo law, identity aside)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["video"]
    asset: str  # an id from the project's media listing — never invented
    source_start: float = Field(ge=0.0)
    source_end: float = Field(gt=0.0)
    at: float = Field(default=0.0, ge=0.0)
    duration: float | None = Field(default=None, gt=0.0)
    rect: FilmElementRect = Field(default_factory=FilmElementRect)
    fit: Literal["cover", "contain"] = "cover"
    keep_audio: bool = False
    z: int = 0


class FilmDraftElementImage(BaseModel):
    """An image draft element (the FilmElementImage law, identity aside)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["image"]
    asset: str
    at: float = Field(default=0.0, ge=0.0)
    until: float | None = Field(default=None, gt=0.0)
    rect: FilmElementRect = Field(default_factory=FilmElementRect)
    fit: Literal["cover", "contain"] = "cover"
    z: int = 0


class FilmDraftElementText(BaseModel):
    """A text draft element (the FilmElementText law, identity aside): the
    copy rides the segment's OWN cite/write law — verbatim mode cites
    manifest lines (``refs``), authored mode writes ``text``."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["text"]
    refs: list[CopyRef] | None = None
    text: list[str] | None = None
    tone: Literal["light", "dark", "accent"] = "light"
    at: float = Field(default=0.0, ge=0.0)
    until: float | None = Field(default=None, gt=0.0)
    rect: FilmElementRect = Field(default_factory=FilmElementRect)
    enter: Literal["lines", "words"] | None = None
    motion: Literal["static", "push", "pull"] | None = None
    enter_start: float | None = Field(default=None, ge=0.0)
    enter_interval: float | None = Field(default=None, ge=0.0)
    enter_duration: float | None = Field(default=None, ge=0.0)
    motion_start: float | None = Field(default=None, ge=0.0)
    motion_end: float | None = Field(default=None, ge=0.0)
    exit_duration: float | None = Field(default=None, gt=0.0)
    motion_scale: float | None = Field(default=None, gt=1.0, le=1.25)
    align: Literal["left", "center"] | None = None
    size: Literal["small", "medium", "large"] | None = None
    accent_style: Literal["chip", "color"] | None = None
    enter_style: Literal["rise", "fade", "slide"] | None = None
    z: int = 0


FilmDraftElement = Annotated[
    FilmDraftElementVideo | FilmDraftElementImage | FilmDraftElementText,
    Field(discriminator="kind"),
]


class FilmCompositeSegment(BaseModel):
    """One composite segment of the direction: a theme-colored background
    plus ordered elements (media + independent text) composing one screen.
    No ``seconds`` — the scene's length is CODE-DERIVED from the element
    windows (the material's play time; see the assembly's frame law), never
    model-guessed."""

    model_config = ConfigDict(extra="forbid")

    dark: bool | None = None  # null = code alternates for rhythm
    elements: list[FilmDraftElement] = Field(min_length=1)
    narration: str | None = None


class FilmTextDirection(BaseModel):
    """The text director's answer (the FilmDirection twin for the text
    source): ONLY the segmentation + per-segment vocabulary — durations are
    code-owned (readability floors + the user's named target; a composite
    segment's length derives from its element windows). A segment is a
    words plane or a composite composition."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    language: str | None = None
    segments: list[FilmTextSegment | FilmCompositeSegment] = Field(min_length=1)


def _resolve_copy_texts(
    *,
    refs: list[CopyRef] | None,
    text: list[str] | None,
    verbatim: bool,
    by_id: dict[int, ManifestLine],
    where: str,
    cited: list[tuple[int, int, int]],
) -> tuple[list[str], list[FilmViolation]]:
    """One copy slot's content resolution — a words segment OR a composite
    text element rides the SAME cite/write law (one seat, never two
    readings): verbatim mode cites manifest lines (``fit`` stays full, an
    optional ``accent`` wraps a substring, an optional ``span`` cites a
    piece of the line — code slices it word/cluster-safe via ``_snap_span``;
    every citation lands in ``cited`` as (line id, start, end) for the
    board-wide tiling coverage check); authored mode takes the model's own
    lines. Returns the content texts (pre-wrap, accents applied) plus any
    violations — an empty texts list with violations means the slot
    produced nothing."""
    violations: list[FilmViolation] = []
    texts: list[str] = []
    if verbatim:
        if text is not None or not refs:
            violations.append(
                FilmViolation(
                    CONSTRAINT_VIOLATION,
                    f"{where}: the user's copy is verbatim-preserved — cite "
                    "its lines with refs (never rewrite them into text)",
                )
            )
            return [], violations
        for ref in refs:
            line = by_id.get(ref.line)
            if line is None:
                violations.append(
                    FilmViolation(
                        INVALID_COPY_REF, f"{where}: line L{ref.line} names no copy line"
                    )
                )
                continue
            if ref.fit != "full":
                violations.append(
                    FilmViolation(
                        INVALID_COPY_REF,
                        f"{where}: line L{ref.line} cited with fit={ref.fit} — "
                        "verbatim copy is never trimmed (fit stays full; a "
                        "PIECE of the line cites span [start, end) instead)",
                    )
                )
                continue
            if ref.span is not None:
                s, e = _snap_span(line.text, ref.span[0], ref.span[1])
                resolved = line.text[s:e].strip()
                if not resolved:
                    violations.append(
                        FilmViolation(
                            INVALID_COPY_REF,
                            f"{where}: line L{ref.line} span "
                            f"[{ref.span[0]},{ref.span[1]}) resolves to "
                            "nothing — cut between glyphs/words, never on "
                            "whitespace alone",
                        )
                    )
                    continue
            else:
                s, e = 0, len(line.text)
                resolved = line.text
            if ref.accent is not None:
                accented = _apply_accent(resolved, ref.accent)
                if accented is None:
                    violations.append(
                        FilmViolation(
                            INVALID_COPY_REF,
                            f"{where}: accent «{ref.accent[:30]}» is not in line L{ref.line}",
                        )
                    )
                    continue
                resolved = accented
            cited.append((ref.line, s, e))
            texts.append(resolved)
        return texts, violations
    if refs is not None or not text:
        violations.append(
            FilmViolation(
                CONSTRAINT_VIOLATION,
                f"{where}: authored mode writes its own lines (text) — "
                "refs cite a user corpus this film does not have",
            )
        )
        return [], violations
    for t in text:
        t = t.strip()
        if not _norm(t):
            violations.append(
                FilmViolation(CONSTRAINT_VIOLATION, f"{where}: blank line")
            )
        texts.append(t)
    return texts, violations


def _draft_element_window_frames(element: FilmSceneElement) -> int | None:
    """A freshly assembled element's bounded window END on the render frame
    grid — the SAME quantized accounting the validator applies (端点先量化,
    never quantize-the-delta): video = at_f + play frames (an explicit
    duration quantized, else the quantized source span); an explicit
    ``until`` quantizes directly. None = unbounded (the element runs to the
    scene's end and does not bound it). The composite scene's own length
    derives from these ends, so the assembled board can never reject ITSELF
    on the grid (a scene whose frames cover every element's quantized end
    by construction)."""
    if element.kind == "video":
        at_f = film_seconds_to_frames(element.at)
        if element.duration is not None:
            play_f = film_seconds_to_frames(element.duration)
        else:
            play_f = film_seconds_to_frames(element.source_end) - film_seconds_to_frames(
                element.source_start
            )
        return at_f + max(play_f, 0)
    if element.until is not None:
        return film_seconds_to_frames(element.until)
    return None


def assemble_text_storyboard(
    direction: FilmTextDirection,
    lines: list[ManifestLine],
    *,
    source: FilmTextSource,
    pinned_language: str | None = None,
    composite_ok: bool = False,
) -> tuple[FilmStoryboard | None, list[FilmViolation]]:
    """Text direction (segmentation + vocabulary) → the resolved board.
    Verbatim mode resolves citations VERBATIM (a trim is a violation, never
    a silent edit); authored mode takes the model's own lines as the corpus.
    Durations are code-owned (readability floors + the named target; a
    composite segment's length DERIVES from its element windows on the
    render frame grid — see ``_draft_element_window_frames``).

    ``composite_ok`` — the media-composition capability's deployment gate
    (settings.film_edits_enabled, read by the orchestration seat): OFF, a
    composite segment is a repairable violation, never an assembled scene
    (the prompt never taught the vocabulary either — declaration and
    enforcement gate together)."""
    violations: list[FilmViolation] = []
    by_id = {l.id: l for l in lines}
    if source.scene_count is not None and len(direction.segments) != source.scene_count:
        violations.append(
            FilmViolation(
                CONSTRAINT_VIOLATION,
                f"the plan named {source.scene_count} scenes; you returned "
                f"{len(direction.segments)} — re-segment to exactly "
                f"{source.scene_count} (merge or split segments, never the words)",
            )
        )
        return None, violations

    # prepared: ("words", seg, display, copy_text, units) per words segment,
    # ("composite", dark_pin, elements, seconds, narration) per composite
    # segment — one entry per segment, in segment order.
    prepared: list[tuple] = []
    cited: list[tuple[int, int, int]] = []
    for i, seg in enumerate(direction.segments):
        where = f"segment[{i + 1}]"
        if isinstance(seg, FilmCompositeSegment):
            if not composite_ok:
                violations.append(
                    FilmViolation(
                        CONSTRAINT_VIOLATION,
                        f"{where}: composite scenes are not available in "
                        "this deployment — keep the arc on text planes (words)",
                    )
                )
                continue
            elements: list[FilmSceneElement] = []
            bounded_f = 0
            has_bound = False
            for el_index, draft in enumerate(seg.elements):
                ewhere = f"{where}.element{el_index + 1}"
                eid = f"e{el_index + 1}"  # birth-minted; ensure_scene_ids keeps them
                try:
                    if draft.kind == "video":
                        element: FilmSceneElement = FilmElementVideo(
                            kind="video", element_id=eid, asset=draft.asset,
                            source_start=draft.source_start,
                            source_end=draft.source_end, at=draft.at,
                            duration=draft.duration, rect=draft.rect,
                            fit=draft.fit, keep_audio=draft.keep_audio, z=draft.z,
                        )
                    elif draft.kind == "image":
                        element = FilmElementImage(
                            kind="image", element_id=eid, asset=draft.asset,
                            at=draft.at, until=draft.until, rect=draft.rect,
                            fit=draft.fit, z=draft.z,
                        )
                    else:
                        texts, el_violations = _resolve_copy_texts(
                            refs=draft.refs, text=draft.text,
                            verbatim=source.verbatim, by_id=by_id,
                            where=ewhere, cited=cited,
                        )
                        violations.extend(el_violations)
                        if not texts:
                            continue
                        display = [
                            dl
                            for t in texts
                            for dl in _wrap_display_lines(
                                t,
                                film_text_line_cap(
                                    draft.size,
                                    seat="element",
                                    rect_w=draft.rect.w,
                                ),
                            )
                        ]
                        if len(display) > _LIST_CAPS["composite.text-lines"]:
                            violations.append(
                                FilmViolation(
                                    CONSTRAINT_VIOLATION,
                                    f"{ewhere}: wraps to {len(display)} display "
                                    f"lines — over the {_LIST_CAPS['composite.text-lines']}-line "
                                    "element; split it into more text elements "
                                    "(never shrink the words away)",
                                )
                            )
                            continue
                        # The element's pre-wrap corpus anchors at assembly
                        # time (逐字律 — the words plane's same seat).
                        copy_text = "\n".join(t.replace("*", "") for t in texts)
                        element = FilmElementText(
                            kind="text", element_id=eid, lines=display,
                            tone=draft.tone, at=draft.at, until=draft.until,
                            rect=draft.rect, enter=draft.enter,
                            motion=draft.motion, enter_start=draft.enter_start,
                            enter_interval=draft.enter_interval,
                            enter_duration=draft.enter_duration,
                            motion_start=draft.motion_start,
                            motion_end=draft.motion_end,
                            exit_duration=draft.exit_duration,
                            motion_scale=draft.motion_scale,
                            align=draft.align, size=draft.size,
                            accent_style=draft.accent_style,
                            enter_style=draft.enter_style,
                            copy_text=copy_text, z=draft.z,
                        )
                except ValidationError as exc:
                    # A cross-field breach (window ordering, play window past
                    # the source span, rect past the canvas) is a repairable
                    # draft defect — the bounded rewrite fixes it; never a
                    # ladder-crashing exception.
                    msg = exc.errors()[0].get("msg", str(exc))
                    violations.append(
                        FilmViolation(CONSTRAINT_VIOLATION, f"{ewhere}: {msg}")
                    )
                    continue
                elements.append(element)
                end_f = _draft_element_window_frames(element)
                if end_f is not None:
                    has_bound = True
                    bounded_f = max(bounded_f, end_f)
            if not elements:
                continue  # the element violations above already say why
            if not has_bound:
                violations.append(
                    FilmViolation(
                        CONSTRAINT_VIOLATION,
                        f"{where}: a composite scene's length derives from "
                        "its element windows — none of these elements bounds "
                        "it (no video play window, no explicit until); give "
                        "one element a concrete window",
                    )
                )
                continue
            # The scene's length on the frame grid: every element's
            # quantized end covered by construction (≥ the 1s structural
            # floor, snapped UP to the half-second grid).
            scene_frames = max(
                _MIN_SCENE_FRAMES, ((bounded_f + 14) // 15) * 15
            )
            prepared.append(
                (
                    "composite",
                    seg.dark,
                    elements,
                    scene_frames / FILM_FPS,
                    seg.narration,
                )
            )
            continue
        texts, seg_violations = _resolve_copy_texts(
            refs=seg.refs, text=seg.text, verbatim=source.verbatim,
            by_id=by_id, where=where, cited=cited,
        )
        violations.extend(seg_violations)
        if not texts:
            continue
        display = [
            dl
            for t in texts
            for dl in _wrap_display_lines(
                t, film_text_line_cap(seg.size, seat="words")
            )
        ]
        if len(display) > _LIST_CAPS["words.lines"]:
            violations.append(
                FilmViolation(
                    CONSTRAINT_VIOLATION,
                    f"{where}: wraps to {len(display)} display lines — over the "
                    f"{_LIST_CAPS['words.lines']}-line screen; split this segment "
                    "into more scenes (never shrink the words away)",
                )
            )
            continue
        # The scene's pre-wrap corpus anchors at assembly time (逐字律): the
        # display lines below are this text's layout result — later corpus
        # projections re-derive from the source, never from the wrap.
        copy_text = "\n".join(t.replace("*", "") for t in texts)
        prepared.append(
            ("words", seg, display, copy_text, sum(_read_units(dl) for dl in display))
        )
    if source.verbatim:
        # 逐字律's coverage half (deterministic, never the model's say-so):
        # the full copy shows — every manifest line cited exactly once
        # ACROSS THE WHOLE BOARD (words segments and composite text
        # elements alike — one citation universe), now at CHARACTER
        # granularity: a line cited in pieces (span) must be tiled by its
        # pieces in order — a dropped gap is silent deletion, an overlap is
        # invention; only split-point whitespace may vanish between pieces
        # (the manifest law's own half).
        by_line: dict[int, list[tuple[int, int]]] = {}
        for line_id, s, e in cited:
            by_line.setdefault(line_id, []).append((s, e))
        problems: list[str] = []
        missing = [l.id for l in lines if l.id not in by_line]
        if missing:
            problems.append(
                "never cited: " + ", ".join(f"L{i}" for i in missing)
            )
        for l in lines:
            spans = by_line.get(l.id)
            if not spans:
                continue
            cursor = 0
            broken = False
            for s, e in spans:
                if s < cursor:
                    problems.append(
                        f"L{l.id}: the piece starting at character {s} "
                        "overlaps or re-shows an earlier citation"
                    )
                    broken = True
                    break
                gap = l.text[cursor:s]
                if gap.strip():
                    problems.append(
                        f"L{l.id}: «{gap[:20]}» never shows — the cited "
                        "pieces must tile the line in order, dropping "
                        "nothing (split-point whitespace may vanish)"
                    )
                    broken = True
                    break
                cursor = e
            if not broken and l.text[cursor:].strip():
                problems.append(
                    f"L{l.id}: the tail «{l.text[cursor:][:20]}» never "
                    "shows — cite through the line's end"
                )
        if problems:
            violations.append(
                FilmViolation(
                    CONSTRAINT_VIOLATION,
                    "verbatim copy is shown in FULL — every line exactly once ("
                    + "; ".join(problems)
                    + ")",
                )
            )
        # 逐字律's ORDER half (7276ef13 修复批): the copy shows in the text's
        # own order — citations ascend across the whole board. Coverage alone
        # never noticed a reorder, and clause-fine citation units make an
        # accidental one reachable; a deliberate reorder is a content change,
        # which verbatim mode never makes (改编模式 writes its own lines).
        # Equal ids are legal: one line cited in several consecutive pieces
        # (span) — the per-line tiling above judges their inner order.
        cited_ids = [line_id for line_id, _, _ in cited]
        for prev, cur in zip(cited_ids, cited_ids[1:]):
            if cur < prev:
                violations.append(
                    FilmViolation(
                        CONSTRAINT_VIOLATION,
                        "verbatim copy shows in the text's OWN order — line "
                        f"L{cur} is cited after L{prev}; re-cite the lines in "
                        "ascending order (never reorder the user's words)",
                    )
                )
                break
    # The named on-screen grouping (「一次只展示3-5个字」→ group_chars): each
    # words plane carries ONE group within the named band — one group shows
    # at a time, the previous leaves as the next enters (a group = its own
    # scene; never stack groups onto one screen). Measured by _group_units
    # (punctuation rides its group, counts 0). The honest exceptions: a
    # single unsplittable latin word over the cap stands (a word never
    # severs), and a runt group stands only when nothing legal can absorb
    # it (merging into the neighbour would overfill it and no two-group
    # repartition of the pair fits the band) — it is presented as-is,
    # never padded or dropped to reach the number.
    if source.group_chars is not None:
        lo_g, hi_g = source.group_chars
        words_seq = [
            (i + 1, item[3])
            for i, item in enumerate(prepared)
            if item[0] == "words"
        ]
        for pos, (seg_no, copy) in enumerate(words_seq):
            units = _group_units(copy)
            if units > hi_g:
                if re.fullmatch(r"[A-Za-z0-9]+", copy):
                    continue  # one unsplittable word — the honest exception
                violations.append(
                    FilmViolation(
                        CONSTRAINT_VIOLATION,
                        f"segment[{seg_no}] shows {units} characters "
                        f"(«{copy[:24]}») — the named grouping is "
                        f"{lo_g}–{hi_g} per screen: split the citation with "
                        "span (code keeps the words byte-exact), never by "
                        "rewriting or dropping them",
                    )
                )
            elif units < lo_g and len(words_seq) > 1:
                nbr_units = (
                    _group_units(words_seq[pos - 1][1])
                    if pos
                    else _group_units(words_seq[1][1])
                )
                merged = nbr_units + units
                if merged <= hi_g or merged >= 2 * lo_g:
                    violations.append(
                        FilmViolation(
                            CONSTRAINT_VIOLATION,
                            f"segment[{seg_no}] shows only {units} "
                            f"characters («{copy[:24]}») — the named "
                            f"grouping is {lo_g}–{hi_g} per screen: merge it "
                            "into its neighbour or rebalance the two groups "
                            f"({merged} characters between them)",
                        )
                    )
                # else: the unavoidable runt — it stands, presented as-is.
    if violations:
        return None, violations
    if not prepared:
        return None, [
            FilmViolation(CONSTRAINT_VIOLATION, "no segment carries any text")
        ]

    words_units = [item[4] for item in prepared if item[0] == "words"]
    composite_total = sum(item[3] for item in prepared if item[0] == "composite")
    seconds_words: list[float] = []
    if words_units:
        seconds_words, overflow = _assign_text_seconds(
            words_units, source.target_seconds, base=composite_total
        )
        if overflow is not None:
            violations.append(FilmViolation(CONSTRAINT_VIOLATION, overflow))
            return None, violations
    elif source.target_seconds is not None and composite_total > 0:
        # All-composite board with a named total: the material owns the
        # length, so the law is a FRAME-level match — the named total and
        # the derived total quantize to the same frame count through the
        # ONE seat. A match passes as-is; a mismatch rejects with the
        # CONCRETE delta (frames and direction) so the next candidate
        # adjusts its media windows — never a demand for words filler
        # planes, and never a silent stretch/loop/pad of the user's
        # source ranges or animation timing.
        target_f = film_seconds_to_frames(source.target_seconds)
        total_f = film_seconds_to_frames(composite_total)
        if target_f != total_f:
            gap_f = total_f - target_f
            direction = (
                f"{gap_f} frame(s) over" if gap_f > 0 else f"{-gap_f} frame(s) short"
            )
            violations.append(
                FilmViolation(
                    CONSTRAINT_VIOLATION,
                    f"the named {source.target_seconds:g}s does not match "
                    f"the media compositions' material-derived total "
                    f"{composite_total:g}s — {direction} on the render "
                    "grid; adjust the media windows toward the named "
                    "total (the source ranges and animation timing are "
                    "yours to revise — the system never stretches, loops "
                    "or pads them on its own)",
                )
            )
            return None, violations
    scenes: list[FilmScene] = []
    word_idx = 0
    for i, item in enumerate(prepared):
        dark_default = i % 2 == 1
        if item[0] == "composite":
            _, dark_pin, elements, scene_seconds, narration = item
            scenes.append(
                FilmSceneComposite(
                    type="composite",
                    seconds=scene_seconds,
                    dark=dark_pin if dark_pin is not None else dark_default,
                    elements=elements,
                    narration=narration,
                )
            )
            continue
        _, seg, display, copy_text, _units = item
        scenes.append(
            FilmSceneWords(
                type="words",
                seconds=seconds_words[word_idx],
                dark=seg.dark if seg.dark is not None else dark_default,
                lines=display,
                motion=seg.motion,
                enter=seg.enter,
                enter_start=seg.enter_start,
                enter_interval=seg.enter_interval,
                enter_duration=seg.enter_duration,
                enter_hold_until=seg.enter_hold_until,
                motion_start=seg.motion_start,
                motion_end=seg.motion_end,
                exit_duration=seg.exit_duration,
                motion_scale=seg.motion_scale,
                align=seg.align,
                size=seg.size,
                accent_style=seg.accent_style,
                enter_style=seg.enter_style,
                narration=seg.narration,
                copy_text=copy_text,
            )
        )
        word_idx += 1
    board = FilmStoryboard(
        scenes=scenes,
        name=direction.name,
        language=direction.language or pinned_language,
    )
    return board, violations


def _text_read_floor(units: int) -> float:
    """One text plane's reading-time ESTIMATE snapped UP to the half-second
    grid (a floor never rounds down past the estimate; the craft band's
    lower stop as the absolute floor). The ONE measure the allocator and
    the feasibility preflight read — a RECOMMENDATION, never a gate
    (2026-10-22 拍板: a named faster total or an explicit seconds patch
    legally scales below it; the validator never enforces it)."""
    return max(
        TEXT_SCENE_SECONDS["words"][0],
        math.ceil(units / _TEXT_READ_UNITS_PER_SEC * 2 - 1e-9) / 2,
    )


def _assign_text_seconds(
    segment_units: list[int], target: float | None, *, base: float = 0.0
) -> tuple[list[float], str | None]:
    """Code-owned text-plane durations. The reading-time estimate is the
    DEFAULT pace, never a bound (2026-10-22 拍板 — 估计 = 建议，不是不可
    突破的技术边界): no target = the floors recommend a readable rhythm;
    a NAMED target is the user's law — the floors rescale to it in BOTH
    directions (slower or faster than the estimate; a faster pace's
    readability impact rides the presentation's pace note —
    ``_text_source_note`` — never a silent change, never a rejection).
    The ONE refusal is REAL, not estimated: a target so small that a scene
    quantizes to ZERO on the half-second render grid (nothing would
    render).

    ``base`` = the seconds already owned by material-bound scenes (media
    compositions — their length derives from the element windows and never
    rescales): a named target paces the text planes into the REMAINING
    room (target − base), and the no-target top-up counts the base toward
    the total floor."""
    hi = TEXT_SCENE_SECONDS["words"][1]
    floors = [_text_read_floor(u) for u in segment_units]
    if target is not None:
        # The user named the total — scale the floor proportions to it
        # (up OR down). The 8s craft default never clamps; the reading
        # estimate never floors an explicit choice.
        room = target - base
        if room <= 0:
            return [], (
                f"the named {target:g}s is already filled by the media "
                f"composition scenes ({base:g}s) — the text planes have no "
                "room; name a longer duration or shorten the media windows"
            )
        scale = room / sum(floors)
        secs = [round(f * scale * 2) / 2 for f in floors]
        if any(s <= 0 for s in secs):
            return [], (
                f"the named {target:g}s squeezes a scene to zero on the "
                "half-second render grid — name a longer duration or fewer "
                "scenes"
            )
        return secs, None
    # No target: the reading estimate IS the recommendation — floors, then
    # top up short totals to the text band's floor, inside the craft
    # default band (the default rhythm's own seat).
    secs = list(floors)
    while base + sum(secs) < TEXT_TOTAL_SECONDS_RANGE[0] and any(s < hi for s in secs):
        i = min(range(len(secs)), key=lambda j: secs[j])
        secs[i] = min(hi, secs[i] + 0.5)
    return [round(s * 2) / 2 for s in secs], None


def _group_spans(text: str, lo: int, hi: int) -> list[str]:
    """One line's deterministic split into [lo, hi]-unit groups (the
    fallback's seat — the design path's groups are the director's spans,
    checked at assembly; the unit law is ``_group_units``'s). Tokens: a
    latin word or one glyph, each with its trailing punctuation/space
    attached (punctuation rides its text, never opens a group); combining
    marks cling to their base. Greedy-pack up to hi, then a runt tail
    merges into its predecessor when the sum fits, else borrows tokens
    back until it reaches lo; a single over-hi token (a long word) stands
    alone — never a severed word, never a dropped or added character."""
    tokens: list[str] = []
    i, n = 0, len(text)
    while i < n:
        m = _LATIN_RUN.match(text, i)
        if m:
            j = m.end()
        else:
            j = i + 1
            while j < n and unicodedata.combining(text[j]):
                j += 1
        while j < n and not text[j].isalnum():
            j += 1
        tokens.append(text[i:j])
        i = j
    groups: list[list[str]] = []
    cur: list[str] = []
    cur_u = 0
    for tok in tokens:
        w = _group_units(tok)
        if cur and cur_u + w > hi:
            groups.append(cur)
            cur, cur_u = [], 0
        cur.append(tok)
        cur_u += w
    if cur:
        groups.append(cur)
    if len(groups) >= 2:
        last_u = sum(_group_units(t) for t in groups[-1])
        if last_u < lo:
            prev_u = sum(_group_units(t) for t in groups[-2])
            if prev_u + last_u <= hi:
                groups[-2].extend(groups.pop())
            else:
                # Rebalance: borrow the predecessor's tail tokens until the
                # tail reaches the floor — never starving the predecessor
                # below it, never pushing the tail over the cap; a move
                # that can't work leaves the runt standing (the honest
                # exception, presented as-is).
                while groups[-2] and last_u < lo:
                    moved = groups[-2][-1]
                    moved_u = _group_units(moved)
                    prev_rest = prev_u - moved_u
                    if last_u + moved_u > hi:
                        break
                    if prev_rest < lo and len(groups[-2]) > 1:
                        break
                    groups[-1].insert(0, groups[-2].pop())
                    last_u += moved_u
                    prev_u = prev_rest
                    if not groups[-2]:
                        del groups[-2]
                        break
    return [g for g in ("".join(toks).strip() for toks in groups) if g]


def fixed_text_storyboard(
    lines: list[ManifestLine],
    *,
    source: FilmTextSource,
    language: str | None = None,
) -> FilmStoryboard | None:
    """The no-LLM text board (the worker's unattended fallback — the same
    law as fixed_direction): code segments the manifest greedily (up to 4
    display lines per scene, order preserved) — or, when the user named an
    on-screen grouping, packs the copy into [min, max]-unit groups (one
    group per scene, ``_group_spans``) — alternates the planes, and assigns
    readability durations. None = the copy can't stand at all."""
    if not lines:
        return None
    segments: list[list[str]] = []
    if source.group_chars is not None:
        lo_g, hi_g = source.group_chars
        pieces: list[str] = []
        for l in lines:
            pieces.extend(_group_spans(l.text, lo_g, hi_g))
        # Short pieces merge onto one screen while the group stays within
        # the band; an under-floor runt stands (presented as-is, never
        # padded or dropped to reach the number).
        cur_p: list[str] = []
        cur_u = 0
        for p in pieces:
            w = _group_units(p)
            if cur_p and cur_u + w > hi_g:
                segments.append(cur_p)
                cur_p, cur_u = [], 0
            cur_p.append(p)
            cur_u += w
        if cur_p:
            segments.append(cur_p)
    else:
        cur_l: list[str] = []
        cur_display = 0
        for l in lines:
            n = len(_wrap_display_lines(l.text))
            if cur_l and cur_display + n > _LIST_CAPS["words.lines"]:
                segments.append(cur_l)
                cur_l, cur_display = [], 0
            cur_l.append(l.text)
            cur_display += n
        if cur_l:
            segments.append(cur_l)
    if source.scene_count is not None and len(segments) != source.scene_count:
        return None  # a pinned count with no model to re-segment — fail honestly
    prepared = [
        (
            [dl for piece in seg for dl in _wrap_display_lines(piece)],
            # The pieces ARE the pre-wrap corpus (no accents were ever
            # applied on this fallback path) — anchor them per scene.
            "\n".join(seg),
        )
        for seg in segments
    ]
    seconds, overflow = _assign_text_seconds(
        [sum(_read_units(dl) for dl in display) for display, _ in prepared],
        source.target_seconds,
    )
    if overflow is not None:
        return None
    return FilmStoryboard(
        scenes=[
            FilmSceneWords(
                type="words", seconds=s, dark=(i % 2 == 1), lines=display,
                copy_text=copy_text,
            )
            for i, ((display, copy_text), s) in enumerate(zip(prepared, seconds, strict=True))
        ],
        name=None,
        language=language,
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
    if t == "composite":
        # Only the text elements put authored strings on screen — media
        # elements are imagery (ADR-140).
        return [
            ("lines", line)
            for el in scene.elements
            if el.kind == "text"
            for line in el.lines
        ]
    return []


# ---------------------------------------------------------------------------
# Precise words-plane timing (Batch B)
# ---------------------------------------------------------------------------

FILM_WORDS_TIMING_FIELDS = frozenset(
    {
        "enter_start",
        "enter_interval",
        "enter_duration",
        "enter_hold_until",
        "motion_start",
        "motion_end",
        "exit_duration",
        "motion_scale",
    }
)
# The words plane's style knobs (words scene AND composite text element):
# presence-sensitive like the timing fields — absent keeps, explicit null
# restores the default, an explicit value lands.
FILM_WORDS_STYLE_FIELDS = frozenset(
    {"align", "size", "accent_style", "enter_style"}
)
_ENTER_TIMING_FIELDS = frozenset(
    {"enter_start", "enter_interval", "enter_duration", "enter_hold_until"}
)
_MOTION_TIMING_FIELDS = frozenset({"motion_start", "motion_end"})

# Font size tiers (px on the 1920 design grid — the renderer's map must
# match byte-for-byte). "medium" IS the pre-tier size (168 words plane /
# 80 composite text element); null reads as medium. The line-wrap capacity
# scales with the tier, so a larger tier never clips or drops copy.
FILM_TEXT_SIZE_PX = {
    "words": {"small": 120, "medium": 168, "large": 232},
    "element": {"small": 56, "medium": 80, "large": 120},
}


_WORDS_TEXT_WIDTH_PX = 1920 - 2 * 220  # the words plane's padded text box


def film_text_line_cap(
    size: str | None,
    *,
    seat: str,
    rect_w: float = 1.0,
    motion_scale: float | None = None,
) -> int:
    """A size tier's per-line display-unit capacity (CJK glyph = 2 units at
    1em advance, latin letter = 1 — an ESTIMATE anchored on the em advance,
    not a font-metric measurement). Two laws by tier, one seat: the legacy
    "medium" tier keeps the pre-existing 36-unit convention (the assembly's
    historical wrap cap — loose by design, tightened nowhere, so legacy
    boards revalidate byte-identically); the NEW tiers (small/large) carry
    the PIXEL-honest cap — a line fits ONE visual row inside its text box,
    so a larger font wraps earlier and never clips (the element seat's box
    is its rect's pixel width; the words seat's is the padded canvas). The
    words seat needs no motion-scale discount (its padded box keeps 22%
    horizontal headroom against the canvas — past the 1.25 amplitude cap);
    the element seat's rect CLIPS (overflow hidden), so a push/pull
    amplitude shrinks its effective width."""
    if size in (None, "medium"):
        return _TEXT_DISPLAY_CAP
    px = FILM_TEXT_SIZE_PX[seat][size]
    width_px = _WORDS_TEXT_WIDTH_PX if seat == "words" else 1920 * rect_w
    if seat == "element" and motion_scale is not None:
        width_px /= motion_scale
    return max(8, math.floor(width_px / px * 2))


def film_text_vertical_violation(
    size: str | None,
    *,
    seat: str,
    lines: int,
    rect_h: float = 1.0,
    motion_scale: float | None = None,
) -> str | None:
    """The NEW tiers' vertical fit check (medium keeps the legacy
    convention, so it never runs here): pixel-honest line caps guarantee
    one visual row per line, so the text block's height is lines × px ×
    line-height — it must fit the box's pixel height (the words plane's
    canvas, the element's rect). A push/pull move scales the block around
    its center, so the estimate carries the amplitude (an explicit
    motion_scale, else the legacy 1.06 — the caller passes it only when the
    plane actually moves). Returns the conflict text, None = fits."""
    if size in (None, "medium"):
        return None
    px = FILM_TEXT_SIZE_PX[seat][size]
    scale = motion_scale if motion_scale is not None else 1.0
    need_px = lines * px * 1.04 * scale
    box_px = 1080 if seat == "words" else 1080 * rect_h
    if need_px > box_px + 1e-6:
        scaled = f" at the ×{scale:g} motion scale" if scale != 1.0 else ""
        return (
            f"{lines} lines at the {size} size{scaled} need "
            f"{need_px:.0f}px of vertical room but the box holds "
            f"{box_px:.0f}px — fewer lines, a smaller size, a smaller "
            "scale, or a taller box (never a silent crop)"
        )
    return None
# A parameterized entrance's absent duration gets an explicit 12-frame default;
# a spec carrying NO timing keys keeps the legacy unparameterized spring.
_ENTER_DURATION_DEFAULT_FRAMES = 12
_ACCENT_SPLIT = re.compile(r"\*([^*]+)\*")
_WORD_TOKEN = re.compile(
    r"[㐀-䶿一-鿿豈-﫿]|[^\s㐀-䶿一-鿿豈-﫿]+"
)


def film_seconds_to_frames(seconds: float) -> int:
    """Animation seconds → integer frames (Batch B's ONE quantization seat):
    nearest frame, halves round UP, a 1e-9 epsilon steadies exact half-frame
    boundaries — the renderer runs the SAME float64 formula (never its own
    rounding), so a value can never land on different frames on the two
    sides. The error bound is PER VALUE (< half a frame, <0.017s at 30fps):
    a per-token interval's quantization delta accumulates linearly down the
    token run — the presentation names the last token's computed start/end
    frames instead of claiming a sequence-wide sub-frame bound."""
    return max(0, math.floor(seconds * FILM_FPS + 0.5 + 1e-9))


def word_enter_token_count(lines: list[str]) -> int:
    """The enter="words" token count (the renderer tokenizer's Python mirror):
    latin whitespace runs are one token, CJK glyphs are one each, and the
    accent split happens FIRST — the chip edge is a token edge (a latin run
    never merges across it)."""
    return sum(
        len(_WORD_TOKEN.findall(part))
        for line in lines
        for part in _ACCENT_SPLIT.split(line)
    )


def _legacy_word_step_frames(frames: int, token_count: int) -> int:
    """The pre-parameterization cadence, preserved as the default step."""
    return max(2, min(4, int((frames * 0.6) / max(1, token_count))))


def _enter_schedule_frames(
    lines: list[str],
    *,
    frames: int,
    enter_start: float | None,
    enter_interval: float | None,
    enter_duration: float | None,
    enter_hold_until: float | None,
    unit: Literal["words", "lines"] = "words",
) -> tuple[int, int, int, int, int, int, int]:
    """The ONE enter-schedule computation for the words plane.

    ``unit='words'`` keeps the legacy token cadence. ``unit='lines'`` counts
    whole display lines and defaults to their legacy 8-frame stagger; it is
    used only when explicit line timing is present, so an unparameterized
    legacy board keeps its original renderer branch and digest.
    """
    tokens = word_enter_token_count(lines) if unit == "words" else len(lines)
    start_f = film_seconds_to_frames(
        enter_start if enter_start is not None else 0.0
    )
    step_f = (
        film_seconds_to_frames(enter_interval)
        if enter_interval is not None
        else (
            _legacy_word_step_frames(frames, tokens)
            if unit == "words"
            else 8
        )
    )
    duration_f = (
        film_seconds_to_frames(enter_duration)
        if enter_duration is not None
        else _ENTER_DURATION_DEFAULT_FRAMES
    )
    hold_f = (
        film_seconds_to_frames(enter_hold_until)
        if enter_hold_until is not None
        else frames
    )
    last_start_f = start_f + max(0, tokens - 1) * step_f
    last_end_f = last_start_f + duration_f
    return tokens, start_f, step_f, duration_f, hold_f, last_start_f, last_end_f


def _words_timing_violations(
    scene: Any, *, frames: int, where: str
) -> list[FilmViolation]:
    """Validate a words scene's timing against ONE frame window. The caller
    passes the authoritative allocation (authored seconds at design time, the
    snapped/flexed frames at spec build) — an overflow is a concrete conflict,
    never a clamp, a shortened animation, or a dropped token."""
    if scene.type != "words":
        return []
    violations: list[FilmViolation] = []
    enter_values = {
        key: getattr(scene, key, None) for key in _ENTER_TIMING_FIELDS
    }
    motion_values = {
        key: getattr(scene, key, None) for key in _MOTION_TIMING_FIELDS
    }

    enter_mode = scene.enter or "lines"
    if any(value is not None for value in enter_values.values()):
        (
            tokens,
            start_f,
            step_f,
            duration_f,
            hold_f,
            last_start_f,
            last_end_f,
        ) = _enter_schedule_frames(
            scene.lines,
            frames=frames,
            enter_start=scene.enter_start,
            enter_interval=scene.enter_interval,
            enter_duration=scene.enter_duration,
            enter_hold_until=scene.enter_hold_until,
            unit=enter_mode,
        )
        unit_label = "tokens" if enter_mode == "words" else "lines"
        if tokens == 0:
            violations.append(
                FilmViolation(
                    CONSTRAINT_VIOLATION,
                    f"{where}: enter='{enter_mode}' found no {unit_label} to animate",
                )
            )
        elif hold_f > frames:
            violations.append(
                FilmViolation(
                    DURATION_INVALID,
                    f"{where}: enter_hold_until {scene.enter_hold_until:g}s "
                    f"lands at f{hold_f}, beyond the scene's {frames}f "
                    f"window — move it inside the scene or lengthen the scene",
                )
            )
        elif hold_f <= last_start_f:
            # The last unit must be visible for at least one frame — a hold
            # at or before its start would render copy that never exists.
            violations.append(
                FilmViolation(
                    DURATION_INVALID,
                    f"{where}: the hold ends at f{hold_f} "
                    f"({hold_f / FILM_FPS:.2f}s) but the last {unit_label[:-1]} starts "
                    f"at f{last_start_f} ({last_start_f / FILM_FPS:.2f}s) "
                    "— the hold must stay after every entrance start so "
                    "each one is visible at least one frame",
                )
            )
        elif last_end_f > hold_f:
            need_f = last_end_f
            violations.append(
                FilmViolation(
                    DURATION_INVALID,
                    f"{where}: enter timing needs {need_f}f "
                    f"({need_f / FILM_FPS:.2f}s) for {tokens} {unit_label} "
                    f"(start f{start_f} + interval f{step_f} + duration "
                    f"f{duration_f}), but the hold ends at f{hold_f} "
                    f"({hold_f / FILM_FPS:.2f}s) — lengthen the scene, "
                    "widen the hold, or shorten the interval / duration "
                    "(the user decides; never adjust the numbers "
                    "silently)",
                )
            )

    if any(value is not None for value in motion_values.values()):
        if scene.motion not in ("push", "pull"):
            violations.append(
                FilmViolation(
                    CONSTRAINT_VIOLATION,
                    f"{where}: motion timing needs motion='push' or 'pull' "
                    "(static has no motion window); set the move or clear "
                    "the timing fields",
                )
            )
        else:
            start_f = film_seconds_to_frames(
                scene.motion_start if scene.motion_start is not None else 0.0
            )
            end_f = (
                film_seconds_to_frames(scene.motion_end)
                if scene.motion_end is not None
                else frames
            )
            if end_f <= start_f:
                violations.append(
                    FilmViolation(
                        DURATION_INVALID,
                        f"{where}: motion window ends at f{end_f} but starts "
                        f"at f{start_f} — the end must stay after the start",
                    )
                )
            elif end_f > frames:
                violations.append(
                    FilmViolation(
                        DURATION_INVALID,
                        f"{where}: motion_end {scene.motion_end:g}s lands at "
                        f"f{end_f}, beyond the scene's {frames}f window — "
                        "move it inside the scene or lengthen the scene",
                    )
                )

    if scene.motion_scale is not None and scene.motion not in ("push", "pull"):
        violations.append(
            FilmViolation(
                CONSTRAINT_VIOLATION,
                f"{where}: motion_scale needs motion='push' or 'pull' "
                "(static has no move to scale); set the move or clear the "
                "scale",
            )
        )
    # The exit fade guards against the words' OWN schedule (the caller's
    # real parameters — defaults included), never a re-derived one.
    last_entered_f: int | None = None
    if scene.enter == "words" or any(
        value is not None for value in enter_values.values()
    ):
        sched = _enter_schedule_frames(
            scene.lines,
            frames=frames,
            enter_start=scene.enter_start,
            enter_interval=scene.enter_interval,
            enter_duration=scene.enter_duration,
            enter_hold_until=scene.enter_hold_until,
            unit=enter_mode,
        )
        if sched[0]:
            last_entered_f = sched[6]
    violations.extend(
        _exit_fade_violations(
            exit_duration=scene.exit_duration,
            window_f=frames,
            hold_until=scene.enter_hold_until,
            last_entered_f=last_entered_f,
            where=where,
        )
    )
    return violations


def _exit_fade_violations(
    *,
    exit_duration: float | None,
    window_f: int,
    hold_until: float | None,
    last_entered_f: int | None,
    where: str,
) -> list[FilmViolation]:
    """The exit fade's fit check (words scene AND composite text element —
    one law): the fade occupies the window's FINAL ``exit_duration`` seconds
    (ending at the hold endpoint when one is set, else the window's end);
    it must quantize to ≥1 frame, fit inside the window, and start only
    after the last word has fully entered (``last_entered_f`` — the
    caller's OWN schedule with its real parameters; None = a lines
    entrance, whose spring needs no such guard). The background never fades
    with the text; a window that can't hold the fade is a concrete
    conflict, never a silent shortening."""
    if exit_duration is None:
        return []
    exit_f = film_seconds_to_frames(exit_duration)
    if exit_f < 1:
        return [
            FilmViolation(
                DURATION_INVALID,
                f"{where}: exit_duration {exit_duration:g}s collapses to zero "
                "frames on the render grid — the fade needs at least one "
                "frame; widen it or drop it",
            )
        ]
    end_f = (
        film_seconds_to_frames(hold_until) if hold_until is not None else window_f
    )
    start_f = end_f - exit_f
    if start_f < 0:
        return [
            FilmViolation(
                DURATION_INVALID,
                f"{where}: the {exit_duration:g}s exit fade ({exit_f}f) is "
                f"longer than the text's window ending at f{end_f} — shorten "
                "the fade or lengthen the window",
            )
        ]
    if last_entered_f is not None and start_f < last_entered_f:
        return [
            FilmViolation(
                DURATION_INVALID,
                f"{where}: the exit fade starts at f{start_f} "
                f"({start_f / FILM_FPS:.2f}s) but the last word only "
                f"finishes entering at f{last_entered_f} "
                f"({last_entered_f / FILM_FPS:.2f}s) — shorten the fade or "
                "push it later",
            )
        ]
    return []


def _element_timing_violations(
    el: Any, *, frames: int, where: str
) -> list[FilmViolation]:
    """Validate a composite TEXT element's enter/motion timing against its
    OWN window (``until - at``, already frame-quantized by the caller —
    ADR-140). The words plane's law in miniature, with two deltas: there is
    no ``enter_hold_until`` (the hard leave at ``until`` IS the hold end) and
    the messages name the element's window, never the scene's."""
    violations: list[FilmViolation] = []
    enter_present = any(
        getattr(el, key, None) is not None
        for key in ("enter_start", "enter_interval", "enter_duration")
    )
    enter_mode = el.enter or "lines"
    if enter_present:
        (
            tokens,
            start_f,
            step_f,
            duration_f,
            hold_f,
            last_start_f,
            last_end_f,
        ) = _enter_schedule_frames(
            el.lines,
            frames=frames,
            enter_start=el.enter_start,
            enter_interval=el.enter_interval,
            enter_duration=el.enter_duration,
            enter_hold_until=None,
            unit=enter_mode,
        )
        unit_label = "tokens" if enter_mode == "words" else "lines"
        if tokens == 0:
            violations.append(
                FilmViolation(
                    CONSTRAINT_VIOLATION,
                    f"{where}: enter='{enter_mode}' found no {unit_label} to animate",
                )
            )
        elif hold_f <= last_start_f:
            violations.append(
                FilmViolation(
                    DURATION_INVALID,
                    f"{where}: the element's {frames}f window "
                    f"({frames / FILM_FPS:.2f}s) ends at or before the "
                    f"last {unit_label[:-1]}'s start f{last_start_f} "
                    f"({last_start_f / FILM_FPS:.2f}s) — every {unit_label[:-1]} must "
                    "be visible at least one frame before the element "
                    "leaves; widen the window or compress the cadence",
                )
            )
        elif last_end_f > hold_f:
            need_f = last_end_f
            violations.append(
                FilmViolation(
                    DURATION_INVALID,
                    f"{where}: enter timing needs {need_f}f "
                    f"({need_f / FILM_FPS:.2f}s) for {tokens} {unit_label} "
                    f"(start f{start_f} + interval f{step_f} + duration "
                    f"f{duration_f}), but the element leaves at f{hold_f} "
                    f"({hold_f / FILM_FPS:.2f}s) — widen the element's "
                    "window or shorten the interval / duration (the user "
                    "decides; never adjust the numbers silently)",
                )
            )

    if el.motion_start is not None or el.motion_end is not None:
        if el.motion not in ("push", "pull"):
            violations.append(
                FilmViolation(
                    CONSTRAINT_VIOLATION,
                    f"{where}: motion timing needs motion='push' or 'pull' "
                    "(static has no motion window); set the move or clear "
                    "the timing fields",
                )
            )
        else:
            start_f = film_seconds_to_frames(
                el.motion_start if el.motion_start is not None else 0.0
            )
            end_f = (
                film_seconds_to_frames(el.motion_end)
                if el.motion_end is not None
                else frames
            )
            if end_f <= start_f:
                violations.append(
                    FilmViolation(
                        DURATION_INVALID,
                        f"{where}: motion window ends at f{end_f} but starts "
                        f"at f{start_f} — the end must stay after the start",
                    )
                )
            elif end_f > frames:
                violations.append(
                    FilmViolation(
                        DURATION_INVALID,
                        f"{where}: motion_end {el.motion_end:g}s lands at "
                        f"f{end_f}, beyond the element's {frames}f window — "
                        "move it inside the window or lengthen the window",
                    )
                )

    if el.motion_scale is not None and el.motion not in ("push", "pull"):
        violations.append(
            FilmViolation(
                CONSTRAINT_VIOLATION,
                f"{where}: motion_scale needs motion='push' or 'pull' "
                "(static has no move to scale); set the move or clear the "
                "scale",
            )
        )
    last_entered_f: int | None = None
    if el.enter == "words" or enter_present:
        sched = _enter_schedule_frames(
            el.lines,
            frames=frames,
            enter_start=el.enter_start,
            enter_interval=el.enter_interval,
            enter_duration=el.enter_duration,
            enter_hold_until=None,
            unit=enter_mode,
        )
        if sched[0]:
            last_entered_f = sched[6]
    violations.extend(
        _exit_fade_violations(
            exit_duration=el.exit_duration,
            window_f=frames,
            hold_until=None,
            last_entered_f=last_entered_f,
            where=where,
        )
    )
    return violations


def _composite_violations(
    scene: Any, *, frames: int, media: "StoryboardMedia | None", where: str
) -> list[FilmViolation]:
    """A composite scene's structural + media checks (ADR-140). The element
    window law: every element must live INSIDE the scene's frame window — a
    play window running past the scene's end or an ``until`` landing beyond
    it is a concrete conflict (shorten the window or lengthen the scene),
    never a freeze-frame, a clamp, or a silent drop."""
    violations: list[FilmViolation] = []
    if len(scene.elements) > _LIST_CAPS["composite.elements"]:
        violations.append(
            FilmViolation(
                CONSTRAINT_VIOLATION,
                f"{where}: {len(scene.elements)} elements over "
                f"{_LIST_CAPS['composite.elements']}",
            )
        )
    seen_ids: set[str] = set()
    for el_index, el in enumerate(scene.elements):
        # Identity is birth-assigned (ensure_scene_ids) — a board not yet
        # through that seat carries None ids; only ASSIGNED ids can
        # duplicate. The display name falls back positionally.
        ewhere = f"{where}.{el.element_id or f'element{el_index + 1}'}"
        if el.element_id is not None:
            if el.element_id in seen_ids:
                violations.append(
                    FilmViolation(
                        CONSTRAINT_VIOLATION,
                        f"{ewhere}: duplicate element id within one scene",
                    )
                )
            seen_ids.add(el.element_id)
        at_f = film_seconds_to_frames(el.at)
        if el.kind == "video":
            # 源入出帧与输出播放帧同一量化契约 (复审①): the endpoints quantize
            # FIRST (the renderer's startFrom/endAt ride the same formula);
            # the default play window IS the quantized span — never
            # quantize-the-delta, which can claim a frame the trim never
            # shows; an explicit window may not exceed the quantized source
            # frames. No seat pads a frame.
            start_f = film_seconds_to_frames(el.source_start)
            end_f = film_seconds_to_frames(el.source_end)
            available_f = end_f - start_f
            if available_f < 1:
                violations.append(
                    FilmViolation(
                        DURATION_INVALID,
                        f"{ewhere}: source {el.source_start:g}–"
                        f"{el.source_end:g}s collapses to zero frames on "
                        "the render grid (both endpoints land on the same "
                        "frame) — the trim names no picture; widen the "
                        "source window past one frame",
                    )
                )
            play_f = (
                film_seconds_to_frames(el.duration)
                if el.duration is not None
                else available_f
            )
            if available_f >= 1:
                if play_f < 1:
                    # The same zero-frames law as the at/until window below:
                    # nothing may fabricate a frame — a sub-frame play window
                    # names no picture at all.
                    violations.append(
                        FilmViolation(
                            DURATION_INVALID,
                            f"{ewhere}: plays {el.duration:g}s — that "
                            "quantizes to zero frames on the render grid; "
                            "widen the play window past one frame",
                        )
                    )
                elif play_f > available_f:
                    violations.append(
                        FilmViolation(
                            DURATION_INVALID,
                            f"{ewhere}: the play window {el.duration:g}s = "
                            f"{play_f}f exceeds the {available_f}f the "
                            "quantized source trim holds — shorten the "
                            "window or widen the source range",
                        )
                    )
                leave_f = at_f + play_f
                if leave_f > frames:
                    violations.append(
                        FilmViolation(
                            DURATION_INVALID,
                            f"{ewhere}: plays {play_f / FILM_FPS:g}s from "
                            f"{el.at:g}s — the element would still be "
                            f"running at f{leave_f}, past the scene's "
                            f"{frames}f window; shorten the play window, "
                            "start it earlier, or lengthen the scene",
                        )
                    )
        else:
            # ``until`` null = the scene's end (the hard leave resolves
            # against THIS seat's authoritative window).
            until_f = (
                film_seconds_to_frames(el.until) if el.until is not None else frames
            )
            if el.until is not None and until_f > frames:
                violations.append(
                    FilmViolation(
                        DURATION_INVALID,
                        f"{ewhere}: until {el.until:g}s lands at f{until_f}, "
                        f"beyond the scene's {frames}f window — pull it "
                        "inside the scene or lengthen the scene",
                    )
                )
            window_f = until_f - at_f
            if window_f < 1:
                violations.append(
                    FilmViolation(
                        DURATION_INVALID,
                        f"{ewhere}: at/until collapse to zero frames on the "
                        "render grid — the element needs at least one frame",
                    )
                )
            elif el.kind == "text":
                if len(el.lines) > _LIST_CAPS["composite.text-lines"]:
                    violations.append(
                        FilmViolation(
                            CONSTRAINT_VIOLATION,
                            f"{ewhere}: {len(el.lines)} lines over "
                            f"{_LIST_CAPS['composite.text-lines']}",
                        )
                    )
                # The words plane's line-capacity law, element-scoped: a
                # line past its size tier's capacity would visually
                # wrap/clip inside the rect — never a silent trim. The rect
                # clips (overflow hidden), so a push/pull amplitude shrinks
                # the effective box.
                el_scale = (
                    (el.motion_scale if el.motion_scale is not None else 1.06)
                    if el.motion in ("push", "pull")
                    else None
                )
                el_line_cap = film_text_line_cap(
                    el.size, seat="element", rect_w=el.rect.w,
                    motion_scale=el_scale,
                )
                for line in el.lines:
                    if _display_units(line) > el_line_cap:
                        violations.append(
                            FilmViolation(
                                CONSTRAINT_VIOLATION,
                                f"{ewhere}: the line «{line[:30]}» runs "
                                f"{_display_units(line)} display units over "
                                f"the {el_line_cap} the "
                                f"{el.size or 'medium'} size tier fits on "
                                "one line inside the element's rect — "
                                "shorten the line or step the size down "
                                "(never a silent trim)",
                            )
                        )
                el_vertical = film_text_vertical_violation(
                    el.size,
                    seat="element",
                    lines=len(el.lines),
                    rect_h=el.rect.h,
                    motion_scale=el_scale,
                )
                if el_vertical is not None:
                    violations.append(
                        FilmViolation(
                            CONSTRAINT_VIOLATION,
                            f"{ewhere}: {el_vertical}",
                        )
                    )
                violations.extend(
                    _element_timing_violations(el, frames=window_f, where=ewhere)
                )
        if el.kind in ("video", "image") and media is not None:
            entry = media.assets.get(el.asset)
            if entry is None:
                violations.append(
                    FilmViolation(
                        CONSTRAINT_VIOLATION,
                        f"{ewhere}: asset {el.asset} is not one of this "
                        "project's media assets — cite the project's own "
                        "videos / images by id",
                    )
                )
            else:
                name = entry.title or el.asset
                if entry.kind != el.kind:
                    violations.append(
                        FilmViolation(
                            CONSTRAINT_VIOLATION,
                            f"{ewhere}: «{name}» is a {entry.kind} asset, "
                            f"not {el.kind} — an element's kind must match "
                            "its asset",
                        )
                    )
                if not entry.key:
                    violations.append(
                        FilmViolation(
                            CONSTRAINT_VIOLATION,
                            f"{ewhere}: «{name}» carries no media bytes",
                        )
                    )
                if (
                    el.kind == "video"
                    and entry.kind == "video"
                    and entry.duration_seconds is not None
                    and el.source_end > entry.duration_seconds + 1e-9
                ):
                    violations.append(
                        FilmViolation(
                            DURATION_INVALID,
                            f"{ewhere}: the source window ends at "
                            f"{el.source_end:g}s but «{name}» runs "
                            f"{entry.duration_seconds:g}s — keep the cut "
                            "inside the material",
                        )
                    )
    return violations


# The creative channel (ADR-127): these slots are the film's OWN framing —
# hooks and lead-ins, never product claims — so the grounding check exempts
# them (caps, non-blank and the duplicate guards still apply). Every other
# on-screen slot is a citation and grounds by construction.
_CREATIVE_SLOTS = {
    ("words", "lines"),
    ("reveal", "lead"),
    ("divider", "label"),
    # A composite text element's lines are the film's own framing beside the
    # media — the words plane's exemption applies (ADR-140).
    ("composite", "lines"),
}


def validate_storyboard(
    storyboard: FilmStoryboard,
    pages: list[StoryboardPage],
    *,
    narration_required: bool = False,
    text_lines: list[ManifestLine] | None = None,
    media: StoryboardMedia | None = None,
) -> list[FilmViolation]:
    """Every violation found, in scene order. Empty list = the storyboard may
    proceed to frame allocation. The union corpus grounds every scene.

    ``text_lines`` (ADR-138 §7.6 — 素材源抽象): present = a TEXT-source film —
    the grounding corpus is the copy itself, the count/seconds bands relax to
    the text profile, page-coupled scene types (ui/end) are illegal, and a
    words scene's only duration law is a POSITIVE window (the reading
    estimate recommends the pace, it never gates — 2026-10-22 拍板).
    Absent = the web source's law (unchanged).

    ``narration_required`` (2026-10-18 最后一公里 — the 4ad7963e silent-film
    incident): the plan PROMISED voiceover. Individual scenes may stay
    silent by craft (a divider beat, the fast cold open), but an ALL-silent
    board fails the promise — caught here at design time (the bounded
    rewrite repairs it) and again at the run's defensive re-validation,
    never delivered as a successful silent film.

    ``media`` (ADR-140): the composite scenes' cited assets, keyed by id.
    None = no media knowledge at this seat — asset identity checks defer to
    the seats that load it (patch / run); the structural element checks
    (windows, timing, ids) always run."""
    text_mode = text_lines is not None
    count_limits = TEXT_SCENE_COUNT_LIMITS if text_mode else SCENE_COUNT_LIMITS
    seconds_map = TEXT_SCENE_SECONDS if text_mode else SCENE_SECONDS
    total_range = TEXT_TOTAL_SECONDS_RANGE if text_mode else TOTAL_SECONDS_RANGE
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
    if text_lines:
        # Text source: the copy itself is the grounding universe.
        union_pairs += [(n, l.text) for l in text_lines if (n := _norm(l.text))]

    def grounded(text: str, corpus: list[str]) -> bool:
        norm = _norm(text)
        return bool(norm) and any(norm in item for item in corpus)

    scenes = storyboard.scenes
    if text_mode:
        # The 2..30 count band is a CRAFT DEFAULT for text films (prompt
        # guidance + the preflight's named-count satisfiable range), never
        # an unconditional rejection — the real bounds are the per-scene
        # reading floors and the frame-capped total below. A film still
        # needs at least one scene.
        if not scenes:
            violations.append(
                FilmViolation(CONSTRAINT_VIOLATION, "a film needs at least one scene")
            )
    elif not (count_limits[0] <= len(scenes) <= count_limits[1]):
        violations.append(
            FilmViolation(
                CONSTRAINT_VIOLATION,
                f"scene count {len(scenes)} outside {count_limits[0]}..{count_limits[1]}",
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
        if text_mode and scene.type in TEXT_ILLEGAL_SCENES:
            violations.append(
                FilmViolation(
                    UNSUPPORTED_SCENE,
                    f"{where}: a {scene.type} scene needs a captured page — a "
                    "text film has none; keep the arc on text planes (words)",
                )
            )
            continue

        lo, hi = seconds_map[scene.type]
        # Text-mode words planes: the per-scene band is a craft DEFAULT, not
        # hard law — the plane's duration law is its reading-time floor (the
        # mirror below) plus the film-level bands. Every other scene type
        # (and the whole web source) keeps its band.
        if not (text_mode and scene.type == "words") and not (lo <= scene.seconds <= hi):
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
            # A composite's screen is its text AND its media identity —
            # two composites sharing captions over DIFFERENT assets are
            # different screens (ADR-140).
            else (
                "composite",
                tuple(sorted(normed)),
                tuple((el.kind, getattr(el, "asset", None)) for el in scene.elements),
            )
            if scene.type == "composite"
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
        # count; the views are the world's). Web-source law only — a text
        # film has no page walks by construction.
        if scene.type == "divider" and not text_mode:
            chapter_ordinal += 1
            has_walk = False
            for later in scenes[idx + 1:]:
                if later.type in ("divider", "reveal", "end"):
                    break
                # A composite scene is a chapter's substance too (ADR-140)
                # — its media walk carries the chapter like a page walk.
                if later.type in ("ui", "composite"):
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
        if scene.type == "words":
            # A display line must fit its size tier's line capacity — a
            # line past it would visually wrap/clip (the assembly wraps to
            # the cap; a patch-authored line re-checks here). Never a
            # silent trim. (Text-mode law: the web chain's words planes
            # predate the capacity seat and stay on their own law.)
            if text_mode:
                line_cap = film_text_line_cap(scene.size, seat="words")
                for line in scene.lines:
                    if _display_units(line) > line_cap:
                        violations.append(
                            FilmViolation(
                                CONSTRAINT_VIOLATION,
                                f"{where}: the line «{line[:30]}» runs "
                                f"{_display_units(line)} display units over the "
                                f"{line_cap} the {scene.size or 'medium'} size "
                                "tier fits on one line — shorten the line or "
                                "step the size down (never a silent trim)",
                            )
                        )
                vertical = film_text_vertical_violation(
                    scene.size,
                    seat="words",
                    lines=len(scene.lines),
                    motion_scale=(
                        (scene.motion_scale if scene.motion_scale is not None else 1.06)
                        if scene.motion in ("push", "pull")
                        else None
                    ),
                )
                if vertical is not None:
                    violations.append(
                        FilmViolation(CONSTRAINT_VIOLATION, f"{where}: {vertical}")
                    )
        if scene.type == "words":
            # Design-time timing leg: the authored scene window (the spec
            # builder re-checks the snapped/flexed allocation below).
            violations.extend(
                _words_timing_violations(
                    scene,
                    frames=film_seconds_to_frames(scene.seconds),
                    where=where,
                )
            )
        if scene.type == "composite":
            violations.extend(
                _composite_violations(
                    scene,
                    frames=film_seconds_to_frames(scene.seconds),
                    media=media,
                    where=where,
                )
            )
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

    if text_mode:
        # Only the total's UPPER is hard law for a text film: 120s = the
        # render frame cap (FILM_MAX_FRAMES / FILM_FPS, mirrored from the
        # post-allocation guard). The 5s lower is a craft suggestion (the
        # allocator's no-target top-up seat), never a rejection — a short
        # film stands when every scene is readable.
        if total_seconds > total_range[1]:
            violations.append(
                FilmViolation(
                    DURATION_INVALID,
                    f"total {total_seconds:.1f}s over the {total_range[1]:g}s "
                    "render frame cap",
                )
            )
    elif not (total_range[0] <= total_seconds <= total_range[1]):
        violations.append(
            FilmViolation(
                DURATION_INVALID,
                f"total {total_seconds:.1f}s outside {total_range[0]}..{total_range[1]}s",
            )
        )

    if text_mode:
        # The reading-time estimate NEVER gates (2026-10-22 拍板 — 估计 =
        # 建议非边界): a scene faster than the estimated reading pace is the
        # user's explicit faster choice (a named total the allocator scaled
        # down to, or an explicit seconds patch) — the readability impact
        # rides the presentation's pace note, never a rejection. The REAL
        # duration checks that remain: a positive window on the render's
        # time grid (a zero/negative scene renders nothing — illegal data)
        # and the frame-capped total above.
        for idx, scene in enumerate(scenes):
            if scene.type == "words" and scene.seconds <= 0:
                violations.append(
                    FilmViolation(
                        DURATION_INVALID,
                        f"scene[{idx}](words): {scene.seconds:g}s renders "
                        "nothing — a scene needs a positive window",
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


def execution_frames(
    storyboard: FilmStoryboard,
    beats: list[float] | None,
) -> list[int]:
    """The run/presentation timeline's ONE frame-allocation seat
    (allocate → beat snap): the spec's per-scene frames and the fact sheet's
    times both come from here, never re-derived per consumer. The keep_cut
    fork does NOT ride this seat — a kept cut is the BASE version's own
    executed/presented timeline (see the run's ``film_kept_frames``
    consumption), never a freshly snapped re-allocation."""
    frames = allocate_frames(storyboard)
    if beats:
        frames = snap_frames_to_beats(storyboard, frames, beats)
    return frames


def spec_scene_frames(spec: Any) -> list[int] | None:
    """A film render spec's per-scene executed frames (the cut AS RENDERED —
    snap + any narration flex baked in). None = no readable timeline (a
    corrupt/half-written spec reads as absent, never a partial cut)."""
    scenes = spec.get("scenes") if isinstance(spec, dict) else None
    if not isinstance(scenes, list) or not scenes:
        return None
    out: list[int] = []
    for scene in scenes:
        n = scene.get("frames") if isinstance(scene, dict) else None
        if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
            return None
        out.append(n)
    return out


def spec_scene_reveal_onsets(spec: Any) -> list[int | None] | None:
    """A film render spec's per-scene reveal word onsets AS RENDERED
    (``lead_frames``; None per non-reveal scene) — the in-scene cut points
    of the executed timeline, the frozen timeline's other half (a kept cut
    preserves the word's landing beat, not just the scene lengths). None =
    no readable timeline (a corrupt/half-written/pre-split spec reads as
    absent, never a partial cut)."""
    scenes = spec.get("scenes") if isinstance(spec, dict) else None
    if not isinstance(scenes, list) or not scenes:
        return None
    out: list[int | None] = []
    for scene in scenes:
        n = scene.get("frames") if isinstance(scene, dict) else None
        if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
            return None
        if scene.get("type") == "reveal":
            onset = scene.get("lead_frames")
            if not isinstance(onset, int) or isinstance(onset, bool) or onset <= 0:
                return None
            out.append(onset)
        else:
            out.append(None)
    return out


def valid_kept_cut(storyboard: FilmStoryboard, frames: Any) -> bool:
    """The kept-cut handoff's fail-closed check (keep_cut 执行语义): one
    positive int per scene, every scene at/above its structural floor, the
    total under the render cap. A kept cut that fails any leg is corrupt —
    the run refuses it, never silently re-snaps."""
    if not isinstance(frames, list) or len(frames) != len(storyboard.scenes):
        return False
    for scene, n in zip(storyboard.scenes, frames):
        if not isinstance(n, int) or isinstance(n, bool) or n < _scene_floor(scene):
            return False
    return sum(frames) <= FILM_MAX_FRAMES


def valid_kept_reveal_onsets(
    storyboard: FilmStoryboard, onsets: Any, frames: list[int]
) -> bool:
    """The frozen reveal onsets' fail-closed check (冻结场内切点 = 冻结时间
    轴的同一半 — keep_cut keeps the word's landing beat too): one entry per
    scene, every REVEAL scene's onset a positive int leaving ≥1s of word
    phase inside its kept scene frames. A frozen cut whose onsets fail any
    leg is corrupt — the run/patch refuses it, never silently re-snapping
    an in-scene cut point onto the new bed's grid."""
    if not isinstance(onsets, list) or len(onsets) != len(storyboard.scenes):
        return False
    for scene, onset, n in zip(storyboard.scenes, onsets, frames, strict=True):
        if scene.type != "reveal":
            continue
        if not isinstance(onset, int) or isinstance(onset, bool):
            return False
        if onset < FILM_FPS or onset > n - FILM_FPS:
            return False
    return True


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


def reveal_onset_frames(
    scene: FilmScene,
    *,
    cursor_frames: int,
    scene_frames: int,
    beat_s: float | None,
    beats: list[float] | None,
) -> int:
    """The reveal scene's word onset within its scene (lead → beat pause →
    word — the ONE onset seat): the lead holds its lead_seconds, then the
    word lands ON the music grid — the next beat at/after the lead's end,
    plus one real beat of black pause. No grid = the silent-cut fallback
    (a music-less film has no beat to land on — the half-second hold is a
    plain pause, never passed off as a beat). The word phase always keeps
    ≥1s. The spec builder and the draft-freeze seat share this formula, so
    a presented plan timeline and its rendered spec never disagree on
    in-scene cut points."""
    word_f = round(scene.lead_seconds * FILM_FPS) + FILM_FPS // 2
    if beat_s:
        lead_end_abs = cursor_frames / FILM_FPS + scene.lead_seconds
        nxt = (
            min((b for b in beats if b >= lead_end_abs - 1e-9), default=None)
            if isinstance(beats, list)
            else None
        )
        word_abs = (
            nxt + beat_s
            if nxt is not None
            else math.ceil(lead_end_abs / beat_s - 1e-9) * beat_s + beat_s
        )
        word_f = round((word_abs - cursor_frames / FILM_FPS) * FILM_FPS)
    return max(FILM_FPS, min(word_f, scene_frames - FILM_FPS))


def draft_reveal_onsets(
    storyboard: FilmStoryboard,
    frames: list[int],
    music: dict | None,
) -> list[int | None] | None:
    """A plan timeline's per-scene reveal word onsets (None per non-reveal
    scene), computed by the ONE onset seat on the given music grid — a
    draft's PRESENTED in-scene cut points, frozen alongside
    ``film_kept_frames`` when a keep_cut freezes the presented timeline.
    None = the board carries no reveal scene."""
    if not any(s.type == "reveal" for s in storyboard.scenes):
        return None
    beat_s = _beat_interval((music or {}).get("beats"), (music or {}).get("bpm"))
    beats = (music or {}).get("beats")
    out: list[int | None] = []
    cursor = 0
    for scene, n in zip(storyboard.scenes, frames, strict=True):
        if scene.type == "reveal":
            out.append(
                reveal_onset_frames(
                    scene,
                    cursor_frames=cursor,
                    scene_frames=n,
                    beat_s=beat_s,
                    beats=beats,
                )
            )
        else:
            out.append(None)
        cursor += n
    return out


def build_film_spec(
    storyboard: FilmStoryboard,
    pages: list[StoryboardPage],
    *,
    narration: dict[int, tuple[str, float]] | None = None,
    music: dict[str, Any] | None = None,
    aspect: str = "16:9",
    frames: list[int] | None = None,
    reveal_onsets: list[int | None] | None = None,
    storyboard_digest: str | None = None,
    execution_digest: str | None = None,
    media: StoryboardMedia | None = None,
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
    ``reveal_onsets`` = the frozen cut's in-scene word onsets (the kept-cut
    handoff's other half — a kept cut preserves the reveal's landing beat,
    never re-snapping it onto the (possibly new) bed's grid); None = the
    onset seat computes from the current grid (compose / recut / draft
    seats).
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
        if storyboard.theme.accent is not None:
            theme["accent"] = storyboard.theme.accent
    beat_s = _beat_interval(
        (music or {}).get("beats"), (music or {}).get("bpm")
    )
    divider_ordinal = 0
    cursor = 0  # absolute frames — the reveal's word onset snaps to the grid
    scenes: list[dict[str, Any]] = []
    for idx, (scene, n) in enumerate(zip(storyboard.scenes, allocated, strict=True)):
        if scene.type == "words":
            timing_violations = _words_timing_violations(
                scene, frames=n, where=f"scene[{idx}](words)"
            )
            if timing_violations:
                raise FilmStoryboardRejected(
                    [v.code for v in timing_violations],
                    format_violations(timing_violations),
                )
            scenes.append(
                {
                    "type": "words",
                    "frames": n,
                    "dark": scene.dark,
                    "lines": scene.lines,
                    # Text-plane vocabulary/timing rides only when SET — null
                    # keys stay out of the spec (the digest law's spec-side
                    # twin; explicit zero is a value, never an omission).
                    **({"motion": scene.motion} if scene.motion else {}),
                    **({"enter": scene.enter} if scene.enter else {}),
                    **(
                        {"enter_start": scene.enter_start}
                        if scene.enter_start is not None
                        else {}
                    ),
                    **(
                        {"enter_interval": scene.enter_interval}
                        if scene.enter_interval is not None
                        else {}
                    ),
                    **(
                        {"enter_duration": scene.enter_duration}
                        if scene.enter_duration is not None
                        else {}
                    ),
                    **(
                        {"enter_hold_until": scene.enter_hold_until}
                        if scene.enter_hold_until is not None
                        else {}
                    ),
                    **(
                        {"motion_start": scene.motion_start}
                        if scene.motion_start is not None
                        else {}
                    ),
                    **(
                        {"motion_end": scene.motion_end}
                        if scene.motion_end is not None
                        else {}
                    ),
                    **(
                        {"exit_duration": scene.exit_duration}
                        if scene.exit_duration is not None
                        else {}
                    ),
                    **(
                        {"motion_scale": scene.motion_scale}
                        if scene.motion_scale is not None
                        else {}
                    ),
                    **({"align": scene.align} if scene.align else {}),
                    **({"size": scene.size} if scene.size else {}),
                    **(
                        {"accent_style": scene.accent_style}
                        if scene.accent_style
                        else {}
                    ),
                    **(
                        {"enter_style": scene.enter_style}
                        if scene.enter_style
                        else {}
                    ),
                }
            )
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
            # lead → beat pause → word (the reference arc): the onset comes
            # from the ONE onset seat on the current grid — or from the
            # FROZEN cut (``reveal_onsets``): a kept cut preserves the
            # word's landing beat exactly (冻结场内切点 — the (possibly new)
            # bed's grid is never re-snapped onto a cut the user approved
            # as kept); the clamp only guards a corrupt envelope.
            frozen_onset = reveal_onsets[idx] if reveal_onsets is not None else None
            if frozen_onset is not None:
                word_f = max(FILM_FPS, min(int(frozen_onset), n - FILM_FPS))
            else:
                word_f = reveal_onset_frames(
                    scene,
                    cursor_frames=cursor,
                    scene_frames=n,
                    beat_s=beat_s,
                    beats=(music or {}).get("beats"),
                )
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
        elif scene.type == "composite":
            # ADR-140: element windows re-check against the SNAPPED/FLEXED
            # allocation (the authored-seconds seat is validate_storyboard;
            # this is the spec-build mirror — an overflow is a concrete
            # conflict, never a clamp). Media elements resolve asset id →
            # storage key HERE (the spec carries keys like ui.image does;
            # absolutized at render time by the same seam). An unresolvable
            # id fails honestly, never a silent drop.
            comp_violations = _composite_violations(
                scene, frames=n, media=media, where=f"scene[{idx}](composite)"
            )
            if comp_violations:
                raise FilmStoryboardRejected(
                    [v.code for v in comp_violations],
                    format_violations(comp_violations),
                )
            elements: list[dict[str, Any]] = []
            for el in scene.elements:
                if el.kind == "text":
                    elements.append(
                        {
                            "kind": "text",
                            "id": el.element_id,
                            "lines": el.lines,
                            "tone": el.tone,
                            "at": el.at,
                            # ``until`` null = scene end — null stays out of
                            # the spec (the renderer resolves the scene's
                            # own frames), the words plane's convention.
                            **({"until": el.until} if el.until is not None else {}),
                            "rect": el.rect.model_dump(mode="json"),
                            "z": el.z,
                            # Null timing/vocabulary keys stay out of the
                            # spec — the words plane's convention verbatim.
                            **({"enter": el.enter} if el.enter else {}),
                            **({"motion": el.motion} if el.motion else {}),
                            **(
                                {"enter_start": el.enter_start}
                                if el.enter_start is not None
                                else {}
                            ),
                            **(
                                {"enter_interval": el.enter_interval}
                                if el.enter_interval is not None
                                else {}
                            ),
                            **(
                                {"enter_duration": el.enter_duration}
                                if el.enter_duration is not None
                                else {}
                            ),
                            **(
                                {"motion_start": el.motion_start}
                                if el.motion_start is not None
                                else {}
                            ),
                            **(
                                {"motion_end": el.motion_end}
                                if el.motion_end is not None
                                else {}
                            ),
                            **(
                                {"exit_duration": el.exit_duration}
                                if el.exit_duration is not None
                                else {}
                            ),
                            **(
                                {"motion_scale": el.motion_scale}
                                if el.motion_scale is not None
                                else {}
                            ),
                            **({"align": el.align} if el.align else {}),
                            **({"size": el.size} if el.size else {}),
                            **(
                                {"accent_style": el.accent_style}
                                if el.accent_style
                                else {}
                            ),
                            **(
                                {"enter_style": el.enter_style}
                                if el.enter_style
                                else {}
                            ),
                        }
                    )
                    continue
                entry = media.assets.get(el.asset) if media is not None else None
                if entry is None or not entry.key:
                    raise FilmStoryboardRejected(
                        [CONSTRAINT_VIOLATION],
                        f"scene[{idx}](composite).{el.element_id}: asset "
                        f"{el.asset} has no resolvable media key — the "
                        "composition can only cite the project's own media",
                    )
                emitted = {
                    "kind": el.kind,
                    "id": el.element_id,
                    "src": entry.key,
                    "at": el.at,
                    "rect": el.rect.model_dump(mode="json"),
                    "fit": el.fit,
                    "z": el.z,
                }
                if el.kind == "video":
                    emitted.update(
                        {
                            "source_start": el.source_start,
                            "source_end": el.source_end,
                            "keep_audio": el.keep_audio,
                            **(
                                {"duration": el.duration}
                                if el.duration is not None
                                else {}
                            ),
                        }
                    )
                else:
                    if el.until is not None:
                        emitted["until"] = el.until
                elements.append(emitted)
            scenes.append(
                {
                    "type": "composite",
                    "frames": n,
                    "dark": scene.dark,
                    "elements": elements,
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


def ui_focus_moves(
    scene: FilmSceneUi, pages: list[StoryboardPage], *, with_ids: bool = False
) -> list[str]:
    """A ui scene's camera moves with each element-named focus resolved to
    its captured text — never a raw DOM id (ADR-121 B2). ONE resolution
    seat: the design beat's fact sheet (``with_ids=False`` — user-bound
    text never carries internal ids) and the chat read's取景文本
    (``with_ids=True`` — the read is model-facing internal fact: the id an
    ``update_scene`` focus must name rides along; an element that no longer
    resolves against the current inventory is NAMED as drift, never
    silently demoted to a center push)."""
    moves: list[str] = []
    for f in scene.focuses:
        target = None
        if f.element is not None and 0 <= scene.page < len(pages):
            pg = pages[scene.page]
            elts = (
                pg.shots[scene.shot].elements
                if pg.shots and scene.shot < len(pg.shots)
                else []
            )
            el = next((e for e in elts if e.id == f.element), None)
            if el is not None:
                target = f'"{el.text}" ({el.kind})' if el.text else el.kind
        if target is not None:
            moves.append(
                f"push to {target} [{f.element}] at {f.at:g}s"
                if with_ids
                else f"push to {target} at {f.at:g}s"
            )
        elif with_ids and f.element is not None:
            moves.append(
                f"push to [{f.element}] (not in the view's current "
                f"inventory) at {f.at:g}s"
            )
        else:
            moves.append(f"center push at {f.at:g}s")
    return moves


def words_timing_clause(scene: "FilmScene", frame_count: int | None = None) -> str:
    """The words plane's effective timing as ONE fact clause (design
    presentation + read-back + patch summary all ride it). Every set value
    shows the REQUESTED seconds, the quantized frame, AND the frame's
    realized seconds — quantization moves a decimal (0.12s→f4 renders
    0.133s) and the presentation never hides that; omitted pieces name
    their deterministic default instead of disappearing into an implicit
    renderer formula. The enter clause ends with the computed last-unit
    schedule (start / fully-in frames + seconds): the interval's per-step
    quantization delta ACCUMULATES down a long token/line run, so the honest
    disclosure is the computed landing, never a claimed sequence-wide
    sub-frame bound."""
    if scene.type != "words":
        return ""
    frames = (
        frame_count
        if frame_count is not None
        else film_seconds_to_frames(scene.seconds)
    )

    def _realized(f: int) -> str:
        return f"{f / FILM_FPS:.3f}s"

    clauses: list[str] = []
    if any(
        getattr(scene, key, None) is not None
        for key in _ENTER_TIMING_FIELDS
    ):
        (
            tokens,
            start_f,
            step_f,
            duration_f,
            _hold_f,
            last_start_f,
            last_end_f,
        ) = _enter_schedule_frames(
            scene.lines,
            frames=frames,
            enter_start=scene.enter_start,
            enter_interval=scene.enter_interval,
            enter_duration=scene.enter_duration,
            enter_hold_until=scene.enter_hold_until,
            unit=scene.enter or "lines",
        )

        def _seconds_and_frames(label: str, value: float | None, fallback_f: int) -> str:
            if value is None:
                return f"{label} default f{fallback_f} ({_realized(fallback_f)})"
            f = film_seconds_to_frames(value)
            return f"{label} {value:g}s→f{f} ({_realized(f)})"

        hold = (
            f"hold until {scene.enter_hold_until:g}s→f{film_seconds_to_frames(scene.enter_hold_until)}"
            f" ({_realized(film_seconds_to_frames(scene.enter_hold_until))})"
            if scene.enter_hold_until is not None
            else f"hold to scene end (f{frames})"
        )
        unit_label = "tokens" if scene.enter == "words" else "lines"
        clauses.append(
            "enter timing: "
            + " · ".join(
                [
                    _seconds_and_frames("start", scene.enter_start, start_f),
                    _seconds_and_frames("interval", scene.enter_interval, step_f),
                    _seconds_and_frames("duration", scene.enter_duration, duration_f),
                    hold,
                ]
            )
            + f" · {tokens} {unit_label}, last starts f{last_start_f} "
            f"({_realized(last_start_f)}), fully in f{last_end_f} "
            f"({_realized(last_end_f)})"
        )
    if any(
        getattr(scene, key, None) is not None
        for key in _MOTION_TIMING_FIELDS
    ):
        start = (
            f"{scene.motion_start:g}s→f{film_seconds_to_frames(scene.motion_start)}"
            f" ({_realized(film_seconds_to_frames(scene.motion_start))})"
            if scene.motion_start is not None
            else "scene start f0"
        )
        end = (
            f"{scene.motion_end:g}s→f{film_seconds_to_frames(scene.motion_end)}"
            f" ({_realized(film_seconds_to_frames(scene.motion_end))})"
            if scene.motion_end is not None
            else f"scene end f{frames}"
        )
        clauses.append(f"motion window: {start}–{end}")
    if scene.exit_duration is not None:
        exit_f = film_seconds_to_frames(scene.exit_duration)
        end_f = (
            film_seconds_to_frames(scene.enter_hold_until)
            if scene.enter_hold_until is not None
            else frames
        )
        start_f = end_f - exit_f
        clauses.append(
            f"exit fade: {scene.exit_duration:g}s→f{exit_f} "
            f"({_realized(exit_f)}), f{start_f}–f{end_f} — the words fade "
            "out, the background stays"
        )
    if scene.motion_scale is not None:
        clauses.append(f"motion scale ×{scene.motion_scale:g}")
    return " · ".join(clauses)


def _text_style_clause(obj: Any) -> str:
    """The text plane's style facts (centering / size tier / accent
    rendering / entrance effect) — ONE clause shared by the fact sheet, the
    chat read and the patch summary; the defaults (left / medium / chip /
    rise) stay silent."""
    bits: list[str] = []
    if getattr(obj, "align", None) == "center":
        bits.append("centered")
    if getattr(obj, "size", None) not in (None, "medium"):
        bits.append(f"size {obj.size}")
    if getattr(obj, "accent_style", None) == "color":
        bits.append("emphasis in the accent color")
    if getattr(obj, "enter_style", None) == "fade":
        bits.append("fade-only entrance (no rise, no blur)")
    if getattr(obj, "enter_style", None) == "slide":
        bits.append("slide-only entrance (no fade, no blur)")
    return " · ".join(bits)


def _rect_clause(rect: Any) -> str:
    """An element rect as a compact fact clause — the default full canvas
    says nothing (the common case stays silent)."""
    if rect is None:
        return ""
    if (
        abs(rect.x) < 1e-9
        and abs(rect.y) < 1e-9
        and abs(rect.w - 1.0) < 1e-9
        and abs(rect.h - 1.0) < 1e-9
    ):
        return ""
    return f" at ({rect.x:g},{rect.y:g}) {rect.w:g}×{rect.h:g}"


def element_timing_clause(el: "FilmElementText", frames: int) -> str:
    """A composite text element's effective timing as ONE fact clause
    (ADR-140) — the words plane's clause in miniature: every set value
    shows requested seconds, quantized frame, and realized time; the
    window's hard leave (``until``, null = scene end — the caller resolves
    it against the SCENE's ``frames``) IS the hold end."""
    until_f = film_seconds_to_frames(el.until) if el.until is not None else frames
    window_f = until_f - film_seconds_to_frames(el.at)

    def _realized(f: int) -> str:
        return f"{f / FILM_FPS:.3f}s"

    clauses: list[str] = []
    if any(
        getattr(el, key, None) is not None
        for key in ("enter_start", "enter_interval", "enter_duration")
    ):
        (
            tokens,
            start_f,
            step_f,
            duration_f,
            _hold_f,
            last_start_f,
            last_end_f,
        ) = _enter_schedule_frames(
            el.lines,
            frames=window_f,
            enter_start=el.enter_start,
            enter_interval=el.enter_interval,
            enter_duration=el.enter_duration,
            enter_hold_until=None,
            unit=el.enter or "lines",
        )

        unit_label = "tokens" if el.enter == "words" else "lines"

        def _seconds_and_frames(label: str, value: float | None, fallback_f: int) -> str:
            if value is None:
                return f"{label} default f{fallback_f} ({_realized(fallback_f)})"
            f = film_seconds_to_frames(value)
            return f"{label} {value:g}s→f{f} ({_realized(f)})"

        clauses.append(
            "enter timing: "
            + " · ".join(
                [
                    _seconds_and_frames("start", el.enter_start, start_f),
                    _seconds_and_frames("interval", el.enter_interval, step_f),
                    _seconds_and_frames("duration", el.enter_duration, duration_f),
                    f"holds until the element leaves (f{window_f})",
                ]
            )
            + f" · {tokens} {unit_label}, last starts f{last_start_f} "
            f"({_realized(last_start_f)}), fully in f{last_end_f} "
            f"({_realized(last_end_f)})"
        )
    if el.motion_start is not None or el.motion_end is not None:
        start = (
            f"{el.motion_start:g}s→f{film_seconds_to_frames(el.motion_start)}"
            f" ({_realized(film_seconds_to_frames(el.motion_start))})"
            if el.motion_start is not None
            else "element start f0"
        )
        end = (
            f"{el.motion_end:g}s→f{film_seconds_to_frames(el.motion_end)}"
            f" ({_realized(film_seconds_to_frames(el.motion_end))})"
            if el.motion_end is not None
            else f"element end f{window_f}"
        )
        clauses.append(f"motion window: {start}–{end}")
    if el.exit_duration is not None:
        exit_f = film_seconds_to_frames(el.exit_duration)
        clauses.append(
            f"exit fade: {el.exit_duration:g}s→f{exit_f} "
            f"({_realized(exit_f)}), f{window_f - exit_f}–f{window_f} — the "
            "words fade out, the background stays"
        )
    if el.motion_scale is not None:
        clauses.append(f"motion scale ×{el.motion_scale:g}")
    return " · ".join(clauses)


def film_scene_content(
    scene: "FilmScene",
    frame_count: int | None = None,
    media: "StoryboardMedia | None" = None,
) -> str:
    """A scene's display copy, verbatim, one compact clause — the chat
    read's content seat (the model editing 「结尾那句」 must SEE the current
    words; material screenshots never carry the film's overlay text).
    Field coverage mirrors the design beat's fact sheet
    (``storyboard_presentation``): a scene model's new copy field belongs
    in BOTH. Narration rides its own clause, never merged here; nothing is
    summarized, reworded, or guessed. ui scenes carry no copy (their
    content is the view/focuses)."""
    if scene.type == "words":
        vocab = []
        if scene.motion and scene.motion != "static":
            vocab.append(scene.motion)
        if scene.enter == "words":
            vocab.append("word-by-word")
        timing = words_timing_clause(scene, frame_count)
        if timing:
            vocab.append(timing)
        style = _text_style_clause(scene)
        if style:
            vocab.append(style)
        return " / ".join(f'"{line}"' for line in scene.lines) + (
            " (dark)" if scene.dark else ""
        ) + (f" · {' · '.join(vocab)}" if vocab else "")
    if scene.type == "hero":
        return f'word: "{scene.word}" · sub: "{scene.sub}"'
    if scene.type == "divider":
        return f'label: "{scene.label}" · roll: {" / ".join(scene.roll)}'
    if scene.type == "plate":
        cards = " · ".join(
            f'"{c.big}" — "{c.label}"' if c.big else f'"{c.label}"'
            for c in scene.cards
        )
        return f'title: "{scene.title}" · cards: {cards}'
    if scene.type == "reveal":
        return f'lead: "{scene.lead}" · then: "{scene.word}" — "{scene.sub}"'
    if scene.type == "end":
        return f'name: "{scene.name}" · tagline: "{scene.tagline}"'
    if scene.type == "composite":
        # ADR-140: every element's facts, verbatim — media elements name
        # their asset's title when the media universe is at hand (never
        # guessed), text elements show their copy and timing.
        frames = (
            frame_count
            if frame_count is not None
            else film_seconds_to_frames(scene.seconds)
        )
        parts: list[str] = []
        for el in scene.elements:
            pos = _rect_clause(el.rect)
            name = ""
            asset_facts = ""
            if el.kind in ("video", "image"):
                # The media universe names the asset's title when known; a
                # cited id ABSENT from it is named as missing (drift), never
                # left blank to be guessed around.
                if media is not None:
                    entry = media.assets.get(el.asset)
                    if entry is not None and entry.title:
                        name = f' "{entry.title}"'
                    elif entry is None:
                        name = " (asset not in project media)"
                    if entry is not None and el.kind == "video":
                        # The material's own length — the fact a
                        # source-window decision reads from (known, or
                        # honestly unknown; never guessed).
                        asset_facts = (
                            f" ({entry.duration_seconds:g}s asset)"
                            if entry.duration_seconds is not None
                            else " (asset duration unknown)"
                        )
            extras: list[str] = []
            if el.kind in ("video", "image") and el.fit != "cover":
                extras.append(el.fit)
            if el.z:
                extras.append(f"z{el.z}")
            tail = f" · {' · '.join(extras)}" if extras else ""
            if el.kind == "video":
                play = (
                    el.duration
                    if el.duration is not None
                    else el.source_end - el.source_start
                )
                audio = " · keeps its sound" if el.keep_audio else ""
                parts.append(
                    f"video [{el.element_id}]{name}{asset_facts} source "
                    f"{el.source_start:g}–{el.source_end:g}s → plays {play:g}s "
                    f"from {el.at:g}s{audio}{tail}{pos}"
                )
            elif el.kind == "image":
                leave = f"{el.until:g}s" if el.until is not None else "the scene's end"
                parts.append(
                    f"image [{el.element_id}]{name} on screen "
                    f"{el.at:g}s–{leave}{tail}{pos}"
                )
            else:
                leave = f"{el.until:g}s" if el.until is not None else "the scene's end"
                vocab = []
                if el.motion and el.motion != "static":
                    vocab.append(el.motion)
                if el.enter == "words":
                    vocab.append("word-by-word")
                timing = element_timing_clause(el, frames)
                if timing:
                    vocab.append(timing)
                style = _text_style_clause(el)
                if style:
                    vocab.append(style)
                parts.append(
                    f"text [{el.element_id}] "
                    + " / ".join(f'"{line}"' for line in el.lines)
                    + f" · on screen {el.at:g}s–{leave} ({el.tone}){tail}{pos}"
                    + (f" · {' · '.join(vocab)}" if vocab else "")
                )
        return " · ".join(parts) + (" · dark" if scene.dark else "")
    return ""  # ui: no overlay copy


def storyboard_presentation(
    storyboard: FilmStoryboard,
    pages: list[StoryboardPage],
    *,
    aspect: str = "16:9",
    music: str | None = None,
    beats: list[float] | None = None,
    bpm: float | None = None,
    captions: bool = False,
    source_note: str | None = None,
    media: StoryboardMedia | None = None,
    frame_override: list[int] | None = None,
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

    ``frame_override`` is the saved version's frozen per-scene cut when a
    patch inherited one; without it, the usual execution timeline is
    projected from the resolved bed grid. This keeps a revision's displayed
    windows identical to the version Start will consume.

    Completeness law (对内必须足够准确, 对外可以简洁): the name and the
    ACTUAL narration language, aspect/fps, the execution timeline's total
    seconds + frames, the bed label + BPM, per-scene order / type / arc
    role / start–end / duration / frames, what the viewer sees, the camera
    walk (focus elements resolved to their captured text — never a raw DOM
    id), the VERBATIM narration per scene (a silent scene says so — the
    model never guesses), and the compact source list (host+path+title —
    traceable without line-id spam)."""
    frames = (
        list(frame_override)
        if frame_override is not None
        else execution_frames(storyboard, beats)
    )
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
    # 配音开关恒显 (默认无配音): the presenting model must always be able to
    # SAY the real voiceover state — a silent default that never appears on
    # the fact sheet reads as an omission the model then improvises around.
    head_bits.append(f"voiceover: {'on' if captions else 'off'}")
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
            roles.append("cold open" if pages else "text plane")
        elif s.type == "hero":
            roles.append("brand hero")
        elif s.type == "plate":
            roles.append("numbers plate")
        elif s.type == "reveal":
            roles.append("reveal")
            revealed = True
        elif s.type == "composite":
            roles.append("media composition")
        else:
            roles.append("closing card")

    def scene_lines(idx: int, s: FilmScene) -> list[str]:
        start = round(sum(frames[: idx - 1]) / FILM_FPS, 1)
        end = round(sum(frames[:idx]) / FILM_FPS, 1)
        span = round(frames[idx - 1] / FILM_FPS, 1)
        # The stable scene id rides the header (the edit path's handle — the
        # model names scenes by id in update/reorder/remove ops).
        sid = getattr(s, "scene_id", None)
        out = [
            f"scene {idx}{f' [{sid}]' if sid else ''} · {s.type} · {roles[idx - 1]} · "
            f"{start:g}–{end:g}s · {span:g}s · {frames[idx - 1]} frames"
        ]
        if s.type == "words":
            vocab = []
            if s.motion and s.motion != "static":
                vocab.append(s.motion)
            if s.enter == "words":
                vocab.append("word-by-word")
            timing = words_timing_clause(s, frames[idx - 1])
            if timing:
                vocab.append(timing)
            style = _text_style_clause(s)
            if style:
                vocab.append(style)
            out.append(
                f"  shows: {' / '.join(s.lines)}{' (dark)' if s.dark else ''}"
                + (f" · {' · '.join(vocab)}" if vocab else "")
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
            moves = ui_focus_moves(s, pages)
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
        elif s.type == "composite":
            # The element facts ride the ONE content seat (ADR-140) —
            # fact sheet and chat read can never drift apart.
            out.append(f"  shows: {film_scene_content(s, frames[idx - 1], media)}")
        out.append(
            f'  narration: "{s.narration}"'
            if s.narration
            else "  narration: (silent — no narration by design)"
        )
        return out

    sources = " · ".join(dict.fromkeys(page_label(p) for p in range(len(pages))))
    lines = [
        " · ".join(head_bits),
        # The echo anti-fabrication law: a text film names its real source
        # (the user's copy / the assistant's draft), never an invented URL.
        source_note or f"sources: {sources}",
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


def current_text_direction_dict(storyboard: FilmStoryboard) -> dict[str, Any]:
    """The text board under review as the text director's revision base
    (修订基于当前稿, the text twin of current_direction_dict): words
    segments as RESOLVED display lines (real strings — the model re-cites
    what it keeps), composite segments as their element facts (asset ids,
    source windows, placements — the model re-addresses what it keeps).
    EVERY scene projects (a scene silently dropped from the revision base
    would be re-invented from scratch on the next redraft — the 修订基于
    当前稿 law's completeness half)."""
    segments: list[dict[str, Any]] = []
    for s in storyboard.scenes:
        if s.type == "composite":
            elements: list[dict[str, Any]] = []
            for el in s.elements:
                dump = el.model_dump(mode="json")
                # Code-owned seats never ride the revision base: identity
                # (re-minted at assembly) and the corpus anchor (re-derived
                # from the cited lines).
                dump.pop("element_id", None)
                dump.pop("copy_text", None)
                elements.append(dump)
            segments.append(
                {
                    "type": "composite",
                    "dark": s.dark,
                    "narration": s.narration,
                    "elements": elements,
                }
            )
            continue
        segments.append(
            {
                "type": "words",
                "lines": list(s.lines),
                "dark": s.dark,
                "motion": s.motion,
                "enter": s.enter,
                "enter_start": s.enter_start,
                "enter_interval": s.enter_interval,
                "enter_duration": s.enter_duration,
                "enter_hold_until": s.enter_hold_until,
                "motion_start": s.motion_start,
                "motion_end": s.motion_end,
                "exit_duration": s.exit_duration,
                "motion_scale": s.motion_scale,
                "align": s.align,
                "size": s.size,
                "accent_style": s.accent_style,
                "enter_style": s.enter_style,
                "narration": s.narration,
            }
        )
    return {
        "name": storyboard.name,
        "language": storyboard.language,
        "segments": segments,
    }


def _assemble_text(
    lines: list[dict[str, Any]],
    instruction: str | None,
    focus: str | None,
    language: str | None,
    current: dict[str, Any] | None,
    voiceover: bool,
    verbatim: bool,
    target_seconds: float | None,
    scene_count: int | None,
    media: list[dict[str, Any]] | None = None,
    composite_ok: bool = False,
    media_more: int = 0,
    group: tuple[int, int] | None = None,
) -> AssembleResult:
    """The text director's answer sheet (purity by signature, the
    ``_assemble`` twin): the numbered copy lines (its citation universe in
    verbatim mode), the run's instruction, the focus steer, the pinned
    language, the board under review, the voiceover promise, and the copy's
    ROLE (verbatim = cite, never rewrite) plus the user's named shape
    (duration / scene count / on-screen group size — ``group`` = [min, max]
    字 per screen).

    ``media`` = the project's composite-candidate listing (the ONE listing
    seat's rows — the model cites ids from it, never invents one);
    ``composite_ok`` = the media-composition capability's deployment gate —
    both ride the template's conditional section (gate OFF = the composite
    vocabulary never enters the prompt); ``media_more`` = the honest
    truncation count (assets existing beyond the printed listing — a
    truncated listing is never "the asset does not exist"). No screenshots
    exist on this source — nothing else."""
    return (
        {
            "lines": lines,
            "instruction": instruction,
            "focus": focus,
            "language": language,
            "current": current,
            "voiceover": voiceover,
            "verbatim": verbatim,
            "target_seconds": target_seconds,
            "scene_count": scene_count,
            "group": group,
            "media": media,
            "composite_ok": composite_ok,
            "media_more": media_more,
        },
        [],
    )


film_text_director = Agent[FilmTextDirection](
    name="film_text_director",
    prompt="film_director_text.j2",
    schema=FilmTextDirection,
    system=(
        "You are a film director cutting a TEXT film: solid-color text "
        "planes and — when the project's media is offered — composite "
        "scenes placing that media beside independent text on one screen. "
        "You decide the segmentation (which lines land together on one "
        "screen), each segment's composition and rhythm, and the narration "
        "when the plan promises voiceover. Durations and scene budgets are "
        "decided for you (a composite scene's length comes from its "
        "element windows). When the copy is the user's own text "
        "(verbatim), you CITE its lines by number — you never write, trim, "
        "reorder or reword them. Media elements cite asset ids from the "
        "project's media listing only — you never invent an id, and you "
        "have not watched the footage: when the request depends on what "
        "happens at a moment, the time range comes from the user."
    ),
    assemble=_assemble_text,
    temperature=0.5,
    # No skill pack: the launch-film pack's arc vocabulary is the WEB
    # source's (chapters / page walks); the text law lives in the template.
    stream=True,
    timeout_s=300,
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


def composite_asset_ids(board: FilmStoryboard | None) -> list[str]:
    """The ordered unique asset ids a board's composite scenes cite
    (ADR-140) — the media loader's fetch list. Empty for every legacy
    board, so the media universe costs nothing when unused."""
    ids: list[str] = []
    if board is None:
        return ids
    for scene in board.scenes:
        if scene.type != "composite":
            continue
        for el in scene.elements:
            if el.kind in ("video", "image") and el.asset not in ids:
                ids.append(el.asset)
    return ids


async def load_storyboard_media(
    db: AsyncSession,
    project: Project,
    board: FilmStoryboard | None,
    *,
    probe_duration: bool = False,
) -> StoryboardMedia:
    """The composite scenes' cited assets → the media universe (ADR-140).
    Only assets OWNED by this project resolve — a foreign or fabricated id
    simply never enters the map (the validator names it unresolved).

    ``probe_duration`` (the write seats — patch / run): a video whose
    ``duration_seconds`` is unknown (dormant, never ASR'd) gets ONE honest
    probe — the bytes come down through the shared cache and PyAV reads the
    container header — and the probed seconds are written back to the row
    (riding the caller's transaction). The Integer ``duration_seconds``
    column stores the FLOOR (display/legacy seats), while the EXACT probed
    value rides ``meta["probed_duration_seconds"]`` — flooring away the
    sub-second truth would falsely reject a legitimate trailing source
    window on every later read (复审缺陷③). Probe failure leaves the
    duration unknown, never guessed. Read seats pass False and report
    "unknown" honestly."""
    ids = composite_asset_ids(board)
    if not ids:
        return StoryboardMedia(assets={})
    uuid_ids: list[UUID] = []
    for raw in ids:
        with suppress(ValueError):
            uuid_ids.append(UUID(raw))
    if not uuid_ids:
        return StoryboardMedia(assets={})
    rows = list(
        (
            await db.execute(
                select(Asset)
                .where(Asset.project_id == project.id, Asset.id.in_(uuid_ids))
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    assets: dict[str, StoryboardMediaAsset] = {}
    for row in rows:
        meta = row.meta if isinstance(row.meta, dict) else {}
        duration = (
            float(row.duration_seconds)
            if row.duration_seconds is not None
            else None
        )
        # The probed sub-second truth (same bytes, finer precision) wins over
        # the floored Integer column whenever both are on the row.
        probed_known = meta.get("probed_duration_seconds")
        if isinstance(probed_known, (int, float)) and not isinstance(
            probed_known, bool
        ):
            duration = float(probed_known)
        if (
            probe_duration
            and duration is None
            and row.type == AssetType.VIDEO
            and row.file_url
        ):
            probed = await _probe_video_duration(row.file_url)
            if probed is not None:
                duration = probed
                # Write-back (the _track_beats_backfilled precedent): the
                # next seat reads the row instead of re-downloading. Floor
                # into the Integer column — never round UP past the truth —
                # and pin the exact value in meta so later reads keep the
                # sub-second truth.
                row.duration_seconds = int(probed)
                row.meta = {**meta, "probed_duration_seconds": probed}
        assets[str(row.id)] = StoryboardMediaAsset(
            id=str(row.id),
            key=row.file_url,
            kind=row.type.value,
            title=row.display_name,
            duration_seconds=duration,
            width=meta.get("width") if isinstance(meta.get("width"), int) else None,
            height=meta.get("height") if isinstance(meta.get("height"), int) else None,
        )
    return StoryboardMedia(assets=assets)


async def _probe_video_duration(key: str) -> float | None:
    """Container-header duration probe over the shared download cache —
    degrade-to-absence, never an exception up the stack."""
    try:
        from app.providers.storage import download_to_cache

        path = await download_to_cache(key)
        if path is None:
            return None
        import av  # faster-whisper dep; no system ffmpeg needed

        with av.open(str(path)) as container:
            if container.duration is None:
                return None
            seconds = float(container.duration) / float(av.time_base)
            return seconds if seconds > 0 else None
    except Exception:
        return None


# The media DISCOVERY listing (ADR-140 下批): the project-wide candidate
# universe a composite design cites from. ONE seat, two consumers — the chat
# read (list_project_media) and the text director's prompt — so the facts the
# model reads and the facts it designs from can never drift apart.
MEDIA_LISTING_CAP = 40  # print budget per listing (newest first)


async def project_media_candidates(
    db: AsyncSession,
    project: Project,
    *,
    pinned_ids: list[str] | None = None,
) -> list[dict]:
    """The project's composite-candidate media (video + image) as FACT dicts.

    Ids + facts only — storage keys never leave the server (the model cites
    ids, code resolves the bytes; the ui scene's law). Ordered newest-first;
    the consumers print at most ``MEDIA_LISTING_CAP`` rows per listing and
    say so (a truncated listing is never "the asset does not exist" — the
    41st asset is still citable, the read pages to it, and validation
    resolves any project id regardless of what was printed).

    ``pinned_ids`` (the assets the user explicitly selected, e.g. via
    @-mentions) are lifted to the front of the listing in the given order —
    a pinned id beyond the print cap still enters the listing. Pinning is
    filtered through the project query itself, so a foreign or unknown id
    can never materialise a candidate the tenant does not own.

    Per row: ``id`` / ``kind`` / ``title`` / ``duration_seconds`` (None =
    UNKNOWN — never guessed; the exact probed value wins over the floored
    Integer column, the loader's own law) / ``width`` / ``height`` (None =
    unknown) / ``usable`` (the media bytes exist — a transcript-less or
    never-analysed video is still fully usable footage; composition reads
    the BYTES, not the ASR) / ``processing`` (the content-analysis state —
    informational, never a usability gate)."""
    rows = list(
        (
            await db.execute(
                select(Asset)
                .where(
                    Asset.project_id == project.id,
                    Asset.type.in_((AssetType.VIDEO, AssetType.IMAGE)),
                )
                .order_by(Asset.created_at.desc())
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    candidates: list[dict] = []
    for row in rows:
        meta = row.meta if isinstance(row.meta, dict) else {}
        duration = (
            float(row.duration_seconds)
            if row.duration_seconds is not None
            else None
        )
        probed = meta.get("probed_duration_seconds")
        if isinstance(probed, (int, float)) and not isinstance(probed, bool):
            duration = float(probed)
        candidates.append(
            {
                "id": str(row.id),
                "kind": row.type.value,
                "title": row.display_name,
                "duration_seconds": duration,
                "width": (
                    meta.get("width") if isinstance(meta.get("width"), int) else None
                ),
                "height": (
                    meta.get("height")
                    if isinstance(meta.get("height"), int)
                    else None
                ),
                "usable": bool(row.file_url),
                "processing": (
                    row.processing_status.value if row.processing_status else None
                ),
            }
        )
    if pinned_ids:
        # Pinned-first: the user's explicit selection leads the listing so a
        # pick beyond the print cap still reaches the director's context.
        # Every pinned id has been resolved through the project-scoped query
        # above — a foreign/unknown id simply finds no row and is ignored.
        by_id = {c["id"]: c for c in candidates}
        pinned = [
            by_id[pid]
            for pid in dict.fromkeys(str(i) for i in pinned_ids)
            if pid in by_id
        ]
        if pinned:
            pinned_set = {c["id"] for c in pinned}
            candidates = pinned + [c for c in candidates if c["id"] not in pinned_set]
    return candidates


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
    text_source: FilmTextSource | None = None,
    media_candidates: list[dict[str, Any]] | None = None,
    media_loader: Any = None,
    composite_ok: bool = False,
    media_more: int = 0,
) -> FilmStoryboard:
    """THE bounded direction loop (打回有界, ADR-127): the skeleton is
    code-owned; up to 1 + MAX_REWRITES direction candidates, each re-called
    with the violation echo (never a blind re-roll), each spliced into the
    skeleton by ``assemble_storyboard`` and then facing the validator.
    Returns the first assembly that passes.

    ``text_source`` (ADR-138 §7.6 素材源抽象): present = the TEXT source's
    twin loop (``_orchestrate_text_storyboard``) — the copy is the grounding
    universe, the arc is text planes, the birth gate is the zero-copy
    preflight instead of ``_MIN_VIEWS``. The two sources share everything
    else: the bounded ladder, the honest terminal, the validator.

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
    if text_source is not None:
        return await _orchestrate_text_storyboard(
            text_source=text_source,
            instruction=instruction,
            focus=focus,
            language=language,
            current=current,
            on_reject=on_reject,
            allow_fixed_fallback=allow_fixed_fallback,
            voiceover=voiceover,
            media_candidates=media_candidates,
            media_loader=media_loader,
            composite_ok=composite_ok,
            media_more=media_more,
        )
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


def _text_feasibility(
    lines: list[ManifestLine], *, source: FilmTextSource, media_available: bool = False
) -> FilmStoryboardRejected | None:
    """The text film's material-feasibility preflight — it runs BEFORE any
    model call, so the model is never asked for the impossible (the
    cf00526d deadlock's law: never demand a full citation of an
    unsplittable unit, then reject the unit). It judges ONLY what is
    provably impossible before any candidate exists (复审②): the densest
    COMPOSITE packing bounds the copy's minimum footprint (a media-only
    scene carries no copy; several text elements share one scene), and
    everything else — the director's composition choices — goes to the
    candidate assembly and the real validator, never to an estimate-based
    guess here. ``media_available`` = the project has at least one usable
    video/image asset (the verbatim named-count bound's only media
    dependence). None = a legal arrangement exists — the director's job is
    findable.

    改编 ≠ 逐字 (定点复审): in AUTHORED mode the input is REFERENCE
    MATERIAL — it informs the copy the model writes, it is not text that
    must appear on screen. Its line count, display packing and estimated
    reading time therefore bound NOTHING about the legal output (输入长度
    ≠ 输出篇幅): the coverage-derived checks below are verbatim-only, and
    an authored candidate's real limits (screen capacity, element windows,
    media ranges, the frame cap) are judged on the candidate itself by
    assembly and the validator — never estimated here from the reference."""
    # The densest packing: a composite scene's text elements hold up to
    # (elements cap × per-element line cap) display lines — the real
    # screen-capacity bound. A words plane's 4-line screen is the
    # CONVENIENCE recipe, never the densest.
    per_scene_cap = (
        _LIST_CAPS["composite.elements"] * _LIST_CAPS["composite.text-lines"]
    )
    packed_units: list[int] = []
    cur_units = 0
    cur_display = 0
    min_scenes = 0
    for l in lines:
        wrapped = _wrap_display_lines(l.text)
        n = len(wrapped)
        u = sum(_read_units(dl) for dl in wrapped)
        if cur_units and cur_display + n > per_scene_cap:
            packed_units.append(cur_units)
            min_scenes += 1
            cur_units, cur_display = 0, 0
        cur_units += u
        cur_display += n
    if cur_units:
        packed_units.append(cur_units)
        min_scenes += 1
    floors_sum = sum(_text_read_floor(u) for u in packed_units)
    hi_total = TEXT_TOTAL_SECONDS_RANGE[1]
    # The DEFAULT-pace ceiling — VERBATIM ONLY (定点复审): the estimate
    # measures the input copy, so it can only gate a mode where the full
    # input must appear (verbatim). In authored mode the reference
    # condenses into the model's own copy — its estimated reading time
    # says nothing about the output. The check only gates when NO duration
    # is named: the estimated reading time is a recommendation, never a
    # technical bound (2026-10-22 拍板). A named duration ≤ the cap is the
    # user's law — the allocator rescales to it no matter what the
    # estimate says, so this check must stand aside (a named duration OVER
    # the cap meets the real TARGET_OVERFLOW refusal below). Without the
    # guard the echo's own escape hatch ("OR name a duration") would be a
    # lie.
    if (
        source.verbatim
        and floors_sum > hi_total
        and source.target_seconds is None
    ):
        return FilmStoryboardRejected(
            ["TEXT_BEYOND_REACH"],
            f"the full copy reads for ~{floors_sum:g}s at the estimated "
            f"reading pace — past the {hi_total:g}s frame-cap ceiling, so "
            "the DEFAULT pace cannot stand; the words must shrink or the "
            "copy must be adapted or split — OR name a duration and the "
            "system paces it faster (the text will move quickly: your "
            "explicit choice)",
            user_key="film_text_beyond_reach",
        )
    # The densest-packing count (min_scenes) is NOT itself a rejection gate:
    # the 2..30 count band is a craft default. It feeds only the named-count
    # provable bounds below — the floors_sum check above is the real gate
    # (a 35-plane copy whose floors fit the frame cap is a legal film).
    #
    # A named duration is the user's LAW, never estimate-gated (2026-10-22
    # 拍板): shorter than the estimated reading time = the user's explicit
    # faster pace — the allocator scales down and the presentation notes
    # the readability impact. The ONE duration refusal is REAL: over the
    # render frame cap.
    if source.target_seconds is not None and source.target_seconds > hi_total:
        return FilmStoryboardRejected(
            ["TARGET_OVERFLOW"],
            f"the named {source.target_seconds:g}s is over the {hi_total:g}s "
            "render frame cap — name a duration within the cap",
            user_key="film_text_target_overflow",
        )
    if source.scene_count is not None:
        # Provably-impossible bounds ONLY (复审② + 定点复审), and they are
        # VERBATIM-ONLY: the coverage law (every input line shows exactly
        # once) is what turns the input's display packing into a scene
        # floor — below the densest composite packing the copy cannot
        # physically fit (screen capacity — a hard technical bound). The
        # ceiling is the copy's FINEST citation granularity, not its line
        # count (fc13e77d 修复: spans split a line —「引用行数就是最大幕数」
        # was the wrong bound): one latin word / one glyph per scene, and
        # without usable media a scene cannot stand without copy. In
        # AUTHORED mode the input is reference material — the model
        # condenses it into its own copy, so no input-derived count
        # bound exists at all: the named count faces the candidates and
        # the real validator, never this preflight.
        if source.verbatim and source.scene_count < min_scenes:
            return FilmStoryboardRejected(
                ["TARGET_OVERFLOW"],
                f"the named {source.scene_count} scene(s) cannot hold this "
                f"copy — even the densest composition ({per_scene_cap} "
                f"display lines on one screen) needs {min_scenes}; name at "
                f"least {min_scenes} or let the director pick",
                user_key="film_text_target_overflow",
            )
        if source.verbatim and not media_available:
            max_scenes = sum(_atomic_unit_count(l.text) for l in lines)
            if source.scene_count > max_scenes:
                return FilmStoryboardRejected(
                    ["TARGET_OVERFLOW"],
                    f"the named {source.scene_count} scenes cannot each carry "
                    f"the user's verbatim copy — every character shows "
                    f"exactly once and a latin word never splits, so the "
                    f"finest split is {max_scenes} scenes; name a count up "
                    f"to {max_scenes}, add media to compose with, or let "
                    "the director pick",
                    user_key="film_text_target_overflow",
                )
    return None


async def _orchestrate_text_storyboard(
    *,
    text_source: FilmTextSource,
    instruction: str | None,
    focus: str | None,
    language: str | None,
    current: FilmStoryboard | None,
    on_reject,
    allow_fixed_fallback: bool,
    voiceover: bool,
    media_candidates: list[dict[str, Any]] | None = None,
    media_loader: Any = None,
    composite_ok: bool = False,
    media_more: int = 0,
) -> FilmStoryboard:
    """The text source's bounded direction loop (the web loop's twin — same
    ladder, same honest terminal): 1 + MAX_REWRITES candidates, each
    repaired by the violation echo; the birth gate is the zero-copy
    preflight plus the material-feasibility preflight (an unsatisfiable
    copy/target fails BEFORE an LLM call is burned); a repeated identical
    violation set stops the ladder early (no-progress — never a third
    blind full regeneration); the fallback is ``fixed_text_storyboard``
    (the worker's unattended rung — the design journey closes it like the
    web path does).

    Media composition (ADR-140 出生面): ``composite_ok`` is the capability
    gate (prompt AND assembly read it together); ``media_candidates`` is
    the prompt's citation universe (the ONE listing seat's rows);
    ``media_loader`` resolves a candidate board's media universe for the
    validator (the design/run seats probe durations — identity and window
    truths are checked against the real bytes at birth, never deferred).
    None candidates/loader = the pure seats' deferral law (media=None).
    ``media_more`` is the honest truncation count — how many candidates
    exist beyond the printed listing (a truncated listing is never "the
    asset does not exist"; the prompt says so and validation still
    resolves any project id)."""
    lines = build_text_manifest(text_source.text)
    if not lines:
        logger.info("film_text_preflight_failed", reason="empty_copy")
        raise FilmStoryboardRejected(
            ["EMPTY_COPY"],
            "the text is empty — paste the copy itself (or name what the "
            "film should say)",
            user_key="film_text_empty",
        )
    # Material feasibility BEFORE any model call (the model is never asked
    # for the impossible): an unsatisfiable copy/target fails here with
    # the concrete conflict, never after three burned candidates.
    infeasible = _text_feasibility(
        lines,
        source=text_source,
        media_available=any(
            c.get("usable") for c in (media_candidates or [])
        ),
    )
    if infeasible is not None:
        logger.info(
            "film_text_preflight_failed",
            reason=infeasible.user_key,
            detail=infeasible.detail[:300],
        )
        raise infeasible
    prompt_lines = [{"id": l.id, "kind": l.kind, "text": l.text} for l in lines]
    prompt_current = (
        current_text_direction_dict(current) if current is not None else None
    )
    violations: list[FilmViolation] = []
    feedback: str | None = None
    prev_signatures: frozenset[tuple[str, str]] | None = None
    try:
        async with asyncio.timeout(_DIRECTION_BUDGET_S):
            for attempt in range(1 + MAX_REWRITES):
                direction = await film_text_director.call(
                    lines=prompt_lines,
                    instruction=instruction,
                    focus=focus,
                    language=language,
                    current=prompt_current,
                    voiceover=voiceover,
                    verbatim=text_source.verbatim,
                    target_seconds=text_source.target_seconds,
                    scene_count=text_source.scene_count,
                    group=text_source.group_chars,
                    media=media_candidates,
                    composite_ok=composite_ok,
                    media_more=media_more,
                    repair_feedback=feedback,
                )
                resolved, violations = assemble_text_storyboard(
                    direction, lines, source=text_source,
                    pinned_language=language, composite_ok=composite_ok,
                )
                if resolved is not None:
                    media = (
                        await media_loader(resolved)
                        if media_loader is not None
                        else None
                    )
                    violations = validate_storyboard(
                        resolved, [], narration_required=voiceover,
                        text_lines=lines, media=media,
                    )
                    if not violations:
                        return resolved
                feedback = format_violations(violations)
                signatures = frozenset((v.code, v.detail) for v in violations)
                if signatures == prev_signatures:
                    # No progress (总设计 §8.2.8): the SAME violation set two
                    # candidates in a row — a third full regeneration would
                    # re-burn the budget for the same answer. Stop here and
                    # fail honestly with the standing violations.
                    logger.info(
                        "film_text_direction_no_progress",
                        attempt=attempt,
                        codes=sorted({v.code for v in violations}),
                    )
                    break
                prev_signatures = signatures
                if on_reject is not None:
                    notification = on_reject(attempt, violations, feedback)
                    if inspect.isawaitable(notification):
                        await notification
        rejection: Exception = FilmStoryboardRejected(
            sorted({v.code for v in violations}),
            feedback or "",
            # The text ladder's exhaustion speaks the TEXT context (the
            # copy/duration/scene-count not lining up) — never the web
            # source's "clearer page" remedy.
            user_key="film_text_ungrounded",
        )
    except TimeoutError:
        logger.warning("film_direction_budget_exhausted", budget_s=_DIRECTION_BUDGET_S)
        rejection = LLMError("Storyboard generation exceeded its total budget", user_key="film_storyboard_timeout")
    except (LLMSchemaError, LLMError) as exc:
        rejection = exc
    if allow_fixed_fallback:
        logger.info("film_text_direction_fixed_fallback", reason=str(rejection)[:200])
        fixed = fixed_text_storyboard(lines, source=text_source, language=language)
        if fixed is not None:
            fviolations = validate_storyboard(
                fixed, [], narration_required=voiceover, text_lines=lines
            )
            if not fviolations:
                logger.info(
                    "film_fixed_storyboard_used",
                    scenes=len(fixed.scenes),
                    seconds=sum(s.seconds for s in fixed.scenes),
                )
                return fixed
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
    text_source: FilmTextSource | None = None,
    pinned_asset_ids: list[str] | None = None,
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
    frame), so a label never outlives its work.

    ``text_source`` (ADR-138 §7.6): present = a TEXT film — no capture wait,
    no pages (the copy is the universe; the returned pages list is empty).
    The "capturing" phase rides the WEB branch alone (B1): a text film reads
    no page, so its first phase is "storyboarding" — the web path emits
    "capturing" byte-for-byte as before.

    ``pinned_asset_ids`` (ADR-140 发现面): the assets the user explicitly
    selected (e.g. @-mentions on the request) — lifted to the front of the
    director's candidate listing so a pick beyond the print cap still
    reaches its context (tenant-scoped at the listing seat: a foreign id
    never materialises a row)."""
    if on_progress is not None and text_source is None:
        await on_progress("capturing")
    try:
        if text_source is not None:
            pages: list[StoryboardPage] = []
            page_images: list[MediaInput] = []
        else:
            await _await_captures_settled(project.id)
            pages = await load_storyboard_pages(db, project)
            if not pages:
                return None
            page_images = await page_media_inputs(pages)
        if on_progress is not None:
            await on_progress("storyboarding")

        async def rejected(attempt, violations, feedback):
            logger.info("film_plan_draft_rejected", project_id=str(project.id),
                        attempt=attempt, codes=sorted({v.code for v in violations}),
                        detail=(feedback or "")[:600])
            if on_progress is not None:
                await on_progress("storyboard_revision")
        # Media composition (ADR-140 出生面): the TEXT branch wires the
        # discovery listing into the director's prompt and the per-candidate
        # media universe into the validator — identity and source-window
        # truths checked against the real bytes AT BIRTH (the write seats'
        # probe law), never deferred to the run. Gate OFF (or the pure
        # tests' db=None): the vocabulary stays closed and media checks
        # defer (media=None).
        media_candidates: list[dict[str, Any]] | None = None
        media_loader = None
        composite_ok = False
        media_more = 0
        if text_source is not None and db is not None:
            from app.config import settings  # deferred: config leaf

            composite_ok = bool(settings.film_edits_enabled)
            if composite_ok:
                full_candidates = await project_media_candidates(
                    db, project, pinned_ids=pinned_asset_ids
                )
                media_candidates = full_candidates[:MEDIA_LISTING_CAP]
                media_more = len(full_candidates) - len(media_candidates)

                async def media_loader(board: FilmStoryboard) -> StoryboardMedia:
                    return await load_storyboard_media(
                        db, project, board, probe_duration=True
                    )
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
                text_source=text_source,
                media_candidates=media_candidates,
                media_loader=media_loader,
                composite_ok=composite_ok,
                media_more=media_more,
            )
        except (FilmStoryboardRejected, LLMSchemaError, LLMError) as exc:
            # Preflight and budget failures keep their OWN honest keys all the
            # way to the user — converting them to None would relabel a known
            # cause (missing captures / provider slowness / an empty copy /
            # an exhausted text ladder) as an ungrounded copy problem.
            if getattr(exc, "user_key", None) in {
                "film_storyboard_timeout",
                "film_views_missing",
                "film_text_empty",
                "film_text_ungrounded",
                "film_text_beyond_reach",
                "film_text_target_overflow",
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


# 音频三态 (ADR-138 §7.5): the film bed's explicit OFF state. ``music_mood``
# carries three states — absent/None = unspecified (the resolution chain:
# named mood → persona skin default → "calm"), a mood name = an explicit
# selection, and this sentinel = an explicit OFF. OFF is a REAL terminal
# state: the resolution chain short-circuits on it (persona and the calm
# default NEVER re-open a bed the user switched off), and the version pins
# it so later versions inherit it until an edit names a mood again.
FILM_MUSIC_OFF = "off"


def canonical_film_params(params: dict) -> dict:
    """The launch_film design params in their ONE canonical form (the
    fingerprint's own pinning: nulls drop out, aspect pins "16:9",
    voiceover pins narrated). The dock seats rewrite the proposed task's
    params from the presented version's params through this, so the
    confirmed chain carries exactly what the presented board was designed
    with — a param the model spelled only once never reads as drift.

    Music three states (ADR-138 §7.5): an absent ``music_mood`` drops out
    (unspecified → the resolution chain), a mood string pins the selection,
    and the explicit OFF (``FILM_MUSIC_OFF``) pins the closed state — three
    distinguishable fingerprints, so a version born off never reads as
    merely unset (which would resolve back to the calm default)."""
    canonical = {
        k: v
        for k, v in params.items()
        if v is not None and k in {"focus", "language", "music_mood", "aspect"}
    }
    canonical["aspect"] = canonical.get("aspect") or "16:9"
    canonical["voiceover"] = params.get("voiceover") is not False
    # Text source (ADR-138 §7.6): the copy pins WITH its role and named
    # shape — a text film's identity includes its words (two films over
    # different copy never share a fingerprint). Absent text = a web film;
    # the keys stay out (legacy web fingerprints byte-unchanged).
    if params.get("text"):
        canonical["text"] = str(params["text"])
        canonical["verbatim"] = params.get("verbatim") is not False
        for k in ("target_seconds", "scene_count", "group_chars"):
            if params.get(k) is not None:
                canonical[k] = params[k]
    return canonical


def film_voiceover_birth_pin(
    value: bool | None, base_params: object, *, base_present: bool
) -> bool:
    """The voiceover pin at a film's BIRTH (默认无配音, 2026-10-21 用户拍板):
    the ONE seat where an unset voiceover becomes the explicit value a new
    version carries. Both chat design seats (compose path) ride here so the
    pin lands in ``design_params`` BEFORE canonicalization — the stored
    version params, the fingerprint, the dock restore and the run's slot
    then all carry the explicit value byte-for-byte.

    The law (新建默认 vs legacy 解读 — two different lenses, never mixed):
    - an explicit value (true/false) pins verbatim — true is legitimate ONLY
      when the user explicitly asked for narration (the schema's law; code
      trusts the declared arg);
    - a redraft/variant over an EXISTING version inherits THAT version's
      pinned setting (修改继承既有设置) — legacy params read through
      ``canonical_film_params``'s historical lens (a missing key = the
      historical narrated default), and a legacy base with no params record
      at all reads as narrated too (that is what those films shipped with);
    - only a genuinely NEW film (no base version) defaults OFF.

    ``canonical_film_params``'s null→narrated reading is NOT changed: it is
    the legacy lens for already-stored versions (their digests, restores,
    re-renders and quotes keep resolving byte-identically)."""
    if value is not None:
        return bool(value)
    if not base_present:
        return False
    if isinstance(base_params, dict):
        return canonical_film_params(base_params)["voiceover"]
    # A legacy base whose params were never recorded: the historical default
    # was narrated — inherit it rather than silently muting an old film.
    return True


def film_verbatim_birth_pin(
    value: bool | None, base_params: object, *, base_present: bool, text_present: bool
) -> bool | None:
    """The verbatim pin at a text film's BIRTH (贴文 ≠ 逐字, 2026-10-22 用户
    拍板): the mode is the direction-stage decision, never a guess from the
    mere fact the user pasted text. The ONE seat where an unset verbatim
    becomes the explicit value a new version carries — mirroring
    ``film_voiceover_birth_pin``, the pin lands in ``design_params`` BEFORE
    canonicalization, so the stored version params, the fingerprint, the
    dock restore and the run's slot all carry the explicit value
    byte-for-byte (执行提案继承已确定版本, never re-guessed).

    The law (继承已确定版本 vs legacy 解读 — two lenses, never mixed):
    - an explicit value pins verbatim — the model's declared direction-stage
      decision (code trusts the declared arg);
    - a redraft over an EXISTING text version inherits THAT version's pinned
      mode — legacy params read through ``canonical_film_params``'s
      historical lens (a missing key = the historical preserve read), and a
      legacy base with no params record reads as preserve too;
    - only a genuinely NEW text film (no base version) with no declared mode
      reads null as true — the safe legacy-compatible read: preserve the
      user's words, never silently rewrite them.

    ``canonical_film_params``'s null→true reading is NOT changed: it is the
    legacy lens for already-stored versions. No text source = None (the key
    drops out of the canonical form)."""
    if not text_present:
        return None
    if value is not None:
        return bool(value)
    if base_present:
        if isinstance(base_params, dict):
            return canonical_film_params(base_params).get("verbatim", True)
        # A legacy base whose params were never recorded: preserve is what
        # those films shipped with.
        return True
    return True


def film_text_source_birth_pin(
    text: str | None,
    target_seconds: float | None,
    scene_count: int | None,
    group_chars: list[int] | None,
    base_params: object,
    *,
    base_present: bool,
    target_seconds_present: bool,
    scene_count_present: bool,
    group_chars_present: bool,
) -> tuple[str | None, float | None, int | None, list[int] | None]:
    """Pin a text source at birth/redraft without losing field presence.

    ``text`` keeps its existing value semantics: a re-pasted value overrides,
    otherwise the base copy is inherited. The three shape constraints are
    presence-sensitive: omission inherits the base, an explicit null clears
    it, and a supplied value overrides it. The callers read presence from
    ``DesignStoryboardArgs.model_fields_set`` AFTER wire normalization; using
    ``value is not None`` here would make an explicit clear indistinguishable
    from an omitted field.
    """
    base = base_params if (base_present and isinstance(base_params, dict)) else {}

    def _shape_pin(value: Any, *, present: bool, key: str) -> Any:
        if not base_present:
            return value
        return value if present else base.get(key)

    return (
        text if text is not None else base.get("text"),
        _shape_pin(target_seconds, present=target_seconds_present, key="target_seconds"),
        _shape_pin(scene_count, present=scene_count_present, key="scene_count"),
        _shape_pin(group_chars, present=group_chars_present, key="group_chars"),
    )


def text_source_drift_note(restated: str | None, base_text: str | None) -> str | None:
    """逐字重稿的抄录漂移注记 (7276ef13 v3 取证 — 「买喜欢的东西」被模型重抄
    成「买喜欢的事」): the redraft pin (``film_text_source_birth_pin``)
    inherits the base version's copy only when ``text`` is OMITTED — an
    explicit re-paste is trusted verbatim BY LAW (a deliberate copy edit
    stays legal, never a hard reject), so a drifted re-transcription would
    otherwise pass coverage against the NEW wrong text and present as «原
    文一字未改». When the re-pasted text differs from the base version's
    pinned copy, this note names the drifted clause pair(s) — the
    observation carries it so the presentation is honest.

    The diff rides the SAME clause segmentation as the citation universe
    (``build_text_manifest``) — the note speaks in the line ids the model
    already sees. None = nothing to report (identical re-paste, no
    restate, or no base copy to drift from)."""
    if restated is None or base_text is None or restated == base_text:
        return None
    base_lines = [l.text for l in build_text_manifest(base_text)]
    new_lines = [l.text for l in build_text_manifest(restated)]
    diffs: list[str] = []
    for i, (old, new) in enumerate(zip(base_lines, new_lines), start=1):
        if old != new:
            diffs.append(f"L{i} was «{old}» and now reads «{new}»")
        if len(diffs) >= 3:
            break
    if not diffs:
        diffs.append(
            f"the copy now runs {len(new_lines)} lines (was {len(base_lines)})"
        )
    return (
        "COPY DRIFT — the copy re-pasted with this redraft differs from "
        "the version it revises: "
        + "; ".join(diffs)
        + ". The saved board carries the RE-PASTED wording verbatim (a "
        "deliberate copy edit stays legal — this is a note, never a "
        "rejection): present the new wording as it stands, and never "
        "describe it as the original unchanged; if the drift was not what "
        "the user meant, say so and re-paste the confirmed copy."
    )


def text_drift_user_proven(restated: str, user_text: str) -> bool:
    """漂移的用户可证性 (7276ef13 定点收尾②): the re-pasted copy counts as
    USER-SOURCED only when it appears verbatim (whitespace-insensitive) in
    the turn's own user message — the user pasted the new copy themselves.
    A drift the message never carried (the model re-transcribing, an added
    clause on a layout-only ask) is UNPROVEN: the version publishes with
    the honest note, but the dock's confirmation law holds the auto start
    (``copy_drift``) — a note alone never spends on unproven wording. The
    precise route for a deliberate text change stays the patch path's
    explicit copy slots, whose exact before/after facts are reviewable;
    those slots alone still do not prove user authorization."""
    norm = lambda s: "".join(s.split())  # noqa: E731
    return bool(restated and user_text) and norm(restated) in norm(user_text)


def _text_drift_digest(text: str) -> str:
    """The drift baseline's content identity (whitespace-insensitive — the
    proven check's same normalization seat)."""
    import hashlib

    return hashlib.sha256("".join(text.split()).encode()).hexdigest()


def film_text_drift_next(
    base_drift: dict | None,
    base_text: str | None,
    new_text: str | None,
    user_text: str,
) -> dict | None:
    """未接受文字漂移的持续性 (7276ef13 定点收尾②复审 — the A→B→继承 B
    hole): the drift hold tracks the LAST PROVABLY-ACCEPTED text baseline,
    never the adjacent-version diff. ``base_drift`` = the base version's
    persisted drift state (None = its pinned text was the accepted
    baseline); ``new_text`` = the NEW version's pinned copy (post-
    inheritance — an omitted ``text`` inherits the base's, and inheriting
    a drifted copy NEVER clears the hold).

    Release is exhaustive — exactly three provable paths: ① RESTORE — the
    new pinned copy matches the baseline (whitespace-insensitive);
    ② USER-SOURCED — the user pasted the new copy themselves this turn
    (``text_drift_user_proven``); ③ the copy_drift dock's explicit confirm
    (the start consumes the pending — the state dies with it, no seat
    here). Everything else — omitting text, re-stating the drifted copy,
    an unrelated patch, an ordinary redraft — CARRIES the state forward.
    Returns the new version's ``film_text_drift`` (``None`` = no hold)."""
    if not new_text:
        # No text lineage to judge (non-text chain) — a standing hold
        # carries conservatively, never washes.
        return base_drift if isinstance(base_drift, dict) else None
    baseline_digest = (
        base_drift.get("baseline_sha256")
        if isinstance(base_drift, dict)
        else None
    )
    if baseline_digest is None:
        if not base_text:
            return None  # first text version — no baseline to drift from
        baseline_digest = _text_drift_digest(base_text)
    if _text_drift_digest(new_text) == baseline_digest:
        return None  # ① restored (or never drifted)
    if text_drift_user_proven(new_text, user_text):
        return None  # ② the user sourced this copy
    return {"baseline_sha256": baseline_digest}


def film_text_drift_held(pending: Any) -> bool:
    """The dock seats' copy_drift flag (定点收尾②复审): read the STANDING
    version's persisted drift state — the world truth, never a turn-local
    flag (a later turn's dock over a drifted-unaccepted version holds
    exactly like the birth turn's; a turn object rebuilt across turns
    never loses the protection). Accepts a pending dict, a PendingPlan,
    or None."""
    if pending is None:
        return False
    drift = (
        pending.get("film_text_drift")
        if isinstance(pending, dict)
        else getattr(pending, "film_text_drift", None)
    )
    return isinstance(drift, dict) and bool(drift.get("baseline_sha256"))


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


def _scene_content_dump(scene: dict) -> dict:
    """One scene's CONTENT dump: ``scene_id`` is an identity handle, never
    content — it never participates in any digest, so assigning or keeping
    ids moves neither the per-scene nor the whole-board digest of a legacy
    board (old stored digests keep matching byte-for-byte). Post-v1
    vocabulary keys (``_LEGACY_ABSENT_SCENE_KEYS``) are likewise excluded
    while null: a legacy board validated by the new model materializes the
    default ``None`` — dropping the null keeps its digest byte-identical,
    while a SET value participates normally (an edit moves the digest).
    Nested element ids (ADR-140) ride the same law: ``element_id`` is an
    identity handle for edit targeting, never content."""
    dump: dict = {}
    for k, v in scene.items():
        if k == "scene_id" or (v is None and k in _LEGACY_ABSENT_SCENE_KEYS):
            continue
        if k == "elements" and isinstance(v, list):
            # Nested element nulls ride the SAME legacy-absent law as
            # scene-level keys: a pre-vocabulary element re-validated by
            # the new model materializes the defaults — dropping the nulls
            # keeps its digest byte-identical; a SET value participates.
            v = [
                {
                    ek: ev
                    for ek, ev in el.items()
                    if ek != "element_id"
                    and not (ev is None and ek in _LEGACY_ABSENT_SCENE_KEYS)
                }
                if isinstance(el, dict)
                else el
                for el in v
            ]
        dump[k] = v
    return dump


# Scene keys no legacy board carries — null reads as absent in digests.
_LEGACY_ABSENT_SCENE_KEYS = frozenset(
    {
        "motion",
        "enter",
        "copy_text",
        "enter_start",
        "enter_interval",
        "enter_duration",
        "enter_hold_until",
        "motion_start",
        "motion_end",
        "exit_duration",
        "motion_scale",
        "align",
        "size",
        "accent_style",
        "enter_style",
    }
)


def scene_content_digest(scene: FilmScene | dict) -> str:
    """The position-independent identity of ONE scene's content (复用与
    diff 的身份): reorder moves the board digest but never this one; an
    edit moves this one. The id itself is excluded by law (see above)."""
    model = (
        scene
        if not isinstance(scene, dict)
        else TypeAdapter(FilmScene).validate_python(scene)
    )
    payload = json.dumps(
        _scene_content_dump(model.model_dump(mode="json")),
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
    garbage. ORDER-SENSITIVE by contract (a reorder is a meaningful
    change); scene ids never participate (``_scene_content_dump``)."""
    model = (
        storyboard
        if isinstance(storyboard, FilmStoryboard)
        else FilmStoryboard.model_validate(storyboard)
    )
    dump = model.model_dump(mode="json")
    dump["scenes"] = [_scene_content_dump(s) for s in dump.get("scenes", [])]
    # A null theme accent reads as absent (the scene-level law's board-level
    # twin): a pre-accent board re-validated by the new model materializes
    # ``accent: None`` — dropping the null keeps its digest byte-identical.
    theme_dump = dump.get("theme")
    if isinstance(theme_dump, dict):
        dump["theme"] = {k: v for k, v in theme_dump.items() if v is not None}
    payload = json.dumps(dump, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_film_execution_snapshot(
    *,
    pages: list[StoryboardPage],
    track: Music | None,
    media: StoryboardMedia | None = None,
) -> dict:
    """The film's execution inputs frozen at design time (ADR-129/ADR-130
    §1): the pages the board was grounded on (asset id / url / screenshot
    key), the resolved music grid (track id / mood / bpm / beats — the SAME
    grid the markdown's snapped timing shows), the timing constant, and
    ``digest`` over that canonical form. LaunchFilm consumes the snapshot
    verbatim; drift against it fails honestly, never a silent
    re-orchestration.

    ``media`` (ADR-140): the composite scenes' cited assets pinned by
    IDENTITY (id + storage key) — a deleted or replaced asset drifts the
    digest and fails honestly. Durations stay OUT (a probe backfill moves
    knowledge, not identity — pinning it would false-positive every
    first-run probe). The section is omitted when empty so pre-composite
    snapshots digest byte-identically."""
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
    if media is not None and media.assets:
        snapshot["media"] = [
            {"asset_id": a.id, "key": a.key}
            for a in sorted(media.assets.values(), key=lambda a: a.id)
        ]
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
    created_via: str = "compose",
    change_set: Any = None,
    kept_frames: Any = None,
    kept_reveal_onsets: Any = None,
) -> dict:
    """The PendingPlan's versioned film state after a design beat (ADR-129,
    both chat paths' design seats ride here). ``stored`` = the current
    PendingPlan (or None); ``film`` = the prepared DockStoryboard.

    - a FRESH draft (new board — first design, a feedback redraft, or an
      edit patch): version +1, a new draft token (旧 Start 失效), the
      canonical design params, the content digest, the design-time
      execution snapshot, and this turn's authorizing user message;
    - a REUSE re-presentation (fingerprint hit, no fresh feedback): the
      stored version / token / params / snapshot survive — the SAME board
      is shown again, nothing is invalidated (a token the begin beat
      cleared re-mints: the old confirmation was already voided).

    ``created_via`` = compose (default) | patch | variant — the version
    envelope's lineage (a patch additionally carries the SYSTEM-computed
    ``change_set``, never the op echo).

    ``kept_frames`` = the version's frozen cut (冻结时间轴 = 版本状态): the
    BASE version's own established per-scene frames, computed by the patch
    beat — for a keep_cut music swap AND for any timeline-preserving edit
    inheriting an established cut; None on a compose/recut/
    timeline-changing birth. ``kept_reveal_onsets`` = the frozen cut's
    other half (the reveal words' landing beats — 冻结场内切点同一继承律);
    None when the frozen cut is absent or the board carries no reveal
    scene. The Start stamp projects both onto run.context and the run
    consumes them fail-closed whenever present
    (``valid_kept_cut``/``valid_kept_reveal_onsets``).

    ``review_hold``: True sets the「只看分镜」hold, False releases it. None:
    a FRESH COMPOSE draft holds for review by default — a storyboard is a
    creation, so production never starts from a board the user has not
    seen; a PATCH/VARIANT version is born from the user's explicit
    modification request (授权已在场, ADR-134 修订) — no NEW hold, and a
    hold STANDING on the base persists across the edit (the beat never
    releases it as a side effect). The one release seat stays the user's
    explicit production request (the approval dock clears it). A REUSE
    re-presentation keeps the stored hold (that board was already seen).
    The content digest re-stamps on all paths (same input → same digest).
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
        # 首稿默认 hold ON (compose only): production never starts from a
        # board the user has not seen — the approval dock is the one release
        # seat. edit/variant versions carry their own authorization (the
        # user's explicit modification request) — NO NEW hold (ADR-134 修订);
        # a hold STANDING on the base version persists across the edit (the
        # one release seat stays the user's explicit production request —
        # the edit beat never releases it as a side effect).
        hold = (
            review_hold
            if review_hold is not None
            else (
                True
                if created_via == "compose"
                else bool(getattr(stored, "film_review_hold", False))
            )
        )
        base_version = stored_version
        via = created_via
        changes = change_set
        # The frozen cut rides ONLY a fresh version whose patch beat
        # computed one (a keep_cut swap, or a timeline-preserving edit
        # inheriting an established cut); every other birth carries None.
        # The reveal onsets are the frozen cut's other half (冻结场内切点).
        kept = kept_frames if isinstance(kept_frames, list) else None
        kept_onsets = (
            kept_reveal_onsets if isinstance(kept_reveal_onsets, list) else None
        )
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
        # The envelope survives a reuse re-presentation untouched (读容忍 —
        # legacy rows and provenance-recovered namespaces carry none).
        base_version = getattr(stored, "film_base_version", None)
        via = getattr(stored, "film_created_via", None)
        changes = getattr(stored, "film_change_set", None)
        kept = getattr(stored, "film_kept_frames", None)
        kept = kept if isinstance(kept, list) else None
        kept_onsets = getattr(stored, "film_kept_reveal_onsets", None)
        kept_onsets = kept_onsets if isinstance(kept_onsets, list) else None
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
        "film_base_version": base_version,
        "film_created_via": via,
        "film_change_set": changes,
        "film_kept_frames": kept,
        "film_kept_reveal_onsets": kept_onsets,
        # constraints_choice's write seat arrives with the layered validator
        # (L4 来源记录) — until then the envelope carries the stored value
        # verbatim (读容忍).
        "film_constraints_choice": getattr(stored, "film_constraints_choice", None),
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
            "film_text_drift": getattr(stored, "film_text_drift", None),
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
        "film_text_drift": getattr(stored, "film_text_drift", None),
    }


def film_first_draft_unpresented(stored: Any) -> bool:
    """Whether the work's FIRST board still lacks its persisted presentation.

    The first draft always owes a reviewable presentation before ANY start,
    including a same-turn auto start delegated in the opening request. The
    presentation message id is the world fact: a dock may clear review_hold,
    but it cannot manufacture that presentation. Later versions do not
    inherit this first-work review gate; their own holds still apply.
    """
    return bool(
        stored is not None
        and getattr(stored, "film_storyboard", None) is not None
        and getattr(stored, "film_storyboard_version", None) == 1
        and not getattr(stored, "film_presented_message_id", None)
    )


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
    created_via: Any = None,
    base_version: Any = None,
    change_set: Any = None,
    cut_frames: Any = None,
    cut_state: Any = None,
    cut_reveal_onsets: Any = None,
    spec_music: Any = None,
) -> Any | None:
    """One revision-base candidate's validation (pure): the board must parse
    and — when a content digest rides along — re-prove against it. Returns a
    PendingPlan-shaped namespace (``film_design_state`` reads it through the
    same getattr surface), or None when the candidate is unusable (the next
    seat is tried).

    ``cut_frames`` = the base version's OWN established cut (the frozen
    timeline's read半): its executed spec frames when a run delivered them,
    its frozen ``film_kept_frames`` when the base is itself a kept-cut
    draft, else None. ``cut_reveal_onsets`` = the cut's other half (the
    reveal words' landing beats — spec ``lead_frames`` / a kept envelope's
    frozen onsets; None on a draft cut, whose onsets the freeze seat
    computes on the draft's own grid). ``cut_state`` records the cut's
    PROVENANCE so the patch beat never mistakes one absence for another:
    ``"spec"`` (frames from a delivered run's render spec — the flex-baked
    truth), ``"kept"`` (frames from a draft envelope's frozen cut),
    ``"draft"`` (no frames; never executed — its PRESENTED plan timeline
    is the trustworthy cut), ``"unreadable"`` (no frames; the version WAS
    executed but its spec is missing/corrupt — the actual cut is
    unrecoverable and a timeline-keeping edit must refuse, never silently
    recompute a guess)."""
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
        # The version envelope rides along (读容忍 — pre-envelope rows carry
        # none): a chained patch reads its base's lineage through the same
        # surface as the live pending's.
        film_created_via=created_via if isinstance(created_via, str) else None,
        film_base_version=base_version if isinstance(base_version, int) else None,
        film_change_set=change_set if isinstance(change_set, dict) else None,
        film_cut_frames=cut_frames if isinstance(cut_frames, list) else None,
        film_cut_state=cut_state if isinstance(cut_state, str) else None,
        film_cut_reveal_onsets=(
            cut_reveal_onsets if isinstance(cut_reveal_onsets, list) else None
        ),
        # The DELIVERED render spec's music block (executed versions only —
        # the actual landed bed, vs the snapshot's design-time plan). None
        # for drafts and for an executed spec that carries no bed: the two
        # read apart through ``film_cut_state`` (spec vs unreadable), never
        # through this field alone.
        film_render_spec_music=spec_music if isinstance(spec_music, dict) else None,
        film_constraints_choice=None,
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
        mentioned = (
            await db.execute(
                select(WorkflowRun.context, Output.render_spec)
                .select_from(Output)
                .join(WorkflowStep, Output.workflow_step_id == WorkflowStep.id)
                .join(WorkflowRun, WorkflowStep.run_id == WorkflowRun.id)
                .where(Output.id == output_id, Output.project_id == project.id)
            )
        ).one_or_none()
        if mentioned is None:
            return None
        mentioned_ctx, mentioned_spec = mentioned
        if not isinstance(mentioned_ctx, dict):
            return None
        # The pinned film's cut AS RENDERED (the frozen timeline's read半).
        # A pinned output IS an executed work: a spec-less/corrupt one reads
        # as "unreadable" (the actual cut is unrecoverable — the patch beat
        # refuses a timeline-keeping edit, never recomputes a guess), never
        # as a draft's absent cut.
        cut_frames = spec_scene_frames(mentioned_spec)
        base = _film_revision_base_from_state(
            board=mentioned_ctx.get("prepared_storyboard"),
            fingerprint=mentioned_ctx.get("film_storyboard_fingerprint"),
            version=mentioned_ctx.get("film_storyboard_version"),
            params=mentioned_ctx.get("film_storyboard_params"),
            content_digest=mentioned_ctx.get("film_storyboard_content_digest"),
            execution=mentioned_ctx.get("film_execution"),
            created_via=mentioned_ctx.get("film_created_via"),
            base_version=mentioned_ctx.get("film_base_version"),
            cut_frames=cut_frames,
            cut_state="spec" if cut_frames is not None else "unreadable",
            cut_reveal_onsets=(
                spec_scene_reveal_onsets(mentioned_spec)
                if cut_frames is not None
                else None
            ),
            # The pinned output's OWN landed bed — never the live draft's
            # plan (an old Output's read never borrows the current
            # version's music).
            spec_music=(
                mentioned_spec.get("music")
                if isinstance(mentioned_spec, dict)
                else None
            ),
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
        pending_cut = pending.get("film_kept_frames")
        return _film_revision_base_from_state(
            board=pending.get("film_storyboard"),
            fingerprint=pending.get("film_storyboard_fingerprint"),
            version=pending.get("film_storyboard_version"),
            params=pending.get("film_storyboard_params"),
            content_digest=pending.get("film_storyboard_content_digest"),
            execution=pending.get("film_storyboard_execution"),
            created_via=pending.get("film_created_via"),
            base_version=pending.get("film_base_version"),
            change_set=pending.get("film_change_set"),
            # A live pending never RAN — its established cut is its frozen
            # kept frames when it is itself a frozen-cut version ("kept" —
            # the chain never loses the freeze, in-scene onsets included),
            # else it is a plain draft ("draft": its PRESENTED plan
            # timeline is the trustworthy cut).
            cut_frames=pending_cut,
            cut_state="kept" if isinstance(pending_cut, list) else "draft",
            cut_reveal_onsets=(
                pending.get("film_kept_reveal_onsets")
                if isinstance(pending_cut, list)
                else None
            ),
        )

    # Latest film run fallback: the portable read (no JSON operator — the
    # recent-run scan filters in Python) so the seat holds on every backend.
    recent = (
        (
            await db.execute(
                select(WorkflowRun.context, WorkflowRun.id)
                .where(WorkflowRun.project_id == project.id)
                .order_by(WorkflowRun.created_at.desc())
                .limit(50)
            )
        )
        .all()
    )
    for row in recent:
        ctx, run_id = row
        if not isinstance(ctx, dict) or not isinstance(ctx.get("prepared_storyboard"), dict):
            continue
        base = _film_revision_base_from_state(
            board=ctx.get("prepared_storyboard"),
            fingerprint=ctx.get("film_storyboard_fingerprint"),
            version=ctx.get("film_storyboard_version"),
            params=ctx.get("film_storyboard_params"),
            content_digest=ctx.get("film_storyboard_content_digest"),
            execution=ctx.get("film_execution"),
            created_via=ctx.get("film_created_via"),
            base_version=ctx.get("film_base_version"),
        )
        if base is None:
            continue
        # The recovered run's cut (the frozen timeline's read半).
        # Provenance matters here — no output row does NOT mean no
        # established timeline:
        # - a run that never created its film output may STILL carry the
        #   version's frozen cut in its stamped context (Start 投影的版本
        #   状态 — the run died between Start and the output's birth): the
        #   freeze persists, recover it ("kept") — never a plain-draft
        #   silent recompute;
        # - that frozen state present-but-corrupt, or a keep_cut
        #   instruction whose frames are absent (半写信封), reads as
        #   "unreadable" — the patch beat refuses a timeline-keeping edit
        #   rather than recomputing a guess;
        # - only a version with genuinely NO frozen state is draft-like
        #   ("draft": its presented plan timeline is the trustworthy cut);
        # - a delivered output whose spec is missing/corrupt is
        #   "unreadable" — the actual (flex-baked) cut is unrecoverable.
        row = (
            await db.execute(
                select(Output.render_spec)
                .select_from(Output)
                .join(WorkflowStep, Output.workflow_step_id == WorkflowStep.id)
                .where(WorkflowStep.run_id == run_id, Output.type == "film")
                .order_by(Output.created_at.desc())
                .limit(1)
            )
        ).one_or_none()
        if row is None:
            kept = ctx.get("film_kept_frames")
            if kept is not None or ctx.get("film_music_retime") == "keep_cut":
                # The board already parsed above (the candidate validated) —
                # re-prove the frozen frames against it before inheriting.
                validated = FilmStoryboard.model_validate(base.film_storyboard)
                if valid_kept_cut(validated, kept):
                    base.film_cut_frames = [int(n) for n in kept]
                    base.film_cut_state = "kept"
                    base.film_cut_reveal_onsets = (
                        ctx.get("film_kept_reveal_onsets")
                        if isinstance(ctx.get("film_kept_reveal_onsets"), list)
                        else None
                    )
                else:
                    base.film_cut_state = "unreadable"
            else:
                base.film_cut_state = "draft"
        else:
            cut_frames = spec_scene_frames(row[0])
            base.film_cut_frames = cut_frames
            base.film_cut_state = "spec" if cut_frames is not None else "unreadable"
            base.film_cut_reveal_onsets = (
                spec_scene_reveal_onsets(row[0]) if cut_frames is not None else None
            )
            # The delivered bed rides the read base too (same law as the
            # pinned seat — the landed spec's own entry).
            base.film_render_spec_music = (
                row[0].get("music") if isinstance(row[0], dict) else None
            )
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


def _is_lock_contention(exc: BaseException) -> bool:
    """True when the DBAPI failure IS the NOWAIT lock refusal (SQLSTATE
    55P03 lock_not_available / 40P01 deadlock_detected).

    asyncpg's ``LockNotAvailableError`` does NOT map to SQLAlchemy's
    ``OperationalError`` — it surfaces as a plain ``DBAPIError`` (verified
    against the live dialect, 2026-10-23 T3 crash: the designed honest
    refusal below became an 'Internal server error' because the catch
    named only ``OperationalError``). The asyncpg dialect then RE-WRAPS
    the driver error in its own translated ``Error`` (verified against the
    live wrap the same day): ``DBAPIError.orig``'s type name is ``Error``
    and ``DBAPIError.sqlstate`` is absent — the real signal lives on
    ``orig.sqlstate`` and on the ``__cause__`` chain's type names. Check
    sqlstate on both levels, then walk the cause chain."""
    for holder in (exc, getattr(exc, "orig", None)):
        if holder is not None and getattr(holder, "sqlstate", None) in (
            "55P03",
            "40P01",
        ):
            return True
    node: BaseException | None = getattr(exc, "orig", exc)
    seen: set[int] = set()
    while node is not None and id(node) not in seen:
        seen.add(id(node))
        if type(node).__name__ in ("LockNotAvailableError", "DeadlockDetectedError"):
            return True
        node = node.__cause__ or node.__context__
    return False


@dataclass(frozen=True)
class FilmDraftBegin:
    """begin_film_draft's structured outcome (拒绝原因结构化 — the callers
    never parse the observation text to learn WHY): ``draft_id`` set = the
    begin landed; ``refusal`` names the refused reason —

    - ``"in_flight"``: a LIVE committed marker names another draft (the ONE
      refusal that may be narrated as "another design is running").
    - ``"locked"``: the NOWAIT row-lock refused — the holder is UNKNOWN
      (a concurrent request's transaction; never narrated as a design).
    - ``"gone"``: the project row vanished.
    """

    draft_id: str | None = None
    refusal: str | None = None


async def begin_film_draft(
    db: AsyncSession,
    project: Project,
    *,
    base_version: int | None,
    user_message_id: str | None,
) -> FilmDraftBegin:
    """The design beat's BEGIN (并发护栏 step 1): write the in-flight marker
    + supersede the old film confirmation (``film_draft_token`` clears) in
    the marker's OWN committed mini-transaction, so the Start gate (a
    separate request's transaction) sees it DURING the long draft. Returns
    the structured begin outcome; ``refusal`` set = the begin is REFUSED.

    No fallback channel, by law: the marker is either committed through the
    side session or the beat does not start. A NOWAIT failure means the
    project row is locked — by a concurrent design's begin, by a Start's
    answer transaction, or by THIS turn's own earlier write (the flush
    below surfaces any pending write first, so an own-write reads as the
    lock it holds — the answer-continuation seam commits its input BEFORE
    the LLM turn so a legitimate continuation never meets its own lock
    here). Every one of those resolves to the same honest refusal — never
    a stale in-memory overwrite, never an uncommitted marker the Start gate
    cannot see. The publish beat's conditional check reads the COMMITTED
    marker, which is therefore always this begin's own row.

    Lock discipline: the side session locks ONLY the project row (nowait —
    it never waits behind another holder, so a second designer is refused,
    not queued); the caller's message writes stay in the turn transaction,
    so the Message → Project order is never inverted here. On success the
    turn session RE-READS the row (a plain refresh — no lock, no write) so
    its later reads see the committed marker + cleared token; the turn
    transaction never holds the project lock across the draft.
    """
    from uuid import uuid4

    from sqlalchemy.exc import DBAPIError, OperationalError

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
                return FilmDraftBegin(refusal="gone")
            pend = dict(row.pending_brief) if isinstance(row.pending_brief, dict) else {}
            if film_draft_inflight_live(pend.get("film_draft_inflight")):
                logger.info(
                    "film_draft_begin_refused",
                    project_id=str(project.id),
                    holder=(pend.get("film_draft_inflight") or {}).get("draft_id"),
                )
                return FilmDraftBegin(refusal="in_flight")
            row.pending_brief = _apply(pend)
            await session.commit()
    except OperationalError as exc:
        # Same discipline as the DBAPIError branch below: only a
        # RECOGNISED lock conflict (55P03 / 40P01) reads as contention —
        # every other OperationalError (connectivity, statement timeout,
        # …) keeps its real error category and raises.
        if not _is_lock_contention(exc):
            raise
        # The row is locked — a concurrent design / a Start / a turn whose
        # own earlier write still holds it. Refuse; NEVER fall back to an
        # uncommitted turn-transaction marker (the Start gate couldn't see
        # it and the publish check couldn't prove it).
        logger.info("film_draft_begin_contended", project_id=str(project.id))
        return FilmDraftBegin(refusal="locked")
    except DBAPIError as exc:
        # asyncpg's LockNotAvailableError lands here, not in
        # OperationalError — same contention, same honest refusal
        # (_is_lock_contention; a non-lock DBAPI failure still raises).
        if not _is_lock_contention(exc):
            raise
        logger.info("film_draft_begin_contended", project_id=str(project.id))
        return FilmDraftBegin(refusal="locked")
    # Sync the turn session's object with the committed truth (plain
    # re-read — the turn holds no lock and carries no pending write here).
    await db.refresh(project)
    return FilmDraftBegin(draft_id=draft_id)


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


async def read_committed_film_state(
    project_id: UUID,
) -> tuple[dict | None, dict | None]:
    """The patch publish beat's 并发回防 read (base 引用协议 step 4): ONE
    committed side-session SELECT returning (in-flight marker, the
    committed pending's FILM envelope — the raw pending dict when it
    carries a storyboard, else None). The publish guard mints the
    committed world's identity off this envelope through the SAME seats
    that minted the read-time reference
    (``edits.committed_film_state_identity`` — full identity: content +
    canonical params + ordered scene ids + version + frozen cut). Version
    NUMBERS or a stored content digest alone never prove identity — branch
    lineages can mint same-numbered versions, and same-content drafts can
    differ in params or frozen timeline; the digest recomputes from the
    committed board itself, so a legacy row missing the stored digest
    field still proves itself, and an unprovable envelope (missing
    board/params/version) fails closed instead of passing on a version
    number."""
    from app.models.database import AsyncSessionLocal  # deferred: worker seat

    async with AsyncSessionLocal() as session:
        pend = (
            await session.execute(
                select(Project.pending_brief).where(Project.id == project_id)
            )
        ).scalar_one_or_none()
    if not isinstance(pend, dict):
        return None, None
    marker = pend.get("film_draft_inflight")
    return (
        marker if isinstance(marker, dict) else None,
        pend if isinstance(pend.get("film_storyboard"), dict) else None,
    )


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
    from sqlalchemy.exc import DBAPIError, OperationalError

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
    except OperationalError as exc:
        # Someone else holds the row (a concurrent Start committing, a newer
        # design's begin): their transaction owns the pending plan's fate —
        # a Start's success clears pending_brief wholesale, a newer design
        # replaced the marker. Either way our marker is gone or stale; the
        # budget covers the rest. Same discipline as begin: only a
        # RECOGNISED lock conflict swallows — every other OperationalError
        # (connectivity, timeout, …) keeps its real category and raises.
        if not _is_lock_contention(exc):
            raise
    except DBAPIError as exc:
        # Same contention through asyncpg's plain-DBAPIError mapping
        # (_is_lock_contention); a non-lock DBAPI failure still raises.
        if not _is_lock_contention(exc):
            raise
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
    time) or an honest omission (the dock's music line simply stays out).

    The explicit OFF (``FILM_MUSIC_OFF``) short-circuits the WHOLE chain
    before the persona/default rungs: a bed the user switched off is a real
    terminal state, never a silent fall back to the calm default (音频三态,
    ADR-138 §7.5)."""
    if music_mood == FILM_MUSIC_OFF:
        return None
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


async def resolve_named_film_track(
    db: AsyncSession, project: Project, mood: str
) -> tuple[Music | None, list[float] | None]:
    """The patch path's music gate (the set_music op's own 校验: 曲目可解 +
    节拍网格可得): the NAMED ref itself must resolve — never the silent
    mood→brand→"calm" fallback chain (a mistyped mood must surface, not
    quietly become another track) — and the track must carry an analyzable
    beat grid (backfilled on first need, the design beat's same seat).
    (None, None) = the mood names no library track; (track, None) = the
    track's rhythm cannot be obtained."""
    from app.memory.brand import resolve_music_ref  # deferred: memory edge

    track = await resolve_music_ref(db, mood)
    if track is None:
        return None, None
    return track, await _track_beats_backfilled(db, track)


async def film_snapshot_track(
    db: AsyncSession, project: Project, params: dict
) -> Music | None:
    """The design-time execution snapshot's music resolution (ONE seat, the
    dock beat and the patch beat ride it alike): best-effort through the
    version's canonical mood chain with the beat grid backfilled; None = the
    silent-cut snapshot (a resolution failure omits the bed, never blocks
    the version — the run's own gate fails loud on a named mood)."""
    try:
        return await _resolve_track_backfilled(
            db, project, canonical_film_params(params).get("music_mood")
        )
    except Exception as e:  # noqa: BLE001 — auxiliary snapshot fact
        logger.info(
            "film_snapshot_music_failed", project_id=str(project.id), error=str(e)
        )
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
    pinned_asset_ids: list[str] | None = None,
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
    or auto-start; None means this is not a film proposal.

    ``pinned_asset_ids`` (ADR-140 发现面): the assets the user explicitly
    selected on the request (@-mentions) — forwarded to the draft seat so
    they lead the director's candidate listing (a pick beyond the print
    cap still reaches its context; tenant scoping is enforced at the
    listing seat, never by trusting the ids)."""
    fingerprint = storyboard_fingerprint(tasks, instruction)
    if fingerprint is None:
        return None
    params = _launch_film_params(tasks) or {}
    aspect = params.get("aspect") or "16:9"
    voiceover = params.get("voiceover") is not False
    # Text source (ADR-138 §7.6): the copy rides the pinned design params —
    # present = a text film (no capture wait, no pages, no web manifest).
    # verbatim's read: new versions pin it EXPLICITLY at birth
    # (film_verbatim_birth_pin) and the approval dock rewrites the task from
    # the presented version byte-for-byte, so the null→true lens below only
    # ever reads a LEGACY pre-pin version — the mode is inherited from the
    # decided version, never re-guessed from the pasted text (贴文 ≠ 逐字).
    text_source = film_text_source_from_params(params)
    music_label, music_beats, music_bpm = await _dock_music_context(
        db, project, params.get("music_mood")
    )
    if params.get("music_mood") == FILM_MUSIC_OFF:
        # Explicit OFF is a real audio state, not an omitted display fact.
        music_label = "off (no bed)"
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
            pages = (
                await load_storyboard_pages(db, project)
                if text_source is None
                else []
            )
            media = await load_storyboard_media(db, project, cached)
            return DockStoryboard(
                presentation=storyboard_presentation(
                    cached,
                    pages,
                    aspect=aspect,
                    music=music_label,
                    beats=music_beats,
                    bpm=music_bpm,
                    captions=voiceover,
                    source_note=_text_source_note(text_source),
                    media=media,
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
                text_source=text_source,
                pinned_asset_ids=pinned_asset_ids,
            )
    except TimeoutError as exc:
        logger.warning("film_dock_budget_exhausted", project_id=str(project.id),
                       budget_s=_DOCK_DRAFT_BUDGET_S)
        raise LLMError("Storyboard preparation timed out", user_key="film_storyboard_timeout") from exc
    if drafted is None:
        # Never auto-start a film whose storyboard could not be presented.
        # The failure speaks the SOURCE's context: a text film's copy
        # problem never reads as a web page's.
        raise LLMError(
            "No usable storyboard",
            user_key=(
                "film_text_ungrounded"
                if text_source is not None
                else "film_storyboard_ungrounded"
            ),
        )
    storyboard, pages = drafted
    media = await load_storyboard_media(db, project, storyboard)
    presentation = storyboard_presentation(
        storyboard,
        pages,
        aspect=aspect,
        music=music_label,
        beats=music_beats,
        bpm=music_bpm,
        captions=voiceover,
        source_note=_text_source_note(text_source),
        media=media,
    )
    # The design-time execution snapshot (ADR-129/ADR-130 §1): pages +
    # the resolved music grid + timing, digested — the run consumes THIS
    # and drift fails honestly. Best-effort music resolve (the fact sheet's
    # own best-effort law, one seat: ``film_snapshot_track``); None = the
    # silent-cut snapshot. Composite media pins (ADR-140) ride the same
    # snapshot — identity only, never probed durations.
    snap_track = await film_snapshot_track(db, project, params)
    return DockStoryboard(
        presentation=presentation,
        storyboard=storyboard.model_dump(mode="json"),
        fingerprint=fingerprint,
        execution=build_film_execution_snapshot(
            pages=pages, track=snap_track, media=media
        ),
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

    def label(self, slot: Any, ui_language: str = "en") -> str | None:
        """The Tasks row's creation-time name, source-aware (文字片不是
        官网片): a text-sourced slot names the text film; anything else
        keeps the class default. The slot tag (language/focus) still
        suffixes exactly as the base law."""
        if slot is not None and getattr(slot, "text", None):
            name = (
                "生成文字短片" if ui_language.startswith("zh") else "Generate text film"
            )
            tag = slot_tag(slot)
            return f"{name} · {tag}" if tag else name
        return super().label(slot, ui_language)

    def estimate(self, ctx: dict) -> dict | None:
        """Orchestration tokens (worst case = one storyboard pass per
        candidate, 1 + MAX_REWRITES) + the film-seconds flat item (D3 简式
        计价: ESTIMATE_FILM_SECONDS typical × the ``film.usd_per_second``
        config rate — the capture settles the storyboard's true allocated
        seconds through the same price line, hold/release absorb the
        difference).

        报价分叉 (edit 路径, R2-B): when the run is born from a VERSIONED
        board (``film_board_seconds``/``film_board_tts_chars`` ride the
        estimate facts — a confirmed compose or an edit patch), the quote
        reads the ACTUAL board seconds and the ACTUAL full narration
        characters (the interim narration policy is full re-synthesis —
        no reuse discount is ever pre-claimed before the reuse store
        exists). Facts absent (a snapshot-less birth) → the typical-film
        constants stand."""
        single = estimate_agent([1500, 8000], [400, 2000])
        n = 1 + MAX_REWRITES
        actual_seconds = ctx.get("film_board_seconds")
        seconds = (
            float(actual_seconds)
            if isinstance(actual_seconds, (int, float))
            and not isinstance(actual_seconds, bool)
            and actual_seconds > 0
            else ESTIMATE_FILM_SECONDS
        )
        actual_tts = ctx.get("film_board_tts_chars")
        tts_chars = (
            float(actual_tts)
            if isinstance(actual_tts, (int, float))
            and not isinstance(actual_tts, bool)
            else seconds * 14.0
        )
        return {
            "prompt_tokens": [single["prompt_tokens"][0] * n, single["prompt_tokens"][1] * n],
            "completion_tokens": [single["completion_tokens"][0] * n, single["completion_tokens"][1] * n],
            "units": {
                "film_seconds": seconds,
                # E2 配音: speech ≈ 14 chars/s over the estimate window
                # (voiceover is the plan default; a voiceover-off plan
                # simply captures less — hold/release absorbs). A versioned
                # board quotes its REAL narration characters instead (the
                # fork above).
                "tts_chars": tts_chars,
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

        # Text source (ADR-138 §7.6): the copy rides the pinned slot params
        # — a text film needs no captured page (the words ARE the material);
        # the page-load refusal below stays the WEB source's law. verbatim's
        # slot read: the slot carries the confirmed version's EXPLICIT birth
        # pin (film_verbatim_birth_pin → the dock's byte-for-byte rewrite);
        # the null→true lens below is the LEGACY read for pre-pin rows only
        # (贴文 ≠ 逐字 — the mode is inherited, never re-guessed here).
        text_source: FilmTextSource | None = None
        slot_text = (slot.text if slot else None) or None
        if slot_text:
            text_source = FilmTextSource(
                text=slot_text,
                verbatim=(slot.verbatim if slot else None) is not False,
                target_seconds=(slot.target_seconds if slot else None) or None,
                scene_count=(slot.scene_count if slot else None) or None,
                group_chars=_group_chars_param(
                    slot.group_chars if slot else None
                ),
            )
        text_lines = (
            build_text_manifest(text_source.text) if text_source is not None else None
        )

        # 执行契约护栏 (文字片): a run born from a version that PINNED a text
        # source must carry that source on its slot — the compiler's slot
        # projection owns the plan→step handoff. A missing text on such a run
        # is a broken execution contract (the params were lost between the
        # confirmed version and the compiled step), NEVER a missing web page:
        # fail honestly — never masquerade as a capture failure, never send
        # the user for a link. The fix is a fresh production setup from the
        # current version (the version itself stands intact).
        if text_source is None:
            version_params = ctx.get("film_storyboard_params")
            if isinstance(version_params, dict) and version_params.get("text"):
                raise ValueError(
                    "This film was confirmed as a TEXT film, but its text "
                    "never reached the production step — the plan-to-step "
                    "parameter handoff lost it. No webpage is involved; ask "
                    "me to set up production again from the current version."
                )

        pages = (
            await load_storyboard_pages(db, project) if text_source is None else []
        )
        if not pages and text_source is None:
            # The birthplace gates presence+readiness; a capture that FAILED
            # mid-wait lands here — the honest refusal (never an ungrounded
            # film).
            raise ValueError(
                "The page never became readable (the capture failed) — send the link again to re-capture it."
            )

        storyboard: FilmStoryboard | None = None
        media: StoryboardMedia | None = None
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
            # ADR-140 two-gate law at the run seat: the composite scenes'
            # media loads WITH duration probing (unknown durations probe the
            # bytes now and the truth is checked, never guessed).
            media = await load_storyboard_media(
                db, project, prepared, probe_duration=True
            )
            stale = validate_storyboard(
                prepared,
                pages,
                narration_required=voiceover,
                text_lines=text_lines,
                media=media,
            )
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

            # Media composition (ADR-140 出生面 — the run seat's fresh
            # orchestration wires the SAME discovery listing + per-candidate
            # probing loader as the design beat): gate OFF, the composite
            # vocabulary stays closed for an unattended birth too.
            media_candidates: list[dict[str, Any]] | None = None
            media_loader = None
            composite_ok = False
            media_more = 0
            if text_source is not None:
                from app.config import settings  # deferred: config leaf

                composite_ok = bool(settings.film_edits_enabled)
                if composite_ok:
                    full_candidates = await project_media_candidates(db, project)
                    media_candidates = full_candidates[:MEDIA_LISTING_CAP]
                    media_more = len(full_candidates) - len(media_candidates)

                    async def media_loader(board: FilmStoryboard) -> StoryboardMedia:
                        return await load_storyboard_media(
                            db, project, board, probe_duration=True
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
                    text_source=text_source,
                    media_candidates=media_candidates,
                    media_loader=media_loader,
                    composite_ok=composite_ok,
                    media_more=media_more,
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

        if media is None:
            # The fresh-orchestration path (or a prepared path that never
            # reached its load) resolves the composite media universe here —
            # one load seat per run, duration-probing (ADR-140 two-gate).
            media = await load_storyboard_media(
                db, project, storyboard, probe_duration=True
            )

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

        frames: list[int]  # assigned by the execution_frames seat below

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
        if track is None and music_mood and music_mood != FILM_MUSIC_OFF:
            raise ValueError(f"No music track found for mood '{music_mood}'")
        # 明确关闭 (音频三态): OFF is a real state, not a failed resolution —
        # no track, no grid, no raise; the spec simply omits the bed.

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
        # 冻结时间轴 = 版本状态 (ADR-137): a version carrying
        # ``film_kept_frames`` renders ITS frozen cut — the base version's
        # own timeline (its executed spec frames / a draft's presented plan,
        # frozen at patch time), inherited across every timeline-preserving
        # edit; the (possibly new) bed's grid is never snapped onto it. A
        # present-but-corrupt kept cut fails closed (``valid_kept_cut``),
        # and a keep_cut INSTRUCTION whose frames are absent is a
        # half-written envelope — the same honest failure; never a silent
        # re-snap. ``film_kept_reveal_onsets`` is the frozen cut's other
        # half (the reveal words' landing beats): a kept cut over a board
        # WITH reveal scenes must carry them, same fail-closed family —
        # never a silent onset re-snap onto the new grid. Absent both
        # (compose / recut / a timeline-changing patch / legacy births) =
        # allocate + snap as before.
        kept = ctx.get("film_kept_frames")
        frozen_reveal_onsets: list[int | None] | None = None
        if kept is not None or ctx.get("film_music_retime") == "keep_cut":
            if not valid_kept_cut(storyboard, kept):
                raise ValueError(
                    "The confirmed version's kept cut is missing or no longer "
                    "fits the board — ask the assistant to redesign the "
                    "storyboard and confirm the new version; the run never "
                    "silently re-snaps a cut the user approved as kept."
                )
            frames = [int(n) for n in kept]
            if any(s.type == "reveal" for s in storyboard.scenes):
                kept_onsets = ctx.get("film_kept_reveal_onsets")
                if not valid_kept_reveal_onsets(storyboard, kept_onsets, frames):
                    raise ValueError(
                        "The confirmed version's kept cut is missing its "
                        "frozen reveal timing (the word's landing beats) — "
                        "ask the assistant to redesign the storyboard and "
                        "confirm the new version; the run never silently "
                        "re-snaps an in-scene cut point the user approved "
                        "as kept."
                    )
                frozen_reveal_onsets = list(kept_onsets)
        else:
            frames = execution_frames(storyboard, beats)

        # 执行快照漂移校验 (ADR-129): the confirmed run's world must still
        # be the world the design beat froze — pages and music digest-equal
        # to the stamped snapshot. Drift fails honestly with a redesign
        # request, never a silent re-orchestration.
        if isinstance(execution_snapshot, dict) and execution_snapshot.get("digest"):
            current_digest = build_film_execution_snapshot(
                pages=pages, track=track, media=media
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
            if flex_moves and kept is not None:
                # 冻结时间轴的旁白适配冻结 (ADR-137): the frozen cut covers
                # narration too — a re-synthesized line that outruns its
                # kept window fails honestly (shorten the line or allow a
                # recut), the flex rescue never moves a cut the user
                # approved as kept.
                raise ValueError(
                    "The re-synthesized narration outruns the kept cut — "
                    "shorten the line (or allow a re-cut to the bed's grid); "
                    "a keep_cut version's scene boundaries never move."
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
            reveal_onsets=frozen_reveal_onsets,
            # 血缘只写已证 digest (ADR-129 fail-closed): the render spec /
            # output payload carry the digests THIS node recomputed and
            # proved against the stamps — never the stamped values copied
            # blind. A tampered stamp fails above and writes no provenance.
            storyboard_digest=proven_content_digest,
            execution_digest=proven_execution_digest,
            # ADR-140: the composite scenes' media universe (loaded above,
            # duration-probed) — element windows re-check against the
            # snapped frames and asset ids resolve to storage keys here.
            media=media,
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
            # One rounding rule with the read/presentation seats (0.1 + :g —
            # 29.5s never prints as "29").
            total_seconds=round(total_seconds, 1),
        )
        return [output.id]
