# intent-ask-primitive 实施简报——ask 原语 + 任务书 slot 化 + 停靠确认 + 方向检查点

> Status: 📋 待实施（2026-07-29 定稿：任务书 slot 化纳入——"同类产物多语言"是扁平模型唯一表达不了的结构性缺口，触发解冻；本轮目标 = chat 确认面全面对齐 Agent Opus 实证形态）
> 依据：CHAT_ARCH §3（IntentProposal 二态，N-14）/§8（pending_intent 持久化与恢复）；NAMING §5（新词族登记 + 翻案判例）；AGENT_ARCH §12.3；`docs/research/opusclip.md` §9（Agent Opus HITL 实证）；Mastra suspend-resume / HITL / agent-approval 官方文档（机制语义参照，非依赖候选）
> 前置：output-quality-verify 期 1 已落地——其 `quotes_count`/`carousel_count` 扁平字段是**过渡形态**，本简报期 2 由 `IntentSlot.count` 取代（全库退役，不留过桥层，宪法 §1）；与 quality 期 2/3 并行无依赖，唯 checkpoint 的 orchestrator 改动与 verify 期 3 同文件，review 时对账
> 迁移：1 个 alembic 迁移（`messages.question` / `messages.answer` 两个 JSONB nullable 列），down_revision 跟落地时最新 head。**slot 化零表迁移**——全部住在 JSON 载荷层（pending_intent / run.context / 请求体）

## 0. Context

意图层有两个结构性病灶：

1. **扁平参数袋**：`clip_count` → `quotes_count` → `carousel_count` 发现一点改一点，且用户无法差异化对待不同产物。四个真实场景判了它死刑：
   - ① **分产物角度**："切片剪定价争议、帖子写全场总结、金句挑远程团队"——一个全局 instruction 刷所有产物，LLM 只能猜分配。
   - ② **同类产物多语言**："英文 LinkedIn 帖 + 德语帖"——`outputs` 类型枚举 + 全局单一 `target_language`，**一次 run 在结构上不可能**；绕法（两次 run）产物撞角度，像孪生草稿而非互补资产。对欧洲 ICP 这是入场券场景（CLAUDE.md：多语言是入场券）。
   - ③ **分产物语气**："帖子正式、金句活泼"——分镜槽位早有 `tone_override`/`cta` 字段，意图层够不着。
   - ④ **修改牵一发动全身**：re-inference 全量重推断，"金句改 6 张"可能悄悄改掉已确认的"德语"——pin 纪律需要数据结构保证。
2. **确认盲**：确认面是一张混在消息流里的参数卡片，用户在系统展示任何素材理解之前做承诺。

2026-07-28/29 两轮设计评审结论：用户发完提示词需要被理解的证据、可预期的交付、花钱前的低成本修正通道；确认有光谱（参数→方向→身份→负空间）；问话有纪律（拦/回显/邀请/永不问）。Opus Agent UI 实证了形态（research §9）：**审阅面板在消息流里可编辑，决策条停靠 input 正上方；选项卡提问、QA 双层入档、best-judgment 兜底文案**。Mastra 提供机制语义参照：suspend/resume/bail 三动词 + 双向 typed 载荷 + 存储Backed 待决重建。

## 1. 已核实的现状事实（读码确认）

- **IntentProposal 二态判别联合**（`schemas.py:180-227`，N-14）：`tasks=[]` = 反问，summary 装自由文本；ask 无 typed payload 座位。
- **分镜表已是 slot 形状**（`director_plan.j2`：`slot/focus/argument_ids/quote_candidates/cta/tone_override/count`）——下游早就会说槽位语言，是意图层的扁平让用户够不着已有结构。
- **任务书全链路扁平**：`InferredIntent.outputs`（类型枚举）+ 三个 count 字段 → `GenerateRequest` → `TaskSpec.outputs: list[str]`（`orchestrator.py:57`）→ run.context。`compile_graph` 按**类型**扇出 executor（一种产物一个节点，`orchestrator.py:110-115`）；`run_derivative_gen` 幂等语义 = 删该项目同类型全部旧产物（`node_runners.py:1104`）。
- **mode② 回填**：`_backfill_context`（`orchestrator.py:246`）从 task items 推导 outputs/clip_count 补 mode① 上下文字段——slot 化需同步改。
- **`waiting` 座位已预留**：`StepStatus` 含 `waiting`（`schemas.py:1081`，注释明写 `spec.suspend_payload`）；`WorkflowStatus.WAITING_HUMAN` 枚举已存在（`schemas.py:102`）全库无引用。
- **finalize 两处谓词不含 waiting**（必改）：`maybe_finalize_run` active 谓词（`orchestrator.py:476-480`）；`finalize_stuck_runs` SQL（`orchestrator.py:514-525`）——waiting 节点会让 run 被提前收官/被崩溃恢复扫掉。
- **Message 表**（`tables.py:360`）：无 question/answer 列；`intent` JSON 列已在（IntentProposal dump/轮）。
- **pending_intent 持久化已落地**（b61260d）："待决"存储语义就位。
- **计划卡钉在消息流上方**（非 input 上方）：GenerationOverlay "Conversation below the pinned regions"。
- **QualityBounce（quality 期 3 设计）验证了暂停-恢复图机语义**：重置 pending + spec 载荷 → 自动重认领。checkpoint 复用同地基，区别是等人（停 `waiting`）不是等重跑。
- **问话纪律雏形已存在**：needs_clarification + reasons（`projects.py:305`），确定 auto-start（`GenerationOverlay.tsx:401`）。
- **方向选项原料已存在**：`MaterialUnderstanding.key_arguments`——checkpoint 选项代码派生，零 LLM。
- **run.context 老行是扁平形状**：只读历史（前端展示容忍双形状）；runners 只读本 run 新上下文，无回填负担。

## 2. 设计论证（评审沉淀区）

### 2.1 确认光谱与四层确认面

| 层 | 内容 | 落点 |
|---|---|---|
| 素材回响 | "我看到 47 分钟视频 + 一份 PDF" | 入口首条 assistant 消息 |
| 任务书审阅 | **逐槽** outputs/count/focus/language 可编辑面板 | 消息流内面板 |
| 身份回响 | "以 Anna 的口吻、大学品牌模板" | 面板内一行，不再询问 |
| 方向预览与确认 | understanding 核心论点 → 方向选项 | checkpoint（期 4，Review 档） |

### 2.2 停靠法则与 question 一行两态

> **消息列表是"已决"的历史，输入框上方是"待决"的现在。**

- 待决问题（task_book 确认 / 选项卡 / 成本 quote）永远停靠 input 正上方的 **QuestionDock**；同一时间最多一个待决（并发时 dock 显示最早未答，其余排队）。
- 回答瞬间坍缩成 **QA 双层消息**入档。
- 数据模型一行两态：`messages.question` JSONB + `messages.answer` JSONB nullable（**NULL = 待决**，宪法 §4）；`content` 存问题人话原文（自然进 LLM 上下文历史）。
- 待决重建零内存态：查会话最新未答 question（Mastra `listSuspendedRuns` 同款，靠消息行免费得到）。

### 2.3 ask 原语（IntentProposal 第三态，翻案 N-14）

```jsonc
{
  "type": "ask",
  "question": "这五个切片你想做成哪种方向？",
  "kind": "choice",                 // choice | task_book | confirm（成本 quote 预留）
  "options": [{"id": "a", "label": "…"}, …],
  "allow_freeform": true,
  "cost_hint": null
}
```

- **翻案 N-14**：结构化 ask 的 payload 与 task_list/edit_ops 正交，判别联合加第三态；原"tasks=[] 反问"全部迁移（纯文本反问 = options 为空 + allow_freeform 的 ask）。
- **answer 契约**：`{kind: "option"|"freeform"|"bail", option_id?, text?, answered_at}`。
- **bail 是一等公民**：入口 bail = 回 draft 可重开；checkpoint bail = 下游级联 skipped、run COMPLETED（注明用户中止）。**永不标 failed**。
- **autoResume（确定性版）**：待决中用户发自由文本 → 命中选项 label/序号字母 → option；否则 allow_freeform → freeform；否则按新 intent 处理、问题保持待决。零 LLM；语义级映射归后续。

### 2.4 命名：机制词与用途词分离（Mastra 参照）

机制一词一物：`Suspend` 异常 / `waiting` 状态 / `answer` / `bail`；用途住 payload kind（direction/task_book/cost quote），**用途×机制组合词永禁**。状态词从机制动词派生；配对词整体引入（ask/answer/bail）。resume 不显式命名——答案端点即恢复。复用不造词：`explicit`（=pinned）、cost quote（v3）、`suspend_payload`（座位注释同款）。

### 2.5 任务书 slot 化（期 2，本轮解冻）

**形状**：

```jsonc
IntentSlot = {
  "type": "clips" | "post" | "quotes" | "carousel" | "article",
  "count": null,          // None = 默认（clips 5 / quotes 3 / carousel 6）
  "focus": null,          // ① 分产物角度（用户/意图识别）
  "language": null,       // ② None = 任务书级 target_language；同类型不同语言 = 多槽
  "tone_override": null,  // ③ 直通分镜槽同名字段
  "explicit": false       // ④ 用户手编标记（pin 合并规则用）
}
```

- **分层命名**：IntentSlot = **任务槽**（请求层，用户要什么）≠ StoryboardSlot = 分镜槽位（派工层，导演怎么排）。同名不同物禁令要求分层词。
- **全链路换形**：`InferredIntent.outputs: list[IntentSlot]` → `GenerateRequest` → `TaskSpec.outputs`（run.context 原样落库）→ task_book。**quality 期 1 的三个扁平 count 字段随之全库退役**（InferredIntent/GenerateRequest/TaskSpec/前端 wiring）。
- **拓扑变化：per-slot 扇出**。`compile_graph` 从"一种类型一个 executor 节点"改为"一个槽一个节点"——两个 post 槽（en/de）→ 两个 post_gen 节点，spec 携带本槽。语言解析 = `slot.language ?? run.target_language`。
- **幂等删除的兄弟撞车修复**：`run_derivative_gen` 现行"删该项目同类型全部旧产物"在多 post 节点的同一次 run 里会误删兄弟节点的新产物。改为：**删同类型且 `workflow_step_id` 不属于本 run 的该类型节点集合的旧产物**（clips 单槽不受影响）。
- **director_plan 槽规则**：任务书逐槽给出（count/focus/language 显式值）；director 只补空缺（argument_ids/quote_candidates/cta），**显式槽字段不可违背**；两 post 槽的论点分配必须互补（写进 prompt 规则）。
- **优先级**：`slot.focus`（用户显式）> checkpoint 方向（期 4）> director 自排。
- **pin 合并规则**：手编过的槽字段（`explicit: true`）在 re-inference 后被保留，新推断只填空缺——④的结构化解。
- **`_backfill_context` 兼容**：mode② task items → 槽形状回填（type 从 skill、count 从 params）。
- **零表迁移**：全在 JSON 载荷层；run.context 老行扁平形状仅前端展示容忍，后端无回填。

### 2.6 checkpoint 节点（方向检查点，期 4）

独立节点 kind，**瘦节点规则**——提问前不做重活（队列式重入：答案回来后从 runner 顶上重跑，靠 spec.answer 分支直达 done；不是 Mastra 的调用栈续跑）。

```
director_understand(3) → checkpoint(3.5, spec.for=direction) → director_plan(4) → executors…
```

- 被认领：从 understanding.key_arguments 派生选项（≤3 个"聚焦：{论点}" + "全场高光"默认 + freeform）→ 写 question 消息 → 转 `waiting`（`spec.suspend_payload` 存选项）→ run 转 `WAITING_HUMAN`。
- 答案到（`POST /messages/{id}/answer`）：spec.answer 写入、节点回 pending、run 回 RUNNING → 重认领 → done，summary = 选定方向。
- `director_plan` 消费：option → priority argument_ids；freeform → focus 指引文本；默认 → 现状行为。与槽 focus 的关系见 §2.5 优先级。
- **bail**：节点 done（spec.bailed）+ 下游级联 skipped（`_cascade_skip` 非失败变体）+ run COMPLETED。
- **finalize 两处谓词补 waiting**（§1 已核实）。
- **不进 SKILL_REGISTRY**（verify 判例同款）。

### 2.7 自治档 autonomy

- `TaskSpec.autonomy: "auto" | "review"`（默认 auto，随 run.context 落库）。
- auto：只硬阻塞（clips 无媒体、语言必错类入口拦截）——现状行为，零新增打断。
- review：full run 在 understand→plan 间插 direction checkpoint；targeted run 不插。
- UI：dock 决策条内 Auto/Review 切换（Opus 同款位置），随本次 /generate 提交。
- 兜底文案："计划已保存，离开不中断——我会按最佳判断完成，随时回来看看"。

### 2.8 明确不做（本期）

- **transcript 纠错确认**——归术语表线（ROADMAP §6，查找替换式 + 固定译法/发音两消费者）。
- **成本 quote**（confirm 形态 + cost_hint 解剖位已预留）——CHAT_ARCH v3。
- **per-slot cta**（CTA 归 speaker 级/全局 instruction）与 per-slot tone 的**编辑 UI**（`tone_override` 字段进 schema，由意图识别填充；手编 UI 归后续）。
- **LLM 语义级 autoResume**、多待决并行、per-output 检查点、verify needs_human 主动 ask 版、@picker。

## 3. 后端改动点

1. `app/models/tables.py`：`messages.question` / `messages.answer` JSONB nullable + alembic 迁移。
2. `app/models/schemas.py`：`IntentSlot`；`AskProposal`（第三态）；question/answer payload schema；`InferredIntent.outputs` → `list[IntentSlot]`（退役三个扁平 count）；`GenerateRequest` 换 slots；`TaskSpec.outputs` → `list[IntentSlot]` + `autonomy`；ChatResponse 带 pending question。
3. `app/chat/intent.py`：ComposerIntentAgent 产出槽（count/focus/language 逐槽识别，含"英德两版帖"同类多槽）；ChatIntentAgent prompt 加 ask 形态规则；context 组装带待决问题。
4. `app/chat/service.py`：ask 落库；answer 处理分派（task_book → 更新 pending_intent/起 run；choice → 续聊；checkpoint → 唤醒节点）；确定性 autoResume；待决查询；**pin 合并**（explicit 槽字段在 re-infer 后保留）。
5. `app/chat/routes.py`：`POST /messages/{id}/answer`；GET conversation 带 pending_question。
6. `app/pipeline/routes/projects.py`：/generate 换 slots 契约（422 语义不变）；needs_clarification reasons → question 消息（期 3）。
7. `app/pipeline/orchestrator.py`：`Suspend` 异常 + execute_step 捕获分支 + answer 唤醒 + bail 级联；finalize 两处谓词补 waiting；`compile_graph` per-slot 扇出 + autonomy 裁决 + `_backfill_context` 槽兼容。
8. `app/pipeline/node_runners.py`：`run_checkpoint`；`run_director_plan` 任务书逐槽 + 消费 checkpoint answer；executor runners 读 `node.spec.slot`（count/focus/language）；`run_derivative_gen` 幂等删除改兄弟安全。
9. `app/prompts/director_plan.j2`：槽规则（显式字段不可违背；同类多槽论点互补分配）。

## 4. 前端改动点

1. `QuestionDock.tsx`（新）：停靠条常驻 input 正上方；解剖 = ✓ + 问句 + cost_hint? + 按钮组（含 bail）；choice 形态渲染选项按钮组；task_book 形态渲染决策条（开始/取消 + Auto/Review 切换）。
2. 任务书审阅面板：**逐槽行**（类型 + count 步进器 + focus 行 + language 下拉），Start 决策移入 dock；身份回响行；老 run.context 扁平形状展示容忍。
3. input 变种：choice 待决时占位提示 "Something else…"；自由文本走 autoResume。
4. QA 消息渲染变种（Q/A 双层）。
5. 步骤流 waiting 行 + run waiting_human 展示；per-slot 扇出后同类型多节点的区分显示（节点带语言/角度标签）。
6. 离开提示文案行。
7. i18n en/zh 全套（dock/question/QA/autonomy/waiting/slot 编辑/离开提示）。

## 5. 命名审计（NAMING §5 触发）

新名词登记（§2 词汇表）：`IntentSlot`（任务槽：任务书一行 = 一个产物的请求，带 count/focus/language；**不是分镜槽位**——请求层 vs 派工层）、`ask`（提问，提议态）、`question`（问题，落库态）、`answer`（回答）、`bail`（弃做）、`Suspend`（挂起异常）、`checkpoint`（检查点节点 kind）、`autonomy`（自治档）。
退役：`InferredIntent.clip_count`/`quotes_count`/`carousel_count` 扁平 count 字段（quality 期 1 过渡形态，`IntentSlot.count` 取代，全库清除不留过桥层，宪法 §1）。
翻案判例（拟 N-18）：N-14"不加第三态"翻案——结构化 ask 升第三态，自由文本反问迁移为 ask 的 freeform 形态。
判例（拟 N-19）：机制词与用途词分离——用途×机制组合词永禁（Mastra 参照）。
判例（拟 N-20）：任务槽 vs 分镜槽分层——请求层与派工层各有槽位词，混用即违规。
启用座位不算新词：`waiting`/`WAITING_HUMAN`/`suspend_payload`。

## 6. 分期与验收

| 期 | 内容 | 行为变化 |
|---|---|---|
| 1 | messages 迁移 + answer 端点 + QuestionDock（task_book 形态）+ QA 渲染 + 离开文案 | 决策不再被滚走；可取消；离开有提示；刷新/跨设备 dock 复活 |
| 2 | **任务书 slot 化全链路** + 逐槽编辑面板 + pin 合并 | 逐产物角度/语言生效；"英德两版帖"一次 run；改一槽不动其他槽 |
| 3 | ask 第三态 + choice dock + autoResume + 入口 reasons→question | chat 出选项卡提问；答完 QA 入档；自由文本命中选项即映射 |
| 4 | Suspend + checkpoint + autonomy + finalize 谓词 + bail + waiting UI | Review 档生成中途停问方向；选/自由/弃做三路径 |

验收（e2e 为准，无测试套件纪律）：

1. **期 1**：长对话滚动确认条不动；Cancel 回 draft 可重开；QA 双层入档；刷新 dock 复活。
2. **期 2 多语言**："给我英文和德语两版 LinkedIn 帖"→ 一次 run 两个 post 产物、语言各自正确、storyboard 两槽论点分配互补、兄弟节点产物互不误删。
3. **期 2 角度/数量**："切片剪定价争议、帖子写总结、8 张金句卡"→ 槽 focus/count 进 director_plan prompt 可见；产物角度与之一致。
4. **期 2 pin**：手编某槽 count 后自由文本 refine → 该槽 count 保留，其余按新推断。
5. **期 3**：模糊指令出选项卡（非纯文本反问）；点选/字母/原文命中 → QA 入档续跑；非命中自由文本 → freeform 或保持待决，不静默吞掉。
6. **期 4 拓扑**：Review 档 full run 含 checkpoint；auto 档不含；targeted 不含。
7. **期 4 三路径**：选项 → slot focus/argument 分配体现；freeform → focus 指引含原文；bail → 下游 skipped、run COMPLETED 注明用户中止、不标 failed。
8. **期 4 韧性**：waiting 时 kill worker 重启 → 不被 finalize_stuck_runs 收官；答案到后正常续跑。
9. **成本**：checkpoint 节点零 LLM 调用。
10. **文档落地**：CHAT_ARCH §3 三态 + §8 dock/question 节；NAMING §2 登记 + N-18/N-19/N-20；ROADMAP 相应行更新。

## 7. 禁止行为（Prohibited Behaviors）

1. **禁** ReAct/多步推理——轮内单次调用铁律不动。
2. **禁**待决问题进消息流渲染——待决只在 dock，已决才入档。
3. **禁**多待决并行——最多一个未答 question，新题取代或排队。
4. **禁** LLM 生成 checkpoint 选项文案 / 语义级 autoResume——代码派生与确定性映射，LLM 版归后续。
5. **禁** bail 标 failed 或弹错误 toast——优雅退出是正常路径。
6. **禁** checkpoint/ask 进 SKILL_REGISTRY 或被 LLM 任务列表提议。
7. **禁**用途×机制组合词——用途住 `question.kind` / `spec.for`。
8. **禁**引 agent 框架、快照存储层、内存态待决。
9. **禁**新造 pinned/suspended 词——用已有 explicit / waiting。
10. **禁**扁平 count 字段与 slot 并存——全库退役不留过桥层（宪法 §1）。
11. **禁**任务槽与分镜槽混名、slot 化新增表列（全 JSON 载荷层）。
12. **禁** auto 档插任何可选检查点——自治档是用户偏好不是产品赌博。
13. **禁** transcript 纠错、成本 quote、per-slot cta、意图外的 slot 化扩散进本期。
14. **禁**前端 stepper 契约变更——只加 waiting 行样式与 question 渲染变种；同类型多节点靠标签区分，不改步骤数据结构。
