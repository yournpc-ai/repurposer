# 积分系统收口 + 确认教义默认值翻转——施工合同（ADR-117）

> 目标：确认收敛为两种（执行确认 / 费用确认），默认全 auto——方案呈现即开工，扣费无感；会话层 token 计量落地（用户免费）；context 预算管理纯后端；确认偏好从 composer 退市进 SettingsDialog。
>
> 本简报只承载现行规格。竞品取证（Pexo / ElevenLabs / Flora 截图分析）与三轮讨论过程在 git 与会话历史；UI 形态原型 = `scratch/credits-settings-proposal.html`（v2，三画板）。

## 决策台账（已拍板，不再议）

| # | 决策 | 形态 |
|---|---|---|
| D1 | 确认只有两种：**执行确认**（调用 tool 前是否询问）与**费用确认**（消耗积分前是否询问）；其他类型一律不问 | 两个设置键，默认全 `auto` |
| D2 | 理解性提问（ask_user 问受众/目的，ADR-116）**不是许可请求**，不在「不询问」射程内 | 适用范围明文 |
| D3 | 会话层 LLM token **计量但不收费**：新表 `conversation_usage` 每回合一行（COGS 台账），用户面免费 | 纯内部 |
| D4 | context 管理 = 后端预算 + 滑动窗口；**零 UI**（前端将来需要再加面） | 纯后端 |
| D5 | 展示主轴 = 积分（余额数字），百分比永不做主轴（估价四面同源律：% 的分母在混合钱包下无意义）；ring 类可视化只是将来的 garnish | BILLING §7 |
| D6 | 内部守卫线：方案 fold high 端 > `billing.always_confirm_above`（默认 5000）**或**含 NULL 不可报价节点 → 任何设置下恒带价问一次 | ops 参数，不是用户设置 |
| D7 | 旧 `confirm_strategy` 三档弃读连根（从未产生过行为，零迁移负担）；`billing.confirm_large_threshold` 从注册表删除 | 死亡清单 |

## 目标形态

**auto + auto（默认）**：用户消息 → agent 规划 → 方案呈现（dock echo + 草稿图 + 任务列表，呈现义务不变）→ **同回合 start_run** → StatusLine 相位叙事接管。Start pill 不出现；估价四面照常显示；扣费经既有 hold→capture→release，CreditsPill 数字自然变动。

**任一档 ask**：方案 dock 后等确认拍（现行行为）。执行=ask → Start 不带价；费用=ask → Start 带价（`开始 · 约 N 积分`）；两者可独立组合。

**守卫线触发**（任何设置）：fold high > 守卫线 或 含 NULL 节点 → start_run 工具结果返回结构化阻断 `{code:"start.needs_confirm", reason:"above_guardrail"|"unquotable", quote_high}` → 模型转为呈现带价确认（Start pill 现身，NULL 族标「估价随运行确定」）→ 用户确认后走既有 Start 道。

**设置座位**：SettingsDialog 新增两个 section——「助手」（权限卡：执行确认 / 消耗积分两行右对齐 Select：自动/询问；footnote 诚实线 = 估价恒显 + 守卫线声明）与「积分」（概览卡：余额/冻结中>0 时/免费试用版零 CTA 占位；最近变动卡：语义台账行 + 查看全部记录）。形态原型 = 上述 HTML 画板 A/B/C。

## B1 — 设置两档 + 控件退市

**存储**：`users.settings` JSONB 新增两键（读容忍，缺席 = 默认）：

```python
confirm_execution: "auto" | "ask"   # 默认 auto
confirm_credits:   "auto" | "ask"   # 默认 auto
```

- `app/platform/user_settings.py`：删 `read_confirm_strategy`/`merge_confirm_strategy`，写 `read_confirmation_prefs(settings) -> (execution, credits)` 与 `merge_confirmation_pref(settings, key, value)`；非法值读容忍回 auto。
- `app/platform/routes.py` `/auth/settings`：GET 返回两键；PUT 接受任一/双全（Literal 校验）。旧字段 `confirm_strategy` / `confirm_large_threshold` 从响应与请求模型删除。
- `app/platform/configs.py`：注册表删 `billing.confirm_large_threshold`，增 `billing.always_confirm_above`（int，默认 5000，desc = 守卫线语义 + 「不是用户设置」）。启动 reconcile 只补不删——旧 key 的 DB 残留行随批附一条清理 SQL（简报末尾）。

**前端退市**：

| 死什么 | 位置 |
|---|---|
| `CostConfirmControl` 整文件 | `apps/web/src/components/composer/CostConfirmControl.tsx` |
| 两处挂载 + 注释 | home composer + `ChatDock.tsx:3936` 附近 |
| i18n 键族 `composer.confirmStrategy.*` | `en.ts` / `zh.ts`（en 先写 zh 镜像） |
| localStorage `repurposer-confirm-strategy` | 弃读即死，无清理代码 |

**SettingsDialog 两个新 section**：`SettingsSectionId` 加 `"assistant" | "credits"`；左导航注释「等第二个 section」兑现。行解剖照 `ChannelsSection`（Card + row + h-9 中心线）；Select 用 `ui/select`；i18n 键 `settings.assistant.*` / `settings.credits.*`（en 源 zh 镜像）。积分区数据复用 `/wallet` + `/wallet/transactions` 既有投影（与 CreditsPill/account-console 三面同源，零新端点）。

**验收**：pure 测试覆盖 read/merge 读容忍（非法值/缺席/部分键）；tsc 绿；设置改动后同会话生效（module 缓存照 `useConfirmStrategy` 旧模式重写为新 hook，或并入 auth-context——施工时择一并在简报补记）。

## B2 — auto 开工道（教义默认值翻转，半径最大批）

**服务端强制**（`app/pipeline/lifecycle.py:evaluate_start_gate`）：

```python
needs_confirm = (
    execution == "ask"
    or (credits == "ask" and quote_high > 0)
    or quote_high > always_confirm_above      # D6 守卫线
    or has_null_estimate                      # NULL 族恒问
)
```

- gate 读两档 + 守卫线 config + 报价；`quote_high=0` 的免费方案在费用=ask 档不触发。
- start_run 工具路径（`_create_run_from_tasks`，service.py:429）在阻断时不抛 422 给前端，而是**回工具结果** `{code:"start.needs_confirm", reason, quote_high}` 让模型转呈现带价 dock；typed 端点路径维持 422 形态。
- 计划呈现载荷（dock payload）增 `requires_confirmation: bool` + `quote_high` + `unquotable`——服务端在呈现时算好，客户端 Start pill 的渲染谓词 = 此旗（**客户端永不自行推导**）；`ChatDock` `confirmActive` 合取此旗。
- Start pill 带价形态：label 插值 `开始 · 约 N 积分` / NULL 族 `开始 · 估价随运行确定`（i18n 双写）。

**scope_classifier 目的地分流**（D4 分类律本身零改动——continuation/expansion/unproven 判定不动）：

- continuation：自治直跑（两档同，现行不动）。
- expansion：ask 档 → dock 等确认（现行）；auto 档 → 呈现（草稿图 + echo）+ 直跑，守卫线照常把关。
- `/generate` 未证重试门（B5 链分类器）：形态不变——create_run 恒要求**已呈现** scope 快照；快照 = 授权记录，`confirmed_via` 增 `"auto"` 值（常驻授权通道），`"explicit"` 为 ask 道。

**prompt 面**（→ prompt_gate 必过）：

- 口头确认律改档条件：ask 档 echo 收尾恒为朴素问句（现行）；auto 档方案呈现后直接说出开工句（ADR-093 起始句言语权不变）并同回合 start_run。
- B3 禁令「propose 同 turn create_run 全路径禁止」改为**档条件**：ask 档维持禁止；auto 档同回合 propose→start_run 是**标准道**。
- 守卫线工具结果的转呈现措辞：模型收到 `start.needs_confirm` 后呈现带价确认，永不静默重试。

**剧本矩阵**：默认档旅程断言从「dock 等确认」翻为「呈现即开工」；ask 档旅程保留既有断言。改造范围逐本在剧本 harness 标注（开工时先盘 S1~S10 哪些座断言确认拍）。

**验收**：`evaluate_start_gate` 模式矩阵 pure 测试（2×2 档 × 守卫线 × NULL × quote=0 边界）；prompt_gate 全探针；剧本矩阵受影响座用户自跑。

## B3 — 会话层计量（纯内部，零用户面）

**新表 `conversation_usage`**（owner = 平台层，MODULE_ARCH §4 登记）：

```python
id                  uuid PK
user_id             FK users.id
project_id          FK projects.id, nullable
prompt_tokens       int
completion_tokens   int
cached_tokens       int, nullable      # provider 返回即记（prefix cache 命中分析）
cost_usd            float              # 写入时 price_tokens 一算定型，不随价目漂移
model               str
created_at
# 索引：(user_id, created_at) / (project_id, created_at)
```

- **绑定机制零新增**：chat 回合入口（routes/service 单一缝）套 `bind_conversation_turn()` contextvar；既有 `record_usage` 咽喉（`minimax.py:434`）自然累积；回合尾把台账折成**一行**（tool loop 多轮迭代聚合为一行，行量可控）。
- 写纪律照 billing 先例：usage 行与回合 assistant 消息同一 commit（adr-050 会话纪律）；计量永不打断生成（record 路径既有 never-break 律继承）。
- **永不上用户账单、永不上 UI**——用途 = COGS 可见性（每用户会话/生产成本比）+ W11 fair-use 配额的数据基础 + B4 预算校准数据源。
- 需求池联动：`agent_calls` 台账（PROGRESS §2 池 P1 行）的**计量半边**由本表落地；取证级 envelope 重建（prompt 快照/哈希/spill）仍在池，不在本批。

**验收**：migration + 纯测试（fold 聚合 / 空回合零行 / never-break）；live 一回合后 SQL 抽查行内容（用户自跑）。

## B4 — context 预算管理（纯后端零 UI）

- **装配预算审计先行**：B3 台账跑起来后，按回合族（router / plan / answer / explore / trigger）读真实 `prompt_tokens` 分布再定阈值；候选默认 `chat.context_budget_tokens = 120000`（ops 参数进 configs，免发版可调）。
- **滑动窗口装配**：消息历史超预算 → 保留近端窗口（现有 `history[-n:]` 散座收编为统一预算谓词）；世界状态（图快照/资产元数据）本就不走消息窗，天然幸存。
- **LLM 滚动摘要 = 缓做项**（池登记）：首版只做窗口折叠，不做摘要生成；「早期内容引用丢失」由 B3 台账观察实际发生率后再评。
- prefix cache 友好装配顺序不动（system+world 前缀稳定，消息追加）。
- **零 UI**：无折叠提示行、无 token 仪表盘（D4）。

**验收**：预算谓词 pure 测试（窗口边界/世界状态幸存）；审计报告入 `scratch/`（不落库数字断言）。

## B5 — 文档收口

- `docs/DECISIONS.md`：ADR-117 落档（本批母法）；ADR-092 收缩为「口头确认律（ask 档）」；ADR-089 §5 停顿定律措辞修订；ADR-088 §1 北极星英文行修订（均已随批落）。
- `docs/BILLING.md`：§4 注册表更替；新增会话层与 context 节；§7 展示面补 Settings 座位与「积分主轴」抉择；§8 W11 挂账更新。
- `docs/PROGRESS.md`：§0.2 登记本批；需求池 `agent_calls` 行标注计量半边落地。
- `CLAUDE.md`：北极星行与口头确认律行同步现行法。

## 验证纪律（部署前仪式链，用户自跑）

1. `cd apps/api && uv run --extra dev python -m pytest tests/ -q`
2. `uv run python scripts/check_gates.py`
3. `uv run python scripts/prompt_gate.py`（B2 触 prompt 面，必跑）
4. `uv run python scripts/chat_scenarios.py`（B2 翻默认档断言，受影响座全绿）
5. Web：`cd apps/web && npm test` + `tsc`

## Prohibited Behaviors

- **永不新增第二意图入口**；auto 道复用既有 `_dock_plan_as_question` / start 机器，不开新路由。
- **守卫线永不是用户设置**——不进 Settings UI、不进 i18n 用户文案（除画板 A footnote 那句诚实声明）。
- **会话计量永不上用户账单与 UI**；token 数字永不上 UI（USD 既有禁令同族）。
- **auto 档下 Start pill 永不渲染**（守卫线触发除外）；客户端永不自行推导「要不要确认」——读服务端 `requires_confirmation` 旗。
- **理解性提问不受本批影响**（ask_user / ADR-116 选项律原样承重）。
- **context 折叠零 UI**（本迭代）；无「已折叠 N 条」日志格。
- **旧 `confirm_strategy` 键永不再读**；不为其写迁移（它从未生效）。
- 打字机律 / 信封权威 / 状态行一座两行 / dock 三形态机：零触碰。
- 手改撤名律 / 展示文案二源律：价格数字的唯一来源 = 服务端 fold，客户端永不自算。

## 遗留校准数（施工中以真实数据定夺，不靠拍脑袋）

| 数 | 候选 | 定夺依据 |
|---|---|---|
| `billing.always_confirm_above` | 5000（=$5） | 真实 fold 报价分布（金句卡 ≈8 / dub 链 ≈2000） |
| `chat.context_budget_tokens` | 120000 | B3 台账的回合族 token 分布 + m3 标准档上限 |

## 清理 SQL（随 B1 执行）

```sql
DELETE FROM configs WHERE key = 'billing.confirm_large_threshold';
```

## 避让清单（新会话开工必读）

- 开工先读：`docs/BILLING.md`、`docs/CHAT_ARCHITECTURE.md`、`DECISIONS.md` 的 ADR-117/092/089§5/088§1、`docs/UI_GUIDELINES.md`（SettingsDialog 解剖）、本简报。
- `apps/api/scripts/chat_scenarios.py` 工作树有未提交改动——先问清归属再动。
- 常驻 dev worker 会抢跑手工 run；验证后清数据（fixture 纪律）。
- UI 稿 = `scratch/credits-settings-proposal.html`（v2 三画板）；Settings 行解剖对齐 `ChannelsSection`。
