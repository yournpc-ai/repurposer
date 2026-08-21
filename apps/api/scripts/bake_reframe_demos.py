"""Bake the 分镜双子卡 demos (reframe / highlight-clips) through the REAL
pipeline (2026-08-20 卡面 authoring batch).

Both cards are the same craft layer (crop_track) in two dishes — the bake
proves the declared chain `[select_clips → reframe_clip]` on each card's
curated demo source and harvests the most reframe-active clip (the one with
the most crop_track keyframes — the visible switch / follow story) into
demo/outputs with content-hashed keys.

Demo craft (TikTok 分镜 genre, all existing contract — zero renderer work):
- persistent hook title on top (single-line layouts keep it for the whole
  video portion), written by the clip_writer;
- karaoke word-highlight captions at the bottom (the bake persona's brand
  block pins captionStylePreset=karaoke-highlight — a skin option, honestly
  user-selectable);
- no intro/outro cards (system default).

Sources: demo/uploads/xy_1_interview_15s.mp4 (cut from xy_1 [172.5,187.0] —
one clean speaker switch ~6.6s in, chosen against the full file's real
speaker_map turns; NEVER loudness-normalize a demo source: loudnorm fills
the ≥0.6s silence gaps whisper's turn segmentation depends on, collapsing
the interview to one turn and the reframe to one static keyframe) and the
already-curated demo/uploads/xy_2_15s.mp4 (the subs card's keynote excerpt —
one source, many products is the product's own story).

Usage:
    uv run python scripts/bake_reframe_demos.py reframe [--keep]
    uv run python scripts/bake_reframe_demos.py highlight-clips [--keep]
    uv run python scripts/bake_reframe_demos.py reframe --harvest <project_id>

Requires the worker + render service running (dev.sh). The bake project is
deleted in FK order afterwards unless --keep — on FAILURE the scaffolding
leaks instead (the project id is printed before the waits; rescue or wipe
via `--harvest <pid>`, which cleans up unless --keep). Cleanup deletes DB
rows only; rendered objects under the project output prefix stay in the
bucket (reset_db.py's storage purge is the wipe path).
"""

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import delete, select  # noqa: E402

from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.schemas import (  # noqa: E402
    AssetStatus,
    AssetType,
    ProjectStatus,
    RenderStatus,
    WorkflowStatus,
)
from app.models.tables import (  # noqa: E402
    Asset,
    Operation,
    Output,
    Persona,
    Project,
    Publication,
    User,
    WorkflowRun,
    WorkflowStep,
)
from app.pipeline.orchestrator import TaskSpec, create_run  # noqa: E402
from app.providers.storage import read  # noqa: E402
from bake_subs_contrast import _poster_frame, _put_demo  # noqa: E402

BAKE_EMAIL = "bake-reframe@local"
# The karaoke look is a persona skin option — the bake pins it on a throwaway
# persona so the demo renders what a user can select (never a bake-only
# renderer branch). captionColor=white matters: karaoke's accent is #facc15
# and the DEFAULT skin's captionColor is the same yellow — on the default
# both active and resting words are yellow and the karaoke sweep is
# invisible. White resting words make the yellow active word read.
BAKE_BRAND = {"captionStylePreset": "karaoke-highlight", "captionColor": "#ffffff"}

CARDS = {
    # 访谈分镜: the 15s segment carries exactly one speaker switch (~6.6s) —
    # count=1 keeps the clip spanning the boundary so the switch is visible.
    "reframe": {
        "source_key": "demo/uploads/xy_1_interview_15s.mp4",
        "tasks": [
            {"tool": "select_clips", "params": {"count": 1}},
            {"tool": "reframe_clip", "params": {"mode": "auto"}},
        ],
        # The card's real promptTemplate (zh) — the demo IS the card launch.
        "instruction": "把我的双人访谈剪成竖屏短片，镜头跟着说话人切换。",
        "language": "zh",
        "output_stem": "reframe-vertical",
    },
    # 演讲短片: the curated 15s keynote excerpt; follow mode micro-tracks the
    # podium speaker (3-7 keyframes per clip in acceptance).
    "highlight-clips": {
        "source_key": "demo/uploads/xy_2_15s.mp4",
        "tasks": [
            {"tool": "select_clips", "params": {"count": 2}},
            {"tool": "reframe_clip", "params": {"mode": "auto"}},
        ],
        "instruction": "Find the best moments of this video and cut them into vertical clips — the camera follows the speaker.",
        "language": "en",
        "output_stem": "highlight-clips-vertical",
    },
}


async def _wait_assets(project_id, timeout_s=300) -> None:
    for _ in range(timeout_s // 3):
        # A FRESH session per poll: the main session's identity map serves
        # stale row state (the image-video bake's MissingGreenlet lesson).
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


async def _cleanup(db, project_id) -> None:
    """FK-order wipe of the bake scaffolding (dev DB hygiene)."""
    await db.execute(delete(Operation).where(Operation.project_id == project_id))
    await db.execute(delete(Publication).where(Publication.project_id == project_id))
    await db.execute(
        delete(WorkflowStep).where(
            WorkflowStep.run_id.in_(
                select(WorkflowRun.id).where(WorkflowRun.project_id == project_id)
            )
        )
    )
    await db.execute(delete(Output).where(Output.project_id == project_id))
    await db.execute(delete(WorkflowRun).where(WorkflowRun.project_id == project_id))
    await db.execute(delete(Asset).where(Asset.project_id == project_id))
    persona_id = (
        await db.execute(select(Project.persona_id).where(Project.id == project_id))
    ).scalar_one_or_none()
    await db.execute(delete(Project).where(Project.id == project_id))
    await db.commit()
    if persona_id:
        await db.execute(delete(Persona).where(Persona.id == persona_id))
        await db.commit()
    print("cleanup done", flush=True)


def _keyframe_count(output: Output) -> int:
    spec = output.render_spec or {}
    return len(spec.get("crop_track") or [])


async def _harvest(db, project, card: str, keep: bool) -> None:
    """Reap the most reframe-active clip (max crop_track keyframes — the
    visible switch/follow story) + poster into demo/outputs, print the
    recipes.py ExampleOutput line."""
    # run COMPLETED ≠ renders landed: the render fan-out is claimed by the
    # worker's render loop AFTER run_finalized — ONE render per tick, so a
    # count=2 run's second MP4 lands tens of seconds after the first. Wait
    # until EVERY clip output carries files.video (the rows exist from select
    # time); a settle window would under-pick the first-rendered clip and the
    # "most keyframes" criterion would never see the rest.
    clips: list[Output] = []
    n_all = 0
    for _ in range(120):  # up to 10 min
        async with AsyncSessionLocal() as s:  # fresh session per poll — no stale identity map
            outputs = (
                await s.execute(
                    select(Output).where(Output.project_id == project.id).order_by(Output.created_at)
                )
            ).scalars().all()
            all_clips = [o for o in outputs if o.type == "clip"]
            failed = next(
                (o for o in all_clips if o.render_status == RenderStatus.FAILED), None
            )
            clips = [o for o in all_clips if (o.files or {}).get("video")]
            n_all = len(all_clips)
        # A FAILED render never gains files.video — surface the real error at
        # once instead of burning the full poll budget on "incomplete".
        if failed is not None:
            raise SystemExit(
                f"render FAILED on output {failed.id}: "
                f"{failed.render_error or 'no render_error recorded'}"
            )
        if n_all and len(clips) == n_all:
            break
        await asyncio.sleep(5)
    if not n_all:
        raise SystemExit("no clip outputs on the project — did select_clips run?")
    if len(clips) < n_all:
        raise SystemExit(f"renders incomplete: {len(clips)}/{n_all} clips rendered")
    best = max(clips, key=lambda o: (_keyframe_count(o), len(str(o.files))))
    print(
        f"harvest pick: output {best.id} — {_keyframe_count(best)} keyframes "
        f"of {len(clips)} clip(s)",
        flush=True,
    )
    mp4 = await read(best.files["video"])
    tmp = Path(tempfile.mkdtemp(prefix=f"bake-{card}-"))
    stem = CARDS[card]["output_stem"]
    (tmp / f"{stem}.mp4").write_bytes(mp4)
    poster = _poster_frame(mp4, 2.0)
    if poster:
        (tmp / f"{stem}-poster.jpg").write_bytes(poster)

    url = await _put_demo(stem, ".mp4", mp4, "video/mp4")
    poster_url = (
        await _put_demo(f"{stem}-poster", ".jpg", poster, "image/jpeg") if poster else None
    )
    print("\n--- recipes.py example_outputs ---")
    poster_field = f'poster_url="{poster_url}", ' if poster_url else ""
    print(
        f'ExampleOutput(kind="video", url="{url}", {poster_field}'
        f'label_key="{"reframe_output" if card == "reframe" else "follow_output"}"),'
    )
    print(f"\nlocal copy: {tmp} (run upload_recipe_assets.py to refresh the web manifest)")

    if not keep:
        await _cleanup(db, project.id)


async def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    card = args[0] if args else None
    if card not in CARDS:
        raise SystemExit(f"usage: bake_reframe_demos.py {'|'.join(CARDS)} [--keep] [--harvest <pid>]")
    cfg = CARDS[card]
    keep = "--keep" in sys.argv
    harvest_pid = (
        sys.argv[sys.argv.index("--harvest") + 1] if "--harvest" in sys.argv else None
    )

    async with AsyncSessionLocal() as db:
        if harvest_pid:
            project = await db.get(Project, harvest_pid)
            if project is None:
                raise SystemExit(f"project {harvest_pid} not found")
            # Ownership guard: _cleanup deletes the project's outputs, runs,
            # assets and mounted persona. On a typo'd / real-user pid that is
            # someone else's data. Refuse anything but our own bake user.
            owner = await db.get(User, project.user_id)
            if owner is None or owner.email != BAKE_EMAIL:
                raise SystemExit(
                    f"project {harvest_pid} does not belong to the bake user "
                    f"({BAKE_EMAIL}) — refusing to harvest/cleanup a real "
                    "user's project"
                )
            await _harvest(db, project, card, keep)
            return

        user = (
            await db.execute(select(User).where(User.email == BAKE_EMAIL))
        ).scalars().one_or_none()
        if user is None:
            user = User(email=BAKE_EMAIL, name="bake")
            db.add(user)
            await db.flush()
        persona = Persona(
            user_id=user.id,
            name="bake-demo-skin",
            language=cfg["language"],
            # PersonaContext.from_attributes turns NULL scalars into
            # validation failures — the style six need real values.
            sentence_style="简洁有力的口语短句。" if cfg["language"] == "zh" else "Short, punchy spoken-word sentences.",
            emotional_tone="rational",
            brand=dict(BAKE_BRAND),
        )
        db.add(persona)
        await db.flush()
        project = Project(
            user_id=user.id,
            title=f"bake: {card} demo",
            language=cfg["language"],
            status=ProjectStatus.DRAFT,
            persona_id=persona.id,
        )
        db.add(project)
        await db.flush()
        db.add(
            Asset(
                user_id=user.id,
                project_id=project.id,
                type=AssetType.VIDEO,
                file_url=cfg["source_key"],  # storage KEY, never the URL
                title=cfg["source_key"].rsplit("/", 1)[-1],
                processing_status=AssetStatus.PENDING,
            )
        )
        await db.commit()
        print(f"project {project.id} — waiting for ASR + speaker_map…", flush=True)

        await _wait_assets(project.id)
        print("assets ready — creating run…", flush=True)

        run = await create_run(
            db,
            project,
            TaskSpec(
                tasks=cfg["tasks"],
                target_language=cfg["language"],
                ui_language=cfg["language"],
                instruction=cfg["instruction"],
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

        await _harvest(db, project, card, keep)


if __name__ == "__main__":
    asyncio.run(main())
