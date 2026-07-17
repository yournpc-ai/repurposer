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

## ADR-023: Music becomes an AI-generated, asset-based library

**Status**: Proposed

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
