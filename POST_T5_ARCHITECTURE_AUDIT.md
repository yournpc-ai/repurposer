# POST_T5_ARCHITECTURE_AUDIT — T5 后架构体检报告

> **日期**：2026-09-16 · **范围**：T5/decompiler 落地后（`9ee3e5d..453b73d`）全库只读审计 · **代码快照**：HEAD = `453b73d`
> **方法**：五个并行审计线程（Agent 边界 / 执行内核 / Artifact·Output / Decompiler·T5 / DB 模型）+ 主线程第一手核对。证据只取代码、表、migration、ADR、Journeys、tests；行号为 HEAD 快照行号。
> **纪律**：文档承诺 ≠ 实际实现处显式标注「⚠ 文档承诺 ≠ 实现」；反例如实列出；不为既有架构辩护；能跑 ≠ 边界正确。

---

## 一、Executive Summary

**总体判断：产品面 / agent 面 / 画布面是健康的；执行内核缺一个所有上层都已经依赖的概念 —— 执行身份（execution identity：attempt / lease / fencing）。这是本审计唯一认定为 P0 的族。**

三条主线：

1. **四层工程地图（ADR-039）在代码里是真的。** `agents/` 包 DB-free 决策纯；ToolLoopAgent 有界 loop 真实存在（`max_iterations=6`、终态工具一调即停、loop 驱动内零副作用）；perception 读工具严格只读；T5 decompiler 的「确定性字段零 LLM」是**构造性保证**（`craft_scan.py` 全文无 provider import + `CraftJudgment extra=forbid` 只开 3 个 LLM 座位 + `test_decompile_pure.py` 源码扫描看门），不是口头承诺。这一面不需要修。

2. **执行内核没有围栏（fencing）。** `workflow_steps` 的终态写是盲 ORM 赋值（`orchestrator.py:1189-1218`、`:1343-1360`），reap 不认 owner（`jobs.py:208-212`、`:243-248`），全库无 lease / heartbeat / fencing token 列。后果链：节点执行超时 600s（`orchestrator.py:1136`）< reap 阈值 900s（`jobs.py:231-256`）→ 慢节点会被重执行 → 新旧两个执行者都能写终态 → **last-writer-wins**；run 行靠 finalize 的行锁保住第一写者（`orchestrator.py:1530-1534`），step 与 graph 行被后写者覆写 → 三面不一致。credits 已活（ADR-055 hold→capture→release 在生产路径），W11 支付批排期已挂（PROGRESS：09-10~09-23 支付实际开发 + 分发联调）——**重复执行 = 可能重复扣费 + 错账**。把「已知隐患」升级为 P0 的理由只有一个：钱。

3. **「Artifact」作为一等概念不存在，且现有形态是有意设计而非事故**（ADR-030：可变 god-row + `render_status` 顶格做 worker 认领谓词）。审计任务给出的三条铁律逐条判决：**铁律 1（不可变）= 不成立，是拍板**；**铁律 2（产物无执行态）= 不成立，同为拍板**，但其代价已在渲染边界显形 —— 渲染终态护栏是 status-based 不是 identity-based（`rendering.py:283-314`），zombie render 可覆写新 spec 的 render；**铁律 3（产物 = 缓存边界）= 半成立** —— 只有 `material_understanding` 与 `craft_skeleton` 两个内部类型是内容寻址的，且住所是「伪装成 outputs 行 + latest-20 Python 扫描 + 无索引无唯一约束」，规模化即退化。T5 证明了缓存边界模式的价值，也走到了它的承重极限。

随批上报一个潜伏炸弹：**`operations.output_id` 是 NO ACTION 外键（`tables.py:423`；migration `e5b8c3d91f07:31`），而两条删除路径（`delete_output` 路由 `routes/outputs.py:135-164`、`select_clips` 全清 `clips/node.py:303-321`）都不清 operations —— 删除任何「被编辑过」的产物（filler morph、editor set_trim 都会在 base clip 上记 operations）= FK 违反 = run 失败 / 500。**

**下一批建议（唯一）：执行身份与围栏批（Execution Identity & Fencing）** —— 论证与边界见末节「NEXT ITERATION」。

---

## 二、Current Architecture Map

从代码与 migration 重建的真实地图（不是任何一篇 doc 的复述）：

```
用户 ── composer / dock ── POST /chat（唯一意图面，ADR-077）
                              │
                    ToolLoopAgent（agents/tool_loop.py，max_iterations=6）
                              │  终态工具：ask_user / present_plan / start_run / answer
                              │             | propose_tasks / apply_edit_ops / edit_graph
                              │  读工具：chat/perception/*（严格只读）
                              ▼
        ┌──────────── 三扇动作门 ────────────┐     辅助写口（文档未枚举）：
        │ create_run / apply_wiring_ops /    │     create_transcript_asset、
        │ apply_operations                   │     graph_fill.stamp_draft_graph、
        └────────────────────────────────────┘     run 生命周期写、warms
                              │
        graph_nodes / graph_edges（ADR-057/072/076；draft 图 → run fill）
                              │
   ┌──────────── 执行内核（5 个认领源，worker.py 主循环 2.0s tick）────────────┐
   │ assets.processing_status │ workflow_steps(claim_ready_node) │           │
   │ outputs.render_status    │ publications                                        │
   └──────────────────────────────────────────────────────────────────────────┘
                              │
        outputs god-row（产物 + 渲染执行态 + 发布 + 质量 同表）
        operations journal（append-only，spec_hash 链，undo）
        内部产物（material_understanding / craft_skeleton 伪装成 outputs 行）
        wallets / credit_transactions（hold→capture→release，idempotency_key UNIQUE）
        HITL 四存：messages Q/A + step.waiting·suspend_payload + run.WAITING_HUMAN + project.pending_brief
```

表归属（`tables.py` + MODULE_ARCH 合同核对一致的）：20 张表，归属合同大体真实；**三处合同与代码有出入**（§十三冲突清单 #7）。

**简报承诺核对（`docs/tasks/done/chat-tool-loop-migration.md` 声称 T1~T5 全落地，2026-09-15）**：

| 批次 | 承诺 | 代码实测 | 判决 |
|---|---|---|---|
| T1 线格式三层 | Tier 0/1/2 + 能力旗标 | `tool_loop.py` tier 门 + minimax tool_calls 通道 + `test_wire_tiers_pure.py` | ✅ 真 |
| T2 loop 内核 | 终态工具 / 护栏搬进执行 / 读工具族 / service.py 拆解 | 前三项真；**service.py 未拆解**（仍 ~2241 行，ask 机器/账本/dock 生命周期仍在） | ⚠ 主体真，拆解未做 |
| T3 触发回合 | understand 完成 + run 完成白名单 | 触发器、发座、wrap_up、suggestions 全真；**但 run 路径 decompile 物化从不触发 craft 触发回合（仅 warm 新鲜产出触发）** | ✅ 真（一处漏接，见 §八） |
| T4 验收/命名/文档 | 剧本改写 + NAMING v3 + 文档现在时 | 14 个纯函数套件在；prompt_gate 按 provider 参数化 | ✅ 真 |
| T5 decompiler | 见 §八 | 机制全在，8 个集成缺口 | ✅ 主体真 |
| B4 镜头跟随 | running 节点平滑居中 / 节点切换镜头游走 / 终态拉远 fit | `FlowView.tsx:183 CameraBeats` = **仅节点诞生节拍**（fit/pan + 3s 手势盾 + reduced-motion 退化）；**无 running 节点跟随** | ⚠ 半落地（C6 落地的是用户发起节拍） |

---

## 三、Agent Boundary Audit

**问题：Agent 是否只做决策？工具是否偷偷编排？工具结果如何回流？旧方言残留？第二隐状态机？bounded loop 真实性？**

### 3.1 Agent = 决策纯 ✅

`agents/` 包全文无 DB import、无 session、无模型类 —— Agent 漏斗（assemble→render→call→validate→repair-one-round→meter→declared-fallback）是决策纯函数族。tool loop 驱动内**零副作用**：所有写世界动作发生在工具执行体内，不在 loop 驱动里。判决成立。

### 3.2 工具不编排 ✅（一处例外登记）

工具执行体是「门铃」不是「编排器」：`start_run` → `create_run`、`edit_graph` → `apply_wiring_ops`、`apply_edit_ops` → `apply_operations`，各调一扇唯一门。唯一的编排味道在触发回合（worker 侧写座调 chat 服务函数），属白名单设计内。

### 3.3 工具结果回流 ✅

原生 tool-result 消息回流（observation_tail 截断）；被拒调用以结构化错误回执回灌 loop；读工具实现里**没有写函数**（逐文件核对）。

### 3.4 退役方言残留 ⚠

- `InferredIntent(action="draft"/"ask")` 已退役，但**每次 dock 仍新鲜写入** messages.intent，且任何决策路径都不读它 —— 死座位在持续生产新数据。
- `StreamingAgent` + `generate_stream` 在 `app/` 内已死（仅剧本 harness 引用）。

### 3.5 第二隐状态机 ⚠（定性：存在但有界）

对话生命周期有一台**无 LLM 的确定性状态机**（messages question/answer 列 + project.pending_brief + 路由）：单待决、autoResume 结算、checkpoint 表单。它是**对话生命周期**的状态机，不是执行状态机 —— 与 run/step 状态机职责分离干净。判决：存在， scoped 正确，但它是 HITL 四存状态的原因之一（§九）。

### 3.6 bounded loop：迭代有界 ✅ / 墙钟无界 ⚠

`max_iterations=6` + 终态工具停环 = 迭代界真。但**无墙钟上限**：6 迭代 × （工具执行 + LLM 调用） 最坏 ~36 分钟/回合（读工具链 + repair 轮）。chat 回合是同步 SSE —— 用户视角是「agent 卡死」。

### 3.7 「三扇写门」枚举滞后 ⚠

`tool_loop.py` docstring 的「写世界只走三扇门」与实测不符。实际写口 ≥ 6：三扇门 + `create_transcript_asset`（prompt-only 发送物化转写资产）+ `graph_fill.stamp_draft_graph`（draft 图落库，**绕过 apply_wiring_ops** —— 有 MODULE_ARCH §4 合同依据，但「唯一写口」叙述应修订）+ run 生命周期写 + warms。**⚠ 文档承诺 ≠ 实现（窄口径表述，非架构违反）。**

---

## 四、Workflow / State Machine Audit

### 4.1 真实状态机（从代码重建）

**Run**（`WorkflowRun tables.py:184-201`；`WorkflowStatus schemas.py:100-107`）：

```
PENDING → RUNNING ⇄ WAITING_HUMAN → COMPLETED / FAILED
```

- **没有 SUSPENDED / RESUMED / CANCELLED**。用户假设的 CREATED→RUNNING→SUSPENDED→RESUMED→COMPLETED 不存在。
- 5 个写点 / 4 个 actor：create_run（出生）、claim_ready_node（PENDING→RUNNING 翻转 `jobs.py:118-125`）、execute_step Suspend 分支（→WAITING_HUMAN）、resume_waiting_interrupt（→RUNNING）、maybe_finalize_run（→COMPLETED/FAILED）。
- **无 lease / owner / heartbeat 列。**

**Step**（`WorkflowStep tables.py:204-253`）：`status String(20)` **无枚举**，实测 6 值 `pending/running/waiting/done/failed/skipped`，全小写原生字符串（与 run 的 Enum 存 NAME `'RUNNING'` 两种大小写并存 —— `finalize_stuck_runs:1721-1751` 有专门 case-law 注释处理这个分裂）。

**其余三台**：assets.processing_status、outputs.render_status（Enum 顶格）、graph_nodes.state（派生聚合，draft/queued/running/done/failed/skipped/stale 第三套方言）。

### 4.2 「用户在任意中间节点说暂停」→ 实际发生什么

**答案：这个能力不存在。** 全 routes 无 pause/cancel 端点。用户唯一的控制面：① 对 interrupt 提问「算了」（cascade-skip 下游，run COMPLETED）；② 删项目。中途 interrupt 是系统唯一「暂停」形态，且它有 30 分钟 TTL（§九）。

### 4.3 「Worker 15 分钟死掉，25 分钟复活 —— 老 worker 还能改系统吗？」

**答案：能。这是 P0。**

完整走查（每一条都有代码座位）：

1. 节点 N 被 worker-A 认领（`claim_ready_node jobs.py:68-142`：status→running、attempt+1、run 翻转 RUNNING）。
2. worker-A 进程卡死/休眠/失联。节点执行超 600s 进程内超时围栏（`orchestrator.py:1136`）不适用于「进程死了」——它只围栏活着的进程。
3. 900s 后 per-tick reap（`reap_stale_nodes_older_than jobs.py:243-248`）**盲 UPDATE** 把 N 打回 pending —— **不查 owner、不查心跳**。或 worker-B 重启，startup 全量 reap（`reap_stale jobs.py:186-228`）把所有 running 打回。
4. worker-B 认领 N，attempt+1，从头执行。
5. 25 分钟时 worker-A 复活（笔记本合盖醒来 / 孤儿进程恢复），它手里的 asyncio task 还在跑，**继续执行到终态**。
6. 两个执行者都到终态写：
   - **step 成功尾（`orchestrator.py:1189-1218`）= 盲 ORM 赋值**：`node.output_refs=…; node.cost=…; node.status="done"; capture_step(…); sync_graph_node_for_step; commit` —— **无 WHERE、无 owner、无 attempt guard**。后写者赢。
   - **失败尾（`:1343-1360`）同样盲写**。
   - run 行靠 `maybe_finalize_run` 的 `FOR UPDATE` + 终态 early-return（`:1530-1534`）保住第一写者的判决 —— 但 step/graph 已被第二写者覆写。**结果：run 说 FAILED（先到的失败），step/graph 说 done（后到的成功），三面不一致。**
   - billing：`capture_step` 幂等键 `step:{id}:capture:{attempt}` + delta = total − prior —— **同成本 zombie 被 delta=0 吸收（侥幸），不同成本 zombie 落一条 delta 扣费行（真扣钱）**。

缓解物清单（为什么日常没炸）：run finalize 锁、billing 幂等键、渲染 status 护栏、产物 sweep。但渲染护栏本身是 status-based 不是 identity-based（§4.4），sweep 是 last-writer-wins 的另一种写法。**单 worker 部署让概率低，不让危害小 —— 笔记本合盖、孤儿 uvicorn、`python -m app.worker` 重复启动都是常态场景**（`reap_stale` docstring 自己就登记了孤儿 worker 危害）。

### 4.4 渲染链同款洞（P0-2）

`rendering.py:283-314`：渲染终态写的护栏是 `render_status==RENDERING` 匹配 —— **status 匹配不是身份匹配**。zombie render 完成时若行已被 reap→re-pend→morph 改了 spec，zombie 的写仍然匹配 `RENDERING`（新认领刚翻过状态）→ 用旧 spec 渲染出的文件覆写新 spec 的行，新渲染反被当 superseded 丢弃。

### 4.5 Suspend 写无护栏（P0-3）

Suspend 分支把 `run.status=WAITING_HUMAN` 写在 `orchestrator.py:1237` —— **无 guard**。zombie 在 run 已 COMPLETED 后抛出 Suspend，run 被拉回 WAITING_HUMAN（resume 后靠 `resume_waiting_interrupt:1422-1448` 的 guarded 翻转才能回来，但用户看到的是一个「已完成又活过来问问题」的 run）。

### 4.6 其余登记（非 P0）

- `create_run` 的 has_active_run 检查（`orchestrator.py:987-1004`）：PENDING/RUNNING 阻断新 run 出生，**WAITING_HUMAN 不阻断** —— 挂人等待的 run 与新 run 并存，配合 select_clips 全清（§6.4）= 跨 run 破坏面。
- `claim_ready_node` 不看 run.status —— WAITING_HUMAN 的 run 里其他 pending 节点仍会被认领执行（设计上「人等回答时别的分支照跑」可辩护，但与「run 在等待」的用户心智冲突，需 ADR 明示）。
- assets / renders **无 attempt 上限**：确定性崩溃的资产在每次 worker 重启后被重新认领 → poison-pill crash-loop（`reap_stale` TODO 自认：`jobs.py:199-201`）。
- 从未启动的 run（PENDING 卡死）**hold 永久冻结** —— `release_run` 只在终态触发。

---

## 五、Task / Attempt Audit

**问题：Task 是什么？Attempt 真实存在吗？**

- **Task = 一张 `workflow_steps` 行，逻辑节点与执行记录同一行，跨 attempt 复用。** `attempt = Column(Integer, default=0)`（`tables.py:204-253`）是**计数器不是记录**。
- **没有 ExecutionAttempt 表。** 一次崩溃不留任何可分辨记录 —— 你无法从 DB 回答「这个节点历史上被执行过几次、每次是谁、怎么死的」。
- **attempt 语义三合一**：用户可重试（TransientNodeError 预算内 re-pend）、reap 弹跳、zombie 双执行 —— 三种性质完全不同的事件共享同一个计数器。billing 用 `capture:{attempt}` 做幂等键，意味着 attempt 的语义漂移直接传导到钱。
- **判决书**：Task 概念当前够用（逻辑节点=执行单元的折叠是 ADR-028 的拍板，拓扑铁律健康）；**Attempt 是缺失的一等概念** —— 它是 P0 围栏的天然载体（claim token = attempt-scoped），也是 postmortem 的天然座位。建议最小形态：不建大表，step 上加 `attempts` JSONB 日志（每次 claim 记 {attempt, claimed_by, claimed_at, outcome}）+ claim token 列。

---

## 六、Artifact / Output Audit

### 6.1 outputs 解剖（`Output tables.py:336-404`）

一张表 ≥ 8 个关注点：身份（id/project_id/workflow_step_id）· 业务（type/language/**status String 自由串，客户端可写**）· 内容（payload/source_ref/render_spec）· **执行态（render_status Enum 顶格 + render_error）** · 文件（files）· 质量（score/quality 两套）· 发布（publishing）。`spec_hash` 是 computed property；**无 content_hash / parent_output / version 列**。

### 6.2 三铁律逐条判决

| 铁律 | 判决 | 证据与定性 |
|---|---|---|
| **1. 产物不可变**（修改 = 新版本，不 UPDATE） | **不成立 —— 是拍板** | 所有修订路径原地 UPDATE：payload（文案修订）、render_spec（edit ops）、publishing、score/quality、status。operations journal 挂在可变行上（`spec_after` 快照链 = ADR-032 设计）。派生 sweep 直接删行重建。undo 用快照原地 restore（restore 插回的行是新 id）。⚠ 与审计任务给定的规则冲突，但与 ADR-030/032 一致 —— **冲突要摆到明处：这是「可变 god-row + 账簿」学派，不是 immutable-artifact 学派** |
| **2. 产物不带执行态** | **不成立 —— 是拍板，但代价已显形** | `render_status`/`render_error` 顶格在 outputs 上是 **ADR-030 Rule 2 的刻意选择**（worker 认领谓词必须可查询 → 查询字段挣列）。代价 = §4.4 渲染护栏洞 + run 生命周期修复被迫耦合产物行（ADR-074② renders hold run → delete_output 要结算镜像 step）。**设计张力真实存在，需要在下一 ADR 重新权衡** |
| **3. 产物 = 缓存边界**（Transcript→ClipSpec→Approved ClipSpec→Render 各层可复用） | **半成立** | 只有 `material_understanding` 与 `craft_skeleton` 两个内部类型内容寻址 + 复用命中；翻译产物挂在 `graph_nodes.spec` 上。其余链路**无任何缓存**：同 spec 重渲染不跳过（无 render-skip cache）；**ClipSpec 与其渲染产物同一行 —— 没有派生边界**；「Approved ClipSpec」这个概念不存在 |

### 6.3 写点清单（全库 outputs 写者）

create_run 系（plan/storyboard stub 插入）、select_clips、translate/dub fork、edit ops（apply_precomputed）、rendering 终态、delete_output 路由、warms（understand/decompile）、发布链。其中 **plan/understand-stub 每次执行插新行、无清扫** —— 重试/弹跳累积重复行（读面靠 output_refs 覆写保持正确，存储与复用查询被污染）。

### 6.4 潜伏炸弹（P0-adjacent，随批上报）

- `operations.output_id` FK **NO ACTION**（`tables.py:423`；migration `e5b8c3d91f07_add_operations.py:31`）。
- `select_clips` 每次执行**删除全项目所有 clip 产物**（`clips/node.py:303-321`，跳过 pending render 的镜像后 `delete(Output)`）—— 幂等靠毁灭，且**不清 operations**。
- `delete_output` 路由（`routes/outputs.py:135-164`）删存储对象 + 行 + 结算镜像 —— **不清 operations**。
- 全库唯一 `delete(Operation)` 在 `projects.py:715`（删项目级联）。
- **引爆路径**：filler morph / editor set_trim 在 base clip 上记 operations → 用户删该产物 / 下次 select_clips 全清 → FK 违反 → run 失败 / 500。
- 对照：`publications.output_id` 是 `ondelete="RESTRICT"`（`tables.py:605-609`）—— 同一张 outputs 的两种删除纪律，说明 operations 的 NO ACTION 是漏配不是拍板。

### 6.5 select_clips 的跨 run 破坏面

「删除全项目 clips」+ WAITING_HUMAN 不阻断新 run 出生（§4.6）= 一个挂人等待的 run 的 clips 可被另一个 run 的 select_clips 整族销毁。**「重新剪」语义（ADR-061 variant-parallel：fork 不覆盖原版）与 select_clips 的毁灭重建是两套版本学并存** —— 冲突清单 #6。

---

## 七、Structured Media / ClipSpec Audit

**问题：ClipSpec 是 Artifact 本身，还是 Artifact 的 payload/schema？**

**答案：在现行代码里它两个都不是 —— 它是可变 god-row 上的一个 JSONB 列（`render_spec`），与其渲染产物共享同一行身份。** 用三铁律的语言说：ClipSpec 是「一个尚不存在的 Artifact 的 payload」。

具体判决：

1. **持久化形态**：clip-spec 契约（ADR-016/044，TRACK_REGISTRY 9 轨）本身健康、renderer-agnostic 成立（render 服务无业务概念回流）。但它的存储 = `outputs.render_spec` JSONB，行内还有 `payload`（业务面）与 `files`（渲染产物）—— **spec、渲染产物、业务载荷三位一体**，铁律 3 要求的「Transcript→ClipSpec→Render 分层缓存」在存储层物理不可能。
2. **校验缺口**：`apply_precomputed` 不对 new_spec 做 ClipSpec schema 校验 —— LLM 翻译文本可经 dict spread 骑进 `caption_track`，render POST 无闸门。契约在出生端严、在修订端松。
3. **双轨漂移**：`payload.hook` 与 `render_spec.title.text` 两个座位存同一事实，revise 只更 payload —— 渲染面与业务面可说出不同的 hook。
4. **三处存储**：render_spec 同时活在 outputs 行、operations.spec_after、verify rounds —— 对账靠 spec_hash 链（operations 内自洽），跨存无对账。

---

## 八、Decompiler / T5 Audit

### 8.1 数据流与判决

pin 结算（纯代码）→ 编译期注入 → 物化（warm/run 共享路径）→ 持久化（`Output(type="craft_skeleton")`，`source_ref.asset_hash = asset.meta.content_sha256`，`decompile.py:66-71`）→ plan/run 消费（hash 重查，非图边）。

- **产出 = 真实持久可复用内部产物** ✅（INTERNAL_OUTPUT_TYPES 成员，payload schema 看门）。
- **内容寻址** ✅ 但有 4 个缺口（下表）。
- **LLM 直写 ClipSpec 结构性不可能** ✅：`CraftJudgment extra=forbid` 只开 music_mood/hook_device/gaps 三座位；assemble 签名纯度；`craft_scan.py` 零 provider import；palette snap / preset Literal 漂移门；全部由 `test_decompile_pure.py` 看门。**这是全库「LLM 权限最小化」的最佳先例。**
- **确定性字段真零 LLM** ✅（镜头切分 HSV 直方图相关 / 字幕带扫描 / 最近邻 preset+palette，`CRAFT_SCAN_VERSION=1`）。
- **exemplar 参数 = 代码映射** ✅（explicit > exemplar > default 优先级统一，LLM 永不写 spec）。

### 8.2 八个集成缺口

| # | 缺口 | 证据/影响 |
|---|---|---|
| 1 | 复用查找 = latest-20 同用户行 Python 扫描 | hash 无索引、无唯一约束 → 规模化退化；warm/run 竞态双插（良性但脏） |
| 2 | `CRAFT_SCAN_VERSION` 只写不读 | 版本演进后旧骨架照样命中复用 |
| 3 | warm 行无 `workflow_step_id` lineage | 来源不可溯 |
| 4 | decompile 长 fallback `text×manual` 画布节点（不在 `_PRELUDE_KINDS`）而其产物被画布 join 过滤 | 画布出现孤儿节点 —— canvas seam 尴尬 |
| 5 | **run 路径物化从不触发 craft 触发回合**（仅 warm 新鲜产出触发） | 旅程二拍 1「看完主动说话」在 run 路径失声 |
| 6 | **skeleton 时序结构（shot spans / rhythm 细节 / hook_device）持久化了但没有下游消费者** | 只有 count/aspect/captions/music 变成参数 —— **「内容槽替换」落地 = 数量+风格级 remix，不是结构级 remix**。⚠ ADR-078 承诺 > 实现（冲突清单 #4） |
| 7 | 无 e2e remix 剧本（S1-S15 无 remix 场景） | T5 验收靠用户自跑，回归无看门 |
| 8 | 2b「契约即能力边界」纠偏 = schema + prompt 座位在，但无确定性代码路径把 gaps 喂给 plan | LLM prose only —— 半成立（符合顾问姿态设计，登记不追责） |

---

## 九、Human-in-the-loop Audit

### 9.1 状态四存（DB 概念债 Top-1）

HITL 状态同时活在：① messages question/answer 列 ② step.waiting + spec.suspend_payload ③ run.WAITING_HUMAN ④ project.pending_brief。交叉引用走 JSONB 不走 FK（`suspend_payload.question_message_id` 是 JSON 字符串，可悬空）；answer 写两处。任何一处漂移 = 三面不一致的又一种形态。

### 9.2 Case A：「用户三天后回答」逐帧回答

| 问题 | 答案（证据） |
|---|---|
| worker 释放了吗 | ✅ 释放了。Suspend 分支 park 后 step→waiting，认领计数让出（`orchestrator.py:1220-1239`） |
| 等待原因持久化了吗 | ✅ 持久化（spec.suspend_payload + message 行） |
| run 状态对吗 | ⚠ 状态对（WAITING_HUMAN），**但中途 interrupt 有 30 分钟 TTL**：`interrupt_expiry_seconds=1800`（`config.py:58`），`expire_stale_interrupts:1641-1718` 自动填默认答案（text="expired"）→ **三天后回来：run 早已自动降级跑完，回答 = 409（answer 已非 NULL；扫掠与用户抢答时用户赢——answer 写是 guarded `answer IS NULL`）** |
| 可从正确 Artifact/Task 恢复吗 | ✅ 恢复 = 队列重入（step→pending、started_at=None、run→RUNNING guarded），节点带 spec.answer 从头重跑 —— **不是调用栈恢复，是重执行**，前提 = 节点幂等（§十） |
| 对照：run 前的计划确认 | ✅ 无 TTL，永久耐用（pending_brief）—— **两种 HITL 两种寿命，产品语义需在文档明示** |

### 9.3 Case B：「不要这个版本，换一个」逐帧回答

三套版本机制并存，按产物族分家：

| 产物族 | 机制 | 版本历史 |
|---|---|---|
| 视频参数修订（filler/music/reframe/trim） | operations 快照 journal + 原地 morph（ADR-032） | ✅ 有账（render_spec only），undo 真 |
| 翻译/配音变体 | fork 派生新行（ADR-061） | ✅ 原版保留 |
| **文本文物（post/article）** | **原地 payload 重写** | ❌ **无版本账** —— operations 只记 render_spec，payload 修订历史直接丢失 |
| 「重新剪」 | select_clips 全项目销毁重建 | ❌ 旧版物理删除（且踩 §6.4 FK 雷） |

---

## 十、Retry / Idempotency / Cache Audit

| 重活 | 可缓存 | 幂等 | 重试重复副作用 | 有执行身份 |
|---|---|---|---|---|
| LLM 调用 | 否（按设计） | 否（重试 = 新调用新计费） | 计费重复（billed_per_attempt 吸收同 attempt） | ❌ |
| 媒体分析（understand） | ✅ 已做（content-addressed） | ✅ | 无（复用命中） | ❌（warm 行无 lineage） |
| 转写（ASR） | ✅（asset 级） | ✅（processing_status 状态机） | poison-pill 无上限 | ❌ |
| 渲染 | ❌ 无 render-skip cache | ⚠ status 护栏非身份护栏 | **zombie 覆写新 spec（§4.4）** | ❌ |
| 镜头检测 / craft_scan | ✅ 已做（craft_skeleton） | ✅ | 无 | ❌ |
| decompile | ✅ 已做 | ✅（双插良性） | latest-20 扫描退化 | ❌ |
| 工具执行（三扇门） | — | create_run：项目行锁+has_active_run；wiring/ops：base_hash 乐观锁 | 低 | ⚠ 乐观锁 ≠ 执行身份 |
| select_clips | — | **幂等靠毁灭（全清重建）** | 跨 run 破坏 + FK 雷 | ❌ |
| billing | — | ✅ **全库唯一真幂等层**（NOT-EXISTS 门 + idempotency_key UNIQUE） | 无 | ✅（idem key 即身份） |

**结论**：Artifact 能不能当缓存边界？—— 两个内部类型证明**能**，且是唯一被验证过的缓存边界形态。缺口不在理念在住所：无 content_hash 列、无索引、无唯一约束、无 lineage。

---

## 十一、Journey ↔ Architecture Matrix

| Journey | 当前实现 | 依赖的架构能力 | 是否真正成立 | 最大缺口 |
|---|---|---|---|---|
| 旅程一 迷失用户首产 | 配方卡/composer/出书门槛/draft 图/确认 pill/SSE/读工具/触发回合全真 | 四层地图 + tool loop + draft 图 + fold 估价 | ✅ 主体成立（JOURNEYS 状态列滞后一天：拍 2/拍 7 标 🚧T2/T3，代码已落地） | chat 回合无墙钟（~36min 极端）；plan/understand 重试重复行；B4 运镜半 |
| 旅程二 案例仿制 | 角色 pin/消歧、decompiler、exemplar 参数、gaps schema 全在 | T5 全家 + 资产角色 + 内容寻址复用 | ⚠ **数量+风格级 remix 成立；结构级 remix 不成立**（skeleton 时序结构无消费者） | 无 e2e remix 剧本；run 路径触发回合漏接；canvas seam 孤儿节点 |
| 旅程三 修订服务 | 读工具/edit ops/wiring/undo 真 | 三扇门 + operations 账 + perception | ⚠ 主体成立 | op 覆盖度缺 size/color；文本产物无版本账；「重新剪」= 毁灭重建（与 variant-parallel 冲突）+ FK 雷 |
| Artifact/复用（横切） | understand + craft_skeleton 内容寻址 | 内部产物伪装 outputs 行 | ⚠ 成立但到承重极限 | 无 content_hash 列/索引/唯一约束/lineage；latest-20 Python 扫描 |
| 状态机旅程（暂停/恢复/取消） | 恢复=队列重入 ✅；run 终态锁 ✅ | 执行内核 | ❌ **用户暂停/取消不存在**；中途 interrupt 30min TTL 自动降级 | 无 pause/cancel 端点；TTL 语义未文档化 |
| 工具调用（T1-T4） | wire 三层/终态停环/只读 perception/触发回合 全真 | tool loop | ✅ 成立 | 无墙钟；被拒调用回显用户消息（设计内）；service.py 未拆解 |
| decompiler 消费（T5 下游） | count/aspect/captions/music → 参数 | exemplar 参数源 | ⚠ 半成立 | 时序结构持久化无消费 = 存储了没人读的账 |

---

## 十二、Architecture Debt Map

### P0 —— 数据/执行正确性（挡 W11 支付）

| # | 债 | 证据 |
|---|---|---|
| P0-1 | **无 zombie 围栏**：终态写盲 ORM + reap 无 owner → 双执行、last-writer-wins、三面不一致、可重复扣费 | `orchestrator.py:1189-1218`/`:1343-1360`；`jobs.py:208-212`/`:243-248` |
| P0-2 | **渲染护栏 status-based 非 identity-based**：zombie render 覆写新 spec render | `rendering.py:283-314` |
| P0-3 | **Suspend 写无 guard**：zombie 把 COMPLETED run 拉回 WAITING_HUMAN | `orchestrator.py:1237` |
| P0-4 | **operations FK NO ACTION + 删除路径不清 operations**：删已编辑产物 = FK 炸 | `tables.py:423`；migration `e5b8c3d91f07:31`；`clips/node.py:303-321`；`routes/outputs.py:135-164` |

### P1 —— 挡下一阶段架构演进

| # | 债 | 影响 |
|---|---|---|
| P1-1 | **Attempt 非一等概念**（计数器三合一、crash 无记录） | 围栏无载体、postmortem 不可能、billing 幂等键语义漂移 |
| P1-2 | **内部产物无一等住所**（content_hash 无列/索引/唯一约束；latest-20 扫描；warm 无 lineage；plan/understand-stub 重复行无清扫） | 缓存边界模式无法推广；T6+ 旅程依赖复用 |
| P1-3 | **HITL 状态四存 + JSONB 交叉引用** | 提问机器演进的每一步都要维护四面一致性 |
| P1-4 | **状态方言三套 + 大小写两套 + outputs.status 客户端可写自由串** | 「failed」在库里有 6 种含义；聚合漂移结构性可能 |
| P1-5 | **select_clips 跨 run 全清 + WAITING_HUMAN 不阻断新 run** | 挂人 run 的产物可被并行 run 整族销毁 |
| P1-6 | **文本产物无版本账**（payload 不入 operations） | 旅程三主战场的主力产物族没有 undo |
| P1-7 | **poison-pill 无 attempt 上限**（assets/renders） | 确定性崩溃 = 每次重启重新烧 provider 成本 |
| P1-8 | **从未启动 run 的 hold 永久冻结** | 积分泄漏 |

### P2 —— 产品能力 / 可维护性

文档漂移三处（§十三 #1/#2/#3）；死代码/死列（StreamingAgent+generate_stream、InferredIntent.action 新写、personas.learned_from 无写者、projects.tone_snapshot 死列、conversations.asset_id/asset_type）；chat 回合墙钟；T5 八缺口（§8.2）；personas 73% 可空 grab-bag（随 ADR-042 运营端批次拆）；plan 路径 gaps 纠偏确定性化；service.py 拆解。

### P3 —— 以后

agent_calls 台账（需求池已有 P1）；执行中自适应重规划；产品度量地基；EU 驻留实装；多 provider 可选 picker（policy switch 形态）。

---

## 十三、Conflicts between ADR / Docs / Code

| # | 冲突 | 定性 |
|---|---|---|
| 1 | `RENDERING.md §5` 描述 render_hook_preview + server.ts preview 参数 —— 代码已随 ADR-049 退役（grep 全无） | ⚠ 文档承诺 ≠ 实现（文档滞后） |
| 2 | `MODULE_ARCHITECTURE.md §7.1` 列 pipeline/hook_gate.py + `§4` outputs.files.hook_preview —— 代码同退役 | ⚠ 文档滞后 |
| 3 | `AGENT_ARCHITECTURE.md §4.3`「render 节点永不 hold run」旧判负谓词 —— 已被 ADR-074 翻案 | ⚠ 文档滞后 |
| 4 | **ADR-078「内容槽替换/结构复刻」 vs 实现 = count+style 参数映射**（skeleton 时序结构无消费者，§8.2#6） | ⚠ **ADR 承诺 > 实现**（本审计最重要的产品面落差） |
| 5 | 审计任务三铁律 vs ADR-030/032（可变 god-row + render_status 顶格 + 原地 morph） | 设计学派冲突，需摆明：铁律 1/2 的不成立是拍板；铁律 3 是值得追的北极星 |
| 6 | ADR-061 variant-parallel（fork 不覆盖原版） vs select_clips 全项目销毁重建 | 同一「变体」概念两套版本学并存 |
| 7 | 「三扇写门」叙述 vs 实测 6+ 写口（stamp_draft_graph 绕过 apply_wiring_ops 有合同依据但叙述未修订） | ⚠ 窄口径表述滞后 |
| 8 | InferredIntent 退役方言仍每次 dock 新鲜写入 | 代码自相矛盾（退役但持续生产） |
| 9 | JOURNEYS.md 状态列（2026-09-14）标 T2/T3/B4 🚧 vs 批次⑥ 落地（09-15） | 文档滞后一天，已随 `453b73d` 部分收口；B4 仍为半（§二） |

---

## 十四、Recommended P0

**执行身份与围栏批（Execution Identity & Fencing）** —— 一个批次四件事：

1. **step 认领身份化**：`workflow_steps` 加 `claim_token`（每次 claim 生成）+ `claimed_by`（worker 实例 id）+ `claimed_at`；终态写全部改 **guarded UPDATE**（`WHERE id=:id AND status='running' AND claim_token=:mine`），0 行命中 = 丢弃并记日志。reap 只收「claim 超龄」的行，且 reap 本身使旧 token 失效（fencing 语义）。
2. **渲染链身份化**：outputs 加 render claim token（或最小：终态写 WHERE 携带认领时快照的 token/spec_hash），zombie render 写 0 命中即弃。
3. **Suspend/finalize 写护栏**：run 状态迁移全部改 expected-from-state guarded UPDATE。
4. **operations FK 修复**：delete_output / select_clips 先清 operations（或 FK 改 CASCADE + 评审），附引爆路径的回归剧本。

验收纪律：纯函数套件（guard 构造/token 匹配）+ 手工 create_run 全链 + **双 worker 竞态演练**（杀一个 worker 验证另一个接管后旧执行者写被弃）。

## 十五、Recommended P1

1. **Attempt 最小记录化**：step 加 `attempts` JSONB 日志（claim/outcome 事件流）+ assets/renders attempt 上限 + dead-letter 标记。（P1-1/P1-7）
2. **内部产物住所**：outputs 加 `content_hash` 列 + 索引 + `(user_id, type, content_hash, schema_version)` 唯一约束 + warm 行补 `workflow_step_id`；plan/understand-stub 落地即去重。（P1-2）
3. **hold GC**：PENDING run 超时自动 release。（P1-8）
4. **HITL 收拢**：以 step.waiting+suspend_payload 为执行唯一真源，message Q/A 降为展示投影，question_message_id 改真 FK。（P1-3）
5. **状态方言统一**：step status 枚举化 + casing 统一 + outputs.status 收窄为枚举。（P1-4）
6. **select_clips 收窄**：清扫范围限本 run/本家族；create_run 对 WAITING_HUMAN 同项目阻断（或 ADR 明示放行）。（P1-5）
7. **文本产物版本账**：payload 修订入 operations（或等价物）。（P1-6）

## 十六、Recommended P2

文档漂移三处修复（冲突 #1/#2/#3，小 commit 随批）；死代码/死列清除（StreamingAgent/generate_stream、InferredIntent.action 新写、tone_snapshot、learned_from、conversations 死座位）；chat 回合墙钟上限；T5 缺口批（run 路径触发回合漏接、canvas seam、e2e remix 剧本、skeleton 时序消费深化——**深化前先回答「结构级 remix 是不是下一产品承诺」**，是 → 独立批次立项）；service.py 拆解评估。

## 十七、Explicitly Deferred Items

- **用户暂停/取消 run**（pause/cancel 端点）：产品决策先行（旅程尚无此拍），机制上等围栏批落地后再加才安全。
- **结构级 remix**（skeleton 时序结构消费）：见 P2 —— 是产品承诺问题不是缺陷修复。
- **personas 拆桌 / Positioning 根座位**：挂 ADR-042 运营端批次（W8-W10），不动。
- **多 provider 线格式抽象第二层**：T1 三层已够，policy switch 等真实第二 provider。
- **agent_calls 台账 / 产品度量地基**：需求池 P1，不挡路，缓。
- **EU 驻留**：营销文案保持 ready 角度，实装后排。

---

## 十八、NEXT ITERATION —— 下一批到底做什么

### P0 / P1 / P2 清单

见 §十四/十五/十六，不重复。

### 唯一最值得作为下一批施工起点的任务：**执行身份与围栏批（§十四全批）**

**为什么是现在**
1. **钱的理由**：credits 已在生产路径（hold→capture→release），W11 支付批排期已挂（PROGRESS 09-10~09-23）。当前防双重扣费靠「delta=0 侥幸」不靠结构 —— 同成本 zombie 被吸、不同成本 zombie 真扣。支付接入真实信用卡后这不是 bug 是账单事故。
2. **概率不低**：单 worker 让概率低，但触发场景全是常态 —— 笔记本合盖、孤儿 uvicorn、`python -m app.worker` 重复启动、600s/900s 之间的慢节点窗口。`reap_stale` docstring 自己就登记了这个危害，只是没有机制接住。
3. **零概念发明**：不引入新框架、不改状态机形状、不动四层地图 —— 纯机制层加固（token + guarded write + reap 语义），风险面全库最小。
4. **它是 P1 半数事项的前置**：attempt 记录化、hold GC、内部产物 dedup 竞态收敛，全部以「claim 有身份」为前提。

**解决哪个真实问题**：老 worker 复活后覆写新执行的结果（双执行 / 三面不一致 / 可重复扣费）；zombie render 覆写新 spec 的产物；删除已编辑产物直接 FK 炸库。

**依赖**：一个新 ADR（执行身份与围栏）；无外部依赖、无排期冲突（W11 支付批应排在此批之后，或至少把「双重扣费族」验收挂到本批）。

**可并行**：文档漂移三处修复（独立小 commit）；operations FK 修复（P0-4，独立 commit）；死代码清除；P1-2 内部产物住所的**设计讨论**可并行（落地等本批）。

**必须排在其后**：P1-1 attempt 记录化（围栏防旧写手，记录让你看见发生了什么 —— 一枚硬币两面）；P1-2 住所落地；hold GC。

**应取消/改道的原计划**：W11「支付实际开发」在围栏批之前不启动；T5 结构级 remix 深化推迟到产品承诺拍板；「执行中自适应重规划」维持缓做。

**需新增/修订的 ADR**：
- **新增 ADR-079**：执行身份与围栏（claim token / guarded terminal write / reap fencing 语义 / render claim 身份 / run 迁移 expected-from-state guard）。
- **修订 ADR-017**：reap 语义从 ownerless 改 lease/fencing-aware。
- **修订 ADR-030**：render_status 认领谓词补身份维度（或登记「谓词 + token」双层）。
- **修订 ADR-050**：session 纪律章补 guarded-write 纪律。
- 文档同步：RENDERING §5 / MODULE_ARCH §7.1+§4 / AGENT_ARCH §4.3（冲突 #1/#2/#3 同批）。

**绝对不要碰的现有代码**：`apply_wiring_ops` 唯一写口纪律；NodeBase 四算子（fold/topo/∀/⊆）与 compile_graph 纯度；TRACK_REGISTRY；operations journal 机制本体（append-only + spec_hash 链）；billing 幂等键机制；clip-spec 契约；ToolLoopAgent 终态工具机与 max_iterations；perception 只读纪律；craft_scan 零 LLM 构造与 test_decompile_pure 看门。

---

> **审计完。等待下一步指令 —— 不自行开始 P0/P1 编码。**
