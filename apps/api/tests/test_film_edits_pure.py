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
from app.tools.film.storyboard import (
    build_text_manifest,
    canonical_film_params,
    scene_content_digest,
    storyboard_content_digest,
    validate_storyboard,
)

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


def test_branch_same_number_versions_with_different_cuts_never_share_a_ref():
    """复审遗留问题①: branch lineages can mint SAME-numbered versions with
    identical content and params (a pinned branch re-applying the base's
    own patch) whose TIMELINE state differs — 冻结时间轴 = 版本状态, so the
    frozen cut rides the base identity: their references never coincide,
    and a ref minted against one rejects on the other."""
    base = _board()
    op = _op({"op": "update_scene", "scene_id": "s4", "copy_slots": {"tagline": "Go"}})

    ref_frozen = film_version_identity_digest(
        base, _PARAMS, version=2, cut=("kept", [96, 270, 150], [None, 60, None])
    )
    ref_draft = film_version_identity_digest(base, _PARAMS, version=2)
    ref_spec = film_version_identity_digest(
        base, _PARAMS, version=2, cut=("spec", [100, 260, 155], None)
    )
    # Same content, same params, same version NUMBER — the cut alone splits
    # the identity (a draft's derived plan timeline binds nothing).
    assert len({ref_frozen, ref_draft, ref_spec}) == 3

    # The read showed a frozen cut; the current same-number version is a
    # plain draft → the ref rejects before any op applies.
    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(
            base, dict(_PARAMS), [op],
            expected_base_digest=ref_frozen, base_version=2,
        )
    assert _codes(exc_info) == "base_mismatch"

    # The frozen-cut base itself still applies.
    result = apply_film_edits(
        base, dict(_PARAMS), [op],
        expected_base_digest=ref_frozen, base_version=2,
        base_cut=("kept", [96, 270, 150], [None, 60, None]),
    )
    assert result.base_identity_digest == ref_frozen


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


def test_set_voiceover_on_reopens_existing_narration_lines():
    """音频三态 (闸 21): re-opening voiceover synthesizes the version's OWN
    narration lines at run time — zero redesign: the board rides through
    byte-identical, only the param flips."""
    result = apply_film_edits(
        _board(), {**_PARAMS, "voiceover": False},
        [_op({"op": "set_voiceover", "enabled": True})],
    )
    assert result.params["voiceover"] is True
    assert result.change_set.voiceover is True
    assert result.board.model_dump(mode="json") == ensure_scene_ids(
        _board()
    ).model_dump(mode="json")


def test_set_voiceover_on_without_narration_is_a_content_gap_refusal():
    """旁白存在律 (闸 21): zero narration lines + voiceover on ⇒ a structured
    CONTENT-gap refusal (voiceover_needs_narration — never a synthesis/voice
    failure); the law judges the POST-batch board, so one batch may author
    the lines and re-enable in the same pass (voiceover op listed FIRST —
    order-independence proof)."""
    silent = FilmStoryboard.model_validate(
        {"scenes": [
            {k: v for k, v in s.items() if k != "narration"} for s in _scenes()
        ]}
    )
    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(
            silent, {**_PARAMS, "voiceover": False},
            [_op({"op": "set_voiceover", "enabled": True})],
        )
    assert _codes(exc_info) == "voiceover_needs_narration"

    result = apply_film_edits(
        silent, {**_PARAMS, "voiceover": False},
        [
            _op({"op": "set_voiceover", "enabled": True}),
            _op({"op": "update_scene", "scene_id": "s1", "narration": "Meet Acme."}),
        ],
    )
    assert result.params["voiceover"] is True
    assert result.change_set.voiceover is True


def test_set_voiceover_on_noop_when_already_on():
    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(
            _board(), _PARAMS, [_op({"op": "set_voiceover", "enabled": True})]
        )
    assert _codes(exc_info) == "noop"


def test_set_music_off_is_a_real_terminal_state():
    """音频三态 (闸 21): the explicit OFF is a selection of its own — pinned
    as music_mood 'off' (distinct from unset AND from any mood), reported
    in the change set; off→off is a noop; a later named mood re-opens the
    bed through the same op."""
    result = apply_film_edits(
        _board(), _PARAMS, [_op({"op": "set_music", "mood": "off"})]
    )
    assert result.params["music_mood"] == "off"
    music = result.change_set.music
    assert music is not None
    assert (music.mood_before, music.mood_after, music.retime) == ("calm", "off", "keep_cut")

    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(
            _board(), {**_PARAMS, "music_mood": "off"},
            [_op({"op": "set_music", "mood": "off"})],
        )
    assert _codes(exc_info) == "noop"

    reopened = apply_film_edits(
        _board(), {**_PARAMS, "music_mood": "off"},
        [_op({"op": "set_music", "mood": "calm"})],
    )
    assert reopened.params["music_mood"] == "calm"
    assert reopened.change_set.music is not None
    assert reopened.change_set.music.mood_before == "off"


def test_music_off_canonical_pins_distinct_from_unset():
    """The OFF pin is a real fingerprint state: canonical keeps it (an unset
    null drops out, an off pins), so a version born off never reads as
    merely unspecified — the resolution chain would otherwise resolve the
    calm default back in."""
    assert canonical_film_params({"music_mood": "off"})["music_mood"] == "off"
    assert "music_mood" not in canonical_film_params({})
    assert canonical_film_params({"music_mood": "off"}) != canonical_film_params({})


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


# ---------------------------------------------------------------------------
# text-plane vocabulary (motion/enter) + the text source's corpus sync
# ---------------------------------------------------------------------------

_TEXT_COPY = (
    "好的内容，不该只出现一次。\n"
    "一场分享，可以长成文章、短片和讨论。\n"
    "你把专业讲清楚，助手负责送到更多人面前。"
)


def _text_board() -> FilmStoryboard:
    return FilmStoryboard.model_validate(
        {
            "name": None,
            "language": "zh",
            "scenes": [
                {"type": "words", "seconds": 4.0, "dark": False,
                 "lines": ["好的内容，不该只出现一次。"]},
                {"type": "words", "seconds": 5.0, "dark": True,
                 "lines": ["一场分享，可以长成文章、短片和讨论。"]},
                {"type": "words", "seconds": 5.0, "dark": False,
                 "lines": ["你把专业讲清楚，助手负责送到更多人面前。"]},
            ],
        }
    )


_TEXT_PARAMS = {
    "text": _TEXT_COPY,
    "verbatim": True,
    "target_seconds": 14.0,
    "voiceover": False,
    "aspect": "9:16",
}


def test_words_motion_and_enter_apply_and_report_in_the_change_set():
    result = apply_film_edits(
        _text_board(),
        dict(_TEXT_PARAMS),
        [_op({"op": "update_scene", "scene_id": "s2",
              "motion": "push", "enter": "words"})],
    )
    scene = result.board.scenes[1]
    assert scene.motion == "push" and scene.enter == "words"
    edited = {e.scene_id: e.fields for e in result.change_set.edited}
    assert edited == {"s2": ["enter", "motion"]}
    # A vocabulary-only batch never touches the pinned text (修改只影响声明范围).
    assert result.params["text"] == _TEXT_COPY


def test_motion_and_enter_are_words_only_fields():
    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(
            _board(), _PARAMS,
            [_op({"op": "update_scene", "scene_id": "s1", "motion": "push"})],
        )
    assert _codes(exc_info) == "field_not_applicable"
    # A value outside the closed enum never reaches the apply layer — the op
    # adapter rejects it at the wire.
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _op({"op": "update_scene", "scene_id": "s1", "enter": "sentences"})


def test_text_source_follows_an_explicit_copy_edit():
    result = apply_film_edits(
        _text_board(),
        dict(_TEXT_PARAMS),
        [_op({"op": "update_scene", "scene_id": "s2",
              "copy_slots": {"lines": ["一次分享，也能持续长出新的讨论。"]}})],
    )
    text = result.params["text"]
    # The new version's corpus IS what the board now says: the user's
    # replacement in, the replaced line out, untouched scenes byte-identical.
    assert "一次分享，也能持续长出新的讨论。" in text
    assert "一场分享，可以长成文章、短片和讨论。" not in text
    assert "好的内容，不该只出现一次。" in text
    assert "你把专业讲清楚，助手负责送到更多人面前。" in text
    # The copy is part of the text film's identity: the fingerprint moves.
    from app.tools.film.storyboard import storyboard_fingerprint

    assert storyboard_fingerprint(
        [{"tool": "launch_film", "params": result.params}], None
    ) != storyboard_fingerprint(
        [{"tool": "launch_film", "params": _TEXT_PARAMS}], None
    )


def test_text_source_pin_survives_non_copy_batches_byte_stable():
    for ops in (
        [_op({"op": "update_scene", "scene_id": "s1", "seconds": 5.0})],
        [_op({"op": "update_scene", "scene_id": "s3", "narration": "旁白一句"})],
        [_op({"op": "reorder_scenes", "order": ["s1", "s2", "s3"]}),
         _op({"op": "set_voiceover", "enabled": True}),
         _op({"op": "update_scene", "scene_id": "s2", "narration": "再一句"})],
    ):
        result = apply_film_edits(_text_board(), dict(_TEXT_PARAMS), ops)
        assert result.params["text"] == _TEXT_COPY


def test_web_films_never_grow_a_text_pin():
    result = apply_film_edits(
        _board(), dict(_PARAMS),
        [_op({"op": "update_scene", "scene_id": "s1",
              "copy_slots": {"word": "Ship fastest"}})],
    )
    assert "text" not in result.params


# ---------------------------------------------------------------------------
# copy_text anchoring + emphasis survival (逐字律的编辑侧: the pinned text
# re-derives from each scene's PRE-WRAP anchor — a display wrap is never a
# paragraph break — and an emphasis that still corresponds exactly survives
# a copy edit, with any honest loss NAMED in the change set)
# ---------------------------------------------------------------------------

_ANCHOR_TEXT_PARAMS = {
    "text": "你把专业讲清楚，助手负责送到更多人面前。\n好内容值得持续被看见",
    "language": "zh",
}


def _anchor_text_board(*, anchored: bool = True) -> FilmStoryboard:
    """A two-scene words board whose FIRST scene's display pair is a visual
    wrap of one sentence (the incident shape)."""
    scenes = [
        {"type": "words", "seconds": 4.0, "dark": False,
         "lines": ["你把专业讲清楚，助手负责", "送到更多人面前。"]},
        {"type": "words", "seconds": 4.0, "dark": True,
         "lines": ["好内容值得 *持续被看见*"]},
    ]
    if anchored:
        scenes[0]["copy_text"] = "你把专业讲清楚，助手负责送到更多人面前。"
        scenes[1]["copy_text"] = "好内容值得持续被看见"
    return FilmStoryboard.model_validate({"scenes": scenes})


def test_copy_edit_keeps_untouched_scenes_pre_wrap_source_in_the_pin():
    """The incident regression (折行污染): editing one scene must not turn
    another scene's visual wrap into a paragraph break in the pinned text."""
    base = ensure_scene_ids(_anchor_text_board())
    result = apply_film_edits(
        base, dict(_ANCHOR_TEXT_PARAMS),
        [_op({"op": "update_scene", "scene_id": "s2",
              "copy_slots": {"lines": ["好内容值得被更多人看见"]}})],
    )
    assert result.params["text"] == (
        "你把专业讲清楚，助手负责送到更多人面前。\n好内容值得被更多人看见"
    )
    # The edited scene re-anchored to its authored copy (accent-free).
    assert result.board.scenes[1].copy_text == "好内容值得被更多人看见"
    assert result.board.scenes[0].copy_text == "你把专业讲清楚，助手负责送到更多人面前。"


def test_legacy_board_without_anchor_falls_back_to_display_lines():
    """Legacy boards carry no anchor: the corpus projection honestly falls
    back to the display strings (documented legacy shape, never a guess
    re-join)."""
    base = ensure_scene_ids(_anchor_text_board(anchored=False))
    result = apply_film_edits(
        base, dict(_ANCHOR_TEXT_PARAMS),
        [_op({"op": "update_scene", "scene_id": "s2",
              "copy_slots": {"lines": ["好内容值得被更多人看见"]}})],
    )
    assert result.params["text"] == (
        "你把专业讲清楚，助手负责\n送到更多人面前。\n好内容值得被更多人看见"
    )
    # The edited scene got its anchor even on a legacy base.
    assert result.board.scenes[1].copy_text == "好内容值得被更多人看见"
    assert result.board.scenes[0].copy_text is None


def test_non_copy_edit_keeps_the_pin_byte_stable():
    base = ensure_scene_ids(_anchor_text_board())
    result = apply_film_edits(
        base, dict(_ANCHOR_TEXT_PARAMS),
        [_op({"op": "update_scene", "scene_id": "s2", "dark": False})],
    )
    assert result.params["text"] == _ANCHOR_TEXT_PARAMS["text"]


def test_copy_edit_remarks_an_exactly_corresponding_accent():
    base = ensure_scene_ids(_anchor_text_board())
    result = apply_film_edits(
        base, dict(_ANCHOR_TEXT_PARAMS),
        [_op({"op": "update_scene", "scene_id": "s2",
              "copy_slots": {"lines": ["好内容值得持续被看见，也值得被分享"]}})],
    )
    assert result.board.scenes[1].lines == ["好内容值得*持续被看见*，也值得被分享"]
    # The corpus anchor stays presentation-neutral.
    assert result.board.scenes[1].copy_text == "好内容值得持续被看见，也值得被分享"
    # Fully corresponding — no dropped-emphasis note.
    assert result.change_set.edited[0].notes == []


def test_copy_edit_with_authored_marks_is_not_remarked():
    base = ensure_scene_ids(_anchor_text_board())
    result = apply_film_edits(
        base, dict(_ANCHOR_TEXT_PARAMS),
        [_op({"op": "update_scene", "scene_id": "s2",
              "copy_slots": {"lines": ["*好内容* 值得持续被看见"]}})],
    )
    # The editor owns the emphasis — no auto re-mark of the old phrase…
    assert result.board.scenes[1].lines == ["*好内容* 值得持续被看见"]
    # …and the change set NAMES the emphasis that lost its mark.
    assert result.change_set.edited[0].notes == [
        "emphasis «持续被看见» is no longer marked in the new copy"
    ]


def test_vanished_accent_phrase_needs_no_note():
    """The phrase left WITH the words — the copy change itself is the report."""
    base = ensure_scene_ids(_anchor_text_board())
    result = apply_film_edits(
        base, dict(_ANCHOR_TEXT_PARAMS),
        [_op({"op": "update_scene", "scene_id": "s2",
              "copy_slots": {"lines": ["每周都有新内容"]}})],
    )
    assert result.change_set.edited[0].notes == []


def test_change_set_presentation_renders_the_dropped_emphasis_note():
    from app.tools.film.edits import change_set_presentation

    base = ensure_scene_ids(_anchor_text_board())
    result = apply_film_edits(
        base, dict(_ANCHOR_TEXT_PARAMS),
        [_op({"op": "update_scene", "scene_id": "s2",
              "copy_slots": {"lines": ["*好内容* 值得持续被看见"]}})],
    )
    text = change_set_presentation(result.change_set, result.board)
    assert "emphasis «持续被看见» is no longer marked in the new copy" in text


def test_change_set_presentation_carries_exact_copy_before_after():
    """The reviewable delta names the actual wording change, not only
    ``fields: lines``; the full board remains a separate presentation seat."""
    from app.tools.film.edits import change_set_presentation

    base = ensure_scene_ids(_anchor_text_board())
    result = apply_film_edits(
        base, dict(_ANCHOR_TEXT_PARAMS),
        [_op({"op": "update_scene", "scene_id": "s2",
              "copy_slots": {"lines": ["好内容值得被更多人看见"]}})],
    )
    text = change_set_presentation(result.change_set, result.board, base_board=base)
    assert 'lines: "好内容值得 *持续被看见*" → "好内容值得被更多人看见"' in text


def test_dark_applies_reports_and_is_words_only():
    """The background polarity op (深/浅 two stops): applies atomically,
    reports in the change set, rejects on non-words scenes."""
    result = apply_film_edits(
        _text_board(),
        dict(_TEXT_PARAMS),
        [_op({"op": "update_scene", "scene_id": "s2", "dark": False})],
    )
    assert result.board.scenes[1].dark is False
    edited = {e.scene_id: e.fields for e in result.change_set.edited}
    assert edited == {"s2": ["dark"]}
    # A polarity flip is presentation, not corpus — the pin never moves.
    assert result.params["text"] == _TEXT_COPY

    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(
            _board(), _PARAMS,
            [_op({"op": "update_scene", "scene_id": "s1", "dark": True})],
        )
    assert _codes(exc_info) == "field_not_applicable"


def test_words_copy_slots_use_a_bare_lines_array():
    """The wire shape is copy_slots={"lines":[...]}: no words wrapper and
    no stringly-typed line array. The bad shapes fail before any mutation."""
    result = apply_film_edits(
        _text_board(), dict(_TEXT_PARAMS),
        [_op({"op": "update_scene", "scene_id": "s2",
              "copy_slots": {"lines": ["见阳光的人", "眼里全是温柔和笑意"]}})],
    )
    assert result.board.scenes[1].lines == ["见阳光的人", "眼里全是温柔和笑意"]

    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(
            _text_board(), dict(_TEXT_PARAMS),
            [_op({"op": "update_scene", "scene_id": "s2",
                  "copy_slots": {"words": "见阳光的人"}})],
        )
    assert _codes(exc_info) == "unknown_copy_field"
    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(
            _text_board(), dict(_TEXT_PARAMS),
            [_op({"op": "update_scene", "scene_id": "s2",
                  "copy_slots": {"lines": "见阳光的人"}})],
        )
    assert _codes(exc_info) == "invalid_field"

    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _op({"op": "update_scene", "scene_id": "s2",
             "copy_slots": {"words": {"lines": ["见阳光的人"]}}})


def _real_text_validation(board: FilmStoryboard, params: dict) -> list:
    return validate_storyboard(
        board,
        [],
        text_lines=build_text_manifest(str(params["text"])),
    )


def _legal_text_fixture() -> tuple[FilmStoryboard, dict]:
    text = "好的内容值得再次被看见。\n一场分享。\n专业表达很有帮助。"
    board = FilmStoryboard.model_validate(
        {
            "name": None,
            "language": "zh",
            "scenes": [
                {"type": "words", "seconds": 4.0, "dark": False,
                 "lines": ["好的内容值得再次被看见。"]},
                {"type": "words", "seconds": 5.0, "dark": True,
                 "lines": ["一场分享。"]},
                {"type": "words", "seconds": 5.0, "dark": False,
                 "lines": ["专业表达很有帮助。"]},
            ],
        }
    )
    return board, dict(_TEXT_PARAMS, text=text, voiceover=True)


def test_words_complete_sentence_edit_passes_the_real_validator():
    """Semantic line breaks may carry one complete sentence; the patch must
    satisfy the SAME validator used by the chat edit path."""
    base, params = _legal_text_fixture()
    before = base.model_dump(mode="json")
    result = apply_film_edits(
        base,
        params,
        [
            _op({"op": "set_voiceover", "enabled": False}),
            _op({
                "op": "update_scene",
                "scene_id": "s2",
                "copy_slots": {
                    "lines": ["一场分享可以写成文章，", "也能引发更多讨论。"]
                },
            }),
        ],
        validate=_real_text_validation,
    )
    assert result.board.scenes[1].lines == [
        "一场分享可以写成文章，",
        "也能引发更多讨论。",
    ]
    assert result.params["voiceover"] is False
    assert base.model_dump(mode="json") == before


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        (["x" * 46, "y" * 37], "over the 36 cap"),
        (["one", "two", "three", "four", "five"], "5 lines over 4"),
    ],
)
def test_words_copy_limits_still_reject_atomically(lines, expected):
    """The declaration adds no trim or fallback: over-cap copy is rejected
    by the real validator and the caller's original board stays intact."""
    base, params = _legal_text_fixture()
    before = base.model_dump(mode="json")
    original_params = dict(params)
    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(
            base,
            params,
            [_op({
                "op": "update_scene",
                "scene_id": "s2",
                "copy_slots": {"lines": lines},
            })],
            validate=_real_text_validation,
        )
    assert _codes(exc_info) == "validation_failed"
    assert expected in exc_info.value.detail
    assert base.model_dump(mode="json") == before
    assert params == original_params


# ---------------------------------------------------------------------------
# Batch B: precise timing edit semantics
# ---------------------------------------------------------------------------


def _timed_text_board() -> FilmStoryboard:
    """A text board whose middle plane carries the user's example timing."""
    raw = _text_board().model_dump(mode="json")
    raw["scenes"][1].update(
        {
            "enter": "words",
            "enter_start": 0.3,
            "enter_interval": 0.12,
            "enter_duration": 0.25,
        }
    )
    return FilmStoryboard.model_validate(raw)


def test_timing_edit_applies_and_reports_the_current_values():
    """The patch applies the named seconds; the change set names the fields
    AND the presentation line states the quantized landing (the model never
    presents a bare field list)."""
    from app.tools.film.edits import change_set_presentation

    result = apply_film_edits(
        _text_board(),
        dict(_TEXT_PARAMS),
        [_op({"op": "update_scene", "scene_id": "s2", "enter": "words",
              "enter_start": 0.3, "enter_interval": 0.12,
              "enter_duration": 0.25})],
    )
    scene = result.board.scenes[1]
    assert scene.enter_start == 0.3
    assert scene.enter_interval == 0.12
    assert scene.enter_duration == 0.25
    edited = {e.scene_id: e.fields for e in result.change_set.edited}
    assert edited == {
        "s2": ["enter", "enter_duration", "enter_interval", "enter_start"]
    }
    text = change_set_presentation(result.change_set, result.board)
    assert "start 0.3s→f9" in text
    assert "interval 0.12s→f4" in text
    assert "duration 0.25s→f8" in text
    # A vocabulary/timing edit never touches the pinned corpus.
    assert result.params["text"] == _TEXT_COPY


def test_timing_absent_keeps_explicit_null_restores_zero_is_real():
    """Presence semantics: an absent key preserves the current value, an
    explicit null writes None (restore default), explicit 0.0 stays 0.0."""
    base = ensure_scene_ids(_timed_text_board())
    # Absent keys preserve: only the interval moves.
    result = apply_film_edits(
        base, dict(_TEXT_PARAMS),
        [_op({"op": "update_scene", "scene_id": "s2", "enter_interval": 0.2})],
    )
    scene = result.board.scenes[1]
    assert scene.enter_start == 0.3 and scene.enter_duration == 0.25
    assert scene.enter_interval == 0.2
    # Explicit null restores the default.
    result = apply_film_edits(
        base, dict(_TEXT_PARAMS),
        [_op({"op": "update_scene", "scene_id": "s2",
              "enter_start": None, "enter_duration": None})],
    )
    scene = result.board.scenes[1]
    assert scene.enter_start is None and scene.enter_duration is None
    assert scene.enter_interval == 0.12  # untouched
    # Explicit zero is a real value, never read as "clear".
    result = apply_film_edits(
        base, dict(_TEXT_PARAMS),
        [_op({"op": "update_scene", "scene_id": "s2", "enter_start": 0.0})],
    )
    assert result.board.scenes[1].enter_start == 0.0


def test_timing_edit_isolates_the_target_scene_byte_for_byte():
    """Editing one scene's timing moves ONLY that scene's content digest —
    every untouched scene stays byte-identical (复制/时序修改的局部性律)."""
    base = ensure_scene_ids(_timed_text_board())
    before = [scene_content_digest(s) for s in base.scenes]
    result = apply_film_edits(
        base, dict(_TEXT_PARAMS),
        [_op({"op": "update_scene", "scene_id": "s2", "enter_interval": 0.2})],
    )
    after = [scene_content_digest(s) for s in result.board.scenes]
    assert after[0] == before[0] and after[2] == before[2]
    assert after[1] != before[1]


def test_timing_fields_are_words_only():
    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(
            _board(), _PARAMS,
            [_op({"op": "update_scene", "scene_id": "s1", "enter_start": 0.3})],
        )
    assert _codes(exc_info) == "field_not_applicable"


def test_enter_timing_defaults_to_whole_lines():
    """An absent enter mode means lines. Its timing is real, and pure slide
    rides the same op; clearing a value still restores the default."""
    result = apply_film_edits(
        _text_board(), dict(_TEXT_PARAMS),
        [_op({"op": "update_scene", "scene_id": "s2",
              "enter_start": 0.3, "enter_style": "slide"})],
    )
    scene = result.board.scenes[1]
    assert scene.enter is None
    assert scene.enter_start == 0.3
    assert scene.enter_style == "slide"
    result = apply_film_edits(
        ensure_scene_ids(_timed_text_board()), dict(_TEXT_PARAMS),
        [_op({"op": "update_scene", "scene_id": "s2", "enter_start": None})],
    )
    assert result.board.scenes[1].enter_start is None


def test_switching_enter_units_requires_explicit_timing_migration():
    """A token cadence is never silently reinterpreted as a line cadence.
    The same op must replace or clear every old non-null timing value."""
    base = ensure_scene_ids(_timed_text_board())
    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(
            base, dict(_TEXT_PARAMS),
            [_op({"op": "update_scene", "scene_id": "s2", "enter": "lines"})],
        )
    assert _codes(exc_info) == "timing_unit_change"
    assert "enter_start" in exc_info.value.detail

    result = apply_film_edits(
        base, dict(_TEXT_PARAMS),
        [_op({"op": "update_scene", "scene_id": "s2",
              "enter": "lines", "enter_style": "slide",
              "enter_start": 0.0, "enter_interval": 0.5,
              "enter_duration": 0.4})],
    )
    scene = result.board.scenes[1]
    assert scene.enter == "lines" and scene.enter_style == "slide"
    assert scene.enter_interval == 0.5 and scene.enter_duration == 0.4
    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(
            result.board, result.params,
            [_op({"op": "update_scene", "scene_id": "s2", "enter": "words"})],
        )
    assert _codes(exc_info) == "timing_unit_change"


def test_motion_timing_without_a_move_rejects():
    with pytest.raises(FilmEditError) as exc_info:
        apply_film_edits(
            _text_board(), dict(_TEXT_PARAMS),
            [_op({"op": "update_scene", "scene_id": "s2", "motion_start": 1.0})],
        )
    assert _codes(exc_info) == "field_not_applicable"
    result = apply_film_edits(
        _text_board(), dict(_TEXT_PARAMS),
        [_op({"op": "update_scene", "scene_id": "s2", "motion": "pull",
              "motion_start": 0.5, "motion_end": 3.0})],
    )
    scene = result.board.scenes[1]
    assert scene.motion == "pull"
    assert scene.motion_start == 0.5 and scene.motion_end == 3.0


# ---------------------------------------------------------------------------
# update_element (ADR-140) — element-level edits inside composite scenes
# ---------------------------------------------------------------------------

_ELEMENT_ASSET = "11111111-1111-1111-1111-111111111111"


def _composite_board() -> FilmStoryboard:
    return FilmStoryboard.model_validate(
        {
            "scenes": [
                {"type": "words", "seconds": 3.0, "dark": False,
                 "lines": ["hello world"]},
                {
                    "type": "composite",
                    "seconds": 8.0,
                    "elements": [
                        {"kind": "video", "asset": _ELEMENT_ASSET,
                         "source_start": 10.0, "source_end": 18.0,
                         "rect": {"x": 0.5, "y": 0.0, "w": 0.5, "h": 1.0}},
                        {"kind": "text", "lines": ["旧 *标题* 文案", "second line"],
                         "at": 1.0, "until": 7.0,
                         "enter": "words", "enter_interval": 0.3},
                    ],
                },
            ]
        }
    )


def _apply(board, ops, params=None):
    return apply_film_edits(
        board, dict(params or {"voiceover": False}), [_op(o) for o in ops]
    )


def test_ensure_scene_ids_assigns_element_ids_digest_neutrally():
    bare = _composite_board()
    keyed = ensure_scene_ids(bare)
    scene = next(s for s in keyed.scenes if s.type == "composite")
    assert [e.element_id for e in scene.elements] == ["e1", "e2"]
    # The identity handle never participates in content digests.
    assert storyboard_content_digest(bare) == storyboard_content_digest(keyed)


def test_ensure_scene_ids_rejects_duplicate_element_ids():
    board = _composite_board()
    scene = next(s for s in board.scenes if s.type == "composite")
    scene.elements[1].element_id = None
    scene.elements[0].element_id = None
    keyed = ensure_scene_ids(board)
    scene = next(s for s in keyed.scenes if s.type == "composite")
    assert len({e.element_id for e in scene.elements}) == 2
    # A corrupt base (both carrying the SAME id) is not a patch target.
    corrupt = _composite_board()
    cscene = next(s for s in corrupt.scenes if s.type == "composite")
    cscene.elements[0].element_id = "e1"
    cscene.elements[1].element_id = "e1"
    with pytest.raises(FilmEditError) as exc:
        ensure_scene_ids(corrupt)
    assert _codes(exc) == "duplicate_element_id"


def test_version_identity_digest_binds_element_ids():
    """复审缺陷①: element ids are the update_element op's addressing handles,
    so the VERSION IDENTITY must bind them (the scene_ids law one level
    down). Two boards identical in content/params/scene ids but carrying
    DIFFERENT element ids are different edit bases — a reference minted
    against one must never apply against the other (the digest's element-id
    exclusion is the CONTENT digest's law, not the identity's)."""
    board_a = ensure_scene_ids(_composite_board())  # composite ids e1, e2
    board_b = FilmStoryboard.model_validate(board_a.model_dump(mode="json"))
    scene_b = next(s for s in board_b.scenes if s.type == "composite")
    scene_b.elements[1].element_id = "e9"  # same content, renamed handle
    assert storyboard_content_digest(board_a) == storyboard_content_digest(board_b)
    digest_a = film_version_identity_digest(board_a, {"voiceover": False}, version=1)
    digest_b = film_version_identity_digest(board_b, {"voiceover": False}, version=1)
    assert digest_a != digest_b
    # The apply gate fires base_mismatch — it never silently edits whichever
    # element happens to carry the addressed id in the other numbering.
    with pytest.raises(FilmEditError) as exc:
        apply_film_edits(
            board_b,
            {"voiceover": False},
            [_op({"op": "update_element", "scene_id": "s2", "element_id": "e2",
                  "at": 2.0})],
            expected_base_digest=digest_a,
        )
    assert _codes(exc) == "base_mismatch"


def test_update_element_lines_preserves_emphasis_and_reanchors_corpus():
    board = ensure_scene_ids(_composite_board())
    result = _apply(
        board,
        [{"op": "update_element", "scene_id": "s2", "element_id": "e2",
          "lines": ["新标题 旧 标题 文案"]}],
    )
    el = next(s for s in result.board.scenes if s.type == "composite").elements[1]
    assert "*标题*" in el.lines[0]  # still-corresponding emphasis re-marked
    assert el.copy_text == "新标题 旧 标题 文案"  # corpus re-anchored
    assert "elements.e2.lines" in result.change_set.edited[0].fields


def test_update_element_presence_null_restores_default():
    board = ensure_scene_ids(_composite_board())
    result = _apply(
        board,
        [{"op": "update_element", "scene_id": "s2", "element_id": "e2",
          "enter_interval": None}],
    )
    el = next(s for s in result.board.scenes if s.type == "composite").elements[1]
    assert el.enter_interval is None  # restored to the default cadence
    # Absent keys keep the value — a tone edit leaves the interval alone.
    result2 = _apply(
        board,
        [{"op": "update_element", "scene_id": "s2", "element_id": "e2",
          "tone": "dark"}],
    )
    el2 = next(s for s in result2.board.scenes if s.type == "composite").elements[1]
    assert el2.enter_interval == 0.3 and el2.tone == "dark"


def test_update_element_null_on_lines_rejects():
    board = ensure_scene_ids(_composite_board())
    with pytest.raises(FilmEditError) as exc:
        _apply(
            board,
            [{"op": "update_element", "scene_id": "s2", "element_id": "e2",
              "lines": None}],
        )
    assert _codes(exc) == "invalid_field"
    assert "no default" in exc.value.detail


def test_update_element_kind_applicability():
    board = ensure_scene_ids(_composite_board())
    # A source range never edits a text element.
    with pytest.raises(FilmEditError) as exc:
        _apply(
            board,
            [{"op": "update_element", "scene_id": "s2", "element_id": "e2",
              "source_start": 1.0}],
        )
    assert _codes(exc) == "field_not_applicable"
    # Text knobs never edit a video element.
    with pytest.raises(FilmEditError) as exc:
        _apply(
            board,
            [{"op": "update_element", "scene_id": "s2", "element_id": "e1",
              "tone": "dark"}],
        )
    assert _codes(exc) == "field_not_applicable"
    # keep_audio edits the video element.
    result = _apply(
        board,
        [{"op": "update_element", "scene_id": "s2", "element_id": "e1",
          "keep_audio": True}],
    )
    el = next(s for s in result.board.scenes if s.type == "composite").elements[0]
    assert el.keep_audio is True
    assert "elements.e1.keep_audio" in result.change_set.edited[0].fields


def test_update_element_enter_gate():
    board = ensure_scene_ids(_composite_board())
    scene = next(s for s in board.scenes if s.type == "composite")
    scene.elements[1].enter = None  # absent = whole-line rhythm
    result = _apply(
        board,
        [{"op": "update_element", "scene_id": "s2", "element_id": "e2",
          "enter_start": 0.2}],
    )
    el = next(s for s in result.board.scenes if s.type == "composite").elements[1]
    assert el.enter is None and el.enter_start == 0.2


def test_update_element_unit_switch_migrates_existing_timing_explicitly():
    board = ensure_scene_ids(_composite_board())
    with pytest.raises(FilmEditError) as exc:
        _apply(
            board,
            [{"op": "update_element", "scene_id": "s2", "element_id": "e2",
              "enter": "lines"}],
        )
    assert _codes(exc) == "timing_unit_change"
    assert "enter_interval" in exc.value.detail

    result = _apply(
        board,
        [{"op": "update_element", "scene_id": "s2", "element_id": "e2",
          "enter": "lines", "enter_style": "slide", "enter_interval": 0.5}],
    )
    el = next(s for s in result.board.scenes if s.type == "composite").elements[1]
    assert el.enter == "lines" and el.enter_style == "slide"
    assert el.enter_interval == 0.5


def test_update_element_unknown_element_and_wrong_scene():
    board = ensure_scene_ids(_composite_board())
    with pytest.raises(FilmEditError) as exc:
        _apply(
            board,
            [{"op": "update_element", "scene_id": "s2", "element_id": "e9",
              "tone": "dark"}],
        )
    assert _codes(exc) == "unknown_element"
    with pytest.raises(FilmEditError) as exc:
        _apply(
            board,
            [{"op": "update_element", "scene_id": "s1", "element_id": "e1",
              "tone": "dark"}],
        )
    assert _codes(exc) == "field_not_applicable"


def test_update_element_noop_rejects_as_unchanged():
    board = ensure_scene_ids(_composite_board())
    with pytest.raises(FilmEditError) as exc:
        _apply(
            board,
            [{"op": "update_element", "scene_id": "s2", "element_id": "e2",
              "tone": "light"}],  # already the default
        )
    assert _codes(exc) == "unchanged"


def test_update_element_change_set_now_line():
    """The confirmation beat shows the element's NOW window + timing clause
    (the words plane's cumulative-fact law, one level down)."""
    from app.tools.film.edits import change_set_presentation

    board = ensure_scene_ids(_composite_board())
    result = _apply(
        board,
        [{"op": "update_element", "scene_id": "s2", "element_id": "e2",
          "at": 2.0, "enter_interval": 0.5}],
    )
    presentation = change_set_presentation(result.change_set, result.board)
    assert "elements.e2.at" in presentation
    assert "elements.e2.enter_interval" in presentation
    assert "[e2] now: on screen 2s–7s" in presentation
    assert "interval 0.5s" in presentation


def test_update_element_untouched_elements_stay_byte_identical():
    """未触碰元素保持: an edit naming e2 leaves e1's dump byte-identical."""
    board = ensure_scene_ids(_composite_board())
    result = _apply(
        board,
        [{"op": "update_element", "scene_id": "s2", "element_id": "e2",
          "tone": "dark"}],
    )
    before_el = next(s for s in board.scenes if s.type == "composite").elements[0]
    after_el = next(s for s in result.board.scenes if s.type == "composite").elements[0]
    assert before_el.model_dump(mode="json") == after_el.model_dump(mode="json")
