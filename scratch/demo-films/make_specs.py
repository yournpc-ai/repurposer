"""Demo film production (ADR-122 验收锚): fresh-capture zymix.ai through the
playwright engine (fold + section shots + element inventory + sub-page
discovery), storyboard a 75–95s pillar walk against the camera-target table
(pillar iteration arc, plate numbers beats, mixed framed/full-bleed ui),
snap scene boundaries to the calm bed's beat grid (B3), synthesize narration
on the SNAPPED windows, then emit three ABSOLUTIZED film-specs
(16:9 / 1:1 / 9:16) to scratch/demo-films/specs/. The render half
(render_films.ts) turns them into MP4s with the real renderer.

Offline by design: no Output rows, no runs — nothing to clean in the DB.
Shot PNGs and narration objects land under the source project's output
prefix. The demo lane mirrors production seats exactly (capture_page →
StoryboardPage → orchestrate → snap → narration → build_film_spec) — only
the DB asset/run rows are skipped.
"""

import asyncio
import json
import sys
import uuid
from pathlib import Path

# The script lives outside the api package — put apps/api on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api"))

OUT = Path(__file__).parent / "specs"
PROJECT_ID = uuid.UUID("9efdd699-3fcd-4983-9373-441557cfe507")  # S11 capture
URL = "https://www.zymix.ai/en/"
EXTRA_PAGES = 2  # B4 discovered sub-pages join the grounding universe


async def main() -> None:
    from app.models.database import AsyncSessionLocal
    from app.models.schemas import PageElement, ShotRef
    from app.models.tables import Project
    from app.providers.storage import (
        get_project_output_dir,
        public_url,
        read,
        save,
    )
    from app.memory.brand import resolve_music_ref
    from app.pipeline.music import music_file_path
    from app.tools.music.beats import analyze_beat_grid
    from app.tools.film.narration import (
        DEFAULT_FILM_VOICE_ID,
        synthesize_film_narration,
    )
    from app.tools.film.storyboard import (
        FilmStoryboardRejected,
        StoryboardPage,
        allocate_frames,
        build_film_spec,
        orchestrate_storyboard,
        page_media_inputs,
        snap_frames_to_beats,
    )
    from app.tools.research.capture import capture_page

    async with AsyncSessionLocal() as db:
        project = await db.get(Project, PROJECT_ID)
        if project is None:
            raise SystemExit(f"anchor project {PROJECT_ID} gone — pick a live one")
        out_dir = get_project_output_dir(project.id, project.user_id)

        # B1/B2/B4: fresh captures through the playwright engine — fold +
        # section shots with element inventories; the main page's discovery
        # feeds up to EXTRA_PAGES sub-pages into the grounding universe
        # (multi-page walk, the reference film's shape). Shot PNGs persist
        # under the demo project's prefix (storage-relative keys).
        async def capture_one(url: str, tag: str) -> tuple[StoryboardPage | None, list[str]]:
            outcome = await capture_page(url)
            if not outcome.shots:
                print(f"capture degraded to no shots for {url} — skipped")
                return None, []
            refs: list[ShotRef] = []
            for i, shot in enumerate(outcome.shots):
                key = f"{out_dir}/demo-film-{tag}-s{i}.png"
                await save(key, shot.png, content_type="image/png")
                refs.append(
                    ShotRef(
                        key=key,
                        y=shot.y,
                        heading=shot.heading,
                        elements=[PageElement.model_validate(e) for e in shot.elements],
                    )
                )
            print(
                f"capture {tag}: {len(refs)} shots, "
                f"elements={[len(s.elements) for s in refs]}, "
                f"discovered={outcome.discovered}"
            )
            from urllib.parse import urlparse

            return StoryboardPage(
                asset_id=f"demo-{tag}",
                research=outcome.research,
                screenshot_key=refs[0].key,
                host=urlparse(url).netloc,
                shots=tuple(refs),
            ), outcome.discovered

        main_page, discovered = await capture_one(URL, "p0")
        if main_page is None:
            raise SystemExit("main capture degraded — cannot demo")
        pages = [main_page]
        for i, sub in enumerate(discovered[:EXTRA_PAGES]):
            child, _ = await capture_one(sub, f"p{i + 1}")
            if child is not None:
                pages.append(child)
        print(f"pages: {[p.research.url for p in pages]}")

        page_images = await page_media_inputs(pages)

        # The bounded loop (3 candidates) already echoes violations; the
        # demo lane re-enters the loop instead of dying on the first
        # rejection (DURATION_INVALID exhaustion precedent).
        storyboard = None
        for outer in range(3):
            try:
                storyboard = await orchestrate_storyboard(
                    pages=pages,
                    instruction=(
                        "A polished launch film of the site, 75-95 seconds — "
                        "cold-open on the page's strongest line, hero the brand, "
                        "then walk the pillars one by one: a numbered divider, "
                        "the ui evidence for that pillar (ride the section shots "
                        "and name element ids for the camera), and a plate for "
                        "any real numbers the page carries. Mix framed and "
                        "full-bleed ui scenes. Close with a reveal callback and "
                        "the end card. Narration on the story-bearing scenes."
                    ),
                    focus=None,
                    page_images=page_images,
                )
                break
            except FilmStoryboardRejected as exc:
                print(f"storyboard rejected (outer {outer + 1}/3): {exc}")
        assert storyboard is not None, "storyboard rejected after 3 loops"
        frames = allocate_frames(storyboard)
        print(
            f"storyboard: {storyboard.name} — {len(storyboard.scenes)} scenes, "
            f"{sum(frames) / 30:.0f}s"
        )
        for i, s in enumerate(storyboard.scenes):
            extra = ""
            if s.type == "ui":
                extra = (
                    f" page={s.page} shot={s.shot} frame={s.frame} "
                    f"focuses={[f.element or 'xyz' for f in s.focuses]}"
                )
            elif s.type == "plate":
                extra = f" cards={[c.big for c in s.cards]}"
            print(
                f"  [{i}] {s.type} {s.seconds}s "
                f"narr={bool(getattr(s, 'narration', None))}{extra}"
            )

        # B3: snap scene boundaries to the calm bed's beat grid. Production
        # reads track.meta (seed/reconcile seat); the demo lane computes the
        # grid in-script when the row predates it — same analyzer.
        track = await resolve_music_ref(db, "calm")
        beats: list[float] | None = None
        if track is not None:
            raw = (track.meta or {}).get("beats")
            if isinstance(raw, list) and raw:
                beats = [float(b) for b in raw]
            else:
                grid = analyze_beat_grid(await read(track.file_path))
                beats = grid["beats"] if grid else None
        if beats:
            frames = snap_frames_to_beats(storyboard, frames, beats)
            print(f"beat-snapped: {len(beats)} beats, frames={frames}")
        total = sum(frames) / 30
        print(f"total: {total:.1f}s")

        narration = await synthesize_film_narration(
            output_id=uuid.uuid4(),
            project=project,
            storyboard=storyboard,
            frames=frames,
            voice_id=DEFAULT_FILM_VOICE_ID,
            language="en",
        )
        print(f"narration scenes: {sorted(narration)}")
        print(f"music: {track.title if track else None}")

        OUT.mkdir(parents=True, exist_ok=True)
        for aspect in ("16:9", "1:1", "9:16"):
            # Fresh dict per aspect — build_film_spec embeds the reference,
            # so reusing one dict would double-absolutize the URL on later
            # iterations (1x1/9x16 曾踩).
            music = {"url": music_file_path(track.id), "gain_db": -20.0} if track else None
            spec = build_film_spec(
                storyboard, pages, narration=narration, music=music,
                aspect=aspect, frames=frames,
            )
            # Absolutize every storage-relative URL (the offline path skips
            # pipeline/rendering.py's seam — same law, same function shape).
            for scene in spec["scenes"]:
                for key in ("image", "logo_url", "audio"):
                    if isinstance(scene.get(key), str):
                        scene[key] = public_url(scene[key]) or scene[key]
            if spec.get("music"):
                spec["music"]["url"] = public_url(spec["music"]["url"])
            out = OUT / f"film-{aspect.replace(':', 'x')}.json"
            out.write_text(json.dumps(spec, ensure_ascii=False, indent=1))
            print(f"wrote {out}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
