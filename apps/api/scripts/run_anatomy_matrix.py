"""Anatomy matrix runner (产物质量线 期 0): run every live recipe card once
against the curated demo/uploads materials through the REAL pipeline, then
anatomize every rendered clip (scripts/craft_anatomy.py) and dump the
four-layer evidence （数据 / 决策者 / 契约 / 渲染) per run.

The matrix (one run per live card, honest default skin — no bake brand pin):
- subs          multilingual-subs card: xy_2_15s → translate zh bilingual +
                translate fr + dub es (all fork) — the caption family
- image-video   图文视频 card: demo-article.md + 3 teaser photos →
                select_clips + add_music — the stills family
- highlight     演讲短片 card: xy_2.mp4 FULL (780 s keynote) → select_clips +
                reframe_clip auto — long-footage picking is the point
- reframe       访谈分镜 card: xy_1.mp4 FULL interview → select_clips +
                reframe_clip auto

Every run is deleted afterwards in FK order unless --keep (验证 run 用完即清,
常驻 worker 抢跑纪律). Requires API-independent: worker + render service up.

Usage:
    uv run python scripts/run_anatomy_matrix.py [card ...] [--keep] [--report dir]
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select  # noqa: E402

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
    Output,
    Persona,
    Project,
    User,
    WorkflowStep,
)
from app.pipeline.orchestrator import TaskSpec, create_run  # noqa: E402
from bake_reframe_demos import _cleanup, _wait_assets, _wait_run  # noqa: E402
from craft_anatomy import ClipCase, anatomize  # noqa: E402
from app.providers.storage import download_to_temp  # noqa: E402

ANATOMY_EMAIL = "anatomy@local"

CARDS = {
    "subs": {
        "title": "anatomy: multilingual-subs",
        "language": "en",
        "assets": [("demo/uploads/xy_2_15s.mp4", AssetType.VIDEO)],
        "tasks": [
            {"tool": "translate_clip", "params": {"target_language": "zh", "bilingual": True, "fork": True}},
            {"tool": "translate_clip", "params": {"target_language": "fr", "fork": True}},
            {"tool": "dub_clip", "params": {"target_language": "es", "fork": True}},
        ],
        "instruction": "Add bilingual Chinese-English captions and French captions to my video, and dub one version in Spanish with my voice.",
    },
    "image-video": {
        "title": "anatomy: image-video",
        "language": "en",
        "assets": [
            ("demo/uploads/demo-article.md", AssetType.TRANSCRIPT),
            ("demo/uploads/teasers-photo-title.jpg", AssetType.IMAGE),
            ("demo/uploads/teasers-photo-industries.jpg", AssetType.IMAGE),
            ("demo/uploads/teasers-photo-outcomes.jpg", AssetType.IMAGE),
        ],
        "tasks": [
            {"tool": "select_clips", "params": {"aspect": "16:9"}},
            {"tool": "add_music", "params": {"mood": "calm"}},
        ],
        "instruction": "Turn my write-up and photos into a short subtitled slideshow video with music.",
    },
    "highlight": {
        "title": "anatomy: highlight-clips",
        "language": "en",
        "assets": [("demo/uploads/xy_2.mp4", AssetType.VIDEO)],
        "tasks": [
            {"tool": "select_clips", "params": {"count": 3}},
            {"tool": "reframe_clip", "params": {"mode": "auto"}},
        ],
        "instruction": "Find the best moments of this keynote and cut them into vertical clips — the camera follows the speaker.",
    },
    "reframe": {
        "title": "anatomy: reframe (interview)",
        "language": "zh",
        "assets": [("demo/uploads/xy_1.mp4", AssetType.VIDEO)],
        "tasks": [
            {"tool": "select_clips", "params": {"count": 3}},
            {"tool": "reframe_clip", "params": {"mode": "auto"}},
        ],
        "instruction": "把我的双人访谈剪成竖屏短片，镜头跟着说话人切换。",
    },
}


async def _wait_renders(project_id, timeout_s=1800) -> list[Output]:
    """run COMPLETED ≠ renders landed (one render claimed per worker tick)."""
    for _ in range(timeout_s // 5):
        async with AsyncSessionLocal() as s:
            outputs = (
                await s.execute(
                    select(Output).where(Output.project_id == project_id).order_by(Output.created_at)
                )
            ).scalars().all()
            clips = [o for o in outputs if o.type == "clip"]
            done = [o for o in clips if (o.files or {}).get("video")]
            failed = next((o for o in clips if o.render_status == RenderStatus.FAILED), None)
        if failed is not None:
            raise SystemExit(f"render FAILED on output {failed.id}: {failed.render_error}")
        if clips and len(done) == len(clips):
            return done
        await asyncio.sleep(5)
    raise SystemExit("renders timed out")


async def _dump_decision_layer(project_id) -> dict:
    """决策者层: understanding / storyboard / clip plans as the LLM wrote them."""
    async with AsyncSessionLocal() as s:
        outputs = (
            await s.execute(select(Output).where(Output.project_id == project_id))
        ).scalars().all()
    decision: dict[str, object] = {}
    for o in outputs:
        if o.type == "material_understanding":
            decision["understanding"] = o.payload
        elif o.type == "storyboard":
            decision["storyboard"] = o.payload
    decision["clip_payloads"] = [
        {
            "output_id": str(o.id),
            "language": o.language,
            "payload": o.payload,
            "source_ref": o.source_ref,
            "score": o.score,
        }
        for o in outputs
        if o.type == "clip"
    ]
    return decision


async def _anatomize_outputs(clips: list[Output], frames_root: Path, label_prefix: str) -> list[dict]:
    reports: list[dict] = []
    for o in clips:
        spec = o.render_spec or {}
        mp4 = await download_to_temp((o.files or {})["video"])
        assert mp4 is not None
        words: list[dict] = []
        asset_id = (spec.get("source") or {}).get("asset_id")
        async with AsyncSessionLocal() as s:
            if asset_id:
                from uuid import UUID

                asset = await s.get(Asset, UUID(str(asset_id)))
                if asset is not None:
                    words = (asset.meta or {}).get("words") or []
        case = ClipCase(
            label=f"{label_prefix}-{str(o.id)[:8]}",
            mp4_path=mp4,
            spec=spec,
            words=words,
            meta={"output_id": str(o.id), "language": o.language, "type": o.type},
        )
        reports.append(anatomize(case, frames_root, frame_fps=1.0))
        mp4.unlink(missing_ok=True)
    return reports


async def _run_card(card: str, cfg: dict, report_dir: Path, keep: bool) -> dict:
    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.email == ANATOMY_EMAIL))
        ).scalars().one_or_none()
        if user is None:
            user = User(email=ANATOMY_EMAIL, name="anatomy")
            db.add(user)
            await db.flush()
        persona = Persona(
            user_id=user.id,
            name="anatomy-default",
            language=cfg["language"],
            sentence_style="Short, punchy spoken-word sentences.",
            emotional_tone="rational",
            brand=None,  # honest default skin — the anatomy judges what users get
        )
        db.add(persona)
        await db.flush()
        project = Project(
            user_id=user.id,
            title=cfg["title"],
            language=cfg["language"],
            status=ProjectStatus.DRAFT,
            persona_id=persona.id,
        )
        db.add(project)
        await db.flush()
        for key, atype in cfg["assets"]:
            db.add(
                Asset(
                    user_id=user.id,
                    project_id=project.id,
                    type=atype,
                    file_url=key,
                    title=key.rsplit("/", 1)[-1],
                    processing_status=AssetStatus.PENDING,
                )
            )
        await db.commit()
        project_id = project.id
        print(f"[{card}] project {project_id} — waiting for asset processing…", flush=True)

    await _wait_assets(project_id, timeout_s=1800)
    print(f"[{card}] assets ready — creating run…", flush=True)

    async with AsyncSessionLocal() as db:
        project = await db.get(Project, project_id)
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
        run_id = run.id
        print(f"[{card}] run {run_id}", flush=True)

    status = await _wait_run(run_id, timeout_s=3600)
    if status != WorkflowStatus.COMPLETED:
        raise SystemExit(f"[{card}] run ended {status.value}")
    async with AsyncSessionLocal() as db:
        project = await db.get(Project, project_id)
        project.status = ProjectStatus.COMPLETED
        await db.commit()

    clips = await _wait_renders(project_id)
    print(f"[{card}] {len(clips)} clip(s) rendered — anatomizing…", flush=True)

    decision = await _dump_decision_layer(project_id)
    clip_reports = await _anatomize_outputs(clips, report_dir / "frames", card)

    evidence = {
        "card": card,
        "project_id": str(project_id),
        "run_id": str(run_id),
        "decision_layer": decision,
        "clips": clip_reports,
    }

    if not keep:
        async with AsyncSessionLocal() as db:
            await _cleanup(db, project_id)
        print(f"[{card}] cleaned up", flush=True)
    return evidence


async def main() -> None:
    argv = sys.argv[1:]
    keep = "--keep" in argv
    report_dir = Path("data/anatomy")
    if "--report" in argv:
        report_dir = Path(argv[argv.index("--report") + 1])
        del argv[argv.index("--report") : argv.index("--report") + 2]
    args = [a for a in argv if not a.startswith("--")]
    report_dir.mkdir(parents=True, exist_ok=True)

    cards = args or list(CARDS)
    for c in cards:
        if c not in CARDS:
            raise SystemExit(f"unknown card {c} — pick from {list(CARDS)}")

    all_evidence = []
    for c in cards:
        evidence = await _run_card(c, CARDS[c], report_dir, keep)
        all_evidence.append(evidence)
        out = report_dir / f"{c}.json"
        out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str))
        print(f"[{c}] evidence → {out}", flush=True)

    print("\nALL CARDS DONE", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
