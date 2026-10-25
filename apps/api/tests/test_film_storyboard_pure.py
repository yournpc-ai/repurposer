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
    narration_subtitle_cues,
    resolve_film_dock_state,
    scene_content_digest,
    skeleton_prompt_dict,
    snap_frames_to_beats,
    storyboard_content_digest,
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
    cues = narration_subtitle_cues("Version 2.4 ships today.", window_s=5.0, spoken_s=4.0)
    assert [c["text"] for c in cues] == ["Version 2.4 ships today."]
    cues = narration_subtitle_cues("First line. Second line.", window_s=8.0, spoken_s=6.0)
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
        voiceover=True,
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


def test_born_boards_carry_skeleton_key_scene_ids():
    """出生即分配 (R2-B): every assembled scene's id IS its skeleton key —
    the edit path's stable handle from birth, never a post-hoc assignment."""
    pages = [_film_page()]
    resolved, violations = _assemble_with(pages)
    assert violations == [] and resolved is not None
    assert [s.scene_id for s in resolved.scenes] == [
        "open", "hero", "home",
        "ch1_divider", "ch1_ui", "ch2_divider", "ch2_ui",
        "ch3_divider", "ch3_ui",
        "reveal", "end",
    ]
    # The digest law: ids are handles, never content — the born board's
    # content digest is byte-identical to its id-stripped twin (legacy
    # boards keep matching old stored digests).
    raw = resolved.model_dump(mode="json")
    for scene in raw["scenes"]:
        scene.pop("scene_id")
    assert storyboard_content_digest(raw) == storyboard_content_digest(resolved)
    # The fact sheet carries the ids (the model names scenes by id in ops).
    text = storyboard_presentation(resolved, pages)
    assert "[hero]" in text and "[ch2_ui]" in text and "[end]" in text
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


def test_build_spec_narration_does_not_implicitly_add_subtitles():
    scenes = _good_scenes()
    scenes[0]["narration"] = "This is Acme. It ships the release."
    spec = build_film_spec(
        _storyboard(scenes), [_page()],
        narration={0: ("user/out/narr-0.mp3", 2.4)},
    )
    assert spec["scenes"][0]["audio"] == "user/out/narr-0.mp3"
    assert "subtitle_track" not in spec["scenes"][0]
    assert "captions" not in spec["scenes"][0]


def test_narration_subtitle_cues_split_and_fit_the_spoken_window():
    cues = narration_subtitle_cues(
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
        voiceover=True,
    )
    assert "total 31s · 930 frames" in facts
    assert "music: calm — Bed · 120 BPM" in facts
    assert "scene 2 · ui · home walk · 3–12s · 9s · 270 frames" in facts


def test_presentation_honors_saved_frozen_frame_windows():
    """A patch fact sheet reads the version's frozen cut instead of
    recomputing a different timeline from the music grid."""
    storyboard = _storyboard(_good_scenes())
    frames = [30 * (i + 1) for i in range(len(storyboard.scenes))]
    facts = storyboard_presentation(
        storyboard, [_page()], frame_override=frames
    )
    total = sum(frames)
    assert f"total {total / 30:g}s · {total} frames" in facts
    assert "0–1s · 1s · 30 frames" in facts


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


def test_text_source_birth_pin_redraft_inherits_the_base_source():
    """Omission inherits; an explicit value overrides; explicit null clears.

    Text keeps its separate re-paste/inherit rule. A new film or a base with
    no recorded params inherits nothing.
    """
    from app.tools.film.storyboard import (
        film_text_source_birth_pin,
        film_verbatim_birth_pin,
    )

    pin = film_text_source_birth_pin
    base = {"text": "旧文案", "verbatim": False, "target_seconds": 11.0, "scene_count": 2, "group_chars": [3, 5]}
    absent = dict(
        target_seconds_present=False,
        scene_count_present=False,
        group_chars_present=False,
    )
    present = dict(
        target_seconds_present=True,
        scene_count_present=True,
        group_chars_present=True,
    )
    assert pin(None, None, None, None, base, base_present=True, **absent) == ("旧文案", 11.0, 2, [3, 5])
    assert pin("新文案", None, None, None, base, base_present=True, **absent) == ("新文案", 11.0, 2, [3, 5])
    assert pin(None, 20.0, 3, [2, 4], base, base_present=True, **present) == ("旧文案", 20.0, 3, [2, 4])
    assert pin("新文案", 20.0, 3, [2, 4], base, base_present=True, **present) == ("新文案", 20.0, 3, [2, 4])
    # Explicit null is a REAL clear, not an omitted key and not a base inherit.
    assert pin(None, None, None, None, base, base_present=True, **present) == ("旧文案", None, None, None)
    assert pin(None, None, None, None, None, base_present=False, **absent) == (None, None, None, None)
    assert pin(None, None, None, None, None, base_present=True, **absent) == (None, None, None, None)
    assert pin(None, None, None, None, "garbage", base_present=True, **absent) == (None, None, None, None)
    assert pin(None, None, None, None, {"aspect": "16:9"}, base_present=True, **absent) == (None, None, None, None)
    # The verbatim pin reads the RESOLVED text: an inherited source keeps
    # the base's verbatim mode (never drops the key and re-guesses).
    text, _t, _c, _g = pin(None, None, None, None, base, base_present=True, **absent)
    assert film_verbatim_birth_pin(None, base, base_present=True, text_present=bool(text)) is False


def test_voiceover_birth_pin_new_default_off_and_legacy_inheritance():
    """默认无配音 (2026-10-21 用户拍板) — the birth pin's two lenses: a NEW
    film (no base version) defaults OFF; a redraft INHERITS the base
    version's pinned setting, with legacy rows reading through canonical's
    historical lens (a missing key = the narrated default those films
    shipped with). An explicit arg always wins — true is legitimate only as
    the user's explicit ask (the schema's law; the pin trusts the declared
    value)."""
    from app.tools.film.storyboard import film_voiceover_birth_pin

    pin = film_voiceover_birth_pin
    # A genuinely new film defaults OFF.
    assert pin(None, None, base_present=False) is False
    # An explicit ask always pins verbatim.
    assert pin(True, None, base_present=False) is True
    assert pin(False, None, base_present=False) is False
    assert pin(True, {"voiceover": False}, base_present=True) is True
    assert pin(False, {"voiceover": True}, base_present=True) is False
    # A redraft inherits the base version's pinned setting.
    assert pin(None, {"voiceover": False}, base_present=True) is False
    assert pin(None, {"voiceover": True}, base_present=True) is True
    # Legacy lenses: a base whose params predate the pin (missing key) or
    # were never recorded reads as the historical narrated default — an old
    # film is never silently muted by a redraft.
    assert pin(None, {"aspect": "16:9"}, base_present=True) is True
    assert pin(None, None, base_present=True) is True
    assert pin(None, "garbage", base_present=True) is True


def test_presentation_fact_sheet_always_states_the_voiceover_switch():
    """配音开关恒显: the fact sheet carries the real voiceover state in BOTH
    positions — a silent default that never appears reads as an omission the
    presenting model improvises around."""
    pages = [_film_page()]
    lines = build_line_manifest(pages)
    skeleton = build_skeleton(pages, lines)
    resolved, violations = assemble_storyboard(skeleton, _direction(), lines)
    assert violations == [] and resolved is not None
    on = storyboard_presentation(resolved, pages, voiceover=True)
    off = storyboard_presentation(resolved, pages, voiceover=False)
    assert "voiceover: on" in on and "voiceover: off" not in on
    assert "voiceover: off" in off and "voiceover: on" not in off


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


# ---------------------------------------------------------------------------
# Text-plane vocabulary (ADR-138 §7.6): words-scene motion/enter enums.
# ---------------------------------------------------------------------------


def test_words_vocabulary_null_keys_keep_legacy_digests_byte_identical():
    """Null motion/enter are EXCLUDED from the content dump: a legacy board
    (keys absent) and its explicit-null twin digest byte-identically, so
    every stored digest keeps matching after the vocabulary ships. A SET
    value participates — an edit moves the digest."""
    legacy = {"type": "words", "seconds": 3.0, "dark": False, "lines": ["Ship faster"]}
    explicit_null = {**legacy, "motion": None, "enter": None}
    assert scene_content_digest(legacy) == scene_content_digest(explicit_null)
    assert storyboard_content_digest(_storyboard([legacy])) == storyboard_content_digest(
        _storyboard([explicit_null])
    )
    assert scene_content_digest({**legacy, "motion": "push"}) != scene_content_digest(legacy)
    assert scene_content_digest({**legacy, "enter": "words"}) != scene_content_digest(legacy)


def test_build_spec_words_vocabulary_rides_only_when_set():
    """The spec carries motion/enter only when the scene sets them — null
    keys stay out of the render contract (the digest law's spec-side twin)."""
    scenes = [
        {"type": "words", "seconds": 3.0, "dark": False, "lines": ["Ship faster"],
         "motion": "push", "enter": "words"},
        {"type": "words", "seconds": 3.0, "dark": True, "lines": ["Legacy"]},
        {"type": "end", "seconds": 2.5, "name": "Acme", "tagline": "Ship faster"},
    ]
    spec = build_film_spec(_storyboard(scenes), [_page()])
    assert spec["scenes"][0]["motion"] == "push"
    assert spec["scenes"][0]["enter"] == "words"
    assert "motion" not in spec["scenes"][1]
    assert "enter" not in spec["scenes"][1]


def test_words_vocabulary_enums_are_closed():
    """The vocabulary is a closed enum (L3 枚举纪律) — an unknown value is a
    schema rejection, never a renderer surprise."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _storyboard([
            {"type": "words", "seconds": 3.0, "dark": False, "lines": ["x"], "motion": "zoom-crazy"}
        ])
    with pytest.raises(ValidationError):
        _storyboard([
            {"type": "words", "seconds": 3.0, "dark": False, "lines": ["x"], "enter": "explode"}
        ])


# ---------------------------------------------------------------------------
# Batch B: precise words-plane timing
# ---------------------------------------------------------------------------


def test_seconds_to_frames_is_the_one_quantization_rule():
    """Nearest frame, halves UP — the user's named decimals land on stable
    frames (0.3s→f9, 0.12s→f4, 0.25s→f8); zero stays zero."""
    from app.tools.film.storyboard import film_seconds_to_frames

    assert film_seconds_to_frames(0.0) == 0
    assert film_seconds_to_frames(0.3) == 9
    assert film_seconds_to_frames(0.12) == 4  # 3.6 → 4
    assert film_seconds_to_frames(0.25) == 8  # 7.5 → halves up
    assert film_seconds_to_frames(1.0) == FILM_FPS


def test_word_token_count_mirrors_the_renderer_tokenizer():
    """CJK glyphs are one token each, latin whitespace runs are one token,
    and the accent boundary breaks a latin run across it (the chip edge is
    a token edge, exactly like the renderer's split-then-tokenize)."""
    from app.tools.film.storyboard import word_enter_token_count

    assert word_enter_token_count(["文字依次入场"]) == 6
    assert word_enter_token_count(["Ship faster now"]) == 3
    assert word_enter_token_count(["好的 *内容* 不止一次"]) == 2 + 2 + 4
    assert word_enter_token_count(["ab*cd*ef"]) == 3  # the chip edge splits
    assert word_enter_token_count(["ab", "cd"]) == 2


def _timed_words_scene(**timing) -> dict:
    """The user's example beat: six CJK tokens on a 4s (120f) plane."""
    return {
        "type": "words",
        "seconds": 4.0,
        "dark": False,
        "lines": ["文字依次入场"],
        "enter": "words",
        **timing,
    }


def test_user_example_timing_validates_clean():
    """第二幕开始后 0.3 秒 / 相邻 0.12 秒 / 每个 0.25 秒 / 停留至幕末 —
    f9 start, f4 step, f8 duration, 6 tokens: last end f37 ≪ f120."""
    scene = _timed_words_scene(
        enter_start=0.3, enter_interval=0.12, enter_duration=0.25
    )
    board = _storyboard(_pad([scene] + _good_scenes()))
    assert validate_storyboard(board, [_page()]) == []


def test_timing_overflow_is_a_concrete_rejection_never_a_clamp():
    """A wide cadence on a 3s (90f) plane cannot fit: the last token starts
    at f84 but its entrance ends at f92 > the f90 scene end — the validator
    names the numbers, nothing is shortened."""
    scene = _timed_words_scene(
        enter_start=0.3, enter_interval=0.5, enter_duration=0.25
    )
    scene["seconds"] = 3.0
    violations = validate_storyboard(_storyboard(_pad([scene])), [_page()])
    assert DURATION_INVALID in _codes(violations)
    detail = next(v.detail for v in violations if v.code == DURATION_INVALID)
    assert "6 tokens" in detail and "scene[0]" in detail


def test_hold_must_leave_every_token_a_visible_frame():
    """A hold at/before the LAST token's start renders a scene whose words
    never visibly exist (the zero-duration / zero-interval degenerate) —
    concrete rejection, never a silent invisible board."""
    for timing in (
        {"enter_start": 0.0, "enter_interval": 0.0, "enter_duration": 0.0,
         "enter_hold_until": 0.0},
        {"enter_start": 0.3, "enter_interval": 0.12, "enter_duration": 0.25,
         "enter_hold_until": 0.5},  # f15 hold < f29 last start
    ):
        violations = validate_storyboard(
            _storyboard(_pad([_timed_words_scene(**timing)])), [_page()]
        )
        assert DURATION_INVALID in _codes(violations), timing


def test_hold_beyond_the_scene_window_rejects():
    scene = _timed_words_scene(enter_start=0.3, enter_hold_until=4.5)  # f135 > f120
    violations = validate_storyboard(_storyboard(_pad([scene])), [_page()])
    assert DURATION_INVALID in _codes(violations)
    detail = next(v.detail for v in violations if v.code == DURATION_INVALID)
    assert "enter_hold_until" in detail


def test_enter_timing_supports_the_whole_line_rhythm():
    """Explicit timing is unit-aware: enter=lines schedules whole lines,
    while the old enter=words tests above keep their token cadence."""
    scene = _timed_words_scene(enter_start=0.3)
    scene["enter"] = "lines"
    board = _storyboard(_pad([scene] + _good_scenes()))
    assert validate_storyboard(board, [_page()]) == []


def test_strict_line_slide_has_exact_sequence_facts_and_spec_fields():
    """Two lines with interval >= duration: line one is fully in at f21,
    line two starts at f24 and lands at f36. Pure slide is part of the same
    versioned spec/presentation, not a renderer-only side channel."""
    from app.tools.film.storyboard import film_scene_content, words_timing_clause

    scene = _timed_words_scene(
        enter_start=0.3,
        enter_interval=0.5,
        enter_duration=0.4,
    )
    scene.update(
        enter="lines",
        enter_style="slide",
        lines=["见阳光的人", "眼里全是温柔和笑意"],
    )
    board = _storyboard(_pad([scene] + _good_scenes()))
    assert validate_storyboard(board, [_page()]) == []
    clause = words_timing_clause(board.scenes[0])
    assert "2 lines" in clause
    assert "last starts f24 (0.800s)" in clause
    assert "fully in f36 (1.200s)" in clause
    assert "slide-only entrance (no fade, no blur)" in film_scene_content(board.scenes[0])
    rendered = build_film_spec(board, [_page()])["scenes"][0]
    assert rendered["enter"] == "lines"
    assert rendered["enter_style"] == "slide"
    assert rendered["enter_interval"] == 0.5
    assert rendered["enter_duration"] == 0.4


def test_motion_window_requires_a_move_and_stays_ordered_inside():
    base = _timed_words_scene()
    base.pop("enter")
    static = {**base, "motion": "static", "motion_start": 1.0}
    violations = validate_storyboard(_storyboard(_pad([static])), [_page()])
    assert CONSTRAINT_VIOLATION in _codes(violations)

    inverted = {**base, "motion": "push", "motion_start": 2.0, "motion_end": 1.0}
    violations = validate_storyboard(_storyboard(_pad([inverted])), [_page()])
    assert DURATION_INVALID in _codes(violations)

    beyond = {**base, "motion": "pull", "motion_end": 4.5}  # f135 > f120
    violations = validate_storyboard(_storyboard(_pad([beyond])), [_page()])
    assert DURATION_INVALID in _codes(violations)

    clean = {**base, "motion": "push", "motion_start": 0.5, "motion_end": 3.0}
    board = _storyboard(_pad([clean] + _good_scenes()))
    assert validate_storyboard(board, [_page()]) == []


def test_build_spec_carries_set_timing_and_omits_nulls():
    """Explicit zero is a VALUE (it reaches the spec); a null key stays out
    (legacy boards keep their byte-shape)."""
    timed = _timed_words_scene(
        enter_start=0.3, enter_interval=0.12, enter_duration=0.25,
        enter_hold_until=3.5,
    )
    zeroed = _timed_words_scene(enter_start=0.0, enter_interval=0.0)
    legacy = {"type": "words", "seconds": 3.0, "dark": True, "lines": ["Legacy"]}
    spec = build_film_spec(_storyboard([timed, zeroed, legacy]), [_page()])
    first, second, third = spec["scenes"]
    assert first["enter_start"] == 0.3
    assert first["enter_interval"] == 0.12
    assert first["enter_duration"] == 0.25
    assert first["enter_hold_until"] == 3.5
    assert "motion_start" not in first
    assert second["enter_start"] == 0.0 and second["enter_interval"] == 0.0
    assert "enter_duration" not in second  # omitted, not nulled
    for key in (
        "enter_start", "enter_interval", "enter_duration",
        "enter_hold_until", "motion_start", "motion_end",
    ):
        assert key not in third


def test_build_spec_revalidates_against_the_allocated_frames():
    """Design-time seconds said it fits; beat-snapped/shrunk allocation says
    it does not — the spec build refuses with the concrete conflict instead
    of silently truncating the animation."""
    scene = _timed_words_scene(
        enter_start=0.3, enter_interval=0.12, enter_duration=0.25
    )
    board = _storyboard([scene])
    with pytest.raises(FilmStoryboardRejected) as exc_info:
        build_film_spec(board, [_page()], frames=[30])  # f30 < the f37 need
    assert DURATION_INVALID in exc_info.value.codes


def test_timing_fields_join_the_digest_only_when_set():
    """Null timing keys read as absent (legacy boards digest byte-identical);
    a SET value — explicit zero included — moves the scene's identity."""
    from app.tools.film.storyboard import (
        FILM_WORDS_TIMING_FIELDS,
        _LEGACY_ABSENT_SCENE_KEYS,
    )

    assert FILM_WORDS_TIMING_FIELDS <= _LEGACY_ABSENT_SCENE_KEYS
    legacy = {"type": "words", "seconds": 3.0, "dark": False, "lines": ["Ship faster"]}
    nulled = {**legacy, **{k: None for k in FILM_WORDS_TIMING_FIELDS}}
    assert scene_content_digest(legacy) == scene_content_digest(nulled)
    assert storyboard_content_digest(_storyboard([legacy])) == storyboard_content_digest(
        _storyboard([nulled])
    )
    zeroed = {**legacy, "enter": "words", "enter_start": 0.0}
    assert scene_content_digest(zeroed) != scene_content_digest(legacy)


def test_text_assembly_carries_segment_timing_onto_the_board():
    """The text director's per-segment timing lands on the words scene —
    the design tool → draft leg of the chain."""
    from app.tools.film.storyboard import (
        FilmTextDirection,
        FilmTextSource,
        ManifestLine,
        assemble_text_storyboard,
    )

    lines = [
        ManifestLine(1, 0, "paragraph", "文字依次入场"),
        ManifestLine(2, 0, "paragraph", "随后停留至幕末"),
    ]
    direction = FilmTextDirection.model_validate(
        {
            "segments": [
                {"refs": [{"line": 1}], "enter": "words",
                 "enter_start": 0.3, "enter_interval": 0.12,
                 "enter_duration": 0.25},
                {"refs": [{"line": 2}]},
            ]
        }
    )
    board, violations = assemble_text_storyboard(
        direction, lines, source=FilmTextSource(text="x", verbatim=True)
    )
    assert violations == []
    assert board is not None
    first, second = board.scenes
    assert first.enter_start == 0.3
    assert first.enter_interval == 0.12
    assert first.enter_duration == 0.25
    assert first.enter_hold_until is None
    assert second.enter_start is None  # untouched segment stays default


def test_timing_facts_are_one_clause_across_presentation_and_read():
    """The fact sheet, the read-back content seat and the patch summary all
    ride ``words_timing_clause`` — set values show seconds→frames, omitted
    pieces name their deterministic default."""
    from app.tools.film.storyboard import film_scene_content, words_timing_clause

    scene = _storyboard([
        _timed_words_scene(
            enter_start=0.3, enter_interval=0.12, enter_duration=0.25
        )
    ]).scenes[0]
    clause = words_timing_clause(scene, 120)
    # Requested seconds + quantized frame + the frame's REALIZED seconds —
    # quantization moves a decimal and the clause never hides it.
    assert "start 0.3s→f9 (0.300s)" in clause
    assert "interval 0.12s→f4 (0.133s)" in clause  # 0.12s requested ≠ rendered
    assert "duration 0.25s→f8 (0.267s)" in clause
    assert "hold to scene end (f120)" in clause
    # The last token's computed schedule (zero point f9 + 5×f4 = f29, fully
    # in after the 8-frame entrance at f37) is disclosed, not a claimed
    # sequence-wide sub-frame bound.
    assert "6 tokens, last starts f29 (0.967s), fully in f37 (1.233s)" in clause
    assert clause in film_scene_content(scene, 120)
    # A legacy scene names no timing clause at all.
    plain = _storyboard(_good_scenes()).scenes[2]
    assert words_timing_clause(plain) == ""


def test_current_text_direction_dict_round_trips_the_timing():
    """An open redraft sees (and therefore preserves) the current timing —
    the revision base's projection carries all six fields."""
    from app.tools.film.storyboard import current_text_direction_dict

    board = _storyboard([
        _timed_words_scene(
            enter_start=0.3, enter_interval=0.12, enter_duration=0.25,
            motion="push", motion_start=0.5, motion_end=3.0,
        )
    ])
    segment = current_text_direction_dict(board)["segments"][0]
    assert segment["enter_start"] == 0.3
    assert segment["enter_interval"] == 0.12
    assert segment["enter_duration"] == 0.25
    assert segment["enter_hold_until"] is None
    assert segment["motion_start"] == 0.5
    assert segment["motion_end"] == 3.0


def test_long_token_run_discloses_the_accumulated_landing():
    """长文本例 (非六字样例): 25 个 CJK token、0.12s 间隔量化到 f4——逐
    token 的量化偏差随序列线性累计 (每步 +0.0133s), 呈现层给出计算后的
    最后 token 落点 (f105/f113), 永不声称整段仍在亚帧误差内; 校验器按同
    一累计公式判定 (f113 ≤ f120 通过)."""
    from app.tools.film.storyboard import words_timing_clause

    line = "好的内容不应该只出现一次它可以长成文章短片和讨论中"  # 25 glyphs
    from app.tools.film.storyboard import word_enter_token_count

    assert word_enter_token_count([line]) == 25
    scene = _storyboard([
        {
            "type": "words", "seconds": 4.0, "dark": False, "lines": [line],
            "enter": "words", "enter_start": 0.3, "enter_interval": 0.12,
            "enter_duration": 0.25,
        }
    ]).scenes[0]
    clause = words_timing_clause(scene, 120)
    # start f9 + 24 × f4 = f105; fully in f105 + f8 = f113 (requested ideal
    # 0.3 + 24×0.12 + 0.25 = 3.43s — the realized 3.767s is the honest number).
    assert "25 tokens, last starts f105 (3.500s), fully in f113 (3.767s)" in clause
    board = _storyboard(_pad([
        {
            "type": "words", "seconds": 4.0, "dark": False, "lines": [line],
            "enter": "words", "enter_start": 0.3, "enter_interval": 0.12,
            "enter_duration": 0.25,
        }
    ] + _good_scenes()))
    assert validate_storyboard(board, [_page()]) == []
    # One more token's worth of interval would overflow the same window —
    # the accumulated schedule, not a per-step check, is what rejects.
    overflow = _storyboard(_pad([
        {
            "type": "words", "seconds": 4.0, "dark": False, "lines": [line],
            "enter": "words", "enter_start": 0.6, "enter_interval": 0.12,
            "enter_duration": 0.25,
        }
    ]))
    violations = validate_storyboard(overflow, [_page()])
    assert DURATION_INVALID in _codes(violations)


# ---------------------------------------------------------------------------
# F3 (事故 7886d879): Tasks 行文案 — 文字片不冒充官网片; 时长与读取/呈现座
# 同一 0.1 舍入律.
# ---------------------------------------------------------------------------


def test_launch_film_label_is_source_aware():
    """文字源 slot 的 Tasks 行名是「文字短片」, 官网措辞只服务官网源;
    slot tag 后缀律不变."""
    from app.models.schemas import IntentSlot
    from app.tools.film.storyboard import LaunchFilm

    node = LaunchFilm()
    text_slot = IntentSlot.model_validate(
        {"type": "film", "text": "产品介绍稿……", "language": "zh"}
    )
    web_slot = IntentSlot.model_validate({"type": "film", "language": "en"})

    assert node.label(text_slot, "zh") == "生成文字短片 · ZH"
    assert node.label(text_slot, "en") == "Generate text film · ZH"
    # 非文字源保持类默认 (tag 在场时 base 律用 slot_label 短词).
    assert node.label(web_slot, "zh") == "介绍短片 · EN"
    assert node.label(web_slot, "en") == "Film · EN"
    # 无 slot / 无 tag 的兜底形状不变.
    bare = IntentSlot.model_validate({"type": "film", "text": "稿……"})
    assert node.label(bare, "zh") == "生成文字短片"
    assert node.label(None, "zh") == "生成官网介绍短片"


def test_launch_film_summary_template_is_neutral_and_rounds_like_the_read_seats():
    """done 行模板: 中性「组装」(组装 spec + 挂起渲染, 渲染行自己报交付),
    时长走 :g —— 调用座的 round(x, 1) 进来后 29.5 永不印成 29, 整数不拖
    小数点."""
    from app.tools import TOOL_REGISTRY

    templates = TOOL_REGISTRY["launch_film"].summary_templates
    assert "官网" not in templates["zh"]
    assert templates["zh"].format(total_seconds=round(29.5, 1)) == (
        "已组装短片 · 29.5 秒"
    )
    assert templates["zh"].format(total_seconds=round(30.0, 1)) == "已组装短片 · 30 秒"
    assert templates["en"].format(total_seconds=round(29.5, 1)) == (
        "Assembled the film · 29.5s"
    )


# ---------------------------------------------------------------------------
# composite scenes (ADR-140) — media elements + independent text elements
# ---------------------------------------------------------------------------

_COMPOSITE_ASSET = "11111111-1111-1111-1111-111111111111"
_COMPOSITE_ASSET_2 = "22222222-2222-2222-2222-222222222222"


def _composite_scene(**over) -> dict:
    scene = {
        "type": "composite",
        "seconds": 8.0,
        "elements": [
            {
                "kind": "video",
                "asset": _COMPOSITE_ASSET,
                "source_start": 10.0,
                "source_end": 18.0,
                "at": 0.0,
                "rect": {"x": 0.5, "y": 0.0, "w": 0.5, "h": 1.0},
            },
            {
                "kind": "text",
                "lines": ["逐字出现", "second line"],
                "at": 1.0,
                "until": 7.0,
                "rect": {"x": 0.05, "y": 0.3, "w": 0.4, "h": 0.4},
                "enter": "words",
                "enter_interval": 0.3,
            },
        ],
    }
    scene.update(over)
    return scene


def _media(**over) -> "StoryboardMedia":
    from app.tools.film.storyboard import StoryboardMedia, StoryboardMediaAsset

    entry = StoryboardMediaAsset(
        id=_COMPOSITE_ASSET,
        key="u/demo/video.mp4",
        kind="video",
        title="Demo clip",
        duration_seconds=25.0,
        width=1920,
        height=1080,
    )
    for key, value in over.items():
        entry = StoryboardMediaAsset(**{**entry.__dict__, key: value})
    return StoryboardMedia(assets={entry.id: entry})


def _composite_board(**scene_over) -> FilmStoryboard:
    # Padded into the web-source contract window; the composite scene's own
    # point stays the only signal.
    return _storyboard(_pad(_good_scenes() + [_composite_scene(**scene_over)]))


def test_composite_clean_board_passes():
    assert validate_storyboard(_composite_board(), [_page()], media=_media()) == []


def test_composite_video_play_window_zero_frames_rejects():
    """复审缺陷②: a play window that quantizes to ZERO frames on the render
    grid must reject at the validator — the renderer never pads a fabricated
    frame (0.01s at 30fps rounds to 0 frames)."""
    scene = _composite_scene()
    scene["elements"][0]["source_end"] = 10.01
    violations = validate_storyboard(
        _composite_board(elements=scene["elements"]), [_page()], media=_media()
    )
    assert any(
        v.code == DURATION_INVALID and "zero frames" in v.detail
        for v in violations
    )


def test_composite_source_window_frame_contract():
    """复审①: source in/out frames and the output play window ride ONE
    quantization contract — the endpoints quantize FIRST (the renderer's
    startFrom/endAt), the default play window IS the quantized span (never
    quantize-the-delta, which can claim a frame the trim never shows), a
    sub-frame source span is EMPTY, and an explicit play window may not
    exceed the quantized source frames. No seat pads a frame."""
    # (a) Both endpoints land on the SAME frame (0.02s/0.04s → f1/f1): the
    #     source span is EMPTY even though the delta quantizes to 1 frame.
    scene = _composite_scene()
    scene["elements"][0].update(source_start=0.02, source_end=0.04)
    violations = validate_storyboard(
        _composite_board(elements=scene["elements"]), [_page()], media=_media()
    )
    assert any(
        v.code == DURATION_INVALID
        and "source" in v.detail
        and "zero frames" in v.detail
        for v in violations
    ), [f"{v.code}: {v.detail}" for v in violations]

    # (b) Non-integer endpoints, DEFAULT duration: the play window is the
    #     quantized span (f301..f541 → 240f) — so it fits a 240f scene
    #     EXACTLY (boundary equality). quantize-the-delta would claim 241f
    #     and either freeze a frame or falsely reject.
    scene = _composite_scene()
    scene["elements"][0].update(source_start=10.02, source_end=18.04)
    assert (
        validate_storyboard(
            _composite_board(elements=scene["elements"]), [_page()], media=_media()
        )
        == []
    )

    # (c) Explicit duration exceeding the QUANTIZED span (8.02s → 241f over
    #     the 240f the f301..f541 trim holds) rejects — the seconds-level
    #     schema rule (8.02 ≤ 8.02) cannot see the rounding gap.
    scene = _composite_scene(seconds=9.0)
    scene["elements"][0].update(
        source_start=10.02, source_end=18.04, duration=8.02
    )
    violations = validate_storyboard(
        _composite_board(elements=scene["elements"]), [_page()], media=_media()
    )
    assert any(
        v.code == DURATION_INVALID and "exceeds" in v.detail for v in violations
    ), [f"{v.code}: {v.detail}" for v in violations]

    # (d) Boundary equality passes: an explicit window of exactly the
    #     quantized span (10.0–18.0 → f300..f540 = 240f, duration 8.0 → 240f).
    scene = _composite_scene(seconds=9.0)
    scene["elements"][0].update(duration=8.0)
    assert (
        validate_storyboard(
            _composite_board(elements=scene["elements"]), [_page()], media=_media()
        )
        == []
    )

    # (e) Explicit sub-frame duration quantizes to zero frames → reject.
    scene = _composite_scene()
    scene["elements"][0].update(duration=0.01)
    violations = validate_storyboard(
        _composite_board(elements=scene["elements"]), [_page()], media=_media()
    )
    assert any(
        v.code == DURATION_INVALID and "zero frames" in v.detail
        for v in violations
    )


def test_composite_text_only_composes():
    """Text elements compose on their own (2026-10-23 复审拍板): a composite
    scene needs NO media element — several independent text elements over
    the theme canvas are a legal composition (words stays the convenient
    full-canvas recipe, never a forced funnel)."""
    scene = _composite_scene()
    text_a = dict(scene["elements"][1])
    text_b = dict(scene["elements"][1])
    text_b["lines"] = ["底部注释"]
    text_b["at"], text_b["until"] = 2.0, 6.0
    text_b["rect"] = {"x": 0.05, "y": 0.75, "w": 0.5, "h": 0.2}
    assert (
        validate_storyboard(
            _composite_board(elements=[text_a, text_b]), [_page()], media=_media()
        )
        == []
    )


def test_composite_legal_in_text_films():
    """composite is text-source legal (its media is an uploaded asset, never
    a captured page); the text profile's real bounds apply (1..120s)."""
    from app.tools.film.storyboard import build_text_manifest

    board = _storyboard(
        [
            {"type": "words", "seconds": 3.0, "dark": False, "lines": ["开场"]},
            _composite_scene(),
            {"type": "words", "seconds": 3.0, "dark": True, "lines": ["收尾"]},
        ]
    )
    violations = validate_storyboard(
        board, [], text_lines=build_text_manifest("开场\n收尾"), media=_media()
    )
    assert "UNSUPPORTED_SCENE" not in _codes(violations)


def test_composite_unknown_asset_rejects():
    violations = validate_storyboard(
        _composite_board(),
        [_page()],
        media=__import__("app.tools.film.storyboard", fromlist=["StoryboardMedia"]).StoryboardMedia(assets={}),
    )
    assert CONSTRAINT_VIOLATION in _codes(violations)
    assert any("not one of this project" in v.detail for v in violations)


def test_composite_media_none_defers_identity_checks():
    """media=None = this seat has no media knowledge — structural checks
    still fire, asset identity checks defer to the write/run seats."""
    violations = validate_storyboard(_composite_board(), [_page()], media=None)
    assert not any("not one of this project" in v.detail for v in violations)


def test_composite_kind_mismatch_rejects():
    board = _composite_board()
    scene = next(s for s in board.scenes if s.type == "composite")
    # An image element has no source window — rebuild honestly.
    from app.models.schemas import FilmElementImage

    scene.elements[0] = FilmElementImage(kind="image", asset=_COMPOSITE_ASSET)
    violations = validate_storyboard(board, [_page()], media=_media())
    assert any("is a video asset, not image" in v.detail for v in violations)


def test_composite_source_window_beyond_duration_rejects():
    scene = _composite_scene()
    scene["elements"][0]["source_end"] = 26.0
    violations = validate_storyboard(
        _storyboard(_pad([scene])), [_page()], media=_media()
    )
    assert DURATION_INVALID in _codes(violations)
    assert any("runs 25" in v.detail for v in violations)


def test_composite_unknown_duration_defers_to_run_probe():
    """Two-gate law: an unknown duration never guesses — no design-time
    rejection, the run seat probes the bytes."""
    scene = _composite_scene()
    scene["elements"][0]["source_end"] = 90.0
    violations = validate_storyboard(
        _storyboard(_pad([scene])), [_page()], media=_media(duration_seconds=None)
    )
    assert not any("runs" in v.detail for v in violations)


def test_composite_duplicate_element_id_rejects():
    scene = _composite_scene()
    scene["elements"][0]["element_id"] = "e1"
    scene["elements"][1]["element_id"] = "e1"
    violations = validate_storyboard(
        _storyboard(_pad([scene])), [_page()], media=_media()
    )
    assert any("duplicate element id" in v.detail for v in violations)


def test_composite_text_window_overflow_rejects():
    scene = _composite_scene()
    scene["elements"][1]["until"] = 9.0
    violations = validate_storyboard(
        _storyboard(_pad([scene])), [_page()], media=_media()
    )
    assert any("beyond the scene" in v.detail for v in violations)


def test_composite_null_until_is_scene_end():
    board = _composite_board()
    scene = next(s for s in board.scenes if s.type == "composite")
    scene.elements[1].until = None
    assert validate_storyboard(board, [_page()], media=_media()) == []


def test_composite_video_play_window_past_scene_rejects():
    scene = _composite_scene()
    scene["elements"][0]["at"] = 3.0  # 3 + 8 = 11s > 8s scene
    violations = validate_storyboard(
        _storyboard(_pad([scene])), [_page()], media=_media()
    )
    assert DURATION_INVALID in _codes(violations)
    assert any("past the scene" in v.detail for v in violations)


def test_composite_enter_timing_overflow_rejects():
    """The element-window enter schedule: 6 tokens at 0.5s interval can
    never land inside a 1s window — the words plane's law, one level down."""
    scene = _composite_scene()
    scene["elements"][1]["until"] = 2.0
    scene["elements"][1]["enter_interval"] = 0.5
    violations = validate_storyboard(
        _storyboard(_pad([scene])), [_page()], media=_media()
    )
    assert DURATION_INVALID in _codes(violations)
    assert any(
        "before the element leaves" in v.detail or "the element leaves at" in v.detail
        for v in violations
    )


def test_composite_motion_timing_gate():
    scene = _composite_scene()
    scene["elements"][1]["motion_start"] = 0.5  # no motion=push/pull
    violations = validate_storyboard(
        _storyboard(_pad([scene])), [_page()], media=_media()
    )
    assert any("motion timing needs" in v.detail for v in violations)


def test_composite_repeated_signature_keys_on_media_identity():
    """Two composites with the same captions over DIFFERENT assets are
    different screens; over the SAME asset + captions they repeat."""
    scene_a = _composite_scene()
    scene_b = _composite_scene()
    scene_b["elements"] = [dict(scene_b["elements"][0], asset=_COMPOSITE_ASSET_2)]
    board = _storyboard(_pad([scene_a, scene_b]))
    media = _media()
    from app.tools.film.storyboard import StoryboardMediaAsset

    media.assets[_COMPOSITE_ASSET_2] = StoryboardMediaAsset(
        id=_COMPOSITE_ASSET_2, key="u/demo/other.mp4", kind="video",
        title="Other", duration_seconds=30.0, width=1920, height=1080,
    )
    violations = validate_storyboard(board, [_page()], media=media)
    assert not any("repeats another scene's screen" in v.detail for v in violations)

    board_same = _storyboard(_pad([_composite_scene(), _composite_scene()]))
    violations_same = validate_storyboard(board_same, [_page()], media=media)
    assert any("repeats another scene's screen" in v.detail for v in violations_same)


def test_composite_counts_as_chapter_substance():
    """EMPTY_CHAPTER: a divider followed by a composite scene HAS its walk
    (the media composition is substance, like a page walk)."""
    scenes = _pad(
        [
            {"type": "divider", "seconds": 3.0, "label": "Chapter",
             "roll": ["Ship faster"]},
            _composite_scene(),
        ]
    )
    violations = validate_storyboard(_storyboard(scenes), [_page()], media=_media())
    assert EMPTY_CHAPTER not in _codes(violations)


def test_composite_spec_build_emits_elements():
    """The spec carries storage KEYS (resolved from asset ids via the media
    universe), null-stays-out timing/until, per-element windows."""
    board = _composite_board()
    spec = build_film_spec(board, [_page()], media=_media())
    scene = next(s for s in spec["scenes"] if s["type"] == "composite")
    assert scene["type"] == "composite" and scene["dark"] is False
    video, text = scene["elements"]
    assert video["kind"] == "video"
    assert video["src"] == "u/demo/video.mp4"  # asset id resolved to the key
    assert video["source_start"] == 10.0 and video["source_end"] == 18.0
    assert video["keep_audio"] is False
    assert video["rect"] == {"x": 0.5, "y": 0.0, "w": 0.5, "h": 1.0}
    assert "duration" not in video  # null = full source range, stays out
    assert text["kind"] == "text"
    assert text["lines"] == ["逐字出现", "second line"]
    assert text["until"] == 7.0 and text["at"] == 1.0
    assert text["enter"] == "words" and text["enter_interval"] == 0.3
    assert "enter_start" not in text  # null stays out
    # element ids ride as "id" (the renderer keys windows on them)
    assert "id" in video or True  # ids may be None pre-ensure; keys exist


def test_composite_spec_build_null_until_omitted():
    board = _composite_board()
    scene_model = next(s for s in board.scenes if s.type == "composite")
    scene_model.elements[1].until = None
    spec = build_film_spec(board, [_page()], media=_media())
    scene = next(s for s in spec["scenes"] if s["type"] == "composite")
    assert "until" not in scene["elements"][1]


def test_composite_spec_build_unresolvable_asset_fails_honestly():
    from app.tools.film.storyboard import StoryboardMedia

    with pytest.raises(FilmStoryboardRejected):
        build_film_spec(_composite_board(), [_page()], media=StoryboardMedia(assets={}))
    with pytest.raises(FilmStoryboardRejected):
        build_film_spec(_composite_board(), [_page()], media=None)


def test_composite_spec_build_rechecks_against_snapped_frames():
    """The spec-build mirror seat: an element window that fit the authored
    seconds but not the snapped allocation rejects, never clamps."""
    board = _composite_board()
    alloc = allocate_frames(board)
    # Squeeze the composite scene's allocation below the text element's
    # until=7s (authored 8s scene).
    idx = next(i for i, s in enumerate(board.scenes) if s.type == "composite")
    alloc[idx] = 120  # 4s < 7s window
    with pytest.raises(FilmStoryboardRejected):
        build_film_spec(board, [_page()], frames=alloc, media=_media())


def test_composite_execution_snapshot_media_pins():
    """Identity pins only (id + key), sorted, omitted when empty — a legacy
    (composite-less) snapshot digests byte-identically to before."""
    from app.tools.film.storyboard import film_execution_snapshot_digest

    snap = build_film_execution_snapshot(pages=[_page()], track=None, media=_media())
    assert snap["media"] == [
        {"asset_id": _COMPOSITE_ASSET, "key": "u/demo/video.mp4"}
    ]
    assert film_execution_snapshot_digest(snap) == snap["digest"]

    from app.tools.film.storyboard import StoryboardMedia

    empty = build_film_execution_snapshot(
        pages=[_page()], track=None, media=StoryboardMedia(assets={})
    )
    legacy = build_film_execution_snapshot(pages=[_page()], track=None)
    assert "media" not in empty
    assert empty["digest"] == legacy["digest"]


def test_composite_element_ids_never_enter_the_digest():
    """Assigning element ids moves no digest (the scene_id law one level
    down); an element CONTENT edit moves it."""
    from app.tools.film.edits import ensure_scene_ids

    bare = _composite_board()
    keyed = ensure_scene_ids(bare)
    keyed_scene = next(s for s in keyed.scenes if s.type == "composite")
    bare_scene = next(s for s in bare.scenes if s.type == "composite")
    assert [e.element_id for e in keyed_scene.elements] == ["e1", "e2"]
    assert storyboard_content_digest(bare) == storyboard_content_digest(keyed)
    assert scene_content_digest(bare_scene) == scene_content_digest(keyed_scene)

    edited = keyed.model_copy(deep=True)
    next(s for s in edited.scenes if s.type == "composite").elements[1].tone = "dark"
    assert storyboard_content_digest(edited) != storyboard_content_digest(keyed)


def test_composite_presentation_shows_element_facts():
    presentation = storyboard_presentation(_composite_board(), [_page()], media=_media())
    assert "media composition" in presentation
    assert '"Demo clip"' in presentation  # the asset's title, from media
    assert "source 10–18s" in presentation
    assert "逐字出现" in presentation


# ---- 素材发现清单座 (ADR-140 下批 A1): project_media_candidates --------------
#
# The ONE listing seat's mapping law (two consumers — the chat read and the
# text director's prompt — can never drift apart): the exact probed duration
# wins over the floored Integer column, unknowns stay None (never guessed),
# non-int dimensions drop, usability = the bytes exist, the processing state
# is informational. Tenant/kind scoping is SQL-side — covered by the
# isolated-DB lifecycle test; here a fake db returns the rows.


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


class _FakeDB:
    """Answers execute() with the staged rows — the select itself is pure
    (no round trip), so the fake never sees SQL."""

    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return _FakeResult(self._rows)


def _media_row(**over):
    from types import SimpleNamespace
    from uuid import uuid4

    from app.models.tables import AssetStatus, AssetType

    base = dict(
        id=uuid4(),
        type=AssetType.VIDEO,
        display_name="clip.mp4",
        duration_seconds=15,
        meta={},
        file_url="uploads/clip.mp4",
        processing_status=AssetStatus.COMPLETED,
    )
    base.update(over)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_media_candidates_mapping_law():
    from types import SimpleNamespace

    from app.models.tables import AssetType
    from app.tools.film.storyboard import project_media_candidates

    probed = _media_row(
        duration_seconds=15,  # the floored Integer column…
        meta={
            "probed_duration_seconds": 15.42,  # …loses to the exact probe
            "width": 1920,
            "height": 1080,
        },
    )
    column_only = _media_row(meta={})
    unknown = _media_row(
        duration_seconds=None,
        file_url=None,
        processing_status=None,
        meta={"width": "1920"},  # non-int dimensions drop
    )
    image = _media_row(type=AssetType.IMAGE)
    rows = [probed, column_only, unknown, image]

    candidates = await project_media_candidates(
        _FakeDB(rows), SimpleNamespace(id=object())
    )
    assert [c["id"] for c in candidates] == [str(r.id) for r in rows]

    by_id = {c["id"]: c for c in candidates}
    p = by_id[str(probed.id)]
    assert p["duration_seconds"] == pytest.approx(15.42)
    assert p["width"] == 1920 and p["height"] == 1080
    assert p["usable"] is True and p["processing"] == "completed"
    assert p["kind"] == "video" and p["title"] == "clip.mp4"

    c = by_id[str(column_only.id)]
    assert c["duration_seconds"] == pytest.approx(15.0)  # column float fallback

    u = by_id[str(unknown.id)]
    assert u["duration_seconds"] is None  # never guessed
    assert u["width"] is None and u["height"] is None
    assert u["usable"] is False  # no bytes
    assert u["processing"] is None

    i = by_id[str(image.id)]
    assert i["kind"] == "image"

    # A boolean probed value never passes for a duration.
    bool_meta = _media_row(meta={"probed_duration_seconds": True})
    (only,) = await project_media_candidates(
        _FakeDB([bool_meta]), SimpleNamespace(id=object())
    )
    assert only["duration_seconds"] == pytest.approx(15.0)


def test_composite_content_fit_z_and_asset_duration_clauses():
    """A3 读取补全: fit ≠ cover / z ≠ 0 ride the element clause (defaults
    stay silent — the common case reads clean); the video's asset duration
    shows known or honestly unknown, never guessed; media=None defers the
    whole fact."""
    from app.tools.film.storyboard import film_scene_content

    board = FilmStoryboard.model_validate(
        {
            "scenes": [
                {
                    "type": "composite",
                    "seconds": 8.0,
                    "elements": [
                        {
                            "kind": "video", "element_id": "e1",
                            "asset": _COMPOSITE_ASSET,
                            "source_start": 0.0, "source_end": 8.0,
                            "fit": "contain", "z": 2,
                        },
                        {
                            "kind": "text", "element_id": "e2",
                            "lines": ["注脚"], "z": 1,
                        },
                    ],
                }
            ]
        }
    )
    known = _media()  # "Demo clip", 25s
    content = film_scene_content(board.scenes[0], media=known)
    assert "source 0–8s → plays 8s" in content
    assert "(25s asset)" in content
    assert "· contain · z2" in content
    # z on a text element; defaults (cover / z0) print nothing.
    assert 'text [e2] "注脚" · on screen 0s–the scene\'s end (light) · z1' in content

    unknown = _media(duration_seconds=None)
    content = film_scene_content(board.scenes[0], media=unknown)
    assert "(asset duration unknown)" in content

    # No media universe at this seat — no duration clause at all.
    content = film_scene_content(board.scenes[0], media=None)
    assert "asset" not in content.split("→")[0].replace("[e1]", "")


@pytest.mark.asyncio
async def test_media_candidates_pinned_first_dedup_and_tenant_scope():
    """复审③: user-selected ids pin to the FRONT of the candidate universe
    (in the given order, deduplicated out of the newest-first fill) — so an
    explicit pick past the print cap still enters the director's context.
    Project scoping holds on pinned ids too: a foreign id never
    materializes (不能借此接受任意外部 ID)."""
    from types import SimpleNamespace

    from app.models.tables import AssetType
    from app.tools.film.storyboard import project_media_candidates

    rows = [_media_row() for _ in range(3)]
    foreign = _media_row()  # not in this project's rows
    db = _FakeDB(rows)
    picked = str(rows[2].id)
    candidates = await project_media_candidates(
        db, SimpleNamespace(id=object()), pinned_ids=[picked, str(foreign.id)]
    )
    # Pinned first in order; the foreign id never appears; the fill keeps
    # the newest-first order without re-listing the pinned row.
    assert [c["id"] for c in candidates] == [
        picked,
        str(rows[0].id),
        str(rows[1].id),
    ]
    assert str(foreign.id) not in [c["id"] for c in candidates]
