# Credits / Permissions——当前合同与剩余验收（ADR-117/139）

> Status: 代码层已落；仪式链、`conversation_usage` 真实行、旧配置清理和 live 授权路径仍待验证。长期规则归 BILLING.md、CHAT_ARCHITECTURE 与 ADR-117/139；本文不保留施工批次。

## 1. 当前契约

- 用户设置只有 `confirm_execution` 与 `confirm_credits`，取值 auto/ask，默认全 auto，唯一座位是 SettingsDialog「助手」。理解性提问不是许可请求，不受这两个开关影响。
- **auto 只免批准拍，不创造制作意图**：付费执行必须从已呈现且已授权的范围开始；无制作意图、纯修改或“先看看”在任何档都安全等待。作品首版 Film 分镜另有强制完整呈现与 review hold。
- ask 档、守卫线 `billing.always_confirm_above`、NULL 不可报价族按现行规则确认；守卫线是 ops 参数，不是用户设置。`quote_high=0` 的免费方案不因 credits=ask 产生费用确认。
- Start 由服务端 `evaluate_start_gate` 统一裁决；dock Start、口头/typed answer 共用同一机器。客户端只读 `requires_confirmation` / `quote_high` / `unquotable`，不自行推导。
- `confirmed_via` 记录真实 auto/explicit 授权通道；快照是 scope 完整性与重试证据，不是伪造的用户手势。scope classifier 仍按 resulting paid scope 判定 continuation/expansion/unproven。
- `conversation_usage` 每回合一行，聚合该回合所有 LLM 调用；计量但不向用户收费、不上 UI，usage 写入永不打断生成。取证级 `agent_calls` envelope 仍是独立需求。
- context 采用后端预算与滑动窗口，世界状态不依赖消息窗；滚动摘要只有在真实溢出证据后才评估。prefix-cache 友好的稳定前缀不被破坏。
- 积分余额是用户面唯一主轴，百分比不是第二货币；Settings「积分」、CreditsPill 与 AccountConsole 使用同一钱包投影。
- 旧 `confirm_strategy` / `billing.confirm_large_threshold` 不再读取；不得为其建立第二套兼容逻辑。

## 2. 剩余验收

1. 当前纯 pytest、check_gates、prompt_gate、当前注册矩阵、web 测试与 tsc 按改动面运行。
2. 设置读写覆盖缺席、非法值、部分键与同会话生效；composer/dock 不出现确认偏好控件。
3. auto/ask × quote=0/正价 × 守卫线 × NULL × 有无制作意图的服务端矩阵与真实 Chat 各覆盖代表路径；Film 首稿单独验证不可同回合开工。
4. `conversation_usage` 在真实回合后检查：每回合一行、tokens/cache/cost/model/project 归属正确、多迭代聚合、空回合零行、记录失败不打断回复。
5. context 窗口边界与世界状态幸存有纯测试；是否调预算由真实 usage 分布决定，不凭旧候选值拍脑袋。
6. 费用四面同源，NULL 与守卫线文案诚实；积分余额、冻结与台账三处一致。
7. 旧配置清理先查目标环境：`SELECT * FROM configs WHERE key='billing.confirm_large_threshold'`；仅在确认残留且获授权后删除该 key，并记录实际执行状态。本轮文档整理未执行 SQL。

## Prohibited Behaviors

- 禁第二意图入口、第二 Start 机器或新的确认类型；禁以 auto 为由省略呈现、制作意图或 Film review hold。
- 禁会话计量上账单/UI，禁守卫线变成用户设置，禁客户端自行算价或推导 readiness。
- 禁为旧确认字段建立新迁移语义；禁用滚动摘要替代真实的窗口溢出证据。
- 当前 WorkSegment、Dock 两形态机、打字机与信封权威不得因设置或交付改动回退。
