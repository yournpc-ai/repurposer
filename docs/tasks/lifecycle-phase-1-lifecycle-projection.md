# Lifecycle Phase 1 施工合同——Lifecycle Projection（服务端命名生命周期事实，单点谓词）

> 拍板：2026-09-19（用户，Architecture Freeze）。架构合同 = `docs/DECISIONS.md` ADR-087（§2 Lifecycle Contract + §2.1 Charge Semantics Ready + Reversal Ledger R1/R2/R4）。
> 前置：Phase 0 已确认（ADR-087 + docs 规范化落档）。
> 范围纪律：**只做 Lifecycle Projection**。Activity Projection（Phase 2）、Presentation 归位（Phase 3）、确认教义统一（Phase 4）本合同不施工。

## Product goal

Lifecycle 成为服务端命名的只读投影，客户端零生命周期推导：

1. 素材处理中（PREPARING）：Review Surface 不出现（画布不提前翻页，ADR-086 条款 4 翻案注 R2）。
2. PLAN_READY：Canvas + Confirm Dock **同拍出现**——同一 lifecycle 状态的两个 presentation effects，不是两个独立 readiness predicates；移动端 parity（无画布形态 plan card 是评审面，同一投影戳驱动）。
3. CONFIRMATION_READY=false：Confirm disabled + 信息补全态（如估价进行中：pill 可见不可点）。
4. 刷新 / 跨设备恢复旅程按投影戳决定挂载形态（水合首帧不重播的原则不变）。
5. 转写节点上传即出生、状态随 ASR（缓做项「转写节点 loading 出生」随此批落）。

## Current evidence（锚点已核于 Phase 0 HEAD `d0006ac`；行号会漂移，开工前以 current HEAD 重新定位）

- 客户端画布驱动推导：`apps/web/src/routes/projects.$id.index.tsx:238-244`（`hasRuns` / `hasDraftGraph` / `graphLive` / `worldLive`——artifact existence → lifecycle 反模式主座）。
- Confirm pill 门：`apps/web/src/components/chat/ChatDock.tsx:4415`（`planDock = phase==="confirm" && intentReady && !chatBusy && !singlePlan`）。
- pending_brief 恢复链：`projects.$id.index.tsx:855-864`（parked plan wins 推导）/ `ChatDock.tsx:1251-1253`（phase 初始态推导）。
- 转写节点出生守卫：`apps/api/app/pipeline/graph_fill.py:330-332`（`text = asset.transcript or asset.extracted_text; if not text: return None`——无文本即不出生，ASR 完成前画布无转写节点）。
- 谓词可复用纯函数（已存在，缺的是调用不是能力）：`plan_turn.py:550-562`（`validate_task_list` + `_check_transform_targets` 同语裁决，present_plan 执行内校验座）、`orchestrator.py:804-811`（出生地同款裁决）、`plan_turn.py:305-316`（素材 PENDING/PROCESSING/FAILED 计数）。
- dispatch 谓词现状：`service.py:2122-2147`（plan path 分派三条件）——Lifecycle 投影不改变 dispatch，只命名事实。

## Contract changes

- ADR-087 §2 五态谓词是唯一合同；本批把它落成代码，**不改语义**。
- Reversal Ledger R1（ADR-057 §3 可见性移至 PLAN_READY 起）、R2（ADR-086 条款 4：fold 报价前提保留、翻页时机移后）、R4（ADR-084 补「确认权等 CONFIRMATION_READY」）随本批生效。
- estimate completeness **不是** PLAN_READY 必要条件；`PLAN_READY ∧ ¬CONFIRMATION_READY` 是合法态（信息补全态）。
- 新模块七问（§十七）预判：Lifecycle Projection 拥有「lifecycle facts」概念；写者 = 无（只读计算层，不写 DB）；读者 = Transport（results/graph 响应）→ Presentation；Domain 写路径永不依赖它；层 = Projection。若落地为新文件（候选 `app/pipeline/lifecycle.py`），施工时在 `MODULE_ARCHITECTURE.md` §7.1 代码地图登记；**不加表、不加队列认领源**（不满足分组准入测试则作为现有模块职责扩充，不开包）。

## Files（预判，施工时按依赖方向裁定）

- 新建：Lifecycle Projection 模块（候选 `apps/api/app/pipeline/lifecycle.py`——纯函数谓词族 + 投影戳装配）。
- Transport：`apps/api/app/pipeline/routes/projects.py`（results/graph 响应携带投影戳）。
- Presentation：`apps/web/src/routes/projects.$id.index.tsx`、`apps/web/src/components/chat/ChatDock.tsx`（消费投影戳；**本批只做 switch 消费，旧推导在 dual-read 期保留**）。
- 转写节点：`apps/api/app/pipeline/graph_fill.py`（上传即出生 loading 态节点，状态随 ASR 翻转）。

## Tests（Claude 编写，用户自跑）

- 纯 pytest：谓词分支矩阵（§Preflight P6 全表 T1~T15）——素材 PENDING / PROCESSING / FAILED / COMPLETED；空 transcript；未知语言（language_unknown = 内容事实缺席，U5）；已知语言规则不通过（chain_adjudication_failed，U5）；前置提问挂起；链重裁决失败；估价 NULL；旗舰 negative `PLAN_READY ∧ ¬CONFIRMATION_READY`（T10 active run / T10b scope 未就绪双变体）；四合取项独立性（T15）。
- 剧本：PENDING 素材 dock 存活（S5 / S7 / S10 / S11 / S20A 全保留）+ 投影戳断言新增。
- 预部署门禁顺序：纯 pytest → prompt_gate（本批不动 prompt 面则无新增义务，动了必过）→ chat_scenarios 全量。

## Migration strategy

projection additive → dual-read verification → switch consumer → remove old inference。**不直接删旧逻辑**：

1. 服务端投影戳上线（additive，客户端不消费）；
2. dual-read：客户端同时算旧推导 + 读投影戳，日志/断言比对一致（不一致 = 上报，不自行裁决）；
3. switch consumer：可见性/Confirm 门改读投影戳；
4. remove：旧推导删除（独立 commit，可回滚）。

## Rollback strategy

投影戳是 additive；consumer switch 与旧推导删除是两个独立 commit——回滚 = revert switch（dual-read 期旧路径仍在）。转写节点 loading 出生独立 commit，可单独 revert。

## Acceptance criteria

- 素材处理中：Review Surface 不出现（R2）。
- PLAN_READY：Canvas + Confirm Dock 同拍出现；移动端 plan card 同一投影戳。
- CONFIRMATION_READY=false：Confirm disabled + 信息补全态（估价 NULL 折叠 =「估价随运行」诚实标签，ADR-063 不动）。
- 刷新 / 跨设备恢复旅程按投影戳决定挂载形态。
- 转写节点上传即出生、状态随 ASR。
- 固定不等式静态可证：客户端无 `hasDraftGraph → worldLive` 类推导残留（grep）。

## Prohibited Behaviors

- 禁止进入 graph write gate（本阶段一切改造只在 read-side，ADR-087 §7）。
- 禁止改 C-0/C-1/C-2（Product Graph / rank / frame / 执行序不动）。
- 禁止把 estimate completeness 塞进 PLAN_READY。
- 禁止给客户端留第二个 readiness 谓词（投影戳唯一）。
- 禁止顺手拆 ChatDock（Phase 3 的事）/ 顺手改 Activity（Phase 2 的事）/ 顺手统一确认路径（Phase 4 的事）。
- 禁止新增 deferred import；跨模块取数走 public application command / explicit protocol。
- 禁止 Presentation→artifact existence 推导 lifecycle 的新写点。
- 禁止把「dock payload 存在」当 lifecycle authority（U4 判词：payload-existence → confirmation_ready = task_book exists → confirm 的换皮错误；投影只读字段级 Domain facts）。
- 禁止把旧 frontend predicates 原样集中搬入 projection（门禁一禁令的另一面：搬迁 ≠ 重建——每个谓词必须从 Domain facts 重新推导）。
- 禁止修改 Architecture Contract（ADR-087 本文不动；裁定落档在本文）。

## 收尾报告格式（每 Phase 同律，§十六）

Goal / Current evidence / Contract changes / Files / Tests / Migration strategy / Rollback strategy / Acceptance criteria / Status（日期 + commit 范围 + 验证状态——compileall / import 探针 / tsc / 剧本 = 用户自跑，报告标注「未跑验证」项）。

## Docs update（同批）

- ADR-087 Consequences Phase 1 行回填落地座位 + commit 范围。
- PROGRESS §0.2 状态行更新。
- `MODULE_ARCHITECTURE.md` §7.1 代码地图登记（若新文件落地）。
- NAMING 如有新词入册（§8 准入即登记）。

## Status

IMPLEMENTATION 已批准（2026-09-19 用户验收 Preflight：**PASS WITH 3 CONDITIONS**——U1/U2/U4/U5 裁定落档于 §Preflight P7/P8/P9，ConfirmationScope 字段盘点与 Fact→Owner Matrix 已补齐，方准开工）。Preflight 产物 = 本文 §Preflight 报告 P1~P9。

## 三道硬门禁（2026-09-19 用户拍板，验收时逐条过）

1. **门禁一：先证明 Lifecycle Predicate 能覆盖真实现有路径**——建立 `Current readiness facts → Lifecycle Projection → PLAN_READY / CONFIRMATION_READY` 对账表，逐一检查 PENDING / PROCESSING / FAILED / COMPLETED / 空 transcript / 未知 language / pending prerequisite / 旧 task_book / re-dock / revision / 已有 run 是否都能被新 Projection 明确回答。**禁止为适配旧代码往 Lifecycle Projection 里塞回历史 heuristic**——它只接收已定义好的 Domain facts，不成为新的「垃圾推理中心」。
2. **门禁二：必须先证明「一个真相，多处读取」**——成功标准不是「Canvas 能正常显示」，而是 `Lifecycle Fact → {Canvas, Confirm, Chat, future clients}` 单源多读者；**静态验收硬门禁：客户端旧 lifecycle predicate 数量归零**（grep 可证）。
3. **门禁三：PLAN_READY 与 CONFIRMATION_READY 永不被实现成同一个 boolean**——旗舰 negative case：`PLAN_READY = true ∧ CONFIRMATION_READY = false` 且 UI 合法（估价进行中：Canvas + pill 可见，Confirm disabled），必须进测试矩阵。

## Preflight（先行步骤，不改代码；产物 = 本文 §Preflight 的七项）

1. 找出现有 lifecycle predicate 全集；2. 建立 old → new 对账表；3. 确认 Lifecycle Projection 的输入事实（及其 ownership）；4. 确认输出 contract；5. 列出需要迁移的 consumer；6. 设计纯函数测试矩阵；7. 找出无法由当前 Domain facts 判定的场景（[PROVEN]/[INFERRED]/[UNPROVEN] 标注上报，不自行裁决）。

**Implementation 只有在 Preflight 经用户确认后才开工。**

---

## §Preflight 报告（2026-09-19；只读取证，未改代码；未跑验证——本报告全部结论来自静态阅读）

### P1. 现有 lifecycle predicate 全集

**服务端**（锚点核于 worktree HEAD `83c37c2`）：

| # | 谓词 | 座位 | 语义 | 性质 |
|---|---|---|---|---|
| S1 | `is_pending_plan` | `chat/service.py:1003` 一带 | unanswered task_book 提问行 = 「有挂起计划」 | 事实读法 |
| S2 | `latest_pending_question` | `chat/service.py:982` | dock 重建取最新未答提问 | 事实读法 |
| S3 | dispatch 谓词族 | `chat/service.py:2122-2147` | plan path 分派三条件 | 路由，非 lifecycle 可见性 |
| S4 | 素材计数 → `material_pending_line` | `chat/plan_turn.py:305-316` | PENDING/PROCESSING/FAILED 计数 | **仅 prompt 行**（喂 router），无代码门 |
| S5 | 出生地 ∀-check + 同语裁决 | `pipeline/orchestrator.py:804-811` + `pipeline/graph.py:39-130`（`Requirement.missing`） | media/transcript **存在性**（只看 `file_url`/文本列，**不看 processing_status**） | Domain 写门 |
| S6 | `has_active_run` / `RunAlreadyActiveError` | `pipeline/orchestrator.py:835` / create_run 入口 | PENDING/RUNNING run 存在性 | Domain 写门 |
| S7 | worker deferred claim | `pipeline/jobs.py:176` | 素材 PENDING/PROCESSING 时 run 不被认领 | 执行层兜底（非可见性） |
| S8 | transcript 节点出生守卫 | `pipeline/graph_fill.py:330-332` | 无文本即不出生 | 图填充事实 |
| S9 | dock payload 估价戳 | `chat/service.py:1223`（`estimate_credits`）+ `:1244`（stamp/clear draft graph） | 估价随 dock 盖章 | Transport 事实 |
| S10 | trigger 双谓词 | `chat/trigger_turn.py:102/110/330` | in_flight / pending plan 静默 | ADR-080 静默谓词（豁免，见 P5） |

**客户端**：

| # | 谓词 | 座位 | 语义 |
|---|---|---|---|
| C1 | `hasRuns` / `hasDraftGraph` / `graphLive` / `worldLive` | `routes/projects.$id.index.tsx:238-244` | artifact existence → lifecycle 反模式主座 |
| C2 | `runActive` | 同文件 `:269-271` | pending\|running run |
| C3 | pendingBrief → `initialIntent` 恢复 | 同文件 `:855-864` | parked plan always wins |
| C4 | phase 初始态 | `ChatDock.tsx:1251-1253` | initialRunId→running / initialIntent→confirm / chat |
| C5 | `intentReady` | `ChatDock.tsx:1282` | dock intent 可用 |
| C6 | **`canStartGeneration = intent.tasks.length > 0`** | `ChatDock.tsx:2098` | **今天唯一的 Start 门**——无 lifecycle 门、无费用门 |
| C7 | planDock gate / `startDisabled` | `ChatDock.tsx:4415` / `:4424` | confirm 相位 + intentReady + !chatBusy + !singlePlan |
| C8 | `singlePlan` | `ChatDock.tsx:3747` | 密度档（ADR-054，不动） |
| C9 | recall / mobile 可见性 / setPhase 触发点 | `ChatDock.tsx:3529` / `:3734` / `:2449-2458` | 相位机杂点 |

**关键现状结论**：素材就绪今天**没有任何代码门**——S4 只喂 prompt；S5 只看存在性；C6 只看链非空。「PENDING 素材可 Start、run 造出后由 S7 挂起」是现行行为，正是 R2 要在可见性层翻案的对象。

### P2. Old → New 对账表（门禁一）

| 场景 | 今天的行为（证据） | Lifecycle Projection 回答 | 覆盖 |
|---|---|---|---|
| 素材 PENDING | Start 可点（C6 只看 tasks.length>0；S5 不看 processing_status）；run PENDING 由 S7 挂起；S4 仅 prompt 行 | MATERIAL_READY(P)=false → PLAN_READY=false → PREPARING；Review Surface 不出现（R2） | ✅ |
| 素材 PROCESSING | 同上 | 同上（PENDING/PROCESSING 同态） | ✅ |
| 素材 FAILED | S4 告知 router；无代码门阻挡 Start → 可造出注定失败的 run | MATERIAL_READY(P)=false → PREPARING；FAILED 出口引导 = prepare 层职责（上报 U1） | ✅ |
| 素材 COMPLETED | 正常 | MATERIAL_READY=true（文本事实 = transcript/extracted_text/meta.words 任一，消费规则镜像 `graph.py` transcript requirement） | ✅ |
| 空 transcript（ASR 完成无词） | S8 节点不出生；S5 transcript requirement 缺 → 出生地 422 | MATERIAL_READY=false（chain 内容事实不在）→ PREPARING | ✅ |
| 未知 language（transform 链） | 同语裁决在 S5（出生地）+ `plan_turn.py:550-562`（present_plan 校验）二次执行 | **language_unknown = 必需内容事实缺席（U5 裁定）** → MATERIAL_READY=false → PREPARING；不属于裁决失败 | ✅ |
| pending prerequisite 未答 | S1 真 → dock 重建提问；S10 trigger 静默 | PLAN_READY 条件「无挂起前置提问」读同一 unanswered 行事实 | ✅ |
| 旧 task_book（已答/被取代） | S1 假 → 不进 plan 恢复 | 投影只认 unanswered 行 | ✅ |
| re-dock | dock 覆写 pending_brief；C3 parked plan wins | 投影读最新 dock 行重算 | ✅ |
| revision（已有 run 后新计划） | 新 dock + Start；RunAlreadyActiveError 兜底 | 活动 run → RUNNING 态 → CONFIRMATION_READY=false；run 终态后新 dock 重算 | ✅ |
| 已有活动 run | C2 runActive；S6 写门 | RUNNING；CONFIRMATION_READY=false | ✅ |
| 估价 NULL（transform 链编译期） | S9 `estimate_credits=None`；「估价随运行」诚实标签（ADR-063） | Charge Semantics Ready = Deferred 面可呈现（静态文案 + hold 规则），不因此拉低 CONFIRMATION_READY | ✅ |
| **旗舰 negative case**：PLAN_READY=true ∧ CONFIRMATION_READY=false | 今天不存在此区分（C6 一个 boolean） | 实例 = 活动 run ∧ 新计划已 dock 且就绪（revision 窗口）→ plan_ready=true ∧ confirmation_ready=false；UI：Canvas + pill 可见、Confirm disabled | ✅（门禁三） |

### P3. 输入事实 + ownership（门禁一后半：只接收已定义 Domain facts，零新推理）

| 输入事实 | Owner | 证据锚 |
|---|---|---|
| unanswered task_book 提问行（挂起计划存在性 + dock payload） | Agent Interface | S1 / S2 / `service.py:1195-1260` |
| `assets.processing_status` 四态 | Pipeline（asset_processing 状态机） | S4 同款读法 |
| 素材文本事实（transcript / extracted_text / meta.words） | Pipeline | `graph.py` transcript requirement 消费规则镜像 |
| `asset.meta.language`（ASR 后语言事实） | Pipeline | `_check_transform_targets` 读法 |
| 链重裁决纯函数（`validate_task_list` / `_check_transform_targets`） | 既有纯函数（chat/pipeline 共享，公共座位归位 = Phase 5；本批按现状引用） | `plan_turn.py:550-562` |
| `has_active_run` | Pipeline orchestrator | S6 |
| 费用披露事实（`estimate_credits` 戳 / 「估价随运行」标签 / hold 规则静态文案） | Billing 契约（ADR-055）+ Agent Interface dock 戳 | S9 / graph 响应 `estimate_usd_range` |

原则落实：投影**零新推理**——每个输入都是已有 owner 的已定义事实；链裁决复用既有纯函数，不新写 heuristic（门禁一禁令遵守）。

### P4. 输出 contract（投影戳形状；已按 2026-09-19 用户 U4 裁定修订——Implementation 期冻结为 schema）

**CONFIRMATION_READY 的构造律（U4 裁定原文落档）**：

```
CONFIRMATION_READY = PLAN_READY
                   ∧ ConfirmationScopeReady
                   ∧ ChargeSemanticsReady
                   ∧ NoActiveConflictingRun
```

四个合取项各自独立成字段出现在投影戳里——**禁止坍缩成一个 boolean**（门禁三的结构性兑现；「dock payload 存在 → confirmation_ready」被明确否决，投影读的是 payload 内的字段级事实，不是 payload 的存在性）。

```jsonc
"lifecycle": {
  "state": "preparing" | "plan_ready" | "confirmation_ready" | "running",
  "material_ready": false,              // MATERIAL_READY(P)，P = 当前 dock 计划（plan-scoped，U2）
  "plan_ready": false,
  "confirmation_scope_ready": false,    // ConfirmationScopeReady（字段盘点见 P8）
  "charge_semantics_ready": false,      // ChargeSemanticsReady（ADR-087 §2.1 五面可呈现性）
  "no_active_conflicting_run": false,   // NoActiveConflictingRun
  "confirmation_ready": false,          // = 上述 plan_ready ∧ scope ∧ charge ∧ no_run（唯一合成点）
  "blockers": ["material_pending" | "material_failed" | "content_missing"
             | "language_unknown"                       // U5：必需内容事实缺席，非裁决失败
             | "chain_adjudication_failed"              // 已知语言但规则不通过（U5）
             | "pending_prerequisite" | "active_run"],
  "charge": { "known": [low, high] | null, "deferred": true }  // 展示事实，不裁决
}
```

载体：results 响应 + graph 响应携带同一戳（一票源、两处运输）；移动端 plan card 读同一戳（parity）。`blockers` 存在是为了信息补全态文案（CONFIRMATION_READY=false 时 UI 知道说什么），不是第二套谓词。**blocker reason 是一等输出（U1 裁定）：FAILED ≠ generic not-ready——投影必须能表达 blocker reason，本阶段不新增 UI（Presentation 消费归 Phase 3，本批只保证戳里带 reason）。**

### P5. Consumer 迁移清单（门禁二：迁移完成后客户端旧 lifecycle predicate 归零）

**迁移**（switch consumer 阶段改读投影戳）：C1 / C2 / C3 / C4 / C5 / C6 / C7 / C9。其中 C6 整体替换为 `confirmation_ready ∧ 链非空`（空链守卫并入投影，不留本地残余谓词）。

**明确豁免（不动，附理由）**：
- S10 trigger 双谓词——ADR-080 静默谓词读「挂起计划存在性」而非 readiness；R3：trigger 不构成第三条 readiness 路径。
- S3 dispatch 谓词——路由分派 ≠ lifecycle 可见性。
- S7 worker deferred claim——执行层兜底；R2 后 UI 路径不再触达，API 直调仍可能，保留为防御。
- S5/S6 出生地写门——Domain 写路径永不依赖投影（ADR-087 §2），原位保留。

### P6. 纯函数测试矩阵（门禁三旗舰 case 在列；已按 U4/U5 裁定修订）

| # | 输入组合 | 期望 |
|---|---|---|
| T1 | 无挂起计划 | preparing；各 ready 均 false |
| T2 | dock 计划 + 素材 PENDING | material_pending；preparing |
| T3 | 素材 PROCESSING | 同 T2 |
| T4 | 素材 FAILED | material_failed（**独立 reason，不坍缩进 generic not-ready——U1**）；preparing |
| T5 | 素材 COMPLETED 但空 transcript（链需文本） | content_missing；preparing |
| T6 | transform 链 + 未知 language | **language_unknown——必需内容事实缺席（U5：不属于裁决失败）**；material_ready=false；preparing |
| T6b | transform 链 + 已知 language 但同语规则不通过 | chain_adjudication_failed（U5：已知语言但规则不通过才是 revalidation failure）；plan_ready=false |
| T7 | 前置提问挂起 | pending_prerequisite；plan_ready=false |
| T8 | 同语链裁决失败（已知语言） | chain_adjudication_failed |
| T9 | 全就绪 + 估价 NULL | plan_ready=true；charge_semantics_ready=true（Deferred 面可呈现）；confirmation_ready=true |
| T10 | **旗舰 negative：全就绪 + 活动 run** | plan_ready=true ∧ no_active_conflicting_run=false → confirmation_ready=false；state=running；UI 合法（Canvas + pill 可见、Confirm disabled） |
| T10b | 旗舰变体：PLAN_READY ∧ ConfirmationScopeReady=false（scope 字段缺席，盘点见 P8） | confirmation_ready=false 且 plan_ready=true——四合取项独立性的第二证据 |
| T11 | 活动 run + 无新计划 | running |
| T12 | 已答/被取代 task_book | 不参与（等价 T1） |
| T13 | re-dock | 按最新行重算 |
| T14 | 手改面板链（panel dirty） | 投影裁决**存储的** dock 链；手改链由出生地 422 兜底（现行行为不变，见 U3） |
| T15 | 四合取项排列：plan_ready=false 时 confirmation_ready 恒 false（无论其余三项） | 合成点唯一性 |

### P7. Preflight 上报项 → 用户裁定落档（2026-09-19，PASS WITH 3 CONDITIONS）

- **U1 → 裁定：FAILED ≠ generic not-ready。** Projection 必须能表达 blocker reason（`material_failed` 独立成 blocker 枚举值，见 P4）；本阶段不新增 UI（Presentation 消费归 Phase 3）。原「FAILED 出口引导属 prepare 层」结论保留：S4 material line 继续作 router 信号，不加新 UI。
- **U2 → 裁定：不允许把 project-level asset set 写成 MATERIAL_READY 的架构定义。** MATERIAL_READY(P) 必须保持 plan-scoped（「计划 P 引用的资产」）；可以存在 legacy project-scope resolver（v1 实现可先用项目级资产集求解 P 的引用集），但**必须在代码与本文标明兼容性座位**——它是 resolver 的 v1 近似，不是概念定义。概念定义永远是 plan-scoped。
- **U3 [PROVEN] 手改面板链**：投影只能裁决存储的 dock 链；手改链在 Start 时由出生地 ∀-check + 同语裁决兜底（现行行为，不变）。无需新事实。
- **U4 → 裁定：否决「dock payload 存在」作为 lifecycle authority。** CONFIRMATION_READY = PLAN_READY ∧ ConfirmationScopeReady ∧ ChargeSemanticsReady ∧ NoActiveConflictingRun（四合取项，见 P4）；ConfirmationScope 字段盘点 = P8（Implementation 前置，已补齐）。**警戒判词（用户原文落档）**：「task_book exists → confirm」是已经走过一次的错误；「dock payload exists → confirmation_ready」是架构上换皮的同一个错误。本 Phase 建立的方向是 `Domain Facts → Lifecycle Projection → Presentation`，永不是 `Presentation Artifact → Lifecycle`。
- **U5 → 裁定：UNKNOWN_LANGUAGE = required content fact missing**（blocker = `language_unknown`，归入内容事实缺席族，material_ready=false）；**已知语言但规则不通过才是 revalidation failure**（blocker = `chain_adjudication_failed`）。两个 blocker 永不混用。

### P8. ConfirmationScope 字段盘点（U4 裁定的 Implementation 前置产物；锚点核于 worktree HEAD `83c37c2`）

ConfirmationScope = 确认拍呈现给用户裁决的**范围事实集**。盘点结论：每个字段都是已有 owner 的 Domain fact，投影逐字段读取——**不存在「payload 存在即 ready」的捷径**。

| 字段 | 座位 | Owner | 就绪条件（Scope Ready 的组成） | 确认拍消费者 |
|---|---|---|---|---|
| 链（task list） | task_book 行 `intent` 列（`InferredIntent.tasks`） | Agent Interface（dock 时由代码 stamp） | 非空且每 task 结构合法（`validate_task_list` 同款纯函数裁决） | ChatDock.tsx:3837（行渲染）/ :2043 |
| 计划散文 | `intent.answer`（= 提问行 `content`，回声实体化） | Agent Interface | 非空（全文卡律：计划文本 = 提案自身散文） | ChatDock.tsx:3753-3788 |
| 估价戳 | `payload.estimate_credits`（`PlanEstimate{total, per_task}`） | Billing 契约（ADR-055）+ Agent Interface dock 戳 | **非 scope 条件**——归 ChargeSemanticsReady（NULL = Deferred 面，合法） | ChatDock.tsx:4413 / :3738 |
| 派生预览 | `payload.derived` / `pending_brief.derived`（ADR-043 dry-run 投影） | Agent Interface（dock 时 dry-run compile 计算） | **非 scope 条件**——展示事实（空 = 旧行读容忍，不阻塞） | ChatDock.tsx:2446 / :2455 |
| 澄清原因键 | `payload.reasons`（needs_clarification keys） | Agent Interface | **非 scope 条件**——非空时计划本就停在提问态（pending_prerequisite 已覆盖） | dock 渲染（本地化在 render） |
| brief 槽位 | `payload.brief` / `pending_brief.brief`（`Brief`，provenance 槽） | Agent Interface | **非 scope 条件**——slot 未答 = 挂起提问（pending_prerequisite 已覆盖） | 计划回合合并 |
| 角色 pins | `pending_brief.source_asset_id` / `exemplar_asset_id`（ADR-078） | Agent Interface（代码 settle，永不 LLM） | 多视频 remix 时必须已 settle——未 settle 时角色提问 dock 中 = pending_prerequisite 已覆盖 | run start 时 stamp 到 TaskSpec |
| persona | `pending_brief.persona_id` | Agent Interface | **非 scope 条件**——null = Auto，合法 | run.context 钉入 |

**ConfirmationScopeReady 判定（v1）**：链非空 ∧ 结构合法 ∧ 计划散文非空。其余字段或归入其他合取项（估价 → ChargeSemanticsReady），或已被 pending_prerequisite 覆盖（reasons / brief / 角色 pins），或为合法可空（derived / persona）——**盘点结论：ConfirmationScopeReady 不引入任何新事实源，全部读 task_book 行已有 stamp 字段**。

### P9. Lifecycle Fact → Input Fact → Owner Matrix（2026-09-19 用户新增 Phase 1 前置静态产物）

| Lifecycle Fact | Input Facts | Owner | 读法 |
|---|---|---|---|
| PREPARING（默认） | 无挂起计划 ∨ 任何下游条件不满足 | —（缺省态，无输入） | 缺省 |
| MATERIAL_READY(P) | ① P 引用资产集（plan-scoped，U2——v1 可由 project-scope legacy resolver 求解，标明兼容性）② 每资产 `processing_status` ③ 链内容事实（transcript / extracted_text / meta.words，镜像 `graph.py` transcript requirement）④ transform 链目标语言 vs `asset.meta.language` | Pipeline（asset_processing 状态机 / 资产文本事实 / ASR 语言事实） | 纯函数，输入 = 资产行 + 链 |
| PLAN_READY | ① unanswered task_book 行存在 ② MATERIAL_READY(P) ③ 链重裁决通过（`validate_task_list` + `_check_transform_targets` 同款纯函数）④ 无挂起前置提问 | Agent Interface（①④）+ Pipeline（②③的事实输入） | ①④ = 行存在性；②③ = 纯函数 |
| ConfirmationScopeReady | 链 stamp 非空 ∧ 结构合法 ∧ 计划散文非空（P8） | Agent Interface | 字段级读法（否决 payload-existence 捷径，U4） |
| ChargeSemanticsReady | `estimate_credits` 戳（Known）∨ Deferred 面可呈现（静态文案 + hold 规则，ADR-087 §2.1） | Billing 契约（ADR-055）+ Agent Interface dock 戳 | 字段读法 + 静态规则 |
| NoActiveConflictingRun | `has_active_run` | Pipeline orchestrator（S6） | 现有谓词直读 |
| CONFIRMATION_READY | 上述四合取（唯一合成点） | —（合成，无新输入） | 纯合取 |
| RUNNING | 活动 run 存在 | Pipeline orchestrator | 现有谓词直读 |

**矩阵纪律**：每行的 Input Facts 都必须是「已存在、有明确 owner 的 Domain fact」——任何一行若需要新推理 / 新事实源，STOP 上报（门禁一禁令的矩阵形态）。
