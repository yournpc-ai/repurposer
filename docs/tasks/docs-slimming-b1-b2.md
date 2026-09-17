# Docs Slimming B1+B2 施工合同——历史物理隔离 + PROGRESS 入口恢复

> 拍板：2026-09-17（用户）。依据：审计报告 `scratch/docs-slimming-audit-2026-09-17.md`。
> 范围纪律：**只做 B1+B2，完成后停**。ADR 瘦身（B3）、架构文档去重（B4）、域文档压缩（B5）、治理收口（B6）**本合同不施工**，完成 B1+B2 后重新审计再评估。
> 性质：这不是新设计，是执行 README 早已承诺的治理规则（"周期结束归档"、"历史在 git"）。**不删除任何事实，只改变 active surface**——全部用 `git mv`，历史可溯。

## Product goal

让新 coding session 的入口链重新成立且变短：

```
README → PROGRESS §0（明确的 active batch）→ 当前 task 合同 → 必要时才读架构文档
```

验收只问四件事（用户自验）：
1. 新 session 从 `PROGRESS §0` 能找到明确 active batch。
2. active docs 不再把 7 周历史当当前上下文（PROGRESS 321KB → ~60KB 量级）。
3. `tasks/done` 不再进入默认施工上下文（移出 docs/tasks/）。
4. 入口到当前任务的阅读链明显变短。

## Current state（审计实证，施工前复核）

- `docs/` 下**无 archive 目录**；README 承诺的"周期结束归档"从未执行（PROGRESS 108 次提交全是滚动追加）。
- `PROGRESS.md` 657 行 / 321KB：当前有效 ~64KB（20%），已完成历史 ~257KB（80%）。
- `docs/REPORT-2026-09.md`：09-01 节点快照，已过期，自带"过期即归档"条款；继任者 = 根目录 `a.md` 草稿（不动它）。
- `docs/tasks/`：活跃位 30 份中 ~23 份已完工未归档；`docs/tasks/done/` 24 份 ~350KB 与活跃文档同域。
- **入口已断链**：R1 四批全 DONE、R1 于 09-17 封板、R1.1 排期挂起（09-16 拍板），§0.5 明文"留周五 09-18 滚动定夺"——新 agent 按"§0 → 当前 batch 合同"进来找不到 active batch。

## B1：历史物理隔离（commit 1）

1. `mkdir docs/archive/`。
2. `git mv docs/REPORT-2026-09.md docs/archive/`。
3. `git mv docs/tasks/done docs/archive/tasks-done`（24 份整体迁出）。
4. tasks/ 活跃位清扫：逐一核对候选简报的批次在 PROGRESS 中已标 ✅/DONE 才移；**拿不准的一律留在原地**。预期移入 `archive/tasks-done/` 的包括：dialog-workflow-b1~b4、arch-overhaul、chat-flow-sequencing、intent-surface-unification、de-dialect-question-machine、flora-parity、persona-identity、output-quality-*、home-skeleton 等（以 PROGRESS 完成标记为准，不以本清单为准）。活跃位应只剩 7 份 R1/R1.1 合同（r1-batch-1/2/3/4a、r1-1-batch-4b/5/c1）± 真在施工的 ± 本合同。
5. PROGRESS 历史切出 → `docs/archive/PROGRESS-2026-cycle1.md`（新文件，头部注明"Cycle 1 历史归档，2026-09-17 自 PROGRESS.md 切出，不再维护"）。切出内容（按节标题定位，**不要按行号**——编辑后行号会漂）：
   - §1.3 近十日交付明细（整节，~117KB）
   - §2 W1~W7 已过去周（~88KB）
   - §2 三个已完成插入批：全流程测试批 / 画布三族批 / 工具 loop+decompiler 批
   - §2 W11 支付批残留节（节内自注"日期为历史记录，已平移为 §0.3 R1.1 B5"——实质内容在 §0.3，此节是纯冗余）
   - §0.5 对账表（随 R1 封板转为历史）
   - §0.1 / §0.2 的 R1 批次完成记录（R1 封板后即为历史；R1.1 挂起状态行**保留在 PROGRESS**，那是当前状态不是历史）
6. PROGRESS 保留：头部 status、§0（B2 滚动）、§1.0~1.2 产品现状（加一行诚实注"快照截至 07-31，交付明细归 archive"）、§2 纵览 + W8~W14 未来排期、需求池、可选需求、§3 外部依赖。
7. 引用清扫：全仓 grep `tasks/done`、`tasks/done/`、`REPORT-2026-09`（docs/、根 CLAUDE.md、apps/ 代码注释），指向改为 `archive/tasks-done` / `archive/REPORT-2026-09.md`；README 文档清单的 tasks/ 行、REPORT 行同步更新。完成后旧路径 grep 必须零命中。

**B1 完成判据**：`git mv` 历史可溯（`git log --follow` 抽查 2 个文件）；旧路径 grep 零命中；PROGRESS 体积降到 ~60~70KB 量级；文档内容零改写（纯移动 + 指针更新）。

## B2：PROGRESS §0 滚动 + 入口恢复（commit 2）

1. §0 重写为现在时：
   - R1 已封板（09-17），DoD/封板账细节已归 archive。
   - R1.1 排期挂起（09-16 拍板）状态明示。
   - **Active batch = 本批（Docs Slimming B1+B2，合同 = 本文档）**；其后注明"下一批待 09-18 周五滚动拍板（候选：运营端 / R1.1 解冻，见 §0.3）"。
   - **诚实纪律：不编造下一批**。如果施工时用户已给出 09-18 决定，以用户决定为准替换。
2. §0.4 执行规则/checklist 中对每次开工有约束力的部分保留，已兑现的批次性条目删。
3. README 入口描述如有变化同步（"新 coding session 入口 = PROGRESS §0 → 当前 batch 合同"保持字面成立）。
4. CLAUDE.md 的 docs/tasks/ 描述行同步新路径。

**B2 完成判据**：四件验收事的 1/2/4 成立（3 已在 B1 成立）；§0 自洽（每个指向的文档/合同都存在）。

## Do NOT touch

- `DECISIONS.md` 一个字不动（B3 的事，含已发现的 12 处翻案残文——记录在审计报告里，不顺手修）。
- 所有其他文档正文（CHAT_ARCH / MODULE_ARCH / NAMING / PRD 等）一个字不动。
- 审计发现的 drift（剧本编号三说法、ADR-025 接口名、ADR-042 Pending 标注、API.md 章节号、DISTRIBUTION 状态行）**本批不修**——它们属于 B3+ 或内容批，只在审计报告里留档。
- 需求池死条目关闭（10 条划线 + 2 条应关未关）**本批不做**，随 B2 之后重新审计评估。
- 不新建 roadmap / 批次编号 / milestone；不给 OPEN 架构债排日期。
- apps/ 代码零改动（除引用清扫命中的注释）。
- 根目录 `a.md` 不动（用户的汇报草稿）。
- `research/` 不动。

## Verification（验证归用户自跑，施工方只做机械检查）

施工方做：旧路径 grep 零命中；`git log --follow` 抽查；`wc -c` 前后对比写入 commit message。
用户自跑：
1. 开一个全新会话，只给"读 README 然后开始工作"，验证它能沿入口链找到 active batch 而不踩历史。
2. `git log --follow docs/archive/tasks-done/<任一文件>` 确认历史可溯。
3. PROGRESS 翻阅一遍 §0 + 需求池，确认无失联引用。

## Docs update（同批）

- README：tasks/ 行、REPORT 行、archive/ 目录登记（新目录必须回本表登记——治理表自己的规则）。
- CLAUDE.md：docs/tasks/ 描述行。
- PROGRESS：§0 滚动（B2 本体）。
- 审计报告 `scratch/docs-slimming-audit-2026-09-17.md` 不动（它是本轮快照；B3+ 重新审计时替换）。
