# API 规范

> 状态：Draft，随开发迭代更新。

## 1. 基础信息

- **Base URL**：`http://localhost:8000`
- **API Prefix**：`/api/v1`
- **Content-Type**：`application/json`
- **认证**：本期暂不实现，后续通过 JWT 或 session

## 2. 文件流式

上传源视频、渲染成片、内置配乐均通过支持 HTTP Range 的端点，供浏览器播放 / seek / 渲染服务拉取：

```http
GET /api/v1/files/{file_path}
GET /api/v1/outputs/{file_path}
GET /api/v1/music/{mood}        # 内置 mood 曲库，如 calm / uplifting / corporate
```

## 3. 错误格式

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Project not found",
    "detail": {}
  }
}
```

## 3. Speaker 管理

> **演进说明**：Speaker API 正在按 ADR-021 重构。目标方向是：Speaker 按用户隔离、创建项目时 `speaker_id` 可选、未选择时系统自动创建。当前以下端点仍保留手动创建和过往材料生成 persona 的形态，后续会逐步收敛到 auto/manual 统一的 memory 模型。

### 创建 Speaker

```http
POST /api/v1/speakers
```

Request:

```json
{
  "name": "熊榆",
  "title": "萨里大学协理副校长",
  "language": "zh",
  "avatar_url": null
}
```

Response:

```json
{
  "id": "uuid",
  "name": "熊榆",
  "title": "萨里大学协理副校长",
  "language": "zh",
  "persona": null,
  "created_at": "2026-06-22T10:00:00Z"
}
```

### 获取 Speaker 列表

```http
GET /api/v1/speakers
```

### 获取 Speaker 详情

```http
GET /api/v1/speakers/{speaker_id}
```

### 更新 Speaker

```http
PUT /api/v1/speakers/{speaker_id}
```

### 上传 Speaker 过往材料

```http
POST /api/v1/speakers/{speaker_id}/materials
Content-Type: multipart/form-data
```

Fields:

- `file`: 文件
- `type`: `book` | `article` | `speech` | `social_media`

### 生成/更新 Speaker 风格画像

```http
POST /api/v1/speakers/{speaker_id}/persona/generate
```

Response:

```json
{
  "core_values": ["人类尊严", "技术校准"],
  "favorite_metaphors": ["火"],
  "sentence_style": "理性、善用类比",
  "emotional_tone": "理性",
  "typical_hooks": ["关键不再是...而是..."],
  "avoid_words": []
}
```

## 4. 项目管理

> **演进说明**：创建项目时的 `speaker_id` 计划改为可选。未选择时，系统会在任务处理完成后自动创建一条 Speaker memory 并关联项目。当前实现可能仍为必填，正在重构中。

### 创建项目

```http
POST /api/v1/projects
```

Request:

```json
{
  "speaker_id": "uuid",
  "title": "2026世界未来科技发展峰会演讲",
  "event_name": "2026世界未来科技发展峰会",
  "language": "zh"
}
```

### 获取项目列表

```http
GET /api/v1/projects?speaker_id=uuid
```

### 获取项目详情

```http
GET /api/v1/projects/{project_id}
```

## 5. 素材上传

### 上传素材

```http
POST /api/v1/projects/{project_id}/assets
Content-Type: multipart/form-data
```

Fields:

- `file`: 文件
- `type`: `video` | `audio` | `transcript` | `slides` | `image` | `voice_sample` | `past_material`

> `voice_sample` 也可挂在 speaker 上(`POST /api/v1/speakers/{id}/assets`，带 `type`)——见「Speaker = 用户画像」。`image`/`slides` 会被处理:图片走 M3 视觉提取要点、幻灯片 PDF 逐页渲染成图。

### 获取素材列表

```http
GET /api/v1/projects/{project_id}/assets
```

### 删除素材

```http
DELETE /api/v1/projects/{project_id}/assets/{asset_id}
```

## 6. 生成任务

### 触发生成

```http
POST /api/v1/projects/{project_id}/generate
```

Request:

```json
{
  "clip_count": 3,
  "outputs": ["clips", "linkedin", "quote_cards", "carousel", "summary", "blog"],
  "target_language": "en",
  "brand_template_id": "uuid | null",        // 选用哪套品牌模板；缺省取最新
  "instruction": "聚焦实体机器人角度，hook 要狠",  // 用户意图，驱动 analyzer/script 及各衍生 agent
  "tone_settings": {
    "academic_vs_casual": 0.7,
    "rational_vs_passionate": 0.4,
    "concise_vs_detailed": 0.5,
    "audience": "industry"
  }
}
```

> `outputs` 可选项：`clips | linkedin | quote_cards | carousel | summary | blog`。`clips` 始终生成。

Response:

```json
{
  "job_id": "uuid",
  "status": "pending",
  "message": "Generation started"
}
```

### 查询生成任务

```http
GET /api/v1/projects/{project_id}/jobs
GET /api/v1/projects/{project_id}/jobs/{job_id}
```

## 7. Clip 管理

### 获取 Clip 列表

```http
GET /api/v1/projects/{project_id}/clips
```

### 获取 Clip 详情

```http
GET /api/v1/clips/{clip_id}
```

### 编辑 Clip

```http
PUT /api/v1/clips/{clip_id}
```

Request:

```json
{
  "hook": "Your keynote reached 300 people...",
  "script": { "hook": "...", "shots": [...], ... },
  "title_options": ["...", "..."],
  "music_mood": "corporate",
  "render_spec": {
    "source": { "asset_id": "uuid", "kind": "video", "url": "...", "image_urls": [], "fps": 30 },
    "aspect": "9:16",
    "segments": [{ "start": 0, "end": 30, "hidden": false }],
    "caption_track": [{ "start": 0, "end": 1.2, "text": "Hello", "lang": "en" }],
    "caption_style_preset": "clean-bottom",
    "caption_position": { "x": 0.5, "y": 0.84 },
    "title": { "text": "...", "enabled": true, "size": 56, "position": { "x": 0.5, "y": 0.12 } },
    "music": { "track_id": "calm", "url": "...", "enabled": true, "gain_db": -18 },
    "dub": { "url": "...", "enabled": false, "gain_db": 0 },
    "brand": { "logo_url": "...", "cta": "...", "cta_position": { "x": 0.5, "y": 0.92 }, "caption_color": "#ffffff", "fill_mode": "fill" }
  }
}
```

> `source.kind`: `video`(真人录像) | `stills`(图片音频图,`image_urls` 垫底 + `url` 可选语音)。位置点 `caption_position`/`title.position`/`brand.cta_position` 为归一化 `{x,y}`,null→默认。

### 触发渲染

```http
POST /api/v1/clips/{clip_id}/render
```

队列化渲染:返回 202,worker 认领 `render_status=PENDING` → 调 Remotion → 写回 `video_url`/`srt_url`。

### 字幕换语言

```http
POST /api/v1/clips/{clip_id}/translate-captions
```

Request: `{ "target_language": "fr" }`。Response：更新后的 `Clip`（`caption_track` 与 `target_language` 已重写）。

### 语音克隆配音(dub)

```http
POST /api/v1/clips/{clip_id}/dub
```

Request: `{ "target_language": "fr" }`。用演讲者声音(画像 VOICE_SAMPLE / 本场 AUDIO / VIDEO 抽轨)经 MiniMax voice_clone + T2A 把(翻译后的)字幕配成目标语言。Response：更新后的 `Clip`,`render_spec.dub` 已写入(渲染时静音原声、播配音)。

### 基于反馈修订

```http
POST /api/v1/clips/{clip_id}/revise
```

Request: 同 `FeedbackRequest`。Response：修订后的 `Clip`。

### 提交反馈

```http
POST /api/v1/clips/{clip_id}/feedback
```

Request:

```json
{
  "scope": "hook",
  "reason": "hook_not_catchy",
  "detail": "太平淡了，没有冲突感"
}
```

## 8. 衍生内容

### 获取衍生内容列表

```http
GET /api/v1/projects/{project_id}/derivatives
```

### 编辑衍生内容

```http
PUT /api/v1/derivatives/{derivative_id}
```

## 9. 导出

### 导出项目全部内容

```http
POST /api/v1/projects/{project_id}/export
```

Request:

```json
{
  "formats": ["text", "images"]
}
```

Response:

```json
{
  "download_url": "https://storage.example.com/exports/uuid.zip",
  "expires_at": "2026-06-22T12:00:00Z"
}
```

## 10. 品牌模板（Brand Template）

品牌模板决定视频成片中的品牌叠加元素。**多套 CRUD**;启动时种一份默认。生成时由 `GenerateRequest.brand_template_id` 选用(缺省取最新),把 `aspect` / 字幕·标题·CTA 样式与**位置点** / 片头尾 / 配乐 mood 烘焙进 `render_spec`。

### 创建/更新品牌模板

```http
POST /api/v1/brand-templates
PUT /api/v1/brand-templates/{template_id}
```

Request:

```json
{
  "name": "Default",
  "config": {
    "aspect": "9:16",
    "fillMode": "fill",
    "captionFont": "lilita",
    "captionSize": 56,
    "captionColor": "#facc15",
    "captionPosition": { "x": 0.5, "y": 0.84 },
    "titleSize": 58,
    "titlePosition": { "x": 0.5, "y": 0.12 },
    "ctaPosition": { "x": 0.5, "y": 0.92 },
    "logoUrl": "https://.../logo.png",
    "cta": "Read the full talk →",
    "introEnabled": true,
    "introText": "This talk is from…",
    "outroEnabled": true,
    "outroText": "Follow for more insights",
    "musicEnabled": true,
    "musicMood": "corporate"
  }
}
```

### 获取品牌模板列表

```http
GET /api/v1/brand-templates
```

### 获取单个品牌模板

```http
GET /api/v1/brand-templates/{template_id}
```

### 删除品牌模板

```http
DELETE /api/v1/brand-templates/{template_id}
```

## 11. 数据模型

详见 [架构设计](./ARCHITECTURE.md) 中的数据模型部分。

核心模型：

- `Speaker`（= 用户画像：persona 风格 + 声纹；见 ADR-021）
- `Project`
- `Asset`
- `Clip`
- `Derivative`
- `WorkflowRun`
- `HumanFeedback`
- `BrandTemplate`

clip-spec 相关：`ClipSpec` / `ClipSource`(kind/image_urls) / `CaptionCue` / `ClipTitle`(size/position) / `ClipMusic` / `ClipDub` / `ClipBrand`(cta_position) / `Point`。
请求/衍生:`GenerateRequest`(carousel/brand_template_id/instruction) / `DubRequest` / `TranslateCaptionsRequest` / `CarouselResponse` / `CarouselSlide`。
