# BILLING — 积分与计费架构

> Status: 活跃（2026-09-05 建，ADR-055 同批落档；积分层施工 = PROGRESS W7 积分批 09-07~09-11；支付 / 套餐经济 = W11）
> 本文是积分 / 钱包 / 计费架构的**唯一事实源**：概念、表、扣费时序、比例参数、负余额语义、API、分期。排期只引用 PROGRESS；参数的当前生效值以 `app/platform/configs.py` 注册表为准（本文只写默认）。

## 1. 概念层（三个词，两层货币）

```
        provider cost (USD)                user price (credits)
  ┌─────────────────────────┐   单一换算点   ┌──────────────────────────┐
  │ PRICING × 量 = $         │ ──────────► │ credit = 用户面唯一货币     │
  │ 对账 / 采购 / 偏差回归用   │ ×消耗比例    │ wallet = 余额 + 够不够花    │
  │ 永不直接上 UI            │             │ ledger = 余额变动唯一事实源  │
  └─────────────────────────┘             └──────────────────────────┘
                                                        ▲
                                  W11 payment adapter ──┘ 只是一种 grant 写入者
                                  （钱→积分换算发生在适配器边界，台账不认识"钱"）
```

- **credit（积分）**：用户面唯一计价单位。估价、扣费、余额、配方卡估价贴、任务书总价全部同一单位。en `credits` / zh `积分`。
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
    ref             = Column(JSONB)       # {"run_id":…} / {"step_id":…} / {"source":"signup"} / {"payment_event":…}
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
- **幂等键是一等列**：worker 重启、step 重试、支付 webhook 重放，全靠 `idempotency_key` 唯一约束去重，不写防御代码。
- **`balance_after` 链**：台账任意行可独立校验，对账 SQL 一条查出漂移。
- kind 的 `purchase` 座位本期留空——W11 支付只新增枚举值和适配器，台账结构零改动。

## 3. 资金流四个时刻（hold → capture → release）

```
注册/首登           create_run 出生地            execute_step 尾段（每 step）       run 终态
    │                     │                             │                        │
 grant(开户赠额)      fold estimate → hold(high 端)    成功 → capture(actual)     release(剩余 =
 积分                 余额不足 → 422/灰行             失败/skipped → 不写行       H − Σcaptures)
                     （用户级 shortfall）            ✅ 失败不扣费（§6）
```

1. **授予（grant）**：开户赠额（默认 `wallet.signup_grant=500`），`kind=grant, ref={source:"signup"}`。
2. **预扣（hold）**：`create_run` 折完全图报价后按 **high 端**写 hold（idem `run:{id}:hold`）。余额 < hold → 出生地拒绝（422 `credits.insufficient` + 入流灰行；**用户级"积分不足"与 provider 级 MiniMax 402 严格两词**）。并发 run 各自 hold，`wallets.version` 乐观锁防超扣。
3. **实扣（capture）**：在每个 step 收尾、metering 归并 `cost` 的**同一写入点**（ADR-050 会话纪律不破）按 actual 实扣（idem `step:{id}:capture`）。成功 step 收全量（含内部重试消耗——那是真实成本）；**failed/skipped 不写 capture 行**。provider cost 照记 `workflow_steps.cost` 供对账，不上用户账单。
4. **释放（release）**：run 终态释放剩余（idem `run:{id}:release`）。
5. **购买（purchase，W11）**：payment adapter 收 webhook 确认 → 钱→积分换算（**购买比例**，W11 套餐定价时定，与消耗比例解耦）→ 写 `kind=purchase, idempotency_key=provider_event_id`。订阅周期额度 = `kind=grant, ref={source:"subscription", period:…}`。

### NULL 估价的诚实处理

`estimate=None`（编译期量未知，如 dub fan-out）的 step：hold 按 0 计，结算按 actual 照扣——余额可能因此击穿为负，**允许负余额**（§5），方向是把 NULL 报价节点随校准闭环逐步消灭，不在钱包里打补丁。

## 4. 消耗比例参数 + 公共 config 表

**单一比例参数**：

```python
# configs 表注册项（app/platform/configs.py CONFIG_REGISTRY）
"credits.per_cost_usd" = 300   # 每 $1 provider 成本 = 300 积分（默认）
# 估价侧: estimate(量) × PRICING × 比例 → credits [low, high]
# 实扣侧: cost(量)     × PRICING × 比例 → credits 精确值
```

- 报价 fold 与实扣读同一个值，结构性同源；调消费比例 = 改 config 一行，不用发版。
- **消耗比例 ≠ 购买比例**（钱→积分汇率是 W11 套餐定价的另一个决策，可独立做阶梯加赠）。
- 调参不动历史账：transaction 的积分额落库即事实，USD 成本在 `workflow_steps.cost` 原样保留，两侧各自为真；只有估价贴数字随参数实时变（期望行为）。
- render_seconds 价目当前为 0（自家 infra）——估价贴不含渲染成本，诚实；将来定价只改 PRICING 一行。

**公共 config 表（configs）**——运营参数的统一家（admin 预备），三条防腐纪律：

1. **代码注册表是唯一事实源**：`CONFIG_REGISTRY = {key: (default, type, desc)}`——key 集合 / 默认值 / 类型 / desc 全在代码，表只是覆盖值的载体；启动 reconcile 补插缺失 key（`seed_default_music` 同款机制）。
2. **读取只有一个漏斗**：`get_config(key)` 类型化取值（进程内缓存 + 写失效）；其他模块永不直接查表；未知 key 直接报错。
3. **两分界**：**运营参数（改了不该要发版）→ config 表**；**工程参数（改错会炸部署）→ env `config.py` 不动**（连接串 / 密钥 / DB 保险丝）。

首批住户：`wallet.signup_grant` / `credits.per_cost_usd`。

## 5. 负余额语义

**规则**：允许余额为负并如实显示；负余额用户过不了下一次 hold 判定（余额 < high 端即拒）。

**业界实证（2026-09-05 查证）**：OpenRouter 预付余额可为负（在途请求照扣），随后硬停一切新请求（连免费档），直到回正；Replicate / fal.ai 同款——**在途任务跑完照扣、被拦的永远是新任务**。行业共识 = gate at the start, never mid-flight。中途拦停催款是 AWS 惊喜账单象限，无人采用。

**为什么允许**：① run 不死在半程（会击穿的只有 NULL 估价步骤——我们报价能力的缺口，不该让用户用中断买单）；② 账本诚实（clamp 0 是让自己永远看不见失血点）；③ 负余额发生次数 = NULL 报价节点的消灭进度指标，喂校准闭环；④ 支付未接入期立语义零成本。

**代价与边界**：资损窗口有界（负额不可再起跑，单账户封顶 ≈ 一个 run 的不可报价部分）；文案接住（"上次实际花费超出预估，差额已记账，充值后继续"）；多账号刷负额是注册风控问题，不在此解。

**留档后手**（现在不实装）：W12 监控批加"负余额账户数 / 负总额"告警；若数据证明击穿频繁，给 NULL 步骤注册表级保守上限参与 hold，或运行时超预估 N 倍降级为 checkpoint 询问。

## 6. 失败不扣费语义

- **step 级**：终态 failed / skipped → 该 step 用户 charge = 0（不写 capture 行）；成功 step 收 actual 全量（含其内部瞬时重试的真实消耗）。
- provider 侧成本（`workflow_steps.cost`，含失败尝试）照记不误——那是我们对账与偏差回归的事实，只是不上用户账单。
- estimate 已 hold 的部分随 run 终态 release 自动结清，无人工介入。

## 7. API 与展示面

**新增端点（本期仅两个）**：

```
GET /wallet                                → {balance, held}
GET /wallet/transactions?limit&cursor      → 台账行（W11 计费中心的只读投影前身）
```

**骑既有响应的派生字段（零新端点）**：credits 全部由 `outputs` 序列化层派生（fold × 比例），**不落列**——USD 继续住 `estimate` / `cost`：

- 任务书 dock 载荷 + `estimate_credits: [low, high]`（合计 + 逐任务）；
- `GET /runs/{id}` 每 step + `estimate_credits` / `cost_credits`；
- `GET /recipes` 卡 + `estimate_credits`（配方预设图 fold × 比例 = 配方卡估价贴）。

**错误形态**（API.md §4）：`422 {detail: {code: "credits.insufficient", balance, required}}`。

**前端三面**：dock 生成前总价 / chat 修改单价 / 配方卡估价贴 + 账户控制台 credits 槽 + 余额不足入流灰行。三面同源（同一个 fold、同一份 PRICING、同一个比例），结构性不可能不一致。

## 8. 分期与边界

| 期 | 内容 |
|---|---|
| **W7 积分批（09-07~09-11）** | 三表 + migration + configs 注册表/reconcile + 开户 grant + hold/capture/release 真扣费 + 出生地 shortfall 判定 + 三面展示 + 灰行 + `/wallet` 端点。**积分此时就是真的**——只是还没有花钱买的入口 |
| **W11 支付批** | `platform/payments.py` 适配器（三方对接 + webhook + 订阅生命周期）→ 只写 ledger；套餐语义（周期额度 vs 充值包、购买比例、档位）那时定，`kind`/`ref` 已留座位；用户计费中心 = 台账只读投影 |

**显式不做（W11 座位已留）**：`/payments/*` 端点、webhook 接收器、admin 侧 configs 读写端点、双桶余额（订阅周期额度 vs 充值包——W11 套餐语义定夺时如需分桶，ledger 加列而非改语义）。

## 9. 模块家与缝合点

```
app/platform/
├── configs.py     # CONFIG_REGISTRY + get_config（缓存+写失效）+ set_config + 启动 reconcile
├── billing.py     # 钱包服务：get_or_create_wallet（lazy 开户+grant）/ credits_for_cost /
│                  #   check_hold / hold_run / capture_step / release_run / balance
└── routes.py      # /wallet 路由（W11 加计费中心投影）
# W11: platform/payments.py —— 支付适配器边界（webhook → purchase 行）
```

- 三表进 `models/tables.py`（User 先例）；表归属 = 平台层（MODULE_ARCH §4 已登记）。
- **缝合点**（orchestrator 三处，跨模块调平台服务 = Distribution `_transition` 调 `create_notification` 同款缝）：`create_run` 折完报价 → `hold_run`；`execute_step` 尾段（metering 归并同点）→ 成功分支 `capture_step`；`maybe_finalize_run` → `release_run`。
- `metering.py` 不动：它管"量"（provider 账），billing 管"钱"（用户账），一个 fold 两处消费。
- 启动自检链加 configs reconcile（`main.py`，`seed_default_music` 同款机制）。

## 10. 验收口径

事前有预估（任务书 dock 总价 + 配方卡估价贴）、事后有明细（`GET /wallet/transactions` 逐笔 + run 逐步 `cost_credits`）、失败不扣费（failed/skipped 零 capture）、余额不足出生地拦截（422 + 灰行，用户级两词）、调比例参数三面同动。
