"""MG D3 失败释放实证 (放行闸④ 的失败半边): a project whose web_page capture
FAILED → launch_film's honest refusal (no LLM call, zero cost) → step failed
→ run failed → the hold releases IN FULL with zero capture rows.

Run: uv run python scratch/mg_d3_failure_release.py
"""

import asyncio
import sys
import time

sys.path.insert(0, "/Users/sylas/repurposer/apps/api")

from sqlalchemy import select

from app.models.database import AsyncSessionLocal
from app.models.schemas import AssetStatus, AssetType, TaskItem
from app.models.tables import Asset, CreditTransaction, Project, User, WorkflowRun
from app.pipeline.orchestrator import TaskSpec, create_run


async def main() -> None:
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).order_by(User.created_at).limit(1))).scalar_one()
        project = Project(user_id=user.id, title="MG D3 failure-release probe", language="en")
        db.add(project)
        await db.flush()
        # A capture that "completed" without a manifest (the corrupt
        # mid-run surface): the birthplace ∀-check sees a web_page present
        # and not-FAILED, the run starts, the node's honest refusal fires
        # before any LLM call (zero provider cost on the failed step).
        db.add(
            Asset(
                project_id=project.id,
                user_id=user.id,
                type=AssetType.WEB_PAGE,
                title="dead.example",
                processing_status=AssetStatus.COMPLETED,
                meta={"error": "probe: manifest missing"},
            )
        )
        await db.flush()
        try:
            run = await create_run(
                db,
                project,
                TaskSpec(
                    tasks=[TaskItem(tool="launch_film", params={})],
                    instruction="probe",
                    ui_language="en",
                ),
            )
        except ValueError as e:
            print("birthplace rejected (also lawful):", str(e)[:200])
            return
        await db.commit()
        run_id = run.id
        print("run", run_id)

    deadline = time.time() + 300
    while time.time() < deadline:
        async with AsyncSessionLocal() as db:
            run = await db.get(WorkflowRun, run_id)
            if str(run.status).lower().endswith(("completed", "failed")):
                break
        await asyncio.sleep(3)
    print("terminal:", run.status)

    async with AsyncSessionLocal() as db:
        txns = list(
            (
                await db.execute(
                    select(CreditTransaction).where(CreditTransaction.user_id == user.id)
                )
            )
            .scalars()
            .all()
        )
    rows = [t for t in txns if (t.ref or {}).get("run_id") == str(run_id)]
    for t in rows:
        print("ledger:", t.kind, t.amount, t.idempotency_key)
    held = sum(-t.amount for t in rows if t.kind == "hold")
    captured = sum(-t.amount for t in rows if t.kind == "capture")
    released = sum(t.amount for t in rows if t.kind == "release")
    print(f"held={held} captured={captured} released={released}")
    assert str(run.status).lower().endswith("failed"), "run should fail (honest refusal)"
    assert captured == 0, "failed run must have ZERO capture (失败不扣费)"
    assert released == held, "hold must release in full"
    print("failure-release ok")


asyncio.run(main())
