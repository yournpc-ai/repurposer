# BILLING — 积分与计费架构

> Status: 当前规范（2026-10-29）。积分、钱包与 hold/capture/release 是当前能力；Stripe 一次性积分充值首批已落码、真实验收未运行，支付架构归 `PAYMENTS.md`，订阅经济仍按 `PROGRESS.md` 挂起。
> 本文是积分 / 钱包 / 计费架构的**唯一事实源**：概念、表、扣费时序、比例参数、负余额语义、API 与边界。参数的当前生效值以 `app/platform/configs.py` 注册表为准（本文只写默认）。

## 1. 概念层（三个词，两层货币）

```
        provider cost (USD)                user price (credits)
  ┌─────────────────────────┐   单一换算点   ┌──────────────────────────┐
  │ PRICING × 量 = $         │ ──────────► │ credit = 用户面唯一货币     │
  │ 对账 / 采购 / 偏差回归用   │ ×消耗比例    │ wallet = 余额 + 够不够花    │
  │ 永不直接上 UI            │             │ ledger = 余额变动唯一事实源  │
  └─────────────────────────┘             └──────────────────────────┘
                                                        ▲
                                  payment adapter（PAYMENTS）──┘ 只是一种 purchase 写入者
                                  （钱→积分换算发生在适配器边界，台账不认识"钱"）
```

- **credit（积分）**：用户面唯一计价单位。估价、扣费、余额、授权报价全部同一单位。en `credits` / zh `积分`。
- **wallet（钱包）**：`wallets` 一行 = 一个用户的当前余额 + 判定接口。注册首登 lazy 开户。
- **ledger（台账）**：`credit_transactions` 表，**append-only**，一切余额变动的事实源；`wallets.balance` 只是台账的物化缓存。

内部成本层（USD、`minimax.PRICING`）原样保留——报价 fold 与计量账簿继续读它（AGENT_ARCHITECTURE §8 不变）；**USD 永不直接上 UI**，用户只见积分。

## 2. 数据模型（三表，Owner = 平台层）

```python
class Wallet(Base):                       # wallets
    user_id        = PK(FK users.id)
    balance        = Column(BigInteger)   # 当前积分余额（台账物化缓存；允许为负，见 §5）
    version        = Column(Integer)      # 乐观锁，并发扣费防撞
    updated_at

class CreditTransaction(Base):            # credit_transactions — append-only
    id              = PK(uuid)
    user_id         = Column(FK users.id, index=True)
    kind            = Column(String)      # grant | purchase | hold | capture | release | refund | adjust
    amount          = Column(BigInteger)  # 有符号积分（hold/capture 为负）
    balance_after   = Column(BigInteger)  # 写后余额（台账自校验链）
    ref             = Column(JSONB)       # {"export_id":…} / {"media_job_id":…} / {"source":"signup"} / {"payment_event":…}
    idempotency_key = Column(String, unique=True)   # 重试 / 重启 / webhook 重放天然去重
    note            = Column(String)      # 人话注记
    created_at

class Config(Base):                       # configs — 公共运营参数表（§4）
    key         = Column(String, primary_key=True)   # 点号命名空间："credits.per_cost_usd"
    value       = Column(JSONB)
    description = Column(String)
    updated_at
```

设计要点：

- **不往 `users` 加列**——钱包是独立聚合根，首登 lazy 开户 + 开户 grant。
- **幂等键是一等列**：worker 重启、Job 重放、支付 webhook 重放，全靠 `idempotency_key` 唯一约束去重，不写防御代码。
- **`balance_after` 链**：台账任意行可独立校验，对账 SQL 一条查出漂移。
- kind 的 `purchase` 座位在支付实施前留空——支付只新增枚举值和适配器，台账结构零改动。

## 3. 授权、预占与结算

MediaJob 与 ExportJob 先取得有上限的报价。批准绑定原 opening、原生调用、参数与报价。钱包检查余额，任务与该 Job 的预占在同一事务写入。Worker 成功时，释放原预占并在同一事务按已授权金额上限 capture 实际费用；零费用无需写空台账行。已安全取消或失败的任务 capture 为零。供应商结果未知时保留预占、核对身份与回执。运维通过 `apps/api/scripts/reconcile_credits.py` 核对钱包、Job 和台账。

## 4. 消耗比例参数 + 公共 config 表

**单一比例参数**：

```python
# configs 表注册项（app/platform/configs.py CONFIG_REGISTRY）
"credits.per_cost_usd" = 1000   # 每 $1 provider 成本 = 1000 积分（默认）
# 估价侧: estimate(量) × PRICING × 比例 → credits [low, high]
# 实扣侧: cost(量)     × PRICING × 比例 → credits 精确值
```

- 报价 fold 与实扣读同一个值，结构性同源；调消费比例 = 改 config 一行，不用发版。
- **消耗比例 ≠ 购买比例**（钱→积分汇率是积分包定价的另一个决策，可独立做阶梯加赠）。
- 已写入的钱包台账和已授权上限按原数值核对。调参后，新操作读取当期配置。

**公共 config 表（configs）**——运营参数的统一家（admin 预备），三条防腐纪律：

1. **代码注册表是唯一事实源**：`CONFIG_REGISTRY = {key: (default, type, desc)}`——key 集合 / 默认值 / 类型 / desc 全在代码，表只是覆盖值的载体；启动 reconcile 补插缺失 key（`seed_default_music` 同款机制）。
2. **读取只有一个漏斗**：`get_config(key)` 类型化取值（进程内缓存 + 写失效）；其他模块永不直接查表；未知 key 直接报错。
3. **两分界**：**运营参数（改了不该要发版）→ config 表**；**工程参数（改错会炸部署）→ env `config.py` 不动**（连接串 / 密钥 / DB 保险丝）。

首批住户：`wallet.signup_grant` / `credits.per_cost_usd` / `billing.always_confirm_above`（确认守卫线；ops 参数，永不是用户设置）/ `chat.context_budget_tokens`（装配预算）/ `video.usd_per_second`（video-spec 成片秒费率）：ProduceVideo 报价与实际秒数计量共用 `price_units` 的 `video_seconds` 价目线；Clip 的 `render_seconds` 仍是零价计量单位。

## 5. 余额与并发

`check_hold` 检查可用余额，实际预占进行原子余额检查。同一用户可以有多个独立预占，用户之间分别对账。稳定的 Job 幂等键与唯一约束防止重复记账。

## 6. Stop 和删除

导出成功提交和 Stop 争用同一 ExportJob。如果 Stop 先提交，未确认的外部上传须保留凭据和预占。核清后全额 release，capture 为零，无交付。成功先提交则保留合法 Output 和扣款。项目存在未安全终结的 Job、未决台账或外部发帖时，删除返回 409。

## 6.5 会话层计量与 context 预算（ADR-117 §5）

**会话层 LLM 调用（路由 / 理解 / 规划 / 应答 / 探索 / 触发回合）只计量、不收费。** 对话是产品界面本身——按回合计价 = 出租车计价器焦虑，无一主流 agent 产品这么做；但成本是真实的（按当前文本模型的实际 token、缓存与价格表入账），必须入账可见。

- **`conversation_usage` 表**（owner = 平台层）：每回合一行（user / project / prompt_tokens / completion_tokens / cached_tokens / cost_usd 写入时定型 / model / created_at）。chat 回合入口绑 `bind_conversation_turn()` contextvar，复用 `record_usage` 唯一咽喉（`providers/llm` 边界），tool loop 多轮迭代聚合为一行；写纪律 = 与回合 assistant 消息同一 commit；计量永不打断生成。
- 会话计量按真实调用聚合；空回合无调用时零 usage 行，记录失败不能打断回复。取证级 agent_calls envelope 是独立需求，不由 conversation_usage 冒充。真实 tokens/cache/cost/model/project 归属与窗口边界验收仍开放，见验证登记 §4.2。
- **永不上用户账单、永不上 UI**。用途三：COGS 可见性（会话/生产成本比）/ 商业化 fair-use 配额的数据基础 / context 预算校准数据源。
- **context 预算**（纯后端零 UI）：装配超 `chat.context_budget_tokens`（ops 参数）→ 消息历史滑动窗口收编（现有 `history[-n:]` 散座归一预算谓词）；世界状态（图快照 / 资产元数据）不走消息窗，天然幸存。LLM 滚动摘要 = 缓做项（真实溢出率由台账观察后再评）。prefix cache 友好装配顺序不动。
- token 是内部计量单位，credit 是用户面唯一货币——token 数字与 USD 一样永不上 UI。

## 7. API 与展示

Chat 的费用问题使用原消息 ID，approve / decline 由服务端记录。执行消息给出 `media_result.charged_credits` 和 `reserved_credits`。钱包读接口通过 `app/platform/routes.py` 返回余额与语义交易，媒体按 media_job_id、导出按 export_id 归集。支付充值关联原 payment_order_id，积分不能反推支付金额。

## 8. 当前边界与支付分工

| 范围 | 当前状态 |
|---|---|
| 积分底座 | 三表、migration、configs reconcile、开户 grant、hold/capture/release、shortfall、钱包与多个估价读面是当前能力 |
| 支付 | `PAYMENTS.md` 定义 Stripe adapter、公网/本地 webhook、支付订单与 purchase 写门；固定档位本地真实主旅程已验证，自定义金额已落码待真实联调，其余验收见当前支付任务 |
| 订阅 | 订阅生命周期、周期额度与套餐权益仍是 PLANNED；启动时间归 `PROGRESS.md` R1.1 |
| 计费中心扩展 | 当前 Settings/CreditsPill 共用语义交易投影；分桶余额、周期额度、fair-use 配额与 admin configs 写面按后续商业合同实施 |

支付通过既有订单与 webhook 适配器写入 purchase。价格、充值状态与退款规则见 [支付规范](PAYMENTS.md)。

## 9. 执行与核对位置

`app/platform/billing.py` 定义 hold_media、hold_export、settle_media、settle_export 和 settled_job_amounts。原生 Job 各自完成领取、提交与核对。Worker 自动恢复与供应商待核对状态的实际测试见 [6D 记录](tasks/agent-editor-evidence/iteration-6/6d.md)。
