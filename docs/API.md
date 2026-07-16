# API Specification

> Status: Draft, updated iteratively as development progresses. Last updated: 2026-07-16.

## 1. Basics

- **Base URL**: `http://localhost:8000`
- **API Prefix**: `/api/v1`
- **Content-Type**: `application/json`
- **Authentication**: Passwordless email verification-code login; clients send the returned JWT as `Authorization: Bearer <token>`. The home page and demo content are readable anonymously; all write endpoints and per-user data require a valid token — there is no default-user fallback.

## 1.1 Authentication

Login is a 6-digit email code delivered via Resend:

```
POST /api/v1/auth/send-code    { "email": "you@example.com" }
  → { "message": "Verification code sent" }
POST /api/v1/auth/verify-code  { "email": "you@example.com", "code": "123456" }
  → { "token": "<jwt>", "user": { "id", "email", "name" } }
```

- Codes expire after 10 minutes, allow max 5 verification attempts, and are single-use.
- send-code rate limits: 60s resend cooldown per email, 5 codes/hour per email, 30 codes/hour per IP (over-limit → 429).
- `verify-code` creates the user on first login (name defaults to the email prefix) and returns a 30-day JWT (HS256).
- List endpoints merge the caller's items with shared demo content owned by the seeded default user (`00000000-0000-0000-0000-000000000001`); the demo project is hidden once the user has real projects.
- Invalid/expired tokens receive 401; the frontend clears the stored token and opens the login dialog on any 401.

## 2. Main Flow Call Sequence

The homepage input box is the main entry point. After the user clicks Generate, the frontend calls the following endpoints in sequence:

```
POST /api/v1/projects
  → Create Project
  → Returns { id, title, ... }

POST /api/v1/projects/{project_id}/assets
  → Upload raw material (file or prompt text)
  → Returns { id, type, processing_status: "pending", ... }

POST /api/v1/projects/{project_id}/generate
  → Trigger async generation
  → Returns { job_id, status: "pending" }
```

After that, the frontend navigates to the project detail page and polls the following endpoints to check results:

```
GET /api/v1/projects/{project_id}/results   → Aggregate view: project + prompt + clips + derivatives + latest job
GET /api/v1/projects/{project_id}/jobs/{job_id}
```

The `/results` endpoint is the preferred way to load a project detail page; it returns everything needed for the review UI in one call. The legacy single-resource endpoints are still available:

```
GET /api/v1/projects/{project_id}
GET /api/v1/projects/{project_id}/assets
GET /api/v1/projects/{project_id}/clips
GET /api/v1/projects/{project_id}/derivatives
GET /api/v1/projects/{project_id}/jobs
```

When rendering a video, call:

```
POST /api/v1/clips/{clip_id}/render
```

## 3. File Streaming

Source video uploads, rendered outputs, and built-in music tracks are all served through HTTP Range-enabled endpoints for browser playback, seeking, and renderer fetching:

```http
GET /api/v1/files/{file_path}
GET /api/v1/outputs/{file_path}
GET /api/v1/outputs/{file_path}?download=1   # Force download with Content-Disposition: attachment
GET /api/v1/music/{mood}                     # Built-in mood library, e.g. calm / uplifting / corporate
```

## 4. Error Format

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Project not found",
    "detail": {}
  }
}
```

## 5. Speaker Management

> **Evolution Note**: The Speaker API is being refactored per ADR-021. The target direction is: Speakers are isolated per user; `speaker_id` is optional at project creation; if not selected, the system auto-creates one. The endpoints below still retain the manual-creation and past-material-to-persona shapes, and will gradually converge toward a unified auto/manual memory model.

### Create Speaker

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

### List Speakers

```http
GET /api/v1/speakers
```

### Get Speaker Detail

```http
GET /api/v1/speakers/{speaker_id}
```

### Update Speaker

```http
PUT /api/v1/speakers/{speaker_id}
```

### Upload Speaker Past Material

```http
POST /api/v1/speakers/{speaker_id}/assets
Content-Type: multipart/form-data
```

Fields:

- `file`: File
- `type`: `video` | `audio` | `transcript` | `slides` | `image` | `voice_sample` | `past_material`

### Generate / Update Speaker Style Persona

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

## 4. Project Management

> **Current state**: `speaker_id` is optional at project creation. When omitted, the system uses the project's own `tone_snapshot` and the default speaker profile for generation; a dedicated `Speaker` row can still be created and selected manually.

### Create Project

```http
POST /api/v1/projects
```

Request:

```json
{
  "speaker_id": "uuid | null",
  "title": "2026世界未来科技发展峰会演讲",
  "event_name": "2026世界未来科技发展峰会",
  "language": "zh"
}
```

### List Projects

```http
GET /api/v1/projects?speaker_id=uuid
```

Response now includes a representative clip thumbnail for each project:

```json
[
  {
    "id": "uuid",
    "title": "...",
    "updated_at": "2026-07-16T...",
    "thumbnail_url": "/api/v1/outputs/.../clip.mp4",
    "thumbnail_duration": 62,
    "thumbnail_aspect": "9:16"
  }
]
```

- `thumbnail_url` points to the earliest rendered clip for the project.
- Demo project is hidden from the list once the user has created any real project.

```http
GET /api/v1/projects/{project_id}
```

## 5. Asset Upload

### Upload Asset

```http
POST /api/v1/projects/{project_id}/assets
Content-Type: multipart/form-data
```

Fields:

- `file`: File
- `type`: `video` | `audio` | `transcript` | `slides` | `image` | `voice_sample` | `past_material`

> `voice_sample` can also be attached to a speaker (`POST /api/v1/speakers/{id}/assets`, with `type`) — see "Speaker = User Profile". `image`/`slides` will be processed: images go through M3 vision for key-point extraction; slide PDFs are rendered page-by-page into images.

### List Assets

```http
GET /api/v1/projects/{project_id}/assets
```

### Delete Asset

```http
DELETE /api/v1/projects/{project_id}/assets/{asset_id}
```

## 6. Generation Tasks

### Trigger Generation

```http
POST /api/v1/projects/{project_id}/generate
```

Request:

```json
{
  "clip_count": 5,
  "outputs": ["clips", "post", "quotes", "article", "carousel"],
  "target_language": "en",
  "brand_template_id": "uuid | null",
  "instruction": "聚焦实体机器人角度，hook 要狠",
  "tone_settings": {
    "academic_vs_casual": 0.7,
    "rational_vs_passionate": 0.4,
    "concise_vs_detailed": 0.5,
    "audience": "industry"
  },
  "scope": "full",
  "target_id": null,
  "operation": "regenerate"
}
```

- `outputs`: any subset of `clips | post | quotes | article | carousel`. Clips are generated only when included.
- `clip_count`: number of clips to generate when `"clips"` is in `outputs` (default `5`).
- `scope`: `"full"` for a full project generation, or `"hook" | "clip" | "derivative" | "render"` for targeted revisions.
- `target_id`: clip or derivative UUID when `scope` is not `"full"`.
- `operation`: operation for targeted revisions (`regenerate | shorten | lengthen | translate | render`).

Response:

```json
{
  "job_id": "uuid",
  "status": "pending",
  "message": "Generation started"
}
```

### Query Generation Jobs

```http
GET /api/v1/projects/{project_id}/jobs
GET /api/v1/projects/{project_id}/jobs/{job_id}
```

`WorkflowRun` includes `context` with per-output progress:

```json
{
  "context": {
    "outputs": ["clips", "post", "quotes", "article"],
    "clip_count": 5,
    "output_status": {
      "clips": {"status": "completed", "progress": 100, "error": null},
      "post": {"status": "failed", "progress": 0, "error": "..."}
    }
  }
}
```

## 7. Clip Management

### List Clips

```http
GET /api/v1/projects/{project_id}/clips
```

### Get Clip Detail

```http
GET /api/v1/clips/{clip_id}
```

### Edit / Revise Clip

Clips are not edited via a single `PUT`. Instead, use the action-specific endpoints below.

### Regenerate Clip

```http
POST /api/v1/clips/{clip_id}/regenerate
```

Request: `{ "instruction": "make the hook shorter" }`. Response: updated `Clip`.

### Revise Based on Feedback

```http
POST /api/v1/clips/{clip_id}/revise
```

Request:

```json
{
  "scope": "hook",
  "reason": "hook_not_catchy",
  "detail": "太平淡了，没有冲突感"
}
```

Response: revised `Clip`.

### Trigger Render

```http
POST /api/v1/clips/{clip_id}/render
```

Queued render: returns 202, worker claims `render_status=PENDING` → calls Remotion → writes back `video_url`/`srt_url`.

### Translate Captions

```http
POST /api/v1/clips/{clip_id}/translate-captions
```

Request: `{ "target_language": "fr" }`. Response: updated `Clip` (`caption_track` and `target_language` rewritten).

### Voice Clone Dubbing (dub)

```http
POST /api/v1/clips/{clip_id}/dub
```

Request: `{ "target_language": "fr" }`. Uses the speaker's voice (from persona VOICE_SAMPLE / this session's AUDIO / VIDEO extracted track) via MiniMax voice_clone + T2A to dub the (translated) captions into the target language. Response: updated `Clip`, `render_spec.dub` written (original audio is muted during render, dubbed audio plays).

### List Derivatives

```http
GET /api/v1/projects/{project_id}/derivatives
```

### Edit Derivative

```http
PUT /api/v1/derivatives/{derivative_id}
```

## 9. Export

### Export All Project Content

```http
POST /api/v1/projects/{project_id}/export
```

Request:

```json
{
  "formats": ["text", "images"]
}
```

Response: a `application/zip` file download with `Content-Disposition: attachment; filename={project_title}.zip`. The archive contains Markdown files for clips, posts, quote cards, and articles. There is no presigned URL; the ZIP is generated on the fly.

## 10. Chat

Project-scoped and asset-scoped chat sessions persist the original prompt and all follow-up instructions. The `/generate` endpoint automatically creates a project-scoped session and stores the user's `instruction` as the first user message.

### Get or Create Session

```http
GET /api/v1/chat/session?project_id={project_id}&asset_id={asset_id}&asset_type={asset_type}
```

Returns the existing session or creates one. `asset_type` is `clip` or `derivative` when the chat is tied to a specific asset.

### Send a Message

```http
POST /api/v1/chat
```

Request:

```json
{
  "project_id": "uuid",
  "asset_id": "uuid | null",
  "asset_type": "clip | derivative | null",
  "message": "make the hook shorter",
  "attachments": []
}
```

Response: `{ session_id, user_message, assistant_message, job_id }`. The assistant message parses the user's intent (translate, revise, render, select music, etc.) and may dispatch a `WorkflowRun` returned as `job_id`.

### List Session Messages

```http
GET /api/v1/chat/sessions/{session_id}/messages
```

## 11. Library

The library lists all downloadable outputs across projects (clips and derivatives) for quick access.

### List Library Items

```http
GET /api/v1/library
```

Query params:

- `type`: `clip` | `derivative` (optional)
- `derivative_type`: `post` | `quotes` | `carousel` | `article` (optional)

## 12. Brand Template

Brand templates determine the brand overlay elements in the final video. **Full CRUD**; a default is seeded on startup. At generation time, `GenerateRequest.brand_template_id` selects one (defaults to latest), baking `aspect` / caption·title·CTA styles and **position points** / intro/outro / music mood into `render_spec`.

### Create / Update Brand Template

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
    "titleEnabled": true,
    "titleSize": 58,
    "titlePosition": { "x": 0.5, "y": 0.12 },
    "introEnabled": true,
    "introKind": "image",
    "introText": "",
    "introMediaUrl": "/api/v1/files/.../intro.png",
    "introDurationSeconds": 2,
    "outroEnabled": true,
    "outroKind": "video",
    "outroText": "",
    "outroMediaUrl": "/api/v1/files/.../outro.mp4",
    "outroDurationSeconds": 3,
    "musicEnabled": true,
    "musicMood": "corporate"
  }
}
```

### List Brand Templates

```http
GET /api/v1/brand-templates
```

### Get Single Brand Template

```http
GET /api/v1/brand-templates/{template_id}
```

### Delete Brand Template

```http
DELETE /api/v1/brand-templates/{template_id}
```

### Upload Intro/Outro Media

```http
POST /api/v1/brand-templates/media
```

Multipart `file` (image or video). Not scoped by `template_id` — a draft may
not have one yet. Returns `{"url": "/api/v1/files/..."}`, a storage-seam URL
to store in `config.introMediaUrl` / `config.outroMediaUrl`.

## 13. Data Models

See the Data Models section in [Architecture Design](./ARCHITECTURE.md).

Core models:

- `Speaker` (= user profile: style memory + voiceprint; see ADR-021)
- `Project` (includes `content_plan: JSON` for persisted ContentPlan)
- `Asset`
- `Clip`
- `Derivative`
- `WorkflowRun` (includes `context` with `outputs`, `clip_count`, `output_status`)
- `ChatSession` (project-scoped or asset-scoped chat container)
- `Message` (chat messages, referenced by `session_id`)
- `BrandTemplate`

Removed / not yet implemented:

- `HumanFeedback` (feedback is now handled by the `/clips/{id}/revise` endpoint and stored on the revised `Clip`)
- `WorkflowStep` (dropped; `WorkflowRun.current_step` tracks progress as a string)

Clip-spec related: `ClipSpec` / `ClipSource`(kind/image_urls) / `CaptionCue` / `ClipTitle`(size/position) / `ClipMusic` / `ClipDub` / `ClipBrand`(intro/outro) / `IntroOutroCard`(kind/text/media_url) / `Point`.
Requests/derivatives: `GenerateRequest`(carousel/brand_template_id/instruction) / `DubRequest` / `TranslateCaptionsRequest` / `CarouselResponse` / `CarouselSlide`.
