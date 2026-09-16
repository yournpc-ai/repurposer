# R1.1 Batch 4b — Hold GC（冻结额度回收）

> Status: PLANNED（2026-09-16 建；属 R1.1，**不阻塞 R1**；排期唯一事实源 = `docs/PROGRESS.md` §0.3，本文件只是施工合同）
> 行号核验于 HEAD `e8dbced`；开工前以 current HEAD 重新定位。

## 1. Product goal

服务商业化（R1.1）与 J5 的资金可用性场景。

用户故事：一笔因「生成从未真正开始」而冻结的额度，不会永远卡住——系统能识别它、结算它、退回它。收费后这是资金体验；收费前只是赠额卡住（有 `release_run` 手工救济 + `_release_orphaned_hold` 先例 `orchestrator.py:1479-1488` 兜底），所以本批属 R1.1 不进 R1。

## 2. Current state（核验于 e8dbced）

- hold→capture→release 语义：`app/platform/billing.py`（`hold_run` :255 / `capture_step` :277 / `release_run` :321，idem key 族 + `_mutate` 双层 dedupe :347-412——**永不破坏**）。
- `release_run` 现有调用点 = 终态收官（`orchestrator.py:1502` / `:1609`）+ 删项目（`app/pipeline/routes/projects.py:732`）。**无 GC sweep**——从未启动（PENDING）run 的 hold 永久冻结。
- claim 查询的资产门控：`jobs.py:101-105`——项目仍有 assets PENDING/PROCESSING 的 run **合法停在 PENDING**（长视频 ASR 期间）。**naive `created_at + age` sweep 会误杀合法等待。**

## 3. Gap

PENDING 一词同时承载三种状态：① 用户从未启动；② 已确认但 worker 未开始；③ 等依赖（素材在处理）。GC 的第一交付物不是 timeout 数值，而是**资格丧失谓词**——「这个 hold 从什么时候开始失去继续执行的资格」。

## 4. Files / modules

- `apps/api/app/pipeline/jobs.py`（资格谓词共享定义）
- `apps/api/app/pipeline/orchestrator.py`（GC sweep 座，入 `finalize_stuck_runs` :1721 家族/worker tick）
- `apps/api/app/platform/billing.py`（只调 `release_run`，不改其机制）
- `apps/api/app/config.py`（超龄阈值常量）
- `apps/api/tests/`（新增纯函数测试）

## 5. Preconditions

- **Batch 4a（硬前置）**：asset 终态 FAILED 解开 claim gate，「项目资产已 settled」的判定才有意义。
- Batch 2/3 已落地（R1 停止线之后）。

## 6. Implementation tasks

### T1 — 资格谓词 = claim 谓词的语义镜像（一份定义，两个消费者）
- **Objective**：GC 不自创「看起来差不多」的条件——claim 资格判定一份定义：claim loop 正向找工作，GC 反向找「可认领却长期无人认领」。
- **Seat**：抽取 `jobs.py:84-110` 中与项目资产门控（:101-105）同源的判定为共享定义。
- **Expected behavior**：GC 候选 = `run PENDING ∧ 项目资产全集已 settled（无 PENDING/PROCESSING asset）∧ run.updated_at 超龄`——即 runnable-but-unclaimed。锚点用 `updated_at` 不用 `created_at`。
- **Tests**：镜像一致性纯测试（`test_prompt_registry_consistency` 先例）——claim 谓词与 GC 谓词共用同一份定义，漂移即红。

### T2 — GC sweep
- **Seat**：worker tick（与 `finalize_stuck_runs` 同族座位）。
- **Expected behavior**：候选 run → finalize FAILED（复用既有终态路径）→ `release_run`（idem `run:{id}:release` 防重）。**只碰 PENDING**；RUNNING / WAITING_HUMAN 永不进 GC。
- **Tests**：超龄 PENDING 冻结额 sweep 后归零（ledger 有 release 行）；重复 sweep 幂等。

### T3 — 误杀守卫测试
- ASR 在途（assets PROCESSING）的 PENDING run 纹丝不动；依赖未完成的不动；刚出生的不动。
- 剧本（用户自跑）：造一笔超龄冻结 hold → sweep → 余额恢复 + 台账 hold+release 闭合（S15 先例形态）。

## 7. Do NOT touch

- `_mutate` 双层 dedupe / idem key 机制（永不破坏）。
- RUNNING / WAITING_HUMAN run 的任何状态。
- claim 谓词的业务语义（只抽取共享，不改变谁可被执行）。
- backoff / 多次 GC 节奏设计（tick 即节奏）。

## 8. Acceptance

- [ ] 镜像一致性纯测试绿（谓词一份定义）
- [ ] 超龄 PENDING 的 hold sweep 后归零，ledger 闭合、幂等
- [ ] 三类合法等待（ASR 中 / 依赖未完 / 新生）零误杀
- [ ] 剧本：冻结 → 回收 → 余额恢复（用户自跑）

**Invariant（验收字段）**：GC eligibility 是 claim eligibility 的语义子集（runnable-but-unclaimed ∧ stale）。

## 9. Docs update（完成后同批）

- `docs/BILLING.md`：GC 语义入 hold→capture→release 章节；**ADR-055 修订注记**（新转移「用户从未启动 → 系统终态」，机制小不独立编号）。
- `docs/PROGRESS.md` §0.3：B4b → DONE + commit。
- `docs/ARCHITECTURE_NORTH_STAR.md`：P1-8 行翻转。
- 本文件 Status → DONE。
