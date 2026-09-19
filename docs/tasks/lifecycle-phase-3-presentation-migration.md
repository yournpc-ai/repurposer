# Lifecycle Phase 3 施工合同——Presentation Migration（客户端零生命周期推导 + Presentation Contract 归位）

> 拍板：2026-09-19（用户，Architecture Freeze）。架构合同 = `docs/DECISIONS.md` ADR-087（原则 2/3/5 + §6 Dependency Direction）。
> 前置：Phase 1（Lifecycle 投影戳存在——客户端推导的删除有替代事实源）。
> 范围纪律：**只做 Presentation 层归位与推导清除**。不一次性拆 ChatDock / service.py（Non-goal）；Activity 机制（Phase 2）、确认教义（Phase 4）本合同不施工。

## Product goal

Presentation 只消费 projection，客户端不再存在任何 lifecycle 推导：

1. `_read_face` 出 transport、`activity_key` 出工具注册表、`THINKING_PHASE_*` 出 service.py——统一入 protocol / presentation-contract 模块。
2. ChatDock 先拆 protocol adapter 层；状态机与视图可继续同居。
3. prompt 内前端渲染阈值单主化（阈值唯一事实源在代码，prompt 只引用语义）。
4. 静态审计可证：客户端零 lifecycle 反模式。

## Current evidence（锚点已核于 Phase 0 HEAD `d0006ac`；行号会漂移，开工前以 current HEAD 重新定位）

- `_read_face` 住 transport：`apps/api/app/pipeline/routes/projects.py:287-327`（legacy 行 → v3 face 一帧映射——展示语义住在路由文件里）。
- `activity_key` 住工具注册表：`apps/api/app/chat/perception/__init__.py:62+`（展示文案键与工具声明混居——注册项应只持机械事实，copy key 归展示层）。
- `THINKING_PHASE_*` 住 service.py：`apps/api/app/chat/service.py:2177-2198`（展示词汇住应用命令层）。
- ChatDock normalize*：`apps/web/src/components/chat/ChatDock.tsx:278-419`（normalize* 已被路由文件 import——protocol adapter 层的事实存在，抽出即第一刀）。
- prompt 内前端阈值：`apps/api/app/prompts/chat/intent_router_system.j2` DENSITY 段（复制 `singlePlan` 渲染阈值语义——Prompt→frontend 渲染阈值是冻结的禁止方向）。
- 客户端推导残留（Phase 1 switch 完成后本批清除）：`projects.$id.index.tsx:238-244`、`ChatDock.tsx:1251-1253` / `:4415`。

## Contract changes

- ADR-087 §6 依赖方向是唯一合同：`Prompt→frontend 渲染阈值`、`Tool→Presentation`、`Presentation→Domain internals` 均为禁止方向。
- 新模块七问（§十七）预判：presentation-contract 模块拥有「展示词汇与展示语义映射」概念（phase 词汇 / activity copy key / read-face 映射）；写者 = 无（纯声明层）；读者 = Transport / Presentation / Prompt 装配；Domain 与 Application Command 层永不依赖它；层 = Transport/Presentation 交界。落地座位施工时裁定并登记 `MODULE_ARCHITECTURE.md` §7.1；不满足分组准入测试则不开包。

## Files（预判）

- 新建：presentation-contract 模块（候选 `apps/api/app/presentation/` 或既有包的公共层——施工时按依赖方向裁定，**禁新 deferred import**）。
- 迁出：`routes/projects.py::_read_face` → 新模块；`perception/__init__.py` 的 `activity_key` → 新模块（注册项只留机械声明）；`service.py` 的 `THINKING_PHASE_*` → 新模块。
- 前端：`ChatDock.tsx` 抽 protocol adapter 层（normalize* 一族出 4877 行文件，状态机与视图继续同居）。
- prompt：`intent_router_system.j2` DENSITY 段改写为引用语义（阈值数值/条件不出 prompt——单主在代码）。

## Tests（Claude 编写，用户自跑）

- 静态审计（grep 可证，验收主依据）：客户端不再存在——
  - artifact existence → lifecycle（`hasDraftGraph` / `hasRuns` 驱动 worldLive 类）；
  - turn.completed → Canvas；
  - activity → lifecycle；
  - pending_brief → confirm readiness。
- 冷导入探针：presentation-contract 模块不反向 import Domain / Application Command。
- 纯 pytest：`_read_face` 迁移后映射行为不变（既有用例平移）；activity_key 归位后相位帧文案不变。
- tsc：ChatDock adapter 抽出后类型面不变。
- 剧本回归：S5 / S7 / S10 / S11 / S20A 全保留。

## Migration strategy

先立后迁：新模块落地（additive，旧座位留转发）→ 消费方逐座切换（每座独立 commit）→ 旧转发删除。tsc 每 commit 自绿。ChatDock 只抽 adapter，不碰状态机与视图。

## Rollback strategy

逐座独立 commit，回滚 = revert 对应座位的 switch commit（旧转发在迁移期保留）。

## Acceptance criteria

- 静态审计四类反模式 grep 零命中（见 Tests）。
- `_read_face` / `activity_key` / `THINKING_PHASE_*` 单一座位，全仓引用同一源。
- prompt 内无前端渲染阈值数值（DENSITY 段只引用语义）。
- ChatDock protocol adapter 层独立成文件，行为零变化（tsc + 剧本）。

## Prohibited Behaviors

- 禁止一次性拆 ChatDock（只抽 adapter 层；状态机/视图拆留 Phase 6）。
- 禁止一次性拆 service.py（Phase 6 的事）。
- 禁止为目录漂亮移动文件（每一次移动必须有依赖方向理由）。
- 禁止顺手改产品语义（迁移 = 平移，措辞/阈值/行为零变化；发现漂移必须上报，不顺手修）。
- 禁止新增 deferred import 来修依赖（改走 explicit protocol / 重排 ownership）。
- 禁止本批改 Activity 机制（Phase 2）与确认路径（Phase 4）。

## 收尾报告格式（每 Phase 同律，§十六）

Goal / Current evidence / Contract changes / Files / Tests / Migration strategy / Rollback strategy / Acceptance criteria / Status（日期 + commit 范围 + 验证状态——compileall / import 探针 / tsc / 剧本 = 用户自跑，报告标注「未跑验证」项）。

## Docs update（同批）

- ADR-087 Consequences Phase 3 行回填 + commit 范围。
- PROGRESS §0.2 状态行更新；`MODULE_ARCHITECTURE.md` §7.1 登记新座位。
- prompt 面若动：prompt_gate 必过（ADR-071 T2）。

## Status

PLANNED（2026-09-19 建档，未开工；前置 = Phase 1 全闭环）。

**PREFLIGHT PASS / READY（2026-09-19，四路并行只读取证 + 主线复核，锚点 `3ca6f76`）**：客户端 lifecycle 推导近清零（`hasDraftGraph` 全仓零命中；唯一残存推导族 = ResultsCanvas draft-confirm 卡）；ChatDock 实测 4995 行，其 `phase` 三态机 = 第二台生命周期机（六转换点：ChatDock.tsx:1266-1272/:1309/:1981/:2137/:2518/:2527，无腿离开 running）；四替身相位（drafting/inspecting/repairing/creating_run）发射与消费全枚举待步⑤；Web 测试空洞定位到纯函数缝（activity reducer 对 ChatDock.tsx:1358-1376 / 戳门谓词 / replay 行映射器 :1550-1671 / chat-stream dispatch :211-240——全部 node 环境零 DOM 可测，vitest config 缺失是唯一 setup gap）。简报两处预判被取证修正：`activity_key` 住 perception 注册表**合法**（ChatTool 投影故意丢弃该键，内核永不见——KEEP 不需迁）；`_read_face` 住 `pipeline/routes/projects.py:323`（非 graph_store）且命运是**随 legacy 行清理删除**而非搬迁（DEFER）。

**用户开工裁定（2026-09-19，五条判词）**：
1. **Canvas 不是 Confirmation Seat**——ResultsCanvas.tsx:506-545 / FlowNodeCard.tsx:581-604 的 draft-confirm 卡与 Start 路径**退役删除**（不补戳门——补了就是两个确认座，违反 ADR-070 唯一座位律）；Canvas 管结构与审阅，Confirm/Start 唯 dock pill。
2. **No lifecycle fallback-to-true（P0）**——`lifecycle?.x ?? true` 四站点（ChatDock.tsx:1269/:2167/:3827/:4533）是藏得更深的隐形 Lifecycle Authority；终态 = stamp missing → loading/unknown → 不做 lifecycle decision；兼容期 fallback 必须标记 legacy 且最终删除。必须配纯测试：stamp present / false / missing 三态，证明 missing ≠ ready。
3. **phase 机不整体删除，拆语义**——confirm/running 腿退位给戳；phase 只留 System Status 职责（composing 等）。
4. **creating_run 先验证死窗再删**——极小真实剧本实证「Start → run 活动 → RUNNING」无空窗后才剪线；若死窗真实存在则它收窄为 System Status 而非 Lifecycle。
5. **Activity refresh 蒸发不碰**——v1 turn-scoped 非持久化是合同线，登记为 future product decision。

**施工分三批**（每批独立 STOP）：Batch A = Presentation Authority + Web Contract Seats（退役画布确认座 / 消灭 fallback-to-true / 三面共用戳 + 纯 contract tests）；Batch B = Phase Machine Migration（confirm/running 退位 + 三替身相位退役 + creating_run 死窗实证 + 剧本验证点迁移）；Batch C = Presentation Contract Cleanup（adapter 抽出 / prompt DENSITY 单主 / rendering.py:173 / fallback 终清理）。

**BATCH A 已落地（2026-09-19→20，worktree `worktree-phase3-batch-a` commits `df5de98` 戳谓词 / `e5a95a2` 画布座退役 / `75f0570` stream dispatch 缝 / `ad05a2d` ChatDock 两纯缝）**：

- **判词 1 落地**：Canvas Confirmation Seat 退役——ResultsCanvas draft-confirm 卡整族 / FlowNodeCard DocumentCard 的 price+Start 块 / FlowView 与 types 的 `draftConfirm` 布线 / layout.ts `documentTextHeight` 的 confirm +88 预留 / ChatDockHandle.startPendingPlan / projects 页 handleDraftConfirm 全删（grep 零命中可证）。不补戳门。K4 卡面 prompt 直改的定价确认（promptConfirm）不动——那是另一节拍（判词① 动作住节点内）。
- **判词 2 落地（P0）**：四处 `lifecycle ? … : true` 全灭（ChatDock 挂载相位 / canStartGeneration / planCardVisible / planDock）——统一消费 `lib/lifecycleStamp.ts` 三态谓词（ready/blocked/unknown），stamp missing → unknown → 不做 lifecycle decision（挂载停 chat 相位等戳翻、Start disabled、卡片与 pill 不出现）。projects 页 graphLive 同批切 `isPlanReady`。
- **Web contract seats**：`vitest.config.ts`（纯 node 零 DOM；app vite.config 的 tanstackStart/devtools 插件在 vitest 下挂起——setup gap 已补）+ 三缝抽出（行为零变化）：`activityReducer.ts`（upsert 幂等 / arrival 序 / sweep 零 dangling / per-turn reset）、`historyReplay.ts`（mapHistoryRows + 行词汇单座；恢复不推导 lifecycle 由输出 keys 白名单测试钉死）、`chatStreamFrames.ts`（routeStreamFrame 三通道 dispatch；JSON.parse 留 router 内保 throw 语义）。vitest 52 例全绿（含既有 11）。
- **验证（Claude 自跑）**：vitest 52 绿 / tsc 仅剩 2 处 HEAD 预存错误（ChatDock `typeTargetId = cpId` UUID 模板型 + layout.ts `const y` 自引用——与本批无关，按避让清单上报不修）/ apps/api 纯 pytest 305 绿 / check_gates 全绿（gate 5c 过）/ 剧本 S1+S5+S20 回归。
- **上报项（未顺手修）**：① 服务端 `graph_store._document_frame` 仍按 +88 确认解剖预留出生帧——客户端渲染不再填满，留白合法（reservation law）但镜像已漂移，Batch C 裁决；② HEAD 预存 tsc 错误 ×2（见上）；③ ChatDock 两缝同 commit（ad05a2d）——文件级回滚粒度，非逐座。
- **Batch B/C 未动**：旧相位 token 全保留；ToolLoop / Lifecycle / Activity / Product Domain 零触碰；Activity persistence 不做。
- **A.1 Acceptance 实测 PASS（2026-09-20，四场景种子 + CDP 无头 Chrome 真实驱动，worktree API :8011 + web :3002）**：A 空项目 = 纯聊天面（画布门 `pointer-events-none opacity-0` 在祖先链，无 Start 钮）/ B 全就绪 = 画布 1440×813 可见 + 「Start generation」**enabled**（移动视口 390px 同戳：计划卡两任务行 + pill 同在）/ C 旗舰组合（plan_ready ∧ ¬confirmation_ready，空散文种子）= 画布可见 + Start **disabled** / D 已完成 run = 工作区持续可见、无回翻纯聊天（`hasRuns = latestRun != null` 是单调存在事实非 readiness 门——概念判明成立，「完成 run 翻回聊天」语义错误不存在）。种子/用户/测试进程已清理。**Batch A CLOSED。**
