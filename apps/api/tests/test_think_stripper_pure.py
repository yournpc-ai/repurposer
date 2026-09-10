"""Tests for _ThinkStripper (providers/llm/minimax) — provider-dialect
normalization at the Model seam.

Pure-function coverage only (suite discipline: no DB, no LLM, no HTTP). The
stripper's contract: swallow ONE leading ``<think>…</think>`` block from the
delta channel (tag-split safe across chunk boundaries); once real payload
starts the filter is a pure pass-through — a mid-stream ``<think>`` is
literal text (same start-only rule as ``_clean_json``).
"""

from app.providers.llm.minimax import _ThinkStripper


def strip(chunks: list[str]) -> str:
    s = _ThinkStripper()
    return "".join(s.feed(chunk) for chunk in chunks)


def split_every_way(text: str) -> str:
    """Feed the fixture split at every single position — tag splits across
    chunk boundaries are the whole point of the state machine."""
    expected = None
    for i in range(len(text) + 1):
        result = strip([text[:i], text[i:]])
        if expected is None:
            expected = result
        assert result == expected, f"split at {i}: {result!r} != {expected!r}"
    return expected or ""


class TestThinkStrip:
    def test_no_think_passthrough(self):
        assert strip(['{"answer": "hi"}']) == '{"answer": "hi"}'

    def test_leading_whitespace_passthrough(self):
        assert strip(['  {"a": 1}']) == '  {"a": 1}'

    def test_think_block_swallowed(self):
        text = (
            '<think>The user wants JSON with an "answer" key.</think>'
            '{"answer": "Real."}'
        )
        assert strip([text]) == '{"answer": "Real."}'

    def test_fake_json_inside_think_never_leaks(self):
        """Example JSON inside the reasoning must never reach consumers."""
        text = (
            '<think>I should reply like {"answer": "FAKE"}</think>'
            '{"answer": "Real."}'
        )
        assert strip([text]) == '{"answer": "Real."}'

    def test_every_split_point(self):
        text = '<think>reasoning {"answer": "FAKE"}</think>{"answer": "Real."}'
        assert split_every_way(text) == '{"answer": "Real."}'

    def test_leading_whitespace_before_think(self):
        text = '  \n<think>reasoning</think>\n{"a": 1}'
        assert strip([text]) == '\n{"a": 1}'

    def test_think_only_stream(self):
        assert strip(['<think>only reasoning</think>']) == ""

    def test_not_quite_a_tag_is_payload(self):
        """``<thinkx`` is not the dialect tag — flush verbatim."""
        assert strip(['<thinkx="1">literal</thinkx>']) == '<thinkx="1">literal</thinkx>'

    def test_midstream_think_is_literal_text(self):
        """Once payload started, a ``<think>`` is content, never a dialect."""
        text = '{"text": "a <think> tag in prose"}'
        assert split_every_way(text) == text

    def test_open_tag_split_across_chunks(self):
        assert strip(["<th", "ink>reasoning</th", "ink>{", '"a": 1}']) == '{"a": 1}'
