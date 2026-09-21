# Lifecycle Phase 4 施工合同——Confirmation Doctrine Unification（统一 Paid Authorization path）

> 拍板：2026-09-19（用户，Architecture Freeze）。架构合同 = `docs/DECISIONS.md` ADR-087 §4（Confirmation Doctrine）+ Reversal Ledger R5/R6/R9。
> 终裁：2026-09-20（用户，Decision Gate 四项终裁 D1~D4 + Frozen Rule 1~10——见 §Decision Ledger，**最终施工合同以终裁为准**）。
> 前置：Phase 1（CONFIRMATION_READY 投影戳存在——统一确认门有事实源）。
> 范围纪律：**只做 Paid Authorization path 统一**。Agent preparation path 的分叉（plan path vs propose path 各自的准备流程）**保留不动**——消灭的是路径分叉，不是 preparation 差异，更不是新增一个「propose dock」UI。

## 判词（用户拍板原文，禁止重新解释）

> plan path 与 propose path 可以拥有不同的 Agent preparation path，但不得拥有不同的 Paid Authorization path。
> 正确目标：所有新 Paid Work → 统一 Confirmation-ready Product State → 统一 Confirmation Dock。
> 消灭的是路径分叉，不是新增一个「propose dock」UI。

核心：自然语言请求 = Task Intent ≠ Paid Execution Authorization。**明确禁止 G-explicit task request = paid gesture**——即使用户明确指定输出类型/语言/数量/范围/「直接帮我做」，仍只是明确 Task Intent。

## Frozen Rules（2026-09-20 终裁——最终施工合同）

- **Rule 1** — Natural Language Request ≠ Paid Execution Authorization.
- **Rule 2** — New Paid Work MUST follow: Task Intent → Preparation → PLAN_READY → CONFIRMATION_READY → Explicit Confirmation → Paid Run.
- **Rule 3** — Explicit language never bypasses Confirmation（「直接做 / 帮我生成 / 生成中文和法语视频 / 不要问我直接开始」= G-explicit Task Intent，可减少澄清、直接成 Plan，不得跳过确认）。
- **Rule 4** — Confirmation Dock is the canonical confirmation seat（不存在 G-explicit auto-start / 散文隐式确认 / 模型自判「用户已明确」/ propose path 特殊豁免；dock pill 与 G-1 散文确认 = 同一 task_book 座位，不是两条授权路）。
- **Rule 5** — Approved Scope Continuation may be autonomous.
- **Rule 6** — Scope Expansion MUST require Confirmation.
- **Rule 7** — Continuation / Expansion classification MUST be deterministic and Application-Command / Domain driven.
- **Rule 8** — Activity / prose / prompt / LLM output MUST NOT decide Paid Authorization.
- **Rule 9** — Client-provided tasks MUST NOT be treated as proof of approval.
- **Rule 10** — Unproven continuation MUST NOT default to autonomous Paid Run.

## Decision Ledger（2026-09-20 用户终裁，四项）

### D1 — `autonomy="review"`：RETIRE

所有正常 Paid Run 不再使用 `autonomy="review"`；默认行为 = autonomous continuation。退役理由：picker 已隐藏（`QuestionDock.tsx:56`）用户无真实入口；当前值事实恒 review（`ChatDock.tsx:957` + `setAutonomy` 无活路 `:4038`）；propose path 又不可达；review 的 direction interrupt 是执行中 HITL 语义，不是 Paid Authorization；无足够产品证据证明其应作为正式用户能力存在。**边界**：不是删除 human-interrupt / WAITING_HUMAN 机制——verification escalation 等运行时升级/异常处理机制全部保留（`orchestrator.py:1652/1764/1956`），只移除「review 档导致 understand→plan direction interrupt」这一产品档位（`orchestrator.py:368-381`）。**Batch 7 施工前先列 inventory**：frontend state/picker、request schema、`TaskSpec.autonomy`、orchestrator review 分支、相关测试、文档——禁止顺手删除无关 WAITING_HUMAN 机制。

### D2 — /generate Paid Boundary：SERVER-VERIFIABLE APPROVED RETRY

- **A. 服务端可证 exact retry**（根据历史 run / approved scope / retry reference 确定性证明当前请求只是已有 approved scope 的精确 retry）→ continuation，不需重新 Confirmation。
- **B. 扩张或不可证**（新增 paid output / 新增 paid branch / execution scope 与历史不一致 / 服务端无法证明其属于 approved retry）→ 不得直接 `create_run`；进入 Preparation / PendingPlan / Confirmation Dock → Explicit Confirmation → Paid Run。
- **C. legacy typed Start / old-client fallback** = unproven legacy path；统一 Dock 路径覆盖后逐步退役，不得继续作为隐式授权通道。
- **禁止的授权依据**：「客户端传了 tasks + scope=full」「客户端说这是 retry」「请求来自前端 retry button」——证明必须建立在**服务端已经存在的事实**之上（Rule 9）。保留当前合法的 exact retry 行为，不得为封口而破坏真正的 approved retry（Rule 5）。

### D3 — Start endpoint：SERVER-SIDE confirmation enforcement（Batch 6，独立 commit）

`answer_question(kind="start")` 在进入 paid `create_run` 前由服务端验证：confirmation scope valid ∧ charge semantics ready ∧ no active conflicting run ∧ plan/material prerequisites satisfied ∧ current plan / task_book 与确认范围一致。不满足 → 不得 `create_run`，返回明确 machine-readable blocker，不伪装成普通业务错误。Confirmation Dock 是产品表现层、Explicit Confirmation 是 Paid Authorization——「前端按钮 disabled」不能是唯一防线。先完成 A1/A2 收敛再施工（便于审计与回滚）。

### D4 — `delete_node + run`：RESULTING-SCOPE 分类律

高层 Domain Rule：**Continuation / Expansion MUST be decided from RESULTING PAID EXECUTION SCOPE, not from operation name.** 判定过程：

```
requested graph operations
  → resulting graph / execution closure
  → resulting paid outputs / branches
  → compare against approved execution scope
  → same approved scope    → autonomous continuation
  → expanded scope         → Confirmation Dock
  → unproven               → Confirmation Dock
```

`delete_node` 本身不是产品语义。分类器判断删除之后**最终 execution scope** 是否仍属于 approved scope；当前系统缺少证明所需的 historical facts 时不猜——**unproven → Confirmation** 为临时安全行为。「delete + run 的精确历史 scope comparison」列为后续 domain capability（挂账），不在 Phase 4 以拍脑袋规则完成。

## Product goal

1. 一切新 Paid Work：无 explicit confirmation 不 `create_run`。
2. Approved Scope 内 continuation（retry / internal repair / render continuation / execution step completion / approved-scope graph revision）不被误阻塞。
3. 同类型工作 plan / propose 两路收敛同一 Confirmation Dock（统一 Confirmation-ready Product State 驱动）。

## Step 0 盘点清单（Preflight 已执行 2026-09-20；全文 = `scratch/phase4_step0_inventory.md`）

锚点核于 current HEAD `d3616c2`（原合同锚点核于 `d0006ac`，漂移已更正）。**先盘点后施工——清单已建，允许动代码。**

| 来源（d3616c2 锚点） | 现状 | 产品含义 | 处置批 |
|---|---|---|---|
| `propose_turn.py:330`（`propose_tasks` → `_create_run_from_tasks`） | chat path 提案直接起 run（caption 闸门豁免外） | 新 Paid Work 无确认节拍（Rule 1/2 打击面 A1） | B3 |
| `propose_turn.py:470`（`edit_graph` run op → `_create_run_from_tasks`） | wiring 提案的 run op 直接起 run；`EditGraphArgs.ops` 全词汇可收（`schemas.py:745`），prompt 只引导 edit_prompt+run，代码层无拦 | approved-scope revision 与 scope expansion 无分界（A2） | B1+B2 |
| `service.py:327-394`（`_create_run_from_tasks`） | 命令层统一起 run 座；`scope="full"` 硬编、不设 autonomy | 范围包含性裁决座（Rule 7 代码裁决，非 LLM 自决） | B1 |
| `service.py:1403-1492`（caption fast path） | 确定性 replay → PendingPlan → dock task_book → 估价随行 → Start。**双标方向与旧表述相反：caption 路已是目标形态**，非 caption propose 工作（A1）才是缺口 | parity = 把 A1 抬到同一 dock，不拆 fast path（Rule 4 样板） | B3 随批 |
| IC:50 前端 G-explicit 自动 Start | **已不存在**——`43dbda3`（2026-09-03，ADR-051 批删 `GenerationOverlay.tsx`）物理消失；当前唯一 Start 触发 = dock pill onClick（`ChatDock.tsx:4039→1546`） | R5 锚点更正：Phase 4 无前端移除工作，验收 grep 即可 | B0（本批落档） |
| `autonomy="review"` 档 | **非死档**：plan path 事实唯一实发档（隐藏 picker 钉死 review）；propose path 恒 auto 不可达 | D1 终裁 RETIRE（WAITING_HUMAN/escalation 基建保留） | B7 |
| `turn_tools.py:88-90`（`propose_tasks` 描述） | 「it never starts a run by itself」= 逐字复制 `present_plan`（`:44-47`）的失信文本；`chat_intent_system.j2:19` 又说 "run NEW work"——系统 prompt 与工具描述自相矛盾 | 必须与最终实际语义一致（B3 落地后改写） | B4 |
| `routes/projects.py:840-856`（/generate） | **合同外新发现（Preflight F7）**：tasks≠None 即信客户端任意链——Retry 合法但服务端不可证；arbitrary/unproven 门全开；legacy Start fallback（`ChatDock.tsx:1596-1617`）确认记录仅在客户端 | D2 终裁 SERVER-VERIFIABLE APPROVED RETRY（Rule 9/10） | B5 |

### create_run 全量调用点（F7 sweep，产品代码 4 处无遗漏）

| 座 | 性质 | 批 |
|---|---|---|
| `service.py:1583`（answer_question task_book Start） | 合法确认座（B6 加服务端四合取强制） | B6 |
| `routes/projects.py:693`（/graph/revise，`origin="node_revise"`） | 合法 approved-scope continuation | —（不动） |
| `routes/projects.py:856`（/generate） | D2 灰区 | B5 |
| `service.py:374`（`_create_run_from_tasks`，propose 两出口汇入） | A1/A2 打击面 | B1~B3 |

脚本侧（零触碰）：`bake_image_video_demo.py:244` / `bake_quote_chain.py:213` / `bake_reframe_demos.py:323` / `bake_text_tribe_demos.py:266` / `run_anatomy_matrix.py:229`。

### 锁现状的测试（改写对象登记）

| 测试 | 锁的旧行为 | 处置 |
|---|---|---|
| S7-B（`chat_scenarios.py:2180-2205`） | chat path 无第二语言 → 当轮直起 run + `caption_mode=source_only` | B3 改写为新确认路径 expected |
| S7-A/C（`:2129-2178` / `:2207-2277`） | caption 闸门 → 答 → dock → Start | 保绿（已是目标形态） |
| S4-A2（`:1478-1508`） | edit_graph 修订 → run_birth 直起 | B2 保绿（edit_prompt = 自治 continuation 不受阻） |
| `terminal_tool_of` 的 `run_birth` 类（`:687-690`） | harness 对「提案工具当轮起 run」的判别 | B2/B3 随语义改写 |
| S13（`:2780-2867`） | plan Start 与 /generate 双路 422 形状 | 保绿 |

## Contract changes

- ADR-087 §4 是唯一合同：Task Intent → Preparation → PLAN_READY → CONFIRMATION_READY → Explicit Confirmation → Paid Run；Frozen Rule 1~10 与 D1~D4 随本批落档（ADR-087 §4 修订 bullets + Reversal Ledger R9 + Consequences Phase 4 行）。
- Scope Expansion（新增未确认付费输出 / 新增付费分支 / 超出已确认范围）必须重新 Confirmation；**范围包含性由 Application Command 层代码裁决，不是 LLM 自决**（Rule 7）；判定对象 = **结果付费执行范围**（D4 resulting-scope 律），不是操作名。
- Caption/Non-caption Parity：caption 特殊性仅限参数收集 / 前置提问 / 模式与语言格式选择。
- Estimate：不阻塞 PLAN_READY；Paid Run MUST NOT begin before charge semantics disclosed（ADR-087 §2.1）∧ explicit confirmation accepted。
- Reversal Ledger R5（IC:50 自动 Start 退役——代码已先于拍板消失）/ R6（ADR-054 §1194 绝对读法胜；密度律不动）/ R9（`autonomy="review"` 退役）随本批生效。

## Contract Matrix（终裁版 2026-09-20）

| Entry | Paid Work? | Existing Approved Scope? | Confirmation | Canonical Path |
|---|---|---|---|---|
| propose_tasks | FACT：付费（出生即 hold，`orchestrator.py:1132-1135`） | FACT：否（新工作） | GAP：今日零确认直起（`propose_turn.py:330`） | CONTRACT：dock → 显式确认 → Start 座（B3） |
| edit_prompt（filled 节点）+run | FACT：付费重跑 | FACT：是（同节点身份、边不变、`node.state` 可证） | CONTRACT：自治 continuation | continuation（B2 放行） |
| edit_prompt（draft 节点）+run | FACT：执行未确认计划 = 新付费工作 | FACT：否（`node.state=="draft"` 可证） | GAP：今日混在 A2 直起里 | CONTRACT：归计划修订/dock（B2） |
| delete_node + run | FACT：删除本身无新付费产出；run 批重跑剩余子图 | D4：由**结果付费执行范围**判定；历史比对能力缺席 → unproven | CONTRACT：unproven → dock（临时安全行为，非归类；精确历史比对 = 后续 domain capability 挂账） | dock（B2 兜底） |
| add_node | FACT：新付费分支（`produces_outputs` ∨ fold 非零可证） | FACT：否 | GAP：今日混在 A2 直起里 | CONTRACT：dock → 确认（B2） |
| connect（改既有节点输入集） | FACT：下游以新输入组合执行 = 新 execution scope | FACT：否（图边可证） | GAP：同上 | CONTRACT：dock → 确认（B2） |
| disconnect | FACT：编译器内部手势（chat 永不发射，`graph_store.py:106-113`） | —（chat 面不可达） | —（出 chat 范围） | 编译器内部（不动） |
| /generate retry（服务端可证一致） | FACT：付费 | D2-A：须服务端确定性证明（历史 run context / retry 引用） | GAP：今日无证明座 | CONTRACT：证明后自治（B5） |
| /generate arbitrary / unproven tasks | FACT：付费 | D2-B：不可证 | GAP：今日门全开（Rule 9 逐字违反） | CONTRACT：不直接 create_run → preparation/confirmation（B5） |
| /generate legacy typed Start fallback | FACT：付费 | D2-C：unproven legacy | GAP：确认记录仅在客户端 | CONTRACT：统一 Dock 覆盖后退役/收敛，旧数据读容忍（B5） |
| answer_question(start)（pill 与 G-1 同一座） | FACT：付费 | FACT：是（docked PendingPlan 即 approved scope） | FACT：显式手势——确认座本体；D3：Batch 6 加服务端四合取强制 | canonical（B6 加固） |
| caption fast path | FACT：答后经 Start 付费 | FACT：replay stash = 提案 scope | FACT：dock + estimate + Start 全链（`service.py:1459-1483`） | canonical（收敛样板，不动） |

## Files（按批次；预判以批次 preflight 为准）

- **B1**：`apps/api/app/chat/service.py`（`_create_run_from_tasks` 周边——分类器座位，additive）或新模块；`apps/api/tests/` 新增分类器纯测试文件。
- **B2**：`apps/api/app/chat/propose_turn.py`（`_edit_graph` dispatch 接分类器：自治放行 / 扩张与 unproven 转 dock）。
- **B3**：`apps/api/app/chat/propose_turn.py`（`_propose_tasks` → PendingPlan + dock）；复用座位 `service.py`（`sync_plan_question` / `_safe_task_estimate` / `stamp_draft_graph` / PendingPlan / 角色 pins stash）；剧本 S7-B 改写。
- **B4**（独立 commit，prompt 面）：`apps/api/app/chat/turn_tools.py`（propose_tasks / edit_graph 描述）+ `apps/api/app/prompts/chat/chat_intent_system.j2`（run 语义与确认措辞）。prompt 不得重定义 lifecycle / scope classifier。
- **B5**（独立 commit）：`apps/api/app/pipeline/routes/projects.py`（/generate server gate + retry 证明座）；前端最小跟随（retry 携带证明 `projects.$id.index.tsx`；legacy fallback 收敛 `ChatDock.tsx`——收敛为非授权通道，不新造 UI）。
- **B6**（独立 commit）：`apps/api/app/chat/service.py`（`answer_question` Start 分支接 lifecycle 四合取强制）+ 纯测试 + 剧本。
- **B7**（独立 commit；**inventory 先行**）：`apps/web/src/components/chat/ChatDock.tsx`（state/prop）、`apps/web/src/components/chat/QuestionDock.tsx`（picker 块）、i18n（`en.ts` / `zh.ts` 的 `questionDock.autonomy.*`）、`apps/api/app/models/schemas.py`（`:245` / `:888` / `:3234`）、`apps/api/app/pipeline/orchestrator.py`（`TaskSpec.autonomy` `:144` + review 分支 `:368-381`）、`apps/api/tests/test_decompile_pure.py`（`:277-281`）、docs。**WAITING_HUMAN / interrupt / expiry sweep / verify escalation 一律不动**。
- **B8**：`apps/api/scripts/chat_scenarios.py`（改写 + 新增）+ `docs/tasks/verification-contracts.md` §2 + `docs/CHAT_ARCHITECTURE.md` §3 + ADR-087 Consequences 回填 + PROGRESS §0.2。

## Tests（Claude 编写，用户自跑）

- **B1 分类器纯测试矩阵**：edit_prompt(filled)=自治 / edit_prompt(draft)=dock / add_node=扩张 / connect 改既有节点输入=扩张 / delete_node+run=unproven→dock（D4 临时安全行为）/ 纯 delete 无 run=无付费动作。
- **B2**：S4-A2 保绿（自治不受阻，Product goal 2）；新增 scope-expansion 转 dock 用例。
- **B3**：S7-B 改写（propose 新工作必须经确认拍）；S7-A/C 保绿；新增「chat path 新工作 → dock → G-1 散文确认 → Start」剧本。
- **B4**：prompt_gate 三探针（plan path 回归门）+ chat 侧剧本当探针（S4-A2/S7/S9/S20——chat_intent prompt 无探针覆盖是已知盲区）；失败先复跑一次再 `scratch/router_ab_probe.py` 二分，**禁止回调阈值凑绿**。
- **B5 六例矩阵（D2 终裁指定）**：① exact approved retry → continuation；② same tasks but altered scope → confirmation；③ new task/output → confirmation；④ arbitrary tasks → rejection or preparation/confirmation；⑤ missing retry proof → never direct create_run；⑥ legacy fallback → never direct paid run。S13 保绿。
- **B6 六例矩阵（D3 终裁指定）**：confirmation_ready=true → allowed；false → blocked；charge semantics unavailable → blocked；scope mismatch → blocked；active conflicting run → blocked；explicit confirmation missing → blocked。
- **B7**：S6/S17 interrupt 机器剧本保绿（基建未伤证明）；review-tier 纯测试改写；prod 存留 WAITING_HUMAN run 数据排查（机器保留，既有 park 仍可答/过期）。
- 预部署门禁顺序：纯 pytest → prompt_gate → chat_scenarios 全量。

## Migration strategy（批次序 B0→B8，每批独立 commit）

| Batch | 内容 | 状态 |
|---|---|---|
| **B0** | Decision Ledger + Frozen Rules 落档 + 锚点更正（R5 前端已完成 / review=活档 / caption 方向）+ Contract Matrix 终裁版（**docs-only，本批**） | ✅ 2026-09-20 |
| B1 | deterministic scope classifier（additive 先行，纯测试先行，零行为切换，无前端改动，无图路由改动）。**落地形态（2026-09-20 用户裁定——可扩展性护栏）**：分类器**零 op 词汇**——不重演 ops，消费 wiring 门前后图 facts 纯比对（D4 结果 scope 律，双写漂移从根上消失；新 op/节点族/工具对分类器不可见）；座位 = `app/pipeline/scope_classifier.py`（纯核+装配器，lifecycle.py 同款）+ `test_scope_classifier_pure.py`（27 例） | ✅ 2026-09-20 |
| B2 | A2 切换：edit_graph 按分类器——approved continuation 自治 / scope expansion → PendingPlan+Dock / unproven → PendingPlan+Dock（零 LLM 决策）。**落地形态（2026-09-21）**：`propose_turn._edit_graph` 门前快照 → savepoint 过门 → 门后 facts → 分类器；continuation 直跑不变（S4-A2 = approved+拓扑不变 → 天然 continuation，剧本零改动）；expansion/unproven → **savepoint 回滚门内变更**（规避 LLM add_node 缺 fill_key 双生风险 + bail 后图原样恢复）→ dock 走 caption replay 同款机器（PendingPlan + sync_plan_question 自带 draft stamp + 估价，Start 原地填充）。**§8 复议点 fired（同日修正）**：`produces_outputs=False` ≠ 免费——它是 settle 簿记旗，`translate_clip`/`dub_clip`/`render`/`research` 全 False 全付费；付费标记修正为 **registry-known 即付费**（`produces_outputs is not None`），note-only 特例整体退役 + 两把修正锁入纯测试 | ✅ 2026-09-21 |
| B3 | A1 切换：propose_tasks → PendingPlan → task_book/dock → estimate/charge semantics → PLAN_READY → CONFIRMATION_READY → explicit Start → Paid Run；**禁止同 turn create_run**；复用既有座位，禁止新确认 UI。**落地形态（2026-09-21）**：`_propose_tasks` 出口改写——caption 闸门顺序不变 → `validate_task_list` 提前到 dock 前（ToolRejected 照旧喂 loop，仅 registry-valid 链入 dock；出生门其余约束——media gates / 缺素材 / active-run——全部移交 Start 422，plan path 自家姿态，dock 中的计划保持 pending 可修订后重 Start）→ caption_mode 随 dock 的 intent（原：同 turn TaskSpec）→ **`_dock_plan_as_question` 唯一 dock 座**（B2 的 `_edit_graph` dock 分支同批收编共用，caption replay 机器一份不再双写）。计费耳语随行：重型计划卡 `defaultPathLine` 下 + 单任务流内（密度律唯一价格面，NULL 估价退无数字版）`generationOverlay.chargeNote(WithEstimate)`（BILLING §2.1 Held+Actualized 披露闭缝，零机器改动）。剧本：S7-B 翻转（dock + `intent.caption_mode=source_only` + Start → `run.context`）+ **S4-A3 expansion dock 剧本座整面落地**（路由无关：task_book + 零 run + draft 预览 + Start 生 run 带链，同 turn 直跑 = 教义红线硬红）；S4-A2 / S7-A / S7-C 保绿 | ✅ 2026-09-21 |
| B4 | prompt 合同修正（独立 commit；只修 propose_tasks / edit_graph 描述 / run 语义 / 确认措辞）。**落地形态（2026-09-21）**：`turn_tools.py` propose_tasks 描述补 dock 座+确认出生点（「never starts a run by itself」B3 后已是真话）、edit_graph 描述 = confirmed scope 内直跑 / 新增付费工作转 dock；`chat_intent_system.j2:19` "run NEW work" → propose NEW work + dock 待确认 + run 只在显式确认后出生、`:23` bare run op 改 "targets" + continuation/expansion 双形态陈述；`schemas.py` EditGraphArgs docstring 同律修正（**经 `model_json_schema()` description 上 wire = prompt 面**，Preflight 实证）；registry catalog 行（tool/wiring）= op 机制层恒真不动；classifier 留代码（Rule 7/8），prompt 只陈述合同不做分类；WiringProposal docstring 非模型面留 B8 docs 收口 | ✅ 2026-09-21 |
| B5 | /generate server gate（独立 commit；approved retry=服务端可证 continuation，否则不直接 create_run；legacy fallback 退役/收敛；不破坏合法 retry）。**落地形态（2026-09-21）**：`classify_chain_against_history` 升两级证明——tier-1 `exact_retry`（全链逐字）+ tier-2 `family_retry`（**单条历史链非空有序子序列** + spec 工作字段逐字等——整类重做形状；跨链组合/重排/参数改动/空链全部不可证；`_normalize_chain` 拆为 `_spec_projection`+内联，死码清除）；路由门在 `seed_project_prompt` 前：tasks≠None 即查 `load_historical_chains` + 分类器，非 continuation → machine-readable 422 `scope.unproven`（reasons 随行），**先于余额检查开火**；`GenerateRequest` 加四个 retry 引用字段（persona_id/caption_mode/source/exemplar——回声 = 引用非证明，TaskSpec 逐字存储使真 retry 的 context 与原 run 相等）；前端 handleRetry 回声全工作字段（tier-2 天然 admitted，**合法整类重做零破坏**），ChatDock legacy fallback 收 `scope.unproven` → 诚实对话确认引导行（en/zh），非授权通道收敛零新 UI；targeted scopes（tasks=None）本批不动在册；S13 种历史链 fixture 保绿 + 新增不可证 wire 断言 | ✅ 2026-09-21 |
| B6 | Start server-side confirmation enforcement（独立 commit，A1/A2 收敛后）。**落地形态（2026-09-21）**：`evaluate_start_gate` 纯核 + `StartGateVerdict`（lifecycle.py，D3 六例矩阵 8 例纯测试）——评估序 = superseded→409 `start.scope_mismatch` / already_answered→409 / no_pending_plan→409（③⑥同码，§3 等价 charge≡has_pending_plan）/ empty_chain→422 / 四合取戳未就绪→422 `start.blocked` 携戳自身 blocker ids；`answer_question` Start 分支接门（dock pill 与 G-1 散文确认同一座——plan_turn._start_run 同函数漏斗）：结构化守卫全机器可读化（question 解析前移 + task_book 限定 `start.scope_mismatch`/`start.already_answered`，他 kind 原形状不动），门先于 stamp_draft_graph 与 create_run 开火；**同批 bug fix**：`pending_plan` 传参 = `True`（answer 写入先于 dispatch，`is_pending_plan` 要求未答行在此恒 False——误传会让 gatherer 落 prerequisite 分支全量误阻，S1/S4/S7 首跑 0/5 取证，修复后全绿）；S13 尾部新增活跃 run Start 阻断 wire 座（`start.blocked` + `active_run` + run 计数恒 2）；前端零改动（客户端本就读戳禁钮，服务端阻断是竞态兜底） | ✅ 2026-09-21 |
| B7 | `autonomy="review"` 退役（独立 commit；inventory 先行；保留 WAITING_HUMAN/escalation 基建）。**落地形态（2026-09-21）**：inventory 全触点核于 HEAD `2230714`（grep 实证 `run.context["autonomy"]` 零读者）——① orchestrator：`TaskSpec.autonomy` 字段整删 + review 分支移除，understand→plan 恒直通（`plan_inputs=[1,2]`，decompile append 不动），interrupt 机器（SuspendRun / resume / bail / expiry sweep / verify escalation `:1652/1764/1956`）零触碰；② schemas：`GenerateRequest.autonomy` 整字段移除（无 `extra="forbid"` → pydantic 默认 ignore，旧客户端静默兼容），`StartAnswerRequest`/`ChatRequest.autonomy` **保留读容忍**（`extra="forbid"` 下移除会 422 旧客户端）注释改 RETIRED+IGNORED；③ 写入面三处删行（`routes/projects.py` / `service.py` / `plan_turn.py`），新 run.context 行自然无 autonomy 键；④ 前端整块清除：ChatDock state/import/三处载荷/deps/props + QuestionDock picker 块与 DropdownMenu/ChevronDown imports + `chat-stream.ts` 两类型字段 + i18n `questionDock.autonomy.*`（en/zh）；⑤ 测试：`test_decompile_injection_survives_review_tier` 改写为 `test_decompile_injection_no_direction_interrupt`（锁新形态：exemplar pinned + 无 interrupt + `plan.inputs={1,2,decompile}`），`test_scope_classifier_pure.py` 的 autonomy fixtures 不动（旧 review 行不影响链匹配的读容忍证明座）；⑥ docs 现在时改写同批（NAMING 自治档行删 / CHAT_ARCH 三处 + checkpoint bullet 两处 review 档措辞 / API.md 六处）；S6/S17 零改动保绿（`seed_parked_interrupt` 直建 WAITING_HUMAN+interrupt 机器不依赖编译期档位，seed context 的 `autonomy:review` 恰是旧行读容忍座）；prod（dev 库）排查：0 WAITING_HUMAN run / 0 waiting interrupt / 0 review-context 行——无存量 park，读容忍纯防御；R9 生效登记与 ADR-087 Consequences commit 范围留 B8 | ✅ 2026-09-21 |
| B8 | 剧本 / 验证 / docs 收口。**落地形态（2026-09-21，施工面）**：**WiringProposal docstring 现在时改写**（B4 挂账收口——非模型面，prompt_gate 三探针实证零扰动）：分类器裁决语义（approved continuation 自治重填 / expansion·unproven 回滚转 dock）取代「修订一种形态」旧述；**CHAT_ARCH §3 工具网格** propose_tasks/edit_graph 两行现在时（dock 待确认 / D4 双形态）；**verification-contracts**：§2 Scope 分类行陈旧片段修正（🟡→🟢，B2/B3/B5 全接线）+ §6 S11 断言迁移登记（`in (True, "true")`，产品侧 coercion 仍挂账）+ §6 CHAT_ARCH §8.6 相位帧残段登记（Phase 3 债）；**ADR-087 R9 生效登记** + **Consequences Phase 4 行 commit 范围补齐**（`b0a3667`→`61181d1`+本批）；**剧本**：S11 fixture 律硬化（material ready 声明——B6 门下裸 PENDING = 确定性 material_failed）+ S19 改写为 ADR-080 第二谓词端到端座（在途 defer → 收敛静默 → **bail** 清 pending → 补发言；不用 Start 的原因见下）+ S16 exemplar 恢复 FAILED 原设计；验收 grep：`_propose_tasks` 零 `create_run` 调用。**B8 取证新猎三项 doctrine 悬案（verification-contracts §4 注册）——已全部拍板（2026-09-21），修复另起后续批**：① **空散文 dock 永不 ready vs P8「计划散文非空」**——`present_plan` 空 content 通道是 LLM 合法形态（实证 S19 dock 行 `content:""`+`intent.answer:""`，近期 3 次 dock 2 次空），caption 回放自 TaskListProposal stash 确定性 `answer=None` → Start 422 `start.blocked` **不携 blocker id**（D3 机读性同损），前端 Confirm 永禁无解释；**拍板 = 选项 B（P8 翻案 → ADR-087 Reversal Ledger R10：确认 scope = 卡载荷，散文降装饰）**；② **触发回合落点竞态**——ADR-080 第二谓词只在准入时评估，落 dock 不复评：warm/run_completed 触发的建议问 dock 抢确认座（S16-P2 实证计划 dock 与 `trigger_turn_spoke` 同秒，`is_pending_plan` 翻 false → Start 路由去 chat 路弹跳）；**拍板 = (a) 落点复评命中即整体静默**；③ **material gatherer 项目级 any()**（B7 已注册）——S16-P2 Start 红座 = 常驻验收位；**拍板 = plan-scoped 收窄**。**验收状态**：compileall + 纯 pytest 352 绿 + check_gates OK + prompt_gate 三探针 PASS + tsc 基线不变 + 剧本 S11/S19 绿、S16 红于在册座（修复批落地后全绿收口） | ✅ 2026-09-21（三项悬案已拍板，修复另批） |

## Rollback strategy

逐批独立 commit，回滚 = revert 对应批。B1 分类器 additive 零行为切换（revert 即无痕迹）；B2/B3 出口 switch 各自 revert；B5/B6/B7 各自独立 revert 互不粘联。

## Acceptance criteria

- 一切新 Paid Work：无 explicit confirmation 不 `create_run`（grep + 剧本可证——propose 两出口无直起路径）。
- approved scope continuation 不被误阻塞（S 族剧本回归全绿；exact retry 全绿）。
- 同类型工作 plan / propose 两路收敛同一 Confirmation Dock。
- continuation / expansion 分类全走确定性 domain facts（Rule 7——零 LLM 自决，代码可证）。
- /generate 无「传 tasks 即信」（Rule 9/10——B5 六例矩阵绿）。
- Start 服务端四合取强制（B6 六例矩阵绿；machine-readable blocker）。
- `propose_tasks` 描述与实际语义一致（失信文本清零）。
- `autonomy="review"` 档退役且 WAITING_HUMAN/escalation 基建保留可证（S6/S17 保绿）。
- prompt_gate 三探针过；chat_scenarios 全量绿。

## Prohibited Behaviors

- 禁止给 propose path 发明第二个 dock UI（统一 Confirmation Dock 唯一）。
- 禁止把范围包含性裁决交给 LLM（Rule 7——命令层代码裁决）。
- 禁止用 prompt / Activity / LLM 输出控制 paid authorization（Rule 8）。
- 禁用客户端字段或客户端声明证明 approved scope（Rule 9——证明建立在服务端既有事实上）。
- 禁止 unproven continuation 默认自治起 run（Rule 10）。
- 禁止按操作名给 `delete_node` 拍脑袋归类（D4——结果付费执行范围判定；缺事实 = unproven → dock）。
- 禁止顺手删除 WAITING_HUMAN / interrupt / expiry sweep / verify escalation 基建（D1 边界）。
- 禁止把 /generate 门（B5）塞进 A2 批；禁止把 Start 服务端强制（B6）与 A1/A2 混批。
- 禁止改动 Agent preparation path 的分叉（plan/propose 各自准备流程保留）。
- 禁止让 estimate completeness 阻塞 PLAN_READY（ADR-087 §2）。
- 禁止破坏密度律（ADR-054 不动——单任务 = 纯散文确认仍是确认手势）。
- 禁止顺手拆 service.py / ChatDock（Phase 6 的事）。
- 禁止 opportunistic refactor / 顺手重构 / 改 Canvas routing / 改 Product Graph canonical 结构 / 把 Execution Graph 暴露成 Product Graph。
- 禁止回调 prompt_gate 阈值凑绿；禁止因为测试旧了就改 contract、为了绿测试而降低 doctrine。
- 施工中发现冻结 doctrine 与代码事实冲突：**STOP——先报告 contradiction / affected contract / affected call sites / proposed options，不自行改变 doctrine**。

## 收尾报告格式（每 Phase 同律，§十六）

Goal / Current evidence / Contract changes / Files / Tests / Migration strategy / Rollback strategy / Acceptance criteria / Status（日期 + commit 范围 + 验证状态——compileall / import 探针 / tsc / 剧本 = 用户自跑，报告标注「未跑验证」项）；另附 Step 0 盘点清单全文。

## Docs update（随批）

- ADR-087 §4 修订 bullets + Reversal Ledger R5 锚点更正 / R9 + Consequences Phase 4 行回填（B0 已落；commit 范围随 B8 补齐）。
- CHAT_ARCHITECTURE §3（终态工具集）现在时改写（propose_tasks 语义，B3/B4 后）。
- PROGRESS §0.2 状态行更新（B0 已落；随批续写）。
- verification-contracts §2 Confirmation Doctrine 行（B1~B6 新验证座随批登记）。

## Status

施工面收口，三项悬案已拍板待修复批（2026-09-19 建档；2026-09-20 Preflight 盘点完成 + Decision Gate 四项终裁 + **Batch 0 落档 ✅** + **Batch 1 落地 ✅**——`pipeline/scope_classifier.py` 零-op-语义纯核+装配器 + 纯测试全绿，additive 未接线；2026-09-21 **Batch 2 落地 ✅**——edit_graph 按分类器裁决（continuation 自治 / expansion·unproven 回滚转 dock）+ §8 付费标记修正（registry-known 即付费）；2026-09-21 **Batch 3 落地 ✅**——propose_tasks 出口切换（同 turn create_run 全路径禁止，`_dock_plan_as_question` 唯一 dock 座收编 B2 分支）+ 计费耳语 `chargeNote(WithEstimate)` 双形态随行（BILLING §2.1 披露闭缝）+ 剧本 S7-B 翻转 / **S4-A3 expansion dock 座整面落地** / S4-A2·S7-A·S7-C 保绿；验证 = compileall + 纯 pytest 27 绿 + tsc 零新增错 + 剧本 S4/S7 复跑（见 commit 报告标注）；2026-09-21 **Batch 4 落地 ✅**——prompt 合同修正（propose_tasks / edit_graph 描述 + `chat_intent_system.j2` run 语义与确认措辞 + EditGraphArgs docstring——`model_json_schema()` description 上 wire 实证为 prompt 面），「propose 当轮直跑」残余表述清零，工具描述 / 系统 prompt / registry catalog 行三处一致，classifier 留代码 prompt 不分类（Rule 7/8）；验证 = compileall + 纯 pytest 332 绿 + **prompt_gate 三探针 36/36 两连 PASS** + tsc 2 预存错基线不变 + check_gates OK + 剧本 S4/S7/S1/S5 全绿（worktree API :8001 + worktree worker，首跑即绿——S5 在册方差窗口未出现）；2026-09-21 **Batch 5 落地 ✅**——/generate server gate（D2 终裁 SERVER-VERIFIABLE APPROVED RETRY）：链分类器升两级证明（`exact_retry` + `family_retry` 单链有序子序列），路由门 tasks≠None 即查、不可证 → machine-readable 422 `scope.unproven`（先于余额检查，永不 create_run，Rule 9/10）；`GenerateRequest` 四 retry 引用字段 + 前端 handleRetry 全工作字段回声（合法整类重做零破坏，Rule 5）+ ChatDock legacy fallback 收敛非授权通道（`scope.unproven` → 诚实引导行，零新 UI）；D2 六例矩阵 + family tier 共 12 例纯测试落地（39/39），S13 种历史链保绿 + 不可证 wire 断言（run 计数恒 1）；验证 = compileall + 纯 pytest 344 绿 + prompt_gate 三探针 36/36 PASS（零 prompt 改动 = 零扰动证据）+ tsc 2 预存错基线不变 + check_gates OK + 剧本 S13/S4/S7/S1/S5 全绿首跑即过；targeted scopes（tasks=None）与 legacy slot-run 整类重做不可证在册（dock 路径覆盖，D2-C）；2026-09-21 **Batch 6 落地 ✅**——Start 服务端四合取强制（D3 终裁）：`evaluate_start_gate` 纯核（lifecycle.py）+ `answer_question` Start 分支接门，结构化守卫全机器可读化（`start.scope_mismatch`/`start.already_answered`/`start.no_pending_plan`/`start.empty_plan`/`start.blocked` 携戳 blocker ids），「前端按钮 disabled」不再是唯一防线；G-1 散文确认与 dock pill 同一座同批覆盖（plan_turn._start_run 同函数漏斗）；同批 bug fix（`pending_plan=True` 直传——answer 先写后 dispatch 使 `is_pending_plan` 恒 False，误传全量误阻 S1/S4/S7 首跑 0/5 取证修复后全绿）；D3 六例矩阵 8 例纯测试 + S13 尾部活跃 run 阻断 wire 座；验证 = compileall + 纯 pytest 352 绿 + tsc 基线不变（零前端改动）+ check_gates OK + prompt_gate 三探针全 PASS（B 11/12 超阈，provider 分钟尺度漂移在册）+ 剧本 S13/S1/S4/S7/S5 全绿；2026-09-21 **Batch 7 落地 ✅**——`autonomy="review"` 退役（D1 终裁/R9）：inventory 先行（grep 实证 `run.context["autonomy"]` 零读者）→ `TaskSpec.autonomy` 字段整删 + review 分支移除（understand→plan 恒直通），`GenerateRequest.autonomy` 移除（默认 ignore 兼容旧客户端），`StartAnswerRequest`/`ChatRequest.autonomy` 保留读容忍（accepted + IGNORED），前端 state/picker/i18n/chat-stream 类型整块清除，review-tier 纯测试改写为新形态锁（无 interrupt + `plan.inputs={1,2,decompile}`）；**WAITING_HUMAN / interrupt / expiry sweep / verify escalation 基建零触碰**；验证 = compileall + 纯 pytest 352 绿 + tsc 2 预存错基线不变 + check_gates OK + prompt_gate 三探针全 PASS（A 12/12 / B 12/12 / C 11/12——零 prompt 改动 = 零扰动证据）+ 剧本 S6/S17/S13/S1/S4 首跑全绿（interrupt 机器未伤实证）；dev 库排查 0 WAITING_HUMAN run / 0 review-context 行（无存量 park，读容忍纯防御）；下一批 = B8 收口（剧本现在时改写 + WiringProposal docstring + ADR-087 Consequences commit 范围补齐 + R9 生效登记）；2026-09-21 **Batch 8 施工面落地 ✅——三项悬案已拍板，修复另批**：WiringProposal docstring 现在时（B4 挂账收口，非模型面——prompt_gate 三探针实证零扰动）+ CHAT_ARCH §3 工具网格两行 + verification-contracts §2 Scope 行陈旧片段修正（🟡→🟢）+ §6 登记（S11 断言迁移 / CHAT_ARCH §8.6 相位残段 Phase 3 债）+ ADR-087 R9 生效登记 + Consequences commit 范围补齐（`b0a3667`→`61181d1`+本批）+ 剧本 S11 fixture 律硬化 / S19 改写 ADR-080 第二谓词端到端座（bail 清 pending）/ S16 exemplar 恢复 FAILED 原设计；验证 = compileall + 纯 pytest 352 绿 + check_gates OK + prompt_gate 三探针 PASS + tsc 基线不变（零前端改动）+ 验收 grep（`_propose_tasks` 零 `create_run` 调用）+ 剧本 S11/S19 绿、S16 红于在册座。**B8 取证新猎三项 doctrine 悬案（verification-contracts §4 注册）——已全部拍板（2026-09-21），修复另起后续批**：① 空散文 dock 永不 ready vs P8「计划散文非空」冻结合取——**拍板 = 选项 B（P8 翻案 → R10：确认 scope = 卡载荷，散文降装饰）**；② 触发回合落点竞态——**拍板 = (a) 落点复评命中即整体静默**；③ material gatherer 项目级 any()——**拍板 = plan-scoped 收窄**（S16-P2 Start 红座 = 常驻验收位，修复批落地后全绿收口）。其余验收标准均已兑现（新 Paid Work 无确认不起 run / continuation 不误阻 / 两路同一 dock / Rule 7 确定性分类 / D2·D3 矩阵绿 / review 退役基建保留 / prompt_gate 过）。
