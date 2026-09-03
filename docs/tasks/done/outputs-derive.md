# outputs 派生化（outputs derive）——任务书语法收敛实施简报

> 依据：ADR-043（2026-08-15 拍板）；上游 CHAT_ARCH §3/§4/§5、RECIPES §4.1/§7.1、AGENT_ARCH §4、STRATEGY §5。
> 触发场景（2026-08-14 字幕卡点亮点收走查）：用户从字幕卡发射「给我的视频加中英双语字幕」+ 长视频源，任务卡呈现「视频片段 ×2 · 中文」——整条视频的变换意图被强制表达为高光提取 + 簿级修饰符。本简报把请求层语法从「产物清单」收敛为「技能链」，outputs 整体转为编译图的派生投影。

## 1. Context

outputs 槽位语法（`IntentSlot` + `InferredIntent.outputs`）是「一场演讲 → N 件衍生品」时代的请求层 schema——彼时业务只有提取族（clips/post/quotes/article）一种形状。技能注册表（ADR-039）落地后，工作语法已迁至技能链（task list → compile_graph mode②），plan path 仍持旧语法：outputs 必填、unclear 默认全家桶、固定拓扑（mode①）编译、簿级修饰符与 clips 槽硬耦合。两个意图语法并存，且旧语法无法表达变换族（给整条视频加字幕/配音/转画幅）——截图场景与两张 Live 卡的承诺分叉（卡不含剪辑，管线只出高光）是同一根因的两个显形。

## 2. 已核实事实（读码，2026-08-15）

- **mode② 已成熟**（`orchestrator.py:373-461` `_compile_task_list`）：任一技能 `needs_director` 即自动 prepend 去重的 director 前奏（preprocess → persona_bootstrap ∥ director_understand → director_plan）；modifier（`needs_director=False` 且 `produces_outputs=False`）挂 clips 节点，**无 clips 则空 inputs = 作用项目现有 clips**——首轮 run 无 clips 可作用，变换-only 链今天编译得出空图。
- **derive 桥已存在**（`orchestrator.py:464` `derive_context_fields`）：task list → slot 形状反推喂 run.context，注释自陈「mode② task items carry no focus/language」——槽位字段未参数化是实缺口：mode② 今天无法表达「一英一德两帖」。
- **director 派工读请求层槽位**（`node_runners.py:482-493`）：director_plan 从 `run.context.outputs` 建 task_book，`_align_storyboard_slots` 对齐——读的是请求层而不是真实执行图。
- **修饰符与 clips 硬耦合**：`compile_graph` 对 caption/dub_languages 无 clips 槽 raise（`orchestrator.py:278/304`），`:627-632` 静默丢弃。
- **出生地守卫已双源**（`orchestrator.py:483+` `_check_birthplace_requires`）：task list 的 requires 与 slot 派生 requires 同驱动——语法切换后守卫免费继承。
- **修饰技能注册现状**：`translate_clip` requires=(TRANSCRIPT,) 无 output_type；`dub_clip` requires=(MEDIA,) 无 output_type；fork 语义由 `spec.fork` 携带。
- **默认全家桶住在 schema**：`InferredIntent.outputs` default_factory = clips+post+quotes+article（`schemas.py:711-717`）。
- **配方预设分叉已在**：`recipes.py:150-159` multilingual-subs `outputs=[_CLIPS_SLOT]`，flow 无 select_clips（卡不含剪辑）——预设编译图与展示 flow 语义分叉。
- **计划卡前端机器**（`GenerationOverlay.tsx`）：`OUTPUT_OPTIONS`（:107）/ `SLOT_COUNT_LIMITS`（:126）/ `SLOT_COUNT_DEFAULT`（:131）/ `normalizeSlots` / `updateSlot` / `addSlot` / `removeSlot` / 字幕版本·配音版本区；服务端 `merge_prior_slots` 三方合并 + `prior_intent` 运输。
- **persona_bootstrap 短路现状**（`node_runners.py:117+`）：无文字素材跳过提取；纯变换链的「不触发人设提取」由编译不入图实现（本简报 R2）。
- **一条待核**：`select_clips` 的源形态分发（video/audio/stills → render_kind，`skills/clips/node.py:122-172`）——materialize_source 复用此决策，禁止复制第二份（抽共享函数）。

## 3. 设计论证

1. **为什么是收敛而不是加座位**：给旧语法加 `video` 产物类型 = 双语法永存；clips 加 scope 标志 = 一个类型藏两种形态，每个消费方长分支。技能链已是工作语法（mode② 在跑、报价 fold 在图上、出生地守卫双源），请求层收敛过去是删掉一套语法，不是新增一套。
2. **为什么合并机器自然死亡**：`merge_prior_slots` 存在的唯一理由 = 面板手改与 LLM 重提活在两份 schema（槽位编辑 vs 槽位推断）需要调和。面板控件改为对 task list 的直接结构编辑后，编辑与推断同一数据结构——修订回合 LLM 带 presented 摘要重提全链，面板编辑作为链的当前状态随行，无需合并。chat 恒胜从机制降格为结构事实。
3. **为什么材料化是内部节点而不是技能/产物类型**：用户不会说「材料化一下我的视频」——「整条视频」是变换的隐含对象不是动词（NAMING §7 不过技能准入）；它也不是可请求的产物（没有人请求「整条」本身，请求的是字幕/配音/画幅）。编译期注入（align_stills 输入画像先例）同时服务 plan path 与 chat loop 两个面。
4. **为什么 derive 在服务端**：compile_graph 是纯函数，干跑零副作用；卡模型、presented_plan 摘要、后续报价 fold 共享同一次编译——派生事实单一来源。面板编辑后的预览 = 链的本地投影（展示词汇），start 时服务端以编辑后的链重新编译（行为唯一事实源）——两处不矛盾：投影错了至多文案难看，run 永远按真编译跑。
5. **卡的价值重述**（设计法则）：HITL 裁决点不变；**请求已决定的维度不呈现为控件，控件只出现在真实自由度上**——select_clips 不在链里，数量步进器就不存在；链里没有的语言版本行不出现。控件全部绑定链参数，无控件即无参数。

## 4. 改动点（按包）

### 期 1（语法切换 + 材料化 + 卡换形）

**技能参数吸收（`app/skills/*/params.py` + registry）**
- writer 族（posts/quotes/article/carousel）新建 params 模型：`language`（必填，Field 描述 = LLM 文档）/ `focus` / `tone_override`；「一英一德两帖」= 两个 write_post 任务各带 language。
- `SelectClipsParams` 增 `focus` / `language` / `aspect`（count 已有）；`TranslateClipParams` 增 `bilingual`（bool）；`DubClipParams` 现状够用。
- `_compile_task_list` 生成技能 spec 改参数透传（spec = params dump + target_type 等既有键），替代今天只带 target_language/target_type 的裸 spec。

**`materialize_source` 内部节点（新技能包座位，不登记技能表）**
- 确定性 runner：span = 主媒体素材全长（ASR 词轨来自 preprocess），产出 1 条 Clip 行（render_status=PENDING），`output_type="video"`；源形态分发复用 select_clips 的 render_kind 决策（抽共享，不复制）。
- 编译注入规则（compile_graph 内核，两面同享）：链含 clip-spec 消费者（translate/dub/music/filler，无 target_output_id 指认）且无 select_clips、且项目无既有 clips → 注入；接 preprocess 之后（requires 驱动）。
- **preprocess 按 requires 入图**：节点 requires 含 TRANSCRIPT/MEDIA 而图中无 preprocess → 插入（今天 preprocess 只随 director 前奏捆绑）。
- 纯变换链不进 director 前奏（无 needs_director 技能时 persona_bootstrap / understand / plan 全不入图——08-11「纯配音/翻译不提取人设」先例的编译化）。
- translate/dub 的 `after` 声明吸收 `materialize_source`（注册项声明，无内核特判）。
- 多视频素材 v1：取主视频（上传序第一）；多视频且无指认 → PlanAgent 反问（提问机器复用）。

**PlanAgent / plan path（`chat/intent.py` / `chat/service.py` / `schemas.py`）**
- `InferredIntent` 换形：`outputs` / `outputs_explicit` / 簿级四修饰符退役 → `tasks: list[TaskItem]`（action/answer/material_text/specific_instruction/tone/confidence 不动）；plan_agent system prompt 重写——技能词汇与四态 loop 的 task_list 臂同源（注册表注入），媒体门禁规则保留（无 media 不出 select_clips/translate/dub），**删默认全家桶**（unclear → 最小链或反问）。
- generate 回合：干跑 `compile_graph(tasks)` → 卡模型（链行人话 + 派生产物行）→ 随 dock question 落库；presented_plan 摘要 = 同一 derive 的文本形。
- `pending_intent` 载荷换形为 task list；存量 outputs 形行读容忍确定性升级（clips 槽 → select_clips{count}；caption_languages[i] → translate_clip；dub_languages[i] → dub_clip；aspect → select_clips.aspect）——读路径升级器，永不写回旧形。
- start 流：`create_run(tasks=编辑后的链)`；merge_prior_slots / prior_intent / explicit 钉删除；出生地 422 不动（requires 双源已免费）。
- 保留：累积 prompt 服务端拼装、recent 5 轮上下文、provider 故障穿透（MiniMaxError → 502 人话行，不编造默认书——编造链同理禁止）。

**director 对齐（`node_runners.py` director_plan runner）**
- task_book 从编译出的生成节点构建（每生成节点一槽：type = output_type，language/focus/count 从节点 spec 参数读），不再读 `run.context.outputs`；`_align_storyboard_slots` 按（type, ordinal）对齐不变；director_plan.j2 的「explicit 字段 binding」语义改述为「节点参数 binding」。
- run.context.outputs 保留为派生投影（`derive_context_fields` 升格为唯一写入路径），消费方（结果分组等）不动。

**配方注册表（`pipeline/recipes.py`）**
- 预设改 task list 形状：multilingual-subs = `[translate{zh,bilingual}, translate{fr}, dub{es}]`；image-video = `[add_music{}]`（材料化 + align_stills 自动注入）。启动自检编译预设断言 flow ⊆ 图不变。aspect 成参数后卡预设的 `aspect="1:1"` 落到材料化节点参数。

**前端（`GenerationOverlay.tsx` / `lib/types.ts` / i18n）**
- 计划卡换形：链行区（每行 = 技能人话 + 参数控件：select_clips.count 步进器 / translate·dub 语言 chips / 行删除）+ 派生产物预览区（只读行：「整条视频 · 英字」「整条视频 · 中英双语」……）+ 既有 dock（Start/Cancel）不动。
- 死亡：`OUTPUT_OPTIONS` / `SLOT_COUNT_LIMITS` / `SLOT_COUNT_DEFAULT` / `normalizeSlots` / `bareSlot` / `updateSlot` / `addSlot` / `removeSlot` / 字幕版本·配音版本区 / 「添加产物」按钮 / prior_intent 运输。
- 链行文案：generate 响应携带服务端渲染的初始行；本地编辑（增删语言/改数量）经每 kind 的 i18n 行模板投影（展示词汇，非行为事实源）。
- i18n：新增链行模板键 + `整条视频/Full video` 派生类型名 + 预览区标题；退役 `outputsLabel` / `outputsHint` / `addOutput` / 版本区键。en 为源语言同步 zh。

### 期 2（清尸）

- mode① 固定拓扑分支（scope="full"）删除；`TaskSpec.outputs` 退役（legacy 行读经升级器）；`IntentSlot` 退役或收窄为派生投影 DTO（名单：run.context.outputs / storyboard 对齐读取面）。
- `slot_default_counts` / `slot_count_limits` 消费面清点（422 文案、director prompt 的 count_defaults_text 改从 params 默认值派生）。
- CHAT_ARCH §3 重写（任务书 = 技能链；outputs = derive）、RECIPES §7.1 预设形状、NAMING 词汇表登记、INTENT_COVERAGE 矩阵更新。

## 5. 命名审计

- 新增：`materialize_source`（源材料化，内部节点）；派生类型词 `video`（整条视频 / Full video，纯展示）；「派生产物预览」（derived outputs preview，卡区名）。
- 退役：`IntentSlot`（任务槽，请求层）/ `prior_intent` / `merge_prior_slots` / 请求层 `outputs`（产物 Output 表与产物行不动——死的是请求层语法）。
- 不变：`task_book`（任务书）词存活，所指从槽位清单换为技能链；`fork` 语义不动。
- NAMING.md 词汇表随期 1 落地登记。

## 6. 分期与验收

| 期 | 内容 | 验收（e2e 真实管线，无测试套件纪律） |
|---|---|---|
| 期 1 | 参数吸收 + materialize_source + 编译注入规则 + PlanAgent/服务换形 + 卡换形 + 配方预设换形 + director 图对齐 | **触发场景转正**：「给我的视频加中英双语字幕」+ 长视频 → 卡呈「整条视频 · 英字 + 中英双语」两行派生、无数量步进器 → Start → 单 run 出两条全长字幕视频，无剪辑；「一英一德两帖」双 language 参数不丢失；图文视频卡发射 = 整条轮播一条；存量 pending_intent 行升级后可 start；剧本测试 S1–S42 回归全绿 + 新增 S43+ 族（变换-only 链 / 双语 / 多版本 writer / 材料化注入 / legacy 升级） |
| 期 2 | mode① 清尸 + schema/词汇/doc 清扫 | 代码库 grep 无 `IntentSlot`（或仅派生 DTO）/ `merge_prior_slots` / `prior_intent`；CHAT_ARCH §3 与代码一致 |

**运维铁律**（RECIPES §9.4）：改 pipeline 代码必重启常驻 worker；验证用手工 run 会被常驻 worker 抢跑，验后清数据。

## 7. Prohibited Behaviors

1. **禁**请求层重新引入产物声明（任何形态的 outputs 必填字段 / 默认全家桶）。
2. **禁**面板编辑走独立于 task list 的第二 schema——控件只能直接改链；禁复活任何形式的 merge/prior 运输。
3. **禁**为 materialize_source 开技能登记或用户可见入口——编译期注入唯一通道（align_stills 先例）。
4. **禁**复制 select_clips 的源形态分发逻辑——抽共享函数。
5. **禁** LLM 直接写 node spec / 绕 compile_graph 落图（CHAT_ARCH 铁律延伸）；派生预览禁前端自行推断 fork 行为（预览 = 链投影，行为事实源 = 服务端编译）。
6. **禁**双语法并存期外的长期桥接——期 2 清尸是本期交付的一部分，不留「暂时兼容」。
7. **禁** provider 故障兜底编造默认链（plan path 穿透先例不变）。
