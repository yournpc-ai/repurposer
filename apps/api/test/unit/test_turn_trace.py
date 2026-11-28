import asyncio
import json
from uuid import uuid4

import pytest

from app.agents.tool_loop import ChatTool, ContextSnapshot, ToolObservation
from app.agents.tool_progress import report_progress
from app.chat.intent import intent_router
from app.chat.prompts import assemble_video_round
from app.config import settings
from app.metering import bind_conversation_turn, current_model_prompt
from app.providers.llm import trace, turn_trace
from app.providers.llm.base import ProviderCapabilities, ToolCall, ToolGeneration


@pytest.mark.parametrize("fail", [False, True])
async def test_trace_follows_real_assembly_provider_shapes_and_tool_exits(tmp_path, monkeypatch, fail):
    wire = tmp_path / "provider-exchange.jsonl"
    monkeypatch.setattr(settings, "llm_trace_path", str(wire))
    conversation, turn, project = uuid4(), uuid4(), uuid4()

    class Provider:
        capabilities = ProviderCapabilities(supports_native_tools=True)

        async def generate_with_tools(self, *, messages, tools, **kwargs):
            iteration = current_model_prompt()["iteration"]
            name = "create_video" if iteration == 0 else "answer"
            call = {"id": name, "name": name, "arguments": "{}"}
            usage = {"prompt_tokens": 400, "prompt_tokens_details": {"cached_tokens": iteration * 200},
                     "completion_tokens": 10}
            response = ({"tool_calls": [call]} if iteration == 0 else
                        {"choices": [{"message": {"tool_calls": [{"id": name, "function": call}]}}]})
            identity = {"provider": "test", "model": "editor"}
            call_id = trace.trace_start({"messages": messages, "tools": tools}, "tools", **identity)
            trace.trace_finish(call_id, **identity, response={**response, "usage": usage})
            return ToolGeneration("done", [ToolCall(id=name, name=name, arguments={})])

    monkeypatch.setattr(intent_router, "client", Provider())
    saved = False

    async def refresh():
        resources = [("project:p", {"kind": "project", "resource_counts": {"composition": int(saved)}})]
        if saved:
            resources.append(("composition:v1", {"kind": "composition", "composition_id": "work",
                              "version_id": "v1", "version": 1, "base_ref": {"composition_version_id": "v1"}}))
        return ContextSnapshot("", resources=tuple(resources), skill_method="私有创作方法")

    def assemble(**facts):
        return assemble_video_round({**facts, "user_text": "make a video", "skill": {"skill_id": "demo"}})

    async def execute(name, params, speech):
        nonlocal saved
        if name == "create_video":
            await report_progress("save")
            if fail:
                raise KeyError("missing timeline")
            saved = True
            return ToolObservation('{"version":1,"version_id":"v1","output_id":"output-a"}', version_saved=True)
        return None

    with bind_conversation_turn(conversation_id=conversation, turn_id=turn, project_id=project):
        run = intent_router.call_loop(execute, message="make a video", refresh_context=refresh,
                                     round_assembler=assemble, tools=[
            ChatTool(name="create_video", description="Create", params_model=None, terminal=False),
            ChatTool(name="answer", description="Finish", params_model=None),
        ])
        if fail:
            with pytest.raises(KeyError, match="missing timeline"):
                await run
        else:
            assert (await run).tool_name == "answer"

    path = tmp_path / "turns" / str(conversation) / f"{turn}.jsonl"
    events = [json.loads(line) for line in path.read_text().splitlines()]
    assembly, exchange, span = events[:3]
    assert set(assembly["template_files"]) >= {
        "chat/video_editor.j2", "chat/_identity_menu.j2", "chat/_interaction_constitution.j2",
        "chat/_markdown_speech.j2", "demo/SKILL.md",
    }
    assert assembly["context_sources"]["bound_skill_method"] == len(json.dumps("私有创作方法", ensure_ascii=False).encode())
    assert assembly["offered_tools"] == ["create_video", "answer"]
    assert assembly["project_resources"]["resource_counts"] == {"composition": 0}
    assert exchange["cached_tokens"] == 0 and exchange["prompt_tokens"] == 400
    assert exchange["tool_calls"] == [{"id": "create_video", "name": "create_video"}]
    assert span["tool_call_id"] == "create_video" and span["sub_steps"] == ["save"]
    assert span["duration_ms"] >= 0 and span["ok"] == (not fail)
    summary = path.with_suffix(".summary.md").read_text()
    assert str(project) in summary and "demo/SKILL.md" in summary and "cached_tokens=0" in summary
    assert "私有创作方法" not in summary + path.read_text()
    assert events[-1]["event"] == "turn_summary"
    assert events[-1]["total_iterations"] == (1 if fail else 2)
    if fail:
        assert events[-1]["outcome"] == "KeyError"
        assert span["error"]["type"] == "KeyError" and "missing timeline" in summary
    else:
        assert span["produced_version"] == {"version": 1, "version_id": "v1"}
        assert span["produced_output_id"] == "output-a"
        assert events[3]["project_resources"]["versions"] == {"work": "v1"}
        assert events[4]["tool_calls"] == [{"id": "answer", "name": "answer"}]
        assert "cached_tokens=200" in summary and "iter 1" in summary


async def test_concurrent_turns_redact_both_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "llm_trace_path", str(tmp_path / "wire.jsonl"))
    conversation = uuid4()

    async def run(turn):
        with bind_conversation_turn(conversation_id=conversation, turn_id=turn):
            turn_trace.record_tool_span(
                iteration=0, tool_call_id=turn, tool_name="inspect", duration_ms=2, ok=False,
                args_summary={"api_key": "private-key", "cookie": "private-cookie",
                              "image": "data:image/png;base64,YWJj"},
                error={"message": "could not fetch https://example.test/file?sig=private-signature"},
            )
            await asyncio.sleep(0)
            turn_trace.finalize_turn_trace(outcome="failed", total_iterations=1)

    await asyncio.gather(run("turn-one"), run("turn-two"))
    folder = tmp_path / "turns" / str(conversation)
    for turn, sibling in (("turn-one", "turn-two"), ("turn-two", "turn-one")):
        for suffix in ("jsonl", "summary.md"):
            content = (folder / f"{turn}.{suffix}").read_text()
            assert turn in content
            assert all(v not in content for v in (sibling, "private-key", "private-cookie", "private-signature", "YWJj"))


@pytest.mark.parametrize("disabled", [False, True])
def test_disabled_or_unwritable_diagnostics_do_not_interrupt_provider(tmp_path, monkeypatch, disabled):
    blocker = tmp_path / "regular-file"
    blocker.touch()
    monkeypatch.setattr(settings, "llm_trace_path", "" if disabled else str(blocker / "wire.jsonl"))
    with bind_conversation_turn(conversation_id=uuid4(), turn_id=uuid4()):
        call = trace.trace_start({}, "test", provider="test", model="editor")
        trace.trace_finish(call, provider="test", model="editor", response={})
        turn_trace.finalize_turn_trace(outcome="done", total_iterations=1)
    assert list(tmp_path.iterdir()) == [blocker]


def test_resumed_turn_summary_keeps_prior_attempt_and_latest_outcome(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "llm_trace_path", str(tmp_path / "wire.jsonl"))
    conversation, turn = uuid4(), uuid4()
    for outcome, count in (("KeyError", 2), ("answer", 3)):
        with bind_conversation_turn(conversation_id=conversation, turn_id=turn):
            turn_trace.finalize_turn_trace(outcome=outcome, total_iterations=count)
    summary = (tmp_path / "turns" / str(conversation) / f"{turn}.summary.md").read_text()
    assert "outcome: answer" in summary and "total_iterations: 5" in summary
    assert summary.index("End: KeyError") < summary.index("End: answer")


async def test_dynamic_project_context_trails_dialogue_and_observations_for_prompt_cache(monkeypatch):
    seen_messages: list[list[dict]] = []
    seen_sections: list[dict] = []

    class Provider:
        capabilities = ProviderCapabilities(supports_native_tools=True)

        async def generate_with_tools(self, *, messages, tools, **kwargs):
            seen_messages.append(messages)
            seen_sections.append(current_model_prompt()["message_sections"])
            iteration = current_model_prompt()["iteration"]
            if iteration == 0:
                return ToolGeneration("", [ToolCall(id="c1", name="edit_step", arguments={})])
            return ToolGeneration("done", [ToolCall(id="c2", name="answer", arguments={})])

    monkeypatch.setattr(intent_router, "client", Provider())
    version = 1

    async def refresh():
        return ContextSnapshot("", resources=(
            ("project:p", {"kind": "project", "resource_counts": {"composition": 1}}),
            (f"composition:v{version}", {"kind": "composition", "composition_id": "work",
             "version_id": f"v{version}", "version": version, "base_ref": {"composition_version_id": f"v{version}"}}),
        ))

    def assemble(**facts):
        from app.agents.tool_loop import RoundAssembly
        return RoundAssembly(
            system="You are an editor.",
            tools=facts["tools"],
            context=json.dumps({"selected_version": version}),
            include_project_context=False,
            opening_text="polish the video",
        )

    async def execute(name, params, speech):
        nonlocal version
        if name == "edit_step":
            version = 2
            return ToolObservation('{"version": 2}', version_saved=True)
        return None

    await intent_router.call_loop(
        execute,
        message="polish the video",
        dialogue=[{"role": "user", "content": "polish the video"}],
        refresh_context=refresh,
        round_assembler=assemble,
        tools=[
            ChatTool(name="edit_step", description="Edit", params_model=None, terminal=False),
            ChatTool(name="answer", description="Answer", params_model=None, terminal=True),
        ],
    )

    assert len(seen_messages) == 2
    # Both iterations place dynamic project_context AFTER dialogue and observations.
    for sections in seen_sections:
        assert sections["project_context"][0] >= sections["dialogue"][-1] + 1
        if sections["observations"]:
            assert sections["project_context"][0] >= sections["observations"][-1] + 1
    # The stable prefix (system + dialogue) before dynamic project_context stays identical across writes.
    assert seen_messages[0][:2] == seen_messages[1][:2]
    assert seen_messages[0][-1]["name"] == "project_evidence"
    assert seen_messages[1][-1]["name"] == "project_evidence"
    assert seen_messages[0][-1]["content"] != seen_messages[1][-1]["content"]
