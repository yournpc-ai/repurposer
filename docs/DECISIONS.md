# Architecture Decision Records (ADR)

> Status: Active（滚动维护现行决策；编号不连续属正常）。本文是决策与必要理由的事实源，不是另一份完整架构规范；字段级与行为契约归对应子系统文档。按下方主题和编号定点阅读，不要求通读全文。

## 阅读与维护

- 同一决策的措辞补正、实现接线和普通 bug 修复更新现行条款或对应规范，**不默认新增 ADR**。
- 只有架构边界、产品语义或关键取舍发生真实变化时才新增独立编号；稳定编号不随意重排。
- 被取代的规则不作为现行法并列保留；失效叙述直接删除，不保存归档或专题历史副本。仍被引用的编号在下表保留替代去向。
- 实施状态与未验证项归 `PROGRESS.md` / 局部 progress；ADR 的 Decided 不等于已实现或已验收。
- 视频施工以 ADR-145 与 VIDEO_PROJECT 为准；旧 FilmStoryboard/pending 信封/固定骨架/legacy 指纹的具体实现条款不再构成兼容义务，仍有效的创作/授权/视听语义归 VIDEO_PROJECT §15，共享守卫与剩余验收归 VERIFICATION。旧编号不用于恢复已退役任务或实现锁。

## 主题索引

| 主题 | 主要 ADR | 详细契约座位 |
|---|---|---|
| 仓库、后端、前端、数据与基础设施 | 001–026 | `MODULE_ARCHITECTURE.md` / `DATABASE_MIGRATIONS.md` |
| RunPlan、执行内核、队列、工具与模块边界 | 017、028–033、039、043、050、077、079、086–089、096–098 | `AGENT_ARCHITECTURE.md` / `MODULE_ARCHITECTURE.md` / `ARCHITECTURE_NORTH_STAR.md` |
| Chat、交互、言语、活动与授权 | 034、040–043、051–054、058–095、099–104、108–110、116–117、133–135、139 | `CHAT_ARCHITECTURE.md` / `DIALOG_WORKFLOW.md` / `BILLING.md` |
| UI、画布、工作区与卡面 | 035–038、041–042、046、048、051、056–058、061–063、067–076、082、098、111–115、118、122、143 | `UI_GUIDELINES.md` / `CHAT_ARCHITECTURE.md` |
| 身份、定位与国际化 | 013、037–038、042 | `POSITIONING.md` / `PRD.md` |
| 渲染、clip-spec、媒体与音乐 | 016、018、020、023–024、044–045、096、113、115、130、136、140、145 | `RENDERING.md` / `MUSIC_ARCHITECTURE.md`；视频目标归 `VIDEO_PROJECT.md` |
| Film/MG | 119、121、123、127、129–132、134–145 | 新目标与施工归 `VIDEO_PROJECT.md` / `tasks/video-project-implementation.md`；旧运行事实查代码/RENDERING，有效需求归 VIDEO_PROJECT §15，旧任务/结构锁退出 |
| 测试与验证治理 | 114 | `VERIFICATION.md` / `PROGRESS.md` |

## 退役编号与别名解析

| 引用 | 现行去向 |
|---|---|
| ADR-101（素材等待旧机制） | ADR-102；现行行为 CHAT_ARCHITECTURE §3.5，验收 VERIFICATION §4.3 |
| ADR-105（画布确认/可见性旧形态） | ADR-111；行为契约 `CHAT_ARCHITECTURE.md` |
| ADR-120（film 分镜核对旧条目） | 设计/版本闭环保留于 ADR-129，执行时序见 ADR-130；后续呈现与批准修订见 ADR-131/132 |
| ADR-123（工作区布局旧代码注释） | 见 ADR-143。**单独出现的 ADR-123 在文档现行索引中默认指 Film 分镜丰富度**；工作区布局的旧代码注释由该别名解析 |

## ADR-001: Single-repo, simple directory structure

**Status**: Decided

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

**Decision**: Run P0 first as an internal tool to validate the core workflow, but choose technologies that prepare for future SaaS.

**Impact**:
- Frontend chose TanStack Start instead of Streamlit
- Database chose PostgreSQL instead of SQLite
- Code structure considers multi-user and permission extensibility
- P0 does not implement billing or multi-tenancy, but leaves room for extension

---

## ADR-013: Internationalization, theme switching, and European market positioning

**Status**: Decided；SSR/i18n 的现行实现约束与 `CLAUDE.md` 一致。

**Decision**:
1. 前端使用 `i18next` + `react-i18next`；英文是字典源语言，`zh.ts` 必须满足同一 `Resources` 类型。
2. 默认语言为 English；用户选择写入 `repurposer-lang` cookie。**SSR 与首个客户端渲染都读取同一 cookie**，每个 SSR 请求创建独立 i18n 实例，禁共享可变 singleton。 hydration 后不得自动切换语言；只有挂载后的明确用户动作可以 `setLocale`。
3. 默认主题为 dark；`system` 首次也按 dark 处理。手动选择写入 `repurposer-theme`；`__root.tsx` 的 anti-FOUC 内联脚本不得删除。
4. 主题切换使用 View Transition API 圆形揭示；不支持或 reduced-motion 时直接切换。
5. 图标统一 `lucide-react`；base-ui trigger 使用 `render`，不使用 Radix `asChild`。
6. 产品服务有素材但无暇经营社媒的欧洲知识专家；输入不限于演讲，输出与渠道由用户点名，不默认承诺“一次生成全套”。
7. 多语言输出是欧洲市场入场券，内容生成需覆盖 FR/DE/ES/IT/EN 等目标语言。
8. GDPR / EU 驻留是已拍板的产品方向，不代表现有部署已完成合规。对外文案在实装与验收前只保持 ready 角度，不宣称已经提供 EU 驻留或机构合规。

**Rationale**: 同语言 SSR/首帧可避免 hydration 漂移；per-request 实例避免并发请求串语言。主题首帧脚本避免闪烁。欧洲知识专家、多语言与合规方向必须和真实交付能力分开陈述。

**Constraints**: 新用户文案先加 `en.ts` 再镜像 `zh.ts`；浏览器 API 只能出现在 effect、事件处理器或 anti-FOUC 脚本。营销与 UI 示例避免 TikTok/viral/爆款定位。

**Related**: `apps/web/src/lib/i18n/` / `apps/web/src/routes/__root.tsx` / `CLAUDE.md` / `docs/POSITIONING.md`。


## ADR-015: ORM uses SQLAlchemy, migration tool uses Alembic

**Status**: Implemented

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

## ADR-016: Structured media specs——clip-spec / film-spec 平级，renderer 是可替换黑盒

**Status**: Decided；clip 编辑器交互 = `VIDEO_EDITOR.md`，字段与 family dispatch = `RENDERING.md`。

**Decision**:
1. **声明式 spec 是渲染契约，renderer 是可替换实现**。`clip-spec` 服务既有素材剪辑；`film-spec` 服务网页/文字/通用组合影片。二者是平级 spec families，不存在“clip-spec 覆盖一切渲染”或第三套隐式 spec。
2. 所有渲染入口只按 `spec.family` 分派；preview / retry / revision / recovery 全生命周期同律。Remotion / React / DOM 等 renderer 概念永不进入任一 spec。
3. 首个 renderer 是服务端 Remotion 黑盒；web preview 与最终渲染共享对应家族实现。替换 renderer 不得改变用户层 spec 语义。
4. **clip 编辑器形态** = 文字稿编辑 + 词级时间戳 + 单轨 trim；其 L3 边界是不做自由多轨 NLE、自由层合成、转场画廊、stock B-roll 库、自动人脸重取景和客户端引擎，专业需求导出剪映/Premiere。ADR-044 的受控锚/层枚举不因此被误读成自由 NLE。
5. **Film composite 是独立家族的受控元素组合**（ADR-140），不套用 clip 编辑器的 L3 禁令，也不开放任意 CSS/自由画布/通用关键帧。
6. 字幕样式只开放 CSS 与 libass 均可表达的枚举子集；多语言 ASR 词级时间戳与对象存储流式/寻址是 clip 编辑硬前提。
7. 两类 spec 都必须保留确定性预览/渲染 parity、文件有效性检查与 renderer 替换成本；生成式媒体本身的方差不得伪装成 parity。

**Related**: ADR-018/020/024/044/045/096/113/115/119/130/140；`docs/RENDERING.md` / `docs/VIDEO_EDITOR.md`。

## ADR-017: Postgres as the task queue, standalone worker process

**Status**: Decided；队列与认领源详表 = `MODULE_ARCHITECTURE.md` §5/§7。

**Decision**:
1. 重活统一使用 Postgres `FOR UPDATE SKIP LOCKED` 队列，由独立 `python -m app.worker` 认领；不引入 Redis/Celery，不在 FastAPI BackgroundTasks 或跨模块同步调用中执行重活。
2. worker 的合法认领源必须在 worker claim loop 与 `MODULE_ARCHITECTURE.md` 登记。新 processor 注册到 `app/pipeline/asset_processing.py:PROCESSORS`；新 run/render/其他队列必须同时登记认领、重试、收官与所有权规则。
3. **上传不等于处理请求**。素材可以先处于休眠态；只有实际消费链或明确处理命令请求所需内容事实时才入处理队列。Chat 需要素材内容时按 ADR-102 在同一读工具内等待 ready/failed，不恢复 `understanding_warmed` 接力或客户端预等待。
4. run、asset processing 与 render 各有自己的状态、重试和终态；不得用一个 status 字段代替执行身份。claim/reap/re-pend 必须配套 fencing token，stale executor 的终态写与副作用按 ADR-079 失败闭。
5. attempt cap、手动 reprocess/reset、孤儿回收和 storage GC 是不同语义；重置必须同时处理状态、错误与计数，不能只翻 status。排队与长等待由队列行表达，不持数据库事务空转。
6. API 与 worker 物理隔离；`SKIP LOCKED` 允许多 worker 安全认领不同工作，但不允许重复计费或旧执行者覆盖新世界。

**Rationale**: 当前规模下 Postgres 队列省去中间件，同时保留并发认领与崩溃恢复。上传休眠避免为无消费需求的素材支付处理成本；统一 worker 边界避免 API 被重活拖住。

**Related**: ADR-079/096/102；`apps/api/app/worker.py` / `apps/api/app/pipeline/jobs.py` / `apps/api/app/pipeline/asset_processing.py` / `scripts/dev.sh`。


## ADR-018: Render service isolation and shared spec-family implementations

**Status**: Decided；字段契约与当前 dispatch = `RENDERING.md`。

**Decision**:
1. 渲染服务独立在 `apps/render/`（Node/pnpm + Remotion + HTTP 服务），对 API 是黑盒；Python `apps/api` 不混入 Node runtime。
2. pnpm workspace 连接 `apps/web`、`apps/render` 与 `packages/*`；`apps/api` 保持 uv 独立。共享包只承载确需共享的实现与类型，不为此引入 Turborepo/Nx/Bazel。
3. **clip-spec 与 film-spec 是平级家族**。clip 的共享组件/类型住 `packages/clip`；Film 的 schema、组件与组合实现住其当前 render 模块。不得把 Film 硬塞进 `<Clip>`，也不得为 Film 建第二渲染服务。
4. render 服务只消费对应 family 的 spec 与已解析媒体 URL，不读数据库；preview/retry/revision/recovery 均按 `spec.family` 走同一分派。
5. 输出先写临时目录，再通过 API 提供的 presigned URL 上传；不依赖共享卷。源 URL 必须可由渲染环境访问，超时、并发与临时资源清理由当前运行配置和 RENDERING 合同约束。
6. preview 与最终渲染的确定性部分共享实现；生成式媒体方差不冒充 parity。字体、浏览器和外部字体下载的可替代/离线条件必须保持可部署。

**Related**: ADR-016/020/096/119/140；`apps/render/` / `packages/clip/` / `pnpm-workspace.yaml` / `docs/RENDERING.md`。


## ADR-020: clip stills——图片与可选音频的 audiogram 源形态

**Status**: Decided；本条只定义 **clip-spec** 的 `stills` 源，不是 Film composite 或 R5 合成主片的契约。

**Decision**:
1. `ClipSource.kind = video | stills`，缺省读作 `video`，保持旧 clip 兼容。
2. `stills` 以 `image_urls` 为基础视觉：零图按契约给纯色底，一图全屏，多图按总时长硬切轮播；`url` 可承载可选录音，无录音时按固定图片时长形成合法区间。
3. 有音频时复用 ASR 词级 `caption_track` 与声轨；无音频时是诚实无声幻灯，不伪造字幕、ASR 或声音。
4. 源选择与输入组合由当前编译/素材规则决定；纯文字不能借此绕过 clips need media。生成式发言主片不得借 `stills` 名称规避 `spec.family` 与 provenance。
5. 该形态只承诺单轨硬切、既有字幕/品牌/音乐能力；自由转场、Ken-Burns、自由文字动效、B-roll 库与自由布局不属于本契约。Film composite 的受控元素组合由 ADR-140 独立定义。

**Related**: ADR-016/044/140；`docs/RENDERING.md` / `docs/tasks/synthetic-talk-video.md`。


## ADR-023: Music becomes an AI-generated, asset-based library

**Status**: Implemented

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
- `apps/api/app/tools/music/node.py`（曲目解析/选择与 clip-spec 接入）
- `packages/clip/src/types.ts` (`ClipMusic`)

## ADR-024: Object storage (Volcengine TOS) for all persistent files

**Status**: Implemented

**Decision**:
1. **All persistent files live in one S3-compatible bucket (Volcengine TOS)**: uploads, rendered outputs, brand media, music, demo assets. PostgreSQL stores only object keys.
2. **Per-user key prefixes**: `{user_id}/uploads|outputs/...`; shared demo assets under `demo/`; music under `music/`. The files endpoint derives ownership from the key prefix (`demo/` is anonymous-readable).
3. **Uploads are direct-to-storage**: the API issues short-lived (15 min) presigned PUT URLs; the client PUTs bytes directly and then creates the Asset row from the returned key. The create-from-key endpoint validates the key prefix and that the object exists.
4. **The bucket is public-read without ListBucket**: reads 307-redirect from the API (after an ownership check) to the public object URL. Accepted trade-off for MVP (URLs are unguessable UUID keys); revisit private bucket + presigned GET before EU institutional sales.
5. **Two delivery modes**: redirect (default, for `<video>/<img>` tags) and `?proxy=1` (API streams bytes) for programmatic `fetch()` — the bucket does not send `Vary: Origin`, so a no-cors copy of an object poisons the browser cache for later CORS fetches.
6. **Downloads use presigned GET** carrying `Content-Disposition: attachment` (`/outputs/{key}?download=1`).

**Consequences**:
- Local `assets/` and `data/` directories are deleted.
- Render service uploads outputs via presigned PUT; no shared volumes anywhere.
- Frontend receives storage-public URLs at the API boundary (`resolve_stored_url`); the DB keeps bare keys.

**Related files**:
- `apps/api/app/providers/storage.py` (keys, presign, public/resolve URLs)
- `apps/api/app/platform/routes.py` (`files_router`：redirect / proxy / presigned download)
- `docker-compose.yml` (S3_* env wiring)

---

## ADR-025: Thin LLM provider interface——模型访问与计量 seam

**Status**: Decided, **PLANNED / 未完整实施**；M3 仍是默认 provider。当前代码是否经过统一接口以实际依赖为准，不把本决策写成已完成多 provider。

**Decision**:
1. 模型访问收敛到薄 provider seam，至少覆盖结构化生成、流式生成与原生 tool calling；agent/harness 不直接依赖某一 provider 的异常、think 块或线格式方言。
2. 这不是多模型 SKU 货架或并发路由承诺。触发条件是真实 EU 驻留/客户要求或主 provider 能力边界；用户面若开放，只呈现“优先 EU 托管”等策略，不暴露模型选购。
3. **usage 必须穿过边界**：每次调用返回 tokens/cache/latency/cost 与 attempt outcome，由真实 owner 落账——run/step 走现有 metering，chat 走 `conversation_usage`；取证级 `agent_calls` 是独立 PLANNED 需求，不虚称已存在。
4. provider dialect 在 adapter 内归一，向上层提供干净 content/tool-call 流。新 provider 选择双方共持的原生能力；不得为兼容而恢复无界执行 loop、盲重试或另一套意图入口。
5. ADR-004 的自建编排不变；这里只抽象模型访问，不引入 LangGraph/CrewAI 等编排框架。

**Related**: ADR-003/004/039/050/055/066/077；PROGRESS 需求池「LLM provider 抽象 / EU-hosted / agent_calls」。

## ADR-026: AI 内容标识分级——合成轨道强制披露，纯剪辑豁免

**Status**: Decided, **PLANNED / 上线前合规义务**；已拍板的法规适用基线日期为 **2026-08-02**。本条不代表 C2PA、发布披露或渠道适配已经实施。

**Decision**:
1. **分类由系统根据真实 provenance 与 spec 自动完成，不要求用户回答“这是不是 AI”**。分类器必须同时理解 clip-spec、film-spec 及输出/元素的 generated provenance；不得只从 clip-spec 或节点名称推断。
2. dub、合成声音、AI 生成视觉及其他合成轨道进入披露族：目标实现包括 C2PA Content Credentials、发布界面披露和 `Publication.ai_disclosure=true`（发布模型落地时）。同一产物中局部合成也必须可追踪，不能因主源是实拍而漏标。
3. 真实素材的剪切、字幕与字幕翻译属于纯剪辑豁免；不得为了“全都有标”给明显非合成内容贴 AI 标。AI 文案是否适用人工 editorial-control 豁免，必须由实际发布前可编辑、人工确认流程支撑，不能只靠一个默认勾选的徽标。
4. 披露状态沿 output/version/publication 血缘传递；重制、合成元素编辑和版本恢复后重新按实际内容计算。Distribution 只读确定结果，不另建第二分类器。
5. 渠道上线时必须核对其 AI 披露字段、直发权限和用户授权；渠道不能表达所需披露时不得静默降级为“已合规”。
6. C2PA 写入、发布 UI、平台适配与法律口径在对应功能上线前必须分别验收；合成媒体生成本身不自动授权发布。

**Consequences**: 合规是横切切面，集中读取 spec/provenance，不散落在各 renderer 或 chat prompt。纯剪辑保持低摩擦，合成内容承担明确披露义务；任何未实现项留在 PROGRESS/对应 PLANNED 合同，不以本 ADR 宣称完成。

**Related**: ADR-016/027/029/030/044/140；`docs/MODULE_ARCHITECTURE.md` §5 / `docs/DISTRIBUTION.md` / `docs/STRATEGY.md`。


## ADR-027: 发布审核分级——个人免审秒发，机构强制人工确认（P2）

**Status**: Decided (2026-07-22)

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

**Related**: ADR-016（对应 spec 契约不动）、ADR-025（provider 抽象与计量）、ADR-035 / ADR-036（用户面图形态）、`docs/MODULE_ARCHITECTURE.md` §2.1/§4、`docs/STRATEGY.md` §2.5/§5、`docs/research/elevencreative.md`

## ADR-029: 生成式媒体与既有剪辑共用执行地基，产物独立标记 provenance

**Status**: Decided, **PLANNED**；R5 当前范围 = `tasks/synthetic-talk-video.md`。本条中的 `voice_gen` / `synth_visual` 等名称是目标能力名，不表示当前 registry 已注册。

**Decision**:
1. 生成式媒体接入时复用 RunPlan/NodeBase、worker、PROCESSORS、报价、计量、活动和 `outputs`，不建立第二条编排链。混合图可以包含真实素材剪辑与生成产物，但每个节点的输入和付费边界必须显式。
2. 生成产物以 `provenance=generated` 和完整 source_ref 区分于实拍；生成主片不硬塞 clip-spec。确定性包装可复用现行 film-spec/等价合成路径，生成模型本身的方差不承诺逐帧 parity。
3. provider 的异步 begin/await、生成谱系、声音/肖像授权与 AI 披露是接入条件；它们不得绕过 ADR-025 的 provider seam、ADR-026 的分类或 persona/voice 权限。
4. 多变体选择门只在具体能力确有需要且报价/授权完整时引入，**不是 R5 v1 的默认义务**。R5 v1 不接唇形 avatar；缺声纹时不得静默换无关 stock voice。
5. 输入 presence-gating 由确定性输入组合与节点 `requires` 决定，不由 LLM 猜“生成模式”。每次真实生成尝试按当前计费规则计量，失败不扣费与 fenced 零副作用不变。
6. 合规分类读取实际 spec 与 provenance 边/字段；不依赖“虚拟产物一定走 clip-spec”的旧假设。

**Related**: ADR-016/025/026/028/030/140；`docs/tasks/synthetic-talk-video.md` / `docs/STRATEGY.md`。


## ADR-030: 产物统一为 outputs——clip 降级为类型，payload schema 注册表守门

**Status**: Decided (2026-07-22)

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

**Related**: ADR-016、ADR-026、ADR-028、ADR-029；`docs/DISTRIBUTION.md` §3；`docs/AGENT_ARCHITECTURE.md`；现行规范 `AGENT_ARCHITECTURE.md`

## ADR-031: 渠道凭证应用级加密——Fernet + env key

**Status**: Decided (2026-07-23)

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

**Related**: ADR-016（clip-spec 在本操作域的契约）、ADR-028（RunPlan 同构对偶）、ADR-030（outputs 统一产物表）；现行规范 `VIDEO_EDITOR.md`（D1–D7 全文）；`docs/MODULE_ARCHITECTURE.md` §2/§4

## ADR-033: 编辑面分层——能力层唯一（ops+tools 双海拔），适配层多前端并存

**Status**: Decided；当前注册表与受控编辑边界见 ADR-039/044/090。

**Decision**:
1. **能力层唯一，双注册表双海拔**：`OP_REGISTRY`（产物级受控微操作，带 operation journal、并发校验与 undo）∪ `TOOL_REGISTRY`（任务级能力，编译为图节点并经受权 run）。参数级精确修改走 operations；需要新任务链的请求走当前计划/提案工具，不能把 precomputed ops 偷渡成 run，也不能把重制伪装成版本内编辑。
2. **适配层多前端，全部薄转换**：适配器只做"输入形式 → 注册表调用"的翻译，**禁止自带编辑逻辑**。当前 editor 手势走 ops HTTP，chat 走 `edit_output` / `edit_graph` / 计划工具；MCP 若启用也只能新增翻译层，能力层与授权边界不变。
3. **能力投资压能力层**：新编辑能力 = 新 op 或新 tool 注册项，全部适配器同时受益；禁止任何适配器私设能力种类（如 editor 独有的编辑类型）。
4. **chat 是正式编辑面**：@output / plan_ref 是其定向机制，pinned output 由服务端确定性解析并优先于模型猜测。editor 不退场——精细手势（拖 trim、点字幕改字、框选删段）仍是其强项。

**Consequences**:
- 文字稿编辑 + 单轨 trim 是 editor 适配器的形态，不是产品编辑面的全部。
- L3 分工线不变：自由多轨 NLE、自由图层合成、转场画廊与 stock B-roll 仍交给 CapCut/Premiere；ADR-044 注册的受控 anchors/layers 与 entry-edge transition 枚举不属于这些自由编辑面。
- chat 的精确编辑、图修订与计划提案能力以当前 Chat 合同为准；开放项归 PROGRESS。
- "能力层 / 适配层"入架构词汇（NAMING §2）；新 op/tool 评审必须回答："这是能力层成员，还是某适配器的呈现细节？"

**Related**: ADR-016（clip-spec 在本操作域的契约）、ADR-028（RunPlan）、ADR-032（Operation Model）、ADR-039（TOOL_REGISTRY）、ADR-090（受控 edit_output）；CHAT_ARCH §9；现行规范 `VIDEO_EDITOR.md` / `RECIPES.md`

## ADR-034: Chat 流式与言语提交——SSE、增量散文、DeferredFrames

**Status**: Decided；帧级行为与打字机规格 = `CHAT_ARCHITECTURE.md` §8，数组顺序 = ADR-108。

**Decision**:
1. `POST /chat` 是唯一意图面；按 `Accept: text/event-stream` 提供 SSE，JSON 客户端保留同一终态语义。非 SSE 重试不得盲目重放会重复落用户消息的 POST。
2. 模型 content 与 tool calling 在同一有界 loop 中消费。iteration 0 的 content 逐字直推为 delta；schema 对散文字段 null/缺失读容忍，被拒迭代的言语不得进入用户面，信封是最终内容权威。
3. **一切 agent 言语都按打字机节奏出现，整段瞬移永禁**。零 delta 或修复路径在信封到达后仍经 `paceSettledProse` 排干；成功收尾只能 drain，不能 flush 未释放缓冲。
4. **Speech Commit Protocol**：每个带 `on_delta` 的 SSE 回合都 armed；终态依赖的 `delta` / `tool_ready` 先进入 DeferredFrames，只有接受后才到客户端；拒绝则 drop，客户端从未看见，零回滚残片。
5. `on_tool_call` 保持 live，用于 Activity、相位清除与 liveness；checkpoint flush 后仍 armed。拒绝重试使用新缓冲，不把旧言语洗进历史。
6. 禁第二 speech router、token 级安全分类器、模型自报 mode、NLP 对账或 history washing。结构化 payload 与世界事实决定承诺，代码不解析自然语言猜测用户已被告知什么。
7. live 与刷新回放共用 transcript reducer 与持久化顺序；cancelled 尝试留审计但从可见投影退役，真实 failed 保留诚实告警。

**Related**: ADR-064/077/093/095/099/104/108/109/110/133；`app/agents/tool_loop.py` / `app/chat/deferred_frames.py`。

## ADR-035: DAG 用户化边界——只读产品图可用，可操作工作流画布永拒

**Status**: Decided；当前图行为 = `CHAT_ARCHITECTURE.md` / `MODULE_ARCHITECTURE.md`。

**Decision**:
1. DAG 是内部执行表征。当前用户面图是由 FlowView 渲染的**只读 Product Graph**，帮助理解素材、产品、来源和修订关系；配方卡不再以额外静态流程图或 overlay 作为必经步骤。
2. **可操作画布永久拒绝**：不开放接线、自由拓扑、拖放增删节点、节点运行按钮或模型 SKU 货架。拓扑由编译与受控写门产生，LLM 也只提交产品语义提案。
3. 图先呈现后运行，真实节点在原位更新；步骤执行细节由 chat 工作段表达，不把 Execution Graph 滴到画布。新节点类型必须声明 product visibility，默认隐藏。
4. 模型/provider 可作为详情事实展示，但用户选择形态若未来开放只能是成本/合规策略，不是节点上的模型货架。
5. 意图不清时通过 chat 追问或给可行方向，不能用“亮出 DAG”代替理解用户。

**Related**: ADR-028/036/041/057/086/118；`docs/CHAT_ARCHITECTURE.md` / `docs/UI_GUIDELINES.md`。


## ADR-036: FlowView——共享只读图基座与确定性空间规则

**Status**: Decided；rank 现行法 = ADR-098，transcript 边界 = ADR-113。

**Decision**:
1. `FlowView` 是共享只读图基座；消费面只把领域数据适配成节点/边，不自绘第二套边、布局或节点 chrome。
2. 节点与边必须来自真实产品关系，禁装饰性假节点/假边。新图没有 transcript 节点或 synthetic transcript→consumer 边；执行步骤永不上图。
3. 拓扑编辑手势结构性缺席。消费面不获得第二套 drag/connect/相机控制 API；组件内部的 explore 导航可提供用户 pan/zoom，但**程序相机只响应用户发起的呈现节拍**（draft 整链 fit、新节点诞生 setCenter），背景 refetch/终态不自动移动。
4. 空间权威是同一 Product DAG 的 effective rank；frame 保存 y/w/h/锚等呈现事实。服务端与客户端不得各算一套 depth/rank，禁 dagre 或靠 birth order 排线。
5. 既有节点保持稳定，append-only 与 settled freeze 保护用户心智；动画只投影真实诞生/状态事件，reduced-motion 直接呈现，刷新/历史首帧不重播。
6. 缩放和平移是导航，不是编辑；dot grid 是 FlowView 唯一签名纹理，不得复制到 Home 或其他页面。

**Related**: ADR-035/041/057/082/086/098/111/113/118；`apps/web/src/components/flow/`。


## ADR-037: 身份模块正名——Speaker 退役、人设（Persona）扶正，IP 留在承诺层

**Status**: Decided (2026-08-08)

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

**Decision**:
1. **`personas` 终态 schema**（ADR-037 改名迁移与本条合并执行）：
   - 身份卡：`id / user_id / name / title? / avatar_url? / language`；
   - 风格块（flat 六件，现状平移）：`core_values / favorite_metaphors / sentence_style / emotional_tone / typical_hooks / avoid_words`；
   - 策略块（flat 三件）：`audience? / guidelines? / cta?`——**CTA 唯一家**；无 `voice` 文本列（`voice` 一词的唯一合法含义 = 音频本义，词汇表；文风内容归 `guidelines`）；
   - 声音块：`voice` JSONB NULL——`{"kind":"cloned","voice_id","sample_asset_id"}` | `{"kind":"stock","stock_id"}` | NULL = Auto；
   - 皮肤块：`brand` JSONB NULL——caption 字体/字号/颜色/位置/preset、title 开关+位置、片头尾卡与已注册的强调样式；NULL = 系统默认皮肤；**块名 = `brand`，全栈一词**（人设块 / 烘焙 / clip-spec `brand` 段同名，§1）——无独立模块，词保留；不引入与 `brand` 平行的 `look` 字段。`logo` 键没有当前渲染消费路径，不进入 UI；
   - 来源与校准：`learned_from` JSONB NULL（asset hashes + 摘要，显化页"它从哪学的"）、`calibrated_at` ts NULL（最近校准，§4 可空时间戳）、`auto_created_at` ts NULL（系统 bootstrap 标记——**替代 is_default 布尔**）；
   - 审计：`created_at / updated_at`。
2. **无 `brand_templates` 表——config 三分流**：皮肤字段 → `persona.brand`；工艺开关（`removeFiller` / `captionEnabled` / `aspect` / `fillMode` / 音乐默认）→ 配方注册表 / 计划默认（`removeFiller` 同时是 op/tool，`aspect` 是产物格式）——**不进人设**；`language_tone` 不单独成字段（风格六件已覆盖）。
3. **引用形态**：无 `projects.brand_template_id`（渲染时经 `persona_id` 解析）；composer payload = 单 `persona_id`；`GenerationContext.brand` ← `persona.brand`；`memory/brand.py` 烘焙读人设（模块名不动）；**clip-spec `brand` 段不动**（渲染黑盒契约零破坏，ADR-016）。
4. **前端**：`/personas` 人设页 = 身份卡 + 风格（"它眼中的你"，含 `bootstrapped_from` 来源说明）+ 策略 + 声音 + **皮肤分区（设置 + 实时预览）**；`/speakers`、`/brand-template` 307 重定向到 `/personas`；sidebar 身份项 = 单「人设」；composer 无 Brand pill——人设块 = 唯一身份控件（皮肤随人设）。
5. **`STOCK_VOICES` 代码内静态注册表**（随代码部署，不建表——系统音色不伪装人设）：id / 名 / 风格标签 / 语言覆盖 / 试听 URL / provider voice_id。
6. **默认人设解析链**（不加 is_default 布尔）：项目挂载 > composer 显式选择 > `auto_created_at` 非空（系统 bootstrap）> 最早创建。
7. **皮肤与工艺分家**：默认皮肤只读 `persona.brand`；配方可以声明工艺与格式默认，经当前计划进入编译与报价，不引入 run 级 `look` 字段或隐藏 brand 覆盖通道。任何计划修订都继续走当前 Chat/受控手势与授权机器。

**Consequences**:
- IP 容器终态（ADR-037 D4）更干净：IP = 人设（身份+风格+策略+声音+皮肤，一个完整对象）+ 绑定账号 + 表现数据，整体迁入无残肢。
- 多人设共享皮肤（未来团队空间共用机构 VI）以"从另一人设复制"过渡，团队空间立项时再升级共享引用——不为它保留独立模块（§7 逆用：失去独立表归属即失去模块资格）。
- 排期以 PROGRESS 为唯一事实源。
- 详细契约：`MODULE_ARCHITECTURE.md`——含**消费面全审计与迁移地图**（渲染链 / DAG / chat / 配方 / 前端 / 种子脚本逐点过）与数据迁移步骤（§6–§7）。

**Related**: ADR-037（改名与人设正名）、ADR-016（对应 spec 契约不动）、RECIPES §4.4（人设皮肤与声音归属）/ §5（声音层）、NAMING N-27/N-28

## ADR-039: 工具能力层与四层工程地图——节点对象化、Agent 归一、outputs 派生与估价

**Status**: Decided；当前工具与 SKILL.md 边界按 N-42 和 `CHAT_ARCHITECTURE.md` §4 执行。

**Decision**:
1. **可派发能力住工具包**：`app/tools/` 是节点类、params、私有工序、估价与可选 agent 声明的家，`TOOL_REGISTRY` 是唯一可派发能力注册表。`app/skills/*/SKILL.md` 只是 prompt 装配期指令包，不做运行时发现，不替代工具。`app/agents/` 持有决策单元与 harness，`app/providers/` 持有外部服务与 LLM client 边界。
2. **Agent 归一**：`agents/base.py` 的 Agent 漏斗 = 装配 → 渲染 → 调用 → 校验 → 带反馈的一轮修复 → 计量 → 显式声明的兜底；实例由 name/prompt/schema 声明，花名册可枚举。流式特化按 chat 与 pipeline 的真实调用面存在。无盲重试；默认不静默兜底；intent provider 故障必须诚实失败，不得编造可 Start 的默认计划。纯度由签名约束，例如 understand 不接收 persona 参数。
3. **节点对象化（`NodeBase`）**：节点类自描述 `run` / `estimate` / `requires` / `label` / `reuse`，并声明 `retries` / `after` / `needs_plan_prelude` / `output_type` / `node_type` / `prototype` / `count_limits` 等适用属性。内核保持图算法：报价 = fold、执行 = topo、校验 = ∀requires、配方声明与编译图对账；不得另建平行 retries、slot 或 runner 映射表。
4. **outputs 由工具属性派生**：产物类型来自产出节点的 `output_type`，请求层不另维护 Literal 枚举或 outputs 声明。新增产物同时登记工具与节点事实；用户看到的“你将得到”来自干跑编译的 derived 预览。
5. **多 agent 经 DAG 协作**：agent 互不对话，协作经落库产物沿 DAG 边流动；拓扑由 `compile_graph` 裁决。四层地图 = Model（client 单边界）/ Harness（调用面漏斗）/ Graph（NodeBase + 图算法）/ Loop（chat 状态分派与有界工具 loop）。开放式自主与模型驱动全图编排不因此开放。
6. **估价与计量分侧同源**：`node.estimate()` 给出机械精确价或 agent token 区间；`workflow_steps.estimate` 是计划侧，`cost` 是账簿侧。生成前报价、chat 修改报价与配方典型估价按各自当前可报价域呈现；actual 校准 estimate。NULL 不可报价与守卫线由 BILLING/ADR-117/139 决定。
7. **actor 概念不采用**：工具包与节点声明已经回答“谁执行”，不新增第三套执行者身份。

**Consequences**:
- 架构改动必须保持 compile_graph、chat 判决/dock、run 与渲染的现行契约；回归使用当前 `SCENARIOS` 注册表与 harness 公共断言，数量不在本 ADR 冻结。
- **DX 目标**：加工具 = 加一个工具包并登记；加 agent = 加一条声明；加产物 = 同时注册工具与产物事实。节点友好名由 `NodeBase.label` 派生，不另起平行表。
- **词汇**：NAMING N-29~N-35 与 N-42；排期以 PROGRESS 为准。
- **Agent 语义边界**：声明式结构化调用不等于开放式 autonomy。pipeline 是 orchestrator-workers；chat 边缘是 routing + 有界工具 loop；生产层有界 loop 节点是另一座受控形态。产品对用户仍是一个 assistant。

**Related**: ADR-028（RunPlan 持久化）、ADR-030（outputs 统一）、ADR-033（能力层双注册表）、ADR-025（计量）、NAMING N-29~N-35/N-42、AGENT_ARCHITECTURE、CHAT_ARCH §4/§5

## ADR-040: 配方 = 提示词——`recipe_id` 传输带与服务端播种退役

**Status**: Decided (2026-08-11)

**Decision**:
1. **发射的全部行为载荷 = 预填模板原文**：无 `ChatRequest.recipe_id`、无 `resolve_recipe_launch`、plan path 无校验块与播种块；配方卡发射与 composer 完全同径（建项目 → 上传 → 首条消息），服务端永不见配方身份。
2. **注册表瘦身不拆除**：`tasks` 工具链保留为启动对账自检的**声明形态**（flow ⊆ 编译图，AGENT_ARCH §4.2；语法经 ADR-043 与请求层统一），不进请求路径；公共卡面投影与示例资产按 `RECIPES.md` 当前边界保留，不恢复 inspect overlay 发射。
3. **后果自担**：计划形状由 LLM 从模板文案推断（composer 主路同款保证）——dock/草稿图可见 + chat 纠偏是产品核心循环，不再设隐藏确定性通道。

**Consequences**:
- 这些符号不存在：`ChatRequest.recipe_id` / `resolve_recipe_launch` / service.py 校验块+播种块 / 前端 `recipeId` 链路（useProjectLaunch / chat-stream / 项目页 router state）。
- 保留：`RECIPE_REGISTRY`（卡面 + flow ⊆ 对账自检）；`ChatMention.type="recipe"` 成员（历史消息 chip 渲染）。
- 「配方身份贯穿三站」无座位——服务端永不见配方身份：打勾流皮肤用节点友好名、chips 按焦点产物派生，均不需要配方身份（ADR-041）。

**Related**: MENTIONS §3（配方永不是 mention 的母判定）、RECIPES §7.1–7.2、ADR-036、AGENT_ARCH §4.2（对账自检不变）

## ADR-041: 项目工作区——结果画布、ChatDock 与 chat 自足

**Status**: Decided；布局偏好由 ADR-143 更新，移动端由 ADR-122 决定。

**Decision**:
1. `/projects/$id` 是同一项目工作区，不维护 `?overlay=chat/run`、fullscreen 第二聊天壳或另一套路由状态。ChatDock 只有 full / panel 两形态，MentionEditor 跨形态不得 remount。
2. `workspace_layout=auto|chat` 默认 chat。auto 下桌面在真实 world live / PLAN_READY 等条件满足时显示画布与 panel；chat 档与移动端始终 full 纯 chat。布局偏好只能关闭画布能力，不能在移动端强制开启。
3. **chat 自足**：画布隐藏时仍能上传、计划、授权、生成、交付与修订。终态锚卡和交付承接句只按 ADR-118 的真实环境与交付事实出现。
4. 画布直读持久 Product Graph；产物、来源与修订状态是图的内容，步骤执行不成为节点。run/chat 的工作叙事统一由 `WorkSegmentRow` 原位承载，取消从可见投影退役，真实失败保留。
5. 产物卡只读，不开放运行/接线 toolbar；选择、详情、复制/下载/发布等动作按当前 UI 合同落座。独立 ChatModal/AssetChatModal 不得复活，产物对话经 dock 与 @output mention。
6. `messages.focus_output` 只允许旧数据读容忍，不再新写；当前指认统一走 mentions。
7. 输入组、问题/确认 dock 与免责声明各有固定座位；不新增 Queue 条、第二进度面或流外状态 chrome。点阵只属于 FlowView。
8. 项目页的“下一步”必须始终可由当前世界状态回答：开始前由 chat/配方接住，计划中由 dock 接住，完成后由真实产物与事实性交付接住。成功交付不强制建议 pills；全败给确定性原因与至多两个可行选项。

**Related**: ADR-035/036/051/056/057/111/118/122/143；`docs/CHAT_ARCHITECTURE.md` / `docs/UI_GUIDELINES.md`。


## ADR-042: 身份根升格——定位（Positioning）为根、人设收窄为表达分区、选题库升一等公民

**Status**: Decided (2026-08-13)

**Decision**:
1. **身份根 = 定位（`positioning`）**，多实例（工作号/生活号 = 两个定位）。表 `personas`→`positionings`、FK 网 `persona_id`→`positioning_id` 全栈平移（speakers→personas 改名先例同构，纯机械刀）。
2. **三分结构**（行业话语映射）：内容定位 = 战略字段（territory/audience/differentiation/goals/guidelines/cta，**对话共建带确认**）；人设定位 = 表达分区（风格六件 + `voice` 块 + `brand` 块原样保留，`persona` = 逻辑分区词，不物理嵌套）；平台定位 = 渠道（`channel_accounts.positioning_id` FK + 公共档案 + 适配默认）。
3. **选题库升一等公民**：`topics` 表 + 生命周期（灵感/已排期/生产中/已发布/有数据）；选题卡 = **prompt 发射捷径**（点卡 → 关联素材与已选定位/渠道形成可编辑 prompt → 用户发送到唯一 `POST /chat` → 正常计划与授权 → run）。渠道不得由系统凭空默认，选题卡不直接建 run。来源 = 素材档案挖矿（主）+ 对标/回流信号（P2）。配方卡（新用户能做什么）与选题卡（老用户下一条做什么）分工并存，共用同一发射机构。
4. **project 退居内部执行容器**：用户可见工作单元 = 选题（管道）+ 产物（成果库）；projects/runs 留管线层做分组与重跑载体。
5. **素材档案上提根级**（assets 挂 positioning，back-catalog 挖矿底座）；**声纹资产用户层共享**（声带是人的不是定位的，多定位引用同一份克隆）。
6. **品牌/IP 留在承诺层**：落地页叙事继续 personal brand / 个人品牌；`brand` 维持皮肤块一词不动（不引入 `look`）；产品内导航用「定位」。

**Consequences**:
- ADR-037 D4 的「IP 容器加法式升格」路径不采用——身份根 = 定位（容器升格 = 定位根改名路径）。
- 启动条件、排期与验收只读 `PROGRESS.md` §1.1；本目标架构未实施，不自动插入当前 Film 主线，也不保留旧周次或目标日期作为承诺。
- 明确不做：对标作为支柱（与反 slop 定位相悖，P2 降级为选题校准信号）；工具格形态（chat 唯一意图面不变）；昵称取名场景（目标用户有名字有机构）。
- 母文档 `docs/POSITIONING.md`；MODULE_ARCHITECTURE / NAMING / CLAUDE.md 的现状描述随第一刀落地时改写（落地前它们仍是现状事实源）。

**Related**: ADR-037/038（身份模块现行边界）、ADR-016（spec family 不动）、ADR-041（项目工作区）、STRATEGY §5（用户到来即彷徨）、`POSITIONING.md`、`PROGRESS.md` §1.1

## ADR-043: 计划语法收敛——outputs 概念退役为派生（derive），plan path 并入工具链

**Status**: Decided (2026-08-15)

**Decision**:
1. **请求层无 outputs 语法——产物 = 编译图的派生投影（derive）**：产物类型词汇由节点 `output_type` 声明派生（N-32 不变；Output 表 / 产物行不动）。意图面唯一语法 = 工具链（task list）：plan path 与 chat loop 的 task-list 臂使用同一词汇。
2. **intent router 产出 task list**：槽位字段下沉为工具参数（writer 族 language / focus / tone_override；select_clips count / focus / aspect；translate_clip target_language + bilingual；dub_clip target_language）；无簿级修饰符（caption_languages / dub_languages / caption_bilingual / aspect 不存在）。unclear 不出默认全家桶——最小链或顾问式反问（CHAT_ARCH §3.3 姿态不变）。
3. **整条源材料化节点 `materialize_source`**（编译期自动注入的内部节点，不进入 `TOOL_REGISTRY` 的 LLM 可提议空间）：确定性全段 clip-spec（span = 素材全长，无 LLM 选段；源形态分发 video/audio/stills 复用 select_clips 的源决策，stills 经 align_stills 注入先例）。**画幅缺省 = `original`**（链无 clip 工具 = 比例跟源）——clip-spec aspect 第四档 `original`，渲染器 calculateMetadata 经 media-utils 实读源尺寸（stills 读首图，失败回退 16:9）；显式意图（spec / run.context）仍胜，人设皮肤的 aspect 是短片工艺默认、永不适用整条材料化。注入规则：链含 clip-spec 消费者（translate / dub / music / filler）而无 select_clips、且项目无既有 clips 可作用时注入（mode② 中途「作用于现有 clips」语义不变）；preprocess 按 requires 声明入图（不只随 director 前奏捆绑）；纯变换链不触发人设提取（ADR-040 先例）。fork 挂接：translate / dub 的 `after` 声明吸收材料化节点。
4. **计划投影 = 工具链 + 派生预览**：present_plan 干跑 compile_graph（纯函数）生成 derived 产物行与后续报价 fold，`presented_plan` 摘要同源。当前阅读面由 draft 图、累计方案与 dock echo 承担，不恢复第二套重型计划编辑器（ADR-111）。受控手改若存在，必须写回同一 task-list 事实；chat 修订携带 presented 摘要重提全链且用户当前指令恒胜。Start 以当前已呈现、已授权链编译起 run，服务端编译为行为事实源。
5. **派生类型 `video`（整条视频）= 纯展示词汇**：`materialize_source` 是编译期注入的内部节点（`NodeBase.internal`，自检豁免注册表席位），**不声明 `output_type`**——可请求类型注册表（N-32）保持原样；"video" 只活在派生预览行 / 步骤摘要 / 结果分组（节点落库的 Output 行仍是 `type="clip"`，渲染血统不变）。**结果画布消费方式**：`source_ref.segment.id === "full"` 的 clip 卡 caption 读作 "Video"（复用素材类型词），不读 "Clips"——fork 派生行携带同一 source_ref，翻译/配音版同样成立。不可请求、无 count_limits、无步进器。
6. **director 派工对齐改 keyed on 编译图**：storyboard 槽从编译出的生成节点（含参数）构建，不再从 `run.context.outputs` 读请求层槽位——多版本互补分配不退化，且与当前累计方案、真实草稿图及其受控修订所编译出的真实执行链严格一致。
7. **配方预设改写为 task list 形状**（multilingual-subs = [translate zh bilingual, translate fr, dub es]；image-video = [add_music] + 材料化/stills 自动注入——「变成短片」单数承诺自此为真），flow ⊆ 编译图对账不变；配方=提示词不过线不变。

**Consequences**:
- 请求层不再存在 `InferredIntent.outputs` / `outputs_explicit` / 簿级修饰符 / 前端 `OUTPUT_OPTIONS` 与 `SLOT_COUNT_*` 镜像。`projects.pending_brief` 持久化当前 task list 与计划事实；legacy outputs/slots 只做读容忍升级，不重新成为请求语法。
- Start 确认流、出生地 422、edit ops、WorkSegment/SSE、配方=提示词、chat 当前指令恒胜与顾问姿态保留。auto/ask 与 continuation 由 ADR-087/117/139 决定，不新增 `autonomy` 用户档。
- 整条源变换不夹带高光选段；各配方的 live/reserved 状态与具体产物承诺只读 `RECIPES.md`，不在本 ADR 冻结卡片示例。
- **目标解析不变量**：modifier→modifier 边只是排序约束——`_target_clips` 跳过 `spec.fork` 上游的 output_refs（fork 产出是新建派生行，其原件经链基座边即达）；否则全 fork 链会把派生行当新目标组合爆炸。morph 上游的 output_refs 照常下传（原地改写的交接）。`_target_clips` 的「项目现存 clips」兜底只含**本 run 之前**的行（按 workflow_step_id 所属 run 排除本 run），避免同胞 fork 的新鲜派生行污染兜底集。
- **重试 = 该类自己的链原样重跑**：受限 retry/targeted-run 面不得把 clip 一律改写成 `select_clips`，否则整条源变换会被换成高光剪辑。clips 族按原序原参数重跑，text 族按对应 writer；chat 域参数（target_output_id）剥离。legacy 读容忍（`legacyOutputsToTasks` / `_legacy_slots_to_tasks`）给 dub/translate 任务补 `fork: true`，保持 slots 时代的派生形态。
- derived 与估价 fold 共享同一次干跑编译；计划呈现、Start 与 echo 的当前规则归 ADR-070/083/111/117/139，不恢复任务数阈值、第二计划编辑器或强制“唯一下一步”。

**Related**: ADR-039（TOOL_REGISTRY——本条的语法家）、ADR-028/029（RunPlan / plan 级 dispatch）、ADR-040（配方=提示词）、ADR-041/111（结果画布与计划呈现）、STRATEGY §5（反打包）；详细契约 `AGENT_ARCHITECTURE.md`

## ADR-044: clip-spec 轨道模型——锚定存储 + 泳道编译产物 + TRACK_REGISTRY（12 操作闭包）

**Status**: Decided (2026-08-17)

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
8. **agent / tool 配套边界**：chat 使用当前有界工具 loop，拓扑仍由代码裁决；工具按用户任务命名和切分，不按轨道切分（「说到工厂时配工厂画面」可以是工具需求，「插入 layer」不是）。泳道投影/remap 是 pipeline 与共享包的确定性函数，不新增平行 tool。六个结构 op 当前 `llm_visible=False`；未来写者工具、层的用户呈现与任何 LLM op 词汇开放分别按 `TOOL_REGISTRY`、PROGRESS 和本契约评审，不因 schema 已存在就宣称能力已交付。
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

**Related**: ADR-016（契约锁定——L3 注记以本条为准）/ ADR-020（stills Ken-Burns 拒绝与本条 transition 的边界：枚举进场边可、动效画廊不可）/ ADR-026（C2PA fold——layers provenance 必填）/ ADR-029（虚拟产物段进主时间轴）/ ADR-032（快照 undo——锚定面是其存储面）/ ADR-033（能力层双海拔）/ ADR-035（可操作画布永拒——泳道期权的前提门）/ ADR-039（注册表时刻同款迭代）/ ADR-043（派生投影同款哲学）；母文档 `docs/RENDERING.md`；详细契约 `RENDERING.md`（§7 配套层 / §8 附录 12 操作走查全表）

## ADR-045: 智能分镜能力线——YuNet 视觉引擎 + speaker_map 素材级事实 + crop_track 稀疏关键帧

**Decision**:

0. **检测空间 ≠ 出图空间**：降采样找框、坐标映射回全分辨率取景——访谈 640 档 / 登台原生档（640 档在远景漏小脸）/ 远景 2×2 拼块兜底（spike 实证：可收回 4/7 漏检，剩余为片尾淡出无人画面）。
1. **视觉引擎 = YuNet（MIT）**：opencv_zoo 官方权重（bbox + 5 点关键点含嘴角），**权重 vendor 入仓库**（MIT 允许再分发；~230KB 消除一切下载/代理失败面，dev 与服务器零网络依赖）+ MIT LICENSE 文件并置；运行时 = `opencv-python-headless` 5.x（`cv2.FaceDetectorYN` 原生 API，NMS 内置），配 5.x 的动态输入封装 `face_detection_yunet_2026may.onnx`（2023mar 系同权重，WIDER Hard 0.7503 最强线；int8 变体全禁——精度降且 5.x 有全漏检 bug）。引擎缝住 `app/providers/vision.py`（懒加载进程缓存）；帧网格拼装 / 词轴切段 / 选页取窗等执行工序住 `app/tools/reframe/`，provider 缝与工具包职责不得互换。
2. **隐私边界**：全程不做人脸识别（不知"是谁"）——只有位置与嘴部运动，全程不出网（faster-whisper 同款 EU 姿势）；密集计算全部本地化，云调用只剩稀疏语义判定。
3. **话轮归属 = 嘴部 ROI 运动能量主 + M3 仲裁辅**：whisper 词轴切话轮（间隙 ≥0.6s 断轮）；静态机位下逐话轮对比各说话人嘴部 ROI 帧差能量，能量比 ≥ 阈值（初值 1.6×，以真实片校准）确定归属；模糊轮（双人同动 / 能量比不足）M3 网格仲裁（每片 1~5 次云调用封顶）。M3 从"主力判定"降级为"模糊仲裁"——静帧猜"谁张嘴"恰是其最弱形态。
4. **speaker_map = 素材级事实**：VIDEO 第二 PROCESSOR（接 ASR 后，`asset_processing.py` 先例——素材级 / 可重跑 / hash 复用；AUDIO 不上——信号是视觉的，音频没有可检的框），**形态闸门先行**（whisper 话轮密度 + 1~2 次 M3 网格判多人/访谈才跑全量归属；单人素材零增量成本）。数据形态：`Asset.meta.speaker_map = {form, speakers:[{id, screen_hint}], turns:[{start, end, speaker}]}`（meta 先例：language）。当前消费者包括 `reframe_clip`、访谈选段/引用定位与 perception 读工具；本人含量门禁等扩展未实装前不得宣称完成，排期归 PROGRESS 需求池。
5. **crop_track = 稀疏决策关键帧**（data 家族轨，源时间轴）：`[{t, x, y, scale}]`——关键帧 = 一次取景决策（"这里切到 A"），非稠密逐帧；渲染采样器在相邻关键帧间固定 smoothstep（~8 帧，渲染常量不进契约——transition 枚举同哲学：枚举可、参数画廊不可）。**防眩晕分工**：最短驻留 / 死区 / 最大转速 = 写侧约束（`app/tools/reframe/` 工序，参数以真实访谈片看调）+ checks 住户校验（与 reframe 包一并回归，禁先注册空座位）；采样器只做平滑插值，永远简单。空轨 = 静态 `crop` 退化形态（语义不变）。
6. **`reframe_clip` 工具包**：三模式 `interview_switch`（双人访谈分镜，静态机位按说话人切换）/ `speaker_follow`（单人中景动态追踪）/ `static_center`（静态中裁，回退档）+ `auto`（按 speaker_map.form 选模）。形态写者写 `crop_track`（+静态 `crop`），`TrackDef.owner` 登记即得撞轨 422；对话可调用走 task_list（六 op 继续 `llm_visible=False`，不开放 LLM op 词汇）；估价 = `detect_seconds` 计量（自有基建零定价，`render_seconds` 先例；挂在本 run 选段后时编译期不可知，报 NULL）。
7. **一引擎两模式**：同一 YuNet 在访谈素材稀疏采样（1~2s 间隔刷新位置）+ 登台素材稠密采样（3~5 帧一检出轨迹）——复杂选型收敛为**一个引擎两种采样密度**；`speaker_follow` 不需要第二套选型。

**Alternatives（翻案条件随附）**:

- **SCRFD（InsightFace，侧脸精度轻量最强）**：预训练权重非商用（官方定价页实证）。**翻案阶梯**：YuNet 侧脸检出实测不达标 → MediaPipe（Apache-2.0）→ 仍不足则购买 InsightFace 商用授权（产品化路径）。
- **pyannote 音频话轮分离**（纯音频 SOTA）：torch 重依赖 + HF 门控模型。**翻案条件**：嘴部运动能量在真实访谈归属准确率不达标（双人小动作多 / 一方说话几乎不动嘴）。
- **自训检测器**：架构 MIT 自由，但标准训练集（WIDER FACE）同样仅限非商业研究 + 1–2 周 ML 工程；蒸馏 SCRFD 权重产伪标签仍属非商用权重派生。**翻案条件**：人脸分析成为产品核心差异点且有常驻 ML 人力。
- **M3 全程判定**（零新依赖）：静帧网格猜"谁张嘴"是其最弱形态；逐帧追踪贵且抖（60s 素材 0.5s 间隔 = 120 次调用）。只任形态归类与模糊仲裁。
- **稠密平滑关键帧 + 线性插值**：契约肥大、防眩晕参数散落数据。**翻案条件**：sparse + smoothstep 在真实素材出现可见跳变且写侧平滑无法吸收。

**Related**: ADR-044（轨道地基；crop_track 进场路径与受控轨契约）/ ADR-016（渲染器黑盒——采样器只进 packages/clip）/ ADR-020（Ken-Burns 拒绝的边界：crop_track 是 video 源取景决策轨，非 stills 动效）/ ADR-026（speaker_map 不涉 C2PA——分析事实非生成内容）；详细契约 `RENDERING.md`；当前验证状态、开放需求与排期归 `docs/PROGRESS.md`


## ADR-046: Studio 视觉骨架——token 灰阶、浮层纵深与 Home 单一入口

**Status**: Decided；完整视觉规格 = `UI_GUIDELINES.md`，本条只保留结构决策。

**Decision**:
1. Studio 采用中性灰阶与 shadcn token；层级优先由填充区分。in-flow 卡、composer、媒体 tile 永不带 shadow，shadow 只属于浮层；禁可见粗描边与临时色值。
2. 小圆角为默认；`rounded-full` 只保留 CLAUDE/UI_GUIDELINES 列出的例外。浮层统一 `overlay-surface`，overlay chrome 只用 Dialog primitive，不手写 backdrop。
3. `_app` 不设全局 AppHeader。主题/语言/账户偏好归 AccountConsole/SettingsDialog；通知铃是 md+ 内容区右上角唯一浮动 chip，该角全站保留。
4. <md 的品牌、Projects、通知与账户入口收进玻璃 MobileHeader；不保留第二套浮动触发器或可达的桌面侧栏抽屉。
5. Home 是 `h-svh` + 单一内部 scrollport。hero 只有一行指向 composer 的问句，品牌由侧栏锁up/MobileHeader 承载；页面唯一目的地是输入框。
6. composer 可在滚动中钉底并压成单行 stadium 条，这是圆角例外之一；实体 chips、上传生命周期与发送纪律按当前 composer 合同，不增加第二发射入口。
7. 配方货架在 composer 之下，卡片点击只预填 prompt；空货架不渲染。真片/占位片的证据边界见 ADR-048 与 Home 当前合同。
8. 设置使用共享 SettingsDialog，不另建平行设置页；`/settings` 仅保留当前 OAuth 回调兼容职责（若仍存在）。

**Related**: ADR-040/041/048/051/118/143；`docs/UI_GUIDELINES.md` / `docs/tasks/home-creation-entry-refresh.md`。


## ADR-047: 产物质量线——剪辑师层 + 有界质检环 + 评审回 chat

**Decision**:

1. **剪辑师层（editor agent）**：storyboard 与 clip-spec 编译之间新增 timeline 创作层——N-30 声明式新成员（团队的下一成员），吃理解层节拍地图、吐节拍方案（beat plan：图序/运动/切点/强调的逐拍决定）。**单发上限 ≤8–15 拍 / 30–45s**（三源收敛），超出走大纲→逐拍两段，拍间靠显式交接状态（时间锚点/上一拍视觉态/已用素材清单/累积强调历史）。
2. **理解层 v2（节拍地图）**：`MaterialUnderstanding` 扩为素材级——climax/emphasis/quotables/topic boundaries/visual anchors/filler regions，上传时跑 + asset 级复用（汇合需求池「素材理解前移」）。铁律：词级时间戳确定性地基 LLM 永不覆写；**语义强调与声学强调分字段存储**（不一致本身是仲裁信号，预合并 = 自信地错且不可溯源）。
3. **质检环（verify 节点升级）**：使用结构化 `QualityBounce` 反馈，升级裁决语义——确定性优先（可测量项零 LLM）/ 逐轮独立打分 **best-not-last** / 字段白名单最小 diff 修复 / 首轮过即跳轮 / 双败升级 interrupt（复用既有机制；fidelity 类维持 needs_human 非阻塞徽章）。LLM judge 在纪律下引入（pairwise 冻结基线 / 样例锚定 / 证据先行 / 校准集）。
4. **重规划边（tool-loop 否决边界明文化）**：常备否决的对象 = **模型当编排者**（ReAct 式运行时决策），不翻案；**节点内有界环**（单目的、≤2 轮、结构化反馈、图调度进出）= 合法形态。质检失败的机械路由：修复所需信息不在理解层 schema / 超出单节点参数域 → 交还意图层重规划（汇合需求池 P1「执行中自适应重规划」）；retry 不中自动升级（schema 错误首 pass 常伪装成参数错误）。素材级不足走诚实降级（标题卡开场/换素材），**禁假造钩子**。
5. **评审回 chat**：评审 AI 钩子质量走 chat 收敛（ADR-041），节拍方案（§1 beat plan）是 chat 评审的可寻址界面；无钩子预览闸——渲染服务无 `preview:{seconds}` 参数、无 previews 提问载荷 / HookPreview / HookTrim / swap_hook_shot，降级由 AI 自动 set_title 评估（ADR-049）。
6. **尺子先行**：施工顺序 = 解剖（craft 清单 + 四层归因证据表）→ 理解层 v2 → 剪辑师 → 质检环 → 节拍方案产品面（接 ADR-049 评审界面落位）。§2.1 craft 语法表全部数值 = 编辑部惯例先验，解剖校准前不作验收标准。

**Rationale**: 质量的 80% 在隐性剪辑知识的形式化（外部评审收敛），而形式化的载体已有（指令包装配注入 + track 模型 + 词级时间戳/speaker_map/reframe 数据资产）；缺的是"谁做逐拍决定"的层与"谁检查"的环，不是地基。三源独立否决模型驱动编排——DAG 的编译期估价/确定性执行正是有界环能安全存在的前提。外部评审全部结论 = 模式先验，解剖与台账产出自己的数据后校准。

**Alternatives（翻案条件随附）**:

- **模型驱动编排（tool-loop）**：三源独立否决（成本失控/不可审计/参数坍塌）。**翻案条件**：台账落地后的实测证据（repair 失败率/单发上限实证）证明声明期分工在某场景结构性不足。
- **每表面独立 agent 声明**（MiniMax 剪辑 Agent/导演台 Agent 式）：维护漂移 + 跨面认知断层；我们的答案 = 同一它 + 作用域上下文（ViewScope，若实施须先登记当前合同）。**翻案条件**：场景上下文组装的边界泄露实测不可控。

**Related**: ADR-039（四层地图 + N-30 声明机制）/ ADR-016（对应 spec 契约不动）/ ADR-041（表面纪律：进度不进图、编辑走 chat）/ ADR-049（钩子闸不存在）/ N-42（指令包装配注入——剪辑工艺包的载体）/ N-25（用户面单助手不破）；详细契约 `AGENT_ARCHITECTURE.md`（施工与验收）；需求池「质检节点」（提级 P1）/「agent 调用台账」（三信号 schema）/「执行中自适应重规划」（路由判据）/「素材理解前移」（汇合理解层 v2）/「节拍方案产品面」（接 ADR-049）

## ADR-048: 配方与 Home 货架——用户任务组织、提示词发射与样片证据分级

**Status**: Decided；当前卡片与样片状态 = `RECIPES.md` / `tasks/home-creation-entry-refresh.md`。

**Decision**:
1. **货架以用户任务组织**，不再把“产物介质”设为唯一分卡轴。输入路径与工艺决定真实可行性；渠道是下游适配，不默认按 LinkedIn/TikTok 等渠道复制卡片，也不得在 prompt 中发明用户未点名的平台。
2. 卡存在的理由是接住真实高频任务并送入主 chat 闭环，不为覆盖所有能力而堆卡。覆盖、回访与选题需求归定位/选题层，不靠增加货架数量解决。
3. **配方 = 提示词**：卡片全部发射载荷是 `promptTemplate`/demo prompt，点击只预填 composer，不自动发送、不建项目/run、不打开模板编辑器；服务端不接收隐藏 recipe_id。
4. 准入至少过三门：真实用户场景、当前能力或明确 PLANNED 边界、诚实且有辨识度的示例。卡可点、demo 可播与制作全旅程通过是三类不同证据，不能互相代替。
5. 当前阵容、排序、显示/隐藏与 tab 归前端 `RECIPE_FAMILIES` 及服务端 `/api/v1/recipes` 各自注册职责；不在 ADR 冻结“八卡”或固定顺序。空 shelf/sub/family 不渲染，隐藏卡片不等于删除能力。
6. 真片与布局占位片必须分开记录。占位只证明布局、画幅、播放与预填，不证明对应制作能力；替换真片后仍需独立走 Chat→方案→授权→制作→交付验收。
7. 文案只写用户要点名的具体任务，不做“一次输入全套出”或传播效果承诺。已有用户草稿不得被预填静默覆盖；离屏暂停与声音单例是货架基本行为。

**Related**: ADR-040/046/060；`docs/RECIPES.md` / `docs/tasks/home-creation-entry-refresh.md` / `docs/VERIFICATION.md`。


## ADR-049: 渲染前评审边界——无 hook 预览闸，Film 分镜审阅独立

**Status**: Decided；仅裁决 clip hook 预览闸，不取消 Film 的创作物审阅。

**Decision**:
1. clip 链不设置 `hook_gate` / `release_renders`、preview-seconds 外部参数、HookPreview/HookTrim 或 `swap_hook_shot`；报价与方案在 chat 中呈现，渲染按既有执行与质量链继续。
2. 具体切点、标题等修订走受控 edit ops / chat；无需为“先看钩子视频”增加一条付费预览流水线。
3. 中间创作方案若需要用户判断，应以可理解、可寻址的产品事实呈现，不用额外视频闸替代方案本身。
4. **Film 例外**：`design_storyboard` 是创作方案的呈现，不是 hook preview。作品首个分镜版本必须完整呈现并等待用户批准后制作（ADR-144）；后续 hold、普通修改与重制分别遵守 ADR-134/137/139。auto 不得跳过此首稿审阅。
5. 本条不授权 LLM judge 或自动降级替代确定性文件/保真检查；质量机制按当前 AGENT_ARCHITECTURE 与验证合同实施。

**Related**: ADR-047/070/087/117/129/134/139/144。

## ADR-050: 会话不跨长等待——计量内存累积 + 渲染会话收窄 + runner 禁污 Session-2 节点 + DEFERRABLE FK（D9 死锁族）

**Status**: Decided (2026-08-28)

**Decision**:

1. **计量改内存累积（`app/metering.py`）**：`bind_workflow_step` 绑定 contextvar 内存台账；`record_usage` / `record_media_usage` 只改内存、**零 SQL**。`execute_step`（orchestrator.py）在执行尾段用 `merge_accrued_cost` 归并一次写入——成功 / Suspend / QualityBounce / 瞬时重试 / 失败五个终态分支全部记账（每节点 N 次写 → 1 次写）。cost 形状 `{prompt_tokens, completion_tokens, fixed_cost, units?}` 不变；跨 attempt 累加（与旧 per-call 机制语义对齐）；空台账 → cost 保持 NULL（估价对账 SQL 继续忽略未计量节点）。**不加表、不加字段**。
2. **render_output 会话收窄（`app/pipeline/rendering.py`）**：短 session 快照行数据（spec / files / project_id / user_id / lang）→ **无 session** 横跨渲染 POST → 新短 session 做 guarded 终态写入（morph 竞态守卫条件不变）。`_mirror_superseded_node` 签名由 `Project` 改收 `lang`。
   - guarded-write 纪律 = **身份守卫**（ADR-079）——render 三处终态写谓词 = `render_claim_token=:mine`（rowcount 检查不变）；execute_step 四尾同样 = 条件 UPDATE + rowcount（fenced → rollback + 零副作用）。会话收窄纪律（短 session / 无 session 横跨长等待）不变。
3. **runner 禁污 Session-2 节点（铁律）**：Session 2 内对 step 行的写只属于 execute_step 尾段结算；runner 中途要写 spec 一律走 `step_display` 的 own-session 原子写（`_pop_spec_field` jsonb `-` 减法 / `_set_*` jsonb_set）。两处 feedback-pop（`derivative_dispatch` / `clips/node`）已改 `_pop_spec_field`。
4. **四条 runner-父行 FK 改 DEFERRABLE INITIALLY DEFERRED**（migration `c3a9e71f52d0`）：`outputs.workflow_step_id` / `outputs.project_id` / `operations.project_id` / `workflow_steps.run_id`——Session 2 中途 INSERT 子行不再对父行持 KEY SHARE 至提交，父行写者（display writers / maybe_finalize / run 状态翻转）永不被 mid-run 锁窗口卡住。完整性不变，检查挪到 COMMIT。
5. **DB 保险丝**：`ALTER ROLE <app_role> SET idle_in_transaction_session_timeout = '3600s'`——**部署新环境时必做**（本条即部署说明）。保险丝是兜底不是许可，只防永久 wedge：Session 2 横跨单次 LLM await 是保留设计，而单次调用在 provider 慢窗口的纯等待可达数十分钟（多模态大生成流式 trickle 时 read timeout 不跳），1 小时不误杀健康事务、照样把永久 wedge 收敛为有界失败。排队与制作的小时级等待必须走队列行状态（row 等认领），永不持事务空转——保险丝不为那种形状服务。
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

## ADR-051: ChatDock 与工作叙事——单一路由、两形态与统一提问面

**Status**: Decided；行为全文 = `CHAT_ARCHITECTURE.md`，视觉细则 = `UI_GUIDELINES.md`。

**Decision**:
1. 项目页只保留画布 + ChatDock 工作区，无 overlay 路由、fullscreen 第二壳或多 chat。composer 发送只负责建项目/上传/导航，首个意图仍由 `POST /chat` 处理。
2. ChatDock = full / panel；移动端恒 full。panel 可最小化，但 agent 新言语、待决提问或新指认必须能召回，用户不能永久藏住新信息。
3. **工作段统一**：chat 与 run 的活动由 `WorkSegmentRow` 原位承载，active→settled 不换第二组件。工具完成不等于收段；正文首字实际经打字机释放或真实终态才收段。live Thinking 不可展开，真实 failed 留安静告警，cancelled 不留删除线。
4. 提问按内容形态分：开放文字问是普通消息；固定选项统一 OptionDock，编号与作答语义一致；`default_path` 是机器事实，不要求散文宣告，也不增加第三种半结构化 pill。
5. 卡面确定性直改走 `POST /projects/{id}/graph/revise`，dock 零消息；chat 修订仍走 `POST /chat`。两者共享图写门、版本与执行边界，不新增第三执行通道。
6. 模型/provider 可在详情面作为事实陈列；节点面永无模型选择器、SKU 货架或虚构能力。真实文件、状态和数字优先于装饰性进度。
7. 输入组、附件 chips、问题 dock、免责声明与 placeholder 是稳定解剖；placeholder 只教授真实存在的 @mention/上传能力，按注册表内容区分 assets/nodes，不承诺 slash 命令。
8. 点阵只属于 FlowView；dock 与消息流不复制。免责行指向真实发布前检查风险，不被模型当作言语模板。

**Related**: ADR-041/053/056/058/070/073/108/110/118/122；`docs/CHAT_ARCHITECTURE.md` §1/§8。


## ADR-052: 对话工作流母蓝图——厚 agent + 双引擎分离 + brief 账本 + ask 一等动作 + 当前计划呈现 + 有界 loop 节点

**Status**: Decided；概念母文档 = `DIALOG_WORKFLOW.md`；当前实施状态与排期归 `PROGRESS.md`

**Decision**:

1. **厚 agent 判词（ADR-039）**：产品 = 一个厚 agent（assistant 单身份，N-25 双轨不变）；其「厚」= **声明式部件的组合厚度**（Agent 漏斗 × NodeBase × compile_graph × 工具注册表 × brief 账本 × 提问机器），不是 autonomy。本系统无开放式自主是设计不是缺口——chat 边缘 = routing + 有界工具 loop（ADR-077），pipeline = orchestrator-workers 模式；`Agent` 类 = 声明式结构化调用（= AI SDK `generateObject`），类名不动；业界 autonomy 义永不适用于任何内部模块，开放式 autonomy 维持永拒。
2. **双引擎 workflow（概念统一，引擎分离）**：对话 = 事件驱动状态机（router + brief 账本 + 提问机器）；生产 = 编译 DAG。**对话永不编译进 DAG**（开放轮数 / 人是环境 / 报价不适用）；两引擎唯一接口 = 当前计划的工具链（对话引擎产出提议，代码编译裁决，run 出生地唯一，ADR-043 不变）。
3. **canonical 词汇，零自造词**：chat 边缘双件 = **intent router**（`plan_agent` / `chat_intent_agent` 同概念两相位 prompt，相位 = 上下文参数）；`director_understand` → **`understand`**、`director_plan` → **`plan`**；`pending_intent` → **`pending_brief`**。业界坐标：Anthropic routing / Plan-and-Execute / AI SDK generateObject / LangGraph node·step。判例归 NAMING N-43~N-47。（plan 归两主：chat 侧计划书义 = plan path / presented_plan，pipeline planner 义不动；存储字 `task_book` / `book_summary` 冻结。判例 N-44 / N-52。）
4. **brief 账本（P0）**：对话引擎的结构化状态（`projects.pending_brief`）——槽位 topic / audience / tone / constraints[] / material_state，**每槽带来源 user-stated > inferred > default，代码侧合并**（LLM proposes, code decides 不变）；账本 = 上下文工程主压缩件，累积 prompt 叙事降存档位。
5. **ask 一等动作（P0）**：pre-run 相位动作集 = **ask / draft / answer / start**（draft = 起草/修订当前计划，从不生成）；ask 复用 shape C（choice 3 项——真二元抉择降 2，对齐 FLORA/Opus 三选项节奏——+ freeform，走 dock 提问机器）。**提问策略三条**：一轮最多一问只问决定质量的那个缺失槽 / 选项一词可答、freeform 恒在 / 默认路径恒带（机器可读、散文零宣告——ADR-103）——**每轮一问、每问可一词答**（顾问姿态的本义是不让用户做创作题，不是不问）。**计划呈现门槛**：brief 有根（主题 / 素材 / 明确配方，三者居一）才呈现计划 dock；zero-material safety net / no-material lift 同属此策略。
6. **计划阅读面 = 当前累计方案 + 真实草稿 + dock**：不维护第二套计划编辑器或空白创作框；槽位有值才显示，修订走受控卡面手势或 chat。`default_path` 只骑机器参数，散文零宣告（ADR-103）；Start/echo 按 ask/auto、制作意图、费用与 Film 首稿规则决定。
7. **角色 = 节点的 display 属性**：工作流内部永远函数名（动词族零人格）；用户可见进行态叙事 = 节点声明上的可选展示属性（`task_name` 机制升级位），**默认写工艺不写人**（「正在剪辑成片…」✓ /「剪辑师正在…」✗）——N-24 禁令对象是 assistant 的班子包装，步骤级工艺叙事是另一层；人形叙事 = 翻 N-24 的案，门槛维持。
8. **有界 loop 节点 = 生产侧 agent 性的合法座位**：编译期排不出拓扑的活（搜索 / 阅读，步数不可预知）由 `NodeBase` 子类承接——内部 mini tool-loop（工具 = `app/tools/` 现成注册表）+ **三护栏**：迭代上限（节点声明）/ 报价 = fold（上限 × 单次，估价体系不破）/ 对外 = DAG 单节点（拓扑 / 占位 / SSE / 诞生编排全无感）。业界同构：LangGraph subgraph / Mastra agent-in-step / Anthropic agentic component。会话层有界工具 loop 同合法（ADR-077：生产封闭 / 服务收编 / 执行永拒）；开放式 autonomy（无界循环 / 自主改拓扑 / 自我 steering）永拒不变。首个试点 = research 节点（产出 research brief artifact 喂 writer）。

**Consequences**:

- 概念母文档 = `DIALOG_WORKFLOW.md`（本条的完整展开）。
- 顾问姿态四律① = 每轮一问、每问可一词答（CLAUDE.md 同文）；ADR-043 计划链契约不变（接口 / 出生地 / 链语法原样）；ADR-047「模型驱动编排 = 禁；节点内有界环 = 合法」与有界 loop 节点同构（环在节点内、有界、对外单节点）。
- NAMING N-43~N-47（厚 agent 判词 / router·understand·plan 更名 / brief 账本 / 角色 = display 属性 / 有界 loop 节点）。
- 悬案归 DIALOG_WORKFLOW §8（槽位优先级参数 / router 两相位实例合并时机——待真实对话数据回收）。

**Alternatives（翻案条件随附）**:

- **对话编译进统一 DAG**（单引擎）：否决——DAG 三大编译期保证（报价=fold / 拓扑可排 / roster 投影）对开放轮数、人是环境的对话不成立。**翻案条件**：无（结构性）。
- **保留空文本框作为「高级选项」**：否决——空框 = 创作题，与「每问可一词答」同体两面；修订通道（点值改 / 聊天改）已全覆盖。**翻案条件**：真实用户点名要自由书写区且两通道被证实不够。
- **人形角色叙事**（「剪辑师正在…」）：否决——工艺叙事发稿；人形版 = 翻 N-24，门槛维持。

**Related**: `DIALOG_WORKFLOW.md`（概念母文档）/ ADR-039（Agent 归一）/ ADR-043（计划链契约）/ ADR-047（有界环同构）/ ADR-051（提问 dock 形态 = ask 的渲染面）/ NAMING N-24（角色隐喻禁令边界）/ NAMING N-43~N-47（词汇判例）/ 外部词汇坐标（Anthropic《Building effective agents》/ LangGraph / AI SDK / Mastra / Agno / OpenAI SDK）

## ADR-053: 提问机器形态律 + 插话支持——文字问对话形态 / 选项问阻塞形态 / 判定结算与提醒尾

**Status**: Decided (2026-09-04；详细契约 `CHAT_ARCHITECTURE.md`；规格 = CHAT_ARCH §8.5 + DIALOG_WORKFLOW §6)

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

**Related**: ADR-052（判词 5 提问策略——本条为其落地形态）/ ADR-051（条款 3 形态律以本条为准）/ ADR-041（dock 三可见性态不受提问影响）/ CHAT_ARCH §8.5（规格落点）/ DIALOG_WORKFLOW §6（不变量登记）/ NAMING N-49（提问机器词汇批）/ 详细契约 `CHAT_ARCHITECTURE.md`

---

## ADR-054: 计划呈现密度——当前累计方案、真实草稿与统一 Start

**Status**: Decided；当前呈现与授权见 ADR-111/117/139，Film 首稿见 ADR-144。

**Decision**:
1. 不维护两套计划卡、两种 Start 语义或按任务数切换确认机器。计划内容必须去重呈现，真实草稿图/当前累计方案与世界状态是范围事实。
2. Start 是否出现、是否需要执行或费用确认由服务端 `evaluate_start_gate` 和当前授权事实决定，不由任务数量决定；口头、typed answer 与 dock Start 共用同一机器。
3. auto 不创造制作意图；ask 的 echo 用一句朴素、可一词回答的方案判断问句收尾。无制作请求、纯讨论或“先看看”在任何档都等待。
4. 保留的必要理由：呈现重量应匹配真实决策，不让空表格、重复清单和第二确认面与用户争夺注意力；但这不再通过旧密度阈值实现。

**Alias**: 旧文档引用 ADR-054 的“密度律”时，按本条解析到当前呈现/授权合同，不恢复旧卡面。

## ADR-055: 积分系统——credit / wallet / credit_transactions + hold→capture→release + configs 表 + 消耗比例参数 + 负余额允许

**Status**: Decided (2026-09-05；母文档 `docs/BILLING.md`；支付 / 套餐经济 = W11)

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

## ADR-056: 桌面 panel 双几何与积分读面

**Status**: Decided；两形态与移动端现行法 = ADR-122/143。

**Decision**:
1. ChatDock 只有 full / panel。桌面 panel 支持 float 与 docked 两种停泊几何，使用同一消息机器与 dock surface；偏好可持久化，但不是第三聊天形态。
2. **保草稿是承重结构**：单一 root、恒渲染容器和稳定子索引保证 MentionEditor 在 full↔panel、float↔docked 间不 remount；草稿、chips、焦点不得靠有损序列化重建。
3. panel 的消息流、问题/确认 dock、免责声明与输入组各有固定区域；不增加折叠状态条或 Queue 条。minimize/LogoMark 召回只属 panel，移动端不复制。
4. 过渡只投影真实布局变化；水合/历史首帧不重播，背景 refetch 不动相机。视觉尺寸、发丝线与圆角细节以 UI_GUIDELINES 和当前组件为准，不在 ADR 冻结像素。
5. `CreditsPill` 是项目页积分读面：余额、held 与最近台账来自 `/wallet` 现有端点；失败静默保 “—” 防双报，不展示 USD、不伪造 Upgrade/购买入口。用户面台账只呈可理解语义，不暴露 hold/release 内部流水。

**Related**: ADR-041/051/055/118/122/143；`docs/BILLING.md` / `docs/CHAT_ARCHITECTURE.md`。


## ADR-057: 持久 Product Graph——唯一图事实、受控写门与确定性修订

**Status**: Decided；product visibility/rank 由 ADR-086/098 补充，transcript 由 ADR-113 重基线。

**Decision**:
1. 项目拥有持久 `graph_nodes` / `graph_edges`。chat 建/改图，授权后 run 在同一批节点上执行与填充；修订继续作用于同一产品世界，不为每次 run 复制第二套展示 DAG。
2. 执行内核仍使用编译 DAG、NodeBase、Postgres 队列与 hold→capture→release。`workflow_steps` 是执行/计量事实，**不是画布节点**；Product Canvas ≠ Execution Graph。
3. 图变更只经 `apply_wiring_ops`，付费 run 只经 `create_run`。chat 是唯一意图面；手动拓扑手势不开放，模型也不能直接 CRUD 数据库。
4. 图先完整呈现后运行；动态生长只是呈现编排，不把 execution step 逐个滴成产品节点。草稿、running、done/failed 是同一节点身份的状态迁移。
5. 节点由媒介类型、prototype/产品角色与业务 label/tool 分轴描述；新类型默认隐藏，必须声明 product visibility。transcript 是 asset 内容，不是新图节点；探索产物不参与执行闭包、报价或 rank。
6. 确定性卡面修订由代码构造 ops，走 `/graph/revise`，dock 零消息、乐观回显不回闪；自然语言修订走 `/chat`。两路共享版本、scope、费用与 Start 守卫。
7. 只读图不等于显示层可另算世界：rank/visibility 由同一服务端产品拓扑规则提供，前端不恢复第二套 depth、transcript 合成边或 canvas_hidden 特判。
8. 端口/边表达真实消费关系，不是执行顺序装饰；呈现需要不得反噬拓扑。节点尺寸、锚点和 rank 是声明式几何，背景 refetch 不移动既有世界。
9. 命名只来自 LLM 建图 name 或世界自证；内部 wiring/spec/tool 词不由 assistant 倒给用户。clip-spec/film-spec 平级、mentions 双端注册和计费内核不变。

**Related**: ADR-035/036/058/062/063/086/089/097/098/113/118；`docs/MODULE_ARCHITECTURE.md` / `docs/CHAT_ARCHITECTURE.md`。


## ADR-058: 展示命名、确定性修订、mentions 与消息秩序

**Status**: Decided；活动/相位现行法 = ADR-110/133，数组秩序 = ADR-108。

**Decision**:
1. **展示命名二源律**：用户可见命名只能来自 LLM 建图时的 `name`（null/空读容忍）或世界自证（产物徽标、节点状态、真实数字）。冻参模板永禁；手改计划后清空旧 name，回退到当前参数的诚实标签。
2. run 标题与收据读生产该 run 的真实提案/context；旧行无名时使用诚实回退，不 retroactive 编造。参数是执行事实，不自动成为文案。
3. **卡面直改是确定性图动作**：代码构造 ops，经 `/graph/revise` 与唯一写门执行，dock 零消息；节点状态和真实产物变化就是反馈。乐观回显不得在 stamp 对齐时回闪。
4. **自然语言修订是意图**：仍经 `POST /chat`、产品语义工具和同一图写门。focus_output 不再新写；@output mention 与可选 quote 是服务端确定性解算的指认依据，pin 恒胜。
5. 活动、散文与 run 工作段各有真实事实来源。不要求固定 `thinking→drafting→creating_run` 三拍：通用 LLM 黑盒窗只显示基座 Thinking，只有结构性不同且真实发生的活动才拥有具名相位（ADR-133）。
6. 一切可见消息按 conversation `messages.seq` 排序；created_at 只用于时刻/耗时，不作第二排序键。SSE 与回放共用 reducer，终态不能靠时间戳猜顺序。
7. 打字机 drain、DeferredFrames、首显收段和稳定 birthKey 是跨路径共同约束；不能用“整回合状态行”吞掉当前活动或让散文瞬移。

**Related**: ADR-034/057/060/069/073/099/108/110/133；`docs/MENTIONS.md` / `docs/CHAT_ARCHITECTURE.md` §8。


## ADR-059: 图持久化分裂 flush 律——SQLAlchemy 无 relationship 不排序裸 FK 混插

**Status**: Decided (2026-09-10)

**Decision**:
1. **写口分阶段 flush**：`graph_store.persist`（图唯一写口）分两段 flush——nodes strictly 先于 edges，代码带「永不合并回去」注释。不是"这次顺序碰巧对"，是把排序从 ORM 骰子收归写口纪律。
2. **律**：同 session 内跨表**新行**若无 relationship 挂接，写口必须分阶段 flush；禁赌 UOW 的排序行为——它只对 relationship 负责，不对 FK 列负责。

**Consequences**: 此律适用于一切多表同事务写口；守卫只锁 nodes-before-edges 的结构顺序，不保存某次 probe 或剧本输出。

## ADR-060: echo 防编造律 + post 渠道中立——agent 永不发明用户没说过的平台

**Status**: Decided (2026-09-10)

**Decision**:
1. **echo 防编造律入 prompt**：回声解剖增一条——只回述用户说过的（作品 / 语言 / 数量），**永不发明平台或场所**（"LinkedIn" / "X" / "newsletter"）；a post is just a post until the user names where it lives。
2. **固化点全量渠道中立化**：工具描述（"long-form social post"）、step 摘要（"Wrote a post"）、类型标签（"post"/"帖子"）、例句与命名示例、writer 人设（"social post for professional audiences"）全部去 LinkedIn。
3. **保留位**：`linkedin-longform` 技能包内部名（包体本身渠道中立，仅 body 经 contexts 进 prompt）；发布婉拒示例（用户真问「发到 LinkedIn」时的应答教学）；landing 营销文案（营销面按设计讲渠道）。渠道的合法来源 = 用户点名 / 渠道授权（发布层，POSITIONING 落地时），永不是默认值。

**Consequences**: echo、提问、后续 echo 与 intent name 都不得引入用户未点名的渠道。「参数/默认永不说用户没说的话」与 ADR-058 二源律同族：默认值是执行事实，不是叙事。

## ADR-061: 变体并行律——修饰节点是变体不是工序，caption 扇出恒并行

**Status**: Decided (2026-09-10)

**Decision**:

1. **变体并行律**：修饰节点分两类——**变体**（translate_clip / dub_clip：消费 `after` 目标，fork 新输出，mutate nothing）与 **mutator**（`_CAPTION_MUTATORS = {"remove_filler"}`：就地改写共享 render_spec，后继节点必须看见它的输出）。编译期依赖 = 变体只挂自己的 `after` 目标 ∪ 既有 mutator（若有），**永不挂兄弟变体**——EN/ZH/FR 三译 + dub 全部并行扇出。
2. **mutator 排序保留**：remove_filler 之后的一切 modifier 追加挂它的输出（共享 render_spec 的写后读序），这是原序列化里唯一真实的需求。
3. **mutator 集合 = 显式注册**：`_CAPTION_MUTATORS` 常量登记，新增 mutator 型 modifier 必须入册（入册 = 声明「我改写共享状态」，编译器据此排序）；未入册的 modifier 默认变体语义（并行）。

**Consequences**: 多变体可并行，共享 mutator 保持写后读序；旧草稿的链式边只在 Start/重盖的 ADR-062 对账中撤回。图正确性来自显式变体/mutator 语义，而不是保守串联或一次编译验证输出。

## ADR-062: 图边对账——同一编译拥有其成员边，撤回也走唯一写门

**Status**: Decided；settled freeze 与 rank 边集 = ADR-098。

**Decision**:
1. draft stamp / run fill 对本次编译拥有的成员集合做边对账：本次不再声明、且属于该集合的旧语义边必须撤回；不得只 `have_edge` 去重新增而留下陈旧拓扑。
2. 成员只包括当前编译产品节点、真实输入资产及明确登记的 companion/reference。**task_book、transcript 文档和合成 transcript 边不属于新图成员**；历史 run、其他 journey 与跨 run 血缘不被本次编译顺手删除。
3. 撤回经 `apply_wiring_ops` 的 `disconnect` 等受控手势，定位 from/to/type；它是编译器内部操作，不进入 LLM 工具目录，也不允许模型自由删边。
4. 对账先撤回再连接，使环检查看到撤回后的工作集；同批瞬态对象与已持久化对象分别处理，不能把未入库行当数据库删除。
5. rank-relevant 的 settled 边变更遵守 ADR-098 freeze；legacy transcript 迁移必须先保存 edited_text 到 asset overlay，再删除旧节点/边，不能借对账丢用户编辑。

**Related**: ADR-057/061/086/098/113；`docs/VERIFICATION.md`。


## ADR-063: 卡面诚实——动作就近、全文可读与估价不撒谎

**Status**: Decided；卡面解剖详见 `UI_GUIDELINES.md` 与 `VERIFICATION.md`。

**Decision**:
1. 节点自己的动作住在节点当前解剖或明确详情面，不另造随视口漂浮的第二卡。执行/费用确认仍只在 dock；canvas 不设计划确认座。
2. **全文卡律**：文档卡展示真实全文，不用摘要/浓缩/省略号冒充内容；超过最大卡高时在卡内滚动。测量与 frame 预留只有一套规则的服务端/客户端镜像，不复制第三份。
3. task_book 不是文档节点；计划正文由当前 draft/dock echo 呈现。transcript 也不是文档节点，全文与编辑 overlay 住资产卡。run fill 不得改写用户草稿或编辑文本。
4. 价格必须区分已知、未知与下界：全部 NULL 显示“估价随运行”，部分 NULL 保留下界开口；不得把 NULL 当 0，也不得给免费节点虚构价格。
5. 卡面程序/参数只显示当前真实 spec；frozen template、失败墓志铭和无动作 factsbar 不得冒充产品信息。失败行在恢复时清除，旧错误只作明确历史回退。

**Related**: ADR-057/058/067/070/072/087/113；`docs/BILLING.md`。


## ADR-064: 顺形律 + 校验分层律——schema 顺着模型的自然写法设计，校验严格度随数据关键度分层

**Status**: Decided (2026-09-11)

**Decision**:

1. **顺形律**：schema 设计顺着模型的自然 JSON 写法，不再靠读容忍扛错误形状。模型的第一直觉写法就是正典——`Brief.constraints`（当时类名 BriefLedger，命名批 v3 ② 更名）从 `BriefSlot[list[str]]` 改形为 `list[BriefSlot[str]]`（一个约束一个对象）。边界归一化只接存量与明显来路（旧对象包数组逐项展开 / 裸字符串包装 / off-enum 来源降 inferred——永不把来路不明的值升格 user-stated）；不是给畸形形状发签证。
2. **校验分层律**：校验严格度 ∝ 数据关键度。关键载荷（action / tasks / answer / ask / name——驱动付费运行）= 严格 + 修复轮；brief = 咨询性记录——归一化后仍无法解析时**丢字段不杀回合**（`Brief.model_validate` try/except → structlog warning + `brief=None`，回合照活）。
3. **constraints 合并 = 键控并集**（`_constraint_key` 归一化 + `_SOURCE_RANK` 逐项优先级 + 存储序追加），装配面只渲染条目文本。

**Consequences**: 正典形状直接解析，存量合法来路可读；不可辨认 brief 不杀回合，关键载荷仍严格拒收。merge_brief 的键控并集与来源优先级由当前纯函数守卫覆盖，不冻结测试数量。

## ADR-065: 服务感两拍——修复轮相位帧 + 失败行第一人称认领

**Status**: Decided (2026-09-11)

**Decision**:

1. **修复轮相位帧**：漏斗新增保留 kwarg `on_repair`（与 `repair_feedback` 同款纪律——`_funnel` 弹出、永不进 assemble；纯函数套件 4 用例：干净通过不触发 / 修复轮恰好触发一次 / 二拒信号后仍传播 / sync 回调兼容）。chat 层把它映射到 SSE 相位管道：`THINKING_PHASE_REPAIRING = "repairing"`，两处 `call_stream` 座（book path / propose path）经 `_repair_phase_callback` 接入；前端 `thinkingPhases.repairing` 双语（en "That answer didn't come out right — reworking it…" / zh「刚才的回答没组织好，我重新整理一下…」）。一次性 JSON 路径无相位管道，kwarg 缺省静默。
2. **失败行第一人称认领**：`USER_ERROR_LINES["ai_unreadable"]` 改写为第一人称认领 + 诚实下一步（en "My answer came back unusable — that's on me, not you. Please try again." / zh「我给出的回答没法用——是我的问题，请再试一次」）。说话者 = assistant，失败归自己，不归 "the AI" 第三方。

**Consequences**: 修复窗从冻结读秒变为有名有姓的相位；两连击终态的措辞与 ADR-064 的结构性修复互为表里（形状顺形后两连击本身应绝迹，措辞是它万一再现时的诚实面）。相位帧纪律不变：bare keepalive 不碰标签、相位只在真实切换点发射。

## ADR-066: provider 方言归 client 层——think 块剥除的位置律

**Status**: Decided (2026-09-11)

**Decision**:

1. **方言关在 Model 边界**：`_ThinkStripper` 住进 `providers/llm/minimax.py`（三态 prelude/in_think/payload，tag 跨片安全——尾部 holdback `len(_CLOSE)-1`；有界内存；start-only 规则与 `_clean_json` 对齐），`generate_stream` 每次重试新建实例过滤 `on_delta`。上层（extractor / watchers / plan beat）永远不见方言——stream_extract 的 think 常量和前奏态机全删。
2. **换 provider 的契约**：新 provider client 实现自己的方言归一化（思考块 / 特殊标记），上层契约 = 干净载荷流。

**Consequences**: 纯函数套件 test_think_stripper_pure 9 用例（split_every_way 模糊 / think 内假 JSON / 非 tag 的 `<thinkx` 放行 / 流中段字面 think）。副作用红利：plan beat 不再被 think 块内的 `"tasks"` 误触发，重试护栏收紧（`emitted` 只数干净载荷）。

**Related**: ADR-064（顺形律族——方言归位是顺形律的传输层镜像：形状顺模型的写法，通道顺 provider 的边界）

## ADR-067: 出锚语义律 + 封顶滚动律——源锚说自己的媒介，文档卡有视口纪律

**Status**: Decided (2026-09-11)

**Decision**:

1. **出锚语义律**：出锚 = 源节点**自身产出的媒介**（asset 按 asset_type：video→video / audio→audio / image、slides→image（渲染侧第五 glyph，从不过线）/ transcript、file→text；document、agent→text；generator、processor 按 frame_class：clip→video / text→text）——**一节点一出发锚，全部出边同点出发**；入锚 = 边的承载类型（消费方拿什么）。跨媒介边 = 「从 X 到 Y」的转译叙事，转换住在边上，源节点永不长外来 glyph。ctx 无例外——引用流的 Files glyph 只住消费端。染色：入锚 + 描边共享承载类型（线锚同色律守在消费端），出锚染源媒介——video→text 边从紫锚出发走中性线，这个「不一致」正是转译叙事本身。实现 = 纯客户端推导（FlowView `productionPort`，源锚集合 = 节点自身类型单例），服务器零改动；落库的 `from_port`/`to_port` 列无读者，维持旧值不动。
2. **封顶滚动律**：全文卡律不变（永无摘要/浓缩/省略号——反对的是浓缩，不是滚动），但 document 卡高封顶 `DOCUMENT_MAX_H = 560`（= text 帧类预留），超出正文卡内就地滚动（nowheel+nopan+thin-scroll）；文档卡只有内容与真实动作区；task_book 不成节点，计划确认仍只在 dock，不在滚动区底复刻 Start。一条测量律两镜像封顶（layout.ts `DOCUMENT_MAX_H` ↔ graph_store `_DOCUMENT_MAX_H`）。画布是文档面，但文档面也有视口纪律。

**Consequences**: 封顶后行估算只决定「是否触顶」，估错无害（卡短一点、多滚一点，永不溢出）——列重叠与文本穿卡结构性消失；legacy 巨帧保留（append-only：旧图多留白，不重叠）。视频节点回到单相机锚；image 锚走中性色（无 `flow-port-image` 规则 = 基座中性，零 CSS 新增）。

**Related**: ADR-057 §5（端口法则）、ADR-063（全文卡律）、ADR-058（二源律——锚语义是节点身份叙事的一部分）

## ADR-068: 画布走查三修——引用 glyph 可读性 + draft 卡无 factsbar + clip 帧 aspect 精确预留

**Status**: Decided (2026-09-11)

**Decision**:

1. **ctx 引用流无自有 glyph**：引用流入锚并入共享 T——Files glyph 在画布上读作「image」、@ glyph 是外来锚，均否；node 左舷只有 T / image / video 三类 icon，@ 永不上画布（ADR-072 ⑤）。中性色不变。
2. **draft 卡无 factsbar**：未运行节点不再向 factsbar 塞参数 chip（language / aspect 全删）——参数复述 caption 已命名的事实是双重说话，无按钮的条是死 chrome；长度守卫自然不渲染。带宽预留留在高度数学里（几何永不动），产物落地时条随真实事实出生。
3. **clip 帧 aspect 精确预留**：fill 的 `_frame_class_of` 返回 (class, aspect)——链上显式 aspect（select_clips spec）胜出，否则 "original"（整片/transform 链永不重取景）；盖章进 `spec.frame_aspect`（纯帧键——不入 `_params_of` factsbar 白名单，运行时工具不读；`node.spec.aspect` 仍是链自己的生意）。`_frame_of` 按 `_CLIP_FRAME_H`（9:16=660 / 1:1=438 / 16:9、original=316）预留，与 layout.ts `clipNodeHeight` 一条律两镜像互引；未盖章 clip 节点回退类上限 660（wiring 出生的节点安全兜底）。

**Consequences**: fork 列的节点间距 = draft 278 + 预留 316 的精确数学，产物落地后卡高恰好填满预留；legacy 图保留旧帧（append-only——多留白，不重叠）。

**Related**: ADR-057 §5（端口法则）、ADR-067（出锚语义律）、ADR-063 判词②（镜像纪律——_CLIP_FRAME_H 入镜）、ADR-072 ⑤（ctx 入锚并入共享 T）

## ADR-069: 段落级指认 + 失败人话行——卡面划选钉进 dock，失败卡读烤好的人话行

**Status**: Decided (2026-09-11)

**Decision**:

1. **选区引用（段落级指认）**：文本产物卡（post/article）读体恢复可选——读体从 `<button>` 改 `div[role=button]`（button 吞文本选区；键盘 Enter/Space 进编辑的平价路径保留）；划出段落在**区域右下角**浮「引用这段」pill（region 级 absolute 锚定，**永不进 scrollport**——进滚动区会随文滚动并在 overflow 边被裁）。点击 → dock 插入**带 quote 的 @output chip**：`ChatMention` 双端加 `quote` 字段（null = 整体指认，旧行读容忍同打字机律牙①）；chip 序列化 = ``@label "quote"``（散文与历史行都留住指认对象）；编辑器 chip 内联渲染截断 muted 引文（说清指哪段，不只指哪个产物）；dataset round-trip 保回滚重插不丢引文。服务端：mention block 行附 `the user pinned this exact passage`（500 字截断——卡面选区是用户真值，上下文预算不是）；prompt 规则钉死语义：**the passage IS the revision's scope**——新程序修订那一段，永不盲目重写全文。引文出生截断 200 字（一两句的生意——更长是整体 mention 的活）。`insertMention` 召回隐藏 dock（chip = 新信息，召回律）；pill 的 mousedown preventDefault（不得在 click 读选区前塌掉它）。范围：文本产物（post/article）——transcript 文档卡不在此列（其选区 = 未来剪辑 primitive）；手动 in-place 编辑保留为逃生舱，永不是故事主线。
2. **失败人话行**：node 失败态卡读 `spec.error`——`sync_graph_node_for_step` 聚合出 failed 时从 failed family step 把烤好的人话行誊入 `node.spec.error`（bake-at-write、UI locale 于失败时刻，与 step summary 同纪律）；**家族恢复即清**（重跑不留陈旧墓志铭）。泛化「运行失败」降级为前 error 行旧数据的回退。

**Consequences**: 修订指认粒度到段落，agent 永不用猜「这段」是哪段；失败卡的叙事与 dock RunTaskList 的失败行同源同文（同一条 `user_error_line`）。无大屏编辑器路线——卡面编辑能力 = 直改程序（K4）+ 选区钉给 agent 两通道，手工改字只是逃生舱。

**Related**: ADR-058（mention 注册表指认族——quote 是其首个字段扩展）、ADR-065（服务感失败行）、ADR-057 K4（卡面直改——与选区引用并列为卡面两修订通道）、MENTIONS §3（闸门——quote 是字段不是新类型）

## ADR-070: Start 与固定选择回座 dock——同一授权机器，不按任务数换 UI

**Status**: Decided；当前授权 = ADR-117/139，Film 首稿 = ADR-144。

**Decision**:
1. 执行确认与费用确认的唯一控件座位是 dock；canvas 不放计划 Start/Confirm。选项问也复用同一 OptionDock 机器，不新增第三确认面。
2. Start 使用直接、具体的动作文案；Start pill 化为普通用户消息走 sendChat，与口头 yes / typed answer 同进下一轮 LLM 的 `start_run` 与服务端 `evaluate_start_gate`，按钮不直接创建 run，客户端 disabled 不是安全边界。
3. 是否显示 Start 由当前生产意图、ask/auto、费用守卫、材料、版本与 Film 首稿审阅决定。**不再按任务数量决定有没有 pill，也不存在“单任务只能口头”的规则。**
4. dock placeholder 不按相位编造新文案；只说明当前真实可用的修改、上传和 @mention 能力，不提不存在的 slash 命令。
5. echo 对评审面的指称必须与实际可见环境一致；dock、草稿图和消息流可以共同呈现，但不得声称用户看见了尚未 reveal 的面。

**Related**: ADR-053/054/087/092/111/117/118/139/144。


## ADR-071: prompt 工程结构律 + 零硬编码默认链——j2 单一化、考古不出 token、规则减负

**Status**: Decided (2026-09-11)

**Decision**:

1. **结构律**：chat 两个 system prompt 住 `app/prompts/chat/*_system.j2`（与全站 agent prompt 同一 jinja_env 基建；`*_system` 后缀区分 `app/prompts/` 根下同名的 user-turn 模板），真·双消费共享段 = `_*.j2` partial 单一定义两处 `{% include %}`——**五件**：speech_language / translate_target / naming / asking_strategy（提问三律，router 嵌套列表形为正典）/ writers_no_material（router 全块为正典 + `{% if chat_loop %}` 相位分支承载 chat loop 的 existing-project 尾巴）；动态目录行（tool / op / wiring lines）作 render 变量注入；`prompts.py` 降级为薄装配包装（函数签名不变，零调用点改动）。机械迁移必须 byte-identical——`scratch/prompt_split_diff.py` 渲染对比脚本卡死（before = 拆分前快照）；后续每次编辑性改动同律——router 侧渲染 byte-diff 卡死，chat_intent 侧 unified diff 审 delta。mention 规则与 key order 不抽：前者从来不是双胞胎（旧 router prompt 无 mention 块，查快照实证），后者两相位字段名不同（answer vs summary/text），是合理分叉。
2. **零硬编码默认链**：链的形状永不写死在 prompt——"Default chain when the request is vague" 规则**整条删除**（先改为「从上下文判断」的灵活版，探针实测后对 vague 引导做减法到底：模型有工具目录的 when-to-use 描述与上下文，vague 请求的判断不需要专条）；`tasks_explicit` 语义不变（false = 默认提案的来源簿记）。
3. **考古不出 token 律**：日期 / ADR 编号 / 历史注永不进模型可见文本——出处住模板头 `{# #}` 注释与本文档；模型只见规则的当前态。**例外判例**：看似考古的行可能有**语义承重**——「lift applies ONLY to the ask-back refusal」限定弹是承重限定不是考古：剥考古括注、留限定本体（模板保留此弹 + "The two rules cooperate: lift the gating, keep the grounding."）。
4. **规则减负**（探针 A/B 双闸后执行）：死字段 `confidence` 不进 prompt（零消费方；schema 字段留作读容忍）；风格脚手架三禁令 + never-reuse 并入 FREE PHRASING 一条（保留 banned literal 作例）；目标语言 worked examples 两条（同源护栏本体保留）；参数骑行四规则并一；NO-MATERIAL CASE 两行；answer/draft 例表每类 ≤3，start 例表 6 条全量保留（中文例防语言锚定）；EXCEPTION 1/2 并入 Disclosure 段；无 vague 默认链（判词②）。**承重保留**：碎键不起跑 / never invent platform（ADR-060）/ subtitles vs dubbing / whole-source vs highlights（ADR-043）/ presented chain 保全 / 提问三律 / 出书门槛 / key order（打字机律牙）/ pending-question 段 / **no-material 块的块结构（标题 + 子弹组）与 lift 限定弹**（判词③例外）/ echo 块近逐字旧构（ADR-070 换面中性 Start 句、Disclosure 命名）。
5. **双 wire 共享一套语义契约**：native `tool_calls` 为主，工具参数 schema 与描述随原生调用面提供给模型；action-JSON 回退由 prompt 散文描述信封与参数形状。两条路径都在服务端经 Pydantic、注册表和工具白名单校验，prompt/schema/枚举必须对账；不得宣称「schema 从不发送给模型」或把 `response_format=json_object` 当成唯一当前路径。provider 是否遵守 `json_schema`、native tools 或其他方言由实际能力声明与探针证明，方言消化归 client。散文字段的 null / 缺省读容忍与 settled-prose 打字机释放在两条路径都成立。chat_intent shape C 骨架带 `default_path`——两相位共用的 skip 路径牙（dock × 与插话提醒消费），只有 `slot` 是 chat loop 留 null。
6. **prompt 减肥必须过探针闸，且探针必须轮转（双重流程律）**：① **任何 prompt delta 靠探针实测，不靠文本推理**——探针闸 = `scripts/prompt_gate.py`（对 native-tool providers 的有界工具 loop 线，绝对阈值，`--provider` 参数化）：**上下文必须复刻剧本真人设状态**（`persona_exists: False`——带人设的探针会给出假绿）。② **探针调用必须 round-robin 交错，禁按变体顺序连跑**——provider 状态以分钟尺度漂移，顺序批把「变体」与「时间」混杂。③ **冗余与限定不是脂肪，小型 open 模型的指令遵循靠它们承重**——承重件 = no-material 块结构 + lift 限定弹 + start 例表 + echo 块结构，减肥不得动它们。
7. **混合形状代码侧顺形**：`draft + tasks=[] + ask 对象在场` 归一为 ask 判决；`draft + tasks=[] + 无 ask + answer 在场` 归一为 answer 判决，播出的散文即最终内容。空链永不可 dock，valid ask 不得因空链校验被降级成拒答。任何 ask 判决在仍有待决计划行（`kind=task_book`）或普通问题时采用插话形态：ask 散文落普通回答，待决行保持敞开；不得 supersede 计划行而让 `project.pending_brief` 与确认生命周期失去对应。**`_constraint_key` 数字归 `#`**：同键重申恒胜——"under 200 words" 与 "under 100 words" 数字归一后同键、逐项 precedence 原位替换，不攒自相矛盾的双条目。
8. **被跳过槽位的推断值不算根**：计划呈现门槛 `has_root`——topic 槽已在 asked 簿（用户 × 跳过 = 已选默认路径）时，只有 user-stated 的 topic 才算根；模型推断的 topic 不再把书重新有根化、绕过 draft_from_persona 的代码宣言（reason + code echo 双缺席 = 失败形态）。素材在场仍经 material_state 成根（infer-from-material 路径不受影响）；用户后补原话永远算根。

**Consequences**: prompt 面改动的验收三阶段——byte-identical（机械拆分）→ 渲染级 unified diff（减负 delta 可审）→ 轮转探针实测 + 剧本矩阵。部署前仪式链：纯函数 pytest → check_gates → prompt gate（`scripts/prompt_gate.py`，10 探针绝对阈值；判负先复跑一次再二分归因，永不调阈值迁就回归）→ 当前 `SCENARIOS` 剧本矩阵。工具名枚举的漂移报警 = `ToolEntry.needs_media_file` 旗标（零行为元数据，人工标定）+ `tests/test_prompt_registry_consistency_pure.py`（media-needing / writers 两枚举与注册表对账 + 全模板枚举名注册校验）——MEDIA∪TRANSCRIPT 派生轴会误纳 align_stills（requires=(TRANSCRIPT,) 却为无录音场景而生），故旗标人工标定、测试对账而非自动派生。slot 握手与 start 判决的残留 flake = 模型侧既有方差，非 prompt 杠杆可解；模型把 brief 写成无槽名来源化条目数组的形状天然有损（无槽名无法映射 topic/audience），代码侧顺形无路，挂账为模型侧课题。

**Related**: ADR-052（提问三律 / 出书门槛——内容不变）、ADR-054（密度律）、ADR-058 / ADR-060（命名与防编造——保留）、ADR-064（顺形律——brief 形状指导保留）、ADR-070


------

## ADR-072: 产品节点解剖——媒介与程序分轴，执行概念不上图

**Status**: Decided；词表由 ADR-076 补充，transcript 由 ADR-113 更新。

**Decision**:
1. 节点身份分轴：媒介类型决定媒体/文本/表格等卡面基础，prototype/产品角色决定程序与编辑面，业务名由 label/tool 与二源律表达；不得用一个不断膨胀的 kind 同时承担三件事。
2. 文档、表格与媒体卡都必须对应真实、用户可拥有/阅读/修改的产品对象。transcript 是 asset 内容层，不再是 text×manual 节点；translation/dub script、research、分镜等只有在实际注册为产品对象时才出现。
3. 翻译/配音等链可以把可编辑文本与装配分成不同产品站，以支持“改文字只重渲染、不重买翻译”。是否拆站必须由真实编译图与报价证明，不能为排线或展示虚构节点。
4. clip 分镜表若作为可编辑中间产品启用，必须登记其产品资格、单元格编辑语义和失效传播；Film 的 `design_storyboard` 呈现是消息中的创作方案，不自动等于 clip 表格节点或 task_book。
5. **task_book 节点退役**：用户的话在 chat，链在图，费用在报价，确认在 dock；不维护“计划的照片”作为执行内节点，也不创造 ctx 假边。
6. modifier 可以是装配卡的结构化杠杆而非独立节点；只展示本 run 实际启用且定义产物的参数，样式细节与未启用能力不堆上卡。
7. `materialize_source`、preprocess、render、verify 等是节点内部执行工序，不成产品节点。素材直接连接真实消费者，工作段仍显示实际步骤。
8. PROMPT/散文程序只携带用户真实原话或明确当前程序；无原话时不拼接参数回声。卡面直改与 chat 修订按 ADR-058 分道。
9. 样式覆写使用已注册 spec/persona 边界；自由 CSS、任意画布、手动加节点/接线和自由多轨 NLE 不因此开放。

**Related**: ADR-057/063/067/076/086/097/113/129；`docs/CHAT_ARCHITECTURE.md` / `docs/RENDERING.md`。


## ADR-073: run 期消息流时序律 + 清单活态默认展开 + 起始 banner 退役

**Status**: Decided (2026-09-13)

**Decision**:

1. **起始句独立锚**：run 的起始言语（ADR-093：start_run 回合的 LLM 言语，落库普通 message 行）序在 taskList 前；活态 mid-run QA / 插话按真实时间落在起始句与钉底动态行之间。
2. **run 工作段锚在 run 结束刻**：terminal 后 taskList 锚 = lastStepT+1，delivery 回复随其后——mid-run 生活（QA / 对话）恒在该工作段之上，ADR-058「收据永不高于生产回声」由构造成立（回声必 mid-run）。`workflow_run_id` 章不再是排序锚，只剩 detached run 内联归档（RunCard）与 delivery 首显收口的归属关联。
3. **无起始 banner**：确认拍的记录 = echo 散文 + 用户原话 + 开工句（ADR-093 §2，start_run 回合的 LLM 言语）+ run 收据行，机器块零增量——无「✓ 生成计划 · 题名」块、无 pre-run QA stand-in 抑制逻辑（`hasPreRunQaArchive`）、无 `generationOverlay.title` i18n 键。
4. **run 工作段一行三态**：RunTaskList 与 chat 共用 `WorkSegmentRow`，同一 `runId` key 承载 RUNNING → REVIEWING → SETTLED。活态默认展开真实步骤导轨树，用户可手动切换，running → reviewing 保留其选择；terminal 只把原行切入「正在整理制作结果…」，匹配当前 run 的 delivery 首个非空白字符实际经打字机释放时才原位收成 Worked，settled 当拍默认折起、之后可再展开。无回复有界出口与历史回放使用 run 自身可观察跨度，chat inline chip 复用同一 settled 边沿，在 delivery 首字实际释放或 Worked 收段后才挂载；产物就绪与画布交接仍独立读真实 output。

**Consequences**: QA 归档律不变（选项问回答坍缩成已答问题双层消息入流、task_book start 永不入 QA 块）——变的只是排序锚；方向问答的记录双座照旧（流内 QA 块 + interrupt 步骤行「方向：…」量化重写）。

**Related**: ADR-058（排序锚与二源律）、ADR-053（问答机器——归档律不变）、ADR-051（dock 唯一壳）

## ADR-074: Run 判决、交付真实性与画布几何

**Status**: Decided；交付分支现行法另见 ADR-135/141，渲染身份见 ADR-079/096。

**Decision**:
1. **同语言变换双重拒绝**：chat 草案校验与 run 出生地都按实际源语言拒绝无意义目标；语言未知时不猜，运行时护栏仍兜底。修法必须给用户可行方向。
2. **run 判决**：任何非 runtime-fanout 工作步骤 failed ⇒ run FAILED；render fanout 的失败是产物级事实，不单独把整 run 判 FAILED。部分失败不新增第三 WorkflowStatus，而由 `delivery=partial` 表达实际落地与缺失。
3. **交付只认真文件**：payload/output 行不等于已交付。`run_completed` 只覆盖 delivered/partial；全败由 `run_failed` 说原因和可行下一步。失败/未就绪行不得进入 landed 列表或锚卡。
4. **活跃与收官**：渲染镜像计入 run 活跃集合；渲染落定、删除输出与崩溃扫尾都要幂等收官。render metering capture 先于 release；pending 镜像不能因输出删除而永久悬挂。
5. **画布几何声明化**：节点尺寸与端口几何由 frame/layout 数学作为一等字段提供给 xyflow，不能依赖一次 DOM 测量或对象身份碰巧稳定；背景 refetch 不得制造隐形节点/边。
6. **终态不例行 remount、不例行 refit**：checkpoint/run 收官使用稳定语义身份与原位过渡；render key 与语义 id 分家。任何恢复性 remount 都不能成为常规收尾，也不能在用户未发起时移动相机。
7. 项目 REVIEW/DRAFT 的呈现只依据真实可交付世界； cancelled 从可见投影退役，真实 failed 保留安静告警。

**Related**: ADR-057/073/079/093/096/108/110/135/141；CHAT_ARCH §8 与相机律。

## ADR-075: 画布媒体跟源比例 + 分档加宽——真实像素是形状真值

**Status**: Decided (2026-09-13)

**Decision**:

1. **真实像素入 meta**：`meta.width/height` 双座写入——① 客户端 staging 探测（`stagedFiles.probeMediaDims`：img naturalWidth / video loadedmetadata，与 chip 预览同一探头族）随创建载荷送达（`AssetCreateRequest.width/height` → `create_asset_from_key` 出生即写 meta，home composer 与 chat dock 两个上传座同律），零赛跑；② 资产处理链头 `_content_hash_processor` PyAV 开容器兜底（API 路径上传 / 预探测旧行回填），探测在临时文件 unlink 之前、任何失败静默缺席。展示面事实，不入计费不入 prompt。
2. **展示档解析一座**：`graph_store.display_aspect_class`（几何均值边界 0.75 / 1.334 取最近档——离比例保 contain 细边，永不裁剪内容）+ `resolve_source_aspect`（多源混形 → 返回 None 不猜，保 "original" 默认条）。三个消费座：① **stamp/fill 时刻**——graph_fill `_stamp_graph_core` 查源资产 meta 尺寸把 "original" 解析成真档（帧出生时就是对的，定居取景律不动）；② **片段出生时刻**——materialize_source 把展示档盖进 `ClipPayload.aspect`（fork 派生行随 payload 复制自然继承；`OutputResponse._derive_aspect` 的写点模式与图片产物同款，`render_spec.aspect` 渲染契约不动，读面永不补丁）；③ **素材节点出生**——`stamp_asset_node` 按资产自身 dims 盖 `spec.frame_aspect`。
3. **分档加宽**：clip 车道 9:16 不动（280×498 媒体区）/ 1:1 → 340×340 / 16:9 → 400×225；素材节点同律（280/340/400 三档）。帧表改按档 (w,h)：`_CLIP_FRAME` / `_ASSET_FRAME`（max 档入 `_FRAME_CLASS`），`_PITCH` 随最大档 400+96。client 镜像（layout.ts `PRODUCT_THUMB_PX` / `displayAspectClass` / graphNodeSize 素材支 `assetDimsHeight`）——判词② 一条测量律两镜像互引不变，永无第三份。
4. **预留律牙（赛跑/旧行兜底）**：帧可能早于尺寸到达（API 路径上传 + 预探测旧项目）——卡面媒体区与 graphNodeSize 双双 cap 到出生帧预算（`frame.h` 减 label/program/toolbar 三段）， contain 细边回归但帧永不被撑破、列永不重叠；dims 全缺的 "original" 保 280×316 默认条（今日外观，零回归）。

**Consequences**: 1:1 链 = 340×340 正形卡，真 16:9 源 = 400×225；无尺寸旧行外观不变。渲染契约 / prompt 面零改动（prompt gate 无新增义务）。

**Related**: ADR-057（定居取景 / 零投影——帧律与测量镜像的座位）、ADR-072 / ADR-076（节点词表——素材节点同律的依据）、ADR-074

------

## ADR-076: 节点词表——媒介、prototype 与业务身份分轴

**Status**: Decided；具体 wire 字段以当前 schema 为准，探索产物边界 = ADR-088。

**Decision**:
1. **媒介轴**只表达 text/table/image/video/audio 等内容形态，驱动卡面解剖、画幅与端口；不把 select_clips、translate、task_book 等业务/执行词塞进媒介枚举。
2. **prototype 轴**表达程序与编辑方式：普通产品节点使用 `generator | editor | manual`。探索产物不住 Product Graph，独立存于 `exploration_rows`，没有第四种普通 prototype；不得为绕过门禁把探索行写回执行图。
3. `generator` 是散文程序，`editor` 是受控参数程序，`manual` 直接编辑内容本体；它们不改变报价、版本、写门与执行身份。具体可编辑 op 由 registry 决定，不由卡名猜。
4. **业务身份 = label/tool/name 等当前字段**：label/name 对用户说作品，tool 对系统说执行体；对用户可见名称仍受 ADR-058 二源律约束。媒介五值不承担业务命名。
5. transcript 不是 `text×manual` 图节点；它是 asset 内容。task_book、render、verify 等执行概念也没有 prototype 座位。翻译/配音 companion 只有真实存在并可编辑时才登记。
6. 端口与卡面由声明式数据驱动，不维护平行 card 映射表。前端兼容 DTO 可以使用 `kind` 等传输名，但不得因此再创造一套语义不同的分类。

**Related**: ADR-057/072/086/088/098/113；`apps/api/app/pipeline/product_graph.py` / `apps/web/src/components/flow/types.ts`。


## ADR-077: 会话层工具 loop 化——常备否决收窄终裁：生产封闭 / 服务收编 / 执行永拒

**Status**: Decided (2026-09-14)；详细契约 `CHAT_ARCHITECTURE.md`；旅程母文档 = `docs/JOURNEYS.md`

**Decision**:

1. **常备否决收窄终裁**（边界三层各自钉死）：
   - **生产层 = 编译期封闭 DAG，永不变**——看什么/做什么编译期可枚举；报价=fold、执行=topo、拓扑代码定（ADR-028）不动摇；
   - **服务感知 = 有界只读 loop，收编**——chat 边缘 agent 可调一族**只读工具**（读 spec / 曲库 / 样式目录 / 理解摘要 / run 状态…）；迭代封顶（`max_iterations` 声明）+ 报价 = fold（上限 × 单次）+ 终产仍是「一份判决 + 工具序列」；
   - **执行 loop 永拒**——写世界永远走三扇唯一门（edit ops / wiring ops / `create_run`），loop 内零副作用。（2026-10-16 修订注：读本类世界事实的快照写穿走独立短事务、回合事务保持只读——ADR-124；「读工具零写函数」的适用面收窄为回合事务内。）
   「是否做 ReAct / 是否做 loop」问题注销：每层各有答案。
2. **会话层全面工具化**：现有判决 union 机械翻译为工具集——`type` 字段 = 工具名、各态字段 = 工具参数（ask → `ask_user` / draft → `present_plan` / start → `start_run` / task_list → `propose_tasks` / edit_ops → `edit_output`（受控四件，ADR-090）/ WiringProposal → `edit_graph`）。**护栏语义搬进工具执行内**：出书门槛 = `present_plan` 的执行内校验（无根 → 工具拒绝 + 结构化反馈，修复回声的同族座位）；出生地 422 不变（`start_run` 内部仍走 `create_run` 零旁路）；dock 生命周期 / 单待决 / autoResume 结算 = UI 状态机 + 代码，原样保留。读工具一族住 `app/chat/perception/`（注册表纪律同 TOOL_REGISTRY：name + params schema + execute + 碎碎念文案键，静态注册随代码部署；与 `app/tools/` 的分工 = **世界的读法 vs 世界的改法**）。loop 驱动 = harness 新形态（迭代封顶 + **终态工具**（ask_user / present_plan / start_run / 最终回复）一调即停）。
3. **触发回合（trigger turn）**：chat 回合的「用户消息」可以是白名单系统事件（当前 = run_completed / run_failed / craft_decompiled），agent 借真实事实或只读工具后说话。`run_completed` 由 delivery reviewer 只陈述 delivered/partial/failed、真实产物与费用，成功不默认追加建议；`run_failed` 给确定性原因与至多两个可行选项。固定建议若存在，必须经 OptionDock/普通 answer 结算，不直达导出、发布或付费执行，也不形成第二意图面。
4. **多 provider 线格式三层**（通用地板 + 高级处理 + 自动降级）：Tier 0 地板 = action-JSON-in-prompt loop；Tier 1 = 原生 tool_calls；Tier 2 = provider 特有（strict schema / parallel calls / reasoning 控制，逐 provider 声明）。**法则：层只换线格式，永不动判决契约**——各层产出同一校验后结果，降级天然安全，修复/错误反馈语义同构。client 声明能力旗标（`supports_native_tools` / `supports_json_schema` / reasoning 方言），harness 选双方共持最高层；PRICING 按 provider+model 分家；prompt gate（ADR-071）按 provider 参数化复跑。错误类型使用 `LLMError` / `LLMSchemaError` 等中性边界名，`user_key` 稳定；方言消化归各自 client（ADR-066 不变）。
5. **预效果一致性纪律**：agent 的「思路与方向」描述恒从提案对象派生（summary/ops 同一对象两投影——summary 到嘴、ops 到手），校验先于庆祝。`delta` / `tool_ready` 预览在 Speech Commit Protocol 中先缓冲，拒绝即丢弃、客户端从未看见；接受后才释放，不使用“先显示再回滚”。**不做额外渲染预览闸**；Film 首稿审阅是独立创作物合同。
6. **NAMING 原则**：会话层用行业词直取——ask_user / tool call / plan（无方言词；brief 保留原词——NAMING N-52；全表见 NAMING.md）。

**Consequences**: schema 变为工具参数，护栏在工具执行内，执行层仍受既有唯一写门约束，提问机器的 dock/单待决/结算语义保留。打字机律两条结构牙（CLAUDE.md）在工具线格式下不变：散文字段 null-read 容忍，零 delta 或信封到达的正文仍经 `paceSettledProse` 排干；工具调用翻译为 Activity/WorkSegment 的真实工作证据，不等同于宏观 Phase，也不逐调用念操作日志。M3 多工具多轮择工具准确率与截断吸收由 prompt gate 和当前用户旅程矩阵验收。画布卡面直改（ADR-058/063）与手动布线永禁（ADR-035）不受影响。

**Related**: ADR-039（四层工程地图——本条是其 Loop 层形态，脊柱不变）/ ADR-052（厚 agent——双引擎分离不变）/ ADR-064（顺形律——架构层兑现）/ ADR-066（方言归 client）/ ADR-071（prompt gate 按 provider 参数化）/ ADR-028（拓扑铁律不破）/ ADR-043（计划链语法）/ ADR-053（提问机器形态律——机制留存，形态工具化）/ ADR-057（图即产品对象——edit_graph 工具的唯一写口不变）/ ADR-078（decompiler——终极旅程内核）/ ADR-090（edit_output 受控四件）

## ADR-078: decompiler 反向编译器——视频 = 可编程时序结构，remix = 换内容留风格

**Status**: Decided (2026-09-14)；旅程全文 = `docs/JOURNEYS.md` §2

**Decision**:

1. **decompiler = video → clip-spec 骨架**：案例视频进、一个 clip-spec 形状的骨架出。字段按确定性分层——镜头切分 / 节奏 / 画幅 = 确定性检测（scene cut 一族，零 LLM）；字幕 preset / 颜色 = 视觉最近邻 best-fit 枚举（只在契约枚举内取值）；配乐 mood / hook 装置 = LLM 判断；**内容槽位留空待填**。产物落库（资产级、内容寻址、可复用——understand 的复用纪律原样继承）。
2. **契约即能力边界**：反向编译只产出 clip-spec 里**有家**的字段；案例里超契约的效果（动图形 / 多轨合成 / L3 清单）在分解时没有座位——「这个我做不到」清单 = 结构对比的副产品，带理由纠偏的素材自动成立（顾问姿态②的兑现机制）。
3. **remix = 内容槽替换**：我的素材经 understand / plan / select_clips 填进骨架内容槽，风格字段（字幕 / 配乐 / 节奏 / 画幅）原样保留；产物天然可渲染——分解输出的就是渲染器消费的同一 schema，可执行性由构造保证。
4. **资产角色（source / reference）**：双素材场景的角色消歧走提问机器（一词可答，选项 = 文件名）或 mention 指认；reference 资产常驻项目、可回读（后续修订的比较基准）；角色可反转（reference → source，链照跑）。
5. **exemplar 参数源**：当前计划参数的第四来源（user-stated / inferred / default 之外 + **exemplar-derived**）。纪律：**参数由代码从骨架映射，LLM 永不写 spec**——拓扑铁律（ADR-028）不破，骨架是数据不是指令。
6. **双抽取分工**：understand 答「它说了什么」（内容），decompile 答「它怎么做的」（工艺）——两种抽取皆资产级、内容寻址、跨项目可复用；plan 的装配签名加 craft 骨架输入（纯度签名化扩展先例 = §5.3 纪律内）。

**Consequences**: 详细契约 `CHAT_ARCHITECTURE.md`。decompiler 住 pipeline 内部 crew（编译期注入，永不进用户提议空间——与 materialize_source 同族）；CraftSkeleton（工作名）= 新内部产物类型（visible_outputs 过滤族同例）。能力缺口清单（案例里做不到的字段）进 PROGRESS 需求池按价值排期。验收 = 案例仿制旅程 e2e（JOURNEYS §2 的分支树逐条过）+ 骨架字段的确定性分层断言（确定性字段零 LLM 介入）。

**Related**: ADR-077（会话层工具 loop 化——终极旅程的服务面）/ ADR-016（clip-spec 是本 decompiler 的目标契约）/ ADR-044（轨道模型——骨架的字段家）/ ADR-028（拓扑铁律——exemplar 参数源不破它）/ ADR-043（计划链语法——第四参数源的语法座位）

## ADR-079: 执行围栏——终态写必须携带执行身份（claim token）+ fenced 零副作用纪律

**Status**: Decided；当前不变量与运行边界 = `docs/ARCHITECTURE_NORTH_STAR.md` §8，守卫映射 = `docs/VERIFICATION.md`。

**Decision**:

1. **两列 fencing token**（migration `f3a8c1d52e97`，可升可降）：`workflow_steps.claim_token UUID NULL` + `outputs.render_claim_token UUID NULL`。token 回答「**现在**谁有权写」——短暂、随 claim 生灭、失势即 NULL；它**不是**执行模型（ExecutionAttempt 回答「当时发生了什么」，形态 OPEN，禁止互冒充，North Star §8.4 分层维持）。
2. **claim 铸 token**：`claim_ready_node` / `claim_pending_render` 的原子 UPDATE 内 `SET (render_)claim_token = gen_random_uuid()`——认领即铸，铸即唯一。
3. **失 Paths 全置 NULL**：两个 reap（startup 全量 + per-tick 按龄）、execute_step 的 retry 重排 / QualityBounce 重排（verify 节点 + executor + done modifiers）/ runtime_fanout 重排 / Suspend park、`resume_waiting_interrupt`、`_cascade_skip`（含 running 子节点——级联语义落成确定性丢弃）、全部 **10 处既有 render re-pend**（morph / node_runners render / verify title-card / music / captions / dub / reframe / filler / operations undo-redo / 手动 render 端点）。少一处 = 竞态洞原样保留（re-pend 与新 claim 之间 zombie 的旧 token 仍能命中）。
4. **终态写谓词换身份 + rowcount**：execute_step 四尾（成功 / Suspend / QualityBounce / 失败含 retry 分支）全部改条件 UPDATE `WHERE id=:id AND claim_token=:mine`；render 三处终态写（no-spec fail / success / exception fail）谓词从 `render_status==RENDERING` 换 `render_claim_token=:mine`。
5. **fenced 零副作用纪律（核心）**：rowcount=0 → rollback session（executor staged writes 一并丢弃）→ 只记 fenced 日志 → **不 capture / 不 graph sync / 不 cascade / 不 mirror / 不 fire trigger / 不写 run 状态**（I-EXEC-01 stale 执行不写终态；I-EXEC-02 stale 执行零副作用）。刻意的唯二例外：① `finally` 的 `maybe_finalize_run` 照调（行锁 + 终态 early-return，幂等；被级联置 NULL 的节点靠它收官）；② Suspend 的问题消息在其独立 session 已先落库（fenced 后成孤儿问题——known residue，归后续小批清理）。
6. **Suspend 的 run 写加 expected-from-state**：`WHERE id=:rid AND status='RUNNING'`——仅 RUNNING→WAITING_HUMAN 可成；node 写与 run 写双保险后，COMPLETED→WAITING_HUMAN 复活链结构性死亡。
7. **入口防御**：execute_step 入口 `running 且 token NULL` = 外来行（迁移前在途 / 无 claim 镜像翻转）→ 防御性 return（pending 直执路径改为 guarded mint——竞态 claim 赢则让步）；render_output 入口 token NULL → 提前 return（省一次渲染钱）。
8. **部署注记**：迁移后在途行 token=NULL 由入口防御接住；部署即重启 worker（在途 asyncio 任务随进程死亡，startup reap 把行送回 pending 由新 claim 重铸）。

**边界**：本 ADR 只规定执行身份与 fenced 零副作用，不定义 ExecutionAttempt / attempt 语义迁移、poison-pill 上限、hold GC、select_clips 语义收窄、worker registry、pause-cancel、chat 墙钟、统一 Policy 层或 AgentBudget；这些能力各有当前合同，不能以本 ADR 为根据扩 scope。fencing 不限制健康并发（双活 worker 各 claim 不同节点 = 合法；startup-reap 竞态造成的重复执行被 fencing 正确丢弃——浪费的是资源，不是正确性）。

**Consequences**: 双扣路径封死（fenced 永不 capture）= 收费的诚实前提；render morph 窗口腐蚀封死（zombie 先完成 0 命中，产物永不回退旧 spec）；run 复活链封死。Known residue（登记挂账）：fenced 执行途中已直传对象存储的媒体对象成孤儿（DB 世界干净、存储世界留垃圾，归后续存储 GC 小批，与 render superseded 删 key 先例对齐）；fenced zombie Suspend 的孤儿问题消息（永不过期，窗口极小，后续小批清理）。锁序影响：fencing 写把 step 行锁提前到尾段写时刻（原来在 commit flush），但锁窗口内只剩 capture/sync 的短 DB 操作（无 LLM 等待），D9 族形态不复发。验收 = 纯函数套件（token 捕获决策 + rowcount=0 零副作用，`tests/test_execution_fencing_pure.py`）+ 手工竞态演练（A claim→停滞→reap→B claim→B 完成→A 醒：A 终态写 0 命中、无第二条 capture、run 行保持 B 判决；render 同型；zombie Suspend 不复活 run）+ 单 worker happy path / retry / QualityBounce 回归。

**Related**: ADR-017（reap 语义 fencing-aware）/ ADR-030（render 认领谓词加身份维度——规则 2 的认领先例扩一列）/ ADR-050（guarded-write 纪律 = 身份守卫——会话纪律不变）/ ADR-055（billing——`_mutate` 双层 dedupe 永不破坏，fenced 永不进 capture_step 是 execution kernel owns billing boundary 的具体含义）/ North Star §8（Execution Kernel）

## ADR-080: 单一叙事者律——会话只有一个叙事者，界面语言有唯一 owner

**Status**: Decided (2026-09-17)

**Decision**:

1. **单一叙事者律**：同一 conversation 内有用户 turn 在飞（`turn_state='in_flight'`）→ trigger **defer**（20s × 15 周期，超限静默）；无在飞回合但**有 pending task_book 计划**→ trigger **静默**（计划 echo 已承担方案叙事，trigger 不得再抢麦；落 dock 前复评 `is_pending_plan`，命中即整体静默，永不压过 docked plan）；两者皆无 → trigger 方可说话。准入门从「时序门」升格为「叙事所有权门」。
2. **界面语言唯一 owner**：conversation 的界面语言只有一个事实源（请求链的 UI locale / 既有 pin），**一切 assistant 写者**（plan path / chat path / trigger / 未来的 worker 生言语）**继承它**，不做 per-writer 推导。`_trigger_language` 的 history 文字推断降级为「owner 缺席时的兜底」，素材语言永不是言语信号（现行原则不变，本条补的是 writer 间不分叉）。
3. **验收标准**：用户看到画布 + chat 的第一眼，5 秒内能回答三问——「系统理解我要做什么吗 / 它准备怎么做 / 我下一步该点什么」。两个 writer 各说一半、语言不一 = 不过。

**明确不做**：不引入 writer 仲裁器 / 优先级调度层——规则是两张静态谓词（在飞？有 pending 计划？），不是新架构。

**Consequences**: trigger 的可说话窗口收窄到「会话空闲且无待决计划」——盲区由世界事件自身的画布表达兜住（静默教义不变：盲评不如不说）。语言分裂在结构上不可能（单一 owner），prompt 级语言指令仍在但不再是唯一防线。施工 = `_project_turn_in_flight` 同族加 pending-plan 谓词 + trigger 语言解析改读 owner，均落在 `trigger_turn.py` 一处。

**Related**: ADR-077（触发回合 = ToolLoopAgent 第三座，本条给它叙事所有权边界）/ ADR-052（厚 agent 产品层——一个 agent 的产品承诺在会话层的兑现）

## ADR-081: 选项语法统一律——固定选项全归 OptionDock，全局编号 1/2/3

**Status**: Decided (2026-09-17)

**Decision**:

1. **二态法则**：凡是系统希望用户**从固定选项中选择** → 一律走 OptionDock（问句 + 全宽选项行 + 铅笔自由行，形态律 ADR-053 R1 不变——trigger 建议 dock 同走**阻塞形态**：ADR-080 双谓词把 trigger 限定到「会话空闲且无待决计划」才说话，阻塞成本低；× = 优雅不选）；**开放式建议** → 普通散文。**无第三种「半结构化 pill」形态**——一切固定选项走 OptionDock，中间形态无座位。
2. **全局数字编号**：OptionDock 选项徽章从 a/b/c 改 **1/2/3**——用户对所有来源（plan / ask_user / trigger / clarification）的固定选项形成同一 interaction grammar（「选 1」恒 = 第一项）。autoResume 的位置命中（字母/序号/原文三态）本就确定性支持序号，改的是展示面不是结算机。
3. **trigger 建议的去向**：`wrap_up` 的 suggestions = **纯 label 数组**（≤3、≤40 字、blank 丢弃；无 download 动作——产物下载是画布产物卡 factsbar 的既有动作座位）；有建议时 review 行经 `_dock_question` **dock 成真实选项问**（选项 id = 1 起位置序号），作答走 answer 端点 generic 续聊分支——**按项目 run 状态分派**（无 run 走 plan path 起草计划，有 run 走 chat path——首跑前点「剪一个金句快剪版」必须产出计划而不是提案工具回答），选中 label 即用户发言。
4. **读容忍**：存量 `intent.type='trigger_review'` 行的 pill 形 suggestions 前端回放渲染保留至自然消亡（灰行旧数据不动），新行的 dump 只带 label 数组（取证用，前端不消费——dock 从 `question` payload 重建）。

**明确不做**：不为建议发明任何新组件/新形态（无「非阻塞 dock 第四态」——trigger 建议复用选项问全机器）；不改 ask_user 的 schema（options 数组不动，纯展示层换徽章字符）。

**Consequences**: 用户面对的选择交互收敛为唯一形态 + 唯一编号语法；「点击 pill 替我说话」的隐式代发声通道关闭，一切选择都经过 dock 的显式作答语义（QA 归档 / autoResume / bail 同源）。施工面 = `QuestionDock` 徽章字符 + `ChatDock` 轮询通道（散文排干后 dock 选项问；`triggerSuggestions` 只服务存量行回放）+ `WrapUpArgs` 纯 label 数组（无 `Suggestion` 类）+ answer 端点 generic 分支按 run 状态分派。

**Related**: ADR-053 R1（形态律——选项问阻塞形态的母体，本条不改阻塞语义只改徽章与消费面）/ ADR-070（确认拍回座 dock——dock 是一切固定选择的唯一座位原则的延续）/ ADR-077 判词③（trigger 是说话不是第二意图表面——建议入 dock 后此原则更显：dock 选项的作答仍走 `/chat` 唯一意图面）

## ADR-082: 画布呈现纪律——可读性永不反噬语义

**Status**: Decided；effective rank 与剩余可读性需求 = ADR-098 / `VERIFICATION.md`。

**Decision**:
1. 永不为了排线新增语义节点、改变执行拓扑或补假边；特别不得恢复虚构 transcript 中继。合法工具只有呈现层的 rank 投影、frame 预留、分组、edge routing、锚点与视口。
2. 先保证几何不重叠、不溢出、方向正确，再处理同族分组、长边与居中。任何客户端显示推导都不能成为第二 rank 权威，也不能让 RunOp 读 x/y。
3. 验收使用真实产品语义：用户应能读出“源素材 → 实际可编辑工作产品/成片”的关系、当前状态和下一步；不以固定的 Source→Transcript→Consumer 三列作为及格线。
4. 既有节点稳定、append-only 与 settled freeze 不动；不引 dagre，不用 clamp、翻边、固定 x/y 或服务端重排旧帧掩盖错误。
5. 背景 refetch 不改变相机；新 draft 与新节点只按用户发起节拍 fit/center。布局修复不能改变打字机、执行拓扑或版本语义。

**Related**: ADR-036/057/067/086/098/111/113；`docs/VERIFICATION.md`。


## ADR-083: 信任锚 echo——present_plan 的三语义职责 + grounding 四级证据链

**Status**: Decided (2026-09-17)

**Decision**:

1. **echo 三语义职责**：present_plan 的言语承载 ① **信任锚**（我实际读到什么 + 核心判断——付费前用户必须能验证 agent 理解了内容）② 计划转述 ③ 完成标准 + 下一步，自然表达为 2–3 句，职责相邻可合并成句，永不为凑数注水。瘦身意图保留：bookkeeping / 公式脚手架 / DAG 复述仍禁（结构是画布的职责——Chat 管 understanding/judgment/confirmation，Canvas 管 structure/plan，互不复述）。
2. **grounding 四级证据链（严格）**：理解行 = 完整语义证据 → transcript/excerpt = 限于已读文字的语义证据 → 用户自己的描述 = 复述/组织用户说过的话，不 extrapolate → filename/metadata（名称/时长/尺寸）= **仅身份证据**，证明「这是哪个文件」，永不推断内容（`xy_2_15s.mp4` 不支持任何内容断言；陈述时长/格式事实合法）。本回合无语义证据 → 职责① 空缺不编造。
3. **assemble 注入优先于工具轮次**：`plan_turn.assemble` 直接读内容寻址的 ready 理解行入 context（`understanding_lines`，复用 perception 的 `understanding_digest_lines`——一条格式化律两消费面）；未物化 / 形态过期 = 缺席，证据链降级到 excerpt / 用户原话。`get_understanding` 读工具原位保留（mid-conversation 追问的入口），但不再是判断的前置义务。
4. **single writer 不动**：ADR-080 双谓词维持（pending task_book 时 trigger 静默）；`run_completed` 收官判断是付费后复盘，与付费前信任锚是两个节拍，不受影响。

**明确不做**：不恢复双 writer / 不加仲裁层（ADR-080 明确不做维持）；不把理解摘要做成独立 deterministic UI 组件（候选 C 存档——未来可作资产详情页补充，不作替代）；不动 ToolLoop / canvas / trigger 仲裁。

**Consequences**: 机械感的根（2 句律 + 文件名级认知）消除；判断的诚实性由证据链代码可查证（注入在 assemble，读到的才说）。prompt 面改动过 prompt gate（ADR-071）。验收：**点 Start 前用户能从 Chat 确认 agent 真懂了素材，且不听到重复的 DAG/计划描述**——不是「多了一句话」。

**Related**: ADR-080（单一叙事者——本条是同一 writer 的「 richer turn」兑现）/ ADR-077（感知族读工具——注入复用其格式化律）/ ADR-058（展示文案二源律——判断句的素材认知源自世界自证的物化行）/ ADR-060（echo 防编造律——grounding 链是其素材侧推广）
## ADR-084: 言语语义与 Start 表达——grounding、可见面与当前授权

**Status**: Decided；read 言语由 ADR-104/109 接管，确认档由 ADR-117/139 接管。

**Decision**:
1. present_plan 的言语承担语义职责而非固定句式：真实素材/需求理解、当前累计方案、完成标准与当前可执行承接。不得复述 DAG、把内部执行过程写成持久散文，或为显得有方向而编造唯一建议；Start、修改与等待授权按真实状态表达。
2. “理解用户要什么”与“已读素材内容”是两个事实。素材未读时只能陈述真实处理状态；需要内容的回答按 ADR-102 在同一工具内等待终态，不编造内容也不制造第二 writer。
3. read 前后是否说话回归自然 SPEECH 律与 checkpoint 路由；**不存在 read 一律静默或一律过程旁白的规则**。活动由 Activity/WorkSegment 表达，终答不念操作日志。
4. Start 表达必须指向当前真实可用手势：ask 档以朴素方案判断问句收尾；auto 档有制作意图时不机械追加同义确认；守卫线/NULL 仍带价确认；无制作意图时等待用户发话。
5. Film 首稿必须邀请审阅并在批准后制作；普通修改、重制与 review-only 按 ADR-137/139 分支，不统一预告“出来后再调”。
6. 只有实际可见的面才可被指认。`canvas_visible=false` 的交付承接句窄门归 ADR-118；reveal 前不得声称计划已在画布，失败分支不得宣称有可点产物。

**Related**: ADR-060/083/092/102/103/104/109/111/117/118/139/144。

## ADR-085: 一回合多交付——Phase / Checkpoint / Settled

**Status**: Decided；当前路由由 ADR-104/109 更新，持久化顺序由 ADR-108 决定。

**Decision**:
1. 一个回合可以包含三类用户可见交付：**Phase** = 瞬态系统状态；**Checkpoint** = 有事实依据、对用户有价值的中途言语；**Settled** = 回合最终答复。Checkpoint 不是 chain-of-thought 或 raw tool output。
2. 非终态工具调用前，模型自带非空散文且参数校验通过，可在 execute 前发射 checkpoint；不再维护工具资格白名单。终态工具散文留账本并随 envelope 结算。
3. checkpoint 是 **earned，不是配额**。`MAX_CHECKPOINTS_PER_TURN=4` 只是防啰嗦护栏；超出记 `tool_loop_checkpoint_capped`，不把被截文字偷偷并回 ledger。纯 answer 或单读直出回合合法地为零。
4. 每个 checkpoint 是 transcript 数组一等行，带独立 seq 与 SSE 镜像；失败/中止也保留真实工作证据。cancelled 从可见投影退役，真实 failed 保留。
5. 观测必须能区分路由与质量：`tool_loop_checkpoint`（含 predecessor）与 `tool_loop_turn` 汇总 reads/checkpoints/outcome。只有实测证明主路径系统性缺失用户价值时才重审路由，不为提高数量强行制造 checkpoint。
6. 覆盖至少五种路径：非终态+散文+合法参数+channel；终态只走 envelope；参数拒绝不发射/不执行；无 channel 时 ledger 不丢字；cap 后记录 capped。
7. 禁逐调用汇报、禁展示推理/概率/候选腹稿、禁第二 writer；Activity 与 checkpoint 可以共存，但各自必须表达不同事实。

**Related**: ADR-083/087/093/099/104/108/109/110；`VERIFICATION.md`。

## ADR-086: 拓扑空间权威三律 + Product Canvas ≠ Execution Graph——Product Flow Alignment 的架构地基

**Status**: Decided (2026-09-18)；施工合同 = `docs/VERIFICATION.md`

**Decision**:

1. **Product Canvas ≠ Execution Graph（追认 + 准入闸）**：画布节点 = **用户拥有、消费、验证或可能修改的产品对象**——含最终产物与实际注册的可编辑中间工作产品（翻译文档、分镜表、字幕文档、渲染视频等）；**transcript 是 asset 内容，不是节点**（ADR-113）。节点永不是纯执行步骤；`task_book / preprocess / understand / plan / materialize / render / verify / queue / retry` 类概念永不上画布。现行 read-face 机制（B1-lite 过滤 / B4-lite 收编 / `_read_face` 映射 / workflow_steps 永不成画布节点）追认为本律的执行机制，不是临时补丁；**新增图节点类型 / spec.tool 必须声明 product visibility，默认隐藏**。「不是最终产物」永不是隐藏理由（分镜表先例，ADR-072）。
2. **拓扑/语义 rank 是唯一空间权威，frame 是呈现 projection**：一切用户可见位置的上游 = Product DAG 拓扑（rank = 拓扑深度）。**rank 的输入边界**：只消费表达生产/消费关系的真实语义边；新图没有 synthetic transcript→consumer 边；历史血缘、跨 run 关系、纯呈现边（lineage / historical / presentation-only）**不参与** rank——ADR-036 的 lineage/dependency 区分是本法母体。`graph_nodes.layout` 帧 = **y 座位 / w·h 预留 / 稳定锚**三职；x 的显示值 = rank 投影，服务端出生帧的 x 不再是显示依据。**方向不变量**：一切用户可见 edge 满足 `rank(target) > rank(source)` 且渲染 `x(target) > x(source) + MIN_GAP`；sibling 序稳定；不依赖 birth order。append-only 保序律对 y/稳定锚维持（ADR-036 维持）；**服务端帧零改动、存量零迁移**（呈现层修法，ADR-082 判词① 先例）。**「零迁移」≠「legacy 图一概不碰」**：旧 frame 不迁移（projection 消化），旧 edge 按 ADR-062 边对账律正常自愈（该 retract 的 retract），旧 node 按 read-face 既有规则判断。
3. **Run order = DAG topology，永不读 layout.x**：`RunOp` 排序改读图边拓扑深度（与 rank 同一事实源）；`graph_revise.py`「x 序 = 深度序」假设删除。执行顺序与视觉坐标解耦——二者共享同一 Product DAG，视觉坐标永不做执行依据。本项触及执行面，施工必须带 regression scenario（R1 执行 invariants I-EXEC-01~04 不动）。
4. **生长 = 呈现编排，节点语义一次 stamp（K5 维持）**：ADR-057「图先展示后运行」维持——计划确认前用户看到完整链 + 逐节点估价是 fold 报价前提。「动态生长感」由出生编排（深度序 reveal）+ 节点原地状态迁移（draft → running → done）承载；loading → ready 是同一 node 更新；不把内部 execution task 逐个变成画布节点；不为生长感让服务端 drip-feed。

**明确不做**：不重写 edge routing（贝塞尔 / 端口法则 / 出入锚保留——错误的语义布局不用漂亮的线补锅，反过来也不为排线改拓扑）；不用 clamp / 翻转 edge / 固定 x-y hack 掩盖拓扑；不迁移存量帧、不引 dagre（ADR-036 判词维持）；不把 SSE 做成事件总线（节点状态 = `step.updated` → graph refetch 既有模式）；不动 ADR-084/085 / 打字机律。

**Consequences**: 布局算法的输入从「出生时刻的拓扑快照」改为「当前 Product DAG 的 rank」——帧错位五源（L1-L5）的视觉症状结构性消除；执行序与呈现解耦后，「帧错 → 执行错」的污染链断掉；Product Canvas 的边界从约定升级为带准入闸的 invariant。空帧处置细则：出生地保证每行必带合法帧；前端静默原点兜底删除——dev 显式失败 / prod graceful fallback（fallback = rank 投影，不是原点）。

**落地座位**：契约模块 = `app/pipeline/product_graph.py`（pure）——判词 1 的准入闸落地为 type 层 membership 谓词（媒介五值可见 / `HIDDEN_ROLES` / `LEVER_TOOLS` 两显式枚举 / 未知 type default-deny，等效机制）；判词 2 的 rank = `product_ranks`（longest-path，rank 边集 = `{video, audio, text}`，ctx 引用流排除）；判词 3 的消费点 = `topological_order`（与 rank 同一事实源，RunOp 接入）；canonical fixture = `apps/api/tests/test_product_graph_pure.py`。legacy `materialize` 行的读面可见性与谓词不一致 = 已知残留；生产 DB 清零证据与删除条件归 `docs/VERIFICATION.md` §4 和 `docs/VERIFICATION.md` §0，未满足前保留兼容。

**Related**: ADR-036（布局自算 + append-only）/ ADR-057（图即产品对象——判词① 的母体；K5 维持）/ ADR-062（边对账律——对账不再依赖帧一致性）/ ADR-067（出锚语义律——「呈现忠于语义」同族）/ ADR-082（呈现/语义隔离铁律 + 呈现层修法先例）

---

## ADR-087: Agent Interaction & Product Lifecycle Architecture——三条语义层 + Lifecycle / Activity / Confirmation 三合同 + 依赖方向冻结

**Status**: Decided；当前剩余验收与 hygiene 前置 = `docs/VERIFICATION.md`，全局状态 = PROGRESS §0.2。

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

**Presentation 映射**：PLAN_READY → Review Surface（Canvas + Confirm Dock 出现）；CONFIRMATION_READY → Confirm action enabled。**Canvas 与 Confirm Dock 是同一 lifecycle 状态的两个 presentation effects，不是两个独立 readiness predicates。** 移动端 parity：无画布，评审面 = 散文 echo，同一投影戳驱动，不另造谓词。

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

### 4. Authorization Doctrine（现行）

核心：**Task Intent ≠ Paid Execution Authorization；呈现也不自动等于授权。**

标准路径：`Task Intent → Preparation → PLAN_READY → Charge Semantics / Scope / Production Intent gates → Paid Run`。

- **两档偏好**：`confirm_execution` / `confirm_credits` 默认 auto；ask 要求对应批准。理解性提问不是许可请求。
- **auto 只免批准拍**：不创造制作意图、不免除呈现、版本、材料、scope、费用或 Film 首稿审阅。无制作请求、纯修改/讨论/“先看看”在任何档都等待。
- **守卫线任何档恒问**：`billing.always_confirm_above` 或 NULL 不可报价族必须带价确认。NULL 不阻塞 PLAN_READY，但不能被折叠成“≈0”。
- **Existing Approved Scope**：retry、internal repair、render continuation、已批准范围内的执行可继续；scope classifier 按 resulting paid scope 判 continuation / expansion / unproven，unproven 失败闭。
- **确认范围**：Confirmed Scope Snapshot 记录编译范围、confirmed_at、confirmed_via 与版本；它是范围/重试证据，不把 auto 伪装成用户手势。
- **Start 唯一强制点**：服务端 `evaluate_start_gate` 校验 scope、报价、守卫线、制作意图、材料、活动 run 与版本；dock、口头和 typed answer 共用。客户端按钮 disabled 不是防线。
- **Film 专用首稿拍**：作品首个分镜版本必须先完整呈现并持久化 `film_presented_message_id`，随后用户明说生产或点击 Start；auto、首条“直接做”与 `review_hold=false` 都不能同回合开工。
- **无 review 档**：执行中的 direction interrupt 是 HITL，不是第三确认偏好。
- **工具描述 = 行为真值**：propose/design 工具是否只呈现、是否允许同回合 start，必须与当前实际执行一致。

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
- **Presentation Contract 归位**：Confirm/Start 唯 dock pill（无 Canvas Confirmation Seat）；`lib/lifecycleStamp.ts` 三态谓词（stamp missing = unknown ≠ ready，无 fallback-to-true）；confirm/running 两腿由戳派生（`confirmActive = intentReady && isPlanReady(lifecycle) && !runAttached`，无 phase 状态机）；System Status 相位面 = 基座 Thinking… + 分镜跨度三相位 + 显式清除帧（ADR-133：通用 LLM 黑盒窗不设别名），永不建相位帧 → lifecycle readiness 正向锁；**「lifecycle 键恒在」不变量**（graph 响应零节点也补戳）；**run 活性/存在是 transport 事实，非 lifecycle 推导**（合法读者在册：ChatDock `runAttached` / `projects.$id.index` `hasRuns` / `runActive`——禁补戳读者）；`render_superseded` 入 `USER_ERROR_LINES`；ChatDock normalize* 族住 `chatProtocol.ts`；无 `_DOCUMENT_CONFIRM_PX` 几何债。
- **Confirmation Doctrine 统一实现座位**：deterministic scope classifier（零 op 词汇纯核 + 装配器）按 resulting paid scope 裁决 continuation / expansion / unproven，绝不按 operation 名称猜测；unproven 失败闭，`/generate` 在余额检查前返回机器可读 `scope.unproven`。呈现与授权按 ADR-117/139 分流：auto 只在制作意图、呈现与全部守卫成立时免批准拍，ask 与守卫线走确认；Start 服务端 `evaluate_start_gate` 是唯一强制点，dock pill 与口头/typed answer 共用同一机器。
- **依赖方向座位（四族合法缝，§6 唯一通道）**：① trigger fires（run_completed / run_failed / craft_decompiled）→ `pipeline/trigger_events.py` 白名单事件缝（白名单冻结，扩名单 = ADR 评审；fire-and-forget 未注册 = 静默降级永不 pipeline 失败；`app.main` / `app.worker` 两组合根双注册）；② 同步会话写四命令（dock_interrupt_question / finalize_bailed_runs / seed_project_prompt / discard_unanswered_plan）→ `pipeline/conversation_bridge.py` 显式 protocol（未注册 fail-loudly）；③ 会话读四助手 → `platform/conversation_context.py` 只读协议座；④ 完整 chat 回合（POST /outputs/{id}/regenerate）→ 端点住 `chat/routes.py`（URL/method/OpenAPI 不变）。`build_context` 住 `chat/context.py`（各层自装上下文）。pipeline→chat import 清零、跨模块私有 import 清零、零新增 deferred import——常驻守卫 = `tests/test_import_direction_pure.py`（AST 双门 + 冷导入探针 + 组合根接线保险 + 自引用改名碰撞扫描）。
- **Hygiene 挂账**：service.py / schemas.py / graph_fill.py 拆分、Message.intent typed union、edit_output operations 路径 commit 律对齐——永不进关键路径，排期见 PROGRESS。
- **新能力机械回答表（验收基准）**：Agent action → Tool Interface；改 Domain → Application Command → Write Gate；用户要看到在做 → Activity Projection；改变产品阶段 → Lifecycle Projection；UI 响应 → Presentation consumes projection。若新增一种能力仍需「新 phase + 新 envelope + 新 ChatDock if + 新 polling + 新 prompt 条件」，说明本合同被破坏——STOP 上报。

**Related**: ADR-057（图即产品对象——Lifecycle 投影的消费面）/ ADR-063（估价诚实面——§2.1 保持其有效性）/ ADR-070（确认拍 dock 唯一座位——Confirmation Dock 的形态基座）/ ADR-072（task_book 节点下线——计划真身各归其位）/ ADR-077（会话层工具 loop——Activity 的内部事件源）/ ADR-080（单一叙事者）/ ADR-083/084（言语语义管线）/ ADR-085（三层交付模型——Checkpoint 是 Activity 的言语族近亲，Activity Projection 不重设计它）/ ADR-086（拓扑空间权威三律——C-0/C-1/C-2 保护合同）/ North Star §3（Agent = Decision Producer——原则 4 的母体）

## ADR-088: Exploration Artifacts & Project Working Loop——探索产物族与 Agent 工作循环

**Status**: Decided, **目标架构 / 渐进实施，未整体落地**；当前工具与节点以 registry 为准。母文档 = `docs/JOURNEYS.md` 旅程四；与 ADR-089 双生——本条答「Agent 在 Project World 里生产什么、这些东西如何持续工作」，ADR-089 答「这些产物如何确定性进入执行世界」

**Decision**:

### 1. 北极星与主循环重定义

**Agent 的主循环不是 Run，而是围绕 User Goal 在 Project World 中连续产生、检查、演化用户可理解的工作产物；Paid Run 是这条连续工作流里的一个授权边界，不是产品主循环。**

> Agent continuously produces and refines user-meaningful project artifacts; it does not compile or directly execute workflow internals. Paid execution begins only within the presented and authorized scope (ADR-117).

「Agent 开始工作」≠「Paid Run 开始」——与确认教义 §4 的准备阶段同义，本条从用户体验侧立。授权 = 明示确认（ask 档）或常驻授权（auto 档默认，ADR-117）；呈现义务（方案必须与开工同拍可见）恒在，与授权通道无关。

### 2. 探索产物族（Exploration Artifacts）

三个 canonical 对象，均为**证据容器**：

- **候选集 Candidate Set**：主题检索的证据集合；成员 = `{asset_id, start, end, excerpt, speaker, duration}`，每字段可回溯 transcript。**R1 粒度律**：合集 = 一个 artifact（默认折叠、可展开）——画布可见粒度服务于「用户纠正 Agent」，而非复刻 agent 内部操作数量；独立铺卡永禁（画布密度律）。
- **精选 Select**：候选的定版；**R7 = 证据引用**（指向源片段，不复制源）；**R3 理由 = artifact 属性**（verdict + 一行用户安全结论 + 证据指针）——**判断的输出是属性，产生判断的私有推理过程永不成为产品状态**（reasoning 永不持久化，CoT 闸不变）。
- **内容方案 Content Plan**：一个 Select 的内容化方案（source range / 产出要求 / 语言 / 字幕 / 文案 / persona 引用）。**R8：Content Plan ≠ Task**——它描述「我们准备怎么把这个内容做出来」，Task DAG 描述「Execution Runtime 执行什么」（编译关系 = ADR-089 §2）。**R9：persona / presentation 默认在 Structure 阶段注入**，不参与候选评估（除非用户目标点名）。
- **完整性自检**：plan 就绪前经确定性完整性检查（区间 / 语言 / 产出类型 / 必填输入）；artifact state `draft → ready`。

### 3. 双状态机（R10 / R17 / R18）

Artifact 状态机 = `draft → ready → revised → compiled → superseded`；Execution 状态机 = 既有（draft → running → done / failed）。**修订发生在哪个语义层，决定哪台状态机变化**——craft 修订（购买信封内的 how）plan 状态不动；plan 级修订（what 变）才走 `compiled → revised`。**R18 同框纪律**：两族可同框展示，**永不共享状态语义**——plan 节点永不镜像 running（`ContentPlan.status = running` 永禁）。

### 4. 探索产物存储与执行隔离（R13 / R14）

探索产物住独立 `exploration_rows` 表，不是 Product Graph 节点，也没有 `prototype` 座位；项目级联与 `journey_id` 归属由该表承载。legacy `graph_nodes.type="exploration"` 行只在读面过滤，不迁回执行图。**I-EXPLORE-01（不变量）**：

> **Exploration artifacts MUST NOT participate in execution topology, execution closure, quote/rank calculation, or media-flow edge semantics.**

plan → compiled chain 的链接 = **spec 引用，永不是 Graph Edge**（边词表保持媒体流纯洁：video / audio / text / ctx）。**探索写门**：免费但仍是真写门——事务（savepoint）+ 证据校验（start < end、不超素材时长、与 transcript 有交集）+ 回合幂等；agent 永不直接写表（终态工具 `propose_candidates` / `propose_selects` / `propose_plans` / `revise_plan` 经 Application 层落门）。真实目标 DB upgrade/downgrade、既有行读/编译/replay 验收未完成前，不得宣称存储迁移已闭环。

### 5. 免费探索区连续性（R2）

探索区（检索 / 评估 / 精选 / 结构化 / 自检 / 编译 / 报价）**默认连续工作，不在拍间停**——**纠正成本对称性决定停顿位置**：免费区纠错便宜（chat 一句插话），故免费区不停；「先给我看看候选」= 作用域暂停指令，逐消息生效。停顿的唯一合法位置 = ADR-089 §5 停顿定律。

### 6. Work Session（R5）

Runtime 可以是多回合的（链式回合 + trigger turn，机制 = ADR-077 §3 既有），**用户体验永不暴露 runtime 回合边界**——一个 goal 的工作 = 一个连续 work session 的 Activity 视图（阶段标签随拍迁移，不按回合替换块）。呈现规格见 JOURNEYS 横切 §6（活动行 = 散文段间穿插的证据行）。

### 7. 阶段化 Observation（R11）

agent 的上下文 = **当前 action 所需的 Project View**，不是一次性 context dump——每拍只取相关切片（Goal / 相关 artifacts / 证据 / 能力目录）；历史旅程 = 摘要行 + 按需 read（§10 读取律）。read 族 = `get_node` / `get_pending_plan` / `list_runs` / `get_artifact`——观察合同 ≥ 行动合同。

### 8. Reviewer 合同（R21 / R22）

run 完成触发回合的 reviewer = **确定性执行验证 + 已批准 plan 的意图兑现检查**（时长 / 字幕存在 / 溢出 / 配音 / 区间 / 产出类型——spec 与证据比对，**不是看片**）；**主观内容质量（「够不够精彩」）永不伪装为系统可验证事实**，归用户纠正。目标修复半径 = Approved Scope 内 retry / internal repair（教义预授权），scope 外必须重新呈现与授权（R22）；**当前交付 reviewer 只报告事实，自治修复尚未兑现**。深度看片复核挂 PROGRESS 需求池。

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

**Consequences**: 迁移弧（ADR-089 §8）：`propose_tasks` / `edit_graph` 与探索流并行 → 证明 → 退役，一刀切永禁。**既有合同承重零改动清单**：确认教义 §4 / §2.1 / scope classifier / Start 四合取 / draft 图 K5 / dock pill 唯一座 / G-1 同座 / trigger turn 白名单 / ADR-058 通道分家 / ADR-069 / ADR-078 exemplar / Activity 十规则 / 打字机律 / persona brand·voice / config 三分流 / C-0/C-1/C-2 / 拓扑铁律（ADR-028）。**认知验收入执行规则**（PROGRESS §0.4 执行规则 7）：触及 agent loop 的批，DoD 必答「agent 看见了什么 / 内部表示是否一致 / 怎么知道自己对了」——A-1 类盲区不再依赖运气。施工排期见 PROGRESS。

**Related**: ADR-089（双生——执行边界）/ ADR-087（三合同——本条的准备阶段 / 活动 / 确认从其条款生长）/ ADR-077（有界 loop + trigger turn——链式回合机制基座）/ ADR-057（Product Graph 与探索存储的边界）/ ADR-086（Product Canvas ≠ Execution Graph——同框纪律的母体）/ ADR-028（拓扑铁律——I-EXPLORE-01 保护它而非削弱）/ ADR-058 / ADR-063 / ADR-069 / ADR-070 / ADR-078（通道分家 / 估价诚实 / quote 指认 / dock 唯一座 / exemplar 参数源）/ ADR-052（厚 agent 判词——本条是其产品层的兑现形态）

## ADR-089: Capability Compilation & Execution Boundary——能力编译层与执行边界

**Status**: Decided, **目标架构 / 渐进实施，未整体落地**；当前主链工具未被本决策预先退役。母文档 = `docs/JOURNEYS.md` 旅程四拍 6/9

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

> **Agent stops iff the next act exceeds its standing authorization or requires information only the user has; every stop must present a complete, user-judgeable decision package.**（Agent 只在下一步超出常驻授权或需要用户独有信息时停下；任何停顿必须形成用户可理解、可判断、可执行的完整决策包。）常驻授权 = 用户明确制作意图 + 用户权限档（ADR-117/139）：auto 只免对应批准拍，ask 要求对应批准；守卫线、NULL、未证明意图和 Film 首稿审阅始终独立生效。

推论：免费探索区不停（ADR-088 §5）；`ask_user` = 信息类停（同律 b 支）；执行中 direction interrupt = 同律在执行侧的投影；确认拍 = 授权边界停——ask 档逐拍；auto 档仍会在制作意图未证明、守卫线/NULL、版本/条件未满足或 Film 首稿未审阅时停下。**Confirmation = Agent 已把真实授权边界准备成用户可判断的决策包**，不是「Agent 做完了所以要确认」。

### 6. 修订分类与范围裁决（R19 执行半边）

修订分两语义层——**plan 级**（what 变：`revise_plan` → 重编译 → 重报价 → 重确认）与 **craft 级**（购买信封内的 how：`revise_output` → 编译为 wiring op → 锚定受影响子图，ADR-058 先例）。**唯一判据 = 结果执行范围是否包含于已批准范围**（`new_scope ⊆ approved_scope` → continuation 自治；否则 expansion → R15 停顿）——agent 可提议语义理解（「我理解你想把字幕调短」），**永不自封 continuation**；scope classifier（D4 结果范围律）是唯一裁判，一个字不改。

### 7. 报价站在 artifact 事实上

quote 输入 = Content Plan 具体字段（精确区间 → 时长 → 渲染单位；语言数 → dub 单位；字幕模式；文案条数）——报价从 LLM 提议参数升级为 domain source of truth；**Known / Deferred / Conditional / Held / Actualized 五面披露保留**（ADR-087 §2.1 不动；「plan ready ≠ 一切成本精确已知」边界明文化）。

### 8. 迁移弧与 select_clips 裁决

新探索流与既有 chat 路（`propose_tasks` / `edit_graph`）**并行 → 证明 → 退役**——一刀切永禁；退役扳机 = 旅程四主链 e2e 全绿 + 迁移期无 regression 在册。干脆请求（ADR-088 §9）在新世界 = Content Plan 的零探索退化形态，词表统一。

**迁移边界（CURRENT）**：当前主链仍使用 `propose_tasks` / `edit_graph` / `revise_output` 等已注册产品语义工具，探索链与确定性 Content Plan 编译尚未完成整体替换。不得提前从 prompt、registry 或执行层删除现役工具。任何退役必须以当前 `SCENARIOS` 主旅程全绿、真实数据兼容与 PROGRESS 明确销号为前提；当前剩余工作归 `tasks/agent-working-loop-iter-3.md`。

**`select_clips` 存留裁决**：
① **执行世界永不做发现**——发现工作的唯一座位 = chat 边缘 agent 探索链（R6 路由 + 证据 reads + 探索写门）；plan 来源的工作经编译器走 `cut_segments`（Select 证据指针编译期解引用 → 数值区间确定性裁剪），编译器永不编译 `select_clips`（N-56）。② select_clips **当前仍是主链执行工具**，同时服务零探索退化形态；只有 Content Plan 新链完整接管并通过相同旅程后，才可评估其退役。不得把目标架构写成当前已禁用。③ 候选存留面复核：长素材二次裁切 = chat 侧 reads + `revise_selects`（N-58）覆盖；语义连续处理 / execution-time transformation 无在册需求——均不构成保留 LLM 可见性的理由。④ 调用面清单（退役时的机械削除对照表）：注册表 `app/tools/__init__.py` / 节点 `app/tools/clips/node.py` / prompt 面三处（`intent_router_system.j2` / `_specific_instruction.j2` / `_writers_no_material.j2`）/ recipes 预设链与执行侧声明（tracks / morph / orchestrator / lifecycle / derivative_dispatch / decompile / outputs / verify / graph_fill / schemas）/ web 展示键（ChatDock / chatProtocol / i18n / 项目页）。

**Consequences**: 每批过既有门禁（纯 pytest / prompt_gate / 剧本 + PROGRESS §0.4 执行规则 7 认知验收）。**零改动重申**：执行写门（`apply_wiring_ops` / `create_run`）/ scope classifier / Start 四合取 / 计费三词两层与 hold→capture→release / fencing（ADR-079）——本条不改任何执行世界机制，只改「谁有资格向执行世界递东西」。

**Related**: ADR-088（双生——探索产物与工作循环）/ ADR-087 §4（确认教义——停顿定律是其付费边的泛化；Consequences Phase 4 = scope classifier D4）/ ADR-028（拓扑铁律——编译器是其新兑现形态）/ ADR-055（计费——决策包的费用语义面）/ ADR-058（通道分家——craft 修订的卡面直改先例）/ ADR-079（fencing——执行写不变）/ ADR-057（draft 图 K5——编译产物的画布形态）

## ADR-090: 精确编辑——`edit_output` 受控终态工具 + quote→range 解算器

**Status**: Decided (2026-09-24)；母法 = ADR-088/089 工作循环与执行边界

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

当前四件零 LLM 成本且重渲染按现行价格为零时，edit→render 不机械复用口头确认闸；这是零费用精确编辑，不是绕过授权。未来任何涉 LLM、外部付费调用或价格非零的 op，必须在执行前进入当前报价、scope、ask/auto 与守卫线机器，按真实 capture 位置扣费；不得沿用“编辑永远免费”的假设。

**Consequences**: `edit_output` 终态工具与解算器按本合同工作，精确修订归当前用户旅程矩阵；**operations 的用户级 undo/restore UI = P1**（REST 面已通；无 `undo_edit` chat 动词）。**认知验收**（PROGRESS §0.4 执行规则 7）必答：agent 看见了什么（产物卡 + 词级 transcript reads）/ 怎么知道自己对了（解算回声 = 「我把 0.0–4.2s 这段去掉了」的事实句）。验收标准：「把开头那句删掉」「第二条再短 3 秒」「字幕换 karaoke」「标题改成 X」四请求族 e2e 全通且 undo 可回滚（含解算器跨 cue/大小写容忍/未命中拒绝/多义拒绝边界面）。

**Related**: ADR-089（终态词表 / 编译移出 LLM——本条是其词表扩员）/ ADR-088（工作循环——edit 是产物打磨拍的主座）/ ADR-069（quote 指认）/ ADR-058（通道分家——chat 修订唯一意图面）/ ADR-016（clip-spec 是本编辑族的参数契约）/ ADR-074②（渲染台账律）/ ADR-091（编辑历史 = work 的 operations 链）/ ADR-087/117/139（未来付费 op 的授权）

## ADR-091: 产物身份与重跑生命周期——work/version 语义 + 归档不变量

**Status**: Decided (2026-09-24)

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

## ADR-092: 口头确认律——方案 dock 后的确认拍（ask 档法律）

**Status**: Decided (2026-09-24)；现行法：确认拍仅 ask 档生效；auto 档（默认）由 ADR-117/139 接管——制作意图在场且无其他确认债时可在呈现后开工，无额外批准拍；auto 不创造制作意图

**Decision**:

**口头确认律（ask 档）**：方案 dock 后恒等用户确认拍——echo 收尾恒为一句朴素的方案判断问句（一词可答）；口头 yes 走普通 chat 道到 start_run，与 Start 钮同一 Start 机器；无任何「存好的策略替你开工」路径在 ask 档内存活；收尾永不带「成片出来后再调」式交付后修订预告。

**偏好持久化座位**：用户级设置 = `users.settings` JSONB + GET/PUT `/auth/settings`（服务端为准，前端 localStorage 降级为读容忍回退）——座位不变，住户 = ADR-117 两键（`confirm_execution` / `confirm_credits`）；旧 `confirm_strategy` 三档弃读删除（其从未产生行为，零迁移）。

**Related**: ADR-117（授权前移——确认教义默认值翻转的母法）/ ADR-089 §5（停顿定律——授权边界停的泛化座）/ ADR-087 §2.1（费用语义五面——estimate 面披露纪律与确认义务分离，两档不变）/ ADR-055（计费母法——参数表座位）

## ADR-093: chat 言语真值律——信封对账补全 + 起始句言语权恢复

**Status**: Decided (2026-09-28)

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

**Decision**:

### 1. 否决资格护栏（trigger 与 router 同律）

一个方向（配方 / 切法 / 产物形态）的否决理由，**永不建立在已交付能力直接处理的素材性状之上**。适用面 = 一切 agent 言语中的方向评判：trigger verdict、plan 提案散文、能力问答、ask_user 的 framing。护栏语义（prompt 面表述走 FREE PHRASING，措辞不抄本句）：不能说「固定全景所以不适合重剪」——分镜工具就是干这个的；可以说「单人固定机位，分镜跟人收益不大，全幅更稳」——否决依据必须是能力**边界外**的真约束。

### 2. 访谈形态的分镜呈现律——说得出来、选了能成

**方向说出律**：素材判型为访谈/对话形态（`speaker_map.form == "interview"` 或 understand 产物同等识别）时，分镜（镜头跟人）是该素材的**活方向**——trigger 首读 / 想法问答 / plan 提案都应能把分镜方向说出口（可作 suggestion dock 的选项），永不以素材性状否决（§1）。

**选择执行律（必含）**：用户选定分镜方向后（点选 suggestion 或口头指明），plan path 组链**必含 `select_clips + reframe_clip`**——选了就要像配方卡那样成片，执行不打折。用户未指明方向且诉求为竖屏短片时，plan path 二选一：组合进链，或 ask_user 提出明确 framing choice（全幅切片 vs 分镜跟人，一词可答，默认路径恒带）。静默中央裁剪永禁。判型证据缺席（无 speaker_map）时不阻塞——按现有默认走，护栏只在证据在场时生效。

**确定性静默补链否决**：「访谈 + 竖屏即自动插入 reframe、不问不说」的确定性补链方案被否——方向必须经 agent 说出、用户选择，选择面不收缩。确定性兜底（只认用户已选的结构化证据）挂账：实测若 LLM 组链仍有漏选，另批评估（届时需 suggestion 选项的结构化指令载荷，属新机制）。

**验证座**：剧本矩阵 S8（访谈→分镜）——访谈素材真处理 → 用户口头选定分镜方向 → 链必含 select_clips + reframe_clip → 成片 render_spec 带 crop_track。

### 3. prompt 面修正（prompt authoring law：现在时法律，零引号例句）

trigger beat ① 的引号示例判句整删，替换为 §1 护栏的抽象表述；router plan 面补 §2 的分镜组合律。模型面文本永不含日期 / ADR 编号 / 事故叙事。两处改动同属 prompt 面，过 prompt_gate。

### 4. 能力菜单措辞升格

`_MENU_PHRASES` 的 reframe_clip 行从画幅机械语言升格为语义语言（智能分镜 / 镜头跟人），注册表文案 en/zh 同改；能力问答面由此能说出分镜能力。

**Consequences**: 访谈素材静默中央裁剪的结构通路关闭；agent 方向评判获得诚实性约束；想法回合说得出分镜、用户选定后链必含分镜；能力问答能说出分镜。零 schema / 零工具改动——reframe_clip 工具不动，动的全是选择律与措辞面。验证 = prompt_gate + 剧本矩阵 S8（分镜必含座）与相关座回归 + 访谈素材 live e2e（验收 = 想法回合说得出分镜方向、选定后同素材产出分镜成片）。

**Related**: ADR-058（展示文案二源律）/ ADR-089（能力编译与执行边界——能力清单是编译事实，选择律在本条）/ prompt authoring law（CLAUDE.md Testing 节）/ RECIPES §4.8（配方准入——分镜能力的用户面承诺）

## ADR-095: 消息流三寄存器律——言语 / 活动日志 / 瞬态状态 + 素材节拍归位

**Status**: Decided (2026-09-28)；讨论底座 = Claude Code / Codex 顶级 agent 三寄存器解剖对照

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

**Related**: ADR-093（根律——本 ADR 是其 §3 准入门的寄存器细化）/ ADR-058（展示文案二源律）/ ADR-087 §3（活动投影——日志面的另一族）/ CHAT_ARCH §8.6（前端渲染律）§8.7（RunTaskList 状态行）

## ADR-096: 渲染所有权与就绪语义——运行期仲裁废止，编译静态所有权 + 就绪对账

**Status**: Decided (2026-09-30)；§1 终态律（编译静态所有权 + 屏障 + defer 律整条删除）、§4 就绪双职责、§5 track 原子写已落地；§6 恢复流程（批次 B）挂账

**Decision**:

### 1. 所有权 = 编译期声明（终态律）

编译器静态指定每份 output 的唯一 render owner（通常 = 装配站）；其余 morph 不 re-pend、不建 render step；owner 的 render step 以 inputs 屏障等待同产物全部并行写入者完工后出生——owner 渲染恒读全量新 spec，死渲染在并行链上结构性消灭。「最后写入者拥有」由编译序静态兑现；运行期只剩执行与验证，不再仲裁。defer 律随本条落地**整条删除**（不是改判定）。

### 2. 过渡律退役

§1 落地后运行期不存在任何所有权推断机制——defer 律整条删除，无过渡分支残留。**立即批与终态批不得同时对同一产物生效**——两套所有权机制并存即新竞态源（本条禁律恒有效）。

### 3. token 守卫不动

claim token CAS（跨 run / 崩溃恢复 / 在飞渲染隔离）原样承重；worker 认领机制零改动。token 管 worker 认领隔离，所有权管内容版本归属——两概念不合并。

### 4. 就绪语义（双职责）

- **verify 拒错误完工（两态判负 + 三态弃权）**：verify 与渲染赛跑是设计形态（verify inputs = 执行器+morph 链，render step 走渲染链认领——verify 恒在渲染在飞时执行），字面「非 COMPLETED 即负」会把每个健康 run 弹回生成器。故判负只取两态矛盾：**render_status NULL 且无文件**（所有权洞）与 **COMPLETED 且无文件**（终态矛盾）——走既有 fidelity bounce / needs_human 出路；pending / rendering / failed **弃权**（在飞无确定性依据不判决；FAILED 由渲染镜像与 render_failed gap 诚实呈现，双门只会为渲染故障误弹生成器）。`run_review` 同律收紧：payload-complete/files-empty 等未交付行不计 delivered，不进 `landed` 提示词行或 Chat 产物卡；按实际状态携带 `output_not_ready:<type>` / `render_failed:<type>` gap，并由 `delivery=failed|partial` 选择诚实的交付分支。
- **finalize reconcile 修遗漏**：run 收尾（verdict 之前）幂等扫描**本 run** 产物中「有 render_spec 但 render_status=NULL 且**未归档**且无 pending render step（跨 run 防御——他者已认领的渲染永不双重拥有）」者并 re-pend。归档排除是承重谓词：claim 门永不拾 archived 行，re-pend 归档产物 = pend 一个无 worker 认领的渲染，run 永远开着。reconcile 是修复机制，永不成正常路径依赖。
- **run 完工 ≠ 产物就绪**：就绪 = 执行终态 + 文件有效 + 版本对账三合取。用户面完工语义随 ADR-097 §5 唯一化为 artifact readiness；「payload 完工即播报成功」永禁。

### 5. 并发 spec 写入同族纪律（track 原子写）

in-place morph 的 spec 写 = output 行锁内 **track 级局部更新**（track 注册表为写入权限依据）+ 合并后 ClipSpec 全量重校验；禁「应用层读快照 → 整体写回」（并发兄弟 track 丢失更新同源于整包写回）。同 track 并发写显式拒绝或串行化。

### 6. 生产数据恢复纪律（判例）

恢复走可审计/可验证/可回滚路径：前置条件核实（目标行归属与归档态 / spec 全量性 / 无有效 pending·running step / 文件无效且无有效在飞 token / 不触发重复扣费或重复建任务）→ 事务内带状态条件的更新 + 影响行数断言 → 经既有 fan_out/enqueue 建任务 → 认领/完工/文件/状态一致性确认。禁裸 SQL 状态改写。

**Consequences**: 黑卡死终态绝源（所有权不再有落空路径；reconcile 兜残余）；「已被新的渲染取代」退为瞬态行（后必有新渲染）；完工消息必须只陈述真实文件与版本；变体并行律不动（并行合法照旧，所有权不再靠它猜）。当前实现只保留确定性所有权与 reconcile；不得重新引入 defer/终态双机制。

**Related**: ADR-079（token 认领守卫——跨 run 隔离原样承重）/ ADR-086（Product Graph——编译期事实源同族纪律）/ ADR-097（artifact 本体——就绪语义的用户面唯一化 + artifact owner 与 render owner 对齐）/ ADR-091（work/version——版本对账的身份地基）/ ADR-074②（渲染台账）

## ADR-097: Product Artifact Ontology——Artifact-first 持久产品图（编译期身份分组，零第二套 DAG）

**Status**: Decided (2026-09-30)；目标架构——Phase 1（canonical JSONB stamp + 读面投影）已拍板，Phase 2（schema 身份表）随 Phase 1 验证后启动

**Decision**:

### 1. 分层与唯一事实源

```text
Work（一次确认的交付意图）
  └── Artifact（用户交付物身份）
        ├── facet（实现面：选段/装配等工序站降格）
        ├── companion（用户可编辑工件：翻译表等）
        └── Version（生产历史，ADR-091 语义）
              └── Output（物化结果）
                    └── Execution Steps（执行真相，永不上画布）
```

Artifact ≠ 第二套 DAG：分组不产新边、不改 rank、不改依赖；它只是 Product Graph 之上的身份层与投影层。

### 2. 第一承重条款——归属只认编译 stamp

- **三身份分离**：`work_key` = 一次确认交付意图的身份；`artifact_key` = 交付物身份（编译器分配，同一交付物的全部相关节点显式携带）；`fill_key` = 节点自身的幂等复用指纹，**永不作交付物身份**。
- **读层永禁推断** artifact 成员——禁从 rank / 邻接 / step 序 / 深度 / created_at / output 归属 / 尾位 / 相同 output_ids / fill_key 相似性推断。
- **legacy 行无 key = legacy/unknown**，走既有兼容读面；**宁可显示 legacy，永不猜一个 artifact**。
- **名与身份分离**：`work_name` / `artifact_name` = 展示事实（ADR-058 二源律，LLM 建图命名）；key = 身份事实。两者永不混用。

### 3. 两层门——产品资格 × 表面角色

- 第一层（不动）：`is_product_node`（ADR-086）——LEVER_TOOLS 保持 modifier 专用，**不吞 facet**。
- 第二层（新增）：`artifact_role ∈ {deliverable, facet, companion, reference}`——「是不是产品对象」与「以哪种用户表面出现」是两个问题。
- 中间工序站（select_clips 等）降 **facet**：不是隐藏（产品资格保留，状态/程序可查），是不再冒充独立交付物。翻译文档等用户可编辑内容 = **companion** 一等对象。

### 4. 投影三律（M2 / M3 / tail-wins 收编）

- **M2 默认投影**：交付物卡 = artifact 的用户表面（当前 version + facet 摘要 + companion 链接）。
- **M3 Activity Overlay**：每 artifact 单一 activity owner；运行时卡携活动态（工序进展聚合），失败才展开工序级定位；运行态与完工态是同一图的两个投影，**禁两套拓扑**。
- **tail-wins 终态律废止**：「一 output 一展示归属」规则作为 Phase-1 投影机制存活，但归属由 artifact 身份直接回答，不再由 rank/尾位推断。

### 5. 就绪语义

目标态 artifact readiness = 唯一用户完工语义（planned / making / ready / failed / needs_attention）；`run completed ≠ artifact ready`（三合取见 ADR-096 §4）。**Phase 1 未完整落地前，当前交付仍由 ADR-074/141 的 delivered/partial/failed 与真实文件判定**，不得伪造 artifact readiness 字段或假装该状态机已存在。

### 6. 迟晋升（late promotion）

中间对象默认 facet/reference；获得独立用户语义（被点名复用，如「就用刚才那段再出法语版」）才晋升 artifact。同一 source selection 的多交付物**共享引用、各自独立编辑**（same source ≠ same editable product）。

### 7. 修订不变量

- 同意图修改（「字幕换法语」）→ 同 artifact 新 version；
- 交付变体（「再来一条德语版」）→ 同 work 兄弟 artifact；
- 新目标（「再做张海报」）→ 新 work。
- version 语义沿用 ADR-091（归档不删除）；**logical version ≠ output 行**——output = 物化载体（preview / attempt / final 可多个），version 是用户语义层。

### 8. Phase 1 / Phase 2 边界

- **Phase 1（零 schema）**：canonical JSONB 字段 `spec.work_key` / `spec.artifact_key` / `spec.artifact_name` / `spec.artifact_role` + 读面投影。字段按未来列设计——**单一 canonical 命名，禁别名垃圾场**。
- **Phase 2（schema）**：`product_artifact(id, work_id, name, current_version_id)` + `artifact_version(id, artifact_id, output_id, version_number, status)`；output 退位为纯物化结果。Phase 2 只搬 canonical 字段语义，不重定义。

### 9. 岛 / 相机 / lineage

- 岛单位 = **artifact sibling set**（一问 N 交付物仍生 N 兄弟卡；廊道/簇适应保留）；append-only 帧律不动。
- **折叠 ≠ 血缘删除**：真实产品 lineage 可以保留，但新图不创建 transcript 节点或 transcript→consumer 合成边。**lineage/display-only 边永不参与 rank、stale/invalidation 闭包或执行调度**；资产 transcript 编辑与下游失效必须按显式依赖语义处理，不能靠假边推断。调度事实源恒为 run 内编译的 step inputs。

### 10. 负向测试（强制）

- 改 rank / 边序 / created_at / 共享 output / fill_key 相似 → artifact 成员不变；
- 无 key 节点 → 不被猜进任何 artifact；
- 改资产 `edited_transcript` → 不创建图边，也不因假 lineage 使下游字幕失效；
- 一 live output 在项目视图内至多一张交付物卡（fork 兄弟不互相吞并）。

**Consequences**: 「一次请求一个东西」的用户心智与「全程可检查/可编辑/可计费/可恢复」的工程面同时成立。批次映射 = A/B 照旧（ADR-096 立即批 + 恢复流程）、C 重定义为本 ADR Phase-1 投影（原 tail-wins 读面折叠案废止并入）、D/E 照旧（执行层）、F 收窄为 artifact 级 lineage（§9）。

**Related**: ADR-086（Product Graph 地基——本 ADR 只补身份层）/ ADR-091（work/version——artifact = work 的图层正式身份分组，version 语义沿用）/ ADR-096（渲染所有权与就绪）/ ADR-088（北极星——用户可理解产物）/ ADR-058（命名二源律）/ ADR-087（Lifecycle 合同——readiness 戳座位）

## ADR-098: 画布拓扑时间一致性——单一 effective rank 与 settled freeze

**Status**: Decided；当前验收 = `VERIFICATION.md`，transcript 边界 = ADR-113。

**Decision**:
1. **一个 effective Product Graph / rank authority**：写时岛/帧分配与读时 `display_ranks` 使用同一纯拓扑层；服务端与客户端 settled projection 对同一 fixture 得同数。前端不得另算第二套 depth/rank。
2. effective/display 层只读，不落库、不进入 RunOp 闭包、stale 传播、工作流编译或 worker 认领。执行拓扑只认 run 内编译事实。
3. **ADR-113 重基线**：新图没有 transcript 节点，也没有 synthetic transcript→consumer 边。transcript 是 asset 内容；不得为恢复三列阅读法重新引入 transcript 特判或合成拓扑。
4. legacy transcript 节点/边只允许在迁移和明确的读兼容层处理：先保存 `edited_text` 到 asset overlay，再删除 legacy 节点/边。兼容逻辑不得成为新图目标。
5. rank 只消费真实生产/消费语义边；lineage/ctx/historical/presentation-only 不参与 rank，也不占合法 rank 边的去重位置。自环排除，append-only 成员顺序确定。
6. **settled rank freeze**：rank-relevant 的 video/audio/text 边 connect/disconnect 到非 draft 目标必须拒绝；ctx/lineage 只按明确豁免处理。`graph_fill` 对账使用同一谓词，内部操作无额外豁免。
7. 显式 lifecycle reflow（如素材删除）可让幸存消费者 rank 下降并左移，这是具名后果，不是随机布局回归。
8. legacy 混合岛按 effective rank 拆 cohort；单成员 cohort 不下发 corridor/island/reserved_bottom。只读归一，不用裸 SQL 重写存储帧。

**Related**: ADR-057/062/079/082/086/097/113；`app/pipeline/product_graph.py`。

## ADR-099: Agent 交互架构——世界事实、决策、言语与代码守卫

**Status**: Decided；固定选项唯一座位 = ADR-100，trigger-only 建议合同 = CHAT_ARCHITECTURE §8.5/§8.8，剩余验收 = VERIFICATION §4.1。

**Decision**:
1. **四层边界**：World Truth 由代码与世界状态盖章；Decision 由 LLM 在结构化产品语义形态中选择；Speech 由 LLM 自由表达；Code Guard 独立校验付费、权限、删除、参数和版本。工具观察只携带世界事实与法条座位，不携带可转述的言语草稿。
2. 高熵、强上下文、可恢复的言语判断可交给模型；状态转换、跨回合一致性、不可逆副作用、成本与承诺必须由结构化契约和代码守卫决定。
3. **终态形态封闭**：`answer` = 纯信息；`ask_user` = 固定选择/阻塞问；`present_plan` 与 revision/proposal 族 = 呈现当前方案并由系统决定后续授权。`answer+suggestions` 不再是合法形态；trigger 的 `wrap_up` 建议只走 dock 机器。
4. 新内容、新措辞不新增 lane；只有新的用户承诺语义才可评新形态。能由 schema/state/code 表达的规则不得塞进 prompt 宪法。
5. 交互宪法只保留跨场景原则：判断给理由但用户决定；内部机械不成言语；世界先于言语；默认值吸收低-risk 细节；不发明用户未说的事实；朴素同语言。
6. 默认值是否可吸收看 reversibility / risk / surprise / commitment / cost；公开发布、权限、删除、高成本与覆盖资产不能因“有默认”而静默执行。
7. **Speech Commit Protocol** 与 ADR-034 同法：终态依赖的帧接受后才可见，拒绝零预览；live tool 活动仍服务 liveness；checkpoint flush 不解除 armed。禁第二 speech router、token 分类、模型自报状态和 NLP 对账。
8. 建议/选项的 provenance 只服务真实 trigger dock；历史 answer 的 suggestions 不恢复。过期候选不得静默采用，用户当前明确指令恒胜。

**Related**: ADR-052/058/060/077/087/089/093/100/108/109/117/139。

## ADR-100: 选项唯一座位——消息流零选项，固定选项全归 dock（ADR-081 恢复全强度）

**Status**: Decided；现行规则归 CHAT_ARCHITECTURE §8.5/§8.8；实现差异与剩余验收归 VERIFICATION.md §4.1

**Decision**:

1. **选项唯一座位律**：系统给出的一切可点选项走 OptionDock（ask_user 选项问 / trigger wrap_up 建议 dock，同一机器）；**消息流零选项**——任何形态的可点选项永不渲染在消息流里。交互语法回到二态：信息 = 散文；选择 = dock。
2. **answer 回归纯信息**：删 `suggestions` 参数（plan path / chat path 两份工具契约同步），散文即全部答复。浏览问与「下一步方向」的家 = ask_user：选项 + 推荐标记 + default_path + ×/铅笔退出面——「建议」由措辞承载，不由形态承载。
3. **拆除面 = answer+suggestions 形态专属**：两份 answer 契约的 `suggestions` 参数与 catalog 描述、plan/propose 两 turn 的 answer 路径 stamp、prompt 面两处契约段（intent_router_system / chat_intent_system）、前端 suggestionOptions 渲染块与点选链路。**trigger 建议 dock 全机器原样保留**（wrap_up 的 SuggestionItem 校验、trigger 行 stamp、answer endpoint 的 ref 代码重构、落地解算与 stale note）——它是真问题结算机器的一部分，不是本 ADR 的对象。
4. **存量读容忍**：`messages.suggestions` / `messages.suggestion_ref` 列保留（trigger 路径照常写入；answer 路径停写），不清洗、不迁移；历史 answer 行的建议块不再渲染卡片，散文保留。
5. **谱系收敛三档**：`answer`（纯信息）/ `ask_user`（必选·阻塞）/ `present_plan`（确认·阻塞·形成方案）；revision 族与谱系封闭律不变（新内容不加形态，新用户承诺语义才考虑且必须 ADR）。

**Consequences**: 交互语法收敛为二态，「这个选项是阻塞问还是可忽略建议」的辨认负担消亡；answer/ask_user 路由灰区消失（有选项 = ask_user，无第二座位）；需求池「建议卡发射率」行的观测对象随之消亡（substrate 先查方法与路由安全零容忍断言迁移为 browse→ask_user 探针）；浏览问的代价 = 多一次点选或 ×，换来全站选择语法唯一。否决备查：① 保留建议卡作「非阻塞轻建议」（被否——视觉不可区分 + dock 退出面已齐备，Context ①③）；② 给建议卡换一套视觉与 dock 区分（被否——形态增殖治标不治本，语法混乱的根不除）；③ suggestions 塞进 mentions（ADR-099 已否，不重开）。

**Related**: ADR-081（选项语法统一律——本条恢复其全强度）/ ADR-099（§2 suggestions 行 / §3 / §4 answer 面被本条翻案，其余各节不动）/ ADR-053 R1（选项问阻塞形态律）/ ADR-070（确认拍回座 dock——本条是「dock 是固定选择唯一座位」的完全化）

## ADR-102: 素材理解 = 回合内前提条件——能力声明 + 休眠素材 + 工具级终态等待（ADR-101 翻案，场景消除）

**Status**: Decided；现行行为归 CHAT_ARCHITECTURE §3.5；剩余验收归 VERIFICATION.md §4.3

**Decision**:

1. **上传 = 纯存储（休眠素材）**：素材创建即休眠——`processing_requested_at` 可空时间戳默认 NULL，worker 认领口加非空条件。被丢弃 / 被围观 / 被冷落的素材处理成本恒为零。
2. **能力声明驱动路径**：`ProviderCapabilities` 增 `understands_video_audio`（ADR-077 判词④声明位；M3 = False）。声明在装配期被代码确定性读取——永不由模型决策，永不是事后补救。具备音轨理解的 provider（未来接 Gemini 类）= 改一行注册表，路径自动换。
3. **worker 事件的唯一创建点 = 模型的读企图**：`get_understanding` 的 pending 分支——素材未就绪且 provider 不具备音轨理解 → **此刻才**盖章 `processing_requested_at` 入队 → 工具内等待到**终态**（理解行落地 or 素材全失败提前出，**无时间上限**——H1 的 240s 上界与 300s 礼貌窗耦合随 trigger 素材路径一起消失）→ 观察只有两种：内容 / 失败事实。寒暄 / 能力问 / 聊别的 = 永不创建任何 worker 事件（没东西要跑）。
4. **逻辑阻塞、零接力、单 writer 由构造保证**：需要素材的回合在工具处等待，同回合同一条消息给出真答案。`understanding_warmed` trigger 路径整族删除（fire 点 / `_already_spoke` / consumed 戳 / 复读禁止律 / 300s 礼貌窗 / trigger prompt 素材段）——屏幕上永远只有用户发起的那一个回合在说话，竞态、轮转、消息打架失去存在前提。
5. **帧诚实三态**：active「正在查看视频内容…」（全程 active，等待期 SSE 帧心跳保活防代理掐线）→「已理解素材 · Ns」（真实时长）/「素材没能读出来」（失败 + 同回合诚实失败话）。
6. **生产链不受影响**：ASR / speaker_map / prosody 链保留；开工入口兜底盖章（付费执行的前提条件，与对话无关）。ADR-024 词级时间戳硬前提是渲染前提，不是对话前提。
7. **ADR-101 的永久继承**：承诺机器（`material_pending` 族）退役维持不复活；打字机律 drain 终态（596ad3a）不变。ADR-101 其余各条（有界等待 / 地板子句 / review 接力 / consumed 戳）随本条翻案，代码整族删除，死亡清单 = 施工合同。

**Consequences**: 「素材处理中提问」从四层机器（等待上限 + 地板 + 接力 + 防复读）变为「等终态 + 一个答案」；`chat.material_wait_secs` 运营参数删除（等待无上限，无参数可调）。代价 = 首次读素材的回合时长 = 本地 ASR 实际时长（CPU whisper 分钟级——加速旋钮 GPU / 云 ASR 是运营层另案，不在本条）。已知边界（在册）：对话阶段模型对素材的理解是语义级（无时间码），「把第 2 分钟剪出来」类精确引用由开工后的 ASR 时间码校准。否决备查：① 云 ASR 替代本地（被否——自托管 / GDPR 叙事不动；加速属运营层另案）；② 视频直发多模态（被否——spike 实证 M3 无音轨理解 + token 60× 且不可缓存）；③ send 入口预盖章起跑（被否——寒暄回合不该创建任何 worker 事件）；④ 保留接力做「我看了」惊喜时刻（被否——UI 阻塞心智下第二 writer = 消息打架根源）。

**Related**: ADR-101（本条翻案——仅承诺机器退役与打字机 drain 两件继承，余者全删）/ ADR-077（能力声明位）/ ADR-024（词级时间戳 = 渲染前提）/ ADR-055（`chat.material_wait_secs` 删除——等待无上限，无运营参数）/ ADR-092（口头确认律——开工盖章点的语义不变）

## ADR-103: 默认路径散文零宣告（ADR-052 判词 5 翻案）

**Status**: Decided (2026-10-05)

**Decision**:

1. **散文零宣告**：提问法条三处（`_asking_strategy` ③ + 两份 intent 契约的 ask_user 段）删去「散文命名不答后果」的要求——`default_path` 只骑机器参数；散文 = 认领 + 理由，问题是唯一收尾。
2. **默认路径零可见面**：「不答会怎样」既不出口也不上卡——推荐项的「· 推荐」标记已承载 agent 的倾向，× 承担跳过手势（09-04「dock 无 default-path 行」拍板复位；卡底 meta 行的可见面方案经 live 走查判画蛇添足，取消）。
3. **机制面不动**：× = bail 走默认路径、提醒尾消费 `default_path` 原文、`pending_disposition` 枚举、intent 上下文 pending 块全部保留。

**Consequences**: 提问与 present_plan 均不要求散文宣告 default_path；`default_path` 继续服务 ×/bail 与提醒尾，推荐倾向由真实选项和 dock 表达。ADR-052 判词 6 已按同一规则更新，无遗留第二套计划卡声明。

**Related**: ADR-052（判词 5 可见面被本条翻案）/ ADR-058（展示文案二源律——本条的原理层）/ ADR-053 R1（选项问阻塞形态律）

## ADR-104: read 言语回归自然 SPEECH 律——等待可读，但不预写方案

**Status**: Decided；checkpoint 通用路由由 ADR-109 更新，数组排序由 ADR-108 决定。

**Decision**:
1. 删除“read 一律静默”。模型在读前/读后按 SPEECH 律决定是否有用户价值的话；读操作本身不禁止言语，也不要求逐调用旁白。
2. 非终态读调用前若已有非空散文且参数校验通过，可在 execute 前形成 checkpoint；其持久化位置先于读活动。当前资格不再使用 `checkpoint_eligible` 白名单，任何非终态工具同法。
3. 素材仍处理中时，读前只能说真实服务员话：已收到、将去读取、可能需要等待。**不得在读完前给方案、内容判断或方向建议**；没有内容证据时不编造。
4. 等待读在同一工具内等到 ready/failed，活动显示真实执行跨度。checkpoint、活动与终答的顺序由 `messages.seq` 和数组 reducer 决定，不再使用 walk key、`settle_at-duration_ms` 或 name_known 时间戳重锚。
5. 终态工具仍需非空合法散文的护栏按当前 schema/loop 执行；空散文修复是兜底，不得借此恢复“每次 read 都说话”的机械节奏。
6. 观测看答复质量与真实等待，不以 checkpoint 数量为目标。零 checkpoint 的单读直出合法。

**Related**: ADR-084/085/093/099/102/108/109/110；`docs/CHAT_ARCHITECTURE.md` §8。


## ADR-106: 素材形态 = 本地聚合判定 + LLM 语义——speaker_map 判定层定型与剪辑复用座

**Status**: Decided (2026-10-06)

**Decision**:

1. **人数 = 本地聚合多数决**：`_people_count_by_majority` 按 2s stride 逐帧 YuNet 数脸，众数 + 严格过半（>50% 有人帧）胜出；空镜帧不稀释；3+ 折叠一桶；无多数 = unknown 诚实收场。零脸时沿 bootstrap 先例升级检测档（640 → native → tiles）再判，防小脸/远脸/口罩误判。
2. **LLM 只保留语义轴**：M3 网格只判 scene（interview/presentation/other），`people` 字段从 prompt 与 schema 整族删除（数人数不是 LLM 的活）。测量任务归测量工具，语义判断归 LLM——两轴各配其器。
3. **仲裁并行化**：`_arbitrate` 的 cap-5 歧义段裁决改 `asyncio.gather` 并发（段间零依赖，串行纯属保守）；仲裁并发必须保持有界，且不改变每段裁决语义。
4. **剪辑复用座**：① interview 的左右槽位锚点（cx/cy/w/n）随 speaker_map 持久化，reframe 的 interview_switch 直接读取、砍掉每 clip 的全片重扫（旧 map 无锚点回退 bootstrap）；② gate 扫描落 `meta.face_scan` digest（counts[] + majority/share + 派生 `face_free_spans` 空镜段 / `extra_people_spans` 观众段），chat 感知层据此加一条 footage-scan 事实行（cutaway/B-roll 候选数）——一次扫描同时喂形态判定与下游分镜原料。

**Consequences**: 访谈误判 multi 的一类 flake 结构性消失（本地计数确定性 + 聚合抗干扰）；纯 PPT/无脸片零脸升级后仍 unknown，诚实不冤枉。明确不做（过度设计防线）：shot boundary 检测是独立工序后补；8fps 帧级轨迹不落库（体积大、消费方不明）；reframe 切点逐帧精检保留自有 pass（2s 粗轨给锚点够用、给切点精度不够）。确定性回归 = `tests/test_speaker_map_pure.py`（多数决/span 推导 13 例）。

**Related**: ADR-045（D3/D4 的判定层被本条定型，仲裁 cap 与能量归属机制不动）/ ADR-102（理解读链——face_scan 事实行经 `speaker_form_lines` 注入同一座位）

## ADR-107: 候选证据 = range 提案 + 服务端派生摘录——verbatim 门退役，锚点全文随理解读（ADR-088 §4 证据门翻案）

**Status**: Decided (2026-10-06)

**Decision**:

1. **模型只提案 range**：CandidateMember 的模型输入面收窄为 `CandidateRange`（start/end/speaker）；excerpt 从工具 schema 删除（extra=forbid 同步拦住模型手打）。
2. **excerpt 服务端派生**：门校验通过后用 `derive_excerpt`（words_in_range + 400 字截断带诚实省略号）从 range 自身语音派生，先于 idem key 计算（重放键与请求散文无关）；持久化 spec 形态不变（members 仍带 excerpt），SSE candidate 帧与 CandidateSurface 卡片零改动。C4 锚链反而加强：卡片展示的引文保证是 range 实际语音，不再是模型挑的漂亮话。
3. **门校验收窄为 range  sanity**：start < end、end ≤ duration、range 内有语音（落在停顿里 = 无证据，拒）。verbatim 校验与 normalize_evidence 整族删除。
4. **锚点全文随理解读**：`_render_understanding` 对每个 timeline-ready 资产追加 `build_anchored_transcript` 全文（[start-end] 行，per-asset ≤8000 chars 内联，超出诚实指路 search_transcript/get_segment），header 带 asset_id（复用 search header 的 live-gate 教训）。短中素材的发现链不再需要 search 往返：get_understanding → propose_candidates 两步到位。search_transcript/get_segment 降为长素材专用路径。

**Consequences**: excerpt 由 range 的真实语音派生，模型不再抛光证据；range 合法性仍由确定性门与候选卡审查承担。**已知边界**：长素材 `search_cues` 的子串匹配对按单字 token 化的 CJK 仍可能大量 miss，需统一 normalization 后用真实中文长素材验收；该开放项归 `tasks/agent-working-loop-iter-3.md`，不得当作已覆盖。

**Related**: ADR-088（§2 traceable 含义从「模型自证」翻为「服务端派生」——加强而非放松；§4 证据门收窄）/ ADR-102（理解读链——锚点全文注入同一座位）/ ADR-089（付费执行只从已确认范围开始——确认范围的证据现在由服务端保真）

## ADR-108: Transcript 数组化——持久化顺序即渲染顺序，运行时交织计算整层退役

**Status**: Decided (2026-10-07)

**Decision**:

1. **会话级单调 `seq`**：`messages` 使用 per-conversation 单调序号，**允许间隙，不要求连续**。**渲染序 = seq 序**；时间戳只用于显示（耗时、时刻），永不参与排序。新 conversation 首回合的 seq 必须在写入父用户行的同一未提交事务中分配，避免父行尚未可见时派生回合提前提交；后续活动/散文行回到独立短事务。
2. **一切可视元素 = 数组一行**：user / assistant 散文 / checkpoint / **activity（每帧一行）** / candidates / question dock。activity 行在 **open 时刻 append**（`at` = execute 入口，诚实开工时刻），settle/failed/cancelled **原地 update 同一行**（填 `duration_ms` 与终态）——行位置 = 工作开始的位置，正是 walk key 想模拟而模拟不好的东西。每回合聚合的 activity_log 消息形态退役（渲染面整删；取证由 activity 行自身承担）。
3. **SSE 镜像数组操作**：`row.append` / `row.update` / `row.delta`（散文增量）/ `row.settle`。live 消费与历史回放**共用同一 reducer 同一渲染函数**——回放 = `ORDER BY seq` 直渲，双路径不一致这一整类 bug 灭种。
4. **退役清单**：walk key（`settle_at − duration_ms` 推导）、last-wins latestLog 回放、`logDismissed` 闩、once-only per ref 去重、finalizePreview 服务端钟重锚跳位。散文气泡行在首 delta 到达时 append（内容空、delta 流 update、settle 原地 finalize），位置从此固定。
5. **失败/中止回合的行照常落库**（failed/cancelled 态随行进 transcript）——诚实 transcript；回合失败不再抹掉工作证据。
6. **折叠渲染 = 呈现层纯函数**：用户可见散文 / user / QA 边界之间的连续 completed / active activity 行属于同一工作段（现行法 = ADR-110 段聚合——折叠说总量、展开为类目分解；active 只承担 live 座位，completed 才进入明细）；当前未收口段由同一个 `WorkSegmentRow` 原位承载瞬态「正在做什么」，首显或真实终态后转成工作记录。cancelled 尝试仍落库供审计，但从可见投影退役；真实 failed 行保留。折叠只动渲染，不动数组。
7. **迁移**：一次性脚本把存量 activity_log 帧按帧时刻物化为行序插 seq；物化不了的旧回合接受活动行缺失（greenfield 验收口径先例），散文/checkpoint 行按 created_at 回填 seq。

**Consequences**: 【已完成理解】消失类、顺序跳位类、live/回放不一致类 bug 结构性不可能再发生——它们要解决的问题不再存在。打字机律两牙不动（散文字段读容忍 + settle 散文 drain 节拍释放：零 delta 回合的散文行 append 时点 = 信封到达后，内容照节拍放出，位置不受影响）。DB 写入次数略增（activity 每行 open+settle 两写）量级可忽略。旧 walk-key 重锚机制不再使用；checkpoint → 读活动 → 读后回复由数组位置表达。

**Related**: ADR-104（checkpoint 发射座时点）/ ADR-099（DeferredFrames 与数组持久化正交）/ ADR-108 当前迁移合同 `VERIFICATION.md` / ADR-109/110/111。

## ADR-109: 言语座位通用化——checkpoint 无白名单，echo 不指不可见面

**Status**: Decided；持久化顺序 = ADR-108，工作段 = ADR-110。

**Decision**:
1. 任何非终态工具调用，只要模型自带非空散文且参数校验通过，就在校验后、execute 前具备 checkpoint 座位；`checkpoint_eligible` 注册表白名单退役。终态工具散文仍随 envelope 结算。
2. before/after 共用同一座位：上一动作之后、下一动作之前的言语只在时间轴落一次，不新增 after hook 或第二 speech router。
3. `MAX_CHECKPOINTS_PER_TURN=4` 是防啰嗦护栏，不是配额或质量目标；cap 记录遥测，不丢字、不强行制造 checkpoint。
4. 模型可在真实相位转换时给有信息量的预期/小结，但逐调用汇报、CoT、概率、候选腹稿和第二 writer 永禁。
5. docked 计划的 echo 不得指向当前不可见的画布/工作区，不复述卡面已经列出的计划组成；ask 档以朴素方案判断问句收尾，auto 档按当前制作意图与守卫执行。
6. 散文字段、计划参数和空值必须读容忍，避免一次 schema 拒收导致流式蒸发；新增字段仍需满足打字机两牙。

**Related**: ADR-034/060/084/085/092/099/103/104/108/110/111/118。


## ADR-110: 活动行段聚合——散文段间整段坍缩为一条聚合总量行（折叠说总量，展开说分解）

**Status**: Decided (2026-10-08)

**Decision**:

1. **段聚合 + 总量/分解两态**：两个用户可见散文段之间的连续 completed / active 活动行（含单行，跨 key）属于**同一个工作段**；active 只承担 live 座位，completed 才进入工作记录明细，user / QA 切断段。折叠态只说总耗时「工作了 2m 7s」这**一个事实**，永不带 fragment 摘要（`Read www.z…` 的截断病理与宽度抖动是其结构性失败；URL/文件名截断需求随之消失）。展开态 = **类目分解**：同 key 行跨全段合并为一条 ×N 类目行（「已读网页 ×3」——Flora 解剖），按首次出现序（时序即真相）；逐行时长与实例名不归归档面（遥测不归消费面；实例名是 live 期的言语——material 读取族经 `activityCategoryKey` 重映射到无名的 `materialCategory` 键族，web_page 分叉随节拍 `asset_type`）；产物计数里程碑（count 无 total）永不合并——两条行说不出一个诚实的计数。折叠仍是呈现层纯函数（`foldActivityUnits` + `foldCategories` + `WorkSegmentRow`），持久化的每帧一行不动——审计继续读落库行。chevron 全站统一 OS disclosure 惯例（`>` 收 / `⌄` 展）。
2. **工具完成 ≠ 工作段完成**：首条 active 宿主出生即形成当前工作段，前段正文 typing 不得吞掉它的具体 label；当前回合最后一个未收口 fold 是 live 工作段的唯一 owner，在同一时间线单元上承载 Thinking / 当前里程碑。已完成工具只在段内累积，**live 恒无 chevron、不可展开**，底部 now seat 只在尚无该 fold 时承担同一组件。后续正文的**首个非空白字符经打字机实际释放**时，同一单元原位转成工作记录并开放展开，正文显示在其下；首显按 prose `rowId` 只封其前方段，前一条 checkpoint 不得误封其后新段。终态 error 灰行不是后续正文，不能抢在 terminal seal 前关段。无正文的成功 / 失败 / 取消 / 断流等真实终态也收口。SSE 帧到达、keepalive、reasoning、空 delta、已缓冲未显示文本都不是首显；零 delta 的信封补齐仍走同一打字机与首显门。busy 时不得同时出现「工作了 X 秒」与另一条 Thinking，纯对话不得生成空的可展开工具框。sendChat、option / freeform answer、Start 与 conversation / runStream 两条展示路径共用这套语义。
3. **cancelled 退役，failed 留真**：cancelled 表示 attempt 被放弃（自动重试 / 用户停止 / 断连），不是最终失败；它仍落库供审计，但从用户可见投影退役，不留 ✗ / 删除线、不打断折段，也不生成空 Worked。真实 failed 行保留一条安静告警并打断折段，使用终态失败文案而非 active 的「正在…」，永不伪装成成功。模型随后组织解释时，当前工作段可继续显示 Thinking。
4. **时钟与稳定身份分轴**：实时段起点 = 用户发送事实 / QA 实际点击显示事实 / Start 实际点击 / 前段散文排干事实，缺失时回落首条活动的 execute-entry `at`；终点 = 首显或真实终态，写一次冻结在首个宿主行，后续打字不继续累计。宿主行 `birthKey ?? id` 是跨回合身份，per-turn `activity_id` 永不用于跨回合收口或重开。工具 `duration_ms`、正文播放、用户等待确认和后台 run 各有自己的时钟，永不混入。历史回放没有客户端首显事实时只报告首末活动自身可观察的跨度；无墙钟事实显示操作数，**永不求和并行工具时长冒充整段墙钟**。

**Consequences**: 散文段间的活动密度从 N 行降到 1 行，与参照件同形；诚实 transcript 不受损（聚合只是投影，数组行还在）。ADR-108 §6 的「同 kind+key ≥2 才折」条款被本条取代（机制同座，`foldActivityUnits` 一处）。

**Related**: ADR-108（数组位置律与每帧一行不动；§6 折叠条款由本条接替）/ ADR-087 §3（活动流白名单不动——聚合文案只读 key/count/name/at/duration_ms）

## ADR-111: 画布 reveal 与计划呈现——PLAN_READY、当前 Start 门与等待态欠账

**Status**: Decided；W3 等待态节点面、相机夹、capture 前估价面与刷新重建仍欠统一 live 验收。当前授权 = ADR-117/139，Film 首稿 = ADR-144。

**Decision**:
1. **PLAN_READY 是桌面画布 reveal 的必要产品状态**，不再以 hasRuns/confirmed run 作为唯一前提；`workspace_layout=chat` 或移动端仍保持纯 chat。reveal 不得绕过 material/plan readiness。
2. 重型任务清单卡与第二计划编辑面退役；计划的阅读事实是真实草稿图、当前累计方案与 dock echo。`pending_brief/task_book` 继续承担冻结范围、刷新重建、插话与修订锚点。
3. **Start 不是“只能口头”**：ask、守卫线、NULL、awaiting_production 和 Film review hold 可显示真实 dock Start；auto 且已授权可同回合开工。所有 Start 都由服务端 `evaluate_start_gate` 裁决，口头/typed answer/按钮同机。
4. auto 不创造制作意图；无制作请求或“先看看”仍等待。作品首个 Film 分镜版本无论档位和首条命令都必须完整呈现并等待用户批准，不能同回合创建 run。
5. 计划重提/修订继续经同一产品语义工具与 `apply_wiring_ops`；不得因卡面退役绕开版本、scope 或费用守卫。
6. 言语是否能指认画布看**当前 `canvas_visible` 事实与 ADR-118 窄门**，不能仅凭 plan-ready 推断桌面/移动端或用户布局。
7. reveal 首帧可在用户发起的呈现节拍 fit 全貌并使用合理缩放夹；背景 refetch、checkpoint 收官和 routine terminal 不动相机。
8. `get_graph` 只提供计划/关系读法；模型无节点 CRUD，写仍只经唯一图写门。
9. 等待态必须同时回答四件事：节点看起来是就绪而非损坏、capture 前估价可见、刷新后同形、dock/full-panel 与 reveal 联动一致。未验收前不得称 W3 完成。

**Related**: ADR-036/058/087/092/100/109/117/118/122/139/143/144；CHAT_ARCH、BILLING 与 VERIFICATION.md §4.2。

## ADR-112: 画布卡面显示律——cue 行时间刻度 / facet strip 失败-only / factsbar 分面 / Top pick 抉择闸门

**Status**: Decided（2026-10-09 用户拍板，同批落地）

**Decision**:

1. **素材卡转写区 = 读面派生的结构化 cue 行 + hover 显时**：从 asset words 经唯一 `group_cues` 派生，label 由服务端预格式化；cue 不落 graph spec，不恢复 transcript 节点。卡面是干净文字块，编辑只动纯文本 overlay，时间不进入 textarea，也不反算词级时间戳。
2. **纯展示媒体卡 = 干净媒体面**：facet strip 健康名字行退役（成功安静——健康 artifact 零 strip，卡面与输入素材卡同构）；失败行保留（失败才展开工序级定位不变）。frame 预留座位整个拆除（`frame_facets` 停盖 / `_frame_of` 删 +29 / `facetStripPx` 只数失败行）——① 的黑边不打预留同步补丁，靠座位消失结构性归零；失败行运行时由 flex 媒体区吸收（既有律）。
3. **factsbar 模型事实分面**：模型 chips 只上 generator（散文程序）卡——散文产物的模型是写作 provenance；editor/manual（参数程序/纯展示）媒体卡的模型是流水线固定事实，只留 lightbox 详情列（ADR-051 条款 5 详情面陈列不动）。语言/画幅/时长芯片不动（媒体事实）。
4. **Top pick = 抉择闸门**：带分 clip ≥2 同场才有 Top pick 徽章（triage 需要真实抉择）；单条回落裸分（hover 载选段理由，世界自证）。两座镜像（ResultsCanvas 画布徽标 / 结果格 ClipCard）同一规则。
5. **null-token 净化两座**：写口 = `TaskItem` 读容忍丢弃恰为 `"null"`（大小写不论）或纯空白的参数值（精确裸 token 匹配，「提到 null 的正文」永不误伤）；读面 = `OutputResponse.language` 放宽 `str | None` + junk→None 归一（`_derive_aspect` 的 `"original"→None` 同款座位），`compose_spec_prompt` 同一谓词（`is_null_token`）守卫存量 spec。

**Consequences**: 黑边根因座位（facet 预留双路径分叉）整体消失而非修补；计划参数从此外界垃圾不进 spec/prompt/产物列；单条交付物卡面回到「caption + 媒体 + factsbar」的干净三件套。代价：健康工序在卡面零痕迹（工序自证归 chat 逐步叙事与 stepper）；存量 spec.prompt 里的历史 "titles in NULL" 不迁移重写（读面守卫兜住，快照不可篡改律不动）。

**Related**: ADR-097（artifact 投影四字段/两层门不动——本条只退休卡面 strip 的健康行）/ ADR-051 §5（模型事实详情面不动）/ ADR-076（prototype 门控成为 factsbar 分面谓词）/ ADR-109 §5（读容忍扩展到参数值级）/ 打字机律牙①（同族方言吸收）

## ADR-113: Transcript 折叠——素材卡内容层 + 成片轨道栈 + 存储唯一座位

**Status**: Decided；存储迁移与卡面验收 = `docs/VERIFICATION.md`。

**Decision**:

1. **存储唯一座位 = asset 行**：`assets.transcript` / `extracted_text`（真相）+ `assets.meta.words`（证据）+ 新增列 `assets.edited_transcript`（用户编辑 overlay，从 graph spec 搬家；C4 地板不动——永不反算时间码、证据与区间永不被编辑触碰）。graph spec 的 `text` / `cues` / `cued_text` 三件套随转写节点退役拆除。cue **永不落库**：一切展示面（素材卡时间条 / 成片文字轨 / chat search）从 words 经 `group_cues` 读面派生，label 服务端预格式化一法一座（ADR-112 继承）。`transcript ?? extracted_text` 的两种相反 fallback 顺序收编为同一座。
2. **转写节点退役**：新图不再调用 `stamp_transcript_node`，也不创建相关合成边。需要保留旧数据的迁移必须**先把 `edited_text` 完整复制到 `assets.edited_transcript`，再删除 legacy 节点/边**；本轮无用户且已授权reset的环境可重建，不承担旧业务回填；其他保留数据环境未复制不得删除。读兼容只为迁移服务，不是新图目标。编辑写口 = 资产级端点，零 run 零积分语义不变；是否进入 Operation Model 账仍是开放项，归 `VERIFICATION.md`。
3. **素材卡解剖（卡即工作面）**：媒体区（click-to-play poster）+ **时间条**（cue 块宽 ∝ 时长、停顿诚实留白、播放头）+ 纵向 cue 流（hover 显时 chip——ADR-112 继承；定高卡内滚动，560 封顶同 DocumentCard 全文卡律）+ factsbar。点 cue / 条块 = **同卡 seek**（「文本驱动 seek」交互族入册）。paste / transcript 型资产 = 同组件去掉媒体区与时间条（无词轴即无时间面；估算词轴补强挂账）。转写处理态面（shimmer / 失败红行）收回素材卡承担。
4. **成片卡轨道栈（检视，不是编排）**：完整视频（顶）+ **视频轨**（片段块，`render_spec.segments` 读面，源时间映射）+ **文字轨**（字幕句块，`caption_track` 经 `group_cues` 句级——词级是渲染细节不上卡）常驻；修饰轨（音乐 / 配音 / filler 划掉行）有内容才出现。轨道只读 + seek，**永不长拖把手、永不长「添加音轨」**——L3 铁律禁的是编排（合成语义），内容解剖的读视图不违反，形态上必须一眼是读视图。
5. **锚点律修订（端口法则精确化）**：轨道可见时，入边锚 = **所喂轨道左缘 Y-center**（video 边锚视频轨）；锚座位恒为「媒体区正下方第一轨」，轨道栈展开 / 收起锚不跳动；修饰 presence 条骑轨栈**顶**（到来只压媒体 flex，钉死的轨座永不动）。无轨道时现行角律（ADR-067 一族）不变。边保持节点级——边落卡内片段（FLORA 形态）不收，片段级血缘归 §6。
6. **血缘 = hover cross-highlight（数据驱动）**：hover 成片卡片段块 → 素材卡时间条与文本流中被 `segments[].start/end`（源时间）覆盖的区间亮起。片段块携带**源资产 id**（异源拼接段各指其 donor）+ 预格式化源区间标签（前端永不格式化时间）。**画布级共享 hover 态**是新增的合法跨卡通道（唯一一座，禁泛化）；两条装饰 text 边随转写节点退役不再出生，存量边由迁移硬删（不再有读面兼容）。
7. **分界与不做**：多轨编排 / 拖片段 / 加轨 / 转场永禁（L3 不动）；改稿驱动重剪（edited transcript → 词轴对齐 → 影响产出）是 **PLANNED，未实现**；当前编辑只是资产层展示 overlay。时间条拖选区间、paste 资产估算词轴与编辑进入 Operation Model 账均为开放项，触发条件与验收归 `VERIFICATION.md`，不得写成已交付。

**Consequences**: 转写节点整族消失——画布每素材少一列（708px 族结构性不可能），graph refetch 不再搬运全文；cue 从「派生四次 + 白存一份」收敛为「一座派生」；互指成立（点句子跳画面，时间轴从装饰变导航）；血缘从「画的边」变「读的联动」；编辑 overlay 单座位且写口落资产层（语义更正）。代价：素材卡变重（定高内滚吸收）；存量 transcript 节点行迁移删除（edited_text 先搬家）。

**Related**: ADR-086（判词①枚举修订——transcript 移出「可编辑中间工作产品」枚举，改判「素材卡的内容层」）/ ADR-097（transcript 的 companion 身份退役——不再是 artifact，是 asset 的面）/ ADR-112（cue 结构化 + hover 显时 + 服务端预格式化 label 由本条继承并改写座位：spec 落库 → 读面派生）/ ADR-057（零投影——图不再存显示副本，本条是修法正身）/ ADR-067（出锚语义律不动；入锚精确化）/ ADR-016（对应 spec family 不变——轨道栈只是读面投影）/ Workspace 合同 v4.2 C4（双层不变量搬家，永不反算时间码）/ `docs/VIDEO_EDITOR.md` L3（编排永禁）

## ADR-114: 测试体系——用户旅程矩阵与承重防漂移守卫

**Status**: Decided；运行规范与合同映射 = `VERIFICATION.md`。

**Decision**:
1. 只长期保留两类测试资产：**用户主流程全旅程矩阵**与**承重架构防漂移守卫**。事故回归锁、批次产物、死机制与镜像实现形态的锁不作为永久资产。
2. 活 LLM 闸 = `scripts/chat_scenarios.py` 的当前 `SCENARIOS` 注册表；数量与编号以注册表为准，不在 ADR 冻结。SSE 工具 loop 线格式、Activity 帧、dock 形态与估价断言由 harness 公共断言携带。
3. 纯 pytest 只测无需 DB/LLM/HTTP 的纯函数与承重分支；需要真实事务或 LLM 的行为归旅程矩阵。web vitest 保持纯 node 组件旁置套件。
4. `check_gates.py` 是静态架构门；`prompt_gate.py` 只在 prompt 面改动时运行，探针/阈值以当前注册表为准。失败先复跑与归因，**永不为放行回归调阈**。
5. 退役 = 自然死亡：重构使测试锁定的机制消失时逐案删除，不留注释尸体；新覆盖必须能指出属于哪本旅程哪一步或哪条全站铁律。
6. fixture 使用 `scenario/` 前缀，防共享 key 被删除；常驻 worker 抢跑、进程组清理、配额与 round-robin 纪律是运行合同的一部分。
7. 客户端法律（打字机、remount、形态机）不进服务端剧本断言；服务端真值才进。真实浏览器、动态视听与付费/生产路径仍需对应人工或专门验收。
8. 当前已知未覆盖/观察面必须保留：S1/S6f/S10 方差归因、失败不扣费、孤儿 hold、run 执行权、turn durability、SSE reconnect、repair 泄漏。没有自动看护不等于已验收。
9. VERIFICATION.md 是当前验证母文档；harness 代码归位仍为 PLANNED，范围与收集/import验收见该文档 §6。当前脚本路径继续有效，不把文档升格当成代码已搬迁。

**Related**: ADR-039/071/079/089/099/102/108/117/119/141/144；`docs/VERIFICATION.md`。

## ADR-115: 卡面解剖 v4——素材卡阅读型 + 成片卡 NLE 检视轴 + 信息秩三分

**Status**: Decided（2026-10-09 用户拍板；形态原型 = `scratch/media-card-anatomy.html` 信息秩三分定稿，基于项目 1aeb9787 真实数据）；施工合同 = `docs/VERIFICATION.md`

**Decision**:

1. **信息秩三分 = 卡面分层法**：L0 结构层**常驻卡面**（道块 / ports / 徽章 / type 身份 / 阅读型卡的转写稿流——必需信息永不 hover）；L1 补充读数 **hover**（句文本 / 时间戳 / 源区间 / 刻度读数——瞬态不占布局，一座 `HoverChip`：portal 到 `document.body`、`overlay-surface` 冰霜、浮于锚行**上方**永不盖字、pointer-events-none）；L2 深详情**点击**（OutputInspector / lightbox 既有座位）。空间不足的压缩答案 = 折叠成摘要行 + 点击展开（Descript 模式，缓做项），永不是 hover 揭示。
2. **素材卡 = 阅读型一体环**：media + divider + 转写稿区同入一环（媒体不再裸奔）；转写稿区固定解剖（divider 1 + 头 20 + cue 流 150 帽 + pads，预留 236→197 两镜像同批），媒体恢复画幅钉死——frame 数学的预留即舞台，flex-1 只吃预留，不再被均分挤压；object-cover 零黑边，画幅 bucket 兜裁切残差。24px 条码时间条退役 → **3px 舞台检视皮**（cue 段∝ 白纱、播放针、hover 变粗 8px、点击拨头、scrubber 读数入 L1 chip）；时长角标上舞台右下；cue 行时间 chip 上浮行外（ADR-112 hover 显时律继承，座位从行内改行上）；播放中行点亮、血缘区间琥珀（ADR-113 §6 不动）。medialess 素材不渲染空媒体槽（转写稿即卡身）。
3. **成片卡 = NLE 检视轴**：**轴头行**（评分撤下舞台入轴头右端，ADR-112 ③ 裸分与 Top pick 闸门律不变，座位修订；非 tracked 解剖保留舞台徽标）+ **ruler**（服务端预格式化刻度——「客户端永不格式化时间」法条覆盖轴刻度：≤10 主刻度 nice step、次刻度纯几何、`t=0`/`t=total` 恒带标签；点击 seek）+ **34px 视频道**（真剪辑块：primary 填充、多块多源 ∝ 产出轴、块内「片段 N · 源区间」截断、hover = L1 chip（产出/源两区间）+ 血缘琥珀跨卡联动、click 拨头）+ **22px 字幕道**（连续块**零内嵌文字**，句与区间入 hover chip）+ **修饰道**（音乐/配音存在面，居文字道下，内容面后续批）+ **跨道播放针** + 道头 gutter 图标。全部只读 + seek——L3 编排永禁不动（无拖把手 / 无加轨 / 无转场），形态上一眼是读视图。
4. **锚点律推广与节拍**：视频道 Y-center = 视频入 port 锚（ADR-113 §5 不动，公式随新解剖重算——两镜像同批）；修饰道到来 = 产品着陆节拍，锚同拍上移 26px/道（版本分页器先例——一次连贯 reflow，永不悄移；取全版本最大道数防翻页重坐）；修饰道 port 化 = 后续批（随 dub/music 输入资产化落地）。
5. **时间格式化一座的边界**：数据行时间标签 = 服务端预格式化（cue label / 源区间 / 产出区间 / ruler 刻度——`track_stack.py` 一座）；播放器 chrome 读数（检视皮 scrubber「m:ss / m:ss」、时长角标）= `formatDuration` 唯一客户端座（lightbox 播放器同座）——连续几何读数非数据行，豁免成立。

**Consequences**: 两型卡各自成立（素材卡 = 读、成片卡 = 检视）；「track 在哪」结构性回答（道 = 结构常驻 L0，连线落到道上）；血缘 hover 与 NLE 块同构（hover 一块、源区间一片亮）；裸奔/挤压/盖字/条码四症根治；黑边法条（object-cover + bucket）从一卡补丁升为解剖律。代价：帧预留变更（TRACK_STACK 96→NLE_AXIS 116、TRANSCRIPT_SECTION 236→197）——存量帧由 flex 吸收（永不溢出律：媒体让位，contain sliver 回归 legacy/raced 既有条款）；修饰道锚移 = 命名的节拍移位例外（分页器先例）。

**Related**: ADR-113（素材卡内容层 / 轨道栈 / 锚点律 / 血缘通道由本条继承并改解剖）/ ADR-112（cue hover 显时 / 裸分 / Top pick 闸门律不动——评分座位由本条修订）/ ADR-016（对应 spec family 不变——NLE 轴只是读面投影）/ `docs/VIDEO_EDITOR.md` L3（编排永禁不动）/ `docs/UI_GUIDELINES.md`（浮层一律 overlay-surface、视口锚浮层 portal——HoverChip 遵守；in-flow 面零 shadow）

## ADR-116: ask_user 选项数双族律——决断 ≤3 / 探索 ≤5，label 用户语言内容词放行

**Status**: Decided（2026-10-11 用户拍板；取证 = ADR-114 矩阵批 2 复跑 S3/S6 连红——模型在素材丰富的探索回合给 4–5 个各有理由的真实方向，撞 harness 1–3 界；法条缺座位，归用户产品拍板）

**Decision**:

1. **选项数双族律**：决断问 ≤3（真二元抉择降 2，ADR-052 节奏不动）；探索方向问 ≤5（context 持有的真实方向全部可 dock）。prompt 双座镜像承载分族计数（intent_router ask_user 调用律 + chat_intent ask_user 工具描述）；harness 公共断言只守结构外界 1–5——分族节奏是模型裁量面，永不进 harness；S1 slot 问的 0/2–3 断言 = 决断族座，不动。
2. **label 放行用户语言内容词**：label 档 lint 收窄到英文参数方言词（bilingual/source_only/target_only），「双语」等用户语言内容词合法；description 档再收窄一层——字幕模式族只查标识符形（source_only/target_only），散文里的 bilingual 与双语同律放行（description 收窄档既有教义的延伸：证据句合法引用源事实与用户点名的作品词）。
3. **harness 不主张 prompt 没教过的法**：lint/断言与 prompt 法条同座同批检查——prompt 从未教「避开用户说过的词」，harness 就永不罚它。

**Consequences**: 探索回合的模型裁量与 harness 界对齐（S3/S6 类红不再误报）；决断节奏保持三选项；label 回声误判关闭。lint 的存活目标收窄为真 shadow plan 签名（标识符形 / 画幅 / 时长 / 成本 / 条数参数）。

**Related**: ADR-052（决断节奏源）/ ADR-100（选项归 dock + 负形 lint 源）/ ADR-107（锚定转录内联预算——同批 S3 读具裁量取证）/ ADR-114（矩阵施工批内取证）

## ADR-117: 授权前移——两档权限设置与确认教义默认值翻转

**Status**: Decided（2026-10-12 用户拍板；竞品取证 = Pexo / ElevenLabs / Flora 截图走查 + 本产品哲学：用户最希望 agent 在不需要过问的情况下完成所有工作；现行规则 = CHAT_ARCHITECTURE / BILLING；剩余验收 = VERIFICATION.md §4.2）

**Decision**:

### 1. 两档权限设置（users.settings JSONB，默认全 auto）

`confirm_execution ∈ {auto, ask}` / `confirm_credits ∈ {auto, ask}`，缺席与非法值读容忍回 `auto`。理解性提问（`ask_user` 问受众/目的）**不是许可请求**，不在「不询问」射程内。座位 = SettingsDialog「助手」section（权限卡两行 Select），composer / dock 控制条永不再出现确认偏好控件。

### 2. auto 开工道——呈现 + 出生制作意图 = 授权基础

auto + auto（默认）：方案呈现（dock echo + 草稿图 + 任务列表，呈现义务不变）后，非 Film 首稿场景可**同回合 start_run**；作品首个 Film 分镜版本必须先审阅（ADR-144）——「propose 同 turn create_run 全路径禁止」改为档条件（ask 档维持禁止）。**（ADR-139 修订）auto 只免去批准拍，永不创造制作意图**：auto 开工道的放行还要求 dock 出生回合的用户消息携带制作请求（`production_intent` 出生事实）；非 Film 的纯讨论/修改/「先看看」出生的 dock 等待用户的制作话，复用既有确认 dock 形态；Film 分镜设计/修订无当前制作意图时依 ADR-139 §3 完整呈现后 `answer`，不建制作 dock。Confirmed Scope Snapshot 语义不变、授权通道加宽：`confirmed_via` 增 `"auto"` 值（常驻授权），`"explicit"` 为 ask 道；快照是 scope 完整性与重试证明的载体，不再是明示确认的签名。scope classifier 判定（continuation / expansion / unproven）零改动——expansion 的目的地按档分流：ask → dock 等确认；auto → 呈现 + 直跑（守卫线照常把关；非 Film 出生无制作意图 → dock 等待；Film 分镜设计/修订无当前制作意图 → 完整呈现后 `answer`）。

### 3. 内部守卫线（ops 参数，不是用户设置）

configs `billing.always_confirm_above`（默认 5000）：方案 fold high 端越线**或**含 NULL 不可报价节点 → 任何设置下恒带价问一次。start_run 工具路径的阻断回结构化工具结果 `{code:"start.needs_confirm", reason, quote_high}`，模型转呈现带价 dock（NULL 族标「估价随运行确定」），永不静默重试。auto 时代用户的保护栈 = 呈现义务 + 打断权 + 出生地 422 + 失败不扣费 + 本守卫线 + 台账可事后对账。

### 4. 服务端唯一强制点

`evaluate_start_gate` 读两档 + 守卫线 + 报价；计划呈现载荷携带 `requires_confirmation` / `quote_high` / `unquotable`，客户端 Start pill 渲染谓词只读此旗（**客户端永不自行推导要不要确认**）；Start 带价形态 = 既有钮 label 插值，零新 chrome。

### 5. 会话层 token 计量 + context 预算

会话层 LLM 调用（路由/理解/规划/应答/探索/触发回合）**计量但不收费**：`conversation_usage` 表每回合一行（tokens / cache / cost_usd / model），chat 回合入口绑 contextvar 复用 `record_usage` 唯一咽喉；永不上用户账单与 UI（COGS 可见性 + fair-use 数据基础）。context 管理 = 后端装配预算（`chat.context_budget_tokens`）+ 滑动窗口，零 UI。

**Consequences**: 口头确认律（ADR-092）收缩为 ask 档法律；停顿定律（ADR-089 §5）的停止条件从「移动金钱」泛化为「超出常驻授权」；北极星（ADR-088 §1）从「已确认范围」修订为「已呈现且已授权范围」。爆炸半径明账：`evaluate_start_gate` / `_create_run_from_tasks` / scope_classifier 目的地 / prompt 法条（确认律档条件化 + B3 禁令档条件化 + 守卫线转呈现措辞）/ 剧本矩阵 dock-确认断言。默认档下 Start pill 从主路径退役，只在 ask 档或守卫线触发时登场。W11 挂账收窄为：三桶余额 / 订阅过期 / 购买比例 / fair-use 配额 / 支付适配器。

**Related**: ADR-092（口头确认律——ask 档法律由本条接管默认档）/ ADR-089 §5（停顿定律措辞由本条修订）/ ADR-088 §1（北极星英文行由本条修订）/ ADR-087 §4（确认教义——档条件化的母座）/ ADR-055（计费母法——守卫线参数座位）/ ADR-093（起始句言语权——auto 档开工句不变）/ ADR-116（理解性提问边界不动）

## ADR-118: 画布宪法——解耦、chat 自足、存在理由与环境感知

**Status**: Decided；工作区用户布局由 ADR-143 补充，移动端由 ADR-122 决定。

**Decision**:
1. **解耦律**：图模型是世界事实源，画布只是一种投影；画布不得反写呈现推断为执行事实。
2. **chat 自足律**：画布完全隐藏时，上传、计划、授权、生成、交付与修订仍须完整可用。新能力先过纯 chat 闭环。
3. **存在理由**：画布帮助理解多产物关系、来源与修订状态；“剧场”不是合法承重理由。退出由 3–5 名目标用户的多产物、隔天修订、来源核对行为证据决定，审美偏好不触发结构翻案。
4. **信任优先级**：交付可信度 > 来源可信度 > 修订可信度 > 过程可见性 > 剧场。
5. **环境谓词**：客户端以视口能力与 `workspace_layout` 合成 `canvas_available`，服务端结合 world_live 得 `canvas_visible`；unknown 不当 false。模型只读结构化 Environment 事实，不从语言/设备名猜测。
6. **锚卡**：`!canvas_visible` 时，真实 ready 产物在终态收据下以静态数组交付；只读 output_refs，零新订阅，点击开 MediaLightbox。它是收据帧，不是第二 live 面。
7. **承接句窄门**：只有 delivered/partial 且 `canvas_visible=false` 才可指向实际交付卡片；visible 时不提面，failed 不承诺卡片。承接句是普通 LLM 散文，遵守打字机。
8. 布局偏好唯一座位是 SettingsDialog「通用」的 `workspace_layout=auto|chat`；不得在 composer/dock 再造第二套 view-mode 控制或相机节拍。英文用户文案不出现 Agent。

**Related**: ADR-058/060/111/122/143；`VERIFICATION.md`。

## ADR-119: film-spec 第二家族——storyboard 编排 + grounding validator + skill 接入装配线

**Status**: Decided；新视频目标/有效需求 = `docs/VIDEO_PROJECT.md`，施工验收 = `docs/tasks/video-project-implementation.md`；旧实现事实查代码/RENDERING。

**Decision**:

1. **film-spec = clip-spec 的平级第二家族**（ADR-016 契约律不变）：渲染侧 zod schema 只锁形状（`apps/render/src/film/schema.ts`，冻结）；语义 grounding 是编排侧 validator 的座位（一法一座）。派发只读 `spec.family`，禁读节点类型/名称推断；family dispatch 覆盖 preview / retry / revision / recovery 全生命周期，不只首次 render。
2. **storyboard 三分层**：LLM 只写有界秒数意图的分镜（`FilmStoryboard`）→ 纯函数 grounding validator 校验（屏上每个字符串必须命中采集 manifest 的归一化子串 / 相机 focus 界 / 场景枚举封闭 / 时长与字数上限，五类错误码）→ 代码确定性分配整数帧（固定 30fps、divider roll 节拍与 end 卡下限、total = Σ 场景帧）；渲染端只加总。
3. **打回有界**：最多 2 次改写（3 个候选），违规清单骑 repair echo 回灌；耗尽 → 节点 FAILED + `spec.failure.codes` 结构化留痕，禁盲重试。
4. **skill 接入装配线四问分诊**（launch-film 为首例）：① 出生地门 = 节点声明 `requires`（新 `WEB_PAGE` 需求——web_page 资产存在且非全 FAILED，PENDING 由 claim 门等齐）；② 渲染认领门 = render-contracted + `render_status` 的合法待认领集合，执行写权另由 `render_claim_token` 围栏；不得用节点类型平行表或单独 `RENDERING` 状态代替 token；③ spec 落节点 + 经 `pend_outputs_for_render` 唯一渲染座入队，禁第二条编排链；④ 能力菜单/意图目录 = 注册表条目单一注册投影三面，禁手写。
5. **URL 素材化座位 = chat 信封 `material_urls`**：LLM 判定链接是素材（禁长度/正则启发式），`plan_turn._absorb` / `propose_turn._propose_tasks` 两处 absorb 走既有 `create_web_page_asset_from_url` 单一创建座，按 `capture_url` 去重；web_page 资产计入 material_state=attached（file_url 恒 NULL 是设计不是缺失）。

**Consequences**: `Output.type="film"` 与 clip 平级（render-contracted 谓词集合 `_RENDER_CONTRACTED` 共享交付判定）；`OutputResponse.render_spec` 为 `ClipSpec | FilmSpecEnvelope` 联合（序列化不冒充 clip-spec）；fixture 链（手写 storyboard → validator → render → PyAV probe）与 LLM 实跑（一次通过率/打回率台账）为验收闸；计价/配方卡/e2e 归 D3，剧本与仪式链归 D4。

**D4 增补（回归座位拍板）**:

6. **产物文件 probe 校验闸**（放行闸③，禁止事项 10 的座位）：`render_output` 成功路径落 COMPLETED 前必过 `app/pipeline/render_probe.py`——一座闸门、家族分派检查项（film：h264 + 1920×1080 + 视频流帧计数 = Σ场景帧 ±1 帧；clip：存在/非零/容器可读/首帧可解码 + caption sidecar 存在即法、非零当且仅当 `caption_track` 非空——渲染服务对空轨写零字节 srt，空 sidecar 是无字幕 clip 的合法产物）。时长判据走**流帧计数**而非容器时长——mp4 容器 duration 带 muxer 衬垫（取证：465 帧流精确 15.5s vs 容器 15.552s），永不作契约面。未过 = 渲染 FAILED + `spec.failure={stage:"probe",codes,detail}` 盖 render 镜像节点（与 storyboard 的 schema/grounding 同字段形状）；被拒产物本体留对象存储作取证，probe 临时副本即清。
7. **worker 渲染执行形态**：渲染认领后跑 asyncio task（与节点同构），并发上限 `render_concurrency`（默认 2——争用资源是渲染服务的 headless Chrome）+ 单渲染栅栏 `render_timeout_seconds`（默认 900 = 历史栅栏可配化；film 基线 ≈46s/26s 片，clip 长源渲染长尾共享同一栅栏故不收紧）；两键住 env Settings（工程参数，configs 边界律 §3）。验收只要求并发帽、超时、临时目录清理与真实渲染隔离在当前环境重新成立，不保存历史墙钟数字。
8. **失败分类台账 = 仪表层**（`scripts/film_stage_ledger.py`）：五段通过率（schema/grounding/constraint/render/probe）+ codes Top N，读数供归因，永不阻塞部署；数据源 = `spec.failure` 单字段 + 节点/产物终态。
9. **MG 旅程座 = 当前 `SCENARIOS` 注册项**（`chat_scenarios.py`）：URL → web_page 真采集 → 分镜方案 dock（echo 内嵌分镜 markdown）→ 口头 yes 开工 → 真渲染 + probe 闸 → film 产物 + 画布血缘 + 台账 hold=capture+release；只锁形态不锁文案。

**Related**: ADR-016（spec 契约律）/ ADR-028（禁第二条编排链）/ ADR-058（name 二源律，null 读容忍）/ ADR-096 §1（渲染 pend 唯一座）/ ADR-052（absorb 信封座）/ ADR-114（旅程注册表纪律）

## ADR-121: film 采集升档——playwright 引擎 / 逐 section 截图 / 元素点名相机 / 节拍预计算 / 子页发现

**Status**: Decided；有界子页发现是当前契约，实施与验收状态归 Film progress / execution。

**Decision**:

1. **采集引擎 = playwright 驱系统 Chrome**（`executable_path`，免浏览器下载；fallback = playwright 专用 chromium 双轨）。三律不动：`_PolicyProxy`（SSRF 浏览器级）/ 系统 Chrome 优先 / degrade-honest（截图半败 = None）。skill 的 settle / 滚动预载 / cookie 关闭 / anchors 四段已验证 JS 逐字移植为 `page.evaluate()`；产出 = fold + ≤6 张 section 截图（`WebPageMeta.shots`，`extra="allow"` 容忍旧行），`screenshot_key` 保留 = fold。
2. **相机目标点名元素 id，永不发明坐标**（skill 律原文：name element ids, never coordinates）：元素清单（id/kind/text/box）入 `WebPageMeta.elements`（capture 侧 cap），prompt 印元素表，`FilmFocus.element` 由 `build_film_spec` 确定性解出 x/y/zoom；裸 x/y 仅作旧数据读容忍降级。渲染侧零改动。
3. **节拍网格 = 音乐库 seed 期预计算**（beat grid + bpm 存 `Music.meta`，seed reconcile 同座缺则补算）；运行时零测速依赖（aubio/librosa 类一律不入）。幕边界 snap 到最近 beat（±0.2s 容差内才动，结构下限不破），顺序钉死（snap-first）：分配 → 选曲（带人设）→ snap → narration 在 snapped 窗口上合成 → spec——零重合成。
4. **子页发现 = 首页 manifest 同 host 链接**（`BAD_LINK` 过滤正则移植），cap 3，逐条复用同一 capture 入口产独立 web_page 资产；资产模型一对多零改动。禁爬外站、禁递归深挖。
5. **排除**：可编辑 HTML 双交付（产品交付面 = canvas 节点 + MP4）、FAL 生成媒体、运行时音频测速库。

**Consequences**: 新依赖唯一 = playwright（pip）；采集时长因滚动预载上升，`web_capture_timeout_seconds` 与 processor 超时预算同批重估；旧 web_page 行（无 shots/elements）走 fold-only 降级路径继续可成片；`FilmSceneUi.shot`（默认 0）让 storyboarder 在一页多图里选取景。验收锚 = 重采 linear.app 出真内容 section 图 + `scratch/demo-films/` 三片重跑端到端。

**Related**: ADR-119（film 家族基座）/ ADR-129（分镜核对与参数行）/ ADR-028（禁第二编排链/采集链）/ ADR-039（工具包一座）


## ADR-122: 移动端恒 full 纯 chat——dock 形态与 list world 退役

**Status**: Decided (2026-10-15)

**Decision**:
1. **ChatDock = 两形态机（full / panel）**：`dock` 形态退役——History 钮、Hide 钮、历史浮层（`historyOpen` / `historySlotOpen` / `dock-history-in`）、`closeHistory` 句柄同批删除。panel 的 minimize/LogoMark 召回与 `dockHidden` 机制保留（panel-only）。
2. **移动端恒 full**：项目页移动端在任何项目龄都挂 `form="full"`——chat 舞台即页面，无形态翻转；产物交付 = 消息流内（终态收据 + 锚卡 + RunCard，ADR-118 单一渲染面律不变）。「< iPad 宽度无画布」（prohibition #13）与 `canvas_available=false` 上报不变。
3. **list world 退役**：ResultsTabs / 结果网格 / 骨架屏 / `results.empty.*` / `results.retry*` 与路由侧的 tab 机器全删；结果卡组件本体保留——`OutputChatCard` 在流内复用它们。
4. **placeholder 世界自证**：`@` 教学文案从按形态分叉改为按 mention 注册表内容分叉——注册表有产物即 nodes 版，否则 assets 版（移动端 post-run 恒 full 后，形态分叉会永远停在 assets 版，是假事实）。
5. **prompt 法条表面中立化**：`chat_intent_system.j2` 的 launch_film 分镜法条直述真实座位（分镜 = 消息流内 dock echo 内嵌 markdown，全端一致），禁位置词/表面名词（'在下面' / '画布' / 'below'）——trigger_system.j2 交付承接句的同族律，防模型把 "the flow" paraphrase 成不存在的面（ADR-060 echo 防编造律）。

**Consequences**: ADR-041 条款 7 与 ADR-051 条款 7/8、ADR-056 条款 2 中描述移动端 dock 形态 / 三形态机 / list world 为现行法的部分被本条翻案；桌面 full→panel morph、画布 reveal 门（ADR-111）、确认教义（ADR-117）零变化。`canvasVisibility` 双键谓词与真值表不变。

**Related**: ADR-118（chat 自足律 / 锚卡交付）/ ADR-111（画布 reveal 门）/ ADR-060（echo 防编造律）/ CHAT_ARCH §1 关键形态事实


## ADR-123: film 分镜丰富度——支柱迭代弧线 / plate 数字幕 / ui 全出血变体 / 时长窗升档

**Status**: Decided（2026-10-15——对标原 skill 90 秒成片逐帧取证后拍板）

**Decision**:
1. **网页源范围**：scene count 8–20、默认总时长 70–118s；ui 每幕 1–3 focuses。文字源的范围独立，120s 是全家族技术帽，不把创作默认当技术上限。
2. **新场景 plate（数字节拍）**：title + 2..4 张玻璃卡（`big` ≤8 字符、可空 = 短语卡；`label` ≤24）+ 命名程序化 backdrop（aurora/dunes/mist/tide——确定性渐变，零图像资产零 staging）；全片至多 2 幕；grounding 与 caps 同座 validator，spec 由 build_film_spec 直烘。
3. **ui 幕 `frame` 旗标**：true = 浏览器框卡（默认——旧 persisted spec 无此键读 true 兼容）；false = 全出血，相机直接填满画布。渲染侧 UiScene 双形态共享 Captions  overlay。
4. **pack 工艺**：以约 75–95s 为典型 craft target（仍受 70–118s 合法带约束）、支柱迭代弧线（冷开场 → hero → 首支 ui → 逐支柱 divider→ui→plate → reveal 回扣 → end）、plate 稀缺律、frame 叙事选择、相机克制（每幕 1–3 focuses、推进间留 ≥2s 空气）。prompt 法条面只载 schema 与 binding bounds，工艺归 pack（一部法一座不变）。
5. **估价锚**：`ESTIMATE_FILM_SECONDS = 85` 只是典型片报价锚，永远不是目标 midpoint 承诺或校验上限；有版本板时按实际板秒数报价。

**Consequences**: Plate、ui 全出血与 frame 形态共享同一 film-spec/validator；验收必须包含多页采集、混合 frame、plate、真实 beat snap 与完整时长。具体样片和验证状态只读 Film progress，不把一次样片当全站通过。

**Related**: ADR-121（采集升档 / 节拍 snap）/ ADR-129（分镜核对）/ ADR-119（film 家族基座）/ ADR-016（spec 契约律）

**Identifier alias**: 本条的 ADR-123 专指 Film 分镜丰富度。旧代码注释中指向 `workspace_layout` / 工作区布局的 ADR-123 应解析到 ADR-143，不指本条。


## ADR-143: 工作区布局用户设置——画布能力位的第二判断源

**Identifier alias**: 本决策曾以重复编号 ADR-123 落档；现编号为 ADR-143。旧代码注释中指向 `workspace_layout` / `canvasCapableFor` 的 ADR-123 均解析到本条；Film 分镜丰富度继续使用 ADR-123。

**Status**: Decided (2026-10-15)

**Decision**:
1. **两档设置**：`users.settings.workspace_layout ∈ {auto, chat}`（默认 chat）。chat = 任何屏幕恒驻 full 纯 chat；auto = 视口跟随（宽屏画布 + panel，窄屏纯 chat）。**不设「强制画布」档**——<iPad 无画布是架构禁令（prohibition #13），强制档在移动端是虚假承诺（虚构 SKU 禁令同族）。
2. **服务端只存不用**：跨设备同步的真值源；谓词消费零新增——有效的 `canvas_available` 由客户端合成并随每条 chat 请求上报（ADR-118 双键机制不变）。存键零迁移（JSONB）；词表/读写纯函数住 `app/platform/user_settings.py`（confirm 双键同构）。
3. **能力位唯一合成座**：`canvasCapableFor(isMobile, workspaceLayout)`（`lib/canvasVisibility.ts`）——视口 ∧ 设置；项目路由内全部画布门（worldLive 的 plan-ready 项 / canvasVis / 画布挂载 / form / 相机节拍）读这一个合成值，单源律扩展到「禁以设置项自行推断」。
4. **localStorage 镜像**（`repurposer-workspace-layout`）：首条 chat 消息挂载即发出并给会话盖 `canvas_available` 章（last-wins），设置必须首帧同步可读，否则 chat 档桌面用户首章错盖 true（承接句门会被反向编造）。镜像 = 主题先例；GeneralSection 挂载时以 server 值回写镜像（server wins，跨设备同步点）；hook 初值 `"chat"` + effect 矫正（SSR 律 + use-mobile 同族先例）。
5. **UI 座位**：SettingsDialog 新增「通用」section（显示类偏好）——「助手」区是确认偏好的唯一座位（CLAUDE.md），布局偏好不混入。主题/语言留 account console 不动。

**Consequences**: chat 档桌面用户得到与移动端完全同构的体验（锚卡交付 + 承接句门自动正确）；auto 档与移动端行为零变化。

**Related**: ADR-122（移动端恒 full 纯 chat）/ ADR-118（环境双键）/ ADR-117 §1（users.settings 座位先例）

## ADR-124: World seats——fetch 型读工具的 consult-first 律与页面读本入库

**Status**: Decided (2026-10-16)

**Decision**:

1. **页面读本入库，随项目终身**：新表 `page_readings`（(project_id, url) 主键 + text + fetched_at，随项目级联删除）。快照语义：文本是 fetched_at 时刻的采集，重抓是显式动作（用户说页面变了 → 工具的 `refresh=true`），永不 TTL 隐式失效。两个写口一个座位：chat 读工具写穿（fetch 成功即写回）+ web_page capture 链在 `process_asset` 落 `extracted_text` 时同写。
2. **world seats 模块**（`app/tools/world.py`）：每个项目级世界事实一个 canonical 读本函数（首座 = `page_reading_for_url`）；新鲜度政策住座位、永不住工具。URL 归一化（scheme/host 小写、去 fragment、去尾斜杠）保证同一页面的不同拼写命中同一行。
3. **consult-first 律 + 注册表门禁**：fetch 型读工具先问座位再触网；`PerceptionTool` 加 `seat` 字段声明所问座位（无 canonical 存储的读——如 web 搜索——声明 None = 天然 ephemeral），纯函数套件门禁：声明的 seat 必须指向 world.py 的真实函数，get_web_page 必须带 seat。新工具的复用能力是构造性的——注册表逼你声明，不声明过不了门。
4. **读工具写纪律的 carve-out**（ADR-077「loop 内零副作用 / 读工具零写函数」修订）：chat 读工具的读本写穿走**独立短事务**（`world.write_page_reading` 自开 session，best-effort 失败只记日志）——回合事务保持只读，快照行是世界 memo 不是领域状态；capture 链写回用 `process_asset` 自有会话。

**Consequences**: 同一 URL 在项目内只抓一次（讨论链接与素材链接收口同一读本）；「读本采集于 N 天前」随观察文本上行，世界自证。讨论链接不落画布的法条不动（读本行不是素材，无资产节点）。`page_readings` 表归属登记 = MODULE_ARCHITECTURE §4。

**Related**: ADR-077（读工具纪律 carve-out 由本条修订）/ ADR-121 B4（web_page 采集链——读本写回的第二写口）

## ADR-127: 分镜骨架收归代码——固定结构 + 创作槽 + 固定分镜兜底 + 流式传输

**Status**: Decided (2026-10-16；2026-10-27 用户拍板修订相机目标分工；适用范围 = 网页源 film 骨架；文字源与组合编排见 ADR-138/140)

**Decision**:

1. **网页源骨架 = 代码（固定模板）**：场景序列/幕数/时长/视图分配以及相机时序与几何由代码确定性派生（`build_skeleton` + `_scene_plan` + `_assign_seconds` + `_camera_walk`），对齐 skill 的「structure that works」：cold open → hero → home walk → 每柱 divider → walk（页面带数字时第一章后插 plate）→ reveal → proof walk → end。时长带 = 70-118s（帧帽留余；skill / prompt / markdown 同此一法），幕数窗 = 8-20（3 柱 10 幕 ~ 5 柱 18 幕），per-type 秒带同批调整（j2 镜像契约同步）。默认相机目标 = 元素清单首选未遮挡 heading/button（大面积优先），无清单 = 诚实中心推近；director 可按第 2 条覆盖同 shot 的目标，代码仍负责元素盒解析、安全缩放与完整 camera walk。视图按序消费，divider 后无 walk 的章节 = EMPTY_CHAPTER 硬违规（打回减柱，永不编造画面也不出空章），同图同呈现 = REPEATED_VIEW，零相机 beat / 相邻近重复 = PADDING_SCENE；< 4 可用视图（home + 三章 walk 的最低配置）= 预检直接诚实失败（INSUFFICIENT_VIEWS），LLM 调用都不烧（skill 同法：站点挡抓取 = 停下来要截图）。
2. **LLM 答创作槽与有界相机目标（`FilmDirection`，一次调用）**：事实槽仍引用（pillars 3-5 / hero / captions / reveal word·sub / end——`CopyRef{line, fit, accent}` 选行不写字，fit=head/tail 代码按词界裁剪，accent = 解析后文本的子串）；创作通道 = 自由文本（cold_open 钩子 ≤3 词、reveal_lead 可空走代码固定句、narrations 按场景键对位）——**钩子不是宣称**（创作永不伪装产品事实），校验器 `_CREATIVE_SLOTS` 免 grounding、帽/空白/查重仍查。`camera_focuses` 以 UI scene key 选择同 page+shot 的未遮挡元素 id；实际被分配的 section 截图随同一 director 调用提供，缺省/空值继承骨架默认。LLM 不返回坐标、zoom 或时间；代码把元素盒解析为安全取景（数值契约归 `RENDERING.md`）并展开完整路径，renderer 只执行路径。divider 的 label = 代码 kicker（按影片语言小表），roll = 代码造（下两章循环当 decoy + 真词收尾，签名按序防同集误判）；plate 卡片 = 代码从数字行切 big/label（全引用纪律，创作零需求）。输出从「整篇分镜 JSON」缩到槽位答案——输出 token 量大头消失。
3. **固定分镜兜底（`fixed_direction`）**：候选穷举 / schema 终局 / 传输失败 → 同一骨架上代码填全槽（pillar = 前 3 个 h2，h3→h1→button 依序补足；hero/end = title/description；cold open 引 title 头部），过装配 + 校验即出片；只有薄到凑不出三章的 manifest 才诚实失败。**适用面收窄（ADR-131）**：固定兜底只保留给无人值守 worker 节点；对话设计旅程永无固定兜底，失败 = 诚实说明 + 有效重试。排序（worker 道）：LLM 多模态（流式）→ 声明式 media_text_fallback → 固定分镜 → 诚实失败行，每级都诚实。
4. **流式传输（Agent 声明 `stream=True`）**：`generate_stream` 无 delta 消费者（无消费者重试恒合法——下游从未见字节）；reasoning chunk 持续流动使读超时不再误杀慢而活的生成，`llm_first_chunk` 秒级见活，真挂死快速判死。修理轮永不流式（既有律）。

**Consequences**: 固定兜底只在骨架与接地事实足够时填槽；`INSUFFICIENT_VIEWS`、空章节、证据不足或装配/校验不合法时必须诚实失败，**不存在“worker LLM 全挂也必有分镜”的承诺**。对话设计旅程不使用固定兜底；worker 的每级降级都必须保留真实原因。已解析 FilmStoryboard 仍是唯一持久化/渲染形态。

**Related**: ADR-129（设计拍同步起草——本条运行时骨架法不动）/ ADR-131（呈现位移与预算——兜底收窄）/ ADR-119（film 家族基座）/ ADR-093（言语 = LLM 之声）/ ADR-039 P3（盲重试禁令——流式重试只在首 delta 前）

## ADR-129: film 分镜 = 设计拍普通工具调用——版本化呈现 / 全局生产授权 / 禁静默换稿

**Status**: Decided（2026-10-16 用户拍板；2026-10-17 用户拍板修订；现行对话行为 = `docs/CHAT_ARCHITECTURE.md` Film 段与 `docs/VIDEO_PROJECT.md`，施工与验证状态 = `docs/tasks/video-project-implementation.md`）

**Decision**:

1. **设计拍独立于生产拍**：`design_storyboard` 呈现分镜，不创建分镜专属确认控件；设计工具自身不创建 run。设计授权只授权设计，生产授权由当前对话的制作意图与全局 ask/auto/credit 规则共同决定。
2. **版本化闭环**：已呈现分镜有版本、不可变内容 digest 与执行快照；方案座只引用当前版本，worker 只执行被引用的版本，漂移即停止并回到重新设计，永不静默换稿。
3. **修订基于当前稿**：明确的修改请求本身就是对应修改的授权，但不等于授权渲染；修订保留用户未要求改变的内容并产生新版本。无关提问只解释当前稿，不设计、不启动。
4. **现行正文与验收分座**：对话行为正文在 `CHAT_ARCHITECTURE.md`；Film 字段与版本契约在 `VIDEO_PROJECT.md`；剩余验收在 execution，实际状态在 progress。早期 journey-closure 尾项只由 `PROGRESS.md` §0.2 追踪，不再充当另一份行为法。

**Consequences**: 分镜不获得独立确认偏好座位；`confirmed_scope` 仍是生产授权快照座；旧确认失效与并发防护是版本闭环的一部分，但不删除无关任务或用户内容。

**Related**: ADR-127（骨架收归代码）/ ADR-119（film 家族基座）/ ADR-117（确认档普通法与守卫线）/ ADR-028（编排环一座）/ ADR-093（言语 = LLM 之声）/ ADR-089 §4（confirmed_scope 快照座）

## ADR-130: film 时序执行契约——beat-locked frames / 配音字幕 / camera walk / split reveal

**Status**: Decided（2026-10-17 用户拍板；字段级正文 = `docs/RENDERING.md` film-spec 段）

**Decision**:

1. **同一时序源**：分镜展示、执行快照与 film-spec 读同一 resolved music grid；曲目缺节奏信息时先走现有分析补齐，仍无法获得才诚实失败。
2. **spec 自带执行血缘**：film-spec 携带 fps、帧数、音乐节奏信息、逐幕 narration audio 与同文本 captions、camera/reveal 的执行锚点。
3. **真实 beat 律**：reveal 黑场是一拍真实 beat interval；固定 0.5s 不得被当作一拍。
4. **字段契约一座**：字段级渲染契约只维护在 `docs/RENDERING.md`；Film 版本、音频与质量约束归 `VIDEO_PROJECT.md`，实际验证状态归 `docs/tasks/video-project-implementation.md`。

**Consequences**: 渲染器只求和、播放并消费 spec 中的锚点，不发明时长、字幕或 reveal 停顿；旧 spec 由 schema 读容忍处理。

**Related**: ADR-129（分镜版本闭环）/ ADR-127（骨架与创作槽）/ ADR-121（capture parity 与 beat grid）/ ADR-016（renderer 黑盒契约律）

## ADR-131: film 分镜呈现位移与生成预算——LLM 唯一表达 / 程序 markdown 退役 / 1800s 上限 / 设计旅程无固定兜底

**Status**: Decided（2026-10-18 用户拍板）

**Decision**:

1. **工具产生真实分镜，LLM 负责唯一表达**：`design_storyboard` 设计/校验/保存真实分镜，并返回已保存稿的完整结构化事实（`storyboard_presentation`——版本/名称/旁白语言/画幅/FPS/执行时间轴总秒数总帧数/音乐 BPM/每幕顺序·类型·时间段·时长·帧数·所见·相机·逐字旁白·素材来源）；设计拍的下一条普通 assistant 消息是分镜的唯一呈现（短引言 → 幕表 → 衔接下一步），程序独立 markdown 消息形态（`render_storyboard_markdown` / `publish_storyboard`）退役。展示时间必须来自同一执行时间轴（allocate_frames → snap_frames_to_beats），LLM 永不自算。
2. **呈现关联在落定后**：`film_presented_message_id` 只在最终 LLM 呈现消息成功持久化后关联（finish() 盖章座位——终态行与 bare-reply 行；降级行永不盖章），且关联到本次工具返回的具体版本（版本守卫——版本移动/无稿不盖；同版本重呈现重盖最新）；失败/取消/断连随回合回滚，不留幻影「已展示」。刷新前后只有一份分镜。
3. **方向/分镜生成预算**：1800s 是共享墙钟允许上限（非固定等待）；per-request 流式读超时与 SSE 心跳按当前配置。**统一 10 次 LLM 生成调用硬上限是独立上线阻塞，当前尚未完整实现**；schema 修复、多模态降级和嵌套重试共享计数，不得刷新。墙钟、候选界和 chat loop 各自有限不能冒充统一预算。
4. **超时兜底必须诚实**：对话设计旅程关闭固定兜底（`allow_fixed_fallback=False`）——候选穷举/预算耗尽/传输失败 = 诚实说明 + 有效重试（`film_storyboard_timeout` 人话行），静默低质稿冒充成功永禁，不误报 grounding 失败，不触发制作；固定兜底只保留给无人值守 worker 节点。

**Consequences**: 同一回合双份分镜结构性不可能（呈现面只剩一座）；用户看到的稿与保存/执行的稿同源；LLM 误呈现永不进入执行（生产消费 digest 锁定稿的既有门禁未动——呈现层诚实靠法条 + 完整事实，不解析 LLM markdown）；180s 级预算误杀慢而活的生成消失。

**Related**: ADR-129（设计拍与版本闭环）/ ADR-127（骨架与兜底——适用面被本条收窄）/ ADR-130（时序同源）/ ADR-093（言语 = LLM 之声）/ ADR-060（echo 防编造律）

## ADR-132: film 批准语义与配音承诺——批准 = 消费呈现版 / 守卫分腿 / voiceover 直达设计层 / 全静默即违规

**Status**: Decided（2026-10-18 用户拍板；后续制作意图与修订呈现修订见 ADR-139；现行对话行为 = `docs/CHAT_ARCHITECTURE.md` Film 段）

**Decision**:

1. **批准 = 消费呈现版**：用户批准已呈现分镜 = 用同参数 dock 提案 + 一句真实开工说明，不产生新版本、不再现设计 activity，也不把批准解释为重设计许可。呈现后的下一步遵守 ADR-139：普通修订完整呈现后以 `answer` 询问是否重制；review-only 不问开工；当前消息明确制作委托时进入既有提案与执行道。内部动作问句（「挂方案/定稿入库」）永禁。开放重编排的 `specific_instruction` 只携带修改本身，定点修改走 `edits`，均不复述既定方向。
2. **dock 守卫分腿**：版本守卫的每个失败腿（在飞设计 / 无版本 / 状态残缺逐项 / 指纹移动）记 structlog 且引导文本只指该腿自己的修复——复呈现/修复性复呈现（原参数裸调 design_storyboard，禁 specific_instruction）或等待，永不一律导向重设计；批准路径上的守卫拒绝永不是重设计许可。
3. **voiceover 直达设计层**：`voiceover` 从计划参数传入 orchestrate → 导演 prompt 明示本片是否带配音（「视觉优先」描述画面不取消声音；修订时未被点名的旁白必须保留）；`voiceover=true` 而全片无旁白 = `NARRATION_MISSING` 校验违规（有界打回修复，冷开场/divider 合理静默合法）；旁白键不匹配任何场景 = `NARRATION_KEY_UNKNOWN`（点名有效键），静默吞键永禁。
4. **worker 两道防线**：prepared 稿防御性重校验带 `narration_required`（voiceover 承诺下无声稿 = stale 诚实失败）；配音合成门前全片无旁白即 fail-closed，永不无声交付，worker 也永不替用户写未看过的旁白。

**Consequences**: 「按这版做」= 不换稿、不取消旁白、不再绕一轮设计；守卫拒绝从此自带可定位的腿名（04:15 式不可考拒绝不再重演）；voiceover 承诺在设计/校验/执行三层同法，静默影片只有 voiceover=false 一条合法路径。

**Related**: ADR-129（版本闭环——批准消费的是它）/ ADR-131（呈现位移——呈现即唯一表达）/ ADR-127（骨架与创作槽——旁白槽的完整性门）/ ADR-130（执行契约——配音/字幕同源）/ ADR-093（言语 = LLM 之声——开工说明一句真话）

## ADR-133: System Status 相位面终态——通用 LLM 黑盒窗只叫 Thinking…，composing 退役

**Status**: Decided（2026-10-18 用户拍板）

**Decision**:

1. `assistant.thinking` 相位面 = 基座（Thinking…）+ 分镜设计跨度三真相位（capturing / storyboarding / storyboard_revision，`design_storyboard` 执行内真实转换点发射）+ 显式清除帧。**通用 LLM 黑盒窗（读后决策 / 回复生成 / 一切无名窗口）只戴基座词，无论多长不设别名。**
2. 清除帧合法发射座两座：每个调用名的 name-known 时刻（`routes.py:_make_tool_hooks`，无相位在戴 = no-op）+ 分镜跨度自身退出（`draft_film_storyboard` 的 finally——跨度的词跨度自己收；bare-reply 终局没有 name-known 兜底，此座承重）。
3. loop 内核 `on_observe` 钩子随唯一消费者（`chat/system_status.py`，整删）退役而删除——内核自带律：无消费者的事件是等待漂移的谎言；`ReadAccepted` 仍骑 `on_loop_event`，Activity 投影不受影响。
4. 新相位准入：它必须命名一段结构性不同的真实活动，且该活动没有更诚实的通道（Activity / prose）——通用决策窗别名永不复活。

**Consequences**: 读后决策窗与回复生成窗回到基座词，窗口时长不变、词不再怪；前端未知相位落 `defaultValue` 回退基座（`ActivityStream.tsx`），新旧端互撞零风险。分镜跨度的真相位机制不受影响。

**Related**: ADR-087 §1（三通道分家——相位面的归宿）/ ADR-110（段聚合——收据行接管「干完了」的证明）/ ADR-129（分镜跨度——真相位的唯一在册族）

## ADR-134: film 首稿分镜默认 hold——用户没见过的稿永不开工

**Status**: Decided；首稿强制审阅 = ADR-144，普通修订授权 = ADR-139。

**Decision**:

1. **fresh COMPOSE 草稿（首稿；开放重编排——用户没见过的结构）默认 `film_review_hold=True`**——`film_design_state` fresh 分支 None 即 ON（`created_via="compose"`），不继承 stored hold；**edit/variant 版本生于用户的明确修改请求，不新增 hold**（默认 OFF）；修改请求授权的是这个版本的修改本身，不等于授权渲染（ADR-139 §3 收窄）。修订呈现系统变化摘要与当前保存版本的完整事实；普通修改没有 `production_intent=true` 时以 `answer` 收尾、不建 `launch_film` dock，当前请求明确制作委托时才进入既有提案、报价与执行道。REUSE 再呈现（同一稿）保持继承（稿已见过）。显式 `review_hold` 参数仍是双向逃生门（用户明说「先让我看看」挂 hold / 后续版本「不用看分镜，直接做」放行）；作品首稿不再由 `review_hold=false` 或开场直接制作委托跳过审阅，见 ADR-144。
2. 释放座不变：用户看过呈现后的制作话释放 hold；ask 可由 approval dock 的 Start 生成这条消息，auto 无其他确认债时直接输入。Start 门 `422 start.review_hold` 是确定性兜底，法条观察文案分叉不变（`hold_fact` 自适应）。
3. **`rewrite_film_task_params` 改替换语义**：launch_film 的 params 整体变成呈现版参数（`dict(version_params)`），永不再 merge——确认链携带的恰好是呈现稿的设计参数，模型多写的 canonical 相关键不落盘。
4. 剧本 S11 增放行拍：设计拍断言无 run（hold ON 呈现即停）→ 用户放行消息 → 下一回合 `start_run`；auto 无其他确认债时不显示首稿 dock，ask 的 dock Start 只发送这条消息。分镜呈现断言不锁信道（row.append 帧或终封筒 assistant_message 皆可——契约 = 用户看到分镜消息）。

**Consequences**: 命令式入口变成两回合流（设计拍呈现即停 → 用户放行消息 → 下一回合开工）；auto 无其他确认债时无首稿 dock，ask 的 Start 只生成同一条放行消息。compose 修订重稿同样等放行；普通 edit/variant 先完整呈现当前保存版本并以 `answer` 询问是否制作，不新增版本 hold，也不先建制作 dock；当前请求明确「改完直接做」时不机械增加第二轮批准，既有执行、费用、drift 与 Start 守卫继续生效。既有挂单（另立批处置，不在本决策）：① ADR-129 的 `on_row_append` 分镜发布座从未接线（零调用点）——分镜行目前只骑终封筒，长跨度窗口内流死即直播不可见、刷新 replay 才现身；② 无前置挂单时设计拍的 birth prompt 冻结为当回合文本（如 "ok"）而非原始求片句。

**Related**: ADR-129（分镜拍与版本闭环）/ ADR-117 + ADR-139（auto 只在制作意图与确认债条件满足后开工；hold ON 时 dock 等待拍先行）/ ADR-131（呈现 = LLM 散文唯一座）/ ADR-137（edit/variant 的 ops 与版本信封——本条 hold 收窄的执行面）

## ADR-135: 全败 run 必须开口——run_failed 入触发白名单

**Status**: Decided；失败分支的当前交付职责见 ADR-141。

**Decision**:

1. **`run_failed` 入触发白名单**（`pipeline/trigger_events.py`）。fire gate 与 run_completed 互斥：`FAILED 且零产物落地` 才 fire（部分失败仍走 run_completed 收官评审，GAP 行说部分真相）。
2. **FAILURE FACTS 块**（`_failure_fact_lines` 纯核 + `_run_failure_lines` 装配，与 DELIVERY FACTS 同教义）：每个失败判决步一行，`step.error` 的烘焙人话行（bake-at-write, errors.py）原样携带——确定性事实，turn 只许叙述永不重推导原因；fanout 渲染失败用判决同一谓词排除（产物级事实永不是 run 死因）。
3. **下一步 dock 成 ≤2 个「能成功」的选项**（`_wrap_up_rejection` 新腿：run_completed 硬顶 0 不变，run_failed 硬顶 2）：零落地没有产物卡可骑，下一步的可点形态 = ADR-081 真实选项问，作答骑 answer 端点 generic 续聊零新机制。prompt 法：确定性死因（如旁白超长）永不给「原样重试」，暂态死因才给；无可行动死因时 suggestions=[]，收尾句口头给重试。
4. **花费沉默绝对**：失败 run 零扣费是事实，但收官/通报拍永不说钱（2026-09-24 拍板不变）。

**Consequences**: 全灭 run 的用户体验从「静默红收据」变为「通报原因 + 可点下一步」；既有入场/落点双门（在飞 defer、pending plan 静默）、按 (trigger, ref) 去重、fire-and-forget 教义全部原样继承。仪表层可后补 staged-failure 剧本（活闸矩阵暂不锁失败通报形态——制造确定性全败 run 需专用 fixture）。

**Related**: ADR-077（触发回合机制）/ ADR-074②（run 判决——全灭沉默腿被本条翻案）/ ADR-081（选项语法统一律）/ ADR-134（首稿审阅与可讲性边界）

## ADR-136: film 旁白窗口弹性——有界零和借帧 + 披露，永不静默改写分镜

**Status**: Decided；字段级旧渲染事实 = RENDERING/代码；新内容合同 = VIDEO_PROJECT。

**Decision**:

1. **窗口弹性（window flex）= 速度梯与 honest fail 之间的唯一救援座**（`tools/film/narration.py` 的 `_flex_frames_for_overruns` 纯核）：旁白场景从**静音场景**借帧把窗口撑到放得下已合成的音频——音频不重合成不重计费，帧动音频不动。
2. **三条硬界**：① 零和——Σ frames（总时长、已计费的 film_seconds）永不动；② 双侧封顶——捐赠场景总计最多让出 30% 且永不跌破结构地板（`_scene_floor`），接收场景最多撑 +40%；③ 只在今天会失败的路径上激活——速度梯能放下的词永不触碰 flex，绿色渲染逐字节不变。
3. **救不回 = 原法不变**：有界借帧盖不住缺口时按原样 honest fail，错误明细同时点名真实尝试与被尝试的 flex 界（设计问题走设计拍，永不是渲染期糊弄）。
4. **披露是法律**：flex 移动记在 output payload（`narration_flex`），run_completed 收官评审的 DELIVERY FACTS 携带 `pace=adjusted(+Xs)` 事实行，叙述者**必须**如实转述（自己的节奏调整口吻，永不说是缺陷，永不跳过不说）——这是「展示=执行」的有界披露容差修正案：分镜表的逐场景秒数允许 ±界内偏差，代价 = 收官句必说。
5. 节拍吸附让位：flex 在 beat snap 之后运行且不再回吸——词放得下是硬需求，节拍对齐是 ±0.2s 的软服务（法条本就说「the grid serves the cut」）。

**Consequences**: 界内缺口可自愈且总时长不变；分镜秒数与成片只可在合同界内偏差并由收官句披露。超出边界仍诚实失败。捐赠顺序确定（余量降序 + 场景序 tiebreak），回放可复现。

**Related**: ADR-130（配音拟合梯——flex 是其 exhausted 分支的延伸）/ ADR-135（救不回时 run_failed 通报座）/ ADR-129（展示=执行——本条引入有界披露容差）/ ADR-134（首稿审阅）

## ADR-137: film 编辑拍（patch path）——结构化 ops / 版本信封 / base 引用协议 / 报价分叉

**Status**: Decided（2026-10-20；现行契约 = `docs/VIDEO_PROJECT.md` §2/§6/§15；施工与验证状态 = `docs/tasks/video-project-implementation.md`）

**Decision**:

1. **`design_storyboard` 增 `edits` 岔路（不新增 chat 工具）**：`edits: list[FilmEditOp]`（update_scene / update_element / reorder_scenes / remove_scene / set_music / set_voiceover）+ 强制 `base_ref`。与全部设计参数及 `specific_instruction`/`material_urls` 互斥（schema 层拒）；`edits` 空 = compose 路径不变。ops 由**系统**有序原子应用（`tools/film/edits.py` 唯一应用座）：任一拒整批中止零部分落库；整批无存活变化 = `unchanged` 拒（不建版本/任务/费用）；`change_set` 由系统按 scene_id 独立比对计算；工具结果同时携带系统变化摘要和共享呈现座生成的完整当前版本事实，回复呈现二者，不让模型根据旧表与差异自行重建当前表。`set_aspect` 不在当前 op 词汇中，画幅变体为 PLANNED。
2. **scene_id 出生即分配**（`assemble_storyboard` 用骨架 key；legacy 板首次 patch 时位置派生一次性升级）；id 是句柄永不入内容指纹（digest 剥 id，legacy digest 字节兼容）。
3. **版本信封**：PendingPlan 增 `film_base_version` / `film_created_via`(compose|patch|variant) / `film_change_set` / `film_constraints_choice`（全读容忍；constraints_choice 写座随约束分层落地）；Start stamping 与 provenance 恢复携带同键。
4. **base 引用协议（目标版本匹配的接线律）**：读取座（设计拍观察行 / `get_output_spec` film 分支）呈现版本时铸造 `base_ref = film_version_identity_digest(board, params)`（内容 + canonical 参数 + 有序场 id 绑定），模型随 edits 原样传回；执行前快拒比对（无 marker 空转）+ apply 座复核 + 提交前 committed 版本回防（live-pending base 限定）；显式 @output 钉旧版 = 以该版本为 base 的分支语义，永不静默换最新版。**禁止用刚解析的 base 现算期望值**（自比较恒匹配，防不了过期编辑）。
5. **编辑拍授权**：edit/variant 版本不新增 review hold（ADR-134 修订）；本回合设计已落版而 `production_intent` 非 `true` 时，`present_plan` / `propose_tasks` 在 dock 前结构性拒绝 `launch_film`，完整呈现后以 `answer` 收尾（普通修改问是否重制，review-only 不问）；当前请求明确「改完直接做」才进入既有提案、报价与执行道，旧 run 或旧版批准不继承授权。语义校验失败/unchanged/base_mismatch 回结构化修复回声进 chat loop（模型回合内修复重调），永不退回导演重设计、永不成通用 500。
6. **edit 报价分叉**：run 生于版本化板时，launch_film 估价的 `film_seconds` 读实际板秒数；compose/新建按全量旁白字符，patch 按失效场与可证明复用范围计算 `tts_chars`，不得预宣称未证明的复用折扣。无钉版板的出生维持典型常数。同一价目线 capture 实扣不变。
7. **编辑能力门控（内部测试纪律的实施座）**：`settings.film_edits_enabled`（env，默认关）。关闭时模型永不获知该能力——wire schema 剪掉 `edits`/`base_ref` 并垃圾回收孤儿 `$defs`（`tool_spec` 的 `wire_view` 钩子，spec 组装时每回合判定）、工具描述去掉 TARGETED EDITS 段、`_website_film.j2` 编辑法条条件渲染（两个系统 prompt 同参）、`get_output_spec` film 分支与 compose 观察不铸造 base_ref——且执行端双路 `_design_storyboard` 对直接带 edits 的调用诚实拒绝（声明与执行同闸，绕过不可达）。开启仅用于本地/测试验证（测试显式 monkeypatch 开启）。
8. **冻结时间轴 = 版本状态（keep_cut 及其继承的消费座）**：`retime` 是执行指令不进 params/指纹，经 change_set.music 传递。**keep_cut = 冻结 base 版本自身的切点**：已执行过 → 其 run 产出 spec 的逐场帧（旁白 flex 后真值，revision-base 座以 `film_cut_frames` 读入）；未执行草稿 → 其**已呈现计划时间轴**（base 板按 base 床网格 snap——呈现与执行同一 `execution_frames` 公式）；**永不回裸分配、永不按新床网格重卡**。**继承律（失效按实际变化与依赖，不按 op 名）**：冻结切点作为版本状态跨版继承——不动时间轴的批次（无 moved/removed/added/retimed、无存活 recut）继承 base 的已确定切点，不因本轮是否出现 `set_music` 而丢失（「换音乐 keep_cut → 再关旁白」链最终帧仍等于原片）；结构变化或存活 recut 合法丢弃，run 重新 allocate+snap，旧帧不被盲目沿用。**来源区分**：基准恢复链路携带 `film_cut_state`（spec / kept / draft / unreadable）——`kept` 含 Start 投影进 `run.context` 的冻结切点（run 在 Output 创建前失败不丢冻结状态；无 Output ≠ 普通草稿）；确无冻结状态的普通版本按 draft 规则用其已呈现计划时间轴；**已执行作品 spec 缺失/损坏、或冻结状态损坏/keep_cut 指令无帧 = 实际切点不可恢复，保时间轴的编辑结构化拒绝 `base_cut_unreadable`**（指引重读版本或显式 recut；永不静默重算冒充原片、永不退全量重设计、永不 500）。链路：patch 拍计算冻结 → 信封 `film_kept_frames` → Start stamping 投影 run.context（`film_music_retime` 作指令 provenance + 半写信封绊线）→ run 消费门 = **kept 帧在场即 fail-closed 消费**（`valid_kept_cut` 不过 = 诚实失败；keep_cut 指令无帧同罪；永不静默重卡）。**旁白适配同样冻结**：冻结版本下 narration flex 要移动帧即诚实失败（指引缩短台词或允许 recut）——「保持节奏」覆盖旁白自救。兼容律：keep_cut 不得与改时间轴 ops 同批（`keep_cut_incompatible` 结构化拒绝，指引 recut/拆批）。其余出生（compose / recut / 时间轴变更批次 / legacy）照旧 allocate+snap。并发丢弃（superseded）座在回答前释放本 draft 的 marker（`clear_film_draft_marker` 只清本 draft——compose 与 patch 四座同法）。

**Consequences**: 定点修改零导演调用（闸 2 由接线测试断言）；编辑能力由门控实施（声明面与执行面同闸），当前本地/测试已启用，生产默认关闭，启用与部署另行授权；能力菜单/交付建议只承诺已实现 ops。`set_aspect` 仍是 PLANNED，画幅修改请求走诚实「暂不支持」，永不导向重设计兜底；`insert_scene` 不做，compose 可增删场景。`set_voiceover(true)` 走既有旁白行合成/复用，零重设计。警告通道（warnings）随约束分层落地前恒空；REPEATED_VIEW / PADDING_SCENE 当前仍为硬违例，warning 降级为 PLANNED。

**Related**: ADR-129（版本化呈现——编辑拍骑同一版本闭环）/ ADR-134（hold 收窄的修订对象）/ ADR-117（auto 档授权继续）/ ADR-130（音乐网格与快照自证——patch 版本重建快照沿用同法）

## ADR-138: film 双链范围——文字视频为本期正式能力 / 音频三态与试听 / 完整知识视频移出本期

**Status**: Decided（2026-10-21 用户拍板；施工组织 = `docs/VIDEO_PROJECT.md`，设计契约 = `docs/VIDEO_PROJECT.md` §2/§6/§15）

**Decision**:

1. **文字视频 = 本期正式能力**：用户直接提供的文字稿是独立素材源——不依赖 website manifest，不伪造网页接地（接地语料 = 用户文案本身）。模型在能力范围内决定分段、出现顺序与持续时间；用户要求文案逐字保留时不擅自改写。最小排版控制 = 枚举 typeface / 字号档 / 对齐 / 行级颜色或重点强调（正确处理换行与溢出；中文正常显示已有 vendored Noto Sans SC 保障）；最小文字运动 = 静止 / 缓慢推近 / 拉远 + 少量进出场枚举，运动作用于文字画面本身，不只实现网页截图相机；背景至少纯色，既有图片/logo 能直接复用则复用（不扩建素材平台）。模板 = 同一能力之上的默认配方（配方卡预填 promptTemplate 即全部发射载荷）。**不做**：自由画布编辑器、任意 CSS、通用关键帧系统、多轨编辑器、模板市场。
2. **音频三态语义**（「参数可选」是产品语义，不是把执行字段全变 nullable）：**未指定** = 允许按配方选默认值，并在制作设置中如实呈现；**明确关闭** = 真实状态，persona 或默认值永不重开——音乐关闭必须有真实状态，不得回落为默认 calm（`resolve_film_music` 的 mood→brand→calm 链遇显式 off 短路）；**明确选定** = 版本与执行使用同一选择，后续读取能说明真实配置（voice 解析上移设计期钉入版本/执行快照，复用 `resolve_film_voice` 同座，先例 = 设计期解析音乐）。重新开启配音不强迫全片重设计——有现成旁白文字时直接走合成。
3. **试听（PLANNED / 条件触发）**：声音目录、试听系统和设计期选声体系不是当前闭环前置；当前默认不配音，用户明确要求才走现有 TTS 链。用户重新提出“先听再决定”时启用以下合同：用户说「先听一下再决定」时，chat 提供真正可播放的声音样例或音乐预览并等待这次选择——只显示声音名/音乐名不算试听完成。优先已有样例、已有音乐或短样例（声音目录最小注册表 + 预生成短样例 reconcile 种子；音乐库曲目文件直接预览），不为试听生成整片旁白，并说明实际调用成本。试听与随后制作绑定同一音频配置——不能试听一种、成片换另一种。不对所有创作强制新增确认步骤（ADR-117 授权律不动）；用户明确要求先试听、先审阅时不得提前制作。试听 UI 骑结构化卡片面（助理消息 markdown 不渲染裸 HTML——只发链接文本不可播放）。
4. **完整知识视频移出本期**：资料检索、事实核查、复杂知识图解、专业图表、自动教学结构不新增专项建设。已有能力自然支持的简单解释内容可以制作，但不据此宣称完整知识视频能力上线。不设「知识视频预备批」。
5. **Chat 展示 = 交付面**：制作前的真实工具调用 = Activity 行；Start 后的真实执行 = Tasks。当前执行是单体 `launch_film`，Tasks 只显示这个真实步骤；R5 宏阶段是 PLANNED，重启合同见 `VIDEO_PROJECT.md` §4.1。无配音或复用音频时不得虚报「正在生成配音」，不为显示进度伪造准备/配音/装配步骤。最终界面验收含浏览器人工核验，不以 SSE key 与 i18n 测试替代。
6. **实施边界与状态座位**：画幅变体、声音设计期钉版与试听未实现；文字源、组合幕与编辑能力已在本地/测试门控下落地，生产默认仍关闭。当前优先级只读 `PROGRESS.md` §0；剩余能力与验收只读 `VIDEO_PROJECT.md` §0～§4；验证层级只读 `docs/tasks/video-project-implementation.md`。旧 R 批次编号与冲刺估时不再是当前计划。

**Consequences**: 文字排版/运动枚举遵守 L3 枚举纪律，不开放自由版式；字段级契约归 `VIDEO_PROJECT.md`，剩余验收与发布条件归 execution，实际验证状态归 progress。估时、旧冲刺顺序与逐轮测试数字不再充当决策条款。

**Related**: ADR-137（编辑拍——文字视频复用同一版本/编辑/复用能力）/ ADR-130（执行快照——voice_id 钉入同座）/ ADR-117（授权律——试听等待是用户明示的暂停，非新增确认拍）/ ADR-134（review hold——「先审阅」请求的覆盖语义）

## ADR-139: auto 只免批准、不创造制作意图——生产意图入 dock 出生事实 + 确认前呈现累计方案

**Status**: Decided（2026-10-22 用户拍板；现行契约 = `docs/VIDEO_PROJECT.md` §11；施工与验证状态 = `docs/tasks/video-project-implementation.md`）

**Decision**:

1. **生产意图 = dock 出生事实（code 侧唯一新 conjunct）**：每个 plan dock 在呈现时记录出生回合的用户消息是否携带制作请求——`production_intent`（三态：true / false / 未断言 None），由模型按法判断（禁关键词启发式——「按这版制作」「直接做，细节你决定」= true；「为什么这样安排」「先给我看方案」「第四幕改成……」= false；理解性提问不受影响）。auto 开工道（`_auto_start_docked_plan`）放行条件从「dock 无确认债」收窄为「**dock 无确认债 ∧ 出生回合有制作意图**」；缺意图的 dock  stamped `requires_confirmation=True, confirm_reason="awaiting_production"`—— dock 等待，Start pill 在场作常驻邀请（bare 形态，非带价），用户的制作话（口头 yes → start_run / pill / typed answer）走既有机器开工。**None 读作无意图**（读容忍取安全侧——宁可多一拍可点的等待，永不朝未证明的意图花钱）；六个 dock 工具参数族全带此字段（present_plan / propose_tasks / edit_graph / propose_plans / revise_plan / revise_selects），一条法覆盖两条 chat 路径与共享启动入口；Film 分镜设计/修订的 dock 前阶段门见第 3 条。
2. **确认前呈现 = 当前累计方案的诚实复述**：累计方案在**请求制作确认的同一消息内、问句之前**呈现（修订后的方案永不对着看不见的增量求确认）——制作确认拍（hold 等待中的呈现、awaiting_production dock 的呈现、ask 档确认拍）必须基于**当前真实草稿**复述累计状态；auto 档带制作意图的直跑道在同一消息的开工句之前携带（**同一消息，永不新增一拍**——明确委托直接制作仍直接执行，不加机械双重确认）；确认之后的开工句不再重复复述——素材与文案、画幅、总时长、幕数、配音/音乐状态、累计修改（背景/文字样式/运镜/动画）、已支持的关键时间安排、其余保持不变的范围；不要求机械四分类；Film 分镜设计/修订每轮展示系统变化摘要与当前保存版本的完整 Markdown 分镜表，其他方案可用简洁摘要加当前方案，但内容必须对应真实状态。助手建议过而用户未选的选项、尚未澄清的事项**永不**被复述为已确认（echo 防编造律同律）。用户边等边改 = 更新草稿、再呈现累计结果；版本/token 绑定（既有 `start.stale_storyboard` 409）保证旧版本确认不授权新版本。
3. **film 编辑拍授权收窄**：edit/variant 版本不新增 review hold（ADR-134 收窄不动）；「修改请求 = 授权已在场」收窄为**授权这个版本的修改本身**，不等于授权渲染。本回合 `design_storyboard` 已落新版本而 dock 参数 `production_intent` 非 `true` 时，`present_plan` / `propose_tasks` 结构性拒绝其中的 `launch_film`：完整呈现当前保存版本后走 `answer`，普通修改询问是否重制，review-only 不问开工。当前消息明确「改完直接做」= 委托在场，`true` 合法，完整呈现后进入既有提案、报价与执行道，不机械增加第二轮批准；作品首稿仍须先经过 ADR-144 的用户审阅。旧 run 完成或旧版批准不授权后续新版本。
4. **精确动画时序纳入分镜与 spec 契约（CURRENT）**：元素相对幕的开始时间 / 入场持续 / 逐字逐词间隔 / 停留至幕末语义入分镜契约与 spec 契约；最小契约与接线见总设计 §7.7，实际验证状态见 progress。

**Consequences**: ADR-117 §2「呈现即授权基础」修订为「呈现 + 出生回合制作意图 = auto 开工道的授权基础」（呈现义务不变；ask 档不变；守卫线任何档恒问不变）；ADR-134 D1「授权已在场」按本条 §3 收窄；两键设置说明文案同步修订；确认只有两个种类（执行/费用）不变——awaiting_production 不是第三种确认，它是「制作意图未在场」的事实记录，复用既有确认 dock 形态零新 chrome。口头确认律（ADR-092）仍是 ask 档法律；auto 档下用户明说「按这版制作」后不再机械追加同义确认。

**Related**: ADR-117（授权前移——本条修订其 §2）/ ADR-134（review hold 面不变，授权语义收窄）/ ADR-137（编辑拍——授权语义收窄）/ ADR-092（ask 档法律）/ ADR-089 §5（停顿定律——未证明的制作意图 = 超出常驻授权）/ ADR-060（echo 防编造——复述只述真实状态）/ ADR-129（批准 = 消费呈现版，版本绑定不变）

## ADR-140: film 组合幕（composite）——视频/图片素材元素 + 独立文字元素的最小组合结构

**Status**: Decided；现行契约 = `docs/VIDEO_PROJECT.md` §2/§6/§15；剩余实施、验收与实际状态 = `docs/tasks/video-project-implementation.md`。

**Decision**:

1. **新场景型 `composite`**：主题色背景（`dark` 两档极性）+ 有序 `elements` 列表（判别子 `kind` = video / image / text 封闭三枚举）。元素自由组合——多个独立文字元素直接叠加在主题色背景上同样合法；words 幕保留为全屏文字的便捷配方，永不是强制漏斗。场景保持叙事组织与用户定位单位，元素是幕内可定位、可编辑的组成。
2. **两个时间空间硬分离，同名字段永不换义**：`source_start`/`source_end` = 源素材秒（仅 video）；`at`/`until`/`duration` = 幕相对输出秒；`enter_*`/`motion_*` = 元素窗内相对秒。秒→帧唯一量化座（双端同一 float64 公式）。播放窗 ≤ 源区间（截尾诚实）；超长 = 拒——无变速/循环/尾帧填充/从头重播；元素离场 = 离开画面，无尾帧冻结；元素窗 ≤ 幕窗（设计时 authored 秒 + spec 构建实际帧双座复校）。
3. **空间 = 归一化 rect + fit + z**（clip-spec layers 同一坐标法），背景极性垫底，不开放任意 CSS。
4. **文字元素复用 words 平面全部时序能力**——渲染侧提取 `TextPlane` 单座组件，words 幕与 composite 文字元素同骑（tokenizer / accent chip / enter 时序 / motion）；tone（light/dark）为文字墨色两档极性。不新建字体系统、不新增第二套 tokenizer。
5. **音频三面独立**：视频原声 = 元素 `keep_audio`（默认 false，录屏不自动开声），只在元素播放窗内出现且源裁切 = 音频裁切（同一 startFrom/endAt）；旁白幕级、音乐片级（现有链）；render_probe 音轨承诺纳入 keep_audio。无声/无 ASR 视频合法可用——时长校验不依赖 transcript（在册时长 → 写座 PyAV 容器头探测 → 读座如实报未在册）。
6. **版本/编辑同链**：`element_id` 出生即铸、digest 排除（scene_id 律孪生）；新 op `update_element`（presence 敏感，kind 不适用字段具体拒）；change_set 逐元素命名字段；引用素材入执行快照漂移校验（删除/替换 = run 诚实失败，永不静默换素材）。未触碰元素/场景字节级不变由系统应用保证。
7. **出生面（现行法）**：composite 经文字源设计链出生——文字导演段词汇 = words ∪ composite（草稿元素模型无 element_id，代码出生铸造）；素材发现读 `list_project_media` 与导演 prompt 同读 `project_media_candidates` 一座；组合出生与编辑能力同骑 `film_edits_enabled` 门（声明/装配/执行三面同门）；幕长代码从元素窗派生（帧端量化同一会计，0.5s 格向上，≥1s）；web 源导演词汇仍不含 composite（patch 链完整可用，patch 无元素新增 op——诚实边界）；spike 的扁平 `video` 场景型随本决策退役（零持久化消费，无迁移）。

**Consequences**: film-spec 场景词汇 7 → 8；`_absolutize_film` 烘焙缝与 render staging 增元素 URL 座位；run_review 交付核对增元素投影比较（asset id ↔ 存储 key 规范化后比对内容字段）；clip 家族零改动；既有文字片/网页片 digest 与渲染逐字节不变（新场景型纯增量 + TextPlane 提取的结构等价回归）。Media IR 仍为 OPEN——composite 是 film 族内的最小组合结构，不是通用媒体平台。

**Related**: ADR-016（spec 契约铁律不变——零 renderer 概念）/ ADR-119（film-spec 第二家族）/ ADR-130（时序执行契约——元素窗随幕平移）/ ADR-136/137（旁白弹性与冻结时间轴对 composite 幕同律）/ ADR-138 + 总设计 §7.6（文字片——composite 文字元素共享同一文字实现）/ ADR-139 §4（精确时序——六参在元素窗内同律）

## ADR-141: Film 逐字子句粒度 / 同回合纠正道 / 带条件授权守卫 / 交付收敛

**Status**: Decided；现行契约 = `docs/VIDEO_PROJECT.md` §2/§6/§15、§11；剩余验收与实际状态 = `docs/tasks/video-project-implementation.md`。

**Decision**:

1. **引用单元 = 子句行，引用单元 ≠ 一屏**：`build_text_manifest` 改为段落 → 句子 → 子句边界每界一行（贪心打包整族删除；词原子帽切只接超帽子句）；导演**组合**连续行同屏（一段多引）或一行一屏（用户点名拆分）。逐字全覆盖校验增**顺序半边**：引用必须按文本自身顺序升序（`assemble_text_storyboard` 确定性拒乱序——更细的引用粒度使意外乱序可达，「除非用户另指顺序」的 prompt 例外随之退役）。退役旧律：「逐字引用粒度天然等于不可拆的屏幕内容」。
2. **同回合纠正道**（同回合有界纠正）：一回合 = 一次首版设计 + 有界纠正（`MAX_DESIGN_CORRECTIONS_PER_TURN=2`，准入即计）。纠正基准 = **回合内刚落版的版本**（`self.stored`——已提交世界合法地读作回合前状态）；纠正**永不二次 begin**（首版 begin 的已提交 marker 全程在位：Start 全程失败闭、并发 begin 被拒——第二次侧会话 NOWAIT 只会读到回合自己的行锁，即旧闸要防的自锁）；publish 守卫只比 committed marker 的 draft_id（patch 纠正同律跳过 committed-world 恒等检查——它对任何纠正都结构性必然误报）；纠正路径的 failure/discard **永不清 marker**（marker 属回合首版 begin，须守到回合提交）。纠正被拒（帽尽/草稿被接管）= 诚实拒文点名在场版本 + 记入回合失败台账（§3 的签名台账律）；成功落版按 §3 销账。退役旧律：「一回合成功设计一次后任何纠正必须等用户下一条消息」。重试风暴防护不变——帽在，形态从「拒绝纠正」变「有界纠正」。
3. **带条件授权守卫**：`confirmation_need` 新增 `unmet_condition` 入参 → `ConfirmationNeed(True, "unmet_condition")`（优先级：钱族之下、`awaiting_production` 之上）；四座 dock（plan_turn ×3 / propose_turn ×1）传回合失败台账是否非空；效果 = auto 直启被押（`start.needs_confirm` 同回合 conjunct），估价尾行新增诚实子句（「你刚才要的修改没能落实——确认即按当前版本开始，或先说一句继续改」）；用户**事后**明示 Start 合法（下一回合台账不在场 = 有意识的接受偏差）；「修完开工」修复真落地时同回合一拍完工、零新增确认。退役旧律：「只要钉住版本即可称为用户确认」——钉版绑定（`start.stale_storyboard`）仍是版本匹配的护栏，但它从不证明条件已满足。
   **台账形态（定点收尾①，复审两度收紧销账律）**：`_design_shortfalls` = 条目清单（`design_call_record`——``key`` = 机械签名：每 op 的「op 名 + 目标句柄 + 在场字段」（dict 字段展开一层子键；值只在值即目标身份时入键——reorder 的排列 / set_music 的 mood / set_voiceover 的开关），compose 一族同键；``target`` = 本次请求在场字段的规范化目标值 canonical JSON）。**签名与记录永不声称证明了用户目标的完成**。**记账 = 每个失败出口**（帽拒 / 过期 base_ref / 接管丢弃 / FilmEditError 回声 / gate-off 拒 / begin 被拒 / 异常路径）；**销账只有一座 = 完全等价的 patch 成功**（key **且** target 全等）——模型改用其他目标值、删掉原请求字段、或无法证明等价时失败记录全部保留（「已经呈现」≠ 用户接受）；compose 成功**永不销账**（重稿成功不证明原修改请求落实）；无法可靠证明已解决时，确认要求保留到 dock，用户看过当前方案后的明示接受（含事后明示 Start）是确认机制既有的出路。退役推断：「compose 重稿 = 重答整回合请求 → 成功即全清」「同字段签名相同 = 修复成功」。
4. **抄录漂移注记 + 原文继承守卫**：逐字重稿重述 `text` 且与 base 版本钉住文案有出入时，观察文本附 `text_source_drift_note` 的子句级诚实注记（同 manifest 切分口径点名 L 行旧/新文）——呈现永不得称「原文一字未改」；永不硬拒（用户有意改文案合法）。**注记只知情、不放行，且保护追踪「最后可证接受的文字基准」而非相邻版本差**（复审②——A→B→继承 B 洞）：漂移状态持久化在**版本封套** `film_text_drift={baseline_sha256}`（白空不敏感 digest），每次 compose/patch 落版经 `film_text_drift_next` 重算——省略 text 继承漂移文案、重述同一漂移文案、无关 patch、普通重稿**全部只延续不解除**；解除恰好三条可证路径：① 恢复原文（新钉住文案 == 基准）；② 用户本回合亲手贴出该文案（`text_drift_user_proven`）；③ copy_drift dock 的明示确认（开工消费 pending，状态随之消亡）。dock 座读**在场版本的持久状态**（`film_text_drift_held`——世界真值，回合对象重建永不丢保护）作为 `copy_drift` 押住 auto 直启（优先级：`unmet_condition` 之下、`awaiting_production` 之上；估价尾行同名诚实子句「确认即按这版开始，或说一句恢复原文」）。结构化 copy patch 不自动豁免：系统 `change_set` 的精确前后文字只证明实际差异，不证明用户授权，也不能给旧 drift 销账；完整当前保存版本是用户的审查对象。
5. **交付收敛与分支专属**：`run_completed` 骑**零读的 `delivery_agent`**（tools=[wrap_up]，max_iterations=3）与独立 `delivery_system.j2`；通用 `trigger_system.j2` 只负责 `run_failed` / `craft_decompiled`。event line 只组合对话上下文与最新工具/run 结果的 DELIVERY FACTS；`run_review` 先以代码裁决唯一 `delivery=failed|partial|delivered`，模型只叙述该分支，不再同时承担成功宣告、全量审计、卡片引导、评价与下一步。空事实块只给收据能证明的普通完成。render-contracted 的 film/clip 必须 render completed 且视频文件存在才算 delivered；失败/未就绪行不进 `landed` 提示词行或 Chat 产物卡，只有已交付 film 做确认版一致性对账。UI `page`/`shot` 选择器烘焙为 `url`/`image` 的形状差不报 drift，身份由 storyboard digest 核对。`run_failed` / `craft_decompiled` 仍骑带读 agent（失败原因与骨架缺口没有预装事实，读是诚实底座）。交付仍是有界 tool loop：拒收/修复迭代合法存在，永不宣称任何情况下绝对一次模型调用。

**Consequences**: `DesignStoryboardArgs` 仍无 `production_intent`（ADR-139：design_storyboard 不在六 dock 工具之列）——改为工具描述明说 + schema 拒收不变；prompt 面触 `film_director_text.j2`（顺序律机械化）/ `delivery_system.j2` / `trigger_system.j2`（交付与失败/骨架职责拆分）/ `turn_tools.py` 工具描述（纠正道 + 无 production_intent 一行）——prompt_gate 欠账合并；`ConfirmationNeed.reason` 词表增两员（`unmet_condition` / `copy_drift`——client pill 谓词只读 `requires_confirmation`，零前端改动）；compose 发布守卫补齐 `film_draft_inflight_live` 活性半边（与 patch 一致——双路一致性由真实隔离 PG 测试锁定：首稿→纠正→提交 / 失败 / 过期 / 接管四分支，核心事务与锁零 stub，LLM 座可 stub）；打字机律两牙不受影响（无新散文通道——drift note 骑既有观察文本座位，交付言语仍一条终态行）。

**Related**: ADR-139（§3 授权收窄——本条 §3 把「条件未满足」补进同一法律）/ ADR-129（版本绑定不变）/ ADR-117（§4 确认 conjunct 增员）/ ADR-088 §8 / ADR-135（trigger 两分：交付只写、失败仍读）/ ADR-058（世界自证——DELIVERY FACTS 即唯一合法事实源）/ ADR-060（echo 防编造——drift note 同教义）/ ADR-137（patch 链纠正道同律）

## ADR-142: 回答续聊输入耐久缝 + Film begin 拒绝锁存

**Status**: Decided；当前实现与验证状态 = `docs/VIDEO_PROJECT.md`，诊断工具留在 scratch 供复测。

**Decision**:

1. **回答续聊的输入耐久缝**：回答落定写（asset_role pins / brief-slot 回填 / 回答行）归一到单个 commit 座，在进 LLM 续聊前提交并 `refresh(project)`——续聊决策只读 committed 真值（缝释放了行锁，并发窗口存在）。当前行为：续聊失败不再回滚已回答的选项；问题保持已答，用户以普通新消息继续。
2. **begin 结构化拒绝**：`begin_film_draft` 返回 `FilmDraftBegin{draft_id, refusal}`——`in_flight`（活到已提交 marker，唯一可叙述「另一个设计进行中」）/ `locked`（行锁冲突，持有者不明，永不叙述成设计或制作）/ `gone`；非锁类 OperationalError 不再一律归为占用（begin/clear 两座同 `_is_lock_contention` 判别），真实错误类别照常抛。
3. **首 begin 拒绝锁存**：拒绝理由置 `_design_begin_refusal`；同回合重复 design 调用返回 `TerminalRefusal`（tool_loop 内核新返回形——拒绝事实照常 emit、循环当场结束、`LoopResult.ended_by` 具名），产品选择不在本回合轮询外部占用（不声称其必然无法解除）；finish 的 ended_by/耗尽两路落 `_design_blocked_text`（按拒绝原因分类的诚实文案），永不落 `_cannot_do_text`。
4. **退役法条**：「begin 拒绝后同回合等价重试落版销账」——销账座的失败例改由 publish 接管/supersede 承担（与值无关的失败座保留等价重试覆盖）。同回合纠正道、纠正帽、条件制作守卫、原文漂移保护不变。

**Consequences**: tool_loop 内核增第四返回形（TerminalRefusal——拒绝语义 + 终态控制，事件与言语撤回骑既有 ToolRejected 机制，内核事件所有权不变）；`LoopResult` 增 `ended_by`（默认 None，其他 agent 零影响）；两座三处拒绝文本收编 `design_begin_refusal_feedback` 单座；回答幂等（already_answered 409）不变——重答拦截在缝前 commit 之后仍先命中；prompt 面零改动。

**Related**: ADR-141（§2 纠正帽的适用前提补「首次拒绝锁存」；§3 台账记账新增锁存重复座）/ ADR-129 / ADR-053/108（回答结算与持久化顺序）/ ADR-141（同回合条件守卫）

## ADR-144: 作品首稿强制审阅——呈现持久化前任何 Start 均失败闭

**Status**: Decided（2026-10-25 用户拍板；现行契约 = `docs/VIDEO_PROJECT.md` §2/§8/§15；施工与验证状态 = `docs/tasks/video-project-implementation.md`）

**Decision**:

1. **作品首个分镜版本一律先审阅**：即使首条消息明确「直接做」、两个确认偏好均为 auto、或设计参数传 `review_hold=false`，首稿也只呈现并等待。提案可与首稿同回合 dock，但不得在同回合创建 run；只有呈现之后用户明说生产或点击 Start 才释放制作。此专用拍只针对 `film_storyboard_version == 1`，后续版本仍由当前制作意图、既有 hold、auto/ask、费用与版本守卫决定。
2. **呈现事实独立于 hold**：`film_presented_message_id` 是首稿已经呈现的世界事实。该 id 未持久化而 Start 已到达时，`evaluate_start_gate` 一律返回 `422 start.review_hold`；同回合 auto 与过早显式调用同法。呈现行落库后的显式 Start 是释放拍，不再被这个首稿呈现门拦住。
3. **dock 按档呈现，Start 统一发消息**：auto 无其他确认债时不显示首稿 approval dock，用户以看过后的制作话继续；ask 仍由 `execution_pref` 呈现既有 Start pill，独立价格、偏好与条件原因在任何档照常呈现。所有 Start pill 都化为普通用户消息走 sendChat，由下一轮 LLM 调 `start_run`，不由按钮直接创建 run。
4. **言语与世界状态同法**：两条意图路径及 Film family prompt 的首稿审阅措辞保持不变；auto 无 dock 不等于首稿自动开工。呈现正文仍按既有打字机律完整释放并排干，Start 消息复用 sendChat 的既有发送、恢复与结算路径。

**Consequences**: 命令式首稿的路径恒为「完整呈现并等待 → 用户看后批准 → 开工」；批准后的 auto 道不机械追加第二次同义确认。非 Film、已呈现首稿的后续批准和后续版本的既有授权路径不变。真实 Chat 停等、Start 与口头批准仍须按 progress 单独验收，纯函数绿不冒充旅程证据。

**Related**: ADR-134（首稿 review hold——本条收紧其显式逃生门对作品首稿的适用面）/ ADR-139（auto 不创造制作意图——本条另约束首稿的批准时点）/ ADR-117（确认戳与 auto Start 机器）/ ADR-129（版本化呈现与 Start 守卫）/ ADR-131（呈现行是唯一表达座）

## ADR-145: 视频编辑本体——Composition / CompositionVersion / Track·Clip·Object / Skill / video-spec

**Status**: Decided（2026-10-26 用户拍板；目标契约 = `docs/VIDEO_PROJECT.md`；四阶段施工 = `docs/tasks/video-project-implementation.md`；**未实施**）

**Decision**:

1. **Project 是 Chat/执行上下文，Composition 是持续编辑的影片身份，CompositionVersion 是不可变内容版本**。同一 Chat 可创建多部影片，通过 @asset/@output 分别修订；全局素材库支持跨 Chat 引用，服务端按 owner/权限解算，引用成片当素材与继续修改同一作品分开。Timeline 只在版本内部；不新增 Work / WorkDocument、Sequence 或独立 Timeline 根。新视频 Output.work_id 映射 Composition.id，承接既有发布/归档锚，旧 Clip/非视频语义不随之更改。
2. **Track 上是 Clip，Clip 内是 Object**。Clip 拥有输出时间窗与可选 SourceSnapshot/source_range；Object 拥有内容、布局、样式和 transform。Animation 以关键帧 + 分段 easing 作用于 Object 属性；Transition 单独表达 Clip 间关系。TextPart 是可寻址的派生对象，只有独立编辑需要时才提升为 TextClip，不默认逐字持久化。
3. **Storyboard 是 CompositionVersion 的服务端 canonical 投影**。Scene 持有可空 `visual_description`，由 LLM 描述真实画面元素与运动；精确时间、文字和旁白仍读结构。视觉修改必须更新或清空该描述，禁止旧摘要冒充新画面。呈现回执钉 `presented_message_id + presentation_digest + composition_version_id`，首稿强制审阅不变。Scene 引用 SpeechObject.text 这一份旁白原文，字幕记录派生关系，用户手改后不被旁白重生成覆盖。
4. **Skill 是版本化创作包，不是执行工具**。VideoTemplate 表达结构，Preset 表达局部参数，PromptTemplate 只做 composer 可见预填。launch-film 在新链只是内置 Skill；通用 `design_video / revise_video / produce_video` 共用 CompositionVersion、CRUD、制作和渲染。`/skill + prompt` 仍走唯一 `POST /chat`，个人保存与外部导入不执行任意脚本、不授予权限。“保存创作方法”才是 Skill；既有素材/产物通过全局 @ 引用，不建设“复制确切作品”功能。Template/Preset 在保存版本前展开，渲染编译不重新查询可变注册表。
5. **作品版本与执行图分家**。`apply_composition_edits` 是作品内容唯一写口；`apply_wiring_ops` 仍是执行图唯一写口。WorkflowRun/WorkflowStep、create_run、队列、fencing、计费、Output/render ownership 全部复用；produce 只消费钉住的 version_ref，缺版或漂移不得重新设计。内容、Start 执行输入、准备后的 execution_digest 与请求幂等按目标合同分开；默认固定切点，只允许有界语速适配，超界回到 Chat 修订，不借帧或静默截断。Graph 可先保留为隐藏血缘/修订拓扑，Canvas 可独立退役，Scene/Clip 不成为 graph nodes。
6. **video-spec 是 Film 的继任渲染契约**。它只描述量化时间、Tracks/Clips/Objects、Animations/Transitions、样式、音频和解析后素材，不含 React/Remotion/DOM/任意 CSS。RenderAdapter 与 PreviewAdapter 都必须可替换并声明能力；Remotion 商业许可或替代实现须在生产前收口。
7. **素材绑定不可变快照**。CompositionVersion 引用 SourceSnapshot 与 content digest；多轮修订不依赖聊天历史恢复素材，不因同一快照重复读取/采集，显式 refresh 才更换绑定。
8. **独立分支内破坏性替换，不迁移既有业务数据**。生产无实际用户，允许停机与本应用旧数据 reset，执行仍核对目标和 dry-run；生产就绪后合并 main。新链先做网页宣传片/MG，验收后删除旧 Film 专用实现，不建设 FilmStoryboard/film-spec 数据适配器。Clip 迁移与删除后置，完整 Scrub/Inspector 最后实施；B 先提供纯 Chat 最小预览，属性组件经统一编辑写口提交。A 内先打通最小渲染闭环，再补官网片/MG 对照；默认切换以 A+B 和生产许可门为前提，不等待个人 Skill 或完整素材库页面。B 在开发期直接替换旧 Film 专用合同，不建设兼容双链；共享可靠性机制与授权/计费/交付不变量保留。D 必须完成旧链残留、依赖、测试与文档的一轮显式删除清理和清理后旅程验收。现有 Chat 外观可保持，必要前端协议接线纳入 B，UI 改版可并行。

**Consequences**: ADR-016/119 的 clip/film 两家族仍是当前代码事实，但不再是长期视频本体上限；迁移期的 video-spec 是 Film 继任而非永久第三套架构。ADR-127 的“模型只填创意槽、代码保证结构”继续成立，但固定结构改由内置 VideoTemplate + 确定性实例化承载。ADR-140 的 composite 不作为长期特殊 Scene 类型，能力由通用 Track/Clip/Object 承接。旧 Film 任务与旧结构锁退出；现行实现查代码与 RENDERING，有效需求归 VIDEO_PROJECT §15，新施工以 ADR-145 两份合同为准，测试退役不代表新链完成。

**Related**: ADR-016（renderer-neutral spec 与黑盒）/ ADR-119（Film storyboard 与 skill 接入）/ ADR-127（固定骨架与创意槽）/ ADR-129（版本身份与执行钉版）/ ADR-137（结构化编辑与 base_ref）/ ADR-139（制作意图）/ ADR-140（组合元素）/ ADR-144（首稿审阅）
