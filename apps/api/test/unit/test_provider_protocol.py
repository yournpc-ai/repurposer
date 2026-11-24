"""Layer 0 pure contracts: LLM streaming tool-call wire assembly, MiniMax dialect filter, retry/deadline, and trace export."""

from __future__ import annotations
import pytest

import json


from types import SimpleNamespace


from app.chat.editor import EDITOR_NAMES


import pytest


from app.providers.llm.base import LLMSchemaError, ToolCall


from app.providers.llm.minimax import (
    _MiniMaxToolMarkupStripper,
    _ToolCallAccumulator,
    _parse_tool_arguments,
    _strip_minimax_tool_markup,
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


@pytest.mark.asyncio
async def test_stream_done_finishes_without_waiting_for_connection_close(monkeypatch):
    """Provider completion is a protocol boundary, independent of Film."""
    import asyncio
    import json
    from contextlib import asynccontextmanager

    import httpx
    from pydantic import BaseModel
    from app.providers.llm import minimax

    class Result(BaseModel):
        ok: bool

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            event = {"choices": [{"delta": {"content": json.dumps({"ok": True})}}]}
            yield ("data: " + json.dumps(event) + "\n\n").encode()
            yield b"data: [DONE]\n\n"
            await asyncio.sleep(10)

    async def handle(request):
        assert request.extensions["timeout"]["read"] == 7
        return httpx.Response(200, stream=Stream())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        @asynccontextmanager
        async def pool():
            yield client

        monkeypatch.setattr(minimax, "_pooled_client", pool)
        async with asyncio.timeout(0.5):
            result = await minimax.MiniMaxClient(
                api_key="test", base_url="https://test.invalid"
            ).generate_stream(messages=[], response_model=Result, timeout_s=7)
    assert result.ok


@pytest.mark.asyncio
@pytest.mark.parametrize(("model", "effort"), [
    ("minimax-m3", "xhigh"), ("MiniMax-M3.1-Flash", "xhigh"), ("MiniMax-M3.1-Flash", "max"),
])
async def test_tool_call_thinking_opt_out_uses_provider_config(monkeypatch, model, effort):
    import json
    from contextlib import asynccontextmanager

    import httpx
    from app.providers.llm import minimax

    payloads = []

    async def handle(request):
        body = json.loads(request.content)
        payloads.append(body)
        if body.get("stream"):
            event = {"choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}], "usage": {}}
            return httpx.Response(
                200,
                content=("data: " + json.dumps(event) + "\n\ndata: [DONE]\n\n").encode(),
            )
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
            "usage": {},
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        @asynccontextmanager
        async def pool():
            yield client

        monkeypatch.setattr(minimax.settings, "minimax_reasoning_effort", effort)
        monkeypatch.setattr(minimax, "_pooled_client", pool)
        monkeypatch.setattr(minimax.settings, "minimax_model", model)
        monkeypatch.setattr(minimax.settings, "llm_trace_path", "")
        llm = minimax.MiniMaxClient(api_key="test", base_url="https://test.invalid")
        await llm.generate_with_tools(messages=[], tools=[], thinking=False)
        await llm.generate_with_tools(messages=[], tools=[])
        await llm.generate_stream_with_tools(messages=[], tools=[], thinking=False)
        await llm.generate_stream_with_tools(messages=[], tools=[], thinking=True)

    if model == "MiniMax-M3.1-Flash":
        assert all(payload["model"] == model and {"temperature", "top_p"}.isdisjoint(payload) and payload["reasoning_split"] for payload in payloads)
        assert all(payload["thinking"] == {"type": "adaptive"} for payload in payloads)
        assert [payload.get("reasoning_effort") for payload in payloads] == ["low", effort, "low", effort]
        return
    assert payloads[0]["thinking"] == {"type": "disabled"}
    assert "thinking" not in payloads[1]
    assert payloads[2]["thinking"] == {"type": "disabled"}
    assert payloads[3]["thinking"] == {"type": "adaptive"}


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.asyncio
async def test_simple_tool_loop_uses_low_latency_thinking(monkeypatch, streaming):
    from app.agents import tool_loop
    from app.providers.llm.base import ProviderCapabilities, ToolGeneration

    calls = []

    class Client:
        capabilities = ProviderCapabilities(supports_native_tools=True)

        async def generate_with_tools(self, **kwargs):
            calls.append(kwargs)
            return ToolGeneration("done", [ToolCall(id="call-1", name="answer", arguments={})])

        async def generate_stream_with_tools(self, **kwargs):
            calls.append(kwargs)
            return ToolGeneration("done", [ToolCall(id="call-1", name="answer", arguments={})])

    class Template:
        def render(self, **_kwargs):
            return "test"

    class Environment:
        def get_template(self, _name):
            return Template()

    monkeypatch.setattr(tool_loop, "jinja_env", Environment())
    agent = tool_loop.ToolLoopAgent(
        name=f"test-tool-thinking-{streaming}",
        prompt="unused.j2",
        system="test",
        assemble=lambda **_kwargs: ({}, None),
        tools=[tool_loop.ChatTool(name="answer", description="Finish", params_model=None)],
        client=Client(),
    )

    async def execute(_name, _params, _call_id):
        return None

    async def delta(_text):
        return None

    result = await agent.call_loop(execute, on_delta=delta if streaming else None)
    assert result.tool_name == "answer"
    assert len(calls) == 1 and calls[0]["thinking"] is False


@pytest.mark.asyncio
async def test_repair_observation_leaves_speech_to_the_current_stage(monkeypatch):
    from pydantic import BaseModel, ConfigDict
    from app.agents import tool_loop
    from app.providers.llm.base import ProviderCapabilities, ToolGeneration

    class Args(BaseModel):
        model_config = ConfigDict(extra="forbid")

    calls = []

    class Client:
        capabilities = ProviderCapabilities(supports_native_tools=True)

        async def generate_with_tools(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return ToolGeneration("I'll start production.", [ToolCall(
                    id="invalid", name="answer", arguments={"title": "internal correction"},
                )])
            return ToolGeneration("Production starts now.", [ToolCall(id="valid", name="answer", arguments={})])

    class Template:
        def render(self, **_kwargs):
            return "test"

    class Environment:
        def get_template(self, _name):
            return Template()

    monkeypatch.setattr(tool_loop, "jinja_env", Environment())
    agent = tool_loop.ToolLoopAgent(
        name="repair-speech-seat", prompt="unused.j2", system="test",
        assemble=lambda **_kwargs: ({}, None),
        tools=[tool_loop.ChatTool(name="answer", description="Finish", params_model=Args)],
        client=Client(),
    )

    async def execute(_name, _params, _speech):
        return None

    result = await agent.call_loop(execute)
    repair_messages = json.dumps(calls[-1]["messages"], ensure_ascii=False)
    assert result.prose == "Production starts now."
    assert "上次工具调用被拒绝" in repair_messages
    assert "Speak to the user" not in repair_messages


@pytest.mark.asyncio
async def test_correction_retains_original_tool_execution_schema(monkeypatch):
    from pydantic import BaseModel, ConfigDict
    from app.agents import tool_loop
    from app.agents.candidate_correction import CandidateRecord, CandidateScope
    from app.providers.llm.base import ProviderCapabilities, ToolGeneration

    class Args(BaseModel):
        model_config = ConfigDict(extra="forbid")

        base_ref: str

    class ProjectedArgs(BaseModel):
        model_config = ConfigDict(extra="forbid")

    original_create = CandidateRecord.create.__func__

    def fixed_create(_cls, **kwargs):
        kwargs["candidate_id"] = "cnd_fixed"
        return original_create(_cls, **kwargs)

    monkeypatch.setattr(CandidateRecord, "create", classmethod(fixed_create))
    monkeypatch.setattr(CandidateRecord, "verify", lambda self, request: None)
    scope = CandidateScope(
        owner_id="agent:repair-execution-schema",
        conversation_id="loop:repair-execution-schema",
    )
    candidate_digest = CandidateRecord.create(
        tool_name="answer",
        arguments={"unexpected": True},
        errors=[],
        schema=ProjectedArgs.model_json_schema(),
        scope=scope,
        base_keys=frozenset(),
        call_id="invalid",
    ).candidate_digest
    calls = []

    class Client:
        capabilities = ProviderCapabilities(supports_native_tools=True)

        async def generate_with_tools(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return ToolGeneration("", [ToolCall(
                    id="invalid", name="answer", arguments={"unexpected": True},
                )])
            return ToolGeneration("", [ToolCall(
                id="correct",
                name="correct_tool_candidate",
                arguments={
                    "candidate_id": "cnd_fixed",
                    "candidate_digest": candidate_digest,
                    "mode": "replace",
                    "reason": "Replace the invalid arguments",
                    "arguments": {},
                },
            )])

    class Template:
        def render(self, **_kwargs):
            return "test"

    class Environment:
        def get_template(self, _name):
            return Template()

    monkeypatch.setattr(tool_loop, "jinja_env", Environment())
    agent = tool_loop.ToolLoopAgent(
        name="repair-execution-schema", prompt="unused.j2", system="test",
        assemble=lambda **_kwargs: ({}, None),
        tools=[tool_loop.ChatTool(
            name="answer", description="Finish", params_model=Args, repairable=True,
        )],
        client=Client(),
    )
    executed = []

    async def execute(name, _params, _speech):
        executed.append(name)

    def assemble(**facts):
        if facts.get("active_repair") is not None:
            from app.agents.candidate_correction import correction_tool

            return tool_loop.RoundAssembly(system="test", tools=[correction_tool()])
        return tool_loop.RoundAssembly(system="test", tools=[tool_loop.ChatTool(
            name="answer", description="Finish", params_model=ProjectedArgs, repairable=True,
        )])

    result = await agent.call_loop(execute, round_assembler=assemble)
    assert result.tool_name == "answer"
    assert executed == ["answer"]
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_structured_thinking_opt_out_uses_provider_config(monkeypatch):
    import json
    from contextlib import asynccontextmanager

    import httpx
    from pydantic import BaseModel
    from app.providers.llm import minimax

    class Result(BaseModel):
        ok: bool

    payloads = []

    async def handle(request):
        body = json.loads(request.content)
        payloads.append(body)
        content = json.dumps({"ok": True})
        if body.get("stream"):
            event = {"choices": [{"delta": {"content": content}, "finish_reason": "stop"}], "usage": {}}
            return httpx.Response(
                200,
                content=("data: " + json.dumps(event) + "\n\ndata: [DONE]\n\n").encode(),
            )
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {},
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        @asynccontextmanager
        async def pool():
            yield client

        monkeypatch.setattr(minimax, "_pooled_client", pool)
        monkeypatch.setattr(minimax.settings, "minimax_model", "minimax-m3")
        monkeypatch.setattr(minimax.settings, "llm_trace_path", "")
        llm = minimax.MiniMaxClient(api_key="test", base_url="https://test.invalid")
        assert (await llm.generate(messages=[], response_model=Result)).ok
        assert (await llm.generate_stream(messages=[], response_model=Result)).ok

    assert [payload["thinking"] for payload in payloads] == [
        {"type": "disabled"}, {"type": "disabled"},
    ]


def test_minimax_tool_dialect_never_leaks_truncated_seq29_markup() -> None:
    leaked = (
        "这三个都是标准 Freesound 预览文件，我试一下导入第二个（Click_7），"
        "同时读出片子的当前版本。]<]minimax[>[<tool_call>\n"
        "]<]minimax[>[<invoke name=\"import_s"
    )
    expected = (
        "这三个都是标准 Freesound 预览文件，我试一下导入第二个（Click_7），"
        "同时读出片子的当前版本。"
    )
    assert _strip_minimax_tool_markup(leaked) == expected
    for split in range(len(leaked) + 1):
        stripper = _MiniMaxToolMarkupStripper()
        streamed = (
            stripper.feed(leaked[:split])
            + stripper.feed(leaked[split:])
            + stripper.finish()
        )
        assert streamed == expected


def test_minimax_tool_filter_preserves_markdown_links_code_and_less_than() -> None:
    ordinary = "**保留** <https://example.com> 与 1 < 2，以及 `<tool>`。"
    assert _strip_minimax_tool_markup(ordinary) == ordinary
    stripper = _MiniMaxToolMarkupStripper()
    streamed = "".join(stripper.feed(char) for char in ordinary) + stripper.finish()


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize(
    ("status_code", "user_key"),
    [(402, "provider_quota_exhausted"), (400, "provider_unavailable")],
)
@pytest.mark.asyncio
async def test_deterministic_provider_rejections_never_blindly_retry(
    monkeypatch, streaming, status_code, user_key,
):
    from contextlib import asynccontextmanager

    import httpx
    from app.providers.llm import minimax
    from app.providers.llm.base import LLMError

    calls = 0

    async def handle(request):
        nonlocal calls
        calls += 1
        return httpx.Response(status_code, json={"error": "provider rejected request"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        @asynccontextmanager
        async def pool():
            yield client

        monkeypatch.setattr(minimax, "_pooled_client", pool)
        monkeypatch.setattr(minimax.settings, "llm_trace_path", "")
        llm = minimax.MiniMaxClient(api_key="test", base_url="https://test.invalid")
        with pytest.raises(LLMError) as caught:
            if streaming:
                await llm.generate_stream_with_tools(messages=[], tools=[])
            else:
                await llm.generate_with_tools(messages=[], tools=[])

    assert calls == 1
    assert caught.value.user_key == user_key


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.asyncio
async def test_outer_deadline_never_starts_another_provider_request(
    monkeypatch, streaming,
):
    import asyncio
    from contextlib import asynccontextmanager

    import httpx
    from app.providers.llm import minimax

    calls = 0

    async def handle(request):
        nonlocal calls
        calls += 1
        raise asyncio.TimeoutError

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        @asynccontextmanager
        async def pool():
            yield client

        monkeypatch.setattr(minimax, "_pooled_client", pool)
        monkeypatch.setattr(minimax.settings, "llm_trace_path", "")
        llm = minimax.MiniMaxClient(api_key="test", base_url="https://test.invalid")
        with pytest.raises(asyncio.TimeoutError):
            if streaming:
                await llm.generate_stream_with_tools(messages=[], tools=[])
            else:
                await llm.generate_with_tools(messages=[], tools=[])

    assert calls == 1


def test_trace_inventory_preserves_exact_part_sizes_and_correlated_records(tmp_path, monkeypatch):
    import json
    from uuid import uuid4
    from pathlib import Path
    from app.metering import bind_conversation_turn, current_conversation_trace, bind_model_prompt
    from app.providers.llm import trace

    path = tmp_path / "exchange.jsonl"
    monkeypatch.setattr(trace.settings, "llm_trace_path", str(path))
    payload = {"messages": [{"role": "system", "content": "规则\nhello"},
                            {"role": "tool", "name": "preview", "tool_call_id": "t1",
                             "content": [{"type": "text", "text": "真实"},
                                         {"type": "image_url", "image_url": {"url": "data:image/png;base64,YWJj"}}]}],
               "tools": [{"type": "function", "function": {"name": "save", "parameters": {"type": "object"}}}]}
    project, conversation, turn = uuid4(), uuid4(), uuid4()
    with bind_conversation_turn(project_id=project, conversation_id=conversation, turn_id=turn), bind_model_prompt({"agent": "trace_test", "iteration": 2, "system_sources": [{"template": "old.j2", "text": "actual source"}]}):
        call_id = trace.trace_start(payload, "generate_with_tools", provider="minimax", model="test-model")
        trace.trace_finish(call_id, provider="minimax", model="test-model", response={"usage": {"prompt_tokens": 123}})
    assert current_conversation_trace() is None
    request, response = [json.loads(line) for line in path.read_text().splitlines()]
    assert request["project_id"] == response["project_id"] == str(project)
    assert request["model_call_id"] == response["model_call_id"] == call_id
    assert request["assembly"]["iteration"] == 2
    assert request["assembly"]["system_sources"][0]["text"] == "actual source"
    assert "assembly" not in request["payload"]
    inventory = request["inventory"]
    compact = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    assert inventory["payload"]["json_chars"] == len(compact)
    assert inventory["payload"]["utf8_bytes"] == len(compact.encode())
    assert inventory["messages"][0]["parts"] == [{"type": "text", "text_chars": 8}]
    assert inventory["tools"][0]["name"] == "save"
    media = request["payload"]["messages"][1]["content"][1]["image_url"]["url"]
    assert Path(media["binary_ref"]).read_bytes() == b"abc"
    assert response["response"]["usage"]["prompt_tokens"] == 123


def test_model_trace_export_supports_ids_full_content_and_pending_call(tmp_path):
    import json
    import runpy
    from pathlib import Path
    from uuid import uuid4
    script = Path(__file__).resolve().parents[2] / "scripts" / "inspect_model_trace.py"
    api = runpy.run_path(str(script))
    call, conversation = str(uuid4()), str(uuid4())
    request = {"phase": "request", "model_call_id": call, "conversation_id": conversation,
               "started_at": "2026-11-06T13:00:00Z",
               "payload": {"messages": [{"role": "system", "content": "full prompt\n真实上下文"}],
                           "tools": [{"function": {"name": "design_video", "parameters": {"type": "object"}}}]}}
    trace = tmp_path / "trace.jsonl"
    trace.write_text(json.dumps(request) + "\n")
    rows = api["select_records"](trace, "legacy-project", {conversation})
    assert rows == [request]
    assert api["select_records"](trace, call, set()) == [request]
    out = tmp_path / "export"
    report = api["export_records"](rows, out)
    assert "pending (no recorded response/error)" in report
    assert "not token attribution" in report
    assert (out / call / "message-000.txt").read_text() == "full prompt\n真实上下文"
    assert json.loads((out / call / "tool-000-design_video.json").read_text())["function"]["name"] == "design_video"


def test_trace_export_keeps_historical_sources_and_actual_round_diff(tmp_path):
    import runpy
    from pathlib import Path
    from uuid import uuid4
    api = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts" / "inspect_model_trace.py"))
    first, second = str(uuid4()), str(uuid4())
    rows = [{"phase": "request", "model_call_id": first,
             "payload": {"messages": [{"role": "user", "content": "original"}]}},
            {"phase": "request", "model_call_id": second,
             "assembly": {"agent": "test", "iteration": 1,
                          "system_sources": [{"template": "old.j2", "path": "/old/root/old.j2", "sha256": "frozen", "text": "frozen source"}]},
             "payload": {"messages": [{"role": "user", "content": "original plus rejection"}]}}]
    report = api["export_records"](rows, tmp_path)
    assert "Source provenance unavailable" in report
    assert "/old/root/old.j2" in report
    assert (tmp_path / second / "source-system_sources-000.j2").read_text() == "frozen source"
    diff = (tmp_path / second / "messages-diff.patch").read_text()
    assert '-    "content": "original"' in diff
    assert '+    "content": "original plus rejection"' in diff


def test_normalized_argument_trace_keeps_original_response_and_exports_conversions(tmp_path, monkeypatch):
    import json
    import runpy
    from pathlib import Path
    from app.metering import bind_model_prompt
    from app.providers.llm import trace
    path = tmp_path / 'trace.jsonl'
    monkeypatch.setattr(trace.settings, 'llm_trace_path', str(path))
    assembly = {'agent': 'numeric_test', 'iteration': 0}
    with bind_model_prompt(assembly):
        call_id = trace.trace_start({'messages': [], 'tools': []}, 'generate_with_tools', provider='minimax', model='test-model')
        trace.trace_finish(call_id, provider='minimax', model='test-model', response={'arguments': {'weight': '600'}})
        trace.trace_argument_normalization(model_call_id=assembly['model_call_id'], tool_call_id='tool1',
            agent='numeric_test', iteration=0, changes=[{'path': ['weight'], 'before': '600', 'after': 600}])
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert rows[1]['response']['arguments']['weight'] == '600'
    assert rows[2]['phase'] == 'arguments_normalized'
    assert rows[2]['model_call_id'] == call_id
    exporter = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'scripts' / 'inspect_model_trace.py'))
    report = exporter['export_records'](rows, tmp_path / 'export')
    assert 'Normalized argument' in report and '`"600"`' in report


def _composition_resource(*, suffix="one", provenance=None):
    from uuid import NAMESPACE_URL, uuid5

    composition_id = str(uuid5(NAMESPACE_URL, f"test-composition-{suffix}"))
    version_id = str(uuid5(NAMESPACE_URL, f"test-version-{suffix}"))
    return {
        "kind": "composition",
        "composition_id": composition_id,
        "version_id": version_id,
        "content_digest": "d" * 64,
        "name": f"Work {suffix}",
        "base_ref": {
            "composition_id": composition_id,
            "composition_version_id": version_id,
            "content_digest": "d" * 64,
        },
        "skill_provenance": provenance or {},
        "scenes": [{"scene_id": "second"}],
        "clip_targets": [{"clip_id": "title-second", "text": "Old title"}],
    }


def _video_round(tools, *, drafts=(), snapshot, skill=None, material_pending=False,
                 package_sessions=None, user_text="review the draft", pending_question=None,
                 active_repair=None, mode="plan", iteration=None, interim_prose_count=0,
                 new_result=False, version_saved=False, new_result_tool=None, asset_mentions=None, attachments=()):
    from app.chat.prompts import assemble_video_round

    return assemble_video_round({
        "tools": tools,
        "drafts": drafts,
        "snapshot": snapshot,
        "skill": skill,
        "material_pending": material_pending,
        "package_sessions": package_sessions,
        "user_text": user_text,
        "version_saved": version_saved,
        "pending_question": pending_question,
        "active_repair": active_repair,
        "mode": mode,
        "iteration": iteration,
        "interim_prose_count": interim_prose_count,
        "new_result": new_result,
        "new_result_tool": new_result_tool,
        "asset_mentions": asset_mentions,
        "attachments": attachments,
    })


async def _immediate(value):
    return value

