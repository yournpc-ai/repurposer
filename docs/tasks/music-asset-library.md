# Task: AI-Generated Asset-Based Music Library

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
   - `render_spec.music` has `track_id`, `url`, `enabled`, `gain_db`.
   - Remotion `Clip.tsx` plays `spec.music.url` via `<Audio>`.
   - `GET /api/v1/music/{mood}` in `apps/api/app/routers/files.py` serves audio with Range support.

2. **Brand template has a music dropdown**:
   - `apps/web/src/routes/brand-template.tsx` has a `Select` for `musicMood` with hardcoded options: `calm`, `uplifting`, `corporate`, `none`.
   - `BrandTemplate.config.musicMood` is persisted.
   - `services/brand.py:music_from_template` maps `musicMood` → `ClipMusic` with URL `/api/v1/music/{mood}`.

3. **Storage helpers exist**:
   - `apps/api/app/services/storage.py:resolve_music_safe(name)` finds `data/music/{name}.<ext>`.
   - `music_url(mood)` returns `/api/v1/music/{mood}`.

4. **Clip Spec builder handles music**:
   - `services/clip_spec.py:build_clip_spec` receives `music: ClipMusic` and bakes it into `render_spec`.

### What does NOT work yet

1. No actual audio files in `data/music/` (only `.gitkeep` and `README.md`).
2. No `AssetType.MUSIC`.
3. No music asset library UI beyond the simple mood dropdown.
4. No MiniMax music generation integration.
5. No chat/editor-driven music regeneration.
6. Clip Agent does not select music based on content.
7. No concept of `musicAssetId` in brand template.

---

## 3. Target Functional Status

After this task, the product should support:

1. **3 pre-generated AI music assets** (`calm`, `uplifting`, `corporate`) seeded at startup.
2. **Brand Template Music panel**:
   - List available music assets.
   - Preview each track.
   - Select one as the brand default.
   - Toggle music on/off.
   - Generate a new custom track from a prompt (optional but desirable in this phase).
3. **Clip Agent music selection**:
   - Picks an existing music asset per clip based on content tone and brand default.
   - Outputs `music_asset_id`, `music_enabled`, `music_gain_db` in `ClipPlan`.
4. **Generation orchestration**:
   - Resolves selected asset → `ClipMusic` → `render_spec.music`.
   - No MiniMax API call during clip generation.
5. **Result Editor music controls**:
   - Switch to another existing asset.
   - Toggle on/off.
   - Adjust gain.
   - *(Optional)* Generate new music from prompt.
6. **Chat-driven regeneration** *(optional but desirable)*:
   - User says "make it more energetic" → chat model outputs music action → generate/select → re-render.

---

## 4. Code Implementation Guidance

### 4.1 Backend

#### Step 1: Add `AssetType.MUSIC`

**File**: `apps/api/app/models/schemas.py`

```python
class AssetType(StrEnum):
    ...
    MUSIC = "music"
```

#### Step 2: Add music asset metadata schema

**File**: `apps/api/app/models/schemas.py`

```python
class MusicAssetKind(StrEnum):
    AI_GENERATED = "ai-generated"
    UPLOADED = "uploaded"


class MusicAssetMeta(BaseModel):
    """Metadata stored in Asset.meta for music assets."""

    model_config = ConfigDict(extra="forbid")

    kind: MusicAssetKind
    title: str
    mood: str | None = None
    prompt: str | None = None
    model: str | None = None
    generation_id: str | None = None
    duration_seconds: int | None = None
    license: str = "ai-generated"
    source_url: str | None = None
    attribution: str | None = None
    is_public: bool = True
    generated_by_user_id: str | None = None
```

#### Step 3: Add music generation service

**File**: `apps/api/app/services/music_generation.py` (new)

Responsibilities:
- Call MiniMax music generation API.
- Save generated audio to `data/music/assets/{uuid}.mp3`.
- Return file path + duration (if available from response).

**Interface sketch**:

```python
async def generate_music_track(
    prompt: str,
    mood: str | None = None,
) -> tuple[Path, int | None]:
    """Generate a music track via MiniMax and save to disk.

    Returns (file_path, duration_seconds).
    """
```

**Important**: If MiniMax music API is async/callback-based, design accordingly. If it does not exist or terms are unclear, **stop and escalate** before proceeding.

#### Step 4: Add music asset service

**File**: `apps/api/app/services/music_assets.py` (new)

Responsibilities:
- `list_music_assets(db)` — list all `Asset(type="music")`.
- `get_music_asset(db, asset_id)` — get one.
- `create_ai_generated_music_asset(db, user_id, prompt, mood, file_path, duration)` — create `Asset` row.
- `seed_default_music_assets(db)` — create the 3 default tracks if missing.
- `delete_music_asset(db, asset_id)` — delete row + file; guard if used by clips (see below).

#### Step 5: Guard deletion with Clip reference check

In `delete_music_asset`, query:

```python
from sqlalchemy import func, select
from app.models.tables import Clip

count = await db.scalar(
    select(func.count())
    .select_from(Clip)
    .where(Clip.render_spec["music"]["track_id"].as_string() == str(asset_id))
)
if count and count > 0:
    raise HTTPException(409, f"Asset is used by {count} clip(s)")
```

*Note*: JSON path indexing depends on your DB (Postgres supports it well). If testing on SQLite, adjust or skip the JSON query in tests.

#### Step 6: Add music API endpoints

**File**: `apps/api/app/routers/music.py` (new)

Routes:
- `GET /api/v1/music` — list music assets.
- `GET /api/v1/music/{asset_id}` — get metadata.
- `POST /api/v1/music/generate` — generate new music from prompt. Accepts `{ "prompt": "...", "mood": "..." }`.
- `DELETE /api/v1/music/{asset_id}` — delete asset (with clip reference guard).

**File**: `apps/api/app/routers/__init__.py` — export `music` router.  
**File**: `apps/api/app/main.py` — register router and call `seed_default_music_assets` on startup.

#### Step 7: Generate 3 default tracks

Options:
- **A**: Generate via MiniMax once, commit the 3 MP3 files to `data/music/assets/`, and write a seed script that creates `Asset` rows pointing to them.
- **B**: If MP3 files are too large for git, generate them via a one-time script (`scripts/seed_default_music.py`) and run it in production.

Recommended: **A** for reproducibility, **B** if files are >10MB each.

#### Step 8: Update brand template config

**File**: `apps/api/app/models/schemas.py`

Add to the brand template config schema (or wherever `BrandTemplateConfig` is defined):

```python
musicEnabled: bool = True
musicAssetId: str | None = None
musicGainDb: float = -18.0
```

**File**: `apps/api/app/services/brand.py`

Update `music_from_template`:

```python
def music_from_template(config: dict[str, Any] | None, default_asset_id: str | None = None) -> ClipMusic:
    cfg = config or {}
    if not cfg.get("musicEnabled", True):
        return ClipMusic(enabled=False, gain_db=cfg.get("musicGainDb", -18.0))

    asset_id = cfg.get("musicAssetId") or default_asset_id
    if asset_id:
        return ClipMusic(
            track_id=asset_id,
            url=f"/api/v1/music/{asset_id}",  # or use asset streaming URL
            enabled=True,
            gain_db=cfg.get("musicGainDb", -18.0),
        )
    return ClipMusic(enabled=False, ...)
```

*Note*: You may need to keep the old `/api/v1/music/{mood}` endpoint working for legacy clips, or migrate URLs to asset-based URLs. The render endpoint can remain `/api/v1/music/{mood}` and we add a new endpoint `/api/v1/music-assets/{asset_id}` for assets. Pick one convention and document it.

**Recommended**: Keep `/api/v1/music/{mood}` for legacy, add `/api/v1/files/{asset_file_path}` for asset streaming, and store the asset file URL in `render_spec.music.url`.

#### Step 9: Update Clip Agent

**File**: `apps/api/app/agents/clip_agent.py`  
**File**: `apps/api/app/prompts/clip_agent.j2`

- Add `music_asset_id`, `music_enabled`, `music_gain_db` to `ClipPlan`.
- Update prompt to include available music assets and brand default.
- Let agent select per clip.

#### Step 10: Update generation orchestration

**File**: `apps/api/app/services/generation.py`

When building clip spec:
- Resolve `plan.music_asset_id` to an `Asset`.
- Build `ClipMusic` from asset file URL.
- Respect `plan.music_enabled` and `plan.music_gain_db`.

### 4.2 Frontend

#### Step 1: Create MusicPanel component

**File**: `apps/web/src/components/brand-template/music-panel.tsx` (new)

Features:
- Fetch `/api/v1/music`.
- List assets with title, mood, duration.
- Play/pause preview (use `<audio>` with `src={asset.url}`).
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
- Persist `musicAssetId`, `musicEnabled`, `musicGainDb` instead of `musicMood`.

#### Step 3: Add i18n keys

**Files**: `apps/web/src/lib/i18n/locales/en.ts`, `apps/web/src/lib/i18n/locales/zh.ts`

Add keys like:
- `brandTemplate.music.title`
- `brandTemplate.music.enable`
- `brandTemplate.music.generate`
- `brandTemplate.music.generatePrompt`
- `brandTemplate.music.noTracks`
- `brandTemplate.music.play`
- `brandTemplate.music.pause`
- `brandTemplate.music.select`
- `brandTemplate.music.gain`

#### Step 4: Update clip editor

**File**: `apps/web/src/routes/projects.$id.clips.$clipId.tsx` (or wherever the clip editor lives)

Add a Music section:
- Dropdown to select from existing assets.
- Toggle enabled.
- Gain slider.
- *(Optional)* "Generate new" button.

On change, PUT/PATCH the clip's `render_spec.music` and trigger re-render.

### 4.3 Tests

**File**: `apps/api/tests/test_music.py` (new)

Cover:
- List music assets.
- Generate new music (mock MiniMax if needed).
- Delete asset with clip reference → 409.
- Clip Agent selects music based on content.

---

## 5. Prohibited Behaviors

### Do NOT do these

1. **Do NOT add a foreign key from `Clip.music_mood` to `music_tracks`**.
   - `Clip.music_mood` is a legacy string field. The per-clip music choice lives in `Clip.render_spec.music`, not the DB schema.
   - Adding an FK would break existing data and constrain the render contract.

2. **Do NOT call MiniMax music generation during clip generation**.
   - Music is selected from pre-generated assets during generation.
   - Generation API is only called on explicit user request via chat/editor.

3. **Do NOT change the render contract**.
   - `render_spec.music` must keep `track_id`, `url`, `enabled`, `gain_db`.
   - Remotion `Clip.tsx` should not need modification.

4. **Do NOT delete or ignore the legacy `/api/v1/music/{mood}` endpoint** until legacy clips are migrated.
   - Existing clips may reference `/api/v1/music/calm`. Keep it working or migrate URLs.

5. **Do NOT implement user-uploaded music in this phase**.
   - Out of MVP scope. Defer to Phase 3 per `docs/MUSIC_ARCHITECTURE.md`.

6. **Do NOT implement audio timeline editing (trim/offset/fade) in this phase**.
   - Out of MVP scope. Defer to Phase 4.

7. **Do NOT store audio files in the database**.
   - Files go to disk; metadata goes to the `Asset` table.

8. **Do NOT create a separate `music_tracks` table**.
   - Reuse the existing `Asset` table with `type="music"`.

9. **Do NOT modify `packages/clip/src/Clip.tsx` or `services/clip_spec.py` unless absolutely necessary**.
   - The render contract already supports music.

10. **Do NOT base this work on the old `feat/music-template-ui` or `feat/music-library-Dushyant` branches**.
    - Those branches are stale and diverged from `main`. Start fresh from `main` and cherry-pick useful ideas only.

---

## 6. Acceptance Criteria

### Backend

- [ ] `AssetType.MUSIC` exists.
- [ ] `GET /api/v1/music` returns the 3 default assets on a fresh startup.
- [ ] `POST /api/v1/music/generate` creates a new music asset (MiniMax integration works or is mocked with a clear path forward).
- [ ] `DELETE /api/v1/music/{asset_id}` returns 409 if the asset is referenced by any clip.
- [ ] `BrandTemplate.config` supports `musicAssetId`, `musicEnabled`, `musicGainDb`.
- [ ] `services/brand.py:music_from_template` resolves by asset id.
- [ ] `ClipPlan` includes `music_asset_id`, `music_enabled`, `music_gain_db`.
- [ ] Clip Agent prompt includes available music assets and selects per clip.
- [ ] `services/generation.py` bakes selected asset into `render_spec.music`.
- [ ] All existing backend tests still pass: `uv run pytest -q`.

### Frontend

- [ ] `/brand-template` has a Music panel with asset list, preview, selection, and toggle.
- [ ] Music selection is persisted as `musicAssetId`.
- [ ] Clip editor allows switching music asset, toggling, and adjusting gain.
- [ ] i18n keys added to both `en.ts` and `zh.ts`.
- [ ] No hard-coded strings in components.

### Assets

- [ ] 3 default MP3 files exist under `data/music/assets/` (or generated by seed script).
- [ ] Default assets are created at startup if missing.

### Integration

- [ ] A full generation run produces clips with `render_spec.music.url` pointing to a real music asset.
- [ ] Remotion preview and final render play the selected music.

---

## 7. Out of Scope

- User-uploaded music.
- Audio timeline editing (trim, offset, fade).
- Multi-track music.
- Artist revenue sharing.
- Public asset library moderation UI.
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
feat(api): add AssetType.MUSIC and default AI-generated tracks
feat(api): add MiniMax music generation service
feat(api): add /api/v1/music endpoints
feat(web): add MusicPanel to brand-template
feat(web): add music controls to clip editor
feat(agent): select music asset per clip in Clip Agent
test(api): add music asset lifecycle tests
```

---

## 10. Need Help?

- Architecture questions: read `docs/MUSIC_ARCHITECTURE.md`.
- Frontend conventions: read `CLAUDE.md`.
- API contracts: read `docs/API.md`.
- Render contract: read `docs/VIDEO_EDITOR.md`.
- If MiniMax music API terms or endpoint details are unclear, escalate before implementing generation.
