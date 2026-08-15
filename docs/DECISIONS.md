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
- Single model (MiniMax M3), no need for provider abstraction（模型访问 seam 后由 ADR-025 补上）
- 编排逻辑持续演进（今为 chat 编译 DAG，见 ADR-028 / ADR-039），自有编排器跟随成本最低
- Prompts need fine-grained control; framework templates may not be flexible enough
- White-box debugging is easier

**Future**: If the workflow becomes very complex, re-evaluate LangGraph or Pydantic AI.

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

## ADR-013: Internationalization, theme switching, and European market positioning

**Status**: Decided

**Context**: Repurposer targets the European knowledge-speaking market, while also needing to support light/dark theme switching and compliance requirements for European institutions.

**Decision**:
1. Use `i18next` + `react-i18next` for internationalization on the frontend.
2. **Default language is English**; user selection is written to the `repurposer-lang` cookie, restored by the client after refresh.
3. **Default theme is dark**; manual user switch is written to `localStorage`. The `system` preference is also treated as dark.
4. Theme switching uses the View Transition API with a circular reveal animation from the click position.
5. All icons use `lucide-react` uniformly.
6. **Product positioning: European knowledge experts who have content**（教授 / 研究者 / 讲师 / 高管——never assume the input is a speech）：core outputs 由用户点名（LinkedIn posts、quote cards、多语言版本、newsletters、vertical clips），核心渠道 LinkedIn / 机构网站 / 邮件通讯。
7. **Multi-language output is the entry ticket to the European market**: in addition to UI language, content generation must cover FR/DE/ES/IT and other major European languages.
8. **GDPR / EU data residency as a sales differentiator**: through Cast AI Kimchi's M3 EU deployment capability, provide optional EU data processing to meet the procurement threshold of European institutions.

**Rationale**:
- `i18next` is mature, type-constrainable, and fits the scale of this project.
- In SSR scenarios, fixing the first render to English + client-side cookie restoration avoids hydration mismatch.
- `localStorage` + anti-FOUC inline script prevents theme flashing.
- View Transition API provides native smooth animations on Chromium/Safari, with automatic degradation on Firefox.
- A unified icon library avoids style inconsistency and manual SVG maintenance.
- The European knowledge-expert market is a whitespace not well covered by OpusClip/Descript; LinkedIn is the core B2B knowledge dissemination channel; multi-language and GDPR compliance are hard requirements.

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
6. **ASR (word-level timestamps) upgraded from optional P1 to hard prerequisite**; video needs to be **streamable/seekable**（本地 FS + FastAPI Range 起步；持久文件现全量归对象存储，见 ADR-024）。Without ASR + playable video, the editor cannot be built.

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

---

## ADR-023: Music becomes an AI-generated, asset-based library

**Status**: Implemented

**Context**: 默认配乐若依赖人工采集或用户上传的音频文件，版权状态不可控——Opus Pro 类工具频繁出现 "license expiry" 告警，用户上传曲目引入法律责任。同时 MiniMax（及其他 provider）已提供音乐生成 API，可以按需产出原创、平台安全的背景音乐。

**Decision**:
1. **Default music is AI-generated and stored in a dedicated `music` table**: three pre-generated music pieces (`calm`, `uplifting`, `corporate`) are seeded as `Music` rows at application startup. Audio objects live in S3-compatible object storage under `music/`; structured metadata lives in the `music` table.
2. **Music defaults by music id, not mood strings**: 配方注册表 / 任务书默认携带默认曲目 id（ADR-038 后 `brand_templates` 退役，音乐默认属工艺配置，不进人设）。
3. **Clip skill selects music per clip**: based on the configured default, the director's mood suggestion, and the clip's content tone, an existing music piece is picked. No music generation API is called during clip generation.
4. **Chat/Editor can regenerate music**: explicit user requests trigger MiniMax music generation, creating a new `Music` and updating `outputs.render_spec.music`. The clip is then re-rendered.
5. **Render contract unchanged**: Remotion still consumes `spec.music.url` and `spec.music.enabled`.
6. **User uploads deferred**: AI-generated music covers MVP needs. Uploaded music may be added later with explicit rights attestation, private-by-default visibility, and a takedown process.

**Rationale**:
- Eliminates platform copyright risk for default and chat-generated music.
- Keeps generation fast and cheap by selecting from pre-generated music pieces instead of generating per clip.
- Makes music a clip-level creative decision rather than a static brand setting.
- Uses a dedicated `music` table because the `Asset` table requires every row to belong to a `project_id` or `persona_id`, which does not fit global/shared music library items.

**Consequences**:
- All music objects live in object storage; PostgreSQL stores only keys and metadata.
- Custom music generation is more expensive than selection, so quotas or paid tiers may be needed.
- MiniMax (or chosen provider) usage terms must explicitly allow commercial use and redistribution.

**Related documents**:
- `docs/MUSIC_ARCHITECTURE.md` (detailed design, flows, data model, phases, copyright strategy)
- `docs/VIDEO_EDITOR.md` (`render_spec.music` contract)

**Related files**:
- `apps/api/app/models/schemas.py` (`MusicResponse`, `MusicGenerateRequest`, `MusicMetadataUpdate`, `ClipMusic`)
- `apps/api/app/models/tables.py` (`Music`)
- `apps/api/app/tools/music.py`（曲目解析/选择）
- `packages/clip/src/types.ts` (`ClipMusic`)

## ADR-024: Object storage (Volcengine TOS) for all persistent files

**Status**: Implemented

**Context**: 早期本地文件方案把文件服务绑死在 API 宿主机磁盘上、阻塞多实例部署，还把上传素材与仓库 checkout 混在一起。音乐库（ADR-023）已假定对象存储。本地 `assets/` 与 `data/` 目录已从仓库移除。

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
2. **Agent Interface roadmap**: chat is being upgraded from rule-based intent dispatch to a tool-calling agent layer. M3's native function-calling reliability is unverified (spike scheduled); an interface lets us swap between "native tool calling" and "structured-output simulated tool calling" without touching agents.
3. **Transparent metering**: cost accounting requires capturing token usage at a single choke point — today `clients/minimax.py` discards the API `usage` fields entirely.

**Decision**:
1. Introduce a thin provider interface with two methods: `generate_structured(prompt, schema)` and `chat_with_tools(messages, tools)`. Agents depend on the interface, not on the MiniMax client; `clients/minimax.py` becomes the first adapter.
2. This is **not** a multi-model strategy: M3 remains the default and only configured provider (ADR-003 unchanged). The interface exists for swap-ability and metering, not for running multiple providers concurrently.
3. Usage capture is part of the interface contract: every call records tokens / latency / cost onto the owning `WorkflowRun` row.

**Consequences**:
- `MiniMaxAgentBase`（后归一为 `app/agents/base.py` 的 Agent 漏斗，ADR-039）is refactored to depend on the interface; M3-specific quirks (prompt idioms, structured-output retry behavior) live in the MiniMax adapter.
- ADR-004's framework rejection is **not** re-opened — orchestration stays hand-rolled; only the model-access seam is abstracted.
- If the M3 tool-calling spike fails, `chat_with_tools` is implemented via structured-output simulation behind the same interface.

**Related**: ADR-003, ADR-004, ADR-039

## ADR-026: AI 内容标识分级策略——合成轨道强制 C2PA，纯剪辑豁免，分类器自动判定

**Status**: Decided (2026-07-21)

**Context**: EU AI Act Art.50（2026-08-02 生效，新部署系统无宽限）要求 AI 生成/操纵内容带机器可读标识。平台侧 2026 年现状：LinkedIn 纯靠 C2PA 自动检测打 "CR" 标（无手动开关、发布 API 无披露字段）；TikTok 对四类内容强制标记（合成人脸/**声音克隆**/AI 背景/拟真产品），C2PA 自动检测兜底，漏标有四级处罚（警告→限流→封禁），被追标内容另有 12–48h 分发冻结。我们的产品里内容分两类：(a) 真实演讲素材的剪辑+字幕（标准编辑，非合成内容）；(b) 含合成轨道的内容——dub 声音克隆配音（已上线，`POST /clips/{id}/dub`）、AI 生成视觉（intro/outro/配图）。七家视频再利用竞品全部未做机器可读标识（structural 缺席，见 STRATEGY §2.3）。

**Decision**:
1. **分级，但分类器自动判定、不靠用户勾选**：渲染服务从 clip-spec 判定——spec 含合成轨道（dub 音轨 / AI 生成视觉）→ 产物嵌 C2PA Content Credentials + 发布界面披露提示 + `Publication.ai_disclosure=true`；纯剪辑+字幕 → 不嵌、不提示。用户永远不回答"这是不是 AI 生成"，也就不会答错。
2. **纯剪辑豁免**：真实素材的剪切、字幕、字幕翻译属标准编辑，不落入合成内容标记义务；LinkedIn 文案类（AI 撰写）依 Art.50(4) 的人工审核豁免——发布对话框内的人工确认（payload 预填可编辑 + 披露徽标可见，ADR-027）构成该豁免所需的 editorial control。
3. **不做全量标识**：尊重"标识是披露不是装饰"的平台语义——给明显非合成的内容贴 AI 标会稀释标识可信度，也误伤纯剪辑内容的分发。

**Consequences**:
- dub 是唯一"已上线且强制标记"的功能：C2PA 嵌入链路须在 2026-08-02 之后的首个部署前落地；范围收窄为"合成轨道检测 + C2PA 写入"，纯剪辑产物零负担。
- 分类规则集中在 clip-spec 扩展字段（合成轨道标记），render 服务一处写入，Distribution 只读结果——符合"合规横切切面不分散"（MODULE_ARCH §5 规则 5）。
- TikTok 直发上线时由发布对话框人工确认标识状态；若 TikTok Content Posting API 后续暴露 AI 标识字段，适配器接入。
- 差异化叙事保留：标识自动化 + 分级精确本身成为机构采购的合规卖点。

**Related**: ADR-027；`docs/MODULE_ARCHITECTURE.md` §5 规则 5；`docs/STRATEGY.md` §2.3

## ADR-027: 发布审核分级——个人免审秒发，机构强制人工确认（P2）

**Status**: Decided (2026-07-22)

**Context**: 发布对话框本身已预填 payload 供编辑——编辑即确认。个人作者再去第二个页面点"通过"是纯摩擦（"作为用户我还自己审核一次吗"）；只有机构场景（审核人 ≠ 作者）才需要独立的审核队列。审核的真实位置是**发布对话框本身**。

**Decision**:
1. **个人账号（P1）**：无审核态，发布流 `draft → scheduled → publishing → published`，秒发；确认点 = 发布对话框（payload 预填可编辑 + `ai_disclosure` 徽标可见）。
2. **机构/团队账号（P2，团队工作区上线时）**：启用 `pending_review` / `approved` 状态，审核人 ≠ 作者，队列成为审核人的工作地点。
3. `pending_review` / `approved` 保留在 schema 与状态机中，标注"机构模式专属"；P1 实现与 UI 均不出现。

**Consequences**:
- `publication_events` 个人流事件序列简化（无 submitted/approved）；机构模式恢复完整。
- Art.50(4) editorial control 由发布对话框内的人工确认构成（见 ADR-026）。

**Related**: ADR-026；`docs/DISTRIBUTION.md` §3.3/§5/§11

## ADR-028: RunPlan 持久化——计划图作为一等对象（内化 flow，不做 Flow 产品）

**Status**: Decided (2026-07-22)

**Context**: 生成计划今天是**易失的**：`ContentPlan` 是单趟 LLM pass 产出的内存对象（`agents/content_director.py`），跑完即焚；`workflow_runs.current_step` 是裸字符串、`context` 是无结构 JSON blob（`tables.py:234-235`）。`clips`/`derivatives` 有 `workflow_run_id`（run 级血统，带 `ondelete="SET NULL"`）但没有节点级血统——"只重跑选段、保留文案"在结构上不可能，重跑单位是整个 run。ElevenCreative Flows（`research/elevencreative.md`）证明 DAG 是生成编排的成熟形态（显式节点图、@ 引用类型化槽位、节点级重跑、一键成模板），但那是卖给操作员的画布产品，不是我们的物种形态。同时三个已排期事项暴露同一个缺口：**P0 成本计量**（ADR-025 约定 usage 落 WorkflowRun，但 run 内没有步骤身份可归属）、**Operation Model**（生成侧操作"带指令重跑这步"需要节点地址）、**配方 = run-plan 模板**（STRATEGY §5，需要可序列化的计划结构，否则配方永远只是参数包）。

**Decision**:
1. **内化 flow，不做 Flow 产品**：DAG 是内部表征——agent 当编排者，用户看步骤清单（每步状态/成本/重跑入口）；不做可操作节点画布、不向用户暴露模型名、不做自由 DAG 编辑（用户面图形态的后继裁决见 ADR-035 / ADR-036）。
2. **`workflow_steps` 独立表**（否决 `workflow_runs.plan` JSONB 方案）：(a) 节点状态是高频并发写——并行节点完成时各自回写，JSONB 整文档读-改-写会丢更新；(b) 血统需要真外键，JSONB 里的"节点 id"只是约定字符串；(c) 成本聚合（`avg(cost) by kind`，成本预估的查询形状）是行级查询。节点的不透明载荷（模型参数、instruction）放 `spec` JSONB 列。表按契约登记 MODULE_ARCH §4（Owner: Pipeline）。
3. **节点级血统**：产物行带 `workflow_step_id`（`ondelete="SET NULL"`，沿用 `workflow_run_id` 先例；产物表后统一为 `outputs`，ADR-030）。解锁：步骤级重跑、逐节点成本归属、编辑痕迹回流的 join 键。
4. **多趟规划自然化**：plan 是图之后，"分析 → 覆盖 → 各格式规划"成为图的多层；覆盖问责（哪个论点未被任何资产使用、两条 clip 是否撞同一论点）成为 plan 的一等字段。
5. **与计量钩子同源**：usage 落 `workflow_steps` 行，run 级成本为聚合视图（ADR-025 第 3 条的落点）。

**Consequences**:
- 步骤级重跑（只重跑选段保留文案、只重跑 dub 不动画面）结构上成为可能；按类型的粗粒度派发逐步被节点寻址取代。
- 成本预估获得查询形状：历史 `workflow_steps` 按 kind 聚合出每步均值，估价 = 逐节点求和（ADR-039 的 estimate 系统落于此）。
- 配方模板获得序列化对象：run-plan 模板 = DAG 定义 + 类型化输入槽位。
- `workflow_runs.current_step` 退役为查询（`workflow_steps WHERE run_id=X AND status='running'`），run 行只管 run 级状态机。
- 用户侧永不见**可操作** DAG 画布（ADR-035 第 2 条永久拒绝）；用户面图形态 = FlowView 渲染的只读图（配方流程图 / 结果画布 / 复核中的血缘板，ADR-035/036/041）。

**Related**: ADR-016（clip-spec 契约不动）、ADR-025（provider 抽象与计量）、ADR-035 / ADR-036（用户面图形态）、`docs/MODULE_ARCHITECTURE.md` §2.1/§4、`docs/STRATEGY.md` §2.5/§5、`docs/research/elevencreative.md`

## ADR-029: 双链并列——AI 生成结果以 RunPlan 新节点类型进入，虚拟产物独立成族

**Status**: Decided (2026-07-22)

**Context**: 2026-07-22 确认战略终态：AI 生成结果必做，形态 = **persona 驱动虚拟产物**（identity-driven），非 Factory 通用生成（STRATEGY §2.2）。分界澄清：clip 线主轨永远是"时间轴上的记录"（选段/trim/hidden 语义预设了已拍素材）；虚拟内容以**轨道级**在 clip 内合法存在（dub 声音克隆、AI 音乐、片头尾卡，ADR-026 管辖）；主轨本身生成的产物**不是 clip**——没有"从素材选段"的语义，其"编辑"是重掷/选变体而非修剪。问题：results 链需要独立的 agent 链路吗？

**Decision**:
1. **双链并列，禁第二条编排链**：虚拟产物生成 = RunPlan 新 node kind（`avatar_gen` / `synth_visual` / `voice_gen`，provider=媒体、异步 begin/await），与 clip 节点共享 `workflow_steps` / worker / 成本汇总 / 步骤清单。**混合图合法**：一次 fortnight 规划可同时产出 clip 与虚拟产物（覆盖节点按内容性质分配产线）。
2. **虚拟产物独立成族**：虚拟产物 = **`outputs` 统一表的类型 + `provenance=generated`**（ADR-030）——不进 clip-spec、parity 承诺只覆盖确定性包装层（字幕/品牌框可复用 Remotion 渲染器），生成部分无 parity（有方差），UI 文案不得混淆两者。
3. **三个扩展**：(a) 媒体 provider `begin_generation / await_generation` 接口（ADR-025 的兄弟接口，任务型：提交→轮询→取件）；(b) provenance 记录（虚拟产物行 + 生成谱系，供 ADR-026 分类器判定）；(c) persona 视觉身份 + 授权记录（GDPR / AI Act 肖像授权，机构采购必问）。
4. **节点语义差**：generate 节点带 `gate: variant_pick`（生成 N 变体、选定后下游才跑——"默认不阻塞"原则的唯一例外，因下游花真钱）；**每次尝试计价**，失败不扣费（PROGRESS 成本线）在生成节点从加分项变为生死项。
5. **图组装 presence-gating**：persona 视觉身份未录入，虚拟分支不进图（同 Distribution 的 presence-gating 原则）。
6. **类型化边 + provenance 边流**：selection 类节点输入类型 = "timeline-of-record"；虚拟产物边携带 generated 标记，合规节点读边判定 C2PA——ADR-026 从"读 clip-spec"升级为"读图的边"。

**Consequences**:
- DECISION_MATRIX §F"AI 视频生成"💡 后排不变，终态声明为 identity-driven 虚拟产物族；接入时 persona / 皮肤原样复用（身份层在范式之上）。
- RunPlan（ADR-028）是双链公共地基；本 ADR 不新增架构层（产物 = `outputs` 类型，零新表）。
- chat 随 DAG 内核连带升级：dispatch 目标 = editor 操作 / 整体重生成 / plan 级（节点重跑·追加·参数），ChatCut 原则推广到计划层（CHAT_ARCHITECTURE）。
- 图检视面随 FlowView 落地（ADR-035/036）；虚拟时代的变体集与混合图更非线性清单所能表达。

**Related**: ADR-016、ADR-025、ADR-026、ADR-028；`docs/STRATEGY.md` §2.2/§2.5；`docs/research/elevencreative.md`；`docs/research/chatcut.md`

## ADR-030: 产物统一为 outputs——clip 降级为类型，payload schema 注册表守门

**Status**: Decided (2026-07-22)

**Context**: 产物劈成两张表：`clips`（元数据富：发布套件 title/desc/hashtags/cover/topic + render 管线）与 `derivatives`（穷人版：content JSON + image_url）。三个不对称（元数据 / 管线 / 扩展成本）导致：Distribution 双 FK+CHECK、verifier 分数无处放、发布对话框两套表单、新输出类型要 enum 迁移+特判（quotes 图片就是这样来的）。统一词汇其实早已存在——`generation.py` 的 `KNOWN_OUTPUTS` 已把它们统称 outputs，schema 没跟上。破坏性更新（不保留数据）给了合并窗口。

**Decision**:
1. **统一 `outputs` 表**，`clips`/`derivatives` 退役。通用列：`id / project_id / plan_node_id（血统）/ type / language / status / provenance(real|generated) / payload JSONB / files JSONB / source_ref JSONB? / render_spec JSONB? / render_status? / score JSONB? / publishing JSONB`。
   - clip = 带 `source_ref`（时间轴语义）+ `render_spec`（渲染管线）的那一类；Editor 照旧只认 `type=clip`。
   - `render_status` 保持顶级列（worker 认领谓词），NULL = 未请求渲染（语义沿用）。
   - **产物类型注册表 = 节点类型注册表**（加一种节点自动有产物位）。
2. **三条 payload 规则**（防 god-table，可评审可执行）：
   - 规则 1：**默认进 payload，schema 注册表守门**——`OUTPUT_PAYLOAD_SCHEMAS`（type→BaseModel），写入 `model_dump()`、读取 parse 回 typed model（沿用 render_spec/ClipSpec 的"JSON 列 + Pydantic 契约"先例）；
   - 规则 2：**要查的字段升级为列**——需要 SQL 谓词/索引/认领的字段挣顶级列（`render_status` 是先例）；
   - 规则 3：**通用列只收跨类型字段**——对 ≥2 类型或横切机制（合规/计量/分发）有意义的才配（plan_node_id / provenance / score / publishing）。
3. **Distribution 单 FK**：`publications.output_id`，双 FK + CHECK（`ck_pub_target_*`）退役。
4. **verifier 的家**：`score JSONB`（分数+理由+维度）——P0-3 分数落库落定于此。

**Consequences**:
- ADR-029 的虚拟产物随本条落为 outputs 的类型 + provenance（见 ADR-029 第 2 条）。
- 新输出类型（newsletter / avatar 视频）= 新节点类型 + payload schema 注册，零表迁移。
- MODULE_ARCH §4 登记 outputs（Owner: Pipeline）；数据架构图见 §2.2。
- payload 的"类型安全"未丢——从 DB 层移到 schema 层（Pydantic 校验强于 SQL CHECK）。

**Related**: ADR-016、ADR-026、ADR-028、ADR-029；`docs/DISTRIBUTION.md` §3；`docs/AGENT_ARCHITECTURE.md`；`docs/tasks/done/runplan-persistence.md`

## ADR-031: 渠道凭证应用级加密——Fernet + env key

**Status**: Decided (2026-07-23)

**Context**: Distribution 的 `channel_accounts.credentials_enc` 存 OAuth token（可代用户发帖的钥匙），泄露路径 = DB dump / 备份外泄 / 只读账号误授权。DISTRIBUTION.md §14 开放问题 2 要求随表结构落地时定案：Fernet + env key vs KMS。

**Decision**:
1. **字段级对称加密**：`credentials_enc` JSONB 中敏感值（`access_token` / `refresh_token`）以 Fernet（AES-128-CBC + HMAC）加密存储，key 来自 env `CHANNEL_CREDENTIALS_KEY`（`Fernet.generate_key()` 生成，dev/prod 各一，入 secret 管理不入 git）。
2. **空 key = 明文（仅 dev）**：本地开发不配 key 时明文存储 + warning 日志；prod 必须配置（上线检查清单项）。
3. **解密容忍明文**：读取遇 `InvalidToken` 按明文原样返回并记 warning——dev 期明文行与 key 轮换窗口不打断服务。
4. **KMS 后排**：EU 驻留 / 机构采购阶段再迁 KMS——加密边界不变（字段级），迁移 = 换 key 提供方 + 批量重加密。

**Consequences**:
- 只有 Distribution 服务持有加解密路径；API 响应模型永不包含 credentials。
- key 轮换 = 旧 key 解密 → 新 key 加密的批量任务；当前单 key 从简。

**Related**: ADR-026、ADR-030；`docs/DISTRIBUTION.md` §3.1/§14

## ADR-032: Operation Model——operations 表 + 快照式 undo + op 集边界

**Status**: Decided (2026-07-26)

**Context**: 编辑侧需要与 RunPlan（生成侧"步骤皆可寻址"）同构的地基：Editor GUI / chat /（未来）MCP 三个前端共用一本操作日志，支撑 undo（VIDEO_EDITOR.md 已承诺）、chat 细粒度修改（"删掉第二句"）与精修痕迹回流校准（MODULE_ARCH 回流边①）。CHAT_ARCH §9 只钉了 edit ops 边界，op 集合与存储形态待定。关键设计问题：undo 用逆运算还是快照；op 集合的边界划在哪。

**Decision**:
1. **`operations` 表**（Owner: Operation Model）：`output_id / project_id / seq / op / params JSONB / spec_after JSONB / spec_hash / source / user_id? / message_id? / undone_at? / created_at`，`UniqueConstraint(output_id, seq)`。append-only，`undone_at` 可空时间戳是唯一可写字段（NAMING §1 宪法第 4 条）。
2. **快照式 undo**：每行存应用后的完整 render_spec 快照（`spec_after`）+ 语义化 `op`+`params`；baseline 行（`op="snapshot", seq=0`）懒创建，不变式"op N 的 before = op N-1 的 spec_after"。否决逆运算模型：LLM op（translate/dub）无可计算的逆；`removeRange` 在 spec 内真删 caption cues，逆运算无法复活；redo 需要 after 态。params 保留语义信号供校准回流，快照提供机械保证——两者各司其职（Git 存 tree、diff 派生的同构）。
3. **op 集边界**：operations 表只装**产物级** op（remove_range / set_trim / set_title / set_caption_style / set_music / set_crop / set_spec(system 内部) / restore_version / translate_captions / set_dub）；**plan 级 op（set_node_params / regenerate_node / swap_slot）归 RunPlan 小拓扑，两家族分开登记**。否决 `restore_range` 独立 op（NAMING 判例 N-16）：caption cues 不可复活，恢复语义全归快照层。
4. **写纪律**：render_spec 的一切修改必须经 `operations/service.py`（MODULE_ARCH §4"内容字段修改必须能产生 operation 记录"的代码化）；`PUT /outputs/{id}` 的 render_spec 整包替换分支删除（破坏性升级，无过桥层）；漂移自愈——hash 链校验失败时自动补 `set_spec`（source=system）行，日志永不谎称现状。
5. **并发**：应用事务内 `SELECT ... FOR UPDATE` + 客户端 `base_hash` 乐观校验（409）；批量原子应用（editor Save 模型的自然形态）。

**Consequences**:
- undo/redo/版本跳转对所有 op 类型统一成立（含 LLM op）；存储代价 ≈15–30KB/op，可接受，未来可按 spec_hash 内容寻址去重（schema 不变）。
- chat `EditOpsProposal` 从"回边界文案"升级为真应用（chat-loop-v2 P3）；EditOp schema 收紧为 registry 校验。
- editor 历史面板/版本时间线 UI 后置（反过度设计裁决）；undo 能力经端点 + chat 撤销按钮先行可用。
- 校准回流的读路径（按 project/op/时间窗聚合 params）落成文档座位，消费端后建。

**Related**: ADR-016（clip-spec 唯一契约）、ADR-028（RunPlan 同构对偶）、ADR-030（outputs 统一产物表）；`docs/tasks/done/operation-model.md`（D1–D7 全文）；`docs/MODULE_ARCHITECTURE.md` §2/§4

## ADR-033: 编辑面分层——能力层唯一（ops+skills 双海拔），适配层多前端并存

**Status**: Decided (2026-08-02)

**Context**: VIDEO_EDITOR.md 把编辑形态写成"文字稿编辑 + 单轨 trim"（editor GUI），CHAT_ARCH 曾把对话式精修写成"辅助入口，deferred"。现实是两条线都已发货且共用 Operation Model：clip editor 路由把手势翻成 ops（COALESCIBLE 合并连续 ops + `base_hash` 乐观锁），chat 把自然语言翻成 `EditOpsProposal`；run 级海拔（`dub_clip` / `translate_clip` / `remove_filler` / `add_music` / `revise_script` 等技能注册项）chat 经 task_list 派发、editor 经 Dub/Translate 按钮直连端点。用户裁决（2026-08-02）：编辑能力的方向是"操作作为 tools/skills，由 chat 引导 agent 执行"。这不是用 chat 取代 editor，而是需要把分层钉死，防止任一前端长出私有编辑逻辑。

**Decision**:
1. **能力层唯一，双注册表双海拔**：`OP_REGISTRY`（参数级微操作——纯函数 clip-spec→clip-spec，无 run，即时，快照/undo）∪ `SKILL_REGISTRY`（任务级宏操作 = 技能注册项——编译为图节点起 run；技能叙事与执行者构成见 ADR-039）。路由纪律维持现状并上升为契约：参数级走 ops，任务级走 task_list（`_validate_edit_ops` 拒收 precomputed ops，原话 "needs a run — propose a task_list"）。
2. **适配层多前端，全部薄转换**：适配器只做"输入形式 → 注册表调用"的翻译，**禁止自带编辑逻辑**。已发货：editor（手势 → ops HTTP）+ chat（自然语言 → EditOpsProposal / task_list）；预留：mcp（`SOURCE_REGISTRY` 座位已注册）。新增适配器 = 新增翻译层，能力层零改动。
3. **能力投资压能力层**：新编辑能力 = 新 op 或新 skill 注册项，全部适配器同时受益；禁止任何适配器私设能力种类（如 editor 独有的编辑类型）。
4. **chat 升格为正式编辑面**：不再是"辅助入口"；@-mention（recipe-mention 期 2）是其定向机制（@产物 → targeted ops / skills）。editor 不退场——精细手势（拖 trim、点字幕改字、框选删段）仍是其强项。

**Consequences**:
- VIDEO_EDITOR.md 的"编辑形式"旧表述修订：文字稿编辑 + 单轨 trim 是 editor 适配器的形态，不是产品编辑面的全部。
- L3 分工线不变：多轨/图层/B-roll 仍推给 CapCut/Premiere，不进能力层。
- chat 适配器的语义完备性成为产品面：morph/fork 选择权暴露、recipe 参数默认值化等归 chat 能力简报（入 PROGRESS 需求池）。
- "能力层 / 适配层"入架构词汇（NAMING §2）；新 op/skill 评审清单固定加一问："这是能力层成员，还是某适配器的呈现细节？"

**Related**: ADR-016（clip-spec 唯一契约）、ADR-028（RunPlan）、ADR-032（Operation Model——本条将其"三前端共用操作日志"的愿景钉为分层纪律）；CHAT_ARCH §9；`docs/tasks/recipe-mention.md` §2.5

## ADR-034: chat 回合流式——单调用流式 + 增量散文提取，Accept 协商落地

**Status**: Decided (2026-08-04)

**Context**: chat 回合是一次性 JSON：thinking 之后计划卡/散文瞬间弹出，感知突兀（手测 2026-08-03）。要做真流式，但 LLM 判定输出是结构化 JSON（PlanAgent / ChatIntentAgent verdict），整体必须到齐才能校验执行——"流式 JSON"本身不可渲染。两条候选：①双调用拆分（先散文后结构）——多一次 LLM 调用，延迟与成本翻倍，且散文与判定可能自相矛盾；②**单调用流式 + 增量散文提取**——判定仍是同一 JSON 同一调用，服务端在字符流累积过程中提取散文字段增量作预览通道，信封照旧收尾。

**Decision**:
1. **单调用流式 + `ProseDeltaExtractor`**：verdict JSON 不变、校验不变、metering 不变（`stream_options.include_usage`）；`stream_extract.py` 状态机从累积字符流中提取散文 key（plan path `answer`，chat loop `text`/`summary`）的解码增量。提取失败一律静默降级为整包落地（dead 锁存）——流式是纯预览通道，信封永远权威。
2. **Accept 协商 rollout**：`POST /chat` 按 `Accept: text/event-stream` 分流 SSE / JSON，JSON 路径逐字节不变——harness、旧前端、剧本零改动，可随时回退。SSE 帧：`assistant.delta`（0..N）→ 恰好一帧终态（`turn.completed` = 完整 ChatResponse / `turn.failed`）。
3. **prompt 配合**：两个 agent 的 system prompt 加"散文字段放第一个 key"——否则 tasks 数组生成完才出散文，流式收益大头丢失（Pydantic 校验与 key 序无关，安全）。
4. **前端 Streamdown 渲染**：assistant 散文（流式预览 + 静态历史）统一走 Streamdown——一次性解决 markdown 渲染缺口与流式中途不完整 markdown（未闭合 **/代码栅栏）的渲染闪烁；不引 AI SDK。`lib/chat-stream.ts` 禁自动重连（重试 POST 会重复落用户消息）。

**Consequences**:
- 计划卡类回合永远零 delta（结构化 JSON 不可增量渲染）——观感靠入场动画软化，不是缺陷。
- 基础设施坑两枚（已修并记录）：BaseHTTPMiddleware 栈下 SSE 生成器必须自开 session（runs.py 先例）；请求日志中间件**不得补丁 `_receive`**——`_CachedRequest` 的 body 缓存自动回放，补丁会在断连探测时喂出陈旧 http.request 触发 starlette "Unexpected message received"。
- 提取器成为散文流的唯一入口：新增 verdict 散文字段 = 注册新 target key，不得旁路。

**Related**: CHAT_ARCH §8.6；ADR-028（RunPlan）；`app/chat/stream_extract.py` 测试套件（逐位切分夹具）

## ADR-035: DAG 用户化三切——静态配方流程图采纳 / 可操作画布永久拒绝 / 运行期活图证据裁决

**Status**: Decided (2026-08-06)

**Context**: 2026-08-06 竞品 UI 评审（七组截图：Lovart 类单产物工作面 ×2、flow 类节点画布+流程智能体 ×2、ElevenCreative 配方 modal——含"流程"tab 静态 DAG、图片编辑 modal、gallery 检视 overlay→composer 回填）。行业收敛到"chat 前门 + 结构可见 + 单一连续面"，触发对本项目 DAG 用户化形态的复审。ADR-028 已决"内化 flow，不做 Flow 产品"（DAG 为内部内核，用户看步骤清单），但留了两扇窗：只读运行图检视面（P2+，混合图/机构信任两触发）与"DAG 编辑 go/no-go"待定项。评审中用户拍板了精修闭环的总原则：**"精修的对象模型是图，界面是语言——隐藏画布，意图识别把用户语言翻译成图操作"**（与 ADR-028 教义同构，并加三条精度：翻译两层——指认确定性/意图归 LLM；翻译失败 = ask 反问，图永不当错误信息；新可翻译操作 = registry 注册项，永不开新面）。在此原则下，DAG 的三种用户化形态必须分别裁决，不可一概而论。

**Decision**:
1. **静态配方流程图 = 采纳**。配方注册时作者策展的只读结构图（友好步骤名、固定结构、无模型名、不可接线），作为"它是怎么做的"堆叠项住进配方检视 overlay（闭环链第 2 周；flow 字段入 Recipe 数据 schema，RECIPES §7.1）。定位 = 说明书/信任件，回答"它拿我的素材做了什么"，不承担任何操作。
2. **可操作画布 = 永久拒绝**。接线/自由拓扑/节点运行按钮/节点模型 SKU 货架永不面向用户——那是操作员形态，与"到来即彷徨"的知识专家画像冲突；拓扑唯一来源维持 `compile_graph`（LLM 亦只准提议 task list）。本条关闭 PROGRESS 决策表中"DAG 检视/编辑 + 简单多轨是否投入"行的"编辑"半边；VIDEO_EDITOR 封存的 L3 分工线（多轨/图层/B-roll 归 CapCut/Premiere）不变。
3. **运行期活图 = 结果画布（ADR-041 终裁）**：单 run 拓扑在收官时一帧渲染为桌面默认中心——进度不进图，打勾流为唯一进度面；小白复述测试为转正复核门（不过则网格回退默认中心）。ADR-028 的"用户侧永不见 DAG 画布"自此修订为"用户侧永不见**可操作**画布"。
4. **模型货架拒绝的证据并入**：竞品画布在节点上摆模型选择器，同时提供"自动（低于 300 积分）"档位——连画布派自己都需要一个策略开关兜底。这佐证 2026-08-02 的 provider-UX 裁决（用户-facing = 策略开关如"优先 EU 托管模型"，不是 SKU 货架）：模型选择是成本/合规策略，不是用户的创作决策。

**Consequences**:
- 排期以 PROGRESS 为唯一事实源：活图 spike 收窄为血缘板升正裁决（ADR-036 第 4 条），不评估编辑，只评估展示。
- 新产物类型 / 新配方进入时，静态流程图随注册项一并策展（注册表纪律 +1 字段）；活图若升正，同一渲染器零浪费接管。
- 翻译失败 = ask 反问成为硬契约：意图识别覆盖率不足时永远多问一句，永不亮图兜底。

**Related**: ADR-028（RunPlan——本条修订其用户侧结论）、ADR-032（Operation Model）、ADR-033（编辑面分层——翻译两层的注册表纪律来源）；简报 `docs/tasks/results-canvas.md`；DECISION_MATRIX §F（画布行与配方 overlay 行证据）

## ADR-036: Flow 基座——只读图渲染扶正为共享能力

**Status**: Decided (2026-08-07)

**Context**: ADR-035 三切次日，dub 载体链的两个事实浮出：① 配方检视 overlay 首版实现把扇出数据包（1 源 → EN/ZH/FR/ES 四片对照包）渲成 tabs + 手风琴——图结构的信息被线性容器物理消灭（四条语言版本同一时刻只能见一条）；② 单 run 的 DAG 拓扑在 `compile_graph` 后固定、run 期间只有状态迁移——ADR-035 第 3 条所指"运行期活图"里真正有布局风险的不是 run 图（死图 + 状态动画），而是跨周增长的项目全史血缘；两者并为一件 spike 颗粒度过粗。用户拍板原话（2026-08-07）：**"这一期先只暴露只读图，但该连线的连线、该有的节点是节点；只能通过 chat 修改，不变。"**

**Decision**:
1. **FlowView = 共享只读图渲染基座**（`apps/web/src/components/flow/`），`packages/clip` 同款单一画笔纪律：配方流程图 / 结果画布 / 血缘板（复核门）三个消费面各自只做"领域数据 → nodes/edges"适配器，禁自绘边、禁自写布局。契约三要素：节点皮（asset / output / step）、双边语义（**lineage 血缘边** ⊥ **dependency 依赖边**，视觉可辨）、确定性分层布局（depth 分层，有界规模不虚拟化、不缩放）。
2. **只读是结构性的，内容不降级**：FlowView 不提供 drag / connect / pan / zoom props——"图不可编辑"（ADR-035 第 2 条）从约定升级为组件 API 物理缺席；同时每条边是真边（step `inputs` / `derived_from_output_id`）、每个节点是真节点，禁装饰性插画。
3. **结果画布 = 用户面 run 图的唯一形态**（2026-08-11 ADR-041 修订）：单 run 拓扑编译期定死，收官时一帧渲染终态为桌面默认中心——进度不进图，打勾流是唯一进度面（线性旁白与空间图同源 workflow_steps，分时复用不并存）。
4. **血缘板**：项目全史血缘 = 唯一无界图面；默认中心之问已由 ADR-041 终裁（结果画布升正），血缘板留作扩展视图候选。
5. **修改通道不变**：chat 是唯一修改通道；图面交互白名单 = 点选聚焦 / hover 血缘路径高亮 /（闭环链第 5 周）点节点插 `@workflow_step` mention 接三档重跑。

**Consequences**:
- 后端增量两处：`StepResponse.inputs` 下发（DAG 边表，单字段读容忍）；`GET /projects/{id}/lineage` 血缘投影端点（服务端解析唯一发生地）。
- DAG 的用户面形态 = FlowView 渲染的只读图（配方流程图 / 结果画布 / 复核中的血缘板）；可操作画布永不用户化（ADR-035 第 2 条）不变。

**Related**: ADR-035（运行期活图拆分裁决的母条）、ADR-028（RunPlan）、ADR-016（clip-spec 单一画笔先例——FlowView 是其图面同构）、ADR-041（结果画布升正——本条第 3/4 条与补记 1/3 的修订来源）；简报 `docs/tasks/results-canvas.md`

### 补记（2026-08-07，同日两轮用户拍板）

1. **缩放 = 导航，不是编辑**：ADR-035 第 2 条永久拒绝的是编辑手势（拖节点/接线/删加节点——拓扑唯一来源仍是 `compile_graph`）；缩放/平移/fit 是导航能力，**基座持有、按面门禁开放**：配方卡说明书（有界策展小图）fit-first 锁缩放；结果画布与血缘板开放 pan/zoom（2026-08-11 ADR-041 重划；minimap 退役——稀疏小图无导航价值）。
2. **引擎定 `@xyflow/react`**：缩放进基座后，pan/zoom/pinch/minimap/命中坐标换算正是手写最坑、最值得买的代码类——手绘分层方案在动工前作废（零沉没成本）。布局仍自算（确定性分层 + append-only 保序，库只做摆位与视口，不引 dagre——"chat 加节点，图只长不晃"论据不变）。交互白名单：`nodesDraggable=false` / `nodesConnectable=false` **常锁**（拓扑编辑手势物理缺席不变）。动工前置核查：React 19 兼容版本 / SSR client-only 挂载 / Tailwind v4 样式共存。
3. **过渡动画愿景（用户拍板："连线、node 的诞生、布局都有 transition，用户会感觉到优雅"）**：三层，每层都投影真实事件——**诞生编排**（结果画布揭幕时按 `seq` 编译序逐节点入场 + 边描画，是把真实编译顺序用缓动时间轴回放，不是剧场）；**状态动画**（running 脉冲 / 边流动指向待执行子节点，SSE 驱动）；**生长动画**（chat 拓扑编辑产生新节点时，新节点诞生 + 边描画）。禁令 #9 不破：动画永远是真实事件（编译序/状态迁移/真实生长）的投影，禁假进度；`prefers-reduced-motion` 降级为即时呈现；断线重连/历史打开不播诞生回放（只有会话内亲见收官才播）。

## ADR-037: 身份模块正名——Speaker 退役、人设（Persona）扶正，IP 留在承诺层

**Status**: Decided (2026-08-08)

**Context**: 产品定位升级后（知识专家任意素材，"never assume the input is a speech"），Speaker 命名三重断裂：① **语义前提崩塌**——"Speaker/演讲者"预设用户是演讲者、素材是演讲，而身份容器的主人是有内容的专家（会议/报告/播客/文字稿+照片）；② **一词三义撞车**——Speaker（用户身份画像）与排期中的 `speaker_map`（素材里"谁在说话"的分析节点，RECIPES §6）、landing 普通英文词 speakers 同词不同域，前两者即将共存于同一个 DAG；③ 旧裁决"Persona 只当概念词、不进表名路由"的前提是"Speaker 是对的实体名"——前提已不存在。同时用户给出产品的用户侧闭环：**管理 IP → 产生 outputs → 发布**（与工程侧"理解 → 生成 → 审校 → 分发"互为表里，STRATEGY §3 牌 1）——"管理 IP"是活动不是对象：今天该模块里用户唯一能操作的是身份理解（风格/受众/禁忌词/声纹），账号绑定与发布数据未落地（Distribution P1 / 数据回流 P2），以"IP"名之则第一天不诚实。

**Decision**:
1. **身份模块正名 = 人设（en `Persona`）**：多实例扁平（工作号/生活号 = 两个人设）；用户面 zh「人设」/ en「Persona」，代码层 `persona`（表 `personas`、`PersonaContext`、路由 `/personas`；节点 `persona_bootstrap` 名零改动）——三层同词族，无需双轨。人设 = **任务完成后沉淀的记忆**（语气/风格/禁忌词/声纹等稳定特征），行为规则：per-user 隔离（`user_id` 在表）；composer 可选选择、**未选则任务分析后 auto-create** 并挂到当前项目；多实例不强制单例；两层分工不变——人设 = 稳定风格记忆，项目 = 当次主题/意图 + 素材。
2. **`speaker` 让位素材域**：指"素材里说话的人"（纯数据层，用户不可见）；`speaker_map`（RECIPES §6）是该词的合法居民，保持原名落地。landing 的 "keynote speakers" 是普通英文词，不受影响。
3. **IP = 承诺层词，不进产品内导航**：对外叙事/landing 可讲"打造你的 IP / 自媒体"（zh）——IP 是整个 agent 的产出（账号+受众+内容+声誉），不是某个模块。**"IP" 禁入英文文案**（英语语境 IP = intellectual property，法律词）：en 叙事用 **personal brand**（LinkedIn/职业人群）/ **thought leadership**（知识专家语境）。营销文案按 locale 适配属正常；NAMING §2 中英唯一映射约束领域词汇，不管营销 slogan。
4. **stock voices 不伪装人设**（修订 RECIPES §5 裁决③的形态描述）：系统音色以"音色"身份进人设选择器的系统区（如 Rachel · Confident，带试听）；声纹 = 人设属性不变。
5. **迁移**：第一刀（全栈改名 `speakers`→`personas`：表 + Alembic 迁移 / schemas / `memory/routes.py` 端点 / persona skill / 前端路由与 i18n / composer 人设块）已于 08-09 落地；皮肤吸收（ADR-038）随插入周推进，排期以 PROGRESS 为准。现状事实源文档（MODULE_ARCHITECTURE / AGENT_ARCHITECTURE / NAMING §2）随代码迁移同步更新。

**Consequences**:
- 闭环叙事三层归档：对外/愿景 = 管理 IP → outputs → 发布（STRATEGY §2.2 落档）；产品内导航 = 人设 / composer / projects（/ 未来 Distribution）；工程层 = 理解 → 生成 → 审校 → 分发（STRATEGY §3 牌 1 不变）。
- `persona_bootstrap`"从源文本提取风格"隐含"素材 = 本人言论"假设；素材域扩展后需"本人含量"门禁（非本人素材不污染人设；`speaker_map` 落地后可升级为"只从用户本人段落学"）——随迁移在 persona skill 与 AGENT_ARCHITECTURE 补记。
- dub 声纹目标态（voice_id 缓存人设行、克隆一次跨项目复用）随插入周落地（08-11 `voice` 缓存 + STOCK_VOICES + dub 声纹优先级链）；声纹质量打磨见 PROGRESS 第四周。

**Related**: ADR-030（outputs 统一）、ADR-038（人设吸收 Brand）、RECIPES §5/§6、STRATEGY §2.2/§3、NAMING N-27

## ADR-038: 人设吸收 Brand——身份单对象化（brand_templates 退役，皮肤/工艺/格式三分流）

**Status**: Decided (2026-08-08)

**Context**: ADR-037 多人设拍板后，Brand 拆分的承重墙被反转——原理由"同一 Speaker 服务多个 Brand（大学官方号 vs 个人 IP）"在多人设下恰是**两个人设各带皮肤**的自然模型。边界早已渗漏：CTA / 语气双边同驻（brand config 有 default CTA，纪律却说 CTA 归 Speaker）；composer 双身份控件（人设块 + Brand pill）逼用户做无意义配对；IA 身份格由两个低存在感页面各撑一半。且 `brand_templates.config` 实为杂物抽屉：皮肤字段（caption 字体/颜色/preset、title、片头尾卡）与工艺开关（`removeFiller`/`captionEnabled`/`fillMode`）、产物格式默认（`aspect`）、音乐默认混居一袋——整体并入人设会误导含义，必须先按真实归属分流。

**Decision**:
1. **`personas` 终态 schema**（ADR-037 改名迁移与本条合并执行）：
   - 身份卡：`id / user_id / name / title? / avatar_url? / language`；
   - 风格块（flat 六件，现状平移）：`core_values / favorite_metaphors / sentence_style / emotional_tone / typical_hooks / avoid_words`；
   - 策略块（flat 三件）：`audience? / guidelines? / cta?`——**CTA 唯一家**（brand config 的 default CTA 归并于此）；旧 `voice` 文本列**删除**（含义双解：文风内容迁移时并入 `guidelines`）——`voice` 一词随即归还唯一合法含义（词汇表：voice = 音频本义）；
   - 声音块：`voice` JSONB NULL——`{"kind":"cloned","voice_id","sample_asset_id"}` | `{"kind":"stock","stock_id"}` | NULL = Auto；
   - 皮肤块：`brand` JSONB NULL——caption 字体/字号/颜色/位置/preset、title 开关+位置、片头尾卡、logo、keyword_highlighter；NULL = 系统默认皮肤；**块名沿用 `brand`，全栈一词**（人设块 / 烘焙 / clip-spec `brand` 段同名，§1）——模块退役，词不退役；不引入 `look` 字段名（RECIPES §4.4 的 look 层是"caption × title/intro × brand 参数"的组合概念，避免撞名）；
   - 来源与校准：`learned_from` JSONB NULL（asset hashes + 摘要，显化页"它从哪学的"）、`calibrated_at` ts NULL（最近校准，§4 可空时间戳）、`auto_created_at` ts NULL（系统 bootstrap 标记——**替代 is_default 布尔**）；
   - 审计：`created_at / updated_at`。
2. **`brand_templates` 表退役，config 三分流**：皮肤字段 → `persona.look`；工艺开关（`removeFiller` / `captionEnabled` / `aspect` / `fillMode` / 音乐默认）→ 配方注册表 / 任务书默认（`removeFiller` 本已是 op/skill，`aspect` 是产物格式）——**不进人设**；`language_tone` 不单独成字段（风格六件已覆盖）。
3. **引用平移**：`projects.brand_template_id` 退役（渲染时经 `persona_id` 解析）；composer payload `speaker_id + brand_template_id` → 单 `persona_id`；`GenerationContext.brand` ← `persona.brand`；`memory/brand.py` 烘焙改读人设（模块名不动）；**clip-spec `brand` 段不动**（渲染黑盒契约零破坏，ADR-016）。
4. **前端**：`/personas` 人设页 = 身份卡 + 风格（"它眼中的你"，含 `bootstrapped_from` 来源说明）+ 策略 + 声音 + **皮肤分区（原 Brand 设置 + 实时预览原样迁入）**；`/speakers`、`/brand-template` 双路由并入（重定向）；sidebar 身份项收敛为单「人设」；composer Brand pill 退役，人设块成唯一身份控件（皮肤随人设）。
5. **`STOCK_VOICES` 代码内静态注册表**（随代码部署，不建表——系统音色不伪装人设）：id / 名 / 风格标签 / 语言覆盖 / 试听 URL / provider voice_id。
6. **默认人设解析链**（不加 is_default 布尔）：项目挂载 > composer 显式选择 > `auto_created_at` 非空（系统 bootstrap）> 最早创建。
7. **配方 brand 参数 → run 级 look 覆盖**：默认 = 人设 look，配方可播种视觉覆盖；任务书字段照旧可 chat 修订。

**Consequences**:
- IP 容器终态（ADR-037 D4）更干净：IP = 人设（身份+风格+策略+声音+皮肤，一个完整对象）+ 绑定账号 + 表现数据，整体迁入无残肢。
- 多人设共享皮肤（未来团队空间共用机构 VI）以"从另一人设复制"过渡，团队空间立项时再升级共享引用——不为它保留独立模块（§7 逆用：失去独立表归属即失去模块资格）。
- 排期（PROGRESS）：**插入周 08-09~08-14 最高优先级连续落地**（改名迁移 08-09 ✅ → 皮肤吸收 08-10 → 声纹缓存 + STOCK_VOICES 08-11 → 人设显化页 08-12 → 触点 + 门禁 v1 08-13）；门禁 v2 随第五周一（08-31，`speaker_map` 过滤）；后续周次以 PROGRESS 为准。
- 实施简报：`docs/tasks/persona-identity.md`——含**消费面全审计与迁移地图**（渲染链 / DAG / chat / 配方 / 前端 / 种子脚本逐点过）与数据迁移步骤（§6–§7）。

**Related**: ADR-037（改名与人设正名）、ADR-016（clip-spec 契约不动）、RECIPES §4.4（look 层）/ §5（声音的家）、NAMING N-27/N-28

## ADR-039: 架构规范级大迭代——技能叙事 + 模块四分 + 节点对象化 + Agent 归一 + harness 层 + outputs 派生 + 估价

**Status**: Decided (2026-08-09)

**Context**: 三轮架构评审（内核核对 → tools/skills 职责梳理 → 多 agent 事实确认）沉淀。代码内核（RunPlan DAG + 注册表裁决 + chat 单入口）经逐文件核对确认健康，但存在系统性规范残留：① **skill 一词三义**（`app/skills/` 目录 / `SKILL_REGISTRY` 条目 / `SkillEntry.kind` 值），且 "班组/班底" 词需解释（NAMING §6 违规）；② **产物类型散在 6 处**（`IntentSlot` Literal / `KNOWN_OUTPUTS` / `_OUTPUT_TO_NODE_KIND` / `_SKILL_TO_OUTPUT` / `_SLOT_ORDER` / `SLOT_COUNT_LIMITS`），新增产物不是纯注册项；③ **tools/ 混 LLM 调用**（`tools/caption_translate` import agent、`tools/dubbing` 两层下藏翻译调用），职责边界渗漏；④ **节点知识散在 4 个文件**（registry / orchestrator 平行表 / node_runners / schemas），内核里全是 `if kind == ...` 分支知识；⑤ **10 个 `xxx_agent` ad-hoc 类**，真实差异只有 prompt/schema/配置——多样性是数据不是代码；⑥ **harness 部件散落**（`skills/base.py` 半个基类 / chat service 巨文件 / client），repair 仅 intent 一家、兜底无声明纪律；⑦ **多 agent 事实只活在文档散文**（RunPlan §12.5 会思考/不会思考），DAG 节点只有扁平 kind，"谁在行动"被抹掉；⑧ `cost_hint` 三档报不了价，生成前费用预估（PROGRESS 第六周）无技术地基。用户拍板：这是一次**规范级大迭代——内核流程不变，概念归位与模块重划**（"磨刀不误砍柴工"），最高优先级随人设插入周后连续攻坚。

**Decision**:
1. **技能叙事为架构主叙事**：Repurposer 是一个 AI 助手，身怀技能（剪辑/配音/字幕/自媒体规划…）；**技能内部 = agent 调 LLM、用 tools 实现**。三层归属：技能包（`app/skills/`，能力唯一家：节点类 + params + 私有工序 + 估价 + 展示键，+技能私有 agent 声明）/ `app/agents/`（决策体共享层）/ `app/tools/`（机械共享层，禁 import agents/LLM client）。
2. **Agent 归一**：`agents/base.py` 一个 Agent 类 = harness 漏斗（装配→渲染→调用→校验→**修复一轮（错误回显）**→计量→声明式兜底）；实例 = 声明（name/prompt/schema），花名册 `AGENTS` 可枚举；特殊子类仅流式（chat intent）；领域逻辑归 schema 校验/技能包工序。**盲重试退役**（修复必须带反馈）；兜底默认禁、显式声明（PlanAgent 永不白屏、多模态降级为合法先例）；**纯度签名化**（understand 签名无 persona 参数，违规在类型层不可表示）。
3. **节点对象化（`NodeBase`）**：每个节点类自描述——`run`（唯一必实现）/ `estimate(ctx)` 估价 / `requires()` 出生地门禁 / `label()` 展示名 / `reuse()` 幂等复用 / `retries`·`after`·`needs_director`·`output_type` 类属性。**内核退化为图算法**：报价 = fold、执行 = topo 走图、校验 = ∀requires、配方对账 = flow keys ⊆ 编译图 kind 集（启动自检机械化，人肉评审退役）。`_validate_requires` 字符串匹配 / `_SLOT_TYPE_LABEL` / `retries_for_node_kind` 扫描 / asset-hash 复用特判全部归位节点。
4. **outputs = 技能属性，注册表派生**：`IntentSlot.type` Literal 退役改 str + 注册表校验（NAMING §5 延伸）；五处散点全派生；新增产物 = 一条注册项，PlanAgent prompt 同源注入当轮即知。
5. **多 agent 落成结构**：`app/agents/` 花名册 + 节点归属技能包；协作哲学不变——**agent 互不对话，协作经落库产物沿 DAG 边流动**（编排者 = `compile_graph`，禁 ReAct 铁律延伸）；loop（chat 治理环）编译出 graph（DAG 执行核），四层工程地图 = Model（client 单边界）/ Harness（调用面漏斗）/ Graph（NodeBase + 图算法）/ Loop（chat 状态分派）。
6. **估价系统**：`cost_hint` 退役 → `node.estimate()`（机械精确价 / agent token 区间）；`workflow_steps.estimate` 增量列（计划侧，与 `cost` 账簿侧对称）；生成前 dock 总价 / chat 修改单价 / 配方卡估价贴随 PROGRESS 第六周（09-07 周）汇合落地；actual 校准 estimate 闭环。
7. **表结构终审**：仅 `estimate` 增量列（nullable）+ kind 与技能名统一（alembic 数据迁移：`dub`→`dub_clip`、`clips_pipeline`→`select_clips`、`post_gen`→`write_post`、`script`→`revise_script`；`SkillEntry.node_kind` 字段退役）；其余零变化；不建新表（agents/skills 皆为静态注册表）。
8. **actor 概念不采用**（评审中提出后否决）：非行业标准词；技能包构成即"谁执行"的答案。

**Consequences**:
- **行为零变化**：compile_graph 同输入同图、chat 四态/裁决/dock/checkpoint 不变、run 行为与渲染链不变；剧本 harness（S1–S40）为回归网，新增三断言（flow 对账自检 / 报价单调性 / repair 只一轮）。
- **DX 目标**：加技能 = 加一个包；加 agent = 加一条声明；加产物 = 加一条注册项——"改 6 处"成为历史。
- **分期（PROGRESS 第二周，与人设模块/闭环链三线并行）**：P1 模块归位（零变化）→ P2 NodeBase + outputs 派生 + kind 同名（含数据迁移）→ P3 harness 漏斗（Agent 归一 + repair 全员 + contexts 抽离）→ P4 估价遍历（地基同周落位，用户可见呈现并入第六周成本统计）。
- **排期**：与人设模块、闭环链同周（08-09~08-14）三线并行收口，后续整体提前，go/no-go **10-02**（回退 10-09；以 PROGRESS 为准）。闭环链直接吃红利：RunFlowGraph 节点友好名 = `NodeBase.label` 派生，不另起平行表。
- **词汇**：NAMING N-29~N-35 同批落档（班组退役/Agent 归一/actor 退役/outputs 派生/harness 限定/estimate/kind 同名）。

**Related**: ADR-028（RunPlan 持久化——本条是其规范面完成）、ADR-030（outputs 统一——本条使其可扩展）、ADR-033（能力层双注册表）、ADR-025（计量——估价是其计划侧）、NAMING N-29~N-35、AGENT_ARCHITECTURE（四层工程地图重画）、CHAT_ARCH §4/§5

## ADR-040: 配方 = 提示词——`recipe_id` 传输带与服务端播种退役

**Status**: Decided (2026-08-11)

**Context**: recipe-launch-context（同日晨间落地）把配方身份做成 `recipe_id` transport + 服务端播种（`resolve_recipe_launch`），当日剧本回归即暴露结构性病灶：配方对 plan agent 不可见——播种块只能给一个 generate 判决补槽，LLM 判 ask 时当轮无书可 dock（S11 连败复现）。病根是双份表达：配方产出写了两遍（前端 prompt 模板文案 + 注册表 `outputs`/`dub_languages`），可漂移；且极端处播种会静默盖过用户对预填文案的编辑（违背 chat 恒胜）。用户裁定原话（2026-08-11）：**"从配方生成其实只是提示词。"**

**Decision**:
1. **发射的全部行为载荷 = 预填模板原文**：`ChatRequest.recipe_id`、`resolve_recipe_launch`、plan path 校验块与播种块删除；配方卡发射与 composer 完全同径（建项目 → 上传 → 首条消息），服务端永不见配方身份。
2. **注册表瘦身不拆除**：`tasks` 技能链保留为启动对账自检的**声明形态**（flow ⊆ 编译图，AGENT_ARCH §4.2；语法经 ADR-043 与请求层统一），不进请求路径；卡面 / 检视 / 示例资产照旧。
3. **剧本换考法**：S5/S11 改发模板原文（与真实前端逐字节一致）；S22（播种确定性剧本）退役，编号留空不回收。
4. **后果自担**：任务书形状由 LLM 从模板文案推断（composer 主路同款保证）——dock 可见 + chat 纠偏是产品核心循环，不再设隐藏确定性通道。

**Consequences**:
- 删除：`ChatRequest.recipe_id` / `resolve_recipe_launch` / service.py 校验块+播种块 / 前端 `recipeId` 链路（useProjectLaunch / GenerationOverlay / chat-stream / 项目页 router state）。
- 保留：`RECIPE_REGISTRY`（卡面 + flow ⊆ 对账自检）；`ChatMention.type="recipe"` 成员（历史消息 chip 渲染）。
- 未决带出：results-workspace D5「配方身份贯穿三站」失去 `run.context.recipe_id` 派生源（代码从未落地），排产该线时需重新裁决（模板匹配 / 放弃配方标签）。
- NAMING 词汇表 `recipe_id` / `resolve_recipe_launch` 两条退役；MENTIONS §3 / RECIPES 裁决⑤+§7.2 / CLAUDE.md composer 契约现在时同步。

**Related**: MENTIONS §3（配方永不是 mention 的母判定）、RECIPES §7.1–7.2、ADR-036（D5 穿线条款随本条失效）、AGENT_ARCH §4.2（对账自检不变）

## ADR-041: 结果画布升正——canvas 为桌面默认中心、底部 dock、进度不进图、移动端 UI in chat

**Status**: Decided (2026-08-11)

**Context**: 闭环链施工中（results-workspace，08-06 立项），结果面四个问题同晚浮出并拍板：① chat 打勾收官后关窗跳结果页 = 跳切，过程与结果被劈成两个房间；② 网格 / tabs / 消息流同为线性容器，多产物扇出被线性容器物理消灭（08-07 dub 对照包证据的推广）——空间面是多产物的唯一解法；③ ADR-036 预留的"血缘板是否升正为默认中心"裁决口，其答案不应只给血缘板——结果面本身是中心候选；④ 移动端渲不了 canvas 曾被视为方向反证——非也：移动端是降级面不是核心场景，方向是否成立的证据看桌面。同日 Lovart 式画布评审 + 多轮讨论后用户拍板：结果面 = 整屏只读 canvas，chat 收为底部 dock。本条关闭 ADR-036 的"默认中心"裁决口，修订其第 3 条与补记 1/3；**ADR-035 第 2 条（可操作画布永久拒绝）不变**——canvas 正当性三理由：连续性（产物从过程里长出来，无跳切）、扇出全景可见、血缘信任（每个产物出处可溯）。

**Decision**:
1. **结果画布 = 桌面/iPad 默认中心**：项目页收官态 = FlowView 渲染当前 run 拓扑 + 最新产物（真节点真边，output 节点 = 产物卡：缩略图 / 分数+top-pick / 下一步建议）。多 tab 结果页与"结果网格为默认中心"退役；网格重构件降级为移动端列表渲染件复用。
2. **进度不进图**：打勾流是唯一进度面（run 进度图排产撤销）；收官转场 = 遮罩淡出 + 消息区上收 + 画布按 `seq` 编译序诞生回放——动画 = 真实事件投影不变；输入组全程零位移；断线重连 / 历史打开直接呈现终态不播回放。
3. **底部 dock（2026-08-13 修订：一体容器 + 灰行入流）**：chat 外壳从全屏 dialog 转 Mac-Dock 式居中悬浮输入组（同一消息机器内脏不动）。dock 只有两态——收起 = 输入组（唯一常驻 chrome），展开 = 历史区域在**同一磨砂容器内**向上生长（容器独占圆角与玻璃，子件全方；摘要卡条 / 焦点 chip / 三态机退役）；**agent 发声（含系统事件：焦点设置）历史必自动展开**；点画布空白 = 回中性（历史收起 + 焦点清除，pane 级事件，节点点击不触发）。**系统层灰行入流原则**：一切系统事实（步骤勾选、run 收官 recap、焦点事件）渲染为消息流内的灰色 meta 行（`MetaRow`：muted + xs + 无填充 + 超长截断可点开），永不另立流外 chrome——信息入流，控制留底。画布视口留 bottom safe-area。一个输入组三停靠位：首页 composer / overlay 底排 / 结果 dock。
4. **产物节点 toolbar 合法化，边界说死**：hover 出带 gap 悬浮 pill（预览 / 下载 / 发布 = 旧卡面动作平移）；单击 = detail modal 旧逻辑原样，publish modal 保留；过程节点永无 toolbar；toolbar 装图操作（运行 / 接线）永久禁区。ChatModal / AssetChatModal 退役——产物对话归 dock + 焦点注入；工作面"舞台 / 检视器"页面区方案取消（detail modal 保留使检视器冗余）。
5. **密度三档 + 渲染单元**（2026-08-12 修订）：配方说明书 = 策展密度（≤5 节点，只画兑现承诺的步骤）；结果画布 = 工件密度（素材 + 工件卡 + 产物主角）；run 期无图。**画布渲染单元 ≠ 执行单元**：step 全量落库（成本 / 重跑 / 血缘靠它），画布按节点类自描述聚合渲染——`canvas_key` 同键 steps 合一张工件卡（计划 = understand+checkpoint+plan；选段；配音按语言分卡；音乐），无键折"过程脊"组节点，`canvas_hidden`（render）永不上图、状态原地投影到产物卡（失败/渲染中 = 卡的原地态，不是独立节点）。节点解剖 = 输入在边上、规格在身上、结果在卡上、改动在 chat。判定任一节点只问："用户会想 @它 说改这个吗？"
6. **导航门禁修订**（修订 ADR-036 补记 1）：缩放 = 导航不是编辑——配方卡说明书锁 fit；结果画布开放 pan / zoom（minimap 退役：稀疏小图无导航价值）；拓扑编辑手势任何面物理缺席。
7. **移动端 = UI in chat**：不渲染 canvas（< iPad 宽度）；对话沉底与桌面 dock 同心智；一回合一张 RunCard（卡头血缘摘要行 + 可展开过程脊 + 产物缩略条 + chips）；点缩略图进全屏查看器（家族滑动 + 底部迷你输入条）；点卡即焦点免 @。卡片种类注册表制：计划 / 操作 / 结果三型。
8. **焦点 = 一次性消费 + 落库**（2026-08-13 修订 N-36「不落库」）：画布点选产物 → 下一轮 chat 携带 `focus_output {id,label}`（context 一行不变），发送即消费（再改再点，点画布空白即清，失败回滚即还）；**焦点持久化在用户消息上**（`messages.focus_output`）——历史回读时该消息上方渲染焦点前缀灰行，刷新后流不撒谎。
9. **复核门**：小白复述测试周五（08-14）照跑——裁决问题从"血缘板是否升正"改为"结果画布是否转正"；不过则结果网格回退为默认中心（组件不删），canvas 降为检视入口，零浪费。

**Consequences**:
- ADR-036 修订：第 3 条（run 进度图升正排产）退役为"结果画布"；补记 1 缩放门禁按面重划；补记 3 诞生编排触发时机从"run 启动"改为"收官揭幕回放"。FlowView 消费面 = 配方流程图 / 结果画布 /（复核中的）血缘板。
- results-workspace 简报退役（中央区状态机 / 六屏 / 工作面三区被本条吸收改写；chips 双级派生 / 翻译两层 / Before-After / 焦点注入沿入新简报）；其 D5「配方身份贯穿三站」条款正式退役——ADR-040 后服务端永不见配方身份：打勾流皮肤用节点友好名、chips 按焦点产物派生，均不需要配方身份（本条同时关闭 ADR-040 的未决带出）。
- 结果页 tour 锚点随画布重锚（`data-tour="results-*"` 挂产物节点卡）。
- 移动端本期保留现有结果列表兜底；RunCard 增强排第三周。

**Related**: ADR-035（可操作画布永久拒绝不变；第 3 条裁决口关闭）、ADR-036（本条修订其第 3 条与补记 1/3）、ADR-040（D5 条款退役的母因）、ADR-028（RunPlan）；简报 `docs/tasks/results-canvas.md`

## ADR-042: 身份根升格——定位（Positioning）为根、人设收窄为表达分区、选题库升一等公民

**Status**: Decided (2026-08-13)

**Context**: persona 超载的三重病灶在 ADR-037/038 落地后显形——① **定位缺位**：策略三件（audience/guidelines/cta）只是定位的薄切片，因无处安放寄存人设；agent 顾问姿态（诊断听众/目的）问完无落点，"用户到来即彷徨"（STRATEGY §5）没有持久答案；② **渠道空壳**：`channel_accounts` 只是 OAuth token 行，不知道自己属于谁、服务哪个受众，发布数据回流（P2）将无处可挂；③ **人设被偷渡**："多实例扁平（工作号/生活号）"实为两个定位压成两行风格对象，同一真人克隆两次声纹。运营全链路对照（定位 → 账号 → 对标 → 选题库 → 生产）显示：现有架构只覆盖生产层，运营层（持续回答"该做什么"）整体缺失。ADR-037 D4 预留的"IP 容器加法式升格"路径经复审否决：**根词不是被打造的结果**（品牌/IP 留在营销承诺层——自媒体新人听到的第一句话是"找定位"，不是品牌相关的话），且行业话语里定位天然三分（内容定位/人设定位/平台定位），定位 ⊇ 人设是标准用法。更根本的分界：**定位是选择（对话共建带确认），人设是特征（素材提取+维修点）**——两种来源、两种生命周期，混在一个对象里，页面既想当接待处又想当维修点。

**Decision**:
1. **身份根 = 定位（`positioning`）**，多实例（工作号/生活号 = 两个定位）。表 `personas`→`positionings`、FK 网 `persona_id`→`positioning_id` 全栈平移（speakers→personas 改名先例同构，纯机械刀）。
2. **三分结构**（行业话语映射）：内容定位 = 战略字段（territory/audience/differentiation/goals/guidelines/cta，**对话共建带确认**）；人设定位 = 表达分区（风格六件 + `voice` 块 + `brand` 块原样保留，`persona` 收窄为逻辑分区词，不物理嵌套）；平台定位 = 渠道（`channel_accounts.positioning_id` FK + 公共档案 + 适配默认）。
3. **选题库升一等公民**：`topics` 表 + 生命周期（灵感/已排期/生产中/已发布/有数据）；选题卡 = 发射单元（点卡 → 任务书预填 → chat 确认 → run，chat 唯一意图面不变）；来源 = 素材档案挖矿（主）+ 对标/回流信号（P2）。配方卡（新用户能做什么）与选题卡（老用户下一条做什么）分工并存，共用同一发射机构。
4. **project 退居内部执行容器**：用户可见工作单元 = 选题（管道）+ 产物（成果库）；projects/runs 留管线层做分组与重跑载体。
5. **素材档案上提根级**（assets 挂 positioning，back-catalog 挖矿底座）；**声纹资产用户层共享**（声带是人的不是定位的，多定位引用同一份克隆）。
6. **品牌/IP 留在承诺层**：落地页叙事继续 personal brand / 个人品牌；`brand` 维持皮肤块一词不动（不引入 `look`）；产品内导航用「定位」。

**Consequences**:
- ADR-037 D4（IP 容器加法式升格）作废，由本条取代（容器升格 = 定位根改名路径）。
- 排期（PROGRESS §2）：生产层闭环（第二~五周）不动；**运营端插第六~八周**（定位根重构 → 选题库 → 回访 home + 素材上提）；商业化/分发/合规/法务顺延 3 周，go/no-go 10-02 → **10-23**（回退 10-30）。
- 明确不做：对标作为支柱（与反 slop 定位相悖，P2 降级为选题校准信号）；工具格形态（chat 唯一意图面不变）；昵称取名场景（目标用户有名字有机构）。
- 母文档 `docs/POSITIONING.md`；MODULE_ARCHITECTURE / NAMING / CLAUDE.md 的现状描述随第一刀落地时改写（落地前它们仍是现状事实源）。

**Related**: ADR-037/038（身份模块前史）、ADR-016（clip-spec 不动）、ADR-041（结果画布——运营端 home 复用其面）、STRATEGY §5（用户到来即彷徨）、PROGRESS §2 第六~八周

## ADR-043: 任务书语法收敛——outputs 概念退役为派生（derive），plan path 并入技能链

**Status**: Decided (2026-08-15)

**Context**: 多语言字幕卡点亮次日（08-14）真实场景走查：用户从字幕卡发射「给我的视频加中英双语字幕」（长视频源），任务卡呈现「视频片段 ×2 · 中文」——整条视频的变换意图被强制表达为高光提取 + 簿级修饰符，数量步进器（默认 3）出现在数量由请求完全决定的场景。根因不是 UI：outputs 槽位语法（`IntentSlot` + `InferredIntent.outputs`）诞生于「一场演讲 → N 件衍生品」时代，彼时业务只有提取族一种形状，请求层 schema 直接就是产物清单。技能注册表（ADR-039）落地后工作语法已迁至技能链：产物类型词汇由节点 `output_type` 声明派生（N-32），mode② 已能从 task list 反推槽位形状（`derive_context_fields`）——plan path 是旧语法最后的堡垒：outputs 必填；unclear 默认全家桶（clips+post+quotes+article，与 07-31 反打包裁定冲突）；固定拓扑编译。同一分叉已在配方层显形：字幕卡流程图已摘掉剪辑步骤（卡不含剪辑，RECIPES §4.1），承诺「为你的视频带来多语言字幕」，但其预设 `outputs=[clips]` 的编译图仍跑 select_clips——15s demo 源下高光≈整条掩盖了分叉，真实长视频穿帮；图文视频卡同病（承诺「短片」单数，管线只出 N 条高光）。备选：① 旧语法加 `video` 产物类型（在退役语法里加座位，双语法永存）；② clips 槽加 scope 标志（一个类型藏两种形态，消费方逐个长分支）；③ 任务书行改自由文本（推翻结构语法，merge/director/UI 全重写）——均否决。

**Decision**:
1. **outputs 概念下线，升格为 derive**：请求层不再有产物声明——产物 = 编译图的派生投影（类型词汇仍由节点 `output_type` 声明派生，N-32 不变；Output 表 / 产物行不动，死的是请求层语法）。意图面唯一语法 = 技能链（task list）：plan path 与 chat loop 四态的 task_list 臂同一词汇，一次收敛。
2. **PlanAgent 产出 task list**：槽位字段下沉为技能参数（writer 族 language / focus / tone_override；select_clips count / focus / aspect；translate_clip target_language + bilingual；dub_clip target_language）；簿级四修饰符（caption_languages / dub_languages / caption_bilingual / aspect）退役。unclear 不出默认全家桶——最小链或顾问式反问（CHAT_ARCH §3.3 姿态不变）。
3. **整条源材料化节点 `materialize_source`**（编译期自动注入的内部节点，不登记技能表）：确定性全段 clip-spec（span = 素材全长，无 LLM 选段；源形态分发 video/audio/stills 复用 select_clips 的源决策，stills 经 align_stills 注入先例）。注入规则：链含 clip-spec 消费者（translate / dub / music / filler）而无 select_clips、且项目无既有 clips 可作用时注入（mode② 中途「作用于现有 clips」语义不变）；preprocess 按 requires 声明入图（不再只随 director 前奏捆绑）；纯变换链不触发人设提取（08-11 先例）。fork 挂接随之修正：translate / dub 的 `after` 声明吸收材料化节点。
4. **计划卡 = 链投影 + 派生预览**：generate 回合干跑 compile_graph（纯函数）产出卡模型——技能链人话行 + 派生产物行（「整条视频 · 英字 / 中英双语」）+ 后续报价 fold 同源；presented_plan 摘要同一 derive。**面板控件 = 对 task list 的直接结构编辑**（数量步进器绑 select_clips.count、语言 chips 增删 translate/dub 任务、删行 = 移除技能）——与 LLM 重提同一数据结构，三方合并（merge_prior_slots / prior_intent 运输 / explicit 钉）无对象自然死亡；chat 修订 = 带 presented 摘要重提全链，chat 恒胜不变。start = 以编辑后的链编译起 run（服务端编译为行为唯一事实源）。
5. **派生类型 `video`（整条视频）= 纯展示词汇**：`materialize_source` 是编译期注入的内部节点（`NodeBase.internal`，自检豁免注册表席位），**不声明 `output_type`**——可请求类型注册表（N-32）保持原样；"video" 只活在派生预览行 / 步骤摘要 / 结果分组（节点落库的 Output 行仍是 `type="clip"`，渲染血统不变）。不可请求、无 count_limits、无步进器。
6. **director 派工对齐改 keyed on 编译图**：storyboard 槽从编译出的生成节点（含参数）构建，不再从 `run.context.outputs` 读请求层槽位——多版本互补分配不退化，且与面板编辑后的真实执行链严格一致。
7. **配方预设改写为 task list 形状**（multilingual-subs = [translate zh bilingual, translate fr, dub es]；image-video = [add_music] + 材料化/stills 自动注入——「变成短片」单数承诺自此为真），flow ⊆ 编译图对账不变；配方=提示词不过线不变。

**Consequences**:
- 死亡清单：`InferredIntent.outputs`（含默认全家桶）/ `outputs_explicit` / 簿级四修饰符 / `IntentSlot` 请求层身份 / merge_prior_slots / prior_intent / mode① 固定拓扑（期 2 清尸）/「clips 槽唯一」规则 /「修饰符必须挂 clips」耦合 / 前端 OUTPUT_OPTIONS 与 SLOT_COUNT_* 镜像 / 卡片「添加产物」按钮 / 字幕版本·配音版本区（折入链行）。
- 存活不动：pending_intent 持久化（载荷换形为 task list，存量行读容忍确定性升级）、start 确认流与 autonomy 档、出生地 422（requires 双源已免费）、edit ops、打勾流 / SSE、配方=提示词、chat 恒胜、顾问姿态四律。
- 行为变更（有意）：图文视频卡产出从 N 条高光轮播变为整条轮播一条（承诺一致）；变换意图不再夹带剪辑。
- **目标解析不变量（同日 review 补入）**：modifier→modifier 边只是排序约束——`_target_clips` 跳过 `spec.fork` 上游的 output_refs（fork 产出是新建派生行，其原件经链基座边即达）；否则全 fork 链（R6：translate×2 + dub）会把派生行当新目标组合爆炸（7 产物而非承诺的 4）。morph 上游的 output_refs 照常下传（原地改写的交接）。**配套的兜底口径**：`_target_clips` 的「项目现存 clips」兜底只含**本 run 之前**的行（按 workflow_step_id 所属 run 排除本 run）——否则 existing 画幅下的全 fork 链（首个 modifier inputs 为空、次个只挂 fork 上游被跳过）会被同胞 fork 的新鲜派生行污染兜底集，同样组合爆炸。
- **重试 = 该类自己的链原样重跑（同日 review 补入）**：结果页 tab 重试不再硬编码「clips  tab → select_clips」——整条源变换链（无 select_clips）的 clips 重试曾会把整条字幕片换成 3 条高光剪辑（产品形态被换）。clips 族重试发帖内 clips 族任务原序原参数（text 族 = 单个 writer 任务）；chat 域参数（target_output_id）剥离（full run 会删旧行）。配套：legacy 读容忍升级（`legacyOutputsToTasks` / `_legacy_slots_to_tasks`）给 dub/translate 任务补 `fork: true`——slots 时代编译产出即 fork 节点，升级须保持形态。
- 排期：2026-08-15 当日全量落地（拍板 08-15：期 1 语法切换 + 材料化 + 卡换形 + 期 2 清尸同日完成），不整周插入。
- 第九周报价系统协同：卡 derive 与估价 fold 共享同一次干跑编译。

**Related**: ADR-039（技能注册表——本条的语法家）、ADR-028/029（RunPlan / plan 级 dispatch——mode② 先例）、ADR-040（配方=提示词——载荷单一通道同款哲学）、ADR-041（结果画布——派生预览的消费面）、STRATEGY §5（反打包）；简报 `docs/tasks/done/outputs-derive.md`
