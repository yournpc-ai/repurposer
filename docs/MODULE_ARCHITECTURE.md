# Module Architecture — 模块划分与边界契约

> Status: Active（2026-07-20 建立，post-MVP 模块架构锚点）
> 排期见 [ROADMAP.md](./ROADMAP.md)（本文多处被其引用为"2027 架构"）；现状系统架构见 [ARCHITECTURE.md](./ARCHITECTURE.md)；决策留痕见 [DECISIONS.md](./DECISIONS.md)。

本文回答三个问题：**有哪些模块、每张表归谁、模块之间怎么通信**。它是方向性契约——部分模块（Operation Model、Agent Interface、Distribution）尚未实现，但其边界现在就定死，避免演进时跨域纠缠。

## 1. 设计原则（2027 透镜）

1. **主交互面是 agent，GUI 是 client 之一**——chat、MCP、编辑器都只是 Operation Model / Pipeline 的前端。
2. **Editor 薄化**——真正要建的是 Operation Model（可检查、可撤销的操作日志），不是编辑器本身。手动编辑占比即使萎缩，投资也沉淀在操作层。
3. **Pipeline 是成本中心不是壁垒**——保持现有 4-layer 编排，不追加差异化投入；差异化在 Memory、Distribution、合规。
4. **Distribution 与 Pipeline 平级**——审核队列是 HITL 的正确形态；发布数据回流是传播潜力分唯一的真实校准源。
5. **合规是底座不是功能**——EU AI Act Art.50（2026-08-02 生效）的内容标识写进 clip-spec 与分发层，横切所有模块。

## 2. 六层模块图

```
┌─────────────────────────────────────────────────────────────┐
│ Agent Interface（chat 升级版 + MCP，📋 未实现）               │  ← 人话 / agent 话统一入口
├─────────────────────────────────────────────────────────────┤
│ Operation Model（操作日志层，📋 未实现）                      │  ← 可检查/可撤销的操作；
│                                                             │    editor GUI / chat / MCP 共用
├──────────────────┬───────────────────────┬──────────────────┤
│ Pipeline         │ Editor GUI            │ Distribution     │
│ （生成管线，      │ （Operation Model     │ （📋 未实现：     │
│  ✅ 已落地）      │  的一个前端，✅ 主体   │  审核队列/LinkedIn│
│                  │  已落地）              │  直发/定时发布）   │
├──────────────────┴───────────────────────┴──────────────────┤
│ Memory / Context（Speaker persona + Brand + 术语表，✅ 主体   │  ← 横切：director 注入 /
│  已落地，术语表 📋）                                         │    chat 上下文 / 品牌皮肤
├─────────────────────────────────────────────────────────────┤
│ 合规与计费底座（AI 内容标识 / 成本计量 / EU 驻留，📋）          │  ← 横切所有模块
└─────────────────────────────────────────────────────────────┘
```

### 2.1 闭环流转图（工作流闭环 = 全模块指导方针）

六层图回答"有哪些模块"，本图回答**数据与价值怎么流转**——闭环是全模块的指导方针（STRATEGY §3 牌 1）：每个模块都要回答"你在闭环的哪一段、你消灭了哪条断头路"。✅ = 已通，📋 = 未建。

```
 上传/链接        预处理          生成              精修              渲染           分发
┌─────────┐   ┌──────────┐   ┌───────────┐   ┌────────────┐   ┌──────────┐   ┌───────────┐
│ 本地文件  │   │ Asset     │   │ 4-layer   │   │ Edit/Chat/  │   │ Remotion  │   │ 审核队列   │
│ 上传 ✅   │──►│ 状态机     │──►│ 生成编排    │──►│ Regenerate │──►│ render_   │──►│ →LinkedIn │
│ Zoom/RSS │   │ ✅        │   │ WorkflowRun│   │ 精修三角     │   │ spec ✅   │   │ /newsletter│
│ 📋 P1   │   └──────────┘   │ ✅        │   │ (Operation  │   └──────────┘   │ 📋 P1     │
└─────────┘                  └───────────┘   │  Model 📋)  │                 └─────┬─────┘
                                              └──────┬─────┘                       │
      ┌──────────────────────────────────────────────┴─────────────────────────────┘
      │ 回流两条边（闭环的关键，均 📋）：
      │  ① 精修痕迹（删了哪条、改了哪句）→ Operation Model → 校准打分 / persona（P1）
      │  ② 发布数据（哪条被打开/互动）  → Publication 回流字段 → 校准传播潜力分（P2）
      ▼
┌────────────────────────────────────────────────────────┐
│ Memory / Context：persona · Brand · 术语表               │
│ 正向边：注入 director / chat / 分发调性（✅ 单向，规则 4）   │
└────────────────────────────────────────────────────────┘
```

每条边的载体（"流转"落在哪些表/队列/服务上）：

| 边 | 载体 | 状态 |
|---|---|---|
| 上传 → 预处理 | `assets` 行 + worker `SKIP LOCKED` 认领 | ✅ |
| 预处理 → 生成 | `workflow_runs` 行（deferred claim：素材未就绪不认领） | ✅ |
| 生成计划图 | （📋）`plan_nodes`——计划作为一等对象，节点级血统/成本/重跑（ADR-028） | 📋 P1 地基 |
| 生成 → 精修 | `clips.render_spec` / `derivatives`（clip-spec 契约） | ✅ |
| 精修 → 渲染 | `clips.render_status=PENDING`（worker 第三认领源） | ✅ |
| 精修操作记录 | （📋）`operations` 表——Edit/Chat/MCP 三前端共用 | 📋 P1 地基 |
| 分发 | （📋）`publications` 状态机 + `channel_accounts` | 📋 P1 |
| 发布数据回流 | （📋）Publication 回流字段 → 传播潜力分校准 | 📋 P2 |
| Memory 注入 | persona block / brand block（消费者各自拉取） | ✅ |
| 校准回流 | （📋）精修痕迹 + 发布数据 → persona agent | 📋 P1/P2 |

**闭环现状：断在两条回流边上。** 正向链路（上传 → 预处理 → 生成 → 精修 → 渲染 → 导出）已全通；回流（精修痕迹、发布数据）一条都不存在——这就是 ROADMAP 把 Operation Model 标为"地基"、把 Distribution 数据模型标为"权重上调"的原因。回流不通，传播潜力分和 persona 永远没有真实校准源，三资产哲学（STRATEGY §2）就停在营销层。

## 3. 模块职责与现状映射

| 模块 | 职责 | 现状代码 | 状态 |
|---|---|---|---|
| **Pipeline** | 素材摄入（上传/未来的链接抓取）、ASR/提取预处理、4-layer 生成编排、RunPlan 计划图（📋 ADR-028）、渲染触发 | `services/asset_processing.py`、`services/generation.py`、`app/agents/`、`services/rendering.py` | ✅ 已落地 |
| **Operation Model** | 操作日志（每个操作 = clip-spec diff）、undo 语义、agent 可调用的操作 schema（原子/幂等/可检查/可撤销） | 无（hidden 标记是雏形：`packages/clip/src/types.ts`） | 📋 ROADMAP §2 |
| **Agent Interface** | chat 主交互、意图→操作/run dispatch、tool calling、MCP server | `services/chat.py`（规则意图→派生 WorkflowRun）、`agents/intent.py`（LLM 意图，未接入 chat） | 🚧 雏形 |
| **Editor GUI** | transcript 编辑、单轨 trim、Remotion 预览——Operation Model 的前端之一 | `apps/web/src/routes/projects.$id.clips.$clipId.tsx` | ✅ 主体落地 |
| **Distribution** | ChannelAccount（OAuth token 生命周期）、Publication（状态机/幂等/限流重试）、审核队列、定时发布、数据回流 | 无 | 📋 ROADMAP §5；设计见 `DISTRIBUTION.md` |
| **Memory / Context** | Speaker persona、Brand template、术语表（📋）；向 director prompt / chat 上下文 / 分发调性注入 | `agents/persona.py`、`services/brand.py`、`routers/brand_templates.py` | ✅ 主体落地 |
| **合规与计费底座** | AI 内容机器可读标识（C2PA/元数据）、披露、WorkflowRun 成本计量、EU 数据驻留（P2） | 无（`clients/minimax.py` 丢弃 usage 字段） | 📋 ROADMAP §7/§8 |

**精修三角（Editor / Chat / Regenerate 的分工，自 MVP_SPEC §5.7 迁入）**：每个产物卡片提供三种精修路径——**Edit**（精确控制：剪到具体时间点、调字幕样式，仅 Clip，进 editor 页）、**Chat**（模糊指令："再短一点"、"换成德语"、"更正式一点"，asset-scoped Modal）、**Regenerate**（同参数生成新变体）。分工判据：指令能用参数精确表达 → Edit；只能用语言描述 → Chat；想要"再来一版" → Regenerate。这条分工是 Agent Interface 意图 dispatch 的设计基线（CHAT_ARCHITECTURE 待写）。

## 4. 表归属契约

每张表只有一个 owner 模块；其他模块**只读或经 owner 的服务函数写**。新表必须先在此登记归属。

| 表 | Owner | 其他模块的访问规则 |
|---|---|---|
| `users` | （平台层，暂不属于任何模块） | 只读 |
| `assets` | Pipeline | 其他模块只读；处理状态只由 worker 的 asset_processing 写 |
| `projects` | Pipeline | `content_plan` 只由 generation 写；各模块只读 |
| `workflow_runs` | Pipeline | **只允许两处创建**：Pipeline 生成入口、Agent Interface 的 dispatch；状态只由 worker 写。成本计量列（📋）由 LLM 接口层（ADR-025）写 |
| `clips` | **共享聚合**（见下） | 创建 + `render_status`/`video_url` 归 Pipeline；内容字段（segments/hidden/trim，经 `render_spec`）归 Operation Model；契约 = clip-spec |
| `derivatives` | Pipeline | 内容修订经 reviser 流程（未来归 Operation Model） |
| `chat_sessions` / `messages` | Agent Interface | Pipeline 只读（run 关联展示） |
| `speakers` | Memory | 各模块注入用只读；persona 只由 persona agent 写 |
| `brand_templates` | Memory | 渲染时经 Pipeline 烘焙进 clip-spec，渲染服务不直读 |
| `music` | Pipeline（渲染资产库） | 生成/挑选经 music 服务；editor 只读选择 |
| （📋）plan_nodes | Pipeline | 节点状态只由 orchestrator/worker 写；Clip/Derivative 的 `plan_node_id` 为只读血统引用；`spec` 载荷 JSONB（ADR-028） |
| （📋）operations | Operation Model | editor GUI / chat / MCP 三个前端写入；worker 消费 |
| （📋）publications / channel_accounts / publication_events | Distribution | 状态机只由 Distribution 服务迁移；事件日志只追加；回流字段预留给分析 |

**Clip 共享聚合的细则**：`clips` 行有三个写者——Pipeline（创建、渲染状态）、Operation Model（内容编辑 = render_spec diff）、worker（渲染产物回写）。规则：任何写者只碰自己的字段子集；内容字段的修改必须能产生一条 operation 记录（Operation Model 落地后强制执行）。

## 5. 跨模块通信规则

1. **耗时任务一律走队列**：模块间触发重活（重生成/渲染/未来的发布）= 写一行 pending 记录（WorkflowRun / Clip.render_status / 未来的 Publication），由 worker 的 `FOR UPDATE SKIP LOCKED` 认领。**禁止**跨模块直接调 service 函数执行重活，禁止 FastAPI BackgroundTasks。
2. **读路径走 API 服务层**：模块间同步读数据经服务函数/路由，不跨域直写对方的表。
3. **clip-spec 是 Pipeline ↔ 渲染的唯一契约**（ADR-016）：渲染服务不读 DB；Operation Model 的编辑也表达为 clip-spec diff，不引入第二个契约。
4. **Memory 注入是单向的**：Memory 模块只暴露"注入载荷"（persona block / brand block / glossary），不知道谁在消费；消费者（director / chat / distribution）各自拉取。
5. **合规与计费是横切切面**：LLM 调用统一经 ADR-025 接口层（计量落 `workflow_runs`）；内容标识在 clip-spec 扩展字段与 Distribution 披露元数据两处落地，不分散到各模块自行实现。

## 6. 演进规则

- **新功能先问归属**：归属不清时按"谁写这张表"判定；都不写表的功能（纯 UI）归最近的前端模块。
- **新模块准入**：必须有独立的表归属或独立的队列认领源，否则只是现有模块的职责扩充。
- **命名注意**：竞品文档中 "pipeline" 也指 Opus 范式（见 DECISION_MATRIX 范式短名）；内部模块语境下 Pipeline = 我们的生成管线，引用竞品时写 `Pipeline 范式`。
- **本契约的变更 = ADR**：表归属调整、新横切切面、认领源增减都要写 ADR 并更新本文。
