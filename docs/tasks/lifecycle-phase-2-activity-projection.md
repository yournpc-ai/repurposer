# Lifecycle Phase 2 施工合同——Agent Activity Projection（单槽状态行 → 追加式活动流）

> 拍板：2026-09-19（用户，Architecture Freeze）。架构合同 = `docs/DECISIONS.md` ADR-087 §3（Agent Activity Contract + 十条对账规则 + 三概念分家）。
> 前置：Lifecycle Contract 稳定（Phase 1 全闭环）。
> 范围纪律：**只做 Activity Projection**。Presentation 归位（Phase 3）、确认教义（Phase 4）本合同不施工；ADR-085 三层交付模型（Phase/Checkpoint/Settled）是言语族近亲，**不重设计、不翻案**。

## Product goal

让用户持续感知 Agent 正在为其完成什么工作：

1. 多工具 / 多迭代过程用户可见**追加式里程碑**（append-oriented stream），不再是单槽 last-write-wins 状态行。
2. 无 15s+ 纯心跳盲窗（>0 迭代目前 15–25s 只有心跳）。
3. 打字机律不破（散文仍 pacing 释放；活动帧与散文节拍共存，整段瞬移永禁）。

## Current evidence（审计事实，开工前以 current HEAD 复核）

- Agent 中间事件丰富：ToolLoop 7 座 hook 全接线（`routes.py _make_tool_hooks` / runner 回调）；相位帧机制现役（`THINKING_PHASE_*`，`service.py:2177-2198`）。
- 线上压扁点：单槽 ThinkingRow（`StatusLine` 一座两行，CHAT_ARCH §8.7）= last-write-wins；拒绝当时零帧；活动无 id / 排序 / 时间戳；客户端无活动累积结构。
- 拒绝当时零帧 = 被拒迭代对用户不可见（修复轮只有 `repairing` 相位帧一拍，无事实内容）。
- 文案寄存器已是 activity 而非 status（"Drafting the plan…" 式叙事——Activity Projection 是给它事实骨架，不是发明文案）。

## Contract changes

- ADR-087 §3 十条对账规则是唯一合同；本批落成机制，**不改语义**。
- phase 保留但定义为 System Status（宏观态）；Activity 是新的独立概念，phase 不再是 Activity container。
- Activity ≠ ADR-085 Checkpoint（grounded judgment 言语）：Checkpoint 是 Assistant Conversation 层的交付，Activity 是工作观察流——两者共存，互不消费。
- 新模块七问（§十七）预判：Activity Projection 拥有「user-safe activity events」概念；写者 = Activity Projection 自身（首版内存态，不写 DB）；读者 = SSE transport → Chat Activity UI；Lifecycle / Domain / Canvas / Confirm 永不依赖它；层 = Projection。落地座位施工时按依赖方向裁定并登记 `MODULE_ARCHITECTURE.md` §7.1。

## Files（预判，施工时按依赖方向裁定）

- 新建：Activity Projection 层（候选 `apps/api/app/chat/activity.py`——internal events → user-safe events 的过滤/聚合/折叠，稳定 identity + deterministic ordering：activity_id / sequence / status / semantic_key）。
- Hook 接缝（最小增量 3 座，复用既有 `_make_tool_hooks` / runner 回调）：**拒绝当时 / 终态接受 / 迭代边界**。
- SSE：新增活动帧类型（候选 `assistant.activity`），`_sse_pump` 既有队列直过。
- 前端：Chat Activity UI（dock 内追加式流；`StatusLine` 相位帧作为 System Status 保留）。
- **ToolLoopAgent 零重写**（hook 接缝外挂，不进内核）。

## Tests（Claude 编写，用户自跑）

- 纯 pytest：id / sequence / started→completed / 聚合（N internal → 1 activity）/ 过滤（1 internal → 0 activity）/ 显式 cancelled/failed 终态。
- 无 CoT：活动帧零内部推理文本；无原始工具参数与结果载荷。
- 零 lifecycle 写入：Activity Projection 对 Domain / Lifecycle 只读（grep 可证——无 DB 写、无 lifecycle 谓词调用）。
- 打字机律回归：散文 pacing 释放不被活动帧打断（剧本断言帧序）。
- 剧本：多迭代回合可见追加式里程碑；无 15s+ 纯心跳窗。

## Migration strategy

additive 先行：活动帧上线但 UI 并行渲染（StatusLine 不动）→ 剧本 + 产品试用验证 → Chat Activity UI 切换为活动流主座 → 单槽 ThinkingRow 的 Activity 职能退役（StatusLine 收窄为纯 System Status）。每步独立 commit。

## Rollback strategy

活动帧是 additive；UI switch 独立 commit，回滚 = revert switch。首版无持久化，无数据迁移面。

## Acceptance criteria

- 多工具 / 多迭代过程用户可见追加式里程碑（started → completed/failed/cancelled 显式生命周期）。
- 无 15s+ 纯心跳盲窗。
- 打字机律不破（散文仍 pacing 释放；零 delta 路径 paceSettledProse 闸门同形适用）。
- Activity 零 UI 迁移驱动（grep 可证：无任何 `activity → canvas/confirm/run/lifecycle` 消费）。
- 词汇单一 canonical owner（活动文案键出注册表一处，Tool Registry / Prompt / Service 引用同一源）。

## Prohibited Behaviors

- 禁止 Activity 作 Lifecycle authority / 直接控制 Canvas / Confirm / Run。
- 禁止把内部 Tool Log 暴露给用户（原始工具参数、结果、推理文本永不上活动帧）。
- 禁止把 Activity 做成 workflow graph（无拓扑、无 DAG 可视化）。
- 禁止改 ToolLoop 内核（terminal 语义 / max_iterations / 言语账本不动）。
- 禁止用 phase 作 Activity container（phase = System Status）。
- 禁止首版做持久化与回放（登记为未来项，不本批）。
- 禁止顺手拆 ChatDock（Phase 3）/ 顺手统一确认路径（Phase 4）。

## 收尾报告格式（每 Phase 同律，§十六）

Goal / Current evidence / Contract changes / Files / Tests / Migration strategy / Rollback strategy / Acceptance criteria / Status（日期 + commit 范围 + 验证状态——compileall / import 探针 / tsc / 剧本 = 用户自跑，报告标注「未跑验证」项）。

## Docs update（同批）

- ADR-087 Consequences Phase 2 行回填落地座位 + commit 范围。
- CHAT_ARCHITECTURE §8.6/§8.7 现在时改写（Activity Stream 座位；phase = System Status 注记）。
- PROGRESS §0.2 状态行更新；`MODULE_ARCHITECTURE.md` §7.1 登记（若新文件落地）。

## Status

PREFLIGHT **PASS WITH CONDITIONS**（2026-09-19 用户裁定：U1/U4 批准、U5 按 T16-A/T16-B 双不变量收紧后批准开工；另冻结两条门禁——kind = 用户语义类别永不退化为 tool name、连续性 ≠ 周期刷新；ToolLoop 只产 typed internal Loop Events）。裁定全文已回填 §Preflight P4/P6/P7。**Implementation 开工。** 前置 = Phase 1 验收全闭环（剧本/tsc 用户自跑，结果未回）。

IMPLEMENTATION **步①~④ 已落地（2026-09-19，commits `662d88a` 服务端 additive / `fa0df01` 客户端解析 / `a33cae4` 并行渲染 UI；worktree `worktree-lifecycle-phase2-preflight`）**：
- 步①：`agents/tool_loop.py` typed `LoopEvent` 四事件（ToolRejected / TerminalAccepted / ReadAccepted / LoopExhausted）+ `on_loop_event` 缝 6 个发射点（零行为变化，可选 kwarg）；`app/chat/activity.py` 纯投影器（kind 四值 / repair N→1 聚合 / conversation 工具 1→0 过滤 / 终帧清扫 T16-B / 零 DB 零 Domain）；`assistant.activity` SSE 帧上流（chat/answer 双流）；`on_loop_event` 全链穿线（execute_chat_turn → 双 shim → 双 runner + answer_question 5 内部点）。纯 pytest 26 例绿（T1-T17 + loop 发射 6 例）。
- 步②：`chat-stream.ts` `ActivityFramePayload` 类型 + `onActivity` 回调 + `assistant.activity` 分发分支（字段白名单注释入码）。
- 步③④：ChatDock 回合级 activities 累积（append-only 按 activity_id upsert）+ 信封/失败/abort 三处防御清扫（T16-B 客户端孪生）+ `ActivityStream` 组件（active spinner+shimmer / ✓ / ✗ destructive / 删除线 cancelled）+ 渲染座在 thinking 行上方、active 活动在位时 System Status 行让位；i18n `chat.activity.*` + `chat.inspectingDone.*` 双语镜像。
- **步⑤（相位面收窄）HOLD**——本简报 Migration strategy 的门禁即「活动帧上线但 UI 并行渲染 → 剧本 + 产品试用验证 → Chat Activity UI 切换」；收窄面 = 服务端 drafting/inspecting/repairing/creating_run 相位发射退役（保留 composing/基座/清除帧）+ 客户端 thinkingKey 移除 + i18n 死键清理 + 剧本 S10 帧序断言更新。**待用户跑剧本 + 产品试用后裁定开工。**
- **Acceptance Gate（2026-09-19 执行，commits `2cf53d7` 测试裁决 / `922c301` harness 扩展）**：compileall ✅ / import 冷启动探针 ✅ / tsc 2 处报错均预存在（主检出 base 同点复现，本批零新增）/ 纯 pytest **295 例全绿**（两例预存在失败经 Test Contract Adjudication 清零，见下）/ 剧本：S10+S20（含 S20A）对新代码全绿（含新增活动帧形状律五断言）；S5/S7/S11 失败在**旧代码基线（:8000 主检出）同族复现** = 已登记 LLM 方差族 + 种子素材存储 404 环境噪声，非 Phase 2 regression / 线上实测一回合原始帧：reject→repair→retry 生命周期、9.2s 修复窗由 active repair 覆盖（连续性≠刷新实证）、信封零 dangling、ask_user 1→0 过滤全部命中。**步⑤ 仍 HOLD，等用户产品试用裁定。**
- **Test Contract Adjudication（Gate 4 裁决记录）**：① `test_transcript_node_skips_textless_assets`——original intent = 无文本资产不生转写卡（Phase 1 前合同）；current contract = 文本产出型资产**上传即出生** queued 卡（8972e74 有意变更，graph_fill docstring + ADR-087 §2 R2 在册）；verdict = 有意变更 → 测试迁移（拆两例：text-yielding 出生 queued+幂等 / image·voice_sample 仍 None）。② `test_bare_question_follows_the_speech_language`——original intent = bare question 跟随言语语言；current contract = 语言跟随（4cb3dd0 引入的文案 "What's next?" 自出生未变，大小写非冻结合同）；verdict = 测试出生即红的大小写笔误（同 commit 文案与断言自相矛盾）→ 改语义断言（case-insensitive + 跨语言互斥）。两例均非「base 已失败即 stale」——取证链在 git（8972e74 / 4cb3dd0）。
- **环境注记**：纯 pytest 需要仓库根 `.env`（Settings 从 `parents[3]` 读，worktree 内已复制一份 gitignored 副本）；worktree 无 node_modules，已软链主检出 `apps/web/node_modules` 供 tsc 使用；剧本实证用 worktree 自有服务器 :8010（已停），种子素材存储对象缺失（HeadObject 404）是环境噪声源之一。

---

## §Preflight 报告（2026-09-19；只读取证，未改代码；未跑验证——本报告全部结论来自静态阅读；锚点核于 HEAD `6196b1f`，行号会漂移，以内容定位）

### P1. 现有 activity-ish 信号全集

**A. Loop 内部信号（`app/agents/tool_loop.py` `call_loop`——Agent Runtime / Harness 层，内部执行事实的唯一源头）：**

| # | 信号 | 座位 | 现状发射 | 今天用户可见形态 |
|---|---|---|---|---|
| L1 | 散文 delta（仅 iteration 0） | tool_loop.py:375-382 | `on_delta` → `assistant.delta` | 散文流（打字机） |
| L2 | reasoning 片段 | tool_loop.py:380（kwarg :238） | `on_reasoning` → `assistant.thinking {}` | 仅保温，永不展示 |
| L3 | 工具名成为已知（name-known） | 流式 :381；静默迭代 :389-390 | `on_tool_call(name)` | 相位拍（drafting / inspecting+key / 清除帧） |
| L4 | 参数校验通过（执行前） | tool_loop.py:482 | `on_tool_ready(name, params)` | 仅 ask_user 消费（`question.preview`） |
| L5 | 拒绝：schema_truncation | tool_loop.py:391-407 | 仅 structlog + `prev_rejected` | **零帧（拒绝当时不可见）** |
| L6 | 拒绝：unknown_tool | tool_loop.py:433-451 | 同上 | 零帧 |
| L7 | 拒绝：params_validation | tool_loop.py:464-481 | 同上 | 零帧 |
| L8 | 拒绝：execute_guardrail | tool_loop.py:577-589 | 同上（runner 经返回值可知） | 零帧 |
| L9 | 重试迭代开始（prev_rejected） | tool_loop.py:367-370 | `on_repair` | `repairing` 相位（经 R4 适配器）——**迟一拍**，拒绝发生时不发 |
| L10 | 读被接受（ToolObservation） | tool_loop.py:485-559 | `on_observe(name)`（:559） | `composing` 相位（经 R5 适配器） |
| L11 | checkpoint 交付 | tool_loop.py:502-522 | `on_checkpoint(text)` | `assistant.checkpoint` 帧 + 持久化行（ADR-085，言语族，互不消费） |
| L12 | 终态接受（execute → None） | tool_loop.py:561-576 | `LoopResult` | runner 副作用（dock / run 出生），无独立帧 |
| L13 | bare reply（无工具调用） | tool_loop.py:410-422 | `LoopResult(tool_name=None)` | 信封散文 |
| L14 | exhausted（上限，全拒绝） | tool_loop.py:590-598 | `LoopResult(exhausted=True)` | runner finish 的 cannot-do 行 |
| L15 | 多余工具调用（>1） | tool_loop.py:423-431 | 仅 structlog warning | 无 |
| L16 | 回合摘要日志 | tool_loop.py:343-357 | 仅 structlog | 无 |

**B. Turn-runner / service 层信号：**

| # | 信号 | 座位 | 现状形态 |
|---|---|---|---|
| R1 | drafting（dock 工作开始） | plan_turn.py:768-774 | `on_phase(drafting)`——brief 写 + dock + 草稿图钢印段 |
| R2 | creating_run ×3 座位 | service.py:375-376（chat 派发）/ :1582-1585（answer plan_start）/ plan_turn.py:929-932（G-1） | `on_phase(creating_run)`——run 出生前 |
| R3 | checkpoint 持久化 + 转发 | service.py:2214-2237（`_checkpoint_callback`） | 消息行 `intent={type:checkpoint}` + SSE 帧 |
| R4 | repair 适配器 | service.py:2264-2274（`_repair_phase_callback`） | on_repair → phase repairing |
| R5 | observe 适配器 | service.py:2201-2211（`_observe_phase_callback`） | on_observe → phase composing |
| R6 | 相位清除帧（未映射 name-known：ask_user / answer / start_run） | routes.py:183-194 | `assistant.thinking {"phase": null}`（I-PFA-06 缝②） |
| R7 | **name→相位映射硬编码** | routes.py:163-194（plan-shape 清单 :164 + perception 成员判定 :171 + 未映射→清除 :183） | 与 turn_tools.py 的工具集声明**双座**（规则 9 隐患，见 U6） |
| R8 | 终端信封 | routes.py:354 / :364-366 + `_sse_pump` :262-275 | `turn.completed` / `turn.failed`（带 persisted 旗） |
| R9 | 心跳 | routes.py:126 + `_sse_pump` :256-259 | `: heartbeat` 注释帧 15s |
| R10 | question.preview | routes.py:104-123 / :196-210 | ask_user 参数一过校验即 dock pill |
| R11 | 相位常量 | service.py:2177-2198 | creating_run / drafting / repairing / inspecting / composing 五值 |

**C. 相邻流（边界登记，非本 Phase 范围）：**

- **run 事件流**：`pipeline/routes/runs.py:87-144`（`run.snapshot` / `step.updated` / `run.updated`，1s DB tail + 15s 心跳）——workflow_steps 的推送管道，消费面 = RunTaskList（**已是追加式打勾流**）。这是执行运行时的可见性，不是 chat 回合的 Agent 活动；两个面不动。
- **trigger 回合**：trigger_turn.py:384-389 `call_loop` **零 hook 接线、无 SSE**（fire-and-forget，说话 = dock 一条 review 行落库）。无直播窗口可挂活动流（见 U2）。

**D. 客户端消费点（取证自 working tree）：**

- thinking 状态：`thinkingPhase` / `thinkingKey`（ChatDock.tsx:1340/:1345）；渲染门 `chatBusy && !proseActive`（:4395-4411），label 优先级 `thinkingKey > chat.thinkingPhases[phase] > chat.thinking`；清空点 = 回合开场（:2609-2610 / :3204-3205）+ 终端帧（:2807-2808 / :2967-2968 / :3279-3280 / :3368-3369，I-PFA-06 终帧律）。
- 帧分发：`lib/chat-stream.ts:188-215`（delta 189-191 / thinking 192-193 / question.preview 194-199 / checkpoint 200-202 / completed/failed 203-213）；`streamTurn` 是唯一 SSE 泵，禁自动重连。
- 打字机耦合：`lib/typewriter.ts:13-100`（忙闲边沿 → `proseActive`；IDLE_GRACE_MS 400ms :28；`drain()` :75-80 是 paceSettledProse/checkpoint 的「散文先行」闸门）；`paceSettledProse` ChatDock.tsx:2714-2736 / `paceUnstreamedTail` :2744-2754。
- StatusLine 一座两行（`components/chat/StatusLine.tsx:18-75`，纯展示组件）：dock thinking 座（ChatDock.tsx:1033-1041 ThinkingRow，label-only 无时钟）+ run 动态行座（RunTaskList.tsx:162-200，消费 run 事件流，不消费 chat 回合流）。
- **`Phase` 同名两义防撞**：ChatDock.tsx:139 的本地 `Phase = "confirm"|"running"|"chat"` 是 dock 表单机（确认门/几何），与服务端 `THINKING_PHASE_*` 是两个概念；ADR-087「phase = System Status」收窄的是服务端族。本 Phase 不动本地 Phase（归位命名是 Phase 3 的事，见 U8）。
- Home 侧零消费（`components/home/` 无任何 stream/StatusLine 引用）。

**现状结论（压扁点取证）**：回合内一切过程可见性 = 单槽 `thinkingPhase` last-write-wins；无身份、无排序、无历史累积结构。`composing` 相位（2026-09-17 交互完整性批 C）已消灭「读完后戴 stale inspecting 标签」的假相，但单槽结构仍在：>0 迭代时用户看不到「已经做过什么」，只有当下一个标签；拒绝当时（L5-L8）到重试开始（L9）之间零帧。这正是十条对账规则要落成机制的三个缺口：**身份 / 排序 / 显式终态**。

### P2. internal → user-safe 事件对账表（逐事件裁定 + 理由）

| 内部事件 | 裁定 | 拟议 user-safe 形态 | 理由 |
|---|---|---|---|
| 读调用 name-known（L3，perception 名） | **暴露** | `read` 活动 active 帧（copy = registry `activity_key`） | 已是用户安全形态（inspecting 帧现役）；补身份与显式开始 |
| 读被接受（L10） | **暴露**（与上配对） | 同一 `read` 活动 completed 帧 | on_observe 是天然的完成边界；started→completed 显式终态（规则 6） |
| 读的 observation 文本 | **过滤**（1→0） | 永不上帧 | 原始结果载荷禁令（简报 Prohibited #2）；它喂模型不喂用户 |
| 计划形调用 name-known（present_plan / propose_tasks / apply_edit_ops / edit_graph） | **暴露** | `draft` 活动 active 帧 | 现役 drafting 语义的活动化 |
| 计划形调用接受（L12） | **暴露**（配对） | `draft` 活动 completed 帧（dock 落 = 副作用完成 = execute 返回 None） | dock/卡到达前用户看到「起草中→已落卡」 |
| start_run name-known → 出生 | **暴露** | `run` 活动 active（name-known）→ completed（L12 accept = create_run 已返回）；出生地 422 → failed | 现役 creating_run 段的活动化；费用手势语义不动（Activity 永不控制 Run，规则 8） |
| ask_user / answer 调用 | **过滤**（1→0） | 无活动帧 | 它们的用户面 = question.preview pill / 散文本体（Assistant Conversation 层）；再发活动行 = 双重叙事 |
| 拒绝当时（L5-L8 四类） | **暴露（新增）** | `repair` 活动 active 帧——**拒绝当时即开始** | 简报预判三座 hook 之首；消灭「拒绝→重试开始」零帧段 |
| 连续拒绝 + 重试 | **聚合**（N→1） | 同一 `repair` 活动保持 active（seq 递增的 refresh 帧可选；v1 建议不逐次刷） | 规则 3；一轮修复是一个用户语义单元 |
| 修复后接受（L12/L10） | **暴露**（配对） | `repair` 活动 completed + 被接受调用自己的活动正常开始 | 显式终态 |
| exhausted（L14） | **暴露**（终态） | `repair` 活动 failed；cannot-do 行照旧（信封职责不变） | 旗舰 negative：不得留 dangling active |
| bare reply（L13） | **过滤**（1→0） | 无活动帧 | 纯散文回合没有工作可观察 |
| reasoning（L2）/ 心跳（R9）/ 多余调用（L15）/ 摘要日志（L16） | **过滤**（1→0） | 永不上帧 | 保温/簿记信号，零信息量；CoT 禁令 |
| checkpoint（L11/R3） | **不动**（互不消费） | 现役 `assistant.checkpoint` 帧不变 | ADR-085 言语族近亲，Assistant Conversation 层；合同明文共存不重设计 |
| question.preview（R10） | **不动** | 现役帧不变 | 同上，pill 是它的面 |
| 相位帧五值（R1/R2/R4/R5/R6） | **保留 = System Status** | `assistant.thinking` 相位协议不动（I-PFA-06 三形态照旧） | 三概念分家：宏观态继续由相位承担，活动流是追加在其旁的里程碑层 |
| 迭代边界（loop 索引） | **内化**（不直接暴露） | 投影的排序/聚合骨架（deterministic ordering 的事实源） | 规则 5 的排序事实；迭代号本身不是用户语义 |

### P3. 输入事实 + ownership（投影零新推理——每个输入都是已有 owner 的已发射事实 + 三座新 hook 点）

| 输入事实 | Owner | 座位 / 通道 |
|---|---|---|
| 工具调用 name-known / 参数校验通过 | Agent Runtime（ToolLoopAgent） | 既有 `on_tool_call` / `on_tool_ready`（tool_loop.py:239-240） |
| 读被接受 | Agent Runtime | 既有 `on_observe`（tool_loop.py:242） |
| 重试迭代开始 | Agent Runtime | 既有 `on_repair`（tool_loop.py:241） |
| **拒绝当时 + 拒绝类（4 类）** | Agent Runtime | **新 hook 点①**（L5-L8 既有 structlog 座位旁 additive `_emit`——runner 侧看不到 L5/L6/L7，[PROVEN] 必须在内核发射，见 U1） |
| **终态接受** | Agent Runtime | **新 hook 点②**（L12 accept 点；runner 亦知其自己执行的结果，但 loop 级发射对所有 agent 同形） |
| **迭代边界（index + 起因 initial/retry/continuation）** | Agent Runtime | **新 hook 点③**（loop 顶部；只有 loop 知道迭代索引，[PROVEN]） |
| 读活动文案键（`activity_key`） | Agent Interface（perception registry） | `perception/__init__.py:62-156`——投影**引用**不复制 |
| 计划形/终态工具集合成员 | Agent Interface（turn_tools 声明） | turn_tools.py:40-131——kind 映射的 canonical owner 归位见 U6 |
| 回合终局（completed/failed） | Transport（routes） | `_sse_pump` 终帧 tuple（routes.py:262-275）——投影的终帧清扫触发 |

**边界纪律**：Activity Projection 只消费上述事件流——零 DB、零 Domain 读、零 Lifecycle 谓词调用（grep 可证，验收标准）；首版内存态（回合级实例，随 SSE 生成器生灭），不写库不回放（合同明文）。

### P4. 输出 contract（活动帧 schema + 活动本体论 v1）

**新 SSE 帧类型（additive，既有帧全不动）：**

```
event: assistant.activity
data: {
  "activity_id": "a3",      // 回合内稳定身份（规则 5）
  "seq": 7,                 // 回合内单调递增帧序号（deterministic ordering）
  "kind": "read" | "draft" | "run" | "repair",
  "status": "active" | "completed" | "failed" | "cancelled",
  "key": "chat.inspecting.music" | null   // 文案键；kind 级静态文案时 null
}
```

- **状态翻转 = 同 `activity_id` 的新帧追加**（append-oriented：客户端维护有序 map，历史永不改写）；一个活动恰好经历 active → 一个终态（completed / failed / cancelled）。
- **终帧清扫律（I-PFA-06 终帧律的活动同形）**：信封（`turn.completed` / `turn.failed`）落地前，投影为一切仍 active 的活动发关闭帧（completed 路径清扫为 completed 属防御——正常时 accept 帧已先行；failed 路径清扫为 failed）；客户端信封到达同样兜底清扫。**任何活动不得比回合活得久。**
- **零泄漏白名单**：帧字段集合 = {activity_id, seq, kind, status, key}，永无参数 / 结果 / 推理文本（测试矩阵 T11 断言）。
- **kind = 用户语义类别，永不退化为 tool name**（2026-09-19 用户裁定）：`get_transcript` / `present_plan` 式 kind 永禁——那是 Tool Log 换皮。kind 词表（read / draft / run / repair，可扩）表达「Agent 在做什么类工作」；**key 才是 user-safe vocabulary identity**（多个 tool 可聚合进同一 kind/key 的活动实例）。语义分工：activity_id = 实例是谁；seq = 顺序；kind = 用户语义类别；status = 生命周期；key = 文案身份。
- **连续性 ≠ 周期刷新**（2026-09-19 用户裁定）：不为「看起来活着」每几秒造帧——连续感来自 active 活动的生命周期 + 真实完成里程碑 + 散文流。`●` 可以合法地持续一段 LLM 时间，只要它最终走向显式终态。
- **ToolLoop 只产 internal Loop Events，永不引用 Activity 词汇**（U1 裁定）：loop 内核只发「发生了什么」（tool_rejected / terminal_accepted / …）的 typed 事件；「这对用户意味着什么」完全由 Activity Projection 裁定。Agent Runtime 不知道、也不得知道 Presentation 词汇。
- **cancelled 的 v1 可达性**：schema 保留为合同完备；v1 无发射路径（断连/abort 都取消任务，无法向已断开客户端发帧，routes.py:367-372——[PROVEN]，见 U10）。
- **载体**：既有队列直过（`_sse_pump` 字符串透传不动）；chat 与 answer 两条流共用同一投影器形状（hooks 同构，routes.py:318/:403）。
- **文案 canonical owner**（规则 9 落地，座位见 U6）：kind→文案键映射由 Activity Projection 模块单点拥有；read 的 key 引用 perception registry `activity_key`；前端 i18n 新家族 `chat.activity.*` 镜像（现役 `chat.thinkingPhases.repairing` 等已是活动形态文案，迁引不新造——U7）。

**活动本体论 v1（四 kind）**：`read`（感知族调用）/ `draft`（计划形调用的起草+dock/落地段）/ `run`（run 出生段）/ `repair`（修复轮，聚合 N 次拒绝）。**decision/composing 窗不进 Activity**——建议归 System Status（相位族保留），见 U4。

### P5. Consumer 迁移清单（additive → 并行渲染 → switch，每步独立 commit）

| 步 | 座位 | 动作 |
|---|---|---|
| ① 服务端 additive | `app/chat/activity.py`（新，投影器纯核）+ routes.py hook 接缝（`_make_tool_hooks` 旁新增活动接线）+ tool_loop.py 三座 additive hook 点 | 活动帧上流；**相位帧、preview、checkpoint 全不动**；纯 pytest 全绿 |
| ② 客户端解析 | `lib/chat-stream.ts:188-215` 新增 `assistant.activity` 分支 → `onActivity` 回调 | 零 UI 变化 |
| ③ 累积结构 | ChatDock：回合级 `activities` 有序 map state（信封时刻定档为静态历史）；终端清扫客户端兜底 | 零 UI 变化（state only） |
| ④ Chat Activity UI 并行渲染 | dock 内追加式流新组件（StatusLine 座不动） | 剧本 + 产品试用验证 |
| ⑤ switch | 单槽 ThinkingRow 的 **Activity 职能**退役——`thinkingPhase` 收窄为纯 System Status（base Thinking…/composing 宏观态保留；drafting/inspecting/repairing/creating_run 的里程碑职能由活动流承担） | revert = 回退本 commit |

**明确豁免（不动，附理由）**：
- RunTaskList / run 事件流——执行运行时可见性，已是追加式，非 chat 回合活动。
- question.preview / checkpoint 路径——Assistant Conversation 层（ADR-085 共存互不消费）。
- I-PFA-06 相位清除协议——System Status 的生命周期纪律，原样保留。
- trigger 回合（U2）/ JSON one-shot 路径（U3）——无流可挂。
- ChatDock 本地 `Phase` 表单机（U8）——Phase 3 归位时再议。

### P6. 纯函数测试矩阵（投影器纯核：输入 = 有序内部事件序列，输出 = 帧序列；零 DB 零 LLM）

| # | 输入组合 | 期望 |
|---|---|---|
| T1 | 单次读：name-known(read) → observe | active(key=activity_key) → completed；同 activity_id；seq 单调 |
| T2 | 两次读链 | 两个活动，身份互异，顺序 = 事件顺序 |
| T3 | 读 name-known 后参数校验拒绝 | 该 read 活动 cancelled（显式终态，不留 dangling）+ repair 活动 active |
| T4 | 两次拒绝后接受（聚合 N→1） | 恰好一个 repair 活动：首次拒绝 active → 接受时 completed |
| T5 | exhausted（全拒绝到上限） | repair 活动 failed（显式终态）；无 dangling active |
| T6 | bare reply 回合 | 零活动帧（1→0 合法） |
| T7 | 计划形调用：name-known → accept | draft active → completed |
| T8 | start_run：name-known → accept | run active → completed |
| T9 | 终帧清扫：turn failed 时仍有 active | 信封前全部关闭（failed）；completed 时清扫为 completed（防御路径） |
| T10 | 过滤：reasoning / 心跳 / observation 文本 / checkpoint / ask_user / answer | 零活动帧 |
| T11 | 零泄漏白名单 | 任意事件序列下，帧载荷键 ⊆ {activity_id, seq, kind, status, key}；值扫描无参数/结果/推理串 |
| T12 | 确定性 | 同事件序列 → 字节级同帧序列（纯函数） |
| T13 | 排序稳定性 | seq 严格递增，与 delta/相位帧交错无关（活动 seq 自域） |
| T14 | 相位共存 | 投影器不触 on_phase 通道——同输入下相位帧序列与无投影时逐字节一致 |
| T15 | **旗舰 negative**：拒绝 → 重试 → 再拒绝 → exhausted | repair 活动恰好一次 active、恰好一次 failed 终态；全程无双 active、无 dangling |
| T16-A | **盲窗不变量（Blind-window，U5 裁定双不变量之一）**：多迭代回合未终态的每个事件时刻 | 有工作在执行 ⇒ 至少存在一个 active user-safe 活动 ∨ 散文在流——「存在 active 活动」是必要非充分条件 |
| T16-B | **活性不变量（Activity liveness，U5 裁定双不变量之二）**：任意 active 活动 / 回合终局 | 每个 active 活动最终必达 completed / failed / cancelled（显式终态或终帧清扫）；`turn.completed` 时 active 活动数 = 0——**dangling 活动结构性不可能** |

**外加静态审计（验收标准落形）**：`activity.py` 无 DB import、无 lifecycle 谓词调用（grep 可证）；打字机律回归 = 剧本 SSE 通道（chat_scenarios.py:203-233 已有 S10 帧序断言）扩展断活动帧序（**用户自跑**）。

### P7. 上报项 → 用户裁定落档（2026-09-19，**PASS WITH CONDITIONS**，裁定原文要点并入各节）

- **U1 → 批准。** 拒绝 / repair / iteration boundary 的增量 hook **不违反「ToolLoopAgent 零重写」**——「重写内核」与「在既有生命周期节点加 instrumentation hook」是两回事。**冻结边界**：ToolLoop 只产出 typed internal Loop Events（`tool_rejected` / `terminal_accepted` / `read_accepted` / `loop_exhausted`，iteration 边界的两个起因已由既有 `on_repair` / `on_observe` 覆盖），**不得引用 Activity 词汇、不得构造 user-facing activity、不得触碰 Presentation**；「发生了什么 → 对用户意味着什么」的翻译全部归 Activity Projection。通道形态 = 明确 typed union，**禁万能 dict**（防未来 30 种事件无限塞入）。
- **U2 → 确认出范围。** trigger 回合无流可挂（trigger_turn.py:384-389）；其可见性 = 落库 review 行。v1 不覆盖。
- **U3 → 确认。** 活动流 v1 = SSE-only；JSON one-shot 路径零帧；剧本 SSE 通道（chat_scenarios.py:203-233）承担帧序断言。
- **U4 → 批准。** composing / orchestration / decision-window 归 **System Status**，不进 Activity Stream。补充措辞律：它表达「系统正在组织下一步动作 / 整理当前结果」，**永不暗示暴露内部推理**（"Thinking about whether French subtitles are needed…" 式文案永禁）。
- **U5 → 批准「结构性质而非 15s 硬时限」，T16 拆双不变量**（见 P6 T16-A / T16-B）。关键修订：「存在 active 活动」是**必要非充分**条件——一个假活着的活动（active 90s 无终态）同样让用户觉得「它死了」；因此活性不变量（一切 active 必达显式终态、turn.completed 时 active=0）与盲窗不变量同级。附加原则入 P4：**连续性 ≠ 周期刷新**；**kind 必须是用户语义类别，不得退化为 tool name；key 是 user-safe vocabulary identity**。
- **U6 → 座位裁定：kind 映射归 Activity Projection 模块单点拥有**（引用 `PERCEPTION_TOOLS` 与 turn_tools 声明，纯 pytest 做「每个已声明工具名恰好落一个桶」的一致性闸）；routes.py 的 name→phase 双座在 switch commit 收窄（相位面只留 composing / clear / keepalive），残余归位是 Phase 3。
- **U7 → 确认方向，实施期定稿。** `chat.activity.*` 新家族 + read 复用 `chat.inspecting.*`；帧的 `key` 随 status 取态（active 帧带进行态键、completed 帧带完成态键），schema 不变；失败态视觉 = ✗ + destructive，不另造文案族。
- **U8 → 记录在案。** ChatDock 本地 `Phase`（confirm/running/chat 表单机）与 `THINKING_PHASE_*` 同名两义；本 Phase 不动前者，命名归位 Phase 3。
- **U9 → 批准留痕方向。** 信封落地后活动块在回合区域**沉淀为静态历史**（ordered history 语义覆盖回看），视觉形态（收成静态行组）实施期定。
- **U10 → 记录在案。** cancelled 保留在 schema 为合同完备，v1 无发射路径。
