# Repurposer Music Architecture

> Status: Implemented（2026-07 落地：`Music` 表、MiniMax music-2.6 生成、管线集成；音乐质检归 verify 节点 Phase 3，未实现）
> Last updated: 2026-07-31（瘦身：提案时代章节压缩，ContentPlan / services 时代引用修正）
> Related: ADR-019 / ADR-022（被本文取代）、ADR-023（AI 生成音乐库决策）、实施简报 `docs/tasks/done/music-asset-library.md`

---

## 1. Background

早期音乐是 Brand 模板里的静态 mood 枚举（`musicMood: "calm"` → 磁盘文件），问题：版权采集脆弱、选择静态、生成/精修两侧都无智能。本架构将其替换为 **AI 生成音乐库 + 专用 `Music` 表**。

> **命名**：`Music` 是音乐库条目的内部表/实体名；用户侧文案与 API 路径用 "music"（`/api/v1/music`）。一条 Music 是库里的**一首背景乐**，不是视频时间线意义上的音轨。

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
2. **No manual audio timeline editing in MVP.** Trim/offset/fade are Phase 4+ features.
3. **No real-time music generation during clip generation.** Music is selected from pre-generated assets; generation only happens on explicit user request via chat/editor.

---

## 4. High-Level Architecture

```
Music Library（Music 表 + 对象存储 music/ 前缀，预生成 + 用户触发生成）
        │
        ▼
Brand Template（musicEnabled / musicId / musicGainDb = 品牌默认曲）
        │
        ▼
Clip Agent 生成时选曲（看到库清单 + 品牌默认，输出 music_id / enabled / gain_db）
        │
        ▼
烘焙进 outputs[type=clip].render_spec.music（渲染器唯一契约，不读 DB）
        │
        ▼
Remotion <Audio url>（loop + gain_db 混音）
        │
        ▼
精修（chat / editor）：set_music 换曲/开关/增益 → 重渲染；
                      自定义新曲 → MiniMax 生成入库 → set_music 应用
```

---

## 5. Source of Truth

| Data | Source of Truth | Rationale |
|---|---|---|
| **Audio bytes** | Object storage (`music/{music_id}.{ext}`) | 与 uploads/outputs 同约定（ADR-024） |
| **Music metadata** | `music` table | 结构化元数据（mood/prompt/license/duration/attribution/is_public）值得类型化列；全局共享资源不进 Asset（Asset 必须属 project 或 speaker） |
| **Brand default music** | `BrandTemplate.config.musicId` | 用户侧 = "default music" |
| **Per-clip music choice** | `outputs[type=clip].render_spec.music` | 渲染契约是运行时事实源 |

---

## 6. Data Model

字段级事实源 = 代码（`app/models/tables.py` + `migrations/`），此处只记归属与绑定模型。

**`music` 表归属 Pipeline**（渲染资产库，MODULE_ARCH §4 已登记）。三种行：

- **Platform/default pieces**: `generated_by_user_id = NULL`, `is_public = TRUE`。平台所有，全员可用。
- **User-generated pieces (MiniMax)**: `generated_by_user_id = <user_id>`, `is_public = TRUE` 默认。用户触发生成，但进入共享库。
- **Future user uploads**: `generated_by_user_id = <user_id>`, `is_public = FALSE` 默认。私有，显式分享 + 审核后才公开。

**Brand Template config**：`musicEnabled: bool`、`musicId: str | null`（替代旧 `musicMood`）、`musicGainDb: float = -18.0`。

**Render spec contract（不变）**：

```typescript
interface ClipMusic {
  music_id: string | null;
  url: string | null;   // 音乐文件的公开对象 URL（生成时从 Music.file_path 烘焙）
  enabled: boolean;
  gain_db: number;
  // Future (not implemented): start/end trim fields
}
```

渲染器不知道音乐库、mood、Music 行的存在——`enabled` 为真时播 `url`，仅此而已。

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

Default music pieces are created at application startup if they do not exist（按 `mood` 唯一键查重，`scripts/seed_default_music.py`；reset_db 会清空包括平台音乐，需重新 seed，花费 MiniMax 配额）。Audio files live at `music/{music_id}.{ext}` in object storage.

### 7.4 Artist-Generated Music Pieces (Future)

When the platform has artists or power users, their generated music pieces can also be seeded into the library:

- `kind` is implied by the `prompt` / `model` fields being present.
- `generated_by_user_id: <user_id>`
- `is_public: true` (after review) or `false` (private)
- Artists may receive attribution or revenue share (business decision TBD).

---

## 8. Generation Flow

1. **Brand default**：`BrandTemplate.config.musicId` → `GenerationContext.brand_music_id`。
2. **Clip Agent 选曲**：prompt 收到库清单（mood + 一句话描述）与品牌默认曲，为每条 clip 输出 `music_id` / `music_enabled` / `music_gain_db`。选择逻辑：① 品牌默认契合即用；② 按 clip 内容调性推断。
   - 注：曾有"导演 mood hint 经 DerivativePlan 传递"的设计，已随 DerivativePlan 退役（N-17）不再存在；选曲判断全在 clip agent。
3. **烘焙**：`build_clip_spec` 解析 `Music` 行 → `render_spec.music`（`url` = 公开对象 URL）。**生成时零 MiniMax 调用**。

---

## 9. Refinement: Edit Ops + Custom Generation

- **换曲 / 开关 / 调增益** = `set_music` edit op（CHAT_ARCH §9，operations 表，editor 与 chat 两前端共用）→ `outputs.render_status=PENDING` → worker 重渲染。
- **自定义新曲** = `POST /api/v1/music` 触发 MiniMax 生成（重活走 worker，ADR-017）→ 新 `Music` 行入库（默认 `is_public=True`，进共享库）→ `set_music` 应用到 clip → 重渲染。
- **chat 词汇**：`add_music` skill（registry 已登记，配乐殿后的 `after` 约束）。

### 9.1 Cost Control

Music generation is more expensive than selection. To avoid runaway costs:
- Each project has a budget or generation quota (future，归计费线 PROGRESS 第 8–9 周).
- Free tier defaults to the 3 pre-generated music pieces; custom generation is a paid/limited feature.
- Generated music pieces are cached as assets so the same prompt does not re-generate.

---

## 10. Music Library UI

- **In Brand Template** (`/brand-template`)：Music 区——曲目列表（title / mood tag / duration / 试听 / 单选）+ "Generate new"（prompt 输入）+ `musicEnabled` 开关。
- **In Result Editor**：clip 编辑器可换曲、开关、增益滑杆、"Generate new"。
- **Future: Standalone Music Library** (`/library/music`)：浏览/搜索/管理全库，Phase 2+ 后置。

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

## 13. Integration

- **Agent 编排**：`GenerationContext.brand_music_id`（Layer 1）；clip agent 选曲（Layer 3）；音乐质检归 verify 节点（Phase 3，未实现——AGENT_ARCH §12）。
- **队列**：自定义生成是重活，走 worker（ADR-017），禁 FastAPI BackgroundTasks。
- **存储缝**（ADR-024）：`music/` 前缀、DB 只存 key、渲染取公开对象 URL。
- **渲染服务零改动**：`packages/clip` 与 `apps/render` 只播 `spec.music.url`。

---

## 14. Status & Phases

| 期 | 内容 | 状态 |
|---|---|---|
| Phase 1 | Music 表 + 迁移 + MiniMax 生成 + 3 首默认曲 seed + `/api/v1/music` 端点 + Brand `musicId` + clip agent 选曲 + UI | ✅（2026-07） |
| Phase 2 | chat/editor 换曲与生成（`set_music` edit op + `add_music` skill + 重渲染） | ✅ |
| Phase 3 | 用户上传（权利声明 + 默认私有 + 审核 + ToS/DMCA） | 📋（§11） |
| Phase 4 | 高级音频编辑（增益自动化 / 起止裁剪 / 淡入淡出；多曲明确 L3 外） | 📋 |

---

## 15. Open Questions

1. **Public library moderation**: who reviews user-generated public music pieces?
2. **Revenue sharing**: if artists contribute music pieces, how are they credited/compensated?
3. **Quota model**: how many custom music generations per user/tier?（随计费线一并设计）

---

## 16. Related Documents

- `docs/DECISIONS.md` ADR-019: Built-in mood music library (filesystem-only, superseded by this doc).
- `docs/DECISIONS.md` ADR-022: Music library CRUD (management layer, superseded by ADR-023).
- `docs/DECISIONS.md` ADR-023: Music becomes an AI-generated, asset-based library.
- `docs/VIDEO_EDITOR.md` (`render_spec.music` contract).
- `docs/AGENT_ARCHITECTURE.md` (agent 编排集成).
- `docs/tasks/done/music-asset-library.md`: Implementation record.

---

## 17. Summary

Repurposer’s music architecture moves from a **static, file-based mood library** to an **AI-generated music library backed by a dedicated `music` table**:

- **Default**: 3 pre-generated AI music pieces (`calm`, `uplifting`, `corporate`) cover most speech/conference clips.
- **Selection**: Clip Agent picks the best existing music piece per clip, influenced by brand defaults and content mood.
- **Refinement**: Users can switch music pieces or generate custom music via chat/editor.
- **Reusability**: All generated music becomes a `Music` in the library, shareable across projects and eventually users.
- **Copyright**: Platform defaults to AI-generated music to avoid licensing fragility; user uploads are deferred and will require explicit rights management.

This design keeps the render contract stable, integrates cleanly with the agent architecture, and gives the product a scalable path from MVP to a community-driven music library.
