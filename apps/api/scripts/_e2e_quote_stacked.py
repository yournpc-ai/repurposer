"""quote-cards v3 真管线 e2e (P1 验收, 2026-08-27): dock 路径 + 叠卡产物形态.

简报验收流（quote-cards-redesign 验证清单）:
  chat 发"做一张金句卡" → caption dock → 答 bilingual → Start →
  产物 = 1 张叠卡（不再是 N 条单卡）+ 中文正常换行 + 合成图 key 在项目作用域

步骤:
  1. /tmp/demo_talk.mp4 (171s 中文演讲) 上传 → 等 ASR
  2. chat "做一张金句卡"（无双语关键词）→ 必须 dock caption_mode 三选项
  3. answer caption_mode_bilingual → 必须 dock task_book，pending_intent
     含 write_quotes 且 caption_mode="bilingual"（answer 回放路径）
  4. answer kind=start → run_id
  5. run completed + render completed
  6. DB 断言（v3 产物形态）:
     - 恰好 1 个 type=clip Output，source_ref.quote_chain=True，
       chain_length >= 2（v1 的 N 条单卡 fan-out 已死）
     - render_spec.image_shots[0].image_url 落在项目作用域
       {user_id}/outputs/projects/{pid}/quote-chain-*.png（D3：用户产物
       禁写 demo/ 前缀）
  7. 下载合成 PNG → /tmp/quote_chain_e2e.png（人工目检中文换行）
  8. FK 清理（worker 会抢跑手工 run 的数据，验证完即清）

Prereqs: dev.sh 栈在跑（api + worker + render）；TOS 走代理时
HTTPS_PROXY 需在此进程环境里（httpx 默认 trust_env）。
"""
import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE = os.getenv("SCENARIO_API_BASE", "http://127.0.0.1:8000/api/v1")
LOCAL_VIDEO = Path("/tmp/demo_talk.mp4")
COMPOSITE_OUT = Path("/tmp/quote_chain_e2e.png")
TIMEOUT_S = 600


def fail(msg, ctx=None):
    print(f"\n✗ {msg}", file=sys.stderr)
    if ctx is not None:
        print(json.dumps(ctx, indent=2, ensure_ascii=False, default=str), file=sys.stderr)
    sys.exit(1)


def ok(msg):
    print(f"  ✓ {msg}", flush=True)


async def setup_user_and_token():
    from sqlalchemy import select

    from app.models.database import AsyncSessionLocal
    from app.models.tables import User
    from app.platform.auth import create_access_token

    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).limit(1))).scalar_one_or_none()
        if user is None:
            fail("no test user in DB — abort")
        return str(user.id), create_access_token(user.id)


async def upload_asset(client, pid, file_path):
    r = await client.post(
        f"/projects/{pid}/assets/upload-url",
        json={"filename": file_path.name, "content_type": "video/mp4"},
    )
    if r.status_code != 200:
        fail("get upload-url", r.text)
    info = r.json()
    file_bytes = file_path.read_bytes()
    async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=30)) as c:
        r2 = await c.put(
            info["upload_url"], content=file_bytes,
            headers={"Content-Type": "video/mp4"},
        )
        if r2.status_code not in (200, 204):
            fail("PUT to TOS", f"HTTP {r2.status_code}: {r2.text[:200]}")
    ok(f"uploaded {len(file_bytes)} bytes to TOS")
    r = await client.post(
        f"/projects/{pid}/assets",
        json={"key": info["key"], "type": "video", "title": file_path.name},
    )
    if r.status_code != 201:
        fail("create asset", r.text)
    return r.json()


async def wait_for_asr(client, pid, asset_id, timeout_s=300):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = await client.get(f"/projects/{pid}/assets/{asset_id}")
        if r.status_code == 200:
            a = r.json()
            status = a.get("processing_status")
            if status == "completed":
                ok(f"ASR completed: duration={a.get('duration_seconds')}s")
                return a
            if status == "failed":
                fail("ASR failed", a)
            print(f"  · ASR polling… status={status}", flush=True)
        await asyncio.sleep(5)
    fail(f"ASR did not complete within {timeout_s}s")


async def wait_for_run(client, pid, timeout_s=300):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = await client.get(f"/projects/{pid}/runs")
        if r.status_code == 200:
            runs = r.json()
            if runs:
                last = runs[0]
                if last.get("status") in ("completed", "failed"):
                    return last
                print(f"  · run status={last.get('status')}", flush=True)
        await asyncio.sleep(5)
    fail(f"run did not complete within {timeout_s}s")


async def wait_clip_rendered(client, pid):
    deadline = time.time() + TIMEOUT_S
    while time.time() < deadline:
        r = await client.get(f"/projects/{pid}/results")
        if r.status_code == 200:
            clips = [o for o in (r.json().get("outputs") or []) if o.get("type") == "clip"]
            if clips:
                rs = clips[0].get("render_status")
                if rs == "completed":
                    return clips[0]
                if rs == "failed":
                    fail("clip render failed", clips[0])
                print(f"  · render status={rs}", flush=True)
        await asyncio.sleep(5)
    fail(f"render did not complete within {TIMEOUT_S}s")


async def assert_v3_product_shape(pid, user_id):
    """v3 产物形态断言（DB 直读 — results 端点不暴露 source_ref）。"""
    from sqlalchemy import select

    from app.models.database import AsyncSessionLocal
    from app.models.tables import Output

    async with AsyncSessionLocal() as db:
        outputs = list(
            (await db.execute(select(Output).where(Output.project_id == pid)))
            .scalars()
            .all()
        )
    clips = [o for o in outputs if o.type == "clip"]
    quote_clips = [o for o in clips if (o.source_ref or {}).get("quote_card")]
    if len(quote_clips) != 1:
        fail(
            f"expected exactly 1 quote-card clip Output (v1 fan-out retired), got {len(quote_clips)}",
            [{"id": str(o.id), "source_ref": o.source_ref} for o in clips],
        )
    clip = quote_clips[0]
    ref = clip.source_ref or {}
    if not ref.get("quote_chain"):
        fail("stacked path not taken — source_ref.quote_chain missing", ref)
    if int(ref.get("chain_length") or 0) < 2:
        fail(f"chain_length < 2: {ref.get('chain_length')}", ref)
    ok(f"1 张叠卡: quote_chain=True chain_length={ref['chain_length']} (fan-out 已死)")

    spec = clip.render_spec or {}
    # ClipSpec nests the stills under ``source`` (source.image_shots /
    # source.image_urls) — not at the top level.
    source = spec.get("source") or {}
    shots = source.get("image_shots") or []
    image_url = shots[0].get("image_url") if shots else None
    if not image_url:
        fail("render_spec.image_shots[0].image_url missing", spec)
    expected_scope = f"{user_id}/outputs/projects/{pid}/quote-chain-"
    if expected_scope not in image_url:
        fail(
            f"composite key NOT in project scope (D3): expected {expected_scope!r} in URL",
            image_url,
        )
    if "/demo/" in image_url or image_url.split("?")[0].startswith("demo/"):
        fail("composite key uses demo/ prefix (user product in display reserve)", image_url)
    ok(f"合成图 key 在项目作用域: …{expected_scope}*.png")
    return clip, image_url


async def assert_metering_reconciled(run_id):
    """D9/F2 计量对账: 内存台账 → 尾段一次归并的落账形状.

    - 至少一个 step cost.prompt_tokens > 0 (write_quotes 的 LLM 调用落了账)
    - 每个非空 cost 都带全量基键 {prompt_tokens, completion_tokens, fixed_cost}
    - render step 无 LLM 调用 → cost 保持 NULL (漂移报表继续忽略它)
    """
    from sqlalchemy import select

    from app.models.database import AsyncSessionLocal
    from app.models.tables import WorkflowStep

    async with AsyncSessionLocal() as db:
        steps = list(
            (
                await db.execute(
                    select(WorkflowStep).where(WorkflowStep.run_id == run_id)
                )
            )
            .scalars()
            .all()
        )
    if not steps:
        fail("no workflow steps found for run", run_id)
    billed = 0
    for s in steps:
        if s.kind == "render":
            if s.cost:
                fail(f"render step must keep cost NULL, got {s.cost}")
            continue
        if not s.cost:
            continue
        billed += 1
        for key in ("prompt_tokens", "completion_tokens", "fixed_cost"):
            if key not in s.cost:
                fail(f"step {s.kind} cost missing base key {key!r}", s.cost)
        ok(
            f"step {s.kind}: prompt={s.cost['prompt_tokens']} "
            f"completion={s.cost['completion_tokens']} "
            f"fixed={s.cost['fixed_cost']} units={s.cost.get('units')}"
        )
    if billed == 0:
        fail("no step has a cost ledger — metering merge did not land")
    if not any(int(s.cost.get("prompt_tokens") or 0) > 0 for s in steps if s.cost):
        fail("no step billed prompt_tokens > 0 — LLM usage not recorded")
    ok(f"计量对账: {billed} 个 step 落账, 形状齐全, render step cost=NULL")


async def terminate_project_backends(pid) -> None:
    """D9 cleanup guard, dev-harness rule: terminate any OTHER session parked
    ``idle in transaction`` for >15s before the FK deletes below — a wedged or
    abandoned runner session would otherwise block them. (pg_stat_activity.query
    carries parameterized SQL, so project-id text matching can't identify the
    culprits; on a dev box at cleanup time, a >15s idle-in-transaction session
    is precisely the wedge class this guard exists for.)"""
    from sqlalchemy import text

    from app.models.database import AsyncSessionLocal

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


async def cleanup(pid):
    from sqlalchemy import delete, select

    from app.models.database import AsyncSessionLocal
    from app.models.tables import (
        Asset,
        Output,
        Persona,
        Project,
        Publication,
        WorkflowRun,
        WorkflowStep,
    )

    await terminate_project_backends(pid)
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Publication).where(Publication.project_id == pid))
        await db.execute(
            delete(WorkflowStep).where(
                WorkflowStep.run_id.in_(
                    select(WorkflowRun.id).where(WorkflowRun.project_id == pid)
                )
            )
        )
        await db.execute(delete(Output).where(Output.project_id == pid))
        await db.execute(delete(WorkflowRun).where(WorkflowRun.project_id == pid))
        await db.execute(delete(Asset).where(Asset.project_id == pid))
        persona_id = (
            await db.execute(select(Project.persona_id).where(Project.id == pid))
        ).scalar_one_or_none()
        await db.execute(delete(Project).where(Project.id == pid))
        await db.commit()
        if persona_id:
            await db.execute(delete(Persona).where(Persona.id == persona_id))
            await db.commit()
    print("cleanup done", flush=True)


async def main():
    print("quote-cards v3 真管线 e2e (dock 路径 + 叠卡产物形态)")
    print(f"  API base: {BASE}")

    if not LOCAL_VIDEO.exists():
        fail(f"{LOCAL_VIDEO} missing — download demo_talk.mp4 first")
    user_id, token = await setup_user_and_token()
    ok(f"auth token issued for user {user_id[:8]}")

    pid = None
    # Optional argv[1] = existing project id — resume after the chat steps
    # (a killed run leaves the ASR'd project behind; reusing it skips the
    # upload + ASR cycle).
    resume_pid = sys.argv[1] if len(sys.argv) > 1 else None
    async with httpx.AsyncClient(
        base_url=BASE,
        headers={"Authorization": f"Bearer {token}"},
        timeout=60.0,
    ) as client:
        try:
            if resume_pid:
                pid = resume_pid
                ok(f"resuming on existing project: {pid}")
            else:
                r = await client.post(
                    "/projects",
                    json={"title": f"v3 stacked e2e {uuid.uuid4().hex[:6]}", "event_name": "Test"},
                )
                if r.status_code != 201:
                    fail("create project", r.text)
                pid = r.json()["id"]
                ok(f"project created: {pid}")

                asset = await upload_asset(client, pid, LOCAL_VIDEO)
                print("\n  --- waiting for ASR ---")
                await wait_for_asr(client, pid, asset["id"])

            # --- chat turn 1: no keyword → caption_mode dock must fire ---
            print("\n  --- chat turn 1: 做一张金句卡 → caption_mode dock ---")
            r = await client.post(
                "/chat", json={"project_id": pid, "message": "做一张金句卡"}
            )
            if r.status_code != 201:
                fail("chat turn 1", r.text)
            t1 = r.json()
            q1 = (t1.get("assistant_message") or {}).get("question")
            if not (
                q1
                and q1.get("kind") == "choice"
                and any(
                    o.get("id", "").startswith("caption_mode_")
                    for o in q1.get("options", [])
                )
            ):
                fail("expected caption_mode choice dock", t1.get("assistant_message"))
            ok("caption_mode 三选项 dock 落地（无关键词 → 不问不行）")

            # --- answer bilingual → task_book dock ---
            print("\n  --- answer caption_mode_bilingual → task_book dock ---")
            r = await client.post(
                f"/chat/messages/{t1['assistant_message']['id']}/answer",
                json={"kind": "option", "option_id": "caption_mode_bilingual"},
            )
            if r.status_code not in (200, 201):
                fail("answer caption_mode_bilingual", r.text)
            t2 = r.json()
            # follow_up is a flat ChatMessageResponse (the docked task_book
            # question message), not an envelope.
            follow = t2.get("follow_up") or {}
            q2 = follow.get("question") or {}
            if q2.get("kind") != "task_book":
                fail("expected task_book dock after caption answer", t2)
            r = await client.get(f"/projects/{pid}/results")
            pending = (r.json().get("pending_intent") or {}) if r.status_code == 200 else {}
            intent = pending.get("intent") or {}
            tasks = intent.get("tasks") or []
            if not any(t.get("tool") == "write_quotes" for t in tasks):
                fail("pending_intent tasks must include write_quotes", tasks)
            if intent.get("caption_mode") != "bilingual":
                fail(
                    f"caption_mode not replayed into pending_intent: {intent.get('caption_mode')!r}",
                    intent,
                )
            ok("task_book docked: write_quotes 在链 + caption_mode='bilingual' 回放成功")

            # --- start ---
            print("\n  --- answer kind=start ---")
            r = await client.post(
                f"/chat/messages/{follow['id']}/answer",
                json={"kind": "start"},
            )
            if r.status_code not in (200, 201):
                fail("answer kind=start", r.text)
            run_id = ((r.json().get("answered_question") or {}).get("workflow_run_id"))
            if not run_id:
                fail("no run_id after start", r.json())
            ok(f"run started: {run_id}")

            print(f"\n  --- waiting for run (max {TIMEOUT_S}s) ---")
            last_run = await wait_for_run(client, pid, timeout_s=TIMEOUT_S)
            if last_run["status"] != "completed":
                fail(f"run terminal status={last_run['status']}", last_run)
            ok("run completed")

            print("\n  --- waiting for render ---")
            await wait_clip_rendered(client, pid)
            ok("render completed")

            # --- v3 产物形态断言 ---
            print("\n  --- v3 产物形态断言 ---")
            _clip, image_url = await assert_v3_product_shape(pid, user_id)

            # --- D9/F2 计量对账(清理前) ---
            print("\n  --- 计量对账 ---")
            await assert_metering_reconciled(run_id)

            # --- 下载合成 PNG 供目检中文换行 ---
            async with httpx.AsyncClient(timeout=120) as c:
                r = await c.get(image_url)
                if r.status_code != 200:
                    fail(f"download composite: HTTP {r.status_code}", image_url)
                COMPOSITE_OUT.write_bytes(r.content)
            ok(f"composite PNG → {COMPOSITE_OUT} ({COMPOSITE_OUT.stat().st_size} bytes)")

            print("\n=== V3 STACKED QUOTE-CARD E2E GREEN ===")
            print(f"project: {pid}")
            print(f"composite: {image_url}")
        finally:
            if pid:
                await cleanup(pid)


if __name__ == "__main__":
    asyncio.run(main())
