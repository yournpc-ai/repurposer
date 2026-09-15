"""Pure tests for the tool-loop harness form (app/agents/tool_loop.py).

No DB, no LLM, no HTTP — a scripted stub client + a scripted execute cover
the loop laws: terminal stop, rejection→feedback→iteration, bare reply,
exhaustion, truncation absorbed as an iteration, iteration-0-only streaming,
read-tolerance at the loop boundary, the perception family's non-terminal
reads (T2b: observation feedback on the wire + kept speech), and the Tier-1
loud gate.
"""

from typing import Any

import pytest
from pydantic import BaseModel

from app.agents.tool_loop import (
    ChatTool,
    LoopResult,
    ToolLoopAgent,
    ToolObservation,
    tool_spec,
)
from app.providers.llm.base import (
    LLMError,
    LLMSchemaError,
    ProviderCapabilities,
    ToolCall,
    ToolGeneration,
)


class EchoArgs(BaseModel):
    text: str
    count: int = 1


class StubClient:
    """A scripted Tier-1 client: each iteration pops one script entry — a
    ToolGeneration to return, or an exception to raise. Records which entry
    point (stream vs plain) each iteration took and the messages it saw."""

    capabilities = ProviderCapabilities(supports_native_tools=True)

    def __init__(self, script: list[ToolGeneration | Exception]) -> None:
        self.script = list(script)
        self.entries: list[str] = []
        self.seen_messages: list[list[dict]] = []

    def _next(self) -> ToolGeneration:
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def generate_with_tools(self, messages: list[dict], tools: list[dict], **kw: Any) -> ToolGeneration:
        self.entries.append("plain")
        self.seen_messages.append(messages)
        return self._next()

    async def generate_stream_with_tools(self, messages: list[dict], tools: list[dict], on_delta=None, **kw: Any) -> ToolGeneration:
        self.entries.append("stream")
        self.seen_messages.append(messages)
        result = self._next()
        if on_delta is not None and result.content:
            for piece in result.content.split(" "):
                out = on_delta(piece + " ")
                if out is not None:
                    await out
        return result


class NoToolsClient(StubClient):
    capabilities = ProviderCapabilities(supports_native_tools=False)


def _make_agent(name: str, client: StubClient, tools: list[ChatTool] | None = None, max_iterations: int = 4) -> ToolLoopAgent:
    return ToolLoopAgent(
        name=name,
        prompt="intent_router.j2",
        system="test system",
        assemble=lambda **ctx: ({"recent": []}, []),
        tools=tools or [ChatTool("echo", "Echo the text.", EchoArgs)],
        max_iterations=max_iterations,
        client=client,  # type: ignore[arg-type] — a scripted stand-in, not a MiniMaxClient
    )


async def _always_accept(name: str, params: BaseModel | None, prose: str) -> str | None:
    return None


def _call(name: str, arguments: dict, prose: str = "spoken") -> ToolGeneration:
    return ToolGeneration(content=prose, tool_calls=[ToolCall(id="c1", name=name, arguments=arguments)])


@pytest.mark.asyncio
async def test_terminal_call_stops_the_loop() -> None:
    client = StubClient([_call("echo", {"text": "hi", "count": 2}), _call("echo", {"text": "never"})])
    seen: list[tuple[str, Any]] = []

    async def execute(name: str, params: BaseModel | None, prose: str) -> str | None:
        seen.append((name, params))
        return None

    agent = _make_agent("tl_terminal", client)
    result = await agent.call_loop(execute)
    assert isinstance(result, LoopResult)
    assert result.tool_name == "echo"
    assert isinstance(result.params, EchoArgs)
    assert result.params.text == "hi" and result.params.count == 2
    assert result.prose == "spoken"
    assert result.iterations == 1 and result.calls == ["echo"] and not result.exhausted
    assert len(seen) == 1  # the second scripted generation never ran
    assert client.entries == ["plain"]  # no on_delta → quiet call


@pytest.mark.asyncio
async def test_rejection_echoes_feedback_and_iterates() -> None:
    client = StubClient([
        _call("echo", {"text": "bad"}, prose="first speech"),
        _call("echo", {"text": "good"}, prose="second speech"),
    ])
    feedbacks = ["empty tasks — present a plan with at least one task or ask a question"]

    async def execute(name: str, params: BaseModel | None, prose: str) -> str | None:
        return feedbacks.pop(0) if feedbacks else None

    agent = _make_agent("tl_reject", client)
    result = await agent.call_loop(execute)
    assert result.iterations == 2 and result.calls == ["echo", "echo"]
    assert result.params is not None and result.params.text == "good"
    # The terminal iteration's prose lands; the rejected speech is replaced.
    assert result.prose == "second speech"
    # The rejection rode the user-message echo (never a role:tool message).
    second_user = client.seen_messages[1][1]
    assert second_user["role"] == "user"
    assert "rejected" in second_user["content"] and feedbacks == []
    assert "empty tasks" in second_user["content"]


@pytest.mark.asyncio
async def test_bare_reply_is_the_answer_floor() -> None:
    client = StubClient([ToolGeneration(content="just words", tool_calls=[])])
    agent = _make_agent("tl_bare", client)
    result = await agent.call_loop(_always_accept)
    assert result.tool_name is None and result.params is None
    assert result.prose == "just words" and not result.exhausted


@pytest.mark.asyncio
async def test_exhaustion_is_an_honest_result_never_a_success() -> None:
    client = StubClient([_call("echo", {"text": "x"}) for _ in range(3)])

    async def reject(name: str, params: BaseModel | None, prose: str) -> str | None:
        return "still wrong"

    agent = _make_agent("tl_exhaust", client, max_iterations=3)
    result = await agent.call_loop(reject)
    assert result.exhausted and result.iterations == 3
    assert result.tool_name is None and result.calls == ["echo", "echo", "echo"]


@pytest.mark.asyncio
async def test_truncation_absorbs_into_the_loop_with_feedback() -> None:
    client = StubClient([
        LLMSchemaError("truncated tool_call arguments"),
        _call("echo", {"text": "recovered"}),
    ])
    agent = _make_agent("tl_trunc", client)
    result = await agent.call_loop(_always_accept)
    assert result.iterations == 2 and not result.exhausted
    assert result.params is not None and result.params.text == "recovered"
    assert "truncated tool_call arguments" in client.seen_messages[1][1]["content"]


@pytest.mark.asyncio
async def test_only_iteration_zero_streams() -> None:
    """打字机律 on the loop: a rejected iteration's speech is replaced speech,
    so later iterations run quiet (repair-never-streams)."""
    client = StubClient([
        _call("echo", {"text": "bad"}, prose="stream me"),
        _call("echo", {"text": "good"}, prose="quiet me"),
    ])
    deltas: list[str] = []

    async def execute(name: str, params: BaseModel | None, prose: str) -> str | None:
        assert params is not None
        return "nope" if params.text == "bad" else None

    agent = _make_agent("tl_stream", client)
    result = await agent.call_loop(execute, on_delta=deltas.append)
    assert client.entries == ["stream", "plain"]
    assert "".join(deltas) == "stream me "
    assert result.prose == "quiet me"  # settled prose rides the envelope


@pytest.mark.asyncio
async def test_read_tolerance_strips_retired_wire_habits() -> None:
    """type/kind naming keys drop silently; a misplaced prose key reads as
    speech when the content channel stayed empty (打字机律牙①'s loop form)."""
    client = StubClient([
        _call("echo", {"type": "echo", "kind": "legacy", "prose": "misplaced speech", "text": "ok"}, prose=""),
    ])
    agent = _make_agent("tl_tolerance", client)
    result = await agent.call_loop(_always_accept)
    assert result.tool_name == "echo"  # extra keys never reached validation
    assert result.params is not None and result.params.text == "ok"
    assert result.prose == "misplaced speech"


@pytest.mark.asyncio
async def test_unknown_tool_and_bad_params_are_feedback_iterations() -> None:
    client = StubClient([
        _call("fly", {}),                       # unknown tool
        _call("echo", {"count": "not-an-int"}),  # missing required text + bad type
        _call("echo", {"text": "fine"}),
    ])
    agent = _make_agent("tl_feedback", client)
    result = await agent.call_loop(_always_accept)
    assert result.iterations == 3 and result.params is not None
    assert result.params.text == "fine"
    assert "unknown tool 'fly'" in client.seen_messages[1][1]["content"]
    assert "echo" in client.seen_messages[2][1]["content"]  # validation echo


@pytest.mark.asyncio
async def test_extra_calls_never_execute() -> None:
    """One call per turn — parallel gate actions would fork the turn's writes."""
    client = StubClient([
        ToolGeneration(
            content="",
            tool_calls=[
                ToolCall(id="c1", name="echo", arguments={"text": "first"}),
                ToolCall(id="c2", name="echo", arguments={"text": "second"}),
            ],
        )
    ])
    seen: list[str] = []

    async def execute(name: str, params: BaseModel | None, prose: str) -> str | None:
        assert params is not None
        seen.append(params.text)
        return None

    agent = _make_agent("tl_extra", client)
    result = await agent.call_loop(execute)
    assert seen == ["first"] and result.params is not None and result.params.text == "first"


@pytest.mark.asyncio
async def test_client_without_native_tools_fails_loud() -> None:
    """Tier law: no silent re-shape into Tier 0 — the floor lands with the
    second provider; until then the loop refuses a tools-blind client."""
    agent = _make_agent("tl_tier", NoToolsClient([]))
    with pytest.raises(LLMError, match="Tier 1"):
        await agent.call_loop(_always_accept)


# ---- T2b 感知族: non-terminal read tools -------------------------------------


def _read_tool(name: str = "lookup") -> ChatTool:
    return ChatTool(name, "Look it up.", None, terminal=False)


@pytest.mark.asyncio
async def test_read_observation_continues_the_loop_and_keeps_speech() -> None:
    """An accepted read feeds its observation back on the wire (assistant
    tool_call echo + role:tool result), KEEPS the iteration's speech, and the
    terminal call closes with the COMPOSED speech (打字机律·工具线重述: the
    kept read speech is the envelope's prefix)."""
    read = _read_tool()
    echo = ChatTool("echo", "Echo the text.", EchoArgs)
    client = StubClient([
        _call("lookup", {}, prose="let me check"),
        _call("echo", {"text": "done"}, prose="the answer"),
    ])
    seen: list[tuple[str, str]] = []

    async def execute(name: str, params: Any, prose: str):
        seen.append((name, prose))
        if name == "lookup":
            return ToolObservation("the world says hi")
        return None

    agent = _make_agent("tl_read", client, tools=[read, echo])
    result = await agent.call_loop(execute, on_delta=lambda t: None)
    assert result.iterations == 2 and result.calls == ["lookup", "echo"]
    assert result.tool_name == "echo"
    assert result.prose == "let me check\n\nthe answer"
    # The terminal execute received the composed speech — the executions
    # dock/write the whole reply, never the last iteration's fragment.
    assert seen == [
        ("lookup", "let me check"),
        ("echo", "let me check\n\nthe answer"),
    ]
    # The wire continuation: iteration 2's messages carry the assistant
    # tool_call echo + the role:tool observation.
    second = client.seen_messages[1]
    assert second[2]["role"] == "assistant"
    assert second[2]["tool_calls"][0]["function"]["name"] == "lookup"
    assert second[3] == {
        "role": "tool",
        "tool_call_id": "c1",
        "name": "lookup",
        "content": "the world says hi",
    }
    # Iteration-0-only streaming holds across reads.
    assert client.entries == ["stream", "plain"]


@pytest.mark.asyncio
async def test_rejection_after_a_read_keeps_the_observation_tail() -> None:
    """A rejected call after an accepted read still rides the user-message
    echo (ONE rejection form), and the observation tail SURVIVES — the retry
    never pays a second read."""
    read = _read_tool()
    echo = ChatTool("echo", "Echo the text.", EchoArgs)
    client = StubClient([
        _call("lookup", {}, prose=""),
        _call("echo", {"text": "bad"}, prose=""),
        _call("echo", {"text": "good"}, prose=""),
    ])
    feedbacks = ["echo broke"]

    async def execute(name: str, params: Any, prose: str):
        if name == "lookup":
            return ToolObservation("world")
        return feedbacks.pop(0) if feedbacks else None

    agent = _make_agent("tl_read_reject", client, tools=[read, echo])
    result = await agent.call_loop(execute)
    assert result.calls == ["lookup", "echo", "echo"] and not result.exhausted
    assert result.params is not None and result.params.text == "good"
    third = client.seen_messages[2]
    assert third[1]["role"] == "user" and "echo broke" in third[1]["content"]
    assert third[2]["role"] == "assistant" and third[3]["role"] == "tool"


@pytest.mark.asyncio
async def test_bare_reply_after_a_read_composes_speech() -> None:
    """The read-tolerant answer floor composes with kept read speech too."""
    read = _read_tool()
    client = StubClient([
        _call("lookup", {}, prose="checking"),
        ToolGeneration(content="the answer", tool_calls=[]),
    ])

    async def execute(name: str, params: Any, prose: str):
        return ToolObservation("world")

    agent = _make_agent("tl_read_bare", client, tools=[read])
    result = await agent.call_loop(execute)
    assert result.tool_name is None
    assert result.prose == "checking\n\nthe answer"


@pytest.mark.asyncio
async def test_read_only_turn_exhausts_honestly() -> None:
    """Reads never end the turn — a read-only loop hits the cap and degrades
    honestly (never a fabricated success)."""
    read = _read_tool()
    client = StubClient([_call("lookup", {}, prose="") for _ in range(3)])

    async def execute(name: str, params: Any, prose: str):
        return ToolObservation("more")

    agent = _make_agent("tl_read_exhaust", client, tools=[read], max_iterations=3)
    result = await agent.call_loop(execute)
    assert result.exhausted and result.calls == ["lookup"] * 3
    assert result.prose == ""


@pytest.mark.asyncio
async def test_terminal_tool_returning_observation_fails_loud() -> None:
    """Declaration/execute skew: a terminal tool's execute must never
    observe — loud, never a silent degrade."""
    client = StubClient([_call("echo", {"text": "x"})])

    async def execute(name: str, params: Any, prose: str):
        return ToolObservation("skew")

    agent = _make_agent("tl_skew_terminal", client)
    with pytest.raises(RuntimeError, match="skewed"):
        await agent.call_loop(execute)


@pytest.mark.asyncio
async def test_read_tool_terminal_accept_fails_loud() -> None:
    """The mirror skew: a read tool's execute must never end the turn."""
    read = _read_tool()
    client = StubClient([_call("lookup", {})])

    async def execute(name: str, params: Any, prose: str):
        return None

    agent = _make_agent("tl_skew_read", client, tools=[read])
    with pytest.raises(RuntimeError, match="skewed"):
        await agent.call_loop(execute)


def test_tool_spec_shape_and_zero_arg_tools() -> None:
    spec = tool_spec(ChatTool("echo", "Echo the text.", EchoArgs))
    assert spec["type"] == "function"
    assert spec["function"]["name"] == "echo"
    props = spec["function"]["parameters"]["properties"]
    assert set(props) == {"text", "count"}
    zero = tool_spec(ChatTool("start_run", "Start.", None))
    assert zero["function"]["parameters"] == {"type": "object", "properties": {}}


def test_declaration_guards() -> None:
    client = StubClient([])
    with pytest.raises(ValueError, match="tool set"):
        _make_agent("tl_empty", client, tools=[])
    dupe = [ChatTool("x", "a", EchoArgs), ChatTool("x", "b", EchoArgs)]
    with pytest.raises(ValueError, match="duplicate"):
        _make_agent("tl_dupe", client, tools=dupe)
    _make_agent("tl_roster", client)
    with pytest.raises(RuntimeError, match="Duplicate"):
        _make_agent("tl_roster", client)
