# ARCHITECTURE_GATE_2_REPORT — 第二道 Architecture Gate（对抗性反审）

> 对象：`docs/ARCHITECTURE_NORTH_STAR.md`（`1452eb7`）+ 两份审计基线 · 纪律：Code > docs > ADR narrative · Current evidence > intended architecture · Race proof > architecture diagram · 不把 TARGET 写成 CURRENT · 不提前解 OPEN · 一 commit 一 correctness 问题。本轮零业务代码改动；North Star 未改，发现的问题仅登记于本报告。

## 1. HEAD

`1452eb7`（Architecture Gate 批落地后；工作树除本报告外干净）。

## 2. Documents audited

`ARCHITECTURE_NORTH_STAR.md`（逐条）/ `POST_T5_DELTA_AUDIT.md` / `POST_T5_ARCHITECTURE_AUDIT.md` / `MODULE_ARCHITECTURE.md` / `AGENT_ARCHITECTURE.md` / `DECISIONS.md`（ADR-017/028/030/032/039/050/052/055/057/066/074/077/078）/ `BILLING.md` / `RENDERING.md` / `CHAT_ARCHITECTURE.md` / `DIALOG_WORKFLOW.md` / `PROGRESS.md` / `DISTRIBUTION.md`（Gate F 需要）。代码侧增量取证：`tables.py`（FK 全集）、`projects.py:695-730`、`clips/node.py`、`routes/outputs.py`、`verify.py`、`derivative_dispatch.py`、`chat/perception/*`（grep 级）、`chat/`+`agents/`（worker 函数调用 grep 级）、`tests/test_graph_wiring_pure.py`（stub 模式）。

## 3. Gate A verdict：五态真实性 —— **PASS，1 处需降级 + 2 处确认**

逐条核对 North Star 全部 `CURRENT` 声明，绝大多数有符号级证据（§2 五概念表 = `tables.py:230/244` + delta §3.1；§3.1 agents 纯度 = 包级 grep；§5 op 闭集 = registry + 启动对账；§6 max_iterations=6 / 无墙钟；§7 _ThinkStripper；§8.1 四 P0 全部 file:line；§8.6 `_mutate` 双层 = `billing.py:366-412`）。三项裁决：

1. **需降级（TARGET 被写得像 CURRENT）**：§3.1「决策生产者可替换、替换不改变下游」——**机制是 CURRENT**（T1 三层线格式 + provider 能力旗标），**被证明的可替换性不是**：生产至今只有 MiniMax 一个 provider，第二 provider 从未真实运行过。建议措辞降为「可替换性机制已就位、未经第二 provider 实证」。不阻塞 Gate。
2. **确认合格（易错点）**：§8.5 ExecutionAttempt 字段速写保持 TARGET + 形态 OPEN，未偷渡 schema；§6 AgentBudget 数值留 OPEN；§10 claim_token 列名属「机制已定、细节归实施」的合法 PLANNED（经审计链拍板），不算偷渡未决设计。
3. **确认合格（REJECTED↔ADR 一致性）**：agent 框架（ADR-052/077 禁令）/ 拓扑塑形（ADR-028）/ 自由 field ops（ADR-032 闭集）/ CoT 上产品面（ADR-066）/ 冻参模板（ADR-058）/ 静默降级（ADR-039 declared fallback）——逐条对得上，无与 ADR 打架的 REJECTED。

## 4. Gate B verdict：Agent 边界 —— **PASS（精确化表述后成立）**

不停留在「agents/ 无 DB import」，向下追了全链：

- **perception 零写**：`chat/perception/*` 全文 grep `insert(/update(/delete(/db.add` = **0 命中**。Query 纯度成立。
- **chat/agents 不调 worker 函数**：两层 grep `execute_step/render_output/claim_*/reap_stale` = **0 命中**。无任何「直接启动 worker」。
- **Command 全部落门**：start_run→`create_run`、edit_graph→`apply_wiring_ops`、apply_edit_ops→`apply_operations`。Interaction（ask_user/present_plan/answer）写对话态走 chat service 自有座位（单待决纪律），不碰 workflow/artifact。
- **Runtime 未暴露**：LLM 面工具目录 = 终态工具 + perception 读工具，无 emit_phase/checkpoint/resume 类原语；SSE 相位与触发回合全在代码侧。
- **辅助写口（登记在案，非越界）**：`create_transcript_asset` / `stamp_draft_graph`（draft 图第二写者，与「wiring 唯一写口」叙述的口径差已登记为 drift）/ warms（进程内 asyncio 物化，非 worker）/ run 生命周期写。

**精确化结论**：「Agent 只产生 Decision」在 **LLM 面**是 CURRENT 事实；写世界的是 harness 侧工具执行体——在门后、可审计。North Star §3.3 诚实注已作此限定，表述合格。

## 5. Gate C verdict：执行身份模型 —— **PASS，九问逐一回答**

1. `claim_token` 存在？**不存在**（无列）。
2. execution identity 存在？**不存在**（无任何 execution_id/claim_id）。
3. worker identity 存在？**不存在**（worker.py 无实例 id 概念）。
4. attempt 只是 counter？**是**，且消费者全部 fail-safe（retry 预算更早就失败；billing key 误用是 zombie 症状）——计数器自身不构成 correctness 问题。
5. **fencing token vs ExecutionAttempt 职责边界**：token 回答「**现在**谁有权写」（短暂、随 claim 生灭、release 即 NULL）；Attempt 回答「**当时**发生了什么」（持久、who/when/input/output/cost/superseded）。一个是写权威的 correctness primitive，一个是执行历史的 observability model。**禁止互冒充**——North Star §8.4 分层正确。
6. claim_token 能解决哪些 P0：P0-1 节点终态盲写、P0-2 渲染 status 守卫、P0-3 Suspend 复活（+from-state guard），及衍生的双扣路径（rowcount=0 → 不 capture）。
7. 明确**不能**解决：poison-pill 崩溃环（attempt 上限）、PENDING run hold 泄漏、执行历史不可见（postmortem）、HITL 四存、select_clips 跨 run 语义、内部产物住所。**也不限制健康并发本身**（双活 worker 各自 claim 不同节点 = 合法；startup-reap 竞态造成的重复执行由 fencing 正确丢弃——浪费的是资源，不是正确性）。
8. ExecutionAttempt 为什么不能顺手设计完：被 race proof 证明的是「缺 fencing」，不是「Attempt 模型设计错了」；其形态 OPEN（下条）；attempt 的三个现存消费者（retry 预算/billing key/bounce 界）需逐一迁移，混入 fencing 批会把回归面炸开；一 commit 一 correctness 问题。
9. 形态为何必须保持 OPEN：独立表（写放大 + JOIN + 迁移面）vs attempts JSONB 日志（零迁移但无查询能力）的选择，取决于 agent_calls 台账（需求池 P1）与 W11 后对账的真实需求——数据未回，现在拍板 = 猜。

## 6. Gate D verdict：施工顺序 —— **维持 Commit 2 → Commit 1（证据版，非惯例版）**

| 维度 | Commit 2（FK） | Commit 1（fencing） |
|---|---|---|
| migration 风险 | 零 | 有（2 列 + downgrade + 部署注记） |
| correctness 触点 | 删除路径排序 | 最热写路径谓词 |
| 回滚 | revert 即完 | downgrade + 在途行 NULL-token 处置 |
| 事务边界 | 不变（同 session 排序） | 不变（谓词变化） |
| API 行为 | 只减少失败（500→204 / run 不炸） | happy path 不可见 |
| 互相污染验证 | 无（C2 的删除 e2e 与 C1 的竞态演练无关） | 同左 |
| 测试基础设施 | 无需新增（`_StubDb` 模式已在 `test_graph_wiring_pure.py:81-194`） | 同左 |

顺序独立的两个 correctness 问题，风险升序 = 先小后大；让 FK 雷在 fencing 批的长施工期内继续挂着没有意义。**两 commit 必须保持独立**：不同 blast radius、不同回滚故事、不同验收——绑在一起就破坏「一 commit 一 correctness 问题」。完成定义见 §13/§14。

## 7. Gate E verdict：Commit 1 范围 —— **PASS，最小边界如下（含越界检查）**

**IN（全部，缺一不可）**：
- migration：`workflow_steps.claim_token UUID NULL` + `outputs.render_claim_token UUID NULL`（可回滚 drop）。
- claim 写 token：`claim_ready_node` 原子 UPDATE 内 `SET claim_token=gen_random_uuid()`；`claim_pending_render` 同。
- 失 Paths 置 NULL：两个 reap；execute_step 的 retry 重排 / QualityBounce 重排 / runtime_fanout 重排 / Suspend park；`resume_waiting_interrupt`。
- execute_step：入口捕获 token（`running 且 token NULL` = 外来行 → 防御性 return）；成功尾 / 失败尾 / Suspend / QualityBounce 四个尾全部改条件 UPDATE `WHERE id=:id AND claim_token=:mine` + rowcount。
- Suspend 的 run 写：`WHERE id=:rid AND status='RUNNING'`（expected-from-state）。
- render：入口捕获 token（NULL → 提前 return，省一次渲染钱）；三个终态写（no-spec fail / success / exception fail）谓词从 `render_status==RENDERING` 换 `render_claim_token=:mine`；**全部 10 处既有行 re-pend**（`morph.py:467`、`node_runners.py:927`、`verify.py:767`、`music/node.py:124`、`captions/node.py:271`、`dub/node.py:178`、`reframe/node.py:198`、`filler/node.py:103`、`operations/service.py:319`、`routes/outputs.py:251`）同步置 NULL——少一处 = morph 竞态洞原样保留。
- `_cascade_skip`：skip 子节点时同置 `claim_token=NULL`——**这是有意的超 happy-path 项**：不置 NULL 则下游 running 子节点仍是 last-writer-wins（delta §6-3 已证），置 NULL 把级联语义落成确定性丢弃。保留在批内。
- **fenced-无-side-effects 纪律（核心）**：rowcount=0 → rollback session（executor staged writes 一并丢弃）→ 只记 fenced 日志 → **不 capture / 不 graph sync / 不 cascade / 不 mirror / 不 fire trigger / 不写 run 状态**。刻意的唯二例外：① `finally` 的 `maybe_finalize_run` 照调（行锁 + 终态 early-return，幂等；被级联置 NULL 的节点靠它收官）；② Suspend 的问题消息在其独立 session 已先落库（fenced 后成孤儿问题——expire sweep 只处理 waiting step，孤儿永不过期；窗口极小，**登记为 known residue，后续小批清理，不进 Commit 1**）。
- 部署注记：迁移后在途行 token=NULL → 新代码入口防御 return；部署即重启 worker，在途 asyncio 任务随进程死亡。

**OUT（本批禁止）**：ExecutionAttempt 任何形态 / attempt 语义迁移 / poison-pill 上限 / hold GC / select_clips 收窄 / worker registry / pause-canel / chat 墙钟 / 统一 Policy 层 / AgentBudget。

## 8. Gate F verdict：operations FK —— **原范围不充分，Commit 2 范围修正案**

从代码重追（不信报告）：

- **删除路径全集 = 5 处**：`clips/node.py:320`（select_clips 全清）、`routes/outputs.py:150`（delete_output）、`verify.py:532`（doomed sweep）、`derivative_dispatch.py:805/822`（派生 sweep ×2）；第 6 处 `projects.py:715-717` 已是正确范式。
- **引用 outputs 的 FK 全集 = 2 个**：`operations.output_id` NO ACTION（`tables.py:423`）**和 `publications.output_id` RESTRICT（`tables.py:607`）**。**只清 operations 不够**——已发布产物在任何删除路径上同样炸（RESTRICT）。上轮两份报告均未覆盖此雷。
- **正确顺序的范本就在库内**：`projects.py:715-717` 先 operations → publications → outputs，注释明写 "must go BEFORE outputs"。修法 = 四处对齐该顺序（可抽小 helper）。
- **JSONB/悬挂引用（不炸，本批不碰）**：`workflow_steps.output_refs` / `graph_nodes.spec.output_ids` / `messages.focus_output` / `source_ref.derived_from_output_id`——读容忍/悬挂无害，join 不到即消失。
- **select_clips 语义不动**：本批只加删除顺序；跨 run 全清是独立 P1，禁止顺手改。
- **登记给 W11 的 follow-up**：`delete_output` 路由对「已发布产物」应加 409 守卫（不静默抹发布史）——分发未上线（`DISTRIBUTION.md`：待平台凭据联调），现实暴露面 ≈ 0，随 W11 分发联调批落地；本批先镜像 FK-safe 顺序保证不炸。

## 9. Gold-plating findings

North Star 全文扫描：**无实质镀金**。两处警示（不阻塞）：① §8.5 ExecutionAttempt 字段速写——实施前任何人不得把它当 schema 引用（形态 OPEN 维持）；② §3.1 可替换性表述按 Gate A-1 降级。未发现「现在就设计 Media IR / Policy framework / AgentBudget / 重写 tool 架构 / remix / 改状态机」的偷渡。

## 10. Confirmed coding contract

五态纪律；执行五概念词汇表；Agent 边界精确表述（LLM 面永不写，写活在门后执行体）；能力四分；根原则「execution writes must be fenced by execution identity」；**fenced-无-side-effects 纪律（Gate E 全清单）**；一 commit 一 correctness 问题；`_mutate` 双层 dedupe 永不破坏；select_clips 语义本批不动；FK-safe 删除顺序 = operations → publications → outputs。

## 11. Rejected / deferred work

REJECTED 维持（North Star §11 全表，经 Gate A-3 核对与 ADR 一致）。**DO NOT IMPLEMENT IN THIS BATCH**：ExecutionAttempt 任何形态 / Media IR schema / 统一 Policy framework / AgentBudget / tool 架构重构 / 结构级 remix / 四分注册表重构 / poison-pill 上限 / hold GC / select_clips 收窄 / pause-canel / chat 墙钟 / delete_output 已发布 409 守卫（W11）。

## 12. Final implementation order

**Commit 2（operations+publications FK cleanup）→ Commit 1（claim fencing）**。证据见 §6；两 commit 独立验收、独立回滚。

## 13. Commit 1 exact scope

§7 的 IN 清单全量，OUT 清单全禁。**完成定义**：migration 可升可降；claim/reap/re-pend 全链 token 生灭正确；四尾 + render 三写全部 token-guarded 且 rowcount 检查；fenced 路径零 side effect（除两条例外）；Suspend run 写仅 RUNNING→WAITING_HUMAN 可成；单 worker happy path / retry / QualityBounce 行为不变。

## 14. Commit 2 exact scope

四处删除路径（`clips/node.py:320` / `routes/outputs.py:150` / `verify.py:532` / `derivative_dispatch.py:805/822`）对齐 `projects.py:715-717` 的 FK-safe 顺序（operations → publications → outputs；可抽 helper）。**完成定义**：编辑过（有 operations 行）的产物可删不炸；select_clips 重跑不炸；已发布产物删除不炸（顺序保证，409 守卫归 W11）；select_clips 清除范围与语义逐字节不变。

## 15. Acceptance tests for each commit

**Commit 2**：① 纯函数套件（`_StubDb` 模式先例 `test_graph_wiring_pure.py:81-194`）：helper 语句序 = Operation/Publication delete 先于 Output delete；② e2e/剧本（repo 纪律：真事务行为归 e2e，用户自跑）：产出 clip → 编辑器 set_trim（落 operations 行）→ DELETE /outputs/{id} → 204；「重新剪」触发 select_clips 全清 → run 不炸。
**Commit 1**：① 纯函数套件：token 捕获决策（running+NULL → 拒）/ rowcount=0 分支不触 capture·sync·cascade（stub 记录调用）；② 手工竞态演练（用户自跑）：A claim → 停滞 → reap → B claim → B 完成 → A 醒 → A 终态写 0 命中、无第二条 capture、run 行保持 B 判决；render 同型演练（morph 窗口内 zombie 先完成不得覆写）；zombie Suspend 不得 COMPLETED→WAITING_HUMAN；单 worker 正常 run / retry / QualityBounce 回归。

## 16. Remaining OPEN decisions

1. ExecutionAttempt 形态（独立表 vs attempts JSONB）——等台账/对账需求数据。
2. 结构级 remix 是否产品承诺——产品拍板后立项。
3. AgentBudget 数值。
4. `delete_output` 已发布产物的用户语义（409 vs 级联）——W11 分发联调批拍板（本批镜像顺序已保证不炸）。
5. Suspend 孤儿问题消息清理形态——后续小批。

---

## ARCHITECTURE GATE #2: **PASS**

附三项非阻塞修正登记：① North Star §3.1 可替换性表述建议降级（机制 CURRENT / 实证 TARGET——文档修改与否由你定，本 Gate 未动文档）；② Commit 2 范围从「只清 operations」修正为「operations + publications 双 FK、四处路径对齐 projects.py 范式」（§8）；③ delete_output 已发布 409 守卫登记 W11。
