"""chat_scenarios.py — 剧本测试：预设多轮剧本对活 API 跑形态级断言。

不是 harness（harness 单义 = 调用面 Agent 漏斗，NAMING N-48），也不是"测试
套件"（scripts/ 下的剧本测试脚本，不配概念名——去方言批禁令）。剧本驱动
活 API 的唯一意图表面（``POST /chat`` + answer 端点），断言 = **工具序列 +
终态帧消息**（ADR-077 判词② 工具 loop 线格式）：terminal_tool_of 从终态
信封的形状判别回合收在哪个终态工具（工具名永不过线，简报 §3——信封形状
就是判别面）。永不锁 LLM 文案（禁令 #7）。例外：代码强制文本（提醒尾 /
机器标记 / 确定性回执）可以锁——那是代码，不是 LLM。

测试体系收敛（ADR-114，施工合同 ``docs/tasks/test-suite-convergence.md``
§3）：41 本 → **用户旅程矩阵**（旧 S 号两次作废重排；S11 = MG 批新增旅程座）。
每本 = 一种用户 × 一种创作流 × 全旅程；机制不立独立剧本。harness
公共断言每本自动携带（见下「harness 公共断言」）；进程内纯函数矩阵
（materialize 注入 / merge_brief 来源 / transcript 数组序）已下沉 tests/
（test_cut_segments_pure / test_brief_pure / test_activity_pure）。

    S1  迷失用户全旅程：裸愿望 → 主题问 → 作答（自由文本 + 选项点选两路）
             / 跳过 → draft-from-persona 计划 → dock → 口头确认 → start_run
             → run（途中锁待决重建 / 一行一答 409 / 选项点选不 500 /
             draft 图横切 / lifecycle stamp 三拍）
    S2  素材→短片全链：真字节素材 → 方向问 → 途中插话（提醒尾 + pending
             保持 + 下轮回填）→ clips 计划 → 计划期修订（面板钉存活 /
             chat 恒胜 / supersede / fill-key 幂等 / 打字母不答）→ 确认 →
             run completed + 产物落库 → 触发回合 reviewer → chat 修订
             wiring 横切（同 id 原地改写无双生 → 子图重跑）→ 扩张 dock
             （新付费工作确认门 + 点名工作直达入口变体）
    S3  素材→建议→探索：方向建议选项 dock → 发现型目标（SSE）→ 探索三族
             出生（一条 journey）→ 决策包 dock（plans + 编译链 + quote）
             → Start → confirmed_scope 快照 → 产物落地 + 确定性尾
             （执行门拒收 / 幂等重放 / 无时间轴降级 / 图面车道律）
    S4  无素材→图文：写手族（post / quotes / carousel）无素材直生 +
             caption_mode 默认吸收三拍（默认 source_only / 用户原话恒胜 /
             设定经修订与面板 Start 存活）
    S5  调研→写作：research 全链（活 DDG；网络全灭时 caveat 降级也算过）
    S6  纯咨询不死路：能力问 / 闲聊 / 无根 "start it" → 纯 answer 终态，
             零计划零 dock 零 run；浏览问永不两级跳劫持
    S7  修订第二圈：落地 clip → 精确编辑（remove_range / set_caption_style
             两族实应用）→ 同 id 无双生 → undo → 归档生命周期（409 墙 /
             换态 / 读面跟随）
    S8  访谈→分镜：访谈 fixture 真处理 → 口头选定分镜方向 → 链必含
             select_clips + reframe_clip → run completed → render_spec
             带 crop_track
    S9  付费边界：余额不足 → typed Start 与 /generate 双路 422 同形同义
             + 不可证载荷 scope.unproven + 台账零行 + 负余额 hold 必拒 +
             活跃 run Start 阻断
    S10 Remix 旗舰：P1 warm 路径（@mention pin → 拆解即说话）+ P2 run
             路径（真链 → decompile 新鲜物化 → 产物参数 = 骨架 → 画布无
             decompile 孤儿）
    S11 贴链成片全旅程（MG）：URL → web_page 资产真采集 → 分镜方案 dock
             （launch_film）→ 守卫线口头 yes → 真渲染 + probe 闸 → film
             产物 COMPLETED + 画布血缘 + 台账 hold=capture+release
    S12 网站旅程入口变体（轻本）：裸求片先问链接（永不盲 dock
             launch_film）→ 讨论链接先 get_web_page 读页再答（读帧 key
             为观测面）→ discussion 链接永不资产化（负形）→ 讨论后拍板
             做片：历史回合的链接 verbatim 入 material_urls（永不追问
             对话已有的链接），链带 launch_film + 本回合诞生 web_page
             资产（正形）；auto 档两形皆合法——dock 待确认或同回合
             propose→start_run（分镜核对 hold 在 run 内 checkpoint）

harness 公共断言（ADR-114 §3.2——每本自动携带，不再单独立本）：

- **SSE 工具 loop 线格式**（``Ctx.chat_stream`` 自动）：concat(deltas) ==
  信封散文；读先 startswith 前缀律；拒轮方差注记（repair 帧出现即豁免，
  被拒迭代的言语是被替换的）；文字问 / 选项问的合成枝分流（选项问
  content == 框架散文，文字问 content == 散文 + 空行 + 裸问题）。
- **Activity 帧形态**（自动）：白名单字段 / 用户语义 kind / seq 严增 /
  翻转律（active 出生、终态唯一、completed 换过去时键）/ T16-B 信封
  清扫——Activity 是工作证据唯一座位（Phase 3 Batch B 后相位帧不再
  承载工作证据）。
- **question.preview 预览帧**（选项问 dock 自动）：预览与 dock 载荷
  逐字段一致（裸问题 / 选项 / slot / allow_freeform / default_path）。
- **dock 形态**（``Ctx.chat`` 与 ``chat_stream`` 自动）：task_book 自完备
  （链随 intent 列 + derived 列表 + estimate_credits 良构——Σ per_task ≡
  total 对账律）；选项问结构律（1–3 选项 / label ≤40 / recommended 至多
  其一 / 载荷永不携带执行参数的负形 lint）。default_path 恒在律归各
  旅程的场景级断言（ask 家族专属，不进 harness——trigger dock 是另一族）。
- **估价三断言 + repair 只一轮**（runner 每本开跑前自动，进程内零 LLM）：
  fold 对账 / 报价单调性（子图 ≤ 全图，非负）/ NULL 语义 + Agent 漏斗
  stub 探针（schema 拒收 → 恰一轮修复 / 二次拒收即失败 / 传输故障不修复 /
  fallback 宣言 / repair_feedback 首轮骑缝 / 流式首试拒轮走非流式 /
  media 降级与修复的组合律）。

LLM 方差口径：凡锁定的是**设计行为**（裸愿望先问主题 / 插话不结算 / 提醒尾
必在 / 判定回答必结算），红了 = prompt 或判定回归信号，不是剧本松劲。flake
处置（合同 §3.6）：断言只锁形态；红先归因机制（pre-批面复跑分水岭纪律），
禁调断言放行；矩阵内任何本连续两次同类方差红 → 登记 PROGRESS 需求池。

fixture 纪律：源片一律先拷 ``scenario/`` 前缀（delete_project 会 unlink
外部共享 key——S16 的课）；真字节素材显式声明 processing_requested_at
（ADR-102 休眠律：无盖章 = worker 永不认领——fixture 自证比等盖章口
确定）；常驻 worker 抢跑律（手工验证前后清数据；改 pipeline 代码必须
重启 worker）。S2/S3/S8/S10 起的 run 是真的（worker 真执行 + MiniMax
配额是硬前提）；每本结束删项目（``--keep`` 例外）。

Usage (from apps/api/, API running on :8000):
    uv run python scripts/chat_scenarios.py                 # all scenarios
    uv run python scripts/chat_scenarios.py --only S1,S5    # subset
    uv run python scripts/chat_scenarios.py --keep          # keep projects
    SCENARIO_API_BASE=http://127.0.0.1:8000/api/v1 uv run python scripts/chat_scenarios.py
"""

import argparse
import asyncio
import itertools
import json
import os
import re
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

# Make ``app`` importable when run as a file (apps/api on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from sqlalchemy import delete, func, select, update  # noqa: E402

from app.agents.base import Agent, StreamingAgent  # noqa: E402
from app.providers.llm.base import LLMError, LLMSchemaError  # noqa: E402
from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.schemas import MediaInput, TaskItem  # noqa: E402
from app.pipeline.graph import NODE_KINDS, fold_estimates  # noqa: E402
from app.pipeline.orchestrator import (  # noqa: E402
    TaskSpec,
    assert_runners_registered,
    compile_graph,
    maybe_finalize_run,
)
from app.models.tables import (  # noqa: E402
    Asset,
    CreditTransaction,
    GraphNode,
    Journey,
    Message,
    Operation,
    Output,
    Project,
    User,
    Wallet,
    WorkflowRun,
    WorkflowStep,
    now_utc,
)
from app.models.schemas import (  # noqa: E402
    AssetStatus,
    AssetType,
    MaterialUnderstanding,
    RenderStatus,
    WorkflowStatus,
)
from app.platform.auth import create_access_token  # noqa: E402
from app.platform.billing import (  # noqa: E402
    CreditsInsufficientError,
    check_hold,
    get_or_create_wallet,
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
    # ADR-085 checkpoint frames: each entry is one checkpoint's full text.
    checkpoints: list[str]
    # Parallel to checkpoints: True = the frame arrived BEFORE any read
    # activity settled — the waiter seat (ADR-104: pre-read speech is legal
    # waiter talk; with the pre-execute emission seat the wire order makes
    # the discrimination exact — a waiter strictly precedes its read's
    # settle frame, result talk strictly follows its predecessor read's
    # settle).
    checkpoints_pre_read: list[bool]
    # ADR-087 §3 activity frames: the append-oriented work stream — each
    # entry is one assistant.activity payload {activity_id, seq, kind,
    # status, key}.
    activities: list[dict]
    # Every data frame as {event, data} in ARRIVAL order — the per-type
    # lists lose the cross-type order, and the ordering is the forensic
    # surface for stream-law failures.
    raw_events: list[dict]
    # Transcript array mirror (ADR-108 §3): the assistant.row.append /
    # assistant.row.update frames in arrival order — append fixes a row's
    # array position, update mutates it in place.
    row_events: list[dict]


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
        turn = res.json()
        # harness 公共断言（dock 形态——每个回合信封自动携带）。
        check_dock_shape(turn.get("assistant_message") or {}, f"/chat {message[:30]!r}")
        return turn

    async def chat_stream(self, pid: str, message: str, **extra: object) -> "StreamTurn":
        """One SSE chat turn (Accept: text/event-stream) — the FULL frame
        record: ordered prose deltas, the assistant.thinking phase frames,
        the question.preview frames (pre-execution, rolled back on a flip),
        the turn.completed envelope, and turn.failed if any.

        harness 公共断言（ADR-114 §3.2）在回合成功收官时自动携带：SSE 线
        格式律 / Activity 帧形态 / checkpoint 形态 / 选项问预览帧律 /
        dock 形态。"""
        deltas: list[str] = []
        thinking: list[dict] = []
        previews: list[dict] = []
        checkpoints: list[str] = []
        checkpoints_pre_read: list[bool] = []
        activities: list[dict] = []
        raw_events: list[dict] = []
        row_events: list[dict] = []
        read_settled_seen = False
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
                    raw_events.append({"event": event, "data": payload})
                    if event == "assistant.delta":
                        deltas.append(payload["text"])
                    elif event == "assistant.thinking":
                        thinking.append(payload)
                    elif event == "question.preview":
                        previews.append(payload)
                    elif event == "assistant.checkpoint":
                        checkpoints.append(payload["text"])
                        checkpoints_pre_read.append(not read_settled_seen)
                    elif event == "assistant.activity":
                        activities.append(payload)
                        if payload.get("kind") == "read" and payload.get(
                            "status"
                        ) in ("completed", "failed", "cancelled"):
                            read_settled_seen = True
                    elif event == "assistant.row.append":
                        row_events.append({"op": "append", **payload})
                    elif event == "assistant.row.update":
                        row_events.append({"op": "update", **payload})
                    elif event == "turn.completed":
                        completed = payload
                    elif event == "turn.failed":
                        failed = payload
        turn = StreamTurn(
            deltas=deltas,
            thinking=thinking,
            previews=previews,
            completed=completed,
            failed=failed,
            checkpoints=checkpoints,
            checkpoints_pre_read=checkpoints_pre_read,
            activities=activities,
            raw_events=raw_events,
            row_events=row_events,
        )
        if completed is not None and failed is None:
            check_turn_stream_laws(turn, f"/chat stream {message[:30]!r}")
        return turn

    async def answer(self, question_id: str, body: dict) -> httpx.Response:
        return await self.client.post(f"/chat/messages/{question_id}/answer", json=body)

    async def set_confirmation(self, *, execution: str, credits: str) -> None:
        """ADR-117 D1: pin the turn's confirmation regime for the journey
        (PUT /auth/settings one-key merge — each leg explicit, never a
        partial assumption)."""
        res = await self.client.put(
            "/auth/settings",
            json={"confirm_execution": execution, "confirm_credits": credits},
        )
        check(res.status_code == 200, "PUT /auth/settings", res.text)
        body = res.json()
        check(
            body.get("confirm_execution") == execution
            and body.get("confirm_credits") == credits,
            "the settings echo the stamped prefs",
            body,
        )

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
    request_processing: bool = False,
) -> str:
    """A fake file-backed asset row — enough for the clips-media gate and the
    intent router's filename context; the bytes never exist. ``extracted_text``
    satisfies the "transcript" required-input check (registry requires).
    ``meta`` carries e.g. the ASR-detected ``language`` the plan context
    surfaces for transform-target decisions. ``processed`` stamps the row
    COMPLETED (the declared-material promotion's end state) — the worker's
    asset queue then never touches the fake bytes (writer chains).
    ``file_url`` points at a REAL bucket object (demo-bucket fixtures — the
    worker really processes a PENDING one). ``status`` overrides the derived
    state (S10's FAILED exemplar — the warm never fires for it).
    ``request_processing`` stamps ``processing_requested_at`` — the ADR-102
    dormant law's claim gate: without it a real-bytes PENDING row sleeps
    forever (the worker only claims stamped rows; the scenario's own fixture
    must declare the request, not wait for a chat-side stamp seat).
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
            processing_requested_at=(
                now_utc() if request_processing and not processed and status is None else None
            ),
        )
        db.add(asset)
        await db.flush()
        asset_id = str(asset.id)
        await db.commit()
        return asset_id


async def seed_understanding(pid: str) -> None:
    """A content-addressed material_understanding row (ADR-083's assemble-time
    injection data face): the digest is computed from the project's live asset
    rows with the pipeline's own ``asset_digest``, so the plan turn's reuse
    lookup hits exactly as an upload-time warm row would."""
    from app.pipeline.step_context import asset_digest

    async with AsyncSessionLocal() as db:
        assets = list(
            (
                await db.execute(
                    select(Asset)
                    .where(Asset.project_id == uuid.UUID(pid))
                    .order_by(Asset.created_at)
                )
            )
            .scalars()
            .all()
        )
        check(bool(assets), "seed_understanding needs the asset seeded first")
        understanding = MaterialUnderstanding(
            overall_summary=(
                "A keynote on urban heat: cities are getting hotter, and "
                "shade trees plus reflective roofs can cool whole "
                "neighborhoods by several degrees."
            ),
            core_thesis=(
                "Neighborhood cooling through shade trees and reflective "
                "surfaces is the cheapest climate adaptation a city can buy."
            ),
            themes=[
                "urban heat",
                "neighborhood cooling",
                "shade trees",
                "reflective roofs",
            ],
            target_audience="city planners and residents",
        )
        db.add(
            Output(
                project_id=uuid.UUID(pid),
                type="material_understanding",
                language="en",
                source_ref={"asset_hash": asset_digest(assets), "warmed": True},
                payload=understanding.model_dump(mode="json"),
            )
        )
        await db.commit()


async def seed_completed_run(pid: str) -> None:
    """A settled run row — the plan path must never claim a project that has
    runs (the chat-path caption gate's phase seat, S4)."""
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
    (S4) derives off it."""
    async with AsyncSessionLocal() as db:
        project = await db.get(Project, uuid.UUID(pid))
        project.language = language
        await db.commit()


async def topup_wallet(user_id: uuid.UUID, amount: int = 200000) -> None:
    """Real runs burn real credits — top the scenario wallet up so the
    journey asserts its own flow, not a 422 (S2/S3/S8/S10)."""
    async with AsyncSessionLocal() as db:
        wallet = await get_or_create_wallet(db, user_id)
        wallet.balance = int(wallet.balance) + amount
        await db.commit()


async def wait_run_terminal(run_id: str, timeout: float = 90.0) -> str:
    """Poll a run to a terminal state (fixture runs fail fast at preprocess —
    scenario/ bytes never exist). Stray-run retry loops must settle a
    wrong-tool run before the next turn, or the active-run guard eats it."""
    terminal = {WorkflowStatus.COMPLETED, WorkflowStatus.FAILED}
    for _ in range(int(timeout / 2)):
        async with AsyncSessionLocal() as db:
            run = await db.get(WorkflowRun, uuid.UUID(run_id))
            if run is not None and run.status in terminal:
                return str(run.status)
        await asyncio.sleep(2)
    return "TIMEOUT"


async def seed_active_run(pid: str) -> str:
    """An authority-holding run: RUNNING + one inert ``running`` node. The
    claim loop only takes ``pending`` rows and the per-tick reap (900s)
    never fires inside a scenario, so the row holds the project's execution
    authority until ``settle_seeded_run`` ends it. Returns the run id."""
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
    handoff seat, so this drives the parked-run resume hook for real."""
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


async def count_runs(pid: str) -> int:
    async with AsyncSessionLocal() as db:
        rows = (
            (
                await db.execute(
                    select(WorkflowRun.id).where(WorkflowRun.project_id == uuid.UUID(pid))
                )
            )
            .all()
        )
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
            # The dock 戳记 assertions read the plan chain off the row (the
            # envelope path is the other seat) — the harness's own contract.
            "intent": msg.intent,
            "workflow_run_id": str(msg.workflow_run_id) if msg.workflow_run_id else None,
            "content": msg.content,
        }


async def wait_run_status(run_id: str, wanted: set[str], timeout: float = 45.0) -> dict:
    """Poll a run until it reaches one of ``wanted`` statuses."""
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


async def wait_asset_status(
    asset_id: str, wanted: set[AssetStatus], timeout: float = 420.0
) -> AssetStatus:
    """Poll an asset row to a wanted processing state (real-bytes seeds: the
    dev worker really ASRs the PENDING demo-bucket source)."""
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


# ---- Assertion helpers ------------------------------------------------------


def is_plan_dock(msg: dict) -> bool:
    return bool(msg.get("question")) and msg["question"].get("kind") == "task_book" and not msg.get("answer")


def terminal_tool_of(turn: dict) -> str:
    """The terminal tool the turn closed on, discriminated off the terminal
    envelope (ADR-077 判词② — the tool NAME never crosses the wire, 简报 §3;
    the envelope's SHAPE is the discriminator):

    - the plan settles + a run is born → ``start_run``
    - an unanswered task_book question docks → ``present_plan``
    - any other unanswered plain question → ``ask_user``
    - a run born with no settled question → ``run_birth`` (chat path: the
      ONLY same-turn birth left is edit_graph's approved-continuation
      branch — propose_tasks always docks; the envelope does not
      discriminate further, the scenarios assert the wiring outcome instead)
    - prose only → ``answer``
    """
    msg = turn.get("assistant_message") or {}
    q = msg.get("question") or {}
    if turn.get("answered_question") is not None and turn.get("run_id"):
        return "start_run"
    # The dock's OWN answer state discriminates, not this turn's settlement
    # of a PREVIOUS question — the enriched-brief answer turn legitimately
    # settles the pending ask AND docks the plan in one beat.
    if q.get("kind") == "task_book" and q.get("answer") is None:
        return "present_plan"
    if q.get("kind") == "question":
        return "ask_user"
    if turn.get("run_id"):
        return "run_birth"
    return "answer"


# ---- Activity work evidence (ADR-087 §3) ------------------------------------
# The Activity channel (assistant.activity frames) is the ONLY work-evidence
# channel (Phase 3 Batch B: the phase-side corroboration signal retired).
def _work_evidence(stream: "StreamTurn") -> tuple[bool, bool]:
    """(had_reads, had_repair) from the ACTIVITY channel — the ONLY work-
    evidence channel after Phase 3 Batch B.

    言语提交协议批 (G1): the repair span opens SILENTLY — a rejection's
    wire evidence is the half-started call's CANCELLED frame (and the rare
    born-terminal repair frame), never a repair active row. had_repair
    keeps its old semantics ("this turn had a rejection" — the stream-law
    skip): any cancelled frame or any repair-kind frame."""
    had_reads = any(a["kind"] == "read" for a in stream.activities)
    had_repair = any(
        a["kind"] == "repair" or a["status"] == "cancelled" for a in stream.activities
    )
    return had_reads, had_repair


def check_stream_law(
    stream: "StreamTurn", content: str, label: str, *, allow_reads: bool = True
) -> None:
    """The SSE 打字机律's tool-loop form (tool_loop.py on_delta 的 iteration-0
    唯一座位): iteration 0's speech streams verbatim; later iterations run
    quiet (a rejected iteration's speech is REPLACED speech, the repair-
    never-streams law). Therefore:

    - single-iteration turn (no read activities): concat(deltas) == the
      envelope content, exactly;
    - read-first turn (accepted reads in iteration 0 — read ACTIVITY frames
      present, the only evidence seat after Batch B): iteration-0 prose
      either rode the CHECKPOINT channel (eligible read — the waiter seat,
      ADR-104: flushed pre-execute, never enters the ledger, so the
      envelope does NOT contain it) or stayed in the ledger (non-eligible
      read — 账本兜底) and then PREFIXES the composed content
      (言语账本: kept parts + the terminal part join on a blank line);
    - a rejected iteration breaks even the prefix relation (its streamed
      speech was replaced) — LLM variance the scenarios cannot foresee, so
      this helper skips the turn entirely when a repair ACTIVITY appears.

    Both relations compare the STRIPPED concat: the envelope is edge-stripped
    by design (``_compose_speech`` strips every part) while the wire carries
    raw provider deltas, so leading "\n\n" tokenizer noise is variance, not
    a violation."""
    concat = "".join(stream.deltas)
    had_reads, had_repair = _work_evidence(stream)
    if had_repair:
        return  # replaced speech: even the prefix relation is void
    streamed = concat.strip()
    if had_reads and allow_reads:
        checkpointed = {c.strip() for c in stream.checkpoints}
        check(
            not streamed
            or content.startswith(streamed)
            or streamed in checkpointed,
            f"{label}: the read-first stream law (kept speech prefixes the "
            "content, or rode the checkpoint channel — ADR-104)",
            f"{concat[:120]!r} vs {content[:120]!r}",
        )
    else:
        check(
            streamed == content,
            f"{label}: the single-iteration stream law (concat(deltas) == content)",
            f"{concat[:120]!r} vs {content[:120]!r}",
        )


def check_turn_stream_law(stream: "StreamTurn", content: str, question: dict, label: str) -> None:
    """The ask-branch-aware stream law (harness 公共断言的 SSE 线格式座):
    an OPTIONS ask's content IS the streamed framing (the question rides the
    dock title); a TEXT ask keeps the bare question IN the speech —
    content = framing + "\\n\\n" + question, appended at compose, never
    streamed. The generic single-iteration law (concat == content) is
    structurally false for TEXT asks; which branch the turn takes is the
    LLM's call, so the harness asserts the BRANCH's law. Everything else
    delegates to :func:`check_stream_law`."""
    _, had_repair = _work_evidence(stream)
    if had_repair:
        return  # replaced speech voids even the prefix relation
    if question.get("kind") == "question" and not (question.get("options") or []):
        streamed = "".join(stream.deltas).strip()
        bare = (question.get("question") or "").strip()
        expected = f"{streamed}\n\n{bare}" if streamed else bare
        check(
            content == expected,
            f"{label}: a TEXT ask's bare question appends at compose "
            "(blank-line join), never streamed",
            f"{''.join(stream.deltas)[:120]!r} vs {content[:120]!r}",
        )
        return
    check_stream_law(stream, content, label)


# ---- ADR-084 speech-contract markers -----------------------------------------
# NEGATIVE shapes only (禁令 #7 — the LLM's own phrasing is never locked; what
# the contract bans is a SHAPE, and a banned shape is assertable).

# Process narration: read-iteration process talk must never persist into the
# settled message (ADR-104: pre-read speech rides the checkpoint channel as
# its own segment — the settled reply stands alone; post-read checkpoints
# carry results, never process narration).
# 词边界 adjudication（C-6，2026-09-19）：IGNORECASE 下裸 `I'?ll` 会把
# "will pull from" 的 "ill pull" 误判为第一人称过程叙述（"the caption text
# will pull from …" 是诚实披露而非过程泄漏）。合同不变（ADR-084 禁的是第一
# 人称过程话入终答），断言补 \b 词界。
PROCESS_NARRATION = re.compile(
    r"(\bI'?ll (pull|check|inspect|look into|fetch|take a look)|"
    r"\bLet me (check|pull|inspect|look|fetch)|"
    r"\bI'?m going to (pull|check|inspect|look)|"
    r"我先(查|看|拉|读)|让我(先)?(查|看|拉|读))",
    re.IGNORECASE,
)


def check_checkpoint_shape(stream: "StreamTurn", content: str, label: str) -> None:
    """Checkpoint shape laws (ADR-109 言语座位通用化; opportunistic —
    checkpoints are EARNED, so absence is legal; when they fired, the shape
    must hold): ≤4/turn (节奏护栏), never empty, never process narration
    POST-READ (pre-read waiter speech is legal — ADR-104 服务员话术律;
    phase-turn expectation sentences are the legal pre-read form), and the
    settled reply never repeats one verbatim."""
    if not stream.checkpoints:
        return
    check(
        len(stream.checkpoints) <= 4,
        f"{label}: checkpoints are capped at ≤4 per turn (ADR-109 rhythm guardrail)",
        stream.checkpoints,
    )
    check(
        all(c.strip() for c in stream.checkpoints),
        f"{label}: checkpoints are never empty",
        stream.checkpoints,
    )
    check(
        # The waiter exemption (ADR-104): a checkpoint that arrived BEFORE
        # any read settled is pre-read waiter speech — legal process talk
        # by the waiter-line law. The results-only bar polices POST-read
        # checkpoints (grounded judgment, never process narration).
        not PROCESS_NARRATION.search(
            " ".join(
                c for c, pre in zip(stream.checkpoints, stream.checkpoints_pre_read) if not pre
            )
        ),
        f"{label}: post-read checkpoints carry results, never process narration",
        stream.checkpoints,
    )
    for cp in stream.checkpoints:
        check(
            cp.strip() not in content,
            f"{label}: the settled reply never repeats a checkpoint verbatim",
            {"checkpoint": cp[:120], "settled": content[:120]},
        )


_ACTIVITY_KINDS = {"read", "draft", "run", "repair"}
_ACTIVITY_TERMINAL = {"completed", "failed", "cancelled"}


def check_activity_shape(stream: "StreamTurn", label: str) -> None:
    """ADR-087 §3 activity shape laws (opportunistic — a bare-reply turn
    legally has ZERO frames; when frames flew, the shape must hold):
    ① the wire whitelist is {activity_id, seq, kind, status, key} + the
    timing/fact extensions {at, count, duration_ms} (no params / results /
    reasoning ever leak); ② kind is a user-semantic category, never a tool
    name; ③ seq is strictly increasing; ④ a status flip appends a NEW frame
    on the same activity_id (never a mutation) — explore milestones are
    BORN-COMPLETED instant facts (one terminal frame, no active birth),
    exempt from the birth/flip laws; ⑤ T16-B wire twin — when the envelope
    lands, every activity's LAST frame is terminal (no dangling active)."""
    acts = stream.activities
    if not acts:
        return
    for a in acts:
        keys = set(a.keys())
        check(
            {"activity_id", "seq", "kind", "status", "key"} <= keys
            and keys <= {"activity_id", "seq", "kind", "status", "key", "at", "count", "duration_ms"},
            f"{label}: activity frame carries only the whitelist fields",
            a,
        )
        check(
            a["kind"] in _ACTIVITY_KINDS,
            f"{label}: kind is a user-semantic category, never a tool name",
            a,
        )
        check(
            a["status"] in _ACTIVITY_TERMINAL | {"active"},
            f"{label}: status is one of active/completed/failed/cancelled",
            a,
        )
        check(
            a["key"] is None or (isinstance(a["key"], str) and a["key"]),
            f"{label}: key is null or a non-empty i18n key",
            a,
        )
    seqs = [a["seq"] for a in acts]
    check(
        seqs == sorted(seqs) and len(set(seqs)) == len(seqs),
        f"{label}: activity seq is strictly increasing",
        seqs,
    )
    # Stable identity law (④): frames sharing an activity_id are ONE work
    # item's state flips — a span's first frame is the active birth, kind
    # never mutates mid-activity, exactly one terminal frame closes the id
    # (and nothing follows it), and the copy key follows the status-form
    # law: failed/cancelled REUSE the active key, completed swaps to the
    # past-tense form. A born-completed milestone is an instant fact: no
    # birth/flip laws apply.
    by_id: dict[str, list[dict]] = {}
    for a in acts:
        by_id.setdefault(a["activity_id"], []).append(a)
    for aid, frames in by_id.items():
        check(
            len({f["kind"] for f in frames}) == 1,
            f"{label}: kind never mutates across an activity's flips ({aid})",
            frames,
        )
        if len(frames) == 1 and frames[0]["status"] in _ACTIVITY_TERMINAL:
            continue  # born-completed milestone — an instant fact
        check(
            frames[0]["status"] == "active",
            f"{label}: a span's first frame is its active birth ({aid})",
            frames,
        )
        check(
            all(f["status"] == "active" for f in frames[:-1]),
            f"{label}: only the terminal frame leaves active ({aid})",
            frames,
        )
        active_keys = {f["key"] for f in frames[:-1]}
        terminal = frames[-1]
        if terminal["status"] == "completed":
            check(
                terminal["key"] is not None and terminal["key"] not in active_keys,
                f"{label}: completion swaps to the past-tense key ({aid})",
                frames,
            )
        elif terminal["status"] in ("failed", "cancelled"):
            check(
                terminal["key"] in active_keys,
                f"{label}: failed/cancelled reuse the active key ({aid})",
                frames,
            )
    last_status: dict[str, str] = {}
    for a in acts:  # append-oriented: the LAST frame per id is its state
        last_status[a["activity_id"]] = a["status"]
    dangling = {k: v for k, v in last_status.items() if v not in _ACTIVITY_TERMINAL}
    check(
        not dangling,
        f"{label}: T16-B — no activity outlives the turn (envelope sweep)",
        dangling,
    )


# ---- dock 形态（harness 公共断言）--------------------------------------------

# 选项载荷边界 lint（ADR-100 — 选项永不携带执行参数）：负形断言。
# label 全档（label 是方向名，带参即 shadow plan）；description 收窄
# 档（证据句合法引用源事实——"the 3 strongest moments" 不是参数，条数
# 词只在 label 档查；字幕模式族只查标识符形 source_only/target_only——
# 散文里的 bilingual 是用户语言内容词，与双语同律放行）。
_INT_LABEL_LINT = [
    re.compile(r"\d+\s*[:×x]\s*\d+"),                                      # 画幅 9:16
    re.compile(r"\b\d+\s*(seconds?|secs?|minutes?|mins?|秒|分钟)\b", re.I),  # 时长
    re.compile(r"\b(?:bilingual|source_only|target_only)\b", re.I),         # 字幕模式参数方言词（用户语言内容词合法）
    re.compile(r"\bcredits?\b|积分", re.I),                                  # 成本
    re.compile(r"\b\d+\s*(?:clips?|cards?|posts?|shorts?|条|张|篇)\b", re.I),  # 条数
]
_INT_DESC_LINT = [
    _INT_LABEL_LINT[0],
    _INT_LABEL_LINT[1],
    re.compile(r"\b(?:source_only|target_only)\b", re.I),  # 只查标识符形
    _INT_LABEL_LINT[3],
]

_INT_EXPLORATION_PROMPTS = (
    "what could I make from this keynote? give me a few directions",
    "what are some good next steps for this video?",
    "any ideas for what to do with the keynote?",
)


def check_dock_shape(msg: dict, label: str) -> None:
    """dock 形态律（harness 公共断言——每个回合信封自动携带）：

    - task_book 计划行自完备：链随 intent 列（非空）+ derived 列表；
      estimate_credits 在场时良构——total = [low, high] 非负有
      序、per_task 按任务序对齐（None ≡ 零报价），且 **Σ per_task ≡
      total**（报价对账律，orchestrator 前缀编译差分三面同源）。
    - 选项问结构律：1–5 选项（决断 ≤3 / 探索 ≤5 的分族节奏归 prompt
      法条座位，harness 只守结构外界）/ label 非空 ≤40 / recommended_id
      至多其一且指在 docked 选项上 / 载荷永不携带执行参数（负形 lint
      ——shadow plan 是本档的定义性违界）。

    default_path 恒在律不在此（ask 家族专属——trigger 建议 dock 是另
    一族，归各旅程的场景级断言）。"""
    q = msg.get("question") or {}
    if not q:
        return
    if q.get("kind") == "task_book":
        tasks = ((msg.get("intent") or {}).get("tasks")) or []
        check(
            bool(tasks),
            f"{label}: the plan dock self-carries the chain (intent column)",
            msg.get("intent"),
        )
        check(
            isinstance(q.get("derived"), list),
            f"{label}: the plan dock's derived preview rides as a list",
            q,
        )
        est = q.get("estimate_credits")
        if est is not None:
            total = est.get("total")
            check(
                isinstance(total, list)
                and len(total) == 2
                and all(isinstance(v, int) for v in total)
                and 0 <= total[0] <= total[1],
                f"{label}: estimate total is a non-negative ordered [low, high]",
                est,
            )
            per_task = est.get("per_task")
            if per_task is not None:
                check(
                    len(per_task) == len(tasks),
                    f"{label}: per_task aligns with the task list by index",
                    est,
                )
                lows = highs = 0
                for entry in per_task:
                    check(
                        entry is None
                        or (
                            isinstance(entry, list)
                            and len(entry) == 2
                            and all(isinstance(v, int) for v in entry)
                            and 0 <= entry[0] <= entry[1]
                        ),
                        f"{label}: each per_task entry is null or a [low, high] range",
                        est,
                    )
                    if entry is not None:
                        lows += entry[0]
                        highs += entry[1]
                check(
                    (lows, highs) == (total[0], total[1]),
                    f"{label}: Σ per_task ≡ total exactly (报价对账律)",
                    est,
                )
    elif q.get("kind") == "question":
        options = q.get("options") or []
        if options:
            check(
                1 <= len(options) <= 5,
                f"{label}: 1-5 options on the dock",
                options,
            )
            ids = {str(o.get("id")) for o in options}
            recommended_id = q.get("recommended_id")
            check(
                recommended_id is None or recommended_id in ids,
                f"{label}: recommended_id names at most one docked option",
                q,
            )
            for o in options:
                text = str(o.get("label") or "")
                check(
                    bool(text.strip()) and len(text) <= 40,
                    f"{label}: label non-empty and ≤40",
                    text,
                )
                for pat in _INT_LABEL_LINT:
                    check(
                        not pat.search(text),
                        f"{label}: labels never carry execution params (shadow plan 负形)",
                        f"{pat.pattern} in {text!r}",
                    )
                desc = str(o.get("description") or "")
                for pat in _INT_DESC_LINT:
                    check(
                        not pat.search(desc),
                        f"{label}: descriptions never carry execution params (shadow plan 负形)",
                        f"{pat.pattern} in {desc!r}",
                    )


def check_turn_stream_laws(stream: "StreamTurn", label: str) -> None:
    """SSE 回合的 harness 公共断言全家桶（``Ctx.chat_stream`` 在信封成功
    收官时自动携带）：线格式律（含文字问/选项问合成枝）+ Activity 帧形态
    + checkpoint 形态 + 选项问预览帧律 + dock 形态。"""
    msg = stream.completed["assistant_message"]
    content = msg.get("content") or ""
    q = msg.get("question") or {}
    check_turn_stream_law(stream, content, q, label)
    check_activity_shape(stream, label)
    check_checkpoint_shape(stream, content, label)
    # question.preview 预览帧律（言语提交协议 G2：预览骑缓冲、接受才释
    # 放——收到的预览即权威件，与信封 dock 载荷逐字段一致）。文字类提问
    # 永不预览 dock（与 R1 文字问门禁同律）——只有选项问 dock 触发本律。
    if q.get("kind") == "question" and (q.get("options") or []):
        check(
            len(stream.previews) >= 1,
            f"{label}: the ask's question.preview frame precedes the terminal envelope",
            stream.thinking,
        )
        preview = stream.previews[-1]
        check(
            preview.get("question") == q.get("question"),
            f"{label}: the preview's bare question IS the docked payload's",
            preview,
        )
        check(
            [o.get("id") for o in preview.get("options") or []]
            == [o.get("id") for o in q.get("options") or []],
            f"{label}: the preview's options match the docked payload's",
            preview,
        )
        check(
            preview.get("slot") == q.get("slot"),
            f"{label}: the preview's slot matches the docked payload's",
            preview,
        )
        check(
            isinstance(preview.get("allow_freeform"), bool),
            f"{label}: the preview carries allow_freeform",
            preview,
        )
        check(
            bool((preview.get("default_path") or "").strip()),
            f"{label}: the preview carries the default path",
            preview,
        )
    check_dock_shape(msg, label)


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
    intent dump is ``{type: "trigger_review", trigger, ref, suggestions}``.
    Returns the message row, or None on timeout."""
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


async def seed_keynote_project(ctx: Ctx, title: str) -> tuple[str, str]:
    """谱系场景素材种子：一个 COMPLETED 视频资产（worker-immune）+ 内容
    理解行（plan-turn 装配的 grounding 面）→ (pid, asset_id)。探索类提问
    的具体下一步方向从这里长出来——suggestions 永不空穴来风（契约：只在
    当前上下文存在具体可供选择的下一步方向时出现）。"""
    pid = await ctx.new_project(title)
    asset_id = await seed_asset(
        pid, ctx.user_id, AssetType.VIDEO, "keynote.mp4",
        extracted_text=(
            "On urban heat: cities are getting hotter, and shade trees plus "
            "reflective roofs can cool whole neighborhoods by several degrees."
        ),
        processed=True, meta={"language": "en"},
    )
    await seed_understanding(pid)
    return pid, asset_id


def check_options_dock(question: dict, label: str) -> None:
    """选项 dock 的谱系锁（ADR-100：一切可点选项归 dock——ask_user 选项
    问承接探索/浏览的方向建议）：kind=question / 1-5 选项 / label ≤40 /
    载荷永不携带执行参数（负形 lint）/ recommended 至多其一且必须指在
    docked 选项上 / default_path 恒在（每个问题都可安全跳过）。"""
    check(question.get("kind") == "question",
          f"{label}: the directions dock as a real options question", question)
    options = question.get("options") or []
    check(1 <= len(options) <= 5,
          f"{label}: 1-5 options on the dock", options)
    check(bool((question.get("default_path") or "").strip()),
          f"{label}: the default path rides every ask (安全跳过)", question)
    recommended_id = question.get("recommended_id")
    check(recommended_id is None
          or recommended_id in {str(o.get("id")) for o in options},
          f"{label}: recommended_id names at most one docked option", question)
    for o in options:
        text = str(o.get("label") or "")
        check(bool(text.strip()) and len(text) <= 40,
              f"{label}: label non-empty and ≤40", text)
        for pat in _INT_LABEL_LINT:
            check(not pat.search(text),
                  f"{label}: labels never carry execution params (shadow plan 负形)",
                  f"{pat.pattern} in {text!r}")
        desc = str(o.get("description") or "")
        for pat in _INT_DESC_LINT:
            check(not pat.search(desc),
                  f"{label}: descriptions never carry execution params (shadow plan 负形)",
                  f"{pat.pattern} in {desc!r}")


async def elicit_options_dock_turn(
    ctx: Ctx, pid: str, label: str,
    prompts: tuple[str, ...] = _INT_EXPLORATION_PROMPTS,
) -> dict:
    """驱动一个探索 → ask_user 选项 dock 回合（ADR-100：浏览/探索的方向
    建议全归 dock）→ turn。

    LLM 方差口径：纯 answer 散文 = 措辞重试（模型有选择散文答复的自由）；
    present_plan = 错档硬红（探索问永不直接承诺——事故④第一跳形态）。"""
    for prompt in prompts:
        turn = await ctx.chat(pid, prompt)
        tool = terminal_tool_of(turn)
        check(tool != "present_plan",
              f"{label}: an exploration question never docks a plan (事故④第一跳形态)",
              turn)
        q = turn["assistant_message"].get("question") or {}
        if tool == "ask_user" and (q.get("options") or []):
            return turn
    raise ScenarioFailure(
        f"{label}: no options-dock turn after {len(prompts)} tries"
    )


async def conversation_items(ctx: Ctx, pid: str) -> list[dict]:
    """The conversation's message list over the wire (持久化事实的客户端观察面)."""
    res = await ctx.conversation(pid)
    check(res.status_code == 200, "the conversation exists after the first turn",
          res.status_text if hasattr(res, "status_text") else res.status_code)
    return await ctx.messages(res.json()["id"])


# ---- 估价三断言 + repair 只一轮（harness 公共断言——runner 每本开跑前自动携带） --


def check_estimate_foundation() -> None:
    """估价地基（进程内编译，零 LLM——每本自动携带）：fold 对账自检 /
    报价单调性（目标子图 ≤ 全图，非负）/ NULL 语义（初启 fan-out 未估
    价；修饰技精确报价）/ 悬空 transform 编译期指名拒绝。"""
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

    # translate fan-out: same NULL semantics; fork 一语言一节点。
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
    # (the profile matrix lives in tests/test_cut_segments_pure.py).
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


_PROBE_SEQ = itertools.count(1)  # the agents registry is single-shot
# ("Duplicate agent declaration") and every probe binds a fresh stub client —
# each probe run IS a new declaration, so the name carries a per-process seq.


def _probe_agent(client: _StubClient, *, name: str, fallback=None) -> Agent:
    def _assemble():
        return ({"context_text": "", "message": "m"}, [])

    return Agent(
        name=f"{name}.{next(_PROBE_SEQ)}",
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


async def check_repair_once_foundation() -> None:
    """repair 只一轮（Agent 漏斗进程内 stub 自检，不打 API 零 LLM——每本
    自动携带）。"""
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
        name=f"scenario_probe_6.{next(_PROBE_SEQ)}",
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
            name=f"{name}.{next(_PROBE_SEQ)}",
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


# ---- 共享 fixture（demo 桶常住对象，reset_db 保护前缀）--------------------------
#
# fixture 纪律：源片一律先拷 ``scenario/`` 前缀——``delete_project`` 会 unlink
# 每个资产的 ``file_url``，共享 demo 键直接引用随清理被删。真字节素材若需
# worker 真处理（ASR），seed 时必须显式 ``request_processing=True``（ADR-102
# 休眠律：无 ``processing_requested_at`` 盖章的 PENDING 行 worker 永不认领）。
REMIX_SOURCE_KEY = "demo/uploads/demo_talk.mp4"
REMIX_EXEMPLAR_KEY = "demo/outputs/highlight-clips-preview-ec8e575b.mp4"
# 14.5s 双人访谈段（xy_1 [172.5,187.0]，约 6.6s 处一次干净的问→答切换——烘焙
# 配方卡「访谈分镜」demo 的同一源，实证 form=interview + 真 crop_track）。
INTERVIEW_SOURCE_KEY = "demo/uploads/xy_1_interview_15s.mp4"


async def copy_fixture(key: str, dest_prefix: str) -> str:
    """Copy a shared demo-bucket fixture to a scenario-owned key. NEVER seed
    an asset pointing at the shared object directly: project deletion unlinks
    every asset's ``file_url`` (``delete_project`` → ``delete_file``), so a
    shared key referenced by a scenario project dies with its cleanup."""
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


# demo_talk（~119s）的合成转写种子：真字节 + 逐词时间轴 + speaker_map，
# processed=True 自证处理终态（worker 不碰——fixture 自证比等盖章口确定），
# clips 链的选段/剪切/render 全在真字节上跑。
_SE2_SENTENCES = [
    (0.0, "Welcome back to the founder notes."),
    (6.0, "Today I want to walk through how we think about pricing."),
    (14.0, "Our pricing is simple."),
    (18.0, "The starter tier is free forever."),
    (24.0, "The pro tier costs ten dollars a month."),
    (30.0, "You only pay when your team actually grows."),
    (38.0, "Let me switch gears and talk about the roadmap for a moment."),
    (52.0, "We are shipping the new dashboard next quarter."),
    (64.0, "Back to pricing for a second."),
    (68.0, "Every paid tier includes the analytics dashboard."),
    (76.0, "Annual billing saves you two months."),
    (84.0, "That is the whole announcement for this week."),
]


def _talk_words() -> list[dict]:
    words: list[dict] = []
    for line_start, sentence in _SE2_SENTENCES:
        t = line_start
        for w in sentence.split():
            words.append({"word": w, "start": round(t, 2), "end": round(t + 0.4, 2)})
            t += 0.5
    return words


def no_decompile_canvas_node(graph: dict) -> bool:
    """decompile folds into the prelude — it must never read back as a
    standalone canvas node."""
    return not any(
        (n.get("spec") or {}).get("tool") == "decompile" for n in graph.get("nodes") or []
    )


# ==============================================================================
# 十本用户旅程矩阵
# ==============================================================================


async def s1_lost_user_full_journey(ctx: Ctx) -> None:
    """S1 迷失用户全旅程（auto 档——默认档旅程, ADR-117 §2）：裸愿望 → 主题问
    （SSE——选项预览律的旅程座位）→ 作答回填（自由文本 slot 握手 + 选项点选
    两路）/ 跳过 → draft-from-persona 计划 → dock 呈现即开工（同回合
    settled+born，confirmed_via="auto"）。途中锁契约拍：待决重建零内存
    态、一行一答 409、选项点选不 500（kind 守卫）、lifecycle stamp 拍①
    （fresh project preparing）。dock 等待态的 stamp/draft 拍（拍②③ +
    图先展示后运行）随 ask 档迁到 S3——本旅程跑默认档。

    LLM 方差说明：router 判 ask 是设计行为（prompt 策略行）；若个别模型把
    "I want a social post." 直接判 draft，首段断言会红——那是 prompt 回归
    信号。options 空合法（无 persona 时储藏室为空）。"""
    # 默认档钉住（顺序无关——Ctx 全矩阵共享一个 user）。
    await ctx.set_confirmation(execution="auto", credits="auto")
    pid = await ctx.new_project("S1 bare wish journey")

    # Lifecycle stamp 拍①：fresh project = preparing / not-ready / 零 blocker
    #（stamp 是唯一 lifecycle 读面，产物永不说话）。
    stamp0 = (await ctx.results(pid))["lifecycle"]
    check(stamp0["state"] == "preparing" and not stamp0["plan_ready"]
          and not stamp0["confirmation_ready"] and stamp0["blockers"] == [],
          "a fresh project reads preparing / not-ready on the stamp", stamp0)

    # turn1 走 SSE——选项问预览帧律（harness 自动断言）在此座上 exercised。
    stream1 = await ctx.chat_stream(pid, "I want a social post.")
    check(stream1.failed is None, "the ask turn never fails", stream1.failed)
    check(stream1.completed is not None, "the ask turn completes", stream1.failed)
    turn1 = stream1.completed
    msg1 = turn1["assistant_message"]
    check(turn1["run_id"] is None, "a bare wish never starts a run", turn1)
    check(terminal_tool_of(turn1) == "ask_user",
          "the rootless wish closes on the ask_user call", turn1)
    q1 = msg1.get("question") or {}
    check(q1.get("kind") == "question" and q1.get("slot") == "topic",
          "the rootless wish docks the topic ask first (never an empty plan)", msg1)
    check(bool((q1.get("default_path") or "").strip()),
          "the default path rides as the schema tooth", q1)
    # ask 三分解剖：content = 框架散文，payload.question = 裸问题（dock 标题 /
    # QA 归档 / 提醒尾读它）。散文缺字段时 content 回退裸问题——回归信号。
    check(bool((q1.get("question") or "").strip()),
          "the bare question rides the payload (dock title's source)", q1)
    check(has_prose(msg1) and (msg1.get("content") or "") != q1.get("question"),
          "the framing prose IS the message content (the ask's echo)",
          (msg1.get("content") or "")[:200])
    options = q1.get("options") or []
    check(len(options) == 0 or 2 <= len(options) <= 3,
          "options: 3 one-word picks (2 only for a genuinely binary choice), "
          "or empty when the persona pantry is empty",
          options)
    plan1 = await pending_plan(ctx, pid)
    check(plan1 is None or plan1.get("intent") is None,
          "no plan parks on an ask turn (brief-only row or none)", plan1)

    # 契约拍①：待决重建零内存态——刷新/跨设备座。
    res = await ctx.conversation(pid)
    check((res.json().get("pending_question") or {}).get("id") == msg1["id"],
          "the pending question rebuilds (the refresh / cross-device seat)",
          res.json())

    # 自由文本作答 —— slot 握手判定结算（router 在 pending 块上下文里把槽位
    # 值提案 user-stated，代码结算 freeform 并回填）。
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

    # 契约拍②：一行一答——已答问题再答 = 409。
    dup = await ctx.answer(msg1["id"], {"kind": "bail"})
    check(dup.status_code == 409, "re-answering the settled ask is a conflict",
          dup.status_code)

    # 契约拍③：选项点选作答（500 事故补盖——点选路曾裸奔）。第二项目同问
    # 点选：200 + answer.kind=option + slot 回填 user-stated（回填的是 label
    # 不是 id）+ plan path 接续带 follow_up。
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
        check(True, "option-pick beat skipped (pantry empty — exempt)", q1b)

    # 评审卡：作答轮直接出书，或推一轮。auto 档终点（ADR-117 §2）：
    # present_plan 呈现即开工——dock 回合的信封读 settled+born
    # （terminal_tool_of 读作 start_run 形；与口头确认同形 = 设计如此，
    # 工具名永不过线），零确认拍。
    turn_dock = turn2
    if turn_dock["run_id"] is None and not is_plan_dock(turn_dock["assistant_message"]):
        turn_dock = await ctx.chat(pid, "go ahead")
    msg2 = turn_dock["assistant_message"]
    check(turn_dock["run_id"] is not None,
          "auto 档呈现即开工 — the dock turn births the run (no confirm beat)",
          turn_dock)
    check(turn_dock["answered_question"] is not None,
          "the dock settles on the presentation-time start", turn_dock)
    aq2 = turn_dock["answered_question"]
    check((aq2.get("question") or {}).get("kind") == "task_book",
          "the settled row IS the docked plan", aq2)
    check(((aq2.get("question") or {}).get("requires_confirmation")) is False,
          "auto 档戳记 = 零确认拍（requires_confirmation=False  stamped at dock）",
          aq2.get("question"))
    check((aq2.get("answer") or {}).get("kind") == "start",
          "the presentation-time start lands kind=start", aq2.get("answer"))
    ftopic = ((aq2.get("question") or {}).get("brief") or {}).get("topic") or {}
    check(ftopic.get("source") == "user-stated" and bool(ftopic.get("value")),
          "the review card stamps the merged brief into the payload", ftopic)
    row_derived = (aq2.get("question") or {}).get("derived")
    check(isinstance(row_derived, list) and len(row_derived) >= 1,
          "the dock row self-carries the derived preview (payload)",
          aq2.get("question"))
    check((await ctx.results(pid)).get("pending_brief") is None,
          "pending_brief cleared on the presentation-time start")

    # confirmed_scope 快照：常驻授权通道的戳（confirmed_via="auto"）。
    s1_run_ctx = (await run_row(turn_dock["run_id"]))["context"]
    check((s1_run_ctx.get("confirmed_scope") or {}).get("confirmed_via") == "auto",
          "confirmed_via = auto（呈现即开工的常驻授权戳）",
          s1_run_ctx.get("confirmed_scope"))

    # 第三项目：rootless 闸门（措辞方差两连）→ 跳过 → draft-from-persona。
    pid3 = await ctx.new_project("S1 rootless gate")
    turn_c = await ctx.chat(pid3, "make me something for my audience")
    check(not is_plan_dock(turn_c["assistant_message"]),
          "a rootless wish never docks a groundless plan", turn_c)
    check(turn_c["run_id"] is None, "a rootless wish never starts a run", turn_c)
    if terminal_tool_of(turn_c) != "ask_user":
        # answer 族答复 = 顾问姿态方差，换新项目重试（历史会带偏后续判定）；
        # 连续两项目无 ask = S1 实证面漂移（红 = router/prompt 回归信号）。
        pid3 = await ctx.new_project("S1 rootless gate retry")
        turn_c = await ctx.chat(pid3, "I want a social post.")
        check(terminal_tool_of(turn_c) == "ask_user",
              "the rootless wish docks the ask gate", turn_c)
    q_c = turn_c["assistant_message"]["question"]
    check(q_c.get("answer") is None, "the gate docks unanswered", q_c)

    # × 跳过 → 默认路径生效：draft-from-persona 计划 dock 并同拍开工（auto
    # 档零确认拍——信封的 follow_up 是已结算 dock 行，workflow_run_id 戳在
    # 上面），asked 簿记挡住第二轮同槽问（问环有界）。跳过后 router 应判
    # draft；若再判 ask(topic)，asked 簿记翻回 draft——同归宿，只看终点。
    ans = await ctx.answer(turn_c["assistant_message"]["id"], {"kind": "bail"})
    check(ans.status_code in (200, 201), "the skip is accepted", ans.text)
    follow = ans.json().get("follow_up") or {}
    check((follow.get("question") or {}).get("kind") == "task_book"
          and follow.get("answer") is not None
          and bool(follow.get("workflow_run_id")),
          "skipping takes the default path — the plan docks AND starts on "
          "presentation (auto 档零确认拍)", follow)
    check(ans.json().get("answered_question") is not None,
          "the skipped ask settles as answered", ans.json())

    # 开工即清 pending_brief——计划快照读 follow_up 行自带的三座（reasons /
    # asked / echo 散文），不再读项目行。
    reasons = ((follow.get("question") or {}).get("reasons")) or []
    check("draft_from_persona" in reasons,
          "the draft-from-persona reason rides the docked plan", reasons)
    asked = (((follow.get("question") or {}).get("brief") or {}).get("asked")) or []
    check("topic" in asked,
          "the asked roll records the topic ask (the loop is bounded)", asked)
    echo = (follow.get("content") or "")
    check("persona" in echo.lower() or "人设" in echo,
          "the echo carries the default-path declaration", echo)


async def s2_material_to_clips_full_chain(ctx: Ctx) -> None:
    """S2 素材→短片全链（旗舰链本，需 dev worker + demo 桶 fixture + MiniMax
    配额）：真字节素材（合成转写自证处理终态）→ 方向建议 dock（SSE——选项
    预览律座）→ 途中插话（提醒尾 + pending 保持 + 下轮回填）→ clips 计划
    dock 呈现即开工（auto 档，ADR-117 §2——settled+born 同拍 + 零确认拍戳
    记 + confirmed_via=auto）→ auto 出生 run 真收官 → ask 档计划期修订链
    （面板钉存活 / chat 恒胜 / supersede 机器标记 / fill-key 幂等 / 打字
    母不答）→ SSE 散文确认 → 修订 run completed + clip 产物 → 触发回合
    reviewer → chat 修订 wiring 横切（同 id 原地改写 → 子图重跑）→ 扩张
    dock（新付费工作确认门 + Start 放行）。

    LLM 方差口径：方向 dock / 计划 dock 的措辞与路由是模型裁量（有界 nudge
    兜底）；锁的全是设计行为（插话不结算 / 提醒尾必在 / 修订恒胜 / 扩张必
    经确认门）。红了 = prompt 或机制回归信号，不是剧本松劲。"""
    # 默认档钉住（顺序无关——Ctx 全矩阵共享一个 user）。
    await ctx.set_confirmation(execution="auto", credits="auto")
    fixture_prefix = f"scenario/s2-{uuid.uuid4().hex[:8]}"
    src_key = await copy_fixture(REMIX_SOURCE_KEY, fixture_prefix)
    pid = await ctx.new_project("S2 material to clips")
    await seed_asset(
        pid, ctx.user_id, AssetType.VIDEO, "s2-talk.mp4",
        file_url=src_key,  # 真字节——select_clips 真的剪
        extracted_text=" ".join(s for _, s in _SE2_SENTENCES),
        meta={
            "words": _talk_words(),
            "speaker_map": {"turns": [{"start": 0.0, "end": 95.0, "speaker": "host"}]},
            "language": "en",
        },
        processed=True,
    )
    await topup_wallet(ctx.user_id)  # clips 真渲染 + article 真 LLM 都花积分

    # ① 方向建议 dock（SSE——选项问预览帧律的确定性座位：探索 dock 恒带
    #    1–3 选项）→ 插话 → 自由文本作答回填。
    dock_turn: dict | None = None
    for prompt in _INT_EXPLORATION_PROMPTS:
        stream = await ctx.chat_stream(pid, prompt)
        check(stream.failed is None, "the exploration turn never fails", stream.failed)
        turn = stream.completed
        tool = terminal_tool_of(turn)
        check(tool != "present_plan",
              "an exploration question never docks a plan (事故④第一跳形态)", turn)
        q = turn["assistant_message"].get("question") or {}
        if tool == "ask_user" and (q.get("options") or []):
            dock_turn = turn
            break
    check(dock_turn is not None, "no options-dock turn after 3 tries", None)
    conv_id = dock_turn["conversation_id"]
    q1 = dock_turn["assistant_message"]["question"]
    check_options_dock(q1, "S2 directions")
    check(not (dock_turn["assistant_message"].get("suggestions") or []),
          "消息流零选项 — the row carries no inline suggestion block",
          dock_turn["assistant_message"])

    # ①b 插话：与待决问题无关的能力问 → 正常回答 + 代码拼装提醒尾（原问题 +
    #    default_path 逐字，代码强制文本可锁）→ 问题保持待决。
    default_path = (q1.get("default_path") or "").strip()
    turn_i = await ctx.chat(pid, "By the way, what can you generate?")
    check(terminal_tool_of(turn_i) == "answer",
          "the interjection closes on the answer call", turn_i)
    check(turn_i.get("answered_question") is None,
          "an interjection never settles the pending ask", turn_i)
    check(not turn_i["assistant_message"].get("question"),
          "the interjection turn docks no new question", turn_i["assistant_message"])
    content_i = turn_i["assistant_message"].get("content") or ""
    check(has_prose(turn_i["assistant_message"]),
          "the interjection gets its normal answer", turn_i["assistant_message"])
    check(has_reminder_tail(content_i),
          "the reply ends with the code-composed reminder tail", content_i[-200:])
    check(default_path in content_i,
          "the tail carries the ask's default path verbatim", content_i[-200:])
    check(bool((q1.get("question") or "").strip()) and q1["question"] in content_i,
          "the tail quotes the BARE question, not the framing prose",
          content_i[-200:])
    res = await ctx.conversation(pid)
    check((res.json().get("pending_question") or {}).get("id")
          == dock_turn["assistant_message"]["id"],
          "the ask stays pending through the interjection", res.json())

    # ①c 自由文本作答（点名 clips 方向）→ plan path 接续 → clips 计划 dock
    #    呈现即开工（auto 档，ADR-117 §2——settled+born 同拍，零确认拍）。
    res_a = await ctx.answer(dock_turn["assistant_message"]["id"],
                             {"kind": "freeform",
                              "text": "cut 3 vertical highlight clips from the talk"})
    check(res_a.status_code in (200, 201), "the freeform direction settles",
          res_a.text)
    follow = res_a.json().get("follow_up") or {}
    dock_msg: dict | None = None
    run1_id: str | None = None
    if follow.get("workflow_run_id"):
        dock_msg, run1_id = follow, str(follow["workflow_run_id"])
    dock_stream: StreamTurn | None = None
    for nudge in ("就按这个方向出计划——3 条竖屏高光短片。",
                  "the highlight clips plan, please",
                  "cut the highlights — 3 vertical clips"):
        if dock_msg is not None:
            break
        stream = await ctx.chat_stream(pid, nudge)
        check(stream.failed is None, "the plan nudge never fails", stream.failed)
        check(not is_plan_dock(stream.completed["assistant_message"]),
              "a held clips dock (守卫线/不可报价) is off-journey — estimate "
              "回归信号", stream.completed["assistant_message"])
        if stream.completed["run_id"] is not None:
            dock_msg = stream.completed["assistant_message"]
            run1_id = stream.completed["run_id"]
            dock_stream = stream
            break
    check(dock_msg is not None and run1_id is not None,
          "auto 档：the clips plan docks AND starts on presentation within "
          "3 nudges (零确认拍)", None)
    # 开工戳记（读库行一座，与信封路径无关）：kind=start + 零确认拍 +
    # 链带 clips + confirmed_via=auto + pending_brief 即清。
    dock_row = await message_row(dock_msg["id"])
    check((dock_row.get("answer") or {}).get("kind") == "start",
          "the presentation-time start lands kind=start", dock_row.get("answer"))
    check(((dock_row.get("question") or {}).get("requires_confirmation")) is False,
          "auto 档戳记 = 零确认拍（requires_confirmation=False at dock）",
          dock_row.get("question"))
    tasks = ((dock_row.get("intent") or {}).get("tasks")) or []
    check(any(t["tool"] == "select_clips" for t in tasks),
          "the docked chain carries the clips tool", tasks)
    run1_ctx = (await run_row(run1_id))["context"]
    check((run1_ctx.get("confirmed_scope") or {}).get("confirmed_via") == "auto",
          "confirmed_via = auto（呈现即开工的常驻授权戳）",
          run1_ctx.get("confirmed_scope"))
    check((await ctx.results(pid)).get("pending_brief") is None,
          "pending_brief cleared on the presentation-time start")
    if dock_stream is not None:
        # SSE draft 律（计划复述座）：信封散文 IS 持久化的计划复述。
        content = dock_msg.get("content") or ""
        echo = ((dock_row.get("intent") or {}).get("answer")) or ""
        check(content == echo,
              "the streamed draft's envelope content IS the persisted plan echo",
              f"{content[:120]!r} vs {echo[:120]!r}")

    # ①d auto 出生 run 真收官（出生即真跑——clips 链在真字节上 completed）+
    # 触发回合消费（建议问先 bail——后续修订消息不能被判定结算吃掉，③b 同
    # 款卫生）。然后钉 ask 档再进修订链：dock 恒等用户的拍，消除收官竞态
    # （auto 档的结构 held 与 ask 等待在信封面同形，计划期机器与档无关）。
    row1 = await wait_run_status(run1_id, {"completed", "failed"}, timeout=600.0)
    check(row1["status"] == "completed",
          "the auto-born run delivers on the real bytes", row1["status"])
    review1 = await wait_trigger_review(ctx, conv_id, run1_id)
    check(review1 is not None,
          "the auto-born run's trigger turn speaks its review row", run1_id)
    if (review1.get("question") or {}).get("kind") == "question":
        bail1 = await ctx.answer(review1["id"], {"kind": "bail"})
        check(bail1.status_code in (200, 201),
              "run1's review question is bailed (revision determinism)",
              bail1.text)
    await ctx.set_confirmation(execution="ask", credits="ask")

    # ② 修订链：面板钉存活 / chat 恒胜 / supersede / fill-key 幂等 / 打字母不答。
    #    开工即清的 pending_brief 由 dock_row 的 intent 列顶替（面板钉模拟器
    #    的胚子）；ids1 = auto 出生 run 的世界（修订 dock 在其上长草稿）。
    def pin_count(plan: dict, count: int) -> dict:
        """Simulate a panel hand edit: the select_clips count set in params —
        the edited chain IS the prior_intent (no merge machinery)."""
        edited = dict(plan["intent"])
        edited["tasks"] = [
            {**t, "params": {**task_params(t), "count": count}}
            if t["tool"] == "select_clips" else t
            for t in plan_tasks(plan)
        ]
        return edited

    plan1 = {"intent": dock_row.get("intent") or {}}  # 开工前的链（shim）
    first_qid = dock_msg["id"]
    ids1 = {n["id"] for n in (await ctx.graph(pid))["nodes"]}
    # 面板钉 count=4（区别于作答里的 3，钉存活才可见）+ 无关 refine 加德语版。
    turn2 = await ctx.chat(
        pid, "also add a German version of the clips", prior_intent=pin_count(plan1, 4)
    )
    check(terminal_tool_of(turn2) == "present_plan",
          "the refinement re-docks on present_plan", turn2)
    check(is_plan_dock(turn2["assistant_message"]), "the refinement re-docks",
          turn2["assistant_message"])
    check(turn2["assistant_message"]["id"] != first_qid,
          "the old plan is superseded by a new question row")
    tasks = plan_tasks(await pending_plan(ctx, pid))
    clips_tasks = [t for t in tasks if t["tool"] == "select_clips"]
    # coerce_numbers_to_str 是 dock 边界的现行法：手改存活锁值不锁 JSON 类型。
    check(clips_tasks and str(task_params(clips_tasks[0]).get("count")) == "4",
          "the panel hand edit survives an unrelated refine", tasks)
    check(any((task_params(t).get("target_language")
               or task_params(t).get("language")) == "de" for t in tasks),
          "the German fork arrived", tasks)
    graph2 = await ctx.graph(pid)
    ids2 = {n["id"] for n in graph2["nodes"]}
    check(ids1 < ids2,
          "the German fork grows a new draft node (superset, never twins)", ids2 - ids1)
    msgs = await ctx.messages(conv_id)
    old = next(m for m in msgs if m["id"] == first_qid)
    check((old.get("answer") or {}).get("text") == "superseded",
          "the superseded plan carries the machine marker", old.get("answer"))

    # chat 修订恒胜（覆盖面板钉）。
    plan2 = await pending_plan(ctx, pid)
    turn3 = await ctx.chat(
        pid, "clips only need 2", prior_intent=pin_count(plan2, 4)
    )
    check(terminal_tool_of(turn3) == "present_plan",
          "the chat revision re-docks", turn3)
    tasks = plan_tasks(await pending_plan(ctx, pid))
    clips_tasks = [t for t in tasks if t["tool"] == "select_clips"]
    check(clips_tasks and str(task_params(clips_tasks[0]).get("count")) == "2",
          "the chat revision overrides the panel pin (chat always wins)", tasks)
    # 参数微调 = 同 fill_key 复用——图节点零双生。
    graph3 = await ctx.graph(pid)
    check(sorted(n["id"] for n in graph3["nodes"]) == sorted(ids2),
          "a param refine reuses the same nodes (fill-key idempotency — no twins)",
          graph3["nodes"])

    # task_book 待决不参与任何结算：打字母永不当选项答掉。
    live_qid = turn3["assistant_message"]["id"]
    turn4 = await ctx.chat(pid, "a")
    check(turn4.get("answered_question") is None,
          "a typed letter never answers a task_book", turn4)
    q_row = await message_row(live_qid)
    check(q_row.get("answer") is None or (q_row["answer"] or {}).get("text") == "superseded",
          "the plan stays pending or is superseded by a re-dock — never letter-answered",
          q_row.get("answer"))

    # ②d 去掉德语版——收缩修订重 dock，终链 = clips-only count 2。
    docked5: dict | None = None
    for prompt in ("drop the German version — just 2 English highlight clips",
                   "remove the German clips, keep the 2 English ones"):
        turn5 = await ctx.chat(pid, prompt)
        if is_plan_dock(turn5["assistant_message"]):
            tasks5 = plan_tasks(await pending_plan(ctx, pid))
            if not any((task_params(t).get("target_language")
                        or task_params(t).get("language")) == "de" for t in tasks5):
                docked5 = turn5
                tasks = tasks5
                break
    check(docked5 is not None, "the German fork leaves the chain on request", tasks)
    clips_tasks = [t for t in tasks if t["tool"] == "select_clips"]
    check(clips_tasks and str(task_params(clips_tasks[0]).get("count")) == "2",
          "the shrink keeps the chat-won count", tasks)
    graph5 = await ctx.graph(pid)

    # ③ SSE 散文确认（ask 档——dock 等到的口头拍，与 Start 钮同一机器）→
    #    start_run + 草稿图原地填充（同 id 无双生；run1 世界在其下不动）。
    stream_s = await ctx.chat_stream(pid, "looks good, start")
    check(stream_s.failed is None, "the confirm turn never fails", stream_s.failed)
    turn_s = stream_s.completed
    check(terminal_tool_of(turn_s) == "start_run",
          "the prose confirmation closes on the start_run call", turn_s)
    run2_id = turn_s["run_id"]
    check(run2_id is not None, "prose confirmation starts the run", turn_s)
    check(turn_s["answered_question"] is not None, "the plan settles on start", turn_s)
    check((await ctx.results(pid)).get("pending_brief") is None,
          "pending_brief cleared on start")
    filled_graph = await ctx.graph(pid)
    check(sorted(n["id"] for n in filled_graph["nodes"])
          == sorted(n["id"] for n in graph5["nodes"]),
          "start fills the SAME nodes in place (fill-key idempotency — never twins)",
          # 双侧 dump（同上——单侧 dump 无法归因多/少的是哪侧）。
          {"draft": graph5["nodes"], "filled": filled_graph["nodes"]})
    check(not any(n.get("state") == "draft" for n in filled_graph["nodes"]),
          "the draft world re-queues on start", filled_graph["nodes"])

    # ③b 真链收官 + 触发回合 reviewer 发言：intent dump = {type:
    #    trigger_review, trigger, ref, suggestions=labels}；建议 dock 成真实
    #    编号选项问。断言 dump 形态与 dock 良构；言语内容不锁（LLM 文案）。
    row = await wait_run_status(run2_id, {"completed", "failed"}, timeout=600.0)
    check(row["status"] == "completed",
          "the clips chain completes on the real bytes", row["status"])
    check(len(await outputs_of(pid, "clip")) >= 1, "the clip outputs land", None)
    review = await wait_trigger_review(ctx, conv_id, run2_id)
    check(review is not None,
          "the run-completed trigger turn speaks its review row", run2_id)
    rintent = (review or {}).get("intent") or {}
    check(rintent.get("trigger") == "run_completed" and rintent.get("ref") == run2_id,
          "the review dump names trigger + ref", rintent)
    sugs = rintent.get("suggestions") or []
    check(0 <= len(sugs) <= 3, "0–3 suggestion labels (schema-bounded)", sugs)
    check(all(isinstance(s, str) and s.strip() for s in sugs),
          "each suggestion is a user-voice label", sugs)
    if sugs:
        question = (review or {}).get("question") or {}
        check(question.get("kind") == "question",
              "the suggestions dock as a real options question", question)
        options = question.get("options") or []
        check([o.get("id") for o in options] == [str(i + 1) for i in range(len(sugs))]
              and [o.get("label") for o in options] == sugs,
              "the dock options are the numbered labels (1/2/3 grammar)",
              options)
        # Harness 卫生（非断言）：建议问先 × 跳过收掉——后续修订消息不能被
        # 判定结算吃掉（wiring 修订路才是断言对象）。
        bail = await ctx.answer(review["id"], {"kind": "bail"})
        check(bail.status_code in (200, 201),
              "the review suggestions question is bailed (revision determinism)",
              bail.text)

    # ④ 修订 = wiring 横切：chat 修订 → WiringProposal（edit_prompt + run
    #    子图）→ 节点程序行原地改写（同 id 无双生）→ 子图重跑起 run。锁的是
    #    设计行为；红了 = chat_intent prompt 回归信号。两 run 世界有两个
    #    clips 节点——模型指认哪一个是 LLM 裁量（wiring 提案自带 node id），
    #    断言锁「恰一个 clips 节点原地改写」不锁指认。
    graph_before = await ctx.graph(pid)
    clips_before = {
        n["id"]: (n.get("spec") or {}).get("prompt")
        for n in graph_before["nodes"]
        if (n.get("spec") or {}).get("tool") == "select_clips"
    }
    check(len(clips_before) >= 1, "the runs' fills grew clips graph nodes",
          graph_before["nodes"])
    turn_rev = await ctx.chat(pid, "把选段再大胆一点——只留最有冲击力的瞬间。")
    check(terminal_tool_of(turn_rev) == "run_birth",
          "the revision closes on a proposal tool's run birth (chat path)", turn_rev)
    check(turn_rev["run_id"] is not None,
          "the revision rides the wiring path — the subgraph rerun is born",
          turn_rev)
    graph_after = await ctx.graph(pid)
    check(sorted(n["id"] for n in graph_after["nodes"])
          == sorted(n["id"] for n in graph_before["nodes"]),
          "the revision reuses the SAME nodes (edit_prompt + rerun — never a twin)",
          graph_after["nodes"])
    after_by_id = {n["id"]: n for n in graph_after["nodes"]}
    edited = [
        nid for nid, prompt in clips_before.items()
        if (after_by_id[nid].get("spec") or {}).get("prompt") != prompt
    ]
    check(len(edited) == 1,
          "edit_prompt rewrote exactly one clips node's program in place",
          {nid: (after_by_id[nid].get("spec") or {}).get("prompt")
           for nid in clips_before})
    check(after_by_id[edited[0]].get("state") != "draft",
          "the rerun re-queues its node", after_by_id[edited[0]].get("state"))
    # 修订 run 先收官（扩张 Start 会撞出生地活跃 422——等待是 harness 卫生）；
    # 其收官触发回合同样先 bail（否则扩张拍的消息被判定结算吃掉）。
    await wait_run_status(turn_rev["run_id"], {"completed", "failed"}, timeout=600.0)
    review2 = await wait_trigger_review(ctx, conv_id, turn_rev["run_id"], timeout=90.0)
    if review2 is not None and (review2.get("question") or {}).get("kind") == "question":
        await ctx.answer(review2["id"], {"kind": "bail"})

    # ⑤ 扩张 → 确认门（已批图之外的新付费工作必须 dock 确认才放行——无论
    #    LLM 走 edit_graph(add_node+run) 还是 propose_tasks，回合都 dock
    #    task_book + 零 run；Start 才生 run。路由无关断言：信封形状 +
    #    draft 预览 + Start 后链上生 run）。
    turn_exp: dict | None = None
    for prompt in ("write a long-form article from the talk as a new piece",
                   "add an article version alongside the clips",
                   "the article, please"):
        cand = await ctx.chat(pid, prompt)
        check(cand.get("run_id") is None,
              "扩张同 turn 直跑 = 教义红线（new paid work must never run "
              "unauthorized）", cand)
        if is_plan_dock(cand["assistant_message"]):
            turn_exp = cand
            break
    check(turn_exp is not None,
          "the expansion ask docks a plan within 3 prompts", None)
    check(terminal_tool_of(turn_exp) == "present_plan",
          "the expansion turn closes on the plan dock", turn_exp)
    graph_docked = await ctx.graph(pid)
    draft_tools = [
        (n.get("spec") or {}).get("tool")
        for n in graph_docked["nodes"]
        if n.get("state") == "draft"
    ]
    check("write_article" in draft_tools,
          "the dock's draft stamp previews the article node (the door's "
          "mutation rolled back; canonical fill keys)", draft_tools)
    res_exp = await ctx.answer(turn_exp["assistant_message"]["id"],
                               {"kind": "start"})
    check(res_exp.status_code == 200, "dock Start answers the plan", res_exp.text)
    run_exp = res_exp.json()["answered_question"].get("workflow_run_id")
    check(run_exp, "a run was born on Start", res_exp.json())
    runs_exp = await ctx.client.get(f"/projects/{pid}/runs")
    born_exp = next((r for r in runs_exp.json() if r.get("id") == run_exp),
                    None) or {}
    exp_tools = [
        t.get("tool")
        for t in (born_exp.get("context") or {}).get("tasks") or []
    ]
    check("write_article" in exp_tools,
          "the born run carries the expansion chain", exp_tools)
    # Harness 卫生：扩张 run（writer 链读 transcript 文本，会 completed）的
    # 触发回合是 fire-and-forget；不消费它就 cleanup 会让在飞 LLM 调用撞上
    # 项目删除（messages conversation FK 竞态）。等到落地就 bail；超时静默。
    await wait_run_terminal(run_exp, timeout=600.0)
    review3 = await wait_trigger_review(ctx, conv_id, run_exp, timeout=90.0)
    if review3 is not None and (review3.get("question") or {}).get("kind") == "question":
        await ctx.answer(review3["id"], {"kind": "bail"})


async def s3_material_suggestion_exploration(ctx: Ctx) -> None:
    """S3 素材→建议→探索（需 dev worker + MiniMax 配额）：方向建议选项 dock
    （消息流零选项 + 持久化事实 + × 安全跳过）→ 发现型目标（SSE 全链：
    chat.explore.* 活动键族 + 决策包 dock 三面）→ 探索三族出生（一条
    journey， ExplorationRow 表座——探索族永不入图）→ Start →
    run.context.confirmed_scope 五字段快照 → 产物真落地 → 确定性尾
    （I-EXPLORE-01 执行门拒收 / 幂等重放 / 无时间轴降级诚实 / 图面零探索
    节点）。fixture 纪律：scenario/ 前缀真桶拷贝；时间轴落在 demo_talk
    真实时长内（~119s）；words 逐词真值（门在出生时刻逐字校验 excerpt）。"""
    from app.chat.exploration_tools import execute_exploration_tool
    from app.chat.perception import SearchTranscriptParams, run_perception_tool
    from app.models.tables import ExplorationRow
    from app.pipeline.graph_store import WiringRejected, apply_wiring_ops

    # ask 档钉住（ADR-117——本旅程保留确认拍族断言：dock 等待 / typed Start /
    # 草稿图横切 / lifecycle stamp 拍②③，均从 S1 迁入或原生）。
    await ctx.set_confirmation(execution="ask", credits="ask")
    fixture_prefix = f"scenario/s3-{uuid.uuid4().hex[:8]}"
    src_key = await copy_fixture(REMIX_SOURCE_KEY, fixture_prefix)
    pid = await ctx.new_project("S3 discovery chain")
    project_uuid = uuid.UUID(pid)
    asset_id = await seed_asset(
        pid, ctx.user_id, AssetType.VIDEO, "s3-talk.mp4",
        file_url=src_key,  # 真字节——cut_segments 真的剪
        extracted_text=" ".join(s for _, s in _SE2_SENTENCES),
        meta={
            "words": _talk_words(),
            "speaker_map": {"turns": [{"start": 0.0, "end": 95.0, "speaker": "host"}]},
            "language": "en",
        },
        processed=True,  # worker 的资产队列不碰（时间轴/文本即种子）
    )
    await topup_wallet(ctx.user_id)  # cut_segments 真渲染 + writer 真 LLM

    # ① 建议 beat：探索问 → 选项 dock（可点选可 ×，散文恒带默认路径）；
    #    消息流零选项——assistant 行永不携带 suggestions 交互块。
    turn0 = await elicit_options_dock_turn(ctx, pid, "S3 directions")
    msg0 = turn0["assistant_message"]
    check(terminal_tool_of(turn0) == "ask_user",
          "the exploration turn closes on the options dock", turn0)
    check_options_dock(msg0.get("question") or {}, "S3 directions")
    check(not (msg0.get("suggestions") or []),
          "消息流零选项 — the row carries no inline suggestion block", msg0)
    check(turn0["run_id"] is None, "an options ask never starts a run", turn0)
    row0 = next(m for m in await conversation_items(ctx, pid) if m["id"] == msg0["id"])
    check((row0.get("question") or {}).get("kind") == "question",
          "the options dock persists on the message row", row0)
    check(not (row0.get("suggestions") or []),
          "the persisted row carries no inline suggestion block", row0)
    bail = await ctx.answer(msg0["id"], {"kind": "bail"})
    check(bail.status_code in (200, 201),
          "the options dock bails clean (× = safe skip)", bail.text)

    # ② 发现型目标（SSE 全链）。
    stream = await ctx.chat_stream(
        pid,
        "Find the parts where I talk about pricing — cut those into a clip, "
        "and write an English post from them.",
    )
    check(stream.failed is None, "the discovery turn never fails", stream.failed)
    check(stream.completed is not None, "the discovery turn completes", stream.activities)

    # 工作会话活动键族：读的开/收 + 三个里程碑帧（出生即完成，count 唯一载荷）。
    # 用哪把读具是模型的合法裁量——ADR-107：锚定转录 ≤8000 字符内联进
    # digest，短文源头不搜索（本 fixture 的 ~119s talk 正在预算内），所以旅
    # 程锁「发现回合落地前读过素材」不变量，不锁 search_transcript 的帧。
    acts = stream.activities
    read_opens = [
        a
        for a in acts
        if (a.get("key") or "").startswith("chat.inspecting.")
        or a.get("key") == "chat.explore.searching"
    ]
    read_settles = [
        a
        for a in acts
        if (a.get("key") or "").startswith("chat.inspectingDone.")
        or (a.get("key") or "").startswith("chat.inspectingFailed.")
        or a.get("key") == "chat.explore.searchingDone"
    ]
    check(
        read_opens and all(a["status"] == "active" for a in read_opens),
        "the discovery turn grounds via visible reads (open frames)",
        acts,
    )
    check(
        read_settles
        and all(a["status"] in ("completed", "failed") for a in read_settles),
        "the reads settle (done/failed mirror frames)",
        acts,
    )
    for key in ("candidatesReady", "selectsReady", "plansReady"):
        frames = [a for a in acts if a.get("key") == f"chat.explore.{key}"]
        check(
            len(frames) == 1
            and frames[0]["kind"] == "draft"
            and frames[0]["status"] == "completed"
            and isinstance(frames[0].get("count"), int)
            and frames[0]["count"] >= 1,
            f"the {key} milestone lands born-completed with its count",
            acts,
        )

    # 决策包 dock：plans 阅读层 + 编译链证据 + quote。
    dock_msg = stream.completed["assistant_message"]
    check(is_plan_dock(dock_msg), "the discovery chain docks the decision package", dock_msg)
    question = dock_msg["question"]
    plans_payload = question.get("plans") or []
    check(plans_payload, "the dock carries the plans reading layer", question)
    check(
        all(p.get("plan_id") and "title" in p and p.get("outputs") for p in plans_payload),
        "every plan row carries plan_id / title / outputs",
        plans_payload,
    )
    intent_dump = dock_msg.get("intent") or {}
    dock_tools = [t.get("tool") for t in intent_dump.get("tasks") or []]
    check(
        "cut_segments" in dock_tools and "write_post" in dock_tools,
        "the compiled chain = cut_segments + write_post (编译移出 LLM)",
        dock_tools,
    )
    check(
        "select_clips" not in dock_tools,
        "the compiler never emits select_clips (the execution world has no "
        "second discoverer)",
        dock_tools,
    )
    check("estimate_credits" in question, "the quote rides the dock (费用语义)", question)
    check("derived" in question, "the derived preview rides the dock", question)
    # ADR-117 §4 戳记（ask 档）：呈现时算好的确认需要——本座断言它欠拍
    # （两档 ask + 有报价 → reason 归 pref 族），auto 档的对偶戳在 S1。
    check(question.get("requires_confirmation") is True,
          "ask 档戳记 = dock 欠确认拍（requires_confirmation=True）", question)
    check(str(question.get("confirm_reason") or "").endswith("_pref"),
          "the reason names the pref family (money first when both ask)",
          question.get("confirm_reason"))

    # 草稿图横切（图先展示后运行——自 S1 迁入 ask 档座）：dock 即 stamp——
    # draft 节点 + 逐节点估价，零消耗直到 start。
    draft_graph = await ctx.graph(pid)
    draft_nodes = [
        n for n in draft_graph["nodes"]
        if n.get("state") == "draft"
        and (n.get("spec") or {}).get("prototype") in ("generator", "editor")
    ]
    check(len(draft_nodes) >= 1, "the dock stamps the draft graph (图先展示后运行)",
          draft_graph["nodes"])
    check(not any(
        (n.get("spec") or {}).get("role") == "task_book"
        for n in draft_graph["nodes"]
    ), "the read frame hides the task_book node (confirm seat = dock pill)",
       draft_graph["nodes"])
    check(any(n.get("estimate_credits") for n in draft_nodes),
          "draft nodes carry their own quotes (逐节点估价)", draft_nodes)
    draft_ids = sorted(n["id"] for n in draft_graph["nodes"])

    # Lifecycle stamp 拍②（自 S1 迁入）：docked 全估价链读 plan_ready ∧
    # confirmation_ready。
    stamp1 = (await ctx.results(pid))["lifecycle"]
    check(stamp1["plan_ready"] is True
          and stamp1["confirmation_ready"] is True
          and stamp1["blockers"] == []
          and stamp1["state"] == "confirmation_ready",
          "the docked plan reads plan_ready ∧ confirmation_ready on the stamp",
          stamp1)

    # Lifecycle stamp 拍③（自 S1 迁入）：活跃 run 扣住确认权而计划保持
    # docked——plan_ready 恒真、confirmation_ready 翻假、blocker 点名
    # active_run、rollup 读 running；落定即交还（PLAN_READY ≠ confirm
    # authority）。
    seeded_run = await seed_active_run(pid)
    stamp2 = (await ctx.results(pid))["lifecycle"]
    check(stamp2["plan_ready"] is True
          and stamp2["confirmation_ready"] is False
          and "active_run" in stamp2["blockers"]
          and stamp2["state"] == "running",
          "an active run blocks confirmation while the plan stays docked",
          stamp2)
    await settle_seeded_run(seeded_run)
    stamp2b = (await ctx.results(pid))["lifecycle"]
    check(stamp2b["confirmation_ready"] is True
          and stamp2b["blockers"] == [],
          "settling the run hands confirmation readiness back", stamp2b)

    # 探索三族出生，一条 journey（ExplorationRow 表座——探索族永不入图）。
    async with AsyncSessionLocal() as db:
        explore_rows = list(
            (
                await db.execute(
                    select(ExplorationRow).where(
                        ExplorationRow.project_id == project_uuid,
                    )
                )
            ).scalars().all()
        )
        kinds = {r.spec.get("exploration_kind") for r in explore_rows}
        check(
            {"candidate_set", "select", "content_plan"} <= kinds,
            "the exploration three families are born",
            kinds,
        )
        journey_ids = {str(r.journey_id) for r in explore_rows}
        check(len(journey_ids) == 1, "the whole chain rides ONE journey", journey_ids)
        journeys = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(Journey)
                    .where(Journey.project_id == project_uuid)
                )
            ).scalar_one()
        )
        check(journeys == 1, "exactly one Journey row", journeys)
    db_plan_ids = {
        str(r.id) for r in explore_rows if r.spec.get("exploration_kind") == "content_plan"
    }
    check(
        {p["plan_id"] for p in plans_payload} == db_plan_ids,
        "the dock's plan ids == the table's content_plan rows",
        (plans_payload, [str(r.id) for r in explore_rows]),
    )

    # 恢复路复证（plans 双座的第二座）：pending_question 直读 plans。
    conv = await ctx.conversation(pid)
    check(conv.status_code == 200, "the conversation reads back", conv.text)
    pending = conv.json().get("pending_question") or {}
    check(
        (pending.get("question") or {}).get("plans"),
        "the restore path's pending_question carries plans (pending_brief 座)",
        pending,
    )

    # ③ 确认 → run 出生 → Confirmed Scope Snapshot。
    res = await ctx.answer(dock_msg["id"], {"kind": "start"})
    check(res.status_code == 200, "dock Start answers the decision package", res.text)
    run_id = res.json()["answered_question"].get("workflow_run_id")
    check(run_id, "a run was born on Start", res.json())

    # 同 id 原地填充（自 S1 迁入——same compile → same fill keys, never
    # twins）：start 后图面 = draft 拍的同批 id，零 draft 态残留。
    filled_graph = await ctx.graph(pid)
    check(sorted(n["id"] for n in filled_graph["nodes"]) == draft_ids,
          "start fills the SAME nodes in place (never twins)",
          # 双侧 dump（取证律——单侧 dump 曾让一轮红无法归因）。
          {"draft": draft_graph["nodes"], "filled": filled_graph["nodes"]})
    check(not any(n.get("state") == "draft" for n in filled_graph["nodes"]),
          "the draft world re-queues on start", filled_graph["nodes"])

    run_ctx = (await run_row(run_id))["context"]
    scope = run_ctx.get("confirmed_scope") or {}
    check(bool(scope), "the run carries the Confirmed Scope Snapshot", run_ctx)
    check(
        scope.get("confirmation_id") == dock_msg["id"],
        "confirmation_id = the docked message (确认点可追)",
        scope,
    )
    check(bool(scope.get("confirmed_at")), "confirmed_at stamped", scope)
    check(
        scope.get("confirmed_via") == "dock_pill",
        "confirmed_via = dock_pill (typed Start 座位)",
        scope,
    )
    check(
        {p.get("plan_id") for p in scope.get("plans") or []}
        == {p["plan_id"] for p in plans_payload},
        "the snapshot's plans = the docked reading layer",
        scope,
    )
    check(
        [t.get("tool") for t in scope.get("compiled_scope") or []] == dock_tools,
        "the snapshot's compiled_scope = the chain the run was born with",
        (scope.get("compiled_scope"), dock_tools),
    )
    check(
        scope.get("quote") == question.get("estimate_credits"),
        "the snapshot's quote = the quote shown at confirm time",
        (scope.get("quote"), question.get("estimate_credits")),
    )

    # ④ 产物落地（真渲染 + 真 writer）。
    final = await wait_run_terminal(run_id, timeout=600.0)
    check(final == "completed", "the discovery run completes", final)
    clips = await outputs_of(pid, "clip")
    check(len(clips) >= 1, "cut_segments' clip output lands", len(clips))
    posts = await outputs_of(pid, "post")
    check(len(posts) >= 1, "the post output lands", len(posts))

    # ⑤ 确定性尾（零 LLM 进程内——执行门 / 幂等 / 降级 / 图面负形）。
    async with AsyncSessionLocal() as db:
        project = (
            await db.execute(select(Project).where(Project.id == project_uuid))
        ).scalar_one()
        rows = list(
            (
                await db.execute(
                    select(ExplorationRow).where(
                        ExplorationRow.project_id == project_uuid,
                    )
                )
            ).scalars().all()
        )
        cset = next(r for r in rows if r.spec.get("exploration_kind") == "candidate_set")
        sel = next(r for r in rows if r.spec.get("exploration_kind") == "select")
        explore_ids = {str(r.id) for r in rows}

        # I-EXPLORE-01: 执行门拒收探索产物（run / delete / connect 全拒——
        # 探索族不在 graph_nodes，任何图写口引用即悬空拒收）。
        for ops in (
            [{"op": "run", "nodes": [str(cset.id)]}],
            [{"op": "delete_node", "node": str(sel.id)}],
            [{"op": "connect", "from_node": str(cset.id), "to_node": str(sel.id)}],
        ):
            try:
                await apply_wiring_ops(db, project_uuid, ops)
            except WiringRejected:
                pass
            else:
                raise ScenarioFailure(f"I-EXPLORE-01: the wiring door accepted {ops}")

        # 幂等重放：identical call → the SAME artifact, no twin。
        idem_args = {
            "asset_id": asset_id,
            "topic": "pricing",
            "goal": "s3 idempotency probe",
            "members": [{"start": 12.0, "end": 18.9, "speaker": "host"}],
        }
        first = await execute_exploration_tool(db, project, "propose_candidates", dict(idem_args))
        await db.commit()
        second = await execute_exploration_tool(db, project, "propose_candidates", dict(idem_args))
        await db.commit()
        id_of = lambda text: re.search(r"candidate_set_id: ([0-9a-f-]{36})", text).group(1)  # noqa: E731
        check(
            id_of(first) == id_of(second),
            "idempotent replay returns the existing artifact",
            (first, second),
        )
        explore_ids.add(id_of(first))

        # 无时间轴降级: an asset without words is an honest door rejection
        # and the reads say so — never a fabricated range。
        bare_asset_id = await seed_asset(
            pid, ctx.user_id, AssetType.VIDEO, "s3-bare.mp4",
            extracted_text="A talk without word-level timestamps.",
            meta={"language": "en"},
            processed=True,
        )
        obs = await run_perception_tool(
            db, project, "search_transcript",
            SearchTranscriptParams(query="pricing", asset_id=uuid.UUID(bare_asset_id)),
        )
        check(
            "timeline-ready" in obs.text or "word-level" in obs.text,
            "the no-timeline read is an honest empty, never a fabricated hit",
            obs.text,
        )
        rejected = await execute_exploration_tool(
            db, project, "propose_candidates",
            {**idem_args, "asset_id": bare_asset_id, "goal": "s3 degradation probe"},
        )
        check(
            rejected.startswith("The door rejected"),
            "exploration on a wordless asset is a door rejection",
            rejected,
        )
        await db.commit()

        journeys = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(Journey)
                    .where(Journey.project_id == project_uuid)
                )
            ).scalar_one()
        )
        check(
            journeys == 2,
            "chain journey + idem-probe journey — adopt never mints twins "
            "(rejected calls never mint)",
            journeys,
        )

    # 图面负形（Workspace v4.2 C1——探索族永不入图，画布零探索节点）。
    graph = await ctx.graph(pid)
    check(
        all(n["id"] not in explore_ids for n in graph["nodes"]),
        "the exploration family never enters the graph (画布零探索节点)",
        [n["id"] for n in graph["nodes"] if n["id"] in explore_ids],
    )

    # Harness 卫生（非断言）：run 收官的 trigger 回合是 fire-and-forget；
    # 不消费它就 cleanup 会让在飞的 LLM 调用撞上项目删除（messages
    # conversation FK 竞态）。等到落地就 bail 掉建议问；超时静默通过。
    conv_id = (stream.completed or {}).get("conversation_id")
    if conv_id:
        review = await wait_trigger_review(ctx, conv_id, run_id, timeout=90.0)
        if review is not None and (review.get("question") or {}).get("kind") == "question":
            await ctx.answer(review["id"], {"kind": "bail"})


async def s4_no_material_writers(ctx: Ctx) -> None:
    """S4 无素材→图文 + caption mode 默认吸收：写手族（post / quotes /
    carousel）无素材直生（root = 主题，六素材硬门全卸）；caption 三拍——
    A) 有独立第二语言（项目 de / 素材 en）且无字幕关键词 → 无字幕 dock
       问，计划直接 dock 且 intent.caption_mode == "source_only"；Start 后
       run.context.caption_mode 同为 source_only；
    B) 用户原话带"双语" → 用户原话恒胜：bilingual 随 dock 的 intent，
       Start 后 run.context.caption_mode == "bilingual"；
    C) 关键词设定 → 追问（修订轮不再提字幕）→ 面板 Start：设定值经暂存
       继承存活（"未提及" ≠ "撤回"，服务端从 stored pending 继承）。

    LLM 判定有抖动（"make a quote card" 可能回反问或提别的链——两者都
    合法），各部各给 3 次尝试直到目标工具的计划落地。

    fixture 纪律：素材必须可读——单行占位文本 + 无 understanding 会让诚实
    读路拿到 _WARM_DEAD_TEXT（字节不存在，warm 建不出），模型依法拒 dock
    或给 paste-text 选项（轮盘式随机命中）。厚转录 + seed_understanding
    让乐观 dock 与先读后 dock 两条合法路都通。"""
    # ask 档钉住（ADR-117——本旅程的 typed Start / dock 等待断言全是确认拍族）。
    await ctx.set_confirmation(execution="ask", credits="ask")
    material = (
        "Cities are getting hotter, and the bill lands on the people least "
        "able to pay it. A shaded street can be ten degrees cooler than the "
        "block next to it — that is not an amenity, that is infrastructure. "
        "When we plant a row of trees we are not decorating the neighborhood; "
        "we are buying the cheapest climate adaptation a city can get. "
        "Reflective roofs do the same work from the top down, bouncing the "
        "heat back before it ever enters the building. The mayors who "
        "understand this are not asking whether to fund shade — they are "
        "asking why they waited so long."
    )

    async def dock_writer(pid: str, prompts: tuple[str, ...], tool: str,
                          label: str) -> dict:
        docked: dict | None = None
        tools_seen: list = []
        for prompt in prompts:
            turn = await ctx.chat(pid, prompt)
            if not is_plan_dock(turn["assistant_message"]):
                continue  # ask-back / prose — nudge again
            plan = await pending_plan(ctx, pid)
            tools_seen = [t.get("tool") for t in plan_tasks(plan)]
            if tool in tools_seen:
                docked = turn
                break
            # Wrong chain docked — bail the plan before nudging again (a live
            # dock would read the next chat message as its revision/Start).
            await ctx.answer(turn["assistant_message"]["id"], {"kind": "bail"})
        check(docked is not None, f"{label}: no {tool} plan dock after 3 turns",
              tools_seen)
        return docked

    # A) distinct alt language, no caption wording → no question ever docks;
    #    the plan carries the visible default (source_only) end-to-end.
    pid = await ctx.new_project("S4-A caption default absorbed")
    await set_project_language(pid, "de")
    # Fixture declaration: the language fact is the declared COMPLETED row's
    # meta — worker-immune by construction.
    await seed_asset(pid, ctx.user_id, AssetType.VIDEO, "keynote.mp4",
                     extracted_text=material, meta={"language": "en"},
                     processed=True)
    await seed_understanding(pid)
    await seed_completed_run(pid)
    docked_a: dict | None = None
    tools_seen_a: list = []
    for prompt in ("make a quote card from the video",
                   "pull the sharpest quotes from my keynote into quote cards",
                   "the quote cards, please"):
        turn = await ctx.chat(pid, prompt)
        q = turn["assistant_message"].get("question") or {}
        check(
            not any(str(o.get("id", "")).startswith("caption_mode_")
                    for o in q.get("options") or []),
            "A: no caption-mode question ever docks (default absorption)",
            q,
        )
        if not is_plan_dock(turn["assistant_message"]):
            continue
        plan = await pending_plan(ctx, pid)
        tools_seen_a = [t.get("tool") for t in plan_tasks(plan)]
        if "write_quotes" in tools_seen_a:
            docked_a = turn
            break
        await ctx.answer(turn["assistant_message"]["id"], {"kind": "bail"})
    check(docked_a is not None, "A: no write_quotes plan dock after 3 turns",
          tools_seen_a)
    check(terminal_tool_of(docked_a) == "present_plan",
          "A: the turn closes straight on the plan dock (no caption gate)",
          docked_a)
    check(docked_a.get("run_id") is None,
          "A: no run before Start (same-turn create_run is forbidden)",
          docked_a)
    plan = await pending_plan(ctx, pid)
    check(((plan or {}).get("intent") or {}).get("caption_mode") == "source_only",
          "A: the visible default rides the docked intent", plan)
    res = await ctx.answer(docked_a["assistant_message"]["id"], {"kind": "start"})
    check(res.status_code == 200, "A: dock Start answers the plan", res.text)
    run_id = res.json()["answered_question"].get("workflow_run_id")
    check(run_id, "A: a run was born on Start", res.json())
    runs = await ctx.client.get(f"/projects/{pid}/runs")
    born = next((r for r in runs.json() if r.get("id") == run_id), None) or {}
    check((born.get("context") or {}).get("caption_mode") == "source_only",
          "A: run.context.caption_mode", born.get("context"))
    await wait_run_terminal(run_id)  # harness 卫生：Start 的 run 落定再起下家

    # B) the user's own words always win: a literal "bilingual" stamps the
    #    mode over any default.
    pid_b = await ctx.new_project("S4-B user wording wins")
    await set_project_language(pid_b, "de")
    await seed_asset(pid_b, ctx.user_id, AssetType.VIDEO, "keynote.mp4",
                     extracted_text=material, meta={"language": "en"},
                     processed=True)
    await seed_understanding(pid_b)
    await seed_completed_run(pid_b)
    docked_b = await dock_writer(
        pid_b,
        ("make a bilingual quote card from the video",
         "pull the keynote's sharpest lines into bilingual quote cards",
         "bilingual quote cards, please"),
        "write_quotes", "B",
    )
    plan_b = await pending_plan(ctx, pid_b)
    check(((plan_b or {}).get("intent") or {}).get("caption_mode") == "bilingual",
          "B: the user's wording stamps bilingual on the docked intent", plan_b)
    res_b = await ctx.answer(docked_b["assistant_message"]["id"], {"kind": "start"})
    check(res_b.status_code == 200, "B: dock Start answers the plan", res_b.text)
    rid_b = res_b.json()["answered_question"].get("workflow_run_id")
    runs = await ctx.client.get(f"/projects/{pid_b}/runs")
    born_b = next((r for r in runs.json() if r.get("id") == rid_b), None) or {}
    check((born_b.get("context") or {}).get("caption_mode") == "bilingual",
          "B: run.context.caption_mode follows the user's wording",
          born_b.get("context"))
    await wait_run_terminal(rid_b)  # harness 卫生

    # C) 设定 → 追问 → Start：the mode survives a refinement turn that
    #    doesn't re-mention it (stash inherit) AND a panel Start that strips
    #    the field ("not mentioned" ≠ "retracted" — the server inherits from
    #    the stored pending brief).
    pid_c = await ctx.new_project("S4-C mode survives refinement")
    await set_project_language(pid_c, "de")
    await seed_asset(pid_c, ctx.user_id, AssetType.VIDEO, "keynote.mp4",
                     extracted_text=material, meta={"language": "en"},
                     processed=True)
    await seed_understanding(pid_c)
    docked_c = await dock_writer(
        pid_c,
        ("make bilingual quote cards from the video",
         "pull the keynote's sharpest quotes into bilingual cards",
         "bilingual quote cards, please"),
        "write_quotes", "C",
    )
    plan_qid = docked_c["assistant_message"]["id"]
    plan_c = await pending_plan(ctx, pid_c)
    check(((plan_c or {}).get("intent") or {}).get("caption_mode") == "bilingual",
          "C: the keyword stamps bilingual on the first dock", plan_c)
    for nudge in ("make it 3 cards instead",
                  "change that to 3 quote cards",
                  "actually, only 3 cards"):  # 修订措辞 — 散文确认会绕过追问路径
        turn = await ctx.chat(pid_c, nudge)
        plan = await pending_plan(ctx, pid_c)
        check(((plan or {}).get("intent") or {}).get("caption_mode") == "bilingual",
              "C: the refinement turn keeps the stamped caption_mode", plan)
        if is_plan_dock(turn["assistant_message"]):
            plan_qid = turn["assistant_message"]["id"]
            break
    # Start THROUGH THE PANEL: the frontend's normalize strips fields it
    # doesn't edit, so its Start payload carries the plan's intent minus
    # caption_mode — the server must inherit the stamped mode from the
    # stored pending brief ("not mentioned" ≠ "retracted").
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
          "C: run.context.caption_mode survives set → refine → Start",
          born_c.get("context"))
    await wait_run_terminal(rid_c)  # harness 卫生

    # D) 无素材直生 — post：主题即根，写手零素材跑（六素材硬门全卸）。
    pid_d = await ctx.new_project("S4-D post without material")
    docked_d = await dock_writer(
        pid_d,
        ("Write a LinkedIn post about the EU AI Act for researchers.",
         "draft a LinkedIn post on the EU AI Act, aimed at researchers",
         "the post, please"),
        "write_post", "D",
    )
    check(docked_d.get("run_id") is None, "D: no run before Start", docked_d)
    await ctx.answer(docked_d["assistant_message"]["id"], {"kind": "bail"})

    # E) 无素材直生 — quotes：alt-language 项目（de）零素材，全程零字幕
    #    dock 问（默认值能扛的参数永不阻塞）。
    pid_e = await ctx.new_project("S4-E quotes without material")
    await set_project_language(pid_e, "de")
    docked_e: dict | None = None
    for prompt in ("make a quote card about remote work",
                   "pull three sharp lines about remote work into quote cards",
                   "the quote cards, please"):
        turn = await ctx.chat(pid_e, prompt)
        q = turn["assistant_message"].get("question") or {}
        check(not any(str(o.get("id", "")).startswith("caption_mode_")
                      for o in q.get("options") or []),
              "E: no caption-mode question ever docks (默认值能扛的参数永不阻塞)", q)
        if not is_plan_dock(turn["assistant_message"]):
            continue
        plan_e = await pending_plan(ctx, pid_e)
        if "write_quotes" in [t.get("tool") for t in plan_tasks(plan_e)]:
            docked_e = turn
            break
        await ctx.answer(turn["assistant_message"]["id"], {"kind": "bail"})
    check(docked_e is not None, "E: no write_quotes plan dock after 3 turns")
    mode_e = (((await pending_plan(ctx, pid_e)) or {}).get("intent") or {}).get("caption_mode")
    check(mode_e in (None, "source_only"),
          "E: the absorbed default never reads bilingual unprompted", mode_e)
    await ctx.answer(docked_e["assistant_message"]["id"], {"kind": "bail"})

    # F) 无素材直生 — carousel。
    pid_f = await ctx.new_project("S4-F carousel without material")
    docked_f = await dock_writer(
        pid_f,
        ("make a carousel about remote work",
         "turn the remote-work theme into a carousel",
         "the carousel, please"),
        "write_carousel", "F",
    )
    check(docked_f.get("run_id") is None, "F: no run before Start", docked_f)
    await ctx.answer(docked_f["assistant_message"]["id"], {"kind": "bail"})


async def s5_research_grounds_writer(ctx: Ctx) -> None:
    """S5 调研→写作：research 全链（有界 loop 节点）——chat 出书 → 面板手编
    chain 为 [research, write_post] 起步 → research step done +
    spec.research_brief 钢印 + writer 在 research 之后完成 + post 产物存在。

    网络方差说明：活 DDG 可能全灭（无网 / 被限流）——诚实降级下 brief 带
    caveat 自述、run 照样 completed。断言只看「钢印存在 + 步骤有序 +
    产物存在」，不看简报内容质量（那是 prompt / provider 层的事）。"""
    # ask 档钉住（ADR-117——dock 等待 + 面板手编 typed Start 是确认拍族断言）。
    await ctx.set_confirmation(execution="ask", credits="ask")
    pid = await ctx.new_project("S5 research grounds writer")

    turn1 = await ctx.chat(
        pid,
        "Write a LinkedIn post about the EU AI Act's 2026 enforcement — "
        "research the latest developments first.",
    )
    check(terminal_tool_of(turn1) == "present_plan",
          "a rooted topic closes on the present_plan call", turn1)
    check(is_plan_dock(turn1["assistant_message"]),
          "a rooted topic docks a plan", turn1["assistant_message"])
    plan = (await ctx.results(pid)).get("pending_brief")
    qid = turn1["assistant_message"]["id"]

    # 面板手编起步（S2 先例）：chain 换成确定性的 [research, write_post]。
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


async def s6_consult_never_deadends(ctx: Ctx) -> None:
    """S6 纯咨询不死路：能力问（SSE——单轮流式律座）/ 闲聊 / 无根
    "start it" → 纯 answer 终态，零计划零 dock 零 run，纯信息答永不带
    建议卡（能力目录换皮 = 噪音）；浏览问（"还有其他推荐吗"族）在推荐
    格局已建立后仍归 ask_user 选项 dock——永不两级跳劫持（present_plan
    承诺 dock / 字幕闸选项 = 硬红）。纯散文 answer = 方差重试。"""
    pid = await ctx.new_project("S6 consult")

    # 能力问走 SSE——单轮流式律（concat(deltas) == 信封散文）在此座
    # exercised（harness 自动断言）。
    stream1 = await ctx.chat_stream(pid, "what can you do?")
    check(stream1.failed is None, "the capability turn never fails", stream1.failed)
    turn1 = stream1.completed
    check(terminal_tool_of(turn1) == "answer",
          "a capability question closes on the answer call", turn1)
    check(turn1["run_id"] is None, "capability question starts no run", turn1)
    check(not turn1["assistant_message"].get("question"), "no question docks",
          turn1["assistant_message"])
    check(not (turn1["assistant_message"].get("suggestions") or []),
          "no suggestion card on a bare capability answer (能力目录换皮 = 噪音)",
          turn1["assistant_message"])
    check(has_prose(turn1["assistant_message"]), "a prose answer lands")

    turn1b = await ctx.chat(pid, "do you support multiple languages?")
    check(terminal_tool_of(turn1b) == "answer",
          "a pure info question closes on the answer call", turn1b)
    check(not turn1b["assistant_message"].get("question")
          and not (turn1b["assistant_message"].get("suggestions") or []),
          "an info question docks nothing and suggests nothing",
          turn1b["assistant_message"])

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

    # 浏览问永不劫持（事故④回归锁）：推荐格局已建立后，自定义措辞的浏览问
    # → ask_user 选项 dock——present_plan / 字幕闸 = 硬红（事故④原形态）。
    pid_b, _ = await seed_keynote_project(ctx, "S6 browse question")
    setup = await elicit_options_dock_turn(ctx, pid_b, "S6 browse setup")
    bail = await ctx.answer(setup["assistant_message"]["id"], {"kind": "bail"})
    check(bail.status_code in (200, 201),
          "the setup dock settles (浏览问不被待决题吃掉)", bail.text)
    got: dict | None = None
    for prompt in ("还有其他推荐吗？", "anything else you'd recommend?",
                   "还有别的方向可以看看吗？"):
        turn = await ctx.chat(pid_b, prompt)
        msg = turn["assistant_message"]
        check(not is_plan_dock(msg),
              "a browse question is never hijacked into a plan dock (事故④第一跳)",
              turn)
        q = msg.get("question") or {}
        check(not any(str(o.get("id", "")).startswith("caption_mode_")
                      for o in q.get("options") or []),
              "no caption gate on a browse question (事故④第二跳)", q)
        if terminal_tool_of(turn) == "ask_user" and (q.get("options") or []):
            got = turn
            break
    check(got is not None,
          "no options-dock browse answer after 3 tries (浏览问无档可去 = 事故④温床)")
    check_options_dock(got["assistant_message"].get("question") or {}, "S6 browse")
    bail = await ctx.answer(got["assistant_message"]["id"], {"kind": "bail"})
    check(bail.status_code in (200, 201), "the browse dock bails clean", bail.text)
    check(await count_runs(pid_b) == 0, "no run the whole journey")


async def s7_second_circle_revision(ctx: Ctx) -> None:
    """S7 修订第二圈（确定性尾剧本，零 LLM——锁真实 DB + 真实 API 门）：
    落地 clip → 精确编辑两族实应用（remove_range 删字幕 cue +
    set_caption_style 换预设）→ 同 id 原地改写无双生 → undo 两连逐级回退
    → wipe 归档（不删除、publication / journal 不连坐）→ 归档不可变 409
    墙 → 换态 restore（同 work 至多一 active）→ 读面跟随。"""
    from app.pipeline.edit_span import ResolvedSpan, resolve_quote_span
    from app.pipeline.outputs import archive_outputs
    from app.models.tables import Publication
    from app.models.schemas import PublicationState

    pid = await ctx.new_project("S7 second circle")
    asset_id = await seed_asset(
        pid, ctx.user_id, AssetType.VIDEO, "s7.mp4", processed=True
    )

    cues = [
        {"start": 10.0, "end": 10.8, "text": "Welcome back", "lang": "en"},
        {"start": 10.8, "end": 11.5, "text": "to the show", "lang": "en"},
        {"start": 12.0, "end": 13.2, "text": "today we talk pricing", "lang": "en"},
    ]
    spec = {
        "segments": [
            {
                "id": "s1",
                "start": 10.0,
                "end": 40.0,
                "hidden": False,
                "asset_id": asset_id,
                "url": "scenario/s7.mp4",
            }
        ],
        "caption_track": cues,
        "source": {
            "kind": "video",
            "url": "scenario/s7.mp4",
            "asset_id": asset_id,
            "duration": 120.0,
        },
        "aspect": "9:16",
    }
    async with AsyncSessionLocal() as db:
        run = WorkflowRun(
            project_id=uuid.UUID(pid),
            status=WorkflowStatus.COMPLETED,
            context={"target_language": "en", "ui_language": "en"},
        )
        db.add(run)
        await db.flush()
        step = WorkflowStep(
            run_id=run.id, kind="select_clips", status="done", seq=1,
        )
        db.add(step)
        await db.flush()
        output = Output(
            project_id=uuid.UUID(pid),
            workflow_step_id=step.id,
            type="clip",
            language="en",
            provenance="real",
            payload={"duration": 30},
            render_spec=spec,
        )
        db.add(output)
        await db.flush()
        oid = output.id
        db.add(
            WorkflowStep(
                run_id=run.id, kind="render", status="done", seq=2,
                inputs=[str(step.id)], spec={"output_id": str(oid)},
            )
        )
        db.add(
            Publication(
                user_id=ctx.user_id,
                project_id=uuid.UUID(pid),
                output_id=oid,
                payload={"title": "s7"},
                state=PublicationState.PUBLISHED,
                idempotency_key=f"s7-{oid}",
            )
        )
        await db.commit()
        work_id = output.work_id

    # ① edit door: quote → span (the resolver's exact tier) → remove_range
    #    op through the real operations API — the door edit_output rides。
    span = resolve_quote_span(cues, "welcome back")
    check(isinstance(span, ResolvedSpan) and span.tier == "exact",
          "the quote resolves at the exact tier", span)
    res = await ctx.client.post(
        f"/outputs/{oid}/operations",
        json={"ops": [{"op": "remove_range", "params": {"start": span.start, "end": span.end}}]},
    )
    check(res.status_code == 201, "remove_range op applies", res.text)
    body = res.json()
    check(body["output"]["id"] == str(oid),
          "the edit rewrites the SAME row in place (同 id 无双生)", body["output"]["id"])
    new_track = body["output"]["render_spec"]["caption_track"]
    check(
        all("Welcome" not in c["text"] for c in new_track),
        "the cut cue leaves the caption track", new_track,
    )
    check(len(body["operations"]) == 1, "the op journals", body["operations"])

    # ② 第二族实应用: set_caption_style 换预设（同 id + journal）。
    res = await ctx.client.post(
        f"/outputs/{oid}/operations",
        json={"ops": [{"op": "set_caption_style",
                       "params": {"preset": "karaoke-highlight", "enabled": True}}]},
    )
    check(res.status_code == 201, "set_caption_style op applies", res.text)
    body = res.json()
    check(body["output"]["id"] == str(oid),
          "the style edit rewrites the SAME row too", body["output"]["id"])
    check(body["output"]["render_spec"].get("caption_style_preset") == "karaoke-highlight",
          "the caption preset lands on the spec", body["output"]["render_spec"])
    # POST 回声 = 本批 ops；累计台账在 GET /operations（undoable journal）。
    journal = await ctx.client.get(f"/outputs/{oid}/operations")
    check(journal.status_code == 200, "the journal reads", journal.text)
    ops = [r for r in journal.json() if r["source"] == "editor"]
    check([r["op"] for r in ops] == ["remove_range", "set_caption_style"],
          "both ops journal", journal.json())

    # ③ undo 两连逐级回退: 先撤样式（预设回退），再撤剪切（cue 回轨）。
    res = await ctx.client.post(f"/outputs/{oid}/operations/undo")
    check(res.status_code == 200, "the first undo applies", res.text)
    check(res.json()["output"]["render_spec"].get("caption_style_preset")
          != "karaoke-highlight",
          "undo reverts the caption preset", res.json()["output"]["render_spec"])
    res = await ctx.client.post(f"/outputs/{oid}/operations/undo")
    check(res.status_code == 200, "the second undo applies", res.text)
    restored_track = res.json()["output"]["render_spec"]["caption_track"]
    check(
        any("Welcome" in c["text"] for c in restored_track),
        "undo restores the cut cue", restored_track,
    )

    # ④ wipe 归档（不重删）: archive the delivered row, birth the successor
    #    with the inherited work_id — publication survives, the journal stays
    #    readable, the visible read face swaps versions。
    async with AsyncSessionLocal() as db:
        await archive_outputs(db, [oid])
        newborn = Output(
            project_id=uuid.UUID(pid),
            workflow_step_id=None,
            type="clip",
            language="en",
            provenance="real",
            payload={"duration": 28},
            render_spec=spec,
            work_id=work_id,  # 按位继承 — the wipe's birth-loop shape
        )
        db.add(newborn)
        await db.flush()
        newborn_id = newborn.id
        await db.commit()
    async with AsyncSessionLocal() as db:
        pub = (
            await db.execute(
                select(func.count()).select_from(Publication).where(
                    Publication.output_id == oid
                )
            )
        ).scalar_one()
        check(pub == 1, "publication survives the archive (不连坐)", pub)
        ops_count = (
            await db.execute(
                select(func.count()).select_from(Operation).where(
                    Operation.output_id == oid
                )
            )
        ).scalar_one()
        check(ops_count >= 2, "the operations journal survives", ops_count)
    res = await ctx.client.get(f"/outputs/{oid}/operations")
    check(res.status_code == 200, "the archived row's journal stays readable",
          res.status_code)
    res = await ctx.client.get(f"/projects/{pid}/results")
    check(res.status_code == 200, "results reads", res.text)
    visible_ids = [o["id"] for o in res.json().get("outputs", [])]
    check(str(oid) not in visible_ids, "the archived version leaves the read face",
          visible_ids)
    check(str(newborn_id) in visible_ids, "the successor is the visible version",
          visible_ids)

    # ④b 归档不可变: the archived row is read-only history — every public
    #    mutate door refuses with 409 while the journal stays readable. The
    #    ONLY way back to mutable is the 换态 below。
    res = await ctx.client.post(
        f"/outputs/{oid}/operations",
        json={"ops": [{"op": "set_title", "params": {"text": "tamper", "enabled": True}}]},
    )
    check(res.status_code == 409, "archived row rejects op writes", res.text)
    res = await ctx.client.post(f"/outputs/{oid}/operations/undo")
    check(res.status_code == 409, "archived row rejects undo", res.text)
    res = await ctx.client.put(f"/outputs/{oid}", json={"payload": {"title": "tamper"}})
    check(res.status_code == 409, "archived row rejects PUT", res.text)
    res = await ctx.client.post(f"/outputs/{oid}/regenerate", json={})
    check(res.status_code == 409, "archived row rejects regenerate", res.text)

    # ⑤ 换态: restore the archived version — it becomes the work's ONE active
    #    row; the successor archives. A second restore on the now-active row
    #    refuses (400)。
    res = await ctx.client.post(f"/outputs/{oid}/restore")
    check(res.status_code == 200, "restore 换态 applies", res.text)
    async with AsyncSessionLocal() as db:
        rows = list(
            (
                await db.execute(
                    select(Output).where(Output.work_id == work_id)
                )
            ).scalars().all()
        )
        actives = [r for r in rows if r.archived_at is None]
        check(len(actives) == 1 and actives[0].id == oid,
              "同 work 内至多一 active — the restored row", rows)
    res = await ctx.client.post(f"/outputs/{oid}/restore")
    check(res.status_code == 400, "restoring the active row refuses",
          res.status_code)
    res = await ctx.client.get(f"/projects/{pid}/results")
    visible_ids = [o["id"] for o in res.json().get("outputs", [])]
    check(str(oid) in visible_ids and str(newborn_id) not in visible_ids,
          "the read face follows the 换态", visible_ids)


async def s8_interview_to_framing(ctx: Ctx) -> None:
    """S8 访谈→分镜（需 dev worker + demo 桶 fixture + MiniMax 配额）：访谈
    素材真处理（worker 真 ASR + speaker_map → form=interview 前提断言）→
    用户口头选定分镜方向（「镜头跟着说话人切换」）→ dock 呈现即开工（auto
    档，ADR-117 §2）→ plan 链必含 select_clips + reframe_clip（选择执行律）
    → run completed → 成片 render_spec 带非空 crop_track（确定性尾——选了
    就要像配方卡那样成片，静默中央裁剪的结构通路在此锁死）。中间（router
    直接出书还是先问）是 LLM 裁量，nudge 有界兜底，红了 = prompt 回归信号。
    fixture 律：素材先拷 scenario/ 前缀隔离 + 显式 request_processing 盖章
    （ADR-102 休眠律——无盖章 worker 永不认领）。"""
    fixture_prefix = f"scenario/s8-{uuid.uuid4().hex[:8]}"
    src_key = await copy_fixture(INTERVIEW_SOURCE_KEY, fixture_prefix)
    pid = await ctx.new_project("S8 interview framing")
    src = await seed_asset(
        pid, ctx.user_id, AssetType.VIDEO, "xy_1_interview_15s.mp4",
        file_url=src_key,  # PENDING — the worker really ASRs + speaker-maps it
        request_processing=True,  # ADR-102 休眠律：fixture 自证盖章
    )
    status = await wait_asset_status(
        src, {AssetStatus.COMPLETED, AssetStatus.FAILED}
    )
    check(status == AssetStatus.COMPLETED,
          "the interview fixture is really processed (ASR + speaker_map)", status)
    async with AsyncSessionLocal() as db:
        asset = await db.get(Asset, uuid.UUID(src))
        speaker_map = (asset.meta or {}).get("speaker_map") or {}
    check(speaker_map.get("form") == "interview"
          and bool(speaker_map.get("turns")),
          "the seat's premise: the fixture judges interview-form with "
          "attributed turns (the bake's proven source)",
          speaker_map.get("form"))

    await topup_wallet(ctx.user_id)  # clips + reframe + render 真链
    # 默认档钉住（Ctx 全矩阵共享一个 user——S3/S4/S5 会把档翻去 ask）。
    await ctx.set_confirmation(execution="auto", credits="auto")

    # 用户口头选定分镜方向——选择执行律：链必含 select_clips + reframe_clip。
    # auto 档（ADR-117 §2）：dock 回合呈现即开工（settled+born 同信封，零
    # 确认拍）；守卫线/不可报价 held 时口头确认拍补一枪（任何档恒问一次的
    # 合法分支）。开工即清 pending_brief——链读 settled 行的 intent 列。
    turn_dock = await ctx.chat(pid, "把我的双人访谈剪成竖屏短片，镜头跟着说话人切换。")
    for _ in range(2):
        if turn_dock["run_id"] is not None or is_plan_dock(turn_dock["assistant_message"]):
            break
        # LLM 裁量兜底（先问了 caption/数量等）——一句推进，路由恒在 plan path。
        turn_dock = await ctx.chat(pid, "就按这个方向出计划吧——竖屏切片，镜头跟人。")
    born_at_dock = turn_dock["run_id"] is not None
    if not born_at_dock:
        check(is_plan_dock(turn_dock["assistant_message"]),
              "the framing-chosen turns dock the plan",
              turn_dock["assistant_message"])
        turn_dock = await ctx.chat(pid, "开始吧")
    aq = turn_dock.get("answered_question")
    check(turn_dock["run_id"] is not None and aq is not None
          and ((aq.get("question") or {}).get("kind") == "task_book"),
          "the dock settles AND the run is born (auto 档: born at the dock "
          "turn itself; held 分支: born at the guardrail confirm beat)",
          turn_dock)
    check((aq.get("answer") or {}).get("kind") == "start",
          "the start lands kind=start", aq.get("answer"))
    if born_at_dock:
        check(((aq.get("question") or {}).get("requires_confirmation")) is False,
              "auto 档戳记 = 零确认拍（requires_confirmation=False at dock）",
              aq.get("question"))
        s8_run_ctx = (await run_row(turn_dock["run_id"]))["context"]
        check((s8_run_ctx.get("confirmed_scope") or {}).get("confirmed_via") == "auto",
              "confirmed_via = auto（呈现即开工的常驻授权戳）",
              s8_run_ctx.get("confirmed_scope"))
    tools = [t.get("tool") for t in ((aq.get("intent") or {}).get("tasks") or [])]
    check("select_clips" in tools and "reframe_clip" in tools,
          "选择执行律：the chosen framing direction lands select_clips + "
          "reframe_clip (never a silent center-crop chain)", tools)
    check(tools.index("reframe_clip") > tools.index("select_clips"),
          "the reframe rides after the clips producer (topology order)", tools)
    run_id = turn_dock["run_id"]

    final = await wait_run_terminal(run_id, timeout=600.0)
    check(final == "completed",
          "the framing run completes on the real interview bytes", final)
    reframe_step = next(
        (s for s in await step_rows(run_id) if s["kind"] == "reframe_clip"), None
    )
    check(reframe_step is not None and reframe_step["status"] == "done",
          "the reframe step ran and completed", reframe_step)
    clips = await outputs_of(pid, "clip")
    check(len(clips) >= 1, "the clips land", len(clips))
    check(
        any((o.render_spec or {}).get("crop_track") for o in clips),
        "确定性尾：at least one clip's render_spec carries a real crop_track "
        "(选了就要像配方卡那样成片——静默中央裁剪永禁)",
        [(str(o.id), len((o.render_spec or {}).get("crop_track") or [])) for o in clips],
    )

    # Harness 卫生（非断言——S3 同款）：run 收官的触发回合是
    # fire-and-forget；不消费它就 cleanup 会让在飞 LLM 调用撞上项目删除。
    review = await wait_trigger_review(ctx, turn_dock["conversation_id"], run_id,
                                       timeout=90.0)
    if review is not None and (review.get("question") or {}).get("kind") == "question":
        await ctx.answer(review["id"], {"kind": "bail"})


async def s9_credits_boundary(ctx: Ctx) -> None:
    """S9 付费边界：钱包置零 → dock 计划 → typed Start 收结构化 422
    {code, balance, required}（/generate 同形同义）→ 零 run、零台账行
    （hold 与 run 同事务回滚）；不可证载荷 scope.unproven 门先于余额检查
    开火；负余额用户下一次 hold 必拒——含 0 元 hold（gate at the start）；
    活跃 run 时 Start 服务端 machine-readable 阻断（前端按钮 disabled 只是
    第一道防线），被阻的 Start 永不生 run。"""
    # 专用 fixture 用户：钱包手工置零——不动共享 ctx 用户的余额（S2 等
    # 剧本还要起真 run）；结束后清台账/钱包行（FK 序）。
    user_id = await make_user()
    local = Ctx(user_id, keep=False)
    try:
        # ask 档钉住（ADR-117——本旅程的 typed Start / 422 门断言全是确认拍族；
        # 默认 auto 档下 dock 回合的 auto-drive 会在零余额门上 held，断言虽同形
        # 通过，钉住消除该变量）。
        await local.set_confirmation(execution="ask", credits="ask")
        async with AsyncSessionLocal() as db:
            db.add(Wallet(user_id=user_id, balance=0))
            await db.commit()

        # 账户控制台 credits 槽的供给端：GET /wallet 必须真服务。
        res_w = await local.client.get("/wallet")
        check(res_w.status_code == 200
              and (res_w.json() or {}).get("balance") == 0,
              "GET /wallet serves the console credits slot", res_w.text)

        pid = await local.new_project("S9 credits 422")
        # 素材要够实——单行文字稿触发模型「无可引用」的诚实拒 dock 轮盘
        # （实测 1/2 概率），而本本的断言对象是 422 载荷，不是 dock 边界裁量。
        await seed_asset(pid, user_id, AssetType.TRANSCRIPT, "talk.txt",
                         extracted_text=(
                             "My talk about grid storage auctions: why the "
                             "capacity market pays for availability, how the "
                             "auction clearing price is set, and what last "
                             "year's three price spikes taught operators about "
                             "bidding strategy."
                         ),
                         processed=True)
        turn1 = await local.chat(pid, "write a LinkedIn post from my talk")
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

        # /generate 的 tasks 载荷必须是服务端可证的 approved retry——先种一条
        # 已确认历史链（本请求正是它的 exact retry），门放行后出生地的
        # credits 422 才是本断言的目标。
        async with AsyncSessionLocal() as db:
            db.add(
                WorkflowRun(
                    project_id=uuid.UUID(pid),
                    status=WorkflowStatus.COMPLETED,
                    context={
                        "tasks": [{"tool": "write_post", "params": {"language": "en"}}],
                        "target_language": "en",
                        "scope": "full",
                        "operation": "regenerate",
                    },
                )
            )
            await db.commit()

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

        # 不可证载荷 → machine-readable 422 scope.unproven，永不 create_run——
        # 门先于余额检查开火（不可证即拒，与余额无关），run 计数恒等于刚种的 1。
        res3 = await local.client.post(
            f"/projects/{pid}/generate",
            json={
                "tasks": [{"tool": "write_post", "params": {"language": "fr"}}],
                "target_language": "fr",
            },
        )
        check(res3.status_code == 422,
              "/generate unproven chain is a 422", res3.text)
        detail3 = (res3.json() or {}).get("detail") or {}
        check(detail3.get("code") == "scope.unproven"
              and "no_exact_retry" in (detail3.get("reasons") or []),
              "the unproven payload is machine-readable", detail3)
        check(await count_runs(pid) == 1,
              "the unproven request never reaches the birthplace", None)

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

        # 负余额 hold 必拒——含 0 元 hold。
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

        # Start 服务端四合取强制——活跃 run 冲突时服务端 machine-readable
        # 阻断；被阻的 Start 永不生 run（计数恒 = 历史 1 + 活跃 1）。
        await seed_active_run(pid)
        res4 = await local.answer(turn1["assistant_message"]["id"], {"kind": "start"})
        check(res4.status_code == 422,
              "typed Start is server-blocked on an active run", res4.text)
        detail4 = (res4.json() or {}).get("detail") or {}
        check(detail4.get("code") == "start.blocked"
              and "active_run" in (detail4.get("blockers") or []),
              "the Start blocker is machine-readable", detail4)
        check(await count_runs(pid) == 2, "the blocked Start births no run", None)
    finally:
        await local.cleanup()
        await local.close()
        async with AsyncSessionLocal() as db:
            await db.execute(
                delete(CreditTransaction).where(CreditTransaction.user_id == user_id)
            )
            await db.execute(delete(Wallet).where(Wallet.user_id == user_id))
            await db.commit()


async def s10_remix_flagship(ctx: Ctx) -> None:
    """S10 Remix 旗舰（需 dev worker + demo 桶 fixture + MiniMax 配额）：
    P1 warm 路径（ask 档钉住——零 run 成本前提的结构保障：直接 dock 的合法
    分支在 auto 档会同拍开工，破坏该前提）——@mention 指认参考片（免问路，
    pin 由代码结算）→ pin 落定即拆解，agent 主动说看懂了案例；P2 run 路径
    （auto 档，ADR-117 §2——dock 呈现即开工，零确认拍）——两视频 + 一句
    「做成案例那样子」→ mention pin → dock 同拍 start → decompile 新鲜物化
    （参考片 seeded 为 FAILED 处理态 = warm 永不点火的现实形态——run 路径
    不看处理态只读字节）→ 触发回合说话 → 产物参数 = 骨架（条数/画幅/字幕
    色三断）→ 画布无 decompile 孤儿节点。角色提问机器一路（router 主动问
    asset_role）是 LLM 裁量，不做 e2e 锁定。复用不重复发声由结构锁住
    （reuse 早退在火前）+ (conversation, trigger, ref) 去重，本剧本末尾
    断言消息恰一条。P1 合法分支：mention 回合直接 dock 计划（LLM 裁量）→
    warm review 准入依法静默（ADR-080 永不压 docked plan——计划 echo 已经
    叙事），该面锁 pin 落账、review 等待合法跳过；无 dock 的回合锁
    「主动说看懂了案例」。"""
    fixture_prefix = f"scenario/s10-{uuid.uuid4().hex[:8]}"
    src_key = await copy_fixture(REMIX_SOURCE_KEY, fixture_prefix)
    ex_key = await copy_fixture(REMIX_EXEMPLAR_KEY, fixture_prefix)
    # ---- P1: warm 路径 —— pin 落定即拆解、主动说话（无 run） ------------------
    # ask 档钉住（ADR-117——P1 前提是零 run 成本：LLM 裁量的直接 dock 分支在
    # auto 档会呈现即开工；钉 ask 让 dock 恒等用户的拍，两个合法分支形态不
    # 变）。P2 开工前再翻回 auto。
    # 消歧走 @mention 指认：角色 pin 由代码结算，不依赖 LLM 是否选择提问——
    # 提问机器一路的 dock 决策是 LLM 裁量，e2e 只锁确定性路径。
    await ctx.set_confirmation(execution="ask", credits="ask")
    pid1 = await ctx.new_project("S10-P1 warm path")
    src1 = await seed_asset(
        pid1, ctx.user_id, AssetType.VIDEO, "s10-p1-source.mp4", processed=True
    )
    ex1 = await seed_asset(
        pid1,
        ctx.user_id,
        AssetType.VIDEO,
        "highlight-clips-preview.mp4",
        processed=True,
        file_url=ex_key,
    )
    # fixture 纪律（S4/S9 同族轮盘）：src1 无真字节，模型「先读源片再承诺」
    # 是合法路——无 understanding 行时诚实读路拿到 _WARM_DEAD_TEXT / failed
    # 观察，依法拒 dock（pin 永不落账，红）。seed_understanding 让先读路与
    # 乐观 dock 路都通（digest 覆盖全项目素材集，与观察的 reuse 键同构）。
    await seed_understanding(pid1)
    turn1 = await ctx.chat(
        pid1,
        "你能帮我把我的原视频做成 @参考案例 那样子吗？",
        mentions=[{"type": "asset", "id": ex1, "label": "highlight-clips-preview.mp4"}],
    )
    conv1 = turn1["conversation_id"]
    brief1 = (await ctx.results(pid1)).get("pending_brief") or {}
    # The pin persists on the first PendingPlan WRITE — a bare-answer turn
    # writes nothing and the pin evaporates with it. Re-mention on each
    # continuation until a write lands (bounded — three prose-only turns =
    # stuck, fail loud).
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
          "the @mention pins the exemplar by code (免问路)",
          {"brief": brief1,
           "last_content": (turn1["assistant_message"].get("content") or "")[:200]})
    # pin 落定（随 PendingPlan 写入）→ warm 拆解（fire-and-forget）→ 触发回合
    # 主动说话。合法分支：pin 落账回合直接 dock 了计划 = warm review 准入
    # 依法静默（ADR-080 永不压 docked plan——计划 echo 已经叙事），该面锁
    # pin 落账 + dock 形态即走完 P1；无 dock 的回合照旧锁主动发言。
    if is_plan_dock(turn1["assistant_message"]):
        check(brief1.get("intent") is not None,
              "the mention turn docked the plan — the warm review's silence "
              "is lawful (ADR-080: never talk over a docked plan)",
              brief1)
    else:
        review1 = await wait_trigger_review(ctx, conv1, ex1, timeout=240.0)
        check(review1 is not None,
              "the warm path's decompile speaks (「我看了你的案例」)", ex1)
        rintent1 = (review1 or {}).get("intent") or {}
        check(rintent1.get("trigger") == "craft_decompiled" and rintent1.get("ref") == ex1,
              "the warm review dump names trigger + exemplar ref", rintent1)
        check(bool(((review1 or {}).get("content") or "").strip()),
              "the agent's case understanding is spoken, not silent", review1)

    # ---- P2: run 路径 —— 新鲜物化必发声 + exemplar 参数 + 画布孤儿修复 ----
    pid2 = await ctx.new_project("S10-P2 run path")
    src2 = await seed_asset(
        pid2, ctx.user_id, AssetType.VIDEO, "demo_talk.mp4",
        file_url=src_key,  # PENDING — the worker really ASRs it
        request_processing=True,  # ADR-102 休眠律：fixture 自证盖章
    )
    ex2 = await seed_asset(
        pid2, ctx.user_id, AssetType.VIDEO, "highlight-clips-preview.mp4",
        file_url=ex_key,
        status=AssetStatus.FAILED,  # warm 永不点火的现实形态（如参考片自身
        # ASR 失败）——run 路径不看处理态只读字节，拆解的火因此必走 run 座位。
        # 已知代价（在册，勿再「修」）：Start 门的 material gatherer 是项目级
        # any()，失败的 REFERENCE 资产也阻塞 Start（material_failed）。
    )
    src_status = await wait_asset_status(
        src2, {AssetStatus.COMPLETED, AssetStatus.FAILED}
    )
    check(src_status == AssetStatus.COMPLETED,
          "the real source asset is ASR-processed by the dev worker", src_status)
    await topup_wallet(ctx.user_id)  # remix = 全模态真链，补足避免 422 噪音

    # auto 档翻回（ADR-117 §2——run 路径：dock 呈现即开工，零确认拍；开工即
    # 清 pending_brief，pin/链改读 run.context 与 settled 行的 intent 列）。
    await ctx.set_confirmation(execution="auto", credits="auto")
    turn2 = await ctx.chat(
        pid2,
        "你能帮我把我的原视频做成 @参考案例 那样子吗？",
        mentions=[{"type": "asset", "id": ex2, "label": "highlight-clips-preview.mp4"}],
    )
    conv2 = turn2["conversation_id"]
    brief2 = (await ctx.results(pid2)).get("pending_brief") or {}
    # Same bounded re-mention recovery as P1: the pin only lands with the
    # first PendingPlan write. auto 档新增出口——dock 同拍开工（brief 即清，
    # pin 改读 run.context）。
    run_id = turn2["run_id"]
    for _ in range(3):
        if brief2.get("exemplar_asset_id") == ex2 or run_id is not None:
            break
        turn2 = await ctx.chat(
            pid2,
            "参考案例就是 @这条，继续。",
            mentions=[{"type": "asset", "id": ex2, "label": "highlight-clips-preview.mp4"}],
        )
        brief2 = (await ctx.results(pid2)).get("pending_brief") or {}
        run_id = turn2["run_id"]
    if run_id is not None:
        pinned2 = (await run_row(run_id))["context"].get("exemplar_asset_id") == ex2
    else:
        pinned2 = brief2.get("exemplar_asset_id") == ex2
    check(pinned2,
          "P2's @mention pins the exemplar by code",
          {"brief": brief2, "terminal": terminal_tool_of(turn2),
           "run_id": run_id,
           "question": (turn2["assistant_message"].get("question") or {}),
           "content_head": (turn2["assistant_message"].get("content") or "")[:200]})

    # 计划 dock：mention 回合可能直接出书（auto 档同拍开工）；若路由仍 dock
    # 了角色问（mention 的 pin 已随写入落账，问题只是再确认），按选项答掉它
    # （答复同样代码落 pin），再回推到出书。held 分支（守卫线/不可报价——
    # ADR-117 §4 任何档恒问一次）留在 dock 等待态，下方口头确认拍开工。
    follow = turn2["assistant_message"]
    q2 = follow.get("question") or {}
    if run_id is None and q2.get("kind") == "question" and q2.get("slot") == "asset_role":
        ans2 = await ctx.answer(follow["id"], {"kind": "option", "option_id": src2})
        check(ans2.status_code in (200, 201), "P2's role answer settles", ans2.text)
        follow = ans2.json().get("follow_up") or {}
        if follow.get("workflow_run_id"):
            run_id = str(follow["workflow_run_id"])
    if run_id is None and not is_plan_dock(follow):
        # 显式覆盖：骨架缺席不该阻塞出书（读工具已被告知 FAILED = 直接出方案，
        # 此话术兜底 agent 仍犹豫的残差）。
        turn_dock = await ctx.chat(
            pid2, "参考片的骨架暂时拿不到也没关系——按你的判断直接出方案，不用等它。"
        )
        follow = turn_dock["assistant_message"]
        run_id = turn_dock["run_id"]
    if run_id is None:
        check(is_plan_dock(follow), "the pinned plan docks", follow)
        tasks = plan_tasks((await ctx.results(pid2)).get("pending_brief"))
        if not any(t.get("tool") == "select_clips" for t in tasks):
            # LLM 路由方差的一次纠偏——旗舰旅程的合法产物就是 clips 链。
            turn_fix = await ctx.chat(pid2, "把原视频剪成案例那样的竖屏短片")
            run_id = turn_fix["run_id"]
            if run_id is None:
                check(is_plan_dock(turn_fix["assistant_message"]),
                      "the corrective re-docks the clips plan", turn_fix)
                tasks = plan_tasks((await ctx.results(pid2)).get("pending_brief"))
            else:
                tasks = (((turn_fix.get("answered_question") or {}).get("intent")
                          or {}).get("tasks")) or []
        check(any(t.get("tool") == "select_clips" for t in tasks),
              "the remix plan carries the clips chain (旗舰旅程的合法链)", tasks)
    else:
        born_tasks = ((await run_row(run_id))["context"].get("tasks")) or []
        check(any(t.get("tool") == "select_clips" for t in born_tasks),
              "auto 档 dock 即开工——链在出生时已定（错链开工 = router 回归"
              "信号）", born_tasks)
    graph2 = await ctx.graph(pid2)
    check(no_decompile_canvas_node(graph2),
          "decompile never reads back as a canvas node (draft or live)",
          graph2["nodes"])

    held_confirm = run_id is None
    if held_confirm:
        # held 分支——守卫线/不可报价的口头确认拍（与 Start 钮同一机器）。
        turn3 = await ctx.chat(pid2, "looks good, start")
        check(terminal_tool_of(turn3) == "start_run",
              "the guardrail confirm closes on start_run", turn3)
        run_id = turn3["run_id"]
    check(run_id is not None, "the remix run is born", None)
    run_ctx = (await run_row(run_id))["context"]
    check(run_ctx.get("exemplar_asset_id") == ex2,
          "the exemplar pin rides run.context into the run — source stays "
          "None on the mention path (两视频项目素材由 exemplar 排除法确定性解析)",
          run_ctx)
    if not held_confirm:
        check((run_ctx.get("confirmed_scope") or {}).get("confirmed_via") == "auto",
              "confirmed_via = auto（呈现即开工的常驻授权戳）",
              run_ctx.get("confirmed_scope"))

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

    # run 路径拆解 → 触发回合说话（与 warm 同权）；恰一条（复用不重复发声的
    # 结构锁 + 去重在本项目内同 ref 恒一条）。
    review2 = await wait_trigger_review(ctx, conv2, ex2, timeout=240.0)
    check(review2 is not None,
          "the RUN path's fresh decompile speaks (与 warm 同权)", ex2)
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

    # 产物落库 + exemplar 参数断言（自洽读骨架行）：画幅 / 字幕色 = 代码映射
    # （确定性，严等）；条数帽 = 优先级律 explicit > exemplar > default，实现
    # 条数是 agent 的内容判断，断言只锁「不超具约束力的帽 + 至少一条」。
    clips_step = await wait_step_terminal(run_id, "select_clips", timeout=600.0)
    check(clips_step["status"] == "done",
          "the clips step completes on the real source", clips_step)
    clips = [
        o for o in await outputs_of(pid2, "clip")
        if str(o.workflow_step_id) == clips_step["id"]
    ]
    slot = (clips_step["spec"] or {}).get("slot") or {}
    explicit_count = slot.get("count") if isinstance(slot, dict) else None
    expected_cap = (
        max(1, min(10, int(explicit_count)))
        if explicit_count
        else max(1, min(10, int(skel["rhythm"]["shot_count"])))
    )
    check(1 <= len(clips) <= expected_cap,
          "clip count respects the BINDING cap (explicit slot count > skeleton cap; "
          "count_default=1 without either)",
          (len(clips), expected_cap, explicit_count, skel["rhythm"]["shot_count"]))
    specs = [o.render_spec or {} for o in clips]
    check(all(s.get("aspect") == skel["aspect"] for s in specs),
          "every clip's aspect = the skeleton's measured aspect",
          [s.get("aspect") for s in specs])
    if (skel.get("captions") or {}).get("present") and skel["captions"].get("color"):
        check(all((s.get("brand") or {}).get("caption_color") == skel["captions"]["color"]
                  for s in specs),
              "every clip's caption color = the skeleton's palette-snapped color",
              [(s.get("brand") or {}).get("caption_color") for s in specs])

    # 终态：run 图无 decompile 孤儿节点；decompile 步骤骑 task book 内部族。
    filled_graph = await ctx.graph(pid2)
    check(no_decompile_canvas_node(filled_graph),
          "the run-filled graph carries NO decompile orphan node",
          filled_graph["nodes"])


S11_URL = "https://linear.app"  # D3-proven stable real site (example.com is DNS-polluted on this network)


async def s11_url_to_launch_film(ctx: Ctx) -> None:
    """S11 贴链成片全旅程（MG D4；需活栈 + dev worker 真采集真渲染 + MiniMax
    配额）：用户贴 URL → material_urls 信封座 absorb 生 web_page 资产 →
    worker 真采集 COMPLETED（浏览器级 SSRF 链）→ 分镜方案 dock（链必含
    launch_film——选择执行律同族）→ auto 档守卫线带价问一次 → 口头 yes
    开工（与 Start 钮同一机器）→ run completed → 血缘三形态：web_page 资产
    节点 → launch_film 节点（video × generator）驮 film 产物 + launch_film/
    render 双 step done → film 产物 render COMPLETED + files.video 在场
    （产物文件本体由 probe 闸兜底——一法一座，剧本不重复 probe）→ 台账
    hold = capture + release（计价幂等形态锁）。打回穷举 = 机制合法终态：
    锁闸②反面形态（FAILED + spec.failure codes）后走真实 retry 旅程，
    连续两次穷举才红（打回率回归信号，非 flake）。只锁形态不锁文案；目标
    站不可达/采集失败 = 环境 flake，按归因纪律处置（禁调断言放行）。"""
    pid = await ctx.new_project("S11 url to launch film")
    await topup_wallet(ctx.user_id)  # launch_film 编排 + 渲染真链

    turn1 = await ctx.chat(pid, f"Turn this page into a short launch film: {S11_URL}")

    # material_urls absorb（ADR-119 §5）：web_page 资产行随回合出生——LLM
    # 判定链接是素材（禁启发式），出生与否本身就是形态断言。
    asset_id: str | None = None
    deadline = asyncio.get_event_loop().time() + 60.0
    while asyncio.get_event_loop().time() < deadline:
        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    select(Asset)
                    .where(
                        Asset.project_id == uuid.UUID(pid),
                        Asset.type == AssetType.WEB_PAGE,
                    )
                    .order_by(Asset.created_at)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if row is not None:
                asset_id = str(row.id)
                break
        await asyncio.sleep(2)
    check(asset_id is not None,
          "the pasted URL births a web_page asset (material_urls absorb)", None)

    # worker 真采集（真站 linear.app）：FAILED = 环境 flake 或采集链回归，
    # 都按机制红处置。
    status = await wait_asset_status(
        asset_id, {AssetStatus.COMPLETED, AssetStatus.FAILED}
    )
    check(status == AssetStatus.COMPLETED,
          "the web_page capture completes on the real site", status)

    # 分镜方案 dock（plan/dock 形态）；LLM 裁量（先问一句）有界兜底一回。
    plan = await pending_plan(ctx, pid)
    if not (plan is not None and plan_tasks(plan)):
        turn1 = await ctx.chat(pid, "Go ahead — plan the launch film from that page.")
        plan = await pending_plan(ctx, pid)
    check(plan is not None and plan_tasks(plan),
          "the URL turn docks the storyboard plan", plan)
    tools = [t.get("tool") for t in plan_tasks(plan)]
    check("launch_film" in tools,
          "the docked chain carries launch_film (the film family's one node)", tools)

    # auto 档：守卫线（带价族）恒问一次——口头 yes 走普通 chat 道到
    # start_run；若回合已直开（propose→start_run 同回合标准道）则顺势。
    run_id = turn1.get("run_id")
    if run_id is None:
        turn_s = await ctx.chat(pid, "Yes — go ahead.")
        check(terminal_tool_of(turn_s) == "start_run",
              "the verbal yes closes on start_run (Start 钮同一机器)", turn_s)
        run_id = turn_s["run_id"]
        conv_id = turn_s["conversation_id"]
    else:
        conv_id = turn1["conversation_id"]
    check(run_id is not None, "the film run is born", turn1)

    # 真渲染全链（采集已齐 → launch_film 编排（有界打回 ≤3 候选）→ 渲染 +
    # probe 闸）：15-30s 片 ≈1.75×实时 + LLM 编排，900s 是宽车道。
    final = await wait_run_terminal(run_id, timeout=900.0)
    if final == "TIMEOUT":
        check(False, "the launch-film run settles within the wide lane", final)
    if final != "completed":
        # 失败终态两族分流：① 打回穷举（validator 合法终态）——launch_film
        # step FAILED 且 spec.failure 带 stage（grounding 族必带 codes），
        # 闸②反面形态锁只约束这一族；② 无 stamp = 基建崩溃族（transport/IO
        # 越过 tenacity——归因面 = worker 日志 + 台账 unattributed 桶，形态
        # 锁不适用）。两族都走真实用户 retry 旅程。
        steps = await step_rows(run_id)
        film_step = next((s for s in steps if s["kind"] == "launch_film"), None)
        failure = ((film_step or {}).get("spec") or {}).get("failure") or {}
        if failure:
            check(film_step is not None and film_step["status"] == "failed"
                  and bool(failure.get("stage")),
                  "闸②反面形态：an exhausted storyboard settles FAILED with "
                  "structured spec.failure (禁盲重试)", film_step)
            if failure.get("stage") == "grounding":
                check(bool(failure.get("codes")),
                      "grounding 穷举必带结构化 codes（台账归因面）", failure)
        # 用户 retry 旅程（一句话再来一次 → 新 run）。先消费失败 run 的
        # 触发回合——它若在 dock 上挂着问题，retry chat 会撞一行一答 409。
        review = await wait_trigger_review(ctx, conv_id, run_id, timeout=45.0)
        if review is not None and (review.get("question") or {}).get("kind") == "question":
            await ctx.answer(review["id"], {"kind": "bail"})
        turn_r = await ctx.chat(pid, "That didn't work — please try the film again.")
        run_id = turn_r.get("run_id")
        if run_id is None:
            plan = await pending_plan(ctx, pid)
            check(plan is not None and plan_tasks(plan),
                  "the retry turn re-docks a plan", plan)
            turn_r = await ctx.chat(pid, "Yes — go ahead.")
            check(terminal_tool_of(turn_r) == "start_run",
                  "the retry confirm closes on start_run", turn_r)
            run_id = turn_r.get("run_id")
        check(run_id is not None, "the retry run is born", turn_r)
        conv_id = turn_r["conversation_id"]
        final = await wait_run_terminal(run_id, timeout=900.0)
        # 连续两次穷举 ≈ 打回率回归信号（D2 基线一次通过 4/6），不是 flake——
        # 红了读 prompt/manifest 覆盖面，禁调断言放行。
        check(final == "completed",
              "the retry run completes (two consecutive grounding exhaustions "
              "= 打回率回归信号, not flake)", final)

    steps = await step_rows(run_id)
    film_step = next((s for s in steps if s["kind"] == "launch_film"), None)
    render_step = next((s for s in steps if s["kind"] == "render"), None)
    check(film_step is not None and film_step["status"] == "done",
          "the launch_film step ran done (grounding 闸通过——穷举终态会带 spec.failure)",
          film_step)
    check(render_step is not None and render_step["status"] == "done",
          "the render step ran done (probe 闸通过——未过校验不算成功)", render_step)

    films = await outputs_of(pid, "film")
    check(len(films) >= 1, "the film output lands", len(films))
    film = films[0]
    check(film.provenance == "generated",
          "ADR-026: the film's provenance is generated", film.provenance)
    check(film.render_status == RenderStatus.COMPLETED
          and bool((film.files or {}).get("video")),
          "the film artifact is COMPLETED with a video object (probe-gated)",
          (str(film.render_status), film.render_error))

    # 画布血缘形态：web_page 素材节点 → launch_film 装配节点（video ×
    # generator，产物驮在卡上）。
    graph = await ctx.graph(pid)
    nodes = graph.get("nodes") or []
    film_node = next(
        (n for n in nodes if (n.get("spec") or {}).get("tool") == "launch_film"), None
    )
    check(film_node is not None and film_node.get("type") == "video"
          and (film_node.get("spec") or {}).get("prototype") == "generator",
          "the canvas carries the film assembly node as video × generator", film_node)
    asset_node = next(
        (n for n in nodes
         if (n.get("spec") or {}).get("asset_type") == "web_page"
         or ((n.get("asset") or {}).get("type") == "web_page")),
        None,
    )
    check(asset_node is not None, "the canvas carries the web_page asset node", nodes)
    check(str(film.id) in [str(o) for o in (film_node.get("spec") or {}).get("output_ids") or []]
          or any(str(o.get("id")) == str(film.id) for o in film_node.get("outputs") or []),
          "the film output rides its assembly node's card", film_node.get("spec"))
    check(any(str(e.get("from_node")) == str(asset_node["id"])
              and str(e.get("to_node")) == str(film_node["id"])
              for e in graph.get("edges") or []),
          "an edge links web_page → launch_film (画布血缘)", graph.get("edges"))

    # 计价幂等形态锁（放行闸④的血缘面）：本 run 台账 hold = capture + release。
    async with AsyncSessionLocal() as db:
        txns = list(
            (
                await db.execute(
                    select(CreditTransaction)
                    .where(CreditTransaction.user_id == ctx.user_id)
                )
            ).scalars().all()
        )
    run_txns = [t for t in txns if (t.ref or {}).get("run_id") == str(run_id)]
    held = sum(-t.amount for t in run_txns if t.kind == "hold")
    captured = sum(-t.amount for t in run_txns if t.kind == "capture")
    released = sum(t.amount for t in run_txns if t.kind == "release")
    check(held > 0 and held == captured + released,
          "hold == capture + release on the film run's ledger",
          {"held": held, "captured": captured, "released": released})

    # Harness 卫生（非断言——S8 同款）：run 收官的触发回合是 fire-and-forget；
    # 不消费它就 cleanup 会让在飞 LLM 调用撞上项目删除。
    review = await wait_trigger_review(ctx, conv_id, run_id, timeout=90.0)
    if review is not None and (review.get("question") or {}).get("kind") == "question":
        await ctx.answer(review["id"], {"kind": "bail"})


async def s12_site_entry_variants(ctx: Ctx) -> None:
    """S12 网站旅程入口变体（轻本——纯 chat 回合 + 一次真网页读取，零 run
    零渲染）：① 裸求片（消息与项目都无链接）→ 先问链接（ask_user 自由问
    / answer 问句两形皆合法），永不盲 dock launch_film 计划、永不开 run；
    ② 讨论链接（「这个网站你看看？」）→ get_web_page 读帧必现 → grounded
    answer/ask，链接永不资产化（discussion ≠ material 卫生律负形）。网络
    全灭时读帧照样出现（degrade-honest——帧锁的是读动作的发生，不是抓取
    的成败）。"""
    # ① 裸求片先问链接（用户拍板的测试形态：「帮我制作一支网站介绍短片」）
    pid_a = await ctx.new_project("S12 bare film ask")
    turn1 = await ctx.chat(pid_a, "帮我制作一支网站介绍短片")
    check(terminal_tool_of(turn1) in ("ask_user", "answer"),
          "a link-less film ask closes on ask_user / answer — never a blind "
          "proposal", turn1)
    check(not is_plan_dock(turn1["assistant_message"]),
          "a link-less film ask never docks a blind launch_film plan",
          turn1["assistant_message"])
    check(turn1["run_id"] is None, "a link-less film ask starts no run", turn1)
    check(await count_runs(pid_a) == 0, "no run the whole variant", None)

    # ② 讨论链接先读页（独立项目——①的待决问若存活会吃掉②的链接语义）
    pid_b = await ctx.new_project("S12 discussion link")
    stream = await ctx.chat_stream(pid_b, f"{S11_URL} 这个网站你看看？")
    check(stream.failed is None, "the discussion-link turn never fails",
          stream.failed)
    keys = {a.get("key") for a in stream.activities}
    check("chat.inspecting.webPage" in keys,
          "a discussion link is read before answering (the read frame's key "
          "is the observable — tool names never cross the wire)", keys)
    turn2 = stream.completed
    check(terminal_tool_of(turn2) in ("answer", "ask_user"),
          "a discussion link closes on answer / ask_user — never a film "
          "proposal from a 「看看」", turn2)
    check(turn2["run_id"] is None, "a discussion link starts no run", turn2)
    check(not is_plan_dock(turn2["assistant_message"]),
          "a discussion link docks no plan", turn2["assistant_message"])
    check(has_prose(turn2["assistant_message"]), "a grounded answer lands")
    # discussion ≠ material：链接永不资产化（卫生律负形断言）
    async with AsyncSessionLocal() as db:
        pages = (
            await db.execute(
                select(Asset).where(
                    Asset.project_id == uuid.UUID(pid_b),
                    Asset.type == AssetType.WEB_PAGE,
                )
            )
        ).scalars().all()
    check(not pages,
          "a discussion link never births a web_page asset (material hygiene)",
          [str(a.id) for a in pages])

    # ③ 讨论后拍板做片（真实对话 66048d72 的延续路径）：历史回合的链接 =
    # 对话已携带的素材——永不反问（法条：never ask for a link the
    # conversation already carries），本回合诞生 web_page 资产。auto 档两
    # 形皆合法（ADR-117）：dock 待确认的计划带 launch_film，或同回合
    # propose→start_run 直开（分镜核对 hold 在 run 内 checkpoint，不在
    # run 前）。LLM 裁量（先接一句）有界兜底一回。
    turn3 = await ctx.chat(pid_b, "好，那就做它的介绍短片吧")
    plan = await pending_plan(ctx, pid_b)
    tools = [t.get("tool") for t in plan_tasks(plan)] if plan is not None else []
    run_id = turn3.get("run_id")
    if "launch_film" not in tools and run_id is None:
        turn3 = await ctx.chat(pid_b, "Go ahead — plan the intro film from that page.")
        plan = await pending_plan(ctx, pid_b)
        tools = [t.get("tool") for t in plan_tasks(plan)] if plan is not None else []
        run_id = turn3.get("run_id")
    check("launch_film" in tools or run_id is not None,
          "the history link becomes material — the chain carries launch_film "
          "(docked plan or auto-started run) without re-asking for the URL",
          {"plan": plan, "run_id": run_id})
    if run_id is not None:
        kinds = [s["kind"] for s in await step_rows(run_id)]
        check("launch_film" in kinds,
              "the auto-started run's chain carries launch_film", kinds)
    # 资产化正形：本回合诞生 web_page 资产（material_urls absorb 从历史抄链）
    asset_id = None
    for _ in range(15):
        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    select(Asset).where(
                        Asset.project_id == uuid.UUID(pid_b),
                        Asset.type == AssetType.WEB_PAGE,
                    )
                )
            ).scalars().first()
            if row is not None:
                asset_id = str(row.id)
                break
        await asyncio.sleep(2)
    check(asset_id is not None,
          "the history link births a web_page asset on the film turn "
          "(material_urls absorb from conversation history)", None)


SCENARIOS = {
    "S1": s1_lost_user_full_journey,
    "S2": s2_material_to_clips_full_chain,
    "S3": s3_material_suggestion_exploration,
    "S4": s4_no_material_writers,
    "S5": s5_research_grounds_writer,
    "S6": s6_consult_never_deadends,
    "S7": s7_second_circle_revision,
    "S8": s8_interview_to_framing,
    "S9": s9_credits_boundary,
    "S10": s10_remix_flagship,
    "S11": s11_url_to_launch_film,
    "S12": s12_site_entry_variants,
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
                # harness 公共断言（每本自动携带）：估价三断言 + repair 只一轮
                # ——进程内编译 + Agent 漏斗 stub，零 LLM 零网络。
                check_estimate_foundation()
                await check_repair_once_foundation()
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
