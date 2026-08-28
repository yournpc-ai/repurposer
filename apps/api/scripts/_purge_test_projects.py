"""One-off: purge ALL test-artifact projects from the dev DB (2026-08-27,
user-requested). Every project in the dev DB is a probe/bake/debug leftover —
nothing user-authored. reset_db.py is NOT the tool (it would also wipe the
user account + hand-made personas/voice clones).

Per project, FK order: Message → Conversation → WorkflowStep → WorkflowRun
→ Output → Operation → Asset(project-linked) → Publication → Project →
project-owned Persona (1:1 auto-created; only when no other project refs it).
Storage: {user}/uploads/projects/{pid}/* + {user}/outputs/projects/{pid}/*
(demo/ and music/ prefixes are never touched — they're not project-scoped).
"""
import asyncio
import sys

sys.path.insert(0, str(__file__.rsplit("/", 2)[0]))

from sqlalchemy import delete, select, func

from app.config import settings
from app.models.database import AsyncSessionLocal
from app.models.tables import (
    Asset,
    Conversation,
    Message,
    Operation,
    Output,
    Persona,
    Project,
    Publication,
    WorkflowRun,
    WorkflowStep,
)
from app.providers.storage import _get_s3_client


async def main() -> None:
    s3 = _get_s3_client()
    bucket = settings.s3_bucket_name
    async with AsyncSessionLocal() as db:
        projects = list((await db.execute(select(Project))).scalars().all())
        print(f"purging {len(projects)} projects…")
        for p in projects:
            pid = p.id
            await db.execute(
                delete(Message).where(
                    Message.conversation_id.in_(
                        select(Conversation.id).where(Conversation.project_id == pid)
                    )
                )
            )
            await db.execute(delete(Conversation).where(Conversation.project_id == pid))
            await db.execute(
                delete(WorkflowStep).where(
                    WorkflowStep.run_id.in_(
                        select(WorkflowRun.id).where(WorkflowRun.project_id == pid)
                    )
                )
            )
            await db.execute(delete(WorkflowRun).where(WorkflowRun.project_id == pid))
            await db.execute(delete(Output).where(Output.project_id == pid))
            await db.execute(delete(Operation).where(Operation.project_id == pid))
            await db.execute(delete(Asset).where(Asset.project_id == pid))
            await db.execute(delete(Publication).where(Publication.project_id == pid))
            persona_id = p.persona_id
            await db.execute(delete(Project).where(Project.id == pid))
            if persona_id:
                still_used = (
                    await db.execute(
                        select(func.count())
                        .select_from(Project)
                        .where(Project.persona_id == persona_id)
                    )
                ).scalar_one()
                if not still_used:
                    await db.execute(delete(Persona).where(Persona.id == persona_id))
            # storage objects under both project scopes
            for scope in ("uploads", "outputs"):
                prefix = f"{p.user_id}/{scope}/projects/{pid}/"
                resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
                for obj in resp.get("Contents", []):
                    s3.delete_object(Bucket=bucket, Key=obj["Key"])
            print(f"  ✓ {str(pid)[:8]} {p.title!r}")
        await db.commit()
        remaining = (await db.execute(select(func.count()).select_from(Project))).scalar_one()
        print(f"projects remaining: {remaining}")


if __name__ == "__main__":
    asyncio.run(main())
