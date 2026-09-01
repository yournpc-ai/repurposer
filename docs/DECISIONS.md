# Architecture Decision Records (ADR)

> Status: Active（滚动维护——只留现行决策，过时 / 被翻案的内容直接删除，历史在 git；新决策追加新编号，编号不连续属正常）

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
2. **Music defaults by music id, not mood strings**: 默认曲配置住人设皮肤块——系统默认皮肤（`DEFAULT_BRAND_CONFIG`）携带 `musicEnabled` / `musicId`（缺省回退 `musicMood`）/ `musicGainDb`，人设 `brand` 块按需覆盖，烘焙缝合并解析出默认曲目 id（`app/memory/brand.py`）。
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
3. **过渡动画愿景（用户拍板："连线、node 的诞生、布局都有 transition，用户会感觉到优雅"）**：每层动画都投影真实事件——**诞生编排**（2026-09-01 ADR-051 定稿形态：画布挂载期间出生的节点——占位物化 / 产物原位填充 / 修订生长——按编译序 `BIRTH_STAGGER_MS` 交错入场 + 边描画，是把真实编译顺序用缓动时间轴回放，不是剧场；fullscreen 时代的「收官整图回放」与「生长动画」在占位世界统一为这一条生长驱动规则）；**状态动画**（running 脉冲 / 边流动指向待执行子节点，SSE 驱动；running 占位卡带 FLORA 左→右填充擦除——纯 CSS 缓动封顶 96%，不声称分数，落地产物是唯一 100%）。禁令 #9 不破：动画永远是真实事件（编译序/状态迁移/真实生长）的投影，禁假进度；`prefers-reduced-motion` 降级为即时呈现；刷新/断线重连/历史打开直出终帧——水合首帧永不重播。

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
1. **结果画布 = 桌面/iPad 默认中心**：项目页收官态 = FlowView 渲染当前 run 拓扑 + 最新产物（真节点真边，output 节点 = 产物卡：媒体内联自播（视频静音循环）/ 分数+top-pick / 磨砂操作条（下载/发布，hover 放大开大屏））。多 tab 结果页与"结果网格为默认中心"退役；网格重构件降级为移动端列表渲染件复用。
2. **进度不进图**（2026-08-31 ADR-051 收窄为「**步骤叙事**不进图」）：打勾流是唯一步骤叙事进度面（run 进度图排产撤销）——ADR-051 起浓缩为默认折叠的一行（Claude Code 式：运行中 shimmer 状态行 + 当前步名，点击展开步骤日志，收官 recap 聚合照旧）；**产物占位/填充 = 图的内容不是进度**（derived preview 确定性投影，run 开始即物化、产物落地原地填充）；收官转场 = 遮罩淡出 + 消息区上收 + 画布按 `seq` 编译序诞生回放——动画 = 真实事件投影不变；输入组全程零位移；断线重连 / 历史打开直接呈现终态不播回放。
3. **底部 dock（2026-08-13 修订：一体容器 + 灰行入流）**：chat 外壳从全屏 dialog 转 Mac-Dock 式居中悬浮输入组（同一消息机器内脏不动）。dock 只有两态——收起 = 输入组（唯一常驻 chrome），展开 = 历史区域在**同一磨砂容器内**向上生长（容器独占圆角与玻璃，子件全方；摘要卡条 / 焦点 chip / 三态机退役）；**agent 发声（新回复落流）历史必自动展开——焦点设置不撑开历史（2026-08-16 走查修订：chip 即反馈，焦点灰行照旧入流，点卡开详情 modal 时历史乱弹是 jump-scare）**；点画布空白 = 回中性（历史收起 + 焦点清除，pane 级事件，节点点击不触发）。**系统层灰行入流原则**：一切系统事实（步骤勾选、run 收官 recap、焦点事件）渲染为消息流内的灰色 meta 行（`MetaRow`：muted + xs + 无填充 + 超长截断可点开），永不另立流外 chrome——信息入流，控制留底。画布视口留 bottom safe-area。一个输入组停靠位（2026-08-31 ADR-051 修订）：首页 composer / 结果 dock（原第三停靠位 overlay 底排随 fullscreen 壳退役）。
4. **产物节点 toolbar 合法化，边界说死**（2026-08-17 走查修订：节点解剖统一）：单击 = detail modal 旧逻辑原样，publish modal 保留；过程节点永无 toolbar；toolbar 装图操作（运行 / 接线）永久禁区。**节点解剖 = caption 恒为类型 icon + 类型名（左上，右槽恒空）+ 媒体区 + 卡下磨砂工具条**：一切信息位（语言 / 分辨率 / 时长 / 画幅）住工具条左区——时长住条内、永不作为视频浮层角标（媒体角标只剩 score），分辨率从媒体元素实读（`onLoadedMetadata` / `naturalWidth`），不立硬编码表；divider 隔信息位与动作位（下载 / 删除 = 条内仅有的两个动作），删除右侧"⋯"开二级菜单（发布 / 打开 / 在对话中指认），菜单带层级故同走雾面玻璃；**工具条宽度不限、信息永不省略**（08-17 三轮走查拍板）——条随内容自然撑开、卡下居中对称悬出，截断/省略号/title 兜底全部撤销（此前 max-w-full 卡宽 + 信息无 overflow-hidden 的组合曾让文字穿透 flex 序与图标层叠）；**产物卡 lane 208 → 280 同轮放大**（9:16 → 498 媒体高，源视频素材节点同宽 280）。素材节点同解剖（文件名 / 时长 / 分辨率 + 下载 / 删除 + ⋯ 重处理），动作归 surface 所有；删除产物 = `DELETE /outputs/{id}`（连存储对象一起清，fork 派生行不陪葬）。ChatModal / AssetChatModal 退役——产物对话归 dock + 焦点注入；工作面"舞台 / 检视器"页面区方案取消（detail modal 保留使检视器冗余）。
5. **密度三档 + 渲染单元**（2026-08-12 修订；2026-08-19 名词节点收窄）：配方说明书 = 策展密度（≤5 节点，只画兑现承诺的步骤）；结果画布 = 名词密度（素材 + 任务书文本节点 + 产物主角）；~~run 期无图~~（2026-08-31 ADR-051 翻案：fullscreen 壳退役后 run 期画布活——占位卡 run 开始即物化 + 折叠打勾随行）。**画布渲染单元 ≠ 执行单元**：step 全量落库（成本 / 重跑 / 血缘靠它），画布按节点类自描述聚合渲染——`canvas_key` 同键 steps 合一卡（现行唯一授予 = `plan`：understand+checkpoint+plan 的任务书，dock-surface 雾面玻璃文本节点，对应 FLORA 文本节点形态）；**过程动词永不上图**（select_clips / dub / add_music 授予全移除，translate_clip 08-15 先例推广——每个动词都是其产物的属性），无键折"过程脊"组节点（干预 = 点产物卡注入 dock 焦点 / 脊内步骤 pill 走 @workflow_step），`canvas_hidden`（render；prelude——preprocess/persona_bootstrap，2026-08-19 二轮 R1：plan 的上游与下游折进同一脊会使可见图成环、任务书沉进产物列，prelude 改 hidden 后资产喂边走下游兜底到任务书）永不上图、状态原地投影到产物卡（失败/渲染中 = 卡的原地态，不是独立节点）。节点解剖 = 输入在边上、规格在身上、结果在卡上、改动在 chat。判定任一节点只问："它是名词吗？"——动词一律折脊。
6. **导航门禁修订**（修订 ADR-036 补记 1）：缩放 = 导航不是编辑——配方卡说明书锁 fit；结果画布开放 pan / zoom（minimap 退役：稀疏小图无导航价值）；拓扑编辑手势任何面物理缺席。
7. **移动端 = UI in chat**：不渲染 canvas（< iPad 宽度）；对话沉底与桌面 dock 同心智；一回合一张 RunCard（卡头血缘摘要行 + 可展开过程脊 + 产物缩略条 + chips）；点缩略图进全屏查看器（家族滑动 + 底部迷你输入条）；点卡即焦点免 @。卡片种类注册表制：计划 / 操作 / 结果三型。
8. **焦点 = 一次性消费 + 落库**（2026-08-13 修订 N-36「不落库」）：画布点选产物 → 下一轮 chat 携带 `focus_output {id,label}`（context 一行不变），发送即消费（再改再点，点画布空白即清，失败回滚即还）；**焦点持久化在用户消息上**（`messages.focus_output`）——历史回读时该消息上方渲染焦点前缀灰行，刷新后流不撒谎。
9. **复核门**：小白复述测试周五（08-14）照跑——裁决问题从"血缘板是否升正"改为"结果画布是否转正"；不过则结果网格回退为默认中心（组件不删），canvas 降为检视入口，零浪费。

**Consequences**:
- ADR-036 修订：第 3 条（run 进度图升正排产）退役为"结果画布"；补记 1 缩放门禁按面重划；补记 3 诞生编排定稿 = 生长驱动（画布挂载期间新生节点按编译序入场，水合首帧直出；2026-09-01 ADR-051 拍板，fullscreen 时代的「run 启动」「收官揭幕回放」两种触发一并退役）。FlowView 消费面 = 配方流程图 / 结果画布 /（复核中的）血缘板。
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
3. **整条源材料化节点 `materialize_source`**（编译期自动注入的内部节点，不登记技能表）：确定性全段 clip-spec（span = 素材全长，无 LLM 选段；源形态分发 video/audio/stills 复用 select_clips 的源决策，stills 经 align_stills 注入先例）。**画幅缺省 = `original`（2026-08-17 走查拍板落地：链无 clip 技能 = 比例跟源）**——clip-spec aspect 增第四档 `original`，渲染器 calculateMetadata 经 media-utils 实读源尺寸（stills 读首图，失败回退 16:9）；显式意图（spec / run.context）仍胜，人设皮肤的 aspect 是短片工艺默认、永不适用整条材料化（横版演讲曾被裁成 9:16 竖屏，08-17 实证）。注入规则：链含 clip-spec 消费者（translate / dub / music / filler）而无 select_clips、且项目无既有 clips 可作用时注入（mode② 中途「作用于现有 clips」语义不变）；preprocess 按 requires 声明入图（不再只随 director 前奏捆绑）；纯变换链不触发人设提取（08-11 先例）。fork 挂接随之修正：translate / dub 的 `after` 声明吸收材料化节点。
4. **计划卡 = 链投影 + 派生预览**：generate 回合干跑 compile_graph（纯函数）产出卡模型——技能链人话行 + 派生产物行（「整条视频 · 英字 / 中英双语」）+ 后续报价 fold 同源；presented_plan 摘要同一 derive。**面板控件 = 对 task list 的直接结构编辑**（数量步进器绑 select_clips.count、语言 chips 增删 translate/dub 任务、删行 = 移除技能）——与 LLM 重提同一数据结构，三方合并（merge_prior_slots / prior_intent 运输 / explicit 钉）无对象自然死亡；chat 修订 = 带 presented 摘要重提全链，chat 恒胜不变。start = 以编辑后的链编译起 run（服务端编译为行为唯一事实源）。
5. **派生类型 `video`（整条视频）= 纯展示词汇**：`materialize_source` 是编译期注入的内部节点（`NodeBase.internal`，自检豁免注册表席位），**不声明 `output_type`**——可请求类型注册表（N-32）保持原样；"video" 只活在派生预览行 / 步骤摘要 / 结果分组（节点落库的 Output 行仍是 `type="clip"`，渲染血统不变）。**结果画布消费方式（2026-08-17 落地）**：`source_ref.segment.id === "full"` 的 clip 卡 caption 读作 "Video"（复用素材类型词），不读 "Clips"——fork 派生行携带同一 source_ref，翻译/配音版同样成立。不可请求、无 count_limits、无步进器。
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

## ADR-044: clip-spec 轨道模型——锚定存储 + 泳道编译产物 + TRACK_REGISTRY（12 操作闭包）

**Status**: Decided (2026-08-17)

**Context**: 图内核（NodeBase/compile_graph）、能力层（OP ∪ SKILL 双注册表）、产物层（outputs 派生）已完成各自的"注册表时刻"（ADR-039/043）；clip-spec 是最后一个未注册表化的面——每条轨一个手写字段 + N 处消费方特判（08-14 translation_track 落地实测摸约 7 处：双端 schema / Clip.tsx 分支 / `_absolutize` / 尺寸规则 / C2PA / ops 寻址，全靠人记——"每加功能前后打架"的力学来源：每个消费方各自重新推导一遍 spec 的结构知识，推导不齐就打架）。同时三股需求朝这个面涌来：crop_track 关键帧轨 / reframe_clip 分镜 / layers（B-roll、双机位 PiP）。验收判据 = **操作集闭包**（2026-08-17 用户以真实剪辑顺序 12 项操作走查立据，全表见简报附录）：registry 合法 op/skill 的任意序列（用户聊 N 轮）产出的 spec 仍可表示、可渲染、可继续改。走查结论：7 项今天已通、1 项缺登记（reorder_segments）、4 项（异源插入 / 过渡 / 文字层 / 贴图层）挂在同一次采购上。同日用户拍板两条：① **允许破坏性更新**——旧数据与旧规划不构成约束，以目标（闭包）为主；② **P2 契约提前至本批**——segments widen / layers / 锚 / 过渡枚举 / ops 寻址 / 泳道投影不再等第一条 insert/B-roll 技能进排期，由 12 操作闭包判据直接驱动。

**Decision**:

1. **形态 = 存法 C：锚定是存储格式，泳道是编译产物**。位置不落库——层条目挂语义锚，输出时间窗由烘焙缝一次 fold 派生；泳道投影永不落库、永不进快照、永不可写（不是缓存，是编译产物，双写不一致在结构上不存在）。**双真相禁令**：锚与绝对坐标不得平级共存于同一行数据。消去法：存法 A（泳道为真相 + 锚作附加元数据）= 两病——锚沦为缓存则漂移原样存在，锚若用于重算则已是 C；平级双真相 = 双主写必然分歧，不存在。锚三形态：**段锚**（`{segment_id + 源偏移}`，内容跟随）/ **边锚**（`{head|tail + 偏移}`；intro/outro 本质即边锚块）/ **比例锚**（`{ratio}`）。非破坏模型红利：段从不真删（hidden），层条目锚点时间落入被剪区间即失去投影窗口、自然不渲染——"级联删除"是纯派生，"并告知"归 op 响应。
2. **词汇四分 + 八词入宪法**：主轨（sequence）/ 数据轨（data，`*_track`）/ 层（layer）/ 块轨（block）四家分完整个 spec；段 segment / 锚 anchor / 过渡 transition 等八词登记 NAMING §2；**裸 track 违规、必须带家族限定**（判例 N-38，N-11 同型）。`layer` 避让 `overlay`（UI 浮层已占名：GenerationOverlay / overlay-surface——N-27 同型一词两义预防）；lane / blocks / junctions / placements 讨论期占位词草稿阶段死亡，不进任何文档。
3. **TRACK_REGISTRY**：**Python 持有可执行目录（`app/pipeline/tracks.py`，唯一运行时端）**；TS 端只声明 `fields` 分区 + `TrackId`（`packages/clip/src/tracks.ts`——类型级断言强制每个 spec 键入一轨，tsc 闸），分区在两端各自独立 pinning（Python 启动对账 + TS 类型断言），无镜像漂移面、无对账脚本。`TrackDef` = `owner`（唯一写者技能，表归属契约的 spec 转置）/ `pairs`（translation⇄caption——既有耦合入档）/ `provenance`（ADR-026 分类器 fold）/ `url_fields`（烘焙缝 fold）/ `fields`（spec 顶层字段分区——自检①的承重墙）/ `depends`（派生轨失效声明，dub⟵main）。family / timeline 分类是文档（RENDERING §4 表），不进 schema；确定性工艺检查随首个住户与其消费方同批回归（08-19 能力批评估）。现有 8 轨平移登记 + layers 轨（layer 家族首条）。渲染器按 family 分派渲染件（sequence→段序列 / data→cue 渲染或关键帧采样 / block→块件 / layer→层件），新增轨 = 注册渲染件不动旧分支；renderer-agnostic 不动（声明只说 WHAT，Remotion 概念不进注册表，FFmpeg 后路保住）。
4. **两条启动自检**（挂 `assert_runners_registered`，API/worker 双进程 + harness 同跑）：① spec 顶层字段 ⊆ 注册表，每字段恰好一条轨；② **phantom track**——注册一条假轨（try/finally 直变异 TRACKS，移除是结构保证），烘焙缝 / 寻址 / 合规自动接管、消费方零改动（"渲染"腿的本批语义 = 烘焙缝 `_absolutize` 接管；渲染件注册随真实住户进场）。**计价不在自检面**：时长算术坐 `clip_spec.total_output_seconds`（kept video + 头尾卡秒）——时长贡献不随注册表自动收养，带时长的轨到来时与其渲染件同批扩展该函数。
5. **spec 进化三件**（12 操作断点的收敛处）：
   - **segments widen**：段 = `{id, asset_id?（缺省=主源）, url?（异源段随写解析，source 同款先例）, start, end, hidden}`——异源插入 = 带 asset_id 的段（ADR-029 虚拟产物段同源入座）；段可带 provenance，混合时间轴 C2PA 判定免费获得。
   - **layers 轨**：锚定放置物列表 `{id, kind, anchor, rect, z, source_ref?, media?, provenance(必填)}`；kind 枚举注册守门（broll / text_callout / pip / motion_graphic）；PiP 经 `source_ref` 自带一路源回放——"两条视频同时可见"的唯一合法形态，三条以上全帧视频叠放 = 真 NLE territory，永久不进。
   - **transition 枚举**：挂段的进场边（none/fade/dip，2-3 封顶——`insert_segment` 与 `set_transition` 两 op 同查），换序随段走；进场边语义与 FFmpeg xfade / Remotion 插值天然对齐。**ADR-016 L3 注记修订为"枚举可、画廊不可"**（转场挑选面板永拒不变）。
6. **泳道投影 = 位置 fold 单函数**：sequence + layer 家族 → 扁平泳道（绝对输出时间 + z 序），TS 单家（packages/clip）+ Python 同名镜像（NAMING §1）；data 家族不投影——按 sourceTime 采样（crop_track 采样器 = keyframes 族第一个渲染件）；块轨本就输出时间轴。渲染器只吃投影/采样，永不读锚；投影函数同时是 FFmpeg 后路的 filtergraph 供料口。
7. **ops 闭包**：`reorder_segments` / `insert_segment` / `set_transition` / `add_layer` / `remove_layer` / `move_layer` 登记入 OP_REGISTRY；**op 载荷 = 实体引用（段 id / 锚 / 枚举），LLM 永不提议绝对时间码**（坐标计算永归代码——"LLM 提议、代码裁决"的编辑侧延伸）；寻址 = （轨, item_id, op) 对注册表校验，不靠 LLM 猜字段路径；段/层 id 唯一性由 ClipSpec 契约断言（锚寻址 first-match 的前提）。**一轨一写者**：撞轨 = 编译期 422（fork 豁免——派生行各有其 spec），不做运行时合并。**派生轨失效声明**：对主时间轴派生的轨（dub）在注册表声明依赖，时间轴 op 落地时经注册表枚举失效轨并告知（重配一句话；不产生"合法的谎"）。
8. **agent / skill / tool 配套边界**：**总 agent 不变**——chat loop / PlanAgent / ChatIntentAgent 零改动，单次调用 + 预装配上下文、禁 ReAct 辩护到底。**skill 按用户语言命名和切分，不按轨道切分**（「说到工厂时配工厂画面」是一个技能，「插入 layer」不是；轨道是内部坐标系）。tools 层零新增（投影/remap 是 pipeline 镜像函数，不进 tools/；边界精确化见 ADR-045——工序零新增，引擎缝按 asr.py 先例豁免）。技能化（insert_broll 工序、reframe_clip、checks 首批住户、LLM op 词汇开放、层的画布标记卡呈现）随功能排期——语录评审全案归简报 `tasks/done/track-model.md` §7。
9. **tracks:{} 容器禁令保留、理由换血**：旧理由"破坏性格式迁移"随破坏性授权作废；保留理由 = 收益已证伪——快照 undo + LLM 不写 spec 的地基上全量常驻空轨无收益，扁平 spec + 注册表索引已提供全部归属能力。本禁令与兼容性无关，是纯目标判断。

**Alternatives（翻案条件随附）**:
- **泳道全量（泳道=真相）**：承认三条真实好处（裸时间操作原生支持 / 渲染映射直接 / 拖拽时间线 UI 期权），但账单是三笔——现有每个 op 重写成 ripple 维护算法（且漏维护不报错：spec 合法、照常渲染、B-roll 静静盖在错误的句子上——"合法的谎"）；LLM 被迫基于过期快照做时间算术（校验拦得住越界、拦不住界内语义错）；合法形态空间无界（同道重叠谁赢 / 道间空隙补什么 / 多音道怎么混——每个问题 NLE 用交互惯例回答，我们只能长代码分支）。拖拽 UI 期权的前提门已被 ADR-035 永拒。**翻案条件**：(a) 开任何直接拖拽的时间线 UI；(b) 出现锚定真实表达不了的操作——最近候选 = 任意区间音频增益自动化，届时其家是一条 `gain_track` 数据轨，仍非泳道。
- **tracks:{} 容器重构**：见 Decision 9。
- **FCP 操作力学照搬**：ripple 手势（"剪两段、尾段后移"）在声明式模型里不存在——插入一段，输出轴派生，尾部自动正确。从 FCP 带来的是能力闭包（哪些事必须可表达），不是操作力学（怎么做这些手势——执行者是 agent 不是人，整个换了一组答案）。

**Consequences**:
- 此后加一条轨 = 一条注册项（+ 新 family 时一个渲染件）；phantom 自检把"触点可数"变成机械事实——第 N 条轨比第 N-1 条便宜且便宜得可证明。
- 12 操作走查表全项翻 ✅（结构级：可表示 / 可渲染 / 可继续改，fixture 实证；技能化入口随排期）。
- 存量 spec：段 `id` 新写必带、旧行读容忍（无 id 行在首个时间轴 op 落地时整体回填——旧行无层无锚，回填无损）；dev 数据可经 reset_db 清场，不构成约束（破坏性授权）。
- 禁令入档：禁 NLE 自由轨语义进 spec（任意增删道 / 同道重叠 / 转场画廊 / 关键帧自由编辑）；UI 永不见轨（层条目呈现为"这段配了画面"标记卡，随技能批）；kind 全枚举注册表守门；消费方禁逐字段特判；每轨唯一写者。

**Related**: ADR-016（契约锁定；L3 注记本条修订）/ ADR-020（stills Ken-Burns 拒绝与本条 transition 的边界：枚举进场边可、动效画廊不可）/ ADR-026（C2PA fold——layers provenance 必填）/ ADR-029（虚拟产物段进主时间轴）/ ADR-032（快照 undo——锚定面是其存储面）/ ADR-033（能力层双海拔）/ ADR-035（可操作画布永拒——泳道期权的前提门）/ ADR-039（注册表时刻同款迭代）/ ADR-043（派生投影同款哲学）；母文档 `docs/RENDERING.md`（§8 本条转正）；简报 `docs/tasks/done/track-model.md`（§7 配套层 / §8 附录 12 操作走查全表）

## ADR-045: 智能分镜能力线——YuNet 视觉引擎 + speaker_map 素材级事实 + crop_track 稀疏关键帧

**Context**: 08-19 能力线（PROGRESS 第三周）要把「双人同屏静态访谈 → 竖屏单人切换」与「单人中景动态追踪」落成 reframe 能力。轨道模型地基已交付（ADR-044 + 08-18 冷审修复批），crop_track 进场还差三块：检测引擎（人在哪）、话轮归属（谁在说话）、crop_track 数据形态（取景决策怎么存）。模型选型经许可证排查（用户以官方定价页实证）：InsightFace/SCRFD 预训练权重**仅限非商业学术研究**，商用需购买授权——SCRFD 及一切 HF repack 不可用于本产品。真实场景 = 静态访谈机位（用户确认）。

**Decision**:

0. **检测空间 ≠ 出图空间**：降采样找框、坐标映射回全分辨率取景——访谈 640 档 / 登台原生档（640 档在远景漏小脸）/ 远景 2×2 拼块兜底（spike 实证：可收回 4/7 漏检，剩余为片尾淡出无人画面）。
1. **视觉引擎 = YuNet（MIT）**：opencv_zoo 官方权重（bbox + 5 点关键点含嘴角），**权重 vendor 入仓库**（MIT 允许再分发；~230KB 消除一切下载/代理失败面，dev 与服务器零网络依赖）+ MIT LICENSE 文件并置；运行时 = `opencv-python-headless` 5.x（`cv2.FaceDetectorYN` 原生 API，NMS 内置），配 5.x 的动态输入封装 `face_detection_yunet_2026may.onnx`（2023mar 系同权重，WIDER Hard 0.7503 最强线；int8 变体全禁——精度降且 5.x 有全漏检 bug）。引擎缝住 `tools/vision.py`（asr.py 同款懒加载进程缓存）；工序（帧网格拼装 / 词轴切段 / 选页取窗）住技能包，不进 tools/。**tools 边界精确化**（ADR-044 第 8 条注记）：工序零新增进 tools/；**引擎缝按 asr.py 先例豁免**——vision.py 是第一个住户。
2. **隐私边界**：全程不做人脸识别（不知"是谁"）——只有位置与嘴部运动，全程不出网（faster-whisper 同款 EU 姿势）；密集计算全部本地化，云调用只剩稀疏语义判定。
3. **话轮归属 = 嘴部 ROI 运动能量主 + M3 仲裁辅**：whisper 词轴切话轮（间隙 ≥0.6s 断轮）；静态机位下逐话轮对比各说话人嘴部 ROI 帧差能量，能量比 ≥ 阈值（初值 1.6×，以真实片校准）确定归属；模糊轮（双人同动 / 能量比不足）M3 网格仲裁（每片 1~5 次云调用封顶）。M3 从"主力判定"降级为"模糊仲裁"——静帧猜"谁张嘴"恰是其最弱形态。
4. **speaker_map = 素材级事实**：VIDEO 第二 PROCESSOR（接 ASR 后，`asset_processing.py` 先例——素材级 / 可重跑 / hash 复用；AUDIO 不上——信号是视觉的，音频没有可检的框），**形态闸门先行**（whisper 话轮密度 + 1~2 次 M3 网格判多人/访谈才跑全量归属；单人素材零增量成本）。数据形态：`Asset.meta.speaker_map = {form, speakers:[{id, screen_hint}], turns:[{start, end, speaker}]}`（meta 先例：language）。消费方地图：reframe_clip（08-19）→ 本人含量门禁 v2（08-31，只从用户本人话轮学风格）→ 访谈选段偏好（后续）。
5. **crop_track = 稀疏决策关键帧**（data 家族轨，源时间轴）：`[{t, x, y, scale}]`——关键帧 = 一次取景决策（"这里切到 A"），非稠密逐帧；渲染采样器在相邻关键帧间固定 smoothstep（~8 帧，渲染常量不进契约——transition 枚举同哲学：枚举可、参数画廊不可）。**防眩晕分工**：最短驻留 / 死区 / 最大转速 = 写侧约束（技能工序，参数以真实访谈片看调）+ checks 住户校验（随 reframe 包同批回归，禁先注册空座位）；采样器只做平滑插值，永远简单。空轨 = 静态 `crop` 退化形态（语义不变）。
6. **reframe_clip 技能包**：三模式 `interview_switch`（双人访谈分镜，静态机位按说话人切换）/ `speaker_follow`（单人中景动态追踪）/ `static_center`（静态中裁，回退档）+ `auto`（按 speaker_map.form 选模）。形态写者写 `crop_track`（+静态 `crop`），`TrackDef.owner` 登记即得撞轨 422；对话可调用走 task_list（六 op 继续 `llm_visible=False`，本批不开放 LLM op 词汇）；估价 = `detect_seconds` 计量（自有基建零定价，`render_seconds` 先例；挂在本 run 选段后时编译期不可知，报 NULL）。
7. **一引擎两模式**：同一 YuNet 在访谈素材稀疏采样（1~2s 间隔刷新位置）+ 登台素材稠密采样（3~5 帧一检出轨迹）——复杂选型收敛为**一个引擎两种采样密度**；`speaker_follow` 不需要第二套选型。

**Alternatives（翻案条件随附）**:

- **SCRFD（InsightFace，侧脸精度轻量最强）**：预训练权重非商用（官方定价页实证）。**翻案阶梯**：YuNet 侧脸检出实测不达标 → MediaPipe（Apache-2.0）→ 仍不足则购买 InsightFace 商用授权（产品化路径）。
- **pyannote 音频话轮分离**（纯音频 SOTA）：torch 重依赖 + HF 门控模型。**翻案条件**：嘴部运动能量在真实访谈归属准确率不达标（双人小动作多 / 一方说话几乎不动嘴）。
- **自训检测器**：架构 MIT 自由，但标准训练集（WIDER FACE）同样仅限非商业研究 + 1–2 周 ML 工程；蒸馏 SCRFD 权重产伪标签仍属非商用权重派生。**翻案条件**：人脸分析成为产品核心差异点且有常驻 ML 人力。
- **M3 全程判定**（零新依赖）：静帧网格猜"谁张嘴"是其最弱形态；逐帧追踪贵且抖（60s 素材 0.5s 间隔 = 120 次调用）。只任形态归类与模糊仲裁。
- **稠密平滑关键帧 + 线性插值**：契约肥大、防眩晕参数散落数据。**翻案条件**：sparse + smoothstep 在真实素材出现可见跳变且写侧平滑无法吸收。

**Related**: ADR-044（轨道地基；crop_track 进场路径与 tools 注记本条落地）/ ADR-016（渲染器黑盒——采样器只进 packages/clip）/ ADR-020（Ken-Burns 拒绝的边界：crop_track 是 video 源取景决策轨，非 stills 动效）/ ADR-026（speaker_map 不涉 C2PA——分析事实非生成内容）；简报 `docs/tasks/done/reframe-line.md`；双验证 spike 与排期见 `docs/PROGRESS.md` 第三周


## ADR-046: Studio 视觉骨架重塑——灰底填充阶 / 影子只属浮层 / 实体丸化 / 海报优先画廊 / 去全局 header

**Context**: 2026-08-20 MiniMax Design 发布日走查（九屏）+ Agent Opus / FLORA / ElevenLabs 对照（证据层 `research/minimax-design.md` §8–§11），暴露五处存量病：① 浅色 composer 白上白读作 wireframe（dark 反而成立——0.12 底 vs 0.21 卡自带阶）；② 配方画廊五根 9:16 强制竖槽 + 横源 letterbox = "黑色墓碑"，且 `posterUrl` 字段存在却被 autoplay 永远跳过、全站无封面概念；③ entity blocks 骑缝设计在截图里读作渲染瑕疵，灰底假设下必然融合；④ 账户区是 Opus 式平铺 list，信息层级缺位；⑤ AppHeader 只装 theme/lang/bell 三个工具却占一条常驻通顶 band。色役粒度盘点（§10）进一步显示：精致感的来源是**角色粒度细**（~20 个可见色役各有阶位），不是品牌色。

**Decision**:

1. **浅色底色定律翻案**：studio（`_app`）`--background` light 纯白 1.0 → **0.96 中性灰**（#f5f5f5 族；暖色调否决——与暗色中性族同宗，用户审美样本全中性）。白卡升格为"最亮一层"，靠填充阶浮起。**双主题高度定律统一为一条：浮层 = 更亮的填充落在更暗的底上**（light 0.96→1.0 / dark 0.12→0.21）。landing（`/`）不动，营销音域分离（Scope 条款已有）。hover `--accent` light 随底重推导 0.95 → 0.92。
2. **影子只属浮层**：文档流表面（卡 / composer / 媒体 tile）双主题一律无影——"产品卡 hairline+shadow-lg"条款与 hero-flat 特例一并退役；浮层（overlay-surface 雾面家族）浅色标配耳语级 `shadow-xl`（把玻璃从内容上揭起），暗色保持无影传统（雾面透光自分离）。
3. **实体丸化 + chips 顶置**：composer 骑缝 blocks 退役（自我批判四条：信息密度倒挂 / 剪影打断 / 跨双表面必坏 / 底排失衡之源）。实体 = 底排左簇 ghost pills（Assets 📎 / Persona 16px avatar），**值状态律 = meta→foreground 一步变色**（无填充无彩色）；pills 开雾面 Popover 面板（`side="top"`，浮层影首个正当场景），AssetsModal / PersonaPickerModal 退役（深度管理归未来资产中心页）。暂存文件 = **卡顶类型化 chips 带**（视频缩略图+时长 / 音频波形+时长 / 文档图标+页数 / 上传中转圈百分比，× 即删）——摘要归 pill、清单归 chips、富展示归面板行。
4. **画廊**（卡面形态与布局 2026-08-23 起由 **ADR-048** 整体取代：工艺示意图封面 / 均匀 4 列网格 / 证据层移交 overlay / badge·chip·featured 退役）：本条残留有效部分 = **click = 检视 overlay 是唯一发射路径**（hover 填充二次否决维持：我们的卡面是多产物组合的 teaser + 配方素材依赖，检视是认知步骤不是摩擦）。
5. **去全局 AppHeader**：工具（主题/语言）迁账户 console；**通知 = 内容区右上角唯一浮动芯片**（圆角方块 + 未读点，右上槽位全 `_app` 保留，页面级控件永不占此角——Agent Opus 证据）；移动端留浮动 trigger。账户区两层架构：rail footer popover = 高频 console（身份头 / inset 账户组 / 行内 segmented 偏好 / 帮助段），深度偏好归设置页（FLORA modal 先例）。
6. **色役表治理**："角色 → token × 双主题"对照表为组件唯一取色来源（禁直引色值），缺位角色补 token（send-disabled、group-title、icon-chip-bg、toggle-track）；角色全住中性阶梯，多角色 ≠ 多颜色。表随简报 `tasks/home-skeleton-revamp.md` 落地并当验收清单。

**Rationale**: 层级来自阶不来自色（Tailwind 哲学 + MiniMax 黑白多层实证）；影子物理（白底困境的止痛是灰底，不是更软的影）；形态跟信息密度走（pill 36px 说一个词的值为足）；发射深度取决于卡面代表度（卡面越完整代表产物，快捷发射越浅）；交互基准线被大厂产品持续抬高，骨架一次到位比逐面补丁省返工。

**Alternatives（翻案条件随附）**:

- **浅色恢复 shadow（hero 开影）**：白底困境的治标版，被灰底方案整体替代。**翻案条件**：灰底在真实内容密度下被读作"脏/灰扑扑"（landing 对照组失真）。
- **CSS columns 纯样式瀑布流**：零 JS 但元素无法跨列，featured 大卡出局。**翻案条件**：grid+dense+span 的 JS 重排在低端机实测掉帧。
- **hover Use Prompt 双动作**（FLORA/MiniMax 先例）：二次否决维持 08-08 清洗判例，理由见 Decision 4。**翻案条件**：配方简化为单产物 + 零素材依赖的那类（若存在）可个案重议。
- **bell 降 rail 导航项**：通知的时效性（"你的片子好了"）需要全页一瞥可达，埋进 rail 伤可发现性；浮芯片方案兼得"无 header"与"一瞥可达"。

**Related**: ADR-035/036（只读图与配方 overlay 纪律不变）/ ADR-040（配方=提示词——hover-fill 否决的教义同源）/ ADR-041（结果画布 dock 体系不受影响）/ ADR-016（clip-spec 契约零关联）；证据 `research/minimax-design.md`（§8–§11 二轮证据 + 色役盘点）+ `research/flora.md`（EU AI Act 偏好项）；简报 `docs/tasks/home-skeleton-revamp.md`（施工与验收）；需求池登记 EU AI Act 水印偏好一条后续

**附（2026-08-21 拍板）**：点阵采纳——home + 结果画布两个工作台面专用（"making surface"信号 + 平移感知）；配方 = muted-foreground 30%（light）/ 40%（dark）、1.5px 点、28px 网格（`dot-grid` utility 与 FlowView `dots` prop 同源）；第三处点阵面即违规。demo 封面维持现烘焙帧（重烘取消）。同日走查修订（用户逐帧对照 MiniMax Design）：① 滚动编排采纳——home 改固定 app-shell（路由根 `h-svh` 不滚、点阵固定视口、画廊唯一滚动口 `no-scrollbar` + 顶 fade），hero 文案级 fade 折叠，composer 常驻顶 chrome 并 compact 变形（pill 隐藏 / 输入带收缩，send 常驻，迟滞阈值）；② 点阵配方细化——1px 点、26px 网格、muted-foreground 20%（light）/ 18%（dark）（原 30%/40% 夜间过重）；③ 滚动条治理——`:root` / `.dark` 挂 `color-scheme`（原生滚动条随主题），home 滚动口无滚动条。同日二轮走查修订（MiniMax 逐帧对照）：④ composer rest **居中停驻**（hero 时刻，`pt-[20vh]`）→ 滚动滑上钉顶成**单行 half-radius（stadium）探索条**——rounded-full 禁令**第三例外**（用户拍板）；⑤ 单行条布局对齐 MiniMax 标准件（左 attach 带计数 + 单行输入 + 右 send），chips 带/控制行折叠，send 改绝对锚点跨形态常驻；⑥ hero 改纯 fade（撤高度折叠，行程耦合）；⑦ sticky chrome `::before` 点阵背板防宽卡露头。同日位置对批（用户双屏对照）：⑧ rest 集群下移居中（spacer 20vh→28vh）；⑨ **核心 hero（标题）常驻**——钉顶收缩悬于单行条之上（MiniMax docked 态 parity：logo+标题永驻、subtitle 消失），subtitle 改 chrome 内部折叠（钉点零位移）。⑩ **设置 = 共享弹窗组件，不设页面**（MiniMax/FLORA 对照拍板）——SettingsDialog 左 nav + 右内容，`useSettingsDialog()` 随处召唤（memory 等未来深面同构入列）；`/settings` 路由退役为 channels OAuth 回调 shim（toast + 开 dialog + 弹回 home）。⑪ **console 分组律**（MiniMax 对照拍板）——inset 账户块只装价值面（plan/credits/订阅），系统面（设置）降级入偏好组；偏好组改 MiniMax 行解剖：行标签 + **尾置** segmented（theme 图标三态 / 语言 EN·中，inset 轨 + card 滑块），深面行带 chevron。⑫ **滚动编排的形变一律滚动链接，禁时钟过渡**（三轮走查拍板）——位置是滚动驱动的即时位移，形变若走 300ms 时钟，快滚必现半途态；`dockP` = 距钉点末 140px 的 scrollTop 插值，全部形变属性随动，阈值/迟滞废除（纯函数无振颤）。⑬ **home hero = 品牌锁up + 品类句**（MiniMax 解剖，用户拍板原话）——`LogoMark`+"Repurposer" 常驻钉顶（em 尺寸 mark 随字号缩放），品类句「你的自媒体Agent团队」折叠；welcome 接待式退役，旧 `welcomeTitle/welcomeSubtitle` 键清尸。⑭ composer pill 面板**一律向下开**（`side="bottom"`——向上开盖输入区）+ 面板滚动列表 `no-scrollbar`；docked 条下方留白加大（`pb-14` + 32px 溶解带），卡片不贴条底消失。⑮ **列表一处律**——面板是其暂存列表的展开形态：Assets 面板开则 composer chips 带收起，同一列表永不同帧双呈（计数 pill 留锚）。⑯ **面板行解剖 + 画廊带声**（同日四轮走查拍板）：面板行 = mock 转正解剖——方形类型 tile + 名称/类型化 meta 两行 + × 居中，**列律：文件列方、身份列圆**（assets 方、persona/Auto 圆）；配方卡 hover 带声裁定 2026-08-23 起随网格视频表面消失而迁移至 overlay 示例 tab（ADR-048——点击 = 手势，带声天然成立）。⑰ **半径简化 + padding 非对称**（同日五轮走查拍板，MiniMax 对照）：composer 半径撤出 dockP 插值——常量 40px（展开态大圆角），坍缩成 56px 一行条时 CSS 半径帽自动裁至 28px = stadium 从盒模型自然涌现（「只有坍缩才 full」零代码）；padding 改非对称 `px-5 pt-5 pb-3`——底 chin 收紧 12px，控制行贴底（原 p-5 底 chin 过厚）。⑱ **hover 动作**（同日六轮走查，MiniMax 逐帧对照；2026-08-23 随 ADR-048 修订）：hover 浮出 = 白色 stadium Remix 丸居中 + expand 钮右上（声音开关随网格视频表面退役）；Remix/expand 均只开检视 overlay（ADR-040 唯一发射路径不破——hover 增加发现性 affordance，不产生第二发射路径）。⑲ **composer 壳 = shadcn InputGroup 收编**（同日七轮走查拍板）：布局已收敛组件预设解剖（chips block-start / MentionEditor 挂 `data-slot=input-group-control` 当 control / 控制行 block-end），手卷 Card+CardContent 退役——白得 focus-within 环、cursor-text 点击聚焦、addon 折叠 border-box 自带 padding 裁剪；描边按卡律换皮（`border-transparent` + 发丝 + bg-card 无影）。**密度律：padding 住 addon 不住容器**——px-4 侧 / pt-4 chips / pb-3 chin，编辑带 py 16→8 随 dockP 防单行裁字；条高 44px、send 锚 16·12→4。

## ADR-047: 产物质量线——剪辑师层 + 有界质检环 + 评审回 chat（tool-loop 否决边界明文化；钩子闸 2026-08-24 转 ADR-049 退役）

**Context**: 2026-08-22 用户判词——"图文视频把图片轮播放几个字，这样的产物配不上用户花钱"。MiniMax Design 证据（`research/minimax-design.md` + 08-22 二手评测交叉）触发全链审查，读码归因：**storyboard（WHAT）与 clip-spec（怎么渲）之间没有 timeline 创作层**——逐拍决定由配方默认值 + 阅读速度常量代劳（`tools/stills/procedure.py` 节拍器）；产物出炉后无质检回看；无质量度量。两轮外部评审（harness 层 + domain 层，Grok/Gemini/Claude 三源）收敛验证归因并供给设计契约。

**Decision**:

1. **剪辑师层（editor agent）**：storyboard 与 clip-spec 编译之间新增 timeline 创作层——N-30 声明式新成员（团队的下一成员），吃理解层节拍地图、吐节拍方案（beat plan：图序/运动/切点/强调的逐拍决定）。**单发上限 ≤8–15 拍 / 30–45s**（三源收敛），超出走大纲→逐拍两段，拍间靠显式交接状态（时间锚点/上一拍视觉态/已用素材清单/累积强调历史）。
2. **理解层 v2（节拍地图）**：`MaterialUnderstanding` 扩为素材级——climax/emphasis/quotables/topic boundaries/visual anchors/filler regions，上传时跑 + asset 级复用（汇合需求池「素材理解前移」）。铁律：词级时间戳确定性地基 LLM 永不覆写；**语义强调与声学强调分字段存储**（不一致本身是仲裁信号，预合并 = 自信地错且不可溯源）。
3. **质检环（verify 节点升级）**：吸收旧简报期 3 传输机制（kind + QualityBounce），升级裁决语义——确定性优先（可测量项零 LLM）/ 逐轮独立打分 **best-not-last** / 字段白名单最小 diff 修复 / 首轮过即跳轮 / 双败升级 interrupt（复用既有机制；fidelity 类维持 needs_human 非阻塞徽章）。LLM judge 在纪律下引入（pairwise 冻结基线 / 样例锚定 / 证据先行 / 校准集）——旧简报"judge 单独评审"条款由此兑现。
4. **重规划边（tool-loop 否决边界明文化）**：常备否决的对象 = **模型当编排者**（ReAct 式运行时决策），不翻案；**节点内有界环**（单目的、≤2 轮、结构化反馈、图调度进出）= 合法形态。质检失败的机械路由：修复所需信息不在理解层 schema / 超出单节点参数域 → 交还意图层重规划（汇合需求池 P1「执行中自适应重规划」）；retry 不中自动升级（schema 错误首 pass 常伪装成参数错误）。素材级不足走诚实降级（标题卡开场/换素材），**禁假造钩子**。
5. **评审回 chat（2026-08-24 翻案）**：原"钩子预览闸"条款整节翻案——评审 AI 钩子质量走 chat 收敛（ADR-041），节拍方案（§1 beat plan）是 chat 评审的可寻址界面；渲染服务 `preview:{seconds}` 黑盒参数退役，AskPayload.previews / HookPreview / HookTrim / swap_hook_shot 全套删除，降级由 AI 自动 set_title 评估，详见 ADR-049。
6. **尺子先行**：施工顺序 = 解剖（craft 清单 + 四层归因证据表）→ 理解层 v2 → 剪辑师 → 质检环 → 节拍方案产品面（接 ADR-049 评审界面落位）。§2.1 craft 语法表全部数值 = 编辑部惯例先验，解剖校准前不作验收标准。

**Rationale**: 质量的 80% 在隐性剪辑知识的形式化（外部评审收敛），而形式化的载体已有（指令包装配注入 + track 模型 + 词级时间戳/speaker_map/reframe 数据资产）；缺的是"谁做逐拍决定"的层与"谁检查"的环，不是地基。三源独立否决模型驱动编排翻案——DAG 的编译期估价/确定性执行正是有界环能安全存在的前提。外部评审全部结论 = 模式先验，解剖与台账产出自己的数据后校准。

**Alternatives（翻案条件随附）**:

- **模型驱动编排（tool-loop 翻案）**：三源独立否决（成本失控/不可审计/参数坍塌）。**翻案条件**：台账落地后的实测证据（repair 失败率/单发上限实证）证明声明期分工在某场景结构性不足。
- **静态确认闸（文本分镜/首帧）**：2026-08-24 翻案——替代方案（节拍方案为 chat 评审界面）由 ADR-049 实施；本条替代路径废止。
- **每表面独立 agent 声明**（MiniMax 剪辑 Agent/导演台 Agent 式）：维护漂移 + 跨面认知断层；我们的答案 = 同一它 + 作用域上下文（ViewScope，后续简报）。**翻案条件**：场景上下文组装的边界泄露实测不可控。

**Related**: ADR-039（四层地图 + N-30 声明机制）/ ADR-016（clip-spec 契约不动）/ ADR-041（表面纪律：进度不进图、编辑走 chat）/ ADR-049（§5 翻案去向：钩子闸退役）/ N-42（指令包装配注入——剪辑工艺包的载体）/ N-25（用户面单助手不破）；简报 `docs/tasks/output-quality-line.md`（施工与验收）；旧简报 `docs/tasks/output-quality-verify.md`（期 3 被吸收升级）；需求池「质检节点」（提级 P1）/「agent 调用台账」（三信号 schema）/「执行中自适应重规划」（路由判据）/「素材理解前移」（汇合理解层 v2）/「节拍方案产品面」（接 ADR-049）

## ADR-048: 配方画廊 v3——三轴模型（产物形态 × 输入路径 × 渠道适配）+ 招牌菜组织原则 + 三级准入闸门

**Status**: Decided (2026-08-23；v3 修订 2026-08-27，用户拍板)

**Context**: 画廊 v1（真实媒体 + 瀑布流）死于产物画幅太杂；v2（08-23：工艺示意图封面 + 均匀网格 + 证据层移交 overlay）解决了"卡面用什么展示产物"的表面问题，但把组织原则顺手换成了**按输入类型遍历**（行一有录像 / 行二无录像）——逻辑终点是"每种输入 × 每种体裁都要有卡"。2026-08-25 stacked 叠卡金句（小红书/TikTok 已验证体裁）找不到座位、只能塞进 quote-cards 凑合；同一道菜多输入路径（录像抽帧 / 照片+文稿 / 纯文稿）与 overlay 写死 "Source video" 的文案互相打架；外部评审（Kimi）的"chip 预设行 / 变体缩略图"提案触发全层重议。用户拍板根判：**画廊不为覆盖负责**——覆盖是选题库的活（ADR-042）；卡 = 招牌菜，霸道程度是唯一组织原则。

**Decision**:

1. **三轴模型**（卡的定义正交分解）：
   - **卡轴 = 产物形态**（用户得到什么）——卡的唯一身份，霸道程度排序。
   - **路径轴 = 输入 → 工艺**（用户给什么）——宽槽，管线按输入画像自适应选路径（materialize 注入，ADR-043 现成机制）；路径打通一条槽里加一类，**同一道菜长路径永远不是新座位**。
   - **适配轴 = 渠道**（发到哪）——发布期变量，**永不进卡**（v2 第 4 条升格为公理）：LinkedIn / X / Ins / TikTok / XHS 的真实差异只剩格式（画幅/时长/字幕规范）× 语气（人设风格层）× 机制（OAuth）三层薄皮，全在卡的下游（POSITIONING 平台定位"适配默认"）。文案纪律保持专家腔不变，产物形态全渠道通用。
2. **组织原则 = 招牌菜，画廊不为覆盖负责**：卡存在的唯一理由 = demo 霸道到 ICP 想截图发给同事 + 试做一次被送进主链路（chat）。覆盖需求的家 = 选题库/定位根（ADR-042，W8–W10）：首访靠招牌菜接住，回访靠"你的素材还能切什么"接住。**画廊 → 选题库接力点**：首跑完成后"下一步"提议用本段素材挖选题（口径 W6 对齐，实装归运营端迭代）。
3. **准入三级闸门**：① **场景真实性**（专家真实高频场景，人造场景一票否决，沿用）② **形态或环路不可替代**（ChatGPT 测试，环路价值可上面者豁免，沿用）③ **demo 霸道**——成对示例本身就是卖点（叠卡帧墙、声纹对照包级别）；示例平平的，能力再真也不上桌。体裁问题标准答案：一个能力族只摆最霸道的一种形态，其余形态归 chat 能力——新体裁不再触发"找座位"。
4. **卡面三行写这道菜，不写能力族**：promise 描述 demo 那道菜的形态，与示例永是同一道菜。文案承接四层：卡面纯菜（不加 meta）→ overlay `promptHint` 升格为"还能怎么点"（改口示范 + 能力族暗示，纯文案不做控件）→ 示例 tab 不说话的广度（多形态示例平铺）→ 画廊末尾一句总承接 + 流程内教学（预填模板可改 = 第一次提示词教学）。
5. **v2 形式全部保留**（08-23 原判 1/2/3/5 条不动）：黑白灰工艺示意图封面（200px 无字测试）/ 卡面状态机（rest 静态 → hover 过程动画 + Remix 丸 + expand，click = 检视 overlay 唯一发射路径）/ 均匀网格零真实媒体 / 证据层 = overlay 示例 tab 成对前后对比（拿不出真实成对示例的卡不进网格）。
6. **输入槽两类卡规则**：**转化类**（形态 = 改造你的录像：高光切片 / 访谈分镜 / 多语言字幕 / 原声配音）= 窄槽必填，Input 小节直说要什么——窄是这道菜的本性；**合成类**（素材是原料：金句卡 / 轮播图 / 社媒帖 / 图文视频）= 宽槽任选 + 可空（copy-writer 无素材 lift 已落地），Input 小节"给什么都行"。槽宽 = 管线真实路径的边界——不更宽（诚实纪律），不更窄（不绑死）。`input_slots` 增"任选一"语义（字段命名随实施过 NAMING §7），overlay 发射闸门同步。
7. **阵容 = 八卡六形态**（RECIPES §4 同步）：竖屏短片（高光切片 / 访谈分镜）/ 多语言版本（多语言字幕 / 原声配音）/ 图文轮播视频（图文视频）/ 金句叠卡（金句卡）/ 轮播幻灯（轮播图）/ 帖子长文（社媒帖）。排序 = 霸道序：**原声配音 → 金句卡 → 高光切片 → 多语言字幕 → 图文视频 → 轮播图 → 访谈分镜 → 社媒帖**（网格从左到右自然落位，行语义退役）。两处调整：**金句卡 = 叠卡本体**（legacy 逐条 fan-out 与 `layout_mode` 退役，帧卡 Output 化带 source_ref 寻址，工程见 `docs/tasks/quote-cards-redesign.md`）；**社媒帖 demo 重修为风格对照**（同素材"无人设版 vs 人设版"并排——文本族过闸门③的标准姿势，随烘焙批）。
8. **阵容治理**：任何座位变更（进/出/合并/拆分）必须附翻案条件 + 认路级证据（复述测试 / 真实用户行为），不当周翻案。本次 v3 落地 = 最后一次结构性翻案。

**处境 × 卡映射**（v3 动机章——卡的合法性由处境授予，不由"我们做过这个能力"授予）：

| # | 处境（用户原话） | 手里素材 | 频次 | 谁接 |
|---|---|---|---|---|
| S1 | "我上周那场讲座录得不错，躺着太浪费" | 长录像 | 高 | 高光切片 |
| S2 | "要持续活跃，不知道发什么" | 零散素材+讲稿 | 最高 | **选题库**（ADR-042，不是画廊的活） |
| S3 | "我写了篇论文/长文，值得被更多人看到" | 文稿 | 高 | 社媒帖 / 轮播图 |
| S4 | "我的受众不止一种语言" | 单语视频 | 中高 | 多语言字幕 / 原声配音 |
| S5 | "我没录像，只有照片和 PPT" | 照片/课件+文稿 | 中 | 图文视频 |
| S6 | "我们访谈录了好多期" | 双人对话录像 | 中 | 访谈分镜 |
| S7 | "下周有会议，得赶紧发点啥" | 任意 | 中 | 快菜（图文视频/社媒帖） |
| S8 | "这段话太亮了，想单独发出来" | 录像/文稿 | 中高 | 金句卡（叠卡） |

**Consequences**:

- RECIPES §4（六形态阵容 + 霸道排序 + 两类卡）/ §4.8（三级闸门）/ §7.1–7.3（input_slots 语义、承接四层、排序无行语义）同步修订；简报 `docs/tasks/quote-cards-redesign.md` 修订到 v3 目标态。
- ADR-046 D4 与附⑯⑱ 的画廊部分维持 08-23 取代状态；「click = 检视 overlay 唯一发射路径」不破。
- recipes.py 注册表排序调整 + 金句卡工程（叠卡本体 / 帧卡 Output 化 / 宽槽三路径）+ 社媒帖风格对照 demo 烘焙随 W6 收尾与 W7 前排实施；迭代欠账清单（quotes.j2 拼写 / demo/ 前缀 / S13 断言 / 死代码）随简报工程清单一次清。

**Alternatives（翻案条件随附）**:

- **chip 预设行**（外部提案：overlay 加 ≤3 维度预设 chip，点击改写 prompt 句子块）：否决——预设参数控件禁令（RECIPES §7.2）与 promptHint 可点形态证据闸（RECIPES §10）已覆盖同类诉求；表达轴的可见性 = prompt 文本 + promptHint + 示例 tab 三件套。**翻案条件**：复述测试级证据证明用户在 overlay 内认不出可改口味（实测认不出，不是"可能会"）。
- **变体缩略图真实媒体上卡面**（外部提案：≤3 个体裁变体缩略图当认路承重墙）：否决——v1 真实媒体死于画幅杂乱，网格零真实媒体是 v2 根基；体裁认路的标准答案 = 示例 tab 多形态平铺 + 同族只摆最霸道形态。**翻案条件**：示例 tab 打开率 / 认路实测证明用户根本不进 overlay。
- **字幕 + 配音合并为一卡**（"一个外语版本意图"论）：维持 08-23 拆分原判——"保留原声看字幕"与"用我的声音说外语"是两种意图，配音卡名把声纹克隆护城河写进菜名。**翻案条件**：认路证据显示用户在两张卡间犹豫选错。
- **画廊按渠道出卡**（LinkedIn 卡 / TikTok 卡）：永久否决——渠道是适配轴不是卡轴（第 1 条）。

**Related**: ADR-046（D4/附⑯⑱ 维持取代）/ ADR-040（唯一发射路径）/ ADR-042（选题库 = 覆盖的家，画廊→选题库接力点）/ ADR-043（materialize 输入画像注入 = 路径轴机制）/ ADR-035/041（画布纪律）；RECIPES §4/§7 / STRATEGY §5 / POSITIONING（平台定位 = 适配轴）；简报 `docs/tasks/recipe-gallery-v2.md`（v2 施工）/ `docs/tasks/quote-cards-redesign.md`（v3 金句卡工程）

## ADR-049: 钩子预览闸退役——评审回 chat，渲染无闸，节拍方案为评审界面

**Status**: Decided (2026-08-24)

**Context**: ADR-047 §5 钩子预览闸落地（commit a867112）后用户产品走查判其过度——dock 三路径（确认 / 调整 / 降级）把评审 AI 钩子质量的责任交给用户，知识专家用户不擅长此评估（决策疲劳），且哲学冲突：产品核心流（ADR-041 + ADR-035 衍生）= **必要评审在 chat 完成 → chat 收敛后走渲染 → 渲染好进 canvas node**；hook gate 在 chat 之外插了一段"评审视频"环节，违反三段不破的边界。正确的产品评审面 = **节拍方案**（beat plan，ADR-047 §1）——timeline 创作层的中间产物（图序 / 运动 / 切点 / 强调），纯数据 + 图片引用，零渲染成本，chat 评审的可寻址产物（AGENT_ARCHITECTURE 总论：每个中间产物可寻址、可复用、可单独重跑）。让用户在 chat 里看节拍方案卡片 = 评到 AI 决策内容本身；hook gate 把 beat plan 翻译成视频让用户看 = 绕了一步。

**Decision**:

1. **hook_gate / release_renders 节点退役**：`app/pipeline/hook_gate.py` 整文件删除；`orchestrator.py` §2.5 编译期注入块删除；`clips/node.py` 闸感抑制分支（`gated` 检查 + `_pend_suppressed_base_renders` 闸调用路径）删除——select_clips 正常扇出 render，render_status 走原 pending 路径。
2. **渲染服务 `preview:{seconds}` 参数退役**：`apps/render/src/server.ts` 与 `render.ts` preview 分支删除——黑盒内部参数，无外部契约，直接删除。
3. **AskPayload.previews / HookPreview / HookTrim 删除**：`app/models/schemas.py` 三类删除；前端 `QuestionDock.HookPreviewStrip` 删除（QuestionDock 回到纯 choice / task_book 二态）；`en.ts` / `zh.ts` `hookGate.*` 翻译键清尸。
4. **swap_hook_shot op 退役**：`app/operations/registry.py` 注册删除；`SetTrimParams` / `set_trim` 保留（chat 评审调尾切点是 chat 评审的一部分）；渲染端 `packages/clip/src/types.ts` `image_shots` 字段保留（节拍方案仍消费）。
5. **降级走 AI 自动 `set_title`**：质量差时 AI 评估钩子自动降级（标题卡开场）——不需要用户决策；保留 set_title op（运行期 AI 触发）。
6. **节拍方案 = chat 评审界面**：beat plan 作为中间产物落到 Output.payload 或新表——chat 评审展开的卡片化形态（具体渲染位置下一期拍板，本 ADR 只拍板机制退役 + 节拍方案为评审界面）。
7. **闸感抑制工程价值归位**：原闸感抑制（避免白烧）通过 chat 的报价 fold + AI 自评质检环覆盖——产品不再有"渲染前用户卡"的形态。

**Rationale**: 产品哲学一致性优先——chat-as-review / render-as-execution / canvas-as-result 三段不可破；hook gate 评估的是渲染结果而非 AI 决策内容，评审点错位。AI 自评（质检环 + 自动 set_title 降级）保留——评估的是 AI 自身产物，不交给用户——符合 ADR-041 "评审走 chat 不走 canvas" 与 ADR-035 "可操作画布永拒"。闸感抑制的工程价值（避免白烧）由 chat 收敛 + AI 自评覆盖，无须用户介入。

**Alternatives（翻案条件随附）**:

- **保留 dock 三路径**：知识专家评审疲劳实测低于收益——拦截率统计显著 + 调整 op 真实使用率 > 阈值。**翻案条件**：自有数据证明用户主动评审收益 > 决策疲劳。
- **节拍方案卡片由 chat 流承载 vs overlay vs canvas 节点 metadata**：本 ADR 拍板 beat plan 为评审界面，不决呈现位置；后续单独拍板（建议合并入节拍方案卡片化下一期）。
- **AI 不自动降级，保留 chat 主动 set_title**：本 ADR 默认 AI 自动降级——chat 主动是补充入口；不反对 chat 里说"加标题卡开场"。

**Related**: ADR-047 §5（被本条整节翻案）/ ADR-041（评审在 chat、渲染进 canvas 的哲学基底）/ ADR-035（可操作画布永拒不变）/ ADR-040（chat 唯一发射路径不变）/ ADR-039（节点对象化 + 估价 = fold，渲染前用户可见是估价而非视频预览）/ ADR-001（hook_gate 落地 commit a867112 作为机制退役的前置基线，其上 4 bug 修复为本 ADR 落地时的清理参考）

## ADR-050: 会话不跨长等待——计量内存累积 + 渲染会话收窄 + runner 禁污 Session-2 节点 + DEFERRABLE FK（D9 死锁族）

**Status**: Decided (2026-08-27；根因补刀 2026-08-28)

**Context**: quote-cards v3 e2e 连跑把 dev worker 反复卡成永久 wedge。pg 取证（pg_stat_activity / pg_locks / pageinspect 逐层下钻）最终定位三个同族病灶，共享一个形状——**runner 的 Session 2 持有 `workflow_steps` 行锁横跨 LLM 等待，行内第二个写者等它，而它等第二个写者**（应用级自死锁）：① 计量 `record_usage` 每次 LLM 调用另开 session UPDATE 本 step 行；② 渲染 `render_output` 持 session 横跨最长 900s 渲染 POST；③ **质量打回重跑时 feedback-pop 走 `node.spec = spec` ORM 赋值**——Session-2 node 变脏，下一次 autoflush（outputs INSERT 时）锁本 step 行至 run 尾，runner 自己的 display writer（`_fill_summary`，own-session jsonb_set）等自己的事务——pageinspect tuple 版本对（xmin/xmax）实锤。verify bounce 路径是触发点：只有 attempt≥2（带 feedback）才脏节点，这解释了"首跑绿、连跑 wedge"的观察史。

**Decision**:

1. **计量改内存累积（`app/metering.py`）**：`bind_workflow_step` 绑定 contextvar 内存台账；`record_usage` / `record_media_usage` 只改内存、**零 SQL**。`execute_step`（orchestrator.py）在执行尾段用 `merge_accrued_cost` 归并一次写入——成功 / Suspend / QualityBounce / 瞬时重试 / 失败五个终态分支全部记账（每节点 N 次写 → 1 次写）。cost 形状 `{prompt_tokens, completion_tokens, fixed_cost, units?}` 不变；跨 attempt 累加（与旧 per-call 机制语义对齐）；空台账 → cost 保持 NULL（估价对账 SQL 继续忽略未计量节点）。**不加表、不加字段**。
2. **render_output 会话收窄（`app/pipeline/rendering.py`）**：短 session 快照行数据（spec / files / project_id / user_id / lang）→ **无 session** 横跨渲染 POST → 新短 session 做 guarded 终态写入（morph 竞态守卫条件不变）。`_mirror_superseded_node` 签名由 `Project` 改收 `lang`。
3. **runner 禁污 Session-2 节点（铁律）**：Session 2 内对 step 行的写只属于 execute_step 尾段结算；runner 中途要写 spec 一律走 `step_display` 的 own-session 原子写（`_pop_spec_field` jsonb `-` 减法 / `_set_*` jsonb_set）。两处 feedback-pop（`derivative_dispatch` / `clips/node`）已改 `_pop_spec_field`。
4. **四条 runner-父行 FK 改 DEFERRABLE INITIALLY DEFERRED**（migration `c3a9e71f52d0`）：`outputs.workflow_step_id` / `outputs.project_id` / `operations.project_id` / `workflow_steps.run_id`——Session 2 中途 INSERT 子行不再对父行持 KEY SHARE 至提交，父行写者（display writers / maybe_finalize / run 状态翻转）永不被 mid-run 锁窗口卡住。完整性不变，检查挪到 COMMIT。
5. **DB 保险丝**：`ALTER ROLE <app_role> SET idle_in_transaction_session_timeout = '600s'`——任何环境（dev 已落地；**部署新环境时必做**，本条即部署说明）。保险丝是兜底不是许可。**120s 首日即被翻案**：Session 2 横跨 runner 的 LLM await 是保留设计，director_understand 一次调用 + schema 修复重试 ≈ 2 分钟纯等待，120s 把健康事务杀成 `connection is closed`——保险丝只防永久 wedge，10 分钟足以把灾难收敛为有界失败。
6. **dev 脚本清理纪律**：FK DELETE 前先 terminate `idle in transaction` 超 15s 的他者 backends（`bake_quote_chain.py` / `accept_quote_card_family.py` 等脚本同款片段；`pg_stat_activity.query` 全是参数化语句、无字面 id，项目级文本匹配不可行，dev 箱上 >15s idle-in-tx 即 wedge 类）。
7. **execute_step 异常分支 node=None 守卫**：清理跑赢 worker 时（项目被删）三异常分支直接返回，不再 AttributeError。

**明确不做**（用户拍板出闸）：runner Session 2 持有权重构（污节点已禁 + FK 锁窗口已关，死锁类整族消除，无须更大 blast radius）；`agent_calls` 台账（需求池 P1，第十一周）；verify bounce 路径本身（触发点随 ③ 修复消失）。

**Rationale**: 死锁的根不是"session 持有太久"，而是"行内长等待期间存在第二个写者 + Session-2 行锁"。把第二个写者消灭（计量归并）、把 Session-2 的行锁窗口关到最小（禁污节点 + FK 延迟到 COMMIT）= 锁族整族死亡，且语义逐条对齐旧机制（累加记账 / NULL 纪律 / guarded 写 / feedback 只搭一轮）。

**Alternatives（翻案条件随附）**:

- **runner Session 2 也拆短**：本 ADR 出闸。**翻案条件**：出现新的"runner 执行期必须写同一行"的需求（先审视能否走 own-session 原子写或尾段归并）。
- **计量入独立队列表再异步落账**：否决——无新表新字段（用户裁定），内存累积已满足所有消费方（RunResponse.cost = 序列化时聚合，无中途可见性需求）。
- **display writers 加 lock_timeout 跳过**：否决——feedback-pop 修复后撞锁窗口已消失；跳过着会常态化丢失完成态 summary（输出型节点 summary 写在 outputs flush 之后）。
- **保险丝 120s**：已翻案（见 Decision 5）。**再翻案条件**：观测证明 600s 仍误杀正常单步（届时先查该步为何纯等待这么久，而非再放宽）。

**Related**: ADR-025（cost 计量账本机制——本条改写入路径不改账本形状）/ ADR-017（Postgres 即队列）/ ADR-039（队列与重试机制；execute_step 终态分支结构；质检打回 feedback 通道）/ MODULE_ARCHITECTURE §7.2（队列机制——本条为其补会话纪律）

## ADR-051: FLORA 对齐——画布优先路由（overlay 概念退役）+ 折叠打勾增量感 + 节点交互升级 + 提问 dock 形态切换

**Status**: Decided (2026-08-31，用户拍板；施工排期 PROGRESS W7 头部 08-31~09-01)

**Context**: 2026-08-31 用户以真实案例项目对照 FLORA 工作台完整走查，五处差距浮出：① 点阵太淡（1px/20% 在白画布上几乎不可见，FLORA 的点阵明显可读）；② 免责行位置/文案学了一半（位置不常驻、文案自造）；③ 提问选项 UI 差距——FLORA 是选项 1/2/3 + 尾行铅笔手输（整个 dock 变形、原输入行隐藏），我们是保留原输入行 + placeholder 换 "Something else"；④ run 节点生命周期交互（节点出生即有最终尺寸 → running 动画 → 结果填充 → hover tooltip + 磨砂 prompt 框可编辑 → 重跑 → 变体分页 1 of N → 详情面板陈列模型事实）是"让用户一步一步进行下去"的关键手感，我们的 run 期缺增量感（产物只在 output 行落地时凭空出现，占位机制缺席）；⑤ 中间节点噪音（"1 step" 过程脊）。架构判断（用户认可）：**物种差异不是架构缺陷**——FLORA node = 单次生成单元，我们 run = 编译批量 DAG 共享一份 director plan；但增量感与节点交互是真实差距，交互模式必须升级。路由层：`?overlay=` 参数是 fullscreen overlay 时代的遗留产物——项目页本应永远画布+dock。用户拍板原话要点：**打勾流不动只浓缩**（折叠型 Claude Code 式——对方一样有 "Running node" 打勾，浓缩即对齐）；**overlay 概念整个去掉**，进来就是画布+dock；**chat 与意图识别毫无变化**；hover prompt 框要学习（心智负担更少，是更正确的交互）；变体分页同批做；**ADR 都可以破，禁令「图面模型名永禁」也可以破**——破法见 Decision 5（事实展示解禁，SKU 货架永禁不动）。

**Decision**:

1. **画布优先路由（overlay 概念退役）**：`/projects/$id` 永远 = 画布 + 底部 dock——`?overlay=chat` / `?overlay=run` 路由参数与 GenerationOverlay 的 fullscreen 壳一并退役，dock 壳成为唯一 chat 外壳。composer 发送 = 建项目 + 上传素材 → **直达项目页画布+dock**，草稿经 router state 交付 dock 发出首条 `POST /chat`（消息机器零变化，去掉的只是壳）。processing 项目卡片 / 待确认 CTA / 继续设置 / tours 的 overlay 引用全部清改为直达项目页——dock 按项目态自呈现（待确认 = 任务书 dock；活 run = 折叠打勾 + 活画布）。断线重连 / 历史打开直接呈现终态不变（ADR-041 D2）。**诞生编排定稿（2026-09-01 用户拍板，FLORA 对照核对）**：fullscreen 时代的「收官整图回放」不复活——占位世界里 reveal 与 ADR-036 生长动画统一为**生长驱动诞生**：画布挂载期间出生的节点（run 开始占位物化 / 产物原位填充 = 收官节拍 / 修订生长）按编译序 `BIRTH_STAGGER_MS` 交错入场 + 边描画；running 占位卡带 FLORA 填充擦除（纯 CSS 封顶 96%）；水合首帧（刷新/重连/历史）永不重播。配套缝：dock 起跑（Start 钮 / 散文确认 / 修订 run）即经 `onRunStarted` 通知页面 refetch——页面 SSE 从第一拍挂上，run 期活画布即时渲染（confirm 起跑路径原先把占位/填充全攒到 terminal 才出现，本批终审捉出并根修）。
2. **打勾流浓缩 + 占位物化（增量感两件）**：打勾流仍是唯一**步骤叙事**进度面（ADR-041 D2 精神不变）——形态浓缩为默认折叠的一行（Claude Code 式：运行中 = shimmer 状态行 + 当前步名，点击展开步骤日志，收官 = recap 聚合行照旧）。同时 run 期画布活起来：**占位产物卡在 run 开始即物化**——derived preview（ADR-043 编译期干跑）已知产物花名册 + 画幅，`productNodeSize(aspect)` 让占位卡出生即占最终位置与尺寸，产物落地即原地填充（画幅未知取默认档）。**ADR-041 D2「进度不进图」范围收窄为「步骤叙事不进图」**：步骤清单永不上图不变；产物占位/填充是图的**内容**（确定性派生投影），不是进度剧场——禁令 #4「禁假进度」不破（占位 roster 必须来自编译期干跑，禁虚构产物）。
3. **提问 dock 形态切换**：choice 待决时 dock 整体变形——输入行（attach + MentionEditor + history + send）与免责行**隐藏**；容器 = 问题行（去掉 ✓——待决不是已完成；加 × 关闭 = bail 通道）+ 选项行（字母徽章映射不动）+ **尾行铅笔手输入**（Enter 提交自由文本；确定性字母/序号/原文 autoResume 映射不变，零 LLM）。形态切换时 dock 与消息流有明确边界区分（容器边界，不靠阴影）。回答坍缩回基础形态、QA 双层入档不变（CHAT_ARCH §8.5 停靠法则不动）。
4. **节点交互升级（hover prompt 框 + 变体分页 + 脊收编）**：hover 产物卡 → tooltip + 磨砂 prompt 框，展示**该产物自己的 spec**（runFlow 产物节点的全局 run `prompt` 逐卡重复退役——改 per-product spec：fork 派生行的目标语言 / hook / 参数，卡说自己的话）；prompt 框可编辑 → 发送 = 带焦点预钉的修订回合，**骑 `POST /chat` 唯一通道，永不开新执行通道**。修订/重跑后 → **变体分页（1 of N）**：数据源 = Operation Model 版本快照 + fork 家族，卡上翻页切换展示。**脊收编**：折叠步 ≤1 时过程脊不成节点（边经既有祖先投影规则解析，零新投影规则）。
5. **模型名禁令修订（事实展示解禁）**：「禁图面模型名 / 技术黑话」（简报 `tasks/results-canvas.md` #10；代码注释里作 #12）修订为——**模型 / provider 事实可出现在详情面**（灯厢信息栏等 detail surface，陈列事实 = 诚实）；**节点面永无模型选择器、无 SKU 货架**（禁令精神不动）；节点 caption 恒友好名不变。真实第二 provider 出现时可选 picker 的用户形态仍是策略开关（需求池「LLM provider 抽象」裁定不变），本条只解禁事实陈列。
6. **点阵与免责行**：`dot-grid` 配方调大调显（一个配方 home + 结果画布共用，两面专用纪律不变）；dock 基础形态在输入区上方常驻免责行，en 原文 = "Repurposer is AI and can make mistakes. Check important info."（zh 镜像「Repurposer 是 AI，可能出错。重要信息请核对。」）——dock 形态切换（提问等）时随输入行一起隐藏。占位卡带 @ mention 教学文案（功能性，非营销）。

**Consequences**:

- ADR-041 修订：D2「进度不进图」收窄为「步骤叙事不进图」（产物占位/填充 = 图内容）；「run 期无图」（D2/D5）随 fullscreen 壳退役；D5 产物卡的 run 级 `prompt` 字段改 per-product spec；fullscreen overlay 壳退役，dock = 唯一 chat 外壳（「一个输入组三停靠位」改两停靠位：首页 composer / 结果 dock）。
- ADR-035 / ADR-036 不变：只读基座不破——hover prompt 框是卡面浮层不是图编辑；拓扑编辑手势任何面物理缺席（#12 本义）不变；可操作画布永拒不变。
- chat 与意图识别**零变化**：PlanAgent / ChatIntentAgent / 四态契约 / plan path / QuestionDock 数据层（question/answer JSONB、autoResume、停靠法则）全部不动——本批改的是渲染壳与投影层，不是消息机器。
- 服务端增量很小：占位物化吃 derived preview（ADR-043 现成干跑）；per-product spec 从编译图 slot 参数投影（outputs.py 序列化增量）；变体分页吃 Operation Model 快照（ADR-032 现成）。无新表、无新执行通道。
- CHAT_ARCH §8（进度面 / 前端实现 / composer 条）、CLAUDE.md（composer 契约）同步修订。
- 排期：W7 头部插入 2 个工作日（08-31~09-01），原计划整体顺延 2 工作日，go/no-go 10-23 → **10-27**，仍早于已批回退位 10-30，不触发新拍板（PROGRESS §2/§3 同步）。
- 简报 `docs/tasks/flora-parity.md`（验收标准 + Prohibited Behaviors + 两天切分）。

**Alternatives（翻案条件随附）**:

- **FLORA 式每节点一 workflow**（节点 = 单次生成单元，图随生成增量生长）：否决——我们的 run = 编译批量 DAG 共享 director plan，物种差异是设计选择不是欠债；增量感由占位物化 + 折叠打勾兑现，不换执行模型。**翻案条件**：真实用户在走查中持续把「一个产物一个格子」误认为可单独运行的单元并试图连线。
- **保留 fullscreen 壳作为 run 期可选视图**：否决——双壳 = 两套进度面悖论复发（ADR-041 D2 当初砍掉它的理由不变）；活画布 + 折叠打勾已覆盖其全部正当场景。
- **hover prompt 框直接改图（就地重跑，不经 chat）**：否决——违反 chat 唯一意图面与「改动在 chat」（ADR-041 D5）；prompt 框发送 = 修订回合的发射快捷位，执行通道不变。

**Related**: ADR-041（本条修订其 D2/D5 与外壳条款）/ ADR-035（可操作画布永拒不变）/ ADR-036（只读基座不变）/ ADR-043（derived preview = 占位物化数据源）/ ADR-032（Operation Model 快照 = 变体分页数据源）/ ADR-039（agent 层零变化）/ ADR-040（chat 唯一发射路径）/ 简报 `docs/tasks/results-canvas.md` #10（模型名禁令本条修订）；施工简报 `docs/tasks/flora-parity.md`；证据 = 用户 FLORA 工作台走查（2026-08-31）
