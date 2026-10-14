"""MG D3 e2e 实录: the full chat chain for a launch film — paste a link →
web_page asset captured → plan → auto 档开工 → three-node lineage
(web_page → launch_film → film output) → rendered film — plus the ledger
reconciliation (估价贴 vs 实扣, hold→capture→release).

Run: uv run python scratch/mg_d3_e2e.py [url]
Requires: live stack (API :8000 with D3 code reloaded, worker with D3 code),
a seeded dev user. Prints every probe line (实录), exits non-zero on any
broken link of the chain.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "/Users/sylas/repurposer/apps/api")

import httpx
from sqlalchemy import select

from app.models.database import AsyncSessionLocal
from app.models.tables import (
    Asset,
    CreditTransaction,
    Output,
    Project,
    User,
    Wallet,
    WorkflowRun,
    WorkflowStep,
)
from app.platform.auth import create_access_token
from app.platform.billing import credits_at_ratio, estimate_usd_range
from app.providers.storage import public_url

API = "http://127.0.0.1:8000"
PAGE_URL = sys.argv[1] if len(sys.argv) > 1 else "https://linear.app"
# Resume mode: an existing project whose plan is already docked — skip the
# creation + first turn, send only the confirm (saves a full turn + capture).
EXISTING_PID = sys.argv[2] if len(sys.argv) > 2 else None
FILM_DIR = Path("/tmp/mg_d3_e2e")
POLL_DEADLINE = 15 * 60


def line(label: str, **kv) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {label}: {json.dumps(kv, ensure_ascii=False, default=str)}", flush=True)


async def poll(label: str, predicate, interval: float = 5.0):
    t0 = time.time()
    while time.time() - t0 < POLL_DEADLINE:
        value = await predicate()
        if value is not None:
            return value
        await asyncio.sleep(interval)
    raise AssertionError(f"{label}: timed out after {POLL_DEADLINE}s")


async def main() -> None:
    FILM_DIR.mkdir(exist_ok=True)
    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).order_by(User.created_at).limit(1))
        ).scalar_one()
    token = create_access_token(user.id)
    line("user", id=user.id, email=user.email)

    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=API, headers=headers, timeout=180) as http:
        if EXISTING_PID:
            project_id = EXISTING_PID
            line("project.resumed", id=project_id)
        else:
            r = await http.post(
                "/api/v1/projects",
                json={"title": f"MG D3 e2e — {PAGE_URL}", "language": "en"},
            )
            r.raise_for_status()
            project_id = r.json()["id"]
            line("project.created", id=project_id)

            message = f"Turn this page into a short launch film: {PAGE_URL}"
            t0 = time.time()
            r = await http.post(
                "/api/v1/chat", json={"project_id": project_id, "message": message}
            )
            line("chat.turn", status=r.status_code, seconds=round(time.time() - t0, 1))
            if r.status_code != 201:
                print(r.text[:2000])
                raise SystemExit(1)
            resp = r.json()
            answered = resp.get("answered_question") or {}
            line(
                "chat.answer",
                run_id=resp.get("run_id"),
                content=str(answered.get("content"))[:400],
            )

        # 守卫线 (ADR-117): the fold's high end crosses the priced-ask
        # threshold, so even auto 档 docks the plan and asks once — the
        # verbal yes rides the same machine as the Start button.
        t0 = time.time()
        r = await http.post(
            "/api/v1/chat", json={"project_id": project_id, "message": "Yes — go ahead."}
        )
        line("chat.confirm_turn", status=r.status_code, seconds=round(time.time() - t0, 1))
        if r.status_code != 201:
            print(r.text[:2000])
            raise SystemExit(1)
        resp2 = r.json()
        answered2 = resp2.get("answered_question") or {}
        line(
            "chat.confirm_answer",
            run_id=resp2.get("run_id"),
            content=str(answered2.get("content"))[:400],
        )

    async def asset_ready():
        async with AsyncSessionLocal() as db:
            assets = list(
                (
                    await db.execute(
                        select(Asset).where(
                            Asset.project_id == project_id,
                            Asset.type == "web_page",
                        )
                    )
                )
                .scalars()
                .all()
            )
            if not assets:
                return None
            a = assets[0]
            status = str(a.processing_status)
            if status.lower().endswith("completed"):
                return a
            if status.lower().endswith("failed"):
                raise AssertionError(f"web_page capture FAILED: {a.meta}")
            line("asset.pending", status=status)
            return None

    asset = await poll("web_page asset ready", asset_ready)
    meta = asset.meta or {}
    research = meta.get("research") or {}
    line(
        "asset.ready",
        id=asset.id,
        title=(research.get("title") or "")[:80],
        h1=len(research.get("h1") or []),
        paragraphs=len(research.get("paragraphs") or []),
        screenshot=bool(meta.get("screenshot_key")),
    )

    async def run_terminal():
        async with AsyncSessionLocal() as db:
            runs = list(
                (
                    await db.execute(
                        select(WorkflowRun)
                        .where(WorkflowRun.project_id == project_id)
                        .order_by(WorkflowRun.created_at)
                    )
                )
                .scalars()
                .all()
            )
            if not runs:
                return None
            run = runs[-1]
            status = str(run.status)
            if status.lower().endswith(("completed", "failed")):
                return run
            return None

    run = await poll("run terminal", run_terminal)
    line("run.terminal", id=run.id, status=str(run.status))

    async with AsyncSessionLocal() as db:
        steps = list(
            (
                await db.execute(
                    select(WorkflowStep)
                    .where(WorkflowStep.run_id == run.id)
                    .order_by(WorkflowStep.seq)
                )
            )
            .scalars()
            .all()
        )
        outputs = list(
            (
                await db.execute(
                    select(Output).where(Output.project_id == project_id)
                )
            )
            .scalars()
            .all()
        )
    film_step = next((s for s in steps if s.kind == "launch_film"), None)
    render_steps = [s for s in steps if s.kind == "render"]
    film = next((o for o in outputs if o.type == "film"), None)
    line(
        "lineage",
        steps=[(s.kind, str(s.status)) for s in steps],
        film_output=str(film.id) if film else None,
        provenance=film.provenance if film else None,
        render_status=str(film.render_status) if film else None,
    )
    assert film_step is not None and str(film_step.status).lower().endswith("done"), "launch_film step not done"
    assert film is not None, "no film output row"
    assert film.provenance == "generated", "ADR-026: film provenance must be generated"
    assert str(film.render_status).lower().endswith("completed"), f"render not complete: {film.render_error}"
    video_key = (film.files or {}).get("video")
    assert video_key, "film files.video missing"
    url = public_url(video_key)
    line("film.rendered", url=url, payload=film.payload)

    # Download + probe (产物文件校验: exists, non-zero, streams readable).
    target = FILM_DIR / f"{film.id}.mp4"
    async with httpx.AsyncClient(timeout=300, follow_redirects=True) as http:
        rr = await http.get(url)
        rr.raise_for_status()
        target.write_bytes(rr.content)
    import av

    with av.open(str(target)) as container:
        v = container.streams.video[0]
        duration = float(container.duration or 0) / 1_000_000
        line(
            "film.probe",
            bytes=target.stat().st_size,
            codec=v.codec_context.name,
            width=v.codec_context.width,
            height=v.codec_context.height,
            duration_s=round(duration, 2),
        )

    # --- ledger reconciliation (估价贴 vs 实扣) ---
    async with AsyncSessionLocal() as db:
        txns = list(
            (
                await db.execute(
                    select(CreditTransaction)
                    .where(CreditTransaction.user_id == user.id)
                    .order_by(CreditTransaction.created_at)
                )
            )
            .scalars()
            .all()
        )
        wallet = await db.get(Wallet, user.id)
    run_txns = [t for t in txns if (t.ref or {}).get("run_id") == str(run.id)]
    holds = [t for t in run_txns if t.kind == "hold"]
    captures = [t for t in run_txns if t.kind == "capture"]
    releases = [t for t in run_txns if t.kind == "release"]
    held = sum(-t.amount for t in holds)
    captured = sum(-t.amount for t in captures)
    released = sum(t.amount for t in releases)
    line(
        "ledger",
        rows=[(t.kind, t.amount, t.idempotency_key) for t in run_txns],
        held=held,
        captured=captured,
        released=released,
        identity_ok=held == captured + released,
        wallet_balance=int(wallet.balance),
    )
    assert held == captured + released, "hold != capture + release"

    # The sticker (what the plan dock / node card quoted) vs the settle.
    assert film_step.estimate, "launch_film estimate missing"
    usd_low, usd_high = estimate_usd_range(film_step.estimate)
    ratio = 1000  # credits.per_cost_usd default; read live below for honesty
    async with AsyncSessionLocal() as db:
        from app.platform.configs import get_config

        ratio = await get_config(db, "credits.per_cost_usd")
        film_rate = await get_config(db, "film.usd_per_second")
    sticker = [credits_at_ratio(usd_low, ratio), credits_at_ratio(usd_high, ratio)]
    actual_seconds = ((film_step.cost or {}).get("units") or {}).get("film_seconds")
    line(
        "reconciliation",
        sticker_credits=sticker,
        captured_credits=captured,
        hold_credits=held,
        estimate_seconds=film_step.estimate["units"]["film_seconds"],
        actual_seconds=actual_seconds,
        film_usd_per_second=film_rate,
        cost=film_step.cost,
    )
    assert captured <= held, "capture exceeded the hold"
    line("e2e.ok", run=str(run.id), film=str(film.id), video=str(target))


asyncio.run(main())
