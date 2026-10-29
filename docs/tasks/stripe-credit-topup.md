# Stripe 一次性积分充值——施工合同

> Status: ACTIVE（2026-10-29）。首批订单、Checkout、webhook、purchase 与前端购买面已落码；migration、测试套件、真实 Stripe 联调和公网部署未运行。长期架构与字段/API 合同归 `docs/PAYMENTS.md`，积分语义归 `BILLING.md`；本文件只载首批施工范围、依赖与验收。

## 0. 目标与当前事实

用一个真实公司 Stripe test 账号跑通并产品化：

```text
选择积分包 → Stripe Checkout 测试付款 → webhook 验签
→ payment_orders paid + purchase 台账同事务提交
→ SettingsDialog 显示真实充值结果与钱包余额
```

当前事实与外部输入：

- 已有公司 Stripe **test API secret key**；它不是 webhook secret，也不具备 live 收款语义。
- 本地 webhook secret 由 Stripe CLI 生成；公网 secret 由 Dashboard endpoint 生成，二者分开配置。
- 现有钱包、台账、`_mutate()` 幂等写门与 purchase → topup 读投影可复用；支付路由、订单表和购买 UI 尚未实现。
- 首档已确定为 test `starter = €10 / 10,000 积分`，代码 registry 已固定该测试快照；公司 test Product/Price 已创建并写入本地配置，不代表 live 定价。
- 公网 API origin 与 `/api/*` 反向代理归属待确认；不能把 Docker 内部 `API_PUBLIC_URL` 当 Stripe 公网地址。
- live key、live Price、live webhook secret 均未提供，本批验收不冒充真实收款上线。

## 1. 范围纪律

本批交付：

1. 单档竖切：实际 Checkout → CLI webhook → 钱包入账。
2. 一张 `payment_orders` 表与 migration；不新建独立 webhook event 表。
3. packages / checkout-sessions / order read / stripe webhook 四个接口。
4. SettingsDialog 积分购买面、CreditsPill 入口与支付返回确认。
5. 公网 test 部署交接材料与完整安全/幂等验收。

本批明确不做：订阅与续费、Customer Portal、自动退款/拒付、延迟到账支付方式、VAT/发票定制、Landing 订阅卡接线、独立支付容器、生产 Stripe CLI。不得为扩大范围修改现有制作授权、hold/capture/release 或 prompt。

## 2. 施工序列

### P0 — 外部配置与单档套餐

1. 确认首个 `package_key`、EUR 金额、积分数，并在公司 Stripe test mode 创建一次性 Product / Price。
2. 本地安装 Stripe CLI，运行 `./scripts/stripe_webhook_dev.sh`：脚本校验公司 test 配置；缺少 signing secret 时生成并写入 `.env`，已有 listener 只确认，未运行才启动，避免重复转发；不需要个人 `stripe login`。
3. 更新 `.env.example`、`apps/api/app/config.py`、`apps/api/pyproject.toml` 与 `docker-compose.yml`：配置项与依赖按 PAYMENTS §1；真实值只进本地/部署 secret store，API 容器以外不注入支付 secret。
4. 在服务端建立 `PACKAGE_REGISTRY`，未配置 Price 的套餐不得出现在 packages 响应。

完成证据：后端能使用公司 test key 创建一张受控 Checkout Session，且 registry/Price 金额一致；此时仍不得宣称已自动入账。

### P1 — 订单模型与 Checkout 接口

1. 按 PAYMENTS §4 在 `apps/api/app/models/tables.py` 增加 `PaymentOrder`，创建 Alembic migration；同批登记 `MODULE_ARCHITECTURE.md §4`。
2. 新建 `apps/api/app/platform/payments.py` 与 `payment_routes.py`，在 `app/main.py` 挂 `/api/v1/payments`；路由命名与 wire schema 全栈统一。
3. 实现 `GET /packages`、`POST /checkout-sessions`、`GET /orders/{order_id}`。订单 owner 校验不能仅靠隐藏 URL。
4. Checkout 创建严格按 PAYMENTS §5：先读取并核对 Stripe Price，再持久 pending 订单，以 order ID 派生 Stripe idempotency key；显式 `mode=payment` + `card`，写入用户与订单关联。
5. success/cancel URL 使用 `WEB_PUBLIC_URL=/settings` 回调形态，不在 success_url 中携带价格、积分或任何“已入账”断言。

完成证据：测试 API 能创建/读取本人订单，他人订单返回 404/既定拒绝形态；返回真实托管 `checkout_url`，数据库订单快照与 registry 一致。

### P2 — Webhook 与唯一入账写门

1. 在 `apps/api/app/platform/billing.py` 增加 `purchase_credits()`，内部复用 `_mutate()`；支付层不得直接改钱包或台账。
2. 实现 `POST /payments/stripe/webhook` 的原始 body 验签、环境/金额/币种/Session/用户/套餐校验与订单 `FOR UPDATE` 状态机，规则只读 PAYMENTS §6。
3. `completed + payment_status=paid` 在同一 DB 事务内完成 purchase、订单 paid、credit_transaction_id 与 paid/credited 时间；提交后才 2xx。
4. `expired` 只关闭 pending 订单；重复事件、已 paid 订单、永久校验失败都不能重复加积分。
5. 日志只记 ID、状态与校验码，不记密钥、完整事件体或银行卡资料。

完成证据：实际 Checkout 测试付款后余额与语义台账正确；同事件重放和不同事件并发都不能双入账，成功 URL 本身零入账。

### P3 — 前端购买与返回确认

1. 新建 `apps/web/src/lib/payments.ts`，统一 API 类型与调用；不在组件里复制价格或积分包常量。
2. 改造 `components/settings/CreditsSection.tsx`：余额/台账保持现状，接入服务端积分包、购买 loading 与整页 Checkout 跳转。
3. 改造 `components/credits/CreditsPill.tsx`：新增打开积分 section 的购买入口，不复制套餐选择面。
4. 扩展 `routes/_app.settings.tsx` 接收 Checkout return：打开积分 section、轮询订单、按真实 paid 状态刷新 wallet/transactions；success 返回先显示确认中，cancelled 不产生成功反馈。
5. 新文案同步 `en.ts` / `zh.ts`；复用现有 Card/Button/i18n/token，不新增 Stripe.js 或银行卡表单。

完成证据：从 CreditsPill 进入购买、付款返回、确认中、paid、超时 pending、取消和硬刷新均有诚实状态；界面永不把浏览器返回当作到账。

### P4 — 文档、部署交接与 live 前置

1. 更新 `API.md`、`BILLING.md`、`MODULE_ARCHITECTURE.md` 与本任务剩余欠账；长期规则只留 PAYMENTS/BILLING，排期更新 `PROGRESS.md`，不新增会话报告或重复 ADR。
2. 给部署/账号管理者交付：公网 webhook URL、两个 event 类型、环境变量名、live/test 配置分工、migration 与 API/Web 重建说明。
3. 公网 test 由 Dashboard 创建独立 webhook secret，服务器不安装/运行 CLI；确认反代落到本项目 API 容器。
4. live 另需 live key/Price/webhook、税务与退款政策、监控责任人和真实小额验收，未满足不得标为真实收款 ready。

## 3. 验收矩阵

### 3.1 真实本地旅程

- 用一个实际 Checkout Session + Stripe 测试卡完成付款；CLI 转发真实事件，订单 paid、钱包增加精确积分、交易记录显示一条 topup。
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
- 多档套餐只显示服务端 active 项，前端改价/改 credits 参数无效。
- en/zh、双主题、窄屏与 CreditsPill/Settings 两入口走查通过；无额外支付 Dialog 或前端 secret。
- 公网 test webhook 不经过 JWT 登录墙但必须验签；反代保留原始 body，Docker 内部与公网 URL 不混淆。

## 4. 验证纪律与当前欠账

- 纯函数覆盖只放在套餐裁决、事件映射与状态机纯层；真实事务、并发、权限和 Stripe 签名链必须走真实 DB/API/Checkout 验收，不能用 mock 绿代替。
- 本批不改 prompt，不新增 LLM 断言或付费模型探针。部署前检查按仓库现行仪式链执行，web 纯测试/类型检查按改动面补齐。
- 当前支付代码、migration、纯校验测试和文档已落地；migration 执行、pytest、web 类型检查/测试、真实 Stripe 联调、公网部署与 live 验收均**未运行**。
- 首档产品语义已确定；本机 Stripe CLI 已安装，公司 test Product/Price 与本地 webhook secret 已配置，CLI listener 已进入 Ready。外部待办转为真实付款验收、公网 API origin/反代与 Dashboard 公网 endpoint。
- 完成后长期约束回 PAYMENTS/BILLING，未完成验收保留在本任务；不把过程日志、密钥或历史报告写入 docs。
