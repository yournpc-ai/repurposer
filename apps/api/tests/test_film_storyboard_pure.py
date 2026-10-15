"""Pure tests for the film storyboard validator / allocator / spec builder.

No database, no LLM, no HTTP — StoryboardPage carriers are built in memory.
These lock the deterministic contract between the LLM's storyboard and the
render chain: grounding (every on-screen string traces to the capture
manifest), camera bounds, duration intents, content caps, and the frame
allocator's structural floors.
"""

from __future__ import annotations

import pytest

from app.models.schemas import FilmStoryboard, PageElement, ShotRef, WebPageResearch
from app.tools.film.storyboard import (
    CONSTRAINT_VIOLATION,
    DURATION_INVALID,
    FILM_FPS,
    FILM_MAX_FRAMES,
    INVALID_FOCUS,
    TEXT_NOT_GROUNDED,
    FilmStoryboardRejected,
    StoryboardPage,
    allocate_frames,
    build_film_spec,
    format_violations,
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
        {"type": "ui", "seconds": 6.0, "page": 0,
         "focuses": [{"at": 0.0, "x": 0.5, "y": 0.5, "zoom": 1.0},
                     {"at": 2.0, "x": 0.3, "y": 0.4, "zoom": 2.0}],
         "captions": [{"at": 2.0, "text": "Why teams switch"}]},
        {"type": "end", "seconds": 3.0, "name": "Acme", "tagline": "Ship faster"},
    ]


def _codes(violations) -> set[str]:
    return {v.code for v in violations}


# ---- grounding ---------------------------------------------------------------


def test_clean_storyboard_passes():
    assert validate_storyboard(_storyboard(_good_scenes()), [_page()]) == []


def test_verbatim_quote_and_trim_hit():
    scenes = [
        # exact H1
        {"type": "words", "seconds": 3.5, "dark": False, "lines": ["Ship faster"]},
        # a trim of the description (leading words dropped)
        {"type": "words", "seconds": 3.5, "dark": True, "lines": ["release work into minutes"]},
        {"type": "hero", "seconds": 5.0, "word": "Acme", "sub": "Start free"},
    ]
    assert validate_storyboard(_storyboard(scenes), [_page()]) == []


def test_emphasis_marks_and_case_are_normalized():
    scenes = [
        {"type": "hero", "seconds": 4.0, "word": "*Ship* faster!", "sub": "ACME"},
        {"type": "words", "seconds": 4.0, "dark": False, "lines": ["ship faster"]},
        {"type": "end", "seconds": 4.0, "name": "Acme", "tagline": "Start free"},
    ]
    assert validate_storyboard(_storyboard(scenes), [_page()]) == []


def test_invented_copy_rejected():
    scenes = _good_scenes()
    scenes[0]["sub"] = "The number one platform loved by millions."
    violations = validate_storyboard(_storyboard(scenes), [_page()])
    assert TEXT_NOT_GROUNDED in _codes(violations)


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
    scenes[1]["focuses"] = [{"at": 6.0, "x": 0.5, "y": 0.5, "zoom": 1.0}]  # scene is 6s: at must be < 6
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
    scenes[0]["seconds"] = 9.0  # hero cap is 5
    assert DURATION_INVALID in _codes(validate_storyboard(_storyboard(scenes), [_page()]))


def test_total_seconds_window():
    # 3 scenes × hero-min is fine; a single 1.5s words scene total < 12s fails
    scenes = [{"type": "words", "seconds": 1.5, "dark": False, "lines": ["Ship faster"]}]
    violations = validate_storyboard(_storyboard(scenes), [_page()])
    assert DURATION_INVALID in _codes(violations)


def test_scene_count_window():
    two = _good_scenes()[:2]
    assert CONSTRAINT_VIOLATION in _codes(validate_storyboard(_storyboard(two), [_page()]))
    nine = _good_scenes() + [
        {"type": "words", "seconds": 2.0, "dark": False, "lines": [f"Ship faster {i}"]}
        for i in range(6)
    ]
    # the words lines are ungrounded too — the count violation is what we assert
    assert CONSTRAINT_VIOLATION in _codes(validate_storyboard(_storyboard(nine), [_page()]))


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
    scenes[2]["tagline"] = "Ship faster"  # == hero.word, different slot/scene
    assert validate_storyboard(_storyboard(scenes), [_page()]) == []


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
    assert validate_storyboard(_storyboard(scenes), [page]) == []
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
    assert validate_storyboard(_storyboard(scenes), [page]) == []
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
    # hero 3.0s → 90; ui 6.0s → 180; end 3.0s → 90 (over the 75 floor)
    assert frames == [90, 180, 90]
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
    # 120 BPM bed → beats every 0.5s = 15 frames. Boundaries at 90/270/360:
    # 90 lands exactly on beat 6; 270 → 15*18=270 exact; nothing moves.
    storyboard = _storyboard(_good_scenes())
    frames = allocate_frames(storyboard)  # [90, 180, 90]
    beats = [i * 0.5 for i in range(25)]
    snapped = snap_frames_to_beats(storyboard, frames, beats)
    assert snapped == frames  # already on-grid
    assert sum(snapped) == sum(frames)


def test_snap_frames_to_beats_snaps_off_grid_boundary():
    storyboard = _storyboard(_good_scenes())
    frames = allocate_frames(storyboard)  # [90, 180, 90]
    # Beat at 96 (3.2s) pulls boundary 90 up by 6 (the tolerance edge);
    # beat at 264 (8.8s) then pulls boundary 270 down by 6 — the ui scene
    # gives both deltas (180→168), the end scene absorbs them (+6→96).
    beats = [3.2, 8.8]
    snapped = snap_frames_to_beats(storyboard, frames, beats)
    assert snapped == [96, 168, 96]
    assert sum(snapped) == sum(frames)


def test_snap_frames_to_beats_respects_tolerance_and_floors():
    storyboard = _storyboard(_good_scenes())
    frames = allocate_frames(storyboard)  # [90, 180, 90], ui floor = 90
    # Boundary 90's nearest beat at frame 100 is 10 frames away > 6-frame
    # tolerance: untouched. Boundary 270's beat at 264 moves 6 off the ui
    # scene — 180-6=174 ≥ floor 90, legal; the end scene absorbs +6.
    snapped = snap_frames_to_beats(storyboard, frames, [100 / FILM_FPS, 8.8])
    assert snapped == [90, 174, 96]
    # A beat far past both boundaries (frame 340) is refused at each —
    # deltas 250/70 both blow the tolerance, so nothing moves.
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
    end = spec["scenes"][2]
    assert end["url"] == "example.com"
    assert end["logo_url"] is None
    assert sum(s["frames"] for s in spec["scenes"]) == 360
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
