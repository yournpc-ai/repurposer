"""Clean up stuck pending/running workflow runs and their projects."""

import asyncio

from sqlalchemy import delete, select

from app.models.database import AsyncSessionLocal
from app.models.tables import Asset, Clip, Derivative, Project, WorkflowRun


async def cleanup() -> None:
    async with AsyncSessionLocal() as db:
        # Find stuck workflow runs
        stuck_runs = await db.execute(
            select(WorkflowRun).where(
                WorkflowRun.status.in_(["pending", "running"])  # type: ignore[arg-type]
            )
        )
        runs = list(stuck_runs.scalars().all())
        project_ids = [r.project_id for r in runs]
        print(f"Found {len(runs)} stuck workflow runs for projects: {project_ids}")

        if project_ids:
            # Delete derivatives, clips, assets for those projects
            await db.execute(delete(Derivative).where(Derivative.project_id.in_(project_ids)))
            await db.execute(delete(Clip).where(Clip.project_id.in_(project_ids)))
            await db.execute(delete(Asset).where(Asset.project_id.in_(project_ids)))
            await db.execute(delete(WorkflowRun).where(WorkflowRun.project_id.in_(project_ids)))
            await db.execute(delete(Project).where(Project.id.in_(project_ids)))
            print(f"Deleted projects and related data for {len(project_ids)} stuck runs.")

        # Also clean up orphaned pending/processing assets (no active run)
        stuck_assets = await db.execute(
            select(Asset).where(
                Asset.processing_status.in_(["pending", "processing"])  # type: ignore[arg-type]
            )
        )
        assets = list(stuck_assets.scalars().all())
        print(f"Found {len(assets)} stuck assets: {[a.id for a in assets]}")
        if assets:
            asset_project_ids = [a.project_id for a in assets if a.project_id]
            if asset_project_ids:
                await db.execute(delete(Derivative).where(Derivative.project_id.in_(asset_project_ids)))
                await db.execute(delete(Clip).where(Clip.project_id.in_(asset_project_ids)))
                await db.execute(delete(WorkflowRun).where(WorkflowRun.project_id.in_(asset_project_ids)))
                await db.execute(delete(Project).where(Project.id.in_(asset_project_ids)))
            await db.execute(delete(Asset).where(Asset.id.in_([a.id for a in assets])))
            print(f"Deleted {len(assets)} stuck assets and their projects.")

        await db.commit()


if __name__ == "__main__":
    asyncio.run(cleanup())
