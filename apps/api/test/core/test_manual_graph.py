from uuid import uuid4

import pytest
from sqlalchemy import select

from app.chat.plan_turn import PlanTurn
from app.chat.propose_turn import ChatTurn
from app.models.schemas import EditGraphArgs, ProjectGraphResponse
from app.models.tables import GraphEdge, GraphNode, Project, User
from app.pipeline.routes.projects import get_project_graph


def test_manual_graph_rejects_tasks_and_run():
    with pytest.raises(ValueError, match="never starts a Run"):
        EditGraphArgs(ops=[{"op": "run"}])
    with pytest.raises(ValueError, match="prototype"):
        EditGraphArgs(ops=[{"op": "add_node", "type": "video", "spec": {"prototype": "generator"}}])


@pytest.mark.asyncio
async def test_manual_graph_crud_uses_existing_write_door(database):
    async with database() as db:
        user = User(email=f"{uuid4()}@example.test", name="manual-graph")
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title="Manual Graph")
        db.add(project)
        await db.flush()
        first, second = uuid4(), uuid4()
        turn = ChatTurn.__new__(ChatTurn)
        turn.db, turn.project = db, project

        created = await turn._edit_graph(EditGraphArgs(ops=[
            {"op": "add_node", "id": str(first), "type": "text", "spec": {"prototype": "manual", "text": "first"}},
            {"op": "add_node", "id": str(second), "type": "text", "spec": {"prototype": "manual", "text": "second"}, "after": [str(first)]},
            {"op": "connect", "from_node": str(first), "to_node": str(second), "edge_type": "text"},
            {"op": "edit_prompt", "node": str(second), "prompt": "edited manual text"},
        ]), "")
        assert created is None
        nodes = list((await db.scalars(select(GraphNode).where(GraphNode.project_id == project.id))).all())
        assert len(nodes) == 2
        assert all((node.spec or {}).get("prototype") == "manual" for node in nodes)
        assert next(node for node in nodes if node.id == second).spec["prompt"] == "edited manual text"
        edges = list((await db.scalars(select(GraphEdge).where(GraphEdge.project_id == project.id))).all())
        assert len(edges) == 1 and edges[0].from_node == first and edges[0].to_node == second
        graph = await get_project_graph(project.id, db, user)
        assert len(graph["nodes"]) == 2 and len(graph["edges"]) == 1
        wire = ProjectGraphResponse.model_validate(graph)
        assert (wire.edges[0].from_port, wire.edges[0].to_port) == ("out", "in")
        nullable_ports = wire.edges[0].model_copy(update={"from_port": None, "to_port": None})
        assert nullable_ports.from_port is None and nullable_ports.to_port is None

        removed = await turn._edit_graph(EditGraphArgs(ops=[
            {"op": "disconnect", "from_node": str(first), "to_node": str(second), "edge_type": "text"},
            {"op": "delete_node", "node": str(second)},
        ]), "")
        assert removed is None
        assert (await db.get(GraphNode, second)) is None
        assert list((await db.scalars(select(GraphEdge).where(GraphEdge.project_id == project.id))).all()) == []
        assert (await db.get(GraphNode, first)) is not None

        recreated = await turn._edit_graph(EditGraphArgs(ops=[
            {"op": "add_node", "id": str(second), "type": "text", "spec": {"prototype": "manual", "text": "second"}, "after": [str(first)]},
            {"op": "connect", "from_node": str(first), "to_node": str(second)},
            {"op": "disconnect", "from_node": str(first), "to_node": str(second)},
            {"op": "delete_node", "node": str(first)},
        ]), "")
        assert recreated is None
        assert (await db.get(GraphNode, first)) is None
        assert (await db.get(GraphNode, second)) is not None
        assert list((await db.scalars(select(GraphEdge).where(GraphEdge.project_id == project.id))).all()) == []

        from app.chat.service import _get_or_create_project_conversation

        conversation = await _get_or_create_project_conversation(db, user.id, project.id)
        for runner in (ChatTurn, PlanTurn):
            terminal = runner.__new__(runner)
            terminal.db, terminal.project = db, project
            terminal.conversation_id = conversation.id
            terminal.text = "请整理手动画布"
            if runner is PlanTurn:
                terminal.settled_pending = None
            else:
                terminal.settled_question = None
            result = await terminal._dispatch("edit_graph", EditGraphArgs(ops=[
                {"op": "add_node", "type": "text", "spec": {"prototype": "manual", "text": "accepted"}},
            ]), "")
            assert result is None
            assert terminal.outcome[0].content == "已更新手动画布。"
