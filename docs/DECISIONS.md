# 架构决策记录（ADR）

## ADR-001：使用单仓库简单目录结构

**状态**：已决策

**背景**：需要同时管理 Python 后端和 Node.js 前端。

**决策**：使用单仓库，前后端分目录，不引入 Turborepo/Nx/Pants 等 monorepo 工具。

```
repurposer/
├── apps/api/
├── apps/web/
├── docs/
└── scripts/
```

**原因**：
- P0 阶段前后端交互简单，没有大量共享代码
- 各用各的包管理器（uv / pnpm），互不干扰
- 用 `Justfile` 或 `scripts/dev.sh` 协调启动即可
- 避免引入不必要的工具学习成本

**替代方案**：
- Turborepo：不适合 Python
- Nx：不是 Python 原生
- Pants/Bazel：太重
- 多仓库：不方便同步改动

---

## ADR-002：后端使用 FastAPI

**状态**：已决策

**决策**：后端使用 FastAPI。

**原因**：
- 自动生成 OpenAPI 文档
- 原生支持 Pydantic，适合结构化输出
- 异步性能优秀
- 团队熟悉

---

## ADR-003：核心智能层使用 MiniMax M3

**状态**：已决策

**决策**：核心 LLM 使用 MiniMax M3。

**原因**：
- 1M 上下文，可吞入演讲稿 + 过往材料 + 示例
- 原生多模态，可处理图片
- 支持结构化输出
- 国内访问稳定

**风险**：
- 如果输出质量不稳定，可能需要 fallback 到其他模型

---

## ADR-004：手搓 Agent 工作流

**状态**：已决策

**决策**：P0 不引入 Pydantic AI / LangGraph / CrewAI 等 Agent 框架，自研 Agent 编排器。

**原因**：
- 单模型（MiniMax M3），不需要 provider 抽象
- Workflow 明确固定：persona → analyze → script → review → revise → HITL
- Prompt 需要精细控制，框架模板可能不够灵活
- 白盒调试更方便

**未来**：如果 P2 workflow 变得非常复杂，再评估 LangGraph 或 Pydantic AI。

---

## ADR-005：Python 包管理使用 uv

**状态**：已决策

**决策**：Python 项目使用 uv 作为包管理器。

**原因**：
- 速度快
- 现代 Python 工作流（lock 文件、venv、run 一体化）
- 适合新项目

---

## ADR-006：前端使用 TanStack Start + TypeScript

**状态**：已决策

**背景**：P0 是内部验证，但未来目标是 SaaS 产品，需要为产品化打好基础。

**决策**：前端使用 TanStack Start + TypeScript。

**原因**：
- 部署平台无关，不绑定 Vercel
- 端到端类型安全强
- 显式服务端/客户端边界，减少 hydration 和密钥泄漏问题
- 为未来 SaaS 产品化做准备

**风险**：
- 框架较新，生态比 Next.js 小
- 团队学习成本
- AI 编码工具对 TanStack Start 支持较弱

**缓解**：
- P0 功能简单，用不到复杂特性
- 文档完善，核心概念清晰

---

## ADR-007：API 类型同步使用 OpenAPI

**状态**：已决策

**决策**：前后端不维护共享类型包，前端类型从后端 OpenAPI 生成。

**原因**：
- 减少共享包维护成本
- 后端是类型权威来源
- 使用 `openapi-typescript` 自动生成

---

## ADR-008：视频渲染先用图片轮播 + 字幕

**状态**：已决策

**决策**：P0 视频渲染不追求复杂剪辑，先用图片轮播 + 字幕 + BGM 的形式。

**原因**：
- 快速验证内容生成质量
- 降低渲染复杂度
- 后续可替换为更复杂的视频引擎

---

## ADR-009：声音克隆 P1 再做

**状态**：已决策

**决策**：P0 使用通用 TTS，P1 再接入声音克隆。

**原因**：
- P0 先验证脚本和内容质量
- 声音克隆涉及授权、效果评估等额外问题
- 通用 TTS 已能满足 demo 需求

---

## ADR-010：数据库使用 PostgreSQL

**状态**：已决策

**决策**：P0 使用 PostgreSQL 作为数据库。

**原因**：
- 未来目标是 SaaS，PostgreSQL 是生产级选择
- 比 SQLite 更适合多用户、并发、数据完整性
- 团队熟悉，生态成熟
- Docker Compose 本地启动简单

**替代方案**：
- SQLite：部署更简单，但扩展性差

---

## ADR-011：文件存储使用本地文件系统

**状态**：已决策

**决策**：P0 上传文件存储在本地文件系统。

**原因**：
- P0 是内部验证，本地存储零成本
- 文件路径抽象一层后，P1 可无缝迁移到对象存储
- 部署简单，无需配置云存储

**未来**：P1 评估 MinIO / 阿里云 OSS / AWS S3。

---

## ADR-012：P0 是内部验证工具，未来目标 SaaS

**状态**：已决策

**背景**：需要明确 P0 的定位，以指导技术选型和功能范围。

**决策**：P0 先作为内部工具跑通核心 workflow，但技术选型为未来 SaaS 化做准备。

**影响**：
- 前端选 TanStack Start 而不是 Streamlit
- 数据库选 PostgreSQL 而不是 SQLite
- 代码结构考虑多用户、权限扩展
- P0 不实现计费、多租户，但预留扩展空间

---

## 待决策事项

| 事项 | 建议 | 决策者 |
|:---|:---|:---|
| 产品名称 | 待定 | 左总 |
| 任务队列 | 纯 asyncio（P0 足够） | 技术 |
| 语音识别 | P0 不做，P1 评估 FunASR / 讯飞听见 | 技术 |
| 视频渲染引擎 | MoviePy + FFmpeg | 技术 |
| 语音合成服务 | P0 不做，P1 评估 MiniMax TTS / 科大讯飞 | 技术 |
| 配乐资源 | Uppbeat / Artlist | 产品/技术 |
| 是否支持 URL 输入 | 本期不做 | 产品 |
| 首期支持语言 | 中英双语 | 产品 |
| 付费模式 | 本期不设计 | 左总 |

## ADR-013：国际化、主题切换与欧洲市场定位

**状态**：已决策

**背景**：Repurposer 面向欧洲知识型演讲市场，同时需要支持明暗主题切换和欧洲机构的合规诉求。

**决策**：
1. 前端使用 `i18next` + `react-i18next` 实现国际化。
2. **默认语言为英文**；用户选择写入 `repurposer-lang` cookie，刷新后由客户端恢复。
3. **默认主题为暗色**；用户手动切换后写入 `localStorage`。`system` 偏好也按暗色处理。
4. 主题切换使用 View Transition API，从点击位置做圆形扩散揭开动画。
5. 所有图标统一使用 `lucide-react`。
6. **产品定位从“viral 短视频”转向“知识资产化”**：核心输出是 LinkedIn 长帖、金句卡、多语言摘要、Newsletter 等，目标用户为学术/企业峰会演讲者与研究机构。
7. **多语言输出是欧洲市场入场门票**：除界面语言外，内容生成需覆盖 FR/DE/ES/IT 等欧洲主流语言。
8. **GDPR / EU 数据驻留作为销售卖点**：通过 Cast AI Kimchi 的 M3 EU 部署能力，提供可选的 EU 数据处理，满足欧洲机构采购门槛。

**原因**：
- `i18next` 成熟、类型可约束，适合本项目规模。
- SSR 场景下，首屏固定英文 + 客户端恢复 cookie 可以避免 hydration 不匹配。
- `localStorage` + anti-FOUC inline script 能避免主题闪烁。
- View Transition API 在 Chromium/Safari 提供原生流畅动画，Firefox 自动降级。
- 统一图标库避免风格混乱和手动维护 SVG。
- 欧洲知识型演讲市场是 OpusClip/Descript 覆盖不足的空白；LinkedIn 是 B2B 知识传播核心阵地；多语言和 GDPR 合规是硬性门槛。
- Agent 驱动的 Analyzer → Script → Review → Reviser → HITL 闭环满足欧洲用户对内容质量和可控性的高要求。

**约束与注意事项**：
- shadcn 组件基于 base-ui，触发器使用 `render` prop 而非 `asChild`。
- 新增用户文案必须同时更新 `zh.ts` 和 `en.ts`，保持键结构一致。
- 浏览器 API（`localStorage`、`matchMedia`、`document.startViewTransition`）必须放在客户端代码路径中。
- 前端文案、示例、工具网格避免使用“抖音/TikTok/爆款/viral”等面向 C 端娱乐短视频的描述。

**相关文件**：
- `apps/web/src/lib/i18n/`
- `apps/web/src/lib/theme/ThemeProvider.tsx`
- `apps/web/src/components/language-switcher.tsx`
- `apps/web/src/components/theme-toggle.tsx`
- `apps/web/src/routes/__root.tsx`
- `apps/web/src/routes/index.tsx`
- `CLAUDE.md`
- `.claude/projects/-Users-sylas-repurposer/memory/europe-strategy-positioning.md`

## ADR-014：Sidebar 参考 OpusClip 布局与 Brand Template 页面

**状态**：已决策

**背景**：随着导航项增加（Home、Projects、Speakers、Library、Brand template），首页顶部 bar 承载过多全局操作；同时用户希望复用 OpusClip 的 sidebar 交互与 Brand template 配置页面。

**决策**：
1. 采用左侧可折叠 icon sidebar（`shadcn/ui Sidebar collapsible="icon"`），参考 OpusClip 的隐藏/展开交互。
2. Sidebar 顶部放置 workspace logo、折叠按钮和用户头像下拉菜单；下拉菜单已简化为 Profile / Settings / Logout，去除 OpusClip 中过多的业务项。
3. Sidebar 中间按 `Create`（Home、Projects、Speakers）和 `Post`（Library、Brand template）分组导航。
4. 新增 `/brand-template` 页面：左侧设置面板（字体、主色、强调色、Logo、默认 CTA、语言调性），右侧实时预览 quote card 与 LinkedIn post 样例。
5. 新增 i18n key：`nav.create`、`nav.post`、`nav.brandTemplate`、`brandTemplate.*`、`common.profile/settings/logout/helpCenter/inviteMembers/freePlan/new`。

**原因**：
- 把全局导航从首页内容区抽离，首页能更聚焦在 prompt 输入和知识资产工具网格。
- Brand template 是知识资产化 SaaS 的核心配置入口，方便用户统一控制输出风格。
- OpusClip 的 sidebar 模式在视频/内容创作工具中已被验证，用户学习成本低。

**约束与注意事项**：
- 继续使用 base-ui 的 `render` prop，不用 `asChild`。
- 新增 sidebar 入口必须同步更新 `zh.ts`/`en.ts` 的 `nav.*` key。
- Brand template 当前为前端 mock 预览，后续需对接后端 `BrandTemplate` 配置表。

**相关文件**：
- `apps/web/src/components/app-sidebar.tsx`
- `apps/web/src/routes/brand-template.tsx`
- `apps/web/src/routes/index.tsx`
- `apps/web/src/lib/i18n/locales/zh.ts`
- `apps/web/src/lib/i18n/locales/en.ts`
- `CLAUDE.md`
- `.claude/projects/-Users-sylas-repurposer/memory/repurposer-sidebar-opusclip-reference.md`

## ADR-015：ORM 用 SQLAlchemy，迁移工具使用 Alembic

**状态**：已实施

**背景**：后端已使用 SQLAlchemy 2.0（`[asyncio]` + asyncpg）作为 ORM。早期使用启动时 `Base.metadata.create_all()` 建表，但随着功能演进，需要修改已有表的列约束（例如 `projects.speaker_id` 改为 nullable），`create_all` 无法处理这类变更。

**决策**：
1. **不更换 ORM**：SQLAlchemy 2.0 async 已是正确选择，不评估替代品。
2. **不为风格批量重写**：现有旧式 `Column(...)` 不重写成 2.0 的 `mapped_column`/`Mapped[]`/`relationship`（纯类型提示改进，不影响功能）；新表可酌情用新写法，但不强制。
3. **使用 Alembic 管理 schema 变更**：已初始化 `alembic.ini`、`migrations/env.py` 和 `migrations/versions/`。
4. **应用启动时自动迁移**：`app/models/database.py` 的 `init_db()` 在 lifespan 中调用 `alembic.command.upgrade(..., "head")`，确保新环境或 CI 自动同步到最新 schema。
5. **Alembic env.py 使用同步驱动**：主应用继续使用 `postgresql+asyncpg`，Alembic 迁移使用 `postgresql+psycopg2`，避免在已有 uvloop 事件循环中调用 `asyncio.run()` 的问题。

**迁移工作流**：

```bash
cd apps/api

# 应用迁移
uv run alembic upgrade head

# 查看当前版本
uv run alembic current

# 修改 models 后生成新迁移
uv run alembic revision --autogenerate -m "describe change"

# 回滚一级
uv run alembic downgrade -1
```

**原因 / 注意**：
- `create_all` **只建缺失的表，不会修改已存在表的列**——给已有表加列/改约束时它静默无效，模型与库会不一致并在运行时报错。
- 自动迁移适合本地开发和简单部署；生产环境建议在部署流程中显式执行 `alembic upgrade head`，而不是依赖应用启动时的自动迁移。
- 生成迁移后务必人工检查生成的脚本，autogenerate 不是 100% 准确（例如 enum、复杂约束可能需要手动调整）。

**相关文件**：
- `apps/api/alembic.ini`
- `apps/api/migrations/env.py`
- `apps/api/migrations/versions/`
- `apps/api/app/models/database.py`（`init_db`）
- `apps/api/app/models/tables.py`
- `apps/api/pyproject.toml`

## ADR-016：竖屏短片编辑器——钉死 clip-spec 契约，Remotion 作为第一渲染器（可替换黑盒）

**状态**：已决策（详细设计见 [VIDEO_EDITOR.md](./VIDEO_EDITOR.md)）

**背景**：「竖屏短片成片」确定为 MVP 必须项，且必须可编辑。需要在"自研 FFmpeg / Remotion / CapCut Web 客户端引擎"之间定型，并明确编辑能做到什么级别。

**决策**：
1. **钉死唯一契约：声明式 `clip-spec(JSON)`**（渲染器无关，只描述"是什么"：segment 列表 / 裁切 / 字幕轨 / 样式预设 / 标题 / 配乐 / 品牌）。渲染器是契约背后的**可替换实现**。
2. **第一个渲染器用 Remotion**（服务端，无头 Chrome + 内部 FFmpeg），当作 `spec→MP4+SRT` 的**黑盒**；Node 渲染服务用 pnpm 启动、自托管 EU，由现有 Python 队列触发。
3. **品类定位 = OpusClip 类**（服务端流水线 + 浏览器瘦编辑面 + 甩剪映精剪），**不做 CapCut Web 客户端引擎**。
4. **编辑形态 = Descript 式文档编辑**：文字稿编辑（删句=剪段，非破坏性可恢复）+ 词↔时间码 + **单轨 trim**；**不做多轨 NLE / 图层合成 / 转场特效 / B-roll 库 / 自动人脸追踪**（L3，甩下游）。
5. **样式限定在预设枚举**（CSS 与 libass 都能表达），保证"预览=成片"且保留将来换手搓 FFmpeg 的低成本。
6. **ASR（词级时间戳）从可选 P1 升级为硬前置**；视频需**可流式播放/seek**（本地文件系统 + FastAPI Range 端点即可，**对象存储非必需**，按 ADR-011 留到规模化）。没有 ASR + 可播放视频，编辑器搭不起来。

**原因**：
- 我们的任务是"处理已有素材"，编辑需求最高只到"裁段+字幕+样式"，够不到多轨 NLE；自研 WASM 引擎是给不存在的需求付几年工程。
- Remotion 让 parity（预览=成片）结构上天然成立、媒体脏活成熟、`<Player>` 直接当预览、契合 React 栈——对小团队是更快到精致 MVP 的路径。
- 因为契约稳定，**低后悔**：将来账单/规模有压力可换手搓 FFmpeg（clip-spec→filtergraph + 两端共享 libass）或客户端 WebCodecs，spec 不动。

**代价 / 注意**：
- 引入一个 Node 渲染服务（多语言栈，但边界是干净黑盒）+ Remotion license（4+ 人 $25/seat 或 $0.01/render）。
- "无头 Chrome 逐帧渲处理任务"较重，但 MVP 规模（短片）无碍，高量再优化或换手搓。
- Python 没有 Remotion 等价物（web-tech parity 范式绑死 JS/浏览器）：要 parity 就接受 Node；坚持纯 Python 则落到 ffmpeg-python + 共享 libass 手搓（另一个范式）。

**相关文件**：
- `docs/VIDEO_EDITOR.md`
- `apps/api/app/models/tables.py`（`Clip` 加 `render_spec/render_status/render_error/srt_url`）
- `apps/api/app/worker.py`、`apps/api/app/services/jobs.py`（渲染认领源）
- `.claude/projects/-Users-sylas-repurposer/memory/repurposer-video-editing-direction.md`

## ADR-017：Postgres 当任务队列（不上 Redis），独立 worker 进程

**状态**：已实施

**背景**：ASR、视频渲染等是耗时重活；原先生成跑在 FastAPI `BackgroundTasks`（进程内、重启即丢、无重试、无并发控制），素材上传是同步阻塞。需要可靠的异步执行层。

**决策**：
1. **用 Postgres `FOR UPDATE SKIP LOCKED` 把数据库当队列**，**不引入 Redis/Celery**（符合 ADR-001 简单优先；将来横向扩展再换 arq/Celery 是一处替换）。
2. 独立 **worker 进程**（`python -m app.worker`）轮询认领 `Asset`（待处理）和 `WorkflowRun`（待生成），与 API 进程物理隔离；启动 `reap_stale` 重置孤儿任务。
3. `Asset` 加 `processing_status`(pending/processing/completed/failed) + `processing_error`；上传改为落盘即返回 pending，前端轮询。
4. `app/services/asset_processing.py` 按类型分发 processor——**ASR/OCR 未来唯一接入点**（现 video/audio 为 no-op）。
5. 生成统一走 `/generate` 的 outputs 多选（clips/linkedin/quote_cards/summary/blog），删除原先 4 个重复的同步生成端点。

**原因**：
- 内部验证阶段（ADR-012）的吞吐/规模还用不到 Redis；DB 当队列零新增中间件。
- worker 进程隔离让重活不拖在线请求；`SKIP LOCKED` 支持多 worker 安全并发。

**相关文件**：
- `apps/api/app/worker.py`、`apps/api/app/services/jobs.py`、`apps/api/app/services/asset_processing.py`
- `apps/api/app/models/tables.py`（`Asset.processing_status`）
- `scripts/dev.sh`、`docker-compose.yml`（worker 进程，无 redis）
- `.claude/projects/-Users-sylas-repurposer/memory/repurposer-queue-foundation.md`

## ADR-018：渲染服务独立为 apps/render + 共享 packages/clip + pnpm workspace

**状态**：已实施

**背景**：Remotion 的 parity（预览=成片）要求 `<Clip>` 组件被 web 的 `<Player>`（预览）和渲染服务的 `renderMedia`（出片）**共用同一份**。需要决定渲染服务和这份共享组件放在仓库哪里，且不破坏 ADR-001 的运行时隔离。

**决策**：
1. **渲染服务独立为 `apps/render/`**（Node/pnpm，`@remotion/bundler` + `@remotion/renderer` + express），对外是 `POST /render: spec→MP4+SRT` 黑盒。**不放 `apps/api/` 下**（api 是 Python/uv，混运行时违反 ADR-001）。
2. **`<Clip>` 组件 + clip-spec TS 类型抽到 `packages/clip/`** 共享包（`@repurposer/clip`），web 和 render 都 import。
3. **用轻量 pnpm workspace**（`pnpm-workspace.yaml` 含 `apps/web`/`apps/render`/`packages/*`）串起三个 TS 包；**`apps/api` 独立用 uv，不进 workspace**。
4. `onlyBuiltDependencies` 从 `apps/web` 移到 workspace 根。

**原因**：
- parity 要求组件共享 —— 这是选 Remotion 的全部理由，不能两边各写一份。
- pnpm workspace 是**最轻的共享机制**（一个 yaml），不是 ADR-001 反对的 Turborepo/Nx/Bazel；这是对 ADR-001「无共享代码」前提的合理演进（现在确实有一份必须共享的 `<Clip>`）。
- api 保持 Python/uv 完全隔离。

**约束与注意**：
- render 的 `spec.source.url` 必须是**绝对 URL**（api worker 调用前把存储 seam 的相对 URL 绝对化）。
- render 把 MP4/SRT 写到共享 `data/outputs`，api 经 Range 端点服务（存储 seam）。
- 首次渲染 Remotion 会下载无头 Chromium（约几百 MB）；个别原生依赖的 build script 可能需 `pnpm approve-builds`。
- `<Clip>` MVP 渲染首个 kept 段；多段 concat（文字稿删句产生间隔）已实施。
- 品牌（logo/CTA/字幕色/字号/字体/fill/片头尾）与配乐以已解析值**烘焙进 `render_spec`**，`<Clip>` 消费 `spec.brand` / `spec.music`；渲染服务不读 DB。
- 字幕字体使用 `@remotion/google-fonts`（拉丁子集），首次渲染从 Google CDN 拉取；离线场景未来可换 `@remotion/fonts` 本地 woff2。

**相关文件**：
- `apps/render/`（`src/server.ts`/`render.ts`/`srt.ts`）、`packages/clip/`（`src/Clip.tsx`/`Root.tsx`/`types.ts`/`fonts.ts`）
- `pnpm-workspace.yaml`、`scripts/dev.sh`、`README.md`、`docs/VIDEO_EDITOR.md` §6

**容器化（补充）**：
- 全栈 5 服务都有 Dockerfile：`api`（uv，装 `libgomp1` 给 ctranslate2）、`worker`（复用 api 镜像换 `command`）、`render`、`web`。
- **`render` / `web` 的构建上下文是仓库根**——它们 import workspace 包 `@repurposer/clip`，子目录上下文拿不到 `pnpm-workspace.yaml` / `pnpm-lock.yaml` / `packages/clip`。Dockerfile 先 COPY 各 workspace 的 `package.json`（pnpm 解析整图所需）+ lockfile 装依赖，再 COPY 源码，最大化层缓存。
- `render` 镜像装无头 Chromium 的系统库（libnss3/libatk/libgbm/字体等）；Chromium 二进制在**首次渲染时惰性下载**（不在构建期拉，避免构建依赖外网、在 CI/受限网络上挂起；render 服务运行时本就有外网用于回拉源视频）。生产可在 Remotion 下载目录挂缓存卷避免重启重下。
- 容器内服务名互联：`API_PUBLIC_URL=http://api:8000`、`RENDER_URL=http://render:3001/render`（覆盖 `config.py` 里的 localhost 默认）。render 写共享卷 `./data/outputs`，api 经 Range 端点服务。
- **`web` 用 `vite preview` 起 SSR**：MVP/staging 够用；高流量再换围绕导出 fetch handler（`dist/server/server.js`）的轻量 node http 适配层。该 SSR 路径已通过镜像构建与单帧渲染冒烟验证。

## ADR-019：配乐用内置 mood 曲库（用户供曲）

**状态**：已实施

**背景**：clip-spec 有 `music` 块，品牌模板有 `musicMood`，但缺"曲从哪来"。涉及版权，不能由 AI 自动抓取无授权音乐。

**决策**：
1. **内置 mood 曲库**：`data/music/<mood>.<ext>`（支持 `.mp3/.m4a/.aac/.ogg/.wav`），用户/运营提供授权曲目。
2. **按 mood 路由**：`GET /api/v1/music/<mood>` 扩展名无关，resolver 按 stem 找文件；带 Range 支持。
3. **生成时烘焙**：`services/brand.py:music_from_template` 把 `BrandTemplate.musicMood` → `ClipMusic{track_id, url}`；`ClipMusic.enabled` 受 `musicEnabled` 控制。
4. **渲染混音**：Remotion `<Audio src={url} volume={dbToLinear(gain_db)} loop>`。

**原因**：
- 不引入第三方音乐 API/订阅，零新增依赖与费用。
- 版权责任清晰：用户/运营只放已授权曲目；仓库不打包音乐。
- 曲库可随运营扩展：加文件即可，无需改代码。

**相关文件**：
- `apps/api/app/services/storage.py`（`resolve_music_safe` / `music_url`）
- `apps/api/app/routers/files.py`（`/music/{mood}`）
- `apps/api/app/services/brand.py`（`music_from_template`）
- `packages/clip/src/Clip.tsx`（`<Audio>`）
- `data/music/README.md`
