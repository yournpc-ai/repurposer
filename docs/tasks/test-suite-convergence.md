# 测试与验证运行规范

> Status: ACTIVE。测试资产政策与部署前仪式链归 CLAUDE.md Testing 和 ADR-114；本文只维护 fixture、方差、配额与当前验证欠账，不记录测试删除或矩阵重排历史。

## 1. 当前资产边界

只保留两类测试资产：

1. **用户主流程旅程矩阵**：各种用户经 chat 完成各类创作流程的全旅程；以 `apps/api/scripts/chat_scenarios.py` 当前 `SCENARIOS` 注册表为准，不在文档复制固定数量。
2. **承重架构防漂移守卫**：唯一写口、依赖方向、registry↔prompt 一致性、执行身份、授权与数据完整性等全站铁律。

事故回归锁、批次产物和镜像实现形态的锁不单独保留。新覆盖必须能指出所属旅程与步骤，或所守的承重合同；重构使测试失去合同依据时逐案删除，不留注释尸体。

## 2. 当前验证层

- 部署前依次运行纯 pytest、check_gates、prompt 面变化时的 prompt_gate、当前注册旅程矩阵；web 按改动面运行纯 node 测试与类型检查。
- 剧本只锁服务端真值与形态，不锁 LLM 文案；打字机、remount、布局形态等客户端法律归 web 纯测试与 live 走查。
- 仪表脚本用于诊断，不阻塞部署；读数不能替代门禁，也不能为放行调整阈值。
- 测试迁移必须先裁决现行合同；“base 也失败”既不自动证明测试该删，也不证明应保留失败。

## 3. Fixture 与 flake 处置

- 剧本素材先复制到 `scenario/` 前缀；项目删除会 unlink 外部共享 key，禁止直接引用营销或用户资产。
- fixture 必须显式建立被测状态；常驻 worker 的时序不得定义剧本语义。手工 run 前后清理数据，修改 pipeline 后重启 worker。
- 断言只锁形态；红先归因机制。可用 pre-批面复跑、固定输入重复采样和失败签名频率区分回归、既有弱点与发射方差，禁止调断言放行。
- 连续出现同类方差时登记 PROGRESS，保留原始输出、工具调用和应用处理证据，不静默重试到绿。

### 3.6 已知方差与覆盖边界

- S1 / S6f / S10 的 baseline LLM 方差是开放观察项，不自动放大为新的 release regression；每次仍需在当前 HEAD 归因。
- prompt_gate I 需以新目标的实际读数完成校准；校准与回归放行是两件事。
- 以下风险目前没有完整活旅程自动化看护：计费失败、孤儿 hold 回收、run 执行权仲裁、turn durability、SSE 断流复连、repair 静默/泄漏。相关纯函数覆盖不能冒充全链覆盖；是否补入矩阵须按用户旅程归属评估。
- `migrate_activity_log_rows.py` 只有在目标环境迁移与真实回放验证完成后才可退役。
- trigger `/event/sync` 无 Activity 行是 parity 观察，不自动等同于缺陷或新需求。

## 4. 当前后续工作

- `verification-overhaul.md` 只保留 PLANNED 的 harness 归位与文档升格；未启动前所有现有路径保持有效。
- Film 独立 prompt_gate 探针族、真实 SSE/断流恢复和动态视听验收分别归 PROGRESS 与 Film execution，不在本文复制操作矩阵。
- 当前未运行或尚未归因的检查必须写“未运行/未归因”，旧计数与旧全绿记录不得转信。

## 5. Harness 纪律

- **进程卫生**：`uv run` 包装器被 kill 可能留下孤儿 worker；手工 harness 使用 `start_new_session` + `killpg`，结束时核对实际进程。
- **配额**：全量剧本/gate 可能产生显著模型费用；合并改动后一次跑，所有真实模型 HTTP 计入预算，warmup 默认关闭。付费运行需明确授权。
- **探针采样**：需要比较 provider/prompt 时采用 round-robin，避免顺序批把 provider 漂移误判为改动效果；保留原始读数。
- **升编**：scratch 工具一旦被现行文档或部署仪式引用，就应迁入受维护的 harness/scripts 位置；不要长期让关键验收依赖一次性目录。
- **文档**：当前注册表、命令和已知限制就地更新；不保存历史测试输出、调用量日志或旧矩阵副本。
