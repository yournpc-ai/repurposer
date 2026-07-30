# Roadmap — 分模块需求排期

> 本文档是**排期表，不是论证场**。理由与依据只引用来源条目（`矩阵 §X` = `docs/DECISION_MATRIX.md`，`竞品` = `docs/research/`，`2027 架构` = `docs/MODULE_ARCHITECTURE.md` 的六层模块契约，`STRATEGY §X` = `docs/STRATEGY.md` 战略论证层），论证留在原文档。
>
> 状态口径：✅ 已落地 / 🚧 部分实现 / 📋 已排期 / 💡 待论证 / ❌ 未开始
>
> Agent 就绪度：✅ 现有技术可支撑 / ⚠️ 需 spike 或先建地基 / — 纯工程与模型无关
>
> 排期原则：
> 1. **依赖显性化**——每行标出前置，被依赖最多的地基（Operation Model、provider 抽象、成本计量）优先。
> 2. **2027 透镜**——editor 薄化为 Operation Model 的一个前端；chat 升级为 Agent Interface；distribution 与 pipeline 平级。
> 3. **合规是法律义务不是卖点**——EU AI Act Article 50（AI 内容机器可读标识）2026-08-02 生效，已上市系统宽限至 2026-12-02。

---

## 0. 模块速览（先读这张）

一句话产品：**把一场演讲（视频/音频/文字稿）自动变成一整套可发布的知识内容——竖屏 clips、LinkedIn 长文、金句卡、轮播、多语言版本——并能直接发到社媒。** 九个模块各管一段：

| # | 模块 | 是干什么的 | 关键技术 | 现状一句话 |
|---|---|---|---|---|
| 1 | Pipeline 生成管线 | 上传素材后全自动产出全套内容：ASR 转写 → 导演规划 → 选段打分 → 写稿 → 渲染 MP4 | MiniMax M3（LLM）、faster-whisper（词级 ASR）、Remotion（服务端渲染）、Postgres SKIP LOCKED 队列 + worker | 核心全绿，进入维持期 |
| 2 | Operation Model 操作日志层 | 把每次编辑记成一条可检查、可撤销的操作（而不是直接改数据），chat / editor / 未来 MCP 共用 | `operations` 表 + registry 纯函数 + 快照式 undo/redo | 地基已落地 |
| 3 | Agent Interface 对话层 | 用自然语言驱动一切：composer 第一句话生成计划，chat 续聊改产物、重跑任务 | ChatIntentAgent（结构化输出模拟 tool-calling）、SSE 进度推送、GenerationOverlay 全屏对话 UI | 后端 + 前端已通；plan 级节点重跑待做 |
| 4 | Editor GUI 网页剪辑器 | 删文字稿 = 剪视频的非破坏编辑；刻意不做专业剪辑（多轨/B-roll 留给剪映/Premiere） | transcript 编辑 + 单轨 trim + Remotion Player 预览 | 核心已落地；undo 按钮待接 |
| 5 | Distribution 分发 | 产物一键直发社媒，消灭"下载再上传"这最后一座手动桥 | LinkedIn / TikTok OAuth + 发布 API + worker 发布认领 | 双平台代码完成，等平台应用审核联调 |
| 6 | Memory 记忆层 | 让 AI 写得像"你"：Speaker 风格画像（Voice DNA）+ Brand 视觉皮肤 + 术语表 | persona 注入生成全链、声音克隆 | persona / Brand 已落地；术语表未开始 |
| 7 | 合规底座 | EU AI Act / GDPR 入场券：AI 内容机器可读标识、披露、数据驻留 | C2PA 打标（待选型）、clip-spec 自动分类器 | 未开始（P1，上线前必须回补） |
| 8 | 平台与计费 | 成本透明化：每次生成花多少、失败不扣费、套餐定价 | 节点级成本计量（已落 `workflow_steps.cost`） | 计量已落地；预估 / 套餐未开始 |
| 9 | Gallery / 落地页 | 获客面：公开落地页 + 配方卡"照这个做一个" | 纯前端 | 落地页 ✅；配方卡 ❌ |

各模块详表如下。

---

## 1. Pipeline（生成管线）

> 定位：必需但是成本中心，不追加差异化投入；现有 4-layer 编排已超前，保持即可。
>
> 这一层是"演讲 → 全套内容"的生成后端。一次生成 = 一张任务图（workflow_steps）：预处理（ASR/抽取）→ 导演看懂素材 → 导演分任务 → 各执行节点（选段/写稿/渲染）→ 汇总。每步可寻址、可计量、可重跑——这是上层一切（chat 重跑、成本预估、质检）的地基。

| 需求 | 来源 | 优先级 | 依赖 | Agent 就绪度 | 状态 |
|---|---|---|---|---|---|
| 4-layer 编排（Director/Executors） | — | — | — | ✅ | ✅ 已落地 |
| 词级时间戳 ASR | — | — | — | ✅ | ✅ 已落地 |
| 成本计量钩子（minimax usage 入 WorkflowRun） | 矩阵 §I；2027 架构 | **P0** | 无（趁管线还热先埋，后补成本极高） | — 纯工程 | ✅（2026-07-22 随 RunPlan Phase 1 落地：`services/metering.py` contextvar 绑定 plan node，usage 直落 `plan_nodes.cost`） |
| 去静默 / 去口头禅 | 矩阵 §B（2026-07-23 重估下放：输入为排练演讲密度低 + 选段层已过滤 + 跳剪伤专业感；残余价值=停顿收紧，手动路径已存在） | P2（自 P0 下放） | 词级时间戳（已有）；随 Operation Model 一并评估（editor 一键操作方向） | ✅ | ❌（仅 i18n 占位文案） |
| 首发推荐分：持久化 + UI 展示（值 + 打分理由） | 矩阵 §C 改造 | **P0** | ~~`Clip` 表加列~~ `outputs.score` 已建 + 前端展示位 | ✅（LLM 已产出分数） | ✅（2026-07-23：prompt 四维口径 + score={value,reason} 落库 + ClipCard 徽章/榜首 accent + 详情理由；简报：`tasks/score-persistence.md`） |
| 首发推荐分：维度明细 | 矩阵 §C；STRATEGY §2.1 | P1 | 上一行 | ✅ | ❌ |
| 链接摄入子系统（Zoom / Drive / RSS；目标形态 = "接管源后持续自动"而非"手动贴链接"——OpusSearch/Auto import 实证，opusclip §8.2/§5.1） | 矩阵 §A；STRATEGY §1 判断 2 | P1 | 存储层（已有）；独立子系统：轮询、平台 API、失败重试 | — 纯工程 | ❌（FR-018 仅一行） |
| persona 校准打分 | 矩阵 §C；STRATEGY §2.1/§2.2 | P1 | Speaker persona（已有）+ 发布数据回流（见 §5） | ✅ | ❌ |
| RunPlan 持久化 + outputs 统一（`plan_nodes` 施工图 + `outputs` 统一产物表（ADR-030）+ 节点级血统——计划图作为一等对象） | ADR-028/030；STRATEGY §2.5；AGENT_ARCH §12 | **P1（地基）** | 无 | — 纯工程 | ✅ Phase 1（2026-07-22：建表 + orchestrator + 创建点零旁路 + 读路径切换；后续 = 下方导演两步走/质检节点行） |
| 导演两步走（看懂素材/分任务两次调用：素材理解自足契约 + asset hash 失效可复用；分任务=分镜表每 run 重排——覆盖问责：论点→槽位 + 未用/撞车报告；DerivativePlan 退役） | AGENT_ARCH §12；ADR-028 | P1 | RunPlan 持久化 | ✅ | ✅（2026-07-27 主体落地：`director_understand`（asset-hash 复用）+ `director_plan`（分镜表+覆盖问责）两节点，DerivativePlan 退役为槽位，简报 `tasks/director-two-step.md`；逐 clip 论点→槽位归 Phase 2b 选段节点） |
| 结构化节拍图 + clip-spec motion 枚举（分镜入 plan：hook/body/payoff 时间戳；运镜入 spec 预设枚举——ADR-016 纪律不破，仍 CSS/libass 双端可表达） | STRATEGY §2.5；elevencreative | P2 | 覆盖问责 | ⚠️ | ❌（`visual_notes` 自由文本；crop 整条静态） |
| YouTube 链接导入 | 矩阵 §A | 💡 待论证 | 反爬成本评估（Descript 已被逼退，属"别人抛弃的战场"） | — | 💡 |
| 质检节点（原"Layer 4"新形态：单产物质检——分数落库/persona 保真/术语合规，不合格带反馈打回上游 ≤2 次；全片质检——跨产物撞车；verify = plan_nodes 一种 kind） | AGENT_ARCH §12；ADR-028 | P2 | RunPlan 持久化 | ⚠️ | ❌（现有 `agents/reviser.py` 只是单 clip 修订，勿混淆） |

## 2. Operation Model（操作日志层）⭐ 地基

> 2027 架构的核心对冲：editor GUI、chat、MCP 都是操作的三个前端。即使手动编辑占比萎缩，投资全部沉淀在本层。
>
> **生成侧半身**：RunPlan 持久化（§1，ADR-028）与本层同一条原则——**步骤皆可寻址**——分别落在生成侧与编辑侧。
>
> 人话：用户（或 AI）每做一次修改——改标题、改短、换音乐、翻译字幕——不直接改产物数据，而是往 `operations` 表追加一条"做了什么"的记录。好处：每一步可检查、可撤销（undo/redo/恢复版本），chat 和网页剪辑器操作的是同一套动作词汇。

| 需求 | 来源 | 优先级 | 依赖 | Agent 就绪度 | 状态 |
|---|---|---|---|---|---|
| 操作日志表 + undo 语义（非破坏 hidden 之上） | 2027 架构；VIDEO_EDITOR.md 已承诺 undoable | **P1（地基，尽早）** | 无 | — 纯工程 | ✅（2026-07-26：`operations` 表 + 快照式 undo/redo/restore_version 端点，ADR-032；简报 `tasks/operation-model.md`） |
| 操作 = clip-spec diff 的映射规范 | 2027 架构 | P1 | 上一行 | — | ✅（`operations/registry.py`：11 op 初集 + params schema + 纯函数应用，产物级/plan 级两家族分离） |
| agent 可调用的操作 schema（原子、幂等、可检查、可撤销） | 2027 架构 | P1 | 操作日志表；M3 tool-calling spike（见 §3） | ⚠️ | ✅（chat edit_ops 真应用：registry 校验 + message_id 血统 + OpsCard 撤销；MCP 仍 💡） |

## 3. Agent Interface（chat 升级 + MCP）

> chat 从 asset-scoped Modal 快捷服务升级为主交互层：人话 / agent 话 → Operation Model / WorkflowRun 的统一入口。
>
> 用户视角的主流程：composer 写一句话（可附素材）→ 全屏对话里 AI 给出执行计划（产物类型/语言/数量可改）→ 确认后步骤逐行亮起（SSE 打勾流）→ 完成后落在结果页，可继续用自然语言改产物（"把第二条翻译成德语"）。
>
> **随 DAG 内核连带升级（2026-07-22）**：dispatch 目标分三类——editor 操作 / 整体重生成 / **plan 级**（节点重跑·追加·参数："重新选段"=重跑 selection 节点，"加德语版"=追加 post_gen(de) 节点）；ChatCut 原则（指令=可检查可撤销的真实操作，矩阵 §E）推广到计划层。chat 引用模型 = **@ 类型化对象**（产物/节点，elevencreative §8 机制 6）；plan 级指令采纳**子图词汇**——只跑此节点 / 从这里跑 / 跑到这里（机制 5）。详见 CHAT_ARCHITECTURE 与 ADR-029。

| 需求 | 来源 | 优先级 | 依赖 | Agent 就绪度 | 状态 |
|---|---|---|---|---|---|
| chat 接入 LLM 意图解析（`agents/intent.py` 已存在未接线） | 代码现状快赢 | **P1 快赢** | 无 | ✅ | ✅（2026-07-26 随 chat-loop-v1/v2：ChatIntentAgent 二态判别联合，规则版退役） |
| M3 tool-calling spike（验证原生 function calling；不可靠则走"结构化输出模拟工具调用"） | 2027 架构 | **P1（先于一切 agent 设计）** | 无 | ⚠️ 待 spike | ✅（2026-07-27 关闭：spike 之问已被事实回答——chat v1/v2 全链走"结构化输出模拟"（`response_format=json_object` 单轮调用）并实证；原生 function calling 未采用，换 provider 时再重估） |
| LLM provider 抽象层（generate structured / chat with tools 两个方法） | 2027 架构；EU 客户可能要求 Mistral/EU-hosted | **P1** | 无；需修订 ADR-003（当前明确"不做抽象"，是有意决策，翻案要走 ADR） | ⚠️ | ❌（有意未做） |
| 意图 → dispatch 注册表（三类目标：editor 操作——翻译/改短/换音乐/配音/prompt-to-clip；整体重生成；**plan 级**——节点重跑·追加·参数） | 矩阵 §B P1；ChatCut 原则推广到计划层 | P1 | Operation Model + RunPlan + spike 结论 | ⚠️ | 🚧（2026-07-26：editor 操作 ✅（edit ops 接线 ADR-032）+ 追加处理 ✅（模式②，含新 translate_clip/dub_clip）+ 整体重生成 ✅；**plan 级节点重跑·参数仍 ❌**——导演两步走后 `director_plan` 已独立可寻址，"重排任务"具备重跑对象；简报 `tasks/chat-loop-v2.md` §4） |
| chat 指令落地语义：何时产生 editor 操作、何时触发重生成 | 2027 架构 | P1 | 同上 | ⚠️ | ✅（CHAT_ARCH §3 三类目标 + 两家族分离：产物级→operations 表，plan 级→RunPlan 小拓扑） |
| chat 全屏 UI（GenerationOverlay：composer → 计划卡 HITL 确认 → SSE 打勾流 → 结果页；中止/续聊/附件展示） | CHAT_ARCH §3/§8；Opus 交互参照 | P1 | chat v1/v2 后端 | — 纯前端 | ✅（2026-07-27：含失败/完成 toast、完成后结果页自动刷新、空态扁平化；results 首访 Tour 同步落地。2026-07-28：GenerationStepper 弹窗 + 后端 `ui_step` 退役，processing 项目走 `?overlay=run` attach 模式，进度面只剩打勾流一处） |
| ask 原语 + 任务书 slot 化 + 方向检查点（QuestionDock 停靠确认 / QA 入档 / autonomy 自治档 / 逐槽任务书——"英德两版帖"一次 run） | CHAT_ARCH §3/§8.5；矩阵 §E；opusclip §9（Opus HITL 实证）；STRATEGY §2.5 L3 | P1 | chat v2 + Operation Model + RunPlan | ⚠️ | ✅（2026-07-29 **期 1** messages question/answer + answer 端点 + QuestionDock task_book 形态 + QA 入档 + autonomy 落 run.context；**期 2** IntentSlot 全链路换形 + per-slot 扇出 + pin 合并 + 逐槽审阅面板——扁平 count 全库退役；2026-07-30 **期 3** AskProposal 三态（N-18）+ choice dock + 确定性 autoResume + answer 端点续聊 + 入口 reasons 进 question；**期 4** Suspend/waiting + 方向检查点（review 档 full run 插点）+ answer 唤醒/bail 级联 + finalize 谓词补 waiting——简报 `tasks/intent-ask-primitive.md`，NAMING N-18/19/20） |
| MCP server（被外部 agent 调用） | 矩阵 §I P2；MCP 已成行业标准（Linux 基金会 AAIF，97M 月下载）；STRATEGY §1 判断 3 | P2 | Agent Interface 稳定 + API 幂等/结构化错误改造 | ⚠️ | ❌ |
| 运行图检视面（只读为主的 DAG 视图：节点成本/重跑/变体检视；机构"管得住"信任工具——画布对我们是信任工具不是创作工具；无接线、无模型名、非图编辑） | ADR-028 Amendment；elevencreative §3 | P2 | RunPlan 持久化 + 混合图/变体现实（虚拟产物线，ADR-029） | — 纯工程 | ❌ |

## 4. Editor GUI（Operation Model 的前端之一）

> 薄化：不追加 L3 能力（多轨/B-roll/转场明确不做），投资只投向与 Operation Model 的接线。
>
> 人话：网页剪辑器只保留最轻的形态——在文字稿里删一句话就等于剪掉那段视频（非破坏，可恢复），加上单轨裁剪和实时预览。专业剪辑需求明确导出到剪映/Premiere（未来的 XML/EDL 交接），我们不在浏览器里重造专业剪辑软件。

| 需求 | 来源 | 优先级 | 依赖 | Agent 就绪度 | 状态 |
|---|---|---|---|---|---|
| transcript 编辑 / 单轨 trim / Remotion 预览 | — | — | — | ✅ | ✅ 已落地 |
| undo 栈（前端接 Operation Model） | VIDEO_EDITOR.md 已承诺 | P1 | Operation Model | — | 🚧（2026-07-26：端点 + chat 撤销按钮已通；editor 内 undo/redo 按钮 + 历史面板后置——反过度设计裁决，见简报 Phase 2b） |
| 字幕翻译 + 校对视图（side-by-side） | 矩阵 §G | P1 | 多语言输出（已有） | ✅ | ❌ |
| XML / EDL 交接 spec（→ CapCut/Premiere） | ADR-016 | P2 | clip-spec 稳定 | — | ❌ |

## 5. Distribution ⭐ 权重上调

> 用户视角：在 clip 的"···"菜单里点"Publish on Social"，选渠道、确认文案，直接发到 LinkedIn / TikTok——不经过下载再上传。发布结果（成功/失败/授权过期）进通知中心。
>
> 2027 透镜下与 pipeline 平级：Pipeline 管"生成什么"，Distribution 管"去了哪里"。**核心 = 发布动作本身（直发）**——"一次上传、审核即走"的"走"目前断在手动下载再上传，这是正向链路最后一座手动桥。设计与实现细节见 `docs/DISTRIBUTION.md`。
>
> **2026-07-23 定界**：**平台范围 = LinkedIn + TikTok 双平台**（其余 X/Meta/YouTube 不接，ESP P2）；定时发布 / 审核队列 / 发布数据回流为**边缘功能**（全部 P2）——定时是 agency 运营多账号的便利；审核队列是机构形态（ADR-027），个体 ICP 的"审核"就是自己看一眼；回流是校准精密化（内部校准源 = 用户选用行为，见 §1，不依赖本模块）。平台准入（LinkedIn 开发者应用、TikTok 应用审核）是零代码 ops，立即排队——墙钟数周，别等功能排上才启动。

| 需求 | 来源 | 优先级 | 依赖 | Agent 就绪度 | 状态 |
|---|---|---|---|---|---|
| Publication / ChannelAccount 数据模型（含回流分析字段预留） | 矩阵 §H；2027 架构 | **P1（直发的载体，与直发同棒落地）** | 无 | — 纯工程 | ✅（2026-07-23 Phase A 建表 + 服务骨架） |
| 审核队列（机构模式：强制人工确认、审核人≠作者；个人免审秒发——ADR-027） | 矩阵 §H | P2 | 数据模型 + 团队工作区 | — | ❌ |
| LinkedIn OAuth + 直发（2026-07-21 定：**个人号 w_member_social 先行**，公司页后置） | 矩阵 §H | **P1（Distribution 核心兑现，本模块第一棒）** | 数据模型；LinkedIn 开发者应用注册（零代码 ops，立即排队） | — | 🚧（2026-07-24 后端 + 前端已落地：OAuth/adapter/worker 认领 + 发布对话框/通知中心/Settings Channels；待应用凭据联调） |
| TikTok Content Posting API 直发（只做直发；2026-07-23 定：**与 LinkedIn 并列为 P1 双平台**——clips 需要出口；**应用审核零代码 ops 立即排队**，墙钟数周期间测试账号联调） | 矩阵 §H | **P1** | 数据模型；TikTok 开发者应用审核 | — | 🚧（2026-07-24 后端 + 前端已落地同上；待应用审核 + 联调） |
| 定时发布（worker 第四认领源，复用 SKIP LOCKED） | 矩阵 §H | P2（2026-07-23 定界：边缘功能——agency 多账号运营便利，非个体刚需） | 数据模型 + 队列（已有） | — | ❌ |
| 发布数据回流 → 校准首发推荐分 | 2027 架构 | P2 | Publication 回流字段 + 打分持久化 | ✅ | ❌ |
| newsletter ESP 集成（owned channel） | 矩阵 §H；STRATEGY §4 风险 2 | P2 | 数据模型 | — | ❌ |
| 源 → 目的地自动规则 | 矩阵 §H | P2 | LinkedIn 直发跑通 | — | ❌ |

## 6. Memory / Context（Speaker + Brand + 术语表）

> 人话：这一层回答"AI 怎么写得/说得像我"。Speaker = 人的画像（写作风格、口吻、声音克隆），Brand = 视觉皮肤（字体/颜色/logo/字幕样式），术语表 = 固定译法（机构名词不翻错）。生成时这些记忆注入每个环节，产物出来就是"你的味道"而不是"通用 AI 腔"。
>
> 2027 最硬的资产：三个"极高"价值改造项全在这层，且横切所有模块（director 注入 / chat 上下文 / editor 品牌皮肤 / 分发调性）。LinkedIn 对"通用 AI 腔"约 94% 检测率 + 30% 触达惩罚，Voice DNA 已成 B2B 必需品——我们的 persona 恰好是正确答案，应升级为对外卖点。

| 需求 | 来源 | 优先级 | 依赖 | Agent 就绪度 | 状态 |
|---|---|---|---|---|---|
| Speaker persona（风格记忆） | ADR-021 | — | — | ✅ | ✅ 已落地 |
| Brand template | — | — | — | ✅ | ✅ 已落地 |
| 术语表 / glossary（机构级翻译质量；含 transcript "Correct everywhere" 批量纠错入口——矩阵 §E；**一份资产两消费者**：固定译法喂翻译 + 发音喂 dub——Opus Pronunciation 实证，opusclip §4 2026-07-28） | 矩阵 §G "极高"；PRD §4.2（对桥梁型 seed ICP 是生存项：固定译法 = 专业尊严） | P1 | persona 注入链路（已有） | ✅ | ❌（仅一条 i18n 占位文案） |
| 多语言文案质量（Voice DNA 跨语言保真） | 矩阵 §G "极高"；2026 B2B 趋势 | P1 | 术语表 | ✅ | ❌ |
| persona 显化于 UI（让用户看到/编辑自己的 Voice DNA） | 2027 架构；STRATEGY §2.2 | P2 | — | ✅ | ❌ |

## 7. 合规底座 ⚖️ 法律时限

> 人话：卖欧洲机构，法律要求 AI 生成内容必须带"机器可读的 AI 标识"（不是界面上贴个徽章，而是嵌进文件元数据，平台/工具能自动识别）。哪些内容要标可以自动判定：整条都是 AI 合成的（配音/生成视觉）要标，纯剪辑真人素材豁免。
>
> EU AI Act Article 50：AI 生成内容须机器可读标识 + 披露，**2026-08-02 生效**（已上市系统宽限至 2026-12-02），罚则最高 €35M / 全球营收 7%。我们是面向欧洲机构的产品，这不是加分项是入场券；七家竞品全部 structural 缺席，同时是差异化。呈现野心参照：ElevenCreative（物种不同）已把合规做成具名可购 SKU——Zero Retention mode / Data Residency options / HIPAA BAA 全挂定价档（research/elevencreative.md §2）；本节各行落地时应以"有名字的开关"形态出现，而非安全页徽章（STRATEGY §2.3）。
>
> **2026-07-23 降级决策**：AI 内容标识三行从 P0 降为 **P1**——产品未上线，Art.50 义务自实际上线日起适用（宽限期只覆盖 2026-08-02 前已上市的系统，不直接覆盖我们）；现阶段优先保证功能线发展。**上线前必须回补**（机构采购必问，且这是法律义务不是选项）。

| 需求 | 来源 | 优先级 | 依赖 | Agent 就绪度 | 状态 |
|---|---|---|---|---|---|
| AI 内容机器可读标识：合成轨道（dub/生成视觉）强制 C2PA，纯剪辑豁免；分类器从 clip-spec 自动判定 | EU AI Act Art.50；ADR-026 | P1（2026-07-23 自 P0 降级，上线前必须回补） | clip-spec 扩展 + render 服务（已有）；C2PA 库选型调研 | — | ❌ |
| 披露元数据随分发层携带（`ai_disclosure` 由 clip-spec 分类器推导，非用户勾选） | EU AI Act Art.50；2027 架构；ADR-026 | P1（同上降级） | Distribution 数据模型 | — | ❌ |
| 界面披露提示（导出/发布时的 AI 内容声明） | EU AI Act Art.50 | P1（同上降级） | 无 | — | ❌ |
| 数据生命周期文档（retention / 删除权 / 导出）——机构采购必问 | GDPR | P1 | 无 | — | ❌ |
| EU 数据驻留（存储 key 布局 + 队列区域路由） | 矩阵 §I | P2 | 现存储按 `{user_id}/` 前缀，需评估改造面 | — | ❌ |
| 模型 EU-hosted 选项（Mistral 等） | 2027 架构 | P2 | provider 抽象（§3） | ⚠️ | ❌ |

## 8. 平台与计费

> 人话：每次生成实际花了多少 LLM/渲染成本，系统已经逐步记录下来（每个任务节点一笔账）。在此之上做：生成前预估"这次大约花多少"、失败不扣费、套餐定价（候选形态 = 按"一场演讲一套内容包"计价，而不是裸 credit 点数）。
>
> "可预期 > 便宜"是矩阵定的信任差异化；不透明 credit 计费正遭全行业反弹。

| 需求 | 来源 | 优先级 | 依赖 | Agent 就绪度 | 状态 |
|---|---|---|---|---|---|
| WorkflowRun 成本列 + 每次 stage 计量 | 矩阵 §I | **P0**（同 §1 计量钩子，同一件事） | 无 | — | ✅（节点级 = `plan_nodes.cost`；run 级 = 节点聚合视图，无独立列） |
| 成本预估展示（生成前） | 矩阵 §I；STRATEGY §2.3；elevencreative §8 机制 5（子图级积分预览实证） | P1（**提速**：对手已到动作级标价——Opus 生成按钮带价、按 part 重生成 20⚡（opusclip §8.1），再晚追不平） | 成本计量数据积累 | — | ❌ |
| 失败不扣费语义 | 矩阵 §I；STRATEGY §2.3 | P1 | 成本计量 | — | ❌ |
| 套餐经济设计（档位 / 免费额度 / credits↔产出换算；**计费形态候选 = 按结果包计价**——一场演讲 = 一套内容包，而非裸 credit；呼应 PRD §4.2 本人验收主路径与 STRATEGY §2.3 "可预期 > 便宜"） | 审计 2026-07-22；Opus pricing 参照（agent-opus §5） | P1 | 成本计量；文档坑位 BILLING.md 已登记（README） | — | ❌ |
| 产品度量地基（漏斗事件埋点：上传→生成→精修→发布→回流；各阶段成功指标） | 审计 2026-07-22 | P1（轻量，随功能落地同步埋点；验证 §9 Phase 1 激活效果的前置） | 无；文档坑位 METRICS.md 已登记（README） | — 纯工程 | ❌ |
| 团队工作区 / 多 Speaker 画像 | 矩阵 §I | P2 | auth（已有）| — | ❌ |

---

## 9. Gallery / 落地页（获客与激活）

> 人话：没注册的人看到的是公开落地页（讲清楚产品怎么工作）；注册后首页是 composer 工作台。"配方卡"是预设示例——"一场 TED 演讲 → 5 条 clips + LinkedIn 长文"这样的卡片，点一下就用同样参数跑你自己的素材。
>
> 品味的陈列窗（STRATEGY §5）：**配方库而非内容流**——每张卡 = 输入 + 输出 + 参数集，"Make one like this" 预填 composer，用户只上传自己的素材。同一套组件服务匿名落地页与已登录 home 两个受众；home 的 hero 文案随之迁往匿名落地页（受众错配修复）。

| 需求 | 来源 | 优先级 | 依赖 | Agent 就绪度 | 状态 |
|---|---|---|---|---|---|
| 配方卡（3–6 个硬编码预设）+ 落地页（parallax：hero + 工作流叙事 + 信任带 + pricing 预告）+ 匿名/已登录路由分流 + 通知中心去占位（铃铛真实设计：发布结果 / 功能公告） | STRATEGY §5；agent-opus §3 | P1（纯前端、无新表，可灵活插队） | 无（预览素材需自备——demo talk 已随 demo seed 于 2026-07-27 退役） | — 纯工程 | 🚧（2026-07-24：**通知中心已提前落地**——`notifications` 表 + 全局顶栏铃铛 + 发布结果三类事件，distribution 为第一个事件源，见 `tasks/publish-dialog-notifications.md`；2026-07-25：**落地页已落地**——`/` 公开落地页（header/hero/工作流叙事/信任带/roadmap/footer，`motion` 视差），sidebar 工作台迁入 `_app` pathless layout（原 `/` → `/home`，其余 URL 不变），pricing 区按决策暂缓；配方卡 ❌ → 2026-07-30 **方向修订**：从"参数预设卡"升级为**能力演示视频卡**（dub / 图片视频 / 分镜 / 风格四张，配方=能力承诺、逐张点亮），实施架构与 R1–R4 分期见 `RECIPES.md`；2026-07-31 **R1 已落地**——caption catalog（`packages/clip` 单点）+ stacking preset + dub_languages/fork 配音接线 + 首页卡片层（dub 卡点亮，预览走 CSS blur-pad）） |
| 真实 Gallery（公开项目流入 + remix） | STRATEGY §5 | P2 | 上一行验证 + `projects`/`clips` 公开性字段（须先 MODULE_ARCH §4 登记 + ADR） | — 纯工程 | ❌ |

---

## 跨模块依赖图

```
成本计量钩子 (P0) ────────────────────────────► 成本预估 / 失败不扣费 (P1)
首发推荐分持久化 (P0) ──► Distribution 回流 (P2) ──► persona 校准打分 (P1)

Operation Model (P1 地基) ──┬──► Editor undo 栈 (P1)
                            ├──► chat 意图→操作 dispatch (P1)
                            └──► Consistency Reviser (P2)

RunPlan 持久化 (P1 地基, ADR-028) ──┬──► 逐节点成本归属 ──► 成本预估 (P1)
                                    ├──► 覆盖问责 (P1) ──► 节拍+motion 枚举 (P2)
                                    ├──► 配方 = run-plan 模板 (STRATEGY §5)
                                    └──► 运行图检视面 (P2, ADR-028 Amendment)

M3 tool-calling spike (P1) ──► Operation schema ──► Agent Interface ──► MCP (P2)
provider 抽象 (P1, 需修订 ADR-003) ──► EU-hosted 模型选项 (P2)

Distribution 数据模型 (P1) ──► LinkedIn + TikTok 直发 (P1 双平台) / 定时发布·审核队列 (P2 边缘)
                           └──► 披露元数据随分发携带 (P1, 合规)

clip-spec 扩展 (P1 合规标识) ──► render 服务打标 ──► XML/EDL 交接 (P2)

配方卡 (P1 纯前端, 无依赖) ──► 真实 Gallery (P2, 需公开性字段登记 + ADR)
```

## P0 汇总（下次排期会议只看这张）

| # | 事项 | 模块 | 一句话理由 |
|---|---|---|---|
| 1 | ~~AI 内容标识（C2PA/元数据 + 界面披露）~~ → **P1**（2026-07-23 降级：未上线，义务自上线日起算，上线前必须回补，见 §7） | 合规 | EU AI Act Art.50，2026-08-02 生效 |
| 2 | ~~成本计量钩子~~ ✅（2026-07-22 随 RunPlan Phase 1 落地） | Pipeline/计费 | 趁管线热埋点，后补成本极高；透明定价的地基 |
| 3 | ~~首发推荐分：持久化 + UI（值+理由）~~ ✅（2026-07-23 落地） | Pipeline | LLM 已产出分数，落库+展示是低成本高兑现；只答"哪条最值得你先发"，不预测传播量 |
| 4 | ~~去静默 / 去口头禅~~ → **P2**（2026-07-23 重估下放：播客刚需 ≠ 演讲刚需，选段层已过滤，跳剪伤专业感；P0 清单清空） | Pipeline | 矩阵 §B 行 |

---

## 附：文档与代码不符纠偏清单（2026-07 代码扫描发现，2026-07-20 已全部处理）

排期之外，代码扫描发现的文档/代码不符点。逐条核实后的结论与处理：

1. **Virality Score 表述** — 核实后**部分误报**：`COMPETITIVE_ANALYSIS.md` 的 "Virality Score ✅ 唯一" 指的是 **Opus 在七家竞品中独有**（表格列全是竞品），不是声称我们已有；PRD 的 "Virality Score™" 出现在竞品借鉴表中，属目标功能规格，合规。真正的缺口是没有任何地方标注实现落差 → 已在 PRD FR-020 补实现状态注记（LLM 已产出分数但未持久化/未展示，即本表 P0-3）。
2. **`VIDEO_EDITOR.md` 承诺 undoable** — 删句剪视频已实现，undo 未实现 → 已在该句补注"undo 待 Operation Model（本表 §2）"。
3. **前端 i18n 已预置 `removeFiller: "去除口头禅"` 文案** — 无任何逻辑，易误判功能存在。该功能 2026-07-23 已下放 P2（矩阵 §B），文案维持死占位，随 P2 落地一并处理。
4. **`AGENT_ARCHITECTURE.md` Layer 4** — 核实后**部分误报**：图上已标注 "reserved for future"，但 `agents/reviser.py`（单 clip 修订 agent）与 Layer 4 命名易混淆 → 已在图下加命名警示注记。
5. **`Message.intent` 列注释写 "parsed LLM intent"** — 实际是规则分类结果，LLM parser（`agents/intent.py`）未接入 chat → 已改注释如实描述。
6. **`MUSIC_ARCHITECTURE.md` 状态仍是 Proposed** — Music 表、MiniMax music-2.6 生成、管线集成均已上线 → 状态已改为 Implemented（Layer-4 音乐校验仍标注 future）。

另：`tables.py` 注释改动属代码注释修正，不涉及迁移。
