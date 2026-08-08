# API Specification

> Status: Draft, updated iteratively as development progresses. Last updated: 2026-07-18.

## 1. Basics

- **Base URL**: `http://localhost:8000`
- **API Prefix**: `/api/v1`
- **Content-Type**: `application/json`
- **Authentication**: Passwordless email verification-code login; clients send the returned JWT as `Authorization: Bearer <token>`. Only the landing page is public; all API reads/writes of per-user data require a valid token — there is no default-user fallback.

## 1.1 Authentication

Login is a 6-digit email code delivered via Resend:

```
POST /api/v1/auth/send-code    { "email": "you@example.com" }
  → { "message": "Verification code sent" }
POST /api/v1/auth/verify-code  { "email": "you@example.com", "code": "123456" }
  → { "token": "<jwt>", "user": { "id", "email", "name" } }
```

- Codes expire after 10 minutes, allow max 5 verification attempts, and are single-use.
- Emails are normalized (lowercase, trimmed) and format-validated on both endpoints — malformed addresses get 400 before a code is created. A recipient rejected by Resend (4xx) also returns 400; genuine provider/5xx failures return 502.
- send-code rate limits: 60s resend cooldown per email, 10 codes/hour per email, 30 codes/hour per IP (over-limit → 429).
- `verify-code` creates the user on first login (name defaults to the email prefix) and returns a 1-day JWT (HS256).
- Projects, personas, brand templates and all other product data are private to their owner — anonymous requests see nothing. `/personas` returns only the caller's own personas: project creation rejects persona_ids the caller does not own, so default-user (shared) personas are never offered as selectable options.
- Invalid/expired tokens receive 401; the frontend clears the stored token and opens the login dialog on any 401.

## 2. Main Flow Call Sequence

The homepage input box is the main entry point. After the user clicks send, the frontend creates the project, uploads the material, then navigates to the project page where the overlay chat sends the draft as the first chat message — **intent recognition lives entirely in the chat loop** (intent-surface-unification, 2026-08-04; there is no separate intent endpoint):

```
POST /api/v1/projects
  → Create Project
  → Returns { id, title, ... }

POST /api/v1/projects/{project_id}/assets
  → Upload raw material (file or prompt text)
  → Returns { id, type, processing_status: "pending", ... }

POST /api/v1/chat
  → The first message enters the plan path: the PlanAgent builds the task
    book, which docks as a pending task_book question (§10)
  → Confirming it (POST /chat/messages/{id}/answer with kind="start", or a
    prose "looks good, start it" via /chat) starts the run
```

After that, the frontend navigates to the project detail page and polls the following endpoints to check results:

```
GET /api/v1/projects/{project_id}/results   → Aggregate view: project + prompt + clips + derivatives + latest run + assets
GET /api/v1/projects/{project_id}/runs/{run_id}
```

The `/results` endpoint is the preferred way to load a project detail page; it returns everything needed for the review UI in one call. The `assets` field carries each asset's `processing_status` / `processing_error` so the results page can render the transcribing/parsing phase while the generation run waits for assets to settle. (The computed `ui_step` field was retired on 2026-07-28 together with the results-page loading dialog — live progress is the chat overlay's step stream, driven by `GET /runs/{id}/events`.) The legacy single-resource endpoints are still available:

```
GET /api/v1/projects                  → the caller's own projects (anonymous: empty list)
GET /api/v1/projects/{project_id}
GET /api/v1/projects/{project_id}/assets
GET /api/v1/projects/{project_id}/clips
GET /api/v1/projects/{project_id}/derivatives
GET /api/v1/projects/{project_id}/runs
```

When rendering a video, call:

```
POST /api/v1/clips/{clip_id}/render
```

## 3. File Streaming

Uploads and rendered outputs live in S3-compatible object storage (Volcengine TOS). These endpoints first perform an **ownership check** (key prefix must be the caller's user id, otherwise 403/404), then redirect to the storage URL — Range requests and delivery are handled by the object store:

```http
GET /api/v1/files/{file_path}            # 307 → public object URL (source uploads)
GET /api/v1/files/{file_path}?proxy=1    # stream bytes through the API (no redirect)
GET /api/v1/outputs/{file_path}          # 307 → public object URL (rendered MP4/SRT)
GET /api/v1/outputs/{file_path}?download=1   # 307 → presigned GET with Content-Disposition: attachment
GET /api/v1/music/{mood}                     # Built-in mood library, e.g. calm / uplifting / corporate
```

- Use `?proxy=1` when fetching a file **programmatically** (`fetch()` → blob): the cross-origin redirect is subject to CORS, and the bucket does not send `Vary: Origin`, so a no-cors `<video>` copy of the same object can poison the browser cache for later CORS fetches. `<video>/<audio>/<img>` tags can use the redirect form directly.

## 4. Error Format

Errors use FastAPI's default shape — the human-readable reason is always in `detail`:

```json
{ "detail": "Persona not found" }
```

- **Handler-raised errors** (4xx/5xx via `HTTPException`): `detail` is a string with the reason.
- **Validation errors** (422): `detail` is an array of `{loc, msg, type}` field errors.
- **Unhandled exceptions** (500): a global handler logs the traceback server-side and returns `{ "detail": "Internal server error" }` — internals never leak to clients.

Every request is logged as `http_request` with method, path, query, status, duration, client IP, and — for JSON payloads — the request and response bodies (credentials like `token`/`code` are redacted, bodies truncated; multipart and file streams are never buffered). Errors additionally log `http_error` / `http_validation_error` / `http_unhandled_error` with the reason at raise time.

## 5. Persona Management

> **Evolution Note**: The identity module was renamed Speaker → Persona across the stack (ADR-037, cut 1 landed 2026-08-09 — table `personas`, endpoints `/api/v1/personas`). Personas are isolated per user; `persona_id` is optional at project creation; if not selected, the system auto-creates one on the first run. The endpoints below still retain the manual-creation and past-material-to-persona shapes, and will gradually converge toward a unified auto/manual memory model.

### Create Persona

```http
POST /api/v1/personas
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
  "core_values": [],
  "favorite_metaphors": [],
  "sentence_style": "",
  "emotional_tone": "rational",
  "typical_hooks": [],
  "avoid_words": [],
  "voice": null,
  "audience": null,
  "guidelines": null,
  "cta": null,
  "created_at": "2026-06-22T10:00:00Z"
}
```

### List Personas

```http
GET /api/v1/personas
```

### Get Persona Detail

```http
GET /api/v1/personas/{persona_id}
```

### Update Persona

```http
PUT /api/v1/personas/{persona_id}
```

### Upload Persona Past Material

```http
POST /api/v1/personas/{persona_id}/assets
Content-Type: multipart/form-data
```

Fields:

- `file`: File
- `type`: `video` | `audio` | `transcript` | `slides` | `image` | `voice_sample` | `past_material`

### Generate / Update Persona Style Profile

```http
POST /api/v1/personas/{persona_id}/generate
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

> **Current state**: `persona_id` is optional at project creation. When omitted, the first run auto-creates a persona from the project's source texts; a dedicated `Persona` row can still be created and selected manually.

### Create Project

```http
POST /api/v1/projects
```

Request:

```json
{
  "persona_id": "uuid | null",
  "title": "2026世界未来科技发展峰会演讲",
  "event_name": "2026世界未来科技发展峰会",
  "language": "zh"
}
```

### List Projects

```http
GET /api/v1/projects?persona_id=uuid
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

```http
GET /api/v1/projects/{project_id}
```

## 5. Asset Upload

The primary flow is **direct-to-storage** via a presigned PUT URL; the multipart endpoint below remains as a fallback:

```http
POST /api/v1/projects/{project_id}/assets/upload-url
{ "filename": "talk.mp4", "content_type": "video/mp4" }
  → { "key": "{user_id}/uploads/projects/{project_id}/{unique}.mp4", "upload_url": "<presigned PUT, 15 min TTL>" }

PUT {upload_url}                               # client uploads bytes directly to object storage

POST /api/v1/projects/{project_id}/assets
{ "type": "video", "key": "{user_id}/uploads/projects/{project_id}/{unique}.mp4" }
  → Asset { id, processing_status: "pending", ... }
```

The create-from-key call validates that the key sits under the server-issued upload dir for that user+project and that the object actually exists in storage (400 otherwise). Persona assets have the same two-step flow under `/api/v1/personas/{persona_id}/assets/upload-url`.

### Upload Asset (multipart fallback)

```http
POST /api/v1/projects/{project_id}/assets/upload
Content-Type: multipart/form-data
```

Fields:

- `file`: File
- `type`: `video` | `audio` | `transcript` | `slides` | `image` | `voice_sample` | `past_material`

> `voice_sample` can also be attached to a persona (`POST /api/v1/personas/{id}/assets`, with `type`) — see "Persona = User Profile". `image`/`slides` will be processed: images go through M3 vision for key-point extraction; slide PDFs are rendered page-by-page into images.

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
  "slots": [
    { "type": "clips", "count": 5 },
    { "type": "post", "language": "de" },
    { "type": "quotes" },
    { "type": "article" }
  ],
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

- `slots`: the task book — one `IntentSlot` per requested output (`clips | post | quotes | article | carousel`, with optional `count` / `focus` / `language` / `tone_override`; same-type multi slots express multi-language versions). **Required for `full`-scope requests** — the task book is built and confirmed in the chat plan path (§10); a full-scope call without explicit `slots` is rejected with `422`. Non-full scopes (retries, targeted runs) may omit them and fall back to the default slot set.
- `target_language`: optional (fallback `en`).
- `clip_count`: number of clips to generate when `"clips"` is in `outputs` (default `5`).
- `scope`: `"full"` for a full project generation, or `"hook" | "clip" | "derivative" | "render"` for targeted revisions.
- `target_id`: clip or derivative UUID when `scope` is not `"full"`.
- `operation`: operation for targeted revisions (`regenerate | shorten | lengthen | translate | render`).

Validation: for a full-scope request whose resolved `outputs` include `"clips"`, the project must have at least one renderable media asset (`video` / `audio` / `image` / `slides` with a file URL); otherwise the endpoint returns `422`. A text-only project cannot produce clips (the intent step already excludes `clips` for text-only input).

Queueing note: the created run stays `pending` until every project asset has finished processing (ASR / extraction) — the worker skips runs whose assets are not ready yet. It is therefore safe to call `/generate` immediately after uploading; there is no need to wait for asset processing first.

Response:

```json
{
  "run_id": "uuid",
  "status": "pending",
  "message": "Generation started"
}
```

### Query Generation Runs

```http
GET /api/v1/projects/{project_id}/runs
GET /api/v1/projects/{project_id}/runs/{run_id}
```

### Stream Run Events (SSE)

```http
GET /api/v1/runs/{run_id}/events
```

Server-Sent Events stream of a run's state (CHAT_ARCHITECTURE §8 — a pushed read of DB state, not an event bus). On connect the server sends a full `run.snapshot` frame (`{run, steps}`, idempotent on reconnect); while the run is active it tails `workflow_steps` once per second and pushes `step.updated` (`{id, kind, seq, status, stage, summary, error}`) and `run.updated` (`{id, status, progress, error}`, terminal frame adds the derived aggregate `summary`) only on change. A `: heartbeat` comment frame is sent every 15s; the stream closes after the terminal state. There is no event store, replay, or delivery guarantee. Use `@microsoft/fetch-event-source` on the frontend — native `EventSource` cannot send the `Authorization` header.

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

Request: `{ "target_language": "fr" }`. Uses the persona's voice (from the persona's VOICE_SAMPLE / this session's AUDIO / VIDEO extracted track) via MiniMax voice_clone + T2A to dub the (translated) captions into the target language. Response: updated `Clip`, `render_spec.dub` written (original audio is muted during render, dubbed audio plays).

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

Project-scoped and asset-scoped conversations persist the original prompt and all follow-up instructions. **`POST /chat` is the only intent surface** (intent-surface-unification, 2026-08-04): the task book is built, refined and confirmed here — the retired `/projects/{id}/intent` and `/infer-intent` endpoints no longer exist.

### Get or Create Conversation

```http
GET /api/v1/chat/conversation?project_id={project_id}&asset_id={asset_id}&asset_type={asset_type}
```

Returns the existing conversation or creates one. `asset_type` is `clip` or `derivative` when the chat is tied to a specific asset.

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
  "attachments": [],
  "mentions": [],
  "prior_intent": null,
  "brand_template_id": "uuid | null",
  "autonomy": "auto | review | null"
}
```

`mentions` pins @ entity references to definite ids (`[{type, id, label}]`, `type` ∈ `asset | output | transcript_segment | workflow_step | recipe`); a `recipe` mention is resolved server-side into pinned task-book slots (fail-fast 422 on unknown / reserved / multiple recipes). Messages echo `mentions` back.

**Streaming (2026-08-04)**: the endpoint content-negotiates on `Accept`. Plain callers get the one-shot JSON `ChatResponse` (201) as before; `Accept: text/event-stream` streams the turn — `assistant.delta` `{"text"}` prose previews (0..N, concatenate in order) while the verdict JSON generates, then exactly one terminal frame: `turn.completed` carrying the full `ChatResponse` (the envelope is authoritative; deltas are a preview channel only) or `turn.failed` `{"detail"}` (mid-stream failure — nothing is committed). 15s heartbeat comment frames. Plan-card turns emit zero deltas (structured JSON must arrive whole); the streaming benefit is prose turns. Clients must not auto-reconnect — a retried POST persists the user message again.

`prior_intent` and `brand_template_id` are plan-path transports (never persisted on the message): `prior_intent` is the review panel's current task book — its `explicit` slots pin through re-inference; `brand_template_id` is written into the pending intent only when a task book docks (a later turn omitting it never clobbers the stored choice). `autonomy` is consumed only when this turn confirms the task book by prose — the dock's tier survives a typed "start it".

**Plan path** (project scope, before the first run or while a task book is pending): the PlanAgent builds / refines the task book. Response shapes by verdict — `generate`: `assistant_message` is the docked `task_book` question (the book itself is on `GET /projects/{id}/results` → `pending_intent`); `answer`: a plain informational reply; `start` (prose confirmation): the run starts — `run_id` is set and `answered_question` carries the settled task book.

**Chat loop** (projects with runs, and all asset scopes): the assistant message carries the intent agent's four-state proposal (CHAT_ARCHITECTURE §3, N-18 + N-21): a non-empty `task_list` compiles into a new `WorkflowRun` (returned as `run_id`); `edit_ops` applies registry-validated ops to the target output; `ask` docks a typed question (`assistant_message.question`, never rendered in the flow); `answer` is a purely informational reply (capability / progress / explanation) as plain text — no run, no dock. `answered_question` carries the question this very message settled via deterministic autoResume (letter/number/label hit or freeform fallback), so the client can archive its QA pair.

### List Conversation Messages

```http
GET /api/v1/chat/conversations/{id}/messages
```

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
    "musicId": "<music row uuid>"
  }
}
```

> `musicId` references a `Music` row (see `docs/MUSIC_ARCHITECTURE.md`); the legacy `musicMood` key (calm/uplifting/corporate/none) is still honored as a fallback for templates saved before ADR-023.

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

Field-level truth lives in code (`apps/api/app/models/tables.py`); cross-cutting data conventions and table ownership are in [MODULE_ARCHITECTURE.md](./MODULE_ARCHITECTURE.md) §4 / §7.3.

Core models:

- `Persona` (= user profile: style memory + voiceprint; ADR-037)
- `Project` (includes `content_plan: JSON` for persisted ContentPlan)
- `Asset`
- `Clip`
- `Derivative`
- `WorkflowRun` (includes `context` with `outputs`, `clip_count`, `output_status`)
- `Conversation` (project-scoped or asset-scoped chat container)
- `Message` (chat messages, referenced by `conversation_id`)
- `BrandTemplate`

Removed / not yet implemented:

- `HumanFeedback` (feedback is now handled by the `/clips/{id}/revise` endpoint and stored on the revised `Clip`)
- `WorkflowStep` (dropped; `WorkflowRun.current_step` tracks progress as a string)

Clip-spec related: `ClipSpec` / `ClipSource`(kind/image_urls) / `CaptionCue` / `ClipTitle`(size/position) / `ClipMusic` / `ClipDub` / `ClipBrand`(intro/outro) / `IntroOutroCard`(kind/text/media_url) / `Point`.
Requests/derivatives: `GenerateRequest`(carousel/brand_template_id/instruction) / `DubRequest` / `TranslateCaptionsRequest` / `CarouselResponse` / `CarouselSlide`.
