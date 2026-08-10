# Arch Overhaul —— ADR-039 架构规范级大迭代实施简报（模块归位 → 节点对象化 → harness 漏斗 → 估价）

> Status: Active（2026-08-10 立项）
> 依据：ADR-039（规范级大迭代）/ AGENT_ARCHITECTURE（四层工程地图目标态）/ NAMING N-29~N-35
> 排期：第二周 08-10~08-14，与人设模块、配方卡闭环链三线并行，周五 08-14 联合验收（PROGRESS §2 第二周）

## 1. 背景与目标

代码内核（RunPlan DAG + 注册表裁决 + chat 单入口）健康，但有系统性规范残留：skill 一词三义、产物类型散在 6+ 处、tools/ 混 LLM 调用、节点知识散在 4 个文件、xxx_agent ad-hoc 类群、harness 部件散落、`cost_hint` 报不了价（ADR-039 Context 八条）。本迭代是**规范级大迭代——内核流程不变，概念归位与模块重划**：技能叙事为架构主叙事，四层工程地图（Model / Harness / Graph / Loop）落为目录结构。

**铁律：行为零变化**。compile_graph 同输入同图；chat 四态/裁决/dock/checkpoint 语义不变；runner 逻辑逐行平移；prompt 文案、template kwargs、温度、错误语义逐字节平移。剧本 harness（S1–S40）是回归网。

**DX 目标**：加技能 = 加一个包；加 agent = 加一条声明；加产物 = 加一条注册项。

## 2. 终态模块地图（P1 末态）

```
app/agents/                 Harness 层——决策体共享层
├── base.py                 唯一 Agent 类（漏斗：装配→渲染→调用→校验 hook；repair/兜底声明化 P3 补齐）
└── roster.py               共享 crew 声明 + AGENTS dict：director_understand / director_plan / persona / translator
app/skills/                 技能包——能力的唯一家（每包：node.py + params.py + procedure.py? + agents.py?）
├── clips/                  node(run_clips_pipeline) + params(SelectClipsParams) + agents(clip_writer 声明)
├── posts/                  node + agents(post_writer)；quotes/ carousel/ article/ 同构
├── revise/                 node(run_script_revision) + params(ReviseScriptParams) + agents(reviser) + procedure(instruction→FeedbackRequest 编排)
├── dub/                    node(run_dub_clip) + params(DubClipParams) + procedure(声纹解析/克隆复用/翻译编排/spec 组装/错误契约)
├── captions/               node(run_translate_clip) + params(TranslateClipParams) + procedure(tools/caption_translate 整迁)
├── filler/                 node(run_remove_filler)
├── music/                  node(run_add_music) + params(AddMusicParams)
└── stills/                 node(run_align_stills) + procedure(阅读节奏时间轴估算)
app/tools/                  纯机械库：asr / voice / storage / filler / transcript / extraction / music(仅 persist/path) / dubbing(仅 cue 对齐合成)
app/pipeline/
├── node_runners.py         内部 crew：preprocess / persona_bootstrap / director_* / checkpoint / render
├── step_context.py         runner 侧装配与杂项（_generation_context / collect_asset_media / _list_assets / KNOWN_OUTPUTS…）
├── step_display.py         展示键写入（_set_stage / _set_summary / _fill_summary / slot_tag / _node_slot…）
├── edges.py                DAG 边读取（_load_understanding / _load_director_outputs / _align_storyboard_slots / _checkpoint_direction / _compute_coverage）
├── morph.py                modifier 公器（_target_clips / _fan_out_renders / _record_target_output_ids / _run_origin…）
├── images.py               图像生成机械（generate_image 封装：金句卡 / 封面）
├── derivative_dispatch.py  writer 共享 procedure（DerivativeType → 包内 writer 声明）
└── registry.py             P1 保留并扩为 STEP_RUNNERS 全表收编点；P2 迁 skills/__init__.py 后退役
```

**导入方向（无环拓扑，P1 结构保证）**：`registry.py` → `skills/<pkg>/node.py` → `step_* / edges / morph / images / .agents / agents.roster / tools.*`；`node_runners.py`（内部 crew）只许 import `agents.roster` + `pipeline.*` 机械模块，**永不 import `skills.*`**；`agents/roster.py` 只收共享 crew，**不 import 技能包**（技能私有声明住各包 `agents.py`，P3 收编枚举）；`tools/` 不 import `app.agents` / `app.clients`（grep 门禁）。`registry.py` 对 runner 的引用维持 dotted-path 惰性解析先例。

## 3. 实施分期

### P1 模块归位（08-10，行为零变化）

1. **建 `app/agents/`**：
   - `base.py` —— 唯一 Agent 类（Generic[OutT]）。声明属性：`name` / `prompt`（jinja 模板名）/ `schema` / `system`（静态 system prompt）/ `temperature` / `assemble`（每声明一个纯函数，参数表 = 输入契约，纯度签名化的落点）/ 可选 `postprocess(result, ctx)`（领域修正，如字幕行数对齐）/ `media_text_fallback`（声明式多模态降级，默认 False）。`call(**ctx)`：assemble → 渲染 → 组 messages → `client.generate` → postprocess；jinja env 全库唯一（现 5 处自建收编）；`trim_texts` / multimodal message 构建为模块级 helper；非 MiniMaxError 统一包 `MiniMaxError(f"{name} failed: {e}")`。盲重试不动（run_clips_pipeline / _generate_derivative_with_retry 的调用方重试 P1 原样保留，P3 由 repair 取代）。repair 一轮 / 兜底声明化 / 模板级计量归因 = P3 席位，P1 不建。
   - `roster.py` —— 共享 crew 四声明 + `AGENTS` dict：`director_understand`（0.3，media_text_fallback=True）、`director_plan`（0.4）、`persona`（0.3，schema=`ExtractedPersonaMemory`——去下划线迁入 schemas.py 输出契约区）、`translator`（0.3，postprocess=行数对齐）。
2. **9 个 `app/skills/` 决策类解散为声明**（N-29/N-30）：上述 4 实例进 roster；技能私有 6 声明住各包 `agents.py`——`clip_writer`（clips，0.4，media_text_fallback=True，assemble 含 slot argument_ids→texts 解析）、`post_writer`（0.5）/ `quotes_writer`（0.4）/ `carousel_writer`（0.4）/ `article_writer`（0.6）各住其包、`reviser`（revise，0.4）。`_find_slot` 随 base 收编。`PlanAgent` / `ChatIntentAgent` **留 `chat/intent.py` 不动**（Loop 层是目标态的家；P3 转流式子类）。
3. **tools/ 违规工序归位**：
   - `tools/caption_translate.py` → `skills/captions/procedure.py` 整迁（`_group_units`/`_redistribute` 机械 + `translate_caption_track`/`translate_text` 编排同属字幕技能私有工序；agent 调用改 roster 的 `translator`）。
   - `tools/dubbing.py` 拆分：**编排**（render_spec/轨道校验、声纹样本解析 VOICE_SAMPLE>AUDIO>VIDEO、克隆复用、persona style hint、翻译编排、存储落盘、spec 组装、HTTPException/TransientNodeError 错误契约）→ `skills/dub/procedure.py` 的 `synthesize_dub`；**cue 对齐合成机械**（timed `_group_units`、`_clip_time_mapper`、`_decode_mp3`/`_encode_audio`、`_synthesize_fit_unit`、PCM 按 cue 起点拼装）留 `tools/dubbing.py`，出口收敛为 `synthesize_aligned_track(units, voice_id, target_language, segments) -> (bytes, ext, stats)`。
   - `tools/voice.py`：断 `MiniMaxError` 依赖——本地定义 `VoiceError`，synthesize/clone 改抛它；dub procedure 捕获 `(MiniMaxError, VoiceError)` → `TransientNodeError`（错误文案不变）。
   - `tools/music.py`：`generate_music`（含 `DEFAULTS_MODEL`/`USER_MODEL`）迁 `pipeline/music.py`（生成编排归 Graph 层库服务）；tools 只留 `GeneratedMusic` / `persist_music` / 路径机械。
4. **pipeline/ 重划**：`node_runners.py` 拆出 `step_context.py` / `step_display.py` / `edges.py` / `morph.py` / `images.py`；技能 runner 迁各包 `node.py`（函数体逐行平移）；`node_runners.py` 只留内部 crew 六 runner；`registry.py` 收编全表 `STEP_RUNNERS`（内部 crew + 技能包节点），runner dotted path 全部指向新家；`_fill_summary` 对 SKILL_REGISTRY 的惰性 import 先例保留。
5. **import 全量修正**（消费方清单见 §6）；`memory/routes.py`、`pipeline/routes/outputs.py`、`pipeline/routes/music.py` 调用形态同步换 `.call(...)` / 新模块路径。
6. **grep 门禁**：`apps/api/scripts/check_gates.py`——扫描 `app/tools/*.py`，命中 `from app.agents` / `import app.agents` / `from app.clients` / `import app.clients` 即非零退出；P2 后扩"平行映射表"检查。
7. **回归**：`uv run python scripts/check_gates.py` 绿；API + worker 启动自检（`assert_runners_registered`）过；真实 e2e 一跑（上传 → clips+post 生成 → chat 发起 dub_clip task_list → 完成）；剧本 harness 抽样 S1–S8 + 配音/翻译族全绿。

### P2 NodeBase + outputs 派生 + kind 同名（08-11~08-12，含数据迁移）

1. `pipeline/graph.py` 新建：`NodeBase` 协议（`kind` / `output_type` / `after` / `needs_director` / `retries` 类属性；`run` 唯一必实现；`estimate` 默认 None（P4 填）；`requires()` / `label()` / `reuse()` 默认实现）+ `NODE_KINDS` 收编。
2. 每包 `node.py` 的 runner 函数 → NodeBase 子类（`kind` = 技能名）；内部 crew 六节点同法对象化（住 `node_runners.py`）；`execute_step` 改走 `NODE_KINDS[kind].run()`。
3. 内核退化图算法：校验 = ∀`requires()`（`_validate_requires` 字符串匹配归位节点）；对账 = 配方 flow keys ⊆ 编译图 kind 集（启动自检，`compile_graph` 纯函数直接编译比对）；`retries_for_node_kind` 扫描、`_SLOT_TYPE_LABEL`、asset-hash 复用特判全部归位节点（`reuse()` 首例 = `director_understand`）。
4. **outputs 注册表派生**（N-32）：产出型技能声明 `output_type`；`IntentSlot.type` Literal 退役改 str + 注册表校验；`_OUTPUT_TO_NODE_KIND` / `_SKILL_TO_OUTPUT` / `KNOWN_OUTPUTS` / `_SLOT_ORDER` / `_SLOT_TYPE_LABEL` / `SLOT_COUNT_LIMITS` / `SLOT_DEFAULT_COUNT` 全部派生；PlanAgent prompt 产出类型清单同源注入。
5. **kind 同名数据迁移**（N-35，alembic）：`workflow_steps.kind` 的 `dub`→`dub_clip`、`clips_pipeline`→`select_clips`、`post_gen`→`write_post`、`quotes_gen`→`write_quotes`、`carousel_gen`→`write_carousel`、`article_gen`→`write_article`、`script`→`revise_script`；`SkillEntry.node_kind` / `kind` 字段退役；SKILL_REGISTRY 收编进 `skills/__init__.py`（registry.py 退役）；启动自检扩"节点→agent 引用存在"（AGENTS 全收编随此落位）。
6. RunFlowGraph 节点友好名切 `NodeBase.label` 派生（闭环链红利，前端零新表）。

### P3 harness 漏斗（08-13）

1. **repair 一轮全员化**：schema/裁决失败 → 错误结构化回显 → 一轮自修复进 `Agent.call`（ChatIntentAgent 的 `repair_feedback` 机制上移）；**盲重试退役**——`run_clips_pipeline` auto-retry 与 `_generate_derivative_with_retry` 删除，由带反馈的 repair 取代；剧本断言"repair 只一轮"。
2. **兜底声明化**：`PlanAgent._fallback`（永不白屏）保留为声明先例；`media_text_fallback` 已是声明；其余默认禁。
3. **contexts 抽离**：`agents/contexts.py` 新建——chat service 的装配逻辑（`_build_context`、mentions 注入、recent 轮次、per-step 状态段）迁入；chat service 不持装配逻辑。
4. **流式子类**：`PlanAgent` / `ChatIntentAgent` 归一为 Agent 的流式子类（`generate_stream` + ProseDeltaExtractor 单漏斗不变，N-26）。
5. 纯度签名化收口评审：`director_understand` 的 assemble 参数表无 persona（类型层已不可表示，评审确认）。

### P4 估价地基（08-13~08-14）

1. `workflow_steps.estimate` 增量列（nullable，NULL = 未估价；alembic 唯一表变更）。
2. 各节点 `estimate(ctx)`：机械精确价（TTS 按字符 / render 按秒 / 克隆按次 / 图像按张）、agent token 区间（按 prompt 规模 + 输出 schema 给上下界）、checkpoint = 0。
3. `create_run` 编译后逐节点估价写入 `estimate`（报价 = 图 fold 的存储侧）；actual（cost）与 estimate 偏差回归的查询形状落成。
4. `SkillEntry.cost_hint` 三档退役；`messages.question` 的 `cost_hint` 字段保留 schema、估价供给切换为 estimate fold（dock 总价 / chat 单价 / 配方卡估价贴三面呈现 = 第六周消费面，不在本周）。
5. 剧本 harness 新增三断言：flow 对账自检过 / 报价单调性（子图 ≤ 全图、非负）/ repair 只一轮。

## 4. 验收口径

1. **每期完工定义**：剧本 harness（S1–S40 全集，真实 LLM）绿 + 门禁脚本绿 + 启动自检过；任一不过即未完工。
2. **P1**：`app/agents/` 与 11 个技能包落位；`app/skills/*.py` 旧决策类文件全删；`grep -r "from app.skills.base\|skills.content_director\|skills.clip_agent…" app/` 无残留；真实 e2e（上传 → 生成 clips+post → chat 派发 dub/翻译/去口头禅 → 完成）行为与动工前逐点一致。
3. **P2**：新增一种假想产物走查——加一条注册项（包 + output_type），PlanAgent prompt 当轮即知、`compile_graph` 裁决通过、出生地门禁生效，全程零散点改动（"改 6 处"成为历史的实证）；`workflow_steps` 存量 kind 全部新名。
4. **P3**：全库无盲重试（grep `auto_retry`/`_with_retry` 无残留）；repair 一轮有剧本断言；chat service 无装配逻辑（`_build_context` 已迁）。
5. **P4**：`workflow_steps.estimate` 有值且 NULL 语义正确；报价单调性断言过；`cost_hint` 三档无残留。
6. **周五联合验收口径**（PROGRESS 第二周周五行）：架构部分看"AI 调用统一过校验+修复一轮+记账"与"每个生成步骤自带估价"两条产品语言验收，对应 P3/P4 完工定义。

## 5. Prohibited Behaviors

- **禁**行为漂移：P1/P2 只搬不改——prompt 文案 / template kwargs / 温度 / 错误文案逐字节平移；runner 函数体逐行平移；compile_graph 同输入同图。任何"顺手优化"单独提案，不夹带。
- **禁** `tools/` import `app.agents` / `app.clients`（N-29 铁律，`check_gates.py` grep 门禁）。
- **禁**平行映射表 / 平行花名册：一切"类型 → X"知识归注册表 / 节点声明派生；P2 后 `_OUTPUT_TO_NODE_KIND` 类散点 grep 无残留。
- **禁** `xxx_agent` 类复活：一个 Agent 类 + 声明实例；assemble/postprocess 是声明数据，不是子类；特殊子类仅流式（P3，chat intent 一家）。
- **禁**盲重试（P3 起）：一切重试带结构化反馈且只一轮；client 层 tenacity 网络重试 = 传输层，不在此列。
- **禁**静默兜底：兜底 = 声明属性（`media_text_fallback` / PlanAgent fallback 先例），声明处一眼可查。
- **禁** ReAct / tool-call loop 脚手架 / context compaction / agent 间对话（协作经落库产物沿 DAG 边流动）。
- **禁** actor / 班组词复活；**禁** skill 一词三义复活（skill = 能力层注册项；执行者分类字段永不建）。
- **禁**建新表（全迭代仅 `workflow_steps.estimate` 一列 + kind 数据迁移）；agents / skills 皆静态注册表，随代码部署，不建插件系统。
- **禁**改 clip-spec / 渲染链契约（ADR-016 黑盒）；**禁**动 chat 四态 / dock / checkpoint 语义。
- 文档同步 = 每期完工定义的一部分：AGENT_ARCHITECTURE §11 / NAMING / MODULE_ARCH §7 代码地图随代码同改，不许"代码改了文档后补"。

## 6. 消费面全审计与迁移地图（P1，2026-08-10 逐点核实）

**`app.skills.*` 现存消费方（全部换源）**
- `pipeline/node_runners.py`：`clip_agent` / `content_director_agent` / `persona_agent` / `reviser_agent` / `base._MAX_CHARS_PER_TEXT` → 内部 crew 留 `node_runners.py`（director/persona 改 roster 声明）；`run_clips_pipeline` → `skills/clips/node.py`（clip_writer 声明）；`run_derivative_gen` → 四 writer 包 `node.py`（共享 `derivative_dispatch`）；`run_script_revision` → `skills/revise/node.py`；`run_translate_clip` → `skills/captions/node.py`；`run_dub_clip` → `skills/dub/node.py`；`run_remove_filler` → `skills/filler/node.py`；`run_add_music` → `skills/music/node.py`；`run_align_stills` → `skills/stills/node.py`；`_MAX_CHARS_PER_TEXT` → `agents/base.py`。
- `pipeline/derivative_dispatch.py`：四 writer import 改各包 `agents.py`；调度 map P1 保留（P2 注册表派生后退役）。
- `pipeline/routes/outputs.py`：`reviser_agent.revise(...)`（feedback 端点）→ `skills/revise/` 声明 `.call(...)`；`translate_caption_track` / `synthesize_dub` import 改 `skills/captions/procedure.py` / `skills/dub/procedure.py`。
- `memory/routes.py`：`persona_agent.generate(...)` → roster `persona` 声明 `.call(...)`。
- `tools/caption_translate.py`：模块整迁（见 §3 P1-3）。

**`tools.*` 现存消费方**
- `tools/dubbing.synthesize_dub`：`node_runners.run_dub_clip` + `pipeline/routes/outputs.py` dub 端点 → 改 `skills/dub/procedure.py`。
- `tools/caption_translate.{translate_caption_track, translate_text}`：`node_runners.run_translate_clip` + `routes/outputs.py` + `tools/dubbing` → 改 `skills/captions/procedure.py`。
- `tools/voice.*`：仅 dub 编排消费（路径不变，错误类型换 `VoiceError`）。
- `tools/music.generate_music`：`pipeline/routes/music.py`（+`USER_MODEL`）→ 改 `pipeline/music.py`；`pipeline/music.py` 对 `persist_music` 等的 import 不变。

**`pipeline/registry.py` 消费方（P1 不动函数面，仅收编 STEP_RUNNERS）**
- `orchestrator.py`：`STEP_RUNNERS` 改自 registry 导入（`KNOWN_OUTPUTS` → step_context，`slot_tag` → step_display）；`validate_task_list` / `retries_for_node_kind` / `generation_node_kinds` 源不变。
- `chat/service.py`（`SkillRejected` / `dispatchable_skills`）、`chat/intent.py`（`dispatchable_skills`）、`main.py` / `worker.py`（`assert_runners_registered`）：import 源不变，零触碰。
- `_fill_summary` 对 SKILL_REGISTRY 的惰性 import：保留惰性先例。

**prompts**：10 个 j2 模板原地不动（jinja env 收编不改模板路径）；模板变量名零变化。

**前端**：P1/P2/P3 零触碰；P4 的 `costHint` 展示切换属第六周消费面。

## 7. 命名终审（全设计过筛）

| 词 | 裁决 | 理由 |
|---|---|---|
| `app/agents/` + `base.py` + `roster.py` | ✅ 采用 | N-29/N-30 正名；roster = 花名册，AGENT_ARCH 已用 |
| `Agent.call(**ctx)` / `assemble` / `postprocess` | ✅ 采用 | 漏斗词族（装配/校验修正）；assemble 参数表 = 纯度签名化落点 |
| `media_text_fallback` | ✅ 采用 | 声明式兜底词，默认 False；多模态降级唯一合法先例之二 |
| `AGENTS` | ✅ 采用 | 花名册 dict，可枚举（P1 = 共享 crew；全收编随 P2/P3 自检） |
| `translator` | ✅ 采用 | 共享 crew 名（caption translate agent 正名；技能 = captions，agent = translator） |
| `clip_writer` / `post_writer` / `quotes_writer` / `carousel_writer` / `article_writer` / `reviser` | ✅ 采用 | 技能私有声明名；`clip_planner` 否决（裸 plan 词根，N-11 避雷） |
| `ExtractedPersonaMemory`（入 schemas.py） | ✅ 采用 | 去下划线 = LLM 输出契约公共区成员 |
| `skills/<pkg>/` 包名 11 个 | ✅ 采用 | clips / posts / quotes / carousel / article / revise / dub / captions / filler / music / stills——名词单数；revise 包备 P2 `script`→`revise_script` 同名；`synthesize_talk_video` 座位 P1 不建包（R5 周落地时建） |
| `node.py` / `params.py` / `procedure.py` / `agents.py` | ✅ 采用 | 包内四件（AGENT_ARCH §7 解剖；agents.py = 私有声明家，可缺省） |
| `step_context.py` / `step_display.py` / `edges.py` / `morph.py` / `images.py` | ✅ 采用 | pipeline 模块名：展示键写入 / DAG 边读取 / modifier 公器（morph 词 PROGRESS 已用）/ 图像生成机械 / runner 侧装配（P3 与 agents/contexts.py 汇合评估） |
| `VoiceError` | ✅ 采用 | tools/voice.py 本地错误词，断 MiniMaxError 依赖；§6 通用词 |
| `check_gates.py` | ✅ 采用 | 门禁脚本；验收器家族成员 |
| 节点 kind 新名（P2 数据迁移） | ✅ 通过 | `dub_clip` / `select_clips` / `write_post` / `write_quotes` / `write_carousel` / `write_article` / `revise_script`——kind = 技能名（N-35）；内部节点名不动 |
