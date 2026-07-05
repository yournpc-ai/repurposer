# Repurposer Music Architecture

> Status: Proposed  
> Last updated: 2026-07-05  
> Author: Claude + Product Team  
> Related: ADR-019 (built-in mood music library), ADR-022 (music track library CRUD), `docs/tasks/todo.md`

---

## 1. Background

Background music is a critical creative layer for vertical clips generated from speeches and conference talks. It influences emotional tone, watch-through rate, and the perceived professionalism of the final output.

Historically, Repurposer treated music as a static brand-template setting (`musicMood: "calm"`) resolved to a file on disk (`data/music/{mood}.<ext>`). This created several problems:

1. **Copyright risk**: Curating a royalty-free music library is expensive and legally fragile (see Opus Pro’s "license expiry" warnings).
2. **Static selection**: A dropdown of a few moods cannot match the emotional arc of diverse clips.
3. **No generation-time intelligence**: The clip planner had no say in which music fit which segment.
4. **No user-driven refinement**: Chat and editor could not regenerate or fine-tune music.
5. **Upload ambiguity**: User-uploaded music introduced unclear copyright liability.

This document proposes a unified architecture that replaces the static mood-file approach with an **AI-generated, asset-based music library**.

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
│                         Music Asset Library                                 │
│  (pre-generated AI tracks + user-generated tracks in future)                │
│  Stored as: Asset(type="music") + audio file on disk                        │
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
| **Audio bytes** | File on disk (`data/music/assets/{asset_id}.mp3`) | The render pipeline streams files; the DB should not hold blobs. |
| **Music metadata** | `Asset` table + `Asset.meta` JSON | Reuses existing asset infrastructure; supports title, mood, prompt, license, generation model. |
| **Brand default music** | `BrandTemplate.config.musicAssetId` | Explicit reference, not a mood string that may resolve differently later. |
| **Per-clip music choice** | `Clip.render_spec.music` | The render contract is the runtime source of truth. |
| **Which music is available** | `Asset` table filtered by `type="music"` | DB queries are fast and support search/filter in the UI. |

---

## 6. Data Model

### 6.1 Asset Type Extension

```python
class AssetType(StrEnum):
    VIDEO = "video"
    AUDIO = "audio"
    TRANSCRIPT = "transcript"
    SLIDES = "slides"
    IMAGE = "image"
    VOICE_SAMPLE = "voice_sample"
    PAST_MATERIAL = "past_material"
    MUSIC = "music"          # NEW
```

### 6.2 Music Asset Meta Schema

```python
class MusicAssetMeta(BaseModel):
    """Metadata stored in Asset.meta for music assets."""

    kind: Literal["ai-generated", "uploaded"]
    title: str
    mood: str | None = None                    # e.g. calm, uplifting, corporate
    prompt: str | None = None                  # generation prompt, if ai-generated
    model: str | None = None                   # e.g. "minimax-music-v1"
    generation_id: str | None = None           # provider-specific generation id
    duration_seconds: int | None = None
    license: str = "ai-generated"              # or "user-uploaded", "royalty-free", etc.
    source_url: str | None = None              # original source, if applicable
    attribution: str | None = None             # required attribution text
    is_public: bool = True                     # visible to other users (future)
    generated_by_user_id: str | None = None    # for attribution/auditing
```

### 6.3 Brand Template Config

```python
class BrandTemplateConfig(BaseModel):
    ...
    musicEnabled: bool = True
    musicAssetId: str | None = None            # NEW: replaces musicMood
    musicGainDb: float = -18.0                 # NEW
```

**Migration note**: Existing templates with `musicMood` should be migrated to point to the corresponding pre-generated AI asset, or left as `musicAssetId=None` and resolved by the Clip Agent.

### 6.4 Clip Plan Extension

```python
class ClipPlan(BaseModel):
    ...
    music_asset_id: str | None = None
    music_enabled: bool = True
    music_gain_db: float = -18.0
```

### 6.5 Render Spec Contract

`render_spec.music` remains:

```typescript
interface ClipMusic {
  track_id: string | null;
  url: string | null;
  enabled: boolean;
  gain_db: number;
  // Future (not implemented):
  // start_in_video_seconds?: number;
  // start_in_track_seconds?: number;
  // end_in_track_seconds?: number;
}
```

The renderer does not know about assets, moods, or the music library. It only plays `url` when `enabled` is true.

---

## 7. Music Library: Pre-Generated Default Assets

### 7.1 Rationale

We do **not** generate music during clip generation because:
- It adds latency and cost to every generation.
- The same 3 moods cover the vast majority of speech/conference clips.
- Pre-generated tracks can be quality-controlled and loop-ready.

Users who want custom music can trigger generation later via chat/editor.

### 7.2 Default Catalog

| Asset ID | Title | Mood | Target Content | Suggested Prompt |
|---|---|---|---|---|
| `{calm-uuid}` | Calm Academic | calm | Thoughtful analysis, data explanation, reflective moments | "Minimal ambient piano, no vocals, calm and intellectual, background music for an academic speech, 60 seconds, seamless loop" |
| `{uplifting-uuid}` | Inspiring Vision | uplifting | Call-to-action, emotional climax, vision statements | "Inspiring orchestral strings with gentle piano, no vocals, uplifting and hopeful, cinematic, 60 seconds, seamless loop" |
| `{corporate-uuid}` | Corporate Drive | corporate | Business updates, product launches, growth metrics | "Modern corporate electronic beat, no vocals, confident and professional, steady mid-tempo, 60 seconds, seamless loop" |

### 7.3 Seeding

Default assets are created at application startup if they do not exist:

```python
async def seed_default_music_assets(db: AsyncSession) -> None:
    """Ensure the 3 default AI-generated music assets exist."""
    for spec in DEFAULT_MUSIC_SPECS:
        existing = await db.scalar(
            select(Asset).where(
                Asset.type == AssetType.MUSIC,
                Asset.meta["mood"].as_string() == spec.mood
            )
        )
        if existing is None:
            await create_music_asset_from_file(db, spec)
```

Audio files live at `data/music/assets/{asset_id}.mp3`.

### 7.4 Artist-Generated Tracks (Future)

When the platform has artists or power users, their generated tracks can also be seeded into the library:

- `kind: "ai-generated"`
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
        music_prompt=None,              # Not used as default; brand default is explicit asset
        brand_music_asset_id=bt.config.get("musicAssetId") if bt else None,
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
Available music assets in the library:
- calm: minimal ambient piano, suitable for academic/reflective content
- uplifting: inspiring strings, suitable for emotional peaks and calls to action
- corporate: modern electronic beat, suitable for business/data content

Brand template default music: {{ context.brand_music_asset_id or "none" }}
Content director suggests mood: {{ derivative_plan.music_mood or "none" }}

For this clip, choose:
- music_asset_id: the UUID of the best-fitting track
- music_enabled: true/false
- music_gain_db: default -18.0
```

Selection logic:
1. If the brand template has a default asset and it fits the clip mood, use it.
2. If the Director suggested a mood, pick the asset with that mood.
3. Otherwise, infer from clip content tone.

### 8.4 Baking into Render Spec

```python
async def build_clip_spec(..., plan: ClipPlan, ...):
    music = ClipMusic(enabled=False, gain_db=-18.0)
    if plan.music_enabled and plan.music_asset_id:
        asset = await db.get(Asset, UUID(plan.music_asset_id))
        if asset and asset.type == AssetType.MUSIC:
            music = ClipMusic(
                track_id=str(asset.id),
                url=stream_url(asset.file_url),
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
- "Generate a cinematic track for this climax"

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
  "asset_id": "uuid-of-existing-track"
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

1. Call `services/music_generation.generate_track(prompt, mood)`.
2. Save audio file to `data/music/assets/{new_uuid}.mp3`.
3. Create `Asset(type="music", kind="ai-generated", meta={...})`.
4. Update `clip.render_spec.music` with new `track_id` and `url`.
5. Set `clip.render_status = RenderStatus.PENDING`.
6. Worker picks up and re-renders.
7. New asset enters the shared library (if `is_public=True`).

For `select_music_asset`:

1. Resolve asset from library.
2. Update `clip.render_spec.music`.
3. Re-render.

### 9.4 Cost Control

Music generation is more expensive than selection. To avoid runaway costs:
- Each project has a budget or generation quota (future).
- Free tier defaults to the 3 pre-generated tracks; custom generation is a paid/limited feature.
- Generated tracks are cached as assets so the same prompt does not re-generate.

---

## 10. Asset Library UI

### 10.1 In Brand Template

The `/brand-template` page has a **Music** section in the left settings list. Opening it shows:

- A list of available music assets.
- Each row: title, mood tag, duration, play/pause button, select radio.
- A "Generate new" button that opens a prompt input + generate button.
- A toggle for `musicEnabled`.

### 10.2 In Result Editor

The clip editor shows the current music asset and allows:
- Switch to another asset from the library.
- Toggle on/off.
- Adjust gain (slider).
- "Generate new" for custom music.

### 10.3 Future: Standalone Music Library

A dedicated `/library/music` page for browsing, searching, and managing all music assets. Deferred to Phase 2.

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
   - Uploaded tracks default to `is_public=False`.
   - User can opt-in to share; shared tracks require platform review before becoming public.

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

- Default tracks are platform-owned outputs of the provider's model.
- User-generated tracks are owned by the user per provider terms, with platform license to host and stream.
- No attribution required for most AI music providers (verify MiniMax terms).

**Action item**: Verify MiniMax music generation Terms of Service for:
- Commercial use allowance.
- Redistribution / platform hosting rights.
- User ownership of generated outputs.
- Whether generated music can be used in videos distributed by end users.

### 12.2 Fallback If AI Terms Are Insufficient

If MiniMax does not grant adequate rights:

1. Use a provider with explicit commercial licenses (e.g., Mubert API, AIVA, Soundraw).
2. Or commission original royalty-free tracks and own them outright.
3. Or remove music from clips entirely until a clean solution is found.

### 12.3 Public Asset Library

When user-generated music becomes public:

- Only `ai-generated` tracks are public by default.
- `uploaded` tracks require explicit rights proof before public sharing.
- Platform may watermark or tag public tracks for auditability.

---

## 13. Integration with Existing Systems

### 13.1 Agent Architecture

The music layer integrates with the 4-layer agent architecture:

- **Layer 1 (GenerationContext)**: carries `brand_music_asset_id`.
- **Layer 2 (Content Director)**: may output `music_mood` in `DerivativePlan`.
- **Layer 3 (Clip Agent)**: selects `music_asset_id`, `music_enabled`, `music_gain_db`.
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

1. Add `AssetType.MUSIC`.
2. Implement `services/music_generation.py` (MiniMax integration).
3. Generate 3 default tracks and seed as assets.
4. Add `/api/v1/music` endpoints (list, generate, get metadata).
5. Update `BrandTemplate.config` to use `musicAssetId`.
6. Update `services/brand.py:music_from_template` to resolve assets.
7. Update Clip Agent prompt and `ClipPlan` to select music.
8. Add Music panel to `/brand-template`.
9. Add music switch/gain control to clip editor.

### Phase 2: Chat-Driven Regeneration

1. Chat model can output `regenerate_music` / `select_music_asset` / `toggle_music` actions.
2. Worker processes music generation and re-render.
3. Generated assets enter the public library.

### Phase 3: User Uploads

1. Upload endpoint with rights attestation.
2. Uploaded tracks default to private.
3. Review flow for public sharing.
4. Terms of Service and DMCA process.

### Phase 4: Advanced Audio Editing

1. Per-clip gain automation.
2. Start/end trim in track.
3. Fade in/out.
4. Multi-track support (explicitly out of scope until L3).

---

## 15. Open Questions

1. **MiniMax music API details**: endpoint, async/sync, pricing, output format, commercial terms.
2. **Audio length**: should default tracks be 60s loops, 2min tracks, or full-length?
3. **Looping behavior**: Remotion `<Audio loop>` is the current path; do we need crossfade or seamless-loop metadata?
4. **Public library moderation**: who reviews user-generated public tracks?
5. **Revenue sharing**: if artists contribute tracks, how are they credited/compensated?
6. **Quota model**: how many custom music generations per user/tier?
7. **Migration**: how to handle existing clips that reference old `musicMood` strings?

---

## 16. Related Documents

- `docs/DECISIONS.md` ADR-019: Built-in mood music library (filesystem-only, superseded by this doc).
- `docs/DECISIONS.md` ADR-022: Music track library CRUD (management layer, partial overlap).
- `docs/VIDEO_EDITOR.md`: Clip-spec contract and renderer-agnostic design.
- `docs/AGENT_ARCHITECTURE.md`: 4-layer agent architecture.
- `docs/tasks/todo.md`: Original narrow task brief.

---

## 17. Summary

Repurposer’s music architecture moves from a **static, file-based mood library** to an **AI-generated, asset-based music system**:

- **Default**: 3 pre-generated AI tracks (`calm`, `uplifting`, `corporate`) cover most speech/conference clips.
- **Selection**: Clip Agent picks the best existing track per clip, influenced by brand defaults and content mood.
- **Refinement**: Users can switch tracks or generate custom music via chat/editor.
- **Reusability**: All generated music becomes an Asset in the library, shareable across projects and eventually users.
- **Copyright**: Platform defaults to AI-generated music to avoid licensing fragility; user uploads are deferred and will require explicit rights management.

This design keeps the render contract stable, integrates cleanly with the 4-layer agent architecture, and gives the product a scalable path from MVP to a community-driven music library.
