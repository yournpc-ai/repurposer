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

claim/reap 语义为 **fencing-aware**（ADR-079）：claim 原子 UPDATE 内铸 `claim_token` / `render_claim_token`（`gen_random_uuid()`），两个 reap（startup 全量 + per-tick 按龄）翻 status 时同置 NULL；被 reap 的旧执行者醒来时其终态写谓词（token）必失败——reap = 失效令牌，不只翻状态。

reap/retry 语义族带**封顶终态**：`assets.attempt` / `outputs.render_attempt` 计数 claim 次数（崩溃 reap 不清零——计数本身就是被封的环；意图 re-pend 与手动 reprocess 清零——新意图 = 新预算），`claim_pending_asset` / `claim_pending_render` / `reap_stale` 三处判定 `attempt > cap`（config `asset_max_attempts` / `render_max_attempts`，默认 3，与 NodeBase.retries 0–2 同量级）→ 终态 FAILED + 本地化人话行（`processing_gave_up` / `render_gave_up`），render 封顶连带 fanout 节点镜像 failed + 收官所属 run（否则节点永 pending 挂死 run）。手动 reprocess = 一座复位（`jobs.reset_asset_processing` / `reset_output_render`：状态+错误+计数一体）——无「只翻 status」旁路。tick 即退避，不发明 backoff 策略。

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
- dub 是唯一强制标记的已上线功能：标识范围 = 合成轨道检测 + C2PA 写入，纯剪辑产物零负担。
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
- `workflow_runs.current_step` 不是列——是查询（`workflow_steps WHERE run_id=X AND status='running'`）；run 行只管 run 级状态机。
- 用户侧永不见**可操作** DAG 画布（ADR-035 第 2 条永久拒绝）；用户面图形态 = FlowView 渲染的只读图（配方流程图 / 结果画布 / 复核中的血缘板，ADR-035/036/041）。

**Related**: ADR-016（clip-spec 契约不动）、ADR-025（provider 抽象与计量）、ADR-035 / ADR-036（用户面图形态）、`docs/MODULE_ARCHITECTURE.md` §2.1/§4、`docs/STRATEGY.md` §2.5/§5、`docs/research/elevencreative.md`

## ADR-029: 双链并列——AI 生成结果以 RunPlan 新节点类型进入，虚拟产物独立成族

**Status**: Decided (2026-07-22)

**Context**: 战略终态：AI 生成结果必做，形态 = **persona 驱动虚拟产物**（identity-driven），非 Factory 通用生成（STRATEGY §2.2）。分界澄清：clip 线主轨永远是"时间轴上的记录"（选段/trim/hidden 语义预设了已拍素材）；虚拟内容以**轨道级**在 clip 内合法存在（dub 声音克隆、AI 音乐、片头尾卡，ADR-026 管辖）；主轨本身生成的产物**不是 clip**——没有"从素材选段"的语义，其"编辑"是重掷/选变体而非修剪。问题：results 链需要独立的 agent 链路吗？

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
1. **统一 `outputs` 表**（取代 `clips`/`derivatives`）。通用列：`id / project_id / plan_node_id（血统）/ type / language / status / provenance(real|generated) / payload JSONB / files JSONB / source_ref JSONB? / render_spec JSONB? / render_status? / score JSONB? / publishing JSONB`。
   - clip = 带 `source_ref`（时间轴语义）+ `render_spec`（渲染管线）的那一类；Editor 照旧只认 `type=clip`。
   - `render_status` 保持顶级列（worker 认领谓词），NULL = 未请求渲染（语义沿用）。
   - **产物类型注册表 = 节点类型注册表**（加一种节点自动有产物位）。

render 认领谓词带**身份维度**（ADR-079）——`render_claim_token UUID NULL` 顶级列（规则 2「要查的字段升级为列」的认领先例扩一列）：claim 铸、一切 re-pend 置 NULL、render 三处终态写谓词 = `render_claim_token=:mine`（身份谓词；`render_status==RENDERING` 是状态谓词，无法区分执行者，不作终态写条件）。
2. **三条 payload 规则**（防 god-table，可评审可执行）：
   - 规则 1：**默认进 payload，schema 注册表守门**——`OUTPUT_PAYLOAD_SCHEMAS`（type→BaseModel），写入 `model_dump()`、读取 parse 回 typed model（沿用 render_spec/ClipSpec 的"JSON 列 + Pydantic 契约"先例）；
   - 规则 2：**要查的字段升级为列**——需要 SQL 谓词/索引/认领的字段挣顶级列（`render_status` 是先例）；
   - 规则 3：**通用列只收跨类型字段**——对 ≥2 类型或横切机制（合规/计量/分发）有意义的才配（plan_node_id / provenance / score / publishing）。
3. **Distribution 单 FK**：`publications.output_id`。
4. **verifier 的家**：`score JSONB`（分数+理由+维度）——P0-3 分数落库落定于此。

**Consequences**:
- ADR-029 的虚拟产物随本条落为 outputs 的类型 + provenance（见 ADR-029 第 2 条）。
- 新输出类型（newsletter / avatar 视频）= 新节点类型 + payload schema 注册，零表迁移。
- MODULE_ARCH §4 登记 outputs（Owner: Pipeline）；数据架构图见 §2.2。
- payload 的"类型安全"未丢——从 DB 层移到 schema 层（Pydantic 校验强于 SQL CHECK）。

**Related**: ADR-016、ADR-026、ADR-028、ADR-029；`docs/DISTRIBUTION.md` §3；`docs/AGENT_ARCHITECTURE.md`；`docs/archive/tasks-done/runplan-persistence.md`

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

**Related**: ADR-016（clip-spec 唯一契约）、ADR-028（RunPlan 同构对偶）、ADR-030（outputs 统一产物表）；`docs/archive/tasks-done/operation-model.md`（D1–D7 全文）；`docs/MODULE_ARCHITECTURE.md` §2/§4

## ADR-033: 编辑面分层——能力层唯一（ops+skills 双海拔），适配层多前端并存

**Status**: Decided (2026-08-02)

**Context**: 编辑能力分两条线且共用 Operation Model：editor GUI（VIDEO_EDITOR.md 的"文字稿编辑 + 单轨 trim"形态）与 chat 对话式精修。clip editor 路由把手势翻成 ops（COALESCIBLE 合并连续 ops + `base_hash` 乐观锁），chat 把自然语言翻成 `EditOpsProposal`；run 级海拔（`dub_clip` / `translate_clip` / `remove_filler` / `add_music` / `revise_script` 等技能注册项）chat 经 task_list 派发、editor 经 Dub/Translate 按钮直连端点。编辑能力的方向 = "操作作为 tools/skills，由 chat 引导 agent 执行"。这不是用 chat 取代 editor，而是需要把分层钉死，防止任一前端长出私有编辑逻辑。

**Decision**:
1. **能力层唯一，双注册表双海拔**：`OP_REGISTRY`（参数级微操作——纯函数 clip-spec→clip-spec，无 run，即时，快照/undo）∪ `SKILL_REGISTRY`（任务级宏操作 = 技能注册项——编译为图节点起 run；技能叙事与执行者构成见 ADR-039）。路由纪律维持现状并上升为契约：参数级走 ops，任务级走 task_list（`_validate_edit_ops` 拒收 precomputed ops，原话 "needs a run — propose a task_list"）。
2. **适配层多前端，全部薄转换**：适配器只做"输入形式 → 注册表调用"的翻译，**禁止自带编辑逻辑**。已发货：editor（手势 → ops HTTP）+ chat（自然语言 → EditOpsProposal / task_list）；预留：mcp（`SOURCE_REGISTRY` 座位已注册）。新增适配器 = 新增翻译层，能力层零改动。
3. **能力投资压能力层**：新编辑能力 = 新 op 或新 skill 注册项，全部适配器同时受益；禁止任何适配器私设能力种类（如 editor 独有的编辑类型）。
4. **chat 是正式编辑面**（非辅助入口）：@-mention（recipe-mention 期 2）是其定向机制（@产物 → targeted ops / skills）。editor 不退场——精细手势（拖 trim、点字幕改字、框选删段）仍是其强项。

**Consequences**:
- VIDEO_EDITOR.md 的"编辑形式"旧表述修订：文字稿编辑 + 单轨 trim 是 editor 适配器的形态，不是产品编辑面的全部。
- L3 分工线不变：多轨/图层/B-roll 仍推给 CapCut/Premiere，不进能力层。
- chat 适配器的语义完备性成为产品面：morph/fork 选择权暴露、recipe 参数默认值化等归 chat 能力简报（入 PROGRESS 需求池）。
- "能力层 / 适配层"入架构词汇（NAMING §2）；新 op/skill 评审清单固定加一问："这是能力层成员，还是某适配器的呈现细节？"

**Related**: ADR-016（clip-spec 唯一契约）、ADR-028（RunPlan）、ADR-032（Operation Model——本条将其"三前端共用操作日志"的愿景钉为分层纪律）；CHAT_ARCH §9；`docs/archive/tasks-done/recipe-mention.md` §2.5

## ADR-034: chat 回合流式——单调用流式 + 增量散文提取，Accept 协商落地

**Status**: Decided (2026-08-04)

**Context**: chat 回合若是一次性 JSON，thinking 之后计划卡/散文瞬间弹出，感知突兀。要做真流式，但 LLM 判定输出是结构化 JSON（PlanAgent / ChatIntentAgent verdict），整体必须到齐才能校验执行——"流式 JSON"本身不可渲染。两条候选：①双调用拆分（先散文后结构）——多一次 LLM 调用，延迟与成本翻倍，且散文与判定可能自相矛盾；②**单调用流式 + 增量散文提取**——判定仍是同一 JSON 同一调用，服务端在字符流累积过程中提取散文字段增量作预览通道，信封照旧收尾。

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

**Context**: 竞品 UI 评审（Lovart 类单产物工作面、flow 类节点画布+流程智能体、ElevenCreative 配方 modal——含"流程"tab 静态 DAG、图片编辑 modal、gallery 检视 overlay→composer 回填）显示行业收敛到"chat 前门 + 结构可见 + 单一连续面"。ADR-028 已决"内化 flow，不做 Flow 产品"（DAG 为内部内核，用户看步骤清单），但留了两扇窗：只读运行图检视面（P2+，混合图/机构信任两触发）与"DAG 编辑 go/no-go"待定项。精修闭环的总原则：**"精修的对象模型是图，界面是语言——隐藏画布，意图识别把用户语言翻译成图操作"**（与 ADR-028 教义同构，并加三条精度：翻译两层——指认确定性/意图归 LLM；翻译失败 = ask 反问，图永不当错误信息；新可翻译操作 = registry 注册项，永不开新面）。在此原则下，DAG 的三种用户化形态分别裁决，不可一概而论。

**Decision**:
1. **静态配方流程图 = 采纳**。配方注册时作者策展的只读结构图（友好步骤名、固定结构、无模型名、不可接线），作为"它是怎么做的"堆叠项住进配方检视 overlay（闭环链第 2 周；flow 字段入 Recipe 数据 schema，RECIPES §7.1）。定位 = 说明书/信任件，回答"它拿我的素材做了什么"，不承担任何操作。
2. **可操作画布 = 永久拒绝**。接线/自由拓扑/节点运行按钮/节点模型 SKU 货架永不面向用户——那是操作员形态，与"到来即彷徨"的知识专家画像冲突；拓扑唯一来源维持 `compile_graph`（LLM 亦只准提议 task list）。本条关闭 PROGRESS 决策表中"DAG 检视/编辑 + 简单多轨是否投入"行的"编辑"半边；VIDEO_EDITOR 封存的 L3 分工线（多轨/图层/B-roll 归 CapCut/Premiere）不变。
3. **运行期活图 = 结果画布（ADR-041 终裁）**：单 run 拓扑在收官时一帧渲染为桌面默认中心——进度不进图，打勾流为唯一进度面；小白复述测试为转正复核门（不过则网格回退默认中心）。
4. **模型货架拒绝的证据并入**：竞品画布在节点上摆模型选择器，同时提供"自动（低于 300 积分）"档位——连画布派自己都需要一个策略开关兜底。这佐证 provider-UX 裁决（用户-facing = 策略开关如"优先 EU 托管模型"，不是 SKU 货架——需求池「LLM provider 抽象」）：模型选择是成本/合规策略，不是用户的创作决策。

**Consequences**:
- 排期以 PROGRESS 为唯一事实源：活图 spike = 血缘板升正裁决（ADR-036 第 4 条），不评估编辑，只评估展示。
- 新产物类型 / 新配方进入时，静态流程图随注册项一并策展（注册表纪律 +1 字段）；活图若升正，同一渲染器零浪费接管。
- 翻译失败 = ask 反问成为硬契约：意图识别覆盖率不足时永远多问一句，永不亮图兜底。

**Related**: ADR-028（RunPlan——本条修订其用户侧结论）、ADR-032（Operation Model）、ADR-033（编辑面分层——翻译两层的注册表纪律来源）；简报 `docs/archive/tasks-done/results-canvas.md`；DECISION_MATRIX §F（画布行与配方 overlay 行证据）

## ADR-036: Flow 基座——只读图渲染扶正为共享能力

**Status**: Decided (2026-08-07)

**Context**: dub 载体链的两个事实：① 扇出数据包（1 源 → EN/ZH/FR/ES 四片对照包）渲成 tabs + 手风琴会把图结构的信息物理消灭（四条语言版本同一时刻只能见一条）；② 单 run 的 DAG 拓扑在 `compile_graph` 后固定、run 期间只有状态迁移——ADR-035 第 3 条所指"运行期活图"里真正有布局风险的不是 run 图（死图 + 状态动画），而是跨周增长的项目全史血缘；两者并为一件 spike 颗粒度过粗。原则：**先只暴露只读图，但该连线的连线、该有的节点是节点；只能通过 chat 修改。**

**Decision**:
1. **FlowView = 共享只读图渲染基座**（`apps/web/src/components/flow/`），`packages/clip` 同款单一画笔纪律：配方流程图 / 血缘板（复核门）两个消费面各自只做"领域数据 → nodes/edges"适配器，禁自绘边、禁自写布局；结果画布直读持久图（显示模型 = 领域模型，零投影，ADR-057）。契约三要素：节点皮（asset / output / step）、双边语义（**lineage 血缘边** ⊥ **dependency 依赖边**，视觉可辨）、确定性分层布局（depth 分层，有界规模不虚拟化、不缩放）。
2. **只读是结构性的，内容不降级**：FlowView 不提供 drag / connect / pan / zoom props——"图不可编辑"（ADR-035 第 2 条）从约定升级为组件 API 物理缺席；同时每条边是真边（step `inputs` / `derived_from_output_id`）、每个节点是真节点，禁装饰性插画。
3. **结果画布 = 用户面 run 图的唯一形态**：单 run 拓扑编译期定死；图先展示后运行——运行前完整链可见，产物落地原位填充（ADR-057）；步骤叙事不进图，打勾流是唯一步骤进度面（线性旁白与空间图同源 workflow_steps）。
4. **血缘板**：项目全史血缘 = 唯一无界图面；默认中心 = 结果画布（ADR-041），血缘板留作扩展视图候选。
5. **修改通道不变**：chat 是唯一修改通道；图面交互白名单 = 点选聚焦 / hover 血缘路径高亮 /（闭环链第 5 周）点节点插 `@workflow_step` mention 接三档重跑。

**Consequences**:
- 后端增量两处：`StepResponse.inputs` 下发（DAG 边表，单字段读容忍）；`GET /projects/{id}/lineage` 血缘投影端点（服务端解析唯一发生地）。
- DAG 的用户面形态 = FlowView 渲染的只读图（配方流程图 / 结果画布 / 复核中的血缘板）；可操作画布永不用户化（ADR-035 第 2 条）不变。

**Related**: ADR-035（运行期活图拆分裁决的母条）、ADR-028（RunPlan）、ADR-016（clip-spec 单一画笔先例——FlowView 是其图面同构）、ADR-041（结果画布升正）、ADR-057（画布直读持久图）；简报 `docs/archive/tasks-done/results-canvas.md`

### 补则

1. **缩放 = 导航，不是编辑**：ADR-035 第 2 条永久拒绝的是编辑手势（拖节点/接线/删加节点——拓扑唯一来源仍是 `compile_graph`）；缩放/平移/fit 是导航能力，**基座持有、按面门禁开放**：配方卡说明书（有界策展小图）fit-first 锁缩放；结果画布与血缘板开放 pan/zoom（无 minimap——稀疏小图无导航价值）。
2. **引擎定 `@xyflow/react`**：缩放进基座后，pan/zoom/pinch/minimap/命中坐标换算正是手写最坑、最值得买的代码类——手绘分层方案在动工前作废（零沉没成本）。布局仍自算（确定性分层 + append-only 保序，库只做摆位与视口，不引 dagre——"chat 加节点，图只长不晃"论据不变）。交互白名单：`nodesDraggable=false` / `nodesConnectable=false` **常锁**（拓扑编辑手势物理缺席不变）。动工前置核查：React 19 兼容版本 / SSR client-only 挂载 / Tailwind v4 样式共存。
3. **过渡动画律**：每层动画都投影真实事件——**诞生编排**：画布挂载期间出生的节点（占位物化 / 产物原位填充 / 修订生长）按编译序 `BIRTH_STAGGER_MS` 交错入场 + 边描画，是把真实编译顺序用缓动时间轴回放，不是剧场；**状态动画**（running 脉冲 / 边流动指向待执行子节点，SSE 驱动；running 占位卡带 FLORA 左→右填充擦除——纯 CSS 缓动封顶 96%，不声称分数，落地产物是唯一 100%）。禁令 #9 不破：动画永远是真实事件（编译序/状态迁移/真实生长）的投影，禁假进度；`prefers-reduced-motion` 降级为即时呈现；刷新/断线重连/历史打开直出终帧——水合首帧永不重播。

## ADR-037: 身份模块正名——Speaker 退役、人设（Persona）扶正，IP 留在承诺层

**Status**: Decided (2026-08-08)

**Context**: 产品定位升级后（知识专家任意素材，"never assume the input is a speech"），Speaker 命名三重断裂：① **语义前提崩塌**——"Speaker/演讲者"预设用户是演讲者、素材是演讲，而身份容器的主人是有内容的专家（会议/报告/播客/文字稿+照片）；② **一词三义撞车**——Speaker（用户身份画像）与排期中的 `speaker_map`（素材里"谁在说话"的分析节点，RECIPES §6）、landing 普通英文词 speakers 同词不同域，前两者即将共存于同一个 DAG；③ 旧裁决"Persona 只当概念词、不进表名路由"的前提是"Speaker 是对的实体名"——前提已不存在。同时用户给出产品的用户侧闭环：**管理 IP → 产生 outputs → 发布**（与工程侧"理解 → 生成 → 审校 → 分发"互为表里，STRATEGY §3 牌 1）——"管理 IP"是活动不是对象：今天该模块里用户唯一能操作的是身份理解（风格/受众/禁忌词/声纹），账号绑定与发布数据未落地（Distribution P1 / 数据回流 P2），以"IP"名之则第一天不诚实。

**Decision**:
1. **身份模块正名 = 人设（en `Persona`）**：多实例扁平（工作号/生活号 = 两个人设）；用户面 zh「人设」/ en「Persona」，代码层 `persona`（表 `personas`、`PersonaContext`、路由 `/personas`；节点 `persona_bootstrap` 名零改动）——三层同词族，无需双轨。人设 = **任务完成后沉淀的记忆**（语气/风格/禁忌词/声纹等稳定特征），行为规则：per-user 隔离（`user_id` 在表）；composer 可选选择、**未选则任务分析后 auto-create** 并挂到当前项目；多实例不强制单例；两层分工不变——人设 = 稳定风格记忆，项目 = 当次主题/意图 + 素材。
2. **`speaker` 让位素材域**：指"素材里说话的人"（纯数据层，用户不可见）；`speaker_map`（RECIPES §6）是该词的合法居民，保持原名落地。landing 的 "keynote speakers" 是普通英文词，不受影响。
3. **IP = 承诺层词，不进产品内导航**：对外叙事/landing 可讲"打造你的 IP / 自媒体"（zh）——IP 是整个 agent 的产出（账号+受众+内容+声誉），不是某个模块。**"IP" 禁入英文文案**（英语语境 IP = intellectual property，法律词）：en 叙事用 **personal brand**（LinkedIn/职业人群）/ **thought leadership**（知识专家语境）。营销文案按 locale 适配属正常；NAMING §2 中英唯一映射约束领域词汇，不管营销 slogan。
4. **stock voices 不伪装人设**（修订 RECIPES §5 裁决③的形态描述）：系统音色以"音色"身份进人设选择器的系统区（如 Rachel · Confident，带试听）；声纹 = 人设属性不变。
5. **迁移**：全栈同词族 `persona`（表 + Alembic 迁移 / schemas / `memory/routes.py` 端点 / persona skill / 前端路由与 i18n / composer 人设块）；皮肤吸收见 ADR-038。现状事实源文档 = MODULE_ARCHITECTURE / AGENT_ARCHITECTURE / NAMING §2。

**Consequences**:
- 闭环叙事三层归档：对外/愿景 = 管理 IP → outputs → 发布（STRATEGY §2.2 落档）；产品内导航 = 人设 / composer / projects（/ 未来 Distribution）；工程层 = 理解 → 生成 → 审校 → 分发（STRATEGY §3 牌 1 不变）。
- `persona_bootstrap`"从源文本提取风格"隐含"素材 = 本人言论"假设；素材域扩展后需"本人含量"门禁（非本人素材不污染人设；`speaker_map` 落地后可升级为"只从用户本人段落学"）——门禁登记于 persona skill 与 AGENT_ARCHITECTURE。
- dub 声纹目标态 = voice_id 缓存人设行、克隆一次跨项目复用（`voice` 缓存 + STOCK_VOICES + dub 声纹优先级链）；声纹质量打磨见 PROGRESS。

**Related**: ADR-030（outputs 统一）、ADR-038（人设吸收 Brand）、RECIPES §5/§6、STRATEGY §2.2/§3、NAMING N-27

## ADR-038: 人设吸收 Brand——身份单对象化（brand_templates 退役，皮肤/工艺/格式三分流）

**Status**: Decided (2026-08-08)

**Context**: 多人设（ADR-037）之下，Brand 与人设的拆分不成立——"同一 Speaker 服务多个 Brand（大学官方号 vs 个人 IP）"在多人设下恰是**两个人设各带皮肤**的自然模型。且边界渗漏：CTA / 语气双边同驻（brand config 有 default CTA，纪律却说 CTA 归 Speaker）；composer 双身份控件（人设块 + Brand pill）逼用户做无意义配对；IA 身份格由两个低存在感页面各撑一半。`brand_templates.config` 实为杂物抽屉：皮肤字段（caption 字体/颜色/preset、title、片头尾卡）与工艺开关（`removeFiller`/`captionEnabled`/`fillMode`）、产物格式默认（`aspect`）、音乐默认混居一袋——整体并入人设会误导含义，必须先按真实归属分流。

**Decision**:
1. **`personas` 终态 schema**（ADR-037 改名迁移与本条合并执行）：
   - 身份卡：`id / user_id / name / title? / avatar_url? / language`；
   - 风格块（flat 六件，现状平移）：`core_values / favorite_metaphors / sentence_style / emotional_tone / typical_hooks / avoid_words`；
   - 策略块（flat 三件）：`audience? / guidelines? / cta?`——**CTA 唯一家**；无 `voice` 文本列（`voice` 一词的唯一合法含义 = 音频本义，词汇表；文风内容归 `guidelines`）；
   - 声音块：`voice` JSONB NULL——`{"kind":"cloned","voice_id","sample_asset_id"}` | `{"kind":"stock","stock_id"}` | NULL = Auto；
   - 皮肤块：`brand` JSONB NULL——caption 字体/字号/颜色/位置/preset、title 开关+位置、片头尾卡、logo、keyword_highlighter；NULL = 系统默认皮肤；**块名 = `brand`，全栈一词**（人设块 / 烘焙 / clip-spec `brand` 段同名，§1）——无独立模块，词保留；不引入 `look` 字段名（RECIPES §4.4 的 look 层是"caption × title/intro × brand 参数"的组合概念，避免撞名）；
   - 来源与校准：`learned_from` JSONB NULL（asset hashes + 摘要，显化页"它从哪学的"）、`calibrated_at` ts NULL（最近校准，§4 可空时间戳）、`auto_created_at` ts NULL（系统 bootstrap 标记——**替代 is_default 布尔**）；
   - 审计：`created_at / updated_at`。
2. **无 `brand_templates` 表——config 三分流**：皮肤字段 → `persona.brand`；工艺开关（`removeFiller` / `captionEnabled` / `aspect` / `fillMode` / 音乐默认）→ 配方注册表 / 任务书默认（`removeFiller` 本已是 op/skill，`aspect` 是产物格式）——**不进人设**；`language_tone` 不单独成字段（风格六件已覆盖）。
3. **引用形态**：无 `projects.brand_template_id`（渲染时经 `persona_id` 解析）；composer payload = 单 `persona_id`；`GenerationContext.brand` ← `persona.brand`；`memory/brand.py` 烘焙读人设（模块名不动）；**clip-spec `brand` 段不动**（渲染黑盒契约零破坏，ADR-016）。
4. **前端**：`/personas` 人设页 = 身份卡 + 风格（"它眼中的你"，含 `bootstrapped_from` 来源说明）+ 策略 + 声音 + **皮肤分区（设置 + 实时预览）**；`/speakers`、`/brand-template` 307 重定向到 `/personas`；sidebar 身份项 = 单「人设」；composer 无 Brand pill——人设块 = 唯一身份控件（皮肤随人设）。
5. **`STOCK_VOICES` 代码内静态注册表**（随代码部署，不建表——系统音色不伪装人设）：id / 名 / 风格标签 / 语言覆盖 / 试听 URL / provider voice_id。
6. **默认人设解析链**（不加 is_default 布尔）：项目挂载 > composer 显式选择 > `auto_created_at` 非空（系统 bootstrap）> 最早创建。
7. **配方 brand 参数 → run 级 look 覆盖**：默认 = 人设 look，配方可播种视觉覆盖；任务书字段照旧可 chat 修订。

**Consequences**:
- IP 容器终态（ADR-037 D4）更干净：IP = 人设（身份+风格+策略+声音+皮肤，一个完整对象）+ 绑定账号 + 表现数据，整体迁入无残肢。
- 多人设共享皮肤（未来团队空间共用机构 VI）以"从另一人设复制"过渡，团队空间立项时再升级共享引用——不为它保留独立模块（§7 逆用：失去独立表归属即失去模块资格）。
- 排期以 PROGRESS 为唯一事实源。
- 实施简报：`docs/archive/tasks-done/persona-identity.md`——含**消费面全审计与迁移地图**（渲染链 / DAG / chat / 配方 / 前端 / 种子脚本逐点过）与数据迁移步骤（§6–§7）。

**Related**: ADR-037（改名与人设正名）、ADR-016（clip-spec 契约不动）、RECIPES §4.4（look 层）/ §5（声音的家）、NAMING N-27/N-28

## ADR-039: 架构规范级大迭代——技能叙事 + 模块四分 + 节点对象化 + Agent 归一 + harness 层 + outputs 派生 + 估价

**Status**: Decided (2026-08-09)

**Context**: 三轮架构评审（内核核对 → tools/skills 职责梳理 → 多 agent 事实确认）沉淀。代码内核（RunPlan DAG + 注册表裁决 + chat 单入口）经逐文件核对确认健康，但存在系统性规范残留：① **skill 一词三义**（`app/skills/` 目录 / `SKILL_REGISTRY` 条目 / `SkillEntry.kind` 值），且 "班组/班底" 词需解释（NAMING §6 违规）；② **产物类型散在 6 处**（`IntentSlot` Literal / `KNOWN_OUTPUTS` / `_OUTPUT_TO_NODE_KIND` / `_SKILL_TO_OUTPUT` / `_SLOT_ORDER` / `SLOT_COUNT_LIMITS`），新增产物不是纯注册项；③ **tools/ 混 LLM 调用**（`tools/caption_translate` import agent、`tools/dubbing` 两层下藏翻译调用），职责边界渗漏；④ **节点知识散在 4 个文件**（registry / orchestrator 平行表 / node_runners / schemas），内核里全是 `if kind == ...` 分支知识；⑤ **10 个 `xxx_agent` ad-hoc 类**，真实差异只有 prompt/schema/配置——多样性是数据不是代码；⑥ **harness 部件散落**（`skills/base.py` 半个基类 / chat service 巨文件 / client），repair 仅 intent 一家、兜底无声明纪律；⑦ **多 agent 事实只活在文档散文**（RunPlan §12.5 会思考/不会思考），DAG 节点只有扁平 kind，"谁在行动"被抹掉；⑧ `cost_hint` 三档报不了价，生成前费用预估（PROGRESS 第六周）无技术地基。本条 = **规范级大迭代——内核流程不变，概念归位与模块重划**。

**Decision**:
1. **技能叙事为架构主叙事**：Repurposer 是一个 AI 助手，身怀技能（剪辑/配音/字幕/自媒体规划…）；**技能内部 = agent 调 LLM、用 tools 实现**。三层归属：技能包（`app/skills/`，能力唯一家：节点类 + params + 私有工序 + 估价 + 展示键，+技能私有 agent 声明）/ `app/agents/`（决策体共享层）/ `app/tools/`（机械共享层，禁 import agents/LLM client）。
2. **Agent 归一**：`agents/base.py` 一个 Agent 类 = harness 漏斗（装配→渲染→调用→校验→**修复一轮（错误回显）**→计量→声明式兜底）；实例 = 声明（name/prompt/schema），花名册 `AGENTS` 可枚举；特殊子类仅流式（chat intent）；领域逻辑归 schema 校验/技能包工序。**无盲重试**（修复必须带反馈）；兜底默认禁、显式声明（PlanAgent 永不白屏、多模态降级为合法先例）；**纯度签名化**（understand 签名无 persona 参数，违规在类型层不可表示）。
3. **节点对象化（`NodeBase`）**：每个节点类自描述——`run`（唯一必实现）/ `estimate(ctx)` 估价 / `requires()` 出生地门禁 / `label()` 展示名 / `reuse()` 幂等复用 / `retries`·`after`·`needs_director`·`output_type` 类属性。**内核退化为图算法**：报价 = fold、执行 = topo 走图、校验 = ∀requires、配方对账 = flow keys ⊆ 编译图 kind 集（启动自检机械化，不靠人肉评审）。`_validate_requires` 字符串匹配 / `_SLOT_TYPE_LABEL` / `retries_for_node_kind` 扫描 / asset-hash 复用特判全部归位节点。
4. **outputs = 技能属性，注册表派生**：`IntentSlot.type` = str + 注册表校验（NAMING §5 延伸，无 Literal 枚举）；五处散点全派生；新增产物 = 一条注册项，PlanAgent prompt 同源注入当轮即知。
5. **多 agent 落成结构**：`app/agents/` 花名册 + 节点归属技能包；协作哲学不变——**agent 互不对话，协作经落库产物沿 DAG 边流动**（编排者 = `compile_graph`，禁 ReAct 铁律延伸）；loop（chat 治理环）编译出 graph（DAG 执行核），四层工程地图 = Model（client 单边界）/ Harness（调用面漏斗）/ Graph（NodeBase + 图算法）/ Loop（chat 状态分派）。
6. **估价系统**：`node.estimate()`（机械精确价 / agent token 区间——无 `cost_hint` 三档）；`workflow_steps.estimate` 增量列（计划侧，与 `cost` 账簿侧对称）；生成前 dock 总价 / chat 修改单价 / 配方卡估价贴（排期见 PROGRESS）；actual 校准 estimate 闭环。
7. **表结构**：仅 `estimate` 增量列（nullable）+ kind 与技能名统一；其余零变化；不建新表（agents/skills 皆为静态注册表）。
8. **actor 概念不采用**：非行业标准词；技能包构成即"谁执行"的答案。

**Consequences**:
- **行为零变化**：compile_graph 同输入同图、chat 四态/裁决/dock/checkpoint 不变、run 行为与渲染链不变；剧本测试（S1–S40）为回归网，新增三断言（flow 对账自检 / 报价单调性 / repair 只一轮）。
- **DX 目标**：加技能 = 加一个包；加 agent = 加一条声明；加产物 = 加一条注册项。
- 节点友好名 = `NodeBase.label` 派生，不另起平行表；排期以 PROGRESS 为准。
- **词汇**：NAMING N-29~N-35（无班组词 / Agent 归一 / 无 actor / outputs 派生 / harness 限定 / estimate / kind 同名）。
- **Agent 语义边界（ADR-052 判词 1）**：`Agent` 类 = 声明式结构化调用（业界对位 = AI SDK `generateObject`），**非业界 autonomy 义**——按 Anthropic《Building effective agents》分野（workflow = 预定义代码路径编排 LLM / agent = LLM 在循环里自主指挥自己），pipeline = orchestrator-workers 模式、chat 边缘 = routing + 有界工具 loop（ADR-077）；开放式自主零座位——这是设计不是缺口。agent 性在产品承诺层（厚 agent = 一个 assistant），实现层合法自主性座位 = 有界 loop 节点（ADR-052 判词 8）与会话层有界工具 loop（ADR-077：生产封闭 / 服务收编 / 执行永拒）。

**Related**: ADR-028（RunPlan 持久化——本条是其规范面完成）、ADR-030（outputs 统一——本条使其可扩展）、ADR-033（能力层双注册表）、ADR-025（计量——估价是其计划侧）、NAMING N-29~N-35、AGENT_ARCHITECTURE（四层工程地图重画）、CHAT_ARCH §4/§5

## ADR-040: 配方 = 提示词——`recipe_id` 传输带与服务端播种退役

**Status**: Decided (2026-08-11)

**Context**: 配方身份若做成 `recipe_id` transport + 服务端播种（`resolve_recipe_launch`）有结构性病灶：配方对 plan agent 不可见——播种块只能给一个 generate 判决补槽，LLM 判 ask 时当轮无书可 dock；病根是双份表达：配方产出写了两遍（前端 prompt 模板文案 + 注册表 `outputs`/`dub_languages`），可漂移；且极端处播种会静默盖过用户对预填文案的编辑（违背 chat 恒胜）。原则：**从配方生成其实只是提示词。**

**Decision**:
1. **发射的全部行为载荷 = 预填模板原文**：无 `ChatRequest.recipe_id`、无 `resolve_recipe_launch`、plan path 无校验块与播种块；配方卡发射与 composer 完全同径（建项目 → 上传 → 首条消息），服务端永不见配方身份。
2. **注册表瘦身不拆除**：`tasks` 技能链保留为启动对账自检的**声明形态**（flow ⊆ 编译图，AGENT_ARCH §4.2；语法经 ADR-043 与请求层统一），不进请求路径；卡面 / 检视 / 示例资产照旧。
3. **剧本考法**：S5/S11 发模板原文（与真实前端逐字节一致）；无播种确定性剧本（S22 编号留空不回收）。
4. **后果自担**：任务书形状由 LLM 从模板文案推断（composer 主路同款保证）——dock 可见 + chat 纠偏是产品核心循环，不再设隐藏确定性通道。

**Consequences**:
- 这些符号不存在：`ChatRequest.recipe_id` / `resolve_recipe_launch` / service.py 校验块+播种块 / 前端 `recipeId` 链路（useProjectLaunch / chat-stream / 项目页 router state）。
- 保留：`RECIPE_REGISTRY`（卡面 + flow ⊆ 对账自检）；`ChatMention.type="recipe"` 成员（历史消息 chip 渲染）。
- 「配方身份贯穿三站」无座位——服务端永不见配方身份：打勾流皮肤用节点友好名、chips 按焦点产物派生，均不需要配方身份（ADR-041）。

**Related**: MENTIONS §3（配方永不是 mention 的母判定）、RECIPES §7.1–7.2、ADR-036、AGENT_ARCH §4.2（对账自检不变）

## ADR-041: 结果画布升正——canvas 为桌面默认中心、底部 dock、进度不进图、移动端 UI in chat

**Status**: Decided (2026-08-11)

**Context**: 结果面四个问题：① chat 打勾收官后关窗跳结果页 = 跳切，过程与结果被劈成两个房间；② 网格 / tabs / 消息流同为线性容器，多产物扇出被线性容器物理消灭——空间面是多产物的唯一解法；③ 结果面本身是桌面默认中心的候选；④ 移动端渲不了 canvas 不是方向反证——移动端是降级面不是核心场景，方向是否成立的证据看桌面。结果面 = 整屏只读 canvas，chat 收为底部 dock；**ADR-035 第 2 条（可操作画布永久拒绝）不变**——canvas 正当性三理由：连续性（产物从过程里长出来，无跳切）、扇出全景可见、血缘信任（每个产物出处可溯）。

**Decision**:
1. **结果画布 = 桌面/iPad 默认中心**：项目页 = FlowView 渲染项目持久图 + 最新产物（真节点真边，output 节点 = 产物卡：媒体内联自播（视频静音循环）/ 分数+top-pick / 磨砂操作条（下载/发布，hover 放大开大屏））；画布直读持久图见 ADR-057。网格重构件作移动端列表渲染件复用。
2. **步骤叙事不进图**：打勾流是唯一步骤叙事进度面——形态 = 流内单行动态行 + 平铺步骤（活态 status line / 终态收据同一行，CHAT_ARCH §8.7）；**产物占位/填充 = 图的内容不是进度**（草稿图即占位，产物落地原地填充，ADR-057）；诞生 = 按编译序生长回放——动画 = 真实事件投影；输入组全程零位移；断线重连 / 历史打开直接呈现终态不播回放。
3. **底部 dock**：chat 外壳 = 居中悬浮输入组（同一消息机器）。dock 可见性三态——收起 = 输入组（唯一常驻 chrome）；展开 = 历史区为**自有磨砂浮层**悬于输入组上方（输入框独立层律：输入组恒为独立一层，永不与消息流融为一体）；hidden = 用户手势收成右下角 LogoMark 磨砂圆点（唤回触发 = agent 发声 / 待决提问——只能藏静态输入组，藏不住新信息）。**agent 发声（新回复落流）历史必自动展开——点卡选择不撑开历史**（点卡开详情时历史乱弹是 jump-scare）；点画布空白 = 回中性（历史收起 + 选择清除，pane 级事件，节点点击不触发）。问句 dock = 独立浮层 pill 悬在输入组上方；免责行钉在输入组**上方**常驻耳语。**系统层灰行入流原则**：一切系统事实（步骤勾选、run 收官 recap）渲染为消息流内的灰色 meta 行（`MetaRow`：muted + xs + 无填充 + 超长截断可点开），永不另立流外 chrome——信息入流，控制留底。画布视口留 bottom safe-area。输入组停靠位两处：首页 composer / 结果 dock。**页级形态机**（现行法 = ADR-056 三形态机）：首个 run 前 = 居中全屏 chat（full 形态），首个 run 到达后桌面 = 右侧面板（panel 形态）/ 移动端 = 底部 dock（dock 形态）——同一台消息机器，纯布局形态，输入组零位移。
4. **产物节点交互边界说死**：点击 = 选中 + 右侧档案（OutputInspector，全产物类型；无居中播放器 modal）；toolbar 装图操作（运行 / 接线）永久禁区。**节点解剖 = caption 恒为类型 icon + 类型名（左上，右槽恒空）+ 媒体区 + factsbar**：信息位（语言 / 分辨率 / 时长 / 画幅）住 factsbar——时长住条内、永不作为视频浮层角标（媒体角标只剩 score），分辨率从媒体元素实读（`onLoadedMetadata` / `naturalWidth`），不立硬编码表；动作 = copy-or-download + 发布（Send），无 ⋯ 菜单、画布无产物删除座位（ADR-063 卡面交互律）；**条随内容自然撑开、信息永不省略**（无截断/省略号/title 兜底）；**产物卡 lane 宽 280**（9:16 → 498 媒体高，源视频素材节点同宽 280）。素材节点同解剖（文件名 / 时长 / 分辨率 + 下载），动作归 surface 所有；删除产物 = `DELETE /outputs/{id}`（连存储对象一起清，fork 派生行不陪葬）。产物对话归 dock（指认走 @mention，ADR-058）——无 ChatModal / AssetChatModal 类独立对话 modal。
5. **密度 + 渲染单元**：配方说明书 = 策展密度（≤5 节点，只画兑现承诺的步骤）；结果画布 = 名词密度（素材 + 文档 + 产物主角）；run 期画布活（占位卡 run 开始即物化 + 打勾随行）。**step 全量落库**（成本 / 重跑 / 血缘靠它）**住节点内部，画布从持久图直读、零投影**（ADR-057——无 `canvas_key` / 过程脊 / `canvas_hidden` 补丁族）；**过程动词永不上图**——每个动词都是其产物的属性；状态原地投影到产物卡（失败/渲染中 = 卡的原地态，不是独立节点）。节点解剖 = 输入在边上、规格在身上、结果在卡上、改动在 chat。
6. **导航门禁**：缩放 = 导航不是编辑——配方卡说明书锁 fit；结果画布开放 pan / zoom（无 minimap——稀疏小图无导航价值）；拓扑编辑手势任何面物理缺席。
7. **移动端 = UI in chat**：不渲染 canvas（< iPad 宽度）；对话沉底与桌面 dock 同心智；一回合一张 RunCard（卡头血缘摘要行 + 可展开过程脊 + 产物缩略条 + chips）；点缩略图进全屏查看器（家族滑动 + 底部迷你输入条）。卡片种类注册表制：计划 / 操作 / 结果三型。
8. **指认 = @mention**：产物指认统一走 @output mention chip（ADR-058）；画布点卡 = 纯选择 + 详情；无 focus 请求字段（`messages.focus_output` 列读容忍保留，旧行历史回放照渲染灰行前缀，永不新写）。
9. **复核门**：小白复述测试——裁决问题 = "结果画布是否转正"；不过则结果网格回退为默认中心（组件不删），canvas 降为检视入口，零浪费。

**Consequences**:
- 诞生编排 = 生长驱动（画布挂载期间新生节点按编译序入场，水合首帧直出——ADR-036 补则 3 同律）。FlowView 消费面 = 配方流程图 / 结果画布 /（复核中的）血缘板。
- 服务端永不见配方身份：打勾流皮肤用节点友好名、chips 按产物派生，均不需要配方身份（ADR-040）。

**Related**: ADR-035（可操作画布永久拒绝不变）、ADR-036、ADR-040、ADR-028（RunPlan）、ADR-056（dock 形态机现行法）；简报 `docs/archive/tasks-done/results-canvas.md`

## ADR-042: 身份根升格——定位（Positioning）为根、人设收窄为表达分区、选题库升一等公民

**Status**: Decided (2026-08-13)

**Context**: persona 超载的三重病灶在多人设下显形——① **定位缺位**：策略三件（audience/guidelines/cta）只是定位的薄切片，因无处安放寄存人设；agent 顾问姿态（诊断听众/目的）问完无落点，"用户到来即彷徨"（STRATEGY §5）没有持久答案；② **渠道空壳**：`channel_accounts` 只是 OAuth token 行，不知道自己属于谁、服务哪个受众，发布数据回流（P2）将无处可挂；③ **人设被偷渡**："多实例扁平（工作号/生活号）"实为两个定位压成两行风格对象，同一真人克隆两次声纹。运营全链路对照（定位 → 账号 → 对标 → 选题库 → 生产）显示：架构只覆盖生产层，运营层（持续回答"该做什么"）整体缺失。「IP 容器加法式升格」路径否决：**根词不是被打造的结果**（品牌/IP 留在营销承诺层——自媒体新人听到的第一句话是"找定位"，不是品牌相关的话），且行业话语里定位天然三分（内容定位/人设定位/平台定位），定位 ⊇ 人设是标准用法。更根本的分界：**定位是选择（对话共建带确认），人设是特征（素材提取+维修点）**——两种来源、两种生命周期，混在一个对象里，页面既想当接待处又想当维修点。

**Decision**:
1. **身份根 = 定位（`positioning`）**，多实例（工作号/生活号 = 两个定位）。表 `personas`→`positionings`、FK 网 `persona_id`→`positioning_id` 全栈平移（speakers→personas 改名先例同构，纯机械刀）。
2. **三分结构**（行业话语映射）：内容定位 = 战略字段（territory/audience/differentiation/goals/guidelines/cta，**对话共建带确认**）；人设定位 = 表达分区（风格六件 + `voice` 块 + `brand` 块原样保留，`persona` = 逻辑分区词，不物理嵌套）；平台定位 = 渠道（`channel_accounts.positioning_id` FK + 公共档案 + 适配默认）。
3. **选题库升一等公民**：`topics` 表 + 生命周期（灵感/已排期/生产中/已发布/有数据）；选题卡 = 发射单元（点卡 → 任务书预填 → chat 确认 → run，chat 唯一意图面不变）；来源 = 素材档案挖矿（主）+ 对标/回流信号（P2）。配方卡（新用户能做什么）与选题卡（老用户下一条做什么）分工并存，共用同一发射机构。
4. **project 退居内部执行容器**：用户可见工作单元 = 选题（管道）+ 产物（成果库）；projects/runs 留管线层做分组与重跑载体。
5. **素材档案上提根级**（assets 挂 positioning，back-catalog 挖矿底座）；**声纹资产用户层共享**（声带是人的不是定位的，多定位引用同一份克隆）。
6. **品牌/IP 留在承诺层**：落地页叙事继续 personal brand / 个人品牌；`brand` 维持皮肤块一词不动（不引入 `look`）；产品内导航用「定位」。

**Consequences**:
- ADR-037 D4 的「IP 容器加法式升格」路径不采用——身份根 = 定位（容器升格 = 定位根改名路径）。
- 排期（PROGRESS §2）：生产层闭环（第二~五周）不动；**运营端 = 第六~八周**（定位根重构 → 选题库 → 回访 home + 素材上提）；go/no-go **10-23**（回退 10-30）。
- 明确不做：对标作为支柱（与反 slop 定位相悖，P2 降级为选题校准信号）；工具格形态（chat 唯一意图面不变）；昵称取名场景（目标用户有名字有机构）。
- 母文档 `docs/POSITIONING.md`；MODULE_ARCHITECTURE / NAMING / CLAUDE.md 的现状描述随第一刀落地时改写（落地前它们仍是现状事实源）。

**Related**: ADR-037/038（身份模块前史）、ADR-016（clip-spec 不动）、ADR-041（结果画布——运营端 home 复用其面）、STRATEGY §5（用户到来即彷徨）、PROGRESS §2 第六~八周

## ADR-043: 任务书语法收敛——outputs 概念退役为派生（derive），plan path 并入技能链

**Status**: Decided (2026-08-15)

**Context**: 真实场景走查：用户从字幕卡发射「给我的视频加中英双语字幕」（长视频源），任务卡呈现「视频片段 ×2 · 中文」——整条视频的变换意图被强制表达为高光提取 + 簿级修饰符，数量步进器（默认 3）出现在数量由请求完全决定的场景。根因不是 UI：outputs 槽位语法（`IntentSlot` + `InferredIntent.outputs`）按「一场演讲 → N 件衍生品」一种形状设计，请求层 schema 直接就是产物清单。技能注册表（ADR-039）之下工作语法 = 技能链：产物类型词汇由节点 `output_type` 声明派生（N-32），mode② 已能从 task list 反推槽位形状（`derive_context_fields`）——plan path 仍带 outputs 语法：outputs 必填；unclear 默认全家桶（clips+post+quotes+article，与反打包裁定 STRATEGY §5 冲突）；固定拓扑编译。同一分叉已在配方层显形：字幕卡流程图已摘掉剪辑步骤（卡不含剪辑，RECIPES §4.1），承诺「为你的视频带来多语言字幕」，但其预设 `outputs=[clips]` 的编译图仍跑 select_clips——15s demo 源下高光≈整条掩盖了分叉，真实长视频穿帮；图文视频卡同病（承诺「短片」单数，管线只出 N 条高光）。备选：① outputs 语法加 `video` 产物类型（双语法永存）；② clips 槽加 scope 标志（一个类型藏两种形态，消费方逐个长分支）；③ 任务书行改自由文本（推翻结构语法，merge/director/UI 全重写）——均否决。

**Decision**:
1. **请求层无 outputs 语法——产物 = 编译图的派生投影（derive）**：产物类型词汇由节点 `output_type` 声明派生（N-32 不变；Output 表 / 产物行不动）。意图面唯一语法 = 技能链（task list）：plan path 与 chat loop 四态的 task_list 臂同一词汇，一次收敛。
2. **PlanAgent 产出 task list**：槽位字段下沉为技能参数（writer 族 language / focus / tone_override；select_clips count / focus / aspect；translate_clip target_language + bilingual；dub_clip target_language）；无簿级修饰符（caption_languages / dub_languages / caption_bilingual / aspect 不存在）。unclear 不出默认全家桶——最小链或顾问式反问（CHAT_ARCH §3.3 姿态不变）。
3. **整条源材料化节点 `materialize_source`**（编译期自动注入的内部节点，不登记技能表）：确定性全段 clip-spec（span = 素材全长，无 LLM 选段；源形态分发 video/audio/stills 复用 select_clips 的源决策，stills 经 align_stills 注入先例）。**画幅缺省 = `original`**（链无 clip 技能 = 比例跟源）——clip-spec aspect 第四档 `original`，渲染器 calculateMetadata 经 media-utils 实读源尺寸（stills 读首图，失败回退 16:9）；显式意图（spec / run.context）仍胜，人设皮肤的 aspect 是短片工艺默认、永不适用整条材料化。注入规则：链含 clip-spec 消费者（translate / dub / music / filler）而无 select_clips、且项目无既有 clips 可作用时注入（mode② 中途「作用于现有 clips」语义不变）；preprocess 按 requires 声明入图（不只随 director 前奏捆绑）；纯变换链不触发人设提取（ADR-040 先例）。fork 挂接：translate / dub 的 `after` 声明吸收材料化节点。
4. **计划卡 = 链投影 + 派生预览**：generate 回合干跑 compile_graph（纯函数）产出卡模型——技能链人话行 + 派生产物行（「整条视频 · 英字 / 中英双语」）+ 后续报价 fold 同源；presented_plan 摘要同一 derive。**面板控件 = 对 task list 的直接结构编辑**（数量步进器绑 select_clips.count、语言 chips 增删 translate/dub 任务、删行 = 移除技能）——与 LLM 重提同一数据结构，三方合并（merge_prior_slots / prior_intent 运输 / explicit 钉）无对象自然死亡；chat 修订 = 带 presented 摘要重提全链，chat 恒胜不变。start = 以编辑后的链编译起 run（服务端编译为行为唯一事实源）。
5. **派生类型 `video`（整条视频）= 纯展示词汇**：`materialize_source` 是编译期注入的内部节点（`NodeBase.internal`，自检豁免注册表席位），**不声明 `output_type`**——可请求类型注册表（N-32）保持原样；"video" 只活在派生预览行 / 步骤摘要 / 结果分组（节点落库的 Output 行仍是 `type="clip"`，渲染血统不变）。**结果画布消费方式**：`source_ref.segment.id === "full"` 的 clip 卡 caption 读作 "Video"（复用素材类型词），不读 "Clips"——fork 派生行携带同一 source_ref，翻译/配音版同样成立。不可请求、无 count_limits、无步进器。
6. **director 派工对齐改 keyed on 编译图**：storyboard 槽从编译出的生成节点（含参数）构建，不再从 `run.context.outputs` 读请求层槽位——多版本互补分配不退化，且与面板编辑后的真实执行链严格一致。
7. **配方预设改写为 task list 形状**（multilingual-subs = [translate zh bilingual, translate fr, dub es]；image-video = [add_music] + 材料化/stills 自动注入——「变成短片」单数承诺自此为真），flow ⊆ 编译图对账不变；配方=提示词不过线不变。

**Consequences**:
- 不存在清单：`InferredIntent.outputs`（含默认全家桶）/ `outputs_explicit` / 簿级修饰符 / `IntentSlot` 请求层身份 / merge_prior_slots / prior_intent / mode① 固定拓扑 /「clips 槽唯一」规则 /「修饰符必须挂 clips」耦合 / 前端 OUTPUT_OPTIONS 与 SLOT_COUNT_* 镜像 / 卡片「添加产物」按钮 / 字幕版本·配音版本区（折入链行）。
- 存活不动：pending_intent 持久化（载荷 = task list，存量行读容忍确定性升级）、start 确认流、出生地 422（requires 双源已免费）、edit ops、打勾流 / SSE、配方=提示词、chat 恒胜、顾问姿态四律。（无 `autonomy` 档——一切正常 Paid Run 默认 autonomous continuation，ADR-087 R9。）
- 行为变更（有意）：图文视频卡产出 = 整条轮播一条（承诺一致）；变换意图不夹带剪辑。
- **目标解析不变量**：modifier→modifier 边只是排序约束——`_target_clips` 跳过 `spec.fork` 上游的 output_refs（fork 产出是新建派生行，其原件经链基座边即达）；否则全 fork 链（R6：translate×2 + dub）会把派生行当新目标组合爆炸（7 产物而非承诺的 4）。morph 上游的 output_refs 照常下传（原地改写的交接）。**配套的兜底口径**：`_target_clips` 的「项目现存 clips」兜底只含**本 run 之前**的行（按 workflow_step_id 所属 run 排除本 run）——否则 existing 画幅下的全 fork 链（首个 modifier inputs 为空、次个只挂 fork 上游被跳过）会被同胞 fork 的新鲜派生行污染兜底集，同样组合爆炸。
- **重试 = 该类自己的链原样重跑**：结果页 tab 重试不硬编码「clips tab → select_clips」——否则整条源变换链（无 select_clips）的 clips 重试会把整条字幕片换成 3 条高光剪辑（产品形态被换）。clips 族重试发帖内 clips 族任务原序原参数（text 族 = 单个 writer 任务）；chat 域参数（target_output_id）剥离（full run 会删旧行）。配套：legacy 读容忍（`legacyOutputsToTasks` / `_legacy_slots_to_tasks`）给 dub/translate 任务补 `fork: true`——slots 时代编译产出即 fork 节点，读容忍须保持形态。
- **计划卡解剖 = 任务行（唯一编辑面）+ 增量派生**：① 派生节只在 materialize 家族（整条源）出现：「整条视频」是任务行说不出的唯一信息（materialize_source 是编译期注入的内部节点），提取/写作链的派生行与任务行 1:1 复读、整节隐藏；② 无节标/hint/「Style: …」identity 行（身份由 echo 散文吸收）；③ instruction 框永远空开——`specific_instruction` 蒸馏照进 run（数据层不动），但不倒进用户编辑区（推断簿记不是 UI 文案，needs_clarification reasons 同款判词）；可见框 = 用户自己的补充，ship 时合并（Start / prior_intent / legacy generate 三点同径）；④ echo 散文 ≤2 句：结论 + 唯一下一步，成功定义随散文（顾问姿态 law 3；措辞归 LLM 自由发挥，prompt 只约束话型与原则，ADR-054 条款 2）；⑤ clips 无素材 = 行内 amber 警告（数据 = `clips_without_media` reason）。
- 第九周报价系统协同：卡 derive 与估价 fold 共享同一次干跑编译。

**Related**: ADR-039（技能注册表——本条的语法家）、ADR-028/029（RunPlan / plan 级 dispatch——mode② 先例）、ADR-040（配方=提示词——载荷单一通道同款哲学）、ADR-041（结果画布——派生预览的消费面）、STRATEGY §5（反打包）；简报 `docs/archive/tasks-done/outputs-derive.md`

## ADR-044: clip-spec 轨道模型——锚定存储 + 泳道编译产物 + TRACK_REGISTRY（12 操作闭包）

**Status**: Decided (2026-08-17)

**Context**: 图内核（NodeBase/compile_graph）、能力层（OP ∪ SKILL 双注册表）、产物层（outputs 派生）已完成各自的"注册表时刻"（ADR-039/043）；clip-spec 是最后一个未注册表化的面——每条轨一个手写字段 + N 处消费方特判（translation_track 落地时实测约 7 处：双端 schema / Clip.tsx 分支 / `_absolutize` / 尺寸规则 / C2PA / ops 寻址，全靠人记——"每加功能前后打架"的力学来源：每个消费方各自重新推导一遍 spec 的结构知识，推导不齐就打架）。同时三股需求朝这个面涌来：crop_track 关键帧轨 / reframe_clip 分镜 / layers（B-roll、双机位 PiP）。验收判据 = **操作集闭包**（真实剪辑顺序 12 项操作走查立据，全表见简报附录）：registry 合法 op/skill 的任意序列（用户聊 N 轮）产出的 spec 仍可表示、可渲染、可继续改。走查结论：7 项已通、1 项缺登记（reorder_segments）、4 项（异源插入 / 过渡 / 文字层 / 贴图层）挂在同一次采购上。两条配套裁决：① **允许破坏性更新**——旧数据与旧规划不构成约束，以目标（闭包）为主；② **P2 契约提前**——segments widen / layers / 锚 / 过渡枚举 / ops 寻址 / 泳道投影不等第一条 insert/B-roll 技能进排期，由 12 操作闭包判据直接驱动。

**Decision**:

1. **形态 = 存法 C：锚定是存储格式，泳道是编译产物**。位置不落库——层条目挂语义锚，输出时间窗由烘焙缝一次 fold 派生；泳道投影永不落库、永不进快照、永不可写（不是缓存，是编译产物，双写不一致在结构上不存在）。**双真相禁令**：锚与绝对坐标不得平级共存于同一行数据。消去法：存法 A（泳道为真相 + 锚作附加元数据）= 两病——锚沦为缓存则漂移原样存在，锚若用于重算则已是 C；平级双真相 = 双主写必然分歧，不存在。锚三形态：**段锚**（`{segment_id + 源偏移}`，内容跟随）/ **边锚**（`{head|tail + 偏移}`；intro/outro 本质即边锚块）/ **比例锚**（`{ratio}`）。非破坏模型红利：段从不真删（hidden），层条目锚点时间落入被剪区间即失去投影窗口、自然不渲染——"级联删除"是纯派生，"并告知"归 op 响应。
2. **词汇四分 + 八词入宪法**：主轨（sequence）/ 数据轨（data，`*_track`）/ 层（layer）/ 块轨（block）四家分完整个 spec；段 segment / 锚 anchor / 过渡 transition 等八词登记 NAMING §2；**裸 track 违规、必须带家族限定**（判例 N-38，N-11 同型）。`layer` 避让 `overlay`（UI 浮层已占名：overlay-surface 浮层族 / ChatDock——N-27 同型一词两义预防）；lane / blocks / junctions / placements 不是本系统词汇，不进任何文档。
3. **TRACK_REGISTRY**：**Python 持有可执行目录（`app/pipeline/tracks.py`，唯一运行时端）**；TS 端只声明 `fields` 分区 + `TrackId`（`packages/clip/src/tracks.ts`——类型级断言强制每个 spec 键入一轨，tsc 闸），分区在两端各自独立 pinning（Python 启动对账 + TS 类型断言），无镜像漂移面、无对账脚本。`TrackDef` = `owner`（唯一写者技能，表归属契约的 spec 转置）/ `pairs`（translation⇄caption——既有耦合入档）/ `provenance`（ADR-026 分类器 fold）/ `url_fields`（烘焙缝 fold）/ `fields`（spec 顶层字段分区——自检①的承重墙）/ `depends`（派生轨失效声明，dub⟵main）。family / timeline 分类是文档（RENDERING §4 表），不进 schema；确定性工艺检查与首个住户及其消费方一并回归（ADR-045 能力批评估）。现有 8 轨平移登记 + layers 轨（layer 家族首条）。渲染器按 family 分派渲染件（sequence→段序列 / data→cue 渲染或关键帧采样 / block→块件 / layer→层件），新增轨 = 注册渲染件不动旧分支；renderer-agnostic 不动（声明只说 WHAT，Remotion 概念不进注册表，FFmpeg 后路保住）。
4. **两条启动自检**（挂 `assert_runners_registered`，API/worker 双进程 + harness 同跑）：① spec 顶层字段 ⊆ 注册表，每字段恰好一条轨；② **phantom track**——注册一条假轨（try/finally 直变异 TRACKS，移除是结构保证），烘焙缝 / 寻址 / 合规自动接管、消费方零改动（"渲染"腿的语义 = 烘焙缝 `_absolutize` 接管；渲染件注册随真实住户进场）。**计价不在自检面**：时长算术坐 `clip_spec.total_output_seconds`（kept video + 头尾卡秒）——时长贡献不随注册表自动收养，带时长的轨到来时与其渲染件一并扩展该函数。
5. **spec 进化三件**（12 操作断点的收敛处）：
   - **segments widen**：段 = `{id, asset_id?（缺省=主源）, url?（异源段随写解析，source 同款先例）, start, end, hidden}`——异源插入 = 带 asset_id 的段（ADR-029 虚拟产物段同源入座）；段可带 provenance，混合时间轴 C2PA 判定免费获得。
   - **layers 轨**：锚定放置物列表 `{id, kind, anchor, rect, z, source_ref?, media?, provenance(必填)}`；kind 枚举注册守门（broll / text_callout / pip / motion_graphic）；PiP 经 `source_ref` 自带一路源回放——"两条视频同时可见"的唯一合法形态，三条以上全帧视频叠放 = 真 NLE territory，永久不进。
   - **transition 枚举**：挂段的进场边（none/fade/dip，2-3 封顶——`insert_segment` 与 `set_transition` 两 op 同查），换序随段走；进场边语义与 FFmpeg xfade / Remotion 插值天然对齐。**L3 线 = 枚举可、画廊不可**（ADR-016 L3 注记以此为准；转场挑选面板永拒不变）。
6. **泳道投影 = 位置 fold 单函数**：sequence + layer 家族 → 扁平泳道（绝对输出时间 + z 序），TS 单家（packages/clip）+ Python 同名镜像（NAMING §1）；data 家族不投影——按 sourceTime 采样（crop_track 采样器 = keyframes 族第一个渲染件）；块轨本就输出时间轴。渲染器只吃投影/采样，永不读锚；投影函数同时是 FFmpeg 后路的 filtergraph 供料口。
7. **ops 闭包**：`reorder_segments` / `insert_segment` / `set_transition` / `add_layer` / `remove_layer` / `move_layer` 登记入 OP_REGISTRY；**op 载荷 = 实体引用（段 id / 锚 / 枚举），LLM 永不提议绝对时间码**（坐标计算永归代码——"LLM 提议、代码裁决"的编辑侧延伸）；寻址 = （轨, item_id, op) 对注册表校验，不靠 LLM 猜字段路径；段/层 id 唯一性由 ClipSpec 契约断言（锚寻址 first-match 的前提）。**一轨一写者**：撞轨 = 编译期 422（fork 豁免——派生行各有其 spec），不做运行时合并。**派生轨失效声明**：对主时间轴派生的轨（dub）在注册表声明依赖，时间轴 op 落地时经注册表枚举失效轨并告知（重配一句话；不产生"合法的谎"）。
8. **agent / skill / tool 配套边界**：**总 agent 不变**——chat loop / PlanAgent / ChatIntentAgent 零改动，单次调用 + 预装配上下文、禁 ReAct 辩护到底。**skill 按用户语言命名和切分，不按轨道切分**（「说到工厂时配工厂画面」是一个技能，「插入 layer」不是；轨道是内部坐标系）。tools 层零新增（投影/remap 是 pipeline 镜像函数，不进 tools/；边界精确化见 ADR-045——工序零新增，引擎缝按 asr.py 先例豁免）。技能化（insert_broll 工序、reframe_clip、checks 首批住户、LLM op 词汇开放、层的画布标记卡呈现）随功能排期——语录评审全案归简报 `archive/tasks-done/track-model.md` §7。
9. **tracks:{} 容器禁令**：快照 undo + LLM 不写 spec 的地基上全量常驻空轨无收益，扁平 spec + 注册表索引已提供全部归属能力。本禁令与兼容性无关，是纯目标判断。

**Alternatives（翻案条件随附）**:
- **泳道全量（泳道=真相）**：承认三条真实好处（裸时间操作原生支持 / 渲染映射直接 / 拖拽时间线 UI 期权），但账单是三笔——现有每个 op 重写成 ripple 维护算法（且漏维护不报错：spec 合法、照常渲染、B-roll 静静盖在错误的句子上——"合法的谎"）；LLM 被迫基于过期快照做时间算术（校验拦得住越界、拦不住界内语义错）；合法形态空间无界（同道重叠谁赢 / 道间空隙补什么 / 多音道怎么混——每个问题 NLE 用交互惯例回答，我们只能长代码分支）。拖拽 UI 期权的前提门已被 ADR-035 永拒。**翻案条件**：(a) 开任何直接拖拽的时间线 UI；(b) 出现锚定真实表达不了的操作——最近候选 = 任意区间音频增益自动化，届时其家是一条 `gain_track` 数据轨，仍非泳道。
- **tracks:{} 容器重构**：见 Decision 9。
- **FCP 操作力学照搬**：ripple 手势（"剪两段、尾段后移"）在声明式模型里不存在——插入一段，输出轴派生，尾部自动正确。从 FCP 带来的是能力闭包（哪些事必须可表达），不是操作力学（怎么做这些手势——执行者是 agent 不是人，整个换了一组答案）。

**Consequences**:
- 此后加一条轨 = 一条注册项（+ 新 family 时一个渲染件）；phantom 自检把"触点可数"变成机械事实——第 N 条轨比第 N-1 条便宜且便宜得可证明。
- 12 操作闭包成立（结构级：可表示 / 可渲染 / 可继续改，fixture 实证；技能化入口随排期）。
- 存量 spec：段 `id` 新写必带、旧行读容忍（无 id 行在首个时间轴 op 落地时整体回填——旧行无层无锚，回填无损）；dev 数据可经 reset_db 清场，不构成约束（破坏性授权）。
- 禁令入档：禁 NLE 自由轨语义进 spec（任意增删道 / 同道重叠 / 转场画廊 / 关键帧自由编辑）；UI 永不见轨（层条目呈现为"这段配了画面"标记卡，随技能批）；kind 全枚举注册表守门；消费方禁逐字段特判；每轨唯一写者。

**Related**: ADR-016（契约锁定——L3 注记以本条为准）/ ADR-020（stills Ken-Burns 拒绝与本条 transition 的边界：枚举进场边可、动效画廊不可）/ ADR-026（C2PA fold——layers provenance 必填）/ ADR-029（虚拟产物段进主时间轴）/ ADR-032（快照 undo——锚定面是其存储面）/ ADR-033（能力层双海拔）/ ADR-035（可操作画布永拒——泳道期权的前提门）/ ADR-039（注册表时刻同款迭代）/ ADR-043（派生投影同款哲学）；母文档 `docs/RENDERING.md`；简报 `docs/archive/tasks-done/track-model.md`（§7 配套层 / §8 附录 12 操作走查全表）

## ADR-045: 智能分镜能力线——YuNet 视觉引擎 + speaker_map 素材级事实 + crop_track 稀疏关键帧

**Context**: 能力线（PROGRESS 第三周）要把「双人同屏静态访谈 → 竖屏单人切换」与「单人中景动态追踪」落成 reframe 能力。轨道模型地基 = ADR-044；crop_track 进场还差三块：检测引擎（人在哪）、话轮归属（谁在说话）、crop_track 数据形态（取景决策怎么存）。模型选型经许可证排查：InsightFace/SCRFD 预训练权重**仅限非商业学术研究**，商用需购买授权——SCRFD 及一切 HF repack 不可用于本产品。真实场景 = 静态访谈机位。

**Decision**:

0. **检测空间 ≠ 出图空间**：降采样找框、坐标映射回全分辨率取景——访谈 640 档 / 登台原生档（640 档在远景漏小脸）/ 远景 2×2 拼块兜底（spike 实证：可收回 4/7 漏检，剩余为片尾淡出无人画面）。
1. **视觉引擎 = YuNet（MIT）**：opencv_zoo 官方权重（bbox + 5 点关键点含嘴角），**权重 vendor 入仓库**（MIT 允许再分发；~230KB 消除一切下载/代理失败面，dev 与服务器零网络依赖）+ MIT LICENSE 文件并置；运行时 = `opencv-python-headless` 5.x（`cv2.FaceDetectorYN` 原生 API，NMS 内置），配 5.x 的动态输入封装 `face_detection_yunet_2026may.onnx`（2023mar 系同权重，WIDER Hard 0.7503 最强线；int8 变体全禁——精度降且 5.x 有全漏检 bug）。引擎缝住 `tools/vision.py`（asr.py 同款懒加载进程缓存）；工序（帧网格拼装 / 词轴切段 / 选页取窗）住技能包，不进 tools/。**tools 边界精确化**（ADR-044 第 8 条注记）：工序零新增进 tools/；**引擎缝按 asr.py 先例豁免**——vision.py 是第一个住户。
2. **隐私边界**：全程不做人脸识别（不知"是谁"）——只有位置与嘴部运动，全程不出网（faster-whisper 同款 EU 姿势）；密集计算全部本地化，云调用只剩稀疏语义判定。
3. **话轮归属 = 嘴部 ROI 运动能量主 + M3 仲裁辅**：whisper 词轴切话轮（间隙 ≥0.6s 断轮）；静态机位下逐话轮对比各说话人嘴部 ROI 帧差能量，能量比 ≥ 阈值（初值 1.6×，以真实片校准）确定归属；模糊轮（双人同动 / 能量比不足）M3 网格仲裁（每片 1~5 次云调用封顶）。M3 从"主力判定"降级为"模糊仲裁"——静帧猜"谁张嘴"恰是其最弱形态。
4. **speaker_map = 素材级事实**：VIDEO 第二 PROCESSOR（接 ASR 后，`asset_processing.py` 先例——素材级 / 可重跑 / hash 复用；AUDIO 不上——信号是视觉的，音频没有可检的框），**形态闸门先行**（whisper 话轮密度 + 1~2 次 M3 网格判多人/访谈才跑全量归属；单人素材零增量成本）。数据形态：`Asset.meta.speaker_map = {form, speakers:[{id, screen_hint}], turns:[{start, end, speaker}]}`（meta 先例：language）。消费方地图：reframe_clip（08-19）→ 本人含量门禁 v2（08-31，只从用户本人话轮学风格）→ 访谈选段偏好（后续）。
5. **crop_track = 稀疏决策关键帧**（data 家族轨，源时间轴）：`[{t, x, y, scale}]`——关键帧 = 一次取景决策（"这里切到 A"），非稠密逐帧；渲染采样器在相邻关键帧间固定 smoothstep（~8 帧，渲染常量不进契约——transition 枚举同哲学：枚举可、参数画廊不可）。**防眩晕分工**：最短驻留 / 死区 / 最大转速 = 写侧约束（技能工序，参数以真实访谈片看调）+ checks 住户校验（与 reframe 包一并回归，禁先注册空座位）；采样器只做平滑插值，永远简单。空轨 = 静态 `crop` 退化形态（语义不变）。
6. **reframe_clip 技能包**：三模式 `interview_switch`（双人访谈分镜，静态机位按说话人切换）/ `speaker_follow`（单人中景动态追踪）/ `static_center`（静态中裁，回退档）+ `auto`（按 speaker_map.form 选模）。形态写者写 `crop_track`（+静态 `crop`），`TrackDef.owner` 登记即得撞轨 422；对话可调用走 task_list（六 op 继续 `llm_visible=False`，不开放 LLM op 词汇）；估价 = `detect_seconds` 计量（自有基建零定价，`render_seconds` 先例；挂在本 run 选段后时编译期不可知，报 NULL）。
7. **一引擎两模式**：同一 YuNet 在访谈素材稀疏采样（1~2s 间隔刷新位置）+ 登台素材稠密采样（3~5 帧一检出轨迹）——复杂选型收敛为**一个引擎两种采样密度**；`speaker_follow` 不需要第二套选型。

**Alternatives（翻案条件随附）**:

- **SCRFD（InsightFace，侧脸精度轻量最强）**：预训练权重非商用（官方定价页实证）。**翻案阶梯**：YuNet 侧脸检出实测不达标 → MediaPipe（Apache-2.0）→ 仍不足则购买 InsightFace 商用授权（产品化路径）。
- **pyannote 音频话轮分离**（纯音频 SOTA）：torch 重依赖 + HF 门控模型。**翻案条件**：嘴部运动能量在真实访谈归属准确率不达标（双人小动作多 / 一方说话几乎不动嘴）。
- **自训检测器**：架构 MIT 自由，但标准训练集（WIDER FACE）同样仅限非商业研究 + 1–2 周 ML 工程；蒸馏 SCRFD 权重产伪标签仍属非商用权重派生。**翻案条件**：人脸分析成为产品核心差异点且有常驻 ML 人力。
- **M3 全程判定**（零新依赖）：静帧网格猜"谁张嘴"是其最弱形态；逐帧追踪贵且抖（60s 素材 0.5s 间隔 = 120 次调用）。只任形态归类与模糊仲裁。
- **稠密平滑关键帧 + 线性插值**：契约肥大、防眩晕参数散落数据。**翻案条件**：sparse + smoothstep 在真实素材出现可见跳变且写侧平滑无法吸收。

**Related**: ADR-044（轨道地基；crop_track 进场路径与 tools 注记本条落地）/ ADR-016（渲染器黑盒——采样器只进 packages/clip）/ ADR-020（Ken-Burns 拒绝的边界：crop_track 是 video 源取景决策轨，非 stills 动效）/ ADR-026（speaker_map 不涉 C2PA——分析事实非生成内容）；简报 `docs/archive/tasks-done/reframe-line.md`；双验证 spike 与排期见 `docs/PROGRESS.md` 第三周


## ADR-046: Studio 视觉骨架重塑——灰底填充阶 / 影子只属浮层 / 实体丸化 / 海报优先画廊 / 去全局 header

**Context**: MiniMax Design 走查 + Agent Opus / FLORA / ElevenLabs 对照（证据层 `research/minimax-design.md` §8–§11）暴露五处存量病：① 浅色 composer 白上白读作 wireframe（dark 反而成立——0.12 底 vs 0.21 卡自带阶）；② 配方画廊五根 9:16 强制竖槽 + 横源 letterbox = "黑色墓碑"，且 `posterUrl` 字段存在却被 autoplay 永远跳过、全站无封面概念；③ entity blocks 骑缝设计在截图里读作渲染瑕疵，灰底假设下必然融合；④ 账户区是 Opus 式平铺 list，信息层级缺位；⑤ AppHeader 只装 theme/lang/bell 三个工具却占一条常驻通顶 band。色役粒度盘点（§10）进一步显示：精致感的来源是**角色粒度细**（~20 个可见色役各有阶位），不是品牌色。

**Decision**:

1. **浅色底色定律**：studio（`_app`）`--background` light = **0.96 中性灰**（#f5f5f5 族；暖色调否决——与暗色中性族同宗，用户审美样本全中性）。白卡 = "最亮一层"，靠填充阶浮起。**双主题高度定律统一为一条：浮层 = 更亮的填充落在更暗的底上**（light 0.96→1.0 / dark 0.12→0.21）。landing（`/`）不动，营销音域分离（Scope 条款）。hover `--accent` light = 0.92。
2. **影子只属浮层**：文档流表面（卡 / composer / 媒体 tile）双主题一律无影；浮层（overlay-surface 雾面家族）浅色标配耳语级 `shadow-xl`（把玻璃从内容上揭起），暗色无影（雾面透光自分离）。
3. **实体丸化 + chips 顶置**：composer 无骑缝 blocks（信息密度倒挂 / 剪影打断 / 跨双表面必坏 / 底排失衡）。实体 = 底排左簇 ghost pills（Assets / Persona 16px avatar），**值状态律 = meta→foreground 一步变色**（无填充无彩色）；pills 开雾面 Popover 面板（`side="bottom"` 向下开——向上开盖输入区；浮层影首个正当场景）；无 AssetsModal / PersonaPickerModal（深度管理归未来资产中心页）。暂存文件 = **卡顶类型化 chips 带**（视频缩略图+时长 / 音频波形+时长 / 文档图标+页数 / 上传中转圈百分比，× 即删）——摘要归 pill、清单归 chips、富展示归面板行。
4. **画廊**：卡面形态与布局 = ADR-048（工艺示意图封面 / 均匀 4 列网格 / 证据层移交 overlay）；本条法律 = **click = 检视 overlay 是唯一发射路径**（hover 填充否决：我们的卡面是多产物组合的 teaser + 配方素材依赖，检视是认知步骤不是摩擦）。
5. **去全局 AppHeader**：工具（主题/语言）迁账户 console；**通知 = 内容区右上角唯一浮动芯片**（圆角方块 + 未读点，右上槽位全 `_app` 保留，页面级控件永不占此角——Agent Opus 证据）；移动端留浮动 trigger，PC 展开入口 = rail hover-logo 钮 + `Cmd/Ctrl+B`——rail 可展开、展开状态 cookie 持久化、sidebar 右侧 `border-sidebar-border` 发丝线（ChatGPT parity），`--sidebar == --background` 填充融合维持。账户区两层架构：rail footer popover = 高频 console（身份头 / inset 账户组 / 行内 segmented 偏好 / 帮助段），深度偏好归设置页（FLORA modal 先例）。
6. **色役表治理**："角色 → token × 双主题"对照表为组件唯一取色来源（禁直引色值），缺位角色补 token（send-disabled、group-title、icon-chip-bg、toggle-track）；角色全住中性阶梯，多角色 ≠ 多颜色。表随简报 `archive/tasks-done/home-skeleton-revamp.md` 落地并当验收清单。

**Rationale**: 层级来自阶不来自色（Tailwind 哲学 + MiniMax 黑白多层实证）；影子物理（白底困境的止痛是灰底，不是更软的影）；形态跟信息密度走（pill 36px 说一个词的值为足）；发射深度取决于卡面代表度（卡面越完整代表产物，快捷发射越浅）；交互基准线被大厂产品持续抬高，骨架一次到位比逐面补丁省返工。

**Alternatives（翻案条件随附）**:

- **浅色恢复 shadow（hero 开影）**：白底困境的治标版，被灰底方案整体替代。**翻案条件**：灰底在真实内容密度下被读作"脏/灰扑扑"（landing 对照组失真）。
- **CSS columns 纯样式瀑布流**：零 JS 但元素无法跨列，featured 大卡出局。**翻案条件**：grid+dense+span 的 JS 重排在低端机实测掉帧。
- **hover Use Prompt 双动作**（FLORA/MiniMax 先例）：否决——理由见 Decision 4。**翻案条件**：配方简化为单产物 + 零素材依赖的那类（若存在）可个案重议。
- **bell 降 rail 导航项**：通知的时效性（"你的片子好了"）需要全页一瞥可达，埋进 rail 伤可发现性；浮芯片方案兼得"无 header"与"一瞥可达"。

**Related**: ADR-035/036（只读图与配方 overlay 纪律不变）/ ADR-040（配方=提示词——hover-fill 否决的教义同源）/ ADR-041（结果画布 dock 体系不受影响）/ ADR-016（clip-spec 契约零关联）；证据 `research/minimax-design.md`（§8–§11 二轮证据 + 色役盘点）+ `research/flora.md`（EU AI Act 偏好项）；简报 `docs/archive/tasks-done/home-skeleton-revamp.md`（施工与验收）；需求池登记 EU AI Act 水印偏好一条后续

**附（home/composer 形态细则）**：点阵 = **结果画布唯一签名面**（不可平移面上的固定纹理会广告不存在的 affordance；单面使用让点阵 = 「进入图」的舞台信号）；配方 = muted-foreground 32%（light）/ 30%（dark）、2px 点、32px 网格（FLORA 世界常量，FlowView `dots` prop 世界坐标随缩放，无重铺无缩放补偿；无 `dot-grid` CSS 工具类）；第二处点阵面即违规。demo 封面维持现烘焙帧。① **home = 固定 app-shell**：路由根 `h-svh` 不滚、画廊唯一滚动口 `no-scrollbar` + 顶 fade；hero 文案级 fade 折叠；composer 常驻顶 chrome 并 compact 变形（pill 隐藏 / 输入带收缩，send 常驻）。② 滚动条治理——`:root` / `.dark` 挂 `color-scheme`（原生滚动条随主题），home 滚动口无滚动条。③ composer rest **居中停驻**（`h-[28vh]` spacer 兄弟节点）→ 滚动滑上钉顶成**单行 stadium 探索条**——rounded-full 禁令第三例外；单行条布局 = 左 attach + 单行输入 + 右 send（chips 带/控制行折叠，send 绝对锚点跨形态常驻）；sticky chrome 背板防宽卡露头（纯色 page fill）。④ **核心 hero（标题）常驻**——钉顶收缩悬于单行条之上（logo+标题永驻、subtitle 折进 chrome 内部，钉点零位移）。⑤ **设置 = 共享弹窗组件，不设页面**——SettingsDialog 左 nav + 右内容，`useSettingsDialog()` 随处召唤（memory 等未来深面同构入列）；`/settings` 路由 = channels OAuth 回调 shim（toast + 开 dialog + 弹回 home）。⑥ **console 分组律**——inset 账户块只装价值面（plan/credits/订阅），系统面（设置）降级入偏好组；偏好组行解剖 = 行标签 + **尾置** segmented（theme 图标三态 / 语言 EN·中，inset 轨 + card 滑块），深面行带 chevron。⑦ **滚动编排的形变一律滚动链接，禁时钟过渡**——位置是滚动驱动的即时位移，时钟过渡在快滚下必现半途态；`dockP` = 距钉点末 140px 的 scrollTop 插值，全部形变属性随动，无阈值/迟滞（纯函数无振颤）。⑧ **home hero = 品牌锁up + 品类句**——`LogoMark`+"Repurposer" 常驻钉顶（em 尺寸 mark 随字号缩放），品类句折叠；无 welcome 接待式（无 `welcomeTitle/welcomeSubtitle` 键）。⑨ composer pill 面板**一律向下开**（`side="bottom"`）+ 面板滚动列表 `no-scrollbar`；docked 条下方留白 `pb-14` + 32px 溶解带，卡片不贴条底消失。⑩ **列表一处律**——面板是其暂存列表的展开形态：Assets 面板开则 composer chips 带收起，同一列表永不同帧双呈（计数 pill 留锚）。⑪ **面板行解剖**：方形类型 tile + 名称/类型化 meta 两行 + × 居中，**列律：文件列方、身份列圆**（assets 方、persona/Auto 圆）；配方卡带声预览住 overlay 示例 tab（ADR-048——点击 = 手势，带声天然成立）。⑫ **半径 + padding 非对称**：composer 半径常量 40px（展开态大圆角），坍缩成 56px 一行条时 CSS 半径帽自动裁至 28px = stadium 从盒模型自然涌现；padding 非对称 `px-5 pt-5 pb-3`——底 chin 收紧 12px，控制行贴底。⑬ **hover 动作**（ADR-048）：hover 浮出 = 右上 expand 钮（整卡 cursor-pointer）；只开检视 overlay（ADR-040 唯一发射路径不破——hover 增加发现性 affordance，不产生第二发射路径）。⑭ **composer 壳 = shadcn InputGroup**：chips block-start / MentionEditor 挂 `data-slot=input-group-control` 当 control / 控制行 block-end——focus-within 环、cursor-text 点击聚焦、addon 折叠 border-box 自带 padding 裁剪；描边按卡律（`border-transparent` + 发丝 + bg-card 无影）。**密度律：padding 住 addon 不住容器**——px-4 侧 / pt-4 chips / pb-3 chin，编辑带 py 16→8 随 dockP 防单行裁字；条高 44px、send 锚 16·12→4。

## ADR-047: 产物质量线——剪辑师层 + 有界质检环 + 评审回 chat

**Context**: "图文视频把图片轮播放几个字，这样的产物配不上用户花钱"——全链审查读码归因：**storyboard（WHAT）与 clip-spec（怎么渲）之间没有 timeline 创作层**——逐拍决定由配方默认值 + 阅读速度常量代劳（`tools/stills/procedure.py` 节拍器）；产物出炉后无质检回看；无质量度量。外部评审（harness 层 + domain 层，Grok/Gemini/Claude 三源）收敛验证归因并供给设计契约。

**Decision**:

1. **剪辑师层（editor agent）**：storyboard 与 clip-spec 编译之间新增 timeline 创作层——N-30 声明式新成员（团队的下一成员），吃理解层节拍地图、吐节拍方案（beat plan：图序/运动/切点/强调的逐拍决定）。**单发上限 ≤8–15 拍 / 30–45s**（三源收敛），超出走大纲→逐拍两段，拍间靠显式交接状态（时间锚点/上一拍视觉态/已用素材清单/累积强调历史）。
2. **理解层 v2（节拍地图）**：`MaterialUnderstanding` 扩为素材级——climax/emphasis/quotables/topic boundaries/visual anchors/filler regions，上传时跑 + asset 级复用（汇合需求池「素材理解前移」）。铁律：词级时间戳确定性地基 LLM 永不覆写；**语义强调与声学强调分字段存储**（不一致本身是仲裁信号，预合并 = 自信地错且不可溯源）。
3. **质检环（verify 节点升级）**：吸收旧简报期 3 传输机制（kind + QualityBounce），升级裁决语义——确定性优先（可测量项零 LLM）/ 逐轮独立打分 **best-not-last** / 字段白名单最小 diff 修复 / 首轮过即跳轮 / 双败升级 interrupt（复用既有机制；fidelity 类维持 needs_human 非阻塞徽章）。LLM judge 在纪律下引入（pairwise 冻结基线 / 样例锚定 / 证据先行 / 校准集）——旧简报"judge 单独评审"条款由此兑现。
4. **重规划边（tool-loop 否决边界明文化）**：常备否决的对象 = **模型当编排者**（ReAct 式运行时决策），不翻案；**节点内有界环**（单目的、≤2 轮、结构化反馈、图调度进出）= 合法形态。质检失败的机械路由：修复所需信息不在理解层 schema / 超出单节点参数域 → 交还意图层重规划（汇合需求池 P1「执行中自适应重规划」）；retry 不中自动升级（schema 错误首 pass 常伪装成参数错误）。素材级不足走诚实降级（标题卡开场/换素材），**禁假造钩子**。
5. **评审回 chat**：评审 AI 钩子质量走 chat 收敛（ADR-041），节拍方案（§1 beat plan）是 chat 评审的可寻址界面；无钩子预览闸——渲染服务无 `preview:{seconds}` 参数、无 previews 提问载荷 / HookPreview / HookTrim / swap_hook_shot，降级由 AI 自动 set_title 评估（ADR-049）。
6. **尺子先行**：施工顺序 = 解剖（craft 清单 + 四层归因证据表）→ 理解层 v2 → 剪辑师 → 质检环 → 节拍方案产品面（接 ADR-049 评审界面落位）。§2.1 craft 语法表全部数值 = 编辑部惯例先验，解剖校准前不作验收标准。

**Rationale**: 质量的 80% 在隐性剪辑知识的形式化（外部评审收敛），而形式化的载体已有（指令包装配注入 + track 模型 + 词级时间戳/speaker_map/reframe 数据资产）；缺的是"谁做逐拍决定"的层与"谁检查"的环，不是地基。三源独立否决模型驱动编排——DAG 的编译期估价/确定性执行正是有界环能安全存在的前提。外部评审全部结论 = 模式先验，解剖与台账产出自己的数据后校准。

**Alternatives（翻案条件随附）**:

- **模型驱动编排（tool-loop）**：三源独立否决（成本失控/不可审计/参数坍塌）。**翻案条件**：台账落地后的实测证据（repair 失败率/单发上限实证）证明声明期分工在某场景结构性不足。
- **每表面独立 agent 声明**（MiniMax 剪辑 Agent/导演台 Agent 式）：维护漂移 + 跨面认知断层；我们的答案 = 同一它 + 作用域上下文（ViewScope，后续简报）。**翻案条件**：场景上下文组装的边界泄露实测不可控。

**Related**: ADR-039（四层地图 + N-30 声明机制）/ ADR-016（clip-spec 契约不动）/ ADR-041（表面纪律：进度不进图、编辑走 chat）/ ADR-049（钩子闸不存在）/ N-42（指令包装配注入——剪辑工艺包的载体）/ N-25（用户面单助手不破）；简报 `docs/archive/tasks-done/output-quality-line.md`（施工与验收）；需求池「质检节点」（提级 P1）/「agent 调用台账」（三信号 schema）/「执行中自适应重规划」（路由判据）/「素材理解前移」（汇合理解层 v2）/「节拍方案产品面」（接 ADR-049）

## ADR-048: 配方画廊 v3——三轴模型（产物形态 × 输入路径 × 渠道适配）+ 招牌菜组织原则 + 三级准入闸门

**Status**: Decided (2026-08-27)

**Context**: 真实媒体瀑布流死于产物画幅太杂；工艺示意图封面 + 均匀网格 + 证据层移交 overlay 解决"卡面用什么展示产物"，但组织原则不能是**按输入类型遍历**——逻辑终点是"每种输入 × 每种体裁都要有卡"；同一道菜多输入路径（录像抽帧 / 照片+文稿 / 纯文稿）与 overlay 写死 "Source video" 的文案互相打架。根判：**画廊不为覆盖负责**——覆盖是选题库的活（ADR-042）；卡 = 招牌菜，霸道程度是唯一组织原则。

**Decision**:

1. **三轴模型**（卡的定义正交分解）：
   - **卡轴 = 产物形态**（用户得到什么）——卡的唯一身份，霸道程度排序。
   - **路径轴 = 输入 → 工艺**（用户给什么）——宽槽，管线按输入画像自适应选路径（materialize 注入，ADR-043 现成机制）；路径打通一条槽里加一类，**同一道菜长路径永远不是新座位**。
   - **适配轴 = 渠道**（发到哪）——发布期变量，**永不进卡**：LinkedIn / X / Ins / TikTok / XHS 的真实差异只剩格式（画幅/时长/字幕规范）× 语气（人设风格层）× 机制（OAuth）三层薄皮，全在卡的下游（POSITIONING 平台定位"适配默认"）。文案纪律保持专家腔不变，产物形态全渠道通用。
2. **组织原则 = 招牌菜，画廊不为覆盖负责**：卡存在的唯一理由 = demo 霸道到 ICP 想截图发给同事 + 试做一次被送进主链路（chat）。覆盖需求的家 = 选题库/定位根（ADR-042，W8–W10）：首访靠招牌菜接住，回访靠"你的素材还能切什么"接住。**画廊 → 选题库接力点**：首跑完成后"下一步"提议用本段素材挖选题（口径 W6 对齐，实装归运营端迭代）。
3. **准入三级闸门**：① **场景真实性**（专家真实高频场景，人造场景一票否决，沿用）② **形态或环路不可替代**（ChatGPT 测试，环路价值可上面者豁免，沿用）③ **demo 霸道**——成对示例本身就是卖点（叠卡帧墙、声纹对照包级别）；示例平平的，能力再真也不上桌。体裁问题标准答案：一个能力族只摆最霸道的一种形态，其余形态归 chat 能力——新体裁不再触发"找座位"。
4. **卡面三行写这道菜，不写能力族**：promise 描述 demo 那道菜的形态，与示例永是同一道菜。文案承接四层：卡面纯菜（不加 meta）→ overlay `promptHint` 升格为"还能怎么点"（改口示范 + 能力族暗示，纯文案不做控件）→ 示例 tab 不说话的广度（多形态示例平铺）→ 画廊末尾一句总承接 + 流程内教学（预填模板可改 = 第一次提示词教学）。
5. **卡面形式**：黑白灰工艺示意图封面（200px 无字测试）/ 卡面状态机（rest 静态 → hover 过程动画 + 右上 expand 钮，click = 检视 overlay 唯一发射路径）/ 均匀网格零真实媒体 / 证据层 = overlay 示例 tab 成对前后对比（拿不出真实成对示例的卡不进网格）。
6. **输入槽两类卡规则**：**转化类**（形态 = 改造你的录像：高光切片 / 访谈分镜 / 多语言字幕 / 原声配音）= 窄槽必填，Input 小节直说要什么——窄是这道菜的本性；**合成类**（素材是原料：金句卡 / 轮播图 / 社媒帖 / 图文视频）= 宽槽任选 + 可空（copy-writer 无素材 lift 已落地），Input 小节"给什么都行"。槽宽 = 管线真实路径的边界——不更宽（诚实纪律），不更窄（不绑死）。`input_slots` 增"任选一"语义（字段命名随实施过 NAMING §7），overlay 发射闸门同步。
7. **阵容 = 八卡六形态**（RECIPES §4 同步）：竖屏短片（高光切片 / 访谈分镜）/ 多语言版本（多语言字幕 / 原声配音）/ 图文轮播视频（图文视频）/ 金句叠卡（金句卡）/ 轮播幻灯（轮播图）/ 帖子长文（社媒帖）。排序 = 霸道序：**原声配音 → 金句卡 → 高光切片 → 多语言字幕 → 图文视频 → 轮播图 → 访谈分镜 → 社媒帖**（网格从左到右自然落位，无行语义）。两处调整：**金句卡 = 叠卡本体**（帧卡 Output 化带 source_ref 寻址，工程见 `docs/tasks/quote-cards-redesign.md`）；**社媒帖 demo 重修为风格对照**（同素材"无人设版 vs 人设版"并排——文本族过闸门③的标准姿势，随烘焙批）。
8. **阵容治理**：任何座位变更（进/出/合并/拆分）必须附翻案条件 + 认路级证据（复述测试 / 真实用户行为），不当周翻案。

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

- RECIPES §4（六形态阵容 + 霸道排序 + 两类卡）/ §4.8（三级闸门）/ §7.1–7.3（input_slots 语义、承接四层、排序无行语义）= 本条的规格落点；金句卡工程简报 = `docs/tasks/quote-cards-redesign.md`。
- 画廊卡面形态与布局以本条为准；「click = 检视 overlay 唯一发射路径」不破（ADR-046 D4）。

**Alternatives（翻案条件随附）**:

- **chip 预设行**（外部提案：overlay 加 ≤3 维度预设 chip，点击改写 prompt 句子块）：否决——预设参数控件禁令（RECIPES §7.2）与 promptHint 可点形态证据闸（RECIPES §10）已覆盖同类诉求；表达轴的可见性 = prompt 文本 + promptHint + 示例 tab 三件套。**翻案条件**：复述测试级证据证明用户在 overlay 内认不出可改口味（实测认不出，不是"可能会"）。
- **变体缩略图真实媒体上卡面**（外部提案：≤3 个体裁变体缩略图当认路承重墙）：否决——真实媒体死于画幅杂乱，网格零真实媒体是根基；体裁认路的标准答案 = 示例 tab 多形态平铺 + 同族只摆最霸道形态。**翻案条件**：示例 tab 打开率 / 认路实测证明用户根本不进 overlay。
- **字幕 + 配音合并为一卡**（"一个外语版本意图"论）：拆分维持——"保留原声看字幕"与"用我的声音说外语"是两种意图，配音卡名把声纹克隆护城河写进菜名。**翻案条件**：认路证据显示用户在两张卡间犹豫选错。
- **画廊按渠道出卡**（LinkedIn 卡 / TikTok 卡）：永久否决——渠道是适配轴不是卡轴（第 1 条）。

**Related**: ADR-046（画廊条以本条为准）/ ADR-040（唯一发射路径）/ ADR-042（选题库 = 覆盖的家，画廊→选题库接力点）/ ADR-043（materialize 输入画像注入 = 路径轴机制）/ ADR-035/041（画布纪律）；RECIPES §4/§7 / STRATEGY §5 / POSITIONING（平台定位 = 适配轴）；简报 `docs/archive/tasks-done/recipe-gallery-v2.md` / `docs/tasks/quote-cards-redesign.md`（金句卡工程）

## ADR-049: 钩子预览闸退役——评审回 chat，渲染无闸，节拍方案为评审界面

**Status**: Decided (2026-08-24)

**Context**: 钩子预览闸判为过度——dock 三路径（确认 / 调整 / 降级）把评审 AI 钩子质量的责任交给用户，知识专家用户不擅长此评估（决策疲劳），且哲学冲突：产品核心流（ADR-041 + ADR-035 衍生）= **必要评审在 chat 完成 → chat 收敛后走渲染 → 渲染好进 canvas node**；hook gate 在 chat 之外插了一段"评审视频"环节，违反三段不破的边界。正确的产品评审面 = **节拍方案**（beat plan，ADR-047 §1）——timeline 创作层的中间产物（图序 / 运动 / 切点 / 强调），纯数据 + 图片引用，零渲染成本，chat 评审的可寻址产物（AGENT_ARCHITECTURE 总论：每个中间产物可寻址、可复用、可单独重跑）。让用户在 chat 里看节拍方案卡片 = 评到 AI 决策内容本身；hook gate 把 beat plan 翻译成视频让用户看 = 绕了一步。

**Decision**:

1. **无 hook_gate / release_renders 节点**：无 `app/pipeline/hook_gate.py`；orchestrator 无编译期注入块；`clips/node.py` 无闸感抑制分支——select_clips 正常扇出 render，render_status 走 pending 路径。
2. **渲染服务无 `preview:{seconds}` 参数**——黑盒内部参数，无外部契约。
3. **提问载荷无 previews 字段、无 HookPreview / HookTrim**：QuestionDock = 纯 choice / task_book 二态；无 `hookGate.*` 翻译键。
4. **无 swap_hook_shot op**；`SetTrimParams` / `set_trim` 保留（chat 评审调尾切点是 chat 评审的一部分）；渲染端 `packages/clip/src/types.ts` `image_shots` 字段保留（节拍方案仍消费）。
5. **降级走 AI 自动 `set_title`**：质量差时 AI 评估钩子自动降级（标题卡开场）——不需要用户决策；保留 set_title op（运行期 AI 触发）。
6. **节拍方案 = chat 评审界面**：beat plan 作为中间产物落到 Output.payload 或新表——chat 评审展开的卡片化形态（呈现位置不在本条范围；本条只定机制 + 节拍方案为评审界面）。
7. **闸感抑制的工程价值归位**：避免白烧通过 chat 的报价 fold + AI 自评质检环覆盖——产品没有"渲染前用户卡"的形态。

**Rationale**: 产品哲学一致性优先——chat-as-review / render-as-execution / canvas-as-result 三段不可破；hook gate 评估的是渲染结果而非 AI 决策内容，评审点错位。AI 自评（质检环 + 自动 set_title 降级）保留——评估的是 AI 自身产物，不交给用户——符合 ADR-041 "评审走 chat 不走 canvas" 与 ADR-035 "可操作画布永拒"。闸感抑制的工程价值（避免白烧）由 chat 收敛 + AI 自评覆盖，无须用户介入。

**Alternatives（翻案条件随附）**:

- **保留 dock 三路径**：知识专家评审疲劳实测低于收益——拦截率统计显著 + 调整 op 真实使用率 > 阈值。**翻案条件**：自有数据证明用户主动评审收益 > 决策疲劳。
- **节拍方案卡片由 chat 流承载 vs overlay vs canvas 节点 metadata**：本条定 beat plan 为评审界面，不决呈现位置（归节拍方案卡片化批次）。
- **AI 不自动降级，保留 chat 主动 set_title**：本 ADR 默认 AI 自动降级——chat 主动是补充入口；不反对 chat 里说"加标题卡开场"。

**Related**: ADR-047 §5 / ADR-041（评审在 chat、渲染进 canvas 的哲学基底）/ ADR-035（可操作画布永拒不变）/ ADR-040（chat 唯一发射路径不变）/ ADR-039（节点对象化 + 估价 = fold，渲染前用户可见是估价而非视频预览）

## ADR-050: 会话不跨长等待——计量内存累积 + 渲染会话收窄 + runner 禁污 Session-2 节点 + DEFERRABLE FK（D9 死锁族）

**Status**: Decided (2026-08-28)

**Context**: quote-cards v3 e2e 连跑把 dev worker 反复卡成永久 wedge。pg 取证（pg_stat_activity / pg_locks / pageinspect 逐层下钻）最终定位三个同族病灶，共享一个形状——**runner 的 Session 2 持有 `workflow_steps` 行锁横跨 LLM 等待，行内第二个写者等它，而它等第二个写者**（应用级自死锁）：① 计量 `record_usage` 每次 LLM 调用另开 session UPDATE 本 step 行；② 渲染 `render_output` 持 session 横跨最长 900s 渲染 POST；③ **质量打回重跑时 feedback-pop 走 `node.spec = spec` ORM 赋值**——Session-2 node 变脏，下一次 autoflush（outputs INSERT 时）锁本 step 行至 run 尾，runner 自己的 display writer（`_fill_summary`，own-session jsonb_set）等自己的事务——pageinspect tuple 版本对（xmin/xmax）实锤。verify bounce 路径是触发点：只有 attempt≥2（带 feedback）才脏节点，这解释了"首跑绿、连跑 wedge"的观察史。

**Decision**:

1. **计量改内存累积（`app/metering.py`）**：`bind_workflow_step` 绑定 contextvar 内存台账；`record_usage` / `record_media_usage` 只改内存、**零 SQL**。`execute_step`（orchestrator.py）在执行尾段用 `merge_accrued_cost` 归并一次写入——成功 / Suspend / QualityBounce / 瞬时重试 / 失败五个终态分支全部记账（每节点 N 次写 → 1 次写）。cost 形状 `{prompt_tokens, completion_tokens, fixed_cost, units?}` 不变；跨 attempt 累加（与旧 per-call 机制语义对齐）；空台账 → cost 保持 NULL（估价对账 SQL 继续忽略未计量节点）。**不加表、不加字段**。
2. **render_output 会话收窄（`app/pipeline/rendering.py`）**：短 session 快照行数据（spec / files / project_id / user_id / lang）→ **无 session** 横跨渲染 POST → 新短 session 做 guarded 终态写入（morph 竞态守卫条件不变）。`_mirror_superseded_node` 签名由 `Project` 改收 `lang`。
   - guarded-write 纪律 = **身份守卫**（ADR-079）——render 三处终态写谓词 = `render_claim_token=:mine`（rowcount 检查不变）；execute_step 四尾同样 = 条件 UPDATE + rowcount（fenced → rollback + 零副作用）。会话收窄纪律（短 session / 无 session 横跨长等待）不变。
3. **runner 禁污 Session-2 节点（铁律）**：Session 2 内对 step 行的写只属于 execute_step 尾段结算；runner 中途要写 spec 一律走 `step_display` 的 own-session 原子写（`_pop_spec_field` jsonb `-` 减法 / `_set_*` jsonb_set）。两处 feedback-pop（`derivative_dispatch` / `clips/node`）已改 `_pop_spec_field`。
4. **四条 runner-父行 FK 改 DEFERRABLE INITIALLY DEFERRED**（migration `c3a9e71f52d0`）：`outputs.workflow_step_id` / `outputs.project_id` / `operations.project_id` / `workflow_steps.run_id`——Session 2 中途 INSERT 子行不再对父行持 KEY SHARE 至提交，父行写者（display writers / maybe_finalize / run 状态翻转）永不被 mid-run 锁窗口卡住。完整性不变，检查挪到 COMMIT。
5. **DB 保险丝**：`ALTER ROLE <app_role> SET idle_in_transaction_session_timeout = '600s'`——**部署新环境时必做**（本条即部署说明）。保险丝是兜底不是许可，只防永久 wedge：Session 2 横跨 runner 的 LLM await 是保留设计（director_understand 一次调用 + schema 修复重试 ≈ 2 分钟纯等待），10 分钟足以把灾难收敛为有界失败而不误杀健康事务。
6. **dev 脚本清理纪律**：FK DELETE 前先 terminate `idle in transaction` 超 15s 的他者 backends（`bake_quote_chain.py` / `accept_quote_card_family.py` 等脚本同款片段；`pg_stat_activity.query` 全是参数化语句、无字面 id，项目级文本匹配不可行，dev 箱上 >15s idle-in-tx 即 wedge 类）。
7. **execute_step 异常分支 node=None 守卫**：清理跑赢 worker 时（项目被删）三异常分支直接返回，不再 AttributeError。

**明确不做**：runner Session 2 持有权重构（污节点已禁 + FK 锁窗口已关，死锁类整族消除，无须更大 blast radius）；`agent_calls` 台账（需求池 P1，第十一周）；verify bounce 路径本身（触发点随 ③ 修复消失）。

**Rationale**: 死锁的根不是"session 持有太久"，而是"行内长等待期间存在第二个写者 + Session-2 行锁"。把第二个写者消灭（计量归并）、把 Session-2 的行锁窗口关到最小（禁污节点 + FK 延迟到 COMMIT）= 锁族整族死亡，且语义逐条对齐旧机制（累加记账 / NULL 纪律 / guarded 写 / feedback 只搭一轮）。

**Alternatives（翻案条件随附）**:

- **runner Session 2 也拆短**：本 ADR 出闸。**翻案条件**：出现新的"runner 执行期必须写同一行"的需求（先审视能否走 own-session 原子写或尾段归并）。
- **计量入独立队列表再异步落账**：否决——无新表新字段（用户裁定），内存累积已满足所有消费方（RunResponse.cost = 序列化时聚合，无中途可见性需求）。
- **display writers 加 lock_timeout 跳过**：否决——feedback-pop 修复后撞锁窗口已消失；跳过着会常态化丢失完成态 summary（输出型节点 summary 写在 outputs flush 之后）。
- **保险丝更短（如 120s）**：否决——Session 2 的 LLM await 纯等待可达 ~2 分钟，过短误杀健康事务。**翻案条件**：观测证明 600s 仍误杀正常单步（届时先查该步为何纯等待这么久，而非再放宽）。

**Related**: ADR-025（cost 计量账本机制——本条改写入路径不改账本形状）/ ADR-017（Postgres 即队列）/ ADR-039（队列与重试机制；execute_step 终态分支结构；质检打回 feedback 通道）/ MODULE_ARCHITECTURE §7.2（队列机制——本条为其补会话纪律）

## ADR-051: FLORA 对齐——画布优先路由（overlay 概念退役）+ 折叠打勾增量感 + 节点交互升级 + 提问 dock 形态

**Status**: Decided (2026-08-31)

**Context**: FLORA 工作台对照走查暴露五处差距：① 点阵太淡（1px/20% 在白画布上几乎不可见，FLORA 的点阵明显可读）；② 免责行位置/文案学了一半（位置不常驻、文案自造）；③ 提问选项 UI 差距——FLORA 是选项 1/2/3 + 尾行铅笔手输（整个 dock 变形、原输入行隐藏），我方是保留原输入行 + placeholder 换 "Something else"；④ run 节点生命周期交互（节点出生即有最终尺寸 → running 动画 → 结果填充 → hover tooltip + 磨砂 prompt 框可编辑 → 重跑 → 变体分页 1 of N → 详情面板陈列模型事实）是"让用户一步一步进行下去"的关键手感，run 期缺增量感（产物只在 output 行落地时凭空出现，占位机制缺席）不行；⑤ 中间节点噪音（"1 step" 过程脊）。架构判断：**物种差异不是架构缺陷**——FLORA node = 单次生成单元，我们 run = 编译批量 DAG 共享一份 director plan；但增量感与节点交互是真实差距，交互模式必须升级。路由层：项目页永远画布+dock，无 `?overlay=` 参数。原则：**打勾流不动只浓缩**（折叠型 Claude Code 式——对方一样有 "Running node" 打勾，浓缩即对齐）；**无 overlay 概念**，进来就是画布+dock；**chat 与意图识别毫无变化**；hover prompt 框要学习（心智负担更少，是更正确的交互）；变体分页一并做；**禁令「图面模型名永禁」的破法见 Decision 5**（事实展示解禁，SKU 货架永禁不动）。

**Decision**:

1. **画布优先路由（无 overlay 概念）**：`/projects/$id` 永远 = 画布 + dock——无 `?overlay=chat` / `?overlay=run` 路由参数、无 fullscreen 壳，dock 壳 = 唯一 chat 外壳。composer 发送 = 建项目 + 上传素材 → **直达项目页画布+dock**，草稿经 router state 交付 dock 发出首条 `POST /chat`（消息机器零变化）。processing 项目卡片 / 待确认 CTA / 继续设置 / tours 全部直达项目页——dock 按项目态自呈现（待确认 = 任务书 dock；活 run = 打勾 + 活画布）。断线重连 / 历史打开直接呈现终态不变（ADR-041 D2）。**诞生编排 = 生长驱动**：画布挂载期间出生的节点（run 开始占位物化 / 产物原位填充 = 收官节拍 / 修订生长）按编译序 `BIRTH_STAGGER_MS` 交错入场 + 边描画；running 占位卡带 FLORA 填充擦除（纯 CSS 封顶 96%）；水合首帧（刷新/重连/历史）永不重播。配套缝：dock 起跑（Start 钮 / 散文确认 / 修订 run）即经 `onRunStarted` 通知页面 refetch——页面 SSE 从第一拍挂上，run 期活画布即时渲染。
2. **打勾流 + 占位（增量感两件）**：打勾流是唯一步骤叙事进度面（ADR-041 D2）——形态 = 流内一行动态动作行 + 平铺步骤（活态 status line / 终态收据同一行原位 morph，CHAT_ARCH §8.7），输入组上方无折叠状态行。同时 run 期画布活起来：**占位产物卡在 run 开始即物化**——草稿图就是占位（图本体先存在、产物落地填充节点，ADR-057），`productNodeSize(aspect)` 让占位卡出生即占最终位置与尺寸，产物落地即原地填充（画幅未知取默认档）。**步骤叙事不进图**：步骤清单永不上图；产物占位/填充是图的**内容**，不是进度剧场——禁令 #4「禁假进度」不破（占位 = 编译期已知花名册，禁虚构产物）。
3. **提问 dock 形态（形态律，现行法 = ADR-053 R1）**：渲染按 `options` 是否为空分流——文字问（options 空）= 普通对话消息，永不 dock；选项问 = **阻塞形态**：待决时输入行与免责行让位（CSS 隐藏不卸载，编辑器草稿保住），pill = 问题行 + × + 选项行 + 尾行铅笔自由输入（与选项行同一 item 解剖——铅笔坐进字母徽章同款 tile）；**default_path 行不渲染**（跳过语义由 × 承担）。× = bail 出口（取 default_path，interrupt 停活 run）。回答坍缩 / 已答问题入流 / 判定结算见 ADR-053 与 CHAT_ARCH §8.5。
4. **节点交互（卡面 prompt 区 + 变体分页）**：产物卡面常驻 prompt 区展示**该产物自己的 spec**（fork 派生行的目标语言 / hook / 参数，卡说自己的话）；prompt 直改 = 一次 wiring op + 定价确认（ADR-057 K4；通道 = 确定性手势走 `POST /projects/{id}/graph/revise`，chat 修订骑 `POST /chat` 唯一意图面——ADR-058 通道分家），永不开新执行通道。修订/重跑后 → **变体分页（1 of N）**：数据源 = Operation Model 版本快照 + fork 家族，卡上翻页切换展示。无过程脊（ADR-057——step 住节点内部）。
5. **模型事实陈列**：**模型 / provider 事实可出现在详情面**（灯厢信息栏等 detail surface，陈列事实 = 诚实）；**节点面永无模型选择器、无 SKU 货架**；节点 caption 恒友好名不变。真实第二 provider 出现时可选 picker 的用户形态仍是策略开关（需求池「LLM provider 抽象」不变），本条只解禁事实陈列。
6. **点阵与免责行**：点阵 = 结果画布唯一签名面（配方见 ADR-046 附）；dock 常驻免责行，en = "Repurposer is AI and can make mistakes. Check important info."（zh 镜像「Repurposer 是 AI，可能出错。重要信息请核对。」）——位置 = 输入组**上方**耳语（不回容器内、不夹在问句与输入之间）；文字问不隐藏任何 chrome，选项问待决时免责行随输入行一并让位（ADR-053 R1），其余时刻免责行与输入框同常驻。dock placeholder = @ mention 教学文案：「Use '@' to mention nodes and describe changes」/「输入 @ 引用节点，描述你的修改想法」——**只教 '@'，不写 '/'**（chat 无 slash 体系，写了即虚假承诺——虚构 SKU 禁令同适用于 placeholder；「nodes」措辞成立：@ 候选〔素材/产物〕本就是画布节点）。**placeholder 耳语注册**：耳语靠**对比度**不靠字号——渲染 = 继承输入字号 14px + meta-foreground（比正文 muted 暗一档），单行 nowrap 省略；免责行 = 12px。**耳语层色**：meta-foreground 暗色档 = **0.42**（FLORA #606060 实测，整个暗色耳语层〔meta 标签 / disabled / 免责行〕同值）；**用户气泡**：Bubble `muted` 变体暗色 = `dark:bg-white/10`（FLORA #FFFFFF1A 实测，磨砂面板上的半透明 veil 比实心 muted 阶更静；亮色不动），padding px-4 py-2。**dock 输入框增高上限 max-h-56**；暂存附件 chip = **缩略图先行**（`StagedAttachmentChip`：image = 文件本体 / video = 首帧，走共享 `useStagedFileMeta` 探针，object URL 自回收；音频/文档留图标），与 composer 的 AssetChips 同一套暂存文件语言（三处输入面同构：composer / 无画布 full 形态 / 有画布 panel·dock 形态）。**滚动条统一**：`@utility thin-scroll`（6px rounded thumb = foreground 12% / 透明轨 / 无 gutter），挂消息流视口 + dock 编辑器；无 inline `scrollbarWidth`。**输入框解剖 = 两行流式**：rest 即两行——满宽文本带（上）+ 控制条流入（下）（ElevenLabs composer 同构；无覆盖层、无测量、构造上不可能振荡）；输入组全形态恒 `rounded-xl`（stadium 只属于真单行盒）。attach 图标 = **Plus**（dock 与 composer Assets 实体钮同）；暂存 chip 的 ×/重试**悬停显现**（error 态常显防死端，focus-within 罩键盘）；**控制条 glyph 铁轨对齐**——strip 去容器 padding，`+` glyph 左缘 / `↑` glyph 右缘钉文本带 12px 铁轨（36px 钮 − 18px glyph = 9px 内缩，ml/mr-[3px]），双 glyph 同 18px 光学对齐——composer glyph 左缘对齐律的 dock 孪生。
7. **dock 形态机（现行法 = ADR-056 三形态机）**：**首个 run 到达前**项目页 = 居中全屏 chat（full 形态：消息舞台占满页面上部，输入组同一台消息机器原地不动）+ 左上角仅「← Projects」返回 pill；首个 run 到达同一拍：舞台原地淡出（300ms opacity）、画布延迟 150ms 淡入（500ms）、返回 pill crossfade 成完全体 ProjectMenu，chat 收拢变形为——**桌面 = 右侧面板（panel 形态：full-bleed 画布上的雾面 overlay，float/docked-right 双几何 header 切换，解剖与保草稿结构见 ADR-056）/ 移动端 = 底部 dock（dock 形态）**。驱动 = 页面 `latestRun`（loading 闸保证主树首渲染即定态——带 run 项目直挂 panel/dock 形态，水合首帧永不重播，诞生编排铁律同义）。**hidden 态**（dock 与 panel 通用）：用户手势（dock 输入行 − 钮 / panel 头部 − 钮）把整个 chat 收成右下角 LogoMark 磨砂圆点——节点密集后要看完整画布、截图分享正在使用的产品，是正当场景；唤回触发 = agent 发声 / 待决提问（choice / 任务书 dock）/ mention 插入召回（ADR-069）——用户只能藏起一个**静态输入组**，永远藏不住新信息（禁静默在 hidden 下存活）；活 run 状态行故意不作触发（画布擦除已传达活性，收官 recap 属 agent 发声自行唤回）。**否决的 FLORA 形态**：右下浮动 panel、Queue 条（违反唯一进度面）、多 chat（项目单会话模型 ADR-041 D8）、窗口管理控件。组件名 = ChatDock（`components/chat/`；i18n 命名空间 `generationOverlay.*` 保留——消息键名不是产品概念）。
8. **dock 拆粘（移动端 dock 法则；桌面 panel 形态的三职责天然分层——问句/任务书 pill 钉面板底寄存、输入钉面板底、历史 = 面板滚动区，见 ADR-056）**：决策（问句）/ 行动（输入）/ 诚实（免责行）三寄存分离：① QuestionDock（task_book / choice）= **独立浮层 pill** 悬在输入组上方，dock-surface 同款磨砂 + 发丝线；② 输入容器只装输入组（+chips 带——无折叠打勾状态行：消息流恒在，折叠行是纯重复）；历史区 = 自有磨砂浮层悬于输入组上方（**输入框独立层律**——输入组恒为独立一层，永不与消息流融为一体）；③ 免责行钉在输入组**上方**常驻耳语。**停靠法则不动**——问句 pill 恒可见，不随计划卡滚走。**否决**：只移免责行（问句+输入焊接还在，解一半）；行动随卡进流（计划卡高时 Start 滚出视口，废停靠法则）。细则：Ⓐ pill↔输入组间距 `mb-2.5`；Ⓑ **task_book pill 单行化 + 无 Cancel**（非阻塞提问不配负向动作：「不开始」用沉默表达——继续聊 = 修订、走开 = 计划如实待确认、/projects 可删；FLORA / ChatGPT 的非阻塞确认 pill 均无负向动作；**选项问的 × = 阻塞形态的 bail 出口**——取 default_path、interrupt 的 × 停活 run），Start 并入顶行成单行解剖（✓ + 问句 + Start）；Ⓒ 输入组全形态恒 `rounded-xl`（两行流式解剖下 dock 输入组 rest 即两带，stadium 只属于真单行盒 = 首页钉顶条）；问句 pill 恒 `rounded-xl`。

**Consequences**:

- ADR-035 / ADR-036 不变：只读基座不破——卡面 prompt 区是卡面控件不是图编辑；拓扑编辑手势任何面物理缺席（#12 本义）不变；可操作画布永拒不变。
- chat 与意图识别**零变化**：PlanAgent / ChatIntentAgent / 四态契约 / plan path / QuestionDock 数据层（question/answer JSONB、autoResume、停靠法则）全部不动。
- 服务端增量很小：占位 = 草稿图（ADR-057）；per-product spec 从编译图 slot 参数投影（outputs.py 序列化增量）；变体分页吃 Operation Model 快照（ADR-032 现成）。无新表、无新执行通道。
- 简报 `docs/archive/tasks-done/flora-parity.md`（验收标准 + Prohibited Behaviors）。
- **run 活性同步（三条）**：① **interrupt 准入**——`key_arguments` 为空时选项只剩默认项，单选项提问无分支 = 纯摩擦（writer-only stub understanding 必中：「Full-talk highlights」是 clips 话语，对 post 任务书错体系），interrupt runner 自动按默认项决议（`spec.answer` 与 human pick 同形状，director_plan 经 `_interrupt_direction` 的读法不变），不停车；顾问姿态 = 每轮一问（ADR-052 判词 5）。② **画布活性 = runAlive，waiting ⊆ running**——画布与消息流吃同一个 `step.status` 值、各按自己粒度诚实（FLORA 对齐：message 侧 "Running node…" 与画布节点同一值）：消息流保 `waiting` 细分（CircleHelp 提问行），画布只有「活 / 不活」一档——parked interrupt 映射 running（脊脉冲 + 边包裹不断），占位卡在生产步骤未启动时也随活 run 保 FLORA 擦除（roster 服务端只对活 run 投影，`runAlive` 客户端兜 stale 帧），park 帧画布不再死寂；步骤提问 UI 永不上图（D2）不破。③ **plan 卡 compile 期任务书兜底**——director_plan 节点 `spec.task_book` 编译期钉入（与 runtime 覆写同源 = 生成节点 `spec.slot`），`canvas_text` 的 `_plan_summary` fallback 从出生即有正文，park 时不再是透明空壳；runtime 的 plan_summary 落地后同文替换（同源渲染，无闪变）。

**Alternatives（翻案条件随附）**:

- **FLORA 式每节点一 workflow**（节点 = 单次生成单元，图随生成增量生长）：否决——我们的 run = 编译批量 DAG 共享 director plan，物种差异是设计选择不是欠债；增量感由占位物化 + 打勾流兑现，不换执行模型。**翻案条件**：真实用户在走查中持续把「一个产物一个格子」误认为可单独运行的单元并试图连线。
- **保留 fullscreen 壳作为 run 期可选视图**：否决——双壳 = 两套进度面悖论（ADR-041 D2）；活画布 + 打勾流已覆盖其全部正当场景。
- **hover prompt 框直接改图（就地重跑，不经 chat）**：否决——违反 chat 唯一意图面与「改动在 chat」（ADR-041 D5）；卡面 prompt 直改 = 确定性图动作（ADR-057 K4 / ADR-058 通道分家），意图修订仍走 chat。

**Related**: ADR-041 / ADR-035（可操作画布永拒不变）/ ADR-036（只读基座不变）/ ADR-053（提问形态律现行法）/ ADR-056（三形态机现行法）/ ADR-057（占位 = 草稿图；卡面 prompt 区）/ ADR-058（通道分家）/ ADR-043 / ADR-032（Operation Model 快照 = 变体分页数据源）/ ADR-039（agent 层零变化）/ ADR-040（chat 唯一发射路径）；施工简报 `docs/archive/tasks-done/flora-parity.md`；证据 = FLORA 工作台走查

## ADR-052: 对话工作流母蓝图——厚 agent 判词 + 双引擎分离 + brief 账本 + ask 一等动作 + 预填评审卡 + 有界 loop 节点

**Status**: Decided (2026-09-03；概念母文档 = `DIALOG_WORKFLOW.md`；施工切分 = B1~B4，PROGRESS W7）

**Context**: 真实使用走查报「不知所措」，系统分析定位三因：**问题数量 × 不可答性 × 主路缺失**。对照 Agent Opus 走查确认任务书卡是**东施效颦**——Opus 的卡 = 已填对话状态的渲染（用户做识别题），我们的卡 = 空表格（用户做创作题）；Opus 每轮一问、一词可答、散文恒带默认路径（"I'll use my best judgment if you step away"）。概念批判三连：①「导演」是否是产品流程的正确概念——它是动词（素材理解 + 派工）不是角色；② PlanAgent 是否真是「Agent」——按业界定义（Anthropic workflow/agent 分野）全系统没有一个 autonomy 义的 agent；③ 自造词提案（intake/workshop 等）在业界标准（Claude/DeepSeek harness、agno、pi、AI SDK、Mastra）找不到坐标 = 过度设计，撤回。蓝图：整个用户对话 workflow——聊天 → 识别意图 → 分配任务（各环节 agent 角色带技能/tool）→ 产出结果，workflow 结束；我们是做「厚」agent 的，基类都在。

**Decision**:

1. **厚 agent 判词（ADR-039）**：产品 = 一个厚 agent（assistant 单身份，N-25 双轨不变）；其「厚」= **声明式部件的组合厚度**（Agent 漏斗 × NodeBase × compile_graph × 工具注册表 × brief 账本 × 提问机器），不是 autonomy。本系统无开放式自主是设计不是缺口——chat 边缘 = routing + 有界工具 loop（ADR-077），pipeline = orchestrator-workers 模式；`Agent` 类 = 声明式结构化调用（= AI SDK `generateObject`），类名不动；业界 autonomy 义永不适用于任何内部模块，开放式 autonomy 维持永拒。
2. **双引擎 workflow（概念统一，引擎分离）**：对话 = 事件驱动状态机（router + brief 账本 + 提问机器）；生产 = 编译 DAG。**对话永不编译进 DAG**（开放轮数 / 人是环境 / 报价不适用）；两引擎唯一接口 = 任务书（对话引擎的产出 = 生产引擎的输入，出生地唯一，ADR-043 不变）。
3. **canonical 词汇，零自造词**：chat 边缘双件 = **intent router**（`plan_agent` / `chat_intent_agent` 同概念两相位 prompt，相位 = 上下文参数）；`director_understand` → **`understand`**、`director_plan` → **`plan`**；`pending_intent` → **`pending_brief`**。业界坐标：Anthropic routing / Plan-and-Execute / AI SDK generateObject / LangGraph node·step。判例归 NAMING N-43~N-47；更名批 = B1（commit 级自绿）。（plan 归两主：chat 侧计划书义 = plan path / presented_plan，pipeline planner 义不动；存储字 `task_book` / `book_summary` 冻结。判例 N-44 / N-52。）
4. **brief 账本（P0）**：对话引擎的结构化状态（`projects.pending_brief`）——槽位 topic / audience / tone / constraints[] / material_state，**每槽带来源 user-stated > inferred > default，代码侧合并**（LLM proposes, code decides 不变）；账本 = 上下文工程主压缩件，累积 prompt 叙事降存档位。
5. **ask 一等动作（P0）**：pre-run 相位动作集 = **ask / draft / answer / start**（draft = 起草/修订任务书，从不生成）；ask 复用 shape C（choice 3 项——真二元抉择降 2，对齐 FLORA/Opus 三选项节奏——+ freeform，走 dock 提问机器）。**提问策略三条**：一轮最多一问只问决定质量的那个缺失槽 / 选项一词可答、freeform 恒在 / 散文必带默认路径——**每轮一问、每问可一词答**（顾问姿态的本义是不让用户做创作题，不是不问）。**出书门槛**：brief 有根（主题 / 素材 / 明确配方，三者居一）才 dock 任务书；zero-material safety net / no-material lift 同属此策略。
6. **任务书卡 = brief 的渲染（P1）**：卡顶 = brief 槽位渲染（有值显示、inferred 可点改、无值不显示、**零空框**）；per-row focus 与 run 级 instruction 两个空文本框**全删**（修订走点值改 / 聊天改，chat 恒胜不变）；确认 pill 按动作命名（"Save & generate" /「保存并开始」）；散文第二句恒为默认路径声明（≤2 句，本条给它 schema 级牙齿）。
7. **角色 = 节点的 display 属性**：工作流内部永远函数名（动词族零人格）；用户可见进行态叙事 = 节点声明上的可选展示属性（`task_name` 机制升级位），**默认写工艺不写人**（「正在剪辑成片…」✓ /「剪辑师正在…」✗）——N-24 禁令对象是 assistant 的班子包装，步骤级工艺叙事是另一层；人形叙事 = 翻 N-24 的案，门槛维持。
8. **有界 loop 节点 = 生产侧 agent 性的合法座位**：编译期排不出拓扑的活（搜索 / 阅读，步数不可预知）由 `NodeBase` 子类承接——内部 mini tool-loop（工具 = `app/tools/` 现成注册表）+ **三护栏**：迭代上限（节点声明）/ 报价 = fold（上限 × 单次，估价体系不破）/ 对外 = DAG 单节点（拓扑 / 占位 / SSE / 诞生编排全无感）。业界同构：LangGraph subgraph / Mastra agent-in-step / Anthropic agentic component。会话层有界工具 loop 同合法（ADR-077：生产封闭 / 服务收编 / 执行永拒）；开放式 autonomy（无界循环 / 自主改拓扑 / 自我 steering）永拒不变。首个试点 = research 节点（产出 research brief artifact 喂 writer）。

**Consequences**:

- 概念母文档 = `DIALOG_WORKFLOW.md`（本条的完整展开）。
- 顾问姿态四律① = 每轮一问、每问可一词答（判词 5，CLAUDE.md 同文）；ADR-043 任务书契约不变（接口 / 出生地 / 链语法原样）；ADR-047「模型驱动编排 = 禁；节点内有界环 = 合法」与判词 8 同构扩展（loop 节点的环在节点内、有界、对外单节点）。
- NAMING N-43~N-47（厚 agent 判词 / router·understand·plan 更名 / brief 账本 / 角色 = display 属性 / 有界 loop 节点）。
- 悬案归 DIALOG_WORKFLOW §8（槽位优先级参数 / router 两相位实例合并时机——待真实对话数据回收）。

**Alternatives（翻案条件随附）**:

- **对话编译进统一 DAG**（单引擎）：否决——DAG 三大编译期保证（报价=fold / 拓扑可排 / roster 投影）对开放轮数、人是环境的对话不成立。**翻案条件**：无（结构性）。
- **保留空文本框作为「高级选项」**：否决——空框 = 创作题，与「每问可一词答」同体两面；修订通道（点值改 / 聊天改）已全覆盖。**翻案条件**：真实用户点名要自由书写区且两通道被证实不够。
- **人形角色叙事**（「剪辑师正在…」）：否决——工艺叙事发稿；人形版 = 翻 N-24，门槛维持。

**Related**: `DIALOG_WORKFLOW.md`（概念母文档）/ ADR-039（Agent 归一）/ ADR-043（任务书契约不变）/ ADR-047（有界环同构）/ ADR-051（提问 dock 形态 = ask 的渲染面）/ NAMING N-24（角色隐喻禁令——判词 7 划定其边界）/ NAMING N-43~N-47（更名判例）/ 证据 = Agent Opus 走查 + 业界框架词汇坐标（Anthropic《Building effective agents》/ LangGraph / AI SDK / Mastra / Agno / OpenAI SDK）

## ADR-053: 提问机器形态律 + 插话支持——文字问对话形态 / 选项问阻塞形态 / 判定结算与提醒尾

**Status**: Decided (2026-09-04；施工简报 `docs/archive/tasks-done/de-dialect-question-machine.md`；规格 = CHAT_ARCH §8.5 + DIALOG_WORKFLOW §6)

**Context**: 提问机器的两处死结：① **文字问（options 空）被迫套选项问的 pill 形态**，明明是普通对话却挂着 dock。② **autoResume 的「任意文本 = freeform 回答」是掩盖映射**——待决中用户说的任何话都被强记为答案，插话（"顺便问下进度"）被误记成回答、问题被吞。「每轮一问、每问可一词答」（ADR-052 判词 5）之下，待决问题存在时用户照常说话是日常形态，系统必须判得清「这是回答 / 这是跳过 / 这是插话」。选项问不是普通对话，是**带快速回复的决断**（FLORA / Opus 双参照：两家选项问待决时输入都让位给问题卡）；文字问保持对话形态。

**Decision**:

1. **形态律（R1）**：渲染按 `options` 是否为空分流，与 kind 无关——**文字问（options 空）= 普通对话消息**（入消息流，永不 dock；输入恒活；待决行住服务端，后续回合带来判定结算或提醒尾）；**选项问（options 非空）= 阻塞形态**——待决时输入行与免责行让位（CSS 隐藏不卸载，编辑器 DOM 草稿保住），dock = 问题本身：问句行 + × + 选项行 + 尾行铅笔自由输入（**与选项行同一 item 解剖**——铅笔坐进字母徽章同款 tile；输入本体底色双主题透明〔Input 基底自带 `bg-input/20` + `dark:bg-input/30`，嵌套行内必须显式扑灭——变体配对律同坑〕；Enter 走与主输入同一条 sendChat 通道；FLORA / Opus "Something else…" 同款）。**default_path 不再直渲为 dock 行**（两家参照均无此行，正常对话即可——跳过语义由 × 承担，提醒尾照旧消费 default_path 原文，机制不动）。morph 跟随**渲染中的 pill** 而非原始待决态——确认期选项 pill 不渲染（task_book dock 占场），输入保持恒活，防「待决隐形 + 输入让位」死局。task_book pill 不阻塞不在此列（「不开始」用沉默表达，ADR-051 条款 8 Ⓑ 不动）。**已答问题入档块（AnsweredQuestion）只对选项问与 task_book 回执**；文字问的回执 = 普通消息对（问答各自本就是一条消息）。
2. **× = 阻塞形态的 bail 出口**——取问题的 default_path；interrupt 的 × 停掉在跑的付费 run。文字问没有 ×（它不 dock）——它的跳过 = 判定 skip（下条）。
3. **插话支持（R2）——判定是 LLM 的、结算是代码的**：待决问题显式进两相位上下文（book path 的 pending 块 / chat path 的 `_build_context` 既有通道）。book path 的回答信号 = **slot 握手**（router 把待决槽位的用户原话提案为 user-stated → 代码结算 freeform 并回填账本，无需新 schema）；chat path 的回答信号 = 信封 **`pending_disposition` 三态**（`answer` → 代码结算 freeform——interrupt 的判定回答唤醒 run + 确定性回执，提案不再叠加派发（唤醒即续跑）；`skip` → 结算 bail——文字问唯一的 ×；`none` = 插话 → 问题保持待决）——三态住信封，不是第五提案态。task_book 待决不参与任何判定结算（它的回答是 dock Start / book path 回合）。选项问阻塞形态下主输入让位，用户文本经铅笔行入**同一 sendChat 通道**——autoResume 选项命中 / slot 握手 / `pending_disposition` 结算语义不变。
4. **提醒尾**：插话回合的回复末尾接**代码拼装的双语固定句式**（原问题 + default_path；`_prefers_zh` 按回合语言）——代码强制文本，永不借 LLM 之声（draft-from-persona 声明同教义）。
5. **autoResume = 唯选项命中**：确定性结算只有字母 / 序号 / 原文命中（零 LLM），其余一律走判定。五处提问源（router ask / chat shape C / caption-mode 问 / 方向 interrupt / 零根主题文字问）同一结算语义。

**Consequences**:

- 文字问待决不改变任何 chrome 的可见性——dock 三可见性态（坍缩 / 展开 / 隐藏，ADR-051 条款 7）与文字问正交；选项问待决 = 阻塞 morph（输入行 / 免责行让位），其余 chrome 不动——待决提问唤回隐藏 dock 的触发不变。
- 判定结算行全部走既有 `ChatResponse.answered_question` 通道，前端零新管线；freeform 判定答案 = 用户原话全文。
- `allow_freeform` schema 字段保留为「本题欢迎自由文本」的元数据（prompt 层对齐用），不再驱动任何强制映射。
- interrupt 三应答不变（选项 / freeform / 默认过期），插话期间 run 保持 parked；`expire_stale_interrupts` TTL 语义不动；interrupt 问的 pill 承载 run 自己的提问（非 interrupt 选项问 morph 走输入行）。

**Alternatives（翻案条件随附）**:

- **插话由代码关键词表判定**（"顺便" / "另外"等）：否决——关键词表是新的启发式方言；判定本就是 LLM 的活，代码只做结算。**翻案条件**：无。
- **`pending_disposition` 做成第五提案态**：否决——判定对象是「这条消息与待决的关系」，与「这条消息要什么动作」正交；并入提案会污染四态判别式的每个分支。**翻案条件**：出现必须与提案联合判定的真实案例。

**Related**: ADR-052（判词 5 提问策略——本条为其落地形态）/ ADR-051（条款 3 形态律以本条为准）/ ADR-041（dock 三可见性态不受提问影响）/ CHAT_ARCH §8.5（规格落点）/ DIALOG_WORKFLOW §6（不变量登记）/ NAMING N-49（提问机器词汇批）/ 简报 `docs/archive/tasks-done/de-dialect-question-machine.md`

---

## ADR-054: 任务书密度律——评审卡 + 确认 pill 归 ≥2 任务，单任务书 = 纯散文确认

**Status**: Decided (2026-09-04；规格落点 = CHAT_ARCH §8.5 task_book 形态条)

**Context**: 一次产品试用（裸愿望 → 主题问 → 作答 → 出书）：单任务书（[write_post]，参数全默认）以完整评审解剖出现——槽位行 / 任务行 / 语言下拉 / Add task / 确认 pill / Start 钮，而卡上每一件内容散文 echo 都已复述，唯一可玩的决策是一个语言下拉。决策实则只剩「开始」一个手势，却套着与五条链媒体流水线相同的全场最重形态——重量与决策错配（形态律 ADR-053 是同一原则在提问上的先例：形态跟决策重量走）。讨论中否决了「任务书没有价值」的更大删法：任务书是付费 run 的出生手势 + 修订锚 + 状态重建点 + run 出生证，是合同；卡只是合同在有评审实质时的形态。

**Decision**:

1. **密度律**：任务书的评审卡 + 确认 pill 是**重渲染**，只在 **chain ≥2 个任务**（有评审实质）时出现；**单任务书 = 纯散文**——live 旅程 = echo 气泡即全部渲染，恢复会话 = 钉底 echo 行；确认 = 下一条 chat 消息的 start 裁决（G-1 既有路，S1 剧本已锁），无卡、无 pill、无 Start 钮。任务书行 / 载荷 / 结算 / 单待决全不动——纯渲染阈值（`intent.tasks.length` 派生，零新状态、零新 wire 字段）。
   **echo = 实体流消息**：task_book question 行的 `content` 存 echo 散文原文（无 "Plan ready for confirmation: …" 机器行，任何界面不出现）；live 旅程 = 信封前先推 echo 气泡（流 delta 已携带则去重，planCard 内 echo 引言同内容去重）；恢复会话 = 历史回放 echo 流消息（时间锚 = question 行出生）+ 已答问题归档行（问句文案 = 本地化确认问句，非 content 机器行）。密度阈值 / 确认结算 / 任务书载荷不动。
2. **散文牙齿**：薄书的 echo 第二句 = 全部确认 UI——成功定义 + 以**一句一词可答的确认问句**收尾。**永不指定魔法词**（无「说『开始』我就开工」式咒语）：start 裁决本就认得任何自然肯定（'go ahead' / '好的' / '可以'——router 裁决词表既有），问句只是发出邀请（顾问姿态：每问可一词答）；「plan card / Start generation」类引用只归 ≥2 任务的 echo（那里有真钮可指）。确认问句与成功定义的**措辞归 LLM 自由发挥**——prompt 只约束话的类型、原则与大意（一句一词可答的确认问句 / 成功定义说人话），不给可照抄的原句（可照抄原句会被模型逐字复读成罐头句；"Done = …" 等式腔不是人话、开放尾巴违反每问可一词答自身教义）；恢复座 `planProseSingle` 保留确定性文案（代码钢印的恢复座是另一类——渲染期无 LLM 可调，与代码强制的提醒尾同律）。
3. **三项细分**：单任务 + 用户显式点名参数（"German post"）= 薄（参数是用户刚说的，识别题为零）；单任务贵链（select_clips 烧 ASR+渲染）= 薄（确认手势的重量本就不随成本缩放，见翻案条件①）；reasons 硬 caveat（clips_without_media）不展卡（「做不出 + 替代方案」必须在散文里说清——顾问姿态②的 prompt 职责，不是 chrome 职责）。

**Consequences**:

- 薄书的 Start = 唯一通道（chat 的 start 裁决）；厚书双通道（pill Start / chat 裁决——pill 化为「确认生成」用户消息走同一 sendChat LLM 道，Workspace 合同 C8）不变。
- 薄书无面板手编（无卡）——修订全走 chat 恒胜；面板手改的 `prior_intent` 本就随每个 confirm 相位 send 送出，厚改薄（面板删到 1 任务）编辑不丢。
- 已登记边缘：厚书面板删到 1 任务时卡即时消失、当轮无可见映射（旧 echo 描述旧链）——编辑保留、下轮自愈；真实用户若在此绊倒，remedy = 未保存编辑期间保卡，不回撤密度律。
- 剧本零新断言（密度是渲染层，剧本驱动 wire；S1 核①的 chat-confirm 拍已锁薄书主径）。

**Alternatives considered**:

- **薄书自动 Start**（放宽 G 明确的自动起步闸门）：否决——G 明确自动起步因用户的话已完整指定请求；薄书是推断出来的，为它烧付费 run 却没有用户手势，确认节拍的意义消失。**翻案条件**：无（付费 run 必须有手势）。
- **薄确认改走选项问**（"开始？" + [开始/换语言] pill）：否决——kind 之外加第二个形态判别维度（重量分支）= 结构性方言；task_book 的 Start 必须同一载荷同一手势。**翻案条件**：无（结构性方言）。
- **删除任务书概念本身**：否决——它是付费 run 的确认对象 / 修订锚（presented_book 防重做梦）/ pending_brief 状态重建点 / derived·估价·画布的出生证；删掉会在原地重新发明它。**翻案条件**：无（承重墙）。
- **「薄/厚」立为正式名词**：否决——细则写成结构条件（chain 任务数），不立名词。

**Reversal conditions**: ① N-34 估价 fold 落地时，薄书的成本预览若需要实体表面（"≈N credits"），重裁阈值；② 真实用户数据显示薄书用户对「没有按钮可点」彷徨（不知道能打「开始」），第一旋钮 = 散文措辞，pill 回归是最后手段。

**Related**: ADR-053（形态律——本条为其向任务书密度的顺延）/ ADR-052 B3（预填评审卡 / 散文牙齿原位）/ ADR-043（任务书载荷 = 技能链）/ CHAT_ARCH §8.5（task_book 形态条落点）

---

## ADR-055: 积分系统——credit / wallet / credit_transactions + hold→capture→release + configs 表 + 消耗比例参数 + 负余额允许

**Status**: Decided (2026-09-05；母文档 `docs/BILLING.md`；简报 `docs/tasks/credits-system.md`；支付 / 套餐经济 = W11)

**Context**: 积分系统的模型层。地基：`workflow_steps.estimate`（报价 = fold，N-34）与 `cost`（计量，ADR-025）两列对称、`minimax.PRICING` 价目唯一事实源、metering 内存台账在 `execute_step` 尾段一次归并（ADR-050）。缺的是用户货币层：余额、扣费时序、失败语义、与支付（W11）的边界。总纲 = **积分系统完全先行；支付只是三方对接 + 钱→积分换算，放 W11**。命名经行业坐标核对（Stripe authorize→capture→release / Modern Treasury ledger transactions / OpenRouter·Replicate·fal.ai 负余额实证）。

**Decision**:

1. **概念三词 + 两层货币**：`credit`（积分 = 用户面唯一计价单位，en credits / zh 积分）/ `wallet`（`wallets` 表 = 余额 + 判定）/ `credit_transactions`（台账，append-only，ledger 是子系统概念名不上表名）。内部 USD 成本层（PRICING）原样保留作对账事实，**USD 永不直接上 UI**。
2. **三表，Owner = 平台层**：`wallets`（user_id PK / balance / version 乐观锁）、`credit_transactions`（kind ∈ grant/purchase/hold/capture/release/refund/adjust；amount 有符号；`balance_after` 自校验链；`idempotency_key` UNIQUE 一等列——重试 / 重启 / webhook 重放天然去重）、`configs`（公共运营参数表，见 ④）。不往 `users` 加列，首登 lazy 开户 + grant。
3. **扣费时序 = hold → capture → release**：`create_run` 折完报价按 **high 端** hold（不足 → 422 `credits.insufficient` + 入流灰行，用户级与 provider 级 402 严格两词）；step 终态在 metering 归并同点按 actual `capture`——**成功收全量（含内部重试），failed/skipped 不写行 = 失败不扣费**；run 终态 `release` 剩余。NULL 估价步骤 hold 按 0、结算照扣。
4. **configs 表 + 单一消耗比例参数**：`CONFIG_REGISTRY`（key → default/类型/desc）是唯一事实源，表只存覆盖值，启动 reconcile 补插（seed_default_music 同款）；读取一个漏斗 `get_config()`，未知 key 报错。两分界：运营参数 → config 表；工程参数 → env `config.py` 不动。首批住户 `wallet.signup_grant` / `credits.per_cost_usd`——**消耗比例**（成本→积分，报价与实扣同源单点，调参不发版）；**购买比例**（钱→积分）是 W11 套餐定价的另一个决策，解耦。调参不动历史账（积分额落库即事实、USD 两侧各自为真）。
5. **负余额允许**：NULL 估价步骤结算可击穿余额——如实显示负数，负额用户过不了下一次 hold。业界实证 = OpenRouter 余额可为负后硬停新请求（连免费档）、Replicate/fal 在途任务跑完照扣——gate at the start, never mid-flight 是行业共识；中途拦停催款（AWS 惊喜账单象限）无人采用。后手留档不实装（负额告警 / NULL 步骤保守上限 / 超预估 N 倍降 checkpoint）。
6. **payment 边界（W11）**：适配器收 webhook 确认 → 购买比例换算 → 写 `kind=purchase, idempotency_key=provider_event_id`；订阅周期额度 = `kind=grant`。**台账永远不认识"钱"**——汇率换算全部发生在适配器边界，积分层结构对支付零预留（kind/ref 已留座位）。
7. **模块家**：`platform/configs.py` + `platform/billing.py`（服务动词：get_or_create_wallet / credits_for_cost / check_hold / hold_run / capture_step / release_run / balance）+ `platform/routes.py` 挂 `/wallet`（W11 `platform/payments.py`）。orchestrator 三缝合点（create_run / execute_step 尾段 / maybe_finalize_run）调平台服务 = Distribution `_transition` 调 `create_notification` 同款缝。credits 展示全部序列化层派生（fold × 比例），不落列。

**Consequences**:

- 配方卡估价贴 / dock 总价 / chat 单价三面同源（同一个 fold、同一份 PRICING、同一个比例），结构性不可能不一致。
- 失败不扣费 = step 终态语义：failed/skipped 零 capture；provider 侧成本照记 `cost` 列供对账，不上用户账单。
- 积分在 W7 结束即为真账本——支付接入前没有花钱入口，赠额消耗即真实计费演习。
- 每 run = 1 hold + N capture + 1 release；台账 append-only，幂等键使 worker 重启 / step 重试 / webhook 重放安全。

**Alternatives（翻案条件随附）**:

- **事后按 actual 扣（不 hold）**：否决——并发 run 可透支且超支不可见；hold 的 high 端是 estimate fold 免费给的。**翻案条件**：无。
- **clamp 余额于 0**：否决——账说谎比账难看可怕，失血点永久隐形。**翻案条件**：无。
- **中途拦停催款（checkpoint 要求充值后续跑）**：否决——半成品 UX，且击穿源是我们的报价缺口不是用户过错。**翻案条件**：W12 数据证明击穿频繁且额度大，此时先上 NULL 步骤保守上限，仍不够再议。
- **kind 用 settle**：改 `capture`——预扣转实扣的行业唯一通词（Stripe/Adyen/Braintree 同构）；settle 是银行间清算语境；claim 是用户发起的收款动作，方向相反。
- **表名 ledger / transactions**：定 `credit_transactions`——ledger 保留为子系统概念名，行 = transaction（Modern Treasury / Stripe balance_transactions 同词）；裸 `transactions` 撞 DB 事务语境，带 credit_ 限定。
- **双桶余额（订阅周期额度 vs 充值包）现在建**：推迟——套餐语义 W11 定；如需分桶，ledger 加列而非改语义。

**Related**: ADR-025（计量单边界）/ ADR-050（会话纪律——capture 与 metering 同写入点）/ ADR-039（报价 = fold）/ ADR-052（W7 排期语境）/ `docs/BILLING.md`（母文档）/ NAMING N-51（积分词汇批）

## ADR-056: 桌面项目页右侧面板化（FLORA 收编）+ 积分 pill + 过渡 fade 简化

**Status**: Decided（2026-09-06）

**Context**: 两个痛点。① 首个 run 到达的 morph（ADR-051 条款 7）若用 grid-rows 1fr→0fr 收拢，读作「整个聊天框直接飞上去」——过度工程；简单 fade out + 一点 delay 后 canvas fade in 即可。② 底部 dock 四不像——只抄了 FLORA 的「缩到右下角圆点」没抄它的右侧面板主体。FLORA 左下角的用量 pill 顺势收编。形态：首个 run 前全屏 chat 仍是主角，首个 run 后 chat 进右侧面板。面板常态 = **浮层 popover 效果**（不是与画布左右分栏），点 Dock panel 后**靠右 fixed**，但**仍然是雾面玻璃**——FLORA 的 docked 态画布依旧在面板雾面之下；in-flow 分栏让画布在面板边缘截断、磨砂后面无物可糊 = 平面实色。

**Decision**:

1. **过渡 fade**：舞台 morph = 原地 opacity 淡出 300ms（无 grid-rows 收拢；wrapper 恒 flex-1、隐形+点击穿透，输入组零位移铁律）+ 画布/移动列表 `duration-500 delay-150` 淡入。chrome crossfade 500ms。
2. **三形态机 + 面板双几何**：`form = "full" | "panel" | "dock"`——pre-first-run = full（全屏 chat）；post-first-run 桌面 = **panel = full-bleed 画布上的雾面 overlay**，两种停泊几何经 header 钮切换（FLORA "Dock panel" 对齐，localStorage `repurposer-panel-mode` 持久）：**float（默认）**= 右锚浮窗（垂直 ~18%/10% 内凹、底偏重——FLORA 浮窗不是全高 sheet，rounded-2xl）；**docked** = 靠右齐边全高（rounded-none）——两态同一 dock-surface 磨砂，300ms inset/半径过渡 morph；**宽度 480px 定宽**（FLORA 右侧面板 fixed 480px 列；发丝线语法对齐 FLORA `border-width: 0 0 0 1px`：docked = 仅左边单线〔齐边三缘不向视口画 ring〕，float 窗口 = 全周发丝线）；移动端 = dock（stadium / 三可见性态 / 拆粘三寄存 / 输入框独立层律 = 移动端 dock 法则）。解剖 = 细长 header（标题 + 几何切换钮 + minimize − 钮）/ chatScroller 主体 / 底寄存（提问·任务书 pill → 免责行〔钉输入组上方〕→ 输入组恒 rounded-xl；无折叠 run 状态行——panel 滚动区常驻消息流，折叠行是纯重复，ADR-051 §2）。panel 两可见性态 = open / minimized（minimize → 右下角 LogoMark 点；唤回触发器与 dock 同一套：agent 发声 / 待决提问 / 确认就绪 / mention 插入召回——复用 `dockHidden` 零新状态；**float 态该点常驻 = 切换钮**（开 → 点收起、收 → 点展开；docked 全高态右下角归 send 钮，点仍只在 minimized 出现，docked-open 收起走 header −）；页面经 `onPanelStateChange`（hidden + 几何）感知，**仅 docked 态**把画布 zoom pill 右移 `md:!mr-[504px]` 让位（480 宽 + 24 呼吸）——float 自 18% 起不触顶角，统一偏移会在浮窗上方留出死区）；面板入场动画只在 full→panel morph 播（stageMounted 闩锁门控，水合首帧永不重播）。**保草稿承重结构**：单一 root（三形态同一 fixed overlay 层，panel 经 `hidden` 隐藏）+ 恒渲染 card 容器（full/dock = `contents` 布局透明，panel = 浮卡）+ 底排恒定子索引——MentionEditor 跨 full→panel 翻转与 float↔docked 切换永不 remount，DOM 拥有草稿 + chips 零丢失（序列化携带必然有损，禁）；scroller 单挂载律 = stage/history/panel 三槽互斥门控（`historySlotOpen` 改键 `dock &&`）。
3. **积分 pill（BILLING §7 第四读面）**：项目页左下角 `CreditsPill`（post-first-run 桌面）——Coins + 余额 tabular-nums，点击 Popover：余额 + held（预占中）+ 最近台账 10 条 + 负余额注记（`credits.negativeNote` 复用）。数据 = `/wallet` + `/wallet/transactions` 现成端点（后端零改动），手卷 apiFetch 静默失败保 "—"（防双报纪律同账户控制台）；刷新 = 挂载 + run 态翻转（refreshKey = latestRun id+status）+ 每次弹窗打开。无百分比无 Upgrade CTA（无套餐无购买入口，W11 座位）。
4. **维持否决**：Queue 条（违反唯一进度面）、多 chat（ADR-041 D8）、窗口管理控件（面板禁拖动/缩放/多窗——float 是固定停泊几何不是窗口）、左侧工具栏（我们的画布只读，无节点创建工具，编辑只经 chat）。

**Consequences**:

- ADR-051 条款 7/8 的现行法 = 本条（三形态机）；拆粘 / stadium / 独立层律 = 移动端 dock 法则；免责行钉输入组上方（全形态一致）。
- 消息机器 / 提问机器 / 任务书 / SSE / 占位打勾零变化（本条只动渲染壳）。
- 面板 overlay 化后画布恒 full-bleed：explore 面 resize 不重框视口（FlowView 门控）天然适配；首帧 fit 不考虑面板遮挡（explore 由用户平移接管，FLORA 同）。
- 规格落点：CLAUDE.md（rounded-full 例外 / 输入框独立层律 / dock 三态 mobile-only / composer 契约面板段）、CHAT_ARCHITECTURE（关键形态事实三形态机）、BILLING §7（pill 读面）。

**Alternatives（翻案条件随附）**:

- **面板 = in-flow 左右分栏（页面 flex-row 让位，画布在面板边缘截断）**：否决——磨砂后面无画布可糊 = 平面实色，违背 FLORA docked 实测形态（雾面玻璃下画布延续）。**翻案条件**：雾面下画布的渲染性能或可读性出现反证。
- **桌面单形态（fullscreen chat 舞台不存在，pre-run 即画布+面板）**：否决——首个 run 前对话仍是主角；空画布迎客无信息增量。**翻案条件**：真实用户反馈 pre-run 全屏 chat 与面板重复。
- **Queue pill（FLORA 右下）**：否决——违反唯一进度面（打勾流）。

**Related**: ADR-051（条款 7/8 以本条为准）/ ADR-053（提问形态律——面板内形态不变）/ ADR-054（密度律不变）/ ADR-055（积分 pill = 其展示面扩展）/ `docs/BILLING.md` §7 / 证据 = FLORA 项目页 + 「Dock panel」切换截图对照 + `docs/research/flora.md`（面板形态）

## ADR-057: 图即产品对象——持久可变图扶正、wiring 层收编、节点五型与端口法则、prompt 直改+确认、投影层火化

**Status**: Decided (2026-09-07)

**Context**: 积分展示面讨论（「积分该在哪展示、在哪消耗」）牵出真伤口——没有一个确定的 node 交互方式，就无从做好积分系统；而修订环在产线带伤（实证：修订 run「Target clip not found / Run failed」）。三平台（ElevenLabs / Flora / MiniMax）对照核对出一个共享图内核：**node = 纯函数**（上下文从连线进 → 程序 → 执行 → 出），每个 node 自身是一条内部 workflow，整个画布是一条 workflow；prompt = 程序在卡面；**DAG 先展示后运行**（草稿态：图完整可见、节点上无产物、运行才消耗）；**chat 布线三家全支持**——手动布线能力必须完善才能表达 chat 布线，只是 UI 不开放手动。我方偏差随之显形：① 图 = 每次 run 编译即弃的产物，不是产品对象；② 画布靠五补丁投影（`canvas_hidden` / `canvas_key` / 过程脊 spine / 脊收编 / R1 下游游走）把过程藏起来——默认反了，真图拿不出手才需要投影；③ 中间产物（转写稿/任务书/research brief）非一等公民；④ 无 wiring/变更层，修订 = 投影模型上的补丁语义，不是图上的操作；⑤ 任务书是独立文档层。消耗粒度核对：ElevenLabs = 节点级（per-node run+charge），Flora = 生成级（chat 免费），我们 = run 级（任务书确认一次 hold、step 级 capture，ADR-055）——粒度差解释了大半竞品 UI 差异；run 级符合 delegator 定位，**不动**。原则：「他们从头到尾没有什么中间 node，只有 generator node 或者 agent node 和连线」「手动布线功能必须完善，才能表达好 chat 布线，只是 ui 不开放手动罢了」「修订的时候，其实从用户看到产物有意见想修改开始，就和正常的平台操作没有任何区别」。

**Decision**:

1. **图升正为持久可变产品对象**。项目 = 一张持久图（`graph_nodes` / `graph_edges` 两表，project 作用域，owner = Pipeline，MODULE_ARCH §4 登记）。工作流 = **chat 建/改持久草稿图 → 确认 → run 填充节点 → 修订原地 mutate**。**执行内核不动**：compile DAG / NodeBase 四算子（报价=fold / 执行=topo / 校验=∀ / 对账=⊆）/ Postgres 队列 / hold→capture→release 计费全部保留——`workflow_steps` 保持 step 粒度（billing capture / 计量 / 重试靠它），steps 住进节点**内部**作为节点的内部 workflow（组合，不是投影）。
2. **wiring 层 = 图变更 API**：`add_node` / `connect` / `edit_prompt` / `delete_node` / `run(_subgraph)`。chat 是唯一意图消费面；手动布线能力必须完善（chat 布线的表达力以它为底），**UI 永不开放手动**——能力完备、手势缺席（ADR-035 第 2 条以此为准）。**初始生成 / 修订 / 新建 = 同一组 wiring op**——无「修订环」概念，只有一张被持续编辑的图；孤岛合法（图 = 森林，不是单连通 DAG）。
3. **草稿态**：图先展示后运行——运行前节点完整可见、产物区空态（「运行后生成」+ 逐节点估价），零消耗直到 run。**确认拍 = dock pill 唯一座位**（估价随行，ADR-070）；修订的定价确认锚定受影响子图（§6 / ADR-063）。无 derived preview 投影——草稿图本身就是「你将得到」。
4. **节点词表（现行 = ADR-076 词表 v3）**：`type` = 媒介五值 text/table/image/video/audio；`spec.prototype` = generator/editor/manual（程序区按它门控）；业务身份 = `spec.summary` + `spec.tool`；状态是正交维度（draft / queued / running / done / failed / skipped / stale / versions）。卡面解剖族 = 全文卡 / 表格卡 / 媒体卡。legacy 五值行（asset/document/generator/processor/agent）读面 `_read_face` 一帧映射，永不迁移。
5. **端口法则**：**进 = 消费区域的左下角（一条角律两个区域），出 = 生产区域最右上角**；同侧多口从角起堆叠。**进分位细分**：媒体流（video/audio）的消费区域 = 内容区，锚在**内容区左下角**（PROMPT 分界上 16px，底锚上堆）；文本流（text/ctx）的消费区域 = 提示词区，锚在**提示词区左下**（factsbar 带上）。**圆缘贝塞尔**：连线锚 = 圆缘（cx±r, cy）非圆心——可见 28px 圆即 Handle，xyflow 原生锚 = 把手矩形位方向外缘，贝塞尔水平切线出源右缘、入目标左缘，整条线插在圆边界上（ElevenLabs 解剖）。圆与卡边间隙 6px（约 1/4 直径贴边比例）。连线 = 上下文/数据流（类型化：video / audio / text / ctx 虚线），不是执行顺序装饰。无不可见 Handle。端口形态 = 28px 圆形图标芯片，glyph = 流的类型（video=Clapperboard / audio=AudioLines / text=FileText；ctx 引用流无自有 glyph——ctx 入锚并入共享 T，@ 永不上画布，ADR-072）。
6. **prompt 直改 + 确认**：节点卡上的 prompt 直接编辑 = 一次 wiring op（`edit_prompt`），发送 = 定价确认（估价随行）→ 只重跑该节点与其下游。通道：直改是确定性手势不是意图——ops 代码构建，走 `POST /projects/{id}/graph/revise`，dock 零消息、节点状态周期 = 全部反馈；chat 唯一**意图**面不变（ADR-058）。节点面永无模型选择器 / SKU 货架（ADR-051 条款 5 不变）；runtime 事实（模型/参数/耗时）住卡外 factsbar，不住节点卡内。
7. **零投影**：无 `canvas_hidden` / `canvas_key` / 过程脊 spine / 脊收编 / 下游游走（`resolveAssetFeedTargets`）补丁族——**显示模型 = 领域模型**。步骤永不上图（step 住节点内部，画布从图直读，无从投影）；过程动词永不上图；打勾流仍是唯一步骤叙事进度面（dock 内）。
8. **语义账本塌缩**：hold / release 永不上 UI；台账用户面只显**花费 / 赠送 / 充值**三族，行 = per-run-event 语义行（「Post 修订 −3」）；CreditsPill popover 无裸 kind 列表。逐节点估价 = 卡面空态位；确认合计 = 受影响子图 fold（同一个 fold、同一份 PRICING、同一个比例——三面同源纪律不变，BILLING §7）。
9. **agent 言语律**：agent 的话必须是**世界状态的函数，不是剧本的函数**——禁 manual-speak（「点它卡上的 prompt 直接改」式 UI 教学永禁）、禁内部词汇（wiring op / spec / 程序 / 任务书等工程词永不出 agent 之口，同事口吻）；动作状态 = **一句话原位变化**（进行态 → 完成态同一行 morph，不叠行——由 RunTaskList 单行动态行承载，CHAT_ARCH §8.7）。
10. **存活不动**：chat 唯一意图面 / 确认先于花费 + hold→capture→release / NodeBase 四算子 / clip-spec 唯一渲染契约（ADR-016）/ 参数吸收与虚构 SKU 禁令 / delegator 定位 / mentions 双端注册表（@ = 参数绑定的文本视图，连线 = 空间视图——同一引用的两视图）。

**Consequences**:

- 数据：`graph_nodes` / `graph_edges` 两表（MODULE_ARCH §4 登记，owner = Pipeline）；run 获得图语义（**run = 对（子）图的一次填充**）；产物与节点的血缘经 node id 汇聚（`outputs.workflow_step_id` 血统保留在节点内部，不消失）。
- 前端：无 `runFlow.ts` 投影适配器——画布数据源 = `GET /projects/{id}/graph` 直读；FlowNodeCard 解剖（caption 右槽恒空——状态原地表达不打角标 / 卡面 prompt 区 / 端口法则落 Handle 位 / factsbar 外置 runtime+actions）。
- 消耗展示三面同源扩展为四面：dock 总价 / chat 单价 / 配方卡估价贴 + **节点卡空态估价**；确认卡节点锚定。
- 修订 = 图变更——「Target clip not found」类结构性不可能；排期见 PROGRESS。
- **定居取景机制**：布局一开始就定好——帧在门内一次性出生：add_node 可钉 `id`（stamper 专座），同批 connect 直接引用新生儿，门内定居 = parents-first 按最终边集一次赋值；禁「先乱长、二次重构」的两批次修复形态。既有帧永不动（append-only 保序律不变）。
- 简报 `docs/archive/tasks-done/graph-as-product.md`。

**Related**: ADR-035（可操作画布：能力完备、手势缺席）、ADR-036 / ADR-041 / ADR-051（以本条现行法为准）、ADR-043、ADR-052（有界 loop 不变）、ADR-055（计费内核不动）、ADR-039（四算子与四层地图不动）、ADR-016（clip-spec 唯一渲染契约不动）、ADR-040（配方 = 提示词不变——配方卡预填模板 = 草稿图的一种出生方式）、ADR-070（确认拍 dock pill 唯一座位）、ADR-072（任务书节点下线）、ADR-076（词表 v3）

## ADR-058: 展示文案二源律 + 卡面直改 = 确定性图动作零消息 + focus 退役归 @mention + 整回合状态行

**Status**: Decided (2026-09-09)

**Context**: 一次真实用户走查（四截图实证）把同族伤口一次点亮：用户在 Post 卡面把 prompt 改成 "Write post, in Chinese" 点发送——① 卡面回闪旧程序 "Write post, in EN"（直改骑 chat 通道，无乐观回显）；② 回声 "Drafting a Chinese LinkedIn post..." 之后进入死窗——thinking 行只活到首个 delta，结构化尾巴（提案 JSON → dispatch → run 出生）没有任何状态主，用户以为「回复完了」；③ 任务列表突然出现，收据标题却是 "Post (English)"——读的是 dock 陈旧 intent state 而非 run 真值（投影漂移：系统手里有对的话——run 步骤说 "Post · ZH"、提案 summary 说 Chinese——然后把它扔了）；④ 终态消息排序错乱（runStreamUnits 假设回声先于 run 出生——book 路径成立，chat dispatch 回合是先建 run 后落回声，created_at 倒挂，回声掉到收据下面）；⑤ 收官句 "Your Post (English) is ready" 同款漂移。根因归纳两条：**可以让 LLM 命名的展示文案被写死**（"Post (English)" = 冻参模板在说话——参数一说话就有「参数与文案对账」问题，thinking 行同病）；**卡面直改是确定性手势却绕道 LLM 意图通道**（既丢用户字面程序，又制造回声/收据/完成行三份多余言语）。用户判词：「是在打补丁，我们似乎把一些可以让 llm 生成的文案，写得太死了」「节点级 run，dock 应该不产生任何消息——loading 加载也有，prompt 也变了，产物也变了，谁看不出来？」「删除 working focus，只走 prompt mention」。

**Decision**:

1. **展示文案二源律（参数文案解绑）**：一切用户可见的命名类文案只有两个合法来源——① **LLM 建图时命名**：提案携带 `name`（2-6 词名词短语、界面语言、命名作品不命名工具——TaskListProposal / WiringProposal / InferredIntent 三家同字段，null/空 = 未命名，读容忍同打字机律牙①）；② **世界自证**：产物徽标、节点状态、真实数字（facts 量化摘要与默认值保持确定性，不动）。**冻参模板永禁**（"Post (English)" 式参数拼接标签）——参数降级为不可见执行事实，永不说话；参数一不说话，「文字核对」问题类整体消失，无需任何对账机制。
2. **收据 / 收官句读 run 真值，不读 dock state**：回执标题 = 生产该 run 的提案的 name——chat 回合在信封时刻从回声行的 `intent` 列盖章（`runTitleOverride`，回声行服务端恒带生产它的提案）；刷新路径从 `run.context.name` 重建（TaskSpec.name → context 模型导出）；无 name 的旧 run 回退链推导标签（读容忍，不 retroactive 命名）。
3. **卡面 prompt 直改 = 确定性图动作，dock 零消息**（就地修订 ADR-057 §6 通道律）：直改不是意图、是手势——ops 由**代码构建**（`edit_prompt` + `run`），走新端点 `POST /projects/{id}/graph/revise`（202；经 `apply_wiring_ops` 唯一写门、`create_run` 唯一出生口不变），**不骑 POST /chat**。dock 零消息：无回声、无收据、无完成行——节点自身状态周期就是全部反馈（loading 在、prompt 变了、产物变了）。卡面**乐观回显**（`pendingProgram`：编辑确认后卡面恒显用户字面程序，stamp 对齐即收，永不回闪）；定价确认（锚定受影响子图 + 估价随行，ADR-057 §6 前半）不动。run 盖章 `context.origin = "node_revise"`（页面据此不把它当上流焦点 run）。chat 唯一**意图**面不变——意图识别的唯一入口仍是 POST /chat；确定性手势不经过意图层。
4. **focus 归 @mention**：指认产物 = @output mention chip（确定性解算通道，MENTIONS 注册表）；无焦点机制——无 `ChatRequest.focus_output` 字段、无 contexts 焦点注入块、无 intent prompt 焦点规则，outputs regenerate 骑 mention，画布点卡 = 纯选择 + 详情（「在对话中指认」动作 = 插 mention chip）。`messages.focus_output` 列与 `FocusRef` 保留**读容忍**（旧行历史回放照渲染灰行前缀），永不新写。
5. **整回合状态行 + 相位接入**：状态行渲染于「回合忙 **且** 无散文在可视流动」的一切窗口——发送 → 首个 delta、回声排干后 → 信封（结构化尾巴 → dispatch → run 出生）；**打字机说话途中它隐藏**（散文在动 = 活在干活的证据已经在，一段话说完、下个动作 pending 时才需要它）。驱动 = 打字机的忙/闲边沿（`createTypewriter` 第二参，闲态带宽限防抖——模型吐字的天然阵发间隔不闪行）；无 `previewSeen` 门。服务端相位帧接入 chat 路径（`_create_run_from_tasks` 带 `on_phase`）。**打字机律最后闸门**：零 delta 开局（funnel 修复轮）的 start 路径回声照样走打字机节拍排干才落 run，禁整段瞬移（闸门覆盖 dock / start / prose 全三分支）。**状态行一座两行**：消息流里一切「现在在干什么」的瞬态行 = 同一个 `StatusLine` 组件（dock thinking 座 + RunTaskList 动态行座），label 恒为当下相位/叙事，永不只是 "Thinking" 一个冻词。**相位完整律**：相位 = thinking → drafting → creating_run 三拍；`drafting` 由**计划数组流拍**驱动——`_make_plan_beat()` 监听判决流原文，裸引号键 `"tasks"`/`"ops"` 一旦出现即发一拍（裸引号键只能是 JSON 语法——字符串值内的引号必转义，子串扫描零误报；滚动 16 字符尾窗覆盖跨片拆分）。零散文回合（start 判决、散文殿后键序、修复轮）的唯一中途拍就是它；无 `understanding` 相位，base "Thinking…" 是 LLM 黑盒期的诚实占位。
6. **排序锚修订**：终态收据锚定 = `max(run 出生时刻, 生产回声时刻) + 1`——book 路径回声先于 run（旧锚不变、向后兼容），chat dispatch 回合 run 先于回声（收据落回声之下）；回声行在信封时刻盖章 runId 作锚。

**Consequences**:

- schemas：三家提案增 `name`；`ChatRequest.focus_output` 删除；新增 `GraphReviseRequest/Response`。
- prompts：chat_intent 形态 A/E 与 intent_router 增 `name` 字段规则；焦点目标规则删除。
- 新端点 `POST /projects/{id}/graph/revise`；outputs regenerate 的 ChatRequest 构造改 mentions。
- 前端：ChatDock `runTitle = runTitleOverride ?? planSummary`（planSummary = `intent.name || 链推导`）；thinking 行整回合 + previewSeen 删除；focus props / sendRevision / focus 载荷全删（FocusRow 留作旧行回放）；ResultsCanvas `onNodeRevise` + `pendingProgram` 乐观回显 + stamp 对齐自清；项目页 `handleGraphRevise`（credits 422 typed toast）。
- 挂账（简报登记）：步骤级 LLM 命名（per-task name——「tasks 的步骤也是 LLM 命名」的全量形态）；stub 塌缩（"No source material" 行）；mobile OutputChatCard 核对。
- 打勾流步骤标签（`taskLabel` 链推导）= name 缺席时的回退，name 优先。

**Related**: ADR-057（图内核 / 写门 / 出生口不变）、ADR-041（dock 体系其余不动）、ADR-051（条款 5 模型事实陈列禁令不动——本条解绑的是冻参模板，不是事实陈列）、ADR-052（双引擎分离不变——确定性手势不进对话引擎）、打字机律三牙（CLAUDE.md composer 契约段）、CHAT_ARCH §5/§8.6/§8.7

## ADR-059: 图持久化分裂 flush 律——SQLAlchemy 无 relationship 不排序裸 FK 混插

**Status**: Decided (2026-09-10)

**Context**: 剧本 S3 复跑逮到 `turn.failed` 500——`graph_edges_to_node_fkey` 违反，`stamp_transcript_node` 落图时边先于父节点插入。四层取证（真 API 复现 / 进程内复现 / 最小复现 + session spy / 真空对照）坐实根因：**SQLAlchemy 2.0.51 的 UOW 只通过 `relationship()` 排序跨表插入，裸 ForeignKey 列不参与排序**——两表新行在同一 flush 混插时，子行可能先于父行（真空测试实证）。graph_nodes / graph_edges 之间恰无 relationship 挂接，K1 出生的单 flush persist 从此潜伏 4 天，撞上混插顺序才爆。

**Decision**:
1. **写口分阶段 flush**：`graph_store.persist`（图唯一写口）分两段 flush——nodes strictly 先于 edges，代码带「永不合并回去」注释。不是"这次顺序碰巧对"，是把排序从 ORM 骰子收归写口纪律。
2. **律**：同 session 内跨表**新行**若无 relationship 挂接，写口必须分阶段 flush；禁赌 UOW 的排序行为——它只对 relationship 负责，不对 FK 列负责。

**Consequences**: probe4（session spy）复证正确 `[GraphNode]→[GraphEdge]` flush 序列；S3 复跑全绿。此律适用于一切未来多表同事务写口（新模块登记时自查）。

## ADR-060: echo 防编造律 + post 渠道中立——agent 永不发明用户没说过的平台

**Status**: Decided (2026-09-10)

**Context**: 用户走查逮到回声 "…a LinkedIn post on…"——该用户全程没提过任何平台。LinkedIn 固化点散在六处模型可见/用户可见座位：`write_post`/`write_carousel` 工具描述、step 完成摘要、book_summary 类型标签（"LinkedIn post"）、router prompt 例句、命名示例、writer 人设模板（post.j2/carousel.j2/agents.py）——LLM 从工具描述与例句学到 "post = LinkedIn" 再回述给用户，用户摸不着头脑。用户判词：「我们现在是一个世界级 agent，并且 post 不再内部限定为 linkedin」。

**Decision**:
1. **echo 防编造律入 prompt**：回声解剖增一条——只回述用户说过的（作品 / 语言 / 数量），**永不发明平台或场所**（"LinkedIn" / "X" / "newsletter"）；a post is just a post until the user names where it lives。
2. **固化点全量渠道中立化**：工具描述（"long-form social post"）、step 摘要（"Wrote a post"）、类型标签（"post"/"帖子"）、例句与命名示例、writer 人设（"social post for professional audiences"）全部去 LinkedIn。
3. **保留位**：`linkedin-longform` 技能包内部名（包体本身渠道中立，仅 body 经 contexts 进 prompt）；发布婉拒示例（用户真问「发到 LinkedIn」时的应答教学）；landing 营销文案（营销面按设计讲渠道）。渠道的合法来源 = 用户点名 / 渠道授权（发布层，POSITIONING 落地时），永不是默认值。

**Consequences**: 实测复现位（"I want a social post." 模糊两轮）全链 `LinkedIn present: False`——echo / 提问 / follow-up echo / intent name 干净。「参数/默认永不说用户没说的话」与 ADR-058 二源律同族：默认值是执行事实，不是叙事。

## ADR-061: 变体并行律——修饰节点是变体不是工序，caption 扇出恒并行

**Status**: Decided (2026-09-10)

**Context**: 用户走查 caption 项目抓到线性图：素材 → translate EN → translate ZH → translate FR → dub 一条链（截图实证 DB 里 translate→translate 边与正确的 materialize 扇出共存）。根因在 orchestrator 编译期的 `prev_modifier_idx`「永不并行」序列化——一切 modifier（translate / dub / remove_filler）被强制挂上一个 modifier 的输出，理由是「modifier 可能改写共享 render_spec，并行有竞争」。但这个理由只对**字幕 mutator**（remove_filler 就地改写共享 render_spec，走 apply_precomputed journal）成立；translate/dub 是**变体**——各自 fork 新产物、不改写任何共享状态，串行化纯属误伤。用户判词：「不是这个流程吧！应该是并行关系而不是前后」。

**Decision**:

1. **变体并行律**：修饰节点分两类——**变体**（translate_clip / dub_clip：消费 `after` 目标，fork 新输出，mutate nothing）与 **mutator**（`_CAPTION_MUTATORS = {"remove_filler"}`：就地改写共享 render_spec，后继节点必须看见它的输出）。编译期依赖 = 变体只挂自己的 `after` 目标 ∪ 既有 mutator（若有），**永不挂兄弟变体**——EN/ZH/FR 三译 + dub 全部并行扇出。
2. **mutator 排序保留**：remove_filler 之后的一切 modifier 追加挂它的输出（共享 render_spec 的写后读序），这是原序列化里唯一真实的需求。
3. **mutator 集合 = 显式注册**：`_CAPTION_MUTATORS` 常量登记，新增 mutator 型 modifier 必须入册（入册 = 声明「我改写共享状态」，编译器据此排序）；未入册的 modifier 默认变体语义（并行）。

**Consequences**: 进程内编译验证：translate×3 + dub 扇出全部 `inputs=[materialize]`；加 remove_filler 后全部 `inputs=[materialize, remove_filler]`。旧草稿的链式边**数据保留**（草稿不可变），Start / 重盖时由边对账律（ADR-062）撤除——本律落地当天的「Start 即自愈」论断在边层被证伪（`have_edge` 只去重新增、run fill 永不删除），对账律是该论断的成立条件。图正确性从「编译器保守」升格为「编译器懂语义」：变体/mutator 之分就是数据流语义。

## ADR-062: 边对账律——盖章拥有其成员间的一切边，编译不再发射的边经 disconnect 撤回

**Status**: Decided (2026-09-10)

**Context**: ADR-061 落地后复核自愈路径，发现边层有一个结构性缺口：`_stamp_graph_core` 的 `have_edge` 只对**新增**去重，「run fill never deletes」律又保一切历史——于是旧编译器（modifier 链式律）落库的链式边在新编译（并行扇出）重盖时**永不撤除**，新旧两套边并存，画布把「执行早已并行」的链显示成线性。节点层有 orphan sweep（草稿重盖撕掉消失槽位的草稿节点），边层没有对应物——「Start 即见并行拓扑」在边层不成立。用户走查实证：部署后画布仍是线性链。

**Decision**:

1. **边对账律**：盖章（draft stamp / run fill 同律）**拥有其成员集合内的一切边**——成员 = 本次编译填充的节点 ∪ 素材节点 ∪ 任务书 / 研究简报文档。现存边中两端都在成员集内、而本次编译不再发射的，一律经写门撤回（retract）。一端在成员集外的边（他 run 历史 / 转写稿文档 / 修订布线）永不属于本次盖章的事务。
2. **`disconnect` 写门手势**：撤回走唯一写口 `apply_wiring_ops` 的新 op（三元组 from/to/type 定位；缺边即 WiringRejected 严格门；同批新生边只从工作集摘除、不下 DELETE——瞬态对象不入库）。它是**编译器内部手势**——prompt 目录永不列它，chat 提案永不发射它。
3. **对账序：disconnect 领先批首**——写门的环检查走工作边集，拓扑翻转（旧 B→A 陈旧、新 A→B 要连）必须在 connect 校验时看到**撤回后**的集合，否则被幻影环误杀。
4. **自愈路径闭环**：旧草稿无需迁移——`scripts/restamp_draft_graph.py <project_id>` 从 `project.pending_brief`（Start 路径同一读出位）重放草稿盖章，对账撤陈旧边、fill key 碰撞复用节点，画布不起 run 即愈合；Start 的 run fill 同律对账。

**Consequences**: 「run fill never deletes」律的语义 = **节点/历史**——成员内的拓扑宣称不属于历史，属于本次编译。自愈无需迁移：重盖即对账。

## ADR-063: 动作住节点内 + 全文卡律 + 估价诚实面——卡面诚实三律

**Status**: Decided (2026-09-10)

**Context**: 一次 caption 画布走查三连拍：① confirm 之类动作不该单独起 UI（draft 确认卡与 promptEdit 定价确认卡是两张 ViewportPortal 浮卡，锚位数学各一份）——节点动作应做在节点内部；② 实现者提议「把 frame 行数律搬一份给 DocumentCard」被当场驳回——「这不是重复造轮子吗？？应该是封装」；③ transcript 卡 `line-clamp-6` 截断带省略号、padding 四边不齐——用户判词：「进了 node 卡面的东西，不要任何摘要和浓缩，必须是原文全文，不需要画蛇添足」。同场挖出的两宗失信：任务书节点对 transform 链是哑巴（`Plan.book_summary` 只认产物型 slot，translate/dub 不盖 slot → 书文本 None → 空卡；Start 时 run fill 的确定性组合还会把草稿散文**抹掉**）；确认卡许诺「≈ 0 credits」（transform 节点编译期报价 NULL——clips 不存在不可报价——报价折叠只加已报价子图，全 NULL 折叠显示 0 = 谎言）。

**Decision**:

1. **动作住节点内（判词①）**：节点动作 = 节点内部解剖，无浮卡形态（无 ViewportPortal 卡与锚位数学）。promptEdit 定价确认住进 ProgramRegion（暂存程序行下就地展开：锚定子图 chips + 估价 + 余额 + Cancel/Confirm）；事实经节点数据通道下达（`promptConfirm` payload），可见性计算留在 ResultsCanvas。draft 确认拍（K5）座位 = dock pill 唯一座位、三形态同座（ADR-070）；任务书节点下线（ADR-072 ⑤）。
2. **全文卡律（判词④）**：卡面内容 = 原文全文，永无摘要/浓缩/省略号。DocumentCard 全文渲染 + **封顶滚动**（卡高封顶 560，超出卡内就地滚动——ADR-067）；**文档框出生即全文需求高、封顶 560**（graph_store `_document_frame` ↔ layout.ts `documentTextHeight` 一条测量律两镜像互引，task_book 加 88 确认预留）；**任务书文本 = 判决自身的计划散文**（`intent.answer`，二源律①——确定性浓缩组合对 transform 链失明且是「画蛇添足」；run-born 书 = 编译组合 ?? run.context.name）。**双面 back-write 律**：draft 模式 dock 拥有草稿书面（修订刷新散文，run-born 书面是历史不动）；run 模式 fill 只填空面（永不改写/抹除草稿散文）。
3. **测量封装（判词②）**：文本测量一条律两个镜像——client `layout.ts`（textLineCount / documentTextHeight）↔ server `graph_store._document_frame`，注释互引，永不出现第三份拷贝；卡内共享 = `EstimatePriceLine` 一个组件服务确认区/定价确认/草稿 chip 三处。
4. **估价诚实面**：折叠中存在未报价节点（estimate NULL）时——全 NULL 折叠显示「估价随运行」（永不许诺 ≈0），部分折叠带开口「+」下界；节点草稿 chip 在 [0,0]（free/未报价）时不出场（免费节点不报价自己的脸）。

**Consequences**: 无 `confirmTitle` i18n 键。transform 链的运行时报价（编译期 floor 估价——按时长×字幕密度启发式）= BILLING 层增强，登记需求池；转写节点 loading 出生（上传即落节点、状态随 ASR）= 同池；mention 扩族（transcript 候选）= 挂账。

**Related**: ADR-057（通道与写门不变）、ADR-058（二源律延伸——书文本取 LLM 散文、run 名兜底）、ADR-062、ADR-067（封顶滚动律）、ADR-070（确认拍座位）、ADR-072（任务书节点下线）

## ADR-064: 顺形律 + 校验分层律——schema 顺着模型的自然写法设计，校验严格度随数据关键度分层

**Status**: Decided (2026-09-11)

**Context**: 生产逮到 caption 配方卡全灭：回声送达后卡在 "Drafting the plan…"，终态 turn.failed「The AI returned an unusable answer」。17 次 LLM 复现取证（`scratch/repro_caption_router.py`）定位到 `brief.constraints` 形状两连击：模型的第一直觉写法是**来源化条目数组** `[{"value":…, "source":…}]`（6/6 spike 全这么写），而 schema 要的是「对象包数组」`BriefSlot[list[str]]`（`{"value": [...], "source":…}`）——strike 1「Input should be an object」；修复轮模型改成对象包一整句字符串——strike 2「Input should be a valid array」→ MiniMaxSchemaError → 回合死。两宗失信叠加：① 失败全有或全无——一条簿记字段的形状错杀掉整个回合（散文已送达、判决本可用）；② 修复窗不可见——thinking 冻结读秒，用户不知道我们在修。

**Decision**:

1. **顺形律**：schema 设计顺着模型的自然 JSON 写法，不再靠读容忍扛错误形状。模型的第一直觉写法就是正典——`Brief.constraints`（当时类名 BriefLedger，命名批 v3 ② 更名）从 `BriefSlot[list[str]]` 改形为 `list[BriefSlot[str]]`（一个约束一个对象）。边界归一化只接存量与明显来路（旧对象包数组逐项展开 / 裸字符串包装 / off-enum 来源降 inferred——永不把来路不明的值升格 user-stated）；不是给畸形形状发签证。
2. **校验分层律**：校验严格度 ∝ 数据关键度。关键载荷（action / tasks / answer / ask / name——驱动付费运行）= 严格 + 修复轮；brief = 咨询性记录——归一化后仍无法解析时**丢字段不杀回合**（`Brief.model_validate` try/except → structlog warning + `brief=None`，回合照活）。
3. **constraints 合并 = 键控并集**（`_constraint_key` 归一化 + `_SOURCE_RANK` 逐项优先级 + 存储序追加），装配面只渲染条目文本。

**Consequences**: 两种曾杀死生产的形状现在直接解析；纯函数套件 test_brief_pure（11 用例：正典形状 / 旧对象包两种 / 裸字符串 / off-enum 降级 / 不可辨认按无意见 / typed 实例放行 / garbled brief 丢字段不杀回合 / 关键载荷仍严格拒收）。前端零改动（Brief 卡面类型本就不含 constraints）。S12 case 5 改为键控并集矩阵。

## ADR-065: 服务感两拍——修复轮相位帧 + 失败行第一人称认领

**Status**: Decided (2026-09-11)

**Context**: ADR-064 取证时的两宗失信里，形状是病根，体感是伤口：修复轮窗口 thinking 冻结（用户盯着 "Drafting the plan…" 读秒，不知道模型第一稿被拒、正在重修）；终态失败行把失败推给第三方「The AI returned an unusable answer」——而说话的就是 assistant 自己。用户判词：「即使我们自己有问题也应该说出来」——【服务感】= 动作有叙述、失败有认领。

**Decision**:

1. **修复轮相位帧**：漏斗新增保留 kwarg `on_repair`（与 `repair_feedback` 同款纪律——`_funnel` 弹出、永不进 assemble；纯函数套件 4 用例：干净通过不触发 / 修复轮恰好触发一次 / 二拒信号后仍传播 / sync 回调兼容）。chat 层把它映射到 SSE 相位管道：`THINKING_PHASE_REPAIRING = "repairing"`，两处 `call_stream` 座（book path / propose path）经 `_repair_phase_callback` 接入；前端 `thinkingPhases.repairing` 双语（en "That answer didn't come out right — reworking it…" / zh「刚才的回答没组织好，我重新整理一下…」）。一次性 JSON 路径无相位管道，kwarg 缺省静默。
2. **失败行第一人称认领**：`USER_ERROR_LINES["ai_unreadable"]` 改写为第一人称认领 + 诚实下一步（en "My answer came back unusable — that's on me, not you. Please try again." / zh「我给出的回答没法用——是我的问题，请再试一次」）。说话者 = assistant，失败归自己，不归 "the AI" 第三方。

**Consequences**: 修复窗从冻结读秒变为有名有姓的相位；两连击终态的措辞与 ADR-064 的结构性修复互为表里（形状顺形后两连击本身应绝迹，措辞是它万一再现时的诚实面）。相位帧纪律不变：bare keepalive 不碰标签、相位只在真实切换点发射。

## ADR-066: provider 方言归 client 层——think 块剥除的位置律

**Status**: Decided (2026-09-11)

**Context**: M3 的 `<think>` 思考块混在 content 通道到达；剥除状态机若住在上层（stream_extract 的 ProseDeltaExtractor / AskObjectWatcher 各一份前奏态），换 provider 就会误处理 think。用户判词：「我们还会支持其他模型的，所以对 <think> 的这种处理应该做在 minimax client 层，而不是上层，这样换 provider 的 llm 就不会误处理 think。」

**Decision**:

1. **方言关在 Model 边界**：`_ThinkStripper` 住进 `providers/llm/minimax.py`（三态 prelude/in_think/payload，tag 跨片安全——尾部 holdback `len(_CLOSE)-1`；有界内存；start-only 规则与 `_clean_json` 对齐），`generate_stream` 每次重试新建实例过滤 `on_delta`。上层（extractor / watchers / plan beat）永远不见方言——stream_extract 的 think 常量和前奏态机全删。
2. **换 provider 的契约**：新 provider client 实现自己的方言归一化（思考块 / 特殊标记），上层契约 = 干净载荷流。

**Consequences**: 纯函数套件 test_think_stripper_pure 9 用例（split_every_way 模糊 / think 内假 JSON / 非 tag 的 `<thinkx` 放行 / 流中段字面 think）。副作用红利：plan beat 不再被 think 块内的 `"tasks"` 误触发，重试护栏收紧（`emitted` 只数干净载荷）。

**Related**: ADR-064（顺形律族——方言归位是顺形律的传输层镜像：形状顺模型的写法，通道顺 provider 的边界）

## ADR-067: 出锚语义律 + 封顶滚动律——源锚说自己的媒介，文档卡有视口纪律

**Status**: Decided (2026-09-11)

**Context**: 真实项目画布走查（340s 视频）三连：① 视频素材节点长出 T 出锚——边类型律把边的两端都染成承载类型，源节点被迫戴上自己不产出的类型；用户判词：一个 node 的出发点讲述「从什么类型到什么类型」，原视频不该有 T 锚点，两条边应从同一点出发。② transcript 文档卡 = 340s 全文 → ~3000px 巨塔。③ task book 卡的 Confirm & run 按钮被散文穿透（「隐隐约约的按钮」）——病根是估算镜像失真（CJK 假设 32 字/行，text-xs 实测 ~19 字/行 → 1.7× 低估）× 正文无溢出治理：真实文本溢出 style 钉死的估算卡高继续下流，穿过 mt-auto 钉在估算卡底的按钮与卡边界。用户处方：document 卡面应有最大高宽，超了 auto-y 滚动。

**Decision**:

1. **出锚语义律**：出锚 = 源节点**自身产出的媒介**（asset 按 asset_type：video→video / audio→audio / image、slides→image（渲染侧第五 glyph，从不过线）/ transcript、file→text；document、agent→text；generator、processor 按 frame_class：clip→video / text→text）——**一节点一出发锚，全部出边同点出发**；入锚 = 边的承载类型（消费方拿什么）。跨媒介边 = 「从 X 到 Y」的转译叙事，转换住在边上，源节点永不长外来 glyph。ctx 无例外——引用流的 Files glyph 只住消费端。染色：入锚 + 描边共享承载类型（线锚同色律守在消费端），出锚染源媒介——video→text 边从紫锚出发走中性线，这个「不一致」正是转译叙事本身。实现 = 纯客户端推导（FlowView `productionPort`，源锚集合 = 节点自身类型单例），服务器零改动；落库的 `from_port`/`to_port` 列无读者，维持旧值不动。
2. **封顶滚动律**：全文卡律不变（永无摘要/浓缩/省略号——反对的是浓缩，不是滚动），但 document 卡高封顶 `DOCUMENT_MAX_H = 560`（= text 帧类预留），超出正文卡内就地滚动（nowheel+nopan+thin-scroll）；task_book 确认拍钉在**滚动区之外**的卡底（flex 列：caption / scrollport flex-1 / confirm shrink-0——散文永远穿不过按钮）。一条测量律两镜像封顶（layout.ts `DOCUMENT_MAX_H` ↔ graph_store `_DOCUMENT_MAX_H`）。画布是文档面，但文档面也有视口纪律。

**Consequences**: 封顶后行估算只决定「是否触顶」，估错无害（卡短一点、多滚一点，永不溢出）——列重叠与文本穿卡结构性消失；legacy 巨帧保留（append-only：旧图多留白，不重叠）。视频节点回到单相机锚；image 锚走中性色（无 `flow-port-image` 规则 = 基座中性，零 CSS 新增）。

**Related**: ADR-057 §5（端口法则）、ADR-063（全文卡律）、ADR-058（二源律——锚语义是节点身份叙事的一部分）

## ADR-068: 画布走查三修——引用 glyph 可读性 + draft 卡无 factsbar + clip 帧 aspect 精确预留

**Status**: Decided (2026-09-11)

**Context**: 同一块草稿画布的三宗走查：① prepare 节点的 ctx 入锚 glyph 读成「图片」——一条 task book 的 T 出锚连线落到 Files（叠文件）图标上，用户问「从 T 过来咋就连接到了一个 image」；② 三个 fork 节点（Dub voice ·EN / Translate captions ·EN / ·FR）列间距巨大——clip 帧类一律预留 9:16 上限 660，而整片 fork 链比例跟源（materialize.py：链无 clip 工具 = 比例跟源，"original"），draft 渲染 278 / done 渲染 316，死空 ~400px/节点且产物落地后依旧；③ draft 卡的 toolbar 只有一个「French」chip、零按钮——caption 已说「Translate captions ·FR」，chip 纯复述。用户判词：无实际按钮的 toolbar 压根不该渲染。

**Decision**:

1. **ctx 引用流无自有 glyph**：引用流入锚并入共享 T——Files glyph 在画布上读作「image」、@ glyph 是外来锚，均否；node 左舷只有 T / image / video 三类 icon，@ 永不上画布（ADR-072 ⑤）。中性色不变。
2. **draft 卡无 factsbar**：未运行节点不再向 factsbar 塞参数 chip（language / aspect 全删）——参数复述 caption 已命名的事实是双重说话，无按钮的条是死 chrome；长度守卫自然不渲染。带宽预留留在高度数学里（几何永不动），产物落地时条随真实事实出生。
3. **clip 帧 aspect 精确预留**：fill 的 `_frame_class_of` 返回 (class, aspect)——链上显式 aspect（select_clips spec）胜出，否则 "original"（整片/transform 链永不重取景）；盖章进 `spec.frame_aspect`（纯帧键——不入 `_params_of` factsbar 白名单，运行时工具不读；`node.spec.aspect` 仍是链自己的生意）。`_frame_of` 按 `_CLIP_FRAME_H`（9:16=660 / 1:1=438 / 16:9、original=316）预留，与 layout.ts `clipNodeHeight` 一条律两镜像互引；未盖章 clip 节点回退类上限 660（wiring 出生的节点安全兜底）。

**Consequences**: fork 列的节点间距 = draft 278 + 预留 316 的精确数学，产物落地后卡高恰好填满预留；legacy 图保留旧帧（append-only——多留白，不重叠）。

**Related**: ADR-057 §5（端口法则）、ADR-067（出锚语义律）、ADR-063 判词②（镜像纪律——_CLIP_FRAME_H 入镜）、ADR-072 ⑤（ctx 入锚并入共享 T）

## ADR-069: 段落级指认 + 失败人话行——卡面划选钉进 dock，失败卡读烤好的人话行

**Status**: Decided (2026-09-11)

**Context**: MiniMax Design 竞品走查：选中识别体验获认可（划选即知你在指哪段），但大屏展开编辑器被用户否决（「我们先不做」）——用户判词：**用户得能在 chat 里通过 mention 指定这一段怎么改，而不是自己手动改，这才是 agent 的意义**。另发现：failed 卡只说泛化的「运行失败」，而 orchestrator 早已把烤好的人话行（`user_error_line`，ADR-065 服务感两拍）写进 step.error——画布卡面读不到它。

**Decision**:

1. **选区引用（段落级指认）**：文本产物卡（post/article）读体恢复可选——读体从 `<button>` 改 `div[role=button]`（button 吞文本选区；键盘 Enter/Space 进编辑的平价路径保留）；划出段落在**区域右下角**浮「引用这段」pill（region 级 absolute 锚定，**永不进 scrollport**——进滚动区会随文滚动并在 overflow 边被裁）。点击 → dock 插入**带 quote 的 @output chip**：`ChatMention` 双端加 `quote` 字段（null = 整体指认，旧行读容忍同打字机律牙①）；chip 序列化 = ``@label "quote"``（散文与历史行都留住指认对象）；编辑器 chip 内联渲染截断 muted 引文（说清指哪段，不只指哪个产物）；dataset round-trip 保回滚重插不丢引文。服务端：mention block 行附 `the user pinned this exact passage`（500 字截断——卡面选区是用户真值，上下文预算不是）；prompt 规则钉死语义：**the passage IS the revision's scope**——新程序修订那一段，永不盲目重写全文。引文出生截断 200 字（一两句的生意——更长是整体 mention 的活）。`insertMention` 召回隐藏 dock（chip = 新信息，召回律）；pill 的 mousedown preventDefault（不得在 click 读选区前塌掉它）。范围：文本产物（post/article）——transcript 文档卡不在此列（其选区 = 未来剪辑 primitive）；手动 in-place 编辑保留为逃生舱，永不是故事主线。
2. **失败人话行**：node 失败态卡读 `spec.error`——`sync_graph_node_for_step` 聚合出 failed 时从 failed family step 把烤好的人话行誊入 `node.spec.error`（bake-at-write、UI locale 于失败时刻，与 step summary 同纪律）；**家族恢复即清**（重跑不留陈旧墓志铭）。泛化「运行失败」降级为前 error 行旧数据的回退。

**Consequences**: 修订指认粒度到段落，agent 永不用猜「这段」是哪段；失败卡的叙事与 dock RunTaskList 的失败行同源同文（同一条 `user_error_line`）。无大屏编辑器路线——卡面编辑能力 = 直改程序（K4）+ 选区钉给 agent 两通道，手工改字只是逃生舱。

**Related**: ADR-058（mention 注册表指认族——quote 是其首个字段扩展）、ADR-065（服务感失败行）、ADR-057 K4（卡面直改——与选区引用并列为卡面两修订通道）、MENTIONS §3（闸门——quote 是字段不是新类型）

## ADR-070: 确认拍回座 dock + placeholder 恒定律——下一步住在用户看着的地方

**Status**: Decided (2026-09-11)

**Context**: 产品试用截图取证：桌面 panel 形态任务书 dock 后，echo 散文说 "review the plan and hit Start"，但 ADR-063 K5 裁定把确认 pill 闸出 panel 形态——唯一 Start 住在画布任务书卡的 "Confirm & run" 按钮上。四重断裂：① 散文指的按钮在 chat 里不存在；② 按钮名（Confirm & run）与散文动词（Start）不一致；③ 确认期 placeholder（"Ask me to adjust the plan…"）只承诺「改」的路径，已存在的文字确认路径（G-1：chat 里说 "start"）无人告知；④ 被指认的画布按钮可能被 float 面板遮住（fitView panel-blind，画布探索导航的设计使然）。用户判词：「用户怎么可能在这一刻去注意到什么 canvas 上的按钮」；对动态 placeholder：「就固定用一开始那句，心智负担超很多」。

**Decision**:

1. **确认拍 = dock pill 唯一座位，三形态同座**（无 `form !== "panel"` 闸）：确认时刻用户看着的地方是 chat；画布无确认钮（任务书节点下线，ADR-072 ⑤）。密度律（ADR-054）不动——单任务书仍纯散文确认、无 pill。
2. **一个动作一个词**：确认动作文案 = dock pill 的 `generationOverlay.confirm`（"Start generation"），echo 散文的 "Start" 有所实指；promptEdit 定价确认的 "Confirm & run" 不动（那是另一个动作——确认一次卡面直改）。
3. **placeholder 恒定律**：dock 输入框 placeholder 一切相位恒为 `chatPlaceholder`（"Use '@' to mention nodes and describe changes"）——相位感知切换的引导价值抵不过它的心智负担；确认期「下一步是什么」由确认 pill 自己说。无 `chatPlaceholderConfirm` i18n 键。
4. **echo prompt 松绑**：`prompts.py` DENSITY 段不再硬编码 "card + Start button" 双指认——Start 钮恒在 dock（全形态），计划的评审面表述为表面中立（计划卡或画布草稿图，均可审）。

**Consequences**: 确认时刻的唯一下一步在它被读到的同一表面上有钮可点；散文、按钮、placeholder 三处词汇归一。

**Related**: ADR-063（动作住节点内）、ADR-054（密度律不变）、ADR-058（二源律）、ADR-072（任务书节点下线——确认拍最终座位）

## ADR-071: prompt 工程结构律 + 零硬编码默认链——j2 单一化、考古不出 token、规则减负

**Status**: Decided (2026-09-11)

**Context**: 用户判词「prompts.py 太不灵活」——工程结构僵硬与行为教条双确诊：① 两座 200 行 Python 字符串字面量（隐式拼接 + 手工 `\n`，编辑 = 字符串手术）；② 双胞胎规则 6 处且已不同形（言语语言 / 提问三律 / 无素材 / 目标语言 / 命名 / mention——改一处漏一处 = 相位漂移）；③ 考古沉积进 token——历史注（"the prior reflex was the bug" 类）把被否决的旧模式摆进模型上下文；④ schema Field 描述与 prompt 散文双文档且已漂移（实证：`answer` 描述 "Null for draft" 是错的——draft 的 echo 散文恰恰骑 answer）；⑤ 默认链硬编码（vague → 固定四件套）与现实冲突——用户判词：「不同的 chat 不同的 graph 流程都不一样，不要出现任何硬编码，信息通过动态上下文工程来」。

**Decision**:

1. **结构律**：chat 两个 system prompt 住 `app/prompts/chat/*_system.j2`（与全站 agent prompt 同一 jinja_env 基建；`*_system` 后缀区分 `app/prompts/` 根下同名的 user-turn 模板），真·双消费共享段 = `_*.j2` partial 单一定义两处 `{% include %}`——**五件**：speech_language / translate_target / naming / asking_strategy（提问三律，router 嵌套列表形为正典）/ writers_no_material（router 全块为正典 + `{% if chat_loop %}` 相位分支承载 chat loop 的 existing-project 尾巴）；动态目录行（tool / op / wiring lines）作 render 变量注入；`prompts.py` 降级为薄装配包装（函数签名不变，零调用点改动）。机械迁移必须 byte-identical——`scratch/prompt_split_diff.py` 渲染对比脚本卡死（before = 拆分前快照）；后续每次编辑性改动同律——router 侧渲染 byte-diff 卡死，chat_intent 侧 unified diff 审 delta。mention 规则与 key order 不抽：前者从来不是双胞胎（旧 router prompt 无 mention 块，查快照实证），后者两相位字段名不同（answer vs summary/text），是合理分叉。
2. **零硬编码默认链**：链的形状永不写死在 prompt——"Default chain when the request is vague" 规则**整条删除**（先改为「从上下文判断」的灵活版，探针实测后对 vague 引导做减法到底：模型有工具目录的 when-to-use 描述与上下文，vague 请求的判断不需要专条）；`tasks_explicit` 语义不变（false = 默认提案的来源簿记）。
3. **考古不出 token 律**：日期 / ADR 编号 / 历史注永不进模型可见文本——出处住模板头 `{# #}` 注释与本文档；模型只见规则的当前态。**例外判例**：看似考古的行可能有**语义承重**——「lift applies ONLY to the ask-back refusal」限定弹是承重限定不是考古：剥考古括注、留限定本体（模板保留此弹 + "The two rules cooperate: lift the gating, keep the grounding."）。
4. **规则减负**（探针 A/B 双闸后执行）：死字段 `confidence` 不进 prompt（零消费方；schema 字段留作读容忍）；风格脚手架三禁令 + never-reuse 并入 FREE PHRASING 一条（保留 banned literal 作例）；目标语言 worked examples 两条（同源护栏本体保留）；参数骑行四规则并一；NO-MATERIAL CASE 两行；answer/draft 例表每类 ≤3，start 例表 6 条全量保留（中文例防语言锚定）；EXCEPTION 1/2 并入 Disclosure 段；无 vague 默认链（判词②）。**承重保留**：碎键不起跑 / never invent platform（ADR-060）/ subtitles vs dubbing / whole-source vs highlights（ADR-043）/ presented chain 保全 / 提问三律 / 出书门槛 / key order（打字机律牙）/ pending-question 段 / **no-material 块的块结构（标题 + 子弹组）与 lift 限定弹**（判词③例外）/ echo 块近逐字旧构（ADR-070 换面中性 Start 句、Disclosure 命名）。
5. **prompt 散文 = 模型契约单一事实源，schema = 人类侧镜像**：provider 调用发 `response_format: {"type": "json_object"}`（`providers/llm/minimax.py`），Pydantic schema（含全部 Field 描述）**从不发送给模型**，纯做解析侧校验；模型唯一可见的形状规格 = prompt 散文。schemas.py 注释做准确镜像 + 路标（"edit the template first, then sync this mirror"）。**json_schema 路线判负**：MiniMax M3 hosted **接受但完全无视** `json_schema` response format（spike 实证：裸 prompt 下输出自由发明结构，必需顶层字段全缺席）；同一 provider 的 **tool_calls 通道的 parameters schema 模型是遵循的**——结构化约束在 M3 上唯一有效的载体是 tool_calls 通道，json_schema 是摆设。未来若要消灭 schema 拒收失败类，路径 = 原生 tool-calling 迁移（~11% 截断率由「JSON parse 失败按 schema 拒收走修复轮」吸收），独立迁移批。chat_intent shape C 骨架带 `default_path`——两相位共用的 skip 路径牙（dock × 与插话提醒消费），只有 `slot` 是 chat loop 留 null。
6. **prompt 减肥必须过探针闸，且探针必须轮转（双重流程律）**：① **任何 prompt delta 靠探针实测，不靠文本推理**——bisect 仪器 = `scratch/router_ab_probe.py`（合成上下文直调 router，old/new 同 ctx 对比）：三个探针（start 判决 / slot 握手 / 裸愿望）+ **上下文必须复刻剧本真人设状态**（`persona_exists: False`——带人设的探针会给出假绿）。② **探针调用必须 round-robin 交错，禁按变体顺序连跑**——provider 状态以分钟尺度漂移，顺序批把「变体」与「时间」混杂。③ **冗余与限定不是脂肪，小型 open 模型的指令遵循靠它们承重**——承重件 = no-material 块结构 + lift 限定弹 + start 例表 + echo 块结构，减肥不得动它们。
7. **混血形状代码侧顺形（断根修复）**：`draft + tasks=[] + ask 对象在场` 是模型表达「我得先问」的自然混血——链裁决**无回 ask 的活路**（repair 只认非空有效链，retry 改判 ask 也算失败）→ 必落拒答行。`service.py` 出书前加读容忍：该形状直接重读为 ask 判决（ask 分支自有误触/已问轮转护栏接手）——任何 prompt 版本下它都落座提问，永不落拒答行。**扩座**：任何 ask 判决（直判或混血翻转）在仍有待决行（任务书或普通问题）时一律转**插话形态**（ask 散文落普通回答 + 普通问题待决时带提醒尾，待决行保持敞开）——docking 会 supersede 任务书行、使确认成孤儿：书行死而 `project.pending_brief` 活，派发读「无待决书」把后续轮路由进 chat loop，"looks good, start" 落成 bare-run wiring 空转、run 永不起。**`_constraint_key` 数字归 `#`**：同键重申恒胜——"under 200 words" 与 "under 100 words" 数字归一后同键、逐项 precedence 原位替换，不攒自相矛盾的双条目。**第二颗牙**：`draft + tasks=[] + 无 ask + answer 在场` 是混血的对偶——模型把能力/元问题的回答写进 echo、走错 action 字段；重读为 answer 判决：播出的散文即最终内容，无拒答无换面（空链永不可 dock——严格优于必降级结局）。
8. **被跳过槽位的推断值不算根**：出书门槛 `has_root`——topic 槽已在 asked 簿（用户 × 跳过 = 已选默认路径）时，只有 user-stated 的 topic 才算根；模型推断的 topic 不再把书重新有根化、绕过 draft_from_persona 的代码宣言（reason + code echo 双缺席 = 失败形态）。素材在场仍经 material_state 成根（infer-from-material 路径不受影响）；用户后补原话永远算根。

**Consequences**: prompt 面改动的验收三阶段——byte-identical（机械拆分）→ 渲染级 unified diff（减负 delta 可审）→ 轮转探针 A/B + 全量剧本。部署前仪式：纯函数 pytest → prompt gate（`scripts/prompt_gate.py`，三探针绝对阈值 A≥8/B≥8/C≥10；判负先复跑一次再用 A/B 仪器 bisect，永不调阈值迁就回归）→ 全量剧本。工具名枚举的漂移报警 = `ToolEntry.needs_media_file` 旗标（零行为元数据，人工标定）+ `tests/test_prompt_registry_consistency_pure.py`（media-needing / writers 两枚举与注册表对账 + 全模板枚举名注册校验）——MEDIA∪TRANSCRIPT 派生轴会误纳 align_stills（requires=(TRANSCRIPT,) 却为无录音场景而生），故旗标人工标定、测试对账而非自动派生。slot 握手与 start 判决的残留 flake = 模型侧既有方差，非 prompt 杠杆可解；模型把 brief 写成无槽名来源化条目数组的形状天然有损（无槽名无法映射 topic/audience），代码侧顺形无路，挂账为模型侧课题。

**Related**: ADR-052（提问三律 / 出书门槛——内容不变）、ADR-054（密度律）、ADR-058 / ADR-060（命名与防编造——保留）、ADR-064（顺形律——brief 形状指导保留）、ADR-070


------

## ADR-072: 画布三族 + 两站拆分 + 任务书节点下线——画布 = 过程图与改点暴露

**Status**: Decided (2026-09-12)；词表 v3 见 ADR-076；施工简报 `docs/archive/tasks-done/graph-canvas-three-families.md`

**Context**: 画布走查三伤连根——① 线与锚歪（出生动画 transform 污染 xyflow 挂载期 `getBoundingClientRect` 测量，事后无重测）；② 节点左舷冒出 @ 锚（task_book → 每节点的 ctx 叙事边）；③ PROMPT 区只有一行参数复读（`compose_spec_prompt` 拼装的假程序）。讨论中用户立下画布公理：**图 = 我们替用户完成任务的过程图，并暴露过程中用户可能想知道和修改的点**——筛子 = 每个元素回答「用户在这儿能知道什么、能改什么」，答不上就降级或删；prompt 测试 = 「改这段话，产出会变吗」，不会变的就是假杠杆。用户拓扑判词：transcript → 派生译文文档 → 派生成片；task_book 节点不该存在。MiniMax Design 节点划分（文本/表格/图片/视频/音频——按媒介不按生成方式，深度编辑面与驻留卡分离）互证。

**Decision**:

1. **节点身份词表（现行 = ADR-076 词表 v3）**：`type` = 媒介五值 text/table/image/video/audio；`spec.prototype` = generator/editor/manual；业务身份 = label/tool；卡面解剖族 = 全文卡/表格卡/媒体卡。节点内部怎么实现 = 出生史维度，不决定卡种；分类轴 = 流程位置 × 程序本质（无程序 / 参数程序 / 散文程序）。
2. **文档族两解剖**：**散文档**（transcript / 译文 / 配音稿 / post / article / research brief——文字层直改，封顶滚动 + 选区引用现成）与**表格档**（结构化行列，单元格级确定性修改）。**两层诚实模型**：文字层可改、时间轴层冻结（词级时间戳不动；时间轴错了走素材 reprocess）；改字 → 下游 stale 徽标（机制现成）。
3. **翻译/配音两站拆分**：`translate_clip` / `dub_clip` 各拆为「文本站（文档节点：译文/配音稿，语言杠杆，**无 prompt 位**）→ 装配站（字幕/配音成片卡）」。红利：翻错一个词改文字、**只重渲染不重买翻译**；估价更诚实（翻译 token 记文档站、渲染记装配站）。
4. **分镜表升格为表格档节点**（clips 链：transcript → 分镜表 → clips 装配卡）——回答「为什么是这三条」；用户原话挂分镜表（选段决策发生处），clips 卡纯化为装配族；单元格改 = 确定性 op（删行 = 弃选、改时间窗 = 重切）。
5. **task_book 画布节点下线**：任务书是计划，图就是计划的显形——计划的照片不挂在计划的执行里（同一份事实的第二个座位）。它承载的一切有真身：用户的话在 chat（出生与确认之地）、链 = 图结构、估价 = 节点折叠、确认手势 = dock pill 唯一座位（ADR-070）。`projects.pending_brief` 项目状态不动，dock「继续设置」复活路径不动。**无 ctx 边物种**（节点真正读的是上游工作产品，不是合同）——边全部回归真实物料流；@ glyph 永不上画布（ctx 入锚并入共享 T）。
6. **modifier 杠杆化**：`add_music` / `remove_filler` / `reframe_clip` 不再拥有画布节点——它们是装配卡的**结构化杠杆**（配乐 mood / 去口头禅开关 / 画幅）。杠杆行纪律：上行 ≤3 个定义性参数（改变「产物是什么」的）；只上行本 run 实际启用的（卡面不做能力货架，加能力归 chat/配方卡）；样式参数永不上杠杆行。每个杠杆 = 确定性参数级 wiring op（`set_param` 族）+ 程序区定价确认（ADR-058 通道分家延伸，零 LLM、零 dock 消息）。
7. **materialize_source 折叠为消费节点内部 step**（render 同案先例）——画布上素材直连变换卡，打勾流里仍以 step 行可见。
8. **PROMPT 区 = 散文程序节点挂用户原话**：`TaskItem` 加可选 `instruction`（router 逐任务**逐字摘录**用户原话——copy verbatim 永不改写，无枚举则 null）；无原话 = 区域不出现（无 `compose_spec_prompt` 参数回声，legacy 行读容忍）。散文修订恒走 chat；卡面散文直改（ADR-057 K4）语义不变。
9. **样式覆写地基**（迟早会做样式修改）：默认样式 = persona 皮肤块（ADR-038 不变）；单点覆写 = 产物/节点 spec 级 `style_overrides` 键（数据层留好，UI 后做，形态 = 面板/overlay 非杠杆行）。
10. **锚点测量污染修复**：出生动画（`flow-node-born` transform）不再包端口层——NodePorts 移出动画容器（或动画结束 `updateNodeInternals`），挂载期测量失真断根。
11. **prototype 三值地基（ADR-076）**：`spec.prototype` = generator/editor/manual 随 stamp 入 spec，卡面程序区按 prototype 组装（editor 卡组件层无 prompt 槽——参数回声根灭；generator 保留程序区）；作者身份不作卡种——业务身份归 label/tool；纯 prompt 生媒体 = 媒介×generator，矩阵有其格。
12. **MiniMax 三不抄**：「添加节点」菜单（图由 chat 生，手动布线永不开放）、多轨时间线剪辑（L3 铁律，导出剪映）、ComfyUI 工作流（开放式编排，拓扑代码定 ADR-028 不变）。

**Consequences**: prompt 面有改动（`TaskItem.instruction` 摘录规则）——prompt gate 必过。`FlowNode` kind 词汇前后端一致；legacy 数据（旧五型行 / ctx 边 / 书节点行）读容忍。配方卡图形态见简报 `docs/archive/tasks-done/graph-canvas-three-families.md`。

**Related**: ADR-057（图即产品对象）/ ADR-058（二源律、通道分家——杠杆与零消息延伸）/ ADR-060（防编造——PROMPT 挂原话是其最强形态）/ ADR-061（变体并行律——两站拆分后不变）/ ADR-062（边对账律——ctx 撤边经 disconnect）/ ADR-067（端口法则）/ ADR-069（选区引用——文档卡修改面延伸）/ ADR-070（确认拍 dock pill 唯一座位）/ ADR-076（词表 v3）

------

## ADR-073: run 期消息流时序律 + 清单活态默认展开 + 起始 banner 退役

**Status**: Decided (2026-09-13)

**Context**: 产品试用截图取证三伤——① 方向选择题（期 4 interrupt）回答后，活态流里 QA 块排在「我开始生成了——」**上面**：起始行住在 taskList 单元内随它 +∞ 钉底，QA 按真实时间排序反而压过 run 的开场白（用户判词：QA 应该在起始行和「正在规划内容结构…」**之间**）；② 终态后 QA 块排在收据（✓ 题名 · 总耗时）**下面**：收据锚在 run 出生刻（ADR-058 排序锚），mid-run 生活全部掉到收据之下；③ 点击 Start 后消息流多一条「✓ 生成计划 · 题名」机器块（活态 header unit / pre-run QA stand-in）——用户判词「这个不应该在这种时候出现」。

**Decision**:

1. **起始句独立锚**：run 的起始言语（ADR-093：start_run 回合的 LLM 言语，落库普通 message 行）序在 taskList 前；活态 mid-run QA / 插话按真实时间落在起始句与钉底动态行之间。
2. **收据锚在 run 结束刻**：终态 taskList（收据）锚 = lastStepT+1，terminal 单元（收官句）随其后——mid-run 生活（QA / 对话）恒在收据之上，ADR-058「收据永不高于生产回声」由构造成立（回声必 mid-run）。`workflow_run_id` 章不再是排序锚，只剩 detached run 内联归档（RunCard）的归属关联。
3. **无起始 banner**：确认拍的记录 = echo 散文 + 用户原话 + 开工句（ADR-093 §2，start_run 回合的 LLM 言语）+ run 收据行，机器块零增量——无「✓ 生成计划 · 题名」块、无 pre-run QA stand-in 抑制逻辑（`hasPreRunQaArchive`）、无 `generationOverlay.title` i18n 键。
4. **清单活态默认展开、落档即收**：RunTaskList `open = userOpen ?? !terminal`——live 默认展开导轨树（步骤平铺 = run 的活读面，步骤推进逐行可见）；terminal flip 仍重置未手切的 toggle，落档恒收一行收据（✓ 题名 · 总耗时），归档态点击可再展开。

**Consequences**: QA 归档律不变（选项问回答坍缩成已答问题双层消息入流、task_book start 永不入 QA 块）——变的只是排序锚；方向问答的记录双座照旧（流内 QA 块 + interrupt 步骤行「方向：…」量化重写）。

**Related**: ADR-058（排序锚与二源律）、ADR-053（问答机器——归档律不变）、ADR-051（dock 唯一壳）

## ADR-074: 部分失败 = FAILED + 同语言编译期裁决双座 + 画布终态自愈

**Status**: Decided (2026-09-13)

**Context**: 同一张字幕配方卡走查三连伤（用户截图取证）：① 「中英双语」遇 en 源——router 在 ASR 落地前判意图（`file_language=None`：素材 19:26:55 创建、消息同秒发出、ASR 判出 en 是 6 秒后），按 prompt 语言猜源拟出 translate→en 死链，用户确认后 run 在步骤上才死；② 该 fork 红 ✗ 失败，run 却仍 COMPLETED——绿收据 +「做好了」收官句（`maybe_finalize_run` 的旧判定谓词是 fork 时代写法：只数 generation 节点，fork 失败搭幸存兄弟便车）；③ 生成途中画布节点/边整体消失、刷新才回（探针在 scratch 项目复现同形冻结：run 尾部 refetch 重建全部节点时卡高正在变，xyflow store 重同步留下一层渲染输入未就位，refetch 循环全停后再无东西触发它）。另有判词：字幕卡声明链追齐 ADR-048 分家（西语配音腿移除，配音归 voice-dub 卡 / chat 点名）。

**Decision**:

1. **同语言编译期裁决双座**（一真值两座）：`_check_transform_targets`（morph.py）= 运行时同语护栏的编译期镜像——目标语言 = 实际面对的源语言即拒，修法指名且方向感知（zh 源双语目标 en / en 源目标 zh；语言未知静默，运行时护栏仍是兜底）。落 **chat 草案校验**（随既有修复环弹回 router 重拟，修复轮同查，再拒则 degrade 答话，永不 dock 死链）+ **出生地 422**（typed Start / 手改书面板，钱动之前拒）。判定所面对的源语言按运行时同一规则镜像：target_output_id 的 clip / 带 select_clips 链 → 源素材语言 / existing profile → 既有 clips / materialize profile → 录音素材。
2. **部分失败判定收紧**：`maybe_finalize_run` 谓词 = **任何非 runtime-fanout 步骤 failed ⇒ run FAILED**（render fanout 排除照旧：一产物一步，渲染失败是画布卡上的产物级事实，永不是 run 判决）；谓词唯一。失败但有产物落地 = **部分失败**（落地 = done 且带 `output_refs` 的步骤——preprocess / understand / plan 等预备步不算， Prelude 跑完而工作全灭的 run 画布上什么都没有）：project → REVIEW（结果世界开在落地的产物上）；全灭才回 DRAFT。前端：收据红 ✗（ADR-073 失败收据态不变）；**收官句随成功 run 或有落地的部分失败 run 落**（前端门与判决同一真值：done + output_refs），部分失败说部分真相（`chat.runPartial` / `runPartialMore` 文案不变——命名首败步 + 人话 error，二源律照旧）；`onComplete` 完成 refetch 同门（有落地才交接，全灭不拉）。全灭 run 不推 terminal 单元（收据即失败面）。
3. **画布终态自愈 remount**：run 落终态 ~0.6s 后页面 bump epoch，ResultsCanvas 按 key 重挂载 FlowView——xyflow store 从零按沉淀后的 props 重同步，失同步族（节点层 + 边层）在「告诉我做好了」时刻必愈。代价 = 终态 viewport 重新 fit 一次（用户彼时在读收据不在拖画布）；mid-run 窗口仍由 SSE step diff 的持续 refetch 覆盖。
4. **渲染步计入活跃集合**：run 终态 = 最后一条渲染落地（渲染失败仍是产物级事实、不撑失败判决，但撑活跃判定）；渲染链在渲染落定处补调 `maybe_finalize_run`（渲染镜像不经 `execute_step`，无人替它收官则 run 永不收官）；启动扫尾 `finalize_stuck_runs` 同律（reap 刚把渲染 re-pend，崩中渲染的 run 必须活过扫尾）。`delete_output` 把 pending 渲染镜像落 skipped（行没了镜像永 pending = run 永不收官；running 镜像由完成路径自愈）。渲染 metering 的 capture 在 release 之前。前端零改动——SSE run 流活到终态帧，终态帧就是真相。
5. **画布几何零测量依赖（钉死几何，不依赖测量）**：xyflow 的受控同步对身份 churn 丢弃测量——refetch 重 map 出的新节点对象触发 `adoptUserNodes` 重建内部态并丢弃 `measured`，而尺寸不变的节点永远等不到 ResizeObserver 重测（隐形至 remount）；`handleBounds` 同病（测量票丢失的 handle 的边隐形到 remount，节点 visible 不代表 handle 已测）。修法：`flowNodeSize` 的尺寸（frame 律真值）以一等公民字段声明给 xyflow——`width`/`height`/`measured` 三件套随 rfNode 一起传，`adoptUserNodes` 原样保留 `userNode.measured`，`parseHandles` 只在 `userNode.measured` 存在时保留旧 `handleBounds`；端口座位同律声明——`layout.ts declaredHandles`（端口几何纯数学：28px 圆 / 左右 -34 / 34px 叠距 / 入锚底锚定分区基线 / 出锚 top 40，与 NodePorts CSS 互引两座位）随 rfNode 传 `handles`，`parseHandles` 每次重建直接采信声明值。画布几何（盒 + 锚）零测量依赖，DOM 测量退化为只会读到同一组数字的兜底校验；终态 remount 降为纯兜底。

**Consequences**: 连带修复两个真 bug——`/graph` 在 ≥2 个转写文档时必 500（A3-lite 边合成把已合成的 dict 行当 ORM 行做属性访问；改循环外单次 ORM 快照）与 `/results` 一次瞬断后 error 闩锁不清（成功即清）。不新增 `WorkflowStatus.PARTIAL` 第三态（SSE terminal 集 / RunCard / project 映射的爆炸半径过大；项目列表徽章对部分失败读 failed = 诚实面）。同语裁决与配方卡改的都是代码座与 UI 文案，`app/prompts/chat/` 未动，prompt gate 无新增义务。

**Related**: ADR-073（失败收据态）、ADR-048（字幕/配音分家）、ADR-057（零投影直读——自愈 remount 的座位）、ADR-040（配方 = 提示词）

## ADR-075: 画布媒体跟源比例 + 分档加宽——真实像素是形状真值

**Status**: Decided (2026-09-13)

**Context**: 字幕卡走查第二轮（用户截图取证）：100% 缩放下产物视频节点太小，且不跟源比例——源文件取证 = 960×960 方形（keynote 录屏，16:9 内容自带上下黑边），渲染层忠实保源（materialize → translate×2 全程 960×960 出），但画布把 `render_spec.aspect == "original"` 一律按 16:9 默认条预留（280×158 媒体区），1:1 视频 object-contain 进 16:9 盒 = 两侧大黑边 + 面积缩水；素材节点同病。根因不是渲染是画布：整条栈从无源的真实像素——`asset.meta` 只记 words / language / speaker_map / prosody，"original" 的展示档在画布出生时刻无处可解。

**Decision**:

1. **真实像素入 meta**：`meta.width/height` 双座写入——① 客户端 staging 探测（`stagedFiles.probeMediaDims`：img naturalWidth / video loadedmetadata，与 chip 预览同一探头族）随创建载荷送达（`AssetCreateRequest.width/height` → `create_asset_from_key` 出生即写 meta，home composer 与 chat dock 两个上传座同律），零赛跑；② 资产处理链头 `_content_hash_processor` PyAV 开容器兜底（API 路径上传 / 预探测旧行回填），探测在临时文件 unlink 之前、任何失败静默缺席。展示面事实，不入计费不入 prompt。
2. **展示档解析一座**：`graph_store.display_aspect_class`（几何均值边界 0.75 / 1.334 取最近档——离比例保 contain 细边，永不裁剪内容）+ `resolve_source_aspect`（多源混形 → 返回 None 不猜，保 "original" 默认条）。三个消费座：① **stamp/fill 时刻**——graph_fill `_stamp_graph_core` 查源资产 meta 尺寸把 "original" 解析成真档（帧出生时就是对的，定居取景律不动）；② **片段出生时刻**——materialize_source 把展示档盖进 `ClipPayload.aspect`（fork 派生行随 payload 复制自然继承；`OutputResponse._derive_aspect` 的写点模式与图片产物同款，`render_spec.aspect` 渲染契约不动，读面永不补丁）；③ **素材节点出生**——`stamp_asset_node` 按资产自身 dims 盖 `spec.frame_aspect`。
3. **分档加宽**：clip 车道 9:16 不动（280×498 媒体区）/ 1:1 → 340×340 / 16:9 → 400×225；素材节点同律（280/340/400 三档）。帧表改按档 (w,h)：`_CLIP_FRAME` / `_ASSET_FRAME`（max 档入 `_FRAME_CLASS`），`_PITCH` 随最大档 400+96。client 镜像（layout.ts `PRODUCT_THUMB_PX` / `displayAspectClass` / graphNodeSize 素材支 `assetDimsHeight`）——判词② 一条测量律两镜像互引不变，永无第三份。
4. **预留律牙（赛跑/旧行兜底）**：帧可能早于尺寸到达（API 路径上传 + 预探测旧项目）——卡面媒体区与 graphNodeSize 双双 cap 到出生帧预算（`frame.h` 减 label/program/toolbar 三段）， contain 细边回归但帧永不被撑破、列永不重叠；dims 全缺的 "original" 保 280×316 默认条（今日外观，零回归）。

**Consequences**: 1:1 链 = 340×340 正形卡，真 16:9 源 = 400×225；无尺寸旧行外观不变。渲染契约 / prompt 面零改动（prompt gate 无新增义务）。

**Related**: ADR-057（定居取景 / 零投影——帧律与测量镜像的座位）、ADR-072 / ADR-076（节点词表——素材节点同律的依据）、ADR-074

------

## ADR-076: 画布词表 v3——type = 媒介五值、prototype = 能力原型三值、业务身份归 label/tool

**Status**: Decided (2026-09-14)；施工简报 `docs/archive/tasks-done/graph-canvas-three-families.md` §3.5

**Context**: 画布三族批（ADR-072）批 A3 主体动工前的词表评审，五轮收敛：① `kind` 一词双义（`step.kind` = 工具名 N-35 vs 图节点 kind = 族）必须拆；② 节点身份词表先后两案被否——抽象案（源/文档/装配三词）「不直接」、业务案（post/captions/dubbing 业务词）「越层」——用户判词：**type 怎么可能和业务强绑定；type 是通用工作流流程节点概念，「能用于表达 xxx 业务」但本身不 named after 业务**（ElevenLabs 的媒介 tab = type 本身，菜单项 = type 上配置出的业务能力；MiniMax 的媒介列表同构互证）；③ generator/editor 之分是真实产品轴——编辑链配方卡的 PROMPT 参数回声 = editor 卡上挂了不属于它的部件——作为**能力原型**地基落成，缺省值定名 `manual`；④ `prototype` 属性名由用户亲定（不用 nature）。

**Decision**:

1. **三轴词表，各管一件事，谁也不越界**：
   - **`type`**（graph_nodes 列，kind→type 改名 + 值迁移）：通用媒介概念——**`text` / `table` / `image` / `video` / `audio` 五值**（MiniMax 媒介划分；与 ADR-072 判词② 文档两解剖合体：散文档 = text、表格档 = table）。决定卡面解剖（全文卡 / 表格卡 / 媒体卡）与框架律。
   - **`prototype`**（spec 键，stamp 写入）：能力原型——**`generator`**（散文程序：PROMPT 区 = 用户原话，散文修订）/ **`editor`**（参数程序：杠杆行 + 原话指令行）/ **`manual`**（无程序区：改动 = 直操内容本体——文字层直改 / reprocess / 删除）。决定程序区形态，**不改变执行语义**（估价折叠 / 修订通道 / 版本分页不变）。
   - **业务身份 = label + tool**：`spec.summary`（builder/LLM 写的卡名，ADR-058 二源律①）与 `spec.tool`（执行体）承载「翻译字幕 · DE」「撰写社交帖子」——type 能表达什么业务由这层说，type 词表恒五值、永不长业务词。
2. **映射律**（全节点落位，含 ChatCut/ElevenLabs 终局验证）：上传素材 = 媒介×manual；转写稿 = text×manual；帖子/文章/调研简报 = text×generator；译文稿/配音稿/分镜表 = table×manual（文字层直改是唯一改点）；切片/字幕成片/配音成片 = video×editor；金句卡/轮图 = image×generator；文生视频/图/音乐、MG 动画、口型同步、视频超分、对话剪辑 = 媒介×generator/editor——ChatCut 六入口与 ElevenLabs 十四入口无一格填不进。
3. **结构红利**：无 `spec.frame_class`（type 即框架类：text→全文框架数学、table→行数驱动、video/image→ADR-075 画幅分档；旧行 frame_class 留作读容忍）；端口法则媒介化——**video 节点恒 offers {video, audio, text}**（素材与成片同律：翻译一个已翻译的视频天然合法；金句卡谎称 offers video 的旧粒度谎言根灭），text/table offers {text}，image offers {image, text}，accepts 按 prototype 分（editor 收媒介+text、generator 收 text、manual 不收）；卡种 = type 直出、chrome = prototype 直出，无第三轴（不设 spec.card）。
4. **词界与闸门**：`step.kind` 保留 = 工具名（N-35 不动），图节点的族词改称 `type`，双义消除；`spec.role` 降为内部出生证（transcript 级联删除 / task_book +88 框架额），不驱动卡面身份，批 B1 随书节点收编；EditPromptOp 终态闸门 = `prototype == "generator"`，过渡期（批 B4 set_param 落地前）保持 spec.tool 存在性闸门——editor 的修订路不能提前断；type 值随工具注册表声明（NodeBase 类属性 + 启动自检收编），禁平行映射表。
5. **MiniMax 三不抄不变**（ADR-072 判词⑫）：「添加节点」菜单永不开放——type 词表的消费方 = 卡面身份 / 图标 / 端口 / i18n /（未来）能力画廊派生，不是添加入口。

**Consequences**: 词表迁移：列改名走 Alembic；legacy 五值行映射——asset→按 asset_type 落媒介值+manual；document+role→text；generator/processor/agent→按 tool 落媒介值+各自 prototype；`modifier` / `materialize` 过渡词随旧行存活，永不迁移。翻译/配音两站的文档站恒 type=table、prototype=manual。配方画廊 generate/edit 分组徽标与能力路线（MG 动画 / 文生媒体 / 对话剪辑工具）入 PROGRESS 需求池。

**Related**: ADR-072（画布三族——解剖三族保留）/ ADR-057（图即产品对象）/ ADR-058（二源律——label 的座位）/ ADR-067（端口法则媒介化）/ ADR-075（画幅分档——video/image 的框架律）

## ADR-077: 会话层工具 loop 化——常备否决收窄终裁：生产封闭 / 服务收编 / 执行永拒

**Status**: Decided (2026-09-14)；施工简报 `docs/archive/tasks-done/chat-tool-loop-migration.md`；旅程母文档 = `docs/JOURNEYS.md`

**Context**: chat 体验「少了智能」的病根经代码级诊断定案（`agents/base|contexts`、`chat/intent|service`、`pipeline/graph|orchestrator`、`providers/llm/minimax` 通读）：**脊柱（四层工程地图）无病，Loop 层被建成了纯裁决器**——有嘴（散文）有判断（verdict）没眼睛（感知）、没有在对的时刻说话的座位（主动发声）、一次定音（轮内单调用）。三轮需求模拟逐拍倒推（迷失用户首产 / 后续更改服务 / 终极案例仿制，全文 = JOURNEYS）：缺口集中于①感知（read-before-write 是相对量指令与推荐的**功能前提**，不是体验糖）②触发回合（理解完成 / run 完成时 agent 主动说话）③收官 reviewer（判断 + 下一步）④镜头跟随。同期 spike 实证：M3 唯一遵循 schema 的通道 = tool_calls（json_schema 被完全无视；截断 ~11% 走工具错误反馈吸收）——**模型为工具形态训练，JSON-in-prompt 判决逆模型纹理**（顺形律 ADR-064 的架构层兑现）。且我们已在逐个重建标准件（BoundedLoopNode = agent-in-step、ask 判决 = AskUserQuestion 工具、四态 union = 工具集）——方言翻译表（AGENT_ARCH §2.5）的存在本身就是方言的证据。修补判词：当年判「零 agent 全 workflow」时恐惧的对象 = 不可估价/不可测试/不可预测的**开放式自主**；本轮模拟证明该恐惧只命中执行 loop 与拓扑塑形，不命中有界感知。

**Decision**:

1. **常备否决收窄终裁**（边界三层各自钉死）：
   - **生产层 = 编译期封闭 DAG，永不变**——看什么/做什么编译期可枚举；报价=fold、执行=topo、拓扑代码定（ADR-028）不动摇；
   - **服务感知 = 有界只读 loop，收编**——chat 边缘 agent 可调一族**只读工具**（读 spec / 曲库 / 样式目录 / 理解摘要 / run 状态…）；迭代封顶（`max_iterations` 声明）+ 报价 = fold（上限 × 单次）+ 终产仍是「一份判决 + 工具序列」；
   - **执行 loop 永拒**——写世界永远走三扇唯一门（edit ops / wiring ops / `create_run`），loop 内零副作用。
   「是否做 ReAct / 是否做 loop」问题注销：每层各有答案。
2. **会话层全面工具化**：现有判决 union 机械翻译为工具集——`type` 字段 = 工具名、各态字段 = 工具参数（ask → `ask_user` / draft → `present_plan` / start → `start_run` / task_list → `propose_tasks` / edit_ops → `edit_output`（受控四件，ADR-090）/ WiringProposal → `edit_graph`）。**护栏语义搬进工具执行内**：出书门槛 = `present_plan` 的执行内校验（无根 → 工具拒绝 + 结构化反馈，修复回声的同族座位）；出生地 422 不变（`start_run` 内部仍走 `create_run` 零旁路）；dock 生命周期 / 单待决 / autoResume 结算 = UI 状态机 + 代码，原样保留。读工具一族住 `app/chat/perception/`（注册表纪律同 TOOL_REGISTRY：name + params schema + execute + 碎碎念文案键，静态注册随代码部署；与 `app/tools/` 的分工 = **世界的读法 vs 世界的改法**）。loop 驱动 = harness 新形态（迭代封顶 + **终态工具**（ask_user / present_plan / start_run / 最终回复）一调即停）。
3. **触发回合（trigger turn）**：chat 回合的「用户消息」可以是系统事件（白名单首批 = 理解完成 / run 完成）——agent 借读工具看世界再说话。**主动发声（感知缺口 B2）与收官 reviewer + 建议 pills（B3）合并为此机制的两个触发器**；建议 pill 点击 = 把文本作为下一条用户消息发出（修订型走 chat 唯一意图面）或直达动作（导出/下载）。reviewer 的产出 = 判断 + 引导——recap 复读机（复读 spec.summary 的清单复读）永禁；reviewer 看过产物后下一步有据可依。
4. **多 provider 线格式三层**（通用地板 + 高级处理 + 自动降级，用户判词「始终考虑多 provider」）：Tier 0 地板 = action-JSON-in-prompt loop（research 节点已验证此形态可承载全部语义）；Tier 1 原生 tool_calls（M3 唯一 schema 遵循通道，spike 已验）；Tier 2 provider 特有（strict schema / parallel calls / reasoning 控制，逐 provider 声明）。**法则：层只换线格式，永不动判决契约**——各层产出同一校验后结果，降级天然安全，修复/错误反馈语义同构。client 声明能力旗标（`supports_native_tools` / `supports_json_schema` / reasoning 方言），harness 选双方共持最高层；PRICING 按 provider+model 分家；prompt gate（ADR-071）按 provider 参数化复跑。配套结构收口：错误类型去品牌化（`MiniMaxError` 族随迁移批改中性名，user_key 税制不动）；方言消化归各自 client（ADR-066 不变）。
5. **预效果一致性纪律**：agent 的「思路与方向」描述恒从提案对象派生（summary/ops 同一对象两投影——summary 到嘴、ops 到手），校验先于庆祝（ops 过裁决后收官才落地），流式预览翻案即回滚（`question.preview` 既有纪律覆盖）；**不做渲染预览**（口头描述与画布变动一致即可）。
6. **NAMING 原则**：会话层用行业词直取——ask_user / tool call / plan（无方言词；brief 保留原词——NAMING N-52；全表见 NAMING.md）。

**Consequences**: 资产存活：schema（变工具参数）、护栏语义（搬入工具执行）、执行层（零改动）、提问机器 UX（dock/单待决/结算全留）。打字机律三牙（CLAUDE.md）在工具线格式下的重述：散文 = content 通道（~1s 先达）、工具调用 = 相位帧（「正在查曲库…」免费碎碎念）、零 delta 路径仍走 paceSettledProse。风险挂账：M3 多工具多轮择工具准确率 + 截断率吸收——prompt gate 与剧本测试是验收网。画布卡面直改（ADR-058/063）与手动布线永禁（ADR-035）不受影响。

**Related**: ADR-039（四层工程地图——本条是其 Loop 层形态，脊柱不变）/ ADR-052（厚 agent——双引擎分离不变）/ ADR-064（顺形律——架构层兑现）/ ADR-066（方言归 client）/ ADR-071（prompt gate 按 provider 参数化）/ ADR-028（拓扑铁律不破）/ ADR-043（任务书语法）/ ADR-053（提问机器形态律——机制留存，形态工具化）/ ADR-057（图即产品对象——edit_graph 工具的唯一写口不变）/ ADR-078（decompiler——终极旅程内核）/ ADR-090（edit_output 受控四件）

## ADR-078: decompiler 反向编译器——视频 = 可编程时序结构，remix = 换内容留风格

**Status**: Decided (2026-09-14)；旅程全文 = `docs/JOURNEYS.md` §2

**Context**: 终极旅程逐拍走查证明：全旅程只需**三个新概念**即被现有架构撑住（资产角色 / decompiler / exemplar 参数源），其余每拍都是已落地机器或已挂账缺口。本条是其中最重的一个。正向链 clip-spec → video（renderer，黑盒）早已存在；用户洞察指出反向必然成立——clip-spec 就是视频的可编程表示，反向拆解 = 把案例视频编译回这个表示。craft 解剖（`research/craft-anatomy-2026-08-22.md`）与轨道模型（ADR-044）是它的地基。

**Decision**:

1. **decompiler = video → clip-spec 骨架**：案例视频进、一个 clip-spec 形状的骨架出。字段按确定性分层——镜头切分 / 节奏 / 画幅 = 确定性检测（scene cut 一族，零 LLM）；字幕 preset / 颜色 = 视觉最近邻 best-fit 枚举（只在契约枚举内取值）；配乐 mood / hook 装置 = LLM 判断；**内容槽位留空待填**。产物落库（资产级、内容寻址、可复用——understand 的复用纪律原样继承）。
2. **契约即能力边界**：反向编译只产出 clip-spec 里**有家**的字段；案例里超契约的效果（动图形 / 多轨合成 / L3 清单）在分解时没有座位——「这个我做不到」清单 = 结构对比的副产品，带理由纠偏的素材自动成立（顾问姿态②的兑现机制）。
3. **remix = 内容槽替换**：我的素材经 understand / plan / select_clips 填进骨架内容槽，风格字段（字幕 / 配乐 / 节奏 / 画幅）原样保留；产物天然可渲染——分解输出的就是渲染器消费的同一 schema，可执行性由构造保证。
4. **资产角色（source / reference）**：双素材场景的角色消歧走提问机器（一词可答，选项 = 文件名）或 mention 指认；reference 资产常驻项目、可回读（后续修订的比较基准）；角色可反转（reference → source，链照跑）。
5. **exemplar 参数源**：任务书参数的第四来源（user-stated / inferred / default 之外 + **exemplar-derived**）。纪律：**参数由代码从骨架映射，LLM 永不写 spec**——拓扑铁律（ADR-028）不破，骨架是数据不是指令。
6. **双抽取分工**：understand 答「它说了什么」（内容），decompile 答「它怎么做的」（工艺）——两种抽取皆资产级、内容寻址、跨项目可复用；plan 的装配签名加 craft 骨架输入（纯度签名化扩展先例 = §5.3 纪律内）。

**Consequences**: 施工简报 `docs/archive/tasks-done/chat-tool-loop-migration.md`。decompiler 住 pipeline 内部 crew（编译期注入，永不进用户提议空间——与 materialize_source 同族）；CraftSkeleton（工作名）= 新内部产物类型（visible_outputs 过滤族同例）。能力缺口清单（案例里做不到的字段）进 PROGRESS 需求池按价值排期。验收 = 案例仿制旅程 e2e（JOURNEYS §2 的分支树逐条过）+ 骨架字段的确定性分层断言（确定性字段零 LLM 介入）。

**Related**: ADR-077（会话层工具 loop 化——终极旅程的服务面）/ ADR-016（clip-spec 唯一契约——本条是它的反向通道）/ ADR-044（轨道模型——骨架的字段家）/ ADR-028（拓扑铁律——exemplar 参数源不破它）/ ADR-043（任务书语法——第四参数源的语法座位）

## ADR-079: 执行围栏——终态写必须携带执行身份（claim token）+ fenced 零副作用纪律

**Status**: Decided (2026-09-16)；施工合同 = `docs/tasks/r1-batch-2-execution-fencing.md`

**Context**: 写操作不携带「这次执行是谁」。`A claim → A 停滞 → reap → B claim → B 完成 → A 醒来 → A 终态写` 全链路上 A 没有任何一个 DB predicate 会失败：step 行最后写者赢（四尾 = ORM 按 PK 盲写）；钱包双扣（zombie 的 idem key `step:{id}:capture:{attempt}` 与合法 QualityBounce 重跑同族，`merge_accrued_cost` 严格加和 = 真实重复扣款，`release_run` 钳制保证多扣永不退）；渲染守卫 `render_status==RENDERING` 是状态不是身份（re-claim 重进同状态，morph 窗口内 zombie 先完成即静默持久腐蚀——产物与 spec 不一致且无后续触发器）；Suspend 的 run 写是全库唯一无 from-state 守卫的迁移（zombie 可 COMPLETED→WAITING_HUMAN 复活 run，已 release 的 hold 永不回来）。根原则（North Star §8.3）：**Execution writes must be fenced by execution identity**——每一次终态写的 WHERE 必须携带本次执行的身份；写不动 = 失去 authority = 丢弃 + 记日志 + 永不 capture。

**Decision**:

1. **两列 fencing token**（migration `f3a8c1d52e97`，可升可降）：`workflow_steps.claim_token UUID NULL` + `outputs.render_claim_token UUID NULL`。token 回答「**现在**谁有权写」——短暂、随 claim 生灭、失势即 NULL；它**不是**执行模型（ExecutionAttempt 回答「当时发生了什么」，形态 OPEN，禁止互冒充，North Star §8.4 分层维持）。
2. **claim 铸 token**：`claim_ready_node` / `claim_pending_render` 的原子 UPDATE 内 `SET (render_)claim_token = gen_random_uuid()`——认领即铸，铸即唯一。
3. **失 Paths 全置 NULL**：两个 reap（startup 全量 + per-tick 按龄）、execute_step 的 retry 重排 / QualityBounce 重排（verify 节点 + executor + done modifiers）/ runtime_fanout 重排 / Suspend park、`resume_waiting_interrupt`、`_cascade_skip`（含 running 子节点——级联语义落成确定性丢弃）、全部 **10 处既有 render re-pend**（morph / node_runners render / verify title-card / music / captions / dub / reframe / filler / operations undo-redo / 手动 render 端点）。少一处 = 竞态洞原样保留（re-pend 与新 claim 之间 zombie 的旧 token 仍能命中）。
4. **终态写谓词换身份 + rowcount**：execute_step 四尾（成功 / Suspend / QualityBounce / 失败含 retry 分支）全部改条件 UPDATE `WHERE id=:id AND claim_token=:mine`；render 三处终态写（no-spec fail / success / exception fail）谓词从 `render_status==RENDERING` 换 `render_claim_token=:mine`。
5. **fenced 零副作用纪律（核心）**：rowcount=0 → rollback session（executor staged writes 一并丢弃）→ 只记 fenced 日志 → **不 capture / 不 graph sync / 不 cascade / 不 mirror / 不 fire trigger / 不写 run 状态**（I-EXEC-01 stale 执行不写终态；I-EXEC-02 stale 执行零副作用）。刻意的唯二例外：① `finally` 的 `maybe_finalize_run` 照调（行锁 + 终态 early-return，幂等；被级联置 NULL 的节点靠它收官）；② Suspend 的问题消息在其独立 session 已先落库（fenced 后成孤儿问题——known residue，归后续小批清理）。
6. **Suspend 的 run 写加 expected-from-state**：`WHERE id=:rid AND status='RUNNING'`——仅 RUNNING→WAITING_HUMAN 可成；node 写与 run 写双保险后，COMPLETED→WAITING_HUMAN 复活链结构性死亡。
7. **入口防御**：execute_step 入口 `running 且 token NULL` = 外来行（迁移前在途 / 无 claim 镜像翻转）→ 防御性 return（pending 直执路径改为 guarded mint——竞态 claim 赢则让步）；render_output 入口 token NULL → 提前 return（省一次渲染钱）。
8. **部署注记**：迁移后在途行 token=NULL 由入口防御接住；部署即重启 worker（在途 asyncio 任务随进程死亡，startup reap 把行送回 pending 由新 claim 重铸）。

**明确不做**（Gate #2 §7 OUT 清单，逐项维持）：ExecutionAttempt 任何形态 / attempt 语义迁移 / poison-pill 上限（R1 B4a）/ hold GC（R1.1 B4b）/ select_clips 语义收窄 / worker registry / pause-cancel / chat 墙钟 / 统一 Policy 层 / AgentBudget。fencing 不限制健康并发（双活 worker 各 claim 不同节点 = 合法；startup-reap 竞态造成的重复执行被 fencing 正确丢弃——浪费的是资源，不是正确性）。

**Consequences**: 双扣路径封死（fenced 永不 capture）= 收费的诚实前提；render morph 窗口腐蚀封死（zombie 先完成 0 命中，产物永不回退旧 spec）；run 复活链封死。Known residue（登记挂账）：fenced 执行途中已直传对象存储的媒体对象成孤儿（DB 世界干净、存储世界留垃圾，归后续存储 GC 小批，与 render superseded 删 key 先例对齐）；fenced zombie Suspend 的孤儿问题消息（永不过期，窗口极小，后续小批清理）。锁序影响：fencing 写把 step 行锁提前到尾段写时刻（原来在 commit flush），但锁窗口内只剩 capture/sync 的短 DB 操作（无 LLM 等待），D9 族形态不复发。验收 = 纯函数套件（token 捕获决策 + rowcount=0 零副作用，`tests/test_execution_fencing_pure.py`）+ 手工竞态演练（A claim→停滞→reap→B claim→B 完成→A 醒：A 终态写 0 命中、无第二条 capture、run 行保持 B 判决；render 同型；zombie Suspend 不复活 run）+ 单 worker happy path / retry / QualityBounce 回归。

**Related**: ADR-017（reap 语义 fencing-aware）/ ADR-030（render 认领谓词加身份维度——规则 2 的认领先例扩一列）/ ADR-050（guarded-write 纪律 = 身份守卫——会话纪律不变）/ ADR-055（billing——`_mutate` 双层 dedupe 永不破坏，fenced 永不进 capture_step 是 execution kernel owns billing boundary 的具体含义）/ North Star §8（Execution Kernel）

## ADR-080: 单一叙事者律——会话只有一个叙事者，界面语言有唯一 owner

**Status**: Decided (2026-09-17)

**Context**: 一条用户消息引来两个 assistant 写者的事故：plan turn（跟请求 UI locale，说英文）与 `understanding_warmed` trigger（worker 生、自行推导语言，被中文素材拖拽说中文），内容互相打脸（一个说"计划待确认"，一个说"已在跑"）。竞态的地基已修（用户行 prepare 即持久化 + in-flight defer 准入门），但两个残余缺口是产品规则问题不是工程 bug：① 准入门只看「回合在飞」，计划已 dock 待 Start 时 trigger 仍可发言——「这是我的计划请确认 ↓ 我建议你做三件别的事」的冲突依旧成立；② 语言决策沿三条独立代码路径分叉（plan/chat = 请求 locale，trigger = run pin/history 推导），同一会话允许两个 writer 各自决定「今天说什么语言」。

**Decision**:

1. **单一叙事者律**：同一 conversation 内有用户 turn 在飞（`turn_state='in_flight'`）→ trigger **defer**（20s × 15 周期，超限静默）；无在飞回合但**有 pending task_book 计划**→ trigger **静默**（`understanding_warmed` 的「我看了什么」叙事已被计划 echo 散文覆盖，再说一遍只有抢麦没有增量；落点同律——trigger 落 dock 前复评 `is_pending_plan`，命中即整体静默，永不压过 docked plan）；两者皆无 → trigger 方可说话。准入门从「时序门」升格为「叙事所有权门」。
2. **界面语言唯一 owner**：conversation 的界面语言只有一个事实源（请求链的 UI locale / 既有 pin），**一切 assistant 写者**（plan path / chat path / trigger / 未来的 worker 生言语）**继承它**，不做 per-writer 推导。`_trigger_language` 的 history 文字推断降级为「owner 缺席时的兜底」，素材语言永不是言语信号（现行原则不变，本条补的是 writer 间不分叉）。
3. **验收标准**：用户看到画布 + chat 的第一眼，5 秒内能回答三问——「系统理解我要做什么吗 / 它准备怎么做 / 我下一步该点什么」。两个 writer 各说一半、语言不一 = 不过。

**明确不做**：不引入 writer 仲裁器 / 优先级调度层——规则是两张静态谓词（在飞？有 pending 计划？），不是新架构。

**Consequences**: trigger 的可说话窗口收窄到「会话空闲且无待决计划」——盲区由世界事件自身的画布表达兜住（静默教义不变：盲评不如不说）。语言分裂在结构上不可能（单一 owner），prompt 级语言指令仍在但不再是唯一防线。施工 = `_project_turn_in_flight` 同族加 pending-plan 谓词 + trigger 语言解析改读 owner，均落在 `trigger_turn.py` 一处。

**Related**: ADR-077（触发回合 = ToolLoopAgent 第三座，本条给它叙事所有权边界）/ ADR-052（厚 agent 产品层——一个 agent 的产品承诺在会话层的兑现）

## ADR-081: 选项语法统一律——固定选项全归 OptionDock，全局编号 1/2/3

**Status**: Decided (2026-09-17)

**Context**: 提问/建议 UI 曾有三形态并存：阻塞式 option dock（ask_user 族，字母徽章 a/b/c）、计划确认 pill（task_book）、trigger 建议 chip（`intent.suggestions`，LLM 写的用户口吻 pill，点击原样发消息）。第三种「半结构化 pill」是交互碎片：它长得像可选项却不走问题的结算机器（无待决、无 QA 归档、无 autoResume），用户形不成稳定的交互语法。

**Decision**:

1. **二态法则**：凡是系统希望用户**从固定选项中选择** → 一律走 OptionDock（问句 + 全宽选项行 + 铅笔自由行，形态律 ADR-053 R1 不变——trigger 建议 dock 同走**阻塞形态**：ADR-080 双谓词把 trigger 限定到「会话空闲且无待决计划」才说话，阻塞成本低；× = 优雅不选）；**开放式建议** → 普通散文。**无第三种「半结构化 pill」形态**——一切固定选项走 OptionDock，中间形态无座位。
2. **全局数字编号**：OptionDock 选项徽章从 a/b/c 改 **1/2/3**——用户对所有来源（plan / ask_user / trigger / clarification）的固定选项形成同一 interaction grammar（「选 1」恒 = 第一项）。autoResume 的位置命中（字母/序号/原文三态）本就确定性支持序号，改的是展示面不是结算机。
3. **trigger 建议的去向**：`wrap_up` 的 suggestions = **纯 label 数组**（≤3、≤40 字、blank 丢弃；无 download 动作——产物下载是画布产物卡 factsbar 的既有动作座位）；有建议时 review 行经 `_dock_question` **dock 成真实选项问**（选项 id = 1 起位置序号），作答走 answer 端点 generic 续聊分支——**按项目 run 状态分派**（无 run 走 plan path 起草计划，有 run 走 chat path——首跑前点「剪一个金句快剪版」必须产出计划而不是提案工具回答），选中 label 即用户发言。
4. **读容忍**：存量 `intent.type='trigger_review'` 行的 pill 形 suggestions 前端回放渲染保留至自然消亡（灰行旧数据不动），新行的 dump 只带 label 数组（取证用，前端不消费——dock 从 `question` payload 重建）。

**明确不做**：不为建议发明任何新组件/新形态（无「非阻塞 dock 第四态」——trigger 建议复用选项问全机器）；不改 ask_user 的 schema（options 数组不动，纯展示层换徽章字符）。

**Consequences**: 用户面对的选择交互收敛为唯一形态 + 唯一编号语法；「点击 pill 替我说话」的隐式代发声通道关闭，一切选择都经过 dock 的显式作答语义（QA 归档 / autoResume / bail 同源）。施工面 = `QuestionDock` 徽章字符 + `ChatDock` 轮询通道（散文排干后 dock 选项问；`triggerSuggestions` 只服务存量行回放）+ `WrapUpArgs` 纯 label 数组（无 `Suggestion` 类）+ answer 端点 generic 分支按 run 状态分派。

**Related**: ADR-053 R1（形态律——选项问阻塞形态的母体，本条不改阻塞语义只改徽章与消费面）/ ADR-070（确认拍回座 dock——dock 是一切固定选择的唯一座位原则的延续）/ ADR-077 判词③（trigger 是说话不是第二意图表面——建议入 dock 后此原则更显：dock 选项的作答仍走 `/chat` 唯一意图面）

## ADR-082: 画布呈现纪律——布局服务「看懂生产计划」，呈现永不反噬语义

**Status**: Decided (2026-09-17)

**Context**: caption 链走查暴露的画布失真全部由现行算法直接解释（非观感问题）：① **预留高度 ≠ 渲染高度**——文档站预留 340×560 / clip 预留 660，draft 态实渲 ~280/~278，兄弟节点按预留堆叠产生 300~380px 隐形空气，6 节点摊到 ~1200px 纵跨；② **跨列长边**——asset（col0）直喂装配节点（col3），贝塞尔横跨 ~1100px 与其他边穿插；③ **新列上移 88px**（`_FRESH_COLUMN_RISE`）且 settled 路径无居中，图整体向右上发散。GPT 的收紧判词：画布的目标不是「忠实显示工程 DAG」，是「用户 5 秒看懂我让它做什么、它准备怎么做」——execution topology viewer ≠ production workspace。

**Decision**:

1. **呈现/语义隔离铁律**：**永不为了画布排线新增语义节点、改变执行拓扑或补假边**（如为美观虚构 transcript 中继）。图 = 产品对象 + 执行拓扑（ADR-057 不变）；可读性问题的合法工具箱只有呈现层：布局常量、帧预留、分组框（`GroupFrames`，项目页画布补传 groups）、edge routing、视口。
2. **修复次序**：先修**高度失真**（客户端 settled 分支**空气压缩**——同列跟随者上提到前序节点的当前渲染底，`displayY = min(serverY, prevRenderBottom + gap)`。`min` 是结构保险：渲染高永不超预留（graphNodeSize 律），压缩后永不越过服务端座位、列永不重叠；产物落地只长不高回退，跟随者单调下滑归位——图只长不晃。服务端帧零改动，append-only 保序律结构性成立）；再修可读性（同族链分组 / 长边路由 / 居中）。
3. **验收标准**：同 ADR-080 判词 ③ 的 5 秒三问——画布部分的及格线 = 用户一眼读出「Video → Transcript → 中文字幕 / 法语字幕」的生产计划，而不是一团穿插的贝塞尔。

**明确不做**：不改 `settle_frames_with_edges` 的 append-only 保序律（服务端帧永不移动不变——判词① 的压缩是客户端每帧重算的显示推导，服务端帧零触碰）；不引 dagre 等外部布局库（ADR-036 判词不变）；不重开节点族 / 端口法则（词表 v3 与出入锚律不动）。

**Consequences**: 布局算法的输入从「预留档」改为「当前形态实高」，同值封顶（`DOCUMENT_MAX_H`）与两镜像互引律（graph_store ↔ layout.ts）照旧——改的是测量口径不是契约。分组框上项目页 = `GroupFrames` 的第二个消费面（配方说明书先例），零新组件。

**Related**: ADR-036（布局自算 + append-only 保序——本条只动测量输入）/ ADR-057（图即产品对象——呈现/语义隔离铁律的母体）/ ADR-067（出锚语义律——同族的「呈现忠于语义」原则）/ ADR-080（共享 5 秒三问验收标准）

## ADR-083: 信任锚 echo——present_plan 的三语义职责 + grounding 四级证据链

**Status**: Decided (2026-09-17)

**Context**: ADR-080 静默 trigger 后暴露能力误杀——「Agent 真的看懂了素材」这个**付费前信任锚**的数据层（`MaterialUnderstanding` 物化行）与工具层（`get_understanding` 在 plan path 注册表内）完好，但它唯一的发言人（trigger turn）被静默，而存活的 plan turn 被「2 句律」明文限制在文件名级素材认知（"judged from the user's own words or the filename"）。first loss boundary = 言语契约层，不是数据层。三条收紧：① 不做新僵硬模板（约束语义职责，不约束句法）；② 不强制 `get_understanding` 工具轮次（会破坏 speak-first 流式拍，产生 "I'll take a look…" 过渡语）——ready 理解行在 assemble 期注入（DB 读，零 LLM 零轮次）；③ grounding 链收紧——filename/metadata 是**身份证据不是语义证据**。

**Decision**:

1. **echo 三语义职责**：present_plan 的言语承载 ① **信任锚**（我实际读到什么 + 核心判断——付费前用户必须能验证 agent 理解了内容）② 计划转述 ③ 完成标准 + 下一步，自然表达为 2–3 句，职责相邻可合并成句，永不为凑数注水。瘦身意图保留：bookkeeping / 公式脚手架 / DAG 复述仍禁（结构是画布的职责——Chat 管 understanding/judgment/confirmation，Canvas 管 structure/plan，互不复述）。
2. **grounding 四级证据链（严格）**：理解行 = 完整语义证据 → transcript/excerpt = 限于已读文字的语义证据 → 用户自己的描述 = 复述/组织用户说过的话，不 extrapolate → filename/metadata（名称/时长/尺寸）= **仅身份证据**，证明「这是哪个文件」，永不推断内容（`xy_2_15s.mp4` 不支持任何内容断言；陈述时长/格式事实合法）。本回合无语义证据 → 职责① 空缺不编造。
3. **assemble 注入优先于工具轮次**：`plan_turn.assemble` 直接读内容寻址的 ready 理解行入 context（`understanding_lines`，复用 perception 的 `understanding_digest_lines`——一条格式化律两消费面）；未物化 / 形态过期 = 缺席，证据链降级到 excerpt / 用户原话。`get_understanding` 读工具原位保留（mid-conversation 追问的入口），但不再是判断的前置义务。
4. **single writer 不动**：ADR-080 双谓词维持（pending task_book 时 trigger 静默）；`run_completed` 收官判断是付费后复盘，与付费前信任锚是两个节拍，不受影响。

**明确不做**：不恢复双 writer / 不加仲裁层（ADR-080 明确不做维持）；不把理解摘要做成独立 deterministic UI 组件（候选 C 存档——未来可作资产详情页补充，不作替代）；不动 ToolLoop / canvas / trigger 仲裁。

**Consequences**: 机械感的根（2 句律 + 文件名级认知）消除；判断的诚实性由证据链代码可查证（注入在 assemble，读到的才说）。prompt 面改动过 prompt gate（ADR-071）。验收：**点 Start 前用户能从 Chat 确认 agent 真懂了素材，且不听到重复的 DAG/计划描述**——不是「多了一句话」。

**Related**: ADR-080（单一叙事者——本条是同一 writer 的「 richer turn」兑现）/ ADR-077（感知族读工具——注入复用其格式化律）/ ADR-058（展示文案二源律——判断句的素材认知源自世界自证的物化行）/ ADR-060（echo 防编造律——grounding 链是其素材侧推广）
## ADR-084: 言语语义管线——read 静默律 + Start CTA 归 dock + grounding 两态诚实

**Status**: Decided (2026-09-17)

**Context**: ADR-083 信任锚上线后实测仍机械：read-before-plan 回合的最终消息以 "I'll pull the video's language…" 开头。取证定位（`tool_loop.py` 言语账本 + `intent_router_system.j2` SPEECH 律）：SPEECH 律 "ALWAYS speak first, then call the tool" 无条件覆盖 read 调用 → 过程叙事在 iteration 0 流出 → accepted read 的散文按「已流式不可擦」约束并入信封前缀（`speech_parts.append`）→ 过程话被永久持久化。根因是 **speech 语义契约缺失**：系统只有一个 content channel、一个账本，唯一区分是 rejected vs accepted，没有 process vs settled 维度。同时 prompt 内部存在两组冲突：`_read_tools.j2` 的「do not narrate the lookup」从句对抗不了 SPEECH 段的最高位禁令；duty ③ 让 Chat 指向 Start 与 ADR-070「dock pill 是确认拍唯一座位」重复。

**Decision**:

1. **read 静默律（G1，最小正确修复）**：SPEECH 契约 = 「speak first, then call the **TERMINAL** tool; before a READ tool say nothing at all」。read 迭代的 liveness 全部由 inspecting 相位帧承担（`on_tool_call` name-known 帧的既有座位）；过程叙事（'I'll pull…'/'Let me check…'/'I'll inspect…'）= banned speech。**`speech_parts` / ToolLoop 账本一行不改**——过程话不再流出，「已流式不可擦」约束不再被触发，账本自然无害化。两个 loop 面（`intent_router_system.j2` / `chat_intent_system.j2`）+ 共享 `_read_tools.j2` 同律。
2. **语义角色而非句式（维持 ADR-083 意图）**：present_plan 的 echo 定义的是 semantic duties（素材判断 → 用户意图 → 完成标准+下一步），不是机械句数；本条不新增模板。
3. **grounding 两态诚实**：「理解用户需求」和「已读用户素材」是两个不同的事实，永不混淆。素材内容本回合不可读（仍在处理——read 明说或上下文无文本）时，duty ① 不退化为沉默，而是变成**一句诚实短句**：我理解了你想要什么、内容读取在处理完成后落地、计划先按你自己的话起草。四级证据链（ADR-083 判词 2）不变。
4. **Start CTA 归属**：≥2 task 的 task_book 回合，Chat 永不邀请言语确认——no 'say the word' / no 'just say start' / no 'tell me when you're ready'；duty ③ 最多一次性平指 dock 的 Start 按钮。Chat 可以解释 Start 的意义，但不拥有 Start 的交互职责（Canvas = 结构，Chat = 理解+简述，Dock = 唯一 Start 动作）。单任务无按钮分支的会话式确认（DENSITY 律）不变。

**明确不做**：不给 `speech_parts` 加 process/value/settled 三角色（harness 层过度修复——prompt 一句话能解决的事不变成机制）；不动 trigger writer（ADR-080 单一叙事者维持）；不动 Canvas；不改 ToolLoop 代码；单任务会话式确认不波及。

**Consequences**: 最终消息只承载三类用户价值言语——「我理解了什么 / 我准备做什么 / 你需要决定什么」；内部执行状态（调用哪个工具、拼几个 task）归 transient 相位帧，永不入持久消息。Interaction Integrity 推进一步：**不是所有真实发生的内部状态都要展示；但展示给用户的每一项状态都必须真实且有用户价值**。回归面 = chat_scenarios S20（A 部未就绪：read-silent 流式空读 + 处理中披露 + 过程话负向标记；B 部就绪：grounded 内容词代理断言 + ≥2 task 无言语确认邀请 + 流式律）。prompt 面改动过 prompt gate（ADR-071）。

**Related**: ADR-083（信任锚 echo——grounding 链与注入机制不动）/ ADR-080（单一叙事者——trigger 静默维持）/ ADR-070（确认拍 = dock pill 唯一座位）/ ADR-077（工具 loop——read 静默律是其言语账本语义的契约层补全）
## ADR-085: 一回合多交付——Phase / Checkpoint / Settled 三层用户可见交付模型

**Status**: **Implemented** (2026-09-17)；机制有意 opportunistic——checkpoint earned 不配额（判词 3），主路径单读直出时结构性零 checkpoint 是设计不是缺陷（见 Consequences）

**落地座位**：路由规则在 `tool_loop.py` 的 observation 分支（quiet 迭代 + eligible 前驱 + 另一条 read → `on_checkpoint`，≤2 闸，超出丢弃记日志；iteration 0 豁免 = 违规回退账本；无通道 = 账本兜底）；资格声明在 `perception/__init__.py`（`checkpoint_eligible`：get_understanding / get_asset / get_craft_skeleton 三席）；持久化在 `service._checkpoint_callback`（`intent={"type":"checkpoint"}` 行，flush-only 随回合一次 commit）；SSE 帧 `assistant.checkpoint` 在 `routes.py`；前端分段在 `ChatDock`（`typeTargetId` + `checkpointChain` 串行化，streamId 主泡不动）；言语语义在 `_read_tools.j2`（CHECKPOINTS 段：结果陈述 = 唯一例外，终答必须独立成文不复读）。确定性回归 = `test_tool_loop_pure.py` 五条路由用例 + `chat_scenarios` S20B opportunistic 形态断言。

**Context**: ADR-084 关掉过程话之后，「机械感」的结构性根因完整暴露：当前系统只有两个用户可见座位——transient 相位（「在做什么」）与 settled 终答（「最终怎么做」），中间缺了「**我刚发现了什么**」的交付座位。审计坐实 Turn ↔ Message 的 1:1 绑定是**产出契约层**的实现便利而非产品必需：first binding = `LoopResult.prose: str` + `PlanTurnOutcome(Message)`（tool_loop/plan_turn），前端对应物 = streamId 一键一泡；DB（messages 无 turn 分组，assistant 行数无约束）与 SSE（`_sse_pump` 多路复用，`question.preview` 是回合中途结构化帧的现存先例）都不是瓶颈。缺少 checkpoint 座位时，读到的有价值结果只有两个去向：并入终答（ADR-084 已禁的前形态）或退化成无内容的相位标签——「看不到它在干活」与「听到它念操作日志」是同一个缺口的两副面孔。

**Decision**:

1. **三层交付模型**：一个用户回合可以产生多个有意义的 user-facing deliveries——**Phase**（我现在在做什么：transient，相位帧，不落库，被下一相位替换）/ **Checkpoint**（我刚发现了什么：grounded judgment，留在消息流）/ **Settled**（基于发现我最终准备怎么做：terminal，唯一终态消息）。Checkpoint 不是 chain-of-thought：它 = 真实动作 + 真实结果 + 用户价值，永不携带内部推理。
2. **`on_observe` 是允许边界，不是生成器**：checkpoint 的真实链路 = ToolObservation → 下一轮 LLM 迭代判断「这个结果值得告诉用户」→ 生成 checkpoint prose → `assistant.checkpoint` 帧。checkpoint 必须是 grounded judgment（同一 ADR-083 证据层级），永不是 raw tool output 的搬运。
3. **Registry 声明资格，不声明触发**：感知族工具条目带 `checkpoint_eligible`（get_understanding 级 ✅ / get_asset 级 △ / 目录浏览族 ❌），最终是否产生由「是否产生新的用户相关信息」当场判定（同回合重复读取同内容 = 不新 = 不说）；每 turn ≤2，**earned，不是配额**——纯 answer 回合的正确 checkpoint 数是零。
4. **Checkpoint 落库，且带显式语义类型**：checkpoint 行与普通 settled assistant message 分开（明确 kind/语义标记），四项目标——刷新可恢复 / future context 可选择性读取 / replay 不把 checkpoint 当最终回答 / trigger_review·checkpoint·settled 三语义分家。是一回合多**交付**，不是一回合多**assistant 行**。**持久化语义**：checkpoint 是 **live delivery，不是 durable delivery**——落库 flush-only 随回合一次 commit，回合中途失败则已展示的 checkpoint 随事务回滚（刷新后消失）。**不为此扩大事务模型**；若「已交付事实随失败消失」伤信任被证实，中途 commit 的评估是一条新 ADR。
5. **Harness 路由机制（ToolLoop 内核不动）**：非终态调用前的散文 = checkpoint 候选（走新通道，**永不入 `speech_parts`**）；终态调用前的散文 = settled speech（账本现状不动）。iteration 0 的 read 前叙事仍被 ADR-084 禁（无先有 observation，无 grounded 内容可说）——**iteration 0 豁免是 streaming safety 的防御兜底，不是产品行为**：模型违规后不让 UI 坏掉，如此而已（测试面 `test_iteration_zero_prose_stays_in_the_ledger` 锁的正是这个兜底语义）。checkpoint 只可能诞生于 observation 之后的迭代。SSE 侧新增 `assistant.checkpoint` 帧（`_sse_pump` 既有队列直过）；前端 stream key 从「一发送一键」变「一键一段」——checkpoint 帧 finalize 当前泡并开新泡，帧携带完整文本走打字机节拍（安静迭代零 delta，打字机律最后闸门同形适用）。

**明确不做**：不改 ToolLoop 的 terminal/max_iterations/账本语义；不展示 raw reasoning / 候选方案 / 概率；不为每个 tool 发 checkpoint；不恢复多 writer（ADR-080 维持）；不引入新 execution architecture（ExecutionAttempt / 新 Agent 状态机 / Media IR / 新里程碑）；不把 registry 变成产品规则系统（只声明资格）。

**Consequences**: Chat 从「一个会生成漂亮答案的聊天框」变成「能看到它在干活的 Agent」——用户看到的是有意义的工作进展，不是内部思维日志。caption 场景理想序列：User → [Phase] 正在读取素材 → [Checkpoint] 我看到了——关于 X 的演讲，核心是 Y（grounded in understanding）→ [Phase] 正在整理计划 → [Settled] 两版字幕：中文双语 + 法语，计划在画布上 → Canvas 结构 / Dock Start。Interaction Integrity 的最终形态：**不是所有真实发生的内部状态都展示；但展示的每一项都必须真实、有结果、有用户价值**。checkpoint 的验收问句：**「这条消息是用户刚刚真的需要知道的信息，还是系统只是想证明自己做过某个动作？」**——前者过，后者禁。**已知风险与验证义务**：路由规则要求「结果陈述后再跟一条 read」才出 checkpoint，主路径 `get_understanding → present_plan`（单读直出）**结构性零 checkpoint**——判断句由终答的 duty ① 承载（ADR-083），这不是缺陷；但如果实测发现 earned 条件在主路径上**系统性过低**、理解锚沦为偶然体验，则重审路由（候选：显式 checkpoint 工具 / 终态前分流），那是一次新评审而不是静默扩闸。命中率数据面 = `tool_loop_checkpoint` structlog（含 predecessor）+ **`tool_loop_turn` 每回合一条汇总**（reads 序列 / eligible_reads / checkpoints / outcome——eligible 占比、eligible→checkpoint 转化、checkpoint→settled 三比例及「哪类 read 真挣到 checkpoint」全可算）+ `chat_scenarios` S21 探针（四场景 PRINT read 序列与 checkpoint 计数，只锁硬律不锁出现）。资格纪律：`checkpoint_eligible` 永是资格不是触发；「信息生产 vs 动作证明」的判定永远归 new + user-relevant + changes understanding。回归面 = chat_scenarios S20B/S21 + `test_tool_loop_pure.py` 五条路由用例；prompt 面改动过 prompt gate（ADR-071）。

**Related**: ADR-084（read 静默律——read 前静默不动，read 后的结果言语走 checkpoint 通道）/ ADR-083（信任锚——checkpoint 的 grounding 层级同源）/ ADR-077（工具 loop——checkpoint 是其呈现协议补全，内核不动）/ ADR-080（单一叙事者——checkpoint 不引入第二 writer，它仍是同一 turn 的言语）/ ADR-070（确认拍 = dock pill——Settled 层的 Start 归属不变）

## ADR-086: 拓扑空间权威三律 + Product Canvas ≠ Execution Graph——Product Flow Alignment 的架构地基

**Status**: Decided (2026-09-18)；施工合同 = `docs/tasks/product-flow-alignment.md`

**Context**: 画布「线往回走」的取证结论不是 edge routing 问题，是**拓扑与帧已不一致后的视觉症状**：深度-间距律只在节点出生执行一次、既有帧永不移动（append-only 保序律），而晚出生的中间节点（翻译/配音两站 doc 伴侣）、边对账、pitch 漂移（迁移 436 vs 现行 464）、空帧前端 `{0,0}` 静默兜底、读时合成边五个来源各自制造 `target.x < source.x`。加重发现：`RunOp` 按 `(layout.x, layout.y)` 排序 run_nodes——**视觉坐标被当作执行依据**，帧错位可让修订 run 把消费者排在生产者之前。用户判词：「Product Canvas 被执行图的历史设计污染了」；「不要把呈现层重推实现成临时视觉补丁——topology / semantic stage 必须明确定义成 layout projection 的上游依据」。

**Decision**:

1. **Product Canvas ≠ Execution Graph（追认 + 准入闸）**：画布节点 = **用户拥有、消费、验证或可能修改的产品对象**——含最终产物与可编辑中间工作产品（transcript / 翻译文档 / 分镜表 / 字幕文档 / 渲染视频等，ADR-072 词表 v3 为词汇基线），永不是纯执行步骤；`task_book / preprocess / understand / plan / materialize / render / verify / queue / retry` 类概念永不上画布。现行 read-face 机制（B1-lite 过滤 / B4-lite 收编 / `_read_face` 映射 / workflow_steps 永不成画布节点）追认为本律的执行机制，不是临时补丁；**新增图节点类型 / spec.tool 必须声明 product visibility，默认隐藏**。「不是最终产物」永不是隐藏理由（分镜表先例，ADR-072）。
2. **拓扑/语义 rank 是唯一空间权威，frame 是呈现 projection**：一切用户可见位置的上游 = Product DAG 拓扑（rank = 拓扑深度）。**rank 的输入边界**：只消费表达生产/消费关系的语义边（含读时合成边中表达真实物料流的 A3-lite 边）；历史血缘、跨 run 关系、纯呈现边（lineage / historical / presentation-only）**不参与** rank——ADR-036 的 lineage/dependency 区分是本法母体。`graph_nodes.layout` 帧 = **y 座位 / w·h 预留 / 稳定锚**三职；x 的显示值 = rank 投影，服务端出生帧的 x 不再是显示依据。**方向不变量**：一切用户可见 edge 满足 `rank(target) > rank(source)` 且渲染 `x(target) > x(source) + MIN_GAP`；sibling 序稳定；不依赖 birth order。append-only 保序律对 y/稳定锚维持（ADR-036 维持）；**服务端帧零改动、存量零迁移**（呈现层修法，ADR-082 判词① 先例）。**「零迁移」≠「legacy 图一概不碰」**：旧 frame 不迁移（projection 消化），旧 edge 按 ADR-062 边对账律正常自愈（该 retract 的 retract），旧 node 按 read-face 既有规则判断。
3. **Run order = DAG topology，永不读 layout.x**：`RunOp` 排序改读图边拓扑深度（与 rank 同一事实源）；`graph_revise.py`「x 序 = 深度序」假设删除。执行顺序与视觉坐标解耦——二者共享同一 Product DAG，视觉坐标永不做执行依据。本项触及执行面，施工必须带 regression scenario（R1 执行 invariants I-EXEC-01~04 不动）。
4. **生长 = 呈现编排，节点语义一次 stamp（K5 维持）**：ADR-057「图先展示后运行」维持——计划确认前用户看到完整链 + 逐节点估价是 fold 报价前提。「动态生长感」由出生编排（深度序 reveal）+ 节点原地状态迁移（draft → running → done）承载；loading → ready 是同一 node 更新；不把内部 execution task 逐个变成画布节点；不为生长感让服务端 drip-feed。

**明确不做**：不重写 edge routing（贝塞尔 / 端口法则 / 出入锚保留——错误的语义布局不用漂亮的线补锅，反过来也不为排线改拓扑）；不用 clamp / 翻转 edge / 固定 x-y hack 掩盖拓扑；不迁移存量帧、不引 dagre（ADR-036 判词维持）；不把 SSE 做成事件总线（节点状态 = `step.updated` → graph refetch 既有模式）；不动 ADR-084/085 / 打字机律。

**Consequences**: 布局算法的输入从「出生时刻的拓扑快照」改为「当前 Product DAG 的 rank」——帧错位五源（L1-L5）的视觉症状结构性消除；执行序与呈现解耦后，「帧错 → 执行错」的污染链断掉；Product Canvas 的边界从约定升级为带准入闸的 invariant。空帧处置细则：出生地保证每行必带合法帧；前端静默原点兜底删除——dev 显式失败 / prod graceful fallback（fallback = rank 投影，不是原点）。

**落地座位**：契约模块 = `app/pipeline/product_graph.py`（pure）——判词 1 的准入闸落地为 type 层 membership 谓词（媒介五值可见 / `HIDDEN_ROLES` / `LEVER_TOOLS` 两显式枚举 / 未知 type default-deny，等效机制）；判词 2 的 rank = `product_ranks`（longest-path，rank 边集 = `{video, audio, text}`，ctx 引用流排除）；判词 3 的消费点 = `topological_order`（与 rank 同一事实源，RunOp 接入）；canonical fixture = `apps/api/tests/test_product_graph_pure.py`。legacy `materialize` 行的读面可见性与谓词不一致 = 已知残留（合同 §12 D-PFA-01，随历史清理收编）。

**Related**: ADR-036（布局自算 + append-only）/ ADR-057（图即产品对象——判词① 的母体；K5 维持）/ ADR-062（边对账律——对账不再依赖帧一致性）/ ADR-067（出锚语义律——「呈现忠于语义」同族）/ ADR-082（呈现/语义隔离铁律 + 呈现层修法先例）

---

## ADR-087: Agent Interaction & Product Lifecycle Architecture——三条语义层 + Lifecycle / Activity / Confirmation 三合同 + 依赖方向冻结

**Status**: Decided (2026-09-19)；施工切分 = Phase 1~6 简报 `docs/tasks/lifecycle-phase-1~6-*.md`，批次登记 = PROGRESS §0.2

**Context**: 九轮只读取证 + Architecture Fitness Audit 的终判（等级 **B——骨架正确、边界重划**）：Agent Runtime / ToolLoop（有界 loop / terminal 语义 / hooks）/ Write Gates（图双门 / run 单出生地 `create_run` / operations 单门）/ DB-state-driven dispatch / Application Command 层的事实存在 / Product Domain / Product Graph / C-0/C-1/C-2 / Execution Runtime / 双引擎分离 / SSE 通用 transport 全部健康，**禁止因 UX 问题重写**。真正的结构性缺口是 **Product Lifecycle Projection 唯一真缺**——生命周期事实由 dispatch 谓词、trigger 双谓词与客户端多处推导代偿（plan pending ≥4 权威、素材就绪 ≥7 站点、Plan Ready 0 权威）；Presentation 向上越位（artifact existence → lifecycle 推导、turn.completed → Canvas）；Agent 中间事件丰富却被压扁成单槽 last-write-wins 状态行（>0 迭代 15–25s 只有心跳的盲窗）；确认教义存在路径分叉（propose path 直起 run、caption 双标、G-explicit 自动 Start）；docs 层 12 对矛盾条款与 10 组命名冲突。本条把已冻结的架构合同一次落档——允许重划的只有六处：Lifecycle Projection（新建）/ Activity Projection（新建）/ Presentation Contract（归位）/ Confirmation Doctrine 统一实现 / chat↔pipeline 依赖方向 / docs canonicalization。

**Decision**:

### 1. 五条 Architecture Principles（冻结）

1. **Agent execution、Product lifecycle、Presentation 是三个不同问题**，必须由三个不同语义层回答。
2. **Lifecycle 是服务端命名的只读投影**；Presentation 只能响应 Lifecycle，不得从 artifact existence、Agent event 或客户端推理恢复生命周期。
3. **Activity 是 Agent 工作的用户安全观察流**；是可见性机制，不是生命周期权威，也不是 Tool Log。
4. **Agent proposes → Application Commands → Domain decides**；新的 Paid Work 必须经过统一 Confirmation Doctrine；已确认 Scope 内的 continuation 可以自治。
5. **每个产品概念只有一个 canonical definition**；代码、Transport、Prompt、Frontend 和 Docs 都只能引用该定义，不得另造语义。

### 2. Lifecycle Contract

服务端命名事实；**plan-scoped**；只读；唯一 lifecycle authority。

- **PREPARING** = 计划形成 / 材料处理阶段（默认态）。
- **MATERIAL_READY(P)** ⇔ 计划 P 引用的资产全部 COMPLETED ∧ 无 FAILED ∧ 链所需内容事实就位（text 链需非空 transcript；transform 需已知语言）。**相对 Plan P 的谓词，不是 project-global flag**（门控资产集 plan-scoped：pinned exemplar 非源时排除）。
- **PLAN_READY** ⇔ unanswered task_book exists ∧ MATERIAL_READY(P) ∧ chain 针对当前事实重新裁决通过（复用 `validate_task_list` + 同语裁决——纯函数已存在，缺的是调用不是能力）∧ 无挂起前置提问。
- **CONFIRMATION_READY** ⇔ PLAN_READY ∧ 确认信息完整 ∧ 对 Paid Work 费用语义已披露（§2.1）∧ 无活动 run。
- **RUNNING** ⇔ 活动 run 存在。

**固定不等式（入册）**：

```
Material Exists ≠ Material Ready ≠ Plan Ready ≠ Confirmation Ready
turn.completed ≠ PLAN_READY
present_plan ≠ PLAN_READY
task_book exists ≠ PLAN_READY
activity.completed ≠ PLAN_READY
```

estimate completeness 不是 PLAN_READY 必要条件。允许 **PLAN_READY=true ∧ CONFIRMATION_READY=false**（如估价进行中：Canvas + pill 可见，Confirm disabled）。

**Presentation 映射**：PLAN_READY → Review Surface（Canvas + Confirm Dock 出现）；CONFIRMATION_READY → Confirm action enabled。**Canvas 与 Confirm Dock 是同一 lifecycle 状态的两个 presentation effects，不是两个独立 readiness predicates。** 移动端 parity：无画布形态下 plan card 是评审面（已发货形态），同一投影戳驱动，不另造谓词。

#### 2.1 费用语义就绪（Charge Semantics Ready——衔接微合同）

CONFIRMATION_READY 的「费用信息可见」≠「所有节点 estimate 非空」。ADR-063（编译期 NULL 估价合法、「估价随运行」）**保持有效**——本条只定义确认就绪的费用披露标准，不改变「估价可随运行确定」的合法性；Lifecycle 表达产品阶段事实，不强迫下游 Runtime 提前产生它还没有能力产生的事实。对 Paid Work，CONFIRMATION_READY 要求**计费语义已经完整披露**：

| 面 | 含义 |
|---|---|
| **Known** | 当前可得的精确 / 估算费用事实已知 |
| **Deferred** | 当前无法计算的部分：不确定性、确定时点与计费规则必须明确标注 |
| **Conditional** | 费用取决于什么条件必须明确 |
| **Held** | 预留 / 冻结（hold）语义必须明确 |
| **Actualized** | 最终扣费发生在什么时点必须明确 |

禁止「价格以后再说」——Confirm 之后才浮现任何未披露费用的形态永禁（`Confirm → 后台才发现还有一部分收费` 是本合同真正禁止的事）。「必须全量估价才能 Confirm」是独立的未来产品 / 商业策略决策，**不在本合同内**。

### 3. Agent Activity Contract

唯一产品目标：**让用户持续感知 Agent 正在为其完成什么工作**。Activity ≠ Chain-of-Thought ≠ Tool Log ≠ Product Lifecycle ≠ Presentation Lifecycle。

标准链：`Internal Agent Events → Activity Projection → User-safe Activity Events → Activity Stream → Chat Activity UI`。**Tool execution event 不直接进入用户 UI。**

对账规则（十条，冻结）：

1. 每个用户可见 Activity 必须可追溯到一个或多个内部执行事实；
2. 内部事件可被过滤 / 聚合 / 折叠；
3. N internal events → 1 Activity 合法；
4. 1 internal event → 0 Activity 合法；
5. 稳定 identity + deterministic ordering（activity_id / sequence / status / semantic_key）；
6. 显式生命周期 started → completed / failed / cancelled；
7. 永不作 Lifecycle authority；
8. 永不直接控制 Canvas / Confirm / Run；
9. 词汇单一 canonical owner（出 Tool Registry / Prompt / Service）；
10. 对 Domain / Lifecycle 只读。

Stream 语义：回合内 **append-oriented**，非 last-write-wins；至少表达 active / completed / ordered history；不要求持久化与回放；长执行 / 多 iteration 不得再产生无界盲窗（>0 迭代 15–25s 只有心跳）；发射节奏是实现细节，不是架构合同。

**draft 类活动落定即消失**：draft 跨度（present_plan / propose_tasks / edit_graph / revise_output / edit_output）只在 active 态存在（now-line 的活进度）——落定帧骑 live wire 但**永不持久化、永不入流**；方案卡 / run 收据即落定证据，无空心收据行（「方案整理好了」「改好了」）；回放旧日志由时间线读面过滤（`isDraftSpanRow`）；无 draftDone/editDone i18n 键。

**三概念分家**：`phase` 保留，但定义为 **System Status**（宏观态）——System Status = 系统处于什么大状态；Agent Activity = Agent 在做什么工作；Assistant Conversation = Agent 在对用户说什么。phase 不再是 Activity container。

绝对约束：**SSE 打字机律不可破**——活动帧与散文打字机节拍共存，任何改动不得让散文整段瞬移（CHAT_ARCH §8.6）。

### 4. Confirmation Doctrine（禁止重新解释）

核心：**自然语言请求 = Task Intent ≠ Paid Execution Authorization**。

标准路径：`Task Intent → Preparation → PLAN_READY → CONFIRMATION_READY → Explicit Confirmation → Paid Run`。

- **明确禁止 G-explicit task request = paid gesture**：即使用户明确指定输出类型 / 语言 / 数量 / 范围 /「直接帮我做」，仍只是明确 Task Intent——可减少澄清、直接成 Plan，不得绕过 PLAN_READY → CONFIRMATION_READY → Explicit Confirmation。
- **Existing Approved Scope（可自治）**：retry / internal repair / render continuation / execution step completion / approved-scope graph revision。
- **Scope Expansion（必须重新 Confirmation）**：新增未确认付费输出 / 新增付费分支 / 超出已确认范围。**范围包含性由 Application Command 层代码裁决，不是 LLM 自决。** **Resulting-scope 分类律**：continuation / expansion 的判定对象 = 操作施加后的**结果付费执行范围**（requested ops → resulting graph/execution closure → resulting paid outputs/branches → 与已批准 execution scope 比对：same = 自治 / expanded = Confirmation Dock / unproven = Confirmation Dock），不是操作名——`delete_node` 本身不是产品语义；精确历史 scope 比对能力缺席时按 unproven 处理（「delete+run 精确历史比对」= 后续 domain capability 挂账，不以拍脑袋规则完成）。
- **Caption/Non-caption Parity**：caption 特殊性仅限参数收集 / 前置提问 / 模式与语言格式选择；不拥有独立 Paid Authorization 语义。
- **Estimate**：不阻塞 PLAN_READY；但 Paid Work 的 CONFIRMATION_READY 要求 scope 完整 + 费用语义披露（§2.1）+ 用户拥有足够信息做决定。**Paid Run MUST NOT begin before charge semantics disclosed ∧ explicit confirmation accepted。**
- **统一 Paid Authorization path**：plan path 与 propose path 可以拥有不同的 Agent preparation path，但**不得拥有不同的 Paid Authorization path**。正确目标：所有新 Paid Work → 统一 Confirmation-ready Product State → 统一 Confirmation Dock。**消灭的是路径分叉，不是新增一个「propose dock」UI。**
- **确认 scope = 卡载荷**：ConfirmationScopeReady = 链非空 ∧ 结构合法（tasks/brief/estimate——payload 字段级盘点）；计划散文不是 scope 事实、是叙事装饰——空散文 dock 可确认（`present_plan` 空 content 通道是 LLM 合法形态）。
- **客户端 tasks ≠ 批准证明**：/generate 等 typed 入口的合法 retry 必须由服务端基于既有事实（历史 run context / approved scope / retry 引用）确定性证明；「客户端传了 tasks」「客户端自称 retry」「请求来自 retry 按钮」都不是授权依据。unproven → 不直接 `create_run`，转 Preparation / PendingPlan / Confirmation Dock；legacy typed Start fallback = unproven legacy path——同样转 Dock，无旁路。
- **Start 服务端确认强制**：`answer_question(kind="start")` 进入 paid `create_run` 前由服务端验证（confirmation scope valid ∧ charge semantics ready ∧ no active conflicting run ∧ plan/material prerequisites ∧ 计划与确认范围一致）；不满足 → machine-readable blocker，不伪装普通业务错误——「前端按钮 disabled」不是唯一防线。
- **无 `autonomy="review"` 档**：一切正常 Paid Run 默认 autonomous continuation；direction interrupt 是执行中 HITL 不是 Paid Authorization——WAITING_HUMAN / interrupt / verify escalation 基建保留，只无 review 档的 understand→plan interrupt 插入。
- **工具描述 = 行为真值**：`propose_tasks` 只 dock 不起 run；工具描述与系统 prompt 必须与最终实际语义一致——描述在行为落地后变真，不许失信文本。

### 5. Target Architecture

```
                       USER
                        │
                        ▼
                 Agent Runtime
                 ToolLoop / hooks
                   │        │
                   │        └──────────────┐
                   ▼                       ▼
             Tool Interface        Agent Execution Events
                   │                       │
                   ▼                       ▼
           Application Commands    Activity Projection
                   │                       │
                   ▼                       ▼
             Product Domain       Activity Stream → Chat
                   │
        ┌──────────┴───────────┐
        ▼                      ▼
Lifecycle Projection       Execution Runtime
        │                      │
        └──────────┬───────────┘
                   ▼
                Transport
                   ▼
              Presentation
           Chat / Canvas / Dock
```

两投影可消费共同底层事实；互不消费对方输出；**Presentation 只消费 projection**。

### 6. Dependency Direction（冻结）

**允许**：Agent→Tool→Application Command→Domain；Domain→Execution Runtime 委托；Runtime→Events/Domain facts；Events→Projection；Projection→Transport→Presentation。

**禁止**：

- Presentation→Domain internals；
- Presentation→artifact existence 推导 lifecycle；
- Activity→Lifecycle / Canvas visibility / Confirm；
- Tool→Presentation；
- Agent→Product Lifecycle 决定；
- Lifecycle Projection→Domain 写；
- Pipeline→Chat 直接 import（现状 2 顶层 + 6 deferred，改走 trigger 事件缝）；
- Prompt→frontend 渲染阈值；
- Chat↔Pipeline 双向依赖；
- 跨模块私有函数 import（`_asset_digest` / `_check_transform_targets` 等现状违规）。

**跨层回溯只能经过**：event seam / public application command / explicit protocol。**不得再新增 deferred import 来修架构。**

### 7. C-0/C-1/C-2 保护合同

不重新设计。Product Graph ≠ Execution Runtime ≠ Presentation。Rank 是 topology authority；Frame 是 presentation projection；执行序走拓扑（ADR-086 不变）。Canvas edge/anchor routing 不重写。**本阶段一切 lifecycle/activity 改造只在 read-side，不得进入 graph write gate。**

### Non-goals

- 不重写 ToolLoop / Agent / Product Graph / Execution Runtime / SSE 机制 / Canvas edge routing；
- 不把 Product Canvas 变成 Execution Graph；
- 不把 Activity 做成 workflow graph；
- 不把内部 Tool Log 暴露给用户；
- 不一次性拆 ChatDock / service.py；
- 不为目录漂亮移动文件。

### Consequences

- **Lifecycle Projection 座位**：`app/pipeline/lifecycle.py`（纯核 + 装配器，MODULE_ARCH §7.1）；CONFIRMATION_READY 四合取（PLAN_READY ∧ ConfirmationScopeReady ∧ ChargeSemanticsReady ∧ NoActiveConflictingRun，payload-existence 捷径永禁）；素材处理中 Review Surface 不出现、PLAN_READY 同拍出现、CONFIRMATION_READY=false 时 Confirm disabled；客户端零 lifecycle 推导（无 `hasDraftGraph` 族旧谓词）。
- **Activity Projection 座位**：`agents/tool_loop.py` typed `LoopEvent`（内核只说发生了什么）+ `chat/activity.py` 纯投影器（kind 用户语义四值，MODULE_ARCH §7.1）+ `assistant.activity` SSE 帧 + dock `ActivityStream` 组件；相位帧保留（并行渲染），打字机律不破。
- **Presentation Contract 归位**：Confirm/Start 唯 dock pill（无 Canvas Confirmation Seat）；`lib/lifecycleStamp.ts` 三态谓词（stamp missing = unknown ≠ ready，无 fallback-to-true）；confirm/running 两腿由戳派生（`confirmActive = intentReady && isPlanReady(lifecycle) && !runAttached`，无 phase 状态机）；composing = System Status 唯一宏观叙事（住 `app/chat/system_status.py`），永不建相位帧 → lifecycle readiness 正向锁；**「lifecycle 键恒在」不变量**（graph 响应零节点也补戳）；**run 活性/存在是 transport 事实，非 lifecycle 推导**（合法读者在册：ChatDock `runAttached` / `projects.$id.index` `hasRuns` / `runActive`——禁补戳读者）；`render_superseded` 入 `USER_ERROR_LINES`；ChatDock normalize* 族住 `chatProtocol.ts`；无 `_DOCUMENT_CONFIRM_PX` 几何债。
- **Confirmation Doctrine 统一实现座位**：deterministic scope classifier（零 op 词汇纯核 + 装配器）裁决 edit_graph 按 resulting-scope（continuation 自治 / expansion·unproven 转 dock）；`propose_tasks` → Confirmation Dock（同 turn create_run 全路径禁止，`_dock_plan_as_question` 唯一 dock 座）；/generate server gate（exact/family 两级 retry 证明，不可证 → machine-readable 422 `scope.unproven` 先于余额检查）；Start 服务端四合取（`evaluate_start_gate` + 机器可读码，dock pill 与散文确认同一座）。施工合同 = `docs/tasks/lifecycle-phase-4-confirmation-doctrine.md`。
- **依赖方向座位（四族合法缝，§6 唯一通道）**：① trigger fires（understanding_warmed / run_completed / craft_decompiled）→ `pipeline/trigger_events.py` 白名单事件缝（白名单冻结，扩名单 = ADR 评审；fire-and-forget 未注册 = 静默降级永不 pipeline 失败；`app.main` / `app.worker` 两组合根双注册）；② 同步会话写四命令（dock_interrupt_question / finalize_bailed_runs / seed_project_prompt / discard_unanswered_plan）→ `pipeline/conversation_bridge.py` 显式 protocol（未注册 fail-loudly）；③ 会话读四助手 → `platform/conversation_context.py` 只读协议座；④ 完整 chat 回合（POST /outputs/{id}/regenerate）→ 端点住 `chat/routes.py`（URL/method/OpenAPI 不变）。`build_context` 住 `chat/context.py`（各层自装上下文）。pipeline→chat import 清零、跨模块私有 import 清零、零新增 deferred import——常驻守卫 = `tests/test_import_direction_pure.py`（AST 双门 + 冷导入探针 + 组合根接线保险 + 自引用改名碰撞扫描）。
- **Hygiene 挂账**：service.py / schemas.py / graph_fill.py 拆分、Message.intent typed union、edit_output operations 路径 commit 律对齐——永不进关键路径，排期见 PROGRESS。
- **新能力机械回答表（验收基准）**：Agent action → Tool Interface；改 Domain → Application Command → Write Gate；用户要看到在做 → Activity Projection；改变产品阶段 → Lifecycle Projection；UI 响应 → Presentation consumes projection。若新增一种能力仍需「新 phase + 新 envelope + 新 ChatDock if + 新 polling + 新 prompt 条件」，说明本合同被破坏——STOP 上报。

**Related**: ADR-057（图即产品对象——Lifecycle 投影的消费面）/ ADR-063（估价诚实面——§2.1 保持其有效性）/ ADR-070（确认拍 dock 唯一座位——Confirmation Dock 的形态基座）/ ADR-072（task_book 节点下线——计划真身各归其位）/ ADR-077（会话层工具 loop——Activity 的内部事件源）/ ADR-080（单一叙事者）/ ADR-083/084（言语语义管线）/ ADR-085（三层交付模型——Checkpoint 是 Activity 的言语族近亲，Activity Projection 不重设计它）/ ADR-086（拓扑空间权威三律——C-0/C-1/C-2 保护合同）/ North Star §3（Agent = Decision Producer——原则 4 的母体）

## ADR-088: Exploration Artifacts & Project Working Loop——探索产物族与 Agent 工作循环

**Status**: Decided (2026-09-22)；母文档 = `docs/JOURNEYS.md` 旅程四；与 ADR-089 双生——本条答「Agent 在 Project World 里生产什么、这些东西如何持续工作」，ADR-089 答「这些产物如何确定性进入执行世界」

**Context**: Phase 0–5（ADR-087）把 Agent Safety Architecture 收口（Lifecycle / Activity / Confirmation / Scope / 依赖方向），验收网全绿——但 Agent Tools 审计证实**能力层缺席**：agent 的工具词表只有执行世界的内部语言（add_node / connect / edit_prompt / task.tool），LLM 沦为 workflow compiler（审计 P0-③）；观察合同 < 行动合同（A-1 程序盲改：prompt 要求基于当前程序合成新程序，context 只给 140 字）；意图表示双哲学（P0-②）。参照系重校准：OriginCut（项目状态连续性 + 证据/精选中间层）与 Claude Code（一句绿灯 → 连续可见工作 → 只在需要用户时停）证明「正在自主工作」本身是产品体验——当前的僵硬感不来自确认教义（付费边界两家一致），而来自 agent 没有可见的工作对象与连续的工作循环。旅程四逐拍模拟（11 拍，JOURNEYS）从真实任务倒推出本组裁决；拍 6/9 压力测试证明既有合同（确认教义 §4 / scope classifier D4 / draft 图 K5 / dock 唯一座 / trigger turn / 打字机律）全部原样承重，零推翻。

**Decision**:

### 1. 北极星与主循环重定义

**Agent 的主循环不是 Run，而是围绕 User Goal 在 Project World 中连续产生、检查、演化用户可理解的工作产物；Paid Run 是这条连续工作流里的一个授权边界，不是产品主循环。**

> Agent continuously produces and refines user-meaningful project artifacts; it does not compile or directly execute workflow internals. Paid execution begins only at the confirmed scope boundary.

「Agent 开始工作」≠「Paid Run 开始」——与确认教义 §4 的准备阶段同义，本条从用户体验侧立。

### 2. 探索产物族（Exploration Artifacts）

三个 canonical 对象，均为**证据容器**：

- **候选集 Candidate Set**：主题检索的证据集合；成员 = `{asset_id, start, end, excerpt, speaker, duration}`，每字段可回溯 transcript。**R1 粒度律**：合集 = 一个 artifact（默认折叠、可展开）——画布可见粒度服务于「用户纠正 Agent」，而非复刻 agent 内部操作数量；独立铺卡永禁（画布密度律）。
- **精选 Select**：候选的定版；**R7 = 证据引用**（指向源片段，不复制源）；**R3 理由 = artifact 属性**（verdict + 一行用户安全结论 + 证据指针）——**判断的输出是属性，产生判断的私有推理过程永不成为产品状态**（reasoning 永不持久化，CoT 闸不变）。
- **内容方案 Content Plan**：一个 Select 的内容化方案（source range / 产出要求 / 语言 / 字幕 / 文案 / persona 引用）。**R8：Content Plan ≠ Task**——它描述「我们准备怎么把这个内容做出来」，Task DAG 描述「Execution Runtime 执行什么」（编译关系 = ADR-089 §2）。**R9：persona / presentation 默认在 Structure 阶段注入**，不参与候选评估（除非用户目标点名）。
- **完整性自检**：plan 就绪前经确定性完整性检查（区间 / 语言 / 产出类型 / 必填输入）；artifact state `draft → ready`。

### 3. 双状态机（R10 / R17 / R18）

Artifact 状态机 = `draft → ready → revised → compiled → superseded`；Execution 状态机 = 既有（draft → running → done / failed）。**修订发生在哪个语义层，决定哪台状态机变化**——craft 修订（购买信封内的 how）plan 状态不动；plan 级修订（what 变）才走 `compiled → revised`。**R18 同框纪律**：两族可同框展示，**永不共享状态语义**——plan 节点永不镜像 running（`ContentPlan.status = running` 永禁）。

### 4. Project Artifact Graph 居住律（R13 / R14 探索门半边）

探索产物住持久图（`graph_nodes` 新族，prototype 第四值 `exploration`，NAMING 注册）——零投影律（ADR-057）与项目删除级联统一。**I-EXPLORE-01（不变量，纯测试锁）**：

> **Exploration artifacts MUST NOT participate in execution topology, execution closure, quote/rank calculation, or media-flow edge semantics.**

plan → compiled chain 的链接 = **spec 引用，永不是 Graph Edge**（边词表保持媒体流纯洁：video / audio / text / ctx）。**探索写门**：免费但仍是真写门——事务（savepoint）+ 证据校验（start < end、不超素材时长、与 transcript 有交集）+ 回合幂等；agent 永不直接写图（终态工具 `propose_candidates` / `propose_selects` / `propose_plans` / `revise_plan` 经 Application 层落门）。

### 5. 免费探索区连续性（R2）

探索区（检索 / 评估 / 精选 / 结构化 / 自检 / 编译 / 报价）**默认连续工作，不在拍间停**——**纠正成本对称性决定停顿位置**：免费区纠错便宜（chat 一句插话），故免费区不停；「先给我看看候选」= 作用域暂停指令，逐消息生效。停顿的唯一合法位置 = ADR-089 §5 停顿定律。

### 6. Work Session（R5）

Runtime 可以是多回合的（链式回合 + trigger turn，机制 = ADR-077 §3 既有），**用户体验永不暴露 runtime 回合边界**——一个 goal 的工作 = 一个连续 work session 的 Activity 视图（阶段标签随拍迁移，不按回合替换块）。呈现规格见 JOURNEYS 横切 §6（活动行 = 散文段间穿插的证据行）。

### 7. 阶段化 Observation（R11）

agent 的上下文 = **当前 action 所需的 Project View**，不是一次性 context dump——每拍只取相关切片（Goal / 相关 artifacts / 证据 / 能力目录）；历史旅程 = 摘要行 + 按需 read（§10 读取律）。read 族 = `get_node` / `get_pending_plan` / `list_runs` / `get_artifact`——观察合同 ≥ 行动合同。

### 8. Reviewer 合同（R21 / R22）

run 完成触发回合的 reviewer = **确定性执行验证 + 已批准 plan 的意图兑现检查**（时长 / 字幕存在 / 溢出 / 配音 / 区间 / 产出类型——spec 与证据比对，**不是看片**）；**主观内容质量（「够不够精彩」）永不伪装为系统可验证事实**，归用户纠正。修复半径 = Approved Scope 内 retry / internal repair（教义预授权）；**scope 外 = 建议 pill 唯一出口**（R22）。深度看片复核挂 PROGRESS 需求池。

### 9. 发现型路由（R6）

探索链只服务**实现空间未定的发现型目标**（「找最好 / 挑 / 哪些」类语义）；范围清晰的干脆请求（「加中文字幕」）走既有短路径——**「更智能 = 所有事情都探索」永禁**。判定归 intent router（prompt 面改动走 prompt_gate）；干脆请求在新世界 = Content Plan 的零探索退化形态（ADR-089 §8 统一词表）。

### 10. 项目记忆（R23~R26）

不是「Memory Feature」，是 **Project World 的事实分层与 Agent 的学习边界**：

- **Tier 0 资产事实**：transcript / understanding / craft skeleton（内容寻址，既有法律）。
- **Tier 1 旅程产物**：候选集 / 精选 / 方案 / 确认快照 / 产物——**事实可复用，判断不迁移**（判断是主题与目标的作用域：「pricing 的完整回答」推不出「募资的好片段」）。
- **Tier 2 显式偏好**：persona brand·voice / 项目默认（既有家）。
- **Tier 3 会话历史**：messages（既有持久化）。
- **永不升格清单**：判断 / 一次性纠正 / transient 工作集 / Activity / reasoning。
- **读取律**：当前旅程按 §7 阶段视图全量；历史旅程 = 摘要行 + 按需 read（context 有界摘要纪律不破）。
- **R24 旅程归属**：每个探索产物携带 `journey_id`（归属属性，**永不成图边**）——画布组织学 / 历史摘要 / 读取律的前提契约。
- **R25 偏好升格律（反专断）**：**Preference promotion requires explicit user authorization; recurrence alone is insufficient.** 纠正确切记为 artifact 事实；升格 Tier 2 只经显式声明或 persona 编辑流；agent 有提议权（「要不要以后都这样？」），**无升格权**。
- **R26 前作 exemplar**：「照上次的样子」= exemplar-derived 参数（ADR-078 第四参数源座位），项目内部前作与外部 reference 同法——**exemplar 是参数来源，不是新业务对象**。

**Consequences**: 迁移弧（ADR-089 §8）：`propose_tasks` / `edit_graph` 与探索流并行 → 证明 → 退役，一刀切永禁。**既有合同承重零改动清单**：确认教义 §4 / §2.1 / scope classifier / Start 四合取 / draft 图 K5 / dock pill 唯一座 / G-1 同座 / trigger turn 白名单 / ADR-058 通道分家 / ADR-069 / ADR-078 exemplar / Activity 十规则 / 打字机律 / persona brand·voice / config 三分流 / C-0/C-1/C-2 / 拓扑铁律（ADR-028）。**认知验收入执行规则**（PROGRESS §0.4 规则 9）：触及 agent loop 的批，DoD 必答「agent 看见了什么 / 内部表示是否一致 / 怎么知道自己对了」——A-1 类盲区不再依赖运气。施工排期见 PROGRESS。

**Related**: ADR-089（双生——执行边界）/ ADR-087（三合同——本条的准备阶段 / 活动 / 确认从其条款生长）/ ADR-077（有界 loop + trigger turn——链式回合机制基座）/ ADR-057（图即产品对象——探索族的家）/ ADR-086（Product Canvas ≠ Execution Graph——同框纪律的母体）/ ADR-028（拓扑铁律——I-EXPLORE-01 保护它而非削弱）/ ADR-058 / ADR-063 / ADR-069 / ADR-070 / ADR-078（通道分家 / 估价诚实 / quote 指认 / dock 唯一座 / exemplar 参数源）/ ADR-052（厚 agent 判词——本条是其产品层的兑现形态）

## ADR-089: Capability Compilation & Execution Boundary——能力编译层与执行边界

**Status**: Decided (2026-09-22)；母文档 = `docs/JOURNEYS.md` 旅程四拍 6/9

**Context**: Agent Tools 审计 P0-③ 实锤：`propose_tasks` / `edit_graph` 把执行世界内部语言（task.tool / add_node / connect / edit_prompt / 媒介五值 / offer·accept / 闭包）直接暴露给 LLM——「LLM = workflow compiler」是能力层缺席的**代偿**，不是 prompt 问题；edit_graph 要求 LLM 具备的知识逐项实证（裸 UUID / spec.tool 注册表名 / typed edge / 环拒收 / run 闭包）全属系统内部。P0-① 实锤：Approved Scope 无出处字段（信任根 = 「曾出生且 context 带 tasks」），哪个 run 是用户确认的不可审计。旅程四拍 6 逼出接缝四问：Content Plan 如何变成 Execution Scope、确认消费什么、quote 凭什么可信、agent 凭什么在这里停。

**Decision**:

### 1. 编译移出 LLM（R12）

agent 的终态词表 = **纯产品语义**（`propose_candidates` / `propose_selects` / `propose_plans` / `revise_plan` / `revise_output` / read 族 / `ask_user` / `answer`）——**workflow compilation 从 LLM 的职责里删除**；`propose_tasks` / `edit_graph` 退居编译器内部（迁移弧 = §8），不再作为 agent 的产品语义语言。验收标准（旅程四拍 9）：agent 全程不见 UUID / wiring op / 媒介五值 / 闭包词汇。

### 2. Content Plan → Execution Scope 编译合同

编译器 = Content Plan × Goal × 注册表 → task DAG 的**确定性纯函数**（`validate_task_list` / 同语裁决复用——「只有注册表合法的链才进 dock」的 B3 先例上移为**只有可编译的方案才呈现确认**）；编译失败 = 域拒绝回环修复（`_loop_echo` 同族座位），确认面永不呈现不可编译的方案。

### 3. 编译器座位（R14 编译器半边）

Application Command 层（审计认出的 de facto 层：dock / Start / `create_run` / scope classifier 一家）。**编译器 = 从一种已合法的世界状态确定性产生另一种世界状态的翻译器，不是第三个写门**——它经既有执行写门发写（`apply_wiring_ops` 唯一图写口 / `create_run` 唯一出生地），自身不新增写特权。

### 4. 决策包与确认出处（R16 / R20，P0-① 销账）

确认面消费 = **方案语义（用户阅读层）+ 编译范围（证据层）+ 费用语义五面（ADR-087 §2.1）**——**用户确认的是 plan，task DAG 是证据层不是阅读层**。确认手势落戳 = **Confirmed Scope Snapshot** 持久化：`{confirmed plans, compiled scope, confirmed_at, confirmed_via, confirmation_id}`——Approved Scope 的证明基材从「run 存在 + context 有 tasks」升级为**决策包的生命周期**（P0-① 事实模型缺口销账；legacy run = 不可证，与 D2 读法一致）。**R20：快照 = 修订路由器**——「plan 2 的字幕」解析为节点集的确定性索引（plan → compiled nodes 映射）；provenance 从审计装饰升格为产品语义修订的基础设施。

### 5. 停顿定律（R15，总纲）

> **Agent stops iff the next act moves money or requires information only the user has; every stop must present a complete, user-judgeable decision package.**（Agent 只在下一步移动金钱或需要用户独有信息时停下；任何停顿必须形成用户可理解、可判断、可执行的完整决策包。）

推论：免费探索区不停（ADR-088 §5）；`ask_user` = 信息类停（同律 b 支）；执行中 direction interrupt = 同律在执行侧的投影；确认拍 = 付费边界停——**Confirmation = Agent 已经把需要用户决策的付费边界准备好了**，不是「Agent 做完了所以要确认」。

### 6. 修订分类与范围裁决（R19 执行半边）

修订分两语义层——**plan 级**（what 变：`revise_plan` → 重编译 → 重报价 → 重确认）与 **craft 级**（购买信封内的 how：`revise_output` → 编译为 wiring op → 锚定受影响子图，ADR-058 先例）。**唯一判据 = 结果执行范围是否包含于已批准范围**（`new_scope ⊆ approved_scope` → continuation 自治；否则 expansion → R15 停顿）——agent 可提议语义理解（「我理解你想把字幕调短」），**永不自封 continuation**；scope classifier（D4 结果范围律）是唯一裁判，一个字不改。

### 7. 报价站在 artifact 事实上

quote 输入 = Content Plan 具体字段（精确区间 → 时长 → 渲染单位；语言数 → dub 单位；字幕模式；文案条数）——报价从 LLM 提议参数升级为 domain source of truth；**Known / Deferred / Conditional / Held / Actualized 五面披露保留**（ADR-087 §2.1 不动；「plan ready ≠ 一切成本精确已知」边界明文化）。

### 8. 迁移弧与 select_clips 裁决

新探索流与既有 chat 路（`propose_tasks` / `edit_graph`）**并行 → 证明 → 退役**——一刀切永禁；退役扳机 = 旅程四主链 e2e 全绿 + 迁移期无 regression 在册。干脆请求（ADR-088 §9）在新世界 = Content Plan 的零探索退化形态，词表统一。

**修订动词族（迁移弧现状）**：`revise_plan`（plan/chat 双路）/ `revise_output`（chat 专用终态，骑 `_run_wiring_proposal` 同座）/ `revise_selects`（三金钱态）全在册；「修订动词族表达不了的节点级重写」残座复核为**空集**（prompt 消费族节点重写 = revise_output 覆盖；结构性 graph surgery = 能力完备手势缺席）。`edit_graph` 退役扳机 = 全量剧本绿——扳机未扣前并行期继续，零删。旅程三承接面对账表 = 简报 `docs/tasks/agent-working-loop-iter-3.md` §4。

**`select_clips` 存留裁决**：
① **执行世界永不做发现**——发现工作的唯一座位 = chat 边缘 agent 探索链（R6 路由 + 证据 reads + 探索写门）；plan 来源的工作经编译器走 `cut_segments`（Select 证据指针编译期解引用 → 数值区间确定性裁剪），编译器永不编译 `select_clips`（N-56）。② select_clips **保留为旧路（`propose_tasks` 任务链）的执行工具**——它是零探索退化形态在旧路的唯一机制；其退役随旧路（propose_tasks 退役弧 = PROGRESS 需求池挂账「零探索退化形态」）。③ 候选存留面复核：长素材二次裁切 = chat 侧 reads + `revise_selects`（N-58）覆盖；语义连续处理 / execution-time transformation 无在册需求——均不构成保留 LLM 可见性的理由。④ 调用面清单（退役时的机械削除对照表）：注册表 `app/tools/__init__.py` / 节点 `app/tools/clips/node.py` / prompt 面三处（`intent_router_system.j2` / `_specific_instruction.j2` / `_writers_no_material.j2`）/ recipes 预设链与执行侧声明（tracks / morph / orchestrator / lifecycle / derivative_dispatch / decompile / outputs / verify / graph_fill / schemas）/ web 展示键（ChatDock / chatProtocol / i18n / 项目页）。

**Consequences**: 每批过既有门禁（纯 pytest / prompt_gate / 剧本 + PROGRESS §0.4 规则 9 认知验收）。**零改动重申**：执行写门（`apply_wiring_ops` / `create_run`）/ scope classifier / Start 四合取 / 计费三词两层与 hold→capture→release / fencing（ADR-079）——本条不改任何执行世界机制，只改「谁有资格向执行世界递东西」。

**Related**: ADR-088（双生——探索产物与工作循环）/ ADR-087 §4（确认教义——停顿定律是其付费边的泛化；Consequences Phase 4 = scope classifier D4）/ ADR-028（拓扑铁律——编译器是其新兑现形态）/ ADR-055（计费——决策包的费用语义面）/ ADR-058（通道分家——craft 修订的卡面直改先例）/ ADR-079（fencing——执行写不变）/ ADR-057（draft 图 K5——编译产物的画布形态）

## ADR-090: 精确编辑——`edit_output` 受控终态工具 + quote→range 解算器

**Status**: Decided (2026-09-24)；母法 = ADR-088/089 工作循环与执行边界

**Context**: 年底审计量尺（自然语言 → agent 理解 → agent 真做视频活 → **可编辑、可检视、可重跑**的视频状态）结论：Agent 架构冻结，**精确编辑是距最大公约数的唯一缺口**。机制实证齐全却不可达：OP_REGISTRY 21 个 edit ops（`remove_range` / `set_trim` / `set_caption_style` / `set_title` 在册）+ undo/redo/`restore_version` + base_hash/409 乐观锁后端完备，但 **llm_visible=False 全族**——LLM 不可见、前端零调用、editor 路由孤儿。精确编辑请求在野外已到（live 验收：「你能把字幕改成白色吗」——agent 只能绕行「改 persona 皮肤 + 整条 clip 重新生成」，改一个颜色重买一遍生产链）。评审收敛：不是把 21 个原始 ops 暴露给 LLM（ADR-089 P0-③ 同款代偿），是**受控终态工具 + enum kinds**。

**Decision**:

### 1. `edit_output` = chat path 受控终态工具

终态词表扩员（propose_* / revise_* 同族，ADR-089 §1 纯产品语义律的延伸）：`edit_output(target, params)`——target 指认骑 @output pin 与 ADR-069 quote 引用（既有指认族零新增；**pin 恒胜由服务端写门保证**，LLM 的 target 转述只是建议）；**动词由参数形状携带**（`quote` / `seconds` / `style` / `title` 恰填其一，`edit_kind_for_params` 解码——schema 无 `kind` 字段），**MVP 四件**：`remove_range` / `set_trim` / `set_caption_style` / `set_title`；`set_caption_visibility` 延后 P1（与 caption_enabled 计划默认纠缠，先观察前四件的野外形态）。参数 = 产品语义（样式枚举名 / 标题文本 / quote 引文）——**LLM 永不写时间戳、UUID、op 参数内部形状**。chat 源批次在 operations 写门再校验 llm_visible 词表（纵深，非仅 prompt 期过滤）。

### 2. quote→range 解算器（确定性代码）

「把开头那句删掉」的 range 由代码解算：LLM 只给 quote 文本（用户原话引用或产物原文摘抄），解算器 = `locate_span` 既有地基（ASR 词级时间戳 + marker/文本匹配 + 词边界 snap + silence-only pad，`clip_spec.py`）升格为 edit 面服务。解算置信不足 = **域拒绝回环**（never guess——回环话术指认歧义并给出可答形态，R12 编译失败回环同族座位）。

### 3. 写门与台账律不变

edit ops 经既有 operations 机制落账（base_hash/409、snapshot undo/redo 一字不改）；触发的重渲染走既有 render 链——重 PENDING + **镜像步骤同步补登**（ADR-074② 台账律同律适用于 edit 出生地；新增渲染认领源必须登记 MODULE_ARCH §7.2）。

### 4. 范围纪律与路由判据

`edit_output` 只动**产物级参数**（clip-spec 契约内字段族）；结构性 graph surgery = 能力完备手势缺席（ADR-035）；L3 铁律不动（字幕样式仅枚举，不开放自由版式）；plan 级变更仍归 `revise_plan`。与 `revise_output` 的分工——**精确请求路由 edit_output**（请求给定了可机械执行的具体变更：删这段 / 短 3 秒 / 换这个枚举 / 改这个标题）；**开放意图路由 revise_output**（「再紧凑点」类需要重买内容判断的请求）；router 判据 = 变更是否可机械执行，判不准走域拒绝回环，永不猜。

### 5. 计费语义

MVP 四件零 LLM 成本——edit 动作不收钱；重渲染 = render $0（自有基建定价的既有裁决不变）；**edit→render 全程无确认闸、计费偏好不作用于该路径**（$0 路径无闸可落 = 设计非缺口；偏好只作用于付费 run 的 plan-confirm 披露分级）。未来涉 LLM 的 op 族（`set_caption_text` 改写类）按 capture_step 既有座位扣。

**Consequences**: 施工 = 注册表 edit_output 终态工具（loop 终态族）+ 解算器服务化 + 剧本 S 席（精确修订旅程）；**operations 的用户级 undo/restore UI = P1**（REST 面已通；无 `undo_edit` chat 动词）。**认知验收**（PROGRESS §0.4 规则 9）必答：agent 看见了什么（产物卡 + 词级 transcript reads）/ 怎么知道自己对了（解算回声 = 「我把 0.0–4.2s 这段去掉了」的事实句）。验收标准：「把开头那句删掉」「第二条再短 3 秒」「字幕换 karaoke」「标题改成 X」四请求族 e2e 全通且 undo 可回滚（含解算器跨 cue/大小写容忍/未命中拒绝/多义拒绝边界面）。

**Related**: ADR-089（终态词表 / 编译移出 LLM——本条是其词表扩员）/ ADR-088（工作循环——edit 是产物打磨拍的主座）/ ADR-069（quote 指认）/ ADR-058（通道分家——chat 修订唯一意图面）/ ADR-016（clip-spec 唯一契约——edit 的参数域）/ ADR-074②（渲染台账律）/ ADR-091（编辑历史 = work 的 operations 链）/ ADR-092（确认闸复用）

## ADR-091: 产物身份与重跑生命周期——work/version 语义 + 归档不变量

**Status**: Decided (2026-09-24)

**Context**: rerun 的现行语义 = **物理 DELETE + 新 id**（select_clips wipe / derivative sweep / verify 回退三处），取证四个未登记事实：① 产物身份不存活——用户指认的「第二条短片」每次重跑都是新 id，指认/发布/修订的对象随 rerun 蒸发；② **operations journal 连坐蒸发**（`delete_outputs_fk_safe` 级联删 operations）——undo/redo/`restore_version` 机制在而历史不在；③ output_refs 累积死 id（live 证据：18 个引用 15 死）；④ **publication 连坐删除**（已发布产物重跑即丢发布记录）+ 旧 MP4 孤儿无 GC。「修订」在数据层实际是「销毁重建」——与 ADR-088「持续修订用户可理解的产物」的承诺直接冲突。

**Decision**:

### 1. 两身份分离：work ≠ version

**work** = 用户语义对象（指认 / 发布 / 修订 / 历史回滚的锚）；**version** = 一次生产或重跑的物理产物行（文件 / render_spec / quality 的载体）。用户可见语义全部锚 work；version 是 work 的生产历史。

### 2. 重跑 = 归档，不删除

对已交付（用户可见）的产物：rerun 不再物理 DELETE——旧 version 行转 `archived`（读面默认排除、按 id 可读、restore 可换态、**其余写门全 409 不可变**——operations / undo / PUT / regenerate / 定点 regen 同律），新 version 接替（work_id 按位继承）。**operations journal 跟随 version 行存活**（wipe 不连坐，undo/redo/`restore` 对归档行可溯；journal 永不跨 version——新版本从自己的 snapshot 基线起账）；死 id 不再产生。**精确编辑 = 当前 version 内的原地 operation**（render_spec 原地改 + journal +1），**永不产生新 version 行**——version 只由 rerun/再生诞生。**publication 锚定发布时的 version 行**（immutable 快照语义：发布记录指向被发布的那一版，重跑不连坐、不迁移——已发布的形态凝固在当时那版）。

### 3. 例外：生产中途的自我修正不归档

verify 回退的 best-not-last restore 与 run 内重试 = **产物从未交付**的生产内部修正——保持物理删除（未交付无历史权，归档是纯成本）。归档义务从产物第一次对用户可见开始；分界判据 = 产物是否已随 settled run 出现在用户画布。

### 4. 文件与存储

归档 version 的文件保留（回滚能力的物理基础）；GC = 随项目删除级联；存储增量的成本观察挂账（PROGRESS 需求池行），不预设压缩/清理机制。

### 5. 迁移弧与不变量

新写门先行（三处 wipe 点改归档写），读面读容忍（既有死 id 旧数据永不迁移、永不修复）；物理删除保留给项目删除与 §3 例外。实现形态 = `outputs.archived_at` 可空时间戳律（既有 status 列不复用）；本条只锁语义不变量——**交付后的产物历史不可销毁，只可归档**。

**Consequences**: 取证四问题全部入档（①③ 由身份分离结构性消除；②④ 由 §2 直接裁决）。**既有机制受益**：operations undo/redo 从「机制在而历史常亡」变为真正可溯；`POST /outputs/{id}/restore` 跨 version 换态（指针切换，唯一让归档行重回可写的门）。**零改动重申**：run 内生产链（verify 回退 / 重试）的物理删除不动；render 链与台账律不动。

**Related**: ADR-088（工作循环——「持续修订的产物」承诺的身份地基）/ ADR-090（edit_output——编辑历史 = work 的 operations 链）/ ADR-057（图即产品对象）/ ADR-074②（渲染台账——version 的生产事实）

## ADR-092: 计费偏好集成——三档策略持久化 + 确认闸座位

**Status**: Decided (2026-09-24)；现行法：策略 = 纯披露偏好，一切方案 dock 后恒等确认拍（§2）

**Context**: 六环取证：① 偏好 UI ✅（composer CostConfirmControl 三档 always/large/never）但 localStorage-only（自标 UI ONLY）；② 服务端持久化 ❌；③ 策略读取点 ❌；④ 确认闸 ❌；⑤ ChargeFact 已读真台账 ✅；⑥ hold→capture→release 机器真但在 run 出生地单点。结论：不是计费重设计，是**把已存在的偏好接到已存在的机制上**。

**Decision**:

### 1. 偏好升格为服务端设置

`confirm_strategy ∈ {always, large, never}` 落用户级设置（API GET/PUT），`large` 的费用阈值走 configs 公共参数表（ADR-055 参数座位）；前端 localStorage 降级为读容忍回退（未登录 / 接口失败），服务端值为准。

### 2. 读取点 = 计划确认拍唯一座位

策略在 **plan dock 呈现前**读取一次（确认拍 = 既有付费边界停，ADR-089 §5 停顿定律的唯一停顿形态）：`always` → 任何费用强制显式费用确认；`large` → quote total 超阈值才强制；`never` → 不强制（estimate 面照常显示——**显示义务与确认义务分离**）。闸的形态 = 既有 task_book dock estimate 面的强制档升格（强制档要求一次显式确认手势，非新 dock 类型），具体交互归施工简报。

**口头确认律**：一切方案 dock 后恒等用户确认拍——口头 yes 走普通 chat 道到 start_run，与 Start 钮同一 Start 机器；无任何「存好的策略替你开工」路径（策略直执 / 静默开工永禁——策略只调披露强度，永不替用户开工）。方案 echo 的收尾恒为一句朴素的方案判断问句（一词可答），永不以「成片出来后再调」式交付后修订预告收尾。

### 3. 机制零新增

hold→capture→release 不动；edit→render 维持 $0 定价（自有基建既有裁决）；`edit_output` MVP 零 LLM 成本不收钱（ADR-090 §5）；订阅 / 支付维持 W11 边界不重开。

**Consequences**: 四环 = 持久化 / 读取点 / 闸 / 偏好真生效，UI 环与台账环不变。座位 = settings API（users.settings JSONB + GET/PUT /auth/settings + configs `billing.confirm_large_threshold`）+ composer 读源以服务端为准 + dock estimate 面强制档形态。认知验收必答：用户怎么知道自己设了什么（设置面回显当前档）；agent 怎么知道（确认拍呈现受策略驱动的事实句）。

**Related**: ADR-055（计费母法——三词两层与参数表座位）/ ADR-089 §5（停顿定律——确认拍唯一停顿）/ ADR-087 §2.1（费用语义五面——estimate 面披露纪律）/ ADR-090（edit 计费语义复用）

## ADR-093: chat 言语真值律——信封对账补全 + 起始句言语权恢复

**Status**: Decided (2026-09-28)

**Context**: 两起同族事故暴露同一结构洞——chat 的 live 渲染与 restore 渲染不同构：

① **计划确认拍重复段落**：计划散文（`intent.answer`）在 live 消息流内同文出现两次，DB 只存一行。桌面形态无计划卡（planCardVisible 律），排除卡片回声。定位 = answer-SSE 续聊路径的结算缝（`ChatDock.tsx` 选项作答续聊的信封拼接处）：该缝用信封盖 runId/streaming 章，但**从不以信封内容替换预览内容**——sendChat 的 `finalizePreview` 有 `content: content ?? m.content`，此缝缺这半边 parity；叠加 echoCarried/previewStreamed 派生链（它决定 `questionEcho` 是否再推一条流内行），同一段散文可以一路活在预览气泡、一路再进消息流。

② **起始句刷新消失**：「我开始生成了——你可以继续和我聊，也可以离开页面，它会在后台完成」是客户端 i18n chrome（`generationOverlay.startingLine`），由合成单元在 run 出生刻渲染、terminal 即消失，**永不落库**——run 完成后刷新，行消失。用户的记录语义期待：agent 说过的话就在聊天记录里。

**根律**：agent 的一切言语只有两个合法存在形态——**入库的 message 行**（restore 唯一真值源）与 **live 途中的预览**（信封到达即被信封真值对账）；且**言语的作者恒为 LLM**——模板文案（客户端 chrome / 服务端模板）替 agent 说话全形态永禁。凡出现在消息流里的话，刷新前后必须逐字节一致；不一致即结构 bug，不是产品形态差异。

**Decision**:

### 1. 信封对账补全——「信封永远赢」是完整对账，不是半个盖章

一切 SSE 结算路径（sendChat / streamAnswer / 未来任何新路径）在信封到达时执行同一完整对账：身份盖章（runId / streaming 归零）**+ 内容真值替换（信封 content 取代预览 typed text）**。缺任一半 = parity 洞。对账在 `paceSettledProse` 排干之后发生——打字机律两牙零触碰（排干释放的就是信封散文，同值替换零视觉变化；异值时信封赢，这正是对账的意义）。echo 实体化的精确内容匹配 dedup 不动——它防的是卡片回声行重复，与本缝互补；施工时先复现（选项作答触发续聊计划回合，live 观察双段落，刷新归一）再动缝，修复后同一剧本回归。

### 2. 起始句 = start_run 回合的 LLM 言语——模板言语全形态永禁

起始句是 agent 的话，作者只能是 LLM——代码 / i18n / 模板替它说话全形态永禁：

- **start_run 回合有言语权**：speech BEFORE calling 适用于 start_run：模型在调用前以一句自己的话说开工语义（开工 / 可以继续聊或离开 / 后台完成的语义三要素，FREE PHRASING，零引号例句），散文走正常 delta → 打字机 → 信封结算 → **落库为普通 assistant message 行**。live/restore 同构由普通消息机制天然兑现，零持久化新机。
- **模板言语全形态永禁**：无客户端 i18n chrome 起始句（无 `generationOverlay.startingLine`、无合成 startLine 单元）；服务端模板写起始文案同样禁止——言语要么由 LLM 说出并落库，要么不存在。
- **开工道按有无 LLM 回合分两态**：口头 yes 与 Start pill（pill 化为「确认生成」用户消息走同一 sendChat 道，Workspace 合同 C8）同进 start_run 回合——开工句照上条落库；零 LLM 开工道（确定性直启）诚实缺席——无人说话即无记录，进度由 RunTaskList 动态行与画布状态承载，收官言语归 run_completed 触发回合。任何开工道若要求言语，唯一合法形态 = 走 LLM 回合——永不以模板补位。
- 历史 run 无此言语行——不补、不迁移。

### 3. 派生律：状态派生永不持久化，言语永不只活在客户端

`qa`/`streaming` 等客户端派生态不落库（既有律重申）；反向同律——**言语永不只活在客户端**：想被记住的 agent 言语必须在出生刻落库。新增消息流文案的准入门：它是不是 agent 说过的话？是 → 入库；不是 → 不得出现在消息流（去 status 行 / 卡片 / 原生控件）。（**寄存器细化（ADR-095）**：消息流允许「日志格」的世界事件行——动宾短语 + 事实后缀、无人称无语气、视觉分行，Claude Code tool 行同款；本准入门禁令只针对「言语格写法 + 非 LLM 作者」的组合。）

**Consequences**: live-only 重复类 bug 结构性不可能（对账一处不缺）；起始句成为普通言语行——刷新一致由消息机制天然兑现，零持久化新机；零 LLM 开工道的沉默是诚实形态而非缺失。零 schema 变更；W2~W5 均触 prompt 面，过 prompt_gate。验收 = 复现剧本 live 无重复 + LLM 开工道（口头 yes / Start pill 同进 start_run 回合）开工句流式出现且刷新后仍在 + echo dedup 回归（计划回声不双显）+ 打字机律回归（开工句不瞬移）。

**Related**: ADR-058（展示文案二源律——言语来源纪律的母法）/ ADR-073（收据层级与时序律）/ ADR-080（界面语言唯一 owner）/ ADR-095（三寄存器律——§3 准入门的寄存器细化）/ CHAT_ARCH §8.6（信封权威与打字机律）/ §8.7（run 段时序律）

## ADR-094: 方向否决资格护栏——能力范围内的性状永不作否决依据 + 分镜呈现律

**Status**: Decided (2026-09-28)；取证底座 = trigger verdict 与 `trigger_system.j2` 引号例句近乎逐字一致的比对 + 分镜能力存在性核验（配方卡「访谈分镜」同素材演示产出——能力为既有事实，生产链零 `reframe_clip` 步是选择律问题不是能力问题）

**Context**: 同一访谈素材，配方卡演示产出了镜头跟人的竖屏分镜，生产链路却产出中央裁剪 9:16——两位主持人之间无人入镜。机制取证三链全断：

① **trigger verdict 照抄引号例句**：`trigger_system.j2` beat ① 的引号示例判词被模型近乎逐字复制为生产 verdict——同时违反 FREE PHRASING 律（模型面永不给引号例句，给了就会被抄），且例句的否决理由（素材性状：固定全景 / 发言密度）正是 `reframe_clip` 直接处理的性状——**能力范围内的性状成了方向否决的依据**，产品在劝用户远离自己的能力。

② **router plan 面无分镜组合律**：访谈形态 + 竖屏诉求时，plan path 没有任何条款驱动 `select_clips + reframe_clip` 组合或向用户提出 framing choice（全幅 vs 分镜），静默落到中央裁剪默认。

③ **能力菜单措辞欠卖**：`_MENU_PHRASES` 的 reframe_clip 行说 "reframing (vertical / square / horizontal)"——画幅机械语言，从不说镜头跟人的智能分镜语义，能力问答面自然说不出来。

④ **能力问答误读实证（单人定机位素材）**：用户问「切片镜头会对准主人公吗」，agent 断言「镜头跟着人走需要原生镜头运动或多机位，单一全景做不到」——与 `resolve_mode`（`procedure.py:40-50`）真实行为相悖：**form=="single" → speaker_follow**（YuNet 逐帧人脸锚定 crop_track——定机位素材上的虚拟运镜正是它的主场），form=="interview" → interview_switch，仅无 speaker_map 时才落 static_center。且答复的竖版/方形/横版三 bullet 逐条复刻菜单措辞——`_MENU_PHRASES` 写什么，agent 就以为能力是什么，欠卖措辞直接塑形能力认知。

**Decision**:

### 1. 否决资格护栏（trigger 与 router 同律）

一个方向（配方 / 切法 / 产物形态）的否决理由，**永不建立在已交付能力直接处理的素材性状之上**。适用面 = 一切 agent 言语中的方向评判：trigger verdict、plan 提案散文、能力问答、ask_user 的 framing。护栏语义（prompt 面表述走 FREE PHRASING，措辞不抄本句）：不能说「固定全景所以不适合重剪」——分镜工具就是干这个的；可以说「单人固定机位，分镜跟人收益不大，全幅更稳」——否决依据必须是能力**边界外**的真约束。

### 2. 访谈形态的分镜呈现律——说得出来、选了能成

**方向说出律**：素材判型为访谈/对话形态（`speaker_map.form == "interview"` 或 understand 产物同等识别）时，分镜（镜头跟人）是该素材的**活方向**——trigger 首读 / 想法问答 / plan 提案都应能把分镜方向说出口（可作 suggestion dock 的选项），永不以素材性状否决（§1）。

**选择执行律（必含）**：用户选定分镜方向后（点选 suggestion 或口头指明），plan path 组链**必含 `select_clips + reframe_clip`**——选了就要像配方卡那样成片，执行不打折。用户未指明方向且诉求为竖屏短片时，plan path 二选一：组合进链，或 ask_user 提出明确 framing choice（全幅切片 vs 分镜跟人，一词可答，散文恒带默认路径）。静默中央裁剪永禁。判型证据缺席（无 speaker_map）时不阻塞——按现有默认走，护栏只在证据在场时生效。

**确定性静默补链否决**：「访谈 + 竖屏即自动插入 reframe、不问不说」的确定性补链方案被否——方向必须经 agent 说出、用户选择，选择面不收缩。确定性兜底（只认用户已选的结构化证据）挂账：实测若 LLM 组链仍有漏选，另批评估（届时需 suggestion 选项的结构化指令载荷，属新机制）。

**验证座**：chat_scenarios 新增常驻回归——访谈素材 → 用户选分镜方向 → 断言链含 reframe_clip 且成片带 crop_track（确定性尾）。

### 3. prompt 面修正（prompt authoring law：现在时法律，零引号例句）

trigger beat ① 的引号示例判句整删，替换为 §1 护栏的抽象表述；router plan 面补 §2 的分镜组合律。模型面文本永不含日期 / ADR 编号 / 事故叙事。两处改动同属 prompt 面，过 prompt_gate。

### 4. 能力菜单措辞升格

`_MENU_PHRASES` 的 reframe_clip 行从画幅机械语言升格为语义语言（智能分镜 / 镜头跟人），注册表文案 en/zh 同改；能力问答面由此能说出分镜能力。

**Consequences**: 访谈素材静默中央裁剪的结构通路关闭；agent 方向评判获得诚实性约束；想法回合说得出分镜、用户选定后链必含分镜；能力问答能说出分镜。零 schema / 零工具改动——reframe_clip 工具不动，动的全是选择律与措辞面。验证 = prompt_gate 三探针 + chat_scenarios 分镜必含座与相关座回归 + 访谈素材 live e2e（验收 = 想法回合说得出分镜方向、选定后同素材产出分镜成片）。

**Related**: ADR-058（展示文案二源律）/ ADR-089（能力编译与执行边界——能力清单是编译事实，选择律在本条）/ prompt authoring law（CLAUDE.md Testing 节）/ RECIPES §4.8（配方准入——分镜能力的用户面承诺）

## ADR-095: 消息流三寄存器律——言语 / 活动日志 / 瞬态状态 + 素材节拍归位

**Status**: Decided (2026-09-28)；讨论底座 = Claude Code / Codex 顶级 agent 三寄存器解剖对照

**Context**: 两问同族——

① **节拍身份错位**：「正在看 xy_1.mp4…」= 言语格写法（进行态 + 省略号 + 会话语气）+ 模板作者 + 入库消息行——读起来像 agent 说过的话，实际 LLM 从未说过。与 startLine 案（ADR-093）同族不同病：startLine 死于三规则全违反（言语格 + chrome 作者 + 不入库），节拍是写法与身份错位。

② **「为什么没有正在转写」**（机制取证）：素材处理链 = `_content_hash → _asr → speaker_map → prosody` 四工序（VIDEO，`asset_processing.py:263`）共用一个资产级 `PROCESSING` 状态——**工序信号从未暴露到资产面**；live now-line 由客户端按 `processing_status == PROCESSING` 派生，只能说资产级的「正在看」；入库节拍 `_record_reading_beat` 只在终态写一行（「已读完 X · 41s · N/M」）。另存在两面词汇不一致：run stepper 说「正在转写你的媒体…」（`results.stepper.transcribing`），上传节拍说「看」——同一动作两个名。

**顶级 agent 对照取证（三寄存器解剖）**：

| 寄存器 | Claude Code | Codex / Deep Research | 作者 | 入库 |
|---|---|---|---|---|
| 言语面 | assistant 散文（含工具前言） | final answer / thinking 摘要 | 只有模型 | ✅ 原文 |
| 活动日志面 | `⏺ Read(path)` / `⎿ Read N lines` | `$ npm test` 执行块 / "Searched for X" 列表 | harness 模板 | ✅ 事件记录 |
| 瞬态面 | spinner 俏皮词 / "Thinking…" | "Working (12s)" | harness | ❌ 绝不入库 |

共同不变量：记录可逐字节重放（一切持久化元素派生自事件/会话日志）；瞬态 chrome 永不入记录；散文作者 = 模型独占。**合法性的边界不在「模板 vs LLM」，在寄存器**——日志面模板渲染合法且可持久化，前提是语法为日志格；言语面模板永禁；瞬态面模板合法但绝不入库。

**Decision**:

### 1. 三寄存器律（ADR-093 根律的展开，§3 准入门的细化）

- **言语面**：会话散文（第一人称完整句）。作者恒为 LLM，落库为 message 行，信封对账同 ADR-093 §1。
- **活动日志面**：世界/循环事件的结构化事实行（素材节拍、活动帧、步骤行）。确定性模板渲染**合法且可持久化**，但语法必须是**日志格**：动宾/名词短语 + 事实后缀，无人称、无进行态、无省略号、无会话语气；视觉与言语分行（灰阶 / meta 座）。**ADR-093 §3 准入门据此细化**：消息流允许日志面行存在（Claude Code tool 行同款），禁令只针对「言语格写法 + 非 LLM 作者」的组合。
- **瞬态面**：spinner / thinking / now-line 等活态 chrome。模板合法，**绝不入库**，refresh 后不存在；可随工序/相位细化——瞬态面比入库面细的合法性来源即此。

### 2. 素材节拍归位（日志化 + live 工序化）

- **入库节拍（终态行，`_record_reading_beat` 既有座不变）**：措辞日志格化——动词分叉（看/听/读）保留、去言语语气；事实后缀保留（时长 / N·M drain 进度）。
- **live now-line（瞬态面）工序化**：素材处理链在每个 processor 入口把当前工序写入资产面（`asset.meta` 携带，零 schema 变更；终态清除，读容忍），客户端 now-line 随工序推进说真话（转写 / 理解等用户语言标签）；入库节拍仍一行资产级，不随工序膨胀。
- **渲染座位、动词分叉、N/M 进度、入库时机（终态）全部不动**。

### 3. 边界与禁令

- 工序标签 = 用户语言的工序真相（「转写」经用户点名成为合法词汇），内部 processor 名（`speaker_map` / `prosody`）永不上屏。
- 节拍永不进言语格；LLM 言语永不模仿节拍格式。
- run stepper 工序文案（「正在转写你的媒体…」）是 run 面工序座，与节拍面并存合法——两面词汇对齐同一工序词表（转写 / 理解），消「同一动作两个名」。

**Consequences**: 记录面干净——入库行无一「像言语的非言语」；处理中的几分钟行文本说真话（工序级）；两面词汇一致。零 schema 变更（stage 走 `asset.meta`）。验证 = live 走查（上传素材观察工序推进文案）+ 刷新一致性 + 纯测试（stage 写入/清除/读容忍）。

**Related**: ADR-093（根律——本 ADR 是其 §3 准入门的寄存器细化）/ ADR-058（展示文案二源律）/ ADR-087 §3（活动投影——日志面的另一族）/ CHAT_ARCH §8.6（前端渲染律）§8.7（StatusLine 一座两行）
