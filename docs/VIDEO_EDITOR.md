# Portrait Video Editor — Design & Implementation Plan

> Status: Implemented（L2 主流程已落地；undo 已随 Operation Model 落地——端点 + chat 撤销，editor 内按钮/历史面板后置，见 ADR-032 与 `docs/tasks/done/operation-model.md`）
> 编辑面分层（2026-08-02，ADR-033）：本文的"编辑形式"= **editor 适配器**的形态，不是产品编辑面的全部——能力层（OP_REGISTRY ∪ SKILL_REGISTRY）唯一，editor / chat /（预留）mcp 是并存的薄适配器；chat 已是正式编辑面，不再是"辅助入口"。
> This document records the final plan for Repurposer's "portrait video output + editable" main pipeline.
> It is the conclusion of multiple rounds of technical reviews (benchmarked against OpusClip / Descript / InVideo / CapCut Web).
> See also: ADR-016 (decision record), ADR-017 (queue foundation, implemented).
> **clip-spec 字段级契约、渲染链架构（烘焙缝 / 渲染服务 / 共享包 / 函数地图）、渲染器替换路径 → `RENDERING.md`（本文原 §4/§6/§9 已迁入，本文只留编辑器交互形态与范围纪律）。**
> Last updated: 2026-07-20.

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

**Polished means**: (1) preview = output pixel parity; (2) multilingual subtitles are accurate and one-click editable; (3) one-click yields a publishable clip (editing is optional, not required); (4) deleting a sentence = trimming the video, undoable (undo 已落地：operations 端点 + chat 撤销按钮；editor 内 undo 按钮后置——见 ADR-032 与 `docs/tasks/done/operation-model.md`); (5) restrained, unified UI + honesty (clearly say "export to CapCut for fine-tuning" where we can't deliver).

## 3. Core Decision: Lock the Contract, Treat Renderer as a Replaceable Black Box

**唯一锁定的架构决策 = 声明式 `clip-spec(JSON)` 作为唯一契约；渲染器是其后可替换的黑盒实现。**（决策与选型理由 → ADR-016；字段级契约 / 烘焙缝 / 渲染服务 / 函数地图 → `RENDERING.md`；替换路径 → `RENDERING.md` §7。）

## 4. Contract Layer: clip-spec Data Structure

**字段级契约 → `RENDERING.md` §3**；字段的时间轴归属（源 vs 输出）与隐式轨道解剖 → `RENDERING.md` §4；契约演进方向（轨道模型）→ `RENDERING.md` §8。本文不复述。

## 5. Hard Prerequisites (Upgraded from Optional P1 to Hard Blockers)

Without these two, the editor cannot be built:

| Prerequisite | Choice | Why it is a hard blocker |
|:---|:---|:---|
| **Streamable / seekable video URL** | 对象存储（Volcengine TOS）+ API 307 重定向 / `?proxy=1` 流式（ADR-024），Range 由对象存储与 API 双侧支撑 | Trimming / preview requires the browser to **play + seek** the source video |
| **Multilingual ASR (word-level timestamps)** | Self-hosted WhisperX / faster-whisper (EU/GDPR, not cloud API) | Foundation for real-time subtitle overlay + subtitle editing (= Descript "forced alignment" equivalent) |

Standard MP4/H.264 uploads are **directly playable in the browser** (via the storage-served URL), no transcoding needed. Proxy transcoding (H.264/AAC) is only needed when the upload is a **non-browser-playable format** (.mov/.mkv/strange codec) — this step is **deferrable**, not an MVP prerequisite. Note: **Remotion rendering bundles its own ffmpeg, faster-whisper uses PyAV (wheel bundles ffmpeg)**, neither requires system ffmpeg; system ffmpeg is only potentially needed for the proxy transcoding step.

**存储边界**：`storage.py` 是唯一存储缝（ADR-024）——视频 URL 永远间接寻址、clip-spec/前端/渲染器/worker 均存储无关；渲染侧读写路径与烘焙缝 → `RENDERING.md` §1。

## 6. Render Layer

渲染服务结构、共享包拆分（`apps/render` + `packages/clip`）、烘焙缝与驱动函数地图 → `RENDERING.md`（§1/§2/§5）。

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

## 8. Data Model

产物统一为 `outputs` 表（ADR-030），clip = `type='clip'` 的那一类。渲染相关列：

| Field | Type | Purpose |
|:---|:---|:---|
| `render_spec` | JSONB | clip-spec contract |
| `render_status` | String nullable | render task status（worker 认领谓词；NULL = 未请求渲染） |
| `files` | JSONB | 产物文件键（MP4 / SRT / 图片），对象存储 key |
| `source_ref` | JSONB nullable | 时间轴语义（选段 / trim / hidden）——clip 类型的血统 |

**Model coordination**: `render_spec` is the single source of truth for the renderer; the director's creative output lives in `payload`（payload schema 注册表守门，ADR-030 规则 1）。字幕由 `render_spec.caption_track` 承载；SLIDES 上传经 PyMuPDF 逐页渲成图片存 `Asset.slide_pages`，喂给 stills `image_urls`（see ADR-020）。

## 9. Future Replaceable Paths (spec unchanged)

渲染器替换路径（手写 FFmpeg+libass / 客户端 WebCodecs 的触发条件与成本）→ `RENDERING.md` §7。

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

- The backend generates `carousel` and `blog` output types alongside clips, LinkedIn posts, quote cards, and summaries. As of the current build, the project results page (`/projects/$id`) only renders tabs for **clips, LinkedIn, quote cards, and summaries**; carousel and blog outputs exist in the API but are not yet surfaced in the UI or the library endpoint.
- The clip editor route (`/projects/$id/clips/$clipId`) uses the shared `@repurposer/clip` component inside a Remotion `<Player>` and supports caption editing, language switching, render triggering, and export. The full Descript-style single-track trim strip described in §7 is partially wired through `trimBounds`/`removeRange` helpers but not yet fully exposed in the UI.
- **Clip card rendering state**: on the project results page, a clip with `render_status` of `pending` or `rendering` shows a spinner overlay, hides the action bar, and disables hover playback / detail open until rendering completes or fails.
- **Clip download**: the frontend requests rendered outputs with `?download=1` so the API returns `Content-Disposition: attachment`, prompting the browser to save the MP4/SRT instead of playing it inline.
- **Project thumbnails**: the home page project cards display the earliest rendered clip as a video thumbnail with a duration / aspect badge; the API left-joins the first rendered clip per project in `GET /api/v1/projects`.
- **Image visual understanding**: IMAGE assets are consumed directly by the generation agents as raw media — M3 multimodal reads the original image (`pipeline/asset_processing.py` registers a no-op processor for IMAGE).

## 11. Validation

- End-to-end validation: upload a talk video → ASR produces word-level subtitles → editor edits a word / deletes a sentence / switches language → preview reflects in real time → export → **output pixel-identical to preview** + SRT importable by CapCut.
- Parity regression: randomly sample specs, compare `<Player>` frame capture with render service output first frame.
