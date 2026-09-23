# Agent Tools Forensic Audit — 2026-09-22

> **Status**: read-only audit of current `main`（Phase 0–5 全部落地后、PFA 验收 30/30 绿之后的快照）。**后续归宿（2026-09-22 落档批）**：P0-① → ADR-089 §4 合同已立（Confirmed Scope Snapshot，实现待 ADR 实施批）；P0-③ → ADR-089 §1/§8（编译移出 LLM + 迁移弧）；A-1 与 P0-② → 修复批（交接提示词已发，修后在本行标注日期+commit）；§7 read 洞 (d)(e) → 修复批 stretch；15E SSE 实流审计 → 独立取证动作待排。
> **修复登记（2026-09-22）**：A-1（程序盲改，§3.1）与 P0-②（specific_instruction 双哲学，§2）**已修**——branch `worktree-agent-tools-fix-0922`，commits `96b43fc`（perception 读族三补：get_node + get_pending_plan + list_runs）/ `2e04328`（specific_instruction distilled 合同对齐 + edit_graph 读全文 prompt 提示）；§7(d)/(e) 同族 read 洞随批落地。验证 = compileall + 纯 pytest 370 绿 + check_gates OK + prompt_gate minimax 三探针两轮 PASS；e2e 剧本未跑（需 dev worker，用户复跑）。**已落 main（merge `c8322fd`，同日）**——合并树独立复跑：compileall + 纯 pytest 370/370 + check_gates OK + prompt_gate 三探针第三轮 PASS（B 12/12、C 12/12，A 由退出码 0 证实）。
> 审计问题来自用户 2026-09-22 的整链走读报告（Agent Runtime → Tool Loop → Chat Tools → Perception → Application Command → Scope/Lifecycle → Run Birth）。
> 纪律：纯只读，零代码改动；证据 = file:line；verdict ∈ CONFIRMED / PARTIAL / REFUTED；不超限词——非本批 regression 不免责，已验证的才写。
> 取证分工：P0 三条 + scope/lifecycle + loop 单终态由主会话亲自核；工具面抽象层级、loop 机制细目各派一个只读子代理（报告已回收核对）。

---

## 0. 总结论

用户对骨架的判断与代码证据一致：**ToolLoop / Activity 分离 / 触发白名单 / 确认教义的服务端强制全部扎实，不建议推倒。**
P0 三条中两条代码级实锤（②①），一条（③ 工具抽象层级）属于产品层判断但证据支持其前提。

| # | 条目 | Verdict | 一句话 |
|---|---|---|---|
| P0-① | historical run ≠ confirmed scope | **CONFIRMED**（事实模型缺口，非代码 bug） | 批准出处字段不存在；信任根 = "曾出生且 context 带 tasks" |
| P0-② | specific_instruction 污染 | **CONFIRMED**（代码级） | chat 路 = 原始消息全文灌入；schema 根本没有 distilled 字段 |
| P0-③ | edit_graph/propose_tasks 抽象层级低 | **PARTIAL→见 §3**（子代理工具面证据） | 待补 |
| P1-④ | family_retry 比名字宽 | **CONFIRMED，但比用户描述的窄** | spec work-fields 全等才放行（见 §4） |
| P1-⑤ | bare prose fallback 过强 | **CONFIRMED（仅 prompt 管束）** | 代码地板只挡空散文，且 chat 路连空散文都不挡 |
| P2-⑥ | 单终态 = bounded proposal loop | **CONFIRMED（刻意设计）** | 一用户回合天花板 = [read]* → 一个 terminal |
| P2-⑦ | world model 靠 context 塞 | **PARTIAL** | build_context 其实是有界摘要（203 行）；缺口在 read 覆盖深度（§7 五洞） |
| A-1 | **程序盲改**：prompt 要求"从当前程序合成新程序"，context 却把程序截断 140 字 | **CONFIRMED（本审计新猎，用户清单外）** | 规则的前提条件在上下文里不可满足——见 §3.1 |

---

## 1. P0-① CONFIRMED — Approval provenance 不存在

**证据链**：

1. `app/pipeline/scope_classifier.py:365-389` `load_historical_chains()`：读项目**全部** `WorkflowRun.context`，凡 `tasks` 为非空 list 即收为 "confirmed chain"。docstring 自称 "Load every historical confirmed chain"，但**没有任何字段证明 confirmed**——它只是 "run 存在 + context 有 tasks"。
2. 全库无批准出处：`grep confirmed_at|confirmation_id|approved_at|approved_by|approval` 在 `models/tables.py` / `chat/service.py` **零命中**。Start 确认落 dock 后，持久化的事实只有 run 行本身。
3. D2 教义原文（DECISIONS.md:1931）："合法 retry 必须由服务端基于既有事实（**历史 run context** / approved scope / retry 引用）确定性证明"——**教义文本本身把 run.context 列为合法证明基材**，所以代码不违教义；缺口在教义的事实模型：证明基材自己不带批准戳。
4. 传递信任根分析：continuation run（分类器自治放行，**未经用户确认**）出生后同样写入 run.context → 成为未来 family/exact 证明的基材。逐链回溯，每条链的信任根只有两类：(a) Start 确认过的 dock（有确认事实，但没存下来）；(b) doctrine 落地前的 legacy run（从未有确认）。两者无法区分。

**边界（不超限词）**：family_retry 只能收敛不能扩张（子序列只会更短），所以该缺口**不会导致 scope 蠕变**；真实暴露面 = 信任根无法审计（哪个 run 是用户确认的、何时、哪条路径）+ legacy run 永远锚定家族树。dev 库旧项目已清（Greenfield 拍板），生产库若有 pre-doctrine run 则仍在基材集内。

**图侧同款近似**（用户 §9，CONFIRMED）：`scope_classifier.py:187` `approved = prior is not None and prior.state != "draft"` —— "run-born 图 = approved scope" 的近似，代码注释自承是近似（"Born draft by the door in this batch, or still an unconfirmed draft"）。delete_node+run 卡住的现象由此解释：删除饿死输入集 → `closure_inputs_reduced` → unproven → 回 dock（:211-212），机制按设计工作，缺的是 Approved Scope 的历史身份。

## 2. P0-② CONFIRMED — specific_instruction 双哲学，chat 路全文灌入

**证据链**：

1. **prompt 合同**：`app/prompts/chat/intent_router_system.j2:64` —— "specific_instruction: a short distilled EXTRA instruction … NEVER restate the requested work itself … Omit when nothing extra remains."
2. **plan 路合规**：`plan_turn.py:632/754` 用 `params.specific_instruction`（router 结构化输出的 distilled 字段，schema 定义 `models/schemas.py:1402`）。
3. **chat 路断线**：`ProposeTasksArgs`（`schemas.py:686-708`）**没有 specific_instruction 字段**——LLM 在 chat 路根本无法提交 distilled 值；`propose_turn.py:370` 直接 `specific_instruction=text or None`（`text` = 本轮用户原始消息全文）。
4. **caption 回放同哲学**：`service.py:1425-1434` 注释明言 "synthesize one from the prompt so the downstream text-tribe agents see the user's intent"——chat 路 stash 无字段时，用**首条用户消息**合成。
5. **消费端实锤**：Start 路径 `service.py:1600` `instruction=intent.specific_instruction or pending.prompt` → `TaskSpec.instruction` → `orchestrator.py:261/427` → `run.context["instruction"]` + 节点 `spec["instruction"]` → `agents/contexts.py:69` `GenerationContext.instruction` → writer 族（posts/quotes agents 注释 "persona + user instruction"）。

**判断**：不是粗心 bug，是**两种哲学并存**——schema/prompt 合同要 "distilled extras only"，chat 路（ADR-077 后唯一意图面的主力路径）选择 "原文即意图"。用户警告的风险真实存在：router 已把请求结构化吸收（默认值/语言/数量进 params），instruction 全文又把人名以外的所有暗示原样带下去——router 刻意排除的读法可能经 instruction 复活。修法不是"删原文"，是**两哲学对账成一个合同**（哪个字段承载什么，writers 信哪个）。

## 3. P0-③ 工具抽象层级 — CONFIRMED（前提层面）

工具面全景（`app/chat/intent.py` 两 agent + trigger；schema 即 wire——`tool_spec()` `tool_loop.py:106-121` 把 pydantic Field description 直接编进 provider 可见的 tool spec）：

**plan 路**（intent_router）：present_plan / ask_user / start_run / answer + 5 个 read。
**chat 路**（chat_intent）：propose_tasks / apply_edit_ops / edit_graph / ask_user / answer + 7 个 read。

**语言分层实测**（引原文）：
- ask_user / answer / start_run 与七个 read：**用户能力名词**（"Read one output's current state (caption style, music, aspect, the text body)"）。
- propose_tasks：**内部语言**——"Propose new work as a **task list** … never starts a **run**"（turn_tools.py:86-93）；task = `{tool: 注册表内部名, params}`（select_clips / translate_clip / dub_clip / write_post…），LLM 从 prompt 注入的注册表目录自行枚举编链，validate_task_list 事后裁决 + difflib 建议进修复 echo。
- apply_edit_ops：任务可懂、词汇内部——"**clip-spec-level operations**, in the **Operation Model vocabulary**"。
- edit_graph：**100% 系统内部语言**——"Revise the project's **persistent graph**（add_node / connect / edit_prompt / delete_node / run）… re-fills the affected **subgraph** … **docks**"（turn_tools.py:104-115）；ops = "Wiring ops in the registry vocabulary"。

**edit_graph 要求 LLM 具备的知识**（逐项实证）：裸节点 UUID；媒介五值类型词表；`spec.tool`+`spec.prompt` = 可执行身份（graph_revise.py:53-66）而目录**从未说明** spec.tool 必须是注册表工具名（坏值只在 run bridge 处迟发 ToolRejected）；typed edge（video/audio/text/ctx）+ offer/accept 端口语义 + 环拒收；run 闭包语义（{节点} ∪ 下游）。prompt 把教学收窄为 edit_prompt + bare run 两板斧（chat_intent_system.j2:29），但 schema 与目录暴露全部五 op。

**结论**：用户对 edit_graph / propose_tasks 的定性（"LLM = workflow compiler"，graph-surgery-by-LLM + apply_wiring_ops 裁决门）与证据一致。ask_user/answer/read 族已在能力语言层。**断开点在两个工作提案终态工具上**。

### 3.1 本审计新猎（A-1）：程序盲改 —— prompt 规则与上下文供给结构性矛盾

- 规则（chat_intent_system.j2:29）："compose the node's NEW full program from its CURRENT one plus the user's ask（**never invent a fresh program out of context**）"。
- 供给（context.py:116）：Graph 段每节点程序 `str(prompt)[:140]` —— **140 字截断**；全图 cap 16 节点。
- read 族无补洞工具：注册表无 get_node / get_program（perception/__init__.py:66-158 全目核实）。

后果：任何程序 >140 字的节点被修订时，LLM 要么违反"never invent"规则凭空补全，要么产出截断杂交版——**修订质量静默降级的结构性来源**，每次长程序修订必中。这是本次审计单条性价比最高的发现（一条 prompt 规则的前提条件在其上下文里不可满足）。

## 4. P1-④ family_retry — CONFIRMED，但有一道用户未提的窄化门

`scope_classifier.py:266-291`：exact_retry = 全链逐字相等；family_retry = 请求链是某条历史链的**非空有序子序列**（`_is_subsequence`，:294-299，允许跳过中间项——A→B→C→D 批准，A→C 命中）。

**用户描述漏掉的前置门**：`wanted_spec = _spec_projection(requested.spec)`，spec 投影（`SPEC_WORK_FIELDS` :243-263 —— target_language / instruction / tone_settings / persona_id / scope / operation / target_id / caption_mode / source/exemplar）**必须逐字段全等**才进入子序列比较。所以 "A→C 自动执行" 只在**同 instruction、同语言、同 persona** 下成立——换一句话问就落到 unproven → dock。

**仍然是产品语义问题**：用户的例子（B 是 C 的准备条件时 A→C 是否合法）classifier 确实不知道语义，只知 task equality + order + spec 全等。认定为**需要长期维护的 domain contract** 是准确的定性。

## 5. P1-⑤ bare prose fallback — CONFIRMED，且 chat 路连空散文地板都没有

子代理逐行核实：

- 地板位置：`tool_loop.py:481-493` —— 任一迭代零 tool call 即 `_finish(LoopResult(tool_name=None))`，**无论用户消息是提问还是工作请求**，代码无分支区分。
- 管束只有 prompt：`chat_intent_system.j2:55-56`（work request 禁止 answer / 歧义禁 answer）+ `turn_tools.py:126-133`（"answer is never the lazy out"）。
- 代码地板不对称：plan 路空散文 → `_cannot_do_text`（plan_turn.py:1004-1017）；**chat 路 bare reply 连空散文守卫都没有**（propose_turn.py:692-702，原文直写）。`answer` 工具本身两路都拒空散文——但那只管工具调用，不管 bare floor。
- 验收时的实发证据：本审计周期 v9 验收跑里，"给中文字幕视频版本加一段背景音乐"（明确工作请求）收到 bare answer "这个我现在还做不了"——正是 lazy-out 形态在野出现（虽然那次是能力误判，不是懒）。

## 6. P2-⑥ 单终态 — CONFIRMED，刻意设计，注释自证

- `tool_loop.py:494-503`：`call = result.tool_calls[0]`，多余调用 warning 丢弃，注释："parallel gate actions would fork the turn's writes"。纯测试锁：`test_tool_loop_pure.py:235-254` `test_extra_calls_never_execute`。
- 结构性天花板：terminal accept 即 return（:643-659）；terminal 返 observation / read 返 terminal 都 RuntimeError（:566-572 / :643-649）——**act→observe→act 在单个用户回合内结构性不可能**。
- 跨回合自治唯一通道 = trigger turn（白名单三 kind + 双重 is_pending_plan 静默，`trigger_turn.py:325-341` 准入 / `:404-421` 落点复评——B8 修复批 ② 机制在码）。
- 最接近多步的合法形态：单 terminal execute 内的复合写（`_edit_graph` CONTINUATION = apply_wiring_ops + create_run 一个 savepoint；`_start_run` = answer + create_run）——一次调用多次写、中间零观察。

**定性**：当前 = **bounded proposal loop** 是准确描述。要长成 "read→act→inspect→revise→verify" 的自治 agent，需要的是 terminal observation 通道——这是 ADR 级决策，不是工具数问题（支持用户 §14 "不要再加工具"）。

## 7. P2-⑦ world model — PARTIAL

`chat/context.py`（203 行单函数 `build_context`）：项目行 + 资产（id/status/language）+ 可见产物（id + 一句话）+ 图节点（id/state/label/program 前 140 字/产物数，cap 截断）+ 最近 3 轮 + mentions + pending。**不是巨型 context 倾倒，是有界确定性摘要**——用户 §10 的 "巨大 context assembly" 描述与实际不符。

真实缺口 = read 族覆盖深度（五个可证洞，全部从工具清单 + context 装配实证，零推测）：

a. **无项目级 "产物 + 当前 spec/状态" 单读**——context 只给 `- {type} id={id}: {一句话}`（context.py:74-79），详情须逐产物 get_output_spec。
b. **无两产物对比读**（两次顺序 get_output_spec 机制上可行，无一-shot 对比）。
c. **无节点完整程序读**——即 A-1 的洞（140 字截断 vs 全文合成规则）。
d. **chat 路无当前草稿计划读**——plan 路在 context 里拿到 docked plan 的 JSON 链（plan_turn.py:343-349），chat 路只有 Graph 段。
e. **无 run 历史读**——get_run_status 只读最新 run（executes.py:332-339）。

## 8. 用户 15 问速答（已取证部分）

| 问 | 答（证据） |
|---|---|
| 3. Agent→Tool→Command 边界 | 扎实：ADR-087 §6 依赖方向刚收口（pipeline↛chat 探针五牙，`test_import_direction_pure.py`）；terminal execute 是唯一写座，loop 本体零 DB（tool_loop.py 无 sqlalchemy import 实证） |
| 4. Read-before-write | 成立：perception 族 terminal=False + observation 回灌（:642）+ 拒收重试不重复 read（:423-427 注释） |
| 5. Multi-step autonomy | 结构性缺席（§6 节）；跨回合自治 = trigger turn 白名单 |
| 6. Tool failure/repair | 四种拒收同类 `_loop_echo` 回灌 user 消息（:150-159）；bound=6（intent/chat/trigger 三 agent 声明），耗尽 → cannot_do / trigger 静默；**read 也耗迭代**（all-reads 回合可耗尽，纯测试锁） |
| 8. 用户可见行为 | 打字机律双牙在码（散文字段读容忍 + paceSettledProse 闸门）；thinking 相位帧三拍 |
| 9. Activity projection | LoopEvent 四冻结 dataclass 联合（tool_loop.py:191-228），loop 永不引用 Activity 词汇（模块注释 :180-188 自证 + 单向 import 实证），投影器 `chat/activity.py` 纯状态机零 DB |
| 10. Canvas handoff | 本次 Greenfield 验收 30/30 实证（draft 图→live 图 rank 稳定、modifier 读面隐藏、相机律） |
| 11. Confirmation UX | dock pill 唯一座位（Phase 3 判词 1）+ Start 服务端四合取强制（B6 `evaluate_start_gate` 五机器可读码） |
| 15E. CoT 泄露 | wire 合同注释在码：`chatStreamFrames.ts:20` / `ActivityStream.tsx:12`（"never carries reasoning"）；**未做 SSE 实流审计**——建议列为单独动作 |

## 9. 修法选项备料（不动工，仅备决策）

- **P0-① 批准出处**：(a) run.context 加 `confirmed_via`/`confirmed_at` 戳（Start 座写入，legacy 行 NULL=不可证）；(b) scope 证明基材从 run 行改为独立 approval 记录；(c) 维持现状 + 文档写明"信任根不可审计"为已知边界。
- **P0-② 双哲学对账**：(a) ProposeTasksArgs 加 specific_instruction 字段走 distilled 合同（prompt 面改动 → prompt_gate 门禁）；(b) 维持全文灌入、改写 j2:64 合同向代码低头；(c) distilled + 原文双字段并行（writers 信 distilled，原文只作 fallback）。
- **A-1 程序盲改**：(a) perception 加 `get_node`/`get_program` read（零 prompt 面改动，最稳）；(b) Graph 段对 edit_graph 目标节点全量放行（需要先看目标——鸡生蛋）；(c) 提 140 上限（治标，长程序仍截）。
- **P0-③ 能力动词层**：revise_output / create_variant 类能力动词 → 编译为现有 ops 的中间层；属 ADR 级决策，与 C-3/D 联动倒推。
- **15E SSE 实流 CoT 审计**：独立动作，需抓真流。

## 10. 审计方法附录

- 主会话亲核：P0-①（provenance 零命中 + 信任根传递分析）、P0-②（五环节全链）、§4 spec 窄化门、§6 单终态（tool_loop.py:494-503 + 纯测试锁）、A-1 复核（context.py:116 + j2:29 对照原文）、build_context 全文。
- 子代理①（工具面）：六问全答 + 双通道示例（schema→wire→prompt 三处同词）；引用均已抽查。
- 子代理②（loop 机制）：五 claim 全 CONFIRMED + 附加两问（answer 终态形态；多步自治结构性缺席）；拒收 echo 回灌 user 消息形态、bare floor 双路不对称、read 耗迭代三处为报告新增细节。
- 未覆盖：SSE 实流抓包（15E 完整版）；web 端组件级走查；生产库 legacy run 清点（P0-① 暴露面定量）。
