# MENTIONS — @ 提及体系方针

> Status: 活跃（2026-08-11 建）
> 本文是**一切 mention 需求的判定方针与机制纪律**——一个新"@X"想法先过 §2 族判定 + §3 排除清单，过不了就是不做。运行态实现细节归 `CHAT_ARCHITECTURE.md`，本文只立规矩。

## 1. 定位

mention = 用户与 AI 交流时对**实体**的点名机制。提示词的基本语法是：**用什么技能，处理什么素材，达到什么产出**。mention 只承载这个语法里用户手指得到的两类词——技能与素材；其余一切（产出类型、参数、配方、人设）用大白话说，或根本不由 mention 承载。

## 2. 两族分类

| 族 | 回答的问题 | 成员 | 效果族 | 消费面 |
|---|---|---|---|---|
| **请求** request | "用什么做"——计划时的材料与能力 | `asset`（素材）、`skill`（技能，方针见 §5） | 上下文富化为底；注册项可声明书字段硬钩子（如 `dub_languages` 存在性填充） | composer / 配方 overlay 首发 |
| **指认** reference | "改哪个"——已有之物的引用 | `output`、`transcript_segment`、`workflow_step` | 确定性指认注入（LLM 永不猜"第二条"是哪条） | chat 修订 |

两族不混：请求族进计划路径，指认族进修订路径。一个新 mention 类型必须唯一落族；两族都落不了的实体（如配方）说明它根本不是 mention。

## 3. 永不是 mention 的

| 候选 | 为什么不是 | 正确通道 |
|---|---|---|
| 配方 recipe | 发射上下文——点卡这个动作已经说完了一切，句中 chip 是第三遍冗余（overlay 标题与预填文案已各说一遍） | **配方 = 提示词**（2026-08-11 裁定）：预填模板原文即全部发射载荷，模板点名产出与语言；无 `recipe_id` transport、无服务端播种，plan path 与 composer 完全同径 |
| 产出类型（clips / post / article…） | 大白话推断已够准；且 `@output` 已被指认族占用（引用已有产物），同词两义禁 | PlanAgent 槽位推断 |
| 参数（语言 / 数量 / 画幅…） | mention 不是表单控件，预设空间无界 | 预填文案改字（发送前）/ chat 修订（发送后，恒胜） |
| 人设 persona | 身份是挂载，不是点名 | composer Persona 块 / `persona_id` 载荷 |

**判定三问**（全过才可立案新 mention 类型）：
1. 它是**实体**吗——有稳定 id、有注册表可查？
2. 用户**手指得到**吗——一句话里非点它不可，否则 LLM 会猜错或漏掉？
3. 它**唯一落入** §2 的一族吗？

## 4. 机制纪律

- **双端注册表**：前端 `MENTION_REGISTRY`（picker 候选源 + icon + i18n）+ 服务端解析注册表。新类型 = 双端各一条注册项，禁一次性分支。
- **输入组件唯一**：一切文本输入面挂同一个 `MentionEditor`（composer / chat dock——生成 overlay 底排在结果期就地转为底部 dock，ADR-041；产物微调会话并入 dock + 焦点注入）；候选源差异走 `MentionContext`（面的数据喂注册表源），禁每面各起 textarea / 自养 picker。
- **chip 三律**：可见（内联 chip 带 ×）/ 发送即消费 / × 即纯化（无状态跨发送残留）。
- **服务端解析唯一发生地**：mention 的机械效果（上下文富化、指认注入）只在服务端发生；前端永不构建 prior。
- **大白话显示名**：picker 与 chip 显示用户语言（"配音"），永不出现节点 kind / 模型名 / 技术黑话。

## 5. @skill 方针（请求族第二成员）

- 候选源 = `SKILL_REGISTRY` 的**公开投影**（显示名走 i18n）——用户能 @ 的技能与 intent agent 能提议的技能是同一张表，公开投影永不泄 params/schema。
- **`seat=True` 项永不进 picker**（占位技能不可提议，`dispatchable_skills()` 同款排除）。
- 效果两档，注册项内声明：① **上下文化**（默认）——LLM 读到技能点名，计划时倾向排入；② **书字段硬钩子**——对存在任务书字段的技能做存在性填充（同配方播种纪律：只补推断没有的，无 explicit，chat 修订永远赢）。
- 边界：技能的素材前提不满足（如 @配音 但无视频）→ plan path ask 反问（clips-media 门先例）——不裸跑、不静默拒绝。

## 6. 与其他文档的关系

| 文档 | 关系 |
|---|---|
| `CHAT_ARCHITECTURE.md` | mention 的运行时语义（context 注入、edit ops 指认通道）——"怎么跑"归它，"该不该是 mention"归本文 |
| `RECIPES.md` | 配方 = 发射上下文的完整论证与卡片层架构 |
| `tasks/recipe-launch-context.md` | recipe 脱离 mention 体系的实施简报（本文 §3 第一行的落地） |
| `NAMING.md` | mention type 词汇表座位 |
