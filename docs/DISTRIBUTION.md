# Distribution — 分发模块设计

> Status: Active（2026-07-21 建立；📋 未实现——表结构与平台决策先行）
>
> 模块定位与边界见 `MODULE_ARCHITECTURE.md`（六层图 §2、闭环流转图 §2.1、表归属 §4）；排期见 `ROADMAP.md` §5；AI 标识分级见 ADR-026；战略理由（工作流闭环 / LinkedIn 单押风险）见 `STRATEGY.md` §3 牌 1、§4 风险 2。本文是 Distribution 模块设计与实现细节的**唯一事实源**——各文档只引用，不复述。

## 1. 模块职责与定位

内容离开产品的最后一公里：**审核 → 调度 → 发布 → 数据回流**。

- 与 Pipeline 平级（2027 透镜）：Pipeline 管"生成什么"，Distribution 管"去了哪里、效果如何"。
- 审核队列是 HITL 的正确形态，机构合规刚需（2026-07-21 定：**默认全员强制人工确认**）。
- 发布数据回流是传播潜力分**唯一的真实校准源**（闭环流转图的回流②）；表结构现在不定，闭环永远断着。

### 1.1 命名约定（2026-07-21 定）

- **模块 / 服务 / adapter / 文档 = `distribution`**（业务域）：`services/distribution.py`（长大可拆 `services/distribution/` 包，adapter 入包）、`routers/distribution.py`。
- **表 = 资源名**：`publications` / `channel_accounts` / `publication_events`——表名 ≠ 模块名（先例：Pipeline 模块的表叫 `assets` / `workflow_runs`，不叫 pipeline）。
- **REST 路径 = 资源名**：`/channels/*` / `/publications/*`，不加 `/distribution` 前缀（URL 命资源，不命模块）。
- **不叫 `posts`**（与 derivative 类型 `post` 撞名）；**不叫 `social_accounts`**（P2 的 ESP 渠道不是 social）。
- **`channel_accounts` 独立成表，不进 users**：一对多基数、唯一约束与 FK 需要表载体；credentials 是密钥，独立表 = 只有 Distribution 服务碰它；per-user 实体独立成表是仓库惯例。

## 2. 平台范围与准入决策（2026-07-21）

| 平台 | 决策 | 准入动作（墙钟，立即排队） |
|---|---|---|
| **LinkedIn** | 个人号先行（`w_member_social` 自助即得）；公司页（`w_organization_social` + Page Admin 验证）后置 | 创建开发者应用 + 添加 "Share on LinkedIn" / "Sign In with OpenID Connect" products |
| **TikTok** | **只做直发**（`video.publish`），等应用审核；不做草稿箱模式 | 企业开发者注册 + Content Posting API 直发权限申请（审核数周，期间用测试账号联调） |

不接（本期）：X（API 付费）、Instagram/Meta、YouTube（P2 后再评估，见 §13）。

## 3. 数据模型

表归属 Distribution（`MODULE_ARCHITECTURE.md` §4 已登记 📋）；**状态机迁移只由 Distribution 服务函数执行**，其他模块只读。

### 3.1 `channel_accounts`（渠道账号 = OAuth token 生命周期）

```python
id: UUID PK
user_id: UUID FK users
platform: Enum("linkedin", "tiktok")
platform_user_id: str            # LinkedIn sub / TikTok open_id
display_name: str
avatar_url: str | None
scopes: JSON                     # list[str]，授权时快照
credentials_enc: JSONB           # 加密存储：{access_token, refresh_token, ...}
                                 # 形状随平台（P2 的 ESP 渠道是 API-key 而非 OAuth，
                                 # 同一 JSONB 兼容）；加密方案见 §14 开放问题
token_expires_at: datetime | None
status: Enum("active", "expired", "revoked")
last_refreshed_at: datetime | None
created_at / updated_at

UniqueConstraint(user_id, platform, platform_user_id)
# P1 产品面每平台只暴露一个号；schema 已允许未来多号。
```

### 3.2 `publications`（发布单 = 状态机 + 幂等 + 回流预留）

```python
id: UUID PK
user_id: UUID FK                 # 去规范化（同 Asset 约定）：免 join 做归属校验
project_id: UUID FK
clip_id: UUID FK clips | NULL        # 二选一 + CHECK 约束（沿用 Asset 表
derivative_id: UUID FK derivatives | NULL  # ck_asset_owner_set / ck_asset_owner_single
                                     # 先例）：ck_pub_target_set + ck_pub_target_single。
                                     # 不用 target_type/target_id 多态引用——DB 无法
                                     # 强制外键完整性，clip 删除会产生孤儿行
channel_account_id: UUID FK channel_accounts ON DELETE SET NULL
                             # 渠道断连只删 token，发布历史留存（配合 payload.channel 快照）
payload: JSONB                   # 发布快照：title / caption / hashtags / cover / 媒体引用
                                 # + channel 快照（platform + 账号显示名，断连后历史可读）
                                 # 建单时从 target 预填（clips 表已有发布套件字段：
                                 # title/description/hashtags/cover_image_url）；
                                 # 快照后 clip 再编辑不同步（见 §14）
ai_disclosure: bool              # ADR-026：clip-spec 分类器推导，非用户勾选；
                                 # 提交审核时（draft→pending_review）重新推导——
                                 # 防建单后 clip 重渲染（如补 dub）导致标记陈旧
state: Enum("draft", "pending_review", "approved", "scheduled",
            "publishing", "published", "failed", "cancelled")
scheduled_at: datetime | None    # 用户选定的发布时间（展示/审计值）
due_at: datetime | None          # worker 认领谓词（唯一时间源）：初始 = scheduled_at，
                                 # 失败退避时改写为下次重试时间
published_at: datetime | None
platform_job_id: str | None      # 平台侧任务句柄（TikTok publish_id /
                                 # LinkedIn video URN）——不确定结果的对账锚点（§7）
platform_post_id: str | None
platform_post_url: str | None
idempotency_key: str unique      # 我方 DB 级防重：双击/刷新/重复提交不产生两行
attempt_count: int = 0
last_error: Text | None
metrics: JSONB | None            # 回流字段（P2）：{t1h: {...}, t24h: {...}, t7d: {...}}
created_at / updated_at
```

索引：`(state, due_at)` 部分索引（`WHERE state='scheduled'`，认领扫描）；`(user_id, state)`（队列页）；`idempotency_key` 唯一；`(channel_account_id)`。

删除语义：删除 clip/derivative 前，服务层先取消其非终态 publication（FK `ON DELETE RESTRICT` 兜底）。

### 3.3 状态机

```
draft ──提交审核──► pending_review ──通过──► approved ──定时/立即──► scheduled
                        │                                            │ worker 认领到期行
                        └──驳回(带 reason)──► draft                   ▼
                                                                publishing
                                                                  │     │
                                            平台回执 post_id ◄── 成功     失败 ──► failed
                                            ▼                            │
                                        published          attempt<N: 退避后回 scheduled
                                        （终态）             超限/用户取消 ──► cancelled
任何 published 之前的状态 ──用户取消──► cancelled
```

规则：
- `published` 是终态（P1 不支持编辑/删除已发布内容，§13）。
- 驳回必须带 reason，回到 draft 重改后可再提交。
- 状态迁移只允许经 Distribution 服务函数；路由/其他模块不得直写 `state`。
- `publishing` 是**时间驱动状态**：TikTok 视频处理是异步的（返回 publish_id 后需轮询状态），进入 publishing 时 `due_at` = 下次轮询时间，worker 到期再认领续查，不阻塞认领线程。

### 3.4 `publication_events`（状态迁移日志 = 审核留痕）

```python
id: UUID PK
publication_id: UUID FK publications ON DELETE CASCADE
from_state: str | None           # NULL = 建单
to_state: str
actor_id: UUID FK users | NULL   # NULL = worker / 系统
reason: Text | None              # 驳回必填（状态机规则）
created_at
```

每条状态迁移写一行。两个用途：机构合规要的**审核留痕**（谁、何时、通过/驳回了什么——审核队列的卖点落点）；发布排障的事后现场（哪一步、什么错误码）。队列页的"审核人/审核时间"从最新事件 join 得出，不在 publications 上冗余列。

## 4. OAuth 与 token 生命周期

- **LinkedIn**：Authorization Code + OpenID Connect（`openid profile email w_member_social`）；access token 长有效期 + refresh 流程，过期前置后台刷新。
- **TikTok**：OAuth 2.0（`user.info.basic video.publish`），以 `open_id` 为平台用户键；短 access token + 长 refresh token，发布前检查 `token_expires_at`，过期先刷新。
- Token 状态为 `expired` 时渠道设置页提示重连；`revoked`（用户在平台侧解除授权）由发布失败/刷新失败的错误码识别并落态。
- 发布前必查 `creator` 能力（TikTok `creator_info` 查询：可发视频时长/隐私档），不满足则建单时拦截。

### 4.1 配置（env，命名沿用 `config.py` 前缀惯例）

| env | 用途 |
|---|---|
| `LINKEDIN_CLIENT_ID` / `LINKEDIN_CLIENT_SECRET` | LinkedIn 应用凭证 |
| `TIKTOK_CLIENT_KEY` / `TIKTOK_CLIENT_SECRET` | TikTok 应用凭证（官方字段就叫 client_key，不是 client_id） |
| `CHANNEL_CREDENTIALS_KEY` | `credentials_enc` 的加密 key（方案定案走 ADR，§14 开放问题 2） |

三个"刻意不加"：

- **Redirect URI 不加 env**：由既有 `api_public_url` 派生——`{api_public_url}/api/v1/channels/{platform}/callback`。平台后台必须登记完全一致的 URI（dev/prod 各一套，两边后台都登记）。
- **渠道开关不加 env**：presence-gating——`LINKEDIN_CLIENT_ID` 为空，该渠道在 UI 就不展示（"即将上线"态）。TikTok 审核期间代码可先合并，天然灰度，不需要 feature flag。
- **Scope 不加 env**：固化在代码里（LinkedIn `openid profile email w_member_social`；TikTok `user.info.basic video.publish`）——避免环境间 scope 漂移导致行为不一致。

本地联调注意：LinkedIn 允许 `http://localhost` redirect；**TikTok 要求 HTTPS**，本地需 tunnel（ngrok 等）联调。

## 5. 审核队列

- **默认全员强制人工确认**（2026-07-21 决策）：`approved` 之前没有人肉节点不得进入调度。
- P1 形态：自审 + 确认页（用户=审核人，团队角色等 P2 团队工作区）；机构卖点是**队列与留痕**，不是多角色本身。
- 队列页：`pending_review` 列表，展示 payload 全文 + 媒体预览 + `ai_disclosure` 状态；通过 / 驳回（必填 reason）。
- 文案类（LinkedIn 长文）的人工确认同时构成 Art.50(4) 披露豁免所需的 editorial control（ADR-026）。

## 6. 定时发布与 worker 认领

- **不需要新 worker**：复用现有 worker 进程（`python -m app.worker`，ADR-017），publication 是**第四认领源**——与 Asset / WorkflowRun / Clip.render_status 并列，`FOR UPDATE SKIP LOCKED`。
- **认领谓词只有 `due_at`**：`state=scheduled AND due_at <= now()` 发起发布；`state=publishing AND due_at <= now()` 继续状态轮询。首次 `due_at = scheduled_at`，失败退避与轮询间隔都改写 `due_at`——单一时间源，重试不会绕过退避窗口。
- **认领优先级**：每个 worker 循环先查 publication（通常为空表，成本可忽略）再查其他源——定时发布是**对用户的时刻承诺**（"周三 9:00 发"），不能被 ASR/渲染等重任务挤后。
- 认领后 `state=publishing` 再调 adapter；进程崩溃由 `reap_stale` 回收（与 Asset/Run 同款语义）。
- **未来拆解阀门**：发布量上来、或要对平台限流做进程级隔离时，可拆独立 worker 进程——调用方不变（仍是写表认领），P1 不拆。
- 用户时区在 UI 层转换，`scheduled_at`/`due_at` 一律 UTC。

## 7. 幂等、重试与失败语义

- 建单即生成 `idempotency_key`（target + channel + scheduled_at 哈希）：双击、刷新、重复提交不会在我方 DB 产生两条发布单。但注意：**平台不接受我们的幂等键**，"重复发布"不是平台会返回的错误码——不能指望它兜底。
- **不确定结果必须对账，禁止盲重试**：请求发出后超时/5xx（平台可能已受理），先凭 `platform_job_id`（TikTok `publish_id` 状态查询 / LinkedIn video URN）查平台侧真实状态——确认未成才允许重试；确认已成则回写 `platform_post_id` 按成功处理。这是"两将军问题"的标准解法：平台 job 句柄是唯一的对账锚点。
- 确定性失败退避：指数 backoff（如 1m/5m/30m，改写 `due_at`），`attempt_count` 超限 → `failed` 定格 + 界面提示，用户可手动重试或取消。
- Token 类失败（401）→ 刷新后重试一次，仍失败落 `channel_accounts.status=expired` 并提示重连，**不算发布失败**。

## 8. AI 内容披露（ADR-026 落地）

- `ai_disclosure` **由 clip-spec 分类器推导**（spec 含 dub 音轨 / AI 生成视觉 → `true`），不是用户勾选——用户永远不回答"这是不是 AI 生成"。
- 文件层：合成轨道产物的 MP4 已嵌 C2PA（ROADMAP P0-1），LinkedIn 端靠平台自动检测打 "CR" 标，我们零动作。
- TikTok 端：审核队列人工确认标识状态（API 披露字段是否暴露见 §14 开放问题）；voice-clone 内容属平台强制标记类，漏标的处罚落在用户账号上，审核页必须显式展示。
- 纯剪辑+字幕内容（真实素材标准编辑）：`ai_disclosure=false`，不嵌标、不提示（ADR-026 纯剪辑豁免）。

## 9. 发布数据回流（P2）

- `metrics` 字段本期预留：发布后经 adapter `fetch_metrics` 按 T+1h / T+24h / T+7d 节奏拉取（worker 周期任务，非认领源），以 `{t1h: {...}, t24h: {...}, t7d: {...}}` 结构存 JSONB——保留"首小时 vs 首日"的速度信号，这是校准的重要特征。
- 数据用途唯一：校准传播潜力分（`ROADMAP.md` §5 末行 → §1 persona/打分校准）；**不做面向用户的 analytics dashboard**（§13）。
- 升级路径：若校准需要跨发布单的时序查询（JSONB 不便聚合），再拆 `publication_metrics(publication_id, pulled_at, ...)` 明细表——P2 按校准的实际查询模式定，现在不过度设计。

## 10. 平台 adapter 接口与 REST 路由

### 10.1 进程内 adapter 接口

```python
class PlatformAdapter(Protocol):
    async def oauth_url(self, state: str) -> str
    async def exchange_code(self, code: str) -> ChannelAccountPayload
    async def refresh(self, account: ChannelAccount) -> ChannelAccount

    # 发布拆两段（不是一次性 publish）：
    async def begin_publish(self, account, payload) -> JobHandle
        # 发起发布 → 平台 job 句柄（TikTok publish_id / LinkedIn video URN），
        # 服务层立刻持久化到 publications.platform_job_id —— 此后进程崩溃也有对账锚点
    async def await_publish(self, account, job: JobHandle) -> PublishResult
        # 轮询平台状态 → published(post_id, url) | failed(统一错误枚举) | pending
        # worker 在 publishing 状态按 due_at 节奏重复调用

    async def fetch_metrics(self, account, post_id: str) -> Metrics  # P2
```

- 为什么拆两段：两家平台的视频发布**都是异步的**（TikTok 上传后需轮询 publish 状态；LinkedIn 视频 initialize→upload→finalize 多步）。合并成一个 `publish()` 会把"等待"憋在 worker 里，且崩溃后无对账锚点。
- 每平台一个 adapter（`linkedin.py` / `tiktok.py`）；平台特有逻辑（LinkedIn 视频多步、TikTok `creator_info` 前置查询可发时长/隐私档）封装在 adapter 内，不外泄到服务层。
- 平台错误码 → 统一错误枚举（`token / rate_limit / content_policy / validation / unknown`），服务层只处理统一枚举。

### 10.2 REST 路由面（对外 API）

路由镜像状态机，**每个迁移一个显式动词端点**（权限与审计都比通用 PATCH state 清晰）：

| 端点 | 作用 | 状态迁移 |
|---|---|---|
| `GET /channels/{platform}/oauth-url` | 生成授权链接 | — |
| `GET /channels/{platform}/callback` | OAuth 回跳，落 channel_account | — |
| `GET /channels` / `DELETE /channels/{id}` | 渠道列表 / 断开（删 token，历史留存） | — |
| `POST /projects/{id}/publications` | 从 clip/derivative 建发布单（payload 预填） | → draft |
| `POST /publications/{id}/submit` | 提交审核（**此时重新推导 ai_disclosure**） | draft → pending_review |
| `POST /publications/{id}/approve` / `reject` | 审核（reject 必填 reason） | → approved / → draft |
| `POST /publications/{id}/schedule` | 定时或立即（写 scheduled_at + due_at） | approved → scheduled |
| `POST /publications/{id}/cancel` | 取消（published 前任意态） | → cancelled |
| `GET /publications?state=&project_id=` | 列表（审核队列页 = `state=pending_review`） | — |
| `GET /publications/{id}` | 详情 + publication_events 时间线 | — |

约定：路由只做参数校验与调用服务函数；状态迁移、事件写入、due_at 计算全在 Distribution 服务层（守 §3.3 规则）；全部走 `apiFetch` + 全局 toast（前端约定）。

### 10.3 服务层函数清单（状态机的唯一写者）

```python
# ── 渠道侧 ──────────────────────────────────────────────
connect_start(platform, user_id) -> url      # 生成 OAuth 链接（带 state nonce 防 CSRF）
connect_finish(platform, code, state)        # 换 token，upsert channel_account
disconnect(account_id, user_id)              # 删 credentials，发布历史留存（SET NULL）
refresh_if_needed(account) -> account        # token 过期前刷新

# ── 发布单生命周期（每个都经 _transition 写事件）─────────
create_publication(project_id, target, channel_id, overrides)
                                             # payload 预填快照 + idempotency_key
submit(pub_id, user_id)                      # draft→pending_review；重推导 ai_disclosure
approve(pub_id, reviewer) / reject(pub_id, reviewer, reason)
schedule(pub_id, user_id, when)              # approved→scheduled；due_at = scheduled_at
cancel(pub_id, user_id)                      # published 前任意态 → cancelled

# ── worker 侧（同进程第四认领源，§6）─────────────────────
claim_due_publications()                     # SKIP LOCKED；每轮循环最先查
execute_publication(pub)                     # refresh → begin_publish → 存 job_id
                                             # → due_at = 轮询间隔
poll_publication(pub)                        # await_publish → published / failed / 续等
                                             # （不确定结果的对账逻辑在此，§7）
reap_stale_publications()                    # publishing 卡死回收

# ── 内部（模块外不可见）─────────────────────────────────
_transition(pub, to_state, actor, reason)    # 唯一状态写者：改 state + 写 publication_events
_classify_ai_disclosure(target) -> bool      # clip-spec 分类器（ADR-026）
_build_payload(target, channel) -> dict      # 预填快照（含 channel 快照，断连后历史可读）
```

规则：`_transition` 之外的任何代码（路由、其他模块、脚本）不得写 `state` 列；查询函数（`list_publications` / `get_publication` 带 events 时间线）只读，所有模块可用。

## 11. UI 面

| 面 | 内容 |
|---|---|
| Clip/derivative 卡片 | "发布"入口 → 建 publication（payload 预填，可改） |
| 审核队列页 | pending_review 列表；通过/驳回；`ai_disclosure` 显式展示 |
| 渠道设置页 | 连接/断开 LinkedIn、TikTok；token 状态与过期重连提示 |
| 项目页 | 各产物 publication 状态徽标（scheduled/published + 平台原帖链接） |

## 12. 分期路线（排期以 `ROADMAP.md` §5 为准）

- **P1**：两张表 + 状态机 + 审核队列（自审形态）+ LinkedIn 个人号直发 + TikTok 直发（审核通过后）+ 定时发布 + 幂等/重试。
- **P2**：metrics 回流校准、newsletter ESP（自有渠道，对冲 LinkedIn 单押）、源→目的地自动规则、多号、公司页、团队审核角色。

## 13. 范围纪律（不做什么）

- 不编辑/删除已发布内容（平台 API 限制 + 范围控制）。
- 不做评论/私信/互动管理。
- 不做用户向 analytics dashboard；metrics 只为校准回流。
- 不接 X / Meta / YouTube（P2 后再按渠道数据评估）。
- 不做"一键全平台轰炸"式营销 blasts——一次发布单 = 一个渠道，调性纪律（知识资产，非病毒分发）。

## 14. 开放问题

1. **TikTok AI 标识 API 字段**：Content Posting API 是否暴露披露字段（2026-07 未见官方确认）——跟踪官方文档，出现后 adapter 接入；此前靠审核队列人工确认。
2. **Token 加密方案**：应用级加密的 key 管理（env key + Fernet vs KMS）——随表结构落地时定，写 ADR。
3. **payload 快照 vs 同步**：建单后 clip 再编辑，publication 不同步（快照语义）；是否需要"重新预填"按钮，看 P1 使用反馈。
4. **LinkedIn 大视频上传**：多步流程的分片大小与超时策略，联调时定。
