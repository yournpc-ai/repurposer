"""zymix.ai multi-turn chat journey v2 (ADR-123 live 验收锚): the REAL product
path against the live stack. One scripted user:

  1. paste the zymix.ai link, ask for the launch film
     → absorb births web_page assets (B4 children included)
     → plan docks WITH the storyboard review hold (E1 消息块 v1)
     → (honest degrade: if the dock-time draft fails, auto mode starts the
       run without review — the journey then exercises POST-delivery
       revision instead)
  2. revision turn: slow to ~90s, numbers as plate cards     → v2
  3. revision turn: ending callback + brand sign-off         → v3
  4. verbal yes → start_run (confirmed_storyboard = latest block)
  5. run terminal → verify film output (duration / scenes / music)
  6. post-delivery revision turn → second run (修订旅程)

Every storyboard version is printed from the DB (the message-flow rows ARE
the transcript truth). The project is KEPT (keep=True) so the film is
inspectable in the UI — cleanup is the user's call.

Run from apps/api with the live stack up:
  NO_PROXY=127.0.0.1,localhost uv run python -u ../../scratch/demo-films/zymix_journey.py
"""

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api" / "scripts"))

URL = "https://www.zymix.ai/en/"
PID_COL = "zymix 官网介绍短片（多轮对话）"


def scene_line(i: int, s: dict) -> str:
    extra = ""
    if s["type"] == "ui":
        extra = f" page={s.get('page')} shot={s.get('shot')} frame={s.get('frame', True)}"
    elif s["type"] == "plate":
        extra = f" cards={[c.get('big') for c in s.get('cards', [])]}"
    return (
        f"  [{i:02d}] {s['type']:<8} {s.get('seconds')}s"
        f"{' narr' if s.get('narration') else ''}{extra}"
    )


async def storyboard_versions(conv_id: str) -> list[dict]:
    from sqlalchemy import select

    from app.models.database import AsyncSessionLocal
    from app.models.tables import Message

    async with AsyncSessionLocal() as db:
        rows = (
            (
                await db.execute(
                    select(Message)
                    .where(
                        Message.conversation_id == uuid.UUID(conv_id),
                        Message.intent["type"].astext == "storyboard",
                    )
                    .order_by(Message.seq)
                )
            )
            .scalars()
            .all()
        )
    return [r.intent for r in rows if isinstance(r.intent, dict)]


def print_storyboard(tag: str, block: dict) -> None:
    sb = block.get("storyboard") or {}
    scenes = sb.get("scenes") or []
    total = sum(s.get("seconds", 0) for s in scenes)
    print(f"\n--- storyboard {tag}: «{sb.get('name')}» — {len(scenes)} scenes, ~{total:.0f}s", flush=True)
    for i, s in enumerate(scenes):
        print(scene_line(i, s), flush=True)


async def run_states(pid: str) -> list[tuple[str, str, bool]]:
    from sqlalchemy import text

    from app.models.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                text(
                    "select id, status, context->'confirmed_storyboard' is not null "
                    "from workflow_runs where project_id = :pid order by created_at"
                ),
                {"pid": pid},
            )
        ).all()
    return [(str(r[0]), str(r[1]), bool(r[2])) for r in rows]


async def print_outputs(pid: str) -> None:
    from sqlalchemy import select

    from app.models.database import AsyncSessionLocal
    from app.models.tables import Output

    async with AsyncSessionLocal() as db:
        outs = (
            (await db.execute(select(Output).where(Output.project_id == uuid.UUID(pid))))
            .scalars()
            .all()
        )
    for o in outs:
        payload = o.payload or {}
        files = o.files or {}
        print(
            f"output {str(o.id)[:8]}: type={o.type} render_status={o.render_status} "
            f"duration={payload.get('duration')}s scenes={payload.get('scene_count')} "
            f"aspect={payload.get('aspect')} video={'video' in files}",
            flush=True,
        )


async def main() -> None:
    import chat_scenarios as cs

    uid = await cs.make_user()
    ctx = cs.Ctx(uid, keep=True)  # the film stays inspectable in the UI
    # Dock-time storyboard drafts ride INSIDE the chat turn — at tonight's
    # provider throughput a turn can run 10-20 min; the harness's 300s
    # default is calibrated for plan turns without a draft.
    import httpx

    ctx.client.timeout = httpx.Timeout(1800.0)
    await cs.topup_wallet(uid)
    pid = await ctx.new_project(PID_COL)
    print(f"project: {pid}  user: {uid}", flush=True)

    # ---- turn 1: paste the link, ask for the film ------------------------
    t1 = await ctx.chat(pid, f"这是我们产品的官网，帮我做一条官网介绍短片：{URL}")
    conv = t1["conversation_id"]
    msg = (t1.get("assistant_message") or {}).get("content") or ""
    print(f"\n[turn1] {msg[:400]}", flush=True)

    # worker 真采集（playwright 引擎 + 子页发现）——等全部落定
    from sqlalchemy import select

    from app.models.database import AsyncSessionLocal
    from app.models.tables import Asset
    from app.models.schemas import AssetStatus, AssetType

    deadline = asyncio.get_event_loop().time() + 420.0
    while asyncio.get_event_loop().time() < deadline:
        async with AsyncSessionLocal() as db:
            rows = (
                (
                    await db.execute(
                        select(Asset)
                        .where(
                            Asset.project_id == uuid.UUID(pid),
                            Asset.type == AssetType.WEB_PAGE,
                        )
                        .order_by(Asset.created_at)
                    )
                )
                .scalars()
                .all()
            )
            if rows and all(
                r.processing_status == AssetStatus.COMPLETED for r in rows
            ):
                break
            if any(r.processing_status == AssetStatus.FAILED for r in rows):
                print(f"capture FAILED: {[str(r.id)[:8] for r in rows]}", flush=True)
                break
        await asyncio.sleep(3)
    print(f"\ncapture: {len(rows)} page asset(s) — {[str(r.processing_status) for r in rows]}", flush=True)

    # 分镜 v1（dock 期起草成功才有块；失败 = auto 直开的诚实降级）
    v1 = await storyboard_versions(conv)
    for r in await run_states(pid):
        print(f"run state: {r[0][:8]} {r[1]} confirmed_sb={r[2]}", flush=True)

    run_id = t1.get("run_id")
    if v1:
        print_storyboard("v1 (dock)", v1[-1])

        # ---- turn 2: pacing + plate revision -----------------------------
        t2 = await ctx.chat(
            pid,
            "节奏放慢一点，整条做到一分半左右。页面里的数字卖点（性能、规模之类）"
            "用数字卡单独呈现一幕，别埋在页面镜头里。",
        )
        print(f"\n[turn2] {((t2.get('assistant_message') or {}).get('content') or '')[:300]}", flush=True)
        v2 = await storyboard_versions(conv)
        if len(v2) > len(v1):
            print_storyboard(f"v{len(v2)} (pacing+plate)", v2[-1])
        else:
            print("(no new storyboard version — the turn answered without redrafting)", flush=True)

        # ---- turn 3: ending callback --------------------------------------
        t3 = await ctx.chat(pid, "结尾再回扣一下开头那句话，最后给出品牌名和官网地址。")
        print(f"\n[turn3] {((t3.get('assistant_message') or {}).get('content') or '')[:300]}", flush=True)
        v3 = await storyboard_versions(conv)
        if len(v3) > len(v2):
            print_storyboard(f"v{len(v3)} (ending)", v3[-1])

        # ---- turn 4: verbal yes → start_run --------------------------------
        t4 = await ctx.chat(pid, "可以，就这样开工吧。")
        print(f"\n[turn4] {((t4.get('assistant_message') or {}).get('content') or '')[:300]}", flush=True)
        run_id = t4.get("run_id") or run_id
        states = await run_states(pid)
        for r in states:
            print(f"run state: {r[0][:8]} {r[1]} confirmed_sb={r[2]}", flush=True)
    else:
        print("\n(no storyboard block — dock-time draft degraded; auto mode started the run without review)", flush=True)

    assert run_id, f"no run born: {list(t1)}"
    print(f"\nrun: {run_id} — waiting for terminal…", flush=True)

    # ---- run to terminal (90s 片编排+合成+渲染，宽车道) --------------------
    final = await cs.wait_run_terminal(run_id, timeout=1800.0)
    print(f"\nrun terminal: {final}", flush=True)
    await print_outputs(pid)

    # ---- post-delivery revision journey (修订 = 再来一版) ------------------
    if final == "completed":
        t5 = await ctx.chat(pid, "开头那句话再短一点，更有力一些，其余不变，重新出一版。")
        print(f"\n[turn5 post-delivery revision] {((t5.get('assistant_message') or {}).get('content') or '')[:300]}", flush=True)
        states = await run_states(pid)
        for r in states:
            print(f"run state: {r[0][:8]} {r[1]} confirmed_sb={r[2]}", flush=True)
        new_run = next((r for r in states if r[1] not in ("completed", "failed")), None)
        if new_run is not None:
            final2 = await cs.wait_run_terminal(new_run[0], timeout=1800.0)
            print(f"\nrevision run terminal: {final2}", flush=True)
            await print_outputs(pid)

    print(f"\nDONE — project {pid} kept for UI inspection", flush=True)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
