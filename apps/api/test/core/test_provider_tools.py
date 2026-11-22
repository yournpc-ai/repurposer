"""Deterministic provider tool-call and trace contracts.

No real model, paid production or external HTTP: mocked transports cover wire
fragment assembly, argument parsing, completion boundaries, provider rejections
and the complete local trace/export path.
"""

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
@pytest.mark.parametrize("model", ["minimax-m3", "MiniMax-M3.1-Flash"])
async def test_tool_call_thinking_opt_out_uses_provider_config(monkeypatch, model):
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

        monkeypatch.setattr(minimax, "_pooled_client", pool)
        monkeypatch.setattr(minimax.settings, "minimax_model", model)
        monkeypatch.setattr(minimax.settings, "llm_trace_path", "")
        llm = minimax.MiniMaxClient(api_key="test", base_url="https://test.invalid")
        await llm.generate_with_tools(messages=[], tools=[], thinking=False)
        await llm.generate_with_tools(messages=[], tools=[])
        await llm.generate_stream_with_tools(messages=[], tools=[], thinking=False)
        await llm.generate_stream_with_tools(messages=[], tools=[])

    if model == "MiniMax-M3.1-Flash":
        assert all(payload["model"] == model and "temperature" not in payload for payload in payloads)
        assert all(payload["thinking"] == {"type": "adaptive"} for payload in payloads)
        assert [payload.get("reasoning_effort") for payload in payloads] == ["low", None, "low", None]
        return
    assert payloads[0]["thinking"] == {"type": "disabled"}
    assert "thinking" not in payloads[1]
    assert payloads[2]["thinking"] == {"type": "disabled"}
    assert "thinking" not in payloads[3]


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.asyncio
async def test_chat_tool_loop_always_disables_provider_thinking(monkeypatch, streaming):
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
                 new_result=False, version_saved=False, new_result_tool=None, asset_mentions=None):
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
    })


def test_bound_skill_tools_follow_material_and_saved_version_state():
    from types import SimpleNamespace
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.conversation_context import conversation_context_tool
    from app.chat.intent import intent_router
    from app.chat.turn_tools import tools_for_bound_skill

    skill = SimpleNamespace(skill_id="promo-video")
    declared = [*tools_for_bound_skill(intent_router.tools, skill), conversation_context_tool()]

    fresh = _video_round(
        declared, snapshot=ContextSnapshot("fresh", frozenset({"project:one"})),
        skill=skill, material_pending=True,
    ).tools
    fresh_names = {tool.name for tool in fresh}
    assert not {"get_graph", "get_node", "edit_graph"} & fresh_names
    assert "design_video" not in fresh_names
    assert "get_understanding" in fresh_names
    assert "prepare_video_materials" in fresh_names
    assert "read_conversation_context" in fresh_names
    assert {"ask_user", "answer"} <= fresh_names

    prepared = _video_round(
        declared,
        snapshot=ContextSnapshot(
            "prepared", frozenset({"project:one", "snapshot:source:digest"}),
            resources=(("snapshot:source:digest", {"kind": "image", "snapshot_id": "source", "digest": "d" * 64}),),
        ),
        skill=skill, material_pending=True,
    ).tools
    assert "create_video" in {tool.name for tool in prepared}
    assert "present_plan" not in {tool.name for tool in prepared}

    saved_resource = _composition_resource(provenance={"skill": "promo-video"})
    saved = _video_round(
        declared,
        snapshot=ContextSnapshot(
            "saved", frozenset({"project:one", "snapshot:source:digest", "composition:version:digest"}),
            resources=(("composition:version:digest", saved_resource),),
        ),
        skill=skill, material_pending=True, user_text="change the title",
    ).tools
    saved_names = {tool.name for tool in saved}
    assert {"split_clip", "inspect_timeline", "preview_range"} <= saved_names
    assert not {"revise_video", "present_plan", "start_run"} & saved_names
    assert "design_video" not in saved_names
    assert "create_video" not in saved_names


def test_scene_plan_and_explicit_count_have_no_six_scene_cap():
    from app.skills.external import SkillPolicy
    from app.chat.editor_create import CreateVideoArgs

    args = CreateVideoArgs.model_validate({
        "name": "Seven beats",
        "shots": [{"headline": f"Beat {index}", "duration_seconds": 1} for index in range(7)],
    })
    assert len(args.shots) == 7
    assert SkillPolicy(scene_count=7).scene_count == 7


@pytest.mark.asyncio
async def test_derived_web_view_infers_its_unique_view_id():
    from uuid import uuid4

    from app.editing.schemas import CompositionContent, VersionSettings
    from app.editing.validators import validate_content
    from app.tools.video.design import (
        CompositionSceneAuthoring,
        CompositionScenePlan,
        _expand_scene_authoring,
        _scene_plan_write,
    )

    parent_id, derived_id = uuid4(), uuid4()
    facts = {
        parent_id: {
            "kind": "web", "digest": "p" * 64, "storage_key": "web.json",
            "meta": {"views": [{
                "view_id": "view-3", "storage_key": "view.png", "digest": "v" * 64,
                "width": 1440, "height": 900, "elements": [],
            }]},
        },
        derived_id: {
            "kind": "image", "digest": "d" * 64, "storage_key": "derived.png",
            "meta": {
                "origin": "web_view", "web_snapshot_id": str(parent_id), "view_id": "view-3",
                "width": 1440, "height": 900,
            },
        },
    }
    content = _scene_plan_write({
        "schema_version": 1,
        "settings": VersionSettings(width=1920, height=1080).model_dump(mode="json"),
        "sources": [], "scenes": [], "timeline": {"tracks": [], "transitions": []},
    }, [CompositionScenePlan(scene_id="feature", intent="Show the actual feature")])
    expanded = await _expand_scene_authoring(content, CompositionSceneAuthoring(
        scene_id="feature", snapshot_id=derived_id, source_motion="hold", headline="Feature",
    ), facts)
    candidate = CompositionContent.model_validate(expanded)
    validate_content(candidate, facts)
    web = next(clip for track in candidate.timeline.tracks for clip in track.clips if clip.object.kind == "web")
    assert web.object.view_id == "view-3"
    assert web.source.snapshot_id == parent_id




def test_chat_tool_loops_allow_twenty_bounded_iterations():
    from app.chat.intent import intent_router

    assert intent_router.max_iterations == 20


def test_native_chat_prompt_contains_pending_question_and_language():
    from app.agents.base import jinja_env
    from app.chat.prompts import chat_system

    plan = chat_system()
    assert plan.count("待回答的问题：") == 1
    assert plan.count("交流语言：") == 1
    assert "pending_disposition" in plan

    opening = jinja_env.get_template("chat/user.j2").render(
        recent=["- user: earlier"], message="latest answer",
        asset_lines=["- page (web_page)"], understanding_lines=["- Summary: evidence"],
        persona_lines=["- tone: rational"], brief_lines=["- target_seconds: 30 (user-stated)"],
        confirmation_line="确认设置： execution=auto, spending=auto.",
        pending_lines=["- question: specs?"],
    )
    opening_order = (
        "最近的对话：", "上传的文件", "系统对本组素材的理解", "用户人设",
        "目前的 Brief", "确认设置：", "你之前的问题仍待回答", "用户消息：",
    )
    assert [opening.index(block) for block in opening_order] == sorted(
        opening.index(block) for block in opening_order
    )


def test_missing_package_session_uses_native_create_protocol(installed_promo):
    from app.agents.tool_loop import ContextSnapshot, tool_spec
    from app.chat.intent import intent_router
    from app.chat.turn_tools import tools_for_bound_skill
    from app.skills.resolution import get_builtin_skill_option

    skill = get_builtin_skill_option("promo-video").reference
    declared = tools_for_bound_skill(intent_router.tools, skill)
    projected = _video_round(
        declared,
        snapshot=ContextSnapshot("fresh", frozenset({"project:one"})),
        skill=skill,
        package_sessions={},
    )
    create = next(tool for tool in projected.tools if tool.name == "create_video")
    properties = tool_spec(create)["function"]["parameters"]["properties"]
    assert "shots" in properties and "scene_plan" not in properties
    assert "create_video" in {tool.name for tool in projected.tools}


def test_saved_and_ambiguous_work_use_editor_without_legacy_draft_review():
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.intent import intent_router

    saved = _composition_resource()
    snapshot = ContextSnapshot(
        "complete project and an unrelated asset", frozenset({"composition:ver-one:digest"}),
        resources=(("composition:ver-one:digest", saved),
                   ("asset:first", {"kind": "asset", "asset_id": "first", "type": "image"}),
                   ("asset:second", {"kind": "asset", "asset_id": "second", "type": "image"})),
    )
    edited = _video_round(intent_router.tools, snapshot=snapshot, user_text="Change the second Scene title",
                          asset_mentions={"first": "product.png", "second": "product.png", "foreign": "other.png"})
    assert json.loads(edited.context)["mentioned_assets"] == [
        {"asset_id": asset_id, "type": "image", "label": "product.png"} for asset_id in ("first", "second")
    ]
    assert edited.caller_state["video_target"] == saved
    assert (EDITOR_NAMES - {"create_video"}) <= {tool.name for tool in edited.tools}
    assert not {"design_video", "review_working_draft"} & {tool.name for tool in edited.tools}
    assert "complete project and an unrelated asset" not in edited.context
    assert "title-second" not in edited.context
    assert edited.include_observation_media
    presenting = _video_round(intent_router.tools, snapshot=snapshot, version_saved=True,
                              user_text="Review the draft and deliver the MP4")
    assert presenting.caller_state["video_target"] == saved
    assert (EDITOR_NAMES - {"create_video"}) <= {tool.name for tool in presenting.tools}
    draft_only = _video_round(intent_router.tools, snapshot=snapshot, version_saved=True,
                             user_text="请保存初稿给我看。")
    assert {t.name for t in draft_only.tools} == {"answer"}

    other = _composition_resource(suffix="two")
    ambiguous = _video_round(
        intent_router.tools,
        snapshot=ContextSnapshot("two", resources=(("one", saved), ("two", other))),
    )
    assert ambiguous.caller_state["video_target"] is None
    assert (EDITOR_NAMES - {"create_video"}) <= {tool.name for tool in ambiguous.tools}
    assert "ask_user" in {tool.name for tool in ambiguous.tools}


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.asyncio
async def test_final_video_provider_request_clears_pending_and_historical_media(
    monkeypatch, streaming,
):
    from app.agents import tool_loop
    from app.chat.intent import intent_router
    from app.providers.llm.base import ProviderCapabilities, ToolGeneration

    calls = []
    pending = SimpleNamespace(
        id="question-1", content="Which title?", question={"question": "Which title?"},
        intent={"question": {"question": "Which title?"}},
    )
    saved = _composition_resource()
    snapshot = tool_loop.ContextSnapshot(
        "full project", frozenset({"composition:ver-one:digest"}),
        resources=(("composition:ver-one:digest", saved),),
    )
    historical = {
        "role": "tool", "tool_call_id": "old", "content": [
            {"type": "text", "text": "old review"},
            {"type": "video", "caption": "Historical observation old", "data_url": "data:video/mp4;base64,AA=="},
        ],
    }

    class Client:
        capabilities = ProviderCapabilities(supports_native_tools=True)

        async def generate_with_tools(self, **kwargs):
            return await self.answer(**kwargs)

        async def generate_stream_with_tools(self, **kwargs):
            return await self.answer(**kwargs)

        async def answer(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return ToolGeneration("", [ToolCall(
                    id="split-1", name="split_clip",
                    arguments={"clip_id": "title-second", "time": 1},
                )])
            return ToolGeneration("Saved", [ToolCall(id="answer-1", name="answer", arguments={})])

    class Template:
        def render(self, **_kwargs):
            return "current user request"

    class Environment:
        def get_template(self, _name):
            return Template()

    monkeypatch.setattr(tool_loop, "jinja_env", Environment())
    agent = tool_loop.ToolLoopAgent(
        name=f"video-round-{streaming}", prompt="unused.j2", system="test",
        assemble=lambda **_kwargs: ({}, None), tools=intent_router.tools, client=Client(),
    )

    async def restore(_snapshot, _messages):
        return tool_loop.ConversationHistory(messages=(historical,))

    async def execute(name, _params, _speech):
        nonlocal pending
        if name == "split_clip":
            pending = None
            return tool_loop.ToolObservation("saved")
        return None

    def assemble(**facts):
        from app.chat.prompts import assemble_video_round

        return assemble_video_round({
            **facts, "mode": "plan", "user_text": "Split the selected clip at one second.",
            "answered_this_opening": True,
            "pending_question": lambda: pending,
        })

    result = await agent.call_loop(
        execute, refresh_context=lambda: _immediate(snapshot), restore_context=restore,
        dialogue=[{"role": "user", "content": "Second title"}],
        round_assembler=assemble, on_delta=(lambda _text: _immediate(None)) if streaming else None,
    )
    assert result.tool_name == "answer"
    assert len(calls) == 2
    first, second = calls
    first_text = json.dumps(first["messages"], ensure_ascii=False)
    second_text = json.dumps(second["messages"], ensure_ascii=False)
    for wire in (first, second):
        assert any(m["content"] == "Second title" for m in wire["messages"])
        assert any("clarified_request" in str(m["content"]) and
                   "Split the selected clip at one second." in str(m["content"])
                   for m in wire["messages"])
    assert "Which title?" in first_text
    assert "Which title?" not in second_text
    assert "old review" not in second_text and "Historical observation old" not in second_text
    assert all(
        part.get("type") == "text"
        for message in second["messages"] if isinstance(message.get("content"), list)
        for part in message["content"] if isinstance(part, dict)
    )
    assert "review_working_draft" not in {
        item["function"]["name"] for item in second["tools"]
    }


async def _immediate(value):
    return value


def test_editor_tools_do_not_depend_on_requested_action():
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.intent import intent_router

    saved = _composition_resource()
    snapshot = ContextSnapshot("saved", resources=(("work", saved),))
    first = _video_round(intent_router.tools, snapshot=snapshot, user_text="Split the second clip")
    second = _video_round(intent_router.tools, snapshot=snapshot, user_text="Change the title")
    assert {t.name for t in first.tools} == {t.name for t in second.tools}
    assert (EDITOR_NAMES - {"create_video"}) <= {t.name for t in second.tools}
    assert not {"start_run", "revise_video", "design_video"} & {t.name for t in second.tools}
    assert "clip_targets" not in second.context and "title-second" not in second.context


def test_video_rounds_allow_service_text_for_reads_and_edits():
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.intent import intent_router

    for iteration in (0, 1, 6):
        projected = _video_round(intent_router.tools, snapshot=ContextSnapshot("empty"), iteration=iteration)
        assert projected.stream_prose
        assert "speech_rule" not in projected.context

    media = _video_round(
        intent_router.tools, snapshot=ContextSnapshot("empty"),
        user_text="Make a three-second ambient score only", new_result_tool="generate_music",
    )
    assert media.project_reply is not None and media.missing_tool_feedback is None

    saved = _composition_resource()
    edit = _video_round(
        intent_router.tools,
        snapshot=ContextSnapshot(
            "saved", resources=(("composition", saved),),
        ),
        user_text="Change the title", iteration=0, new_result=True,
    )
    assert edit.caller_state["video_target"] == saved
    assert edit.stream_prose and edit.project_reply is not None


def test_existing_media_only_offer_keeps_creation_and_excludes_generation():
    from app.agents.tool_loop import ContextSnapshot, tool_spec
    from app.chat.intent import intent_router
    from app.chat.prompts import assemble_video_round

    turn = assemble_video_round({
        "tools": intent_router.tools, "snapshot": ContextSnapshot("empty"),
        "user_text": "Create a cut from the uploaded footage. No new media or export.",
    })
    tools = {tool.name: tool for tool in turn.tools}
    assert {"create_video", "prepare_video_materials"} <= tools.keys()
    assert not {"generate_voice", "generate_image", "generate_music", "export_video"} & tools.keys()
    shot = tool_spec(tools["create_video"])["function"]["parameters"]["$defs"]["FirstShot"]["properties"]
    assert "narration" not in shot and "snapshot_id" in shot


def test_fixed_recording_is_available_before_word_alignment():
    from app.agents.tool_loop import ContextSnapshot, tool_spec
    from app.chat.intent import intent_router

    audio = {"kind": "audio", "snapshot_id": "fixed", "alignment": {"status": "PROCESSING"}}
    snapshot = ContextSnapshot("fresh", resources=(("audio", audio),))
    from app.chat.prompts import assemble_video_round

    projected = assemble_video_round({
        "tools": intent_router.tools, "snapshot": snapshot, "user_text": "Create the video with this recording",
        "media_receipts": [{"role": "narration", "status": "available", "snapshot_id": "fixed"}],
    })
    tools = {tool.name: tool for tool in projected.tools}
    shot = tool_spec(tools["create_video"])["function"]["parameters"]["$defs"]["FirstShot"]["properties"]
    assert not {"narration", "narration_alignment_id", "narration_snapshot_id"} & shot.keys()
    assert "inspect_timeline" not in tools and "insert_audio" not in tools
    assert "fixed" in projected.context


def test_native_create_projection_keeps_skill_context(installed_promo):
    from types import SimpleNamespace
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.intent import intent_router
    from app.chat.turn_tools import tools_for_bound_skill

    skill = SimpleNamespace(skill_id="promo-video")
    snapshot = ContextSnapshot("fresh", frozenset({"project:one"}), skill_method="COMPLETE SKILL METHOD FOR PLANNING")
    projected = _video_round(tools_for_bound_skill(intent_router.tools, skill), snapshot=snapshot, skill=skill)
    assert "create_video" in {tool.name for tool in projected.tools}
    assert "design_video" not in {tool.name for tool in projected.tools}
    assert "COMPLETE SKILL METHOD FOR PLANNING" in projected.context


def test_explicit_constraints_use_native_create_parameters(installed_promo):
    from app.agents.tool_loop import ContextSnapshot, tool_spec
    from app.chat.editor_create import CreateVideoArgs
    from app.chat.intent import intent_router
    from app.chat.turn_tools import tools_for_bound_skill
    from app.skills.resolution import get_builtin_skill_option

    skill = get_builtin_skill_option("promo-video").reference
    tools = tools_for_bound_skill(intent_router.tools, skill)
    snapshot = ContextSnapshot("prepared", frozenset({"snapshot:source:digest"}))
    projected = _video_round(tools, snapshot=snapshot, skill=skill, user_text="做 3 幕，总时长 24 秒，画幅 9:16，背景 #A1b2C3")
    create = next(tool for tool in projected.tools if tool.name == "create_video")
    properties = tool_spec(create)["function"]["parameters"]["properties"]
    assert {"shots", "aspect", "background"} <= set(properties)
    assert not {"scene_count", "target_seconds", "design_video"} & set(properties)
    args = CreateVideoArgs.model_validate({
        "name": "Constraint check", "aspect": "9:16", "background": "#A1B2C3",
        "shots": [{"headline": "One", "duration_seconds": 8}, {"headline": "Two", "duration_seconds": 8}, {"headline": "Three", "duration_seconds": 8}],
    })
    assert args.aspect == "9:16" and args.background == "#A1B2C3"
    assert sum(shot.duration_seconds for shot in args.shots) == 24


def test_concurrent_head_keeps_confirmed_actions_but_expires_old_targets_and_preview():
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.intent import intent_router
    from app.chat.prompts import assemble_video_round

    saved = _composition_resource()
    receipt = {"tool": "move_clip", "version": 2, "arguments": {"clip_id": "moved", "time": 3}}
    round = assemble_video_round({
        "tools": intent_router.tools, "user_text": "Move the clip", "mode": "plan",
        "snapshot": ContextSnapshot("head", resources=(("work", saved),)),
        "recent_edit": {"composition_id": saved["composition_id"], "version_id": "old",
                        "clips": {"moved": {"start_seconds": 3}}, "applied": [receipt]},
        "last_preview": {"version_id": "old", "window_seconds": {"start": 3, "end": 4}},
    })
    facts = json.loads(round.context)
    assert facts["already_saved_this_turn"] == [receipt]
    assert facts["selected"] == saved["base_ref"]
    assert "recently_edited_clips" not in facts and "observed_preview" not in facts



def test_revised_playback_request_keeps_prior_export_as_history():
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.intent import intent_router
    from app.chat.prompts import assemble_video_round

    work = _composition_resource()
    previous = {"composition_id": work["composition_id"], "output_id": "previous"}
    result = assemble_video_round({
        "tools": intent_router.tools, "user_text": "调整构图，然后播放这一段给我看。",
        "snapshot": ContextSnapshot("head", resources=(("work", work),)),
        "preceding_delivery": previous,
        "recent_edit": {"composition_id": work["composition_id"], "version_id": work["version_id"],
                        "clips": {}, "applied": [{"tool": "set_keyframe", "version": 2}]},
    })
    context = json.loads(result.context)
    assert context["preceding_reviewed_delivery"] == previous
    assert "revised_delivery" not in context
    assert "does not explicitly request formal export" in context["delivery_scope"]


def test_export_opening_reviews_its_own_output_after_another_edit():
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.intent import intent_router
    from app.chat.prompts import assemble_video_round

    work = _composition_resource()
    exported = {**work["base_ref"], "composition_version_id": "earlier-version", "status": "available",
                "output_id": "the-export", "content_digest": "e" * 64}
    result = assemble_video_round({
        "tools": intent_router.tools, "user_text": "Review and deliver the exported version",
        "snapshot": ContextSnapshot("head", resources=(("work", work),)), "exported": exported,
    })
    facts = json.loads(result.context)
    assert facts["selected"] == work["base_ref"]
    assert facts["exported_this_opening"] == exported
    assert {tool.name for tool in result.tools} == {"review_video", "deliver_video", "answer"}

    # A completed export can resume with the original edit request even when
    # no other opening advanced the head. The edit is already in the MP4.
    exported = {**work["base_ref"], "role": "export", "status": "available", "output_id": "the-export"}
    recovery_facts = {
        "tools": intent_router.tools, "user_text": "Extend the closing still by one second and export",
        "snapshot": ContextSnapshot("head", resources=(("work", work),)), "exported": exported,
        "authorized_media": exported,
        "recent_edit": {"composition_id": work["composition_id"], "version_id": work["version_id"],
                        "clips": {}, "applied": [{"tool": "extend_still", "version": 14}]},
    }
    resumed = assemble_video_round(recovery_facts)
    names = {tool.name for tool in resumed.tools}
    assert "review_video" in names and not {"extend_still", "export_video"} & names
    assert json.loads(resumed.context)["already_saved_this_turn"] == [{"tool": "extend_still", "version": 14}]
    reviewed = assemble_video_round({**recovery_facts, "reviewed_output_id": exported["output_id"]})
    assert {tool.name for tool in reviewed.tools} == {"answer", "deliver_video", "review_video"}



def test_create_rejection_stops_repeated_or_unproductive_attempts():
    from app.agents.tool_loop import ToolRejected
    from app.chat.turn_tools import video_rejection_stop

    first = ToolRejected(kind="params_validation", tool_name="create_video", iteration=0, detail="bad shot", duration_ms=0)
    same = ToolRejected(kind="params_validation", tool_name="create_video", iteration=1, detail="bad shot", duration_ms=0)
    assert video_rejection_stop(first, ()) is False
    assert video_rejection_stop(same, (first,)) is True
    other = ToolRejected(kind="execute_guardrail", tool_name="create_video", iteration=1, detail="other", duration_ms=0)
    third = ToolRejected(kind="execute_guardrail", tool_name="create_video", iteration=2, detail="third", duration_ms=0)
    assert video_rejection_stop(other, (first,)) is False
    assert video_rejection_stop(third, (first, other)) is True
    assert video_rejection_stop(ToolRejected(kind="execute_guardrail", tool_name="split_clip", iteration=0, detail="bad", duration_ms=0), (first, other)) is False
    preview = ToolRejected(kind="execute_guardrail", tool_name="preview_range", iteration=0, detail="generator_preview_failed: registerRoot missing", duration_ms=0)
    assert video_rejection_stop(preview, ()) is False
    assert video_rejection_stop(preview, (preview,)) is True
    pending = ToolRejected(kind="execute_guardrail", tool_name="preview_range", iteration=0,
                           detail="pending_media", duration_ms=0, candidate_digest="same-window")
    animated = ToolRejected(kind="execute_guardrail", tool_name="translate", iteration=1,
                            detail="Keyframes control this property. Its static transform cannot make this edit.",
                            duration_ms=0, candidate_digest="same-transform")
    changed = ToolRejected(kind="execute_guardrail", tool_name="preview_range", iteration=2,
                           detail="pending_media", duration_ms=0, candidate_digest="another-window")
    assert video_rejection_stop(pending, (pending, animated)) is True
    assert video_rejection_stop(animated, (pending, animated, changed)) is True
    assert video_rejection_stop(changed, (pending, animated)) is False


def test_saved_version_offers_materials_and_blocking_clarification():
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.intent import intent_router

    resource = _composition_resource()
    snapshot = ContextSnapshot("saved", resources=(("work", resource),))
    assembly = _video_round(intent_router.tools, snapshot=snapshot, version_saved=True)
    names = {tool.name for tool in assembly.tools}
    assert "create_video" not in names
    assert {"ask_user", "prepare_video_materials", "insert_visual"} <= names
    assert "translate" in names


def test_completed_delivery_does_not_reopen_optional_questionnaire():
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.intent import intent_router
    from app.chat.prompts import assemble_video_round

    resource = _composition_resource()
    assembly = assemble_video_round({
        "tools": intent_router.tools,
        "snapshot": ContextSnapshot("saved", resources=(("work", resource),)),
        "user_text": "把刚才已审阅的 MP4 交付给我，不要再导出。",
        "delivered": {"composition_version_id": resource["version_id"], "delivered_to_chat": True},
    })
    assert "ask_user" not in {tool.name for tool in assembly.tools}


@pytest.mark.asyncio
async def test_observed_version_wire_allows_clarification_without_recreating_work():
    from copy import copy
    from types import SimpleNamespace
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.intent import intent_router
    from app.chat.prompts import assemble_video_round
    from app.providers.llm.base import ToolCall, ToolGeneration

    resource = _composition_resource()
    snapshot = ContextSnapshot("saved", resources=(("work", resource),))

    class Client:
        capabilities = SimpleNamespace(supports_native_tools=True)

        def __init__(self):
            self.wires = []

        async def generate_with_tools(self, **kwargs):
            self.wires.append(kwargs["tools"])
            return ToolGeneration(content="Done", tool_calls=[
                ToolCall(id="finish", name="answer", arguments={"pending_disposition": "none"}),
            ])

    client = Client()
    agent = copy(intent_router)
    agent.client = client

    def assemble(**facts):
        return assemble_video_round({**facts, "snapshot": snapshot, "user_text": "预览当前版本 0–3 秒，不要正式导出。",
                                    "last_preview": {"version_id": resource["version_id"]}})

    async def execute(_name, _params, _speech):
        return None

    result = await agent.call_loop(execute, round_assembler=assemble,
                                  message="预览当前版本 0–3 秒，不要正式导出。")
    assert result.calls == ["answer"]
    assert len(client.wires) == 1
    names = {tool["function"]["name"] for tool in client.wires[0]}
    assert "ask_user" in names and "create_video" not in names


@pytest.mark.asyncio
async def test_failed_observations_stop_across_equivalent_arguments_and_other_reads():
    from copy import copy
    from types import SimpleNamespace
    from app.agents.tool_loop import ChatTool
    from app.chat.intent import intent_router
    from app.chat.turn_tools import video_rejection_stop
    from app.models.schemas import VideoRangeScrubTarget
    from app.providers.llm.base import ToolCall, ToolGeneration

    calls = [
        ToolCall(id="first", name="preview_range", arguments={"start_seconds": 0, "end_seconds": 2}),
        ToolCall(id="other", name="other_read", arguments={"start_seconds": 0, "end_seconds": 2}),
        ToolCall(id="second", name="preview_range", arguments={"kind": "range", "start_seconds": 0, "end_seconds": 2}),
        ToolCall(id="unexpected", name="other_read", arguments={"start_seconds": 0, "end_seconds": 2}),
    ]

    class Client:
        capabilities = SimpleNamespace(supports_native_tools=True)

        def __init__(self):
            self.requests = 0

        async def generate_with_tools(self, **_kwargs):
            result = ToolGeneration(content="", tool_calls=[calls[self.requests]])
            self.requests += 1
            return result

    agent = copy(intent_router)
    agent.client = Client()
    agent.tools = [
        ChatTool(name="preview_range", description="Preview", params_model=VideoRangeScrubTarget, terminal=False),
        ChatTool(name="other_read", description="Read", params_model=VideoRangeScrubTarget, terminal=False),
    ]
    agent.max_iterations = 6

    async def execute(name, _params, _speech):
        from app.agents.tool_loop import ToolObservation

        return ToolObservation("pending_media" if name == "preview_range" else "{}", ok=name != "preview_range")

    result = await agent.call_loop(execute, should_stop_rejection=video_rejection_stop,
                                  message="Preview the saved work")
    assert result.no_progress_tool == "preview_range"
    assert result.iterations == 3
    assert agent.client.requests == 3
    assert [event.tool_name for event in result.rejections] == ["preview_range", "preview_range"]
