"""Deterministic provider tool-call and trace contracts.

No real model, paid production or external HTTP: mocked transports cover wire
fragment assembly, argument parsing, completion boundaries, provider rejections
and the complete local trace/export path.
"""

import json
from types import SimpleNamespace

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
async def test_tool_call_thinking_opt_out_uses_provider_config(monkeypatch):
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
        monkeypatch.setattr(minimax.settings, "llm_trace_path", "")
        llm = minimax.MiniMaxClient(api_key="test", base_url="https://test.invalid")
        await llm.generate_with_tools(messages=[], tools=[], thinking=False)
        await llm.generate_with_tools(messages=[], tools=[])
        await llm.generate_stream_with_tools(messages=[], tools=[], thinking=False)
        await llm.generate_stream_with_tools(messages=[], tools=[])

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
    assert "previous tool call was rejected" in repair_messages
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
                 new_result=False, version_saved=False, draft_finalized=False):
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
        "draft_finalized": draft_finalized,
        "pending_question": pending_question,
        "active_repair": active_repair,
        "mode": mode,
        "iteration": iteration,
        "interim_prose_count": interim_prose_count,
        "new_result": new_result,
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
        snapshot=ContextSnapshot("prepared", frozenset({"project:one", "snapshot:source:digest"})),
        skill=skill, material_pending=True,
    ).tools
    assert "design_video" in {tool.name for tool in prepared}
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
    assert {"revise_video", "get_video_version", "present_plan"} <= saved_names
    assert "design_video" not in saved_names


@pytest.mark.asyncio
async def test_builtin_promo_active_draft_uses_single_scene_writes(installed_promo):
    from uuid import uuid4
    from app.agents.candidate_correction import CandidateRecord, CandidateScope
    from app.agents.tool_loop import ContextSnapshot, tool_spec
    from app.agents.working_drafts import merge_working_draft
    from app.chat.intent import intent_router
    from app.chat.turn_tools import tools_for_bound_skill
    from app.editing.schemas import CompositionContent, VersionSettings
    from app.editing.validators import validate_content
    from app.skills.resolution import get_builtin_skill_option
    from app.tools.video.design import (
        CompositionDesignVideoArgs,
        CompositionSceneAuthoring,
        CompositionScenePlan,
        _expand_scene_authoring,
        _music_bed_write,
        _scene_plan_write,
    )

    skill = get_builtin_skill_option("promo-video").reference
    initial = _video_round(
        tools_for_bound_skill(intent_router.tools, skill),
        snapshot=ContextSnapshot("prepared", frozenset({"snapshot:source:digest"})), skill=skill,
        user_text="Use this exact copy in order",
    )
    initial_design = next(tool for tool in initial.tools if tool.name == "design_video")
    initial_properties = tool_spec(initial_design)["function"]["parameters"]["properties"]
    assert {"scene_plan", "source_ids", "music_snapshot_id", "verbatim_copy"} <= set(initial_properties)
    assert not {"settings", "sources", "scenes", "tracks", "clips", "scene_id"} & set(initial_properties)

    source_id, music_id = uuid4(), uuid4()
    content = _scene_plan_write({
        "schema_version": 1,
        "settings": VersionSettings(width=1920, height=1080).model_dump(mode="json"),
        "sources": [{"snapshot_id": str(source_id), "snapshot_digest": "d" * 64}],
        "scenes": [], "timeline": {"tracks": [], "transitions": []},
    }, [
        CompositionScenePlan(scene_id="first", intent="Show the real product"),
        CompositionScenePlan(scene_id="second", intent="Close on the next step"),
    ])
    draft = CandidateRecord.create(
        tool_name="design_video", arguments={"content": content, "design": {}}, errors=[],
        schema=CompositionDesignVideoArgs.model_json_schema(),
        scope=CandidateScope(owner_id="owner", conversation_id="conversation"),
        base_keys=frozenset(), call_id="call",
    )
    round = _video_round(
        tools_for_bound_skill(intent_router.tools, skill), drafts=(draft,),
        snapshot=ContextSnapshot("draft"), skill=skill,
    )
    design = next(tool for tool in round.tools if tool.name == "design_video")
    assert design.params_model is CompositionDesignVideoArgs
    properties = tool_spec(design)["function"]["parameters"]["properties"]
    assert {"draft_ref", "scene"} <= set(properties)
    assert not {"scenes", "clips", "tracks", "settings", "sources", "scene_id"} & set(properties)
    assert "high-level scene object" in round.system
    assert "DEFAULT SOUNDTRACK" in round.system

    args = CompositionDesignVideoArgs.model_validate({
        "draft_ref": {"draft_id": draft.candidate_id, "draft_digest": draft.candidate_digest},
        "scene": {
            "scene_id": "first",
            "snapshot_id": str(source_id), "view_id": "view-0",
            "source_motion": "hold",
            "headline": "OxValue",
            "supporting_text": "Defensible valuations",
            "text_preset": "title-lockup",
            "narration": "See the evidence behind every valuation.",
            "narration_language": "en",
        },
    })
    merged = merge_working_draft(draft, args)
    assert merged["content"] == content
    assert merged["design"]["authoring"] == "high_level_scene"
    facts = {
        source_id: {
            "kind": "web", "digest": "d" * 64, "storage_key": "web.json",
            "meta": {"views": [{
                "view_id": "view-0", "storage_key": "view.png", "digest": "v" * 64,
                "width": 1440, "height": 900, "elements": [],
            }]},
        },
        music_id: {
            "kind": "audio", "digest": "a" * 64, "storage_key": "music.mp3",
            "duration_ticks": 900000, "meta": {},
        },
    }
    expanded = await _expand_scene_authoring(merged["content"], args.scene, facts)
    expanded = _music_bed_write(expanded, music_id, facts)
    expanded = _music_bed_write(expanded, str(music_id), facts)
    assert sum(binding["snapshot_id"] == str(music_id) for binding in expanded["sources"]) == 1
    assert sum(track["track_id"] == "trk_music" for track in expanded["timeline"]["tracks"]) == 1
    candidate = CompositionContent.model_validate(expanded)
    validate_content(candidate, facts)
    assert candidate.scenes[1].range.start == candidate.scenes[0].range.end
    source_clips = [clip for track in candidate.timeline.tracks for clip in track.clips
                    if clip.object.kind == "web"]
    assert len(source_clips) == 1
    assert source_clips[0].source.snapshot_digest == "d" * 64
    texts = [clip.object.text for track in candidate.timeline.tracks for clip in track.clips
             if clip.object.kind == "text"]
    assert texts == ["OxValue", "Defensible valuations"]
    speech = [clip for track in candidate.timeline.tracks for clip in track.clips
              if clip.object.kind == "speech"]
    assert len(speech) == 1
    assert speech[0].object.text == "See the evidence behind every valuation."
    assert speech[0].object.language == "en"
    assert speech[0].object.voice_id == "presenter_male"
    assert speech[0].clip_id in candidate.scenes[0].speech_clip_ids
    music = next(track for track in candidate.timeline.tracks if track.track_id == "trk_music")
    assert music.clips and all(clip.scene_id is None for clip in music.clips)
    from app.editing.service import format_storyboard_text
    from app.editing.storyboard import storyboard_payload

    presentation = storyboard_payload(
        candidate, composition_id=uuid4(), version_id=uuid4(), version=1, content_digest="c" * 64,
    )
    assert presentation["scenes"][0]["narration"] == "See the evidence behind every valuation."
    read = {**presentation, "composition_name": "Promo", "base_ref": {}, "storyboard": presentation}
    assert f"Music: {len(music.clips)} saved Clip(s) in this version." in format_storyboard_text(read)
    assert "Narration: reviewed SpeechObjects" in format_storyboard_text(read)


def test_scene_plan_and_explicit_count_have_no_six_scene_cap():
    from app.skills.external import SkillPolicy
    from app.tools.video.design import CompositionDesignVideoArgs, CompositionScenePlan

    scenes = [CompositionScenePlan(scene_id=f"scene-{index}", intent=f"Beat {index}") for index in range(7)]
    args = CompositionDesignVideoArgs.model_validate({"scene_plan": scenes, "scene_count": 7})
    assert len(args.scene_plan) == 7
    assert args.scene_count == 7
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


@pytest.mark.asyncio
async def test_high_level_scene_verbatim_copy_fails_while_current_scene_is_retryable():
    from app.agents.working_drafts import working_draft_diagnostic
    from app.editing.schemas import VersionSettings
    from app.tools.video.design import (
        CandidateDesignError,
        CompositionDesignVideoArgs,
        CompositionSceneAuthoring,
        CompositionScenePlan,
        _expand_scene_authoring,
        _scene_plan_write,
        _validate_scene_verbatim_copy,
    )

    content = _scene_plan_write({
        "schema_version": 1,
        "settings": VersionSettings(width=1920, height=1080).model_dump(mode="json"),
        "sources": [], "scenes": [], "timeline": {"tracks": [], "transitions": []},
    }, [
        CompositionScenePlan(scene_id="first", intent="Introduce the product"),
        CompositionScenePlan(scene_id="second", intent="Close"),
    ])
    args = CompositionDesignVideoArgs(verbatim_copy=[
        "OxValue", "Intelligence, with accountability", "Close",
    ])
    invalid = await _expand_scene_authoring(content, CompositionSceneAuthoring(
        scene_id="first", headline="OxValue",
        supporting_text="INTELLIGENCE, WITH ACCOUNTABILITY",
    ), {})
    with pytest.raises(CandidateDesignError) as rejected:
        _validate_scene_verbatim_copy(args=args, composition=invalid)
    issue = rejected.value.issues[0]
    assert issue["actual"] == ["OxValue", "INTELLIGENCE, WITH ACCOUNTABILITY"]
    diagnostic = working_draft_diagnostic(SimpleNamespace(
        candidate_id="cnd_copy", candidate_digest="d" * 64, errors=[issue],
    ))
    assert diagnostic["errors"][0]["expected"] == args.verbatim_copy
    assert diagnostic["errors"][0]["actual"] == issue["actual"]

    first = await _expand_scene_authoring(content, CompositionSceneAuthoring(
        scene_id="first", headline="OxValue",
        supporting_text="Intelligence, with accountability",
    ), {})
    _validate_scene_verbatim_copy(args=args, composition=first)
    second = await _expand_scene_authoring(first, CompositionSceneAuthoring(
        scene_id="second", headline="Wrong close",
    ), {})
    with pytest.raises(CandidateDesignError) as rejected_last:
        _validate_scene_verbatim_copy(args=args, composition=second)
    assert rejected_last.value.issues[0]["actual"][-1] == "Wrong close"
    valid = await _expand_scene_authoring(first, CompositionSceneAuthoring(
        scene_id="second", headline="Close",
    ), {})
    _validate_scene_verbatim_copy(args=args, composition=valid)


def test_legacy_expanded_draft_recovers_through_save_only_protocol():
    from app.agents.candidate_correction import CandidateRecord, CandidateScope
    from app.agents.tool_loop import ContextSnapshot, tool_spec
    from app.agents.working_drafts import merge_working_draft
    from app.chat.intent import intent_router
    from app.chat.turn_tools import resolve_video_stage, video_round_tools
    from app.tools.video.design import CompositionDesignVideoArgs

    content = {
        "scenes": [{
            "scene_id": "lead", "range": {"start": 0, "end": 90000},
            "intent": "Lead", "speech_clip_ids": [],
        }],
        "sources": [],
        "timeline": {"tracks": [{
            "track_id": "trk_title", "kind": "visual", "role": "title", "order": 0,
            "clips": [{"clip_id": "clp_lead", "scene_id": "lead", "range": {"start": 0, "end": 90000}}],
        }], "transitions": []},
    }
    record = CandidateRecord.create(
        tool_name="design_video",
        arguments={
            "content": content,
            "design": {"arc_id": "product-evidence", "shots": [{"shot": "brand-emergence"}]},
        },
        errors=[],
        schema=CompositionDesignVideoArgs.model_json_schema(),
        scope=CandidateScope(owner_id="owner", conversation_id="conversation"),
        base_keys=frozenset(), call_id="legacy-call",
    )
    args = CompositionDesignVideoArgs.model_validate({
        "save": True,
        "draft_ref": {"draft_id": record.candidate_id, "draft_digest": record.candidate_digest},
    })
    merged = merge_working_draft(record, args)
    assert merged["content"] == content
    resolution = resolve_video_stage(
        tools=intent_router.tools, drafts=(record,),
        snapshot=ContextSnapshot("legacy", frozenset()), user_text="Save that draft",
    )
    assert resolution["stage"] == "draft_finalize"
    projected = video_round_tools(
        intent_router.tools, resolution=resolution,
        snapshot=ContextSnapshot("legacy", frozenset()),
    )
    design = next(tool for tool in projected if tool.name == "design_video")
    properties = tool_spec(design)["function"]["parameters"]["properties"]
    assert "draft_ref" in properties and "save" in properties
    assert not {"shots", "tracks", "clips", "scene", "scene_plan"} & set(properties)


def test_chat_tool_loops_allow_twenty_bounded_iterations():
    from app.chat.intent import chat_intent_agent, intent_router

    assert intent_router.max_iterations == 20
    assert chat_intent_agent.max_iterations == 20


def test_video_modes_use_the_shared_pending_question_rule():
    from app.agents.base import jinja_env
    from app.chat.intent import chat_intent_agent, intent_router
    from app.chat.prompts import chat_system

    plan = chat_system("plan", available_tools=intent_router.tools)
    conversation = chat_system("conversation", available_tools=chat_intent_agent.tools)
    assert plan.count("PENDING QUESTION:") == 1
    assert conversation.count("PENDING QUESTION:") == 1
    assert plan.count("SPEECH LANGUAGE:") == 1
    assert conversation.count("SPEECH LANGUAGE:") == 1
    assert "pending_disposition" in plan and "pending_disposition" in conversation

    video = chat_system(
        "plan", available_tools=intent_router.tools,
        video_stage="draft_build", video_speech="opening", scene_authoring=True,
    )
    assert video.count("SPEECH LANGUAGE:") == 1
    ordered_rules = (
        "SPEECH LANGUAGE:", "READ TOOLS:", "REJECTIONS:", "Video works",
        "- answer:", "- ask_user:", "PENDING QUESTION:",
    )
    assert [video.index(rule) for rule in ordered_rules] == sorted(
        video.index(rule) for rule in ordered_rules
    )

    opening = jinja_env.get_template("chat/user.j2").render(
        mode="plan", recent=["- user: earlier"], message="latest answer",
        asset_lines=["- page (web_page)"], understanding_lines=["- Summary: evidence"],
        persona_lines=["- tone: rational"], brief_lines=["- target_seconds: 30 (user-stated)"],
        confirmation_line="Confirmation settings: execution=auto, spending=auto.",
        pending_lines=["- question: specs?"],
    )
    opening_order = (
        "Recent conversation:", "Uploaded files", "The system's read", "The user's persona",
        "The brief so far", "Confirmation settings:", "A question of yours", "User message:",
    )
    assert [opening.index(block) for block in opening_order] == sorted(
        opening.index(block) for block in opening_order
    )


def test_missing_package_session_keeps_generic_high_level_protocol(installed_promo):
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
    design = next(tool for tool in projected.tools if tool.name == "design_video")
    properties = tool_spec(design)["function"]["parameters"]["properties"]
    assert "scene_plan" in properties and "tracks" not in properties
    assert "high-level scene object" in projected.system


def test_video_round_resolves_draft_review_saved_edit_ambiguity_and_repair():
    from types import SimpleNamespace
    from app.agents.candidate_correction import CandidateRecord, CandidateScope, correction_tool
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.intent import intent_router
    from app.tools.video.design import CompositionDesignVideoArgs

    draft = CandidateRecord.create(
        tool_name="design_video",
        arguments={"content": {
            "scenes": [{"scene_id": "first", "range": {"start": 0, "end": 90000}}],
            "timeline": {"tracks": []}, "sources": [{"snapshot_id": "frozen-web"}],
        }, "design": {}},
        errors=[], schema=CompositionDesignVideoArgs.model_json_schema(),
        scope=CandidateScope(owner_id="owner", conversation_id="conversation"),
        base_keys=frozenset(), call_id="call",
    )
    review = _video_round(intent_router.tools, drafts=(draft,), snapshot=ContextSnapshot("draft"))
    assert review.stage == "draft_build"
    assert {"design_video", "review_working_draft", "ask_user", "answer"} <= {
        tool.name for tool in review.tools
    }
    assert "Default to saving and presenting the storyboard" in review.system
    sequential = _video_round(
        intent_router.tools, drafts=(draft,), snapshot=ContextSnapshot("draft"),
        user_text="请按播放顺序审查当前工作草稿。",
    )
    assert sequential.stage == "draft_review"
    assert "design_video" not in {tool.name for tool in sequential.tools}
    negated = _video_round(
        intent_router.tools, drafts=(draft,), snapshot=ContextSnapshot("draft"),
        user_text="不要按播放顺序检查，直接保存草稿。",
    )
    assert negated.stage == "draft_build"
    from app.agents.tool_loop import tool_spec
    from app.agents.working_drafts import record_working_draft_review

    review_tool = next(tool for tool in review.tools if tool.name == "review_working_draft")
    assert "judgment" not in tool_spec(review_tool)["function"]["parameters"]["properties"]
    with_evidence = draft.updated(record_working_draft_review(draft.arguments, {
        "content_digest": "c" * 64,
        "scope": {"source_range_seconds": {"start": 0.0, "end": 1.0}, "scene_ids": ["first"], "clip_ids": []},
        "observation": {"media_digest": "e" * 64},
    }), [], call_id="review")
    web_snapshot = ContextSnapshot("draft", resources=((
        "snapshot:frozen-web:digest",
        {"kind": "web", "snapshot_id": "frozen-web", "citable_lines": [{"text": "frozen source page only"}]},
    ),))
    judging = _video_round(intent_router.tools, drafts=(with_evidence,), snapshot=web_snapshot)
    assert judging.stage == "draft_review"
    assert {tool.name for tool in judging.tools} == {"review_working_draft", "ask_user", "answer"}
    judging_tool = next(tool for tool in judging.tools if tool.name == "review_working_draft")
    assert "judgment" in tool_spec(judging_tool)["function"]["parameters"]["required"]
    assert "frozen source page only" not in judging.context
    assert "editable_targets" not in judging.context
    assert judging.include_observation_media

    saved = _composition_resource()
    snapshot = ContextSnapshot(
        "complete project and an unrelated asset", frozenset({"composition:ver-one:digest"}),
        resources=(("composition:ver-one:digest", saved),),
    )
    edited = _video_round(
        intent_router.tools, drafts=(draft,), snapshot=snapshot,
        user_text="Change the second Scene title",
    )
    assert edited.stage == "version_edit"
    assert "revise_video" in {tool.name for tool in edited.tools}
    assert not {"design_video", "review_working_draft"} & {tool.name for tool in edited.tools}
    assert "complete project and an unrelated asset" not in edited.context
    assert "title-second" in edited.context
    assert edited.include_observation_media is False
    assert "TARGETED REVISION: edit only" in edited.system
    presenting = _video_round(intent_router.tools, snapshot=snapshot, version_saved=True, draft_finalized=True)
    assert presenting.stage == "draft_present"
    assert {tool.name for tool in presenting.tools} == {"answer"}

    other = _composition_resource(suffix="two")
    ambiguous = _video_round(
        intent_router.tools,
        snapshot=ContextSnapshot("two", resources=(("one", saved), ("two", other))),
    )
    assert ambiguous.stage == "resolve_target"
    assert {tool.name for tool in ambiguous.tools} == {
        "ask_user", "answer", "get_video_version",
    }

    repaired = _video_round(
        [correction_tool()], snapshot=snapshot, active_repair=SimpleNamespace(tool_name="design_video"),
    )
    assert [tool.name for tool in repaired.tools] == ["correct_tool_candidate"]
    assert "pending_question" not in repaired.context
    assert "CURRENT PROJECT EVIDENCE" not in repaired.context


@pytest.mark.parametrize("mode", ["plan", "conversation"])
@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.asyncio
async def test_final_video_provider_request_clears_pending_and_historical_media(
    monkeypatch, mode, streaming,
):
    from app.agents import tool_loop
    from app.chat.intent import chat_intent_agent, intent_router
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
                    id="revise-1", name="revise_video",
                    arguments={"ops": [{"op": "remove_clip", "clip_id": "title-second"}], "pending_disposition": "answer"},
                )])
            return ToolGeneration("Saved", [ToolCall(id="answer-1", name="answer", arguments={})])

    class Template:
        def render(self, **_kwargs):
            return "current user request"

    class Environment:
        def get_template(self, _name):
            return Template()

    monkeypatch.setattr(tool_loop, "jinja_env", Environment())
    source = intent_router if mode == "plan" else chat_intent_agent
    agent = tool_loop.ToolLoopAgent(
        name=f"video-round-{mode}-{streaming}", prompt="unused.j2", system="test",
        assemble=lambda **_kwargs: ({}, None), tools=source.tools, client=Client(),
    )

    async def restore(_snapshot, _messages):
        return tool_loop.ConversationHistory(messages=(historical,))

    async def execute(name, _params, _speech):
        nonlocal pending
        if name == "revise_video":
            pending = None
            return tool_loop.ToolObservation("saved")
        return None

    def assemble(**facts):
        from app.chat.prompts import assemble_video_round

        return assemble_video_round({
            **facts, "mode": mode, "user_text": "Use the answered title",
            "pending_question": lambda: pending,
        })

    result = await agent.call_loop(
        execute, refresh_context=lambda: _immediate(snapshot), restore_context=restore,
        round_assembler=assemble, on_delta=(lambda _text: _immediate(None)) if streaming else None,
    )
    assert result.tool_name == "answer"
    assert len(calls) == 2
    first, second = calls
    first_text = json.dumps(first["messages"], ensure_ascii=False)
    second_text = json.dumps(second["messages"], ensure_ascii=False)
    assert "Which title?" in first_text
    assert "Which title?" not in second_text
    assert "old review" in second_text and "Historical observation old" not in second_text
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


def test_explicit_title_edit_only_projects_current_title_and_its_write():
    from pydantic import ValidationError

    from app.agents.tool_loop import ContextSnapshot
    from app.chat.intent import intent_router

    saved = _composition_resource()
    saved["scenes"] = [
        {"scene_id": "second", "range": {"start": 20}},
        {"scene_id": "first", "range": {"start": 0}},
    ]
    saved["clip_targets"] = [
        {"clip_id": "other", "scene_id": "first", "object_kind": "text", "text": "unrelated"},
        {"clip_id": "title-second", "scene_id": "second", "object_kind": "text", "text": "Old title"},
        {"clip_id": "captions", "scene_id": "second", "object_kind": "text", "derived_caption": True},
    ]
    snapshot = ContextSnapshot("large project snapshot", resources=(("composition", saved),))
    request = "把刚才保存作品的第二幕标题改为“Value / Defend”。只改这个标题，不要重新审片，不要制作或渲染正式视频。"
    edit = _video_round(intent_router.tools, snapshot=snapshot, user_text=request)
    assert edit.opening_text == request
    assert not edit.include_project_context
    assert "Old title" in edit.context
    assert "unrelated" not in edit.context and "captions" not in edit.context
    assert {tool.name for tool in edit.tools} == {"revise_video", "answer"}
    revision = next(tool.params_model for tool in edit.tools if tool.name == "revise_video")
    valid = {"base_ref": saved["base_ref"], "clip_id": "title-second", "text": "Value / Defend"}
    assert revision.model_validate(valid).clip_id == "title-second"
    with pytest.raises(ValidationError):
        revision.model_validate({**valid, "clip_id": "other"})
    with pytest.raises(ValidationError):
        revision.model_validate({**valid, "base_ref": {**saved["base_ref"], "content_digest": "a" * 64}})
    after_save = _video_round(intent_router.tools, snapshot=snapshot, user_text=request, version_saved=True)
    assert {tool.name for tool in after_save.tools} == {"answer"}

    compound = _video_round(intent_router.tools, snapshot=snapshot, user_text=request + "再加一段音乐。")
    assert compound.opening_text is None
    assert "search_music" in {tool.name for tool in compound.tools}
    saved["clip_targets"].append(
        {"clip_id": "another", "scene_id": "second", "object_kind": "text", "text": "Another title"}
    )
    ambiguous = _video_round(intent_router.tools, snapshot=snapshot, user_text=request)
    assert {tool.name for tool in ambiguous.tools} == {"ask_user"}


def test_video_rounds_allow_service_text_for_reads_and_edits():
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.intent import intent_router

    for iteration in (0, 1, 6):
        projected = _video_round(intent_router.tools, snapshot=ContextSnapshot("empty"), iteration=iteration)
        assert projected.allow_interim_prose
        assert "speech_rule" not in projected.context

    saved = _composition_resource()
    edit = _video_round(
        intent_router.tools,
        snapshot=ContextSnapshot(
            "saved", resources=(("composition", saved),),
        ),
        user_text="Change the title", iteration=0, new_result=True,
    )
    assert edit.stage == "version_edit"
    assert edit.allow_interim_prose


def test_draft_repair_focus_schema_uses_real_clip_and_element_ids():
    from app.agents.candidate_correction import CandidateRecord, CandidateScope
    from app.agents.tool_loop import ContextSnapshot, tool_spec
    from app.chat.intent import intent_router
    from app.tools.video.design import CompositionDesignVideoArgs

    content = {
        "settings": {"timebase": 90000},
        "scenes": [{"scene_id": "review", "range": {"start": 0, "end": 90000}}],
        "timeline": {"tracks": [{
            "track_id": "main", "clips": [{
                "clip_id": "clp_review_web", "scene_id": "review", "range": {"start": 0, "end": 90000},
                "object": {"kind": "web", "view_id": "view-3"},
                "source": {"snapshot_id": "source-3"},
            }],
        }]},
    }
    draft = CandidateRecord.create(
        tool_name="design_video", arguments={"content": content, "design": {}},
        errors=[{"msg": "bad framing"}], schema=CompositionDesignVideoArgs.model_json_schema(),
        scope=CandidateScope(owner_id="owner", conversation_id="conversation"),
        base_keys=frozenset(), call_id="call",
    )
    source = {
        "kind": "web", "snapshot_id": "source-3",
        "views": [{"view_id": "view-3", "targets": [{"id": "s3e10"}, {"id": "s3e11"}]}],
    }
    round = _video_round(
        intent_router.tools, drafts=(draft,),
        snapshot=ContextSnapshot("source", resources=(("snapshot:source-3", source),)),
    )
    design = next(tool for tool in round.tools if tool.name == "design_video")
    properties = tool_spec(design)["function"]["parameters"]["properties"]
    assert set(properties) == {"draft_ref", "focus_clip_id", "focus_element_id", "pending_disposition"}
    assert properties["focus_clip_id"]["enum"] == ["clp_review_web"]
    assert properties["focus_element_id"]["enum"] == ["s3e10", "s3e11"]
    assert {"focus_clip_id", "focus_element_id"} <= set(
        tool_spec(design)["function"]["parameters"]["required"]
    )
    assert '"element_ids": ["s3e10", "s3e11"]' in round.context


@pytest.mark.asyncio
async def test_review_result_identity_survives_stale_history_restore(monkeypatch):
    from app.agents import tool_loop
    from app.agents.candidate_correction import CandidateRecord, CandidateScope, RestoredCandidate
    from app.agents.working_drafts import WorkingDraftReviewed, record_working_draft_judgment, record_working_draft_review
    from app.chat.intent import intent_router
    from app.models.schemas import canonical_json_hash
    from app.providers.llm.base import ProviderCapabilities, ToolGeneration
    from app.tools.video.design import CompositionDesignVideoArgs
    from app.tools.video.preview import WorkingDraftReviewJudgment

    content = {
        "settings": {"timebase": 90000},
        "scenes": [
            {"scene_id": "input", "range": {"start": 0, "end": 360000}},
            {"scene_id": "review", "range": {"start": 360000, "end": 720000}},
        ],
        "timeline": {"tracks": []},
    }
    initial = CandidateRecord.create(
        tool_name="design_video", arguments={"content": content, "design": {}}, errors=[],
        schema=CompositionDesignVideoArgs.model_json_schema(),
        scope=CandidateScope(owner_id="owner", conversation_id="conversation"),
        base_keys=frozenset(), call_id="fixture",
    )
    evidence = {
        "content_digest": canonical_json_hash(content),
        "scope": {"source_range_seconds": {"start": 0.0, "end": 4.0}, "scene_ids": ["input"], "clip_ids": []},
        "observation": {"media_digest": "e" * 64},
    }
    reviewed_arguments = record_working_draft_review(initial.arguments, evidence)
    evidence_id = reviewed_arguments["review"]["reviews"][-1]["evidence_id"]
    requests = []

    class Client:
        capabilities = ProviderCapabilities(supports_native_tools=True)

        async def generate_with_tools(self, **kwargs):
            requests.append(kwargs)
            count = len(requests)
            if count == 1:
                return ToolGeneration("", [ToolCall(id="preview", name="review_working_draft", arguments={
                    "draft_ref": {"draft_id": initial.candidate_id, "draft_digest": initial.candidate_digest},
                })])
            if count == 2:
                current = initial.updated(reviewed_arguments, [], call_id="preview")
                return ToolGeneration("", [ToolCall(id="judge", name="review_working_draft", arguments={
                    "draft_ref": {"draft_id": current.candidate_id, "draft_digest": current.candidate_digest},
                    "judgment": {"evidence_id": evidence_id, "verdict": "pass", "summary": "Scene 1 passes"},
                })])
            return ToolGeneration("done", [ToolCall(id="answer", name="answer", arguments={})])

    class Template:
        def render(self, **_kwargs):
            return "review"

    class Environment:
        def get_template(self, _name):
            return Template()

    monkeypatch.setattr(tool_loop, "jinja_env", Environment())
    agent = tool_loop.ToolLoopAgent(
        name="review-current-draft-restore", prompt="unused.j2", system="test",
        assemble=lambda **_kwargs: ({}, None), tools=intent_router.tools, client=Client(),
    )

    async def restore(_snapshot, _messages):
        return tool_loop.ConversationHistory(candidates=(RestoredCandidate(
            candidate_id=initial.candidate_id, candidate_digest=initial.candidate_digest,
            tool_name=initial.tool_name, arguments=initial.arguments, errors=[], base_keys=frozenset(), call_id="fixture",
        ),))

    async def execute(name, params, _speech):
        if name == "answer":
            return None
        if params.judgment is None:
            return WorkingDraftReviewed(reviewed_arguments, tool_loop.ToolObservation(
                json.dumps({"evidence_id": evidence_id}), context_lifetime="call",
            ))
        judged = record_working_draft_judgment(params._working_draft, WorkingDraftReviewJudgment(
            evidence_id=evidence_id, verdict="pass", summary="Scene 1 passes",
        ))
        return WorkingDraftReviewed(judged, tool_loop.ToolObservation(
            json.dumps({"judgment": "accepted"}), context_lifetime="call",
        ))

    def assemble(**facts):
        from app.chat.prompts import assemble_video_round

        return assemble_video_round({**facts, "mode": "plan", "user_text": "Review both Scenes"})

    result = await agent.call_loop(
        execute, refresh_context=lambda: _immediate(tool_loop.ContextSnapshot("")),
        restore_context=restore, round_assembler=assemble, candidate_scope=initial.scope,
    )
    assert result.tool_name == "answer"
    assert len(requests) == 3
    final_text = json.dumps(requests[-1]["messages"], ensure_ascii=False)
    final_fact = json.loads(next(
        message["content"].split("\n", 1)[1]
        for message in requests[-1]["messages"]
        if isinstance(message.get("content"), str) and "CURRENT VIDEO ROUND" in message["content"]
    ))
    assert final_fact["draft"]["unjudged_evidence_ids"] == []
    assert final_fact["draft"]["next_review_target"]["scene_id"] == "review"


@pytest.mark.asyncio
async def test_accepted_issue_summary_is_interim_once_before_repair(monkeypatch):
    from app.agents import tool_loop
    from app.agents.candidate_correction import CandidateRecord, CandidateScope, RestoredCandidate
    from app.agents.working_drafts import WorkingDraftUpdated, record_working_draft_review
    from app.chat.intent import intent_router
    from app.chat.video_turn_seats import review_working_draft_seat
    from app.models.schemas import canonical_json_hash
    from app.providers.llm.base import ProviderCapabilities, ToolGeneration
    from app.tools.video.design import CompositionDesignVideoArgs
    from app.tools.video.preview import ReviewWorkingDraftArgs, WorkingDraftReviewJudgment

    content = {"settings": {"timebase": 90000}, "scenes": [{"scene_id": "review", "range": {"start": 0, "end": 90000}}], "timeline": {"tracks": []}}
    arguments = record_working_draft_review({"content": content, "design": {}}, {
        "content_digest": canonical_json_hash(content),
        "scope": {"source_range_seconds": {"start": 0.0, "end": 1.0}, "scene_ids": ["review"], "clip_ids": []},
        "observation": {"media_digest": "e" * 64},
    })
    record = CandidateRecord.create(
        tool_name="design_video", arguments=arguments, errors=[],
        schema=CompositionDesignVideoArgs.model_json_schema(),
        scope=CandidateScope(owner_id="owner", conversation_id="conversation"),
        base_keys=frozenset(), call_id="fixture",
    )
    judgment = WorkingDraftReviewJudgment(
        evidence_id=arguments["review"]["reviews"][-1]["evidence_id"],
        verdict="issue", summary="Value / Defend are not visible",
    )
    accepted_args = ReviewWorkingDraftArgs(
        draft_ref={"draft_id": record.candidate_id, "draft_digest": record.candidate_digest},
        judgment=judgment,
    )
    accepted_args.bind_working_draft(record.arguments)
    accepted = await review_working_draft_seat(project=None, args=accepted_args)
    assert accepted.observation.accepted_interim_prose == judgment.summary
    events = []
    requests = []

    class Client:
        capabilities = ProviderCapabilities(supports_native_tools=True)

        async def generate_with_tools(self, **kwargs):
            requests.append(kwargs)
            if len(requests) == 1:
                return ToolGeneration("The second scene has a framing issue.", [ToolCall(id="judge", name="review_working_draft", arguments={
                    "draft_ref": {"draft_id": record.candidate_id, "draft_digest": record.candidate_digest},
                    "judgment": judgment.model_dump(mode="json"),
                })])
            if len(requests) == 2:
                current = record.updated(accepted.arguments, [], call_id="judge")
                return ToolGeneration("I'll apply the repair now.", [ToolCall(id="repair", name="design_video", arguments={
                    "draft_ref": {"draft_id": current.candidate_id, "draft_digest": current.candidate_digest},
                    "save": False,
                })])
            return ToolGeneration("done", [ToolCall(id="answer", name="answer", arguments={})])

    class Template:
        def render(self, **_kwargs):
            return "review"

    class Environment:
        def get_template(self, _name):
            return Template()

    monkeypatch.setattr(tool_loop, "jinja_env", Environment())
    agent = tool_loop.ToolLoopAgent(
        name="accepted-issue-interim", service_per_call=True, prompt="unused.j2", system="test",
        assemble=lambda **_kwargs: ({}, None), tools=intent_router.tools, client=Client(),
    )

    async def restore(_snapshot, _messages):
        return tool_loop.ConversationHistory(candidates=(RestoredCandidate(
            candidate_id=record.candidate_id, candidate_digest=record.candidate_digest,
            tool_name=record.tool_name, arguments=record.arguments, errors=[], base_keys=frozenset(), call_id="fixture",
        ),))

    async def execute(name, params, _speech):
        if name == "review_working_draft":
            events.append("review_execute")
            return await review_working_draft_seat(project=None, args=params)
        if name == "design_video":
            events.append("repair_execute")
            return WorkingDraftUpdated(params._working_draft)
        return None

    async def on_interim(text):
        events.append(f"interim:{text}")

    async def on_event(event):
        if isinstance(event, tool_loop.ReadAccepted):
            events.append("accepted")

    def assemble(**facts):
        from app.chat.prompts import assemble_video_round

        return assemble_video_round({**facts, "mode": "plan", "user_text": "Review and repair"})

    result = await agent.call_loop(
        execute, refresh_context=lambda: _immediate(tool_loop.ContextSnapshot("")),
        restore_context=restore, round_assembler=assemble, candidate_scope=record.scope,
        on_interim_prose=on_interim, on_loop_event=on_event,
    )
    assert result.tool_name == "answer"
    assert events == [
        "interim:The second scene has a framing issue.", "review_execute", "accepted",
        "interim:I'll apply the repair now.", "repair_execute", "accepted",
    ]

    passing_args = ReviewWorkingDraftArgs(
        draft_ref={"draft_id": record.candidate_id, "draft_digest": record.candidate_digest},
        judgment=WorkingDraftReviewJudgment(
            evidence_id=judgment.evidence_id, verdict="pass", summary="ordinary pass",
        ),
    )
    passing_args.bind_working_draft(record.arguments)
    passing = await review_working_draft_seat(project=None, args=passing_args)
    assert passing.observation.accepted_interim_prose is None


def test_copy_only_draft_hold_projects_skill_receipt_without_media():
    from app.agents.candidate_correction import CandidateRecord, CandidateScope
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.intent import intent_router
    from app.tools.video.design import CompositionDesignVideoArgs

    content = {
        "scenes": [{
            "scene_id": "lead", "range": {"start": 0, "end": 90000},
            "intent": "Lead", "speech_clip_ids": [],
        }],
        "sources": [],
        "timeline": {"tracks": [{
            "track_id": "trk_title", "kind": "visual", "role": "title", "order": 0,
            "clips": [{"clip_id": "clp_lead", "scene_id": "lead", "range": {"start": 0, "end": 90000}}],
        }], "transitions": []},
    }
    draft = CandidateRecord.create(
        tool_name="design_video", arguments={"content": content, "design": {}}, errors=[],
        schema=CompositionDesignVideoArgs.model_json_schema(),
        scope=CandidateScope(owner_id="owner", conversation_id="conversation"),
        base_keys=frozenset(), call_id="call",
    )
    receipt = {
        "kind": "skill_read_receipt", "package_identity": "promo@1",
        "skill_reference": {"kind": "builtin", "skill_id": "promo-video", "version": "1.0.0"},
        "reads": [{"path": "references/sequences/message-first-spotlight.md", "digest": "a" * 64}],
        "preview_checks": [], "media_files_actually_read": 1, "receipt_contains_media": False,
    }
    snapshot = ContextSnapshot(
        "draft", frozenset(), resources=(("skill-read:promo@1", receipt),),
    )
    round = _video_round(
        intent_router.tools, drafts=(draft,), snapshot=snapshot,
        user_text="Only clarify the draft; do not save it.",
    )
    assert round.stage == "draft_hold"
    assert "a" * 64 in round.context and "receipt_contains_media" in round.context
    assert round.include_observation_media is False
    assert {tool.name for tool in round.tools} == {"answer"}


@pytest.mark.asyncio
async def test_high_level_provider_requests_fold_prior_scene_writes_and_projections(monkeypatch):
    from copy import deepcopy
    from types import SimpleNamespace

    from app.agents import tool_loop
    from app.agents.candidate_correction import CandidateScope
    from app.agents.working_drafts import WorkingDraftUpdated
    from app.chat.conversation_context import conversation_context_tool
    from app.chat.intent import intent_router
    from app.chat.turn_tools import tools_for_bound_skill
    from app.providers.llm.base import ProviderCapabilities, ToolGeneration
    from app.tools.video.design import _scene_plan_write

    source_id = "23003fb4-a081-5abe-a979-d5fca44c0294"
    source_key = f"snapshot:{source_id}:{'s' * 64}"
    source = {
        "kind": "web", "snapshot_id": source_id, "digest": "s" * 64,
        "citable_lines": [{"line_id": "line-1", "text": "VERBATIM SOURCE ONLY NEEDED FOR PLANNING"}],
        "views": [{
            "view_id": "hero", "heading": "Real product view", "width": 1440, "height": 900,
            "targets": [{"id": "value-card", "kind": "text", "text": "Value / Defend"}],
        }],
    }
    snapshot = tool_loop.ContextSnapshot(
        "FULL UNRELATED PROJECT CATALOG\n" + json.dumps(source, ensure_ascii=False),
        frozenset({source_key}), resources=((source_key, source),),
        skill_method="COMPLETE SKILL METHOD FOR PLANNING",
    )
    skill = SimpleNamespace(skill_id="promo-video")
    tools = [*tools_for_bound_skill(intent_router.tools, skill), conversation_context_tool()]
    requests = []
    scope = CandidateScope(owner_id="owner", conversation_id="conversation")

    class Client:
        capabilities = ProviderCapabilities(supports_native_tools=True)

        async def generate_with_tools(self, **kwargs):
            requests.append(kwargs)
            count = len(requests)
            if count == 1:
                return ToolGeneration("", [
                    ToolCall(id="music-search", name="search_music", arguments={}),
                    ToolCall(id="skill-read", name="read_skill_reference", arguments={"path": "shot.md"}),
                ])
            current = next(
                message["content"] for message in reversed(requests[-1]["messages"])
                if isinstance(message.get("content"), str) and "CURRENT VIDEO ROUND" in message["content"]
            )
            facts = json.loads(current.rsplit("\n", 1)[-1])
            if count == 2:
                return ToolGeneration("", [ToolCall(id="plan", name="design_video", arguments={
                    "name": "Real source promo",
                    "scene_plan": [
                        {"scene_id": "first", "intent": "Establish the actual product"},
                        {"scene_id": "second", "intent": "Show Value / Defend in the current product"},
                    ],
                    "source_ids": [source_id],
                })])
            if count in {3, 4}:
                scene_id = facts["next_unfilled_scene"]["scene_id"]
                return ToolGeneration("", [ToolCall(id=f"scene-{count}", name="design_video", arguments={
                    "draft_ref": facts["draft_ref"],
                    "scene": {"scene_id": scene_id, "headline": f"Exact headline {scene_id}"},
                })])
            if count == 5:
                return ToolGeneration("", [ToolCall(id="save", name="design_video", arguments={
                    "draft_ref": facts["draft_ref"], "save": True,
                })])
            return ToolGeneration("Saved storyboard", [ToolCall(id="answer", name="answer", arguments={})])

    class Template:
        def render(self, **_kwargs):
            return "Make a promo from the real source; keep the user's exact requested headline."

    class Environment:
        def get_template(self, _name):
            return Template()

    monkeypatch.setattr(tool_loop, "jinja_env", Environment())
    agent = tool_loop.ToolLoopAgent(
        name="high-level-context-convergence", prompt="unused.j2", system="test",
        assemble=lambda **_kwargs: ({}, None), tools=tools, client=Client(), max_iterations=20,
    )

    async def execute(name, params, _speech):
        if name == "answer":
            return None
        if name == "search_music":
            return tool_loop.ToolObservation("Tech House is a searched candidate, never a saved Clip")
        if name == "read_skill_reference":
            return tool_loop.ToolObservation("DETAILED SKILL REFERENCE NEEDED BEFORE PLAN")
        if params.save:
            return tool_loop.ToolObservation("SAVED VERSION with presentation_rows and no music track")
        if params.scene_plan is not None:
            content = _scene_plan_write({
                "schema_version": 1,
                "settings": {"width": 1920, "height": 1080, "timebase": 90000, "fps": {"num": 30, "den": 1}},
                "sources": [{"snapshot_id": source_id, "snapshot_digest": "s" * 64}],
                "scenes": [], "timeline": {"tracks": [], "transitions": []},
            }, params.scene_plan)
            return WorkingDraftUpdated({"content": content, "design": {"authoring": "high_level_scene"}})
        content = deepcopy(params._working_draft["content"])
        scene_id = params.scene.scene_id
        scene = next(item for item in content["scenes"] if item["scene_id"] == scene_id)
        content["timeline"]["tracks"][0]["clips"].append({
            "clip_id": f"clip-{scene_id}", "scene_id": scene_id, "range": deepcopy(scene["range"]),
            "object": {"kind": "text", "text": params.scene.headline},
        })
        return WorkingDraftUpdated({"content": content, "design": {"authoring": "high_level_scene"}})

    def assemble(**facts):
        from app.chat.prompts import assemble_video_round

        return assemble_video_round({
            **facts, "mode": "plan", "skill": skill,
            "user_text": "Make a promo from the real source; keep the user's exact requested headline.",
        })

    result = await agent.call_loop(
        execute, refresh_context=lambda: _immediate(snapshot), round_assembler=assemble,
        candidate_scope=scope,
    )
    assert result.tool_name == "answer"
    assert len(requests) == 6
    stages = []
    for request in requests:
        current = next(
            message["content"] for message in reversed(request["messages"])
            if isinstance(message.get("content"), str) and "CURRENT VIDEO ROUND" in message["content"]
        )
        stages.append(json.loads(current.rsplit("\n", 1)[-1])["video_stage"])
        assert "DISCOVERY GOALS" not in request["messages"][0]["content"]
        assert not {"present_plan", "propose_candidates", "review_video"} & {
            item["function"]["name"] for item in request["tools"]
        }
    assert stages == [
        "draft_build", "draft_build", "draft_build", "draft_build", "draft_finalize", "draft_present",
    ]
    first_text = json.dumps(requests[0]["messages"], ensure_ascii=False)
    assert "COMPLETE SKILL METHOD FOR PLANNING" in first_text
    assert "VERBATIM SOURCE ONLY NEEDED FOR PLANNING" in first_text
    assert "DETAILED SKILL REFERENCE NEEDED BEFORE PLAN" in json.dumps(requests[1]["messages"])
    for request in requests[2:4]:
        text = json.dumps(request["messages"], ensure_ascii=False)
        assert "DETAILED SKILL REFERENCE NEEDED BEFORE PLAN" not in text
        assert "COMPLETE SKILL METHOD FOR PLANNING" not in text
        assert "VERBATIM SOURCE ONLY NEEDED FOR PLANNING" not in text
        assert "FULL UNRELATED PROJECT CATALOG" not in text
        assert source_id in text and "value-card" in text
        assert "Establish the actual product" in text
        assert "Show Value / Defend in the current product" in text
        assert "prepare_video_materials" in {item["function"]["name"] for item in request["tools"]}
        assert "editable_targets" not in text
    for request in requests[2:5]:
        assert sum(
            message.get("name") == "design_video"
            for message in request["messages"] if message.get("role") == "tool"
        ) == 1
    finalizing_text = json.dumps(requests[4]["messages"], ensure_ascii=False)
    assert "Exact headline first" not in finalizing_text
    assert "Exact headline second" in finalizing_text
    assert {item["function"]["name"] for item in requests[4]["tools"]} == {"design_video", "answer", "read_conversation_context"}
    assert {item["function"]["name"] for item in requests[5]["tools"]} == {"answer"}
    presented_text = json.dumps(requests[5]["messages"], ensure_ascii=False)
    assert "SAVED VERSION with presentation_rows and no music track" in presented_text
    assert "Tech House" not in presented_text


def test_explicit_design_constraints_share_wire_execution_and_draft_facts(installed_promo):
    from app.agents.candidate_correction import CandidateRecord, CandidateScope
    from app.agents.tool_loop import ContextSnapshot, tool_spec
    from app.agents.working_drafts import working_draft_arguments
    from app.chat.intent import intent_router
    from app.chat.turn_tools import tools_for_bound_skill
    from app.editing.schemas import VersionSettings
    from app.skills.resolution import get_builtin_skill_option
    from app.tools.video.design import (
        CandidateDesignError,
        CompositionDesignVideoArgs,
        _scene_plan_write,
        bind_explicit_design_constraints,
        explicit_design_constraints,
    )

    skill = get_builtin_skill_option("promo-video").reference
    tools = tools_for_bound_skill(intent_router.tools, skill)
    snapshot = ContextSnapshot(
        "prepared", frozenset({"snapshot:source:digest"}),
        resources=(("project:one", {"kind": "project", "user_stated_constraints": []}),),
    )
    unspecified = _video_round(tools, snapshot=snapshot, skill=skill, user_text="Make a promo from this site")
    design = next(tool for tool in unspecified.tools if tool.name == "design_video")
    properties = tool_spec(design)["function"]["parameters"]["properties"]
    assert not {"scene_count", "target_seconds", "aspect", "background"} & set(properties)
    assert "verbatim_copy" not in properties
    assert not {"show_music_candidates", "select_music"} & {tool.name for tool in unspecified.tools}
    assert "search_music" in {tool.name for tool in unspecified.tools}
    choosing = _video_round(
        tools, snapshot=snapshot, skill=skill,
        user_text="Show me music candidates to compare before choosing",
    )
    assert "show_music_candidates" in {tool.name for tool in choosing.tools}
    with pytest.raises(CandidateDesignError, match="not fixed by the user") as bypass:
        bind_explicit_design_constraints(CompositionDesignVideoArgs.model_validate({
            "scene_plan": [{"scene_id": "one", "intent": "Open"}], "aspect": "16:9",
        }), user_text="Make a promo from this site")
    assert bypass.value.issues[0]["loc"] == ["aspect"]

    request = "做 3 幕，总时长 24 秒，画幅 9:16，背景 #A1b2C3"
    fixed = _video_round(tools, snapshot=snapshot, skill=skill, user_text=request)
    design = next(tool for tool in fixed.tools if tool.name == "design_video")
    properties = tool_spec(design)["function"]["parameters"]["properties"]
    expected = {"scene_count": 3, "target_seconds": 24.0, "aspect": "9:16", "background": "#A1B2C3"}
    assert {field: properties[field]["enum"] for field in expected} == {
        field: [value] for field, value in expected.items()
    }
    assert '"user_constraints"' in fixed.context and '"aspect": "9:16"' in fixed.context
    args = CompositionDesignVideoArgs.model_validate({
        "scene_plan": [
            {"scene_id": "one", "intent": "Open"},
            {"scene_id": "two", "intent": "Prove"},
            {"scene_id": "three", "intent": "Close"},
        ],
        **expected,
    })
    bound = bind_explicit_design_constraints(args, user_text=request)
    content = _scene_plan_write({
        "schema_version": 1,
        "settings": VersionSettings(width=1080, height=1920, background="#A1B2C3").model_dump(mode="json"),
        "sources": [], "scenes": [], "timeline": {"tracks": [], "transitions": []},
    }, bound.scene_plan)
    draft_arguments = working_draft_arguments(bound, content)
    assert draft_arguments["design"]["user_constraints"] == expected
    record = CandidateRecord.create(
        tool_name="design_video", arguments=draft_arguments, errors=[],
        schema=CompositionDesignVideoArgs.model_json_schema(),
        scope=CandidateScope(owner_id="owner", conversation_id="conversation"), call_id="plan",
        base_keys=frozenset(),
    )
    continued = _video_round(tools, drafts=(record,), snapshot=snapshot, skill=skill, user_text="继续")
    design = next(tool for tool in continued.tools if tool.name == "design_video")
    properties = tool_spec(design)["function"]["parameters"]["properties"]
    assert not {"scene_count", "target_seconds", "aspect", "background"} & set(properties)
    assert all(f'"{field}"' in continued.context for field in expected)
    save = CompositionDesignVideoArgs.model_validate({
        "save": True,
        "draft_ref": {"draft_id": record.candidate_id, "draft_digest": record.candidate_digest},
    })
    save.bind_working_draft(record.arguments)
    restored = bind_explicit_design_constraints(save, user_text="保存当前草稿")
    assert restored._explicit_constraints == expected
    assert restored.aspect == "9:16" and restored.target_seconds == 24

    wrong = CompositionDesignVideoArgs.model_validate({
        "draft_ref": {"draft_id": record.candidate_id, "draft_digest": record.candidate_digest},
        "scene": {"scene_id": "one", "headline": "Keep this draft"}, "aspect": "16:9",
    })
    wrong.bind_working_draft(record.arguments)
    with pytest.raises(CandidateDesignError, match="preserve the user-fixed value") as rejected:
        bind_explicit_design_constraints(wrong, user_text="继续")
    assert rejected.value.working_content == content
    assert rejected.value.issues[0]["expected"] == "9:16"

    brief = {"brief": {"constraints": [
        {"value": "画幅 9:16", "source": "user-stated"},
        {"value": "画幅 16:9", "source": "inferred"},
    ]}}
    assert explicit_design_constraints("继续", brief=brief)["aspect"] == "9:16"
    assert explicit_design_constraints("exactly 2 scenes and 8 seconds") == {
        "scene_count": 2, "target_seconds": 8.0,
    }
    assert explicit_design_constraints("a 4-second component-mode storyboard")["target_seconds"] == 4.0
    assert explicit_design_constraints("Make one 9:16 video with a fixed cover crop")["aspect"] == "9:16"


def test_complete_draft_repair_only_saves_the_existing_draft(installed_promo):
    from app.agents.candidate_correction import CandidateRecord, CandidateScope
    from app.agents.tool_loop import ContextSnapshot, tool_spec
    from app.chat.intent import intent_router
    from app.chat.turn_tools import tools_for_bound_skill
    from app.skills.resolution import get_builtin_skill_option
    from app.tools.video.design import CompositionDesignVideoArgs

    content = {
        "settings": {"timebase": 90000},
        "scenes": [{"scene_id": "one", "range": {"start": 0, "end": 90000}, "intent": "Done"}],
        "timeline": {"tracks": [{
            "track_id": "trk_main", "kind": "visual", "role": "main", "order": 0,
            "clips": [{
                "clip_id": "clp_done", "scene_id": "one", "range": {"start": 0, "end": 90000},
                "object": {"kind": "text", "text": "Already written"},
            }],
        }], "transitions": []},
        "sources": [],
    }
    record = CandidateRecord.create(
        tool_name="design_video", arguments={"content": content, "design": {"authoring": "high_level_scene"}},
        errors=[{"loc": ["aspect_ratio"], "type": "extra_forbidden", "msg": "Extra inputs are not permitted"}],
        schema=CompositionDesignVideoArgs.model_json_schema(),
        scope=CandidateScope(owner_id="owner", conversation_id="conversation"),
        base_keys=frozenset(), call_id="bad-save",
    )
    skill = get_builtin_skill_option("promo-video").reference
    round = _video_round(
        tools_for_bound_skill(intent_router.tools, skill), drafts=(record,),
        snapshot=ContextSnapshot("current draft"), skill=skill, user_text="保存当前草稿",
    )
    assert round.stage == "draft_repair"
    design = next(tool for tool in round.tools if tool.name == "design_video")
    spec = tool_spec(design)["function"]
    properties = spec["parameters"]["properties"]
    assert set(properties) == {"draft_ref", "save", "pending_disposition"}
    assert not {"scene_plan", "scene", "aspect_ratio"} & set(properties)
    assert "Extra inputs are not permitted" in round.context
    assert "Every planned Scene is already present" in spec["description"]
