# Chat Architecture — Agent Interface 层

> Status: 当前规范（2026-10-25）。`POST /chat` 是唯一意图表面，计划构建/修订/确认并入 plan path；会话层使用 ADR-077 有界工具 loop。实现与 live 验收欠账归 `PROGRESS.md` 和当前任务合同。
> 上游决策：ADR-028（RunPlan）/ ADR-029（plan 级 dispatch）/ ADR-030（产物统一）/ ADR-032（edit ops）/ ADR-039（四层工程地图与 `TOOL_REGISTRY`，见 §4）/ **ADR-057（图即产品对象）——图结构变更统一为 wiring ops（add_node / connect / edit_prompt / delete_node / run(_subgraph)）并经 `apply_wiring_ops` 唯一写口；Chat 与确定性卡面动作都是合法消费者。产物级精确修改另走 Operation Model，不把两家族混成同一写口** / **ADR-077（会话层工具 loop 化）——动作 union 机械翻译为终态工具集（§3），护栏搬进工具执行内，读工具一族 = 世界的读法（§3.4），触发回合 = 主动说话（§8.8）；生产层 DAG 与执行写门不因此被绕开，执行 loop 永拒（§12）**
> 命名遵循：`docs/NAMING.md`；模块归属：`docs/MODULE_ARCHITECTURE.md`（Agent Interface：conversations/messages）；chat/ 包是本文的代码家。
>
> 关键形态事实：
> - 拓扑约束用 `requires`（输入校验）+ `after`（顺序约束）表达（AGENT_ARCH §4  NodeBase）。
> - `synthesize_talk_video` 已登记但未实装（`seat=True`，不可派发）；目标合同归 R5 `docs/tasks/synthetic-talk-video.md` 与 RECIPES §8。
> - 提及系统 = 双端注册表架构（前端 `MENTION_REGISTRY` + 服务端解析注册表，方针 MENTIONS §4）；配方不是 mention——配方 = 提示词（ADR-040）：发射的全部行为载荷 = 预填模板原文，无 `recipe_id` transport、无服务端播种，plan path 与 composer 完全同径（chat 修订永远赢）。
> - SSE 统一由项目页 dock 打勾流消费（`useRunEvents` / fetch-event-source；无 `?overlay=` 路由参数与 fullscreen 壳——processing 项目直达项目页即 attach 活 run，ADR-051）；step 状态枚举含 `waiting`（HITL/suspend-resume，§8.5）。
> - **ChatDock 两形态机**（ADR-051/056）：项目页 chat 外壳 = 一台消息机器两种布局形态——**full** = 居中全屏 chat（消息舞台占满页面上部；每个项目的 pre-world 形态，**移动端恒驻此形态**——< iPad 宽度无画布〔prohibition #13〕，chat 舞台即页面，产物经消息流内交付：终态收据 + 锚卡，ADR-118；桌面用户可经 设置→通用→工作区布局 = 纯对话 恒驻此形态，ADR-143）；桌面图世界到达同一拍 morph 为 **panel** = full-bleed 画布上的雾面 overlay（双停泊几何 header 切换，FLORA "Dock panel" 对齐：float 默认 = 右锚浮窗〔垂直 ~18%/10% 内凹、底偏重，非全高 sheet〕rounded-2xl；docked = 靠右齐边全高 rounded-none，dock-surface 磨砂画布恒在其下，localStorage `repurposer-panel-mode` 持久；解剖 = 细长 header〔标题 + 几何切换 + minimize〕+ scroller 主体 + 底寄存〔提问/计划 pill → 免责行 → 输入组恒 rounded-xl〕；页面经 `onPanelStateChange` 感知 hidden+几何，**仅 docked 态**把画布 zoom pill 右移让位——float 不触顶角）；桌面驱动 = `workspace_layout=auto` 且 PLAN-READY（ADR-111——dock 计划落章、draft 图就绪即画布 reveal，full→panel 同拍翻转；图先展示后运行的投影子【计划落流 / bail 成功即经 `onDraftGraphChange` 触发页面 `fetchGraph`】为 reveal 帧备齐内容）；纯对话或移动端不 reveal 画布；loading 闸定态，水合首帧永不重播。可见性态：panel 两态 = open / minimized——用户手势收成右下角 LogoMark 点；唤回 = agent 发声 / 待决提问（只能藏静态输入组，藏不住新信息）；**float 态该点常驻 = 切换钮**，开/收双向，docked 态右下角归 send 钮、点仅 minimized 出现。**保草稿承重结构**：单一 root + 恒渲染 card 容器（full = `contents`、panel = 浮卡）+ 底排恒定子索引 → MentionEditor 跨形态翻转永不 remount，DOM 草稿 + chips 零丢失；scroller 单挂载律 = stage 一槽常驻（full 的舞台 = panel 的主体）。组件 = `components/chat/ChatDock.tsx`。

## 1. 定位与三条原则

Agent Interface 是六层模块图里"意图 → 执行"的唯一入口。用户的三张脸——composer pills、composer 自由 prompt、chat 对话——在它这里汇成**一条机制**：

```
task list（LLM 提议）→ compile_graph 校验/排序/补默认（代码裁决）→ workflow_steps（施工图）
```

1. **LLM 提议，代码裁决**。LLM 只出"干什么"（task list），拓扑正确性（tool 是否存在、顺序是否合法、参数默认值）全部归 `compile_graph`。LLM 永不直接写 node spec。
2. **有界工具 loop，轮间才是对话循环**。每条用户消息 = intent agent 的一回合有界工具 loop（`agents/tool_loop.py`；信道 = 原生 tool calling，线格式按 provider 能力分层）：模型一轮可读世界（读工具一族，§3.4），**终态工具一调即停**（§3）→ 计划/提案 → 编译 → 跑。无界 ReAct 与执行 loop 永拒（§12）；"循环"的大头仍发生在对话轮次之间。
3. **composer = chat 的第一条消息**。composer 发送 = 建项目 + 上传素材 → 直达项目页 ChatDock（无 overlay 路由参数；auto 桌面布局在草稿图就绪后再 reveal 画布），草稿经 router state 交付 dock 作为第一条 `POST /chat` 消息发出（mentions + `persona_id` 随行）；空指令由前端本地拦截（toast）——compile_graph 只接受任务链，full scope 无 tasks 直接拒生。纯 prompt 发送不建资产：消息是「用户自己的内容」还是「请求」由 intent router 判定（LLM 判定，禁长度启发式）；判定为内容（贴入的文字稿/草稿，有无 "this is my…" 框架皆可）即提升为真实 transcript 资产（`create_transcript_asset_from_text`）；无资产无贴文的生成请求得到要素材的回答，永不无中生有计划。

## 2. 一次对话指令的完整生命

```
用户: "去掉口头禅，剪 3 条高光，加个音乐"
 │
 ▼
chat/service.py ──► intent agent（有界工具 loop，带 §6 上下文）
 │                   输出 task list（提议，无执行权）:
 │                   [{tool:"remove_filler"}, {tool:"select_clips",params:{count:3}}, {tool:"add_music"}]
 ▼
TOOL_REGISTRY             校验：tool 已注册？参数过 schema？
pipeline/orchestrator  compile_graph：拓扑排序（配乐殿后）+ 补默认值
 ▼
workflow_steps（动态 DAG，3 步骤 + render fan-out）── worker 认领（SKIP LOCKED）
 │
 ▼ 执行中
node.spec.summary = "Removed 12 fillers · 3 repeated takes"（量化摘要，§8.5）
 │  经 SSE 推送（§8）
 ▼
打勾流逐行亮起 → outputs（render_status=PENDING）→ Remotion → MP4
 │
 ▼
收官内容回复（真实 delivered/partial/failed + 必要失败或差异，§8.7/§8.8）
 │
 ▼（下一轮：改现有产物而非跑新任务）
"第二条再短一点" ──► intent ──► edit ops ──► Operation Model（§9 边界）
```

## 3. 终态工具集

intent agent 的回合 = **有界工具 loop**（`agents/tool_loop.py` 的 ToolLoopAgent；线格式按 provider 能力分层——原生 tool_calls 为主，action-JSON 地板兜底）：模型一轮可调用读工具看世界（§3.4），**终态工具一调即停**。终态工具 = 动作 union 的机械翻译（type = 工具名，字段 = 参数模型，ADR-077 判词②），Pydantic schema 强校验。声明归 `chat/turn_tools.py`（模型面描述 = 何时调 / 调用做什么 / 调用前必须先说什么），执行住回合 runner（`plan_turn.py` / `propose_turn.py`）——**护栏在工具执行内，不在 loop 外**。

```jsonc
// plan path（首个 run 前 / 有计划待确认）——PLAN_TOOLS
present_plan    呈现计划：计划 dock 待确认，自身永不起 run
ask_user        提问：问题 dock 带选项，作答 / 安全跳过续会话
start_run       起已确认计划的 run（唯一出生地，零旁路）
answer          纯信息直答：言语即回复，无计划无提问无 run

// chat path（有 run 的项目）——CHAT_TOOLS
propose_tasks   提议新任务链：链校验在执行内（必要时先 dock caption 选项问）→ 计划 dock 待确认——同 turn 永不起 run，run 只在显式确认后出生（ADR-087 §4 B3）
edit_output     精确编辑现有产物（ADR-090 受控终态工具，Final Hardening B1 唯一入口）：MVP 四件 remove_range/set_trim/set_caption_style/set_title，动词由所填参数唯一解码；target 骑 @output pin（B4 钉恒胜：服务端强制）或 plan_ref；quote→range 由解算器确定性裁决（→ Operation Model，§9）
edit_graph      修订持久图（wiring ops）→ apply_wiring_ops 唯一写口 → 已批 scope 内 continuation 自治重填 / 扩张·unproven 回滚转 dock（ADR-087 §4 D4，B2）
ask_user        提问（同 plan path 形态）
answer          纯信息直答（读数先调 get_run_status）
```

提案类工具（present_plan / propose_tasks / edit_graph）的参数带 `summary`（打勾流标题文案 + 消息记录里"这轮干了什么"的人话存档）与 `name`（命名作品不命名工具——展示文案二源律之首，ADR-058）。**被拒的调用什么都不写**：校验拒绝（registry / 门槛 / 死链）就是 loop 的反馈，模型下一迭代重拟——修复轮不再有独立信道。

**Film 是 `edit_graph` 的版本闭环例外**：对既有 `launch_film` 节点的 `edit_prompt`，以及解析后含 `launch_film` 的 generic wiring run，都在 graph savepoint 提交前拒绝；通用 chat run dispatcher 以同一 guard 后挡。Film 修改必须回 `design_storyboard` 形成并呈现新版本，再经既有提案、报价与 versioned Start 执行；普通非 Film wiring 的 continuation/dock 不变。

**重复拒绝 ≠ 必须烧满迭代**：ToolLoopAgent 接受调用方注入的同步 `should_stop_rejection`；当前 Chat 只对 `design_storyboard` 使用该策略——同签名（工具名 + kind + detail）第 2 次拒绝即停，不同签名仍修复，但同回合累计第 3 次 Film 设计拒绝也停止。结果以 `LoopResult.no_progress_tool` 独立标记，不伪装 budget exhaustion，不发 `LoopExhausted`，也不再生成下一次调用。两条 finish 路径落普通 assistant 终态消息，明确本回合是否已有保存版、未开始新制作、旧内容保留；其他工具保持原有有界修复。这个每回合失败预算不清零、不替代统一嵌套 LLM 调用预算。

### 3.1 plan path：计划的构建 / 修订 / 确认

`/chat` 是**唯一意图表面**。`chat()` 在 autoResume 之后按状态分派：project scope 且（有待确认计划行（kind=task_book）/ 刚回答了带 `slot` 的提问 / 无任何 run 且 `pending_brief` 为空或是 brief-only 行）→ **plan path**；其余 → chat path 提案工具集。

plan path 的推理者是 **intent router**——有界工具 loop（`plan_turn.py`；终态工具 = 四动作的机械翻译，ADR-052 B2 的动作集不变）：

- `present_plan` → reasons 推导（chain_default / clip_count_default / clips_without_media / text_without_material）→ **derived 预览**（ADR-043：服务端干跑 compile_graph 产出「你将得到」投影行，随 pending_brief 持久化）→ `sync_task_book_question` dock。**计划载荷 = 工具链（task list），无合并机械**：阅读面 = 当前累计方案 + 真实草稿图 + dock echo，不恢复第二套厚任务列表编辑器；受控卡面直改走 `POST /projects/{id}/graph/revise`，chat 修订携带当前累计方案与图上下文重提整链、重新校验，chat 恒胜。**整条源规则**（ADR-043）：「给我的视频加字幕 / 配音」类请求 = 变换工具单独成链，永不夹带 select_clips——编译期自动注入内部节点 `materialize_source`（确定性全段 clip-spec，无 LLM 选段；出生地画像分发：media 直挂 preprocess / stills 先 align_stills / 项目有既有 clips 不注入 = 作用于现有 clips / 无源可作用 = 编译期 422 指名拒绝，永不静默丢弃）
- `ask_user` → **一等动作直通 dock**（ADR-052 B2 D2-C1，caption-mode 特例泛化为正典）：`_dock_question` 选项问形态，payload 带 `slot` 握手（作答由 autoResume 选项命中或 slot 握手判定回填 brief 槽位 user-stated，回 plan path 重判——ADR-053 R2）+ `default_path`（跳过即走默认路径出计划——× / bail 取它、提醒尾消费它；散文织入它做可见面，见下条解剖）。brief 合并落 brief-only 行（`intent=None`，桌上计划原样保留）。同槽位重问被代码翻回 present_plan——问环有界。**ask 三分解剖（Claude Code 提问形态对齐）**：① **框架散文**（`prose`——认领请求 + 为什么这一问最决定质量，1~2 句，言语先行）= 回合的 echo，走 `assistant.delta` 通道流式入流，落库为问题行 `content`（echo 实体化同律）；② **裸问题**（payload `question` 字段）= dock 标题 / QA 归档问句 / 提醒尾引文 / pending 上下文块，四消费点统一读它（旧行空值回退 `content`，读容忍）；③ 选项 + 铅笔行不变。散文缺字段（code 组装问：caption-mode / 方向 interrupt / verify 降级 / topic 门槛问——全部补 stamp `question=`）时 `content` = 裸问题，前端以「content ≠ payload.question」判定有无 echo；**文字问**（options 空，永不 dock）的 `content` = 散文 + 裸问题双行（消息本体即全部提问，`_ask_content` 单点组成）。**default_path 零可见面**（ADR-103）——散文零宣告、dock 零渲染，× 承担跳过手势，提醒尾消费 default_path 原文。
- `answer` → 普通 assistant 消息，stored 计划不被动
- `start_run` → 复用 answer kind=start 路径起 run（唯一出生地）；dock 中的计划以 `presented_plan`（整链）注入推断上下文——短确认看得见自己在确认什么

**plan 门槛（ADR-052 B2 D2-C2）= `present_plan` 的执行内校验（护栏搬进工具执行内）**：计划只在 brief 有根时 dock——根 = topic 有值 ∨ material_state ≠ none ∨（tasks_explicit ∧ specific_instruction 非空，即明确点名的落地配方）。无根 → 执行拒绝回环，代码组装 topic 问一轮（choice dock，slot=topic，asked 簿记防重问）；问过仍无根（或用户跳过提问）→ 接受并带 draft-from-persona 声明 dock：`draft_from_persona` reason + 代码组装 echo 散文声明（「按你的人设风格起草了这版——直接开始就行」）；media-needing 链 ∧ material none ∧ 桌上无计划 → answer 素材引导（上传或贴文），永不 dock——零素材反问网与 copy-writer 无素材 lift 同由这门承载。

修订回合的累积状态 = **brief**（ADR-052 B2，取代累积 prompt 拼装）：topic / audience / tone / material_state 标量槽各带来源 + constraints = 来源化条目数组（**ADR-064 顺形律**——模型第一直觉写法 = 正典形状，一约束一对象；合并 = 键控并集：`_constraint_key` 归一化 + 逐项来源优先级 + 存储序追加；标量槽照旧 user-stated > inferred > default——LLM 每轮提议全量更新，代码 `merge_brief` 按来源优先级合并：user-stated 永不反向覆盖、重申恒胜；`asked` 簿代码自持防重问，永不吃 LLM 提议；material_state 代码钢印 post-merge 无条件覆盖——attached / pasted / none 看项目事实不看 LLM）。**校验分层律（同 ADR-064）**：严格度 ∝ 关键度——关键载荷（终态工具的核心参数，驱动付费运行）严格 + 拒绝回环；brief = 咨询性记录，归一化后仍无法解析 → 丢字段 + structlog，回合照活（记录错永不杀回合）。`pending.prompt` = 出生 prompt 冻结于首次 dock，无累积 prompt 上限字段，composer/前端永不构建累积 prompt 或 prior。intent router 的装配面（`_assemble_plan_turn`）：本轮消息 + **brief 块**（值槽带源 + material 行恒在 + asked 簿——根判断与防重问读它）+ 文件名 / file_language / material_excerpt + `presented_plan` + 最近 5 轮对话（"Recent conversation"——素材/请求判定需要看见上一轮上下文；只喂上下文不加倾向规则，判定归 LLM 凭语境完成）。intent router 的 provider 故障不兜底：MiniMaxError 直接穿透到 chat 路由边界——SSE 终帧 `turn.failed` / JSON 502 都带 `user_error_line` 本地化行（provider 错误人话化梯），永不 dock 编造默认计划（错误计划看着像真的，Start 会为它烧一次付费 run）；`tasks:null` 等松散输出由 schema 读容忍接住（存量 outputs/簿级修饰符形状的 pending_brief 行同机制升级，只读不写）。**失败行的呈现 = 入流灰行**：turn.failed 的本地化行渲染为消息流里的灰色 MetaRow（TurnErrorRow），永不用 toast——回合失败是对话里的事实，不是外加 chrome。已提交的用户行、活动与失败记录按各自事务保留；未提交的主回合事务回滚，不得把失败描述成“整个回合零提交”或“历史上什么都没发生”。run 级失败同理无 toast——失败步骤行已带人话错误入流。

### 3.2 工具边界规则

**answer 边界**：用于能力/进度/解释/闲聊，以及网站介绍片的创作方向沟通阶段；要干活 → propose_tasks / edit_output / edit_graph；读数有歧义 → ask_user——answer 永不当偷懒出口。进度问题先调 `get_run_status` 照实答；发布意图 → 引导到产物卡发布按钮；品牌/说话人等身份设置 → 导航到对应页面。

**answer 契约**：`{kind: "option"|"freeform"|"bail"|"start", option_id?, text?, answered_at}`。bail 是一等公民——入口回 present_plan 可重开、checkpoint 下游级联 skipped，**永不标 failed**；`start` 是计划确认的一等 kind。请求体 `AnswerRequest` 是按 `kind` 判别的联合（option/freeform/start/bail）——`intent` 只存在于 `start` 上，其他 kind 带 kind 外字段直接 422；计划行（kind=task_book）只接受 start/bail，其他问题不接受 start。N-14 的"tasks=[] 反问" = ask_user 的 freeform 形态（options 空 + allow_freeform）——反问仍是合法输出，只是有了类型座位。

### 3.3 intent router 顾问姿态

来源：一份真实顾问对话样本（用户 = 目标画像：有素材、不懂自媒体、助理也不懂）。plan path 不只是填计划——**用户到来即彷徨，agent 是接住彷徨的人**（哲学论证 → STRATEGY §5）。四条行为规格：

1. **每轮一问、每问可一词答、默认路径恒在**（ADR-052 判词 5，可见面 = ADR-103）：提问只问决定质量的缺失槽（听众 / 目的 / 场合——答案会改变计划形状的问题），不问用户不懂的（画幅 / 参数 / 样式，由配方卡与默认值吸收）；决断问选项 **≤3** 一词可答（真二元抉择降 2；三选项节奏对齐 FLORA/Opus）、探索方向问放宽到 **≤5**（双族律 ADR-116；分族节奏只在 prompt 座位，harness 守结构外界 1–5）+ freeform 恒在；每个 ask_user 恒带 `default_path`——**每个问题都可安全跳过**，跳过即走默认路径出方案（draft-from-persona）；默认路径机器可读、零可见面（散文零宣告，ADR-103）。诊断是手段，出方案是目的——**不做职业 / 变现咨询**。
2. **带理由纠偏**：用户点的东西做不出或与素材不匹配（无 media 要 clips、两小时讲座要 20 条）→ 拒绝 / 降级时必须给理由 + 替代方案，禁静默排除（现状 `clips_without_media` reason 是雏形，升级为建议形态）。
3. **成功定义随计划**：dock 的计划摘要携带"什么叫成了"（本批产物的验收口径），schema / overlay 同改，结果页对照呈现。
4. **按素材画像推荐配方**：输入画像命中某张 live 卡时主动说"照这张卡做"（读 `RECIPE_REGISTRY` 公开面；reserved 卡永不推荐——点亮纪律不变，RECIPES §4 / §4.8）。

验收：迷失用户横切（`scripts/chat_scenarios.py` S1——裸愿望 → 主题问 → 作答 / 跳过 → draft-from-persona 计划；迷失是用户状态不是意图类别，plan 门槛主径即迷失主径）。

### 网站介绍片的方向与分镜阶段

普通网站求片首轮先读取网页，回复真实内容与一个可判断的创作方向，用普通 `answer` 消息询问是否按该方向设计分镜。plan path 装配时把消息里的 URL 当场建成采集资产（`prime_web_page_captures_from_text`——独立事务落库，方向对话期间后台采集；`answer.material_urls` 模型声明座仍在）；本轮无 film 计划、无分镜调用、无 run。用户接受或修订方向后才提案 `launch_film`；明确要求直接设计分镜、已给定方向并授权继续时直接进入提案。方向对话不属于执行/费用确认，不修改用户偏好；短确认只有在执行计划已呈现时才可进入 `start_run`。两条意图路径共享 `_website_film.j2`。

分镜准备沿现有 phase 通道报告 `capturing` / `storyboarding` / `storyboard_revision`，细化通用 draft 状态，心跳不覆盖阶段。采集等待与候选生成各有自己的预算（采集排干上限 1800 秒——子页发现链以分钟计；候选生成与返工共用 **1800 秒**）；dock 准备的总兜底 = 两相预算之和加装配余量，永不互相挤占。采集等待超时 = 诚实失败（`FilmCaptureTimeout` / `film_capture_timeout`），禁止带着采了一半的世界静默起草。对话设计超预算或没有合法候选时同样诚实失败并保留当前已呈现版本，**不得用固定分镜兜底**；`fixed_direction` 仅限 worker 无人值守的首次生成道，边界见 Film 总设计 §7.4。展示与渲染继续消费同一份定稿。

工作段 = 两段用户可见散文之间的连续模型等待与工具活动；工具完成只落定段内证据，不收口工作段。当前段在同一时间线单元上从「思考中… / 正在…」原位变为「工作了 X 秒」，其下再显示正文；段边界、首显与计时口径见 §8.6 / ADR-110。实时与回放共用折叠投影，但回放缺少客户端首显事实时只报告可观察活动跨度，不补造整段耗时。

### 3.4 读工具一族（perception，ADR-077 判词② T2b）

**世界的读法 vs `app/tools/` 世界的改法**——注册表家 = `app/chat/perception/`。读工具是 loop 里的**非终态**调用：执行直发（永不写 brief、永不落 outcome），结果以 ToolObservation 喂回 loop，模型看完继续想。初集：`get_run_status`（run 进度读数——answer 答进度前必调）/ `get_output_spec` / `get_understanding` / `get_asset` / `search_music` / `list_caption_styles`。按路径配座：plan path（尚无 run 与产物）只挂素材/目录读（`PLAN_READ_TOOLS`——挂上死座只会招来幻觉调用）；chat path 全族（`CHAT_READ_TOOLS`）。**工具名永不上用户面**——读调用翻成 Activity 读拍 + 注册项 i18n copy key（「正在查曲库…」，§8.6）。新读工具准入 = 注册表加一行（声明 + 执行 + activity_key），同 §4 的扩展门纪律。

## 4. Tool Registry 与 Skill Packs

> 可派发能力的唯一注册表 = `app/tools/__init__.py:TOOL_REGISTRY`（静态表随代码部署）；执行者是 agent 还是机械由 tool 包构成，无 `kind` 分类字段。估价与执行/拓扑知识住同名节点类（N-34/N-35），注册项没有 runner 字段。`seat=True` = 已登记未实装，不可派发。
>
> `app/skills/*/SKILL.md` 是另一层的**指令包**：只在 prompt 装配时注入写作/工艺知识，永不在运行时发现，也不替代代码能力。新增工具与新增指令包分别登记，不混用两个 registry。

每条工具登记：

```jsonc
{
  "name": "remove_filler",            // = 节点 kind（N-35 同名）
  "description": "Remove filler words and repeated takes …",   // "何时用"，注入 intent prompt
  "behavior": "deterministic",        // deterministic 可缓存 / probabilistic 每次计价
  "params_model": null,               // Pydantic 模型（可空）；Field 描述 = LLM 的参数文档
  "summary_templates": {              // 按 locale 的模板 dict（"en" 必填，其余回落 en）
    "en": "Removed {filler_count} filler{filler_count_s} · {repeat_count} repeated take{repeat_count_s}",
    "zh": "剪掉了 {filler_count} 处口水词 · {repeat_count} 处重拍"
  }
}
```

**准入纪律：tool 总数十几个封顶。** 新 tool 准入 = 过 NAMING §7 同款评审（用户会用自然语言说到它吗？现有 tool 组合能表达吗？），通过后同时登记注册项与同名节点类。

**扩展门纪律**：加可派发能力 = 往 `TOOL_REGISTRY` 填一项，没有第二种方式。节点类声明的 `retries`（步骤级重试预算）、`requires`（出生地输入校验）、`after`（拓扑约束）、`estimate`（估价）与注册项的 `summary_templates`（进度文案）随同一登记消费；节点类落进 `NODE_KINDS` 才由编排/工作流/SSE 接管。**禁止侧门**：不为某个节点单开映射表/特判分支（如平行的 retries 表）。内部节点（§4.3）不进入 LLM 可提议注册表，但其扩展同样优先审视能否表达为注册项。

### 4.1 当前可派发工具

| tool | 工具包 | 当前职责 |
|---|---|---|
| `select_clips` / `cut_segments` | `tools/clips/` | 选段与确定性切段；选段编剧 agent 声明随工具包登记 |
| `write_post` / `write_quotes` / `write_carousel` / `write_article` | `tools/posts/` / `tools/quotes/` / `tools/carousel/` / `tools/article/` | 文本、金句、轮播与文章产物 |
| `revise_script` / `remove_filler` | `tools/revise/` / `tools/filler/` | 改稿与非破坏口水词移除 |
| `dub_clip` / `translate_clip` | `tools/dub/` / `tools/captions/` | 配音与字幕翻译；共享翻译能力但不合并用户语义 |
| `add_music` | `tools/music/` + clip-spec music 槽 | 选择现有音乐并接入产物，不是自定义音乐生成入口 |
| `reframe_clip` | `tools/reframe/` | 按注册模式重取景 |
| `align_stills` | `tools/align_stills/` + `tools/stills/` | 图片材料化与阅读节奏时间轴 |
| `research` | `tools/research/` | 有界检索与研究产物 |
| `launch_film` | `tools/film/` | 把已确认分镜组装为 film-spec 并进入现有渲染链 |

`summary_templates` 只描述真实工序与数字，不把“已组装/已选择”写成“成片已交付”。完整登记以 `app/tools/__init__.py` 与各工具包为准。

### 4.2 座位与候选

| 名称 | 状态 | 说明 |
|---|---|---|
| `synthesize_talk_video` | 已登记 `seat=True`，不可派发 | R5 文字稿 + 照片 + 声纹合成发言视频；目标合同归 `docs/tasks/synthetic-talk-video.md`，不代表无声版或声音链已交付 |
| `make_hook` | 未登记候选，未实装 | 只有在 `revise_script(scope=hook)` 无法表达真实需求时才按 §4 准入评审；不是当前技能或排期承诺 |

### 4.3 不登记

- **管线内部节点**：`preprocess` / `persona_bootstrap` / `understand` / `plan` / `checkpoint` / `render` / `materialize_source`（ADR-043：整条源材料化，编译期注入——链含 clip-spec 消费者而无 select_clips 时把项目主源落成一条全段 clip-spec）——拓扑的组成部分，不是用户可选工具。
- **意图推断**：它是 chat 的工具 loop 本体，不是 loop 可调用的一项。
- **edit ops**：Operation Model 的词汇（§9），产出 clip-spec diff 而非 run——两个家族分开登记。
- **judge/verify**：`verify` 是当前可执行的内部节点 kind，负责确定性检查与已注册辅助 judge；不是用户可提议工具或独立 Product Graph 节点，全片深度看片仍开放。
- **缓议**：`adapt_to_platform` 等 Distribution 回流数据；`insert_broll` / `motion_graphics` 未登记，依赖与优先级归 PROGRESS，不预占空 seat；`avatar_gen` 仅保留 ADR-029 的后续框架，不宣称当前能力。

## 5. 物化：wiring ops → 持久图 → run 填充（ADR-057）

> **（ADR-072 / ADR-076 当前词表）** 本节机制（wiring ops / apply_wiring_ops 唯一写口 / run 原地填充）不变；图的用户面 = **媒介 / prototype / 业务身份三轴**：节点 `type` = 媒介五值（`text`/`table`/`image`/`video`/`audio`，`graph_nodes.type` 列——与 step.kind 工具名是两轴），`spec.prototype` = 能力原型（`generator` 散文程序 / `editor` 参数程序 / `manual` 无程序区——程序区按它门控，editor/manual 卡不渲染 prompt 区），业务身份 = `spec.summary` + `spec.tool`。翻译/配音 = **两站**（装配站 video×editor + 文档站伴侣 `{fill_key}#doc` table×manual，`asm.spec.doc_node_id` 链接；估价 stamp 侧 token/units 拆分——doc 站 = token 段、asm 站 = units 段或 None，step.estimate 不动保 hold）；materialize 折叠为消费节点内部 step（宿主 root 恒吃素材）；research = 单节点（text×generator，query 即程序，brief 直渲节点 spec.text）；writer 升 text×generator（产物 content 回写 spec.text）。legacy 行（asset/document/generator/processor/agent 与 modifier/materialize 过渡词）先由读面 `_read_face`（键 = spec.tool 执行真相）映射为当前面；task_book 节点读面隐藏。legacy 探索行只过滤、永不回填执行图；需要物理升级时必须按 `docs/tasks/product-flow-alignment.md` §4 在真实目标 DB 副本验证升级/回退与零双写，不能用开发库或读面映射冒充迁移验收。**画布相机**：用户发起节拍聚焦转场——dock 路径（chat 发送后 draft 图到来）= 确定性聚焦：route 对自己的 fetchGraph 响应 diff 新生 id → `centerRequest`;**单卡锁 zoom 居中，多卡簇走一次安全区适应窗口**（簇有界、一次请求一次，zoom 守恒唯二例外之一——station 链的 bbox 中心在锁 zoom 下是空地）；异步到达（run 落地 / SSE）= token 节拍 ensure-in-view 最小平移（zoom 恒锁，永不 fit）。唯二自动 fit = ① 出生定居取景 ② dock 多卡簇适应窗口。相机读**渲染席位**（layoutFlow 投影 positions/sizes），永不读 `n.frame`（岛成员渲染于 rank×PITCH，frame.x 只是 y 座/稳定锚）。愈合重挂载（canvasEpoch 自愈）视口保全——surface 持有的 ref 镜像实时视口，重挂载世界出生在原视口、定居 fit 跳过，**完工画面纹丝不动**；项目切换重置。背景 refetch 永不动相机；护栏 = 手势防护 / reduced-motion 瞬移 / docked 面板遮挡补偿 / 布防门（画布活 + 桌面）。用户主动 pan/zoom 是合法导航，不受自动相机禁令限制；后台 refetch 仍不得移动相机。探索记录住独立 `exploration_rows`，不是第四种 prototype，也不进入执行闭包、报价或 rank。

**项目 = 一张持久可变图**（`graph_nodes` / `graph_edges`，owner = Pipeline，MODULE_ARCH §4）。chat 的全部图结构产出统一为 **wiring ops**——`add_node` / `connect` / `edit_prompt` / `delete_node` / `run(_subgraph)`，初始生成 / 修订 / 新建同一组 op；`apply_wiring_ops` 是唯一写口，chat 与确定性卡面动作是已登记消费面，任何路由都不得另写图。画布直读领域投影（节点 id = 图行 id，边 = 图边，状态 = 行状态），不另造可写的平行图。

- **plan path（draft 载荷）**：计划 dock 即干跑出生地同款编译，把链 stamp 为 **draft 图**（`graph_fill.stamp_draft_graph`——图先展示后运行：节点空态 + 逐节点估价，零消耗直到 Start；bail / 编译失败经 `clear_draft_graph` 拆除）。计划正文与确认生命周期由 `pending_brief` / `messages.kind=task_book` 和 dock 持有；**不创建计划 document 节点或 task_book 图节点**，draft 图只表达真实生产对象与连接。
- **chat path 的 `edit_graph`（wiring 提案）**：修订/新建诉求产出 op 序列 + 摘要；`edit_prompt` 改写目标节点程序行，`run` 解出受影响子图（本节点 ∪ 图边下游），经 `graph_revise` 桥翻回 task list 进 `create_run`。
- **run = 图填充**：`create_run` 仍是 WorkflowRun 唯一出生地（零旁路不变），`compile_graph` 的三职责不变——① **校验**（registry + params schema，不认识或参数非法 → 拒绝反馈回有界 loop 重拟，仍失败则诚实说明能力边界）；② **拓扑排序**（节点类声明的 `after` / `requires`；生成工具共享去重 plan 前奏；修饰工具挂 clips / 注入的 `materialize_source` 之后，按提议顺序串链）；③ **补默认值**（全部由代码补，不信 LLM 的缺省判断）。产物仍是标准 `workflow_steps`（billing capture / 计量 / 重试的 step 粒度账本不变），steps 住进节点**内部**（组合，不是投影）。同一确定性编译 → 同一 fill_key——run 的 stamp 把 draft 节点**原地**填充（state 重 queue、step 回指、产物反写 `spec.output_ids`），永无双生；新槽位长新节点，图持续编辑从不整体重长。
- **画布读面**：`GET /projects/{id}/graph`（节点 + 边 + 产物引用一帧）→ FlowView 读取同一领域事实；布局与 rank 的只读派生不得成为第二可写事实源。**transcript 不成节点（ADR-113）**：转写稿 = 素材资产行的内容层（`assets.transcript`/`extracted_text` 唯一座 + `edited_transcript` 改稿覆盖层——C4 双层不变量：改稿只写覆盖层、源层与词级时间戳永不动；写口 = `PUT /projects/{id}/assets/{id}/transcript`，零 run 零积分，不是 wiring op）；素材卡解剖 = 媒体 + 时间条（cue 块 ∝ + 播放头）+ cue 流（点击拨头）；cues 永不持久化（读时 `group_cues`/`display_cues` 一法）。**成片卡轨道栈**：video×editor 剪辑族（`select_clips`/`translate_clip`/`dub_clip`）卡面常驻两条只读检视轨——视频轨（保留段块 ∝ 产出轴）+ 文字轨（字幕句块，停顿留白），读 `output.track_stack`（读时从 render_spec 推导，`pipeline/track_stack.py`，/results 与 /graph 两座 stamp）；draft/running = muted 空轨行（座位先钉）；修饰轨（音乐/配音）有内容才出现且骑轨栈顶（到来永不动锚）。**锚点律**：轨道卡的视频入锚离开角落栈，钉在视频轨 Y-center（`bottom = factsbar 带 + 文字轨行 + 视频轨行/2 − 半圆`，layout.ts `trackVideoPortBasePx` ↔ NodePorts 两镜像）。**血缘 = cross-highlight**（唯一跨卡通道，禁泛化）：成片卡视频轨块 hover 上报源区间（`lineageHover`），素材卡时间条/cue 行重叠区间琥珀亮起（`--lineage` token——灰阶画布唯一色相）；血缘只用 cross-highlight，不创建展示专用语义边。

## 6. 对话上下文（context 组装）

确定性代码组装，不是塞聊天历史（代码家 = `agents/contexts.py`——harness 输入侧，ADR-039；chat service 不持装配逻辑）。每回合组装以下段落：

| 部分 | 内容 | 来源 | 预算 |
|---|---|---|---|
| 项目摘要 | 素材清单、当前 outputs 列表（type + 一句话）、latest run 状态 + **节点级进度**（每步一行 `kind: status — summary`，≤12 行，G-2） | DB 确定性生成 | 4k |
| 最近操作 | 近 3 轮的 task list / edit ops 及结果摘要 | messages | 2k |
| 待决问题 | 未答问题原文 + 选项（防重问——下条消息可能就是它的答案） | messages | — |
| 言语语言行 | **言语语言律：我们发给用户的消息（提问 / 选项 label / 散文 / 摘要）一律走用户设置的系统语言**——`Accept-Language`（apiFetch 注入 i18n.language）→ middleware 抓进 `app.ui_locale` ContextVar → 两相位装配各注一行权威指令（plan path = j2 `speech_language` 块 / chat path = digest 尾行）。消息语言 / 人设语言 / 素材语言永不越权；人设储藏室的选项值**翻译**进界面语言。**只治言语不治产物**——内容语言（write_* `language` / dub `target_language`）走任务参数既有规则；请求外（worker / 剧本无头）缺省省略该行，回退消息语言推断 | 请求头 | — |
| mentions | 本轮消息已钉的 @ 实体（确定引用注入，§7） | 请求载荷 | 1k |
| 早期摘要 | 超窗对话压缩 | 未实现（v3，§11） | 2k |

## 7. Mentions（@ 实体引用）

> 提及系统 = 双端注册表（前端 `MENTION_REGISTRY`：icon / i18n / 候选源；服务端效果注册表按类型富化上下文）。可 @ 实体三条注册项：**asset / output（某条产物）/ workflow step**（step chip 只从结果画布点进程节点进入，@ 选择器不列步骤）；新 @ 类型 = 双端各一条注册项，无类型分支。配方不是 mention（MENTIONS §3：配方 = 提示词，卡面预填模板即全部发射载荷，ADR-040）；`recipe` 与 `transcript_segment` 仅是类型残留（未注册、不可新建；历史消息行的 chip 还能画出）。

多轮对话的模糊指代必须落为确定引用。

- 前端输入框 @ 触发选择器，`messages.mentions` JSONB 存 `[{type, id, label}]`；
- intent 收到的 prompt 中 mention 已替换为确定 ID 引用，LLM 解析歧义降一个量级；
- "把第二段高光换掉"无 mention 时，intent 可反问澄清——**反问是合法输出，不是失败**。

## 8. 进度推送：SSE = 推送优化的读

**定位：run 进度 SSE 是 `workflow_steps` 状态的推送优化读，不是事件总线。** 这条 run stream 本身没有独立事件存储、投递保证或帧重放；断线重连 = 重读当前节点状态，天然幂等。Chat 回合 SSE 是另一条传输：其散文、Activity、Candidate 与 dock 行按 `messages.seq` 持久化并可回放，规则见 §8.6～§8.9，不得把 run stream 的“无重放”误套到 chat transcript。

```
GET /api/v1/runs/{id}/events   （chat/routes.py 或 pipeline/routes/）
  async generator：run 非终态期间每 1s tail workflow_steps
  → 有变化才推：event: step.updated / run.updated
  → 15s 心跳防空闲断连
  → run 终态推完最后一帧即关流
```

- **该 SSE 的**：results 页 run 进度、chat 打勾流（用户正盯着一个活 run）。
- **该普通 GET 的**：projects 列表等一切非实时读——不为一棵树买一片森林。
- **前端用 fetch-event-source**：原生 EventSource 不能带 Authorization header，这是实际坑。
- **LISTEN/NOTIFY 后置**：内部 1s tail 在单 worker 规模足够；多实例部署再换 PG 通知桥，**客户端契约不变**。

**前端实现**：`useRunEvents` hook 统一消费这条流，接项目页 dock 打勾流（ADR-051：dock 壳唯一形态，无 fullscreen 壳；计划卡 HITL 确认 → 打勾流入流——活清单默认展开（导轨树 = run 的活读面，ADR-073）钉消息流底，终态收成一行收据；run 期画布 = 持久图节点原地填充（ADR-057：图先展示后运行——dock 即 stamp 草稿图，run 把节点 queued→running 擦除→产物落地反写节点产物区，画布直读零投影；**节点态的 run 期活读 = 同一 SSE 的 step diff 驱动 graph refetch**，step 每次状态翻转都伴随节点反写，画布与清单同一拍））。**渲染步撑住 run（ADR-074②）**：run 终态 = 最后一条渲染落地，「run 已终态但 clip 仍在渲染」的尾部窗口结构性消失——终态帧即真相；轮询只保留给无 token 的匿名场景。

**进度面**：进度 UI 只留打勾流一处（§8.7 单行动态行 = 唯一形态——活态 status line / 终态收据同一行）。`processing` 项目卡片直达 `/projects/$id`：项目页 dock 自动 attach 到活 run（无确认阶段、无 intent 兜底推理，计划摘要行由 `latest_run.context` 重建）；run 排队/素材处理中（步骤流为空）动态行显示 transcribing/queued 占位。attach 的 run id 由页面 latch（不靠活态重判），避免页面自身 SSE refetch 把 run 翻成 completed 时打勾态中途卸载。

**计划确认的持久化与恢复**：plan path 的 present_plan 回合把未确认的计划 + 原始 prompt 写到 `projects.pending_brief`（字段 = prompt / intent / reasons / persona_id / derived 预览；answer 回合不写，免得覆盖用户在确认的计划），run 启动时清除（answer kind=start）。`draft` 项目 ⟺ 待确认：项目卡片显示"待确认"并直达 `/projects/$id`，项目页无 run 时 dock 呈现"继续设置"计划——两处都能精确复活同一份计划（跨设备；卡片上的手动微调不入库，恢复的是最近一次推理版）。

### 8.5 QuestionDock 与 question/answer（ask_user 的落地面）

> **消息列表是"已决"的历史，输入框上方是"待决"的现在。**

- **一行两态**：`messages.question` JSONB（typed payload：`{kind: task_book|question, options, allow_freeform, slot?, default_path?, estimate?, reasons?, brief?, derived?}`——kind 收敛两值，存量 choice/confirm 行读取容忍升格）+ `messages.answer` JSONB nullable（**NULL = 待决**，宪法 §4）；`content` 存问题人话原文（自然进 LLM 上下文历史）。
- **已决/待决不共存（渲染缝不变量）**：QA 归档块携带 `questionId`（落库行 id——乐观块 / 信封归档 / 历史回放同盖），dock 的状态与渲染同认一个事实：流里已有该问题的 QA 归档时它是**已决**，dock 永不渲染——`dockSettled` 一座两处（effect 清 pendingQuestion 僵尸态 + pillQuestion 门同帧隐藏）。无论哪条路径让 dock 滞留（信封重 dock 与作答流竞态 / fetch 复活晚到），「上方 QA 汇总已入流、下方选项 UI 未消失」的成对态结构性不可能。
- **停靠法则（形态律，ADR-053 R1）**：渲染按 `options` 是否为空分流——**文字问**（options 空）= 普通对话消息，直接入消息流，永不 dock、永不等答（输入恒活；待决行住服务端，后续回合带来判定结算或提醒尾）；**选项问**（options 非空）= **阻塞形态**（FLORA / Opus 双参照——两家选项问待决输入均让位）：待决时输入行与免责行让位（CSS 隐藏不卸载，编辑器 DOM 草稿保住），dock = 问题本身——问句 + × + 选项行 + 尾行铅笔自由输入（**与选项行同一 item 解剖**：铅笔坐进数字徽章同款 tile——**徽章全局 1/2/3**（ADR-081：一切来源的固定选项同一编号语法）；输入本体底色双主题透明——Input 基底 `dark:bg-input/30` 需显式扑灭；Enter 走与主输入同一条 sendChat 通道——autoResume 选项命中 / slot 握手 / `pending_disposition` 判定结算语义不变）。**default_path 零可见面**（ADR-103）——散文零宣告、dock 零渲染（× 承担跳过手势），提醒尾照旧消费 default_path 原文（引文改读 payload 裸问题），机制不动；× = 阻塞态的 bail 出口——走问题的 default_path，interrupt 的 × 停掉在跑的付费 run。morph 跟随**渲染中的 pill** 而非原始待决态——确认期选项 pill 不渲染（计划 dock 占场），输入保持恒活。计划 pill 不阻塞不在此列（「不开始」用沉默表达）。**同一时间最多一个待决**——新题落库前旧题 auto-bail（`answer.text="superseded"` 机器标记）。回答瞬间坍缩成**已答问题双层消息**入流（`AnsweredQuestion`——**只归选项问**；文字问的回执 = 普通消息对）。**task_book 的 start 确认永不入 QA 块**——无论 chat 文本确认（G-1）还是 pill Start 手势，start 不是问答是手势；薄书的记录 = echo 散文 + 用户原话消息 + run 收据行。归档按 **answer.kind 行数据自证**：QA 归档只认 option/freeform 问答，task_book 分支（answer 只会是 start）整块不砌；渲染只由 message 数组自证，不塞派生数据。
- **待决重建零内存态**：`latest_pending_question` = 会话最新未答 question 的行查询（Mastra `listSuspendedRuns` 同款），GET `/chat/conversation` 带 `pending_question`——刷新/跨设备 dock 复活免费。
- **answer 端点即恢复**：`POST /chat/messages/{id}/answer` 写答案即解除阻塞（不显式命名 resume）。计划行分派：bail → 清 pending_brief 回 draft（prompt 已 seed 进会话，可重开）；`start`（一等 answer kind）→ 从 pending_brief 起 run 并写 `workflow_run_id`。choice 分派：记录后续聊——响应 `AnswerResponse{answered_question, follow_up}`（与 `ChatResponse.answered_question` 同角色同名，B2），option 答案回填 label 进 `answer.text`。重复回答 409。`/generate` 路径丢弃未答的计划行（`discard_unanswered_plan`——run 起于未答即无问答交互，问题行直接删除，历史不留伪造问答；真正的确认仍走 answer_question 结算）。
- **plan path 回合形态（B1/B4 + G-1）**：dock 计划 = `ChatResponse.assistant_message` 携带待确认计划行（kind=task_book）；answer 回合的答复落普通消息行且**不覆盖 stored 计划**；原话确认（G-1：intent router 调 `start_run`）复用 answer kind=start 路径起 run，`ChatResponse` 携带 `run_id` + `answered_question`；无可启动对象时 re-dock 存量计划或降级 answer，同样不覆盖 stored 计划。无 `needs_clarification` 布尔（`reasons.length > 0` 可推导，存量行读取容忍）。修订回合发 brief 做推理（LLM 提议、代码 merge，见 §3.1），每轮用户原文各自入档。
- **计划行自完备**：dock 即全量钢印——链 = 行 `intent` 列（InferredIntent dump），payload 携带 `derived` 预览 / `reasons` / `brief` / `estimate_credits`（冻结于 dock 时刻、每次 dock 重印）；**dock 行本身就是整张计划卡**，SSE 信封的行直渲零拉取（信封 = 回合的全部载荷，无第二次补全调用）。`GET /projects/{id}/results` 的 pending_brief 退回**恢复座**：draft 复活 / 跨设备 / 钢印前旧行（intent 列 null）的回退路径，活路永不再经过。caption 应答 replay 路同 stamp（该路 derived 恒空，与 pending_brief 行为一致）。前端 QA 块收口一个 builder（乐观块与归档行共用 `buildQaBlock`，Q 行恒读 payload 裸问题）。
- **入口约束归出生地**：clips-media 门、slot count 边界（节点 `count_limits` 声明派生：clips 1-10 / quotes 1-20 / carousel 2-15）、targeted scope 校验、链上工具的 `requires` 全部在 `create_run` 内拒绝（ValueError → 请求层 422 / chat 层反问兜底）——`/generate`、计划 start、chat 派发三条入口不再各持一份 guard。`create_run` 只 flush 不 commit：run、启动它的 answer、project 状态落在同一请求事务里，提交点唯一。
- **计划呈现与 Start（ADR-070/111/117/139）**：重型任务清单卡与第二计划编辑面退役；计划阅读事实 = 真实 draft 图 + 当前累计方案 + dock echo，`pending_brief/task_book` 继续承担冻结范围与恢复。不得按 `chain >= 2` 或“单任务只能口头”切换 UI。客户端只读服务端 `requires_confirmation` 等呈现戳；ask、守卫线、NULL、awaiting production 与 Film review hold 可显示真实 dock Start，auto 且已授权可同回合开工。口头 yes、typed answer 与 Start 按钮都化为普通用户消息走 sendChat，下一轮由 LLM 调 `start_run` 并进入同一 `evaluate_start_gate`，按钮不直接创建 run。ask 档 echo 以朴素、可一词回答的方案判断问句收尾；auto 只免普通批准拍，不创造制作意图；守卫线与 NULL 任何档恒带价确认。作品首个 Film 分镜版本必须先完整呈现并等待用户发话；auto 无其他确认债时不显示首稿 approval dock，ask 的 Start 同样只发消息。支持中的手改必须更新当前计划事实并清除失效命名；旧 yes 不授权新范围。
- **选项问与回答结算（ADR-053 R2）**：pill 渲染选项按钮组（ADR-081 全局数字 1/2/3）。待决中的用户文本两条结算路：**确定性 autoResume**（零 LLM）只认无歧义选项命中（字母/序号/原文）→ option 回答；**其余一切交给判定**——判定是 LLM 的、结算是代码的：plan path 由 slot 握手判（router 在 pending 块上下文里把该槽位值提案为 user-stated → 代码结算 freeform 并回填 brief）；chat path 由信封 `pending_disposition` 三态判（`answer` → 代码结算 freeform，interrupt 的判定回答唤醒 run 并给确定性回执；`skip` → 结算 bail——文字问唯一的 ×，它不 dock pill；`none` = 插话 → 问题保持待决，回复末尾接**代码拼装的提醒尾**〔双语固定句式：原问题 + default_path，代码强制文本永不借 LLM 之声〕）。计划待决不参与任何判定结算。`ChatResponse.answered_question` 携带本回合掉的问题行供已答问题入流。执行与费用确认使用当前 `requires_confirmation`、`quote_high`、`confirm_reason` 与 unquotable 标记，由服务端 Start 门裁决；不再把成本确认留作 v3。
- **checkpoint 形态**：方向检查点是选项问题 + `workflow_run_id` 分派标记。`Suspend` 异常把瘦节点停进 `waiting`（选项住 `spec.suspend_payload`）、run 停进 `WAITING_HUMAN`；答案端点/autoResume/判定回答（ADR-053 R2 的 disposition=answer）写 `spec.answer`、节点回 pending、run 回 RUNNING——队列式重入（runner 从顶上重跑，answer 分支直达 done），不是调用栈续跑。选项代码派生自 `key_arguments`（零 LLM）；**准入**：`key_arguments` 为空 → 选项只剩默认项 → 单选项无分支，不 dock 不 Suspend，runner 自动按默认项决议（`spec.answer` 与 human pick 同形状，`_interrupt_direction` 读法不变）——writer-only stub understanding 必中此分支（「Full-talk highlights」是 clips 话语，对 post 计划错体系），无分支问题不停车；bail = 节点 done(spec.bailed) + 下游级联 skipped("user bailed") + run COMPLETED（永不 failed）；`plan` 经 `task_book.direction` 消费（option → 优先论点，freeform → 指引原文，默认 → 现状；slot.focus > checkpoint > plan）。**过期**：park 超过 `checkpoint_expiry_seconds`（默认 30 分钟）由 worker 扫描自动以默认项回答并续跑（`answer.text="expired"` 机器标记，兑现"离开不中断"，永不 auto-bail）。**多 run 并停**：新题 dock 取代开口 checkpoint 题时同笔级联 bail 那个 run（`finalize_bailed_runs` 收官 COMPLETED）——单待决不变量不会搁浅 run。
- **film 分镜（ADR-127/129/130/131/132/134/137/138/139/140/141/142/144；本段只载 chat 行为摘要）**：字段级分镜、编辑、音频与渲染契约唯一归 [Film 总设计](tasks/film-storyboard-orchestration.md)；剩余工作与上线条件归 [execution](tasks/film-storyboard-orchestration-execution.md)，实现与验证层级归 [progress](tasks/film-storyboard-orchestration-progress.md)。`design_storyboard` 在 PLAN/CHAT 两路共用同一编排与版本座；网页 URL 的 `material_urls` 先经独立事务吸收，文字源不伪造网页采集。对话设计失败诚实收口，不用固定低质稿冒充成功；当前生产执行仍是单体 `launch_film`，Tasks 只显示真实单步。
- **film 呈现与版本**：工具从当前已保存版本生成完整 `storyboard_presentation`，patch 另给系统计算的 `change_presentation`；LLM 是唯一言语表达，但不得用旧表加差异自行重建当前表，程序不得另发第二份 markdown。完整散文仍受打字机两牙约束；呈现消息真正持久化后才关联 `film_presented_message_id`。活版本在 `pending_brief`，Start 将同一版本与执行快照钉入 `run.context.prepared_storyboard`；digest、draft token、review hold、制作意图与费用分别校验，漂移或过期版本诚实拒绝，旧 Output 不被修改版覆盖。
- **film 修订与制作授权**：定点修订骑 `edits` 六 op（`update_scene` / `update_element` / `reorder_scenes` / `remove_scene` / `set_music` / `set_voiceover`），开放重编排才骑 compose；同回合纠正有界，原子失败不得发布半稿。修订回复先呈现变化摘要与完整当前保存版：普通修改以 `answer` 询问是否重制，review-only 不问开工；只有当前消息明确「改完直接做」才进入既有提案、报价与执行道。auto 只免批准拍、不创造制作意图；**作品首版分镜在 `film_presented_message_id` 持久化前任何 Start 均失败闭，开场直接制作委托与 auto 也不能同回合开工。auto 无其他确认债时不显示首稿 approval dock，等用户看过后的制作话；ask 可显示 dock，但 Start 只发送普通用户消息。下一轮 LLM 调 `start_run` 才放行（ADR-144）**；fresh compose 与开放重稿默认 review hold ON，edit/variant 不新增 hold，但旧 run/旧版批准也不授权新版。shortfall、copy_drift、review hold、守卫线与 Start 版本绑定均不因 patch 或完整呈现而削弱。
- **film 音频与交付**：新建默认无配音；voiceover、音乐与视频原声独立，显式 off 不被 persona/默认值重开。`voiceover=true` 时全片无旁白仍是违规，worker fail-closed；重开配音复用既有旁白，不强迫全片重设计。voice 设计期钉版、STOCK_VOICES 与试听是 PLANNED。交付只陈述 run.context 与 Output 的真实版本、音乐/旁白/原声和渲染结果，成功才称完成，失败必须给出事实与下一步。

**量化摘要**：`node.spec.summary` 由 runner 按 registry 的 `summary_template` 填充（模板填数字，不是 LLM 润色；英文模板用自动注入的 `{参数名}_s` 复数位——n=1 为空、否则 "s"），随 step.updated 推送——这是打勾流"Removed 12 fillers · 2 repeated takes"的数据来源。收官 = **普通 assistant 内容散文回复**：run terminal 后由 §8.8 的 delivery / failure trigger 按 DELIVERY / FAILURE FACTS 写作；工作段只承担过程与 Worked 收据，不另立确定性「做好了」模板、timing footer 或 recap 聚合（`spec.summary` 已在清单产物行说过一遍）。**失败行是人话不是原文**：异常携带 `user_key`（`pipeline/errors.py` 的 `USER_ERROR_LINES` 键；MiniMax 客户端按 429/5xx/传输/schema 分键，voice 族自带，包装层 `propagate_key` 透传），终态 `node.error` 烘焙成 run UI 语言的本地化短句——原始异常全文只进 structlog，SQL/SQLAlchemy/httpx 内脏永不上脸。渲染链同理：`render_error` 写人话行（项目语言链），output 行与 render 节点镜像同源。

### 8.6 chat 回合 SSE

**工具 loop 流式**：散文 = 模型言语直推（`assistant.delta` `{"text"}`，逐字 verbatim——言语即回复的内容通道，无 JSON 筛选）；工具调用永不上用户面（禁令见 §12）——调用名成为已知的那一刻翻成 **Activity 帧**（工作证据唯一通道，name→kind 映射见下条活动流）；`assistant.thinking` 只剩两件事：`{}` = 纯 keepalive（只保温 thinking 指示，永不展示）；相位帧 = 分镜设计跨度的三个真相位（`capturing` / `storyboarding` / `storyboard_revision`——`design_storyboard` 执行内的真实转换点发射，跨度退出时发显式清除帧，ADR-133）。**on_delta 只在 iteration 0 发射**——被拒迭代的言语被替换，后续迭代静默（言语账本：被保留的言语片段前缀缀进合成内容）。**`question.preview`**：ask_user 调用的参数一完整过校验即由 `on_tool_ready` 形成预览帧（question / options / allow_freeform / slot / default_path），但 SSE 路径先进入 `DeferredFrames`；只有终态接受后的有序 flush 才把预览发给客户端，信封仍是 authoritative（happy path 载荷相同 → 真行原地替换零视觉变化）。调用被拒 / turn.failed / abort 时预览随缓冲撤下，客户端从未看见，零回滚残片；曾遭拒绝的回合关闭为 frame-silent，最终信封整段经打字机释放。**preview 期点击 = 寄存**（乐观 QA 块先落、复用同一 id 不重挂载，信封 dock 真行后以真 id 发射；选项集被翻案改写则寄存干净退役）；preview 期 × 隐藏、铅笔禁（行未生成就无可 bail / 无可答——chatBusy 同窗）。**基座 Thinking + 相位**：基座恒为 "Thinking…"（LLM 黑盒窗 = thinking 本义，不设别名）；差异化相位只在结构性不同的活动上拍；前端未知相位落 `defaultValue` 回退，`{}` 帧不碰文案；失败行第一人称认领（`ai_unreadable` =「是我的问题，请再试一次」——说话的就是 assistant，失败不归第三方）。**相位清除协议（I-PFA-06）——任何相位不得比它的活动活得久，相位死亡只有三个合法形态**：① **覆盖律（活动移交）**——带标签帧 = 新相位开始 = 前一相位终止（分镜跨度内 capturing → storyboarding → storyboard_revision 依次移交）；② **清除帧（活动终止无后继）**——`{"phase": null}` 的合法发射座只有两座：每个调用名的 name-known 时刻（`routes.py:_make_tool_hooks.on_tool_call`——无相位在戴时是 no-op）与分镜跨度自身的退出（`draft_film_storyboard` 的 finally——跨度的词跨度自己收，bare-reply 终局没有 name-known 兜底）；client `"phase" in payload` 判据区分清除帧与裸 keepalive，归零回落基座（基座 = LLM 黑盒窗本义，不是残留）；③ **终帧律（信封权威）**——turn.completed / turn.failed 关闭一切残余相位，client 两条流（sendChat / streamAnswer）在信封与失败路径都归零。`chat.thinking` 基座覆盖一切其余窗口——LLM 黑盒窗（决策 / 写回复）无论多长只叫 Thinking…，不设别名（时长不设限，词语不许怪——ADR-133）。终态恰好一帧——`turn.completed`（完整 ChatResponse，**信封永远赢**，整体替换预览气泡）或 `turn.failed`（`{"detail"}`，流中失败；失败信封不是 assistant 正文，已持久化的用户行、活动与失败记录按各自事务保留，不把整个回合伪装成从未发生）。15s 心跳注释帧。**对账完整律（ADR-093）**：信封永远赢 = 身份盖章 + 内容真值替换两半齐备，一切 SSE 结算路径同一纪律。

**活动流：`assistant.activity`（ADR-087 §3）**：回合内 Agent 工作的**追加式里程碑流**，与相位帧（System Status）分家——相位回答「系统处于什么宏观态」（基座 Thinking… / 分镜跨度三相位），活动帧回答「Agent 正在替你完成什么工作」。标准链 = loop 内核 typed `LoopEvent`（`agents/tool_loop.py`：`ToolRejected` 拒绝当时 / `TerminalAccepted` / `ReadAccepted` / `LoopExhausted`——**内核只说发生了什么，永不引用 Activity 词汇**（U1 冻结边界）；迭代边界无独立事件，两个起因由既有 `on_repair`/`ReadAccepted` 覆盖）+ 既有 name-known 缝 → `chat/activity.py` 纯投影器（name→kind 映射单点拥有：read / draft / run / repair **用户语义类别**，永不退化为 tool name；repair 聚合 N→1；ask_user / answer 属 Conversation 层 1→0 过滤；零 DB 零 Domain 读）→ `assistant.activity` 帧（live 瞬态面——字段白名单 `activity_id`/`seq`/`kind`/`status`/`key` + `at`/`count`/`duration_ms`，零参数零结果零推理；key 随 status 取态——active 帧进行态、completed 帧过去态）→ `_sse_pump` 直过 → dock now-line。**持久化 = 每帧一行（ADR-108 §2）**：`frame_persistence` 纯映射（`chat/activity.py`）一法一座决定落库——读跨度 open 时 append（`intent.type='activity'` 单帧行，`at` = execute 入口出生戳），settle/failed 时**同行原地 update**（终态 + 过去时键 + duration_ms，数组位置永不动）；repair 终态帧与 explore 里程碑（born-completed）append 即落定；draft/run 跨度永不持久化（落定即退役——dock 的计划卡 / run 收据就是它们的落定证据）。写口全部走独立短事务（`routes.py:_make_activity_persister`），不碰回合长事务——失败/中止回合已 append 的行照常提交（**诚实 transcript**），断连路径 open 行原地 settle 为 cancelled（`cancel_open`）。SSE 镜像数组操作：`assistant.row.append` / `assistant.row.update`（载荷 = 消息行镜像），live reducer 与历史回放吃同一语义。**回放 = `ORDER BY seq` 直渲**——渲染层零重算顺序（无时间戳混排 / 锚点推导 / last-wins 闩锁）；`activity_forensics` 拒收台账行与旧聚合行永不渲染（存量聚合行由 `scripts/migrate_activity_log_rows.py` 一次性物化为单帧行）。**工作段折叠 = 呈现层纯函数**（`lib/chatTimeline.ts:foldActivityUnits` + `foldCategories` + `WorkSegmentRow`，ADR-110 段聚合——折叠说总量、展开说分解）：两个用户可见散文段之间的连续 completed / active 活动行（含单行，跨 key）属于同一个工作段单元；active 从出生即在数组原位承担 live 座位，completed 才进入工作记录明细，user / QA 切断段。cancelled 尝试从可见投影退役，不留 ✗ / 删除线、不打断折段；真实 failed 行保留一条安静告警并打断折段，文案使用终态失败形式，不复用 active 的「正在…」。**工具完成 ≠ 工作段完成**：当前回合最后一个未收口 fold 原位承载 Thinking / 具体里程碑，已完成工具先在段内累积，**live 恒无 chevron、不可展开**；后续正文第一个非空白字符由打字机实际释放时，或无正文的成功 / 失败 / 取消 / 断流等真实终态，同一单元原位收成「工作了 2m 7s」并开放展开，正文显示在其下；首显按 prose `rowId` 只封其前方段，前一条 checkpoint 不得误封其后新段。终态 error 灰行不是后续正文，不能抢在 terminal seal 前关段。SSE 帧到达、keepalive、reasoning、空 delta、已缓冲但未显示的文本都不收口；busy 时永不同时出现「工作了 X 秒」与下方另一条 Thinking。尚无活动行的纯对话由底部同一个 `WorkSegmentRow` 显示不可展开 Thinking，永不制造空工具框。展开 = 类目分解——同 key 行跨全段合并为一条 ×N 类目行（「已读网页 ×3」），实例名与逐行时长不归归档面（material 读取族经 `activityCategoryKey` 重映射到无名的 `materialCategory` 键族，web_page 分叉随节拍 `asset_type`），产物计数里程碑（count 无 total）永不合并。**时钟与身份**：实时段从用户发送 / QA 实际点击显示 / Start 实际点击 / 前段散文排干后的真实边界起算，缺这些事实才回落首条活动的 execute-entry `at`；首显或真实终态写一次冻结终点，后续打字不继续累计，工具 `duration_ms`、后台 run 与用户等待确认都不混入。宿主行 `birthKey ?? id` 是跨回合身份，per-turn `activity_id` 永不承担它；完整身份 = 首个宿主行的 `birthKey ?? id` + 本回合宿主行 key 集合，不使用数组下标或新随机 id。Path A checkpoint rekey 必须保留首显身份与 `birthKey`，不得重复收段。回放没有客户端首显事实时只显示首末活动自身可观察的跨度；无墙钟事实显示操作数，永不求和并行工具时长冒充整段耗时。conversation 与 runStream 共用这一投影和渲染器。**终帧清扫律**（I-PFA-06 终帧律的活动同形）：信封落地前服务端清扫一切仍 active 的活动，客户端信封/失败/abort 三处再兜底（同扫 now-line 瞬态列表与 messages 内嵌数组行两座）——dangling 活动结构性不可能（T16-B 活性不变量）。**连续性 ≠ 周期刷新**：active 活动可合法横跨整段 LLM 思考窗，连续感来自活动生命周期与真实里程碑，不来自帧频率。**合一律**：active 活动从首条宿主行出生即入流，同一 `WorkSegmentRow` 在 think → 里程碑 → think 间原地 morph；前段正文 typing 只隐藏尚无活动宿主的底部 Thinking，不吞当前活动。后续首显或真实终态把同一 rowKey 收成工作记录。相位面 = 基座 / 分镜跨度三相位 / 清除帧。

- **auto-Start 的言语结算**：echo 去重读取实际消息流，不能把 `assistant_message` 与 `answered_question` 同 id 当成 echo 已显示。只有完全相同的 assistant echo 已在流中才跳过重复释放；同回合首次生成并自动开工的计划必须先经 `paceSettledProse` 排干完整正文再挂 run。独立开工句始终释放，零正文 Start 不产生空气泡。

- **Accept 协商**：`POST /chat` 内容协商——普通调用拿一次性 JSON（201，行为逐字节不变）；`Accept: text/event-stream` 拿流。剧本测试 / 旧前端零改动，随时回退。
- **计划卡永远流不了**（结构化调用参数必须完整到齐，dock 只随信封到）——但回合散文（计划卡的引言）流式推 delta；start_run 回合同律有言语权——开工句是 start_run 回合的 LLM 言语（ADR-093 §2），走正常 delta → 打字机 → 信封结算，落库为普通 assistant 行。两个 agent 的 system prompt 与 turn_tools 描述同款纪律 = **先说话再调用**（speech BEFORE calling），散文恒在工具帧之先。
- **打字机律（绝对规范——任何改动不得违背）**：agent 的一切言语必须以打字机节奏出现，整段瞬移永禁。两条结构牙：① **散文字段入 schema 必带读容忍**（`prose`/`default_path`/`options`/`name`/`tasks_explicit` 的 null 读为空默认值——一次 schema 拒收 = 被拒迭代，而**被拒迭代永不流式**（两条 delta 流交错进一个气泡比信封换文更坏，N-26），于是整段瞬移）；② **零 delta 路径的最后闸门 = `paceSettledProse`**：信封到达后散文照样走 typewriter 节拍释放（typewriter `drain()` 等排干），dock / QA 归档 / follow_up 一律等释放完成才落——sendChat 四分支（选项问 dock / 纯散文 / 文字问 / start 开局）与 streamAnswer 的 follow_up 全接。
- **service 拆两段**：`prepare_chat_turn`（dispatch 决策之前全部，所有 4xx 在此抛）+ `execute_chat_turn(db, prepared, request, on_delta)`；`chat()` = prepare + execute(on_delta=None)，JSON 路径不变。SSE 生成器使用独立 `AsyncSessionLocal`，避免请求级 session 在流结束后提前关闭。主回合事务与活动/世界读本的独立短事务分开：断连或失败只回滚尚未提交的主事务，不撤销已提交的用户行、活动或失败记录；`turn.failed` 不是“整个回合零提交”的同义词。重试必须新建用户动作，不能靠自动重连重复发送。
- **前端**：`lib/chat-stream.ts`（fetchEventSource POST，**禁自动重连**——重试会重复落用户消息；非 2xx 读 JSON detail 保持 422 toast 语义）。两个面同款节奏：发送 → thinking → 首个 delta 才建预览气泡（Streamdown `mode="streaming"` 渲染不完整 markdown）→ 信封**原地落定**（同 key finalize 转静态，**永不 remount**——删除重推会让已定散文重播入场动画 = 肉眼闪烁；answer 路径同纪律：乐观 QA 块**原位**替换为归档行（同 index **同 key**——换 key = 卸载重建 = 入场动画重播的闪烁）、预览泡原地转静态，follow_up 散文由预览携带 echoCarried 不重推）+ 跑现有完成逻辑。**Chat 工作段行的显隐**：尚无当前活动 fold 时，底部座位在 `chatBusy && !visibleProseTyping` 显示同一个 `WorkSegmentRow`；已有当前未收口 fold 时由它原位接管，底部座位互斥消失。`visibleProseTyping = proseActive && 存在 content 已含非空白字符的 streaming 行`——只收到 delta / 信封或仍缓冲的文本不算可见，打字机实际释放首字才通过 `speechSegments.onVisible` 收口前段；散文播放途中不另压一条 Thinking，排干后的后续模型等待仍属当前工作段。**工作段同一骨架**：chat 的 Thinking / 工作里程碑 / 工作记录与 run 的制作 / 交付等待 / Worked 收据统一由 `WorkSegmentRow` 承载；chat activity 与 run steps 只各持一个数据适配器，时钟按各自工作段独立计算，`StatusLine` 与底部独立 `closingReview` 座位不再存在。静态历史消息同走 Streamdown（`mode="static"`）。**素材节拍三寄存器归位（ADR-095）**：入库节拍 = 日志格措辞（动宾 + 事实后缀，无人称无进行态）；live now-line 工序化（瞬态面可比入库面细——随 processor stage 说「转写/理解」真话，stage 经 `asset.meta` 出口，零 schema）。**素材理解 = 回合内前提条件（ADR-102）**：上传 = 纯存储（休眠素材——worker 认领需 `processing_requested_at` 非空，盖章口唯二：模型的读企图 + run 出生地兜底；寒暄/围观零处理）；`get_understanding` 在回合内等终态（无时间上限——ready / failed 两终态，逻辑阻塞单 writer，零接力零轮转零评审复读；worker-down 悬挂 = 在册承重观察），用户面 = 读活动帧三态（「正在查看素材内容…」→「已理解素材 · Ns」/「素材没能读出来」——`ToolObservation.ok=False` 落 failed 帧），同回合 grounded 作答或诚实宣告读不出 + 重传出路。散文与结构预览帧在服务端按序缓冲（`DeferredFrames`——言语提交协议，ADR-099 §7）：每个带 `on_delta` 的 SSE 回合都武装它，`delta` 与 `tool_ready` 入队；`on_tool_call` 仍为 Activity、相位清除与 liveness 实时通道。终态接受才 flush 后 disarm；checkpoint 先 flush 但保持 armed；任何 ToolRejected 立即清空陈旧帧并继续 armed，曾遭拒绝的回合最终 frame-silent 关闭，信封整段走打字机。不得新增第二 speech router、token classifier、自报 mode 字段、NLP 散文对账或全局 history washing。检查点帧先冲刷再出（**言语座位通用化，ADR-109**：checkpoint 无资格白名单——任何非终态调用，模型自带散文且参数校验通过，即在校验后、execute **之前**发射；before/after 一座两用（after 汇报 = 下一迭代的散文撞上同一 before 座位）；终态工具散文留账本随 settle 的守卫不动；`MAX_CHECKPOINTS_PER_TURN=4` 是防啰嗦节奏护栏，不是资格限制；prompt 面 = 相位叙事律——读前预期句/读后小结句合法，逐调用旁白永禁）。发射座时点承重（ADR-104 撤回窗论证不变）：等待读的 execute 阻塞到素材终态，押在执行后会把服务员话扣押整场等待。排序 = **数组位置律**（ADR-108）：消息流 = append-only 类型化数组，`messages.seq` per-conversation 单调（分配器 = 独立 `message_seq_counters` 表 + 短事务 upsert——回合长事务持有 conversations 行锁，计数器若住该行必自死锁），持久化顺序即渲染顺序：checkpoint 行落库于发射时刻，读活动行 append 于 execute 入口（`ReadExecuting`——name_known 是生成中途的 liveness 戳，锚它会早于服务员话落库戳），settle = 同行原地 update——三者的数组序天然就是真实时序，live 与回放同一 reducer，渲染层零重算（无时间戳混排/锚点推导/闩锁过滤））。**dock attach 钮 = 中途上传暂存**：选中文件在输入组内落生命周期 chips（uploading → done/error，× 删且删资产，direct-to-storage 与 composer 同流）；只有 send 消费它们——骑回合消息 `attachments` 落库、刷新重渲染；选文件自身永不发送；附件单发合法（plan path 从诚实替身行推断）；空消息永不自动作答 docked checkpoint。
- **answer 端点同 /chat Accept 协商**：SSE 模式推续聊散文的 `assistant.delta` 预览 + 终帧 `answer.completed`（完整 AnswerResponse）/`answer.failed`。JSON 仍是默认（剧本 / 无待决行的 legacy 直启回落不变）。answer 流同享 `question.preview`（同一 `_question_preview_frame` 构建器 + `on_tool_ready` 钩子）——连答序列的 Q2..N 与 Q1 同享；续聊 `on_phase` 穿线同 chat 路径。**preview 期点选的跨 await 寄存**：回答在途时新 preview 到达，点选暂存（`stashedAnswerRef`——TS 控制流不可见的重入写，读取处显式 cast），follow_up 落定后以真 id 发射；无 follow_up / 流失败则寄存干净退役。文字类提问永不预览 dock（`!question && 无 options` 直接拒——与 R1 文字问门禁同律）。

- **断流、停止与恢复**：放弃或停止时清扫瞬态活动与 Thinking 并释放输入；cancelled 不算成功，真实 failed 保留诚实告警。chat（含 Start 普通消息）与 answer 流都有静默看门狗，keepalive 计入活性，结束时清理计时器。chat 死流由既有 `reconcileTurn` 只读轮询落库回复，窗口内仍无回复则显示 `connectionLost`，刷新由归档回放补齐；不得自动重发用户消息。answer 流由 `answerWatchdog` 终止静默死管并按既有回答路径收口。

### 8.7 Run / Chat 工作段统一显示律

- **一套组件，两个适配器**：`WorkSegmentRow` 统一拥有 live / reviewing / settled 的头部、disclosure、Worked 收据与成败槽位。chat adapter 仍读 activity fold；`RunTaskList` 只把 `WorkflowStep[]`、run narrative、成败和时间投影成同一组件的 props，**不把 run 步骤伪造成 chat activity 消息**。steps 树与 chat 类目树是两种 details 投影，不是两套生命周期。全部消息经同一个 `rowStreamUnits` 渲染，`taskList` 只是 run 数据分支；独立 `StatusLine`、run 专用开合机和底部 `closingReview` 行均不再存在。
- **run 三段生命周期**：`RUNNING → REVIEWING → SETTLED`。**run terminal ≠ 工作段 settled**——terminal 只在原 row 把当前活动换成「正在整理制作结果…」，步骤不另起一行；匹配当前 `runId` 的 delivery 消息，其首个非空白字符**实际经打字机释放**时，同一 row 才原位收成 Worked 并开放展开。消息帧到达、已缓冲文本、空白 fragment、其他 chat 回复和其他 run 的迟到消息都不收口。review 无回复 / 被静默时由既有 60s 有界出口落定；历史回放只放真实行，不复活等待态。
- **三个边沿分家**：run terminal + 真实可交付 output 决定产物就绪与画布交接；chat inline chip 复用 `runWorkPhase === "settled"` 的同一展示边沿——匹配 delivery 首字实际释放或既有有界 Worked 出口，REVIEWING 中不提前挂载；回复 drain / 落定再完成 suggestions 与普通消息收尾。产物准入继续由 `AnchorCards` / `RunCard` 共享的 `isDeliveredOutput` 把守，成败不从回复文本猜测。交付回复仍是普通 `AssistantText`，不是 chrome；不新增确定性「做好了」模板。
- **时钟与身份**：run row 的 key 由 `runId` 稳定持有，running / reviewing / settled 不换 key、不 remount。seal 按当前 run 作用域写一次；实时段从 `run.created_at` 计到交付首显，包含这次交付等待，**但不与任何 chat 工作段时钟相加**。历史回放或无回复回退只读 run 自身可观察的最后步骤边沿，不拿 assistant 写入时间冒充首显；并行步骤时长永不相加。当前步骤耗时只属于 RUNNING，reviewing 不继续冒充电流。
- **details 与开合**：run 的步骤导轨树在 RUNNING / REVIEWING 默认展开，用户可手动切换；开合覆盖按 live / settled 姿态分域，running → reviewing 保留用户选择，首显 settled 当拍默认折起，之后可再展开。chat live 仍遵循 §8.6 的潜伏工具行规则，不为统一而重新展开。no-op 仍读服务端 `spec.noop` / skipped，whisper + line-through；失败步骤保留红 ✗ 与人话 error，pending / waiting / running 的既有语义不变。
- **行文本与命名**：step label 继续读 builder-written `spec.summary`，live narrative 只走 stage hint → kind progressive → preset → raw kind 的既有回退；零上传 preprocess 仍说「准备生成」，不谎称分析上传。存在诚实耗时时，run 收口与 chat 一样读 Worked；run 的 LLM 命名继续由提案 / `run.context.name` 持有，只作为无诚实耗时旧行的读取回退，不再另立一份标题收据。
- **命名撤保不变**：run 标题仍优先取生产它的提案 `name`，每条出生路径分别盖章，后续 run 不继承；手改语言 / count / bilingual / 增删任务即清空该名，回退到读当前参数的诚实标签。未命名提案仍在 dispatch 处记 `unnamed_proposal`，回退合法但不得静默。
- **部分失败判决不变**：任何非 runtime-fanout 步骤 failed ⇒ run FAILED；render fanout 除外。存在 done 且带 `output_refs` 的产出步时 project → REVIEW 并执行完成交接，全灭才回 DRAFT 且不交接；prep 步不算产物。run row 保留失败标记，交付回复只说实际交付与缺失，永不在失败分支上盖 blanket「做好了」。
- **成败与时序**：settled 的 ✓ / ✗ 与红色失败文案读 run 自身状态；已交付和部分交付只展示真实可交付 chip，全败不制造产物卡。后端 `delivery_state=delivered|partial|failed|unknown` 只拥有交付言语分支，前端不复制一套推断。run 活态单元钉消息流底；terminal 后锚在 run 结束刻并可在那里继续 REVIEWING，mid-run QA / 插话留在其上，delivery 回复按消息数组序随其后。

### 8.8 触发回合（主动说话，ADR-077 判词③）

世界事件到达 = agent 自己开口：pipeline 在白名单座位 fire-and-forget 触发 `chat/trigger_turn.py`——ToolLoopAgent 家族的第三座（与 plan path / chat path 两回合 runner 同族），按事件选择带读的 `trigger_agent` 或零读的 `delivery_agent`，最终由 `wrap_up` 终态落一条 assistant 行（`intent={type:"trigger_review", trigger, ref, suggestions}`）。`_already_spoke` 按 (trigger, ref) 去重——一个事件最多说一次。触发回合永不起 run——它是说话，不是第二意图表面（建议的作答仍走 answer 端点 / autoResume 的既有结算，trigger 自身不结算）。**轮询恢复不是第二遍全量历史回放**：activity / material_beat 只准入晚于客户端此前已观察 `messages.seq` 尾部的新行，旧行由挂载历史回放承担，不得在 run review 或素材轮询时因「客户端未见」补进 live 尾部。普通 watch 只接新尾 trigger；run review 只接当前 `runId` 的交付 / 失败行且不补 activity，其他 run 的旧 trigger 不由该窗口代接。属于当前恢复窗口的 trigger 与断流恢复散文仍须到达，但按 `seq` 插入既有后继之前；只有晚于已观察尾部且无后继的新行才落 live edge，散文继续经 typewriter 排干。挂载回放只补当前 live 数组缺失的服务端行 id，不覆盖或复制已在场的行。**缝注（ADR-087 §6）**：pipeline 侧一切 fire 走 `pipeline/trigger_events.py` 白名单事件缝——kind ∈ {`run_completed`, `run_failed`, `craft_decompiled`} 冻结白名单（扩名单 = ADR 评审；素材评审事件已随 ADR-102 退役——素材理解是回合内前提，永不是世界事件）；handler 由组合根（app.main / app.worker）经 `chat/seams.py` 注册，未注册 = 静默降级永不 pipeline 失败；pipeline 零 `app.chat` import（冷导入探针可证）。**`run_failed`（ADR-135）= 全败 run 的失败通报座**：fire gate 与 run_completed 互斥（FAILED 且零产物落地才 fire）；事件行携带确定性 FAILURE FACTS 块（每个失败判决步一行——`step.error` 的烘焙人话行，永不重推导）；下一步 dock 成 ≤2 个「能成功」的选项（确定性死因永不给原样重试），收据自证不了原因也说不出下一步——沉默即失联。

- **交付回合专词专用（`run_completed`）**：独立 `delivery_agent`（零读，只有 `wrap_up`）+ `prompts/chat/delivery_system.j2`；通用 `trigger_system.j2` 只保留 `run_failed` / `craft_decompiled`。交付输入只有对话上下文与最新工具/run 结果组成的 DELIVERY FACTS。`run_review` 先用代码裁决唯一 `delivery=failed|partial|delivered` 分支，模型只叙述该分支：全未交付只说未交付内容、已证失败与可行下一步；部分交付只点名实际交付与缺失；已交付平实收尾，不默认追加审计、评价或下一步。旧无事实 run 只给收据能证明的普通完成。交付回合 `suggestions=[]` 不变。
- **可交付才进入交付事实与 Chat 产物卡**：render-contracted 的 `clip` / `film` 必须同时满足 `render_status=completed` 与 `files.video` 存在；失败、在飞、 completed 但无文件的行不产生 `landed` 提示词行，也被 `AnchorCards` / `RunCard` 共享的 `isDeliveredOutput` 准入滤掉，失败证据仍由 Tasks 与交付文字承担。文本产物走原有 payload，不受该媒体门影响。只有已交付 film 才做确认版与执行 spec 的一致性汇报；UI 场景的 `page` / `shot` 是烘焙前选择器，执行 spec 已解析为 `url` / `image`，两者形状差不得报 drift，身份一致性由 storyboard digest 承担。画布上的工作节点与失败状态不因此隐藏。

- **单一叙事者律（ADR-080）**：准入门 = 叙事所有权门，两张静态谓词——会话内有用户 turn 在飞（`turn_state='in_flight'`）→ **defer**（20s × 15 周期）；无在飞但有 **pending task_book 计划** → **静默**（「我看了什么」的叙事已被计划 echo 覆盖，再说只有抢麦）；两者皆无才可说话。超限/失势一律落静默教义：盲评不如不说。
- **界面语言唯一 owner（ADR-080）**：`conversations.ui_language` 列 = 单一事实源（prepare 每个用户回合从请求 Accept-Language 盖章），一切 assistant 写者（plan / chat / trigger）继承它——`_trigger_language` 链 = owner → run pin → history 兜底推导 → en，无 per-writer 推导。
- **建议形态（ADR-081）**：`suggestions` = ≤3 条**用户口吻选项 label**（schema 约束：blank 丢弃、>40 字拒收；产物下载归画布产物卡 factsbar），有建议时 review 行**dock 成真实编号选项问**（`kind="question"`，选项 id = 1/2/3 位置序号，阻塞形态律不变，× = 优雅不选）；无建议 = 普通散文行。作答路径零新机制：选项命中（点击 / 打序号）走 answer 端点 generic 续聊分支——**按项目 run 状态分派**（无 run 走 plan path 起草计划，有 run 走 chat path），选中 label = 用户发言。存量 pill 行前端读容忍回放，新行不再产出。

### 8.9 Candidate Surface

选段工具把领域事实写入 `exploration_rows`；Candidate Surface 的客户端传输是 `assistant.candidates` SSE 帧族，turn settle 后聚合为一行 `candidates_log` 供回放折叠。它不创建 Product Graph 节点，也不新增候选查询端点。live、刷新 replay 和 answer 回合必须恢复同一组候选；聚合行与 ADR-108 数组行的形态差异及验收归 `tasks/transcript-array-and-speech-seats.md` §2～§3。

- 默认呈现至多三条推荐，用户可要求有界扩展；不得把全部搜索结果无界倾倒进 chat。
- 每张候选卡显示可核实的 ordinal / 时间范围 / excerpt / speaker 事实；不得把模型评价伪装成源素材事实。当前 schema 没有 `why` 字段时就不显示理由；源素材已删除的悬空引用必须读容忍并诚实留空，不伪造 range。
- 当前选择必须高亮；同一 journey 重选是**替换**原选择，不与旧选择做并集。bounds 变化后重新校验 member index，并刷新 verdict / reason。同集幂等重发原位更新，selection-only 日志只重绘前序卡，不生成空行。
- 卡片只反映选择，不新增点选原语；用户经自然语言换选。若未来允许点击直选，必须另过交互与授权评审。
- 失败回合不得留下半应用的候选或选择：回滚本回合 Candidate Surface 变更，已落库的旧选择不被静默改写。
- 跨轮继续沿用 journey 身份；settled 后只读，replay 零写。选择修订在 dock 前、dock 后与 run 后的授权路径分别遵循 §8.5、`DIALOG_WORKFLOW.md` §4.3 与 `BILLING.md` 当前守卫，不因卡片交互绕过 Start 或费用确认。

## 9. 修订边界（ADR-057：wiring 统一 + edit ops 节点内部存活）

chat 的另一半是“改现有产物”。修订目标必须能确定性解算：`@output` 在服务端钉住 output id；`plan_ref` 经 Decision Package 快照解出节点集；图结构手术使用 graph node id。目标缺失或 legacy 映射不可证时按当前工具反问或诚实降级，agent 永不靠列表位置猜 scope。边界判定：

- 指令需要重新生成（改意图 / 改程序）→ **wiring ops**（§5）——`edit_prompt(node)` 改写程序行 + `run({node} ∪ downstream)`（下游由图边遍历确定）；卡面 prompt 直改 = 同一个 op、**确定性通道**（ADR-058 通道分家 + ADR-063 动作内化：定价确认住进程序区——锚定受影响子图 chips、估价随行就地展开，确认后 ops 由代码构建走 `POST /projects/{id}/graph/revise`——直改是手势不是意图，**dock 零消息**，节点状态周期 = 全部反馈，卡面乐观回显永不回闪；chat 唯一意图面不变）。
- 指令能表达为对某个 output 的 clip-spec diff（trim / 字幕样式等参数精确指令）→ **edit ops** → Operation Model（operations 表）——作为**节点内部**的产物级精修存活。
- 改稿 = 资产内容层覆盖写（ADR-113）→ `PUT /projects/{id}/assets/{id}/transcript`（素材卡转写区就地编辑，overlay 层）——零 run 零积分，**不是 wiring op 也不是 edit op**；源层词级时间戳永不动。改稿驱动重剪（edited transcript → 词轴对齐 → 影响产出）是 PLANNED、未实现，触发条件与验收归 `docs/tasks/media-card-anatomy.md`。
- 拿不准 → ask_user 反问（**反问是合法输出，不是失败**）。

edit ops（ADR-032 D5 + 现行规范 `VIDEO_EDITOR.md`）：产物级 op = `remove_range` / `set_trim` / `set_title` / `set_caption_style` / `set_music` / `set_crop` / `set_aspect` / `set_caption_text` / `restore_version`（+ system 内部 `snapshot` / `set_spec`），chat 已真应用（registry 校验 + message_id 血统）；**plan 级 op（`set_node_params` / `regenerate_node` / `swap_slot`）归 RunPlan 小拓扑，不进 operations 表**——两家族分开登记；`restore_range` 独立 op 否决（判例 N-16：caption 不可复活，恢复语义归快照层）。

## 10. 失败语义

- 单节点失败：保留真实 failed 的安静告警；run/delivery 按实际 delivered/partial/failed 收官，对话继续。需要用户选择时只给当前可行、至多两个选项，不编造固定问答。
- tool 持续拒收或 loop 预算耗尽：回复确定性原因与当前可行承接；difflib 相近匹配和完整拒绝细节只进内部 repair/诊断，不把注册表或工具名清单抛给用户。
- **同语目标死链 = 编译期裁决，不跑到 run**（ADR-074①）：translate/dub 的目标语言 = 实际面对的源语言即拒——chat 侧 = present_plan / propose_tasks 的执行内校验，拒绝反馈回 loop 重拟（修法指名、方向感知：zh 源双语目标 en / en 源目标 zh；再拒 degrade 答话，永不 dock 死链），出生地 422 兜底所有 Start 与确定性修订（钱动之前拒）；语言未知不猜测，需要目标判断时提问或诚实降级，运行时护栏只是最后兜底（陈旧计划 / wiring 出生 run）。
- **run 判决（ADR-074② + ADR-135 修订）**：任何非 runtime-fanout 步骤 failed ⇒ run FAILED——部分失败不再有绿收据（收据红 ✗，§8.7）；部分失败（有产物落地 = done 且带 `output_refs` 的步骤，预备步不算）= project → REVIEW + 收官句说部分真相 + 完成 refetch 照发；全灭 = project → DRAFT + **`run_failed` 触发回合开口**（确定性失败原因 + 至多两个可行选项，§8.8；确定性死因不提供原样重试）。render fanout 失败永不是 run 判决（产物级事实，画布卡红 + 重试入口）。

## 11. 当前边界与后续工作

当前 tool registry、mentions、chat-born Candidate Surface、精确 edit ops、SSE/Activity、报价与授权机器同属现行系统，不再按 v1/v2/v3 分期判断行为。后续工作只登记仍有实施或验收欠账的部分：

- `synthesize_talk_video` 是 R5 的不可派发 seat；完整目标、媒体/声音前提和验收归 `docs/tasks/synthetic-talk-video.md`，不得把 seat 当成已交付能力。
- Agent Tools 长程序修订、Candidate Surface live/replay、CJK 长素材检索与探索存储真实 DB 迁移的验收归 `docs/tasks/agent-working-loop-iter-3.md`。
- `edit_graph` 只有在现行工具覆盖、生产引用与存量读/迁移结论齐备后才可退役；`propose_tasks`、`select_clips` 等当前工具不得被目标架构文字提前删除。
- 精确编辑的自然 pin/model 分歧、归档/恢复与真实 run 验收归 `docs/VIDEO_EDITOR.md` §11 和 `docs/tasks/verification-contracts.md`。
- 优先级、发布阻塞和其他开放项以 `docs/PROGRESS.md` §0 为准；本文不维护第二份排期或施工日志。

## 12. Prohibited Behaviors

- **禁止**无界 / 执行 loop——chat 侧 = 有界工具 loop（终态工具一调即停 + 迭代上界）；生产层执行 loop 永拒（ADR-077 边界不变）。
- **禁止** LLM 直接写 node spec / 自由生成执行代码——一切经 registry + compile_graph。
- **禁止**引入 agent 框架（Agno / LangGraph 等）。
- **禁止**把 run progress SSE 做成通用事件总线或另建事件存储/投递保证；Chat transcript 回放只读既有 typed、有序消息行，不因此新增第二事件日志。
- **禁止** chat 绕开 `orchestrator.create_run` 自建 run（零旁路原则不变）。
- **禁止**画布绕开持久图自建可写平行事实源；布局、rank 等只读派生必须可重算，不反向拥有图语义。
- **禁止**图结构变更绕开 `apply_wiring_ops`（wiring 层 = 唯一写口）；**禁止** LLM 簿记上图（wiring op 的图面命名走 builder 钢印——执行期模型自报与冻参模板永禁；**提案时刻** LLM 经 schema 闸门命名〔`name` 字段〕是展示文案两个合法来源之首，ADR-058）。
- **禁止** echo 编造平台或场所（ADR-060 防编造律）——回声只回述用户说过的（作品 / 语言 / 数量），永不发明 LinkedIn / X / newsletter：a post is just a post until the user names where it lives；post 类工具 / 摘要 / 标签 / 例句 / writer 人设全渠道中立，渠道的合法来源 = 用户点名或渠道授权，永不是默认值。
- **禁止**冻参模板当用户文案（ADR-058 展示文案二源律）——命名类文案只许 LLM 建图时命名或世界自证（产物徽标 / 节点状态 / 真实数字）；参数 = 不可见执行事实，永不拼接成标签说话。
- **禁止**给确定性手势配 chat 回声（ADR-058）——卡面直改走 `graph/revise` 零消息通道；节点状态周期就是反馈，回声 / 收据 / 完成行都是多余言语。
- **禁止**给裸肯定句（"yes" / "好" / "对"）加确定性词表短路（有 pending 计划上下文时 LLM 该理解自然语言，短路 = 画蛇添足；偶发误判的伤害面由同名链命名继承 + draft 图翻转通道兜底）。
- **禁止**工具名上用户面——工具调用只经 Activity 帧叙事（注册项 activity_key 的人话），名字永不越线进用户文案。
- **禁止**一个 run 在消息流里开两个渲染面（**单一渲染面律**）：dock 已 attach 的 run 只经 runStreamUnits 渲染（活态打勾流 → 终态收据，锚在 run 时序上）；生产行的 `workflow_run_id` 章是**归属关联不是渲染触发**（排序锚也不是——收据锚在 run 结束刻，ADR-073）。detached（无 dock attach）的 run 才走内联 RunCard——那是它们唯一的面。
- **禁止** registry 无评审膨胀——tool 准入必须过 NAMING §7/§8。
