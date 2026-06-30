# Brand-template Music Panel + Music Library Management

## Why we need this

Background music is part of the final rendered clip. The backend already supports it: `services/brand.py:music_from_template` reads the brand-template's `musicMood` and bakes a track URL into `render_spec.music`. The renderer (`packages/clip/src/Clip.tsx`) then plays that track via Remotion `<Audio>`.

The problem is that the actual music library is empty. The `data/music/` directory only contains `.gitkeep` and a `README.md`. The `/brand-template` page lets the user pick a `musicMood` from a dropdown, but they cannot:

- See which tracks are actually available.
- Preview what a track sounds like.
- Upload or delete tracks.
- View or maintain licensing sources.

So the brand-template music setting is currently blind. This task makes it usable.

## Current implementation

- **Storage**: Tracks are expected at `data/music/{mood}.mp3`.
- **Backend serving**: `GET /api/v1/music/{mood}` in `apps/api/app/routers/files.py` serves the track with Range support.
- **Resolution**: `apps/api/app/services/storage.py:resolve_music_safe` finds the file by mood stem, supporting `.mp3`, `.m4a`, `.aac`, `.ogg`, `.wav`.
- **Brand mapping**: `apps/api/app/services/brand.py:music_from_template` maps `BrandTemplate.config.musicMood` to a `ClipMusic` block.
- **Frontend selector**: `apps/web/src/routes/brand-template.tsx` has a `musicMood` Select with hardcoded options `calm`, `uplifting`, `corporate`, `none`.
- **Renderer**: `packages/clip/src/Clip.tsx` plays `spec.music.url` when enabled.

There is no API to list, upload, or delete tracks. There is no UI to preview tracks.

## What we want

Add a **Music** section inside `/brand-template`. Clicking it opens a panel that behaves like the reference screenshot: a track list with preview, selection, upload, delete, and source management.

Specifically:

- Add a `Music` row to the left-side settings list on `/brand-template`.
- Opening Music shows a panel with:
  - A list of tracks currently in `data/music/`.
  - Each track shows mood name, duration, a play/pause button, and a delete button.
  - The currently selected `musicMood` is highlighted.
  - Clicking a track sets it as the active `musicMood`.
  - Clicking play previews the track via `/api/v1/music/{mood}`.
  - An upload button to add new tracks.
  - A simple editor for `data/music/SOURCES.md`.
- Populate the library with 3 default tracks: `calm`, `corporate`, `uplifting`.
- Add a complete `data/music/SOURCES.md` with licensing info for each track.

## Code modules involved

### Backend

| File | What to do |
|:---|:---|
| `apps/api/app/routers/files.py` | Already serves `/api/v1/music/{mood}`. Keep as is. |
| `apps/api/app/routers/brand_templates.py` or a new `music.py` | Add `GET /api/v1/admin/music`, `POST /api/v1/admin/music`, `DELETE /api/v1/admin/music/{mood}`, `GET/PUT /api/v1/admin/music/sources`. |
| `apps/api/app/services/storage.py` | Reuse `resolve_music_safe`, `music_url`. May add helpers for listing music files. |
| `apps/api/app/models/schemas.py` | Add request/response schemas for track listing and upload if needed. |
| `apps/api/app/main.py` | Register the new router. |
| `data/music/` | Add 3 MP3 files and `SOURCES.md`. |

### Frontend

| File | What to do |
|:---|:---|
| `apps/web/src/routes/brand-template.tsx` | Add `Music` to the left settings list. Add the right-side panel. Wire track selection to `musicMood`. |
| `apps/web/src/lib/i18n/locales/zh.ts` / `en.ts` | Add UI copy for Music panel, upload, delete, sources. |
| `apps/web/src/components/ui/` | Reuse `Sheet`, `Dialog`, `Button`, `Table`, `Input` as needed. |

## Docs to read first

- `README.md` — project overview.
- `docs/ARCHITECTURE.md` — especially the brand-template and rendering sections.
- `docs/DECISIONS.md` ADR-019 — built-in mood music library decision.
- `docs/VIDEO_EDITOR.md` — how `render_spec.music` is used.
- `CLAUDE.md` — frontend conventions (shadcn, Tailwind, lucide icons, i18n, no `asChild`).

## Notes and precautions

- **No main flow changes**: Do not modify `services/generation.py`, `services/clip_spec.py`, or `packages/clip/src/Clip.tsx`. The existing mapping from `musicMood` to `render_spec.music` should keep working unchanged.
- **File naming**: Use `{mood}.mp3` in `data/music/`. Keep mood names lowercase and simple.
- **Licensing**: Choose tracks that do not require attribution, such as Pixabay License. Document source, author, and license in `SOURCES.md`.
- **Duration**: If reading MP3 metadata is too much work, skip duration display or estimate from file size. Do not block the rest of the task on this.
- **UI consistency**: Use shadcn/ui components. Icons only from `lucide-react`. All copy through i18n.
- **Preview playback**: Let the user preview a track before selecting it. How to implement the player is up to you; keep it simple and consistent with the rest of the UI.
- **Upload/delete**: Confirm before delete. After upload or delete, refresh the track list.
- **SOURCES.md editor**: A simple textarea is enough. Save via the backend PUT endpoint.
- **No user system**: Do not add login or permissions. This is an internal management UI inside brand-template.
- **Keep it small**: Do not add search, categories, favorites, or playlists. Only list, preview, select, upload, delete, and source editing.

## Commit message examples

```
feat: add music panel and library management to brand-template
assets: add 3 default background tracks and license sources
```
