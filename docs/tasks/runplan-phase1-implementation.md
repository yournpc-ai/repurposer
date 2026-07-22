# RunPlan Phase 1 施工图：实施计划（已批准 2026-07-22）

> Status: Approved — in implementation
> 准绳：`docs/tasks/runplan-persistence.md`（简报）；决策：ADR-028/029/030；概念：`docs/AGENT_ARCHITECTURE.md` §12
> 评审修正 4 条已吸收（见 §1.1）；执行纪律：阶段 A→F 小步提交、每步可编译。

## 1. Context

生成内核现状是"函数调用链 + JSON blob"：`ContentPlan` 跑完即焚（复用靠 `project.content_plan` 盲目 blob）、`workflow_runs.context["output_status"]` 靠进程内 asyncio 锁 + `flag_modified` 续命、定向重生靠伪造 plan、产物劈成 clips/derivatives 两张不对称的表、token usage 全量丢弃。Phase 1 把内核换成 **plan_nodes（施工图）+ outputs（统一产物）+ 节点级血统 + 逐节点计量**，零行为变化（同输入同产出），破坏性更新（不保留数据、零兼容层）。

已核实现状（行号为 2026-07-22 main）：

- 编排单体 `apps/api/app/services/generation.py:953-1180`；五宗罪点位：`_run_context_lock` :81、伪造 plan :569-585、`project.content_plan` 复用 :1069、speaker 埋点 :1016、scope if-else :995-999。
- WorkflowRun 创建点全库仅 **3 个物理位，覆盖 4 个逻辑入口**：`routers/projects.py:397`（/generate）、`services/chat.py:244`（chat dispatch；derivative/clip 定向重生经 `routers/derivatives.py:87-121`、`routers/clips.py:383-415` → chat()）、`services/demo_seed.py:250`。`derivative_dispatch.py` 不建 run，只是 DerivativeType→agent 注册表。
- worker `app/worker.py:32-54` 三认领源（Asset / WorkflowRun / Clip.render_status），全部 `FOR UPDATE SKIP LOCKED`（`services/jobs.py`）；`reap_stale` jobs.py:119-153。
- usage 零捕获：所有 LLM 调用汇聚于唯一咽喉点 `clients/minimax.py:60-103` `MiniMaxClient.generate`（`data["usage"]` 被丢弃）；ADR-025 provider interface 代码尚不存在。
- render 链：`Clip.render_status` PENDING → `services/rendering.py:render_clip()` :86-175 → 回写 video_url/srt_url。重渲染有不经过 run 的路径（`routers/clips.py:160-183` render / :266-371 dub / :218-263 translate-captions）。
- publications 表**不存在**；DISTRIBUTION.md:64-66 设计已是 output_id 单 FK——Phase 1 不建表，简报验收项天然满足。
- 前端步骤清单唯一消费者 `apps/web/src/routes/projects.$id.tsx`（轮询 `/projects/{id}/results`，读 `latest_job.context.output_status` + 后端算好的 `ui_step`）；产物消费面 8 个组件 + library + editor；无 openapi codegen，类型手写。

### 1.1 评审修正（2026-07-22 批准时附带，必须执行）

1. **D1 概念污染防控**：outputs 混入非产物（content_plan）是唯一污染点——必须提供 `visible_outputs()` 统一过滤助手，results/library/export 三处及未来 MCP/画廊全部走它，`INTERNAL_TYPES` 不得从任何查询漏出。
2. **D9 微行为变更声明**：定向重生成从"伪造 plan"变"真导演调用"是**有意的**偏离"同输入同产出"——阶段 C 提交信息里显式声明，避免误读为意外漂移。（验收 diff 只覆盖 demo 全量生成路径，不冲突。）
3. **render_error 顶级列已批**：它随 render_status 认领写集同写同读，符合 ADR-030 规则 2；保留"评审不过则回 payload"自首注释。
4. **R1 纪律**：阶段 A→F 顺序小步提交、每步可编译，不得中途合并。

## 2. 关键设计决策（10 条）

- **D1 导演计划 = 内部 outputs 行**：`ContentPlan` 持久化为 `outputs[type='content_plan', provenance='generated']`，payload 即 ContentPlan `model_dump()`；director_plan 节点 `output_refs` 指向它，下游节点经它读取。`project.content_plan` 列删除，Phase 1 每 run 重排（asset-hash 复用是 Phase 2）。配 `visible_outputs()` 过滤助手（评审修正 1）。理由：不加 plan_nodes 列、符合"节点产物"概念（§12.1）、Phase 2 director_understand 复用同机制。
- **D2 render 双轨**：render 节点提供步骤可见性/成本位，但**认领仍走 `outputs.render_status`**——保住无 run 的重渲染路径（手动 render/dub/translate）。节点状态在 fan-out 与 render 终态两处镜像更新。
- **D3 节点级并行**：worker tick 认领节点后 `asyncio.create_task` 执行（并发上限 4），保住今天 derivatives 的 gather 并行度；Asset/render 两源保持现状顺序 await（今天 render 本就阻塞 tick，不变差）。
- **D4 API 统一 `/outputs/*`**：删 `routers/clips.py`、`routers/derivatives.py`，新建 `routers/outputs.py`（clip 动作 = 子路径 render/cover/translate-captions/dub/revise/regenerate）；响应为统一 `OutputResponse`；前端按 `type` 分区。UI 路由 `/projects/$id/clips/$clipId` 保留（用户可见 URL，非数据词汇）。
- **D5 计量 = contextvar + 唯一咽喉点**：新建 `app/services/metering.py`，`bind_plan_node(node_id)` context manager 由节点执行器设置；`MiniMaxClient.generate` 捕获 `data["usage"]` 调 `record_usage()`，SQL 表达式原子累加进 `plan_nodes.cost`（`{prompt_tokens, completion_tokens, fixed_cost}`，无读改写）。节点内串行 + contextvars 按 task 隔离，无竞态；retry/fallback 自然累加（每次尝试计价）。image/music gen 无 usage 返回则跳过。不落 step-name 过渡。
- **D6 拓扑代码确定 + 注册表守门**：`lower_plan(task_spec) -> list[NodeSpec]` 纯函数；`kind`/`type`/`status` 一律 `String` 列 + 应用层 Literal/注册表校验（新类型零表迁移）；`OUTPUT_PAYLOAD_SCHEMAS`（type→BaseModel）复用现有 agent 响应模型（Post/Quotes/CarouselResponse/Article/ContentPlan），新增 `ClipPayload`。
- **D7 run 行只管 run 级状态机**：status PENDING→RUNNING（首个节点被认领时）→COMPLETED/FAILED；`current_step` 列删除（API 派生 = running 节点 kind）；`progress` 由节点状态聚合（done+skipped / total）。
- **D8 失败级联 skipped**：节点最终失败 → 下游传递标 `skipped`（否则 run 永不收尾）；收尾口径沿用"全败才 failed" = 生成类节点（clips_pipeline + *_gen）全部 failed → run FAILED，否则 COMPLETED + project REVIEW。
- **D9 定向修订 = 小拓扑**（伪造 plan :569-585 整体删除）：scope=hook/clip → `[script]`（reviser，带 instruction）；scope=derivative → `[director_plan → {post|quotes|carousel|article}_gen(spec.target_id)]`（真导演计划——评审修正 2 的有意行为变更）；scope=render → `[render]`（置 render_status=PENDING）。
- **D10 四个入口零旁路**：全部 `WorkflowRun(` 只在 `orchestrator.create_run()`；demo_seed 走 `create_run` + `execute_run_inline`（与 worker 共享同一 `execute_node`，仅认领循环不同）。

## 3. 阶段 A：数据模型 + Alembic 迁移

**`app/models/tables.py`**：

`PlanNode`（新表 `plan_nodes`，Owner: Pipeline）：`id` UUID PK / `run_id` UUID FK `workflow_runs.id` **`ondelete="CASCADE"`** / `kind` String(50) / `status` String(20) default `'pending'` / `seq` Integer / `inputs` JSONB default `[]` / `spec` JSONB default `{}` / `output_refs` JSONB default `[]` / `cost` JSONB nullable / `error` Text / `attempt` Integer default 0 / `started_at` `finished_at` `created_at` `updated_at`。索引：`(run_id, status)`、`(kind, status)`。

`Output`（新表 `outputs`，替代 clips/derivatives）：`id` / `project_id` FK / **`plan_node_id` FK `plan_nodes.id` `ondelete="SET NULL"` nullable** / `type` String(50) / `language` String(10) / `status` String(50) default `'generated'` / `provenance` String(20) default `'real'` / `payload` JSONB / `files` JSONB（`{video, srt, image}` URL）/ `source_ref` JSONB nullable / `render_spec` JSONB nullable / `render_status` Enum(RenderStatus) nullable（NULL=未请求，认领谓词）/ `render_error` Text nullable（评审修正 3 已批）/ `score` JSONB nullable / `publishing` JSONB（title/description/hashtags/cover_image_url/topic）。索引：`(project_id, type)`、`(render_status)` partial、`(plan_node_id)`。

修改：`WorkflowRun` 删 `current_step`；`Project` 删 `content_plan`；删 `Clip`、`Derivative` model。`ChatSession.asset_type` 不动。

**`app/models/schemas.py`**：
- `PlanNodeKind` Literal：`preprocess | persona_bootstrap | director_plan | clips_pipeline | post_gen | quotes_gen | carousel_gen | article_gen | script | render`（`director_understand/selection/dub/music/verify` 仅注释标注 Phase 2/3，不注册不实现）。`PlanNodeStatus` Literal：pending/running/done/failed/skipped。`OutputType` Literal：clip/post/quotes/carousel/article/content_plan。
- `OUTPUT_PAYLOAD_SCHEMAS`：`{clip: ClipPayload, post: Post, quotes: Quotes, carousel: CarouselResponse, article: Article, content_plan: ContentPlan}` + `INTERNAL_TYPES = {"content_plan"}`。写入 `model_dump()`、读取 parse 回 typed model。
- `ClipPayload`：`{hook, title_options, music_mood, duration}`；segment/start/end 进 `source_ref`。
- `OutputResponse`（通用列全量 + parsed payload）、`PlanNodeResponse`（id/kind/status/seq/error/cost/spec.stage）；`ProjectResultsResponse` 改：`outputs: list[OutputResponse]` + `latest_job.nodes: list[PlanNodeResponse]`；`WorkflowRunResponse` 加聚合 `cost`；删 `ProjectResponse.content_plan`（schemas.py:389）、`ClipResponse`/`DerivativeResponse`/`ClipUpdate`/`DerivativeUpdate`。

**迁移**（单文件，down_revision = `bfa24df7e8db`）：create plan_nodes + outputs + 索引 → drop clips、derivatives → drop projects.content_plan、workflow_runs.current_step。downgrade 重建空表结构。

## 4. 阶段 B：orchestrator（物化 / 走图 / 执行 / 收尾）

**新建 `app/services/orchestrator.py`**：

```python
class TaskSpec(BaseModel):   # 任务书（意图归一）
    outputs: list[str]; clip_count: int; target_language: str
    instruction: str | None; tone_settings: dict | None
    brand_template_id: str | None
    scope: str = "full"; operation: str = "regenerate"; target_id: UUID | None

async def create_run(db, project, task: TaskSpec) -> WorkflowRun
def lower_plan(task: TaskSpec) -> list[NodeSpec]      # 纯函数，拓扑代码确定
async def execute_node(node_id: UUID) -> None         # 唯一执行入口（worker/inline 共享）
async def execute_run_inline(run_id: UUID) -> None    # demo_seed 用：拓扑序直执
```

- **物化**（`create_run`）：建 run（status=PENDING，context 存任务书原参数）+ 按 `lower_plan` 批量插节点。full 拓扑：`preprocess → persona_bootstrap → director_plan → {clips_pipeline?, post_gen?, quotes_gen?, carousel_gen?, article_gen?}`（按 task.outputs presence-gating；`seq` 展示序 1/2/3/10/11/12/13/14）。targeted 拓扑按 D9。render 节点此时不建（clip 未存在）。
- **认领**（`claim_ready_node`，放 `services/jobs.py` 并列现有认领器）：`status='pending'` + 上游全 done（`NOT EXISTS (SELECT 1 FROM jsonb_array_elements_text(inputs) AS up JOIN plan_nodes p ON p.id = up.value::uuid WHERE p.status != 'done')`）+ 资产就绪门（`claim_pending_run` 的 NOT-EXISTS 子查询平移）→ `FOR UPDATE SKIP LOCKED` 翻 running、started_at、attempt+1；run 仍 PENDING 则顺带翻 RUNNING。**`claim_pending_run` 删除**。
- **执行**（`execute_node`）：kind → `NODE_RUNNERS` 注册表（`app/services/node_runners.py`）→ `async with bind_plan_node(node.id)` → runner(db, run, node, project) → 成功置 done/finished_at + 写 output_refs；终败置 failed + **级联 skipped 下游**；每次结束调 `maybe_finalize_run`（SELECT run FOR UPDATE；无 pending/running → 按 D8 收尾 + progress=100）。
- **render fan-out**：clips_pipeline 完成后为每个带 render_spec 的 clip output 建 render 节点（`inputs=[clips_pipeline]`，`spec={"output_id": ...}`）+ 置 `render_status=PENDING`。render 节点不经 `claim_ready_node`（D2）——`rendering.py` 终态写回时镜像节点 done/failed（按 `spec.output_id` 找节点）。
- **run COMPLETED 时** project.status=REVIEW（沿用 generation.py:1152）。

**`app/services/node_runners.py`**（generation.py 逻辑平移，签名统一 `(db, run, node, project)`）：

| 现状（generation.py） | 节点 kind | 平移说明 |
|---|---|---|
| :1001-1014 collect + 无素材报错 | `preprocess` | 校验 + log；下游节点自行重取（texts 廉价 DB 读；media 由 director_plan/clips_pipeline 各自 collect——同输入同产出，代价是重复下载，Phase 1 接受） |
| `_resolve_or_create_speaker` :336-407 | `persona_bootstrap` | 原样抠出 |
| :1069-1086 reuse-or-plan | `director_plan` | **删复用分支**，每 run 调 `content_director_agent.plan`，产物=D1 content_plan outputs 行 |
| `_run_clips_task` :724-931 | `clips_pipeline` | 原逻辑（含一次自动重试、brand/music、build_clip_spec）；产物=N 个 `outputs[type=clip]` + plan_node_id + render_status=PENDING + render fan-out；stage hint 写 `node.spec["stage"]` |
| `_run_derivative_task` :641-721 × N | `post_gen` 等每类型一节点 | 经 `derivative_dispatch.generate_derivative`（注册表不动）；quotes 配图进 `files.image`；`spec.target_id` 存在=定向重生成（更新目标行而非新建） |
| `_run_targeted_revision` hook/clip :500-527 | `script` | reviser + 更新目标 clip output 的 payload |
| `_run_targeted_revision` render :529-545 | `render`（direct） | 置 render_status=PENDING |
| `_delete_prior_outputs` :934-950 | 并入 gen runners | full run 先行幂等删除本项目同类 outputs |
| run 收尾 :1134-1161 | `maybe_finalize_run` | D8 口径 |

**删除**：`_run_context_lock`/`flag_modified`/`output_status` 全套（:81, :415-484, :1169-1178）、伪造 plan（:569-585）、`_LEGACY_OUTPUT_NAMES`/`_normalize_*`（:92-123）、scope if-else。`generation.py` 文件删除。`_save_minimax_image`/`_save_quote_card_image`/`_generate_clip_cover_image`/`collect_asset_media` 移至 `node_runners.py`。

**worker.py**：tick 第二源改为 `while len(running) < 4: node = claim_ready_node(); if not node: break; running.add(create_task(execute_node(node.id)))`；无可认领且无在跑时 sleep。`reap_stale` 增补：running 节点 → pending；stuck run（无 pending/running 节点但未收尾）→ finalize。

**metering.py**：`bind_plan_node` contextmanager + `record_usage(usage)`（新开 session，SQL 表达式累加 cost）。`clients/minimax.py:92` 处捕获 `data.get("usage")` 调用之（缺失则静默跳过）。run 级成本 = 节点聚合（results 端点序列化时 SUM）。

## 5. 阶段 C：run 创建点切换（零旁路）

1. `routers/projects.py:390-417` POST /generate → `orchestrator.create_run(project, TaskSpec(**req.model_dump()))`；project PROCESSING + seed prompt 保留。
2. `services/chat.py:216-262` → create_run（scope/target/operation/instruction 映射进 TaskSpec）。
3. 定向重生（derivatives/clips regenerate）已走 chat()，随 2 收编。
4. `services/demo_seed.py:250-284` → create_run + `execute_run_inline`；完成判定改 outputs[type=clip] 计数 + run COMPLETED。

验收 grep：全库 `WorkflowRun(` 仅 orchestrator.py。
**提交信息显式声明**（评审修正 2）：定向重生成由伪造 plan 改为真导演调用，是有意的微行为变更。

## 6. 阶段 D：读路径与 render 链

- `services/rendering.py`：`render_clip` → `render_output(output_id)`，终态写 files/render_status + 镜像 render 节点；`_absolutize` 不动。`jobs.py:claim_pending_render` 改 `Output.type=='clip' AND render_status==PENDING`。
- `routers/outputs.py`（新，合并 clips.py+derivatives.py 到 `/outputs/{id}/...`）：GET/PUT、/render、/cover、/translate-captions、/dub、/revise、/regenerate（后两个仍经 chat）。`_get_output_for_user` 合并两个取数函数。
- `routers/projects.py`：results 端点（:256-278）改经 `visible_outputs()` + 附 latest_job.nodes；`_compute_ui_step`（:173-227）改从 plan_nodes 派生（kind/stage→现有 key：preprocess/persona_bootstrap→analyze、director_plan→plan、clips_pipeline 按 spec.stage→selecting_segments/building_specs、*_gen→writing_copy、quotes 配图→generating_image、render→ready_to_render，**i18n 零新增**）；项目删除级联（:336-337）改 outputs（plan_nodes 随 run CASCADE）；列表端点（:472-497）、export（:515-532）、缩略图（:87-94）全走 `visible_outputs()`。
- `routers/library.py`：union 改单表 outputs（经 `visible_outputs()`；preview/download 从 files/publishing 取）。
- `services/project_context.py:106-130`、`services/music.py:184` 改查 outputs。

## 7. 阶段 E：前端（触点已核实）

- `lib/types.ts`：`Clip`/`Derivative`（93-136）→ `Output` + `PlanNode`；`Job` 删 current_step。
- `projects.$id.tsx`：局部 interface（24-56）→ nodes 驱动；`runningTabs`/`failedTabs`（177-195）由节点 kind→tab 映射一处；删 `OUTPUT_KEY_TO_TAB` legacy 兜底（76-87, 292-302）；轮询条件（137-163）改"run 未终态 OR 任一 output render_status in pending/rendering"；产物分区（240-253）改 `outputs.filter(type)`。
- `GenerationStepper.tsx`：不动（ui_step 仍后端算好，keys 不变）。
- 产物卡片 6 个（ClipCard/ClipDetailModal/PostCard/QuotesCard/CarouselCard/ArticleCard）：字段路径改 payload/files/publishing；端点改 `/outputs/{id}/...`；`AssetChatModal` asset_type 词汇保留。
- editor `projects.$id.clips.$clipId.tsx`：GET/PUT `/outputs/{id}`、/render、/translate-captions、/dub。
- `library.tsx`：type 词汇已对齐，只改数据源字段。
- i18n：**零新增**。

## 8. 阶段 F：文档同步

- `docs/MODULE_ARCHITECTURE.md` §4：outputs/plan_nodes ✅，删 clips/derivatives 过渡行；§3 Pipeline 现状代码 +orchestrator/node_runners。
- `docs/AGENT_ARCHITECTURE.md` §11 critical files + §12.7 Phase 1 标记已落地。
- `docs/tasks/runplan-persistence.md` status → Implemented；§4.4 口径同步为"3 物理位覆盖 4 逻辑入口，derivative_dispatch 不建 run"。
- 不需要新 ADR。

## 9. 验收方案

1. **迁移**：fresh DB `alembic upgrade head` → plan_nodes/outputs 存在；clips/derivatives/content_plan/current_step 不存在。
2. **grep 硬指标**：`_run_context_lock`、`flag_modified`、`output_status`、伪造 plan 文案 `"Regenerate this derivative faithfully"`、`_LEGACY_OUTPUT_NAMES` 零命中；`WorkflowRun(` 仅 orchestrator.py；`ck_pub_target` 零命中。
3. **`python scripts/seed_demo.py --force` 全绿**（逐项断言）：
   - run COMPLETED；plan_nodes 全 done（preprocess/persona_bootstrap/director_plan/clips_pipeline + 5×render）；
   - LLM 节点（persona_bootstrap/director_plan/clips_pipeline）`cost` 非空且 prompt_tokens>0；
   - 5 个 `outputs[type=clip]` 每个 `plan_node_id` = clips_pipeline 节点、render_status 非 NULL、payload/source_ref/render_spec/publishing 齐备；content_plan output 存在且 internal；
   - worker 渲染完成后 `files.video` 非空。
4. **同输入同产出 diff**：main 与分支各跑一次 seed，对比**结构不变量**——clip 条数=5、每条 hook/title_options/render_spec 齐备、segment 边界在源时长内、render_spec 顶层键集一致、caption cue 来自同一 ASR words。LLM 采样方差不纳入逐字 diff（简报口径 = 条数/文案结构/渲染参数）。
5. **API 冒烟**：results 返回 outputs+nodes 且无 output_status；chat 重生成某 post → 小拓扑 [director_plan→post_gen] 两节点 done、目标行更新而非新增；`/outputs/{id}/render` 走通。
6. **前端手测**：步骤清单节点状态与 tab 圆点、editor 渲染、library、四卡片重生。

## 10. 风险与回滚

| 风险 | 缓解 |
|---|---|
| R1 大爆炸 PR | A→F 顺序小步提交、每步可编译（评审修正 4，纪律必须守住） |
| R2 render 双轨不一致 | 镜像写入集中两处：fan-out 与 rendering.py 终态；无 run 的重渲染本无节点 |
| R3 inline 与 claimed 执行分叉 | 共享 `execute_node` 单入口；inline 仅替换 claim 循环 |
| R4 计量漏记/串记 | contextvar 由执行器 context manager 绑定；验收断言 LLM 节点 cost 非空 |
| R5 节点并行改变 LLM 并发量 | cap=4 ≈ 今天 gather 规模；单 worker |
| R6 type String 列失去 DB 约束 | OUTPUT_PAYLOAD_SCHEMAS + Literal 守门（ADR-030 规则 1） |
| R7 前端漏改导致永远转圈 | 按 §7 清单逐文件核对；results 形状变更编译期可抓 |

**回滚**：`git revert` + `alembic downgrade`（数据本就不保留，demo seed 重跑恢复任意一侧）。无 feature flag——破坏性一次到位是简报明确要求。

## 11. 明确不做

不引入 agent 框架/LangGraph；LLM 不参与拓扑；不为虚拟产物线建 variant gate/media provider/avatar 类型；不留 clips/derivatives 过桥层；不合并导演两步（Phase 2）；不新建 worker/队列；不建 publications 表；operations、C2PA、审核队列不在本期。
