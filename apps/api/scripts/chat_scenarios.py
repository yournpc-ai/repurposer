"""chat_scenarios.py — 剧本测试：预设多轮剧本对活 API 跑形态级断言。

不是 harness（harness 单义 = 调用面 Agent 漏斗，NAMING N-48），也不是"测试
套件"（scripts/ 下的剧本测试脚本，不配概念名——去方言批禁令）。剧本驱动
活 API 的唯一意图表面（``POST /chat`` + answer 端点），断言形态级结果——
提案态 / dock 态 / run 数 / 落库行 / SSE 帧序——永不锁 LLM 文案（禁令 #7）。
例外：代码强制文本（提醒尾 / 机器标记 / 确定性回执）可以锁——那是代码，
不是 LLM。

2026-09-04 大浓缩（C4，简报 ``docs/tasks/de-dialect-question-machine.md``）：
52 本机制碎片（旧 S1–S53，S22 空）浓缩为 **12 条核心用户 story**，编号连续
重排（本次不再沿用留空洞先例——旧 S 号与现行 S 号无一对应，映射见简报
§C4 与 ``docs/INTENT_COVERAGE.md`` §6）。每条 = 一个完整用户故事，不是
机制碎片；进程内纯函数断言（估价 / repair / 编译矩阵 / merge 矩阵）按简报
「保留并入」随链收编——零 LLM 零方差，是最便宜的覆盖。

    S1  核① 裸愿望全旅程：主题问 → 作答（自由文本 slot 握手 + 选项点选两路）
             → 评审卡 → start → run（途中锁待决重建 / 一行一答 409 / 选项点选
             不 500 三张契约拍）
    S2  核② 跳过提问 → draft-from-persona 书 + 默认路径声明
    S3  核③ 插话：正常回答 + 代码拼装提醒尾 + 保持 pending → 下轮作答回填
    S4  核④ 素材全链（run completed + 产物落库）+ 估价三断言 + repair 只一轮
    S5  核⑤ 修订链：手改存活 / chat 恒胜 / supersede 标记 / task_book 不打字母
    S6  核⑥ interrupt 一条：三答法 + 空白不答 + bail 级联 + 插话后续跑
    S7  核⑦ caption mode：选项问 → 回执 + run.context + refine 存活
    S8  核⑧ research 全链（活 DDG，网络全灭时 caveat 降级也算过）
    S9  核⑨ 问事不出书：能力问 / 闲聊纯 answer，无书 start 不死路不起 run
    S10 SSE 流式：delta 拼接 == 信封散文（唯一 transport 座）
    S11 整条源规则（整条视频字幕活链）+ materialize 注入矩阵（进程内）
    S12 merge_brief 来源矩阵（进程内纯函数）

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
from datetime import UTC, datetime
from pathlib import Path

# Make ``app`` importable when run as a file (apps/api on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from app.agents.base import Agent, StreamingAgent  # noqa: E402
from app.providers.llm.minimax import MiniMaxError, MiniMaxSchemaError  # noqa: E402
from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.schemas import MediaInput, TaskItem  # noqa: E402
from app.pipeline.graph import NODE_KINDS, fold_estimates  # noqa: E402
from app.pipeline.orchestrator import (  # noqa: E402
    TaskSpec,
    assert_runners_registered,
    compile_graph,
)
from app.models.tables import (  # noqa: E402
    Asset,
    Conversation,
    Message,
    Operation,
    Output,
    Project,
    User,
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

BASE = os.getenv("SCENARIO_API_BASE", "http://127.0.0.1:8000/api/v1")
TIMEOUT = httpx.Timeout(180.0)  # book-path turns are real LLM calls


class ScenarioFailure(AssertionError):
    pass


def check(condition: bool, label: str, detail: object = "") -> None:
    if not condition:
        raise ScenarioFailure(f"{label}" + (f" — {detail}" if detail else ""))


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

    async def chat_stream(
        self, pid: str, message: str, **extra: object
    ) -> tuple[list[str], dict | None, dict | None]:
        """One SSE chat turn (Accept: text/event-stream). Returns the ordered
        prose deltas, the turn.completed envelope, and turn.failed if any."""
        deltas: list[str] = []
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
                    elif event == "turn.completed":
                        completed = payload
                    elif event == "turn.failed":
                        failed = payload
        return deltas, completed, failed

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
) -> None:
    """A fake file-backed asset row — enough for the clips-media gate and the
    intent router's filename context; the bytes never exist. ``extracted_text``
    satisfies the "transcript" required-input check (registry requires).
    ``meta`` carries e.g. the ASR-detected ``language`` the plan context
    surfaces for transform-target decisions. ``processed`` stamps the row
    COMPLETED (the declared-material promotion's end state) — the worker's
    asset queue then never touches the fake bytes (S4's writer chain)."""
    async with AsyncSessionLocal() as db:
        db.add(
            Asset(
                user_id=user_id,
                project_id=uuid.UUID(pid),
                type=type_,
                file_url=f"scenario/{filename}",
                title=filename,
                extracted_text=extracted_text,
                meta=meta,
                processing_status=(
                    AssetStatus.COMPLETED if processed else AssetStatus.PENDING
                ),
            )
        )
        await db.commit()


async def seed_completed_run(pid: str) -> None:
    """A settled run row — the book path must never claim a project that has
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


def is_task_book_dock(msg: dict) -> bool:
    return bool(msg.get("question")) and msg["question"].get("kind") == "task_book" and not msg.get("answer")


async def answer_caption_gate(ctx: Ctx, turn1: dict) -> dict:
    """The caption gate (S1 precedent): a chain carrying write_quotes docks
    the caption_mode options question BEFORE the task book. When turn1 docked
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


def book_tasks(book: dict) -> list[dict]:
    """The docked chain (ADR-043): pending_brief.intent.tasks — the plan
    card's rows, one {tool, params} dict per task."""
    return ((book or {}).get("intent") or {}).get("tasks") or []


def task_params(task: dict) -> dict:
    return task.get("params") or {}


async def pending_book(ctx: Ctx, pid: str) -> dict | None:
    """The project's pending task book via the results endpoint (None when none)."""
    return (await ctx.results(pid)).get("pending_brief")


def has_reminder_tail(content: str) -> bool:
    """The code-composed interjection reminder tail (ADR-053 R2 — code-forced
    text, so locking its marker is legal: it is code, never the LLM's voice)."""
    return "Still waiting for your answer:" in content or "还在等你的回答：" in content


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
    q1 = msg1.get("question") or {}
    check(q1.get("kind") == "question" and q1.get("slot") == "topic",
          "the rootless wish docks the topic ask first (never an empty book)", msg1)
    check(bool((q1.get("default_path") or "").strip()),
          "the default path rides as the schema tooth (策略③)", q1)
    options = q1.get("options") or []
    check(len(options) == 0 or 2 <= len(options) <= 3,
          "options: 3 one-word picks (2 only for a genuinely binary choice), "
          "or empty when the persona pantry is empty (C2)",
          options)
    book1 = await pending_book(ctx, pid)
    check(book1 is None or book1.get("intent") is None,
          "no task book parks on an ask turn (ledger-only row or none)", book1)

    # 契约拍①：待决重建零内存态（旧 S26 并入）。
    res = await ctx.conversation(pid)
    check((res.json().get("pending_question") or {}).get("id") == msg1["id"],
          "the pending question rebuilds (the refresh / cross-device seat)",
          res.json())

    # 自由文本作答 —— slot 握手判定结算（ADR-053 R2 book path：router 在
    # pending 块上下文里把槽位值提案 user-stated，代码结算 freeform 并回填）。
    turn2 = await ctx.chat(pid, "Make it about the EU AI Act for researchers.")
    aq = turn2.get("answered_question")
    check(aq is not None and aq["id"] == msg1["id"],
          "the free-text answer settles the pending ask (judged — code settles)",
          turn2)
    check((aq.get("answer") or {}).get("kind") == "freeform",
          "the judged settlement lands kind=freeform (the user's own words)",
          aq.get("answer"))
    brief = ((await pending_book(ctx, pid)) or {}).get("brief") or {}
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
    # 的是 label 不是 id）+ book path 接续带 follow_up。
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
        brief2 = ((await pending_book(ctx, pid2)) or {}).get("brief") or {}
        topic2 = brief2.get("topic") or {}
        check(topic2.get("source") == "user-stated"
              and topic2.get("value") == opts[0]["label"],
              "the option pick backfills the slot with the LABEL (not the id)",
              topic2)
        check(body.get("follow_up") is not None,
              "the book path resumes with a follow-up", body)
    else:
        check(True, "option-pick beat skipped (pantry empty — C2 exempt)", q1b)

    # 评审卡：作答轮直接出书，或（answer 裁决时）推一轮——终点断言不变：
    # task_book dock 且 merged brief 钢印进 payload（预填评审卡 B3）。
    msg2 = turn2["assistant_message"]
    if not is_task_book_dock(msg2):
        turn2b = await ctx.chat(pid, "go ahead")
        msg2 = turn2b["assistant_message"]
    check(is_task_book_dock(msg2),
          "the enriched ledger docks the task book (root now exists)", msg2)
    ftopic = ((msg2.get("question") or {}).get("brief") or {}).get("topic") or {}
    check(ftopic.get("source") == "user-stated" and bool(ftopic.get("value")),
          "the review card stamps the merged brief into the payload", ftopic)

    # 散文确认 start → run 起步（G-1）。
    turn3 = await ctx.chat(pid, "looks good, start")
    check(turn3["run_id"] is not None, "prose confirmation starts the run", turn3)
    check(turn3["answered_question"] is not None, "the book settles on start", turn3)
    check((await ctx.results(pid)).get("pending_brief") is None,
          "pending_brief cleared on start")


# ---- S2 核② 跳过 → draft-from-persona ------------------------------------------


async def s2_skipped_topic_ask_drafts_from_persona(ctx: Ctx) -> None:
    """核② 问完一轮仍无根 → draft-from-persona 书（ADR-052 B2 D2-C2，验收③）：
    裸愿望 → 主题问 → × 跳过（bail）→ 默认路径生效——出书门槛 dock
    draft-from-persona 书（reason + 散文含默认路径声明），asked 簿记挡住
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
    check(is_task_book_dock(follow),
          "skipping takes the default path — a task book docks", follow)
    check(ans.json().get("answered_question") is not None,
          "the skipped ask settles as answered", ans.json())

    book = await pending_book(ctx, pid)
    check(book is not None, "the draft-from-persona book persists", book)
    reasons = (book or {}).get("reasons") or []
    check("draft_from_persona" in reasons,
          "the draft-from-persona reason rides the docked book", reasons)
    asked = ((book or {}).get("brief") or {}).get("asked") or []
    check("topic" in asked,
          "the asked roll records the topic ask (the loop is bounded)", asked)
    echo = ((book or {}).get("intent") or {}).get("answer") or ""
    check("persona" in echo.lower() or "人设" in echo,
          "the echo carries the default-path declaration (验收③)", echo)


# ---- S3 核③ 插话支持 -----------------------------------------------------------


async def s3_interjection_keeps_pending(ctx: Ctx) -> None:
    """核③ 插话未答 → 正常回答 + 提醒尾 + 问题保持 pending → 下轮作答回填
    （ADR-053 R2 book path）：主题问待决中插一句与问题无关的能力问——
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
    res = await ctx.conversation(pid)
    check((res.json().get("pending_question") or {}).get("id") == msg1["id"],
          "the ask stays pending through the interjection", res.json())

    # 下轮作答 → slot 握手结算回填（S1 同径）。
    turn3 = await ctx.chat(pid, "Make it about European research policy.")
    aq = turn3.get("answered_question")
    check(aq is not None and aq["id"] == msg1["id"]
          and (aq.get("answer") or {}).get("kind") == "freeform",
          "the next-turn answer settles by the slot handshake", turn3)
    brief = ((await pending_book(ctx, pid)) or {}).get("brief") or {}
    check(((brief.get("topic") or {}).get("source")) == "user-stated",
          "the answer backfills the topic slot user-stated", brief)


# ---- S4 核④ 素材全链 + 估价地基（进程内自检并入） ---------------------------------


async def s4_material_chain_and_estimate_foundation(ctx: Ctx) -> None:
    """核④ 带素材全链：transcript 素材 → dock 任务书 → dock Start → run
    completed → post 产物落库；估价三断言（fold 对账 / 报价单调性 / NULL
    语义）与 repair 只一轮（Agent 漏斗进程内 stub 自检）随链并入（简报
    C4「原 S41/S42 保留并入」）。"""
    # A) 活链：COMPLETED transcript 资产（声明素材升格的终态——worker 资产
    #    队列不碰假字节），writer 链走真 LLM 到 completed。
    pid = await ctx.new_project("S4 material chain")
    await seed_asset(pid, ctx.user_id, AssetType.TRANSCRIPT, "talk.txt",
                     extracted_text="My talk about grid storage auctions.",
                     processed=True)

    turn1 = await ctx.chat(pid, "write a LinkedIn post from my talk")
    turn1 = await answer_caption_gate(ctx, turn1)  # write_quotes 链先答 caption
    check(is_task_book_dock(turn1["assistant_message"]), "turn1 docks a task_book",
          turn1["assistant_message"])
    res = await ctx.answer(turn1["assistant_message"]["id"], {"kind": "start"})
    check(res.status_code == 200, "dock Start answers the task book", res.text)
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
    except MiniMaxSchemaError as exc:
        raised = exc
    check(isinstance(raised, MiniMaxSchemaError), "the second rejection raises")
    check(len(stub.calls) == 2, "no third call after the repair round",
          len(stub.calls))

    # 3. Transport-class MiniMaxError is NOT repaired (client tenacity owns it).
    stub = _StubClient([MiniMaxError("MiniMax HTTP 500"), _ProbeResult(text="x")])
    raised = None
    try:
        await _probe_agent(stub, name="scenario_probe_3").call()
    except MiniMaxError as exc:
        raised = exc
    check(isinstance(raised, MiniMaxError)
          and not isinstance(raised, MiniMaxSchemaError),
          "transport failure propagates unrepaired")
    check(len(stub.calls) == 1, "transport failure: no repair round", len(stub.calls))

    # 4. Declared fallback: a failed call returns the declaration's result.
    stub = _StubClient([MiniMaxError("MiniMax HTTP 500")])
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

    # 7. media_text_fallback × repair composition: the text-only degradation
    #    runs INSIDE the attempt, and the repair round re-carries the media
    #    (degrading again on its own schema rejection) — worst case 4 calls,
    #    the pre-P3 retry-era bound.
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

    # 7a. A successful text-only degradation does NOT consume the repair
    #     round — the echo never appears.
    stub = _StubClient(["schema", _ProbeResult(text="ok")])
    result = await _media_agent(stub, name="scenario_probe_7a").call()
    check(result.text == "ok", "media degradation returns", result)
    check(len(stub.calls) == 2,
          "media degradation inside one attempt == 2 calls", len(stub.calls))
    a_media, a_text = stub.calls[0][1][1], stub.calls[1][1][1]
    check(isinstance(a_media["content"], list)
          and any(p.get("type") == "image_url" for p in a_media["content"]),
          "attempt 1 carries the media parts", a_media["content"])
    check(isinstance(a_text["content"], str) and echo not in a_text["content"],
          "the text degradation is pre-echo (no repair round consumed)",
          a_text["content"][-120:])

    # 7b. Both attempts degrade: attempt(media→text) fails twice, the repair
    #     round re-carries media + echo and degrades to the echoed text —
    #     4 calls total.
    stub = _StubClient(["schema", "schema", "schema", _ProbeResult(text="ok")])
    result = await _media_agent(stub, name="scenario_probe_7b").call()
    check(result.text == "ok", "media composition survives to the repair round",
          result)
    check(len(stub.calls) == 4,
          "worst case == 4 calls (attempt media+text, repair media+text)",
          len(stub.calls))
    check([k for k, _ in stub.calls] == ["generate"] * 4,
          "the media degradation never streams", [k for k, _ in stub.calls])
    r_media, r_text = stub.calls[2][1][1], stub.calls[3][1][1]
    check(isinstance(r_media["content"], list)
          and any(p.get("type") == "image_url" for p in r_media["content"])
          and echo in r_media["content"][-1]["text"],
          "the repair round re-carries media + echo", r_media["content"])
    check(isinstance(r_text["content"], str) and echo in r_text["content"],
          "the repair round's text degradation carries the echo",
          r_text["content"][-120:])


class _ProbeResult(BaseModel):
    text: str


class _StubClient:
    """Scripted MiniMaxClient stand-in: records every call, plays outcomes.

    Script items: ``"schema"`` (raise MiniMaxSchemaError), an exception
    instance (raise it), or a ``_ProbeResult`` (return it).
    """

    def __init__(self, script: list[object]) -> None:
        self.script = list(script)
        self.calls: list[tuple[str, list[dict]]] = []

    def _play(self, kind: str, messages: list[dict]) -> _ProbeResult:
        self.calls.append((kind, messages))
        item = self.script.pop(0)
        if item == "schema":
            raise MiniMaxSchemaError("Failed to validate response: boom")
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
    """核⑤ 修订链（ADR-043 + ADR-053）：re-dock 旧书 supersede（机器标记入
    流）→ 面板手改整链存活于无关 refine → chat 修订恒胜（覆盖面板钉）→
    task_book 待决打字母永不误答（不参与任何结算）→ 散文确认起 run。"""
    pid = await ctx.new_project("S5 revision chain")
    await seed_asset(pid, ctx.user_id, AssetType.VIDEO, "talk.mp4")

    turn1 = await ctx.chat(pid, "cut highlight clips from my talk")
    check(is_task_book_dock(turn1["assistant_message"]), "turn1 docks a task_book",
          turn1["assistant_message"])
    first_qid = turn1["assistant_message"]["id"]

    def pin_count(book: dict, count: int) -> dict:
        """Simulate a panel hand edit: the select_clips count set in params —
        the edited chain IS the prior_intent (no merge machinery, ADR-043)."""
        edited = dict(book["intent"])
        edited["tasks"] = [
            {**t, "params": {**task_params(t), "count": count}}
            if t["tool"] == "select_clips" else t
            for t in book_tasks(book)
        ]
        return edited

    # 面板手改存活 + 旧书 supersede（已答问题入流的机器标记）。
    book1 = (await ctx.results(pid)).get("pending_brief")
    turn2 = await ctx.chat(
        pid, "also add a German post", prior_intent=pin_count(book1, 3)
    )
    check(is_task_book_dock(turn2["assistant_message"]), "turn2 re-docks",
          turn2["assistant_message"])
    check(turn2["assistant_message"]["id"] != first_qid,
          "the old book is superseded by a new question row")
    tasks = book_tasks((await ctx.results(pid)).get("pending_brief"))
    clips = [t for t in tasks if t["tool"] == "select_clips"]
    check(clips and task_params(clips[0]).get("count") == 3,
          "the panel hand edit survives an unrelated refine", tasks)
    check(any(t["tool"] == "write_post" and task_params(t).get("language") == "de" for t in tasks),
          "the German post arrived", tasks)
    msgs = await ctx.messages(turn2["conversation_id"])
    old = next(m for m in msgs if m["id"] == first_qid)
    check((old.get("answer") or {}).get("text") == "superseded",
          "the superseded book carries the machine marker", old.get("answer"))

    # chat 修订恒胜（覆盖面板钉）。
    book2 = (await ctx.results(pid)).get("pending_brief")
    turn3 = await ctx.chat(
        pid, "clips only needs 2", prior_intent=pin_count(book2, 3)
    )
    check(is_task_book_dock(turn3["assistant_message"]), "turn3 re-docks",
          turn3["assistant_message"])
    tasks = book_tasks((await ctx.results(pid)).get("pending_brief"))
    clips = [t for t in tasks if t["tool"] == "select_clips"]
    check(clips and task_params(clips[0]).get("count") == 2,
          "the chat revision overrides the panel pin (chat always wins)", tasks)

    # task_book 待决不参与任何结算：打字母永不当选项答掉（旧 S40 并入）。
    live_qid = turn3["assistant_message"]["id"]
    turn4 = await ctx.chat(pid, "a")
    check(turn4.get("answered_question") is None,
          "a typed letter never answers a task_book", turn4)
    q = await message_row(live_qid)
    check(q.get("answer") is None or (q["answer"] or {}).get("text") == "superseded",
          "the book stays pending or is superseded by a re-dock — never letter-answered",
          q.get("answer"))

    turn5 = await ctx.chat(pid, "looks good, start")
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

    # f) 插话后续跑（ADR-053 R2 chat path）：进度插话 → 正常回答 + 代码拼装
    #    提醒尾 + 问题保持 pending + run 保持 parked → 再打字母唤醒。
    pid = await ctx.new_project("S6f interjection resumes later")
    ck = await seed_parked_interrupt(pid, ctx.user_id)
    turn = await ctx.chat(pid, "how is the run doing?")
    check(turn.get("answered_question") is None,
          "an interjection never settles the parked interrupt", turn)
    content = turn["assistant_message"].get("content") or ""
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
       回答后 replay 出任务书：回执 kind=option + 选中的 mode 钉进
       pending_brief；
    B) 无独立第二语言（项目 en / 素材 en）→ 不问，run 直接带
       run.context.caption_mode == "source_only"（§2.3/D4）；
    C) 答 → 追问 → Start：answered mode 存活于中间修订轮（stash 继承：
       fresh LLM-set > fresh keyword > stashed answer）。

    LLM 判定有抖动（"make a quote card" 可能回反问或提别的链——两者都
    正确地跳过 caption 闸门），各部各给 3 次尝试直到 write_quotes 落地。
    """
    material = "Some keynote transcript about the future of embodied intelligence."

    # A) distinct alt language exists → dock first, answer, task book follows.
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
    check(is_task_book_dock(follow),
          "A: the answer replays the stashed proposal into a task book", follow)
    book = await pending_book(ctx, pid)
    check(((book or {}).get("intent") or {}).get("caption_mode") == "bilingual",
          "A: the picked mode rides pending_brief end-to-end", book)

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
    #    between the answer and Start — the book path overwrites
    #    pending_brief wholesale with the fresh verdict (caption_mode=None
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
          "C: the caption question docks on the book path")
    ans = await ctx.answer(docked_c["assistant_message"]["id"],
                           {"kind": "option", "option_id": "caption_mode_bilingual"})
    check(ans.status_code in (200, 201), "C: caption answer accepted", ans.text)
    # The answer's replay already docks the task book; refinement nudges may
    # re-dock it (superseding the row) — always Start the LATEST live row.
    follow_c = ans.json().get("follow_up") or {}
    book_qid: str | None = follow_c.get("id") if is_task_book_dock(follow_c) else None
    check(book_qid is not None, "C: the answer replays the stashed task book", follow_c)
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
        book = await pending_book(ctx, pid_c)
        check(((book or {}).get("intent") or {}).get("caption_mode") == "bilingual",
              "C: the refinement turn keeps the answered caption_mode", book)
        if is_task_book_dock(turn["assistant_message"]):
            book_qid = turn["assistant_message"]["id"]
            break
    check(reasked is None, "C: the answered question is never re-asked", reasked)
    check(book_qid is not None, "C: a task book docks after the refinement")
    # Start THROUGH THE PANEL: the frontend's normalize strips fields it
    # doesn't edit, so its Start payload carries the book's intent minus
    # caption_mode — the server must inherit the answered mode from the
    # stored pending brief ("not mentioned" ≠ "retracted", 2026-08-29).
    book = await pending_book(ctx, pid_c)
    panel_intent = dict((book or {}).get("intent") or {})
    check(bool(panel_intent), "C: pending book carries an intent", book)
    panel_intent.pop("caption_mode", None)
    res = await ctx.answer(book_qid, {"kind": "start", "intent": panel_intent})
    check(res.status_code == 200, "C: task book start accepted", res.text)
    rid_c = res.json()["answered_question"].get("workflow_run_id")
    check(rid_c, "C: run id on the answered book", res.json())
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
    check(is_task_book_dock(turn1["assistant_message"]),
          "a rooted topic docks a task book", turn1["assistant_message"])
    book = (await ctx.results(pid)).get("pending_brief")
    qid = turn1["assistant_message"]["id"]

    # 面板手编起步（S5 先例）：chain 换成确定性的 [research, write_post]。
    edited = dict(book["intent"])
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
    """核⑨ 问事不出书：能力提问 / 闲聊 → 纯 answer（无 dock 无 run 无账本）；
    无书 "start it" 不死路不起 run（rootless → 主题问门槛接住，永不裸跑）。"""
    pid = await ctx.new_project("S9 consult")

    turn1 = await ctx.chat(pid, "what can you do?")
    check(turn1["run_id"] is None, "capability question starts no run")
    check(not turn1["assistant_message"].get("question"), "no question docks",
          turn1["assistant_message"])
    check(has_prose(turn1["assistant_message"]), "a prose answer lands")

    turn2 = await ctx.chat(pid, "hello, how are you today?")
    check(turn2["run_id"] is None, "small talk starts no run", turn2)
    check(not turn2["assistant_message"].get("question"),
          "small talk docks nothing", turn2["assistant_message"])
    check(has_prose(turn2["assistant_message"]), "small talk gets an answer")

    turn3 = await ctx.chat(pid, "start it")
    check(turn3["run_id"] is None, "a baseless start never launches a run", turn3)
    check(not is_task_book_dock(turn3["assistant_message"]),
          "a baseless start never docks a groundless book either (出书门槛接住)",
          turn3["assistant_message"])
    check(await count_runs(pid) == 0, "no run the whole journey")
    book = await pending_book(ctx, pid)
    check(book is None or book.get("intent") is None,
          "no task book parks on consults", book)


# ---- S10 SSE 流式 --------------------------------------------------------------------


async def s10_sse_turn_streaming(ctx: Ctx) -> None:
    """S10 SSE 回合：answer 流式（delta 拼接 == 信封散文）；draft 流计划复述（== intent.answer）。"""
    pid = await ctx.new_project("S10 sse streaming")
    await seed_asset(pid, ctx.user_id, AssetType.VIDEO, "keynote.mp4")

    # Answer turn: prose previews stream, and concatenated deltas must equal
    # the envelope's persisted content (preview channel == source of truth).
    # The phrasing mirrors the system prompt's few-shot example verbatim —
    # the answer/draft judgment is LLM variance, and the strict concat
    # assertion below needs the answer verdict to be near-deterministic.
    deltas, completed, failed = await ctx.chat_stream(pid, "what can you generate?")
    check(failed is None, "answer turn has no turn.failed", failed)
    check(completed is not None, "answer turn ends with turn.completed")
    content = (completed["assistant_message"].get("content") or "")
    check(len(deltas) > 0, "answer turn streams prose deltas")
    check("".join(deltas) == content, "delta concat == envelope content",
          f"{''.join(deltas)!r} vs {content!r}")
    check(completed["run_id"] is None, "answer turn starts no run")

    # Draft turn: the plan echo (intent.answer) streams as deltas and is
    # persisted in the pending brief; the dock rides the envelope.
    deltas, completed, failed = await ctx.chat_stream(
        pid, "Cut 3 highlight clips from my talk"
    )
    check(failed is None, "draft turn has no turn.failed", failed)
    check(completed is not None, "draft turn ends with turn.completed")
    check(is_task_book_dock(completed["assistant_message"]),
          "draft turn docks the task book via the envelope",
          completed["assistant_message"])
    book = (await ctx.results(pid)).get("pending_brief")
    echo = (book["intent"].get("answer") or "")
    check(len(deltas) > 0, "draft turn streams the plan echo")
    check("".join(deltas) == echo, "echo deltas == persisted intent.answer",
          f"{''.join(deltas)!r} vs {echo!r}")


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
    check(is_task_book_dock(turn1["assistant_message"]), "turn1 docks a task_book",
          turn1["assistant_message"])
    book = (await ctx.results(pid)).get("pending_brief")
    tasks = book_tasks(book)
    check(not any(t["tool"] == "select_clips" for t in tasks),
          "whole-source intent never routes through select_clips", tasks)
    subs = [t for t in tasks if t["tool"] == "translate_clip"]
    check(len(subs) == 1 and task_params(subs[0]).get("target_language") == "zh",
          "one translate task into Chinese", tasks)
    check(task_params(subs[0]).get("bilingual") is True,
          "双语 → bilingual: true", tasks)
    derived = (book or {}).get("derived") or []
    check(any(r.get("type") == "video" for r in derived),
          "the derived preview shows the whole video", derived)
    check(any(r.get("variant") == "subs" for r in derived),
          "the derived preview shows the subtitled version", derived)

    res = await ctx.answer(turn1["assistant_message"]["id"], {"kind": "start"})
    check(res.status_code == 200, "dock Start answers the task book", res.text)
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
    """S12 brief 账本来源优先级三态矩阵（ADR-052 B2 D1-C1，进程内纯函数）：
    user-stated 永不反向覆盖 / user 重申恒胜 / inferred 压 default /
    default 永不压 inferred / no-opinion 槽永不落账 / 整账 None 原样返回 /
    asked 簿永不吃 LLM 提议。"""
    del ctx  # in-process pure-function matrix — no API, no DB rows
    from app.chat.service import merge_brief
    from app.models.schemas import BriefLedger, BriefSlot, BriefSlotSource as Src

    def ledger(**slots) -> BriefLedger:
        return BriefLedger(**slots)

    def slot(value, source) -> BriefSlot:
        return BriefSlot(value=value, source=source)

    # 1. user-stated survives inferred AND default proposals (永不反向覆盖).
    stored = ledger(topic=slot("grid storage", Src.USER_STATED))
    out = merge_brief(
        ledger(
            topic=slot("renewables", Src.INFERRED),
            audience=slot("CTOs", Src.INFERRED),
        ),
        stored,
    )
    check(out.topic.value == "grid storage"
          and out.topic.source == Src.USER_STATED,
          "user-stated topic survives an inferred proposal", out.topic)
    out = merge_brief(ledger(topic=slot("anything", Src.DEFAULT)), stored)
    check(out.topic.value == "grid storage",
          "user-stated topic survives a default proposal", out.topic)

    # 2. The user re-stating a slot always wins (user-stated ≥ user-stated —
    #    chat 修订恒胜).
    out = merge_brief(ledger(topic=slot("renewables", Src.USER_STATED)), stored)
    check(out.topic.value == "renewables"
          and out.topic.source == Src.USER_STATED,
          "a re-stated slot lands (the user spoke again)", out.topic)

    # 3. inferred lands over an empty/default slot and over a default value;
    #    default never lands over inferred.
    stored = ledger(audience=slot("general public", Src.DEFAULT))
    out = merge_brief(ledger(audience=slot("first-time founders", Src.INFERRED)), stored)
    check(out.audience.value == "first-time founders"
          and out.audience.source == Src.INFERRED,
          "inferred outranks default", out.audience)
    out = merge_brief(ledger(audience=slot("everyone", Src.DEFAULT)), out)
    check(out.audience.value == "first-time founders",
          "default never overwrites inferred", out.audience)

    # 4. A no-opinion slot (value=None) never lands — stored survives; and
    #    fresh inference re-lands over stale inference (same rank, latest wins).
    out = merge_brief(
        ledger(tone=BriefSlot(source=Src.INFERRED), topic=slot("new angle", Src.INFERRED)),
        ledger(tone=slot("sharp", Src.USER_STATED), topic=slot("old angle", Src.INFERRED)),
    )
    check(out.tone.value == "sharp", "a None update never lands", out.tone)
    check(out.topic.value == "new angle",
          "same-rank updates land (fresh inference over stale)", out.topic)

    # 5. constraints is one slot — the list rides as the value, same rules.
    stored = ledger(constraints=slot(["keep it under 200 words"], Src.USER_STATED))
    out = merge_brief(ledger(constraints=slot(["add hashtags"], Src.INFERRED)), stored)
    check(out.constraints.value == ["keep it under 200 words"],
          "user-stated constraints survive inference", out.constraints)

    # 6. update=None returns the stored ledger (start/answer verdicts carry
    #    no proposal); the merge never mutates the stored input in place.
    stored = ledger(topic=slot("grid storage", Src.USER_STATED))
    check(merge_brief(None, stored) is stored, "None update returns stored verbatim")
    merge_brief(ledger(audience=slot("CTOs", Src.INFERRED)), stored)
    check(stored.audience.value is None, "the merge never mutates the stored input")

    # 7. The code-owned asked roll never lands from an LLM proposal (禁 LLM
    #    簿记, D2-C2) — it rides only the stored side of the merge.
    stored.asked = ["topic"]
    upd = ledger()
    upd.asked = ["audience"]
    out = merge_brief(upd, stored)
    check(out.asked == ["topic"],
          "an LLM-proposed asked roll never lands (code-owned)", out.asked)


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
