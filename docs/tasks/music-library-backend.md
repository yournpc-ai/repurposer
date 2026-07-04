# Music library backend

> Summary for reviewers. Full rationale in `docs/DECISIONS.md`, ADR-022.

## Summary

Implements backend CRUD for the brand-template Music panel. Previously, official
tracks were hardcoded with no backing data, and personal uploads were client-only
blob URLs that did not survive a page refresh.

## Changes

- **New table** `music_tracks` (`apps/api/app/models/tables.py`, migration
  `0026843ad9e7`). One row per track; `user_id IS NULL` denotes an official/
  built-in track, a non-null value denotes a personal upload. Columns: `title`,
  `filename`, `file_url`, `duration_seconds`, `source_note`, `created_at`.
- **New router** `apps/api/app/routers/music_tracks.py`, mounted at `/api/v1/music`:
  - `GET /api/v1/music?scope=official|personal` — list
  - `POST /api/v1/music` — multipart upload (`scope=official` requires `mood`;
    `scope=personal` is scoped to the current user)
  - `DELETE /api/v1/music/{id}`
  - `GET /api/v1/music/track/{id}` — Range-capable stream by id
- **Frontend** (`apps/web/src/components/brand-template/music-panel.tsx`) now
  calls these endpoints instead of `URL.createObjectURL`. Personal uploads
  persist across a page refresh; official tracks display real title/duration
  once populated.
- **`docker-compose.yml`**: added `MUSIC_DIR` and a `./data/music` volume mount
  to the `api`/`worker` services (previously only `uploads`/`outputs` were
  mounted, so uploads made in full-Docker mode would not have persisted).

## Compatibility

The code path that feeds the Remotion renderer is unchanged:
`services/brand.py:music_from_template`, `services/storage.py:resolve_music_safe`,
and the mood-keyed `GET /api/v1/music/{mood}` route in `routers/files.py` continue
to resolve official tracks by filename convention (`data/music/{mood}.<ext>`).
Uploading an official track through the new endpoint writes to that same file;
the render pipeline has no dependency on the new router. Verified end-to-end:
uploaded a `calm` track and confirmed the existing mood route served it; deleted
it and confirmed the route returned 404 again.

## Out of scope

- `SOURCES.md` file-editor endpoints (proposed in the original task brief) —
  superseded by a per-track `source_note` field.
- Audio-timeline trim/offset (start position within the video; start position
  within the track) — reserved via a comment on `ClipMusic`
  (`schemas.py` and `packages/clip/src/types.ts`) only. No fields added, no
  renderer changes. Pending a dedicated design discussion.
- No UI for uploading official tracks. The endpoint is available (e.g. via
  `/docs`), but populating `data/music/` remains an operator/admin action
  rather than an end-user `/brand-template` feature.

---

# 音乐库后端

> 面向审阅者的变更摘要，完整决策记录见 `docs/DECISIONS.md` ADR-022。

## 摘要

为 brand-template 的 Music 面板实现了后端 CRUD。此前，官方曲目为硬编码且无实际数据支撑，个人上传曲目仅存在于前端（blob URL），页面刷新后即丢失。

## 变更内容

- **新增数据表** `music_tracks`（`apps/api/app/models/tables.py`，迁移文件
  `0026843ad9e7`）。每首曲目对应一行记录；`user_id` 为空表示官方/内置曲目，
  非空表示用户上传的个人曲目。字段包括 `title`、`filename`、`file_url`、
  `duration_seconds`、`source_note`、`created_at`。
- **新增路由** `apps/api/app/routers/music_tracks.py`，挂载于 `/api/v1/music`：
  - `GET /api/v1/music?scope=official|personal`：列表查询
  - `POST /api/v1/music`：表单上传（`scope=official` 需提供 `mood`；
    `scope=personal` 按当前用户隔离）
  - `DELETE /api/v1/music/{id}`
  - `GET /api/v1/music/track/{id}`：按 id 的流式接口，支持 Range 请求
- **前端**（`apps/web/src/components/brand-template/music-panel.tsx`）改为
  调用上述接口，不再使用 `URL.createObjectURL`。个人上传曲目在页面刷新后
  依然存在；官方曲目一经录入即展示真实的标题与时长。
- **`docker-compose.yml`**：为 `api`/`worker` 服务补充了 `MUSIC_DIR` 环境
  变量及 `./data/music` 卷挂载（此前仅挂载了 `uploads`/`outputs`，全 Docker
  模式下的音乐上传原本不会持久化）。

## 兼容性

实际供 Remotion 渲染器使用的代码路径未发生变更：
`services/brand.py:music_from_template`、`services/storage.py:resolve_music_safe`
以及 `routers/files.py` 中按 mood 取值的 `GET /api/v1/music/{mood}` 路由，
仍按既有文件命名约定（`data/music/{mood}.<ext>`）解析官方曲目。通过新接口
上传官方曲目，本质上是写入同一约定文件；渲染管线对新路由的存在没有依赖。
已完成端到端验证：上传 `calm` 曲目后确认旧路由可正常读取；删除后确认该
路由重新返回 404。

## 本次不包含的内容

- `SOURCES.md` 整文件在线编辑接口（原任务简报中提出）——由更轻量的逐曲目
  `source_note` 字段替代。
- 音频时间轴剪辑/偏移（曲目在视频时间轴上的起始位置、曲目自身的播放起点）
  ——仅在 `ClipMusic`（`schemas.py` 与 `packages/clip/src/types.ts`）中以
  注释形式预留，未添加字段，亦未改动渲染器。具体方案有待专门讨论后确定。
- 未提供"上传官方曲目"的界面。接口本身可用（如通过 `/docs` 调用），但当前
  阶段填充 `data/music/` 仍属运维/管理员操作，尚未作为 `/brand-template`
  面向终端用户的功能。
