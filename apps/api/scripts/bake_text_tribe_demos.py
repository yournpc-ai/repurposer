"""Bake the text-tribe recipe demos (social-post / quote-cards / carousel)
through the REAL pipeline (2026-08-24 三卡点亮批).

Each card is one writer tool (write_post / write_quotes / write_carousel)
driven off the same source — demo/uploads/demo-article.md — and harvests
the writer's Output row into demo/outputs with content-hashed keys. The
quote-card additionally bakes the writer's first PNG (the run-time
`_save_quote_card_image` lands under the project's own output prefix —
the bake re-uploads it to the protected demo/ tree so the card points to
the shared demo/ root).

Each bake creates its own Project + Persona + Asset, runs the writer
through the live pipeline (worker does the LLM call + image generation),
then cleans up its scaffolding in FK order (the persistent BAKE_EMAIL
user is shared).

Usage:
    uv run python scripts/bake_text_tribe_demos.py social-post
    uv run python scripts/bake_text_tribe_demos.py quote-cards
    uv run python scripts/bake_text_tribe_demos.py carousel
    uv run python scripts/bake_text_tribe_demos.py all
    uv run python scripts/bake_text_tribe_demos.py <card> --harvest <project_id>

Requires the worker (dev.sh starts it). The bake project is deleted in FK
order afterwards unless --keep — on FAILURE the scaffolding leaks (the
project id is printed before the waits; rescue or wipe via `--harvest
<pid>`, which cleans up unless --keep).
"""

import asyncio
import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.schemas import (  # noqa: E402
    AssetStatus,
    AssetType,
    ProjectStatus,
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
from app.providers.storage import _get_s3_client, public_url, read  # noqa: E402
from app.config import settings  # noqa: E402

_DEMO = "https://repurposer.tos-ap-southeast-1.volces.com/demo"
ARTICLE_URL = f"{_DEMO}/uploads/demo-article.md"
ARTICLE_KEY = "demo/uploads/demo-article.md"
PREFIX = "demo/outputs"
IMMUTABLE = "public, max-age=31536000, immutable"
BAKE_EMAIL = "bake-text-tribe@local"

# The card-side prompt templates (the demo IS the card launch — i18n
# recipes.<id>.promptTemplate, zh source → card's prefilled text on launch;
# en is the locale the bake runs in so the LLM produces English copy).
CARDS = {
    "social-post": {
        "tool": "write_post",
        "tool_params": {"language": "en"},
        "instruction": (
            "Write a LinkedIn long-form post that reframes my keynote for "
            "a professional audience."
        ),
        "language": "en",
        "output_stem": "post",
        "label_key": "post_output",
        "kind": "image",  # overlay preview tile — JSON payload reads as a doc preview
        "needs_poster": False,
    },
    "quote-cards": {
        "tool": "write_quotes",
        "tool_params": {"language": "en", "count": 4},
        "instruction": (
            "Pull 4 shareable quote cards from my keynote — hook first, "
            "each standalone."
        ),
        "language": "en",
        "output_stem": "quotes",
        "label_key": "quotes_output",
        "kind": "image",
        "needs_poster": True,  # the writer's first-card PNG
    },
    "carousel": {
        "tool": "write_carousel",
        "tool_params": {"language": "en", "count": 6},
        "instruction": (
            "Turn my keynote into a 6-slide LinkedIn carousel — cover "
            "hook first, then the argument, CTA last."
        ),
        "language": "en",
        "output_stem": "carousel",
        "label_key": "carousel_output",
        "kind": "image",
        "needs_poster": False,
    },
}


async def _put_demo(stem: str, suffix: str, data: bytes, content_type: str) -> str:
    """Upload to the protected demo/ prefix with a content-hashed key."""
    digest = hashlib.md5(data).hexdigest()[:8]
    key = f"{PREFIX}/{stem}-{digest}{suffix}"
    client = _get_s3_client()
    await asyncio.to_thread(
        client.put_object,
        Bucket=settings.s3_bucket_name,
        Key=key,
        Body=data,
        ContentType=content_type,
        CacheControl=IMMUTABLE,
    )
    url = public_url(key)
    assert url is not None
    return url


async def _wait_run(run_id, timeout_s=900) -> WorkflowStatus:
    seen: dict[str, str] = {}
    for _ in range(timeout_s // 5):
        async with AsyncSessionLocal() as s:
            run = await s.get(WorkflowRun, run_id)
            status = run.status
            steps = (
                await s.execute(
                    select(WorkflowStep)
                    .where(WorkflowStep.run_id == run_id)
                    .order_by(WorkflowStep.seq)
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
    """FK-order wipe of the bake scaffolding (dev DB hygiene, matches
    bake_reframe_demos._cleanup: keep the BAKE_EMAIL User, drop the
    card's Persona)."""
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


async def _harvest(db, project, card: str, keep: bool) -> None:
    """Read the writer's Output row, upload JSON to demo/outputs (and the
    quote-card PNG when present), print the recipes.py ExampleOutput line."""
    cfg = CARDS[card]
    output_type = cfg["tool"].replace("write_", "")  # post / quotes / carousel
    async with AsyncSessionLocal() as s:
        outputs = (
            await s.execute(
                select(Output)
                .where(Output.project_id == project.id)
                .order_by(Output.created_at)
            )
        ).scalars().all()
    writers = [o for o in outputs if o.type == output_type]
    if not writers:
        raise SystemExit(
            f"no {output_type!r} output on project {project.id} — did the "
            "writer node run?"
        )
    if any(o.status != "generated" for o in writers):
        raise SystemExit(
            f"{output_type} output not generated: "
            f"{[(o.id, o.status) for o in writers]}"
        )
    out = writers[0]
    payload = out.payload or {}
    json_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    tmp = Path(tempfile.mkdtemp(prefix=f"bake-text-tribe-{card}-"))
    (tmp / f"{cfg['output_stem']}.json").write_bytes(json_bytes)
    url = await _put_demo(cfg["output_stem"], ".json", json_bytes, "application/json")
    print(f"harvested JSON {len(json_bytes)} bytes from output {out.id}", flush=True)

    poster_url: str | None = None
    if cfg["needs_poster"]:
        # files.image is the public URL (output_url() wraps the key at write
        # time, N-30 storage seam); read() needs a bare key — strip the
        # public URL prefix.
        raw_image = (out.files or {}).get("image")
        if not raw_image:
            raise SystemExit(
                f"quote-cards needs the writer's first-card PNG, but output "
                f"{out.id} has no files.image — image generation failed"
            )
        public_prefix = (settings.s3_public_url or "").rstrip("/") + "/"
        image_key = raw_image[len(public_prefix):] if raw_image.startswith(public_prefix) else raw_image
        # The writer's PNG was saved to the project's output prefix (not
        # demo/) — copy it under demo/outputs/<stem>-poster-<hash>.png so
        # the gallery card points at the shared demo root (the recipe
        # asset layer).
        png = await read(image_key)
        (tmp / f"{cfg['output_stem']}-poster.png").write_bytes(png)
        poster_url = await _put_demo(
            f"{cfg['output_stem']}-poster", ".png", png, "image/png"
        )
        print(f"harvested PNG {len(png)} bytes from {image_key}", flush=True)

    print("\n--- recipes.py example_outputs ---")
    poster_field = f'poster_url="{poster_url}", ' if poster_url else ""
    print(
        f'ExampleOutput(kind="{cfg["kind"]}", url="{url}", {poster_field}'
        f'label_key="{cfg["label_key"]}"),'
    )
    print(f"\nlocal copy: {tmp}")

    if not keep:
        await _cleanup(db, project.id)


async def _bake_one(card: str, keep: bool) -> None:
    """Run one card's writer through the live pipeline and harvest."""
    cfg = CARDS[card]
    async with AsyncSessionLocal() as db:
        article = (await httpx.AsyncClient().get(ARTICLE_URL)).text
        if len(article) < 100:
            raise SystemExit(f"article fetch looks wrong ({len(article)} bytes)")

        user = (
            await db.execute(select(User).where(User.email == BAKE_EMAIL))
        ).scalars().one_or_none()
        if user is None:
            user = User(email=BAKE_EMAIL, name="bake-text-tribe")
            db.add(user)
            await db.flush()

        persona = Persona(
            user_id=user.id,
            name=f"bake-text-tribe-{card}",
            language=cfg["language"],
            sentence_style=(
                "Short, punchy spoken-word sentences."
                if cfg["language"] == "en"
                else "简洁有力的口语短句。"
            ),
            emotional_tone="rational",
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
        # Text-tribe pre-fills the transcript status — no ASR pipeline runs
        # (mirror of bake_image_video_demo's transcript setup).
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
        await db.commit()
        print(f"project {project.id} — assets pre-filled, creating run…", flush=True)

        run = await create_run(
            db,
            project,
            TaskSpec(
                tasks=[{"tool": cfg["tool"], "params": cfg["tool_params"]}],
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


async def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    card = args[0] if args else None
    keep = "--keep" in sys.argv
    harvest_pid = (
        sys.argv[sys.argv.index("--harvest") + 1] if "--harvest" in sys.argv else None
    )

    targets = list(CARDS) if card in (None, "all") else [card]
    if card not in (None, "all") and card not in CARDS:
        raise SystemExit(
            f"usage: bake_text_tribe_demos.py [{'|'.join(CARDS)}|all] "
            "[--keep] [--harvest <pid>]"
        )

    for one in targets:
        if harvest_pid:
            async with AsyncSessionLocal() as db:
                project = await db.get(Project, harvest_pid)
                if project is None:
                    raise SystemExit(f"project {harvest_pid} not found")
                owner = await db.get(User, project.user_id)
                if owner is None or owner.email != BAKE_EMAIL:
                    raise SystemExit(
                        f"project {harvest_pid} does not belong to the bake "
                        f"user ({BAKE_EMAIL}) — refusing to harvest/cleanup "
                        "a real user's project"
                    )
                await _harvest(db, project, one, keep)
            return
        print(f"\n========== baking {one} ==========", flush=True)
        await _bake_one(one, keep)


if __name__ == "__main__":
    asyncio.run(main())
