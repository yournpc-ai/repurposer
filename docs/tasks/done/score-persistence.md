# 首发推荐分：持久化 + UI 展示 — 实施简报

> Status: ✅ Implemented（2026-07-23；验收：seed_demo --force 15/15 全绿，5 条 clip score.value 78–92 且 reason 点名驱动维度）
> 排期：ROADMAP §1 P0-3；来源：矩阵 §C 改造；STRATEGY §2.1（打分理由可见 = 品味可证伪的前提——理由随本简报一起落，不再等 P1）
> 前置核实（2026-07-23 代码扫描）：管道已全线铺好——`outputs.score` JSONB 列（tables.py:268）、API 序列化（schemas.py:1009）、前端类型（types.ts:151）均已存在；缺的只有**写入**和**展示**两个点。
> 改名说明（2026-07-23 产品决策）：原"传播潜力分 / virality_score"更名为**首发推荐分（recommendation_score）**。理由：传播量不可证伪（取决于粉丝数/算法/时机，我们观测不到）、优化目标错位（猎奇 ≠ 专业信誉）、校准源太远（LinkedIn 回流 P2）；知识演讲者的真实动作是"选一条署我名的先发"，分数必须回答这个问题，且校准信号（用户选用行为）从第一天就在产品内可观测。

## 1. 一句话目标

LLM 产出的**首发推荐分**（1–100，回答"这条最值得你先发"）连同**一句打分理由**落 `outputs.score`，并在 clip 卡片与详情上展示。

## 2. 打分口径（prompt 层，本次必须改）

分数只评价模型**有资格判断**的内容属性，禁止预测阅读量/传播量。四个维度：

| 维度 | 回答的问题 |
|---|---|
| 完整度 | 这 30 秒独立成立吗？有完整论点弧（铺垫→观点→收束），不是只有上下文里才成立的碎片 |
| 开头 | 前 3 秒值不值得给出后 27 秒？知识向 hook（惊人论断/问题/张力），不是噱头 |
| 代表性 | 它承载本场核心论点吗？（接 director core_thesis）观众只看这条，讲者被良好代表 |
| 表达 | 这段里讲者是最佳状态吗？（还是口头禅/绕路段落） |

`score_reason` 一句话（目标语言），点名驱动维度，**逐字展示给用户**。

## 3. 数据形状

`outputs.score = {"value": int, "reason": str}`（value 1–100）。P1 的维度明细往同一 JSONB 加 `dimensions` key，本次不写。

模型字段改名：`ClipPlan.virality_score` / `Segment.virality_score` / `ClipRevision.virality_score` → `recommendation_score`；`ClipPlan` 新增 `score_reason: str`，`ClipRevision` 新增 `score_reason: str | None`。

## 4. 改动面

**后端：**
1. `schemas.py`：三处字段改名 + `score_reason`（`to_segment()` 映射同步）。
2. `prompts/clip_agent.j2`：新增 Scoring 段（四维口径 + reason 要求）；输出 JSON 示例字段改名；requirements 行同步。
3. `prompts/reviser.j2`：输出示例字段改名 + reason；修订后重打分。
4. `node_runners.py` clips 创建循环：`Output(..., score={"value": plan.recommendation_score, "reason": plan.score_reason or None})`。
5. `node_runners.py run_script_revision`：`revised.recommendation_score` 非空时同步更新 `output.score`（reason 缺省保留旧值）。
6. `clip_agent.py` / `reviser.py` log 字段名同步。

**前端：**
7. `ClipCard`：左上角分数徽章（与右上角时长徽章对位，同 `bg-black/70` 样式系）；**榜首 clip（同批最高分）徽章用 accent 色** + `title` 属性悬停显 reason；`isTopPick` 由父级（projects.$id.tsx 的 clips 列表）算好传入。
8. `ClipDetailModal`：展示分数 + 理由。
9. i18n（en/zh 同步）：`results.topPick`（首发推荐/Top pick）、`results.scoreLabel`（推荐度/Pick score）、`results.scoreReason`（推荐理由/Why this clip）。

## 5. 验收标准

- [ ] `python scripts/seed_demo.py --force` 后，每个 clip output 的 `score.value` 非空且在 1–100、`score.reason` 非空
- [ ] 前端 clip 卡片可见分数徽章，榜首 accent，明暗两主题正常
- [ ] ClipDetailModal 可见分数与理由
- [ ] reviser 重生成后分数更新（reason 缺省保留）
- [ ] 零新表、零新列、零迁移
- [ ] 代码全库 `virality` 零命中（prompt 里"禁止预测 virality"的告诫除外）；我方产品语义的文档（PRD/矩阵/ROADMAP/STRATEGY/MODULE_ARCH/DISTRIBUTION）不再使用"传播潜力分"命名（竞品事实描述除外）

## 6. Prohibited Behaviors

- **禁止**把分数塞进 payload——`score` 是 ADR-030 批准的顶级通用列，就写顶级列；
- **禁止**本次做维度明细（`dimensions`）/ 排序筛选 UI——P1 范围，本简报兑现"值 + 理由可见"；
- **禁止**给 derivative 类产物（post / article / quotes）打分——首发推荐分是 clip 概念；
- **禁止**在 prompt/UI 里承诺阅读量、传播量、"会火"——分数只回答"哪条最值得你先发"；
- **禁止**保留 `virality` 命名的任何残留（字段、log、i18n、文档）。
