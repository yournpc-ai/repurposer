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

- 纯 pytest：谓词分支矩阵——素材 PENDING / PROCESSING / FAILED / COMPLETED；空 transcript；未知语言（transform 链）；前置提问挂起；链重裁决失败；估价 NULL；`PLAN_READY ∧ ¬CONFIRMATION_READY`；无活动 run / 有活动 run。
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

## 收尾报告格式（每 Phase 同律，§十六）

Goal / Current evidence / Contract changes / Files / Tests / Migration strategy / Rollback strategy / Acceptance criteria / Status（日期 + commit 范围 + 验证状态——compileall / import 探针 / tsc / 剧本 = 用户自跑，报告标注「未跑验证」项）。

## Docs update（同批）

- ADR-087 Consequences Phase 1 行回填落地座位 + commit 范围。
- PROGRESS §0.2 状态行更新。
- `MODULE_ARCHITECTURE.md` §7.1 代码地图登记（若新文件落地）。
- NAMING 如有新词入册（§8 准入即登记）。

## Status

PLANNED（2026-09-19 建档，未开工；Phase 0 = ADR-087 + docs 规范化，commit 范围见 PROGRESS §0.2）。
