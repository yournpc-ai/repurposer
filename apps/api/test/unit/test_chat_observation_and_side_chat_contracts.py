"""Chat observation and side chat — unit contracts."""
from __future__ import annotations

from copy import copy
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.agents.tool_loop import BatchDeclared, ContextSnapshot, ReadExecuting
from app.chat.editor import InsertMotionBlockArgs, _remember_labels, project_editor_reply
from app.chat.intent import intent_router
from app.chat.prompts import assemble_video_round
from app.editing.catalog import MOTION_BLOCK_CATALOG
from app.providers.llm.base import ToolCall, ToolGeneration

pytestmark = pytest.mark.unit


def test_h4_h5_redaction_catalog_guidance_and_local_storage(tmp_path, monkeypatch):
    turn = SimpleNamespace()
    comp_id = UUID("27c839ec-1111-4222-8333-444455556666")
    ver_id = UUID("88aa99bb-1111-4222-8333-444455556666")
    _remember_labels(turn, [], ver_id, "abcdef1234567890", 1, composition_id=comp_id)

    leaked = f"已为你创建作品 `27c839ec`（完整 ID {comp_id}），当前版本 `88aa99bb`。"
    redacted = project_editor_reply(leaked, turn._editor_labels, "帮我做个视频")
    assert "27c839ec" not in redacted
    assert str(comp_id) not in redacted
    assert "88aa99bb" not in redacted
    assert "当前作品" in redacted
    assert "第 1 版" in redacted

    # version_present wires project_reply
    assembly = assemble_video_round({
        "tools": intent_router.tools,
        "snapshot": ContextSnapshot("empty"),
        "user_text": "帮我做个视频",
        "version_saved": True,
        "editor_labels": turn._editor_labels,
    })
    assert assembly.stage == "version_present"
    assert assembly.project_reply is not None
    assert "27c839ec" not in assembly.project_reply("组合 27c839ec 已保存")

    # H5: metric_grid unit guidance in catalog & schema
    assert "items[].value" in MOTION_BLOCK_CATALOG["metric_grid"]["desc"]
    assert "items[].value" in InsertMotionBlockArgs.model_fields["props"].description


class _PendingSideScriptedClient:
    capabilities = SimpleNamespace(supports_native_tools=True, supports_streaming=False)

    def __init__(self, generations: list[ToolGeneration]):
        self._generations = list(generations)
        self.calls: list[dict] = []

    async def generate_with_tools(self, **kwargs):
        self.calls.append(kwargs)
        assert self._generations, "Unexpected extra LLM iteration"
        return self._generations.pop(0)


def test_assemble_video_round_preserves_editor_context_when_pending_without_works():
    pending_card = SimpleNamespace(
        question={
            "kind": "question",
            "question": "允许为「封面」生成图片吗？最多使用 4 积分。",
            "options": [{"id": "approve", "label": "允许"}, {"id": "decline", "label": "取消"}],
        },
        intent={"media_permission": {"quote": {"total": [4, 4]}}},
    )
    assembly = assemble_video_round({
        "tools": intent_router.tools,
        "snapshot": ContextSnapshot("empty"),
        "user_text": "顺便问一下，导出 1080p 要多久？",
        "pending_question": pending_card,
    })
    tool_names = {t.name for t in assembly.tools}
    assert "create_video" in tool_names
    assert "answer" in tool_names
    assert "update_focus" in tool_names
    assert assembly.allow_bare_reply is True
    assert '"awaiting_media_authorization": true' in assembly.context
    assert '"video_target": "unresolved"' not in assembly.context


@pytest.mark.asyncio
async def test_update_focus_batched_with_editor_tool_omits_focus_from_batch_declared():
    from app.agents.tool_loop import ToolObservation

    client = _PendingSideScriptedClient([
        ToolGeneration(
            content="",
            tool_calls=[
                ToolCall(id="c_focus", name="update_focus", arguments={"focus": "正在编排 Vox 风格开场幕"}),
                ToolCall(id="c_style", name="set_composition_style", arguments={"preset_id": "vox_editorial"}),
            ],
        ),
        ToolGeneration(
            content="已切换为 Vox 报刊风格。",
            tool_calls=[ToolCall(id="c_done", name="answer", arguments={"pending_disposition": "none"})],
        ),
    ])
    agent = copy(intent_router)
    agent.client = client
    events = []
    executed = []

    async def execute(name, _params, _speech):
        executed.append(name)
        if name == "answer":
            return None
        return ToolObservation("ok", ok=True, context_lifetime="call", persist=False)

    result = await agent.call_loop(
        execute,
        on_loop_event=events.append,
        message="换成 Vox 风格",
    )
    assert result.calls == ["update_focus", "set_composition_style", "answer"]
    assert executed == ["update_focus", "set_composition_style", "answer"]
    declared = [e for e in events if isinstance(e, BatchDeclared)]
    assert len(declared) == 1
    assert [m.tool_name for m in declared[0].members] == ["set_composition_style"]
    executing_tools = [e.tool_name for e in events if isinstance(e, ReadExecuting)]
    assert executing_tools == ["update_focus", "set_composition_style"]
