# 积分系统批（credits system）

> 状态：待施工（2026-09-05 立项，用户拍板；ADR-055 同批落档）。
> 排期：PROGRESS W7 积分批 09-07~09-11（5 个工作日）。
> 先读：`docs/BILLING.md`（母文档，唯一事实源）、ADR-055、仓库根 `CLAUDE.md`、`docs/MODULE_ARCHITECTURE.md` §4（表归属）、`docs/NAMING.md` N-51、`docs/API.md` §4（错误形态）。架构语境：AGENT_ARCHITECTURE §8（估价与计量）、ADR-025（计量单边界）、ADR-050（会话纪律）。

## 1. 范围

**积分系统完全先行，支付只留边界。** 本批交付真账本：开户赠额可花、hold/capture/release 真扣、失败不扣费、三面可见；唯一没有的是花钱买的入口（W11）。

母文档没写进本简报的口径一律以 `docs/BILLING.md` 为准；本简报只列工作项、验收与禁令。

## 2. 工作项（按日）

### Day 1（09-07）地基：configs + 三表

- `app/platform/configs.py`：`CONFIG_REGISTRY`（key → default/类型/desc）+ `get_config(key)`（进程内缓存 + 写失效 + 未知 key 报错）+ `set_config`（写路径，admin 预备）+ 启动 reconcile 补插缺失 key（`seed_default_music` 同款机制）。首批住户：`wallet.signup_grant=500` / `credits.per_cost_usd=300`。
- `models/tables.py` + Alembic 一个 migration：`wallets`（user_id PK / balance BigInteger / version Integer / updated_at）、`credit_transactions`（id / user_id / kind String / amount BigInteger / balance_after / ref JSONB / idempotency_key UNIQUE / note / created_at）、`configs`（key PK / value JSONB / description / updated_at）。
- `app/platform/billing.py` 骨架：`get_or_create_wallet`（首登 lazy 开户 + `grant` 行，idem `user:{id}:signup_grant`）挂登录/首登链路。
- `main.py` 启动自检链加 configs reconcile。

### Day 2（09-08）扣费时序：hold → capture → release

- `billing.py` 全动词：`credits_for_cost(usd)`（读 `credits.per_cost_usd`，报价与实扣同源单点）/ `check_hold` / `hold_run`（idem `run:{id}:hold`）/ `capture_step`（idem `step:{id}:capture`）/ `release_run`（idem `run:{id}:release`）/ `balance`。
- orchestrator 三缝合点：`create_run` 折完报价 → `check_hold` + `hold_run`（不足 → 422 `credits.insufficient {balance, required}`）；`execute_step` 尾段（metering 归并 `cost` 的**同一写入点**）→ 成功分支 `capture_step`；`maybe_finalize_run` → `release_run`。
- 幂等：worker 重启 / step 重试 / 重复调用全部经 `idempotency_key` 唯一约束天然去重。
- 并发：`wallets.version` 乐观锁防并发 hold 超扣。

### Day 3（09-09）展示三面

- 序列化层派生（`pipeline/outputs.py`，**不落列**）：`estimate_credits [low, high]` / `cost_credits` = fold × `credits_for_cost`。
- 任务书 dock 载荷 + 合计与逐任务 `estimate_credits`；`GET /runs/{id}` 每 step + `estimate_credits`/`cost_credits`；`GET /recipes` 卡 + `estimate_credits`（配方预设图 fold × 比例）。
- 前端三面：dock 生成前总价 / chat 修改单价 / 配方卡估价贴（"约 X credits"）+ 账户控制台 credits 槽接真余额。i18n en `credits` / zh `积分`。

### Day 4（09-10）失败不扣费 + 余额不足

- 失败不扣费：failed/skipped step 零 capture（Day 2 结构已保证，本日补边界：级联 skipped 下游、TransientNodeError 复位重试的 capture 只记一次）。
- 余额不足：422 `credits.insufficient` 入流灰行（**用户级"积分不足"与 provider 级 MiniMax 402 严格两词**，字典分开）；chat start 路径与 typed Start 双路同语义。
- `GET /wallet` → `{balance, held}`；`GET /wallet/transactions?limit&cursor` → 台账行。
- 负余额：如实显示负数 + 文案（"上次实际花费超出预估，差额已记账，充值后继续"）；负额用户下一次 hold 必拒。

### Day 5（09-11）联调验收

- 全链路联调 + 🎯 验收（口径见 §3）。

## 3. 验收口径（用户视角）

1. **事前有预估**：任务书 dock 显示本次总价区间；配方卡带"约 X credits"。
2. **事后有明细**：`GET /wallet/transactions` 每 run = 1 hold + N capture + 1 release 逐笔可查；run 逐步带 `cost_credits`。
3. **失败不扣费**：人为制造失败 step（缺参确定性失败探针先例），台账零 capture、hold 全额 release。
4. **余额不足出生地拦截**：余额 < high 端 → 422 + 入流灰行；文案与 provider 402 两词。
5. **调参三面同动**：改 `credits.per_cost_usd` → 估价贴 / dock 总价 / 实扣同动，历史 transaction 不变。
6. **负余额如实**：NULL 估价 step 击穿后余额显示负数，下一次起跑被拒。
7. e2e：真管线 run（dub 链一张卡）走通，台账行与 `workflow_steps.cost` 聚合对账一致（× 比例）。

## 4. Prohibited Behaviors

- **禁往 `users` 表加余额列**——钱包是独立聚合根。
- **禁 USD 上 UI**——用户面只有 credits；USD 只住 `estimate`/`cost` 与 PRICING。
- **禁 credits 落列**——`estimate_credits`/`cost_credits` 一律序列化派生（fold × 比例），不落 `workflow_steps` 列。
- **禁绕过幂等键写台账**——任何 `credit_transactions` 写必须带 `idempotency_key`；禁"先查后写"代码级去重。
- **禁 capture 走独立 session/独立事务点**——必须与 metering 归并同一写入点（ADR-050 会话纪律不破）。
- **禁中途拦停催款**——余额击穿放行记账，永不在 run 半程插 checkpoint 要钱。
- **禁 clamp 余额于 0**——负余额如实显示。
- **禁购买比例混入本批**——钱→积分汇率是 W11 套餐定价决策；`credits.per_cost_usd` 只管消耗侧。
- **禁工程参数进 configs 表**——连接串 / 密钥 / DB 保险丝留 env `config.py`；configs 只收运营参数。
- **禁模块直查 configs 表**——一切读取走 `get_config()` 漏斗。
- **禁第二份价目**——任何 USD 价格只读 `minimax.PRICING`；billing 不复制价目表。
- **禁 LLM 报价**——报价 = 节点 estimate fold（N-34 不变）；钱包层不引入任何模型判断。
- **禁提前实装 W11 项**：`/payments/*`、webhook、双桶余额、admin configs 端点。

## 5. 登记义务

- 三表 → MODULE_ARCH §4 表归属（平台层）已随立项登记。
- 新词 → NAMING N-51 已随立项登记。
- `/wallet` 端点 → API.md 随施工同步。
- 剧本测试：估价三断言（S4）在册不动；本批新增断言 = 失败不扣费（失败探针后台账零 capture）与出生地 422 各一条，随 Day 4/5 落。
