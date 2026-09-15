# POST_T5_DELTA_AUDIT — Delta / Verification Report

> 审计纪律：Current HEAD > previous report · Code > ADR · DB constraint > ORM intention · Actual SQL predicate > function name · Race proof > architecture diagram。

## 1. HEAD

| 项 | 值 |
|---|---|
| current HEAD | `453b73d39f21a653ac0794ce8ec96abe94b754f1`（main，工作树干净） |
| previous audited HEAD | `453b73d39f21a653ac0794ce8ec96abe94b754f1` |
| commits since previous audit | **0**（`git fetch` 后 `origin/main` 同为 453b73d；`git rev-list --count 453b73d..origin/main` = 0） |

**这是本报告最重要的一行：仓库没有移动。**「修复了吗」对每一项的答案在构造上只能是「没有代码变化」。远端 5 条 feature 分支中 2 条 ahead of main（`feat/home-composer-ui-fixes` +1、`feat/music-template-ui` +2），diff 均不触及 orchestrator / jobs / rendering / billing / worker / clips / operations / decompile。

因此本报告的增量价值不是 delta，而是按对抗性纪律对**同一棵树**的重新取证：完整的竞态证明、精确的 WHERE 子句清单、五概念区分、以及**对原报告自身两处错误结论的修正**（§6）。

## 2. P0 Verification

| Issue | Old verdict | Current verdict | Evidence（current HEAD 精确定位） | Severity |
|---|---|---|---|---|
| zombie worker | P0 | **Previous P0 still exists.** 终态写 = ORM 按 PK 赋值，WHERE 只有主键 | `orchestrator.py:1189-1218`（成功尾）/ `1343-1360`（失败尾）；schema 无任何身份列 `tables.py:204-253` | **P0** |
| zombie render | P0 | **Previous P0 still exists，但窗口比原报告窄。** 存在 guarded UPDATE + rowcount 检查，谓词是 status 不是身份 | `rendering.py:289-302`（`WHERE id AND render_status==RENDERING`，rowcount=0 → superseded 丢弃） | **P0（窗口收窄）** |
| suspend resurrection | P0 | **Previous P0 still exists.** 全库 8 个 run 写点中唯一无 guard 的迁移 | `orchestrator.py:1235-1237`（唯一守卫 = `run is not None`） | **P0** |
| operations FK | P0 | **Previous P0 still exists.** schema/migration/删除路径逐字节未变 | `tables.py:423`；migration `e5b8c3d91f07:31`；`clips/node.py:320`；`routes/outputs.py:147`（`db.delete(output)`）；另有两条同类路径 `verify.py:532`、`derivative_dispatch.py:805/822` | **P0** |

## 3. Execution Race Proof

### 3.1 五概念区分（current main 的真实存在性）

| 概念 | 存在？ | 位置 | 被用作终态写谓词？ |
|---|---|---|---|
| status | ✅ | `workflow_steps.status String(20)`（无枚举，`tables.py:230`） | ❌ 只做认领谓词（`jobs.py:93`）和 execute_step **入口**头卫（`orchestrator.py:1148`，进门前查一次，之后永不复查） |
| attempt counter | ✅ | `workflow_steps.attempt Integer`（`tables.py:244`） | ❌ 只被 retry 预算（`orchestrator.py:1330`）和 billing idem key（`billing.py:308`）消费 |
| worker identity | ❌ | 不存在 —— 无列、无实例 id（worker.py 无身份概念） | — |
| execution identity | ❌ | 不存在 —— 无 execution_id / claim_id，任何东西无法区分 attempt-1 的执行与 attempt-2 的执行 | — |
| fencing token | ❌ | 不存在 —— reap 没有任何可失效的东西；`reap_stale_nodes_older_than`（`jobs.py:243-248`）只翻 status，不失效任何令牌 | — |

### 3.2 节点执行竞态（逐步）

```
t0  A claim:  UPDATE workflow_steps SET status='running', started_at=now(),
              attempt=attempt+1
              WHERE id=(SELECT ... FOR UPDATE OF pn2 SKIP LOCKED)   -- jobs.py:84-110
              → N: pending→running, attempt 0→1
              ⚠ 该行记录了「被认领」，但没有记录「被谁认领」

t1  A 进入 execute_step(N)：头卫 status in ("pending","running") 通过
    （orchestrator.py:1147-1148）→ executor 开跑，LLM 计费累积

t2  A 停滞（机器休眠 / 事件循环卡死 / 进程被 SIGSTOP）

t3  900s 后 B 的 per-tick reap:
    UPDATE workflow_steps SET status='pending'
    WHERE status='running' AND started_at < cutoff                 -- jobs.py:243-248
    → N: pending   ⚠ 无 owner 检查；没有任何令牌被失效（无令牌可失效）

t4  B claim：N: pending→running, attempt 1→2 → B 完整重跑 executor（第二次 LLM 计费）

t5  B 成功尾（orchestrator.py:1189-1218）：
    db.get(WorkflowStep, N) → 赋值 output_refs/cost/status='done'
    → capture_step（idem `step:{N}:capture`，prior=0）→ commit
    → maybe_finalize_run：run 行 FOR UPDATE + 终态 early-return（1520-1534）
    → run = COMPLETED，hold release

t6  A 醒来，executor 返回 output_ids_A，进入同一个成功尾：
    node = await db.get(WorkflowStep, node_id)     -- orchestrator.py:1166
    node.output_refs = [A 的产物]                   -- 1189
    node.cost = merge_accrued_cost(node.cost, A)    -- 1194（严格加和，metering.py:65-97）
    node.status = "done"                            -- 1201
    await capture_step(...)                         -- 1212（idem `step:{N}:capture:2`）
    await sync_graph_node_for_step(...)             -- 1217
    await db.commit()                               -- 1218
```

**A 的哪一个 DB predicate 必然失败？—— 没有任何一个。**

A 的终态写是 SQLAlchemy ORM 工作单元，实际 SQL 形如：

```sql
UPDATE workflow_steps
SET output_refs=..., cost=..., status='done', finished_at=..., updated_at=...
WHERE id = :node_id          -- 唯一谓词：主键
```

头卫（1148）在 t1 用过即弃；t6 不再有任何 status / attempt / token 复查。capture 的 NOT-EXISTS 门（`billing.py:366-369`）拦不住——zombie 的 idem key 是 `step:{N}:capture:2`，与 B 的 `step:{N}:capture` **不同 key**，门通过，钱包第二次扣款。

**最终谁有 authority？—— 三方分裂：**
- **run 行**：第一写者赢（`maybe_finalize_run` 的 FOR UPDATE + 终态 early-return 是全库唯一真正围栏的迁移族）→ run 说 COMPLETED（B 的判决）；
- **step 行**：最后写者赢 → output_refs/cost 是 A 的值；
- **graph 节点**：被 A 的 sync 重新聚合，跟随 A；
- **钱包**：扣了两次（A、B 各一条 capture 行，ledger 在设计上无法区分 zombie 与合法 QualityBounce 重跑——bounce-delta 机制用的就是同一个 `:capture:{attempt}` key 族）。

### 3.3 渲染竞态（精确化原 P0-2）

current main 的渲染终态写是**带 rowcount 检查的 guarded UPDATE**（`rendering.py:289-302`）——比节点步骤强。但谓词 `render_status==RENDERING` 是**状态不是身份**：B 的认领会让行重新进入同一个 RENDERING 状态，守卫无法区分 A 和 B。

无害交错：A 停滞 → B 重启 reap（`jobs.py:213-217`，RENDRING→PENDING 只在 startup sweep）→ B 认领同 spec 重渲 → 谁先完成谁赢，内容与 spec 一致，输家 superseded 丢弃。**良性（渲染 $0 定价，无计费影响）。**

腐蚀交错（最小复现）：

```
1. A 认领 O（PENDING→RENDERING），以 spec_v1 POST 渲染服务，停滞
2. B 重启 → startup reap：O → PENDING（jobs.py:213-217，无条件）
3. 一次 morph（去水词/换音乐）落库：O 重写为 spec_v2 + PENDING
4. B 的 claim_pending_render 认领 O → RENDERING；render_output 快照
   的是 spec_v2（rendering.py:243 深拷贝于执行时刻）→ POST v2
5. A 先醒：guarded write WHERE render_status==RENDERING —— B 刚翻过状态，
   命中 → 行 = COMPLETED + A 的 v1 渲染文件 + 行内 spec 却是 v2
6. B 完成：0 命中 → v2 渲染被判 superseded，文件被删（302-314）
   → 行永久展示 morph 前的旧视频，且无任何后续触发器重渲 v2
```

窗口 = worker 重启 + 窗口期内有 morph + zombie 先完成。比节点 zombie 窄，但腐蚀是**静默且持久**的（产物与 spec 不一致，用户无感知）。

### 3.4 Run 复活链（全写点盘点后的结论）

current main 全部 8 个 run 状态写点：

| # | 写点 | 迁移 | 守卫 |
|---|---|---|---|
| 1 | `orchestrator.py:1040`（create_run） | → PENDING | 出生 |
| 2 | `orchestrator.py:1159-1160`（execute_step 头） | PENDING→RUNNING | `== PENDING` ✅ |
| 3 | `jobs.py:118-125`（claim_ready_node） | PENDING→RUNNING | SQL `AND status='PENDING'` ✅ |
| 4 | **`orchestrator.py:1235-1237`（Suspend 分支）** | **任意→WAITING_HUMAN** | **仅 `run is not None` ❌** |
| 5 | `orchestrator.py:1444-1445`（resume） | WAITING_HUMAN→RUNNING | `== WAITING_HUMAN` ✅ |
| 6 | `orchestrator.py:1580`（finalize） | →FAILED | 行锁 + 终态 early-return ✅ |
| 7 | `orchestrator.py:1598`（finalize） | →COMPLETED | 同上 ✅ |
| 8 | `orchestrator.py:1734-1751`（finalize_stuck_runs） | 只筛选，委托 6/7 | 同上 ✅ |

- **COMPLETED → WAITING_HUMAN**：存在，唯一路径 = zombie Suspend（#4）。之后 expire（1800s TTL，`config.py:58`）或用户回答触发 #5 → **RUNNING**。已 release 的 hold 不会回来，第三次执行的 capture 直接吃负余额（真实扣款，永不退）。
- **FAILED → RUNNING**：无直达路径；两跳路径 = zombie Suspend（FAILED→WAITING_HUMAN）→ resume（→RUNNING）同样成立。

### 3.5 Billing 矩阵（第四优先级）

先区分三件事：duplicate execution（无围栏 → 必然）/ duplicate billing row（看 idem key）/ duplicate actual charge（看钱包）。

| 场景 | dup execution | dup billing row | dup actual charge |
|---|---|---|---|
| A/B 先后完成，同成本 | ✅ | ✅（A 落 `step:{id}:capture:{attempt}`，与 B 的 `:capture` 不同 key） | **✅ 是**——`merge_accrued_cost` 严格加和（`metering.py:65-97` docstring 自述 "Additive over whatever the row already carries"），A 的 delta = credits(C_A) > 0 |
| A/B 先后完成，不同成本 | ✅ | ✅ | **✅ 是**——delta = credits(C_A+C_B) − credits(C_B) |
| A/B 同时终态写（同 key 竞态） | ✅ | ❌ 被拦 | ❌ 被拦——NOT-EXISTS 门在行锁唤醒后重估（READ COMMITTED EvalPlanQual）+ `pg_insert.on_conflict_do_nothing`（`billing.py:410`，注释明言就是防这个）→ 干净 dedupe，**不污染调用方 commit** |

结论：zombie 双执行的**主路径（先后完成）= 真实重复扣款**，且 `release_run` 的 remainder 钳制（`billing.py:329-331`）保证多扣永不退。同 key 同时到达的病态子路径已被双层防住。**原报告推论「zombie → duplicate capture → possible duplicate charge」坐实为事实，且原报告「同成本 zombie 被 delta=0 吸收」一句是错的（§6-1）。**

### 3.6 operations FK 最短复现（第五优先级）

current main 仍然存在可实际触发的 FK failure。最短路径：

```
1. run 产出 clip → outputs 行 O
2. 任何一次操作落账：编辑器 set_trim / 字幕样式 / 去水词 morph / undo
   —— operations/service.py:82-95 (_insert_row: output_id=O)；
   _ensure_chain 保证首次触碰即写 baseline 行（98-113）
3. 删除 O，二选一：
   a. DELETE /outputs/{O.id}（routes/outputs.py:147 `db.delete(output)`，无 operations 清理）
   b. 「重新剪」→ 新 run 的 select_clips 全清全项目 clips（clips/node.py:320，无 operations 清理）
4. DELETE FROM outputs WHERE id=O
   → operations.output_id FK NO ACTION（tables.py:423；migration e5b8c3d91f07:31）
   → ForeignKeyViolation → 路由 500 / run FAILED
```

（注：画布产物删除手势已退役，delete API 保留——3a 触发面收窄；**3b 是旅程三「这条剪得不好，重新剪」的头牌路径，现实引爆器。**）

## 4. Fixed Since 453b73d

**无。commits since previous audit = 0，不存在任何修复。**本节的存在只是为了如实记录这个事实。

## 5. Still Open（重新定级，不继承旧等级）

### P0

| # | 问题 | 依据 |
|---|---|---|
| 1 | 节点终态写无围栏（race proof §3.2） | `orchestrator.py:1189-1218/1343-1360`；`jobs.py:243-248` |
| 2 | 渲染守卫 status-based（腐蚀交错 §3.3） | `rendering.py:289-302` |
| 3 | Suspend 迁移无 from-state 守卫（复活链 §3.4） | `orchestrator.py:1235-1237` |
| 4 | operations FK 可实际引爆（§3.6） | `tables.py:423` 等 |

### P1

| # | 问题 | 定级理由 |
|---|---|---|
| 5 | select_clips 跨 run 全清（`clips/node.py:303-321`）+ WAITING_HUMAN 不阻断新 run（`orchestrator.py:987-1004`） | FK 部分已入 P0-4；语义部分（挂人 run 的产物被并行 run 整族销毁）独立成立 |
| 6 | 内部产物无一等住所：latest-20 Python 扫描（`decompile.py:86-98`）、无 hash 索引/唯一约束、warm 行 `step_id=None`（`decompile.py:341`）、version 不进 cache key（lookup 只匹配 asset_hash，99-105） | T5 复用模式规模化即退化 |
| 7 | poison-pill 无 attempt 上限：assets/renders 崩溃环（`jobs.py:199-201` TODO 自认） | 每次重启重烧 provider 成本；节点步骤靠 attempt 膨胀恰好有 fail-safe，assets/renders 没有 |
| 8 | 从未启动 run 的 hold 永久冻结（release 只在终态触发） | 资金可用性问题，有界但真实 |
| 9 | HITL 状态四存 + JSONB 交叉引用（`suspend_payload.question_message_id` 可悬空） | 提问机器每演进一步都要维护四面一致 |

### P2（含重新定级的下调项）

| # | 问题 | 旧级 | 新级 | 理由 |
|---|---|---|---|---|
| 10 | **attempt 只是计数器** | P1 | **P2（下调）** | 逐一检查其消费者：retry 预算（1330）膨胀方向 fail-safe（更早就失败，不是更晚）；billing key 误用是 zombie 的症状，随 P0-1 修复自愈；bounce 循环界同理。**计数器自身不构成任何 correctness 问题**——它是 observability/postmortem 债。attempt 日志并入 P0 修复设计即可，不立独立 P1 |
| 11 | 状态方言三套 + 大小写两套 + outputs.status 客户端可写自由串 | P1 | **P2（下调）** | 大小写分裂自 case-law 注释（`orchestrator.py:1728-1732`）后未再造成活 bug；不挡演进，只是丑 |
| 12 | 文本产物无版本账（payload 不入 operations） | P1 | **P2（下调）** | 是缺失的产品能力（旅程三 undo 覆盖度），不是正确性问题 |
| 13 | T5 缺口族（§7 逐项） | P1/P2 | 见 §7 | — |
| 14 | 文档漂移三处（RENDERING §5 / MODULE_ARCH §7.1+§4 / AGENT_ARCH §4.3）、死代码（StreamingAgent/generate_stream、InferredIntent.action 新写、tone_snapshot、learned_from）、chat 回合无墙钟 | P2 | P2 | 未复验项因零提交与旧报告一致 |

### T5 八缺口逐项判决（第七优先级）

| # | 缺口 | 判决 | current-main 证据 |
|---|---|---|---|
| 1 | latest-20 Python 扫描 | **STILL PRESENT** | `decompile.py:86-98`（`limit(20)` + Python 循环比对） |
| 2 | CRAFT_SCAN_VERSION 不进 cache key | **STILL PRESENT** | `_find_reusable_skeleton` 只比 `asset_hash`（99-105），version 永不参与 |
| 3 | warm 行无 lineage | **STILL PRESENT** | `decompile.py:341` `step_id=None` |
| 4 | canvas 孤儿节点 | **STILL PRESENT** | `Decompile` 类只声明 kind/task_name/agents（`decompile.py:381-391`），无 `node_type/prototype` → `_decl_of` 落默认 **text×manual**（`graph_fill.py:152-153`）；不在 `_PRELUDE_KINDS`（`graph_fill.py:71`） |
| 5 | run 路径不触发 craft 触发回合 | **STILL PRESENT** | `TRIGGER_CRAFT_DECOMPILED` 唯一发座 = warm 新鲜物化（`decompile.py:357`）；run 路径物化（411-505）无 fire_trigger |
| 6 | skeleton 时序结构无消费者 | **PARTIALLY FALSE POSITIVE** | 原报告「无消费者」**说过头**：prompt 侧消费者存在——plan 输入注入完整 `craft_skeleton`（`registry.py:175-178`）、perception 读工具渲染 `hook_device`（`perception/executes.py:462-463`）。准确重述：**确定性参数消费者仍只有 count/aspect/captions/music**（`clips/node.py:225/325/341/368`），时序结构零确定性消费 —— 「结构级 remix 未实现」成立，「无消费者」不成立 |
| 7 | 无 remix e2e 剧本 | **STILL PRESENT** | `chat_scenarios.py` 全文 grep decompile/remix/craft/exemplar = 0 命中 |
| 8 | gaps 无确定性 plan 路径 | **FALSE POSITIVE（按原表述）** | 确定性**注入**存在：`craft_skeleton`（含 gaps）作为只读 facts 固定进 plan 输入（`registry.py:166-178`）。无确定性**强制**——但「纠偏决策由 LLM 做」是 ADR-052 顾问姿态的设计，不是缺陷 |

## 6. New Risks

**453b73d 之后新增的问题：无（零提交，构造上不可能存在）。**

如实登记本次对抗性重读在**同一棵树**上的新发现（不是新代码引入的风险，是原报告的错漏）：

1. **原报告错误：billing「同成本 zombie 被 delta=0 吸收（侥幸）」。** 真相更坏：`merge_accrued_cost` 严格加和（`metering.py:65-97`），两次执行全额各自落账。zombie 的 capture 与合法 QualityBounce 重跑的 capture 用同一个 `:capture:{attempt}` key 族——**账本在设计上无法区分二者**，这不是幂等机制失灵，是它没有区分依据。
2. **同 key 同时 capture 的病态子路径已被防住**（本 pass 验证）：NOT-EXISTS 门 + `on_conflict_do_nothing`（`billing.py:366-412`，注释明言防止污染 execute_step 的 commit）。原报告未覆盖此子路径，本报告排除它。
3. **cascade-skip 可选中 running 子节点**（`orchestrator.py:1408` `status.in_(["pending","running"])`）：zombie 失败级联可以 skip 掉 B 正在合法执行的下游节点；B 的盲写随后又把它翻回 done。**下游行也卷入 last-writer-wins**——原报告只论证了当事节点行。
4. 原报告 T5 #6「时序结构无消费者」与 #8「gaps 无代码路径」两处表述过头（§5-T5 表已修正）。

## 7. Recommended Next Commit

**一个批次：执行身份围栏（claim token end-to-end）+ operations FK 清理（同批第二个小 commit）。**

Commit 1（主体）——把 §3.1 表中「不存在」的三个概念的最小可行子集建起来：

1. migration：`workflow_steps ADD COLUMN claim_token UUID NULL`；`outputs ADD COLUMN render_claim_token UUID NULL`。
2. `claim_ready_node` 的原子 UPDATE 同时 `SET claim_token = gen_random_uuid()`；`claim_pending_render` 同理。reap / re-pend / resume 路径把 token 置 NULL（fencing 语义：让旧执行者的写必失败）。
3. `execute_step` 成功尾 / 失败尾 / Suspend 分支从 ORM 盲赋值改为条件 UPDATE：`WHERE id=:id AND claim_token=:进入时读到的 token`，检查 rowcount；**0 命中 = 丢弃并记日志，且不调 capture_step**——一行改动同时封死双重扣费路径。
4. Suspend 的 run 写加 expected-from-state：`WHERE status IN ('RUNNING')`（PENDING 与终态都拒绝）。
5. 渲染终态写谓词从 `render_status==RENDERING` 换 `render_claim_token=:mine`；morph re-pend 置 NULL。
6. 纯函数套件：guard 构造 + token 匹配分支；验收 = 手工 create_run 全链 + 双 worker 竞态演练（杀一个，验证旧执行者终态写 0 命中、无第二条 capture）。

Commit 2（10 行）：`delete_output` 与 `select_clips` 全清前先 `delete(Operation).where(Operation.output_id.in_(doomed))`（对齐 `projects.py:715` 的既有顺序），附 §3.6 复现路径的回归剧本。

**为什么是它而不是别的**：§3 的四张 race proof 证明 P0-1/2/3 共享同一根因——**写不携带执行身份**；修法是机械加固，零概念发明、不动状态机形状、不动四层地图；W11 支付批（PROGRESS 09-10~09-23）之前必须封死双扣路径；FK 清理移除的是旅程三头牌路径上的确定性 run 失败。attempt 日志、内部产物住所、HITL 收拢全部排在它之后——它们的前置就是「claim 有身份」。

> **Previous P0 still exists.** 最短可复现竞态见 §3.2（节点）/ §3.3（渲染）/ §3.6（FK）。
