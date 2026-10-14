"""MG D2 fixture chain: hand-written storyboard → validator → render service →
artifact probe. The LLM is NOT in this leg — the storyboard is hand-picked
from the real capture manifest so the full chain (web_page asset → capture →
spec → render → MP4) proves green before the model is wired in.

Run: uv run python scratch/mg_d2_fixture.py
Requires: dev stack live (API :8000 / render :3001 / worker with D2 code).
Real-site verification uses github.com only (example.com is DNS-polluted on
this network).
"""

import asyncio
import re
import sys
import time

sys.path.insert(0, "/Users/sylas/repurposer/apps/api")

from sqlalchemy import select

from app.models.database import AsyncSessionLocal
from app.models.schemas import (
    AssetStatus,
    AssetType,
    FilmStoryboard,
    RenderStatus,
    WebPageResearch,
)
from app.models.tables import Asset, Output, Project
from app.pipeline.assets import create_web_page_assets_from_urls
from app.tools.film.storyboard import (
    StoryboardPage,
    allocate_frames,
    build_film_spec,
    validate_storyboard,
)

CAPTURE_URL = "https://github.com"


async def pick_project(db) -> Project:
    project = (
        await db.execute(select(Project).order_by(Project.created_at.desc()).limit(1))
    ).scalar_one_or_none()
    assert project is not None, "no project in dev DB"
    return project


async def wait_capture(asset_id, timeout=420) -> Asset:
    # A fresh session per poll — a long-lived session's identity map serves
    # stale rows here (the worker commits from its own sessions).
    deadline = time.time() + timeout
    while time.time() < deadline:
        async with AsyncSessionLocal() as db:
            asset = await db.get(Asset, asset_id)
            if asset.processing_status == AssetStatus.COMPLETED:
                return asset
            if asset.processing_status == AssetStatus.FAILED:
                raise AssertionError(f"capture FAILED: {asset.processing_error}")
        await asyncio.sleep(3)
    raise AssertionError("capture timed out")


def pick_page(asset: Asset) -> StoryboardPage:
    meta = asset.meta or {}
    research = WebPageResearch.model_validate(meta["research"])
    from urllib.parse import urlparse

    return StoryboardPage(
        asset_id=str(asset.id),
        research=research,
        screenshot_key=meta.get("screenshot_key"),
        host=urlparse(research.url).netloc,
    )


def hand_storyboard(page: StoryboardPage) -> FilmStoryboard:
    """Compose a storyboard ENTIRELY from manifest strings (the LLM's future
    seat — here a human hand, proving the validator's ground rules against a
    real capture)."""
    r = page.research

    def fit(candidates, cap):
        for c in candidates:
            if c and len(c) <= cap:
                return c
        return None

    corpus = [r.title, r.description, *r.h1, *r.h2, *r.h3, *r.buttons, *r.links]
    title_segs = [s.strip() for s in re.split(r"[·—:|]", r.title) if s.strip()]
    hero_word = fit(
        [*r.h1, *title_segs, *r.h2, *r.buttons, *r.links], 16
    )
    hero_sub = fit([r.description, *r.h2], 90)
    lines = [c for c in [*r.h2, *r.h3, *r.buttons] if c and len(c) <= 30][:3]
    captions = [c for c in [*r.h2, *r.buttons] if c and len(c) <= 60][:2]
    tagline = fit([r.description, r.title, *r.h1], 90)
    name = fit([*title_segs, *r.h1, *r.buttons], 24)
    assert hero_word and hero_sub and len(lines) >= 1 and tagline and name, (
        f"manifest too thin for a fixture storyboard: {corpus}"
    )
    scenes = [
        {"type": "hero", "seconds": 3.0, "word": hero_word, "sub": hero_sub},
        {"type": "words", "seconds": 3.0, "dark": False, "lines": lines},
    ]
    if page.screenshot_key:
        scenes.append(
            {
                "type": "ui",
                "seconds": 6.0,
                "page": 0,
                "focuses": [
                    {"at": 0.0, "x": 0.5, "y": 0.5, "zoom": 1.0},
                    {"at": 2.0, "x": 0.5, "y": 0.35, "zoom": 1.6},
                ],
                "captions": [
                    {"at": i * 2.0, "text": c} for i, c in enumerate(captions)
                ],
            }
        )
    scenes.append({"type": "end", "seconds": 3.5, "name": name, "tagline": tagline})
    return FilmStoryboard.model_validate({"name": None, "scenes": scenes})


async def wait_render(output_id, timeout=600) -> Output:
    deadline = time.time() + timeout
    while time.time() < deadline:
        async with AsyncSessionLocal() as db:
            output = await db.get(Output, output_id)
            if output.render_status == RenderStatus.COMPLETED:
                return output
            if output.render_status == RenderStatus.FAILED:
                raise AssertionError(f"render FAILED: {output.render_error}")
        await asyncio.sleep(4)
    raise AssertionError("render timed out")


async def main():
    async with AsyncSessionLocal() as db:
        project = await pick_project(db)
        print(f"project: {project.id} ({project.title!r})")

        # 1. Capture (the D1 chain, real site) — reuse a ready capture of the
        # same URL when the project already has one (the absorb path's own
        # dedupe law).
        existing = (
            await db.execute(
                select(Asset).where(
                    Asset.project_id == project.id,
                    Asset.type == AssetType.WEB_PAGE,
                    Asset.processing_status == AssetStatus.COMPLETED,
                )
            )
        ).scalars().all()
        asset = next(
            (
                a
                for a in existing
                if (a.meta or {}).get("capture_url") == CAPTURE_URL
                # Pre-paragraphs captures ground only headings/buttons — the
                # validator's universe needs the paragraph inventory.
                and "paragraphs" in ((a.meta or {}).get("research") or {})
            ),
            None,
        )
        if asset is None:
            [asset] = await create_web_page_assets_from_urls(
                db, project.id, project.user_id, [CAPTURE_URL]
            )
            await db.commit()
            print(f"web_page asset: {asset.id} — capturing…")
            asset = await wait_capture(asset.id)
        else:
            print(f"web_page asset: {asset.id} — already captured, reusing")
        page = pick_page(asset)
        print(
            f"captured: title={page.research.title[:60]!r} "
            f"h1={page.research.h1[:2]} buttons={page.research.buttons[:3]} "
            f"screenshot={'yes' if page.screenshot_key else 'NO'}"
        )

        # 2. Hand storyboard → validator.
        storyboard = hand_storyboard(page)
        violations = validate_storyboard(storyboard, [page])
        if violations:
            for v in violations:
                print(f"  VIOLATION {v.code}: {v.detail}")
            raise AssertionError("hand storyboard failed the validator")
        print("validator: clean")

        # 3. Frames + spec.
        frames = allocate_frames(storyboard)
        spec = build_film_spec(storyboard, [page])
        total = sum(frames)
        print(f"frames: {frames} (total {total} = {total / 30:.1f}s)")

        # 4. Birth the film output run-less (NULL barrier → immediate claim)
        #    and let the REAL worker render chain take it. A previous fixture
        #    run's COMPLETED row is reused — re-rendering the identical spec
        #    proves nothing new.
        output = (
            await db.execute(
                select(Output)
                .where(
                    Output.project_id == project.id,
                    Output.type == "film",
                    Output.render_status == RenderStatus.COMPLETED,
                )
                .order_by(Output.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if (
            output is not None
            and (output.source_ref or {}).get("fixture") == "mg_d2"
            and output.render_spec == spec  # same storyboard only — a changed
            # spec (new manifest coverage) must actually render
        ):
            print(f"output: {output.id} — already rendered, reusing")
        else:
            output = Output(
                project_id=project.id,
                workflow_step_id=None,
                type="film",
                language="en",
                provenance="generated",
                payload={
                    "name": storyboard.name or "",
                    "duration": round(total / 30),
                    "scene_count": len(storyboard.scenes),
                    "aspect": "16:9",
                },
                source_ref={"pages": [page.asset_id], "fixture": "mg_d2"},
                render_spec=spec,
                render_status=RenderStatus.PENDING,
            )
            db.add(output)
            await db.commit()
            print(f"output: {output.id} — rendering via worker…")
            output = await wait_render(output.id)
            print(f"render COMPLETED: {(output.files or {}).get('video')}")
        video_key = (output.files or {}).get("video")

        # 5. Probe the artifact (PyAV — the repo's ffmpeg discipline: no
        # system binary assumed).
        from app.providers.storage import download_to_temp

        path = await download_to_temp(video_key)
        assert path is not None, "video key unreadable from storage"
        import av

        container = av.open(str(path))
        stream = next(s for s in container.streams if s.type == "video")
        duration = float(container.duration or 0) / 1_000_000
        codec = stream.codec_context.name
        width, height = stream.codec_context.width, stream.codec_context.height
        container.close()
        expected = total / 30
        print(
            f"probe: {codec} {width}x{height} "
            f"{duration:.2f}s (expected ≈{expected:.2f}s)"
        )
        assert codec == "h264", codec
        assert (width, height) == (1920, 1080)
        assert abs(duration - expected) < 1.0, (duration, expected)
        print("PROBE GREEN — fixture chain passed end to end")


if __name__ == "__main__":
    asyncio.run(main())
