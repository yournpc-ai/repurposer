# Repurposer Architecture Design

> Status: Active（现状架构的唯一事实源；模块边界与表归属见 `MODULE_ARCHITECTURE.md`，排期见 `ROADMAP.md`）
> Last updated: 2026-07-20

## 1. Design Principles

1. **Simplicity First**: P0 does not introduce complex frameworks; agent workflows are hand-rolled in pure Python + FastAPI
2. **Modular Decoupling**: Media processing, intelligent generation, and rendering layers can be independently replaced
3. **Human-in-the-Loop**: Every generation step supports user feedback and partial regeneration
4. **Single-Model Strategy**: The core intelligence layer uses only MiniMax M3

## 2. Abstract Architecture

```
┌─────────────────────────────────────────────┐
│  Frontend: TanStack Start                    │
│  Upload media / optionally or auto-create Speaker memory / review results / export │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Backend: FastAPI                            │
│  REST API / file upload / task scheduling / state management │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Agent Workflow Orchestrator                 │
│  Defines step order, state transitions, and human pause points │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Agent Steps (pure Python functions)         │
│  memory / content_director / clip /          │
│  post / quotes / carousel / article /        │
│  reviser / caption_translate                 │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  MiniMax M3 Client                           │
│  Unified wrapper for calls, JSON parsing, retries, and error handling │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Media Processing Layer                      │
│  Speech recognition / video frame extraction / document parsing / image processing │
│  Voice cloning / speech synthesis / video rendering / graphic generation │
│  Music resources                             │
└─────────────────────────────────────────────┘
```

## 3. Agent Workflow

### 3.1 Core Agents

| Agent | Input | Output | Description |
|:---|:---|:---|:---|
| `persona` | Task materials + speaker name/title | `SpeakerContext` fields | Extract speaker style and content memory |
| `content_director` | Materials + `GenerationContext` | `ContentPlan` | Unified analysis: core thesis, themes, audience, per-output plans |
| `clip` | Materials + `GenerationContext` + `ContentPlan` | `ClipPlans` | Select segments and write vertical clip scripts |
| `post` | Materials + `GenerationContext` + `ContentPlan` | `Post` | Social post |
| `quotes` | Materials + `GenerationContext` + `ContentPlan` | `Quotes` | Quote card copy |
| `carousel` | Materials + `GenerationContext` + `ContentPlan` | `CarouselResponse` | Social carousel (cover → points → CTA) |
| `article` | Materials + `GenerationContext` + `ContentPlan` | `Article` | Long-form article |
| `reviser` | Clip metadata + feedback + `SpeakerContext` | `ClipRevision` | Revised clip metadata (hook, duration, titles, music) |
| `caption_translate` | Word-level captions + target_language | `CaptionTranslation` | Caption language swap |

> **Intent Channel**: `GenerateRequest.instruction` (homepage prompt) is folded into `GenerationContext` and passed to the Content Director and every derivative agent as "the highest-priority directive for this run."
> **Vision/Voice**: `IMAGE` assets are processed through M3 multimodal (`services/vision.py`) to extract key points into materials; `POST /clips/{id}/dub` uses MiniMax voice_clone + T2A (`services/voice.py`) for voice-cloned dubbing.

### 3.2 Generation Flow

```
User uploads media + inputs prompt
    ↓
Preprocessing (transcription / parsing / image processing)
    ↓
Resolve Speaker (auto-create default memory if none selected)
    ↓
Resolve Brand template
    ↓
Content Director Agent → unified ContentPlan
    ↓
Clip Agent → segment selection + scripts
    ↓
Derivative Agents (Post / Quotes / Carousel / Article) → outputs
    ↓
Save results, await user review
    ↓
User feedback → Reviser Agent → partial regeneration
```

### 3.3 Human Feedback Loop

User feedback must be structured:

```python
class FeedbackRequest(BaseModel):
    clip_id: str
    scope: Literal["hook", "full_script", "tone", "translation"]
    reason: Literal[
        "hook_not_catchy",
        "not_like_speaker",
        "too_complex",
        "too_simple",
        "factually_inaccurate",
        "different_expression",
        "other"
    ]
    detail: Optional[str] = None
```

## 4. Data Flow

The main entry point is the homepage input box, not the project list page. A complete task's data flow is as follows:

```
User on the homepage input box:
  ├── Drag in files (video/audio/transcript/slides/images) or paste text
  ├── Input output intent prompt
  ├── Select Speaker (optional)
  ├── Select Brand template (optional)
  ├── Select Tone and Outputs
  └── Click generate
            ↓
Frontend makes three consecutive API calls:
  POST /api/v1/projects              → Create Project
  POST /api/v1/projects/{id}/assets  → Upload Asset (file or prompt text)
  POST /api/v1/projects/{id}/generate → Create WorkflowRun, enter generation queue
                                            (also creates a project-scoped ChatSession and stores the prompt)
            ↓
Worker claims WorkflowRun and calls Agents in order:
  content_director → clip → post / quotes / carousel / article
            ↓
Generate clip-spec (including brand, music) and save to Clip.render_spec
            ↓
WorkflowRun status updated to completed
            ↓
TanStack Start frontend: user enters project detail page to review / edit / export
            ↓
Render trigger → Clip.render_status=PENDING → worker calls Remotion rendering service
            ↓
Export MP4 + SRT
```

**Note**: After upload, an `Asset(processing_status=PENDING)` is created immediately; the worker claims and processes it in the background (ASR / text extraction / vision). The generation runtime reads the Asset's `extracted_text` / `transcript` / `meta["words"]` directly. A generation run created while assets are still processing simply stays `pending`: the worker skips runs whose project has unprocessed assets (deferred claim), so `/generate` can be called immediately after upload — no client-side wait for ASR/extraction is needed.

## 5. Code Structure

```
apps/api/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # Configuration management
│   ├── dependencies.py      # Dependency injection
│   ├── worker.py            # Standalone worker process entry point
│   ├── routers/             # API routes
│   │   ├── speakers.py
│   │   ├── projects.py      # Includes generation, export, jobs, clips, derivatives, results
│   │   ├── assets.py
│   │   ├── clips.py         # Review, render trigger, caption translation, dub, regenerate, revise
│   │   ├── derivatives.py
│   │   ├── files.py         # File streaming: ownership check → 307 redirect (or ?proxy=1 byte streaming)
│   │   ├── brand_templates.py
│   │   ├── chat.py          # Project/asset-scoped chat sessions and intent dispatch
│   │   └── library.py       # Cross-project output library
│   ├── services/            # Business logic
│   │   ├── jobs.py          # Queue claiming
│   │   ├── asset_processing.py   # Processing dispatch: ASR / text extraction / slide page rendering / image vision
│   │   ├── generation.py    # Generation flow orchestration
│   │   ├── rendering.py     # Calls Remotion rendering service
│   │   ├── clip_spec.py     # clip-spec construction
│   │   ├── brand.py         # Brand template → ClipBrand/ClipMusic + default seeds
│   │   ├── extraction.py    # Text/PDF extraction + PyMuPDF per-page image rendering
│   │   ├── vision.py        # M3 vision: image → key point text
│   │   ├── voice.py         # Voice cloning + T2A synthesis + video audio track extraction
│   │   ├── caption_translate.py  # Caption track translation
│   │   ├── chat.py          # Chat session logic and intent parsing/dispatch
│   │   ├── project_context.py    # Project ownership helpers
│   │   ├── storage.py       # Storage seam
│   │   └── asr.py           # faster-whisper
│   ├── models/              # Database models + Pydantic schemas
│   │   ├── database.py
│   │   ├── schemas.py
│   │   └── tables.py
│   ├── agents/              # Agent steps
│   │   ├── base.py          # Shared MiniMax agent base + derivative plan helper
│   │   ├── persona.py
│   │   ├── content_director.py
│   │   ├── clip_agent.py
│   │   ├── reviser.py
│   │   ├── post.py
│   │   ├── quotes.py
│   │   ├── carousel.py
│   │   ├── article.py
│   │   ├── intent.py        # /infer-intent helper
│   │   └── caption_translate.py
│   ├── prompts/             # Jinja2 templates
│   └── clients/
│       └── minimax.py       # MiniMax M3 wrapper
├── migrations/              # Alembic migration scripts
├── pyproject.toml
└── Dockerfile

apps/web/                    # TanStack Start frontend
apps/render/                 # Remotion rendering service (Node)
packages/clip/               # Shared <Clip> + clip-spec TS types
pnpm-workspace.yaml          # web/render/clip
```

## 6. State Management

### 6.1 Workflow Run

Records the full lifecycle of a generation task:

```python
class WorkflowRun(BaseModel):
    id: UUID
    project_id: UUID
    status: Literal[
        "pending", "running", "waiting_human",
        "completed", "failed"
    ]
    current_step: str
    context: dict
    created_at: datetime
    updated_at: datetime
```

### 6.2 Asset Status

`Asset` has its own processing state machine:

```python
class AssetStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
```

- After upload, the API immediately returns `PENDING`; the worker claims and processes it.
- `processing_error` stores the failure reason; the frontend can retry.

### 6.3 Clip Render Status

```python
class RenderStatus(StrEnum):
    PENDING = "pending"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"
```

- `Clip.render_status` is the worker's third claiming source.
- `Clip.render_spec` stores the clip-spec contract; `video_url` / `srt_url` store the final output artifacts.

## 7. Key Design Decisions

- **No Turborepo/Nx/Pants**: Frontend and backend are managed independently; a simple directory structure suffices
- **Hand-Rolled Agents**: Single model, fixed workflow; framework abstraction adds little value
- **Pydantic Strong Typing**: All agent inputs and outputs use Pydantic models
- **Structured Feedback**: User feedback must select a reason, not just free text
- **Version History**: Every regeneration currently overwrites the existing clip/derivative. Full version history (save old versions, comparison, rollback) is a future feature.

## 8. Extension Points

| Future Requirement | Extension Approach |
|:---|:---|
| Model swap / EU-hosted model | Thin provider interface per ADR-025 (`generate_structured` / `chat_with_tools`); MiniMax stays the default and only configured adapter |
| More languages | Add `translator.py` to support additional target languages |
| Complex workflow | P2 evaluate LangGraph or Pydantic AI |
| Team collaboration | Add `organizations` / `members` tables and permission middleware |
| Direct social publishing | Add `routers/publish.py` to call platform APIs |

## 9. Task Queue (Implemented, ADR-017)

Long-running tasks (ASR, video rendering, generation) do not run in the API process; they are handled by a standalone worker process. **Postgres is used as the queue; Redis is not introduced.**

```
┌──────────┐  upload/generate creates pending row  ┌─────────────┐
│ FastAPI   │ ───────────────────────────────────► │ PostgreSQL   │
│ (API process) │                            │ Asset/Run row │
└──────────┘                            └──────┬──────┘
                                               │ FOR UPDATE SKIP LOCKED claiming
┌──────────────────────┐                       ▼
│ worker process        │ ◄─────────────────────┘
│ python -m app.worker  │  process_asset / run_generation
│ physically isolated from API │  failure writes to *_error, loop doesn't crash
└──────────────────────┘
```

- `app/services/jobs.py`: `claim_pending_*` (atomic claiming) + `reap_stale` (startup reset of orphaned tasks). `claim_pending_run` additionally skips runs whose project still has `pending`/`processing` assets, so generation never starts before its source material is ready.
- `app/services/asset_processing.py`: Processor dispatch by `AssetType` — **the future hook-in point for ASR/OCR/video rendering**.
- When horizontal scaling is needed, replace claiming with arq/Celery + Redis; callers remain unchanged.

## 10. Video Editing and Rendering Architecture (ADR-016, see VIDEO_EDITOR.md)

"Vertical short final output + editable" is the MVP main flow. Architecture core = **a declarative `clip-spec(JSON)` contract is pinned down; the renderer is a replaceable black box behind the contract.**

```
clip-spec(JSON)  ← permanent contract (renderer-agnostic)
     │
     ├──► Preview: Remotion <Player> (real-time browser rendering, editor canvas)
     └──► Export: Remotion rendering service (Node, headless Chrome + internal FFmpeg)
              └─ Python queue (§9) triggers via HTTP → MP4 + SRT
```

- **First renderer = Remotion** (server-side), acting as a `spec→MP4+SRT` black box; started with pnpm.
- **Category = OpusClip-like** (server-side pipeline + lean editing surface + hand off to CapCut/Premiere for fine editing). Editing form follows Descript (transcript editing / delete sentence = cut segment, non-destructive / single-track trim), **no multi-track NLE / layers / effects / client-side engine**.
- **Brand enters rendering**: The API parses `BrandTemplate` into `ClipBrand` (logo/CTA/caption color/font size/font/fill/intro-outro) at generation time and **bakes it into `render_spec`**; the rendering service only reads the spec, not the DB, ensuring parity.
- **Music enters rendering**: `BrandTemplate.musicMood` → `ClipMusic.url` (built-in mood music library `/api/v1/music/<mood>`) → Remotion `<Audio>` looped and mixed.
- **Hard prerequisites**: Multi-language ASR (word-level timestamps) + streamable/seekable video. Storage is **S3-compatible object storage (Volcengine TOS, ADR-024)** — the API performs ownership checks and 307-redirects to public object URLs (or streams via `?proxy=1` for programmatic fetches); uploads go through short-lived presigned PUT URLs.
- **Low regret**: The spec is stable; in the future it can be swapped for hand-rolled FFmpeg (+ shared libass across both ends) or client-side WebCodecs without changing the contract.

## 11. Data Model Conventions

Field-level truth lives in code: `apps/api/app/models/tables.py` (table structures) + `apps/api/migrations/` (evolution history). Docs do not duplicate field tables (the pre-2026-07 PRD copy had already drifted). Cross-cutting conventions:

- **Auth & isolation**: passwordless email verification-code login (Resend); per-user data isolation across speakers / projects / assets / brand templates / chat sessions. The seeded default user remains only as the owner of shared demo content.
- **Storage keys**: PostgreSQL stores object keys only; bytes live in TOS (ADR-024). Key prefix `{user_id}/…` carries ownership; `demo/` is anonymous-readable.
- **EU data residency**: project-level `data_region` is a future differentiator (see `docs/ROADMAP.md` §7), not implemented.
- **UI language preference**: future; the first screen renders in English to avoid hydration mismatch (see CLAUDE.md i18n).
