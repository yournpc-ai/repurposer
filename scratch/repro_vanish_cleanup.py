"""FK-order wipe of the vanish-repro scratch projects (dev DB hygiene —
验证后清数据 discipline). Only the four known scratch ids, never anything
else. Storage objects under their upload keys are orphaned (dev bucket).
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))

from sqlalchemy import delete, select  # noqa: E402

from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.tables import (  # noqa: E402
    Asset,
    Conversation,
    GraphEdge,
    GraphNode,
    Message,
    Operation,
    Output,
    Project,
    Publication,
    WorkflowRun,
    WorkflowStep,
)

# The three vanish repros. (Agent A's 79eac1a3 cleanup stays its own offer.)
# Notifications / CreditTransactions are user-scoped (no project_id) — left
# alone; they reference runs only informationally via ref.
SCRATCH = [
    "4dedd937-cd4a-4b5a-b64e-a24e3e98d361",
    "e6c50396-cd12-4c23-aed3-c667ff862a31",
    "be2348e9-35a8-4114-bfec-19e2ab4b82dd",
    "f8c2dc11-f578-4d95-95d3-b441e3488468",
]


async def wipe(pid: str) -> None:
    async with AsyncSessionLocal() as db:
        proj = (
            await db.execute(select(Project).where(Project.id == pid))
        ).scalar_one_or_none()
        if proj is None:
            print(f"{pid}: not found, skip")
            return
        print(f"{pid}: wiping '{proj.title}'")
        run_ids = select(WorkflowRun.id).where(WorkflowRun.project_id == pid)
        conv_ids = select(Conversation.id).where(Conversation.project_id == pid)
        await db.execute(delete(Publication).where(Publication.project_id == pid))
        await db.execute(delete(Operation).where(Operation.project_id == pid))
        await db.execute(delete(WorkflowStep).where(WorkflowStep.run_id.in_(run_ids)))
        await db.execute(delete(Output).where(Output.project_id == pid))
        await db.execute(delete(WorkflowRun).where(WorkflowRun.project_id == pid))
        await db.execute(delete(Message).where(Message.conversation_id.in_(conv_ids)))
        await db.execute(delete(Conversation).where(Conversation.project_id == pid))
        await db.execute(delete(GraphEdge).where(GraphEdge.project_id == pid))
        await db.execute(delete(GraphNode).where(GraphNode.project_id == pid))
        await db.execute(delete(Asset).where(Asset.project_id == pid))
        await db.execute(delete(Project).where(Project.id == pid))
        await db.commit()
        print(f"{pid}: done")


async def main() -> None:
    for pid in SCRATCH:
        await wipe(pid)


if __name__ == "__main__":
    asyncio.run(main())
