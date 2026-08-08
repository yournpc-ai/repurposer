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
| 提问 | `ask` | 提议态：IntentProposal 第三态（结构化提问，N-18；期 3 已落代码） | 不是 question——question 是落库态 |
| 问题 | `question` | 落库态：messages.question JSONB（kind: task_book/choice/confirm + options/allow_freeform/cost_hint）；待决只在 dock，已决 QA 入档 | 不进消息流渲染 |
| 回答 | `answer` | 一词两态同域：① 落库态 messages.answer JSONB（kind: option/freeform/bail/start + answered_at）——**用户**答复待决问题，NULL = 待决，answer 端点即恢复；② 提议态 `AnswerProposal`（IntentProposal 第四态，N-21）——**系统**对信息类提问的直答，落库为普通 assistant 消息 content（B1 同款），**不进 messages.answer** | — |
| 弃做 | `bail` | 优雅退出一等公民：入口回 draft / checkpoint 下游级联 skipped；永不标 failed | 不是 cancel（cancel 是 UI 按钮词） |
| 自治档 | `autonomy` | `TaskSpec.autonomy: auto\|review`，随 run.context 落库；review 档 full run 插方向 checkpoint（期 4 已落代码） | 不是 mode（撞太多） |
| 任务槽 | `IntentSlot` | 任务书一行 = 一个产物的请求（type/count/focus/language/tone_override/explicit）；请求层（期 2 已落代码） | **不是分镜槽位** `StoryboardSlot`（派工层，N-20） |
| 挂起 | `Suspend` | 挂起异常：checkpoint 瘦节点转 `waiting` 的机制（期 4 已落代码）；状态词从机制动词派生 | 不是 paused——启用已有 waiting 座位 |
| 检查点 | `checkpoint` | 节点 kind：提问-等待-续跑的瘦节点（期 4 已落代码；`spec.for` 住用途） | 不进 SKILL_REGISTRY |
| 配方卡 | `RecipeCard` | 首页能力演示卡：承诺 + 输入槽位 + slots prior + preview（RECIPES §7） | 不是模板市场、不是内容流 |
| 配音语言集 | `dub_languages` | 任务书级字段：本 run 的配音语言清单（空列表 = 无配音，§4 不加布尔） | 不是 IntentSlot 字段（dub 是跨产物修饰，非产物类型） |
| 派生 | `fork` | dub 节点的用途标记（`spec.fork`）：新建派生产物行而非原地改写 render_spec | 机制词仍 dub（N-19 用途住 payload）；不是 git fork |
| 派生来源 | `derived_from_output_id` | 派生行 `source_ref` 内的溯源指针（住 JSONB） | 不新建表列 |
| 字幕样式目录 | `CAPTION_PRESETS` | 字幕样式注册表（packages/clip）：preset id → 原语组合；TS 类型由它推导，Python 只校验成员 | 不是自由样式（preset 枚举纪律不变） |
| 布局 / 进场 / 词级高亮 | `layout` / `entrance` / `wordHighlight` | 字幕样式三原语：single\|stack × none\|fade-in\|pop-in\|slide-up × bool | — |
| 堆叠 | `stacking` | catalog 成员：新行淡入、旧行驻留、超 maxLines 滑动窗口 | — |
| 工作室 | `studio` | 登录后应用区（landing 之外的 sidebar 世界）的统称：home composer、projects、editor；用户文案（`openStudio`、"欢迎来到你的工作室"）与内部文档同词。**只是空间名**，品类自称永远是 agent（N-23） | 不是 workbench/工作台（已退役，N-22）；不是品类词 |
| 助手 | `assistant` | 对外文案的自称（N-25 双轨：对内技术 = agent）；zh 优先用代词"它" | 不是 agent（agent 只对内）；不是运营官（已退役，N-24） |
| 任务书构建 agent | `PlanAgent` | chat plan path 的推理者：free-form 文本 → 任务书推断（三动作 generate/answer/start；曾名 `ComposerIntentAgent`，2026-08-04 单面化更名内化） | 不是第二意图入口——入口只有 `/chat` |
| plan 路径 | `plan path` | chat service 内分派分支：首次 / 待决任务书的项目级回合 → 任务书构建/修订/确认（`chat()` 状态分派，asset scope 永不进） | 不是相位（confirm 相位已降为"有 pending task_book"的普通 chat 状态） |
| 剧本验收 | `chat_scenarios.py` | 意图层验收 harness：预设多轮剧本对活 API 跑形态级断言（S1–S8），真实 LLM 不锁文案 | 不是测试套件（无测试套件纪律不变） |
| 能力层 | capability layer | 编辑能力的唯一事实层（ADR-033）：`OP_REGISTRY`（参数级微操作）∪ `SKILL_REGISTRY`（任务级宏操作），双注册表双海拔 | 不适配器私设能力 |
| 适配层 | adapter | 能力层之上的薄转换：chat / editor /（预留）mcp——只做"输入形式 → 注册表调用"的翻译 | 不含编辑逻辑；不是新能力来源 |
| 瞬时节点错误 | `TransientNodeError` | step 级重试的判定类型（`app/pipeline/errors.py`，agent-loop-upgrade W3）：provider/网络/存储瞬时故障；`execute_step` 按 `SkillEntry.retries` 预算复位 pending | 不是确定性失败的通行证——缺失输入/空批次必须普通异常快速失败 |
| 去口头禅 | `remove_filler` | skill 与 op 同名同义（跨注册表对齐 §1，agent-loop-upgrade W4）：skill = 确定性 modifier（task_list 派发）；op = precomputed 记账参数（`filler_count`/`repeat_count`，runner 计算后记账） | 不是客户端 edit ops 可提议 op（precomputed 归 task_list） |
| 风格 | `style` | 文风（写作风格），对外文案统一用词（hero/showcase/FAQ/identityEcho 已全扫）；voice 仅保留音频本义（声纹克隆/配音 dub）；Brand voice/语气 表单标签保留 | 不是"口吻"（已退役，2026-08-01）；不是 voice |
| 提及类型 | mention type（`ChatMention.type`） | @ 引用的实体类别：asset / output / transcript_segment / workflow_step / recipe（第五类，2026-08-01） | 不是自由文本、不是标签 |
| 提及注册表 | `MENTION_REGISTRY` | 前端提及类型注册表（icon / i18n / 候选源）；picker 与 chip 只读注册表，新类型 = 一条注册项 | 不是 switch 分支、不是插件系统 |
| 配方注册表 | `RECIPE_REGISTRY` | 服务端配方静态注册表（随代码部署）：任务书钉（outputs/dub_languages）+ 输入槽位 + status——**钉死唯一事实源**，钉死实质不出服务端 | 不是前端数据文件、不是表 |
| 输入槽位 | `input_slots` | 配方的类型化素材要求（素材类型 + 是否必填）；前端提示 + 服务端门禁双消费者 | 不是上传组件 |
| 流程视图 | `FlowView` | 只读图渲染基座（`components/flow/`，ADR-036）：节点皮（asset/output/step）× 双边语义 × 分层布局，四消费面共用；引擎 `@xyflow/react`（摆位+视口，布局自算）；编辑手势常锁，缩放按面门禁（导航 ≠ 编辑，ADR-036 补记） | 不是画布（canvas 撞可操作画布禁令）、不是图编辑器 |
| 血缘边 | lineage edge | FlowView 边语义之一：素材→产物 / 产物→产物（`derived_from_output_id`）的派生关系 | 不是依赖边 |
| 依赖边 | dependency edge | FlowView 边语义之二：step 间工艺顺序（step `inputs`） | 不是血缘边 |
| run 进度图 | run flow graph | 单 run 拓扑的只读状态动画投影（编译期定死的死图，ADR-036 第 3 条排产项）；适配器组件 `RunFlowGraph` | 不是 spike（spike 只剩血缘板）；不取代打勾流 |
| 配方流程画布 | recipe process flow | 配方 overlay"流程"tab 的唯一图面（2026-08-08，D6 二次修订）：素材 → 策展步骤（fanout 展开）→ 烘焙成片的一张图；适配器 `recipeProcessFlow`（`components/recipes/recipeFlow.ts`） | 图只画一次——示例 tab 是平铺输入/输出卡，不是第二张图 |
| 家族视图 | family view | 舞台焦点产物的一跳血缘邻里（父 + 己 + 派生子） | 只画一跳，不画全史 |
| 血缘板 | lineage board | 项目全史产物血缘的只读投影（spike 名，09-03 复述测试裁决是否升正默认中心） | 图内不堆历史（禁令 #6） |
| 人设 | `Persona` / `personas` 表 / `/api/v1/personas` | 身份模块唯一对象（ADR-037，N-27；2026-08-09 第一刀落地）：身份卡 + 风格 + 策略 + 声音（+ 皮肤，第二刀），多实例扁平（工作号/生活号）；用户面 zh「人设」/ en「Persona」，三层同词族 | 不是 speaker——`speaker` 只指素材里说话的人（`speaker_map` 合法居民）；不是 IP（承诺层词，禁入英文文案） |

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
| N-17 | ContentPlan 拆分：素材理解 `MaterialUnderstanding` + 分镜表 `Storyboard`；DerivativePlan 退役为槽位 `StoryboardSlot` | 导演两步走落地（`docs/tasks/done/director-two-step.md`）：理解=素材级（asset-hash 复用），分镜=请求级（每 run 重排）。否决 `TaskBoard`（撞 TaskSpec/TaskItem 词族，N-11 同型三撞）与 ContentPlan 沿用（理解是描述不是计划，沿用旧名不诚实）。"两个 plan 各司其职"注记改写：RunPlan 成唯一 plan | §1、§6 |
| N-18 | `IntentProposal` 升三态（**翻案 N-14**） | 结构化 ask 的 payload 与 task_list/edit_ops 正交，判别联合加第三态；N-14 的"tasks=[] 反问"迁移为 ask 的 freeform 形态（options 空 + allow_freeform）——反问仍是合法输出，只是有了类型座位（简报 `tasks/done/intent-ask-primitive.md` §2.3；期 3 已落代码） | §1 |
| N-19 | 机制词与用途词分离 | 机制一词一物：`Suspend` 异常 / `waiting` 状态 / `answer` / `bail`；用途住 payload kind（`question.kind` / `spec.for`）；**用途×机制组合词永禁**；配对词整体引入（ask/answer/bail）；状态词从机制动词派生（Mastra 参照） | §1、§6 |
| N-20 | 任务槽 vs 分镜槽分层 | `IntentSlot`（请求层：用户要什么）≠ `StoryboardSlot`（派工层：导演怎么排）——两层各有槽位词，混用即违规 | §1 |
| N-21 | `IntentProposal` 升四态（answer 直答态，延展 N-18） | 纯信息直答（能力/进度/解释/闲聊）与 task_list/edit_ops/ask 正交，判别联合加第四态 `AnswerProposal{type:"answer", text}`——落普通 assistant 消息，不起 run、不 dock；与 ask 的边界写死在 agent 规则（无工作请求且无歧义才可用）。沿用 `answer` 词（§1 同概念同名：与 `InferredIntent.action="answer"`、messages.answer 同族）；同一机制收编发布/导航引导，不开新通道（期 4 补四已落代码） | §1 |
| N-22 | 应用区定名 `studio`，workbench/工作台全库退役 | 创作类 AI 产品惯例（ElevenLabs/Suno/Descript/PlayHT Studio）；workbench 是企业 SaaS 语域（控制台味），与 agent/IP 孵化定位不符；studio 无夸大（一间创作的屋子，不承诺结果）。动线闭环：landing 按钮"进入工作室"→ home 接待语"欢迎来到你的工作室"。i18n key `openWorkbench`→`openStudio`，CLAUDE.md 布局节与代码注释同步 | §1 |
| N-23 | 品类词 = agent，空间词 = studio，两层分离 | 品类自称永远是 agent（PRD one-liner "An AI agent for knowledge experts"、hero "We do the rest"）；**studio 只做应用区空间名**（"你的工作室"），永不出现在品类陈述句（"Repurposer is a …"）——避免触发 CapCut/Descript 式工具功能数量对标（外部评审 Kimi 同判：叫 studio 就被拉进工具军备竞赛，叫 agent 比的是交付与省心）。空间名成立前提：房间内永不出现工具货架（多轨/特效/素材库），UI 保持 composer + 卡片、editor 薄化；中文"工作室"双关运营团队（明星工作室 = 替名人运营自媒体的班子），与 agent 定位咬合 | §1 |
| N-24 | 品类词只用 `agent`，角色隐喻（运营官/操盘手/班子）全库退役 | 角色包装是话术 dressing：landing heroSubtitle 自称 "an AI agent"，PRD 曾写 "content-operations officer"——一份产品两个自称，朴素品类词胜出（2026-08-01 用户裁决）。PRD one-liner / CLAUDE.md 定位条 / N-22·N-23 引述同步清洗；"运营官"承载的洞察（用户不懂自媒体、产品指导并孵化其 IP）保留在 CLAUDE.md 定位条，仅标签退役 | §1 |
| N-25 | 自称双轨：对内技术 = agent，对外文案 = assistant/助手（细化 N-24 适用范围） | "agent" 对非技术用户是行话（欧洲用户甚至会读成"经纪人/特工"）；技术实体不变——架构/PRD/CLAUDE.md/代码全用 agent，N-24 的隐喻禁令不变；hero/showcase 等对外文案一律 assistant（EN）/ 助手或代词"它"（zh，zh 优先代词）（2026-08-01 用户裁决）。对外文案中出现 "agent" 字样即违规 | §1、§6 |
| N-25 | 任务书钉死归服务端配方注册表解析；mention 系统双端注册表化 | 钉死唯一发生地 = 服务端 `resolve_recipe_mentions`（composer/chat 两表面同一份解析器）；客户端 prior 构造路径退役（旧事故根因：隐式状态 + 客户端持钉）。提及类型与效果各自注册表化（recipe 第一成员、第五提及类型），后续 @ 类型只填注册项，禁类型分支补丁（2026-08-01 用户裁决：mention 做成可扩展架构，功能先只开 recipe）。**词汇修订**："硬编码"表述退役——正确表述是"静态注册表，随代码部署"（SKILL_REGISTRY 同款纪律）。**2026-08-05 语义修订**：钉（pin）降为**预设播种（preset seed）**——存在性填充（只补推断没有的槽位类型）+ dub 空时填默认，无 explicit，下一轮起每个字段可经 chat 修订（chat 永远赢，三方合并 `merge_prior_slots`）；"唯一发生地 = 服务端解析"不变 | §1、§5 |
| N-26 | chat 流式词族：delta = 散文预览增量，envelope = 终帧信封 | 流式三层各一词：LLM 原始片 = fragment（`on_delta(fragment)` 入提取器）；解码后散文增量 = **delta**（SSE 帧 `assistant.delta`，纯预览，非事实源）；终帧 = **envelope**（`turn.completed`/`turn.failed`，完整 ChatResponse，永远权威）。机制名：`ProseDeltaExtractor`（唯一散文提取入口）、`MiniMaxClient.generate_stream`、service 拆分 `prepare_chat_turn`/`execute_chat_turn`、前端 `streamChat`。禁 chunk/token 混用（chunk 是 HTTP/LLM 传输单位，token 是计费单位，delta 才是渲染单位）（ADR-034） | §1、§5 |
| N-27 | 身份模块正名：Speaker → 人设 / `Persona`；`speaker` 让位素材说话人 | 定位升级后"演讲者"前提崩塌（素材 = 会议/报告/播客，不只是演讲）+ 一词三义（用户身份画像 / `speaker_map` 素材里说话的人 / landing 普通词 speakers）。用户面 zh「人设」/ en「Persona」、代码 `persona`，三层同词族；`speaker` 此后只指素材里说话的人（`speaker_map` 合法居民）；**IP = 承诺层词，禁入英文文案**（en 叙事 = personal brand / thought leadership），不进产品内导航（ADR-037，翻案 ADR-021 §6）。迁移落地时词汇表登记「人设 / Persona」 | §1、§6 |
| N-28 | 人设吸收 Brand：`brand_templates` 退役，皮肤 = `persona.brand` | 多人设拍板反转拆分理由（一人多号 = 多人设各带皮肤）；`config` 杂物抽屉三分流——皮肤→`brand` 块、工艺开关（removeFiller/captionEnabled/aspect/fillMode）→配方/任务书默认、CTA 唯一家 = `persona.cta`；**`brand` 全栈一词**（人设块 / 烘焙 / clip-spec 段同名）——模块退役词不退役，不引入 `look` 字段名（避免撞 RECIPES §4.4 look 层组合概念）；composer 单身份控件；失去独立表归属即失去模块资格（§7 逆用）（ADR-038） | §1、§7 |

## 4. API 命名

- REST，复数资源，动作用子路径：`POST /outputs/{id}/render`、`POST /outputs/{id}/dub`。
- 不为单个动作造 RPC 式端点（`/api/sendChat` 此类永不出现）。
- 内部类型（如 `material_understanding` / `storyboard`）不得从任何公开响应漏出——统一经 `visible_outputs()` 过滤（ADR-030 D1）。

## 5. 命名审计触发点

以下情况必须做命名审计并在任务简报中列出结论：

- 新模块 / 新表 / 新 skill 准入（§7、§8）；
- 大规模重构（判例 N-06 的重构简报附带全库审计）；
- 发现同名不同物（如 `routers/intent.py` vs `agents/intent.py`）或同物不同名（如 `music.py` / `music_generation.py` 的职责切分）。
