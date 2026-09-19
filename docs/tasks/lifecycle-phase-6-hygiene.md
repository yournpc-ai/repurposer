# Lifecycle Phase 6 施工合同——Hygiene（巨文件拆分与残留单主化；永不进关键路径）

> 拍板：2026-09-19（用户，Architecture Freeze）。架构合同 = `docs/DECISIONS.md` ADR-087（原则 5：每个产品概念只有一个 canonical definition）。
> 前置：Phase 1~5 全闭环。**本批最后做，永不进关键路径**——任何 Phase 1~5 的工作不得依赖本批产出。
> 范围纪律：hygiene 只做登记在册的四项；发现新项登记 PROGRESS 需求池，不顺手扩。

## Product goal

1. `service.py`（2416L）/ `schemas.py`（3547L）/ `graph_fill.py`（1534L）拆分——按既有职责缝拆，行为零变化。
2. `Message.intent` typed union（JSONB astext 教训在册——新列/新读面一律强类型）。
3. `apply_edit_ops` commit 律对齐（`operations/service.py:225` flush-only 例外的回滚不对称——审计登记：跳层且回合中 commit，回滚不对称）。
4. 其余 threshold / 词汇单主残留清零（Phase 3 之后仍存的散点）。

## Current evidence

- 巨文件三座（审计实测行数）：`apps/api/app/chat/service.py` 2416L / `apps/api/app/models/schemas.py` 3547L / `apps/api/app/pipeline/graph_fill.py` 1534L。
- `Message.intent` 是 generic JSON 列（无 `.astext`——`messages.intent` 曾致触发回合全静默，坑记录在册）。
- `apply_edit_ops`：跳层且回合中 commit（`operations/service.py:225`，flush-only 律唯一例外，回滚不对称）。
- ChatDock.tsx 4877L：Phase 3 已抽 adapter；状态机/视图同居的拆留本批**评估**（非必做——拆与否以依赖方向理由为准，不为漂亮）。

## Contract changes

- 无新合同。本批是原则 5 的残留清扫，不引入任何新语义。

## Files（预判，施工时逐座定位）

- `apps/api/app/chat/service.py`（按既有职责缝：dispatch / 命令族 / 相位词汇已出 Phase 3）。
- `apps/api/app/models/schemas.py`（按域切分；输出契约 / 请求响应 / 内部模型）。
- `apps/api/app/pipeline/graph_fill.py`（stamp / sync / 文档帧三族）。
- `apps/api/app/models/tables.py` + 读面（Message.intent typed union）。
- `apps/api/app/operations/service.py`（commit 律对齐）。

## Tests（Claude 编写，用户自跑）

- 拆分 = 纯平移：compileall + import 探针 + 纯 pytest 全量回归（行为零变化是验收线）。
- Message.intent typed union：序列化/反序列化用例（旧行读容忍——存量 intent=None / 旧形状行照读）。
- commit 律对齐：回滚对称性用例（失败路径零残留）。

## Migration strategy

一文件一批、一缝一 commit；每 commit 冷启动自绿（import 探针 + 纯 pytest）。typed union 先加读容忍层，再收窄写面，最后收紧类型。

## Rollback strategy

逐 commit revert；拆分批内任意 commit 可独立回退（平移无行为依赖）。

## Acceptance criteria

- 行为零变化（纯 pytest 全量 + 剧本 S5 / S7 / S10 / S11 / S20A 保留）。
- 三座巨文件按缝拆分，无第二事实源产生。
- Message.intent typed union 落地，旧行读容忍。
- apply_edit_ops commit 律与其他写口对称（或登记为显式例外并附理由）。

## Prohibited Behaviors

- 禁止在本批引入任何产品语义变化（hygiene = 平移与收紧，发现语义问题登记上报）。
- 禁止让 Phase 1~5 依赖本批产出（永不进关键路径）。
- 禁止顺手扩登记外项目（新项进 PROGRESS 需求池）。
- 禁止拆分中产生平行事实源（每拆一处，引用同源）。

## 收尾报告格式（每 Phase 同律，§十六）

Goal / Current evidence / Contract changes / Files / Tests / Migration strategy / Rollback strategy / Acceptance criteria / Status（日期 + commit 范围 + 验证状态——compileall / import 探针 / tsc / 剧本 = 用户自跑，报告标注「未跑验证」项）。

## Docs update（同批）

- ADR-087 Consequences Phase 6 行回填 + commit 范围。
- `MODULE_ARCHITECTURE.md` §7.1 代码地图同步。
- PROGRESS §0.2 状态行更新（本批闭环 = 整个 Lifecycle & Interaction Architecture 批次收口）。

## Status

PLANNED（2026-09-19 建档，未开工；前置 = Phase 1~5 全闭环）。
