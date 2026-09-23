"""S-explore-3 deterministic-tail drive (拍 6 修订回路, iter-3 S9 seat — 永不开 PR).

Exercises everything S-explore-3 asserts EXCEPT the LLM revision beats
(those land with the resident scenario seat when the user runs the full
suite): the R20 revision router + the R19 craft assembly + the wiring door
on REAL rows —

- plan_ref 双通道 (ordinal "1" and the verbatim plan_id) resolve through
  the confirmed-scope snapshot's plan_task_map → task slice → fill_keys →
  the live canvas nodes;
- the @output pin resolves straight to the producing node (snapshot
  membership is best-effort context);
- legacy (no snapshot) / out-of-range refs degrade honestly (never a
  guess — the @output channel is the named fallback);
- assemble_craft_revision gates the prompt-consuming family: a mixed set
  yields edit_prompt+run ops PLUS the deterministic nodes' uncovered
  labels (the disclosure line's material); an all-deterministic set
  degrades to None;
- the assembled edit_prompt lands through apply_wiring_ops (the ONLY
  write door) and the node's program honestly shows the revision clause;
  an unknown node id dies at the door (WiringRejected).

The classifier's continuation/expansion adjudication is pure-tested
(scope_classifier's own suites, Phase 4 B1/B2) and the run op is
deliberately NOT fired here (a resident worker would eat it — the LLM
beat's live run lands with the resident seat).

Run (from apps/api, dev API live):
    uv run python ../../scratch/s_explore_3_deterministic_drive.py
"""

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "scripts"))

import httpx  # noqa: E402

from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.tables import GraphNode, Output, WorkflowRun  # noqa: E402
from app.pipeline.graph_store import WiringRejected, apply_wiring_ops  # noqa: E402
from app.pipeline.scope_compile import (  # noqa: E402
    assemble_craft_revision,
    compose_revised_program,
    route_revision,
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
    res = await client.post("/projects", json={"title": "S-explore-3 deterministic drive", "event_name": ""})
    assert res.status_code == 201, res.text
    pid = res.json()["id"]
    pu = uuid.UUID(pid)
    print("▶ S-explore-3 deterministic tail drive (拍 6 修订回路)")

    async with AsyncSessionLocal() as db:
        # A fabricated settled world: one plan's two-task scope — a
        # deterministic cut + a writer — compiled, run, and landed.
        output = Output(
            id=uuid.uuid4(), project_id=pu, type="post", language="en",
            payload={"body": "The launch post."},
        )
        cut = GraphNode(
            id=uuid.uuid4(), project_id=pu, type="video", state="done",
            spec={"tool": "cut_segments", "fill_key": "cut_segments#clips#0", "summary": "Cut segments"},
        )
        writer = GraphNode(
            id=uuid.uuid4(), project_id=pu, type="text", state="done",
            spec={
                "tool": "write_post", "fill_key": "write_post#post#0",
                "prompt": "Write a launch post.", "summary": "Post",
                "output_ids": [str(output.id)],
            },
        )
        plan_id = uuid.uuid4()
        snapshot = {
            "confirmation_id": "c1",
            "confirmed_at": "2026-09-23T00:00:00Z",
            "confirmed_via": "dock_pill",
            "plans": [{"plan_id": str(plan_id), "title": "Launch week"}],
            "compiled_scope": [
                {"tool": "cut_segments", "params": {"segments": [{"start": 6.0, "end": 14.4}]}},
                {"tool": "write_post", "params": {"language": "en"}},
            ],
            "quote": {"total": [100, 200], "per_task": []},
            "plan_task_map": {str(plan_id): [0, 2]},
        }
        run = WorkflowRun(
            id=uuid.uuid4(), project_id=pu, status="completed",
            context={"confirmed_scope": snapshot},
        )
        db.add_all([output, cut, writer, run])
        await db.commit()
        nodes = [cut, writer]

        # R20 路由器: plan_ref 双通道 over the real snapshot + live rows.
        route = route_revision(snapshot, nodes, plan_ref="1")
        ok("ordinal plan_ref resolves the plan's full slice (cut + writer)",
           route.status == "ok" and set(route.node_ids) == {str(cut.id), str(writer.id)}, route)
        route_by_id = route_revision(snapshot, nodes, plan_ref=str(plan_id))
        ok("verbatim plan_id resolves identically",
           route_by_id.status == "ok" and route_by_id.plan_id == str(plan_id), route_by_id)
        route_pin = route_revision(snapshot, nodes, output_id=str(output.id))
        ok("@output pin resolves straight to the producing node (+ owning plan)",
           route_pin.status == "ok" and route_pin.node_ids == (str(writer.id),)
           and route_pin.plan_id == str(plan_id), route_pin)
        legacy = route_revision(None, nodes, plan_ref="1")
        ok("legacy (no snapshot) degrades honestly to the @ channel",
           legacy.status == "degrade" and "@" in (legacy.reason or ""), legacy)
        oob = route_revision(snapshot, nodes, plan_ref="7")
        ok("out-of-range plan_ref degrades, never guesses",
           oob.status == "degrade" and "1..1" in (oob.reason or ""), oob)

        # R19 消费侧: prompt-consuming gate + ops assembly + composition.
        assembled = assemble_craft_revision(nodes, "Make it sharper.")
        ok("mixed set: edit_prompt on the writer + bare run, cut disclosed uncovered",
           assembled is not None
           and [op["op"] for op in assembled.ops] == ["edit_prompt", "run"]
           and assembled.ops[0]["node"] == str(writer.id)
           and assembled.uncovered == ("Cut segments",), assembled)
        ok("all-deterministic set degrades to None (the honest 'nothing here "
           "consumes a program')",
           assemble_craft_revision([cut], "Make it sharper.") is None)
        ok("compose_revised_program appends the user's clause verbatim",
           compose_revised_program("Write a launch post.", "Make it sharper.")
           == "Write a launch post.\n\nMake it sharper.")

        # The wiring door: the assembled edit_prompt lands; the program
        # honestly shows the revision clause (never a silent rewrite).
        assert assembled is not None
        await apply_wiring_ops(db, pu, [assembled.ops[0]])
        await db.commit()
        await db.refresh(writer)
        ok("the door lands the edit_prompt; the clause is visible in the program",
           writer.spec["prompt"] == "Write a launch post.\n\nMake it sharper.", writer.spec)
        try:
            await apply_wiring_ops(
                db, pu, [{"op": "edit_prompt", "node": str(uuid.uuid4()), "prompt": "x"}]
            )
        except WiringRejected:
            ok("an unknown node dies at the door (WiringRejected)", True)
        else:
            ok("an unknown node dies at the door (WiringRejected)", False, "no rejection")
        await db.rollback()

    await client.delete(f"/projects/{pid}")
    await client.aclose()
    print("  ✓ S-explore-3 deterministic tail ALL GREEN (LLM 修订拍位随常驻剧本座)")


asyncio.run(main())
