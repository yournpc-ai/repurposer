# Architecture Decision Records (ADR)

## ADR-001: Single-repo, simple directory structure

**Status**: Decided

**Context**: Need to manage both a Python backend and a Node.js frontend.

**Decision**: Use a single repository with separate frontend and backend directories. Do not introduce monorepo tools like Turborepo/Nx/Pants.

```
repurposer/
├── apps/api/
├── apps/web/
├── docs/
└── scripts/
```

**Rationale**:
- P0 phase: frontend and backend interactions are simple, with little shared code
- Each uses its own package manager (uv / pnpm), no interference
- Coordinate startup with `Justfile` or `scripts/dev.sh`
- Avoid unnecessary tooling learning overhead

**Alternatives**:
- Turborepo: not suitable for Python
- Nx: not Python-native
- Pants/Bazel: too heavy
- Multi-repo: inconvenient for syncing changes

---

## ADR-002: FastAPI for the backend

**Status**: Decided

**Decision**: Use FastAPI for the backend.

**Rationale**:
- Auto-generates OpenAPI documentation
- Native Pydantic support, good for structured output
- Excellent async performance
- Team familiarity

---

## ADR-003: MiniMax M3 as the core intelligence layer

**Status**: Decided

**Decision**: Use MiniMax M3 as the core LLM.

**Rationale**:
- 1M context window, can ingest transcripts + past materials + examples
- Native multimodal, can process images
- Supports structured output
- Stable access from mainland China

**Risk**:
- If output quality is unstable, may need to fallback to another model

---

## ADR-004: Hand-rolled agent workflow

**Status**: Decided

**Decision**: Do not introduce Pydantic AI / LangGraph / CrewAI for P0. Build a custom agent orchestrator.

**Rationale**:
- Single model (MiniMax M3), no need for provider abstraction
- Workflow is clearly fixed: persona → analyze → script → review → revise → HITL
- Prompts need fine-grained control; framework templates may not be flexible enough
- White-box debugging is easier

**Future**: If the P2 workflow becomes very complex, re-evaluate LangGraph or Pydantic AI.

**Context appendix**（2026-07-20 自 PRD §20 迁入，决策当时的候选对比，仅作历史存档）:

| Framework | Core Positioning | Suitability |
|:---|:---|:---|
| Pydantic AI | Type-safe LLM Agent | High, but needs MiniMax Custom Model |
| LangGraph | Complex state machine workflow | High, strongest HITL, steep learning curve |
| ControlFlow | Structured Agent task flow | High, clearest code, small ecosystem |
| CrewAI | Role-playing multi-Agent | Medium, simple API but weak control |
| dspy | LLM program optimization | Medium, for continuous prompt optimization |
| Hand-rolled | Self-developed orchestrator | High, fully controllable |

Hand-rolled vs Pydantic AI 关键差异：开发速度（P0 手搓更快，无需适配层）、MiniMax 兼容性（直连 vs Custom Model 适配）、调试白盒 vs 框架黑盒、未来扩展性（框架更整洁）。

---

## ADR-005: uv for Python package management

**Status**: Decided

**Decision**: Use uv as the Python package manager.

**Rationale**:
- Fast
- Modern Python workflow (lock files, venv, run all-in-one)
- Good fit for new projects

---

## ADR-006: TanStack Start + TypeScript for the frontend

**Status**: Decided

**Context**: P0 is internal validation, but the end goal is a SaaS product, so we need to lay the groundwork for productization.

**Decision**: Use TanStack Start + TypeScript for the frontend.

**Rationale**:
- Platform-agnostic, not tied to Vercel
- Strong end-to-end type safety
- Explicit server/client boundaries, reducing hydration and key leakage issues
- Prepares for future SaaS productization

**Risks**:
- Framework is relatively new, smaller ecosystem than Next.js
- Team learning curve
- AI coding tools have weaker support for TanStack Start

**Mitigation**:
- P0 features are simple, no complex features needed
- Documentation is solid, core concepts are clear

---

## ADR-007: OpenAPI for API type synchronization

**Status**: Decided

**Decision**: Do not maintain a shared types package between frontend and backend. Generate frontend types from the backend OpenAPI spec.

**Rationale**:
- Reduces shared package maintenance cost
- Backend is the source of truth for types
- Use `openapi-typescript` for automatic generation

---

## ADR-008: Video rendering starts with image carousel + subtitles

**Status**: Decided

**Decision**: For P0, video rendering does not aim for complex editing. Start with an image carousel + subtitles + BGM format.

**Rationale**:
- Quickly validate content generation quality
- Reduces rendering complexity
- Can be replaced with a more sophisticated video engine later

---

## ADR-009: Voice cloning deferred to P1

**Status**: Decided

**Decision**: Use generic TTS for P0; integrate voice cloning in P1.

**Rationale**:
- P0 first validates script and content quality
- Voice cloning involves additional issues like authorization and quality evaluation
- Generic TTS is sufficient for demo needs

---

## ADR-010: PostgreSQL as the database

**Status**: Decided

**Decision**: Use PostgreSQL for P0.

**Rationale**:
- End goal is SaaS; PostgreSQL is a production-grade choice
- Better than SQLite for multi-user, concurrency, and data integrity
- Team familiarity, mature ecosystem
- Simple local startup with Docker Compose

**Alternatives**:
- SQLite: simpler deployment, but poor scalability

---

## ADR-011: Local file system for file storage

**Status**: Superseded by ADR-024 (object storage, Volcengine TOS)

**Decision**: Store uploaded files on the local file system for P0.

**Rationale**:
- P0 is internal validation; local storage is zero-cost
- After abstracting file paths, P1 can seamlessly migrate to object storage
- Simple deployment, no cloud storage configuration needed

**Future**: Evaluate MinIO / Alibaba Cloud OSS / AWS S3 in P1.

---

## ADR-012: P0 is an internal validation tool; future target is SaaS

**Status**: Decided

**Context**: Need to clarify P0's positioning to guide tech choices and feature scope.

**Decision**: Run P0 first as an internal tool to validate the core workflow, but choose technologies that prepare for future SaaS.

**Impact**:
- Frontend chose TanStack Start instead of Streamlit
- Database chose PostgreSQL instead of SQLite
- Code structure considers multi-user and permission extensibility
- P0 does not implement billing or multi-tenancy, but leaves room for extension

---

## Open items

| Item | Recommendation | Decision maker |
|:---|:---|:---|
| Product name | TBD | CEO Zuo |
| Task queue | Postgres `FOR UPDATE SKIP LOCKED` + standalone worker process | Engineering |
| Speech recognition | faster-whisper self-hosted for P0 | Engineering |
| Video rendering engine | Remotion (server-side headless Chrome + FFmpeg) as first renderer; clip-spec(JSON) contract preserves future swap to hand-rolled FFmpeg | Engineering |
| Speech synthesis service | MiniMax voice_clone + T2A for dubbing in P0 | Engineering |
| Music assets | Built-in mood music library (`/api/v1/music/<mood>`) + optional custom upload | Product / Engineering |
| URL input support | Not in this phase | Product |
| Languages supported in first phase | Chinese/English + German/French/Spanish/Italian | Product |
| Pricing model | Not designed in this phase | CEO Zuo |

## ADR-013: Internationalization, theme switching, and European market positioning

**Status**: Decided

**Context**: Repurposer targets the European knowledge-speaking market, while also needing to support light/dark theme switching and compliance requirements for European institutions.

**Decision**:
1. Use `i18next` + `react-i18next` for internationalization on the frontend.
2. **Default language is English**; user selection is written to the `repurposer-lang` cookie, restored by the client after refresh.
3. **Default theme is dark**; manual user switch is written to `localStorage`. The `system` preference is also treated as dark.
4. Theme switching uses the View Transition API with a circular reveal animation from the click position.
5. All icons use `lucide-react` uniformly.
6. **Product positioning shifts from "viral short videos" to "knowledge assetization"**: core outputs are LinkedIn long posts, quote cards, multi-language summaries, newsletters, etc. Target users are academic/corporate summit speakers and research institutions.
7. **Multi-language output is the entry ticket to the European market**: in addition to UI language, content generation must cover FR/DE/ES/IT and other major European languages.
8. **GDPR / EU data residency as a sales differentiator**: through Cast AI Kimchi's M3 EU deployment capability, provide optional EU data processing to meet the procurement threshold of European institutions.

**Rationale**:
- `i18next` is mature, type-constrainable, and fits the scale of this project.
- In SSR scenarios, fixing the first render to English + client-side cookie restoration avoids hydration mismatch.
- `localStorage` + anti-FOUC inline script prevents theme flashing.
- View Transition API provides native smooth animations on Chromium/Safari, with automatic degradation on Firefox.
- A unified icon library avoids style inconsistency and manual SVG maintenance.
- The European knowledge-speaking market is a whitespace not well covered by OpusClip/Descript; LinkedIn is the core B2B knowledge dissemination channel; multi-language and GDPR compliance are hard requirements.
- The agent-driven Analyzer → Script → Review → Reviser → HITL loop meets European users' high demands for content quality and controllability.

**Constraints and notes**:
- shadcn components are based on base-ui; triggers use the `render` prop, not `asChild`.
- New user-facing copy must be updated in both `en.ts` and `zh.ts` simultaneously, keeping key structures consistent.
- Browser APIs (`localStorage`, `matchMedia`, `document.startViewTransition`) must be placed in client-side code paths.
- Frontend copy, examples, and tool grids should avoid descriptions targeting C-end entertainment short videos like "Douyin/TikTok/viral/爆款".

**Related files**:
- `apps/web/src/lib/i18n/`
- `apps/web/src/lib/theme/ThemeProvider.tsx`
- `apps/web/src/components/language-switcher.tsx`
- `apps/web/src/components/theme-toggle.tsx`
- `apps/web/src/routes/__root.tsx`
- `apps/web/src/routes/index.tsx`
- `CLAUDE.md`
- `.claude/projects/-Users-sylas-repurposer/memory/europe-strategy-positioning.md`

## ADR-014: Sidebar references OpusClip layout and Brand Template page

**Status**: Decided

**Context**: As navigation items grow (Home, Projects, Speakers, Library, Brand template), the top bar on the home page carries too many global actions; meanwhile, users want to reuse OpusClip's sidebar interaction and Brand template configuration page.

**Decision**:
1. Adopt a left collapsible icon sidebar (`shadcn/ui Sidebar collapsible="icon"`), referencing OpusClip's hide/expand interaction.
2. Place the workspace logo, collapse button, and user avatar dropdown at the top of the sidebar; the dropdown is simplified to Profile / Settings / Logout, removing excessive business items from OpusClip.
3. Group navigation in the middle by `Create` (Home, Projects, Speakers) and `Post` (Library, Brand template).
4. Add a `/brand-template` page: left settings panel (font, primary color, accent color, logo, default CTA, language tone), right real-time preview of quote card and LinkedIn post sample.
5. Add i18n keys: `nav.create`, `nav.post`, `nav.brandTemplate`, `brandTemplate.*`, `common.profile/settings/logout/helpCenter/inviteMembers/freePlan/new`.

**Rationale**:
- Extract global navigation from the home page content area, so the home page can focus on prompt input and the knowledge asset tool grid.
- Brand template is a core configuration entry for a knowledge assetization SaaS, allowing users to control output style uniformly.
- OpusClip's sidebar mode has been validated in video/content creation tools, with low user learning cost.

**Constraints and notes**:
- Continue using base-ui's `render` prop, not `asChild`.
- New sidebar entries must be synchronized with `zh.ts`/`en.ts` `nav.*` keys.
- Brand template is currently a frontend mock preview; needs to connect to the backend `BrandTemplate` config table later.

**Related files**:
- `apps/web/src/components/app-sidebar.tsx`
- `apps/web/src/routes/brand-template.tsx`
- `apps/web/src/routes/index.tsx`
- `apps/web/src/lib/i18n/locales/zh.ts`
- `apps/web/src/lib/i18n/locales/en.ts`
- `CLAUDE.md`
- `.claude/projects/-Users-sylas-repurposer/memory/repurposer-sidebar-opusclip-reference.md`

## ADR-015: ORM uses SQLAlchemy, migration tool uses Alembic

**Status**: Implemented

**Context**: The backend already uses SQLAlchemy 2.0 (`[asyncio]` + asyncpg) as the ORM. Early on, tables were created with `Base.metadata.create_all()` at startup, but as features evolved, existing table columns and constraints needed to be modified (e.g., `projects.speaker_id` changed to nullable). `create_all` cannot handle such changes.

**Decision**:
1. **Do not switch ORMs**: SQLAlchemy 2.0 async is the correct choice; no alternatives are evaluated.
2. **Do not bulk-rewrite for style**: existing legacy `Column(...)` syntax is not rewritten to 2.0's `mapped_column`/`Mapped[]`/`relationship` (pure type-hint improvement, no functional impact); new tables may optionally use the new syntax, but it is not mandatory.
3. **Use Alembic for schema changes**: `alembic.ini`, `migrations/env.py`, and `migrations/versions/` are already initialized.
4. **Auto-migrate on application startup**: `app/models/database.py` `init_db()` calls `alembic.command.upgrade(..., "head")` in the lifespan, ensuring new environments or CI auto-sync to the latest schema.
5. **Alembic env.py uses a synchronous driver**: the main app continues with `postgresql+asyncpg`; Alembic migrations use `postgresql+psycopg2`, avoiding the issue of calling `asyncio.run()` inside an existing uvloop event loop.

**Migration workflow**:

```bash
cd apps/api

# Apply migrations
uv run alembic upgrade head

# Check current version
uv run alembic current

# Generate new migration after modifying models
uv run alembic revision --autogenerate -m "describe change"

# Rollback one level
uv run alembic downgrade -1
```

**Rationale / Notes**:
- `create_all` **only creates missing tables, it does not modify columns on existing tables** — adding columns or changing constraints on existing tables silently does nothing, causing model/database inconsistency and runtime errors.
- Auto-migration is suitable for local development and simple deployments; for production, it is recommended to explicitly run `alembic upgrade head` in the deployment pipeline rather than relying on auto-migration at application startup.
- After generating a migration, always manually review the generated script; autogenerate is not 100% accurate (e.g., enums, complex constraints may need manual adjustment).

**Related files**:
- `apps/api/alembic.ini`
- `apps/api/migrations/env.py`
- `apps/api/migrations/versions/`
- `apps/api/app/models/database.py` (`init_db`)
- `apps/api/app/models/tables.py`
- `apps/api/pyproject.toml`

## ADR-016: Vertical short video editor — lock down the clip-spec contract, Remotion as the first renderer (replaceable black box)

**Status**: Decided (detailed design in [VIDEO_EDITOR.md](./VIDEO_EDITOR.md))

**Context**: "Vertical short video final cut" is confirmed as a required MVP item, and must be editable. Need to finalize the choice among "self-built FFmpeg / Remotion / CapCut Web client engine", and clarify what level of editing is feasible.

**Decision**:
1. **Lock down the single contract: declarative `clip-spec(JSON)`** (renderer-agnostic, only describes "what it is": segment list / crop / subtitle track / style preset / title / music / brand). The renderer is a **replaceable implementation** behind the contract.
2. **First renderer uses Remotion** (server-side, headless Chrome + internal FFmpeg), treated as a **black box** for `spec→MP4+SRT`; Node render service starts with pnpm, self-hosted in EU, triggered by the existing Python queue.
3. **Category positioning = OpusClip class** (server-side pipeline + browser thin editing surface + hand off to CapCut for fine editing), **not CapCut Web client engine**.
4. **Editing form = Descript-style document editing**: transcript editing (delete sentence = cut segment, non-destructively recoverable) + word↔timecode + **single-track trim**; **no multi-track NLE / layer compositing / transition effects / B-roll library / auto face tracking** (L3, hand off to downstream).
5. **Styles limited to preset enums** (expressible by both CSS and libass), guaranteeing "preview = final cut" and preserving low-cost future migration to hand-built FFmpeg.
6. **ASR (word-level timestamps) upgraded from optional P1 to hard prerequisite**; video needs to be **streamable/seekable** (local file system + FastAPI Range endpoint is sufficient, **object storage not required**, deferred to scale per ADR-011). Without ASR + playable video, the editor cannot be built.

**Rationale**:
- Our task is "processing existing material"; editing needs top out at "cut segments + subtitles + styles", far from multi-track NLE; self-building a WASM engine is paying years of engineering for a non-existent need.
- Remotion makes parity (preview = final cut) structurally natural, handles media dirty work maturely, `<Player>` directly serves as preview, fits the React stack — a faster path to a polished MVP for a small team.
- Because the contract is stable, **low regret**: if bills/scale become painful later, can switch to hand-built FFmpeg (clip-spec→filtergraph + shared libass on both ends) or client-side WebCodecs, without changing the spec.

**Costs / Notes**:
- Introduces a Node render service (polyglot stack, but boundary is a clean black box) + Remotion license (4+ people $25/seat or $0.01/render).
- "Headless Chrome frame-by-frame rendering" is heavy, but MVP scale (short clips) is fine; optimize or switch at high volume.
- Python has no Remotion equivalent (web-tech parity paradigm is tied to JS/browser): for parity, accept Node; insist on pure Python and you land on ffmpeg-python + shared libass hand-building (another paradigm).

**Related files**:
- `docs/VIDEO_EDITOR.md`
- `apps/api/app/models/tables.py` (`Clip` adds `render_spec/render_status/render_error/srt_url`)
- `apps/api/app/worker.py`, `apps/api/app/services/jobs.py` (render claim source)
- `.claude/projects/-Users-sylas-repurposer/memory/repurposer-video-editing-direction.md`

## ADR-017: Postgres as the task queue (no Redis), standalone worker process

**Status**: Implemented

**Context**: ASR, video rendering, etc. are time-consuming heavy tasks; originally generation ran in FastAPI `BackgroundTasks` (in-process, lost on restart, no retries, no concurrency control), and asset uploads were synchronous blocking. A reliable async execution layer is needed.

**Decision**:
1. **Use Postgres `FOR UPDATE SKIP LOCKED` as the queue**, **do not introduce Redis/Celery** (fits ADR-001 simplicity-first; replacing with arq/Celery for horizontal scaling later is a single swap).
2. Standalone **worker process** (`python -m app.worker`) polls and claims `Asset` (pending processing) and `WorkflowRun` (pending generation), physically isolated from the API process; starts `reap_stale` to reset orphaned tasks. `claim_pending_run` **defers runs whose project still has pending/processing assets** (the run stays PENDING until ASR/extraction settles), so `/generate` can be called immediately after upload without any client-side wait.
3. `Asset` adds `processing_status` (pending/processing/completed/failed) + `processing_error`; upload returns pending immediately after disk write, frontend polls.
4. `app/services/asset_processing.py` dispatches processors by type — **future single entry point for ASR/OCR** (currently video/audio is no-op).
5. Generation unified through `/generate` outputs multi-select (clips/linkedin/quote_cards/summary/blog), deleting the previous 4 duplicate synchronous generation endpoints.

**Rationale**:
- Internal validation phase (ADR-012) throughput/scale does not yet need Redis; DB-as-queue adds zero new middleware.
- Worker process isolation prevents heavy tasks from dragging down online requests; `SKIP LOCKED` supports safe concurrent multi-worker.

**Related files**:
- `apps/api/app/worker.py`, `apps/api/app/services/jobs.py`, `apps/api/app/services/asset_processing.py`
- `apps/api/app/models/tables.py` (`Asset.processing_status`)
- `scripts/dev.sh`, `docker-compose.yml` (worker process, no redis)
- `.claude/projects/-Users-sylas-repurposer/memory/repurposer-queue-foundation.md`

## ADR-018: Render service isolated as apps/render + shared packages/clip + pnpm workspace

**Status**: Implemented

**Context**: Remotion's parity (preview = final cut) requires the `<Clip>` component to be **shared** between the web's `<Player>` (preview) and the render service's `renderMedia` (final cut). Need to decide where in the repo the render service and this shared component live, without breaking ADR-001's runtime isolation.

**Decision**:
1. **Render service isolated as `apps/render/`** (Node/pnpm, `@remotion/bundler` + `@remotion/renderer` + express), externally a `POST /render: spec→MP4+SRT` black box. **Not placed under `apps/api/`** (api is Python/uv, mixing runtimes violates ADR-001).
2. **`<Clip>` component + clip-spec TS types extracted to `packages/clip/`** shared package (`@repurposer/clip`), imported by both web and render.
3. **Use a lightweight pnpm workspace** (`pnpm-workspace.yaml` includes `apps/web`/`apps/render`/`packages/*`) to connect the three TS packages; **`apps/api` stays independent with uv, not in the workspace**.
4. `onlyBuiltDependencies` moved from `apps/web` to the workspace root.

**Rationale**:
- Parity requires component sharing — this is the entire reason for choosing Remotion; cannot write two separate copies.
- pnpm workspace is the **lightest sharing mechanism** (one yaml), not the Turborepo/Nx/Bazel that ADR-001 opposes; this is a reasonable evolution of ADR-001's "no shared code" premise (there is now a piece that must be shared: `<Clip>`).
- api remains fully isolated as Python/uv.

**Constraints and notes**:
- render's `spec.source.url` must be an **absolute URL** (the API worker absolutizes the storage seam's relative URL before calling).
- render outputs MP4/SRT to a **temporary directory**, then PUTs them to the presigned URLs supplied by the API worker. No shared volume or local `data/outputs` is used.
- First Remotion render will download headless Chromium (~hundreds of MB); some native dependency build scripts may need `pnpm approve-builds`.
- `<Clip>` MVP renders the first kept segment; multi-segment concat (gaps from transcript sentence deletion) is implemented.
- Brand (logo/CTA/subtitle color/font size/font/fill/opening/closing) and music are **baked into `render_spec`** as resolved values; `<Clip>` consumes `spec.brand` / `spec.music`; render service does not read the DB.
- Subtitle fonts use `@remotion/google-fonts` (Latin subset), fetched from Google CDN on first render; offline scenarios may switch to `@remotion/fonts` local woff2 in the future.

**Related files**:
- `apps/render/` (`src/server.ts`/`render.ts`/`srt.ts`), `packages/clip/` (`src/Clip.tsx`/`Root.tsx`/`types.ts`/`fonts.ts`)
- `pnpm-workspace.yaml`, `scripts/dev.sh`, `README.md`, `docs/VIDEO_EDITOR.md` §6

**Containerization (supplement)**:
- All 5 full-stack services have Dockerfiles: `api` (uv, installs `libgomp1` for ctranslate2), `worker` (reuses api image with different `command`), `render`, `web`.
- **`render` / `web` build context is the repo root** — they import workspace package `@repurposer/clip`, and a subdirectory context cannot access `pnpm-workspace.yaml` / `pnpm-lock.yaml` / `packages/clip`. Dockerfile first COPYs each workspace's `package.json` (needed for pnpm to resolve the whole graph) + lockfile to install dependencies, then COPYs source code, maximizing layer cache.
- `render` image installs headless Chromium system libraries (libnss3/libatk/libgbm/fonts, etc.); Chromium binary is **lazily downloaded on first render** (not pulled during build, avoiding build dependency on external network and hanging in CI/restricted networks; render service runtime already needs external network to pull source video). Production can mount a cache volume on the Remotion download directory to avoid re-downloading on restart.
- Container service interconnection: `API_PUBLIC_URL=http://api:8000`, `RENDER_URL=http://render:3001/render` (overrides localhost defaults in `config.py`). The render service uploads outputs to the presigned URLs provided by the API worker; no shared volumes are required.
- **`web` uses `vite preview` for SSR**: sufficient for MVP/staging; switch to a lightweight node http adapter around the exported fetch handler (`dist/server/server.js`) for high traffic. This SSR path has been smoke-tested through image build and single-frame rendering.

## ADR-019: Music uses built-in mood library (user-provided music pieces)

**Status**: Superseded by ADR-023 / `docs/MUSIC_ARCHITECTURE.md`

**Context** (historical): clip-spec has a `music` block, brand template has `musicMood`, but missing "where do music pieces come from". Involves copyright; cannot have AI automatically grab unauthorized music.

**Decision** (historical):
1. **Built-in mood library**: local `data/music/<mood>.<ext>` (supports `.mp3/.m4a/.aac/.ogg/.wav`), music pieces provided by users/operations with authorization.
2. **Route by mood**: `GET /api/v1/music/<mood>` extension-agnostic, resolver finds files by stem; with Range support.
3. **Bake at generation time**: `services/brand.py:music_from_template` maps `BrandTemplate.musicMood` → `ClipMusic{music_id, url}`; `ClipMusic.enabled` is controlled by `musicEnabled`.
4. **Render mix**: Remotion `<Audio src={url} volume={dbToLinear(gain_db)} loop>`.

**Rationale** (historical):
- No third-party music API/subscription, zero new dependencies or costs.
- Copyright responsibility is clear: users/operations only place authorized music pieces; repo does not bundle music.
- Library can expand with operations: add files, no code changes needed.

**Related files**:
- `apps/api/app/services/storage.py`
- `apps/api/app/routers/music.py`
- `apps/api/app/services/brand.py` (`music_from_template`)
- `packages/clip/src/Clip.tsx` (`<Audio>`)

## ADR-020: Final cut supports a second source kind — "stills" image+audio audiogram

**Status**: Implemented

**Context**: The MVP's top output "vertical highlight clips" originally only produced video when there was a real-person VIDEO source; pure audio speeches
(podcasts/roundtables) and presentations with only images + key points could not produce any video at all. Meanwhile, tools like Headliner / Typito / Canva
commonly combine **images + optional audio + text** into vertical videos (audiogram), which is a coherent and
common format.

**Decision**: Add a discriminator field to clip-spec's `ClipSource`, renderer branches, video path unchanged (backward compatible):
1. `kind: "video" | "stills"` (default `"video"`).
2. For `stills`, `image_urls: list[str]` serves as the base visual (0→solid color / 1→full screen / N→hard-cut carousel evenly distributed by duration),
   `url` is reused as an **optional** voice track (empty string if no recording).
3. If audio is present, reuse ASR word-level `caption_track` + voice track; if no audio, fixed-duration slideshow
   (each image `SECS_PER_IMAGE=4s`, backend writes a synthetic segment to fix duration).
4. Source selection priority at generation time: VIDEO → AUDIO → IMAGE; if none are present, `render_spec=None` (text-only assets).

**Scope boundary (stay at L2)**: Only single-track hard-cut stills + existing word-by-word subtitles + title/logo/CTA/music/opening/closing.
**Not doing** (L3 or later): image transitions/cross-fade, Ken-Burns pan/zoom, multi-sentence kinetic-typography
animated text tracks, B-roll library, single-image free layout, waveform animation.

**Rationale**:
- Reuses already-built ASR (subtitle timeline) + brand/music/opening/closing rendering path, zero new heavy dependencies.
- Contract describes "what it is" — "this clip is composed of images + optional audio" is a valid "what it is", and a future hand-built FFmpeg
  renderer would also need this discriminator field; it is not a renderer leak.
- `<Clip>` same component serves both preview and final cut; stills reuses `<Sequence>/<Series>/<Img>/<Audio>` primitives.

**Related files**:
- `packages/clip/src/types.ts` (`ClipSource.kind` / `image_urls`), `Clip.tsx` (kind branch + `splitFrames`), `Root.tsx` (default spec)
- `apps/api/app/models/schemas.py` (`ClipSource`), `services/clip_spec.py` (`build_clip_spec` stills branch + `SECS_PER_IMAGE`)
- `apps/api/app/services/generation.py` (source selection priority VIDEO→AUDIO→IMAGE), `services/rendering.py` (`_absolutize` handles `image_urls`)
- `apps/web/src/routes/projects.$id.tsx` (upload infers type by MIME, never infers voice_sample)

## ADR-022: Music library CRUD (management layer over the mood library)

**Status**: Superseded by ADR-023

> 2026-07-20 补录：此 ADR 被 ADR-023 与 `docs/MUSIC_ARCHITECTURE.md` 引用但从未落笔成文，按代码与文档记录重建。

**Decision**: 在 ADR-019 的文件系统情绪音乐库（`data/music/{mood}.<ext>`）之上加管理 CRUD 层（上传 / 列表 / 指派 mood），供后台维护音乐素材。

**Consequences**: 管理面建立在"人工采集音频"之上，素材版权状态不可控；ADR-023 随后将音乐库整体改为 AI 生成 + `Music` 表，本决策的文件系统部分随之废弃，管理 API 演化为 `app/routers/music.py`。

---

## ADR-023: Music becomes an AI-generated, asset-based library

**Status**: Implemented (2026-07; supersedes ADR-019/ADR-022 的人工采集路线)

**Context**: ADR-019 established a filesystem-only mood music library (`data/music/{mood}.<ext>`), and ADR-022 later added a management CRUD layer on top of it. Both approaches share a fundamental limitation: they rely on manually sourced audio files with uncertain copyright status. Opus Pro and similar tools frequently show "license expiry" warnings, and user-uploaded music pieces introduce legal liability. Meanwhile, MiniMax (and other providers) now offer music generation APIs, making it possible to produce original, platform-safe background music on demand.

**Decision**:
1. **Default music is AI-generated and stored in a dedicated `music` table**: three pre-generated music pieces (`calm`, `uplifting`, `corporate`) are seeded as `Music` rows at application startup. Audio objects live in S3-compatible object storage under `music/`; structured metadata lives in the `music` table.
2. **Brand template selects by music id**: `BrandTemplate.config.musicId` replaces `musicMood`. The template only picks a default music piece; it does not store a generation prompt or a mood string.
3. **Clip Agent selects music per clip**: based on the brand default, the Content Director's mood suggestion, and the clip's content tone, the Clip Agent picks an existing music piece. No music generation API is called during clip generation.
4. **Chat/Editor can regenerate music**: explicit user requests trigger MiniMax music generation, creating a new `Music` and updating `Clip.render_spec.music`. The clip is then re-rendered.
5. **Render contract unchanged**: Remotion still consumes `spec.music.url` and `spec.music.enabled`.
6. **User uploads deferred**: AI-generated music covers MVP needs. Uploaded music may be added later with explicit rights attestation, private-by-default visibility, and a takedown process.

**Rationale**:
- Eliminates platform copyright risk for default and chat-generated music.
- Keeps generation fast and cheap by selecting from pre-generated music pieces instead of generating per clip.
- Makes music a clip-level creative decision rather than a static brand setting.
- Uses a dedicated `music` table because the existing `Asset` table requires every row to belong to a `project_id` or `speaker_id`, which does not fit global/shared music library items.

**Consequences**:
- `musicMood` and the filesystem-only resolver become legacy; existing templates and clips need migration or graceful fallback.
- Local `assets/` and `data/music/` storage is removed; all music objects live in object storage.
- A new `music` table and Alembic migration are required.
- Custom music generation is more expensive than selection, so quotas or paid tiers may be needed.
- MiniMax (or chosen provider) usage terms must explicitly allow commercial use and redistribution.

**Related documents**:
- `docs/MUSIC_ARCHITECTURE.md` (detailed design, flows, data model, phases, copyright strategy)
- `docs/VIDEO_EDITOR.md` (`render_spec.music` contract)
- `docs/AGENT_ARCHITECTURE.md` (4-layer agent integration)

**Related files**:
- `apps/api/app/models/schemas.py` (`MusicResponse`, `MusicGenerateRequest`, `MusicMetadataUpdate`, `ClipMusic`, `BrandTemplateConfig`)
- `apps/api/app/models/tables.py` (`Music`)
- `apps/api/app/services/music_generation.py` (future)
- `apps/api/app/services/music.py` (future)
- `apps/api/app/agents/clip_agent.py` (music selection)
- `apps/web/src/components/brand-template/music-panel.tsx` (future)
- `packages/clip/src/types.ts` (`ClipMusic`)


## ADR-021: Speaker = persisted memory (optional selection / auto-create if not selected / per-user isolation)

**Status**: Implemented

**Context**: `Speaker` and `Persona` were used interchangeably in code, documentation, and UI, causing conceptual ambiguity such as "Is Speaker a CRM contact? Or a user profile? Is Persona a standalone entity or a sub-field of Speaker?" After clarification: **Speaker is essentially memory persisted after a task completes** — recording the user's tone, style, preferences, voiceprint, and other stable characteristics. Externally still called Speaker, internally it is memory.

**Decision**:
1. **Speaker = persisted memory**: a user profile extracted from task inputs (prompt + attachments) via M3 analysis, persisted to the `speakers` table after the task completes.
2. **Per-user isolation**: `user_id` is on the `speakers` table; users can only see and operate their own Speakers.
3. **Optional selection on home page / project creation**: existing Speakers can be selected in the input box / project creation form, but **not mandatory**. Users may actively choose a historical profile, or choose not to select one.
4. **Auto-create if not selected**: if the user does not select a Speaker, the system automatically creates one after task analysis completes, and associates it with the current project.
5. **Support multiple Speakers**: users can retain multiple Speaker records (e.g., different occasions / different identities), not forced to a singleton. But the default auto-created one is the current task's profile.
6. **Naming unification**: code and documentation no longer treat `Speaker` and `Persona` as two separate entities. `Persona` is only used as a conceptual word describing the internal style attributes of a Speaker, not reflected in table names, routes, or component names. The legacy `SpeakerPersona` schema has been removed; `SpeakerContext` is the single agent-facing object, and style/memory fields are stored as flat columns on the `speakers` table.
7. **Keep `/speakers` management page**: users can view, edit, and delete their own Speaker records on the list page; the detail page is for editing memory fields.
8. **Two-layer division unchanged**: Speaker = stable user style memory; Project = current theme/intent + materials.
9. **Dub voiceprint attached to Speaker**: priority is profile.VOICE_SAMPLE → current AUDIO/VIDEO; `voice_id` is cached on the Speaker, cloned once and reused across projects.

**Boundaries (explicitly not doing)**:
- auth / multi-tenancy / team collaboration are still post-auth items.
- Not forcing users to have only one Speaker; multi-Speaker selection is reserved for subsequent product iterations.

**Rationale**:
- Eliminates understanding cost from `Speaker`/`Persona` naming confusion.
- New users do not need to maintain a profile first, lowering the barrier to entry.
- Existing users can still actively select or manage historical profiles, preserving flexibility.
- Dub voiceprint has a stable owner, cloned once and reused.

**Related files (at implementation time)**:
- `apps/api/app/models/tables.py` (add `user_id`)
- `apps/api/app/routers/speakers.py` (filter by user, optional selection support)
- `apps/api/app/routers/projects.py` (`speaker_id` optional)
- `apps/api/app/services/generation.py` (auto-create Speaker when not selected)
- `apps/api/app/routers/clips.py` (dub reads profile voiceprint + voice_id cached on profile)
- `apps/web/src/routes/index.tsx`, `projects.tsx` (optional Speaker selection)
- `apps/web/src/routes/speakers.tsx`, `speakers.$id.tsx` (per-user isolated multi-Speaker management page)

## ADR-024: Object storage (Volcengine TOS) for all persistent files

**Status**: Implemented (supersedes ADR-011's local-FS decision; ADR-016's "local FS + Range suffices" note is updated accordingly)

**Context**: The local-filesystem approach (ADR-011) tied file serving to the API host's disk, blocked multi-instance deployment, and mixed uploaded assets with the repo checkout. The music library (ADR-023) already assumed object storage. Meanwhile `assets/` and `data/` local dirs have been removed from the repo.

**Decision**:
1. **All persistent files live in one S3-compatible bucket (Volcengine TOS)**: uploads, rendered outputs, brand media, music, demo assets. PostgreSQL stores only object keys.
2. **Per-user key prefixes**: `{user_id}/uploads|outputs/...`; shared demo assets under `demo/`; music under `music/`. The files endpoint derives ownership from the key prefix (`demo/` is anonymous-readable).
3. **Uploads are direct-to-storage**: the API issues short-lived (15 min) presigned PUT URLs; the client PUTs bytes directly and then creates the Asset row from the returned key. The create-from-key endpoint validates the key prefix and that the object exists.
4. **The bucket is public-read without ListBucket**: reads 307-redirect from the API (after an ownership check) to the public object URL. Accepted trade-off for MVP (URLs are unguessable UUID keys); revisit private bucket + presigned GET before EU institutional sales.
5. **Two delivery modes**: redirect (default, for `<video>/<img>` tags) and `?proxy=1` (API streams bytes) for programmatic `fetch()` — the bucket does not send `Vary: Origin`, so a no-cors copy of an object poisons the browser cache for later CORS fetches.
6. **Downloads use presigned GET** carrying `Content-Disposition: attachment` (`/outputs/{key}?download=1`).

**Consequences**:
- Local `assets/` and `data/` directories are deleted; `scripts/migrate_to_tos.py` performs the one-time upload of MVP assets.
- Render service uploads outputs via presigned PUT; no shared volumes anywhere.
- Frontend receives storage-public URLs at the API boundary (`resolve_stored_url`); the DB keeps bare keys.

**Related files**:
- `apps/api/app/services/storage.py` (keys, presign, public/resolve URLs)
- `apps/api/app/routers/files.py` (redirect / proxy / presigned download)
- `apps/api/scripts/migrate_to_tos.py`
- `docker-compose.yml` (S3_* env wiring)

---

## ADR-025: Thin LLM provider interface (amends ADR-004's "no provider abstraction" rationale)

**Status**: Decided

**Context**: ADR-004 rejected agent frameworks partly on the grounds of "single model (MiniMax M3), no need for provider abstraction", and agents today depend directly on `clients/minimax.py` via `MiniMaxAgentBase`. Three things changed since:

1. **EU institutional sales** (ADR-013's positioning, EU AI Act era) may require EU-hosted models (e.g. Mistral) for data-residency reasons. Without an interface, every agent's prompts and structured-output handling are welded to M3's behavior and a swap becomes a rewrite.
2. **Agent Interface roadmap** (`docs/ROADMAP.md` §3): chat is being upgraded from rule-based intent dispatch to a tool-calling agent layer. M3's native function-calling reliability is unverified (spike scheduled); an interface lets us swap between "native tool calling" and "structured-output simulated tool calling" without touching agents.
3. **Transparent metering** (ROADMAP P0-2): cost accounting requires capturing token usage at a single choke point — today `clients/minimax.py` discards the API `usage` fields entirely.

**Decision**:
1. Introduce a thin provider interface with two methods: `generate_structured(prompt, schema)` and `chat_with_tools(messages, tools)`. Agents depend on the interface, not on the MiniMax client; `clients/minimax.py` becomes the first adapter.
2. This is **not** a multi-model strategy: M3 remains the default and only configured provider (ADR-003 unchanged). The interface exists for swap-ability and metering, not for running multiple providers concurrently.
3. Usage capture is part of the interface contract: every call records tokens / latency / cost onto the owning `WorkflowRun` row.

**Consequences**:
- `MiniMaxAgentBase` (`app/agents/base.py`) is refactored to depend on the interface; M3-specific quirks (prompt idioms, structured-output retry behavior) live in the MiniMax adapter.
- ADR-004's framework rejection is **not** re-opened — orchestration stays hand-rolled; only the model-access seam is abstracted.
- If the M3 tool-calling spike fails, `chat_with_tools` is implemented via structured-output simulation behind the same interface.

**Related**: ADR-003, ADR-004, `docs/ROADMAP.md` §3

## ADR-026: AI 内容标识分级策略——合成轨道强制 C2PA，纯剪辑豁免，分类器自动判定

**Status**: Decided (2026-07-21)

**Context**: EU AI Act Art.50（2026-08-02 生效，新部署系统无宽限）要求 AI 生成/操纵内容带机器可读标识。平台侧 2026 年现状：LinkedIn 纯靠 C2PA 自动检测打 "CR" 标（无手动开关、发布 API 无披露字段）；TikTok 对四类内容强制标记（合成人脸/**声音克隆**/AI 背景/拟真产品），C2PA 自动检测兜底，漏标有四级处罚（警告→限流→封禁），被追标内容另有 12–48h 分发冻结。我们的产品里内容分两类：(a) 真实演讲素材的剪辑+字幕（标准编辑，非合成内容）；(b) 含合成轨道的内容——dub 声音克隆配音（已上线，`POST /clips/{id}/dub`）、AI 生成视觉（intro/outro/配图）。七家视频再利用竞品全部未做机器可读标识（structural 缺席，见 STRATEGY §2.3）。

**Decision**:
1. **分级，但分类器自动判定、不靠用户勾选**：渲染服务从 clip-spec 判定——spec 含合成轨道（dub 音轨 / AI 生成视觉）→ 产物嵌 C2PA Content Credentials + 发布界面披露提示 + `Publication.ai_disclosure=true`；纯剪辑+字幕 → 不嵌、不提示。用户永远不回答"这是不是 AI 生成"，也就不会答错。
2. **纯剪辑豁免**：真实素材的剪切、字幕、字幕翻译属标准编辑，不落入合成内容标记义务；LinkedIn 文案类（AI 撰写）依 Art.50(4) 的人工审核豁免——审核队列默认全员强制人工确认（2026-07-21 决策）恰好构成该豁免所需的 editorial control。
3. **不做全量标识**：尊重"标识是披露不是装饰"的平台语义——给明显非合成的内容贴 AI 标会稀释标识可信度，也误伤纯剪辑内容的分发。

**Consequences**:
- dub 是唯一"已上线且强制标记"的功能：C2PA 嵌入链路须在 2026-08-02 之后的首个部署前落地；ROADMAP P0-1 范围收窄为"合成轨道检测 + C2PA 写入"，纯剪辑产物零负担。
- 分类规则集中在 clip-spec 扩展字段（合成轨道标记），render 服务一处写入，Distribution 只读结果——符合"合规横切切面不分散"（MODULE_ARCH §5 规则 5）。
- TikTok 直发上线时由审核队列人工确认标识状态；若 TikTok Content Posting API 后续暴露 AI 标识字段，适配器接入。
- 差异化叙事保留：标识自动化 + 分级精确本身成为机构采购的合规卖点。

**Related**: `docs/ROADMAP.md` §7、§5；`docs/MODULE_ARCHITECTURE.md` §5 规则 5；`docs/STRATEGY.md` §2.3

## ADR-027: 发布审核分级——个人免审秒发，机构强制人工确认（P2）

**Status**: Decided (2026-07-22；翻案 2026-07-21 "默认全员强制人工确认")

**Context**: 2026-07-21 曾定"发布前默认全员强制人工确认"（ROADMAP §5、DISTRIBUTION §5）。用户实测指出：payload 本就预填进发布对话框供修改，个人作者再去第二个页面点"通过"是纯摩擦（"作为用户我还自己审核一次吗"）。审核的真实位置是**发布对话框本身**——编辑即确认。

**Decision**:
1. **个人账号（P1）**：无审核态，发布流 `draft → scheduled → publishing → published`，秒发；确认点 = 发布对话框（payload 预填可编辑 + `ai_disclosure` 徽标可见）。
2. **机构/团队账号（P2，团队工作区上线时）**：启用 `pending_review` / `approved` 状态，审核人 ≠ 作者，队列成为审核人的工作地点。
3. `pending_review` / `approved` 保留在 schema 与状态机中，标注"机构模式专属"；P1 实现与 UI 均不出现。

**Consequences**:
- ADR-026 中"审核队列构成 Art.50(4) editorial control"的论据改指**发布对话框内的人工确认**（payload 可编辑 + 披露徽标可见），效力相同。
- `publication_events` 个人流事件序列简化（无 submitted/approved）；机构模式恢复完整。
- ROADMAP §5 审核队列行移至 P2（与团队工作区同行）；DISTRIBUTION §5/§11 按本文改写。

**Related**: ADR-026；`docs/DISTRIBUTION.md` §3.3/§5/§11；`docs/ROADMAP.md` §5

## ADR-028: RunPlan 持久化——计划图作为一等对象（内化 flow，不做 Flow 产品）

**Status**: Decided (2026-07-22)

**Context**: 生成计划今天是**易失的**：`ContentPlan` 是单趟 LLM pass 产出的内存对象（`agents/content_director.py`），跑完即焚；`workflow_runs.current_step` 是裸字符串、`context` 是无结构 JSON blob（`tables.py:234-235`）。`clips`/`derivatives` 有 `workflow_run_id`（run 级血统，带 `ondelete="SET NULL"`）但没有节点级血统——"只重跑选段、保留文案"在结构上不可能，重跑单位是整个 run。ElevenCreative Flows（`research/elevencreative.md`）证明 DAG 是生成编排的成熟形态（显式节点图、@ 引用类型化槽位、节点级重跑、一键成模板），但那是卖给操作员的画布产品，不是我们的物种形态。同时三个已排期事项暴露同一个缺口：**P0 成本计量**（ADR-025 约定 usage 落 WorkflowRun，但 run 内没有步骤身份可归属）、**Operation Model**（生成侧操作"带指令重跑这步"需要节点地址）、**配方 = run-plan 模板**（STRATEGY §5，需要可序列化的计划结构，否则配方永远只是参数包）。

**Decision**:
1. **内化 flow，不做 Flow 产品**：DAG 是内部表征——agent 当编排者，用户看步骤清单（每步状态/成本/重跑入口）；不做节点画布 UI、不向用户暴露模型名、不做自由 DAG 编辑。
2. **`plan_nodes` 独立表**（否决 `workflow_runs.plan` JSONB 方案）：(a) 节点状态是高频并发写——并行节点完成时各自回写，JSONB 整文档读-改-写会丢更新；(b) 血统需要真外键，JSONB 里的"节点 id"只是约定字符串；(c) 成本聚合（`avg(cost) by kind`，成本预估的查询形状）是行级查询。节点的不透明载荷（模型参数、instruction）放 `spec` JSONB 列。新表按契约登记 MODULE_ARCH §4（Owner: Pipeline）。
3. **节点级血统**：`clips`/`derivatives` 加 `plan_node_id`（`ondelete="SET NULL"`，沿用 `workflow_run_id` 先例）。解锁：步骤级重跑、逐节点成本归属、编辑痕迹回流的 join 键。
4. **多趟规划自然化**：plan 是图之后，"分析 → 覆盖 → 各格式规划"成为图的多层；覆盖问责（哪个论点未被任何资产使用、两条 clip 是否撞同一论点）成为 plan 的一等字段（ROADMAP §1）。
5. **与 P0 计量钩子同源**：usage 先按 step-name 记（零迁移成本），`plan_nodes` 落地后切换到 node id；ADR-025 第 3 条"usage 落 WorkflowRun 行"修订为"落 `plan_nodes` 行，run 级成本为聚合视图"。

**Consequences**:
- 步骤级重跑（只重跑选段保留文案、只重跑 dub 不动画面）结构上成为可能；`derivative_dispatch` 的按类型粗粒度寻址逐步被节点寻址取代。
- 成本预估（ROADMAP §8 P1）获得查询形状：历史 `plan_nodes` 按 kind 聚合出每步均值，估价 = 逐节点求和。
- 配方模板（STRATEGY §5）获得序列化对象：run-plan 模板 = DAG 定义 + 类型化输入槽位。
- `workflow_runs.current_step` 退役为查询（`plan_nodes WHERE run_id=X AND status='running'`），run 行只管 run 级状态机。
- 用户侧永不见 DAG 画布；步骤清单是唯一呈现形态（DECISION_MATRIX §F"节点编排画布"行：对内采纳、对外放弃）。

**Amendment（2026-07-22）**：Consequences 中"用户侧永不见 DAG 画布"修正为——**画布不作前门**；P2+ 增加以读为主的**运行图检视面**（触发条件：机构模式"管得住"信任需求 + 虚拟产物时代混合图/变体使线性清单失效），无接线、无模型名、非图编辑。依据：ElevenCreative 自身为双界面结构（composer 前门 + Flows 收侧边栏，`research/elevencreative.md` §1/§3）——画布对我们是信任工具，不是创作工具。排期见 ROADMAP §3"运行图检视面"行。

**Related**: ADR-016（clip-spec 契约不动）、ADR-025（provider 抽象与计量）、`docs/MODULE_ARCHITECTURE.md` §2.1/§4、`docs/STRATEGY.md` §2.5/§5、`docs/research/elevencreative.md`、`docs/ROADMAP.md` §1/§2

## ADR-029: 双链并列——AI 生成结果以 RunPlan 新节点类型进入，虚拟产物独立成族

**Status**: Decided (2026-07-22)

**Context**: 2026-07-22 确认战略终态：AI 生成结果必做，形态 = **persona 驱动虚拟产物**（identity-driven），非 Factory 通用生成（STRATEGY §2.2）。分界澄清：clip 线主轨永远是"时间轴上的记录"（选段/trim/hidden 语义预设了已拍素材）；虚拟内容以**轨道级**在 clip 内合法存在（dub 声音克隆、AI 音乐、片头尾卡，ADR-026 管辖）；主轨本身生成的产物**不是 clip**——没有"从素材选段"的语义，其"编辑"是重掷/选变体而非修剪。问题：results 链需要独立的 agent 链路吗？

**Decision**:
1. **双链并列，禁第二条编排链**：虚拟产物生成 = RunPlan 新 node kind（`avatar_gen` / `synth_visual` / `voice_gen`，provider=媒体、异步 begin/await），与 clip 节点共享 `plan_nodes` / worker / 成本汇总 / 步骤清单。**混合图合法**：一次 fortnight 规划可同时产出 clip 与虚拟产物（覆盖节点按内容性质分配产线）。
2. **虚拟产物独立成族**：新输出表（与 `clips` 平级，落地时按契约登记 MODULE_ARCH §4），不进 `clips`、不进 clip-spec；包装层（字幕/品牌框）可复用 Remotion 渲染器，但产物身份不是 Clip。**parity 承诺只覆盖确定性包装层**，生成部分无 parity（有方差），UI 文案不得混淆两者。
3. **三个扩展**：(a) 媒体 provider `begin_generation / await_generation` 接口（ADR-025 的兄弟接口，任务型：提交→轮询→取件）；(b) provenance 记录（虚拟产物行 + 生成谱系，供 ADR-026 分类器判定）；(c) persona 视觉身份 + 授权记录（GDPR / AI Act 肖像授权，机构采购必问）。
4. **节点语义差**：generate 节点带 `gate: variant_pick`（生成 N 变体、选定后下游才跑——"默认不阻塞"原则的唯一例外，因下游花真钱）；**每次尝试计价**，失败不扣费（ROADMAP §8）在生成节点从加分项变为生死项。
5. **图组装 presence-gating**：persona 视觉身份未录入，虚拟分支不进图（同 Distribution 的 presence-gating 原则）。
6. **类型化边 + provenance 边流**：selection 类节点输入类型 = "timeline-of-record"；虚拟产物边携带 generated 标记，合规节点读边判定 C2PA——ADR-026 从"读 clip-spec"升级为"读图的边"。

**Consequences**:
- DECISION_MATRIX §F"AI 视频生成"💡 后排不变，终态声明为 identity-driven 虚拟产物族；接入时 persona / Brand 原样复用（身份层在范式之上）。
- RunPlan（ADR-028）是双链公共地基；本 ADR 除新产物表外不新增架构层。
- chat 随 DAG 内核连带升级：dispatch 目标 = editor 操作 / 整体重生成 / plan 级（节点重跑·追加·参数），ChatCut 原则推广到计划层（CHAT_ARCHITECTURE 待写；ROADMAP §3）。
- 运行图检视面（ADR-028 Amendment）在虚拟时代从"可选深度面"变为必需——变体集与混合图是线性清单表达不了的。

**Related**: ADR-016、ADR-021、ADR-025、ADR-026、ADR-028（含 Amendment）；`docs/STRATEGY.md` §2.2/§2.5；`docs/research/elevencreative.md`；`docs/research/chatcut.md`；`docs/ROADMAP.md` §3
