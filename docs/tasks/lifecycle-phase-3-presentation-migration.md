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
