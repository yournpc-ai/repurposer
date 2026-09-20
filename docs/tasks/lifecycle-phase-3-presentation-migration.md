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

**BATCH B 已落地（2026-09-20，worktree `worktree-phase3-batch-b` commits `755028f` ① confirm 腿 / `840e4d4` ② running 腿 + phase 机退役 / `44b5d4d` ③ 三替身相位 / `046bd9f` ④ CDP 取证 harness / `b9dc6ee` ⑤ creating_run 删除 / `37e252c` ⑥ 剧本迁移）**：

- **三裁定落地**：
  - **裁定 1（confirm 谓词）**：`confirmActive = intentReady && isPlanReady(lifecycle) && !runAttached`（runAttached = `runId != null && !terminal`——活性非存在，终态后修订计划可再举起确认拍）；phase 永不参与 lifecycle 判定；信封→盖章窗口按裁定接受（安全收敛 + zombie-dock 守卫），永不再造 phase authority。pillDock 的 phase 合取判明语义为空（plan_turn.py:812 服务端插话规则），随批摘除。
  - **裁定 2（creating_run 先证后删）**：B4 CDP 取证（`scratch/phase3_b4_seed.py` + `phase3_b4_deadwindow.mjs`，50ms DOM 采样，五类覆盖分类器含散文运动）双场景 PASS——typed Start 32 样本 / G-1 散文 75 样本，dead=0、creatingRunOnly=0；覆盖链 = ThinkingRow 基座 → Activity RUN 里程碑（`chat.activity.run`）+ 散文 → run 叙事面；System Status 的 creating_run label 两 run 零样本出现（发射时刻 Activity 里程碑已是可见面）。B4-d 双 PASS → B4-e 才剪线（`b9dc6ee`）。
  - **裁定 3（无正向相位锁）**：composing 幸存为 System Status 唯一宏观叙事（read→think takeover 不动）；永不建「相位帧 → lifecycle readiness」锁。
- **退役账**：`type Phase` 状态机整体删除（ChatDock）；drafting/inspecting/repairing 三 token 服务端发射器 + 客户端消费 + i18n 双语 key 清零（`chat.inspecting.*` 族合法保留——Activity 读帧复用同注册表）；creating_run 三发射器（plan_turn `_start_run` / service `_create_run_from_tasks` / answer start 分支）+ 常量 + i18n 双语 key 清零（`_create_run_from_tasks` 的 `on_phase` 死参同摘，propose_turn 两 caller 同步）；`THINKING_PHASE_COMPOSING` 保留。
- **剧本迁移（⑥）**：`SCENARIO_ACTIVITY_LEGACY` 逃生舱 + 尾部汇总打印删除；`_work_evidence` 收窄为纯 Activity 通道（co-fire 律失去第二信号）；S10 drafting 相位断言随葬（迁移座位 = 同位 draft Activity 生→收断言）；`_stream_reads` 的 inspecting 相位 print fallback 删除。
- **验收 grep 门全过**：`phase === "confirm"` / `"running"` 在 lifecycle 决策零命中（phase 机已不存在）；drafting/inspecting/repairing token 零（退役谱系注释除外）；creating_run 发射器/常量/key 零；`SCENARIO_ACTIVITY_LEGACY` 零；`_stream_reads` fallback 零；PLAN_READY / CONFIRMATION_READY / RUNNING 各自唯一事实源不变。
- **验证（Claude 自跑）**：vitest 58 绿 / 纯 pytest 305 绿 / API boot 绿 / tsc 2 错 = main HEAD `2d415ba` 预存（layout.ts:441 自引用 + ChatDock typeTargetId 模板串，与本批无关）。
- **B8 全量验证 PASS（2026-09-20）**：check_gates 全绿（gate 5c 随批加固——`confirmActive` 入本地 readiness 名集，裁定 1 派生谓词唯一直读戳形态，正反探针入 `test_check_gates_pure.py`，`8a57b2a`）；活链剧本回归 S1 / S5 / S6(含 f) / S10 / S20(含 A·B) / S21 全绿——S5 首跑单发红（refine 轮 slots 抖动，合并座本批零触碰，复跑即绿）已登记 verification-contracts §4 KNOWN VARIANCE；prompt 面零触碰（diff 可证），prompt_gate 免检；剧本种子自清理无残留（库内 09-16 三条旧剧本残留属历史会话，非本批）。**Batch B CLOSED。**

**BATCH C PREFLIGHT CLOSED（2026-09-20，只读取证 @ `f60ff4b` + 用户两裁定）**：十项取证闭环，裁决与施工切分如下（证据行号 @ `f60ff4b`，行号会漂移，开工重新定位）——

- **C1 删（本批）**：`graph_store._DOCUMENT_CONFIRM_PX`（+88）= 纯几何债——task_book 节点自 B1-lite 读面过滤（`projects.py:399-417`）永不达客户端，server 侧无 frame 读者（graph_fill 只写 text/spec）；client 镜像已随 Batch A 退役（`layout.ts:235-239` 自证 reservation law 合法）。删常量 + role 条件 + `:358-362` 注释块；`test_graph_wiring_pure.py:1278-1282` 断言迁移。**避让**同文件无关两 88（`_FRESH_COLUMN_RISE` :286 间距常数 / port 几何注释 :280）。
- **C2 预留删（DEFER 维持）**：`_read_face`（`projects.py:323`）**不搬迁**（= 为目录漂亮移动文件，Prohibited）。dev DB 实测 `document`×10 + `asset`×5 仍在被映射（分支活）；`generator/processor/agent/modifier/materialize` 分支 dev 零行、**prod UNKNOWN**（守卫查询挂账）。删除扳机 = legacy 五型 + 旧工具集 DB 守卫查询全零。
- **C3 改写（prompt 面，压轴）**：`intent_router_system.j2:30` DENSITY 段——言语分叉改键 agent 自知的链组成 domain fact（one task / ≥2 tasks），**删全部渲染断言**（card/button 出不出、plan 在哪展示、桌面形态）；保留 ADR-070 语义指针（start 控件 = 唯一启动动作）。该段部分断言已失信（"the Start button always appears"——Phase 1 R2 后 pill 以 PLAN_READY 为门）。阈值单主 = `ChatDock.tsx:3550`（不动）。`:26` "plan card's introduction" 保留（语义职责非阈值）。**prompt_gate 三探针必过**（ADR-071 T2，round-robin）+ 剧本 S5/S7/S10/S11/S20A。
- **C4 改写**：`rendering.py:173` 内联双语串 → `USER_ERROR_LINES` 加 `render_superseded` key（`errors.py:91` 既有注册表，单主化），文案逐字平移，行为零变化。不开「展示词汇出 pipeline」大议题（= ADR-069 人话行全家合同翻案，超出本批）。
- **C5 迁移**：`THINKING_PHASE_COMPOSING`（`service.py:2186`）+ `_observe_phase_callback`（`:2189`）→ **`app/chat/system_status.py`**（新文件 = chat 模块职责扩充；**不开 `app/presentation/`**——纯声明层无表无队列认领源，不过 NAMING §7 分组准入测试）。顺带消灭 `propose_turn.py:61` / `plan_turn.py:68` 两条 §6 跨模块私有 import（callback 公开化摘帽）。登记 `MODULE_ARCHITECTURE.md` §7.1 chat 行。
- **C6 落档（docs-only）**：`verification-contracts.md:36`（§2 行）与 `:171`（§6 行）数字 8+13+12 → 实测 **8/14/10/10**（总账 52 吻合）；`DECISIONS.md:2018` Consequences Batch B commit 清单补 `803096b` / `8a57b2a` / `f60ff4b`。
- **C7 补戳（用户拍板 A）**：`projects.py:501-502` 零节点早退补 `lifecycle` 键——「lifecycle 键恒在」不变量（2 行；空项目 blocked vs unknown 今日 UI 零差异）。
- **C8 合同落档（用户拍板 B）**：**代码零改动**——「run 活性/存在 = transport 事实，非 lifecycle 推导」写入 verification-contracts §2 Lifecycle 行注 + ADR-087 Consequences Batch C 行。三读者合法在册：`ChatDock.tsx:1295` runAttached（裁定 1 窗口收敛腿）/ `projects.$id.index.tsx:242` hasRuns / `:271` runActive。**禁补戳读者**（重开裁定 1 信封→盖章窗口）。
- **C9 抽出**：normalize* 族（`ChatDock.tsx:278-470` 九件 + `:163`/`:168` TaskItem/InferredIntent 接口）→ `apps/web/src/components/chat/chatProtocol.ts`（Batch A 三缝同目录同族）。外部消费仅 `projects.$id.index.tsx:14`。状态机/视图零触碰（Phase 6）。
- **C10 sweep 干净**：fallback-to-true / phase 机残留 / 退役 token（除合法 `chat.inspecting.*` i18n 族）/ hasDraftGraph / turn.completed→Canvas / activity→lifecycle / pending_brief→readiness **全零命中**；戳读者 = 三个已登记谓词站点。原 Batch C「fallback 终清理」项已由 Batch B 事实闭环，**无需刀**。

**施工切分（七刀，零代码依赖，每刀独立 commit，回滚 = 逐刀 revert）**：① docs-only（C6 + C8 + C7 文档注）→ ② C1 删 → ③ C4 注册表 → ④ C5 迁移 + §7.1 登记 → ⑤ C9 抽出 + tsc → ⑥ C7 补戳（可并②）→ ⑦ C3 prompt 改写 + prompt_gate（压轴，验证成本最高）。

**验证纪律**：preflight 未跑套件（grep + dev DB SELECT 取证）；施工批验证 = 用户自跑——纯 pytest 305 基线 / vitest 52 / tsc 回 2 预存错（`ChatDock.tsx:2412` + `layout.ts:441`，避让不修）/ check_gates / 剧本 S5·S7·S10·S11·S20A / prompt_gate（刀⑦）。**Batch C READY。**

**BATCH C 七刀已落地（2026-09-20，worktree `worktree-phase3-batch-c` commits `c143ad1` ① / `3d57098` ② / `ed0262e` ③ / `99dc8e7` ④ / `273c2b5` ⑤ / `6e5628a` ⑥ / `1ae164d` ⑦）**：

- **① docs-only（C6+C8+C7 文档注）**：verification-contracts §2 Web 纯缝行 8+13+12 → 8/14/10 + §6 行 historyReplay 13→14 / chatStreamFrames 12→10（实测总账 52 吻合）；DECISIONS Consequences Batch B commit 清单补 `803096b`/`8a57b2a`/`f60ff4b`；C8 拍板 B（run 活性/存在 = transport 事实非 lifecycle 推导，三读者合法在册，禁补戳读者）+ C7 拍板 A（「lifecycle 键恒在」不变量）同批落档（§2 Lifecycle 行注 + ADR-087 Consequences Batch C 行）。
- **② C1 删**：`_DOCUMENT_CONFIRM_PX`（+88）+ role 条件 + 注释块全删；`_TASK_BOOK_ROLE` 保留（graph_fill 5 处在用），仅摘除随删失信注释从句；断言迁移 a*600 role=task_book 308→280（220 触底，旧码 308 牙仍在）。避让两 88 零触碰。
- **③ C4 注册表**：`render_superseded` key 入 `USER_ERROR_LINES`，文案逐字平移；lang 全域 = primary subtag，`startswith('zh')` ⟺ `user_line` 精确命中（与同函数既有 `render_failed` 同一输入同一助手）——行为零变化。
- **④ C5 迁移**：`THINKING_PHASE_COMPOSING` + callback → `app/chat/system_status.py`（不开 `app/presentation/`）；callback 公开化摘帽，`propose_turn`/`plan_turn` 两条 §6 跨模块私有 import 同灭；MODULE_ARCH §7.1 chat 行登记。
- **⑤ C9 抽出**：normalize 族全件 + `TaskItem`/`InferredIntent`/`BriefSlot`/`Brief` 行词汇 → `components/chat/chatProtocol.ts`；ChatDock 回导、`IntentSlot` 随族离舰；外部唯一消费 `projects.$id.index` 改直导。状态机/视图零触碰。
- **⑥ C7 补戳**：`/graph` 零节点早退补 `lifecycle` 键——`ProjectGraphResponse` 两返回路径同形；`_lifecycle_stamp` 对 `conversation=None` 安全。
- **⑦ C3 DENSITY 改写**：言语分叉改键链组成 domain fact（never on what the interface shows）；三处渲染断言全删（含失信 "the Start button always appears"）；ADR-070 语义指针保留（button→control surface-neutral）；阈值单主 ChatDock 不动；provenance 头补注。
- **验证（Claude 自跑，逐刀自绿）**：compileall 全过 / 定向纯 pytest（graph_wiring 64、check_gates+activity 27、lifecycle 22、prompt registry consistency 3）全绿 / 生产 jinja env 渲染探针五断言全过 / tsc 回 2 预存错（避让不修）/ vitest 52/52 绿。
- **未跑验证（用户自跑）**：纯 pytest 全量 305 基线 / check_gates 全量 / 剧本 S5·S7·S10·S11·S20A（S5 在册方差，复跑即绿不算红）/ prompt_gate 三探针 round-robin（刀⑦）。**待验收回填。**
- **尾刀（2026-09-20，用户拍板删）**：preflight 漂移上报项闭环——`intent_router_system.j2` "Never narrate the DAG" 句的渲染断言半句（"the canvas/plan card shows the structure"）与 C3 同标准退役，言语纪律 + speech-role 分工（"your words carry understanding, judgment, and the ask"）原样保留。**新上报（零触碰，待拍板）**：Disclosure 段 "remove it in the plan panel when the card is shown" 的 "when the card is shown" 是同款渲染条件从句（同族残留，验收后不阻塞地裁决）。
