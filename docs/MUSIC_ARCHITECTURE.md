# Repurposer Music Architecture

> Status: Proposed  
> Last updated: 2026-07-05  
> Author: Claude + Product Team  
> Related: ADR-019 (built-in mood music library), ADR-022 (music library CRUD), `docs/tasks/todo.md`

---

## 1. Background

Background music is a critical creative layer for vertical clips generated from speeches and conference talks. It influences emotional tone, watch-through rate, and the perceived professionalism of the final output.

Historically, Repurposer treated music as a static brand-template setting (`musicMood: "calm"`) resolved to a file on disk (`data/music/{mood}.<ext>`). This created several problems:

1. **Copyright risk**: Curating a royalty-free music library is expensive and legally fragile (see Opus Pro’s "license expiry" warnings).
2. **Static selection**: A dropdown of a few moods cannot match the emotional arc of diverse clips.
3. **No generation-time intelligence**: The clip planner had no say in which music fit which segment.
4. **No user-driven refinement**: Chat and editor could not regenerate or fine-tune music.
5. **Upload ambiguity**: User-uploaded music introduced unclear copyright liability.

This document proposes a unified architecture that replaces the static mood-file approach with an **AI-generated music library backed by a dedicated `Music` table**.

> **Naming note**: `Music` is the internal table/entity name for a music library item. User-facing language and API paths use "music" (e.g., `/api/v1/music`, "Music panel"). A `Music` is **not** an audio track in the video-editing timeline sense; it is one piece of background music stored in the library.

---

## 2. Goals

1. **Eliminate copyright uncertainty** for the platform and its users by defaulting to AI-generated music.
2. **Make music a clip-level creative decision** selected by the Clip Agent based on content and brand defaults.
3. **Enable chat/editor-driven regeneration** so users can refine music with natural language.
4. **Build a reusable asset library** where generated music can be shared across projects and, eventually, across users.
5. **Keep the render pipeline contract unchanged**: Remotion still consumes `render_spec.music.url`.
6. **Defer user uploads** to a future phase with explicit rights management.

---

## 3. Non-Goals

1. **No user-uploaded music in MVP.** The legal and product overhead exceeds MVP value.
2. **No manual audio timeline editing in MVP.** Trim/offset/fade are Phase 2+ features.
3. **No real-time music generation during clip generation.** Music is selected from pre-generated assets; generation only happens on explicit user request via chat/editor.

---

## 4. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Music Library                                       │
│  (pre-generated AI music + user-generated music in future)                  │
│  Stored as: Music row + audio object in S3-compatible object storage         │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Brand Template                                      │
│  musicEnabled: bool                                                           │
│  musicAssetId: UUID | null  ← default music for this brand                  │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Content Director + Clip Agent                       │
│  ContentPlan.derivatives[].music_prompt  ← optional suggestion              │
│  ClipPlan.music_asset_id                ← selected from library             │
│  ClipPlan.music_enabled                 ← per-clip override                 │
│  ClipPlan.music_gain_db                 ← per-clip volume                   │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         services/generation.py                              │
│  Resolve selected asset → ClipMusic                                           │
│  Bake into render_spec.music                                                  │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Remotion Renderer                                   │
│  Play spec.music.url via <Audio />                                          │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Result Editor / Chat                                │
│  - Switch to another existing music asset                                     │
│  - Toggle music / adjust gain                                                 │
│  - Provide prompt → generate new music asset → update clip → re-render        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Source of Truth

| Data | Source of Truth | Rationale |
|---|---|---|
| **Audio bytes** | Object storage (`music/{music_id}.{ext}`) | Current `main` stores uploads/outputs in object storage. Music follows the same convention; legacy `data/music/` is deprecated. |
| **Music metadata** | `music` table (`Music` model) | Dedicated table for music-specific fields (mood, prompt, license, duration, attribution, is_public, generated_by_user_id). |
| **Brand default music** | `BrandTemplate.config.musicId` | Explicit reference to a `Music.id`. User-facing: "default music". |
| **Per-clip music choice** | `Clip.render_spec.music` | The render contract is the runtime source of truth. |
| **Which music is available** | `music` table | DB queries are fast and support search/filter in the UI. |

---

## 6. Data Model

### 6.1 Music Table

**File**: `apps/api/app/models/tables.py`

Why a dedicated table instead of `Asset`?
- The existing `Asset` table requires every row to belong to either a `project_id` or a `speaker_id`. Music library items are global/shared resources, not tied to a specific project or speaker.
- Music has structured metadata (mood, prompt, license, duration, attribution, is_public) that deserves typed columns rather than a JSON blob.

**Binding model**:
- **Platform/default music pieces**: `generated_by_user_id = NULL`, `is_public = TRUE`. Owned by the platform, available to all users.
- **User-generated music pieces via MiniMax**: `generated_by_user_id = <user_id>`, `is_public = TRUE` by default. The user generated it, but it enters the shared library.
- **Future user uploads**: `generated_by_user_id = <user_id>`, `is_public = FALSE` by default. Private until explicitly shared and reviewed.

```python
class Music(Base):
    """Background music piece (DB-backed; audio bytes stay in object storage)."""

    __tablename__ = "music"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    mood = Column(String(50), nullable=False, unique=True)
    title = Column(String(255), nullable=False)
    ext = Column(String(8), nullable=False)
    file_path = Column(String(512), nullable=False)  # object storage key, e.g. "music/{music_id}.mp3"
    size_bytes = Column(Integer, nullable=False)
    duration_seconds = Column(Integer, nullable=True)
    prompt = Column(Text, nullable=True)
    model = Column(String(100), nullable=True)
    generation_id = Column(String(255), nullable=True)
    license = Column(String(100), nullable=True)
    source_url = Column(String(512), nullable=True)
    attribution = Column(Text, nullable=True)
    is_public = Column(Boolean, default=True, nullable=False)
    generated_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)
```

### 6.2 Response Schemas

**File**: `apps/api/app/models/schemas.py`

```python
class MusicResponse(BaseModel):
    id: str
    mood: str
    title: str
    ext: str
    url: str
    size_bytes: int
    duration_seconds: int | None
    prompt: str | None
    license: str | None
    source_url: str | None
    attribution: str | None
    is_public: bool
    created_at: datetime


class MusicGenerateRequest(BaseModel):
    prompt: str
    mood: str | None = None


class MusicMetadataUpdate(BaseModel):
    title: str | None = None
    license: str | None = None
    source_url: str | None = None
    attribution: str | None = None
    is_public: bool | None = None
```

### 6.3 Brand Template Config

```python
class BrandTemplateConfig(BaseModel):
    ...
    musicEnabled: bool = True
    musicId: str | None = None            # NEW: replaces musicMood
    musicGainDb: float = -18.0                 # NEW
```

**Migration note**: Existing templates with `musicMood` should be migrated to point to the corresponding pre-generated AI music piece, or left as `musicId=None` and resolved by the Clip Agent.

### 6.4 Clip Plan Extension

```python
class ClipPlan(BaseModel):
    ...
    music_id: str | None = None
    music_enabled: bool = True
    music_gain_db: float = -18.0
```

### 6.5 Render Spec Contract

`render_spec.music` remains:

```typescript
interface ClipMusic {
  music_id: string | null;
  url: string | null;
  enabled: boolean;
  gain_db: number;
  // Future (not implemented):
  // start_in_video_seconds?: number;
  // start_in_music_seconds?: number;
  // end_in_music_seconds?: number;
}
```

The renderer does not know about music pieces, moods, or the music library. It only plays `url` when `enabled` is true.

---

## 7. Music Library: Pre-Generated Default Music

### 7.1 Rationale

We do **not** generate music during clip generation because:
- It adds latency and cost to every generation.
- The same 3 moods cover the vast majority of speech/conference clips.
- Pre-generated music pieces can be quality-controlled and loop-ready.

Users who want custom music can trigger generation later via chat/editor.

### 7.2 Default Catalog

| Music ID | Title | Mood | Target Content | Suggested Prompt |
|---|---|---|---|---|
| `{calm-uuid}` | Calm Academic | calm | Thoughtful analysis, data explanation, reflective moments | "Minimal ambient piano, no vocals, calm and intellectual, background music for an academic speech, 60 seconds, seamless loop" |
| `{uplifting-uuid}` | Inspiring Vision | uplifting | Call-to-action, emotional climax, vision statements | "Inspiring orchestral strings with gentle piano, no vocals, uplifting and hopeful, cinematic, 60 seconds, seamless loop" |
| `{corporate-uuid}` | Corporate Drive | corporate | Business updates, product launches, growth metrics | "Modern corporate electronic beat, no vocals, confident and professional, steady mid-tempo, 60 seconds, seamless loop" |

### 7.3 Seeding

Default music pieces are created at application startup if they do not exist:

```python
async def seed_default_music(db: AsyncSession) -> None:
    """Ensure the 3 default AI-generated music pieces exist."""
    for spec in DEFAULT_MUSIC_SPECS:
        existing = await db.scalar(
            select(Music).where(Music.mood == spec.mood)
        )
        if existing is None:
            await create_music_from_file(db, spec)
```

Audio files live at `music/{music_id}.{ext}` in object storage.

### 7.4 Artist-Generated Music Pieces (Future)

When the platform has artists or power users, their generated music pieces can also be seeded into the library:

- `kind` is implied by the `prompt` / `model` fields being present.
- `generated_by_user_id: <user_id>`
- `is_public: true` (after review) or `false` (private)
- Artists may receive attribution or revenue share (business decision TBD).

---

## 8. Generation Flow

### 8.1 Building the Generation Context

```python
async def build_generation_context(...) -> GenerationContext:
    ...
    return GenerationContext(
        ...
        music_prompt=None,              # Not used as default; brand default is explicit music piece
        brand_music_id=bt.config.get("musicId") if bt else None,
    )
```

### 8.2 Content Director

The Director may optionally suggest a music mood in `DerivativePlan`:

```python
class DerivativePlan(BaseModel):
    ...
    music_mood: str | None = None      # "calm", "uplifting", "corporate"
```

This is a hint, not a binding selection.

### 8.3 Clip Agent Selection

The Clip Agent prompt receives:

```jinja2
Available music pieces in the library:
- calm: minimal ambient piano, suitable for academic/reflective content
- uplifting: inspiring strings, suitable for emotional peaks and calls to action
- corporate: modern electronic beat, suitable for business/data content

Brand template default music: {{ context.brand_music_id or "none" }}
Content director suggests mood: {{ derivative_plan.music_mood or "none" }}

For this clip, choose:
- music_id: the UUID of the best-fitting music piece
- music_enabled: true/false
- music_gain_db: default -18.0
```

Selection logic:
1. If the brand template has a default music piece and it fits the clip mood, use it.
2. If the Director suggested a mood, pick the music piece with that mood.
3. Otherwise, infer from clip content tone.

### 8.4 Baking into Render Spec

```python
async def build_clip_spec(..., plan: ClipPlan, ...):
    music = ClipMusic(enabled=False, gain_db=-18.0)
    if plan.music_enabled and plan.music_id:
        music_piece = await db.get(Music, UUID(plan.music_id))
        if music_piece and music_piece.file_path:
            music = ClipMusic(
                music_id=str(music_piece.id),
                url=stream_url(music_piece.file_path),  # resolves to public object URL
                enabled=True,
                gain_db=plan.music_gain_db,
            )
    ...
```

No MiniMax API call occurs during generation.

---

## 9. Chat / Editor Regeneration Flow

### 9.1 User Intent Examples

- "Make this more energetic"
- "Change the music to something calmer"
- "Remove background music"
- "Generate a cinematic music piece for this climax"

### 9.2 Chat Model Output

```json
{
  "action": "regenerate_music",
  "prompt": "cinematic drums and strings, no vocals, high energy, motivational speech climax",
  "mood": "uplifting",
  "gain_db": -16
}
```

Or:

```json
{
  "action": "select_music_asset",
  "asset_id": "uuid-of-existing-music-piece"
}
```

Or:

```json
{
  "action": "toggle_music",
  "enabled": false
}
```

### 9.3 Backend Handling

For `regenerate_music`:

1. Call `services/music_generation.generate_music(prompt, mood)`.
2. Save audio object to object storage under `music/{new_music_id}.{ext}`.
3. Create `Music(...)` row with `file_path="music/{new_music_id}.{ext}"`.
4. Update `clip.render_spec.music` with new `music_id` and `url`.
5. Set `clip.render_status = RenderStatus.PENDING`.
6. Worker picks up and re-renders.
7. New music piece enters the shared library (if `is_public=True`).

For `select_music`:

1. Resolve music piece from library.
2. Update `clip.render_spec.music`.
3. Re-render.

### 9.4 Cost Control

Music generation is more expensive than selection. To avoid runaway costs:
- Each project has a budget or generation quota (future).
- Free tier defaults to the 3 pre-generated music pieces; custom generation is a paid/limited feature.
- Generated music pieces are cached as assets so the same prompt does not re-generate.

---

## 10. Music Library UI

### 10.1 In Brand Template

The `/brand-template` page has a **Music** section in the left settings list. Opening it shows:

- A list of available music pieces.
- Each row: title, mood tag, duration, play/pause button, select radio.
- A "Generate new" button that opens a prompt input + generate button.
- A toggle for `musicEnabled`.

### 10.2 In Result Editor

The clip editor shows the current music piece and allows:
- Switch to another music piece from the library.
- Toggle on/off.
- Adjust gain (slider).
- "Generate new" for custom music.

### 10.3 Future: Standalone Music Library

A dedicated `/library/music` page for browsing, searching, and managing all music pieces. Deferred to Phase 2.

---

## 11. User Uploads (Future Phase)

### 11.1 Why Deferred

1. **Copyright liability**: Users may upload copyrighted material without realizing it.
2. **Verification cost**: Detecting ownership is hard and error-prone.
3. **Product focus**: AI-generated music satisfies MVP needs for a European knowledge-speaking audience.

### 11.2 If Added Later

User uploads must include:

1. **Explicit rights attestation**:
   - Checkbox: "I confirm I own the copyright or have a valid license to use this audio."
   - Stored in `Asset.meta.uploader_attestation`.

2. **Terms of Service update**:
   - User retains responsibility for uploaded content.
   - Platform reserves the right to remove infringing content.

3. **Default visibility**:
   - Uploaded music pieces default to `is_public=False`.
   - User can opt-in to share; shared music pieces require platform review before becoming public.

4. **Technical guardrails**:
   - File type restriction: `.mp3`, `.m4a`, `.aac`, `.ogg`, `.wav`.
   - File size limit.
   - Metadata stripping is not required but may be considered.

5. **DMCA / takedown process**:
   - Provide a reporting mechanism.
   - Maintain an audit log of uploads.

### 11.3 Legal Note

Even with attestations, platforms that actively transform user-uploaded copyrighted audio into derivative videos (e.g., background music for a clip) may not fully qualify for DMCA safe harbor in all jurisdictions. Legal counsel should review the Terms of Service and operational model before launching user uploads.

---

## 12. Copyright Strategy

### 12.1 AI-Generated Music

Assuming MiniMax (or chosen provider) grants commercial usage rights for generated audio:

- Default music pieces are platform-owned outputs of the provider's model.
- User-generated music pieces are owned by the user per provider terms, with platform license to host and stream.
- No attribution required for most AI music providers (verify MiniMax terms).

**Action item**: Verify MiniMax music generation Terms of Service for:
- Commercial use allowance.
- Redistribution / platform hosting rights.
- User ownership of generated outputs.
- Whether generated music can be used in videos distributed by end users.

### 12.2 Fallback If AI Terms Are Insufficient

If MiniMax does not grant adequate rights:

1. Use a provider with explicit commercial licenses (e.g., Mubert API, AIVA, Soundraw).
2. Or commission original royalty-free music pieces and own them outright.
3. Or remove music from clips entirely until a clean solution is found.

### 12.3 Public Music Library

When user-generated music becomes public:

- Music pieces with a `prompt` / `model` (AI-generated) are public by default.
- Uploaded music pieces require explicit rights proof before public sharing.
- Platform may watermark or tag public music pieces for auditability.

---

## 13. Integration with Existing Systems

### 13.1 Agent Architecture

The music layer integrates with the 4-layer agent architecture:

- **Layer 1 (GenerationContext)**: carries `brand_music_id`.
- **Layer 2 (Content Director)**: may output `music_mood` in `DerivativePlan`.
- **Layer 3 (Clip Agent)**: selects `music_id`, `music_enabled`, `music_gain_db`.
- **Layer 4 (Consistency Reviser, future)**: may verify that music matches brand voice.

### 13.2 Task Queue

Custom music generation is a heavy task and must run in the worker (`app/worker`), not in FastAPI background tasks. It creates a `RenderStatus.PENDING` clip for re-rendering.

### 13.3 Storage Seams

Music files use the existing storage seam:
- Save: `save_output` or new `save_music_asset` helper.
- Stream: `stream_url(asset.file_url)` → `GET /api/v1/files/{path}`.

### 13.4 Render Service

No changes to `packages/clip/src/Clip.tsx` or `apps/render`. Remotion continues to play `spec.music.url`.

---

## 14. Implementation Phases

### Phase 1: MVP — AI-Generated Defaults + Selection

1. Add `Music` table and Alembic migration.
2. Update storage helpers so generated music objects use the `music/` prefix in object storage.
3. Implement `services/music_generation.py` (MiniMax integration).
4. Generate 3 default music pieces and seed as `Music` rows.
5. Add `/api/v1/music` endpoints (list, generate, get metadata, update metadata, delete).
6. Add streaming endpoint for music pieces.
7. Update `BrandTemplate.config` to use `musicId`.
8. Update `services/brand.py:music_from_template` to resolve music pieces.
9. Update Clip Agent prompt and `ClipPlan` to select music.
10. Add Music panel to `/brand-template`.
11. Add music switch/gain control to clip editor.

### Phase 2: Chat-Driven Regeneration

1. Chat model can output `regenerate_music` / `select_music_asset` / `toggle_music` actions.
2. Worker processes music generation and re-render.
3. Generated assets enter the public library.

### Phase 3: User Uploads

1. Upload endpoint with rights attestation.
2. Uploaded music pieces default to private.
3. Review flow for public sharing.
4. Terms of Service and DMCA process.

### Phase 4: Advanced Audio Editing

1. Per-clip gain automation.
2. Start/end trim in music piece.
3. Fade in/out.
4. Multi-music support (explicitly out of scope until L3).

---

## 15. Open Questions

1. **MiniMax music API details**: endpoint, async/sync, pricing, output format, commercial terms.
2. **Audio length**: should default music pieces be 60s loops, 2min pieces, or full-length?
3. **Looping behavior**: Remotion `<Audio loop>` is the current path; do we need crossfade or seamless-loop metadata?
4. **Public library moderation**: who reviews user-generated public music pieces?
5. **Revenue sharing**: if artists contribute music pieces, how are they credited/compensated?
6. **Quota model**: how many custom music generations per user/tier?
7. **Migration**: how to handle existing clips that reference old `musicMood` strings?

---

## 16. Related Documents

- `docs/DECISIONS.md` ADR-019: Built-in mood music library (filesystem-only, superseded by this doc).
- `docs/DECISIONS.md` ADR-022: Music library CRUD (management layer, partial overlap).
- `docs/DECISIONS.md` ADR-023: Music becomes an AI-generated, asset-based library.
- `docs/VIDEO_EDITOR.md` (`render_spec.music` contract).
- `docs/AGENT_ARCHITECTURE.md` (4-layer agent integration).
- `docs/tasks/todo.md`: Original narrow task brief.
- `docs/tasks/music-asset-library.md`: Implementation todo for this architecture.

---

## 17. Summary

Repurposer’s music architecture moves from a **static, file-based mood library** to an **AI-generated music library backed by a dedicated `music` table**:

- **Default**: 3 pre-generated AI music pieces (`calm`, `uplifting`, `corporate`) cover most speech/conference clips.
- **Selection**: Clip Agent picks the best existing music piece per clip, influenced by brand defaults and content mood.
- **Refinement**: Users can switch music pieces or generate custom music via chat/editor.
- **Reusability**: All generated music becomes a `Music` in the library, shareable across projects and eventually users.
- **Copyright**: Platform defaults to AI-generated music to avoid licensing fragility; user uploads are deferred and will require explicit rights management.

This design keeps the render contract stable, integrates cleanly with the 4-layer agent architecture, and gives the product a scalable path from MVP to a community-driven music library.
