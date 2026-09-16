"""B2 §10.2 drill — node fencing race, for real:
A claims LLM node N → A frozen (SIGSTOP) → SQL reap → B claims (new token,
attempt+1) → B completes → A wakes (SIGCONT) → A's terminal write fenced.

Evidence asserted: N keeps B's values; exactly ONE capture for N; run stays
COMPLETED; wallet balance changes exactly once. A's own log must show
``workflow_step_fenced``.

The user's dev worker is SIGSTOPped for the drill's duration (no claim
races) and SIGCONTed at the end. Drill workers A/B log to /tmp files.
"""
import asyncio
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
from app.models.schemas import AssetStatus, AssetType
from app.models.tables import Asset, Conversation, CreditTransaction, Message, Output, Project, User, Wallet, WorkflowRun, WorkflowStep
from app.platform.auth import create_access_token

BASE = "http://127.0.0.1:8000/api/v1"
API_DIR = "/Users/sylas/repurposer/apps/api"
LOG_A = "/tmp/b2_workerA.log"
LOG_B = "/tmp/b2_workerB.log"
LLM_KINDS = ("understand", "plan", "write_post", "write_article", "write_quotes")

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


async def db_steps(rid):
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(WorkflowStep).where(WorkflowStep.run_id == uuid.UUID(rid)).order_by(WorkflowStep.seq)
            )
        ).scalars().all()
        return [
            {"id": str(s.id), "kind": s.kind, "status": s.status, "attempt": s.attempt,
             "token": str(s.claim_token) if s.claim_token else None,
             "output_refs": s.output_refs, "cost": s.cost}
            for s in rows
        ]


async def captures_for_step(step_id):
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(CreditTransaction).where(
                    CreditTransaction.kind == "capture",
                    CreditTransaction.ref["step_id"].astext == step_id,
                )
            )
        ).scalars().all()
        return [(str(r.id), r.idempotency_key, r.amount) for r in rows]


async def wallet_balance(uid):
    async with AsyncSessionLocal() as db:
        w = (await db.execute(select(Wallet).where(Wallet.user_id == uid))).scalar_one_or_none()
        return w.balance if w is not None else None


async def main():
    # 0. freeze the user's dev worker(s) so claims are deterministic among A/B
    # (dev.sh's watchdog shows as a parent+child pair — freeze every match)
    dev_pids = [int(p) for p in subprocess.run(
        ["pgrep", "-f", "app.worker"], capture_output=True, text=True
    ).stdout.split()]
    check(len(dev_pids) >= 1, "pre-existing dev worker(s) found", dev_pids)
    import os
    for p in dev_pids:
        os.kill(p, signal.SIGSTOP)
    print(f"· dev worker(s) {dev_pids} SIGSTOPped for the drill")

    worker_a = worker_b = None
    uid = pid = rid = None
    try:
        # 1. worker A up (claims the target node)
        worker_a = start_worker(LOG_A)
        await asyncio.sleep(4)  # startup: registry + startup reap

        # 2. project + COMPLETED transcript asset + plan → start (S4 shape)
        async with AsyncSessionLocal() as db:
            user = User(email=f"drill-b2-{uuid.uuid4().hex[:8]}@test.local", name="drill-b2")
            db.add(user)
            await db.flush()
            project = Project(user_id=user.id, title="B2 10.2 drill")
            db.add(project)
            await db.flush()
            asset = Asset(
                user_id=user.id, project_id=project.id, type=AssetType.TRANSCRIPT,
                file_url="scenario/b2-drill.txt", title="notes.txt",
                extracted_text="Pricing strategy notes: value-based pricing beats cost-plus; "
                "anchor high, tier the offer, never discount the core tier. " * 20,
                processing_status=AssetStatus.COMPLETED,
            )
            db.add(asset)
            await db.commit()
            uid, pid = user.id, project.id
        print(f"· balance before: {await wallet_balance(uid)}")

        async with httpx.AsyncClient(
            base_url=BASE, headers={"Authorization": f"Bearer {create_access_token(uid)}"}, timeout=180
        ) as c:
            turn = await c.post("/chat", json={"project_id": str(pid), "message": "Write a LinkedIn post from my notes."})
            check(turn.status_code == 201, "chat turn 1", turn.text[:200])
            body = turn.json()
            for _ in range(4):  # answer asks until the task_book docks
                q = (body.get("assistant_message") or {}).get("question") or {}
                if q.get("kind") == "task_book":
                    res = await c.post(f"/chat/messages/{body['assistant_message']['id']}/answer", json={"kind": "start"})
                    check(res.status_code == 200, "start answer", res.text[:200])
                    body = res.json()
                    break
                if q.get("kind") == "question":
                    res = await c.post(f"/chat/messages/{body['assistant_message']['id']}/answer",
                                       json={"kind": "freeform", "text": "pricing strategy for researchers"})
                    check(res.status_code == 200, "slot answer", res.text[:200])
                    body = res.json()
                    continue
                check(False, "unexpected dock state", body)
                return
        async with AsyncSessionLocal() as db:
            r = (await db.execute(
                select(WorkflowRun).where(WorkflowRun.project_id == pid).order_by(WorkflowRun.created_at.desc()).limit(1)
            )).scalar_one()
            rid = str(r.id)
        print(f"· run {rid} born")

        # 3. catch an LLM node mid-flight (claimed by A)
        target = None
        deadline = time.time() + 60
        while time.time() < deadline:
            for s in await db_steps(rid):
                if s["kind"] in LLM_KINDS and s["status"] == "running" and s["token"]:
                    target = s
                    break
            if target:
                break
            await asyncio.sleep(0.25)
        check(target is not None, "caught an LLM node running with claim_token (T_A)", await db_steps(rid))
        if not target:
            return
        nid, t_a = target["id"], target["token"]
        print(f"· node {target['kind']} {nid} claimed by A, token {t_a[:8]}…, attempt={target['attempt']}")

        # 4. freeze A mid-execution
        os.kill(worker_a.pid, signal.SIGSTOP)
        print(f"· worker A {worker_a.pid} frozen mid-flight")

        # 5. simulate the reap (per-tick 900s equivalent)
        async with AsyncSessionLocal() as db:
            await db.execute(
                text("UPDATE workflow_steps SET status='pending', claim_token=NULL, updated_at=now() WHERE id=:i"),
                {"i": nid},
            )
            await db.commit()
        print("· reaped via SQL (status=pending, token=NULL)")

        # 6. worker B claims and finishes the whole run
        worker_b = start_worker(LOG_B)
        deadline = time.time() + 300
        final = None
        while time.time() < deadline:
            steps = await db_steps(rid)
            row = next(s for s in steps if s["id"] == nid)
            async with AsyncSessionLocal() as db:
                r = await db.get(WorkflowRun, uuid.UUID(rid))
                rstatus = str(r.status)
            if row["status"] in ("done", "failed") and rstatus in ("WorkflowStatus.COMPLETED", "completed", "WorkflowStatus.FAILED", "failed"):
                final = (row, rstatus)
                break
            await asyncio.sleep(2)
        check(final is not None, "B completed the node and the run settled", await db_steps(rid))
        if not final:
            return
        row_b, rstatus = final
        check(row_b["token"] != t_a and row_b["attempt"] == target["attempt"] + 1,
              "B re-claimed with a FRESH token and attempt+1", row_b)
        check(rstatus.upper().endswith("COMPLETED"), "run COMPLETED by B", rstatus)
        caps = await captures_for_step(nid)
        check(len(caps) == 1, "exactly ONE capture for the node (B's)", caps)
        bal_after_b = await wallet_balance(uid)
        print(f"· balance after B: {bal_after_b}")

        # 7. wake A — its zombie terminal write must be fenced
        os.kill(worker_a.pid, signal.SIGCONT)
        print(f"· worker A woken — waiting for its fenced terminal write…")
        deadline = time.time() + 240
        fenced = False
        while time.time() < deadline:
            try:
                if "workflow_step_fenced" in Path(LOG_A).read_text():
                    fenced = True
                    break
            except FileNotFoundError:
                pass
            await asyncio.sleep(2)
        check(fenced, "A's log shows workflow_step_fenced (zombie write discarded)", Path(LOG_A).read_text()[-800:])

        # 8. post-wake invariants
        row_after = next(s for s in await db_steps(rid) if s["id"] == nid)
        check(row_after["status"] == row_b["status"] and row_after["token"] == row_b["token"]
              and row_after["output_refs"] == row_b["output_refs"],
              "N keeps B's values after A woke (no overwrite)", {"B": row_b, "after": row_after})
        caps2 = await captures_for_step(nid)
        check(caps2 == caps, "still exactly one capture — 双扣封死", caps2)
        bal_final = await wallet_balance(uid)
        check(bal_final == bal_after_b, "wallet balance unchanged by A's wake", (bal_after_b, bal_final))
        async with AsyncSessionLocal() as db:
            r = await db.get(WorkflowRun, uuid.UUID(rid))
            check(str(r.status).upper().endswith("COMPLETED"), "run stays COMPLETED", r.status)

    finally:
        for w in (worker_a, worker_b):
            if w and w.poll() is None:
                os.killpg(os.getpgid(w.pid), signal.SIGKILL)
        import os
        for p in dev_pids:
            os.kill(p, signal.SIGCONT)
        print(f"· dev worker(s) {dev_pids} SIGCONTed (restored)")
        # FK-safe cleanup (steps → runs → assets → project → user), one commit per tier
        if rid:
            async with AsyncSessionLocal() as db:
                for s in (await db.execute(select(WorkflowStep).where(WorkflowStep.run_id == uuid.UUID(rid)))).scalars().all():
                    await db.delete(s)
                await db.commit()
            async with AsyncSessionLocal() as db:
                await db.delete(await db.get(WorkflowRun, uuid.UUID(rid)))
                await db.commit()
        if pid:
            async with AsyncSessionLocal() as db:
                for o in (await db.execute(select(Output).where(Output.project_id == pid))).scalars().all():
                    await db.delete(o)
                for a in (await db.execute(select(Asset).where(Asset.project_id == pid))).scalars().all():
                    await db.delete(a)
                txs = (await db.execute(select(CreditTransaction).where(CreditTransaction.user_id == uid))).scalars().all()
                for t in txs:
                    await db.delete(t)
                await db.commit()
            async with AsyncSessionLocal() as db:
                convs = (await db.execute(
                    select(Conversation).where(Conversation.project_id == pid)
                )).scalars().all()
                for cv in convs:
                    for m in (await db.execute(select(Message).where(Message.conversation_id == cv.id))).scalars().all():
                        await db.delete(m)
                for cv in convs:
                    await db.delete(cv)
                await db.delete(await db.get(Project, pid))
                await db.commit()
            print("· drill rows cleaned (user row kept, scenario convention)")
    print("\nDRILL §10.2", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


asyncio.run(main())
