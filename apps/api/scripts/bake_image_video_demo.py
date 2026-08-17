"""Bake the image-video recipe demo at 16:9 (2026-08-17 跟源画幅 ruling).

The card's chain carries no clip skill — the frame never changes hands, so
the output follows the SOURCE frame (the demo photos are landscape 16:9).
Runs the REAL pipeline in the dev DB (select_clips{aspect: 16:9} + add_music
{calm}) over the demo inputs (demo/uploads/demo-article.md + the three
on-site photos), then harvests the rendered clip + a poster frame into
demo/outputs with content-hashed keys and prints the recipes.py
ExampleOutput line for pasting.

Usage:
    uv run python scripts/bake_image_video_demo.py [--keep]
    uv run python scripts/bake_image_video_demo.py --harvest <project_id> [--keep]

Requires the worker (``uv run python -m app.worker``) and the render service
running. The bake project is deleted in FK order afterwards unless --keep.
--harvest skips creation and reaps an already-finished project (the rescue
path when the run needed manual surgery — reset-step-and-redo mid-bake).
"""

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.schemas import AssetStatus, AssetType, ProjectStatus, WorkflowStatus  # noqa: E402
from app.models.tables import (  # noqa: E402
    Asset,
    Operation,
    Output,
    Persona,
    Project,
    User,
    WorkflowRun,
    WorkflowStep,
)
from app.pipeline.orchestrator import TaskSpec, create_run  # noqa: E402
from app.tools.storage import read  # noqa: E402
from bake_subs_contrast import _poster_frame, _put_demo  # noqa: E402

_DEMO = "https://repurposer.tos-ap-southeast-1.volces.com/demo/uploads"
ARTICLE_URL = f"{_DEMO}/demo-article.md"
PHOTO_URLS = [
    f"{_DEMO}/teasers-photo-title.jpg",
    f"{_DEMO}/teasers-photo-industries.jpg",
    f"{_DEMO}/teasers-photo-outcomes.jpg",
]
# file_url stores the storage KEY, never the public URL (collect_asset_media
# downloads by key — a URL-shaped key HeadObject-404s, the first bake's
# director_understand failure).
ARTICLE_KEY = "demo/uploads/demo-article.md"
PHOTO_KEYS = [
    "demo/uploads/teasers-photo-title.jpg",
    "demo/uploads/teasers-photo-industries.jpg",
    "demo/uploads/teasers-photo-outcomes.jpg",
]
BAKE_EMAIL = "bake-image-video@local"
TASKS = [
    {"skill": "select_clips", "params": {"aspect": "16:9"}},
    {"skill": "add_music", "params": {"mood": "calm"}},
]


async def _wait_assets(project_id, timeout_s=300) -> None:
    for _ in range(timeout_s // 3):
        # A FRESH session per poll: the main session's identity map serves
        # stale row state, and expire_all() there detaches the project/user
        # instances the bake still needs (first re-bake's MissingGreenlet).
        async with AsyncSessionLocal() as s:
            rows = (
                await s.execute(
                    select(Asset.processing_status).where(Asset.project_id == project_id)
                )
            ).scalars().all()
        if rows and all(x == AssetStatus.COMPLETED for x in rows):
            return
        if any(x == AssetStatus.FAILED for x in rows):
            raise SystemExit("asset processing FAILED")
        await asyncio.sleep(3)
    raise SystemExit("asset processing timed out")


async def _wait_run(run_id, timeout_s=900) -> WorkflowStatus:
    seen: dict[str, str] = {}
    for _ in range(timeout_s // 5):
        async with AsyncSessionLocal() as s:
            run = await s.get(WorkflowRun, run_id)
            status = run.status
            steps = (
                await s.execute(
                    select(WorkflowStep).where(WorkflowStep.run_id == run_id).order_by(WorkflowStep.seq)
                )
            ).scalars().all()
            snap = [(x.seq, x.kind, x.status) for x in steps]
        for seq, kind, st in snap:
            key = f"{seq}:{kind}"
            if seen.get(key) != st:
                seen[key] = st
                print(f"  step {seq} {kind}: {st}", flush=True)
        if status in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED):
            return status
        await asyncio.sleep(5)
    raise SystemExit("run timed out")


async def _cleanup(db, user_id, project_id) -> None:
    """FK-order wipe of the bake scaffolding (dev DB hygiene)."""
    await db.execute(delete(Operation).where(Operation.project_id == project_id))
    await db.execute(
        delete(WorkflowStep).where(
            WorkflowStep.run_id.in_(
                select(WorkflowRun.id).where(WorkflowRun.project_id == project_id)
            )
        )
    )
    await db.execute(delete(Output).where(Output.project_id == project_id))
    await db.execute(delete(WorkflowRun).where(WorkflowRun.project_id == project_id))
    await db.execute(delete(Asset).where(Asset.user_id == user_id))
    await db.execute(delete(Project).where(Project.id == project_id))
    await db.execute(delete(Persona).where(Persona.user_id == user_id))
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()
    print("cleanup done", flush=True)


async def _harvest(db, project, user, keep: bool) -> None:
    """Reap the rendered clips of a finished bake project: biggest cut +
    poster frame to demo/outputs (content-hashed), print the recipes.py
    ExampleOutput line, then the FK-order cleanup unless --keep."""
    outputs = (
        await db.execute(
            select(Output).where(Output.project_id == project.id).order_by(Output.created_at)
        )
    ).scalars().all()
    clips = [o for o in outputs if (o.files or {}).get("video")]
    if not clips:
        raise SystemExit("no rendered clip output")
    # The demo shows ONE video — the biggest cut carries the most of the
    # write-up (several clips = storyboard fan-out).
    best_mp4, best, mp4_len = b"", None, -1
    for o in clips:
        data = await read(o.files["video"])
        if len(data) > mp4_len:
            best_mp4, best, mp4_len = data, o, len(data)
    mp4 = best_mp4
    tmp = Path(tempfile.mkdtemp(prefix="bake-image-video-"))
    (tmp / "image-video-preview.mp4").write_bytes(mp4)
    poster = _poster_frame(mp4, 2.0)
    if poster:
        (tmp / "image-video-poster.jpg").write_bytes(poster)
    print(f"harvested {len(mp4) / 1e6:.1f}MB from output {best.id} ({len(clips)} clips)")

    url = await _put_demo("image-video-preview", ".mp4", mp4, "video/mp4")
    poster_url = (
        await _put_demo("image-video-poster", ".jpg", poster, "image/jpeg") if poster else None
    )
    print("\n--- recipes.py example_outputs ---")
    poster_field = f'poster_url="{poster_url}", ' if poster_url else ""
    print(f'ExampleOutput(kind="video", url="{url}", {poster_field}label_key="image_video_preview"),')
    print(f"\nlocal copy: {tmp} (run upload_recipe_assets.py to refresh the web manifest)")

    if not keep:
        await _cleanup(db, user.id, project.id)


async def main() -> None:
    keep = "--keep" in sys.argv
    harvest_pid = (
        sys.argv[sys.argv.index("--harvest") + 1] if "--harvest" in sys.argv else None
    )

    async with AsyncSessionLocal() as db:
        if harvest_pid:
            project = await db.get(Project, harvest_pid)
            if project is None:
                raise SystemExit(f"project {harvest_pid} not found")
            user = await db.get(User, project.user_id)
            await _harvest(db, project, user, keep)
            return

        article = (await httpx.AsyncClient().get(ARTICLE_URL)).text
        if len(article) < 100:
            raise SystemExit(f"article fetch looks wrong ({len(article)} bytes)")

        user = (
            await db.execute(select(User).where(User.email == BAKE_EMAIL))
        ).scalars().one_or_none()
        if user is None:
            user = User(email=BAKE_EMAIL, name="bake")
            db.add(user)
            await db.flush()
        project = Project(
            user_id=user.id,
            title="bake: image-video demo 16:9",
            language="en",
            status=ProjectStatus.DRAFT,
        )
        db.add(project)
        await db.flush()
        db.add(
            Asset(
                user_id=user.id,
                project_id=project.id,
                type=AssetType.TRANSCRIPT,
                file_url=ARTICLE_KEY,
                title="demo-article.md",
                extracted_text=article,
                processing_status=AssetStatus.COMPLETED,
            )
        )
        for key in PHOTO_KEYS:
            db.add(
                Asset(
                    user_id=user.id,
                    project_id=project.id,
                    type=AssetType.IMAGE,
                    file_url=key,
                    title=key.rsplit("/", 1)[-1],
                    processing_status=AssetStatus.PENDING,
                )
            )
        await db.commit()
        print(f"project {project.id} — waiting for image processing…", flush=True)

        await _wait_assets(project.id)
        print("assets ready — creating run…", flush=True)

        run = await create_run(
            db,
            project,
            TaskSpec(
                tasks=TASKS,
                target_language="en",
                ui_language="en",
                instruction=(
                    "Turn my write-up and photos into a short subtitled "
                    "slideshow video with music."
                ),
            ),
        )
        project.status = ProjectStatus.PROCESSING
        await db.commit()
        print(f"run {run.id}", flush=True)

        status = await _wait_run(run.id)
        if status != WorkflowStatus.COMPLETED:
            raise SystemExit(f"run ended {status.value}")
        project.status = ProjectStatus.COMPLETED
        await db.flush()

        await _harvest(db, project, user, keep)


if __name__ == "__main__":
    asyncio.run(main())
