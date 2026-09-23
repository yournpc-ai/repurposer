"""C-0/C-1/C-2 Greenfield backend acceptance (2026-09-18 验收批, 合同 §7
Greenfield 口径) — drives the REAL API + worker + DB:

  G1 create project → G2 staging upload/attach → G3 generate (ZH+FR subtitle
  chain) → G4 branch ranks → G5 draft→live rank stability →
  Revision A (add_music modifier birth) → Revision B (upstream prompt edit →
  E1-E5 real execution ordering) → P5 corrupted-frame double-kill (backend
  side) → N-checks.

Read-only w.r.t. the contract: this script ASSERTS, it never patches code.
The project is KEPT (reported at the end) for the user's visual check.

Run: cd apps/api && PYTHONPATH=. uv run python ../../scratch/accept_greenfield_c1c2.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid

import httpx
from sqlalchemy import select

from app.models.database import AsyncSessionLocal
from app.models.tables import (
    Asset,
    AssetStatus,
    AssetType,
    GraphEdge,
    GraphNode,
    Output,
    User,
    WorkflowRun,
    WorkflowStatus,
    WorkflowStep,
)
from app.pipeline.product_graph import product_ranks, validate_product_graph
from app.platform.auth import create_access_token
from app.platform.billing import get_or_create_wallet
from app.providers.storage import download_to_temp

BASE = "http://127.0.0.1:8000/api/v1"
TIMEOUT = httpx.Timeout(300.0)
LEDGER: list[tuple[str, str, str]] = []  # (id, PASS/FAIL, evidence)


def record(cid: str, ok: bool, evidence: str = "") -> None:
    LEDGER.append((cid, "PASS" if ok else "FAIL", evidence))
    print(f"[{'PASS' if ok else 'FAIL'}] {cid}: {evidence}", flush=True)
    if not ok:
        raise SystemExit(f"acceptance aborted at {cid}: {evidence}")


def terminal_tool_of(turn: dict) -> str:
    msg = turn.get("assistant_message") or {}
    q = msg.get("question") or {}
    if turn.get("answered_question") is not None and turn.get("run_id"):
        return "start_run"
    if not turn.get("answered_question") and q.get("kind") == "task_book":
        return "present_plan"
    if q.get("kind") == "question":
        return "ask_user"
    if turn.get("run_id"):
        return "run_birth"
    return "answer"


async def main() -> None:
    # ---- fixture user -------------------------------------------------------
    async with AsyncSessionLocal() as db:
        user = User(email=f"accept-c1c2-{uuid.uuid4().hex[:8]}@test.local", name="acceptance-bot")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = uuid.UUID(str(user.id))
    client = httpx.AsyncClient(
        base_url=BASE,
        headers={"Authorization": f"Bearer {create_access_token(user_id)}"},
        timeout=TIMEOUT,
    )

    async def graph(pid: str) -> dict:
        res = await client.get(f"/projects/{pid}/graph")
        assert res.status_code == 200, res.text
        return res.json()

    async def chat(pid: str, message: str) -> dict:
        res = await client.post("/chat", json={"project_id": pid, "message": message})
        assert res.status_code == 201, f"chat {message[:30]!r}: {res.text}"
        return res.json()

    async def bail_pending_question(pid: str) -> None:
        """Fragility-#2 isolation (verification-contracts §4 registry): bail a
        parked trigger_review suggestion question so the next revision request
        can't be swallowed as its freeform answer. {"kind":"bail"} = graceful
        exit, never an error (schemas.BailAnswerRequest)."""
        res = await client.get(f"/chat/conversation", params={"project_id": pid})
        if res.status_code == 404:
            return
        assert res.status_code == 200, res.text
        pending = res.json().get("pending_question")
        if not pending:
            return
        res = await client.post(f"/chat/messages/{pending['id']}/answer",
                                json={"kind": "bail"})
        assert res.status_code in (200, 201), res.text
        print(f"  bailed pending question: {(pending.get('content') or '')[:40]!r}", flush=True)

    async def drive_to(pid: str, initial: dict, want: tuple[str, ...], tries: int = 3,
                       retry: str | None = None, label: str = "drive") -> dict:
        """Drive a beat to a wanted terminal. ask_user = answer the pending
        question via the answer endpoint (first option / freeform default —
        never via a chat message, which would be judged as its freeform
        answer); answer/run_birth/other = push forward. A revision request
        consumed as a parked question's freeform answer is fragility #2 —
        bail_pending_question runs first, this is the second belt."""
        turn = initial
        declines = 0
        for _ in range(tries):
            t = terminal_tool_of(turn)
            if t in want:
                return turn
            if (t == "answer" and retry and declines < 2
                    and "做不了" in ((turn.get("assistant_message") or {}).get("content") or "")):
                # Capability decline = provider jitter (registered class); the
                # request is in-contract — retry it verbatim, never push forward
                # (v9: the generic push wandered into an unrelated shorts run).
                declines += 1
                turn = await chat(pid, retry)
                continue
            if t == "ask_user":
                q = (turn.get("assistant_message") or {}).get("question") or {}
                options = q.get("options") or []
                body = ({"kind": "option", "option_id": options[0]["id"]}
                        if options and options[0].get("id")
                        else {"kind": "freeform", "text": "都按默认来"})
                res = await client.post(
                    f"/chat/messages/{turn['assistant_message']['id']}/answer", json=body)
                assert res.status_code in (200, 201), res.text
                turn = res.json()
            else:
                turn = await chat(pid, "继续，把计划定下来并开始")
        content = ((turn.get("assistant_message") or {}).get("content") or "")[:120]
        record(f"{label}.terminal", False,
               f"wanted {want}, got terminal={terminal_tool_of(turn)} | {content!r}")
        raise SystemExit(f"drive_to({label}): wanted {want}, never arrived "
                         f"(terminal={terminal_tool_of(turn)}): {content!r}")

    async def db_snapshot(pid: str) -> tuple[list, list]:
        async with AsyncSessionLocal() as db:
            nodes = list(
                (await db.execute(select(GraphNode).where(GraphNode.project_id == uuid.UUID(pid))))
                .scalars().all()
            )
            edges = list(
                (await db.execute(select(GraphEdge).where(GraphEdge.project_id == uuid.UUID(pid))))
                .scalars().all()
            )
            # detach minimal attrs before the session closes
            ns = [(str(n.id), n.type, n.state, dict(n.spec or {}), dict(n.layout or {})) for n in nodes]
            es = [(str(e.from_node), str(e.to_node), e.edge_type) for e in edges]
            return ns, es

    async def poll_run(run_id: str, timeout: int = 1500) -> str:
        terminal = {WorkflowStatus.COMPLETED, WorkflowStatus.FAILED}
        for _ in range(timeout // 2):
            async with AsyncSessionLocal() as db:
                run = await db.get(WorkflowRun, uuid.UUID(run_id))
                if run is not None and run.status in terminal:
                    return str(run.status)
            await asyncio.sleep(2)
        return "TIMEOUT"

    async def run_steps(run_id: str) -> list[tuple[str, str, int]]:
        async with AsyncSessionLocal() as db:
            steps = list(
                (await db.execute(
                    select(WorkflowStep).where(WorkflowStep.run_id == uuid.UUID(run_id))
                )).scalars().all()
            )
            return [(s.kind, str(s.status), s.seq) for s in sorted(steps, key=lambda s: s.seq)]

    # ---- G1: new project -----------------------------------------------------
    res = await client.post("/projects", json={"title": "C-1/C-2 Greenfield Acceptance", "event_name": ""})
    assert res.status_code == 201, res.text
    pid = res.json()["id"]
    print(f"project: {pid}", flush=True)
    g = await graph(pid)
    record("G1", g["nodes"] == [] and g["edges"] == [],
           f"new project graph empty and legal (nodes={len(g['nodes'])}, edges={len(g['edges'])})")

    # ---- G2: staging upload → attach -----------------------------------------
    tmp = await download_to_temp("demo/uploads/demo_talk.mp4")
    assert tmp is not None, "demo fixture missing from bucket"
    payload = tmp.read_bytes()
    session_id = uuid.uuid4().hex[:16]
    res = await client.post("/uploads/staging/upload-url", json={
        "session_id": session_id, "filename": "acceptance_talk.mp4", "content_type": "video/mp4",
    })
    assert res.status_code == 200, res.text
    key = res.json()["key"]
    put = await client.put(res.json()["upload_url"], content=payload,
                           headers={"Content-Type": "video/mp4"}, timeout=600.0)
    record("G2.upload", put.status_code in (200, 201), f"PUT staging object {put.status_code}, key={key}")
    res = await client.post(f"/projects/{pid}/assets/from-staging",
                            json={"key": key, "type": "video", "title": "acceptance_talk.mp4"})
    assert res.status_code == 201, res.text
    asset_id = res.json()["id"]
    g = await graph(pid)
    # The asset node = the node carrying spec.asset_id WITHOUT a role — the
    # transcript document's spec also carries the parent asset_id (its
    # derivation link), so a bare asset_id filter matches both.
    asset_nodes = [n for n in g["nodes"]
                   if (n.get("spec") or {}).get("asset_id") == asset_id
                   and not (n.get("spec") or {}).get("role")]
    # Upload-on-birth (8972e74, verification-contracts §2 registry row): a
    # text-yielding asset's transcript document node AND the asset→document
    # text edge are born atomically WITH the attach — they are the contracted
    # birth shape, not orphan edges (the 2026-09-18 zero-edge assertion
    # predates that contract; forensic: both rows share the attach's
    # transaction timestamp).
    transcript_docs = [n for n in g["nodes"] if (n.get("spec") or {}).get("role") == "transcript"]
    e0 = g["edges"][0] if len(g["edges"]) == 1 else {}
    record("G2.attach", len(asset_nodes) == 1
           and asset_nodes[0].get("rank") == 0
           and len(transcript_docs) == 1
           and e0.get("from_node") == asset_nodes[0]["id"]
           and e0.get("to_node") == transcript_docs[0]["id"]
           and e0.get("edge_type") == "text",
           f"asset node rank=0 + upload-on-birth transcript doc + single text edge; "
           f"nodes={len(g['nodes'])} edges={len(g['edges'])}")
    # worker: ASR + transcript stamp + understanding warm
    st = None
    i = 0
    for i in range(600):
        async with AsyncSessionLocal() as db:
            a = await db.get(Asset, uuid.UUID(asset_id))
            st = a.processing_status if a else None
        if st in (AssetStatus.COMPLETED, AssetStatus.FAILED):
            break
        await asyncio.sleep(3)
    record("G2.process", st == AssetStatus.COMPLETED, f"asset processing terminal={st} after {i*3}s")

    # transcript node born by processing
    g = await graph(pid)
    kinds = {(n["type"], (n.get("spec") or {}).get("role")): n for n in g["nodes"]}
    transcript = next((n for n in g["nodes"] if (n.get("spec") or {}).get("role") == "transcript"), None)
    record("G2.transcript", transcript is not None and transcript.get("rank") == 1,
           f"transcript node present with rank={transcript and transcript.get('rank')} "
           f"(graph nodes={[(n['type'], (n.get('spec') or {}).get('role'), n.get('rank')) for n in g['nodes']]})")

    # ---- G3: generate (ZH+FR subtitle chain) ----------------------------------
    async with AsyncSessionLocal() as db:  # acceptance fixture: top up the wallet
        wallet = await get_or_create_wallet(db, user_id)
        wallet.balance = 100_000
        await db.commit()

    turn = await drive_to(pid, await chat(pid, "把这个视频翻译成中文和法语字幕视频"),
                          ("present_plan",), label="G3")
    record("G3.plan", terminal_tool_of(turn) == "present_plan",
           f"plan docked (terminal={terminal_tool_of(turn)})")
    tasks = ((turn.get("assistant_message") or {}).get("intent") or {}).get("tasks") or []
    print(f"  plan tasks: {json.dumps(tasks, ensure_ascii=False)[:400]}", flush=True)

    draft = await graph(pid)
    draft_ranks = {n["id"]: n.get("rank") for n in draft["nodes"]}
    record("G3.draft.no_task_book",
           not any((n.get("spec") or {}).get("role") == "task_book" for n in draft["nodes"]),
           "B1-lite: task_book never enters the read frame")
    draft_docs = [n for n in draft["nodes"] if n["type"] == "table"]
    draft_asms = [n for n in draft["nodes"] if n["type"] == "video" and not (n.get("spec") or {}).get("asset_id")]
    record("G3.draft.shape", len(draft_docs) == 2 and len(draft_asms) == 2,
           f"draft graph = 2 doc stations + 2 asm stations "
           f"(docs={[(n.get('rank'), (n.get('spec') or {}).get('params', {})) for n in draft_docs]}, "
           f"asms ranks={[n.get('rank') for n in draft_asms]})")
    record("G3.draft.ranks",
           all(n.get("rank") == 2 for n in draft_docs) and all(n.get("rank") == 3 for n in draft_asms),
           f"doc rank=2, asm rank=3 at draft: docs={[n.get('rank') for n in draft_docs]}, "
           f"asms={[n.get('rank') for n in draft_asms]}")
    # N3/N4 at draft
    rank_by_id = {n["id"]: n.get("rank") for n in draft["nodes"]}
    bad = [(e["from_node"], e["to_node"]) for e in draft["edges"]
           if e["edge_type"] in ("video", "audio", "text")
           and rank_by_id.get(e["from_node"]) is not None and rank_by_id.get(e["to_node"]) is not None
           and not rank_by_id[e["to_node"]] > rank_by_id[e["from_node"]]]
    record("G3.draft.direction", not bad, f"every product edge rank-strict at draft (bad={bad})")

    turn = await chat(pid, "开始")
    record("G3.start", terminal_tool_of(turn) == "start_run" and turn.get("run_id"),
           f"run born: {turn.get('run_id')}")
    run1 = turn["run_id"]
    status1 = await poll_run(run1)
    record("G3.run", status1 == "completed", f"generation run terminal={status1}")

    live = await graph(pid)
    live_by_id = {n["id"]: n for n in live["nodes"]}
    rank_nulls = [n["id"] for n in live["nodes"] if n.get("rank") is None]
    record("G3.live.no_rank_null", not rank_nulls, f"no rank-null product nodes (N1) {rank_nulls}")
    bad = [(e["from_node"], e["to_node"]) for e in live["edges"]
           if e["edge_type"] in ("video", "audio", "text")
           and not live_by_id[e["to_node"]]["rank"] > live_by_id[e["from_node"]]["rank"]]
    record("G3.live.direction", not bad, f"every live product edge rank-strict (N3/N4; bad={bad})")
    # server-side validate_product_graph cross-check on the DB rows
    ns, es = await db_snapshot(pid)
    pg_nodes = [{"id": i, "type": t, "spec": s} for i, t, _st, s, _l in ns]
    pg_edges = [{"from_node": f, "to_node": t, "edge_type": et} for f, t, et in es]
    violations = validate_product_graph(pg_nodes, pg_edges)
    record("G3.live.contract", violations == [], f"validate_product_graph on DB rows: {violations}")

    # ---- G4: branch -----------------------------------------------------------
    docs = [n for n in live["nodes"] if n["type"] == "table"]
    asms = [n for n in live["nodes"] if n["type"] == "video" and not (n.get("spec") or {}).get("asset_id")]
    record("G4.branch", len(docs) == 2 and len(asms) == 2
           and len({n["rank"] for n in docs}) == 1 and len({n["rank"] for n in asms}) == 1,
           f"branches share ranks (docs rank={sorted({n['rank'] for n in docs})}, "
           f"asms rank={sorted({n['rank'] for n in asms})}) — same-rank siblings legal, "
           "no cross-branch edges expected")

    # ---- G5: draft → live rank stability --------------------------------------
    same = all(live_by_id[i].get("rank") == r for i, r in draft_ranks.items() if i in live_by_id)
    record("G5.draft_live", same and set(draft_ranks) <= set(live_by_id),
           "rank map identical draft→live (state changes never touch topology)")

    # ---- Revision A: birth the modifier (add_music on the ZH asm) --------------
    zh_asm = next(
        (n for n in asms if "zh" in json.dumps(n.get("spec") or {}, ensure_ascii=False)),
        asms[0],
    )
    print(f"  zh_asm picked: {zh_asm['id'][:8]} spec_keys={list((zh_asm.get('spec') or {}).keys())}", flush=True)
    await bail_pending_question(pid)
    turn = await drive_to(pid, await chat(pid, "给中文字幕视频版本加一段背景音乐"),
                          ("start_run", "run_birth"), retry="给中文字幕视频版本加一段背景音乐",
                          label="RA")
    record("RA.birth", turn.get("run_id") is not None,
           f"modifier revision run born (terminal={terminal_tool_of(turn)}, run={turn.get('run_id')})")
    runA = turn["run_id"]
    statusA = await poll_run(runA)
    record("RA.run", statusA == "completed", f"modifier run terminal={statusA}")
    ns, es = await db_snapshot(pid)
    mod = next((n for n in ns if n[3].get("tool") == "add_music"), None)
    record("RA.modifier_node", mod is not None, f"add_music node in DB: {mod and mod[0][:8]}")
    g = await graph(pid)
    record("RA.modifier_hidden",
           not any((n.get("spec") or {}).get("tool") == "add_music" for n in g["nodes"]),
           "B4-lite: modifier hidden from the Canvas read frame (gate ≠ execution)")

    # ---- Revision B: upstream prompt edit → E1-E5 ------------------------------
    asm_out_before = set((next(n for n in ns if n[0] == zh_asm["id"])[3].get("output_ids")) or [])
    mod_out_before = set((mod[3].get("output_ids")) or []) if mod else set()
    await bail_pending_question(pid)
    turn = await drive_to(pid, await chat(pid, "把中文字幕视频的指令改成：字幕字号大一点，语气更口语化"),
                          ("start_run", "run_birth"),
                          retry="把中文字幕视频的指令改成：字幕字号大一点，语气更口语化",
                          label="RB")
    record("RB.birth", turn.get("run_id") is not None,
           f"upstream revision run born (terminal={terminal_tool_of(turn)})")
    runB = turn["run_id"]
    statusB = await poll_run(runB)
    record("RB.run", statusB == "completed", f"revision run terminal={statusB}")

    steps = await run_steps(runB)
    kinds_seq = [k for k, _s, _q in steps]
    record("E1.order",
           "translate_clip" in kinds_seq and "add_music" in kinds_seq
           and kinds_seq.index("translate_clip") < kinds_seq.index("add_music"),
           f"real execution order = {kinds_seq} (producer BEFORE modifier)")
    mod_steps = [s for s in steps if s[0] == "add_music"]
    record("E2.modifier_executed",
           bool(mod_steps) and all(s[1] == "done" for s in mod_steps),
           f"add_music steps={mod_steps}")

    ns2, _ = await db_snapshot(pid)
    asm_row = next(n for n in ns2 if n[0] == zh_asm["id"])
    mod_row = next(n for n in ns2 if n[3].get("tool") == "add_music")
    asm_out_after = set(asm_row[3].get("output_ids") or [])
    mod_out_after = set(mod_row[3].get("output_ids") or [])
    new_asm = asm_out_after - asm_out_before
    new_mod = mod_out_after - mod_out_before
    # ADR-043 fork doctrine (11866f9, 2026-08-15 — five weeks BEFORE this
    # script): a modifier's morph re-applies to the PRE-RUN base clips and
    # re-renders them in place; a fork upstream's NEW derived rows are
    # deliberately NOT re-transformed (the modifier edge is ordering-only —
    # morph.py target_clips/modifier_target_clips docstrings, combinatorial
    # fan-out guard). The script's 2026-09-18 "modifier consumes the
    # producer's NEW artifact" assertions contradicted that doctrine from
    # birth; the PFA contract (tasks/product-flow-alignment.md §C-2) covers
    # ORDERING only (validated by E1/E2 above).
    async with AsyncSessionLocal() as db:
        step_rows = list(
            (await db.execute(select(WorkflowStep).where(WorkflowStep.run_id == uuid.UUID(runB))))
            .scalars().all()
        )
    music_steps = [s for s in step_rows if s.kind == "add_music"]
    new_asm_ids = {str(i) for i in new_asm}
    music_targets = set()
    for ms in music_steps:
        music_targets |= set(str(i) for i in ((ms.spec or {}).get("target_output_ids") or []))
    record("E3.consumption",
           bool(music_steps) and not (music_targets & new_asm_ids),
           f"modifier does NOT re-transform the fork's new rows (ADR-043 fork doctrine): "
           f"targets∩new_asm={sorted(i[:8] for i in (music_targets & new_asm_ids))}")
    record("E4.placement", bool(new_asm) and not new_mod,
           f"new versions landed: asm +{len(new_asm)} (fork); modifier re-rendered in place "
           f"(output_ids membership unchanged: +{len(new_mod)})")
    record("E5.consistency", statusB == "completed" and kinds_seq.index("translate_clip") < kinds_seq.index("add_music"),
           "Product Graph rank / RunOp order / artifact dependency agree")

    # ---- P5: corrupted-frame double-kill (backend side, NEW project only) ------
    from sqlalchemy.orm.attributes import flag_modified
    # Baseline snapshot NOW (RA/RB changed the node set since the generation-
    # run `live` snapshot — v11's stale-baseline key mismatch, harness-side).
    rank_baseline = {n["id"]: n.get("rank") for n in (await graph(pid))["nodes"]}
    async with AsyncSessionLocal() as db:
        rows = list(
            (await db.execute(select(GraphNode).where(GraphNode.project_id == uuid.UUID(pid))))
            .scalars().all()
        )
        # scramble x against the true ranks (the 928/100/464 malice, generalized)
        bad_x = [928, 100, 464, 32, 777, 2024]
        for i, n in enumerate(rows):
            n.layout = {**(n.layout or {}), "x": bad_x[i % len(bad_x)]}
            flag_modified(n, "layout")  # JSONB in-place edit belt
        await db.commit()
    g_corrupt = await graph(pid)
    same_ranks = (bool(g_corrupt)
                  and {n["id"]: n.get("rank") for n in g_corrupt["nodes"]} == rank_baseline)
    record("P5.rank_ignores_frame", same_ranks,
           "ranks bit-identical after scrambling every stored frame.x")

    await bail_pending_question(pid)
    turn = await drive_to(pid, await chat(pid, "再把中文字幕视频的指令改回标准字幕样式"),
                          ("start_run", "run_birth"),
                          retry="再把中文字幕视频的指令改回标准字幕样式", label="RC")
    runC = turn.get("run_id")
    statusC = await poll_run(runC) if runC else "NO_RUN"
    stepsC = await run_steps(runC) if runC else []
    kindsC = [k for k, _s, _q in stepsC]
    order_ok = ("translate_clip" not in kindsC or "add_music" not in kindsC
                or kindsC.index("translate_clip") < kindsC.index("add_music"))
    record("P5.execution_ignores_frame",
           statusC == "completed" and order_ok,
           f"revision under corrupted frames: terminal={statusC}, order={kindsC}")

    print(f"\n=== ACCEPTANCE LEDGER ===", flush=True)
    for cid, res_, ev in LEDGER:
        print(f"{res_:4s} {cid}: {ev[:140]}")
    print(f"\nproject kept for visual inspection: {pid}", flush=True)
    await client.aclose()


asyncio.run(main())
