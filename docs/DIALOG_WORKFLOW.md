# Repurposer Dialog Workflow — 对话到生产

> Status: 当前概念规范（2026-10-25）。实现细节与实时状态分别以 `CHAT_ARCHITECTURE.md`、`AGENT_ARCHITECTURE.md` 和 `PROGRESS.md` 为准。
>
> 本文定义对话引擎、brief、计划和生产引擎之间的边界；不记录交互迁移过程，也不把目标架构写成已落地能力。

## 1. 核心模型

对用户，这是一个持续的 assistant；对实现，它是**事件驱动的对话状态机 + 编译后执行的生产 DAG**。

```text
用户消息 / 附件 / mentions
  → POST /chat（唯一意图面）
  → 有界 ToolLoopAgent（读世界 → 一个终态动作）
  → answer / ask_user / present_plan / start_run / 修订提案
  → 持久 Product Graph 与 Decision Package
  → create_run 唯一执行出生地
  → compile_graph → Postgres queue → worker → 真实 outputs
```

对话不能编译进 DAG：对话轮数由人决定，生产拓扑、报价和执行顺序必须在启动时可判定。两引擎通过已呈现的计划、持久图和授权范围连接，而不是通过共享一段 prompt 文本连接。

## 2. 概念与边界

### 2.1 厚 assistant，非开放式 autonomy

- 会话层使用有界工具 loop：模型可调用只读工具，终态工具一次调用结束该 loop；护栏在工具执行内。
- 生产层由代码编译拓扑、worker 执行；模型不得直接写数据库、自由改拓扑或启动无界执行 loop。
- “LLM proposes, code decides”适用于 brief、任务链、wiring ops、编辑 ops、报价与启动校验。
- 用户可见名称遵循展示文案二源律；内部步骤写工艺，不包装成虚拟团队或人格角色。

### 2.2 双引擎

| | 对话引擎 | 生产引擎 |
|---|---|---|
| 形态 | 事件驱动状态机 | 编译 DAG |
| 状态 | brief、pending plan、questions、presented versions | graph、run、steps、outputs、ledger |
| 环境 | 用户可多轮回答、修改、拒绝 | worker 认领有界任务 |
| 保证 | 单一待决座、来源化合并、可恢复 dock | compile 校验、报价 fold、topo 执行、终态身份 |
| 接口 | 已呈现计划与授权范围 | `create_run` 唯一出生地 |

`pending_brief` 是当前计划恢复状态，不是画布 document/task_book 节点。用户言语在 messages，任务链与产物关系在 graph，确认在 dock；不得再造合成 transcript/task_book 节点或边。

### 2.3 Router 与两条路径

- plan path 处理首个 run 前的计划、回答 slot 后的续判和待确认计划；chat path 处理已有 run 项目的新工作、精确编辑和图修订。
- 两者都是同一个 `POST /chat` 内的状态分派，不是两个 API 意图入口。
- 当前物理实现保留 `intent_router` 与 `chat_intent_agent` 两个实例；共享概念与提问语义，不为“概念合一”强行合并 schema/装配。
- 具体终态工具集以 `CHAT_ARCHITECTURE.md` §3 和当前 registry 为准；目标架构不得提前退役仍在使用的 `propose_tasks`、`edit_graph`、`select_clips`。

### 2.4 Brief

`projects.pending_brief` 中的 brief 保存对话工作状态的咨询性部分：

- `topic` / `audience` / `tone` / `material_state` 与来源化 `constraints[]`；任务链、derived、授权事实按当前 `PendingPlan` schema 保存。
- 槽位来源为 `user-stated` / `inferred` / `default`；代码合并优先级为 user-stated > inferred > default，用户重申优先。
- `asked` 与 material state 由代码依据真实世界维护，不能由模型反向覆盖。
- brief 是主压缩件，recent messages 保留必要语境；不能把累积 prompt 当作唯一事实源。
- brief 关键执行载荷仍严格校验；咨询性字段不可辨认时读容忍，不因记录损坏杀死整个回合。

### 2.5 计划与图

- 计划是技能链及其用户可理解投影，不是冻结文案模板，也不是 DAG 的直接序列化展示。
- `present_plan` 干跑编译以生成 derived 预览，并持久化 Decision Package；自身不执行付费工作。
- 图是唯一持久产品对象；chat 图修订经 `apply_wiring_ops` 唯一写口，精确产物修改走当前 edit operations。
- 面板手改与 chat 修订都必须更新当前计划事实；旧确认不得静默授权新范围。
- transcript 是资产内容，不是 graph node；legacy 迁移必须先保留 `edited_text` 到 asset overlay，再删除旧节点/边。

### 2.6 有界 loop 节点

需要搜索、阅读或不可预知步数的生产节点时，可使用有界 loop，但必须满足：

1. 节点声明迭代/时间/调用上限；
2. 报价包含上限语义，不可报价时进入 NULL/守卫线；
3. 对外仍是 DAG 的一个节点，拓扑、SSE、计量与重试不获得旁路。

节点内环不能扩张成模型驱动的全图编排。chat ToolLoopAgent 是另一座有界 loop，不适用生产节点的报价形状，但同样必须有界。

## 3. Canonical 词汇

| 概念 | 词 |
|---|---|
| chat 边缘意图调用 | router / intent router |
| 分任务调用 | plan |
| 素材理解 | understand |
| 图执行单位 | node / step |
| 对话状态 | brief |
| 会话回合机器 | ToolLoopAgent / 有界工具 loop |
| 模型动作 | 终态工具调用 |
| 嵌套自主性 | 有界 loop 节点 |
| 用户待确认对象 | Decision Package / presented plan |
| 已授权执行范围 | confirmed scope |

`plan` 在 chat 计划与 pipeline planner 两个语境中使用；存储键和 registry 名以代码现状为准，不为概念统一批量改名。新词先过 `NAMING.md`。

## 4. 对话工作流

### 4.1 提问

`ask_user` 是一等终态工具：

- 每轮最多一个决定质量的问题；选项一词可答，freeform 始终可用。
- 每个问题带机器可读 `default_path`；它只骑参数，散文和 dock 不宣告默认路径。
- 选项问进入 dock；文字问是普通消息。输入、铅笔自由输入、跳过、提醒和恢复行为归 `CHAT_ARCHITECTURE.md`。
- 只问用户能回答且会改变计划的事，如目的、听众、主题；技术参数由配方与默认值吸收。
- 素材未读完不得预写方案；无法完成时给理由与可行替代，不静默拒绝。

### 4.2 计划门槛

`present_plan` 在执行内校验 brief 是否有根：topic、真实素材或明确具体的制作请求至少其一。

- 无根时先问主题；问过仍无根或用户跳过后，可走代码明确标记的 `draft_from_persona` 路径。模型推断不等于用户已给主题。
- 需要 media 的任务在没有素材/贴文且桌上无计划时，必须请求素材，不得 dock 不可执行计划。
- 纯文本生成请求与“用户贴入自己的内容”由 LLM 语境判断，禁长度启发式；内容可提升为 transcript 资产。
- 计划呈现不等于制作授权。`production_intent` 是 dock 工具的出生事实，缺失时安全侧挂起。

### 4.3 授权与 Start

- `auto` 只免普通批准拍，不创造制作意图；无制作请求、纯修改或“先看方案”任何档都等待用户发话。
- `ask` 档在 dock 后等待朴素方案判断问句的一词回答；口头 yes 与 Start 钮走同一机器。
- Start 必须针对当前已呈现计划与 confirmed scope；确认复述累计方案、未选项和未清项，旧 yes 不授权新稿。
- `billing.always_confirm_above` 与 NULL 不可报价族任何档都要带价确认。
- 付费执行只从 `create_run` 出生；出生地再次校验素材、报价、scope、活跃 run 与执行身份。
- Film 首稿必须先完整呈现分镜并等待用户看后明确生产；auto、开场“直接做”和 `review_hold=false` 都不能绕过。后续版本按 Film 当前版本合同处理。

### 4.4 上下文与失败

- 装配只携带当前 brief、presented plan/version、真实素材摘要、必要最近消息和工具读数。
- provider 失败不得 dock 编造默认计划；错误进入当前回合失败形态，不产生可 Start 的假计划。
- 工具拒绝只返回世界事实与应遵守的合同座位，不携带可被模型复述的回复草稿。
- 计划/提问散文遵守打字机律；DeferredFrames 拒绝时零预览、零提交，checkpoint 后仍 armed。

## 5. 计划呈现

- dock 呈现当前真实任务链、关键参数、产物预览、成功定义、报价与授权状态；没有空 brief 表单或第二套执行表单。
- 卡片是已填计划的呈现，不是让用户从零创作的起点。
- 不使用 `chain >= 2` 决定是否有确认卡；单任务与多任务都按同一 Decision Package、制作意图和授权规则处理。
- 用户可改任务参数、删除任务、通过 chat 修改；任何手改清除 LLM 命名，显示回退到当前参数的诚实标签。
- Start、bail、修订与恢复共享同一持久计划身份；不得为单任务另造纯散文执行旁路。

## 6. 不变量

- `POST /chat` 是唯一意图面；`create_run` 是唯一 run 出生地。
- `apply_wiring_ops` 是唯一图写口；拓扑由代码裁决。
- clips need media 在 intent 与出生地双重 enforce。
- 报价 = fold、执行 = topo、校验覆盖每个节点、对账检查声明与真实图。
- clip-spec 与 film-spec 是平级渲染契约，按 `spec.family` 分派；renderer 概念不进入 spec。
- 只有一个待决 dock 座；文字问与选项问形态不混用。
- 所有散文走打字机节拍；整段瞬移与静默预览拒绝都禁止。
- auto/ask、制作意图、守卫线、Film 首稿和 versioned Start 不得互相绕过。
- 开放式执行 loop、模型自主改拓扑、无界重试和直接 LLM 数据库写入永禁。

## 7. 行为验收

- 裸愿望先得到可一词回答的问题或合法 draft-from-persona 路径，不得到空心计划。
- 无素材 clips 请求在 intent 与 `create_run` 都被拒绝；copy-writer 合法无素材路径不受影响。
- 单任务与多任务使用同一确认和报价机器；修改后旧授权不覆盖新范围。
- auto/ask、无制作意图、守卫线和 NULL 报价分别验收；Film 首稿未经呈现不能 Start。
- 刷新、拒绝、断流与恢复后，brief、计划、dock、版本和消息顺序一致。
- 生产节点若含有界 loop，上限、报价、拓扑和失败行为均可观察。
- 自动剧本只锁服务端真值和形态；客户端打字机、remount 与 dock 形态另做浏览器验收。

## 8. 当前参数与实现选择

- **开放参数**：槽位提问顺序与几轮后出计划仍需真实对话数据校准；调整不得破坏每轮一问、可跳过和计划门槛。
- **当前实现选择**：router 两相位保留双实例。只有联合 schema 不扩大非法动作空间、assemble 纯度与 prompt 隔离有等价保证时，才重新评估合并。
