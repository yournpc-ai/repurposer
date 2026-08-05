"""chat_scenarios.py — preset multi-turn acceptance scripts for the intent layer.

The intent-surface-unification acceptance harness (brief
``docs/tasks/intent-surface-unification.md`` W6): preset multi-turn
scripts (S1–S11) drive a LIVE API through the only intent surface
(``POST /chat`` + the answer endpoint) and assert SHAPE-level outcomes per
turn — proposal state, dock state, run count, archived rows, SSE frame
sequence — never LLM wording (prohibition #7: no copy assertions).

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
from pathlib import Path

# Make ``app`` importable when run as a file (apps/api on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.tables import Asset, User, WorkflowRun  # noqa: E402
from app.models.schemas import AssetType, WorkflowStatus  # noqa: E402
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

    async def results(self, pid: str) -> dict:
        res = await self.client.get(f"/projects/{pid}/results")
        check(res.status_code == 200, "GET results", res.text)
        return res.json()

    async def listed_project_ids(self) -> set[str]:
        res = await self.client.get("/projects")
        check(res.status_code == 200, "GET /projects", res.text)
        return {p["id"] for p in res.json()}

    async def cleanup(self) -> None:
        if self.keep:
            return
        for pid in self.project_ids:
            await self.client.delete(f"/projects/{pid}")


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


async def seed_asset(pid: str, user_id: uuid.UUID, type_: AssetType, filename: str) -> None:
    """A fake file-backed asset row — enough for the clips-media gate and the
    plan agent's filename context; the bytes never exist."""
    async with AsyncSessionLocal() as db:
        db.add(
            Asset(
                user_id=user_id,
                project_id=uuid.UUID(pid),
                type=type_,
                file_url=f"scenario/{filename}",
                title=filename,
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


async def count_runs(pid: str) -> int:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(WorkflowRun.id).where(WorkflowRun.project_id == uuid.UUID(pid))
            )
        ).all()
        return len(rows)


# ---- Assertion helpers ------------------------------------------------------


def is_task_book_dock(msg: dict) -> bool:
    return bool(msg.get("question")) and msg["question"].get("kind") == "task_book" and not msg.get("answer")


def book_slots(book: dict) -> list[dict]:
    return ((book or {}).get("intent") or {}).get("outputs") or []


# ---- Scenarios ---------------------------------------------------------------


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


async def s4_capability_question_then_baseless_start(ctx: Ctx) -> None:
    """S4 能力提问 → 纯 answer（无 dock 无 run）；无书“start it”不死路不起 run。"""
    pid = await ctx.new_project("S4 capability question")

    turn1 = await ctx.chat(pid, "what can you do?")
    check(turn1["run_id"] is None, "capability question starts no run")
    check(not turn1["assistant_message"].get("question"), "no question docks", turn1["assistant_message"])
    check(bool((turn1["assistant_message"].get("content") or "").strip()), "a prose answer lands")

    turn2 = await ctx.chat(pid, "start it")
    check(turn2["run_id"] is None, "a baseless start never launches a run", turn2)


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
    res = await ctx.chat_raw(pid, "again", mentions=[{"type": "recipe", "id": "style", "label": "Style"}])
    check(res.status_code == 422, "reserved recipe → 422", res.status_code)


async def s6_followup_after_run_stays_off_plan_path(ctx: Ctx) -> None:
    """S6 完成后追问：plan path 不抢已有 run 的项目（无 task_book dock）。"""
    pid = await ctx.new_project("S6 post-run followup")
    await seed_completed_run(pid)

    turn1 = await ctx.chat(pid, "translate the second clip into French")
    check(turn1["assistant_message"].get("question", {}).get("kind") != "task_book"
          if turn1["assistant_message"].get("question") else True,
          "no task_book dock on a project with runs", turn1["assistant_message"])
    check(await count_runs(pid) >= 1, "the seeded run survives")


async def s7_small_talk_and_publish_guidance(ctx: Ctx) -> None:
    """S7 闲聊/发布引导：answer 形态，无 run 数变化，无 task_book。"""
    pid = await ctx.new_project("S7 small talk")
    await seed_completed_run(pid)
    before = await count_runs(pid)

    turn1 = await ctx.chat(pid, "hello, how is the weather today?")
    check(turn1["run_id"] is None, "small talk starts no run")
    check(turn1["assistant_message"].get("question", {}).get("kind") != "task_book"
          if turn1["assistant_message"].get("question") else True,
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
    check(bool((turn1["assistant_message"].get("content") or "").strip()),
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


SCENARIOS = {
    "S1": s1_vague_first_turn_then_prose_start,
    "S2": s2_explicit_first_turn_then_dock_start,
    "S3": s3_refinement_loop,
    "S4": s4_capability_question_then_baseless_start,
    "S5": s5_recipe_mention_pin,
    "S6": s6_followup_after_run_stays_off_plan_path,
    "S7": s7_small_talk_and_publish_guidance,
    "S8": s8_empty_project_visibility,
    "S9": s9_sse_turn_streaming,
    "S10": s10_dub_language_classification,
    "S11": s11_recipe_clips_without_media_escape,
    "S12": s12_declared_material_promotes,
    "S13": s13_no_material_asks,
    "S14": s14_bare_pasted_content_promotes,
    "S15": s15_recipe_refine_count,
    "S16": s16_panel_edit_three_way,
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
