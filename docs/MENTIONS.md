# MENTIONS — @ 提及体系方针

> Status: 活跃（output mention 带 `quote` 字段，ADR-069）
> 本文是**一切 mention 需求的判定方针与机制纪律**——一个新"@X"想法先过 §2 族判定 + §3 排除清单，过不了就是不做。运行态实现细节归 `CHAT_ARCHITECTURE.md`，本文只立规矩。

## 1. 定位

mention = 用户与 AI 交流时对**实体**的点名机制。它服务两类问题：请求时“用什么素材/能力”，修订时“改哪个既有对象”。产出类型、自由参数、配方与人设不因为能写成 `@X` 就成为 mention；它们分别走自然语言、计划字段、prompt 预填与身份载荷。

## 2. 两族分类

| 族 | 回答的问题 | 成员 | 效果族 | 消费面 |
|---|---|---|---|---|
| **请求** request | "用什么做"——计划时的材料与能力 | `asset`（当前）；`tool`（仅立案方针，未实施，见 §5） | 上下文富化与明确的素材角色 pin；意图仍由 `POST /chat` 判定 | Home composer / ChatDock |
| **指认** reference | "改哪个"——已有之物的引用 | `output`（可携带 `quote`）、`workflow_step`（只由画布步骤点击进入，不进 @ picker）；`transcript_segment` 仅 legacy 类型，未注册不可创建 | 确定性指认注入；回合恰一个 output pin 时服务端强制修订 target = 钉 id，LLM 转述不能覆盖用户钉选 | chat 修订 |

两族不混：请求族进计划路径，指认族进修订路径。一个新 mention 类型必须唯一落族；两族都落不了的实体（如配方）说明它根本不是 mention。

## 3. 永不是 mention 的

| 候选 | 为什么不是 | 正确通道 |
|---|---|---|
| 配方 recipe | 点卡已经选择了一个 prompt 捷径，再插 chip 不会增加执行语义 | **配方 = 提示词**：预填模板原文即全部发射载荷；无 `recipe_id` transport、服务端播种、overlay 发射或第二意图面 |
| 产出类型（clips / post / article…） | 大白话推断已够准；且 `@output` 已被指认族占用（引用已有产物），同词两义禁 | intent_router 链推断 |
| 参数（语言 / 数量 / 画幅…） | mention 不是表单控件，预设空间无界 | 预填文案改字（发送前）/ chat 修订（发送后，恒胜） |
| 人设 persona | 身份是挂载，不是点名 | composer Persona 块 / `persona_id` 载荷 |

**判定三问**（全过才可立案新 mention 类型）：
1. 它是**实体**吗——有稳定 id、有注册表可查？
2. 用户**手指得到**吗——一句话里非点它不可，否则 LLM 会猜错或漏掉？
3. 它**唯一落入** §2 的一族吗？

## 4. 机制纪律

- **双端职责**：前端 `MENTION_REGISTRY` 注册 picker/chip 的候选源、icon 与 i18n；服务端 `chat/context.py:build_context` 统一注入上下文，修订写门对 output pin 做确定性 target 解算并覆盖模型转述。新增类型必须同时登记前端候选/渲染与服务端机械效果，不能只加 chip 或一次性 prompt 分支。
- **输入组件唯一**：一切文本输入面挂同一个 `MentionEditor`（Home composer / ChatDock 两形态）；跨形态不得 remount 丢草稿。候选源差异走 `MentionContext`，禁每面各起 textarea / 自养 picker。产物指认 = @output；旧 `focus_output` 只读历史，不恢复写入。
- **chip 三律**：可见（内联 chip 带 ×）/ 发送即消费 / × 即纯化（无状态跨发送残留）。
- **服务端解析唯一发生地**：mention 的机械效果（上下文富化、指认注入）只在服务端发生；前端永不构建 prior。
- **大白话显示名**：picker 与 chip 显示用户语言（"配音"），永不出现节点 kind / 模型名 / 技术黑话。`@output` 候选行以右侧 `vN` 标示真实内容版本，插入 chip 使用「名称 vN」；当前项目与跨项目候选一致。名称只用于显示与筛选，修订目标始终由 pinned `output_id` 解算。
- **段落级指认（ADR-069——`quote` 是 output mention 的字段，不是新类型）**：文本产物卡（post/article）上划选段落 → 「引用这段」pill → dock 落**带引文的 @output chip**（序列化 = `@label "quote"`，chip 内联渲染截断引文；出生截断 200 字，上下文注入截断 500 字）。语义 = **引文即修订范围**（prompt 规则钉死：agent 修订那一段，永不盲目重写全文）。§3 闸门关系：quote 不是新 mention 类型——它是 output 指认的粒度细化，类型表不动。transcript 文档卡不开此口（其选区 = 未来剪辑 primitive）。

## 5. @tool 方针（PLANNED，未实施）

> 当前前端注册成员只有 `asset` / `output` / `workflow_step`，服务端没有 tool mention 类型或处理路径。本节只是立案政策；落地前不得读作现役，也不得用旧 `skill` 命名另起一套注册表。

- 候选源 = `TOOL_REGISTRY` 的公开投影（显示名走 i18n），与 intent agent 可提议能力同源；公开投影永不泄 params/schema。
- **`seat=True` 与 `llm_visible=False` 项不进 picker**；可派发集合与 `dispatchable_tools()` 对齐。compiler-only 能力不因 @ 提及变成模型可见工具。
- 机械效果只允许两类并在注册项声明：① 上下文化，让计划倾向排入该 tool；② 对已存在的计划字段补空缺，用户明示与 chat 修订恒胜。任何效果都不得创建制作意图、自动 Start 或绕过报价/授权。
- 素材前提不满足（如 @配音 但无视频）时走现有 QuestionDock / plan path 反问；不裸跑、不静默拒绝，也不新增 `/intent` 端点。

## 6. 与其他文档的关系

| 文档 | 关系 |
|---|---|
| `CHAT_ARCHITECTURE.md` | mention 的运行时语义（context 注入、edit ops 指认通道）——"怎么跑"归它，"该不该是 mention"归本文 |
| `RECIPES.md` | 配方 = prompt-only 发射与卡片层架构；配方为什么不是 mention |
| `NAMING.md` | mention type 词汇表座位 |
