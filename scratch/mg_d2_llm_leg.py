"""MG D2 LLM leg: real create_run([launch_film]) × N on the fixture project —
measures the storyboarder's first-pass rate and the validator's rejection
shape (双未知之② 的实证).

Run: uv run python scratch/mg_d2_llm_leg.py [N]
Requires: the D2 fixture chain already green (a COMPLETED web_page capture of
github.com on the project), the worker running D2 code.
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, "/Users/sylas/repurposer/apps/api")

from sqlalchemy import select

from app.models.database import AsyncSessionLocal
from app.models.schemas import TaskItem
from app.models.tables import Project, WorkflowRun, WorkflowStep
from app.pipeline.orchestrator import TaskSpec, create_run

PROJECT_ID = "4e97b9c5-851b-43be-94c1-4144af6d15a5"
WORKER_LOG = Path("/tmp/mg_d2_worker.log")
N_RUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 3


async def wait_run(run_id, timeout=900) -> WorkflowRun:
    deadline = time.time() + timeout
    while time.time() < deadline:
        async with AsyncSessionLocal() as db:
            run = await db.get(WorkflowRun, run_id)
            if str(run.status) in ("COMPLETED", "FAILED", "completed", "failed"):
                return run
        await asyncio.sleep(4)
    raise AssertionError("run timed out")


def rejections_since(offset: int) -> list[str]:
    """Worker-log film_storyboard_rejected lines past a byte offset."""
    if not WORKER_LOG.exists():
        return []
    with WORKER_LOG.open() as f:
        f.seek(offset)
        return [ln for ln in f if "film_storyboard_rejected" in ln]


async def one_run(i: int) -> dict:
    log_offset = WORKER_LOG.stat().st_size if WORKER_LOG.exists() else 0
    async with AsyncSessionLocal() as db:
        project = await db.get(Project, PROJECT_ID)
        run = await create_run(
            db,
            project,
            TaskSpec(
                tasks=[TaskItem(tool="launch_film", params={})],
                instruction="Make a short launch film of this page.",
                ui_language="en",
            ),
        )
        await db.commit()
        run_id = run.id
    print(f"run {i}: {run_id} — running…", flush=True)
    run = await wait_run(run_id)

    async with AsyncSessionLocal() as db:
        steps = (
            await db.execute(
                select(WorkflowStep).where(WorkflowStep.run_id == run_id)
            )
        ).scalars().all()
    film = next((s for s in steps if s.kind == "launch_film"), None)
    rejects = rejections_since(log_offset)
    return {
        "run": str(run_id),
        "status": str(run.status),
        "node_status": str(film.status) if film else None,
        "rewrites": len(rejects),
        "failure": (film.spec or {}).get("failure") if film else None,
        "error": getattr(film, "error", None) if film else None,
    }


async def main():
    results = []
    for i in range(1, N_RUNS + 1):
        results.append(await one_run(i))
        print(f"  → {results[-1]}", flush=True)
    passes = sum(1 for r in results if r["node_status"] == "done")
    print("\n=== LLM leg summary ===")
    for r in results:
        print(r)
    print(
        f"first-pass rate: {sum(1 for r in results if r['rewrites'] == 0 and r['node_status'] == 'done')}/{len(results)}; "
        f"node done: {passes}/{len(results)}; "
        f"total rewrites: {sum(r['rewrites'] for r in results)}"
    )


if __name__ == "__main__":
    asyncio.run(main())
