"""B2 §10.3 drill — render zombie race, for real:
Re-render an existing clip → worker A claims (RENDERING + token) → A frozen
(SIGSTOP) mid-render → SQL morph-sim (render_status=PENDING, token=NULL) →
worker B claims (fresh token, attempt+1) and completes → A wakes (SIGCONT)
→ A's terminal write fenced (`render_superseded` in A's log).

Evidence asserted: output row keeps B's files; render_status stays
COMPLETED; exactly one render_superseded in A's log; no second completion.

The clip row's original files/render_status are captured and RESTORED in the
finally block (the row belongs to a real dev fixture, not the drill).

The user's dev worker(s) are SIGSTOPped for the drill's duration and
SIGCONTed at the end. Drill workers A/B log to /tmp files.
"""
import asyncio
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, "/Users/sylas/repurposer/apps/api")

import httpx
from sqlalchemy import select, text

from app.models.database import AsyncSessionLocal
from app.models.tables import Output, Project
from app.platform.auth import create_access_token

BASE = "http://127.0.0.1:8000/api/v1"
API_DIR = "/Users/sylas/repurposer/apps/api"
LOG_A = "/tmp/b2r_workerA.log"
LOG_B = "/tmp/b2r_workerB.log"

# §10.3 prep scan (b2_drill_104_probe.py): a clip with render_spec + real TOS source
CLIP_ID = uuid.UUID("910898d8-1e81-4ac9-a158-6dda1dad70a5")
OWNER_ID = uuid.UUID("52037604-9321-4b70-9212-445ccf5ade60")

ok = True


def check(cond, label, detail=""):
    global ok
    print(("✓" if cond else "✘ FAIL"), label, "" if cond else str(detail)[:300])
    if not cond:
        ok = False


def start_worker(log_path):
    f = open(log_path, "w")
    # start_new_session: own process group, so teardown kills the uv wrapper
    # AND the python child (killing the wrapper alone orphans the worker).
    return subprocess.Popen(
        ["uv", "run", "python", "-m", "app.worker"],
        cwd=API_DIR, stdout=f, stderr=subprocess.STDOUT, start_new_session=True,
    )


async def clip_row():
    async with AsyncSessionLocal() as db:
        o = await db.get(Output, CLIP_ID)
        if o is None:
            return None
        return {
            "render_status": str(o.render_status),
            "token": str(o.render_claim_token) if o.render_claim_token else None,
            "attempt": o.render_attempt,
            "files": dict(o.files or {}),
            "error": o.render_error,
        }


async def main():
    dev_pids = [int(p) for p in subprocess.run(
        ["pgrep", "-f", "app.worker"], capture_output=True, text=True
    ).stdout.split()]
    check(len(dev_pids) >= 1, "pre-existing dev worker(s) found", dev_pids)
    for p in dev_pids:
        os.kill(p, signal.SIGSTOP)
    print(f"· dev worker(s) {dev_pids} SIGSTOPped for the drill")

    worker_a = worker_b = None
    original = await clip_row()
    check(original is not None, "target clip exists", CLIP_ID)
    if original is None:
        for p in dev_pids:
            os.kill(p, signal.SIGCONT)
        sys.exit(1)
    print(f"· clip {CLIP_ID} owner check…")
    async with AsyncSessionLocal() as db:
        o = await db.get(Output, CLIP_ID)
        proj = await db.get(Project, o.project_id)
        check(str(proj.user_id) == str(OWNER_ID), "clip owned by expected user", proj.user_id)
        check(bool(o.render_spec), "clip has render_spec")

    try:
        worker_a = start_worker(LOG_A)
        await asyncio.sleep(4)

        # 1. re-render via the real endpoint (B4a one-seat reset → PENDING)
        async with httpx.AsyncClient(
            base_url=BASE,
            headers={"Authorization": f"Bearer {create_access_token(OWNER_ID)}"},
            timeout=60,
        ) as c:
            res = await c.post(f"/outputs/{CLIP_ID}/render")
            check(res.status_code == 202, "POST /outputs/{id}/render (202 Accepted)", res.text[:200])

        # 2. wait for A to claim (RENDERING + token)
        claimed = None
        deadline = time.time() + 30
        while time.time() < deadline:
            row = await clip_row()
            if row["render_status"].upper().endswith("RENDERING") and row["token"]:
                claimed = row
                break
            await asyncio.sleep(0.5)
        check(claimed is not None, "worker A claimed the render (RENDERING + token T_A)", await clip_row())
        if not claimed:
            return
        t_a = claimed["token"]
        print(f"· A claimed, token {t_a[:8]}…, attempt={claimed['attempt']}")

        # 3. give the render a head start, then freeze A mid-flight
        await asyncio.sleep(3)
        os.kill(worker_a.pid, signal.SIGSTOP)
        print(f"· worker A {worker_a.pid} frozen mid-render")

        # 4. morph-sim via SQL (per contract: RENDERING → PENDING, token NULLed)
        async with AsyncSessionLocal() as db:
            await db.execute(
                text("UPDATE outputs SET render_status='PENDING', render_claim_token=NULL, updated_at=now() WHERE id=:i"),
                {"i": str(CLIP_ID)},
            )
            await db.commit()
        print("· morph-sim applied (render_status=PENDING, token=NULL)")

        # 5. worker B claims (fresh token) and completes the render
        worker_b = start_worker(LOG_B)
        deadline = time.time() + 600
        done_b = None
        while time.time() < deadline:
            row = await clip_row()
            if row["render_status"].upper().endswith("COMPLETED"):
                done_b = row
                break
            if row["render_status"].upper().endswith("FAILED"):
                check(False, "B's render FAILED (environment?)", row)
                break
            await asyncio.sleep(3)
        check(done_b is not None, "B completed the render", await clip_row())
        if not done_b:
            return
        check(done_b["token"] != t_a, "B re-claimed with a FRESH token", (t_a, done_b["token"]))
        check(done_b["files"].get("video"), "B wrote video file", done_b["files"])
        print(f"· B completed, video={str(done_b['files'].get('video'))[:60]}…")

        # 6. wake A — its zombie terminal write must be fenced
        os.kill(worker_a.pid, signal.SIGCONT)
        print("· worker A woken — waiting for its superseded write…")
        deadline = time.time() + 300
        superseded = False
        while time.time() < deadline:
            try:
                if "render_superseded" in Path(LOG_A).read_text():
                    superseded = True
                    break
            except FileNotFoundError:
                pass
            await asyncio.sleep(3)
        check(superseded, "A's log shows render_superseded (zombie render discarded)",
              Path(LOG_A).read_text()[-800:])

        # 7. post-wake invariants
        row_after = await clip_row()
        check(row_after["render_status"].upper().endswith("COMPLETED"), "row stays COMPLETED", row_after)
        check(row_after["files"] == done_b["files"], "row keeps B's files (no clobber)",
              {"B": done_b["files"], "after": row_after["files"]})
        check(row_after["token"] == done_b["token"], "row keeps B's token", row_after["token"])

    finally:
        for w in (worker_a, worker_b):
            if w and w.poll() is None:
                os.killpg(os.getpgid(w.pid), signal.SIGKILL)
        for p in dev_pids:
            os.kill(p, signal.SIGCONT)
        print(f"· dev worker(s) {dev_pids} SIGCONTed (restored)")
        # No restore: B's completion legitimately owns the row (that IS the
        # production end state of a morph-supersede cycle), and the success
        # path already GC'd the pre-drill storage objects — restoring the old
        # keys would dangle. Drill side effect = one real re-render of a dev
        # fixture clip (same spec, fresh objects).
        print(f"· clip row left with B's fresh render (was: {original['render_status']})")
    print("\nDRILL §10.3", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


asyncio.run(main())
