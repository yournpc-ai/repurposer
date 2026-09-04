# Repurposer Dialog Workflow — 厚 Agent 蓝图

> Status: 已拍板（2026-09-03，ADR-052），**B1~B4 代码全落（2026-09-03）**——B1 改名批 / B2 brief 账本+ask+出书门槛 / B3 预填评审卡 / B4 有界 loop 节点+research 试点；剧本测试（S50~S53）与产品试用验证归用户（简报 `docs/tasks/dialog-workflow-b*.md`）。
> 本文是「对话→生产」全链路的**概念架构母文档**：一个产品级厚 agent，身体是一条 workflow。工程实现地图（Model / Harness / Graph / Loop 四层）归 `AGENT_ARCHITECTURE.md`；chat 机器规格归 `CHAT_ARCHITECTURE.md`；命名判例归 `NAMING.md`（N-43 起）；任务书字段契约归 ADR-043。

## 1. 蓝图一句话

**整个用户对话就是一条 workflow**：聊天 → 意图路由（router）→ 任务分配（brief 账本 → 任务书）→ 生产 DAG（understand → plan → 执行器群 → verify）→ 产出结果，workflow 结束。

对用户，这是**一个「厚」agent**（assistant，单身份，NAMING N-25 双轨不变）；对实现，这全是 workflow——**agent 性在产品承诺层，实现层没有一个 autonomy 义的 agent**（判词见 §2.1）。各环节需要"角色"处理的事，由**带工具的节点**完成；角色是节点的展示属性，不是节点的名字（§2.5）。

## 2. 概念模型（六个概念，没有第七个）

### 2.1 厚 agent（thick agent）

产品 = 一个厚 agent。它的"厚"不来自自主循环，来自**声明式部件的组合厚度**：Agent 调用漏斗（harness）× NodeBase 节点协议 × compile_graph 编译器 × app/tools 能力注册表 × brief 账本 × 提问机器——基类全部已在仓库里。

**判词（ADR-039 补记）**：按业界定义（Anthropic《Building effective agents》：workflow = 预定义代码路径编排 LLM；agent = LLM 在循环里自主指挥自己），本系统**零 agent、全 workflow**——chat 边缘是 routing 模式，pipeline 是 orchestrator-workers 模式。这是设计，不是缺口：开放式 autonomy 永拒（常备否决清单），"LLM proposes, code decides" 就是 workflow 哲学的别名。对外文案的 agent/assistant 指产品承诺层，不指任何内部模块。

### 2.2 双引擎 workflow（概念统一，引擎分离）

| | 对话引擎 | 生产引擎 |
|---|---|---|
| 本质 | **事件驱动状态机**（router + brief 账本 + 提问机器） | **编译 DAG**（compile_graph → workflow_steps） |
| 步数 | 开放（人决定何时说完） | 编译期封闭（拓扑可排） |
| 环境 | 人（每轮等待输入） | 队列（worker 认领执行） |
| 保证 | 单待决问题 / brief 合并优先级 | 报价=fold / 执行=topo / 占位 roster 编译期投影 |

**对话永不编译进 DAG**：DAG 的三大编译期保证对开放对话不成立（轮数未知、环境是人、报价无意义）。两引擎的唯一接口 = **任务书**（对话引擎的产出 = 生产引擎的输入，出生地唯一——`answer_question` kind=start，ADR-043 不变）。

### 2.3 router（意图路由）

chat 边缘的两个结构化调用（原 `plan_agent` / `chat_intent_agent`）是**同一个概念**：意图路由器，两个相位 prompt（pre-run / post-run——相位是上下文参数，不是两个概念）。业界对位：Anthropic routing 模式 / OpenAI SDK triage / AI SDK `generateObject`。**ask 形状两相位共享**——「pre-run 不能提问」的不对称（东施效颦事件的结构性根因之一）在概念层根除。

### 2.4 brief 账本（对话状态）

对话引擎的结构化状态，持久化于 `projects.pending_brief`（原 `pending_intent` 更名）：

- **槽位**（初版）：`topic` / `audience` / `tone` / `constraints[]` / `material_state`（none | pasted | attached）+ 任务链与 derived（原样保留）。
- **每槽带来源**：`user-stated` / `inferred` / `default`。合并是代码的事：**user-stated > inferred > default**（LLM proposes, code decides 不变——LLM 每轮提议更新，代码按来源优先级合并，永不反向覆盖）。
- **上下文工程的主压缩件**：账本存在后，累积 prompt 叙事退居存档位，recent 窗口保留——账本比任何 message window 便宜且抗遗忘。

### 2.5 角色 = 节点的 display 属性

工作流内部**永远函数名**（`select_clips` / `dub_clip` / `write_post`——动词族零人格）；用户可见的**进行态叙事**是节点声明上的可选展示属性（`task_name` 机制的升级位）：「正在剪辑成片…」「正在制作配乐…」渲染在打勾流 shimmer 行 / 占位卡 / 画布节点。

**叙事写工艺不写人**（2026-09-03 用户拍板发稿）：「正在剪辑成片…」✓，「剪辑师正在…」✗——assistant 单身份不破（N-24 的禁令对象是 assistant 的班子包装，步骤级工艺叙事是另一层；**人形叙事 = 明确翻 N-24 的案**，门槛维持）。

### 2.6 有界 loop 节点（agent 性的合法座位）

产品需求里出现编译期排不出拓扑的活（搜索、阅读、步数不可预知）。业界标准答案 = **workflow 做脊柱，agent 做脊柱上的有界节点**（LangGraph 嵌 subgraph / Mastra step 内跑 agent / Anthropic agentic component）。落地 = `NodeBase` 新子类，内部跑 mini tool-loop（工具 = `app/tools/` 现成注册表），**三条硬护栏**：

1. **迭代上限**（如 8 轮，节点声明）
2. **报价 = fold**（上限 × 单次报价——估价体系不破）
3. **对外 = DAG 里的一个节点**（拓扑 / 占位 roster / SSE / 诞生编排全部无感）

首个试点 = **research 节点**（产出 research brief artifact 喂 writer；2026-09-03 拍板「立即」——B4 随本批，PROGRESS W7 09-09~09-10）。开放式 autonomy（无界循环 / 自主改拓扑 / 自我 steering）维持永拒——常备否决清单只收编有界形态。

## 3. 词汇表（canonical，零自造词）

| 我们的部件 | canonical 词 | 业界出处 |
|---|---|---|
| chat 边缘意图调用 | **router**（intent router） | Anthropic routing 模式；OpenAI SDK triage；AI SDK generateObject |
| 原 `director_plan` | **`plan`**（planner 的动词形） | Plan-and-Execute 正典模式（LangGraph 官方模板） |
| 原 `director_understand` | **`understand`** | 结构化抽取 pass（extractor/comprehension 的动词形） |
| 图执行单位 | **node / step** | LangGraph node / Mastra step / AI SDK workflow step |
| `Agent` 类原语 | 声明式结构化调用 | = AI SDK `generateObject`；ADR-039 判词补记，类名不动 |
| 对话状态 | **brief**（账本） | 对话系统 frame / slot-filling 的 frame |
| 嵌套自主性 | **有界 loop 节点** | LangGraph subgraph / Mastra agent-in-step / Anthropic agentic component |

**改名批**（判例归 NAMING.md N-43 起，commit 级自绿）：`plan_agent → intent_router`（相位参数化）/ `chat_intent_agent → intent_router`（同概念）/ `director_understand → understand` / `director_plan → plan`（**plan 一词归一主**——pipeline 唯一规划节点；chat 侧只叫 book/brief）/ `pending_intent → pending_brief` / plan path → book path / presented_plan → presented_book / plan_summary → book_summary。工具侧 `*_writer` / `translator` / `verify_judge` 不动（本来就是诚实角色名）。

## 4. 对话工作流（P0：brief 账本 + ask 一等动作）

### 4.1 ask 升格为一等动作

router 动作集（pre-run 相位）：**ask / draft / answer / start**（原 generate/answer/start 修订——generate 名不副实，它从不生成，只是起草/修订任务书）。ask 复用 chat_intent agent shape C 的形状（选项 3 项——真二元抉择降 2，2026-09-04 拍板——+ freeform，走现成 dock 提问机器——caption-mode 特例泛化为正典）。

**提问策略三条**：
1. **一轮最多一问，只问决定质量的那个缺失槽**（裸愿望无素材 → 第一问 = 主题/受众）
2. **选项一词可答**（具体值，来源 = persona / 项目上下文），freeform 恒在
3. **散文必带默认路径**（"不答我就按你的人设风格起草"）——每个问题都可安全跳过，不知所措在原理层消除

「诊断一轮封顶」翻案为「**每轮一问、每问可一词答**」——顾问姿态的本义是不让用户做创作题，不是不问（证据：Opus sequential singles 走查）。

### 4.2 出书门槛

任务书只在 brief **有根**时 dock：主题 / 素材 / 明确配方，三者有其一。零根裸愿望永远先走 ask；问完一轮仍无主题 → 出 draft-from-persona 书 + 散文带默认路径声明（"直接开始我会按人设风格起草，你也可以先告诉我主题"）。原 zero-material safety net / no-material lift 两张补丁**折叠进这同一策略**——出书决策只看账本，不看临时网。

### 4.3 上下文装配

router 每轮输入 = brief 账本（主状态）+ presented book（chain JSON，修订时）+ recent 消息窗口 + 素材摘要（800 字，现状不变）。累积 prompt 叙事降为存档（head/tail 截断簿记退役）。

## 5. 任务书卡 = brief 的渲染（P1：预填评审卡）

**东施效颦的正解**（证据走查 2026-09-02，Opus 对照）：Opus 的卡是对话的**终点**（已填账本的渲染，用户做识别题），我们的卡曾是对话的**起点**（空账本表格，用户做创作题）。修订解剖：

- **卡顶 = brief 槽位渲染**（About / For / Tone / Material——有值显示，inferred 值可点改，无值不显示；零空框）
- **任务行保留**（链 = 要确认的东西，现状解剖不变）
- **两个空文本框全删**（per-row focus + run 级 instruction——修订全部走「点值改 / 聊天改」；chat 修订恒胜不变）
- **确认 pill 按动作命名**（"Save & generate" / 「保存并开始」），散文第二句恒为默认路径声明（≤2 句拍板不变——本条给它 schema 级牙齿）
- **默认路径必声明**（Opus "I'll use my best judgment if you step away" 同义）——「不填会怎样」永远有答案
- **密度律（ADR-054，2026-09-04 拍板）**：卡 + 确认 pill 只在 **chain ≥2 任务**（有评审实质）时出现；**单任务书 = 纯散文确认**（无卡无 pill，确认 = 下一条 chat 的 start 裁决）——识别题为零时连卡都不展开，散文牙齿升格为全部确认 UI

## 6. 不变量（本蓝图不动的部分）

四层工程地图（AGENT_ARCHITECTURE）/ LLM proposes, code decides / 报价=fold、执行=topo、校验=∀、对账=⊆ / chat 唯一意图面（POST /chat）/ 单 LLM 边界（MiniMaxClient）/ 禁 ReAct 开放式 autonomy / 占位 roster 编译期投影（ADR-051）/ clip-spec 唯一渲染契约（ADR-016）/ 提问机器与停靠法则（CHAT_ARCH §8.5）/ **形态律**（文字问 = 普通对话消息、输入恒活；选项问 = 阻塞形态——待决时输入行与免责行让位给问题卡，铅笔行 = 自由输入通道，ADR-053 R1）/ **插话支持**（判定是 LLM 的、结算是代码的——slot 握手 / pending_disposition；插话回合回复接代码拼装提醒尾，ADR-053 R2）/ **任务书密度律**（评审卡 + 确认 pill 归 ≥2 任务，单任务书 = 纯散文确认，ADR-054）。

## 7. 落地切分（批次，各自 commit 级自绿）

| 批 | 内容 | 验收 |
|---|---|---|
| **B1 改名批** ✅（2026-09-03） | §3 全栈改名（实例/字段/路径/文档）；NAMING N-43+ 判例同批 | 每 commit 冷启动绿（tsc + import + 引导一处真实路径）；零行为变化 |
| **B2 P0** ✅ 代码已落（2026-09-03，验证归用户产品试用） | brief 账本（schema + 迁移 + 合并规则）/ router 相位统一 + ask 动作 / 出书门槛 / 默认路径声明 | 裸愿望 "I want a social post." → 先收到一词可答的主题问（带默认路径），不再收到空心书 |
| **B3 P1** ✅ 代码已落（2026-09-03，同上） | 任务书卡 = brief 渲染（槽位行 + 空框全删 + 确认 pill 改名 + 散文牙齿） | 卡面零空文本框；每个值有来源；不填任何东⻄直接 Start 的路径在卡上可读 |
| **B4 research 试点** ✅ 代码已落（2026-09-03，同上） | 有界 loop 节点类型 + research 节点（工具：web search/fetch） | 三护栏成立；DAG/报价/占位无感；writer 收到 research brief |

B1→B2→B3 顺序强依赖；B4 独立（2026-09-03 拍板「立即」——排期随批 09-09~09-10）。每批施工简报开做前落 `docs/tasks/`（flora-parity 先例）。B2~B4 三批代码同日落地（简报 `tasks/dialog-workflow-b*.md`），剧本测试 与产品试用验证归用户。

## 8. 悬案（待真实数据 / 后续拍板）

1. **槽位优先级参数**：「问哪个槽」的顺序与「几轮问完出书」的阈值，初版按 §4.1 三条策略，真实对话数据回来再调。

> 已关闭（2026-09-03 拍板）：research 试点排期（「立即」——B4 随批，PROGRESS W7）；人形叙事一判（工艺叙事发稿，人形 = 翻 N-24 维持门槛）；**router 两相位物理形态（案 A 双实例保持）**——`intent_router` + `chat_intent_agent` 各自声明，概念合一由本节与共享 `QuestionProposal` schema 承载：两声明的 schema / assemble / 动作集 / prompt 主体本就不共享，单实例相位参数化要以联合 schema（非法动作变可表示）+ assemble 纯度签名腐蚀 + `StreamingAgent` 漏斗手术为代价，且是未来唯一用户的 bespoke 机制；双实例下 prompt 迭代面物理隔离、第三件走「再声明一个实例」正典，A→B 可逆 B→A 贵。
