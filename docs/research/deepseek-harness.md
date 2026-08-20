# DeepSeek Harness（dsh）架构调研

> Status: 已评审（2026-08-20 调研，证据层存档）。采纳项已分流——需求池条目在 `PROGRESS.md`（agent 调用台账 / 闸门编目 / LLM 录制回放层 / provider 边界规范化 / 命名对齐批）、命名裁决在 `NAMING.md` 判例库、行业坐标映射在 `AGENT_ARCHITECTURE.md` §2.5。本文只存调研证据与裁决理由，不复述上述现行决策。

## 1. 调研对象

- 仓库：https://github.com/deepseek-ai/deepseek-harness（调研时 commit `141eb6f`，2026-08-19）
- 文档站：https://deepseek-harness.github.io/deepseek-harness/（由 `docs/` 双语源经 VitePress 投影生成）
- 同源参照（本次一并核对）：Mastra AgentController（https://mastra.ai/docs/harness/overview）、Agno AgentOS（https://docs.agno.com/features/api）

**它是什么**：DeepSeek 官方的通用 coding-agent harness（Claude Code 同类）——vendored Cordis 插件框架上「万物皆插件，无特权内核」，TypeScript ESM monorepo，46 个子系统包，交付形态 = CLI + Web GUI + headless runner + ACP 自动化服务器 + TS/Python 双 SDK。

**承重墙**：append-only `SessionEvent` 日志是单一事实源。消息历史 `deriveMessages()` 从日志投影；compaction 用 `surfaceOp: replace` + `sourceEventSeqs` 改写表层；fork 继承稳定前缀；崩溃恢复合成 `interrupted` 的 `turn/end`；token-meter 对日志做 per-session fold；goal / agent-team 状态全是日志 fold。总闸是一条运行时不变式：**model-visible ⟺ logged**——抵达模型请求的一切必须能从日志重建，新增模型可见输入 = 新增会话事件。

## 2. 架构骨架

**Cordis 插件框架**：插件 = 带 `inject` / `apply(ctx)` 的 Service；`ctx` 服务容器按稳定键查找（`ctx.tools` / `ctx.llm` / `ctx.sessions`…）；`inject` 声明依赖决定加载序；类型化事件四种分发模式（`emit` / `waterfall` / `parallel` / `serial`，模式是事件公开约定的一部分，`@mode` 标签 + 生成目录交叉校验）；**注册 = 可逆副作用**（`ctx.effect()` 返回 disposer，reload/teardown 逐层撤销）；waterfall = 环绕中间件（`next()` 委托，不调用即短路）。

**turn-flow**：turn = 0..n step；step = 一次模型请求 + 它调用的工具。`agent/pre-step`（waterfall）是请求推导前唯一串行拦截链（reject | enter(messages)）；输入经持久 inbox（`next-turn` / `next-step` 两列）到达，`steer()` 中途引导、`inject()` 注入下一步上下文；`agent/request-error` 处理失败请求，`agent/turn-stopping` 可由 steering 阻止轮次关闭。

**capability seam 三角**：每个可替换能力 = Service Definition（接口）+ Service Provider（实现）+ Consumer（通常是面向模型的工具），三者齐设。fs / subprocess / shell / llm / compaction / subagent / workflow / skills / storage / settings / credentials 皆然。替换 provider 即替换整条能力线（如 fs+subprocess 指向远程沙箱，Bash/PTY/LSP 一并搬过去）。

**组合层**：profile（web / headless 模板）= bundle patch 层的有序叠加 + 用户 patch；agent presets = per-session 能力组合（preset cordis.yml 挂进 agent 作用域）。

**子系统分组（46）**：内核与作用域（core/session/system-prompt/tools/agent/agent-loop/scope/invariants/typert）· 会话与持久化（persistence JSONL+SQLite / session-query / session-reference / session-title / session-projection(+cache) / spill / session-telemetry）· 模型与上下文（llm-streaming / token-meter / compaction(+tool-result-pruner)）· 执行与工具（shell / subprocess / terminal / filesystem / lsp / code-runtime / web / skills / workflow / subagent / jobs）· 策略与交互（approval / permission-presets / sandbox(+policy) / plan-mode / user-questions / commands / goal / schedule）· 平台与接入（web-server / client-modules / storage(+domain) / workspace / settings / credentials / api-gateway）。

## 3. 对照裁决（理由存档；现行决策以分流去处为准）

### 维持否决

| dsh 机制 | 否决理由 |
|---|---|
| Cordis 插件系统 | 平台解法：第三方从配置替换一切（含 loop 本身）。产品是静态注册表随代码部署（NAMING §5），注册即得全套纪律，不要平行映射表与特判 |
| compaction 全家（pressure pre-step / tool-result 剪枝 / surface replace） | AGENT_ARCH §5.4：短调用 + 每节点精确装配，没有可压缩的增长 transcript。事件溯源解决「可变的单条 transcript」，我们没有可变 transcript（历史从不改写，只追加新 run） |
| steering / approval / sandbox / permission-presets | 交互式编码 agent 的执行危险控制面。我们的审批面 = dock/checkpoint 确认（提议→裁决→预览→执行），已是一等产品面；agent 不执行任意工具 |
| tool-call loop 脚手架 | 禁 ReAct 铁律 |
| subagent seam / agent teams | delegation 是单 context agent 的逃生口；我们的中间产物落库可寻址，协作沿 DAG 边流动，agent 互不对话 |
| workflow 引擎（模型写 JS 编排脚本） | 与 ADR-028（拓扑代码定，LLM 永不塑形图）正面对立。其护栏（meta 纯数据校验、fatal 错误绝不映射 null、agent 数上限、事件只观察）正是开这扇门必须付的税 |

### 采纳（已分流 PROGRESS 需求池）

1. **agent 调用台账**——`assistant/message` 纪律：每次 provider 调用（含空内容 / max-tokens / 校验失败首试）都是落库事实，usage 永留；升级为取证级 = 调用 envelope 可重建（model-visible ⟺ logged 的账簿形态）。行业座位 = Agno Traces。
2. **闸门编目（invariants）**——包级配套注册 + explained-empty（`No runtime invariant: <原因>`，机械闸拒绝无解释的空）+ 闸只断言自有数据关系（事件流/可变数据，绝不断言服务存在性）。
3. **LLM 录制回放层**——`llm-replay` 包先例：适配器 seam 录制真实 provider 流，无密钥确定性回放；与全真 e2e 分工（他们的 snapshot（无密钥） vs test:e2e（带密钥）格局）。
4. **provider 边界规范化**——defensive-patterns「公共约定两侧都要遵守」：适配器可抛异常可发 error finish，runtime 只以终止型 finish 单态暴露；消费方永不猜异常来源。

### 平手互证（双向确认，无动作）

- **崩溃语义**：他们恢复时合成 `interrupted`（日志永不说谎）；我们 `reap_stale` 收孤儿 + claim loop 重跑 runner（行级重认领）。等价结果不同机制。
- **计量**：token-meter = 日志 fold 出**压力**快照（喂 compaction）；我们 metering = usage → **cost**（喂校准）。同一条纪律：量 = 事实的纯函数。
- **文档法则**：one home per fact（tier 表 ≈ README 单一事实源表）；「Document current state, not change history」（≈ 文档不保留历史）；slop 清单（同规两 home / 叙事历史 / prose 标状态 ≈ 既有禁忌逐条同款）；Agent Note 随非平凡 PR 必交 + archived 冻结（≈ 拍板同批落档 + DECISIONS 只留现行）。
- **pre-release stance**：正确地基 > 兼容补丁，随意改名，格式版本不给兼容承诺（≈ reset_db 清盘姿势）。

### 治理机械化差距（我们低一档，记录不排期）

`verify-doc-budgets`（文档词数预算闸）/ `verify-type-equiv`（文档类型声明与源码逐字节比对）/ `verify-md-links`（死链闸）/ `doc-typecheck`（文档代码块必须编译）/ 生成目录 byte-verified / 双语配对记录。我们同哲学但靠人肉；死链检查是唯一的便宜可偷项。

### defensive-patterns 摘译（生命周期/并发/清理代码参照）

1. **正交结果独立上报**：超时 / 信号 / 退出码各自独立上报，绝不嵌套在彼此分支里（否则提前终止被误判正常成功）。
2. **公共约定两侧都要遵守**：同一结果的多种表示在公共 API 前规范化单态。
3. **异步状态不是同步状态**：`agent/status` 不是某次 followup 的结果；自动化调用方必须显式定义自己的区间（持久回执 → 下一次 idle）。
4. **dispose 必须达到完全停稳**：清理流程等待工作真正停止，不只发停止信号。
5. **分发器中隔离回调异常**：行为不当的订阅者绝不能破坏核心生命周期。
6. **凭证环境消毒**：启动命令剔除 `*KEY*` / `*SECRET*` / `*TOKEN*` / `*PASSWORD*` 环境变量；spill 文件 0700 私目录 + 随机名 + 独占打开。

## 4. 五源原始词汇（证据清单）

**dsh**：session / turn / step / inbox / steer / inject / pre-step / tool / skill（指令包）/ compaction / token-meter / spill / subagent / agent-team / workflow（编排脚本）/ goal / approval / permission-preset / sandbox / invariant / projection / preset / bundle / profile / branded-id / effect（disposer）。

**Mastra AgentController**：AgentController（共享运行时宿主）/ **Session**（隔离的 live runtime：mode/model/state/事件总线/run state/grants）/ **Thread**（持久对话：messages + settings）/ Mode（同一 Agent 的指令与工具视图，`transitionsTo`）/ Workspace / Storage / permissions（ask/allow/deny）/ `tool_approval_required` / **`tool_suspended`** + `respondToToolSuspension` / forked subagent / channels。

**Agno AgentOS**：Run / Session / **Memory**（用户记忆：CRUD + 搜索 + 主题过滤 + token 优化）/ **Learnings**（runs 捕获的学习记录）/ Knowledge（RAG 文档库）/ Eval（accuracy / agent-as-judge / reliability）/ **Traces**（span tree / filter DSL / LLM+tool 调用检查）/ Metrics / Schedules / Approvals / Components（版本管理/草稿/发布/回滚）。

**对我们的词汇出处核对**（NAMING 判例已引用者）：`run`（N-13，GitHub Actions / Mastra `workflow.createRun()` 先例）✅ 仍与五源同词；`agent`（N-29，Mastra/Agno/Anthropic）✅；`Suspend`（N-54 参照 Mastra）✅ 与 `tool_suspended` 同族；**Actor 退役（N-31）✅ 五源词表均无 actor**。
