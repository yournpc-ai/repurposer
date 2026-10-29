# PAYMENTS — 支付、订单与 Stripe 接入架构

> Status: 当前规范（2026-10-29）。Stripe 一次性积分充值首批已落码，migration、测试套件与真实联调未运行；剩余范围与验收欠账归 `tasks/stripe-credit-topup.md`，积分、钱包与扣费语义归 `BILLING.md`，排期归 `PROGRESS.md`。

## 0. 边界与目标形态

支付模块把外部法币收款转换为现有钱包的 `purchase` 台账，不重做积分系统，也不让积分台账认识法币。

首批目标形态固定为：

```text
SettingsDialog 积分 section
  → 后端创建 payment_order + Stripe Checkout Session
  → 用户在 Stripe 托管页面付款
  → Stripe webhook 到达后端
  → 验签、环境与订单校验、订单行锁
  → 同一事务写 purchase 台账 + 更新钱包 + 订单 paid
  → 前端读取真实订单与钱包状态
```

- **Checkout 托管收银台 + 服务端 webhook 是唯一支付链路**。不使用 Payment Link 代替产品内订单，不自建银行卡表单，不引入 Stripe.js，不在前端暴露 secret key。
- 首批只支持**一次性积分包、EUR、银行卡、`mode=payment`**。Checkout 显式限制为 `card`，不开放延迟到账支付方式。
- 成功 URL 只是浏览器返回信号，**永不产生入账**。只有签名有效且满足全部订单校验的 webhook 可以入账。
- 三个事实源各管一层：Stripe = 收款事实；`payment_orders` = 内部购买订单；`credit_transactions` = 积分余额变动事实。任何一层都不是另外两层的副本。
- 订阅、周期额度、升级/降级、Customer Portal、自动退款、VAT/发票定制与 Landing 订阅卡接线不是首批能力；启动条件见 §8。

## 1. 公司账号、环境与凭据

### 1.1 凭据职责

| 凭据 / ID | 来源 | 用途 | 可见范围 |
|---|---|---|---|
| `STRIPE_SECRET_KEY` | 公司 Stripe 账号的 test/live secret | 后端创建 Checkout Session 等 Stripe API 调用 | 仅服务端 secret store |
| `STRIPE_WEBHOOK_SECRET` | 本地 CLI 或 Dashboard webhook endpoint | 验证 `Stripe-Signature` | 仅对应环境的服务端 |
| `STRIPE_PRICE_*` | 公司 Stripe Dashboard 的 Product / Price | 服务端可售积分包白名单 | 后端配置；Price ID 可出现在服务端响应，但不由客户端任意指定 |
| `WEB_PUBLIC_URL` | 本项目公网 Web origin | 生成 Checkout success/cancel URL | 现有部署配置 |

公司 `sk_test_...` 只代表公司账号的 **test mode**，不代表已经取得 webhook secret 或 live 收款能力。本地不需要注册个人 Stripe 账号，也不需要 `stripe login`；CLI 直接读取公司 test key。

test 与 live 的 API key、webhook secret、Product / Price ID 全部独立。live key 由有权限的管理者直接写入生产 secret store，不通过聊天、工单、Git 或前端传递。疑似泄漏的 key 必须轮换。

### 1.2 环境变量

根 `.env` 只存当前环境真实值，`.env.example` 只存占位符：

```dotenv
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_STARTER=
```

当前只实现 `starter`：test 配置为 **1000 最小货币单位（€10）= 10,000 积分**，不是 live 定价承诺。缺少 Price 时 packages 返回空列表，新增档位必须同批扩展 Settings、registry、env example 与部署变量。`apps/api/app/config.py` 负责类型化读取，`docker-compose.yml` 只把变量传进 `api` 容器；`web` 与首批 `worker` 不需要支付 secret。

### 1.3 本地 Stripe CLI

CLI 只是本地事件转发器，不是应用运行时依赖，不进 Docker、不上生产。日常检查/启动统一使用：

```bash
./scripts/stripe_webhook_dev.sh
```

脚本只接受 test key，验证 `.env` 的 API key 与 Price 配置；缺少 CLI signing secret 时通过 `--print-secret` 生成并写入 `.env`，已有但不一致则报错，不会静默覆盖。已有匹配 listener 时只确认，多个 listener 会报错，未运行时才后台启动并等待 Ready。输出不打印密钥；API 不可达会单独警告。

需要手工诊断时才直接运行 CLI：

```bash
# 仅本机 macOS；生产服务器不安装
brew install stripe/stripe-cli/stripe

stripe listen \
  --api-key sk_test_... \
  --events checkout.session.completed,checkout.session.expired \
  --forward-to http://127.0.0.1:8000/api/v1/payments/stripe/webhook
```

CLI 输出的 `whsec_...` 填本地 `STRIPE_WEBHOOK_SECRET`。它与 Dashboard 公网 endpoint 的 secret 不通用。真实入账联调必须走实际 Checkout Session 与测试付款；通用 `stripe trigger` fixture 没有对应内部订单，只能验证接收/拒绝路径，不能冒充购买旅程通过。

## 2. Docker 与公网拓扑

不新增“Stripe 服务”或专用容器。支付能力属于现有 `api`，订单进入现有 Postgres：

```text
公司 Stripe
  │ HTTPS webhook
  ▼
公网 API origin / 反向代理
  │ Docker network
  ▼
本项目 api:8000 ──► 本项目 Postgres
```

- 公网 webhook 路径固定为 `POST /api/v1/payments/stripe/webhook`；完整 URL = `https://<API_PUBLIC_ORIGIN>/api/v1/payments/stripe/webhook`。
- 反向代理按本项目域名把 `/api/*` 转到本项目 `api` 容器，不与其他项目的容器或端口混用。webhook 不挂用户 JWT 中间件，签名就是其认证；必须保留原始请求体。
- `API_PUBLIC_URL` 当前可以是 Docker 内部地址，**不得据此推定 Stripe 可达**。公网 webhook URL 由实际 DNS / 反向代理确认后登记 Dashboard。
- 公网 test mode 也使用 Dashboard 创建的 webhook 及其独立 `whsec_...`；生产服务器不运行 CLI。
- 部署包含 API/Web 镜像更新与 Alembic migration。live 切换另走 §9，不把 test 验收写成真实收款验收。

## 3. 积分包与金额事实

可售积分包由后端 `PACKAGE_REGISTRY` 白名单定义，首批一张表都不需要用于商品目录。每个条目包含：

```text
package_key       稳定内部 key，如 starter
stripe_price_id   当前环境 Settings 中的 Price ID
amount_minor      预期收款金额（最小货币单位）
currency          eur
credits           支付成功授予的积分
active            是否可售
```

- 客户端只提交 `package_key`，永不提交或决定 `amount`、`currency`、`credits`、`price_id`。
- Stripe Price 是实际收款价格，服务端 registry 是允许销售与应授积分的白名单；创建订单时保存金额/币种/积分快照，webhook 再核对 Stripe Session，任何不一致都不入账。
- 积分包的购买换算与 `credits.per_cost_usd` 消耗比例完全解耦。调整消耗比例不重写已购买订单或台账。
- 前端展示数字来自服务端 packages 读面；名称与动作文案走现有 i18n，不复制第二份价格表到前端。

## 4. 数据模型

### 4.1 `payment_orders`

首批只新增这一张支付表，Owner = 平台层；migration 同批登记 `MODULE_ARCHITECTURE.md §4`。现有 `wallets` / `credit_transactions` 结构不变。

| 字段 | 类型 | 合同 |
|---|---|---|
| `id` | `UUID PK` | 内部订单 ID；写入 Checkout metadata |
| `user_id` | `UUID FK users.id NOT NULL` | 购买用户；与 `created_at` 建组合索引 |
| `package_key` | `String(40) NOT NULL` | 下单时的 registry key |
| `provider` | `String(20) NOT NULL` | 当前恒 `stripe` |
| `livemode` | `Boolean NOT NULL` | 下单环境；webhook 必须匹配 |
| `amount_minor` | `BigInteger NOT NULL` | 金额最小单位；禁止 float |
| `currency` | `String(3) NOT NULL` | 当前 `eur` |
| `credits` | `BigInteger NOT NULL` | 应授积分快照，必须 `> 0` |
| `status` | `String(20) NOT NULL` | `pending / paid / expired / failed`，应用层注册表校验 |
| `provider_checkout_session_id` | `String(255) NULL` | Stripe Checkout Session ID；UNIQUE |
| `provider_payment_intent_id` | `String(255) NULL` | 支付成功后记录，用于对账 |
| `credit_transaction_id` | `UUID FK credit_transactions.id NULL` | 已入账台账行；UNIQUE，一订单至多一条 purchase |
| `paid_at` | `DateTime(tz) NULL` | Stripe 确认支付的时间 |
| `credited_at` | `DateTime(tz) NULL` | 本系统完成积分入账的时间 |
| `created_at` | `DateTime(tz) NOT NULL` | 创建时间 |
| `updated_at` | `DateTime(tz) NULL` | 最近状态变化时间 |

金额非负、积分正数由应用与 DB 约束共同保证；状态字符串不使用 Postgres enum。`credit_transaction_id` 与订单行锁共同防止不同事件给同一订单重复入账。

首批不建独立 webhook event 表：Stripe Dashboard 保存事件与投递证据，`payment_orders` + `credit_transactions.idempotency_key` 已能保证入账正确性。确需本地长期留存完整事件/离线重放时另立 `payment_events`，但正确性不得依赖它。默认不保存完整 webhook payload、银行卡资料或敏感认证数据。

### 4.2 积分台账接缝

支付服务只经 `app/platform/billing.py` 的公开 `purchase_credits()` 动词写账，内部继续走 `_mutate()`；禁止支付路由直接 UPDATE wallet 或 INSERT 台账。

```text
kind = purchase
amount = payment_orders.credits
idempotency_key = "stripe:" + provider_event_id + ":purchase"
ref = {
  "payment_order_id": "<internal order uuid>",
  "payment_event": "evt_..."
}
```

订单行锁防止不同事件并发入账，台账唯一幂等键防止同一事件重放入账。`credit_transaction_id` 把两层事实显式连起来；append-only、balance_after、负余额与失败不扣费规则继续归 BILLING。

## 5. API 合同

所有路由挂现有 `/api/v1`：

| 方法与路径 | 认证 | 职责 |
|---|---|---|
| `GET /payments/packages` | 用户登录 | 返回当前 active 积分包的 `key / credits / amount_minor / currency` |
| `POST /payments/checkout-sessions` | 用户登录 | body 仅 `{package_key}`；创建内部订单与 Checkout，返回 `{order_id, checkout_url}` |
| `GET /payments/orders/{order_id}` | 用户登录 + owner | 返回订单状态与展示快照；永不触发入账 |
| `POST /payments/stripe/webhook` | Stripe 签名 | 处理支付确认与过期事件 |

Checkout 创建顺序：

1. 校验 registry 与登录用户，并读取 Stripe Price，确认 `active`、`one_time`、金额与币种全部匹配；任何配置错误都在用户可付款前拒绝。
2. 创建并提交 `pending` 订单，确保 webhook 到达前订单已可查。
3. 以内部 `order_id` 派生 Stripe API idempotency key，同一内部订单至多创建一个 Checkout Session。
4. 使用 `mode=payment`、显式 `card`、服务端 Price、`client_reference_id=user_id` 与 `metadata.order_id`。
5. success/cancel URL 由 `WEB_PUBLIC_URL` 派生到 `/settings`，携带内部 `order_id` 与返回状态；保存 Session ID 后返回托管 URL。
6. Stripe 创建失败将订单标为 `failed` 并走统一 API 错误；未支付重复订单不代表重复收款，用户只有在不同 Session 分别付款才分别购买。

## 6. Webhook 与订单状态机

首批只订阅：

- `checkout.session.completed`
- `checkout.session.expired`

处理纪律：

1. 读取**原始 request body** 与 `Stripe-Signature`，用当前环境 webhook secret 验签；不得先解析/重序列化 JSON 再验签。
2. 校验事件 `livemode`、订单环境、Session ID、`client_reference_id`、metadata 订单 ID、用户、套餐快照、金额与币种。metadata 只是定位线索，不是独立授权事实。
3. 已知订单使用 `SELECT ... FOR UPDATE` 串行化状态迁移。
4. `completed` 只有 `payment_status="paid"` 才可进入入账；未支付事件保持 pending，不写 purchase。
5. 订单已 paid / 已有 `credit_transaction_id` 时重复通知直接成功返回，不再次写账。
6. 订单状态、台账、钱包与支付时间在同一 DB 事务中提交；提交成功才返回 2xx。
7. `expired` 只允许 `pending → expired`；对 paid 订单单调无效，永不回滚已入账事实。
8. 签名错误返回 400；临时 DB/内部故障返回 500 让 Stripe 重试。未知订单、永久校验不符与不支持的事件类型不加积分，记录安全/运营信号后按确定策略 ACK，避免无意义重试风暴。
9. webhook 不调用 LLM、不排队执行生产任务、不做慢速外部动作；需要补数据时以有界 Stripe 读取或后续对账工具完成，不把收款确认依赖第三方非关键服务。

状态终态：

```text
pending ── paid webhook ──► paid（purchase 已同事务入账）
   └────── expired ───────► expired
   └────── checkout 创建失败 ──► failed
expired ── 乱序送达的 paid webhook ──► paid（已验证的付款事实优先）
paid 永不被 expired / failed / 浏览器返回覆盖
```

## 7. 前端座位与返回行为

- `components/settings/CreditsSection.tsx` 是唯一套餐购买面：保留余额/held/语义台账，新增积分包列表与购买按钮，替换付费套餐占位。按钮 pending 时禁止重复点击；不在 Dialog 内嵌银行卡表单或再开支付 Dialog。
- `components/credits/CreditsPill.tsx` 只新增“购买积分 / Add credits”入口，调用 `openSettings("credits")`；不复制套餐面板。
- `lib/payments.ts` 统一 packages / checkout / order 的 wire types 与 `apiFetch`；金额用 `Intl.NumberFormat` 按 EUR 与当前语言格式化，积分沿用 `formatCredits`。
- `routes/_app.settings.tsx` 复用为 Checkout return shim：接收 `checkout=success|cancelled&order_id=...`，打开积分 section 后回 `/home`；不新建支付设置页。
- 返回 success 只显示“正在确认付款”，有界轮询订单（2 秒一次、至多 30 秒）。只有服务端 `paid` 才显示充值成功并刷新 wallet/transactions；超时仍 pending 显示稍后刷新，不重复下单。
- cancelled 回到购买面且不入账，不显示伪造支付错误。所有新文案同步 `en.ts` / `zh.ts`。
- Landing 的 Pro / Institution 订阅卡与 AccountConsole 的订阅升级入口在订阅批之前不接一次性 Checkout，避免把不同商品混为同一承诺。

## 8. 订阅、退款与后续商业语义

以下均为 **PLANNED，未实现**，不得以支付首批落地自动宣称支持：

- 订阅需要 recurring Price、用户与 Stripe Customer/Subscription 映射、`invoice.paid` 周期 grant、续费/升级/降级/取消/支付失败状态机与 Customer Portal。
- 启动订阅前必须拍板周期额度是否清零、未用积分是否结转、取消生效时点、fair-use 与分桶消耗顺序；周期额度使用 `kind=grant`，不与一次性 `purchase` 混写。
- 自动退款/拒付需要独立事件、原订单关联和积分扣回政策。现有积分 `refund` 语义不得直接冒充法币退款；未拍板前只走人工退款与人工台账调整流程。
- VAT、发票、 receipts、退款政策、服务条款与隐私文案是 live 前置，不由 Stripe Checkout 自动代表完成。

## 9. 上线、对账与安全门

### 公网 test mode

- 部署代码与 migration，确认公网 webhook 到达本项目 API。
- Dashboard 创建 test endpoint 并配置对应 `whsec_...`，验证 test Price 与 registry 一致。
- 完成真实 Checkout 测试付款、重放、并发、过期、返回页与权限验收。

### live mode

- 管理者直接配置 `sk_live`、live webhook secret 与 live Price IDs；test/live 配置不得混用。
- 明确商品价格是否含税、VAT/发票、退款与拒付处理、客服与监控责任人。
- 完成小额真实付款及按已拍板政策的退款演练；test 通过不等于 live 通过。

### 对账不变量

- 每个 paid 订单恰好一条 `credit_transaction_id`，其 `kind=purchase`、`amount=orders.credits`、owner 与订单一致。
- 每个 pending/expired/failed 订单没有 purchase 台账。
- Stripe 已付款但内部未 paid 的 Session 可由 Session ID 对账；不得通过手工改余额修复，必须重放/补走同一入账写门。
- 日志只记内部订单、Stripe Session/Event/PaymentIntent ID、状态与校验码，不记 secret、完整 payload 或银行卡资料。
