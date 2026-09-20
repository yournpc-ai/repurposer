# Phase 4 Step 0 盘点清单（全文）——propose path 直起 run 全部来源与测试

> 取证：2026-09-20 Phase 4 Preflight（只读，零代码改动）。锚点核于 current HEAD `d3616c2`（原合同锚点核于 `d0006ac`，漂移已逐条重新定位）。
> 合同依据：`docs/tasks/lifecycle-phase-4-confirmation-doctrine.md` §Step 0「未建清单不动代码」——清单已建，B1 起允许动代码。
> 终裁：2026-09-20 Decision Gate D1~D4 + Frozen Rule 1~10（见施工合同 §Decision Ledger）。

## 表 A：propose path 直起 run 全部来源（产品代码，2 出口 + 1 漏斗）

| # | 来源（d3616c2） | call path | 触发条件 | 锁现状的测试 | old expected | 产品含义 | 处置批 |
|---|---|---|---|---|---|---|---|
| A1 | `apps/api/app/chat/propose_turn.py:330`（`_propose_tasks` → `_create_run_from_tasks`） | chat path 终态工具 → caption 闸门（`:300-323`）→ `_derive_chat_caption_mode`（`:327`）→ 角色 pins（`:328`）→ `_create_run_from_tasks`（`service.py:327-394`）→ `create_run`（`orchestrator.py:983`，hold 于 `:1132-1135`） | 任务列表非空 ∧ 无需 caption 问（或 mode 已解析：关键词/stash/source_only 兜底） | S7-B（`chat_scenarios.py:2180-2205`）；harness `terminal_tool_of` 的 `run_birth` 类（`:687-690`） | 当轮起 run，零确认、零估价披露 | 新 Paid Work 无确认节拍（Rule 1/2 打击面） | B3 |
| A2 | `apps/api/app/chat/propose_turn.py:470`（`_edit_graph` run op → `_create_run_from_tasks`） | `apply_wiring_ops`（图唯一写门）→ `delta.run_nodes` 非空 → `tasks_for_graph_nodes` → `_create_run_from_tasks`（`:439-474`） | wiring ops 落地且解析出可执行子图（纯删等无 run op 不起 run，`:443-445`） | S4-A2（`chat_scenarios.py:1478-1508`） | 修订即起 run，零范围裁决 | approved-scope revision 与 scope expansion 无分界；`EditGraphArgs.ops` 全词汇可收（`schemas.py:745-748`），prompt 只引导 edit_prompt+run（`chat_intent_system.j2:23,44`），代码层无拦 | B1+B2 |
| A3 | `apps/api/app/chat/service.py:327-394`（`_create_run_from_tasks` 漏斗本体） | 上述两出口唯一汇入；`TaskSpec` 硬编 `scope="full"`（`:378`）、不设 autonomy | —（被调件） | 无纯测试直锁（S13 只锁 plan Start 与 /generate 两路 422，不锁 chat dispatch 的 422 转换 `:385-393`） | `CreditsInsufficientError` → 结构化 422 | 范围包含性裁决座（Rule 7——代码裁决，非 LLM 自决） | B1 |

## 表 B：确认路径其余 create_run 来源（F7 兜底 sweep 全量——产品代码 4 处，无遗漏）

| # | 来源 | 性质判定 | 测试 | 备注 |
|---|---|---|---|---|
| B1 | `service.py:1583`（`answer_question` task_book kind=start） | 合法确认座（plan path Paid Authorization） | S1/S4/S5/S7-C/S13 等 | autonomy/估价/lifecycle 戳全链齐备；D3 = Batch 6 加服务端四合取强制 |
| B2 | `routes/projects.py:693`（`POST /graph/revise`） | 合法 approved-scope continuation（卡面直改，确定性手势，ADR-058） | S 族回归间接 | `origin="node_revise"` 出生后盖章（`:726`）——全栈唯一 origin 标记先例；本 Phase 不动 |
| B3 | `routes/projects.py:856`（`POST /generate`） | **D2 灰区**：tasks=None+full scope 422（`:826-830`），但 tasks≠None 时信任客户端任意链 | S13（裸链 422 形状） | 三个真实用户：① tab retry（`projects.$id.index.tsx:608-624`，逐字重放上链 = 合法 retry 但服务端不可证）② legacy Start fallback（`ChatDock.tsx:1596-1617`，pre-dock 项目，确认记录仅在客户端）③ 裸 API。处置 = B5 |
| B4 | `orchestrator.py:1058`（出生地本体） | 唯一 `WorkflowRun(` 构造点（sweep 实证：worker/jobs/trigger_turn 零构造） | — | hold 与 run 同事务（`:1132-1135`）——propose 直起路径在提案当拍即扣钱零披露，§2.1 违反面 |

脚本侧（非产品路径，零触碰）：`bake_image_video_demo.py:244` / `bake_quote_chain.py:213` / `bake_reframe_demos.py:323` / `bake_text_tribe_demos.py:266` / `run_anatomy_matrix.py:229`。

## 表 C：caption 双标现状（方向与旧表述相反）

| 面 | 现状（d3616c2） | 测试锁 |
|---|---|---|
| caption 参数闸门（合法特殊性） | propose 侧 `propose_turn.py:300-323`；plan 侧 `plan_turn.py:671-715`；共用 `_build_caption_mode_question` / `_is_caption_mode_question`（`service.py:832-837`） | S7-A/C（`caption_gate` 终态判别 + 答前无 run） |
| caption 答后 fast path | `service.py:1403-1492`：确定性 replay stash → `PendingPlan`（`:1459`）→ `sync_plan_question` dock task_book（`:1474`）→ 估价随行（`:1479`）→ 用户 Start | S7-A（follow_up 即计划 dock + mode 入 pending_brief）；`answer_caption_gate` helper（`:964-984`）被 S1/S4/S13/S18/S20 共用 |
| **双标实锤** | 带 caption 的 propose 工作拿全套确认（闸门→dock→Start+估价）；不带 caption 的 propose 工作（A1）零确认零披露——**caption 路已是目标形态，非 caption 路才是缺口** | S7-A（有确认）vs S7-B（无确认）同场对照 |
| parity 处置方向 | 「选项答完 dock+Start 绕过 propose_turn 重判」不是罪状是样板（`:1409-1410` 注释自证确定性 replay 是有意的）；拆除对象 = A1 的无确认直起，不是 fast path | — |

## 表 D：失信描述枚举（模型可见面全量）

| # | 位置 | 现状文本 | 定性 | 处置批 |
|---|---|---|---|---|
| D1 | `turn_tools.py:88-90`（`propose_tasks`） | "Propose new work as a task list for the user's confirmation — it never starts a run by itself." | 实锤失信——实现 `propose_turn.py:330` 当轮起 run；系逐字复制 `present_plan` 的诚实文本（`turn_tools.py:44-47`） | B4 |
| D2 | `turn_tools.py:105-108`（`edit_graph`） | "…(add_node / connect / edit_prompt / delete_node / run) and re-fill the affected subgraph" | 半失信——对重跑机制含糊、对付费 run 零披露 | B4 |
| D3 | `chat_intent_system.j2:19` | "propose_tasks — run NEW work" | 与 D1 自相矛盾（系统 prompt 说 run、工具描述说 never run）；与现实现一致，与目标语义不一致 | B4 |
| D4 | `chat_intent_system.j2:23` | "The bare run op re-fills the edited node and everything downstream" | 机制诚实、确认语义缺席 | B4 |
| D5 | plan path 侧（`intent_router_system.j2:41,48` + `turn_tools.py:44-47,62-67`） | present_plan "never starts a run by itself" / start_run "Only when the user confirms a docked plan" | 本就合规——plan path = 目标形态，预计零改动 | — |
| D6 | `docs/CHAT_ARCHITECTURE.md:66` | "propose_tasks …→ 出生地起 run" | 文档对现状诚实，目标语义下需现在时改写 | B8 |

## 表 E：`autonomy="review"` 取证（D1 终裁的事实基础）

| 面 | 事实（d3616c2） |
|---|---|
| 前端 | `ChatDock.tsx:957` `useState<Autonomy>("review")`；picker 隐藏（`QuestionDock.tsx:56` `SHOW_AUTONOMY_PICKER = false`）；`setAutonomy` 唯一出口挂被隐藏的 picker（`ChatDock.tsx:4038`）= 用户无真实入口 |
| 发送面 | pill Start 恒带（`ChatDock.tsx:1568`）；confirm 期散文 send 条件带（`:2308`） |
| 服务端链 | `schemas.py:245/888/3234` → `service.py:1601` → `TaskSpec.autonomy`（`orchestrator.py:144`）→ review 时 understand→plan 间插 direction interrupt（`orchestrator.py:368-381`）→ `node_runners.py:548-629` 挂 WAITING_HUMAN dock 方向问 → TTL 1800s 自动按默认项续跑（`orchestrator.py:1956-2024` + `config.py:58` + `worker.py:91`）；零 key arguments 自动放行不挂起（`node_runners.py:623-629`）；插入条件 = 链含 `needs_plan_prelude` 生成工具（`orchestrator.py:339`） |
| propose path | `_create_run_from_tasks` 不设 autonomy（`service.py:374-384`）→ 恒 auto，review 不可达 |
| 测试 | 剧本从未真跑 review 编译（`chat_scenarios.py:478/557` 仅 fixture context；Start 调用全不带 autonomy → auto）；S6 族 + S17 以 `seed_parked_interrupt` 测 interrupt 机器（非 tier）；纯测试唯一 tier 覆盖 = `test_decompile_pure.py:277-281` |
| 结论 | **非死档**：plan path 事实唯一实发档；propose path 不可达——同一付费工作两路执行中治理不同；D1 终裁 RETIRE（WAITING_HUMAN / interrupt / verify escalation 基建保留：`orchestrator.py:1652/1764/1956`） |

## 表 F：IC:50 前端 G-explicit 自动 Start（R5 锚点更正）

| 面 | 事实 |
|---|---|
| 旧座 | `apps/web/src/components/generation/GenerationOverlay.tsx:952-964` @ `22f0567`——`useEffect` 在 `initialIntent.action==="generate" ∧ !initialNeedsClarification ∧ phase==="confirm" ∧ questionLoaded` 时自动调 `handleStartGeneration()` |
| 消失点 | `43dbda3`（2026-09-03，ADR-051 批删 `GenerationOverlay.tsx` 整文件）——比 ADR-087 拍板（2026-09-19）早 16 天 |
| 当前 HEAD | 唯一 Start 触发 = dock pill onClick（`ChatDock.tsx:4039 → 1546`；全仓 `kind: "start"` 唯一调用点 `:1568`）；`autoStarted` / `startPendingPlan` / `draftConfirm` / `onDraftConfirm` 标识符 grep 全零 |
| 结论 | R5 migration note 的「Phase 4：前端移除自动 Start」所指代码工作已不存在；Phase 4 剩余 = 验收 grep 防回潮 + 服务端 propose path 统一 |

## 表 G：收敛可行性（确认装置是 dock 驱动、路径无关的）

| 事实 | 座位（d3616c2） |
|---|---|
| dock 存在即转 plan path（G-1 散文确认 / pill Start 双通道自动继承） | `service.py:2121-2122`（`is_pending_plan(pending)` → `plan_path=True`） |
| dock pill 只读 `pendingQuestion` 不问出处 | `ChatDock.tsx:1556-1568` |
| lifecycle 投影只读 dock 行字段级事实，propose dock 的提案自动获得五态戳 + 四合取 | `lifecycle.py:283-300` |
| PendingPlan / sync_plan_question / stamp_draft_graph / _safe_task_estimate / 角色 pins stash → Start 读取 全座位现成且已被 caption replay 共用 | `service.py:1145` / `:1229-1237` / `:403` / `plan_turn.py:779` / `service.py:1612-1613` |
| 密度律天然兼容（单任务书 = 纯散文确认，确认手势骑下一条 chat 消息——该回合自动转 plan path） | ADR-054 + `service.py:2121` |
| caption_mode 结构化字段 + Start 继承逻辑 | `service.py:1537-1544` / `plan_turn.py:724-733` |
