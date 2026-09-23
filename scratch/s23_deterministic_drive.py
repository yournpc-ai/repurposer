"""S23 deterministic-tail drive (MiniMax 429 期间的替身验证 — 永不开 PR).

Exercises everything S23 asserts EXCEPT the three LLM terminal selections:
the door chain (candidates → selects → plans ready) / I-EXPLORE-01 wiring
rejection / idempotent replay / no-timeline degradation / journey adoption
/ the graph API face (rank-blind, lane x=-464, zero edges, journey_id).

Run (from apps/api, dev API live):
    uv run python ../../scratch/s23_deterministic_drive.py
"""

import asyncio
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "scripts"))

import httpx  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.chat.exploration_tools import execute_exploration_tool  # noqa: E402
from app.chat.perception import SearchTranscriptParams, run_perception_tool  # noqa: E402
from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.schemas import AssetType  # noqa: E402
from app.models.tables import GraphNode, Journey, Project  # noqa: E402
from app.pipeline.graph_store import WiringRejected, apply_wiring_ops  # noqa: E402
from app.platform.auth import create_access_token  # noqa: E402
from chat_scenarios import make_user, seed_asset  # noqa: E402

BASE = "http://127.0.0.1:8000/api/v1"

SENTENCES = [
    (0.0, "Welcome back to the founder notes."),
    (6.0, "Today I answer the question everyone asks."),
    (12.0, "Our pricing is simple."),
    (15.0, "The pro tier costs ten dollars a month."),
    (21.0, "You can start free and upgrade when the team grows."),
    (28.0, "Let me switch gears to the roadmap."),
    (34.0, "Every pricing tier includes the analytics dashboard."),
    (41.0, "That is the whole announcement for this week."),
]


def words() -> list[dict]:
    out: list[dict] = []
    for line_start, sentence in SENTENCES:
        t = line_start
        for w in sentence.split():
            out.append({"word": w, "start": round(t, 2), "end": round(t + 0.4, 2)})
            t += 0.5
    return out


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
    res = await client.post("/projects", json={"title": "S23 deterministic drive", "event_name": ""})
    assert res.status_code == 201, res.text
    pid = res.json()["id"]
    pu = uuid.UUID(pid)
    asset_id = await seed_asset(
        pid, user_id, AssetType.VIDEO, "explore-talk.mp4",
        extracted_text=" ".join(s for _, s in SENTENCES),
        meta={"words": words(), "speaker_map": {"turns": [{"start": 0.0, "end": 48.0, "speaker": "host"}]}, "language": "en"},
        processed=True,
    )
    print("▶ S23 deterministic tail drive")

    async with AsyncSessionLocal() as db:
        project = (await db.execute(select(Project).where(Project.id == pu))).scalar_one()

        # 拍 2 读面: search_transcript finds the pricing cues.
        obs = await run_perception_tool(db, project, "search_transcript", SearchTranscriptParams(query="pricing"))
        ok("search_transcript hits with [start–end] anchors", "[12.0–" in obs.text and "pricing" in obs.text.casefold(), obs.text)

        # The door chain (what the three LLM beats would call).
        cs_text = await execute_exploration_tool(db, project, "propose_candidates", {
            "asset_id": asset_id, "topic": "pricing",
            "goal": "pricing clips for my launch post",
            "members": [
                {"start": 12.0, "end": 18.9, "excerpt": "Our pricing is simple. The pro tier costs ten dollars a month.", "speaker": "host"},
                {"start": 34.0, "end": 37.4, "excerpt": "Every pricing tier includes the analytics dashboard.", "speaker": "host"},
            ],
        })
        await db.commit()
        cs_id = re.search(r"candidate_set_id: ([0-9a-f-]{36})", cs_text).group(1)
        ok("propose_candidates lands (door accepts verbatim evidence)", "landed" in cs_text, cs_text)

        sel_text = await execute_exploration_tool(db, project, "propose_selects", {
            "candidate_set_id": cs_id,
            "selects": [
                {"member_index": 0, "verdict": "Most complete pricing answer", "reason": "Names the tier and the price in one breath."},
            ],
        })
        await db.commit()
        sel_id = re.search(r"select_id: ([0-9a-f-]{36})", sel_text).group(1)
        ok("propose_selects lands", "landed" in sel_text, sel_text)

        plan_text = await execute_exploration_tool(db, project, "propose_plans", {
            "plans": [
                {"select_id": sel_id, "title": "Pricing clip + post", "outputs": [{"kind": "clip"}, {"kind": "post", "language": "en"}]},
            ],
        })
        await db.commit()
        ok("propose_plans lands ready", "landed" in plan_text and "[ready]" in plan_text, plan_text)

        # A door rejection feeds the loop echo (paraphrase = not evidence).
        bad = await execute_exploration_tool(db, project, "propose_candidates", {
            "asset_id": asset_id, "topic": "pricing", "goal": "rejection probe",
            "members": [{"start": 12.0, "end": 13.9, "excerpt": "Our pricing is very simple indeed."}],
        })
        ok("paraphrase excerpt is a door rejection, never a crash", bad.startswith("The door rejected"), bad)

        # Journey ownership: one journey across the chain.
        nodes = (await db.execute(select(GraphNode).where(GraphNode.project_id == pu, GraphNode.type == "exploration"))).scalars().all()
        journeys = {str(n.journey_id) for n in nodes}
        ok("the chain rides ONE journey (R24)", len(journeys) == 1, journeys)
        ok("three kinds born in order", [n.spec["exploration_kind"] for n in nodes] == ["candidate_set", "select", "content_plan"], [n.spec["exploration_kind"] for n in nodes])
        ok("plan state ready, others ready", all(n.state == "ready" for n in nodes), [(n.spec["exploration_kind"], n.state) for n in nodes])

        # I-EXPLORE-01 execution-door rejection.
        for ops in (
            [{"op": "run", "nodes": [cs_id]}],
            [{"op": "delete_node", "node": sel_id}],
            [{"op": "connect", "from_node": cs_id, "to_node": sel_id}],
        ):
            try:
                await apply_wiring_ops(db, pu, ops)
            except WiringRejected:
                ok(f"wiring door rejects {ops[0]['op']}", True)
            else:
                ok(f"wiring door rejects {ops[0]['op']}", False)

        # Idempotent replay (a new goal → one mint, then adopt).
        idem_args = {
            "asset_id": asset_id, "topic": "pricing", "goal": "idem probe",
            "members": [{"start": 12.0, "end": 18.9, "excerpt": "Our pricing is simple. The pro tier costs ten dollars a month.", "speaker": "host"}],
        }
        first = await execute_exploration_tool(db, project, "propose_candidates", dict(idem_args))
        await db.commit()
        second = await execute_exploration_tool(db, project, "propose_candidates", dict(idem_args))
        await db.commit()
        id_of = lambda t: re.search(r"candidate_set_id: ([0-9a-f-]{36})", t).group(1)  # noqa: E731
        ok("idempotent replay returns the same artifact", id_of(first) == id_of(second), (first, second))

        # No-timeline degradation: honest read + door rejection.
        bare_id = await seed_asset(
            pid, user_id, AssetType.VIDEO, "explore-bare.mp4",
            extracted_text="A talk without word-level timestamps.",
            meta={"language": "en"}, processed=True,
        )
        obs2 = await run_perception_tool(db, project, "search_transcript", SearchTranscriptParams(query="pricing", asset_id=uuid.UUID(bare_id)))
        ok("no-timeline read is an honest empty", any(k in obs2.text for k in ("timeline-ready", "word-level", "No file assets")), obs2.text)
        rej = await execute_exploration_tool(db, project, "propose_candidates", {**idem_args, "asset_id": bare_id, "goal": "degradation probe"})
        ok("wordless asset is a door rejection", rej.startswith("The door rejected"), rej)
        await db.commit()

        journey_count = int((await db.execute(select(func.count()).select_from(Journey).where(Journey.project_id == pu))).scalar_one())
        ok("journeys = chain + idem probe (adopt never mints twins)", journey_count == 2, journey_count)

    # The graph API face.
    g = await client.get(f"/projects/{pid}/graph")
    assert g.status_code == 200, g.text
    graph = g.json()
    explore = [n for n in graph["nodes"] if n["type"] == "exploration"]
    ok("graph carries the exploration family", len(explore) >= 4, len(explore))
    ok("rank None on every exploration node (rank-blind)", all(n.get("rank") is None for n in explore))
    ok("journey_id on every exploration node", all(n.get("journey_id") for n in explore))
    ok("lane x = -464 on every exploration node", all(int(n["layout"]["x"]) == -464 for n in explore), [n["layout"] for n in explore])
    ids = {n["id"] for n in explore}
    ok("zero edges touch exploration nodes", not [e for e in graph["edges"] if {e["from_node"], e["to_node"]} & ids])
    kinds = {n["spec"].get("exploration_kind") for n in explore}
    ok("three kinds on the graph face", kinds == {"candidate_set", "select", "content_plan"}, kinds)
    # The select card's read-time projection source: parent set's member is
    # intact on the wire (the client resolves the range from it).
    cs = next(n for n in explore if n["spec"].get("exploration_kind") == "candidate_set" and len(n["spec"]["members"]) == 2)
    ok("candidate members ride the wire verbatim", cs["spec"]["members"][0]["start"] == 12.0, cs["spec"]["members"][0])

    await client.delete(f"/projects/{pid}")
    await client.aclose()
    print("  ✓ deterministic tail ALL GREEN (LLM beats pending quota)")


asyncio.run(main())
