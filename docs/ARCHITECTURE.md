# Repurposer 架构设计

## 1. 设计原则

1. **简单优先**：P0 不引入复杂框架，用纯 Python + FastAPI 手搓 Agent 工作流
2. **模块解耦**：媒体处理、智能生成、渲染层可独立替换
3. **人工反馈闭环**：每个生成步骤都支持用户反馈和局部重生成
4. **单模型策略**：核心智能层只用 MiniMax M3

## 2. 抽象架构

```
┌─────────────────────────────────────────────┐
│  前端：TanStack Start                        │
│  上传素材 / 可选或自动创建 Speaker memory / 审校结果 / 导出   │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  后端：FastAPI                               │
│  REST API / 文件上传 / 任务调度 / 状态管理   │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Agent 工作流编排器                          │
│  定义步骤顺序、状态流转、人工暂停点          │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Agent Steps（纯 Python 函数）               │
│  persona / analyze / script / review /       │
│  revise / linkedin / quote_card / translate  │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  MiniMax M3 Client                           │
│  统一封装调用、JSON 解析、重试、错误处理     │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  媒体处理层                                  │
│  语音识别 / 视频抽帧 / 文档解析 / 图片处理   │
│  声音克隆 / 语音合成 / 视频渲染 / 图形生成   │
│  配乐资源                                    │
└─────────────────────────────────────────────┘
```

## 3. Agent 工作流

### 3.1 核心 Agent

| Agent | 输入 | 输出 | 说明 |
|:---|:---|:---|:---|
| `persona` | 演讲者过往材料 | `SpeakerPersona` | 风格画像 |
| `analyzer` | 演讲稿 + persona + target_language | `ContentAnalysis` | 内容切片与评分 |
| `script` | 片段 + persona + tone + target_language | `ClipScript` | 竖屏脚本 |
| `reviser` | 脚本 + 反馈 + persona | `ClipScript` | 修正后的脚本 |
| `linkedin` | 材料/片段 + persona | `LinkedInPost` | LinkedIn 长帖 |
| `quote_card` | 材料/片段 + persona | `QuoteCards` | 金句卡文案 |
| `carousel` | 材料 + persona | `CarouselResponse` | LinkedIn 轮播长图(封面→观点→CTA) |
| `summary` | 材料 + persona | `Summary` | 多语言摘要 |
| `blog` | 材料 + persona | `BlogPost` | 博客文章 |
| `caption_translate` | 词级字幕 + target_language | `CaptionTranslation` | 字幕换语言 |

> **意图通道**:`GenerateRequest.instruction`(主页提示词)会额外传给 analyzer/script/linkedin/quote_card/carousel/summary/blog,作为"本次产出的最高优先级指令"。
> **视觉/语音**:`IMAGE` 资产经 M3 多模态(`services/vision.py`)提取要点进 materials;`POST /clips/{id}/dub` 用 MiniMax voice_clone + T2A(`services/voice.py`)做语音克隆配音。

### 3.2 生成流程

```
用户上传素材 + 输入提示词
    ↓
预处理（转写 / 解析 / 图片处理）
    ↓
Analyzer Agent → 内容切片 + 传播潜力评分
    ↓
从任务输入中提取 / 更新 Speaker memory（可选；若用户未选 Speaker，则自动创建）
    ↓
对每个高潜片段：
    Script Agent → 初稿（带 Speaker memory 风格约束）
    Review Agent → 评分
    如果未通过：
        Reviser Agent → 修正
    重复最多 2 次
    ↓
LinkedIn Agent / Quote Card Agent → 衍生内容
    ↓
保存结果，等待用户审校
    ↓
用户反馈 → Reviser Agent → 局部重生成
```

> **与当前实现的差异**：现有代码仍有一个独立的 `persona` Agent，它从 Speaker 上传的"过往材料"中生成 `SpeakerPersona`。按 ADR-021 的目标方向，这个流程正在被重构为"任务输入直接提取 memory 并持久化为 Speaker"。在重构完成前，代码里会暂时并存两种形态。

### 3.3 人工反馈循环

用户反馈必须结构化：

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

## 4. 数据流

```
用户上传
    ↓
FastAPI 接收文件 → 本地文件系统
    ↓
写入 PostgreSQL：创建 Asset(processing_status=PENDING)
    ↓
worker 进程认领并执行：
    - 文本/PDF → 提取
    - 视频/音频 → ASR（词级时间戳）
    ↓
用户触发 Generate → 创建 WorkflowRun(status=PENDING)
    ↓
worker 认领 WorkflowRun，按顺序调用 Agent：
    analyzer → script → linkedin / quote_card / summary / blog
    ↓
生成 clip-spec（含品牌、配乐）保存到 Clip.render_spec
    ↓
WorkflowRun 状态更新为 completed
    ↓
TanStack Start 前端：用户审校 / 编辑 / 导出
    ↓
渲染触发 → Clip.render_status=PENDING → worker 调 Remotion 渲染服务
    ↓
导出 MP4 + SRT
```

## 5. 代码结构

```
apps/api/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置管理
│   ├── dependencies.py      # 依赖注入
│   ├── worker.py            # 独立 worker 进程入口
│   ├── routers/             # API 路由
│   │   ├── speakers.py
│   │   ├── projects.py      # 含生成、导出、jobs、clips、derivatives
│   │   ├── assets.py
│   │   ├── clips.py         # 审校、渲染触发、字幕翻译
│   │   ├── derivatives.py
│   │   ├── files.py         # Range 流式端点（uploads/outputs/music）
│   │   └── brand_templates.py
│   ├── services/            # 业务逻辑
│   │   ├── jobs.py          # 队列认领
│   │   ├── asset_processing.py   # 处理派发：ASR / 文本提取 / 幻灯片渲页 / 图片视觉
│   │   ├── generation.py    # 生成流程编排
│   │   ├── rendering.py     # 调用 Remotion 渲染服务
│   │   ├── clip_spec.py     # clip-spec 构建
│   │   ├── brand.py         # 品牌模板 → ClipBrand/ClipMusic + 默认种子
│   │   ├── extraction.py    # 文本/PDF 提取 + PyMuPDF 逐页渲图
│   │   ├── vision.py        # M3 视觉:图片 → 要点文本
│   │   ├── voice.py         # 语音克隆 + T2A 合成 + 视频抽音轨
│   │   ├── caption_translate.py  # 字幕轨翻译
│   │   ├── storage.py       # 存储 seam
│   │   └── asr.py           # faster-whisper
│   ├── models/              # 数据库模型 + Pydantic schemas
│   │   ├── database.py
│   │   ├── schemas.py
│   │   └── tables.py
│   ├── agents/              # Agent steps
│   │   ├── persona.py
│   │   ├── analyzer.py
│   │   ├── script.py
│   │   ├── reviser.py
│   │   ├── linkedin.py
│   │   ├── quote_card.py
│   │   ├── carousel.py
│   │   ├── summary.py
│   │   ├── blog.py
│   │   └── caption_translate.py
│   ├── prompts/             # Jinja2 模板
│   └── clients/
│       └── minimax.py       # MiniMax M3 封装
├── migrations/              # Alembic 迁移脚本
├── pyproject.toml
└── Dockerfile

apps/web/                    # TanStack Start 前端
apps/render/                 # Remotion 渲染服务（Node）
packages/clip/               # 共享 <Clip> + clip-spec TS 类型
pnpm-workspace.yaml          # web/render/clip
```

## 6. 状态管理

### 6.1 Workflow Run

记录一次生成任务的完整生命周期：

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

`Asset` 自带处理状态机：

```python
class AssetStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
```

- 上传后 API 立即返回 `PENDING`，由 worker 认领处理。
- `processing_error` 保存失败原因，前端可重试。

### 6.3 Clip Render Status

```python
class RenderStatus(StrEnum):
    PENDING = "pending"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"
```

- `Clip.render_status` 是 worker 的第三个认领源。
- `Clip.render_spec` 保存 clip-spec 契约，`video_url` / `srt_url` 保存成片产物。

## 7. 关键设计决策

- **不用 Turborepo/Nx/Pants**：前后端独立管理，简单目录结构即可
- **手搓 Agent**：单模型、固定 workflow，框架抽象价值不大
- **Pydantic 强类型**：所有 Agent 输入输出都用 Pydantic model
- **结构化反馈**：用户反馈必须选择原因，不能只有自由文本
- **版本历史**：每次重生成保存旧版本，支持对比和回滚

## 8. 扩展点

| 未来需求 | 扩展方式 |
|:---|:---|
| 接入第二个模型 | 新增 `clients/openai.py`，在 `minimax.py` 同级抽象 LLMClient 接口 |
| 多语言扩展 | 新增 `translator.py` 支持更多目标语言 |
| 复杂 workflow | P2 评估 LangGraph 或 Pydantic AI |
| 团队协作 | 新增 `organizations` / `members` 表和权限中间件 |
| 社媒直接发布 | 新增 `routers/publish.py` 调用平台 API |

## 9. 任务队列（已实施，ADR-017）

耗时任务（ASR、视频渲染、生成）不跑在 API 进程，改由独立 worker 进程处理。**用 Postgres 当队列，不上 Redis。**

```
┌──────────┐  上传/生成 创建 pending 行  ┌─────────────┐
│ FastAPI   │ ─────────────────────────► │ PostgreSQL   │
│ (API 进程) │                            │ Asset/Run 行 │
└──────────┘                            └──────┬──────┘
                                               │ FOR UPDATE SKIP LOCKED 认领
┌──────────────────────┐                       ▼
│ worker 进程           │ ◄─────────────────────┘
│ python -m app.worker  │  process_asset / run_generation
│ 与 API 物理隔离        │  失败落 *_error，循环不崩
└──────────────────────┘
```

- `app/services/jobs.py`：`claim_pending_*`（原子认领）+ `reap_stale`（启动重置孤儿任务）。
- `app/services/asset_processing.py`：按 `AssetType` 分发的 processor——**ASR/OCR/视频渲染未来的接入点**。
- 将来横向扩展再把认领换成 arq/Celery + Redis，调用方不变。

## 10. 视频编辑与渲染架构（ADR-016，详见 VIDEO_EDITOR.md）

「竖屏短片成片 + 可编辑」是 MVP 主流程。架构核心 = **钉死一份声明式 `clip-spec(JSON)` 契约，渲染器是契约背后的可替换黑盒**。

```
clip-spec(JSON)  ← 永久契约（渲染器无关）
     │
     ├──► 预览：Remotion <Player>（浏览器实时渲染，编辑器画布）
     └──► 出片：Remotion 渲染服务(Node, 无头 Chrome + 内部 FFmpeg)
              └─ Python 队列(§9)经 HTTP 触发 → MP4 + SRT
```

- **第一个渲染器 = Remotion**（服务端），当 `spec→MP4+SRT` 黑盒；pnpm 启动。
- **品类 = OpusClip 类**（服务端流水线 + 瘦编辑面 + 甩剪映精剪），编辑形态抄 Descript（文字稿编辑 / 删句=剪段非破坏性 / 单轨 trim），**不做多轨 NLE / 图层 / 特效 / 客户端引擎**。
- **品牌进渲染**：API 在生成时从 `BrandTemplate` 解析出 `ClipBrand`（logo/CTA/字幕色/字号/字体/fill/片头尾）**烘焙进 `render_spec`**，渲染服务只读 spec、不读 DB，保证 parity。
- **配乐进渲染**：`BrandTemplate.musicMood` → `ClipMusic.url`（内置 mood 曲库 `/api/v1/music/<mood>`）→ Remotion `<Audio>` 循环混音。
- **硬前置**：多语 ASR（词级时间戳）+ 可流式播放/seek 的视频（**本地 FS + Range 端点即可**；对象存储留到规模化，ADR-011）。
- **低后悔**：spec 稳定，将来可换手搓 FFmpeg（+ 两端共享 libass）或客户端 WebCodecs，契约不变。
