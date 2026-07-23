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

## 1. Pipeline（生成管线）

> 定位：必需但是成本中心，不追加差异化投入；现有 4-layer 编排已超前，保持即可。

| 需求 | 来源 | 优先级 | 依赖 | Agent 就绪度 | 状态 |
|---|---|---|---|---|---|
| 4-layer 编排（Director/Executors） | — | — | — | ✅ | ✅ 已落地 |
| 词级时间戳 ASR | — | — | — | ✅ | ✅ 已落地 |
| 成本计量钩子（minimax usage 入 WorkflowRun） | 矩阵 §I；2027 架构 | **P0** | 无（趁管线还热先埋，后补成本极高） | — 纯工程 | ❌（`clients/minimax.py` 丢弃 usage 字段） |
| 去静默 / 去口头禅 | 矩阵 §B 快赢 | **P0** | 词级时间戳（已有）；归属决策：ASR 后处理 vs editor 一键操作 | ✅ | ❌（仅 i18n 占位文案） |
| 传播潜力分：持久化 + UI 展示 | 矩阵 §C 改造 | **P0** | `Clip` 表加列 + 前端展示位 | ✅（LLM 已产出分数） | 🚧（分数只写日志，不落库不展示） |
| 传播潜力分：维度明细 + 打分理由 | 矩阵 §C；STRATEGY §2.1 | P1 | 上一行 | ✅ | ❌ |
| 链接摄入子系统（Zoom / Drive / RSS；目标形态 = "接管源后持续自动"而非"手动贴链接"——OpusSearch/Auto import 实证，opusclip §8.2/§5.1） | 矩阵 §A；STRATEGY §1 判断 2 | P1 | 存储层（已有）；独立子系统：轮询、平台 API、失败重试 | — 纯工程 | ❌（FR-018 仅一行） |
| persona 校准打分 | 矩阵 §C；STRATEGY §2.1/§2.2 | P1 | Speaker persona（已有）+ 发布数据回流（见 §5） | ✅ | ❌ |
| RunPlan 持久化 + outputs 统一（`plan_nodes` 施工图 + `outputs` 统一产物表（ADR-030）+ 节点级血统——计划图作为一等对象） | ADR-028/030；STRATEGY §2.5；AGENT_ARCH §12 | **P1（地基）** | 无 | — 纯工程 | ❌（计划为单趟易失对象；产物劈两张表；`current_step` 裸字符串） |
| 导演两步走（看懂素材/分任务两次调用：素材理解自足契约 + asset hash 失效可复用；分任务=分镜表每 run 重排——覆盖问责：论点→槽位 + 未用/撞车报告；DerivativePlan 退役） | AGENT_ARCH §12；ADR-028 | P1 | RunPlan 持久化 | ✅ | ❌（Director 单趟一坨 + project.content_plan 盲目复用 + 伪造 DerivativePlan） |
| 结构化节拍图 + clip-spec motion 枚举（分镜入 plan：hook/body/payoff 时间戳；运镜入 spec 预设枚举——ADR-016 纪律不破，仍 CSS/libass 双端可表达） | STRATEGY §2.5；elevencreative | P2 | 覆盖问责 | ⚠️ | ❌（`visual_notes` 自由文本；crop 整条静态） |
| YouTube 链接导入 | 矩阵 §A | 💡 待论证 | 反爬成本评估（Descript 已被逼退，属"别人抛弃的战场"） | — | 💡 |
| 质检节点（原"Layer 4"新形态：单产物质检——分数落库/persona 保真/术语合规，不合格带反馈打回上游 ≤2 次；全片质检——跨产物撞车；verify = plan_nodes 一种 kind） | AGENT_ARCH §12；ADR-028 | P2 | RunPlan 持久化 | ⚠️ | ❌（现有 `agents/reviser.py` 只是单 clip 修订，勿混淆） |

## 2. Operation Model（操作日志层）⭐ 地基

> 2027 架构的核心对冲：editor GUI、chat、MCP 都是操作的三个前端。即使手动编辑占比萎缩，投资全部沉淀在本层。
>
> **生成侧半身**：RunPlan 持久化（§1，ADR-028）与本层同一条原则——**步骤皆可寻址**——分别落在生成侧与编辑侧。

| 需求 | 来源 | 优先级 | 依赖 | Agent 就绪度 | 状态 |
|---|---|---|---|---|---|
| 操作日志表 + undo 语义（非破坏 hidden 之上） | 2027 架构；VIDEO_EDITOR.md 已承诺 undoable | **P1（地基，尽早）** | 无 | — 纯工程 | ❌（全仓无 undo 栈/操作日志表） |
| 操作 = clip-spec diff 的映射规范 | 2027 架构 | P1 | 上一行 | — | ❌ |
| agent 可调用的操作 schema（原子、幂等、可检查、可撤销） | 2027 架构 | P1 | 操作日志表；M3 tool-calling spike（见 §3） | ⚠️ | ❌ |

## 3. Agent Interface（chat 升级 + MCP）

> chat 从 asset-scoped Modal 快捷服务升级为主交互层：人话 / agent 话 → Operation Model / WorkflowRun 的统一入口。
>
> **随 DAG 内核连带升级（2026-07-22）**：dispatch 目标分三类——editor 操作 / 整体重生成 / **plan 级**（节点重跑·追加·参数："重新选段"=重跑 selection 节点，"加德语版"=追加 post_gen(de) 节点）；ChatCut 原则（指令=可检查可撤销的真实操作，矩阵 §E）推广到计划层。chat 引用模型 = **@ 类型化对象**（产物/节点，elevencreative §8 机制 6）；plan 级指令采纳**子图词汇**——只跑此节点 / 从这里跑 / 跑到这里（机制 5）。详见 CHAT_ARCHITECTURE（待写）与 ADR-029。

| 需求 | 来源 | 优先级 | 依赖 | Agent 就绪度 | 状态 |
|---|---|---|---|---|---|
| chat 接入 LLM 意图解析（`agents/intent.py` 已存在未接线） | 代码现状快赢 | **P1 快赢** | 无 | ✅ | 🚧（chat 用纯关键词规则，`Message.intent` 注释与实际不符） |
| M3 tool-calling spike（验证原生 function calling；不可靠则走"结构化输出模拟工具调用"） | 2027 架构 | **P1（先于一切 agent 设计）** | 无 | ⚠️ 待 spike | ❌ |
| LLM provider 抽象层（generate structured / chat with tools 两个方法） | 2027 架构；EU 客户可能要求 Mistral/EU-hosted | **P1** | 无；需修订 ADR-003（当前明确"不做抽象"，是有意决策，翻案要走 ADR） | ⚠️ | ❌（有意未做） |
| 意图 → dispatch 注册表（三类目标：editor 操作——翻译/改短/换音乐/配音/prompt-to-clip；整体重生成；**plan 级**——节点重跑·追加·参数） | 矩阵 §B P1；ChatCut 原则推广到计划层 | P1 | Operation Model + RunPlan + spike 结论 | ⚠️ | ❌ |
| chat 指令落地语义：何时产生 editor 操作、何时触发重生成 | 2027 架构 | P1 | 同上 | ⚠️ | ❌（需 CHAT_ARCHITECTURE 文档仲裁） |
| MCP server（被外部 agent 调用） | 矩阵 §I P2；MCP 已成行业标准（Linux 基金会 AAIF，97M 月下载）；STRATEGY §1 判断 3 | P2 | Agent Interface 稳定 + API 幂等/结构化错误改造 | ⚠️ | ❌ |
| 运行图检视面（只读为主的 DAG 视图：节点成本/重跑/变体检视；机构"管得住"信任工具——画布对我们是信任工具不是创作工具；无接线、无模型名、非图编辑） | ADR-028 Amendment；elevencreative §3 | P2 | RunPlan 持久化 + 混合图/变体现实（虚拟产物线，ADR-029） | — 纯工程 | ❌ |

## 4. Editor GUI（Operation Model 的前端之一）

> 薄化：不追加 L3 能力（多轨/B-roll/转场明确不做），投资只投向与 Operation Model 的接线。

| 需求 | 来源 | 优先级 | 依赖 | Agent 就绪度 | 状态 |
|---|---|---|---|---|---|
| transcript 编辑 / 单轨 trim / Remotion 预览 | — | — | — | ✅ | ✅ 已落地 |
| undo 栈（前端接 Operation Model） | VIDEO_EDITOR.md 已承诺 | P1 | Operation Model | — | ❌ |
| 字幕翻译 + 校对视图（side-by-side） | 矩阵 §G | P1 | 多语言输出（已有） | ✅ | ❌ |
| XML / EDL 交接 spec（→ CapCut/Premiere） | ADR-016 | P2 | clip-spec 稳定 | — | ❌ |

## 5. Distribution ⭐ 权重上调

> 2027 透镜下与 pipeline 平级：审核队列是 HITL 的正确形态；发布数据回流是传播潜力分唯一的真实校准源——现在不定表结构，闭环永远断着。设计与实现细节见 `docs/DISTRIBUTION.md`。

| 需求 | 来源 | 优先级 | 依赖 | Agent 就绪度 | 状态 |
|---|---|---|---|---|---|
| Publication / ChannelAccount 数据模型（含回流分析字段预留） | 矩阵 §H；2027 架构 | **P1（表结构先行，功能可后做）** | 无 | — 纯工程 | ❌（无任何代码） |
| 审核队列（机构模式：强制人工确认、审核人≠作者；个人免审秒发——ADR-027） | 矩阵 §H | P2 | 数据模型 + 团队工作区 | — | ❌ |
| LinkedIn OAuth + 直发（2026-07-21 定：**个人号 w_member_social 先行**，公司页后置） | 矩阵 §H | P1 | 数据模型；LinkedIn 开发者应用注册 | — | ❌ |
| TikTok Content Posting API 直发（2026-07-21 定：**只做直发，立即提交应用审核**——墙钟数周，期间用测试账号联调） | 矩阵 §H | P1 | 数据模型；TikTok 开发者应用审核 | — | ❌ |
| 定时发布（worker 第四认领源，复用 SKIP LOCKED） | 矩阵 §H | P1 | 数据模型 + 队列（已有） | — | ❌ |
| 发布数据回流 → 校准传播潜力分 | 2027 架构 | P2 | Publication 回流字段 + 打分持久化 | ✅ | ❌ |
| newsletter ESP 集成（owned channel） | 矩阵 §H；STRATEGY §4 风险 2 | P2 | 数据模型 | — | ❌ |
| 源 → 目的地自动规则 | 矩阵 §H | P2 | LinkedIn 直发跑通 | — | ❌ |

## 6. Memory / Context（Speaker + Brand + 术语表）

> 2027 最硬的资产：三个"极高"价值改造项全在这层，且横切所有模块（director 注入 / chat 上下文 / editor 品牌皮肤 / 分发调性）。LinkedIn 对"通用 AI 腔"约 94% 检测率 + 30% 触达惩罚，Voice DNA 已成 B2B 必需品——我们的 persona 恰好是正确答案，应升级为对外卖点。

| 需求 | 来源 | 优先级 | 依赖 | Agent 就绪度 | 状态 |
|---|---|---|---|---|---|
| Speaker persona（风格记忆） | ADR-021 | — | — | ✅ | ✅ 已落地 |
| Brand template | — | — | — | ✅ | ✅ 已落地 |
| 术语表 / glossary（机构级翻译质量；含 transcript "Correct everywhere" 批量纠错入口——矩阵 §E） | 矩阵 §G "极高"；PRD §4.2（对桥梁型 seed ICP 是生存项：固定译法 = 专业尊严） | P1 | persona 注入链路（已有） | ✅ | ❌（仅一条 i18n 占位文案） |
| 多语言文案质量（Voice DNA 跨语言保真） | 矩阵 §G "极高"；2026 B2B 趋势 | P1 | 术语表 | ✅ | ❌ |
| persona 显化于 UI（让用户看到/编辑自己的 Voice DNA） | 2027 架构；STRATEGY §2.2 | P2 | — | ✅ | ❌ |

## 7. 合规底座 ⚖️ 法律时限

> EU AI Act Article 50：AI 生成内容须机器可读标识 + 披露，**2026-08-02 生效**（已上市系统宽限至 2026-12-02），罚则最高 €35M / 全球营收 7%。我们是面向欧洲机构的产品，这不是加分项是入场券；七家竞品全部 structural 缺席，同时是差异化。呈现野心参照：ElevenCreative（物种不同）已把合规做成具名可购 SKU——Zero Retention mode / Data Residency options / HIPAA BAA 全挂定价档（research/elevencreative.md §2）；本节各行落地时应以"有名字的开关"形态出现，而非安全页徽章（STRATEGY §2.3）。

| 需求 | 来源 | 优先级 | 依赖 | Agent 就绪度 | 状态 |
|---|---|---|---|---|---|
| AI 内容机器可读标识：合成轨道（dub/生成视觉）强制 C2PA，纯剪辑豁免；分类器从 clip-spec 自动判定 | EU AI Act Art.50；ADR-026 | **P0（法律时限）** | clip-spec 扩展 + render 服务（已有）；C2PA 库选型调研 | — | ❌ |
| 披露元数据随分发层携带（`ai_disclosure` 由 clip-spec 分类器推导，非用户勾选） | EU AI Act Art.50；2027 架构；ADR-026 | **P0** | Distribution 数据模型 | — | ❌ |
| 界面披露提示（导出/发布时的 AI 内容声明） | EU AI Act Art.50 | P0 | 无 | — | ❌ |
| 数据生命周期文档（retention / 删除权 / 导出）——机构采购必问 | GDPR | P1 | 无 | — | ❌ |
| EU 数据驻留（存储 key 布局 + 队列区域路由） | 矩阵 §I | P2 | 现存储按 `{user_id}/` 前缀，需评估改造面 | — | ❌ |
| 模型 EU-hosted 选项（Mistral 等） | 2027 架构 | P2 | provider 抽象（§3） | ⚠️ | ❌ |

## 8. 平台与计费

> "可预期 > 便宜"是矩阵定的信任差异化；不透明 credit 计费正遭全行业反弹。

| 需求 | 来源 | 优先级 | 依赖 | Agent 就绪度 | 状态 |
|---|---|---|---|---|---|
| WorkflowRun 成本列 + 每次 stage 计量 | 矩阵 §I | **P0**（同 §1 计量钩子，同一件事） | 无 | — | ❌ |
| 成本预估展示（生成前） | 矩阵 §I；STRATEGY §2.3；elevencreative §8 机制 5（子图级积分预览实证） | P1（**提速**：对手已到动作级标价——Opus 生成按钮带价、按 part 重生成 20⚡（opusclip §8.1），再晚追不平） | 成本计量数据积累 | — | ❌ |
| 失败不扣费语义 | 矩阵 §I；STRATEGY §2.3 | P1 | 成本计量 | — | ❌ |
| 套餐经济设计（档位 / 免费额度 / credits↔产出换算；**计费形态候选 = 按结果包计价**——一场演讲 = 一套内容包，而非裸 credit；呼应 PRD §4.2 本人验收主路径与 STRATEGY §2.3 "可预期 > 便宜"） | 审计 2026-07-22；Opus pricing 参照（agent-opus §5） | P1 | 成本计量；文档坑位 BILLING.md 已登记（README） | — | ❌ |
| 产品度量地基（漏斗事件埋点：上传→生成→精修→发布→回流；各阶段成功指标） | 审计 2026-07-22 | P1（轻量，随功能落地同步埋点；验证 §9 Phase 1 激活效果的前置） | 无；文档坑位 METRICS.md 已登记（README） | — 纯工程 | ❌ |
| 团队工作区 / 多 Speaker 画像 | 矩阵 §I | P2 | auth（已有）| — | ❌ |

---

## 9. Gallery / 落地页（获客与激活）

> 品味的陈列窗（STRATEGY §5）：**配方库而非内容流**——每张卡 = 输入 + 输出 + 参数集，"Make one like this" 预填 composer，用户只上传自己的素材。同一套组件服务匿名落地页与已登录 home 两个受众；home 的 hero 文案随之迁往匿名落地页（受众错配修复）。

| 需求 | 来源 | 优先级 | 依赖 | Agent 就绪度 | 状态 |
|---|---|---|---|---|---|
| 配方卡（3–6 个硬编码预设）+ 落地页（parallax：hero + 工作流叙事 + 信任带 + pricing 预告）+ 匿名/已登录路由分流 + 通知中心去占位（铃铛真实设计：发布结果 / 功能公告） | STRATEGY §5；agent-opus §3 | P1（纯前端、无新表，可灵活插队） | 无（预览素材复用 demo talk） | — 纯工程 | ❌ |
| 真实 Gallery（公开项目流入 + remix） | STRATEGY §5 | P2 | 上一行验证 + `projects`/`clips` 公开性字段（须先 MODULE_ARCH §4 登记 + ADR） | — 纯工程 | ❌ |

---

## 跨模块依赖图

```
成本计量钩子 (P0) ────────────────────────────► 成本预估 / 失败不扣费 (P1)
传播分持久化 (P0) ──► Distribution 回流 (P2) ──► persona 校准打分 (P1)

Operation Model (P1 地基) ──┬──► Editor undo 栈 (P1)
                            ├──► chat 意图→操作 dispatch (P1)
                            └──► Consistency Reviser (P2)

RunPlan 持久化 (P1 地基, ADR-028) ──┬──► 逐节点成本归属 ──► 成本预估 (P1)
                                    ├──► 覆盖问责 (P1) ──► 节拍+motion 枚举 (P2)
                                    ├──► 配方 = run-plan 模板 (STRATEGY §5)
                                    └──► 运行图检视面 (P2, ADR-028 Amendment)

M3 tool-calling spike (P1) ──► Operation schema ──► Agent Interface ──► MCP (P2)
provider 抽象 (P1, 需修订 ADR-003) ──► EU-hosted 模型选项 (P2)

Distribution 数据模型 (P1) ──► 审核队列 / LinkedIn 直发 / 定时发布 (P1)
                           └──► 披露元数据随分发携带 (P0, 合规)

clip-spec 扩展 (P0 合规标识) ──► render 服务打标 ──► XML/EDL 交接 (P2)

配方卡 (P1 纯前端, 无依赖) ──► 真实 Gallery (P2, 需公开性字段登记 + ADR)
```

## P0 汇总（下次排期会议只看这张）

| # | 事项 | 模块 | 一句话理由 |
|---|---|---|---|
| 1 | AI 内容标识（C2PA/元数据 + 界面披露） | 合规 | EU AI Act Art.50，2026-08-02 生效，法律时限 |
| 2 | 成本计量钩子 | Pipeline/计费 | 趁管线热埋点，后补成本极高；透明定价的地基 |
| 3 | 传播潜力分：持久化 + UI | Pipeline | LLM 已产出分数，落库+展示是低成本高兑现 |
| 4 | 去静默 / 去口头禅 | Pipeline | 矩阵快赢，词级时间戳已有 |

---

## 附：文档与代码不符纠偏清单（2026-07 代码扫描发现，2026-07-20 已全部处理）

排期之外，代码扫描发现的文档/代码不符点。逐条核实后的结论与处理：

1. **Virality Score 表述** — 核实后**部分误报**：`COMPETITIVE_ANALYSIS.md` 的 "Virality Score ✅ 唯一" 指的是 **Opus 在七家竞品中独有**（表格列全是竞品），不是声称我们已有；PRD 的 "Virality Score™" 出现在竞品借鉴表中，属目标功能规格，合规。真正的缺口是没有任何地方标注实现落差 → 已在 PRD FR-020 补实现状态注记（LLM 已产出分数但未持久化/未展示，即本表 P0-3）。
2. **`VIDEO_EDITOR.md` 承诺 undoable** — 删句剪视频已实现，undo 未实现 → 已在该句补注"undo 待 Operation Model（本表 §2）"。
3. **前端 i18n 已预置 `removeFiller: "去除口头禅"` 文案** — 无任何逻辑，易误判功能存在。P0-4 落地前建议注释或标记（前端改动，随 P0-4 一并处理）。
4. **`AGENT_ARCHITECTURE.md` Layer 4** — 核实后**部分误报**：图上已标注 "reserved for future"，但 `agents/reviser.py`（单 clip 修订 agent）与 Layer 4 命名易混淆 → 已在图下加命名警示注记。
5. **`Message.intent` 列注释写 "parsed LLM intent"** — 实际是规则分类结果，LLM parser（`agents/intent.py`）未接入 chat → 已改注释如实描述。
6. **`MUSIC_ARCHITECTURE.md` 状态仍是 Proposed** — Music 表、MiniMax music-2.6 生成、管线集成均已上线 → 状态已改为 Implemented（Layer-4 音乐校验仍标注 future）。

另：`tables.py` 注释改动属代码注释修正，不涉及迁移。
