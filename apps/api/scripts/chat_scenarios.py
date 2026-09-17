"""chat_scenarios.py — 剧本测试：预设多轮剧本对活 API 跑形态级断言。

不是 harness（harness 单义 = 调用面 Agent 漏斗，NAMING N-48），也不是"测试
套件"（scripts/ 下的剧本测试脚本，不配概念名——去方言批禁令）。剧本驱动
活 API 的唯一意图表面（``POST /chat`` + answer 端点），断言 = **工具序列 +
终态帧消息**（ADR-077 判词② 工具 loop 线格式）：terminal_tool_of 从终态
信封的形状判别回合收在哪个终态工具（工具名永不过线，简报 §3——信封形状
就是判别面），SSE 侧断言相位帧序（assistant.thinking 的 drafting /
inspecting 座）与 question.preview 预览帧，外加既有形态级结果——dock 态 /
run 数 / 落库行——永不锁 LLM 文案（禁令 #7）。例外：代码强制文本（提醒尾 /
机器标记 / 确定性回执）可以锁——那是代码，不是 LLM。

2026-09-04 大浓缩（C4，简报 ``docs/tasks/de-dialect-question-machine.md``）：
52 本机制碎片（旧 S1–S53，S22 空）浓缩为 **12 条核心用户 story**，编号连续
重排（本次不再沿用留空洞先例——旧 S 号与现行 S 号无一对应，映射见简报
§C4 与 ``docs/INTENT_COVERAGE.md`` §6）。每条 = 一个完整用户故事，不是
机制碎片；进程内纯函数断言（估价 / repair / 编译矩阵 / merge 矩阵）按简报
「保留并入」随链收编——零 LLM 零方差，是最便宜的覆盖。

    S1  核① 裸愿望全旅程：主题问 → 作答（自由文本 slot 握手 + 选项点选两路）
             → 评审卡 → start → run（途中锁待决重建 / 一行一答 409 / 选项点选
             不 500 三张契约拍；K5 草稿图横切：dock 即 stamp draft 节点 +
             计划 document + 逐节点估价，start 同 id 原地填充无双生）
    S2  核② 跳过提问 → draft-from-persona 计划 + 默认路径声明
    S3  核③ 插话：正常回答 + 代码拼装提醒尾 + 保持 pending → 下轮作答回填
    S4  核④ 素材全链（run completed + 产物落库 + 触发回合 reviewer
             poll）+ 估价三断言 + repair 只一轮 + 修订 = wiring 横切
             （K4/K5 验收点：chat 修订 → edit_prompt 原地改写节点程序
             （同 id 无双生）→ 子图重跑起 run）
    S5  核⑤ 修订链：手改存活 / chat 恒胜 / supersede 标记 / task_book 不打字母
             + 草稿图随行（新槽位长新 draft 节点 / 参数微调同 fill_key 零双生）
    S6  核⑥ interrupt 一条：三答法 + 空白不答 + bail 级联 + 插话后续跑
    S7  核⑦ caption mode：选项问 → 回执 + run.context + refine 存活
    S8  核⑧ research 全链（活 DDG，网络全灭时 caveat 降级也算过）
    S9  核⑨ 问事不出书：能力问 / 闲聊纯 answer，无计划 start 不死路不起 run
    S10 SSE 流式（工具 loop 线格式）：单轮 concat(deltas) == 信封散文 /
             读先 startswith 前缀律 / 拒轮方差注记 + drafting 相位帧 +
             question.preview 预览帧
    S11 整条源规则（整条视频字幕活链）+ materialize 注入矩阵（进程内）
    S12 merge_brief 来源矩阵（进程内纯函数）
    S13 积分① 余额不足出生地拦截（typed Start 与 /generate 双路 422
             同形同义）+ 负余额 hold 必拒（BILLING §5）
    S14 积分② 失败不扣费（活 worker 缺参探针：FAILED + 级联 skipped →
             零 capture、hold 全额 release）+ capture 幂等/bounce 差额（进程内）
    S15 积分③ 孤儿 hold 回收（BILLING §8 边界落地：project 删除先退未结
             hold 再级联删 run——台账闭合、余额回赠额）
    S17 run 执行权仲裁（R1 B3）：A 挂 B 跑 → 答/过期皆 blocked 再挂+明示
             （零状态污染、全程单 owner）→ B 收官交接钩续跑 A

S4/S7/S8 起的 run 是真的（worker 会执行；writer 链走真 LLM——S4 用
``processing_status=COMPLETED`` 的 transcript 资产走 writer 链到 completed，
fixture 媒体字节不存在的 media 链 fail fast 属预期）；S6 seed parked run
手工行，答题/插话后由 worker 跑零 LLM 的 answer 分支收官——需要 dev
worker 在跑。

LLM 方差口径：凡锁定的是**设计行为**（裸愿望先问主题 / 插话不结算 / 提醒尾
必在 / 判定回答必结算），红了 = prompt 或判定回归信号，不是剧本松劲。

The server does all LLM work (the intent router / the chat_intent agent); this script only
mints a scenario user's JWT and seeds DB rows the scenarios need (a fake
media asset for clips gating, a COMPLETED transcript asset for the writer
chain, a parked interrupt for the checkpoint family).
Runs started by the scenarios are real — keep the dev worker's quota in mind;
every scenario deletes its project afterwards (``--keep`` opts out).

Usage (from apps/api/, API running on :8000):
    uv run python scripts/chat_scenarios.py                 # all scenarios
    uv run python scripts/chat_scenarios.py --only S1,S5    # subset
    uv run python scripts/chat_scenarios.py --keep          # keep projects
    SCENARIO_API_BASE=http://127.0.0.1:8000/api/v1 uv run python scripts/chat_scenarios.py
"""

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NamedTuple

# Make ``app`` importable when run as a file (apps/api on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from sqlalchemy import delete, func, select, update  # noqa: E402

from app.agents.base import Agent, StreamingAgent  # noqa: E402
from app.chat.perception import PERCEPTION_TOOLS  # noqa: E402
from app.providers.llm.base import LLMError, LLMSchemaError  # noqa: E402
from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.schemas import MediaInput, TaskItem  # noqa: E402
from app.pipeline.graph import NODE_KINDS, fold_estimates  # noqa: E402
from app.pipeline.orchestrator import (  # noqa: E402
    TaskSpec,
    assert_runners_registered,
    compile_graph,
    expire_stale_interrupts,
    maybe_finalize_run,
)
from app.models.tables import (  # noqa: E402
    Asset,
    Conversation,
    CreditTransaction,
    Message,
    Operation,
    Output,
    Project,
    User,
    Wallet,
    WorkflowRun,
    WorkflowStep,
)
from app.models.schemas import (  # noqa: E402
    AssetStatus,
    AssetType,
    Option,
    QuestionPayload,
    WorkflowStatus,
)
from app.platform.auth import create_access_token  # noqa: E402
from app.platform.billing import (  # noqa: E402
    CreditsInsufficientError,
    capture_step,
    check_hold,
    cost_usd,
    credits_for_cost,
    get_or_create_wallet,
    hold_run,
)

BASE = os.getenv("SCENARIO_API_BASE", "http://127.0.0.1:8000/api/v1")
TIMEOUT = httpx.Timeout(300.0)  # plan-path turns are real LLM calls (remix turns with a real transcript excerpt have crossed 180s on a slow provider)


class ScenarioFailure(AssertionError):
    pass


def check(condition: bool, label: str, detail: object = "") -> None:
    if not condition:
        raise ScenarioFailure(f"{label}" + (f" — {detail}" if detail else ""))


class StreamTurn(NamedTuple):
    """One SSE chat turn's full frame record (Ctx.chat_stream)."""

    deltas: list[str]
    thinking: list[dict]
    previews: list[dict]
    completed: dict | None
    failed: dict | None


class Ctx:
    """Per-run context: an authed HTTP client plus cleanup bookkeeping."""

    def __init__(self, user_id: uuid.UUID, keep: bool) -> None:
        self.client = httpx.AsyncClient(
            base_url=BASE,
            headers={"Authorization": f"Bearer {create_access_token(user_id)}"},
            timeout=TIMEOUT,
        )
        self.user_id = user_id
        self.keep = keep
        self.project_ids: list[str] = []

    async def close(self) -> None:
        await self.client.aclose()

    async def new_project(self, title: str) -> str:
        res = await self.client.post(
            "/projects", json={"title": title, "event_name": ""}
        )
        check(res.status_code == 201, "create project", res.text)
        pid = res.json()["id"]
        self.project_ids.append(pid)
        return pid

    async def chat(self, pid: str, message: str, **extra: object) -> dict:
        res = await self.client.post(
            "/chat",
            json={"project_id": pid, "message": message, **extra},
        )
        check(res.status_code == 201, f"/chat {message[:30]!r}", res.text)
        return res.json()

    async def chat_stream(self, pid: str, message: str, **extra: object) -> "StreamTurn":
        """One SSE chat turn (Accept: text/event-stream) — the FULL frame
        record: ordered prose deltas, the assistant.thinking phase frames
        ({} / {phase} / {phase, key} — the inspecting family's seat), the
        question.preview frames (pre-execution, rolled back on a flip), the
        turn.completed envelope, and turn.failed if any."""
        deltas: list[str] = []
        thinking: list[dict] = []
        previews: list[dict] = []
        completed: dict | None = None
        failed: dict | None = None
        async with self.client.stream(
            "POST",
            "/chat",
            json={"project_id": pid, "message": message, **extra},
            headers={"Accept": "text/event-stream"},
        ) as res:
            check(res.status_code == 200, f"/chat stream {message[:30]!r}", res.status_code)
            event = ""
            async for line in res.aiter_lines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    payload = json.loads(line[5:].strip())
                    if event == "assistant.delta":
                        deltas.append(payload["text"])
                    elif event == "assistant.thinking":
                        thinking.append(payload)
                    elif event == "question.preview":
                        previews.append(payload)
                    elif event == "turn.completed":
                        completed = payload
                    elif event == "turn.failed":
                        failed = payload
        return StreamTurn(
            deltas=deltas,
            thinking=thinking,
            previews=previews,
            completed=completed,
            failed=failed,
        )

    async def answer(self, question_id: str, body: dict) -> httpx.Response:
        return await self.client.post(f"/chat/messages/{question_id}/answer", json=body)

    async def conversation(self, pid: str, **params: object) -> httpx.Response:
        """GET /chat/conversation — 200 with pending_question, or 404 pre-chat."""
        return await self.client.get(
            "/chat/conversation", params={"project_id": pid, **params}
        )

    async def messages(self, conversation_id: str) -> list[dict]:
        res = await self.client.get(f"/chat/conversations/{conversation_id}/messages")
        check(res.status_code == 200, "GET conversation messages", res.text)
        return res.json()["items"]

    async def results(self, pid: str) -> dict:
        res = await self.client.get(f"/projects/{pid}/results")
        check(res.status_code == 200, "GET results", res.text)
        return res.json()

    async def graph(self, pid: str) -> dict:
        """The persistent graph's one read frame (ADR-057 K3 直读端点)."""
        res = await self.client.get(f"/projects/{pid}/graph")
        check(res.status_code == 200, "GET project graph", res.text)
        return res.json()

    async def runs(self, pid: str) -> list[dict]:
        res = await self.client.get(f"/projects/{pid}/runs")
        check(res.status_code == 200, "GET runs", res.text)
        return res.json()

    async def cleanup(self) -> None:
        if self.keep:
            return
        if self.project_ids:
            # Operation rows FK-block project deletion (no ondelete cascade) —
            # edit-ops scenarios must journal away before the API delete.
            async with AsyncSessionLocal() as db:
                await db.execute(
                    delete(Operation).where(
                        Operation.project_id.in_([uuid.UUID(p) for p in self.project_ids])
                    )
                )
                await db.commit()
        for pid in self.project_ids:
            await self.client.delete(f"/projects/{pid}")
        self.project_ids.clear()


# ---- DB seeding helpers (in-process, same DB the API uses) -----------------


async def make_user() -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        user = User(
            email=f"scenario-{uuid.uuid4().hex[:8]}@test.local",
            name="scenario-bot",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return uuid.UUID(str(user.id))


async def seed_asset(
    pid: str,
    user_id: uuid.UUID,
    type_: AssetType,
    filename: str,
    *,
    extracted_text: str | None = None,
    meta: dict | None = None,
    processed: bool = False,
    file_url: str | None = None,
    status: AssetStatus | None = None,
) -> str:
    """A fake file-backed asset row — enough for the clips-media gate and the
    intent router's filename context; the bytes never exist. ``extracted_text``
    satisfies the "transcript" required-input check (registry requires).
    ``meta`` carries e.g. the ASR-detected ``language`` the plan context
    surfaces for transform-target decisions. ``processed`` stamps the row
    COMPLETED (the declared-material promotion's end state) — the worker's
    asset queue then never touches the fake bytes (S4's writer chain).
    ``file_url`` points at a REAL bucket object (S16's demo-bucket fixtures —
    the worker really processes a PENDING one). ``status`` overrides the
    derived state (S16's FAILED exemplar — the warm never fires for it).
    Returns the row's id."""
    async with AsyncSessionLocal() as db:
        asset = Asset(
            user_id=user_id,
            project_id=uuid.UUID(pid),
            type=type_,
            file_url=file_url or f"scenario/{filename}",
            title=filename,
            extracted_text=extracted_text,
            meta=meta,
            processing_status=(
                status
                or (AssetStatus.COMPLETED if processed else AssetStatus.PENDING)
            ),
        )
        db.add(asset)
        await db.flush()
        asset_id = str(asset.id)
        await db.commit()
        return asset_id


async def seed_completed_run(pid: str) -> None:
    """A settled run row — the plan path must never claim a project that has
    runs (the chat-path caption gate's phase seat, S7)."""
    async with AsyncSessionLocal() as db:
        db.add(
            WorkflowRun(
                project_id=uuid.UUID(pid),
                status=WorkflowStatus.COMPLETED,
                context={"outputs": [{"type": "post"}], "target_language": "en"},
            )
        )
        await db.commit()


async def set_project_language(pid: str, language: str) -> None:
    """Pin the project's locale — the caption gate's alt-language candidate
    (S7) derives off it."""
    async with AsyncSessionLocal() as db:
        project = await db.get(Project, uuid.UUID(pid))
        project.language = language
        await db.commit()


async def wait_run_terminal(run_id: str, timeout: float = 90.0) -> str:
    """Poll a run to a terminal state (fixture runs fail fast at preprocess —
    scenario/ bytes never exist). Stray-run retry loops (S7-B) must settle a
    wrong-tool run before the next turn, or the active-run guard eats it."""
    terminal = {WorkflowStatus.COMPLETED, WorkflowStatus.FAILED}
    for _ in range(int(timeout / 2)):
        async with AsyncSessionLocal() as db:
            run = await db.get(WorkflowRun, uuid.UUID(run_id))
            if run is not None and run.status in terminal:
                return str(run.status)
        await asyncio.sleep(2)
    return "TIMEOUT"


async def seed_parked_interrupt(
    pid: str,
    user_id: uuid.UUID,
    *,
    with_downstream: bool = False,
) -> dict:
    """A direction interrupt parked for a human answer (期 4 seed shape):
    WAITING_HUMAN run + waiting ``interrupt`` node (options in
    spec.suspend_payload) + the docked options-question row carrying the
    ``workflow_run_id`` dispatch marker. ``with_downstream`` adds a pending
    child node so the bail cascade has something to skip (S6-e)."""
    options = [
        {"id": "a", "label": "Focus: Pricing", "argument_id": "arg-1"},
        {"id": "b", "label": "Focus: Roadmap", "argument_id": "arg-2"},
        {"id": "c", "label": "Full-talk highlights", "argument_id": None},
    ]
    started_at = datetime.now(UTC)
    async with AsyncSessionLocal() as db:
        run = WorkflowRun(
            project_id=uuid.UUID(pid),
            status=WorkflowStatus.WAITING_HUMAN,
            context={
                "outputs": [{"type": "post"}],
                "target_language": "en",
                "autonomy": "review",
            },
        )
        db.add(run)
        await db.flush()
        conversation = (
            await db.execute(
                select(Conversation).where(
                    Conversation.project_id == uuid.UUID(pid),
                    Conversation.asset_id.is_(None),
                )
            )
        ).scalar_one_or_none()
        if conversation is None:
            conversation = Conversation(user_id=user_id, project_id=uuid.UUID(pid))
            db.add(conversation)
            await db.flush()
        question = Message(
            conversation_id=conversation.id,
            role="assistant",
            content="Which direction should this run focus on?",
            question=QuestionPayload(
                kind="question",
                options=[Option(id=o["id"], label=o["label"]) for o in options],
                allow_freeform=True,
            ).model_dump(mode="json"),
            workflow_run_id=run.id,
        )
        db.add(question)
        await db.flush()
        node = WorkflowStep(
            run_id=run.id,
            kind="interrupt",
            status="waiting",
            seq=1,
            started_at=started_at,
            spec={
                "suspend_payload": {
                    "question_message_id": str(question.id),
                    "options": options,
                }
            },
        )
        db.add(node)
        await db.flush()
        child_id: str | None = None
        if with_downstream:
            child = WorkflowStep(
                run_id=run.id,
                kind="plan",
                status="pending",
                seq=2,
                inputs=[str(node.id)],
            )
            db.add(child)
            await db.flush()
            child_id = str(child.id)
        await db.commit()
        return {
            "run_id": str(run.id),
            "node_id": str(node.id),
            "child_id": child_id,
            "question_id": str(question.id),
        }


async def seed_active_run(pid: str) -> str:
    """An authority-holding run (I-EXEC-03 fixture, R1 B3): RUNNING + one
    inert ``running`` node. The claim loop only takes ``pending`` rows and
    the per-tick reap (900s) never fires inside a scenario, so the row holds
    the project's execution authority until ``settle_seeded_run`` ends it.
    Returns the run id."""
    async with AsyncSessionLocal() as db:
        run = WorkflowRun(
            project_id=uuid.UUID(pid),
            status=WorkflowStatus.RUNNING,
            context={
                "outputs": [{"type": "post"}],
                "target_language": "en",
                "autonomy": "review",
            },
        )
        db.add(run)
        await db.flush()
        db.add(
            WorkflowStep(
                run_id=run.id,
                kind="plan",
                status="running",
                seq=1,
                started_at=datetime.now(UTC),
            )
        )
        await db.commit()
        return str(run.id)


async def settle_seeded_run(run_id: str) -> None:
    """Settle a seeded inert run the way its worker execution would end:
    nodes done, then maybe_finalize_run — the finalizer is the authority-
    handoff seat (R1 B3), so this drives the parked-run resume hook for real.
    """
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(WorkflowStep)
            .where(
                WorkflowStep.run_id == uuid.UUID(run_id),
                WorkflowStep.status.in_(["pending", "running"]),
            )
            .values(status="done", finished_at=datetime.now(UTC))
        )
        await db.commit()
    await maybe_finalize_run(uuid.UUID(run_id))


async def count_active_runs(pid: str) -> int:
    """The I-EXEC-03 witness: a project's {PENDING, RUNNING} run count."""
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(WorkflowRun.id).where(
                    WorkflowRun.project_id == uuid.UUID(pid),
                    WorkflowRun.status.in_(
                        [WorkflowStatus.PENDING, WorkflowStatus.RUNNING]
                    ),
                )
            )
        ).all()
        return len(rows)


async def count_runs(pid: str) -> int:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(WorkflowRun.id).where(WorkflowRun.project_id == uuid.UUID(pid))
            )
        ).all()
        return len(rows)


async def run_row(run_id: str) -> dict:
    async with AsyncSessionLocal() as db:
        run = await db.get(WorkflowRun, uuid.UUID(run_id))
        check(run is not None, f"run {run_id} exists")
        return {"status": str(run.status), "context": run.context or {}}


async def step_rows(run_id: str) -> list[dict]:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(WorkflowStep)
                .where(WorkflowStep.run_id == uuid.UUID(run_id))
                .order_by(WorkflowStep.seq)
            )
        ).scalars().all()
        return [
            {"id": str(s.id), "kind": s.kind, "status": s.status, "spec": s.spec or {}, "error": s.error}
            for s in rows
        ]


async def message_row(message_id: str) -> dict:
    async with AsyncSessionLocal() as db:
        msg = await db.get(Message, uuid.UUID(message_id))
        check(msg is not None, f"message {message_id} exists")
        return {
            "question": msg.question,
            "answer": msg.answer,
            "workflow_run_id": str(msg.workflow_run_id) if msg.workflow_run_id else None,
            "content": msg.content,
        }


async def wait_run_status(run_id: str, wanted: set[str], timeout: float = 45.0) -> dict:
    """Poll a run until it reaches one of ``wanted`` statuses. The wake half
    of a interrupt answer is synchronous, but settling (the thin node's
    answer branch → finalize) is worker-driven — hence the poll. Requires the
    dev worker (the interrupt answer branch is zero-LLM, so this is fast)."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        row = await run_row(run_id)
        if row["status"] in wanted:
            return row
        if asyncio.get_event_loop().time() > deadline:
            raise ScenarioFailure(
                f"run did not reach {sorted(wanted)} within {timeout}s (worker down?) — last {row['status']}"
            )
        await asyncio.sleep(2)


# ---- Assertion helpers ------------------------------------------------------


def is_plan_dock(msg: dict) -> bool:
    return bool(msg.get("question")) and msg["question"].get("kind") == "task_book" and not msg.get("answer")


def terminal_tool_of(turn: dict) -> str:
    """The terminal tool the turn closed on, discriminated off the terminal
    envelope (ADR-077 判词② — the tool NAME never crosses the wire, 简报 §3;
    the envelope's SHAPE is the discriminator):

    - the plan settles + a run is born → ``start_run``
    - an unanswered task_book question docks → ``present_plan``
    - an unanswered caption-mode options question → ``caption_gate``
      (propose_tasks' execution sub-dock, not an ask_user call)
    - any other unanswered plain question → ``ask_user``
    - a run born with no settled question → ``run_birth`` (chat path: a
      proposal tool — propose_tasks / apply_edit_ops / edit_graph — started
      it; the envelope does not discriminate further, the scenarios assert
      the wiring outcome instead)
    - prose only → ``answer``
    """
    msg = turn.get("assistant_message") or {}
    q = msg.get("question") or {}
    if turn.get("answered_question") is not None and turn.get("run_id"):
        return "start_run"
    if not turn.get("answered_question") and q.get("kind") == "task_book":
        return "present_plan"
    if q.get("kind") == "question":
        if any(
            str(o.get("id", "")).startswith("caption_mode_")
            for o in q.get("options") or []
        ):
            return "caption_gate"
        return "ask_user"
    if turn.get("run_id"):
        return "run_birth"
    return "answer"


def check_stream_law(
    stream: "StreamTurn", content: str, label: str, *, allow_reads: bool = True
) -> None:
    """The SSE 打字机律's tool-loop form (tool_loop.py on_delta 的 iteration-0
    唯一座位): iteration 0's speech streams verbatim; later iterations run
    quiet (a rejected iteration's speech is REPLACED speech, the repair-
    never-streams law). Therefore:

    - single-iteration turn (no inspecting frames): concat(deltas) == the
      envelope content, exactly;
    - read-first turn (accepted reads in iteration 0 — inspecting frames
      present): the kept read-iteration speech is a PREFIX of the composed
      content (言语账本: kept parts + the terminal part join on a blank
      line), so content.startswith(concat(deltas));
    - a rejected iteration breaks even the prefix relation (its streamed
      speech was replaced) — LLM variance the scenarios cannot foresee, so
      this helper asserts the two designed relations only.
    """
    concat = "".join(stream.deltas)
    had_reads = any(t.get("phase") == "inspecting" for t in stream.thinking)
    if had_reads and allow_reads:
        check(
            not concat or content.startswith(concat),
            f"{label}: the read-first stream law (kept speech prefixes the content)",
            f"{concat[:120]!r} vs {content[:120]!r}",
        )
    else:
        check(
            concat == content,
            f"{label}: the single-iteration stream law (concat(deltas) == content)",
            f"{concat[:120]!r} vs {content[:120]!r}",
        )


async def answer_caption_gate(ctx: Ctx, turn1: dict) -> dict:
    """The caption gate (S1 precedent): a chain carrying write_quotes docks
    the caption_mode options question BEFORE the plan. When turn1 docked
    it, answer bilingual and re-wrap the follow_up in turn1's shape so the
    caller's task_book assertions work unchanged; no-op otherwise."""
    q1 = turn1["assistant_message"].get("question")
    if q1 is not None and q1.get("kind") == "question" and any(
        o.get("id", "").startswith("caption_mode_") for o in q1.get("options", [])
    ):
        ans = await ctx.answer(
            turn1["assistant_message"]["id"],
            {"kind": "option", "option_id": "caption_mode_bilingual"},
        )
        check(ans.status_code in (200, 201), "caption_mode answer accepted", ans.text)
        turn1 = {
            "assistant_message": ans.json().get("follow_up") or {},
            "run_id": None,
            "answered_question": ans.json().get("answered_question"),
        }
    return turn1


def has_prose(msg: dict) -> bool:
    """The assistant message carries a non-empty prose reply."""
    return bool((msg.get("content") or "").strip())


def plan_tasks(plan: dict) -> list[dict]:
    """The docked chain (ADR-043): pending_brief.intent.tasks — the plan
    card's rows, one {tool, params} dict per task."""
    return ((plan or {}).get("intent") or {}).get("tasks") or []


def task_params(task: dict) -> dict:
    return task.get("params") or {}


async def pending_plan(ctx: Ctx, pid: str) -> dict | None:
    """The project's pending plan via the results endpoint (None when none)."""
    return (await ctx.results(pid)).get("pending_brief")


async def wait_trigger_review(
    ctx: Ctx, conversation_id: str, run_id: str, timeout: float = 90.0
) -> dict | None:
    """Poll the conversation for the run-completed trigger turn's review row
    (ADR-077 判词③ T3): the pipeline fires the proactive turn fire-and-forget
    at run terminal, and the agent's wrap_up persists an assistant row whose
    intent dump is ``{type: "trigger_review", trigger, ref, suggestions}``
    (ADR-081: suggestions = option labels; the row also docks the numbered
    options question when labels exist). Returns the message row, or None on
    timeout."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        for m in await ctx.messages(conversation_id):
            intent = m.get("intent") or {}
            if intent.get("type") == "trigger_review" and intent.get("ref") == run_id:
                return m
        await asyncio.sleep(2)
    return None


def has_reminder_tail(content: str) -> bool:
    """The code-composed interjection reminder tail (ADR-053 R2 — code-forced
    text, so locking its marker is legal: it is code, never the LLM's voice)."""
    return "Still waiting for your answer:" in content or "还在等你的回答：" in content


async def wait_asset_status(
    asset_id: str, wanted: set[AssetStatus], timeout: float = 420.0
) -> AssetStatus:
    """Poll an asset row to a wanted processing state (S16's real-bytes seed:
    the dev worker really ASRs the PENDING demo-bucket source)."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        async with AsyncSessionLocal() as db:
            asset = await db.get(Asset, uuid.UUID(asset_id))
            check(asset is not None, f"asset {asset_id} exists")
            if asset.processing_status in wanted:
                return asset.processing_status
        if asyncio.get_event_loop().time() > deadline:
            raise ScenarioFailure(
                f"asset did not reach {sorted(str(s) for s in wanted)} within {timeout}s "
                f"(worker down?) — last {asset.processing_status}"
            )
        await asyncio.sleep(3)


async def wait_step_terminal(
    run_id: str, kind: str, timeout: float = 600.0
) -> dict:
    """Poll a run's steps until the named kind settles (done/failed/skipped).
    The caller asserts WHICH terminal is acceptable — a failed step surfaces
    its error verbatim."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        for step in await step_rows(run_id):
            if step["kind"] == kind and step["status"] in ("done", "failed", "skipped"):
                return step
        if asyncio.get_event_loop().time() > deadline:
            raise ScenarioFailure(
                f"step {kind} did not settle within {timeout}s — steps: "
                f"{[(s['kind'], s['status']) for s in await step_rows(run_id)]}"
            )
        await asyncio.sleep(3)


async def outputs_of(pid: str, type_: str) -> list[Output]:
    async with AsyncSessionLocal() as db:
        return list(
            (
                await db.execute(
                    select(Output).where(
                        Output.project_id == uuid.UUID(pid), Output.type == type_
                    )
                )
            ).scalars().all()
        )


async def task_book_step_ids(pid: str) -> list[str]:
    """The task-book node's internal step family (the read frame hides the
    book — B1-lite — so the prelude-membership assertion reads the row)."""
    from app.models.tables import GraphNode

    async with AsyncSessionLocal() as db:
        node = (
            await db.execute(
                select(GraphNode).where(
                    GraphNode.project_id == uuid.UUID(pid),
                    GraphNode.spec["role"].astext == "task_book",
                )
            )
        ).scalars().one_or_none()
        if node is None:
            return []
        return [str(s) for s in (node.spec or {}).get("step_ids") or []]


def no_decompile_canvas_node(graph: dict) -> bool:
    """T3 (R1 B1): decompile folds into the prelude — it must never read back
    as a standalone canvas node (its pre-fold face was a text×manual orphan)."""
    return not any(
        (n.get("spec") or {}).get("tool") == "decompile" for n in graph.get("nodes") or []
    )


# ---- S1 核① 裸愿望全旅程 ------------------------------------------------------


async def s1_bare_wish_full_journey(ctx: Ctx) -> None:
    """核① 裸愿望 → 主题问 → 作答回填（自由文本 slot 握手 + 选项点选两路）→
    评审卡 → start → run 起步（ADR-052 出书门槛 + ADR-053 R2 slot 握手判定
    结算）。途中锁三张契约拍：待决重建零内存态、一行一答 409、选项点选不
    500（kind 守卫）。

    LLM 方差说明：router 判 ask 是设计行为（prompt 策略行）；若个别模型把
    "I want a social post." 直接判 draft，首段断言会红——那是 prompt 回归
    信号。options 空合法（C2：无 persona 时储藏室为空，策略②豁免）。"""
    pid = await ctx.new_project("S1 bare wish journey")

    turn1 = await ctx.chat(pid, "I want a social post.")
    msg1 = turn1["assistant_message"]
    check(turn1["run_id"] is None, "a bare wish never starts a run", turn1)
    check(terminal_tool_of(turn1) == "ask_user",
          "the rootless wish closes on the ask_user call", turn1)
    q1 = msg1.get("question") or {}
    check(q1.get("kind") == "question" and q1.get("slot") == "topic",
          "the rootless wish docks the topic ask first (never an empty plan)", msg1)
    check(bool((q1.get("default_path") or "").strip()),
          "the default path rides as the schema tooth (策略③)", q1)
    # ask 三分解剖 (2026-09-08): content = 框架散文（①，认领+理由+default
    # path 织入），payload.question = 裸问题（②，dock 标题 / QA 归档 / 提醒
    # 尾读它）。散文缺字段时 content 回退裸问题——那即是回归信号。
    check(bool((q1.get("question") or "").strip()),
          "the bare question rides the payload (解剖② — dock title's source)", q1)
    check(has_prose(msg1) and (msg1.get("content") or "") != q1.get("question"),
          "the framing prose IS the message content (解剖① — the ask's echo)",
          (msg1.get("content") or "")[:200])
    options = q1.get("options") or []
    check(len(options) == 0 or 2 <= len(options) <= 3,
          "options: 3 one-word picks (2 only for a genuinely binary choice), "
          "or empty when the persona pantry is empty (C2)",
          options)
    plan1 = await pending_plan(ctx, pid)
    check(plan1 is None or plan1.get("intent") is None,
          "no plan parks on an ask turn (brief-only row or none)", plan1)

    # 契约拍①：待决重建零内存态（旧 S26 并入）。
    res = await ctx.conversation(pid)
    check((res.json().get("pending_question") or {}).get("id") == msg1["id"],
          "the pending question rebuilds (the refresh / cross-device seat)",
          res.json())

    # 自由文本作答 —— slot 握手判定结算（ADR-053 R2 plan path：router 在
    # pending 块上下文里把槽位值提案 user-stated，代码结算 freeform 并回填）。
    turn2 = await ctx.chat(pid, "Make it about the EU AI Act for researchers.")
    aq = turn2.get("answered_question")
    check(aq is not None and aq["id"] == msg1["id"],
          "the free-text answer settles the pending ask (judged — code settles)",
          turn2)
    check((aq.get("answer") or {}).get("kind") == "freeform",
          "the judged settlement lands kind=freeform (the user's own words)",
          aq.get("answer"))
    brief = ((await pending_plan(ctx, pid)) or {}).get("brief") or {}
    topic = brief.get("topic") or {}
    check(topic.get("source") == "user-stated" and bool(topic.get("value")),
          "the slot backfills user-stated from the answer", topic)

    # 契约拍②：一行一答（旧 S25 并入）——已答问题再答 = 409。
    dup = await ctx.answer(msg1["id"], {"kind": "bail"})
    check(dup.status_code == 409, "re-answering the settled ask is a conflict",
          dup.status_code)

    # 契约拍③：选项点选作答（2026-09-04 500 事故补盖——OptionAnswerRequest
    # 没有 .text 属性，续聊分支的 data.text 直读未 kind 守卫就恒 500；此前
    # 剧本只有自由文本一条作答路，点选路裸奔正是漏网根因）。第二项目同问
    # 点选：200（无 500）+ answer.kind=option + slot 回填 user-stated（回填
    # 的是 label 不是 id）+ plan path 接续带 follow_up。
    pid2 = await ctx.new_project("S1 option pick")
    turn1b = await ctx.chat(pid2, "I want a social post.")
    msg1b = turn1b["assistant_message"]
    q1b = msg1b.get("question") or {}
    opts = q1b.get("options") or []
    if q1b.get("slot") == "topic" and opts:
        pick = await ctx.answer(msg1b["id"],
                                {"kind": "option", "option_id": opts[0]["id"]})
        check(pick.status_code == 200, "the option pick settles (no 500)",
              pick.text)
        body = pick.json()
        check(((body.get("answered_question") or {}).get("answer") or {})
              .get("kind") == "option",
              "the pick lands kind=option", body.get("answered_question"))
        brief2 = ((await pending_plan(ctx, pid2)) or {}).get("brief") or {}
        topic2 = brief2.get("topic") or {}
        check(topic2.get("source") == "user-stated"
              and topic2.get("value") == opts[0]["label"],
              "the option pick backfills the slot with the LABEL (not the id)",
              topic2)
        check(body.get("follow_up") is not None,
              "the plan path resumes with a follow-up", body)
    else:
        check(True, "option-pick beat skipped (pantry empty — C2 exempt)", q1b)

    # 评审卡：作答轮直接出书，或（answer 裁决时）推一轮——终点断言不变：
    # present_plan 终态（task_book dock）且 merged brief 钢印进 payload
    # （预填评审卡 B3）。
    turn_dock = turn2
    msg2 = turn_dock["assistant_message"]
    if not is_plan_dock(msg2):
        turn_dock = await ctx.chat(pid, "go ahead")
        msg2 = turn_dock["assistant_message"]
    check(terminal_tool_of(turn_dock) == "present_plan",
          "the enriched brief closes on the present_plan call (root now exists)",
          turn_dock)
    check(is_plan_dock(msg2),
          "the enriched brief docks the plan (root now exists)", msg2)
    ftopic = ((msg2.get("question") or {}).get("brief") or {}).get("topic") or {}
    check(ftopic.get("source") == "user-stated" and bool(ftopic.get("value")),
          "the review card stamps the merged brief into the payload", ftopic)
    # 计划行自完备（方案 B, 2026-09-08）：dock 行自带链（intent 列）+ 派生
    # 预览（payload derived）——SSE envelope 的行即整张计划卡，前端活路不再
    # 取 pending_brief（那 GET 退回恢复座）。
    check(bool(((msg2.get("intent") or {}).get("tasks")) or []),
          "the dock row self-carries the chain (intent column)",
          msg2.get("intent"))
    row_derived = (msg2.get("question") or {}).get("derived")
    check(isinstance(row_derived, list) and len(row_derived) >= 1,
          "the dock row self-carries the derived preview (payload)",
          msg2.get("question"))

    # 草稿图（ADR-057 K5——图先展示后运行）：dock 即 stamp——draft 节点 +
    # 计划 document + 逐节点估价，零消耗直到 start。
    draft_graph = await ctx.graph(pid)
    draft_nodes = [
        n for n in draft_graph["nodes"]
        # 词表 v3 (ADR-076, 三族批): the graph read frame carries ``type`` +
        # ``spec.prototype`` (never the legacy card kinds) — producer draft
        # nodes = the two working prototypes (generator/editor).
        if n.get("state") == "draft"
        and (n.get("spec") or {}).get("prototype") in ("generator", "editor")
    ]
    check(len(draft_nodes) >= 1, "the dock stamps the draft graph (图先展示后运行)",
          draft_graph["nodes"])
    check(not any(
        # B1-lite (a82e1a9, 2026-09-13, ADR-070): the task_book node is
        # stamped server-side but filtered out of the read frame — the
        # canvas shows the pure material flow, the confirm beat's only seat
        # is the dock pill. This check locks the CURRENT design (an
        # accidental un-hiding goes red); it replaces the pre-B1-lite
        # positive "the plan rides the draft graph" assertion.
        (n.get("spec") or {}).get("role") == "task_book"
        for n in draft_graph["nodes"]
    ), "the read frame hides the task_book node (B1-lite — confirm seat = dock pill)",
       draft_graph["nodes"])
    check(any(n.get("estimate_credits") for n in draft_nodes),
          "draft nodes carry their own quotes (逐节点估价)", draft_nodes)
    draft_ids = sorted(n["id"] for n in draft_graph["nodes"])

    # 散文确认 start → run 起步（G-1）+ 草稿图原地填充（同 id 无双生）。
    turn3 = await ctx.chat(pid, "looks good, start")
    check(terminal_tool_of(turn3) == "start_run",
          "the prose confirmation closes on the start_run call", turn3)
    check(turn3["run_id"] is not None, "prose confirmation starts the run", turn3)
    check(turn3["answered_question"] is not None, "the plan settles on start", turn3)
    check((await ctx.results(pid)).get("pending_brief") is None,
          "pending_brief cleared on start")
    filled_graph = await ctx.graph(pid)
    check(sorted(n["id"] for n in filled_graph["nodes"]) == draft_ids,
          "start fills the SAME nodes in place (same compile → same fill keys — never twins)",
          filled_graph["nodes"])
    check(not any(n.get("state") == "draft" for n in filled_graph["nodes"]),
          "the draft world re-queues on start", filled_graph["nodes"])


# ---- S2 核② 跳过 → draft-from-persona ------------------------------------------


async def s2_skipped_topic_ask_drafts_from_persona(ctx: Ctx) -> None:
    """核② 问完一轮仍无根 → draft-from-persona 计划（ADR-052 B2 D2-C2，验收③）：
    裸愿望 → 主题问 → × 跳过（bail）→ 默认路径生效——出书门槛 dock
    draft-from-persona 计划（reason + 散文含默认路径声明），asked 簿记挡住
    第二轮同槽问（问环有界）。

    LLM 方差说明：跳过后 router 应判 draft（stand-in 行明示默认路径）；
    若它再判 ask(topic)，asked 簿记把判词翻回 draft 走门槛——两种路径同
    归宿，断言只看终点。"""
    pid = await ctx.new_project("S2 skip ask drafts from persona")

    turn1 = await ctx.chat(pid, "I want a social post.")
    q1 = turn1["assistant_message"].get("question") or {}
    check(q1.get("kind") == "question" and q1.get("slot") == "topic",
          "the topic ask docks first (S1's gate)", turn1["assistant_message"])

    ans = await ctx.answer(turn1["assistant_message"]["id"], {"kind": "bail"})
    check(ans.status_code in (200, 201), "the skip is accepted", ans.text)
    follow = ans.json().get("follow_up") or {}
    check(is_plan_dock(follow),
          "skipping takes the default path — a plan docks", follow)
    check(ans.json().get("answered_question") is not None,
          "the skipped ask settles as answered", ans.json())

    plan = await pending_plan(ctx, pid)
    check(plan is not None, "the draft-from-persona plan persists", plan)
    reasons = (plan or {}).get("reasons") or []
    check("draft_from_persona" in reasons,
          "the draft-from-persona reason rides the docked plan", reasons)
    asked = ((plan or {}).get("brief") or {}).get("asked") or []
    check("topic" in asked,
          "the asked roll records the topic ask (the loop is bounded)", asked)
    echo = ((plan or {}).get("intent") or {}).get("answer") or ""
    check("persona" in echo.lower() or "人设" in echo,
          "the echo carries the default-path declaration (验收③)", echo)


# ---- S3 核③ 插话支持 -----------------------------------------------------------


async def s3_interjection_keeps_pending(ctx: Ctx) -> None:
    """核③ 插话未答 → 正常回答 + 提醒尾 + 问题保持 pending → 下轮作答回填
    （ADR-053 R2 plan path）：主题问待决中插一句与问题无关的能力问——
    router 判 answer 出口，回复末尾接代码拼装提醒尾（原问题 + default_path，
    代码强制文本可锁）；问题行保持待决；下一轮作答经 slot 握手结算回填。"""
    pid = await ctx.new_project("S3 interjection")

    turn1 = await ctx.chat(pid, "I want a social post.")
    msg1 = turn1["assistant_message"]
    q1 = msg1.get("question") or {}
    check(q1.get("kind") == "question" and q1.get("slot") == "topic",
          "the topic ask docks first", msg1)
    default_path = (q1.get("default_path") or "").strip()
    check(bool(default_path), "the ask carries its default path", q1)

    turn2 = await ctx.chat(pid, "By the way, what can you generate?")
    check(terminal_tool_of(turn2) == "answer",
          "the interjection closes on the answer call", turn2)
    check(turn2.get("answered_question") is None,
          "an interjection never settles the pending ask", turn2)
    msg2 = turn2["assistant_message"]
    check(not msg2.get("question"),
          "the interjection turn docks no new question", msg2)
    check(has_prose(msg2), "the interjection gets its normal answer", msg2)
    content = msg2.get("content") or ""
    check(has_reminder_tail(content),
          "the reply ends with the code-composed reminder tail", content[-200:])
    check(default_path in content,
          "the tail carries the ask's default path verbatim", content[-200:])
    check(bool((q1.get("question") or "").strip())
          and q1["question"] in content,
          "the tail quotes the BARE question (解剖②), not the framing prose",
          content[-200:])
    res = await ctx.conversation(pid)
    check((res.json().get("pending_question") or {}).get("id") == msg1["id"],
          "the ask stays pending through the interjection", res.json())

    # 下轮作答 → slot 握手结算回填（S1 同径）。
    turn3 = await ctx.chat(pid, "Make it about European research policy.")
    aq = turn3.get("answered_question")
    check(aq is not None and aq["id"] == msg1["id"]
          and (aq.get("answer") or {}).get("kind") == "freeform",
          "the next-turn answer settles by the slot handshake", turn3)
    brief = ((await pending_plan(ctx, pid)) or {}).get("brief") or {}
    check(((brief.get("topic") or {}).get("source")) == "user-stated",
          "the answer backfills the topic slot user-stated", brief)


# ---- S4 核④ 素材全链 + 估价地基（进程内自检并入） ---------------------------------


async def s4_material_chain_and_estimate_foundation(ctx: Ctx) -> None:
    """核④ 带素材全链：transcript 素材 → dock 计划 → dock Start → run
    completed → post 产物落库 → 触发回合 reviewer 发言（T3：trigger_review
    dump + 0–3 枚良构建议 pill）；估价三断言（fold 对账 / 报价单调性 /
    NULL 语义）与 repair 只一轮（Agent 漏斗进程内 stub 自检）随链并入
    （简报 C4「原 S41/S42 保留并入」）。"""
    # A) 活链：COMPLETED transcript 资产（声明素材升格的终态——worker 资产
    #    队列不碰假字节），writer 链走真 LLM 到 completed。
    pid = await ctx.new_project("S4 material chain")
    await seed_asset(pid, ctx.user_id, AssetType.TRANSCRIPT, "talk.txt",
                     extracted_text="My talk about grid storage auctions.",
                     processed=True)

    turn1 = await ctx.chat(pid, "write a LinkedIn post from my talk")
    conv_id = turn1["conversation_id"]  # the gate's re-wrap drops the key
    turn1 = await answer_caption_gate(ctx, turn1)  # write_quotes 链先答 caption
    check(terminal_tool_of(turn1) == "present_plan",
          "turn1 closes on the present_plan call", turn1)
    check(is_plan_dock(turn1["assistant_message"]), "turn1 docks a task_book",
          turn1["assistant_message"])
    res = await ctx.answer(turn1["assistant_message"]["id"], {"kind": "start"})
    check(res.status_code == 200, "dock Start answers the plan", res.text)
    run_id = res.json()["answered_question"].get("workflow_run_id")
    check(run_id, "a run was born", res.json())
    row = await wait_run_status(run_id, {"completed", "failed"}, timeout=600.0)
    check(row["status"] == "completed",
          "the writer chain completes on a text asset", row["status"])
    async with AsyncSessionLocal() as db:
        outs = (
            await db.execute(
                select(Output).where(
                    Output.project_id == uuid.UUID(pid), Output.type == "post"
                )
            )
        ).scalars().all()
    check(len(outs) >= 1, "the post output lands in the DB", len(outs))

    # A1) 触发回合（ADR-077 判词③ T3 + ADR-081 选项语法统一律）：run 收官
    #    触发 reviewer 主动发言——持久化为 assistant 行，intent dump =
    #    {type: "trigger_review", trigger, ref, suggestions=labels}；有建议
    #    时建议 dock 成真实编号选项问（messages.question payload，id = 1 起
    #    序号）。断言 dump 形态与 dock 良构；言语内容不锁（LLM 文案，禁令 #7）。
    review = await wait_trigger_review(ctx, conv_id, run_id)
    check(review is not None,
          "the run-completed trigger turn speaks its review row", run_id)
    rintent = (review or {}).get("intent") or {}
    check(rintent.get("trigger") == "run_completed" and rintent.get("ref") == run_id,
          "the review dump names trigger + ref", rintent)
    sugs = rintent.get("suggestions") or []
    check(0 <= len(sugs) <= 3, "0–3 suggestion labels (schema-bounded)", sugs)
    check(all(isinstance(s, str) and s.strip() for s in sugs),
          "each suggestion is a user-voice label (ADR-081 — pills retired)",
          sugs)
    if sugs:
        question = (review or {}).get("question") or {}
        check(question.get("kind") == "question",
              "the suggestions dock as a real options question", question)
        options = question.get("options") or []
        check([o.get("id") for o in options] == [str(i + 1) for i in range(len(sugs))]
              and [o.get("label") for o in options] == sugs,
              "the dock options are the numbered labels (1/2/3 grammar)",
              options)

    # A2) 修订 = wiring（ADR-057 K4/K5 横切——修订环根治验收点）: chat 修订
    #    → WiringProposal（edit_prompt + run 子图）→ 节点程序行原地改写
    #    （同 id 无双生）→ 子图重跑起 run。锁的是设计行为（shape E 修既有图
    #    节点）；红了 = chat_intent prompt 回归信号，不是剧本松劲。
    graph_before = await ctx.graph(pid)
    post_node = next(
        (n for n in graph_before["nodes"]
         if (n.get("spec") or {}).get("tool") == "write_post"),
        None,
    )
    check(post_node is not None, "the run's fill grew the writer's graph node",
          graph_before["nodes"])
    prompt_before = (post_node.get("spec") or {}).get("prompt")
    turn_rev = await ctx.chat(pid, "make the post shorter")
    check(terminal_tool_of(turn_rev) == "run_birth",
          "the revision closes on a proposal tool's run birth (chat path)", turn_rev)
    check(turn_rev["run_id"] is not None,
          "the revision rides the wiring path — the subgraph rerun is born",
          turn_rev)
    graph_after = await ctx.graph(pid)
    post_after = next(
        (n for n in graph_after["nodes"] if n["id"] == post_node["id"]), None
    )
    check(post_after is not None,
          "the revision reuses the SAME node (edit_prompt + rerun — never a twin)",
          graph_after["nodes"])
    check((post_after.get("spec") or {}).get("prompt") != prompt_before,
          "edit_prompt rewrote the node's program in place",
          (post_after.get("spec") or {}).get("prompt"))
    check(post_after.get("state") != "draft",
          "the rerun re-queues its node", post_after.get("state"))

    # B) 估价地基（进程内编译，零 LLM）——fold 对账 / 单调性 / NULL 语义。
    assert_runners_registered()

    facts = {
        "text_chars": 50_000,
        "text_count": 1,
        "media_count": 1,
        "persona_exists": False,
        "voice_clone_needed": True,
        "clips": [],
        "output_seconds": {},
    }

    def quote(node_specs: list) -> dict:
        return fold_estimates(
            NODE_KINDS[ns.kind].estimate(
                {
                    **facts,
                    "spec": ns.spec,
                    "input_kinds": [node_specs[i].kind for i in ns.inputs],
                }
            )
            for ns in node_specs
        )

    # 报价单调性: the targeted-derivative subgraph quotes ≤ the full graph,
    # every field non-negative.
    full = compile_graph(
        TaskSpec(
            tasks=[
                TaskItem(tool="select_clips", params={"language": "en"}),
                TaskItem(tool="write_post", params={"language": "en"}),
                TaskItem(tool="write_quotes", params={"language": "en"}),
            ]
        )
    )
    sub = compile_graph(
        TaskSpec(scope="post", target_id=uuid.uuid4()), target_type="post"
    )
    full_q, sub_q = quote(full), quote(sub)
    for field in ("prompt_tokens", "completion_tokens"):
        check(
            sub_q[field][0] <= full_q[field][0]
            and sub_q[field][1] <= full_q[field][1],
            f"subgraph {field} ≤ full graph",
            (sub_q[field], full_q[field]),
        )
        check(
            all(v >= 0 for v in sub_q[field] + full_q[field]),
            f"{field} non-negative",
            (sub_q[field], full_q[field]),
        )
    for key, value in sub_q["units"].items():
        check(
            full_q["units"].get(key, 0) >= value,
            f"subgraph units.{key} ≤ full graph",
            (sub_q["units"], full_q["units"]),
        )
    check(
        all(v >= 0 for v in full_q["units"].values()),
        "units non-negative",
        full_q["units"],
    )

    # NULL 语义: an initial-run dub fan-out (its target clips don't exist at
    # compile) stays NULL (未估价); a modifier dub on existing clips quotes
    # its exact mechanical units.
    with_dub = compile_graph(
        TaskSpec(
            tasks=[
                TaskItem(tool="select_clips", params={"language": "en"}),
                TaskItem(
                    tool="dub_clip",
                    params={"target_language": "de", "fork": True},
                ),
            ]
        )
    )
    dub_ns = next(ns for ns in with_dub if ns.kind == "dub_clip")
    est = NODE_KINDS["dub_clip"].estimate(
        {
            **facts,
            "spec": dub_ns.spec,
            "input_kinds": [with_dub[i].kind for i in dub_ns.inputs],
        }
    )
    check(est is None, "the initial-run dub fan-out stays NULL", est)
    modifier = NODE_KINDS["dub_clip"].estimate(
        {
            **facts,
            "clips": [{"seconds": 30.0, "caption_chars": 420}],
            "spec": {"target_language": "de"},
            "input_kinds": [],
        }
    )
    check(
        modifier is not None
        and modifier["units"]["tts_chars"] == 420.0
        and modifier["units"]["voice_clones"] == 1.0,
        "the modifier dub quotes exact units",
        modifier,
    )

    # translate fan-out (R6's chain shape): same NULL semantics.
    with_caps = compile_graph(
        TaskSpec(
            tasks=[
                TaskItem(tool="select_clips", params={"language": "en"}),
                TaskItem(
                    tool="translate_clip",
                    params={"target_language": "fr", "fork": True},
                ),
                TaskItem(
                    tool="translate_clip",
                    params={"target_language": "de", "fork": True},
                ),
            ]
        )
    )
    cap_ns = [ns for ns in with_caps if ns.kind == "translate_clip"]
    check(
        len(cap_ns) == 2 and all(ns.spec.get("fork") for ns in cap_ns),
        "fork translate tasks fan out one node per language",
        [(ns.kind, ns.spec) for ns in cap_ns],
    )
    cap_est = NODE_KINDS["translate_clip"].estimate(
        {
            **facts,
            "spec": cap_ns[0].spec,
            "input_kinds": [with_caps[i].kind for i in cap_ns[0].inputs],
        }
    )
    check(cap_est is None, "the initial-run translate fan-out stays NULL", cap_est)
    cap_modifier = NODE_KINDS["translate_clip"].estimate(
        {
            **facts,
            "clips": [{"seconds": 30.0, "caption_chars": 420}],
            "spec": {"target_language": "fr"},
            "input_kinds": [],
        }
    )
    check(
        cap_modifier is not None,
        "the modifier translate quotes",
        cap_modifier,
    )
    # dangling-transform gate: translate with no clip selection and no
    # materialize profile is a compile-time ValueError naming the transform
    # (the profile matrix lives in S11).
    try:
        compile_graph(
            TaskSpec(
                tasks=[
                    TaskItem(tool="write_post", params={"language": "en"}),
                    TaskItem(
                        tool="translate_clip", params={"target_language": "fr"}
                    ),
                ]
            )
        )
        check(False, "dangling translate raises", None)
    except ValueError as exc:
        check("translate clip" in str(exc), "dangling translate raises", str(exc))

    # C) repair 只一轮（Agent 漏斗进程内 stub 自检，不打 API 零 LLM）。
    # 1. Schema rejection → exactly one repair round, carrying the echo.
    stub = _StubClient(["schema", _ProbeResult(text="ok")])
    result = await _probe_agent(stub, name="scenario_probe_1").call()
    check(result.text == "ok", "the repair round's result returns", result)
    check(len(stub.calls) == 2, "first failure + one repair round == 2 calls",
          len(stub.calls))
    echo = "Your previous proposal was rejected"
    check(echo not in _user_text(stub.calls[0][1]), "first attempt carries no echo")
    check(echo in _user_text(stub.calls[1][1])
          and "boom" in _user_text(stub.calls[1][1]),
          "the repair round carries the structured error echo",
          _user_text(stub.calls[1][1])[-160:])

    # 2. A second rejection is the call's failure — never a third roll.
    stub = _StubClient(["schema", "schema", _ProbeResult(text="never")])
    raised = None
    try:
        await _probe_agent(stub, name="scenario_probe_2").call()
    except LLMSchemaError as exc:
        raised = exc
    check(isinstance(raised, LLMSchemaError), "the second rejection raises")
    check(len(stub.calls) == 2, "no third call after the repair round",
          len(stub.calls))

    # 3. Transport-class LLMError is NOT repaired (client tenacity owns it).
    stub = _StubClient([LLMError("MiniMax HTTP 500"), _ProbeResult(text="x")])
    raised = None
    try:
        await _probe_agent(stub, name="scenario_probe_3").call()
    except LLMError as exc:
        raised = exc
    check(isinstance(raised, LLMError)
          and not isinstance(raised, LLMSchemaError),
          "transport failure propagates unrepaired")
    check(len(stub.calls) == 1, "transport failure: no repair round", len(stub.calls))

    # 4. Declared fallback: a failed call returns the declaration's result.
    stub = _StubClient([LLMError("MiniMax HTTP 500")])
    result = await _probe_agent(
        stub, name="scenario_probe_4",
        fallback=lambda: _ProbeResult(text="declared"),
    ).call()
    check(result.text == "declared", "the declared fallback answers", result)

    # 5. The reserved repair_feedback kwarg echoes on the FIRST attempt (the
    #    chat loop's adjudication repair), never reaching assemble.
    stub = _StubClient([_ProbeResult(text="ok")])
    result = await _probe_agent(stub, name="scenario_probe_5").call(
        repair_feedback="adjudication said no"
    )
    check(result.text == "ok", "adjudication-feedback call returns", result)
    check(len(stub.calls) == 1, "feedback echo needs no extra round", len(stub.calls))
    check("adjudication said no" in _user_text(stub.calls[0][1]),
          "the adjudication echo rides the first attempt",
          _user_text(stub.calls[0][1])[-120:])

    # 6. Streaming: a schema rejection repairs via the NON-streaming path.
    stub = _StubClient(["schema", _ProbeResult(text="ok")])
    agent = StreamingAgent(
        name="scenario_probe_6",
        prompt="chat_intent.j2",
        schema=_ProbeResult,
        system="sys",
        assemble=lambda: ({"context_text": "", "message": "m"}, []),
        client=stub,  # type: ignore[arg-type]
    )
    result = await agent.call_stream(on_delta=lambda f: None)
    check(result.text == "ok", "the streamed call repairs", result)
    check([k for k, _ in stub.calls] == ["stream", "generate"],
          "first attempt streams, the repair round never does", stub.calls)

    # 7. media_text_fallback × repair composition (the c31ff8c carve-out law):
    #    a SCHEMA rejection is not media brittleness — it routes to the
    #    repair round with the media still attached (media-derived fields
    #    must never be blind-labeled on a text-only retry); the text-only
    #    degradation fires ONLY on non-schema (brittleness) errors.
    def _media_agent(stub: _StubClient, *, name: str) -> Agent:
        media = [MediaInput(type="image", mime="image/png",
                            data_url="data:image/png;base64,x")]
        return Agent(
            name=name,
            prompt="chat_intent.j2",
            schema=_ProbeResult,
            system="sys",
            assemble=lambda: ({"context_text": "", "message": "m"}, media),
            media_text_fallback=True,
            client=stub,  # type: ignore[arg-type]
        )

    # 7a. Schema rejection → the repair round re-carries media + echo
    #     (parts-list) — NO text-only degradation in between.
    stub = _StubClient(["schema", _ProbeResult(text="ok")])
    result = await _media_agent(stub, name="scenario_probe_7a").call()
    check(result.text == "ok", "the repair round's result returns", result)
    check(len(stub.calls) == 2,
          "schema rejection + one repair round == 2 calls", len(stub.calls))
    a_media, a_repair = stub.calls[0][1][1], stub.calls[1][1][1]
    check(isinstance(a_media["content"], list)
          and any(p.get("type") == "image_url" for p in a_media["content"]),
          "attempt 1 carries the media parts", a_media["content"])
    check(isinstance(a_repair["content"], list)
          and any(p.get("type") == "image_url" for p in a_repair["content"])
          and echo in a_repair["content"][-1]["text"],
          "the repair round re-carries media + echo (no degradation between)",
          a_repair["content"])

    # 7b. Brittleness (non-schema) → the text-only degradation runs INSIDE the
    #     attempt: string payload, no echo, the repair round unconsumed.
    stub = _StubClient([LLMError("MiniMax HTTP 500"), _ProbeResult(text="ok")])
    result = await _media_agent(stub, name="scenario_probe_7b").call()
    check(result.text == "ok", "media degradation returns", result)
    check(len(stub.calls) == 2,
          "brittleness degradation inside one attempt == 2 calls", len(stub.calls))
    b_media, b_text = stub.calls[0][1][1], stub.calls[1][1][1]
    check(isinstance(b_media["content"], list)
          and any(p.get("type") == "image_url" for p in b_media["content"]),
          "attempt 1 carries the media parts", b_media["content"])
    check(isinstance(b_text["content"], str) and echo not in b_text["content"],
          "the text degradation is pre-echo (no repair round consumed)",
          b_text["content"][-120:])

    # 7c. Composition: media brittle → text retry schema-rejected → the repair
    #     round re-carries media + echo (3 calls; the degradation never
    #     streams).
    stub = _StubClient(
        [LLMError("MiniMax HTTP 500"), "schema", _ProbeResult(text="ok")]
    )
    result = await _media_agent(stub, name="scenario_probe_7c").call()
    check(result.text == "ok", "brittle-then-schema composition survives",
          result)
    check(len(stub.calls) == 3,
          "media + degraded text + repair(media) == 3 calls", len(stub.calls))
    check([k for k, _ in stub.calls] == ["generate"] * 3,
          "the media degradation never streams", [k for k, _ in stub.calls])
    check(isinstance(stub.calls[1][1][1]["content"], str),
          "the middle retry is the text-only degradation",
          stub.calls[1][1][1]["content"][:80])
    c_repair = stub.calls[2][1][1]
    check(isinstance(c_repair["content"], list)
          and any(p.get("type") == "image_url" for p in c_repair["content"])
          and echo in c_repair["content"][-1]["text"],
          "the repair round re-carries media + echo after the degradation",
          c_repair["content"])


class _ProbeResult(BaseModel):
    text: str


class _StubClient:
    """Scripted MiniMaxClient stand-in: records every call, plays outcomes.

    Script items: ``"schema"`` (raise LLMSchemaError), an exception
    instance (raise it), or a ``_ProbeResult`` (return it).
    """

    def __init__(self, script: list[object]) -> None:
        self.script = list(script)
        self.calls: list[tuple[str, list[dict]]] = []

    def _play(self, kind: str, messages: list[dict]) -> _ProbeResult:
        self.calls.append((kind, messages))
        item = self.script.pop(0)
        if item == "schema":
            raise LLMSchemaError("Failed to validate response: boom")
        if isinstance(item, Exception):
            raise item
        return item  # type: ignore[return-value]

    async def generate(self, *, messages, response_model, **_):
        return self._play("generate", messages)

    async def generate_stream(self, *, messages, response_model, on_delta=None, **_):
        return self._play("stream", messages)


def _probe_agent(client: _StubClient, *, name: str, fallback=None) -> Agent:
    def _assemble():
        return ({"context_text": "", "message": "m"}, [])

    return Agent(
        name=name,
        prompt="chat_intent.j2",
        schema=_ProbeResult,
        system="sys",
        assemble=_assemble,
        fallback=fallback,
        client=client,  # type: ignore[arg-type]
    )


def _user_text(messages: list[dict]) -> str:
    """The user message's trailing text part (the funnel's prompt carrier)."""
    return messages[1]["content"][-1]["text"]


# ---- S5 核⑤ 修订链 --------------------------------------------------------------


async def s5_revision_chat_always_wins(ctx: Ctx) -> None:
    """核⑤ 修订链（ADR-043 + ADR-053）：re-dock 旧计划 supersede（机器标记
    入流）→ 面板手改整链存活于无关 refine → chat 修订恒胜（覆盖面板钉）
    → task_book 待决打字母永不误答（不参与任何结算）→ 散文确认起 run。"""
    pid = await ctx.new_project("S5 revision chain")
    await seed_asset(pid, ctx.user_id, AssetType.VIDEO, "talk.mp4")

    turn1 = await ctx.chat(pid, "cut highlight clips from my talk")
    check(terminal_tool_of(turn1) == "present_plan",
          "turn1 closes on the present_plan call", turn1)
    check(is_plan_dock(turn1["assistant_message"]), "turn1 docks a task_book",
          turn1["assistant_message"])
    first_qid = turn1["assistant_message"]["id"]

    def pin_count(plan: dict, count: int) -> dict:
        """Simulate a panel hand edit: the select_clips count set in params —
        the edited chain IS the prior_intent (no merge machinery, ADR-043)."""
        edited = dict(plan["intent"])
        edited["tasks"] = [
            {**t, "params": {**task_params(t), "count": count}}
            if t["tool"] == "select_clips" else t
            for t in plan_tasks(plan)
        ]
        return edited

    # 面板手改存活 + 旧计划 supersede（已答问题入流的机器标记）。
    plan1 = (await ctx.results(pid)).get("pending_brief")
    turn2 = await ctx.chat(
        pid, "also add a German post", prior_intent=pin_count(plan1, 3)
    )
    check(terminal_tool_of(turn2) == "present_plan",
          "turn2 closes on present_plan again (the refinement re-docks)", turn2)
    check(is_plan_dock(turn2["assistant_message"]), "turn2 re-docks",
          turn2["assistant_message"])
    check(turn2["assistant_message"]["id"] != first_qid,
          "the old plan is superseded by a new question row")
    tasks = plan_tasks((await ctx.results(pid)).get("pending_brief"))
    clips = [t for t in tasks if t["tool"] == "select_clips"]
    check(clips and task_params(clips[0]).get("count") == 3,
          "the panel hand edit survives an unrelated refine", tasks)
    check(any(t["tool"] == "write_post" and task_params(t).get("language") == "de" for t in tasks),
          "the German post arrived", tasks)
    # 草稿图随行（K5）：新槽位长新 draft 节点，计划全文进 document。
    graph2 = await ctx.graph(pid)
    check(any(
        (n.get("spec") or {}).get("tool") == "write_post" and n.get("state") == "draft"
        for n in graph2["nodes"]
    ), "the German post grows its own draft node on the graph", graph2["nodes"])
    msgs = await ctx.messages(turn2["conversation_id"])
    old = next(m for m in msgs if m["id"] == first_qid)
    check((old.get("answer") or {}).get("text") == "superseded",
          "the superseded plan carries the machine marker", old.get("answer"))

    # chat 修订恒胜（覆盖面板钉）。
    plan2 = (await ctx.results(pid)).get("pending_brief")
    turn3 = await ctx.chat(
        pid, "clips only needs 2", prior_intent=pin_count(plan2, 3)
    )
    check(terminal_tool_of(turn3) == "present_plan",
          "turn3 closes on present_plan (the chat revision re-docks)", turn3)
    check(is_plan_dock(turn3["assistant_message"]), "turn3 re-docks",
          turn3["assistant_message"])
    tasks = plan_tasks((await ctx.results(pid)).get("pending_brief"))
    clips = [t for t in tasks if t["tool"] == "select_clips"]
    check(clips and task_params(clips[0]).get("count") == 2,
          "the chat revision overrides the panel pin (chat always wins)", tasks)
    # 参数微调 = 同 fill_key 复用——图节点零双生（K5 幂等锚）。
    graph3 = await ctx.graph(pid)
    check(sorted(n["id"] for n in graph3["nodes"]) == sorted(n["id"] for n in graph2["nodes"]),
          "a param refine reuses the same nodes (fill-key idempotency — no twins)",
          graph3["nodes"])

    # task_book 待决不参与任何结算：打字母永不当选项答掉（旧 S40 并入）。
    live_qid = turn3["assistant_message"]["id"]
    turn4 = await ctx.chat(pid, "a")
    check(turn4.get("answered_question") is None,
          "a typed letter never answers a task_book", turn4)
    q = await message_row(live_qid)
    check(q.get("answer") is None or (q["answer"] or {}).get("text") == "superseded",
          "the plan stays pending or is superseded by a re-dock — never letter-answered",
          q.get("answer"))

    turn5 = await ctx.chat(pid, "looks good, start")
    check(terminal_tool_of(turn5) == "start_run",
          "the prose confirmation closes on the start_run call", turn5)
    check(turn5["run_id"] is not None, "prose confirmation starts the run", turn5)


# ---- S6 核⑥ interrupt 一条 -------------------------------------------------------


async def s6_interrupt_consolidated(ctx: Ctx) -> None:
    """核⑥ interrupt 一条（期 4 家族浓缩 + ADR-053 R2 判定结算）：
    a) option 答（端点）→ 唤醒收官；b) 打字母 → autoResume 确定性结算；
    c) 自由文本 → 判定结算 freeform + 确定性回执 + 唤醒；d) 空白附件不答；
    e) bail → 节点 done(bailed) + 下游级联 skipped + run COMPLETED（永不
    failed）；f) 插话 → 正常回答 + 提醒尾 + 保持 parked → 再答唤醒。"""
    # a) 按钮：answer 端点 option。
    pid = await ctx.new_project("S6a option answer")
    ck = await seed_parked_interrupt(pid, ctx.user_id)
    res = await ctx.answer(ck["question_id"], {"kind": "option", "option_id": "a"})
    check(res.status_code == 200, "the option answer lands", res.text)
    answered = res.json()["answered_question"]
    check((answered.get("answer") or {}).get("kind") == "option",
          "answer kind=option", answered.get("answer"))
    check((answered.get("answer") or {}).get("text") == "Focus: Pricing",
          "the answered row shows the option's human label", answered.get("answer"))
    node = (await step_rows(ck["run_id"]))[0]
    check(node["status"] != "waiting" and "answer" in node["spec"],
          "the wake is synchronous (spec.answer written, node re-pended)", node)
    check((await run_row(ck["run_id"]))["status"] != "waiting_human",
          "the run left WAITING_HUMAN")
    await wait_run_status(ck["run_id"], {"completed"})
    await ctx.cleanup()

    # b) 打字母：/chat autoResume 选项命中（零 LLM 确定性结算——ADR-053 后
    #    唯一的确定性结算）。
    pid = await ctx.new_project("S6b typed letter")
    ck = await seed_parked_interrupt(pid, ctx.user_id)
    turn = await ctx.chat(pid, "a")
    aq = turn.get("answered_question")
    check(aq is not None and aq["id"] == ck["question_id"],
          "the typed letter auto-resumed the interrupt", turn)
    check((aq.get("answer") or {}).get("kind") == "option", "the letter maps to an option",
          aq.get("answer"))
    await wait_run_status(ck["run_id"], {"completed"})
    await ctx.cleanup()

    # c) 自由文本：判定结算（ADR-053 R2——「任意文本 = freeform 回答」掩盖
    #    已退役；chat_intent 判 disposition=answer，代码结算 freeform 并
    #    唤醒，确定性回执收官）。
    pid = await ctx.new_project("S6c judged freeform")
    ck = await seed_parked_interrupt(pid, ctx.user_id)
    turn = await ctx.chat(pid, "focus on the pricing argument")
    aq = turn.get("answered_question")
    check(aq is not None and aq["id"] == ck["question_id"],
          "the free-text answer is judged the interrupt's answer and settles",
          turn)
    check((aq.get("answer") or {}).get("kind") == "freeform", "answer kind=freeform",
          aq.get("answer"))
    ack = turn["assistant_message"].get("content") or ""
    check("Resuming the run" in ack or "继续生成" in ack,
          "the deterministic wake ack lands (code-forced)", ack)
    await wait_run_status(ck["run_id"], {"completed"})
    await ctx.cleanup()

    # d) 空白 attachment-only 永不 auto-answer（K6）。
    pid = await ctx.new_project("S6d blank never answers")
    ck = await seed_parked_interrupt(pid, ctx.user_id)
    turn = await ctx.chat(
        pid, "", attachments=[{"id": "att-1", "name": "notes.txt", "type": "file"}]
    )
    check(turn.get("answered_question") is None,
          "a blank attachment-only turn never answers a interrupt", turn)
    q = await message_row(ck["question_id"])
    check(q.get("answer") is None or (q["answer"] or {}).get("text") == "superseded",
          "the interrupt was not auto-answered (a new docked question superseding "
          "it is the designed cascade)", q.get("answer"))
    await ctx.cleanup()

    # e) bail 级联：节点 done(bailed) + 下游级联 skipped + run COMPLETED。
    pid = await ctx.new_project("S6e interrupt bail")
    ck = await seed_parked_interrupt(pid, ctx.user_id, with_downstream=True)
    res = await ctx.answer(ck["question_id"], {"kind": "bail"})
    check(res.status_code == 200, "bail lands", res.text)
    steps = {s["id"]: s for s in await step_rows(ck["run_id"])}
    node = steps[ck["node_id"]]
    check(node["status"] == "done" and node["spec"].get("bailed") is True,
          "the interrupt settles done with spec.bailed", node)
    child = steps[ck["child_id"]]
    check(child["status"] == "skipped" and child["error"] == "user bailed",
          "the downstream cascade-skips with the non-failure reason", child)
    run = await run_row(ck["run_id"])
    check(run["status"] == "completed",
          "the bailed run settles COMPLETED, never failed", run["status"])
    await ctx.cleanup()

    # f) 插话后续跑（ADR-053 R2 chat path）：进度插话 → get_run_status 读
    #    （inspecting 相位帧）→ 正常回答 + 代码拼装提醒尾 + 问题保持
    #    pending + run 保持 parked → 再打字母唤醒。
    #    LLM 方差说明：进度问先读后答是设计行为（answer 工具契约：run
    #    readouts call get_run_status first）；不读直接答红了 = chat_intent
    #    prompt 回归信号，不是剧本松劲。
    pid = await ctx.new_project("S6f interjection resumes later")
    ck = await seed_parked_interrupt(pid, ctx.user_id)
    stream = await ctx.chat_stream(pid, "how is the run doing?")
    check(stream.failed is None, "the interjection turn has no turn.failed",
          stream.failed)
    check(stream.completed is not None, "the interjection turn completes")
    turn = stream.completed
    status_key = PERCEPTION_TOOLS["get_run_status"].activity_key
    check(any(t.get("phase") == "inspecting" and t.get("key") == status_key
              for t in stream.thinking),
          "the progress question reads first (get_run_status's inspecting frame)",
          stream.thinking)
    check(turn.get("answered_question") is None,
          "an interjection never settles the parked interrupt", turn)
    check(terminal_tool_of(turn) == "answer",
          "the progress interjection closes on the answer call", turn)
    content = turn["assistant_message"].get("content") or ""
    check_stream_law(stream, content, "the read-first interjection")
    check(has_reminder_tail(content),
          "the reply carries the code-composed reminder tail", content[-200:])
    q = await message_row(ck["question_id"])
    check(q.get("answer") is None, "the interrupt question stays pending",
          q.get("answer"))
    check((await run_row(ck["run_id"]))["status"] == "waiting_human",
          "the run stays parked through the interjection")
    turn = await ctx.chat(pid, "a")
    aq = turn.get("answered_question")
    check(aq is not None and aq["id"] == ck["question_id"],
          "the follow-up letter answer wakes the run", turn)
    await wait_run_status(ck["run_id"], {"completed"})
    await ctx.cleanup()


# ---- S7 核⑦ caption mode ----------------------------------------------------------


async def s7_caption_mode_gate(ctx: Ctx) -> None:
    """核⑦ caption mode 三拍（2026-08-29 root-fix 回归座 + ADR-053 形态律
    wire 面）：caption 选择 = 选项问（options 非空——形态律下前端 pill 化，
    本脚本锁 wire）——

    A) 有独立第二语言（项目 de / 素材 en）→ 选择问先 dock（不起 run），
       回答后 replay 出计划：回执 kind=option + 选中的 mode 钉进
       pending_brief；
    B) 无独立第二语言（项目 en / 素材 en）→ 不问，run 直接带
       run.context.caption_mode == "source_only"（§2.3/D4）；
    C) 答 → 追问 → Start：answered mode 存活于中间修订轮（stash 继承：
       fresh LLM-set > fresh keyword > stashed answer）。

    LLM 判定有抖动（"make a quote card" 可能回反问或提别的链——两者都
    正确地跳过 caption 闸门），各部各给 3 次尝试直到 write_quotes 落地。
    """
    material = "Some keynote transcript about the future of embodied intelligence."

    # A) distinct alt language exists → dock first, answer, plan follows.
    pid = await ctx.new_project("S7-A chat caption dock")
    await set_project_language(pid, "de")
    await seed_asset(pid, ctx.user_id, AssetType.VIDEO, "keynote.mp4",
                     extracted_text=material, meta={"language": "en"})
    await seed_completed_run(pid)
    docked: dict | None = None
    for prompt in ("make a quote card from the video",
                   "pull the sharpest quotes from my keynote into quote cards",
                   "the quote cards, please"):
        turn = await ctx.chat(pid, prompt)
        q = turn["assistant_message"].get("question")
        if q and q.get("kind") == "question" and any(
            o.get("id", "").startswith("caption_mode_") for o in q.get("options", [])
        ):
            docked = turn
            break
        rid = turn.get("run_id")
        if rid:  # a non-quotes run started (the gate correctly skipped it)
            await wait_run_terminal(rid)
    check(docked is not None,
          "A: the caption question docks for a chat-path quote-cards ask")
    check(terminal_tool_of(docked) == "caption_gate",
          "A: the turn closes on the caption gate (propose_tasks' sub-dock)",
          docked)
    check(docked.get("run_id") is None, "A: no run before the answer", docked)
    check(len((docked["assistant_message"].get("question") or {}).get("options") or []) > 0,
          "A: the caption ask is an OPTIONS question (形态律 pill 的 wire 面)",
          docked["assistant_message"].get("question"))
    ans = await ctx.answer(docked["assistant_message"]["id"],
                           {"kind": "option", "option_id": "caption_mode_bilingual"})
    check(ans.status_code in (200, 201), "A: caption answer accepted", ans.text)
    answered_row = ans.json().get("answered_question") or {}
    check((answered_row.get("answer") or {}).get("kind") == "option",
          "A: 答案行落库 kind=option（AnsweredQuestion 已答块的 wire 面）",
          answered_row.get("answer"))
    follow = ans.json().get("follow_up") or {}
    check(is_plan_dock(follow),
          "A: the answer replays the stashed proposal into a plan", follow)
    # 计划行自完备（方案 B）：answer 轮的 follow_up 行同样自带链——前端
    # 从 envelope 直渲计划卡，无需 pending_brief 二次拉取。
    check(bool(((follow.get("intent") or {}).get("tasks")) or []),
          "A: the follow-up row self-carries the chain (intent column)",
          follow.get("intent"))
    plan = await pending_plan(ctx, pid)
    check(((plan or {}).get("intent") or {}).get("caption_mode") == "bilingual",
          "A: the picked mode rides pending_brief end-to-end", plan)

    # B) no distinct alt (en/en) → no question; source_only rides run.context.
    pid_b = await ctx.new_project("S7-B chat caption source_only")
    await set_project_language(pid_b, "en")
    await seed_asset(pid_b, ctx.user_id, AssetType.VIDEO, "keynote.mp4",
                     extracted_text=material, meta={"language": "en"})
    await seed_completed_run(pid_b)
    mode: str | None = None
    tools_seen: list = []
    for prompt in ("make a quote card from the video",
                   "pull the sharpest quotes from my keynote into quote cards",
                   "the quote cards, please"):
        turn = await ctx.chat(pid_b, prompt)
        rid = turn.get("run_id")
        if rid is None:
            continue  # ask-back — nudge again
        runs = await ctx.client.get(f"/projects/{pid_b}/runs")
        born = next((r for r in runs.json() if r.get("id") == rid), None) or {}
        run_ctx = born.get("context") or {}
        tools_seen = [t.get("tool") for t in run_ctx.get("tasks") or []]
        if "write_quotes" in tools_seen:
            mode = run_ctx.get("caption_mode")
            break
        await wait_run_terminal(rid)  # non-quotes run — settle, then retry
    check(mode is not None, "B: no write_quotes run after 3 turns", tools_seen)
    check(mode == "source_only", "B: run.context.caption_mode", mode)

    # C) 答 → 追问 → Start：the answered mode must survive a refinement turn
    #    between the answer and Start — the plan path overwrites
    #    pending_brief wholesale with the fresh call (caption_mode=None
    #    whenever the turn doesn't re-mention it), which used to drop the
    #    answer on the floor: the run started single-language and the NEXT
    #    turn re-asked the already-answered question. Now the stash is
    #    inherited (fresh LLM-set > fresh keyword > stashed answer).
    pid_c = await ctx.new_project("S7-C caption answer survives refinement")
    await set_project_language(pid_c, "de")
    await seed_asset(pid_c, ctx.user_id, AssetType.VIDEO, "keynote.mp4",
                     extracted_text=material, meta={"language": "en"})
    docked_c: dict | None = None
    for prompt in ("make quote cards from the video",
                   "pull the keynote's sharpest quotes into cards",
                   "the quote cards, please"):
        turn = await ctx.chat(pid_c, prompt)
        q = turn["assistant_message"].get("question")
        if q and q.get("kind") == "question" and any(
            o.get("id", "").startswith("caption_mode_") for o in q.get("options", [])
        ):
            docked_c = turn
            break
    check(docked_c is not None,
          "C: the caption question docks on the plan path")
    check(terminal_tool_of(docked_c) == "caption_gate",
          "C: the turn closes on the caption gate (present_plan's sub-dock)",
          docked_c)
    ans = await ctx.answer(docked_c["assistant_message"]["id"],
                           {"kind": "option", "option_id": "caption_mode_bilingual"})
    check(ans.status_code in (200, 201), "C: caption answer accepted", ans.text)
    # The answer's replay already docks the plan; refinement nudges may
    # re-dock it (superseding the row) — always Start the LATEST live row.
    follow_c = ans.json().get("follow_up") or {}
    plan_qid: str | None = follow_c.get("id") if is_plan_dock(follow_c) else None
    check(plan_qid is not None, "C: the answer replays the stashed plan", follow_c)
    reasked: dict | None = None
    for nudge in ("make it 3 cards instead",
                  "change that to 3 quote cards",
                  "actually, only 3 cards"):  # 修订措辞 — 散文确认会绕过追问路径
        turn = await ctx.chat(pid_c, nudge)
        q = turn["assistant_message"].get("question")
        if q and any(o.get("id", "").startswith("caption_mode_")
                     for o in q.get("options", [])):
            reasked = q  # the bug: the answered question is re-asked
            break
        plan = await pending_plan(ctx, pid_c)
        check(((plan or {}).get("intent") or {}).get("caption_mode") == "bilingual",
              "C: the refinement turn keeps the answered caption_mode", plan)
        if is_plan_dock(turn["assistant_message"]):
            plan_qid = turn["assistant_message"]["id"]
            break
    check(reasked is None, "C: the answered question is never re-asked", reasked)
    check(plan_qid is not None, "C: a plan docks after the refinement")
    # Start THROUGH THE PANEL: the frontend's normalize strips fields it
    # doesn't edit, so its Start payload carries the plan's intent minus
    # caption_mode — the server must inherit the answered mode from the
    # stored pending brief ("not mentioned" ≠ "retracted", 2026-08-29).
    plan = await pending_plan(ctx, pid_c)
    panel_intent = dict((plan or {}).get("intent") or {})
    check(bool(panel_intent), "C: pending plan carries an intent", plan)
    panel_intent.pop("caption_mode", None)
    res = await ctx.answer(plan_qid, {"kind": "start", "intent": panel_intent})
    check(res.status_code == 200, "C: plan start accepted", res.text)
    rid_c = res.json()["answered_question"].get("workflow_run_id")
    check(rid_c, "C: run id on the answered plan", res.json())
    runs = await ctx.client.get(f"/projects/{pid_c}/runs")
    born_c = next((r for r in runs.json() if r.get("id") == rid_c), None) or {}
    check((born_c.get("context") or {}).get("caption_mode") == "bilingual",
          "C: run.context.caption_mode survives answer → refine → Start",
          born_c.get("context"))


# ---- S8 核⑧ research 全链 ---------------------------------------------------------


async def s8_research_grounds_writer(ctx: Ctx) -> None:
    """核⑧ research 试点全链（ADR-052 B4，有界 loop 节点）：chat 出书 → 面板
    手编 chain 为 [research, write_post] 起步 → research step done +
    spec.research_brief 钢印 + writer 在 research 之后完成 + post 产物存在。

    网络方差说明：活 DDG 可能全灭（无网 / 被限流）——诚实降级下 brief 带
    caveat 自述、run 照样 completed。断言只看「钢印存在 + 步骤有序 +
    产物存在」，不看简报内容质量（那是 prompt / provider 层的事）。"""
    pid = await ctx.new_project("S8 research grounds writer")

    turn1 = await ctx.chat(
        pid,
        "Write a LinkedIn post about the EU AI Act's 2026 enforcement — "
        "research the latest developments first.",
    )
    turn1 = await answer_caption_gate(ctx, turn1)  # no-op unless the dock quotes first
    check(terminal_tool_of(turn1) == "present_plan",
          "a rooted topic closes on the present_plan call", turn1)
    check(is_plan_dock(turn1["assistant_message"]),
          "a rooted topic docks a plan", turn1["assistant_message"])
    plan = (await ctx.results(pid)).get("pending_brief")
    qid = turn1["assistant_message"]["id"]

    # 面板手编起步（S5 先例）：chain 换成确定性的 [research, write_post]。
    edited = dict(plan["intent"])
    edited["tasks"] = [
        {
            "tool": "research",
            "params": {"query": "EU AI Act 2026 enforcement latest developments"},
        },
        {"tool": "write_post", "params": {"language": "en"}},
    ]
    res = await ctx.answer(qid, {"kind": "start", "intent": edited})
    check(res.status_code == 200, "the research chain starts", res.text)
    run_id = res.json()["answered_question"].get("workflow_run_id")
    check(run_id, "a run was born", res.json())

    row = await wait_run_status(run_id, {"completed", "failed"}, timeout=600.0)
    check(row["status"] == "completed",
          "the run completes (research is best-effort, never a blocker)", row["status"])

    steps = await step_rows(run_id)
    research_steps = [s for s in steps if s["kind"] == "research"]
    check(len(research_steps) == 1, "one hoisted research step", [s["kind"] for s in steps])
    rs = research_steps[0]
    check(rs["status"] == "done",
          "the research step completes even on a dry trail", rs["error"])
    check(isinstance((rs["spec"] or {}).get("research_brief"), dict),
          "the brief is stamped into the step spec (spec.research_brief)", rs["spec"])
    writer = next(s for s in steps if s["kind"] == "write_post")
    check(writer["status"] == "done",
          "the writer completes after the research edge", writer["error"])

    async with AsyncSessionLocal() as db:
        outs = (
            await db.execute(
                select(Output).where(
                    Output.project_id == uuid.UUID(pid), Output.type == "post"
                )
            )
        ).scalars().all()
    check(len(outs) >= 1, "the post output exists", len(outs))


# ---- S9 核⑨ 问事不出书 -------------------------------------------------------------


async def s9_consult_never_books(ctx: Ctx) -> None:
    """核⑨ 问事不出书：能力提问 / 闲聊 → 纯 answer（无 dock 无 run 无 brief）；
    无计划 "start it" 不死路不起 run（rootless → 主题问门槛接住，永不裸跑）。"""
    pid = await ctx.new_project("S9 consult")

    turn1 = await ctx.chat(pid, "what can you do?")
    check(terminal_tool_of(turn1) == "answer",
          "a capability question closes on the answer call", turn1)
    check(turn1["run_id"] is None, "capability question starts no run")
    check(not turn1["assistant_message"].get("question"), "no question docks",
          turn1["assistant_message"])
    check(has_prose(turn1["assistant_message"]), "a prose answer lands")

    turn2 = await ctx.chat(pid, "hello, how are you today?")
    check(terminal_tool_of(turn2) == "answer",
          "small talk closes on the answer call", turn2)
    check(turn2["run_id"] is None, "small talk starts no run", turn2)
    check(not turn2["assistant_message"].get("question"),
          "small talk docks nothing", turn2["assistant_message"])
    check(has_prose(turn2["assistant_message"]), "small talk gets an answer")

    turn3 = await ctx.chat(pid, "start it")
    check(terminal_tool_of(turn3) in ("ask_user", "answer"),
          "a baseless start closes on ask_user (出书门槛) or answer — never "
          "present_plan / start_run (LLM 方差: the rootless-start phrasing "
          "reads as either a work wish or a capability question)", turn3)
    check(turn3["run_id"] is None, "a baseless start never launches a run", turn3)
    check(not is_plan_dock(turn3["assistant_message"]),
          "a baseless start never docks a groundless plan either (出书门槛接住)",
          turn3["assistant_message"])
    check(await count_runs(pid) == 0, "no run the whole journey")
    plan = await pending_plan(ctx, pid)
    check(plan is None or plan.get("intent") is None,
          "no plan parks on consults", plan)


# ---- S10 SSE 流式 --------------------------------------------------------------------


async def s10_sse_turn_streaming(ctx: Ctx) -> None:
    """S10 SSE 回合（工具 loop 线格式，ADR-077 判词②）：answer 单轮流式
    （concat(deltas) == 信封散文）；draft 流计划复述 + drafting 相位帧；
    ask 流框架散文 + question.preview 预览帧先于终态信封。流式律的两款
    关系（单轮 == / 读先 startswith / 拒轮方差注记）归 check_stream_law。"""
    pid = await ctx.new_project("S10 sse streaming")
    await seed_asset(pid, ctx.user_id, AssetType.VIDEO, "keynote.mp4")

    # Answer turn: prose streams on the content channel (iteration 0 only —
    # later iterations run quiet by the repair-never-streams law). The
    # phrasing mirrors the system prompt's few-shot example verbatim — the
    # answer/draft judgment is LLM variance, and the single-iteration
    # relation needs the answer call to be near-deterministic.
    stream = await ctx.chat_stream(pid, "what can you generate?")
    check(stream.failed is None, "answer turn has no turn.failed", stream.failed)
    check(stream.completed is not None, "answer turn ends with turn.completed")
    check(terminal_tool_of(stream.completed) == "answer",
          "the capability question closes on the answer call", stream.completed)
    content = (stream.completed["assistant_message"].get("content") or "")
    check(len(stream.deltas) > 0, "answer turn streams prose deltas")
    check_stream_law(stream, content, "answer turn")
    check(stream.completed["run_id"] is None, "answer turn starts no run")

    # Draft turn: the plan echo (intent.answer) streams as deltas; the
    # present_plan name-known frame moves the phase beat to drafting BEFORE
    # the envelope (相位完整律's tool seat); the dock rides the envelope.
    stream = await ctx.chat_stream(pid, "Cut 3 highlight clips from my talk")
    check(stream.failed is None, "draft turn has no turn.failed", stream.failed)
    check(stream.completed is not None, "draft turn ends with turn.completed")
    check(terminal_tool_of(stream.completed) == "present_plan",
          "the draft closes on the present_plan call", stream.completed)
    check(is_plan_dock(stream.completed["assistant_message"]),
          "draft turn docks the plan via the envelope",
          stream.completed["assistant_message"])
    check(any(t.get("phase") == "drafting" for t in stream.thinking),
          "the present_plan name-known frame moves the beat to drafting",
          stream.thinking)
    content = (stream.completed["assistant_message"].get("content") or "")
    plan = (await ctx.results(pid)).get("pending_brief")
    echo = (plan["intent"].get("answer") or "")
    check(content == echo, "the envelope content IS the persisted plan echo",
          f"{content[:120]!r} vs {echo[:120]!r}")
    check_stream_law(stream, content, "draft turn")

    # Ask turn (ask 三分解剖): the framing prose streams like the draft echo;
    # the pill's whole payload lands EARLY as question.preview (pre-execution
    # — a rejected iteration re-previews and the client rolls back, so the
    # LAST preview is the authoritative one) and must match the envelope's
    # docked payload field for field.
    pid2 = await ctx.new_project("S10 sse ask streaming")
    stream = await ctx.chat_stream(pid2, "I want a social post.")
    check(stream.failed is None, "ask turn has no turn.failed", stream.failed)
    check(stream.completed is not None, "ask turn ends with turn.completed")
    check(terminal_tool_of(stream.completed) == "ask_user",
          "the bare wish closes on the ask_user call", stream.completed)
    msg = stream.completed["assistant_message"]
    q = msg.get("question") or {}
    check(q.get("kind") == "question", "the bare wish docks the ask", msg)
    content = (msg.get("content") or "")
    check(len(stream.deltas) > 0, "ask turn streams the framing prose", q)
    check_stream_law(stream, content, "ask turn")
    check(bool((q.get("question") or "").strip())
          and content != q["question"],
          "the bare question rides the payload, distinct from the prose", q)
    check(len(stream.previews) >= 1,
          "the ask's question.preview frame precedes the terminal envelope",
          stream.thinking)
    preview = stream.previews[-1]
    check(preview.get("question") == q.get("question"),
          "the preview's bare question IS the docked payload's", preview)
    check([o.get("id") for o in preview.get("options") or []]
          == [o.get("id") for o in q.get("options") or []],
          "the preview's options match the docked payload's", preview)
    check(preview.get("slot") == q.get("slot"),
          "the preview's slot matches the docked payload's", preview)
    check(isinstance(preview.get("allow_freeform"), bool),
          "the preview carries allow_freeform", preview)
    check(bool((preview.get("default_path") or "").strip()),
          "the preview carries the default path", preview)


# ---- S11 整条源规则 + materialize 注入矩阵 ----------------------------------------------


async def s11_whole_source_and_materialize_matrix(ctx: Ctx) -> None:
    """S11 整条源规则（ADR-043 考纲原点）+ materialize 注入矩阵：

    活链——"给我的视频加中英双语字幕" → 链 = translate_clip 单独（无
    select_clips）；derived 预览 = 整条视频 + 字幕版；Start 后编译图 =
    materialize_source → translate_clip。
    进程内——media/stills/existing 三画像注入矩阵 + 无画像编译期指名拒绝 +
    select_clips 在场不注入。"""
    # 活链段 (whole-video subs)。
    pid = await ctx.new_project("S11 whole-video subs")
    # The source's language is pinned (an English keynote): the 同源语言护栏
    # prompt (2026-08-17) resolves 中英双语 → target zh deterministically —
    # without it the planner infers the source language from the zh prompt.
    await seed_asset(pid, ctx.user_id, AssetType.VIDEO, "keynote.mp4", meta={"language": "en"})

    turn1 = await ctx.chat(pid, "给我的视频加中英双语字幕")
    check(terminal_tool_of(turn1) == "present_plan",
          "turn1 closes on the present_plan call", turn1)
    check(is_plan_dock(turn1["assistant_message"]), "turn1 docks a task_book",
          turn1["assistant_message"])
    plan = (await ctx.results(pid)).get("pending_brief")
    tasks = plan_tasks(plan)
    check(not any(t["tool"] == "select_clips" for t in tasks),
          "whole-source intent never routes through select_clips", tasks)
    subs = [t for t in tasks if t["tool"] == "translate_clip"]
    check(len(subs) == 1 and task_params(subs[0]).get("target_language") == "zh",
          "one translate task into Chinese", tasks)
    check(task_params(subs[0]).get("bilingual") is True,
          "双语 → bilingual: true", tasks)
    derived = (plan or {}).get("derived") or []
    check(any(r.get("type") == "video" for r in derived),
          "the derived preview shows the whole video", derived)
    check(any(r.get("variant") == "subs" for r in derived),
          "the derived preview shows the subtitled version", derived)

    res = await ctx.answer(turn1["assistant_message"]["id"], {"kind": "start"})
    check(res.status_code == 200, "dock Start answers the plan", res.text)
    run_id = res.json()["answered_question"]["workflow_run_id"]
    steps = await step_rows(run_id)
    kinds = [s["kind"] for s in steps]
    check("materialize_source" in kinds,
          "the compiled graph materializes the source", kinds)
    check("translate_clip" in kinds, "the translate node is in the graph", kinds)
    check("select_clips" not in kinds, "no highlight extraction anywhere", kinds)
    await ctx.cleanup()

    # 进程内矩阵（编译面，零 LLM）。
    def node_kinds(nodes: list) -> list[str]:
        return [ns.kind for ns in nodes]

    translate = TaskItem(
        tool="translate_clip",
        params={"target_language": "zh", "bilingual": True},
    )

    # media profile: preprocess → materialize_source → translate.
    media = compile_graph(
        TaskSpec(tasks=[translate]),
        materialize_profile="media",
    )
    check("materialize_source" in node_kinds(media),
          "media profile injects materialize_source", node_kinds(media))
    check("select_clips" not in node_kinds(media), "no highlight extraction",
          node_kinds(media))
    mat = next(ns for ns in media if ns.kind == "materialize_source")
    check(any(media[i].kind == "preprocess" for i in mat.inputs),
          "materialize hangs off preprocess", mat.inputs)
    tr = next(ns for ns in media if ns.kind == "translate_clip")
    check(any(media[i].kind == "materialize_source" for i in tr.inputs),
          "translate hangs off materialize via its after declaration", tr.inputs)

    # stills profile: align_stills first, materialize takes both inputs.
    stills = compile_graph(
        TaskSpec(tasks=[translate]),
        materialize_profile="stills",
    )
    check("align_stills" in node_kinds(stills),
          "stills profile injects align_stills first", node_kinds(stills))
    mat = next(ns for ns in stills if ns.kind == "materialize_source")
    mat_input_kinds = [stills[i].kind for i in mat.inputs]
    check("preprocess" in mat_input_kinds and "align_stills" in mat_input_kinds,
          "materialize takes preprocess + align_stills", mat_input_kinds)

    # existing profile: bare translate with empty inputs (= act on existing clips).
    existing = compile_graph(
        TaskSpec(tasks=[translate]),
        materialize_profile="existing",
    )
    check("materialize_source" not in node_kinds(existing),
          "existing clips need no materialization", node_kinds(existing))
    tr = next(ns for ns in existing if ns.kind == "translate_clip")
    check(tr.inputs == [], "the modifier's inputs stay empty (existing clips)", tr.inputs)

    # No profile: compile-time rejection naming the culprit.
    try:
        compile_graph(TaskSpec(tasks=[translate]), materialize_profile=None)
        check(False, "a dangling transform rejects at compile", None)
    except ValueError as exc:
        check("translate clip" in str(exc),
              "the error names the dangling transform", str(exc))

    # select_clips present: no injection, translate hangs off select_clips.
    with_clips = compile_graph(
        TaskSpec(
            tasks=[
                TaskItem(tool="select_clips", params={"count": 3}),
                translate,
            ]
        ),
        materialize_profile=None,
    )
    check("materialize_source" not in node_kinds(with_clips),
          "select_clips present — no injection", node_kinds(with_clips))
    tr = next(ns for ns in with_clips if ns.kind == "translate_clip")
    check(any(with_clips[i].kind == "select_clips" for i in tr.inputs),
          "translate hangs off select_clips", tr.inputs)


# ---- S12 merge_brief 来源矩阵 ----------------------------------------------------------


async def s12_merge_brief_source_matrix(ctx: Ctx) -> None:
    """S12 brief 来源优先级三态矩阵（ADR-052 B2 D1-C1，进程内纯函数）：
    user-stated 永不反向覆盖 / user 重申恒胜 / inferred 压 default /
    default 永不压 inferred / no-opinion 槽永不落账 / 整账 None 原样返回 /
    asked 簿永不吃 LLM 提议。"""
    del ctx  # in-process pure-function matrix — no API, no DB rows
    from app.chat.service import merge_brief
    from app.models.schemas import Brief, BriefSlot, BriefSlotSource as Src

    def brief(**slots) -> Brief:
        return Brief(**slots)

    def slot(value, source) -> BriefSlot:
        return BriefSlot(value=value, source=source)

    # 1. user-stated survives inferred AND default proposals (永不反向覆盖).
    stored = brief(topic=slot("grid storage", Src.USER_STATED))
    out = merge_brief(
        brief(
            topic=slot("renewables", Src.INFERRED),
            audience=slot("CTOs", Src.INFERRED),
        ),
        stored,
    )
    check(out.topic.value == "grid storage"
          and out.topic.source == Src.USER_STATED,
          "user-stated topic survives an inferred proposal", out.topic)
    out = merge_brief(brief(topic=slot("anything", Src.DEFAULT)), stored)
    check(out.topic.value == "grid storage",
          "user-stated topic survives a default proposal", out.topic)

    # 2. The user re-stating a slot always wins (user-stated ≥ user-stated —
    #    chat 修订恒胜).
    out = merge_brief(brief(topic=slot("renewables", Src.USER_STATED)), stored)
    check(out.topic.value == "renewables"
          and out.topic.source == Src.USER_STATED,
          "a re-stated slot lands (the user spoke again)", out.topic)

    # 3. inferred lands over an empty/default slot and over a default value;
    #    default never lands over inferred.
    stored = brief(audience=slot("general public", Src.DEFAULT))
    out = merge_brief(brief(audience=slot("first-time founders", Src.INFERRED)), stored)
    check(out.audience.value == "first-time founders"
          and out.audience.source == Src.INFERRED,
          "inferred outranks default", out.audience)
    out = merge_brief(brief(audience=slot("everyone", Src.DEFAULT)), out)
    check(out.audience.value == "first-time founders",
          "default never overwrites inferred", out.audience)

    # 4. A no-opinion slot (value=None) never lands — stored survives; and
    #    fresh inference re-lands over stale inference (same rank, latest wins).
    out = merge_brief(
        brief(tone=BriefSlot(source=Src.INFERRED), topic=slot("new angle", Src.INFERRED)),
        brief(tone=slot("sharp", Src.USER_STATED), topic=slot("old angle", Src.INFERRED)),
    )
    check(out.tone.value == "sharp", "a None update never lands", out.tone)
    check(out.topic.value == "new angle",
          "same-rank updates land (fresh inference over stale)", out.topic)

    # 5. constraints 是数组槽（ADR-064 顺形律）——按条目 keyed union：新条目
    #    追加、同文本冲突逐项 precedence（user-stated 永不反向覆盖）、归一化
    #    键大小写/空白不敏感。
    stored = brief(constraints=[slot("keep it under 200 words", Src.USER_STATED)])
    out = merge_brief(
        brief(constraints=[
            slot("add hashtags", Src.INFERRED),
            slot("Keep it under 200  words", Src.INFERRED),  # 同键不同来源
        ]),
        stored,
    )
    check(
        [c.value for c in out.constraints]
        == ["keep it under 200 words", "add hashtags"],
        "constraints keyed union: new item appends, same-key user-stated survives",
        out.constraints,
    )
    check(
        out.constraints[0].source == Src.USER_STATED,
        "per-item precedence: a same-key inferred item never demotes user-stated",
        out.constraints,
    )
    # 同键重申恒胜（user-stated ≥ user-stated — 与标量槽同尺）。
    out = merge_brief(
        brief(constraints=[slot("keep it under 100 words", Src.USER_STATED)]),
        out,
    )
    check(
        [c.value for c in out.constraints]
        == ["keep it under 100 words", "add hashtags"],
        "the user re-stating a constraint wins (chat 修订恒胜)",
        out.constraints,
    )
    # 旧槽形状（对象包数组/对象包字符串）读容忍——存量 pending_brief 行。
    legacy = Brief.model_validate(
        {"constraints": {"value": ["a", "b"], "source": "user-stated"}}
    )
    check(
        [c.value for c in legacy.constraints] == ["a", "b"]
        and all(c.source == Src.USER_STATED for c in legacy.constraints),
        "legacy object-wrapped constraints normalize on read",
        legacy.constraints,
    )
    legacy_str = Brief.model_validate(
        {"constraints": {"value": "one long sentence", "source": "inferred"}}
    )
    check(
        [c.value for c in legacy_str.constraints] == ["one long sentence"],
        "object-wrapped bare-string constraints normalize on read",
        legacy_str.constraints,
    )
    bare = Brief.model_validate({"constraints": ["keep 1:1"]})
    check(
        [c.value for c in bare.constraints] == ["keep 1:1"],
        "bare-string items normalize",
        bare.constraints,
    )
    made_up = Brief.model_validate(
        {"constraints": [{"value": "x", "source": "explicit"}]}
    )
    check(
        made_up.constraints[0].source == Src.INFERRED,
        "an off-enum source coerces to inferred (never overclaims user-stated)",
        made_up.constraints,
    )

    # 6. update=None returns the stored brief (start/answer calls carry
    #    no proposal); the merge never mutates the stored input in place.
    stored = brief(topic=slot("grid storage", Src.USER_STATED))
    check(merge_brief(None, stored) is stored, "None update returns stored verbatim")
    merge_brief(brief(audience=slot("CTOs", Src.INFERRED)), stored)
    check(stored.audience.value is None, "the merge never mutates the stored input")

    # 7. The code-owned asked roll never lands from an LLM proposal (禁 LLM
    #    簿记, D2-C2) — it rides only the stored side of the merge.
    stored.asked = ["topic"]
    upd = brief()
    upd.asked = ["audience"]
    out = merge_brief(upd, stored)
    check(out.asked == ["topic"],
          "an LLM-proposed asked roll never lands (code-owned)", out.asked)


async def s13_credits_insufficient_birthplace_422(ctx: Ctx) -> None:
    """积分① 余额不足出生地拦截：钱包置零 → dock 计划 → typed Start
    收结构化 422 {code, balance, required}（typed /generate 同形同义）
    → 零 run、零台账行（hold 与 run 同事务回滚）；负余额用户下一次 hold
    必拒——含 0 元 hold（BILLING §5：gate at the start）。"""
    # 专用 fixture 用户：钱包手工置零——不动共享 ctx 用户的余额（S4 等
    # 剧本还要起真 run）；结束后清台账/钱包行（FK 序）。
    user_id = await make_user()
    local = Ctx(user_id, keep=False)
    try:
        async with AsyncSessionLocal() as db:
            db.add(Wallet(user_id=user_id, balance=0))
            await db.commit()

        # 账户控制台 credits 槽的供给端：GET /wallet 必须真服务——held() 的
        # SQL JSONB 分组曾自 Day 2 起恒 500（控制台「—」案，2026-09-06 修）。
        res_w = await local.client.get("/wallet")
        check(res_w.status_code == 200
              and (res_w.json() or {}).get("balance") == 0,
              "GET /wallet serves the console credits slot", res_w.text)

        pid = await local.new_project("S13 credits 422")
        await seed_asset(pid, user_id, AssetType.TRANSCRIPT, "talk.txt",
                         extracted_text="My talk about grid storage auctions.",
                         processed=True)
        turn1 = await local.chat(pid, "write a LinkedIn post from my talk")
        turn1 = await answer_caption_gate(local, turn1)
        check(is_plan_dock(turn1["assistant_message"]),
              "turn1 docks a task_book", turn1["assistant_message"])

        # typed Start（答题端点 kind=start）——结构化 422。
        res = await local.answer(turn1["assistant_message"]["id"], {"kind": "start"})
        check(res.status_code == 422, "typed Start is a 422 on zero balance", res.text)
        detail = (res.json() or {}).get("detail") or {}
        check(detail.get("code") == "credits.insufficient",
              "the payload carries the user-level code", detail)
        check(detail.get("balance") == 0, "balance rides the payload", detail)
        check(isinstance(detail.get("required"), int) and detail["required"] > 0,
              "required rides the payload", detail)
        check(await count_runs(pid) == 0, "no run was born", None)

        # typed /generate（legacy fallback 路）——同形同义。
        res2 = await local.client.post(
            f"/projects/{pid}/generate",
            json={
                "tasks": [{"tool": "write_post", "params": {"language": "en"}}],
                "target_language": "en",
            },
        )
        check(res2.status_code == 422, "/generate is a 422 on zero balance", res2.text)
        detail2 = (res2.json() or {}).get("detail") or {}
        check(detail2.get("code") == "credits.insufficient"
              and detail2.get("balance") == 0 and detail2.get("required", 0) > 0,
              "the /generate payload is the same shape", detail2)

        # 台账零行：check_hold 拒在 hold_run 之前，run 行也随事务回滚。
        async with AsyncSessionLocal() as db:
            n = (
                await db.execute(
                    select(func.count())
                    .select_from(CreditTransaction)
                    .where(CreditTransaction.user_id == user_id)
                )
            ).scalar_one()
        check(n == 0, "no ledger rows leaked from the rejected births", n)

        # 负余额 hold 必拒（BILLING §5）——含 0 元 hold。
        async with AsyncSessionLocal() as db:
            wallet = await db.get(Wallet, user_id)
            wallet.balance = -50
            await db.commit()
        raised: CreditsInsufficientError | None = None
        async with AsyncSessionLocal() as db:
            try:
                await check_hold(db, user_id=user_id, required=0)
            except CreditsInsufficientError as e:
                raised = e
        check(raised is not None and raised.balance == -50,
              "a negative balance fails even a free (0) hold", raised)
    finally:
        await local.cleanup()
        await local.close()
        async with AsyncSessionLocal() as db:
            await db.execute(
                delete(CreditTransaction).where(CreditTransaction.user_id == user_id)
            )
            await db.execute(delete(Wallet).where(Wallet.user_id == user_id))
            await db.commit()


async def s14_failed_run_zero_capture_full_release(ctx: Ctx) -> None:
    """积分② 失败不扣费：确定性失败探针（translate_clip 缺参，08-14 先例）
    被活 worker 执行到 FAILED、两个下游级联 skipped → 台账零 capture、
    hold 全额 release、余额回到赠额；进程内 capture 幂等（重复调用结构
    性 no-op = 复位重跑只记一次）+ QualityBounce 重跑差额落 attempt 键。"""
    user_id = await make_user()
    local = Ctx(user_id, keep=False)
    hold_amount = 120
    try:
        pid = await local.new_project("S14 no charge on failure")

        # A) 活 worker 探针：seeded run（缺参 translate_clip + 两个下游
        #    节点），hold 走真动词 hold_run，认领/失败/级联/收官/释放全
        #    走真路径（需要 dev worker 在跑——剧本通用前提）。
        async with AsyncSessionLocal() as db:
            wallet = await get_or_create_wallet(db, user_id)  # 开户赠额
            grant = int(wallet.balance)
            run = WorkflowRun(
                project_id=uuid.UUID(pid),
                status=WorkflowStatus.PENDING,
                context={"outputs": [{"type": "clip"}], "target_language": "en"},
            )
            db.add(run)
            await db.flush()
            bad = WorkflowStep(run_id=run.id, kind="translate_clip", status="pending",
                               seq=1, spec={}, estimate=None)
            down1 = WorkflowStep(run_id=run.id, kind="add_music", status="pending",
                                 seq=2, spec={}, estimate=None)
            down2 = WorkflowStep(run_id=run.id, kind="remove_filler", status="pending",
                                 seq=3, spec={}, estimate=None)
            db.add_all([bad, down1, down2])
            await db.flush()
            down1.inputs = [str(bad.id)]
            down2.inputs = [str(down1.id)]
            await hold_run(db, user_id=user_id, run_id=run.id, amount=hold_amount)
            await db.commit()
            run_id = str(run.id)

        row = await wait_run_status(run_id, {"failed"}, timeout=120.0)
        check(row["status"] == "failed", "the probe run settles FAILED", row)
        steps = await step_rows(run_id)
        by_kind = {s["kind"]: s["status"] for s in steps}
        check(by_kind.get("translate_clip") == "failed",
              "the probe node itself failed", by_kind)
        check(by_kind.get("add_music") == "skipped"
              and by_kind.get("remove_filler") == "skipped",
              "the downstream cascade-skipped", by_kind)

        async with AsyncSessionLocal() as db:
            txns = list(
                (
                    await db.execute(
                        select(CreditTransaction)
                        .where(CreditTransaction.user_id == user_id)
                        .order_by(CreditTransaction.created_at)
                    )
                ).scalars().all()
            )
        kinds = [t.kind for t in txns]
        check("capture" not in kinds,
              "zero capture rows — failed/skipped steps never charge", kinds)
        hold_row = next((t for t in txns if t.kind == "hold"), None)
        release_row = next((t for t in txns if t.kind == "release"), None)
        check(hold_row is not None and hold_row.amount == -hold_amount,
              "the hold landed at birth", hold_row.amount if hold_row else None)
        check(release_row is not None and release_row.amount == hold_amount,
              "the hold releases in full at the terminal state",
              release_row.amount if release_row else None)
        async with AsyncSessionLocal() as db:
            final_balance = int((await db.get(Wallet, user_id)).balance)
        check(final_balance == grant,
              "the wallet is whole again (balance back to the grant)",
              (grant, final_balance))

        # B) capture 幂等（进程内，零 worker 依赖）：重复调用结构性 no-op
        #    （TransientNodeError 复位重跑只记一次的存储侧保证）；成本累加
        #    后的第二 capture（QualityBounce 重跑）只记差额、落 attempt 键，
        #    且 Σ captures ≡ credits(总成本)（与 workflow_steps.cost ×比例
        #    对账的恒等式，不吃取整抖动）。
        async with AsyncSessionLocal() as db:
            run2 = WorkflowRun(
                project_id=uuid.UUID(pid),
                status=WorkflowStatus.COMPLETED,
                context={"target_language": "en"},
            )
            db.add(run2)
            await db.flush()
            step = WorkflowStep(
                run_id=run2.id, kind="write_post", status="done", seq=1, spec={},
                cost={"prompt_tokens": 100_000, "completion_tokens": 50_000},
            )
            db.add(step)
            await db.flush()
            first = await capture_step(db, user_id=user_id, node=step)
            check(first is not None and first.idempotency_key.endswith(":capture"),
                  "the first capture lands at the step key",
                  getattr(first, "idempotency_key", None))
            again = await capture_step(db, user_id=user_id, node=step)
            check(again is None,
                  "a duplicate capture call is a structural no-op", again)
            step.cost = {"prompt_tokens": 200_000, "completion_tokens": 100_000}
            step.attempt = 2
            delta = await capture_step(db, user_id=user_id, node=step)
            check(delta is not None and delta.idempotency_key.endswith(":capture:2"),
                  "the bounce re-run lands at the attempt key",
                  getattr(delta, "idempotency_key", None))
            total_credits = await credits_for_cost(db, cost_usd(step.cost))
            check(abs(int(first.amount)) + abs(int(delta.amount)) == total_credits,
                  "Σ captures ≡ credits(total cost) — the delta reconciles",
                  (first.amount, delta.amount, total_credits))
            await db.commit()
    finally:
        await local.cleanup()
        await local.close()
        async with AsyncSessionLocal() as db:
            await db.execute(
                delete(CreditTransaction).where(CreditTransaction.user_id == user_id)
            )
            await db.execute(delete(Wallet).where(Wallet.user_id == user_id))
            await db.commit()


async def s15_orphan_hold_released_on_project_delete(ctx: Ctx) -> None:
    """积分③ 孤儿 hold 回收（BILLING §8 边界落地）：project 删除先把未结
    hold 按台账动词退回（同事务；RUNNING 除外——在途 worker 的收官路径
    从台账结算）。删除后台账 grant+hold+release 闭合、钱包余额回到赠额。
    与 worker 认领无 racing 依赖：未认领 = 删除路径即退，已认领 = 收官路径
    即退，幂等键保证只退一笔。专用 fixture 用户（钱包动账），FK 序清理。"""
    user_id = await make_user()
    local = Ctx(user_id, keep=False)
    hold_amount = 77
    try:
        pid = await local.new_project("S15 orphan hold recovery")

        # 造一个 PENDING run + 真 hold——从未执行的 run 被删 = 事故现场
        # 的形状（无任何收官路径会触到它）。
        async with AsyncSessionLocal() as db:
            wallet = await get_or_create_wallet(db, user_id)  # 开户赠额
            grant = int(wallet.balance)
            run = WorkflowRun(
                project_id=uuid.UUID(pid),
                status=WorkflowStatus.PENDING,
                context={"outputs": [{"type": "clip"}], "target_language": "en"},
            )
            db.add(run)
            await db.flush()
            db.add(WorkflowStep(run_id=run.id, kind="translate_clip",
                                status="pending", seq=1, spec={}, estimate=None))
            await hold_run(db, user_id=user_id, run_id=run.id, amount=hold_amount)
            await db.commit()
            run_id = str(run.id)

        res = await local.client.delete(f"/projects/{pid}")
        check(res.status_code == 204, "project delete succeeds", res.text)

        # 等 release 落定（删除路径同步落；在途路径由 worker 收官落——
        # 两种路径幂等键相斥，只落一笔）。
        rows: list = []
        for _ in range(60):
            async with AsyncSessionLocal() as db:
                rows = (
                    await db.execute(
                        select(CreditTransaction).where(
                            CreditTransaction.user_id == user_id,
                            CreditTransaction.ref["run_id"].astext == run_id,
                        ).order_by(CreditTransaction.created_at,
                                   CreditTransaction.id)
                    )
                ).scalars().all()
            if any(r.kind == "release" for r in rows):
                break
            await asyncio.sleep(1)
        kinds = [r.kind for r in rows]
        check("release" in kinds,
              "the deleted run's hold settles (delete path or terminal path)",
              kinds)
        check(kinds == ["hold", "release"],
              "the run's ledger closes hold + release — no capture, no drift"
              " (grant row carries no run ref, by design)",
              kinds)
        hold = next(r for r in rows if r.kind == "hold")
        rel = next(r for r in rows if r.kind == "release")
        check(int(hold.amount) == -hold_amount and int(rel.amount) == hold_amount,
              "the hold returns whole — nothing executed",
              [(r.kind, int(r.amount)) for r in rows])
        check(int(rel.balance_after) == grant,
              "wallet is back at the grant", int(rel.balance_after))
    finally:
        await local.cleanup()
        await local.close()
        async with AsyncSessionLocal() as db:
            await db.execute(
                delete(CreditTransaction).where(CreditTransaction.user_id == user_id)
            )
            await db.execute(delete(Wallet).where(Wallet.user_id == user_id))
            await db.commit()


# ---- S16 remix 旗舰旅程（旅程二，R1 B1 T5） --------------------------------------

# 固定 fixture（demo 桶常住对象，reset_db 保护前缀）：
# - 用户素材 = 真演讲片（worker 真 ASR → 真剪辑）；
# - 参考片 = 特征明显的高光剪辑成品（实测 craft_scan: 9:16 / 2 shots / steady /
#   clean-bottom 青色 #22D3EE 字幕）——断言全部自洽读骨架行，不硬编码事实。
REMIX_SOURCE_KEY = "demo/uploads/demo_talk.mp4"
REMIX_EXEMPLAR_KEY = "demo/outputs/highlight-clips-preview-ec8e575b.mp4"


async def copy_fixture(key: str, dest_prefix: str) -> str:
    """Copy a shared demo-bucket fixture to a scenario-owned key. NEVER seed
    an asset pointing at the shared object directly: project deletion unlinks
    every asset's ``file_url`` (``delete_project`` → ``delete_file``), so a
    shared key referenced by a scenario project dies with its cleanup — S16's
    first run ate a recipe card's marketing video this way. (Script seam:
    scripts reach into app internals throughout this file.)"""
    from app.config import settings
    from app.providers.storage import _get_s3_client

    dest = f"{dest_prefix}/{key.rsplit('/', 1)[-1]}"
    client = _get_s3_client()
    await asyncio.to_thread(
        client.copy_object,
        Bucket=settings.s3_bucket_name,
        Key=dest,
        CopySource={"Bucket": settings.s3_bucket_name, "Key": key},
    )
    return dest


async def s16_remix_flagship_journey(ctx: Ctx) -> None:
    """remix 旗舰（旅程二零自动化验收的收口，需 dev worker + demo 桶 fixture）：
    P1 warm 路径——@mention 指认参考片（拍 0a 免问路，pin 由代码结算）→ pin 落
    定即拆解，agent 主动说看懂了案例（零 run 成本）；P2 run 路径——两视频 +
    一句「做成案例那样子」→ mention pin → plan → start → decompile 新鲜物化
    （参考片 seeded 为 FAILED 处理态 = warm 永不点火的现实形态，如参考片自身
    ASR 失败——run 路径不看处理态只读字节，T4 的火因此必走 run 座位）→ 触发
    回合说话 → 产物参数 = 骨架（条数/画幅/字幕色三断）→ 画布无 decompile 孤儿
    节点。角色提问机器一路（router 主动问 asset_role）是 LLM 裁量，不做 e2e
    锁定（登记 INTENT_COVERAGE §6 ⚠️ 行；其代码侧——选项构造 / 答复落 pin /
    默认路径——由纯测试锁定）。复用不重复发声由结构锁住（reuse 早退在火前
    60 行）+ (conversation, trigger, ref) 去重（test_trigger_turn_pure），本
    剧本末尾断言消息恰一条。"""
    fixture_prefix = f"scenario/s16-{uuid.uuid4().hex[:8]}"
    src_key = await copy_fixture(REMIX_SOURCE_KEY, fixture_prefix)
    ex_key = await copy_fixture(REMIX_EXEMPLAR_KEY, fixture_prefix)
    # ---- P1: warm 路径 —— pin 落定即拆解、主动说话（无 run） ------------------
    # 消歧走 @mention 指认（拍 0a 第二路「免问」）：角色 pin 由代码结算（判词
    # ④），不依赖 LLM 是否选择提问——提问机器一路的 dock 决策是 LLM 裁量
    # （两次实测路由在旗舰句上直接出默认 plan，miss 率归 prompt 探针测量，
    # 登记 INTENT_COVERAGE §6 ⚠️ 行），e2e 只锁确定性路径。
    pid1 = await ctx.new_project("S16-P1 warm path")
    src1 = await seed_asset(
        pid1, ctx.user_id, AssetType.VIDEO, "s16-p1-source.mp4", processed=True
    )
    ex1 = await seed_asset(
        pid1,
        ctx.user_id,
        AssetType.VIDEO,
        "highlight-clips-preview.mp4",
        processed=True,
        file_url=ex_key,
    )
    turn1 = await ctx.chat(
        pid1,
        "你能帮我把我的原视频做成 @参考案例 那样子吗？",
        mentions=[{"type": "asset", "id": ex1, "label": "highlight-clips-preview.mp4"}],
    )
    conv1 = turn1["conversation_id"]
    brief1 = (await ctx.results(pid1)).get("pending_brief") or {}
    # The pin persists on the first PendingPlan WRITE — a bare-answer turn
    # (the router freeform-asks instead of calling a tool) writes nothing
    # and the pin evaporates with it. Re-mention on each continuation until
    # a write lands (bounded — three prose-only turns = stuck, fail loud).
    for _ in range(3):
        if brief1.get("exemplar_asset_id") == ex1:
            break
        turn1 = await ctx.chat(
            pid1,
            "参考案例就是 @这条，继续。",
            mentions=[{"type": "asset", "id": ex1, "label": "highlight-clips-preview.mp4"}],
        )
        brief1 = (await ctx.results(pid1)).get("pending_brief") or {}
    check(brief1.get("exemplar_asset_id") == ex1,
          "the @mention pins the exemplar by code (拍 0a 免问路 — 判词④)",
          {"brief": brief1,
           "last_content": (turn1["assistant_message"].get("content") or "")[:200]})
    # pin 落定（随 PendingPlan 写入）→ warm 拆解（fire-and-forget）→ 触发回合
    # 主动说话（拍 1）。
    review1 = await wait_trigger_review(ctx, conv1, ex1, timeout=240.0)
    check(review1 is not None,
          "the warm path's decompile speaks (拍 1 — 「我看了你的案例」)", ex1)
    rintent1 = (review1 or {}).get("intent") or {}
    check(rintent1.get("trigger") == "craft_decompiled" and rintent1.get("ref") == ex1,
          "the warm review dump names trigger + exemplar ref", rintent1)
    check(bool(((review1 or {}).get("content") or "").strip()),
          "the agent's case understanding is spoken, not silent", review1)

    # ---- P2: run 路径 —— 新鲜物化必发声（T4）+ exemplar 参数 + 画布孤儿修复 ----
    pid2 = await ctx.new_project("S16-P2 run path")
    src2 = await seed_asset(
        pid2, ctx.user_id, AssetType.VIDEO, "demo_talk.mp4",
        file_url=src_key,  # PENDING — the worker really ASRs it
    )
    ex2 = await seed_asset(
        pid2, ctx.user_id, AssetType.VIDEO, "highlight-clips-preview.mp4",
        file_url=ex_key,
        status=AssetStatus.FAILED,  # warm 永不点火 → run 路径新鲜物化（T4 的火）
    )
    src_status = await wait_asset_status(
        src2, {AssetStatus.COMPLETED, AssetStatus.FAILED}
    )
    check(src_status == AssetStatus.COMPLETED,
          "the real source asset is ASR-processed by the dev worker", src_status)
    # remix = 全模态真链（decompile + clips + render pending），赠额外补足避免
    # 422 噪音（S13/S14 的余额断言都按当前值动态读，互不影响）。
    async with AsyncSessionLocal() as db:
        wallet = await get_or_create_wallet(db, ctx.user_id)
        wallet.balance = int(wallet.balance) + 200000
        await db.commit()

    turn2 = await ctx.chat(
        pid2,
        "你能帮我把我的原视频做成 @参考案例 那样子吗？",
        mentions=[{"type": "asset", "id": ex2, "label": "highlight-clips-preview.mp4"}],
    )
    conv2 = turn2["conversation_id"]
    brief2 = (await ctx.results(pid2)).get("pending_brief") or {}
    # Same bounded re-mention recovery as P1: the pin only lands with the
    # first PendingPlan write.
    for _ in range(3):
        if brief2.get("exemplar_asset_id") == ex2:
            break
        turn2 = await ctx.chat(
            pid2,
            "参考案例就是 @这条，继续。",
            mentions=[{"type": "asset", "id": ex2, "label": "highlight-clips-preview.mp4"}],
        )
        brief2 = (await ctx.results(pid2)).get("pending_brief") or {}
    check(brief2.get("exemplar_asset_id") == ex2,
          "P2's @mention pins the exemplar by code",
          {"brief": brief2, "terminal": terminal_tool_of(turn2),
           "run_id": turn2.get("run_id"),
           "question": (turn2["assistant_message"].get("question") or {}),
           "content_head": (turn2["assistant_message"].get("content") or "")[:200]})

    # 计划 dock：mention 回合可能直接出书；若路由仍 dock 了角色问（mention 的
    # pin 已随写入落账，问题只是再确认），按选项答掉它（答复同样代码落 pin），
    # 再回推到出书。
    follow = turn2["assistant_message"]
    q2 = follow.get("question") or {}
    if q2.get("kind") == "question" and q2.get("slot") == "asset_role":
        ans2 = await ctx.answer(follow["id"], {"kind": "option", "option_id": src2})
        check(ans2.status_code in (200, 201), "P2's role answer settles", ans2.text)
        follow = ans2.json().get("follow_up") or {}
    if not is_plan_dock(follow):
        # 显式覆盖：骨架缺席不该阻塞出书（读工具已被告知 FAILED = 直接出方案，
        # 此话术兜底 agent 仍犹豫的残差）。
        turn_dock = await ctx.chat(
            pid2, "参考片的骨架暂时拿不到也没关系——按你的判断直接出方案，不用等它。"
        )
        follow = turn_dock["assistant_message"]
    check(is_plan_dock(follow), "the pinned plan docks", follow)
    tasks = plan_tasks((await ctx.results(pid2)).get("pending_brief"))
    if not any(t.get("tool") == "select_clips" for t in tasks):
        # LLM 路由方差的一次纠偏——旗舰旅程的合法产物就是 clips 链。
        await ctx.chat(pid2, "把原视频剪成案例那样的竖屏短片")
        tasks = plan_tasks((await ctx.results(pid2)).get("pending_brief"))
    check(any(t.get("tool") == "select_clips" for t in tasks),
          "the remix plan carries the clips chain (旗舰旅程的合法链)", tasks)
    draft_graph = await ctx.graph(pid2)
    check(no_decompile_canvas_node(draft_graph),
          "the draft graph carries NO decompile orphan node (T3)", draft_graph["nodes"])

    turn3 = await ctx.chat(pid2, "looks good, start")
    check(terminal_tool_of(turn3) == "start_run",
          "the prose confirmation closes on start_run", turn3)
    run_id = turn3["run_id"]
    check(run_id is not None, "the remix run is born", turn3)
    run_ctx = (await run_row(run_id))["context"]
    check(run_ctx.get("exemplar_asset_id") == ex2,
          "the exemplar pin rides run.context into the run (判词④) — source stays "
          "None on the mention path (两视频项目素材由 exemplar 排除法确定性解析)",
          run_ctx)

    # decompile 步骤新鲜物化（参考片 FAILED → warm 从未点火 → 非复用）。
    dec_step = await wait_step_terminal(run_id, "decompile", timeout=420.0)
    check(dec_step["status"] == "done",
          "the decompile step completes on the real exemplar bytes", dec_step)
    dec_summary = str((dec_step["spec"] or {}).get("summary") or "")
    check("复用" not in dec_summary and "Reused" not in dec_summary,
          "the run path materializes FRESH (no warm row existed)", dec_summary)
    # 骨架行：run 路径所物化（warmed=False, source_ref 指认参考片）。
    skeletons = [
        o for o in await outputs_of(pid2, "craft_skeleton")
        if (o.source_ref or {}).get("asset_id") == ex2
    ]
    check(len(skeletons) == 1, "exactly one skeleton row names the exemplar",
          [o.source_ref for o in skeletons])
    check((skeletons[0].source_ref or {}).get("warmed") is False,
          "the skeleton is the RUN path's materialization, not the warm's",
          skeletons[0].source_ref)
    skel = skeletons[0].payload

    # T4: run 路径拆解 → 触发回合说话（与 warm 同权）；恰一条（复用不重复发声
    # 的结构锁 + 去重在本项目内同 ref 恒一条）。
    review2 = await wait_trigger_review(ctx, conv2, ex2, timeout=240.0)
    check(review2 is not None,
          "the RUN path's fresh decompile speaks (T4 — 与 warm 同权)", ex2)
    rintent2 = (review2 or {}).get("intent") or {}
    check(rintent2.get("trigger") == "craft_decompiled",
          "the run-path review dump names the craft trigger", rintent2)
    craft_msgs = [
        m for m in await ctx.messages(conv2)
        if (m.get("intent") or {}).get("type") == "trigger_review"
        and (m.get("intent") or {}).get("ref") == ex2
    ]
    check(len(craft_msgs) == 1,
          "exactly one craft speech per (conversation, exemplar) — no double-speak",
          len(craft_msgs))

    # 产物落库 + exemplar 参数断言（自洽读骨架行，ADR-078 判词⑤ code-mapped）：
    # 画幅 / 字幕色 = 代码映射（确定性，严等）；条数 = clamp(骨架 shots) 是 CAP
    # 不是产量——实现条数是 agent 的内容判断（119s 原片挑 1 条高光合法），断言
    # 只锁「不超帽 + 至少一条」。
    clips_step = await wait_step_terminal(run_id, "select_clips", timeout=600.0)
    check(clips_step["status"] == "done",
          "the clips step completes on the real source", clips_step)
    clips = [
        o for o in await outputs_of(pid2, "clip")
        if str(o.workflow_step_id) == clips_step["id"]
    ]
    expected_cap = max(1, min(10, int(skel["rhythm"]["shot_count"])))
    check(1 <= len(clips) <= expected_cap,
          "clip count respects the skeleton-derived cap (count_default=1 without it)",
          (len(clips), expected_cap, (clips_step["spec"] or {}).get("slot")))
    specs = [o.render_spec or {} for o in clips]
    check(all(s.get("aspect") == skel["aspect"] for s in specs),
          "every clip's aspect = the skeleton's measured aspect",
          [s.get("aspect") for s in specs])
    if (skel.get("captions") or {}).get("present") and skel["captions"].get("color"):
        check(all((s.get("brand") or {}).get("caption_color") == skel["captions"]["color"]
                  for s in specs),
              "every clip's caption color = the skeleton's palette-snapped color",
              [(s.get("brand") or {}).get("caption_color") for s in specs])

    # T3 终态：run 图无 decompile 孤儿节点；decompile 步骤骑 task book 内部族。
    filled_graph = await ctx.graph(pid2)
    check(no_decompile_canvas_node(filled_graph),
          "the run-filled graph carries NO decompile orphan node (T3)",
          filled_graph["nodes"])
    book_steps = await task_book_step_ids(pid2)
    check(dec_step["id"] in book_steps,
          "the decompile step rides the task book's internal family (prelude 折叠)",
          (dec_step["id"], book_steps))


async def s17_run_authority_park_and_handoff(ctx: Ctx) -> None:
    """核⑰ run 执行权仲裁（R1 B3，J6 多轮一致性；I-EXEC-03/04）：
    a) 答旧问——B 活跃时 A 被答 → 仲裁 blocked → 明示回执（再挂+明示）+
       A 保持 parked（节点/运行零状态污染）+ 全程单 owner；B 收官 → 交接钩
       续跑 A → A 完成、B 行零损失。
    b) 过期路——expire 结算默认答案但 authority 被占 → answered-but-parked，
       不再制造双 RUNNING；sweep 重试分支不重复结算/计数；B 收官 → A 续跑
       完成。"""

    # a) 回答路径：blocked → 明示 → B 收官 → 交接钩续跑。
    pid = await ctx.new_project("S17a answer blocked then handoff")
    ck = await seed_parked_interrupt(pid, ctx.user_id)
    b_run = await seed_active_run(pid)
    res = await ctx.answer(ck["question_id"], {"kind": "option", "option_id": "a"})
    check(res.status_code == 200, "the answer lands", res.text)
    follow = res.json().get("follow_up")
    check(
        follow is not None and "current generation" in (follow.get("content") or ""),
        "the blocked arbitration speaks the honest parked line (再挂+明示)",
        follow,
    )
    answered = res.json()["answered_question"]
    check(
        (answered.get("answer") or {}).get("text") == "Focus: Pricing",
        "the answer is settled on the message row even while parked",
        answered.get("answer"),
    )
    a_run = await run_row(ck["run_id"])
    check(a_run["status"] == "waiting_human", "A stays WAITING_HUMAN (再挂)", a_run)
    a_node = (await step_rows(ck["run_id"]))[0]
    check(
        a_node["status"] == "waiting" and "answer" not in a_node["spec"],
        "the blocked park writes ZERO node state (no spec.answer)",
        a_node,
    )
    check(
        await count_active_runs(pid) == 1,
        "I-EXEC-03: answering the old question never births a second owner",
    )
    await settle_seeded_run(b_run)
    b_after = await run_row(b_run)
    check(b_after["status"] == "completed", "B settles completed, rows untouched", b_after)
    await wait_run_status(ck["run_id"], {"completed"})
    check(
        await count_active_runs(pid) == 0,
        "the handoff resumed A only after B settled — authority serialized",
    )
    await ctx.cleanup()

    # b) 过期路径：expire = 结算 + 尝试重获执行权；被占 = answered-but-parked。
    pid = await ctx.new_project("S17b expire blocked then handoff")
    ck = await seed_parked_interrupt(pid, ctx.user_id)
    b_run = await seed_active_run(pid)
    expired = await expire_stale_interrupts(timedelta(0))
    check(expired == 1, "the sweep settles the default answer", expired)
    msg = await message_row(ck["question_id"])
    check(
        (msg["answer"] or {}).get("text") == "expired",
        "the default answer settled with the machine marker",
        msg["answer"],
    )
    a_node = (await step_rows(ck["run_id"]))[0]
    check(
        a_node["status"] == "waiting" and "answer" not in a_node["spec"],
        "expire under a held authority parks answered-but-blocked",
        a_node,
    )
    check(
        await count_active_runs(pid) == 1,
        "I-EXEC-03: expire never manufactures a double RUNNING",
    )
    again = await expire_stale_interrupts(timedelta(0))
    check(again == 0, "the settled park is never re-expired (retry branch)", again)
    check(
        await count_active_runs(pid) == 1,
        "the sweep retry keeps the single owner",
    )
    await settle_seeded_run(b_run)
    await wait_run_status(ck["run_id"], {"completed"})
    await ctx.cleanup()


async def s18_idless_asset_read_terminalizes(ctx: Ctx) -> None:
    """交互完整性批 (2026-09-17) 事故场景回归：单视频 pre-ASR（PENDING、
    meta 无 language）+ 原事故文案 —— 模型想「先看源语言」时 get_asset 的
    无 id 调用必须成功（工具自证 provenance：prompt 面从不列 asset id，
    必填 id 曾逼模型编造 → schema 拒绝 → 静默 repair 窗）。回合必须收敛
    到计划 dock，永不落入 exhausted 的 cannot-do 降级。锁终态形态
    （task_book / 提问），不锁 LLM 言语（禁令 #7）。"""
    pid = await ctx.new_project("S18 idless asset read")
    await seed_asset(
        pid,
        ctx.user_id,
        AssetType.VIDEO,
        "talk.mp4",
        extracted_text="So a company from Oxford University introduced "
        "some of his new initiative.",
        # PENDING + no meta.language — the incident's pre-ASR window: the
        # plan surface shows the filename with no detected language.
    )
    turn1 = await ctx.chat(
        pid,
        "Caption my video in Chinese and French — Chinese as bilingual "
        "subtitles.",
    )
    turn1 = await answer_caption_gate(ctx, turn1)
    terminal = terminal_tool_of(turn1)
    check(
        terminal in ("present_plan", "ask_user"),
        "the pre-ASR caption turn terminalizes as a plan dock or an honest "
        "question — never the exhaustion degrade",
        terminal,
    )
    check(
        has_prose(turn1["assistant_message"]),
        "the terminal message carries the settled speech",
        turn1["assistant_message"],
    )
    if terminal == "present_plan":
        plan = await pending_plan(ctx, pid)
        check(
            len(plan_tasks(plan)) >= 1,
            "the docked chain has at least one task",
            plan,
        )


async def s19_turn_durability_and_trigger_admission(ctx: Ctx) -> None:
    """交互完整性批 A+B (2026-09-17) 回归：用户消息从回合第一拍即可持久
    （turn_state: in_flight → settled 随回合提交盖章），trigger 准入门永不
    超越在途用户回合 —— 回合进行中 in-process 直接点火 run_trigger_turn，
    review 必须落在用户回合收敛之后。2026-09-16 事故原样：commit-once
    回合死亡吞掉用户消息 + understanding_warmed 撞进在途回合盲说。"""
    from app.chat.trigger_turn import TRIGGER_UNDERSTANDING, run_trigger_turn

    pid = await ctx.new_project("S19 turn durability + admission")
    await seed_asset(
        pid,
        ctx.user_id,
        AssetType.VIDEO,
        "talk.mp4",
        extracted_text="So a company from Oxford University.",
        processed=True,
        meta={"language": "en"},
    )
    chat_task = asyncio.create_task(
        ctx.chat(
            pid,
            "Caption my video in Chinese and French — Chinese as bilingual "
            "subtitles.",
        )
    )
    # A) 用户行随回合第一拍持久，且持有 in-flight 标记（轮询等它出现——
    #    prepare 的前置提交在 LLM 调用之前，几秒内必现）。
    user_row: dict | None = None
    for _ in range(30):
        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    select(Message)
                    .join(Conversation, Message.conversation_id == Conversation.id)
                    .where(
                        Conversation.project_id == uuid.UUID(pid),
                        Message.role == "user",
                    )
                    .order_by(Message.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if row is not None:
                user_row = {
                    "id": str(row.id),
                    "turn_state": row.turn_state,
                    "content": row.content,
                }
                break
        await asyncio.sleep(1)
    check(user_row is not None, "the user row is durable from the first beat")
    check(
        user_row["turn_state"] == "in_flight",
        "the durable row owns the in-flight marker while the turn runs",
        user_row,
    )
    check(
        "Caption my video" in (user_row["content"] or ""),
        "the durable row carries the user's actual words",
        user_row,
    )
    # B) 在途点火：准入门必须 defer（纯决策由 test_trigger_turn_pure 锁；
    #    这里锁端到端秩序——review 落在用户回合收敛之后）。
    trigger_task = asyncio.create_task(
        run_trigger_turn(uuid.UUID(pid), TRIGGER_UNDERSTANDING, "s19-digest")
    )
    turn1 = await chat_task
    turn1 = await answer_caption_gate(ctx, turn1)
    check(
        terminal_tool_of(turn1) in ("present_plan", "ask_user"),
        "the user turn converges normally under the racing trigger",
        terminal_tool_of(turn1),
    )
    async with AsyncSessionLocal() as db:
        settled = await db.get(Message, uuid.UUID(user_row["id"]))
        check(
            settled is not None and settled.turn_state == "settled",
            "the turn's commit stamps the user row settled",
            settled.turn_state if settled is not None else None,
        )
    review = await trigger_task  # 5 分钟礼貌窗 >> 正常回合时长——必发言
    check(review is not None, "the deferred review eventually speaks")
    async with AsyncSessionLocal() as db:
        rows = list(
            (
                await db.execute(
                    select(Message)
                    .join(Conversation, Message.conversation_id == Conversation.id)
                    .where(Conversation.project_id == uuid.UUID(pid))
                    .order_by(Message.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
    review_row = next(r for r in rows if str(r.id) == str(review.id))
    assistants_before = [
        r for r in rows if r.role == "assistant" and r.created_at < review_row.created_at
    ]
    check(
        len(assistants_before) >= 1,
        "the review lands AFTER the user turn's reply — never mid-turn "
        "(the 2026-09-16 blind-speech race)",
        [(r.role, r.created_at.isoformat()) for r in rows],
    )


SCENARIOS = {
    "S1": s1_bare_wish_full_journey,
    "S2": s2_skipped_topic_ask_drafts_from_persona,
    "S3": s3_interjection_keeps_pending,
    "S4": s4_material_chain_and_estimate_foundation,
    "S5": s5_revision_chat_always_wins,
    "S6": s6_interrupt_consolidated,
    "S7": s7_caption_mode_gate,
    "S8": s8_research_grounds_writer,
    "S9": s9_consult_never_books,
    "S10": s10_sse_turn_streaming,
    "S11": s11_whole_source_and_materialize_matrix,
    "S12": s12_merge_brief_source_matrix,
    "S13": s13_credits_insufficient_birthplace_422,
    "S14": s14_failed_run_zero_capture_full_release,
    "S15": s15_orphan_hold_released_on_project_delete,
    "S16": s16_remix_flagship_journey,
    "S17": s17_run_authority_park_and_handoff,
    "S18": s18_idless_asset_read_terminalizes,
    "S19": s19_turn_durability_and_trigger_admission,
}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", help="comma-separated scenario ids (e.g. S1,S5)")
    parser.add_argument("--keep", action="store_true", help="keep scenario projects")
    args = parser.parse_args()

    only = {s.strip() for s in args.only.split(",")} if args.only else None
    selected = [(k, fn) for k, fn in SCENARIOS.items() if only is None or k in only]
    if not selected:
        print(f"No scenarios matched --only {args.only!r} (have: {', '.join(SCENARIOS)})")
        return 2

    print(f"API: {BASE} — {len(selected)} scenario(s)\n")
    user_id = await make_user()
    ctx = Ctx(user_id, keep=args.keep)

    failures: dict[str, str] = {}
    try:
        for name, fn in selected:
            print(f"▶ {name} {fn.__doc__.strip() if fn.__doc__ else ''}")
            try:
                await fn(ctx)
            except ScenarioFailure as exc:
                failures[name] = str(exc)
                print(f"  ✘ FAIL {exc}\n")
            except Exception as exc:  # server 5xx, LLM timeout, …
                failures[name] = f"{type(exc).__name__}: {exc}"
                print(f"  ✘ ERROR {type(exc).__name__}: {exc}\n")
            else:
                print("  ✓ PASS\n")
            await ctx.cleanup()
    finally:
        await ctx.close()

    print("=" * 60)
    if failures:
        print(f"{len(selected) - len(failures)}/{len(selected)} passed. Failures:")
        for name, why in failures.items():
            print(f"  {name}: {why}")
        return 1
    print(f"All {len(selected)} scenario(s) passed.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
