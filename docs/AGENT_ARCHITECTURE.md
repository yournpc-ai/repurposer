# Repurposer Agent Architecture

> Status: implemented on main
> Last updated: 2026-07-16
> **2026-07-22 架构升级**：本文的 4-layer 结构将演进到 RunPlan（施工图）架构——概念基线、目标链路、导演两步走、质检节点与分期见 §12。

## 1. Overview

Repurposer turns a single source (talk video, audio, slides, or transcript) into a set of reusable knowledge assets: vertical clips, social posts, quote cards, carousels, and articles.

The backend generation pipeline is organized as a **4-layer agent architecture**:

```
┌─────────────────────────────────────────────┐
│ Layer 1: GenerationContext                  │
│ (shared speaker / brand / tone / language)  │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│ Layer 2: Content Director                   │
│ (produces ContentPlan from source texts)    │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│ Layer 3: Agent Executors                    │
│ (clip / post / quotes / carousel /          │
│  article)                                   │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│ Layer 4: Consistency Reviser                │
│ (reserved for future cross-output review)   │
└─────────────────────────────────────────────┘
```

> **Naming caution**: `app/agents/reviser.py` is **not** Layer 4 — it is the single-clip metadata revision agent invoked by targeted revision (see §9). Layer 4 (cross-output consistency review) is unimplemented as of 2026-07; there is no `consistency` code in `app/`.

This design guarantees that every output is derived from the same **content plan** and **generation context**, instead of each agent independently re-analyzing the source material.

## 2. Goals

- **Consistency**: clips, posts, quote cards, etc. should reinforce the same core thesis and brand voice.
- **Single source of truth**: speaker memory, tone, and user instruction are assembled once and shared.
- **Extensibility**: adding a new derivative type requires only a new executor agent and one registry entry.
- **Parallel execution**: independent derivative agents run concurrently via `asyncio.gather`.
- **Resilience**: a single output failure does not fail the whole run; it is retried once and then surfaced for manual retry.

## 3. Layer 1: GenerationContext

`GenerationContext` is an immutable value object built at the start of every full generation run. It contains everything an agent needs to know about *who* is speaking, *to whom*, *in what voice*, and *with what constraints*.

```python
class GenerationContext(BaseModel):
    speaker: SpeakerContext | None
    event_name: str | None
    tone_settings: ToneSettings | None
    target_language: str
    instruction: str | None
    brand_music_id: str | None
```

It is constructed in `app/services/generation.py` from the resolved `Speaker`, selected `BrandTemplate`, project metadata, and the user's generation request.

## 4. Layer 2: Content Director

The `ContentDirectorAgent` (`app/agents/content_director.py`) performs one analysis pass over the source texts and media inputs and produces a `ContentPlan`.

### 4.1 ContentPlan

```python
class ContentPlan(BaseModel):
    core_thesis: str
    themes: list[str]
    target_audience: str
    key_arguments: list[str]
    derivatives: list[DerivativePlan]
    quote_candidates: list[str]
    overall_summary: str

class DerivativePlan(BaseModel):
    derivative_type: DerivativeType
    focus: str
    cta: str | None
    quote_candidates: list[str]
    tone_override: str | None
    count: int | None
```

### 4.2 Why a separate director?

Previously, the clip planner (`planner.py`) performed a rich analysis (`overall_summary`, `themes`, `target_audience`) but threw it away after clips were generated. Derivative agents then re-analyzed the same transcript independently, often arriving at different theses.

The director centralizes analysis so that every downstream agent works from the same interpretation.

### 4.3 Persistent ContentPlan

The generated `ContentPlan` is persisted to `Project.content_plan` (JSON column) on first generation. Subsequent full regenerations reuse it instead of calling the director again, enabling faster iteration. Future work may invalidate the cache based on a materials hash.

### 4.4 Prompt

`app/prompts/content_director.j2` receives:
- `asset_texts` and optional `asset_media`
- `context` (`GenerationContext`)
- `requested_derivatives` (the output types the user asked for)

It outputs JSON matching `ContentPlan`.

### 4.5 Director output constraints

`ContentPlan.derivatives` must only contain **text derivative** plans. Valid `derivative_type` values are:

- `post`
- `quotes`
- `carousel`
- `article`

The director must **never** emit `clips`, `short_clips`, `video`, or any other non-text type. Clips are planned separately by the `ClipAgent` because they require word-level timestamp alignment and segment-level constraints (e.g., minimum duration) that do not apply to text outputs. If the user did not request any text derivatives, the director returns an empty `derivatives` array.

## 5. Layer 3: Agent Executors

All content executors share the same interface:

```python
async def generate(
    self,
    asset_texts: list[str],
    context: GenerationContext,
    content_plan: ContentPlan,
) -> BaseModel:
    ...
```

Each executor extracts its own guidance from `content_plan.derivatives` by matching `derivative_type`.

### 5.1 Agents

| Domain | File | Class | Output schema | Notes |
|--------|------|-------|---------------|-------|
| Clip | `app/agents/clip_agent.py` | `ClipAgent` | `ClipPlans` | Renamed from `ContentPlannerAgent` / `planner.py` |
| Post | `app/agents/post.py` | `PostAgent` | `Post` | |
| Quotes | `app/agents/quotes.py` | `QuotesAgent` | `Quotes` | |
| Carousel | `app/agents/carousel.py` | `CarouselAgent` | `CarouselResponse` | |
| Article | `app/agents/article.py` | `ArticleAgent` | `Article` | |

### 5.2 Clip agent constraints

`ClipAgent` plans video segments from the source transcript's word-level timestamps. Every planned clip must satisfy:

- `start_seconds < end_seconds`.
- **Minimum duration of 5 seconds**; if the selected words produce a shorter segment, the agent extends the selection by including surrounding words until the duration is at least 5 seconds.
- No overlap between consecutive clips; each subsequent clip starts after the previous one ends.
- `duration_seconds` is clamped to `5–120` seconds.
- `caption_enabled` is tri-state (`bool | None`): the agent sets `false` when the source video already has hard-coded subtitles; when the agent omits a decision (`None`), the brand template's `captionEnabled` default applies.

These constraints are enforced in `app/prompts/clip_agent.j2` and validated by `ClipPlans` before `Clip` rows are created.

### 5.3 Prompt templates

Each prompt template receives `asset_texts`, `context`, and `content_plan`:

- `app/prompts/clip_agent.j2`
- `app/prompts/post.j2`
- `app/prompts/quotes.j2`
- `app/prompts/carousel.j2`
- `app/prompts/article.j2`

Prompts render:
- Speaker identity and style memory from `context.speaker`
- Tone settings and user instruction from `context`
- Brand music default from `context.brand_music_id`
- Core thesis, themes, and target audience from `content_plan`
- Per-output focus and CTA from the matching `DerivativePlan`

## 6. Dispatch

`app/services/derivative_dispatch.py` holds the registry of derivative executors:

```python
_AGENTS: dict[DerivativeType, BaseDerivativeAgent] = {
    DerivativeType.POST: post_agent,
    DerivativeType.QUOTES: quotes_agent,
    DerivativeType.CAROUSEL: carousel_agent,
    DerivativeType.ARTICLE: article_agent,
}

async def generate_derivative(
    derivative_type: DerivativeType,
    asset_texts: list[str],
    context: GenerationContext,
    content_plan: ContentPlan,
) -> dict:
    agent = _AGENTS[derivative_type]
    result = await agent.generate(asset_texts, context, content_plan)
    return validate_derivative_content(derivative_type, result.model_dump())
```

This file was previously `derivative_generation.py` and contained per-type parameter normalization. With the unified interface, its only remaining responsibility is **dispatch** plus content validation.

## 7. Orchestration

`app/services/generation.py` implements the top-level orchestration for a full generation run.

### 7.1 Flow

1. Collect source texts (`collect_asset_texts`) and media inputs (`collect_asset_media`).
2. Resolve speaker (auto-create default memory if none selected), brand template, and tone settings.
3. Build `GenerationContext`.
4. Map requested `outputs` to `DerivativeType`s.
5. Call `content_director_agent.plan(...)` → `ContentPlan`, then persist to `Project.content_plan`.
6. Delete prior outputs for the requested types.
7. If clips requested:
   - Call `clip_agent.generate(...)` → `ClipPlans`
   - Build `ClipSpec` for each plan and persist `Clip` rows.
8. Run all requested derivatives concurrently with `asyncio.gather`:
   - Call `generate_derivative(...)`
   - Persist `Derivative` rows.
9. Mark `WorkflowRun` completed (or failed if every output failed) and project status `REVIEW`.

### 7.2 Per-output status and retry

`run.context["output_status"]` tracks each output independently:

```json
{
  "clips": {"status": "completed", "progress": 100, "error": null, "stage": null},
  "post": {"status": "failed", "progress": 0, "error": "...", "stage": null}
}
```

Each entry carries a machine-readable `stage` for the loading UI — coarse but real sub-stage markers: `selecting_segments` / `building_specs` (clips), `writing_copy` (all text derivatives), `generating_image` (quotes). `progress` moves at those same code points (e.g. clips: 60 → 90 → 100, calibrated so the slow LLM phases sit in the upper half of the bar), and `run.progress` is the mean of per-output progress values.

The results page does **not** derive its stepper from these raw values. `GET /projects/{id}/results` returns a computed `ui_step` (`{key, index, total}`, see `_compute_ui_step` in `app/routers/projects.py`): the step list is `transcribing → queued → analyze → plan → prepare` plus per-output steps (`selecting_segments`/`building_specs` for clips, one shared `writing_copy` for the concurrent text derivatives, `generating_image` for quotes) and ends with `ready_to_render`, which holds at 100% while clips wait for the render worker. The frontend renders `percent = (index + 1) / total` — equal increments per step — and interpolates between the 2.5 s polls; `ui_step = null` (run failed, or everything including renders settled) closes the dialog.

Context updates are persisted with `flag_modified` — plain SQLAlchemy JSON columns do not detect in-place mutation, and without it per-output statuses never reach the database.

Each output agent call is wrapped in `try/except` with **one automatic retry**. If it still fails, the error is recorded and the run continues. A run that fails mid-flight marks every non-terminal output as `failed` so consumers can settle. The frontend shows a manual retry button per failed output; retrying triggers a new `WorkflowRun` with only that output.

### 7.3 Stepper stages

During the planning phase, `WorkflowRun.current_step` uses three discrete values so the Result page can render a real stepper:

- `"analyze"` — collecting source texts / media, resolving speaker and brand
- `"plan"` — running the Content Director
- `"prepare"` — plan persisted, clearing old outputs, about to generate

After planning, `current_step` switches to the active output key (`clips`, `post`, `quotes`, `carousel`, `article`) and finally `"done"`.

### 7.4 Preserved behavior

- Idempotency: prior outputs for requested types are still deleted before regeneration.
- Targeted revision (`_run_targeted_revision`) bypasses the director and uses a minimal plan.
- The orchestrator never raises; failures land on the `WorkflowRun`.

## 8. API and Data Stability

| Surface | Change |
|---------|--------|
| `POST /api/v1/projects/{id}/generate` | `outputs` now includes `carousel`; `clips` is no longer forced; default `clip_count` is 5 |
| `GET /api/v1/projects/{id}/results` | Returns `latest_job.context.output_status` for per-output progress |
| `Project` response | Includes `content_plan` |
| `WorkflowRun.context` | Includes `output_status`, `outputs`, `clip_count` |
| Speaker schema | Flattened: `persona` JSON replaced with direct columns (already landed) |

## 9. Non-content agents

The following agents are **not** part of the 4-layer executor pipeline and remain unchanged:

- `app/agents/persona.py` — extracts speaker style and content memory from source texts.
- `app/agents/reviser.py` — revises a single clip script from human feedback.
- `app/agents/intent.py` — infers generation intent (`outputs`, `clip_count`, `language`, `tone`) from the user's prompt before generation. `clips` is only suggested when a media source file (video/audio/image) is attached; text-only input falls back to post/quotes/article.
- `app/agents/caption_translate.py` — translates caption lines.

## 10. Future work

### 10.1 Consistency Reviser (Layer 4)

A future agent can review all generated outputs against the `ContentPlan` and `GenerationContext`, flag inconsistencies (e.g., a quote card contradicts the post's thesis), and trigger targeted revisions.

### 10.2 ContentPlan invalidation

Currently `Project.content_plan` is reused unconditionally. Future work should invalidate/rebuild when source materials change significantly, e.g. via a hash of asset texts/media.

## 11. Critical files

- `app/models/schemas.py` — `GenerationContext`, `ContentPlan`, `DerivativePlan`, `InferredIntent`, RunPlan 词汇（`PlanNodeKind`/`OutputType`/`OUTPUT_PAYLOAD_SCHEMAS`）
- `app/agents/content_director.py` — director agent
- `app/prompts/content_director.j2` — director prompt
- `app/agents/clip_agent.py` — clip agent
- `app/prompts/clip_agent.j2` — clip agent prompt
- `app/agents/post.py`, `quotes.py`, `carousel.py`, `article.py` — derivative executors
- `app/prompts/post.j2`, `quotes.j2`, `carousel.j2`, `article.j2` — derivative prompts
- `app/services/derivative_dispatch.py` — thin dispatcher registry
- `app/services/orchestrator.py` — RunPlan 物化/走图/执行/收尾（`create_run` 是 WorkflowRun 唯一出生地）
- `app/services/node_runners.py` — 节点执行器注册表（`NODE_RUNNERS`，generation 逻辑平移）
- `app/services/metering.py` — 逐节点计量（usage → `plan_nodes.cost`，ADR-025）
- `app/agents/intent.py` — intent recognition
- `app/routers/outputs.py` — 统一产物 API（含单产物重生成）

> 已退役（Phase 1 破坏性删除）：`services/generation.py`、`routers/clips.py`、`routers/derivatives.py`。

## 12. 施工图视图（RunPlan 架构，2026-07-22 定型）

> 本节是 generation 编排演进的**概念基线**。决策：ADR-028（RunPlan 持久化）/ ADR-029（双链并列）/ ADR-030（产物统一）；实施简报：`docs/tasks/runplan-persistence.md`。老四层概念全部保留，换了更准的形态。

### 12.1 概念表（八个，没有第九个）

| 概念 | 一句话 | 老概念对应 |
|---|---|---|
| **任务书** | 意图归一：outputs×语言×数量×预算+instruction | run.context 参数 / infer-intent / chat 指令 |
| **预处理** | ASR 词级时间戳 + 文本提取（机器，无 LLM） | asset_processing |
| **导演** | 两步走：看懂素材（可复用）→ 分任务（分镜表，每 run 重排） | Content Director（单趟 → 两次调用） |
| **班组** | executors：选段 / 编剧 / 文案 / 配音 / 渲染——每工种一个节点 | Agent Executors |
| **质检** | 单产物（分数落库 / 保真 / 合规，打回 ≤2 次）+ 全片（跨产物撞车） | Layer 4（未实现）的新形态 |
| **施工图** | plan_nodes：DAG 内核，计划+账簿一体 | `workflow_runs.context` 的替代 |
| **产物** | outputs 统一表；clip = 带时间轴+渲染的那一类 | clips / derivatives（ADR-030） |
| **分发** | 缝 = 产物表，零变化 | Distribution |

### 12.2 导演两步走（两次 LLM 调用）

- **看懂素材**：产出素材理解（论点带 transcript 位置 / 金句 / 主题 / 受众）。**自足契约**：产物必须足以支撑分任务，分任务不再读原稿。**asset hash 失效**：素材变才重算（§10.2 的正式实现，替代 §4.3 的盲目复用）。
- **分任务**：吃素材理解 + 任务书 → 分镜表（论点→槽位 + 任务卡 + 未用/撞车报告），每次 run 必重排。
- **为什么两次**：寿命不同（理解=素材级，任务=请求级）；理解要冻结，fortnight 整包才一致；可寻址（"重排任务"只重跑第二步）。首次成本差可忽略（理解 ≪ 原稿）。
- **DerivativePlan 退役**：任务卡只含 what（论点/角度/语言/格式），how 归 executor——伪造 plan 的代码路径（`generation.py:569-585`）整体删除。

### 12.3 质检节点（Layer 4 的答案）

Layer 4 不再是一个"层"，是图里的一种节点（kind=verify）：**单产物质检**（分数+理由落库 = P0-3 的家、persona 保真、术语合规；不合格带反馈打回上游 ≤2 次，再败标"待人工"不阻塞）+ **全片质检**（跨产物矛盾/撞车）。可寻址、可计价、可单独重跑——失败只打回不合格分支，不搞全局复审。

### 12.4 流程图（一次 fortnight run）

```
预处理 → 任务书 → 导演·看懂素材 → 导演·分任务
  → 班组（选段→编剧→渲染 / 文案×N / 配音·音乐）
  → 质检（单产物 → 全片）
  → 产物（outputs）→ 分发（零变化）
```

每一步 = 施工图上的一个节点：pending 可估价（成本预览）、running 可看状态、done 有账可查、不满意可单独重跑（子图词汇：只跑此节点 / 从这里跑 / 跑到这里）。

### 12.5 班底与机械

- **会思考（LLM 班底）**：意图识别 / 导演 / 班组 / 质检 / persona / chat 意图解析
- **不会思考（施工机械）**：processor / orchestrator（物化图+走图）/ worker（认领节点）/ Remotion / 队列 / 存储 / 分发状态机

### 12.6 现状五宗罪（2026-07-22 代码核实；Phase 1 已全部清除）

1. ~~ContentPlan = project 上 JSON blob，盲目复用无失效~~ → 内部 `outputs[type=content_plan]` 行，director_plan 节点产物（每 run 重排；asset-hash 复用是 Phase 2）
2. ~~DerivativePlan 混 what/how，定向重生成靠伪造 plan~~ → 定向重生成 = 小拓扑 `[director_plan → X_gen(target_id)]`，伪造 plan 路径整体删除
3. ~~output_status JSON + 进程内 asyncio 锁，跨 worker 失效~~ → plan_nodes 行级状态，步骤清单改读节点
4. ~~speaker 自动创建埋在 run_generation~~ → `persona_bootstrap` 节点
5. ~~scope if-else 双形态~~ → 同机制小拓扑图（hook/clip→`[script]`，render→`[render]`）

### 12.7 分期（防范围蠕变）

| 期 | 内容 | 行为变化 | 状态 |
|---|---|---|---|
| Phase 1 | 隐式图原样持久化 + outputs 统一 + 节点级血统 + 逐节点计量 | 零 | ✅ 已落地（2026-07-22；实施计划 `docs/tasks/runplan-phase1-implementation.md`） |
| Phase 2 | 导演两步走 + DerivativePlan 退役 + persona_bootstrap/选段独立成节点 | 生成质量提升 | 📋 |
| Phase 3 | 质检节点（单产物 + 全片） | P0-3 兑现 | 📋 |
