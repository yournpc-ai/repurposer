# 任务简报：Distribution UI——发布对话框 + 通知中心 + Settings Channels

> Status: Implemented（2026-07-24）
> 关联：`docs/DISTRIBUTION.md`（§11 修订）、`docs/MODULE_ARCHITECTURE.md` §4（notifications 表登记）、ROADMAP §5/§9。

## 背景

Distribution 后端（Phase A+B）落地后前端零入口。经 2026-07-24 讨论定界：**不做 sidebar 入口和发布记录页**——事件流由通知中心承载（ROADMAP §9"铃铛真实设计：发布结果"提前落地，distribution 为第一个事件源）；持续管理（渠道连接）放 Settings。

## 范围

### 后端（apps/api）
- `notifications` 表（id / user_id / type 字符串 / payload JSONB / read_at / created_at；partial unread 索引）+ Alembic 迁移 `b3d7f1a94e52`。
- `services/notifications.py`：create / list(+unread_count) / mark_all_read。
- 写入钩子：`services/distribution/core.py::_transition` 终态（PUBLISHED / FAILED）写通知；backoff 的 →SCHEDULED 不写。FAILED 且 `last_error == "channel_token_expired"` 时 type = `channel_expired`。平台/标题取自 payload 冻结快照（断连后可读）。
- `routers/notifications.py`：`GET /api/v1/notifications`（items + unread_count）、`POST /api/v1/notifications/read-all`。
- `routers/distribution.py`：`GET /channels/platforms`（presence-gating 三态）；OAuth 回调跳转 `/publishing` → `/settings`。
- `services/distribution/channels.py`：`_configured` 重构出 `is_configured` 谓词。

### 前端（apps/web）
- `components/AppHeader.tsx`：**全局真顶栏**（sticky top-0），挂 `__root.tsx`；含 SidebarTrigger / ThemeToggle / LanguageSwitcher / NotificationBell / credits pill。`SidebarInset` 改 `overflow-x-clip`（overflow-hidden 会破坏 sticky）。`index.tsx` 假 header 删除。
- `components/notifications/NotificationBell.tsx`：铃铛 + 未读红点（非数字）；DropdownMenu 面板（非页面）；条目 = 条级未读点 + 平台图标 + 标题 + 摘要 + 相对时间 + CTA（Open post ↗ / Retry / Reconnect）。30s 轮询（`toast:false`），打开面板即 read-all。未登录不渲染。
- `components/publish/PublishDialog.tsx` + `PlatformIcon.tsx`（LinkedIn 用 lucide；TikTok 手写 SVG 属第三方 logo 例外）。
- `AssetActionBar` 加 `onPublish`（Send icon，排在最后）；`ClipCard` 接线（仅渲染完成的 clip 显示）。
- `routes/settings.tsx`：Channels 区块三态卡（已连接 / 未连接 / 未配置=即将上线；expired 单独展示 + Reconnect）；读 `?connected= / ?error=` toast 后清 URL。sidebar footer 死 Settings 项接线。
- i18n：`notifications.*` / `publish.*` / `channels.*` / `settings.*`（en 先行，zh 镜像）。

## 验收标准

1. `alembic upgrade head` 建成 notifications 表；`pnpm tsc` 通过（zh 镜像完整性由 `Resources` 类型强制）。
2. 顶栏全局 sticky，滚动不消失；各页面不再有局部顶栏（brand-template 的编辑器工具栏除外）。
3. 发布对话框：分渠道 tab **草稿各自保留**（切 tab / 取消勾选再勾选不丢）；预填 `output.publishing` 套件；`ai_disclosure` 触发条件（provenance=generated 或 spec 含 dub）显示 ⓘ muted 小字。
4. 提交通道幂等：同一 dialog 会话一个 `client_key`，重复提交服务端返回同一行。
5. 无平台凭据时：dialog / Settings 显示"即将上线"（presence-gating），点 Connect 由 apiFetch 全局 toast 404 detail。
6. 铃铛：有未读显示红点；打开面板红点清除（read-all）；Retry / Reconnect / Open post 三个 CTA 可用。
7. OAuth 回调落地 `/settings?connected=` / `?error=` 并 toast。

## Prohibited Behaviors

- **禁止**新增 sidebar 入口 / 发布记录页（事件流 = 通知中心，管理 = Settings）。
- **禁止**改动 clip 卡片结构（卡片 UI 升级归 Gallery/composer 波次）；只许在 AssetActionBar 加图标。
- **禁止** datetime picker / 定时 UI（P2）；发布 = 立即。
- **禁止** notification 分页 / 每条目已读端点（面板 = 最近 N 条 + read-all）。
- **禁止**把通知写成 toast 之外的第二种页面内反馈（发布成功/失败只走铃铛 + 卡片状态，不做 inline 横幅）。
- **禁止**在 `_transition` 之外写 publication state；通知只在终态写，backoff 不打扰用户。
- UI 规范：Badge 一律 `rounded-md`；AI 披露文案禁止红色 / 勾选框（告知非警告）。
