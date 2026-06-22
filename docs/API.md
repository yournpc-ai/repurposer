# API 规范

> 状态：Draft，随开发迭代更新。

## 1. 基础信息

- **Base URL**：`http://localhost:8000`
- **API Prefix**：`/api/v1`
- **Content-Type**：`application/json`
- **认证**：本期暂不实现，后续通过 JWT 或 session

## 2. 错误格式

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
- `type`: `video` | `audio` | `transcript` | `slides` | `image` | `voice_sample`

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
  "languages": ["en"],
  "outputs": ["clips", "linkedin", "quote_cards"],
  "tone_settings": {
    "academic_vs_casual": 0.7,
    "rational_vs_passionate": 0.4,
    "concise_vs_detailed": 0.5,
    "audience": "industry"
  }
}
```

Response:

```json
{
  "run_id": "uuid",
  "status": "running",
  "message": "Generation started"
}
```

### 查询生成状态

```http
GET /api/v1/projects/{project_id}/generate/status
```

Response:

```json
{
  "run_id": "uuid",
  "status": "running",
  "current_step": "script_agent",
  "progress": 0.6,
  "clips_generated": 2,
  "total_clips": 3
}
```

### 重新生成单个 Clip

```http
POST /api/v1/clips/{clip_id}/regenerate
```

Request:

```json
{
  "scope": "hook",
  "feedback": "Hook 不够抓人"
}
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
  "hook": "AI 这把火已经烧起来了",
  "shots": [...],
  "title_options": ["...", "..."]
}
```

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
  "formats": ["video", "subtitles", "text", "images"]
}
```

Response:

```json
{
  "download_url": "https://storage.example.com/exports/uuid.zip",
  "expires_at": "2026-06-22T12:00:00Z"
}
```

## 10. 数据模型

详见 [架构设计](./ARCHITECTURE.md) 中的数据模型部分。

核心模型：

- `User`
- `Speaker`
- `Project`
- `Asset`
- `Clip`
- `Derivative`
- `WorkflowRun`
- `WorkflowStep`
- `HumanFeedback`
