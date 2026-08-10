# Module Architecture — 模块划分与边界契约

> Status: Active（**现状系统架构的唯一事实源**）
> 排期见 [PROGRESS.md](./PROGRESS.md)；决策见 [DECISIONS.md](./DECISIONS.md)（现行决策集）。

本文回答三个问题：**有哪些模块、每张表归谁、模块之间怎么通信**。它是方向性契约——部分模块（Operation Model、Agent Interface、Distribution）尚未实现，但其边界现在就定死，避免演进时跨域纠缠。

## 1. 设计原则（2027 透镜）

1. **主交互面是 agent，GUI 是 client 之一**——chat、MCP、编辑器都只是 Operation Model / Pipeline 的前端。
2. **Editor 薄化**——真正要建的是 Operation Model（可检查、可撤销的操作日志），不是编辑器本身。手动编辑占比即使萎缩，投资也沉淀在操作层。
3. **Pipeline 是成本中心不是壁垒**——保持现有编排（NodeBase 图内核，AGENT_ARCHITECTURE），不追加差异化投入；差异化在 Memory、Distribution、合规。
4. **Distribution 与 Pipeline 平级**——核心是发布动作本身（直发）：正向链路最后一座手动桥。审核队列 / 定时 / 数据回流为边缘功能（P2）；发布数据回流若做，是首发推荐分的外部校准源（内部校准源 = 用户选用行为）。
5. **合规是底座不是功能**——EU AI Act Art.50（2026-08-02 生效）的内容标识写进 clip-spec 与分发层，横切所有模块。

## 2. 六层模块图

```
┌────────────────────────── 前端面 ──────────────────────────┐
│ composer ✅ │ Editor GUI ✅ │ chat ✅ │ 步骤清单 ✅          │
│ FlowView 图面（配方流程图 ✅ / run 进度图 🚧 / 血缘板 📋spike，ADR-036）│ MCP 📋P2 │
└──────────────────────────────┬─────────────────────────────┘
                               ▼ 意图
┌──────────────── Agent Interface（chat 升级版 + MCP）────────┐
│ dispatch 三类目标：editor 操作 / 整体重生成 / plan 级          │
│ 表：conversations/messages ✅                               │
└───────┬──────────────────────────────┬─────────────────────┘
        ▼                              ▼
┌───────────────────┐   ┌─────────── Pipeline ✅（RunPlan 内核）────────┐
│ Operation Model ✅ │   │ 摄入/预处理（ASR）✅ │ 导演/agent 花名册 ✅    │
│ （操作日志层，      │   │ ┌── RunPlan 内核（施工图，ADR-028 ✅）───┐│
│  三前端共用）      │   │ │ workflow_steps：导演两步/技能节点/质检节点   ││
└─────────┬─────────┘   │ │ orchestrator 走图 · worker 认领节点       ││
          │             │ │ 链：clip 链 ✅/文案链 ✅/虚拟链 📋A-029   ││
          │             │ └───────────────────────────────────────────┘│
          │             └──────────────────┬────────────────────────────┘
          ▼ clip-spec diff                 ▼ clip-spec（唯一契约 ADR-016）
        outputs ◄────────────── Remotion 渲染服务 ✅（黑盒）
       （统一产物表 ✅，ADR-030）

┌──────────────── Distribution 📋（与 Pipeline 平级，零变化）──────┐
│ channel_accounts / publications 状态机 / 缝 = 产物表单 FK         │
├──────────────────────────────────────────────────────────────────┤
│ Memory / Context ✅（persona（含皮肤块 brand，ADR-038）+ 术语表 📋；📋视觉身份+授权） │
├──────────────────────────────────────────────────────────────────┤
│ 合规与计费底座 📋（分类器读产物 provenance→C2PA / usage→           │
│ workflow_steps.cost / EU 驻留）                                       │
└──────────────────────────────────────────────────────────────────┘
```

### 2.1 闭环流转图（工作流闭环 = 全模块指导方针）

六层图回答"有哪些模块"，本图回答**数据与价值怎么流转**——闭环是全模块的指导方针（STRATEGY §3 牌 1）：每个模块都要回答"你在闭环的哪一段、你消灭了哪条断头路"。✅ = 已通，📋 = 未建。

```
 上传/链接        预处理          生成              精修              渲染           分发
┌─────────┐   ┌──────────┐   ┌───────────┐   ┌────────────┐   ┌──────────┐   ┌───────────┐
│ 本地文件  │   │ Asset     │   │ DAG 生成   │   │ Edit/Chat/  │   │ Remotion  │   │ 审核队列   │
│ 上传 ✅   │──►│ 状态机     │──►│ 编排        │──►│ Regenerate │──►│ render_   │──►│ →LinkedIn │
│ Zoom/RSS │   │ ✅        │   │ WorkflowRun│   │ 精修三角     │   │ spec ✅   │   │ /newsletter│
│ 📋 P1   │   └──────────┘   │ ✅        │   │ (Operation  │   └──────────┘   │ 📋 P1     │
└─────────┘                  └───────────┘   │  Model ✅)  │                 └─────┬─────┘
                                              └──────┬─────┘                       │
      ┌──────────────────────────────────────────────┴─────────────────────────────┘
      │ 回流两条边（闭环的关键，均 📋）：
      │  ① 精修痕迹（删了哪条、改了哪句）→ Operation Model → 校准打分 / persona（P1）
      │  ② 发布数据（哪条被打开/互动）  → Publication 回流字段 → 校准首发推荐分（P2）
      ▼
┌────────────────────────────────────────────────────────┐
│ Memory / Context：persona（风格/策略/声音/皮肤）· 术语表    │
│ 正向边：注入 director / chat / 分发调性（✅ 单向，规则 4）   │
└────────────────────────────────────────────────────────┘
```

每条边的载体（"流转"落在哪些表/队列/服务上）：

| 边 | 载体 | 状态 |
|---|---|---|
| 上传 → 预处理 | `assets` 行 + worker `SKIP LOCKED` 认领 | ✅ |
| 预处理 → 生成 | `workflow_runs` 行（deferred claim：素材未就绪不认领） | ✅ |
| 生成计划图 | `workflow_steps`——计划作为一等对象，节点级血统/成本/重跑（ADR-028） | ✅ |
| 生成 → 精修 | `outputs.render_spec` / `outputs.payload`（clip-spec 契约） | ✅ |
| 精修 → 渲染 | `outputs.render_status=PENDING`（worker 认领源） | ✅ |
| 精修操作记录 | `operations` 表——Edit/Chat 已写入（MCP 座位） | ✅（ADR-032） |
| 分发 | （📋）`publications` 状态机 + `channel_accounts` | 📋 P1 |
| 发布数据回流 | （📋）Publication 回流字段 → 首发推荐分校准 | 📋 P2 |
| Memory 注入 | persona block / brand block（消费者各自拉取） | ✅ |
| 校准回流 | （📋）精修痕迹 + 发布数据 → persona agent | 📋 P1/P2 |

**闭环现状：断在发布动作与两条回流边上。** 正向链路（上传 → 预处理 → 生成 → 精修 → 渲染 → 导出）已全通，但"导出 → 平台"仍是手动下载再上传——这是 Distribution 直发标 P1 的理由；回流（精修痕迹、发布数据）一条都不存在——这是 Operation Model 标为"地基"的理由（编辑痕迹属内部校准源，不依赖 Distribution）。发布数据回流属边缘功能（P2）：不通则首发推荐分和 persona 缺外部校准源，但内部校准（选用行为 + 编辑痕迹）先行。

### 2.2 数据架构图（ADR-028/030 后）

```
users（平台层）

Memory/Context：personas（含皮肤块 brand / 声纹块 voice，ADR-038；📋视觉身份/授权）

Pipeline：
assets ──► workflow_runs ──► workflow_steps ✅ ──► outputs ✅（统一产物，ADR-030）
（上传/ASR）  （run 容器）     （施工图：计划+账簿）     type=clip 带 source_ref+render_spec
music（AI 音乐库）                             payload/files/score/publishing/provenance

Agent Interface：conversations ──► messages
Operation Model 📋：operations（clip-spec diff；目标=outputs[type=clip]）
Distribution 📋：channel_accounts ──► publications ──► publication_events（只追加）
                                      output_id 单 FK · due_at · metrics · ai_disclosure

横切数据流：
计量：LLM usage（ADR-025）→ workflow_steps.cost ──聚合──► workflow_runs
合规：产物 provenance → 分类器 → C2PA（渲染嵌入）+ publications.ai_disclosure
回流：① operations（编辑痕迹）② publications.metrics（发布数据）→ 校准打分/persona
```

读法：模块图回答"谁干活"，本图回答"记在哪"——每张表一个 owner（§4），血统经 `workflow_step_id` 汇聚到 workflow_steps（DAG 内核是数据架构的中心）。

## 3. 模块职责与现状映射

| 模块 | 职责 | 现状代码 | 状态 |
|---|---|---|---|
| **Pipeline** | 素材摄入（上传/未来的链接抓取）、ASR/提取预处理、生成编排（导演两步 + 技能节点）、RunPlan 计划图（ADR-028 ✅）、渲染触发 | `pipeline/asset_processing.py`、`pipeline/orchestrator.py`、`pipeline/node_runners.py`（内部节点）、`app/skills/`（技能包）、`app/agents/`（花名册+harness 漏斗）、`pipeline/rendering.py`；agent 架构事实源 = AGENT_ARCHITECTURE（ADR-039 四层工程地图） | ✅ 已落地 |
| **Operation Model** | 操作日志（每个操作 = clip-spec diff）、undo 语义、agent 可调用的操作 schema（原子/幂等/可检查/可撤销） | `operations/`（registry/service/routes；ADR-032 快照式 undo） | ✅ 地基落地（2026-07-26：editor/chat 两前端已写入；校准消费端仍 📋） |
| **Agent Interface** | chat 主交互、意图→操作/run dispatch、tool calling、MCP server | `chat/service.py`（plan path + 四态 dispatch：任务书构建/修订/确认、task_list→create_run / edit_ops→operations）、`chat/intent.py`（PlanAgent + ChatIntentAgent，op 词汇注入）、`components/chat/`（ChatModal/RunCard/OpsCard/MentionPicker）、`skills/__init__.py`（SKILL_REGISTRY 裁决） | 🚧 v2 落地（chat UI + edit ops + translate/dub skills；plan 级节点重跑仍 ❌，MCP 📋） |
| **Editor GUI** | transcript 编辑、单轨 trim、Remotion 预览——Operation Model 的前端之一 | `apps/web/src/routes/projects.$id.clips.$clipId.tsx` | ✅ 主体落地 |
| **Distribution** | ChannelAccount（OAuth token 生命周期）、Publication（状态机/幂等/限流重试）、审核队列、定时发布、数据回流 | `distribution/`（core/channels/publishing/adapters + routes） | 🚧 OAuth/直发骨架已落地（PROGRESS 第八周联调） |
| **Memory / Context** | Persona（人设：风格 / 策略 / 皮肤块 `brand` / 声纹块 `voice`）、术语表（📋）；向 director prompt / chat 上下文 / 分发调性注入 | `agents/roster.py`（persona 声明）、`memory/brand.py`（人设皮肤 → clip-spec 烘焙，模块名不动）、`memory/routes.py` | ✅ 主体落地 |
| **合规与计费底座** | AI 内容机器可读标识（C2PA/元数据）、披露、逐节点成本计量、EU 数据驻留（P2） | `metering.py`（usage → `workflow_steps.cost`，ADR-025）、`clients/minimax.py`（usage 捕获点） | 🚧 计量 ✅（Phase 1）；C2PA/披露 📋 PROGRESS 第八周；EU 驻留 📋 需求池 |

**精修三角（Editor / Chat / Regenerate 的分工，自 MVP_SPEC §5.7 迁入）**：每个产物卡片提供三种精修路径——**Edit**（精确控制：剪到具体时间点、调字幕样式，仅 Clip，进 editor 页）、**Chat**（模糊指令："再短一点"、"换成德语"、"更正式一点"，asset-scoped Modal）、**Regenerate**（同参数生成新变体）。分工判据：指令能用参数精确表达 → Edit；只能用语言描述 → Chat；想要"再来一版" → Regenerate。这条分工是 Agent Interface 意图 dispatch 的设计基线（CHAT_ARCHITECTURE 待写）。

## 4. 表归属契约

每张表只有一个 owner 模块；其他模块**只读或经 owner 的服务函数写**。新表必须先在此登记归属。

| 表 | Owner | 其他模块的访问规则 |
|---|---|---|
| `users` | （平台层，暂不属于任何模块） | 只读 |
| `assets` | Pipeline | 其他模块只读；处理状态只由 worker 的 asset_processing 写 |
| `projects` | Pipeline | 各模块只读 |
| `workflow_runs` | Pipeline | **创建收口于 `orchestrator.create_run`**（/generate、chat dispatch 全部经它，全库无旁路）；状态只由 orchestrator/worker 写。run 级成本 = `workflow_steps.cost` 聚合（API 序列化时计算，不落列） |
| `outputs` | Pipeline | 创建 + `render_status`/`files` 归 Pipeline；内容字段（`payload`/`render_spec`/`publishing`）经 `/outputs` API 编辑，Operation Model 落地后归入其写集；payload 三规则（ADR-030）；`workflow_step_id` 为只读血统；内部类型（`content_plan`）经 `visible_outputs()` 统一过滤 |
| `conversations` / `messages` | Agent Interface | Pipeline 只读（run 关联展示） |
| `personas` | Memory | 各模块注入用只读；内容只由 persona agent 写。终态 schema（ADR-038 第二刀）：身份卡 + 风格六件 flat + 策略三件（audience/guidelines/cta）+ `voice` JSONB（声纹块，NULL=Auto）+ `brand` JSONB（皮肤块，NULL=系统默认皮肤）+ `learned_from` JSONB + `calibrated_at` + `auto_created_at`（可空时间戳替代 is_default；默认解析链 = run.context pin > 项目挂载 > auto_created_at 非空 > 最早创建） |
| `music` | Pipeline（渲染资产库） | 生成/挑选经 music 服务；editor 只读选择 |
| `workflow_steps` | Pipeline | 节点状态只由 orchestrator/worker 写；outputs 的 `workflow_step_id` 为只读血统引用；`spec` 载荷 JSONB（ADR-028）；`cost` 只由 metering（ADR-025）原子累加 |
| operations | Operation Model（✅ 2026-07-26） | editor GUI / chat 两前端写入（MCP 座位）；append-only，`undone_at` 唯一可写字段 |
| publications / channel_accounts | Distribution | 状态机只由 Distribution 服务迁移；回流字段预留给分析（2026-07-24 落地，📋 移除；publication_events 仍 P2） |
| `notifications` | （平台层，暂不属于任何模块） | 事件源模块经 `platform/notifications.create_notification` 写（当前唯一写者 = Distribution `_transition` 终态钩子）；读/已读收口于 `/notifications` 路由 |

**outputs 共享聚合的细则**：`outputs` 行有三个写者——Pipeline（创建、渲染状态）、Operation Model（内容编辑 = payload/render_spec diff）、worker（渲染产物回写 `files.video`/`files.srt`）。规则：任何写者只碰自己的字段子集；内容字段的修改必须能产生一条 operation 记录（Operation Model 落地后强制执行）。

### 4.1 行业词汇对照（Mastra / Agno / OpenAI ↔ 本系统）

对照唯一事实源——评估外部框架、写新文档、评审命名时以此为准，不另起炉灶。

| 行业通用词 | 本系统对应 | 说明 |
|---|---|---|
| Agents（LLM 决策单元） | `app/agents/`（一个 Agent 类 + 声明实例，N-29/N-30） | 与 Mastra/Agno 同词 |
| Tools（确定性执行） | `app/tools/`（机械） | 同名同物；禁 import agents/LLM client |
| Skills（组合能力） | `app/skills/` 技能包 + SKILL_REGISTRY | = Mastra Skills 的登记处；技能一词一义（N-29），用户语言同词 |
| Agent Harness（调用面脚手架） | `agents/base.py` 漏斗 + contexts 装配 + prompts | 装配/校验/修复一轮/计量/声明兜底；剧本 harness 是 test harness（N-33 限定） |
| Workflows（编排图+执行） | RunPlan 内核（orchestrator + workflow_steps + worker 认领） | Workflow State=run 状态机；Suspend/Resume=step `waiting` 座位；Snapshots=spec/context；HITL=variant_pick gate（📋） |
| workflow run（执行实例） | `workflow_runs` 表 | 行业标准全名（每 run 自带其编译出的 workflow=步骤图） |
| Agent Runtime | `app/worker.py` | 执行进程 |
| Memory | `memory/`（personas） | persona/brand block 单向注入 |
| Evals（Scorers/Gates/Verdicts） | 📋 Phase 3 verify 节点 + variant_pick gate | verify=节点 / eval=活动，与 Mastra 兼容 |
| Threads / Conversations | `conversations` + `messages` | OpenAI Conversations API 同款 |
| Agent Observability | metering（workflow_steps.cost）+ structlog + 📋 METRICS.md | 横切不开包（§5） |
| Channels | `distribution/` | 直发渠道 |
| Guardrails | 📋 合规底座（ADR-026 分类器/C2PA） | PROGRESS 第八周 |

反对照：`pipeline/` 模块 ≠ Mastra Workflows（我们的 Pipeline = 摄入+ASR+编排+渲染，大于 Workflows，不改名）；`chat/` ≈ Agno Interfaces。

## 5. 跨模块通信规则

1. **耗时任务一律走队列**：模块间触发重活（重生成/渲染/未来的发布）= 写一行 pending 记录（WorkflowRun 经 `orchestrator.create_run` / `outputs.render_status` / 未来的 Publication），由 worker 的 `FOR UPDATE SKIP LOCKED` 认领。**禁止**跨模块直接调 service 函数执行重活，禁止 FastAPI BackgroundTasks。
2. **读路径走 API 服务层**：模块间同步读数据经服务函数/路由，不跨域直写对方的表。
3. **clip-spec 是 Pipeline ↔ 渲染的唯一契约**（ADR-016）：渲染服务不读 DB；Operation Model 的编辑也表达为 clip-spec diff，不引入第二个契约。
4. **Memory 注入是单向的**：Memory 模块只暴露"注入载荷"（persona block / brand block / glossary），不知道谁在消费；消费者（director / chat / distribution）各自拉取。
5. **合规与计费是横切切面**：LLM 调用统一经 ADR-025 接口层（计量落 `workflow_steps.cost`）；内容标识在 clip-spec 扩展字段与 Distribution 披露元数据两处落地，不分散到各模块自行实现。
6. **内核重建接缝稳定**：模块内核可重建，只要表归属与通信规则不变，其他模块零感知——2026-07-22 实证：Pipeline 的 RunPlan（DAG）化后，Distribution / Memory / Editor GUI / Operation Model 全部零改动（缝 = 产物表与 clip-spec）。新内核设计必须守住既有接缝，不得以内核升级为借口移动缝。

## 6. 演进规则

- **新功能先问归属**：归属不清时按"谁写这张表"判定；都不写表的功能（纯 UI）归最近的前端模块。
- **新模块准入**：必须有独立的表归属或独立的队列认领源，否则只是现有模块的职责扩充。
- **命名注意**：竞品文档中 "pipeline" 也指 Opus 范式（见 DECISION_MATRIX 范式短名）；内部模块语境下 Pipeline = 我们的生成管线，引用竞品时写 `Pipeline 范式`。
- **本契约的变更 = ADR**：表归属调整、新横切切面、认领源增减都要写 ADR 并更新本文。

## 7. 代码地图与运行约定（自 ARCHITECTURE.md 并入，2026-07-31）

### 7.1 代码地图

```
apps/api/
├── app/
│   ├── main.py / config.py / worker.py   # FastAPI 入口 / 配置 / 独立 worker 进程
│   ├── chat/            # Agent Interface：routes / service / intent
│   ├── pipeline/        # Pipeline（RunPlan 内核）
│   │   ├── routes/      # projects / assets / outputs / runs / music 端点
│   │   ├── orchestrator.py        # RunPlan 物化/走图（create_run = WorkflowRun 唯一出生地）
│   │   ├── graph.py               # NodeBase 协议 + 图算法（报价=fold/执行=topo/校验=∀/对账=⊆，ADR-039）
│   │   ├── node_runners.py        # 内部节点 crew（preprocess / director 节点 / checkpoint / render）
│   │   ├── step_context.py / step_display.py / edges.py / morph.py / images.py  # 节点共享机械助手
│   │   ├── errors.py              # 执行错误分类：TransientNodeError（step 级重试判定）
│   │   ├── jobs.py                # 队列认领（SKIP LOCKED）+ reap_stale
│   │   ├── asset_processing.py    # 预处理分发：ASR / 文本提取 / 幻灯片转图 / 图片视觉
│   │   ├── clip_spec.py / rendering.py / outputs.py / music.py / quality.py / derivative_dispatch.py
│   ├── agents/          # agent 花名册 + harness 漏斗（ADR-039）：base.py（Agent 唯一类）/
│   │                    #   roster.py（共享 crew：director/persona/translator）
│   ├── skills/          # 技能包（能力唯一家）：__init__.py（SKILL_REGISTRY 收编 + 注册门）+
│   │                    #   clips / dub / captions / posts / quotes /
│   │                    #   carousel / article / music / filler / stills…（节点类+params+私有工序+估价）
│   ├── tools/           # 机械（确定性执行，禁 import agents/LLM client）：asr / voice /
│   │                    #   dubbing / extraction / filler / music / storage / transcript
│   ├── memory/          # Memory：personas 端点、人设皮肤块 → clip-spec 烘焙
│   ├── distribution/    # Distribution：core / channels / publishing / adapters / routes
│   ├── operations/      # Operation Model：registry / service / routes（ADR-032）
│   ├── platform/        # 平台层：auth / email / notifications / project_context / routes
│   ├── models/          # tables.py + schemas.py + database.py
│   ├── clients/         # minimax.py（M3 wrapper + usage 捕获点）
│   ├── prompts/         # Jinja2 模板
│   └── metering.py      # 逐节点计量（usage → workflow_steps.cost，ADR-025）
├── migrations/          # Alembic
apps/web/                # TanStack Start 前端
apps/render/             # Remotion 渲染服务（Node）
packages/clip/           # 共享 <Clip> 组件 + clip-spec TS 类型（镜像 Pydantic）
```

### 7.2 队列机制（ADR-017）

- **Postgres 即队列**：`FOR UPDATE SKIP LOCKED` 认领；独立 worker 进程（`python -m app.worker`），与 API 进程物理隔离；不引入 Redis/Celery，横向扩容时再换 arq/Celery，调用方不变。
- **四个认领源**：`assets.processing_status`（预处理）/ `workflow_runs.status`（生成；deferred claim——项目还有 pending/processing 素材时不认领）/ `outputs.render_status`（渲染）/ `publications`（`state='scheduled'` + `due_at` 部分索引，分发）。
- **孤儿回收**：worker 启动时 `reap_stale` 重置中断任务；失败写 `*_error` 列，认领循环不崩。
- **step 级瞬时重试**（2026-08-02，agent-loop-upgrade W3）：runner 把 provider/网络/存储瞬时故障抛为 `TransientNodeError`（`pipeline/errors.py`）；`execute_step` 按节点类 `retries` 预算（NodeBase 声明，dub/translate = 2）把节点复位 pending（worker 下一 tick 即退避），**不级联跳过下游**；确定性失败（缺输入/空批次）普通异常快速失败。LLM HTTP 层另有 client 内 tenacity，两层不叠加。
- **morph 记账**（同日 W4）：modifier runner（dub/translate/add_music/remove_filler）的 render_spec 改写一律经 `apply_precomputed` 入 operations 账（source 由 `messages.workflow_run_id` 反链派生 chat/system）——chat  morph 可撤销、hash 链不断、ADR-032 写纪律补齐。
- 纪律见 §5 规则 1（耗时任务一律写 pending 行入队，禁跨模块直调 service 执行重活，禁 FastAPI BackgroundTasks）。

### 7.3 横切数据约定

- **字段级事实源 = 代码**：`app/models/tables.py`（表结构）+ `migrations/`（演进史）；文档不复述字段表（旧 PRD 副本已 drift 删除）。
- **认证与隔离**：邮箱验证码无密码登录（Resend）；personas / projects / assets / conversations 全部按 user 隔离；seed 默认用户仅作共享默认内容（demo 项目资产）的属主。
- **存储 key**：DB 只存对象 key，字节在 TOS（ADR-024）；key 前缀 `{user_id}/…` 承载归属；上传走短时 presigned PUT；读取经 API 归属校验后 307 重定向到公开对象 URL（程序拉取走 `?proxy=1` 由 API 转流）。
- **EU 数据驻留**：project 级 `data_region` 是未来差异化（PROGRESS 明确不在本周期），未实现。
- **UI 语言偏好**：future；首屏英文渲染避免 hydration mismatch（见 CLAUDE.md i18n 约定）。
