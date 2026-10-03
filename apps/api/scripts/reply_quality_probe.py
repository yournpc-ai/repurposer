"""reply_quality_probe.py — 答复质量尺（批0）：场景集 × 质量尺 × 基线对账。

定位（仪表不是闸）: chat_scenarios 断言形态（禁令 #7 永不锁 LLM 文案）、
prompt_gate 断言行为阈值——本脚本测第三个轴：逐场景答复质量。基线先行
（任何质量批施工前 --save-baseline），批后复测 --diff，delta 的分布决定
后续批（帧级视觉 / 单 prompt 化）的 go/no-go——不评估就施工 = 没有仪表
就改引擎。

Preflight（同 chat_scenarios）:
- 活 API（SCENARIO_API_BASE，默认 127.0.0.1:8000——SCENARIO_API_BASE 同
   chat_scenarios 的环境变量名）;
- dev worker 在跑（S-warm 的 fixture 视频要真 ASR + 真 warm + 真触发回合,
  全程约 5-10 分钟——这不是卡顿，是真实链路）;
- demo 桶可达（fixture 源 demo/uploads/demo_talk.mp4）。
fixture 纪律（memory: delete_project 毁共享 key 坑）: 源片先拷 scenario/
前缀再 seed——项目删除会 unlink asset 的 file_url，共享 key 直接引用会被
清理想死（S16 吃过 recipe 卡营销片）。

场景集（批0 三本 + 批 D 语言矩阵；S-done 收官触发回合待后续——它要真 run
全程，骑 S4 的链另排）:
- S-cap  能力问家族:「你会做什么？你能剪辑已有素材吗」(Pexo 图4 同句,
         直接可比) × 语言矩阵六格（prompt 语言 × Accept-Language 地板,
         风险加权序: en→zh / mixed→zh 先行, zh→zh / en→en 基线,
         zh→en / mixed→en 末位——事故①②活在 ZH 答复里）
- S-adv  素材处理中建议: 传片即问「这个视频你有什么建议」(截图图1 同句)
- S-warm 理解落地触发回合（主战场,对标 Pexo 图5 的编辑视角评述）

质量尺 v1（RUBRIC_VERSION 随尺变更递增——基线文件记录版本,跨版本 diff
只比共有维度）:
  det（代码判,无偏锚）:
  D1 time_anchors            [S-warm] 应答含素材内时间锚(1:18 / 第2分钟 类;
                              秒数区间与裸时长不算锚——正则分不开落点与规格)
  D2 menu_grounding          [all]    产物名命中菜单表（S-cap 期望 ≥3）且无
                              平台编造（echo 防编造律 ADR-060 的确定性镜像:
  D3 prose_dock_consistency  [S-warm] 散文点名的产物 ⊆ suggestion 标签里的产物
  judged（LLM judge,0/1/2 + 一句证据）:
  J1 verdict_first           [S-adv,S-warm] 判定先行 + 带拒绝项
  J2 editorial_facts         [S-adv,S-warm] 剪辑相关事实 vs 内容摘要
  J3 negative_judgment       [S-warm] 明确说了哪段不值得留/不要怎么做
  J4 single_next_step        [all]    收尾收敛到一个明确决策点(带选项卡的
                              回合 = 散文干净收进卡,卡即决策点)
  J5 direct_answer           [S-cap]  直接回答先行+接担忧+口语节奏+开放邀请收尾
  J6 semantic_roles          [all]    语义角色守位五对（批 D 事故①②仪表):
                              推荐=提议非指令 / 提问=邀请非命令 / 默认值=可改
                              非被迫 / 选项=可选非已决 / 观察=有据非断言

Judge 的已知偏置: 唯一 provider 座是 minimax——被测与 judge 同族,自偏好
风险在案,det 半尺是无偏锚;第二 provider 座落地时 --provider 轮转（mirror
prompt_gate 的 PROVIDERS 纪律,judge 与被测异族）。

用法:
  uv run python scripts/reply_quality_probe.py                    # 跑+印报告
  uv run python scripts/reply_quality_probe.py --no-judge         # 只跑 det 半尺
  uv run python scripts/reply_quality_probe.py --save-baseline pre-pexo
  uv run python scripts/reply_quality_probe.py --diff pre-pexo    # 与基线对账
报告落 <repo>/scratch/reply_quality/（scratch 不提交——审计报告先例）。
"""

import argparse
import asyncio
import json
import re
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

# Make ``app`` importable when run as a file (apps/api on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import BaseModel, Field  # noqa: E402

# Client/fixture helpers ride the scenario script's single source (scripts
# reach into app internals throughout — the scripts/ 去概念名 doctrine).
from scripts.chat_scenarios import (  # noqa: E402
    REMIX_SOURCE_KEY,
    Ctx,
    ScenarioFailure,
    copy_fixture,
    make_user,
    seed_asset,
    wait_asset_status,
)
from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.schemas import AssetStatus, AssetType  # noqa: E402
from app.providers.llm.base import LLMError  # noqa: E402
from app.providers.llm.minimax import minimax_client  # noqa: E402

# ---------------------------------------------------------------------------
# 质量尺 v1
# ---------------------------------------------------------------------------

RUBRIC_VERSION = 6  # v6: J6 语义角色维度 + S-cap 语言矩阵（批 D 事故①②仪表——推荐/提问/默认/选项/观察五对角色守位,措辞质感的测量座);v5: J5 示例拍退役——收尾=素材优先开放邀请,替用户写台词不可满分(2026-09-27 用户裁定);v4: J5 入口语节奏轴——规格表腔不可满分(批5 v2 事故尺补);v3: D1 只认无歧义锚(v2 秒数区间被「切 30–60 秒」时长规格假阳);v2: J4 按「选项卡=决策点」校准

# 语言矩阵（批 D · 事故①②语义角色仪表）：能力问家族的 prompt 语言 × 界面
# 地板语言（Accept-Language——mirror 律下地板只在消息无明确语言信号时
# 生效,mixed prompt 是地板真正有权重之座）。cell = 「prompt→floor」,答复
# 实际落地语言随 capture 记录。dict 序 = 风险加权序（EN→ZH 与 mixed→ZH
# 先行,ZH→ZH / EN→EN 基线,ZH→EN / mixed→EN 末位）——默认场景清单同序。
CAP_VARIANTS: dict[str, tuple[str, str | None, str]] = {
    # scenario id: (prompt, Accept-Language floor, lang cell)
    "S-cap-en2zh": (
        "What can you do? Can you edit existing material?", "zh", "en→zh"),
    "S-cap-mixed2zh": (
        "你会做什么？can you turn my talks into clips and posts?", "zh",
        "mixed→zh"),
    "S-cap": ("你会做什么？你能剪辑已有素材吗", None, "zh→zh"),
    "S-cap-en2en": (
        "What can you do? Can you edit existing material?", "en", "en→en"),
    "S-cap-zh2en": ("你会做什么？你能剪辑已有素材吗", "en", "zh→en"),
    "S-cap-mixed2en": (
        "What can you do? 能把我的演讲剪成切片和帖子吗？", "en", "mixed→en"),
}
CAP_ALL = frozenset(CAP_VARIANTS)

# 菜单对账表（测量仪器,与批1落地的注册表菜单投影 capability_menu_lines()
# 对齐维护——投影增删产物时本表同批改;zh alias 是应答侧的用户语言叫法,
# 命中任一 alias 记该产物一次）。
MENU: dict[str, list[str]] = {
    "金句卡": ["金句卡", "金句", "名言卡", "quote card", "quotes"],
    "轮播图": ["轮播图", "轮播", "图解卡", "carousel"],
    "高光切片": ["高光切片", "切片", "高光短片", "highlight clip", "clips"],
    "长文": ["长文", "深度文", "article"],
    "帖子": ["帖子", "长帖", "post"],
    "字幕": ["字幕", "subtitle", "captions"],
    "配音": ["配音", "dub", "dubbing"],
    "封面": ["封面", "cover"],
    "音乐": ["配乐", "音乐", "music"],
    "去口头禅": ["去口头禅", "去废话", "filler"],
    "相册视频": ["相册视频", "照片视频", "slideshow"],
}

# 平台编造黑名单（用户没点名的渠道永不出现在建议里——ADR-060; bare "X" 太
# 噪不收）。注意这是我们有意的与 Pexo 的分歧（他们示例里说「发抖音」)——
# 尺量的是我们的法,不是他们的。
PLATFORM_BAN = [
    "LinkedIn", "领英", "Twitter", "TikTok", "YouTube", "Instagram",
    "Facebook", "newsletter", "抖音", "小红书", "快手", "B站", "公众号",
    "视频号",
]

DIMENSIONS: dict[str, dict] = {
    "D1": {
        "name": "time_anchors", "kind": "det", "scenarios": {"S-warm"},
        "what": "应答含素材内时间锚（1:18 / 0-3秒 / 3.5–4.5秒 类）",
    },
    "D2": {
        "name": "menu_grounding", "kind": "det",
        "scenarios": CAP_ALL | {"S-adv", "S-warm"},
        "what": "产物名命中菜单表且无平台编造",
    },
    "D3": {
        "name": "prose_dock_consistency", "kind": "det", "scenarios": {"S-warm"},
        "what": "散文点名的产物 ⊆ suggestion 标签里的产物",
    },
    "J1": {
        "name": "verdict_first", "kind": "judged", "scenarios": {"S-adv", "S-warm"},
        "what": "判定先行 + 带拒绝项（0=纯描述 1=有判定无拒绝项 2=判定+拒绝项）",
    },
    "J2": {
        "name": "editorial_facts", "kind": "judged", "scenarios": {"S-adv", "S-warm"},
        "what": "剪辑相关事实 vs 内容摘要（0=纯摘要 1=混合 2=剪辑事实为主）",
    },
    "J3": {
        "name": "negative_judgment", "kind": "judged", "scenarios": {"S-warm"},
        "what": "明确负向判断（0=无 1=隐含 2=明确+理由）",
    },
    "J4": {
        "name": "single_next_step", "kind": "judged",
        "scenarios": {"S-cap", "S-adv", "S-warm"},
        # v2 校准（基线实证）: 带选项卡的回合,选项卡本身就是那个决策点
        # (ADR-081)——问的是散文是否干净收进卡(无悬空引导句、无与选项竞争
        # 的第二问),不是「选项只能有一个」。
        "what": "收尾收敛到一个明确决策点——普通回合 = 一句话下一步;带选项卡的回合 = 散文干净收进选项卡(0=无/多头/悬空引导 1=有但绕 2=单一明确)",
    },
    "J5": {
        "name": "direct_answer", "kind": "judged", "scenarios": CAP_ALL,
        # v4 校准（批5 v2 事故尺补）: 规格表腔（全量菜单倾倒/SKU 名词清单/
        # 模板分组标签）不可满分——「人机感」入尺,否则规格表答复仍拿 2。
        # v5 校准（2026-09-27 用户裁定）: 收尾示例拍退役——替用户写台词
        # （「试试这样说：…」式脚本化示例请求）= presumption,列 1 分封顶;
        # 满分收尾 = 素材优先的开放邀请（邀请即台阶）。
        "what": "直接回答先行+接住隐含担忧+口语节奏（动词分组、无规格表腔）+收尾=素材优先的开放邀请（0=绕弯或规格表腔倾倒 1=直接但说明书腔、替用户写台词、或缺邀请 2=直接+接担忧+口语化+开放邀请）",
    },
    "J6": {
        "name": "semantic_roles", "kind": "judged",
        "scenarios": CAP_ALL | {"S-adv", "S-warm"},
        # v6 新增（批 D 事故①②仪表）：措辞质感的测量座——场景面只锁形态,
        # 推荐 vs 指令的角色判定归本维度（断言面分工,简报批 D 施工点 5）。
        "what": "语义角色守位——五对角色：推荐=一词可收尾的提议,非替用户拍板的指令；提问=邀请,非命令；默认值=可改的可见事实,非被迫之选；选项=可选可忽略,非已决定；观察=有据事实,非超出证据的断言（0=任一角色塌成禁态 1=边缘含混 2=出现的角色全部守位,未出现的角色不扣分）",
    },
}

# 时间锚模式（D1 v3）: 只认无歧义的素材内定位——时间戳 0:00 / 1:18:22 /
# 「第 N 分钟」/「N 分 M 秒」。秒数区间（0-3秒 / 30–60秒）v2 收过又退役:
# 「切 30–60 秒」是时长规格不是落点,正则分不开两者,宁缺毋滥（v2 基线
# 实证假阳性）。
TIME_ANCHOR_PATTERNS = [
    r"\d{1,2}:\d{2}(?::\d{2})?",
    r"第\s*\d+\s*分钟",
    r"\d+\s*分\s*\d+\s*秒",
]


# ---------------------------------------------------------------------------
# det 半尺
# ---------------------------------------------------------------------------


def _menu_hits(text: str) -> set[str]:
    """菜单表命中（alias 级,en 小写化匹配）。"""
    lowered = text.lower()
    return {
        canonical
        for canonical, aliases in MENU.items()
        if any(a.lower() in lowered for a in aliases)
    }


def check_time_anchors(reply: str) -> dict:
    hits = sorted(
        {m for pat in TIME_ANCHOR_PATTERNS for m in re.findall(pat, reply)}
    )
    return {
        "score": 1 if hits else 0,
        "detail": f"anchors: {', '.join(hits[:6])}" if hits else "no time anchor",
    }


def check_menu_grounding(reply: str, scenario: str) -> dict:
    hits = _menu_hits(reply)
    platform_hits = [p for p in PLATFORM_BAN if p.lower() in reply.lower()]
    # 能力问家族（含语言矩阵变体）是能力枚举,期望多命中;建议类场景至少
    # 一个不编造。
    want = 3 if scenario in CAP_ALL else 1
    ok = len(hits) >= want and not platform_hits
    return {
        "score": 1 if ok else 0,
        "detail": f"menu: {sorted(hits) or '∅'}; platform violations: "
        f"{platform_hits or '∅'} (want ≥{want})",
    }


def check_prose_dock_consistency(reply: str, suggestions: list[str]) -> dict:
    prose_products = _menu_hits(reply)
    dock_products = _menu_hits(" ".join(suggestions))
    missing = prose_products - dock_products
    return {
        "score": 1 if not missing else 0,
        "detail": f"prose: {sorted(prose_products) or '∅'}; dock: "
        f"{sorted(dock_products) or '∅'}; named-but-not-pickable: "
        f"{sorted(missing) or '∅'}",
    }


DET_CHECKS = {
    "D1": lambda reply, suggestions, scenario: check_time_anchors(reply),
    "D2": lambda reply, suggestions, scenario: check_menu_grounding(reply, scenario),
    "D3": lambda reply, suggestions, scenario: check_prose_dock_consistency(
        reply, suggestions
    ),
}


# ---------------------------------------------------------------------------
# judged 半尺
# ---------------------------------------------------------------------------


class JudgeScore(BaseModel):
    dimension: str
    score: int = Field(ge=0, le=2)
    evidence: str = ""


class JudgeResult(BaseModel):
    scores: list[JudgeScore] = Field(default_factory=list)


JUDGE_SYSTEM = """你是答复质量评审。按给定维度给一条 AI 助手答复打分——只看维度定义问的事,不评文笔,不被篇幅和礼貌影响。每个维度给 0/1/2 分和一句证据(引用原文片段)。只输出 JSON。

JSON 卫生(硬性): evidence 引用原文一律用「」括起——字符串值内禁止出现英文双引号(v1 基线实证: evidence 内嵌 " 直接打爆 JSON parse,整场测量作废)。"""


def _judge_prompt(scenario: str, user_prompt: str, reply: str,
                  suggestions: list[str], dims: list[str]) -> str:
    rubric_lines = "\n".join(
        f"- {d} {DIMENSIONS[d]['name']}: {DIMENSIONS[d]['what']}" for d in dims
    )
    dock = (
        "\n答复后附的选项卡标签: " + " / ".join(suggestions) if suggestions else ""
    )
    return (
        f"场景 {scenario}——用户说:「{user_prompt}」\n\n"
        f"AI 助手的答复:\n---\n{reply}\n---{dock}\n\n"
        f"按以下维度打分(0/1/2 + 一句 evidence 引用原文):\n{rubric_lines}\n\n"
        'JSON 格式: {"scores": [{"dimension": "J1", "score": 0, "evidence": "…"}]}'
    )


async def judge_reply(scenario: str, user_prompt: str, reply: str,
                      suggestions: list[str]) -> dict[str, dict]:
    dims = [d for d, spec in DIMENSIONS.items()
            if spec["kind"] == "judged" and scenario in spec["scenarios"]]
    if not dims:
        return {}
    # judge 失败降级不炸场(v1 基线实证): judge 的 JSON 故障 = 该本 judged
    # 半尺缺失,不是整场测量的死刑——det 半尺照常落,维度记 None 标原因。
    try:
        result = await minimax_client.generate(
            [
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": _judge_prompt(
                    scenario, user_prompt, reply, suggestions, dims)},
            ],
            JudgeResult,
            temperature=0.0,
        )
    except LLMError as e:
        return {d: {"score": None, "evidence": f"judge error: {e!r:.120}"}
                for d in dims}
    out: dict[str, dict] = {}
    for s in result.scores:
        if s.dimension in dims:
            out[s.dimension] = {"score": s.score, "evidence": s.evidence}
    # 缺维度 = judge 漏答,记 None 而不是静默当 0(读容忍的测量镜像)。
    for d in dims:
        out.setdefault(d, {"score": None, "evidence": "judge omitted"})
    return out


# ---------------------------------------------------------------------------
# 场景跑者
# ---------------------------------------------------------------------------


async def _last_assistant_content(ctx: Ctx, conversation_id: str) -> str:
    msgs = await ctx.messages(conversation_id)
    for m in reversed(msgs):
        if m.get("role") == "assistant" and (m.get("content") or "").strip():
            return m["content"]
    return ""


async def _conversation_id(ctx: Ctx, pid: str) -> str:
    res = await ctx.conversation(pid)
    if res.status_code != 200:
        raise ScenarioFailure(f"conversation missing for {pid}: {res.text}")
    data = res.json()
    cid = data.get("id") or (data.get("conversation") or {}).get("id")
    if not cid:
        raise ScenarioFailure(f"conversation id unreadable: {list(data)}")
    return str(cid)


async def scenario_cap(ctx: Ctx, scenario: str) -> dict:
    """S-cap 能力问家族（Pexo 图4 同句 + 批 D 语言矩阵变体）：prompt 语言
    × Accept-Language 地板按 CAP_VARIANTS 配对,cell 随 capture 记录——
    语义角色判定的语言覆盖面（事故①②活在 ZH 答复里,mixed/EN prompt +
    ZH 地板是风险加权序的先行格）。"""
    prompt, floor, cell = CAP_VARIANTS[scenario]
    pid = await ctx.new_project(f"rq-{scenario}")
    res = await ctx.client.post(
        "/chat",
        json={"project_id": pid, "message": prompt},
        headers={"Accept-Language": floor} if floor else None,
    )
    if res.status_code != 201:
        raise ScenarioFailure(f"/chat {prompt[:30]!r}: {res.text}")
    turn = res.json()
    reply = ((turn.get("assistant_message") or {}).get("content") or "").strip()
    if not reply:  # 非常规形状兜底: 回读会话
        reply = await _last_assistant_content(ctx, await _conversation_id(ctx, pid))
    return {"scenario": scenario, "user_prompt": prompt, "reply": reply,
            "suggestions": [], "lang_cell": cell}


async def scenario_adv_and_warm(ctx: Ctx, warm_timeout: float) -> list[dict]:
    """S-adv + S-warm 共享一次真实处理周期: 传片(PENDING)即问 → 建议应答
    (S-adv) → worker 真 ASR → 真 warm → 真触发回合 (S-warm)。"""
    adv_prompt = "这个视频你有什么建议"
    pid = await ctx.new_project("rq-S-adv-warm")
    fixture_prefix = f"scenario/rq-{uuid.uuid4().hex[:8]}"
    key = await copy_fixture(REMIX_SOURCE_KEY, fixture_prefix)
    asset_id = await seed_asset(
        pid, ctx.user_id, AssetType.VIDEO, "demo_talk.mp4", file_url=key
    )
    turn = await ctx.chat(pid, adv_prompt)
    adv_reply = (
        (turn.get("assistant_message") or {}).get("content") or ""
    ).strip()
    cid = await _conversation_id(ctx, pid)
    if not adv_reply:
        adv_reply = await _last_assistant_content(ctx, cid)
    out = [{"scenario": "S-adv", "user_prompt": adv_prompt,
            "reply": adv_reply, "suggestions": []}]

    await wait_asset_status(asset_id, {AssetStatus.COMPLETED, AssetStatus.FAILED})
    # warm 只为处理成功的素材点火(S16 FAILED 先例: warm 永不触发)——失败则
    # S-warm 直接标 skipped,不在 poll 上空等一个超时。
    async with AsyncSessionLocal() as db:
        from app.models.tables import Asset

        asset_row = await db.get(Asset, uuid.UUID(asset_id))
        final_status = (
            asset_row.processing_status if asset_row is not None else None
        )
    if final_status != AssetStatus.COMPLETED:
        out.append({"scenario": "S-warm", "user_prompt": "(trigger turn)",
                    "reply": "", "suggestions": [],
                    "skipped": f"asset processing ended {final_status} — "
                    "the warm never fires for a failed asset"})
        return out

    # 触发回合 poll(trigger=understanding_warmed; 新会话至多一条,不必对
    # ref)。pending plan 落桌 = 触发合法沉默(ADR-080 第二谓词)——那是可报告
    # 的产品行为,不是 probe 故障: 标 skipped 记原因。
    deadline = asyncio.get_event_loop().time() + warm_timeout
    review = None
    while asyncio.get_event_loop().time() < deadline:
        for m in await ctx.messages(cid):
            intent = m.get("intent") or {}
            if (intent.get("type") == "trigger_review"
                    and intent.get("trigger") == "understanding_warmed"):
                review = m
                break
        if review is not None:
            break
        await asyncio.sleep(3)
    if review is None:
        plan = ((await ctx.conversation(pid)).json().get("pending_question")
                or {})
        reason = ("silenced: a plan docked (ADR-080 silence is product "
                  "behavior)" if plan.get("kind") == "task_book"
                  else f"timeout {warm_timeout}s (worker/warm/trigger chain?)")
        out.append({"scenario": "S-warm", "user_prompt": "(trigger turn)",
                    "reply": "", "suggestions": [], "skipped": reason})
        return out
    suggestions = [
        o.get("label", "")
        for o in ((review.get("question") or {}).get("options") or [])
    ]
    out.append({"scenario": "S-warm", "user_prompt": "(trigger turn)",
                "reply": (review.get("content") or "").strip(),
                "suggestions": suggestions})
    return out


# ---------------------------------------------------------------------------
# 评分 + 报告 + 基线对账
# ---------------------------------------------------------------------------


async def score_capture(capture: dict, with_judge: bool) -> dict:
    if capture.get("skipped") or capture.get("error"):
        capture.setdefault("det", {})
        capture.setdefault("judged", {})
        return capture
    scenario, reply, suggestions = (
        capture["scenario"], capture["reply"], capture["suggestions"],
    )
    if not reply:
        # 空答复 = 捕获失败,记 error 而不是让 judge 给空气打分(测量卫生:
        # 空应答的 0 分会污染基线——它和「答复很烂」是两件事)。
        capture["error"] = "no reply captured"
        capture["det"] = {}
        capture["judged"] = {}
        return capture
    det: dict[str, dict] = {}
    for d, fn in DET_CHECKS.items():
        if scenario in DIMENSIONS[d]["scenarios"]:
            det[d] = fn(reply, suggestions, scenario)
    judged = (
        await judge_reply(scenario, capture["user_prompt"], reply, suggestions)
        if with_judge
        else {}
    )
    capture["det"] = det
    capture["judged"] = judged
    return capture


def print_report(captures: list[dict]) -> None:
    for c in captures:
        cell = f" [{c['lang_cell']}]" if c.get("lang_cell") else ""
        print(f"\n=== {c['scenario']}{cell} ===")
        if c.get("skipped"):
            print(f"  SKIPPED — {c['skipped']}")
            continue
        if c.get("error"):
            print(f"  ERROR — {c['error']}")
            continue
        print(f"  reply: {c['reply'][:120].replace(chr(10), ' / ')}…")
        if c.get("suggestions"):
            print(f"  dock:  {' / '.join(c['suggestions'])}")
        for d, r in c["det"].items():
            print(f"  [{d} {DIMENSIONS[d]['name']}] {r['score']} — {r['detail']}")
        for d, r in c["judged"].items():
            print(f"  [{d} {DIMENSIONS[d]['name']}] {r['score']} — {r['evidence']}")


REPORT_DIR = Path(__file__).resolve().parents[3] / "scratch" / "reply_quality"


def save_report(captures: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "rubric_version": RUBRIC_VERSION,
                "created_at": datetime.now(UTC).isoformat(),
                "scenarios": captures,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def diff_baseline(name: str, captures: list[dict]) -> None:
    path = REPORT_DIR / f"baseline-{name}.json"
    if not path.exists():
        raise ScenarioFailure(f"baseline not found: {path}")
    base = json.loads(path.read_text())
    if base.get("rubric_version") != RUBRIC_VERSION:
        print(f"⚠ rubric version {base.get('rubric_version')} → "
              f"{RUBRIC_VERSION}: only shared dimensions compared")
    base_by_scenario = {c["scenario"]: c for c in base.get("scenarios", [])}
    print(f"\ndiff vs baseline {name} ({base.get('created_at', '?')}):")
    for c in captures:
        b = base_by_scenario.get(c["scenario"])
        if b is None or c.get("skipped"):
            continue
        for half in ("det", "judged"):
            for d, r in c.get(half, {}).items():
                old = (b.get(half) or {}).get(d, {}).get("score")
                new = r.get("score")
                mark = "▲" if (old is not None and new is not None and new > old) else (
                    "▼" if (old is not None and new is not None and new < old) else "="
                )
                print(f"  {c['scenario']:7s} {d:3s} {DIMENSIONS[d]['name']:26s} "
                      f"{old} → {new}  {mark}")


# ---------------------------------------------------------------------------


async def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--scenario",
                        default=",".join([*CAP_VARIANTS, "S-adv", "S-warm"]),
                        help="comma list (default: S-cap 语言矩阵全格 + S-adv + S-warm)")
    parser.add_argument("--save-baseline", metavar="NAME",
                        help="save this run as the named baseline")
    parser.add_argument("--diff", metavar="NAME",
                        help="diff this run against the named baseline")
    parser.add_argument("--no-judge", action="store_true",
                        help="det half only (no LLM judge calls)")
    parser.add_argument("--keep", action="store_true",
                        help="keep the scenario projects (default: cleanup)")
    parser.add_argument("--warm-timeout", type=float, default=480.0,
                        help="S-warm trigger poll bound (seconds)")
    args = parser.parse_args()

    wanted = {s.strip() for s in args.scenario.split(",") if s.strip()}
    ctx = Ctx(await make_user(), keep=args.keep)
    captures: list[dict] = []
    try:
        # 逐场景隔离失败——测量仪器的部分结果也有价值(一本挂了不烧掉已捕获
        # 的其他本);场景异常进 error 字段,评分阶段按空答复同律跳过。
        for cap_id in CAP_VARIANTS:
            if cap_id not in wanted:
                continue
            try:
                captures.append(await scenario_cap(ctx, cap_id))
            except Exception as e:  # noqa: BLE001 — per-scenario isolation
                captures.append({"scenario": cap_id, "user_prompt": "",
                                 "reply": "", "suggestions": [],
                                 "error": f"{type(e).__name__}: {e}"})
        if {"S-adv", "S-warm"} & wanted:
            try:
                for c in await scenario_adv_and_warm(ctx, args.warm_timeout):
                    if c["scenario"] in wanted:
                        captures.append(c)
            except Exception as e:  # noqa: BLE001 — per-scenario isolation
                for name in ("S-adv", "S-warm"):
                    if name in wanted and not any(
                        c["scenario"] == name for c in captures
                    ):
                        captures.append({"scenario": name, "user_prompt": "",
                                         "reply": "", "suggestions": [],
                                         "error": f"{type(e).__name__}: {e}"})
    finally:
        await ctx.cleanup()
        await ctx.close()

    for c in captures:
        await score_capture(c, with_judge=not args.no_judge)
    print_report(captures)

    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    save_report(captures, REPORT_DIR / f"probe-{ts}.json")
    if args.save_baseline:
        save_report(captures, REPORT_DIR / f"baseline-{args.save_baseline}.json")
        print(f"\nbaseline saved: baseline-{args.save_baseline}.json")
    if args.diff:
        diff_baseline(args.diff, captures)
    print(f"\nreport: {REPORT_DIR / f'probe-{ts}.json'}")


if __name__ == "__main__":
    asyncio.run(main())
