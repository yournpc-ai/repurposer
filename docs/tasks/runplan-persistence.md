# RunPlan 持久化 + outputs 统一 — 实施简报

> Status: Ready for dev（2026-07-22）
> 决策依据：ADR-028（RunPlan）/ ADR-029（双链并列，含 Amendment）/ ADR-030（产物统一）
> 概念基线：`docs/AGENT_ARCHITECTURE.md` §12（八概念/导演两步/质检节点/分期）——开工前必读
> 排期：ROADMAP §1 P1（地基）
> **破坏性更新**：不保留数据（demo seed 重跑即可），直接改表，不写过桥迁移/兼容层。

## 1. 一句话目标

把生成内核从"函数调用链 + JSON blob"换成"**施工图（plan_nodes）+ 统一产物（outputs）**"；Phase 1 零行为变化（同输入同产出），Phase 2 导演两步走，Phase 3 质检节点。

## 2. 概念基线（八个，没有第九个）

任务书（意图归一）→ 预处理（ASR/提取）→ 导演两步（看懂素材/分任务）→ 班组（选段/编剧/文案/配音/渲染，每工种一节点）→ 质检（单产物+全片）→ 施工图（plan_nodes：计划+账簿）→ 产物（outputs 统一表）→ 分发（零变化）。

## 3. 数据模型

### 3.1 `plan_nodes`（新表，Owner: Pipeline）

| 列 | 类型 | 说明 |
|---|---|---|
| id / run_id | UUID FK workflow_runs | 属于哪次 run |
| kind | enum | `preprocess / persona_bootstrap / director_understand / director_plan / selection / script / post_gen / quotes_gen / carousel_gen / article_gen / dub / music / render / verify`（Phase 1 先用粗粒度子集，见 §4.2） |
| status | enum | `pending / running / done / failed / skipped` |
| seq | int | 图内序号（步骤清单展示序） |
| inputs | JSONB | 上游节点 id 列表（边） |
| spec | JSONB | 节点参数（instruction/语言/count/模型路由等，DB 不理解的载荷） |
| output_refs | JSONB | 产出引用（outputs 行 id 列表） |
| cost | JSONB | `{prompt_tokens, completion_tokens, fixed_cost}`——ADR-025 接口层写入 |
| error / attempt | text / int | 失败信息与第几次尝试 |
| started_at / finished_at / created_at / updated_at | ts | |

索引：`(run_id, status)`、`(kind, status)`（认领与聚合查询）；成本预估查询形状 = `avg(cost) by kind`。

### 3.2 `outputs`（新表，替代 clips/derivatives；Owner: Pipeline）

按 ADR-030：通用列 `id / project_id / plan_node_id（血统 FK，ondelete SET NULL）/ type / language / status / provenance(real|generated) / payload JSONB / files JSONB / source_ref JSONB? / render_spec JSONB? / render_status? / score JSONB? / publishing JSONB`。

**三条 payload 规则**（评审红线）：
1. 默认进 payload，`OUTPUT_PAYLOAD_SCHEMAS`（type→BaseModel）写入 `model_dump()`、读取 parse 回 typed model（沿用 ClipSpec/render_spec 先例）；
2. 需要 SQL 谓词/索引/认领的字段才升级为顶级列（`render_status` 是先例）；
3. 顶级通用列只收跨类型字段（plan_node_id / provenance / score / publishing / type / language / status）。

### 3.3 退役与改造

- `clips` / `derivatives`：删表，demo seed 重建为 outputs 行；
- `project.content_plan` blob：删除（素材理解 Phase 2 挂 `director_understand` 节点产物，不再存 project）；
- `publications`：按 `output_id` 单 FK 设计落地（双 FK + CHECK 不建）；
- `workflow_runs.current_step`：退役为查询（`plan_nodes WHERE run_id=X AND status='running'`）；`progress` 由节点状态聚合。

## 4. 编排改造

### 4.1 orchestrator（新，`services/orchestrator.py`）

- **物化**：run 创建时按任务书 lowering 出固定拓扑——**拓扑代码确定，LLM 不参与拓扑**；
- **走图**：就绪节点（上游全 done）→ 置 pending 可认领 → worker `FOR UPDATE SKIP LOCKED` 节点级认领（破坏性一次到位，不留 run 级过渡）；
- **完成判定**：无 running/pending 节点 → run 收尾（成败口径沿用"全败才 failed"）。

### 4.2 现状函数 → 节点映射（Phase 1 粗粒度）

| 现状（generation.py） | 节点 kind | 备注 |
|---|---|---|
| collect_asset_texts/media | `preprocess` | 已有逻辑，包成节点 |
| `_resolve_or_create_speaker`（:1016） | `persona_bootstrap` | 从 run_generation 抠出，成本可见 |
| `content_director.plan` | `director_plan`（Phase 1 单趟；Phase 2 拆 `director_understand`+`director_plan`） | |
| `_run_clips_task` | `clips_pipeline`（Phase 1 复合；Phase 2 拆 `selection`/`script`） | |
| `_run_derivative_task` × N | `post_gen` 等每类型一节点 | |
| render 认领 | `render` | 沿用现有 render_status 机制 |

### 4.3 必须消灭的三样东西（验收硬指标）

1. `_run_context_lock` + `flag_modified` hack（generation.py:81）——节点行级更新替代 output_status JSON blob；
2. 伪造 plan 代码路径（`:569-585`）——定向修订改为小拓扑图（scope=hook → `[script 重跑(带 instruction)]`）；
3. `project.content_plan` 盲目复用（`:1069`）——Phase 2 由 asset hash 失效替代。

### 4.4 防旁路：全部 run 创建点

`run_generation` / `derivative_dispatch` / chat dispatch / `demo_seed` ——四处统一走 orchestrator，验收含"无旁路"。

## 5. Phase 2：导演两步走

- 两次 LLM 调用：**看懂素材**（自足契约：素材理解含论点+transcript 位置/金句/主题/受众，分任务不再读原稿）→ **分任务**（分镜表：论点→槽位+任务卡+未用/撞车报告）；
- 素材理解按 **asset 内容 hash** 失效（素材变才重算）；分任务每 run 必重排；
- **DerivativePlan 退役**：任务卡只含 what（论点/角度/语言/格式），how 归 executor。

## 6. Phase 3：质检节点（kind=verify）

- 单产物质检：分数+理由落 `outputs.score`（P0-3 的家）、persona 保真、术语合规；不合格带反馈打回上游节点 ≤2 次，再败标"待人工"不阻塞；
- 全片质检：跨产物矛盾/撞车；
- verify 是普通 plan_nodes 行：可寻址、可计价、可单独重跑。

## 7. 成本计量

ADR-025 接口层把 usage 直接落 `plan_nodes.cost`（不经过 step-name 过渡——破坏性更新一次到位）；run 级成本 = 节点聚合视图；成本预估 = 历史 `avg(cost) by kind` 求和。

## 8. 验收标准

- [ ] `python scripts/seed_demo.py --force` 全绿：每节点有状态/成本/产出引用；每产物有 `plan_node_id`
- [ ] 步骤清单 UI 读 plan_nodes（output_status JSON 不存在了）
- [ ] clips/derivatives 表不存在；editor 只认 `outputs[type=clip]`；发布元数据走 `publishing`
- [ ] §4.3 三样东西在代码里搜不到
- [ ] 四个 run 创建点全部经 orchestrator（grep 无直接建 WorkflowRun 执行逻辑）
- [ ] `publications.output_id` 单 FK；`ck_pub_target_*` 不存在
- [ ] Phase 1 行为 diff = 0：同一 demo 视频产物集与 main 一致（条数/文案结构/渲染参数）

## 9. Prohibited Behaviors

- **禁止**引入 agent 框架 / LangGraph——图 = 表 + 走图器（ADR-004）；
- **禁止** LLM 决定图拓扑——拓扑由代码按任务书 lowering；
- **禁止**把类型专属字段塞进 outputs 顶级列——回 payload（ADR-030 规则 3）；
- **禁止**为虚拟产物线提前建扩展（variant gate / media provider 接口 / avatar 产物类型）——随 ADR-029 对应行落地；
- **禁止**保留 clips/derivatives 写过桥兼容层；
- **禁止**把导演两步合并回一次调用（ADR-028/AGENT_ARCH §12.2：寿命不同、理解要冻结、可寻址）；
- **禁止**新建 worker 或队列机制——节点认领复用现有 worker + SKIP LOCKED。
