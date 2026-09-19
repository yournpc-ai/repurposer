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

PLANNED（2026-09-19 建档，未开工；前置 = Phase 1 全闭环）。
