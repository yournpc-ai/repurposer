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
    FILM_FPS,
    FILM_MAX_FRAMES,
    INVALID_COPY_REF,
    INVALID_FOCUS,
    SCENE_COUNT_LIMITS,
    SCENE_SECONDS,
    TEXT_NOT_GROUNDED,
    TOTAL_SECONDS_RANGE,
    FilmDirection,
    FilmStoryboardRejected,
    StoryboardPage,
    allocate_frames,
    assemble_storyboard,
    build_film_spec,
    build_line_manifest,
    build_skeleton,
    fixed_direction,
    format_violations,
    skeleton_prompt_dict,
    snap_frames_to_beats,
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
         "captions": [{"at": 2.0, "text": "Why teams switch"}]},
        {"type": "words", "seconds": 3.0, "dark": False, "lines": ["Ship faster"]},
        {"type": "divider", "seconds": 3.0, "label": "Why teams switch",
         "roll": ["Ship faster", "Start free"]},
        {"type": "ui", "seconds": 9.0, "page": 0,
         "focuses": [{"at": 0.0, "x": 0.5, "y": 0.5, "zoom": 1.0}],
         "captions": []},
        {"type": "end", "seconds": 4.0, "name": "Acme", "tagline": "Ship faster"},
    ]


def _codes(violations) -> set[str]:
    return {v.code for v in violations}


# Compliant filler boards (ADR-127 contract window: 8..20 scenes, 70..118s)
# — appended to focused test boards so the validator's global gates stay
# silent and each test's own point remains the only signal. Distinct
# signatures throughout (words lines are the creative channel; the divider
# kicker is code chrome).
_PAD_SCENES: list[dict] = [
    {"type": "words", "seconds": 4.0, "dark": True, "lines": ["pad one"]},
    {"type": "words", "seconds": 4.0, "dark": False, "lines": ["pad two"]},
    {"type": "divider", "seconds": 6.0, "label": "Chapter", "roll": ["Start free", "Docs"]},
    {"type": "divider", "seconds": 6.0, "label": "Chapter", "roll": ["Ship faster", "Docs"]},
    {"type": "reveal", "seconds": 6.0, "lead": "One more thing.", "word": "Acme", "sub": "Start free"},
    {"type": "hero", "seconds": 6.0, "word": "Acme", "sub": "Why teams switch"},
    {"type": "end", "seconds": 6.0, "name": "Acme", "tagline": "Why teams switch"},
    {"type": "words", "seconds": 4.0, "dark": True, "lines": ["pad three"]},
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


def test_ui_captions_ground_against_their_own_page():
    pages = [
        _page(),
        _page(title="Beta — Docs", description="Read the manual.",
              h1=["Documentation"], h2=["Reference"], buttons=["Download"],
              screenshot="user/capture/b.png"),
    ]
    scenes = [
        {"type": "ui", "seconds": 6.0, "page": 1,
         "focuses": [{"at": 0.0, "x": 0.5, "y": 0.5, "zoom": 1.0}],
         # "Why teams switch" lives on page 0, NOT page 1
         "captions": [{"at": 0.0, "text": "Why teams switch"}]},
        {"type": "hero", "seconds": 3.0, "word": "Ship faster", "sub": "Start free"},
        {"type": "end", "seconds": 3.0, "name": "Acme", "tagline": "Docs"},
    ]
    violations = validate_storyboard(_storyboard(scenes), pages)
    assert TEXT_NOT_GROUNDED in _codes(violations)


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
        "captions": [],
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


def test_assemble_fit_trims_at_word_boundary():
    pages = [_film_page()]
    lines = build_line_manifest(pages)
    title_line = lines[0].text  # "Acme — Ship faster" (18 chars, over the 16 cap)
    resolved, violations = _assemble_with(
        pages, hero_word={"line": 1, "fit": "head"},
    )
    assert violations == []
    assert resolved is not None
    word = next(s for s in resolved.scenes if s.type == "hero").word
    assert len(word) <= 16 and title_line.startswith(word) and not word.endswith(" ")
    long_line = lines[1].text  # the 46-char description
    tail, violations = _assemble_with(pages, hero_word={"line": 2, "fit": "tail"})
    assert violations == []
    assert tail is not None
    hero = next(s for s in tail.scenes if s.type == "hero")
    assert len(hero.word) <= 16 and long_line.endswith(hero.word)


def test_assemble_full_fit_over_cap_surfaces_as_constraint_violation():
    pages = [_film_page()]
    resolved, violations = _assemble_with(pages, hero_sub={"line": 2})  # full fit, ≤90: fine
    assert violations == []
    assert resolved is not None
    # The end name cap is 24 — the 20-char title fits; force an over-cap via
    # the reveal word (cap 24, the 46-char description with a full fit).
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


def test_assemble_unknown_line_and_cross_page_caption_rejected():
    pages = [
        _film_page(),
        _page(title="Beta — Docs", description="Read the manual.",
              h1=["Documentation"], h2=["Reference"], buttons=["Download"],
              screenshot="user/capture/b.png"),
    ]
    _, violations = _assemble_with(pages, hero_word={"line": 999})
    assert INVALID_COPY_REF in _codes(violations)

    # A page-1 line cited from a page-0 walk's caption is a citation error.
    _, violations = _assemble_with(
        pages,
        captions=[{"scene": "home", "text": {"line": 8}}],  # L8 lives on page 1
    )
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
    _, violations = _assemble_with(pages, cold_open=["x" * 31])
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


def test_captions_need_air():
    scenes = _good_scenes()
    scenes[1]["captions"] = [
        {"at": 1.0, "text": "Why teams switch"},
        {"at": 1.2, "text": "Start free"},  # 0.2s later — under the 0.5s floor
    ]
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
    assert focuses[1]["x"] == 0.8 and focuses[1]["zoom"] == 2.6  # 0.5/0.1 → clamp down
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
    scenes.insert(4, _plate_scene(cards=[{"big": "256 Bytes!!", "label": "Start free"},
                                         {"big": None, "label": "Why teams switch"}]))
    # big cap is 8 — also ungrounded; the cap violation is what we assert
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
    there — the model never reads the conversation's own language)."""
    from app.tools.film.storyboard import _assemble

    kwargs, _images = _assemble([], {"scenes": []}, "make it pop", None, "de", [])
    assert kwargs["language"] == "de"
    assert kwargs["skeleton"] == {"scenes": []}
    kwargs, _images = _assemble([], {"scenes": []}, None, None, None, [])
    assert kwargs["language"] is None
