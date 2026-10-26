# Portrait Video Editor — Design & Implementation Plan

> Status: Implemented（L2 主流程已落地；undo 可用 = operations 端点 + chat 撤销，editor 内按钮/历史面板后置，见 ADR-032）
> 编辑面分层（ADR-033）：本文的"编辑形式"= **editor 适配器**的形态，不是产品编辑面的全部——执行能力层由 `OP_REGISTRY ∪ TOOL_REGISTRY` 组成，`SKILL_REGISTRY` 只提供装配期指令包；editor / chat /（预留）mcp 是并存的薄适配器（chat 是正式编辑面）。
> This document records the design plan for Repurposer's "portrait video output + editable" main pipeline (benchmarked against OpusClip / Descript / InVideo / CapCut Web).
> See also: ADR-016 (decision record), ADR-017 (queue foundation, implemented).
> **clip-spec 字段级契约、渲染链架构（烘焙缝 / 渲染服务 / 共享包 / 函数地图）、渲染器替换路径 → `RENDERING.md`；本文只载编辑器交互形态与范围纪律。**
> Last updated: 2026-08-18.

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
| **L3** | Free multi-track timeline / freeform layer compositing / transition gallery or freeform transition editor / stock B-roll library / generic face or object tracking / desktop offline / client-side engine | **Never; hand off to CapCut**. ADR-044's registered anchors/layers and entry-edge transition enum are not a free NLE |

**Polished means**: (1) preview = output pixel parity; (2) multilingual subtitles are accurate and one-click editable; (3) one-click yields a publishable clip (editing is optional, not required); (4) deleting a sentence = trimming the video, undoable (undo 可用 = operations 端点 + chat 撤销按钮；editor 内 undo 按钮后置——见 ADR-032); (5) restrained, unified UI + honesty (clearly say "export to CapCut for fine-tuning" where we can't deliver).

## 3. Core Decision: Lock the Contract, Treat Renderer as a Replaceable Black Box

**唯一锁定的架构决策 = 声明式 `clip-spec(JSON)` 作为唯一契约；渲染器是其后可替换的黑盒实现。**（决策与选型理由 → ADR-016；字段级契约 / 烘焙缝 / 渲染服务 / 函数地图 → `RENDERING.md`；替换路径 → `RENDERING.md` §7。）

## 4. Contract Layer: clip-spec Data Structure

**字段级契约 → `RENDERING.md` §3**；字段的时间轴归属（源 vs 输出）与隐式轨道解剖 → `RENDERING.md` §4；契约演进方向（轨道模型）→ `RENDERING.md` §8。本文不复述。

## 5. Hard Prerequisites (Upgraded from Optional P1 to Hard Blockers)

Without these two, the editor cannot be built:

| Prerequisite | Choice | Why it is a hard blocker |
|:---|:---|:---|
| **Streamable / seekable video URL** | 对象存储（Volcengine TOS）+ API 307 重定向 / `?proxy=1` 流式（ADR-024），Range 完全由对象存储承担（API 不做 Range；`?proxy=1` 分支整文件落临时盘后 FileResponse） | Trimming / preview requires the browser to **play + seek** the source video |
| **Multilingual ASR (word-level timestamps)** | Self-hosted WhisperX / faster-whisper (EU/GDPR, not cloud API) | Foundation for real-time subtitle overlay + subtitle editing (= Descript "forced alignment" equivalent) |

Standard MP4/H.264 uploads are **directly playable in the browser** (via the storage-served URL), no transcoding needed. Proxy transcoding (H.264/AAC) is only needed when the upload is a **non-browser-playable format** (.mov/.mkv/strange codec) — this step is **deferrable**, not an MVP prerequisite. Note: **Remotion rendering bundles its own ffmpeg, faster-whisper uses PyAV (wheel bundles ffmpeg)**, neither requires system ffmpeg; system ffmpeg is only potentially needed for the proxy transcoding step.

**存储边界**：`app/providers/storage.py` 是唯一存储缝（ADR-024）——视频 URL 永远间接寻址、clip-spec/前端/渲染器/worker 均存储无关；渲染侧读写路径与烘焙缝 → `RENDERING.md` §1。

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

## 10. Current Implementation Notes

- Public output types are `clip`, `film`, `post`, `quotes`, `quote_frame`, `carousel`, and `article`. The project workspace presents outputs through the current canvas + ChatDock contracts, not a retired per-type results-tab layout. Render accepts `clip` and `film`; other output actions remain action-specific.
- The clip editor route (`/projects/$id/clips/$clipId`) uses the shared `@repurposer/clip` component inside a Remotion `<Player>` and supports caption editing, language switching, render triggering, and export. The full Descript-style single-track trim strip described in §7 is partially wired through `trimBounds`/`removeRange` helpers but not yet fully exposed in the UI.
- **Clip card rendering state**: on the project results page, a clip with `render_status` of `pending` or `rendering` shows a spinner overlay, hides the action bar, and disables hover playback / detail open until rendering completes or fails.
- **Clip download**: the frontend downloads via `downloadFile` — fetch the URL → blob → `<a download>` on a same-origin object URL (honored cross-origin; API-relative URLs carry the bearer token via apiFetch). The API also has `/outputs/?download=true` (307 to a presigned GET with `Content-Disposition: attachment`), but the frontend does not use it.
- **Project thumbnails**: project-list cards display the earliest rendered clip as a video thumbnail with a duration / aspect badge; the API left-joins the first rendered clip per project in `GET /api/v1/projects`.
- **Image visual understanding**: IMAGE assets are consumed directly by the generation agents as raw media — M3 multimodal reads the original image (`pipeline/asset_processing.py` registers a no-op processor for IMAGE).

## 11. Validation

### 11.1 渲染与编辑器主链

- End-to-end：上传真实发言视频 → ASR 词级字幕 → 修改文字/删句/切语言 → preview 同步 → export；导出与 preview 像素一致，SRT 可导入 CapCut。
- Parity：抽样 spec 对比 `<Player>` 帧与 render service 输出；preview/render 必须共享 `packages/clip`，不能用截图相似代替契约一致。
- 当前 editor UI 未暴露的 trim 能力必须按 §10 的实际边界验收，不能把 helper 存在写成界面已完成。

### 11.2 精确编辑四族与指认

用至少两条已交付 clip 的真实项目执行，目标通过 `@output` 或 `plan_ref` 明确指认：

1. `remove_range`：引用原句删除，回声区间来自落账 op；另验跨 cue、CJK/标点/大小写归一化、未命中与多义。后两者必须域拒绝并给出可答问题，不猜时间、不静默重生成。
2. `set_trim`：如“这条再短 3 秒”，核对 pin = target、实际时长差与事实回声。
3. `set_caption_style`：合法 preset 生效；Comic Sans/自由颜色等表外请求返回可用枚举，不伪报成功。
4. `set_title`：标题更新并重渲染，产物和 journal 一致。
5. **pin/model 自然分歧**：构造模型自选目标与用户唯一 `@output` 不同的真实回合，服务端 `pinned_output_id` 必须强制钉 id。当前只有纯件覆盖强制分支，尚需自然分歧 live 证据或明确裁决只接受纯件层级；普通“pin 恰好命中”不能代替本项。

### 11.3 journal / undo / rerun / archive / restore

- `GET /outputs/{id}/operations` 可读 baseline、各 op 与 `undone_at`；`POST /outputs/{id}/operations/undo` 只在同一 Version 内回滚，不创建新 Version。
- rerun/regeneration 产生新 outputs Version 并按位继承 `work_id`；旧 Version 只归档不物理销毁，按 id 仍可读，journal 与 publication 的版本锚保持有效，默认 results 只展示 active。
- 对 archived Version 的 operations、undo、PUT、regenerate 等写门都必须 409。`POST /outputs/{id}/restore` 在同 Work 内切换 active 指针：被恢复行可编辑，原 active 自动归档，至多一 active。
- 精确编辑是版本内 operation，**“edit → V2”永禁**；Restore 才是跨 Version 换态。按当前定价 edit→render 为 $0，不能拿已退役的 `confirm_strategy` 或 composer 控件验收当前授权设置。

自动覆盖归 `VERIFICATION.md` 的精确编辑合同与当前注册的纯测试/旅程矩阵；不恢复退役剧本名或旧探针计数。既有 live 证据与剩余人工拍位见 `../scratch/precise-edit-walkthrough.md`，其旧结果不能替代当前 HEAD 复验。
