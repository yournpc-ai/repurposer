"""Pure tests for the tool-name echo sanitizer (2026-09-30 用户拍板 — 彻底删掉).

The model occasionally echoes the tool it is calling as a BARE bracketed
line of prose ('[start_run]'): the name saturates its prompt (it must — it
is the tool's name), the bracket shape is its pretraining's function-call
markup, and the real call already rides the native tool channel. The echo
is pure machine vocabulary the user must never see; ``strip_tool_echoes``
removes exactly those lines at the message-persistence chokepoint.
"""

import pytest

from app.chat.turn_tools import (
    _TOOL_ECHO_NAMES,
    make_tool_echo_delta_filter,
    strip_tool_echoes,
)


class TestStripToolEchoes:
    def test_bare_echo_line_after_ack_is_stripped(self) -> None:
        # The image-#68 case verbatim: the work-start sentence lands, then
        # the echo rides as its own trailing paragraph.
        content = "好的，开始跑——后台做完会推过来，你接着聊或者关掉页面都行。\n\n[start_run]"
        assert strip_tool_echoes(content) == (
            "好的，开始跑——后台做完会推过来，你接着聊或者关掉页面都行。"
        )

    def test_paragraph_seam_collapses(self) -> None:
        content = "先说一句。\n\n[start_run]\n\n再说一句。"
        assert strip_tool_echoes(content) == "先说一句。\n\n再说一句。"

    def test_mid_sentence_mention_is_prose_and_stays(self) -> None:
        content = "我接下来会用 start_run 开工，也会调 [start_run] 来完成它。"
        assert strip_tool_echoes(content) == content

    def test_unregistered_bracket_name_stays(self) -> None:
        content = "这是一个普通括号标记。\n\n[note]"
        assert strip_tool_echoes(content) == content

    def test_no_bracket_fast_path_returns_input(self) -> None:
        content = "完全没有方括号的一句话。"
        assert strip_tool_echoes(content) is content

    def test_indented_echo_line_is_stripped(self) -> None:
        content = "开工。\n  [wrap_up]  "
        assert strip_tool_echoes(content) == "开工。"

    def test_all_registered_names_are_stripped(self) -> None:
        for name in sorted(_TOOL_ECHO_NAMES):
            assert strip_tool_echoes(f"说一句。\n\n[{name}]") == "说一句。"

    def test_registered_names_cover_the_observed_tic(self) -> None:
        # The regression anchor: start_run (the plan path terminal) and
        # wrap_up (the trigger turn's terminal) must both be in the set.
        assert "start_run" in _TOOL_ECHO_NAMES
        assert "wrap_up" in _TOOL_ECHO_NAMES


class _DeltaSink:
    """Collects emitted fragments; join() is the client's live bubble."""

    def __init__(self) -> None:
        self.fragments: list[str] = []

    async def emit(self, text: str) -> None:
        self.fragments.append(text)

    def join(self) -> str:
        return "".join(self.fragments)


async def _drive(fragments: list[str]) -> str:
    sink = _DeltaSink()
    on_delta = make_tool_echo_delta_filter(sink.emit)
    for fragment in fragments:
        await on_delta(fragment)
    return sink.join()


class TestToolEchoDeltaFilter:
    @pytest.mark.asyncio
    async def test_echo_split_across_fragments_never_flashes(self) -> None:
        # The image-#68 stream shape: ack sentence, then the echo arrives
        # in pieces and the stream ends — the echo is held undecided at
        # stream end and simply never exists on the wire.
        out = await _drive(
            ["好的，开始跑——后台做完会推过来。\n\n[sta", "rt_ru", "n]"]
        )
        assert out == "好的，开始跑——后台做完会推过来。\n\n"

    @pytest.mark.asyncio
    async def test_echo_decided_by_newline_is_dropped_with_its_newline(self) -> None:
        out = await _drive(["先说。\n\n[start_run]", "\n后说。"])
        assert out == "先说。\n\n后说。"

    @pytest.mark.asyncio
    async def test_echo_mid_stream_seam_matches_persistence_strip(self) -> None:
        out = await _drive(["先说。\n\n[wrap_up]\n\n后说。"])
        assert out == "先说。\n\n后说。"

    @pytest.mark.asyncio
    async def test_markdown_link_prose_flows_byte_exact(self) -> None:
        # '['-initial but the second character already breaks the echo
        # shape — held for a fragment, then released verbatim.
        text = "看这里 [链接文字](https://example.com) 结尾。"
        out = await _drive(["看这里 [", "链接文字](https://exa", "mple.com) 结尾。"])
        assert out == text

    @pytest.mark.asyncio
    async def test_unregistered_bracket_line_is_released(self) -> None:
        out = await _drive(["说明。\n\n[note]", "\n下一句。"])
        assert out == "说明。\n\n[note]\n下一句。"

    @pytest.mark.asyncio
    async def test_unregistered_bracket_tail_at_stream_end_is_released(self) -> None:
        out = await _drive(["说明。\n\n[note]"])
        assert out == "说明。\n\n[note]"

    @pytest.mark.asyncio
    async def test_registered_echo_extended_into_prose_is_released(self) -> None:
        # '[start_run]' then more text on the same line — not a bare echo.
        out = await _drive(["[start_run]", " 额外说明。"])
        assert out == "[start_run] 额外说明。"

    @pytest.mark.asyncio
    async def test_plain_prose_is_untouched(self) -> None:
        text = "完全没有括号的回复。\n两行。"
        out = await _drive([text[:5], text[5:]])
        assert out == text
