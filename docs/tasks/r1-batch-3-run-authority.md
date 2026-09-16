# R1 Batch 3 — Run Execution Authority（E′ run 隔离）

> Status: DONE（2026-09-16 施工+验证绿：T1 仲裁座（`resume_waiting_interrupt` 函数体，四入口继承）+ T2 expire 解耦（结算/重获执行权两动作 + 已答分支重试）+ T3 三入口「再挂+明示」（共享 `_resume_ack_line`）+ T4 双触发（`maybe_finalize_run` 收官交接钩 `_resume_parked_answered` + sweep 重试——单 sweep 有 TTL 内搁浅洞，故两做）+ T5 纯测试 `test_run_authority_pure.py` 6 例绿 + S17 剧本绿（a 答题 blocked→明示→交接续跑 / b expire blocked→不造双 RUNNING→重试不重复计数→交接续跑）+ 回归 S14·S4·S13·S15 绿；S6f read-first 流式断言 = 既有 LLM 方差（baseline HEAD 同红 3/4，零假设排除本批）；commit 3e1cbc8；排期唯一事实源 = `docs/PROGRESS.md` §0.1，本文件只是施工合同）
> 行号核验于 HEAD `e8dbced`；开工前以 current HEAD 重新定位。发现合同与代码不一致 → 标记 discrepancy 回报，不自行扩大 scope。

## 1. Product goal

服务 **J6（多轮项目一致性）**，兼护 J4（HITL）。

用户故事：run A 中途被系统提问挂起，用户先去开了新 run B；回头回答 A 的问题（或 30 分钟不答被自动处理）——**A 不得毁掉 B 的任何产物**；等 B 做完，A 可以接着走。

为什么是现在：这是「系统亲手毁用户工作」的通道。挂起-新开-后答是服务员旅程（J3/J4）的自然行为，不是边缘操作。

## 2. Current state（核验于 e8dbced）

- 出生地 invariant 已存在：`has_active_run`（`app/pipeline/orchestrator.py:835-852`）= 一个 project 至多一个 {PENDING, RUNNING} run；`create_run` 持项目行锁后重查（:994-1004）。WAITING_HUMAN **刻意不阻断**新 run（:991-993 注释：挂起的 run 是用户可放弃的）。
- **第二出生通道无守卫**：`resume_waiting_interrupt`（:1422-1448）无项目行锁、无 `has_active_run` 重查，`:1444-1445` 无条件 WAITING_HUMAN→RUNNING。
- **四个调用入口**全部汇入同一个函数：expire sweep `orchestrator.py:1712` / chat `app/chat/service.py:1642` / `service.py:2011` / `app/chat/propose_turn.py:218`。
- expire sweep（:1642-1718）当前 = 结算默认答案（message guarded UPDATE）**然后直接 resume**——它会**自动**制造双 RUNNING：A 挂起 → 用户开 B（合法）→ 30 分钟未答 → sweep 自动 resume A → A 的 select_clips 按 `project_id` **整族销毁 B 的产物**（`app/tools/clips/node.py:304-322`）。

## 3. Gap

「project 执行权 = {PENDING, RUNNING} 至多一 run」是系统出生地自立的法，但 resume/expire 通道不执法。check-then-update 无锁 = 补了 `has_active_run` 也仍有 TOCTOU。

## 4. Files / modules

- `apps/api/app/pipeline/orchestrator.py`（`resume_waiting_interrupt` / expire sweep）
- `apps/api/app/chat/service.py`（两个 answer 入口的 blocked 分支文案）
- `apps/api/app/chat/propose_turn.py`（同上）
- `apps/api/scripts/chat_scenarios.py`（回归剧本）
- `apps/api/tests/`（新增纯函数测试）

## 5. Preconditions

Batch 2（fencing 落地——本批的 resume 座同时是 Batch 2 T3 的 token 置 NULL 点之一，避免同一函数两批各改一遍的冲突；顺序已由 PROGRESS §0.1 拍板）。

## 6. Implementation tasks

### T1 — 唯一仲裁座
- **Objective**：把 project-level arbitration 长进 `resume_waiting_interrupt` **函数体内**——四个入口天然全部继承；**禁止**在各调用点分别补略有差异的 `has_active_run()`。
- **Seat**：`orchestrator.py:1422-1448`。
- **Expected behavior**（原子语义）：
  ```
  SELECT ... FOR UPDATE（project 行锁，create_run :994-996 同款）
  → 重查 has_active_run
  → authority 空：原逻辑（写 spec.answer、node→pending、run WAITING_HUMAN→RUNNING）
  → authority 被占：node 保持 waiting（答案保留），返回 blocked 结果
  ```
- 返回值必须区分「已 resume」与「blocked-parked」，让调用方能说人话。
- **VERIFY BEFORE CODING**：项目行锁与既有会话内其他锁的获取顺序（D9 死锁族纪律——参照 create_run 先例，项目锁先行）。
- **Tests**：纯函数决策矩阵（authority 空/占 × 答案已/未结算）。

### T2 — expire sweep 解耦
- **Objective**：expire ≠ TTL resume；expire = 答案结算 + **尝试**重获执行权。
- **Seat**：`orchestrator.py:1642-1718`。
- **Expected behavior**：默认答案照现逻辑结算进 message（guarded UPDATE，用户答案永远赢）→ 调 T1 仲裁座 → 成功 = resume；**被占 = 保持挂起（answered-but-parked），记日志，后续 sweep tick 天然重试**。已结算答案的 parked 节点不得被再次 expire（选择谓词排除或分支处理——实现选择，合同只要求语义）。
- **Tests**：剧本（T5）覆盖。

### T3 — chat 入口的 blocked 分支人话
- **Objective**：用户答了旧问题但当前有 run 在跑时，听到诚实的一句，不是静默也不是报错。
- **Seat**：`service.py:1642` / `service.py:2011` / `propose_turn.py:218` 的调用点。
- **Expected behavior**：默认路径 = **再挂 + 明示**（「你的回答已收到——等当前生成完成后，这条会继续」）；dock 问题状态如实（已答、排队中）。
- **Tests**：剧本断言文案与 dock 状态。

### T4 — authority 空出后的续跑
- **Objective**：answered-but-parked 的 run 在 B 收官后无需用户动作即可继续。
- **Seat**：expire sweep 每 tick 重试（复用 T2 分支）或 B 收官钩——实现选择，合同要求：有确定性触发器，无永久搁浅。
- **Tests**：剧本覆盖「B 收官 → A 自动续跑」。

### T5 — 回归剧本
- **Seat**：`apps/api/scripts/chat_scenarios.py` 新增场景（INTENT_COVERAGE §6 登记）。
- **Expected behavior**：A 挂起 → B 出生执行 → A 被答/过期 → A 不得成为第二 owner、**B 产物零损失**、A 再挂并明示 → B 收官 → A 续跑。

## 7. Do NOT touch

- A/B/C/D 产品四选（拒答/再挂/abandon/合并）——默认「再挂+明示」以外的选项保持 **OPEN**，本批不实现、不借施工重设计产品语义。
- `select_clips` 删除范围语义重设计（独立产品问题，挂账；本批封的是引爆器不是删除语义）。
- 「project 是否允许多个活跃 run」的产品终局。
- HITL canonical store / 四存收拢（R1 不做）。
- `bail_waiting_interrupt`（终态动作，无需 authority，不动）。
- WAITING_HUMAN 不阻断 create_run 的既有产品语义（**保留**）。

## 8. Acceptance

- [ ] 纯函数决策矩阵绿（空/占 × 已/未结算；blocked 分支零状态污染）
- [ ] 剧本绿：完成定义场景全链（A 挂 → B 跑 → A 答/过期 → 被拒再挂 → B 收官 → A 续跑），B 产物零损失
- [ ] expire 在 authority 被占时不再制造双 RUNNING
- [ ] 既有 S6 checkpoint 族剧本不红（需 dev worker，用户自跑）

**Invariant（验收字段）**：I-EXEC-03 一个 project 在 {PENDING, RUNNING} 中至多一 run；I-EXEC-04 任何进入 {PENDING, RUNNING} 的迁移（出生/resume/未来任何通道）必须在项目级仲裁下原子重查。

## 9. Docs update（完成后同批）

- `docs/PROGRESS.md` §0.1：B3 → DONE + commit。
- `docs/ARCHITECTURE_NORTH_STAR.md`：run 隔离相关五态同步（§8 家族）。
- `docs/INTENT_COVERAGE.md` §6：新剧本行；§3.2 checkpoint 过期行的语义注记更新（expire = 尝试重获执行权）。
- 本文件 Status → DONE。
