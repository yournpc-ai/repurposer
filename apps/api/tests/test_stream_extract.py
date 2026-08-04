"""Tests for ProseDeltaExtractor (chat SSE 流式 preview channel).

Pure-function coverage only (suite discipline: no DB, no LLM, no HTTP). The
extractor's contract: decode the prose field's content incrementally from a
streaming JSON verdict; go silently dead on any surprise — never wrong text.
"""

from app.chat.stream_extract import ProseDeltaExtractor


def extract(chunks: list[str], keys=("answer",)) -> str:
    ext = ProseDeltaExtractor(keys)
    return "".join(ext.feed(chunk) for chunk in chunks)


def split_every_way(text: str, keys=("answer",)) -> None:
    """Feed the fixture split at every single position — chunk-boundary
    safety is the whole point of the state machine."""
    expected = None
    for i in range(len(text) + 1):
        result = extract([text[:i], text[i:]], keys)
        if expected is None:
            expected = result
        assert result == expected, f"split at {i}: {result!r} != {expected!r}"
    return expected


class TestBasicExtraction:
    def test_plan_answer(self):
        text = '{"action": "answer", "answer": "The sea is vast.", "language": "en"}'
        assert extract([text]) == "The sea is vast."

    def test_every_split_point(self):
        text = '{"action": "answer", "answer": "Hello, world!", "language": "en"}'
        assert split_every_way(text) == "Hello, world!"

    def test_one_char_chunks(self):
        text = '{"answer": "abc"}'
        assert extract(list(text)) == "abc"

    def test_wrapped_proposal_shape(self):
        text = '{"proposal": {"type": "answer", "text": "Deep answer."}}'
        assert extract([text], keys=("text", "summary")) == "Deep answer."

    def test_bare_proposal_shape(self):
        text = '{"type": "answer", "text": "Bare answer."}'
        assert extract([text], keys=("text", "summary")) == "Bare answer."

    def test_summary_key(self):
        text = '{"type": "task_list", "summary": "Making 3 clips.", "tasks": []}'
        assert extract([text], keys=("text", "summary")) == "Making 3 clips."


class TestEscapeDecoding:
    def test_simple_escapes(self):
        text = '{"answer": "line1\\nline2 \\"quoted\\" \\\\ slash"}'
        assert extract([text]) == 'line1\nline2 "quoted" \\ slash'

    def test_unicode_escape(self):
        text = '{"answer": "\\u4f60\\u597d"}'
        assert extract([text]) == "你好"

    def test_unicode_escape_split_across_chunks(self):
        text = '{"answer": "\\u4f60\\u597d"}'
        assert split_every_way(text) == "你好"

    def test_surrogate_pair(self):
        text = '{"answer": "\\ud83d\\ude00"}'  # 😀
        assert extract([text]) == "\U0001f600"

    def test_surrogate_pair_split(self):
        text = '{"answer": "\\ud83d\\ude00"}'
        assert split_every_way(text) == "\U0001f600"

    def test_escape_split_at_backslash(self):
        text = '{"answer": "a\\nb"}'
        assert split_every_way(text) == "a\nb"


class TestDeadEnds:
    """Non-prose or hostile input: zero deltas, never wrong text."""

    def test_null_answer(self):
        assert extract(['{"action": "generate", "answer": null}']) == ""

    def test_object_value(self):
        assert extract(['{"answer": {"nested": true}}']) == ""

    def test_think_preamble(self):
        text = (
            '<think>The user wants JSON with an "answer" key.</think>'
            '{"answer": "Real."}'
        )
        assert extract([text]) == "Real."

    def test_think_preamble_with_example_json(self):
        """Example JSON inside the think block must never trigger capture."""
        text = (
            '<think>I should reply like {"answer": "FAKE"}</think>'
            '{"answer": "Real."}'
        )
        assert extract([text]) == "Real."

    def test_think_preamble_split(self):
        text = '<think>reasoning {"answer": "FAKE"}</think>{"answer": "Real."}'
        assert split_every_way(text) == "Real."

    def test_op_param_text_never_captured(self):
        """edit_ops params carry a text key at depth >= 3 — must not leak."""
        text = (
            '{"type": "edit_ops", "ops": [{"op": "set_title", '
            '"params": {"text": "OP PARAM"}}, {"op": "set_trim", '
            '"params": {"start": 1.0}}], "summary": "Done."}'
        )
        assert extract([text], keys=("text", "summary")) == "Done."

    def test_markdown_fence(self):
        text = '```json\n{"answer": "Fenced."}\n```'
        assert extract([text]) == "Fenced."

    def test_garbage_goes_dead_silently(self):
        assert extract(["not json at all"]) == ""

    def test_no_target_key(self):
        assert extract(['{"action": "generate", "outputs": []}']) == ""


class TestDoneLatch:
    def test_nothing_after_closing_quote(self):
        ext = ProseDeltaExtractor(("answer",))
        first = ext.feed('{"answer": "Hi')
        second = ext.feed(' there"}')
        third = ext.feed(', "answer": "again"}')
        assert first + second == "Hi there"
        assert third == ""
        assert ext.dead
