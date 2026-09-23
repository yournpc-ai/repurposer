"""writer source_span — the plan-sourced writers' material narrowing (iter-2 ②, N-57).

Pure coverage (suite discipline: no DB, no LLM, no HTTP):

- **Params/schema**: SourceSpan ordering validation; CopyWriterParams and
  the quotes/carousel subclasses carry the optional field; the slot
  projection ferries it (orchestrator's slot filter) into spec.slot and
  ``node_slot`` reads it back into IntentSlot.
- **resolve_source_span_texts** (the injection helper): None without a
  span (the zero-hypothesis half — the caller's fallback is byte-identical
  to the pre-span path); the verbatim in-range transcript with an asset
  pin / the sole timeline asset without one; None (honest fallback) when
  the asset left, carries no timeline, or the range lands in a pause.
- **Zero-hypothesis**: a write task compiled WITHOUT source_span produces
  the byte-same slot projection as before the field existed.
"""

from types import SimpleNamespace

import pytest

from app.models.schemas import IntentSlot, SourceSpan, TaskItem
from app.pipeline.derivative_dispatch import (
    CopyWriterParams,
    resolve_source_span_texts,
)
from app.pipeline.orchestrator import TaskSpec, compile_graph
from app.pipeline.step_display import node_slot
from app.tools.carousel.params import WriteCarouselParams
from app.tools.clips.transcript import words_in_range
from app.tools.quotes.params import WriteQuotesParams


def _words() -> list[dict]:
    words = []
    t = 0.0
    for sentence in (
        "Welcome to the talk",
        "pricing is simple",
        "the roadmap comes next",
    ):
        for w in sentence.split():
            words.append({"word": w, "start": round(t, 2), "end": round(t + 0.4, 2)})
            t += 1.0
    return words


def _asset(asset_id: str, with_words: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        id=asset_id, meta={"words": _words()} if with_words else {}
    )


# ---- params / schema -----------------------------------------------------------


class TestSourceSpanSchema:
    def test_span_must_be_ordered(self):
        with pytest.raises(ValueError, match="must be < end"):
            SourceSpan(start=5.0, end=5.0)
        with pytest.raises(ValueError):
            SourceSpan(start=6.0, end=5.0)

    def test_writers_carry_the_optional_field(self):
        params = CopyWriterParams(
            language="en", source_span={"start": 4.0, "end": 8.9}
        )
        assert params.source_span is not None
        assert params.source_span.start == 4.0
        # The subclasses inherit the shared document's field.
        assert "source_span" in WriteQuotesParams.model_fields
        assert "source_span" in WriteCarouselParams.model_fields

    def test_null_default(self):
        assert CopyWriterParams(language="en").source_span is None


# ---- the narrowing helper ------------------------------------------------------


class TestResolve:
    def test_no_span_is_none(self):
        assert resolve_source_span_texts(None, [_asset("a")]) is None

    def test_span_resolves_the_verbatim_range(self):
        span = SourceSpan(start=4.0, end=6.4, asset_id="a")
        texts = resolve_source_span_texts(span, [_asset("a")])
        assert texts == [words_in_range(_words(), 4.0, 6.4)]
        assert texts[0] == "pricing is simple"

    def test_asset_pin_selects_the_pinned_asset(self):
        span = SourceSpan(start=0.0, end=1.4, asset_id="b")
        texts = resolve_source_span_texts(span, [_asset("a"), _asset("b")])
        assert texts == ["Welcome to"]

    def test_unpinned_picks_the_timeline_asset(self):
        span = SourceSpan(start=8.0, end=10.4)
        texts = resolve_source_span_texts(
            span, [_asset("no-words", with_words=False), _asset("b")]
        )
        assert texts == ["roadmap comes next"]

    def test_unresolvable_span_is_an_honest_none(self):
        # Asset gone between dock and run.
        assert (
            resolve_source_span_texts(
                SourceSpan(start=0.0, end=1.0, asset_id="gone"), [_asset("a")]
            )
            is None
        )
        # No timeline anywhere.
        assert (
            resolve_source_span_texts(
                SourceSpan(start=0.0, end=1.0), [_asset("bare", with_words=False)]
            )
            is None
        )
        # The range lands in a pause (no words overlap).
        assert (
            resolve_source_span_texts(
                SourceSpan(start=100.0, end=101.0), [_asset("a")]
            )
            is None
        )


# ---- the slot projection ferry -------------------------------------------------


class TestSlotProjection:
    def test_span_rides_the_compiled_slot(self):
        task = TaskItem(
            tool="write_post",
            params={
                "language": "en",
                "focus": "pricing",
                "source_span": {"start": 4.0, "end": 6.4, "asset_id": "a"},
            },
        )
        compiled = compile_graph(TaskSpec(tasks=[task], ui_language="en"))
        writer = next(n for n in compiled if n.kind == "write_post")
        span = (writer.spec or {}).get("slot", {}).get("source_span")
        assert span == {"start": 4.0, "end": 6.4, "asset_id": "a"}
        # node_slot reads it back typed (the runner's seat).
        slot = node_slot(
            SimpleNamespace(spec=writer.spec), {}, "post"
        )
        assert slot is not None and slot.source_span is not None
        assert slot.source_span.asset_id == "a"

    def test_zero_hypothesis_no_span_slot_byte_identical(self):
        """A span-less task compiles to exactly the pre-field slot shape."""
        task = TaskItem(
            tool="write_post", params={"language": "en", "focus": "pricing"}
        )
        compiled = compile_graph(TaskSpec(tasks=[task], ui_language="en"))
        writer = next(n for n in compiled if n.kind == "write_post")
        assert (writer.spec or {}).get("slot") == {
            "type": "post",
            "language": "en",
            "focus": "pricing",
        }
        slot = node_slot(SimpleNamespace(spec=writer.spec), {}, "post")
        assert slot is not None and slot.source_span is None

    def test_intent_slot_accepts_and_defaults(self):
        slot = IntentSlot.model_validate({"type": "post"})
        assert slot.source_span is None
        slot = IntentSlot.model_validate(
            {"type": "post", "source_span": {"start": 1.0, "end": 2.0}}
        )
        assert slot.source_span is not None and slot.source_span.end == 2.0
