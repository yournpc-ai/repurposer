# Workspace v4.2 差距审计（上批 · 数据/链路）

> 基线：`scratch/workspace-model-v3.html`（Workspace 空间模型合同 v4.2，2026-09-26 封板）。
> 本表是唯一施工地图：合同条款 × 当前实现（文件：行）× 差距 × 修改范围 × 状态。下部会话按此表继续，不从代码反推产品模型。
> 状态词：✅ 符合 / 🔧 本批已改（未跑验证）/ ⬇️ 下部待改 / 👀 符合但需观察。
> 施工位置：上批 = worktree `.claude/worktrees/ws-v42-upper` 分支 `ws-v42-upper`（基线 `35c4997`）；**下部 = 分支 `ws-v42-lower`（自 `2602fb9` 起）**，交接区第二节起为下部落账。

## 施工范围总表

| # | 合同条款 | 当前实现 | 差距 | 修改范围 | 状态 |
|---|---|---|---|---|---|
| C1-a | Candidate / Selection / Preview 永不进 Graph；旧模型（Candidate Set / Select / Content Plan 三种探索泳道节点）**代码级删除**，不是读面隐藏 | 探索族作为 `graph_nodes` 的 `type="exploration"` 行持久化（ADR-088 拍板时如此），经 `exploration_store.py` 四动词写入（L446-525 / L528-582 / L585-644 / L966-1082），客户端唯一可见面 = 画布卡（`FlowNodeCard.tsx:499-690` 三种卡 + `layout.ts:40-49` 泳道尺寸镜像 + `projects.py:350-354` 读面直传） | 持久化位置违反合同：探索泳道节点必须不再产生；数据链需迁出 Graph 供 chat Candidate Surface 使用 | `graph_nodes` → 新表 `exploration_rows`（数据/链路迁址，本批）；画布读面/卡片/布局下线（本批）；chat Candidate Surface UI（⬇️ 下部） | 🔧 本批已改 |
| C1-b | 伴侣文档（字幕文档）资格上限：独立身份/可查看/可编辑才进图；纯装配中间产物永不入图 | 字幕两站已存在（asm video×editor + doc table×manual，`doc_node_id` 链，ADR-072/076）；`task_book` 文档仍 stamping、仅 B1-lite 读面过滤（`projects.py:413-431`） | task_book 节点是「实现需要入图」的反例——合同要求不 stamp，不是读面隐藏 | task_book 节点 de-stamp + 存量清理 | 🔧 下部已改 |
| C2-a | 两种 Graph Birth 分离：Entity Birth（上传即落）≠ Promotion（唯一晋升口） | `stamp_asset_node` / `stamp_transcript_node` 上传即落（`graph_fill.py:235-394`）；draft work 经 `stamp_draft_graph` dock 即 stamp | 符合；Promotion 语义由 plan dock 承担 | 无 | ✅ |
| C2-b | Revision ≠ New Work ≠ New Product 三分；改同一作品 = 同 identity 新 version；「再做一个不同的」= 新 Work entity 向右长 | ADR-091 已实施：rerun = 归档旧 version + 新 version（`work_id` 继承），wipe 点已改归档写；新作品经 wiring `add_node` 生新节点 | 身份语义已立；「再做一个…」路由是否稳定产新节点（而非塞进 pager）依赖 LLM 提案 + wiring 门，需野外观察 | 无本批改动 | 👀 |
| C2-c | Settled append-only：跨授权门后失败/重试不删 Work；Provisional draft 可弃 | 失败节点保留（ADR-074 失败判决 + 卡内红 face）；bail 拆 draft（`clear_draft_graph`） | 符合 | 无 | ✅ |
| C3 | Workspace Birth 三事实分离：graph entity 存在（不动）/ `workspaceBorn` 独立 presentation 谓词 / PLAN_READY（不动）。桌面翻转 = 首个非 Source workspace entity 存在（今天 = transcript processing 卡）；移动端 run-driven | `projects.$id.index.tsx:253-258`：`graphLive = hasRuns \|\| isPlanReady(lifecycle)`——画布出生绑在 run/PLAN_READY 上，T0~T1（上传→转写中）整段没有画布 | 谓词错位：上传后 transcript 卡已存在（数据事实）但画布不示人 | `projects.$id.index.tsx`：`graphLive` → `workspaceBorn`（graph 首个非 Source 实体：无 asset dossier 且非 exploration 旧行）；ADR-056/057 K5 注释处加翻案注 | 🔧 本批已改 |
| C4 | Evidence 锚链 + Transcript 双层；用户可直改文字（canvas 直改 / chat 同一写口），text changed / evidence unchanged / range unchanged | 锚链不变量在探索写门（`member_issues` 逐字校验）；Transcript 卡在画布只读（document 卡 prototype=manual 无程序区），直改写口不存在 | Transcript 直接编辑写口（同一实体、版本演进语义）未建 | 转写稿卡直改 + 写口（写口形态已拍板 = 卡内就地编辑，2026-09-26） | 🔧 下部已改 |
| C5 | Camera = ensure-in-view 一条：已在安全区不动 / 不在最小 pan / zoom 永不自动 / 唯一自动节拍 = Workspace Birth 的 initial fit；「draft 到达→整链 fitNow」**不入合同** | 相机节拍族（2026-09-14 C6 批 + 2026-09-25 拍板）：`cameraBeat` fit / pan / fitNow 三种 armed beats（`projects.$id.index.tsx:324-345, 1131-1164`），含 onPlanConfirmVisible 的 fitNow | fitNow 节拍与 v4.2 直接冲突；其余 beats 需收窄为 ensure-in-view 语义 | 相机律重写：删 fitNow（**2026-09-26 已拍板翻案 09-25 拍板**，见未覆盖 #3）；beats 收窄；新增「当前操作元素移到画布中心」方法供前端/agent 调用 | 🔧 下部已改 |
| C6 | Layout Island：sibling group 出生定格 origin/size（容量预留 + 增长廊道），岛零 UI，overlap 结构性不可能 | 定居取景 append-only（`graph_store._assign_layout` + `layout.ts` GAP_MAIN/GAP_CROSS/FRESH_COLUMN_RISE 镜像）；无「组容量/廊道」概念 | 岛模型未建（数据：节点 group 归属 + 容量参数；律：出生定格 bounding） | 布局岛数据结构与摆位律 | 🔧 下部已改 |
| C7 | Motion 三语义固定（edge arrival / node birth / node working），禁第四种 | birth stagger（BIRTH_STAGGER_MS）/ 边 draw-on / running wipe 均在；focus 族已退役（ADR-058） | 符合 | 无 | ✅ |
| C8-a | 授权门 server 接线：confirm_strategy ∈ always / large（高端过 `billing.confirm_large_threshold`）/ never，门控在 server 侧读 `users.settings`；不落拍 = 直接执行 + 正文披露执行范围与估价 | ADR-092 S4 已落：settings API + 阈值 config + **前端** dock 披露分级（`ChatDock.tsx:3777-3782`）——策略只调披露强度，dock 恒弹；server 侧门控不存在（合同原文已标注「行为接线是后续批」） | server 侧策略门缺失 | `user_settings.py` 纯律 + `service.py` 装配器；`propose_turn._propose_tasks` / `_run_wiring_proposal` expansion 分支 / `plan_turn._present_plan` 三落点接线；直执 = dock + 同事务 instant start（复用 Start 全部机器：gate / snapshot / mark_compiled），正文附确定性披露行 | 🔧 本批已改 |
| C8-b | 确认拍归档 = 普通用户气泡：dock Start pill 点击等同代用户输入「确认生成」（走唯一 sendChat 通道）；QA 块对 start 类退役 | Start pill POST `/chat/messages/{id}/answer` kind=start（`ChatDock.tsx:1777-1784`）——无用户气泡；QA 归档已于 2026-09-05 拍板退役（replay 不回放，`historyReplay.ts:379-398`），但 `AnsweredQuestion.tsx:43-50` 的 start 分支仍在 | pill 手势不产生用户气泡（合同要求消息流 = 用户气泡 + agent 开工散文） | `ChatDock.handleStartGeneration` 改走 sendChat（plan path `start_run` 工具既有 G-1 链路）；`answeredQuestionText` start 分支删除；新增 i18n key | 🔧 本批已改 |
| C8-c | Candidate Surface 默认 3 推荐 + 全量展开；ordinal 是地址；chat 决策永不成节点 | chat 内候选面不存在（候选只在画布卡）；`candidates_observation` 等 observation 是 LLM 面 | chat Candidate Surface UI + 选择态表达（高亮）未建；数据链已备妥（消息载：tool observations + dock payloads 全量持久化，刷新可重建——见未覆盖 #1 修订） | Surface UI + 选择态表达（高亮） | 🔧 下部已改 |
| 封板① | T0 上传 Source 仍是 Chat world | 现 `graphLive` 下成立（无 run 无 plan = fullscreen chat）；本批 C3 改后：无 text yield 的素材（纯图片）依然成立；ASR 素材 T1 即出生 | 符合（合同绑的是 transcript processing 卡同帧，纯图片项目的出生顺延到首个 draft/work 节点） | 无 | ✅ |
| 封板⑤ | Settled 只长不消，provisional draft 可弃 | 见 C2-c | 符合 | 无 | ✅ |

## 合同未覆盖 / 与合同冲突登记

1. **Candidate Surface 的数据传输形态合同未定**（chat 内联卡片的数据从哪来）。**本批取证结论（修订）**：数据链**全程消息载**，无需新端点——live 回合走 SSE 帧族（tool observations），刷新/跨设备重建走持久化载荷（`messages.intent` 的提案转储 + dock `question.plans` 阅读层，DecisionPlanRow 先例）；删除画布卡后客户端没有任何按行查询探索族的座位。**本批未建** `GET /projects/{id}/exploration`（原拟最小补丁，取证后判定为发明性 API 面）。**下部 T6 收口**：候选面数据链全程消息载落地（`assistant.candidates` SSE 帧族 + `candidates_log` 持久化行），无需任何端点——跨回合回看由消息回放折叠承担；该只读帧永久关闭（除非未来出现消息流之外的候选面座位）。
2. **策略直执的 Confirmed Scope Snapshot 通道词**：`confirmed_via` 现有 `dock_pill` / `chat_reply` 两词（ADR-089 R20）。直执拍本批新增第三词 `policy_direct`（快照必须能区分「用户没看过就开工」与「用户点了确认」——对账与 revision router 的诚实地基）。合同未列词表，按命名纪律登记于此。
3. **C5 fitNow 冲突——已拍板（2026-09-26）**：2026-09-25「确认 pill 首现 = 整链 fitNow」**翻案**，以封板合同为准——删 `onPlanConfirmVisible` 的 fitNow 节拍，draft 到达不做整链 fit。相机能力升级方向（同拍）：提供「**把当前操作元素移到画布中心**」的方法供前端/agent 调用（既有 `setCenter` 平移锁 zoom 语义族，`projects.$id.index.tsx` 相机节拍座位），ensure-in-view 的最小 pan 收敛到这条方法上；zoom 永不自动不变。
4. **large 档估价 NULL 的口径**——已拍板（2026-09-26，随本批安全默认生效）：估价不可报（编译期量未知）时无法与阈值比较，取保守档（落 dock），与「unproven → dock」同族。下部不改。
5. **探索行不随素材删除级联**（现状如此，迁表后保持）：candidate_set spec 引用 asset_id，素材删除后候选悬空。候选是瞬时决策材料，合同语义下可接受；如下部建 Surface，需在读面容忍悬空（range 行诚实留空，既有 SelectCard 先例）。
6. **剧本与 pure 测试的旧座位引用**：`tests/test_exploration_*_pure.py`（store / compile 两套件）+ `test_revise_selects_pure.py` + `test_memory_narrow_pure.py` 的桩与种子本批已机械换座 `ExplorationRow`（删泳道测试与 type/layout 断言；memory_narrow 桩 get 加 isinstance 守卫）——import 面冷探针通过，**未跑 pytest**（用户验证）。`scripts/chat_scenarios.py` 未动：s23 探索段（`s23_exploration_chain_lands_on_canvas` 及其车道/rank/零边断言，~L4059-4547）对「读过滤后的 /graph + 新表」**已知破损**，由用户验证批决定重指或修剪。
7. **wiring expansion 直执路径无 Confirmed Scope Snapshot——已拍板（2026-09-26）：补。** plan/propose 两路的直执走 dock + 同事务 `answer_question`，快照随 Start 机器落戳（`confirmed_via="policy_direct"`）；但 `_run_wiring_proposal` 的 expansion 直执经 `_create_run_from_tasks` 产 run，无 question 行可挂 `confirmation_id`，run.context 缺 `confirmed_scope`（与 continuation 同形——continuation 本就不要快照，expansion 直执是「常驻策略授权的新付费边界」，语义上该有）。**下部施工补丁（已落地，🔧）**：直执产后在 run.context 补戳（`confirmed_via="policy_direct"`，confirmation_id = 落盘 assistant message id，quote = 门算的 estimate），与 dock 路快照同一形状（读面零分叉）。
8. **caption-mode 问题 × never 策略的叠加——已拍板（2026-09-26）：接受安全默认。** caption 问是真 slot 问（内容选择），不是确认拍——策略门**不跳过**它；回答后 caption 快径重落 task_book 仍出现确认拍（never 用户多一拍）。维持落拍；「caption 答案并入直执链」的免拍变体不做（属交互变更）。

---

## 交接区

> 下部会话施工按本区与总表走，不从代码反推产品模型。行号以 worktree `ws-v42-upper` 分支交付 commit 为准（基线 `35c4997` 之上）。

### 一、本批改动清单（file:line × 一句话理由）

**A. Candidate 旧模型代码级删除（探索族迁址 `exploration_rows`）**

| 文件：行 | 改动 | 理由 |
|---|---|---|
| `apps/api/app/models/tables.py:358-393` | 新增 `ExplorationRow` 模型（id / project_id / journey_id / state / spec + 时间戳；**无 type 无 layout**） | v4.2 C1：探索族的家不是 Graph——家族即表，无画布座位 |
| `apps/api/migrations/versions/k1a4b7c3d4e5_add_exploration_rows.py`（新） | 建表迁移，down_revision=`j9f3a6b24c38`；legacy 图行**不迁移** | 生产止产生 + 存量读过滤即满足 C1；迁移在既有库上**未实证** |
| `apps/api/app/pipeline/exploration_store.py` 全文件 | 四动词 + 全部读座从 `GraphNode` 换座 `ExplorationRow`；删泳道律（`_EXPLORATION_FRAME` / `_EXPLORATION_LANE_X=-464` / `_LANE_GAP_Y` / `exploration_lane_frame`）与构造器 `type=`/`layout=`；docstring 现在时改写 | 泳道节点停止产生（stamping 下线）；chat 数据链（observations/dock payloads）形状不变 |
| `apps/api/app/chat/exploration_compile.py:29,99-111` | select 行查询换座 `ExplorationRow`（去 type 过滤） | 编译器读新表 |
| `apps/api/app/chat/perception/executes.py:36-56,974-980,1007` | `get_artifact` 改读 `ExplorationRow`（`GraphNode` import 保留给 L337 的图读工具） | 读洞随迁址 |
| `apps/api/app/chat/context.py:86-107,115-120` | context 图块查询过滤 legacy exploration 行 + 删 exploration 标签分支 | agent 语境的 Graph 块同样不进探索族（C1）；journey digest 块保留（读新表） |
| `apps/api/app/pipeline/routes/projects.py:52,346-349,405-413,619-624` | `/graph` 读过滤 legacy exploration 行；`_read_face` 删 exploration 直传分支；`GraphNodeResponse` 构造删 `journey_id` | 读面下线（B1-lite task_book 过滤先例） |
| `apps/api/app/models/schemas.py:3560` | `GraphNodeResponse.journey_id` 字段删除 | 画布无探索族后该字段恒 NULL |
| `apps/api/app/pipeline/product_graph.py:80-89` | `EXPLORATION_*` 词注释现在时改写（词**保留**） | 两词剩两个座位：legacy 行读过滤 + 执行写门反门卫兵 |
| `apps/web/src/components/flow/FlowNodeCard.tsx` | 删 `ExplorationCard`/`CandidateSetCard`/`SelectCard`/`ContentPlanCard`/`formatTimestamp`（约 200 行）+ 分发链的 exploration 分支 + 关联 import（`Badge`/`BadgeCheck`/`ClipboardList`/`ListChecks`/`EXPLORATION_MEMBER_LIST_PX`/两个 spec 类型） | Judgment/Candidate Set/已选三节点形态代码级删除 |
| `apps/web/src/components/flow/flow.css:232-238` | 删 `.exploration-card-open` 规则 | 合集卡展开态随卡删除 |
| `apps/web/src/components/flow/layout.ts` | 删 `FLOW_NODE_SIZE.exploration` + `EXPLORATION_NODE_SIZE` + `EXPLORATION_MEMBER_LIST_PX` + `graphNodeSize` exploration 分支 | 布局镜像随卡删除（`FLOW_NODE_SIZE` 为 `Record<FlowNodeKind,…>`，探索键在类型上已非法） |
| `apps/web/src/components/flow/layout.test.ts` | 删 exploration family describe 套件（lane 投影/零边/尺寸镜像三例） | 被测对象已删 |
| `apps/web/src/components/flow/types.ts:36-43,121-129` | `FlowNodeStatus` 收窄为 `GraphNodeState`；删 `FlowNode.journeyId` / `FlowNode.evidenceRange` | 第二状态词表与证据投影随族删除 |
| `apps/web/src/components/flow/ResultsCanvas.tsx:202-219,244-245` | 删 Select 证据区间读时投影 + `journeyId` passthrough | R7 投影随卡删除 |
| `apps/web/src/lib/types.ts:263-287,298-307,371-406` | `GraphNodeType` 删 `"exploration"`；删 `ExplorationNodeState`/`ExplorationKind`/`ExplorationMember`/`ExplorationPlanOutput`；`GraphNode` 删 `journey_id` | 词表 v3 回七值 |
| `apps/web/src/lib/i18n/locales/en.ts:1125-1155` + `zh.ts:1071-1099` | 删 `nodeType.exploration` 与 `results.canvas.exploration` 整块 | 全 src 零消费方（grep 实证） |
| `apps/api/tests/test_exploration_store_pure.py`、`test_revise_selects_pure.py`、`test_exploration_compile_pure.py`、`test_memory_narrow_pure.py` | 桩/种子换座 `ExplorationRow`；删泳道测试与 type/layout 断言；memory_narrow 桩 `get` 加 isinstance 守卫（误物种测试存活） | pure 套件与迁址对齐（**未跑 pytest**） |
| `apps/api/scripts/chat_scenarios.py` | **未动** | s23 探索段（~L4059-4547）已知破损，登记于未覆盖 #6 |

**B. Workspace Birth 谓词**

| 文件：行 | 改动 | 理由 |
|---|---|---|
| `apps/web/src/routes/projects.$id.index.tsx:241-263` 及全部 `graphLive` 引用 | `graphLive`（`hasRuns \|\| isPlanReady`）→ `workspaceBorn`（graph 首个非 Source 实体：`n.asset == null`）；`isPlanReady` import 移除；翻案注加在 ADR-056/057 K5 注释座位 | v4.2 C3：三事实分离，画布出生不再等 run/PLAN_READY；C1 后 exploration 排除从谓词移除（读面已过滤，类型上不可比） |

**C. 授权门 server 接线（ADR-092 目标语义）**

| 文件：行 | 改动 | 理由 |
|---|---|---|
| `apps/api/app/platform/user_settings.py:33-56` | 新增 `confirmation_required(strategy, high_credits, threshold)` 纯律 | 三档门（always→落拍 / never→直执 / large→估价 NULL 保守落拍，高端过阈落拍） |
| `apps/api/app/chat/service.py:395-443` | `_confirmation_policy`（读 users.settings）/ `_confirmation_required`（读 configs `billing.confirm_large_threshold`）/ `_policy_direct_disclosure`（zh/en 确定性披露行） | 付费边界永不骑客户端状态；不询问 ≠ 不披露 |
| `apps/api/app/chat/propose_turn.py:491-535` | `_propose_tasks` 授权门：直执 = dock + 同事务 `answer_question(kind="start", intent=None, confirmed_via="policy_direct")` | Start 全部机器（gate/draft 重戳/快照/mark_compiled）同构运行；拍不渲染 |
| `apps/api/app/chat/propose_turn.py:566,623` | `_dock_plan_as_question` 加 `estimate` 透传参（sentinel 缺省 = 重算） | 门算过的估价不重复 fold |
| `apps/api/app/chat/propose_turn.py:1006-1135` | `_run_wiring_proposal._dispatch` 返回 `(run_id, direct_disclosure)`；expansion 分支读门（落拍=rollback + dock 带估价 / 直执=commit + 披露行）；落盘散文附披露 | 修订链的 expansion 同样过授权门 |
| `apps/api/app/chat/plan_turn.py:594-641`（两共享半门）、`870-872,915-919`（`_present_plan`）、`1027-1028,1092-1096`（`_propose_plans`）、`1165-1166,1229-1233`（`_redock_journey_package`） | `_policy_direct_disclosure_for` / `_answer_docked_direct` + 三 dock 落点接线：门前半披露骑 echo + `intent.answer`，门后半同事务直执 | plan path 每个 dock 确认拍一条律，都读 server 策略 |

**D. 确认拍归档 = 用户气泡**

| 文件：行 | 改动 | 理由 |
|---|---|---|
| `apps/web/src/components/chat/ChatDock.tsx` `handleStartGeneration` | 由 `useCallback` 改普通 async 函数（deps 引用后置 `sendChat` 会 TDZ 崩溃）；`pendingQuestion` 分支改走 `sendChat(t("generationOverlay.confirmUserMessage"))`（乐观用户气泡 + `rollbackId` + `raiseHistory` + `scrollerSendRef`）；`/generate` legacy 回退分支保留 | v4.2 C8：pill 点击 = 代用户输入「确认生成」，走唯一 sendChat 通道（G-1 链路复用：回声行 → plan path `start_run` → `confirmed_via="chat_reply"`；panel 编辑经 `prior_intent` 保留） |
| `apps/web/src/components/chat/AnsweredQuestion.tsx:43-50` | `answeredQuestionText` start 分支删除（留退役注） | start 类 QA 归档退役（气泡即归档） |
| `apps/web/src/lib/i18n/locales/en.ts` + `zh.ts` | + `generationOverlay.confirmUserMessage`（en "Confirm and generate" / zh "确认生成"）；− `chat.qa.started` | en 先行镜像 zh；零消费方键删除 |

### 二、未跑验证声明（全部行为改动 —— 不跑测试 / 不起服务 / 不跑剧本，用户自验）

已做的**静态**核对：改动 .py 全部 `py_compile` 通过；冷导入探针通过（app 侧 10 模块 + 迁移文件 + 6 个 pure 套件 import 面，含 `ExplorationRow` 存在性、泳道律删除、两半门存在性断言）；web 全 src grep 零残留（exploration / journeyId / evidenceRange / 删除的 i18n 键）。**web 侧 tsc 未跑**（worktree 无 node_modules）；**pytest 未跑**；**迁移未在真实 DB 上 upgrade/downgrade**。

重点未验证行为面：

1. 授权门直执三路端到端：never 策略零拍开工 + 披露行出现；large 过阈/估价 NULL 落拍；always 恒落拍。
2. 直执路径「同事务内 dock 未提交行 + `answer_question` 的 `with_for_update` 读取」的可见性（同 session 理论可见，未实证）；`answered.workflow_run_id` 在同事务内的读取。
3. `confirmed_via="policy_direct"` 快照落戳与 revision router 读面；wiring expansion 直执无快照（未覆盖 #7，已拍板=下部补戳）。
4. `workspaceBorn` 翻转节拍：ASR 素材上传后 transcript 卡 queued 帧画布即出生；纯图片项目出生顺延至首个 draft/work 节点；移动端仍 run-driven；老项目（有 runs）首帧不重放形态机动画。
5. Start pill → sendChat「确认生成」全链：乐观气泡、SSE 回声行、plan path `start_run`、失败回滚；credits.insufficient 灰行；panel 编辑经 `prior_intent` 保留。
6. `exploration_rows` 迁移后：legacy 图行读过滤（画布/context 不再出现探索卡）；journey digest、`get_artifact`、compile_plans_package、mark_compiled/supersede 读新表；propose_candidates 幂等重放。
7. `graph_nodes.journey_id` 列保留（legacy 行 + SET NULL FK），未删列——属后续清理，合同未要求。

**prompt 面**：本批未动 `app/prompts/` 任何文件，prompt_gate 无需重跑（C8 披露行是代码确定性文案，不进 prompt）。

### 三、合同未覆盖补充——全部已拍板（2026-09-26）

见上文登记表：**#3**（fitNow 翻案，删 `onPlanConfirmVisible` 节拍；相机升级为「当前操作元素移到画布中心」方法，供前端/agent 调用）、**#4**（large 档估价 NULL 保守落拍，不改）、**#7**（wiring expansion 直执补 confirmed_scope 快照，下部施工）、**#8**（caption × never 维持落拍安全默认，不做免拍变体）。仍开放的只有 **#1**（消息载够用，端点未建——下部 Surface UI 若确需跨回合回看再立只读帧）、**#6**（剧本 s23 破损，用户验证批决定重指或修剪）。

### 四、给下部的一句话提醒

`ChatDock.tsx` 本批只动了 `handleStartGeneration`（`useCallback` → 普通 async 函数 + `pendingQuestion` 分支换 sendChat 通道，同函数内 `/generate` 回退分支保留），17 文件批次的其余块未触碰；`exploration_store.py` 已整体换座 `exploration_rows` 且**泳道律（x=−464 一族）删除**，下部建 Candidate Surface 时从消息载数据链读（端点未建，见未覆盖 #1），别再引用泳道常数；`scripts/chat_scenarios.py` s23 探索段已知破损待修剪。

---

## 下部交接（2026-09-26，branch `ws-v42-lower` 自 2602fb9 起）

T1~T6 已收口。上部改的是「授权门 + 数据迁址 + 出生节拍」，下部补的是「快照补戳 + task_book 资格上限 + Transcript 直改 + 相机律重写 + Layout Island + Candidate Surface」。

### 一、改动清单（commit × 文件：行 × 一句话理由）

**T1｜wiring expansion 直执补 Confirmed Scope 快照（7d07df6）——未覆盖 #7**

| 文件：行 | 改动 | 理由 |
|---|---|---|
| `apps/api/app/chat/propose_turn.py:1158-1170` | wiring expansion 直执分支补 `confirmed_scope` 快照落戳（`build_confirmed_scope(...)`，`confirmed_via="policy_direct"`） | 直执 = 授权拍语义等价物，快照缺失会让 revision router 读面拿不到 scope 边界 |
| `apps/api/app/pipeline/scope_compile.py` | `build_confirmed_scope` 支持 wiring 提案的 scope 折叠 | 同上 |

**T2｜C1-b task_book 节点 de-stamp + 存量硬删（9cd0391）**

| 文件：行 | 改动 | 理由 |
|---|---|---|
| `apps/api/app/pipeline/graph_fill.py` | task_book 节点出生/stamp 路径整体删除；伴侣文档资格上限收紧 | v4.2 C1-b：task_book 不是可再指认的 Product Entity，资格上限 = 伴侣文档只挂真实产物 |
| `apps/api/migrations/versions/l2b5c8e1f4a7_delete_task_book_nodes.py` | 存量 task_book 行硬删（含关联边） | 合同 = 代码级删除，不是读面隐藏 |
| `apps/api/app/chat/service.py` / `node_runners.py` / `orchestrator.py` / `product_graph.py` / `routes/projects.py` | task_book 分支/读面同步删除 | 一次性清净，不留兼容层 |

**T3｜C4 Transcript 直改写口（adce4c1 + aa80787）——用户拍板卡内就地编辑**

| 文件：行 | 改动 | 理由 |
|---|---|---|
| `apps/api/app/pipeline/graph_store.py:101-120` + `:1104` | 新增 `EditTextOp`（schema + 执行分支），挂 `WiringOp` union / `WIRING_OPS` / `wiring_catalog_lines` | 同一写口 = chat 唯一意图面；卡内直改 = 确定性手势，零 run 零 credits 零回声 |
| `apps/api/app/models/schemas.py` | `GraphEditTextRequest` / `GraphEditTextResponse`；`EditGraphArgs` 描述列 edit_text | 请求契约 + prompt 面登记 |
| `apps/api/app/pipeline/routes/projects.py:780` | `POST /{project_id}/graph/edit-text`——代码构建单 op 走 `apply_wiring_ops` | 确定性手势通道（ADR-058），不进 chat |
| `apps/api/app/chat/turn_tools.py` | edit_graph 工具描述枚举 edit_text（「只改用户可见文本层，源证据不动」） | chat path 继承同一 op 族 |
| `apps/web/src/components/flow/FlowNodeCard.tsx`（DocumentCard） | 卡内就地编辑：click-to-edit → textarea（Esc 取消 / ⌘Enter·blur 提交 / 「恢复原文」按钮）+ 乐观回显 | 零新 chrome——卡面本体即 affordance（合同 Δ2）；TextProductRegion 先例 |
| `apps/web/src/components/flow/layout.ts` | text 节点尺寸读 `edited_text ?? text` | 展示层镜像 |
| `apps/web/src/lib/types.ts` + `flow/types.ts` | `spec.edited_text?: string \| null`（C4 注释） | 双层语义：源证据永不动，展示层可覆写 |
| `apps/web/src/routes/projects.$id.index.tsx` | `handleTextEdit` useCallback → apiPost → 成功 `fetchGraph()` 回显 | 表面接线 |

**T4｜C5 相机律重写（b5e5d25）**

| 文件：行 | 改动 | 理由 |
|---|---|---|
| `apps/web/src/components/flow/FlowView.tsx:165-360` | CameraBeats 重写：`panLockedCenter` 唯一位移原语（锁 zoom）；ensure-in-view 单语义（安全区内不动 / 越区最小平移 / zoom 永不自动 fit）；新增 `centerRequest` 一次性居中 | 2026-09-26 翻案 09-25 的 fitNow 拍板——draft 到达 → 整链 fitNow 未入合同；收窄为 ensure-in-view；新增「把当前操作元素移到画布中心」能力供前端/agent 调用 |
| `apps/web/src/components/flow/types.ts` | `cameraBeat: {token} \| null`；`centerRequest` / `onCenterRequestConsumed` | 节拍形状收窄 |
| `apps/web/src/components/chat/ChatDock.tsx` | `onPlanConfirmVisible` prop 声明 / destructure / 触发 effect 全删（留退役注） | 确认拍不再触发相机移动（C5 判词） |
| `apps/web/src/routes/projects.$id.index.tsx` | cameraBeat state 收窄为 `{token}`；`requestCenterNode` 接线 handleOutputAction「focus」分支 + handleQuoteOutput 找节点 | 指认/引用手势 = 居中能力的首个消费方（零新 chrome） |

**T5｜C6 Layout Island（bcbdca7）**

| 文件：行 | 改动 | 理由 |
|---|---|---|
| `apps/api/app/models/tables.py:450` | `GraphIsland` 模型（depth / parent_ids JSONB / origin_x·y / row_h / cols / cap / created_at——无 updated_at，出生定格）+ `graph_nodes.island_id` / `island_seq` | C6 岛注册表：节点组成员资格 + 容量参数入档 |
| `apps/api/migrations/versions/m3c6d9f2a5b8_layout_islands.py` | 建表 + 两列 + 索引 + 命名 FK；无回填 | 岛 = 出生时刻注册，存量行无岛 |
| `apps/api/app/pipeline/graph_store.py:524-830` | `island_reserved_bottom()`；`_assign_islands()` 两段式（阶段一：家族分组 + join-or-birth + islands `flush()`——先于任何 member stamp，FK 保序；阶段二：retroactive sib 打座 + seat_of）；走廊钳位（deeper band 已落 → cols=1）；`settle_frames_with_edges` 改 async 收 `island_ctx`；`_assign_layout` 增 `x_slot` / `extra_tails` / `island_seat` | 出生定格摆位律：同 rank-edge 父集 + 同深度的兄弟族共享岛原点；容量预留 + 增长廊道；超容量（seq ≥ cols×cap）末列向下延伸（contact-sheet 留座不实现，用户拍板） |
| `apps/api/app/pipeline/product_graph.py:199` | `display_ranks(nodes, edges, islands)`——岛占 cols 个连续 rank 槽，`band_origin(d) = d + Σ(slots(b)−1)` | 客户端 x 律（rank × PITCH）不变；岛化只改 rank 投影 |
| `apps/api/app/pipeline/routes/projects.py` | 读面 preload islands；`display_ranks` 取代 `product_ranks`；island member 的 `spec.island.reserved_bottom` 打戳 | 客户端压缩镜像的唯一输入 |
| `apps/web/src/components/flow/layout.ts` | `projectSettledFrames` 岛内成员直读定格 y（不压缩）；列底 = `reserved_bottom` 镜像 | 两镜像纪律（graph_store ↔ layout.ts）不变 |
| `docs/MODULE_ARCHITECTURE.md` | `graph_islands` 注册表行 + `graph_nodes` 行补注 | 新表登记（§7 契约） |

**T6｜C8-c Candidate Surface UI（fe591e6）**

| 文件：行 | 改动 | 理由 |
|---|---|---|
| `apps/api/app/chat/plan_turn.py` / `propose_turn.py` | 新增 `_emit_candidates` / `_candidate_set_payload` / `_selection_payloads` 三件套；`propose_candidates` / `propose_selects` / `_revise_selects` 门成功处发射 | C8-c 数据链的产出侧：set 载荷读持久化 spec（幂等重放重发存储态）；selection 经 `read_journey_evidence` 算该集合**当前完整**选中序号（客户端替换不并集，revise 重指自动摘旧选） |
| `apps/api/app/chat/service.py` | `record_candidates_log` + `CANDIDATES_LOG_TYPE`（`record_activity_log` 镜像：ref 去重、flush-only）；`on_candidates` 穿线全部 on_activity 座位 | 持久化 = turn 完成后一行 `intent.type="candidates_log"`，失败回合零持久化 |
| `apps/api/app/chat/routes.py` | `_make_candidates_hook`（sink 收集 + SSE 发射）+ `_persist_candidates_log`（own session、best-effort）；两个流（chat turn / answer turn）同接线 | 新 SSE 帧 `assistant.candidates`；持久化座位 = 完成路径唯一 |
| `apps/web/src/lib/chatStreamFrames.ts` | `CandidateEventPayload` 词表 + 帧路由 | 帧白名单扩张（conversation 信道） |
| `apps/web/src/lib/chat-stream.ts` | `onCandidates` 回调穿线（streamTurn / streamAnswer / streamChat） | 泵面扩张 |
| `apps/web/src/components/chat/historyReplay.ts` | `CandidateSurface` 类型 + `candidatesLog` 读容忍解析 + `mapHistoryRows` 折叠（set 生卡行，幂等重放原位替换；selection 重绘前序卡行高亮；纯 selection 日志行不产生空行） | 刷新/跨设备重建 = 消息回放折叠，无需端点（未覆盖 #1 就此关闭） |
| `apps/web/src/components/chat/CandidateSurface.tsx`（新） | 候选卡：ordinal 两位视觉地址 + mm:ss 时间段 + 源锚定 excerpt + speaker（有则显示）；默认 3 推荐 + 「另外还有 N 个」展开（cap-height 滚动）；选中行 `bg-accent` 高亮；行不可点 | 合同 Seg C 同构解剖；选择经自然语言，表面只反映（chat 决策永不成节点）；register 对齐 AnsweredQuestion（bg-muted 填充步，无环无影） |
| `apps/web/src/components/chat/ChatDock.tsx` | `handleCandidatesFrame` + `liveCandidateRowsRef` + `rollbackCandidateRows`；两个流接线；两个回合起点清回滚域；两个 catch 座位回滚；renderConversationMessage 渲染座位 | live 帧行推流尾（与回放同位）；失败回合删行（服务端同事务回滚了门写入）；幂等重发原位替换保选中态 |
| i18n en.ts / zh.ts | `chat.candidates.more` / `chat.candidates.less` | en 先行镜像 zh |

### 二、未跑验证声明（同上部纪律）

静态核对全绿：改动 .py `py_compile` 通过；冷导入探针通过（`app.main` + 全部触及模块 + `display_ranks` / `island_reserved_bottom` 存在性断言 + 迁移链单 head `m3c6d9f2a5b8`）；web `tsc --noEmit` 通过（node_modules 软链自主 checkout）。**pytest 未跑**；**迁移未在真实 DB 上 upgrade/downgrade**；**端到端行为零验证**。

重点未验证行为面：

1. edit_text 卡内就地编辑端到端：点击 → textarea → ⌘Enter/blur 提交 → 乐观回显 → `fetchGraph()` 回显一致；「恢复原文」写 null 清展示层；text_edits 追加截断 50。
2. 相机律：ensure-in-view 三态（已在安全区不动 / 越区最小平移 / zoom 恒不变）；centerRequest 居中（含 docked 面板遮挡补偿）；3s 手势盾 / prefers-reduced-motion 瞬移退化 / 背景 refetch 不武装。
3. Layout Island：同族兄弟出生定格共享岛原点；join 族 seq 从活成员 max+1 起（孤儿重入座同格）；走廊钳位 cols=1；超容量末列下延；`display_ranks` 槽位膨胀对下游 rank 的影响；`reserved_bottom` 压缩底镜像。
4. wiring expansion 直执快照：revision router 读面拿到 scope 边界。
5. task_book 硬删迁移在含存量行的 DB 上 upgrade/downgrade。
6. T6 候选面端到端：探索回合（「你有什么想法？」类）SSE 帧到达 → 卡行推流尾 → turn 完成持久化 → 刷新回放一致；选择回合（「第二个」）高亮重绘；revise（「把第二个换掉」）旧选摘除；失败回合卡行回滚消失；跨回合（先 refresh 再选）回放卡照常重绘。
7. T6 的 answer-turn 链（选项答复续聊触发探索）同 6。
8. 候选卡解剖核对：3 推荐 + 展开、两行 clamp、mm:ss 格式、speaker 前缀、bg-accent 高亮双主题。

### 三、合同未覆盖补充——本批新增

- **edit_text 词表入 prompt 面**：`wiring_catalog_lines` 与 edit_graph 工具描述新增 edit_text 枚举——**prompt_gate 需重跑**（词表扩张进 intent router 的注册面）。
- **岛容量参数入档**：`_ISLAND_COL_CAPACITY=4` / `_ISLAND_CORRIDOR_COLS=1` / `_ISLAND_MAX_COLS=3` 为出生默认值；同族判定 = 同深度 + 同 rank-edge 父集（ctx 边不入 key）；超容量 contact-sheet 留座不实现（末列向下延伸，结构性不重叠）。
- **岛假设**：同族成员的 frame_class 一致（同一 rank-edge 父集 → 同一消费区域形状）；走廊钳位只发生在 deeper band 已落定场景。
- **MODULE_ARCH §7 探索行**：上部迁址 `exploration_rows` 后注册表行仍写旧座，本批未顺手修（属上部座次，下批清理批一并）。
- **T6 取证修订（上部「数据链已备妥」不准确）**：tool observation 是喂给 LLM 的纯文本，成员级数据（ordinal/时间段/excerpt/speaker）此前从不出服务器；客户端只有 count 里程碑。T6 新建了 `assistant.candidates` 帧族 + `candidates_log` 持久化行——消息载数据链是**本批建成**的，不是既有事实。
- **`exploration_tools.py:execute_exploration_tool` 是死座位**（唯一调用方 = `scripts/chat_scenarios.py` s23，已破损待修剪）：它绕开 turn 类直调门，无 SSE/持久化接线。若未来复活为生产路径，需补 `on_candidates` 通道。
- **候选行无「why」一句**：合同模拟图的 why 行（「观点完整，起承转合都在」）在 CandidateMember schema 无字段（start/end/excerpt/speaker 四件），卡面按数据实况渲染，why 不虚构；若要补，是 schema 扩张 + prompt 面改动，属未来批。
- **候选行不可点**（合同「不再新增任何交互原语」）：选择只经自然语言；若未来要点选直选，属新原语，需先拍板。

### 四、上部遗留提醒（不变）

`ChatDock.tsx` 下部只删了 `onPlanConfirmVisible` 一族（C5 翻案），其余块未触碰；`exploration_rows` 泳道律已删；Candidate Surface 已建成（T6，消息载全链：SSE 帧 + candidates_log 回放，零端点）；`scripts/chat_scenarios.py` s23 探索段仍破损待修剪（注意它走死座位 `execute_exploration_tool`，见上）。

---

## Final Closure（2026-09-27，branch `ws-v42-lower` 自 2992337 起）

终审（同日，静态取证）判 PASS WITH BLOCKERS 后的四项收口。全部【未跑验证】（语法/冷导入静态核对通过；pytest / prompt_gate / live 一律用户自验）。

### 一、改动清单（file:line × 一句话理由）

**P1-1｜探索旅程 decision-package dock 接授权门（propose_turn.py）**

| 文件：行 | 改动 | 理由 |
|---|---|---|
| `apps/api/app/chat/propose_turn.py:640-682` | 新增 `_policy_direct_disclosure_for` / `_answer_docked_direct` 两半门（plan_turn 同形复用）；`_answer_docked_direct` 透传 dock 的 `bailed_run_ids`（修正上批 `_propose_tasks` 直执内联块丢 bailed 致 parked run 泄漏 finalize 的瑕疵，该内联块同批收敛到共享后半门） | 一门两宅：与 plan_turn 同一律，不新造原语 |
| `apps/api/app/chat/propose_turn.py:876-894`（`_propose_plans`） | 门前半：`_safe_task_estimate` + disclosure 骑 dock answer + `estimate=` 透传；门后半：同事务 instant start | 探索「候选→选择→计划」决策包 dock 座位不再恒落拍 |
| `apps/api/app/chat/propose_turn.py:969-985`（`_redock_journey_package`） | 同上（revise_plan 全旅程重编译与 revise_selects docked/post-run 重报价共用此座位） | 修订重落同一确认座位，同过门 |

旁路终查：`sync_plan_question` 全仓 6 个调用点——propose_turn:621（五个座位共用的 dock 座，全有门）/ plan_turn:909、1157、1294（上批已门）/ plan_turn:1580（start misfire 原样重落，非新付费边界，不落直执）/ service.py:1618（caption/slot 答案重落 = 未覆盖 #8 拍板的安全默认，维持落拍）。零旁路。

**P1-2｜prompt 面 画布 → 工作空间（命名三层律，v4.2 封板⑪）**

| 文件：行 | 改动 | 理由 |
|---|---|---|
| `apps/api/app/prompts/chat/intent_router_system.j2:45` | review invitation 的用户话术 `'the canvas', '画布'` → `'the workspace', '工作空间'`；头部 provenance 注记 2026-09-27 改口；L63「canvas's exploration rows」→「chat's candidate cards」（C1 后探索行无画布座位，顺带修陈旧指引） | 封板⑪用户话术 = 工作空间 |
| `apps/api/app/prompts/chat/trigger_system.j2:33,36,43` | 模型面指引的 canvas 参照系全改 workspace；「canvas card」→「its own card」 | 同上（agent 散文的参照系词汇） |
| `apps/api/app/chat/intent.py:250-262` | `surface_line` 事实句改口 workspace（`surface == "canvas"` 内部枚举不动） | LLM 输入事实与模板法一致 |
| 不动 | 内部代码命名（ChatRequest.surface 枚举 / results.canvas.* 键空间 / 组件注释）与 `quotes.j2` 图像构图语义的 canvas | 用户拍板：内部 Canvas 命名不改 |

**⚠️ prompt 面已动（intent_router_system.j2 / trigger_system.j2 / 注册表 catalog 行见 P1-3）——deploy 前必须重跑 `scripts/prompt_gate.py`（ADR-071 T2）。**

**P1-3｜DeleteNodeOp settled guard（graph_store.py）**

| 文件：行 | 改动 | 理由 |
|---|---|---|
| `apps/api/app/pipeline/graph_store.py:863-885` | `apply_wiring_ops` 加 `allow_settled_delete: bool = False` 关键字参（门的内部参数，非 op 词汇） | settled 守卫的合法旁路只有一个主人 |
| `apps/api/app/pipeline/graph_store.py:1156-1176` | DeleteNodeOp 分支守卫：非 draft 态且非 legacy draft-born task_book（`role==task_book` 且无 `run_id`）→ `WiringRejected("append-only")` | 封板⑤ Settled 只长不消；chat/LLM 永无旁路 |
| `apps/api/app/pipeline/graph_fill.py:313-321`（`remove_asset_node`） | 素材生命周期删除传 `allow_settled_delete=True` | 唯一合法 settled-delete 调用方（asset 节点 born done + 其转写文档随行） |
| `apps/api/app/pipeline/graph_store.py:194-196` | wiring catalog 行改「remove a PROVISIONAL draft node…settled append-only」 | 模型面目录与门一致（**prompt 面改动，prompt_gate 同批**） |
| `apps/api/tests/test_graph_wiring_pure.py:461-525` | 既有 edge 级联测试改走 bypass（mirror remove_asset_node）；新增两例：settled(done/running) 拒删 + draft/legacy task_book 可删、run-born book 拒删 | 守卫分支覆盖（**pytest 未跑**） |

合法清理路径不受影响：`clear_draft_graph`（draft 态 + legacy task_book 受害者形状全在守卫允许面内，无需 bypass）；draft re-stamp 孤儿清扫（draft-only）；`_DRAFT_RESTAMP_STATES`（draft/failed/skipped）是**复用**语义与删除无关，未触碰。

**P3｜用户可见「画布」清零**

| 文件：行 | 改动 | 理由 |
|---|---|---|
| `apps/web/src/lib/i18n/locales/zh.ts:1097` | `zoomFit: "适应画布"` → `"适应工作空间"`（en `"Fit to view"` 本无 canvas 词，不动） | 唯一用户可见中文残留 |

全仓扫描：UI 用户可见值零 画布/canvas 残留（其余命中 = 注释 / `results.canvas.*` 键空间 / `offcanvas` 类型字面量 / surface 枚举——内部命名按拍板保留）；prompt 面残留 = Jinja provenance 注释（模型不可见，记改口史）+ `quotes.j2` 图像构图语义（词义不同，不动）。

### 二、未跑验证声明

静态核对：五个 .py `py_compile` 通过；两个 .j2 Jinja parse 通过；冷导入探针通过（app.main + `allow_settled_delete` 参数存在性 + ChatTurn 两半门存在性 + 测试模块 import 面）。**pytest 未跑**（含新增两例守卫测试）；**prompt_gate 未跑**（prompt 面三处改动 + catalog 行，deploy 前必跑）；**三档策略在 propose_plans / revise_plan / revise_selects 路径的行为未 live 验证**（重点：never 直执时 `answer_question` 对刚 dock 的 pending 的同事务可见性——与既有五座位同构，理论一致）；**直执后探索旅程的 mark_compiled / 快照落戳未 live 验证**（走 `answer_question` 同一 Start 机器，理论同构）。
