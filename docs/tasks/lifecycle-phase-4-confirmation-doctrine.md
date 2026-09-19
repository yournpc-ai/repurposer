# Lifecycle Phase 4 施工合同——Confirmation Doctrine Unification（统一 Paid Authorization path）

> 拍板：2026-09-19（用户，Architecture Freeze）。架构合同 = `docs/DECISIONS.md` ADR-087 §4（Confirmation Doctrine）+ Reversal Ledger R5/R6。
> 前置：Phase 1（CONFIRMATION_READY 投影戳存在——统一确认门有事实源）。
> 范围纪律：**只做 Paid Authorization path 统一**。Agent preparation path 的分叉（plan path vs propose path 各自的准备流程）**保留不动**——消灭的是路径分叉，不是 preparation 差异，更不是新增一个「propose dock」UI。

## 判词（用户拍板原文，禁止重新解释）

> plan path 与 propose path 可以拥有不同的 Agent preparation path，但不得拥有不同的 Paid Authorization path。
> 正确目标：所有新 Paid Work → 统一 Confirmation-ready Product State → 统一 Confirmation Dock。
> 消灭的是路径分叉，不是新增一个「propose dock」UI。

核心：自然语言请求 = Task Intent ≠ Paid Execution Authorization。**明确禁止 G-explicit task request = paid gesture**——即使用户明确指定输出类型/语言/数量/范围/「直接帮我做」，仍只是明确 Task Intent。

## Product goal

1. 一切新 Paid Work：无 explicit confirmation 不 `create_run`。
2. Approved Scope 内 continuation（retry / internal repair / render continuation / execution step completion / approved-scope graph revision）不被误阻塞。
3. 同类型工作 plan / propose 两路收敛同一 Confirmation Dock（统一 Confirmation-ready Product State 驱动）。

## Step 0——先盘点，不是改代码

盘点所有「propose path 直接 create_run」的来源与测试，建立清单（source file / call path / test name / old expected / target / 产品含义），随本批第一份 commit 落 `scratch/` 并附进收尾报告。**未建清单不动代码。**

已知锚点（已核于 Phase 0 HEAD `d0006ac`；行号会漂移）：

| 来源 | 现状 | 产品含义 |
|---|---|---|
| `propose_turn.py:331`（`propose_tasks` → `_create_run_from_tasks`） | chat path 提案直接起 run（caption-mode 解析后即起） | 新 Paid Work 无确认节拍 |
| `propose_turn.py:471`（`edit_graph` 的 run op → `_create_run_from_tasks`） | wiring 提案的 run op 直接起 run | approved-scope revision 与 scope expansion 无分界 |
| `service.py:327-401`（`_create_run_from_tasks`） | 命令层统一起 run 座（出生地 `create_run` 不变） | 范围包含性裁决应住这里（代码裁决，非 LLM 自决） |
| `service.py:1409-1414`（caption-mode fast path） | caption 双标：选项答完直接 dock + Start，绕过 propose_turn 重判 | caption 不拥有独立 Paid Authorization 语义（parity 条款） |
| IC:50 前端 G-explicit 自动 Start | 前端在 reasons 空时自动 Start | R5：翻案退役 |
| `autonomy="review"` 档 | propose path 不可达的死档 | 一并裁决：接线或退役，**不允许继续悬空** |
| `turn_tools.py:88-89`（`propose_tasks` 描述） | 「it never starts a run by itself」= 逐字复制 `present_plan` 的失信文本（实现 `propose_turn.py:331` 恰恰起 run） | 必须与最终实际语义一致 |

## Contract changes

- ADR-087 §4 是唯一合同：Task Intent → Preparation → PLAN_READY → CONFIRMATION_READY → Explicit Confirmation → Paid Run。
- Scope Expansion（新增未确认付费输出 / 新增付费分支 / 超出已确认范围）必须重新 Confirmation；**范围包含性由 Application Command 层代码裁决，不是 LLM 自决**。
- Caption/Non-caption Parity：caption 特殊性仅限参数收集 / 前置提问 / 模式与语言格式选择。
- Estimate：不阻塞 PLAN_READY；Paid Run MUST NOT begin before charge semantics disclosed（ADR-087 §2.1）∧ explicit confirmation accepted。
- Reversal Ledger R5（IC:50 自动 Start 退役）/ R6（ADR-054 §1194 绝对读法胜；密度律不动）随本批生效。

## Files（预判，以 Step 0 清单为准）

- `apps/api/app/chat/propose_turn.py`（propose_tasks / edit_graph 的 run 出口改走确认门）。
- `apps/api/app/chat/service.py`（`_create_run_from_tasks` 范围包含性裁决座；caption fast path 双标拆除）。
- `apps/api/app/chat/turn_tools.py`（propose_tasks 失信描述改写与实际语义一致）。
- 前端：G-explicit 自动 Start 移除（自动起步闸删除，统一走确认拍）。
- prompt：`intent_router_system.j2` / `chat_intent_system.j2` / `turn_tools.py` 描述（quote-before-paid-run 语义——费用语义披露先于付费 run）。
- 剧本：`chat_scenarios.py` 相关剧本改写（propose 直起 run 的旧 expected → 新确认路径 expected）。

## Tests（Claude 编写，用户自跑）

- 纯 pytest：范围包含性裁决矩阵（retry / repair / render continuation / approved-scope revision = 自治；新增付费输出 / 新增付费分支 = 重新确认）。
- 剧本：propose path 新 Paid Work 必须经确认拍；approved continuation 不阻塞；caption 与非 caption 同一授权语义；G-explicit 消息不再自动 Start（裸愿望与明确请求同走确认门）。
- **门禁（ADR-071 T2）**：prompt 面改动必过 `scripts/prompt_gate.py` 三探针；失败先复跑一次（provider 漂移存在），再 A/B 仪器 `scratch/router_ab_probe.py` 二分——**禁止回调阈值凑绿**。
- 预部署门禁顺序：纯 pytest → prompt_gate → chat_scenarios 全量。

## Migration strategy

Step 0 清单 → 命令层范围裁决落地（additive，旧直起路径并行一版）→ propose 两出口切换 → 前端自动 Start 移除 → caption 双标拆除 → 失信描述与 prompt 改写 → 剧本改写。每步独立 commit；prompt 面改动与行为改动分离 commit（prompt gate 可定位回归源）。

## Rollback strategy

逐出口独立 commit，回滚 = revert 对应出口 switch。命令层裁决 additive，旧路径在切换前保留。

## Acceptance criteria

- 一切新 Paid Work：无 explicit confirmation 不 `create_run`（grep + 剧本可证——propose 两出口无直起路径）。
- approved scope continuation 不被误阻塞（S 族剧本回归全绿）。
- 同类型工作 plan / propose 两路收敛同一 Confirmation Dock。
- `propose_tasks` 描述与实际语义一致（失信文本清零）。
- `autonomy="review"` 死档有裁决（接线或退役，不留悬空）。
- prompt_gate 三探针过；chat_scenarios 全量绿。

## Prohibited Behaviors

- 禁止给 propose path 发明第二个 dock UI（统一 Confirmation Dock 唯一）。
- 禁止把范围包含性裁决交给 LLM（命令层代码裁决）。
- 禁止改动 Agent preparation path 的分叉（plan/propose 各自准备流程保留）。
- 禁止让 estimate completeness 阻塞 PLAN_READY（ADR-087 §2）。
- 禁止破坏密度律（ADR-054 不动——单任务 = 纯散文确认仍是确认手势）。
- 禁止顺手拆 service.py / ChatDock（Phase 3/6 的事）。
- 禁止回调 prompt_gate 阈值凑绿。

## 收尾报告格式（每 Phase 同律，§十六）

Goal / Current evidence / Contract changes / Files / Tests / Migration strategy / Rollback strategy / Acceptance criteria / Status（日期 + commit 范围 + 验证状态——compileall / import 探针 / tsc / 剧本 = 用户自跑，报告标注「未跑验证」项）；另附 Step 0 盘点清单全文。

## Docs update（同批）

- ADR-087 Consequences Phase 4 行回填 + commit 范围。
- CHAT_ARCHITECTURE §3（终态工具集）现在时改写（propose_tasks 语义）。
- PROGRESS §0.2 状态行更新。

## Status

PLANNED（2026-09-19 建档，未开工；前置 = Phase 1 全闭环）。
