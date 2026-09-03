# Chat Architecture — Agent Interface 层

> Status: ✅ v2 已实现（意图层单面化：`POST /chat` 是唯一意图表面，任务书构建/修订/确认并入 book path；2026-08-18 复核对齐代码）。意图覆盖现状见 `INTENT_COVERAGE.md`；实施史简报归 `docs/tasks/done/`。
> 上游决策：ADR-028（RunPlan）/ ADR-029（plan 级 dispatch）/ ADR-030（产物统一）/ ADR-032（edit ops）/ ADR-039（架构规范级大迭代：本文 = 四层工程地图的 Loop 层行为规格；技能包收编注册表、`kind`/`cost_hint` 字段退役、agent 正名，见 §4）
> 命名遵循：`docs/NAMING.md`；模块归属：`docs/MODULE_ARCHITECTURE.md`（Agent Interface：conversations/messages）；chat/ 包是本文的代码家。
>
> 关键形态事实：
> - 拓扑约束用 `requires`（输入校验）+ `after`（顺序约束）表达（AGENT_ARCH §4  NodeBase）。
> - `synthesize_talk_video` 已登记未实装（seat 座位，不可派发；归 R2，见 RECIPES §8）。
> - 提及系统 = 双端注册表架构（前端 `MENTION_REGISTRY` + 服务端解析注册表，方针 MENTIONS §4）；配方不是 mention——配方 = 提示词（ADR-040）：发射的全部行为载荷 = 预填模板原文，无 `recipe_id` transport、无服务端播种，book path 与 composer 完全同径（chat 修订永远赢）。
> - SSE 统一由项目页 dock 打勾流消费（`useRunEvents` / fetch-event-source；2026-08-31 ADR-051：`?overlay=` 路由参数与 fullscreen 壳退役，processing 项目直达项目页即 attach 活 run）；step 状态枚举含 `waiting`（HITL/suspend-resume，§8.5）。
> - **ChatDock 两态形态机 + 三可见性态**（2026-09-02 ADR-051 条款 7）：项目页 chat 外壳 = 一台消息机器两种布局形态——首个 run 前 = 居中全屏 chat（full：消息舞台占满页面上部，左上角仅返回 pill，画布未显现）；首个 run 到达同一拍收拢变形为底部 dock（dock：画布淡入，返回 pill crossfade 成完全体 ProjectMenu；驱动 = 页面 `latestRun`，loading 闸定态，水合首帧永不重播）。dock 形态下三可见性态 = 收起（输入组常驻）/ 展开（历史浮为**自有磨砂层**悬于输入组上方——2026-09-02 输入框独立层律：输入组恒为独立一层，永不与消息流融为一体；原「历史在同容器内上长」同批作废）/ hidden（用户手势收成右下角 LogoMark 点；唤回 = agent 发声 / 待决提问 / 焦点注入——只能藏静态输入组，藏不住新信息）。组件 GenerationOverlay → ChatDock 同批改名（`components/chat/`，`generation/` 目录退役）。

## 1. 定位与三条原则

Agent Interface 是六层模块图里"意图 → 执行"的唯一入口。用户的三张脸——composer pills、composer 自由 prompt、chat 对话——在它这里汇成**一条机制**：

```
task list（LLM 提议）→ compile_graph 校验/排序/补默认（代码裁决）→ workflow_steps（施工图）
```

1. **LLM 提议，代码裁决**。LLM 只出"干什么"（task list），拓扑正确性（skill 是否存在、顺序是否合法、参数默认值）全部归 `compile_graph`。LLM 永不直接写 node spec。
2. **轮内一次调用，轮间才是循环**。每条用户消息 = intent agent 单次调用（信道 = JSON-in-prompt 约定，非原生工具协议）→ task list → 编译 → 跑。不做 ReAct 式多步推理；"循环"只发生在对话轮次之间。
3. **composer = chat 的第一条消息**。composer 发送 = 建项目 + 上传素材 → 直达项目页画布+dock（2026-08-31 ADR-051：`?overlay=chat` 路由参数退役），草稿经 router state 交付 dock 作为第一条 `POST /chat` 消息发出（mentions + `persona_id` 随行）；空指令由前端本地拦截（toast）——compile_graph 只有技能链一种入口，full scope 无 tasks 直接拒生。

## 2. 一次对话指令的完整生命

```
用户: "去掉口头禅，剪 3 条高光，加个音乐"
 │
 ▼
chat/service.py ──► intent agent（LLM 单次 tool calling，带 §6 上下文）
 │                   输出 task list（提议，无执行权）:
 │                   [{skill:"remove_filler"}, {skill:"select_clips",params:{count:3}}, {skill:"add_music"}]
 ▼
SKILL_REGISTRY（技能包收编）  校验：skill 已注册？参数过 schema？
pipeline/orchestrator  compile_graph：拓扑排序（配乐殿后）+ 补默认值
 ▼
workflow_steps（动态 DAG，3 步骤 + render fan-out）── worker 认领（SKIP LOCKED）
 │
 ▼ 执行中
node.spec.summary = "Removed 12 fillers · 3 repeated takes"（量化摘要，§7）
 │  经 SSE 推送（§8）
 ▼
打勾流逐行亮起 → outputs（render_status=PENDING）→ Remotion → MP4
 │
 ▼
recap（技能行聚合）：Selected 3 clips · 64s total · Removed 12 fillers · 2 repeated takes
 │
 ▼（下一轮：改现有产物而非跑新任务）
"第二条再短一点" ──► intent ──► edit ops ──► Operation Model（📋，§9 边界）
```

## 3. Task List 契约

intent agent 的轮内输出四态（N-18 三态 + N-21 第四态，均已落代码），JSON schema 强校验：

```jsonc
// A. 跑新任务（→ compile_graph → 新 WorkflowRun）
{
  "type": "task_list",
  "tasks": [
    { "skill": "remove_filler", "params": {} },
    { "skill": "select_clips", "params": { "count": 3 } },
    { "skill": "add_music", "params": { "mood": "calm" } }
  ],
  "summary": "去口头禅、剪 3 条高光、加舒缓配乐"   // 给用户看的一句话
}

// B. 改现有产物（→ Operation Model，v2）
{
  "type": "edit_ops",
  "target_output_id": "uuid",
  "ops": [{ "op": "trim_segment", "target": "seg_03", "params": { "end_delta": -2.0 } }],
  "summary": "把第二段结尾剪掉 2 秒"
}

// C. 结构化提问（→ QuestionDock；N-18）
{
  "type": "ask",
  "question": "这五个切片你想做成哪种方向？",
  "kind": "choice",                 // choice | task_book | confirm（成本 quote 预留）
  "options": [{"id": "a", "label": "…"}, …],
  "allow_freeform": true,
  "estimate": null
}

// D. 纯信息直答（→ 普通 assistant 消息；N-21，期 4 补四已落代码）
{
  "type": "answer",
  "text": "发布不在 chat 里——产物卡上有发布按钮。"
}
```

`summary` 字段必填——它是打勾流的标题文案，也是消息记录里"这轮干了什么"的人话存档。

### 3.1 book path：任务书的构建 / 修订 / 确认（2026-08-04 单面化）

`/chat` 是**唯一意图表面**。`chat()` 在 autoResume 之后按状态分派：project scope 且（有 pending task_book question / 刚回答了带 `slot` 的提问 / 无任何 run 且 `pending_brief` 为空或是 ledger-only 行）→ **book path**；其余 → 上述四态提案。

book path 的推理者是 **intent router**（四动作 verdict，ADR-052 B2）：

- `draft` → reasons 推导（chain_default / clip_count_default / clips_without_media / text_without_material）→ **derived 预览**（ADR-043：服务端干跑 compile_graph 产出「你将得到」投影行，随 pending_brief 持久化）→ `sync_task_book_question` dock。**任务书载荷 = 技能链（task list），无合并机械**：面板手改 = 对 task list 的直接结构编辑（数量步进器绑 select_clips.count、语言下拉绑各任务的 language 参数、删行 = 移除技能），编辑后的整链 ride prior_intent 注入推断上下文，intent router 重提全链（「保留本轮未修订的每个任务」写进 prompt），chat 恒胜——merge_prior_slots 三方合并 / explicit 钉随之退役。**整条源规则**（ADR-043 考纲原点）：「给我的视频加字幕 / 配音」类请求 = 变换技能单独成链，永不夹带 select_clips——编译期自动注入内部节点 `materialize_source`（确定性全段 clip-spec，无 LLM 选段；出生地画像分发：media 直挂 preprocess / stills 先 align_stills / 项目有既有 clips 不注入 = 作用于现有 clips / 无源可作用 = 编译期 422 指名拒绝，永不静默丢弃）
- `ask` → **一等动作直通 dock 提问机器**（ADR-052 B2 D2-C1，caption-mode 特例泛化为正典）：`_dock_question` choice 形态，payload 带 `slot` 握手（作答由 autoResume 回填账本槽位 user-stated，回 book path 重判）+ `default_path` 牙齿（dock 散文第二句——每个问题都可安全跳过；choice bail + slot 以替身行恢复 book turn，走到默认路径出书）。账本合并落 ledger-only 行（`intent=None`，桌上存书原样保留）。同槽位重问被代码翻回 draft——问环有界
- `answer` → 普通 assistant 消息，stored 任务书不被动
- `start` → 复用 answer kind=start 路径起 run（唯一出生地）；dock 中的任务书以 `presented_book`（整链 JSON）注入推断上下文——短确认看得见自己在确认什么（2026-08-04 硬化，此前裸"开始吧"在模糊首轮后 2/3 误判 generate）

**出书门槛（ADR-052 B2 D2-C2，draft 判定后的代码裁决）**：任务书只在 brief 有根时 dock——根 = topic 有值 ∨ material_state ≠ none ∨（tasks_explicit ∧ specific_instruction 非空，即明确点名的落地配方）。无根 → 代码组装 topic 问一轮（choice dock，slot=topic，asked 簿记防重问）；问过仍无根（或用户跳过提问）→ draft-from-persona dock：`draft_from_persona` reason + 代码组装 echo 散文声明（「按你的人设风格起草了这版——直接开始就行」）；media-needing 链 ∧ material none ∧ 桌上无书 → answer 素材引导（上传或贴文），永不 dock——零素材反问网与 copy-writer 无素材 lift 两补丁同批折叠进此门，`_ask_for_material_text` 退役。

修订回合的累积状态 = **brief 账本**（ADR-052 B2，取代累积 prompt 拼装）：topic / audience / tone / constraints / material_state 五槽位各带来源（user-stated > inferred > default——LLM 每轮提议全量更新，代码 `merge_brief` 按来源优先级落账：user-stated 永不反向覆盖、重申恒胜；`asked` 簿代码自持防重问，永不吃 LLM 提议；material_state 代码钢印 post-merge 无条件覆盖——attached / pasted / none 看项目事实不看 LLM）——`pending.prompt` = 出生 prompt 冻结于首次 dock，`MAX_ACCUM_PROMPT_CHARS` 同批退役，composer/前端永不构建累积 prompt 或 prior。intent router 的装配面（`_assemble_book_turn`）：本轮消息 + **brief 账本块**（值槽带源 + material 行恒在 + asked 簿——根判断与防重问读它）+ 文件名 / file_language / material_excerpt + `presented_book` + 最近 5 轮对话（"Recent conversation"——G-7：素材/请求判定需要看见"上一轮刚被要素材"，短贴文曾在真空里被系统性误判为非素材形成反问死循环；只喂上下文不加倾向规则，判定归 LLM 凭语境完成，同 presented_book 硬化先例）。intent router 的 provider 故障不兜底：MiniMaxError 直接穿透到 chat 路由边界——SSE 终帧 `turn.failed` / JSON 502 都带 `user_error_line` 本地化行（provider 错误人话化梯），永不 dock 编造默认书（错误计划看着像真的，Start 会为它烧一次付费 run）；`tasks:null` 等松散输出由 schema 读容忍接住（存量 outputs/簿级修饰符形状的 pending_brief 行同机制升级，只读不写）。**失败行的呈现 = 入流灰行**（2026-08-15 裁定，Claude Code 内嵌用量上限行同款解剖）：turn.failed 的本地化行渲染为消息流里的灰色 MetaRow（TurnErrorRow），永不用 toast——回合失败是对话里的事实，不是外加 chrome；服务端对失败回合零提交，灰行本地瞬态、刷新即失（历史保持诚实：没有任何回答发生过）。run 级失败同理无 toast——失败步骤行已带人话错误入流。

### 3.2 四态边界规则

**answer 态边界（写死在 agent 规则里）**：只在无工作请求且无歧义时用（能力/进度/解释/闲聊）；要干活 → task_list/edit_ops；读数有歧义 → ask——answer 永不当偷懒出口。进度问题凭 §6 的节点级进度段照实答；发布意图 → 引导到产物卡发布按钮；品牌/说话人等身份设置 → 导航到对应页面。

**answer 契约**（期 1 已落，期 4 补修订）：`{kind: "option"|"freeform"|"bail"|"start", option_id?, text?, answered_at}`。bail 是一等公民——入口回 draft 可重开、checkpoint 下游级联 skipped（期 4），**永不标 failed**；`start` 是 task_book 确认的一等 kind（取代期 1 的魔法 `option_id="start"`）。请求体 `AnswerRequest` 是按 `kind` 判别的联合（option/freeform/start/bail）——`autonomy`/`intent` 只存在于 `start` 上，其他 kind 带 kind 外字段直接 422，不再静默忽略；task_book 问题只接受 start/bail，其他问题不接受 start。N-14 的"tasks=[] 反问"届时迁移为 ask 的 freeform 形态（options 空 + allow_freeform）——反问仍是合法输出，只是有了类型座位。

### 3.3 intent router 顾问姿态（2026-08-05 立；PROGRESS 第二周施工）

来源：一份真实顾问对话样本（用户 = 目标画像：有素材、不懂自媒体、助理也不懂）。book path 不只是填任务书——**用户到来即彷徨，agent 是接住彷徨的人**（哲学论证 → STRATEGY §5）。四条行为规格：

1. **每轮一问、每问可一词答、散文恒带默认路径**（ADR-052 判词 5，B2 落地，取代"诊断一轮封顶"）：提问只问决定质量的缺失槽（听众 / 目的 / 场合——答案会改变任务书形状的问题），不问用户不懂的（画幅 / 参数 / 样式，由配方卡与默认值吸收）；选项 2-4 个一词可答 + freeform 恒在；每个 ask 恒带 `default_path`——**每个问题都可安全跳过**，跳过即走默认路径出方案（draft-from-persona）。诊断是手段，出方案是目的——**不做职业 / 变现咨询**。
2. **带理由纠偏**：用户点的东西做不出或与素材不匹配（无 media 要 clips、两小时讲座要 20 条）→ 拒绝 / 降级时必须给理由 + 替代方案，禁静默排除（现状 `clips_without_media` reason 是雏形，升级为建议形态）。
3. **成功定义随任务书**：dock 的计划摘要携带"什么叫成了"（本批产物的验收口径），schema / overlay 同改，结果页对照呈现。
4. **按素材画像推荐配方**：输入画像命中某张 live 卡时主动说"照这张卡做"（读 `RECIPE_REGISTRY` 公开面；reserved 卡永不推荐——点亮纪律不变，RECIPES §8）。

验收：迷失用户横切变体 S17–S21（`scripts/chat_scenarios.py`，散入路由/咨询/修订/边界/素材五族而非独立成块——迷失是用户状态，不是意图类别；S1–S16 不得回归）。

## 4. Skill Registry 初集

> 注册表收编进技能包（ADR-039）：`skills/__init__.py` 汇总各包声明建成 `SKILL_REGISTRY`（静态注册表随代码部署）；执行者是 agent 还是机械 = 技能包的构成（N-31），无 `kind` 分类字段；估价 = 节点 `estimate()` 函数（N-34，`cost_hint` 三档退役）；节点 kind = 技能名（N-35）。

每条登记：

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

注册项只持提议/展示数据——执行与拓扑知识（`run` / `requires` / `retries` / `after` / `estimate`）住同名节点类（N-35），注册项没有 runner 字段；`seat=True` = 已登记未实装（不可派发）。

**准入纪律：skill 总数十几个封顶。** 新 skill 准入 = 过 NAMING §7 同款评审（用户会用自然语言说到它吗？现有 skill 组合能表达吗？），通过即登记（§8 词汇表）。

**扩展门纪律（2026-08-05 立）**：加功能 = 往注册表填一项，没有第二种方式。登记一项（注册项 + 同名节点类）自带全家桶——节点类声明的 `retries`（步骤级重试预算）、`requires`（出生地输入校验）、`after`（拓扑约束）、`estimate`（估价）与注册项的 `summary_templates`（进度文案）全部随登记免费获得；节点类落进 `NODE_KINDS` 即被编排/工作流/SSE 打勾流自动接管。**禁止侧门**：不为某个节点单开映射表/特判分支（如平行的 retries 表）——那是"房间本来有门又造了侧门"，发现即拆。内部节点（§4.3）不登记，但它们的扩展同样优先审视能否表达为注册项。

### 4.1 已在（反向抽象登记）

| skill | 技能包 | summary_template 示例 |
|---|---|---|
| `select_clips` | `skills/clips/`（含选段编剧 agent 声明） | "Selected {n} clips · {total_seconds}s total" |
| `write_post` / `write_quotes` / `write_carousel` / `write_article` | `skills/posts·quotes·carousel·article/` | "Wrote a LinkedIn post · {word_count} words" |
| `revise_script` | `skills/revise/` | "Revised hook · {reason}" |
| `dub_clip` | `skills/dub/`（私有工序 + 共享 translator agent） | "Dubbed {n} clips · {lang}" |
| `translate_clip` | `skills/captions/`（词级时间摊铺工序） | "Translated {n} clips · {lang}" |
| `add_music` | `skills/music/` + clip-spec music 槽 + `tools/music.py` | "Scored · {mood} bed" |
| `align_stills` | `skills/stills/`（阅读节奏估算时间轴） | "Aligned transcript · {n} words · {total_seconds}s" |

### 4.2 新增（按价值排序，独立排期）

| skill | 状态 | 说明 |
|---|---|---|
| `synthesize_talk_video` | 📋 任务简报 `docs/tasks/synthetic-talk-video.md`；声音路径随第四~五周声纹/R5 线落地（R2 已先行交付无声版，RECIPES §4.2） | 文字稿+照片+声纹 → 合成发言视频（生成端 v1） |
| `remove_filler` | ✅ 已实装可派发（chat 线 hello world 已跑通） | 词级时间戳 + filler 检测 → 标 hidden（非破坏）→ 重渲染 |
| `make_hook` | 📋 半新 | ≈ `revise_script(scope=hook)` 的独立入口 |

### 4.3 不登记

- **管线内部节点**：`preprocess` / `persona_bootstrap` / `understand` / `plan` / `checkpoint` / `render` / `materialize_source`（ADR-043：整条源材料化，编译期注入——链含 clip-spec 消费者而无 select_clips 时把项目主源落成一条全段 clip-spec）——拓扑的组成部分，不是用户可选技能。
- **`infer_intent`**：它是 loop 的入口，不是 loop 可调用的一项。
- **edit ops**：Operation Model 的词汇（§9），产出 clip-spec diff 而非 run——两个家族分开登记。
- **judge/verify**：Phase 3 节点 kind，非用户技能。
- **缓议**：`adapt_to_platform`（等 Distribution 回流数据）、`insert_broll` / `motion_graphics`（talking-head 知识内容价值低）、`avatar_gen`（v2，ADR-029 已定框架）。

## 5. compile_graph：任务列表物化

`compile_graph` 的全量入口只有技能链一种（task list；targeted scope 走各自的定向小拓扑，full scope 无 tasks 直接拒生）：

1. **校验**：task list 每个 skill 必须在 registry；params 过 schema；不认识的 skill → 拒收并让 intent 修复一次（retry 1 次），仍败 → 回复用户"这个我还不会"。
2. **拓扑排序**：拓扑约束 = 节点类声明的 `after`（顺序）与 `requires`（出生地输入校验），无 ports / 类型边机制。生成技能共享一份去重的 plan 前奏（preprocess → persona_bootstrap ∥ understand → plan）；修饰技能（`needs_plan_prelude=False`，如 `add_music` / `remove_filler`，`after=("select_clips","materialize_source")`）挂在 clips 节点或注入的 `materialize_source` 之后、渲染 fan-out 之前跑（render 节点运行期物化，D2），多个修饰节点按提议顺序串链。
3. **补默认值**：`select_clips.count` 缺省 = 项目默认 / brand 默认 music 等，全部由代码补，不信 LLM 的缺省判断。
4. **落图**：产物是标准 `workflow_steps`——之后走图、认领、计量、打勾流与既有 run 零差异。**动态化只发生在编译前，编译后零差异。**

## 6. 对话上下文（context 组装）

确定性代码组装，不是塞聊天历史（代码家 = `agents/contexts.py`——harness 输入侧，ADR-039；chat service 不持装配逻辑）。每轮 intent 调用组装以下段落：

| 部分 | 内容 | 来源 | 预算 |
|---|---|---|---|
| 项目摘要 | 素材清单、当前 outputs 列表（type + 一句话）、latest run 状态 + **节点级进度**（每步一行 `kind: status — summary`，≤12 行，G-2） | DB 确定性生成 | 4k |
| 焦点注入 | 画布所指产物一行（ADR-041 D8） | DB | — |
| 最近操作 | 近 3 轮的 task list / edit ops 及结果摘要 | messages | 2k |
| 待决问题 | 未答问题原文 + 选项（防重问——下条消息可能就是它的答案） | messages | — |
| mentions | 本轮消息已钉的 @ 实体（确定引用注入，§7） | 请求载荷 | 1k |
| 早期摘要 | 超窗对话压缩 | 未实现（v3，§11） | 2k |

## 7. Mentions（@ 实体引用）

> 提及系统 = 双端注册表（前端 `MENTION_REGISTRY`：icon / i18n / 候选源；服务端效果注册表按类型富化上下文）。可 @ 实体三条注册项：**asset / output（某条产物）/ workflow step**（step chip 只从结果画布点进程节点进入，@ 选择器不列步骤）；新 @ 类型 = 双端各一条注册项，无类型分支。配方不是 mention（MENTIONS §3：配方 = 提示词，卡面预填模板即全部发射载荷，ADR-040）；`recipe` 与 `transcript_segment` 仅是类型残留（未注册、不可新建；历史消息行的 chip 还能画出）。

多轮对话的模糊指代必须落为确定引用。

- 前端输入框 @ 触发选择器，`messages.mentions` JSONB 存 `[{type, id, label}]`；
- intent 收到的 prompt 中 mention 已替换为确定 ID 引用，LLM 解析歧义降一个量级；
- "把第二段高光换掉"无 mention 时，intent 可反问澄清——**反问是合法输出，不是失败**。

## 8. 进度推送：SSE = 推送优化的读

**定位：SSE 是 DB 状态的推送管道，不是事件总线。** 事实源唯一 = `workflow_steps` 表，因此无事件存储、无投递保证、无重放——断线重连 = 重读当前节点状态，天然幂等。

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

**前端实现**：`useRunEvents` hook 统一消费这条流，接项目页 dock 打勾流（2026-08-31 ADR-051：fullscreen 壳退役、dock 壳唯一形态；计划卡 HITL 确认 → **折叠打勾**——默认折叠一行：shimmer 状态行 + 当前步名，点击展开步骤日志 → 终态 toast + 结果页 refetch；run 期画布活：占位产物卡 run 开始即物化〔derived preview 投影〕、产物落地原地填充）。轮询只保留给无 token 的匿名场景与"run 已终态但 clip 仍在渲染"的尾部阶段。

**进度面**：进度 UI 只留打勾流一处（ADR-051 浓缩为默认折叠一行，展开才见步骤日志——形态变了，唯一进度面不变）。`processing` 项目卡片直达 `/projects/$id`（`?overlay=run` 退役）：项目页 dock 自动 attach 到活 run（无确认阶段、无 intent 兜底推理，计划摘要行由 `latest_run.context` 重建）；run 排队/素材处理中（步骤流为空）显示 transcribing/queued 占位行。attach 的 run id 由页面 latch（不靠活态重判），避免页面自身 SSE refetch 把 run 翻成 completed 时打勾态中途卸载。

**计划确认的持久化与恢复**：book path 的 generate 回合把未确认的任务书 + 原始 prompt 写到 `projects.pending_brief`（字段 = prompt / intent / reasons / persona_id / derived 预览；answer 回合不写，免得覆盖用户在确认的计划），run 启动时清除（answer kind=start）。`draft` 项目 ⟺ 待确认：项目卡片显示"待确认"并直达 `/projects/$id`（`?overlay=chat` 退役），项目页无 run 时 dock 呈现"继续设置"任务书——两处都能精确复活同一份计划（跨设备；卡片上的手动微调不入库，恢复的是最近一次推理版）。

### 8.5 QuestionDock 与 question/answer（提问机器，期 1/3 已落）

> **消息列表是"已决"的历史，输入框上方是"待决"的现在。**

- **一行两态**：`messages.question` JSONB（typed payload：`{kind: task_book|choice|confirm, options, allow_freeform, estimate}`）+ `messages.answer` JSONB nullable（**NULL = 待决**，宪法 §4）；`content` 存问题人话原文（自然进 LLM 上下文历史）。
- **停靠法则**：待决问题永远停靠 input 正上方的 **QuestionDock**——形态 = **独立浮层 pill**（2026-09-02 ADR-051 条款 8 拆粘：不再焊进输入容器，悬在其上方、小间距，恒可见不随计划卡滚走；问句 + estimate? + 按钮组含 bail；**2026-08-31 形态切换**：choice 待决时输入行与免责行隐藏，pill = 问题行〔去 ✓——待决不是已完成；加 × 关闭 = bail 通道〕+ 选项行 + **尾行铅笔手输入**〔Enter 提交 freeform〕；回答后坍缩回基础形态）；**同一时间最多一个待决**——新题落库前旧题 auto-bail（`answer.text="superseded"` 机器标记）。回答瞬间坍缩成**已答问题双层消息**入流（`AnsweredQuestion`）。
- **待决重建零内存态**：`latest_pending_question` = 会话最新未答 question 的行查询（Mastra `listSuspendedRuns` 同款），GET `/chat/conversation` 带 `pending_question`——刷新/跨设备 dock 复活免费。
- **answer 端点即恢复**：`POST /chat/messages/{id}/answer` 写答案即解除阻塞（不显式命名 resume）。task_book 分派：bail → 清 pending_brief 回 draft（prompt 已 seed 进会话，可重开）；`start`（一等 answer kind）→ 从 pending_brief 起 run 并写 `workflow_run_id`。choice 分派（期 3）：记录后续聊——响应 `AnswerResponse{answered_question, follow_up}`（与 `ChatResponse.answered_question` 同角色同名，B2），option 答案回填 label 进 `answer.text`。重复回答 409。`/generate` 路径丢弃未答的 task_book 问题行（`discard_unanswered_task_book`——run 起于未答即无问答交互，问题行直接删除，历史不留伪造问答；真正的确认仍走 answer_question 结算）。
- **book path 回合形态（B1/B4 + G-1，2026-08-04 自 /intent 迁入）**：dock 任务书 = `ChatResponse.assistant_message` 携带 pending task_book question 行；answer 回合的答复落普通消息行且**不覆盖 stored 任务书**；原话确认（G-1：intent router 判 `start`）复用 answer kind=start 路径起 run，`ChatResponse` 携带 `run_id` + `answered_question`（dock 的 autonomy 档随 `ChatRequest.autonomy` 透传不丢档——打字确认与 dock Start 同待遇）；无可启动对象时 re-dock 存量书或降级 plan，同样不覆盖 stored 任务书。`needs_clarification` 布尔已摘除（`reasons.length > 0` 可推导，存量行读取容忍）。修订回合发 brief 账本做推理（LLM 提议、代码 merge，见 §3.1），每轮用户原文各自入档。
- **入口约束归出生地（期 4 补）**：clips-media 门、slot count 边界（节点 `count_limits` 声明派生：clips 1-10 / quotes 1-20 / carousel 2-15）、targeted scope 校验、链上技能的 `requires` 全部在 `create_run` 内拒绝（ValueError → 请求层 422 / chat 层反问兜底）——`/generate`、task_book start、chat 派发三条入口不再各持一份 guard。`create_run` 只 flush 不 commit：run、启动它的 answer、project 状态落在同一请求事务里，提交点唯一。
- **task_book 形态（期 1；卡面 2026-09-02 瘦身，ADR-043 附）**：计划卡留在消息流做审阅面板（编辑属流内）——卡解剖 = 任务行（唯一编辑面）+ 增量派生（仅 materialize 家族；节标 / hint / identity 行退役），instruction 空开（蒸馏照进 run、机器预填退役，用户补充 ship 时合并），echo 散文 ≤2 句带成功定义，clips 无素材 = 行内警告；Start 决策 + **Auto/Review 自治档**移入 dock——pill = 单行（✓ + 问句 + Start，恒 `rounded-xl`；2026-09-02 ADR-051 条款 8：**Cancel 退役**——非阻塞提问不配负向动作，放弃 = 继续聊修订 / 走开留待确认 / 删项目；负向动作只在阻塞态存在，choice 的 × 保留。stadium 归坍缩态输入组不归 pill）；`autonomy` 经 AnswerRequest/GenerateRequest/`TaskSpec` 落 run.context（行为期 4 生效：review 档 full run 插方向 checkpoint，auto 档与 targeted 不插）。needs_clarification reasons 随 question 落库（数据存键）：键本身永不直渲成用户文案（推断簿记不是 UI 文案）——只驱动 auto-start 备妥判定（reasons 空 = 无疑点）与卡内行内警告（`clips_without_media` 触发手写的本地化 amber 行，是 authored copy 不是键直渲）。
- **choice 形态与 autoResume（期 3）**：dock 渲染选项按钮组（字母徽章镜像映射规则）；待决中自由文本确定性映射——命中选项字母/序号/原文 → option 回答，否则 allow_freeform → freeform，否则按新 intent 处理、问题保持待决（零 LLM；task_book 待决不参与）。`ChatResponse.answered_question` 携带本回合掉的问题行供已答问题入流。成本 quote（confirm 形态，estimate 解剖位已预留）归 v3。
- **checkpoint 形态（期 4）**：方向检查点是 choice 问题 + `workflow_run_id` 分派标记。`Suspend` 异常把瘦节点停进 `waiting`（选项住 `spec.suspend_payload`）、run 停进 `WAITING_HUMAN`；答案端点/autoResume 写 `spec.answer`、节点回 pending、run 回 RUNNING——队列式重入（runner 从顶上重跑，answer 分支直达 done），不是调用栈续跑。选项代码派生自 `key_arguments`（零 LLM）；**准入（2026-09-02 用户拍板）**：`key_arguments` 为空 → 选项只剩默认项 → 单选项无分支，不 dock 不 Suspend，runner 自动按默认项决议（`spec.answer` 与 human pick 同形状，`_interrupt_direction` 读法不变）——writer-only stub understanding 必中此分支（「Full-talk highlights」是 clips 话语，对 post 任务书错体系），review 档不再为无分支问题停车；bail = 节点 done(spec.bailed) + 下游级联 skipped("user bailed") + run COMPLETED（永不 failed）；`plan` 经 `task_book.direction` 消费（option → 优先论点，freeform → 指引原文，默认 → 现状；slot.focus > checkpoint > plan）。**过期**：park 超过 `checkpoint_expiry_seconds`（默认 30 分钟）由 worker 扫描自动以默认项回答并续跑（`answer.text="expired"` 机器标记；review 档超时降级为 auto 档，兑现"离开不中断"，永不 auto-bail）。**多 run 并停**：新题 dock 取代开口 checkpoint 题时同笔级联 bail 那个 run（`finalize_bailed_runs` 收官 COMPLETED）——单待决不变量不会搁浅 run。

**量化摘要**：`node.spec.summary` 由 runner 按 registry 的 `summary_template` 填充（模板填数字，不是 LLM 润色；英文模板用自动注入的 `{参数名}_s` 复数位——n=1 为空、否则 "s"），随 step.updated 推送——这是打勾流"Removed 12 fillers · 2 repeated takes"的数据来源。**run 收官 recap 只聚技能行**：`aggregate_run_summary` 按 seq 序拼接 done 节点的 spec.summary，但只收 `SKILL_REGISTRY` 成员 kind + bailed checkpoint（"Bailed by user" 用户中止注记）——内部班组行（理解/规划/渲染簿记）留在各自步骤行，不进 recap；派生发生在读取时，无列。**失败行是人话不是原文**：异常携带 `user_key`（`pipeline/errors.py` 的 `USER_ERROR_LINES` 键；MiniMax 客户端按 429/5xx/传输/schema 分键，voice 族自带，包装层 `propagate_key` 透传），终态 `node.error` 烘焙成 run UI 语言的本地化短句——原始异常全文只进 structlog，SQL/SQLAlchemy/httpx 内脏永不上脸。渲染链同理：`render_error` 写人话行（项目语言链），output 行与 render 节点镜像同源。

### 8.6 chat 回合 SSE（2026-08-04）

**单调用流式 + 增量散文提取**：LLM 判定仍是同一 JSON、同一调用（不加延迟不加成本）；服务端在 JSON 字符流累积过程中用状态机（`ProseDeltaExtractor`）提取散文字段（book path 的 `answer` / chat loop 的 `text`·`summary`），把字符增量实时推给前端；流末完整 JSON 走现有 Pydantic 校验，现有 `ChatResponse` 作终帧收尾。

- **Accept 协商**：`POST /chat` 内容协商——普通调用拿一次性 JSON（201，行为逐字节不变）；`Accept: text/event-stream` 拿流。剧本测试 / 旧前端零改动，随时回退。
- **协议**：`assistant.delta` `{"text"}`（0..N，有序拼接的散文预览）；非散文片段（think 前缀 / verdict JSON 尾部 / reasoning）推 `assistant.thinking` keepalive 帧（只保温 thinking 指示，永不展示）；终态恰好一帧——`turn.completed`（完整 ChatResponse，**信封永远赢**，整体替换预览气泡）或 `turn.failed`（`{"detail"}`，流中失败，不落库）。15s 心跳注释帧。
- **计划卡永远流不了**（结构化 JSON 必须完整到齐，dock 只随信封到）——但 generate 回合的计划复述散文（`answer` 字段 = 计划卡的引言）流式推 delta；只有 start 回合（answer=null）零 delta。两个 agent 的 system prompt 各加"散文字段放第一个 key"，否则 tasks 数组生成完才出散文。
- **提取器纪律**：目标 key 只在 brace 深度 ≤2 接受（`ops[i].params.text` 深度 ≥3 绝不误触发）；think 前缀跳过；值非字符串 → 静默零 delta；任何意外 → dead 锁存降级为整包落地。重试只发生在首个 delta 发出前（流中失败直接抛，走现有 fallback）。
- **service 拆两段**：`prepare_chat_turn`（dispatch 决策之前全部，所有 4xx 在此抛）+ `execute_chat_turn(db, prepared, request, on_delta)`；`chat()` = prepare + execute(on_delta=None)，JSON 路径不变。**单次末尾 commit 不变**——SSE 生成器自开 `AsyncSessionLocal`（BaseHTTPMiddleware 栈会在路由返回后关掉请求级 session，runs.py 同款）；断连取消 task → 不 commit → 回滚，"失败回合什么都不落库"契约保住。
- **前端**：`lib/chat-stream.ts`（fetchEventSource POST，**禁自动重连**——重试会重复落用户消息；非 2xx 读 JSON detail 保持 422 toast 语义）。两个面同款节奏：发送 → thinking → 首个 delta 才建预览气泡（Streamdown `mode="streaming"` 渲染不完整 markdown）→ 信封整体替换 + 跑现有完成逻辑。静态历史消息同走 Streamdown（`mode="static"`）。
- **answer 端点保持 JSON**（dock 点击低频；start 路径无 LLM）。

## 9. Edit Ops 边界（v2，归 Operation Model）

chat 的另一半是"改现有产物"。边界判定：

- 指令能表达为对某个 output 的 clip-spec diff → **edit ops** → Operation Model（operations 表，✅ 已落地）；
- 指令需要新的生成 → **task list** → 新 run（本文机制）；
- 拿不准 → intent 反问。

edit ops **已定稿并落地**（2026-07-26，ADR-032 D5 + `tasks/done/operation-model.md`）：产物级 op = `remove_range` / `set_trim` / `set_title` / `set_caption_style` / `set_music` / `set_crop` / `set_aspect` / `set_caption_text` / `restore_version`（+ system 内部 `snapshot` / `set_spec`），chat 已真应用（registry 校验 + message_id 血统）；**plan 级 op（`set_node_params` / `regenerate_node` / `swap_slot`）归 RunPlan 小拓扑，不进 operations 表**——两家族分开登记；`restore_range` 独立 op 被否决（判例 N-16：caption 不可复活，恢复语义归快照层）。

## 10. 失败语义

- 单节点失败：打 ✗ + 对话内给替代方案（"曲库没有合适的，要上传还是换个风格？"），对话继续，不阻塞。
- skill 拒收（§5 修复失败）：回复"这个我还不会"+ 列出全部可派发 skill（difflib 相近匹配只进 repair_feedback，不上用户面）。
- run 全败：沿用 RunPlan 收尾口径，对话里给出失败原因与重试入口。

## 11. 分期

| 期 | 内容 | 依赖 |
|---|---|---|
| v1 | registry 初集（§4.1）+ compile_graph 技能链物化 + intent tool-calling + SSE + 量化摘要 + `remove_filler` 实装（全链路 hello world） | backend-module-restructure |
| v2 | mentions + edit ops（Operation Model 联动） | Operation Model ✅ |
| v3 | 成本 quote（probabilistic skill 执行前报价确认）+ context 异步摘要 + `make_hook`（📋 未实装） | metering 扩展 |

## 12. Prohibited Behaviors

- **禁止** ReAct 式多步推理 loop——轮内单次 tool calling。
- **禁止** LLM 直接写 node spec / 自由生成执行代码——一切经 registry + compile_graph。
- **禁止**引入 agent 框架（Agno / LangGraph 等）。
- **禁止**把 SSE 做成事件总线（事件存储 / 投递保证 / 重放）。
- **禁止** chat 绕开 `orchestrator.create_run` 自建 run（零旁路原则不变）。
- **禁止** registry 无评审膨胀——skill 准入必须过 NAMING §7/§8。
