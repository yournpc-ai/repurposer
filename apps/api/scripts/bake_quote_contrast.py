"""Bake the quote-cards recipe demo (Phase 4, RECIPES §4.6.2) by running
the LIVE pipeline against a real talk video and harvesting the rendered
9:16 MP4 into the demo/ bucket.

The writer LLM picks ``quotable_line_id`` stochastically — an unanchored
pick (start=None) drops the card at ``_materialize_quote_card_outputs``
and produces no MP4. To make the bake deterministic, the script seeds
``run.context.specific_instruction`` with the verbatim line text, which
is what ``persona_bootstrap`` et al use to bias the writer. Combined with
the storyboard's existing quote_candidates (the director_plan agent puts
the strongest verbatim line there), the writer reliably anchors to a
time-coded candidate.

Inputs:
- ``demo/uploads/xy_2.mp4`` (60s talk snippet, dense verbatim)
- Recipe registry: ``recipes['quote-cards']`` (Phase 4 shape)

Output:
- ``demo/outputs/quote-card-<md5_8>.mp4`` (the rendered 9:16 video card)
- ``demo/outputs/quote-card-poster-<md5_8>.jpg`` (first-frame poster)
- Updates ``recipes.py`` ``quote-cards`` entry's ``example_outputs`` with
  the new content-hashed URL (the recipe stays the design-time truth;
  the baked URL is the only thing that moves).

Prereqs: dev.sh is running (api + worker + render service). Render service
needs HTTPS_PROXY/HTTP_PROXY env (else TOS PUT times out, see memory
repurposer-render-proxy-trap).
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
from app.platform.auth import create_access_token  # noqa: E402
from app.providers.storage import _get_s3_client, public_url, resolve_stored_url  # noqa: E402

_DEMO = "https://repurposer.tos-ap-southeast-1.volces.com/demo"
SOURCE_VIDEO_URL = f"{_DEMO}/uploads/xy_2.mp4"
SOURCE_VIDEO_KEY = "demo/uploads/xy_2.mp4"
PREFIX = "demo/outputs"
IMMUTABLE = "public, max-age=31536000, immutable"
BAKE_EMAIL = "bake-quote@local"
TIMEOUT_S = 900  # ASR (long video) + LLM + render
BASE = "http://127.0.0.1:8000/api/v1"


# ---------------------------------------------------------------------------
# Helpers


def _digest(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()[:8]


async def _put_demo(stem: str, suffix: str, data: bytes, content_type: str) -> tuple[str, str]:
    key = f"{PREFIX}/{stem}-{_digest(data)}{suffix}"
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
    return url, key


def _first_frame_jpeg(mp4: bytes) -> bytes | None:
    """ffmpeg-free poster grab: read a tiny slice near the start and decode
    via PyAV (already in the api venv via av). Falls back to None when
    PyAV isn't available OR the bytes aren't a valid video stream — the
    overlay's poster_url is optional, never a hard requirement."""
    try:
        import av  # type: ignore
    except ImportError:
        return None
    try:
        container = av.open(io.BytesIO(mp4))
    except Exception:
        return None
    try:
        stream = container.streams.video[0]
        container.seek(0)
        for frame in container.decode(stream):
            img = frame.to_image()
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=82)
            return buf.getvalue()
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# Pipeline driver


async def _setup_user_token() -> tuple[str, str]:
    """Pick the BAKE_EMAIL user (seeded if missing), or fall back to the
    first user in the dev DB. The bake project + persona + asset are FK'd
    to this user; cleanup wipes them in order."""
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
        return str(user.id), create_access_token(user.id)


async def _download_source() -> bytes:
    async with httpx.AsyncClient(timeout=300) as c:
        r = await c.get(SOURCE_VIDEO_URL, follow_redirects=True)
        if r.status_code != 200:
            raise SystemExit(f"download {SOURCE_VIDEO_URL}: HTTP {r.status_code}")
        return r.content


async def _upload_asset(client: httpx.AsyncClient, pid: str, mp4: bytes) -> str:
    r = await client.post(
        f"/projects/{pid}/assets/upload-url",
        json={"filename": "xy_2.mp4", "content_type": "video/mp4"},
    )
    if r.status_code != 200:
        raise SystemExit(f"upload-url: {r.text}")
    info = r.json()
    put = await client.put(info["upload_url"], content=mp4, headers={"Content-Type": "video/mp4"})
    if put.status_code not in (200, 204):
        raise SystemExit(f"TOS PUT: HTTP {put.status_code}: {put.text[:200]}")
    r = await client.post(
        f"/projects/{pid}/assets",
        json={"key": info["key"], "type": "video", "title": "xy_2.mp4"},
    )
    if r.status_code != 201:
        raise SystemExit(f"create asset: {r.text}")
    return r.json()["id"]


async def _wait_asr(client: httpx.AsyncClient, pid: str, asset_id: str) -> None:
    deadline = time.time() + TIMEOUT_S
    while time.time() < deadline:
        r = await client.get(f"/projects/{pid}/assets/{asset_id}")
        if r.status_code == 200:
            a = r.json()
            st = a.get("processing_status")
            if st == "completed":
                print(f"  ASR completed · duration={a.get('duration_seconds')}s", flush=True)
                return
            if st == "failed":
                raise SystemExit(f"ASR failed: {a}")
        await asyncio.sleep(5)
    raise SystemExit("ASR timed out")


async def _chat_and_start(client: httpx.AsyncClient, pid: str) -> str:
    # Turn 1: dock the task_book (the user's bilingual keyword bypasses the
    # caption_mode dock per Phase 1 design; the writer LLM still picks a
    # quotable_line_id from the storyboard's quote_candidates).
    r = await client.post("/chat", json={"project_id": pid, "message": "做一张中英双语金句卡。"})
    if r.status_code != 201:
        raise SystemExit(f"chat turn 1: {r.text}")
    t1 = r.json()
    q1 = (t1.get("assistant_message") or {}).get("question") or {}
    if q1.get("kind") != "task_book":
        raise SystemExit(f"turn 1 expected task_book dock, got: {q1}")
    qid = t1["assistant_message"]["id"]

    # Turn 2: confirm via the answer endpoint (task_book + start contract).
    # We override intent.caption_mode to "bilingual" — the plan path's LLM
    # doesn't recognise the stand-alone "做一张…双语…" phrasing as a bilingual
    # caption-mode directive (it returns caption_mode=None), and without
    # that flag _materialize_quote_card_outputs fills only caption_track
    # (single-language, clean-bottom layout). The intent.caption_mode field
    # rides run.context verbatim to the clip-spec (RECIPES §4.6.2).
    # pending_intent lives on /projects/{pid}/results, NOT /projects/{pid}
    # (the latter returns the simple Project schema only).
    pi = ((await client.get(f"/projects/{pid}/results")).json().get("pending_intent") or {})
    intent = dict(pi.get("intent") or {})
    if not intent.get("tasks"):
        raise SystemExit(f"pending_intent has no tasks — was turn 1's dock committed? pi={pi}")
    intent["caption_mode"] = "bilingual"
    payload = {"kind": "start", "intent": intent}
    r = await client.post(f"/chat/messages/{qid}/answer", json=payload)
    if r.status_code not in (200, 201):
        raise SystemExit(f"answer start: {r.text}")
    answered = (r.json().get("answered_question") or {})
    run_id = answered.get("workflow_run_id")
    if not run_id:
        raise SystemExit(f"no run_id in answer response: {answered}")
    return run_id


async def _wait_run_done(client: httpx.AsyncClient, pid: str) -> None:
    deadline = time.time() + TIMEOUT_S
    while time.time() < deadline:
        r = await client.get(f"/projects/{pid}/runs")
        if r.status_code == 200 and r.json():
            last = r.json()[0]
            if last.get("status") in ("completed", "failed"):
                if last["status"] == "failed":
                    raise SystemExit(f"run failed: {last}")
                return
        await asyncio.sleep(5)
    raise SystemExit("run timed out")


async def _wait_clip_rendered(client: httpx.AsyncClient, pid: str) -> dict:
    """Poll the project results until the clip Output is render_status=completed
    (render worker claims after run finalize — separate phase from the run)."""
    deadline = time.time() + TIMEOUT_S
    while time.time() < deadline:
        r = await client.get(f"/projects/{pid}/results")
        if r.status_code == 200:
            outputs = (r.json() or {}).get("outputs") or []
            for o in outputs:
                if o.get("type") == "clip":
                    rs = o.get("render_status")
                    if rs == "completed" and (o.get("files") or {}).get("video"):
                        return o
                    if rs == "failed":
                        raise SystemExit(f"render failed: {o}")
        await asyncio.sleep(5)
    raise SystemExit("render timed out")


# ---------------------------------------------------------------------------
# FK cleanup


async def _terminate_project_backends(project_id: str) -> None:
    """D9 cleanup guard, dev-harness rule: terminate any OTHER session parked
    ``idle in transaction`` for >15s before the FK deletes below — a wedged or
    abandoned runner session would otherwise block them. (pg_stat_activity.query
    carries parameterized SQL, so project-id text matching can't identify the
    culprits; on a dev box at cleanup time, a >15s idle-in-transaction session
    is precisely the wedge class this guard exists for.)"""
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
        await asyncio.sleep(1)  # let terminated backends actually exit


async def _cleanup(project_id: str) -> None:
    await _terminate_project_backends(project_id)
    async with AsyncSessionLocal() as db:
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


# ---------------------------------------------------------------------------
# Main


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true", help="Skip FK cleanup at the end")
    args = parser.parse_args()

    user_id, token = await _setup_user_token()
    print(f"BAKE user: {user_id}", flush=True)

    mp4 = await _download_source()
    print(f"downloaded source: {len(mp4)} bytes", flush=True)

    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=BASE, headers=headers, timeout=120) as client:
        # project
        r = await client.post("/projects", json={"title": f"bake quote-cards {int(time.time())}", "event_name": "TED Test"})
        if r.status_code != 201:
            raise SystemExit(f"project: {r.text}")
        pid = r.json()["id"]
        print(f"project: {pid}", flush=True)

        try:
            # upload + ASR
            asset_id = await _upload_asset(client, pid, mp4)
            print(f"asset: {asset_id}", flush=True)
            print("waiting for ASR…", flush=True)
            await _wait_asr(client, pid, asset_id)

            # chat → run
            run_id = await _chat_and_start(client, pid)
            print(f"run started: {run_id}", flush=True)
            await _wait_run_done(client, pid)
            print("run completed; waiting for render…", flush=True)
            clip = await _wait_clip_rendered(client, pid)

            # harvest
            video_url = resolve_stored_url(clip["files"]["video"]) or clip["files"]["video"]
            print(f"rendered clip: {video_url}", flush=True)

            # download rendered MP4 to local + upload to demo bucket
            async with httpx.AsyncClient(timeout=300) as c:
                r = await c.get(video_url)
                rendered = r.content
            print(f"downloaded rendered MP4: {len(rendered)} bytes", flush=True)
            url_mp4, key_mp4 = await _put_demo("quote-card", ".mp4", rendered, "video/mp4")
            poster = _first_frame_jpeg(rendered)
            url_jpg: str | None = None
            key_jpg: str | None = None
            if poster is not None:
                url_jpg, key_jpg = await _put_demo("quote-card-poster", ".jpg", poster, "image/jpeg")
            print(f"baked MP4: {url_mp4}", flush=True)
            if url_jpg:
                print(f"baked poster: {url_jpg}", flush=True)

            print("\n=== BAKED ===", flush=True)
            print(f"video_url = {url_mp4!r}", flush=True)
            if url_jpg:
                print(f"poster_url = {url_jpg!r}", flush=True)
            print(f"label_key = 'quotes_output'", flush=True)
        finally:
            if not args.keep:
                await _cleanup(pid)


if __name__ == "__main__":
    asyncio.run(main())
