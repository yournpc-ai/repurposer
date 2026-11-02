# Stripe 一次性积分充值——施工合同

> Status: ACTIVE（2026-11-02）。金额预设、自由金额、Checkout、webhook、purchase 与前端购买面已落码；既有 €10 订单已验证本地真实 Checkout → webhook → paid/purchase → UI 主旅程且只有一条入账台账。当前预设与自由金额统一由前端提交 `amount_minor`、服务端以 `price_data` 创建 Checkout；该改动后的真实联调、重放、并发、测试套件和公网部署未运行。长期架构与字段/API 合同归 `docs/PAYMENTS.md`，积分语义归 `BILLING.md`；本文件只载首批施工范围、依赖与验收。

## 0. 目标与当前事实

用一个真实公司 Stripe test 账号跑通并产品化：

```text
输入金额或选择金额预设 → Stripe Checkout 测试付款 → webhook 验签
→ payment_orders paid + purchase 台账同事务提交
→ SettingsDialog 显示真实充值结果与钱包余额
```

当前事实与外部输入：

- 已有公司 Stripe **test API secret key**；它不是 webhook secret，也不具备 live 收款语义。
- 本地 webhook secret 由 Stripe CLI 生成；公网 secret 由 Dashboard endpoint 生成，二者分开配置。
- 现有钱包、台账、`_mutate()` 幂等写门与 purchase → topup 读投影已复用；支付路由、订单表和购买 UI 已实现，既有本地真实主旅程已验证。
- 服务端预设 registry 为 `starter = €10 / 10,000`、`topup_20 = €20 / 20,000`、`topup_50 = €50 / 50,000` 积分，均不代表 live 定价。预设按钮只回填前端金额 input，下单始终提交整数 `amount_minor`。
- 自由金额当前为 **€1 = 1,000 积分、单次 €1–€1,000**。预设与自由金额都由服务端计算金额/币种/积分快照，并统一以 `price_data` 创建 Checkout；不需要 Stripe Product / Price，也没有 `STRIPE_PRICE_*` 配置。
- 为兼容既有调用，服务端仍接受 `{package_key}` 或 `{amount_minor}` 二选一；两种请求最终走同一 inline-price、订单快照、webhook 校验与唯一入账写门。
- 公网 API origin 与 `/api/*` 反向代理归属待确认；不能把 Docker 内部 `API_PUBLIC_URL` 当 Stripe 公网地址。
- live key 与 live webhook secret 均未提供，本批验收不冒充真实收款上线。

## 1. 范围纪律

本批交付：

1. 金额预设与自由金额竖切：实际 Checkout → CLI webhook → 钱包入账。
2. 一张 `payment_orders` 表与 migration；不新建独立 webhook event 表。
3. packages / checkout-sessions / order read / stripe webhook 四个接口。
4. SettingsDialog 积分购买面、CreditsPill 入口与支付返回确认。
5. 公网 test 部署交接材料与完整安全/幂等验收。

本批明确不做：订阅与续费、Customer Portal、自动退款/拒付、延迟到账支付方式、VAT/发票定制、Landing 订阅卡接线、独立支付容器、生产 Stripe CLI。不得为扩大范围修改现有制作授权、hold/capture/release 或 prompt。

## 2. 施工序列

### P0 — 外部配置与金额预设

1. 在服务端固定预设 `package_key`、EUR 金额与积分数；预设只是输入快捷方式，不在 Stripe Dashboard 创建 Product / Price。
2. 本地安装 Stripe CLI，运行 `./scripts/stripe_webhook_dev.sh`：脚本校验公司 test API key 与 webhook signing secret；缺少 signing secret 时生成并写入 `.env`，已有 listener 只确认，未运行才启动，避免重复转发；不需要个人 `stripe login`。
3. 更新 `.env.example`、`apps/api/app/config.py`、`apps/api/pyproject.toml` 与 `docker-compose.yml`：支付配置只含 API key 与 webhook secret，依赖按 PAYMENTS §1；真实值只进本地/部署 secret store，API 容器以外不注入支付 secret。
4. 在服务端建立 `PACKAGE_REGISTRY`，packages 响应返回全部 registry 预设与 custom policy，不按环境或 Stripe Price 配置隐藏。

完成证据：后端能使用公司 test key 创建一张金额与积分均由服务端决定的 inline-price Checkout Session；此时仍不得宣称已自动入账。

### P1 — 订单模型与 Checkout 接口

1. 按 PAYMENTS §4 在 `apps/api/app/models/tables.py` 增加 `PaymentOrder`，创建 Alembic migration；同批登记 `MODULE_ARCHITECTURE.md §4`。
2. 新建 `apps/api/app/platform/payments.py` 与 `payment_routes.py`，在 `app/main.py` 挂 `/api/v1/payments`；路由命名与 wire schema 全栈统一。
3. 实现 `GET /packages`、`POST /checkout-sessions`、`GET /orders/{order_id}`。packages 同时下发金额预设与 custom policy；当前前端 Checkout body 恒为 `{amount_minor}`，服务端兼容 `{package_key}` 或 `{amount_minor}` 二选一，订单 owner 校验不能仅靠隐藏 URL。
4. Checkout 创建严格按 PAYMENTS §5：两种请求都在服务端解析金额、币种与积分，自由金额校验范围并计算积分，随后统一使用 `price_data`。先持久 pending 订单，以 order ID 派生 Stripe idempotency key；显式 `mode=payment` + `allowed_payment_method_types=["card"]`，写入用户与订单关联。
5. success/cancel URL 使用 `WEB_PUBLIC_URL=/settings` 回调形态，不在 success_url 中携带价格、积分或任何“已入账”断言。

完成证据：测试 API 能创建/读取本人订单，他人订单返回 404/既定拒绝形态；返回真实托管 `checkout_url`，数据库订单快照与服务端金额解析一致。

### P2 — Webhook 与唯一入账写门

1. 在 `apps/api/app/platform/billing.py` 增加 `purchase_credits()`，内部复用 `_mutate()`；支付层不得直接改钱包或台账。
2. 实现 `POST /payments/stripe/webhook` 的原始 body 验签、环境/金额/币种/Session/用户/套餐校验与订单 `FOR UPDATE` 状态机，规则只读 PAYMENTS §6。
3. `completed + payment_status=paid` 在同一 DB 事务内完成 purchase、订单 paid、credit_transaction_id 与 paid/credited 时间；提交后才 2xx。
4. `expired` 只关闭 pending 订单；重复事件、已 paid 订单、永久校验失败都不能重复加积分。
5. 日志只记 ID、状态与校验码，不记密钥、完整事件体或银行卡资料。

完成证据：实际 Checkout 测试付款后余额与语义台账正确；同事件重放和不同事件并发都不能双入账，成功 URL 本身零入账。

### P3 — 前端购买与返回确认

1. 新建 `apps/web/src/lib/payments.ts`，统一 API 类型与调用；不在组件里复制价格或积分包常量。
2. 新建 `components/credits/CreditPackagePicker.tsx` 作为唯一金额选择与 Checkout 启动组件；改造 `components/settings/CreditsSection.tsx` 的余额、购买入口与台账层级，不在 Settings 内嵌金额选择或支付表单。
3. 新增轻量 `CreditTopupDialog` 独占金额 input、预设按钮、换算 tooltip、取消与 Checkout 跳转；手动输入取消预设选中，点击预设回填 input 并显示选中态，两种输入都提交 `amount_minor`。改造 `components/credits/CreditsPill.tsx` 区分购买入口与完整台账入口，Settings 余额区购买按钮与 Chat 余额不足灰行均打开该弹窗，支付成功不自动重试 run。
4. 扩展 `routes/_app.settings.tsx` 接收 Checkout return：打开积分 section、轮询订单、按真实 paid 状态刷新 wallet/transactions；success 返回先显示确认中，cancelled 不产生成功反馈。
5. 新文案同步 `en.ts` / `zh.ts`；复用现有 Card/Button/i18n/token，不新增 Stripe.js 或银行卡表单。

完成证据：从 CreditsPill 或 Chat 余额不足灰行进入购买、付款返回、确认中、paid、超时 pending、取消和硬刷新均有诚实状态；界面永不把浏览器返回当作到账，支付成功不自动重试 run。

### P4 — 文档、部署交接与 live 前置

1. 更新 `API.md`、`BILLING.md`、`MODULE_ARCHITECTURE.md` 与本任务剩余欠账；长期规则只留 PAYMENTS/BILLING，排期更新 `PROGRESS.md`，不新增会话报告或重复 ADR。
2. 给部署/账号管理者交付：公网 webhook URL、两个 event 类型、两个支付环境变量名、live/test 配置分工、migration 与 API/Web 重建说明。
3. 公网 test 由 Dashboard 创建独立 webhook secret，服务器不安装/运行 CLI；确认反代落到本项目 API 容器。
4. live 另需 live key/webhook、税务与退款政策、监控责任人和真实小额验收，未满足不得标为真实收款 ready；一次性充值不需要 live Price。

## 3. 验收矩阵

### 3.1 真实本地旅程

- 用实际 Checkout Session + Stripe 测试卡完成付款；CLI 转发真实事件，订单 paid、钱包增加精确积分、交易记录显示一条 topup。€10/€20/€50 三个预设与一个非预设自由金额都要分别走通；统一 `price_data` 改动后，既有 €10 旅程也需复跑，自由金额到账积分必须等于服务端按 policy 计算的快照。
- 手动输入后所有预设取消选中；点击预设回填 input 并显示选中态；空值、超两位小数、越界金额不能启动 Checkout。
- 入账后发起一个现有 Run，充值积分可正常 hold/capture/release；本批无制作链扣费回归。
- 取消付款、未支付返回、过期 Session 均零 purchase。
- 浏览器比 webhook 先返回时先确认中，最终 paid；轮询超时与硬刷新仍可恢复真实状态。

### 3.2 资金与并发

- 同一 webhook 重放至少两次只入一次；同一订单两个不同 completed 投递并发也只入一次。
- paid 后收到 expired 不改变订单或余额；pending 收到 unpaid completed 不入账。
- webhook 提交前模拟 DB 故障时返回 500，Stripe 重试后可恢复且仍只入一次。
- 伪造签名、test/live 环境不符、金额/币种不符、Session/订单/用户不匹配均零入账。
- 重复点击/请求产生的未支付订单不造成收款；同一内部订单不能创建两个 Checkout Session。

### 3.3 权限、前端与部署

- 用户只能创建本人订单、读取本人订单；他人 order ID 不泄漏订单内容。
- 页面显示服务端 registry 的全部预设与 custom policy，前端改价/改 credits 参数无效。
- en/zh、双主题、窄屏与 CreditsPill/Settings 两入口走查通过；无额外支付 Dialog 或前端 secret。
- 公网 test webhook 不经过 JWT 登录墙但必须验签；反代保留原始 body，Docker 内部与公网 URL 不混淆。

## 4. 验证纪律与当前欠账

- 纯函数覆盖只放在金额解析、事件映射与状态机纯层；真实事务、并发、权限和 Stripe 签名链必须走真实 DB/API/Checkout 验收，不能用 mock 绿代替。
- 本批不改 prompt，不新增 LLM 断言或付费模型探针。部署前检查按仓库现行仪式链执行，web 纯测试/类型检查按改动面补齐。
- 当前支付代码、migration、纯校验测试和文档已落地；migration 已由 dev 执行。既有 €10 订单已完成本地真实 Checkout 测试付款，webhook 验签后将订单置为 `paid`，写入恰好一条 10,000 积分 purchase 台账并刷新 UI；统一 inline-price 改动后的真实 Checkout/webhook、€20/€50、自由金额、重放、并发、取消/过期、伪造签名、权限、pytest、web 类型检查/测试、公网部署与 live 验收均**未运行**。
- 本机 Stripe CLI 与本地 webhook secret 已配置，listener 已进入 Ready。剩余外部待办为公网 API origin/反代与 Dashboard 公网 endpoint；一次性充值不再需要创建或配置 Stripe Product / Price。
- 完成后长期约束回 PAYMENTS/BILLING，未完成验收保留在本任务；不把过程日志、密钥或历史报告写入 docs。
