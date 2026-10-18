"""Pure tests for the film storyboard skeleton / assembler / validator /
allocator / spec builder.

No database, no LLM, no HTTP — StoryboardPage carriers are built in memory.
These lock the deterministic contract between the director's slot answers
(FilmDirection, ADR-127) and the render chain: the code-owned skeleton
(structure, durations, camera), citation resolution, grounding (every
factual on-screen string traces to the capture manifest; the creative
channel is exempt), camera bounds, duration intents, content caps, and the
frame allocator's structural floors.
"""

from __future__ import annotations

import pytest

from app.models.schemas import FilmStoryboard, PageElement, ShotRef, WebPageResearch
from app.tools.film.storyboard import (
    CONSTRAINT_VIOLATION,
    DURATION_INVALID,
    EMPTY_CHAPTER,
    FILM_FPS,
    FILM_MAX_FRAMES,
    INVALID_COPY_REF,
    INVALID_FOCUS,
    NARRATION_KEY_UNKNOWN,
    NARRATION_MISSING,
    PADDING_SCENE,
    REPEATED_VIEW,
    SCENE_COUNT_LIMITS,
    SCENE_SECONDS,
    TEXT_NOT_GROUNDED,
    TOTAL_SECONDS_RANGE,
    DockStoryboard,
    FilmDirection,
    FilmStoryboardRejected,
    StoryboardPage,
    allocate_frames,
    assemble_storyboard,
    build_film_execution_snapshot,
    build_film_spec,
    build_line_manifest,
    build_skeleton,
    film_design_state,
    fixed_direction,
    format_violations,
    narration_caption_cues,
    resolve_film_dock_state,
    skeleton_prompt_dict,
    snap_frames_to_beats,
    storyboard_fingerprint,
    storyboard_presentation,
    validate_storyboard,
)

URL = "https://example.com/product"


def _page(
    *,
    title: str = "Acme — Ship faster",
    description: str = "Acme turns hours of release work into minutes.",
    h1: list[str] | None = None,
    h2: list[str] | None = None,
    buttons: list[str] | None = None,
    screenshot: str | None = "user/capture/shot.png",
    shots: tuple = (),
) -> StoryboardPage:
    research = WebPageResearch(
        url=URL,
        title=title,
        description=description,
        h1=h1 or ["Ship faster"],
        h2=h2 if h2 is not None else ["Why teams switch"],
        h3=[],
        buttons=buttons or ["Start free"],
        links=["Docs"],
    )
    return StoryboardPage(
        asset_id="a1", research=research, screenshot_key=screenshot,
        host="example.com", shots=shots,
    )


def _storyboard(scenes: list[dict], **kw) -> FilmStoryboard:
    return FilmStoryboard.model_validate({"scenes": scenes, **kw})


def _good_scenes() -> list[dict]:
    return [
        {"type": "hero", "seconds": 3.0, "word": "Ship faster", "sub": "Acme turns hours of release work into minutes."},
        {"type": "ui", "seconds": 9.0, "page": 0,
         "focuses": [{"at": 0.0, "x": 0.5, "y": 0.5, "zoom": 1.0},
                     {"at": 2.0, "x": 0.3, "y": 0.4, "zoom": 2.0}],
},
        {"type": "words", "seconds": 3.0, "dark": False, "lines": ["Ship faster"]},
        {"type": "divider", "seconds": 3.0, "label": "Why teams switch",
         "roll": ["Ship faster", "Start free"]},
        {"type": "ui", "seconds": 9.0, "page": 0, "frame": False,
         "focuses": [{"at": 0.0, "x": 0.5, "y": 0.5, "zoom": 1.0}],
},
        {"type": "end", "seconds": 4.0, "name": "Acme", "tagline": "Ship faster"},
    ]


def _codes(violations) -> set[str]:
    return {v.code for v in violations}


# Compliant filler boards (ADR-127 contract window: 8..20 scenes, 70..118s)
# — appended to focused test boards so the validator's global gates stay
# silent and each test's own point remains the only signal. Distinct
# signatures throughout; filler is words/hero/reveal/end only — a filler
# divider would need its own walk (EMPTY_CHAPTER), and words lines are the
# creative channel (grounding-exempt), the cheapest legal filler.
_PAD_SCENES: list[dict] = [
    {"type": "words", "seconds": 4.0, "dark": True, "lines": ["pad one"]},
    {"type": "words", "seconds": 4.0, "dark": False, "lines": ["pad two"]},
    {"type": "words", "seconds": 4.0, "dark": True, "lines": ["pad three"]},
    {"type": "reveal", "seconds": 9.0, "lead": "One more thing.", "word": "Acme", "sub": "Start free"},
    {"type": "hero", "seconds": 6.0, "word": "Acme", "sub": "Why teams switch"},
    {"type": "end", "seconds": 6.0, "name": "Acme", "tagline": "Why teams switch"},
    {"type": "words", "seconds": 4.0, "dark": True, "lines": ["pad four"]},
    {"type": "words", "seconds": 4.0, "dark": False, "lines": ["pad five"]},
]


def _pad(scenes: list[dict]) -> list[dict]:
    """Bring a focused test board into the contract window with filler."""
    return scenes + [dict(s) for s in _PAD_SCENES]


# ---- grounding ---------------------------------------------------------------


def test_clean_storyboard_passes():
    assert validate_storyboard(_storyboard(_pad(_good_scenes())), [_page()]) == []


def test_verbatim_quote_and_trim_hit():
    scenes = [
        # exact H1
        {"type": "words", "seconds": 3.5, "dark": False, "lines": ["Ship faster"]},
        # a trim of the description (leading words dropped)
        {"type": "words", "seconds": 3.5, "dark": True, "lines": ["release work into minutes"]},
        {"type": "hero", "seconds": 5.0, "word": "Acme", "sub": "Start free"},
        {"type": "ui", "seconds": 9.0, "page": 0,
         "focuses": [{"at": 0.0, "x": 0.5, "y": 0.5, "zoom": 1.0}]},
        {"type": "divider", "seconds": 5.0, "label": "Why teams switch", "roll": ["Start free"]},
        # the chapter's walk (EMPTY_CHAPTER law: a divider needs one)
        {"type": "ui", "seconds": 4.0, "page": 0, "frame": False,
         "focuses": [{"at": 0.0, "x": 0.5, "y": 0.5, "zoom": 1.0}]},
        {"type": "end", "seconds": 5.0, "name": "Acme", "tagline": "Ship faster"},
    ]
    assert validate_storyboard(_storyboard(_pad(scenes)), [_page()]) == []


def test_emphasis_marks_and_case_are_normalized():
    scenes = [
        {"type": "hero", "seconds": 4.0, "word": "*Ship* faster!", "sub": "ACME"},
        {"type": "words", "seconds": 4.0, "dark": False, "lines": ["ship faster"]},
        {"type": "ui", "seconds": 9.0, "page": 0,
         "focuses": [{"at": 0.0, "x": 0.5, "y": 0.5, "zoom": 1.0}]},
        {"type": "divider", "seconds": 4.0, "label": "WHY TEAMS SWITCH", "roll": ["Start Free"]},
        # the chapter's walk (EMPTY_CHAPTER law: a divider needs one)
        {"type": "ui", "seconds": 4.0, "page": 0, "frame": False,
         "focuses": [{"at": 0.0, "x": 0.5, "y": 0.5, "zoom": 1.0}]},
        {"type": "words", "seconds": 4.0, "dark": True, "lines": ["Release work"]},
        {"type": "end", "seconds": 5.0, "name": "Acme", "tagline": "Start free"},
    ]
    assert validate_storyboard(_storyboard(_pad(scenes)), [_page()]) == []


def test_invented_copy_rejected():
    scenes = _good_scenes()
    scenes[0]["sub"] = "The number one platform loved by millions."
    violations = validate_storyboard(_storyboard(scenes), [_page()])
    assert TEXT_NOT_GROUNDED in _codes(violations)


def test_grounding_rejection_carries_nearest_manifest_lines():
    """The repair echo's menu (2026-10-16): a rejected line names its nearest
    quotable candidates, so the rewrite picks instead of re-inventing."""
    scenes = _good_scenes()
    scenes[0]["sub"] = "Ship faster with your team"  # near "Ship faster"
    violations = validate_storyboard(_storyboard(scenes), [_page()])
    detail = next(v.detail for v in violations if v.code == TEXT_NOT_GROUNDED)
    assert "closest manifest lines:" in detail
    assert "Ship faster" in detail

    scenes = _good_scenes()
    scenes[0]["sub"] = "zzz qqq unrelated gibberish 12345"
    violations = validate_storyboard(_storyboard(scenes), [_page()])
    detail = next(v.detail for v in violations if v.code == TEXT_NOT_GROUNDED)
    assert "closest manifest lines:" not in detail  # 无近邻 = 零噪音


# ---- Batch 2 quality gates ---------------------------------------------------


def test_empty_chapter_rejected():
    """A chapter card no page walk follows (up to the next structural
    scene) is padding dressed as structure — a hard, attributable failure.
    A plate BETWEEN the card and the walk stays legal (the arc's order)."""
    scenes = _good_scenes()
    scenes[4] = {"type": "words", "seconds": 4.0, "dark": False, "lines": ["filler beat"]}
    violations = validate_storyboard(_storyboard(scenes), [_page()])
    assert EMPTY_CHAPTER in _codes(violations)
    detail = next(v.detail for v in violations if v.code == EMPTY_CHAPTER)
    assert "chapter 1" in detail and "fewer pillars" in detail
    # Plate between card and walk: the chapter still has its walk.
    scenes = _good_scenes()
    scenes.insert(4, _plate_scene())
    assert EMPTY_CHAPTER not in _codes(validate_storyboard(_storyboard(scenes), [_page()]))


def test_repeated_web_shot_rejected():
    """The same captured image with the SAME presentation twice is a
    repeated web shot — keyed on the image, not the shot index. The walk's
    frame-alternation rhythm (one browser-carded, one full-bleed) stays
    legal, and so do two genuinely different views."""
    # same image, same frame → repeat
    scenes = _good_scenes()
    scenes[4]["frame"] = True
    assert REPEATED_VIEW in _codes(validate_storyboard(_storyboard(scenes), [_page()]))
    # same image, alternating presentation → the deliberate rhythm
    scenes = _good_scenes()
    assert REPEATED_VIEW not in _codes(validate_storyboard(_storyboard(_pad(scenes)), [_page()]))
    # two shot slots pointing at the same stored image: same pixels repeat
    shots = (
        ShotRef(key="user/capture/a.png", y=0, heading="(top)"),
        ShotRef(key="user/capture/a.png", y=1400, heading="(top)"),
    )
    page = _page(shots=shots)
    scenes = _good_scenes()
    scenes[4]["shot"] = 1
    scenes[4]["frame"] = True
    violations = validate_storyboard(_storyboard(scenes), [page])
    assert REPEATED_VIEW in _codes(violations)
    detail = next(v.detail for v in violations if v.code == REPEATED_VIEW)
    assert "scene[1]" in detail and "user/capture/a.png" in detail


def test_padding_scene_static_shot_rejected():
    """Defense in depth: a ui scene with zero camera beats (the schema's
    min_length=1 bars this on the parsed path — a hand-built board can
    still try) is a static padding shot."""
    parsed = FilmStoryboard.model_validate({"scenes": _good_scenes()})
    scenes = list(parsed.scenes)
    scenes[1] = scenes[1].model_copy(update={"focuses": []})
    board = FilmStoryboard.model_construct(name=None, theme=None, scenes=scenes)
    assert PADDING_SCENE in _codes(validate_storyboard(board, [_page()]))


def test_adjacent_near_repeat_is_padding():
    """Two adjacent same-type beats saying nearly the same thing = padding;
    the deliberate cross-type callback (hero word echoing in the end
    tagline) is untouched."""
    scenes = [
        {"type": "words", "seconds": 3.0, "dark": True, "lines": ["Ship faster"]},
        {"type": "words", "seconds": 3.0, "dark": False, "lines": ["Ship faster!"]},
    ]
    assert PADDING_SCENE in _codes(validate_storyboard(_storyboard(scenes), [_page()]))
    scenes[1]["lines"] = ["something else entirely"]
    assert PADDING_SCENE not in _codes(validate_storyboard(_storyboard(scenes), [_page()]))


def test_narration_cap_is_cjk_aware():
    """The design-time fit law is calibrated to the REAL synthesized rate:
    13 latin units/s at natural speed (a CJK glyph = one syllable = 4
    units), so a passing line reads at 1.0× and the synthesis speed ladder
    (≤1.35×) stays headroom for voice variance — never the plan. The 3s
    hero scene's cap = max(38, int(3.0*13)) = 39 units."""
    scenes = _good_scenes()
    scenes[0]["narration"] = "这" * 20  # 80 units over the 39-unit cap
    violations = validate_storyboard(_storyboard(_pad(scenes)), [_page()])
    assert any("speech units" in v.detail for v in violations)
    scenes[0]["narration"] = "这" * 9  # 36 units — reads at natural speed
    assert validate_storyboard(_storyboard(_pad(scenes)), [_page()]) == []
    # The 40–60 latin-unit band in a 3s scene only fits through the speed
    # ladder (or fails synthesis outright) — the design law rejects it so
    # the bounded rewrite shortens the line before any synthesis runs.
    scenes[0]["narration"] = "a" * 40
    assert any(
        "speech units" in v.detail
        for v in validate_storyboard(_storyboard(_pad(scenes)), [_page()])
    )


def test_caption_cues_split_latin_sentences_never_decimals():
    """The full stop ends a cue only when it ends a SENTENCE (whitespace or
    string end after it) — decimals and version strings survive intact."""
    cues = narration_caption_cues("Version 2.4 ships today.", window_s=5.0, spoken_s=4.0)
    assert [c["text"] for c in cues] == ["Version 2.4 ships today."]
    cues = narration_caption_cues("First line. Second line.", window_s=8.0, spoken_s=6.0)
    assert [c["text"] for c in cues] == ["First line.", "Second line."]
    assert cues[-1]["end"] == 6.0


def test_presentation_facts_carry_role_source_camera_and_verbatim_narration():
    """The LLM-facing fact sheet (2026-10-18 裁决 — 工具产生真实分镜, the
    chat model is the board's ONE voice): every scene row names its arc
    role, what the viewer sees, the camera's RESOLVED target (never a raw
    DOM id), and the verbatim narration; silent scenes say so. Sources
    compact — each page named once, never line-id spam."""
    pages = [_film_page()]
    lines = build_line_manifest(pages)
    skeleton = build_skeleton(pages, lines)
    resolved, violations = assemble_storyboard(skeleton, _direction(), lines)
    assert violations == [] and resolved is not None
    facts = storyboard_presentation(
        resolved,
        pages,
        aspect="16:9",
        music="calm — Bed · 120 BPM",
        beats=[i * 0.5 for i in range(240)],
        bpm=120,
        captions=True,
    )
    assert 'sources: example.com/product "Acme — Ship faster"' in facts
    for role in (
        "cold open", "brand hero", "home walk",
        "chapter 1 card", "chapter 1 walk", "chapter 3 walk",
        "reveal", "closing card",
    ):
        assert role in facts
    assert "shows:" in facts
    assert 'camera: wide → push to "Section 1" (heading)' in facts
    assert 'narration: "This is Acme."' in facts
    assert "narration: (silent" in facts
    # Internal markers never leak: no line ids, no DOM ids.
    assert "L3" not in facts and "s1e0" not in facts


# ---- the skeleton + assembly (ADR-127) ---------------------------------------
#
# The default _page()'s line manifest (1-based, kind order title →
# description → h1 → h2 → button → link):
#   L1 [title] Acme — Ship faster
#   L2 [description] Acme turns hours of release work into minutes.
#   L3 [h1] Ship faster
#   L4 [h2] Why teams switch
#   L5 [button] Start free
#   L6 [link] Docs


def _film_shots(n: int = 4) -> tuple:
    return tuple(
        ShotRef(
            key=f"user/capture/a-s{i}.png",
            y=i * 1200,
            heading="(top)" if i == 0 else f"Section {i}",
            elements=[
                PageElement(
                    id=f"s{i}e0", kind="heading", text=f"Section {i}",
                    x=0.5, y=0.4, w=0.6, h=0.2,
                )
            ],
        )
        for i in range(n)
    )


def _film_page(**kw) -> StoryboardPage:
    """A page with the full section-shot capture (ADR-121 B1) — the world
    the skeleton preflight accepts (≥3 usable views)."""
    kw.setdefault("shots", _film_shots())
    return _page(**kw)


def _direction(**over) -> FilmDirection:
    d: dict = {
        "pillars": [{"line": 4}, {"line": 5}, {"line": 6}],
        "hero_word": {"line": 3},
        "hero_sub": {"line": 2},
        "cold_open": ["Ship less"],
        "reveal_word": {"line": 4},
        "reveal_sub": {"line": 5},
        "end_name": {"line": 1},
        "end_tagline": {"line": 3},
        "narrations": {"hero": "This is Acme.", "end": "Start today."},
    }
    d.update(over)
    return FilmDirection.model_validate(d)


def _assemble_with(pages, direction=None, **over):
    lines = build_line_manifest(pages)
    skeleton = build_skeleton(pages, lines)
    return assemble_storyboard(
        skeleton, direction or _direction(**over), lines
    )


def test_skeleton_views_focuses_and_plate_verdict():
    pages = [_film_page()]
    lines = build_line_manifest(pages)
    skeleton = build_skeleton(pages, lines)
    assert skeleton.views == ((0, 0), (0, 1), (0, 2), (0, 3))
    # Each view's camera names the shot's heading element (never coordinates).
    assert skeleton.focuses[(0, 1)].element == "s1e0"
    # No number-ish lines in the default manifest → no plate.
    assert skeleton.plate_lines == ()
    # A fold-only page (pre-B1) still contributes its fold view, with the
    # raw center push-in (no element inventory).
    fold_only = build_skeleton([_page()], build_line_manifest([_page()]))
    assert fold_only.views == ((0, 0),)
    assert fold_only.focuses[(0, 0)].element is None


def test_assemble_clean_direction_passes():
    pages = [_film_page()]
    resolved, violations = _assemble_with(pages)
    assert violations == []
    assert resolved is not None
    # The fixed arc, 3 chapters, views consumed in order (the 4-view world
    # walks home + 3 chapters; the proof walk drops honestly).
    keys = [(s.type, getattr(s, "shot", None)) for s in resolved.scenes]
    assert [k for k, _ in keys] == [
        "words", "hero", "ui",
        "divider", "ui", "divider", "ui", "divider", "ui",
        "reveal", "end",
    ]
    assert [s for t, s in keys if t == "ui"] == [0, 1, 2, 3]
    hero = resolved.scenes[1]
    assert hero.word == "Ship faster"
    assert hero.sub == "Acme turns hours of release work into minutes."
    # Narration lands by scene key; unnarrated scenes read None.
    assert hero.narration == "This is Acme."
    assert resolved.scenes[0].narration is None
    # The walk alternates browser-card and full-bleed (code's rhythm).
    assert [s.frame for s in resolved.scenes if s.type == "ui"] == [True, False, True, False]
    # The divider roll ends on the real chapter word, decoys first.
    divider = resolved.scenes[3]
    assert divider.label == "Chapter"
    assert divider.roll[-1] == "Why teams switch"
    assert len(divider.roll) == 3
    # Durations: every scene in its band, the total in the skill's window.
    assert all(
        SCENE_SECONDS[s.type][0] <= s.seconds <= SCENE_SECONDS[s.type][1]
        for s in resolved.scenes
    )
    total = sum(s.seconds for s in resolved.scenes)
    assert TOTAL_SECONDS_RANGE[0] <= total <= TOTAL_SECONDS_RANGE[1]
    # The resolved board passes the validator by construction.
    assert validate_storyboard(resolved, pages) == []


def test_plate_follows_the_chapter_that_proved_the_numbers():
    """The plate hangs off the chapter whose PAGE carries the number-ish
    lines (the reference arc plates the chapter that proved them) — never
    blindly chapter 1. Layout: page 0 has 2 views (home walk + chapter 1),
    page 1 has 2 views (chapters 2-3) and the numbers → plate after ch2."""
    p0 = _film_page(shots=_film_shots(2))
    p1 = _film_page(
        title="Pricing — Acme",
        h2=["256B envelope encryption", "40 apps a month"],
        shots=_film_shots(2),
    )
    pages = [p0, p1]
    lines = build_line_manifest(pages)
    skeleton = build_skeleton(pages, lines)
    assert skeleton.plate_page == 1
    resolved, violations = _assemble_with(pages)
    assert violations == []
    assert resolved is not None
    types = [s.type for s in resolved.scenes]
    assert types == [
        "words", "hero", "ui",
        "divider", "ui", "divider", "ui", "plate", "divider", "ui",
        "reveal", "end",
    ]
    plate = next(s for s in resolved.scenes if s.type == "plate")
    assert [(c.big, c.label) for c in plate.cards] == [
        ("256B", "envelope encryption"),
        ("40", "apps a month"),
    ]
    # Numbers on chapter 1's page keep the chapter-1 placement.
    p_num = _film_page(h2=["99% uptime guaranteed", "3 steps total"], shots=_film_shots(2))
    resolved1, violations1 = _assemble_with([p_num, _film_page(shots=_film_shots(2))])
    assert violations1 == []
    assert resolved1 is not None
    assert [s.type for s in resolved1.scenes] == [
        "words", "hero", "ui",
        "divider", "ui", "plate", "divider", "ui", "divider", "ui",
        "reveal", "end",
    ]


def test_assemble_fit_trims_at_word_boundary():
    pages = [_film_page()]
    lines = build_line_manifest(pages)
    long_line = lines[1].text  # the 46-char description (over the 20 cap)
    resolved, violations = _assemble_with(
        pages, hero_word={"line": 2, "fit": "head"},
    )
    assert violations == []
    assert resolved is not None
    word = next(s for s in resolved.scenes if s.type == "hero").word
    assert len(word) <= 20 and long_line.startswith(word) and not word.endswith(" ")
    tail, violations = _assemble_with(pages, hero_word={"line": 2, "fit": "tail"})
    assert violations == []
    assert tail is not None
    hero = next(s for s in tail.scenes if s.type == "hero")
    assert len(hero.word) <= 20 and long_line.endswith(hero.word)


def test_assemble_full_fit_over_cap_surfaces_as_constraint_violation():
    pages = [_film_page()]
    resolved, violations = _assemble_with(pages, hero_sub={"line": 2})  # full fit, ≤90: fine
    assert violations == []
    assert resolved is not None
    # The end name cap is 30 — the 20-char title fits; force an over-cap via
    # the reveal word (cap 30, the 46-char description with a full fit).
    resolved, violations = _assemble_with(pages, reveal_word={"line": 2})
    assert violations == []  # resolution is honest; the cap gate is validate's
    assert resolved is not None
    assert CONSTRAINT_VIOLATION in _codes(validate_storyboard(resolved, pages))


def test_assemble_accent_wraps_and_missing_accent_rejected():
    pages = [_film_page()]
    resolved, violations = _assemble_with(
        pages, hero_word={"line": 3, "accent": "Ship"}
    )
    assert violations == []
    assert resolved is not None
    hero = next(s for s in resolved.scenes if s.type == "hero")
    assert hero.word == "*Ship* faster"

    _, violations = _assemble_with(pages, hero_word={"line": 3, "accent": "zebras"})
    assert INVALID_COPY_REF in _codes(violations)


def test_assemble_unknown_line_rejected():
    pages = [
        _film_page(),
        _page(title="Beta — Docs", description="Read the manual.",
              h1=["Documentation"], h2=["Reference"], buttons=["Download"],
              screenshot="user/capture/b.png"),
    ]
    _, violations = _assemble_with(pages, hero_word={"line": 999})
    assert INVALID_COPY_REF in _codes(violations)


def test_creative_slots_are_grounding_exempt_but_capped():
    pages = [_film_page()]
    # A wholly invented hook is the creative channel — no grounding check.
    resolved, violations = _assemble_with(
        pages, cold_open=["Nobody wrote this hook"]
    )
    assert violations == []
    assert resolved is not None
    assert validate_storyboard(resolved, pages) == []
    # …but caps and the blank law still apply, at assembly and at validate.
    _, violations = _assemble_with(pages, cold_open=["x" * 37])
    assert CONSTRAINT_VIOLATION in _codes(violations)
    _, violations = _assemble_with(pages, cold_open=["   "])
    assert CONSTRAINT_VIOLATION in _codes(violations)
    # The reveal lead is creative too (null → the code phrase).
    resolved, _ = _assemble_with(pages, reveal_lead=None)
    assert resolved is not None
    reveal = next(s for s in resolved.scenes if s.type == "reveal")
    assert reveal.lead == "One more thing."
    resolved, _ = _assemble_with(pages, reveal_lead="Wait for it.")
    assert resolved is not None
    reveal = next(s for s in resolved.scenes if s.type == "reveal")
    assert reveal.lead == "Wait for it."
    assert validate_storyboard(resolved, pages) == []


def test_fixed_direction_full_path_validates_clean():
    """The no-LLM terminal (固定分镜): code fills every slot from the
    manifest's own semantics; the assembled board passes the validator."""
    pages = [_film_page()]
    lines = build_line_manifest(pages)
    skeleton = build_skeleton(pages, lines)
    direction = fixed_direction(lines)
    assert direction is not None
    resolved, violations = assemble_storyboard(skeleton, direction, lines)
    assert violations == []
    assert resolved is not None
    assert validate_storyboard(resolved, pages) == []
    hero = next(s for s in resolved.scenes if s.type == "hero")
    assert hero.word  # resolved from the title line
    # 填全槽含配音 (2026-10-17 取证锁): the fallback must NOT ship a silent
    # film — voiceover was promised in the review; hero/walks/end speak the
    # site's own cited lines (60-char cap fits the shortest scene window).
    narrated = {s.type for s in resolved.scenes if getattr(s, "narration", None)}
    assert {"hero", "ui", "end"} <= narrated
    assert all(
        len(s.narration) <= 60
        for s in resolved.scenes
        if getattr(s, "narration", None)
    )
    # A manifest too thin for three chapters fails honestly (None).
    bare = StoryboardPage(
        asset_id="a9",
        research=WebPageResearch(
            url=URL, title="Solo", description="", h1=[], h2=[], h3=[],
            buttons=[], links=[], paragraphs=[],
        ),
        screenshot_key="k", host="example.com",
    )
    assert fixed_direction(build_line_manifest([bare])) is None


def test_skeleton_prompt_dict_is_the_answer_sheet():
    pages = [_film_page()]
    lines = build_line_manifest(pages)
    skeleton = build_skeleton(pages, lines)
    block = skeleton_prompt_dict(skeleton, pages)
    keys = [s["key"] for s in block["scenes"]]
    assert keys[0] == "open" and keys[-1] == "end"
    assert "ch5_divider" in keys  # the maximal arc (chapters 4-5 trim at assembly)
    # Durations are never printed — a printed number reads as a writable slot.
    assert all("seconds" not in s for s in block["scenes"])
    home = next(s for s in block["scenes"] if s["key"] == "home")
    assert home["camera"] == {"element": "s0e0"}


# ---- camera bounds -----------------------------------------------------------


def test_focus_out_of_bounds_rejected():
    scenes = _good_scenes()
    scenes[1]["focuses"] = [{"at": 0.0, "x": 1.4, "y": 0.5, "zoom": 1.0}]
    assert INVALID_FOCUS in _codes(validate_storyboard(_storyboard(scenes), [_page()]))


def test_zoom_bounds():
    scenes = _good_scenes()
    scenes[1]["focuses"] = [{"at": 0.0, "x": 0.5, "y": 0.5, "zoom": 0.5}]
    assert INVALID_FOCUS in _codes(validate_storyboard(_storyboard(scenes), [_page()]))
    scenes[1]["focuses"] = [{"at": 0.0, "x": 0.5, "y": 0.5, "zoom": 5.0}]
    assert INVALID_FOCUS in _codes(validate_storyboard(_storyboard(scenes), [_page()]))


def test_focus_at_must_ascend_within_scene():
    scenes = _good_scenes()
    scenes[1]["focuses"] = [
        {"at": 3.0, "x": 0.5, "y": 0.5, "zoom": 1.0},
        {"at": 1.0, "x": 0.5, "y": 0.5, "zoom": 1.0},
    ]
    assert INVALID_FOCUS in _codes(validate_storyboard(_storyboard(scenes), [_page()]))


def test_focus_at_beyond_scene_seconds_rejected():
    scenes = _good_scenes()
    scenes[1]["focuses"] = [{"at": 9.5, "x": 0.5, "y": 0.5, "zoom": 1.0}]  # scene is 9s: at must be < 9
    assert INVALID_FOCUS in _codes(validate_storyboard(_storyboard(scenes), [_page()]))


# ---- durations / counts ------------------------------------------------------


def test_scene_seconds_out_of_range():
    scenes = _good_scenes()
    scenes[0]["seconds"] = 9.0  # hero cap is 6
    assert DURATION_INVALID in _codes(validate_storyboard(_storyboard(scenes), [_page()]))


def test_total_seconds_window():
    # a single 1.5s words scene is under the 70s total floor (and the count
    # floor — the duration violation is what we assert)
    scenes = [{"type": "words", "seconds": 1.5, "dark": False, "lines": ["Ship faster"]}]
    violations = validate_storyboard(_storyboard(scenes), [_page()])
    assert DURATION_INVALID in _codes(violations)


def test_scene_count_window():
    two = _good_scenes()[:2]
    assert CONSTRAINT_VIOLATION in _codes(validate_storyboard(_storyboard(two), [_page()]))
    too_many = _good_scenes() + [
        {"type": "words", "seconds": 2.0, "dark": False, "lines": [f"Ship faster {i}"]}
        for i in range(SCENE_COUNT_LIMITS[1] - len(_good_scenes()) + 1)
    ]
    # over the 20-scene ceiling — the count violation is what we assert
    assert len(too_many) > SCENE_COUNT_LIMITS[1]
    assert CONSTRAINT_VIOLATION in _codes(validate_storyboard(_storyboard(too_many), [_page()]))


def test_char_caps_and_list_caps():
    scenes = _good_scenes()
    scenes[0]["word"] = "Ship faster plus padding"  # hero.word cap 16 — also ungrounded
    violations = validate_storyboard(_storyboard(scenes), [_page()])
    assert CONSTRAINT_VIOLATION in _codes(violations)

    scenes = _good_scenes()
    scenes[1]["focuses"] = [
        {"at": float(i), "x": 0.5, "y": 0.5, "zoom": 1.0} for i in range(6)
    ]
    assert CONSTRAINT_VIOLATION in _codes(validate_storyboard(_storyboard(scenes), [_page()]))


def test_duplicate_copy_within_scene_rejected():
    scenes = _good_scenes()
    scenes[0] = {"type": "words", "seconds": 2.5, "dark": False,
                 "lines": ["Ship faster", "ship  faster"]}  # same after normalize
    assert CONSTRAINT_VIOLATION in _codes(validate_storyboard(_storyboard(scenes), [_page()]))


def test_whole_scene_duplicated_rejected():
    scenes = _good_scenes()
    scenes.insert(1, dict(scenes[0]))
    assert CONSTRAINT_VIOLATION in _codes(validate_storyboard(_storyboard(scenes), [_page()]))


def test_cross_scene_callback_allowed():
    """The spike's shape: the hero's word echoing in the end tagline is a
    deliberate callback, not a duplicate (different scene types / strings)."""
    scenes = _good_scenes()
    scenes[5]["tagline"] = "Ship faster"  # == hero.word, different slot/scene
    assert validate_storyboard(_storyboard(_pad(scenes)), [_page()]) == []


def test_empty_after_normalize_rejected():
    scenes = _good_scenes()
    scenes[0]["word"] = "***"
    violations = validate_storyboard(_storyboard(scenes), [_page()])
    assert CONSTRAINT_VIOLATION in _codes(violations)


def test_bad_theme_hex_rejected():
    violations = validate_storyboard(
        _storyboard(_good_scenes(), theme={"canvas": "white", "ink": "#141414"}),
        [_page()],
    )
    assert CONSTRAINT_VIOLATION in _codes(violations)


def test_ui_scene_needs_a_page_with_screenshot():
    page = _page(screenshot=None)
    scenes = _good_scenes()
    violations = validate_storyboard(_storyboard(scenes), [page])
    assert CONSTRAINT_VIOLATION in _codes(violations)
    scenes[1]["page"] = 7  # no such page
    violations = validate_storyboard(_storyboard(scenes), [_page()])
    assert CONSTRAINT_VIOLATION in _codes(violations)


def test_ui_scene_shot_bounds():
    """ADR-121 B1: the shot picks which captured view the ui scene shows —
    bounds are the validator's seat (out-of-range / fold-only misuse both
    reject; a legal section shot passes and projects into the spec image)."""
    shots = (
        ShotRef(key="user/capture/a.png", y=0, heading="(top)"),
        ShotRef(key="user/capture/a-s1.png", y=1400, heading="Why teams switch"),
    )
    page = _page(shots=shots)
    scenes = _good_scenes()
    scenes[1]["shot"] = 1
    assert validate_storyboard(_storyboard(_pad(scenes)), [page]) == []
    spec = build_film_spec(_storyboard(scenes), [page])
    assert spec["scenes"][1]["image"] == "user/capture/a-s1.png"
    # out of range
    scenes[1]["shot"] = 5
    assert CONSTRAINT_VIOLATION in _codes(validate_storyboard(_storyboard(scenes), [page]))
    # fold-only page (pre-B1 rows): shot must stay 0
    scenes[1]["shot"] = 1
    assert CONSTRAINT_VIOLATION in _codes(validate_storyboard(_storyboard(scenes), [_page()]))


def test_ui_focus_element_form():
    """ADR-121 B2: focuses name element ids — the spec builder resolves
    coordinates deterministically; mixed / unknown / covered forms reject."""
    elts = [
        PageElement(id="s1e0", kind="heading", text="Why teams switch", x=0.2, y=0.3, w=0.5, h=0.2),
        PageElement(id="s1e1", kind="button", text="Start free", x=0.8, y=0.7, w=0.1, h=0.05),
        PageElement(id="s1e2", kind="text", text="hidden note", x=0.5, y=0.5, w=0.3, h=0.1, covered=True),
    ]
    shots = (
        ShotRef(key="user/capture/a.png", y=0, heading="(top)"),
        ShotRef(key="user/capture/a-s1.png", y=1400, heading="Why teams switch", elements=elts),
    )
    page = _page(shots=shots)
    scenes = _good_scenes()
    scenes[1]["shot"] = 1
    scenes[1]["focuses"] = [{"at": 0.0, "element": "s1e0"}, {"at": 2.0, "element": "s1e1"}]
    assert validate_storyboard(_storyboard(_pad(scenes)), [page]) == []
    spec = build_film_spec(_storyboard(scenes), [page])
    focuses = spec["scenes"][1]["focuses"]
    assert focuses[0] == {"at": 0.0, "x": 0.2, "y": 0.3, "zoom": 1.2}  # 0.5/0.5 → clamp up
    assert any(f["x"] == 0.8 and f["zoom"] == 2.6 for f in focuses)  # 0.5/0.1 → clamp down
    assert focuses[-1]["at"] == 9.0 and focuses[-1]["zoom"] > focuses[-2]["zoom"]
    assert "element" not in focuses[0]  # never leaks into the render contract
    scenes[1]["focuses"] = [{"at": 0.0, "element": "s1e9"}]  # unknown id
    assert INVALID_FOCUS in _codes(validate_storyboard(_storyboard(scenes), [page]))
    scenes[1]["focuses"] = [{"at": 0.0, "element": "s1e2"}]  # covered at capture
    assert INVALID_FOCUS in _codes(validate_storyboard(_storyboard(scenes), [page]))
    scenes[1]["focuses"] = [{"at": 0.0, "element": "s1e0", "x": 0.5, "y": 0.5, "zoom": 1.0}]  # mixed
    assert INVALID_FOCUS in _codes(validate_storyboard(_storyboard(scenes), [page]))
    scenes[1]["focuses"] = [{"at": 0.0, "x": 0.5, "y": 0.5}]  # incomplete raw triple
    assert INVALID_FOCUS in _codes(validate_storyboard(_storyboard(scenes), [page]))


def _plate_scene(**over) -> dict:
    scene = {
        "type": "plate", "seconds": 5.0, "title": "Acme",
        "cards": [{"big": "256 B", "label": "Start free"},
                  {"big": None, "label": "Why teams switch"}],
        "backdrop": "mist",
    }
    scene.update(over)
    return scene


def test_plate_scene_grounds_and_bakes():
    """The numbers beat: title/big/label ground like any other string (a
    null big = a phrase card), and the spec carries the scene verbatim."""
    page = _page(h2=["Why teams switch", "256 B"])
    scenes = _pad(_good_scenes())
    scenes.insert(4, _plate_scene())
    storyboard = _storyboard(scenes)
    assert validate_storyboard(storyboard, [page]) == []
    spec = build_film_spec(storyboard, [page])
    plate = spec["scenes"][4]
    assert plate["type"] == "plate"
    assert plate["title"] == "Acme"
    assert plate["cards"] == [{"big": "256 B", "label": "Start free"},
                              {"big": None, "label": "Why teams switch"}]
    assert plate["backdrop"] == "mist"
    assert plate["frames"] == 150


def test_plate_caps_and_rarity():
    page = _page(h2=["Why teams switch", "256 B"])
    scenes = _good_scenes()
    scenes.insert(4, _plate_scene(cards=[{"big": "256 Bytes!!!!", "label": "Start free"},
                                         {"big": None, "label": "Why teams switch"}]))
    # big cap is 12 — also ungrounded; the cap violation is what we assert
    assert CONSTRAINT_VIOLATION in _codes(validate_storyboard(_storyboard(scenes), [page]))
    # Three plates with distinct strings: the rarity law (≤2 per film) is
    # what fires, not grounding or duplication.
    scenes = _good_scenes()
    scenes.insert(2, _plate_scene())
    scenes.insert(4, _plate_scene(
        title="Ship faster",
        cards=[{"big": "256 B", "label": "Docs"}, {"big": None, "label": "Acme"}]))
    scenes.insert(6, _plate_scene(
        title="Why teams switch",
        cards=[{"big": "256 B", "label": "Ship faster"}, {"big": None, "label": "Start free"}]))
    violations = validate_storyboard(_storyboard(scenes), [page])
    assert any(v.code == CONSTRAINT_VIOLATION and "plate" in v.detail for v in violations)


def test_ui_frame_flag_flows_to_spec():
    """frame=false = the full-bleed immersive variant; default stays true."""
    scenes = _good_scenes()
    scenes[1]["frame"] = False
    scenes[4]["frame"] = True  # the fixture's second walk rides full-bleed
    storyboard = _storyboard(scenes)
    assert validate_storyboard(_storyboard(_pad(scenes)), [_page()]) == []
    spec = build_film_spec(storyboard, [_page()])
    assert spec["scenes"][1]["frame"] is False
    assert spec["scenes"][4]["frame"] is True


def test_format_violations_is_compact_and_coded():
    scenes = _good_scenes()
    scenes[0]["sub"] = "invented copy nobody wrote"
    violations = validate_storyboard(_storyboard(scenes), [_page()])
    echo = format_violations(violations)
    assert "TEXT_NOT_GROUNDED" in echo and "scene[0]" in echo


# ---- the allocator + spec builder --------------------------------------------


def test_allocate_frames_rounds_and_floors():
    storyboard = _storyboard(_good_scenes())
    frames = allocate_frames(storyboard)
    # hero 3.0s → 90; ui 9.0s → 270; words/divider 3.0s → 90; end 4.0s → 120
    assert frames == [90, 270, 90, 90, 270, 120]
    assert all(n % 1 == 0 for n in frames)


def test_allocate_frames_minimums_clamp_up():
    scenes = [
        {"type": "words", "seconds": 1.5, "dark": False, "lines": ["Ship faster"]},  # 45
        {"type": "divider", "seconds": 2.0, "label": "Why teams switch",
         "roll": ["Ship faster", "Start free", "Docs"]},  # roll floor: 2*13+25=51 > 60? no: 60 wins
        {"type": "end", "seconds": 2.5, "name": "Acme", "tagline": "Ship faster"},  # 75 floor
    ]
    frames = allocate_frames(_storyboard(scenes))
    assert frames[0] == 45
    assert frames[1] == max(60, (3 - 1) * 13 + 25)
    assert frames[2] == 75


def test_divider_roll_floor_drives_frames():
    scenes = [
        {"type": "words", "seconds": 2.0, "dark": False, "lines": ["Ship faster"]},
        {"type": "divider", "seconds": 2.0, "label": "Why teams switch",
         "roll": ["Ship faster", "Start free", "Docs", "Ship faster", "Start free"]},
        {"type": "end", "seconds": 2.5, "name": "Acme", "tagline": "Ship faster"},
    ]
    frames = allocate_frames(_storyboard(scenes))
    # 5 words: (5-1)*13 + 25 = 77 > 60
    assert frames[1] == 77


def test_snap_frames_to_beats_moves_boundaries_within_tolerance():
    # 120 BPM bed → beats every 0.5s = 15 frames. Boundaries at 90/360/450/
    # 540/810: 90 lands exactly on beat 6, 360 on beat 24; the rest sit past
    # the grid's end (12s) — far beyond tolerance, untouched. Nothing moves.
    storyboard = _storyboard(_good_scenes())
    frames = allocate_frames(storyboard)  # [90, 270, 90, 90, 270, 120]
    beats = [i * 0.5 for i in range(25)]
    snapped = snap_frames_to_beats(storyboard, frames, beats)
    assert snapped == frames  # already on-grid
    assert sum(snapped) == sum(frames)


def test_snap_frames_to_beats_snaps_off_grid_boundary():
    storyboard = _storyboard(_good_scenes())
    frames = allocate_frames(storyboard)  # [90, 270, 90, 90, 270, 120]
    # Beat at 96 (3.2s) pulls boundary 90 up by 6 (the tolerance edge);
    # beat at 366 (12.2s) then pulls boundary 360 up by 6 — the hero gains
    # 6, the ui scene nets +6-6, the words scene absorbs the second delta.
    beats = [3.2, 12.2]
    snapped = snap_frames_to_beats(storyboard, frames, beats)
    assert snapped == [96, 270, 84, 90, 270, 120]
    assert sum(snapped) == sum(frames)


def test_snap_frames_to_beats_respects_tolerance_and_floors():
    storyboard = _storyboard(_good_scenes())
    frames = allocate_frames(storyboard)  # [90, 270, 90, 90, 270, 120]
    # Boundary 90's nearest beat at frame 100 is 10 frames away > 6-frame
    # tolerance: untouched. Boundary 360's beat at 354 moves 6 off the ui
    # scene — 270-6=264 ≥ floor, legal; the words scene absorbs +6.
    snapped = snap_frames_to_beats(storyboard, frames, [100 / FILM_FPS, 354 / FILM_FPS])
    assert snapped == [90, 264, 96, 90, 270, 120]
    # A beat at frame 340 (11.333s) is 20 frames from boundary 360 — past
    # tolerance at every boundary, so nothing moves.
    assert snap_frames_to_beats(storyboard, frames, [11.333]) == frames


def test_snap_frames_to_beats_never_breaks_a_floor():
    # end at exactly its 75-frame floor; the boundary beat at 66 (in
    # tolerance) would push it to 69 — refused, the boundary stays at 60.
    scenes = [
        {"type": "words", "seconds": 2.0, "dark": False, "lines": ["Ship faster"]},
        {"type": "end", "seconds": 2.5, "name": "Acme", "tagline": "Ship faster"},
    ]
    storyboard = _storyboard(scenes)
    frames = allocate_frames(storyboard)  # [60, 75]
    assert snap_frames_to_beats(storyboard, frames, [66 / FILM_FPS]) == frames


def test_snap_frames_to_beats_empty_grid_is_identity():
    storyboard = _storyboard(_good_scenes())
    frames = allocate_frames(storyboard)
    assert snap_frames_to_beats(storyboard, frames, []) == frames


def test_build_spec_accepts_snapped_frames():
    pages = [_page()]
    storyboard = _storyboard(_good_scenes())
    frames = allocate_frames(storyboard)
    snapped = snap_frames_to_beats(storyboard, frames, [3.2, 8.8])
    spec = build_film_spec(storyboard, pages, frames=snapped)
    assert [s["frames"] for s in spec["scenes"]] == snapped


def test_build_spec_bakes_chrome_and_stores_relative_keys():
    pages = [_page()]
    storyboard = _storyboard(_good_scenes(), name="Launch cut")
    spec = build_film_spec(storyboard, pages)
    assert spec["family"] == "film"
    assert spec["fps"] == FILM_FPS
    assert spec["name"] == "Launch cut"
    ui = spec["scenes"][1]
    assert ui["image"] == "user/capture/shot.png"  # relative key — absolutized at render
    assert ui["url"] == "example.com"  # display URL baked by code
    assert ui["frame"] is True  # the browser-chrome default
    end = spec["scenes"][5]
    assert end["url"] == "example.com"
    assert end["logo_url"] is None
    assert sum(s["frames"] for s in spec["scenes"]) == 930
    assert all(isinstance(s["frames"], int) for s in spec["scenes"])


def test_build_spec_projects_narration_audio_and_caption_cues():
    scenes = _good_scenes()
    scenes[0]["narration"] = "This is Acme. It ships the release."
    spec = build_film_spec(
        _storyboard(scenes),
        [_page()],
        narration={0: ("user/out/narr-0.mp3", 2.4)},
    )
    hero = spec["scenes"][0]
    assert hero["audio"] == "user/out/narr-0.mp3"
    assert [c["text"] for c in hero["captions"]] == [
        "This is Acme.",
        "It ships the release.",
    ]
    assert hero["captions"][0]["at"] == 0
    assert 0 < hero["captions"][1]["at"] < 2.4
    assert hero["captions"][-1]["end"] == 2.4


def test_narration_caption_cues_split_and_fit_the_spoken_window():
    cues = narration_caption_cues(
        "先说第一句，再接第二句。Then the closer lands!",
        window_s=5.0,
        spoken_s=4.0,
    )
    assert len(cues) == 3
    assert cues[0]["at"] == 0
    assert [a["at"] for a in cues] == sorted(a["at"] for a in cues)
    assert all(a["at"] < a["end"] <= 4.0 for a in cues)
    assert cues[-1]["end"] == 4.0


def test_presentation_times_come_from_the_execution_timeline():
    """展示=执行: the fact sheet's per-scene times/frames read the SAME
    snapped frame allocation the run renders — the presenting model never
    re-derives times from raw seconds."""
    storyboard = _storyboard(_good_scenes())
    beats = [i * 0.5 for i in range(80)]  # 120 BPM
    facts = storyboard_presentation(
        storyboard,
        [_page()],
        aspect="16:9",
        music="calm — Bed · 120 BPM",
        beats=beats,
        bpm=120,
        captions=True,
    )
    assert "total 31s · 930 frames" in facts
    assert "music: calm — Bed · 120 BPM" in facts
    assert "scene 2 · ui · home walk · 3–12s · 9s · 270 frames" in facts


def test_build_spec_assigns_divider_ordinals():
    scenes = [
        {"type": "divider", "seconds": 2.0, "label": "Why teams switch", "roll": ["Ship faster"]},
        {"type": "words", "seconds": 2.0, "dark": False, "lines": ["Ship faster"]},
        {"type": "divider", "seconds": 2.0, "label": "Start free", "roll": ["Docs"]},
        {"type": "end", "seconds": 2.5, "name": "Acme", "tagline": "Ship faster"},
    ]
    spec = build_film_spec(_storyboard(scenes), [_page()])
    dividers = [s for s in spec["scenes"] if s["type"] == "divider"]
    assert [d["index"] for d in dividers] == ["01", "02"]


def test_build_spec_carries_the_split_reveal_lead_frames():
    scenes = [
        {
            "type": "reveal",
            "seconds": 5.0,
            "lead": "One more thing.",
            "lead_seconds": 1.5,
            "word": "Acme",
            "sub": "Ship faster",
        },
        {"type": "end", "seconds": 2.5, "name": "Acme", "tagline": "Ship faster"},
    ]
    spec = build_film_spec(_storyboard(scenes), [_page()])
    # lead (1.5s = 45 frames) + one-beat black pause (0.5s = 15 frames)
    assert spec["scenes"][0]["lead_frames"] == 60
    # Read tolerance: a pre-split stored reveal defaults to the code lead hold.
    legacy = dict(scenes[0])
    legacy.pop("lead_seconds")
    spec = build_film_spec(_storyboard([legacy, scenes[1]]), [_page()])
    assert spec["scenes"][0]["lead_frames"] == 60


def test_build_spec_reveal_word_onset_snaps_to_the_music_grid():
    """lead → beat pause → word: the word lands on the next beat at/after
    the lead's end plus one beat of pause (120 BPM grid = 0.5s)."""
    scenes = [
        {
            "type": "reveal",
            "seconds": 12.0,
            "lead": "One more thing.",
            "lead_seconds": 5.75,  # off-grid lead end
            "word": "Acme",
            "sub": "Ship faster",
        },
        {"type": "end", "seconds": 2.5, "name": "Acme", "tagline": "Ship faster"},
    ]
    music = {"url": "music/x.mp3", "gain_db": -20.0, "bpm": 120.0}
    spec = build_film_spec(_storyboard(scenes), [_page()], music=music)
    # lead ends at 5.75s → next beat 6.0s → word at 6.5s = 195 frames
    assert spec["scenes"][0]["lead_frames"] == 195
    # The word phase keeps ≥1s even when the grid would push past it.
    scenes[0]["lead_seconds"] = 11.0
    spec = build_film_spec(_storyboard(scenes), [_page()], music=music)
    assert spec["scenes"][0]["lead_frames"] == 330  # clamped to n - 30


def test_build_spec_reveal_pause_uses_the_real_beat_interval():
    """ADR-130: the black pause IS the bed's real beat interval — a 100 BPM
    grid (0.6s) lands the word where a hardcoded half-second never would
    (the 120 BPM test above cannot tell the two apart)."""
    scenes = [
        {
            "type": "reveal",
            "seconds": 12.0,
            "lead": "One more thing.",
            "lead_seconds": 5.75,
            "word": "Acme",
            "sub": "Ship faster",
        },
        {"type": "end", "seconds": 2.5, "name": "Acme", "tagline": "Ship faster"},
    ]
    music = {"url": "music/x.mp3", "gain_db": -20.0, "bpm": 100.0}
    spec = build_film_spec(_storyboard(scenes), [_page()], music=music)
    # lead ends 5.75s → next 0.6s beat 6.0s → word at 6.6s = 198 frames.
    assert spec["scenes"][0]["lead_frames"] == 198


def test_build_spec_provenance_stamps_the_design_digests():
    """ADR-129: 呈现稿 digest = run context digest = render spec digest —
    the design beat's stamps ride the spec as ``provenance``; snapshot-less
    births keep the keys out (读容忍)."""
    scenes = [
        {"type": "hero", "seconds": 3.0, "word": "Ship faster", "sub": "Acme."},
        {"type": "end", "seconds": 2.5, "name": "Acme", "tagline": "Ship faster"},
    ]
    spec = build_film_spec(
        _storyboard(scenes),
        [_page()],
        storyboard_digest="sb-digest",
        execution_digest="ex-digest",
    )
    assert spec["provenance"] == {
        "storyboard_digest": "sb-digest",
        "execution_digest": "ex-digest",
    }
    bare = build_film_spec(_storyboard(scenes), [_page()])
    assert "provenance" not in bare


def test_current_direction_dict_projects_the_resolved_board():
    """修订基于当前稿 (ADR-129): the board under review projects as the
    director's revision base — resolved strings keyed like the direction's
    own output, narrations addressed by 1-based scene index."""
    from app.tools.film.storyboard import current_direction_dict

    board = _storyboard(
        [
            {"type": "words", "seconds": 3.0, "dark": True, "lines": ["hook one", "hook two"]},
            {"type": "hero", "seconds": 3.0, "word": "Ship faster", "sub": "Acme.",
             "narration": "Meet Acme."},
            {"type": "divider", "seconds": 3.0, "label": "Why teams switch",
             "roll": ["Ship faster"]},
            {"type": "divider", "seconds": 3.0, "label": "Pricing",
             "roll": ["Start free"]},
            {"type": "reveal", "seconds": 9.0, "lead": "One more thing.",
             "word": "Acme", "sub": "Start free", "narration": "And one more thing."},
            {"type": "end", "seconds": 4.0, "name": "Acme", "tagline": "Ship faster"},
        ],
        name="Launch",
        language="en",
    )
    current = current_direction_dict(board)
    assert current["name"] == "Launch"
    assert current["language"] == "en"
    assert current["cold_open"] == ["hook one", "hook two"]
    assert current["hero_word"] == "Ship faster"
    assert current["hero_sub"] == "Acme."
    assert current["pillars"] == ["Why teams switch", "Pricing"]
    assert current["reveal_lead"] == "One more thing."
    assert current["reveal_word"] == "Acme"
    assert current["reveal_sub"] == "Start free"
    assert current["end_name"] == "Acme"
    assert current["end_tagline"] == "Ship faster"
    assert current["narrations"] == [
        {"scene": 2, "type": "hero", "text": "Meet Acme."},
        {"scene": 5, "type": "reveal", "text": "And one more thing."},
    ]


def test_build_spec_rejects_over_cap_total():
    scenes = [
        {"type": "ui", "seconds": 10.0, "page": 0,
         "focuses": [{"at": 0.0, "x": 0.5, "y": 0.5, "zoom": 1.0}]}
        for _ in range(8)
    ]
    # 8 ui scenes × 300 frames = 2400 — under cap; bump via long end cards
    storyboard = _storyboard(scenes)
    assert sum(allocate_frames(storyboard)) <= FILM_MAX_FRAMES
    # Push past the cap synthetically: seconds intents are capped per scene,
    # so the cap is unreachable via the validator — the builder's raise is
    # the defense-in-depth seat for hand-built storyboards.
    big = FilmStoryboard.model_construct(
        name=None,
        theme=None,
        scenes=[
            FilmStoryboard.model_validate({"scenes": scenes}).scenes[0]
        ] * 20,
    )
    with pytest.raises(FilmStoryboardRejected):
        build_film_spec(big, [_page()])


# ---- registry citizenship ----------------------------------------------------


def test_registry_and_node_citizenship():
    from app.pipeline.graph import NODE_KINDS
    from app.tools import TOOL_REGISTRY

    entry = TOOL_REGISTRY["launch_film"]
    assert entry.behavior == "probabilistic"
    assert not entry.needs_media_file  # the page is the input, not an upload
    node = NODE_KINDS["launch_film"]
    assert node.output_type == "film"
    assert [r.key for r in node.requires] == ["web_page"]
    assert node.produces_outputs and not node.needs_plan_prelude
    # The render claim gate keys on render_status alone — no type list to
    # drift (jobs.py claim_pending_render).


# ---- the film language chain (2026-10-15 语言钉参) ------------------------------


def test_storyboard_language_read_tolerance():
    """The drafter-declared language: absent on legacy rows reads as None
    (the schema carries the read tolerance), a declared code rides verbatim."""
    assert _storyboard(_good_scenes()).language is None
    assert _storyboard(_good_scenes(), language=None).language is None
    assert _storyboard(_good_scenes(), language="en").language == "en"


def test_launch_film_params_language_pin():
    """The plan's pin is an ordinary param (null = declare it from the
    page); the conversation's own language is never a source — the law lives
    in the Field description, the pin lives in params.language."""
    from app.tools.film.storyboard import LaunchFilmParams

    assert LaunchFilmParams.model_validate({}).language is None
    assert LaunchFilmParams.model_validate({"language": "en"}).language == "en"


def test_assemble_carries_the_pinned_language():
    """Purity by signature: the pin reaches the prompt assembly (and only
    there — the model never reads the conversation's own language). The
    board under review rides the same assembly (``current`` — None on a
    first design)."""
    from app.tools.film.storyboard import _assemble

    kwargs, _images = _assemble([], {"scenes": []}, "make it pop", None, "de", None, [])
    assert kwargs["language"] == "de"
    assert kwargs["skeleton"] == {"scenes": []}
    assert kwargs["current"] is None
    current = {"hero_word": "Ship faster", "pillars": ["Why teams switch"]}
    kwargs, _images = _assemble([], {"scenes": []}, None, None, None, current, [])
    assert kwargs["language"] is None
    assert kwargs["current"] is current


def test_storyboard_fingerprint_canonical_form():
    """设计拍 → dock 拍同键 (ADR-129 §4, 2026-10-17): the design beat's
    synthetic task and the approval dock's real task hash equal when they
    MEAN the same film — null params drop out, voiceover null pins to its
    explicit twin (narrated), a null aspect pins to the 16:9 default."""
    from app.tools.film.storyboard import storyboard_fingerprint

    def fp(params: dict, instruction: str = "make a film of the site") -> str | None:
        return storyboard_fingerprint([{"tool": "launch_film", "params": params}], instruction)

    assert fp({}) == fp({"aspect": None, "voiceover": None}) == fp({"aspect": "16:9", "voiceover": True})
    assert fp({"focus": "social"}) == fp({"focus": "social", "aspect": "16:9"})
    # A moved param is a different film — the dock must NOT reuse the board.
    assert fp({"aspect": "9:16"}) != fp({})
    assert fp({"voiceover": False}) != fp({})
    assert fp({"focus": "social"}) != fp({"focus": "pricing"})
    # The birth narrative is the fingerprint's other half.
    assert fp({}, "first narrative") != fp({}, "revised narrative")
    # A film-free chain fingerprints to None.
    assert storyboard_fingerprint([{"tool": "make_clips", "params": {}}], "x") is None


# ---- the direction budget + the fixed-fallback ladder (2026-10-18 裁决) ----
#
# The 30-minute generation ceiling + the journey split: the DESIGN journey
# (a user watches and judges the board) fails honestly on exhaustion, never
# masked by the fixed board; the unattended worker node keeps the 2026-10-16
# fixed-fallback 拍板.

import asyncio

from app.providers.llm.base import LLMError
from app.tools.film.storyboard import (
    _CAPTURE_SETTLE_WAIT_S,
    _DIRECTION_BUDGET_S,
    _DOCK_DRAFT_BUDGET_S,
    film_director,
    orchestrate_storyboard,
)


def test_direction_budget_is_the_thirty_minute_ceiling():
    """2026-10-18 用户拍板: the generation budget is the 30-minute ALLOWED
    ceiling (a clean first candidate still returns in seconds); the dock
    wrapper derives — capture wait + generation + slack."""
    assert _DIRECTION_BUDGET_S == 1800.0
    assert _DOCK_DRAFT_BUDGET_S == (
        _CAPTURE_SETTLE_WAIT_S + _DIRECTION_BUDGET_S + 60.0
    )


@pytest.mark.asyncio
async def test_design_journey_never_falls_to_the_fixed_board(monkeypatch):
    """The design journey's ladder has NO fixed rung: an LLM failure raises
    the original rejection — fixed_direction is never consulted."""
    pages = [_film_page()]

    async def _down(**_kw):
        raise LLMError("provider down")

    def _forbidden(_lines, **_kw):  # pragma: no cover - must never run
        raise AssertionError("the design journey consulted the fixed fallback")

    monkeypatch.setattr(film_director, "call", _down)
    monkeypatch.setattr(
        "app.tools.film.storyboard.fixed_direction", _forbidden
    )
    with pytest.raises(LLMError):
        await orchestrate_storyboard(
            pages=pages,
            instruction=None,
            focus=None,
            page_images=[],
            allow_fixed_fallback=False,
        )


@pytest.mark.asyncio
async def test_worker_path_keeps_the_fixed_fallback(monkeypatch):
    """The unattended mid-run path keeps the 2026-10-16 拍板: the LLM
    ladder's exhaustion ships the fixed board over the same skeleton."""
    pages = [_film_page()]

    async def _down(**_kw):
        raise LLMError("provider down")

    monkeypatch.setattr(film_director, "call", _down)
    board = await orchestrate_storyboard(
        pages=pages,
        instruction=None,
        focus=None,
        page_images=[],
        allow_fixed_fallback=True,
    )
    assert board.scenes  # the fixed board stands


@pytest.mark.asyncio
async def test_budget_exhaustion_raises_timeout_never_a_fixed_board(monkeypatch):
    """A slow-but-alive generation outlasting the ceiling raises the honest
    timeout (its own user_key — never relabeled a grounding failure), and
    the design journey never masks it with the fixed board."""
    pages = [_film_page()]

    async def _slow(**_kw):
        await asyncio.sleep(5)

    monkeypatch.setattr(film_director, "call", _slow)
    monkeypatch.setattr("app.tools.film.storyboard._DIRECTION_BUDGET_S", 0.05)
    with pytest.raises(LLMError) as excinfo:
        await orchestrate_storyboard(
            pages=pages,
            instruction=None,
            focus=None,
            page_images=[],
            allow_fixed_fallback=False,
        )
    assert excinfo.value.user_key == "film_storyboard_timeout"


# ---------------------------------------------------------------------------
# Dock 守卫分腿 + 配音承诺 (2026-10-18 最后一公里 — 4ad7963e):
# 批准已呈现分镜 = 消费它, 永不是重设计许可; voiceover 承诺下全片无旁白
# 不合格; 旁白键不匹配不得静默吞掉.
# ---------------------------------------------------------------------------


def _designed_namespace(**over):
    """The PendingPlan-shaped namespace right after a coherent design beat
    (the state resolve_film_dock_state reads)."""
    from types import SimpleNamespace

    board = _storyboard(_good_scenes())
    design_params = {"focus": "一站式整合", "language": "zh"}
    birth = "就按这个方向吧"
    fingerprint = storyboard_fingerprint(
        [{"tool": "launch_film", "params": design_params}], birth
    )
    film = DockStoryboard(
        presentation="x",
        storyboard=board.model_dump(mode="json"),
        fingerprint=fingerprint,
        reused=False,
        execution=build_film_execution_snapshot(pages=[], track=None),
    )
    state = film_design_state(
        None,
        film=film,
        design_params=design_params,
        review_hold=None,
        authorized_by="u1",
    )
    state.update(over)
    return SimpleNamespace(**state), birth


def _dock_tasks() -> list[dict]:
    # The model's approval dock — a param SUBSET (the rewrite + canonical
    # pinning must make it read as the presented version's own).
    return [{"tool": "launch_film", "params": {"focus": "一站式整合"}}]


def test_dock_resolution_passes_right_after_the_design_beat():
    """The 04:15 rejection does NOT reproduce on the current tree: the
    same-turn design → approval-dock state machine passes, model-side
    params spelled as a subset."""
    stored, birth = _designed_namespace()
    res = resolve_film_dock_state(stored, _dock_tasks(), birth)
    assert not isinstance(res, str)
    assert res.film_chain is True


def test_dock_stale_without_board_steers_represent_never_redesign():
    from types import SimpleNamespace

    stored = SimpleNamespace(
        film_storyboard=None, film_storyboard_params=None, film_draft_inflight=None
    )
    res = resolve_film_dock_state(stored, _dock_tasks(), "birth")
    assert isinstance(res, str)
    assert "no_board" in res
    assert "NO specific_instruction" in res
    assert "Redesign only on the user's change words" in res


def test_dock_stale_waits_for_an_in_flight_design():
    import time as _time
    from types import SimpleNamespace

    stored = SimpleNamespace(
        film_storyboard=None,
        film_storyboard_params=None,
        film_draft_inflight={"draft_id": "x", "started_at": _time.time()},
    )
    res = resolve_film_dock_state(stored, _dock_tasks(), "birth")
    assert isinstance(res, str)
    assert "in flight" in res
    assert "never redesign" in res


def test_dock_stale_plan_moved_names_the_retry():
    stored, birth = _designed_namespace()
    res = resolve_film_dock_state(stored, _dock_tasks(), "a DIFFERENT birth")
    assert isinstance(res, str)
    assert "fingerprint_mismatch" in res
    assert "retry present_plan once" in res
    assert "Approval of the presented board is never a redesign" in res


def test_dock_stale_broken_state_names_each_leg():
    stored, birth = _designed_namespace(
        film_draft_token=None, film_storyboard_version=None
    )
    res = resolve_film_dock_state(stored, _dock_tasks(), birth)
    assert isinstance(res, str)
    assert "draft_token_missing" in res
    assert "version_missing" in res
    assert "state fault, never a reason to redesign" in res
    assert "NO specific_instruction" in res


def test_dock_stale_tampered_execution_digest_named():
    stored, birth = _designed_namespace()
    stored.film_storyboard_execution = {
        **stored.film_storyboard_execution,
        "timing": {"fps": 24},
    }
    res = resolve_film_dock_state(stored, _dock_tasks(), birth)
    assert isinstance(res, str)
    assert "execution_digest_mismatch" in res


def test_dock_non_film_chain_clears_film_state():
    stored, birth = _designed_namespace()
    res = resolve_film_dock_state(
        stored, [{"tool": "make_post", "params": {}}], birth
    )
    assert not isinstance(res, str)
    assert res.film_chain is False
    assert res.state["film_storyboard"] is None


def test_voiceover_required_rejects_the_all_silent_board():
    pages = [_page()]
    board = _storyboard(_good_scenes())  # no narration anywhere
    assert NARRATION_MISSING in _codes(
        validate_storyboard(board, pages, narration_required=True)
    )
    # …and the same board is a legal SILENT cut without the promise.
    assert NARRATION_MISSING not in _codes(validate_storyboard(board, pages))


def test_voiceover_required_allows_partial_silence():
    pages = [_page()]
    scenes = _good_scenes()
    scenes[0]["narration"] = "This is Acme."  # the hero speaks; the rest silent
    board = _storyboard(scenes)
    assert NARRATION_MISSING not in _codes(
        validate_storyboard(board, pages, narration_required=True)
    )


def test_unknown_narration_key_is_named_never_silently_dropped():
    resolved, violations = _assemble_with(
        [_film_page()],
        narrations={"scene_1": "Nobody hears this.", "hero": "This is Acme."},
    )
    assert resolved is None
    assert NARRATION_KEY_UNKNOWN in _codes(violations)
    detail = format_violations(violations)
    assert "scene_1" in detail
    assert "hero" in detail  # the valid keys are enumerated for the rewrite


@pytest.mark.asyncio
async def test_voiceover_promise_reaches_the_director_and_the_validator(
    monkeypatch,
):
    """The 4ad7963e hole, closed at both ends: voiceover=true TELLS the
    director (the kwarg rides the call) and an all-silent candidate is
    REJECTED (NARRATION_MISSING rides the bounded rewrite's feedback) —
    never accepted as a designed board; voiceover=false keeps the silent
    cut legal."""
    pages = [_film_page()]
    seen: list = []

    async def _silent(**kw):
        seen.append(kw.get("voiceover"))
        return _direction(narrations={})

    monkeypatch.setattr(film_director, "call", _silent)
    with pytest.raises(FilmStoryboardRejected) as excinfo:
        await orchestrate_storyboard(
            pages=pages,
            instruction=None,
            focus=None,
            page_images=[],
            allow_fixed_fallback=False,
            voiceover=True,
        )
    assert NARRATION_MISSING in excinfo.value.codes
    assert seen and seen[0] is True

    seen.clear()
    board = await orchestrate_storyboard(
        pages=pages,
        instruction=None,
        focus=None,
        page_images=[],
        allow_fixed_fallback=False,
        voiceover=False,
    )
    assert all(not getattr(s, "narration", None) for s in board.scenes)
    assert seen and seen[0] is False
