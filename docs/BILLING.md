# BILLING — 积分与计费架构

> Status: 当前规范（2026-10-25）。积分、钱包与 hold/capture/release 是当前能力；支付、套餐与订阅经济仍按 `PROGRESS.md` 挂起。
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
                                  W11 payment adapter ──┘ 只是一种 grant 写入者
                                  （钱→积分换算发生在适配器边界，台账不认识"钱"）
```

- **credit（积分）**：用户面唯一计价单位。估价、扣费、余额、配方卡估价贴、计划总价全部同一单位。en `credits` / zh `积分`。
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
 积分                 余额不足 → 422/灰行             失败/skipped → 不写行       H − Σrelease)
                     （用户级 shortfall）            ✅ 失败不扣费（§6）
```

1. **授予（grant）**：开户赠额（默认 `wallet.signup_grant=100000`），`kind=grant, ref={source:"signup"}`。
2. **预扣（hold）**：`create_run` 折完全图报价后按 **high 端**写 hold（idem `run:{id}:hold`）。余额 < hold → 出生地拒绝（422 `credits.insufficient` + 入流灰行；**用户级"积分不足"与 provider 级 MiniMax 402 严格两词**）。并发 run 各自 hold，`wallets.version` 乐观锁防超扣。
3. **实扣（capture）**：先锁钱包，同一事务释放实际费用覆盖的预扣（`release`，idem `step:{id}:capture:hold-release`，增量 capture 使用对应增量键），再记实际扣费。两条台账同事务提交，余额只减少超出预扣的部分，禁止 hold 和 capture 重复扣款。在每个 step 收尾、metering 归并 `cost` 的**同一写入点**（ADR-050 会话纪律不破）按 actual 实扣（idem `step:{id}:capture`）。成功 step 收全量（含内部重试消耗——那是真实成本）；**failed/skipped 不写 capture 行**。provider cost 照记 `workflow_steps.cost` 供对账，不上用户账单。
4. **释放（release）**：run 终态释放 `hold − Σrelease` 的剩余预扣（idem `run:{id}:release`）。终态恒等式：`Σrelease = hold`，净支出仅为 `Σcapture`；无预扣的实际扣费合法。历史重复扣款由 `scripts/repair_credit_reservations.py` 审计，默认只读，`--apply` 追加幂等释放行，不改旧记录。
5. **购买（purchase，W11）**：payment adapter 收 webhook 确认 → 钱→积分换算（**购买比例**，W11 套餐定价时定，与消耗比例解耦）→ 写 `kind=purchase, idempotency_key=provider_event_id`。订阅周期额度 = `kind=grant, ref={source:"subscription", period:…}`。

### NULL 估价的诚实处理

`estimate=None`（编译期量未知，如 runtime render fanout，或未出生 clips 上的 dub/translate）的 step：hold 按 0 计，结算按 actual 照扣——余额可能因此击穿为负，**允许负余额**（§5）。**含 NULL 不可报价族的方案在任何权限档都必须先带价说明并取得一次费用确认**；0 hold 不是免确认或免费承诺。这是当前报价能力边界，不是对“编译期精确总价”的隐性承诺；方向是把 NULL 报价节点随校准闭环逐步消灭，不在钱包里打补丁。

## 4. 消耗比例参数 + 公共 config 表

**单一比例参数**：

```python
# configs 表注册项（app/platform/configs.py CONFIG_REGISTRY）
"credits.per_cost_usd" = 1000   # 每 $1 provider 成本 = 1000 积分（默认）
# 估价侧: estimate(量) × PRICING × 比例 → credits [low, high]
# 实扣侧: cost(量)     × PRICING × 比例 → credits 精确值
```

- 报价 fold 与实扣读同一个值，结构性同源；调消费比例 = 改 config 一行，不用发版。
- **消耗比例 ≠ 购买比例**（钱→积分汇率是 W11 套餐定价的另一个决策，可独立做阶梯加赠）。
- 调参不改已经写入的 ledger 积分额；USD 成本仍保留在 `workflow_steps.cost`。**读面不是全部冻结**：历史 step 的 `cost_credits` 也由持久 USD × 当前比例重新序列化，估价贴同样随参数变化；只有已写 transaction 金额与幂等事实不随比例重写。
- render_seconds 价目当前为 0（自家 infra）——估价贴不含渲染成本，诚实；将来定价只改 PRICING 一行。
- **voice_clones 报价幂等**：声纹克隆按「每个新声一次」计费（provider 规则——首次 T2A 使用触发），一条链多站 dub 逐节点各自声明 would-be clone 时 fold 只收一次（钳制在 `fold_estimates` 一座，报价=fold 的唯一缝合点；与计量同律——`record_media_usage` 只在 voice_id 缺失时记账）——估价 ≡ 计量，多语言配音链的克隆费如实计一次。
- **配方卡估价贴的可报价域**：translate / dub / reframe 挂在 materialize_source 上的链，live 计划诚实 NULL（编译期片段未生——「估价随运行」），配方卡贴纸按 RECIPE_QUOTE_FACTS 声明的典型素材可报价（`quote_scope="recipe"` 单座豁免，传进 `compile_recipe_quote` 的 ctx）。

**公共 config 表（configs）**——运营参数的统一家（admin 预备），三条防腐纪律：

1. **代码注册表是唯一事实源**：`CONFIG_REGISTRY = {key: (default, type, desc)}`——key 集合 / 默认值 / 类型 / desc 全在代码，表只是覆盖值的载体；启动 reconcile 补插缺失 key（`seed_default_music` 同款机制）。
2. **读取只有一个漏斗**：`get_config(key)` 类型化取值（进程内缓存 + 写失效）；其他模块永不直接查表；未知 key 直接报错。
3. **两分界**：**运营参数（改了不该要发版）→ config 表**；**工程参数（改错会炸部署）→ env `config.py` 不动**（连接串 / 密钥 / DB 保险丝）。

首批住户：`wallet.signup_grant` / `credits.per_cost_usd` / `billing.always_confirm_above`（确认守卫线，ADR-117 D6——方案 fold high 端越线或含 NULL 节点时任何权限档恒带价问一次；ops 参数，永不是用户设置）/ `chat.context_budget_tokens`（装配滑动窗口预算，ADR-117 D4——消息历史超预算折叠近端窗口；ops 参数，永不上 UI）/ `film.usd_per_second`（MG film-spec 成片秒费率，ADR-119 D3——自家 infra 首个带菜单价的 SKU：launch_film 报价 = storyboard 秒数典型值 × 费率 + 编排 tokens 平项，实扣 = 分配后真实秒数经 `record_media_usage` 入 `fixed_cost`；报价与实扣过同一条 `price_units` 价目线（费率同步读 = `peek_config` 预热缓存），clip 族 `render_seconds` 仍是零价计量单位，两不相干）。

## 5. 负余额语义

**规则**：允许余额为负并如实显示；负余额用户过不了下一次 hold 判定（余额 < high 端即拒）。

**业界实证**：OpenRouter 预付余额可为负（在途请求照扣），随后硬停一切新请求（连免费档），直到回正；Replicate / fal.ai 同款——**在途任务跑完照扣、被拦的永远是新任务**。行业共识 = gate at the start, never mid-flight。中途拦停催款是 AWS 惊喜账单象限，无人采用。

**为什么允许**：① run 不死在半程（会击穿的只有 NULL 估价步骤——我们报价能力的缺口，不该让用户用中断买单）；② 账本诚实（clamp 0 是让自己永远看不见失血点）；③ 负余额发生次数 = NULL 报价节点的消灭进度指标，喂校准闭环；④ 支付未接入期立语义零成本。

**代价与边界**：资损窗口有界（负额不可再起跑，单账户封顶 ≈ 一个 run 的不可报价部分）；文案接住（"上次实际花费超出预估，差额已记账，充值后继续"）；多账号刷负额是注册风控问题，不在此解。

**留档后手**（现在不实装）：W12 监控批加"负余额账户数 / 负总额"告警；若数据证明击穿频繁，给 NULL 步骤注册表级保守上限参与 hold，或运行时超预估 N 倍降级为 checkpoint 询问。

## 6. 失败不扣费语义

- **step 级**：终态 failed / skipped → 该 step 用户 charge = 0（不写 capture 行）；成功 step 收 actual 全量（含其内部瞬时重试的真实消耗）。
- provider 侧成本（`workflow_steps.cost`，含失败尝试）照记不误——那是我们对账与偏差回归的事实，只是不上用户账单。
- estimate 已 hold 的部分随 run 终态 release 自动结清，无人工介入。

## 6.5 会话层计量与 context 预算（ADR-117 §5）

**会话层 LLM 调用（路由 / 理解 / 规划 / 应答 / 探索 / 触发回合）只计量、不收费。** 对话是产品界面本身——按回合计价 = 出租车计价器焦虑，无一主流 agent 产品这么做；但成本是真实的（m3 $0.30/$1.20 per 1M token，重度话痨项目的会话成本可超生产成本），必须入账可见。

- **`conversation_usage` 表**（owner = 平台层）：每回合一行（user / project / prompt_tokens / completion_tokens / cached_tokens / cost_usd 写入时定型 / model / created_at）。chat 回合入口绑 `bind_conversation_turn()` contextvar，复用 `record_usage` 唯一咽喉（`minimax.py` provider 层），tool loop 多轮迭代聚合为一行；写纪律 = 与回合 assistant 消息同一 commit；计量永不打断生成。
- **永不上用户账单、永不上 UI**。用途三：COGS 可见性（会话/生产成本比）/ W11 fair-use 配额的数据基础 / context 预算校准数据源。
- **context 预算**（纯后端零 UI）：装配超 `chat.context_budget_tokens`（ops 参数）→ 消息历史滑动窗口收编（现有 `history[-n:]` 散座归一预算谓词）；世界状态（图快照 / 资产元数据）不走消息窗，天然幸存。LLM 滚动摘要 = 缓做项（真实溢出率由台账观察后再评）。prefix cache 友好装配顺序不动。
- token 是内部计量单位，credit 是用户面唯一货币——token 数字与 USD 一样永不上 UI。

## 7. API 与展示面

**当前端点**：

```
GET /wallet                                → {balance, held}
GET /wallet/transactions?limit&cursor      → per-run/per-event 语义交易行
```

`/wallet/transactions` 不是裸台账查询：hold/capture/release 在服务端按 run 折叠为一条 spend，grant/refund/positive adjust 归为 grant，purchase 归为 topup。wire 字段为 `id / family / amount / label? / output_types / hint? / project_name? / created_at`；raw `kind / ref / balance_after / idempotency_key` 留在内部。keyset 在原始 append-only ledger 上分页，语义 fold 在每页内进行，跨页 run 显示该页净额。

**跨读面的派生字段**：credits 在各自序列化边界以 fold × 当前比例派生，**不落重复列**；USD 继续住 `estimate` / `cost`。不是只有 `outputs` 一个序列化器：

- 计划 dock：`estimate_credits: {total, per_task}`；
- `GET /runs/{id}`：每 step `estimate_credits [low, high]` / `cost_credits`，由该 read model 派生；
- `GET /recipes`：固定量卡 `estimate_credits [low, high]`；按秒卡改发 `estimate_rate`，不再伪造固定总价；
- graph 草稿节点在 projects read model 中做同样的 fold × live-ratio 投影。

ledger 已写金额不变，历史 step 的 credits 读投影可随比例变化，二者不能混为“调参不动所有历史数字”。

**错误形态**（API.md §4）：`422 {detail: {code: "credits.insufficient", balance, required}}`。

**前端四面 + 两余额读面**（ADR-057）：dock 生成前总价 / chat 修改单价 / 配方卡估价贴 / **节点卡空态估价**（草稿态产物区「运行后生成 · 约 N 积分」，逐节点 fold）+ 账户控制台 credits 槽 + 项目页左下角 **CreditsPill** + 余额不足入流灰行。**生成前估价的家**：dock echo 的真实估价信息、需要确认时的 dock Start pill（服务端 `quote_high` / unquotable 标记）与画布草稿节点逐节点估价共同呈现；重型确认卡和第二总价面不再另建。执行与费用确认控件只住 dock，画布不放计划 Start/Confirm（ADR-070）；确认针对当前受影响节点、scope 与报价，不由客户端自行推导。估价四面同源（同一个 fold、同一份 PRICING、同一个比例），结构性不可能不一致。

**语义账本塌缩**（ADR-057）：hold / release 永不上 UI——CreditsPill popover 的台账投影 = **per-run-event 语义行**（「Post 修订 −3」「初始生成 −42」：一次用户可感知动作 = 一行，hold/capture/release 内部时序折叠进该行净额）；用户面只显**花费 / 赠送 / 充值**三族。裸 kind 列表（`hold`/`capture`/`release` 逐行）是机器视角泄漏，不上 UI。

**展示主轴抉择（ADR-117 同批拍板）**：积分余额是唯一的用户面数字——**百分比永不做主轴**（估价四面同源律：dock 总价 / 修改单价 / 估价贴 / 节点估价全说积分，余额讲 % 则用户无法对账；且 % 的分母在赠额+充值+订阅混合钱包下无意义）。ring 类可视化只是将来订阅落地后的可选 garnish（配额的可视化，不是第二货币）。**SettingsDialog「积分」section** = 余额与台账的全貌座位（概览卡 + 语义行 + 查看全部），与 CreditsPill / 账户控制台三面同源同一投影，零新端点。**确认闸形态**（ADR-117）：默认 auto 档无闸——方案呈现即开工；ask 档与守卫线触发时 Start 钮带价（`开始 · 约 N 积分` / NULL 族「估价随运行确定」），复用既有 pill 零新 chrome。

## 8. 当前边界与支付延期

| 范围 | 当前状态 |
|---|---|
| 积分底座 | 三表、migration、configs reconcile、开户 grant、hold/capture/release、shortfall、钱包与多个估价读面是当前能力 |
| 支付/订阅 | `platform/payments.py`、三方 webhook、订阅生命周期、购买比例与套餐档位仍是 PLANNED；启动时间归 `PROGRESS.md` R1.1 |
| 计费中心扩展 | 当前 Settings/CreditsPill 共用语义交易投影；分桶余额、周期额度、fair-use 配额与 admin configs 写面按后续商业合同实施 |

**支付边界**：未来 `/payments/*` 与 webhook 只经适配器写 ledger；分桶余额若实施，应增加明确字段/语义而非篡改现有交易。三桶方向（Subscription / Purchased / Bonus）、到期顺序、fair-use 和 admin 写面都不是当前已实现能力。auto-spend 的当前法律仍是 ADR-117 默认 auto + 制作意图 + 守卫线，不由支付批另造一套授权。

**孤儿 hold 回收**：run 被删（project 级联，台账 append-only 按设计存活）或永停非终态（WAITING_HUMAN 被弃）时，hold 的解冻走双路闭环：① **删除即退**——project 删除端点同事务对非 RUNNING run 调 `release_run`（RUNNING 在途 run 的捕获量仍在增长，提前退会与后落 capture 对不上账；它归 worker 收官路）；② **收官路台账自结算**——`maybe_finalize_run` 对 run 行已删 / 项目已删的残余调用走 `_release_orphaned_hold`（ledger hold 行自带 owner，remainder 从台账重算，幂等键防双退）；WAITING_HUMAN 被弃由 TTL 过期扫荡（`expire_stale_interrupts`）→ run 收官 → 正常 release 兜住。reconcile 尺子对「被删 run 的未结 hold」保留 ○ known-open 豁免，活 run 未结仍硬判。

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

事前有预估（计划 dock 总价 + 配方卡估价贴）、事后有语义明细（`GET /wallet/transactions` 的 per-run/per-event 行）与逐步成本（`GET /runs/{id}` 的 `cost_credits`）、失败不扣费（failed/skipped 零 capture）、余额不足出生地拦截（422 + 灰行，用户级两词）。调比例时，所有读面重新按同一 live ratio 投影，已写 ledger 不变；不得把语义交易行数与原始 hold/capture/release 行数混为同一验收口径。
