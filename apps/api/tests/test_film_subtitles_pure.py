"""Independent subtitles: edit/read/compile, atomic rejection and camera preservation."""
import json

import pytest
from pydantic import TypeAdapter, ValidationError
from test_film_storyboard_pure import _good_scenes, _page, _storyboard

from app.models.schemas import FilmEditOp, FilmStoryboard, SubtitleTrack
from app.tools.film.edits import (
    FilmEditError,
    apply_film_edits,
    ensure_scene_ids,
    film_version_identity_digest,
)
from app.tools.film.storyboard import build_film_spec, storyboard_presentation


def track(text="A quiet film can still have subtitles."):
    return {"cues": [{"at": 0.5, "end": 2, "text": text}],
            "style": {"background": "#000000", "color": "#FFFFFF", "enter": "fade"}}


def patch(board, value, **kwargs):
    op = TypeAdapter(FilmEditOp).validate_python(
        {"op": "set_subtitles", "scene_id": board.scenes[1].scene_id, "track": value})
    return apply_film_edits(board, {"voiceover": False}, [op], **kwargs)


def test_subtitle_crud_preserves_ui_camera_and_audio_state():
    board = ensure_scene_ids(_storyboard(_good_scenes()))
    original = build_film_spec(board, [_page()])
    result = patch(board, track())
    spec = build_film_spec(result.board, [_page()])
    assert result.params["voiceover"] is False
    assert "audio" not in spec["scenes"][1]
    assert spec["scenes"][1].pop("subtitle_track")["cues"][0]["text"] == track()["cues"][0]["text"]
    assert spec == original  # every frame, camera, page and unrelated scene survives
    assert board.scenes[1].subtitle_track is None
    assert "subtitle_track" in result.change_set.edited[0].fields
    assert track()["cues"][0]["text"] in storyboard_presentation(result.board, [_page()])
    restored = FilmStoryboard.model_validate_json(result.board.model_dump_json())
    updated = patch(restored, track("Updated text"))
    assert updated.board.scenes[1].subtitle_track.cues[0].text == "Updated text"
    deleted = patch(updated.board, None)
    assert build_film_spec(deleted.board, [_page()]) == original


def test_invalid_subtitle_and_stale_base_leave_board_untouched():
    board = ensure_scene_ids(_storyboard(_good_scenes()))
    before = board.model_dump_json()
    bad = track()
    bad["cues"][0]["end"] = 999
    with pytest.raises(FilmEditError, match="scene duration"):
        patch(board, bad)
    updated = patch(board, track()).board
    old_ref = film_version_identity_digest(board, {"voiceover": False})
    with pytest.raises(FilmEditError, match="base"):
        patch(updated, track("stale"), expected_base_digest=old_ref)
    assert board.model_dump_json() == before


@pytest.mark.parametrize("cues", [
    [{"at": 1, "end": 1, "text": "bad"}],
    [{"at": 0, "end": 2, "text": "a"}, {"at": 1, "end": 3, "text": "b"}],
    [{"at": 0, "end": 1, "text": "   "}],
])
def test_invalid_cues_rejected(cues):
    with pytest.raises(ValidationError):
        SubtitleTrack(cues=cues)


def test_old_caption_field_is_rejected():
    data = _storyboard(_good_scenes()).model_dump(mode="json")
    data["scenes"][1]["captions"] = []
    with pytest.raises(ValidationError):
        FilmStoryboard.model_validate(data)


def test_tool_wire_exposes_independent_subtitles(monkeypatch):
    from app.agents.tool_loop import tool_spec
    from app.chat.turn_tools import _DESIGN_STORYBOARD_TOOL
    monkeypatch.setattr("app.config.settings.film_edits_enabled", True)
    wire = json.dumps(tool_spec(_DESIGN_STORYBOARD_TOOL))
    for token in ("set_subtitles", "SubtitleTrack", "SubtitleCue", "fade_seconds"):
        assert token in wire


@pytest.mark.asyncio
async def test_output_read_returns_full_track_and_current_base_ref(monkeypatch):
    from test_film_output_spec_pure import (
        _base,
        _board,
        _ImageSeam,
        _output,
        _params,
        _patch_read,
        _read,
    )
    board = _board()
    board.scenes[1].subtitle_track = SubtitleTrack.model_validate(track())
    base = _base(board, cut_state="spec", cut_frames=[96, 270, 150])
    output = _output()
    _patch_read(monkeypatch, base, [_page()])
    text, _ = await _read(monkeypatch, output, _params(output), _ImageSeam())
    assert "base_ref:" in text
    assert board.scenes[1].subtitle_track.model_dump_json() in text


def test_shortened_render_window_rejects_instead_of_truncating_subtitles():
    board = ensure_scene_ids(_storyboard(_good_scenes()))
    board = patch(board, track()).board
    spec = build_film_spec(board, [_page()])
    frames = [scene["frames"] for scene in spec["scenes"]]
    frames[1] = 30
    with pytest.raises(ValueError, match="allocated scene duration"):
        build_film_spec(board, [_page()], frames=frames)
