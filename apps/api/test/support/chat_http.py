"""Drive the production Chat route and decode its complete SSE response."""
from uuid import uuid4

from app.providers.llm.base import ToolCall, ToolGeneration
from scripts.eval_chat_e2e import parse_sse_frames


def tool(name, arguments, content="", *, call_id=None):
    return ToolGeneration(content=content, tool_calls=[
        ToolCall(id=call_id or str(uuid4()), name=name, arguments=arguments),
    ])


async def post_chat(client, project_id, message, **fields):
    response = await client.post(
        "/api/v1/chat", headers={"Accept": "text/event-stream"},
        json={"project_id": str(project_id), "message": message, **fields},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = parse_sse_frames(response.text)
    assert frames and frames[-1][0] == "turn.completed", frames
    return frames


async def scripted_chat(database, monkeypatch, owner_id, project_id, message, generations, **fields):
    """Return the provider transcript and real SSE frames of a persisted opening."""
    from uuid import UUID

    from app.chat.intent import intent_router
    from app.models.tables import Message, User
    from test.support.db_helpers import ScriptedToolClient, bind_test_database, full_api_client

    bind_test_database(monkeypatch, database)
    llm = ScriptedToolClient(generations, streaming=True)
    monkeypatch.setattr(intent_router, "client", llm)
    monkeypatch.setattr("app.providers.llm.get_llm_client", lambda: llm)
    async with database() as db:
        user = await db.get(User, owner_id)
    async with full_api_client(database, user) as client:
        frames = await post_chat(client, project_id, message, **fields)
    async with database() as db:
        opening = await db.get(Message, UUID(frames[-1][1]["user_message"]["id"]))
        assert opening.content == message and opening.turn_state == "settled"
    return llm, frames


async def tool_result(database, monkeypatch, owner_id, project_id, message, name, args,
                      *, operation, call_id=None, **fields):
    """Drive one editor action and observe its unabridged result before LLM projection."""
    from importlib import import_module

    module_name, attribute = operation.rsplit(".", 1)
    module = import_module(module_name)
    original = getattr(module, attribute)
    observed = []

    async def record(*args, **kwargs):
        result = await original(*args, **kwargs)
        observed.append(result)
        return result

    with monkeypatch.context() as patch:
        patch.setattr(module, attribute, record)
        llm, frames = await scripted_chat(
            database, patch, owner_id, project_id, message,
            [tool(name, args, call_id=call_id), tool("answer", {}, "Done.")], **fields,
        )
    assert len(observed) == 1, [call["messages"][-1] for call in llm.calls]
    return observed[0], frames
