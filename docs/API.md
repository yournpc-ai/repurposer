# API Specification

> Status: Current API reference (2026-10-25). Route and schema code remains the field-level source of truth; discrepancies must be checked against the current router before client implementation.

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

The homepage composer uploads selected files to staging as they are chosen. Send then creates the project, attaches the completed staging objects without re-uploading them, and navigates to the project page where the chat dock sends the draft as the first chat message. Intent recognition lives entirely in the chat loop:

```
POST /api/v1/projects
  → Create Project
  → Returns { id, title, ... }

POST /api/v1/projects/{project_id}/assets/from-staging
  → Attach one completed staging upload with { type, key, title, width?, height? }
  → Repeat for each completed file; no bytes are uploaded again

POST /api/v1/chat
  → The first message enters the plan path and may dock a plan/question (§12)
  → A typed production confirmation or the Start pill sends an ordinary
    message through /chat; the next LLM turn may call start_run, which enters
    the same answer_question(kind="start") and evaluate_start_gate machine
```

A prompt-only send creates no asset. If the router determines that the text is the user's own material, the server promotes it to a transcript asset later in the plan path; this is an LLM judgment, not a length heuristic. `AssetCreateRequest` requires a storage `key`; arbitrary prompt text is not an upload body.

The project detail page uses:

```
GET /api/v1/projects/{project_id}/results   → { project, prompt, outputs, latest_run, assets, ... }
GET /api/v1/projects/{project_id}/runs/{run_id}
```

The `/results` endpoint returns one unified `outputs` array, not separate `clips` and `derivatives` arrays. The `assets` field carries each asset's `processing_status` / `processing_error` so the page can render the transcribing/parsing phase. Live run progress is driven by `GET /runs/{id}/events`; chat turn progress uses the separate `POST /chat` SSE contract. Legacy single-resource endpoints remain available:

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

`mood` (calm / uplifting / corporate / …) is a metadata field on each `Music` row, not a path — see §10.

- Use `?proxy=1` when fetching a file **programmatically** (`fetch()` → blob): the cross-origin redirect is subject to CORS, and the bucket does not send `Vary: Origin`, so a no-cors `<video>` copy of the same object can poison the browser cache for later CORS fetches. `<video>/<audio>/<img>` tags can use the redirect form directly.

## 4. Error Format

Errors use FastAPI's `{ "detail": ... }` envelope, but `detail` is **not always a string**:

```json
{ "detail": "Persona not found" }
```

- **Handler-raised errors**: `detail` may be a human-readable string or a typed object. Current structured examples include `{"code":"credits.insufficient","balance":12,"required":340}` and `{"code":"scope.unproven","reasons":[...]}`.
- **Validation errors (422)**: `detail` is normally an array of `{loc, msg, type}` field errors. Endpoint-level business 422 responses may instead use a string or typed object.
- **Unhandled exceptions (500)**: the global handler logs the traceback server-side and returns `{ "detail": "Internal server error" }`; internals do not leak to clients.

Clients must handle string, validation-array and object forms. Do not stringify a structured object and discard its `code`; the frontend toast/error adapter owns display formatting.

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

## 6. Project Management

> `persona_id` is optional at project creation. When omitted, the first run auto-creates a persona from the project's source texts; a dedicated `Persona` row can still be created and selected manually.

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

The response includes a representative clip thumbnail for each project:

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

## 7. Asset Upload

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

## 8. Generation Tasks

### Trigger Generation

```http
POST /api/v1/projects/{project_id}/generate
```

Request (a restricted retry example):

```json
{
  "tasks": [
    { "tool": "select_clips", "params": { "count": 5 } },
    { "tool": "write_post", "params": { "language": "de" } }
  ],
  "target_language": "de",
  "instruction": "聚焦实体机器人角度",
  "tone_settings": null,
  "scope": "full",
  "target_id": null,
  "operation": "regenerate",
  "persona_id": null,
  "caption_mode": null,
  "source_asset_id": null,
  "exemplar_asset_id": null
}
```

**This is not the general first-generation door.** Initial task-book runs are born through the Chat plan/Start machine and `create_run`. `/generate` remains active for typed retries and targeted runs:

- `tasks`: each `TaskItem` is `{ "tool": string, "params": object }`; `tool` names a current registry entry. The schema forbids extra keys — `{ "skill": ... }` is invalid. A `full`-scope request without `tasks` receives 422.
- A tasks-bearing request is paid work and must match a historical confirmed chain exactly or as an ordered subsequence with equal work fields. The request only names the retry reference; persisted run history is the authorization evidence. An unproven/expansion request returns `422 { "detail": { "code": "scope.unproven", "reasons": [...] } }` before `create_run`.
- Targeted scopes (`hook | clip | post | quotes | derivative | translation | render`) may omit `tasks` and use `target_id` plus `operation` (`regenerate | shorten | lengthen | translate | render`). Targeted validity is checked again at the run birthplace.
- `target_language` is an optional fallback; otherwise the first task language is used, then `en`. `persona_id`, `caption_mode`, `source_asset_id` and `exemplar_asset_id` echo the historical scope being retried; they are not independent authorization proof.
- Clips still require renderable media at the birthplace. Text-only projects cannot bypass the clips-media gate by calling this endpoint directly.
- `create_run` wakes dormant assets required by the chain. Workers claim ready `workflow_steps`; clients do not need to poll every unrelated asset before using a valid retry surface.

Response (202):

```json
{
  "run_id": "uuid",
  "status": "pending"
}
```

There is no `message` field.

### Query Generation Runs

```http
GET /api/v1/projects/{project_id}/runs
GET /api/v1/projects/{project_id}/runs/{run_id}
```

### Stream Run Events (SSE)

```http
GET /api/v1/runs/{run_id}/events
```

Server-Sent Events stream of a run's database state, not an event bus. On connect the server sends `run.snapshot` `{run, steps}`; while active it tails `workflow_steps` once per second and pushes changed `step.updated` and `run.updated` frames.

- `run` / `run.updated` contains `id`, `status`, `progress`, `error`, `created_at`; there is no terminal aggregate `summary` field.
- Each step frame is the full current `StepResponse` serialization, including its current credits read projection where applicable.
- A `: heartbeat` comment is sent every 15s; the stream closes after a terminal state.
- There is no event store, replay or delivery guarantee. Reconnect uses a fresh snapshot. Use `@microsoft/fetch-event-source` when an `Authorization` header is required; native `EventSource` cannot set it.

`WorkflowRun.context` stores the run's typed `TaskSpec` and authorization/provenance facts. Task entries use `tool`:

```json
{
  "context": {
    "tasks": [{ "tool": "select_clips", "params": { "count": 5 } }],
    "target_language": "en",
    "instruction": "...",
    "tone_settings": null,
    "scope": "full",
    "operation": "regenerate",
    "target_id": null
  }
}
```

Per-node progress lives on `workflow_steps`; run responses and SSE snapshots carry the current `steps` array.

## 9. Output Management

Clips, films and derivatives are `Output` rows. Public product types are `clip | film | post | quotes | quote_frame | carousel | article`; internal artifacts are excluded by the shared visibility filter. Item-level endpoints live under `/outputs/{output_id}`. Action eligibility is action-specific — do not apply a global “clip only” rule to every endpoint.

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

Accepts `clip` and `film` outputs. Returns 202 with the updated output; repeated clicks while `PENDING`/`RENDERING` do not revoke the in-flight claim. A queued render is claimed using the render eligibility and claim-token fencing rules, rendered through the matching `spec.family`, then writes back the produced files. A missing `render_spec` or another output type returns 400. This render action does not imply that clip-only revise/cover/translate/dub actions also accept film.

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

## 10. Music Library

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

## 11. Export

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

## 12. Chat

Conversations are project-scoped. **`POST /chat` is the only intent surface**: plans, questions, revisions and Start are resolved here. Product targeting rides an `output` mention, not an asset-scoped conversation.

### Get Conversation

```http
GET /api/v1/chat/conversation?project_id={project_id}
```

Returns the existing project conversation. `asset_id` and `asset_type` are not accepted. When no conversation exists the endpoint returns 404; it does not create one. `POST /chat` locates or creates the conversation as part of the first turn.

### Send a Message

```http
POST /api/v1/chat
```

Request (common fields):

```json
{
  "project_id": "uuid",
  "message": "make the hook shorter",
  "attachments": [],
  "mentions": [{"type": "output", "id": "uuid", "label": "Current cut"}],
  "prior_intent": null,
  "persona_id": null,
  "suggestion_ref": null,
  "surface": "canvas",
  "canvas_available": true
}
```

`ChatRequest` is `extra="forbid"`; `asset_id`/`asset_type` now produce 422. `attachments` are the already-staged items consumed by this send and are persisted for history rendering. `mentions` pins entity references to definite ids; the live frontend registry is `asset | output | workflow_step` (workflow-step chips come from canvas selection, not the @ picker). `recipe` is retired and `transcript_segment` is filed but unimplemented. Messages echo their persisted mentions and attachments.

**Streaming**: the endpoint content-negotiates on `Accept`. Plain callers receive one-shot JSON `ChatResponse` (201). `Accept: text/event-stream` streams the current tool-loop turn:

- `assistant.delta` `{"text":"..."}` carries assistant prose verbatim in order, alongside the current tool/activity frames. It is not an extractor for a verdict-JSON stream.
- The 15-second quiet-frame is `assistant.thinking` with `{}`. It is a keepalive/phase fact, not a reasoning channel; reasoning fragments and provider think text never belong on the user wire.
- The terminal envelope is authoritative: `turn.completed` carries the full `ChatResponse`; `turn.failed` carries the failure detail and may include a `persisted` flag.
- Failure does **not** mean “nothing committed.” The user row commits before the agent turn; failure stamps, authored failure rows and activity rows may survive. Clients must not roll back a durable user row or fabricate a successful assistant answer.
- Do not auto-reconnect the POST: a retry can persist another user message. Reconciliation uses the conversation/read endpoints and the terminal envelope rules in `CHAT_ARCHITECTURE.md`.

`prior_intent` and `persona_id` are plan-path transports, not message fields persisted as chat content. `prior_intent` carries the currently presented task chain after panel edits; the router re-proposes the whole chain with the user's revisions winning. `persona_id` rides the first composer message, is stored when a plan docks, and is pinned into `run.context.persona_id` at `create_run`. `surface`/`canvas_available` describe the client environment; they do not authorize work.

**Outcomes**: plan-path turns can dock/refine a plan, ask a question, answer, or enter Start. Projects with runs use the current proposal/edit tools and their scope/authorization adjudication; a proposal does not automatically imply a new run, and a run is never created merely because the client supplied `tasks`. `answered_question` identifies a question settled by deterministic autoResume. Response variants and dock payloads follow `ChatResponse` and the current tool registry, not a retired fixed four-state `task_list/edit_ops/ask/answer` union.

### List Conversation Messages

```http
GET /api/v1/chat/conversations/{id}/messages
```

### Answer a Pending Question

```http
POST /api/v1/chat/messages/{id}/answer
```

Answers a docked question (the question machine) — writing the answer is what unblocks the pending decision: a task-book start begins the run, an options answer continues the conversation (the follow-up reply rides back in the response). The body is discriminated on `kind`: `start` (confirm the docked task book; carries the review panel's edited book), `option` / `freeform` (answers to options questions), `bail` (graceful exit, never an error). Response: `{ "answered_question", "follow_up" }`.

## 13. Notifications

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

## 14. Wallet (credits)

### Read Wallet

```http
GET /api/v1/wallet
```

Returns `{ "balance": n, "held": n }` in credits (ADR-055). `balance` is the spendable truth and may be negative (shown honestly — an over-estimate run settled past zero; the next hold is refused until it recovers); `held` is the credits currently frozen in un-settled run holds. The wallet is lazy-opened with the signup grant on first login, so every caller always has one.

### List Wallet Transactions

```http
GET /api/v1/wallet/transactions?limit=30&cursor=<opaque>
```

Returns **semantic per-event rows**, not raw ledger rows. Hold/capture/release entries for a run fold into one spend row; holds and releases do not appear independently. Grants/refunds/positive adjustments map to `grant`, purchases to `topup`, and negative adjustments to `spend`. Raw `kind`, `ref`, `balance_after` and `idempotency_key` remain internal ledger facts and do not cross this wire.

Pagination is keyset over the raw append-only ledger, newest-first; the semantic fold is applied per page. A run split by a page boundary therefore shows its page-local net. `limit` defaults to 30, max 100; malformed cursors return 422.

```json
{
  "items": [
    {
      "id": "run:…",
      "family": "spend",
      "amount": -27,
      "label": "Conference highlights",
      "output_types": ["clip", "post"],
      "hint": "Turn my talk into…",
      "project_name": "Policy summit",
      "created_at": "2026-09-10T09:00:00Z"
    }
  ],
  "next_cursor": null
}
```

`label` and `hint` are nullable; `output_types` contains public produced types only. `project_name` is nullable. `created_at` uses the semantic group's latest underlying row. `GET /runs/{id}` remains the place for per-step estimate/cost detail.

Insufficient credits at run birth is a structured 422 (user-level vocabulary, never conflated with a provider 402):

```json
{ "detail": { "code": "credits.insufficient", "balance": 12, "required": 340 } }
```

Credits are read-time projections from persisted amounts/USD using the live ratio; only written ledger amounts are immutable. Current shapes differ by surface: `GET /runs/{id}` steps carry `estimate_credits [low, high]` / `cost_credits`; the task-book dock carries `estimate_credits {total, per_task}`; `GET /recipes` cards carry either `estimate_credits [low, high]` or, for per-second cards, `estimate_rate` instead.

## 15. Persona Skin Block (brand)

The visual skin lives on the persona as the `brand` JSONB block (ADR-038), read and written through the Persona endpoints (§5 — `PUT /api/v1/personas/{persona_id}` with `{"brand": {...}}`). There are no `/brand-templates` endpoints.

At clip-generation time the Pipeline merges the resolved persona's `brand` block over the system default skin and bakes caption color/size/font + position points + intro/outro + music selection into `render_spec.brand`; `render_spec.brand_ref` records the persona id. A persona with `brand: null` renders with the system default skin. Craft/format keys (`aspect`, `fillMode`, `captionEnabled`, filler removal) are **not** persona fields — they come from the recipe registry / task-book defaults.

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

## 16. Data Models

Field-level truth lives in code (`apps/api/app/models/tables.py`); cross-cutting data conventions and table ownership are in [MODULE_ARCHITECTURE.md](./MODULE_ARCHITECTURE.md) §4 / §7.3.

Core models:

- `Persona` (= user profile: style memory + voiceprint block + skin block; ADR-037/038)
- `Project` (includes `content_plan: JSON` for persisted ContentPlan)
- `Asset`
- `Output` (one table for public products and internal artifacts — public `type` = `clip | film | post | quotes | quote_frame | carousel | article`; render state on `render_status` / `render_spec` / claim fencing fields, publish state on `publishing`)
- `WorkflowRun` (run-level state machine; `context` = typed TaskSpec plus current authorization/provenance facts, `progress` aggregates node states)
- `WorkflowStep` (RunPlan node: one step of a run's execution plan, materialized at run creation — `inputs` edge list, `spec` params, `output_refs`, per-node `cost` metering facts)
- `Conversation` (project-scoped chat container; output targeting rides mentions)
- `Message` (chat messages, referenced by `conversation_id`)

Rendering contracts: `ClipSpec` and `FilmSpec` are separate families dispatched by `spec.family`; renderer names do not enter either contract. Clip-related models include `ClipSource` / `CaptionCue` / `ClipTitle` / `ClipMusic` / `ClipDub` / `ClipBrand` / `IntroOutroCard` / `Point`. Request/derivative models include `GenerateRequest` / `DubRequest` / `TranslateCaptionsRequest` / `CarouselResponse` / `CarouselSlide`; field-level truth remains the Pydantic schema.

## 17. Distribution (Channels & Publications)

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

## 18. Recipes

### List Recipe Cards

```http
GET /api/v1/recipes
```

The public card catalogue: each recipe's public projection (base structure / flow / example_* / input_slots, RECIPES §7.1). No auth — the landing audience is anonymous and reads the same cards. Pin substance (the `tasks` compile shape) never leaves the server.

## 19. Payments (Stripe credit packages)

Hosted Checkout and order/webhook semantics are defined by `docs/PAYMENTS.md`. An empty environment Price hides its package; clients never submit prices, currencies, credits, or arbitrary Stripe Price IDs.

### List Active Credit Packages

```http
GET /api/v1/payments/packages
```

Requires the caller's JWT. Returns `{ "items": [{ "key", "credits", "amount_minor", "currency" }] }`. `amount_minor` is the integer minor currency unit (EUR cents for the current starter package).

### Create Checkout Session

```http
POST /api/v1/payments/checkout-sessions
Content-Type: application/json

{ "package_key": "starter" }
```

Validates the Stripe Price as active, one-time, and exactly matched to the server's amount/currency before creating and committing an internal `pending` order, then creates a card-only Stripe `mode=payment` Checkout Session. Returns:

```json
{ "order_id": "uuid", "checkout_url": "https://checkout.stripe.com/..." }
```

Unknown/inactive packages return 404 `payments.package_not_found`; missing server configuration returns 503 `payments.not_configured`; Stripe creation failure returns 502 `payments.checkout_failed`. The browser must open `checkout_url`; no card data crosses this API.

### Read Payment Order

```http
GET /api/v1/payments/orders/{order_id}
```

Returns the caller's `{ id, package_key, status, credits, amount_minor, currency, paid_at, credited_at, created_at }`; another user's order returns 404 `payments.order_not_found`. Status is `pending | paid | expired | failed`. This read never grants credits and is the only return-page polling source for announcing a top-up.

### Stripe Webhook

```http
POST /api/v1/payments/stripe/webhook
Stripe-Signature: ...
```

No user JWT: the endpoint authenticates Stripe with the raw request body and webhook signing secret. It handles `checkout.session.completed` and `checkout.session.expired`. Only a fully cross-checked Session with `payment_status=paid` writes the `purchase` ledger row and marks the order paid in the same transaction. Replays are successful no-ops; invalid signatures return 400, temporary internal failures return non-2xx for Stripe retry. Browser success/cancel URLs never move credits.
