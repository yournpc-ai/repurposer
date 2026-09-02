# API Specification

> Status: Draft, updated iteratively as development progresses. Last updated: 2026-08-18.

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
  → The first message enters the book path: the intent router builds the task
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
POST /api/v1/outputs/{output_id}/render
```

## 3. File Streaming

Uploads and rendered outputs live in S3-compatible object storage (Volcengine TOS). These endpoints first perform an **ownership check** (key prefix must be the caller's user id, otherwise 403/404), then redirect to the storage URL — Range requests and delivery are handled by the object store:

```http
GET /api/v1/files/{file_path}            # 307 → public object URL (source uploads)
GET /api/v1/files/{file_path}?proxy=1    # stream bytes through the API (no redirect)
GET /api/v1/outputs/{file_path}          # 307 → public object URL (rendered MP4/SRT)
GET /api/v1/outputs/{file_path}?download=1   # 307 → presigned GET with Content-Disposition: attachment
GET /api/v1/music/{music_id}/stream      # 307 → public audio URL (no auth)
GET /api/v1/music/{music_id}             # public piece metadata (no auth)
```

`mood` (calm / uplifting / corporate / …) is a metadata field on each `Music` row, not a path — see §8.

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

> The identity module is `personas` (ADR-037/038). Personas are isolated per user; `persona_id` is optional at project creation; the default-persona resolution chain is: run-context pin → project mount → persona with `auto_created_at` set → earliest created. A persona's `voice` field is the **voiceprint block** (`{"kind":"cloned","voice_id","sample_asset_id"}` | `{"kind":"stock","stock_id"}` | `null` = Auto) — writing style lives in the style fields + `guidelines`. `brand` is the visual-skin block (`null` = system default skin), merged over the default at bake time.

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
  "brand": null,
  "learned_from": null,
  "calibrated_at": null,
  "auto_created_at": null,
  "audience": null,
  "guidelines": null,
  "cta": null,
  "created_at": "2026-06-22T10:00:00Z"
}
```

`voice` = voiceprint block (see the note above); `brand` = visual-skin block (`captionFont` / `captionSize` / `captionColor` / `captionPosition` / `captionStylePreset` / `title*` / `keywordHighlighter` / `logo` / `intro` / `outro` / `musicId` / `musicMood`), merged over the system default at bake time; `learned_from` records which assets the profile was calibrated from; `calibrated_at` / `auto_created_at` are nullable timestamps (`auto_created_at` doubles as the "system-created" marker in the default-persona chain).

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

### Delete Persona

```http
DELETE /api/v1/personas/{persona_id}
```

204; deletes the persona and all its source assets (storage files + rows).

### Upload Persona Past Material

```http
POST /api/v1/personas/{persona_id}/assets
Content-Type: multipart/form-data
```

Fields:

- `file`: File
- `type`: `video` | `audio` | `transcript` | `slides` | `image` | `voice_sample` | `past_material`

### List / Rename / Delete Persona Assets

```http
GET /api/v1/personas/{persona_id}/assets?type=past_material
PUT /api/v1/personas/{persona_id}/assets/{asset_id}     { "title": "..." }
DELETE /api/v1/personas/{persona_id}/assets/{asset_id}
```

The list reads one kind of persona asset (default `past_material`; the voice section reads samples with `type=voice_sample`). `PUT` renames (the storage key is untouched).

### Skin Intro/Outro Media

```http
POST /api/v1/personas/{persona_id}/media/upload-url   { "filename", "content_type" } → { "key", "upload_url" }
POST /api/v1/personas/{persona_id}/media              { "key" } → { "url" }
```

Two-step direct-to-storage upload for the skin block's intro/outro media (image/video); the confirm call validates the server-issued key and returns the stream URL.

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

### Update / Delete Project

```http
PUT /api/v1/projects/{project_id}
DELETE /api/v1/projects/{project_id}
```

`PUT` applies a partial field update; `DELETE` removes the project with its outputs, runs and assets (204).

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

### Get Asset / Reprocess

```http
GET /api/v1/projects/{project_id}/assets/{asset_id}              → single asset (poll processing status)
POST /api/v1/projects/{project_id}/assets/{asset_id}/reprocess   → re-queue processing (e.g. after a failure)
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
  "tasks": [
    { "skill": "select_clips", "params": { "count": 5 } },
    { "skill": "write_post", "params": { "language": "de" } },
    { "skill": "write_quotes", "params": {} },
    { "skill": "write_article", "params": {} }
  ],
  "target_language": "en",
  "instruction": "聚焦实体机器人角度，hook 要狠",
  "tone_settings": {
    "academic_vs_casual": 0.7,
    "rational_vs_passionate": 0.4,
    "concise_vs_detailed": 0.5,
    "audience": "industry"
  },
  "autonomy": "auto",
  "scope": "full",
  "target_id": null,
  "operation": "regenerate"
}
```

- `tasks`: the confirmed task book (ADR-043 — the book path's only grammar): one `TaskItem` per requested task, `{ "skill", "params" }` where `skill` names a registry skill (`select_clips | write_post | write_quotes | write_carousel | write_article | …`) and `params` carries its parameters (`count` / `language` / `focus` / …; same-skill multi tasks express multi-language versions). **Required for `full`-scope requests** — the task book is built and confirmed in the chat book path (§10); a full-scope call without explicit `tasks` is rejected with `422`. Non-full scopes (retries, targeted runs) may omit them and re-run one node family off `target_id`.
- `target_language`: optional spec-level fallback — `null` derives from the first task that carries a language (fallback `en`).
- `autonomy`: `auto | review` (default `auto`) — `review` pauses full runs at the direction checkpoint; stored verbatim on `run.context`.
- `scope`: `"full"` for a full project generation, or `"hook" | "clip" | "post" | "quotes" | "derivative" | "translation" | "render"` for targeted revisions.
- `target_id`: clip or derivative UUID when `scope` is not `"full"`.
- `operation`: operation for targeted revisions (`regenerate | shorten | lengthen | translate | render`).

Validation: for a full-scope request whose task book produces clips, the project must have at least one renderable media asset (`video` / `audio` / `image` / `slides` with a file URL); otherwise the endpoint returns `422`. A text-only project cannot produce clips (the intent step already excludes clip tasks for text-only input).

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

`WorkflowRun.context` is the confirmed task book (the `TaskSpec` dump):

```json
{
  "context": {
    "tasks": [{ "skill": "select_clips", "params": { "count": 5 } }],
    "target_language": "en",
    "instruction": "...",
    "tone_settings": null,
    "autonomy": "auto",
    "scope": "full",
    "operation": "regenerate",
    "target_id": null
  }
}
```

Per-node progress lives on `workflow_steps` — the run response and the SSE stream carry them as the `steps` array.

## 7. Output Management

Clips and derivatives are both `Output` rows (`type` = `clip | post | quotes | carousel | article`); item-level endpoints live under `/outputs/{output_id}`. Clip-only actions return 400 on other output types.

### List Clips

```http
GET /api/v1/projects/{project_id}/clips
```

### List Derivatives

```http
GET /api/v1/projects/{project_id}/derivatives
```

### Get Output

```http
GET /api/v1/outputs/{output_id}
```

Editor load + render-status polling.

### Update Output

```http
PUT /api/v1/outputs/{output_id}
```

Partial update of the editable fields — `{ "payload": {...}, "status": "...", "publishing": {...} }` (`publishing` merges). `render_spec` edits do NOT come through here; they go through the operations API below (ADR-032: every render_spec write journals an operation).

### Delete Output

```http
DELETE /api/v1/outputs/{output_id}
```

204; removes the row plus its produced storage objects (video/srt/image keys + the cover).

### Regenerate Output

```http
POST /api/v1/outputs/{output_id}/regenerate
```

Request: `{ "instruction": "make the hook shorter", "target_language": "en" }` (both optional). Queues regeneration through the generic chat layer — response: `{ "run_id", "message_id", "conversation_id" }`.

### Revise Clip Based on Feedback

```http
POST /api/v1/outputs/{output_id}/revise
```

Clip outputs only. Request:

```json
{
  "scope": "hook",
  "reason": "hook_not_catchy",
  "detail": "太平淡了，没有冲突感"
}
```

`scope` ∈ `hook | full_script | tone | translation`. Response: the revised output.

### Trigger Render

```http
POST /api/v1/outputs/{output_id}/render
```

Clip outputs only. Queued render: returns 202, worker claims `render_status=PENDING` → calls Remotion → writes back `video_url`/`srt_url`. 400 when the clip has no `render_spec` (text-only project — no source video).

### Generate Cover

```http
POST /api/v1/outputs/{output_id}/cover
```

Clip outputs only. Generates a cover image on demand and stores it on `publishing.cover_image_url` (created only when requested by the UI, to avoid paying image-generation costs for every clip).

### Translate Captions

```http
POST /api/v1/outputs/{output_id}/translate-captions
```

Clip outputs only. Request: `{ "target_language": "fr" }`. Re-translates the persisted `render_spec`'s `caption_track` in place (word-level) and updates the spec's `target_language`; the write is journaled as an operation. Response: the updated output.

### Voice Clone Dubbing (dub)

```http
POST /api/v1/outputs/{output_id}/dub
```

Clip outputs only. Request: `{ "target_language": "fr" }`. Uses the persona's voice (from the persona's VOICE_SAMPLE / this session's AUDIO / VIDEO extracted track) via MiniMax voice_clone + T2A to dub the (translated) captions into the target language; the write is journaled as an operation. Response: the updated output, `render_spec.dub` written (original audio is muted during render, dubbed audio plays).

### Operations (edit journal, ADR-032)

Every `render_spec` write is journaled as an operation — batch apply is the editor's save model, undo/redo are journal state transitions (append-only):

```http
GET  /api/v1/outputs/{output_id}/operations           → operation history (editor timeline)
POST /api/v1/outputs/{output_id}/operations           → 201; apply a batch atomically
POST /api/v1/outputs/{output_id}/operations/undo      → undo the latest op
POST /api/v1/outputs/{output_id}/operations/redo      → redo the latest undone op
```

Batch request: `{ "ops": [{ "op": "...", "params": {...} }], "base_hash": "<hash | null>" }` — op names and params are validated against the server-side registry (400 on a rejected op, 409 on a `base_hash` conflict). Response: `{ "output", "operations", "stale_tracks" }` — `stale_tracks` names derived tracks the batch invalidated (ADR-044; the client surfaces the one-line notice). Undo/redo return `{ "output" }`.

## 8. Music Library

AI-generated + platform-seeded music pieces (`docs/MUSIC_ARCHITECTURE.md`).

### List Pieces

```http
GET /api/v1/music
```

Public pieces + the caller's own.

### Generate a Piece

```http
POST /api/v1/music/generate
```

201; `{ "prompt": "...", "mood": "calm", "title": "...", "is_instrumental": true }` — generates via MiniMax inline in the request and persists the piece (502 on provider failure).

### Stream / Metadata

```http
GET /api/v1/music/{music_id}/stream   → 307 → public audio URL (no auth)
GET /api/v1/music/{music_id}          → public piece metadata (no auth)
```

### Update / Delete (creator only)

```http
PUT /api/v1/music/{music_id}
DELETE /api/v1/music/{music_id}
```

`PUT` edits metadata (`title` / `license` / `source_url` / `attribution` / `is_public`); platform/default pieces are immutable to regular users. `DELETE` returns 204, or 409 while any clip still references the piece.

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
  "persona_id": "uuid | null",
  "autonomy": "auto | review | null"
}
```

`mentions` pins @ entity references to definite ids (`[{type, id, label}]`); the live registry types are `asset | output | workflow_step` (MENTIONS §4). `recipe` is retired — a recipe is just a prompt (ADR-040: the card's prefilled template is the entire launch payload), the type member stays only so historical messages still render their chips; `transcript_segment` is filed but unimplemented. Messages echo `mentions` back.

**Streaming (2026-08-04)**: the endpoint content-negotiates on `Accept`. Plain callers get the one-shot JSON `ChatResponse` (201) as before; `Accept: text/event-stream` streams the turn — `assistant.delta` `{"text"}` prose previews (0..N, concatenate in order) while the verdict JSON generates, then exactly one terminal frame: `turn.completed` carrying the full `ChatResponse` (the envelope is authoritative; deltas are a preview channel only) or `turn.failed` `{"detail"}` (mid-stream failure — nothing is committed). Non-prose fragments (think prefixes, verdict-JSON tails, reasoning) stream as `assistant.thinking` keepalive frames. 15s heartbeat comment frames. A `start` turn (`answer=null`) emits zero deltas; plan-card (`generate`) turns stream the plan echo (`intent.answer` prose) as deltas while the structured book arrives whole in the terminal frame. Clients must not auto-reconnect — a retried POST persists the user message again.

`prior_intent` and `persona_id` are book-path transports (never persisted on the message): `prior_intent` is the review panel's current task chain — panel edits are direct structural edits to the task list (ADR-043), the edited chain rides `prior_intent` into the next inference, and the intent router re-proposes the full chain with chat revisions always winning; `persona_id` is the composer's persona choice riding the first message — it is written into the pending brief only when a task book docks (a later turn omitting it never clobbers the stored choice), and pinned into `run.context.persona_id` at `create_run`. `autonomy` is consumed only when this turn confirms the task book by prose — the dock's tier survives a typed "start it".

**Book path** (project scope, before the first run or while a task book is pending): the intent router builds / refines the task book. Response shapes by verdict — `generate`: `assistant_message` is the docked `task_book` question (the book itself is on `GET /projects/{id}/results` → `pending_brief`); `answer`: a plain informational reply; `start` (prose confirmation): the run starts — `run_id` is set and `answered_question` carries the settled task book.

**Chat loop** (projects with runs): the assistant message carries the intent agent's four-state proposal (CHAT_ARCHITECTURE §3, N-18 + N-21): a non-empty `task_list` compiles into a new `WorkflowRun` (returned as `run_id`); `edit_ops` applies registry-validated ops to the target output; `ask` docks a typed question (`assistant_message.question`, never rendered in the flow); `answer` is a purely informational reply (capability / progress / explanation) as plain text — no run, no dock. `answered_question` carries the question this very message settled via deterministic autoResume (letter/number/label hit or freeform fallback), so the client can archive its QA pair.

### List Conversation Messages

```http
GET /api/v1/chat/conversations/{id}/messages
```

### Answer a Pending Question

```http
POST /api/v1/chat/messages/{id}/answer
```

Answers a docked question (ask primitive) — writing the answer is what unblocks the pending decision: a task-book start begins the run, a choice answer continues the conversation (the follow-up reply rides back in the response). The body is discriminated on `kind`: `start` (confirm the docked task book; carries the autonomy tier and the review panel's edited book), `option` / `freeform` (choice answers), `bail` (graceful exit, never an error). Response: `{ "answered_question", "follow_up" }`.

## 11. Notifications

### List Notifications

```http
GET /api/v1/notifications?limit=30
```

Returns `{ "items": [...], "unread_count": n }` for the caller.

### Mark All Read

```http
POST /api/v1/notifications/read-all
```

204.

## 12. Persona Skin Block (brand)

The standalone Brand Template module is retired (ADR-038): the visual skin lives on the persona as the `brand` JSONB block, read and written through the Persona endpoints (§5 — `PUT /api/v1/personas/{persona_id}` with `{"brand": {...}}`). There are no `/brand-templates` endpoints.

At clip-generation time the Pipeline merges the resolved persona's `brand` block over the system default skin and bakes caption color/size/font + position points + intro/outro + music selection into `render_spec.brand`; `render_spec.brand_ref` records the persona id. A persona with `brand: null` renders with the system default skin. Craft/format keys that used to ride the old template config (`aspect`, `fillMode`, `captionEnabled`, filler removal) are **not** persona fields — they come from the recipe registry / task-book defaults.

Skin keys (`null` on the persona = fall through to the default):

```json
{
  "brand": {
    "captionFont": "lilita",
    "captionSize": 56,
    "captionColor": "#facc15",
    "captionPosition": { "x": 0.5, "y": 0.84 },
    "captionStylePreset": "clean-bottom",
    "titleEnabled": true,
    "titleSize": 58,
    "titlePosition": { "x": 0.5, "y": 0.12 },
    "keywordHighlighter": null,
    "logo": null,
    "intro": null,
    "outro": null,
    "musicEnabled": false,
    "musicId": "<music row uuid>"
  }
}
```

> `musicId` references a `Music` row (see `docs/MUSIC_ARCHITECTURE.md`); the `musicMood` key (calm/uplifting/corporate/none) is honored as a fallback. `musicEnabled` is the master switch (default `false` = no soundtrack).

## 13. Data Models

Field-level truth lives in code (`apps/api/app/models/tables.py`); cross-cutting data conventions and table ownership are in [MODULE_ARCHITECTURE.md](./MODULE_ARCHITECTURE.md) §4 / §7.3.

Core models:

- `Persona` (= user profile: style memory + voiceprint block + skin block; ADR-037/038)
- `Project` (includes `content_plan: JSON` for persisted ContentPlan)
- `Asset`
- `Output` (one table for every product output — `type` = `clip | post | quotes | carousel | article`; render state on `render_status` / `render_spec` / `files`, publish state on `publishing`)
- `WorkflowRun` (run-level state machine only; `context` = the confirmed task book, `progress` aggregates node states)
- `WorkflowStep` (RunPlan node: one step of a run's execution plan, materialized at run creation — `inputs` edge list, `spec` params, `output_refs`, per-node `cost` metering ledger)
- `Conversation` (project-scoped or asset-scoped chat container)
- `Message` (chat messages, referenced by `conversation_id`)

Removed / not yet implemented:

- `BrandTemplate` (table dropped, ADR-038 — skin absorbed into `personas.brand`)
- `HumanFeedback` (feedback is now handled by the `/outputs/{id}/revise` endpoint and stored on the revised `Output`)
- `WorkflowRun.current_step` (retired — per-step state lives in `workflow_steps`; query running nodes instead)

Clip-spec related: `ClipSpec` / `ClipSource`(kind/image_urls) / `CaptionCue` / `ClipTitle`(size/position) / `ClipMusic` / `ClipDub` / `ClipBrand`(intro/outro) / `IntroOutroCard`(kind/text/media_url) / `Point`.
Requests/derivatives: `GenerateRequest`(carousel/instruction) / `DubRequest` / `TranslateCaptionsRequest` / `CarouselResponse` / `CarouselSlide`.

## 14. Distribution (Channels & Publications)

Channel OAuth + publish orders (`docs/DISTRIBUTION.md`). URLs name the resource, not the module: `/channels/*` and `/publications/*` hang directly off the API root. Domain errors surface as `detail` codes: 404 `output_not_found` / `channel_not_found` / `channel_not_configured` / `publication_not_found`, 400 `invalid_state`, 409 `illegal_transition` / `already_published` / `channel_not_active`.

### Channels

```http
GET /api/v1/channels/platforms                  → [{ "platform", "configured" }] — per-platform presence gating for the UI
GET /api/v1/channels/{platform}/oauth-url       → { "url" } — start the OAuth flow
GET /api/v1/channels/{platform}/callback        → provider redirect target (no auth header; identity rides the HMAC-signed state nonce); always 302s back to the web app
GET /api/v1/channels                            → the caller's connected channel accounts
DELETE /api/v1/channels/{account_id}            → 204; disconnect
```

### Publications

```http
POST /api/v1/projects/{project_id}/publications
GET /api/v1/publications?state=&project_id=&limit=
GET /api/v1/publications/{pub_id}
POST /api/v1/publications/{pub_id}/cancel
POST /api/v1/publications/{pub_id}/retry
```

Create body: `{ "output_id", "channel_account_id", "overrides": {...} | null, "client_key": "..." | null }` — one publication per channel; `overrides` merge the dialog's edits over the prefilled snapshot (title / caption / hashtags / cover_image_url), and `client_key` dedupes a publish intent (retries reuse the same row). A new publication is born `scheduled` (publish now); the worker picks it up on the next tick.

## 15. Recipes

### List Recipe Cards

```http
GET /api/v1/recipes
```

The public card catalogue: each recipe's public projection (base structure / flow / example_* / input_slots, RECIPES §7.1). No auth — the landing audience is anonymous and reads the same cards. Pin substance (the `tasks` compile shape) never leaves the server.
