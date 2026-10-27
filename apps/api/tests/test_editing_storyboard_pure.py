"""Minimal DTO / fixture law for the future Chat surface (VIDEO_PROJECT
§10.3): the canonical storyboard payload is generated from a SAVED
version's content (never re-transcribed by the LLM), and the Output DTO
carries the Composition lineage. Presentation components build against
these shapes; nothing here returns component props or model-authored copy.
"""

from __future__ import annotations

from uuid import UUID

from app.editing.store import content_digest_of
from app.editing.storyboard import storyboard_payload
from test_editing_edits_pure import valid_content

COMP_ID = UUID("33333333-3333-3333-3333-333333333333")
VER_ID = UUID("44444444-4444-4444-4444-444444444444")


def test_storyboard_payload_is_canonical_and_factual():
    content = valid_content()
    payload = storyboard_payload(
        content,
        composition_id=COMP_ID,
        version_id=VER_ID,
        version=1,
        content_digest=content_digest_of(content),
    )
    assert payload["composition_id"] == str(COMP_ID)
    assert payload["composition_version_id"] == str(VER_ID)
    assert payload["version"] == 1
    assert payload["settings"] == {"width": 1920, "height": 1080, "fps": 30.0}

    (scene,) = payload["scenes"]
    assert scene["scene_id"] == "scn_open"
    assert scene["range_seconds"] == {"start": 0.0, "end": 4.0}
    assert scene["intent"] == "opening"
    # The music bed has no scene attribution — it surfaces as unassigned,
    # never silently dropped from the readout.
    kinds = {(c["clip_id"], c["object_kind"]) for c in scene["clips"]}
    assert kinds == {("clp_bg", "image"), ("clp_title", "text")}
    assert [c["clip_id"] for c in payload["unassigned_clips"]] == ["clp_bed"]
    title = next(c for c in scene["clips"] if c["clip_id"] == "clp_title")
    assert title["text"] == "Hello"
    assert title["range_seconds"] == {"start": 1.0, "end": 4.0}
