# Repurposer Agent Architecture

> Status: implemented on main
> Last updated: 2026-07-14

## 1. Overview

Repurposer turns a single source (talk video, audio, slides, or transcript) into a set of reusable knowledge assets: vertical clips, LinkedIn posts, quote cards, carousels, summaries, and blog posts.

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
│ (clip / linkedin / quote / carousel /       │
│  summary / blog)                            │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│ Layer 4: Consistency Reviser                │
│ (reserved for future cross-output review)   │
└─────────────────────────────────────────────┘
```

This design guarantees that every output is derived from the same **content plan** and **generation context**, instead of each agent independently re-analyzing the source material.

## 2. Goals

- **Consistency**: clips, LinkedIn posts, quote cards, etc. should reinforce the same core thesis and brand voice.
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
| LinkedIn | `app/agents/linkedin.py` | `LinkedInAgent` | `LinkedInPost` | |
| Quote | `app/agents/quote_agent.py` | `QuoteAgent` | `QuoteCardsResponse` | Renamed from `quote_card.py` |
| Carousel | `app/agents/carousel.py` | `CarouselAgent` | `CarouselResponse` | |
| Summary | `app/agents/summary.py` | `SummaryAgent` | `Summary` | |
| Blog | `app/agents/blog.py` | `BlogAgent` | `BlogPost` | |

### 5.2 Prompt templates

Each prompt template receives `asset_texts`, `context`, and `content_plan`:

- `app/prompts/clip_agent.j2`
- `app/prompts/linkedin.j2`
- `app/prompts/quote_agent.j2`
- `app/prompts/carousel.j2`
- `app/prompts/summary.j2`
- `app/prompts/blog.j2`

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
    DerivativeType.LINKEDIN_POST: linkedin_agent,
    DerivativeType.QUOTE_CARD: quote_agent,
    DerivativeType.CAROUSEL: carousel_agent,
    DerivativeType.SUMMARY: summary_agent,
    DerivativeType.BLOG: blog_agent,
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
  "clips": {"status": "completed", "progress": 100, "error": null},
  "linkedin": {"status": "failed", "progress": 0, "error": "..."}
}
```

Each output agent call is wrapped in `try/except` with **one automatic retry**. If it still fails, the error is recorded and the run continues. The frontend shows a manual retry button per failed output; retrying triggers a new `WorkflowRun` with only that output.

### 7.3 Stepper stages

During the planning phase, `WorkflowRun.current_step` uses three discrete values so the Result page can render a real stepper:

- `"analyze"` — collecting source texts / media, resolving speaker and brand
- `"plan"` — running the Content Director
- `"prepare"` — plan persisted, clearing old outputs, about to generate

After planning, `current_step` switches to the active output key (`clips`, `linkedin`, `quote_cards`, `carousel`, `summary`, `blog`) and finally `"done"`.

### 7.4 Preserved behavior

- Idempotency: prior outputs for requested types are still deleted before regeneration.
- Targeted revision (`_run_targeted_revision`) bypasses the director and uses a minimal plan.
- The orchestrator never raises; failures land on the `WorkflowRun`.

## 8. API and Data Stability

| Surface | Change |
|---------|--------|
| `POST /api/v1/projects/{id}/generate` | `outputs` now includes `carousel`/`blog`; `clips` is no longer forced; default `clip_count` is 5 |
| `GET /api/v1/projects/{id}/results` | Returns `latest_job.context.output_status` for per-output progress |
| `Project` response | Includes `content_plan` |
| `WorkflowRun.context` | Includes `output_status`, `outputs`, `clip_count` |
| Speaker schema | Flattened: `persona` JSON replaced with direct columns (already landed) |

## 9. Non-content agents

The following agents are **not** part of the 4-layer executor pipeline and remain unchanged:

- `app/agents/persona.py` — extracts speaker style and content memory from source texts.
- `app/agents/reviser.py` — revises a single clip script from human feedback.
- `app/agents/intent.py` — infers generation intent (`outputs`, `clip_count`, `language`, `tone`) from the user's prompt before generation.
- `app/agents/caption_translate.py` — translates caption lines.

## 10. Future work

### 10.1 Consistency Reviser (Layer 4)

A future agent can review all generated outputs against the `ContentPlan` and `GenerationContext`, flag inconsistencies (e.g., a quote card contradicts the LinkedIn post's thesis), and trigger targeted revisions.

### 10.2 ContentPlan invalidation

Currently `Project.content_plan` is reused unconditionally. Future work should invalidate/rebuild when source materials change significantly, e.g. via a hash of asset texts/media.

## 11. Critical files

- `app/models/schemas.py` — `GenerationContext`, `ContentPlan`, `DerivativePlan`, `InferredIntent`
- `app/agents/content_director.py` — director agent
- `app/prompts/content_director.j2` — director prompt
- `app/agents/clip_agent.py` — clip agent
- `app/prompts/clip_agent.j2` — clip agent prompt
- `app/agents/linkedin.py`, `quote_agent.py`, `carousel.py`, `summary.py`, `blog.py` — derivative executors
- `app/prompts/linkedin.j2`, `quote_agent.j2`, `carousel.j2`, `summary.j2`, `blog.j2` — derivative prompts
- `app/services/derivative_dispatch.py` — thin dispatcher registry
- `app/services/generation.py` — orchestration
- `app/agents/intent.py` — intent recognition
- `app/routers/derivatives.py` — single-derivative regeneration
