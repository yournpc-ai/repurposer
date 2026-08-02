# Chat Architecture — Agent Interface 层

> Status: ✅ v2 已实现（2026-07-26 backend + edit ops 接线；2026-07-27 GenerationOverlay 前端；2026-07-29/30 ask 原语期 1–4 + 期 4 补四全落地）。实施史见简报 `docs/tasks/done/chat-loop-v1.md` / `chat-loop-v2.md` / `intent-ask-primitive.md`；意图覆盖现状见 `INTENT_COVERAGE.md`。@picker / composer pills 不做（pills 已于 2026-07-27 随 composer 行为契约退役）。
> 补丁（2026-08-02，agent-loop-upgrade 一期，简报 `docs/tasks/agent-loop-upgrade.md`）：① 提案提示词注入参数 `Field` 描述（W2，provider-neutral）；② `DubClipParams.fork`——chat「再来一版」走派生新行、原版保留（W5）；③ morph runner 全部经 operations 记账（W4，壳/核同账，chat 配音/翻译/配乐/去口头禅可撤销）；④ step 级瞬时重试（`TransientNodeError` + `SkillEntry.retries`，W3）；⑤ recipe 合并代数三规则定格 remix 语义（W1，见 RECIPES §4.1）；⑥ 原生 tool-call 信道留待 provider 抽象（W6 不实施）——§1 原则 2 的"tool-calling"目前仍是 JSON-in-prompt 约定信道，非原生工具协议。
> 上游决策：ADR-028（RunPlan）/ ADR-029（plan 级 dispatch）/ ADR-030（产物统一）/ ADR-032（edit ops）
> 命名遵循：`docs/NAMING.md`；模块归属：`docs/MODULE_ARCHITECTURE.md`（Agent Interface：conversations/messages）；前置重构：`docs/tasks/done/backend-module-restructure.md`（chat/ 包是本文的代码家）
>
> 落地偏离点（相对本文设计稿）：
> - §5 的 `ports` 未吸收，拓扑约束用 `requires`（输入校验）+ `after`（顺序约束）表达。
> - `synthesize_talk_video` 已登记未实装（runner=None 座位，不可派发；归 R2，见 RECIPES §8）；`dub_clip` 已实装（2026-07-31 R1）。
> - @picker 注册表化落地（2026-08-01 修订）：提及系统升级为**双端注册表架构**（前端 `MENTION_REGISTRY` + 服务端解析注册表），recipe 为第一注册成员、第五提及类型，任务书钉死收归服务端解析（简报 `docs/tasks/recipe-mention.md`）；此前 mentions 仅落契约与列（type 取 `workflow_step`，N-15 改名后全栈同名）。
> - SSE 统一由 GenerationOverlay 打勾流消费（`useRunEvents` / fetch-event-source；results 页 GenerationStepper 弹窗已于 2026-07-28 退役，processing 项目改开 `?overlay=run` attach 模式）；step 状态枚举加 `waiting` 座位（HITL/suspend-resume 已用，§8.5）。

## 1. 定位与三条原则

Agent Interface 是六层模块图里"意图 → 执行"的唯一入口。用户的三张脸——composer pills、composer 自由 prompt、chat 对话——在它这里汇成**一条机制**：

```
task list（LLM 提议）→ compile_graph 校验/排序/补默认（代码裁决）→ workflow_steps（施工图）
```

1. **LLM 提议，代码裁决**。LLM 只出"干什么"（task list），拓扑正确性（skill 是否存在、顺序是否合法、参数默认值）全部归 `compile_graph`。LLM 永不直接写 node spec。
2. **轮内一次调用，轮间才是循环**。每条用户消息 = intent agent 单次 tool-calling 调用 → task list → 编译 → 跑。不做 ReAct 式多步推理；"循环"只发生在对话轮次之间。
3. **composer = chat 的第一条消息**。数据模型早已如此（`/generate` 建 project-scoped ChatSession 并存 prompt）：pills 是 task list 的结构化快捷方式，自由 prompt 是 task list 的自然语言入口，无指令 = 输入组合推导默认 task list（compile_graph 模式①，现有 presence-gating）。

## 2. 一次对话指令的完整生命

```
用户: "去掉口头禅，剪 3 条高光，加个音乐"
 │
 ▼
chat/service.py ──► intent agent（LLM 单次 tool calling，带 §6 上下文）
 │                   输出 task list（提议，无执行权）:
 │                   [{skill:"remove_filler"}, {skill:"select_clips",params:{count:3}}, {skill:"add_music"}]
 ▼
pipeline/registry.py   校验：skill 已注册？参数过 schema？
pipeline/orchestrator  compile_graph 模式②：拓扑排序（配乐殿后）+ 补默认值
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
Done · 3 clips · 12 fillers removed · 1 score ── [Open in editor]（outputs 链接）
 │
 ▼（下一轮：改现有产物而非跑新任务）
"第二条再短一点" ──► intent ──► edit ops ──► Operation Model（📋，§9 边界）
```

## 3. Task List 契约

intent agent 的轮内输出四态（N-18 三态 + N-21 第四态，均已落代码），JSON schema 强校验：

```jsonc
// A. 跑新任务（→ compile_graph 模式② → 新 WorkflowRun）
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

// C. 结构化提问（→ QuestionDock；N-18 翻案 N-14，期 3 已落代码）
{
  "type": "ask",
  "question": "这五个切片你想做成哪种方向？",
  "kind": "choice",                 // choice | task_book | confirm（成本 quote 预留）
  "options": [{"id": "a", "label": "…"}, …],
  "allow_freeform": true,
  "cost_hint": null
}

// D. 纯信息直答（→ 普通 assistant 消息；N-21，期 4 补四已落代码）
{
  "type": "answer",
  "text": "发布不在 chat 里——产物卡上有发布按钮。"
}
```

`summary` 字段必填——它是打勾流的标题文案，也是消息记录里"这轮干了什么"的人话存档。

**answer 态边界（写死在 agent 规则里）**：只在无工作请求且无歧义时用（能力/进度/解释/闲聊）；要干活 → task_list/edit_ops；读数有歧义 → ask——answer 永不当偷懒出口。进度问题凭 §6 的节点级进度段照实答；发布意图 → 引导到产物卡发布按钮；品牌/说话人等身份设置 → 导航到对应页面。

**answer 契约**（期 1 已落，期 4 补修订）：`{kind: "option"|"freeform"|"bail"|"start", option_id?, text?, answered_at}`。bail 是一等公民——入口回 draft 可重开、checkpoint 下游级联 skipped（期 4），**永不标 failed**；`start` 是 task_book 确认的一等 kind（取代期 1 的魔法 `option_id="start"`）。请求体 `AnswerRequest` 是按 `kind` 判别的联合（option/freeform/start/bail）——`autonomy`/`intent` 只存在于 `start` 上，其他 kind 带 kind 外字段直接 422，不再静默忽略；task_book 问题只接受 start/bail，其他问题不接受 start。N-14 的"tasks=[] 反问"届时迁移为 ask 的 freeform 形态（options 空 + allow_freeform）——反问仍是合法输出，只是有了类型座位。

## 4. Skill Registry 初集

`pipeline/registry.py`：Python dict + Pydantic schema，不上框架。每条登记：

```jsonc
{
  "name": "remove_filler",
  "kind": "skill",                    // skill=LLM 决策单元 / tool=确定性执行单元
  "behavior": "deterministic",        // deterministic 可缓存 / probabilistic 每次计价
  "params_schema": { ... },           // Pydantic
  "summary_template": "Removed {filler_count} fillers · {repeat_count} repeated takes",
  "cost_hint": "cheap",               // 成本量级，供未来 quote
  "runner": "pipeline.node_runners:run_remove_filler"
}
```

**准入纪律：skill 总数十几个封顶。** 新 skill 准入 = 过 NAMING §7 同款评审（用户会用自然语言说到它吗？现有 skill 组合能表达吗？），通过即登记（§8 词汇表）。

### 4.1 已在（反向抽象登记）

| skill | 实现 | summary_template 示例 |
|---|---|---|
| `select_clips` | `skills/clip_agent.py` | "Selected {n} clips · {total_seconds}s total" |
| `write_post` / `write_quotes` / `write_carousel` / `write_article` | `skills/post·quotes·carousel·article.py` | "Wrote a LinkedIn post · {word_count} words" |
| `revise_script` | `skills/reviser.py` | "Revised hook · {reason}" |
| `dub_clip` | dub 端点 → `tools/voice.py` | "Dubbed with cloned voice" |
| `add_music` | clip-spec music 槽 + mood 库 + `tools/music.py` | "Scored · {mood} bed" |

### 4.2 新增（按价值排序，独立排期）

| skill | 状态 | 说明 |
|---|---|---|
| `synthesize_talk_video` | 📋 任务简报 `docs/tasks/synthetic-talk-video.md` | 文字稿+照片+声纹 → 合成发言视频（生成端 v1） |
| `remove_filler` | 📋 chat 线 hello world | 词级时间戳 + filler 检测 → 标 hidden（非破坏）→ 重渲染 |
| `make_hook` | 📋 半新 | ≈ `revise_script(scope=hook)` 的独立入口 |

### 4.3 不登记

- **管线内部节点**：`preprocess` / `persona_bootstrap` / `director_plan`——拓扑的组成部分，不是用户可选技能。
- **`infer_intent`**：它是 loop 的入口，不是 loop 可调用的一项。
- **edit ops**：Operation Model 的词汇（§9），产出 clip-spec diff 而非 run——两个家族分开登记。
- **judge/verify**：Phase 3 节点 kind，非用户技能。
- **缓议**：`adapt_to_platform`（等 Distribution 回流数据）、`insert_broll` / `motion_graphics`（talking-head 知识内容价值低）、`avatar_gen`（v2，ADR-029 已定框架）。

## 5. compile_graph 模式②：任务列表物化

现有 `compile_graph`（模式①，presence-gating）之外新增模式②：

1. **校验**：task list 每个 skill 必须在 registry；params 过 schema；不认识的 skill → 拒收并让 intent 修复一次（retry 1 次），仍败 → 回复用户"这个我还不会"。
2. **拓扑排序**：registry 声明 `ports`（in/out 类型）与 `after` 约束（如 `add_music` 必须在渲染相关节点之后）；编译期校验类型边。
3. **补默认值**：`select_clips.count` 缺省 = 项目默认 / brand 默认 music 等，全部由代码补，不信 LLM 的缺省判断。
4. **落图**：产物是标准 `workflow_steps`——之后走图、认领、计量、打勾流与模式①完全同构。**动态化只发生在编译前，编译后零差异。**

## 6. 对话上下文（context 组装）

确定性代码组装，不是塞聊天历史。每轮 intent 调用带四部分：

| 部分 | 内容 | 来源 | 预算 |
|---|---|---|---|
| 项目摘要 | 素材清单、当前 outputs 列表（type + 一句话）、latest run 状态 + **节点级进度**（每步一行 `kind: status — summary`，≤12 行，G-2） | DB 确定性生成 | 4k |
| 最近操作 | 近 3 轮的 task list / edit ops 及结果摘要 | messages | 2k |
| mention 清单 | 本会话可 @ 实体（§7） | DB | 1k |
| 早期摘要 | 超窗对话压缩 | LLM 异步生成存 messages | 2k |

## 7. Mentions（@ 实体引用）

> **2026-08-01 注册表化修订**：提及系统 = 双端注册表（前端 `MENTION_REGISTRY`：icon / i18n / 候选源；服务端：效果注册表——**上下文富化**族通用注入已免费，**任务书钉死**族为 recipe 专属，解析唯一发生地 = 服务端 `resolve_recipe_mentions`）。`recipe` 为第五提及类型（前四 = asset / output / transcript_segment / workflow_step）；LLM 不解释 recipe 提及——确定性引用直接钉，不占 intent 调用。后续 @ 类型 = 双端各一条注册项，无类型分支（扩展证明见简报 `docs/tasks/recipe-mention.md` §2.5）。以下为本节的原始契约描述，机制不变。

多轮对话的模糊指代必须落为确定引用。可 @ 实体四类：**asset / output（某条 clip）/ transcript 段落 / workflow step**。

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

**前端实现（2026-07-27）**：`useRunEvents` hook 统一消费这条流，接两处——results 页 `GenerationStepper`（顶部进度条）与 `GenerationOverlay` 打勾流（composer 发送后的全屏对话：计划卡 HITL 确认 → 步骤逐行亮起（shimmer 标记进行中）→ 终态 toast + 结果页 refetch）。轮询只保留给无 token 的匿名场景与"run 已终态但 clip 仍在渲染"的尾部阶段。

**进度面收编（2026-07-28）**：GenerationStepper 弹窗与后端 `ui_step` 退役——进度 UI 只留打勾流一处。`processing` 项目卡片链接 `/projects/$id?overlay=run`：GenerationOverlay 以 `initialRunId` attach 到活 run（无确认阶段、无 intent 兜底推理，计划摘要行由 `latest_run.context` 重建）；run 排队/素材处理中（步骤流为空）显示 transcribing/queued 占位行。results 页裸访（无 overlay 参数）只有内联进度：tab 运行指示、骨架卡片、clip 卡渲染 spinner。attach 的 run id 由页面 latch（不靠活态重判），避免页面自身 SSE refetch 把 run 翻成 completed 时 overlay 中途卸载。

**计划确认的持久化与恢复（2026-07-28，2026-07-30 B 组修订）**：`/projects/{id}/intent` 的 generate 回合把未确认的任务书 + 原始 prompt 写到 `projects.pending_intent`（含 reasons / brand_template_id；answer 回合不写，免得覆盖用户在确认的计划），`/generate` 确认时清除。`draft` 项目 ⟺ 待确认：项目卡片显示"待确认"并链接 `/projects/$id?overlay=intent`，results 页无 run 时显示"继续设置"CTA——两处都能精确复活同一份计划（跨设备；卡片上的手动微调不入库，恢复的是最近一次推理版）。sessionStorage 交接管道已于同日退役。

### 8.5 QuestionDock 与 question/answer（ask 原语，期 1/3 已落）

> **消息列表是"已决"的历史，输入框上方是"待决"的现在。**

- **一行两态**：`messages.question` JSONB（typed payload：`{kind: task_book|choice|confirm, options, allow_freeform, cost_hint}`）+ `messages.answer` JSONB nullable（**NULL = 待决**，宪法 §4）；`content` 存问题人话原文（自然进 LLM 上下文历史）。
- **停靠法则**：待决问题永远停靠 input 正上方的 **QuestionDock**（✓ + 问句 + cost_hint? + 按钮组含 bail）；**同一时间最多一个待决**——新题落库前旧题 auto-bail（`answer.text="superseded"` 机器标记）。回答瞬间坍缩成 **QA 双层消息**入档（`QaPair`）。
- **待决重建零内存态**：`latest_pending_question` = 会话最新未答 question 的行查询（Mastra `listSuspendedRuns` 同款），GET `/chat/conversation` 带 `pending_question`——刷新/跨设备 dock 复活免费。
- **answer 端点即恢复**：`POST /chat/messages/{id}/answer` 写答案即解除阻塞（不显式命名 resume）。task_book 分派：bail → 清 pending_intent 回 draft（prompt 已 seed 进会话，可重开）；`start`（一等 answer kind）→ 从 pending_intent 起 run 并写 `workflow_run_id`。choice 分派（期 3）：记录后续聊——响应 `AnswerResponse{answered_question, follow_up}`（与 `ChatResponse.answered_question` 同角色同名，B2），option 答案回填 label 进 `answer.text`。重复回答 409。`/generate` 兜底 settle（`mark_task_book_started`）——两路径共用"一行一答"不变量。
- **/intent 响应判别联合（B1/B4 + G-1）**：`POST /projects/{id}/intent` 返回 `{type:"plan", intent, reasons} | {type:"answer", text} | {type:"started", run_id, answered_question}`——answer 回合的问答双方落普通消息行（确认相位对话从此与"一切皆消息行"一致，刷新可重放），且 **answer 回合不覆盖 stored 任务书**；`started` 是确认相位的原话确认（G-1：`InferredIntent.action="start"` → 复用 answer kind=start 路径起 run，dock 的 autonomy 档随 `ProjectIntentRequest.autonomy` 透传不丢档；用户原话经 `record_intent_turn` 入档，无可启动对象时 re-dock 存量书或降级 plan，同样不覆盖 stored 任务书）。`needs_clarification` 布尔已摘除（`reasons.length > 0` 可推导，存量行读取容忍）。请求带 `turn`（本轮用户原文）——refinement 发累积 prompt 做推理但只把新行入档。
- **入口约束归出生地（期 4 补）**：clips-media 门、slot count 边界（`SLOT_COUNT_LIMITS`：clips 1-10 / quotes 1-20 / carousel 2-15）、targeted scope 校验、mode② requires 全部在 `create_run` 内拒绝（ValueError → 请求层 422 / chat 层反问兜底）——`/generate`、task_book start、chat 派发三条入口不再各持一份 guard。`create_run` 只 flush 不 commit：run、启动它的 answer、project 状态落在同一请求事务里，提交点唯一。
- **task_book 形态（期 1）**：计划卡留在消息流做审阅面板（编辑属流内），Start/Cancel 决策 + **Auto/Review 自治档**移入 dock；`autonomy` 经 AnswerRequest/GenerateRequest/`TaskSpec` 落 run.context（行为期 4 生效：review 档 full run 插方向 checkpoint，auto/targeted/mode② 不插）。needs_clarification reasons（期 3）随 question 人话原文落库（数据存键，渲染时本地化）。
- **choice 形态与 autoResume（期 3）**：dock 渲染选项按钮组（字母徽章镜像映射规则）；待决中自由文本确定性映射——命中选项字母/序号/原文 → option 回答，否则 allow_freeform → freeform，否则按新 intent 处理、问题保持待决（零 LLM；task_book 待决不参与）。`ChatResponse.answered_question` 携带本回合掉的问题行供 QA 入档。成本 quote（confirm 形态，cost_hint 解剖位已预留）归 v3。
- **checkpoint 形态（期 4）**：方向检查点是 choice 问题 + `workflow_run_id` 分派标记。`Suspend` 异常把瘦节点停进 `waiting`（选项住 `spec.suspend_payload`）、run 停进 `WAITING_HUMAN`；答案端点/autoResume 写 `spec.answer`、节点回 pending、run 回 RUNNING——队列式重入（runner 从顶上重跑，answer 分支直达 done），不是调用栈续跑。选项代码派生自 `key_arguments`（零 LLM）；bail = 节点 done(spec.bailed) + 下游级联 skipped("user bailed") + run COMPLETED（永不 failed）；`director_plan` 经 `task_book.direction` 消费（option → 优先论点，freeform → 指引原文，默认 → 现状；slot.focus > checkpoint > director）。**过期**：park 超过 `checkpoint_expiry_seconds`（默认 30 分钟）由 worker 扫描自动以默认项回答并续跑（`answer.text="expired"` 机器标记；review 档超时降级为 auto 档，兑现"离开不中断"，永不 auto-bail）。**多 run 并停**：新题 dock 取代开口 checkpoint 题时同笔级联 bail 那个 run（`finalize_bailed_runs` 收官 COMPLETED）——单待决不变量不会搁浅 run。

**量化摘要**：`node.spec.summary` 由 runner 按 registry 的 `summary_template` 填充（模板填数字，不是 LLM 润色），随 step.updated 推送——这是打勾流"Removed 12 fillers · 3 repeated takes"的数据来源。run 收尾聚合节点摘要成 "Done · 3 clips · 12 fillers removed"。

## 9. Edit Ops 边界（v2，归 Operation Model）

chat 的另一半是"改现有产物"。边界判定：

- 指令能表达为对某个 output 的 clip-spec diff → **edit ops** → Operation Model（operations 表，✅ 已落地）；
- 指令需要新的生成 → **task list** → 新 run（本文机制）；
- 拿不准 → intent 反问。

edit ops **已定稿并落地**（2026-07-26，ADR-032 D5 + `tasks/done/operation-model.md`）：产物级 op = `remove_range` / `set_trim` / `set_title` / `set_caption_style` / `set_music` / `set_crop` / `set_aspect` / `set_caption_text` / `restore_version`（+ system 内部 `snapshot` / `set_spec`），chat 已真应用（registry 校验 + message_id 血统）；**plan 级 op（`set_node_params` / `regenerate_node` / `swap_slot`）归 RunPlan 小拓扑，不进 operations 表**——两家族分开登记；`restore_range` 独立 op 被否决（判例 N-16：caption 不可复活，恢复语义归快照层）。

## 10. 失败语义

- 单节点失败：打 ✗ + 对话内给替代方案（"曲库没有合适的，要上传还是换个风格？"），对话继续，不阻塞。
- skill 拒收（§5.1 修复失败）：回复"这个我还不会"+ 列出相近可用 skill。
- run 全败：沿用 RunPlan 收尾口径，对话里给出失败原因与重试入口。

## 11. 分期

| 期 | 内容 | 依赖 |
|---|---|---|
| v1 | registry 初集（§4.1）+ compile_graph 模式② + intent tool-calling + SSE + 量化摘要 + `remove_filler` 实装（全链路 hello world） | backend-module-restructure |
| v2 | mentions + edit ops（Operation Model 联动）+ `make_hook` | Operation Model 📋 |
| v3 | 成本 quote（probabilistic skill 执行前报价确认）+ context 异步摘要 | metering 扩展 |

## 12. Prohibited Behaviors

- **禁止** ReAct 式多步推理 loop——轮内单次 tool calling。
- **禁止** LLM 直接写 node spec / 自由生成执行代码——一切经 registry + compile_graph。
- **禁止**引入 agent 框架（Agno / LangGraph 等）。
- **禁止**把 SSE 做成事件总线（事件存储 / 投递保证 / 重放）。
- **禁止** chat 绕开 `orchestrator.create_run` 自建 run（零旁路原则不变）。
- **禁止** registry 无评审膨胀——skill 准入必须过 NAMING §7/§8。
