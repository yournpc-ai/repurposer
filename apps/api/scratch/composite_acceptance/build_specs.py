"""Build the composite-acceptance specs through the REAL chain
(FilmStoryboard → validate_storyboard → build_film_spec, and for the edited
variant: apply_film_edits → build_film_spec), writing spec JSON for the node
render driver. The media ``key`` is the fixture's loopback URL (the local
stand-in for the absolutize seam — the driver serves it over HTTP and the
real staging path downloads it, exactly like production).

Usage: uv run python scratch/composite_acceptance/build_specs.py
Writes: specs/*.json + fixture image (panel.png)
"""

import json
from pathlib import Path

from pydantic import TypeAdapter

from app.models.schemas import FilmEditOp, FilmStoryboard
from app.tools.film.edits import apply_film_edits
from app.tools.film.storyboard import (
    StoryboardMedia,
    StoryboardMediaAsset,
    build_film_spec,
    build_text_manifest,
    validate_storyboard,
)

HERE = Path(__file__).parent
FIXTURE_URL = "http://127.0.0.1:8799/fixture/source_25s.mp4"
IMAGE_URL = "http://127.0.0.1:8799/fixture/panel.png"
ASSET_ID = "11111111-1111-1111-1111-111111111111"
IMAGE_ASSET_ID = "22222222-2222-2222-2222-222222222222"
# The fixture's text-source corpus (the anchor's on-screen copy).
FIXTURE_TEXT = "开场三秒\n左边文字\n逐字出现\n收尾"

# The acceptance anchor's timeline: words 0–3s · composite 3–11s · tail 3s.
FRAMES = [90, 240, 90]

TEXT_ELEMENT = {
    "kind": "text",
    "lines": ["左边文字", "逐字出现"],
    # tone = ink tone: dark ink over the light canvas so the probe can see it.
    "tone": "dark",
    "at": 1.0,
    "until": 7.0,
    "rect": {"x": 0.06, "y": 0.2, "w": 0.38, "h": 0.6},
    "enter": "words",
    "enter_interval": 0.3,
}


def _media(video_key: str = FIXTURE_URL) -> StoryboardMedia:
    return StoryboardMedia(
        assets={
            ASSET_ID: StoryboardMediaAsset(
                id=ASSET_ID, key=video_key, kind="video", title="Fixture 25s",
                duration_seconds=25.0, width=1280, height=720,
            ),
            IMAGE_ASSET_ID: StoryboardMediaAsset(
                id=IMAGE_ASSET_ID, key=IMAGE_URL, kind="image",
                title="Panel", duration_seconds=None, width=1280, height=720,
            ),
        }
    )


def _anchor_board() -> FilmStoryboard:
    return FilmStoryboard.model_validate(
        {
            "name": "acceptance-anchor",
            "scenes": [
                {"type": "words", "seconds": 3.0, "dark": False,
                 "lines": ["开场三秒"]},
                {
                    "type": "composite",
                    "seconds": 8.0,
                    "elements": [
                        {
                            "kind": "video",
                            "asset": ASSET_ID,
                            "source_start": 10.0,
                            "source_end": 18.0,
                            "at": 0.0,
                            "rect": {"x": 0.5, "y": 0.0, "w": 0.5, "h": 1.0},
                            "keep_audio": False,
                        },
                        dict(TEXT_ELEMENT),
                    ],
                },
                {"type": "words", "seconds": 3.0, "dark": True,
                 "lines": ["收尾"]},
            ],
        }
    )


def _build(board: FilmStoryboard, name: str) -> dict:
    media = _media()
    # The fixture is a TEXT-source film and must satisfy that mode's COMPLETE
    # validator — zero violations, nothing filtered out (复审: 筛掉违例 =
    # 冒充合法全链).
    violations = validate_storyboard(
        board, [], text_lines=build_text_manifest(FIXTURE_TEXT), media=media
    )
    assert violations == [], [f"{v.code}: {v.detail}" for v in violations]
    spec = build_film_spec(board, [], frames=FRAMES, media=media)
    out = HERE / "specs" / f"{name}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(spec, ensure_ascii=False, indent=1))
    print(f"spec {name}: scenes={[s['type'] for s in spec['scenes']]}")
    return spec


def main() -> None:
    # The fixture image (a distinctive solid panel with a big marker).
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (1280, 720), (200, 60, 40))
    d = ImageDraw.Draw(img)
    d.text((80, 280), "IMG", font=ImageFont.load_default(size=260), fill=(255, 255, 255))
    img.save(HERE / "panel.png")

    # 1. The anchor (A): video source 10–18s on the right from output 3s,
    #    text on the left from output 4s, word-by-word at 0.3s.
    _build(_anchor_board(), "anchor")

    # 2. E leg: same anchor but the video keeps its original sound.
    audio_board = _anchor_board()
    audio_scene = next(s for s in audio_board.scenes if s.type == "composite")
    audio_scene.elements[0].keep_audio = True
    _build(audio_board, "anchor_keep_audio")

    # 3. B legs: the SAME text params over an image background (composite +
    #    image element) and over the bare theme canvas (a MEDIA-FREE
    #    composite of two independent text elements — legal since the
    #    2026-10-23 review removed the media-element requirement; words
    #    stays the convenient full-canvas recipe, never a forced funnel).
    image_board = _anchor_board()
    image_scene = next(s for s in image_board.scenes if s.type == "composite")
    # An image element is a different schema — rebuild honestly.
    from app.models.schemas import FilmElementImage, FilmElementText

    image_scene.elements[0] = FilmElementImage(
        kind="image", asset=IMAGE_ASSET_ID, at=0.0,
        rect={"x": 0.5, "y": 0.0, "w": 0.5, "h": 1.0}, fit="cover",
    )
    _build(image_board, "bg_image")

    plain_board = _anchor_board()
    plain_scene = next(s for s in plain_board.scenes if s.type == "composite")
    note = dict(TEXT_ELEMENT)
    note.update(
        lines=["底部注释"], at=2.0, until=6.0,
        rect={"x": 0.05, "y": 0.82, "w": 0.5, "h": 0.14},
    )
    plain_scene.elements = [
        plain_scene.elements[1],  # the title text element, unchanged
        FilmElementText.model_validate(note),  # a second, independent window
    ]
    _build(plain_board, "bg_plain")

    # 4. C leg: the anchor through the REAL edit chain — update_element
    #    changes the text content, the entrance interval and the window end
    #    (until 7→6: the edited text leaves the screen EARLY, a probe-visible
    #    difference); the video element and everything else stay untouched.
    edited = apply_film_edits(
        _anchor_board(),
        {"voiceover": False},
        [
            TypeAdapter(FilmEditOp).validate_python(
                {
                    "op": "update_element",
                    "scene_id": "s2",
                    "element_id": "e2",
                    "lines": ["改后的文字", "新的节奏"],
                    "enter_interval": 0.5,
                    "until": 6.0,
                }
            )
        ],
    )
    spec = _build(edited.board, "edited_v2")
    scene = next(s for s in spec["scenes"] if s["type"] == "composite")
    video = scene["elements"][0]
    assert video["source_start"] == 10.0 and video["source_end"] == 18.0
    assert video["rect"] == {"x": 0.5, "y": 0.0, "w": 0.5, "h": 1.0}
    text = scene["elements"][1]
    assert text["lines"] == ["改后的文字", "新的节奏"]
    assert text["enter_interval"] == 0.5 and text["until"] == 6.0
    print("edited change_set:", [e.fields for e in edited.change_set.edited])

    print("ALL SPECS BUILT")


if __name__ == "__main__":
    main()
