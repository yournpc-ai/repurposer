"""MG D4 并发冒烟: 3 个 film 渲染并发跑一遍（绕过 LLM——压力目标是
Chrome/worker 并发不是模型）。fixture storyboard 复用 D2 的手写装配
（hand_storyboard，真实 capture manifest 接地），三个 run-less Output
同时 PENDING（NULL barrier → 即刻可被认领），活 worker 按
settings.render_concurrency 并发认领。

观察项: 并发认领深度 / 单渲染耗时 vs 串行基线（45.5s/26s 片 ≈1.75×实时）/
probe 闸在真实成功路径全过 / 临时文件清理（/tmp/repurposer-render-* +
probe 临时副本）/ worker 报错。

Run: uv run python scratch/mg_d4_concurrency_smoke.py
Requires: dev stack live, worker restarted on D4 code.
"""

import asyncio
import glob
import os
import sys
import time
from uuid import uuid4

sys.path.insert(0, "/Users/sylas/repurposer/apps/api")
sys.path.insert(0, "/Users/sylas/repurposer/scratch")

from sqlalchemy import select

from app.config import settings
from app.models.database import AsyncSessionLocal
from app.models.schemas import AssetStatus, AssetType, RenderStatus, WebPageResearch
from app.models.tables import Asset, Output
from app.providers.storage import delete, download_to_temp
from app.tools.film.storyboard import (
    StoryboardPage,
    allocate_frames,
    build_film_spec,
    validate_storyboard,
)
from mg_d2_fixture import hand_storyboard  # D2 fixture 装配复用

N_RENDERS = 3


def render_tmp_dirs() -> list[str]:
    return glob.glob(os.path.join(os.environ.get("TMPDIR", "/tmp"), "repurposer-render-*"))


async def pick_captured_page() -> tuple[StoryboardPage, object]:
    """Reuse ANY project's latest COMPLETED web_page capture (with paragraphs —
    the grounding universe needs them). Returns (page, project)."""
    async with AsyncSessionLocal() as db:
        assets = list(
            (
                await db.execute(
                    select(Asset)
                    .where(
                        Asset.type == AssetType.WEB_PAGE,
                        Asset.processing_status == AssetStatus.COMPLETED,
                    )
                    .order_by(Asset.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
    from urllib.parse import urlparse

    for a in assets:
        meta = a.meta or {}
        research_raw = meta.get("research") or {}
        if "paragraphs" not in research_raw:
            continue
        research = WebPageResearch.model_validate(research_raw)
        page = StoryboardPage(
            asset_id=str(a.id),
            research=research,
            screenshot_key=meta.get("screenshot_key"),
            host=urlparse(research.url).netloc,
        )
        return page, a.project_id
    raise AssertionError("no COMPLETED web_page capture with paragraphs in dev DB")


async def main() -> None:
    print(f"render_concurrency={settings.render_concurrency} "
          f"render_timeout={settings.render_timeout_seconds}s")
    tmp_before = set(render_tmp_dirs())
    print(f"render tmp dirs before: {len(tmp_before)}")

    page, project_id = await pick_captured_page()
    print(f"page: {page.host} (asset {page.asset_id}, project {project_id})")
    storyboard = hand_storyboard(page)
    violations = validate_storyboard(storyboard, [page])
    assert not violations, [f"{v.code}: {v.detail}" for v in violations]
    spec = build_film_spec(storyboard, [page])
    frames = allocate_frames(storyboard)
    seconds = sum(frames) / 30
    print(f"fixture storyboard: {len(storyboard.scenes)} scenes, "
          f"{sum(frames)} frames = {seconds:.1f}s")

    # Birth N run-less film outputs (NULL barrier → immediate claim). Object
    # keys derive from output id — distinct by construction.
    output_ids = []
    async with AsyncSessionLocal() as db:
        for _ in range(N_RENDERS):
            output = Output(
                project_id=project_id,
                workflow_step_id=None,
                type="film",
                language="en",
                provenance="generated",
                payload={
                    "name": f"mg-d4-smoke-{uuid4().hex[:6]}",
                    "duration": round(seconds),
                    "scene_count": len(storyboard.scenes),
                    "aspect": "16:9",
                },
                source_ref={"pages": [page.asset_id], "fixture": "mg_d4_smoke"},
                render_spec=spec,
                render_status=RenderStatus.PENDING,
            )
            db.add(output)
            await db.flush()
            output_ids.append(output.id)
        await db.commit()
    print(f"outputs pended: {[str(o)[:8] for o in output_ids]}")

    # Poll: track transitions (RENDERING start = concurrency depth evidence).
    t0 = time.time()
    rendering_since: dict[str, float] = {}
    completed_at: dict[str, float] = {}
    max_concurrent = 0
    deadline = t0 + 900
    while time.time() < deadline:
        async with AsyncSessionLocal() as db:
            rows = list(
                (await db.execute(select(Output).where(Output.id.in_(output_ids))))
                .scalars()
                .all()
            )
        now = time.time()
        in_flight = 0
        for r in rows:
            oid = str(r.id)
            if r.render_status == RenderStatus.RENDERING:
                rendering_since.setdefault(oid, now)
                in_flight += 1
            elif r.render_status == RenderStatus.COMPLETED and oid not in completed_at:
                completed_at[oid] = now
            elif r.render_status == RenderStatus.FAILED:
                raise AssertionError(f"render FAILED: {oid} {r.render_error}")
        max_concurrent = max(max_concurrent, in_flight)
        if len(completed_at) == N_RENDERS:
            break
        await asyncio.sleep(1.0)
    assert len(completed_at) == N_RENDERS, "timed out waiting for renders"
    total_wall = max(completed_at.values()) - t0

    # Probe each artifact (the gate already passed — this is the report line).
    print("\nresults:")
    for oid in output_ids:
        async with AsyncSessionLocal() as db:
            r = await db.get(Output, oid)
        key = (r.files or {}).get("video")
        path = await download_to_temp(key)
        import av

        with av.open(str(path)) as c:
            v = c.streams.video[0]
            dur = float(c.duration or 0) / 1e6
            meta = f"{v.codec_context.name} {v.codec_context.width}x{v.codec_context.height} {dur:.2f}s"
        size = path.stat().st_size
        path.unlink(missing_ok=True)
        start = rendering_since.get(str(oid), t0)
        print(f"  {str(oid)[:8]}: {meta} {size/1024:.0f}KB "
              f"render≈{completed_at[str(oid)] - start:.1f}s")

    serial_estimate = seconds * 1.75  # spike 基线 ≈1.75×实时
    print(f"\nwall: {total_wall:.1f}s for {N_RENDERS} renders "
          f"(serial estimate ≈{serial_estimate * N_RENDERS:.0f}s; "
          f"cap {settings.render_concurrency} ⇒ ideal ≈{serial_estimate * -(-N_RENDERS // settings.render_concurrency):.0f}s)")
    print(f"max concurrent RENDERING observed: {max_concurrent}")

    tmp_after = set(render_tmp_dirs())
    leaked = tmp_after - tmp_before
    print(f"render tmp dirs after: {len(tmp_after)} (leaked: {len(leaked)})")
    for d in leaked:
        print(f"  LEAKED: {d}")

    # Cleanup: rows + objects (the host project is NOT touched).
    async with AsyncSessionLocal() as db:
        for oid in output_ids:
            r = await db.get(Output, oid)
            key = (r.files or {}).get("video")
            await db.delete(r)
            if key:
                await delete(key)
        await db.commit()
    print("cleanup: rows + objects deleted")


asyncio.run(main())
