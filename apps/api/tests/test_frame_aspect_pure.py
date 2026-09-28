"""Pure tests for the frame-aspect predictive mirror (2026-09-28 root fix —
the 16:9-frame / 9:16-clip walkthrough: a chat-born select_clips chain whose
plan named no aspect used to reserve the SOURCE's display class while the
runtime silently rendered the shorts default).

Gated here (no DB / no LLM / no HTTP — SimpleNamespace steps):

- ``_frame_class_of``: the explicit aspect always wins; an unstamped clip
  family yields the "original" sentinel for the caller to resolve; non-clip
  families take the text class.
- ``_predict_family_frame_aspect``: the caller's mirror of the RUNTIME's
  aspect resolution (tools/clips/node.py + cut.py: spec → run ctx →
  exemplar skeleton → graph_store.SHORTS_DEFAULT_ASPECT). Cut families never
  follow the source; whole-source families (materialize_source, bare or
  folded) keep 比例跟源; transform families inherit their in-run upstream
  producer's resolved aspect; modifiers on the project's EXISTING clips read
  the cross-run class; the genuinely unknowable keeps the "original"
  sentinel. Input cycles terminate (the walk is bounded).
"""

from types import SimpleNamespace
from uuid import uuid4

from app.pipeline.graph_fill import _frame_class_of, _predict_family_frame_aspect


def _step(kind: str, spec: dict | None = None, inputs: list | None = None):
    return SimpleNamespace(
        id=uuid4(), kind=kind, spec=spec or {}, inputs=inputs or []
    )


def _by_id(*steps) -> dict:
    return {str(s.id): s for s in steps}


# ---- _frame_class_of: the explicit aspect wins, else the sentinel --------


class TestFrameClassOf:
    def test_explicit_aspect_wins(self):
        steps = [_step("select_clips", {"aspect": "1:1"}), _step("verify")]
        assert _frame_class_of(steps) == ("clip", "1:1")

    def test_unstamped_clip_family_yields_original(self):
        steps = [_step("select_clips", {"count": 1}), _step("verify")]
        assert _frame_class_of(steps) == ("clip", "original")

    def test_writer_family_is_text(self):
        assert _frame_class_of([_step("write_post")]) == ("text", None)


# ---- _predict_family_frame_aspect -----------------------------------------


class TestPredictFamilyFrameAspect:
    def test_cut_family_never_follows_source(self):
        """The reported bug: an unstamped select_clips chain predicts the
        shorts default even when the source is a landscape lecture."""
        fam = [_step("select_clips"), _step("verify")]
        assert (
            _predict_family_frame_aspect(
                fam,
                _by_id(*fam),
                cut_default="9:16",
                source_aspect="16:9",
                existing_clips_aspect=None,
            )
            == "9:16"
        )

    def test_cut_family_honors_the_exemplar_class(self):
        fam = [_step("select_clips")]
        assert (
            _predict_family_frame_aspect(
                fam,
                _by_id(*fam),
                cut_default="1:1",
                source_aspect="16:9",
                existing_clips_aspect=None,
            )
            == "1:1"
        )

    def test_transform_inherits_upstream_cut_explicit(self):
        producer = _step("select_clips", {"aspect": "1:1"})
        fam = [_step("translate_clip", inputs=[str(producer.id)])]
        assert (
            _predict_family_frame_aspect(
                fam,
                _by_id(*fam, producer),
                cut_default="9:16",
                source_aspect="16:9",
                existing_clips_aspect=None,
            )
            == "1:1"
        )

    def test_transform_inherits_upstream_cut_default(self):
        producer = _step("select_clips")
        fam = [_step("dub_clip", inputs=[str(producer.id)])]
        assert (
            _predict_family_frame_aspect(
                fam,
                _by_id(*fam, producer),
                cut_default="9:16",
                source_aspect="16:9",
                existing_clips_aspect=None,
            )
            == "9:16"
        )

    def test_transform_walks_transitively(self):
        producer = _step("select_clips")
        middle = _step("remove_filler", inputs=[str(producer.id)])
        fam = [_step("translate_clip", inputs=[str(middle.id)])]
        assert (
            _predict_family_frame_aspect(
                fam,
                _by_id(*fam, producer, middle),
                cut_default="9:16",
                source_aspect="16:9",
                existing_clips_aspect=None,
            )
            == "9:16"
        )

    def test_folded_materialize_keeps_source_law(self):
        """multilingual-subs shape: translate with the whole-source
        materialize folded INTO its family — 比例跟源, unchanged."""
        fam = [_step("translate_clip"), _step("materialize_source")]
        assert (
            _predict_family_frame_aspect(
                fam,
                _by_id(*fam),
                cut_default="9:16",
                source_aspect="16:9",
                existing_clips_aspect="9:16",
            )
            == "16:9"
        )

    def test_walked_bare_materialize_keeps_source_law(self):
        materialize = _step("materialize_source")
        fam = [_step("translate_clip", inputs=[str(materialize.id)])]
        assert (
            _predict_family_frame_aspect(
                fam,
                _by_id(*fam, materialize),
                cut_default="9:16",
                source_aspect="16:9",
                existing_clips_aspect=None,
            )
            == "16:9"
        )

    def test_cross_run_modifier_reads_existing_clips(self):
        """Mode②: empty inputs = acting on the project's existing clips."""
        fam = [_step("translate_clip")]
        assert (
            _predict_family_frame_aspect(
                fam,
                _by_id(*fam),
                cut_default="9:16",
                source_aspect="16:9",
                existing_clips_aspect="9:16",
            )
            == "9:16"
        )

    def test_unknown_everything_keeps_the_sentinel(self):
        fam = [_step("translate_clip")]
        assert (
            _predict_family_frame_aspect(
                fam,
                _by_id(*fam),
                cut_default="9:16",
                source_aspect=None,
                existing_clips_aspect=None,
            )
            == "original"
        )

    def test_cyclic_inputs_terminate(self):
        a = _step("translate_clip")
        b = _step("dub_clip", inputs=[str(a.id)])
        a.inputs = [str(b.id)]
        fam = [_step("add_music", inputs=[str(a.id)])]
        assert (
            _predict_family_frame_aspect(
                fam,
                _by_id(*fam, a, b),
                cut_default="9:16",
                source_aspect="16:9",
                existing_clips_aspect=None,
            )
            == "16:9"
        )
