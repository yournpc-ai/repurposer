# Built-in mood music library

Drop royalty-free / licensed background tracks here, named by **mood**:

```
data/music/
  calm.mp3
  uplifting.mp3
  corporate.mp3
```

How it wires up:

- The brand template's **music mood** (`calm` / `uplifting` / `corporate` / `none`)
  is baked into each clip's `render_spec.music` at generation time
  (`services/brand.py:music_from_template`). With **no brand template**, the clip
  falls back to the script agent's own mood suggestion, normalized to a library
  key (`services/brand.py:music_from_mood` / `normalize_mood`).
- The track URL is **extension-less** — `/api/v1/music/calm` — and the API
  resolver (`storage.py:resolve_music_safe`) serves the first `calm.<ext>` it
  finds (`.mp3/.m4a/.aac/.ogg/.wav`), with HTTP Range support
  (`routers/files.py:stream_music`).
- The renderer (`packages/clip/src/Clip.tsx`) plays it via Remotion `<Audio>`,
  looped, at the spec's `gain_db` (default −18 dB).

Until a track for a mood is present, that mood's endpoint returns 404 and the
clip simply renders with no music. **You supply the licensed audio** — nothing
is bundled (keeps the repo free of licensing constraints).
