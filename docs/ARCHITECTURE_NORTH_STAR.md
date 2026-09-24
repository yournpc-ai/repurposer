# ARCHITECTURE NORTH STAR — 目标架构与可靠性主线

> Status: 活跃（2026-09-16 建，Architecture Gate 批——T5 后架构体检（`POST_T5_ARCHITECTURE_AUDIT.md`）与 delta 对抗核验（`POST_T5_DELTA_AUDIT.md`，HEAD `453b73d`）的固化产出；实施边界 2026-09-16 用户拍板：先固化方向盘，再踩油门）。
> 本文回答「我们正在把这个系统建设成什么」——**目标架构（North Star）与可靠性主线的唯一事实源**。现状架构归 `MODULE_ARCHITECTURE.md`；工程地图归 `AGENT_ARCHITECTURE.md`；概念架构归 `DIALOG_WORKFLOW.md`；决策归 `DECISIONS.md`。本文不替代它们，只给方向、边界与实施顺序。
> **五态纪律（全文强制）**：`CURRENT` = 当前代码已存在并经代码验证；`TARGET` = 已明确决定要演进到；`PLANNED` = 已决定、未实施；`OPEN` = 未决定 / 待验证；`REJECTED` = 讨论过、明确不采用。判断优先级：**Current HEAD code > DB constraints / migrations > tests > ADR > 架构图 > 历史计划**。任何一行不得把 TARGET/PLANNED 写成 CURRENT。

## 1. 一句话 North Star

**一个以 Structured Media 为领域核心、以 Execution Kernel 为可靠性核心、以 Agent 为 Decision Producer 的可编排媒体生产系统。**

**对外叙事版**：DAG + 状态机是执行层，不是产品本身——最终产品是一个 **Agentic Content OS**：Agent = 决策层（§3），Structured Media + Decompiler/Compiler = 内容语义层（§9），Execution Kernel = 可靠执行层（§8）。此句只是上一句的展开，不产生任何超出五态表的承诺（统一 Artifact 模型、Media IR 等上层抽象仍为触发制 OPEN）。

**R1 收口后的对外口径（2026-09-17 评审拍板）**：已成立的是**一个 Agent 驱动的 Content Execution System**——Agent → Execution Kernel → Structured Media → Rendered Output 的真实可用闭环（证据 = R1 四条 invariant + S1–S17 剧本族）。「Agentic Content OS」仍是 North Star，但 OS 的高级抽象（统一 Artifact / Media IR / ExecutionAttempt）**不提前承诺、不成 R2/R3 排期暗示**——触发条件满足才进入决策。

### 1.1 愿景词汇 ↔ 现行词汇对照表

拿着 Agentic Content OS 的图读代码时查这张表——左列是讲故事的词，右列是代码里今天的名字与真实进度：

| 愿景词汇 | 现行词汇 / 位置 | 状态 |
|---|---|---|
| Agent / Tool 层 | `app/agents/`（ToolLoopAgent 终态工具机）+ `app/tools/` + perception 只读族 | ✅ CURRENT |
| Decision / Command | 三扇门：`create_run` / `apply_wiring_ops` / `apply_operations` | ✅ CURRENT |
| Workflow DAG | `workflow_steps` + `jobs.py` 队列 + `compile_graph`（拓扑代码裁决） | ✅ CURRENT |
| Execution State Machine（run/task 生命周期 + HITL） | run/step 状态 + interrupt 提问机器 + fencing（R1 B2 ✅）+ run authority 仲裁（R1 B3 ✅）+ retry 封顶终态（R1 B4a ✅） | ✅ CURRENT |
| Task / **Attempt** | step = ✅；attempt 计数器 = ✅（B4a）；**ExecutionAttempt = OPEN**（四证据点触发制，§8.5） | ⏳ OPEN |
| **Artifact 层**（不可变 + parent/version/provenance） | **无统一模型**——其目标已被替代机制部分兑现：operations journal（ADR-032）/ `restore_version` 快照 / 变体并行（ADR-061）/ 内容寻址复用（understanding、skeleton）。统一模型 = 触发制 OPEN | ⏳ OPEN（部分能力 ✅） |
| Structured Media 层（Media Program / AST） | clip-spec（ADR-016 唯一渲染契约）+ CraftSkeleton（ADR-078 首个工艺结构产物）；**Media IR = OPEN** | ✅ 雏形 / ⏳ 深化 OPEN |
| Decompiler / Compiler | `craft_scan` + `Decompile` 节点（video→骨架，T5）/ renderer 确定性渲染（黑盒） | ✅ CURRENT |
| Human-in-the-loop | interrupt/checkpoint 提问机器（S6 族）+ run authority（R1 B3 ✅） | ✅ CURRENT |

用法：对外讲用左列，写代码用右列，评审时倒查「这个词今天的状态配不配得上它的愿景名」——**配不上愿景名的词不许提前用愿景名命名代码**（词汇版「把 OPEN 写成 CURRENT」）。

```
                User
                  │
                  ▼
            Agent Runtime          ← 有界（§6），Decision Producer（§3）
                  │
                  ▼
               Decision
                  │
                  ▼
          Schema / Policy 校验     ← 现行形态是分布式（§3.3 诚实注）
             │          │
           Query      Command      ← 能力四分（§4）
             │          │
             ▼          ▼
        Observation  Execution Kernel   ← 可靠性核心（§8）
                         │
                         ▼
                 Execution Attempt      ← TARGET（§8.5）；CURRENT 只有计数器
                         │
                         ▼
                      Artifact
                         │
                         ▼
                 Structured Media       ← 领域核心（§9）
                       ▲   │
            Decompiler─┘   └─Compiler/Executor
            （video→结构）    （结构→video）
```

核心闭环（TARGET，未闭合）：`Video → Decompiler → Structured Media → Agent/Planner → Decision → Validated Mutation → Structured Media → Deterministic Compiler → Video`，即 **Decompile → Modify → Compile**。

## 2. 概念词典：执行五概念（CURRENT 存在性，源自 delta 核验 §3.1）

这五个概念**永不混用**；后续一切执行层讨论以本表为词汇基线：

| 概念 | 含义 | CURRENT 存在？ | 位置 |
|---|---|---|---|
| status | 行生命周期状态 | ✅ | `workflow_steps.status`（String 无枚举）——只做认领谓词 + execute_step 入口头卫（用过即弃） |
| attempt counter | 认领次数计数 | ✅ | `workflow_steps.attempt`（Integer）——只喂 retry 预算与 billing idem key；**不是执行身份** |
| worker identity | 哪个 worker 实例 | ❌ 不存在 | 无列、无实例 id |
| execution identity | 哪一次执行 | ❌ 不存在 | 无 execution_id / claim_id |
| fencing token | 使旧执行写必失败的令牌 | ✅（ADR-079，2026-09-16） | `workflow_steps.claim_token` / `outputs.render_claim_token`——claim 铸、失势置 NULL、终态写 `WHERE … AND claim_token=:mine` 查 rowcount |

### 2.1 概念词典：内容世界六概念（CURRENT 存在性）

读代码先查这张表——六概念不是冗余，是四个世界各有其主：

| 概念 | 含义 | 位置 | 永不是 |
|---|---|---|---|
| asset | 输入素材（上传 / 贴文升格 / persona 绑定） | `assets` 表 | 产物 |
| output | **统一产物行**（clips 与 derivatives 皆是 `type`，ADR-030） | `outputs` 表 | 素材；版本节点（版本账在 operation） |
| operation | 对已落地产物的编辑账（undo / 快照 / 重放） | `operations` 表（ADR-032） | 产物本身 |
| publication | 产物的发布单（渠道状态机 + 快照语义） | `publications` 表 | 产物本体 |
| graph_node | 画布上的产品对象（持久图，ADR-057） | `graph_nodes` 表 | 执行身份（step 才是） |
| workflow_step | 执行节点（DAG 一步） | `workflow_steps` 表 | 产品对象（graph_node 才是） |

四世界：输入（asset）/ 执行（step）/ 产物与编辑（output+operation）/ 画布投影与分发（graph_node+publication）。可靠性机器各不相同（fencing 管 step、FK-safe 删除管 output、claim 谓词管 asset、状态机管 publication）——这正是不能揉成一个 "Artifact" 大概念的原因。**统一 Artifact 模型 = 触发制 OPEN（§9/§10）**：触发成立时 outputs 自然成为它的第一个 type——概念由需求生出来，不由改名生出来。

## 3. Agent = Decision Producer

### 3.1 含义（TARGET 表述，CURRENT 已大体成立）

Agent 的职责是**产出决策**（choose / request / query / propose / ask），不是操作系统。决策生产者可替换（GPT / Gemini / Claude / Kimi / MiniMax / 本地模型 / 规则引擎）而不改变下游生产系统——**可替换性机制已就位（`providers/llm` 单边界 + T1 三层线格式 + 能力旗标，ADR-039/077），但尚未经第二 provider 真实运行实证（实证 = TARGET，未证明）**——这是该单边界存在的理由。

**CURRENT 证据**：`app/agents/` 包全文无 DB import、无 session——决策纯已经成立（T5 后体检核实）；LLM 能写入的 schema 座位被结构封死的最严先例 = decompile 三座位（`CraftJudgment extra=forbid`，`test_decompile_pure.py` 看门）。

### 3.2 允许 / 永不允许

| Agent 允许 | Agent 永不允许 |
|---|---|
| 查询信息 / 素材（Query） | LLM 面直接写数据库 |
| 提出 edit decision / plan / proposal | LLM 面直接启动 worker |
| 请求用户确认（Interaction） | LLM 面直接改 Artifact / 直接执行 FFmpeg |
| 产出受限 Decision（schema 封死） | LLM 面直接改变 workflow 状态 / 直接 billing |

**正确链路（CURRENT 形态，逐环有代码座位）**：LLM → ToolCall/Decision（tool_loop）→ Schema 校验（Agent 漏斗 pydantic）→ Policy 校验（出书门槛 = `present_plan` 执行内校验 / 出生地 422 / wiring 门规则）→ Domain Command（三扇门：`create_run` / `apply_wiring_ops` / `apply_operations`）→ Execution Kernel（队列认领）→ Attempt → Artifact → Observation（perception 读工具 / 触发回合）。

### 3.3 诚实注（不得误读 §3.2）

- **「Agent 永不写 DB」的准确含义 = LLM 面永不写**。工具**执行体**写 DB 是它们的职责——但只许在门后写（三扇门 + 登记的辅助写口）。`tool_loop.py` docstring 的「三扇写门」枚举滞后于实测（另有 `create_transcript_asset` / `graph_fill.stamp_draft_graph` / run 生命周期 / warms）——`CURRENT` 记录为口径待修订，非架构违反。
- 「Policy / Validator」在 CURRENT 不是一个统一层，是**分布式**（schema 校验在漏斗、出书门槛在工具执行内、拓扑铁律在 compile_graph、权限在门）。统一 Policy 层词汇 = TARGET，不得反写进现状。

### 3.4 与 ADR-052 / ADR-077 的关系

ADR-052 判词「实现层零 agent、全 workflow」维持；ADR-077 收编的两个**有界**座位 = 会话层 ToolLoopAgent + DAG 内有界 loop 节点（三护栏先例：迭代上限 / 报价=fold / 对外=普通节点）。「Decision Producer」是同一判词的更锋利表述，不是翻案。

## 4. 能力四分（Query / Command / Interaction / Runtime）

四类能力永不混为一谈；CURRENT 映射已大体成立，TARGET = 四分成为注册表显式属性：

| 类 | 特征 | CURRENT 映射 |
|---|---|---|
| **Query** | read-only / 幂等 / 不改世界 | ✅ `chat/perception/*` 读工具族（实现里无写函数，逐文件核实） |
| **Command** | 改意图/状态；需校验；可审计 | ✅ 终态工具中的 `start_run` / `edit_output` / `edit_graph` / `propose_tasks`——各落一扇唯一门 |
| **Interaction** | Agent↔Human 协议 | ✅ 终态工具中的 `ask_user` / `present_plan` / `answer`（dock 机器，ADR-053） |
| **Runtime** | 回合/相位/检查点原语 | ✅ **永不作为 LLM 能力暴露**——现行座位 = SSE 相位帧、触发回合白名单、checkpoint/Suspend（代码侧原语） |

## 5. Tool Schema = 安全边界

- **CURRENT**：op 注册表是闭集（`OpDef.writes` 声明写集，启动对账）；op 载荷 = 实体引用（段 id / 锚 / 枚举 / 拍序号），LLM 永不写绝对时间码；LLM 永不写 clip-spec（exemplar 参数代码映射，ADR-078 判词⑤）；decompile 三座位 = schema 即权限的最严先例。
- **REJECTED**：自由 `field/value` ops、arbitrary SQL / Python / FFmpeg——schema 不封口的「工具」本质是远程代码执行。
- **TARGET**：受限 DSL 方向（SetCaptionStyle / TrimClip / ReplaceClip / AddMusic…）——Tool/Decision Schema 本身就是 Agent 的 action space。

## 6. Agent Runtime = bounded agent

- **CURRENT**：会话层 loop 迭代有界（`max_iterations=6`）+ 终态工具停环 + loop 内零副作用（T5 后体检核实）；DAG 内有界 loop 节点三护栏（§3.4）。**已知缺口：`CURRENT` 无墙钟**——6 迭代 × (工具+LLM+repair) 最坏 ~36min/回合（delta 审计登记）。
- **TARGET**：`AgentBudget`（max_iterations / max_tool_calls / max_wall_time / max_token_budget / max_side_effects），数值后定；先把五维预算作为**架构契约**记录，不在本批重写 Runtime。
- **REJECTED**：`while True: call_llm()` 开放式自主（ADR-052 永拒维持：执行 loop / 拓扑塑形 / 自我 steering）。

## 7. SSE / Streaming 原则

**Internal reasoning ≠ Product event**——CURRENT 已成立且比通用表述更严：think 方言封在 provider client（`_ThinkStripper`，ADR-066 方言归 client）；用户面只有打字机散文 + 相位帧（StatusLine 一座两行）+ 触发回合；整段瞬移永禁（打字机律，CHAT_ARCH §8.6）。新增散文通道 / 散文字段 / 提案工具时两牙同批检查的纪律不变。

## 8. Execution Kernel = 可靠性核心

### 8.1 当前基线（CURRENT，R1 B4a 落地后）

`POST_T5_DELTA_AUDIT.md` 登记的四条 P0 **已全部修复**（原文核验于 HEAD `453b73d`），R1 B3/B4a 各补一条：

1. ~~节点终态写无围栏——成功尾/失败尾 = ORM 按 PK 盲写~~ → **已修（ADR-079，R1 B2）**：execute_step 四尾改条件 UPDATE `WHERE id=:id AND claim_token=:mine` + rowcount；fenced → rollback + 零副作用（不 capture / 不 sync / 不 cascade / 不写 run）。
2. ~~渲染守卫是 status 不是身份~~ → **已修（ADR-079，R1 B2）**：render 三处终态写谓词换 `render_claim_token=:mine`；全部 10 处 re-pend 置 NULL；入口 token NULL 提前 return。
3. ~~Suspend 的 run 迁移无 expected-from-state guard~~ → **已修（ADR-079，R1 B2）**：`WHERE id=:rid AND status='RUNNING'`——COMPLETED→WAITING_HUMAN 复活链结构性死亡。
4. ~~`operations.output_id` FK NO ACTION + 删除路径不清 operations~~ → **已修（Gate #2 Commit 2，`6ca3b70`）**：四处删除路径对齐 FK-safe 顺序（operations → publications → outputs）。
5. ~~resume/expire 第二出生通道无守卫——挂起-新开-后答制造双 RUNNING，旧 run 复活整族销毁新 run 产物~~ → **已修（R1 B3，I-EXEC-03/04）**：`resume_waiting_interrupt` 函数体内唯一仲裁座（项目行锁 + 原子重查 `has_active_run`，四入口全继承）；authority 被占 = 再挂+明示（零状态污染）；expire = 答案结算 + 仲裁尝试两动作解耦；authority 空出触发器 = 收官交接钩（`_resume_parked_answered`）+ sweep 重试分支。
6. ~~assets/renders 无执行计数——崩溃环无限重烧、永无终态（`reap_stale` 自认 TODO）~~ → **已修（R1 B4a，ADR-017 修订）**：`attempt` / `render_attempt` 计数列 + claim/reap 封顶终态（> cap → FAILED + 人话行）+ 手动 reprocess 一座复位；意图 re-pend 清零、崩溃 reap 计数。

### 8.2 Race proof 的架构意义

根问题不是四个 bug，是一句话：**写操作没有携带「这次执行是谁」**。`A claim → A 停滞 → reap → B claim → B 完成 → A 醒来 → A 终态写` 全链路上，A 没有任何一个 DB predicate 会失败——结果是 run 行第一写者赢（finalize 行锁是全库唯一真围栏）、step 行最后写者赢、钱包扣两次（ledger 设计上无法区分 zombie 与合法 QualityBounce 重跑）。

### 8.3 根原则（TARGET，一切执行层工作的判据）

> **Execution writes must be fenced by execution identity.**
> 每一次终态写的 WHERE 必须携带本次执行的身份；写不动 = 失去 authority = 丢弃 + 记日志 + **永不 capture**。

### 8.4 Claim Token ≠ ExecutionAttempt（概念分层，永不混淆）

- **Claim Token（CURRENT，2026-09-16 落地，ADR-079）**：`workflow_steps.claim_token` / `outputs.render_claim_token`——claim 时生成、reap/re-pend/resume 时置 NULL、终态写 `WHERE id=:id AND claim_token=:mine` 查 rowcount。已解决 §8.1 的 1/2/3。**它不是执行模型，只是围栏。**
- **ExecutionAttempt（TARGET，长期 execution model）**：回答 Who / When / Which attempt / Which worker / Which claim / What input / What output / What cost / What error / Was it superseded。§8.5。
- 两者有关但不是同一概念；**禁止**以「一次重构全部解决」扩大当前批次 scope，也禁止把 claim_token 命名成 attempt 继续混淆。

### 8.5 ExecutionAttempt（TARGET 模型，未拍板实施期）

```
Task（逻辑节点）
 ├── ExecutionAttempt #1 {started_at, worker_id, heartbeat, finished_at, result, cost, superseded?}
 ├── ExecutionAttempt #2 {…}
 └── current_state（派生）
```

目的不是加表而加表：系统必须能区分「任务是什么」与「某一次执行是谁完成的」。实施后 `attempt` 计数器退役为派生值。**OPEN**：独立表 vs step 上 attempts JSONB 日志（最小形态）——实施前拍板。

### 8.6 Billing boundary（CURRENT 事实 + TARGET 纪律）

CURRENT：`_mutate` 双层 dedupe（NOT-EXISTS 门 + `on_conflict_do_nothing`）是全库唯一真幂等层，**本批及以后永不破坏**；hold→capture→release 语义归 `BILLING.md`。TARGET 纪律：fenced execution（rowcount=0）**永不进入 capture_step**——这是「execution kernel owns billing boundary」的具体含义；禁止用扩大幂等 key 掩盖 race，禁止把 `attempt` 当 execution identity。

## 9. Structured Media 与 Decompiler

### 9.1 CURRENT

- **clip-spec = 现行 Structured Media 形态**：唯一渲染契约（ADR-016），renderer-agnostic（轨道模型 ADR-044，TRACK_REGISTRY 9 轨），渲染服务是可替换黑盒。
- **CraftSkeleton = 首个「工艺结构」内部产物**（ADR-078）：确定性字段零 LLM 是构造性保证（craft_scan 无 provider import + 三座位 schema + 测试看门）；内容寻址复用已成立。
- **Decompiler CURRENT 限制（R1 B1 收口后）**：latest-20 Python 扫描复用 / version 不进 cache key / warm 行无 lineage（三项归 R1.1 C1）；~~decompile 画布孤儿节点 / run 路径不触发 craft 触发回合 / 无 remix e2e 剧本~~（R1 B1 收口：prelude 折叠 + run 路径 fire_trigger + S16 剧本）；**修正**：gaps 有确定性注入进 plan facts（`registry.py:166-178`），skeleton 时序结构有 prompt 侧消费者——但**确定性参数消费者仍只有 count/aspect/captions/music**，结构级 remix 未实现。

### 9.2 TARGET

Structured Media 逐步成长为 **Media IR / AST**：timeline / clips / audio / captions / transitions / effects / output spec / 语义结构信息 /（未来）provenance·lineage。Decompiler 当前谨慎定位 = observable facts + deterministic structure + selected semantic interpretation，逐步增加——不宣称已具备完整 semantic intent / editing grammar / style inference。

### 9.3 范围诚实注

「Structured Media 是领域核心」当前只覆盖**媒体族**（video/audio/image 轨）；**文本族**（post/article/table）是 schema'd payload，没有也没有必要立刻有 media IR。Media IR 主线 = 媒体族方向，不得反写成全产物统一 IR 的既有事实。

## 10. 实施序列（PLANNED，顺序即拍板）

> **2026-09-16 产品-first 重排**：施工顺序从「技术债驱动」翻转为「产品旅程驱动」——**现行批次与顺序的唯一事实源 = `docs/PROGRESS.md` §0**（R1 = J2/J5/J6 must-have：B1 remix 收口 → B2 fencing → B3 run authority → B4a poison-pill；R1.1 = B4b hold GC + B5 W11 + C1 并行）。本节保留技术依赖注记，不再承担排期。

技术依赖注记（被 PROGRESS §0 吸收后的映射）：

```
Architecture Gate（本文，2026-09-16）
  → Commit 2：operations FK cleanup ✅（6ca3b70 已落）
  → B1：remix 旅程收口 + 测试地基（J2）
  → B2：claim fencing（§8.4 短期原语；新 ADR + ADR-017/030/050 修订随实施）——J5 收费诚实前提
  → B3：run execution authority（resume/expire 第二出生通道执法）——J6
  → B4a：poison-pill 封顶——J5 卡死有终态
  →【R1 停止线】
  → R1.1：B4b hold GC（B4a 前置）→ B5 W11（硬前置 = B2：双扣路径封死再接真钱）∥ C1 cache identity
  → ExecutionAttempt 演进（§8.5；独立批次，先拍板形态——四证据点门禁：fenced 频率 / 台账查询模式 / W11 对账 / postmortem 九问）
  → 能力契约显式化（§4 四分注册属性——触发制：首例能力误挂事故或新能力族批量入场）
  → AgentBudget（§6——触发制：跑飞事故 / 台账长尾数据 / 第二 provider）
  → Structured Media 深化（结构级 remix 是产品承诺问题，先拍板再立项）
```

每批只解自己的题：B2 不解 ExecutionAttempt；ExecutionAttempt 不改写围栏语义（它消费围栏）。

## 11. 不做清单（REJECTED / 缓做）

- **REJECTED**（常备否决，维持）：agent 框架（Agno/LangGraph/Mastra 依赖）、开放式自主 loop、LLM 塑形拓扑、静默降级、冻参模板当文案、自由 field ops、arbitrary 代码执行、chain-of-thought 上产品面。
- **缓做（本批及下一批不做）**：重写 Agent Runtime、新建 Tool Framework、完整 Media IR、Billing 重构、旧工具改名运动、为「架构漂亮」加抽象层、personas 拆桌（挂 ADR-042 运营端批次）、用户 pause/cancel（产品拍板先行）。
- **本 Gate 批不做**：任何业务代码 / schema / runtime behavior 修改。

## 12. 文档地图（每类真相只有一个家）

| 信息 | 家 |
|---|---|
| **目标架构 / 可靠性主线 / 五态纪律** | **本文** |
| 现状架构 / 表归属 / 队列机制 | `MODULE_ARCHITECTURE.md` |
| 工程地图（Model/Harness/Graph/Loop） | `AGENT_ARCHITECTURE.md` |
| 对话→生产概念架构 | `DIALOG_WORKFLOW.md` |
| chat 机器规格 / SSE / 打字机律 | `CHAT_ARCHITECTURE.md` |
| 渲染契约（clip-spec / 轨道） | `RENDERING.md` |
| 计费语义 | `BILLING.md` |
| 决策集 | `DECISIONS.md` |
| 用户旅程 | `JOURNEYS.md` |
| 命名 | `NAMING.md` |
| **执行可靠性基线（P0 证据）** | `POST_T5_DELTA_AUDIT.md`（仓库根） |
| 排期 / 需求池 | `PROGRESS.md` |

## 13. 与现行 ADR 的关系

- **兼容继承**：ADR-016（clip-spec 唯一契约）/ ADR-028（拓扑铁律）/ ADR-030（outputs 治理——fencing 为其认领谓词补身份维度，非翻案）/ ADR-032（operations 账）/ ADR-039（四层地图）/ ADR-052/077（厚 agent 判词与有界收编）/ ADR-055（billing）/ ADR-057（图即产品对象）/ ADR-078（decompiler）。
- **实施时需修订（已落地 2026-09-16）**：ADR-017（reap 语义从 ownerless 改 fencing-aware）、ADR-030（render 认领谓词加身份维度）、ADR-050（会话纪律补 guarded-write 纪律）三条修订已随 R1 B2 落档；fencing ADR 已立 = **ADR-079**（随 Commit 1 落地）。
