"""chat_scenarios.py — preset multi-turn acceptance scripts for the intent layer.

The intent-surface-unification acceptance harness (brief
``docs/tasks/intent-surface-unification.md`` W6): preset multi-turn
scripts drive a LIVE API through the only intent surface
(``POST /chat`` + the answer endpoint) and assert SHAPE-level outcomes per
turn — proposal state, dock state, run count, archived rows, SSE frame
sequence — never LLM wording (prohibition #7: no copy assertions).

Scenario families (2026-08-05 restructure): the lost-user / 迷失 dimension
cuts ACROSS families — a lost user's turn can land on routing, consult,
revision, smalltalk, recipe or material alike, so its variants live INSIDE
each family (S17–S22), never as a separate block. Scenario ids are
birth-ordered and never recycled; position in this file = family.

    首轮路由   S1 vague · S2 explicit · S17 lost-with-media journey
    能力咨询   S4 capability · S18 lost "what suits me"
    修订       S3 loop · S19 inarticulate · S15 recipe refine · S16 three-way
    边界       S6 post-run · S7 smalltalk+publish · S8 empty · S20 venting
    配方       S5 mention pin · S10 dub classify · S11 no-media · S22 hesitant
    素材       S12 declared · S13 no-material · S14 bare paste · S21 lost+empty
    契约       S23 bail+reopen · S24 autonomy→run · S25 dup-409 · S26 rebuild
               S27 QA archive · S28 plain no-media · S29 count 422 · S30 attach-only
    四态分派   S31 task_list run · S32 edit_ops ops行 · S33 progress · S34 meta · S35 asset scope
    checkpoint S36 三答法+空白不答 · S37 bail级联 · S38 supersede级联 · S39 过期扫描 · S40 task_book不参与autoResume
    流式       S9 SSE
    harness    S41 repair 只一轮（Agent 漏斗自检，进程内 stub，不打 API）

S31/S35 起的 run 是真的（worker 会执行）；checkpoint 族（S36–S39）seed parked
run 手工行，答题/过期唤醒后由 worker 跑零 LLM 的 answer 分支收官——需要 dev
worker 在跑。S36d 的空白 attachment-only 轮会落到 ChatIntentAgent（空文本），
它若 dock 新题把 checkpoint supersede 掉是设计内行为（J5），断言只管
answered_question 为 None。

``# W4 升级:`` comments mark assertions that tighten when the advisor
posture lands (CHAT_ARCH §3.3: 诊断一轮封顶 / 带理由纠偏 / 成功定义随任务书 /
按素材画像推荐配方). Today the lost-user variants lock the current contract:
never a dead end, never a groundless run, the pending book survives.

The server does all LLM work (PlanAgent / ChatIntentAgent); this script only
mints a scenario user's JWT and seeds DB rows the scenarios need (a fake
media asset for clips gating, a completed run for the plan-path regression).
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

# Make ``app`` importable when run as a file (apps/api on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from app.agents.base import Agent, StreamingAgent  # noqa: E402
from app.clients.minimax import MiniMaxError, MiniMaxSchemaError  # noqa: E402
from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.tables import (  # noqa: E402
    Asset,
    Conversation,
    Message,
    Operation,
    Output,
    User,
    WorkflowRun,
    WorkflowStep,
)
from app.models.schemas import (  # noqa: E402
    AskOption,
    AskPayload,
    AssetType,
    WorkflowStatus,
)
from app.platform.auth import create_access_token  # noqa: E402

BASE = os.getenv("SCENARIO_API_BASE", "http://127.0.0.1:8000/api/v1")
TIMEOUT = httpx.Timeout(180.0)  # plan-path turns are real LLM calls


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

    async def chat_raw(self, pid: str, message: str, **extra: object) -> httpx.Response:
        return await self.client.post(
            "/chat",
            json={"project_id": pid, "message": message, **extra},
        )

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

    async def listed_project_ids(self) -> set[str]:
        res = await self.client.get("/projects")
        check(res.status_code == 200, "GET /projects", res.text)
        return {p["id"] for p in res.json()}

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
) -> None:
    """A fake file-backed asset row — enough for the clips-media gate and the
    plan agent's filename context; the bytes never exist. ``extracted_text``
    satisfies the "transcript" required-input check (registry requires)."""
    async with AsyncSessionLocal() as db:
        db.add(
            Asset(
                user_id=user_id,
                project_id=uuid.UUID(pid),
                type=type_,
                file_url=f"scenario/{filename}",
                title=filename,
                extracted_text=extracted_text,
            )
        )
        await db.commit()


async def seed_completed_run(pid: str) -> None:
    """A settled run row — the plan path must never claim a project that has
    runs (S6/S7 regression seat)."""
    async with AsyncSessionLocal() as db:
        db.add(
            WorkflowRun(
                project_id=uuid.UUID(pid),
                status=WorkflowStatus.COMPLETED,
                context={"outputs": [{"type": "post"}], "target_language": "en"},
            )
        )
        await db.commit()


async def seed_clip_output(pid: str) -> str:
    """A user-facing clip output with a minimal valid render_spec — the edit
    ops dispatch target (S32). The source asset id is fake; ops never read it."""
    async with AsyncSessionLocal() as db:
        output = Output(
            project_id=uuid.UUID(pid),
            type="clip",
            language="en",
            payload={},
            render_spec={"source": {"asset_id": str(uuid.uuid4()), "kind": "video"}},
        )
        db.add(output)
        await db.commit()
        await db.refresh(output)
        return str(output.id)


async def seed_running_run_with_steps(pid: str) -> str:
    """A mid-flight run with node-level progress — the G-2 progress question's
    context source (S33). Steps carry quantified summaries, never executed."""
    async with AsyncSessionLocal() as db:
        run = WorkflowRun(
            project_id=uuid.UUID(pid),
            status=WorkflowStatus.RUNNING,
            context={"outputs": [{"type": "clips", "count": 3}], "target_language": "en"},
        )
        db.add(run)
        await db.flush()
        db.add_all(
            [
                WorkflowStep(
                    run_id=run.id, kind="preprocess", status="done", seq=0,
                    spec={"summary": "Transcribed · 812 words"},
                ),
                WorkflowStep(
                    run_id=run.id, kind="director_understand", status="running", seq=1,
                    spec={},
                ),
                WorkflowStep(run_id=run.id, kind="clips_pipeline", status="pending", seq=2),
            ]
        )
        await db.commit()
        return str(run.id)


async def seed_parked_checkpoint(
    pid: str,
    user_id: uuid.UUID,
    *,
    parked_hours_ago: float = 0,
    with_downstream: bool = False,
) -> dict:
    """A direction checkpoint parked for a human answer (期 4 seed shape):
    WAITING_HUMAN run + waiting ``checkpoint`` node (options in
    spec.suspend_payload) + the docked choice question row carrying the
    ``workflow_run_id`` dispatch marker. ``with_downstream`` adds a pending
    child node so the bail cascade has something to skip (S37)."""
    options = [
        {"id": "a", "label": "Focus: Pricing", "argument_id": "arg-1"},
        {"id": "b", "label": "Focus: Roadmap", "argument_id": "arg-2"},
        {"id": "c", "label": "Full-talk highlights", "argument_id": None},
    ]
    started_at = datetime.now(UTC) - timedelta(hours=parked_hours_ago)
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
            question=AskPayload(
                kind="choice",
                options=[AskOption(id=o["id"], label=o["label"]) for o in options],
                allow_freeform=True,
            ).model_dump(mode="json"),
            workflow_run_id=run.id,
        )
        db.add(question)
        await db.flush()
        node = WorkflowStep(
            run_id=run.id,
            kind="checkpoint",
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
                kind="director_plan",
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


async def operations_for_output(output_id: str) -> list[dict]:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(Operation)
                .where(Operation.output_id == uuid.UUID(output_id))
                .order_by(Operation.seq)
            )
        ).scalars().all()
        return [
            {"op": o.op, "source": o.source, "message_id": str(o.message_id) if o.message_id else None}
            for o in rows
        ]


async def wait_run_status(run_id: str, wanted: set[str], timeout: float = 45.0) -> dict:
    """Poll a run until it reaches one of ``wanted`` statuses. The wake half
    of a checkpoint answer is synchronous, but settling (the thin node's
    answer branch → finalize) is worker-driven — hence the poll. Requires the
    dev worker (the checkpoint answer branch is zero-LLM, so this is fast)."""
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


async def project_assets(pid: str) -> list[dict]:
    """DB read: the project's asset rows (material-promotion assertions)."""
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(Asset).where(Asset.project_id == uuid.UUID(pid))
            )
        ).scalars().all()
        return [
            {"type": str(a.type), "extracted_text": a.extracted_text, "title": a.title}
            for a in rows
        ]


# ---- Assertion helpers ------------------------------------------------------


def is_task_book_dock(msg: dict) -> bool:
    return bool(msg.get("question")) and msg["question"].get("kind") == "task_book" and not msg.get("answer")


def no_task_book_dock(msg: dict) -> bool:
    """No task_book question attached (any other question kind is fine)."""
    question = msg.get("question")
    return not question or question.get("kind") != "task_book"


def has_prose(msg: dict) -> bool:
    """The assistant message carries a non-empty prose reply."""
    return bool((msg.get("content") or "").strip())


def book_slots(book: dict) -> list[dict]:
    return ((book or {}).get("intent") or {}).get("outputs") or []


async def pending_book(ctx: Ctx, pid: str) -> dict | None:
    """The project's pending task book via the results endpoint (None when none)."""
    return (await ctx.results(pid)).get("pending_intent")


# ---- Scenarios: 首轮路由 ------------------------------------------------------
# 迷失横切：S1 是"半迷失"（有动词、没点名产物），S17 是"全迷失"（素材在、目标无）。


async def s1_vague_first_turn_then_prose_start(ctx: Ctx) -> None:
    """S1 模糊首次（有媒体）→ dock 任务书（reasons 非空）→ “开始吧”起 run。"""
    pid = await ctx.new_project("S1 vague start")
    await seed_asset(pid, ctx.user_id, AssetType.VIDEO, "keynote.mp4")

    turn1 = await ctx.chat(pid, "帮我处理一下这个演讲")
    check(is_task_book_dock(turn1["assistant_message"]), "turn1 docks a task_book", turn1["assistant_message"])
    check(turn1["run_id"] is None, "turn1 starts no run")
    book = (await ctx.results(pid)).get("pending_intent")
    check(book is not None, "pending_intent persisted")
    check(len(book.get("reasons") or []) > 0, "vague prompt needs a human check (reasons non-empty)", book)

    turn2 = await ctx.chat(pid, "开始吧")
    check(turn2["run_id"] is not None, "prose confirmation starts the run", turn2)
    check(turn2["answered_question"] is not None, "task book archived as QA", turn2)
    check((await ctx.results(pid)).get("pending_intent") is None, "pending_intent cleared on start")


async def s2_explicit_first_turn_then_dock_start(ctx: Ctx) -> None:
    """S2 精确首次 → dock（clips×5 + post(de)）→ dock Start 起 run，slots 一致。"""
    pid = await ctx.new_project("S2 explicit start")
    await seed_asset(pid, ctx.user_id, AssetType.VIDEO, "interview.mp4")

    turn1 = await ctx.chat(pid, "Cut 5 clips and a German LinkedIn post from this talk")
    check(is_task_book_dock(turn1["assistant_message"]), "turn1 docks a task_book", turn1["assistant_message"])
    book = (await ctx.results(pid)).get("pending_intent")
    slots = book_slots(book)
    clips = next((s for s in slots if s["type"] == "clips"), None)
    posts = [s for s in slots if s["type"] == "post"]
    check(clips is not None and clips.get("count") == 5, "clips slot with count 5", slots)
    check(any(p.get("language") == "de" for p in posts) or (book["intent"].get("language") == "de" and posts),
          "a German post slot", slots)

    res = await ctx.answer(turn1["assistant_message"]["id"], {"kind": "start"})
    check(res.status_code == 200, "dock Start answers the task book", res.text)
    answered = res.json()["answered_question"]
    check(answered.get("workflow_run_id"), "run id on the answered book", answered)
    runs = await ctx.client.get(f"/projects/{pid}/runs")
    run_ctx = runs.json()[0].get("context") or {}
    run_slots = run_ctx.get("outputs") or []
    check(any(s.get("type") == "clips" for s in run_slots if isinstance(s, dict)),
          "run carries the clips slot", run_ctx)


async def s17_lost_first_turn_journey(ctx: Ctx) -> None:
    """S17 全迷失首轮（路由×迷失）：素材在、目标无——不死路不裸跑，指路后归位 dock→start。"""
    pid = await ctx.new_project("S17 lost first turn")
    await seed_asset(pid, ctx.user_id, AssetType.VIDEO, "lecture.mp4")

    # 全迷失首轮：素材在、产物没点名、平台不懂。当日契约：永不裸跑、永不死路
    # ——要么 dock 一本带 reasons 的默认书，要么散文反问/指路。
    # W4 升级: 诊断一轮封顶——首轮必须先问路由问题（听众/目的），而非默认任务书。
    turn1 = await ctx.chat(pid, "我录了一场讲座，想开始做 LinkedIn，但完全不知道从哪里开始")
    check(turn1["run_id"] is None, "a lost first turn never starts a run", turn1)
    msg1 = turn1["assistant_message"]
    if is_task_book_dock(msg1):
        book = await pending_book(ctx, pid)
        check(len((book or {}).get("reasons") or []) > 0,
              "a defaulted book flags its guesses (reasons non-empty)", book)
        turn2 = await ctx.chat(pid, "开始吧")
        check(turn2["run_id"] is not None, "prose confirmation starts the run", turn2)
    else:
        check(has_prose(msg1), "otherwise a prose reply lands (ask/guidance)", msg1)
        turn2 = await ctx.chat(pid, "那你先帮我剪几条高光切片吧")
        check(is_task_book_dock(turn2["assistant_message"]),
              "a named direction docks the task book", turn2["assistant_message"])
        turn3 = await ctx.chat(pid, "开始吧")
        check(turn3["run_id"] is not None, "prose confirmation starts the run", turn3)


# ---- Scenarios: 能力咨询 ------------------------------------------------------


async def s4_capability_question_then_baseless_start(ctx: Ctx) -> None:
    """S4 能力提问 → 纯 answer（无 dock 无 run）；无书“start it”不死路不起 run。"""
    pid = await ctx.new_project("S4 capability question")

    turn1 = await ctx.chat(pid, "what can you do?")
    check(turn1["run_id"] is None, "capability question starts no run")
    check(not turn1["assistant_message"].get("question"), "no question docks", turn1["assistant_message"])
    check(has_prose(turn1["assistant_message"]), "a prose answer lands")

    turn2 = await ctx.chat(pid, "start it")
    check(turn2["run_id"] is None, "a baseless start never launches a run", turn2)


async def s18_lost_capability_consult(ctx: Ctx) -> None:
    """S18 迷失咨询（能力×迷失）："我这种情况适合做什么"——不裸跑、不死路，出书必带 reasons。"""
    pid = await ctx.new_project("S18 lost consult")
    await seed_asset(pid, ctx.user_id, AssetType.VIDEO, "lecture.mp4")

    # 咨询形态：问的是"适合什么"，不是下达工作。当日契约：无 run、非死路；
    # 若直接给任务书，默认值必须标出让人确认。
    # W4 升级: 回答必须按素材画像点名推荐一张 live 配方卡（§3.3 第 4 条）。
    turn1 = await ctx.chat(
        pid, "我是大学讲师，完全不懂社交媒体——像我这种情况，适合做什么样的内容？"
    )
    check(turn1["run_id"] is None, "a consult never starts a run", turn1)
    msg1 = turn1["assistant_message"]
    check(is_task_book_dock(msg1) or has_prose(msg1), "never a dead end", msg1)
    if is_task_book_dock(msg1):
        book = await pending_book(ctx, pid)
        check(len((book or {}).get("reasons") or []) > 0,
              "defaults in the book are flagged for human check", book)


# ---- Scenarios: 修订 ----------------------------------------------------------


async def s3_refinement_loop(ctx: Ctx) -> None:
    """S3 修订循环：两次 re-dock（旧书 supersede）→ pin 存活 → 确认起 run。"""
    pid = await ctx.new_project("S3 refinement loop")
    await seed_asset(pid, ctx.user_id, AssetType.TRANSCRIPT, "talk.txt")

    turn1 = await ctx.chat(pid, "write a LinkedIn post from my talk")
    check(is_task_book_dock(turn1["assistant_message"]), "turn1 docks a task_book", turn1["assistant_message"])
    first_qid = turn1["assistant_message"]["id"]

    turn2 = await ctx.chat(pid, "add a French version too")
    check(is_task_book_dock(turn2["assistant_message"]), "turn2 re-docks", turn2["assistant_message"])
    check(turn2["assistant_message"]["id"] != first_qid, "old book superseded by a new question row")
    slots = book_slots((await ctx.results(pid)).get("pending_intent"))
    posts = [s for s in slots if s["type"] == "post"]
    check(any(p.get("language") == "fr" for p in posts) or len(posts) >= 2,
          "a French post version appeared", slots)

    turn3 = await ctx.chat(pid, "focus on the Q&A section")
    check(is_task_book_dock(turn3["assistant_message"]), "turn3 re-docks", turn3["assistant_message"])
    slots = book_slots((await ctx.results(pid)).get("pending_intent"))
    posts = [s for s in slots if s["type"] == "post"]
    check(any(p.get("language") == "fr" for p in posts) or len(posts) >= 2,
          "the French version survives refinement (accumulated prompt)", slots)

    turn4 = await ctx.chat(pid, "looks good, start")
    check(turn4["run_id"] is not None, "prose confirmation starts the run", turn4)


async def s19_inarticulate_revision(ctx: Ctx) -> None:
    """S19 迷失修订（修订×迷失）："感觉不对但说不好"——书不丢、不裸跑；能指认时正常 re-dock。"""
    pid = await ctx.new_project("S19 inarticulate revision")
    await seed_asset(pid, ctx.user_id, AssetType.TRANSCRIPT, "talk.txt")

    turn1 = await ctx.chat(pid, "write a LinkedIn post from my talk")
    check(is_task_book_dock(turn1["assistant_message"]), "turn1 docks a task_book",
          turn1["assistant_message"])

    # 说不清的修订。当日契约：不裸跑、书存活，re-dock 或散文追问都算接住。
    # W4 升级: 必须把"不太对"翻译成具体可点的修订选项。
    turn2 = await ctx.chat(pid, "感觉不太对……我也说不好哪里，你看着调整一下？")
    check(turn2["run_id"] is None, "an inarticulate revision never starts a run", turn2)
    check((await pending_book(ctx, pid)) is not None, "the pending book survives")
    check(is_task_book_dock(turn2["assistant_message"]) or has_prose(turn2["assistant_message"]),
          "never a dead end", turn2["assistant_message"])

    # 能指认的修订走正常 re-dock（S3 同款通路）。
    turn3 = await ctx.chat(pid, "make the opening more of a hook")
    check(is_task_book_dock(turn3["assistant_message"]), "a specific revision re-docks",
          turn3["assistant_message"])
    check((await pending_book(ctx, pid)) is not None, "the book is still alive")


async def s15_recipe_refine_count(ctx: Ctx) -> None:
    """S15 配方=预设（2026-08-05 裁定）：Remix 后 refine "clips only needs 2"
    → 数量落在 docked 书上（配方只铺第一版，不钉任何字段）。"""
    pid = await ctx.new_project("S15 recipe refine count")
    await seed_asset(pid, ctx.user_id, AssetType.VIDEO, "talk.mp4")
    mentions = [{"type": "recipe", "id": "dub", "label": "Multilingual dub"}]

    turn1 = await ctx.chat(pid, "cut highlight clips from my talk", mentions=mentions)
    check(is_task_book_dock(turn1["assistant_message"]), "turn1 docks a task_book",
          turn1["assistant_message"])

    turn2 = await ctx.chat(pid, "clips only needs 2")
    check(is_task_book_dock(turn2["assistant_message"]), "turn2 re-docks",
          turn2["assistant_message"])
    slots = book_slots((await ctx.results(pid)).get("pending_intent"))
    clips = [s for s in slots if s["type"] == "clips"]
    check(clips and clips[0].get("count") == 2,
          "the chat revision lands on the recipe-seeded clips slot", slots)


async def s16_panel_edit_three_way(ctx: Ctx) -> None:
    """S16 三方合并：面板手改（explicit）在无关 refine 中存活；chat 修订覆盖手改。"""
    pid = await ctx.new_project("S16 three-way merge")
    await seed_asset(pid, ctx.user_id, AssetType.VIDEO, "talk.mp4")

    turn1 = await ctx.chat(pid, "cut highlight clips from my talk")
    check(is_task_book_dock(turn1["assistant_message"]), "turn1 docks a task_book",
          turn1["assistant_message"])

    def pin_count(book: dict, count: int) -> dict:
        """Simulate a panel hand edit: clips count pinned, slot explicit."""
        edited = dict(book["intent"])
        edited["outputs"] = [
            {**s, "count": count, "explicit": True} if s["type"] == "clips" else s
            for s in book_slots(book)
        ]
        return edited

    book1 = (await ctx.results(pid)).get("pending_intent")
    turn2 = await ctx.chat(
        pid, "also add a German post", prior_intent=pin_count(book1, 3)
    )
    check(is_task_book_dock(turn2["assistant_message"]), "turn2 re-docks",
          turn2["assistant_message"])
    slots = book_slots((await ctx.results(pid)).get("pending_intent"))
    clips = [s for s in slots if s["type"] == "clips"]
    check(clips and clips[0].get("count") == 3,
          "the panel hand edit survives an unrelated refine", slots)
    check(any(s["type"] == "post" and s.get("language") == "de" for s in slots),
          "the German post arrived", slots)

    book2 = (await ctx.results(pid)).get("pending_intent")
    turn3 = await ctx.chat(
        pid, "clips only needs 2", prior_intent=pin_count(book2, 3)
    )
    check(is_task_book_dock(turn3["assistant_message"]), "turn3 re-docks",
          turn3["assistant_message"])
    slots = book_slots((await ctx.results(pid)).get("pending_intent"))
    clips = [s for s in slots if s["type"] == "clips"]
    check(clips and clips[0].get("count") == 2,
          "the chat revision overrides the panel pin (chat always wins)", slots)


# ---- Scenarios: 边界 ----------------------------------------------------------


async def s6_followup_after_run_stays_off_plan_path(ctx: Ctx) -> None:
    """S6 完成后追问：plan path 不抢已有 run 的项目（无 task_book dock）。"""
    pid = await ctx.new_project("S6 post-run followup")
    await seed_completed_run(pid)

    turn1 = await ctx.chat(pid, "translate the second clip into French")
    check(no_task_book_dock(turn1["assistant_message"]),
          "no task_book dock on a project with runs", turn1["assistant_message"])
    check(await count_runs(pid) >= 1, "the seeded run survives")


async def s7_small_talk_and_publish_guidance(ctx: Ctx) -> None:
    """S7 闲聊/发布引导：answer 形态，无 run 数变化，无 task_book。"""
    pid = await ctx.new_project("S7 small talk")
    await seed_completed_run(pid)
    before = await count_runs(pid)

    turn1 = await ctx.chat(pid, "hello, how is the weather today?")
    check(turn1["run_id"] is None, "small talk starts no run")
    check(no_task_book_dock(turn1["assistant_message"]),
          "small talk never docks a task book")

    turn2 = await ctx.chat(pid, "post this to TikTok for me")
    check(turn2["run_id"] is None, "publish requests start no run from chat")
    check(await count_runs(pid) == before, "run count unchanged", await count_runs(pid))


async def s8_empty_project_visibility(ctx: Ctx) -> None:
    """S8 空项目：建项目不发消息列表不可见；首发消息后可见。"""
    pid = await ctx.new_project("S8 empty project")
    check(pid not in await ctx.listed_project_ids(), "empty shell hidden from the list")

    await ctx.chat(pid, "hi, I have a keynote recording to work with")
    check(pid in await ctx.listed_project_ids(), "first message makes the project visible")


async def s20_anxious_venting_stays_in_scope(ctx: Ctx) -> None:
    """S20 情绪性迷茫（闲聊×迷失）：职业焦虑倾诉——散文回应，永不借情绪出书出 run。"""
    pid = await ctx.new_project("S20 anxious venting")

    # 不做职业/变现咨询（§3.3）的形态座位：情绪倾诉永不转成任务书或 run。
    # 文案层的"引回产品能做的事"无法形态断言，归 W4 人工走查。
    turn1 = await ctx.chat(pid, "AI 时代像我这样的大学老师还有前途吗？说实话我挺焦虑的")
    check(turn1["run_id"] is None, "venting never starts a run", turn1)
    check(no_task_book_dock(turn1["assistant_message"]),
          "venting never docks a task book", turn1["assistant_message"])
    check(has_prose(turn1["assistant_message"]),
          "a prose reply lands", turn1["assistant_message"])

    turn2 = await ctx.chat(pid, "那你说我该怎么办")
    check(turn2["run_id"] is None, "still no run", turn2)
    check(no_task_book_dock(turn2["assistant_message"]),
          "still no task book", turn2["assistant_message"])
    check(has_prose(turn2["assistant_message"]),
          "still a prose reply", turn2["assistant_message"])


# ---- Scenarios: 配方 ----------------------------------------------------------


async def s5_recipe_mention_pin(ctx: Ctx) -> None:
    """S5 recipe mention：用户点名语言赢配方默认；unknown/reserved 422。"""
    pid = await ctx.new_project("S5 recipe mention")
    await seed_asset(pid, ctx.user_id, AssetType.VIDEO, "talk.mp4")
    mentions = [{"type": "recipe", "id": "dub", "label": "Multilingual dub"}]

    turn1 = await ctx.chat(pid, "dub my clips into Chinese please", mentions=mentions)
    check(is_task_book_dock(turn1["assistant_message"]), "turn1 docks a task_book", turn1["assistant_message"])
    book = (await ctx.results(pid)).get("pending_intent")
    check((book["intent"].get("dub_languages") or []) == ["zh"],
          "user-named language wins the recipe default", book["intent"].get("dub_languages"))

    res = await ctx.chat_raw(pid, "again", mentions=[{"type": "recipe", "id": "nope", "label": "nope"}])
    check(res.status_code == 422, "unknown recipe id → 422", res.status_code)
    res = await ctx.chat_raw(pid, "again", mentions=[{"type": "recipe", "id": "reframe", "label": "Reframe"}])
    check(res.status_code == 422, "reserved recipe → 422", res.status_code)


async def s10_dub_language_classification(ctx: Ctx) -> None:
    """S10 dub 归类回归：'dub them into Chinese' → dub_languages=['zh']（用户手测原句）。"""
    pid = await ctx.new_project("S10 dub classification")
    await seed_asset(pid, ctx.user_id, AssetType.VIDEO, "talk.mp4")
    mentions = [{"type": "recipe", "id": "dub", "label": "Multilingual dub"}]

    turn1 = await ctx.chat(
        pid,
        "Cut highlight clips from my talk and dub them into Chinese",
        mentions=mentions,
    )
    check(is_task_book_dock(turn1["assistant_message"]), "turn1 docks a task_book",
          turn1["assistant_message"])
    book = (await ctx.results(pid)).get("pending_intent")
    check((book["intent"].get("dub_languages") or []) == ["zh"],
          "voice-dub language lands in dub_languages, recipe default stays out",
          book["intent"].get("dub_languages"))


async def s11_recipe_clips_without_media_escape(ctx: Ctx) -> None:
    """S11 纯文字稿 + dub 配方：Start 422（缺媒体）→ 去 clips 再 Start 成功（dub 被丢弃）。"""
    pid = await ctx.new_project("S11 clips without media")
    await seed_asset(pid, ctx.user_id, AssetType.TRANSCRIPT, "talk.txt")
    mentions = [{"type": "recipe", "id": "dub", "label": "Multilingual dub"}]

    turn1 = await ctx.chat(pid, "use this recipe on my talk", mentions=mentions)
    check(is_task_book_dock(turn1["assistant_message"]), "turn1 docks a task_book",
          turn1["assistant_message"])
    book = (await ctx.results(pid)).get("pending_intent")
    slots = book_slots(book)
    check(any(s["type"] == "clips" for s in slots),
          "the recipe seed keeps the clips slot (the card's shape)", slots)
    check("clips_without_media" in (book.get("reasons") or []),
          "the no-media warning rides the dock", book.get("reasons"))
    qid = turn1["assistant_message"]["id"]

    res = await ctx.answer(qid, {"kind": "start"})
    check(res.status_code == 422, "Start without media is rejected", res.status_code)
    check((await ctx.results(pid)).get("pending_intent") is not None,
          "the book survives the 422 (dock intact)")

    # The escape the 422 message names: deselect clips in the panel, Start
    # again. The recipe-pinned dub languages must not cause a second 422 —
    # they drop at the run birthplace (vacuous without clips).
    edited = dict(book["intent"])
    edited["outputs"] = [s for s in slots if s["type"] != "clips"]
    res2 = await ctx.answer(qid, {"kind": "start", "intent": edited})
    check(res2.status_code == 200, "re-Start without clips succeeds", res2.text)
    check(res2.json()["answered_question"].get("workflow_run_id"),
          "a run was born", res2.json())

    runs = await ctx.client.get(f"/projects/{pid}/runs")
    run_ctx = runs.json()[0].get("context") or {}
    check(not run_ctx.get("dub_languages"),
          "vacuous dub languages dropped at the birthplace", run_ctx.get("dub_languages"))


async def s22_hesitant_behind_recipe_mention(ctx: Ctx) -> None:
    """S22 迷失点卡（配方×迷失）：犹豫措辞不破 mention 解析——照样播种 dock，默认语言填齐。"""
    pid = await ctx.new_project("S22 hesitant recipe mention")
    await seed_asset(pid, ctx.user_id, AssetType.VIDEO, "talk.mp4")
    mentions = [{"type": "recipe", "id": "dub", "label": "Multilingual dub"}]

    # 配方卡就是迷失用户的答案——犹豫不构成拒绝。mention 解析是确定性的；
    # 用户没点名语言时配方默认填齐（S5 验"点名覆盖"，这里验"没点名填默认"）。
    turn1 = await ctx.chat(pid, "朋友推荐我点这张卡，但我不太懂这些……就按这张卡帮我做吧？",
                           mentions=mentions)
    check(is_task_book_dock(turn1["assistant_message"]),
          "a hesitant mention still docks the seeded book", turn1["assistant_message"])
    book = await pending_book(ctx, pid)
    slots = book_slots(book)
    check(any(s["type"] == "clips" for s in slots),
          "the recipe seed keeps the clips slot", slots)
    check(sorted(((book or {}).get("intent") or {}).get("dub_languages") or []) == ["de", "es", "fr"],
          "unnamed languages fill from the recipe default",
          ((book or {}).get("intent") or {}).get("dub_languages"))


# ---- Scenarios: 素材 ----------------------------------------------------------


async def s12_declared_material_promotes(ctx: Ctx) -> None:
    """S12 素材声明升格："这是我的文字稿：…" → transcript 资产落库 + dock 任务书。"""
    pid = await ctx.new_project("S12 declared material")
    material = (
        "Good morning everyone. Today I want to talk about why European "
        "research institutes struggle to turn conference talks into an "
        "ongoing public presence, and what we can do about it."
    )

    turn1 = await ctx.chat(pid, f"这是我的文字稿：{material}")
    check(is_task_book_dock(turn1["assistant_message"]),
          "declared material docks a task book", turn1["assistant_message"])
    assets = await project_assets(pid)
    transcripts = [a for a in assets if a["type"].endswith("transcript")]
    check(len(transcripts) == 1, "exactly one transcript asset was promoted", assets)
    check(material in (transcripts[0]["extracted_text"] or ""),
          "the asset carries the declared text verbatim",
          (transcripts[0]["extracted_text"] or "")[:80])
    check(transcripts[0]["title"] and transcripts[0]["title"] != "prompt.txt",
          "a human title, never the retired shim name", transcripts[0]["title"])


async def s13_no_material_asks(ctx: Ctx) -> None:
    """S13 零素材反问：无素材声明的 generate 请求 → answer 引导，无 dock 无 run。"""
    pid = await ctx.new_project("S13 no material asks")

    turn1 = await ctx.chat(pid, "帮我做 LinkedIn 内容")
    check(turn1["run_id"] is None, "no run without material", turn1)
    check(not turn1["assistant_message"].get("question"),
          "no task book docks without material", turn1["assistant_message"])
    check(has_prose(turn1["assistant_message"]),
          "an ask-for-material reply lands", turn1["assistant_message"])
    check((await ctx.results(pid)).get("pending_intent") is None,
          "no groundless book is persisted")
    check(await project_assets(pid) == [], "no fake asset was created")


async def s14_bare_pasted_content_promotes(ctx: Ctx) -> None:
    """S14 无声明贴文升格：直接贴一段自己的内容（无"这是我的…"前缀）→ 升格 + dock。"""
    pid = await ctx.new_project("S14 bare pasted content")
    material = (
        "Let me walk you through the three numbers that matter for grid "
        "storage. First, the cost curve: lithium-iron phosphate packs fell "
        "below 60 dollars per kilowatt-hour this spring, and that changes "
        "every procurement model we built the 2030 targets on. Second, the "
        "interconnection queue. Third, capacity-market bidding."
    )

    turn1 = await ctx.chat(pid, material)
    check(is_task_book_dock(turn1["assistant_message"]),
          "bare pasted content docks a task book", turn1["assistant_message"])
    assets = await project_assets(pid)
    check(any(a["type"].endswith("transcript") for a in assets),
          "the pasted content became a transcript asset", assets)


async def s21_lost_and_empty_handed(ctx: Ctx) -> None:
    """S21 迷失且零素材（素材×迷失）：无目标无素材——反问引导不空出书；贴出内容后正常 dock。"""
    pid = await ctx.new_project("S21 lost and empty-handed")

    # S13 契约的迷失变体：无米且无目标，同样永不空出书 / run / 假资产。
    turn1 = await ctx.chat(pid, "我想做自媒体，但完全不知道做什么，也没有什么头绪")
    check(turn1["run_id"] is None, "no run without material or goal", turn1)
    check(not turn1["assistant_message"].get("question"),
          "no task book docks", turn1["assistant_message"])
    check(has_prose(turn1["assistant_message"]),
          "an ask-for-material reply lands", turn1["assistant_message"])
    check((await pending_book(ctx, pid)) is None, "no groundless book is persisted")
    check(await project_assets(pid) == [], "no fake asset was created")

    # 旅程后半：用户贴出自己的文字稿（S14 通路）→ 升格 + dock。
    # G-7 回归座位（2026-08-06 修复）：25 词开场白式短贴文——PlanAgent 曾有
    # 上下文真空（看不见上一轮刚被要素材），系统性误判为非素材（3/3）；
    # recent 对话注入后由 LLM 凭语境判断，此 fixture 保持短贴文锁回归。
    material = (
        "My talk today is about why peer review takes so long, and three "
        "places where the review process actually breaks down."
    )
    turn2 = await ctx.chat(pid, material)
    check(is_task_book_dock(turn2["assistant_message"]),
          "pasted content docks a task book", turn2["assistant_message"])
    assets = await project_assets(pid)
    check(any(a["type"].endswith("transcript") for a in assets),
          "the pasted content became a transcript asset", assets)


# ---- Scenarios: 契约（dock 生命周期 / answer 端点 / 重建） --------------------


async def s23_task_book_bail_and_reopen(ctx: Ctx) -> None:
    """S23 dock Cancel（bail）→ 清 pending_intent 回 draft、不起 run；重开消息正常 re-dock。"""
    pid = await ctx.new_project("S23 bail and reopen")
    await seed_asset(pid, ctx.user_id, AssetType.TRANSCRIPT, "talk.txt",
                     extracted_text="My talk about grid storage.")

    turn1 = await ctx.chat(pid, "write a LinkedIn post from my talk")
    check(is_task_book_dock(turn1["assistant_message"]), "turn1 docks a task_book",
          turn1["assistant_message"])
    qid = turn1["assistant_message"]["id"]

    res = await ctx.answer(qid, {"kind": "bail"})
    check(res.status_code == 200, "bail answers the task book", res.text)
    answered = res.json()["answered_question"]
    check((answered.get("answer") or {}).get("kind") == "bail",
          "answer kind=bail", answered.get("answer"))
    check((await ctx.results(pid)).get("pending_intent") is None,
          "pending_intent cleared on bail")
    check(await count_runs(pid) == 0, "bail starts no run")

    # 重开：prompt 留在会话里，下一轮回到 plan path 正常 dock。
    turn2 = await ctx.chat(pid, "write a LinkedIn post from my talk")
    check(is_task_book_dock(turn2["assistant_message"]), "reopen re-docks a task_book",
          turn2["assistant_message"])
    check(await count_runs(pid) == 0, "still no run")


async def s24_autonomy_review_rides_to_run(ctx: Ctx) -> None:
    """S24 自治档透传：dock Start 带 autonomy=review → run.context.autonomy == 'review'。"""
    pid = await ctx.new_project("S24 autonomy review")
    await seed_asset(pid, ctx.user_id, AssetType.TRANSCRIPT, "talk.txt",
                     extracted_text="My talk about peer review.")

    turn1 = await ctx.chat(pid, "write a LinkedIn post from my talk")
    check(is_task_book_dock(turn1["assistant_message"]), "turn1 docks a task_book",
          turn1["assistant_message"])

    res = await ctx.answer(turn1["assistant_message"]["id"],
                           {"kind": "start", "autonomy": "review"})
    check(res.status_code == 200, "dock Start with the review tier", res.text)
    answered = res.json()["answered_question"]
    check(answered.get("workflow_run_id"), "a run was born", answered)
    runs = await ctx.runs(pid)
    run_ctx = runs[0].get("context") or {}
    check(run_ctx.get("autonomy") == "review",
          "the review tier lands on run.context verbatim", run_ctx)


async def s25_duplicate_answer_409(ctx: Ctx) -> None:
    """S25 一行一答：已答问题再 answer → 409；非问题行 answer → 409。"""
    pid = await ctx.new_project("S25 duplicate answer")
    await seed_asset(pid, ctx.user_id, AssetType.TRANSCRIPT, "talk.txt",
                     extracted_text="My talk about capacity markets.")

    turn1 = await ctx.chat(pid, "write a LinkedIn post from my talk")
    check(is_task_book_dock(turn1["assistant_message"]), "turn1 docks a task_book",
          turn1["assistant_message"])
    qid = turn1["assistant_message"]["id"]

    res = await ctx.answer(qid, {"kind": "bail"})
    check(res.status_code == 200, "the first answer lands", res.text)
    res = await ctx.answer(qid, {"kind": "bail"})
    check(res.status_code == 409, "re-answering is a conflict", res.status_code)

    res = await ctx.answer(turn1["user_message"]["id"], {"kind": "bail"})
    check(res.status_code == 409, "a non-question row rejects answers", res.status_code)


async def s26_pending_question_rebuild(ctx: Ctx) -> None:
    """S26 待决重建零内存态：dock 后 GET conversation 带 pending_question；回答后消失。"""
    pid = await ctx.new_project("S26 pending question rebuild")
    await seed_asset(pid, ctx.user_id, AssetType.TRANSCRIPT, "talk.txt",
                     extracted_text="My talk about interconnection queues.")

    turn1 = await ctx.chat(pid, "write a LinkedIn post from my talk")
    check(is_task_book_dock(turn1["assistant_message"]), "turn1 docks a task_book",
          turn1["assistant_message"])
    qid = turn1["assistant_message"]["id"]

    res = await ctx.conversation(pid)
    check(res.status_code == 200, "the conversation exists after the dock", res.status_code)
    pending = res.json().get("pending_question")
    check(pending is not None and pending["id"] == qid,
          "the docked question rebuilds as pending_question (refresh / cross-device seat)",
          pending)

    res = await ctx.answer(qid, {"kind": "bail"})
    check(res.status_code == 200, "bail answers the book", res.text)
    res = await ctx.conversation(pid)
    check(res.json().get("pending_question") is None,
          "no pending question after the answer", res.json())


async def s27_qa_archive_rows(ctx: Ctx) -> None:
    """S27 QA 入档：re-dock 旧书标 superseded（机器 bail）；start 的书标 kind=start + run id。"""
    pid = await ctx.new_project("S27 qa archive")
    await seed_asset(pid, ctx.user_id, AssetType.TRANSCRIPT, "talk.txt",
                     extracted_text="My talk about lithium cost curves.")

    turn1 = await ctx.chat(pid, "write a LinkedIn post from my talk")
    first_qid = turn1["assistant_message"]["id"]
    turn2 = await ctx.chat(pid, "add a French version too")
    check(is_task_book_dock(turn2["assistant_message"]), "turn2 re-docks",
          turn2["assistant_message"])
    second_qid = turn2["assistant_message"]["id"]

    messages = await ctx.messages(turn2["conversation_id"])
    books = [m for m in messages if (m.get("question") or {}).get("kind") == "task_book"]
    check(len(books) == 2, "both task-book rows stay archived", len(books))
    old = next(b for b in books if b["id"] == first_qid)
    check((old.get("answer") or {}).get("text") == "superseded",
          "the superseded book carries the machine marker", old.get("answer"))

    res = await ctx.answer(second_qid, {"kind": "start"})
    check(res.status_code == 200, "start answers the live book", res.text)
    answered = res.json()["answered_question"]
    check((answered.get("answer") or {}).get("kind") == "start",
          "the confirmed book archives kind=start", answered.get("answer"))
    check(answered.get("workflow_run_id"), "the archive carries the run id", answered)


async def s28_plain_clips_without_media(ctx: Ctx) -> None:
    """S28 无配方 clips 无媒体：纯文字稿要 clips → 排除 clips，或保留但带 clips_without_media 警告。"""
    pid = await ctx.new_project("S28 plain clips no media")
    await seed_asset(pid, ctx.user_id, AssetType.TRANSCRIPT, "talk.txt",
                     extracted_text="My talk about capacity-market bidding.")

    turn1 = await ctx.chat(pid, "cut 3 highlight clips from my talk")
    check(turn1["run_id"] is None, "no run without media", turn1)
    msg = turn1["assistant_message"]
    if is_task_book_dock(msg):
        book = await pending_book(ctx, pid)
        clips = [s for s in book_slots(book) if s["type"] == "clips"]
        check(
            not clips or "clips_without_media" in ((book or {}).get("reasons") or []),
            "clips excluded, or flagged clips_without_media when kept",
            book,
        )
    else:
        check(has_prose(msg), "otherwise a prose reply lands (never a dead end)", msg)


async def s29_count_boundary_422(ctx: Ctx) -> None:
    """S29 出生地 count 边界：手编 clips=11 Start → 422（SLOT_COUNT_LIMITS），书存活。"""
    pid = await ctx.new_project("S29 count boundary")
    await seed_asset(pid, ctx.user_id, AssetType.VIDEO, "talk.mp4")

    turn1 = await ctx.chat(pid, "cut 3 highlight clips from my talk")
    check(is_task_book_dock(turn1["assistant_message"]), "turn1 docks a task_book",
          turn1["assistant_message"])
    book = (await ctx.results(pid)).get("pending_intent")
    qid = turn1["assistant_message"]["id"]

    # 替换或注入 clips 槽位——不依赖 LLM 一定出了 clips 槽。
    edited = dict(book["intent"])
    clips_slot = next((s for s in book_slots(book) if s["type"] == "clips"), None)
    edited["outputs"] = [{**(clips_slot or {"type": "clips"}), "count": 11}]
    res = await ctx.answer(qid, {"kind": "start", "intent": edited})
    check(res.status_code == 422, "an out-of-bounds count rejects at the birthplace",
          res.status_code)
    check("count" in res.text.lower(), "the 422 names the count violation", res.text[:200])
    check((await ctx.results(pid)).get("pending_intent") is not None,
          "the book survives the 422 (dock intact)")


async def s30_attachment_only_send(ctx: Ctx) -> None:
    """S30 attachment-only 发送：空文本 + chip → 消息持久化 attachments；替身行推断，永不死路。"""
    pid = await ctx.new_project("S30 attachment only")
    await seed_asset(pid, ctx.user_id, AssetType.TRANSCRIPT, "talk.txt",
                     extracted_text="My talk about review backlogs.")
    attachments = [{"id": "att-1", "name": "notes.txt", "type": "file",
                    "url": "scenario/notes.txt"}]

    turn1 = await ctx.chat(pid, "", attachments=attachments)
    check(turn1["user_message"]["content"] == "",
          "the blank message persists blank", turn1["user_message"])
    check(len(turn1["user_message"].get("attachments") or []) == 1,
          "the attachment rides the message", turn1["user_message"])
    check(turn1.get("answered_question") is None, "no question to auto-answer", turn1)
    msg1 = turn1["assistant_message"]
    check(is_task_book_dock(msg1) or has_prose(msg1),
          "the stand-in line infers — never a dead end", msg1)

    messages = await ctx.messages(turn1["conversation_id"])
    names = [
        a.get("name")
        for m in messages if m["role"] == "user"
        for a in (m.get("attachments") or [])
    ]
    check("notes.txt" in names, "attachments persist and re-render on refresh", names)


# ---- Scenarios: 四态分派（run 项目 / asset scope） -----------------------------


async def s31_task_list_dispatch_new_run(ctx: Ctx) -> None:
    """S31 四态 task_list 实分派：有 run 项目发新工作请求 → 新 run 出生（真建图）。"""
    # 注（2026-08-06）：ChatIntentAgent 的 task_list-vs-ask 判定存在 LLM 波动
    # （曾见一次把明确工作请求反问成 ask-back，重跑即过）——断言保持严格
    # （起新 run 是契约），波动失败人工判读，不锁文案。
    pid = await ctx.new_project("S31 task_list dispatch")
    await seed_asset(pid, ctx.user_id, AssetType.TRANSCRIPT, "talk.txt",
                     extracted_text="My talk today is about the three numbers that "
                                    "matter for grid storage.")
    await seed_completed_run(pid)

    turn1 = await ctx.chat(pid, "write a LinkedIn post in French from my talk")
    check(no_task_book_dock(turn1["assistant_message"]),
          "never a task book on a run project", turn1["assistant_message"])
    check(turn1["run_id"] is not None, "a task_list run was dispatched", turn1)
    check(await count_runs(pid) == 2, "the new run joins the seeded one",
          await count_runs(pid))


async def s32_edit_ops_dispatch(ctx: Ctx) -> None:
    """S32 edit_ops 实分派：'rename the clip title' → operations 落行（chat 血统 + message_id），不起 run。"""
    pid = await ctx.new_project("S32 edit ops dispatch")
    output_id = await seed_clip_output(pid)
    await seed_completed_run(pid)

    turn1 = await ctx.chat(pid, "Rename the clip's title to 'Q3 Highlights'")
    check(turn1["run_id"] is None, "edit ops never start a run", turn1)
    check(await count_runs(pid) == 1, "run count unchanged", await count_runs(pid))
    ops = await operations_for_output(output_id)
    applied = [o for o in ops if o["op"] != "snapshot"]
    check(len(applied) == 1, "exactly one edit op was applied", ops)
    check(applied[0]["op"] == "set_title", "the title rename landed as set_title", applied)
    check(applied[0]["source"] == "chat", "chat lineage", applied[0])
    check(applied[0]["message_id"] == turn1["assistant_message"]["id"],
          "the op carries the assistant message lineage", applied[0])


async def s33_progress_question_answer(ctx: Ctx) -> None:
    """S33 G-2 进度询问：run 在跑发'到哪了' → answer 形态（无新 run 无 dock），凭节点级上下文答。"""
    pid = await ctx.new_project("S33 progress question")
    await seed_running_run_with_steps(pid)

    turn1 = await ctx.chat(pid, "how is the generation going?")
    check(turn1["run_id"] is None, "a progress question dispatches nothing", turn1)
    check(not turn1["assistant_message"].get("question"),
          "no question docks", turn1["assistant_message"])
    check(has_prose(turn1["assistant_message"]), "a prose progress answer lands")
    check(await count_runs(pid) == 1, "run count unchanged", await count_runs(pid))


async def s34_meta_info_navigation_answer(ctx: Ctx) -> None:
    """S34 M 元信息：'换个人设' → answer 导航形态，不起 run 不 dock。"""
    pid = await ctx.new_project("S34 meta navigation")
    await seed_completed_run(pid)

    turn1 = await ctx.chat(pid, "Can you switch to a different persona for me?")
    check(turn1["run_id"] is None, "meta changes dispatch no run", turn1)
    check(not turn1["assistant_message"].get("question"),
          "no question docks", turn1["assistant_message"])
    check(has_prose(turn1["assistant_message"]), "a guidance answer lands")
    check(await count_runs(pid) == 1, "run count unchanged", await count_runs(pid))


async def s35_asset_scope_never_plan_path(ctx: Ctx) -> None:
    """S35 asset scope 永不进 plan path：单产物会话任何消息都不出 task_book。"""
    pid = await ctx.new_project("S35 asset scope")
    output_id = await seed_clip_output(pid)

    turn1 = await ctx.chat(pid, "make it shorter",
                           asset_id=output_id, asset_type="clip")
    check(no_task_book_dock(turn1["assistant_message"]),
          "no task book from an asset-scoped turn", turn1["assistant_message"])
    res = await ctx.conversation(pid, asset_id=output_id, asset_type="clip")
    check(res.status_code == 200, "the asset conversation exists", res.status_code)
    check(res.json().get("asset_id") == output_id, "scoped to the output", res.json())


# ---- Scenarios: checkpoint（seed parked run，零 LLM） ---------------------------


async def s36_checkpoint_three_answer_paths(ctx: Ctx) -> None:
    """S36 checkpoint 三答法 + 空白不答题：option 按钮 / 打字母 autoResume / 自由文本 —— 答题即唤醒。"""
    # a) 按钮：answer 端点 option。
    pid = await ctx.new_project("S36a option answer")
    ck = await seed_parked_checkpoint(pid, ctx.user_id)
    res = await ctx.answer(ck["question_id"], {"kind": "option", "option_id": "a"})
    check(res.status_code == 200, "the option answer lands", res.text)
    answered = res.json()["answered_question"]
    check((answered.get("answer") or {}).get("kind") == "option",
          "answer kind=option", answered.get("answer"))
    check((answered.get("answer") or {}).get("text") == "Focus: Pricing",
          "the QA archive shows the option's human label", answered.get("answer"))
    node = (await step_rows(ck["run_id"]))[0]
    check(node["status"] != "waiting" and "answer" in node["spec"],
          "the wake is synchronous (spec.answer written, node re-pended)", node)
    check((await run_row(ck["run_id"]))["status"] != "waiting_human",
          "the run left WAITING_HUMAN")
    await wait_run_status(ck["run_id"], {"completed"})
    await ctx.cleanup()

    # b) 打字母：/chat autoResume（零 LLM）。
    pid = await ctx.new_project("S36b typed letter")
    ck = await seed_parked_checkpoint(pid, ctx.user_id)
    turn = await ctx.chat(pid, "a")
    aq = turn.get("answered_question")
    check(aq is not None and aq["id"] == ck["question_id"],
          "the typed letter auto-resumed the checkpoint", turn)
    check((aq.get("answer") or {}).get("kind") == "option", "the letter maps to an option",
          aq.get("answer"))
    await wait_run_status(ck["run_id"], {"completed"})
    await ctx.cleanup()

    # c) 自由文本：allow_freeform → freeform。
    pid = await ctx.new_project("S36c freeform")
    ck = await seed_parked_checkpoint(pid, ctx.user_id)
    turn = await ctx.chat(pid, "focus on the pricing argument")
    aq = turn.get("answered_question")
    check(aq is not None and aq["id"] == ck["question_id"],
          "freeform auto-resumes (allow_freeform)", turn)
    check((aq.get("answer") or {}).get("kind") == "freeform", "answer kind=freeform",
          aq.get("answer"))
    await wait_run_status(ck["run_id"], {"completed"})
    await ctx.cleanup()

    # d) 空白 attachment-only 永不 auto-answer（K6）。
    pid = await ctx.new_project("S36d blank never answers")
    ck = await seed_parked_checkpoint(pid, ctx.user_id)
    turn = await ctx.chat(
        pid, "", attachments=[{"id": "att-1", "name": "notes.txt", "type": "file"}]
    )
    check(turn.get("answered_question") is None,
          "a blank attachment-only turn never answers a checkpoint", turn)
    q = await message_row(ck["question_id"])
    check(q.get("answer") is None or (q["answer"] or {}).get("text") == "superseded",
          "the checkpoint was not auto-answered (a new docked question superseding "
          "it is the designed cascade)", q.get("answer"))


async def s37_checkpoint_bail_cascade(ctx: Ctx) -> None:
    """S37 checkpoint 弃跑：bail → 节点 done(bailed) + 下游级联 skipped + run COMPLETED（永不 failed）。"""
    pid = await ctx.new_project("S37 checkpoint bail")
    ck = await seed_parked_checkpoint(pid, ctx.user_id, with_downstream=True)

    res = await ctx.answer(ck["question_id"], {"kind": "bail"})
    check(res.status_code == 200, "bail lands", res.text)
    steps = {s["id"]: s for s in await step_rows(ck["run_id"])}
    node = steps[ck["node_id"]]
    check(node["status"] == "done" and node["spec"].get("bailed") is True,
          "the checkpoint settles done with spec.bailed", node)
    child = steps[ck["child_id"]]
    check(child["status"] == "skipped" and child["error"] == "user bailed",
          "the downstream cascade-skips with the non-failure reason", child)
    run = await run_row(ck["run_id"])
    check(run["status"] == "completed",
          "the bailed run settles COMPLETED, never failed", run["status"])


async def s38_new_question_cascade_bails_parked_run(ctx: Ctx) -> None:
    """S38 多 run 不搁浅：新题 supersede 开口 checkpoint 题 → 同笔级联 bail 那个 run，收官 COMPLETED。"""
    from app.chat.service import (  # noqa: PLC0415 — scenario-local, like service.py
        dock_checkpoint_question,
        finalize_bailed_runs,
    )

    pid = await ctx.new_project("S38 supersede cascade")
    ck1 = await seed_parked_checkpoint(pid, ctx.user_id)

    # 第二个 run 的 checkpoint 到题——走 run_checkpoint 的真实函数（runner 到题
    # 就是调 dock_checkpoint_question），单待决不变量同笔级联 bail 第一个 run。
    options = [
        {"id": "a", "label": "Focus: Pricing", "argument_id": "arg-1"},
        {"id": "b", "label": "Full-talk highlights", "argument_id": None},
    ]
    async with AsyncSessionLocal() as db:
        run2 = WorkflowRun(
            project_id=uuid.UUID(pid),
            status=WorkflowStatus.WAITING_HUMAN,
            context={"outputs": [{"type": "post"}], "autonomy": "review"},
        )
        db.add(run2)
        await db.flush()
        node2 = WorkflowStep(
            run_id=run2.id, kind="checkpoint", status="waiting", seq=1,
            started_at=datetime.now(UTC),
        )
        db.add(node2)
        await db.flush()
        message, bailed = await dock_checkpoint_question(
            db, ctx.user_id, uuid.UUID(pid), run2.id,
            "Which direction should this run focus on?",
            AskPayload(
                kind="choice",
                options=[AskOption(id=o["id"], label=o["label"]) for o in options],
                allow_freeform=True,
            ),
        )
        node2.spec = {
            "suspend_payload": {
                "question_message_id": str(message.id),
                "options": options,
            }
        }
        await db.commit()
        q2_id = str(message.id)
    check([str(r) for r in bailed] == [ck1["run_id"]],
          "run1 was cascade-bailed in the same stroke", bailed)
    await finalize_bailed_runs(list(bailed))

    q1 = await message_row(ck1["question_id"])
    check((q1.get("answer") or {}).get("text") == "superseded",
          "the old question retires as superseded", q1.get("answer"))
    node1 = (await step_rows(ck1["run_id"]))[0]
    check(node1["status"] == "done" and node1["spec"].get("bailed") is True,
          "run1's checkpoint cascade-bailed", node1)
    check((await run_row(ck1["run_id"]))["status"] == "completed",
          "run1 settles COMPLETED — never stranded")
    q2 = await message_row(q2_id)
    check(q2.get("answer") is None, "the new question is the live pending one", q2)


async def s39_checkpoint_expiry_sweep(ctx: Ctx) -> None:
    """S39 checkpoint 过期：park 超 TTL → 扫描以默认项 auto-answer（标 expired）+ 唤醒续跑收官。"""
    from app.pipeline.orchestrator import expire_stale_checkpoints  # noqa: PLC0415

    pid = await ctx.new_project("S39 checkpoint expiry")
    ck = await seed_parked_checkpoint(pid, ctx.user_id, parked_hours_ago=2)

    expired = await expire_stale_checkpoints(older_than=timedelta(hours=1))
    check(expired >= 1, "the sweep expired at least our checkpoint", expired)
    q = await message_row(ck["question_id"])
    check((q.get("answer") or {}).get("text") == "expired",
          "the auto-answer carries the machine marker", q.get("answer"))
    check((q.get("answer") or {}).get("option_id") == "c",
          "the default option (argument_id None) answers", q.get("answer"))
    node = (await step_rows(ck["run_id"]))[0]
    check(node["status"] != "waiting", "the run was woken", node)
    await wait_run_status(ck["run_id"], {"completed"})


async def s40_task_book_never_auto_resumes(ctx: Ctx) -> None:
    """S40 task_book 不参与 autoResume（简报禁令 #6）：dock 待决时打"a" → 永不当选项答掉。"""
    pid = await ctx.new_project("S40 task_book no autoResume")
    await seed_asset(pid, ctx.user_id, AssetType.TRANSCRIPT, "talk.txt",
                     extracted_text="My talk about storage auctions.")

    turn1 = await ctx.chat(pid, "write a LinkedIn post from my talk")
    check(is_task_book_dock(turn1["assistant_message"]), "turn1 docks a task_book",
          turn1["assistant_message"])
    qid = turn1["assistant_message"]["id"]

    turn2 = await ctx.chat(pid, "a")
    check(turn2.get("answered_question") is None,
          "a typed letter never auto-answers a task_book", turn2)
    q = await message_row(qid)
    check(q.get("answer") is None or (q["answer"] or {}).get("text") == "superseded",
          "the book stays pending or is superseded by a re-dock — never letter-answered",
          q.get("answer"))


# ---- Scenarios: 流式 ----------------------------------------------------------


async def s9_sse_turn_streaming(ctx: Ctx) -> None:
    """S9 SSE 回合：answer 流式（delta 拼接 == 信封散文）；generate 流计划复述（== intent.answer）。"""
    pid = await ctx.new_project("S9 sse streaming")
    await seed_asset(pid, ctx.user_id, AssetType.VIDEO, "keynote.mp4")

    # Answer turn: prose previews stream, and concatenated deltas must equal
    # the envelope's persisted content (preview channel == source of truth).
    # The phrasing mirrors the system prompt's few-shot example verbatim —
    # the answer/generate judgment is LLM variance, and the strict concat
    # assertion below needs the answer verdict to be near-deterministic.
    deltas, completed, failed = await ctx.chat_stream(pid, "what can you generate?")
    check(failed is None, "answer turn has no turn.failed", failed)
    check(completed is not None, "answer turn ends with turn.completed")
    content = (completed["assistant_message"].get("content") or "")
    check(len(deltas) > 0, "answer turn streams prose deltas")
    check("".join(deltas) == content, "delta concat == envelope content",
          f"{''.join(deltas)!r} vs {content!r}")
    check(completed["run_id"] is None, "answer turn starts no run")

    # Generate turn: the plan echo (intent.answer) streams as deltas and is
    # persisted in the pending intent; the dock rides the envelope.
    deltas, completed, failed = await ctx.chat_stream(
        pid, "Cut 3 highlight clips from my talk"
    )
    check(failed is None, "generate turn has no turn.failed", failed)
    check(completed is not None, "generate turn ends with turn.completed")
    check(is_task_book_dock(completed["assistant_message"]),
          "generate turn docks the task book via the envelope",
          completed["assistant_message"])
    book = (await ctx.results(pid)).get("pending_intent")
    echo = (book["intent"].get("answer") or "")
    check(len(deltas) > 0, "generate turn streams the plan echo")
    check("".join(deltas) == echo, "echo deltas == persisted intent.answer",
          f"{''.join(deltas)!r} vs {echo!r}")


# ---- Scenarios: harness 漏斗 -------------------------------------------------


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


async def s41_repair_one_bounded_round(ctx: Ctx) -> None:
    """S41 repair 只一轮：schema 拒绝 → 第二轮带结构化回显；再拒即败无第三轮；transport 不修。"""
    del ctx  # in-process funnel self-check — no API, no DB rows

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


SCENARIOS = {
    # 首轮路由
    "S1": s1_vague_first_turn_then_prose_start,
    "S2": s2_explicit_first_turn_then_dock_start,
    "S17": s17_lost_first_turn_journey,
    # 能力咨询
    "S4": s4_capability_question_then_baseless_start,
    "S18": s18_lost_capability_consult,
    # 修订
    "S3": s3_refinement_loop,
    "S19": s19_inarticulate_revision,
    "S15": s15_recipe_refine_count,
    "S16": s16_panel_edit_three_way,
    # 边界
    "S6": s6_followup_after_run_stays_off_plan_path,
    "S7": s7_small_talk_and_publish_guidance,
    "S8": s8_empty_project_visibility,
    "S20": s20_anxious_venting_stays_in_scope,
    # 配方
    "S5": s5_recipe_mention_pin,
    "S10": s10_dub_language_classification,
    "S11": s11_recipe_clips_without_media_escape,
    "S22": s22_hesitant_behind_recipe_mention,
    # 素材
    "S12": s12_declared_material_promotes,
    "S13": s13_no_material_asks,
    "S14": s14_bare_pasted_content_promotes,
    "S21": s21_lost_and_empty_handed,
    # 契约（dock 生命周期 / answer 端点 / 重建 / 附件）
    "S23": s23_task_book_bail_and_reopen,
    "S24": s24_autonomy_review_rides_to_run,
    "S25": s25_duplicate_answer_409,
    "S26": s26_pending_question_rebuild,
    "S27": s27_qa_archive_rows,
    "S28": s28_plain_clips_without_media,
    "S29": s29_count_boundary_422,
    "S30": s30_attachment_only_send,
    # 四态分派
    "S31": s31_task_list_dispatch_new_run,
    "S32": s32_edit_ops_dispatch,
    "S33": s33_progress_question_answer,
    "S34": s34_meta_info_navigation_answer,
    "S35": s35_asset_scope_never_plan_path,
    # checkpoint
    "S36": s36_checkpoint_three_answer_paths,
    "S37": s37_checkpoint_bail_cascade,
    "S38": s38_new_question_cascade_bails_parked_run,
    "S39": s39_checkpoint_expiry_sweep,
    "S40": s40_task_book_never_auto_resumes,
    # 流式
    "S9": s9_sse_turn_streaming,
    # harness 漏斗
    "S41": s41_repair_one_bounded_round,
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
