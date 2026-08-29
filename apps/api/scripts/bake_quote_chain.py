"""Bake the quote-cards v3 example matrix (RECIPES §4.6.2 + 简报 §3 P3):
four static composite PNGs + one curated stage photo, content-addressed
into the protected demo/ tree, replacing the retired 形态 C (frame-wall)
v9 example.

The matrix (宽槽三路径 × 两形态 — one tile per cell the overlay shows):

1. **形态 A / Speaker layout** — the VIDEO run's real chain (the writer
   picks the quotes, the translator fills ``quote_alt``) composed with
   the curated stage photo as the speaker region (``image_bytes=[stage]``
   + ``speaker_form=True``) — the flagship "keynote + best event photo"
   combo. The photo guarantees a strong speaker region; the production
   span-pick is at the mercy of wherever chain[0] lands (xy_2's quoted
   windows are slide-heavy, which is why the writer's verdict on this
   video is usually False).
2. **形态 B / Full-bleed layout** — the same video chain composed
   ``speaker_form=False`` with the video bytes: full-bleed dimmed frame
   + centred lines.
3. **照片底 / Photo + transcript** — the TEXT run's real chain
   (demo-article.md) composed with the stage photo.
4. **纯文稿 / Transcript only** — the same text chain with no images at
   all → the dark branch (never clamped).

Tiles are PINNED BY CONSTRUCTION — the compositor IS the product path,
only the form choice is pinned; the writer's ``needs_speaker_frame``
verdict is printed for information but never awaited (a demo matrix
cannot ride on LLM mood).

The stage photo = whole-talk YuNet best-face sweep + a face-anchored
9:8 landscape crop (xy_2 is wide-stage material; users crop their event
photos too). Same engine/scoring as the production span pick — max face
area, sharpness tie-break — but denser and unbound from any quote
window: it stands in for the user's best event photo, an INPUT asset.

Harvested chains are also saved as ``chain-*.json`` so a re-compose
(e.g. a different crop) never needs a pipeline re-run.

Attribution rails: the scaffold persona/event are what the writer puts
on the card (it reads them verbatim) — "Prof. Xu / Future Tech Summit",
never bake-scaffolding names.

主产物 = 静态 PNG（v3 §2.6：MP4 是 motion 衍生品，永不上卡面）——
示例集零 MP4。

**No 63MB re-upload**: the video already lives at
``demo/uploads/xy_2.mp4`` (public, content-stable). The bake downloads
it once, ASRs inline (same provider code the worker runs — the upload
journey is UX plumbing, not product), and fixtures the Asset row at
COMPLETED. Direct TOS PUTs from this dev box are throttled to a stall
(WriteTimeout) and the local proxy drops long bodies (ReadError) —
fixture-in-place is deterministic and minutes faster.

Each run is followed by a family-count assertion (verify-bounce sweep
regression smoke — 2026-08-28 root-fix in derivative_dispatch: a bounce
re-runs the SAME WorkflowStep row and its prior products must die):
exactly one quotes row + one chain composite per project.

Usage:
    uv run python scripts/bake_quote_chain.py          # full matrix
    uv run python scripts/bake_quote_chain.py --keep   # skip FK cleanup

Prereqs: worker running (dev.sh) for the two create_run chains; the ASR
model cache warm (any prior video upload warmed it).
"""
import argparse
import asyncio
import hashlib
import io
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx  # noqa: E402

from sqlalchemy import delete, select, text  # noqa: E402

from app.config import settings  # noqa: E402
from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.schemas import (  # noqa: E402
    AssetStatus,
    AssetType,
    ProjectStatus,
    WorkflowStatus,
)
from app.models.tables import (  # noqa: E402
    Asset,
    Output,
    Persona,
    Project,
    Publication,
    User,
    WorkflowRun,
    WorkflowStep,
)
from app.pipeline.derivative_dispatch import (  # noqa: E402
    _chain_captions,
    _compose_chain_pngs,
)
from app.pipeline.orchestrator import TaskSpec, create_run  # noqa: E402
from app.pipeline.quote_card_stack import _sharpness, extract_video_frames  # noqa: E402
from app.providers.storage import _get_s3_client, public_url  # noqa: E402

_DEMO = "https://repurposer.tos-ap-southeast-1.volces.com/demo"
SOURCE_VIDEO_URL = f"{_DEMO}/uploads/xy_2.mp4"
ARTICLE_URL = f"{_DEMO}/uploads/demo-article.md"
ARTICLE_KEY = "demo/uploads/demo-article.md"
OUT_PREFIX = "demo/outputs"
UPLOAD_PREFIX = "demo/uploads"
IMMUTABLE = "public, max-age=31536000, immutable"
BAKE_EMAIL = "bake-quote@local"
TIMEOUT_S = 900  # LLM chain (understand → plan → write + translator fan-out)

# On-card attribution rails (the writer reads persona name + event name
# verbatim) — presentable, never bake-scaffolding names.
PERSONA_NAME = "Prof. Xu"
EVENT_NAME = "Future Tech Summit"

OUT_DIR = Path("/tmp/p3-quote-examples")


def _digest(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()[:8]


async def _put_demo(prefix: str, stem: str, suffix: str, data: bytes, content_type: str) -> str:
    key = f"{prefix}/{stem}-{_digest(data)}{suffix}"
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
    print(f"  baked {key}", flush=True)
    return url


async def _setup_user() -> User:
    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.email == BAKE_EMAIL).limit(1))
        ).scalar_one_or_none()
        if user is None:
            user = (
                await db.execute(select(User).order_by(User.created_at).limit(1))
            ).scalar_one_or_none()
            if user is None:
                raise SystemExit("no users in dev DB — seed one via /auth/email first")
        return user


async def _mk_scaffold(db, user: User, title: str) -> Project:
    persona = Persona(
        user_id=user.id,
        name=PERSONA_NAME,
        language="en",
        sentence_style="Short, punchy spoken-word sentences.",
        emotional_tone="rational",
    )
    db.add(persona)
    await db.flush()
    project = Project(
        user_id=user.id,
        # alt 推导锚点: project.language=zh → EN 源的双语副行确定性落 ZH。
        title=f"bake quote-cards v3 {title} {int(time.time())}",
        language="zh",
        status=ProjectStatus.DRAFT,
        persona_id=persona.id,
        event_name=EVENT_NAME,
    )
    db.add(project)
    await db.flush()
    return project


async def _asr_inline(mp4: bytes) -> dict:
    """ASR the downloaded video bytes in-process — the worker's own
    provider (``providers/asr.transcribe``, faster-whisper), same result
    shape the ASR processor stamps on the asset. The upload+worker journey
    is UX plumbing; the product path starts at the Asset row."""
    import tempfile

    from app.providers.asr import transcribe

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(mp4)
        tmp = Path(f.name)
    try:
        print("  ASR inline (faster-whisper)…", flush=True)
        return await asyncio.to_thread(transcribe, tmp)
    finally:
        tmp.unlink(missing_ok=True)


async def _run_quotes(project: Project) -> WorkflowRun:
    """Start the write_quotes chain on the scaffolded project and wait.

    create_run is THE ONLY WorkflowRun birthplace — the chat Start answer
    funnels here too, so a bake that drives it exercises the same product
    path (the chat dock is UX, not product). caption_mode=bilingual is the
    bake's one pinned input (the dock's answer); alt language is NOT
    pinned — it derives from the stamped source + project locale (§2.3).
    """
    async with AsyncSessionLocal() as db:
        run = await create_run(
            db,
            project,
            TaskSpec(
                tasks=[{"tool": "write_quotes", "params": {"language": "en", "count": 5}}],
                target_language="en",
                ui_language="zh",
                caption_mode="bilingual",
                instruction=(
                    "Pick the sharpest lines and stack them into one bilingual "
                    "quote card (EN source line + ZH alt line on the same strip)."
                ),
            ),
        )
        project.status = ProjectStatus.PROCESSING
        await db.commit()
        run_id = run.id
    print(f"  run {run_id}", flush=True)

    seen: dict[str, str] = {}
    deadline = time.time() + TIMEOUT_S
    while time.time() < deadline:
        async with AsyncSessionLocal() as s:
            run = await s.get(WorkflowRun, run_id)
            steps = (
                await s.execute(
                    select(WorkflowStep)
                    .where(WorkflowStep.run_id == run_id)
                    .order_by(WorkflowStep.seq)
                )
            ).scalars().all()
            for x in steps:
                key = f"{x.seq}:{x.kind}"
                if seen.get(key) != x.status:
                    seen[key] = x.status
                    print(f"  step {x.seq} {x.kind}: {x.status}", flush=True)
            if run.status in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED):
                if run.status == WorkflowStatus.FAILED:
                    raise SystemExit(f"run FAILED: {run.error}")
                return run
        await asyncio.sleep(5)
    raise SystemExit("run timed out")


async def _harvest_quotes(project_id) -> tuple[list[dict], bool, str | None]:
    """The writer's chain product: quotes list + speaker-frame verdict +
    core idea — read off the quotes Output row's payload."""
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(Output)
                .where(Output.project_id == project_id, Output.type == "quotes")
                .order_by(Output.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            raise SystemExit("no quotes Output — did the writer run?")
        payload = row.payload or {}
        quotes = payload.get("quotes") or []
        if len(quotes) < 2:
            raise SystemExit(f"chain too short for the cascade card: {len(quotes)}")
        return (
            quotes,
            bool(payload.get("needs_speaker_frame")),
            payload.get("core_idea"),
        )


async def _assert_single_family(project_id) -> None:
    """Bounce-sweep regression smoke (2026-08-28 root-fix): however many
    times verify bounced the writer, exactly ONE quotes row + ONE chain
    composite may survive on the project."""
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(select(Output).where(Output.project_id == project_id))
        ).scalars().all()
    quotes_rows = [o for o in rows if o.type == "quotes"]
    composites = [
        o
        for o in rows
        if o.type == "quote_frame" and (o.source_ref or {}).get("quote_chain")
    ]
    frames = [
        o
        for o in rows
        if o.type == "quote_frame" and not (o.source_ref or {}).get("quote_chain")
    ]
    clips = [o for o in rows if o.type == "clip"]
    print(
        f"  family: quotes={len(quotes_rows)} composite={len(composites)} "
        f"frames={len(frames)} clips={len(clips)}",
        flush=True,
    )
    if len(quotes_rows) != 1 or len(composites) != 1:
        raise SystemExit(
            f"family stacked across bounces: quotes={len(quotes_rows)} "
            f"composite={len(composites)} — sweep regression"
        )


def _curate_stage_photo(mp4: bytes, duration: float | None):
    """The user's-best-event-photo stand-in: a whole-talk YuNet best-face
    sweep, then a face-anchored 9:8 landscape crop around the winner.
    xy_2 is wide-stage material (best face ≈ 27px) — the raw frame leaves
    the speaker thumbnail-small, and users crop their event photos too.
    Same engine/scoring as the production span pick (max face area,
    sharpness tie-break), denser and unbound from any quote window — this
    photo is an INPUT asset. CPU-bound; call via to_thread. Returns a
    1080×960 PIL image (the composite's speaker-region frame)."""
    import numpy as np
    from PIL import Image

    from app.providers.vision import detect_faces

    dur = float(duration) if duration and duration > 30 else 300.0
    lo, hi = dur * 0.03, dur * 0.97
    timecodes = [lo + (hi - lo) * i / 23 for i in range(24)]
    try:
        frames = extract_video_frames(mp4, timecodes)
    except ValueError as exc:
        raise SystemExit(f"stage sweep decode failed: {exc}") from exc
    best = None
    best_face = None
    best_key = (-1.0, 0.0)
    best_t = 0.0
    for t, img in zip(timecodes, frames):
        if img is None:
            continue
        arr = np.array(img.convert("RGB"))[:, :, ::-1]  # RGB → BGR
        faces = detect_faces(arr, (640, 640))
        if not faces:
            continue
        face = max(faces, key=lambda f: f.bbox[2] * f.bbox[3])
        area = face.bbox[2] * face.bbox[3]
        key = (area, _sharpness(img))
        if key > best_key:
            best_key, best, best_face, best_t = key, img, face, t
    if best is None or best_face is None:
        raise SystemExit("no face in any sweep frame — cannot bake the stage photo")
    x, y, w, _h = (float(v) for v in best_face.bbox)
    fw, fh = best.size
    win_w = min(fw, max(int(w * 16), 320))
    win_h = win_w * 8 // 9
    x0 = min(max(int(x + w / 2 - win_w * 0.55), 0), fw - win_w)
    y0 = min(max(int(y - win_h * 0.25), 0), fh - win_h)
    crop = best.crop((x0, y0, x0 + win_w, y0 + win_h))
    print(
        f"  stage photo: t={best_t:.1f}s · face {int(best_key[0])}px² @ "
        f"({int(x)},{int(y)}) · crop ({x0},{y0})+{win_w}x{win_h}",
        flush=True,
    )
    return crop.resize((1080, 960), Image.LANCZOS)


async def _terminate_stale_backends() -> None:
    """D9 cleanup guard: terminate OTHER sessions parked idle-in-transaction
    >15s before the FK deletes (a wedged runner session would block them)."""
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT pid, now() - xact_start AS age FROM pg_stat_activity "
                    "WHERE pid <> pg_backend_pid() "
                    "AND state = 'idle in transaction' "
                    "AND xact_start < now() - interval '15 seconds'"
                )
            )
        ).all()
        for bpid, age in rows:
            await db.execute(text("SELECT pg_terminate_backend(:p)"), {"p": bpid})
            print(f"  terminated stale backend pid={bpid} (idle-in-tx {age})", flush=True)
    if rows:
        await asyncio.sleep(1)


async def _cleanup(project_id) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Publication).where(Publication.project_id == project_id))
        await db.execute(delete(Output).where(Output.project_id == project_id))
        await db.execute(
            delete(WorkflowStep).where(
                WorkflowStep.run_id.in_(
                    select(WorkflowRun.id).where(WorkflowRun.project_id == project_id)
                )
            )
        )
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


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true", help="skip FK cleanup")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    user = await _setup_user()
    print(f"BAKE user: {user.id}", flush=True)

    async with httpx.AsyncClient(timeout=300) as c:
        mp4 = (await c.get(SOURCE_VIDEO_URL, follow_redirects=True)).content
        article = (await c.get(ARTICLE_URL, follow_redirects=True)).text
    if len(mp4) < 100_000 or len(article) < 100:
        raise SystemExit("demo sources look wrong — check the demo/ bucket")
    print(f"sources: xy_2.mp4 {len(mp4)}B · demo-article.md {len(article)}B", flush=True)

    project_ids: list = []
    try:
        # ---------- Phase 1: video live run → chain ----------
        print("\n== Phase 1: video live run (xy_2.mp4, bilingual EN/ZH) ==", flush=True)
        asr = await _asr_inline(mp4)
        duration = asr.get("duration")
        async with AsyncSessionLocal() as db:
            project = await _mk_scaffold(db, user, "video")
            db.add(
                Asset(
                    user_id=user.id,
                    project_id=project.id,
                    type=AssetType.VIDEO,
                    # The demo object doubles as the asset body — public,
                    # content-stable, zero re-upload (see module docstring).
                    file_url="demo/uploads/xy_2.mp4",
                    title="xy_2.mp4",
                    extracted_text=asr["transcript"],
                    duration_seconds=int(duration) if duration else None,
                    meta={"words": asr["words"], "language": asr["language"]},
                    processing_status=AssetStatus.COMPLETED,
                )
            )
            await db.commit()
            pid = project.id
        project_ids.append(pid)
        print(f"project: {pid} · ASR {len(asr['words'])} words · lang={asr['language']}", flush=True)
        await _run_quotes(project)
        await _assert_single_family(pid)
        quotes, verdict, _idea = await _harvest_quotes(pid)
        print(
            f"chain: {len(quotes)} entries · writer verdict "
            f"needs_speaker_frame={verdict} (informational — tiles pinned "
            "by construction)",
            flush=True,
        )
        attribution = str(quotes[0].get("attribution") or "") or None
        captions = _chain_captions(quotes, "bilingual")
        # Chain JSON rides along so a re-compose (e.g. a different stage
        # crop) never needs a pipeline re-run.
        (OUT_DIR / "chain-video.json").write_text(
            json.dumps({"quotes": quotes, "attribution": attribution},
                       ensure_ascii=False, indent=2)
        )

        # ---------- Phase 2: 策展舞台照（全片最佳脸 = 用户最佳活动照替身） ----------
        print("\n== Phase 2: curated stage photo (whole-talk sweep) ==", flush=True)
        stage = await asyncio.to_thread(_curate_stage_photo, mp4, duration)
        buf = io.BytesIO()
        stage.save(buf, format="JPEG", quality=85)
        stage_jpg = buf.getvalue()
        (OUT_DIR / "stage-photo.jpg").write_bytes(stage_jpg)

        # ---------- Phase 3: 形态 A（照片人像区）+ 形态 B（全幅） ----------
        print("\n== Phase 3: compose 形态 A / 形态 B (video chain) ==", flush=True)
        _, form_a = await asyncio.to_thread(
            _compose_chain_pngs,
            video_bytes=None,
            image_bytes=[stage_jpg],
            chain=quotes,
            captions=captions,
            speaker_form=True,
            attribution=attribution,
        )
        _, form_b = await asyncio.to_thread(
            _compose_chain_pngs,
            video_bytes=mp4,
            image_bytes=[],
            chain=quotes,
            captions=captions,
            speaker_form=False,
            attribution=attribution,
        )
        (OUT_DIR / "formA.png").write_bytes(form_a)
        (OUT_DIR / "formB.png").write_bytes(form_b)

        # ---------- Phase 4: text live run → 照片底 / 纯文稿 ----------
        print("\n== Phase 4: transcript live run (demo-article.md) ==", flush=True)
        async with AsyncSessionLocal() as db:
            tproject = await _mk_scaffold(db, user, "text")
            db.add(
                Asset(
                    user_id=user.id,
                    project_id=tproject.id,
                    type=AssetType.TRANSCRIPT,
                    file_url=ARTICLE_KEY,
                    title="demo-article.md",
                    extracted_text=article,
                    # The bake KNOWS the article is English and stamps it —
                    # production transcript language stamping is a follow-up
                    # (PROGRESS 需求池); _project_source_language reads it.
                    meta={"language": "en"},
                    processing_status=AssetStatus.COMPLETED,
                )
            )
            await db.commit()
            tpid = tproject.id
        project_ids.append(tpid)
        print(f"project: {tpid}", flush=True)
        await _run_quotes(tproject)
        await _assert_single_family(tpid)
        tquotes, _tverdict, _ = await _harvest_quotes(tpid)
        print(f"text chain: {len(tquotes)} entries", flush=True)
        tattr = str(tquotes[0].get("attribution") or "") or None
        tcaps = _chain_captions(tquotes, "bilingual")
        (OUT_DIR / "chain-text.json").write_text(
            json.dumps({"quotes": tquotes, "attribution": tattr},
                       ensure_ascii=False, indent=2)
        )
        _, photo_png = await asyncio.to_thread(
            _compose_chain_pngs,
            video_bytes=None,
            image_bytes=[stage_jpg],
            chain=tquotes,
            captions=tcaps,
            speaker_form=True,
            attribution=tattr,
        )
        _, text_png = await asyncio.to_thread(
            _compose_chain_pngs,
            video_bytes=None,
            image_bytes=[],
            chain=tquotes,
            captions=tcaps,
            speaker_form=True,
            attribution=tattr,
        )
        (OUT_DIR / "photo.png").write_bytes(photo_png)
        (OUT_DIR / "text.png").write_bytes(text_png)

        # ---------- Phase 5: 内容寻址入 demo/ ----------
        print("\n== Phase 5: upload demo/ (content-addressed) ==", flush=True)
        url_a = await _put_demo(OUT_PREFIX, "quote-card-v3-formA", ".png", form_a, "image/png")
        url_b = await _put_demo(OUT_PREFIX, "quote-card-v3-formB", ".png", form_b, "image/png")
        url_photo = await _put_demo(OUT_PREFIX, "quote-card-v3-photo", ".png", photo_png, "image/png")
        url_text = await _put_demo(OUT_PREFIX, "quote-card-v3-text", ".png", text_png, "image/png")
        url_stage = await _put_demo(UPLOAD_PREFIX, "xy_2-stage", ".jpg", stage_jpg, "image/jpeg")

        print("\n=== BAKED — recipes.py stanza ===", flush=True)
        print(f"formA  = {url_a!r}", flush=True)
        print(f"formB  = {url_b!r}", flush=True)
        print(f"photo  = {url_photo!r}", flush=True)
        print(f"text   = {url_text!r}", flush=True)
        print(f"stage  = {url_stage!r}", flush=True)
    finally:
        if not args.keep:
            print("\ncleanup…", flush=True)
            await _terminate_stale_backends()
            for one in project_ids:
                await _cleanup(one)
            print("cleanup done", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
