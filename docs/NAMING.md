# NAMING — 命名宪法与判例库

> Status: Active（2026-07-25 建立）
> 适用范围：模块 / 包 / 表 / 字段 / API / skill / 事件——一切会被别人读到的名字。
> 用法：命名争议不复述本文论证，引用条目号（`NAMING §3`）或判例号（`N-04`）。新判例只追加。

## 1. 八条宪法

1. **一个概念一个名字，全栈统一**。同一个东西在表、字段、API、模块、前端词汇里必须同名。改概念 = 全库改名，不留旧词过桥层。
2. **包/模块用单词名词，函数用动词，枚举值用形容词/名词**。`chat/`、`pipeline/`、`compile_graph()`、`behavior: "deterministic"`。
3. **禁用后缀黑名单**：`*_manager` / `*_engine` / `*_helper` / `*_utils` / `*_handler`。这类后缀意味着职责没想清楚——它该是现有包里的一个函数，或者职责值得一个真正的名词。例外：计算机科学既定名词（`compiler`、`scheduler`、`worker`）。
4. **布尔语义优先可空时间戳 / 可空枚举**。`pinned_at` 优于 `is_pinned`（白得审计信息）；`render_status NULL = 未请求`（NULL 本身做认领谓词，省一个布尔列）。
5. **枚举 = String 列 + 应用层注册表校验**（ADR-028 D6 先例）。新类型零表迁移；注册表是唯一守门人，DB 不重复约束。
6. **行话黑名单：编译器 / 框架黑话不进业务词汇**。团队通用词优先；一个词需要解释才能懂，就换一个不用解释的。
7. **分组准入测试**：新模块 / 新目录必须拥有**独立的表归属**或**独立的队列认领源**，否则它只是现有模块的职责扩充，不配开包。
8. **准入即登记**：新名词通过评审后必须进 §2 词汇表（中英映射唯一）；新判例进 §3。词汇表是冻结资产，改词 = 改文档 + 全库改名。

## 2. 领域词汇表（中英映射唯一，冻结）

| 中文（文档） | 英文（代码） | 定义 | 不是什么 |
|---|---|---|---|
| 任务书 | `TaskSpec` | 意图归一：outputs × 语言 × 数量 × instruction | 不是 plan、不是 workflow |
| 任务列表 | task list / `TaskItem` | intent agent 的轮内提议（skill + params），compile_graph 模式②的输入 | 不是 plan、不是 node spec |
| 施工图 | RunPlan / `workflow_steps` | **执行计划**+账簿一体的 DAG 内核（谁干什么、什么顺序、花多少） | 不是 DAG 画布（用户不见图） |
| 步骤 | `WorkflowStep` | 施工图上的一个执行单位（曾名 PlanNode，N-15） | 不是 job、不是 task |
| 对话 | `Conversation` | chat 的会话容器（曾名 ChatSession，N-12；session 撞 auth session） | 不是 thread、不是 session |
| 内容计划 | `ContentPlan` | **已退役（N-17，2026-07-27）**：拆分为素材理解 + 分镜表 | 不是 brief（brief 是输入，TaskSpec 才是） |
| 素材理解 | `MaterialUnderstanding` / type `material_understanding` | 导演第一步产出：素材级理解（论点带位置/金句/主题/受众），asset-hash 复用 | 不含任务信息；不是 ContentPlan 改名 |
| 分镜表 | `Storyboard` / type `storyboard` | 导演第二步产出：请求级派工（槽位+覆盖报告），每 run 重排 | 不是 task board（撞任务书词族）；不读原稿 |
| 槽位 | `StoryboardSlot` | 分镜表一行：一个产物的 what（论点/角度/语言/格式） | how 归 executor |
| 覆盖报告 | `CoverageReport` | 论点→槽位映射 + 未用/撞车，代码推导落库 | 不是门禁（门禁归 Phase 3 质检节点） |
| 班组 | skills | LLM 决策单元（`skills/`） | 不是 agent 框架的 agent |
| 机械 | tools | 确定性执行单元（`tools/`），无 LLM 决策 | 不是 service、不是 util |
| 质检 | verify（节点 kind） | 单产物/全片质量校验节点（Phase 3） | 不是 eval（eval 是活动，verify 是节点） |
| 产物 | `outputs` | 统一产物表；clip 是 type 之一 | 不是 clips/derivatives（已退役） |
| 导演 | director | 素材理解 + 分镜表的产出者（两步走，N-17） | — |
| 精修 | refine | Edit / Chat / Regenerate 三角的统称 | — |
| 提及 | mention | 对话中的 @ 实体引用 | 不是 reference、不是 entity |
| 施工图编译 | `compile_graph()` | 任务书 → 节点图的纯函数 | 曾名 `lower_plan`（N-04）/ `compile_plan`（N-08）；裸 plan 违规（N-11），故以产出物命名 |
| 操作 | `Operation` | 产物级编辑动作的记录（op + params + spec_after 快照），operations 表 | 不是 plan 级节点操作（归 RunPlan 小拓扑） |
| 操作源 | `source` | operation 的发起来源：editor / chat / mcp / system（注册表） | — |
| 结果卡 | `RunCard` | assistant 消息内嵌的 run 线性投影（步骤清单 + 产物卡片 + 聚合行） | 不是 DAG 画布 |
| 操作卡 | `OpsCard` | assistant 消息内嵌的 edit ops 应用结果（op 清单 + 撤销） | — |

**plan 词汇现状**：RunPlan = 执行计划（工程层）是唯一在用的 plan；创作层自 N-17 起是**素材理解 + 分镜表**（理解/派工，不再是 plan）。plan 是合法词，但必须带限定词——裸 plan（`lower_plan`/`compile_plan`）歧义，见 N-11。

## 3. 判例库（只追加）

| # | 判例 | 裁决 | 依据 |
|---|---|---|---|
| N-01 | `outputs` 统一产物表 | clips/derivatives 词汇全库清除，`type` 区分产物种类 | §1 |
| N-02 | `render_status NULL = 未请求` | 不加 `render_requested` 布尔列；NULL 做认领谓词 | §4 |
| N-03 | `PlanNodeKind`（现名 `StepKind`，N-15）用 String 列 + Literal/注册表 | 不做 PG ENUM；新 kind（`voice_gen`/`synth_visual`）零迁移注册 | §5 |
| N-04 | `lower_plan` → `compile_plan` | lowering 是编译器黑话；compile 是通用词，且与"DAG 编译期校验"既有说法衔接 | §6 |
| N-05 | 否决 `ai/` 顶层目录 | 不拥有表、不认领队列、不对应部署单元——按技术风味分组 = `services/` 错误的高配版 | §7 |
| N-06 | 六模块包 + routes 入住模块 | `routers/` 平顶解散，模块自包含（routes + service + 逻辑）；skills/tools 永无 routes | §7 |
| N-07 | `services/` 目录废除 | 18 文件混四个架构层；按层分家（pipeline/chat/skills/tools/memory/platform） | §1、§7 |
| N-08 | `compile_plan` → `compile_graph`（翻案 N-04） | 裸 plan 歧义（编译的是哪个 plan？）；以产出物命名 | §1 |
| N-09 | ~~`ContentPlan` → `ContentBrief`~~ | **误判，被 N-11 翻案**：brief 是输入规格（那是 TaskSpec），ContentPlan 是导演的决策产物，语义上就是 plan | — |
| N-10 | ~~RunPlan → run graph；plan_nodes → run_nodes~~ | **过度清洗，被 N-11 翻案** | — |
| N-11 | plan 词汇恢复：**plan 必须带限定词，裸用违规** | 系统有两个 plan 各司其职：RunPlan（执行计划，工程层）/ ContentPlan（内容计划，创作层）——"LLM 提出 plan、executors 执行 plan"是 agent 范式的正名；违规的只是裸 plan（`lower_plan`/`compile_plan`，哪个 plan？）。`compile_graph` 保留（N-08 成立）；表名/类名/kind/type 全部回滚（迁移 b2d6f9a53e18） | §1 |
| N-12 | `chat_sessions` → `conversations` | session 撞 auth session；OpenAI Conversations API 同款；`messages.session_id→conversation_id`、端点 `/chat/session→/chat/conversation` | §1 |
| N-13 | API 层 job 词汇清除 | `/jobs→/runs`、`job_id→run_id`、`latest_job→latest_run`、`WorkflowRunResponse→RunResponse`：job 在 API 指 run，违反 v2.0"run 不是 job"与 N-11 双重原则（GitHub `actions/runs` 先例）。`workflow_runs` 表与 `WorkflowRun` 类**保留**（Mastra `workflow.createRun()`/GitHub 证明 workflow run 是行业标准执行实例全名；每 run 自带其编译出的 workflow=steps 图——改名动议记录在案并**撤回**） | §1 |
| N-14 | `ChatIntent` 退役 → `IntentProposal` 二态判别联合 | 规则版 action 枚举整体退役；`TaskListProposal`/`EditOpsProposal` 判别联合，`tasks=[]` = 反问（合法输出，不加第三态） | §1 |
| N-15 | `plan_nodes` → `workflow_steps` | plan 一词三用（RunPlan/ContentPlan/plan_nodes）真实歧义；表对词族统一（workflow_runs+workflow_steps）；前端早已叫 step（GenerationStepper/results.stepper.*）；Mastra workflow steps 同构。**概念层 RunPlan 不动**——这不是 N-10 翻案（N-10 否的是概念层清洗），是存储层对齐行业词；`outputs.plan_node_id→workflow_step_id`、`PlanNode→WorkflowStep`、`StepKind/StepStatus/StepResponse`（迁移 c4a9e2f17b03） | §1 |
| N-16 | `restore_range` 独立 op 否决 | removeRange 在 spec 内真删 caption cues，独立"恢复删除"op 只能 un-hide segments、复活不了字幕——恢复出来的产物是坏的；恢复语义全归快照层（undo / restore_version，ADR-032 D1/D4）；真要做点选恢复，前置 = clip-spec 契约扩展（cues 加 hidden），属 ADR-016 级改动单独评审 | §1、ADR-032 D4 |
| N-17 | ContentPlan 拆分：素材理解 `MaterialUnderstanding` + 分镜表 `Storyboard`；DerivativePlan 退役为槽位 `StoryboardSlot` | 导演两步走落地（`docs/tasks/director-two-step.md`）：理解=素材级（asset-hash 复用），分镜=请求级（每 run 重排）。否决 `TaskBoard`（撞 TaskSpec/TaskItem 词族，N-11 同型三撞）与 ContentPlan 沿用（理解是描述不是计划，沿用旧名不诚实）。"两个 plan 各司其职"注记改写：RunPlan 成唯一 plan | §1、§6 |

## 4. API 命名

- REST，复数资源，动作用子路径：`POST /outputs/{id}/render`、`POST /outputs/{id}/dub`。
- 不为单个动作造 RPC 式端点（`/api/sendChat` 此类永不出现）。
- 内部类型（如 `material_understanding` / `storyboard`）不得从任何公开响应漏出——统一经 `visible_outputs()` 过滤（ADR-030 D1）。

## 5. 命名审计触发点

以下情况必须做命名审计并在任务简报中列出结论：

- 新模块 / 新表 / 新 skill 准入（§7、§8）；
- 大规模重构（判例 N-06 的重构简报附带全库审计）；
- 发现同名不同物（如 `routers/intent.py` vs `agents/intent.py`）或同物不同名（如 `music.py` / `music_generation.py` 的职责切分）。
