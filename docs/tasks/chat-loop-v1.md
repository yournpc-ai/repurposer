# CHAT_ARCHITECTURE §11 v1 实施简报——agent loop 地基（UI 冻结版）

> Status: 方案定稿（2026-07-26，评审 5 轮后冻结），待实施
> 依据：`docs/CHAT_ARCHITECTURE.md` §11 v1；命名过 `docs/NAMING.md` 八条；无新表/无新认领源 → 无需 ADR
> 实施第一步：将本文件复制为 `docs/tasks/chat-loop-v1.md`（任务简报入库，docs/README.md 清单登记）

## 0. Context 与范围裁决

backend 六模块包重构（N-06/N-07）与 plan 词汇终局（N-11）已在 main。本轮交付 **agent loop 地基**：功能拆成 tool/skill 进 registry，LLM 提议 task list → compile_graph 校验/拓扑/补默认 → 标准 plan_nodes → worker 执行 → SSE 推送。虚拟链按"虚拟 = 普通 skill"大一统标准留座（synthesize_talk_video 线落地时只填 runner 路径）。

**用户裁决（2026-07-26，多轮评审汇总）**：
1. **UI 全面冻结**：chat UI 不做、打勾流不做、composer UI 下个迭代。**唯一 UI 变动 = results 页 loading（GenerationStepper）从 2.5s 轮询换 SSE 驱动**——有新状态就展示新状态，进度条/label 结构不动。
2. add_music 与 remove_filler 都实装 node runner（同构）。
3. 交付标准 = API + worker + render 到位；chat 能力走 API 验证（curl），UI 下轮统一搞。
4. **表名**：`workflow_runs` **保留**（Mastra `workflow.createRun()`/GitHub 证明 workflow run 是行业标准执行实例全名；每个 run 自带其编译出的 workflow=plan_nodes 图，名对每行精确；改名动议记录在案并撤回）。`chat_sessions → conversations` **改名**（session 撞 auth session；OpenAI Conversations API 同款）。
5. **API 层 job 词汇清除**：`/jobs → /runs`、`job_id → run_id`（job 在 API 指 run，违反 v2.0"run 不是 job"与 N-11 双重原则；GitHub `actions/runs` 先例）。
6. v2.0 旧架构文档评审：**plans 版本树与 jobs 表明确不复活**；slots/candidates/evals/credit_transactions 归各自后排简报，不抢跑。

**硬约束（CHAT_ARCH §12）**：禁 ReAct loop（轮内单次 tool calling）；禁 LLM 直写 node spec；禁 agent 框架；禁 SSE 事件总线化（无事件存储/重放/投递保证）；禁绕开 `orchestrator.create_run`；registry 准入过评审并登记词汇表。

## 1. 已核实的现状事实（读码确认，实施时以此为准）

- `orchestrator.compile_graph` 模式①固定拓扑（scope ∈ full/hook/clip/derivative…/render）；`create_run` 唯一 run 出生点，`run.context` 存 TaskSpec verbatim；compile 纯函数（DB 校验在 create_run）。
- `NODE_RUNNERS` 10 kind，签名 `(db, run, node, project) -> list[UUID]`；`_set_stage` 独立-session jsonb_set 先例；`run_clips_pipeline` 运行期 fan-out render 节点先例；`run_render_request` flip render_status 先例；`GENERATION_NODE_KINDS` 硬编码 frozenset（本轮改 registry 派生）。
- `PlanNodeResponse` 已从 `spec["stage"]` lift stage（`pipeline/outputs.py:plan_node_to_response`）→ summary 同点 lift。
- chat：`Message.workflow_run_id` + `intent` JSON 列已在；`ChatAttachment` = 上传文件语义（不能捎带 mentions）；`_parse_chat_intent` 规则版被替换；`_dispatch_intent_to_run` 已走 create_run。
- `chat/intent.py` 现状 = composer IntentAgent（/infer-intent）→ 改名 `ComposerIntentAgent`（NAMING §5 同名不同物审计）。
- clip-spec：`ClipSegment.hidden` + TS `removeRange`（`packages/clip/src/types.ts`）；Python ClipSpec 在 schemas.py:714+；ASR `asset.meta.words=[{start,end,word}]`（`tools/asr.py:39`）。
- dub = 同步端点（`POST /outputs/{id}/dub`）→ registry 登记 runner=None（worker 化超范围）。
- MiniMaxClient：`generate(messages, response_model=T, temperature)` JSON mode（无原生 tool calling，response_model 即"tool calling"形态）；metering ambient（`bind_plan_node` contextvar，无绑定 no-op）。
- 前端：GenerationStepper（进度条+label，`ui_step` 来自 /results）；`_app.projects.$id.tsx` 2.5s setInterval 轮询；AssetChatModal pollJob（2s×60，**本轮不动**）；无 EventSource 依赖；`apiFetch` 注入 Bearer + 401→UNAUTHORIZED_EVENT；`results.stepper.*` i18n 键已在。

## 2. 设计论证（评审沉淀，实施时勿推翻）

### 2.1 JSONB 边界（ADR-030 规则 2：要查的字段挣顶级列）

| 提案 | 会被 SQL 查吗 | 裁决 |
|---|---|---|
| `node.spec.summary` | 不查（完成时写，序列化读） | JSONB（spec.stage 先例） |
| `run.context.tasks` | 不查（审计留痕；成本查 plan_nodes.kind 真列） | JSONB |
| `messages.intent` 新契约 | 列已是 JSON | 零改动 |
| `messages.mentions` | 不查（§7 picker 展示用） | JSONB 新列（本轮迁移） |
| 新 node kind | **查**（worker 认领、成本聚合） | String 真列 + 注册表（N-03） |

防护：① spec 写一律服务端 `jsonb_set` 单语句（禁 Python 读-改-写丢更新）；② summary 照 doc 落渲染英文串（双语化是后续加法 `summary_params`，不破契约）；③ 模式②回填 outputs/clip_count/target_language，run.context 消费者永远看到同一形状。

### 2.2 registry 语义：三个消费者三个视图，两个"不是"

| 消费者 | 视图 |
|---|---|
| intent agent（LLM） | 提议空间——prompt tool 清单由它生成 |
| compile_graph（代码） | 裁决依据——存在性/params schema/拓扑约束 |
| 进度显示/计价 | summary_template / cost_hint / behavior |

不是执行分发表（那是 NODE_RUNNERS，含非 skill 内部节点，§4.3；两表分离，registry 只持 runner dotted path，启动自检可解析）；不是插件系统（静态 dict 随代码部署）。家族定位：NAMING §5 注册表第三成员（OUTPUT_PAYLOAD_SCHEMAS / PlanNodeKind / SKILL_REGISTRY）。

### 2.3 v2.0 旧架构文档评审结论

已内化（不动）：命名 §0→NAMING 八条；LLM 三件事→§1/§12；context 四段表→§6；edit ops 8 个→§9；registry 契约→§4。已推翻（不复活）：五层开包（N-05/06/07）；jobs 表（N-11）；plans 版本树（ADR-028）；events 事件总线包（§12 禁，LISTEN/NOTIFY 桥后置）。落进本轮：① behavior 分型**如实标注**（cache 座位）；② `messages.mentions` 座位（本轮捎带）；③ `credit_transactions` 三态流水记为 v3 计费参考。SSE 事件名用 `step.updated`（快照 diff 推送非领域事件，名实相符）。

### 2.4 行业标准对照（Mastra/Agno/OpenAI）

详见将落入 MODULE_ARCHITECTURE.md 的对照表（工作项 7）。核心结论：skills/tools/memory/Workflows 内核/Evals 座位/Runtime 全部已对齐；`pipeline/` 模块 ≠ Mastra Workflows（我们 Pipeline = 摄入+ASR+编排+渲染，大于 Workflows，不改名）；行业标准对齐发生在 API/SDK 表面，内部词汇自洽优先。

**Mastra Workflows 7 篇文档逐项对照（2026-07-26）**：Agents&Tools（createStep(agent|tool)）≡ registry kind 字段，同构 ✅；Snapshots 表 ≡ plan_nodes 行就是 live snapshot，不需单表 ✅；Workflow State（共享可变 state）不吸收——跨节点数据走 outputs 行 + output_refs 类型化通道（带血统），不引入第二通道 ✅；Control Flow 组合子暂不吸收（并发=worker 认领、foreach=render fan-out、verify 循环用有界代码规则）✅；Error Handling → **吸收：`SkillEntry.retries: int = 0` 座位**（Mastra step-level retry 覆写同款形状；通用重试机制随 provider 型 skill 落地，LLM skill 内联重试现状不动）；HITL/Suspend-Resume → **吸收：step 状态枚举加 `"waiting"` 座位**（String 列零迁移）；variant_pick 契约形状预定：节点 spec 写 `suspend_payload`（候选清单）+ `POST /runs/{id}/resume {step_id, resume_data}`，SSE 只推状态变化，契约不改。

**Mastra Agents 3 篇对照（同日）**：Processors（运行时 guardrail 钩子）不吸收——Mastra 需要它是因为 LLM 有执行权；我们的提议-裁决结构把注入风险结构性消解（最坏结果 = 提议被 compile 拒收），内容合规归 ADR-026 ✅；Skills（createSkill 的 description="何时用"）→ **吸收：`SkillEntry.description` 字段**（intent prompt 注入用）；渐进披露不吸收（11 条全量进 prompt）；Using Tools（LLM 循环 + hooks + approval）契约级同构，差异记录：**Mastra approval 在 tool 调用时（执行中），我们裁决在任何执行前（编译时）——更严**。

### 2.5 "改"的范式：append-only（图不可变，改为新图）+ 最小半径编译

用户改 DAG = 新提议 → compile 出新图 → 新 run 作用于已有产物，**永远不原地改 plan_nodes/workflow_steps**（git/event sourcing 同款哲学：每次改留下可校验、可计量、带血统的编译产物）。

**"改为新图" ≠ "全部重生成"——改动代价谱系（图的大小由改动半径决定，代码裁决最小图）**：

| 改动 | 跑的图 | 成本 |
|---|---|---|
| 编辑器 trim 一条 clip | 无图（clip-spec diff + render_status=PENDING） | 重渲染 1 条 |
| "第二条再短一点" | 单节点（revise_script，target_id） | 1 次 LLM |
| "去掉口头禅" / "换个音乐" | 1 节点（remove_filler/add_music）+ render fan-out | 无 LLM/重渲染 |
| "剪 3 条高光" | 前奏 + clips_pipeline（整批重剪） | 集合级重生 |
| "换个角度重来" | 全图 | 全价（用户明确要求） |

机制：registry `needs_director=false` 的修饰类 skill 不注入前奏——**最小半径编译是"不全部重生成"的第一层答案**（本轮）；**上游复用缓存是第二层答案**（📋 cache/diff，v2.0 `hash(skill,params,input_asset_ids)` 参考，`behavior` 字段是座位）。整批重剪是刻意的集合语义（覆盖问责/防撞论点是集合级判断），"只换第 N 条"走 revise_script 单节点通道；select_clips 加 `keep` 参数记为已知演进点（本轮不做）。

四层验收：① 改产物内容→clip-spec diff/Operation Model（📋 P1，契约本轮落）；② 改参数/加处理→新小图作用于现有产物（本轮 mode② + remove_filler/add_music 实证）；③ 改生成方向→新 run 全图（已在）；④ 改图结构（子图重跑+上游复用）→📋 cache/diff 层。"看结果再决定"的循环放轮间（用户→新指令→新编译），不放轮内（ReAct）——每轮改都留下完整审计。修改历史（plan_node_id=最后写者之上的完整链）归 Operation Model operations 表（📋 P1）。

## 3. 工作项与 tasks 规划

> 实施顺序 = 提交顺序。每个工作项一个 commit（conventional commits）。

### Task 0 — conversations 改名 + API job 词汇清除 + workflow_steps 改名（判例 N-12/N-13/N-15）
`refactor: 命名统一——conversations / API runs 词汇 / workflow_steps（判例 N-12/N-13/N-15）`

- alembic 迁移（与 Task 3 的 messages.mentions 同批）：`chat_sessions→conversations`、`messages.session_id→conversation_id`、`plan_nodes→workflow_steps`、`outputs.plan_node_id→workflow_step_id`、索引改名。
- **workflow_steps 改名**（2026-07-26 批准；要保留 plan_nodes 可撤回）：plan 一词三用（RunPlan/ContentPlan/plan_nodes + director_plan 节点）真实歧义；表对分裂（workflow_runs 用 workflow 词族、plan_nodes 用 plan 词族）；前端早已叫 step（GenerationStepper/results.stepper.*，现成的 §1 分裂）；Mastra workflow steps 同构（逐步持久化 status/result/suspend）。**概念层不动**：RunPlan 施工图 = workflow_run + 它的 steps（N-11 两个 plan 保留，这不是 N-10 翻案——N-10 否的是概念层清洗，本次是存储层对齐行业词）。窗口期：SSE/registry/打勾流未建，node 词汇未扩散。
- 改名映射：`PlanNode→WorkflowStep`、`NODE_RUNNERS→STEP_RUNNERS`、`execute_node→execute_step`、`bind_plan_node→bind_workflow_step`、`PlanNodeKind→StepKind`、`PlanNodeResponse→StepResponse`、SSE 事件 `step.updated`、metering `plan_nodes.cost` 注释同步；词汇表"节点 PlanNode"条目改"步骤 WorkflowStep（不是 job、不是 task）"。
- backend 机械改名：`ChatSession→Conversation`、`ChatSessionResponse→ConversationResponse`；端点 `/chat/session→/chat/conversation`、`/chat/sessions/{id}/messages→/chat/conversations/{id}/messages`。
- API job 清除：`/projects/{id}/jobs[*]→/projects/{id}/runs[*]`、`job_id→run_id`、`latest_job→latest_run`、`WorkflowRunResponse→RunResponse`。**表/ORM 不动**（`workflow_runs` 表与 `WorkflowRun` 类保留）。
- 前端仅字符串同步（types/pollJob/endpoint 常量，非 UI 工作）。
- MODULE_ARCH §4 登记同步（归属不变，非 ADR）。

### Task 1 — `pipeline/registry.py` skill registry 初集
`feat: skill registry 初集（pipeline/registry.py，含虚拟链座位）`

```python
SkillEntry: name / description          # description = "何时用"（intent prompt 注入用，Mastra skills 同款）
  / kind("skill"|"tool") / behavior("deterministic"|"probabilistic")
  / params_model(Pydantic|None) / summary_template / cost_hint
  / runner(dotted path|None) / node_kind / needs_director / after: tuple
  / requires: tuple[str,...]       # "media"/"transcript"/"speaker_photo"/"voiceprint"
  / produces_outputs: bool         # GENERATION_NODE_KINDS 从此派生
  / retries: int = 0               # Mastra step-level retry 同款座位；通用重试随 provider skill 落地
```
- 登记 11 条：select_clips / write_post / write_quotes / write_carousel / write_article / revise_script / dub_clip(runner=None) / add_music（§4.1 九条）+ remove_filler（实装）+ synthesize_talk_video（虚拟链座位，runner=None，requires=("transcript","speaker_photo","voiceprint")）。
- **behavior 如实**：remove_filler/add_music=deterministic；select_clips/write_*/revise_script=probabilistic。
- `validate_task_list()` 抛 `SkillRejected`（带相近可用 skill）；`dispatchable_skills()` 供 intent prompt；启动自检 runner path ∈ STEP_RUNNERS（延迟 import 防循环）。

### Task 2 — compile_graph 模式②
`feat: compile_graph 模式②——task list 动态物化`

- `TaskSpec` 加 `tasks: list[TaskItem] | None`；`TaskItem{skill, params}` 入 schemas.py。
- `_compile_task_list`（纯函数）：校验（registry + params_model）→ 拓扑（needs_director 注入前奏三节点去重；after 约束；修饰节点挂 clips 节点或空 inputs=作用现有 clips）→ 补默认（count 缺省 5 等纯函数项；DB 依赖默认如 mood 由 runner 运行期解析）→ 落标准 plan_nodes。
- `create_run`：target_id 归属校验 + requires 逐项输入校验（出生点拒收）。
- `GENERATION_NODE_KINDS` → registry 派生（produces_outputs）。
- 模式①零改动；chat service 建 TaskSpec 时回填兼容字段（outputs/clip_count/instruction/target_language）。

### Task 3 — chat loop v1 backend + mentions 座位
`feat: chat loop v1 backend——intent tool calling 二态契约 + mentions 座位`

- 契约（旧 `ChatIntent` action 枚举整体退役，NAMING §1）：`TaskListProposal{type:"task_list",tasks,summary}` / `EditOpsProposal{type:"edit_ops",target_output_id,ops,summary}`；`IntentProposal` 判别联合。`tasks=[]` = 反问（§7，不加第三态）。
- **mentions 座位（迁移同批 Task 0）**：`messages.mentions JSONB default []` + `ChatMention{type: "asset"|"output"|"transcript_segment"|"plan_node", id, label}` + `ChatRequest.mentions` + `ChatMessageResponse.mentions`；service 存取直通，@picker UI 下轮。
- `chat/intent.py`：`IntentAgent→ComposerIntentAgent`（routes.py import 同步）；新增 `ChatIntentAgent.propose(message, context)`——单次 `MiniMaxClient.generate(response_model=IntentProposal)`，prompt 注入 dispatchable_skills() + §6 context。
- Context（service.py 确定性组装，v1 范围）：项目摘要（assets 清单/visible outputs type+一句话/最近 run 状态）+ 近 3 轮消息摘要。
- 流程三分支：task_list 非空→create_run（SkillRejected→带错误反馈修复一次→仍败→"这个我还不会"+可用清单）；edit_ops→边界文案不建 run；tasks=[]→summary 纯回复。LLM 失败 fallback：asset 级→revise_script 兜底；项目级→反问文案。
- assistant message：content=summary；intent=proposal.model_dump()；workflow_run_id=run.id。
- 前端 AssetChatModal **不动**（pollJob 对新 run 照常工作）。

### Task 4 — SSE run events + 唯一 UI 变动
`feat: SSE run events + results 页 loading 换推送驱动`

Backend：`pipeline/routes/runs.py`（新）`GET /api/v1/runs/{run_id}/events`（StreamingResponse）：归属校验；连接即 `run.snapshot` 全量帧（重连幂等）；1s tail workflow_steps，逐节点 hash diff 有变才推 `step.updated`（id/kind/seq/status/stage/summary/error）；run 级变推 `run.updated`（终态含聚合 summary，读取时推导不落列，helper 在 `pipeline/outputs.py` 与 runs 序列化共用）；15s 心跳注释帧；终态关流。无事件存储/重放/投递保证。**step 状态枚举（StepKind 旁的 status Literal）加 `"waiting"` 座位**——HITL/suspend-resume 预留（variant_pick 落地时：spec 写 suspend_payload，POST /runs/{id}/resume 恢复，SSE 契约不变）。

前端（唯一 UI 变动）：
- `apps/web/package.json` + `@microsoft/fetch-event-source`（§8 要求，Authorization header）。
- 新 hook `apps/web/src/lib/use-run-events.ts`：订阅 run 事件，nodes 快照 + run 状态；401 走 apiFetch 同款 clearAuth + UNAUTHORIZED_EVENT。
- `_app.projects.$id.tsx`：latest_run 活跃时订阅 SSE 替代 2.5s setInterval；终态一次性 `fetchResults()`；新 run→重订阅。
- `GenerationStepper`：结构不动，数据源换 SSE——percent = settled/total 实时，label = 当前 running 节点 stage（沿用 `results.stepper.*` 键，新 kind 补键）。**不做打勾流**。

### Task 5 — 量化摘要（backend）
`feat: 节点量化摘要（spec.summary + 序列化）`

- runner 完成时按 registry summary_template 填 `node.spec.summary`（jsonb_set 独立 session）：remove_filler "Removed {filler_count} fillers · {repeat_count} repeated takes"；add_music "Scored · {mood} bed"；clips_pipeline "Selected {n} clips · {total_seconds}s total"；derivative_gen "Wrote a {type} · {word_count} words"；script "Revised {scope}"。
- `StepResponse`（原 PlanNodeResponse）加 `summary`（序列化器同 stage 点 lift）。

### Task 6 — remove_filler + add_music 实装
`feat: remove_filler / add_music skills 实装（全链路 hello world）`

- **`tools/filler.py`（新，确定性）**：`FILLER_LEXICON`（en: um/uh/er/ah/mm/hmm；zh: 呃/嗯/啊/那个——保守防误伤）；`detect(words, language) -> FillerReport{ranges, filler_count, repeat_count}`：normalize 匹配 + 相邻重复 n-gram（n≥2）标先出现区间。纯函数。
- **`pipeline/clip_spec.py`**：`remove_range(spec, start, end) -> ClipSpec`（TS removeRange 的 Python 镜像，全栈同名 §1；切 kept 插 hidden + 丢完全落区间 cue）。折衷注明：cue 非词级，混合 cue 保留。
- **`run_remove_filler`**：目标 clips = 上游 output_refs 或项目现有 clips（render_spec 非空）；逐条 detect → remove_range → 写回 + render_status=PENDING + fan-out render 节点；**消费边记 `spec.target_output_ids`**（跨 run DAG 边落库）；聚合计数填 summary。无 clips/零 filler → done + 相应文案。
- **`run_add_music`**：params `{mood?, music_id?, gain_db?}`；`resolve_music_ref(db, music_id or mood or brand 默认 or "calm")` → 烘焙 ClipMusic 进 render_spec → 同构 fan-out + target_output_ids；summary "Scored · {mood} bed"。mood 无曲目 → failed + 清晰 error。
- `STEP_RUNNERS`（原 NODE_RUNNERS）注册两 kind；`StepKind` Literal 加两值（N-03 零迁移）。

### Task 7 — 文档收尾（治理信用）
`docs: CHAT_ARCHITECTURE v1 backend 落地 + NAMING/MODULE_ARCH/API 同步`

- `docs/CHAT_ARCHITECTURE.md`：Status → "v1 backend 已实现（2026-07-26）"；注明偏离点（ports→requires+after；dub_clip/synthesize_talk_video 登记未实装；UI 冻结——chat UI/打勾流归下轮；SSE 仅接 results 页 loading）。
- `docs/NAMING.md`：词汇表 +「任务列表 task list / `TaskItem`」，"节点 PlanNode"条目改「步骤 WorkflowStep（不是 job、不是 task）」；判例 N-12（chat_sessions→conversations）/ N-13（API job 词汇清除）/ N-14（ChatIntent 退役 → IntentProposal 二态；空 tasks=反问）/ **N-15**（plan_nodes→workflow_steps：plan 一词三用歧义 + 表对词族分裂 + 前端已叫 step + Mastra steps 同构；概念层 RunPlan 保留，存储层对齐行业词——非 N-10 翻案）；workflow_runs 改名动议记录在案并撤回。
- `docs/MODULE_ARCHITECTURE.md`：§4 表名同步（conversations）；**新增"行业词汇对照"节**（Mastra/Agno/OpenAI ↔ 本系统，对照唯一事实源）：

  | 行业通用词 | 本系统对应 | 说明 |
  |---|---|---|
  | Agents（LLM 决策单元） | `skills/`（班组） | Mastra Agents 含 Tools/Skills 子集；我们的 agent 按 NAMING 叫 skill |
  | Tools（确定性执行） | `tools/`（机械） | 同名同物 |
  | Skills（组合能力） | `pipeline/registry.py` skill 条目 | = Mastra Skills 的登记处 |
  | Workflows（编排图+执行） | RunPlan 内核（orchestrator + plan_nodes + worker 认领） | Workflow State=run 状态机；Suspend/Resume=`waiting_human`；Snapshots=spec/context；HITL=variant_pick gate（📋） |
  | workflow run（执行实例） | `workflow_runs` 表 | 行业标准全名（每 run 自带其编译出的 workflow=节点图） |
  | Agent Runtime | `app/worker.py` | 执行进程 |
  | Memory | `memory/`（speakers/brand_templates） | persona/brand block 单向注入 |
  | Evals（Scorers/Gates/Verdicts） | 📋 Phase 3 verify 节点 + variant_pick gate | verify=节点 / eval=活动，与 Mastra 兼容 |
  | Threads / Conversations | `conversations` + `messages` | OpenAI Conversations API 同款 |
  | Agent Observability | metering（plan_nodes.cost）+ structlog + 📋 METRICS.md | 横切不开包（§7） |
  | Channels | `distribution/` | 直发渠道 |
  | Guardrails | 📋 合规底座（ADR-026 分类器/C2PA） | ROADMAP §7/§8 |

  反对照：`pipeline/` 模块 ≠ Mastra Workflows（Pipeline = 摄入+ASR+编排+渲染，大于 Workflows）；`chat/` ≈ Agno Interfaces。
- `docs/API.md`：`POST /api/v1/chat` 契约变更 + `GET /api/v1/runs/{id}/events` + `/jobs→/runs` 改名。
- 本简报入 `docs/tasks/chat-loop-v1.md` 并在 `docs/README.md` 清单登记。

## 4. 命名审计（NAMING §5 触发点）

| 新名字 | 过八条 |
|---|---|
| `conversations`（表改名） / API `runs` 词汇 | §1；session 撞 auth session；job 指 run 违反"run 不是 job"（N-12/N-13）；workflow_runs 保留（行业全名，每 run 自带 workflow=节点图） |
| `workflow_steps`（表改名） | §1 消歧（plan 一词三用）；表对词族统一（workflow_runs+workflow_steps）；前端早已叫 step；Mastra steps 同构（N-15） |
| `pipeline/registry.py` / `SkillEntry` / `SKILL_REGISTRY` | 单词名词；registry 有 ADR-030 先例 |
| `TaskItem` / `TaskListProposal` / `EditOpsProposal` / `IntentProposal` | doc §3 契约原名；词汇表登记 |
| `remove_filler` / `add_music` / `synthesize_talk_video` | doc §4 定名；N-03 零迁移 |
| `tools/filler.py` `detect()` | 机械层确定性单元 |
| `remove_range()` | TS removeRange 全栈同名（§1） |
| `ChatIntentAgent` vs `ComposerIntentAgent` | §5 同名不同物审计 |
| `runs.py` / `use-run-events.ts` | REST 复数资源（§4 API 命名） |

## 5. 验证（无测试套件，端到端——CLAUDE.md Testing）

1. 起全栈：api + worker + render service + web（demo seed 已有 ASR 好的视频 + 5 clips）。
2. **chat API 全链（curl）**：POST /api/v1/chat（项目级，"去掉口头禅，剪 3 条高光，加个音乐"）→ intent=task_list + run_id → GET /projects/{id}/runs/{run_id} 节点逐个 done + summary → clips 重渲染完成、带配乐。
3. **SSE（curl -N）**：/api/v1/runs/{id}/events 看 snapshot/step.updated/run.updated/心跳/终态关流。
4. **唯一 UI 变动**：触发 run → results 页进度条/label 实时随 SSE 更新（无 2.5s 跳变），终态产物自动刷新。
5. **反问/拒收**：模糊指令→tasks=[] 纯回复；未知 skill→修复一次→"这个我还不会"。
6. **edit_ops 边界**："把第二段结尾剪掉 2 秒"→边界文案不建 run。
7. **模式①回归**：composer /generate 全流程 + demo seed 启动不破；AssetChatModal 现有轮询路径不破；conversations 改名后 chat 历史可读。

## 6. Prohibited Behaviors（实施红线，CHAT_ARCH §12 + 本轮补充）

- 禁 ReAct 式多步推理 loop——轮内单次 tool calling。（重评触发：出现"不看执行结果就规划不了、反问也救不回"的指令时，放宽为有界 N 次修复回路，仍禁框架。依据：指令是命令形，观察-决策循环在轮间；Mastra 同样把 Agents 自主循环与 Workflows 确定性执行分作两物——我们与其同构。）
- 禁 LLM 直接写 node spec / 自由生成执行代码——一切经 registry + compile_graph。
- 禁引入 agent 框架（Agno/LangGraph 等，Mastra/Agno 只是词汇参照，不是依赖）。
- 禁把 SSE 做成事件总线（事件存储/投递保证/重放）。（重评触发：出现第二个事件消费者——METRICS 埋点/审计流/通知扇出；届时事件总线作内部实现藏在不变客户端契约后。依据：plan_nodes 行已含事件全部信息，事件流是表的纯函数；快照+diff 重连幂等。）
- 禁 chat 绕开 `orchestrator.create_run` 自建 run。
- 禁 registry 无评审膨胀——skill 准入必须过 NAMING §7/§8。
- 禁复活 plans 版本树 / jobs 表 / 五层开包 / 事件总线包（v2.0 评审已判）。
- 禁动 UI（唯一例外：Task 4 的 SSE 接线 + 字符串级同步改名）。
- 禁给 workflow_runs 改名（动议已撤回，行业全名）。
