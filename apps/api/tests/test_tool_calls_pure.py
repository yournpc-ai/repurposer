"""Tests for the Tier-1 tool_calls wire machinery (providers/llm/minimax) —
the fragment accumulator and the one arguments parse law.

Pure-function coverage only (suite discipline: no DB, no LLM, no HTTP). The
contract under test (ADR-077 判词④): prose rides content, calls ride
accumulated tool_call arguments; the TRUNCATION SIGNATURE (finish_reason
says tool_calls but arguments hit EOF — spike 2026-09-11/12, ~11%) is the
schema class, raising ``LLMSchemaError`` so the harness's one feedback
repair round answers it — never a blind re-roll, never a half-call.
"""

import pytest

from app.providers.llm.base import LLMSchemaError, ToolCall
from app.providers.llm.minimax import (
    _ToolCallAccumulator,
    _parse_tool_arguments,
    _tool_call_from_object,
)


def _fragment(idx: int, name: str | None = None, args: str | None = None,
              call_id: str | None = None) -> dict:
    """One ``delta.tool_calls[]`` entry as the provider streams it."""
    fn: dict = {}
    if name is not None:
        fn["name"] = name
    if args is not None:
        fn["arguments"] = args
    out: dict = {"index": idx, "function": fn}
    if call_id is not None:
        out["id"] = call_id
    return out


def test_arguments_parse_law() -> None:
    """Empty text is a legal zero-arg call; object text parses; everything
    else is the schema class."""
    assert _parse_tool_arguments("t", "", "tool_calls") == {}
    assert _parse_tool_arguments("t", '{"a": 1}', "tool_calls") == {"a": 1}
    with pytest.raises(LLMSchemaError):
        _parse_tool_arguments("t", '{"a":', "tool_calls")  # truncated
    with pytest.raises(LLMSchemaError):
        _parse_tool_arguments("t", "[1, 2]", "tool_calls")  # not an object


def test_single_call_assembles_across_fragments() -> None:
    """Name + id arrive once; JSON text shards concatenate in order."""
    acc = _ToolCallAccumulator()
    named = acc.feed([_fragment(0, name="submit_answer", call_id="c1")])
    assert named == ["submit_answer"]
    assert acc.feed([_fragment(0, args='{"act')]) == []  # name already known
    assert acc.feed([_fragment(0, args='ion": "ask"}')]) == []
    assert acc.finish("tool_calls") == [
        ToolCall(id="c1", name="submit_answer", arguments={"action": "ask"})
    ]


def test_two_calls_keep_their_own_shards_and_wire_order() -> None:
    """Calls keyed by index: interleaved fragments never cross-contaminate,
    and finish() returns them in wire order (index ascending)."""
    acc = _ToolCallAccumulator()
    acc.feed([_fragment(1, name="second", args='{"b"')])
    acc.feed([_fragment(0, name="first", args='{"a"')])
    acc.feed([_fragment(1, args=": 2}")])
    acc.feed([_fragment(0, args=": 1}")])
    calls = acc.finish("tool_calls")
    assert [c.name for c in calls] == ["first", "second"]
    assert calls[0].arguments == {"a": 1}
    assert calls[1].arguments == {"b": 2}


def test_zero_arg_call_is_legal() -> None:
    acc = _ToolCallAccumulator()
    acc.feed([_fragment(0, name="list_styles")])
    assert acc.finish("tool_calls") == [
        ToolCall(id=None, name="list_styles", arguments={})
    ]


def test_truncation_signature_raises_schema_class() -> None:
    """finish_reason=tool_calls but the arguments hit EOF mid-call — the
    spike's ~11% case — raises LLMSchemaError (the repair round's class)."""
    acc = _ToolCallAccumulator()
    acc.feed([_fragment(0, name="submit_answer", args='{"action": "start", "tasks": [{"k')])
    with pytest.raises(LLMSchemaError) as excinfo:
        acc.finish("tool_calls")
    assert excinfo.value.user_key == "ai_unreadable"


def test_length_finish_with_a_partial_call_is_truncation_too() -> None:
    """finish_reason=length mid-call = budget truncation — same class."""
    acc = _ToolCallAccumulator()
    acc.feed([_fragment(0, name="submit_answer", args='{"action"')])
    with pytest.raises(LLMSchemaError):
        acc.finish("length")


def test_nameless_fragment_is_wire_malformation() -> None:
    """Arguments without any function name can never become a call."""
    acc = _ToolCallAccumulator()
    acc.feed([_fragment(0, args='{"a": 1}')])
    with pytest.raises(LLMSchemaError):
        acc.finish("tool_calls")


def test_no_tool_calls_is_a_legal_shape() -> None:
    """tool_choice=auto and the model chose prose only: finish() returns an
    empty list — what that means is the caller's contract, not the wire's."""
    acc = _ToolCallAccumulator()
    assert acc.finish("stop") == []


def test_complete_object_form_shares_the_one_parse_law() -> None:
    """The non-streaming tool_calls[] object parses through the same law:
    good object → ToolCall; truncated arguments → schema class; a missing
    function name → wire-malformation (schema class), never a silent
    empty-name call."""
    good = _tool_call_from_object(
        {"id": "c1", "type": "function",
         "function": {"name": "submit_answer", "arguments": '{"action": "ask"}'}},
        "tool_calls",
    )
    assert good == ToolCall(id="c1", name="submit_answer", arguments={"action": "ask"})
    with pytest.raises(LLMSchemaError):
        _tool_call_from_object(
            {"function": {"name": "submit_answer", "arguments": '{"action": "st'}},
            "tool_calls",
        )
    with pytest.raises(LLMSchemaError):
        _tool_call_from_object(
            {"id": "c2", "function": {"arguments": "{}"}}, "tool_calls"
        )
    zero_arg = _tool_call_from_object(
        {"function": {"name": "list_styles", "arguments": ""}}, "tool_calls"
    )
    assert zero_arg.arguments == {}
