"""Pure SFX audio revision journey: new-source binding, windows and identity."""
from __future__ import annotations

import copy
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.editing.edits import apply_ops
from app.editing.service import (
    VideoServiceError,
    revision_snapshot_ids,
    translate_revision,
)
from app.editing.timing import SOURCE_TIMEBASE
from app.editing.validators import validate_content
from app.models.schemas import ReviseVideoArgs
from test_editing_edits_pure import SNAPSHOT_FACTS, valid_content

COMP_ID = UUID("99999999-9999-9999-9999-999999999999")
VER_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
NEW_SNAPSHOT = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
NEW_DIGEST = "e" * 64


def _args(edit: dict) -> ReviseVideoArgs:
    return ReviseVideoArgs.model_validate({
        "base_ref": {
            "composition_id": str(COMP_ID),
            "composition_version_id": str(VER_ID),
            "content_digest": "f" * 64,
        },
        "edits": [edit],
    })


def _facts(duration_seconds: float = 8):
    facts = copy.deepcopy(SNAPSHOT_FACTS)
    facts[NEW_SNAPSHOT] = {
        "digest": NEW_DIGEST,
        "kind": "audio",
        "duration_ticks": round(duration_seconds * SOURCE_TIMEBASE),
        "owner_id": next(iter(SNAPSHOT_FACTS.values()))["owner_id"],
        "storage_key": "snapshots/sfx.mp3",
        "meta": {},
    }
    return facts


def _apply(base, ops, facts):
    return apply_ops(
        base,
        ops,
        {snapshot_id: fact["digest"] for snapshot_id, fact in facts.items()},
    )


def _clip(content, clip_id: str):
    return next(
        clip
        for track in content.timeline.tracks
        for clip in track.clips
        if clip.clip_id == clip_id
    )


def test_add_audio_binds_base_plus_new_digest_and_uses_real_full_duration():
    base = valid_content()
    facts = _facts()
    args = _args({
        "op": "add_audio",
        "snapshot_id": str(NEW_SNAPSHOT),
        "at_seconds": 1.25,
        "gain_db": -8,
        "scene_id": "scn_open",
    })
    assert revision_snapshot_ids(args) == {NEW_SNAPSHOT}
    ops = translate_revision(base, args, request_id="sfx-add", snapshots=facts)
    candidate = _apply(base, ops, facts)
    validate_content(candidate, facts)
    binding = next(b for b in candidate.sources if b.snapshot_id == NEW_SNAPSHOT)
    assert binding.snapshot_digest == NEW_DIGEST
    added = next(
        clip
        for track in candidate.timeline.tracks
        if track.role == "effect"
        for clip in track.clips
    )
    assert added.range.start == round(1.25 * SOURCE_TIMEBASE)
    assert added.range.duration == 8 * SOURCE_TIMEBASE
    assert added.source.source_range.start == 0
    assert added.source.source_range.end == 8 * SOURCE_TIMEBASE
    assert added.source.snapshot_digest == NEW_DIGEST
    assert added.object.gain_db == -8


def test_update_audio_preserves_identity_output_and_complete_source_window():
    base = valid_content()
    before = _clip(base, "clp_bed")
    facts = _facts()
    args = _args({
        "op": "update_audio",
        "clip_id": "clp_bed",
        "snapshot_id": str(NEW_SNAPSHOT),
        "gain_db": -6,
    })
    ops = translate_revision(base, args, request_id="sfx-replace", snapshots=facts)
    candidate = _apply(base, ops, facts)
    validate_content(candidate, facts)
    after = _clip(candidate, "clp_bed")
    assert after.clip_id == before.clip_id
    assert after.object.object_id == before.object.object_id
    assert after.range == before.range
    assert after.scene_id == before.scene_id
    assert after.object.gain_db == -6
    assert after.source.snapshot_id == NEW_SNAPSHOT
    assert after.source.snapshot_digest == NEW_DIGEST
    assert after.source.source_range == before.source.source_range
    assert after.source.source_range.duration == after.range.duration

    short_facts = _facts(duration_seconds=3)
    with pytest.raises(VideoServiceError, match="complete original source window"):
        translate_revision(base, args, snapshots=short_facts)


def test_update_audio_requires_a_real_non_null_change():
    with pytest.raises(ValidationError, match="replacement snapshot or gain_db"):
        _args({"op": "update_audio", "clip_id": "clp_bed"})
    with pytest.raises(ValidationError, match="replacement snapshot or gain_db"):
        _args({
            "op": "update_audio",
            "clip_id": "clp_bed",
            "snapshot_id": None,
            "gain_db": None,
        })


def test_update_audio_gain_only_remains_a_legal_single_field_revision():
    base = valid_content()
    before = _clip(base, "clp_bed")
    args = _args({"op": "update_audio", "clip_id": "clp_bed", "gain_db": -3})
    ops = translate_revision(base, args, request_id="sfx-gain", snapshots=_facts())
    candidate = _apply(base, ops, _facts())
    after = _clip(candidate, "clp_bed")
    assert after.object.gain_db == -3
    assert after.source == before.source
    assert after.range == before.range
