# NAMING — 命名宪法与判例库

> Status: Active（2026-07-25 建立，2026-08-18 校订）
> 适用范围：模块 / 包 / 表 / 字段 / API / tool / skill / 事件——一切会被别人读到的名字。
> 用法：命名争议不复述本文论证，引用条目号（`NAMING §3`）或判例号（`N-29`）。判例只保留现行裁决——过时 / 被翻案的判例直接删除（历史在 git，不留痕）；新判例追加新编号。

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
| 计划 | `TaskSpec` / plan（chat 侧） | 意图归一：工具链（`tasks`，唯一语法，N-37）× instruction。zh 恒「计划」、en 恒 "Plan"，全界面一词（画布名词节点 / 确认 dock / 计划界面同词）。**plan 归两主**（N-44 修订）：本行 = chat 计划书（plan path 义）；pipeline `plan` 节点 = planner 义，双座分工不互改。存储字 `task_book` 冻结（question.kind / spec.role / 存储镜像键，N-52） | 不是 pipeline plan 节点（另一主）；不是 workflow（代码/文档词） |
| 任务列表 | task list / `TaskItem` | intent agent 的轮内提议（tool + params），compile_graph 模式②的输入；**plan path 的 dock 计划也是它**（N-37——产物请求语法已统一为工具链） | 不是 plan、不是 node spec |
| 施工图 | RunPlan / `workflow_steps` | **执行计划**+账簿一体的 DAG 内核（谁干什么、什么顺序、花多少） | 不是 DAG 画布（用户不见图） |
| 步骤 | `WorkflowStep` | 施工图上的一个执行单位 | 不是 job、不是 task |
| 对话 | `Conversation` | chat 的会话容器 | 不是 thread、不是 session（撞 auth session） |
| 素材理解 | `MaterialUnderstanding` / type `material_understanding` | understand 节点产出：素材级理解（论点带位置/金句/主题/受众 + 节拍地图），内容寻址复用（`content_sha256`，同用户跨项目） | 不含任务信息 |
| 节拍地图 | beat map（`MaterialUnderstanding` 期 1 字段集） | 素材级语义节拍：`topic_boundaries` / `climax_spans` / `emphasis_words` / `quotable_lines` / `narrative_role_hints` / `visual_anchors`——LLM 只出文本锚（+ 可选秒数提示），`start`/`end`/`asset_id` 恒由代码吸附 ASR 词轴（locate_span 同纪律，词级时间戳零覆写） | 不是节拍方案（beat plan = 期 2 剪辑师产出）；声学半不住这里（`asset.meta["prosody"]`） |
| 节拍方案 | `BeatPlan` / `StillBeat` | 期 2 剪辑师产出：一条 stills 切片的拍级时间线（图序/运动/强调/复位 + 文本锚）；代码吸附词轴后**平铺**（拍尾 = 下一拍头，dwell = 词跨——字幕/切点/停顿时长共享一只词钟），编译为 `source.image_shots` + 字幕 cue `emphasis`；跨拍连贯性检查（`coherence_violations`）独立存在，违规骑 `repair_feedback` 一轮有界重掷 | 不是节拍地图（素材级语义标注）；不落库——编译产物住 render_spec |
| 剪辑师 | stills editor（`stills_editor` / `stills_editor_outline`） | stills 工具包的私有 agent 双件：单发可靠域（≤15 拍/≤45s）一发成案；超限两段式——大纲段（arc + 资源分配）→ 逐段拍（handoff 显式交接：已用图/末拍运动/强调史/段锚），拼后全局重平铺；工艺惯例骑 `stills-editing-craft` 指令包（装配期注入，N-42 ⑦） | 不是 plan 节点（派工层）；LLM 永不写时间戳（锚 + 吸附，同理解层铁律） |
| 韵律 | `prosody`（asset.meta 键） | 确定性声学特征工序（PROCESSORS 链，ASR/speaker_map 同族）：逐词 F0/能量 z 分、强调峰（f0/energy 声道分标不合流）、filler/死寂区 | 不是语义强调（`emphasis_words` 是语义半——两字段永不合并，预合并 = 自信地错且不可溯源） |
| 内容寻址 | `content_sha256`（asset.meta 键） | 素材字节哈希（处理链首工序/粘贴文本创建时盖章）：理解层复用的寻址键，同素材二次上传零 LLM | 不是 asset id / file_url（那是上传身份，仅作无哈希行的回退） |
| 分镜表 | `Storyboard` / type `storyboard` | plan 节点产出：请求级派工（槽位+覆盖报告），每 run 重排 | 不是 task board（撞计划词族）；不读原稿 |
| 槽位 | `StoryboardSlot` | 分镜表一行：一个产物的 what（论点/角度/语言/格式） | how 归 executor |
| 覆盖报告 | `CoverageReport` | 论点→槽位映射 + 未用/撞车，代码推导落库 | 不是门禁（门禁归 Phase 3 质检节点） |
| agent | `Agent` / `app/agents/` | LLM 决策单元（N-29 正名，行业标准词）：**一个 Agent 类 + 声明实例**（N-30）——实例 = name/prompt/schema 声明，花名册 `AGENTS` 可枚举；工具私有声明住工具包，共享 crew 住 `agents/registry.py`；特殊子类仅流式（chat intent）；**N-43 判词**：实例 = 声明式结构化调用（= AI SDK `generateObject`），非业界 autonomy 义——agent 性在产品承诺层（厚 agent = 一个 assistant），实现层全 workflow | 不是 xxx_agent 子类群；不是 autonomy 义的 agent（永禁）；领域逻辑归 schema 校验/工具包工序 |
| 工具 | tool（`app/tools/`） | 能力层注册项（N-42 全量对齐行业 tool）：agent 会做的事（schema + execute；**调用方 = 图，模型永不直调**——禁 ReAct 不变）；执行者是 agent 还是机械 = 工具包的构成，不是分类字段（actor 概念退役，N-31） | 不是 model-facing tool；不是营销词「技能」 |
| 工具包 | tool package（`app/tools/<name>/`） | 能力的唯一家：节点类 + params schema + 私有工序 + 估价 + 展示键（+ 私有 agent 声明）；新增能力 = 加一个包 + 一行 import | 不是共享资源层（agents/providers 是共享层） |
| 指令包 | skill / `app/skills/` + `SKILL_REGISTRY` | 领域知识即数据（写作惯例 / 渠道约束 / 语种惯例），**行业 skill 包格式 + instructions 式装配消费**：SKILL.md + references/ 渐进披露 + 版本治理；装配器按节点条件注入，模型无感、永不进 loop；覆盖 = name-wins 整包替换（persona 级 > 平台级）；对标 Agent Skills 规范（四厂商同格式，证据 `research/agent-skills-spec.md`）；注册表名 = SKILL_REGISTRY（行业本义重生——能力侧已让位 TOOL_REGISTRY）。首包 = `linkedin-longform`（write_post 内嵌 prompt 逐字节平移，零假设字节级一致；命名批 v2 ⑦ 已落） | 不是技能（营销词）；不是工具（能力恒为代码，指令包参数化工具、不取代工具） |
| providers | `app/providers/` | 外部服务包装的一统家：**`llm/` 子层 = Model 缝**（含 PRICING 价目表；第二 provider 的家，ADR-025 薄接口落地处）+ asr / voice / vision / storage 等；**禁 import agents/、禁 import LLM 决策层**（N-29 铁律迁址，grep 门禁） | 不是能力（能力归工具包） |
| 技能 | ——（营销泛词，无代码对应，N-42） | 用户文案里的泛能力修辞（"多语言字幕是我们的技能"✓）；**不是代码词**——UI 零命中证实非用户可操作对象；§1 同词纪律只约束用户可操作对象（配方/人设/计划/产物/@mention），营销泛词豁免 | 代码里没有叫技能的模块（能力 = 工具；指令包 = `app/skills/`） |
| 机械 | ——（退役为描述语，N-42） | "确定性工具"描述语：无 LLM 决策的工具子集（估价精确价的那个类）；不再是独立目录（原 `app/tools/` 拆 providers/ + 通用件随消费方） | 不再作独立座位词 |
| 内部节点 | internal nodes | 非工具的内核 crew（住 `pipeline/`）：preprocess / persona_bootstrap / understand / plan / interrupt / render；例外：`materialize_source` 住 `tools/clips/`（复用 select_clips 的源决策函数，搬入 pipeline 会成 pipeline→tools 反向 import），以 `NodeBase.internal` 声明，自检豁免注册表席位（ADR-043） | 不进 TOOL_REGISTRY（interrupt 先例不变） |
| 调用面 harness | harness | 模型调用面脚手架：Agent 漏斗（装配→渲染→调用→校验→修复一轮→计量→声明兜底）+ contexts 装配 + prompts 模板 | harness 单义 = 本行（N-48）；测试脚本不叫 harness（那叫剧本测试） |
| 估价 | `estimate` | 节点级估价函数（N-34）：机械精确价 / agent token 区间；**报价 = 图 fold**（全图 = 生成前总价，子图 = 修改单价）；`workflow_steps.estimate` 计划侧列与 `cost` 账簿侧对称 | 不是 `cost_hint`（三档已退役） |
| 质检 | verify（节点 kind） | 单产物/全片质量校验节点（Phase 3） | 不是 eval（eval 是活动，verify 是节点） |
| 质检环 | verify loop（`pipeline/verify.py`） | 期 3 落地的完整机制：executor 后挂 verify（`spec.for` = 产物类型；modifier 链尾部进 inputs，永远检终态）→ 确定性检查矩阵（quality.py，零 LLM）+ judge  advisory（§2.7 校准集落地前不作闸，cls="judge" 只进台账）→ 打回/回退/升级路由；裁决落 `outputs.quality`（`passed` / `needs_human` 非阻塞徽章） | 不是外挂流程——图内节点，attempt 预算是环的界 |
| 打回 | `QualityBounce` | 质检环的有界环传输（ADR-047 节点内有界环）：verify 抛出 → execute_step 复位 executor+verify 为 pending（反馈骑 executor `spec.feedback`，runner 一次性弹出进 repair echo），下游已完成 modifier 一并复位重施；≤2 轮，成本落 executor 节点 | 不是 tool-loop；不是盲重试（反馈必带失败项+白名单纪律行） |
| 最优轮回退 | best-not-last | 逐轮独立评分（同一检查矩阵），回归轮恢复 `spec.rounds` 快照里的最优早轮（新 id 重插 / targeted run 原位回滚），"末轮即最终"被禁 | 不是版本树（只存轮快照，无分支语义） |
| 产物 | `outputs` | 统一产物表；clip 是 type 之一 | 不是 clips/derivatives（已退役） |
| 帧卡 | `quote_frame`（output type） | 金句链的逐条产物 PNG（帧底/照片底/深色底 + 单条字幕块）与链合成卡共用的产物 type（quote-cards §2.2）；合成卡以 `source_ref.quote_chain` 标记、以 `source_ref.parents` 指认帧卡父级；**图片产物**——无 render_spec、无渲染管线，zh 界面词「帧卡」 | 不是 render 任务；不是 quotes 行（quotes = 写手文本产物，帧卡 = 烘焙图） |
| understand | `understand`（kind / 节点类 `Understand` / agent 实例 `understand`） | plan 前奏第一步：素材 → 素材理解（素材级，`source_ref.asset_hash` 命中即复用；N-44 正名，原 `director_understand`） | 不是角色（「导演」概念已退役——动词即节点） |
| plan | `plan`（kind / 节点类 `Plan` / agent 实例 `plan`） | plan 前奏第二步：素材理解 + 计划 → 分镜表（请求级，每 run 重排；**plan 归两主**——本行 = pipeline 唯一规划节点（planner 义），chat 计划书 = plan path 义，N-44 修订） | 不是 RunPlan（执行计划，工程层）；不是 chat 计划（另一主） |
| 精修 | refine | Edit / Chat / Regenerate 三角的统称 | — |
| 提及 | mention | 对话中的 @ 实体引用 | 不是 reference、不是 entity |
| 施工图编译 | `compile_graph()` | 计划 → 节点图的纯函数 | 裸 plan 违规（N-11），故以产出物命名 |
| 操作 | `Operation` | 产物级编辑动作的记录（op + params + spec_after 快照），operations 表 | 不是 plan 级节点操作（归 RunPlan 小拓扑） |
| 操作源 | `source` | operation 的发起来源：editor / chat / mcp / system（注册表） | — |
| 结果卡 | `RunCard` | assistant 消息内嵌的 run 线性投影（步骤清单 + 产物卡片 + 聚合行） | 不是 DAG 画布 |
| 提问 | `ask_user`（终态工具） | ask 的唯一座位 = 终态工具 ask_user（plan path 与 chat loop 两线同名，ADR-077 判词②；其 params 类型 = `PlanAskArgs` / `ChatAskArgs`，N-18 的 action 动词座已随 action union 退役迁入工具集） | 不是名词座位——dock 态 = question（落库 JSONB） |
| 问题 | `question` | 落库态：messages.question JSONB（kind: task_book/question + options/allow_freeform/estimate，旧行读容忍升级只读不写）；已决坍缩入流 = answered question | 待决渲染按形态律分流（下行），不再一律 dock |
| 文字问 / 选项问 | —（渲染形态词，非 schema 字段） | 形态律（ADR-053 R1）：按 `options` 是否为空分流——文字问 = 普通对话消息（永不 dock，待决/已决都在流里）；选项问 = 输入框上方非阻塞 pill（待决只在 pill）。与 kind 无关 | 「形态切换」「morph」永不指提问形态（阻塞形态已拆除） |
| 插话 | —（行为词） | 待决中与问题无关的用户消息（ADR-053 R2）：判定是 LLM 的（slot 握手 / `pending_disposition`），结算是代码的；插话回合回复接代码拼装**提醒尾**（双语固定句：原问题 + default_path） | 不是新意图态（信封字段，非第五提案态） |
| 回答 | `answer` | 一词两态同域：① 落库态 messages.answer JSONB（kind: option/freeform/bail/start + answered_at）——**用户**答复待决问题，NULL = 待决，answer 端点即恢复；② 提议态 `AnswerProposal`（IntentProposal 第四态，N-21）——**系统**对信息类提问的直答，落库为普通 assistant 消息 content（B1 同款），**不进 messages.answer** | — |
| 弃做 | `bail` | 优雅退出一等公民：入口回 draft / checkpoint 下游级联 skipped；永不标 failed | 不是 cancel（cancel 是 UI 按钮词） |
| 任务槽 | `IntentSlot` | 任务链的**编译期投影**一行 = 一个产物的规格（type/count/focus/language/tone_override/explicit）：住生成节点 `spec.slot`（同类型兄弟区分 + 步骤标签 + 派工对账），请求层永不声明（N-37，ADR-043）；存量 run.context 行读容忍 | **不是分镜槽位** `StoryboardSlot`（派工层，N-20）；不是请求语法 |
| 挂起 | `Suspend` | 挂起异常：checkpoint 瘦节点转 `waiting` 的机制（期 4 已落代码）；状态词从机制动词派生 | 不是 paused——启用已有 waiting 座位 |
| 中断 | `interrupt` | 节点 kind：提问-等待-续跑的瘦节点（`spec.for` 住用途） | 不进 TOOL_REGISTRY；不是 LangGraph checkpoint（状态快照供恢复）——语义近 LangGraph `interrupt()` / Mastra `tool_suspended` |
| 配方卡 | `RecipeCard` | 首页能力演示卡：承诺 + 输入槽位 + 预设工具链 + preview（RECIPES §7） | 不是模板市场、不是内容流 |
| 派生预览 | `derived`（`pending_brief.derived`） | 计划卡的「你将得到」投影行：dock 时服务端干跑 compile_graph 产出（type / variant=subs\|dub / language / count / bilingual）；只读展示，编辑面是链行本身（ADR-043） | 不是产物声明（请求层无 outputs，N-37） |
| 整条源材料化 | `materialize_source` | 编译期注入的内部节点：链含 clip-spec 消费者而无 select_clips 时，把项目主源落成一条全段 clip-spec（整条视频，无 LLM 选段）；画像分发 media / stills（先 align_stills）/ existing（不注入）/ 无（编译期 422 指名拒绝） | 不是注册工具（用户从不说"materialize"） |
| 派生 | `fork` | 变换节点的用途标记（`spec.fork`，dub / translate 同款）：true = 新建派生产物行（原版共存）；false = 原地改写 render_spec | 机制词仍是原工具名（N-19 用途住 payload）；不是 git fork |
| 派生来源 | `derived_from_output_id` | 派生行 `source_ref` 内的溯源指针（住 JSONB） | 不新建表列 |
| 字幕样式目录 | `CAPTION_PRESETS` | 字幕样式注册表（packages/clip）：preset id → 原语组合；TS 类型由它推导，Python 只校验成员 | 不是自由样式（preset 枚举纪律不变） |
| 布局 / 进场 / 词级高亮 | `layout` / `entrance` / `wordHighlight` | 字幕样式三原语：single\|stack × none\|fade-in\|pop-in\|slide-up × bool | — |
| 堆叠 | `stacking` | catalog 成员：新行淡入、旧行驻留、超 maxLines 滑动窗口 | — |
| 工作室 | `studio` | 登录后应用区（landing 之外的 sidebar 世界）的统称：home composer、projects、editor；用户文案（`openStudio`、"欢迎来到你的工作室"）与内部文档同词。**只是空间名**，品类自称永远是 agent（N-23） | 不是 workbench/工作台（已退役，N-22）；不是品类词 |
| 助手 | `assistant` | 对外文案的自称（N-25 双轨：对内技术 = agent）；zh 优先用代词"它" | 不是 agent（agent 只对内）；不是运营官（已退役，N-24） |
| plan 路径 | `plan path` | chat service 内分派分支：首次 / 待决计划的项目级回合 → 计划构建/修订/确认（`plan_turn.py` 有界工具 loop，asset scope 永不进；N-44 修订——plan 归两主，chat 侧正名 plan path） | 不是相位（confirm 相位已降为"有 pending task_book"的普通 chat 状态） |
| 路由器 | intent router（`intent_router`） | chat 边缘的意图路由（N-44 / ADR-052）：`plan_agent` / `chat_intent_agent` 的同概念正名——一个 router 两个相位 prompt（pre-run / post-run，相位 = 上下文参数）；ask 形状两相位共享（pre-run 不能提问的不对称根除）。业界坐标 = Anthropic routing 模式 / OpenAI SDK triage。**落地现状**：pre-run 相位实例已更名 `intent_router`（B1，2026-09-03）；post-run 相位实例仍名 `chat_intent_agent`——**物理形态已拍板 = 双实例保持**（2026-09-03，判词 DIALOG_WORKFLOW §8） | 不是 autonomy 义的 agent（永禁）；不是第二意图入口 |
| brief | brief（`projects.pending_brief` 的 brief 块） | 对话引擎的结构化状态（N-45 / ADR-052——更名已随 B1 落地 2026-09-03，原 `pending_intent`；类名 `Brief`，命名批 v3 ② 自 `BriefLedger` 收窄，账本修辞退役）：槽位 topic / audience / tone / constraints[] / material_state + 任务链与 derived（原样）；**每槽带来源 user-stated > inferred > default，代码侧合并**（LLM proposes, code decides）；上下文工程主压缩件（累积 prompt 叙事降存档位） | 不是会话记忆（记忆层座位不变）；不是计划（计划 = brief 的渲染）；不是 session state（评审被拒，N-52） |
| 有界 loop 节点 | bounded loop node | pipeline 侧 agent 性的合法座位（N-47 / ADR-052，**已落地**——B4 收口 2026-09-04，试点 = research 节点）：`NodeBase` 子类，内部 mini tool-loop（工具 = `app/tools/` 注册表）——三护栏：迭代上限（节点声明）/ 报价 = fold（上限 × 单次）/ 对外 = DAG 单节点（拓扑 / 占位 roster / SSE 无感）。业界同构 = LangGraph subgraph / Mastra agent-in-step / Anthropic agentic component | 不是开放式 autonomy（永拒不变）；chat 侧的有界工具 loop = `ToolLoopAgent`（另一座，ADR-077） |
| 剧本测试 | `chat_scenarios.py` | scripts/ 下的剧本测试脚本：预设多轮剧本对活 API 跑形态级断言（S 编号，真实 LLM 不锁文案） | 不是测试套件（无测试套件纪律不变）；不叫 harness（harness 单义 = 调用面，N-48） |
| 能力层 | capability layer | 编辑能力的唯一事实层（ADR-033）：`OP_REGISTRY`（参数级微操作）∪ `TOOL_REGISTRY`（任务级宏操作），双注册表双海拔 | 不适配器私设能力 |
| 适配层 | adapter | 能力层之上的薄转换：chat / editor /（预留）mcp——只做"输入形式 → 注册表调用"的翻译 | 不含编辑逻辑；不是新能力来源 |
| 瞬时节点错误 | `TransientNodeError` | step 级重试的判定类型（`app/pipeline/errors.py`，agent-loop-upgrade W3）：provider/网络/存储瞬时故障；`execute_step` 按节点类声明的 `retries` 预算（`NodeBase.retries`）复位 pending | 不是确定性失败的通行证——缺失输入/空批次必须普通异常快速失败 |
| 去口头禅 | `remove_filler` | tool 与 op 同名同义（跨注册表对齐 §1，agent-loop-upgrade W4）：tool = 确定性 modifier（task_list 派发）；op = precomputed 记账参数（`filler_count`/`repeat_count`，runner 计算后记账） | 不是客户端 edit ops 可提议 op（precomputed 归 task_list） |
| 风格 | `style` | 文风（写作风格），对外文案统一用词（hero/showcase/FAQ/identityEcho 已全扫）；voice 仅保留音频本义（声纹克隆/配音 dub） | 不是"口吻"（已退役，2026-08-01）；不是 voice |
| 声纹块 | `personas.voice`（JSONB） | 人设的声音绑定（音频本义，N-28 归还）：`{"kind":"cloned","voice_id","sample_asset_id"}` \| `{"kind":"stock","stock_id"}` \| NULL=Auto；旧 voice 文本（文风）已并入 `guidelines`，不再单列 | 不是文风（文风 = `style` + guidelines） |
| 皮肤块 | `personas.brand`（JSONB） | 人设的视觉皮肤（字幕字号色 / 标题 / intro/outro / logo / 音乐选择），烘焙时合并系统默认皮肤进 clip-spec `brand` 段；NULL = 系统默认皮肤。**`brand` 全栈一词**（人设块 / 烘焙 / clip-spec 段同名，N-28） | 不是 brand_templates（表已退役）；不引入 `look` |
| 提及类型 | mention type（`ChatMention.type`） | @ 引用的实体类别：asset / output / transcript_segment / workflow_step；`recipe` 已退役（MENTIONS §3——配方 = 发射上下文，不是 mention），类型成员保留供历史消息 chip 渲染 | 不是自由文本、不是标签 |
| 提及注册表 | `MENTION_REGISTRY` | 前端提及类型注册表（icon / i18n / 候选源）；picker 与 chip 只读注册表，新类型 = 一条注册项 | 不是 switch 分支、不是插件系统 |
| 配方注册表 | `RECIPE_REGISTRY` | 服务端配方静态注册表（随代码部署）：卡面数据（input_slots / status / tags）+ 示例素材/成片 + flow 图 + 预设工具链（`tasks`——启动对账自检的声明形态，不进请求路径，配方 = 提示词，ADR-040/043） | 不是前端数据文件、不是表 |
| 输入槽位 | `input_slots` | 配方的类型化素材要求（素材类型 + 是否必填）；发射区 Input 小节（前端）+ 启动自检输入画像（服务端）双消费者 | 不是上传组件 |
| 宽槽 | `any_of`（`InputSlot.any_of`） | 输入槽位的任选形态（quote-cards P2，ADR-048 合成类宽槽任选+可空）：所列素材类型**任一覆盖即过**；与 `type` 互斥（窄槽），`accepted_types` 是全栈统一读取口 | 不是多槽并列；不是类型数组裸写 |
| 父级指认 | `parents`（`source_ref.parents`） | 产物→产物的 N→1 派生指针（quote-cards §2.2）：链合成卡指认其帧卡父级、动效 MP4 指认合成卡；画布血缘边的服务器事实源 | 1→1 派生仍走 `derived_from_output_id`（fork 族），两词不混 |
| 流程视图 | `FlowView` | 只读图渲染基座（`components/flow/`，ADR-036）：节点皮（asset/output/step）× 双边语义 × 分层布局，四消费面共用；引擎 `@xyflow/react`（摆位+视口，布局自算）；编辑手势常锁，缩放按面门禁（导航 ≠ 编辑，ADR-036 补记） | 不是画布（canvas 撞可操作画布禁令）、不是图编辑器 |
| 血缘边 | lineage edge | FlowView 边语义之一：素材→产物 / 产物→产物（`derived_from_output_id`）的派生关系 | 不是依赖边 |
| 依赖边 | dependency edge | FlowView 边语义之二：step 间工艺顺序（step `inputs`） | 不是血缘边 |
| 底部 dock | chat dock（组件 `ChatDock`，2026-09-02 由 GenerationOverlay 改名） | 项目页的 chat 外壳（`components/chat/ChatDock.tsx`）：**两态形态机**——首个 run 前 = 居中全屏 chat（full），首个 run 到达收拢成底部 dock（dock）；dock 形态下**三可见性态**——收起 = 输入组（唯一常驻 chrome），展开 = 历史区域在同一容器内向上生长，hidden = 用户手势收成右下角 LogoMark 点（agent 发声 / 待决提问 / 焦点唤回）；agent 发声必自动展开（#6） | 不是第二意图入口（推断/合并/确认全在 plan path） |
| meta 行 | meta row（`MetaRow`） | 系统层事实的消息流内灰色渲染（Claude Code 解剖：muted + xs + 无填充无卡片 + 流内左对齐 + 超长截断可点开）——步骤勾选项 / recap 行（`RecapRow`，run 收官摘要单行）/ 焦点行（`FocusRow`）共用一族；**信息入流，控制留底** | 不是卡片、不是气泡、不是流外 chrome（独立摘要卡 / 焦点 chip 已退役） |
| 诞生回放 | birth choreography | 收官时画布按 `seq` 编译序逐节点入场 + 边描画（真实编译顺序的缓动回放，ADR-036 补记 3）；reduced-motion / 断线重连 / 历史打开直接终态 | 禁剧场（动画 = 真实事件投影） |
| 配方流程画布 | recipe process flow | 配方 overlay"流程"tab 的唯一图面（D6）：素材 → 策展步骤（fanout 展开）→ 烘焙成片的一张图；适配器 `recipeProcessFlow`（`components/recipes/recipeFlow.ts`） | 图只画一次——示例 tab 是平铺输入/输出卡，不是第二张图 |
| 家族视图 | family view | 舞台焦点产物的一跳血缘邻里（父 + 己 + 派生子） | 只画一跳，不画全史 |
| 血缘板 | lineage board | 项目全史产物血缘的只读投影（spike 名，复述测试裁决是否升正默认中心，排期见 PROGRESS） | 图内不堆历史（禁令 #6） |
| 人设 | `Persona` / `personas` 表 / `/api/v1/personas` | 身份模块唯一对象（ADR-037/038，N-27）：身份卡 + 风格 + 策略 + 声音 + 皮肤块（`brand`），多实例扁平（工作号/生活号）；用户面 zh「人设」/ en「Persona」，三层同词族。【已拍板重构（ADR-042 / `POSITIONING.md`，未实施）：根升格为「定位 `positioning`」，人设收窄为表达分区（风格 + 声纹 + 皮肤）；落地时本行改写并登记 `positioning` / `topics`】 | 不是 speaker——`speaker` 只指素材里说话的人（其分析产物 = `speaker_map`）；不是 IP（承诺层词，禁入英文文案） |
| 记忆层 | `app/memory/` | 行业座位词（Agno Memory 同座）：agent 长期记忆的家；现住户 = persona 身份记忆（语义记忆：身份卡 / 风格 / 声纹 / 皮肤）；积累式写入路径 = persona 校准打分（PROGRESS 需求池 P1）；召回形态 = 烘焙注入 GenerationContext | 不是会话记忆（对话不跨项目召回）；不是 Agno Learnings（runs 捕获式学习，未建） |
| 轨道 | `track` | clip-spec 的命名分区 = 轨道注册表一条声明（ADR-044）；**裸用违规，必须带家族限定**（主轨/数据轨/层/块轨，N-38） | 不是 NLE 自由轨；用户永不见轨 |
| 主轨 | main track | `source` + `segments`，输出 = 数组序连接；唯一持剪辑语义（hidden/trim/reorder）的轨 | — |
| 段 | `segment` | 主轨一行：`{id, asset_id?（缺省=主源）, start, end, hidden}`；异源插入 = 带 asset_id 的段 | 不是 block（讨论期占位词，草稿阶段死亡） |
| 数据轨 | data track（`*_track`） | 源时间轴时序数据：caption（词级）/ translation（单元级）/ crop（关键帧采样，08-19 线未实施）；按 sourceTime 采样 | 不是层；不参与叠放 |
| 层 | `layer`（字段 `layers`） | 锚定放置物列表：kind 枚举注册（broll / text_callout / pip / motion_graphic），z 序渲染；条目可带 `source_ref` 回放（PiP）与 `provenance`（必填，ADR-026） | 不是自由轨；不叫 overlay（UI 浮层词，N-27 同型避让） |
| 锚 | `anchor` | 层条目的语义挂接：段锚（`{segment_id + 源偏移}`）/ 边锚（`{head\|tail + 偏移}`，intro/outro 本质即边锚块）/ 比例锚（`{ratio}`）；输出时间由泳道投影派生，不落库 | 不是时间码 |
| 过渡 | `transition` | 段的进场边效果枚举（none/fade/dip，2-3 封顶），挂段随换序走 | 不是转场画廊 |
| 块轨 | block track | 单值轨，输出时间轴：music / dub / title / 头尾卡；dub⇄原声互斥在注册表声明，不写死渲染器 | — |
| 轨道注册表 | `TRACK_REGISTRY` | 轨的唯一家（ADR-044）：可执行 catalog 住 `app/pipeline/tracks.py`（owner / provenance / url_fields / depends——烘焙缝 / C2PA / ops 寻址 / 一轨一写者 422 全从它 fold）；`packages/clip` 只声明字段分区 `TRACK_FIELDS` + `TrackId`，tsc 类型断言强制每个 spec 键入一轨 | 不是 spec 容器（`tracks:{}` 永拒，收益证伪非兼容妥协） |
| 裁切轨 | `crop_track` | 第一个关键帧数据轨（family=data, timeline=source）：`{t, x, y, scale}` 按 sourceTime 采样（`sampleCrop` 双端逐值 parity）；空轨 = 静态 `crop` 缺省（缺省语义，非兼容包袱） | 不是逐帧密轨；用户永不见 |
| 说话人时间轴 | `speaker_map` | 素材级内部分析产物（谁在何时说话、在画面哪侧 + 素材形态归类），asset-hash 复用；crop_track 的上游（reframe_clip 消费） | 不进 TOOL_REGISTRY；用户永不见 |
| 修饰 | `morph` | 原地变换节点形态（`pipeline/morph.py`）：`spec.fork=false` 改写既有 render_spec 的变换节点（reframe_clip 等）的统称；跳过 / 救援语义自描述 | 不是工具注册项（机制形态词；工具名仍是 reframe_clip 等本体） |
| 救援 | `rescue` | morph 失败 / 跳过的保活机制：未触及目标保 base clip 下游可见；best-effort，永不掩盖失败本身 | 不是重跑（重跑归子图词汇） |
| 撤段 | removed segment（`segment.hidden = true`） | 编辑域用户语言：主轨被撤下的段（非破坏 hidden 标记）；撤段序单调性闸 = 段 `seq`（per-output 单调，baseline=0）在编辑重放下不许倒置 | 不是删除（真删违规，非破坏铁律） |
| 积分 | `credit`（复数 credits） | 用户面唯一计价单位（ADR-055）：估价 / 扣费 / 余额 / 配方卡估价贴 / 计划总价全部同一单位；序列化派生不落列（fold × `credits.per_cost_usd`）；zh 界面词 = 积分 | 不是 USD（内部成本层永不上 UI）；不是 token |
| 钱包 | `wallet`（`wallets` 表） | 用户积分余额 + 够不够花判定（ADR-055）：首登 lazy 开户 + grant；`balance` 是台账的物化缓存（允许为负），`version` 乐观锁 | 不往 `users` 加列；不是支付账户（支付 = W11 `payments`） |
| 台账行 | `credit_transactions`（表） | 积分余额变动唯一事实源（ADR-055）：append-only，kind ∈ grant / purchase / hold / capture / release / refund / adjust；`idempotency_key` UNIQUE 一等列；ledger 是子系统概念名不上表名 | 不叫 entry（双 entry 会计第三层用不到）；不叫裸 `transactions`（撞 DB 事务语境） |
| 消耗比例 | `credits.per_cost_usd`（configs key） | 每 $1 provider 成本的积分价（默认 1000）：报价 fold 与实扣同源单点，调参不发版、不动历史账 | 不是购买比例（钱→积分汇率 = W11 套餐定价决策，解耦） |
| 公共参数表 | `configs`（表）/ `get_config()` | 运营参数的统一家（ADR-055）：`CONFIG_REGISTRY`（key → default/类型/desc）是唯一事实源，表只存覆盖值，启动 reconcile 补插；读取一个漏斗，未知 key 报错 | 工程参数禁入（连接串/密钥/保险丝留 env `config.py`）；模块禁直查表 |
| 生命周期 | lifecycle | 产品阶段的五态命名事实（PREPARING / MATERIAL_READY / PLAN_READY / CONFIRMATION_READY / RUNNING，ADR-087 §2）：plan-scoped、服务端命名、只读 | 不是 run 状态机（执行层词汇）；不是 phase（phase = System Status） |
| 生命周期投影 | Lifecycle Projection | 生命周期事实的唯一计算层：消费 Domain 事实（资产状态 / task_book / 链裁决 / 活动 run），产出投影戳经 Transport 供 Presentation 订阅；对 Domain 只读（ADR-087 原则 2） | 不是 Domain 写口；不是客户端推导（客户端推导永禁） |
| 素材就绪 | MATERIAL_READY(P) | 计划 P 引用的资产全部 COMPLETED ∧ 无 FAILED ∧ 链所需内容事实就位（text 链需非空 transcript；transform 需已知语言）；相对 Plan P 的谓词 | 不是 project-global flag；不是 material exists（固定不等式） |
| 计划就绪 | PLAN_READY | unanswered task_book ∧ MATERIAL_READY(P) ∧ chain 对当前事实重裁决通过 ∧ 无挂起前置提问；驱动 Review Surface（Canvas + Confirm Dock）出现 | ≠ turn.completed / present_plan / task_book exists / activity.completed（固定不等式入册） |
| 确认就绪 | CONFIRMATION_READY | PLAN_READY ∧ 确认信息完整 ∧ 费用语义披露 ∧ 无活动 run；驱动 Confirm action enabled | ≠ PLAN_READY（PLAN_READY ∧ ¬CONFIRMATION_READY 合法——信息补全态 Confirm disabled） |
| 费用语义就绪 | Charge Semantics Ready | Paid Work 的确认前提（ADR-087 §2.1）：Known / Deferred / Conditional / Held / Actualized 五面披露完整——当前可得费用事实 + 未确定部分的不确定性/确定时点/计费规则 + hold 语义 + 最终扣费时点；未披露收费路径永禁 | ≠「全量估价非空」（ADR-063 估价随运行合法不变；全量估价硬门 = 独立未来决策） |
| 活动 | Activity | Agent 工作的用户安全观察流（可见性机制）：stable activity_id + sequence + started→completed/failed/cancelled，append-oriented | 不是 CoT / Tool Log / lifecycle authority / presentation 驱动器（永不控制 Canvas/Confirm/Run） |
| 活动投影 | Activity Projection | Internal Agent Events → User-safe Activity Events 的唯一过滤/聚合层（十条对账规则，ADR-087 §3）；首版无持久化无回放 | 不是事件总线；不是 workflow graph；不是 lifecycle |
| 系统状态 | System Status | `phase` 的保留义：系统宏观态（三概念分家——System Status / Agent Activity / Assistant Conversation） | 不再是 Activity container |
| 确认教义 | Confirmation Doctrine | Task Intent ≠ Paid Execution Authorization：一切新 Paid Work 经 PLAN_READY → CONFIRMATION_READY → Explicit Confirmation；Approved Scope 内 continuation 自治，Scope Expansion 重新确认（ADR-087 §4） | G-explicit 消息 ≠ 付费手势（永禁）；plan/propose 不得有不同 Paid Authorization path |
| 任务意图 | Task Intent | 自然语言请求的唯一语义——含明确指定输出/语言/数量/范围的 G-explicit 消息；可减少澄清直接成 Plan | 不是付费执行授权（再明确也只是意图） |
| 付费执行授权 | Paid Execution Authorization | 显式确认手势才产生的授权；plan path 与 propose path 同一路径同一 Confirmation Dock | 不是 task intent 的强形式；不是 scope continuation（那在已授权范围内自治） |
| 已确认范围 | Approved Scope | 可自治的 continuation：retry / internal repair / render continuation / execution step completion / approved-scope graph revision | 不含新增付费输出/分支（那是 Scope Expansion） |
| 范围扩张 | Scope Expansion | 新增未确认付费输出 / 新增付费分支 / 超出已确认范围 → 必须重新 Confirmation；包含性由 Application Command 层代码裁决 | 不是 LLM 自决（LLM 永不裁决范围包含性） |
| 探索产物 | exploration artifact | Agent 在 Project World 中生产的用户可理解工作产物族（ADR-088）：候选集 / 精选 / 内容方案；住 Project Artifact Graph 惰性族（prototype 第四值 `exploration`；I-EXPLORE-01：永不进执行拓扑 / 闭包 / 报价 rank / 媒体流边语义） | 不是执行节点；不是 task；不是 CoT |
| 候选集 | Candidate Set | 主题检索的证据集合 artifact（成员 = 时间区间 / 摘录 / 说话人 / 时长，每字段可回溯 transcript）；默认折叠、可展开（R1 粒度律：可见粒度服务「用户纠正 Agent」） | 不是 N 个独立画布节点；不是筛选结果（精选才是） |
| 精选 | Select | 候选的定版 artifact：证据引用（不复制源，R7）+ verdict + 一行用户安全理由 + 证据指针（R3——判断的输出是属性，推理过程永不持久化） | 理由不是推理过程（CoT 永禁）；不是 transcript 副本 |
| 内容方案 | Content Plan | Agent 的产品语义方案（ADR-088/089）：一个 Select 的内容化描述（source range / 产出要求 / 语言 / 字幕 / 文案 / persona 引用）——**编译器的输入** | 不是 Task / TaskSpec（那是执行表示）；不是 dock 计划书（task_book——并行弧期共存，ADR-089 §8 吸收） |
| 执行范围 | Execution Scope | Content Plan 经确定性编译的产物（task DAG + 报价 fold 的对象）；确认与范围裁决的事实基 | 不是裸 plan（N-11 不变）；不是 agent 提议文本 |
| 旅程 | journey（`journey_id`） | 一个 User Goal 的完整工作循环身份（R24）：探索产物的归属属性——画布组织 / 历史摘要 / 读取律的前提 | 不是图边（归属 ≠ 媒体流）；不是 session（撞 auth） |
| 决策包 | Decision Package | 确认面消费的完整决策单位（R16）：方案语义 + 编译范围 + 费用语义五面；确认戳（confirmed_at / confirmed_via）盖于其上 | 不是 task list 复述；不是报价单行 |
| 已确认范围快照 | Confirmed Scope Snapshot | 决策包确认时的持久化事实（confirmed plans + compiled scope + 戳，ADR-089 §4）：Approved Scope 的证明基材 + 修订路由器（R20，「plan 2」→ 节点集解析索引） | 不是「run 存在 + context 有 tasks」（P0-① 前形态）；不是审计专用件（修订基础设施） |
| 区间裁切 | `cut_segments` | 执行世界「已知区间 → 首个 clip」的确定性出生能力（ADR-089 §2，迭代二拍板项①，2026-09-23）：Content Plan 的 clip 输出经编译器解算（Select → 候选成员 → 数值区间 + 素材 id）后的唯一落地座位；params 只载 `segments` / `asset_id` / `aspect`，零 LLM 零发现语义；runner 模板 = `materialize_source` 零-LLM 配置推广到 N 区间 | 不是 discovery 工具（无 focus/count/ranking 永禁）；不是 select_clips 第二人格；不进 agent 词表（`llm_visible=False`）；语言/字幕/配音变种归下游 transform，不归它 |
| LLM 可见性旗 | `llm_visible` | 注册表条目的 prompt 投影开关（TOOL_REGISTRY 与 OP_REGISTRY 同词同律）：False = **compiler-only 公民**——`validate_task_list` 照常裁决（编译产物合法链），但永不投影进任何 LLM prompt 面（catalog lines / no-material 枚举）；「注册表存在 ≠ agent 可调用」的结构化座位 | 不是 seat（seat = 已注册未实现不可提议；它是已实现不可见）；不是 per-site `exclude`（那是按面排除清单，这是全局单一声明点） |

**plan 词汇现状**：plan 归两主（N-44 修订，命名批 v3 ③）——pipeline `plan` = 唯一规划节点（planner 义：素材理解 + 计划 → 分镜表）；chat 侧计划书 = plan path 义（`plan_turn.py` 的构建/修订/确认分支，类 `TaskSpec` / `PendingPlan`）。RunPlan = 执行计划（工程层）。plan 是合法词，但跨两主引用时必须带限定词——裸 plan（`lower_plan`/`compile_plan`）歧义，见 N-11。

**内容方案词汇现状（2026-09-22，ADR-088/089）**：Content Plan（探索族产品语义方案）与 dock 计划书（task_book，plan path 义）在迁移弧期并行共存；ADR-089 §8 退役弧收口后 Content Plan 为唯一「方案」座位，dock 内容 = 编译的 Execution Scope。裸 plan 违规（N-11）不变；跨层引用带限定词（pipeline plan / dock plan / Content Plan 三主并立期尤其）。

## 3. 判例库（只保留现行裁决）

| # | 判例 | 裁决 | 依据 |
|---|---|---|---|
| N-01 | `outputs` 统一产物表 | clips/derivatives 词汇全库清除，`type` 区分产物种类 | §1 |
| N-02 | `render_status NULL = 未请求` | 不加 `render_requested` 布尔列；NULL 做认领谓词 | §4 |
| N-03 | `StepKind` 用 String 列 + Literal/注册表 | 不做 PG ENUM；新 kind（`voice_gen`/`synth_visual`）零迁移注册 | §5 |
| N-05 | 否决 `ai/` 顶层目录 | 不拥有表、不认领队列、不对应部署单元——按技术风味分组 = `services/` 错误的高配版 | §7 |
| N-06 | 六模块包 + routes 入住模块 | `routers/` 平顶解散，模块自包含（routes + service + 逻辑）；skills/tools 永无 routes | §7 |
| N-07 | `services/` 目录废除 | 18 文件混四个架构层；按层分家（pipeline/chat/skills/tools/memory/platform） | §1、§7 |
| N-08 | 施工图编译定名 `compile_graph` | 裸 plan 歧义（编译的是哪个 plan？）；以产出物命名 | §1 |
| N-11 | plan 必须带限定词，裸用违规 | RunPlan（执行计划，工程层）是唯一在用的 plan（创作层自 N-17 起是素材理解 + 分镜表）；"LLM 提出 plan、executors 执行 plan"是 agent 范式正名；裸 plan（哪个 plan？）违规，`compile_graph` 以产出物命名成立 | §1 |
| N-13 | API 层 job 词汇清除 | `/jobs→/runs`、`job_id→run_id`、`latest_job→latest_run`、`WorkflowRunResponse→RunResponse`：job 在 API 指 run，违反 v2.0"run 不是 job"与 N-11 双重原则（GitHub `actions/runs` 先例）。`workflow_runs` 表与 `WorkflowRun` 类**保留**（Mastra `workflow.createRun()`/GitHub 先例：workflow run 是行业标准执行实例全名；每 run 自带其编译出的 workflow=steps 图） | §1 |
| N-16 | `restore_range` 独立 op 否决 | removeRange 在 spec 内真删 caption cues，独立"恢复删除"op 只能 un-hide segments、复活不了字幕——恢复出来的产物是坏的；恢复语义全归快照层（undo / restore_version，ADR-032 D1/D4）；真要做点选恢复，前置 = clip-spec 契约扩展（cues 加 hidden），属 ADR-016 级改动单独评审 | §1、ADR-032 D4 |
| N-17 | ContentPlan 拆分：素材理解 `MaterialUnderstanding` + 分镜表 `Storyboard`；DerivativePlan 退役为槽位 `StoryboardSlot` | 导演两步走落地（`docs/archive/tasks-done/director-two-step.md`）：理解=素材级（asset-hash 复用），分镜=请求级（每 run 重排）。否决 `TaskBoard`（撞 TaskSpec/TaskItem 词族，N-11 同型三撞）与 ContentPlan 沿用（理解是描述不是计划，沿用旧名不诚实）。"两个 plan 各司其职"注记改写：RunPlan 成唯一 plan | §1、§6 |
| N-18 | `IntentProposal` 升三态（ask 结构化提问） | 结构化 ask 的 payload 与 task_list/edit_ops 正交，判别联合加第三态；freeform 形态（options 空 + allow_freeform）承接反问——反问仍是合法输出，只是有了类型座位（简报 `archive/tasks-done/intent-ask-primitive.md` §2.3） | §1 |
| N-19 | 机制词与用途词分离 | 机制一词一物：`Suspend` 异常 / `waiting` 状态 / `answer` / `bail`；用途住 payload kind（`question.kind` / `spec.for`）；**用途×机制组合词永禁**；配对词整体引入（ask/answer/bail）；状态词从机制动词派生（Mastra 参照） | §1、§6 |
| N-20 | 任务槽 vs 分镜槽分层 | `IntentSlot`（任务链的编译期投影：产物规格一行，住 `spec.slot`）≠ `StoryboardSlot`（派工层：导演怎么排）——两层各有槽位词，混用即违规 | §1 |
| N-21 | `IntentProposal` 升四态（answer 直答态，延展 N-18） | 纯信息直答（能力/进度/解释/闲聊）与 task_list/edit_ops/ask 正交，判别联合加第四态 `AnswerProposal{type:"answer", text}`——落普通 assistant 消息，不起 run、不 dock；与 ask 的边界写死在 agent 规则（无工作请求且无歧义才可用）。沿用 `answer` 词（§1 同概念同名：与 `InferredIntent.action="answer"`、messages.answer 同族）；同一机制收编发布/导航引导，不开新通道（期 4 补四已落代码） | §1 |
| N-22 | 应用区定名 `studio`，workbench/工作台全库退役 | 创作类 AI 产品惯例（ElevenLabs/Suno/Descript/PlayHT Studio）；workbench 是企业 SaaS 语域（控制台味），与 agent/IP 孵化定位不符；studio 无夸大（一间创作的屋子，不承诺结果）。动线闭环：landing 按钮"进入工作室"→ home 接待语"欢迎来到你的工作室"。i18n key `openWorkbench`→`openStudio`，CLAUDE.md 布局节与代码注释同步 | §1 |
| N-23 | 品类词 = agent，空间词 = studio，两层分离 | 品类自称永远是 agent（PRD one-liner "An AI agent for knowledge experts"、hero "We do the rest"）；**studio 只做应用区空间名**（"你的工作室"），永不出现在品类陈述句（"Repurposer is a …"）——避免触发 CapCut/Descript 式工具功能数量对标（外部评审 Kimi 同判：叫 studio 就被拉进工具军备竞赛，叫 agent 比的是交付与省心）。空间名成立前提：房间内永不出现工具货架（多轨/特效/素材库），UI 保持 composer + 卡片、editor 薄化；中文"工作室"双关运营团队（明星工作室 = 替名人运营自媒体的班子），与 agent 定位咬合 | §1 |
| N-24 | 品类词只用 `agent`，角色隐喻（运营官/操盘手/班子）全库退役 | 角色包装是话术 dressing：landing heroSubtitle 自称 "an AI agent"，PRD 曾写 "content-operations officer"——一份产品两个自称，朴素品类词胜出（2026-08-01 用户裁决）。PRD one-liner / CLAUDE.md 定位条 / N-22·N-23 引述同步清洗；"运营官"承载的洞察（用户不懂自媒体、产品指导并孵化其 IP）保留在 CLAUDE.md 定位条，仅标签退役 | §1 |
| N-25 | 自称双轨：对内技术 = agent，对外文案 = assistant/助手（细化 N-24 适用范围） | "agent" 对非技术用户是行话（欧洲用户甚至会读成"经纪人/特工"）；技术实体不变——架构/PRD/CLAUDE.md/代码全用 agent，N-24 的隐喻禁令不变；hero/showcase 等对外文案一律 assistant（EN）/ 助手或代词"它"（zh，zh 优先代词）（2026-08-01 用户裁决）。对外文案中出现 "agent" 字样即违规 | §1、§6 |
| N-26 | chat 流式词族：delta = 散文预览增量，envelope = 终帧信封 | 流式三层各一词：LLM 原始片 = fragment（`on_delta(fragment)` 入提取器）；解码后散文增量 = **delta**（SSE 帧 `assistant.delta`，纯预览，非事实源）；终帧 = **envelope**（`turn.completed`/`turn.failed`，完整 ChatResponse，永远权威）。机制名：`ProseDeltaExtractor`（唯一散文提取入口）、`MiniMaxClient.generate_stream`、service 拆分 `prepare_chat_turn`/`execute_chat_turn`、前端 `streamChat`。禁 chunk/token 混用（chunk 是 HTTP/LLM 传输单位，token 是计费单位，delta 才是渲染单位）（ADR-034） | §1、§5 |
| N-27 | 身份模块正名：Speaker → 人设 / `Persona`；`speaker` 让位素材说话人 | 定位升级后"演讲者"前提崩塌（素材 = 会议/报告/播客，不只是演讲）+ 一词三义（用户身份画像 / `speaker_map` 素材里说话的人 / landing 普通词 speakers）。用户面 zh「人设」/ en「Persona」、代码 `persona`，三层同词族；`speaker` 此后只指素材里说话的人（其分析产物 = `speaker_map`）；**IP = 承诺层词，禁入英文文案**（en 叙事 = personal brand / thought leadership），不进产品内导航（ADR-037） | §1、§6 |
| N-28 | 人设吸收 Brand：`brand_templates` 退役，皮肤 = `persona.brand` | 多人设拍板反转拆分理由（一人多号 = 多人设各带皮肤）；`config` 杂物抽屉三分流——皮肤→`brand` 块、工艺开关（removeFiller/captionEnabled/aspect/fillMode）→配方/计划默认、CTA 唯一家 = `persona.cta`；**`brand` 全栈一词**（人设块 / 烘焙 / clip-spec 段同名）——模块退役词不退役，不引入 `look` 字段名（避免撞 RECIPES §4.4 look 层组合概念）；composer 单身份控件；失去独立表归属即失去模块资格（§7 逆用）（ADR-038） | §1、§7 |
| N-29 | "班组/班底"式自造词禁令 + agent 正名 | 需要解释才能懂的自造词违反 §6；LLM 决策单元直接叫 agent（Mastra/Agno/Anthropic 行业标准词）；旧 `app/skills/`（决策单元目录）解散——决策体共享层归 `app/agents/`（ADR-039 四分）；`SkillEntry.kind`（skill/tool 值）字段退役。（能力层定词后被 N-42 翻案为工具/tool；LLM 禁 import 铁律迁址 `providers/`） | §1、§6 |
| N-30 | Agent 归一：一个 Agent 类 + 声明实例 | 10 个 `xxx_agent` 类的真实差异只有 prompt 模板 / 输出 schema / 调用配置——**多样性是数据不是代码**。`agents/base.py` 一个 Agent 类（harness 漏斗：装配→渲染→调用→校验→修复一轮→计量→声明兜底）；工具私有声明住工具包，共享 crew（director/persona/translator）住 `agents/roster.py`；特殊子类仅流式。领域逻辑归 schema 校验 / 工具包工序（ClipPlans 时长钳制本已在 schema） | §1 |
| N-31 | actor 概念提出后退役不采用 | actor 非世界级框架标准词（Mastra/Agno/LangGraph 词表 = Agent/Tool/Workflow/Node/Step；actor 属 actor-model 谱系）。工具包构成即"谁执行"的答案，不建分类字段；checkpoint 的"等人答"由节点自声明展示词，不立 taxonomy | §6 |
| N-32 | outputs = 工具属性，注册表派生 | 产物类型 = 产出型工具的 `output_type` 属性：`IntentSlot.type` Literal 退役改 str + 注册表校验（§5 延伸到请求层）；`_OUTPUT_TO_NODE_KIND` / `_SKILL_TO_OUTPUT` / `KNOWN_OUTPUTS` / `SLOT_DEFAULT_COUNT` / `SLOT_COUNT_LIMITS` 五处散点全部注册表派生。**新增产物 = 一条注册项，agent 当轮即知**（intent_router prompt 产出类型清单同源注入） | §1、§5 |
| N-34 | 估价函数 `estimate` 住节点；报价 = 图 fold | `cost_hint` 三档（cheap/moderate/expensive）退役 → `node.estimate(ctx)` 估价函数（机械精确价：TTS 按字符/render 按秒；agent token 区间）。报价 = 编译图逐节点求和：全图 = 生成前总价（dock 展示），子图 = 修改单价，配方预设图 = 配方卡估价贴。`workflow_steps.estimate` 增量列 = 计划侧成本，与 `cost` 账簿侧对称（施工图 = 计划+账簿一体的完整化）；actual 校准 estimate 闭环（§4 可空列纪律：NULL = 未估价） | §4、§5 |
| N-35 | kind 与工具同名（N-42 前技能） | 工具包键即节点 kind（`dub`→`dub_clip`、`clips_pipeline`→`select_clips`、`post_gen`→`write_post`、`script`→`revise_script`，alembic 数据迁移）；`SkillEntry.node_kind` 映射字段退役（同物同名 §1，灭一处平行事实）；内部节点名不动 | §1 |
| N-36 | asset scope 会话退役：ChatModal / AssetChatModal 删除，产物对话归 dock + 焦点注入 | 会话只剩 project scope——`ChatRequest.asset_id/asset_type` 删除（extra=forbid，旧调用 422），`Conversation.asset_id` 列留给历史行、新行恒 NULL；产物指认两通道 = @output mention（注册表参考族，确定性 id）+ `focus_output`（每轮携带 `{id,label}`，context 一行 + 落库为用户消息焦点前缀灰行）；随退役的还有 LLM 失败的 revise_script 猜测兜底——ask 反问是唯一失败形态（禁令 #7） | §1、ADR-041 D8 |
| N-37 | 产物请求语法 = 工具链；`IntentSlot` / 簿级修饰符 / 三方合并退役 | outputs 槽位语法诞生于提取族时代（请求层 schema = 产物清单），「给我的视频加字幕」被迫表达为高光提取（任务卡「视频片段 ×2」病灶）。收敛（ADR-043）：意图面唯一语法 = task list（plan path 与 chat loop 同一词汇）；产物 = 编译图的派生投影（`derived` 预览行），类型词汇仍由节点 `output_type` 派生（N-32 不变）；面板编辑 = task list 直接结构编辑，整链 ride prior_intent，chat 恒胜——merge 机械无对象自然死亡；悬空变换编译期 422 指名拒绝（禁静默丢弃）；存量 pending_intent / run.context 行读容忍升级，只读不写 | §1、§5 |
| N-38 | `track` 必须带家族限定，裸用违规 | 轨道四家分（主轨/数据轨/层/块轨，ADR-044）后，"加条轨"在散文与代码里必须说清是哪一家；N-11（裸 plan）同型判例 | §1 |
| N-39 | mention 系统双端注册表化；配方发射 = 预填模板原文 | 配方不是 mention（MENTIONS §3）——发射的全部行为载荷 = 配方卡的预填 prompt 模板（模板点名产出与语言），无 transport 字段、无服务端播种，plan path 与 composer 完全同径（2026-08-11 裁定：配方 = 提示词，ADR-040）；客户端 prior 构造路径禁建，服务端永不见配方身份。提及类型与效果各自注册表化（asset 为成员；recipe 类型成员保留供历史消息 chip 渲染），后续 @ 类型只填注册项，禁类型分支补丁；"硬编码"表述禁——正确表述是"静态注册表，随代码部署"（TOOL_REGISTRY 同款纪律）。（原编号 N-25，与自称双轨判例重号，2026-08-17 改号） | §1、§5 |
| N-40 | 节点 kind `checkpoint` → `interrupt` 更名 | 行业 checkpoint（LangGraph 状态快照供恢复）≠ 我们的节点（提问-等待-续跑的人在环闸）；最近行业词 = LangGraph `interrupt()`（暂停图等人输入，语义全等）/ Mastra `tool_suspended` / Agno approval。更名 `interrupt`（zh 中断）；机制词 `Suspend` 异常 / `waiting` 状态 / `answer` 不动（N-19/N-54 不变）；代码更名已落（命名批 v2 ①：kind 字符串 + `expire_stale_interrupts` 函数族全换；String 列无 schema 迁移，存量全清零数据迁移）；五源词汇坐标见 `research/deepseek-harness.md` | §1、§6 |
| N-41 | agents 花名册标识符 `roster` → `registry` | §1 同物同名：注册表一词全栈同源（TOOL_ / RECIPE_ / MENTION_ / TRACK_ / OP_ REGISTRY 五表），agents 独异；`agents/roster.py` → `agents/registry.py` 已落（命名批 v2 ②）；「花名册」作散文词可留，代码标识符恒 registry | §1 |
| N-42 | 能力层与行业全量对齐（skill→tool 换位）；「技能」退役为营销泛词 | 证据：四厂商同构（Anthropic / MiniMax / Mastra / Agno——skill = SKILL.md 指令包、tool = 可调能力，`research/agent-skills-spec.md`）+ zh/en UI 零命中证实「技能」非用户可操作对象。更名已落（命名批 v2 ③④，零假设 diff 取证过闸）：`app/skills/` 能力包 → `app/tools/`（TOOL_REGISTRY；TaskItem.skill→tool 全量换名，**存量数据全清、零容忍 shim**；plan/intent prompt 目录措辞同步换——对齐模型先验）；原 `app/tools/` 拆 `app/providers/`（外部服务包装）+ 通用件随消费方；`clients/` → `providers/llm/`（Model 缝，含 PRICING；批⑥已落）；空出的 `app/skills/` = 指令包座位（**行业 skill 包格式 + instructions 式装配消费**：装配器按节点条件注入、模型无感，覆盖 = name-wins 整包替换，persona 级 > 平台级；注册表名 = SKILL_REGISTRY 行业本义重生）。zh：工具 = 能力、指令包 = skills 内容、技能 = 营销泛词——**§1 豁免条款立：同词纪律只约束用户可操作对象（配方/人设/计划/产物/@mention），营销泛词豁免**；机械退役为"确定性工具"描述语，LLM 禁 import 铁律迁址 providers/。约束 = 先于指令包动工与内容技能扩展线。N-29 技能一词一义条款翻案 | §1、§6 |
| N-43 | 厚 agent 判词：Agent 类 = 声明式结构化调用，零 autonomy 义是设计 | 按 Anthropic《Building effective agents》分野（workflow = 预定义代码路径 / agent = LLM 在循环里自主指挥自己），本系统零 agent、全 workflow——chat 边缘 = routing 模式，pipeline = orchestrator-workers 模式；`Agent` 类对位 = AI SDK `generateObject`（声明式结构化调用），类名不动；**agent 性在产品承诺层**（厚 agent = 一个 assistant，N-25 双轨不变），业界 autonomy 义永不适用于任何内部模块；开放式 autonomy 永拒不变（ADR-052 判词 1；ADR-039 补记已落） | §1、§6 |
| N-44 | chat 边缘双件 = intent router；director_* → understand/plan；**plan 归两主**（修订） | 业界坐标批（ADR-052 判词 3，**已实施**——更名批 = B1 落地 2026-09-03，commit 级自绿）：`plan_agent` / `chat_intent_agent` → `intent_router`（同概念两相位 prompt，相位 = 上下文参数——Anthropic routing / OpenAI SDK triage）；`director_understand` → `understand`、`director_plan` → `plan`（Plan-and-Execute 正典；「导演」概念退役——它是动词不是角色）。**plan 归两主**（2026-09-15 命名批 v3 ③ 修订原「归一主」裁决）：pipeline `plan` 节点 = planner 义（唯一规划节点）；chat 计划书 = plan path 义（`book path → plan path`、`presented_book → presented_plan` 复活——原裁决把 plan 让给 pipeline 一主，chat 侧造了 book/任务书方言兜底；方言退役后双座分工：两主各有限定语境，跨主引用带限定词）；N-11 裸 plan 禁令 = 「两主之外的 plan 用途带限定词」 | §1、§6 |
| N-45 | `pending_intent` → `pending_brief`（brief） | 对话引擎的结构化状态正名（ADR-052 判词 4——**更名已实施**（B1，2026-09-03），槽位机制 = B2 施工）：intent 是单轮推断产物，brief 是跨轮累积状态——槽位 topic / audience / tone / constraints[] / material_state，每槽带来源 user-stated > inferred > default，代码侧合并；字段 / 派生预览键 / 累积叙事随批换名。**`pending_brief` 列名是存储出身**（v3 ③ 存储冻结的词源判例：列名 / results 响应字段随列冻结，概念词 = brief） | §1 |
| N-46 | 角色名 = 节点 display 属性，工艺叙事默认 | 工作流内部永远函数名（动词族零人格）；用户可见进行态叙事 = 节点声明上的可选展示属性（`task_name` 机制升级位）——默认**写工艺不写人**（「正在剪辑成片…」✓ /「剪辑师正在…」✗）；N-24 禁令对象 = assistant 的班子包装，步骤级工艺叙事是另一层；人形叙事 = 明确翻 N-24 的案（ADR-052 判词 7；**2026-09-03 用户拍板工艺叙事发稿**，人形版维持翻案门槛） | §1、§6 |
| N-47 | 有界 loop 节点 = agent 性的唯一合法座位 | 编译期排不出拓扑的活（搜索 / 阅读）由 `NodeBase` 子类承接：内部 mini tool-loop（工具 = `app/tools/` 注册表）+ 三护栏（迭代上限 / 报价 = fold / 对外 = DAG 单节点）；业界同构 LangGraph subgraph / Mastra agent-in-step / Anthropic agentic component；开放式 autonomy（无界循环 / 自主改拓扑 / 自我 steering）永拒不变——常备否决清单只收编有界形态（ADR-052 判词 8） | §1、§6 |
| N-48 | harness 单义 = 调用面 Agent 漏斗；「剧本 harness」→「剧本测试」（N-33 结案） | harness 行业两义（agent harness / test harness）当年登记并存是"登记歧义"而非杀歧义，防御性命名随 API 测试套件删除多年早到期。结案：harness 只指调用面漏斗（`agents/base.py` + contexts 装配 + prompts）；测试脚本就叫**剧本测试**（`scripts/chat_scenarios.py`），不配概念名——"测试套件"概念永禁复活（去方言批 `archive/tasks-done/de-dialect-question-machine.md`） | §1、§6 |
| N-49 | 提问机器词汇批：词根 question/answer，ask 只剩 action 动词一个座位 | 去方言批（简报 `archive/tasks-done/de-dialect-question-machine.md`）：`AskPayload`→`QuestionPayload` / `AskProposal`→`QuestionProposal`（kind 字段删除——LLM 只产普通问题，task_book 恒由系统举起）/ `AskOption`→`Option` / kind 枚举收敛 `{task_book, question}`（语义分支只有"是不是计划"一处，其余结算全走载荷握手字段：`workflow_run_id`→续跑 / `slot`→回填 / `caption_mode_` 前缀→恢复模式；旧行 "choice"/"confirm" 读容忍升级，只读不写）/ `QaPair`→`AnsweredQuestion`、`qaAnswerText`→`answeredQuestionText` / OpsCard 死码删除。**方言词永禁**入代码与文档：clarify / archive / receipt / eval / primitive | §1、§6 |
| N-50 | 形态律两词 = 文字问 / 选项问；插话 / 提醒尾；「形态切换」「morph」永禁指提问形态 | 提问机器形态律（ADR-053 R1）：问题按 `options` 是否为空分两形——**文字问**（options 空 = 普通对话消息）/ **选项问**（options 非空 = 非阻塞 pill），渲染分流与 kind 无关；**插话**（interjection）= 待决中与问题无关的用户消息（判定是 LLM 的——slot 握手 / `pending_disposition` 三态；结算是代码的）；**提醒尾** = 插话回合回复末尾代码拼装的双语固定句（原问题 + default_path，永不借 LLM 之声）。「形态切换」「morph」只许指 dock 两态形态机与 stadium 半径过渡——指提问形态 = 方言（阻塞形态已拆除，ADR-053） | §1、§6 |
| N-51 | 积分词汇批：credit / wallet / credit_transactions / hold→capture→release / grant / purchase / payment；settle / claim / pay / ledger 表名 / entry 永禁 | 积分系统命名（ADR-055，行业坐标 = Stripe authorize→capture→release / Modern Treasury ledger transactions）：**credit**（积分 = 用户面唯一计价单位）；**wallet**（余额 + 判定）；**credit_transactions**（台账行——ledger 保留为子系统概念名不上表名，行 = transaction，entry 是双 entry 会计第三层用不到）；扣费时序 **hold → capture → release**（预扣 → 实扣 → 释放剩余——settle 是银行间清算语境、claim 是用户发起的收款动作方向相反，均禁）；**grant**（授予：开户 / 订阅周期 / 补偿）/ **purchase**（购买，W11）/ **payment**（名词位；pay 是动词只留函数名）；比例参数 `credits.per_cost_usd`（消耗比例 ≠ 购买比例） | §1、§6 |
| N-52 | 方言词退役全表（命名批 v3，ADR-077 判词⑥ T4）：verdict → tool call/action；提问机器 → ask_user；`BriefLedger` → `Brief`（账本修辞退役）；任务书 → plan/计划（book path → plan path） | 工具 loop 落地后方言词成批退役（每 commit 冷启动自绿、零行为变化）：① chat 意图域 verdict 全扫为 tool call / action，「提问机器」散文退役为 ask_user 机器/the ask_user machinery——**保留**：pipeline 质检/run 真值域的 verdict（run verdict / 质检裁决 / researcher·judge 义，与 chat 方言无关）；② `BriefLedger` → `Brief`，账本修辞全退——**保留**：言语账本（tool_loop 言语隐喻）/ 计费台账（BILLING 义）/ judge 台账；③ 任务书 → plan/计划，深度 = 用户拍板「标识符+prompt+文档，存储冻结」——**冻结存储字**：`question.kind="task_book"` 及其比较/枚举、`spec.role="task_book"`、`projects.pending_brief` 列与 results 响应字段（N-45 存储出身）、`spec["task_book"]`/`"book_summary"` 键、`plan.j2` 的 `task_book.slots`；存储镜像家族文件（graph_fill / graph_store / registry / test_graph_wiring_pure）整文件不动。**「brief 账本 → session state」评审被拒**（2026-09-15 用户拍板：brief 保留——session state 撞 auth/工程语境，brief 已是行业词）；「任务书→plan」plan 归两主（N-44 修订）；i18n `results.canvas.taskBook` → `plan`（zh「计划」/ en "Plan"，画布名词节点与确认面同词，2026-08-19 两词分工裁决翻案） | §1、§6 |
| N-55 | 探索产物词族注册（ADR-088/089）：Candidate Set / Select / Content Plan / Execution Scope / Decision Package / Confirmed Scope Snapshot / journey / exploration artifact；prototype 第四值 = `exploration` | 旅程四拍板（2026-09-22）：**Content Plan ≠ Task ≠ dock 计划书**——三主并立期各带限定词（Content Plan = 产品语义方案 / task_book = dock 计划书 / Execution Scope = 编译产物），ADR-089 §8 退役弧收口后 Content Plan 唯一「方案」座位；**`journey_id` 是归属属性永不成图边**（R24）；**`exploration` 一词专指探索产物族**（prototype 第四值），不挪作「agent 在探索」的行为描述（那是 work session / discovery goal）；brief 不被新词族触碰（N-52 不变）；canonical vocabulary 冻结：Candidate Set / Select / Content Plan / Execution Scope——Task / Plan（裸）/ Brief / Workflow 互相越界 = 违规；**iter-1 落地注记（2026-09-22）**：`graph_nodes.type` 词表 v3 第八值 = `exploration`；`spec.exploration_kind` 线词 = `candidate_set` / `select` / `content_plan`；探索双状态机词 = `draft → ready → revised → compiled → superseded`（R18——与执行状态机词不共享 chrome）；工具动词族 = `propose_candidates` / `propose_selects` / `propose_plans`（harness 级 EXPLORATION_TOOLS，生产接线 = 迭代二 R6）；`tolerate_null_keys` 升为公开助手（schemas，读容忍牙① 的共享座位） | §1、§6 |

| N-56 | compiler-only 公民先例（注册表第三轴 `llm_visible`）+ Content Plan 产出字段补齐（`aspect` / `dub` / `caption_mode` 词表化） | 迭代二拍板项①（2026-09-23，产品先行裁决——用户需求 → 产品语义 → 编译 → 执行能力，禁从现有 runtime 反推产品语义）：① clip 编译目标 = `cut_segments`（出生能力，runner 模板 = `materialize_source` 零-LLM 配置推广到 N 区间；编译器永不编译 select_clips 不变）；② 注册表新增 `llm_visible` 轴（与 OP_REGISTRY 同词）——dispatchable 但永不投影 prompt 面，「注册表合法 ≠ agent 可见」从此结构化（防执行世界经 tool catalog 偷偷长回第二个发现者）；③ PlanOutput 产品语义缺口三补：`aspect`（画幅枚举——出生参数座位，clip-spec 出生定型、无下游改画幅能力）、`dub`（配音布尔——拆开「法语字幕 vs 法语配音」的 language 歧义）、`caption_mode` 收窄受控词表（bilingual / source_only / target_only，对齐 TaskSpec 既有词表；收窄窗口 = R6 生产接线前，探索工具仍 harness 级、无生产行） | §1、§6 |

| N-57 | 迭代二词族：`source_span` / `scope_compile`+`compile_plans` / `ScopeCompileRejected` / `confirmed_scope` / `revise_plan` / `chat.explore.*` 活动键族 / dock 决策包载荷键 `plans` | 迭代二拍板项②~⑦（2026-09-23 词表先行）：② **`source_span`** = CopyWriterParams 可选源区间（`{start, end, asset_id?}`——asset_id 为编译期显化的确定性解析座，contract 字面 `{start,end}` 的最小扩面）；③ 编译器座位 = `app/pipeline/scope_compile.py` 纯函数 **`compile_plans`**（Content Plan → TaskItem[] 唯一编译座；**`ScopeCompileRejected`** = 域拒绝族第三词，WiringRejected / ExplorationRejected 同族——域拒绝 = 回环修复信号永不 500）；④ **`confirmed_scope`** = run.context 的 Confirmed Scope Snapshot 键（N-55 概念词的存储座位；confirmed_via 词表 = `dock_pill` / `chat_reply`）；⑤ R6 生产注册形态 = **`exploration_chat_tools()`** 投影（propose_candidates / propose_selects **非终态**、propose_plans 终态——R2 免费探索区一回合连续工作的 loop 形态；harness 级 EXPLORATION_TOOLS 全终态形态不变）；⑥ **work session 活动键族 `chat.explore.*`**：`searching`（search_transcript 的 activity_key 改籍——同一读、工作会话词表取代泛化 inspecting 词，done 镜像 = `searchingDone`，与 inspecting→inspectingDone 同律）+ 里程碑三键 `candidatesReady` / `selectsReady` / `plansReady`（门调用成功处一发 completed 帧，ActivityFrame 增 `count` 可选字段——白名单扩列仅此一键，user-safe 纯计数）；⑦ **`revise_plan`** = 探索终态动词族第四词（plan 级修订唯一动词；同一行修订无版本树——`revision_of` 永不建）；决策包 = `question.kind="task_book"` 载荷增 **`plans`** 键（阅读层），存储字不更名（N-52 不变），tasks 证据层 / 费用五面既有座位不动 | §1、§6 |

| N-58 | 迭代三词族：`revise_output` / `revise_selects` / `run_review` / `get_artifact` / `plan_task_map` / `at`+`duration_ms` / `mark_compiled`+supersede-继任 | 迭代三拍板项 E10（2026-09-23 词表先行）：① **`revise_output`** = craft 级修订动词（ADR-089 §6：购买信封内的 how——指认 + 用户的话 → 语义层路由 → classifier 裁决金钱态）；chat path 专用终态工具（pre-run 无已产出对象，pre-run craft 诉求归 revise_plan outputs 重述）；args = `{target: {plan_ref?, output_id?}, instruction}`，指认二选一、全空 = ask 反问，读容忍牙同族；② **`revise_selects`** = 选择修订动词（Select 成员替换：member_index 编辑 + bounds 重校验 + idem 保留，select 首个 revised 写者）；三金钱态（dock 前零仪式 / dock 后原地更新同确认座 / run 后迷你包重确认）；plan path + chat path 双注册；③ **`run_review`** = 兑现审计纯核模块（`app/pipeline/run_review.py`，ADR-088 §8 R21）：确定性兑现事实清单（产出类型/语言/时长 vs 裁切区间/字幕轨/配音存在性/outputs.quality/实扣 vs 报价），零 LLM——**与图内质检 `verify` 分词**：verify 住执行图（节点），review 住 chat 边缘触发回合（收官注入）；④ **`get_artifact`** = perception 族 read（按 id 读探索产物/产物的 user-safe 全字段，ADR-088 §7 read 洞销账）；⑤ 快照键 **`plan_task_map`** = confirmed_scope 增键（plan_id → compiled task 序号区间，R20 修订路由器的映射基材；additive，legacy 快照无键 = 读容忍降级指回 @output 通道）；⑥ 活动帧键 **`at`**（帧出生戳，全帧）+ **`duration_ms`**（completed 帧耗时）——wire 白名单 additive 扩两键，不扩 summary/详情载荷（E7 诚实边界：无载荷的行不假装可展开）；⑦ 探索双态写者语义：**`mark_compiled`**（探索写门新分支：Start 落戳成功后同事务把本包 plans 行 state → compiled）/ **supersede-继任**（post-run plan 级修订 = 旧行 → superseded + 继任行（新 id、同 journey、revised spec）——`revision_of` 指针不建，N-57 无版本树律不变；`compiled → superseded` 是状态机词表内路径） | §1、§6 |
| N-59 | 精确编辑迭代词族：`edit_output` / `quote→range` 解算器 / `work_id`+`archived_at` / 归档不变量 / `confirm_strategy` | 迭代拍板项（2026-09-24 词表先行，ADR-090/091/092 + 简报 `archive/tasks-done/precise-editing-iter.md`；Final Hardening 同批修订）：① **`edit_output`** = 精确编辑受控终态工具（chat path 终态动词族，propose_*/revise_* 同族，B1 起 = Agent 编辑唯一入口）：args = `{target:{output_id?, plan_ref?}, params:{quote?, seconds?, style?, title?}}`——**无 `kind` 字段，动词由恰填其一的参数唯一解码**（`edit_kind_for_params`），MVP 四件 = `remove_range` / `set_trim` / `set_caption_style` / `set_title`（21 原始 ops 永不进 LLM 词表，chat 写门 llm_visible 纵深校验）；指认骑 @output pin（B4 钉恒胜：恰一钉服务端强制）或 plan_ref、全空 = ask 反问；与 revise_output 分工判据 = 变更是否可机械执行，判不准 = 域拒绝回环；② **`quote→range` 解算器** = `locate_span` 升格的 edit 面确定性服务（LLM 只给 quote 文本，range 归代码解算；置信谱：数值引用 > marker 匹配 > 全文唯一 > 多义/未命中 = 域拒绝回环）；③ **work/version 两身份**（ADR-091）：**`outputs.work_id`** = work 物理锚（出生新 UUID、**rerun/wipe 诞生的新版本行按位继承**——精确编辑是版本内原地 operation，永不产新行）+ **`outputs.archived_at`**（可空时间戳律，NULL = active；读面默认 `archived_at IS NULL` 过滤——`outputs.status` 既有列是 generated 遗迹，不复用，S1 施工修正）；④ **归档不变量** = 「交付后的产物历史不可销毁，只可归档」——wipe 点（select_clips wipe / derivative sweep）只准写 `archived_at`，verify 回退保持物理删除（生产中途例外）；`POST /outputs/{id}/restore` = 同 work 内 archived_at ↔ NULL 换态（至多一 active；归档行其余写门全 409 不可变，B2）；⑤ **`confirm_strategy`** ∈ `always` / `large` / `never`（ADR-092）：users.settings JSONB 键 + configs `billing.confirm_large_threshold` 参数；确认闸形态 = plan dock 披露强度分级 + CTA 显价（零新增手势） | §1、§6 |

## 4. API 命名

- REST，复数资源，动作用子路径：`POST /outputs/{id}/render`、`POST /outputs/{id}/dub`。
- 不为单个动作造 RPC 式端点（`/api/sendChat` 此类永不出现）。
- 内部类型（如 `material_understanding` / `storyboard`）不得从任何公开响应漏出——统一经 `visible_outputs_stmt()` 过滤（ADR-030 D1）。

## 5. 命名审计触发点

以下情况必须做命名审计并在任务简报中列出结论：

- 新模块 / 新表 / 新工具 / 新指令包准入（§7、§8）；
- 大规模重构（判例 N-06 的重构简报附带全库审计）；
- 发现同名不同物（如 `routers/intent.py` vs `agents/intent.py`）或同物不同名（如 `music.py` / `music_generation.py` 的职责切分）。
