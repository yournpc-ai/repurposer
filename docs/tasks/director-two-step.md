# director-two-step 实施简报——导演两步走（RunPlan Phase 2 主体）

> Status: ✅ 已落地（2026-07-27：`director_understand`/`director_plan` 两节点 + asset-hash 复用 + Storyboard/覆盖问责 + DerivativePlan 退役为槽位；全模块导入/拓扑编译/模板渲染/前端 tsc 验证通过）
> 依据：`docs/AGENT_ARCHITECTURE.md` §12.2（两步走论证）/§12.7（Phase 2 分期）；ADR-028 D4（覆盖问责成为 plan 一等字段）；ROADMAP §1"导演两步走"行
> 无新表 / 无新迁移（output type = String 列 + 应用层注册表，NAMING §5 先例）→ 无需 ADR；新名词登记见 §7（NAMING §8 义务）
> 范围裁决（2026-07-27）：本轮 = 导演拆两次调用 + asset-hash 复用 + DerivativePlan 退役为槽位 + 覆盖问责落库；**选段独立成节点（逐条 clip 的论点→槽位）归 Phase 2b 另行简报**——clips 槽位本轮是聚合槽（一个槽位带 argument_ids + focus），clip_agent 的选段/编剧融合调用不动。

## 0. Context

Phase 1 已落地：导演是单个 `director_plan` 节点，每 run 单趟 LLM 调用，ContentPlan 落 `outputs[type=content_plan]` 行。遗留三宗债：

1. **理解每 run 重算**：换语言 / 加产物 / 定向重生成都把"看懂素材"（最贵的多模态调用）重跑一遍，尽管素材没变。
2. **DerivativePlan 混 what/how 且覆盖无问责**：导演给的 per-output 指引没有论点溯源——哪个论点没被任何产物覆盖、两个产物是否撞同一论点，结构上无从回答（ADR-028 D4 承诺的"plan 一等字段"未兑现）。
3. **理解不可寻址**："素材没变，只重排任务"在单节点上无法表达——两步拆开后，分任务成为独立可重跑节点（plan 级 dispatch 的预备地基，ROADMAP §3 残留项）。

## 1. 已核实的现状事实（读码确认）

- `run_director_plan`（node_runners.py:559）：每 run 调 `content_director_agent.plan(asset_texts, context, asset_media, requested_derivatives)` → `outputs[type=content_plan]`。无任何复用。
- ContentPlan = shared fields（core_thesis/themes/target_audience/key_arguments/quote_candidates/overall_summary）+ `derivatives: list[DerivativePlan]`（focus/cta/quote_candidates/tone_override/count，仅文本产物；导演从不规划 clips——AGENT_ARCH §4.5）。
- executors（post/quotes/carousel/article）：`generate(asset_texts, context, content_plan)`，经 `_find_derivative_plan(content_plan, type)`（skills/base.py:23）取自己的 DerivativePlan，**找不到时回退空 dict**（fallback 纪律保留）。
- clip_agent：同上签名 + asset_media/clip_count/source_words/music_pieces；只用 ContentPlan 的 shared fields。
- 拓扑（orchestrator.py）：full = `preprocess → persona_bootstrap → director_plan → executors`；定向 derivative = `[director_plan(target_type) → X_gen]`；模式② prelude 同 full 前三个。
- executor 读 plan：`_load_content_plan(db, node)`（node_runners.py:421）= `node.inputs[0]` → 该节点 `output_refs[0]` → ContentPlan。
- `outputs.type` = String(50) 无 DB CHECK；`OutputResponse` 的 payload 校验对未知 type **容忍跳过**（schemas.py:1118 `model is None → return value`）→ 退役 content_plan 类型零迁移、旧行不炸。
- 内部类型过滤唯一口：`INTERNAL_OUTPUT_TYPES` + `visible_outputs_stmt`（pipeline/outputs.py）；前端零 content_plan 引用。
- results stepper：`_compute_ui_step`（projects.py:230）按 kind 映射——preprocess/persona_bootstrap→"analyze"，director_plan→"plan"；前端契约 `{key,index,total}` 不变即可。
- RunCard 步骤标签：i18n `stepKinds.*`（en.ts:530 起），需补新 kind。
- 计量：`bind_workflow_step(node.id)` 对任意 kind 生效；复用（无 LLM 调用）自然成本为 0，无需特判。
- persona_bootstrap 产出不进 ContentPlan——它只建/取 Speaker 行；**看懂素材不需要 speaker**（speaker 影响"怎么写"不影响"素材说了什么"）→ 两节点可并行。

## 2. 设计论证（评审沉淀区）

### 2.1 两个新产物类型

| 产物 | type | 寿命 | 输入纯度 |
|---|---|---|---|
| 素材理解 `MaterialUnderstanding` | `material_understanding` | **素材级**——asset hash 匹配即复用，跨 run / 跨语言 / 跨任务书 | 只准吃素材（trimmed texts + media）。**禁注** speaker/tone/instruction/target_language（纯度 = 复用的前提） |
| 分镜表 `Storyboard` | `storyboard` | **请求级**——每 run 必重排 | **自足契约**：只准吃 understanding + 任务书 + speaker/tone/instruction。**禁读原稿** |

### 2.2 Schema（schemas.py 新增，ContentPlan/DerivativePlan 整体退役）

```python
class KeyArgument(BaseModel):      # 论点带 transcript 位置
    id: str                        # "a1"…由 LLM 编，理解内稳定
    text: str
    position: str                  # 自由文本位置标记（原稿无词级时间戳喂给导演，诚实为文本）

class MaterialUnderstanding(BaseModel):
    overall_summary: str
    core_thesis: str
    key_arguments: list[KeyArgument]
    themes: list[str]
    target_audience: str
    quote_candidates: list[str]    # 金句 = 原文逐字（素材语言）

class StoryboardSlot(BaseModel):   # 槽位 = 一个产物的 what；how 归 executor
    slot: str                      # "clips" | "post" | "quotes" | "carousel" | "article"
    focus: str
    argument_ids: list[str]        # 引用 understanding 的论点 id；代码清洗无效 id
    quote_candidates: list[str]    # 从理解的金句池分配
    cta: str | None
    tone_override: str | None
    count: int | None

class CoverageReport(BaseModel):   # 代码推导，LLM 永不产出
    assignments: dict[str, list[str]]   # argument_id → [slot, ...]
    unused_arguments: list[str]
    collisions: list[str]               # 人话注记（一论点进 >1 槽位）

class Storyboard(BaseModel):
    slots: list[StoryboardSlot]
    coverage: CoverageReport = CoverageReport(...)   # runner 算完再落库
```

- 理解用**素材语言**写（金句逐字原文）；分镜表用 **target_language** 写。
- clips 槽位：聚合一个槽（focus + argument_ids + count=任务书 clip_count）；逐 clip 论点→槽位是 Phase 2b 选段节点的事。
- 覆盖报告是**报告不是门禁**：unused/collisions 落库 + 进 spec.summary，不阻塞生成（门禁归 Phase 3 质检节点）。

### 2.3 asset-hash 复用

```python
def _asset_digest(trimmed_texts, assets) -> str:   # sha256
    # texts: 与 prompt 同窗口的 trimmed 文本（截断窗外的变化不使失效——理解的输入本就没变）
    # assets: id|type|file_url|slide_pages 数（file_url 唯一路径 = 内容身份；words meta 非理解输入，不入 hash）
```

- 存 `Output.source_ref = {"asset_hash": hex}`（零新列）。
- 复用判定：项目最新一条 `material_understanding` 行的 hash 匹配 → 节点直接返回 `[旧行 id]`，summary="Reused understanding · {n} arguments"，成本 0（无 LLM 调用，计量自然为空）。
- 失效 = 素材变（增删/重传/转写变）；语言、任务书、speaker 变**不**失效。

### 2.4 拓扑（compile_graph）

```
full:     preprocess(1) → persona_bootstrap(2) ↘
                        → director_understand(3) → director_plan(4) → executors(10+, inputs=[plan])
          （persona 与 understand 并行——互相无依赖；plan 吃两者）
targeted derivative:  [director_understand(1) → director_plan(2, target_type) → X_gen(3)]
mode②:  prelude 同 full 四节点（needs_director 语义不变）
```

- executor 装载改为**按 kind 寻上游**（不再数位置）：`_load_storyboard(node)` → inputs 中 kind=director_plan 的节点；`_load_understanding(node)` → plan 节点 inputs 中 kind=director_understand 的节点。
- stepper 映射：`director_understand` → "analyze"（看懂素材本来就是分析素材）；`director_plan` 仍 → "plan"。前端契约不变。
- stepKinds i18n 补 `director_understand`（en/zh）。

### 2.5 重试/失败语义（不变）

导演两节点维持现状无自动重试（节点失败 → cascade skip → run failed）；executors 的一次自动重试不动。

## 3. 后端改动点

1. **schemas.py**：新增 §2.2 四个模型；退役 `ContentPlan`/`DerivativePlan`；`OUTPUT_PAYLOAD_SCHEMAS` 换 `material_understanding`/`storyboard`；`INTERNAL_OUTPUT_TYPES` = {"content_plan"(legacy 过滤）, "material_understanding", "storyboard"}；`StepKind` 加 `"director_understand"`。
2. **content_director.py**：`plan()` 拆为 `understand(asset_texts, asset_media)` + `plan(understanding, context, task_book)` 两方法。
3. **prompts**：新 `director_understand.j2`；`content_director.j2` 重写并改名 `director_plan.j2`（删旧文件）；post/quotes/carousel/article/clip_agent 五个 j2 换变量（content_plan→understanding，derivative_plan→slot）。
4. **skills/base.py**：`_find_derivative_plan` → `_find_slot(storyboard, slot)`（空 fallback 纪律保留）。
5. **五个 executor + derivative_dispatch**：签名换 `(asset_texts, context, understanding, slot)`。
6. **node_runners.py**：`run_director_understand`（digest+复用+落行）、`run_director_plan`（装 understanding→调 plan→算 coverage→落行+summary）；`_load_content_plan` 删，换 `_load_storyboard`/`_load_understanding`；`run_clips_pipeline`/`run_derivative_gen` 换装载；STEP_RUNNERS 注册。
7. **orchestrator.py**：compile_graph 三种拓扑按 §2.4 更新。
8. **projects.py**：`_compute_ui_step` 加 `director_understand → "analyze"`。
9. **i18n**：en.ts/zh.ts `stepKinds.director_understand`。

## 4. 前端改动点

仅 i18n 两个 key（stepKinds + 无其他——前端零 content_plan 引用已核实）。

## 5. 命名审计（NAMING §5 触发：新名词）

退役：`ContentPlan`（内容计划）、`DerivativePlan`——全库清除不留过桥层（NAMING §1）。
`DerivativeType` 保留（dispatch 枚举仍在用）。

## 6. 分期与验收

单期落地（无行为灰度——生成质量变化即本意）。验收：

1. **首跑**：full run 出现四节点 prelude；understand 落 `material_understanding` 行（source_ref 带 hash）；plan 落 `storyboard` 行（coverage 齐）；五种产物照常生成。
2. **复用**：同素材第二跑（换语言/加产物）→ understand 节点 summary="Reused…"，无新理解行，该节点成本 0。
3. **失效**：改素材（重传/转写变）→ 第三跑 understand 重新执行。
4. **定向重生成**：post 单产物重生成 = 三节点图，understand 复用。
5. **chat 模式②**："去口头禅加音乐"（无 director）与 "写个 post"（有 director prelude 四节点）均编译通过。
6. **覆盖问责**：storyboard payload.coverage.assignments 论点→槽位齐；未用论点列出；plan 节点 summary="Planned {n} slots · {u} unused"。
7. **demo seed** 端到端跑通；stepper/RunCard 显示新 kind 标签。

## 7. 命名登记（随实施进 NAMING §2 词汇表）

| 中文 | 英文 | 定义 | 不是什么 |
|---|---|---|---|
| 素材理解 | `MaterialUnderstanding` / type `material_understanding` | 导演第一步产出：素材级理解（论点带位置/金句/主题/受众），asset-hash 复用 | 不是 ContentPlan（已退役）；不含任务信息 |
| 分镜表 | `Storyboard` / type `storyboard` | 导演第二步产出：请求级派工（槽位+覆盖报告），每 run 重排 | 不是 task board（撞任务书词族）；不读原稿 |
| 槽位 | `StoryboardSlot` | 分镜表一行：一个产物的 what（论点/角度/语言/格式） | how 归 executor |
| 覆盖报告 | `CoverageReport` | 论点→槽位映射 + 未用/撞车，代码推导 | 不是门禁（归 Phase 3 质检） |

判例（拟 N-17）：ContentPlan 拆分为素材理解 + 分镜表（导演两步走）；DerivativePlan 退役为槽位。"两个 plan 各司其职"注记随之改写（RunPlan 成唯一 plan；创作层是理解+分镜，不再是 plan）。

## 8. 禁止行为（Prohibited Behaviors）

1. **禁** storyboard prompt 读原稿——自足契约：只准吃 understanding + 任务书 + speaker/tone/instruction。
2. **禁** understanding prompt 注入 speaker/tone/instruction/target_language/event_name——素材级纯度是跨语言/跨请求复用的前提。
3. **禁**为复用加新列/新表/项目级缓存字段——判定只读 outputs 行 + `source_ref.asset_hash`。
4. **禁** ContentPlan/DerivativePlan 留过桥层或兼容别名——退役即全库清除（含 prompt 变量名）。
5. **禁** LLM 产出 coverage——代码从 argument_ids 推导；LLM 只标 id，无效 id 代码清洗。
6. **禁**本轮拆 clip 选段/编剧（Phase 2b 另行简报）；clips 槽位 = 聚合槽。
7. **禁** coverage 阻塞生成——报告不是门禁。
8. **禁** stepper 前端契约变更（`{key,index,total}` 不动，只加 kind 映射与 i18n key）。
