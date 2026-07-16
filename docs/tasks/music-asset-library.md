# Task: AI-Generated Music Library

> **Base branch**: `main` (current)  
> **Architecture reference**: `docs/MUSIC_ARCHITECTURE.md`  
> **Decision record**: `docs/DECISIONS.md` ADR-023  
> **Status**: Ready for implementation  
> **Owner**: TBD  

---

## 1. Project Docs Map

Read these in order before writing code:

| Doc | Purpose |
|---|---|
| `README.md` | Project overview, tech stack, quick start. |
| `CLAUDE.md` | Frontend conventions: shadcn/base-ui (`render` prop, not `asChild`), Tailwind, lucide icons, i18n workflow, Sidebar/Composer patterns. |
| `docs/MUSIC_ARCHITECTURE.md` | **This task's full architecture.** Covers goals, data model, flows, UI, copyright strategy, phases. |
| `docs/DECISIONS.md` ADR-023 | High-level decision record. |
| `docs/AGENT_ARCHITECTURE.md` | 4-layer agent flow; understand where music selection happens (Clip Agent). |
| `docs/VIDEO_EDITOR.md` | `render_spec.music` contract and renderer-agnostic design. |
| `docs/API.md` | API conventions. |

---

## 2. Current Functional Status

### What already works on `main`

1. **Render pipeline supports music**:
   - `render_spec.music` has `music_id`, `url`, `enabled`, `gain_db`.
   - Remotion `Clip.tsx` plays `spec.music.url` via `<Audio>`.
   - `GET /api/v1/music/{mood}` in `apps/api/app/routers/files.py` serves audio with Range support.

2. **Brand template has a music dropdown**:
   - `apps/web/src/routes/brand-template.tsx` has a `Select` for `musicMood` with hardcoded options: `calm`, `uplifting`, `corporate`, `none`.
   - `BrandTemplate.config.musicMood` is persisted.
   - `services/brand.py:music_from_template` maps `musicMood` → `ClipMusic` with URL `/api/v1/music/{mood}`.

3. **Storage helpers exist**:
   - `apps/api/app/services/storage.py:music_stream_url(music_id)` returns the public object URL for `music/{music_id}.mp3`.

4. **Clip Spec builder handles music**:
   - `services/clip_spec.py:build_clip_spec` receives `music: ClipMusic` and bakes it into `render_spec`.

### What does NOT work yet

1. No actual audio objects in object storage under `music/` (legacy `data/music/` existed historically).
2. No `music` table for the music library.
3. No MiniMax music generation integration.
4. No music library UI beyond the simple mood dropdown.
5. No chat/editor-driven music regeneration.
6. Clip Agent does not select music based on content.
7. No concept of `musicId` in brand template.
8. The existing `Asset` table requires every asset to belong to a `project_id` or `speaker_id`, which does not fit global/shared music library items.

---

## 3. Target Functional Status

After this task, the product should support:

1. **3 pre-generated AI music pieces** (`calm`, `uplifting`, `corporate`) seeded at startup.
2. **Brand Template Music panel**:
   - List available music pieces.
   - Preview each music piece.
   - Select one as the brand default.
   - Toggle music on/off.
   - Generate a new custom music piece from a prompt (optional but desirable in this phase).
3. **Clip Agent music selection**:
   - Picks an existing music piece per clip based on content tone and brand default.
   - Outputs `music_id`, `music_enabled`, `music_gain_db` in `ClipPlan`.
4. **Generation orchestration**:
   - Resolves selected music piece → `ClipMusic` → `render_spec.music`.
   - No MiniMax API call during clip generation.
5. **Result Editor music controls**:
   - Switch to another existing music piece.
   - Toggle on/off.
   - Adjust gain.
   - *(Optional)* Generate new music from prompt.
6. **Chat-driven regeneration** *(optional but desirable)*:
   - User says "make it more energetic" → chat model outputs music action → generate/select → re-render.

---

## 4. Code Implementation Guidance

### 4.1 Backend

#### Step 1: Add `Music` table

**File**: `apps/api/app/models/tables.py`

Why a dedicated table instead of `Asset`?
- The existing `Asset` table requires every row to belong to either a `project_id` or a `speaker_id` (see its `CheckConstraint`).
- Music library items are global/shared resources, not tied to a specific project or speaker.
- Music has structured metadata (mood, prompt, license, duration, attribution, is_public, generated_by_user_id) that is awkward to store in `Asset.meta` JSON.

**Binding model**:
- **Platform/default music pieces**: `generated_by_user_id = NULL`, `is_public = TRUE`. Owned by the platform, available to all users.
- **User-generated music pieces via MiniMax**: `generated_by_user_id = <user_id>`, `is_public = TRUE` by default. Enters the shared library.
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

**Also add**: Alembic migration `apps/api/migrations/versions/xxxx_add_music_table.py`.

#### Step 2: Add request/response schemas

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

#### Step 3: Add music generation service

**File**: `apps/api/app/services/music_generation.py` (new)

Responsibilities:
- Call MiniMax music generation API.
- Save generated audio object to object storage under `music/{music_id}.{ext}`.
- Return object key + duration (if available from response).

**Interface sketch**:

```python
async def generate_music(
    prompt: str,
    mood: str | None = None,
) -> tuple[str, int | None]:
    """Generate a music piece via MiniMax and save to object storage.

    Returns (key, duration_seconds).
    """
```

**Important**: If MiniMax music API is async/callback-based, design accordingly. If it does not exist or terms are unclear, **stop and escalate** before proceeding.

#### Step 4: Add music service

**File**: `apps/api/app/services/music.py` (new)

Responsibilities:
- `list_music(db)` — list all public + user's own music pieces.
- `get_music(db, music_id)` / `get_music_by_mood(db, mood)`.
- `create_music_from_upload(db, file, filename, ...)` — for future uploads.
- `create_music_from_generation(db, prompt, mood, file_path, duration, user_id)` — after MiniMax returns audio.
- `update_music_metadata(db, music_id, updates)`.
- `delete_music(db, music_id)` — delete row + file; guard if used by clips.
- `seed_default_music(db)` — create the 3 default music pieces if missing.
- `is_music_in_use(db, music_id) -> bool`.

#### Step 5: Guard deletion with Clip reference check

In `delete_music`, query:

```python
from sqlalchemy import func, select
from app.models.tables import Clip

count = await db.scalar(
    select(func.count())
    .select_from(Clip)
    .where(Clip.render_spec["music"]["music_id"].as_string() == str(music_id))
)
if count and count > 0:
    raise MusicInUseError(music_id, int(count))
```

*Note*: JSON path indexing depends on your DB (Postgres supports it well). If testing on SQLite, adjust or skip the JSON query in tests.

#### Step 6: Add music API endpoints

**File**: `apps/api/app/routers/music.py` (new)

Routes:
- `GET /api/v1/music` — list music pieces.
- `GET /api/v1/music/{music_id}` — get metadata.
- `POST /api/v1/music/generate` — generate new music from prompt. Accepts `{ "prompt": "...", "mood": "..." }`.
- `PUT /api/v1/music/{music_id}` — update metadata.
- `DELETE /api/v1/music/{music_id}` — delete music piece (with clip reference guard).

**File**: `apps/api/app/routers/__init__.py` — export `music` router.  
**File**: `apps/api/app/main.py` — register router and call `seed_default_music` on startup.

#### Step 7: Add streaming endpoint for music pieces

**Option A** (recommended): Extend `GET /api/v1/music/{music_id}` to stream the audio file.

**Option B**: Reuse the existing `/api/v1/music/{mood}` endpoint and map `mood` to a `Music`. This keeps legacy clips working but couples the URL to the mood natural key.

**Recommended**: Keep `/api/v1/music/{mood}` for legacy, add `/api/v1/music/{music_id}/stream` for new music pieces. Store the new stream URL in `render_spec.music.url`.

#### Step 8: Generate 3 default music pieces

Options:
- **A**: Generate via MiniMax once, upload the 3 MP3 objects to object storage under `music/`, and write a seed script that creates `Music` rows pointing to them.
- **B**: If MP3 files are too large for git, generate them via a one-time script (`scripts/seed_default_music.py`) and run it in production.

Recommended: **A** for reproducibility, **B** if files are >10MB each.

Default catalog:

| Mood | Title | Suggested Prompt |
|---|---|---|
| `calm` | Calm Academic | "Minimal ambient piano, no vocals, calm and intellectual, background music for an academic speech, 60 seconds, seamless loop" |
| `uplifting` | Inspiring Vision | "Inspiring orchestral strings with gentle piano, no vocals, uplifting and hopeful, cinematic, 60 seconds, seamless loop" |
| `corporate` | Corporate Drive | "Modern corporate electronic beat, no vocals, confident and professional, steady mid-tempo, 60 seconds, seamless loop" |

#### Step 9: Update brand template config

**File**: `apps/api/app/models/schemas.py`

Add to the brand template config schema:

```python
musicEnabled: bool = True
musicId: str | None = None   # NEW: replaces musicMood
musicGainDb: float = -18.0        # NEW
```

**File**: `apps/api/app/services/brand.py`

Update `music_from_template`:

```python
async def music_from_template(
    db: AsyncSession,
    config: dict[str, Any] | None,
    default_music_id: str | None = None,
) -> ClipMusic:
    cfg = config or {}
    if not cfg.get("musicEnabled", True):
        return ClipMusic(enabled=False, gain_db=cfg.get("musicGainDb", -18.0))

    music_id = cfg.get("musicId") or default_music_id
    if music_id:
        music_piece = await db.get(Music, UUID(music_id))
        if music_piece:
            return ClipMusic(
                music_id=str(music_piece.id),
                url=f"/api/v1/music/{music_piece.id}/stream",  # resolves under asset_dir
                enabled=True,
                gain_db=cfg.get("musicGainDb", -18.0),
            )
    return ClipMusic(enabled=False, gain_db=cfg.get("musicGainDb", -18.0))
```

*Note*: This becomes async because it queries the DB. Update callers accordingly.

#### Step 10: Update Clip Agent

**File**: `apps/api/app/agents/clip_agent.py`  
**File**: `apps/api/app/prompts/clip_agent.j2`

- Add `music_id`, `music_enabled`, `music_gain_db` to `ClipPlan`.
- Update prompt to include available music pieces and brand default.
- Let agent select per clip.

#### Step 11: Update generation orchestration

**File**: `apps/api/app/services/generation.py`

When building clip spec:
- Resolve `plan.music_id` to a `Music`.
- Build `ClipMusic` from the music piece's stream URL (resolves under `asset_dir`).
- Respect `plan.music_enabled` and `plan.music_gain_db`.

### 4.2 Frontend

#### Step 1: Create MusicPanel component

**File**: `apps/web/src/components/brand-template/music-panel.tsx` (new)

Features:
- Fetch `/api/v1/music`.
- List music pieces with title, mood, duration.
- Play/pause preview (use `<audio>` with `src={music.url}`).
- Radio/select to set brand default.
- Toggle `musicEnabled`.
- *(Optional)* "Generate new" button with prompt input.

Use shadcn components: `Button`, `Card`, `Slider`, `Toggle`, `Input`, etc.  
Icons from `lucide-react` only.

#### Step 2: Update brand-template route

**File**: `apps/web/src/routes/brand-template.tsx`

- Add "Music" row to the left settings list.
- Render `<MusicPanel />` in the right panel.
- Replace `musicMood` Select with the new panel.
- Persist `musicId`, `musicEnabled`, `musicGainDb` instead of `musicMood`.

#### Step 3: Add i18n keys

**Files**: `apps/web/src/lib/i18n/locales/en.ts`, `apps/web/src/lib/i18n/locales/zh.ts`

Add keys like:
- `brandTemplate.music.title`
- `brandTemplate.music.enable`
- `brandTemplate.music.generate`
- `brandTemplate.music.generatePrompt`
- `brandTemplate.music.noMusic`
- `brandTemplate.music.play`
- `brandTemplate.music.pause`
- `brandTemplate.music.select`
- `brandTemplate.music.gain`

#### Step 4: Update clip editor

**File**: `apps/web/src/routes/projects.$id.clips.$clipId.tsx` (or wherever the clip editor lives)

Add a Music section:
- Dropdown to select from existing music pieces.
- Toggle enabled.
- Gain slider.
- *(Optional)* "Generate new" button.

On change, PUT/PATCH the clip's `render_spec.music` and trigger re-render.

### 4.3 Tests

**File**: `apps/api/tests/test_music.py` (new)

Cover:
- List music pieces.
- Generate new music (mock MiniMax if needed).
- Delete music piece with clip reference → 409.
- Clip Agent selects music based on content.
- Brand template resolves default music piece to `ClipMusic`.

---

## 5. Prohibited Behaviors

### Do NOT do these

1. **Do NOT add a foreign key from `Clip.music_mood` to `music`**.
   - `Clip.music_mood` is a legacy string field. The per-clip music choice lives in `Clip.render_spec.music`, not the DB schema.
   - Adding an FK would break existing data and constrain the render contract.

2. **Do NOT call MiniMax music generation during clip generation**.
   - Music is selected from pre-generated music pieces during generation.
   - Generation API is only called on explicit user request via chat/editor.

3. **Do NOT change the render contract structure**.
   - `render_spec.music` keeps `music_id`, `url`, `enabled`, `gain_db`.
   - Remotion `Clip.tsx` should not need modification beyond the field rename.

4. **Do NOT delete or ignore the legacy `/api/v1/music/{mood}` endpoint** until legacy clips are migrated.
   - Existing clips may reference `/api/v1/music/calm`. Keep it working or migrate URLs.

5. **Do NOT implement user-uploaded music in this phase**.
   - Out of MVP scope. Defer to Phase 3 per `docs/MUSIC_ARCHITECTURE.md`.

6. **Do NOT implement audio timeline editing (trim/offset/fade) in this phase**.
   - Out of MVP scope. Defer to Phase 4.

7. **Do NOT store audio files in the database**.
   - Files go to object storage under `music/`; metadata goes to the `music` table.

8. **Do NOT reuse the `Asset` table for music pieces without removing its project/speaker ownership constraints**.
   - The existing `Asset` table requires `project_id` or `speaker_id`. Music pieces are global library items.
   - If you really want to unify, modify the `Asset` constraints first and document it — but a dedicated `music` table is preferred.

9. **Do NOT modify `packages/clip/src/Clip.tsx` or `services/clip_spec.py` unless absolutely necessary**.
   - The render contract already supports music.

10. **Do NOT base this work on the old `feat/music-template-ui` or `feat/music-library-Dushyant` branches**.
    - Those branches are stale and diverged from `main`. Start fresh from `main` and cherry-pick useful ideas only.
10. **Do NOT base this work on the old `feat/music-template-ui` or `feat/music-library-Dushyant` branches**.
    - Those branches are stale and diverged from `main`. Start fresh from `main` and cherry-pick useful ideas only.

---

## 6. Acceptance Criteria

### Backend

- [ ] `Music` table exists with migration.
- [ ] `GET /api/v1/music` returns the 3 default music pieces on a fresh startup.
- [ ] `POST /api/v1/music/generate` creates a new music piece (MiniMax integration works or is mocked with a clear path forward).
- [ ] `DELETE /api/v1/music/{music_id}` returns 409 if the music piece is referenced by any clip.
- [ ] `BrandTemplate.config` supports `musicId`, `musicEnabled`, `musicGainDb`.
- [ ] `services/brand.py:music_from_template` resolves by music id.
- [ ] `ClipPlan` includes `music_id`, `music_enabled`, `music_gain_db`.
- [ ] Clip Agent prompt includes available music pieces and selects per clip.
- [ ] `services/generation.py` bakes selected music piece into `render_spec.music`.
- [ ] All existing backend tests still pass: `uv run pytest -q`.

### Frontend

- [ ] `/brand-template` has a Music panel with music list, preview, selection, and toggle.
- [ ] Music selection is persisted as `musicId`.
- [ ] Clip editor allows switching music piece, toggling, and adjusting gain.
- [ ] i18n keys added to both `en.ts` and `zh.ts`.
- [ ] No hard-coded strings in components.

### Assets

- [ ] 3 default MP3 objects exist under `music/` (or generated by seed script).
- [ ] Default music pieces are created at startup if missing.

### Integration

- [ ] A full generation run produces clips with `render_spec.music.url` pointing to a real music piece stream URL.
- [ ] Remotion preview and final render play the selected music.

---

## 7. Out of Scope

- User-uploaded music.
- Audio timeline editing (trim, offset, fade).
- Multiple overlapping music pieces.
- Artist revenue sharing.
- Public music library moderation UI.
- Standalone `/library/music` page.

These are documented in `docs/MUSIC_ARCHITECTURE.md` Phase 2–4 and should not be attempted in this task.

---

## 8. Suggested Branch Name

```
feat/music-asset-library
```

---

## 9. Commit Message Examples

```
feat(api): add music table and default AI-generated music pieces
feat(api): add MiniMax music generation service
feat(api): add /api/v1/music endpoints
feat(web): add MusicPanel to brand-template
feat(web): add music controls to clip editor
feat(agent): select music piece per clip in Clip Agent
test(api): add music piece lifecycle tests
```

---

## 10. Need Help?

- Architecture questions: read `docs/MUSIC_ARCHITECTURE.md`.
- Frontend conventions: read `CLAUDE.md`.
- API contracts: read `docs/API.md`.
- Render contract: read `docs/VIDEO_EDITOR.md`.
- If MiniMax music API terms or endpoint details are unclear, escalate before implementing generation.
