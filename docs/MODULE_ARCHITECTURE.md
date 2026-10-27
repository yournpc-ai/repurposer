# Module Architecture — 模块划分与边界契约

> Status: 当前系统架构（2026-10-26；模块、表归属、队列与代码地图事实源）
> 排期见 [PROGRESS.md](./PROGRESS.md)；决策见 [DECISIONS.md](./DECISIONS.md)（现行决策集）。

本文回答三个问题：**有哪些模块、每张表归谁、模块之间怎么通信**。当前能力与 PLANNED 边界分行标记；未实施的子能力不回写成整个模块未建。

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
│ FlowView 图面（配方流程图 ✅ / 结果画布 ✅ ADR-041 / 血缘板 📋spike，ADR-036）│ MCP 📋P2 │
│ 【图 = 持久可变产品对象（ADR-057）：画布直读 graph_nodes/graph_edges，零投影】          │
└──────────────────────────────┬─────────────────────────────┘
                               ▼ 意图
┌──────────────── Agent Interface（chat 升级版 + MCP）────────┐
│ dispatch 三类目标：editor 操作 / 整体重生成 / plan 级          │
│ 表：conversations/messages ✅                               │
└───────┬──────────────────────────────┬─────────────────────┘
        ▼                              ▼
┌───────────────────┐   ┌─────────── Pipeline ✅（RunPlan 内核）────────┐
│ Operation Model ✅ │   │ 摄入/预处理（ASR）✅ │ 两步/agent 花名册 ✅    │
│ （操作日志层，      │   │ ┌── RunPlan 内核（施工图，ADR-028 ✅）───┐│
│  三前端共用）      │   │ │ workflow_steps：前奏两步/工具节点/质检节点   ││
└─────────┬─────────┘   │ │ orchestrator 走图 · worker 认领节点       ││
          │             │ │ 链：clip 链 ✅/文案链 ✅/Film 链 ✅/合成链 📋R5 ││
          │             │ └───────────────────────────────────────────┘│
          │             └──────────────────┬────────────────────────────┘
          ▼ spec diff                      ▼ clip-spec / film-spec（spec.family 分派）
        outputs ◄────────────── Remotion 渲染服务 ✅（可替换黑盒）
       （统一产物表 ✅，ADR-030）

┌──────────────── Distribution ✅（与 Pipeline 平级）───────────────┐
│ channel_accounts / publications 状态机 / worker 发布与轮询 ✅        │
│ 审核队列 / 发布数据回流 📋                                          │
├──────────────────────────────────────────────────────────────────┤
│ Memory / Context ✅（persona（含皮肤块 brand / 声音块 voice）+ 术语表 📋） │
├──────────────────────────────────────────────────────────────────┤
│ 合规与计费：credits / wallet / ledger ✅；C2PA / 披露 / EU 驻留 📋      │
└──────────────────────────────────────────────────────────────────┘
```

### 2.1 闭环流转图（工作流闭环 = 全模块指导方针）

六层图回答"有哪些模块"，本图回答**数据与价值怎么流转**——闭环是全模块的指导方针（STRATEGY §3 牌 1）：每个模块都要回答"你在闭环的哪一段、你消灭了哪条断头路"。✅ = 已通，📋 = 未建。

```
 上传/链接        预处理          生成              精修              渲染           分发
┌─────────┐   ┌──────────┐   ┌───────────┐   ┌────────────┐   ┌──────────┐   ┌───────────┐
│ 本地文件  │   │ Asset     │   │ DAG 生成   │   │ Edit/Chat/  │   │ Remotion  │   │ 渠道直发   │
│ 上传 ✅   │──►│ 状态机     │──►│ 编排        │──►│ Regenerate │──►│ render_   │──►│ + 状态轮询 │
│ Zoom/RSS │   │ ✅        │   │ WorkflowRun│   │ 精修三角     │   │ spec ✅   │   │ ✅；审核/  │
│ 📋 P1   │   └──────────┘   │ ✅        │   │ (Operation  │   └──────────┘   │ 回流 📋   │
└─────────┘                  └───────────┘   │  Model ✅)  │                 └─────┬─────┘
                                              └──────┬─────┘                       │
      ┌──────────────────────────────────────────────┴─────────────────────────────┘
      │ 回流两条边（闭环的关键，均 📋）：
      │  ① 精修痕迹（删了哪条、改了哪句）→ Operation Model → 校准打分 / persona（P1）
      │  ② 发布数据（哪条被打开/互动）  → Publication 回流字段 → 校准首发推荐分（P2）
      ▼
┌────────────────────────────────────────────────────────┐
│ Memory / Context：persona（风格/策略/声音/皮肤）· 术语表    │
│ 正向边：注入 plan 前奏 / chat / 分发调性（✅ 单向，规则 4）  │
└────────────────────────────────────────────────────────┘
```

每条边的载体（"流转"落在哪些表/队列/服务上）：

| 边 | 载体 | 状态 |
|---|---|---|
| 上传 → 预处理 | `assets` 行 + worker `SKIP LOCKED` 认领 | ✅ |
| 预处理 → 生成 | ready `workflow_steps`（上游完成 + 当前项目素材门）；run 状态随节点认领翻转 | ✅ |
| 生成计划图 | `workflow_steps`——计划作为一等对象，节点级血统/成本/重跑（ADR-028） | ✅ |
| 生成 → 精修 | `outputs.render_spec` / `outputs.payload`（clip-spec / film-spec 双家族） | ✅ |
| 精修 → 渲染 | `outputs.render_status=PENDING` + writer barrier + `render_claim_token` | ✅ |
| 精修操作记录 | `operations` 表——Edit/Chat 已写入（MCP 座位） | ✅（ADR-032） |
| 分发 | `publications` 状态机 + `channel_accounts`；worker 认领 scheduled 与 publishing poll lease | ✅（外部平台联调仍开） |
| 发布数据回流 | （📋）Publication 回流字段 → 首发推荐分校准 | 📋 P2 |
| Memory 注入 | persona block / brand block（消费者各自拉取） | ✅ |
| 校准回流 | （📋）精修痕迹 + 发布数据 → persona agent | 📋 P1/P2 |

**闭环现状**：上传 → 预处理 → 生成 → 精修 → 渲染 → 导出/渠道直发均已有当前代码路径；平台开发者凭据、外部审批与真实联调仍是开放条件，不能把代码存在写成渠道已可用。审核队列、发布数据回流与精修痕迹到 persona/推荐分的校准消费仍属后续范围，分别按 `PROGRESS.md` 跟踪。

### 2.2 数据架构图（ADR-028/030 后）

```
users（平台层）

Memory/Context：personas（含皮肤块 brand / 声纹块 voice，ADR-038；📋视觉身份/授权）

Pipeline：
assets ──► workflow_runs ──► workflow_steps ✅ ──► outputs ✅（统一产物，ADR-030）
（上传/ASR）  （run 容器）     （施工图：计划+账簿）     type=clip 带 source_ref+render_spec
graph_nodes ──► graph_edges（✅ ADR-057 持久图：媒介类型 × prototype × 业务身份；画布读持久图）
exploration_rows（✅ 探索产物独立存储；legacy graph 探索行只读过滤，不迁入执行图）
music（AI 音乐库）                             payload/files/score/publishing/provenance

Agent Interface：conversations ──► messages
Operation Model ✅：operations（spec diff / 快照 undo；目标为当前可编辑 outputs）
Distribution ✅：channel_accounts ──► publications（直发状态机与轮询）
                                      output_id 单 FK · due_at · metrics · ai_disclosure
                                      publication_events / 发布回流 📋

横切数据流：
计量：LLM usage（ADR-025）→ workflow_steps.cost ──聚合──► workflow_runs
合规：产物 provenance → 分类器 → C2PA（渲染嵌入）+ publications.ai_disclosure
回流：① operations（编辑痕迹）② publications.metrics（发布数据）→ 校准打分/persona
```

读法：模块图回答"谁干活"，本图回答"记在哪"——每张表一个 owner（§4），血统经 `workflow_step_id` 汇聚到 workflow_steps（DAG 内核是数据架构的中心）。

## 3. 模块职责与现状映射

| 模块 | 职责 | 现状代码 | 状态 |
|---|---|---|---|
| **Pipeline** | 素材摄入（上传/未来的链接抓取）、ASR/提取预处理、生成编排（understand/plan 两步 + 工具节点）、RunPlan 计划图（ADR-028 ✅）、渲染触发 | `pipeline/asset_processing.py`、`pipeline/orchestrator.py`、`pipeline/node_runners.py`（内部节点）、`app/tools/`（工具包与 `TOOL_REGISTRY`）、`app/skills/`（SKILL.md 指令包）、`app/agents/`（花名册+harness 漏斗）、`pipeline/rendering.py`；agent 架构事实源 = AGENT_ARCHITECTURE（ADR-039 四层工程地图） | ✅ 已落地 |
| **Operation Model** | 操作日志（每个操作 = clip-spec diff）、undo 语义、agent 可调用的操作 schema（原子/幂等/可检查/可撤销） | `operations/`（registry/service/routes；ADR-032 快照式 undo） | ✅ 地基落地（editor/chat 两前端已写入；校准消费端仍 📋） |
| **Agent Interface** | chat 主交互、意图→计划/操作/run dispatch、有界 tool calling、mentions、SSE/activity；MCP 不在当前范围 | `chat/routes.py`、`chat/service.py`、`chat/plan_turn.py`、`chat/propose_turn.py`、`chat/turn_tools.py`、`chat/activity.py`、`chat/perception/`、`agents/tool_loop.py`；前端 `components/chat/` 与 `components/mentions/` | ✅ 当前主链；目标工具迁移与 MCP 分列后续 |
| **Editor GUI** | transcript 编辑、单轨 trim、Remotion 预览——Operation Model 的前端之一 | `apps/web/src/routes/_app.projects.$id.clips.$clipId.tsx` | ✅ 主体落地 |
| **Distribution** | ChannelAccount（OAuth token 生命周期）、Publication（状态机/幂等/限流重试）、worker 发布与轮询；审核队列、定时策略与数据回流另列 | `distribution/`（core/channels/publishing/adapters + routes） | ✅ OAuth/直发与 worker 链已落地；外部平台凭据和联调开放，回流 📋 |
| **Memory / Context** | Persona（人设：风格 / 策略 / 皮肤块 `brand` / 声音块 `voice`）、术语表（📋）；向 understand/plan prompt / chat 上下文 / 分发调性注入 | `agents/registry.py`（persona 等共享声明）、`memory/brand.py`（人设皮肤 → clip-spec 烘焙）、`memory/routes.py` | ✅ 主体落地（定位根升级为已定方向、未实施——见 `POSITIONING.md` / ADR-042） |
| **合规与计费底座** | AI 内容机器可读标识（C2PA/元数据）、披露、逐节点成本计量、积分钱包（credit / wallet / 台账）、EU 数据驻留 | `metering.py`、`providers/llm/minimax.py`、`platform/billing.py`、`platform/configs.py`、`platform/routes.py` | 计量与 credits/wallet/ledger ✅；C2PA/披露与 EU 驻留 📋，验收归 PROGRESS/ADR-026 |

**精修三角（Editor / Chat / Regenerate）**：精确文字/参数修改走确定性 edit operations 或卡面直改；模糊方向和跨产物修改走项目 Chat，并用 `output` mention 或计划引用确定目标；需要新版本时走当前 regenerate/revision 路径。资产作用域 Modal 已退役。Film 的修改必须先形成并呈现新分镜版本，不走普通 clip 编辑旁路。具体工具、版本与授权边界见 CHAT_ARCHITECTURE、VIDEO_EDITOR 和 Film 当前合同。

## 4. 表归属契约

每张表只有一个 owner 模块；其他模块**只读或经 owner 的服务函数写**。新表必须先在此登记归属。

| 表 | Owner | 其他模块的访问规则 |
|---|---|---|
| `users` | （平台层，暂不属于任何模块） | 只读 |
| `verification_codes` | （平台层，暂不属于任何模块） | 无密码登录验证码；只由 platform/auth 写 |
| `assets` | Pipeline | 其他模块只读；处理状态只由 worker 的 asset_processing 写。**transcript = 资产行的内容层（ADR-113）**：`transcript`/`extracted_text` = 源层唯一座（读口 `pipeline/assets.py:asset_text_content`），`edited_transcript` = 用户改稿覆盖层（写口 = `PUT /projects/{id}/assets/{id}/transcript`，零 run 零积分；C4 双层不变量——改稿只写覆盖层，源层与 `meta.words` 永不动）；cues 永不持久化（读时 `group_cues`/`display_cues` 一法推导） |
| `projects` | Pipeline | 各模块只读 |
| `workflow_runs` | Pipeline | **创建收口于 `orchestrator.create_run`**（/generate、chat dispatch 全部经它，全库无旁路）；状态只由 orchestrator/worker 写。run 级成本 = `workflow_steps.cost` 聚合（API 序列化时计算，不落列） |
| `outputs` | Pipeline | 创建 + `render_status`/`files` 归 Pipeline；`payload`/`render_spec` 由 Operation Model 与受控产物工具按各自写门修改，`publishing` 归 Distribution 表单；payload 三规则（ADR-030）；`workflow_step_id` 为只读血统；`quality` 由 verify 节点写，NULL = 未质检；内部类型（`material_understanding`/`storyboard`/`craft_skeleton`）与 legacy `content_plan` 行经 `visible_outputs_stmt()` 统一过滤；`composition_id`/`composition_version_id`（ADR-145，A 批 1 已建列）= video 家族钉版血缘（配 `work_id = Composition.id`），只由 tools/video 制作缝写入 |
| `conversations` / `messages` | Agent Interface | Pipeline 只读（run 关联展示） |
| `message_seq_counters` | Agent Interface | transcript 数组序计数器（ADR-108）：计数器刻意不住 conversations 行，避免长回合行锁自死锁。新 conversation 首回合的 seq 必须在父用户行所在的同一未提交事务中分配；后续活动/散文行回到 `alloc_message_seq` 独立短事务。seq 单调但允许间隙，不得用时间戳重建第二顺序 |
| `personas` | Memory | 各模块注入用只读；用户经 Memory/persona 路由显式编辑，persona agent 只走受控学习写口。终态 schema（ADR-038）：身份卡 + 风格六件 flat + 策略三件（audience/guidelines/cta）+ `voice` JSONB（声纹块，NULL=Auto）+ `brand` JSONB（皮肤块，NULL=系统默认皮肤）+ `learned_from` JSONB + `calibrated_at` + `auto_created_at`（可空时间戳替代 is_default；默认解析链 = run.context pin > 项目挂载 > auto_created_at 非空 > 最早创建）。【定位根方向：`positionings`、人设表达分区、`topics` 与 `channel_accounts` 挂根仍 PLANNED——ADR-042 / `POSITIONING.md`；启动与验收归 PROGRESS，未实施前不得改写代码词】 |
| `music` | Pipeline（渲染资产库） | 生成/挑选经 music 服务；editor 只读选择 |
| `workflow_steps` | Pipeline | 节点状态只由 orchestrator/worker 写；outputs 的 `workflow_step_id` 为只读血统引用；`spec` 载荷 JSONB（ADR-028）；`cost` 只由 metering（ADR-025）原子累加 |
| `graph_nodes` / `graph_edges` | Pipeline | **图即产品对象**：节点 `type` 是媒介五值，`spec.prototype` 是普通程序形态 `generator/editor/manual`，业务身份另由 summary/tool 表达；legacy type 只在读面归一。结构变更只经 `pipeline/graph_store.apply_wiring_ops`；Chat 与确定性卡面动作都可成为其消费者。画布读取持久图，draft/run/step 反写经 `graph_fill`。`workflow_steps` 保持执行与计费粒度。`island_id/island_seq` 只经 settle 的 `_assign_islands` 写；岛行 INSERT 必须先于成员写入，不能依赖无 relationship 的 flush 顺序。岛容量/廊道/读面 rank 与客户端镜像常量按 `graph_store.py`、`product_graph.display_ranks` 和 `layout.ts` 当前镜像维护 |
| `exploration_rows` | Pipeline | Candidate Set / Select / Content Plan 的独立存储；`spec.exploration_kind` 区分类型，`journey_id` 是归属属性而非图边。出生只经 `pipeline/exploration_store.py` 的 savepoint + 证据校验 + 幂等写门，免费但不直写。探索行不进入执行闭包、报价、rank 或媒体流边；legacy `graph_nodes.type="exploration"` 行只读过滤，不迁移回执行图。真实目标 DB upgrade/downgrade、读/编译/replay 验收归 Working Loop 当前合同 |
| `journeys` | Pipeline（ADR-088） | 探索旅程的归属锚（`goal_text` + 项目级联删除）；**不是状态机**——状态住探索产物行自身。写只经探索写门（goal_text 即身份：同 goal 重放先 adopt 再判幂等，无双生）；各模块只读 |
| `graph_islands` | Pipeline（Workspace 合同 v4.2 C6） | **Layout Island 注册表**（组内自治、零 UI）：sibling group 出生定格的独占布局区域——`depth` + `parent_ids`（媒体流父集 = 组身份，ctx 边不入）+ `origin_x/origin_y/row_h` + `cols`（预留列 = 增长廊道；更深带已有定居成员**或同批新生更深节点**时 Clamp 回 1——2026-09-29 同批封死律：同批链延续尚在途中时预留廊道会在出生第一天就往画布打入一列永久空槽）+ `cap`（每列行数 C=4；容量参数注册默认 `_ISLAND_COL_CAPACITY=4 / _ISLAND_CORRIDOR_COLS=1 / _ISLAND_MAX_COLS=3`，住 `pipeline/graph_store.py`）。行冻结（无 updated_at）；**出生/认领只经唯一写门** `apply_wiring_ops` 内的 settle（`_assign_islands`，两阶段 flush——岛行 INSERT 先于任何成员写入，裸 FK 轮盘赌律）；真超容量走集合态留座（contact sheet，留座未实现）。`graph_nodes.island_id/island_seq` 为成员归属列；读面 rank 岛化 = `product_graph.display_ranks`（岛占 cols 个连续 rank 槽），客户端镜像 = `layout.ts` projectSettledFrames（冻结格 y 直读 + 压缩地板 = `spec.island.reserved_bottom`） |
| operations | Operation Model ✅ | editor GUI / chat 两前端写入（MCP 座位）；append-only，`undone_at` 唯一可写字段 |
| publications / channel_accounts | Distribution | 状态机只由 Distribution 服务迁移；回流字段预留给分析（📋；publication_events 仍 P2） |
| `notifications` | （平台层，暂不属于任何模块） | 事件源模块经 `platform/notifications.create_notification` 写（当前唯一写者 = Distribution `_transition` 终态钩子）；读/已读收口于 `/notifications` 路由 |
| `wallets` | （平台层，暂不属于任何模块） | 积分余额（ADR-055，`docs/BILLING.md`）；只由 `platform/billing.py` 写（乐观锁 `version`）；读收口于 `/wallet` 路由 |
| `credit_transactions` | （平台层，暂不属于任何模块） | 积分台账（append-only）；只由 `platform/billing.py` 写（`idempotency_key` UNIQUE 去重）；读收口于 `/wallet/transactions` |
| `conversation_usage` | （平台层，暂不属于任何模块） | 会话层 LLM 计量台账（ADR-117 D3——计量不收费，永不上账单/UI）；每回合一行，只由 `metering.fold_conversation_usage` 在回合入口缝（execute_chat_turn / answer_question / run_trigger_turn）随回合自身 commit 写；读 = 内部审计（COGS / W11 fair-use 数据基础 / context 预算校准），无路由 |
| `configs` | （平台层，暂不属于任何模块） | 公共运营参数表（key 点号命名空间）；`CONFIG_REGISTRY` 是唯一事实源，一切读取走 `platform/configs.get_config()` 漏斗，模块禁直查表 |
| `page_readings` | Tools（world 座位层，`app/tools/world.py`） | 项目级页面读本（ADR-124：(project_id, url) 主键 + text + fetched_at，快照语义，随项目级联）；读收口于 `world.page_reading_for_url` 一座，写只经 `world.upsert_page_reading`（chat 读工具写穿走 `world.write_page_reading` 独立短事务；capture 链在 `process_asset` 会话内写） |
| `film_narrations` | Tools（film 座位层，`app/tools/film/narration_store.py`） | 旁白复用库（ADR-138 §10.1）：`(project_id, content_hash)` 唯一，一行 = 一条旁白词的 speed-1.0 原速原件（storage_key + duration_s；适配产物是 run 级 staging，永不住本表）；复用键 = 归一化文本｜已解 voice_id｜语言｜合成配置；一切读写经 `narration_store` 一座（resolve / finalize / fail——原子占位 + 有界接管 + owner 条件写，全独立短会话，run 回滚不带走已完成的行）；消费面 = `narration.py` 合成链，随项目级联删除 |
| `compositions` / `composition_versions` | Editing（ADR-145，A 批 1 已建表） | 内容只经 `app/editing/store.apply_composition_edits`（Composition 行锁序列化 + base_ref CAS + request_id 幂等 + 整批原子）；版本行 append-only 不可改写，`version` 在 Composition 内单调递增；其他模块只读；`origin_project_id` 记来源 Chat 但 SET NULL——删 Chat 不级联毁作品；Composition 删除是未来的显式 op（本批无删除口） |
| `source_snapshots` | Editing（A 批 1 已建表） | 不可变内容快照（owner + asset_id SET NULL 溯源 + storage_key + digest + duration_ticks @SOURCE_TIMEBASE）；行不可原地改写，refresh/换素材 = 新行；登记写口为 editing/sources.register_snapshot；tools/video/preparation 负责从既有 Asset 冻结资源并调用登记，Chat 素材接入在 B 完成 |

**outputs 共享聚合的细则**：Pipeline/worker 负责创建、渲染状态、执行身份与产物文件；Operation Model 负责其注册范围内的 payload/render_spec 编辑与 operation journal；Distribution 只写 publishing 表单。任何写者只碰自己的字段子集，终态渲染写必须匹配 `render_claim_token`。Operation Model 覆盖的内容修改必须产生 operation 记录；Film 版本编辑、系统反写和发布字段不得被伪装成 clip operation。

### 4.1 行业词汇对照（Mastra / Agno / OpenAI ↔ 本系统）

对照唯一事实源——评估外部框架、写新文档、评审命名时以此为准，不另起炉灶。

| 行业通用词 | 本系统对应 | 说明 |
|---|---|---|
| Agents（LLM 决策单元） | `app/agents/`（一个 Agent 类 + 声明实例，N-29/N-30） | 与 Mastra/Agno 同词 |
| Tools（可调用能力） | `app/tools/` 工具包 + `TOOL_REGISTRY` | 工具可包含确定性工序或声明式 agent；同名节点类持有执行、拓扑、计量与估价知识，LLM/provider 依赖按当前依赖方向走 `app/providers/` |
| Skills（指令包） | `app/skills/*/SKILL.md` + `SKILL_REGISTRY` | 装配期按声明注入写作/工艺知识；无运行时工具发现，不替代 `TOOL_REGISTRY`，不是另一套节点能力 |
| Agent Harness（调用面脚手架） | `agents/base.py` 漏斗 + contexts 装配 + prompts | 装配/校验/修复一轮/计量/声明兜底（harness 单义 = 本调用面，N-48） |
| Workflows（编排图+执行） | RunPlan 内核（orchestrator + workflow_steps + worker 认领） | Workflow State=run 状态机；Suspend/Resume=step `waiting` 座位；Snapshots=spec/context；HITL=variant_pick gate（📋） |
| workflow run（执行实例） | `workflow_runs` 表 | 行业标准全名（每 run 自带其编译出的 workflow=步骤图） |
| Agent Runtime | `app/worker.py` | 执行进程 |
| Memory | `memory/`（personas） | persona/brand block 单向注入 |
| Evals（Scorers/Gates/Verdicts） | `pipeline/verify.py` + `quality.py`；variant_pick gate 等未实施能力单列 | verify 是当前注册可执行节点；eval=活动，与 Mastra 兼容 |
| Threads / Conversations | `conversations` + `messages` | OpenAI Conversations API 同款 |
| Agent Observability | metering（workflow_steps.cost）+ structlog + 📋 METRICS.md | 横切不开包（§5） |
| Channels | `distribution/` | 直发渠道 |
| Guardrails | 数据/执行门当前分散在 registry、出生地、claim token 与 scope classifier；合规分类器/C2PA 📋 | 新闸门先登记 owner 与拒绝形态；合规排期归 PROGRESS |

反对照：`pipeline/` 模块 ≠ Mastra Workflows（我们的 Pipeline = 摄入+ASR+编排+渲染，大于 Workflows，不改名）；`chat/` ≈ Agno Interfaces。

### 4.2 视频目标模块与表归属（ADR-145）

本节登记新架构准入与其落地阶段；完整新旧目录/代码处置唯一合同 = [VIDEO_PROJECT §12](VIDEO_PROJECT.md#12-目标目录与新旧代码处置)。A 批 1 已把 `compositions` / `composition_versions` / `source_snapshots` 与 `editing` 模块落进 §4 当前表（上方）；下表剩余行为仍 TARGET。

| 目标表 / 模块 | Owner 与写口 | 阶段与当前边界 |
|---|---|---|
| `compositions` / `composition_versions` | Editing（app/editing）；内容只经 apply_composition_edits，CAS/事务由 store 实现 | **A 批 1 已落地**（见 §4 当前表）；不把 Project/Output 表转移到 Editing |
| `source_snapshots` | Editing 的 sources 服务 | **A 批 1 已建表**；生产写口（素材链快照采集）归后续 A 批；原 Asset 处理状态仍归 Pipeline，不能变成第二 Asset 库 |
| `video_narrations` | Tools（app/tools/video/narration_store.py） | B 承接原件复用/恢复；替代 film_narrations，设计用户权限与跨 Chat 复用，不搬旧业务行；旧表当前归属在退役前不变 |
| `user_skills` / `skill_versions` | Skills 的 store/import 服务 | C 新建；用户显式版本绑定不替代 Tool 注册/执行授权，平台内置包仍沿现有注册表 |
| `editing` 模块 | 内容/版本/快照的领域与应用服务，有独立表归属 | **A 批 1 已落地**（schemas/timing/edits/validators/store/video_spec/storyboard）；service/director/grounding/templates 归 B；不认领 Run/render 队列，不创建第二 scheduler |
| `tools/video` / `packages/video-spec` / renderer adapter | 分别为执行能力、纯渲染契约与具体引擎实现 | **A 批 1 已落地最小缝**（produce.py 队列缝 + 契约包 + Remotion adapter）；produce_video run 节点/估价/计费归 B；Render/Output/Run owner 继续按现行 Pipeline 合同 |

## 5. 跨模块通信规则

1. **长任务与可重试生产链走队列**：生成写 `WorkflowRun`/`workflow_steps`，渲染写 `outputs.render_status`，发布写 `publications`，由 worker `FOR UPDATE SKIP LOCKED` 认领。**禁止 FastAPI BackgroundTasks**，禁止为新的跨模块重活直接调 service 绕开队列。当前有明确请求内联例外：`POST /music/generate`、cover、revise、translate-captions 与 dub 在各自路由内执行；这些例外不得被推广成“所有重活都可 inline”，新增或改为长任务时必须回到队列合同。
2. **读路径走 API 服务层**：模块间同步读数据经服务函数/路由，不跨域直写对方的表。
3. **clip-spec / film-spec 是 Pipeline ↔ 渲染的平级契约**：渲染服务不读 DB，按 `spec.family` 分派；Operation Model 的编辑使用对应 spec 的受控 diff/operation，不引入第三契约或 renderer 概念。
4. **Memory 注入是单向的**：Memory 模块只暴露"注入载荷"（persona block / brand block / glossary），不知道谁在消费；消费者（understand/plan / chat / distribution）各自拉取。
5. **合规与计费是横切切面**：LLM 调用统一经 ADR-025 接口层（计量落 `workflow_steps.cost`）；内容标识按 clip-spec/film-spec 与 generated provenance 分类，在渲染嵌入与 Distribution 披露元数据两处落地，不分散到各模块自行判断。
6. **内核重建接缝稳定**：模块内核可重建，只要表归属与通信规则不变，其他模块零感知——已有先例：Pipeline 的 RunPlan（DAG）化时，Distribution / Memory / Editor GUI / Operation Model 全部零改动（缝 = 产物表与 clip-spec）。新内核设计必须守住既有接缝，不得以内核升级为借口移动缝。

## 6. 演进规则

- **新功能先问归属**：归属不清时按"谁写这张表"判定；都不写表的功能（纯 UI）归最近的前端模块。
- **新模块准入**：必须有独立的表归属或独立的队列认领源，否则只是现有模块的职责扩充。
- **命名注意**：竞品文档中 "pipeline" 也指 Opus 范式（见 DECISION_MATRIX 范式短名）；内部模块语境下 Pipeline = 我们的生成管线，引用竞品时写 `Pipeline 范式`。
- **新世界事件/阶段的用户可感效果 = 五座位登记**：任何新的异步阶段或世界事件上线时，必须逐一登记——① trigger 白名单条目 + fire 点（`pipeline/trigger_events.py`，扩名单 = ADR 评审）；② `chat/trigger_turn.py` 的 case；③ 对应 prompt bullet（`trigger_system.j2` 或当事 prompt）；④ 前端到达通道（SSE 帧或 watch-window 轮询——**轮询续航 ≥ 该阶段的最坏时长包络**，保险丝短于包络 = 页面假死）；⑤ activity / i18n 键（如该阶段有 live 里程碑行）。缺任何一个座位，该阶段就在某一面对用户失声。
- **本契约的变更 = ADR**：表归属调整、新横切切面、认领源增减都要写 ADR 并更新本文。

## 7. 代码地图与运行约定

### 7.1 代码地图

```
apps/api/
├── app/
│   ├── main.py / config.py / worker.py   # FastAPI 入口 / 配置 / 独立 worker 进程
│   ├── dependencies/    # 依赖注入（auth：JWT；私有用户数据无匿名默认回退）
│   ├── chat/            # Agent Interface：routes（SSE、POST /outputs/{id}/regenerate）/ service /
│   │                    #   plan_turn / propose_turn / trigger_turn / turn_tools /
│   │                    #   activity.py（LoopEvent → user-safe activity 的纯投影）/
│   │                    #   perception/（只读工具注册与执行）/
│   │                    #   context.py（chat 意图上下文装配 build_context——各层自装上下文，
│   │                    #   harness 不代读 Message/outputs，ADR-087 §6）
│   │                    #   / canvas_visibility.py（环境谓词 api 半座，ADR-118 §6：
│   │                    #   canvas_visible = canvas_available ∧ world_live，与 web
│   │                    #   lib/canvasVisibility.ts 同义互指；conversations.canvas_available
│   │                    #   能力位戳 = ui_language 同律座）
│   │                    #   / exploration_tools.py（探索终态工具族，ADR-088 §2：
│   │                    #   EXPLORATION_TOOLS harness 四动词全终态 + exploration_chat_tools() 生产投影——
│   │                    #   candidates/selects 非终态一回合连续工作、propose_plans/revise_plan 终态
│   │                    #   R15 停顿；execute 走 plan_turn 的探索座位，写一律经 exploration_store 门）
│   │                    #   / seams.py（wire_pipeline_seams：trigger handler + conversation bridge 注册，
│   │                    #   组合根 app.main / app.worker 各调一次）
│   ├── pipeline/        # Pipeline（RunPlan 内核）
│   │   ├── routes/      # projects（含 GET /projects/{id}/graph 画布直读帧，ADR-057）/ assets / outputs
│   │   │                #   （regenerate 端点住 chat/routes.py——依赖方向）/ runs / music / recipes 端点
│   │   ├── orchestrator.py        # RunPlan 物化/走图（create_run = WorkflowRun 唯一出生地；逐节点 estimate 落库 = 报价存储侧）
│   │   ├── lifecycle.py           # Lifecycle Projection（ADR-087 §2）：服务端命名只读生命周期戳——
│   │   │                        #   compute_lifecycle 纯谓词族（零 DB，T1~T15 纯测试矩阵）+ project_lifecycle
│   │   │                        #   装配器（读既有 Domain facts：资产四态 / 出生地 Requirement / 同款链重裁决 /
│   │   │                        #   has_active_run；chat 事实由调用方经 public 协议传入，本模块零 chat import）；
│   │   │                        #   读者 = Transport（results/graph 响应）→ Presentation；不加表、不写 DB
│   │   ├── scope_classifier.py    # Deterministic Scope Classifier（ADR-087 §4 + D4/D2）：
│   │   │                        #   continuation/expansion/unproven 三值纯核（零 op 词汇——消费 wiring 门前后
│   │   │                        #   图 facts 比对，D4 结果 scope 律）+ 链逐字匹配器（历史 run.context 证明
│   │   │                        #   approved retry，D2）+ 纯核+装配器两瓣（facts gatherer 读 graph_nodes/
│   │   │                        #   graph_edges/workflow_runs 只读）；B1 additive 未接线——B2（edit_graph）/B5（/generate）切换
│   │   ├── scope_compile.py       # 能力编译器（ADR-089 §1~§3）：Content Plan →
│   │   │                        #   Execution Scope 的确定性纯函数（R12 编译移出 LLM——clip → cut_segments，
│   │   │                        #   四 writer 带 source_span；证据指针编译期解引用 R7；编译产物重入
│   │   │                        #   validate_task_list 裁决 B3 上移）+ decision_package_plans（决策包阅读层
│   │   │                        #   R16）+ build_confirmed_scope（R20 快照构造器）；域拒绝 =
│   │   │                        #   ScopeCompileRejected（WiringRejected/ExplorationRejected 同族）；纯函数零写
│   │   │                        #   【R20 修订路由器 route_revision（快照
│   │   │                        #   plan_task_map → 任务切片 → fill_key → 活图节点集；plan_ref 序位词/plan_id
│   │   │                        #   双通道 + @output 单通道 + 诚实降级）+ R19 消费侧 assemble_craft_revision /
│   │   │                        #   compose_revised_program（prompt 消费族门控，确定族 uncovered 披露）】
│   │   ├── run_review.py          # 收官兑现审计纯核（ADR-088 §8 R21）：
│   │   │                        #   confirmed_scope 快照 × landed outputs × 实扣 ledger → 兑现事实清单
│   │   │                        #   + 缺口裁决（保守——只点名数据证明缺失的）+ review_fact_lines 有界渲染；
│   │   │                        #   零 LLM 零 DB；与图内质检 verify 分词（verify 住执行图、review 住 chat
│   │   │                        #   边缘触发回合——消费座 = chat/trigger_turn._run_review_lines）
│   │   ├── exploration_store.py   # 探索写门（ADR-088 §2）：
│   │   │                        #   propose_candidates / propose_selects / propose_plans / revise_plan 四动词
│   │   │                        #   （savepoint + range 校验与摘录服务端派生（ADR-107）+ 幂等 + 完整性自检；免费但真写门）+
│   │   │                        #   journey 读座位 read_journey_evidence / read_journey_plans（编译器的
│   │   │                        #   只读证据来源——读面不是写门）【revise_selects
│   │   │                        #   门分支（member_index 编辑 + verdict/reason 强制重述 + idem 保留）+
│   │   │                        #   mark_compiled / supersede_plan 双态写者（E3）+ select_revision_phase
│   │   │                        #   三金钱态纯判别 + read_journey_summaries / output_fact 记忆读座（S6）】
│   │   ├── trigger_events.py      # trigger 白名单事件缝：kind ∈
│   │   │                        #   {run_completed, run_failed, craft_decompiled}；扩名单需 ADR 评审。
│   │   │                        #   fire-and-forget，未注册静默降级且不让 pipeline 失败；
│   │   │                        #   handler 由组合根注册——pipeline 零 app.chat import
│   │   ├── conversation_bridge.py # 会话写命令显式 protocol（ADR-087 §6）：
│   │   │                        #   dock_interrupt_question / finalize_bailed_runs / seed_project_prompt /
│   │   │                        #   discard_unanswered_plan 四命令 bridge delegate（同签名 + db 透传 +
│   │   │                        #   flush-only 事务语义原样；未注册 fail-loudly）；实现住 chat/service.py
│   │   ├── graph.py               # NodeBase 协议 + BoundedLoopNode（有界 loop，ADR-052 B4）+ 图算法（报价=fold/执行=topo/校验=∀/对账=⊆，ADR-039）
│   │   ├── graph_store.py         # wiring 层（ADR-057）：apply_wiring_ops = 持久图唯一写口
│   │   │                        #   （add_node / connect / edit_prompt / delete_node / run(_subgraph)，op 校验 +
│   │   │                        #   单事务 + 定居取景 layout 指派；GraphDelta 返回受影响子图）
│   │   ├── graph_fill.py          # run/draft → 图 stamping 内核（同一推导源零漂移）：stamp_run_graph（create_run
│   │   │                        #   图填充，fill_key 幂等复用无双生）/ stamp_draft_graph（dock 即 stamp 草稿图，
│   │   │                        #   图先展示后运行）/ clear_draft_graph（bail 拆除）/ sync_graph_node_for_step
│   │   │                        #   （step 终态 → 节点聚合态【族头门控：running 只在族头越过 pending 后点亮，
│   │   │                        #   折叠前奏不借宿主 loading 面；族尾 verify 窗保持亮】+ 产物反写
│   │   │                        #   spec.output_ids 版本累积）/
│   │   │                        #   stamp_asset_node（上传即落图；转写稿 document 已退役——
│   │   │                        #   ADR-113：transcript = 资产行的内容层，永不成节点）/
│   │   │                        #   research brief document（agent 节点的产物面，sync 镜像终态与正文）
│   │   ├── graph_revise.py        # 修订桥（K4）：图节点 → task list（spec.tool/spec.params 展开），
│   │   │                        #   WiringProposal 的 run op 经它进 create_run（出生地不变）
│   │   ├── node_runners.py        # 内部节点 crew（preprocess / understand·plan / checkpoint / render）
│   │   ├── step_context.py / step_display.py / edges.py / morph.py / images.py  # 节点共享机械助手（step_context 兼估价事实装配 _estimate_facts）
│   │   ├── errors.py              # 执行错误分类：TransientNodeError（step 级重试判定）
│   │   ├── jobs.py                # 队列认领（SKIP LOCKED）+ reap_stale
│   │   ├── asset_processing.py    # 预处理分发（PROCESSORS 链）：内容哈希 → ASR / 文本提取 / 幻灯片转图 → speaker_map / prosody
│   │   ├── web_capture.py         # WEB_PAGE 采集 processor（MG D1b）：capture 编排 + 截图入对象存储 + meta 回写
│   │   │                        #   （research 清单为 substance，截图可诚实缺席）；出生时 SSRF 静态门在 assets.py
│   │   ├── speaker_map.py / prosody.py  # asset 级确定性工序：说话人话轮（ADR-045）/ 韵律特征（期 1，ASR 同族）
│   │   ├── visual_anchors.py      # IMAGE 确定性视觉半（期 1）：YuNet 人脸/主体框/安全区（归一化坐标）
│   │   ├── beat_map.py            # 节拍地图代码半（期 1）：LLM 文本锚吸附 ASR 词轴 + 金句自包含检查 + 理解 prompt 源块装配
│   │   ├── assets.py              # 服务端源素材创建（chat 声明文本 → transcript 资产）
│   │   ├── tracks.py              # TRACK_REGISTRY 可执行 catalog：轨分区 fold（烘焙缝/C2PA/ops 寻址/一轨一写者 422，ADR-044）
│   │   ├── track_stack.py         # 轨道栈读面投影（ADR-113 §4，纯模块）：render_spec → 视频轨（保留段
│   │   │                        #   产出轴拼接 + 源区间 + 源资产 id）+ 文字轨（字幕句按段分组，切断 = 硬断句）
│   │   │                        #   + 修饰存在位；读时推导永不持久化，/results 与 /graph 两座 stamp
│   │   ├── recipes.py             # RECIPE_REGISTRY 服务端静态注册表（配方 = 数据，ADR-040）
│   │   ├── clip_spec.py / rendering.py / outputs.py / music.py / quality.py / derivative_dispatch.py
│   │   │                        # （outputs.py 兼报价读面：fold 聚合 aggregate_step_estimate + 偏差回归 step_estimate_deviation）
│   │   ├── render_probe.py      # 产物文件校验闸纯核（MG D4 放行闸③，禁无文件校验的成功态）：
│   │   │                        #   rendering.py 成功路径落 COMPLETED 前唯一闸门，家族分派检查项
│   │   │                        #   （film：h264/1920×1080/流帧计数 ±1 帧——容器时长有 muxer 衬垫，
│   │   │                        #   永不作契约面；clip：存在/非零/可读 + sidecar 存在即法、非零
│   │   │                        #   当且仅当 caption_track 非空）；未过 = FAILED +
│   │   │                        #   spec.failure{stage:probe} 盖 render 镜像节点（台账读单字段）；
│   │   │                        #   video 家族（ADR-145）：spec 自带 width/height/duration_frames/
│   │   │                        #   有理数 fps 为契约面，任一 audio clip → 容器必须带音频流
│   │   ├── verify.py            # 内部质检节点：确定性矩阵裁决 + QualityBounce 打回 + best-not-last
│   │   │                        #   快照回退 + 双败 escalation（dock 提问 + Suspend）；quality.py = 检查矩阵
│   │   │                        #   纯函数半边（fidelity 族 + craft 可测量项 + run_checks 按类型分派）
│   ├── editing/       # Editing（ADR-145，A 批 1 已落地）：Composition 内容领域——
│   │                    #   schemas（CompositionContent：settings/sources/scenes/timeline）/
│   │                    #   timing（整数 ticks + 有理数 fps 唯一量化座，与 packages/video-spec
│   │                    #   共享 golden fixtures）/ edits（op 词汇 + 纯 apply + duplicate_clip
│   │                    #   重映射）/ validators（整候选校验：引用/三时间域/同轨重叠/动画目标）/
│   │                    #   store（apply_composition_edits 唯一内容写口：行锁序列化 +
│   │                    #   base_ref CAS + request_id 幂等 + 整事务原子；get_video_version 读面）/
│   │                    #   video_spec（编译 family="video" 自足 spec）/ storyboard（canonical
│   │                    #   分镜读面）/ sources（快照登记）/ fonts（纯资源描述）；
│   │                    #   存储/字体发布 IO 在 tools/video/preparation，依赖方向由 gate 6a 检查
│   ├── agents/          # agent 声明 + harness 漏斗（ADR-039）：base.py（Agent / StreamingAgent）/
│   │                    #   registry.py（共享 crew：understand·plan/persona/translator 等）/
│   │                    #   contexts.py（GenerationContext + output_one_liner 装配层；
│   │                    #   chat 意图上下文住 chat/context.py）/
│   │                    #   tool_loop.py（有界工具 loop harness，ADR-077；typed LoopEvent 内部事件通道——
│   │                    #   内核只说「发生了什么」，用户语义归 chat/activity.py，ADR-087 §3 U1 冻结边界）
│   ├── tools/           # 工具包（能力唯一家，N-42）：article / captions / carousel / clips /
│   │                    #   dub / filler / music / posts / quotes / reframe / research / revise / stills
│   │                    #   （节点类+params+私有工序+估价+私有 agent 声明）；
│   │                    #   research = 有界 loop 节点首座（ADR-052 B4）：node（BoundedLoopNode，
│   │                    #   max_iterations=8）+ agents（researcher）+ web（零键 DDG search/fetch，
│   │                    #   诚实降级）+ spec.research_brief 钢印 → consumes_research 写手注入；
│   │                    #   + capture（网页素材采集：结构化抽取 + 受控浏览器截图；与讨论高度 web 读面分工）；
│   │                    #   浏览器级 SSRF 边界：顶层导航、重定向、子资源同一策略——协议白名单、
│   │                    #   私网/保留地址拒绝、DNS 解析后重验，配合请求数/字节/时间帽与隔离无凭证上下文；
│   │                    #   _PolicyProxy 是唯一浏览器拦截座，截图失败可 degrade-honest，manifest 仍是本体
│   │                    #   stills/beats.py = 节拍方案代码半（期 2）：backing 表装配 + 拍锚吸附平铺 +
│   │                    #   coherence_violations 跨拍连贯性检查 + 两段式编排（大纲→逐拍，handoff 交接）；
│   │                    #   stills/agents.py = 剪辑师双件声明（stills_editor / stills_editor_outline）；
│   │                    #   video（ADR-145，A 批 1）：produce.py = CompositionVersion → video-spec →
│   │                    #   Output 血缘 + render 队列 pend 的最小制作缝（run 节点/估价/计费归 B）
│   ├── skills/          # 指令包（SKILL.md 领域知识即数据，装配期注入，模型无感）：SKILL_REGISTRY 收编；
│   │                    #   linkedin-longform / stills-editing-craft（期 2 剪辑工艺先验表）
│   ├── providers/       # 外部服务包装（禁 import agents/LLM 决策层）：
│   │                    #   llm/minimax.py（M3 client、PRICING、usage 捕获）/
│   │                    #   asr / voice / vision（YuNet + vendored weights）/ storage
│   ├── memory/          # Memory：personas 端点、人设皮肤块 → clip-spec 烘焙
│   ├── distribution/    # Distribution：core / channels / publishing / adapters / routes
│   ├── operations/      # Operation Model：registry / service / routes（ADR-032）
│   ├── platform/        # 平台层：auth / email / notifications / project_context / conversation_context
│   │                    #   （会话只读协议座——§4「Pipeline 只读」批准座：find_conversation /
│   │                    #   latest_pending_question / is_pending_plan / get_project_prompt，零写）/
│   │                    #   configs（公共参数表漏斗）/ billing（积分钱包：hold→capture→release，ADR-055）/ routes
│   ├── models/          # tables.py + schemas.py + database.py
│   ├── prompts/         # Jinja2 模板
│   ├── ui_locale.py     # UI 语言管道（Accept-Language → ContextVar → create_run 钉入 run.context）
│   └── metering.py      # 逐节点计量（usage → workflow_steps.cost，ADR-025）
├── migrations/          # Alembic
apps/web/                # TanStack Start 前端
apps/render/             # Remotion 渲染服务（Node）：server.ts 按 spec.family 三分派
                         #   （clip 缺省 / film / video——ADR-145）；src/video/ = video 家族
                         #   adapter（capabilities 声明 + Remotion 实现限 src/video/remotion/）；
                         #   scripts/render-video-local.ts = 本地渲染调试入口
packages/clip/           # 共享 <Clip> 组件 + clip-spec TS 类型（镜像 Pydantic）
packages/video-spec/     # video-spec 契约包（ADR-145，A 批 1）：zod schema + 纯量化/插值
                         #   求值 + golden fixtures（与 app/editing/timing.py 共享）；零
                         #   React/Remotion 依赖（check_gates gate 6b）
```

### 7.2 队列机制（ADR-017）

- **Postgres 即队列**：`FOR UPDATE SKIP LOCKED` 认领；独立 worker 进程（`python -m app.worker`），与 API 进程物理隔离；不引入 Redis/Celery，横向扩容时再换 arq/Celery，调用方不变。
- **四个认领源**：
  1. **资产预处理**：`assets.processing_status=PENDING` 且 `processing_requested_at IS NOT NULL`；休眠上传不会被无条件加工，读取或 `create_run` 先登记真实处理请求。
  2. **生成节点**：ready `workflow_steps`，不是 `workflow_runs.status`。谓词要求 step pending、上游 inputs 全 done、非 runtime fanout，并遵守当前项目素材门；认领铸造 `claim_token`，同时把 owning run 从 PENDING 翻为 RUNNING。
  3. **渲染**：`outputs.render_status=PENDING` 且 writer barrier 已满足；认领铸造 `render_claim_token`。状态本身不是终态写权，所有终态写都必须匹配 token。chat `retry_upload` 只复位同一 Output 行与原 render step，`upload_only` 骑内部请求 envelope，不新增认领源、不进入 clip-spec / film-spec。
  4. **发布**：`publications.due_at <= now` 且 state 为 `scheduled`（开始发布）或 `publishing`（poll lease 续轮询），不只认 scheduled。
- **渲染执行形态（MG D4）**：渲染认领后跑 asyncio task（与节点同构），并发上限 `settings.render_concurrency`（默认 2，争用资源 = 渲染服务的 headless Chrome）、单渲染栅栏 `settings.render_timeout_seconds`（默认 1800）——两者住 env Settings（工程参数座位，configs 边界律 = `platform/configs.py` 头 §3）；任务化同时消除了单渲染内联等待堵 tick 环的旧形态。产物落 COMPLETED 前必过 probe 闸（`render_probe.py`，见 §7.1）。
- **孤儿回收**：worker 启动时 `reap_stale` 重置中断任务；失败写 `*_error` 列，认领循环不崩。
- **step 级瞬时重试**：runner 把 provider/网络/存储瞬时故障抛为 `TransientNodeError`（`pipeline/errors.py`）；`execute_step` 按节点类 `retries` 预算（NodeBase 声明，dub/translate = 2）把节点复位 pending（worker 下一 tick 即退避），**不级联跳过下游**；确定性失败（缺输入/空批次）普通异常快速失败。LLM HTTP 层另有 client 内 tenacity，两层不叠加。
- **morph 记账**：modifier runner（dub/translate/add_music/remove_filler）的 render_spec 改写一律经 `apply_precomputed` 入 operations 账（source 由 `messages.workflow_run_id` 反链派生 chat/system）——chat  morph 可撤销、hash 链不断、ADR-032 写纪律补齐。
- **会话纪律（ADR-050）**：session 不跨长等待，且 **Session 2 永不脏 step 行**——计量 = contextvar 内存台账，`execute_step` 尾段一次归并写 `workflow_steps.cost`（五终态分支同记）；`render_output` 短 session 快照 → 无 session 横跨渲染 POST → 新短 session guarded 写入；runner 中途写 spec 只走 `step_display` own-session 原子写（`_pop_spec_field` / `_set_*`），ORM 赋值 = 自死锁；`outputs.workflow_step_id` / `outputs.project_id` / `operations.project_id` / `workflow_steps.run_id` 四条 FK = DEFERRABLE INITIALLY DEFERRED（父行锁窗口挪到 COMMIT）。DB 保险丝 `idle_in_transaction_session_timeout=3600s`（部署必配——Session 2 横跨单次 LLM await 是保留设计，provider 慢窗口单次调用纯等待可达数十分钟；排队/制作的小时级等待走队列行、永不持事务；保险丝只防永久 wedge）。
- 队列边界与当前 request-inline 例外见 §5 规则 1；任何新增 processor 或认领源都必须同时登记 §4/§5/§7，不得只看本节的四个现有源。

### 7.3 横切数据约定

- **字段级事实源 = 代码**：`app/models/tables.py`（表结构）+ `migrations/`（演进史）；文档不复述字段表。
- **asset.meta 键词汇**（处理链产物一律进 meta JSONB，不加表列）：`words`（ASR 词级时间戳——确定性地基，LLM 永不覆写）/ `language` / `speaker_map`（话轮归属）/ `prosody`（韵律：逐词 F0/能量 z、强调峰、filler 区）/ `visual_anchors`（确定性视觉半：人脸/主体框/安全区，归一化坐标；语义半在理解载荷，按 asset_id 汇合）/ `content_sha256`（内容寻址键，见下条）。
- **素材理解前移（产物质量线期 1）**：项目素材集齐（全部 COMPLETED）即由 `process_asset` 完成钩子 fire-and-forget warm 出 `material_understanding` 行（`workflow_step_id=NULL`、`source_ref.warmed=true`）；digest 内容寻址（`understanding_v3` salt + 逐素材 `type|content_sha256` 描述符自排序；无哈希行回退上传身份，仅同项目复用）；复用查询 = **同用户跨项目**最近 20 行内哈希命中，命中行**引用不复制**（删除源项目会使他项目 run 的 output_refs 悬空——重跑即再生，期 1 接受）；warm 无 workflow step 绑定，计量按 request-path 先例静默 no-op（per-call 台账 = 需求池 agent_calls P1）。
- **认证与隔离**：邮箱验证码无密码登录（Resend）；personas / projects / assets / conversations 全部按 user 隔离；seed 默认用户仅作共享默认 personas 的属主；启动仅播种默认音乐。
- **存储 key**：DB 只存对象 key，字节在 TOS（ADR-024）；key 前缀 `{user_id}/…` 承载归属；上传走短时 presigned PUT；读取经 API 归属校验后 307 重定向到公开对象 URL（程序拉取走 `?proxy=1` 由 API 转流）。
- **素材源缓存（共享，api ↔ render 同法）**：源素材字节全机只下载一次。缓存路径律 = `sha1(规范化对象 key)` 落 `$TMPDIR/repurposer-source-cache/`，Python 侧 `providers/storage.source_cache_path` 与 Node 侧 `apps/render/src/stage.ts cachePathFor` 镜像同一律法（带 key 按 key 哈希，无 key 回退按 URL 哈希）；`download_to_cache(key)` 为唯一取字节入口（LRU touch 命中、inflight Future 去重并发下载、4GB 最旧 mtime 逐出）。api 侧消费方：处理链预下载 / content_hash / ASR / prosody / extraction / reframe 全部走它；render 侧经渲染载荷 envelope 字段 `source_key`（非 clip-spec）拿到 key，staging 命中链上已下载的字节 = 零网络。上传永不经缓存，上传也永不走下载代理通道。
- **EU 数据驻留**：project 级 `data_region` 是未来差异化（PROGRESS 明确不在本周期），未实现。
- **UI 语言**：root loader 在服务端读取 `repurposer-lang` cookie，SSR 与首客户端渲染使用同一 per-request i18n 实例；API 侧将当前 UI 语言钉入 request context / run.context。只有明确用户动作可切换语言，不做 hydration 后自动切换。
