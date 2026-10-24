"""Spec round-trip smoke: build a film spec exercising the new text-plane
fields (exit/motion_scale/align/size/accent_style, tone=accent, theme
accent) and dump it for the renderer's zod schema to parse."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.schemas import (
    FilmElementRect,
    FilmElementText,
    FilmSceneComposite,
    FilmSceneWords,
    FilmStoryboard,
    FilmStoryboardTheme,
)
from app.tools.film.storyboard import build_film_spec, validate_storyboard

board = FilmStoryboard(
    name="spec-smoke",
    language="zh",
    theme=FilmStoryboardTheme(canvas="#F7F6F2", ink="#141414", accent="#FF6A1B"),
    scenes=[
        FilmSceneWords(
            type="words",
            scene_id="s1",
            seconds=3.0,
            dark=True,
            lines=["*短词组*", "第二行"],
            enter="words",
            enter_interval=0.1,
            enter_duration=0.25,
            exit_duration=0.3,
            motion="push",
            motion_scale=1.03,
            align="center",
            size="large",
            accent_style="color",
        ),
        FilmSceneComposite(
            type="composite",
            scene_id="s2",
            seconds=4.0,
            dark=False,
            elements=[
                FilmElementText(
                    kind="text",
                    element_id="t1",
                    lines=["第一行先出现"],
                    tone="light",
                    at=0.0,
                    until=4.0,
                    rect=FilmElementRect(x=0.1, y=0.3, w=0.8, h=0.2),
                    align="center",
                    size="large",
                    exit_duration=0.3,
                ),
                FilmElementText(
                    kind="text",
                    element_id="t2",
                    lines=["第二行晚一点"],
                    tone="accent",
                    at=0.8,
                    until=4.0,
                    rect=FilmElementRect(x=0.1, y=0.55, w=0.8, h=0.2),
                    align="center",
                    size="medium",
                    motion="push",
                    motion_scale=1.02,
                    accent_style="color",
                ),
            ],
        ),
    ],
)

violations = validate_storyboard(board, [], text_lines=[])
if violations:
    for v in violations:
        print("VIOLATION:", v.code, v.detail)
    sys.exit(1)

spec = build_film_spec(board, [])
json.dump(spec, sys.stdout, ensure_ascii=False, indent=1)
print()
