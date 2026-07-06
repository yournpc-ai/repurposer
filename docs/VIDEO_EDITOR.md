# Portrait Video Editor — Design & Implementation Plan

> This document records the final plan for Repurposer's "portrait video output + editable" main pipeline.
> It is the conclusion of multiple rounds of technical reviews (benchmarked against OpusClip / Descript / InVideo / CapCut Web).
> See also: ADR-016 (decision record), ADR-017 (queue foundation, implemented).

## 1. Background & Category Positioning

"Portrait video output" is a **MVP must-have**, and it **must be editable** (users will inevitably want to tweak AI output).

- **Our category = OpusClip-like**: server-side AI pipeline + **thin browser editing surface** + hand off deep fine-cutting to **CapCut / Premiere**.
- **Not CapCut Web**: that is a client-side WASM engine "full-featured editor," a different category; its technical depth is overkill for us.
- **Descript is the interaction north star**: document-style editing, word↔timecode binding, non-destructive deletion — **copy these**; its multi-layer compositing / multi-track / Electron desktop engine — **do not copy**.
- **InVideo**'s conversational fine-tuning ("make the intro shorter / translate to French") as an editing auxiliary entry point, deferred. UI can use the shadcn chat component (`MessageScroller` + `Bubble` + `Marker` showing "Translating… / Cropping…", 2026-06 changelog) — do not introduce it now (no chat surface yet; introducing it now creates tech debt). Note that their registry/style needs compatibility confirmation with this project's base-ui version of shadcn.

> Core philosophy: **Be deliberately narrow in breadth — only one main pipeline, but make that line Descript-level polished.** Everything outside the line is cut honestly and handed off to downstream tools.

## 2. "Lighter & Weaker" Boundaries (What We Do / What We Don't)

| Tier | Scope | Decision |
|:---|:---|:---|
| **L1** | Text assets + subtitle correction + template graphics (quote cards) | Mostly built |
| **L2** (main body of this doc) | Basic portrait video output: segment trimming + burned-in subtitles + brand styling + music + intro/outro → MP4 + SRT; transcript-style editing + single-track trim | **Implemented** |
| **L3** | Multi-track / layer compositing / transition effects / B-roll library / auto face-tracking reframe / desktop offline / client-side engine | **Never; hand off to CapCut** |

**Polished means**: (1) preview = output pixel parity; (2) multilingual subtitles are accurate and one-click editable; (3) one-click yields a publishable clip (editing is optional, not required); (4) deleting a sentence = trimming the video, undoable; (5) restrained, unified UI + honesty (clearly say "export to CapCut for fine-tuning" where we can't deliver).

## 3. Core Decision: Lock the Contract, Treat Renderer as a Replaceable Black Box

**The one locked architectural decision = a declarative `clip-spec(JSON)` as the sole contract.** The renderer behind it is a replaceable implementation.

```
clip-spec(JSON)  ← permanent contract (renderer-agnostic, only describes "what it is", no React/Remotion concepts)
     │
     ├──► Preview: Remotion <Player> renders in real time in the browser (editor canvas)
     └──► Output: Remotion render service (headless Chrome + internal FFmpeg) → MP4 + SRT
```

- **First renderer = Remotion** (server-side, headless Chrome + FFmpeg): parity (preview = output) is structurally natural; media dirty work (audio-video sync / decode / seek / fonts) is mature; `<Player>` doubles as preview; fits our React stack.
- **Treat it as a black box**: `spec in → MP4+SRT out`. Python queue triggers it via HTTP/CLI, with a clean boundary and no entanglement with the Python backend.
- **Low regret**: because the spec is a stable contract, if **cost / scale** becomes an issue in the future, we can swap to **hand-rolled FFmpeg** (see §9) or **client-side WebCodecs**, with the spec unchanged and no major surgery.
- **Why not hand-roll from the start**: we are doing "video processing," FFmpeg is indeed the right tool, but hand-rolling means we must guarantee parity ourselves (two different rendering engines will drift) + navigate a long list of media edge cases. For a small team, Remotion buys all of this in one go, in exchange for a faster, polished MVP. The cost is a Node render service + license (4+ people $25/seat or $0.01/render).
- **Why not CapCut Web / client-side engine**: editing needs top out at "trim + subtitles + styling," which does not reach multi-track NLE territory; building a proprietary WASM engine is paying years of engineering for a non-existent need.

## 4. Contract Layer: clip-spec Data Structure

**Principle**: renderer-agnostic; only describes "what it is"; styles limited to **a set of presets (expressible by both CSS and libass)** to preserve low-cost future migration to hand-rolled FFmpeg.

```jsonc
{
  // kind="video": real person on camera, url is the video; kind="stills": image audio slideshow,
  // url is the optional audio track (empty string if no recording), image_urls are background images (0→solid color / 1→full screen / N→evenly split hard-cut slideshow)
  "source": { "asset_id": "uuid", "kind": "video", "url": "/api/v1/files/...mp4", "image_urls": [], "fps": 30, "duration": 120.5 },
  "aspect": "9:16",                         // 9:16 | 1:1
  "segments": [                              // retained interval list; deleting a sentence = mark a segment as hidden (non-destructive)
    { "start": 12.4, "end": 31.0, "hidden": false }
  ],
  "crop": { "x": 0.5, "y": 0.5, "scale": 1.0 }, // normalized center + scale; implemented with transform, not object-position
  "caption_track": [                         // from ASR word-level timestamps; user can edit text
    { "start": 12.4, "end": 12.9, "text": "So", "lang": "en" }
  ],
  "caption_style_preset": "clean-bottom",   // preset enum, not free-form styling
  "caption_position": { "x": 0.5, "y": 0.84 }, // normalized center point (drag to position); null → default bottom
  "title": { "text": "The hook", "enabled": true, "size": 56, "position": { "x": 0.5, "y": 0.12 } },
  "music": { "track_id": "calm", "url": "/api/v1/music/calm", "enabled": true, "gain_db": -18 },
  "dub": { "url": "/api/v1/outputs/.../dub_fr.mp3", "enabled": false, "gain_db": 0 }, // voice-clone dubbing; when enabled, original audio is muted
  // brand block is baked by the API from the selected BrandTemplate (brand_template_id, defaults to latest) at generation time; renderer does not read DB
  "brand": {
    "logo_url": "https://example.com/logo.png",
    "cta": "Read the full talk →",
    "cta_position": { "x": 0.5, "y": 0.92 },  // normalized center point (drag to position)
    "caption_color": "#22c55e",
    "caption_size": 56,
    "caption_font": "lilita",                 // lilita | inter | playfair | source-serif
    "intro_text": "From the keynote",
    "outro_text": "Follow for more insights",
    "fill_mode": "fill"                       // fill (cover) | fit (contain)
  },
  "brand_ref": "brand_template_uuid",       // provenance: which brand template
  "target_language": "en"
}
```

- **Non-destructive** (copied from Descript): deleting a sentence = mark that `segment` as `hidden`, do not actually delete; recoverable.
- `caption_track` drives both **burned-in subtitles** and direct **SRT** export (the handoff artifact for downstream CapCut fine-tuning).
- Styles go through `caption_style_preset` enum (e.g. `clean-bottom` / `karaoke-highlight`), **no free-form layout** — this is the prerequisite for "what you see is what you get" and future libass swapability.
- **Brand enters rendering**: the `brand` block is baked into the spec by the API parsing `BrandTemplate` at **generation time**; the render service / preview only reads the spec, not the DB, guaranteeing parity and keeping the renderer a black box.
- **Music enters rendering**: `music.url` points to the built-in mood music library (`/api/v1/music/<mood>`) or any absolute URL; `<Audio>` loops and mixes, gain controlled by `gain_db`.
- **Intro/outro**: when `brand.intro_text` / `brand.outro_text` are present, a 2-second title card is inserted before and after the main video timeline; the video body `<Sequence>` shifts backward, and subtitle remapping auto-aligns.
- **Two source kinds (output is not limited to real-person recordings)**: `source.kind="video"` uses `<OffthreadVideo>` (current state); `source.kind="stills"` is an **image audio slideshow** — `image_urls` serve as the background visual (1 image = full screen / N images = evenly split hard-cut slideshow / 0 images = solid color fallback), `url` is the optional audio track. When audio is present, reuse ASR word-level `caption_track`; when no audio, it becomes a fixed-duration slideshow (each image `SECS_PER_IMAGE` seconds). Background visual source priority: **slideshow PDF page renders (`Asset.slide_pages`) first** + uploaded photos after; source selection priority VIDEO→AUDIO→SLIDES/IMAGE. **Deliberately not doing** transitions / Ken-Burns / multi-sentence animated text tracks / B-roll (staying at L2, see ADR-020).
- **Text drag positioning**: `caption_position` / `title.position` / `brand.cta_position` are normalized center points `{x,y}∈[0,1]` (= libass `\pos`, portable), null → renderer default. `title.size` is the composite pixel font size. The brand page overlays a transparent layer on the preview for dragging these three text overlays (safe-zone + clamp). **Only move; no scaling / keyframe animation.**
- **Voice-clone dubbing (dub)**: `POST /clips/{id}/dub` uses the speaker's voice (VOICE_SAMPLE / AUDIO / VIDEO track extraction) via MiniMax voice_clone + T2A to dub the (translated) subtitles into the target language, baked into the `dub` track; when rendering, if `dub.enabled`, **mute original audio** and play the dub instead (overlay, no lip-sync, see ADR-021 and memory).
- **Image visual understanding**: IMAGE assets are processed by M3 multimodal (`services/vision.py:describe_image`) to extract key information into `Asset.extracted_text`, feeding into the analyzer's materials like any other asset.
- **Intent channel**: homepage prompt = `GenerateRequest.instruction`, folded into `GenerationContext` and passed to the Content Director and every derivative agent, used to shape the content plan, select clips, determine hook/title, and bias output focus.
- **Multiple brand templates**: CRUD + default seed on startup; at generation time, `brand_template_id` is selected (defaults to latest). `aspect` (9:16/1:1) and the three position points are also baked into the spec from the template.
- **Speaker = user profile** (ADR-021): persona (style) + voiceprint (voice sample / clone voice_id) attached to the profile; dub prefers the profile's voiceprint, clone once and reuse. Theme/intent for this project belongs to the Project.

## 5. Hard Prerequisites (Upgraded from Optional P1 to Hard Blockers)

Without these two, the editor cannot be built:

| Prerequisite | Choice | Why it is a hard blocker |
|:---|:---|:---|
| **Streamable / seekable video URL** | **Local file system + FastAPI Range (206) streaming endpoint is sufficient**. Object storage (MinIO/S3 EU) is a **scale / multi-instance** concern, deferred to P1/production per ADR-011, **not an MVP prerequisite** | Trimming / preview requires the browser to **play + seek** the source video |
| **Multilingual ASR (word-level timestamps)** | Self-hosted WhisperX / faster-whisper (EU/GDPR, not cloud API) | Foundation for real-time subtitle overlay + subtitle editing (= Descript "forced alignment" equivalent) |

Standard MP4/H.264 uploads are **directly playable in the browser** (via the local Range endpoint), no transcoding needed. Proxy transcoding (H.264/AAC) is only needed when the upload is a **non-browser-playable format** (.mov/.mkv/strange codec) — this step is **deferrable**, not an MVP prerequisite. Note: **Remotion rendering bundles its own ffmpeg, faster-whisper uses PyAV (wheel bundles ffmpeg)**, neither requires system ffmpeg; system ffmpeg is only potentially needed for the proxy transcoding step.

**Cloud migration hook (reserve now)**: keep `storage.py` as the sole storage boundary (ADR-011 already abstracted a layer), with discipline:
- Video URLs (`Clip.video_url` / source video) are always **indirect addressing** — frontend / Remotion receives "a playable URL" resolved by the storage layer, **never hardcoded local paths**.
- Currently this URL points to the **local Range endpoint**; when migrating to object storage in the future, the storage layer returns **MinIO/S3 presigned URLs** (also support Range), and `clip-spec`, frontend, Remotion components, and worker **all remain unchanged**.
- Range / read logic is encapsulated behind the storage layer; migration = only swap `storage.py` implementation + config, zero changes for callers.

## 6. Render Layer

```
┌────────────┐   spec(JSON)   ┌──────────────────────┐
│ Python      │ ──HTTP/CLI──► │ Remotion render service (Node)│
│ worker(queue)│               │ headless Chrome frame rendering + │
│ implemented │ ◄──MP4+SRT──── │ internal FFmpeg encoding       │
└────────────┘                └──────────────────────┘
```

- Remotion component `<Clip>` consumes `clip-spec` as `inputProps`; **the same component** is used for `<Player>` (preview) and the render service (output).
- Node render service is started with **pnpm** (per ADR-001, each uses its own package manager), self-hosted in EU.
- Trigger: the existing Postgres queue (see ADR-017) adds a "render" claim source (`Clip.render_status`), worker calls the render service.
- Copy Remotion's FFmpeg encoding parameters (codec/bitrate/pixfmt) as-is; this part is pure FFmpeg anyway.

**Project structure (ADR-018)**: the `<Clip>` component must be shared between the web `<Player>` (preview) and the render `renderMedia` (output) — this is the root of parity, so it is extracted into a shared package:

```
apps/render/        Remotion render service (@remotion/bundler + renderer + express) → POST /render: spec→MP4+SRT
packages/clip/      shared <Clip> component + clip-spec TS types (mirror Pydantic)
apps/web/           editor uses @repurposer/clip <Clip> inside <Player>
pnpm-workspace.yaml web/render/clip workspace; api uses uv independently, not in the workspace
```

Source video URL: the render service's `spec.source.url` must be an **absolute URL** (worker absolutizes the storage seam's relative URL before calling). The render service writes MP4/SRT to the shared `data/outputs`, served by the API via the Range endpoint.

## 7. Editor Interaction (Thin Editing Surface, Not a Multi-Track NLE)

Single-screen layout (reference OpusClip/Descript, but only the main trunk):

```
┌────────────────────────┬───────────────────────────┐
│   9:16 preview (<Player>) │  Transcript (editable) ⟵ editing focus │
│  real-time subtitles + draggable crop box │  click word to edit (fix ASR/translation errors)   │
│      ▶                  │  select sentence to delete = mark paragraph as hidden (recoverable)│
│                        │  Tab: Subtitles|Composition|Brand|Music    │
├────────────────────────┴───────────────────────────┤
│ ▭▭ single-track strip  [⟸trim  trim⟹]  ●scene marker ▭▭▭▭▭▭ │ ⟵ only trim/scrub/jump
└──────────────────────────────────────────────────────┘
                                         [ Export MP4+SRT ]
```

- **Editing focus is on the transcript panel** (delete sentence / edit word / change language), the single-track strip only does trim/scrub.
- Change language: switch `caption_track` `lang` (triggers re-translation).
- Default output is publishable; editing is optional.

## 8. Data Model Extensions

`Clip` table additions (via Alembic migration, reusing the existing queue):

| Field | Type | Purpose |
|:---|:---|:---|
| `render_spec` | JSON | clip-spec contract |
| `render_status` | Enum(pending/rendering/completed/failed) | render task status (worker claim source) |
| `render_error` | Text nullable | failure reason |
| `video_url` | String (existing) | output MP4 |
| `srt_url` | String nullable | exported subtitles |

**In the same migration, clean up dead columns from the old ADR-008 image-slideshow model** (verified never written/read in practice): `Asset.keyframes`, `Clip.subtitles` (subtitles now carried by `render_spec.caption_track`). `Asset.slide_pages` is now active: SLIDES uploads are rendered page-by-page by PyMuPDF into images and stored, fed into stills `image_urls` (see ADR-020).

**Model coordination**: the `Clip` table stores the render contract in `render_spec` and the analyzer's creative output directly on `Clip` fields (`hook`, `title_options`, `music_mood`, `duration`, `source_segment`). The old ADR-008 shot-script model (`time_range`/`visual`/`mood`) has been removed; `render_spec` is the single source of truth for the renderer.

## 9. Future Replaceable Paths (spec unchanged)

| Trigger | Swap to | Cost |
|:---|:---|:---|
| Remotion cost / scale issues | **Hand-rolled Python+FFmpeg+libass**: clip-spec→FFmpeg filtergraph in one pass; subtitles use `.ass`, preview side uses **libass.wasm (JavascriptSubtitlesOctopus)** to render the same .ass → both sides share libass to guarantee parity | Render logic written by us; .ass animation has a ceiling (we won't hit it) |
| Want "video never leaves browser" + cost reduction | **Client-side `@remotion/web-renderer` (WebCodecs)**: our compositing falls within its CSS subset (see restriction list), a realistically viable switch | alpha stage; limited GDPR benefit (ASR still server-side); may still need server-side proxy |

> GDPR main line is still **server-side full stack + EU region deployment**; client-side rendering is only a cost-reduction alternative, not the GDPR answer.

## 10. Phase Breakdown

```
0. Queue foundation (built: Postgres as queue + worker + Asset state machine)  ✅
1. Range streaming endpoint (local files, playable/seekable) + source video proxy transcoding (format normalization)
   — Range is built; proxy transcoding deferred (only needed for non-browser-playable formats)
2. Multilingual ASR (word-level timestamps) → wired into worker's asset processor  ✅
3. clip-spec contract + table migration + Remotion component + Node render service + queue trigger → ✅
   Brand (logo/CTA/color/font size/font/fill/intro/outro) and music baked into clip-spec  ✅
4. Editor UI: <Player> preview + transcript editing (delete sentence = trim segment / non-destructive) + single-track trim + styling/title/music + subtitle language switch  ✅
```

## 12. Current Implementation Notes

- The backend generates `carousel` and `blog` derivative types alongside clips, LinkedIn posts, quote cards, and summaries. As of the current build, the project results page (`/projects/$id`) only renders tabs for **clips, LinkedIn, quote cards, and summaries**; carousel and blog outputs exist in the API but are not yet surfaced in the UI or the library endpoint.
- The clip editor route (`/projects/$id/clips/$clipId`) uses the shared `@repurposer/clip` component inside a Remotion `<Player>` and supports caption editing, language switching, render triggering, and export. The full Descript-style single-track trim strip described in §7 is partially wired through `trimBounds`/`removeRange` helpers but not yet fully exposed in the UI.

## 11. Validation

- End-to-end validation: upload a talk video → ASR produces word-level subtitles → editor edits a word / deletes a sentence / switches language → preview reflects in real time → export → **output pixel-identical to preview** + SRT importable by CapCut.
- Parity regression: randomly sample specs, compare `<Player>` frame capture with render service output first frame.
