"""Shared TextPart identity law and stale-target conflict behavior."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from test_editing_edits_pure import SNAPSHOT_FACTS, valid_content

from app.editing.animation import derive_text_part_families, derive_text_parts
from app.editing.schemas import Animation
from app.editing.validators import ContentValidationError, validate_content

FIXTURE = json.loads(
    (
        Path(__file__).resolve().parents[3] / "packages/video-spec/fixtures/text_parts_golden.json"
    ).read_text()
)


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda case: case["name"])
def test_text_parts_match_shared_golden(case):
    kinds = {part["kind"] for part in case["parts"]}
    actual = derive_text_part_families(case["text"], kinds)
    assert [part.model_dump(mode="json") for part in actual] == case["parts"]


def test_text_edit_rejects_stale_part_targets_instead_of_remapping():
    content = copy.deepcopy(valid_content())
    title = content.timeline.tracks[1].clips[0]
    title.object.text = "Make it\nmove"
    lines = derive_text_parts(title.object.text, "line")
    title.animations.append(
        Animation(
            animation_id="anm_lines",
            target_object_id=title.object.object_id,
            text_part={"kind": "line", "part_ids": [part.part_id for part in lines]},
            property="opacity",
            keyframes=[{"at": 0, "value": 0}, {"at": 27000, "value": 1}],
        )
    )
    validate_content(content, SNAPSHOT_FACTS)

    title.object.text = "Make it\nchanged"
    with pytest.raises(ContentValidationError, match="re-target explicitly"):
        validate_content(content, SNAPSHOT_FACTS)
