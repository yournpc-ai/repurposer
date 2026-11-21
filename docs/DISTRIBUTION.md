# Distribution — 分发模块设计

> Status: Active（2026-10-25）——核心 = 直发：后端（OAuth state nonce + Fernet token 加密 / 双平台 adapter / REST 路由 / worker publication 认领源）与前端（发布对话框 + 通知中心 + Settings Channels）代码已落；平台应用凭据、审批与真实联调随 R1.1 挂起，不能写成生产已打通。机构审核 / 数据回流为后续边缘功能；定时能力按本文当前状态机与 UI 实际入口分别验收。事件流由通知中心承载，见 §11。
>
> 模块定位与边界见 `MODULE_ARCHITECTURE.md`（六层图 §2、闭环流转图 §2.1、表归属 §4）；启动条件与排期见 `PROGRESS.md` §0.3；AI 标识分级见 ADR-026，合规实现仍是上线准备项；战略理由见 `STRATEGY.md` §3 牌 1、§4 风险 2。本文是 Distribution 模块设计与实现边界的**唯一事实源**——各文档只引用，不复述。

## 1. 模块职责与定位

内容离开产品的最后一公里：**发布动作**（核心，P1）——审核 / 调度 / 数据回流为边缘功能（P2）。

- 与 Pipeline 平级（2027 透镜）：Pipeline 管"生成什么"，Distribution 管"去了哪里、效果如何"。
- 审核是**分级**的（ADR-027）：个人免审秒发（发布对话框即确认点）；机构模式（P2）强制人工确认、审核人≠作者——审核队列是机构合规刚需，不是个人的第二页面。
- 发布数据回流是首发推荐分的**外部校准源**（内部校准源 = 用户选用行为；闭环流转图的回流②）——边缘功能（P2）。表结构随直发先行，理由是发布单/渠道账号是直发的载体，回流字段只做预留。

### 1.1 命名约定

- **模块 / 服务 / adapter / 文档 = `distribution`**（业务域）：`app/distribution/core.py`（状态机与发布单）、`channels.py`（OAuth/token）、`publishing.py`（worker 发布/轮询）、`routes.py`；平台 adapter 住 `app/distribution/adapters/`。
- **表 = 资源名**：`publications` / `channel_accounts` / `publication_events`——表名 ≠ 模块名（先例：Pipeline 模块的表叫 `assets` / `workflow_runs`，不叫 pipeline）。
- **REST 路径 = 资源名**：`/channels/*` / `/publications/*`，不加 `/distribution` 前缀（URL 命资源，不命模块）。
- **不叫 `posts`**（与 derivative 类型 `post` 撞名）；**不叫 `social_accounts`**（P2 的 ESP 渠道不是 social）。
- **`channel_accounts` 独立成表，不进 users**：一对多基数、唯一约束与 FK 需要表载体；credentials 是密钥，独立表 = 只有 Distribution 服务碰它；per-user 实体独立成表是仓库惯例。

## 2. 平台范围与准入决策

| 平台 | 决策 | 准入动作（墙钟，立即排队） |
|---|---|---|
| **LinkedIn** | 个人号先行（`w_member_social` 自助即得）；公司页（`w_organization_social` + Page Admin 验证）后置 | 创建开发者应用 + 添加 "Share on LinkedIn" / "Sign In with OpenID Connect" products |
| **TikTok** | **只做直发**（`video.publish`），等应用审核；不做草稿箱模式 | 企业开发者注册 + Content Posting API 直发权限申请（审核数周，期间用测试账号联调） |

不接（本期）：X（API 付费）、Instagram/Meta、YouTube（P2 后再评估，见 §13）。

## 3. 数据模型

表归属 Distribution（`MODULE_ARCHITECTURE.md` §4 已登记）；**状态机迁移只由 Distribution 服务函数执行**，其他模块只读。

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
                                 # 同一 JSONB 兼容）；加密 = ADR-031：Fernet + env key（§4.1）
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
output_id: UUID FK outputs | NOT NULL    # 单 FK（ADR-030）——发布目标一律是 outputs 行。
                                     # 与 Pipeline 的缝 = 产物表，Pipeline 内核
                                     # 变化不影响 publications 设计。
                                     # 不用 target_type/target_id 多态引用——DB 无法
                                     # 强制外键完整性，clip 删除会产生孤儿行
channel_account_id: UUID FK channel_accounts ON DELETE SET NULL
                             # 渠道断连只删 token，发布历史留存（配合 payload.channel 快照）
payload: JSONB                   # 发布快照：title / caption / hashtags / cover / 媒体引用
                                 # + channel 快照（platform + 账号显示名，断连后历史可读）
                                 # 建单时从 target 预填（outputs 表发布套件字段：
                                 # publishing.title/description/hashtags/cover_image_url
                                 # + files 媒体键）；
                                 # 快照后 clip 再编辑不同步（见 §14）
ai_disclosure: bool              # ADR-026：clip-spec 分类器推导，非用户勾选；
                                 # 提交审核时（draft→pending_review）重新推导——
                                 # 防建单后 clip 重渲染（如补 dub）导致标记陈旧
state: Enum("draft", "pending_review", "approved", "scheduled",
            "publishing", "unknown", "published", "failed", "cancelled")
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

索引：`(state, due_at)` 部分索引（`WHERE state IN ('SCHEDULED','PUBLISHING')`，认领扫描）；`(user_id, state)`（队列页）；`idempotency_key` 唯一；`(channel_account_id)`。

删除语义：`output_id` FK 为 `ON DELETE RESTRICT`——删除带非终态 publication 的产物会撞 FK 报错；服务层"先取消其非终态 publication 再删产物"的优雅路径未实施。

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
                                        （终态）             可核实的失败 ──► failed
公开发布请求已发出、结果无法确认 ──► unknown
尚可安全撤销的发布单 ──用户取消──► cancelled
```

规则：
- `published` 是终态（P1 不支持编辑/删除已发布内容，§13）。
- **`pending_review` / `approved` 为机构模式专属状态（ADR-027，P2）**：个人流 `draft → scheduled` 直发；机构模式才经审核态，驳回必须带 reason，回到 draft 重改后可再提交。
- 状态迁移只允许经 Distribution 服务函数；路由/其他模块不得直写 `state`。
- `publishing` 是**时间驱动状态**：TikTok 视频处理是异步的（返回 publish_id 后需轮询状态），进入 publishing 时 `due_at` = 下次轮询时间，worker 到期再认领续查，不阻塞认领线程。

### 3.4 `publication_events`（状态迁移日志 = 审核留痕）**（P2）**

> P1 个人流**不建此表**：其卖点是机构审核留痕（随机构模式回补）；P1 排障靠 `publications.last_error` + `attempt_count` + worker 日志。以下 schema 为回补时的定稿。

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
| `CHANNEL_CREDENTIALS_KEY` | `credentials_enc` 的加密 key（ADR-031：Fernet；空 = 明文存储带告警，仅限本地 dev） |

三个"刻意不加"：

- **Redirect URI 不加 env**：由既有 `api_public_url` 派生——`{api_public_url}/api/v1/channels/{platform}/callback`。平台后台必须登记完全一致的 URI（dev/prod 各一套，两边后台都登记）。
- **渠道开关不加 env**：presence-gating——`LINKEDIN_CLIENT_ID` 为空，该渠道在 UI 就不展示（"即将上线"态）。TikTok 审核期间代码可先合并，天然灰度，不需要 feature flag。
- **Scope 不加 env**：固化在代码里（LinkedIn `openid profile email w_member_social`；TikTok `user.info.basic video.publish`）——避免环境间 scope 漂移导致行为不一致。

本地联调注意：LinkedIn 允许 `http://localhost` redirect；**TikTok 要求 HTTPS**，本地需 tunnel（ngrok 等）联调。

## 5. 审核（分级，ADR-027）

- **个人模式（P1 默认）**：免审秒发——确认点是**发布对话框本身**（payload 预填可编辑 + `ai_disclosure` 徽标可见），编辑即确认；无第二页面、无"待审核"tab。
- **机构模式（P2，团队工作区）**：强制人工确认，审核人 ≠ 作者；`pending_review` 队列成为审核人的工作地点，驳回必填 reason；每次迁移写 `publication_events`（审核留痕 = 机构合规卖点）。
- 文案类（LinkedIn 长文）Art.50(4) 的 editorial control 由**对话框内人工确认**构成（个人/机构同此，ADR-026），不依赖队列。

## 6. 定时发布与 Worker 认领

Publication 是独立业务。Worker 优先领取到期的发布单，使用数据库时钟、行锁和 claim_token。每次领取有独立身份。平台返回任务 ID 后，Worker 按 due_at 有界轮询。LinkedIn 视频的任务 ID 指向上传的视频，视频处理就绪后还需要一次创建帖子的请求。

## 7. 发布、重试与核对

- 同一次用户操作复用 client_key 和发布单。平台创建公开帖子前，适配器把发送事实提交到同一 Publication。TikTok 的边界在 publish/video/init，LinkedIn 的边界在创建帖子，包括视频上传完成后的创建操作。
- 已发出创建请求，响应丢失或 Worker 强杀时进入 unknown。通知中心显示“发布结果待核对”。保留原执行身份、平台任务 ID、发布内容和项目；同一成片、渠道与内容在核对期间也不能换 client_key 再次发布。
- 平台已返回可查询任务 ID 时轮询已有任务。确认该请求成功后保存帖子 ID。明确拒绝的请求使用已有错误与退避策略。仍有未决外部事实时，取消、重发和项目删除均返回 409。
- 运维可用 `python -m app.distribution.publishing PUBLICATION_UUID --post-id POST_ID --evidence CASE_REFERENCE` 登记已核实的帖子。只有原发送者已停止且平台证实请求最终未发布时，才可使用 `--confirmed-not-published`。时间、依据、执行身份和结果保存在原发布单。单纯查不到帖子不足以确认未发布。核对操作本身不会向平台发帖。
- 后到的真实回执只归属原执行身份。人工核对和回执按行锁串行，终态只结算一次。

## 8. AI 内容披露（ADR-026 落地）

- `ai_disclosure` **由 clip-spec 分类器推导**（spec 含 dub 音轨 / AI 生成视觉 → `true`），不是用户勾选——用户永远不回答"这是不是 AI 生成"。
- 文件层：机器可读 AI 标识 / C2PA 仍是 **PLANNED 上线准备项**，当前不得声称 MP4 已嵌标或 LinkedIn 会自动补标。实现范围、合成轨道与纯剪辑分级归 ADR-026 和 `PROGRESS.md` §1.3；完成前发布对话框与平台 API 的披露不能由文件层替代。
- TikTok 端：voice-clone 内容属平台强制标记类，漏标的处罚落在用户账号上——`ai_disclosure` 徽标在**发布对话框**显式展示（个人模式）/ 机构审核页复核（机构模式）；API 披露字段是否暴露见 §14 开放问题。
- 纯剪辑+字幕内容（真实素材标准编辑）：`ai_disclosure=false`，不嵌标、不提示（ADR-026 纯剪辑豁免）。

## 9. 发布数据回流（P2）

- `metrics` 字段本期预留：发布后经 adapter `fetch_metrics` 按 T+1h / T+24h / T+7d 节奏拉取（worker 周期任务，非认领源），以 `{t1h: {...}, t24h: {...}, t7d: {...}}` 结构存 JSONB——保留"首小时 vs 首日"的速度信号，这是校准的重要特征。
- 数据用途唯一：校准首发推荐分（PROGRESS 明确不在本周期 → 需求池·persona 校准）；**不做面向用户的 analytics dashboard**（§13）。
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
- 每平台一个 adapter（`app/distribution/adapters/linkedin.py` / `tiktok.py`）；平台特有逻辑（LinkedIn 视频多步、TikTok `creator_info` 前置查询可发时长/隐私档）封装在 adapter 内，不外泄到服务层。
- 平台错误码 → 统一错误枚举（`token / rate_limit / content_policy / validation / unknown`），服务层只处理统一枚举。

### 10.2 REST 路由面（对外 API）

路由镜像状态机，**每个迁移一个显式动词端点**（权限与审计都比通用 PATCH state 清晰）：

| 端点 | 作用 | 状态迁移 |
|---|---|---|
| `GET /channels/platforms` | 平台 presence-gating 列表（各平台配置与否，"即将上线"态，§4.1） | — |
| `GET /channels/{platform}/oauth-url` | 生成授权链接 | — |
| `GET /channels/{platform}/callback` | OAuth 回跳，落 channel_account | — |
| `GET /channels` / `DELETE /channels/{id}` | 渠道列表 / 断开（删 token，历史留存） | — |
| `POST /projects/{id}/publications` | 从 clip/derivative 建发布单（payload 预填）；**P1 个人流建单即排期（出生 = `scheduled`，立即发布），不经过 `draft`** | → draft（P1：→ scheduled） |
| `POST /publications/{id}/submit` | 提交审核【机构模式 P2；此时重新推导 ai_disclosure】 | draft → pending_review |
| `POST /publications/{id}/approve` / `reject` | 审核【机构模式 P2；reject 必填 reason】 | → approved / → draft |
| `POST /publications/{id}/schedule` | 定时或立即（写 scheduled_at + due_at） | approved → scheduled |
| `POST /publications/{id}/cancel` | 取消尚可安全撤销的发布单 | → cancelled |
| `POST /publications/{id}/retry` | 失败后手动重试（重置 attempt_count，due 立即；有 platform_job_id 时 worker 走对账轮询而非重发，§7） | failed → scheduled |
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
submit(pub_id, user_id)                      # 【机构模式 P2】draft→pending_review；重推导 ai_disclosure
approve(pub_id, reviewer) / reject(...)      # 【机构模式 P2】reject 必填 reason
schedule(pub_id, user_id, when)              # approved→scheduled；due_at = scheduled_at
cancel(pub_id, user_id)                      # 无平台待核对操作且尚未发布 → cancelled

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

> 事件流（发布成功/失败/渠道过期）由**通知中心**承载（全局顶栏铃铛下拉，非页面），渠道连接的持续管理收进 **Settings**；原则 = 通知是事件流的呈现层，只有需要持续操作的东西才配拥有页面。
>
> 方向：**主路径 = 立即发布、个人免审**（ADR-027）。calendar 视图不做（P2+ 按使用数据验证再评估；模型已支持 `scheduled_at`/`due_at`，加上即零迁移）；竞品实证：Agent Opus 的 calendar 只是 projects 页视图 toggle、排期器在其 Pro 付费墙后（`research/agent-opus.md`）——创作工具品类的主流是"创作完立刻发"。

### 11.1 信息架构（三个入口 = 三种心智）

| 入口 | 位置 | 心智 |
|---|---|---|
| "发布"按钮 | clip / derivative 卡片 | "把这条发出去"（动作起点） |
| 发布结果/渠道事件 | 通知中心（全局顶栏铃铛） | "发出去之后发生了什么"（只读事件流） |
| 渠道连接 | Settings Channels | "连接账号" |

### 11.2 发布对话框（主创建路径 = 唯一确认点）

1. **渠道选择**：LinkedIn / TikTok 图标 + 已连接账号头像；未连接 → 就地引导。
2. **Payload 编辑**：预填 clip 发布套件字段——**用户在输入框里改不满意的地方，编辑即确认**（ADR-027）；多渠道同发按渠道分 tab，一次提交 N 张单（一渠道一单，§3）。
3. **AI 披露展示位**：`ai_disclosure=true` 时显式展示徽标 + 原因（"含声音克隆，将标记为 AI 生成"）——用户无勾选权，有知情权。
4. **定时（P2）**：P1 只有"立即发布"（= `scheduled_at` now，与定时同一代码路径，UI 不出 datetime picker）。
5. 点"发布" → toast"正在发布"，**不离开当前页**；事件序列：created → scheduled。

### 11.4 机构模式（P2 预览，ADR-027）

团队工作区上线后：审核队列页（`GET /publications?state=pending_review`，§10.2）成为审核人（≠ 作者）的工作地点；无审核权成员的对话框按钮从"发布"变"提交审核"；其余组件复用，零改版。

### 11.5 渠道 tab / 状态回显 / 设计纪律

- 渠道卡三态：**已连接**（头像 + 名字 + token 健康度）/ **未连接**（Connect 按钮）/ **未配置**（presence-gating "即将上线"，§4.1）。
- 项目页：clip/derivative 卡片上 scheduled / published Badge（平台图标 + 时间）；发布成功/失败 → 全局 sonner toast；列表轮询刷新（与 Clip.render_status 同款模式）。
- `rounded-md` / `border-subtle` + `shadow-*`；Badge 一律 `className="rounded-md"`；平台图标：lucide 有 `Linkedin`，TikTok 走"第三方 logo 无替代"例外（手写 SVG）。
- 新增 i18n keys：`publishing.*`、`channels.*`（en 先行，zh 镜像）。

## 12. 分期路线（排期以 `PROGRESS.md` 为准）

- **P1**：两张表（`publication_events` 属 P2，P1 排障靠 `last_error` + worker 日志）+ 状态机（个人流，ADR-027；建单即排期，产物出生 = `scheduled`）+ **LinkedIn 个人号 + TikTok 双平台直发**（TikTok 应用审核期间测试账号联调）+ **立即发布**（定时字段 schema 就位，datetime picker UI 入 P2）+ 幂等/重试。
- **P2**：机构审核队列（`pending_review`/`approved`）+ metrics 回流校准、newsletter ESP（自有渠道，对冲 LinkedIn 单押）、源→目的地自动规则、多号、公司页、团队审核角色。

## 13. 范围纪律（不做什么）

- 不编辑/删除已发布内容（平台 API 限制 + 范围控制）。
- 不做评论/私信/互动管理。
- 不做用户向 analytics dashboard；metrics 只为校准回流。
- 不接 X / Meta / YouTube（P2 后再按渠道数据评估）。
- 不做"一键全平台轰炸"式营销 blasts——一次发布单 = 一个渠道，调性纪律（知识资产，非病毒分发）。

## 14. 开放问题

1. **TikTok AI 标识 API 字段**：Content Posting API 是否暴露披露字段（2026-07 未见官方确认）——跟踪官方文档，出现后 adapter 接入；此前靠审核队列人工确认。
2. **payload 快照 vs 同步**：建单后 clip 再编辑，publication 不同步（快照语义）；是否需要"重新预填"按钮，看 P1 使用反馈。
3. **LinkedIn 大视频上传**：多步流程的分片大小与超时策略，联调时定。
