"""Pure tests for the film edit core (R2-A — the verified editing core the
chat wiring lands on later; no DB, no LLM, no HTTP).

Gated here (the round's six required proofs + contract edges):

1. **目标版本匹配** — ``expected_base_digest`` (the READ-TIME, server-minted
   reference) is enforced against the current base: a batch minted against
   v1 rejects on v2, and content/params/scene-id binding all participate;
2. **scene ID 唯一且重排不变** — ``ensure_scene_ids`` assigns unique ids
   (collision-aware positional derivation), keeps existing ones, and a
   reorder carries each scene's id to its new position;
3. **按序原子应用** — ops apply in list order (a later op sees the earlier
   op's effect), and a rejection anywhere aborts the whole batch;
4. **失败不修改原版** — on rejection the base board/params are byte-identical
   (digest + dump), nothing partial exists;
5. **未触碰内容保持** — scenes the ops did not address stay byte-identical
   (scene-content digest equality);
6. **重排 digest 律** — a reorder moves the whole-board digest but never a
   scene's content digest; and a legacy board's digest is byte-identical to
   the pre-scene_id algorithm's output (identity never enters content).

Plus the op contract edges: copy slots per scene type, narration clear via
explicit null, no-op rejection, last-scene protection, and the injectable
validator seat rejecting atomically.
"""

import hashlib
import json

import pytest

from app.models.schemas import FilmEditOp, FilmStoryboard
from app.tools.film.edits import (
    FilmEditError,
    apply_film_edits,
    compute_change_set,
    ensure_scene_ids,
    film_version_identity_digest,
)
from app.tools.film.storyboard import scene_content_digest, storyboard_content_digest

_PARAMS = {"focus": "product", "language": "en", "music_mood": "calm", "aspect": "16:9"}


def _scenes() -> list[dict]:
    """A tiny legacy-shaped board (no scene_ids — the pre-edit-contract
    persisted shape)."""
    return [
        {"type": "hero", "seconds": 3.0, "word": "Ship faster",
         "sub": "Acme turns hours of release work into minutes.",
         "narration": "Meet Acme."},
        {"type": "divider", "seconds": 2.0, "label": "Why teams switch",
         "roll": ["Ship faster", "Start free"]},
        {"type": "ui", "seconds": 9.0, "page": 0,
         "focuses": [{"at": 0.0, "x": 0.5, "y": 0.5, "zoom": 1.0}],
         "narration": "The dashboard does the work."},
        {"type": "end", "seconds": 4.0, "name": "Acme", "tagline": "Ship faster"},
    ]


def _board(**kw) -> FilmStoryboard:
    return FilmStoryboard.model_validate({"scenes": _scenes(), **kw})


def _op(raw: dict) -> FilmEditOp:
    from pydantic import TypeAdapter

    return TypeAdapter(FilmEditOp).validate_python(raw)


def _codes(exc_info) -> str:
    return exc_info.value.code


# ---------------------------------------------------------------------------
# scene_id contract
# ---------------------------------------------------------------------------


def test_ensure_scene_ids_assigns_unique_positional_ids_to_legacy_board():
    board = ensure_scene_ids(_board())
    ids = [s.scene_id for s in board.scenes]
    assert ids == ["s1", "s2", "s3", "s4"]
    assert len(set(ids)) == 4


def test_ensure_scene_ids_keeps_existing_and_skips_collisions():
    raw = _scenes()
    raw[1]["scene_id"] = "s3"  # an id the positional scheme would also mint
    board = ensure_scene_ids(FilmStoryboard.model_validate({"scenes": raw}))
    ids = [s.scene_id for s in board.scenes]
    assert ids[1] == "s3"
    assert len(set(ids)) == 4
    assert ids[2] != "s3"  # the third scene derived around the taken id


def test_ensure_scene_ids_rejects_duplicate_ids():
    raw = _scenes()
    raw[0]["scene_id"] = "dup"
    raw[2]["scene_id"] = "dup"
    with pytest.raises(FilmEditError) as exc_info:
        ensure_scene_ids(FilmStoryboard.model_validate({"scenes": raw}))
    assert _codes(exc_info) == "duplicate_scene_id"


def test_reorder_keeps_scene_ids_attached_to_their_scene():
    base = ensure_scene_ids(_board())
    result = apply_film_edits(
        base, _PARAMS, [_op({"op": "reorder_scenes", "order": ["s4", "s1", "s3", "s2"]})]
    )
    assert [s.scene_id for s in result.board.scenes] == ["s4", "s1", "s3", "s2"]
    # The id → content mapping survived the move.
    assert result.board.scenes[0].type == "end"
    assert result.board.scenes[1].type == "hero"


# ---------------------------------------------------------------------------
# digest law (verification 5 + 6 + legacy byte-compat)
# ---------------------------------------------------------------------------


def test_legacy_board_digest_is_byte_identical_to_pre_scene_id_algorithm():
    board = _board()  # no scene_ids anywhere
    legacy_dump = board.model_dump(mode="json")
    assert all("scene_id" in s for s in legacy_dump["scenes"])  # the new field exists…
    for s in legacy_dump["scenes"]:
        del s["scene_id"]  # …and the pre-contract bytes never carried it
    pre_contract = hashlib.sha256(
        json.dumps(legacy_dump, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    assert storyboard_content_digest(board) == pre_contract


def test_assigning_ids_moves_no_digest():
    base = _board()
    with_ids = ensure_scene_ids(base)
    assert storyboard_content_digest(with_ids) == storyboard_content_digest(base)
    for with_id, plain in zip(with_ids.scenes, base.scenes, strict=True):
        assert scene_content_digest(with_id) == scene_content_digest(plain)


def test_reorder_moves_board_digest_but_never_scene_digests():
    base = ensure_scene_ids(_board())
    result = apply_film_edits(
        base, _PARAMS, [_op({"op": "reorder_scenes", "order": ["s4", "s3", "s2", "s1"]})]
    )
    assert result.result_content_digest != storyboard_content_digest(base)
    before = {s.scene_id: scene_content_digest(s) for s in base.scenes}
    after = {s.scene_id: scene_content_digest(s) for s in result.board.scenes}
    assert before == after
    # …and the change_set reports the moves with no edits.
    assert len(result.change_set.moved) == 4
    assert result.change_set.edited == [] and result.change_set.retimed == []


# ---------------------------------------------------------------------------
# ordered & atomic application (verification 3 + 4)
# ---------------------------------------------------------------------------


def test_ops_apply_in_order_later_ops_see_earlier_effects():
    result = apply_film_edits(
        _board(),
        _PARAMS,
        [
            _op({"op": "update_scene", "scene_id": "s3", "seconds": 5.0}),
            _op({"op": "remove_scene", "scene_id": "s3"}),
        ],
    )
    # The update landed first, then the removal consumed the same id.
    assert [s.scene_id for s in result.board.scenes] == ["s1", "s2", "s4"]
    removed = result.change_set.removed
    assert len(removed) == 1 and removed[0].scene_id == "s3"


def test_batch_rejection_leaves_base_byte_identical():
    base = ensure_scene_ids(_board())
    base_dump = base.model_dump(mode="json")
    params = dict(_PARAMS)
    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(
            base,
            params,
            [
                _op({"op": "update_scene", "scene_id": "s1", "seconds": 6.0}),
                _op({"op": "update_scene", "scene_id": "s9", "seconds": 6.0}),
            ],
        )
    assert _codes(exc_info) == "unknown_scene"
    assert base.model_dump(mode="json") == base_dump
    assert params == _PARAMS


def test_injected_validator_rejection_is_atomic():
    base = ensure_scene_ids(_board())
    base_dump = base.model_dump(mode="json")

    def reject(board, params):
        return ["EMPTY_CHAPTER: chapter 2 has no walk"]

    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(
            base,
            dict(_PARAMS),
            [_op({"op": "remove_scene", "scene_id": "s3"})],
            validate=reject,
        )
    assert _codes(exc_info) == "validation_failed"
    assert "EMPTY_CHAPTER" in exc_info.value.detail
    assert base.model_dump(mode="json") == base_dump


def test_empty_batch_rejects():
    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(_board(), _PARAMS, [])
    assert _codes(exc_info) == "empty_ops"


# ---------------------------------------------------------------------------
# target-version proof + untouched preservation (verification 1 + 5)
# ---------------------------------------------------------------------------


def test_expected_base_digest_matching_is_enforced():
    """目标版本匹配（真实语义）：a batch minted against one version must be
    rejected against another — content, params, and the scene-id binding all
    participate in the base identity."""
    base = _board()
    identity = film_version_identity_digest(base, _PARAMS)
    op = _op({"op": "update_scene", "scene_id": "s4", "copy_slots": {"tagline": "Go"}})

    # Matching base → applies; the result carries the identity as proof.
    result = apply_film_edits(base, dict(_PARAMS), [op], expected_base_digest=identity)
    assert result.base_identity_digest == identity
    assert result.result_content_digest != storyboard_content_digest(base)

    # A batch minted against v1 must never land on v2 (content moved).
    v2 = _board()
    v2.scenes[0].word = "Ship fastest"
    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(v2, dict(_PARAMS), [op], expected_base_digest=identity)
    assert _codes(exc_info) == "base_mismatch"

    # Params are part of the base identity (same content, moved params).
    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(
            base,
            {**_PARAMS, "music_mood": "upbeat"},
            [op],
            expected_base_digest=identity,
        )
    assert _codes(exc_info) == "base_mismatch"

    # The scene-id binding is part of the base identity (same content,
    # foreign ids) — the content digest alone could never tell.
    raw = _scenes()
    for i, scene in enumerate(raw):
        scene["scene_id"] = f"x{i + 1}"
    alien = FilmStoryboard.model_validate({"scenes": raw})
    assert storyboard_content_digest(alien) == storyboard_content_digest(base)
    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(alien, dict(_PARAMS), [op], expected_base_digest=identity)
    assert _codes(exc_info) == "base_mismatch"


def test_version_bump_invalidates_the_base_identity():
    """R3c 评审 finding ③: a recut-ONLY new version (identical content,
    identical params — retime is an execution instruction, never a param)
    still moves the base identity: a reference minted against v1 rejects on
    v2, while the version it was minted against still applies."""
    base = _board()
    op = _op({"op": "update_scene", "scene_id": "s4", "copy_slots": {"tagline": "Go"}})

    v1_ref = film_version_identity_digest(base, _PARAMS, version=1)
    v2_ref = film_version_identity_digest(base, _PARAMS, version=2)
    assert v1_ref != v2_ref  # the version number alone moves the identity

    # Same content, same params, only the version moved → the stale ref rejects.
    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(
            base, dict(_PARAMS), [op],
            expected_base_digest=v1_ref, base_version=2,
        )
    assert _codes(exc_info) == "base_mismatch"

    # The version the ref was minted against still applies.
    result = apply_film_edits(
        base, dict(_PARAMS), [op],
        expected_base_digest=v1_ref, base_version=1,
    )
    assert result.base_identity_digest == v1_ref

    # A version-less ref (legacy mint) never matches a versioned base either.
    legacy_ref = film_version_identity_digest(base, _PARAMS)
    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(
            base, dict(_PARAMS), [op],
            expected_base_digest=legacy_ref, base_version=2,
        )
    assert _codes(exc_info) == "base_mismatch"


def test_untouched_scenes_stay_byte_identical():
    base = ensure_scene_ids(_board())
    result = apply_film_edits(
        base,
        _PARAMS,
        [_op({"op": "update_scene", "scene_id": "s3", "copy_slots": {}, "seconds": 5.0,
              "narration": "Shorter line."})],
    )
    before = {s.scene_id: s.model_dump(mode="json") for s in base.scenes}
    after = {s.scene_id: s.model_dump(mode="json") for s in result.board.scenes}
    for scene_id in ("s1", "s2", "s4"):
        assert after[scene_id] == before[scene_id]
    assert scene_content_digest(result.board.scenes[2]) != scene_content_digest(base.scenes[2])
    edited = result.change_set.edited
    assert len(edited) == 1 and edited[0].scene_id == "s3"
    assert "seconds" not in edited[0].fields  # seconds deltas live in retimed
    assert edited[0].fields == ["narration"]
    retimed = result.change_set.retimed
    assert len(retimed) == 1 and retimed[0].seconds_after == 5.0


# ---------------------------------------------------------------------------
# op contract edges
# ---------------------------------------------------------------------------


def test_update_scene_copy_slots_and_unknown_keys():
    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(
            _board(), _PARAMS,
            [_op({"op": "update_scene", "scene_id": "s3", "copy_slots": {"word": "x"}})],
        )
    assert _codes(exc_info) == "unknown_copy_field"  # ui has no copy slots

    result = apply_film_edits(
        _board(), _PARAMS,
        [_op({"op": "update_scene", "scene_id": "s1", "copy_slots": {"word": "Ship fastest"}})],
    )
    assert result.board.scenes[0].word == "Ship fastest"


def test_update_scene_view_and_focuses_only_on_ui():
    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(
            _board(), _PARAMS,
            [_op({"op": "update_scene", "scene_id": "s1",
                  "view": {"page": 0, "shot": 1}})],
        )
    assert _codes(exc_info) == "field_not_applicable"

    result = apply_film_edits(
        _board(), _PARAMS,
        [_op({"op": "update_scene", "scene_id": "s3",
              "view": {"page": 1, "shot": 2, "frame": False}})],
    )
    scene = result.board.scenes[2]
    assert (scene.page, scene.shot, scene.frame) == (1, 2, False)


def test_narration_explicit_null_clears_absent_key_keeps():
    cleared = apply_film_edits(
        _board(), _PARAMS, [_op({"op": "update_scene", "scene_id": "s1", "narration": None})]
    )
    assert cleared.board.scenes[0].narration is None

    kept = apply_film_edits(
        _board(), _PARAMS, [_op({"op": "update_scene", "scene_id": "s1", "seconds": 4.0})]
    )
    assert kept.board.scenes[0].narration == "Meet Acme."


def test_update_scene_rejects_non_positive_seconds():
    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(
            _board(), _PARAMS, [_op({"op": "update_scene", "scene_id": "s1", "seconds": 0})]
        )
    assert _codes(exc_info) == "invalid_field"


def test_reorder_requires_exact_permutation():
    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(
            _board(), _PARAMS, [_op({"op": "reorder_scenes", "order": ["s1", "s2", "s3"]})]
        )
    assert _codes(exc_info) == "order_mismatch"
    with pytest.raises(FilmEditError):
        apply_film_edits(
            _board(), _PARAMS,
            [_op({"op": "reorder_scenes", "order": ["s1", "s1", "s3", "s4"]})],
        )


def test_remove_scene_protects_the_last_scene():
    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(
            _board(),
            _PARAMS,
            [_op({"op": "remove_scene", "scene_id": f"s{i}"}) for i in range(1, 5)],
        )
    assert _codes(exc_info) == "last_scene"


def test_set_music_records_mood_and_retime_and_rejects_noop():
    result = apply_film_edits(
        _board(), _PARAMS, [_op({"op": "set_music", "mood": "upbeat", "retime": "recut"})]
    )
    assert result.params["music_mood"] == "upbeat"
    music = result.change_set.music
    assert music is not None
    assert (music.mood_before, music.mood_after, music.retime) == ("calm", "upbeat", "recut")
    assert result.board.model_dump(mode="json") == ensure_scene_ids(_board()).model_dump(mode="json")

    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(_board(), _PARAMS, [_op({"op": "set_music", "mood": "calm"})])
    assert _codes(exc_info) == "noop"


def test_set_voiceover_off_records_param_and_rejects_noop():
    result = apply_film_edits(
        _board(), _PARAMS, [_op({"op": "set_voiceover", "enabled": False})]
    )
    assert result.params["voiceover"] is False
    assert result.change_set.voiceover is False

    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(
            _board(), {**_PARAMS, "voiceover": False},
            [_op({"op": "set_voiceover", "enabled": False})],
        )
    assert _codes(exc_info) == "noop"


def test_compute_change_set_reports_removed_with_type():
    before = ensure_scene_ids(_board())
    after = FilmStoryboard.model_validate(
        {"scenes": [s.model_dump(mode="json") for s in before.scenes[:3]]}
    )
    change_set = compute_change_set(before, after, _PARAMS, _PARAMS)
    assert len(change_set.removed) == 1
    assert change_set.removed[0].scene_id == "s4"
    assert change_set.removed[0].scene_type == "end"
    assert change_set.moved == [] and change_set.edited == []


# ---------------------------------------------------------------------------
# review-driven boundary locks: selection vs timing intent, whole-batch
# change judgment
# ---------------------------------------------------------------------------


def test_set_music_same_mood_recut_is_a_real_edit():
    """Re-cutting to the CURRENT track's grid is a real change — only
    same-mood + keep_cut is a noop."""
    result = apply_film_edits(
        _board(), _PARAMS, [_op({"op": "set_music", "mood": "calm", "retime": "recut"})]
    )
    music = result.change_set.music
    assert music is not None and music.retime == "recut"
    assert (music.mood_before, music.mood_after) == ("calm", "calm")
    assert result.params["music_mood"] == "calm"  # selection untouched


def test_set_music_roundtrip_keeps_surviving_retime_intent():
    """Mood out-and-back with a surviving recut directive: net selection is
    zero but the timing intent is real — the change_set must carry it."""
    result = apply_film_edits(
        _board(),
        _PARAMS,
        [
            _op({"op": "set_music", "mood": "upbeat"}),
            _op({"op": "set_music", "mood": "calm", "retime": "recut"}),
        ],
    )
    music = result.change_set.music
    assert music is not None
    assert (music.mood_before, music.mood_after, music.retime) == ("calm", "calm", "recut")


def test_fieldless_update_rejects_as_unchanged():
    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(_board(), _PARAMS, [_op({"op": "update_scene", "scene_id": "s1"})])
    assert _codes(exc_info) == "unchanged"


def test_identity_reorder_rejects_as_unchanged():
    base = ensure_scene_ids(_board())
    same_order = [s.scene_id for s in base.scenes]
    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(base, _PARAMS, [_op({"op": "reorder_scenes", "order": same_order})])
    assert _codes(exc_info) == "unchanged"


def test_edit_then_revert_rejects_as_unchanged():
    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(
            _board(),
            _PARAMS,
            [
                _op({"op": "update_scene", "scene_id": "s1",
                     "copy_slots": {"word": "Ship fastest"}}),
                _op({"op": "update_scene", "scene_id": "s1",
                     "copy_slots": {"word": "Ship faster"}}),
            ],
        )
    assert _codes(exc_info) == "unchanged"


def test_music_roundtrip_without_retiming_cancels_to_unchanged():
    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(
            _board(),
            _PARAMS,
            [
                _op({"op": "set_music", "mood": "upbeat"}),
                _op({"op": "set_music", "mood": "calm"}),
            ],
        )
    assert _codes(exc_info) == "unchanged"
