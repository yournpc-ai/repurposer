# R1 Batch 2 — Execution Fencing（执行围栏）

> Status: PLANNED（2026-09-16 建；排期唯一事实源 = `docs/PROGRESS.md` §0.1，本文件只是施工合同）
> **施工范围合同 = `ARCHITECTURE_GATE_2_REPORT.md`（仓库根）§7 IN/OUT 清单 + §13 完成定义 + §15 验收——已冻结，本文件不重述设计、不重新谈判边界。** 行号核验于 HEAD `e8dbced`；开工前以 current HEAD 重新定位。

## 1. Product goal

服务 **J5（失败恢复）**，兼护 J3/J6。

用户故事：执行失败/重试/worker 卡顿恢复时，用户**不被重复扣费**、**已有产物不被污染**、run 的最终判决永远来自合法执行者。

为什么是现在：这是收费的诚实前提——双扣路径不封死，第一个 worker 卡顿事件就是用户账单事故。技术债语言（第二层）：zombie worker 竞态的 race proof 已成立（`POST_T5_DELTA_AUDIT.md` §3.2/§3.3/§3.4）。

## 2. Current state（核验于 e8dbced）

- `workflow_steps` 无 `claim_token` 列（`app/models/tables.py:204-253`）；`outputs` 无 `render_claim_token`（:336-395）。
- execute_step 四尾全部 ORM 按 PK 盲写：成功尾 `app/pipeline/orchestrator.py:1189-1218` / Suspend `:1220-1240` / QualityBounce `:1241-1314` / 失败尾 `:1315-1387`。
- Suspend 的 run 写是全库唯一无 from-state 守卫的迁移：`orchestrator.py:1235-1237`。
- render 终态写谓词是 status 不是身份：`app/pipeline/rendering.py:289-302`（成功）/ `:341-353`（失败）。
- reap 无任何可失效的令牌：`app/pipeline/jobs.py:186-228`（startup）/ `:231-256`（per-tick）。
- `_cascade_skip` 可选中 running 子节点：`orchestrator.py:1408`。

## 3. Gap

写操作不携带「这次执行是谁」——reap 后旧执行者醒来，其终态写没有任何 DB predicate 会失败：step 行最后写者赢、钱包双扣（zombie 的 idem key `:capture:{attempt}` 与合法 Bounce 重跑同族，账本无法区分）、zombie Suspend 可 COMPLETED→WAITING_HUMAN 复活 run。

## 4. Files / modules

- migration（新建，`docs/DATABASE_MIGRATIONS.md` 工作流）
- `apps/api/app/models/tables.py`（两列）
- `apps/api/app/pipeline/jobs.py`（claim 写 token / reap 置 NULL）
- `apps/api/app/pipeline/orchestrator.py`（四尾 + Suspend run 写 + `_cascade_skip`）
- `apps/api/app/pipeline/rendering.py`（三处终态写）
- Gate #2 §7 列出的 **10 处既有 render re-pend 点**（`morph.py` / `node_runners.py` / `verify.py` / `music/node.py` / `captions/node.py` / `dub/node.py` / `reframe/node.py` / `filler/node.py` / `operations/service.py` / `routes/outputs.py`——开工时以 grep 重新枚举，少一处 = morph 竞态洞原样保留）
- `apps/api/tests/`（新增纯函数测试）

## 5. Preconditions

Batch 1（绿基线 + gate 0——本批要加纯函数测试，红基线上加测试不可证伪）。

## 6. Implementation tasks

**严格按 `ARCHITECTURE_GATE_2_REPORT.md` §7 IN 清单施工，逐项对照；OUT 清单全禁。** 摘要（以 §7 为准）：

- T1：migration——`workflow_steps.claim_token UUID NULL` + `outputs.render_claim_token UUID NULL`（可升可降）。
- T2：claim 写 token——`claim_ready_node` / `claim_pending_render` 原子 UPDATE 内 `SET claim_token=gen_random_uuid()`。
- T3：全部失 Paths 置 NULL——两个 reap、retry 重排、QualityBounce 重排、runtime_fanout 重排、Suspend park、`resume_waiting_interrupt`、10 处 render re-pend、`_cascade_skip`。
- T4：execute_step 入口捕获 token（`running 且 token NULL` = 外来行 → 防御性 return）；四尾改条件 UPDATE `WHERE id=:id AND claim_token=:mine` + rowcount 检查。
- T5：Suspend 的 run 写加 expected-from-state（仅 RUNNING→WAITING_HUMAN 可成）。
- T6：render 入口捕获 token（NULL → 提前 return）；三处终态写谓词换 `render_claim_token=:mine`。
- T7：**fenced-零副作用纪律**——rowcount=0 → rollback session → 只记 fenced 日志 → 不 capture / 不 graph sync / 不 cascade / 不 mirror / 不 fire trigger / 不写 run 状态。唯二例外（Gate #2 §7）：`finally` 的 `maybe_finalize_run` 照调；Suspend 问题消息已先落库（孤儿问题 = known residue，登记后续小批，不进本批）。
- T8：部署注记入 commit message——迁移后在途行 token=NULL 由入口防御 return 接住；部署即重启 worker。

**Known residue（登记，不修）**：fenced 执行途中已直传对象存储的媒体对象成孤儿——DB 世界干净、存储世界留垃圾，归后续存储 GC 小批（与 render superseded 删 key 先例 `rendering.py:302-314` 对齐）。

## 7. Do NOT touch

ExecutionAttempt 任何形态 / attempt 语义迁移 / poison-pill（Batch 4a）/ hold GC（R1.1）/ run isolation（Batch 3）/ select_clips 语义 / worker registry / pause-cancel / chat 墙钟 / AgentBudget / 统一 Policy 层 / HITL canonical store。

## 8. Acceptance

- [ ] 纯函数测试（`_StubDb` 模式先例 `tests/test_graph_wiring_pure.py:81-194`）：token 捕获决策（running+NULL → 拒）；rowcount=0 分支 stub 记录调用——capture/graph sync/cascade/trigger/run 写全为 0
- [ ] 手工竞态演练（用户自跑）：A claim → 停滞 → reap → B claim → B 完成 → A 醒 → **A 终态写 0 命中、无第二条 capture、run 行保持 B 判决**
- [ ] render 同型演练（morph 窗口内 zombie 先完成不得覆写）
- [ ] zombie Suspend 不得 COMPLETED→WAITING_HUMAN
- [ ] 单 worker 正常 run / retry / QualityBounce 回归不红
- [ ] migration 可升可降

**Invariant（验收字段，不开新文档）**：I-EXEC-01 stale 执行不写终态；I-EXEC-02 stale 执行零副作用（billing/trigger/graph/cascade/run）。

## 9. Docs update（完成后同批）

- 新增 **ADR-079**（fencing）；修订 **ADR-017**（reap → fencing-aware）/ **ADR-030**（render 认领谓词加身份维度）/ **ADR-050**（guarded-write 纪律）——`docs/ARCHITECTURE_NORTH_STAR.md` §13 已预定。
- `ARCHITECTURE_NORTH_STAR.md` §8.1 四条 P0 中的 1/2/3 翻转为已修；§8.4 claim token PLANNED→CURRENT。
- `docs/PROGRESS.md` §0.1：B2 → DONE + commit。
- 本文件 Status → DONE。
