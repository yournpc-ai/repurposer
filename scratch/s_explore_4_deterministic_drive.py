"""S-explore-4 deterministic-tail drive (拍 3 插话换选, iter-3 S4 — 永不开 PR).

Exercises everything S-explore-4 asserts EXCEPT the LLM interjection beats
(those land with the resident scenario seat in S9): the revise_selects door
branch (swap / bounds / restatement-required / settled closed / one-journey
/ replay) and the three money states' DETERMINISTIC mechanics at door +
compile level —

- PRE-DOCK: swap before any plan — the door revision alone, zero writes
  beyond the row itself, idem survives.
- DOCKED: a live plan rides the pick — the whole-journey recompile
  re-derives the NEW member's range (the plan spec never changes; the
  compile dereferences the live select).
- POST-RUN: mark_compiled → swap → supersede-继任 (spec carry-over
  verbatim) → compile_plan_rows_package over the successor — the mini
  package carries the new range.

The turn-layer adjudication itself (select_revision_phase consumption +
the two paths' dock seats) is covered by tests/test_revise_selects_pure.py
(door + discriminator) and the S9 live beats (dock faces).

Run (from apps/api, dev API live):
    uv run python ../../scratch/s_explore_4_deterministic_drive.py
"""

import asyncio
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "scripts"))

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.chat.exploration_compile import (  # noqa: E402
    CompiledPackage,
    compile_plan_rows_package,
    recompile_journey_package,
)
from app.chat.exploration_tools import execute_exploration_tool  # noqa: E402
from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.schemas import AssetType  # noqa: E402
from app.models.tables import GraphNode, Project  # noqa: E402
from app.pipeline.exploration_store import (  # noqa: E402
    mark_compiled,
    read_journey_plan_rows,
    select_revision_phase,
    supersede_plan,
)
from app.platform.auth import create_access_token  # noqa: E402
from chat_scenarios import make_user, seed_asset  # noqa: E402

BASE = "http://127.0.0.1:8000/api/v1"

SENTENCES = [
    (0.0, "Welcome back to the founder notes."),
    (6.0, "Our pricing is simple."),
    (10.0, "The pro tier costs ten dollars a month."),
    (16.0, "Let me switch gears to the roadmap."),
    (22.0, "We are shipping the new dashboard next quarter."),
    (30.0, "Every pricing tier includes the analytics dashboard."),
    (38.0, "That is the whole announcement for this week."),
]


def words() -> list[dict]:
    out: list[dict] = []
    for line_start, sentence in SENTENCES:
        t = line_start
        for w in sentence.split():
            out.append({"word": w, "start": round(t, 2), "end": round(t + 0.4, 2)})
            t += 0.5
    return out


# Member ranges (verbatim excerpts — the door validates at birth).
MEMBER_A = {"start": 6.0, "end": 14.4, "excerpt": "Our pricing is simple. The pro tier costs ten dollars a month.", "speaker": "host"}
MEMBER_B = {"start": 16.0, "end": 27.4, "excerpt": "Let me switch gears to the roadmap. We are shipping the new dashboard next quarter.", "speaker": "host"}


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
    res = await client.post("/projects", json={"title": "S-explore-4 deterministic drive", "event_name": ""})
    assert res.status_code == 201, res.text
    pid = res.json()["id"]
    pu = uuid.UUID(pid)
    asset_id = await seed_asset(
        pid, user_id, AssetType.VIDEO, "se4-talk.mp4",
        extracted_text=" ".join(s for _, s in SENTENCES),
        meta={"words": words(), "speaker_map": {"turns": [{"start": 0.0, "end": 45.0, "speaker": "host"}]}, "language": "en"},
        processed=True,
    )
    print("▶ S-explore-4 deterministic tail drive (拍 3 插话换选)")

    async with AsyncSessionLocal() as db:
        project = (await db.execute(select(Project).where(Project.id == pu))).scalar_one()

        # The chain's births (what the LLM beats would call).
        cs_text = await execute_exploration_tool(db, project, "propose_candidates", {
            "asset_id": asset_id, "topic": "pricing",
            "goal": "pricing clip for my launch",
            "members": [MEMBER_A, MEMBER_B],
        })
        await db.commit()
        cs_id = re.search(r"candidate_set_id: ([0-9a-f-]{36})", cs_text).group(1)
        ok("propose_candidates lands with two members", "landed" in cs_text, cs_text)

        sel_text = await execute_exploration_tool(db, project, "propose_selects", {
            "candidate_set_id": cs_id,
            "selects": [{"member_index": 0, "verdict": "Direct pricing answer", "reason": "Names the tier and the price."}],
        })
        await db.commit()
        sel_id = re.search(r"select_id: ([0-9a-f-]{36})", sel_text).group(1)
        ok("propose_selects lands on member 0", "member 0" in sel_text, sel_text)

        select_row = (await db.execute(select(GraphNode).where(GraphNode.id == uuid.UUID(sel_id)))).scalar_one()
        birth_idem = select_row.spec["idem"]

        # ── 门内拒收（先于三金钱态）────────────────────────────────────────
        for bad, why in (
            ({"select_id": sel_id, "member_index": 5, "verdict": "v", "reason": "r"}, "bounds re-validate"),
            ({"select_id": sel_id, "member_index": 1, "verdict": "", "reason": "r"}, "verdict restatement required"),
            ({"select_id": sel_id, "member_index": 1, "verdict": "v", "reason": " "}, "reason restatement required"),
        ):
            rej = await execute_exploration_tool(db, project, "revise_selects", {"selects": [bad]})
            ok(f"door rejection: {why}", rej.startswith("The door rejected"), rej)
        await db.rollback()  # rejections are flush-only, but stay clean
        await db.refresh(project)  # rollback expires ORM attrs — re-load before reuse

        # ── PRE-DOCK: swap before any plan — 零仪式 ────────────────────────
        nodes_before = len((await db.execute(select(GraphNode).where(GraphNode.project_id == pu))).scalars().all())
        swap = await execute_exploration_tool(db, project, "revise_selects", {
            "selects": [{"select_id": sel_id, "member_index": 1, "verdict": "Roadmap momentum", "reason": "Stronger launch hook."}],
        })
        await db.commit()
        ok("revise_selects lands (pre-dock swap)", "revised in place" in swap, swap)
        await db.refresh(select_row)
        ok("state → revised (select family's first revised writer)", select_row.state == "revised", select_row.state)
        ok("member_index re-pointed", select_row.spec["member_index"] == 1, select_row.spec)
        ok("birth idem survives (never re-minted)", select_row.spec["idem"] == birth_idem)
        nodes_after = len((await db.execute(select(GraphNode).where(GraphNode.project_id == pu))).scalars().all())
        ok("zero new rows (in-place, zero ceremony)", nodes_after == nodes_before, (nodes_before, nodes_after))
        plans = await read_journey_plan_rows(db, pu, uuid.UUID(str(select_row.journey_id)))
        ok("no riding plans → discriminator says pre_dock", select_revision_phase([p.state for p in plans]) == "pre_dock")

        # Replay: identical restatement = no-op.
        again = await execute_exploration_tool(db, project, "revise_selects", {
            "selects": [{"select_id": sel_id, "member_index": 1, "verdict": "Roadmap momentum", "reason": "Stronger launch hook."}],
        })
        await db.commit()
        ok("identical restatement replays clean", "revised in place" in again, again)

        # ── DOCKED: a live plan rides the pick — recompile follows ────────
        plan_text = await execute_exploration_tool(db, project, "propose_plans", {
            "plans": [{"select_id": sel_id, "title": "Roadmap clip", "outputs": [{"kind": "clip"}]}],
        })
        await db.commit()
        plan_id = re.search(r"plan_id: ([0-9a-f-]{36})", plan_text).group(1)
        ok("plan born ready on the swapped pick", "[ready]" in plan_text, plan_text)
        plan_row = (await db.execute(select(GraphNode).where(GraphNode.id == uuid.UUID(plan_id)))).scalar_one()
        journey_id = uuid.UUID(str(plan_row.journey_id))

        # The swap back to member 0: plan spec untouched, compile follows.
        await execute_exploration_tool(db, project, "revise_selects", {
            "selects": [{"select_id": sel_id, "member_index": 0, "verdict": "Direct pricing answer", "reason": "Names the tier and the price."}],
        })
        await db.commit()
        plans = await read_journey_plan_rows(db, pu, journey_id)
        ok("riding live plan → discriminator says docked", select_revision_phase([p.state for p in plans]) == "docked")
        package = await recompile_journey_package(db, project, journey_id)
        assert isinstance(package, CompiledPackage), package
        seg = package.tasks[0].params["segments"][0]
        ok(
            "docked recompile re-derives the NEW member's range (plan spec untouched)",
            (seg["start"], seg["end"]) == (MEMBER_A["start"], MEMBER_A["end"]),
            seg,
        )
        ok("the R20 map keys are the real plan ids", set(package.plan_task_map) == {plan_id}, package.plan_task_map)
        await db.refresh(plan_row)
        ok("the plan row itself never moved (same id, still ready)", plan_row.state == "ready" and str(plan_row.id) == plan_id)

        # ── POST-RUN: compiled → swap → supersede-继任 → mini compile ─────
        await mark_compiled(db, project, plan_ids=[plan_row.id])
        await db.commit()
        await db.refresh(plan_row)
        ok("mark_compiled settles the plan (Start's stamp)", plan_row.state == "compiled", plan_row.state)

        await execute_exploration_tool(db, project, "revise_selects", {
            "selects": [{"select_id": sel_id, "member_index": 1, "verdict": "Roadmap momentum", "reason": "Stronger launch hook."}],
        })
        plans = await read_journey_plan_rows(db, pu, journey_id)
        ok("riding compiled plan → discriminator says post_run", select_revision_phase([p.state for p in plans]) == "post_run")
        successor = await supersede_plan(db, project, plan_id=plan_row.id)
        await db.commit()
        await db.refresh(plan_row)
        ok("old plan settles superseded", plan_row.state == "superseded", plan_row.state)
        ok("successor born revised, spec carried over verbatim",
           successor.state == "revised" and successor.spec["outputs"] == plan_row.spec["outputs"]
           and successor.spec["select_id"] == sel_id, successor.spec)

        mini = await compile_plan_rows_package(db, project, journey_id, [successor])
        assert isinstance(mini, CompiledPackage), mini
        seg = mini.tasks[0].params["segments"][0]
        ok("mini package re-derives the swapped range", (seg["start"], seg["end"]) == (MEMBER_B["start"], MEMBER_B["end"]), seg)
        ok("mini package = 只含变化 (one successor, one task)", len(mini.plans) == 1 and len(mini.tasks) == 1)
        ok("mini map keys = the successor's real id", set(mini.plan_task_map) == {str(successor.id)})

        # A settled select is closed (defensive — selects never settle in
        # practice, but the state-machine vocabulary allows it).
        sel_row = (await db.execute(select(GraphNode).where(GraphNode.id == uuid.UUID(sel_id)))).scalar_one()
        sel_row.state = "superseded"
        await db.flush()
        rej = await execute_exploration_tool(db, project, "revise_selects", {
            "selects": [{"select_id": sel_id, "member_index": 0, "verdict": "v", "reason": "r"}],
        })
        ok("a settled select is closed to revision", rej.startswith("The door rejected"), rej)
        await db.rollback()

    # The graph API face: the revised select + the supersede pair ride the wire.
    g = await client.get(f"/projects/{pid}/graph")
    assert g.status_code == 200, g.text
    graph = g.json()
    explore = [n for n in graph["nodes"] if n["type"] == "exploration"]
    kinds = [(n["spec"].get("exploration_kind"), n["state"]) for n in explore]
    ok("select row reads revised on the wire", ("select", "revised") in kinds, kinds)
    ok("the supersede pair reads (superseded, revised)", ("content_plan", "superseded") in kinds and ("content_plan", "revised") in kinds, kinds)

    await client.delete(f"/projects/{pid}")
    await client.aclose()
    print("  ✓ S-explore-4 deterministic tail ALL GREEN (LLM interjection beats land with the S9 resident seat)")


asyncio.run(main())
