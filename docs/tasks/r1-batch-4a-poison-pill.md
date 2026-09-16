# R1 Batch 4a — Poison Pill / Retry Termination（卡死有终态）

> Status: DONE（2026-09-16 施工+验证绿：T1 migration `a4b7c2d91e05`（`assets.attempt` + `outputs.render_attempt`——命名裁定：outputs 走 render_* 族，`quality.attempt` 异义键防撞；可升可降实测绿）+ T2 claim 计数（两座）+ T3 封顶终态（claim/reap 三处判定，config `asset_max_attempts`/`render_max_attempts` 默认 3；render 封顶连带 fanout 镜像 + 收官）+ T4 一座复位（`jobs.reset_asset_processing`/`reset_output_render`；10 座意图 re-pend 清零 = 新意图新预算，崩溃 reap 不清零）+ T5 纯测试 4 例绿 + 崩溃环演练 14 项全绿（封顶终态+人话行+不再认领+复位后真重开）+ S4 正常素材链回归绿；commit 051ad0e；行号核验于 HEAD `e8dbced`）
> 行号核验于 HEAD `e8dbced`；开工前以 current HEAD 重新定位。

## 1. Product goal

服务 **J5（失败恢复）**的最后一拍：**卡死最终有确定状态**。

用户故事：一个素材处理失败后，不会每次 worker 重启都重新转圈（用户看到一个「处理了三天」的素材）；失败有终态、有人话原因；用户/运营手动「重新处理」是真的重新开始。

为什么是现在：assets/renders 没有执行计数——`claim → provider fail/crash → reap → reprocess → fail → …` 无限循环，每次重启重烧 provider 成本（平台 margin），用户侧永无终态。

## 2. Current state（核验于 e8dbced）

- `Asset` **无 attempts 列**（`app/models/tables.py:140-181`；`:70` 的 attempts 属 `VerificationCode`，无关）。
- `Output` **无 render 计数列**（:336-395）。
- `claim_pending_asset`（`app/pipeline/jobs.py:41-65`）只翻状态不计数；`claim_pending_render`（:145-176）同。
- `reap_stale`（:186-228）startup 全量无条件下发回 pending——`:199-201` TODO 自认「track attempts + backoff… a row that crashes the worker on every run loops forever」。
- 先例：`WorkflowStep.attempt`（`tables.py:244`）+ `NodeBase.retries` 预算（`orchestrator.py:1328-1342`）——节点级已有 fail-safe，本批把同款保护延伸到 assets/renders。

## 3. Gap

两类执行行（asset processing / render）无 attempt 上限 → 崩溃环无界。且手动 reprocess 若只翻 status 不清计数，会得到「FAILED → reprocess → 立即再 FAILED」的假重开。

## 4. Files / modules

- migration（`docs/DATABASE_MIGRATIONS.md` 工作流）
- `apps/api/app/models/tables.py`（两列）
- `apps/api/app/pipeline/jobs.py`（claim 计数 / reap 与 claim 的封顶判定）
- asset 失败终态写点（`app/pipeline/asset_processing.py`——**VERIFY BEFORE CODING** 精确定位）
- render 失败终态写点（`app/pipeline/rendering.py:337-358`）
- 手动 reprocess 入口（assets: `app/pipeline/routes/assets.py`——**VERIFY BEFORE CODING** 现有 reprocess 座位；renders: `app/pipeline/routes/outputs.py`）
- `apps/api/tests/`（新增纯函数测试）

## 5. Preconditions

Batch 2（fencing 先落地——本批给 outputs 加列，避免与 `render_claim_token` 的 migration 相互 rebase；顺序已拍板）。**本批必须先于 R1.1 Batch 4b**（asset 终态 FAILED 解开 claim gate 的 `NOT EXISTS assets ... IN ('PENDING','PROCESSING')`（`jobs.py:101-105`），是 4b GC 谓词成立的前提）。

## 6. Implementation tasks

### T1 — migration：执行计数列
- `assets.attempt Integer NOT NULL DEFAULT 0`；`outputs` 同义一列。
- **VERIFY BEFORE CODING（命名宪法 `docs/NAMING.md`）**：优先 `attempt` 镜像 `workflow_steps.attempt` 先例；outputs 上若与 `quality` JSONB 内 attempt 语义相混，备选 `render_attempt`——施工前裁定，不两存。
- migration 可升可降。

### T2 — claim 计数
- `claim_pending_asset`（`jobs.py:58-63`）与 `claim_pending_render`（:159-164）的认领 UPDATE 内 `attempt = attempt + 1`。

### T3 — 封顶终态
- 认领/reap 处判定：`attempt > 上限` → 终态 FAILED + 人话 error 落行（asset `processing_error` / render `render_error`，走 `user_error_line` 本地化先例），不再可被认领。
- 上限 = `config.py` settings 常量（建议默认 3——**VERIFY BEFORE CODING** 与 NodeBase.retries 现行量级对齐），tick cadence 即既有 backoff（worker 下一 tick = 退避，`orchestrator.py:1323-1327` 注释同款纪律），**不发明退避策略**。

### T4 — 手动 reprocess = 完整 reset 一座
- **Objective**：reprocess 是一个动作：status→PENDING + attempt=0 + error 清空 + 新预算——**一个函数座**，不允许出现第二条只翻 status 的旁路。
- **Seat**：既有 reprocess 入口（T4 文件清单的 VERIFY 项）；无既有座则在对应 routes 内新建一个动词端点。
- **Expected behavior**：FAILED → reprocess → 真的从头再来（不是立即再 FAILED）。

### T5 — 测试
- 纯函数：封顶边界（attempt == 上限 可认领 / > 上限 终态）、reset 语义（计数清零 + 状态复位一体）。
- 崩溃环剧本（用户自跑）：seed 必崩 asset → 有界次尝试 → 终态 FAILED → reprocess → 重新执行。

## 7. Do NOT touch

- backoff 策略（tick 即退避，不发明）。
- error taxonomy（`processing_error` 文本 + 终态已够，分类法等 attempt 数据回来再长）。
- `workflow_steps` 节点级 retry（已有预算，不动）。
- ExecutionAttempt 任何形态。
- fencing 语义（Batch 2 已冻结——本批的计数与 token 是正交两列，互不消费）。

## 8. Acceptance

- [ ] migration 可升可降
- [ ] 纯函数边界测试绿
- [ ] 崩溃环剧本：claim → crash → reap → … → **有界** → 终态 FAILED + 人话 error
- [ ] 手动 reprocess 后真重新开始（新预算、零残留 error）
- [ ] 正常 asset 处理 / render 路径回归不红

**Invariant（验收字段）**：超限 retry 必有确定终态；人工 reprocess = 完整 reset（新预算）。

## 9. Docs update（完成后同批）

- `docs/PROGRESS.md` §0.1：B4a → DONE + commit。
- `docs/ARCHITECTURE_NORTH_STAR.md`：P1-7 行翻转。
- ADR：机制小（计数 + 封顶终态），建议并入 **ADR-017 修订注记**（reap/retry 语义族）；若施工中出现 backoff 类新语义再独立编号。
- 本文件 Status → DONE。
