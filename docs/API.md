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

## 2. Agent Editor request sequence

Create a project with POST /api/v1/projects and attach completed staging uploads through POST /api/v1/projects/{project_id}/assets/from-staging. Submit the user's instruction and attachment IDs to POST /api/v1/chat. The server persists the opening and streams the Agent's native tool activity. Immediate edits save a CompositionVersion. Authorized media generation and formal export enqueue MediaJob and ExportJob respectively.

GET /api/v1/projects/{project_id}/results returns project, prompt, assets, and pending_brief. GET /api/v1/chat/conversations/{id}/messages restores conversation history. GET /api/v1/projects/{project_id}/chat/outputs resolves delivered Output references.

## 3. File Streaming

Uploads and rendered outputs live in S3-compatible object storage (Volcengine TOS). Upload/output endpoints check the caller's key-prefix ownership; project audio playback instead validates the exact owned Snapshot and returns a short-lived signed URL. Range requests and delivery are handled by the object store:

```http
GET /api/v1/files/{file_path}            # 307 → public object URL (source uploads)
GET /api/v1/files/{file_path}?proxy=1    # stream bytes through the API (no redirect)
GET /api/v1/outputs/{file_path}          # 307 → public object URL (rendered MP4/SRT)
GET /api/v1/outputs/{file_path}?download=1   # 307 → presigned GET with Content-Disposition: attachment
GET /api/v1/music/{music_id}/stream      # 307 → public audio, or owner-authorized private audio
GET /api/v1/music/{music_id}             # public piece metadata (no auth)
GET /api/v1/projects/{project_id}/audio/{snapshot_id}/playback # auth → 200 + short-lived signed URL
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

## 5. Persona Management（存量资料与深链）

> The identity module is `personas` (ADR-037/038). Personas are isolated per user; `persona_id` is optional at project creation; the default-persona resolution chain is: project selection → project mount → persona with `auto_created_at` set → earliest created. A persona's `voice` field is the **voiceprint block** (`{"kind":"cloned","voice_id","sample_asset_id"}` | `{"kind":"stock","stock_id"}` | `null` = Auto) — writing style lives in the style fields + `guidelines`. `brand` is the visual-skin block (`null` = system default skin), merged over the default at bake time.

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

> The project may carry an explicit persona selection.

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

`PUT` applies a partial field update; `DELETE` checks unresolved external effects and holds under the project lock, returns 409 while they remain, and otherwise deletes the owned project (204).

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

## 8. Tool execution

The Agent issues native calls through the Chat turn. Generation and export pin the original opening, native call, quote and receipt. An authorization question is answered through the message endpoint in §12. For the exact SSE frames and durable fields, see [the Chat client contract](tasks/agent-editor-evidence/iteration-6/ui-handoff.md).

## 9. Output management

GET /api/v1/outputs/{output_id} reads an owned Output. GET /api/v1/outputs/{output_id}/playback resolves the owned playback or download location. POST /api/v1/outputs/{output_id}/poster resolves its poster. DELETE /api/v1/outputs/{output_id} checks pending publication before deletion.

POST /api/v1/outputs/{output_id}/regenerate accepts eligible output types and sends an owned Output mention to the project conversation. Its response contains message_id and conversation_id. Editing a delivered video proceeds from its pinned version through Chat.

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

## 11. Video export

The Agent calls export_video for the selected CompositionVersion. ExportJob owns the render claim, object verification, wallet settlement and final Output. review_video reads that Output, and deliver_video writes its reviewed reference to the conversation.

## 12. Chat

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
  "persona_id": null,
  "suggestion_ref": null
}
```

ChatRequest rejects unknown fields. Attachments and mentions are persisted on the opening message. Optional skill, persona_id and suggestion_ref carry the explicit selections on this request.

**Streaming**: the endpoint content-negotiates on `Accept`. Plain callers receive one-shot JSON `ChatResponse` (201). `Accept: text/event-stream` streams the current tool-loop turn:

- `assistant.delta` `{"text":"...","message_id":"uuid"}` carries assistant prose verbatim in order, alongside the current tool/activity frames. Chat's `message_id` identifies the server-owned trailing `partial` message; the answer stream omits it (client value `null`). It is not an extractor for a verdict-JSON stream.
- `assistant.interim_prose` carries `{"text","at","message_id","seq","turn_id"}`. The server commits the `intent.type="interim_prose"` row before emitting this frame; its message id is the only valid prose identity for Stop. `assistant.checkpoint` and `intent.type="checkpoint"` are not accepted aliases.
- The 15-second quiet-frame is `assistant.thinking` with `{}`. It is a keepalive/phase fact, not a reasoning channel; reasoning fragments and provider think text never belong on the user wire.
- The terminal envelope is authoritative: `turn.completed` carries the full `ChatResponse`; `turn.failed` carries the failure detail and may include a `persisted` flag.
- Failure does **not** mean “nothing committed.” The user row commits before the agent turn; failure stamps, authored failure rows and activity rows may survive. Clients must not roll back a durable user row or fabricate a successful assistant answer.
- Do not auto-reconnect the POST: a retry can persist another user message. Reconciliation uses the conversation/read endpoints and the terminal envelope rules in `CHAT_ARCHITECTURE.md`.

Delivery messages own their exact intent.output_refs and reviewed_version. History reads resolve those identities to the corresponding version and Output.

### Stop an In-flight Turn

```http
POST /api/v1/chat/turns/{turn_id}/stop
Content-Type: application/json

{
  "prose": [{"message_id": "uuid", "visible_chars": 17}],
  "activity_ids": ["uuid"],
  "structure_ids": ["uuid"]
}
```

`turn_id` is the opening user message id from `turn.started`. All arrays are optional and capped at 128 entries; ids must address server-owned rows in this Turn. `visible_chars` is the prefix actually released by the client typewriter, measured in Unicode code points. Received/buffered text is not visible. The server clamps prefixes to its own stored content; clients never upload replacement prose.

The control endpoint atomically records the Stop decision and visible boundary before the client aborts SSE:

- No visible prose, Activity or structure: delete the whole Turn and return `{"accepted":true,"turn_state":"retracted"}`. The client restores its draft, mentions and existing attachment chips; history cannot resurrect the Turn.
- Some visible content: retain only the reported prefixes/facts, remove unseen rows, cancel visible active Activity rows and return `{"accepted":true,"turn_state":"cancelled"}`.
- If settlement already won, return the existing terminal state; the client must not abort or rewrite that Turn.

Independent interim/partial/Activity writes and the final assistant message and Job authorization fence on the same opening-row lock. Every such lock read refreshes an already-loaded ORM row (`populate_existing`): acquiring the row lock alone does not update the session's identity map after a competing commit. A Start nested in the Chat Turn takes this opening-row fence before locking the pending question, then only flushes its answer/Run/hold; the outer final fence owns the sole commit. Direct answer requests and presentation-ACK auto-Start retain their own commit. A Stop that wins therefore rolls back the uncommitted final transaction and cannot leave a new Run, hold or capture.

If the SSE quiet-closes while Stop is still in flight, the client waits for the Stop control promise before choosing halt versus ordinary drain/failure, so response-before-close and close-before-response apply the frontier exactly once. Stop-pending UI state is owned by that Turn: late cleanup from an old stream/control response cannot clear or wedge its successor. Disconnect cleanup is idempotent and never reverses the control result. OPTIONS answer streams do not use this prompt-Turn Stop endpoint.

Committed edits and media remain readable at their original version or snapshot. Stopping before Output commit precludes delivery and capture. The ExportJob retains its hold while an external write remains unresolved.

### List Conversation Messages

```http
GET /api/v1/chat/conversations/{id}/messages
```

### Answer a Pending Question

```http
POST /api/v1/chat/messages/{id}/answer
```

Answer the original persisted question using its message ID. Paid calls accept an option with option_id approve or decline. Approval reuses that call's arguments and ceiling.

A pending question may additively carry `items: BriefQuestionItem[]` and a server-issued `group_digest` while retaining the legacy `question/options/slot/default_path` fields. Each item declares `slot`, `question`, `options`, `recommended_id`, `allow_freeform`, `required` and `default_path`. A grouped answer is submitted once for the entire pending row:

```json
{
  "kind": "group",
  "group_digest": "server-issued-digest",
  "answers": [
    {"slot": "purpose", "kind": "option", "option_id": "website"},
    {"slot": "target_seconds", "kind": "option", "option_id": "60"},
    {"slot": "narrative_mode", "kind": "option", "option_id": "mission_tech"},
    {"slot": "narration_language", "kind": "option", "option_id": "en"},
    {"slot": "subtitle_languages", "kind": "option", "option_id": "en"},
    {"slot": "aspect", "kind": "option", "option_id": "16:9"}
  ]
}
```

The server validates the pending row and digest, slot whitelist, duplicate answers, required fields, option ownership and freeform permission/length, then settles the row and backfills all Brief slots atomically with `user-stated` provenance. Wrong options/duplicates/missing required fields return 422; stale digests and already-settled rows return 409 without a second settlement or Run. Item selection and freeform edits stay local; only final submit or skip calls this endpoint. A group `bail` may carry the same `group_digest` and the answers selected so far: those answers remain `user-stated`, while only the remaining fields receive task defaults with `default` provenance. `question.preview` carries the same `items/group_digest`; the final envelope remains authoritative. Unsubmitted drafts are not synchronized across devices.

### Video Version Presentation and Scrub Apply

```http
GET /api/v1/chat/video/versions/{version_id}/storyboard
PUT /api/v1/chat/video/versions/{version_id}/clips/{clip_id}
POST /api/v1/chat/messages/{message_id}/video-presentation
```

The storyboard read is owner-scoped and pins the exact immutable version; when the content needs motion, its `video_preview` carries the same version/digest. Scrub Apply sends `base_ref`, `track_id`, the complete text `clip`, and `request_id`; it creates a new version through the shared revision service. A stale base returns 409. Presentation ACK accepts only the version and presentation digest actually shown, with any required preview ready or honestly pending.

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


### List Wallet Transactions

```http
GET /api/v1/wallet/transactions?limit=30&cursor=<opaque>
```

WalletTransactionItem projects native media and export spend under the corresponding media or export identity. Each row carries family, amount, created_at and optional project and payment metadata. The wallet and append-only credit transactions own balances, holds, release and capture. See [wallet accounting](BILLING.md).

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

Core tables for the editor are Project, Asset, SourceSnapshot, Composition, CompositionVersion, Conversation, Message, MediaJob, ExportJob and Output. Publication owns social delivery. The project and wallet enforce user ownership. Jobs retain their authorized amount, execution token and settlement identity.

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

Create body: `{ "output_id", "channel_account_id", "overrides": {...} | null, "client_key": "..." | null }` — one publication per channel; `overrides` merge explicit client edits over the prefilled snapshot (title / caption / hashtags / cover_image_url), and `client_key` dedupes a publish intent (retries reuse the same row). A new publication is born `scheduled` (publish now); the worker picks it up on the next tick.

## 18. 历史 Recipe 目录

旧的公开配方货架已退役。Home 示例只预填用户可编辑的文本。历史结构见 [Recipes](RECIPES.md)。

## 19. Payments (Stripe credit packages)

Hosted Checkout and order/webhook semantics are defined by `docs/PAYMENTS.md`. Amount presets and custom amounts both use server-owned inline `price_data`; presets only prefill the current frontend's amount input. The server's registry and custom policy own amounts, currencies, credits, and limits. Clients never submit currencies, credits, or Stripe Price IDs.

### List Amount Presets

```http
GET /api/v1/payments/packages
```

Requires the caller's JWT. Returns `{ "items": [{ "key", "credits", "amount_minor", "currency" }], "custom": { "currency", "min_amount_minor", "max_amount_minor", "credits_per_major" } }`. `amount_minor` is the integer minor currency unit (EUR cents for the current catalog). The custom policy is the sole source for the input limits and conversion preview.

### Create Checkout Session

```http
POST /api/v1/payments/checkout-sessions
Content-Type: application/json

{ "amount_minor": 1250 }
// Compatibility for existing callers:
// { "package_key": "starter" }
```

The current frontend always submits `amount_minor`; the server also accepts exactly one of `package_key` and `amount_minor` for compatibility. Both forms resolve through the server-owned registry or custom policy and create the same inline one-time `price_data` item. A custom amount must be inside the advertised server policy; the server computes its credits. Both paths commit an internal `pending` order before creating a card-only Stripe `mode=payment` Checkout Session. Returns:

```json
{ "order_id": "uuid", "checkout_url": "https://checkout.stripe.com/..." }
```

Unknown packages return 404 `payments.package_not_found`; an out-of-range custom amount returns 422 `payments.amount_invalid`; missing server configuration returns 503 `payments.not_configured`; Stripe creation failure returns 502 `payments.checkout_failed`. The browser must open `checkout_url`; no card data crosses this API.

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
