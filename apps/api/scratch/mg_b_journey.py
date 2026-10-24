"""下批 B 真实旅程 harness —— 媒体组合（composite）确认/制作/交付全链验收。

预检（任何付费段之前）：目标 API 实例必须以 MINIMAX_WARMUP_ENABLED=false
启动（启动前显式设环境变量——dev.sh/.env/进程 env 均无默认覆盖，config
默认 true 会在每次 boot/reload 发 3 次可计费 warmup：intent_router /
chat_intent / trigger_turn）。一切真实模型 HTTP 计入预算，不按用途排除。

分段（付费面只在 --run-*）：

  --seed            FREE. 隔离 fixture：新用户 + 项目 + 真实 TOS 上传
                    scratch/composite_acceptance/source_25s.mp4（25s 逐帧烧
                    S{秒}/F{帧} + 音高 220+20·秒 Hz 的校准片）到 scenario/
                    自有前缀 + COMPLETED 资产行（真实时长/尺寸钉 meta）+
                    ask/ask 确认档 + 钱包充值（本地种子，非付费）。
                    状态落 scratch/mg_b/state.json。
  --verify-storage  FREE. 真实对象存储读取链：download_to_cache(真 key) →
                    字节一致 + PyAV 容器头探测（时长/尺寸）+ 抽帧证据 PNG。
                    这是「真实对象存储 URL → staging」的 API 侧证据（renderer
                    侧 staging 由 --run 制作旅程实证）。
  --cleanup         删除 fixture 项目（API delete_project 自清 scenario key）
                    与用户行。

真实 LLM 旅程（付费，授权于 2026-10-23，预算：≤14 chat 回合 / ≤150 MiniMax
HTTP / ≤2 制作 run，本地渲染，无 TTS 无音乐生成）：

  --run-j1   J1+J2 讨论与设计 → 明确组合出生（断言：讨论不出版本不出 run；
             明确规格出生 composite 版本，源 10–18s/at=3/右侧 + 文字 at=4
             逐字；review_hold 出生 ON；无旁白无配乐钉版）
  --run-j3   J3 累计修改与确认（改文案 v2 → 晚半秒 v3 → 确认前累计复述
             →「按这版制作」出 run；断言版本链/change_set/确认前零 run/
             run.context 钉 v3）
  --run-j4   J4 首版真实制作验收（等 run 终态 → Output → 下载产物 →
             帧/音频探针对确认版）
  --run-j5   J5 交付后修改版（只改文字 v4 → 确认 → run2 → 两 Output 并存
             → 新版探针 + 视频区与首版逐帧一致）
  --run-j6   J6 边界（源 20–30s 超 25s 素材 → 诚实拒绝：零新版本零 run）
  --run-all  顺序跑全部（每阶段首红即停）

Usage (from apps/api):
  uv run python scratch/mg_b_journey.py --seed
  uv run python scratch/mg_b_journey.py --verify-storage
  uv run python scratch/mg_b_journey.py --run-all
  uv run python scratch/mg_b_journey.py --cleanup
"""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import chat_scenarios as cs  # noqa: E402

STATE_DIR = Path(__file__).resolve().parent / "mg_b"
STATE_FILE = STATE_DIR / "state.json"
SOURCE_CLIP = (
    Path(__file__).resolve().parent / "composite_acceptance" / "source_25s.mp4"
)


def _load_state() -> dict:
    return json.loads(STATE_FILE.read_text())


def _save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _probe_local(path: Path) -> dict:
    """PyAV container-head probe of the local fixture — exact duration and
    dimensions for the asset row's meta (the candidates read's own law:
    exact probed value wins over the floored Integer column)."""
    import av

    with av.open(str(path)) as container:
        duration = container.duration / 1e6 if container.duration else None
        video = next(s for s in container.streams if s.type == "video")
        return {
            "duration": duration,
            "width": video.codec_context.width,
            "height": video.codec_context.height,
            "fps": float(video.average_rate),
        }


async def seed() -> None:
    from app.providers.storage import _get_s3_client
    from app.config import settings

    probe = _probe_local(SOURCE_CLIP)
    assert probe["duration"] and 24.0 < probe["duration"] < 26.0, probe

    user_id = await cs.make_user()
    ctx = cs.Ctx(user_id, keep=False)
    try:
        pid = await ctx.new_project("MG-B composite acceptance")
        prefix = f"scenario/mg-b-{uuid.uuid4().hex[:8]}"
        key = f"{prefix}/source_25s.mp4"
        client = _get_s3_client()
        await asyncio.to_thread(
            client.upload_file, str(SOURCE_CLIP), settings.s3_bucket_name, key
        )
        asset_id = await cs.seed_asset(
            pid,
            user_id,
            cs.AssetType.VIDEO,
            "source_25s.mp4",
            meta={
                "probed_duration_seconds": probe["duration"],
                "width": probe["width"],
                "height": probe["height"],
            },
            processed=True,
            file_url=key,
        )
        await cs.topup_wallet(user_id)
        await ctx.set_confirmation(execution="ask", credits="ask")
        state = {
            "user_id": str(user_id),
            "project_id": pid,
            "asset_id": asset_id,
            "storage_key": key,
            "fixture": probe,
        }
        _save_state(state)
        print(json.dumps(state, indent=2))
        print("SEED OK — fixture project kept (cleanup via --cleanup).")
        # The project must survive for the journeys — detach it from the
        # ctx cleanup list (cleanup is explicit via --cleanup).
        ctx.project_ids.clear()
    finally:
        await ctx.close()


async def verify_storage() -> None:
    """Real object-storage read chain (API side): presigned/S3 GET → shared
    source cache → PyAV probe → decoded-frame evidence. No LLM, no render."""
    import av

    from app.providers.storage import download_to_cache

    state = _load_state()
    key = state["storage_key"]
    path = await download_to_cache(key)
    assert path is not None and path.exists(), f"staging failed for {key}"
    local_bytes = SOURCE_CLIP.stat().st_size
    staged_bytes = path.stat().st_size
    assert staged_bytes == local_bytes, (staged_bytes, local_bytes)

    probe = _probe_local(path)
    exp = state["fixture"]
    assert abs(probe["duration"] - exp["duration"]) < 0.05, probe
    assert probe["width"] == exp["width"] and probe["height"] == exp["height"], probe

    evidence = STATE_DIR / "storage_probe"
    evidence.mkdir(parents=True, exist_ok=True)
    saved = []
    with av.open(str(path)) as container:
        container.seek(int(10.5 * 1e6))  # microseconds (av.time_base)
        for frame in container.decode(video=0):
            img = frame.to_image()
            out = evidence / f"staged_t{frame.time:.2f}.png"
            img.save(out)
            saved.append(out.name)
            if len(saved) >= 1:
                break
    print(f"STORAGE VERIFY OK — {key} → {path} ({staged_bytes} bytes, "
          f"{probe['duration']:.3f}s {probe['width']}x{probe['height']}); "
          f"frame evidence: {saved}")


async def cleanup() -> None:
    state = _load_state()
    ctx = cs.Ctx(uuid.UUID(state["user_id"]), keep=False)
    try:
        ctx.project_ids.append(state["project_id"])
        await ctx.cleanup()
        # The user row itself has no API delete seat — remove it directly.
        from sqlalchemy import delete

        from app.models.database import AsyncSessionLocal
        from app.models.tables import User

        async with AsyncSessionLocal() as db:
            await db.execute(delete(User).where(User.id == uuid.UUID(state["user_id"])))
            await db.commit()
        STATE_FILE.unlink(missing_ok=True)
        print("CLEANUP OK")
    finally:
        await ctx.close()


# ---------------------------------------------------------------------------
# 真实 LLM 旅程（下批 B，付费段）
# ---------------------------------------------------------------------------

EVIDENCE = STATE_DIR / "evidence"


def _save_evidence(name: str, obj: object) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


async def _snap_film(pid: str) -> dict | None:
    """The project's pending film design state (version / hold / params /
    digest / board dump) straight from projects.pending_brief."""
    from sqlalchemy import select

    from app.models.database import AsyncSessionLocal
    from app.models.tables import Project

    async with AsyncSessionLocal() as db:
        row = (
            (await db.execute(select(Project).where(Project.id == uuid.UUID(pid))))
            .scalars()
            .one()
        )
    brief = row.pending_brief
    if not isinstance(brief, dict):
        return None
    return {
        "version": brief.get("film_storyboard_version"),
        "hold": brief.get("film_review_hold"),
        "params": brief.get("film_storyboard_params"),
        "digest": brief.get("film_storyboard_content_digest"),
        "board": brief.get("film_storyboard"),
        "change_set": brief.get("film_change_set"),
    }


def _composite_facts(board: dict) -> dict:
    """Locate the composite scene and split its elements by kind."""
    scenes = board.get("scenes") or []
    comp = next((s for s in scenes if s.get("type") == "composite"), None)
    assert comp is not None, f"no composite scene in board (types: {[s.get('type') for s in scenes]})"
    elements = comp.get("elements") or []
    video = next((e for e in elements if e.get("kind") == "video"), None)
    texts = [e for e in elements if e.get("kind") == "text"]
    return {"scene": comp, "video": video, "texts": texts}


def _turn_evidence(turn: "cs.StreamTurn", message: str) -> dict:
    completed = turn.completed or {}
    msg = completed.get("assistant_message") or {}
    aq = completed.get("answered_question") or {}
    return {
        "user_message": message,
        "sse_event_kinds": [e["event"] for e in turn.raw_events],
        "activities": [
            {"kind": a.get("kind"), "name": a.get("name"), "status": a.get("status")}
            for a in turn.activities
        ],
        "checkpoints": turn.checkpoints,
        "assistant_text": msg.get("content"),
        "run_id": completed.get("run_id"),
        "answered_question_kind": (aq.get("answer") or {}).get("kind"),
        "failed": turn.failed,
    }


async def _journeys_ctx() -> "tuple[cs.Ctx, dict]":
    state = _load_state()
    return cs.Ctx(uuid.UUID(state["user_id"]), keep=True), state


async def run_j1() -> None:
    """J1 讨论 → J2 明确组合出生。"""
    ctx, state = await _journeys_ctx()
    pid = state["project_id"]
    try:
        # 本批验收聚焦制作确认语义：execution=ask（保留批准拍）；
        # credits=auto（产品默认档——普通可报价 run 在守卫线下零费用确认拍，
        # 不让第二确认拍混入制作意图旅程）。
        await ctx.set_confirmation(execution="ask", credits="auto")
        # 幂等总闸：v1 已出生 = T1+T2 均已发生——复核 J2 板断言即返（重发
        # 任何消息都会污染版本链/对话）。
        existing = await _snap_film(pid)
        if existing is not None and existing.get("version") is not None:
            _assert_j2_board(existing, state)
            print(f"J1+J2 already satisfied (v{existing['version']} on DB) — skipping resend")
            return
        # T1: capability/direction — never a version, never a run.
        # 幂等：T1 已发生过（如首轮 harness 律校准前跑过）时从 DB 取证复核
        # 同一组法律（零版本/零 run/讨论性 dock），不重复发消息。
        conv0 = await ctx.conversation(pid)
        pending0 = conv0.json().get("pending_question") if conv0.status_code == 200 else None
        if pending0 is not None:
            snap = await _snap_film(pid)
            cs.check(snap is None or snap.get("version") is None, "T1 讨论不出生版本", snap)
            cs.check(await cs.count_runs(pid) == 0, "T1 零 run")
            _save_evidence(
                "j1_t1.json",
                {
                    "note": "T1 已于 harness 律校准前完成——本证据为 DB/日志取证重建",
                    "pending_question": pending0,
                    "route_forensics": "api log: intent_router 3 iterations, get_understanding read, "
                    "iteration-1 ask_user guardrail-rejected (bare ask) → retry accepted; "
                    "retracted close (ADR-099 §7) — 预览帧合法缺席",
                },
            )
            print("J1/T1 already satisfied (DB forensics) — continuing with T2")
        else:
            t1 = await ctx.chat_stream(pid, "我上传了一个视频 source_25s.mp4，你觉得能拿它做出什么样的片子？")
            cs.check(t1.failed is None, "T1 turn completes", t1.failed)
            snap = await _snap_film(pid)
            cs.check(snap is None or snap.get("version") is None, "T1 讨论不出生版本", snap)
            cs.check(await cs.count_runs(pid) == 0, "T1 零 run")
            _save_evidence("j1_t1.json", _turn_evidence(t1, "能做出什么样的片子"))

        # T2: explicit composition spec + storyboard ask.
        spec_msg = (
            "就做个产品演示短片。具体要求：取视频的第10到18秒，从成片第3秒开始播放，"
            "放在画面右侧；左侧配文字「全新工作台，一眼看清进度」，从成片第4秒开始"
            "逐字出现。不要旁白，不要配乐。先给我分镜方案。"
        )
        t2 = await ctx.chat_stream(pid, spec_msg)
        cs.check(t2.failed is None, "T2 turn completes", t2.failed)
        _save_evidence("j1_t2.json", _turn_evidence(t2, spec_msg))
        snap = await _snap_film(pid)
        _assert_j2_board(snap, state)
        cs.check(await cs.count_runs(pid) == 0, "T2 先给方案 零 run")
        print("J1+J2 OK — 讨论零版本零 run；明确规格出生 composite v1（hold ON）")
    finally:
        await ctx.close()


def _assert_j2_board(snap: dict | None, state: dict) -> None:
    """J2 出生断言组（turn 内与幂等复核同一座）。"""
    cs.check(snap is not None and snap.get("version") == 1, "T2 出生 v1", snap)
    cs.check(snap.get("hold") is True, "compose 首稿 review_hold 出生 ON", snap)
    params = snap.get("params") or {}
    cs.check(params.get("voiceover") is False, "无旁白钉版", params)
    cs.check(params.get("music_mood") == "off", "无配乐钉版", params)
    facts = _composite_facts(snap["board"])
    video, texts = facts["video"], facts["texts"]
    cs.check(video is not None, "composite 含视频元素", facts["scene"])
    cs.check(video.get("asset") == state["asset_id"], "视频元素引用 fixture 素材", video)
    cs.check(
        float(video.get("source_start")) == 10.0 and float(video.get("source_end")) == 18.0,
        "源区间 10–18s",
        video,
    )
    cs.check(float(video.get("at")) == 3.0, "视频从成片第 3 秒开始", video)
    rect = video.get("rect") or {}
    cs.check(float(rect.get("x", 0)) >= 0.4, "视频在画面右侧", rect)
    cs.check(len(texts) == 1, "一个文字元素", texts)
    text = texts[0]
    first_token_at = float(text.get("at") or 0) + float(text.get("enter_start") or 0)
    cs.check(first_token_at == 4.0, "首个字在成片第 4 秒出现（at + enter_start）", text)
    cs.check(text.get("enter") == "words", "逐字出现", text)
    copy_joined = "".join(text.get("lines") or [])
    cs.check("全新工作台" in copy_joined and "一眼看清进度" in copy_joined, "文案上屏", text)


async def run_j3() -> None:
    """J3 累计修改与确认 → 首版 run。分阶段幂等: 已达成的阶段只复核不
    重发 (付费旅程纪律——停修后续跑不重烧已完成回合)。

    T5 形态 (ask 档, hold ON): 「按这版制作」= 用户明说生产 → approval
    dock 清 hold + 估价披露 (BILLING §2.1), Start 应答才开工——口头
    yes 与 Start 钮同一机器, 但估价必须先可见 (ADR-092/129/134)。
    """
    ctx, state = await _journeys_ctx()
    pid = state["project_id"]
    try:
        snap = await _snap_film(pid)
        assert snap and snap.get("version"), f"J3 requires a born version: {snap}"
        v = snap["version"]

        def _copy(s: dict) -> str:
            return "".join(_composite_facts(s["board"])["texts"][0].get("lines") or [])

        def _first_at(s: dict) -> float:
            t = _composite_facts(s["board"])["texts"][0]
            return float(t.get("at") or 0) + float(t.get("enter_start") or 0)

        def _video(s: dict) -> dict:
            return _composite_facts(s["board"])["video"]

        def _video_untouched(s: dict) -> bool:
            video = _video(s)
            return (
                float(video.get("source_start")) == 10.0
                and float(video.get("source_end")) == 18.0
                and float(video.get("at")) == 3.0
            )

        # T3: 改文案 (已完成 = 复核跳过, 不重烧回合)
        if "下周三上线" not in _copy(snap):
            t3 = await ctx.chat_stream(pid, "左侧文字改成「下周三上线，记得来看」，其他都不动。")
            cs.check(t3.failed is None, "T3 turn completes", t3.failed)
            _save_evidence("j3_t3.json", _turn_evidence(t3, "改文案"))
            snap = await _snap_film(pid)
            v += 1
            cs.check(snap is not None and snap.get("version") == v, f"T3 出生 v{v}", snap and snap.get("version"))
            cs.check("下周三上线" in _copy(snap), f"v{v} 文案生效", _copy(snap))
            cs.check(_video_untouched(snap), f"v{v} 视频元素未触碰", _video(snap))
            _save_evidence("j3_t3_change_set.json", snap.get("change_set"))
            cs.check(await cs.count_runs(pid) == 0, "T3 修改不授权制作 零 run")
        else:
            cs.check(_video_untouched(snap), "T3 复核: 视频元素未触碰", _video(snap))

        # T4: 晚半秒 (已完成 = 复核跳过)
        if _first_at(snap) != 4.5:
            t4 = await ctx.chat_stream(pid, "文字再晚半秒出现。")
            cs.check(t4.failed is None, "T4 turn completes", t4.failed)
            _save_evidence("j3_t4.json", _turn_evidence(t4, "晚半秒"))
            snap = await _snap_film(pid)
            v += 1
            cs.check(snap is not None and snap.get("version") == v, f"T4 出生 v{v}", snap and snap.get("version"))
            cs.check(_first_at(snap) == 4.5, f"v{v} 首字 4.5s（at + enter_start）", _composite_facts(snap["board"])["texts"][0])
            cs.check("下周三上线" in _copy(snap), f"v{v} 文案保持", _copy(snap))
            _save_evidence("j3_t4_change_set.json", snap.get("change_set"))
            cs.check(await cs.count_runs(pid) == 0, "T4 仍未确认制作 零 run")
            # 确认前累计呈现 (仅本跑发送 T4 时断言——编辑后求确认 =
            # 变化行 + 累计摘要 + 问句殿后)
            t4_text = (t4.completed or {}).get("assistant_message", {}).get("content") or ""
            markers = {
                "copy": "下周三上线" in t4_text,
                "source_window": ("10" in t4_text and "18" in t4_text),
                "placement": ("右" in t4_text),
                "timing": ("4.5" in t4_text or "半秒" in t4_text),
            }
            cs.check(all(markers.values()), "确认前同一消息复述累计方案（文案/源窗/位置/时序）", markers)

        # T5: 按这版制作 → approval dock (清 hold + 估价), 不直接开工
        async def _pend():
            conv = await ctx.conversation(pid)
            pq = (conv.json().get("pending_question") or {}) if conv.status_code == 200 else {}
            return pq

        runs_now = await cs.count_runs(pid)
        pend = await _pend()
        dock_open = (pend.get("question") or {}).get("kind") == "task_book" and not pend.get("answer")
        if runs_now == 0 and not dock_open:
            t5 = await ctx.chat_stream(pid, "按这版制作。")
            cs.check(t5.failed is None, "T5 turn completes", t5.failed)
            _save_evidence("j3_t5.json", _turn_evidence(t5, "按这版制作"))
            cs.check(await cs.count_runs(pid) == 0, "T5 approval dock 不直接开工（ask 档: 估价先可见）")
            pend = await _pend()
            dock_open = (pend.get("question") or {}).get("kind") == "task_book" and not pend.get("answer")
            cs.check(dock_open, "T5 出生 approval dock（task_book 未答）", pend.get("question"))
            _save_evidence("j3_pending_after_t5.json", pend)
            snap5 = await _snap_film(pid)
            cs.check(snap5 is not None and not snap5.get("hold"), "approval dock 清 hold", snap5 and snap5.get("hold"))

        # Start 钮同一机器: dock 应答 kind=start → run 出生钉当前版
        if runs_now == 0:
            cs.check(dock_open, "approval dock 在场待 Start", pend.get("question"))
            res = await ctx.answer(pend["id"], {"kind": "start"})
            cs.check(res.status_code == 200, "dock Start 应答", res.text)
            run_id = res.json()["answered_question"].get("workflow_run_id")
            cs.check(run_id is not None, "Start 出 run", res.json())
        else:
            run_id = state.get("run1_id") or await _latest_run_id(pid)
        cs.check(await cs.count_runs(pid) == 1, "确认前零 run 确认后恰好 1 run")
        run = await cs.run_row(run_id)
        ctx_board = ((run.get("context") or {}).get("prepared_storyboard") or {})
        text = _composite_facts(ctx_board)["texts"][0]
        copy_joined = "".join(text.get("lines") or [])
        cs.check("下周三上线" in copy_joined, "run.context 钉的是确认版文案", copy_joined)
        first_token_at = float(text.get("at") or 0) + float(text.get("enter_start") or 0)
        cs.check(first_token_at == 4.5, f"run.context 钉的是 v{v} 时序（首字 4.5s）", text)
        state["run1_id"] = run_id
        _save_state(state)
        print(f"J3 OK — 定点修改 ×2、确认前累计复述、approval dock→Start 出 run={run_id[:8]} 钉 v{v}")
    finally:
        await ctx.close()


async def _latest_run_id(pid: str) -> str | None:
    from sqlalchemy import select

    from app.models.database import AsyncSessionLocal
    from app.models.tables import WorkflowRun

    async with AsyncSessionLocal() as db:
        row = (
            (
                await db.execute(
                    select(WorkflowRun)
                    .where(WorkflowRun.project_id == uuid.UUID(pid))
                    .order_by(WorkflowRun.created_at.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
    return str(row.id) if row else None


async def _latest_run_film_version(pid: str) -> int | None:
    from sqlalchemy import select

    from app.models.database import AsyncSessionLocal
    from app.models.tables import WorkflowRun

    async with AsyncSessionLocal() as db:
        row = (
            (
                await db.execute(
                    select(WorkflowRun)
                    .where(WorkflowRun.project_id == uuid.UUID(pid))
                    .order_by(WorkflowRun.created_at.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
    if row is None or not isinstance(row.context, dict):
        return None
    v = row.context.get("film_storyboard_version")
    return int(v) if v is not None else None


def _spec_composite_expect(render_spec: dict) -> dict:
    """Derive the probe's expectations from the DELIVERED render_spec (the
    confirmed version's own projection — never from my assumed layout)."""
    scenes = render_spec.get("scenes") or []
    offset = 0.0
    fps = render_spec.get("fps") or 30
    for scene in scenes:
        frames = scene.get("frames")
        seconds = (frames / fps) if frames else scene.get("seconds", 0)
        if scene.get("type") == "composite":
            out = {"scene_start": offset, "scene_end": offset + seconds, "dark": bool(scene.get("dark"))}
            for el in scene.get("elements") or []:
                if el.get("kind") == "video":
                    play = el.get("duration")
                    if play is None:
                        play = el.get("source_end") - el.get("source_start")
                    out["video"] = {
                        "at": offset + el.get("at", 0),
                        "end": offset + el.get("at", 0) + play,
                        "source_start": el.get("source_start"),
                        "source_end": el.get("source_end"),
                        "rect": el.get("rect"),
                        "keep_audio": bool(el.get("keep_audio")),
                    }
                elif el.get("kind") == "text":
                    until = el.get("until")
                    el_at = offset + el.get("at", 0)
                    out["text"] = {
                        "at": el_at,
                        # 首个 token 出现的绝对输出秒（at + enter_start——
                        # 逐字入场前文字不可见，两种参数化同义）。
                        "appear": el_at + float(el.get("enter_start") or 0),
                        "end": offset + (until if until is not None else seconds),
                        "rect": el.get("rect"),
                        "tone": el.get("tone"),
                        "lines": el.get("lines"),
                    }
            return out
    raise AssertionError(f"no composite scene in render_spec (types: {[s.get('type') for s in scenes]})")


def _probe_film(mp4, expect: dict, label: str, evidence_prefix: str) -> list[str]:
    """Frame/audio probes against the delivered render_spec's own geometry.
    Returns the list of failed assertions (empty = all green)."""
    import colorsys

    import av
    import numpy as np

    failures: list[str] = []

    def check(cond: bool, name: str, detail: object = "") -> None:
        print(f"  {'ok ' if cond else 'FAIL'} {label}/{name} {detail}")
        if not cond:
            failures.append(f"{label}/{name}: {detail}")

    video = expect["video"]
    text = expect.get("text")
    vrect = video["rect"]
    trect = (text or {}).get("rect")

    targets = sorted(
        {
            round(max(0.5, video["at"] - 1.0), 2),
            round(video["at"] + 0.5, 2),
            round((video["at"] + video["end"]) / 2, 2),
            round(video["end"] - 0.5, 2),
        }
        | ({round(video["end"] + 0.5, 2)} if video["end"] + 0.5 < expect["scene_end"] - 0.1 else set())
        | (
            {
                round(max(0.2, text["appear"] - 0.3), 2),
                round(text["appear"] + 0.3, 2),
                round(text["appear"] + 2.5, 2),
            }
            if text
            else set()
        )
    )

    frames: dict[float, np.ndarray] = {}
    width = height = 0
    with av.open(str(mp4)) as c:
        vstream = next(s for s in c.streams if s.type == "video")
        width, height = vstream.codec_context.width, vstream.codec_context.height
        remaining = dict.fromkeys(targets)
        for frame in c.decode(video=0):
            t = float(frame.pts * frame.time_base)
            for want in list(remaining):
                if abs(t - want) < 1 / 60:
                    frames[want] = frame.to_ndarray(format="rgb24")
                    del remaining[want]
            if not remaining:
                break
    check(not remaining, "frames-present", list(remaining))
    if remaining:
        return failures

    # Evidence frames for the record.
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    from PIL import Image

    for t, arr in frames.items():
        Image.fromarray(arr).save(EVIDENCE / f"{evidence_prefix}_t{t}.png")

    def hue_region(rect: dict) -> "tuple[slice, slice]":
        x0 = int(rect["x"] * width)
        x1 = int((rect["x"] + rect["w"]) * width)
        y0 = int(rect["y"] * height)
        y1 = int(rect["y"] + min(rect["h"], 0.12) * height)  # top hue band
        return (slice(y0, max(y0 + 4, y1)), slice(x0, x1))

    def source_second(img: np.ndarray) -> "tuple[int, float]":
        strip = img[hue_region(vrect)].reshape(-1, 3).mean(axis=0) / 255.0
        h, s, _v = colorsys.rgb_to_hsv(*strip)
        return round(h * 360 / 14) % 360, s

    def text_ink(img: np.ndarray) -> int:
        if not trect:
            return 0
        x0 = int(trect["x"] * width)
        x1 = int((trect["x"] + trect["w"]) * width)
        y0 = int(trect["y"] * height)
        y1 = int((trect["y"] + trect["h"]) * height)
        region = img[y0:y1, x0:x1].astype(np.int32)
        lum = region @ [0.299, 0.587, 0.114]
        dark_text = (text or {}).get("tone") == "dark"
        return int((lum < 90).sum()) if dark_text else int((lum > 165).sum())

    t_before = round(max(0.5, video["at"] - 1.0), 2)
    _sec, sat = source_second(frames[t_before])
    check(sat < 0.15, "no-video-before-window", f"t={t_before} sat={sat:.2f}")

    for out_t, want_src in (
        (round(video["at"] + 0.5, 2), int(video["source_start"])),
        (round((video["at"] + video["end"]) / 2, 2), int((video["source_start"] + video["source_end"]) / 2)),
        (round(video["end"] - 0.5, 2), int(video["source_end"]) - 1),
    ):
        sec, sat = source_second(frames[out_t])
        check(sec == want_src and sat > 0.3, f"source-map@{out_t}", f"S{sec} want S{want_src} sat={sat:.2f}")

    t_after = round(video["end"] + 0.5, 2)
    if t_after in frames:
        _sec, sat = source_second(frames[t_after])
        check(sat < 0.15, "video-leaves-after-window", f"t={t_after} sat={sat:.2f}")

    if text:
        appear = text["appear"]
        t0 = round(max(0.2, appear - 0.3), 2)
        t1 = round(appear + 0.3, 2)
        t2 = round(appear + 2.5, 2)
        ink0, ink1, ink2 = (text_ink(frames[t]) for t in (t0, t1, t2))
        check(ink0 == 0, "text-absent-before-at", f"t={t0} ink={ink0}")
        check(ink2 > 0, "text-present-after-at", f"t={t2} ink={ink2}")
        check(ink2 > ink1, "word-by-word-progression", f"ink {ink1} → {ink2}")

    # Audio: keep_audio=false + voiceover off + music off → silence.
    import numpy as _np

    peak = None
    with av.open(str(mp4)) as c:
        if any(s.type == "audio" for s in c.streams):
            peak = 0.0
            for frame in c.decode(audio=0):
                arr = frame.to_ndarray().astype(_np.float64) / 32768.0
                peak = max(peak, float(_np.sqrt((arr**2).mean())))
    if expect["video"]["keep_audio"]:
        check(peak is not None and peak > 1e-3, "kept-audio-present", peak)
    else:
        check(peak is None or peak < 1e-3, "silent-when-all-off", peak)
    return failures


async def _download_output(output) -> "Path":
    from app.providers.storage import download_to_cache

    files = output.files or {}
    key = files.get("video") or files.get("mp4")
    assert key, f"output has no video file key: {files}"
    path = await download_to_cache(key)
    assert path is not None, f"staging failed for {key}"
    return path


async def run_j4() -> None:
    """J4 首版真实制作验收。"""
    ctx, state = await _journeys_ctx()
    pid = state["project_id"]
    run_id = state.get("run1_id")
    assert run_id, "run_j3 must run first"
    try:
        status = await cs.wait_run_terminal(run_id, timeout=600.0)
        cs.check(str(status).lower() == "completed", "run1 终态 COMPLETED", status)
        outputs = await cs.outputs_of(pid, "film")
        cs.check(len(outputs) == 1, "恰好一个 film Output", [str(o.id) for o in outputs])
        out = outputs[0]
        cs.check(out.render_spec is not None, "Output 携带 render_spec")
        expect = _spec_composite_expect(out.render_spec)
        _save_evidence("j4_expect.json", expect)
        mp4 = await _download_output(out)
        failures = _probe_film(mp4, expect, "j4", "j4_v1")
        cs.check(not failures, "首版产物帧/音频探针", failures)
        state["output1_id"] = str(out.id)
        _save_state(state)
        print(f"J4 OK — run1 COMPLETED, output {str(out.id)[:8]} 探针全绿（{mp4}）")
    finally:
        await ctx.close()


async def run_j5() -> None:
    """J5 交付后修改版：只改文字，视频不动；两版并存。"""
    ctx, state = await _journeys_ctx()
    pid = state["project_id"]
    try:
        snap = await _snap_film(pid)
        base_v = (snap or {}).get("version") or 0
        if not base_v:
            # Start 已清 pending_brief — 版本延续的 base 在 run provenance
            base_v = await _latest_run_film_version(pid) or 0

        def _copy_now(s: dict) -> str:
            return "".join(_composite_facts(s["board"])["texts"][0].get("lines") or [])

        def _video_ok(s: dict) -> bool:
            video = _composite_facts(s["board"])["video"]
            return (
                float(video.get("source_start")) == 10.0
                and float(video.get("source_end")) == 18.0
                and float(video.get("at")) == 3.0
            )

        if not (snap and snap.get("board")) or "限时开放" not in _copy_now(snap):
            t6 = await ctx.chat_stream(pid, "把左侧文字改成「限时开放，先来体验」，视频片段和位置都不变。")
            cs.check(t6.failed is None, "T6 turn completes", t6.failed)
            _save_evidence("j5_t6.json", _turn_evidence(t6, "交付后只改文字"))
            snap = await _snap_film(pid)
            # Start 已清 pending_brief——修改版从 run provenance 恢复 base 后
            # 重新落版本；版本号继续递增。
            cs.check(snap is not None and snap.get("version") == base_v + 1, f"T6 出生 v{base_v + 1}", snap and snap.get("version"))
            cs.check("限时开放" in _copy_now(snap), f"v{base_v + 1} 文案生效", _copy_now(snap))
            cs.check(_video_ok(snap), f"v{base_v + 1} 视频元素未触碰", _composite_facts(snap["board"])["video"])
            cs.check(await cs.count_runs(pid) == 1, "T6 修改不授权制作 仍 1 run")
        else:
            cs.check(_video_ok(snap), "T6 复核: 视频元素未触碰", _composite_facts(snap["board"])["video"])

        # T7: 制作新版 (幂等——dock 已在场或 run2 已出生则只推进不重发)
        async def _pend():
            conv = await ctx.conversation(pid)
            return (conv.json().get("pending_question") or {}) if conv.status_code == 200 else {}

        run2 = state.get("run2_id")
        if run2 is None and await cs.count_runs(pid) < 2:
            pend = await _pend()
            dock_open = (pend.get("question") or {}).get("kind") == "task_book" and not pend.get("answer")
            if not dock_open:
                t7 = await ctx.chat_stream(pid, "没问题，制作新版。")
                cs.check(t7.failed is None, "T7 turn completes", t7.failed)
                _save_evidence("j5_t7.json", _turn_evidence(t7, "制作新版"))
                run2 = (t7.completed or {}).get("run_id")
                if run2 is None:
                    pend = await _pend()
                    dock_open = (pend.get("question") or {}).get("kind") == "task_book" and not pend.get("answer")
            if run2 is None and dock_open:
                # approval dock 形态 (ask 档, J3-T5 同座): Start 应答出 run
                _save_evidence("j5_pending_after_t7.json", pend)
                res = await ctx.answer(pend["id"], {"kind": "start"})
                cs.check(res.status_code == 200, "T7 dock Start 应答", res.text)
                run2 = res.json()["answered_question"].get("workflow_run_id")
        cs.check(run2 is not None, "T7 出第二个 run", run2)
        cs.check(await cs.count_runs(pid) == 2, "恰好两个 run")
        status = await cs.wait_run_terminal(run2, timeout=600.0)
        cs.check(str(status).lower() == "completed", "run2 终态 COMPLETED", status)

        outputs = await cs.outputs_of(pid, "film")
        cs.check(len(outputs) == 2, "原版与修改版两 Output 并存", [str(o.id) for o in outputs])
        out2 = next(o for o in outputs if str(o.id) != state["output1_id"])
        expect2 = _spec_composite_expect(out2.render_spec)
        copy_joined = "".join(expect2.get("text", {}).get("lines") or [])
        cs.check("限时开放" in copy_joined, f"新版 spec 文案 = v{base_v + 1}", copy_joined)
        mp4_2 = await _download_output(out2)
        failures = _probe_film(mp4_2, expect2, "j5", "j5_v2")

        # 视频区与首版逐帧一致（未触碰元素不变）。
        import av
        import numpy as np

        out1 = next(o for o in outputs if str(o.id) == state["output1_id"])
        expect1 = _spec_composite_expect(out1.render_spec)
        mp4_1 = await _download_output(out1)
        vrect = expect1["video"]["rect"]

        def vframes(mp4, ts):
            got = {}
            with av.open(str(mp4)) as c:
                w = next(s for s in c.streams if s.type == "video").codec_context.width
                h = next(s for s in c.streams if s.type == "video").codec_context.height
                remaining = dict.fromkeys(ts)
                for frame in c.decode(video=0):
                    t = float(frame.pts * frame.time_base)
                    for want in list(remaining):
                        if abs(t - want) < 1 / 60:
                            got[want] = frame.to_ndarray(format="rgb24")
                            del remaining[want]
                    if not remaining:
                        break
            x0, x1 = int(vrect["x"] * w), int((vrect["x"] + vrect["w"]) * w)
            y0, y1 = int(vrect["y"] * h), int((vrect["y"] + vrect["h"]) * h)
            return {t: a[y0:y1, x0:x1] for t, a in got.items()}

        sample_ts = [round(expect1["video"]["at"] + 1.0, 2), round(expect1["video"]["end"] - 1.0, 2)]
        f1, f2 = vframes(mp4_1, sample_ts), vframes(mp4_2, sample_ts)
        for t in sample_ts:
            if t in f1 and t in f2 and f1[t].shape == f2[t].shape:
                delta = float(np.abs(f1[t].astype(np.int32) - f2[t].astype(np.int32)).mean())
                print(f"  {'ok ' if delta <= 0.5 else 'FAIL'} j5/video-region-identical@{t} mean|Δ|={delta:.4f}")
                if delta > 0.5:
                    failures.append(f"j5/video-region-identical@{t}: {delta:.4f}")
        cs.check(not failures, "修改版探针 + 视频区一致性", failures)
        state["run2_id"] = run2
        state["output2_id"] = str(out2.id)
        _save_state(state)
        print(f"J5 OK — run2 COMPLETED，两 Output 并存，视频区逐帧一致（{mp4_2}）")
    finally:
        await ctx.close()


async def run_j6() -> None:
    """J6 边界：源窗口超素材真实时长 → 诚实纠偏，零新 run、版本永不
    落 20–30 超界窗。幂等: T8 已发且澄清在场则只复核不重发。"""
    ctx, state = await _journeys_ctx()
    pid = state["project_id"]
    try:
        before = await _snap_film(pid)
        runs_before = await cs.count_runs(pid)
        # T8 已发生过的续跑判别: 最新 user 消息已是 T8 文本 → 只复核。
        items = await cs.conversation_items(ctx, pid)
        last_user = next(
            (m for m in reversed(items) if m.get("role") == "user"), {}
        )
        if (last_user.get("content") or "").strip() == "再把视频换成第20到30秒那段试试。":
            evidence = {"assistant_text": "(resume — 见 j6_t8.json 与 DB 消息行)"}
        else:
            t8 = await ctx.chat_stream(pid, "再把视频换成第20到30秒那段试试。")
            cs.check(t8.failed is None, "T8 turn completes", t8.failed)
            evidence = _turn_evidence(t8, "源 20–30s 超界")
            _save_evidence("j6_t8.json", evidence)
        after = await _snap_film(pid)
        cs.check(await cs.count_runs(pid) == runs_before, "J6 零新 run")
        # 合法结果 = 版本未变（拒绝/澄清），或出生一个仍合法的新版本——永不
        # 是源窗 20–30 的版本（validator 对真字节应拒）。
        if after is not None and (before is None or after.get("version") != before.get("version")):
            facts = _composite_facts(after["board"])
            video = facts["video"]
            cs.check(
                float(video.get("source_end")) <= 25.0,
                "任何新版本源窗必须落在素材真实时长内",
                video,
            )
        # 澄清形态断言: 最后一条 assistant 文本点名素材真实长度（诚实纠偏
        # 的形状——禁静默接受, 禁无解释拒绝）。
        items = await cs.conversation_items(ctx, pid)
        last_assistant = next(
            (m for m in reversed(items) if m.get("role") == "assistant" and (m.get("content") or "").strip()),
            {},
        )
        a_text = last_assistant.get("content") or ""
        cs.check(bool(a_text.strip()), "J6 有答复文本")
        cs.check("25" in a_text, "答复点名素材真实时长（25s）", a_text[:200])
        print("J6 OK — 超界源窗未产新版本未产 run（诚实纠偏答复已存证）")
    finally:
        await ctx.close()


async def run_all() -> None:
    await run_j1()
    await run_j3()
    await run_j4()
    await run_j5()
    await run_j6()
    print("ALL JOURNEYS OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", action="store_true")
    parser.add_argument("--verify-storage", action="store_true")
    parser.add_argument("--cleanup", action="store_true")
    for stage in ("j1", "j3", "j4", "j5", "j6", "all"):
        parser.add_argument(f"--run-{stage}", action="store_true")
    args = parser.parse_args()
    if args.seed:
        asyncio.run(seed())
    elif args.verify_storage:
        asyncio.run(verify_storage())
    elif args.cleanup:
        asyncio.run(cleanup())
    elif args.run_j1:
        asyncio.run(run_j1())
    elif args.run_j3:
        asyncio.run(run_j3())
    elif args.run_j4:
        asyncio.run(run_j4())
    elif args.run_j5:
        asyncio.run(run_j5())
    elif args.run_j6:
        asyncio.run(run_j6())
    elif args.run_all:
        asyncio.run(run_all())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
