"""Pure tests for the track-atomic spec write (ADR-096 §5, batch E).

No DB / no LLM / no HTTP. The in-place morph's render_spec write lands as
one jsonb_set per DECLARED field on the row-locked output — the op
registry's ``writes`` (boot-reconciled against the track partition) is the
write-permission basis, and the merged whole is revalidated before
anything lands. These tests pin the declarations and exercise the pure
merge kernel:

- concurrent DIFFERENT-track writers never lose each other's update (the
  black-card incident's spec side — translate's stale-based new_spec must
  not clobber reframe's committed crop_track);
- same-track writers serialize on the row lock (the lock is the SQL seat's,
  asserted here only as the merge's honest overwrite semantics);
- cross-track joint invariants revalidate — a merged spec that violates
  the schema refuses outright.

The SQL seat itself (the jsonb_set chain, the FOR UPDATE ordering) belongs
to the e2e reruns, never to this suite (repo convention).
"""

from uuid import uuid4

import pytest

from app.models.schemas import ClipSpec
from app.operations.registry import OP_REGISTRY
from app.operations.service import OpRejected, merge_declared_fields
from app.pipeline.tracks import TRACKS

_CROP = [{"t": 0.0, "x": 0.5, "y": 0.5, "scale": 1.2}]
_TITLE_BLANK = {"enabled": False, "position": None, "size": None, "text": ""}


def _base(**over) -> dict:
    """A minimal valid spec dump with caller overrides — the LOCKED row's
    live value in the merge scenarios."""
    spec = ClipSpec.model_validate(
        {"source": {"kind": "video", "asset_id": str(uuid4())}}
    ).model_dump(mode="json")
    spec.update(over)
    return spec


def _translate_new(**over) -> dict:
    """A translate_captions new_spec computed off a STALE pre-reframe read
    (crop_track None) — the incident shape."""
    new = _base()
    new.update(
        {
            "caption_track": [{"start": 0.0, "end": 1.0, "text": "bonjour", "lang": "fr"}],
            "translation_track": [],
            "title": dict(_TITLE_BLANK),
            "target_language": "fr",
        }
    )
    new.update(over)
    return new


# ---- the write-permission declaration (track registry anchored) ---------------


class TestWriteDeclarations:
    def test_every_precomputed_op_declares_track_scoped_writes(self) -> None:
        """A precomputed op without a field list would have nothing to
        merge; a ``*`` would re-open the whole-blob door."""
        precomputed = [n for n, d in OP_REGISTRY.items() if d.precomputed]
        assert precomputed, "registry drift: no precomputed ops at all"
        for name in precomputed:
            writes = OP_REGISTRY[name].writes
            assert writes, name
            assert "*" not in writes, name

    def test_writes_stay_inside_the_track_partition(self) -> None:
        registered = {f for t in TRACKS.values() for f in t.fields}
        for name, opdef in OP_REGISTRY.items():
            for f in opdef.writes:
                if f == "*":
                    continue
                assert f in registered, f"{name}:{f}"

    def test_precomputed_writes_pinned(self) -> None:
        """The four in-place-morph ops' write sets ARE the merge's
        permission basis — a drift here silently widens or narrows what a
        morph can land. set_dub names every field synthesize_dub lands
        (the dub track plus the re-timed captions, the translated title,
        the language stamp)."""
        assert OP_REGISTRY["translate_captions"].writes == (
            "caption_track",
            "translation_track",
            "title",
            "target_language",
        )
        assert OP_REGISTRY["set_dub"].writes == (
            "dub",
            "caption_track",
            "title",
            "target_language",
        )
        assert OP_REGISTRY["remove_filler"].writes == ("segments", "caption_track")
        assert OP_REGISTRY["reframe_clip"].writes == ("crop_track",)


# ---- the merge kernel ----------------------------------------------------------


class TestMergeDeclaredFields:
    def test_disjoint_track_survives_the_merge(self) -> None:
        """The incident shape: reframe's crop_track committed first;
        translate's stale-based new_spec must land its own fields only —
        the crop survives untouched."""
        base = _base(crop_track=[dict(k) for k in _CROP])
        landed = merge_declared_fields(
            base,
            _translate_new(),
            OP_REGISTRY["translate_captions"].writes,
            op="translate_captions",
        )
        assert landed["crop_track"] == _CROP
        assert landed["target_language"] == "fr"
        assert landed["caption_track"][0]["text"] == "bonjour"
        assert landed["translation_track"] == []

    def test_field_nulling_is_a_write(self) -> None:
        """reframe static_center clears the dynamic track — explicit None
        in new_spec lands as null, never mistaken for a missing field."""
        base = _base(crop_track=[dict(k) for k in _CROP])
        landed = merge_declared_fields(base, _base(), ("crop_track",), op="reframe_clip")
        assert landed["crop_track"] is None

    def test_missing_declared_field_rejects(self) -> None:
        """A declared field absent from new_spec is a caller bug — the
        merge must not guess (skip would journal a lie, None-forge would
        erase a live track)."""
        new = _translate_new()
        del new["caption_track"]
        with pytest.raises(OpRejected, match="caption_track"):
            merge_declared_fields(
                _base(),
                new,
                OP_REGISTRY["translate_captions"].writes,
                op="translate_captions",
            )

    def test_cross_track_revalidation_refuses(self) -> None:
        """A merged spec violating the schema refuses outright — no partial
        write ever lands a joint-invariant breach."""
        new = _translate_new(caption_track="not-a-list")
        with pytest.raises(OpRejected, match="validation"):
            merge_declared_fields(
                _base(),
                new,
                OP_REGISTRY["translate_captions"].writes,
                op="translate_captions",
            )

    def test_untouched_fields_keep_the_live_base_exactly(self) -> None:
        """The journal's spec_after must equal the DB post-write value
        field for field (the drift check hashes them): undeclared fields
        pass through byte-identical — even shapes validation would coerce
        had they been rewritten."""
        base = _base()
        base["music"] = {
            "enabled": True,
            "gain_db": -12,  # int — validation coerces to -12.0 on rewrite
            "music_id": None,
            "url": "https://example.test/legacy.mp3",
        }
        landed = merge_declared_fields(
            base,
            _translate_new(),
            OP_REGISTRY["translate_captions"].writes,
            op="translate_captions",
        )
        assert landed["music"] == base["music"]
        assert landed["music"]["gain_db"] == -12  # NOT coerced — untouched

    def test_declared_fields_land_in_validated_form(self) -> None:
        """The written per-field value IS the validated dump — schema
        defaults and coercions apply to what lands."""
        new = _translate_new()
        new["caption_track"] = [
            {"start": 0.0, "end": 1.0, "text": "bonjour", "lang": "fr"}
        ]
        landed = merge_declared_fields(
            _base(),
            new,
            OP_REGISTRY["translate_captions"].writes,
            op="translate_captions",
        )
        assert landed["caption_track"][0]["emphasis"] is False  # default filled

    def test_dub_lands_all_four_fields(self) -> None:
        """synthesize_dub re-times the caption track onto the dub and
        translates the title along — all four declared fields land in one
        merge (the old ("dub",) declaration would have dropped three)."""
        new = _base()
        new.update(
            {
                "dub": {"url": "https://example.test/dub.mp3", "enabled": True, "gain_db": 0.0},
                "caption_track": [{"start": 0.0, "end": 2.0, "text": "hello", "lang": "en"}],
                "title": {"enabled": True, "position": None, "size": None, "text": "Hello"},
                "target_language": "en",
            }
        )
        landed = merge_declared_fields(
            _base(), new, OP_REGISTRY["set_dub"].writes, op="set_dub"
        )
        assert landed["dub"]["enabled"] is True
        assert landed["caption_track"][0]["end"] == 2.0
        assert landed["title"]["text"] == "Hello"
        assert landed["target_language"] == "en"

    def test_filler_lands_segments_and_captions_only(self) -> None:
        """remove_range's cut spans + re-timed captions land; every other
        track (music, crop, dub) keeps the live base."""
        base = _base(crop_track=[dict(k) for k in _CROP])
        new = _base()
        new["segments"] = [
            {"id": "seg-1", "start": 0.0, "end": 5.0, "hidden": False}
        ]
        new["caption_track"] = [{"start": 0.0, "end": 4.0, "text": "clean", "lang": "en"}]
        landed = merge_declared_fields(
            base, new, OP_REGISTRY["remove_filler"].writes, op="remove_filler"
        )
        assert landed["segments"][0]["end"] == 5.0
        assert landed["caption_track"][0]["text"] == "clean"
        assert landed["crop_track"] == _CROP
