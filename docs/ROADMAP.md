# Roadmap — 分模块需求排期

> 本文档是**排期表，不是论证场**。理由与依据只引用来源条目（`矩阵 §X` = `docs/DECISION_MATRIX.md`，`竞品` = `docs/research/`，`2027 架构` = `docs/MODULE_ARCHITECTURE.md` 的六层模块契约），论证留在原文档。
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
| 传播潜力分：维度明细 + 打分理由 | 矩阵 §C | P1 | 上一行 | ✅ | ❌ |
| 链接摄入子系统（Zoom / Drive / RSS） | 矩阵 §A | P1 | 存储层（已有）；独立子系统：轮询、平台 API、失败重试 | — 纯工程 | ❌（FR-018 仅一行） |
| persona 校准打分 | 矩阵 §C | P1 | Speaker persona（已有）+ 发布数据回流（见 §5） | ✅ | ❌ |
| YouTube 链接导入 | 矩阵 §A | 💡 待论证 | 反爬成本评估（Descript 已被逼退，属"别人抛弃的战场"） | — | 💡 |
| Consistency Reviser（真正的 Layer 4） | AGENT_ARCH §10.1 | P2 | Operation Model（修订即操作） | ⚠️ | ❌（现有 `agents/reviser.py` 只是单 clip 修订，勿混淆） |

## 2. Operation Model（操作日志层）⭐ 地基

> 2027 架构的核心对冲：editor GUI、chat、MCP 都是操作的三个前端。即使手动编辑占比萎缩，投资全部沉淀在本层。

| 需求 | 来源 | 优先级 | 依赖 | Agent 就绪度 | 状态 |
|---|---|---|---|---|---|
| 操作日志表 + undo 语义（非破坏 hidden 之上） | 2027 架构；VIDEO_EDITOR.md 已承诺 undoable | **P1（地基，尽早）** | 无 | — 纯工程 | ❌（全仓无 undo 栈/操作日志表） |
| 操作 = clip-spec diff 的映射规范 | 2027 架构 | P1 | 上一行 | — | ❌ |
| agent 可调用的操作 schema（原子、幂等、可检查、可撤销） | 2027 架构 | P1 | 操作日志表；M3 tool-calling spike（见 §3） | ⚠️ | ❌ |

## 3. Agent Interface（chat 升级 + MCP）

> chat 从 asset-scoped Modal 快捷服务升级为主交互层：人话 / agent 话 → Operation Model / WorkflowRun 的统一入口。

| 需求 | 来源 | 优先级 | 依赖 | Agent 就绪度 | 状态 |
|---|---|---|---|---|---|
| chat 接入 LLM 意图解析（`agents/intent.py` 已存在未接线） | 代码现状快赢 | **P1 快赢** | 无 | ✅ | 🚧（chat 用纯关键词规则，`Message.intent` 注释与实际不符） |
| M3 tool-calling spike（验证原生 function calling；不可靠则走"结构化输出模拟工具调用"） | 2027 架构 | **P1（先于一切 agent 设计）** | 无 | ⚠️ 待 spike | ❌ |
| LLM provider 抽象层（generate structured / chat with tools 两个方法） | 2027 架构；EU 客户可能要求 Mistral/EU-hosted | **P1** | 无；需修订 ADR-003（当前明确"不做抽象"，是有意决策，翻案要走 ADR） | ⚠️ | ❌（有意未做） |
| 意图 → 操作 dispatch 注册表（翻译/改短/换音乐/配音/prompt-to-clip） | 矩阵 §B P1 | P1 | Operation Model + spike 结论 | ⚠️ | ❌ |
| chat 指令落地语义：何时产生 editor 操作、何时触发重生成 | 2027 架构 | P1 | 同上 | ⚠️ | ❌（需 CHAT_ARCHITECTURE 文档仲裁） |
| MCP server（被外部 agent 调用） | 矩阵 §I P2；MCP 已成行业标准（Linux 基金会 AAIF，97M 月下载） | P2 | Agent Interface 稳定 + API 幂等/结构化错误改造 | ⚠️ | ❌ |

## 4. Editor GUI（Operation Model 的前端之一）

> 薄化：不追加 L3 能力（多轨/B-roll/转场明确不做），投资只投向与 Operation Model 的接线。

| 需求 | 来源 | 优先级 | 依赖 | Agent 就绪度 | 状态 |
|---|---|---|---|---|---|
| transcript 编辑 / 单轨 trim / Remotion 预览 | — | — | — | ✅ | ✅ 已落地 |
| undo 栈（前端接 Operation Model） | VIDEO_EDITOR.md 已承诺 | P1 | Operation Model | — | ❌ |
| 字幕翻译 + 校对视图（side-by-side） | 矩阵 §G | P1 | 多语言输出（已有） | ✅ | ❌ |
| XML / EDL 交接 spec（→ CapCut/Premiere） | ADR-016 | P2 | clip-spec 稳定 | — | ❌ |

## 5. Distribution ⭐ 权重上调

> 2027 透镜下与 pipeline 平级：审核队列是 HITL 的正确形态；发布数据回流是传播潜力分唯一的真实校准源——现在不定表结构，闭环永远断着。

| 需求 | 来源 | 优先级 | 依赖 | Agent 就绪度 | 状态 |
|---|---|---|---|---|---|
| Publication / ChannelAccount 数据模型（含回流分析字段预留） | 矩阵 §H；2027 架构 | **P1（表结构先行，功能可后做）** | 无 | — 纯工程 | ❌（无任何代码） |
| 审核队列（机构合规刚需，默认人工确认的状态机） | 矩阵 §H | P1 | 数据模型 | — | ❌ |
| LinkedIn OAuth + 直发 | 矩阵 §H | P1 | 数据模型 | — | ❌ |
| 定时发布（worker 第四认领源，复用 SKIP LOCKED） | 矩阵 §H | P1 | 数据模型 + 队列（已有） | — | ❌ |
| 发布数据回流 → 校准传播潜力分 | 2027 架构 | P2 | Publication 回流字段 + 打分持久化 | ✅ | ❌ |
| newsletter ESP 集成（owned channel） | 矩阵 §H | P2 | 数据模型 | — | ❌ |
| 源 → 目的地自动规则 | 矩阵 §H | P2 | LinkedIn 直发跑通 | — | ❌ |

## 6. Memory / Context（Speaker + Brand + 术语表）

> 2027 最硬的资产：三个"极高"价值改造项全在这层，且横切所有模块（director 注入 / chat 上下文 / editor 品牌皮肤 / 分发调性）。LinkedIn 对"通用 AI 腔"约 94% 检测率 + 30% 触达惩罚，Voice DNA 已成 B2B 必需品——我们的 persona 恰好是正确答案，应升级为对外卖点。

| 需求 | 来源 | 优先级 | 依赖 | Agent 就绪度 | 状态 |
|---|---|---|---|---|---|
| Speaker persona（风格记忆） | ADR-021 | — | — | ✅ | ✅ 已落地 |
| Brand template | — | — | — | ✅ | ✅ 已落地 |
| 术语表 / glossary（机构级翻译质量） | 矩阵 §G "极高" | P1 | persona 注入链路（已有） | ✅ | ❌（仅一条 i18n 占位文案） |
| 多语言文案质量（Voice DNA 跨语言保真） | 矩阵 §G "极高"；2026 B2B 趋势 | P1 | 术语表 | ✅ | ❌ |
| persona 显化于 UI（让用户看到/编辑自己的 Voice DNA） | 2027 架构 | P2 | — | ✅ | ❌ |

## 7. 合规底座 ⚖️ 法律时限

> EU AI Act Article 50：AI 生成内容须机器可读标识 + 披露，**2026-08-02 生效**（已上市系统宽限至 2026-12-02），罚则最高 €35M / 全球营收 7%。我们是面向欧洲机构的产品，这不是加分项是入场券；七家竞品全部 structural 缺席，同时是差异化。

| 需求 | 来源 | 优先级 | 依赖 | Agent 就绪度 | 状态 |
|---|---|---|---|---|---|
| AI 内容机器可读标识（C2PA / 元数据）写入渲染产物 | EU AI Act Art.50 | **P0（法律时限）** | clip-spec 扩展 + render 服务（已有）；先调研 C2PA 实现成本 | — | ❌ |
| 披露元数据随分发层携带（发布到 LinkedIn 等平台时声明 AI 生成） | EU AI Act Art.50；2027 架构 | **P0** | Distribution 数据模型 | — | ❌ |
| 界面披露提示（导出/发布时的 AI 内容声明） | EU AI Act Art.50 | P0 | 无 | — | ❌ |
| 数据生命周期文档（retention / 删除权 / 导出）——机构采购必问 | GDPR | P1 | 无 | — | ❌ |
| EU 数据驻留（存储 key 布局 + 队列区域路由） | 矩阵 §I | P2 | 现存储按 `{user_id}/` 前缀，需评估改造面 | — | ❌ |
| 模型 EU-hosted 选项（Mistral 等） | 2027 架构 | P2 | provider 抽象（§3） | ⚠️ | ❌ |

## 8. 平台与计费

> "可预期 > 便宜"是矩阵定的信任差异化；不透明 credit 计费正遭全行业反弹。

| 需求 | 来源 | 优先级 | 依赖 | Agent 就绪度 | 状态 |
|---|---|---|---|---|---|
| WorkflowRun 成本列 + 每次 stage 计量 | 矩阵 §I | **P0**（同 §1 计量钩子，同一件事） | 无 | — | ❌ |
| 成本预估展示（生成前） | 矩阵 §I | P1 | 成本计量数据积累 | — | ❌ |
| 失败不扣费语义 | 矩阵 §I | P1 | 成本计量 | — | ❌ |
| 团队工作区 / 多 Speaker 画像 | 矩阵 §I | P2 | auth（已有）| — | ❌ |

---

## 跨模块依赖图

```
成本计量钩子 (P0) ────────────────────────────► 成本预估 / 失败不扣费 (P1)
传播分持久化 (P0) ──► Distribution 回流 (P2) ──► persona 校准打分 (P1)

Operation Model (P1 地基) ──┬──► Editor undo 栈 (P1)
                            ├──► chat 意图→操作 dispatch (P1)
                            └──► Consistency Reviser (P2)

M3 tool-calling spike (P1) ──► Operation schema ──► Agent Interface ──► MCP (P2)
provider 抽象 (P1, 需修订 ADR-003) ──► EU-hosted 模型选项 (P2)

Distribution 数据模型 (P1) ──► 审核队列 / LinkedIn 直发 / 定时发布 (P1)
                           └──► 披露元数据随分发携带 (P0, 合规)

clip-spec 扩展 (P0 合规标识) ──► render 服务打标 ──► XML/EDL 交接 (P2)
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
