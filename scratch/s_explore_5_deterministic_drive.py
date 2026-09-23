"""S-explore-5 deterministic-tail drive (拍 5 收官 reviewer, iter-3 S5 — 永不开 PR).

Exercises everything S-explore-5 asserts EXCEPT the LLM closing beat itself
(the facts-first / zero-subjective-wording / gap-suggestion prose law lands
with the resident scenario seat in S9): the deterministic 兑现事实清单 —
run_review's injection path end to end against real rows (a fabricated run
+ steps + outputs + ledger captures + a Confirmed Scope Snapshot), the gap
adjudication on a real shortfall, and the bounded block on the wire.

Run (from apps/api, dev API live):
    uv run python ../../scratch/s_explore_5_deterministic_drive.py
"""

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "scripts"))

import httpx  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from app.chat.trigger_turn import _run_review_lines  # noqa: E402
from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.tables import (  # noqa: E402
    CreditTransaction,
    Output,
    Project,
    WorkflowRun,
    WorkflowStep,
)
from app.platform.auth import create_access_token  # noqa: E402
from chat_scenarios import make_user  # noqa: E402

BASE = "http://127.0.0.1:8000/api/v1"


def ok(label: str, cond: bool, detail: object = "") -> None:
    print(("  ✓ " if cond else "  ✘ FAIL ") + label + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        raise SystemExit(1)


async def main() -> None:
    user_id = await make_user()
    client = httpx.AsyncClient(
        base_url=BASE,
        headers={"Authorization": f"Bearer {create_access_token(user_id)}"},
        timeout=60.0,
    )
    res = await client.post("/projects", json={"title": "S-explore-5 deterministic drive", "event_name": ""})
    assert res.status_code == 201, res.text
    pid = res.json()["id"]
    pu = uuid.UUID(pid)
    print("▶ S-explore-5 deterministic tail drive (拍 5 兑现审计)")

    run_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        project = (await db.execute(select(Project).where(Project.id == pu))).scalar_one()

        # A fabricated terminal run: confirmed scope (cut 2 clips + a French
        # post + an article that will NOT land) + quote 100–200.
        run = WorkflowRun(
            id=run_id,
            project_id=pu,
            status="completed",
            context={
                "confirmed_scope": {
                    "confirmation_id": "c1",
                    "confirmed_at": "2026-09-23T00:00:00Z",
                    "confirmed_via": "dock_pill",
                    "plans": [],
                    "compiled_scope": [
                        {"tool": "cut_segments", "params": {"segments": [{"start": 6.0, "end": 14.4}, {"start": 16.0, "end": 27.4}]}},
                        {"tool": "write_post", "params": {"language": "fr"}},
                        {"tool": "write_article", "params": {"language": "fr"}},
                    ],
                    "quote": {"total": [100, 200], "per_task": []},
                }
            },
        )
        db.add(run)
        await db.flush()

        clip = Output(
            id=uuid.uuid4(), project_id=pu, type="clip", language="en",
            payload={"duration": 8},
            source_ref={"start_seconds": 6.0, "end_seconds": 14.4, "asset_id": str(uuid.uuid4())},
            render_spec={"caption_enabled": True, "caption_track": [{"text": "Our pricing is simple."}]},
            quality={"status": "passed", "checks": [], "attempt": 1},
        )
        post = Output(
            id=uuid.uuid4(), project_id=pu, type="post", language="fr",
            payload={"body": "Le prix est simple."},
        )
        db.add_all([clip, post])
        await db.flush()
        db.add_all([
            WorkflowStep(run_id=run_id, kind="cut_segments", status="done", seq=0, output_refs=[str(clip.id)]),
            WorkflowStep(run_id=run_id, kind="write_post", status="done", seq=1, output_refs=[str(post.id)]),
            WorkflowStep(run_id=run_id, kind="write_article", status="failed", seq=2, output_refs=[]),
        ])
        # The ledger: two captures against the run (signed negative).
        db.add_all([
            CreditTransaction(user_id=uuid.UUID(str(user_id)), kind="capture", amount=-90, balance_after=0,
                              ref={"run_id": str(run_id), "step_id": str(uuid.uuid4())},
                              idempotency_key=f"scenario/se5:{uuid.uuid4().hex[:12]}"),
            CreditTransaction(user_id=uuid.UUID(str(user_id)), kind="capture", amount=-60, balance_after=0,
                              ref={"run_id": str(run_id), "step_id": str(uuid.uuid4())},
                              idempotency_key=f"scenario/se5:{uuid.uuid4().hex[:12]}"),
        ])
        await db.commit()

        lines = await _run_review_lines(db, run)
        print("  fact block:")
        for line in lines:
            print("    " + line)
        ok("the promise line names the families + languages",
           any(l.startswith("promised: ") and "clip" in l and "post:fr" in l and "article:fr" in l for l in lines), lines)
        ok("the landed clip carries duration + cut range + captions + verify",
           any("landed clip" in l and "duration=8s" in l and "cut=6.0–14.4s" in l and "captions=yes" in l and "verify=passed" in l for l in lines), lines)
        ok("the landed post carries its language", any("landed post" in l and "lang=fr" in l for l in lines), lines)
        ok("the missing article adjudicates as a GAP", "GAP missing_output:article:fr" in lines, lines)
        ok("the clip shortfall adjudicates (1 landed of 2 promised)", "GAP clip_shortfall:1/2" in lines, lines)
        ok("the charge line reads captured vs quoted",
           any("captured 150 credits (quoted 100–200)" in l for l in lines), lines)

        # The no-snapshot legacy posture: nothing about the promise, no gaps.
        legacy = WorkflowRun(id=uuid.uuid4(), project_id=pu, status="completed", context={})
        db.add(legacy)
        await db.commit()
        legacy_lines = await _run_review_lines(db, legacy)
        ok("legacy run: no promise, no gaps, no charge line",
           not any(l.startswith("promised:") or l.startswith("GAP") or "charge:" in l for l in legacy_lines), legacy_lines)

        # Cleanup: the ledger rows are user-scoped (no project cascade).
        await db.execute(delete(CreditTransaction).where(CreditTransaction.ref["run_id"].astext == str(run_id)))
        await db.commit()

    await client.delete(f"/projects/{pid}")
    await client.aclose()
    print("  ✓ S-explore-5 deterministic tail ALL GREEN (LLM closing beat lands with the S9 resident seat)")


asyncio.run(main())
