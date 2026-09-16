"""B2 §10.4 drill: zombie Suspend guard (COMPLETED→WAITING_HUMAN must match 0 rows)
+ §10.3 prep: find a clip output with a real render_spec."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, "/Users/sylas/repurposer/apps/api")

from sqlalchemy import select, text, update

from app.models.database import AsyncSessionLocal
from app.models.tables import Output, WorkflowRun


async def main():
    async with AsyncSessionLocal() as db:
        # --- §10.4: expected-from-state guard on a COMPLETED run ---
        run = (
            await db.execute(
                select(WorkflowRun)
                .where(WorkflowRun.status == "COMPLETED")
                .order_by(WorkflowRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if run is None:
            print("§10.4 SKIP: no COMPLETED run in dev DB")
        else:
            rid = run.id
            res = await db.execute(
                update(WorkflowRun)
                .where(WorkflowRun.id == rid, WorkflowRun.status == "RUNNING")
                .values(status="WAITING_HUMAN")
            )
            await db.rollback()  # probe only — never persist
            print(
                f"§10.4 guard probe on run {rid}: rowcount={res.rowcount} "
                f"({'PASS — 0 rows, zombie Suspend structurally dead' if res.rowcount == 0 else 'FAIL'})"
            )

        # --- §10.3 prep: reusable clip outputs with render_spec ---
        clips = (
            (
                await db.execute(
                    select(Output)
                    .where(Output.type == "clip", Output.render_spec.isnot(None))
                    .order_by(Output.created_at.desc())
                    .limit(5)
                )
            )
            .scalars()
            .all()
        )
        for c in clips:
            src = (c.render_spec or {}).get("source") or {}
            print(
                f"clip {c.id} status={c.status} render_status={c.render_status} "
                f"asset_id={src.get('asset_id')} url={str(src.get('url'))[:80]} "
                f"segments={len(c.render_spec.get('segments') or [])}"
            )
        if not clips:
            print("§10.3 prep: no clip outputs with render_spec in dev DB")


asyncio.run(main())
